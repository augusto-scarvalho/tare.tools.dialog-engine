"""Universal CLI for tare.tools Dialog Engine with Rich Terminal UI."""

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

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from tare_dialog.diff_engine import (
    DEFAULT_IGNORED_FIELDS,
    configure_utf8_output,
    load_json,
    markdown,
    summarize,
)
from tare_dialog.explorer import (
    explore_document,
    introspect_primitives,
    to_nested_format,
    to_v1_format,
)
from tare_dialog.graph import build_graph, render_dot
from tare_dialog.mutator import DialogTreeMutator, calculate_mutation_score
from tare_dialog.rule_mutator import (
    evaluate_rules_against_scenarios,
    generate_audit_manifest,
    synthesize_counterexample_scenario,
)
from tare_dialog.test_runner import run_scenario
from tare_dialog.validator import validate


def render_rich_diff(report: dict, console: Console) -> None:
    summary = report.get("summary", {})
    t = Table(title="[bold cyan]tare.tools — Semantic AST Diff[/bold cyan]", show_header=True, header_style="bold magenta")
    t.add_column("Category", style="cyan")
    t.add_column("Added", justify="right", style="green")
    t.add_column("Removed", justify="right", style="red")
    t.add_column("Changed", justify="right", style="yellow")

    t.add_row("Total Changes", str(summary.get("added", 0)), str(summary.get("removed", 0)), str(summary.get("changed", 0)))
    console.print(t)


def render_rich_validation(report: dict, console: Console) -> None:
    summary = report.get("summary", {})
    total = summary.get("issues", 0)

    table = Table(title=f"[bold]tare.tools — Validation Report ({total} issues)[/bold]", header_style="bold blue")
    table.add_column("Severity", style="bold")
    table.add_column("Code", style="cyan")
    table.add_column("Node ID", style="magenta")
    table.add_column("Message", style="white")

    for iss in report.get("issues", [])[:25]:
        sev = iss.get("severity", "info")
        color = "red" if sev == "error" else ("yellow" if sev == "warning" else "blue")
        table.add_row(f"[{color}]{sev.upper()}[/{color}]", iss.get("code", ""), str(iss.get("node", "")), iss.get("message", ""))

    console.print(table)
    if total > 25:
        console.print(f"[dim]... e mais {total - 25} issues; use --max-issues para exibir mais.[/dim]")


