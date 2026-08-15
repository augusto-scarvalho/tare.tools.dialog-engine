"""Tests for static reachability analysis of dialog conditions."""

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
MODULE_PATH = Path(os.environ.get("WATSON_DIALOG_CONDITIONS_PATH", ROOT / "watson_dialog_conditions.py"))
FIXTURE = ROOT / "tests" / "fixtures" / "conditions.json"
SPEC = importlib.util.spec_from_file_location("watson_dialog_conditions_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
conditions = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = conditions
SPEC.loader.exec_module(conditions)


class WatsonDialogConditionsTests(unittest.TestCase):
    def test_boolean_satisfiability_handles_negation_and_comparisons(self) -> None:
        self.assertFalse(conditions.analyze_formula("$flag && !$flag")["is_satisfiable"])
        self.assertFalse(conditions.analyze_formula('$value == "a" && $value == "b"')["is_satisfiable"])
        self.assertTrue(conditions.analyze_formula("($flag && !$other) || #known_intent")["is_satisfiable"])

    def test_references_ignore_text_literals_and_entity_properties(self) -> None:
        references = conditions.condition_references('input.text == "#not_an_intent" && input.text == @known_entity.literal && #known_intent')
        self.assertEqual(references["intents"], ["known_intent"])
        self.assertEqual(references["entities"], ["known_entity"])

    def test_reports_reachability_and_unknown_artifacts(self) -> None:
        report = conditions.analyze_conditions(conditions.load_json(FIXTURE), check_variables=True)
        issues = {(issue["node"], issue["type"]) for issue in report["issues"]}
        self.assertIn(("impossible", "unsatisfiable_condition"), issues)
        self.assertIn(("shadowed", "shadowed_by_always_true"), issues)
        self.assertIn(("unknown-references", "unknown_intent"), issues)
        self.assertIn(("unknown-references", "unknown_entity"), issues)
        self.assertIn(("unknown-references", "unknown_variable"), issues)
        self.assertEqual(report["summary"]["conditions"], 4)
        default_issues = {(issue["node"], issue["type"]) for issue in conditions.analyze_conditions(conditions.load_json(FIXTURE))["issues"]}
        self.assertNotIn(("unknown-references", "unknown_variable"), default_issues)

    def test_cli_is_deterministic_and_signals_issues(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            command = [sys.executable, str(MODULE_PATH), str(FIXTURE), "--output"]
            result_one = subprocess.run([*command, str(first)], check=False, capture_output=True, text=True)
            result_two = subprocess.run([*command, str(second)], check=False, capture_output=True, text=True)
            self.assertEqual(result_one.returncode, 1)
            self.assertEqual(result_two.returncode, 1)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertIn("issues", json.loads(first.read_text(encoding="utf-8")))

    def test_evaluates_conditions_using_a_spel_runtime_state(self) -> None:
        document = {"nos": [{"uuid": "node", "condicao": "input.text.toLowerCase() == 'ok' && $enabled", "filhos": []}]}
        result = conditions.evaluate_document_conditions(document, {"input": {"text": "OK"}, "context": {"enabled": True}})
        self.assertEqual(result["summary"], {"true": 1, "false": 0, "unknown": 0})

    def test_reports_invalid_member_access_after_an_entity_shorthand(self) -> None:
        document = {"nos": [{"uuid": "invalid", "condicao": "@entity:(value).literal == input.text", "filhos": []}]}
        issues = conditions.analyze_conditions(document)["issues"]
        self.assertEqual(issues[0]["type"], "invalid_spel_entity_shorthand_member")

    def test_reports_invalid_direct_entity_call(self) -> None:
        document = {"nos": [{"uuid": "invalid-call", "condicao": "@ne(input.text) && true", "filhos": []}]}
        issue_types = {issue["type"] for issue in conditions.analyze_conditions(document)["issues"]}
        self.assertIn("invalid_spel_entity_call", issue_types)


if __name__ == "__main__":
    unittest.main()
