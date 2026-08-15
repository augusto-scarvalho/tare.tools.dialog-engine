#!/usr/bin/env python3
"""Validate a Watson Assistant Dialog export using one stable issue contract.

The validator intentionally reports only problems that can be established from
the export itself.  It does not treat SpEL expressions outside the supported
parser subset as invalid Watson syntax.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

from watson_dialog_conditions import analyze_conditions, iter_conditions, iter_groups
from watson_dialog_diff import load_json
from watson_spel import syntax_diagnostics


SCHEMA_VERSION = 1
MAX_CONDITION_LENGTH = 2048


def field_for_condition(node: str) -> str:
    return "condicao" if not node.startswith("slot:") else "slots[uuid=%s].condicao" % node.removeprefix("slot:")


def iter_json_configurations(document: dict[str, Any]) -> Iterator[tuple[str, str, Any]]:
    def visit(nodes: list[dict[str, Any]]) -> Iterator[tuple[str, str, Any]]:
        for node in nodes:
            node_id = str(node["uuid"])
            if node.get("json") not in (None, ""):
                yield node_id, "json", node["json"]
            for slot in node.get("slots") or []:
                slot_id = f"slot:{slot['uuid']}"
                if slot.get("json") not in (None, ""):
                    yield slot_id, "json", slot["json"]
                yield from visit(slot.get("filhos") or [])
            yield from visit(node.get("filhos") or [])

    yield from visit(document.get("nos") or [])


def iter_nodes(document: dict[str, Any]) -> Iterator[dict[str, Any]]:
    def visit(nodes: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        for node_data in nodes:
            yield node_data
            for slot in node_data.get("slots") or []:
                yield from visit(slot.get("filhos") or [])
            yield from visit(node_data.get("filhos") or [])

    yield from visit(document.get("nos") or [])


def context_variables(document: dict[str, Any]) -> dict[str, str]:
    """Map context variable UUIDs to names, ignoring malformed definitions."""
    return {
        str(item["uuid"]): str(item["variavelContexto"]).lstrip("$")
        for item in document.get("variaveisContexto") or []
        if item.get("uuid") and item.get("variavelContexto")
    }


def issue(category: str, code: str, severity: str, node: str, field: str, value: Any, message: str) -> dict[str, Any]:
    return {
        "category": category,
        "code": code,
        "severity": severity,
        "node": node,
        "field": field,
        "value": value,
        "message": message,
    }


def validate(document: dict[str, Any], check_variables: bool = False) -> dict[str, Any]:
    """Return deterministic validation issues for the complete dialog export."""
    issues: list[dict[str, Any]] = []

    condition_categories = {
        "invalid_spel_entity_shorthand_member": "syntactic",
        "invalid_spel_entity_call": "syntactic",
    }
    for finding in analyze_conditions(document, check_variables=check_variables)["issues"]:
        issues.append(issue(
            condition_categories.get(finding["type"], "semantic"),
            finding["type"],
            finding["severity"],
            finding["node"],
            field_for_condition(finding["node"]),
            finding["condition"],
            finding["message"],
        ))

    for node, _kind, condition in iter_conditions(document):
        if len(condition) > MAX_CONDITION_LENGTH:
            issues.append(issue("syntactic", "condition_too_long", "error", node, field_for_condition(node), condition, f"A condição possui {len(condition)} caracteres; o limite do Watson é {MAX_CONDITION_LENGTH}."))
        for diagnostic in syntax_diagnostics(condition):
            issues.append(issue(
                diagnostic["category"],
                diagnostic["code"],
                "error",
                node,
                field_for_condition(node),
                condition,
                diagnostic["message"],
            ))

    variable_names = set(context_variables(document).values())
    for node, _kind, condition in iter_conditions(document):
        for variable in sorted(name for name in variable_names if "-" in name):
            if re.search(rf"\${re.escape(variable)}(?![\w-])", condition):
                issues.append(issue("semantic", "ambiguous_context_variable_name", "warning", node, field_for_condition(node), condition, f"A variável ${variable} contém hífen; use $({variable}) ou context['{variable}']."))

    for node, _kind, condition in iter_conditions(document):
        if re.search(r"@[\w-]+:\([^)]*\([^)]*\)", condition):
            issues.append(issue("syntactic", "entity_shorthand_value_contains_closing_parenthesis", "error", node, field_for_condition(node), condition, "O shorthand @entidade:(valor) não pode ser usado quando o valor contém )."))

    for node, field, value in iter_json_configurations(document):
        if not isinstance(value, str):
            issues.append(issue("syntactic", "json_configuration_not_string", "error", node, field, value, "A configuração JSON deve ser uma string JSON."))
            continue
        try:
            json.loads(value)
        except json.JSONDecodeError as error:
            issues.append(issue("syntactic", "invalid_json_configuration", "error", node, field, value, f"Configuração JSON inválida: {error.msg}."))

    for parent, siblings in iter_groups(document.get("nos") or []):
        seen_sequences: dict[Any, list[str]] = defaultdict(list)
        for index, node_data in enumerate(siblings):
            node_id = str(node_data["uuid"])
            sequence = node_data.get("sequencia")
            if sequence is not None:
                seen_sequences[sequence].append(node_id)
            if str(node_data.get("condicao") or "").strip().lower() == "anything_else" and index != len(siblings) - 1:
                issues.append(issue("semantic", "anything_else_not_last_sibling", "warning", node_id, "condicao", node_data.get("condicao"), f"anything_else deve ser o último irmão do grupo {parent}."))
        for sequence, node_ids in seen_sequences.items():
            if len(node_ids) > 1:
                for node_id in sorted(node_ids):
                    issues.append(issue("semantic", "duplicate_sibling_sequence", "warning", node_id, "sequencia", sequence, f"A sequência {sequence!r} é compartilhada pelos irmãos: {', '.join(sorted(node_ids))}."))

    roots = sorted(document.get("nos") or [], key=lambda node_data: (node_data.get("sequencia") is None, node_data.get("sequencia", 0), str(node_data["uuid"])))
    if not any(str(node_data.get("condicao") or "").strip().lower() == "anything_else" for node_data in roots):
        issues.append(issue("semantic", "missing_root_anything_else", "warning", "root", "nos", None, "Não há um nó raiz com a condição anything_else."))

    variable_by_uuid = context_variables(document)
    for frame in iter_nodes(document):
        slots = frame.get("slots") or []
        names = [variable_by_uuid.get(str(slot.get("uuidVariavelContexto"))) for slot in slots]
        for index, slot in enumerate(slots):
            condition = str(slot.get("condicao") or "")
            slot_id = f"slot:{slot['uuid']}"
            if "@sys-number" in condition and "@sys-number >= 0" not in condition:
                issues.append(issue("semantic", "sys_number_zero_not_accepted", "warning", slot_id, "condicao", condition, "@sys-number sem comparação >= 0 não reconhece o valor zero."))
            for later_name in sorted(name for name in names[index + 1:] if name and f"${name}" in condition):
                issues.append(issue("semantic", "slot_depends_on_later_slot", "warning", slot_id, "condicao", condition, f"A condição depende de ${later_name}, preenchida por um slot posterior."))
            for prior_index, prior_name in enumerate(names[:index]):
                if prior_name and f"${prior_name}" in condition and not slots[prior_index].get("indicadorObrigatorio"):
                    issues.append(issue("semantic", "slot_depends_on_optional_slot", "warning", slot_id, "condicao", condition, f"A condição depende de ${prior_name}, preenchida por um slot anterior opcional."))

    node_ids = {str(node_data["uuid"]) for node_data in iter_nodes(document)}
    for node_data in iter_nodes(document):
        target = node_data.get("uuidEnviarPara")
        if target not in (None, "") and str(target) not in node_ids:
            issues.append(issue("semantic", "unresolved_jump_target", "error", str(node_data["uuid"]), "uuidEnviarPara", target, f"O jump aponta para o UUID inexistente {target}."))

    issues.sort(key=lambda item: (item["node"], item["field"], item["code"], json.dumps(item["value"], ensure_ascii=False, sort_keys=True)))
    by_category = {category: sum(item["category"] == category for item in issues) for category in sorted({item["category"] for item in issues})}
    by_code = {code: sum(item["code"] == code for item in issues) for code in sorted({item["code"] for item in issues})}
    by_severity = {severity: sum(item["severity"] == severity for item in issues) for severity in sorted({item["severity"] for item in issues})}
    return {
        "schema_version": SCHEMA_VERSION,
        "summary": {"issues": len(issues), "issues_by_category": by_category, "issues_by_code": by_code, "issues_by_severity": by_severity},
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida estrutural e semanticamente um export Watson Assistant Dialog.")
    parser.add_argument("input", type=Path, help="export JSON do Watson Assistant")
    parser.add_argument("--output", type=Path, help="arquivo de saída; padrão: stdout")
    parser.add_argument("--check-variables", action="store_true", help="também valida variáveis fora de variaveisContexto")
    args = parser.parse_args()
    try:
        report = validate(load_json(args.input), check_variables=args.check_variables)
    except (ValueError, KeyError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 1 if report["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
