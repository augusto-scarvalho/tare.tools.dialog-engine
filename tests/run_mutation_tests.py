"""Run targeted mutation tests without requiring a third-party mutation tool."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tare_dialog.diff_engine import configure_utf8_output
from tare_dialog.resources import ResourceBudget, resolve_jobs
DIFF_SOURCE = ROOT / "src/tare_dialog/diff_engine.py"
GRAPH_SOURCE = ROOT / "src/tare_dialog/graph.py"
CONDITIONS_SOURCE = ROOT / "src/tare_dialog/conditions.py"
SPEL_SOURCE = ROOT / "src/tare_dialog/spel.py"
VALIDATE_SOURCE = ROOT / "src/tare_dialog/validator.py"
TEST_RUNNER_SOURCE = ROOT / "src/tare_dialog/test_runner.py"
GENERATE_TEST_SOURCE = ROOT / "src/tare_dialog/generate_test.py"
DIFF_GENERATE_TEST_SOURCE = ROOT / "src/tare_dialog/generate_diff_tests.py"

TARGET_TESTS: dict[Path, str] = {
    DIFF_SOURCE: "tests/test_src/tare_dialog/diff_engine.py",
    GRAPH_SOURCE: "tests/test_src/tare_dialog/graph.py",
    CONDITIONS_SOURCE: "tests/test_src/tare_dialog/conditions.py",
    SPEL_SOURCE: "tests/test_src/tare_dialog/spel.py",
    VALIDATE_SOURCE: "tests/test_src/tare_dialog/validator.py",
    TEST_RUNNER_SOURCE: "tests/test_src/tare_dialog/test_runner.py",
    GENERATE_TEST_SOURCE: "tests/test_src/tare_dialog/generate_test.py",
    DIFF_GENERATE_TEST_SOURCE: "tests/test_src/tare_dialog/generate_diff_tests.py",
}

MUTANTS = (
    (DIFF_SOURCE, "WATSON_DIALOG_DIFF_PATH", "timestamps_are_not_ignored", 'DEFAULT_IGNORED_FIELDS = {"dataCriacao", "dataModificacao"}', "DEFAULT_IGNORED_FIELDS = set()"),
    (DIFF_SOURCE, "WATSON_DIALOG_DIFF_PATH", "uuid_matching_is_disabled", 'return {str(item["uuid"]): item for item in value}', "return None"),
    (DIFF_SOURCE, "WATSON_DIALOG_DIFF_PATH", "embedded_json_is_not_decoded", 'path.rsplit(".", 1)[-1] == "json"', 'path.rsplit(".", 1)[-1] == "not_json"'),
    (DIFF_SOURCE, "WATSON_DIALOG_DIFF_PATH", "tag_order_is_considered", 'if path.rsplit(".", 1)[-1] == "tags":', "if False:"),
    (DIFF_SOURCE, "WATSON_DIALOG_DIFF_PATH", "cli_never_signals_a_diff", 'return 1 if report["changes"] else 0', "return 0"),
    (GRAPH_SOURCE, "WATSON_DIALOG_GRAPH_PATH", "slot_child_type_is_lost", 'kind = "event_handler" if node.get("event_name") else "slot_child" if node.get("uuidSlot") else "dialog_node"', 'kind = "event_handler" if node.get("event_name") else "dialog_node"'),
    (GRAPH_SOURCE, "WATSON_DIALOG_GRAPH_PATH", "slot_edge_type_is_lost", 'add_edge(node_id, slot_id, "contains_slot")', 'add_edge(node_id, slot_id, "contains")'),
    (GRAPH_SOURCE, "WATSON_DIALOG_GRAPH_PATH", "jump_edge_type_is_lost", 'add_edge(node_id, target, "jump")', 'add_edge(node_id, target, "contains")'),
    (GRAPH_SOURCE, "WATSON_DIALOG_GRAPH_PATH", "sibling_order_edge_is_lost", 'add_edge(str(node["uuid"]), str(target["uuid"]), "next_evaluation")', 'add_edge(str(node["uuid"]), str(target["uuid"]), "contains")'),
    (GRAPH_SOURCE, "WATSON_DIALOG_GRAPH_PATH", "condition_reachability_is_ignored", 'if issue["type"] in {"disabled_condition_false", "unsatisfiable_condition", "shadowed_by_always_true"}:', "if False:"),
    (CONDITIONS_SOURCE, "WATSON_DIALOG_CONDITIONS_PATH", "unsatisfiable_conditions_are_ignored", 'if not formula["is_satisfiable"]:', "if False:"),
    (CONDITIONS_SOURCE, "WATSON_DIALOG_CONDITIONS_PATH", "unknown_intents_are_ignored", "if intent not in intents:", "if False:"),
    (CONDITIONS_SOURCE, "WATSON_DIALOG_CONDITIONS_PATH", "always_true_shadowing_is_ignored", "if always_true:", "if False:"),
    (CONDITIONS_SOURCE, "WATSON_DIALOG_CONDITIONS_PATH", "explicit_false_is_misclassified", 'if formula["has_explicit_false"]:', "if False:"),
    (CONDITIONS_SOURCE, "WATSON_DIALOG_CONDITIONS_PATH", "jump_entry_is_ignored_for_shadow", 'if not (interval & jump_targets):\n                    add("shadowed_by_always_true"', 'if True:\n                    add("shadowed_by_always_true"'),
    (CONDITIONS_SOURCE, "WATSON_DIALOG_CONDITIONS_PATH", "revision_status_is_treated_as_operational", 'in {"INATIVO", "REVISAO"}', 'in {"INATIVO"}'),
    (CONDITIONS_SOURCE, "WATSON_DIALOG_CONDITIONS_PATH", "invalid_spel_shorthand_is_ignored", "if INVALID_ENTITY_SHORTHAND_MEMBER.search(condition):", "if False:"),
    (CONDITIONS_SOURCE, "WATSON_DIALOG_CONDITIONS_PATH", "invalid_spel_entity_calls_are_ignored", "if invalid_called_entities:", "if False:"),
    (SPEL_SOURCE, "WATSON_SPEL_PATH", "lowercase_method_is_disabled", 'if method == "toLowerCase": return str(value).lower()', 'if method == "toLowerCase": return UNKNOWN'),
    (SPEL_SOURCE, "WATSON_SPEL_PATH", "filter_method_is_disabled", 'return [item for item in value if _truth(evaluate(tree, {**environment, "locals": {**environment.get("locals", {}), variable: item}})) is True]', "return []"),
    (SPEL_SOURCE, "WATSON_SPEL_PATH", "intent_matching_is_disabled", 'return any(item.get("intent", item.get("name")) == name[1:] for item in intents)', "return False"),
    (SPEL_SOURCE, "WATSON_SPEL_PATH", "template_backslash_is_treated_as_escape", '        if quote:\n            if character == quote:\n                # SpEL string literals escape their delimiter by doubling it', '        if quote:\n            if character == "\\\\":\n                index += 2\n                continue\n            if character == quote:\n                # SpEL string literals escape their delimiter by doubling it'),
    (VALIDATE_SOURCE, "WATSON_DIALOG_VALIDATE_PATH", "unresolved_jumps_are_ignored", 'if target not in (None, "") and str(target) not in node_ids | {"root"}:', "if False:"),
    (VALIDATE_SOURCE, "WATSON_DIALOG_VALIDATE_PATH", "spel_syntax_diagnostics_are_ignored", "for diagnostic in syntax_diagnostics(condition):", "for diagnostic in []:"),
    (VALIDATE_SOURCE, "WATSON_DIALOG_VALIDATE_PATH", "context_spel_diagnostics_are_ignored", "issues.extend(context_spel_issues(document))", "issues.extend([])"),
    (VALIDATE_SOURCE, "WATSON_DIALOG_VALIDATE_PATH", "condition_length_limit_is_ignored", "if len(condition) > MAX_CONDITION_LENGTH:", "if False:"),
    (VALIDATE_SOURCE, "WATSON_DIALOG_VALIDATE_PATH", "same_slot_variable_is_treated_as_later_dependency", 'name != current_name and f"${name}" in condition', 'f"${name}" in condition'),
    (VALIDATE_SOURCE, "WATSON_DIALOG_VALIDATE_PATH", "inactive_forcing_child_blocks_digression", 'if not is_non_operational_status(child)', 'if True'),
    (VALIDATE_SOURCE, "WATSON_DIALOG_VALIDATE_PATH", "zero_handler_diagnostic_is_ignored", 'if any(SYS_NUMBER_ZERO_HANDLER_PATTERN.search(child) for child in children):', 'if False:'),
    (VALIDATE_SOURCE, "WATSON_DIALOG_VALIDATE_PATH", "zero_prompt_range_diagnostic_is_ignored", 'ZERO_IN_PROMPT_RANGE_PATTERN.search(prompt)', 'False'),
    (VALIDATE_SOURCE, "WATSON_DIALOG_VALIDATE_PATH", "document_capture_mismatch_is_ignored", 'if any(DOCUMENT_INPUT_PATTERN.search(child) for child in children):', 'if False:'),
    (VALIDATE_SOURCE, "WATSON_DIALOG_VALIDATE_PATH", "slot_enable_contradiction_is_ignored", 'if enable_condition and slot_enable_is_self_false_contradiction(enable_condition):', 'if False:'),
    (VALIDATE_SOURCE, "WATSON_DIALOG_VALIDATE_PATH", "legacy_order_ambiguity_becomes_warning", '"legacy_order_ambiguous",\n                    "info",', '"legacy_order_ambiguous",\n                    "warning",'),
    (TEST_RUNNER_SOURCE, "WATSON_DIALOG_TEST_PATH", "matching_nodes_are_not_selected", 'if result == "true":', "if False:"),
    (TEST_RUNNER_SOURCE, "WATSON_DIALOG_TEST_PATH", "cursor_is_ignored", "if cursor == ROOT_GROUP:", "if True:"),
    (TEST_RUNNER_SOURCE, "WATSON_DIALOG_TEST_PATH", "v1_stack_list_is_rejected", 'if not isinstance(stack, list) or any(not isinstance(item, dict) or not isinstance(item.get("dialog_node"), str) for item in stack):', "if True:"),
    (TEST_RUNNER_SOURCE, "WATSON_DIALOG_TEST_PATH", "v1_handler_event_order_is_ignored", 'if handler.get("event_name") != event_name:', "if False:"),
    (TEST_RUNNER_SOURCE, "WATSON_DIALOG_TEST_PATH", "digression_return_is_lost", "if not return_from_digression(state, trace, selected):", "if True:"),
    (TEST_RUNNER_SOURCE, "WATSON_DIALOG_TEST_PATH", "nested_digression_returns_fifo", 'state["digression_returns"].pop()', 'state["digression_returns"].pop(0)'),
    (TEST_RUNNER_SOURCE, "WATSON_DIALOG_TEST_PATH", "digression_jump_keeps_returns", 'state["digression_returns"].clear()\n    trace.append({"event": "digression_return_abandoned"', 'pass\n    trace.append({"event": "digression_return_abandoned"'),
    (TEST_RUNNER_SOURCE, "WATSON_DIALOG_TEST_PATH", "callout_effect_is_ignored", 'state["context"].update(context)', "pass"),
    (TEST_RUNNER_SOURCE, "WATSON_DIALOG_TEST_PATH", "node_execution_limit_is_disabled", "if count <= MAX_NODE_EXECUTIONS_PER_TURN:", "if True:"),
    (GENERATE_TEST_SOURCE, "WATSON_DIALOG_GENERATE_TEST_PATH", "topology_children_are_not_generated", 'for child in item.get("children") or []:', "for child in []:"),
    (GENERATE_TEST_SOURCE, "WATSON_DIALOG_GENERATE_TEST_PATH", "topology_slot_prerequisites_are_ignored", 'owner_slots[:target_position + 1]', 'owner_slots[target_position:target_position + 1]'),
    (DIFF_GENERATE_TEST_SOURCE, "WATSON_DIALOG_GENERATE_DIFF_TEST_PATH", "nested_diff_changes_target_the_parent", "for node_id in reversed(path_targets):", "for node_id in []:"),
    (DIFF_GENERATE_TEST_SOURCE, "WATSON_DIALOG_GENERATE_DIFF_TEST_PATH", "removed_diff_changes_are_not_reported", '"missing_from_candidate"', '"covered"'),
)

SMOKE_MUTANT_NAMES = {
    "timestamps_are_not_ignored",
    "slot_child_type_is_lost",
    "unsatisfiable_conditions_are_ignored",
    "lowercase_method_is_disabled",
    "unresolved_jumps_are_ignored",
    "matching_nodes_are_not_selected",
    "topology_children_are_not_generated",
    "nested_diff_changes_target_the_parent",
    "zero_handler_diagnostic_is_ignored",
    "explicit_false_is_misclassified",
}


def extract_killer_test(output: str) -> str | None:
    match = re.search(r"(FAIL|ERROR): ([\w_]+ \([\w_.]+\))", output)
    if match:
        return match.group(2)
    match_short = re.search(r"(FAIL|ERROR): (test_[\w_]+)", output)
    if match_short:
        return match_short.group(2)
    return None


def run_single_mutant(
    source_path: Path,
    environment_key: str,
    name: str,
    original: str,
    replacement: str,
    timeout: float = 10.0,
    full_suite: bool = False,
) -> dict[str, Any]:
    source = source_path.read_text(encoding="utf-8")
    if original not in source:
        return {
            "name": name,
            "module": source_path.name,
            "status": "INVALID_MUTANT",
            "reason": "Alvo da mutação não encontrado no código-fonte",
            "duration_ms": 0,
            "killer": None,
        }

    with tempfile.TemporaryDirectory() as directory:
        mutant = Path(directory) / source_path.name
        mutant.write_text(source.replace(original, replacement, 1), encoding="utf-8")
        environment = {**os.environ, environment_key: str(mutant), "PYTHONUTF8": "1"}

        test_target = TARGET_TESTS.get(source_path)
        if full_suite or not test_target:
            cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"]
        else:
            cmd = [sys.executable, "-m", "unittest", test_target]

        start_time = time.perf_counter()
        try:
            result = subprocess.run(
                cmd,
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        except subprocess.TimeoutExpired:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "name": name,
                "module": source_path.name,
                "status": "TIMEOUT",
                "duration_ms": duration_ms,
                "killer": None,
            }
        except Exception as error:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "name": name,
                "module": source_path.name,
                "status": "HARNESS_ERROR",
                "reason": str(error),
                "duration_ms": duration_ms,
                "killer": None,
            }

    if result.returncode != 0:
        combined_output = f"{result.stdout}\n{result.stderr}"
        killer = extract_killer_test(combined_output)
        return {
            "name": name,
            "module": source_path.name,
            "status": "KILLED",
            "duration_ms": duration_ms,
            "killer": killer,
        }

    # If targeted slice didn't kill it and full suite wasn't run, check full suite before declaring SURVIVED
    if not full_suite:
        return run_single_mutant(
            source_path,
            environment_key,
            name,
            original,
            replacement,
            timeout=timeout,
            full_suite=True,
        )

    return {
        "name": name,
        "module": source_path.name,
        "status": "SURVIVED",
        "duration_ms": duration_ms,
        "killer": None,
    }



def mutant_fingerprint(mutant: tuple[Path, str, str, str, str], full_suite: bool) -> str:
    source_path, environment_key, name, original, replacement = mutant
    digest = hashlib.sha256()
    digest.update(source_path.read_bytes())
    for value in (environment_key, name, original, replacement, str(bool(full_suite))):
        digest.update(b"\0"); digest.update(value.encode("utf-8"))
    return digest.hexdigest()


def load_checkpoint(path: Path, fingerprints: dict[str, str]) -> dict[str, dict[str, Any]]:
    completed: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return completed
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = str(record.get("name") or "")
        if name and record.get("fingerprint") == fingerprints.get(name):
            completed[name] = record
    return completed


def append_checkpoint(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
        file.flush()


def main() -> int:
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Executa mutações comportamentais nos módulos do Watson Dialog Tools.")
    parser.add_argument("--smoke", action="store_true", help="executa apenas subconjunto rápido e representativo de mutantes")
    parser.add_argument("--mutant", type=str, help="executa apenas um mutante específico pelo nome")
    parser.add_argument("--list", action="store_true", help="lista todos os mutantes disponíveis")
    parser.add_argument("--timeout", type=float, default=10.0, help="timeout em segundos por mutante (padrão: 10.0)")
    parser.add_argument("--json", action="store_true", help="imprime o resultado em formato JSON")
    parser.add_argument("--output-json", type=Path, help="grava o resultado detalhado em arquivo JSON")
    parser.add_argument("--checkpoint-jsonl", type=Path, help="append de um registro durável por mutante concluído")
    parser.add_argument("--resume", action="store_true", help="reaproveita resultados válidos de --checkpoint-jsonl")
    parser.add_argument("--jobs", default="auto", help="concorrência: auto ou inteiro positivo")
    parser.add_argument("--budget-seconds", type=float, help="não inicia novos mutantes após este budget de wall time")
    parser.add_argument("--full-suite", action="store_true", help="sempre executa descoberta completa de testes por mutante")
    args = parser.parse_args()

    if args.resume and not args.checkpoint_jsonl:
        parser.error("--resume requer --checkpoint-jsonl")
    if args.budget_seconds is not None and args.budget_seconds <= 0:
        parser.error("--budget-seconds deve ser positivo")

    if args.list:
        print("Mutantes disponíveis:")
        for source_path, _, name, _, _ in MUTANTS:
            smoke_tag = " [SMOKE]" if name in SMOKE_MUTANT_NAMES else ""
            print(f"- {name:<42} ({source_path.name}){smoke_tag}")
        return 0

    mutants_to_run = list(MUTANTS)
    if args.mutant:
        mutants_to_run = [m for m in mutants_to_run if m[2] == args.mutant]
        if not mutants_to_run:
            print(f"Erro: mutante '{args.mutant}' não encontrado.", file=sys.stderr)
            return 2
    elif args.smoke:
        mutants_to_run = [m for m in mutants_to_run if m[2] in SMOKE_MUTANT_NAMES]
    else:
        start = int(os.environ.get("MUTATION_START", "0"))
        end = int(os.environ.get("MUTATION_END", str(len(MUTANTS))))
        mutants_to_run = mutants_to_run[start:end]

    budget = ResourceBudget.detect()
    try:
        jobs = resolve_jobs(args.jobs, len(mutants_to_run), budget)
    except ValueError as error:
        parser.error(str(error))

    fingerprints = {mutant[2]: mutant_fingerprint(mutant, args.full_suite) for mutant in mutants_to_run}
    completed = load_checkpoint(args.checkpoint_jsonl, fingerprints) if args.resume and args.checkpoint_jsonl else {}
    pending = [mutant for mutant in mutants_to_run if mutant[2] not in completed]
    results_by_name: dict[str, dict[str, Any]] = dict(completed)
    total_start = time.perf_counter()
    budget_exhausted = False

    def execute(mutant: tuple[Path, str, str, str, str]) -> dict[str, Any]:
        source_path, environment_key, name, original, replacement = mutant
        result = run_single_mutant(
            source_path, environment_key, name, original, replacement,
            timeout=args.timeout, full_suite=args.full_suite,
        )
        result["fingerprint"] = fingerprints[name]
        return result

    # Dynamic bounded queue: only keep up to ``jobs`` subprocess-owning tasks
    # active, and stop submitting new work when a wall-time budget is reached.
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs, thread_name_prefix="mutation") as executor:
        iterator = iter(pending)
        in_flight: dict[concurrent.futures.Future[dict[str, Any]], tuple[Path, str, str, str, str]] = {}

        def can_submit() -> bool:
            nonlocal budget_exhausted
            if args.budget_seconds is None:
                return True
            if time.perf_counter() - total_start < args.budget_seconds:
                return True
            budget_exhausted = True
            return False

        while len(in_flight) < jobs and can_submit():
            try:
                mutant = next(iterator)
            except StopIteration:
                break
            in_flight[executor.submit(execute, mutant)] = mutant

        while in_flight:
            done, _ = concurrent.futures.wait(in_flight, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                mutant = in_flight.pop(future)
                name = mutant[2]
                try:
                    result = future.result()
                except Exception as error:
                    result = {
                        "name": name, "module": mutant[0].name, "status": "HARNESS_ERROR",
                        "reason": str(error), "duration_ms": 0, "killer": None,
                        "fingerprint": fingerprints[name],
                    }
                results_by_name[name] = result
                if args.checkpoint_jsonl:
                    append_checkpoint(args.checkpoint_jsonl, result)
                if not args.json:
                    killer_info = f" -> {result['killer']}" if result.get("killer") else ""
                    resume_tag = " [resume]" if name in completed else ""
                    print(f"{result['status']:<14} {name:<42} ({result['duration_ms']:>6.1f}ms){killer_info}{resume_tag}")

            while len(in_flight) < jobs and can_submit():
                try:
                    mutant = next(iterator)
                except StopIteration:
                    break
                in_flight[executor.submit(execute, mutant)] = mutant

    # Preserve canonical mutant order independent of completion order.
    results = [results_by_name[m[2]] for m in mutants_to_run if m[2] in results_by_name]
    deferred = [m[2] for m in mutants_to_run if m[2] not in results_by_name]
    total_duration = round(time.perf_counter() - total_start, 2)
    killed_count = sum(1 for r in results if r["status"] == "KILLED")
    total_count = len(results)
    score = (killed_count / total_count * 100) if total_count > 0 else 0.0

    summary = {
        "selected_mutants": len(mutants_to_run),
        "completed_mutants": total_count,
        "deferred_mutants": deferred,
        "budget_exhausted": budget_exhausted and bool(deferred),
        "jobs": jobs,
        "resources": budget.to_dict(),
        "killed": killed_count,
        "survived": sum(1 for r in results if r["status"] == "SURVIVED"),
        "timeout": sum(1 for r in results if r["status"] == "TIMEOUT"),
        "invalid": sum(1 for r in results if r["status"] == "INVALID_MUTANT"),
        "harness_errors": sum(1 for r in results if r["status"] == "HARNESS_ERROR"),
        "mutation_score_pct": round(score, 2),
        "total_duration_sec": total_duration,
        "results": results,
    }

    if args.output_json:
        args.output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("\nResultado da campanha de mutação:")
        print(f"  Jobs: {jobs}; concluídos: {total_count}/{len(mutants_to_run)} em {total_duration:.2f}s")
        print(f"  Score concluído: {killed_count}/{total_count} ({score:.1f}%)")
        if deferred:
            print(f"  Deferred por budget/interrupção: {len(deferred)}")
        if killed_count < total_count:
            print(f"  Avisos: {total_count - killed_count} mutantes concluídos não eliminados.")

    if deferred:
        return 3
    return 0 if killed_count == total_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
