#!/usr/bin/env python3
"""Validate a Watson Assistant Dialog export using one stable issue contract.

The validator intentionally reports only problems that can be established from
the export itself.  It does not treat SpEL expressions outside the supported
parser subset as invalid Watson syntax.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on sys.path when invoked directly
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)


import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

from tare_dialog.conditions import analyze_conditions, iter_conditions
from tare_dialog.diff_engine import DEFAULT_MAX_INPUT_BYTES, configure_utf8_output, load_json
from tare_dialog.spel import syntax_diagnostics, template_syntax_diagnostics


SCHEMA_VERSION = 1
MAX_CONDITION_LENGTH = 2048
V1_NODE_TYPES = {"standard", "event_handler", "frame", "slot", "response_condition", "folder"}
V1_SLOT_EVENTS = {"focus", "input", "filled", "nomatch"}
SYS_NUMBER_ZERO_HANDLER_PATTERN = re.compile(r"@sys-number\s*(?:\.numeric_value\s*)?(?:==\s*0\b|<=\s*0\b|<\s*1\b)", re.IGNORECASE)
SYS_NUMBER_ZERO_SHORTHAND_PATTERN = re.compile(r"@sys-number\s*:\s*0\b", re.IGNORECASE)
ZERO_IN_PROMPT_RANGE_PATTERN = re.compile(r"(?:^|\D)0\s*(?:a|até|ate|[-–—])\s*[1-9]\d*\b", re.IGNORECASE)
DOCUMENT_INPUT_PATTERN = re.compile(r"\$inputType\s*:\s*document\b", re.IGNORECASE)
SELF_FALSE_ENABLE_PATTERNS = (
    re.compile(r"\$([A-Za-z_][\w-]*)\s*&&\s*\$\1\s*==\s*false\b", re.IGNORECASE),
    re.compile(r"\$([A-Za-z_][\w-]*)\s*==\s*false\s*&&\s*\$\1\b", re.IGNORECASE),
)


def field_for_condition(node: str) -> str:
    if node.startswith("response:"):
        _prefix, parent, response = node.split(":", 2)
        return f"nos[uuid={parent}].respostas[uuid={response}].condicao"
    return "condicao" if not node.startswith("slot:") else "slots[uuid=%s].condicao" % node.removeprefix("slot:")


def iter_json_configurations(document: dict[str, Any]) -> Iterator[tuple[str, str, Any]]:
    def visit(nodes: list[dict[str, Any]]) -> Iterator[tuple[str, str, Any]]:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("uuid") or "(sem_uuid)")
            if node.get("json") not in (None, ""):
                yield node_id, "json", node["json"]
            for slot in node.get("slots") or []:
                if not isinstance(slot, dict):
                    continue
                slot_id = f"slot:{slot.get('uuid') or '(sem_uuid)'}"
                if slot.get("json") not in (None, ""):
                    yield slot_id, "json", slot["json"]
                yield from visit(slot.get("filhos") or [])
            yield from visit(node.get("filhos") or [])

    yield from visit(document.get("nos") or [])


def _context_child_path(parent: str, key: Any) -> str:
    """Return a deterministic, unambiguous path for nested context values."""
    return f"{parent}[{json.dumps(str(key), ensure_ascii=False)}]"


def iter_context_strings(value: Any, path: str) -> Iterator[tuple[str, str]]:
    """Yield every string nested inside a context value with its JSON-like path."""
    if isinstance(value, str):
        yield path, value
        return
    if isinstance(value, dict):
        for key in sorted(value, key=lambda item: str(item)):
            yield from iter_context_strings(value[key], _context_child_path(path, key))
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_context_strings(item, f"{path}[{index}]")


def iter_dialog_contexts(document: dict[str, Any]) -> Iterator[tuple[str, str, Any]]:
    """Yield context payloads from API V1 nodes and normalized legacy JSON.

    The side project's normalized legacy export stores the original Watson node
    JSON as a string in ``node.json`` / ``slot.json``.  Production data uses
    that field for the IBM ``context`` object, while native API V1 exports keep
    the context directly on ``dialog_nodes[]``.
    """
    raw_v1_nodes = document.get("dialog_nodes")
    if isinstance(raw_v1_nodes, list):
        for node_data in raw_v1_nodes:
            if not isinstance(node_data, dict) or node_data.get("dialog_node") in (None, ""):
                continue
            if "context" in node_data:
                yield str(node_data["dialog_node"]), "context", node_data["context"]

    def visit(nodes: list[dict[str, Any]]) -> Iterator[tuple[str, str, Any]]:
        for node_data in nodes:
            if not isinstance(node_data, dict):
                continue
            node_id = str(node_data.get("uuid") or "(sem_uuid)")
            raw_json = node_data.get("json")
            if isinstance(raw_json, str) and raw_json:
                try:
                    configuration = json.loads(raw_json)
                except json.JSONDecodeError:
                    configuration = None
                if isinstance(configuration, dict) and "context" in configuration:
                    yield node_id, "json.context", configuration["context"]
            for slot in node_data.get("slots") or []:
                if not isinstance(slot, dict):
                    continue
                slot_id = f"slot:{slot.get('uuid') or '(sem_uuid)'}"
                raw_slot_json = slot.get("json")
                if isinstance(raw_slot_json, str) and raw_slot_json:
                    try:
                        configuration = json.loads(raw_slot_json)
                    except json.JSONDecodeError:
                        configuration = None
                    if isinstance(configuration, dict) and "context" in configuration:
                        yield slot_id, "json.context", configuration["context"]
                yield from visit(slot.get("filhos") or [])
            yield from visit(node_data.get("filhos") or [])

    yield from visit(document.get("nos") or [])


def context_spel_issues(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Return conservative syntax findings for SpEL embedded in node context."""
    findings: list[dict[str, Any]] = []
    for node, context_field, context_value in iter_dialog_contexts(document):
        if not isinstance(context_value, dict):
            findings.append(issue(
                "syntactic",
                "dialog_context_not_object",
                "error",
                node,
                context_field,
                context_value,
                "O context de um dialog node deve ser um objeto JSON.",
            ))
            continue
        for field, value in iter_context_strings(context_value, context_field):
            if "<?" not in value:
                continue
            for diagnostic in template_syntax_diagnostics(value):
                findings.append(issue(
                    diagnostic["category"],
                    f"context_spel_{diagnostic['code']}",
                    "error",
                    node,
                    field,
                    diagnostic["expression"],
                    diagnostic["message"],
                ))
    return findings


