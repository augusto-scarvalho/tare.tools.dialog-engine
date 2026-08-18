"""SIGNAL Design System HTML Mission Control & Triage Console Generator."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on sys.path when invoked directly
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)


from pathlib import Path
from typing import Any

from tare_dialog.test_runner import normalize_document
from tare_dialog.validator import validate


def generate_triage_data(current_doc: dict[str, Any], candidate_doc: dict[str, Any]) -> dict[str, Any]:
    """Generate optimized triage dataset for the SIGNAL HTML console."""
    def validate_full(doc: dict[str, Any]) -> dict[str, Any]:
        is_v1 = "dialog_nodes" in doc and not doc.get("nos")
        if is_v1:
            v1_rep = validate(doc)
            try:
                norm_doc = normalize_document(doc)
                norm_rep = validate(norm_doc)
            except Exception:
                norm_rep = {"issues": [], "summary": {"issues": 0}}

            combined_issues = list(v1_rep.get("issues", []))
            seen = {(iss.get("node"), iss.get("code"), iss.get("field")) for iss in combined_issues}

            for iss in norm_rep.get("issues", []):
                key = (iss.get("node"), iss.get("code"), iss.get("field"))
                if key not in seen:
                    seen.add(key)
                    combined_issues.append(iss)

            by_severity: dict[str, int] = {}
            for iss in combined_issues:
                sev = str(iss.get("severity", "info"))
                by_severity[sev] = by_severity.get(sev, 0) + 1

            by_category: dict[str, int] = {}
            for iss in combined_issues:
                cat = str(iss.get("category", "semantic"))
                by_category[cat] = by_category.get(cat, 0) + 1

            return {
                "summary": {
                    "issues": len(combined_issues),
                    "issues_by_severity": by_severity,
                    "issues_by_category": by_category,
                },
                "issues": combined_issues,
            }
        else:
            return validate(doc)

    current_rep = validate_full(current_doc)
    candidate_rep = validate_full(candidate_doc)

    def build_node_indexer(document: dict[str, Any]) -> dict[str, Any]:
        index: dict[str, Any] = {}

        # 1. Flat Watson V1 format (dialog_nodes)
        if "dialog_nodes" in document and isinstance(document["dialog_nodes"], list):
            for node in document["dialog_nodes"]:
                if not isinstance(node, dict):
                    continue
                node_id = str(node.get("dialog_node") or node.get("uuid") or "")
                if not node_id:
                    continue
                parent_id = str(node.get("parent")) if node.get("parent") else None
                index[node_id] = {
                    "uuid": node_id,
                    "kind": node.get("type", "dialog_node"),
                    "parent_id": parent_id,
                    "name": node.get("title") or node.get("dialog_node"),
                    "status": "active" if node.get("conditions") != "false" else "inactive",
                    "condition": node.get("conditions"),
                    "path": [{"uuid": node_id, "name": node.get("title") or node_id, "kind": "dialog_node"}],
                    "raw_json": node,
                }
            return index

        # 2. Nested Enterprise format (nos / filhos)
        def visit(nodes: list[dict[str, Any]], parent_id: str | None = None, path: list[dict[str, Any]] | None = None) -> None:
            path = path or []
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                node_id = str(node.get("uuid") or "")
                if not node_id:
                    continue
                curr_path = [*path, {"uuid": node_id, "name": node.get("nome"), "kind": "dialog_node"}]
                index[node_id] = {
                    "uuid": node_id,
                    "kind": "dialog_node",
                    "parent_id": parent_id,
                    "name": node.get("nome"),
                    "status": node.get("status"),
                    "condition": node.get("condicao"),
                    "path": curr_path,
                    "raw_json": {k: v for k, v in node.items() if k not in ("filhos", "slots")},
                }
                visit(node.get("filhos") or [], node_id, curr_path)

        visit(document.get("nos") or [])
        return index

    return {
        "generated_at": "2026-08-18T12:00:00Z",
        "current": {
            "summary": current_rep["summary"],
            "actionable_issues": current_rep["issues"],
            "total_info_count": current_rep["summary"]["issues_by_severity"].get("info", 0),
            "nodes": build_node_indexer(current_doc),
        },
        "candidate": {
            "summary": candidate_rep["summary"],
            "actionable_issues": candidate_rep["issues"],
            "total_info_count": candidate_rep["summary"]["issues_by_severity"].get("info", 0),
            "nodes": build_node_indexer(candidate_doc),
        }
    }