def main() -> None:
    configure_utf8_output()
    console = Console() if HAS_RICH else None

    parser = argparse.ArgumentParser(
        prog="dialog-engine",
        description="tare.tools Dialog Engine — High-Performance Conversational AST, Diff & Validation."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 1. Diff
    diff_parser = subparsers.add_parser("diff", help="Semantic AST diff between two dialog versions")
    diff_parser.add_argument("current", type=Path, help="Current/Baseline dialog JSON")
    diff_parser.add_argument("candidate", type=Path, help="Candidate/Modified dialog JSON")
    diff_parser.add_argument("--format", choices=["markdown", "json", "rich"], default="markdown", help="Report format")
    diff_parser.add_argument("--output", "-o", type=Path, help="Output destination file")
    diff_parser.add_argument("--summary-only", action="store_true", help="Emit high-signal summary counts only")
    diff_parser.add_argument("--max-changes", type=int, default=20, help="Max changes to show per item in Markdown")

    # 2. Validate
    val_parser = subparsers.add_parser("validate", help="Validate dialog with single issue contract")
    val_parser.add_argument("document", type=Path, help="Target dialog JSON to validate")
    val_parser.add_argument("--output", "-o", type=Path, help="Output JSON report file")
    val_parser.add_argument("--summary-only", action="store_true", help="Emit high-signal issue summary only")
    val_parser.add_argument("--rich", action="store_true", help="Render rich terminal tables")

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

    # 6. Mutate (Symbolic AST & Automata Mutation Analysis)
    mut_parser = subparsers.add_parser("mutate", help="Symbolic AST and automata mutation testing analysis")
    mut_parser.add_argument("document", type=Path, help="Target dialog JSON document to mutate and analyze")
    mut_parser.add_argument("--output-dir", type=Path, help="Optional directory to save generated mutant JSON variants")

    # 7. Audit Rules (Semantic Business Rule Mutation & Test Gap Auditor)
    audit_parser = subparsers.add_parser("audit-rules", help="Audit conversational test suite against business rule mutations")
    audit_parser.add_argument("document", type=Path, help="Target dialog JSON document")
    audit_parser.add_argument("--scenarios", "-s", type=Path, required=True, help="Test scenarios JSON file or directory")
    audit_parser.add_argument("--audit-out", "-o", type=Path, help="Optional output JSON audit manifest")
    audit_parser.add_argument("--synthesize-gaps", action="store_true", help="Synthesize gap test scenarios for surviving mutants")
    audit_parser.add_argument("--gaps-out-dir", type=Path, help="Directory to save synthesized gap scenarios")

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
            elif args.format == "rich" and HAS_RICH and console:
                render_rich_diff(report, console)
                return
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
            if args.rich and HAS_RICH and console:
                render_rich_validation(report, console)
                return
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
                if HAS_RICH and console:
                    table = Table(title=f"Discovered Channels ({len(intro['discovered_channels'])})", header_style="bold green")
                    table.add_column("Channel Name", style="cyan")
                    for ch in intro["discovered_channels"]:
                        table.add_row(ch)
                    console.print(table)
                else:
                    print(f"=== Discovered Channels ({len(intro['discovered_channels'])}) ===")
                    for ch in intro["discovered_channels"]:
                        print(f" - {ch}")
            elif args.multimedia:
                doc = explore_document(raw_doc)
                if HAS_RICH and console:
                    table = Table(title="Multimedia & Rich Responses", header_style="bold magenta")
                    table.add_column("Node ID", style="cyan")
                    table.add_column("Channel", style="blue")
                    table.add_column("Type", style="yellow")
                    table.add_column("Title / Details", style="white")
                    for node in doc.iter_nodes():
                        for resp in node.responses:
                            if resp.response_type != "text" or resp.media_urls or resp.options:
                                table.add_row(node.id, resp.channel, resp.response_type.upper(), f"title='{resp.title}' media={resp.media_urls}")
                    console.print(table)
                else:
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
                if HAS_RICH and console:
                    panel_text = f"""[bold cyan]Format Detected:[/bold cyan]      {intro['format_detected']}
[bold cyan]Total Dialog Nodes:[/bold cyan]   {intro['total_nodes']} (Root: {intro['root_nodes']})
[bold cyan]Intents Catalog:[/bold cyan]      {intro['intents_count']}
[bold cyan]Entities Catalog:[/bold cyan]     {intro['entities_count']}
[bold cyan]SpEL Conditions:[/bold cyan]      {intro['conditions_count']}
[bold cyan]Slots Configured:[/bold cyan]     {intro['has_slots']}
[bold cyan]Jumps Configured:[/bold cyan]     {intro['has_jumps']}
[bold cyan]Multimedia Assets:[/bold cyan]    {intro['has_multimedia']}
[bold cyan]Discovered Channels:[/bold cyan]  {', '.join(intro['discovered_channels'])}
[bold cyan]Response Components:[/bold cyan]  {', '.join(intro['discovered_response_types'])}
[bold cyan]Custom Tags Found:[/bold cyan]    {intro['tags_count']} {intro['tags']}"""
                    console.print(Panel(panel_text, title="[bold magenta]tare.tools — Dialog AST Explorer[/bold magenta]", expand=False))
                else:
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

        elif args.command == "mutate":
            doc = load_json(args.document)
            mutator = DialogTreeMutator()
            mutants = mutator.generate_all_mutants(doc)
            score_rep = calculate_mutation_score(doc, validate)

            if args.output_dir:
                args.output_dir.mkdir(parents=True, exist_ok=True)
                for i, m in enumerate(mutants):
                    m_file = args.output_dir / f"mutant_{i+1:02d}_{m.mutator_name}.json"
                    m_file.write_text(json.dumps(m.mutated_tree, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"Saved {len(mutants)} mutant variants to: {args.output_dir}")

            if HAS_RICH and console:
                table = Table(title="[bold]tare.tools — Symbolic AST & Automata Mutation Analysis[/bold]", header_style="bold magenta")
                table.add_column("Mutator", style="cyan")
                table.add_column("Type", style="yellow")
                table.add_column("Expected Code / Guard", style="blue")
                table.add_column("Validation Outcome", style="bold")

                for m in mutants:
                    if m.expected_issue_code is None:
                        outcome = "[bold green]METAMORPHIC PASS (0 SPURIOUS ISSUES)[/bold green]"
                        table.add_row(m.mutator_name, "Neutral Metamorphic", "(None)", outcome)
                    else:
                        rep = validate(m.mutated_tree)
                        detected = {iss.get("code") for iss in rep.get("issues", [])}
                        is_killed = any(m.expected_issue_code == code or m.expected_issue_code in str(code) for code in detected)
                        outcome = "[bold green]KILLED (DETECTED)[/bold green]" if is_killed else "[bold red]SURVIVED (MISSED)[/bold red]"
                        table.add_row(m.mutator_name, "Adversarial Fault", m.expected_issue_code, outcome)
                console.print(table)

                score_val = score_rep["mutation_score_pct"]
                score_color = "green" if score_val == 100.0 else "yellow"
                summary_panel = f"""[bold cyan]Total Mutants Generated:[/bold cyan] {score_rep['total_mutants']}
[bold cyan]Adversarial Injections:[/bold cyan]  {score_rep['adversarial_mutants']}
[bold cyan]Mutants Killed (Caught):[/bold cyan]  {score_rep['killed_mutants']}
[bold cyan]Mutants Survived (Miss):[/bold cyan]  {score_rep['survived_mutants']}
[bold cyan]Metamorphic Neutral Pass:[/bold cyan] {score_rep['metamorphic_neutral_passed']}
[bold {score_color}]Mutation Score (Kill Rate): {score_val}%[/bold {score_color}]"""
                console.print(Panel(summary_panel, title="[bold green]Mutation Quality Verification[/bold green]", expand=False))
            else:
                print(json.dumps(score_rep, indent=2, ensure_ascii=False))

        elif args.command == "audit-rules":
            doc = load_json(args.document)
            raw_scen = json.loads(args.scenarios.read_text(encoding="utf-8"))
            if isinstance(raw_scen, dict) and "scenarios" in raw_scen:
                scenarios = raw_scen["scenarios"]
            elif isinstance(raw_scen, list):
                scenarios = raw_scen
            else:
                scenarios = [raw_scen]

            report = evaluate_rules_against_scenarios(doc, scenarios)
            manifest = generate_audit_manifest(report)

            if args.audit_out:
                args.audit_out.parent.mkdir(parents=True, exist_ok=True)
                args.audit_out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"Audit manifest written to: {args.audit_out}")

            if args.synthesize_gaps and args.gaps_out_dir:
                args.gaps_out_dir.mkdir(parents=True, exist_ok=True)
                for m in report.get("_mutants_obj", []):
                    if m.status == "SURVIVED_BLINDSPOT":
                        synth = synthesize_counterexample_scenario(m)
                        f_name = args.gaps_out_dir / f"gap_{m.mutation_id.lower()}.json"
                        f_name.write_text(json.dumps(synth, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"Synthesized {report['summary']['survived_blindspots']} gap test scenarios to: {args.gaps_out_dir}")

            if HAS_RICH and console:
                table = Table(title="[bold]tare.tools — Business Rule Mutation & Test Gap Audit[/bold]", header_style="bold cyan")
                table.add_column("ID", style="dim")
                table.add_column("Risk Tier", style="bold")
                table.add_column("Node ID", style="cyan")
                table.add_column("Operator", style="yellow")
                table.add_column("Rule Mutation", style="white")
                table.add_column("Test Coverage Status", style="bold")

                for m in report.get("mutations", []):
                    tier = m.get("risk_tier")
                    t_color = "red" if tier == "SECURITY_CRITICAL" else ("yellow" if tier == "BUSINESS_FINANCIAL" else "blue")
                    status = m.get("status")
                    s_text = "[bold green]PROTECTED (KILLED)[/bold green]" if status == "KILLED" else "[bold red]BLINDSPOT (SURVIVED)[/bold red]"
                    table.add_row(
                        m.get("mutation_id"),
                        f"[{t_color}]{tier}[/{t_color}]",
                        m.get("node_id"),
                        m.get("operator"),
                        f"{m.get('original_expression')} -> {m.get('mutated_expression')}",
                        s_text,
                    )
                console.print(table)

                summary = report.get("summary", {})
                score = summary.get("test_mutation_score_pct", 0.0)
                s_color = "green" if score >= 80 else ("yellow" if score >= 50 else "red")
                panel_text = f"""[bold cyan]Total Business Rules Mutated:[/bold cyan] {summary.get('total_mutations')}
[bold cyan]Protected by Existing Tests:[/bold cyan]  {summary.get('killed_by_tests')}
[bold red]Uncovered Test Blindspots:[/bold red]    {summary.get('survived_blindspots')}
[bold {s_color}]Conversational Mutation Score: {score}%[/bold {s_color}]"""
                console.print(Panel(panel_text, title="[bold]Test Suite Health & Protection Rating[/bold]", expand=False))
            else:
                print(json.dumps(manifest, indent=2, ensure_ascii=False))

    except Exception as err:
        sys.stderr.write(f"Error: {err}\n")
        sys.exit(1)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    raise SystemExit(main())
