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

from watson_dialog_diff import load_json
from watson_spel import UNKNOWN, SpelError, evaluate_condition


MAX_TERMS = 256
INTENT_PATTERN = re.compile(r"(?<![\w#])#([\w.-]+)")
ENTITY_PATTERN = re.compile(r"(?<![\w@])@([\w-]+)")
VARIABLE_PATTERN = re.compile(r"\$([A-Za-z_][\w-]*)")
INVALID_ENTITY_SHORTHAND_MEMBER = re.compile(r"@[\w-]+:\([^)]*\)\s*\.\s*[A-Za-z_]\w*")
INVALID_ENTITY_CALL = re.compile(r"@[\w-]+\s*\(")
COMPARISON_PATTERN = re.compile(r"^\s*([\$A-Za-z_][\w.\[\]'\"]*)\s*(==|!=)\s*(['\"][^'\"]*['\"]|-?\d+(?:\.\d+)?)\s*$")


@dataclass(frozen=True)
class Formula:
    kind: str
    value: Any


def sorted_siblings(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(nodes, key=lambda node: (node.get("sequencia") is None, node.get("sequencia", 0), str(node["uuid"])))


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
        result = [{}]
        for child in children:
            result = [merged for left in result for right in terms(child) if (merged := merge_terms(left, right)) is not None][:MAX_TERMS]
        return result
    raise ValueError(f"Tipo de fórmula desconhecido: {formula.kind}")


def analyze_formula(condition: str) -> dict[str, Any]:
    normalized = condition.strip()
    parsed = parse_formula(normalized)
    satisfiable_terms = terms(parsed)
    return {
        "normalized": normalized,
        "is_satisfiable": bool(satisfiable_terms),
        "is_always_true": normalized.lower() == "true",
    }


def known_artifacts(document: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    intents = {str(item["nome"]) for item in document.get("intencoes", []) if item.get("nome")}
    entities = {str(item["nome"]) for item in document.get("entidades", []) if item.get("nome")}
    variables = {str(item["variavelContexto"]).lstrip("$") for item in document.get("variaveisContexto", []) if item.get("variavelContexto")}
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
        node_id = str(node["uuid"])
        children = node.get("filhos") or []
        if children:
            yield from iter_groups(children, node_id)
        for slot in node.get("slots") or []:
            slot_id = f"slot:{slot['uuid']}"
            yield slot_id, sorted_siblings(slot.get("filhos") or [])
            for child in slot.get("filhos") or []:
                nested = child.get("filhos") or []
                if nested:
                    yield from iter_groups(nested, str(child["uuid"]))


def iter_conditions(document: dict[str, Any]) -> Any:
    def visit(nodes: list[dict[str, Any]]) -> Any:
        for node in nodes:
            if node.get("condicao"):
                yield str(node["uuid"]), "dialog_node", str(node["condicao"])
            for response in node.get("respostas") or []:
                condition = response.get("condicao") or response.get("conditions")
                if condition:
                    yield f"response:{node['uuid']}:{response.get('uuid', '')}", "response_condition", str(condition)
            for slot in node.get("slots") or []:
                if slot.get("condicao"):
                    yield f"slot:{slot['uuid']}", "slot", str(slot["condicao"])
                yield from visit(slot.get("filhos") or [])
            yield from visit(node.get("filhos") or [])
    yield from visit(document.get("nos") or [])


def analyze_conditions(document: dict[str, Any], check_variables: bool = False) -> dict[str, Any]:
    intents, entities, variables = known_artifacts(document)
    issues: list[dict[str, str]] = []

    def add(issue_type: str, severity: str, node: str, message: str, condition: str) -> None:
        issues.append({"type": issue_type, "severity": severity, "node": node, "message": message, "condition": condition})

    formula_by_node: dict[str, dict[str, Any]] = {}
    for node, _kind, condition in iter_conditions(document):
        formula = analyze_formula(condition)
        formula_by_node[node] = formula
        if not formula["is_satisfiable"]:
            add("unsatisfiable_condition", "warning", node, "A condição é logicamente impossível.", condition)
        if INVALID_ENTITY_SHORTHAND_MEMBER.search(condition):
            add("invalid_spel_entity_shorthand_member", "error", node, "Um atalho @entidade:(valor) já retorna booleano e não pode acessar uma propriedade como .literal.", condition)
        if INVALID_ENTITY_CALL.search(condition):
            add("invalid_spel_entity_call", "error", node, "Entidades não são funções; a sintaxe @entidade(...) é inválida.", condition)
        for intent in condition_references(condition)["intents"]:
            if intent not in intents:
                add("unknown_intent", "warning", node, f"Intent não definida: #{intent}.", condition)
        for entity in condition_references(condition)["entities"]:
            if entity not in entities and not entity.startswith("sys-"):
                add("unknown_entity", "warning", node, f"Entidade não definida: @{entity}.", condition)
        if check_variables:
            for variable in condition_references(condition)["variables"]:
                if variable not in variables and variable not in {"integrations", "skills"}:
                    add("unknown_variable", "info", node, f"Variável de contexto não declarada: ${variable}.", condition)

    for group, siblings in iter_groups(document.get("nos") or []):
        always_true: str | None = None
        seen: dict[str, str] = {}
        for node in siblings:
            node_id = str(node["uuid"])
            condition = str(node.get("condicao") or "")
            if not condition:
                continue
            formula = formula_by_node.get(node_id, analyze_formula(condition))
            if always_true:
                add("shadowed_by_always_true", "warning", node_id, f"Um nó anterior ({always_true}) com condição true impede a avaliação deste irmão.", condition)
            elif formula["normalized"] in seen and formula["is_satisfiable"]:
                add("duplicate_sibling_condition", "info", node_id, f"Condição idêntica à do irmão anterior {seen[formula['normalized']]}.", condition)
            if formula["is_always_true"]:
                always_true = node_id
            seen.setdefault(formula["normalized"], node_id)

    ordered_issues = sorted(issues, key=lambda issue: (issue["node"], issue["type"], issue["condition"]))
    by_type = {issue_type: sum(issue["type"] == issue_type for issue in ordered_issues) for issue_type in sorted({issue["type"] for issue in ordered_issues})}
    return {
        "schema_version": 1,
        "summary": {"conditions": len(formula_by_node), "issues": len(ordered_issues), "issues_by_type": by_type},
        "issues": ordered_issues,
    }


def evaluate_document_conditions(document: dict[str, Any], environment: dict[str, Any]) -> dict[str, Any]:
    """Evaluate every node/slot condition against one supplied runtime state."""
    evaluations: list[dict[str, str]] = []
    for node, kind, condition in iter_conditions(document):
        try:
            result = evaluate_condition(condition, environment)
            value = "unknown" if result is UNKNOWN else str(result).lower()
        except SpelError as error:
            value = "unknown"
        evaluations.append({"node": node, "kind": kind, "condition": condition, "result": value})
    evaluations.sort(key=lambda item: item["node"])
    return {
        "summary": {key: sum(item["result"] == key for item in evaluations) for key in ("true", "false", "unknown")},
        "evaluations": evaluations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Analisa alcançabilidade e referências em condições do Watson Assistant Dialog.")
    parser.add_argument("input", type=Path, help="export JSON do Watson Assistant")
    parser.add_argument("--output", type=Path, help="arquivo de saída; padrão: stdout")
    parser.add_argument("--check-variables", action="store_true", help="também valida variáveis fora de variaveisContexto; pode gerar avisos para integrações externas")
    parser.add_argument("--scenario", type=Path, help="JSON com input, context, intents e entities para avaliar as condições")
    args = parser.parse_args()
    try:
        report = analyze_conditions(load_json(args.input), check_variables=args.check_variables)
        if args.scenario:
            report["evaluation"] = evaluate_document_conditions(load_json(args.input), load_json(args.scenario))
    except (ValueError, KeyError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 1 if report["issues"] or report.get("evaluation", {}).get("summary", {}).get("unknown") else 0


if __name__ == "__main__":
    raise SystemExit(main())
