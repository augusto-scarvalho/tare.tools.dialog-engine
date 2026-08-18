#!/usr/bin/env python3
"""Compare two Watson Assistant Dialog exports semantically.

The exports store their main collections as arrays of objects with UUIDs.  This
tool matches those objects by UUID, so a changed ordering in the JSON does not
appear as a change in the report.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from watson_dialog_resources import DEFAULT_MAX_INPUT_BYTES, ResourceBudget, resolve_jobs, resolve_max_input_bytes


DEFAULT_IGNORED_FIELDS = {"dataCriacao", "dataModificacao"}
DEFAULT_EXTERNAL_THRESHOLD_BYTES = 16 * 1024 * 1024
DEFAULT_DOM_MEMORY_MULTIPLIER = 10.0
DEFAULT_DOM_MEMORY_FRACTION = 0.30

def configure_utf8_output() -> None:
    """Ensure standard output and error streams handle UTF-8 cleanly on all platforms."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass


def load_json(path: Path, max_bytes: int | None = None) -> dict[str, Any]:
    max_bytes = resolve_max_input_bytes(max_bytes)
    try:
        if max_bytes > 0 and path.exists():
            file_size = path.stat().st_size
            if file_size > max_bytes:
                raise ValueError(
                    f"Arquivo {path} ({file_size} bytes) excede o limite configurado de {max_bytes} bytes. "
                    f"Use --max-input-bytes para aumentar o limite se necessário."
                )
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


def summarize(current: dict[str, Any], candidate: dict[str, Any], ignored_fields: set[str], summary_only: bool = False) -> dict[str, Any]:
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
                result["collections"][key] = {"added": [], "removed": [], "changed": [{"label": key, "uuid": None, "changes": changes if not summary_only else []}]}
                result["summary"]["changed"] += len(changes)
                if not summary_only:
                    result["changes"].extend({"collection": key, "uuid": None, "label": key, **c} for c in changes)
            continue

        collection = {"added": [], "removed": [], "changed": []}
        for uuid in sorted(set(before_map) | set(after_map)):
            if uuid not in before_map:
                collection["added"].append({"uuid": uuid, "label": item_label(after_map[uuid]), "value": after_map[uuid] if not summary_only else None})
            elif uuid not in after_map:
                collection["removed"].append({"uuid": uuid, "label": item_label(before_map[uuid]), "value": before_map[uuid] if not summary_only else None})
            else:
                changes = find_differences(before_map[uuid], after_map[uuid], "", ignored_fields)
                if changes:
                    collection["changed"].append({"uuid": uuid, "label": item_label(after_map[uuid]), "changes": changes if not summary_only else []})
        if any(collection.values()):
            result["collections"][key] = collection
            result["summary"]["added"] += len(collection["added"])
            result["summary"]["removed"] += len(collection["removed"])
            result["summary"]["changed"] += len(collection["changed"])

    if not summary_only:
        for collection, data in result["collections"].items():
            for entry in data["added"]:
                result["changes"].append({"collection": collection, "uuid": entry["uuid"], "label": entry["label"], "path": "$", "kind": "added", "before": None, "after": entry["value"]})
            for entry in data["removed"]:
                result["changes"].append({"collection": collection, "uuid": entry["uuid"], "label": entry["label"], "path": "$", "kind": "removed", "before": entry["value"], "after": None})
            for entry in data["changed"]:
                for change in entry["changes"]:
                    result["changes"].append({"collection": collection, "uuid": entry["uuid"], "label": entry["label"], **change})
        result["summary"] = {"added": 0, "removed": 0, "changed": 0}
        for change in result["changes"]:
            result["summary"][change["kind"] if change["kind"] in ("added", "removed") else "changed"] += 1
    return result


class ExternalDiffUnsupported(ValueError):
    """Raised when the source-backed engine cannot preserve incumbent semantics."""


