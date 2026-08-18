"""Tests for candidate scenarios generated from semantic Dialog diffs."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = Path(os.environ.get("WATSON_DIALOG_GENERATE_DIFF_TEST_PATH", ROOT / "src/tare_dialog/generate_diff_tests.py"))
SPEC = importlib.util.spec_from_file_location("watson_dialog_generate_diff_tests_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
generator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = generator
SPEC.loader.exec_module(generator)


class GenerateDiffTests(unittest.TestCase):
    def documents(self) -> tuple[dict, dict]:
        current = {
            "nos": [
                {"uuid": "parent", "sequencia": 0, "condicao": "#parent", "tags": ["old"], "respostas": [{"uuid": "reply", "textoResposta": "old"}], "filhos": [
                    {"uuid": "child", "sequencia": 0, "condicao": "#child", "respostas": [], "filhos": []},
                ]},
                {"uuid": "removed", "sequencia": 1, "condicao": "#removed", "respostas": [], "filhos": []},
            ],
            "intencoes": [{"uuid": "intent", "nome": "old-intent"}],
        }
        candidate = {
            "nos": [
                {"uuid": "parent", "sequencia": 0, "condicao": "#parent", "tags": ["new"], "respostas": [{"uuid": "reply", "textoResposta": "new"}], "filhos": [
                    {"uuid": "child", "sequencia": 0, "condicao": "#candidate-child", "respostas": [], "filhos": []},
                ]},
                {"uuid": "added", "sequencia": 1, "condicao": "#added", "respostas": [], "filhos": []},
            ],
            "intencoes": [{"uuid": "intent", "nome": "candidate-intent"}],
        }
        return current, candidate

    def test_generates_candidate_scenarios_for_added_and_changed_nodes(self) -> None:
        current, candidate = self.documents()
        result = generator.generate_from_diff(current, candidate)
        scenarios = {scenario["generated"]["target"]: scenario for scenario in result["scenarios"]}
        self.assertEqual(list(scenarios), ["added", "child", "parent"])
        self.assertTrue(all(scenario["generated"]["runner_passed"] for scenario in scenarios.values()))
        self.assertEqual(scenarios["child"]["generated"]["diff_changes"], [{"collection": "nos", "uuid": "parent", "path": "filhos[uuid=child].condicao", "kind": "changed"}])
        self.assertEqual(scenarios["parent"]["generated"]["diff_changes"], [
            {"collection": "nos", "uuid": "parent", "path": "respostas[uuid=reply].textoResposta", "kind": "changed"},
            {"collection": "nos", "uuid": "parent", "path": "tags", "kind": "added"},
            {"collection": "nos", "uuid": "parent", "path": "tags", "kind": "removed"},
        ])
        self.assertEqual(result["summary"], {"changes": 7, "scenarios": 3, "runner_passed": 3, "runner_failed": 0, "uncovered_changes": 2})
        self.assertEqual({item["reason"] for item in result["uncovered_changes"]}, {"missing_from_candidate", "non_dialog_change"})

    def test_output_is_deterministic_and_cli_writes_it(self) -> None:
        current, candidate = self.documents()
        first = generator.generate_from_diff(current, candidate)
        second = generator.generate_from_diff(current, candidate)
        self.assertEqual(json.dumps(first, ensure_ascii=False, sort_keys=True), json.dumps(second, ensure_ascii=False, sort_keys=True))
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            current_path, candidate_path, output = folder / "current.json", folder / "candidate.json", folder / "scenarios.json"
            current_path.write_text(json.dumps(current), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            result = subprocess.run([sys.executable, str(MODULE_PATH), str(current_path), str(candidate_path), "--output", str(output)], check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["summary"]["scenarios"], 3)


if __name__ == "__main__":
    unittest.main()
