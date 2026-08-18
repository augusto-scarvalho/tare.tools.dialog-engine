"""Universal CLI for tare.tools Dialog Engine."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tare_dialog.diff_engine import DEFAULT_IGNORED_FIELDS, configure_utf8_output, load_json, markdown, summarize
from tare_dialog.explorer import explore_document, introspect_primitives, to_nested_format, to_v1_format
from tare_dialog.graph import build_graph, render_dot
from tare_dialog.test_runner import run_scenario
from tare_dialog.validator import validate


def main() -> None:
    configure_utf8_output()
    parser = argparse.ArgumentParser(
        prog="dialog-engine",
        description="tare.tools Dialog Engine — Deterministic AST Diff, SpEL Evaluator & Validator."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 1. Diff
    diff_parser = subparsers.add_parser("diff", help="Semantic AST diff between two dialog versions")
    diff_parser.add_argument("current", type=Path, help="Current/Baseline dialog JSON")
    diff_parser.add_argument("candidate", type=Path, help="Candidate/Modified dialog JSON")
    diff_parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Report format")
    diff_parser.add_argument("--output", "-o", type=Path, help="Output destination file")
    diff_parser.add_argument("--summary-only", action="store_true", help="Emit high-signal summary counts only")
    diff_parser.add_argument("--max-changes", type=int, default=20, help="Max changes to show per item in Markdown")

    # 2. Validate
    val_parser = subparsers.add_parser("validate", help="Validate dialog with single issue contract")
    val_parser.add_argument("document", type=Path, help="Target dialog JSON to validate")
    val_parser.add_argument("--output", "-o", type=Path, help="Output JSON report file")
    val_parser.add_argument("--summary-only", action="store_true", help="Emit high-signal issue summary only")

    # 3. Explore
    exp_parser = subparsers.add_parser("explore", help="Explore dialog primitives, channels, media, and schema")
    exp_parser.add_argument("document", type=Path, help="Target dialog JSON export")
    exp_parser.add_argument("--introspect", action="store_true", default=True, help="Print summary of discovered primitives")
    exp_parser.add_argument("--channels", action="store_true", help="List communication channels")
    exp_parser.add_argument("--multimedia", action="store_true", help="List rich media components")
    exp_parser.add_argument("--ast", action="store_true", help="Output Universal AST JSON")
    exp_parser.add_argument("--convert-to", choices=["v1", "nested"], help="Convert format (v1 or nested)")
    exp_parser.add_argument("--output", "-o", type=Path, help="Output file")

    # 4. Graph
    graph_parser = subparsers.add_parser("graph", help="Generate topological graph and reachability report")
    graph_parser.add_argument("document", type=Path, help="Dialog JSON file")
    graph_parser.add_argument("--output-json", type=Path, help="JSON graph output file")
    graph_parser.add_argument("--output-dot", type=Path, help="DOT graph output file")

    # 5. Test
    test_parser = subparsers.add_parser("test", help="Run deterministic test scenario against dialog")
    test_parser.add_argument("document", type=Path, help="Dialog JSON file")
    test_parser.add_argument("scenario", type=Path, help="Scenario JSON test file")
    test_parser.add_argument("--output", "-o", type=Path, help="Output trace JSON file")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        if args.command == "diff":
            cur_doc = load_json(args.current)
            cand_doc = load_json(args.candidate)
            report = summarize(cur_doc, cand_doc, DEFAULT_IGNORED_FIELDS, summary_only=args.summary_only)
            out = json.dumps(report, indent=2, ensure_ascii=False) if args.format == "json" else markdown(report, args.max_changes)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(out, encoding="utf-8")
                print(f"Diff written to {args.output}")
            else:
                print(out)

        elif args.command == "validate":
            doc = load_json(args.document)
            report = validate(doc)
            out = json.dumps(report, indent=2, ensure_ascii=False)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(out, encoding="utf-8")
                print(f"Validation written to {args.output}")
            else:
                print(out)

        elif args.command == "explore":
            raw_doc = load_json(args.document)
            if args.convert_to:
                doc = explore_document(raw_doc)
                converted = to_v1_format(doc) if args.convert_to == "v1" else to_nested_format(doc)
                out = json.dumps(converted, indent=2, ensure_ascii=False)
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(out, encoding="utf-8")
                    print(f"Converted to {args.convert_to}: {args.output}")
                else:
                    print(out)
            elif args.channels:
                intro = introspect_primitives(raw_doc)
                print(f"=== Discovered Channels ({len(intro['discovered_channels'])}) ===")
                for ch in intro["discovered_channels"]:
                    print(f" - {ch}")
            elif args.multimedia:
                doc = explore_document(raw_doc)
                print("=== Discovered Multimedia & Rich Responses ===")
                for node in doc.iter_nodes():
                    for resp in node.responses:
                        if resp.response_type != "text" or resp.media_urls or resp.options:
                            print(f"[{node.id}] ({resp.channel}) {resp.response_type.upper()}: title='{resp.title}' media={resp.media_urls}")
            elif args.ast:
                doc = explore_document(raw_doc)
                out = json.dumps(doc.to_dict(), indent=2, ensure_ascii=False)
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(out, encoding="utf-8")
                    print(f"AST written to {args.output}")
                else:
                    print(out)
            else:
                intro = introspect_primitives(raw_doc)
                print("=================================================================")
                print("  tare.tools — Dialog AST Explorer & Schema Discovery")
                print("=================================================================")
                print(f"  Format Detected:      {intro['format_detected']}")
                print(f"  Total Dialog Nodes:   {intro['total_nodes']} (Root: {intro['root_nodes']})")
                print(f"  Intents Catalog:      {intro['intents_count']}")
                print(f"  Entities Catalog:     {intro['entities_count']}")
                print(f"  SpEL Conditions:      {intro['conditions_count']}")
                print(f"  Slots Configured:     {intro['has_slots']}")
                print(f"  Jumps Configured:     {intro['has_jumps']}")
                print(f"  Multimedia Assets:    {intro['has_multimedia']}")
                print(f"  Discovered Channels:  {', '.join(intro['discovered_channels'])}")
                print(f"  Response Components:  {', '.join(intro['discovered_response_types'])}")
                print(f"  Custom Tags Found:    {intro['tags_count']} {intro['tags']}")
                print("=================================================================")

        elif args.command == "graph":
            doc = load_json(args.document)
            g = build_graph(doc)
            if args.output_json:
                args.output_json.parent.mkdir(parents=True, exist_ok=True)
                args.output_json.write_text(json.dumps(g, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"Graph JSON written to {args.output_json}")
            if args.output_dot:
                args.output_dot.parent.mkdir(parents=True, exist_ok=True)
                args.output_dot.write_text(render_dot(g), encoding="utf-8")
                print(f"Graph DOT written to {args.output_dot}")
            if not args.output_json and not args.output_dot:
                print(json.dumps(g["summary"], indent=2, ensure_ascii=False))

        elif args.command == "test":
            doc = load_json(args.document)
            scen = load_json(args.scenario)
            result = run_scenario(doc, scen)
            out = json.dumps(result, indent=2, ensure_ascii=False)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(out, encoding="utf-8")
                print(f"Test trace written to {args.output}")
            else:
                print(out)

    except Exception as err:
        sys.stderr.write(f"Error: {err}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
