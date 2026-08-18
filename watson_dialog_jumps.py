#!/usr/bin/env python3
"""List the dialog nodes that jump to a given Watson Dialog UUID."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterator

from watson_dialog_diff import DEFAULT_MAX_INPUT_BYTES, configure_utf8_output, load_json


def iter_nodes(document: dict[str, Any]) -> Iterator[dict[str, Any]]:
    def visit(nodes: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        for node in nodes:
            yield node
            for slot in node.get("slots") or []:
                yield from visit(slot.get("filhos") or [])
            yield from visit(node.get("filhos") or [])
    yield from visit(document.get("nos") or [])


def incoming_jumps(document: dict[str, Any], target: str) -> dict[str, Any]:
    sources = [
        {
            "node": str(node["uuid"]),
            "name": node.get("nome"),
            "condition": node.get("condicao"),
            "jump_selector": node.get("jumpSelector"),
        }
        for node in iter_nodes(document)
        if str(node.get("uuidEnviarPara") or "") == target
    ]
    sources.sort(key=lambda item: (str(item["name"] or ""), item["node"]))
    return {"schema_version": 1, "target": target, "summary": {"incoming_jumps": len(sources)}, "sources": sources}


def main() -> int:
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Lista os nós que fazem jump para um UUID do Watson Dialog.")
    parser.add_argument("dialog", type=Path)
    parser.add_argument("target", help="UUID de destino")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-input-bytes", type=int, default=None, help="limite máximo em bytes; padrão: WATSON_DIALOG_MAX_BYTES ou 50 MiB")
    args = parser.parse_args()
    try:
        report = incoming_jumps(load_json(args.dialog, max_bytes=args.max_input_bytes), args.target)
    except ValueError as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
