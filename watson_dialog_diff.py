#!/usr/bin/env python3
"""Compare two Watson Assistant Dialog exports semantically.

The exports store their main collections as arrays of objects with UUIDs.  This
tool matches those objects by UUID, so a changed ordering in the JSON does not
appear as a change in the report.
"""

from __future__ import annotations

import argparse
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


DEFAULT_IGNORED_FIELDS = {"dataCriacao", "dataModificacao"}


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as file:
            document = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Não foi possível ler {path}: {error}") from error
    if not isinstance(document, dict):
        raise ValueError(f"{path} deve conter um objeto JSON na raiz.")
    return document


def item_label(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    for field in ("nome", "textoTema", "textoAcao", "textoObjeto", "variavelContexto"):
        if item.get(field):
            return str(item[field])
    return item.get("uuid", "(sem nome)")


def keyed_by_uuid(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, list) or not all(isinstance(item, dict) and "uuid" in item for item in value):
        return None
    return {str(item["uuid"]): item for item in value}


def path_join(base: str, part: str) -> str:
    return f"{base}.{part}" if base else part


def json_value(value: str) -> Any | None:
    """Decode JSON stored as text, used by dialog nodes' ``json`` field."""
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, (dict, list)) else None


def path_item(path: str, index: int) -> str:
    return f"{path}[{index}]"


def stable_item(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compare_list(current: list[Any], candidate: list[Any], path: str, ignored_fields: set[str]) -> list[dict[str, Any]]:
    """Compare an unkeyed list item-by-item, preserving order when it matters."""
    # Tags are labels, not an ordered dialog flow. Their order is irrelevant.
    if path.rsplit(".", 1)[-1] == "tags":
        current_values = sorted(stable_item(item) for item in current)
        candidate_values = sorted(stable_item(item) for item in candidate)
        matcher = SequenceMatcher(a=current_values, b=candidate_values, autojunk=False)
        decode = json.loads
        changes: list[dict[str, Any]] = []
        for operation, a_start, a_end, b_start, b_end in matcher.get_opcodes():
            if operation in ("delete", "replace"):
                changes.extend({"path": path, "kind": "removed", "before": decode(item), "after": None} for item in current_values[a_start:a_end])
            if operation in ("insert", "replace"):
                changes.extend({"path": path, "kind": "added", "before": None, "after": decode(item)} for item in candidate_values[b_start:b_end])
        return changes

    current_values = [stable_item(item) for item in current]
    candidate_values = [stable_item(item) for item in candidate]
    matcher = SequenceMatcher(a=current_values, b=candidate_values, autojunk=False)
    changes = []
    for operation, a_start, a_end, b_start, b_end in matcher.get_opcodes():
        if operation == "equal":
            continue
        if operation == "replace":
            shared = min(a_end - a_start, b_end - b_start)
            for offset in range(shared):
                changes.extend(find_differences(current[a_start + offset], candidate[b_start + offset], path_item(path, a_start + offset), ignored_fields))
            a_start += shared
            b_start += shared
        if operation in ("delete", "replace"):
            changes.extend({"path": path_item(path, index), "kind": "removed", "before": current[index], "after": None} for index in range(a_start, a_end))
        if operation in ("insert", "replace"):
            changes.extend({"path": path_item(path, index), "kind": "added", "before": None, "after": candidate[index]} for index in range(b_start, b_end))
    return changes


def find_differences(current: Any, candidate: Any, path: str, ignored_fields: set[str]) -> list[dict[str, Any]]:
    """Return atomic additions, removals and substitutions below *path*."""
    if isinstance(current, dict) and isinstance(candidate, dict):
        changes: list[dict[str, Any]] = []
        for key in sorted(set(current) | set(candidate)):
            if key in ignored_fields:
                continue
            child_path = path_join(path, key)
            if key not in current:
                changes.append({"path": child_path, "kind": "added", "before": None, "after": candidate[key]})
            elif key not in candidate:
                changes.append({"path": child_path, "kind": "removed", "before": current[key], "after": None})
            else:
                changes.extend(find_differences(current[key], candidate[key], child_path, ignored_fields))
        return changes

    # Some node configuration, including media components, is itself JSON
    # serialized inside a string field named ``json``. Compare its structure.
    if path.rsplit(".", 1)[-1] == "json" and isinstance(current, str) and isinstance(candidate, str):
        current_json, candidate_json = json_value(current), json_value(candidate)
        if current_json is not None and candidate_json is not None:
            return find_differences(current_json, candidate_json, path, ignored_fields)

    current_by_uuid, candidate_by_uuid = keyed_by_uuid(current), keyed_by_uuid(candidate)
    if current_by_uuid is not None and candidate_by_uuid is not None:
        changes = []
        for uuid in sorted(set(current_by_uuid) | set(candidate_by_uuid)):
            child_path = f"{path}[uuid={uuid}]"
            if uuid not in current_by_uuid:
                changes.append({"path": child_path, "kind": "added", "before": None, "after": candidate_by_uuid[uuid]})
            elif uuid not in candidate_by_uuid:
                changes.append({"path": child_path, "kind": "removed", "before": current_by_uuid[uuid], "after": None})
            else:
                changes.extend(find_differences(current_by_uuid[uuid], candidate_by_uuid[uuid], child_path, ignored_fields))
        return changes

    if isinstance(current, list) and isinstance(candidate, list):
        return compare_list(current, candidate, path, ignored_fields)

    if current != candidate:
        return [{"path": path or "$", "kind": "changed", "before": current, "after": candidate}]
    return []


def summarize(current: dict[str, Any], candidate: dict[str, Any], ignored_fields: set[str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": 1,
        "ignored_fields": sorted(ignored_fields),
        "summary": {"added": 0, "removed": 0, "changed": 0},
        "collections": {},
        "changes": [],
    }
    for key in sorted(set(current) | set(candidate)):
        if key in ignored_fields:
            continue
        before, after = current.get(key), candidate.get(key)
        before_map, after_map = keyed_by_uuid(before), keyed_by_uuid(after)
        if before_map is None or after_map is None:
            changes = find_differences(before, after, key, ignored_fields)
            if changes:
                result["collections"][key] = {"added": [], "removed": [], "changed": [{"label": key, "uuid": None, "changes": changes}]}
            continue

        collection = {"added": [], "removed": [], "changed": []}
        for uuid in sorted(set(before_map) | set(after_map)):
            if uuid not in before_map:
                collection["added"].append({"uuid": uuid, "label": item_label(after_map[uuid]), "value": after_map[uuid]})
            elif uuid not in after_map:
                collection["removed"].append({"uuid": uuid, "label": item_label(before_map[uuid]), "value": before_map[uuid]})
            else:
                changes = find_differences(before_map[uuid], after_map[uuid], "", ignored_fields)
                if changes:
                    collection["changed"].append({"uuid": uuid, "label": item_label(after_map[uuid]), "changes": changes})
        if any(collection.values()):
            result["collections"][key] = collection
    for collection, data in result["collections"].items():
        for entry in data["added"]:
            result["changes"].append({"collection": collection, "uuid": entry["uuid"], "label": entry["label"], "path": "$", "kind": "added", "before": None, "after": entry["value"]})
        for entry in data["removed"]:
            result["changes"].append({"collection": collection, "uuid": entry["uuid"], "label": entry["label"], "path": "$", "kind": "removed", "before": entry["value"], "after": None})
        for entry in data["changed"]:
            for change in entry["changes"]:
                result["changes"].append({"collection": collection, "uuid": entry["uuid"], "label": entry["label"], **change})
    for change in result["changes"]:
        result["summary"][change["kind"] if change["kind"] in ("added", "removed") else "changed"] += 1
    return result


def short_value(value: Any, limit: int = 180) -> str:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ": "))
    return rendered if len(rendered) <= limit else rendered[: limit - 1] + "…"


