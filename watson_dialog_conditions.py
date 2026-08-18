#!/usr/bin/env python3
"""Statically analyze boolean conditions in a Watson Assistant Dialog export."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from watson_dialog_diff import DEFAULT_MAX_INPUT_BYTES, configure_utf8_output, load_json
from watson_spel import UNKNOWN, SpelError, evaluate_condition


MAX_TERMS = 256
INTENT_PATTERN = re.compile(r"(?<![\w#])#([\w.-]+)")
ENTITY_PATTERN = re.compile(r"(?<![\w@])@([\w-]+)")
VARIABLE_PATTERN = re.compile(r"\$([A-Za-z_][\w-]*)")
INVALID_ENTITY_SHORTHAND_MEMBER = re.compile(r"@[\w-]+:\([^)]*\)\s*\.\s*[A-Za-z_]\w*")
INVALID_ENTITY_CALL = re.compile(r"@[\w-]+\s*\(")
INVALID_ENTITY_CALL_NAME = re.compile(r"@([\w-]+)\s*\(")
COMPARISON_PATTERN = re.compile(r"^\s*([\$A-Za-z_][\w.\[\]'\"]*)\s*(==|!=)\s*(['\"][^'\"]*['\"]|-?\d+(?:\.\d+)?)\s*$")


@dataclass(frozen=True)
class Formula:
    kind: str
    value: Any


def sorted_siblings(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(nodes, key=lambda node: (node.get("sequencia") is None, node.get("sequencia", 0), str(node.get("uuid") or "")))


def strip_outer_parentheses(expression: str) -> str:
    expression = expression.strip()
    while expression.startswith("(") and expression.endswith(")"):
        depth = 0
        quote: str | None = None
        wraps_all = True
        for index, character in enumerate(expression):
            if quote:
                if character == quote and expression[index - 1] != "\\":
                    quote = None
            elif character in "'\"":
                quote = character
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0 and index != len(expression) - 1:
                    wraps_all = False
                    break
        if not wraps_all or depth != 0:
            break
        expression = expression[1:-1].strip()
    return expression


def split_top_level(expression: str, symbols: tuple[str, ...], words: tuple[str, ...]) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    index = 0
    upper = expression.upper()
    while index < len(expression):
        character = expression[index]
        if quote:
            if character == quote and (index == 0 or expression[index - 1] != "\\"):
                quote = None
            index += 1
            continue
        if character in "'\"":
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif depth == 0:
            symbol = next((item for item in symbols if expression.startswith(item, index)), None)
            if symbol:
                parts.append(expression[start:index].strip())
                start = index + len(symbol)
                index = start
                continue
            word = next((item for item in words if upper.startswith(item, index) and (index == 0 or not upper[index - 1].isalnum()) and (index + len(item) == len(upper) or not upper[index + len(item)].isalnum())), None)
            if word:
                parts.append(expression[start:index].strip())
                start = index + len(word)
                index = start
                continue
        index += 1
    if not parts:
        return [expression.strip()]
    parts.append(expression[start:].strip())
    return parts


def parse_formula(expression: str) -> Formula:
    expression = strip_outer_parentheses(expression)
    if expression.lower() == "true":
        return Formula("const", True)
    if expression.lower() == "false":
        return Formula("const", False)
    parts = split_top_level(expression, ("||",), ("OR",))
    if len(parts) > 1:
        return Formula("or", tuple(parse_formula(part) for part in parts))
    parts = split_top_level(expression, ("&&",), ("AND",))
    if len(parts) > 1:
        return Formula("and", tuple(parse_formula(part) for part in parts))
    if expression.startswith("!") and not expression.startswith("!="):
        return Formula("not", parse_formula(expression[1:].strip()))
    return Formula("atom", re.sub(r"\s+", " ", expression).strip())


def merge_terms(left: dict[str, bool], right: dict[str, bool]) -> dict[str, bool] | None:
    result = dict(left)
    equalities: dict[str, str] = {}
    inequalities: set[tuple[str, str]] = set()
    for key, value in [*left.items(), *right.items()]:
        if key in result and result[key] != value:
            return None
        result[key] = value
        match = COMPARISON_PATTERN.match(key)
        if not match:
            continue
        subject, operator, literal = match.groups()
        literal = literal.strip("'\"")
        if operator == "==" and value:
            if subject in equalities and equalities[subject] != literal:
                return None
            if (subject, literal) in inequalities:
                return None
            equalities[subject] = literal
        elif operator == "!=" and value:
            if equalities.get(subject) == literal:
                return None
            inequalities.add((subject, literal))
    return result


def terms(formula: Formula, negated: bool = False) -> list[dict[str, bool]]:
    if formula.kind == "const":
        return [{}] if formula.value != negated else []
    if formula.kind == "atom":
        return [{formula.value: not negated}]
    if formula.kind == "not":
        return terms(formula.value, not negated)
    if formula.kind == "or":
        children = formula.value if not negated else tuple(Formula("not", child) for child in formula.value)
        if negated:
            return terms(Formula("and", children))
        return [term for child in children for term in terms(child)] [:MAX_TERMS]
    if formula.kind == "and":
        children = formula.value if not negated else tuple(Formula("not", child) for child in formula.value)
        if negated:
            return terms(Formula("or", children))
        product: list[dict[str, bool]] = [{}]
        for child in children:
            next_product: list[dict[str, bool]] = []
            for left in product:
                for right in terms(child):
                    merged = merge_terms(left, right)
                    if merged is not None:
                        next_product.append(merged)
            product = next_product[:MAX_TERMS]
        return product
    raise ValueError(f"Tipo de fórmula desconhecido: {formula.kind}")


def formula_contains_constant(formula: Formula, value: bool) -> bool:
    """Return whether a parsed formula contains an explicit boolean constant."""
    if formula.kind == "const":
        return formula.value is value
    if formula.kind == "not":
        return formula_contains_constant(formula.value, value)
    if formula.kind in {"and", "or"}:
        return any(formula_contains_constant(child, value) for child in formula.value)
    return False


def analyze_formula(condition: str) -> dict[str, Any]:
    normalized = condition.strip()
    parsed = parse_formula(normalized)
    satisfiable_terms = terms(parsed)
    return {
        "normalized": normalized,
        "is_satisfiable": bool(satisfiable_terms),
        "is_always_true": normalized.lower() == "true",
        # Watson Dialog explicitly supports `false` as a deliberate way to
        # disable a branch or keep it only as an alternate jump target.
        # Preserve that intent separately from accidental contradictions.
        "has_explicit_false": formula_contains_constant(parsed, False),
    }


def known_artifacts(document: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    intents = {str(item["nome"]) for item in document.get("intencoes", []) if isinstance(item, dict) and item.get("nome")}
    entities = {str(item["nome"]) for item in document.get("entidades", []) if isinstance(item, dict) and item.get("nome")}
    variables = {str(item["variavelContexto"]).lstrip("$") for item in document.get("variaveisContexto", []) if isinstance(item, dict) and item.get("variavelContexto")}
    return intents, entities, variables


def condition_references(condition: str) -> dict[str, list[str]]:
    code = re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"", lambda match: " " * len(match.group(0)), condition)
    return {
        "intents": sorted(set(INTENT_PATTERN.findall(code))),
        "entities": sorted(set(ENTITY_PATTERN.findall(code))),
        "variables": sorted(set(VARIABLE_PATTERN.findall(code))),
    }


def iter_groups(nodes: list[dict[str, Any]], parent: str = "root") -> Any:
    yield parent, sorted_siblings(nodes)
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("uuid") or "(sem_uuid)")
        children = node.get("filhos") or []
        if children:
            yield from iter_groups(children, node_id)
        for slot in node.get("slots") or []:
            if not isinstance(slot, dict):
                continue
            slot_id = f"slot:{slot.get('uuid') or '(sem_uuid)'}"
            yield slot_id, sorted_siblings(slot.get("filhos") or [])
            for child in slot.get("filhos") or []:
                if isinstance(child, dict):
                    nested = child.get("filhos") or []
                    if nested:
                        yield from iter_groups(nested, str(child.get("uuid") or "(sem_uuid)"))


def iter_conditions(document: dict[str, Any]) -> Any:
    def visit(nodes: list[dict[str, Any]]) -> Any:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("uuid") or "(sem_uuid)")
            if node.get("condicao"):
                yield node_id, "dialog_node", str(node["condicao"])
            for response in node.get("respostas") or []:
                if isinstance(response, dict):
                    condition = response.get("condicao") or response.get("conditions")
                    if condition:
                        yield f"response:{node_id}:{response.get('uuid', '')}", "response_condition", str(condition)
            for slot in node.get("slots") or []:
                if isinstance(slot, dict):
                    if slot.get("condicao"):
                        yield f"slot:{slot.get('uuid') or '(sem_uuid)'}", "slot", str(slot["condicao"])
                    yield from visit(slot.get("filhos") or [])
            yield from visit(node.get("filhos") or [])
    yield from visit(document.get("nos") or [])


def dormant_legacy_nodes(document: dict[str, Any], formula_by_node: dict[str, dict[str, Any]]) -> set[str]:
    """Return nodes dormant themselves or underneath dormant source evidence.

    A path is treated as dormant for *active-flow diagnostics* when the
    normalized source marks a node `INATIVO` or when that node's condition is
    statically unsatisfiable.  This does not erase the node: explicit-false
    branches can still be valid jump targets and remain present in graph/data
    outputs.
    """
    dormant: set[str] = set()

    def visit(nodes: list[dict[str, Any]], ancestor_dormant: bool = False) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("uuid") or "(sem_uuid)")
            formula = formula_by_node.get(node_id)
            own_dormant = (
                str(node.get("status") or "").strip().upper() in {"INATIVO", "REVISAO"}
                or (formula is not None and not formula["is_satisfiable"])
            )
            current_dormant = ancestor_dormant or own_dormant
            if current_dormant:
                dormant.add(node_id)
            for slot in node.get("slots") or []:
                if isinstance(slot, dict):
                    visit(slot.get("filhos") or [], current_dormant)
            visit(node.get("filhos") or [], current_dormant)

    yield_nodes = document.get("nos") or []
    if isinstance(yield_nodes, list):
        visit(yield_nodes)
    return dormant


def observed_jump_targets(document: dict[str, Any]) -> set[str]:
    """Collect legacy node IDs that have an explicit alternate jump entry."""
    targets: set[str] = set()

    def capture(value: Any) -> None:
        if value not in (None, "", "root"):
            targets.add(str(value))

    def visit(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            capture(node.get("uuidEnviarPara"))
            for response in node.get("respostas") or []:
                if isinstance(response, dict):
                    capture(response.get("uuidEnviarPara") or response.get("dialog_node"))
            for slot in node.get("slots") or []:
                if isinstance(slot, dict):
                    capture(slot.get("uuidEnviarPara"))
                    for response in slot.get("respostas") or []:
                        if isinstance(response, dict):
                            capture(response.get("uuidEnviarPara") or response.get("dialog_node"))
                    visit(slot.get("filhos") or [])
            visit(node.get("filhos") or [])

    yield_nodes = document.get("nos") or []
    if isinstance(yield_nodes, list):
        visit(yield_nodes)
    return targets


def sibling_order_is_proven(siblings: list[dict[str, Any]]) -> bool:
    """Whether legacy sibling order can be derived without a tie-break guess."""
    if len(siblings) <= 1:
        return True
    sequences = [node.get("sequencia") for node in siblings if isinstance(node, dict)]
    return all(sequence is not None for sequence in sequences) and len(set(sequences)) == len(sequences)


def analyze_conditions(document: dict[str, Any], check_variables: bool = False, summary_only: bool = False) -> dict[str, Any]:
    intents, entities, variables = known_artifacts(document)
    issues: list[dict[str, str]] = []

    def add(issue_type: str, severity: str, node: str, message: str, condition: str) -> None:
        issues.append({"type": issue_type, "severity": severity, "node": node, "message": message, "condition": condition})

    formula_by_node: dict[str, dict[str, Any]] = {}
    for node, _kind, condition in iter_conditions(document):
        formula = analyze_formula(condition)
        formula_by_node[node] = formula

    dormant_nodes = dormant_legacy_nodes(document, formula_by_node)
    jump_targets = observed_jump_targets(document)

    for node, _kind, condition in iter_conditions(document):
        formula = formula_by_node[node]
        if not formula["is_satisfiable"]:
            if formula["has_explicit_false"]:
                add("disabled_condition_false", "info", node, "A condição contém `false` explícito e mantém o ramo deliberadamente desabilitado no fluxo normal.", condition)
            else:
                add("unsatisfiable_condition", "warning", node, "A condição é logicamente impossível sem um `false` explícito de desabilitação.", condition)
        if INVALID_ENTITY_SHORTHAND_MEMBER.search(condition):
            add("invalid_spel_entity_shorthand_member", "error", node, "Um atalho @entidade:(valor) já retorna booleano e não pode acessar uma propriedade como .literal.", condition)
        invalid_called_entities = set(INVALID_ENTITY_CALL_NAME.findall(condition))
        if invalid_called_entities:
            add("invalid_spel_entity_call", "error", node, "Entidades não são funções; a sintaxe @entidade(...) é inválida.", condition)

        owner = node.split(":")[1] if node.startswith("response:") else (node.removeprefix("slot:") if node.startswith("slot:") else node)
        is_dormant = node in dormant_nodes or owner in dormant_nodes
        ref_severity = "info" if is_dormant else "warning"

        for intent in condition_references(condition)["intents"]:
            if intent not in intents:
                add("unknown_intent", ref_severity, node, f"Intent não definida: #{intent}.", condition)
        for entity in condition_references(condition)["entities"]:
            if entity in invalid_called_entities:
                continue
            if entity not in entities and not entity.startswith("sys-"):
                add("unknown_entity", ref_severity, node, f"Entidade não definida: @{entity}.", condition)
        if check_variables:
            for variable in condition_references(condition)["variables"]:
                if variable not in variables and variable not in {"integrations", "skills"}:
                    add("unknown_variable", "info", node, f"Variável de contexto não declarada: ${variable}.", condition)
    for _group, siblings in iter_groups(document.get("nos") or []):
        # Do not invent a UUID tie-break and then report reachability from it.
        # Duplicate/missing legacy sequence values make relative order an
        # unresolved provenance question; the unified validator reports that
        # separately as `legacy_order_ambiguous`.
        if not sibling_order_is_proven(siblings):
            continue
        always_true: tuple[str, int] | None = None
        seen: dict[str, tuple[str, int]] = {}
        for index, node in enumerate(siblings):
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("uuid") or "(sem_uuid)")
            if node_id in dormant_nodes:
                continue
            condition = str(node.get("condicao") or "")
            if not condition:
                continue
            formula = formula_by_node.get(node_id, analyze_formula(condition))
            if always_true:
                always_true_id, always_true_index = always_true
                interval = {str(item.get("uuid") or "(sem_uuid)") for item in siblings[always_true_index + 1:index + 1] if isinstance(item, dict)}
                if not (interval & jump_targets):
                    add("shadowed_by_always_true", "warning", node_id, f"Um nó anterior ({always_true_id}) com condição true impede a avaliação deste irmão no fluxo normal, sem entrada Jump observada no intervalo.", condition)
            elif formula["normalized"] in seen and formula["is_satisfiable"]:
                prior_id, prior_index = seen[formula["normalized"]]
                interval = {str(item.get("uuid") or "(sem_uuid)") for item in siblings[prior_index + 1:index + 1] if isinstance(item, dict)}
                if not (interval & jump_targets):
                    add("duplicate_sibling_condition", "info", node_id, f"Condição idêntica à do irmão anterior {prior_id}, sem entrada Jump observada no intervalo.", condition)
            if formula["is_always_true"]:
                always_true = (node_id, index)
            seen.setdefault(formula["normalized"], (node_id, index))

    ordered_issues = sorted(issues, key=lambda issue: (issue["node"], issue["type"], issue["condition"]))
    by_type = {issue_type: sum(issue["type"] == issue_type for issue in ordered_issues) for issue_type in sorted({issue["type"] for issue in ordered_issues})}
    return {
        "schema_version": 1,
        "summary": {"conditions": len(formula_by_node), "issues": len(ordered_issues), "issues_by_type": by_type},
        "issues": [] if summary_only else ordered_issues,
    }


def evaluate_document_conditions(document: dict[str, Any], environment: dict[str, Any], summary_only: bool = False) -> dict[str, Any]:
    """Evaluate every node/slot condition against one supplied runtime state."""
    evaluations: list[dict[str, str]] = []
    for node, kind, condition in iter_conditions(document):
        try:
            result = evaluate_condition(condition, environment)
            value = "unknown" if result is UNKNOWN else str(result).lower()
        except Exception:
            value = "unknown"
        evaluations.append({"node": node, "kind": kind, "condition": condition, "result": value})
    evaluations.sort(key=lambda item: item["node"])
    return {
        "summary": {key: sum(item["result"] == key for item in evaluations) for key in ("true", "false", "unknown")},
        "evaluations": [] if summary_only else evaluations,
    }


def main() -> int:
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Analisa alcançabilidade e referências em condições do Watson Assistant Dialog.")
    parser.add_argument("input", type=Path, help="export JSON do Watson Assistant")
    parser.add_argument("--output", type=Path, help="arquivo de saída; padrão: stdout")
    parser.add_argument("--check-variables", action="store_true", help="também valida variáveis fora de variaveisContexto; pode gerar avisos para integrações externas")
    parser.add_argument("--scenario", type=Path, help="JSON com input, context, intents e entities para avaliar as condições")
    parser.add_argument("--max-input-bytes", type=int, default=None, help="limite máximo em bytes; padrão: WATSON_DIALOG_MAX_BYTES ou 50 MiB")
    parser.add_argument("--summary-only", action="store_true", help="emite apenas sumário consolidado de contagens")
    args = parser.parse_args()
    try:
        doc = load_json(args.input, max_bytes=args.max_input_bytes)
        report = analyze_conditions(doc, check_variables=args.check_variables, summary_only=args.summary_only)
        if args.scenario:
            scenario_data = load_json(args.scenario, max_bytes=args.max_input_bytes)
            report["evaluation"] = evaluate_document_conditions(doc, scenario_data, summary_only=args.summary_only)
    except (ValueError, KeyError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 1 if report["summary"]["issues"] or report.get("evaluation", {}).get("summary", {}).get("unknown") else 0


if __name__ == "__main__":
    raise SystemExit(main())