def iter_nodes(document: dict[str, Any]) -> Iterator[dict[str, Any]]:
    def visit(nodes: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        for node_data in nodes:
            if not isinstance(node_data, dict):
                continue
            yield node_data
            for slot in node_data.get("slots") or []:
                if isinstance(slot, dict):
                    yield from visit(slot.get("filhos") or [])
            yield from visit(node_data.get("filhos") or [])

    yield from visit(document.get("nos") or [])


def iter_legacy_groups_in_source_order(nodes: list[dict[str, Any]], parent: str = "root") -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """Yield legacy sibling groups without inventing an order for sequence ties."""
    yield parent, nodes
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("uuid") or "(sem_uuid)")
        children = node.get("filhos") or []
        if children:
            yield from iter_legacy_groups_in_source_order(children, node_id)
        for slot in node.get("slots") or []:
            if not isinstance(slot, dict):
                continue
            slot_id = f"slot:{slot.get('uuid') or '(sem_uuid)'}"
            slot_children = slot.get("filhos") or []
            yield slot_id, slot_children
            for child in slot_children:
                if not isinstance(child, dict):
                    continue
                nested = child.get("filhos") or []
                if nested:
                    yield from iter_legacy_groups_in_source_order(nested, str(child.get("uuid") or "(sem_uuid)"))