def _empty_report(ignored_fields: set[str]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ignored_fields": sorted(ignored_fields),
        "summary": {"added": 0, "removed": 0, "changed": 0},
        "collections": {},
        "changes": [],
    }


def _prefix_changes(changes: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    if not prefix:
        return changes
    prefixed: list[dict[str, Any]] = []
    for change in changes:
        copied = dict(change)
        path = str(copied.get("path") or "$")
        copied["path"] = prefix if path == "$" else f"{prefix}.{path}"
        prefixed.append(copied)
    return prefixed


def _diff_payload_task(task: tuple[int, str, bytes, bytes, str, tuple[str, ...]]) -> tuple[int, str, list[dict[str, Any]]]:
    """Worker-safe record diff used by the external engine.

    Workers receive only bounded record-local JSON bytes, never an mmap or a
    full export.  This keeps process isolation portable to Windows spawn while
    preserving the parent process' external-memory contract.
    """
    ordinal, root_id, current_bytes, candidate_bytes, prefix, ignored = task
    current = json.loads(current_bytes)
    candidate = json.loads(candidate_bytes)
    changes = find_differences(current, candidate, "", set(ignored))
    return ordinal, root_id, _prefix_changes(changes, prefix)


def _run_payload_tasks(
    tasks: list[tuple[int, str, bytes, bytes, str, tuple[str, ...]]],
    jobs: int,
) -> list[tuple[int, str, list[dict[str, Any]]]]:
    if not tasks:
        return []
    if jobs <= 1 or len(tasks) == 1:
        return [_diff_payload_task(task) for task in tasks]

    # Bound queued work to avoid turning sparse changed-node materialization
    # into a second memory spike on large exports.
    results: list[tuple[int, str, list[dict[str, Any]]]] = []
    iterator = iter(tasks)
    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as executor:
        pending: dict[concurrent.futures.Future[tuple[int, str, list[dict[str, Any]]]], None] = {}
        for _ in range(min(len(tasks), jobs * 2)):
            try:
                pending[executor.submit(_diff_payload_task, next(iterator))] = None
            except StopIteration:
                break
        while pending:
            done, _ = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                pending.pop(future)
                results.append(future.result())
                try:
                    pending[executor.submit(_diff_payload_task, next(iterator))] = None
                except StopIteration:
                    pass
    return sorted(results, key=lambda result: result[0])


def _has_covering_ancestor(index: Any, record_id: str, covered: set[str]) -> bool:
    return any(ancestor in covered for ancestor in index.ancestors(record_id))


def _decode_bytes(value: bytes) -> Any:
    return json.loads(value)


def _ordered_sequence_tokens(
    current_index: Any,
    current_refs: list[Any],
    candidate_index: Any,
    candidate_refs: list[Any],
) -> tuple[list[tuple[str, str, int]], list[tuple[str, str, int]]]:
    """Build exact-equality tokens for incumbent ``SequenceMatcher`` parity.

    Each ordered-item ref carries a SHA-256 of the incumbent-compatible stable
    JSON serialization.  A digest that appears only once across both sequences
    cannot participate in equality, so no canonical bytes need to stay in
    memory.  Repeated digests are verified against the exact canonical bytes
    and assigned an equivalence-class integer.  This makes a cryptographic
    collision a detected condition rather than a silent semantic shortcut.
    """
    counts: dict[str, int] = {}
    for ref in [*current_refs, *candidate_refs]:
        counts[ref.stable_digest] = counts.get(ref.stable_digest, 0) + 1

    variants: dict[str, dict[bytes, int]] = {}

    def tokens(index: Any, refs: list[Any]) -> list[tuple[str, str, int]]:
        result: list[tuple[str, str, int]] = []
        for ref in refs:
            digest = ref.stable_digest
            if counts[digest] == 1:
                result.append(("unique", digest, 0))
                continue
            canonical = index.ordered_item_stable_bytes(ref)
            group = variants.setdefault(digest, {})
            variant = group.get(canonical)
            if variant is None:
                variant = len(group)
                group[canonical] = variant
            result.append(("exact", digest, variant))
        return result

    return tokens(current_index, current_refs), tokens(candidate_index, candidate_refs)


def _external_ordered_object_array(
    key: str,
    current_index: Any,
    candidate_index: Any,
    current_refs: list[Any],
    candidate_refs: list[Any],
    ignored_fields: set[str],
    summary_only: bool,
    jobs: str | int,
) -> dict[str, Any] | None:
    """External-memory equivalent of :func:`compare_list` for object arrays.

    This intentionally preserves the incumbent's *order-sensitive* semantics.
    In particular V1 ``dialog_nodes`` is not reinterpreted as an identity map
    by ``dialog_node`` in this parity mode.
    """
    current_tokens, candidate_tokens = _ordered_sequence_tokens(
        current_index, current_refs, candidate_index, candidate_refs
    )
    matcher = SequenceMatcher(a=current_tokens, b=candidate_tokens, autojunk=False)

    events: list[tuple[int, str, int, int | None]] = []
    pair_tasks: list[tuple[int, str, bytes, bytes, str, tuple[str, ...]]] = []
    event_ordinal = 0
    pair_ordinal = 0
    for operation, a_start, a_end, b_start, b_end in matcher.get_opcodes():
        if operation == "equal":
            continue
        if operation == "replace":
            shared = min(a_end - a_start, b_end - b_start)
            for offset in range(shared):
                ai, bi = a_start + offset, b_start + offset
                events.append((event_ordinal, "pair", pair_ordinal, None))
                pair_tasks.append(
                    (
                        pair_ordinal,
                        key,
                        current_index.ordered_item_bytes(current_refs[ai]),
                        candidate_index.ordered_item_bytes(candidate_refs[bi]),
                        path_item(key, ai),
                        tuple(sorted(ignored_fields)),
                    )
                )
                event_ordinal += 1
                pair_ordinal += 1
            a_start += shared
            b_start += shared
        if operation in ("delete", "replace"):
            for ai in range(a_start, a_end):
                events.append((event_ordinal, "delete", ai, None))
                event_ordinal += 1
        if operation in ("insert", "replace"):
            for bi in range(b_start, b_end):
                events.append((event_ordinal, "insert", bi, None))
                event_ordinal += 1

    budget = ResourceBudget.detect()
    worker_count = resolve_jobs(jobs, len(pair_tasks), budget) if pair_tasks else 1
    pair_results = {ordinal: changes for ordinal, _, changes in _run_payload_tasks(pair_tasks, worker_count)}

    changes: list[dict[str, Any]] = []
    for _, event_type, index_value, _ in events:
        if event_type == "pair":
            changes.extend(pair_results.get(index_value, []))
        elif event_type == "delete":
            before = None if summary_only else _decode_bytes(current_index.ordered_item_bytes(current_refs[index_value]))
            changes.append({"path": path_item(key, index_value), "kind": "removed", "before": before, "after": None})
        else:
            after = None if summary_only else _decode_bytes(candidate_index.ordered_item_bytes(candidate_refs[index_value]))
            changes.append({"path": path_item(key, index_value), "kind": "added", "before": None, "after": after})

    if not changes:
        return None
    return {
        "added": [],
        "removed": [],
        "changed": [{"label": key, "uuid": None, "changes": changes if not summary_only else []}],
        "_summary_atomic_changed": len(changes),
        "_preflatten_changes": [] if summary_only else list(changes),
    }


def _external_generic_collection(
    key: str,
    current_index: Any,
    candidate_index: Any,
    ignored_fields: set[str],
    summary_only: bool,
    jobs: str | int,
) -> dict[str, Any] | None:
    """Compare a root UUID collection without materializing the whole array."""
    before_map = current_index.uuid_collection(key) if key in current_index.root_fields else None
    after_map = candidate_index.uuid_collection(key) if key in candidate_index.root_fields else None
    if before_map is None or after_map is None:
        if key in current_index.root_fields and key in candidate_index.root_fields:
            before_ordered = current_index.ordered_object_array(key)
            after_ordered = candidate_index.ordered_object_array(key)
            if before_ordered is not None and after_ordered is not None:
                return _external_ordered_object_array(
                    key,
                    current_index,
                    candidate_index,
                    before_ordered,
                    after_ordered,
                    ignored_fields,
                    summary_only,
                    jobs,
                )
        before = current_index.root_value(key) if key in current_index.root_fields else None
        after = candidate_index.root_value(key) if key in candidate_index.root_fields else None
        changes = find_differences(before, after, key, ignored_fields)
        if not changes:
            return None
        return {
            "added": [],
            "removed": [],
            "changed": [{"label": key, "uuid": None, "changes": changes if not summary_only else []}],
            "_summary_atomic_changed": len(changes),
            "_preflatten_changes": [] if summary_only else list(changes),
        }

    collection: dict[str, list[dict[str, Any]]] = {"added": [], "removed": [], "changed": []}
    for uuid in sorted(set(before_map) | set(after_map)):
        before_ref = before_map.get(uuid)
        after_ref = after_map.get(uuid)
        if before_ref is None and after_ref is not None:
            value = _decode_bytes(candidate_index.collection_item_bytes(after_ref))
            collection["added"].append({"uuid": uuid, "label": item_label(value), "value": value if not summary_only else None})
        elif after_ref is None and before_ref is not None:
            value = _decode_bytes(current_index.collection_item_bytes(before_ref))
            collection["removed"].append({"uuid": uuid, "label": item_label(value), "value": value if not summary_only else None})
        elif before_ref is not None and after_ref is not None and before_ref.semantic_digest != after_ref.semantic_digest:
            before = _decode_bytes(current_index.collection_item_bytes(before_ref))
            after = _decode_bytes(candidate_index.collection_item_bytes(after_ref))
            changes = find_differences(before, after, "", ignored_fields)
            if changes:
                collection["changed"].append({"uuid": uuid, "label": item_label(after), "changes": changes if not summary_only else []})
    return collection if any(collection.values()) else None


def _external_legacy_nodes(
    current_index: Any,
    candidate_index: Any,
    ignored_fields: set[str],
    summary_only: bool,
    jobs: str | int,
) -> dict[str, Any] | None:
    """Compare legacy ``nos`` by local records while reconstructing nested paths."""
    current_roots = set(current_index.roots)
    candidate_roots = set(candidate_index.roots)
    current_records = current_index.records
    candidate_records = candidate_index.records
    common_records = set(current_records) & set(candidate_records)

    collection: dict[str, list[dict[str, Any]]] = {"added": [], "removed": [], "changed": []}
    changed_by_root: dict[str, list[dict[str, Any]]] = {}

    # Top-level list semantics remain exactly those of the incumbent UUID map.
    for root_id in sorted(candidate_roots - current_roots):
        value = candidate_index.load_record(root_id)
        collection["added"].append({"uuid": root_id, "label": item_label(value), "value": value if not summary_only else None})
    for root_id in sorted(current_roots - candidate_roots):
        value = current_index.load_record(root_id)
        collection["removed"].append({"uuid": root_id, "label": item_label(value), "value": value if not summary_only else None})

    relation_changed = {
        record_id
        for record_id in common_records
        if current_records[record_id].parent_id != candidate_records[record_id].parent_id
    }
    removed_records = set(current_records) - set(candidate_records)
    added_records = set(candidate_records) - set(current_records)
    # A missing/moved ancestor already carries its subtree as the value of one
    # list addition/removal.  Descendants must not be reported twice.
    current_cover = set(removed_records) | relation_changed | (current_roots - candidate_roots)
    candidate_cover = set(added_records) | relation_changed | (candidate_roots - current_roots)

    def add_nested_change(root_id: str, change: dict[str, Any]) -> None:
        if root_id in current_roots & candidate_roots:
            changed_by_root.setdefault(root_id, []).append(change)

    # Pure removals below a surviving top-level root.
    for record_id in sorted(removed_records):
        root_id, path = current_index.legacy_root_and_path(record_id)
        if root_id not in current_roots & candidate_roots:
            continue
        if _has_covering_ancestor(current_index, record_id, current_cover - {record_id}):
            continue
        before = None if summary_only else current_index.load_record(record_id)
        add_nested_change(root_id, {"path": path, "kind": "removed", "before": before, "after": None})

    # Pure additions below a surviving top-level root.
    for record_id in sorted(added_records):
        root_id, path = candidate_index.legacy_root_and_path(record_id)
        if root_id not in current_roots & candidate_roots:
            continue
        if _has_covering_ancestor(candidate_index, record_id, candidate_cover - {record_id}):
            continue
        after = None if summary_only else candidate_index.load_record(record_id)
        add_nested_change(root_id, {"path": path, "kind": "added", "before": None, "after": after})

    # Moves are represented as list removal + list addition, matching the
    # incumbent's recursive keyed-list comparison.  Descendants of a moved
    # record are covered by the moved subtree itself.
    for record_id in sorted(relation_changed):
        if _has_covering_ancestor(current_index, record_id, relation_changed - {record_id}) or _has_covering_ancestor(
            candidate_index, record_id, relation_changed - {record_id}
        ):
            continue
        old_root, old_path = current_index.legacy_root_and_path(record_id)
        new_root, new_path = candidate_index.legacy_root_and_path(record_id)
        if old_root in current_roots & candidate_roots:
            before = None if summary_only else current_index.load_record(record_id)
            add_nested_change(old_root, {"path": old_path, "kind": "removed", "before": before, "after": None})
        if new_root in current_roots & candidate_roots:
            after = None if summary_only else candidate_index.load_record(record_id)
            add_nested_change(new_root, {"path": new_path, "kind": "added", "before": None, "after": after})

    tasks: list[tuple[int, str, bytes, bytes, str, tuple[str, ...]]] = []
    ordinal = 0
    for record_id in sorted(common_records - relation_changed):
        before_ref = current_records[record_id]
        after_ref = candidate_records[record_id]
        if before_ref.semantic_digest == after_ref.semantic_digest:
            continue
        if _has_covering_ancestor(current_index, record_id, relation_changed) or _has_covering_ancestor(
            candidate_index, record_id, relation_changed
        ):
            continue
        old_root, old_path = current_index.legacy_root_and_path(record_id)
        new_root, new_path = candidate_index.legacy_root_and_path(record_id)
        if old_root != new_root or old_path != new_path:
            # Defensive fallback; parent-id changes should already have put the
            # record in relation_changed.
            continue
        if old_root not in current_roots & candidate_roots:
            continue
        tasks.append(
            (
                ordinal,
                old_root,
                current_index.local_record_bytes(record_id),
                candidate_index.local_record_bytes(record_id),
                old_path,
                tuple(sorted(ignored_fields)),
            )
        )
        ordinal += 1

    budget = ResourceBudget.detect()
    worker_count = resolve_jobs(jobs, len(tasks), budget) if tasks else 1
    for _, root_id, changes in _run_payload_tasks(tasks, worker_count):
        if changes:
            changed_by_root.setdefault(root_id, []).extend(changes)

    for root_id in sorted(changed_by_root):
        changes = sorted(
            changed_by_root[root_id],
            key=lambda change: (
                str(change.get("path", "")),
                str(change.get("kind", "")),
                stable_item(change.get("before")),
                stable_item(change.get("after")),
            ),
        )
        label_source = candidate_index if root_id in candidate_records else current_index
        label = item_label(label_source.load_local_record(root_id))
        collection["changed"].append({"uuid": root_id, "label": label, "changes": changes if not summary_only else []})

    return collection if any(collection.values()) else None


def summarize_external_paths(
    current_path: Path,
    candidate_path: Path,
    ignored_fields: set[str],
    *,
    summary_only: bool = False,
    max_bytes: int | None = None,
    jobs: str | int = "auto",
    index_backend: str = "auto",
) -> dict[str, Any]:
    """Source-backed semantic diff for legacy exports.

    The full export is never materialized.  Only changed/added/removed records
    become Python objects; unchanged records are rejected by semantic digest.
    """
    from watson_dialog_external import open_dialog_index

    with open_dialog_index(
        current_path,
        max_bytes=max_bytes,
        capture_details=True,
        ignored_fields=ignored_fields,
        backend=index_backend,
    ) as current_index, open_dialog_index(
        candidate_path,
        max_bytes=max_bytes,
        capture_details=True,
        ignored_fields=ignored_fields,
        backend=index_backend,
    ) as candidate_index:
        if current_index.format_type != candidate_index.format_type:
            raise ExternalDiffUnsupported(
                f"Formats incompatíveis: current={current_index.format_type}, candidate={candidate_index.format_type}"
            )
        if current_index.format_type not in {"legacy", "v1"}:
            raise ExternalDiffUnsupported(
                f"Formato external não suportado: {current_index.format_type}."
            )

        result = _empty_report(ignored_fields)
        for key in sorted(set(current_index.root_fields) | set(candidate_index.root_fields)):
            if key in ignored_fields:
                continue
            if key == "nos" and current_index.format_type == "legacy" and key in current_index.root_fields and key in candidate_index.root_fields:
                collection = _external_legacy_nodes(
                    current_index,
                    candidate_index,
                    ignored_fields,
                    summary_only,
                    jobs,
                )
            else:
                collection = _external_generic_collection(
                    key,
                    current_index,
                    candidate_index,
                    ignored_fields,
                    summary_only,
                    jobs,
                )
            if collection is not None:
                summary_atomic_changed = int(collection.pop("_summary_atomic_changed", len(collection["changed"])))
                preflatten_changes = collection.pop("_preflatten_changes", [])
                result["collections"][key] = collection
                result["summary"]["added"] += len(collection["added"])
                result["summary"]["removed"] += len(collection["removed"])
                result["summary"]["changed"] += summary_atomic_changed if summary_only else len(collection["changed"])
                if not summary_only:
                    result["changes"].extend(
                        {"collection": key, "uuid": None, "label": key, **change}
                        for change in preflatten_changes
                    )

        if not summary_only:
            for collection_name, data in result["collections"].items():
                for entry in data["added"]:
                    result["changes"].append({
                        "collection": collection_name,
                        "uuid": entry["uuid"],
                        "label": entry["label"],
                        "path": "$",
                        "kind": "added",
                        "before": None,
                        "after": entry["value"],
                    })
                for entry in data["removed"]:
                    result["changes"].append({
                        "collection": collection_name,
                        "uuid": entry["uuid"],
                        "label": entry["label"],
                        "path": "$",
                        "kind": "removed",
                        "before": entry["value"],
                        "after": None,
                    })
                for entry in data["changed"]:
                    for change in entry["changes"]:
                        result["changes"].append({
                            "collection": collection_name,
                            "uuid": entry["uuid"],
                            "label": entry["label"],
                            **change,
                        })
            result["summary"] = {"added": 0, "removed": 0, "changed": 0}
            for change in result["changes"]:
                result["summary"][change["kind"] if change["kind"] in ("added", "removed") else "changed"] += 1
        return result


def choose_diff_engine(
    current_path: Path,
    candidate_path: Path,
    requested: str = "auto",
    *,
    budget: ResourceBudget | None = None,
) -> str:
    """Choose the fast DOM path only when it has a conservative RAM envelope.

    ``DEFAULT_EXTERNAL_THRESHOLD_BYTES`` remains a small-file fast-path floor:
    below it, the incumbent DOM is used directly.  Above it, ``auto`` no longer
    means "external unconditionally".  The combined encoded size is expanded
    by an empirical safety multiplier and must fit inside a bounded fraction of
    *currently available* memory.  Unknown memory resolves conservatively to
    external.

    Explicit ``--engine dom|external`` always wins and is the rollback/control
    surface for callers that know more about their workload than the heuristic.
    """
    if requested in {"dom", "external"}:
        return requested
    if requested != "auto":
        raise ValueError("engine deve ser auto, dom ou external")
    threshold_text = os.environ.get("WATSON_DIALOG_EXTERNAL_THRESHOLD_BYTES", "").strip()
    explicit_threshold = threshold_text.isdigit()
    threshold = int(threshold_text) if explicit_threshold else DEFAULT_EXTERNAL_THRESHOLD_BYTES
    largest = max(current_path.stat().st_size, candidate_path.stat().st_size)
    if largest < threshold:
        return "dom"
    if explicit_threshold:
        # Preserve the historical meaning of the existing environment knob:
        # callers that set it explicitly asked for a deterministic size cutoff.
        return "external"

    resolved_budget = budget or ResourceBudget.detect()
    available = resolved_budget.available_memory_bytes
    if not available:
        return "external"
    encoded_total = current_path.stat().st_size + candidate_path.stat().st_size
    estimated_dom_peak = int(encoded_total * DEFAULT_DOM_MEMORY_MULTIPLIER)
    dom_memory_budget = int(available * DEFAULT_DOM_MEMORY_FRACTION)
    return "dom" if estimated_dom_peak <= dom_memory_budget else "external"


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
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Diff semântico de exports do Watson Assistant Dialog.")
    parser.add_argument("current", type=Path, help="arquivo da versão atual")
    parser.add_argument("candidate", type=Path, help="arquivo da versão candidata")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path, help="grava o relatório neste arquivo; padrão: stdout")
    parser.add_argument("--include-timestamps", action="store_true", help="inclui dataCriacao e dataModificacao")
    parser.add_argument("--max-changes", type=int, default=20, help="máximo de campos mostrados por item no Markdown")
    parser.add_argument("--max-input-bytes", type=int, default=None, help="limite máximo em bytes; padrão: WATSON_DIALOG_MAX_BYTES ou 50 MiB")
    parser.add_argument("--summary-only", action="store_true", help="emite apenas sumário consolidado de contagens")
    parser.add_argument(
        "--engine",
        choices=("auto", "dom", "external"),
        default="auto",
        help="auto usa external para exports >= 16 MiB; dom força json.load; external força índice source-backed legacy/V1",
    )
    parser.add_argument(
        "--jobs",
        default="auto",
        help="workers do diff detalhado external: auto ou inteiro positivo",
    )
    parser.add_argument(
        "--index-backend",
        choices=("auto", "mmap", "transient"),
        default="auto",
        help="backend do índice external: auto escolhe transient quando um DOM por vez cabe com folga; mmap força bounded-memory estrito",
    )
    args = parser.parse_args()
    if args.max_changes < 1:
        parser.error("--max-changes deve ser pelo menos 1")

    ignored = set() if args.include_timestamps else DEFAULT_IGNORED_FIELDS
    try:
        engine = choose_diff_engine(args.current, args.candidate, args.engine)
        if engine == "external":
            report = summarize_external_paths(
                args.current,
                args.candidate,
                set(ignored),
                summary_only=args.summary_only,
                max_bytes=args.max_input_bytes,
                jobs=args.jobs,
                index_backend=args.index_backend,
            )
        else:
            report = summarize(
                load_json(args.current, max_bytes=args.max_input_bytes),
                load_json(args.candidate, max_bytes=args.max_input_bytes),
                ignored,
                summary_only=args.summary_only,
            )
    except (OSError, ValueError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n" if args.format == "json" else markdown(report, args.max_changes)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    if args.summary_only:
        return 1 if any(report["summary"].values()) else 0
    return 1 if report["changes"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
