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
MUTANTS = (
    (DIFF_SOURCE, "WATSON_DIALOG_DIFF_PATH", "timestamps_are_not_ignored", 'DEFAULT_IGNORED_FIELDS = {"dataCriacao", "dataModificacao"}', "DEFAULT_IGNORED_FIELDS = set()"),
    (DIFF_SOURCE, "WATSON_DIALOG_DIFF_PATH", "uuid_matching_is_disabled", 'return {str(item["uuid"]): item for item in value}', "return None"),
    (DIFF_SOURCE, "WATSON_DIALOG_DIFF_PATH", "embedded_json_is_not_decoded", 'path.rsplit(".", 1)[-1] == "json"', 'path.rsplit(".", 1)[-1] == "not_json"'),
    (DIFF_SOURCE, "WATSON_DIALOG_DIFF_PATH", "tag_order_is_considered", 'if path.rsplit(".", 1)[-1] == "tags":', "if False:"),
    (DIFF_SOURCE, "WATSON_DIALOG_DIFF_PATH", "cli_never_signals_a_diff", 'return 1 if report["changes"] else 0', "return 0"),
    (GRAPH_SOURCE, "WATSON_DIALOG_GRAPH_PATH", "slot_child_type_is_lost", 'kind = "slot_child" if node.get("uuidSlot") else "dialog_node"', 'kind = "dialog_node"'),
    (GRAPH_SOURCE, "WATSON_DIALOG_GRAPH_PATH", "slot_edge_type_is_lost", 'add_edge(node_id, slot_id, "contains_slot")', 'add_edge(node_id, slot_id, "contains")'),
    (GRAPH_SOURCE, "WATSON_DIALOG_GRAPH_PATH", "jump_edge_type_is_lost", 'add_edge(node_id, target, "jump")', 'add_edge(node_id, target, "contains")'),
    (GRAPH_SOURCE, "WATSON_DIALOG_GRAPH_PATH", "sibling_order_edge_is_lost", 'add_edge(str(node["uuid"]), str(target["uuid"]), "next_evaluation")', 'add_edge(str(node["uuid"]), str(target["uuid"]), "contains")'),
)


def main() -> int:
    killed = 0
    for source_path, environment_key, name, original, replacement in MUTANTS:
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
    print(f"Mutation score: {killed}/{len(MUTANTS)} mutantes detectados")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