def iter_nodes_with_activity(document: dict[str, Any], condition_dormant: set[str] | None = None) -> Iterator[tuple[dict[str, Any], bool]]:
    """Yield legacy nodes plus whether their source path is dormant.

    `condition_dormant` comes from the already-computed condition analysis so
    digression checks can honor explicit-false/unsatisfiable ancestors without
    parsing every condition a second time.
    """
    condition_dormant = condition_dormant or set()

    def visit(nodes: list[dict[str, Any]], ancestor_dormant: bool = False) -> Iterator[tuple[dict[str, Any], bool]]:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("uuid") or "(sem_uuid)")
            dormant = (
                ancestor_dormant
                or node_id in condition_dormant
                or str(node.get("status") or "").strip().upper() in {"INATIVO", "REVISAO"}
            )
            yield node, dormant
            for slot in node.get("slots") or []:
                if isinstance(slot, dict):
                    yield from visit(slot.get("filhos") or [], dormant)
            yield from visit(node.get("filhos") or [], dormant)

    yield from visit(document.get("nos") or [])


def is_non_operational_status(node: dict[str, Any]) -> bool:
    """Project-local status evidence used only to qualify active-flow claims."""
    return str(node.get("status") or "").strip().upper() in {"INATIVO", "REVISAO"}


def iter_response_owners(document: dict[str, Any]) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    def visit(nodes: list[dict[str, Any]]) -> Iterator[tuple[str, list[dict[str, Any]]]]:
        for node_data in nodes:
            if not isinstance(node_data, dict):
                continue
            yield str(node_data.get("uuid") or "(sem_uuid)"), node_data.get("respostas") or []
            for slot in node_data.get("slots") or []:
                if isinstance(slot, dict):
                    yield f"slot:{slot.get('uuid') or '(sem_uuid)'}", slot.get("respostas") or []
                    yield from visit(slot.get("filhos") or [])
            yield from visit(node_data.get("filhos") or [])

    yield from visit(document.get("nos") or [])


