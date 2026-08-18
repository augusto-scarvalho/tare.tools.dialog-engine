#!/usr/bin/env python3
"""Build a deterministic directed graph from a Watson Assistant Dialog export."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on sys.path when invoked directly
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)


import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tare_dialog.conditions import analyze_conditions
from tare_dialog.diff_engine import (
    configure_utf8_output,
    load_json,
)
from tare_dialog.test_runner import normalize_document

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
        # `folder` is a first-class legacy Watson Dialog node type. It is not
        # inferred from the presence of children: standard nodes can also have
        # child nodes, while a folder can be empty.
        "folder": bool(node.get("folder")),
        "name": text(node.get("nome")),
        "condition": text(node.get("condicao")),
        "sequence": node.get("sequencia"),
        "status": text(node.get("status")),
        "jump_selector": text(node.get("jumpSelector")),
        "multiple_responses": bool(node.get("respostaMultipla")),
        "has_action": bool(node.get("actions") or node.get("uuidAcao")),
        "has_webhook": bool(node.get("webhook") or node.get("urlWebhook")),
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


def reachability(document: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    """Prove unreachable vertices from conditions and structural graph edges.

    A `body` jump targets a response directly, bypassing the target condition;
    it therefore prevents this static analysis from classifying that target as
    unreachable. Other jump modes do not provide that proof.
    """
    condition_report = analyze_conditions(document)
    direct_reasons: dict[str, list[str]] = {}
    for issue in condition_report["issues"]:
        if issue["type"] in {"disabled_condition_false", "unsatisfiable_condition", "shadowed_by_always_true"}:
            direct_reasons.setdefault(issue["node"], []).append(issue["type"])

    vertices = {vertex["id"]: vertex for vertex in graph["vertices"]}
    direct_body_targets = {
        edge["target"]
        for edge in graph["edges"]
        if edge["type"] == "jump" and vertices.get(edge["node"], {}).get("jump_selector") == "body"
    }
    parents: dict[str, set[str]] = {vertex_id: set() for vertex_id in vertices}
    for edge in graph["edges"]:
        if edge["type"] in {"contains", "contains_slot", "slot_branch"} and edge["target"] in parents:
            parents[edge["target"]].add(edge["node"])

    unreachable: dict[str, list[str]] = {
        node: sorted(reasons)
        for node, reasons in direct_reasons.items()
        if node in vertices and node not in direct_body_targets
    }
    changed = True
    while changed:
        changed = False
        for node in sorted(vertices):
            if node in unreachable or node in direct_body_targets or not parents[node]:
                continue
            if parents[node].issubset(unreachable):
                unreachable[node] = [f"all_structural_parents_unreachable:{parent}" for parent in sorted(parents[node])]
                changed = True

    items = [
        {
            "node": node,
            "kind": vertices[node]["kind"],
            "name": vertices[node].get("name"),
            "condition": vertices[node].get("condition"),
            "reasons": unreachable[node],
        }
        for node in sorted(unreachable)
    ]
    return {
        "summary": {
            "proven_unreachable": len(items),
            "condition_blocks": len(direct_reasons),
            "body_jump_exceptions": len(set(direct_reasons) & direct_body_targets),
        },
        "unreachable": items,
    }


def build_graph(document: dict[str, Any], summary_only: bool = False) -> dict[str, Any]:
    """Create a detailed graph whose edges always have node, target, and type."""
    document = normalize_document(document)
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
        kind = "event_handler" if node.get("event_name") else "slot_child" if node.get("uuidSlot") else "dialog_node"
        if node_id in vertices:
            raise ValueError(f"Duplicate node UUID: {node_id}")
        vertices[node_id] = node_metadata(node, kind)
        if parent and edge_type:
            add_edge(parent, node_id, edge_type)

        for slot in sorted(node.get("slots") or [], key=lambda value: str(value["uuid"])):
            slot_id = f"slot:{slot['uuid']}"
            if slot_id in vertices:
                raise ValueError(f"Duplicate slot UUID: {slot['uuid']}")
            vertices[slot_id] = slot_metadata(slot)
            add_edge(node_id, slot_id, "contains_slot")
            children = slot.get("filhos") or []
            add_sibling_edges(children)
            for child in sorted_siblings(children):
                add_node(child, slot_id, "slot_branch")

        children = node.get("filhos") or []
        add_sibling_edges(children)
        if node.get("folder") and children:
            add_edge(node_id, str(sorted_siblings(children)[0]["uuid"]), "folder_entry")
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
        if target == "root":
            add_edge(node_id, target, "tree_restart")
        elif target in vertices:
            if target:
                add_edge(node_id, target, "jump")
        elif target:
            add_edge(node_id, target, "jump")
            unresolved_jumps.append({"node": node_id, "target": target, "type": "jump"})

    ordered_vertices = [vertices[vertex_id] for vertex_id in sorted(vertices)]
    ordered_edges = sorted(edges, key=lambda edge: (edge["node"], edge["target"], edge["type"]))
    digression_targets = [
        {"node": str(root["uuid"]), "name": text(root.get("nome")), "returns": bool(root.get("inRetornoDigression"))}
        for root in sorted_siblings(roots)
        if root.get("inDigressionIn")
    ]
    graph = {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "summary": {
            "vertices": len(ordered_vertices),
            "dialog_nodes": sum(vertex["kind"] != "slot" for vertex in ordered_vertices),
            "event_handlers": sum(vertex["kind"] == "event_handler" for vertex in ordered_vertices),
            "folders": sum(bool(vertex.get("folder")) for vertex in ordered_vertices),
            "slots": sum(vertex["kind"] == "slot" for vertex in ordered_vertices),
            "callouts": sum(bool(vertex.get("has_action") or vertex.get("has_webhook")) for vertex in ordered_vertices),
            "digression_targets": len(digression_targets),
            "edges": len(ordered_edges),
            "edges_by_type": {edge_type: sum(edge["type"] == edge_type for edge in ordered_edges) for edge_type in sorted({edge["type"] for edge in ordered_edges})},
            "unresolved_jumps": len(unresolved_jumps),
        },
        "vertices": ordered_vertices,
        "edges": ordered_edges,
        "unresolved_jumps": unresolved_jumps,
        "digression_targets": digression_targets,
    }
    graph["reachability"] = reachability(document, graph)
    if summary_only:
        return {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "summary": {
                "vertex_count": len(graph["vertices"]),
                "edge_count": len(graph["edges"]),
                "unresolved_jumps_count": len(graph["unresolved_jumps"]),
                "digression_targets_count": len(graph["digression_targets"]),
                "unreachable_count": len(graph["reachability"].get("unreachable", [])),
            },
            "unresolved_jumps": graph["unresolved_jumps"],
            "reachability": graph["reachability"],
        }
    return graph


def dot(graph: dict[str, Any]) -> str:
    lines = ["digraph WatsonDialog {", "  rankdir=LR;", '  node [fontname="Helvetica", fontsize=10];', '  edge [fontname="Helvetica", fontsize=8];']
    colors = {
        "dialog_node": "#E8F0FE",
        "slot_child": "#FEF7E0",
        "event_handler": "#FCE8E6",
        "slot": "#F1F3F4",
    }
    for vertex in graph.get("vertices", []):
        label = vertex.get("name") or vertex["id"]
        if vertex.get("folder"):
            label = "[folder] " + label
        if vertex.get("condition"):
            label += "\\n" + vertex["condition"]
        escaped = label.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        shape = "folder" if vertex.get("folder") else "box"
        color = "#D7F2DF" if vertex.get("folder") else colors[vertex["kind"]]
        lines.append(f'  "{vertex["id"]}" [label="{escaped}", shape="{shape}", fillcolor="{color}", style="rounded,filled"];')
    for edge in graph.get("edges", []):
        lines.append(f'  "{edge["node"]}" -> "{edge["target"]}" [label="{edge["type"]}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


render_dot = dot


def main() -> int:
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Generates a directed graph from a dialog export.")
    parser.add_argument("input", type=Path, help="JSON dialog export")
    parser.add_argument("--format", choices=("json", "dot"), default="json")
    parser.add_argument("--output", type=Path, help="output file path; default: stdout")
    parser.add_argument("--max-input-bytes", type=int, default=None, help="maximum byte limit; default: WATSON_DIALOG_MAX_BYTES or 50 MiB")
    parser.add_argument("--summary-only", action="store_true", help="emits only consolidated graph counts")
    args = parser.parse_args()
    try:
        graph = build_graph(load_json(args.input, max_bytes=args.max_input_bytes), summary_only=args.summary_only)
    except (ValueError, KeyError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    output = json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True) + "\n" if args.format == "json" else dot(graph)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    import sys
    from pathlib import Path
    raise SystemExit(main())

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    nx = None
    HAS_NETWORKX = False


def to_networkx(graph_dict: dict[str, Any]) -> Any:
    """Convert dialog graph dictionary to a NetworkX DiGraph for advanced graph algorithms."""
    if not HAS_NETWORKX:
        raise ImportError("networkx is required for to_networkx(). Run: pip install networkx")
    G = nx.DiGraph()
    for v in graph_dict.get("vertices", []):
        G.add_node(v["id"], **v)
    for e in graph_dict.get("edges", []):
        G.add_edge(e["node"], e["target"], edge_type=e.get("type"))
    return G


def find_graph_cycles(graph_dict: dict[str, Any]) -> list[list[str]]:
    """Detect circular jump loops using NetworkX cycle detection."""
    if not HAS_NETWORKX:
        return []
    G = to_networkx(graph_dict)
    return list(nx.simple_cycles(G))