def markdown(report: dict[str, Any], max_changes: int) -> str:
    totals = report["summary"]
    lines = ["# Diff Watson Assistant", "", "`current → candidate`", "", "| Adicionados | Removidos | Alterados |", "| ---: | ---: | ---: |", f"| {totals['added']} | {totals['removed']} | {totals['changed']} |"]
    for collection, data in report["collections"].items():
        lines.extend(["", f"## {collection}"])
        for kind, title in (("added", "Adicionados"), ("removed", "Removidos")):
            if data[kind]:
                lines.extend(["", f"### {title}"])
                lines.extend(f"- `{entry['uuid']}` — {entry['label']}" for entry in data[kind])
        if data["changed"]:
            lines.extend(["", "### Alterados"])
            for entry in data["changed"]:
                lines.extend(["", f"#### {entry['label']} (`{entry['uuid']}`)"])
                shown = entry["changes"][:max_changes]
                for change in shown:
                    lines.append(f"- `{change['path']}`: {short_value(change['before'])} → {short_value(change['after'])}")
                hidden = len(entry["changes"]) - len(shown)
                if hidden:
                    lines.append(f"- _… e mais {hidden} alteração(ões); use `--max-changes` para exibir._")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Diff semântico de exports do Watson Assistant Dialog.")
    parser.add_argument("current", type=Path, help="arquivo da versão atual")
    parser.add_argument("candidate", type=Path, help="arquivo da versão candidata")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path, help="grava o relatório neste arquivo; padrão: stdout")
    parser.add_argument("--include-timestamps", action="store_true", help="inclui dataCriacao e dataModificacao")
    parser.add_argument("--max-changes", type=int, default=20, help="máximo de campos mostrados por item no Markdown")
    args = parser.parse_args()
    if args.max_changes < 1:
        parser.error("--max-changes deve ser pelo menos 1")

    ignored = set() if args.include_timestamps else DEFAULT_IGNORED_FIELDS
    try:
        report = summarize(load_json(args.current), load_json(args.candidate), ignored)
    except ValueError as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n" if args.format == "json" else markdown(report, args.max_changes)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 1 if report["changes"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
