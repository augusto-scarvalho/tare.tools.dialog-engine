"""Shared document model, indexer, and preflight safety inspector for Watson Assistant Dialog.

Provides uniform indexed access across Legacy/Enterprise formats and official IBM Watson API V1/V2 formats,
with lazy lookups, parent/child relationships, slot indexers, multichannel awareness, and document preflight checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from watson_dialog_conditions import sorted_siblings
from watson_dialog_explorer import (
    DialogNode,
    DialogResponse,
    DialogSlot,
    UniversalDialogDocument,
    detect_dialog_format,
    explore_document,
    introspect_primitives,
)
from watson_dialog_external import DialogSourceIndex
from watson_dialog_resources import resolve_max_input_bytes
from watson_dialog_test import normalize_document


@dataclass(frozen=True)
class PreflightMetadata:
    path: str
    file_size_bytes: int
    format_type: str  # 'watson_v1_flat', 'enterprise_nested', 'hybrid', 'empty', or 'unknown'
    node_count: int
    intent_count: int
    entity_count: int
    is_safe: bool
    warnings: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    has_multimedia: bool = False
    tags_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "file_size_bytes": self.file_size_bytes,
            "format_type": self.format_type,
            "node_count": self.node_count,
            "intent_count": self.intent_count,
            "entity_count": self.entity_count,
            "is_safe": self.is_safe,
            "warnings": self.warnings,
            "channels": self.channels,
            "has_multimedia": self.has_multimedia,
            "tags_count": self.tags_count,
        }


def preflight_check(path: Path, max_bytes: int | None = None) -> PreflightMetadata:
    """Inspect the export without materializing the complete JSON document."""
    resolved_max = resolve_max_input_bytes(max_bytes)
    if not path.exists():
        raise ValueError(f"Arquivo não encontrado: {path}")

    file_size = path.stat().st_size
    if resolved_max > 0 and file_size > resolved_max:
        raise ValueError(
            f"Arquivo {path} ({file_size} bytes) excede o limite configurado de {resolved_max} bytes."
        )

    warnings: list[str] = []
    if file_size > 10 * 1024 * 1024:
        warnings.append(
            f"Export de tamanho elevado ({file_size / (1024*1024):.1f} MiB). "
            "Use operações source-backed/summary quando disponíveis."
        )

    with DialogSourceIndex.open(path, max_bytes=resolved_max) as source_index:
        summary = source_index.summary()
        format_type = str(summary["format_type"])
        if format_type == "v1":
            node_count = len(source_index.records)
            intent_count = int(source_index.top_level_counts.get("intents", 0))
            entity_count = int(source_index.top_level_counts.get("entities", 0))
        else:
            node_count = sum(1 for ref in source_index.records.values() if ref.kind != "slot")
            intent_count = int(source_index.top_level_counts.get("intencoes", 0))
            entity_count = int(source_index.top_level_counts.get("entidades", 0))

    return PreflightMetadata(
        path=str(path),
        file_size_bytes=file_size,
        format_type=format_type,
        node_count=node_count,
        intent_count=intent_count,
        entity_count=entity_count,
        is_safe=True,
        warnings=warnings,
    )


class DialogIndex:
    """Unified, indexed document structure for Watson Dialog (Legacy, Enterprise, and V1)."""

    def __init__(self, raw_document: dict[str, Any]) -> None:
        self.raw_document = raw_document
        self.universal_doc: UniversalDialogDocument = explore_document(raw_document)
        self.normalized_document = normalize_document(raw_document)
        self.nodes_by_id: dict[str, dict[str, Any]] = {}
        self.parent_by_id: dict[str, str | None] = {}
        self.children_by_parent: dict[str | None, list[str]] = {}
        self.slots_by_node: dict[str, list[dict[str, Any]]] = {}
        self.slots_by_id: dict[str, dict[str, Any]] = {}
        self.roots: list[str] = []
        self.folders: list[str] = []
        self._build_indexes()

    def _build_indexes(self) -> None:
        def visit(nodes: list[dict[str, Any]], parent_id: str | None) -> None:
            ordered = sorted_siblings(nodes)
            for node in ordered:
                node_id = str(node["uuid"])
                self.nodes_by_id[node_id] = node
                self.parent_by_id[node_id] = parent_id
                self.children_by_parent.setdefault(parent_id, []).append(node_id)
                if node.get("folder"):
                    self.folders.append(node_id)
                if parent_id is None:
                    self.roots.append(node_id)

                for slot in node.get("slots") or []:
                    slot_id = str(slot["uuid"])
                    self.slots_by_id[slot_id] = slot
                    self.slots_by_node.setdefault(node_id, []).append(slot)
                    visit(slot.get("filhos") or [], slot_id)

                visit(node.get("filhos") or [], node_id)

        visit(self.normalized_document.get("nos") or [], None)

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self.nodes_by_id.get(str(node_id))

    def get_ast_node(self, node_id: str) -> DialogNode | None:
        return self.universal_doc.get_node(node_id)

    def get_parent(self, node_id: str) -> str | None:
        return self.parent_by_id.get(str(node_id))

    def get_children(self, parent_id: str | None) -> list[dict[str, Any]]:
        child_ids = self.children_by_parent.get(parent_id) or []
        return [self.nodes_by_id[cid] for cid in child_ids if cid in self.nodes_by_id]

    def get_slots(self, node_id: str) -> list[dict[str, Any]]:
        return self.slots_by_node.get(str(node_id)) or []

    def get_roots(self) -> list[dict[str, Any]]:
        return [self.nodes_by_id[rid] for rid in self.roots if rid in self.nodes_by_id]

    def get_folders(self) -> list[dict[str, Any]]:
        return [self.nodes_by_id[fid] for fid in self.folders if fid in self.nodes_by_id]

    def get_ancestors(self, node_id: str) -> list[dict[str, Any]]:
        ancestors: list[dict[str, Any]] = []
        current = self.get_parent(node_id)
        while current is not None:
            if current in self.nodes_by_id:
                ancestors.append(self.nodes_by_id[current])
            elif current in self.slots_by_id:
                ancestors.append(self.slots_by_id[current])
            current = self.parent_by_id.get(current)
        ancestors.reverse()
        return ancestors

    def iter_all_nodes(self) -> Iterator[dict[str, Any]]:
        yield from self.nodes_by_id.values()

    def iter_all_slots(self) -> Iterator[dict[str, Any]]:
        yield from self.slots_by_id.values()

    def summary(self) -> dict[str, Any]:
        return {
            "total_nodes": len(self.nodes_by_id),
            "root_nodes": len(self.roots),
            "folders": len(self.folders),
            "slots": len(self.slots_by_id),
            "format_detected": self.universal_doc.format_detected,
        }
