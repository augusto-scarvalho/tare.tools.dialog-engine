#!/usr/bin/env python3
"""Deterministic, traceable scenario runner for legacy Watson Dialog exports."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from watson_dialog_conditions import sorted_siblings
from watson_dialog_diff import load_json
from watson_spel import UNKNOWN, SpelError, evaluate_condition


SCHEMA_VERSION = 2
ROOT_GROUP = "root"
MAX_IMMEDIATE_JUMPS = 5_000
MAX_NODE_EXECUTIONS_PER_TURN = 50


def scenario_name(scenario: dict[str, Any], path: Path | None = None) -> str:
    return str(scenario.get("name") or (path.stem if path else "scenario"))


def validate_scenario(scenario: dict[str, Any]) -> None:
    for key, expected in (("input", dict), ("context", dict), ("entities", (dict, list)), ("intents", list), ("turns", list), ("cursor", str), ("effects", dict)):
        if key in scenario and not isinstance(scenario[key], expected):
            raise ValueError(f"scenario.{key} deve ser {expected}.")
    if "dialog_stack" in scenario:
        stack = scenario["dialog_stack"]
        if isinstance(stack, str):
            return
        if not isinstance(stack, list) or any(not isinstance(item, dict) or not isinstance(item.get("dialog_node"), str) for item in stack):
            raise ValueError("scenario.dialog_stack deve ser uma string ou uma lista de objetos com dialog_node.")


def condition_result(condition: str, environment: dict[str, Any], fallback: bool) -> str:
    normalized = condition.strip().lower()
    if normalized == "anything_else": return "true" if fallback else "false"
    if normalized == "welcome": return "true" if environment.get("is_first_turn") and not environment.get("input", {}).get("text") else "false"
    if normalized == "conversation_start": return "true" if environment.get("conversation_start", environment.get("is_first_turn")) is True else "false"
    if normalized == "irrelevant": return "true" if environment.get("irrelevant") is True else "false"
    try: value = evaluate_condition(condition, environment)
    except SpelError: return "unknown"
    return "unknown" if value is UNKNOWN else str(value).lower()


def normalize_document(document: dict[str, Any]) -> dict[str, Any]:
    """Convert the flat Dialog API V1 shape into the legacy runner shape.

    The runner remains intentionally read-only. This adapter only preserves the
    execution fields it understands, and leaves the caller's document intact.
    """
    if "nos" in document:
        return document
    raw_nodes = document.get("dialog_nodes")
    if not isinstance(raw_nodes, list):
        raise ValueError("O diálogo precisa conter nos (legado) ou dialog_nodes (API V1).")
    by_id = {str(node["dialog_node"]): node for node in raw_nodes if isinstance(node, dict) and node.get("dialog_node") is not None}
    children: dict[str | None, list[str]] = {}
    for node_id, node in by_id.items():
        parent = node.get("parent")
        children.setdefault(str(parent) if parent not in (None, "") else None, []).append(node_id)

    def ordered(parent: str | None) -> list[str]:
        ids = children.get(parent, [])
        by_previous = {str(by_id[node_id].get("previous_sibling")): node_id for node_id in ids if by_id[node_id].get("previous_sibling") not in (None, "")}
        first = [node_id for node_id in ids if by_id[node_id].get("previous_sibling") in (None, "")]
        result: list[str] = []
        if len(first) == 1:
            current = first[0]
            seen: set[str] = set()
            while current not in seen:
                result.append(current); seen.add(current)
                if current not in by_previous: break
                current = by_previous[current]
        return result if len(result) == len(ids) else sorted(ids)

    def next_fields(node: dict[str, Any]) -> dict[str, Any]:
        next_step = node.get("next_step") or {}
        if not isinstance(next_step, dict): return {}
        behavior = str(next_step.get("behavior") or "")
        target = next_step.get("dialog_node") or next_step.get("target")
        if behavior in {"jump_to", "jump"} and target:
            selector = str(next_step.get("selector") or "condition")
            return {"uuidEnviarPara": str(target), "jumpSelector": {"response": "body", "client": "user_input"}.get(selector, selector)}
        if behavior in {"skip_user_input", "skip"}:
            return {"jumpSelector": "move_on"}
        return {"jumpSelector": "wait_user_input"}

    def handler(node_id: str, sequence: int) -> dict[str, Any]:
        node = by_id[node_id]
        return {
            "uuid": node_id, "uuidSlot": str(node.get("parent") or ""), "sequencia": sequence,
            "nome": node.get("title"), "condicao": node.get("conditions") or "true",
            "event_name": node.get("event_name"), "respostas": [], "filhos": [], **next_fields(node),
        }

    def convert(node_id: str, sequence: int) -> dict[str, Any]:
        node = by_id[node_id]
        node_type = str(node.get("type") or "standard")
        value: dict[str, Any] = {
            "uuid": node_id, "nome": node.get("title"), "sequencia": sequence,
            "condicao": node.get("conditions") or "true", "folder": node_type == "folder",
            "respostas": [], "filhos": [], "slots": [], **next_fields(node),
            "actions": node.get("actions") or [], "webhook": node.get("webhook"),
            "inDigressionIn": str(node.get("digress_in") or "returns") != "not_available",
            "inDigressionOut": str(node.get("digress_out") or "allow_all") != "not_available",
            "inRetornoDigression": str(node.get("digress_in") or "returns") == "returns",
            "inDigressionSlot": str(node.get("digress_out_slots") or "not_allowed") != "not_allowed",
        }
        for child_sequence, child_id in enumerate(ordered(node_id)):
            child = by_id[child_id]
            child_type = str(child.get("type") or "standard")
            if child_type == "response_condition":
                value["respostas"].append({"uuid": child_id, "sequenciaBloco": child_sequence, "sequenciaItem": 0, "condicao": child.get("conditions") or "true", **next_fields(child)})
            elif child_type == "slot":
                slot_handlers = [handler(handler_id, handler_sequence) for handler_sequence, handler_id in enumerate(ordered(child_id)) if str(by_id[handler_id].get("type") or "standard") == "event_handler"]
                metadata = child.get("metadata") or {}
                value["slots"].append({
                    "uuid": child_id, "identificador": child.get("variable") or child_id,
                    "uuidVariavelContexto": child.get("variable"), "indicadorObrigatorio": bool(child.get("required") or metadata.get("required")),
                    "condicao": child.get("conditions") or "true", "respostas": [], "filhos": slot_handlers,
                })
            elif child_type in {"standard", "frame", "folder"}:
                value["filhos"].append(convert(child_id, child_sequence))
        frame_handlers = [handler(handler_id, handler_sequence) for handler_sequence, handler_id in enumerate(ordered(node_id)) if str(by_id[handler_id].get("type") or "standard") == "event_handler"]
        if frame_handlers:
            value["frame_handlers"] = frame_handlers
        return value

    roots = [convert(node_id, sequence) for sequence, node_id in enumerate(ordered(None)) if str(by_id[node_id].get("type") or "standard") in {"standard", "frame", "folder"}]
    variables = [{"uuid": str(node.get("variable")), "variavelContexto": str(node.get("variable"))} for node in by_id.values() if str(node.get("type") or "standard") == "slot" and node.get("variable")]
    return {"nos": roots, "variaveisContexto": variables}


def index_dialog(document: dict[str, Any]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    groups: dict[str, list[str]] = {}
    group_of: dict[str, str] = {}
    children_of: dict[str, str] = {}
    slots: dict[str, dict[str, Any]] = {}
    frame_for_slot: dict[str, str] = {}

    def visit(values: list[dict[str, Any]], group: str) -> None:
        ordered = sorted_siblings(values)
        groups[group] = [str(node["uuid"]) for node in ordered]
        for node in ordered:
            node_id = str(node["uuid"])
            nodes[node_id], group_of[node_id] = node, group
            child_group = f"children:{node_id}"
            children_of[node_id] = child_group
            frame_handlers = sorted_siblings(node.get("frame_handlers") or [])
            groups[f"frame_handlers:{node_id}"] = [str(handler["uuid"]) for handler in frame_handlers]
            for handler in frame_handlers:
                handler_id = str(handler["uuid"])
                nodes[handler_id], group_of[handler_id] = handler, f"frame_handlers:{node_id}"
                children_of[handler_id] = f"children:{handler_id}"
            visit(node.get("filhos") or [], child_group)
            for slot in node.get("slots") or []:
                slot_id = str(slot["uuid"])
                slots[slot_id] = slot
                frame_for_slot[slot_id] = node_id
                visit(slot.get("filhos") or [], f"slot:{slot['uuid']}")

    visit(document.get("nos") or [], ROOT_GROUP)
    variable_by_uuid = {str(item["uuid"]): str(item["variavelContexto"]).lstrip("$") for item in document.get("variaveisContexto") or [] if item.get("uuid") and item.get("variavelContexto")}
    return {"nodes": nodes, "groups": groups, "group_of": group_of, "children_of": children_of, "slots": slots, "frame_for_slot": frame_for_slot, "variable_by_uuid": variable_by_uuid}


def set_cursor(state: dict[str, Any], index: dict[str, Any], cursor: str) -> None:
    if cursor == ROOT_GROUP:
        state["cursor"] = ROOT_GROUP
        return
    if cursor not in index["nodes"]:
        raise ValueError(f"Cursor aponta para UUID inexistente: {cursor}")
    state["cursor"] = cursor


def first_child(index: dict[str, Any], node_id: str) -> str | None:
    children = index["groups"].get(index["children_of"][node_id], [])
    return children[0] if children else None


def stack_node(value: Any) -> str:
    if isinstance(value, list) and value:
        return str(value[-1].get("dialog_node", ROOT_GROUP))
    return str(value or ROOT_GROUP)


def cursor_for_stack(index: dict[str, Any], dialog_stack: str) -> str:
    if dialog_stack == ROOT_GROUP:
        return ROOT_GROUP
    # A stack points at the active node; the next request starts at its child.
    return first_child(index, dialog_stack) or dialog_stack


def select(index: dict[str, Any], cursor: str, environment: dict[str, Any], trace: list[dict[str, Any]]) -> str | None:
    """Evaluate root, or a node and its following logical siblings.

    A Watson folder is not itself a response-producing dialog step. If its
    condition matches, the runtime immediately evaluates its contents; when no
    contained node matches, evaluation continues after the folder.
    """
    if cursor == ROOT_GROUP:
        group, candidates = ROOT_GROUP, index["groups"].get(ROOT_GROUP, [])
    else:
        group = index["group_of"].get(cursor)
        if group is None:
            raise ValueError(f"Cursor aponta para UUID inexistente: {cursor}")
        siblings = index["groups"][group]
        candidates = siblings[siblings.index(cursor):]
    for node_id in candidates:
        node = index["nodes"][node_id]
        condition = str(node.get("condicao") or "")
        result = condition_result(condition, environment, fallback=True)
        event = "folder_condition" if node.get("folder") else "condition"
        trace.append({"event": event, "scope": group, "node": node_id, "name": node.get("nome"), "condition": condition, "result": result})
        if result != "true":
            continue
        if node.get("folder"):
            child = first_child(index, node_id)
            if child and (selected := select(index, child, environment, trace)) is not None:
                return selected
            continue
        return node_id
    return None


def entity_value(condition: str, environment: dict[str, Any]) -> Any:
    match = re.search(r"@([\w-]+)", condition)
    if not match: return environment.get("input", {}).get("text")
    entity, values = match.group(1), environment.get("entities", {})
    if isinstance(values, dict):
        value = values.get(entity, UNKNOWN)
        return value[0] if isinstance(value, list) and value else value
    for value in values:
        if value.get("entity") == entity: return value.get("value", UNKNOWN)
    return UNKNOWN


def run_slot_handlers(handler_ids: list[str], event_name: str, index: dict[str, Any], state: dict[str, Any], environment: dict[str, Any], trace: list[dict[str, Any]], slot_id: str) -> str | None:
    for handler_id in handler_ids:
        handler = index["nodes"][handler_id]
        if handler.get("event_name") != event_name:
            continue
        condition = str(handler.get("condicao") or "true")
        result = condition_result(condition, {**environment, "context": state["context"], "slot_in_focus": True}, fallback=event_name in {"generic", "nomatch"})
        trace.append({"event": "slot_handler_condition", "scope": f"slot:{slot_id}", "node": handler_id, "name": handler.get("nome"), "handler_event": event_name, "condition": condition, "result": result})
        if result == "true":
            trace.append({"event": "slot_handler", "scope": f"slot:{slot_id}", "node": handler_id, "handler_event": event_name, "action": str(handler.get("jumpSelector") or "wait_user_input")})
            record_node_execution(state, handler_id, trace)
            return handler_id
    return None


def fill_slot(frame: dict[str, Any], index: dict[str, Any], state: dict[str, Any], environment: dict[str, Any], trace: list[dict[str, Any]]) -> dict[str, Any]:
    for slot in frame.get("slots") or []:
        slot_id = str(slot["uuid"])
        variable = index["variable_by_uuid"].get(str(slot.get("uuidVariavelContexto")))
        if variable and state["context"].get(variable) not in (None, ""):
            continue
        condition = str(slot.get("condicao") or "")
        handler_ids = index["groups"].get(f"slot:{slot_id}", [])
        v1_handlers = any(index["nodes"][handler_id].get("event_name") for handler_id in handler_ids)
        if v1_handlers:
            all_handler_ids = [*handler_ids, *index["groups"].get(f"frame_handlers:{frame['uuid']}", [])]
            if slot_id not in state["focused_slots"]:
                state["focused_slots"].add(slot_id)
                if handler := run_slot_handlers(all_handler_ids, "focus", index, state, environment, trace, slot_id):
                    return {"filled": False, "handler": handler}
            input_handler = run_slot_handlers(all_handler_ids, "input", index, state, environment, trace, slot_id)
        else:
            all_handler_ids, input_handler = handler_ids, None
        result = condition_result(condition, {**environment, "context": state["context"], "slot_in_focus": True}, fallback=False)
        trace.append({"event": "slot_condition", "scope": f"slot:{slot_id}", "node": f"slot:{slot_id}", "condition": condition, "result": result})
        if result == "true":
            value = entity_value(condition, environment)
            if variable and value is not UNKNOWN: state["context"][variable] = value
            state["filled_slots"].add(slot_id)
            trace.append({"event": "slot_filled", "scope": f"slot:{slot_id}", "node": f"slot:{slot_id}", "context_variable": variable, "value": None if value is UNKNOWN else value})
            if v1_handlers:
                handler = run_slot_handlers(all_handler_ids, "filled", index, state, environment, trace, slot_id)
                generic = run_slot_handlers(all_handler_ids, "generic", index, state, environment, trace, slot_id)
                return {"filled": True, "handler": generic or handler or input_handler}
            return {"filled": True, "handler": None}
        if v1_handlers:
            generic = run_slot_handlers(all_handler_ids, "generic", index, state, environment, trace, slot_id)
            nomatch = None if generic else run_slot_handlers(all_handler_ids, "nomatch", index, state, environment, trace, slot_id)
            return {"filled": False, "handler": generic or nomatch or input_handler}
        for handler_id in handler_ids:
            handler = index["nodes"][handler_id]
            handler_condition = str(handler.get("condicao") or "")
            handler_result = condition_result(handler_condition, {**environment, "context": state["context"], "slot_in_focus": True}, fallback=True)
            trace.append({"event": "slot_handler_condition", "scope": f"slot:{slot_id}", "node": handler_id, "name": handler.get("nome"), "condition": handler_condition, "result": handler_result})
            if handler_result == "true":
                trace.append({"event": "slot_handler", "scope": f"slot:{slot_id}", "node": handler_id, "action": str(handler.get("jumpSelector") or "wait_user_input")})
                record_node_execution(state, handler_id, trace)
                return {"filled": False, "handler": handler_id}
        return {"filled": False, "handler": None}
    return {"filled": False, "handler": None}


def required_slots_filled(frame: dict[str, Any], state: dict[str, Any]) -> bool:
    return all(str(slot["uuid"]) in state["filled_slots"] or not slot.get("indicadorObrigatorio") for slot in frame.get("slots") or [])


def restore_slot_state(frame_id: str, index: dict[str, Any], state: dict[str, Any]) -> None:
    """Rebuild filled-slot state when a request starts with a slot UUID."""
    frame = index["nodes"][frame_id]
    state["active_frame"] = frame_id
    stack_slot = state["dialog_stack"]
    if stack_slot in index["slots"]:
        state["focused_slots"].add(stack_slot)
    for slot in frame.get("slots") or []:
        variable = index["variable_by_uuid"].get(str(slot.get("uuidVariavelContexto")))
        if variable and state["context"].get(variable) not in (None, ""):
            state["filled_slots"].add(str(slot["uuid"]))


def stack_after(state: dict[str, Any], index: dict[str, Any]) -> list[dict[str, Any]]:
    item: dict[str, Any] = {"dialog_node": state["dialog_stack"]}
    if state["active_frame"] and state["dialog_stack"] in index["slots"]:
        item["state"] = "in_progress"
    return [item]


def selected_data(index: dict[str, Any], node_id: str, direct: bool = False) -> dict[str, Any]:
    node = index["nodes"][node_id]
    data = {"node": node_id, "name": node.get("nome"), "condition": node.get("condicao")}
    if direct: data["direct_response"] = True
    return data


def record_node_execution(state: dict[str, Any], node_id: str, trace: list[dict[str, Any]]) -> bool:
    """Record execution and stop the turn when one UUID reaches the loop limit."""
    count = 1 + sum(item.get("event") == "node_execution" and item.get("node") == node_id for item in trace)
    trace.append({"event": "node_execution", "node": node_id, "count": count})
    if count <= MAX_NODE_EXECUTIONS_PER_TURN:
        return True
    trace.append({"event": "error", "code": "node_execution_limit", "node": node_id, "executions": count, "limit": MAX_NODE_EXECUTIONS_PER_TURN})
    return False


def can_digress(index: dict[str, Any], state: dict[str, Any], target: str) -> tuple[bool, str]:
    """Return whether the current branch may enter a matching root target."""
    target_node = index["nodes"][target]
    if not target_node.get("inDigressionIn", True):
        return False, "target_disallows_digression"
    if state["active_frame"]:
        frame = index["nodes"][state["active_frame"]]
        if not frame.get("inDigressionSlot", False):
            return False, "slot_filling_disallows_digression"
    source = index["nodes"].get(state["dialog_stack"])
    if source:
        if not source.get("inDigressionOut", True):
            return False, "source_disallows_digression"
        if source.get("uuidEnviarPara") or str(source.get("jumpSelector") or "") == "move_on":
            return False, "source_forces_transition"
        if any(str(child.get("condicao") or "").strip().lower() in {"true", "anything_else"} for child in source.get("filhos") or []):
            return False, "source_has_forcing_child"
    return True, "allowed"


def begin_digression(index: dict[str, Any], state: dict[str, Any], target: str, trace: list[dict[str, Any]]) -> None:
    returns = bool(index["nodes"][target].get("inRetornoDigression"))
    if returns:
        state["digression_returns"].append({
            "cursor": state["cursor"], "dialog_stack": state["dialog_stack"], "active_frame": state["active_frame"],
            "filled_slots": set(state["filled_slots"]), "focused_slots": set(state["focused_slots"]),
        })
    else:
        # A destination configured not to return abandons every suspended
        # conversation, including an outer digression.
        state["digression_returns"].clear()
    trace.append({"event": "digression", "from": state["dialog_stack"], "target": target, "returns": returns})


def return_from_digression(state: dict[str, Any], trace: list[dict[str, Any]], node: str) -> bool:
    if not state["digression_returns"]:
        return False
    saved = state["digression_returns"].pop()
    state["cursor"] = saved["cursor"]
    state["dialog_stack"] = saved["dialog_stack"]
    state["active_frame"] = saved["active_frame"]
    state["filled_slots"] = saved["filled_slots"]
    state["focused_slots"] = saved["focused_slots"]
    trace.append({"event": "digression_return", "node": node, "to": state["dialog_stack"]})
    return True


def abandon_digression_returns(state: dict[str, Any], trace: list[dict[str, Any]], node: str, target: str) -> None:
    """A jump leaves the digressed branch instead of returning to its caller."""
    count = len(state["digression_returns"])
    if not count:
        return
    state["digression_returns"].clear()
    trace.append({"event": "digression_return_abandoned", "node": node, "target": target, "returns": count})


def response_jump(node: dict[str, Any], environment: dict[str, Any], trace: list[dict[str, Any]]) -> tuple[str, str] | None:
    """Find the first matching conditional-response jump, if represented.

    The current legacy export stores response components in ``respostas`` and
    normally has no transition fields there. Some compatible exports include
    ``condicao``/``conditions``, ``uuidEnviarPara`` and ``jumpSelector`` on a
    conditional response; Watson gives such a jump precedence over the node's
    final-step jump.
    """
    responses = sorted(node.get("respostas") or [], key=lambda value: (value.get("sequenciaBloco") is None, value.get("sequenciaBloco", 0), value.get("sequenciaItem", 0), str(value.get("uuid", ""))))
    for response in responses:
        target = str(response.get("uuidEnviarPara") or response.get("dialog_node") or "")
        if not target:
            continue
        condition = str(response.get("condicao") or response.get("conditions") or "true")
        result = condition_result(condition, environment, fallback=True)
        trace.append({"event": "response_condition", "node": str(node["uuid"]), "response": str(response.get("uuid") or ""), "condition": condition, "result": result})
        if result == "true":
            return target, str(response.get("jumpSelector") or response.get("jump_selector") or "condition")
    return None


def apply_callout_effect(node: dict[str, Any], state: dict[str, Any], environment: dict[str, Any], trace: list[dict[str, Any]]) -> None:
    """Apply a fixture-provided webhook/action result; never call external code."""
    configured = "action" if node.get("actions") or node.get("uuidAcao") else "webhook" if node.get("webhook") or node.get("urlWebhook") else None
    if not configured:
        return
    effects = environment.get("effects") or {}
    entries = effects.get(f"{configured}s", {}) if isinstance(effects, dict) else {}
    effect = entries.get(str(node["uuid"])) if isinstance(entries, dict) else None
    if not isinstance(effect, dict):
        trace.append({"event": "callout", "node": str(node["uuid"]), "kind": configured, "result": "not_provided"})
        return
    context = effect.get("context") or {}
    if not isinstance(context, dict):
        raise ValueError("effects.<tipo>.<node>.context deve ser um objeto.")
    state["context"].update(context)
    if configured == "action" and "result" in effect:
        variable = str(effect.get("result_variable") or "action_result_1").lstrip("$")
        state["context"][variable] = effect["result"]
    trace.append({"event": "callout", "node": str(node["uuid"]), "kind": configured, "result": "applied", "context_keys": sorted(context)})


def apply_transition(index: dict[str, Any], node_id: str, state: dict[str, Any], environment: dict[str, Any], trace: list[dict[str, Any]]) -> str:
    """Apply child and jump transitions; return the selected node for this turn."""
    selected = node_id
    for _ in range(MAX_IMMEDIATE_JUMPS):
        node = index["nodes"][selected]
        if not record_node_execution(state, selected, trace):
            return selected
        apply_callout_effect(node, state, environment, trace)
        conditional_jump = response_jump(node, environment, trace)
        target = conditional_jump[0] if conditional_jump else str(node.get("uuidEnviarPara") or "")
        if target == ROOT_GROUP or target in index["nodes"]:
            abandon_digression_returns(state, trace, selected, target)
        if target == ROOT_GROUP:
            mode = conditional_jump[1] if conditional_jump else str(node.get("jumpSelector") or "condition")
            trace.append({"event": "response_jump" if conditional_jump else "jump", "node": selected, "target": target, "mode": mode})
            # Root additionally restarts the tree. The digression return was
            # already abandoned above, just as it is for any other jump.
            state["active_frame"] = None
            state["filled_slots"] = set()
            state["focused_slots"] = set()
            set_cursor(state, index, ROOT_GROUP)
            state["dialog_stack"] = ROOT_GROUP
            trace.append({"event": "tree_restart", "node": selected, "mode": mode})
            if mode == "condition":
                next_node = select(index, ROOT_GROUP, environment, trace)
                if next_node is not None:
                    selected = next_node
                    continue
            return selected
        if not target or target not in index["nodes"]:
            action = str(node.get("jumpSelector") or "user_input")
            trace.append({"event": "next_action", "node": selected, "action": action})
            if action == "move_on":
                abandon_digression_returns(state, trace, selected, first_child(index, selected) or ROOT_GROUP)
            if node.get("slots"):
                state["active_frame"] = selected
                slot_result = fill_slot(node, index, state, environment, trace)
                if required_slots_filled(node, state):
                    state["active_frame"] = None
                    set_cursor(state, index, first_child(index, selected) or ROOT_GROUP)
                    state["dialog_stack"] = ROOT_GROUP
                    trace.append({"event": "slots_complete", "node": selected})
                else:
                    state["dialog_stack"] = str(next((slot["uuid"] for slot in node.get("slots") or [] if str(slot["uuid"]) not in state["filled_slots"]), selected))
                if slot_result["handler"]:
                    selected = slot_result["handler"]
            elif (child := first_child(index, selected)):
                set_cursor(state, index, child)
                state["dialog_stack"] = selected
                if action == "move_on":
                    next_node = select(index, child, environment, trace)
                    if next_node is not None:
                        selected = next_node
                        continue
            else:
                set_cursor(state, index, ROOT_GROUP)
                if not return_from_digression(state, trace, selected):
                    state["dialog_stack"] = ROOT_GROUP
            return selected
        mode = conditional_jump[1] if conditional_jump else str(node.get("jumpSelector") or "condition")
        trace.append({"event": "response_jump" if conditional_jump else "jump", "node": selected, "target": target, "mode": mode})
        if mode == "body":
            selected = target
            trace.append({"event": "direct_response", "node": target})
            continue
        if mode == "user_input":
            # Wait for the next user message, then evaluate the destination.
            set_cursor(state, index, target)
            state["dialog_stack"] = target
            return selected
        next_node = select(index, target, environment, trace)
        if next_node is None:
            set_cursor(state, index, ROOT_GROUP)
            state["dialog_stack"] = ROOT_GROUP
            return selected
        selected = next_node
    trace.append({"event": "error", "code": "immediate_jump_limit", "node": selected})
    return selected


def run_scenario(document: dict[str, Any], scenario: dict[str, Any], source: str | None = None) -> dict[str, Any]:
    validate_scenario(scenario)
    document = normalize_document(document)
    index = index_dialog(document)
    incoming_stack = stack_node(scenario.get("dialog_stack") or scenario.get("cursor"))
    state = {"context": dict(scenario.get("context") or {}), "cursor": ROOT_GROUP, "dialog_stack": incoming_stack, "active_frame": None, "filled_slots": set(), "focused_slots": set(), "digression_returns": []}
    if incoming_stack in index["frame_for_slot"]:
        restore_slot_state(index["frame_for_slot"][incoming_stack], index, state)
    else:
        set_cursor(state, index, cursor_for_stack(index, incoming_stack))
    turns = scenario.get("turns") or [{key: scenario[key] for key in ("input", "intents", "entities", "context", "conversation_start", "irrelevant", "effects") if key in scenario}]
    results = []
    for number, turn in enumerate(turns, 1):
        validate_scenario(turn)
        dialog_stack_before = stack_node(turn.get("dialog_stack") or turn.get("cursor") or state["dialog_stack"])
        if "dialog_stack" in turn or "cursor" in turn:
            state["dialog_stack"] = dialog_stack_before
            state["active_frame"] = None
            state["filled_slots"] = set()
            state["focused_slots"] = set()
            state["digression_returns"].clear()
            if dialog_stack_before in index["frame_for_slot"]:
                restore_slot_state(index["frame_for_slot"][dialog_stack_before], index, state)
            else:
                set_cursor(state, index, cursor_for_stack(index, dialog_stack_before))
        state["context"].update(turn.get("context") or {})
        environment = {
            "input": turn.get("input", {}), "intents": turn.get("intents", []), "entities": turn.get("entities", {}), "context": state["context"],
            "is_first_turn": number == 1 and dialog_stack_before == ROOT_GROUP, "effects": {**(scenario.get("effects") or {}), **(turn.get("effects") or {})},
        }
        if "conversation_start" in turn:
            environment["conversation_start"] = turn["conversation_start"]
        if "irrelevant" in turn:
            environment["irrelevant"] = turn["irrelevant"]
        trace: list[dict[str, Any]] = []
        if state["active_frame"]:
            frame_id = state["active_frame"]
            frame = index["nodes"][frame_id]
            slot_result = fill_slot(frame, index, state, environment, trace)
            selected = slot_result["handler"] or frame_id
            if required_slots_filled(frame, state):
                state["active_frame"] = None
                set_cursor(state, index, first_child(index, frame_id) or ROOT_GROUP)
                state["dialog_stack"] = ROOT_GROUP
                trace.append({"event": "slots_complete", "node": frame_id})
        else:
            selected = select(index, state["cursor"], environment, trace)
            if selected is None and state["cursor"] != ROOT_GROUP:
                root_target = select(index, ROOT_GROUP, environment, trace)
                if root_target and str(index["nodes"][root_target].get("condicao") or "").strip().lower() != "anything_else":
                    allowed, reason = can_digress(index, state, root_target)
                    if allowed:
                        begin_digression(index, state, root_target, trace)
                        selected = root_target
                    else:
                        trace.append({"event": "digression_blocked", "from": state["dialog_stack"], "target": root_target, "reason": reason})
                else:
                    selected = root_target
            if selected: selected = apply_transition(index, selected, state, environment, trace)
        results.append({"turn": number, "input": environment["input"], "dialog_stack_before": [{"dialog_node": dialog_stack_before}], "selected": selected_data(index, selected) if selected else None, "dialog_stack_after": stack_after(state, index), "branch_exited": state["dialog_stack"] == ROOT_GROUP, "trace": trace, "context": dict(sorted(state["context"].items()))})
    expected = scenario.get("expect") or {}
    actual_nodes = [item["selected"]["node"] if item["selected"] else None for item in results]
    expected_nodes = expected.get("selected_nodes") or ([expected["selected_node"]] if "selected_node" in expected else None)
    passed = expected_nodes is None or expected_nodes == actual_nodes
    return {"name": scenario_name(scenario, Path(source) if source else None), "source": source, "turns": results, "selected": results[-1]["selected"] if results else None, "passed": passed, **({"expect": expected} if expected else {})}


def run_scenarios(document: dict[str, Any], scenarios: list[tuple[dict[str, Any], str | None]]) -> dict[str, Any]:
    results = [run_scenario(document, scenario, source) for scenario, source in scenarios]
    results.sort(key=lambda item: (item["name"], item["source"] or ""))
    return {"schema_version": SCHEMA_VERSION, "summary": {"scenarios": len(results), "passed": sum(item["passed"] for item in results), "failed": sum(not item["passed"] for item in results)}, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa sessões determinísticas de teste de um Dialog Watson.")
    parser.add_argument("dialog", type=Path); parser.add_argument("scenarios", type=Path, nargs="+"); parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try: report = run_scenarios(load_json(args.dialog), [(load_json(path), str(path)) for path in args.scenarios])
    except (ValueError, KeyError) as error: print(f"Erro: {error}", file=sys.stderr); return 2
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output: args.output.write_text(output, encoding="utf-8")
    else: print(output, end="")
    return 0 if not report["summary"]["failed"] else 1


if __name__ == "__main__": raise SystemExit(main())
