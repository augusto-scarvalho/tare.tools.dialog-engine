"""Tests for the unified Watson Dialog validation report."""

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
MODULE_PATH = Path(os.environ.get("WATSON_DIALOG_VALIDATE_PATH", ROOT / "watson_dialog_validate.py"))
FIXTURES = ROOT / "tests" / "fixtures"
SPEC = importlib.util.spec_from_file_location("watson_dialog_validate_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


class WatsonDialogValidateTests(unittest.TestCase):
    def document(self, name: str) -> dict:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def test_uses_one_stable_contract_across_validation_sources(self) -> None:
        report = validator.validate(self.document("validation_contract.json"))
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(set(report["summary"]), {"issues", "issues_by_category", "issues_by_code", "issues_by_severity"})
        issues = {(item["code"], item["category"], item["severity"]) for item in report["issues"]}
        self.assertIn(("anything_else_not_last_sibling", "semantic", "warning"), issues)
        self.assertIn(("duplicate_sibling_sequence", "semantic", "warning"), issues)
        self.assertIn(("invalid_spel_entity_call", "syntactic", "error"), issues)
        self.assertIn(("invalid_json_configuration", "syntactic", "error"), issues)
        self.assertIn(("unresolved_jump_target", "semantic", "error"), issues)
        self.assertTrue(all(set(item) == {"category", "code", "severity", "node", "field", "value", "message"} for item in report["issues"]))

    def test_validation_is_deterministic_and_cli_signals_issues(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "dialog.json"
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            source.write_text(json.dumps(self.document("validation_contract.json")), encoding="utf-8")
            command = [sys.executable, str(MODULE_PATH), str(source), "--output"]
            one = subprocess.run([*command, str(first)], check=False, capture_output=True, text=True)
            two = subprocess.run([*command, str(second)], check=False, capture_output=True, text=True)
            self.assertEqual(one.returncode, 1)
            self.assertEqual(two.returncode, 1)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_reports_unambiguous_spel_lexical_and_syntax_errors(self) -> None:
        issues = {(item["node"], item["category"], item["code"]) for item in validator.validate(self.document("validation_spel.json"))["issues"]}
        self.assertIn(("quote", "lexical", "unterminated_string"), issues)
        self.assertIn(("parenthesis", "syntactic", "unclosed_parenthesis"), issues)
        self.assertIn(("operator", "syntactic", "missing_right_operand"), issues)
        self.assertIn(("operators", "syntactic", "missing_boolean_operand"), issues)

    def test_reports_documented_legacy_dialog_rules(self) -> None:
        report = validator.validate(self.document("validation_legacy.json"))
        codes = {(item["node"], item["code"]) for item in report["issues"]}
        self.assertIn(("frame", "entity_shorthand_value_contains_closing_parenthesis"), codes)
        self.assertIn(("frame", "ambiguous_context_variable_name"), codes)
        self.assertIn(("root", "missing_root_anything_else"), codes)
        self.assertIn(("slot:first", "sys_number_zero_not_accepted"), codes)
        self.assertIn(("slot:first", "slot_depends_on_later_slot"), codes)
        self.assertIn(("slot:second", "slot_depends_on_optional_slot"), codes)
        self.assertIn(("long-condition", "condition_too_long"), codes)


if __name__ == "__main__":
    unittest.main()
