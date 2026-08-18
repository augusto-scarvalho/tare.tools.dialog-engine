"""Universal Schema Discovery, Semantic Binding, and State Machine Adapter for tare.tools.dialog-engine.

Decouples the engine from specific vendor or proprietary JSON key names, allowing
it to navigate, validate, mutate, and diff ANY conversational state machine or dialog
graph by mapping it to canonical Universal AST primitives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class KeyMapping:
    """Configurable semantic property mappings for a state machine node."""
    id_keys: list[str] = field(default_factory=lambda: ["dialog_node", "uuid", "id", "node_id", "name", "key"])
    title_keys: list[str] = field(default_factory=lambda: ["title", "nome", "name", "label", "description"])
    condition_keys: list[str] = field(default_factory=lambda: ["conditions", "condicao", "condition", "guard", "when", "expression"])
    context_keys: list[str] = field(default_factory=lambda: ["context", "contexto", "variables", "state", "variaveisContexto"])
    children_keys: list[str] = field(default_factory=lambda: ["children", "filhos", "subnodes", "branches", "steps"])
    slots_keys: list[str] = field(default_factory=lambda: ["slots", "parameters", "entities_capture", "quadros"])
    responses_keys: list[str] = field(default_factory=lambda: ["output", "respostas", "responses", "messages", "actions"])
    jumps_keys: list[str] = field(default_factory=lambda: ["next_step", "jump_to", "transitions", "target", "goto"])


@dataclass
class SchemaBinding:
    """Semantic adapter that binds arbitrary JSON structures to Universal AST primitives."""
    schema_name: str = "auto_discovered"
    root_nodes_keys: list[str] = field(default_factory=lambda: ["dialog_nodes", "nos", "nodes", "states", "arvoreDialogo", "blocks"])
    mapping: KeyMapping = field(default_factory=KeyMapping)
    confidence_score: float = 1.0
    discovered_alignment: dict[str, str] = field(default_factory=dict)

    # --------------------------------------------------------------------------
    # Field Extractors (Decoupled Accessors)
    # --------------------------------------------------------------------------
    def get_id(self, node: dict[str, Any]) -> str:
        for k in self.mapping.id_keys:
            if k in node and node[k]:
                return str(node[k])
        return ""

    def get_title(self, node: dict[str, Any]) -> str:
        for k in self.mapping.title_keys:
            if k in node and node[k]:
                return str(node[k])
        return self.get_id(node)

    def get_condition(self, node: dict[str, Any]) -> str:
        for k in self.mapping.condition_keys:
            if k in node and node[k] is not None:
                return str(node[k])
        return ""

    def set_condition(self, node: dict[str, Any], new_condition: str) -> None:
        for k in self.mapping.condition_keys:
            if k in node:
                node[k] = new_condition
                return
        # Default fallback to the primary key in the mapping
        node[self.mapping.condition_keys[0]] = new_condition

    def get_context(self, node: dict[str, Any]) -> dict[str, Any]:
        for k in self.mapping.context_keys:
            if k in node and isinstance(node[k], dict):
                return node[k]
        return {}

    def set_context_variable(self, node: dict[str, Any], var_name: str, var_value: Any) -> None:
        for k in self.mapping.context_keys:
            if k in node and isinstance(node[k], dict):
                node[k][var_name] = var_value
                return
        # Initialize context if missing
        primary_key = self.mapping.context_keys[0]
        node[primary_key] = {var_name: var_value}

    def get_children(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        for k in self.mapping.children_keys:
            if k in node and isinstance(node[k], list):
                return [n for n in node[k] if isinstance(n, dict)]
        return []

    def get_slots(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        for k in self.mapping.slots_keys:
            if k in node and isinstance(node[k], list):
                return [s for s in node[k] if isinstance(s, dict)]
        return []

    def get_root_nodes(self, document: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(document, dict):
            return []
        for k in self.root_nodes_keys:
            if k in document and isinstance(document[k], list):
                return [n for n in document[k] if isinstance(n, dict)]
        return []

    # --------------------------------------------------------------------------
    # Universal Traversal & Visitors
    # --------------------------------------------------------------------------
    def iter_all_nodes(self, document: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """Yield every node, slot, and sub-branch across arbitrary state machines."""
        def visit(nodes: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                yield node
                for slot in self.get_slots(node):
                    yield slot
                    yield from visit(self.get_children(slot))
                yield from visit(self.get_children(node))

        roots = self.get_root_nodes(document)
        # If flat list without children nesting (e.g. standard Watson V1 flat list)
        is_flat = any("dialog_node" in n and ("parent" in n or "previous_sibling" in n) for n in roots[:10])
        if is_flat and not any(self.get_children(n) for n in roots[:10]):
            yield from roots
        else:
            yield from visit(roots)

    # --------------------------------------------------------------------------
    # Schema Auto-Discovery Engine
    # --------------------------------------------------------------------------
    @classmethod
    def discover(cls, document: dict[str, Any]) -> SchemaBinding:
        """Inspect document keys and infer semantic binding with confidence scoring."""
        if not isinstance(document, dict):
            return cls(schema_name="invalid", confidence_score=0.0)

        alignment: dict[str, str] = {}
        sample_node: dict[str, Any] = {}

        # 1. Discover root collection
        root_key = "dialog_nodes"
        for k in ["dialog_nodes", "nos", "nodes", "states", "arvoreDialogo", "blocks"]:
            if k in document and isinstance(document[k], list):
                root_key = k
                alignment["root_collection"] = f"{k} -> canonical:roots"
                if document[k] and isinstance(document[k][0], dict):
                    sample_node = document[k][0]
                break

        # 2. Discover node properties from sample
        mapping = KeyMapping()
        score = 0.7 if root_key in ("dialog_nodes", "nos") else 0.5

        if sample_node:
            # Condition key
            for k in mapping.condition_keys:
                if k in sample_node:
                    alignment["condition"] = f"{k} -> canonical:condition"
                    score += 0.1
                    break

            # Context key
            for k in mapping.context_keys:
                if k in sample_node:
                    alignment["context"] = f"{k} -> canonical:context"
                    score += 0.1
                    break

            # Children key
            for k in mapping.children_keys:
                if k in sample_node:
                    alignment["children"] = f"{k} -> canonical:children"
                    score += 0.1
                    break

            # Slots key
            for k in mapping.slots_keys:
                if k in sample_node:
                    alignment["slots"] = f"{k} -> canonical:slots"
                    score += 0.1
                    break

        format_name = "watson_v1_flat" if root_key == "dialog_nodes" else ("enterprise_hierarchical" if root_key == "nos" else f"custom_{root_key}")

        return cls(
            schema_name=format_name,
            root_nodes_keys=[root_key, *[k for k in ["dialog_nodes", "nos", "nodes", "states"] if k != root_key]],
            mapping=mapping,
            confidence_score=min(1.0, score),
            discovered_alignment=alignment,
        )


# Global default binding instance
DEFAULT_BINDING = SchemaBinding()
