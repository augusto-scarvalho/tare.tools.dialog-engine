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

    def test_reports_rich_response_and_v1_structure_rules(self) -> None:
        legacy = {"nos": [{
            "uuid": "many", "condicao": "anything_else", "respostas": [
                {"idTipoResposta": 1, "sequenciaBloco": 1, "idTipoComponente": component}
                for component in range(1, 7)
            ], "filhos": [],
        }]}
        legacy_codes = {item["code"] for item in validator.validate(legacy)["issues"]}
        self.assertIn("too_many_response_types", legacy_codes)

        response_condition = {"nos": [{"uuid": "source", "condicao": "anything_else", "respostas": [{"uuid": "response", "condicao": "@bad &&", "uuidEnviarPara": "missing"}], "filhos": []}]}
        response_issues = {(item["node"], item["code"]) for item in validator.validate(response_condition)["issues"]}
        self.assertIn(("response:source:response", "missing_right_operand"), response_issues)
        self.assertIn(("source", "unresolved_response_jump_target"), response_issues)

        v1 = {"dialog_nodes": [
            {"dialog_node": "standard", "type": "standard"},
            {"dialog_node": "frame", "type": "frame"},
            {"dialog_node": "slot", "type": "slot", "parent": "standard"},
            {"dialog_node": "response", "type": "response_condition", "parent": "slot"},
            {"dialog_node": "handler", "type": "event_handler", "event_name": "focus", "parent": "frame"},
            {"dialog_node": "handler-child", "type": "standard", "parent": "handler"},
            {"dialog_node": "bad-type", "type": "other"},
        ]}
        v1_codes = {item["code"] for item in validator.validate(v1)["issues"]}
        self.assertTrue({"frame_without_slot", "slot_parent_not_frame", "response_condition_parent_invalid", "slot_handler_parent_invalid", "leaf_node_has_children", "unknown_dialog_node_type"}.issubset(v1_codes))

    def test_accepts_root_as_a_builtin_jump_target(self) -> None:
        document = {"nos": [{"uuid": "restart", "condicao": "anything_else", "uuidEnviarPara": "root", "respostas": [], "filhos": []}]}
        codes = {item["code"] for item in validator.validate(document)["issues"]}
        self.assertNotIn("unresolved_jump_target", codes)


if __name__ == "__main__":
    unittest.main()
