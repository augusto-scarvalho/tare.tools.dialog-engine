#!/usr/bin/env python3
"""Export parent/child/slot topology around one legacy Watson Dialog UUID."""
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

from tare_dialog.conditions import sorted_siblings
from tare_dialog.diff_engine import DEFAULT_MAX_INPUT_BYTES, configure_utf8_output, load_json


def response_groups(item: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for response in item.get("respostas") or []:
        key = (response.get("idTipoResposta"), response.get("sequenciaBloco"))
        groups.setdefault(key, []).append(response)
    return [{"response_type": key[0], "block": key[1], "components": [{"uuid": str(value.get("uuid")), "component_type": value.get("idTipoComponente"), "channel": value.get("tipoRespostaNomeJSON"), "item": value.get("sequenciaItem")} for value in sorted(values, key=lambda value: (value.get("sequenciaItem", 0), str(value.get("uuid"))))]} for key, values in sorted(groups.items(), key=lambda value: (str(value[0][0]), str(value[0][1])))]


def topology(document: dict[str, Any], target: str) -> dict[str, Any]:
    index: dict[str, tuple[dict[str, Any], str, str | None]] = {}

    def visit_nodes(nodes: list[dict[str, Any]], parent: str | None) -> None:
        for node in sorted_siblings(nodes):
            node_id = str(node["uuid"])
            index[node_id] = (node, "dialog_node" if not node.get("uuidSlot") else "slot_handler", parent)
            for slot in node.get("slots") or []:
                slot_id = str(slot["uuid"])
                index[slot_id] = (slot, "slot", node_id)
                visit_nodes(slot.get("filhos") or [], slot_id)
            visit_nodes(node.get("filhos") or [], node_id)

    visit_nodes(document.get("nos") or [], None)
    if target not in index: raise ValueError(f"UUID não encontrado: {target}")

    def render(item_id: str) -> dict[str, Any]:
        item, kind, _parent = index[item_id]
        data = {"uuid": item_id, "kind": kind, "name": item.get("nome") if kind != "slot" else item.get("identificador"), "condition": item.get("condicao"), "multiple_responses": bool(item.get("respostaMultipla") if kind != "slot" else item.get("indicadorRespostaMultipla")), "response_groups": response_groups(item), "children": [], "slots": []}
        if kind != "slot":
            data["slots"] = [render(str(slot["uuid"])) for slot in item.get("slots") or []]
            data["children"] = [render(str(child["uuid"])) for child in sorted_siblings(item.get("filhos") or [])]
        else:
            data["handlers"] = [render(str(child["uuid"])) for child in sorted_siblings(item.get("filhos") or [])]
            del data["children"]
        return {key: value for key, value in data.items() if value not in (None, [], {})}

    ancestors: list[dict[str, Any]] = []
    current: str | None = target
    while current is not None:
        item, kind, parent = index[current]
        ancestors.append({"uuid": current, "kind": kind, "name": item.get("nome") if kind != "slot" else item.get("identificador")})
        current = parent
    ancestors.reverse()
    return {"schema_version": 1, "target": target, "ancestors": ancestors, "descendants": render(target)}


def main() -> int:
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Gera ancestrais e descendentes estruturais de um nó Watson Dialog.")
    parser.add_argument("dialog", type=Path)
    parser.add_argument("target")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-input-bytes", type=int, default=None, help="limite máximo em bytes; padrão: WATSON_DIALOG_MAX_BYTES ou 50 MiB")
    args = parser.parse_args()
    try:
        result = topology(load_json(args.dialog, max_bytes=args.max_input_bytes), args.target)
    except (ValueError, KeyError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    output = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    import sys
    from pathlib import Path
    raise SystemExit(main())