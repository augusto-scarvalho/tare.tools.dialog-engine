"""Run targeted mutation tests without requiring a third-party mutation tool."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIFF_SOURCE = ROOT / "watson_dialog_diff.py"
GRAPH_SOURCE = ROOT / "watson_dialog_graph.py"
CONDITIONS_SOURCE = ROOT / "watson_dialog_conditions.py"
SPEL_SOURCE = ROOT / "watson_spel.py"
VALIDATE_SOURCE = ROOT / "watson_dialog_validate.py"
TEST_RUNNER_SOURCE = ROOT / "watson_dialog_test.py"
GENERATE_TEST_SOURCE = ROOT / "watson_dialog_generate_test.py"
DIFF_GENERATE_TEST_SOURCE = ROOT / "watson_dialog_generate_diff_tests.py"
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
    (GRAPH_SOURCE, "WATSON_DIALOG_GRAPH_PATH", "condition_reachability_is_ignored", 'if issue["type"] in {"unsatisfiable_condition", "shadowed_by_always_true"}:', "if False:"),
    (CONDITIONS_SOURCE, "WATSON_DIALOG_CONDITIONS_PATH", "unsatisfiable_conditions_are_ignored", 'if not formula["is_satisfiable"]:', "if False:"),
    (CONDITIONS_SOURCE, "WATSON_DIALOG_CONDITIONS_PATH", "unknown_intents_are_ignored", "if intent not in intents:", "if False:"),
    (CONDITIONS_SOURCE, "WATSON_DIALOG_CONDITIONS_PATH", "always_true_shadowing_is_ignored", "if always_true:", "if False:"),
    (CONDITIONS_SOURCE, "WATSON_DIALOG_CONDITIONS_PATH", "invalid_spel_shorthand_is_ignored", "if INVALID_ENTITY_SHORTHAND_MEMBER.search(condition):", "if False:"),
    (CONDITIONS_SOURCE, "WATSON_DIALOG_CONDITIONS_PATH", "invalid_spel_entity_calls_are_ignored", "if INVALID_ENTITY_CALL.search(condition):", "if False:"),
    (SPEL_SOURCE, "WATSON_SPEL_PATH", "lowercase_method_is_disabled", 'if method == "toLowerCase": return str(value).lower()', 'if method == "toLowerCase": return UNKNOWN'),
    (SPEL_SOURCE, "WATSON_SPEL_PATH", "filter_method_is_disabled", 'return [item for item in value if _truth(evaluate(tree, {**environment, "locals": {**environment.get("locals", {}), variable: item}})) is True]', "return []"),
    (SPEL_SOURCE, "WATSON_SPEL_PATH", "intent_matching_is_disabled", 'return any(item.get("intent", item.get("name")) == name[1:] for item in intents)', "return False"),
    (VALIDATE_SOURCE, "WATSON_DIALOG_VALIDATE_PATH", "unresolved_jumps_are_ignored", 'if target not in (None, "") and str(target) not in node_ids | {"root"}:', "if False:"),
    (VALIDATE_SOURCE, "WATSON_DIALOG_VALIDATE_PATH", "spel_syntax_diagnostics_are_ignored", "for diagnostic in syntax_diagnostics(condition):", "for diagnostic in []:"),
    (VALIDATE_SOURCE, "WATSON_DIALOG_VALIDATE_PATH", "condition_length_limit_is_ignored", "if len(condition) > MAX_CONDITION_LENGTH:", "if False:"),
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


def main() -> int:
    start = int(os.environ.get("MUTATION_START", "0"))
    end = int(os.environ.get("MUTATION_END", str(len(MUTANTS))))
    mutants = MUTANTS[start:end]
    killed = 0
    for source_path, environment_key, name, original, replacement in mutants:
        source = source_path.read_text(encoding="utf-8")
        if original not in source:
            print(f"ERRO {name}: alvo da mutação não encontrado")
            return 2
        with tempfile.TemporaryDirectory() as directory:
            mutant = Path(directory) / source_path.name
            mutant.write_text(source.replace(original, replacement, 1), encoding="utf-8")
            environment = {**os.environ, environment_key: str(mutant)}
            result = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
        if result.returncode:
            killed += 1
            print(f"KILLED  {name}")
        else:
            print(f"SURVIVED {name}")
    print(f"Mutation score: {killed}/{len(mutants)} mutantes detectados")
    return 0 if killed == len(mutants) else 1


if __name__ == "__main__":
    raise SystemExit(main())
