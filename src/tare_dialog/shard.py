#!/usr/bin/env python3
"""Plan resource-aware semantic work shards without loading the full dialog JSON."""

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

from tare_dialog.diff_engine import configure_utf8_output
from tare_dialog.external import CompactGraph, DialogSourceIndex
from tare_dialog.resources import ResourceBudget, resolve_jobs


def main() -> int:
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Plans semantic work shards for a dialog export.")
    parser.add_argument("input", type=Path, help="JSON dialog export")
    parser.add_argument("--max-input-bytes", type=int, default=None, help="maximum byte limit; default: WATSON_DIALOG_MAX_BYTES or 50 MiB")
    parser.add_argument("--jobs", default="auto", help="physical workers: auto or positive integer")
    parser.add_argument("--logical-shards", default="auto", help="logical shards: auto or positive integer")
    parser.add_argument("--oversubscription", type=int, default=4, help="logical shards per worker in auto mode (default: 4)")
    parser.add_argument("--tolerance", type=float, default=1.15, help="load tolerance per shard (default: 1.15)")
    parser.add_argument("--summary-only", action="store_true", help="omits the vertex list of each shard")
    parser.add_argument("--output", type=Path, help="JSON output file path; default: stdout")
    args = parser.parse_args()
    if args.oversubscription < 1:
        parser.error("--oversubscription must be at least 1")
    if args.tolerance < 1.0:
        parser.error("--tolerance must be >= 1.0")

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
                raise ValueError("logical-shards must be 'auto' or a positive integer")
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
    import sys
    from pathlib import Path
    raise SystemExit(main())
