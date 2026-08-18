"""SIGNAL Design System HTML Mission Control & Triage Console Generator."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on sys.path when invoked directly
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)


import json
from pathlib import Path
from typing import Any

from tare_dialog.diff_engine import load_json
from tare_dialog.explorer import explore_document
from tare_dialog.validator import validate


def generate_triage_data(current_doc: dict[str, Any], candidate_doc: dict[str, Any]) -> dict[str, Any]:
    """Generate optimized triage dataset for the SIGNAL HTML console."""
    current_rep = validate(current_doc)
    candidate_rep = validate(candidate_doc)

    def build_node_indexer(document: dict[str, Any]) -> dict[str, Any]:
        index: dict[str, Any] = {}
        var_by_uuid = {
            str(item.get("uuid")): str(item.get("variavelContexto", "")).lstrip("$")
            for item in document.get("variaveisContexto") or []
            if isinstance(item, dict) and item.get("uuid") and item.get("variavelContexto")
        }

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