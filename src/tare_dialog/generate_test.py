#!/usr/bin/env python3
"""Generate a deterministic runner scenario for a node's structural path."""
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
from pathlib import Path
from typing import Any

from tare_dialog.diff_engine import DEFAULT_MAX_INPUT_BYTES, configure_utf8_output, load_json
from tare_dialog.test_runner import normalize_document, run_scenario


def index_paths(document: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    paths: dict[str, list[dict[str, Any]]] = {}
    def visit(nodes: list[dict[str, Any]], prefix: list[dict[str, Any]]) -> None:
        for node in nodes:
            path = [*prefix, node]
            paths[str(node["uuid"])] = path
            visit(node.get("filhos") or [], path)
            for slot in node.get("slots") or []:
                visit(slot.get("filhos") or [], path)
    visit(document.get("nos") or [], [])
    return paths


def turn_for(condition: str, context: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    text = "generated"
    intents = [{"name": name, "confidence": 1.0} for name in sorted(set(re.findall(r"#([\w.-]+)", condition)))]
    entities: dict[str, list[str]] = {}
    for match in re.finditer(r"@([\w-]+):(?:\(([^()]*)\)|([\w-]+))", condition):
        entities[match.group(1)] = [match.group(2) or match.group(3)]
    for name in re.findall(r"@([\w-]+)", condition):
        entities.setdefault(name, ["generated"])
    for name, value in re.findall(r"\$([A-Za-z_]\w*)\s*(?:==|:)\s*['\"]?([\w.-]+)", condition):
        context[name] = value
    for name in re.findall(r"\$([A-Za-z_]\w*)\b", condition):
        context.setdefault(name, True)
    match = re.search(r"input\.text(?:\.toLowerCase\(\))?\s*==\s*['\"]([^'\"]+)", condition)
    if match: text = match.group(1)
    match = re.search(r"input\.text\.contains\(['\"]([^'\"]+)", condition)
    if match: text = match.group(1)
    unsupported = re.sub(r"(?:#[\w.-]+|@[\w-]+(?::(?:\([^)]*\)|[\w-]+))?|\$[A-Za-z_]\w*|input\.text(?:\.toLowerCase\(\))?(?:\s*(?:==|!=|>|<|>=|<=)\s*['\"][^'\"]+['\"]|\.contains\(['\"][^'\"]+['\"]\))?|true|false|\s|&&|\|\||\(|\)|!|AND|OR)", "", condition, flags=re.I)
    if unsupported: issues.append(f"Trecho SpEL não sintetizado: {unsupported!r}")
    return {"input": {"text": text}, "intents": intents, "entities": entities, "context": dict(sorted(context.items()))}, issues


def generate(document: dict[str, Any], target: str) -> dict[str, Any]:
    document = normalize_document(document)
    path = index_paths(document).get(target)
    if not path: raise ValueError(f"UUID não encontrado: {target}")
    context: dict[str, Any] = {}
    turns, issues = [], []
    executable_path = [node for node in path if not node.get("folder")]
    for node in executable_path:
        turn, turn_issues = turn_for(str(node.get("condicao") or "true"), context)
        turns.append(turn); issues.extend(turn_issues)
    scenario = {"name": f"path-to-{target}", "turns": turns, "expect": {"selected_nodes": [str(node["uuid"]) for node in executable_path]}, "generated": {"target": target, "path": [str(node["uuid"]) for node in path], "issues": sorted(set(issues))}}
    validation = run_scenario(document, scenario)
    scenario["generated"]["runner_passed"] = validation["passed"]
    scenario["generated"]["actual_selected_nodes"] = [turn["selected"]["node"] if turn["selected"] else None for turn in validation["turns"]]
    return scenario


def slots_by_id(document: dict[str, Any]) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    """Return each slot and its owning dialog node, keyed by slot UUID."""
    found: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}

    def visit(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            for slot in node.get("slots") or []:
                slot_id = str(slot["uuid"])
                if slot_id in found:
                    raise ValueError(f"UUID de slot duplicado: {slot_id}")
                found[slot_id] = (node, slot)
                visit(slot.get("filhos") or [])
            visit(node.get("filhos") or [])

    visit(document.get("nos") or [])
    return found


def generate_slot(document: dict[str, Any], target: str) -> dict[str, Any]:
    """Generate a scenario that reaches and fills one slot in a topology."""
    document = normalize_document(document)
    owner, slot = slots_by_id(document).get(target, (None, None))
    if owner is None or slot is None:
        raise ValueError(f"UUID de slot não encontrado: {target}")
    path = index_paths(document).get(str(owner["uuid"]))
    if not path:
        raise ValueError(f"UUID do nó pai do slot não encontrado: {owner['uuid']}")
    context: dict[str, Any] = {}
    issues: list[str] = []
    executable_path = [node for node in path if not node.get("folder")]
    turns: list[dict[str, Any]] = []
    for node in executable_path:
        turn, turn_issues = turn_for(str(node.get("condicao") or "true"), context)
        turns.append(turn)
        issues.extend(turn_issues)
    owner_slots = owner.get("slots") or []
    target_position = next((position for position, value in enumerate(owner_slots) if str(value["uuid"]) == target), None)
    if target_position is None:
        raise ValueError(f"Slot {target} não pertence ao nó {owner['uuid']}")
    for required_slot in owner_slots[:target_position + 1]:
        slot_turn, slot_issues = turn_for(str(required_slot.get("condicao") or "true"), context)
        turns.append(slot_turn)
        issues.extend(slot_issues)
    expected_nodes = [str(node["uuid"]) for node in executable_path] + [str(owner["uuid"])] * (target_position + 1)
    scenario = {
        "name": f"path-to-slot-{target}",
        "turns": turns,
        "expect": {"selected_nodes": expected_nodes},
        "generated": {"target": target, "kind": "slot", "path": [str(node["uuid"]) for node in path], "prerequisite_slots": [str(value["uuid"]) for value in owner_slots[:target_position]], "issues": sorted(set(issues))},
    }
    validation = run_scenario(document, scenario)
    slot_filled = any(
        event.get("event") == "slot_filled" and event.get("node") == f"slot:{target}"
        for turn in validation["turns"]
        for event in turn["trace"]
    )
    scenario["generated"]["runner_passed"] = validation["passed"] and slot_filled
    scenario["generated"]["actual_selected_nodes"] = [turn["selected"]["node"] if turn["selected"] else None for turn in validation["turns"]]
    scenario["generated"]["slot_filled"] = slot_filled
    return scenario


def topology_nodes_leaves_first(topology: dict[str, Any]) -> list[dict[str, str]]:
    """List all topology items in deterministic post-order, without duplicates."""
    descendants = topology.get("descendants")
    if not isinstance(descendants, dict) or not descendants.get("uuid"):
        raise ValueError("Topologia sem descendants.uuid.")
    ordered: list[dict[str, str]] = []
    seen: set[str] = set()

    def visit(item: dict[str, Any]) -> None:
        for child in item.get("children") or []:
            visit(child)
        for slot in item.get("slots") or []:
            visit(slot)
        for handler in item.get("handlers") or []:
            visit(handler)
        node_id = str(item["uuid"])
        if node_id not in seen:
            seen.add(node_id)
            ordered.append({"uuid": node_id, "kind": str(item.get("kind") or "dialog_node")})

    visit(descendants)
    for ancestor in reversed(topology.get("ancestors") or []):
        node_id = str(ancestor.get("uuid") or "")
        if node_id and node_id not in seen:
            seen.add(node_id)
            ordered.append({"uuid": node_id, "kind": str(ancestor.get("kind") or "dialog_node")})
    return ordered


def generate_topology(document: dict[str, Any], topology: dict[str, Any]) -> dict[str, Any]:
    """Generate one runner scenario per topology item, starting at the leaves."""
    document = normalize_document(document)
    cases = []
    for position, item in enumerate(topology_nodes_leaves_first(topology), 1):
        scenario = generate_slot(document, item["uuid"]) if item["kind"] == "slot" else generate(document, item["uuid"])
        scenario["generated"]["topology_position"] = position
        scenario["generated"]["topology_kind"] = item["kind"]
        cases.append(scenario)
    return {
        "schema_version": 1,
        "topology_target": str(topology.get("target") or topology["descendants"]["uuid"]),
        "order": "leaves_to_root",
        "summary": {"scenarios": len(cases), "runner_passed": sum(bool(case["generated"]["runner_passed"]) for case in cases), "runner_failed": sum(not case["generated"]["runner_passed"] for case in cases)},
        "scenarios": cases,
    }


def main() -> int:
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Gera cenário de teste até um nó Watson Dialog.")
    parser.add_argument("dialog", type=Path)
    parser.add_argument("node", nargs="?")
    parser.add_argument("--topology", type=Path, help="JSON produzido por watson_dialog_topology.py")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-input-bytes", type=int, default=None, help="limite máximo em bytes; padrão: WATSON_DIALOG_MAX_BYTES ou 50 MiB")
    args = parser.parse_args()
    if bool(args.node) == bool(args.topology):
        parser.error("Informe exatamente NODE ou --topology TOPOLOGY.json.")
    try:
        scenario = generate_topology(load_json(args.dialog, max_bytes=args.max_input_bytes), load_json(args.topology, max_bytes=args.max_input_bytes)) if args.topology else generate(load_json(args.dialog, max_bytes=args.max_input_bytes), args.node)
    except (ValueError, KeyError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    output = json.dumps(scenario, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    if args.topology:
        return 0 if scenario["summary"]["runner_failed"] == 0 else 1
    return 0 if scenario["generated"]["runner_passed"] else 1


if __name__ == "__main__":
    import sys
    from pathlib import Path
    raise SystemExit(main())