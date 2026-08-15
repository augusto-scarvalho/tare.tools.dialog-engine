#!/usr/bin/env python3
"""Build a deterministic directed graph from a Watson Assistant Dialog export."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from watson_dialog_diff import load_json


GRAPH_SCHEMA_VERSION = 1


def text(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def response_metadata(item: dict[str, Any]) -> dict[str, Any]:
    responses = item.get("respostas") or []
    return {
        "response_count": len(responses),
        "response_types": sorted({str(response["tipoRespostaNomeJSON"]) for response in responses if response.get("tipoRespostaNomeJSON")}),
        "component_types": sorted({response["idTipoComponente"] for response in responses if response.get("idTipoComponente") is not None}),
        "has_json_configuration": bool(item.get("json")),
    }


def node_metadata(node: dict[str, Any], kind: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "id": str(node["uuid"]),
        "kind": kind,
        "name": text(node.get("nome")),
        "condition": text(node.get("condicao")),
        "sequence": node.get("sequencia"),
        "status": text(node.get("status")),
        "jump_selector": text(node.get("jumpSelector")),
        "multiple_responses": bool(node.get("respostaMultipla")),
        "tags": sorted(str(tag) for tag in (node.get("tags") or [])),
        "digression": {
            "in": bool(node.get("inDigressionIn")),
            "out": bool(node.get("inDigressionOut")),
            "return": bool(node.get("inRetornoDigression")),
            "slot": bool(node.get("inDigressionSlot")),
        },
        **response_metadata(node),
    }
    return {key: value for key, value in metadata.items() if value not in (None, [], {})}


def slot_metadata(slot: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "id": f"slot:{slot['uuid']}",
        "kind": "slot",
        "name": text(slot.get("identificador")),
        "condition": text(slot.get("condicao")),
        "required": bool(slot.get("indicadorObrigatorio")),
        "multiple_responses": bool(slot.get("indicadorRespostaMultipla")),
        "tags": sorted(str(tag) for tag in (slot.get("slotTags") or [])),
        "context_variable_id": text(slot.get("uuidVariavelContexto")),
        **response_metadata(slot),
    }
    return {key: value for key, value in metadata.items() if value not in (None, [], {})}


def sorted_siblings(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(nodes, key=lambda node: (node.get("sequencia") is None, node.get("sequencia", 0), str(node["uuid"])))


def build_graph(document: dict[str, Any]) -> dict[str, Any]:
    """Create a detailed graph whose edges always have node, target, and type."""
    vertices: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    unresolved_jumps: list[dict[str, str]] = []

    def add_edge(node: str, target: str, edge_type: str) -> None:
        edges.append({"node": node, "target": target, "type": edge_type})

    def add_sibling_edges(siblings: list[dict[str, Any]]) -> None:
        ordered = sorted_siblings(siblings)
        for node, target in zip(ordered, ordered[1:]):
            add_edge(str(node["uuid"]), str(target["uuid"]), "next_evaluation")

    def add_node(node: dict[str, Any], parent: str | None, edge_type: str | None) -> None:
        node_id = str(node["uuid"])
        kind = "slot_child" if node.get("uuidSlot") else "dialog_node"
        if node_id in vertices:
            raise ValueError(f"UUID de nó duplicado: {node_id}")
        vertices[node_id] = node_metadata(node, kind)
        if parent and edge_type:
            add_edge(parent, node_id, edge_type)

        for slot in sorted(node.get("slots") or [], key=lambda value: str(value["uuid"])):
            slot_id = f"slot:{slot['uuid']}"
            if slot_id in vertices:
                raise ValueError(f"UUID de slot duplicado: {slot['uuid']}")
            vertices[slot_id] = slot_metadata(slot)
            add_edge(node_id, slot_id, "contains_slot")
            children = slot.get("filhos") or []
            add_sibling_edges(children)
            for child in sorted_siblings(children):
                add_node(child, slot_id, "slot_branch")

        children = node.get("filhos") or []
        add_sibling_edges(children)
        for child in sorted_siblings(children):
            add_node(child, node_id, "contains")

    roots = document.get("nos") or []
    add_sibling_edges(roots)
    for root in sorted_siblings(roots):
        add_node(root, None, None)

    native_nodes: dict[str, dict[str, Any]] = {}

    def index_native(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            native_nodes[str(node["uuid"])] = node
            for slot in node.get("slots") or []:
                index_native(slot.get("filhos") or [])
            index_native(node.get("filhos") or [])

    index_native(roots)
    for node_id in sorted(native_nodes):
        target = text(native_nodes[node_id].get("uuidEnviarPara"))
        if target in vertices:
            if target:
                add_edge(node_id, target, "jump")
        elif target:
            add_edge(node_id, target, "jump")
            unresolved_jumps.append({"node": node_id, "target": target, "type": "jump"})

    ordered_vertices = [vertices[vertex_id] for vertex_id in sorted(vertices)]
    ordered_edges = sorted(edges, key=lambda edge: (edge["node"], edge["target"], edge["type"]))
    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "summary": {
            "vertices": len(ordered_vertices),
            "dialog_nodes": sum(vertex["kind"] != "slot" for vertex in ordered_vertices),
            "slots": sum(vertex["kind"] == "slot" for vertex in ordered_vertices),
            "edges": len(ordered_edges),
            "edges_by_type": {edge_type: sum(edge["type"] == edge_type for edge in ordered_edges) for edge_type in sorted({edge["type"] for edge in ordered_edges})},
            "unresolved_jumps": len(unresolved_jumps),
        },
        "vertices": ordered_vertices,
        "edges": ordered_edges,
        "unresolved_jumps": unresolved_jumps,
    }


def dot(graph: dict[str, Any]) -> str:
    colors = {"dialog_node": "#DCEEFF", "slot_child": "#FFF1CC", "slot": "#E5D8FF"}
    lines = ["digraph watson_dialog {", "  rankdir=LR;", "  node [shape=box, style=rounded, fontname=Arial];"]
    for vertex in graph["vertices"]:
        label = vertex.get("name") or vertex["id"]
        if vertex.get("condition"):
            label += "\\n" + vertex["condition"]
        escaped = label.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        lines.append(f'  "{vertex["id"]}" [label="{escaped}", fillcolor="{colors[vertex["kind"]]}", style="rounded,filled"];')
    for edge in graph["edges"]:
        lines.append(f'  "{edge["node"]}" -> "{edge["target"]}" [label="{edge["type"]}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera um grafo direcionado de um export Watson Assistant Dialog.")
    parser.add_argument("input", type=Path, help="export JSON do Watson Assistant")
    parser.add_argument("--format", choices=("json", "dot"), default="json")
    parser.add_argument("--output", type=Path, help="arquivo de saída; padrão: stdout")
    args = parser.parse_args()
    try:
        graph = build_graph(load_json(args.input))
    except (ValueError, KeyError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    output = json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True) + "\n" if args.format == "json" else dot(graph)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
