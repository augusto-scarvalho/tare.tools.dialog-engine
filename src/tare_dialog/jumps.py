#!/usr/bin/env python3
"""List the dialog nodes that jump to a given Watson Dialog UUID."""

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
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from tare_dialog.diff_engine import (
    configure_utf8_output,
    load_json,
)


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
    parser = argparse.ArgumentParser(description="Lists nodes that jump to a target dialog UUID.")
    parser.add_argument("dialog", type=Path)
    parser.add_argument("target", help="target node UUID")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-input-bytes", type=int, default=None, help="maximum byte limit; default: WATSON_DIALOG_MAX_BYTES or 50 MiB")
    args = parser.parse_args()
    try:
        report = incoming_jumps(load_json(args.dialog, max_bytes=args.max_input_bytes), args.target)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    import sys
    from pathlib import Path
    raise SystemExit(main())
