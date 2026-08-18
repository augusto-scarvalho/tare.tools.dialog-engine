#!/usr/bin/env python3
"""Generate deterministic candidate scenarios from a Watson Dialog diff."""

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
from typing import Any

from tare_dialog.diff_engine import (
    DEFAULT_IGNORED_FIELDS,
    configure_utf8_output,
    load_json,
    summarize,
)
from tare_dialog.generate_test import generate, generate_slot, index_paths, slots_by_id
from tare_dialog.test_runner import normalize_document

UUID_IN_PATH = re.compile(r"\[uuid=([^\]]+)\]")


def candidate_items(document: dict[str, Any]) -> dict[str, str]:
    """Map executable candidate UUIDs to their topology kind."""
    document = normalize_document(document)
    items = {node_id: "dialog_node" for node_id in index_paths(document)}
    items.update({slot_id: "slot" for slot_id in slots_by_id(document)})
    return items


def target_for_change(change: dict[str, Any], items: dict[str, str]) -> str | None:
    """Pick the deepest candidate topology item mentioned by one diff record."""
    path_targets = UUID_IN_PATH.findall(str(change.get("path") or ""))
    for node_id in reversed(path_targets):
        if node_id in items:
            return node_id
    fallback = str(change.get("uuid") or "")
    return fallback if fallback in items else None


def change_reference(change: dict[str, Any]) -> dict[str, Any]:
    """Keep the identifying diff data next to the generated scenario."""
    return {
        "collection": change["collection"],
        "uuid": change["uuid"],
        "path": change["path"],
        "kind": change["kind"],
    }


def generate_from_diff(current: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Generate one candidate scenario for every dialog node impacted by a diff."""
    report = summarize(current, candidate, set(DEFAULT_IGNORED_FIELDS))
    normalized_candidate = normalize_document(candidate)
    items = candidate_items(normalized_candidate)
    changes_by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    uncovered: list[dict[str, Any]] = []

    for change in report["changes"]:
        if change["collection"] != "nos":
            uncovered.append({"reason": "non_dialog_change", "change": change_reference(change)})
            continue
        target = target_for_change(change, items)
        if target is None:
            uncovered.append({"reason": "missing_from_candidate", "change": change_reference(change)})
            continue
        changes_by_target[target].append(change_reference(change))

    scenarios = []
    for target in sorted(changes_by_target):
        kind = items[target]
        scenario = generate_slot(normalized_candidate, target) if kind == "slot" else generate(normalized_candidate, target)
        scenario["generated"]["diff_changes"] = sorted(changes_by_target[target], key=lambda change: (change["collection"], str(change["uuid"]), change["path"], change["kind"]))
        scenario["generated"]["candidate_kind"] = kind
        scenarios.append(scenario)

    return {
        "schema_version": 1,
        "source": "current_to_candidate",
        "diff_summary": report["summary"],
        "summary": {
            "changes": len(report["changes"]),
            "scenarios": len(scenarios),
            "runner_passed": sum(bool(scenario["generated"]["runner_passed"]) for scenario in scenarios),
            "runner_failed": sum(not scenario["generated"]["runner_passed"] for scenario in scenarios),
            "uncovered_changes": len(uncovered),
        },
        "scenarios": scenarios,
        "uncovered_changes": uncovered,
    }


def main() -> int:
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Gera cenários da versão candidata a partir do diff current → candidate.")
    parser.add_argument("current", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-input-bytes", type=int, default=None, help="limite máximo em bytes; padrão: WATSON_DIALOG_MAX_BYTES ou 50 MiB")
    args = parser.parse_args()
    try:
        result = generate_from_diff(
            load_json(args.current, max_bytes=args.max_input_bytes),
            load_json(args.candidate, max_bytes=args.max_input_bytes),
        )
    except (ValueError, KeyError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    output = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0 if result["summary"]["runner_failed"] == 0 else 1


if __name__ == "__main__":
    import sys
    from pathlib import Path
    raise SystemExit(main())