def validate_v1_structure(document: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    """Validate the documented graph constraints when an API V1 payload is used."""
    raw_nodes = document.get("dialog_nodes")
    if not isinstance(raw_nodes, list):
        return
    nodes = [item for item in raw_nodes if isinstance(item, dict) and item.get("dialog_node") is not None]
    by_id: dict[str, dict[str, Any]] = {}
    for node_data in nodes:
        node_id = str(node_data["dialog_node"])
        if node_id in by_id:
            issues.append(issue("semantic", "duplicate_dialog_node_id", "error", node_id, "dialog_node", node_id, f"O ID {node_id} é duplicado na API V1."))
        else:
            by_id[node_id] = node_data

    parents = {node_id: str(node_data["parent"]) for node_id, node_data in by_id.items() if node_data.get("parent") not in (None, "")}
    children: dict[str | None, list[str]] = defaultdict(list)
    for node_id, node_data in by_id.items():
        parent = node_data.get("parent")
        parent_id = str(parent) if parent not in (None, "") else None
        children[parent_id].append(node_id)
        if parent_id and parent_id not in by_id:
            issues.append(issue("semantic", "unresolved_parent", "error", node_id, "parent", parent, f"O parent {parent_id} não existe."))
        if parent_id == node_id:
            issues.append(issue("semantic", "self_parent", "error", node_id, "parent", parent, "Um nó não pode ser pai de si mesmo."))
        ancestor = parent_id
        seen: set[str] = set()
        while ancestor in parents and ancestor not in seen:
            if ancestor == node_id:
                issues.append(issue("semantic", "parent_is_descendant", "error", node_id, "parent", parent, "O parent não pode ser descendente do nó."))
                break
            seen.add(ancestor)
            ancestor = parents[ancestor]

    previous_owners: dict[str, list[str]] = defaultdict(list)
    for node_id, node_data in by_id.items():
        node_type = str(node_data.get("type") or "standard")
        if node_type not in V1_NODE_TYPES:
            issues.append(issue("syntactic", "unknown_dialog_node_type", "error", node_id, "type", node_type, f"Tipo de nó V1 não suportado: {node_type}."))
        previous = node_data.get("previous_sibling")
        if previous not in (None, ""):
            previous_id = str(previous)
            previous_owners[previous_id].append(node_id)
            if previous_id not in by_id:
                issues.append(issue("semantic", "unresolved_previous_sibling", "error", node_id, "previous_sibling", previous, f"O irmão anterior {previous_id} não existe."))
            elif previous_id == node_id:
                issues.append(issue("semantic", "self_previous_sibling", "error", node_id, "previous_sibling", previous, "Um nó não pode ser irmão anterior de si mesmo."))
            elif by_id[previous_id].get("parent") != node_data.get("parent"):
                issues.append(issue("semantic", "cross_parent_previous_sibling", "error", node_id, "previous_sibling", previous, "O irmão anterior precisa ter o mesmo parent."))
        if node_type == "slot" and str(node_data.get("parent") or "") in by_id and str(by_id[str(node_data["parent"])].get("type") or "standard") != "frame":
            issues.append(issue("semantic", "slot_parent_not_frame", "error", node_id, "parent", node_data.get("parent"), "Um slot precisa ser filho de um frame."))
        if node_type == "response_condition" and str(node_data.get("parent") or "") in by_id and str(by_id[str(node_data["parent"])].get("type") or "standard") not in {"standard", "frame"}:
            issues.append(issue("semantic", "response_condition_parent_invalid", "error", node_id, "parent", node_data.get("parent"), "Uma response_condition precisa ser filha de standard ou frame."))
        if node_type in {"event_handler", "response_condition"} and children.get(node_id):
            issues.append(issue("semantic", "leaf_node_has_children", "error", node_id, "parent", children[node_id], f"Um nó {node_type} não pode ter filhos."))
        if node_type == "event_handler":
            event = str(node_data.get("event_name") or "")
            parent_type = str(by_id.get(str(node_data.get("parent") or ""), {}).get("type") or "standard")
            if event not in V1_SLOT_EVENTS | {"generic"}:
                issues.append(issue("syntactic", "invalid_event_handler_name", "error", node_id, "event_name", node_data.get("event_name"), "event_name não é permitido para event_handler."))
            elif event == "generic" and parent_type not in {"slot", "frame"}:
                issues.append(issue("semantic", "generic_handler_parent_invalid", "error", node_id, "parent", node_data.get("parent"), "Handler generic precisa pertencer a slot ou frame."))
            elif event in V1_SLOT_EVENTS and parent_type != "slot":
                issues.append(issue("semantic", "slot_handler_parent_invalid", "error", node_id, "parent", node_data.get("parent"), f"Handler {event} precisa pertencer a slot."))

    for previous, owners in previous_owners.items():
        if len(owners) > 1:
            for node_id in sorted(owners):
                issues.append(issue("semantic", "previous_sibling_has_multiple_successors", "error", node_id, "previous_sibling", previous, f"Mais de um nó aponta para o irmão anterior {previous}."))
    for parent, sibling_ids in children.items():
        first = [node_id for node_id in sibling_ids if by_id[node_id].get("previous_sibling") in (None, "")]
        if len(first) > 1:
            for node_id in sorted(first):
                issues.append(issue("semantic", "multiple_first_siblings", "error", node_id, "previous_sibling", None, f"O grupo de irmãos de {parent or 'root'} tem mais de um primeiro nó."))
    for node_id, node_data in by_id.items():
        if str(node_data.get("type") or "standard") == "frame" and not any(str(by_id[child].get("type") or "standard") == "slot" for child in children.get(node_id, [])):
            issues.append(issue("semantic", "frame_without_slot", "error", node_id, "type", "frame", "Um frame precisa ter pelo menos um filho slot."))


def context_variables(document: dict[str, Any]) -> dict[str, str]:
    """Map context variable UUIDs to names, ignoring malformed definitions."""
    return {
        str(item["uuid"]): str(item["variavelContexto"]).lstrip("$")
        for item in document.get("variaveisContexto") or []
        if item.get("uuid") and item.get("variavelContexto")
    }


def descendant_conditions(nodes: list[dict[str, Any]]) -> Iterator[str]:
    """Yield descendant node conditions without assigning runtime semantics."""
    for node in nodes:
        condition = node.get("condicao")
        if condition not in (None, ""):
            yield str(condition)
        yield from descendant_conditions(node.get("filhos") or [])


def response_text(slot: dict[str, Any]) -> str:
    """Return response text only for local semantic diagnostics."""
    return " ".join(
        str(response.get("textoResposta") or "")
        for response in slot.get("respostas") or []
        if response.get("textoResposta") not in (None, "")
    )


def slot_enable_is_self_false_contradiction(condition: str) -> bool:
    """Detect the audited `$x && $x == false` contradiction conservatively."""
    normalized = re.sub(r"\s+", " ", condition.strip())
    return any(pattern.search(normalized) for pattern in SELF_FALSE_ENABLE_PATTERNS)


def slot_number_diagnostics(slot: dict[str, Any], slot_id: str) -> list[dict[str, Any]]:
    """Return high-confidence number-capture diagnostics for one active slot.

    This intentionally does *not* warn on every bare `@sys-number`.  Positive
    selectors and non-zero domains are common.  We report only contradictions
    established by the slot's own children/prompt.
    """
    condition = str(slot.get("condicao") or "")
    if "@sys-number" not in condition or "@sys-number >= 0" in condition:
        return []

    children = list(descendant_conditions(slot.get("filhos") or []))
    findings: list[dict[str, Any]] = []
    if any(SYS_NUMBER_ZERO_HANDLER_PATTERN.search(child) for child in children):
        findings.append(issue(
            "semantic",
            "sys_number_zero_handler_unreachable",
            "warning",
            slot_id,
            "condicao",
            condition,
            "O slot não captura zero, mas possui handler descendente para == 0, <= 0 ou < 1; esse tratamento de zero não é alcançável pela captura atual.",
        ))

    prompt = response_text(slot)
    if (
        ZERO_IN_PROMPT_RANGE_PATTERN.search(prompt)
        and any(SYS_NUMBER_ZERO_SHORTHAND_PATTERN.search(child) for child in children)
    ):
        findings.append(issue(
            "semantic",
            "sys_number_zero_valid_but_not_captured",
            "warning",
            slot_id,
            "condicao",
            condition,
            "O próprio prompt inclui zero no domínio e existe branch @sys-number:0, mas a condição de captura não aceita zero.",
        ))

    if any(DOCUMENT_INPUT_PATTERN.search(child) for child in children):
        findings.append(issue(
            "semantic",
            "slot_capture_type_mismatch_document",
            "warning",
            slot_id,
            "condicao",
            condition,
            "O slot captura @sys-number, mas sua lógica descendente espera $inputType:document; a condição de captura não corresponde ao tipo de entrada processado.",
        ))
    return findings


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


def validate(document: dict[str, Any], check_variables: bool = False, summary_only: bool = False, max_issues: int | None = None) -> dict[str, Any]:
    """Return deterministic validation issues for the complete dialog export."""
    issues: list[dict[str, Any]] = []

    condition_categories = {
        "invalid_spel_entity_shorthand_member": "syntactic",
        "invalid_spel_entity_call": "syntactic",
    }
    condition_report = analyze_conditions(document, check_variables=check_variables)
    condition_dormant = {
        finding["node"] for finding in condition_report["issues"]
        if finding["type"] in {"disabled_condition_false", "unsatisfiable_condition"}
        and not finding["node"].startswith(("slot:", "response:"))
    }
    for finding in condition_report["issues"]:
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

    variable_names = {
        name for name in context_variables(document).values()
        if re.fullmatch(r"[A-Za-z_][\w-]*", name)
    }
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

    issues.extend(context_spel_issues(document))

    for owner, responses in iter_response_owners(document):
        blocks: dict[tuple[Any, Any], set[Any]] = defaultdict(set)
        for response in responses:
            if response.get("idTipoComponente") is not None:
                blocks[(response.get("idTipoResposta"), response.get("sequenciaBloco"))].add(response["idTipoComponente"])
        for block, component_types in sorted(blocks.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))):
            if len(component_types) > 5:
                issues.append(issue("semantic", "too_many_response_types", "error", owner, "respostas", sorted(component_types, key=str), f"A resposta condicional {block!r} possui {len(component_types)} tipos; o limite do Watson é 5."))

    for parent, siblings in iter_legacy_groups_in_source_order(document.get("nos") or []):
        seen_sequences: dict[Any, list[str]] = defaultdict(list)
        for index, node_data in enumerate(siblings):
            if not isinstance(node_data, dict):
                continue
            if node_data.get("uuid") in (None, ""):
                issues.append(issue("syntactic", "missing_node_uuid", "error", "(sem_uuid)", "uuid", None, "O nó legado não possui o campo uuid obrigatório."))
            node_id = str(node_data.get("uuid") or "(sem_uuid)")
            sequence = node_data.get("sequencia")
            if sequence is not None:
                seen_sequences[sequence].append(node_id)
            # `anything_else` is an ordering rule.  For the normalized legacy
            # export the physical sibling array is the only source ordering we
            # can inspect without inventing a tie-break for duplicate/None
            # sequence values.
            if (
                not is_non_operational_status(node_data)
                and str(node_data.get("condicao") or "").strip().lower() == "anything_else"
                and index != len(siblings) - 1
            ):
                issues.append(issue("semantic", "anything_else_not_last_sibling", "warning", node_id, "condicao", node_data.get("condicao"), f"anything_else deve ser o último irmão do grupo {parent}."))
        for sequence, node_ids in seen_sequences.items():
            if len(node_ids) > 1:
                ordered_ids = sorted(node_ids)
                issues.append(issue(
                    "provenance",
                    "legacy_order_ambiguous",
                    "info",
                    parent,
                    "sequencia",
                    {"sequence": sequence, "nodes": ordered_ids},
                    f"A sequência legacy {sequence!r} é compartilhada por {len(ordered_ids)} irmãos; a ordem relativa não pode ser inferida com segurança.",
                ))

    roots = document.get("nos") or []
    if not any(isinstance(node_data, dict) and str(node_data.get("condicao") or "").strip().lower() == "anything_else" for node_data in roots):
        issues.append(issue("semantic", "missing_root_anything_else", "warning", "root", "nos", None, "Não há um nó raiz com a condição anything_else."))

    variable_by_uuid = context_variables(document)
    for frame, inactive_path in iter_nodes_with_activity(document, condition_dormant):
        slots = frame.get("slots") or []
        names = [variable_by_uuid.get(str(slot.get("uuidVariavelContexto"))) for slot in slots if isinstance(slot, dict)]
        for index, slot in enumerate(slots):
            if not isinstance(slot, dict):
                continue
            if slot.get("uuid") in (None, ""):
                issues.append(issue("syntactic", "missing_slot_uuid", "error", "(sem_uuid)", "uuid", None, "O slot não possui o campo uuid obrigatório."))
            condition = str(slot.get("condicao") or "")
            slot_id = f"slot:{slot.get('uuid') or '(sem_uuid)'}"
            if not inactive_path:
                issues.extend(slot_number_diagnostics(slot, slot_id))
                enable_condition = str(slot.get("condicaoSlots") or "").strip()
                if enable_condition and slot_enable_is_self_false_contradiction(enable_condition):
                    issues.append(issue(
                        "semantic",
                        "unsatisfiable_slot_enable_condition",
                        "warning",
                        slot_id,
                        "condicaoSlots",
                        enable_condition,
                        "A condição exige que a mesma variável seja simultaneamente truthy e igual a false; esse slot não pode ser habilitado por essa expressão.",
                    ))
            current_name = names[index] if index < len(names) else None
            for later_name in sorted(name for name in names[index + 1:] if name and name != current_name and f"${name}" in condition):
                issues.append(issue("semantic", "slot_depends_on_later_slot", "warning", slot_id, "condicao", condition, f"A condição depende de ${later_name}, preenchida por um slot posterior."))
            for prior_index, prior_name in enumerate(names[:index]):
                if prior_name and f"${prior_name}" in condition and prior_index < len(slots) and isinstance(slots[prior_index], dict) and not slots[prior_index].get("indicadorObrigatorio"):
                    issues.append(issue("semantic", "slot_depends_on_optional_slot", "warning", slot_id, "condicao", condition, f"A condição depende de ${prior_name}, preenchida por um slot anterior opcional."))

    node_ids = {str(node_data.get("uuid")) for node_data in iter_nodes(document) if isinstance(node_data, dict) and node_data.get("uuid") not in (None, "")}
    for node_data, inactive_path in iter_nodes_with_activity(document, condition_dormant):
        if not isinstance(node_data, dict):
            continue
        node_id = str(node_data.get("uuid") or "(sem_uuid)")
        target = node_data.get("uuidEnviarPara")
        if target not in (None, "") and str(target) not in node_ids | {"root"}:
            issues.append(issue("semantic", "unresolved_jump_target", "error", node_id, "uuidEnviarPara", target, f"O jump aponta para o UUID inexistente {target}."))
        if inactive_path or not node_data.get("inDigressionOut"):
            continue
        if target not in (None, "") or str(node_data.get("jumpSelector") or "") == "move_on":
            issues.append(issue("semantic", "digression_blocked_by_transition", "info", node_id, "inDigressionOut", node_data.get("inDigressionOut"), "O Watson não permite digressão de saída quando o nó ativo força jump ou Skip user input."))
        active_forcing_children = [
            child for child in node_data.get("filhos") or []
            if isinstance(child, dict)
            and not is_non_operational_status(child)
            and str(child.get("condicao") or "").strip().lower() in {"true", "anything_else"}
        ]
        if active_forcing_children:
            blocker_ids = ", ".join(sorted(str(child.get("uuid") or "(sem_uuid)") for child in active_forcing_children))
            all_escapes = all(
                any(keyword in str(child.get("nome") or "").lower() or keyword in str(child.get("condicao") or "").lower() for keyword in ("escape", "sair", "voltar"))
                for child in active_forcing_children
            )
            severity = "info" if all_escapes else "warning"
            issues.append(issue("semantic", "digression_blocked_by_forcing_child", severity, node_id, "inDigressionOut", node_data.get("inDigressionOut"), f"O Watson não permite digressão de saída com filho ativo true/anything_else; blockers: {blocker_ids}."))
    for owner, responses in iter_response_owners(document):
        for response in responses:
            target = response.get("uuidEnviarPara") or response.get("dialog_node")
            if target not in (None, "") and str(target) not in node_ids | {"root"}:
                issues.append(issue("semantic", "unresolved_response_jump_target", "error", owner, "respostas.uuidEnviarPara", target, f"O jump de resposta aponta para o UUID inexistente {target}."))

    validate_v1_structure(document, issues)

    issues.sort(key=lambda item: (item["node"], item["field"], item["code"], json.dumps(item["value"], ensure_ascii=False, sort_keys=True)))
    by_category = {category: sum(item["category"] == category for item in issues) for category in sorted({item["category"] for item in issues})}
    by_code = {code: sum(item["code"] == code for item in issues) for code in sorted({item["code"] for item in issues})}
    by_severity = {severity: sum(item["severity"] == severity for item in issues) for severity in sorted({item["severity"] for item in issues})}
    
    total_issues = len(issues)
    reported_issues = [] if summary_only else (issues[:max_issues] if max_issues is not None and max_issues >= 0 else issues)

    return {
        "schema_version": SCHEMA_VERSION,
        "summary": {
            "issues": total_issues,
            "issues_by_category": by_category,
            "issues_by_code": by_code,
            "issues_by_severity": by_severity,
        },
        "issues": reported_issues,
    }


def main() -> int:
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Valida estrutural e semanticamente um export Watson Assistant Dialog.")
    parser.add_argument("input", type=Path, help="export JSON do Watson Assistant")
    parser.add_argument("--output", type=Path, help="arquivo de saída; padrão: stdout")
    parser.add_argument("--check-variables", action="store_true", help="também valida variáveis fora de variaveisContexto")
    parser.add_argument("--max-input-bytes", type=int, default=None, help="limite máximo em bytes; padrão: WATSON_DIALOG_MAX_BYTES ou 50 MiB")
    parser.add_argument("--summary-only", action="store_true", help="emite apenas sumário consolidado das contagens de issues")
    parser.add_argument("--max-issues", type=int, default=None, help="limite máximo de issues detalhadas no relatório")
    args = parser.parse_args()
    try:
        report = validate(
            load_json(args.input, max_bytes=args.max_input_bytes),
            check_variables=args.check_variables,
            summary_only=args.summary_only,
            max_issues=args.max_issues,
        )
    except (ValueError, KeyError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 1 if report["summary"]["issues"] else 0


if __name__ == "__main__":
    import sys
    from pathlib import Path
    raise SystemExit(main())