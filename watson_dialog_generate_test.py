#!/usr/bin/env python3
"""Generate a deterministic runner scenario for a node's structural path."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from watson_dialog_diff import load_json
from watson_dialog_test import normalize_document, run_scenario


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera cenário de teste até um nó Watson Dialog.")
    parser.add_argument("dialog", type=Path); parser.add_argument("node"); parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try: scenario = generate(load_json(args.dialog), args.node)
    except (ValueError, KeyError) as error: print(f"Erro: {error}", file=sys.stderr); return 2
    output = json.dumps(scenario, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output: args.output.write_text(output, encoding="utf-8")
    else: print(output, end="")
    return 0 if scenario["generated"]["runner_passed"] else 1


if __name__ == "__main__": raise SystemExit(main())
