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
MODULE_PATH = Path(os.environ.get("WATSON_DIALOG_CONDITIONS_PATH", ROOT / "src/tare_dialog/conditions.py"))
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


    def test_explicit_false_is_disabled_evidence_not_an_accidental_contradiction(self) -> None:
        document = {"nos": [
            {"uuid": "disabled", "sequencia": 0, "condicao": "false", "filhos": []},
            {"uuid": "guarded-disabled", "sequencia": 1, "condicao": "$flag && false", "filhos": []},
            {"uuid": "contradiction", "sequencia": 2, "condicao": "$flag && !$flag", "filhos": []},
        ]}
        report = conditions.analyze_conditions(document)
        issues = {(item["node"], item["type"], item["severity"]) for item in report["issues"]}
        self.assertIn(("disabled", "disabled_condition_false", "info"), issues)
        self.assertIn(("guarded-disabled", "disabled_condition_false", "info"), issues)
        self.assertIn(("contradiction", "unsatisfiable_condition", "warning"), issues)
        self.assertNotIn(("disabled", "unsatisfiable_condition", "warning"), issues)

    def test_shadow_analysis_requires_proven_order_and_ignores_inactive_paths(self) -> None:
        ambiguous = {"nos": [
            {"uuid": "true", "sequencia": 1, "condicao": "true", "filhos": []},
            {"uuid": "later", "sequencia": 1, "condicao": "#intent", "filhos": []},
        ]}
        self.assertNotIn("shadowed_by_always_true", {item["type"] for item in conditions.analyze_conditions(ambiguous)["issues"]})

        inactive = {"nos": [
            {"uuid": "true", "sequencia": 1, "condicao": "true", "filhos": []},
            {"uuid": "later", "sequencia": 2, "status": "INATIVO", "condicao": "#intent", "filhos": []},
        ]}
        self.assertNotIn(("later", "shadowed_by_always_true"), {(item["node"], item["type"]) for item in conditions.analyze_conditions(inactive)["issues"]})

        review_duplicate = {"nos": [
            {"uuid": "review", "sequencia": 1, "status": "REVISAO", "condicao": "#same", "filhos": []},
            {"uuid": "active", "sequencia": 2, "status": "ATIVO", "condicao": "#same", "filhos": []},
        ]}
        self.assertNotIn(("active", "duplicate_sibling_condition"), {(item["node"], item["type"]) for item in conditions.analyze_conditions(review_duplicate)["issues"]})


    def test_alternate_jump_entry_prevents_overclaiming_shadow_and_duplicate_unreachability(self) -> None:
        shadow = {"nos": [
            {"uuid": "entry", "sequencia": 0, "condicao": "#go", "uuidEnviarPara": "later", "filhos": []},
            {"uuid": "catchall", "sequencia": 1, "condicao": "true", "filhos": []},
            {"uuid": "later", "sequencia": 2, "condicao": "#later", "filhos": []},
        ]}
        self.assertNotIn(("later", "shadowed_by_always_true"), {(i["node"], i["type"]) for i in conditions.analyze_conditions(shadow)["issues"]})

        duplicate = {"nos": [
            {"uuid": "entry", "sequencia": 0, "condicao": "#go", "uuidEnviarPara": "second", "filhos": []},
            {"uuid": "first", "sequencia": 1, "condicao": "#same", "filhos": []},
            {"uuid": "second", "sequencia": 2, "condicao": "#same", "filhos": []},
        ]}
        self.assertNotIn(("second", "duplicate_sibling_condition"), {(i["node"], i["type"]) for i in conditions.analyze_conditions(duplicate)["issues"]})

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
        report = conditions.analyze_conditions(document)
        issue_types = {issue["type"] for issue in report["issues"]}
        self.assertIn("invalid_spel_entity_call", issue_types)
        self.assertNotIn("unknown_entity", issue_types)


if __name__ == "__main__":
    unittest.main()
