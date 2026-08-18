#!/usr/bin/env python3
"""Build pipeline for tare.tools.dialog-engine distributions.

Produces two distinct distributions:
1. Modular Full Package (Standard development, CI/CD, and CLI tooling).
2. Ephemeral Standalone Distribution (Single-file .py and .pyz ZipApp for ChatGPT ADA & M365 Copilot runtime).
"""

from __future__ import annotations

import re
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src" / "tare_dialog"
DIST_DIR = ROOT / "dist"

CORE_MODULES = [
    "resources.py",
    "spel.py",
    "conditions.py",
    "test_runner.py",
    "graph.py",
    "validator.py",
    "diff_engine.py",
    "explorer.py",
    "schema_adapter.py",
    "mutator.py",
    "rule_mutator.py",
]

HEADER = """#!/usr/bin/env python3
# -*- coding: utf-8 -*-
\"\"\"
tare.tools — Dialog Engine (Ephemeral Standalone Distribution)

A single-file, zero-dependency, pure Python stdlib bundle engineered for:
- ChatGPT Code Interpreter / Advanced Data Analysis (ADA) sandboxes
- Microsoft 365 Copilot Studio & Agent Sandboxes
- Serverless ephemeral runtimes and offline analysis

Capabilities:
- AST Semantic Diff Engine & Provenance Analysis
- Spring Expression Language (SpEL) AST Lexer & Safe Evaluator
- Static Validation & 12-Phase Quality Gates
- Topological Flow Graph & Reachability Analyzer
- Deterministic Scenario Runner & Regression Tracing
- Universal Dialog AST Explorer (Official Watson V1 & Enterprise Nested)

License: Apache-2.0
Copyright (c) 2026 Augusto Carvalho and tare.tools contributors.
\"\"\"

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterator, NamedTuple

"""

MAIN_CLI = """

# ==============================================================================
# Unified CLI Dispatcher for Ephemeral Sandboxes
# ==============================================================================

def main_cli() -> None:
    configure_utf8_output()
    parser = argparse.ArgumentParser(
        prog="dialog_engine",
        description="tare.tools Dialog Engine — Standalone Ephemeral Runner for ChatGPT ADA and M365 Copilot."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available engine commands")

    # 1. Diff
    diff_parser = subparsers.add_parser("diff", help="Semantic AST diff between two dialog versions")
    diff_parser.add_argument("current", type=Path, help="Current/Baseline dialog JSON")
    diff_parser.add_argument("candidate", type=Path, help="Candidate/Modified dialog JSON")
    diff_parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Report format")
    diff_parser.add_argument("--output", "-o", type=Path, help="Output destination file")
    diff_parser.add_argument("--summary-only", action="store_true", help="Emit high-signal summary counts only")
    diff_parser.add_argument("--max-changes", type=int, default=20, help="Maximum changes to print per item in Markdown")

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
            if args.format == "json":
                out = json.dumps(report, indent=2, ensure_ascii=False)
            else:
                out = markdown(report, args.max_changes)
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
                print(f"  tare.tools — Dialog AST Explorer (Ephemeral Standalone)")
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
        sys.stderr.write(f"Error: {err}\\n")
        sys.exit(1)


if __name__ == "__main__":
    main_cli()
"""


def clean_module_code(content: str) -> str:
    """Strip __future__, file headers, duplicate imports, and __main__ blocks."""
    lines = content.splitlines()
    cleaned: list[str] = []
    in_main_block = False
    in_internal_import = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#!/usr/bin/env") or stripped.startswith("# -*- coding:"):
            continue
        if stripped.startswith("from __future__ import"):
            continue
        if "_src_dir = str(Path(__file__)" in stripped or "if _src_dir not in sys.path:" in stripped or "sys.path.insert(0, _src_dir)" in stripped or "Ensure src/ is on sys.path" in stripped:
            continue
        if in_internal_import:
            if ")" in stripped or not (line.startswith(" ") or line.startswith("\t")):
                in_internal_import = False
            continue
        if re.match(r"^from (watson_\w+|tare_dialog\.\w+) import", stripped) or re.match(r"^import (watson_\w+|tare_dialog\.\w+)", stripped):
            if "(" in stripped and ")" not in stripped:
                in_internal_import = True
            continue
        if stripped == 'if __name__ == "__main__":':
            in_main_block = True
            continue
        if in_main_block:
            # Skip everything inside if __name__ == "__main__" block
            if line and not line.startswith("    ") and not line.startswith("\t"):
                in_main_block = False
            else:
                continue
        cleaned.append(line)
    return "\n".join(cleaned)


def build_standalone_script() -> Path:
    """Combine all core engine modules into a single monolithic Python file."""
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    out_file = DIST_DIR / "dialog_engine_standalone.py"

    sections = [HEADER]
    for mod_name in CORE_MODULES:
        mod_path = SRC_DIR / mod_name
        if not mod_path.exists():
            raise FileNotFoundError(f"Missing core module: {mod_path}")
        print(f"Bundling module: {mod_name}...")
        raw = mod_path.read_text(encoding="utf-8")
        cleaned = clean_module_code(raw)
        sections.append(f"\n# ------------------------------------------------------------------------------\n# Module: {mod_name}\n# ------------------------------------------------------------------------------\n")
        sections.append(cleaned)

    sections.append(MAIN_CLI)
    full_content = "\n".join(sections)
    out_file.write_text(full_content, encoding="utf-8")
    print(f"Standalone distribution created: {out_file} ({len(full_content.encode('utf-8')):,} bytes)")
    return out_file


def build_zipapp_distribution(standalone_script: Path) -> Path:
    """Package standalone script as a standard Python .pyz zipapp."""
    app_dir = DIST_DIR / "_zipapp_staging"
    app_dir.mkdir(parents=True, exist_ok=True)

    # Copy as __main__.py
    (app_dir / "__main__.py").write_text(standalone_script.read_text(encoding="utf-8"), encoding="utf-8")

    pyz_file = DIST_DIR / "dialog_engine.pyz"
    zipapp.create_archive(
        source=app_dir,
        target=pyz_file,
        interpreter="/usr/bin/env python3",
        compressed=True,
    )

    # Clean staging
    import shutil
    shutil.rmtree(app_dir, ignore_errors=True)
    print(f"ZipApp distribution created: {pyz_file} ({pyz_file.stat().st_size:,} bytes)")
    return pyz_file


def main() -> None:
    print("=================================================================")
    print("  Building tare.tools.dialog-engine Distributions")
    print("=================================================================")
    standalone = build_standalone_script()
    pyz = build_zipapp_distribution(standalone)
    print("=================================================================")
    print("Distributions build complete!")
    print(f"1. Standalone Single-File (ChatGPT ADA / Copilot): {standalone}")
    print(f"2. Portable ZipApp Executable:                     {pyz}")
    print("=================================================================")


if __name__ == "__main__":
    main()
