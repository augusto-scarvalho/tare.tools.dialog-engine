#!/usr/bin/env python3
"""Plan resource-aware semantic work shards without loading the full dialog JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from watson_dialog_diff import configure_utf8_output
from watson_dialog_external import CompactGraph, DialogSourceIndex
from watson_dialog_resources import ResourceBudget, resolve_jobs


def main() -> int:
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Planeja shards semânticos para um export Watson Assistant Dialog.")
    parser.add_argument("input", type=Path, help="export JSON Watson Assistant Dialog")
    parser.add_argument("--max-input-bytes", type=int, default=None, help="limite máximo em bytes; padrão: WATSON_DIALOG_MAX_BYTES ou 50 MiB")
    parser.add_argument("--jobs", default="auto", help="workers físicos: auto ou inteiro positivo")
    parser.add_argument("--logical-shards", default="auto", help="shards lógicos: auto ou inteiro positivo")
    parser.add_argument("--oversubscription", type=int, default=4, help="shards lógicos por worker em modo auto (padrão: 4)")
    parser.add_argument("--tolerance", type=float, default=1.15, help="tolerância de carga por shard (padrão: 1.15)")
    parser.add_argument("--summary-only", action="store_true", help="omite a lista de vertices de cada shard")
    parser.add_argument("--output", type=Path, help="arquivo JSON de saída; padrão: stdout")
    args = parser.parse_args()
    if args.oversubscription < 1:
        parser.error("--oversubscription deve ser pelo menos 1")
    if args.tolerance < 1.0:
        parser.error("--tolerance deve ser >= 1.0")

    try:
        budget = ResourceBudget.detect()
        with DialogSourceIndex.open(args.input, max_bytes=args.max_input_bytes) as source_index:
            graph = CompactGraph.from_index(source_index)
            jobs = resolve_jobs(args.jobs, max(1, len(graph.vertex_ids)), budget)
            if str(args.logical_shards).lower() == "auto":
                logical_shards = budget.logical_shards(jobs, max(1, len(graph.vertex_ids)), args.oversubscription)
            elif str(args.logical_shards).isdigit() and int(args.logical_shards) > 0:
                logical_shards = min(int(args.logical_shards), max(1, len(graph.vertex_ids)))
            else:
                raise ValueError("logical-shards deve ser 'auto' ou inteiro positivo")
            plan = graph.semantic_shards(logical_shards, tolerance=args.tolerance)
            if args.summary_only:
                for shard in plan["shards"]:
                    shard["vertex_count"] = len(shard.pop("vertices"))
            report = {
                "schema_version": 1,
                "source": source_index.summary(),
                "resources": budget.to_dict(),
                "execution": {
                    "jobs": jobs,
                    "logical_shards": logical_shards,
                    "oversubscription": args.oversubscription,
                    "tolerance": args.tolerance,
                },
                "graph": graph.summary(),
                "plan": plan,
            }
    except (OSError, ValueError, KeyError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2

    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
