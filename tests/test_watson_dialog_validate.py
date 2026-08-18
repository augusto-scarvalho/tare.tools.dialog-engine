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
MODULE_PATH = Path(os.environ.get("WATSON_DIALOG_VALIDATE_PATH", ROOT / "src/tare_dialog/validator.py"))
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
        self.assertIn(("legacy_order_ambiguous", "provenance", "info"), issues)
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
        self.assertNotIn(("slot:first", "sys_number_zero_not_accepted"), codes)
        self.assertIn(("slot:first", "slot_depends_on_later_slot"), codes)
        self.assertIn(("slot:second", "slot_depends_on_optional_slot"), codes)
        self.assertIn(("long-condition", "condition_too_long"), codes)


    def test_legacy_fallback_uses_source_order_instead_of_synthetic_sequence_sort(self) -> None:
        document = {"nos": [
            {"uuid": "legacy-none-a", "sequencia": None, "condicao": "#old", "filhos": []},
            {"uuid": "numbered", "sequencia": 1, "condicao": "#new", "filhos": []},
            {"uuid": "fallback", "sequencia": 2, "condicao": "anything_else", "filhos": []},
        ]}
        codes = {(item["node"], item["code"]) for item in validator.validate(document)["issues"]}
        self.assertNotIn(("fallback", "anything_else_not_last_sibling"), codes)


        historical = {"nos": [
            {"uuid": "old-fallback", "sequencia": None, "status": "INATIVO", "condicao": "anything_else", "filhos": []},
            {"uuid": "active", "sequencia": 0, "status": "ATIVO", "condicao": "#go", "filhos": []},
            {"uuid": "fallback", "sequencia": 1, "status": "ATIVO", "condicao": "anything_else", "filhos": []},
        ]}
        historical_codes = {(item["node"], item["code"]) for item in validator.validate(historical)["issues"]}
        self.assertNotIn(("old-fallback", "anything_else_not_last_sibling"), historical_codes)

    def test_same_context_variable_is_not_a_dependency_on_a_later_slot(self) -> None:
        document = {
            "variaveisContexto": [{"uuid": "shared", "variavelContexto": "motivo"}],
            "nos": [{
                "uuid": "frame", "condicao": "anything_else", "filhos": [],
                "slots": [
                    {"uuid": "first", "uuidVariavelContexto": "shared", "indicadorObrigatorio": True, "condicao": "!$motivo"},
                    {"uuid": "second", "uuidVariavelContexto": "shared", "indicadorObrigatorio": True, "condicao": "@motivo"},
                ],
            }],
        }
        issues = {(item["node"], item["code"]) for item in validator.validate(document)["issues"]}
        self.assertNotIn(("slot:first", "slot_depends_on_later_slot"), issues)

    def test_digression_ignores_inactive_paths_and_inactive_forcing_children(self) -> None:
        document = {"nos": [
            {
                "uuid": "active-parent", "condicao": "#active", "inDigressionOut": True,
                "filhos": [{"uuid": "inactive-catchall", "status": "INATIVO", "condicao": "true", "filhos": []}],
            },
            {
                "uuid": "active-blocked", "condicao": "#blocked", "inDigressionOut": True,
                "filhos": [{"uuid": "active-catchall", "status": "ATIVO", "condicao": "true", "filhos": []}],
            },
            {
                "uuid": "inactive-parent", "status": "INATIVO", "condicao": "#inactive", "inDigressionOut": True,
                "uuidEnviarPara": "root", "filhos": [],
            },
        ]}
        issues = {(item["node"], item["code"]) for item in validator.validate(document)["issues"]}
        self.assertNotIn(("active-parent", "digression_blocked_by_forcing_child"), issues)
        self.assertIn(("active-blocked", "digression_blocked_by_forcing_child"), issues)
        self.assertNotIn(("inactive-parent", "digression_blocked_by_transition"), issues)

    def test_expression_shaped_context_registry_entry_is_not_a_hyphenated_variable(self) -> None:
        document = {
            "variaveisContexto": [{
                "uuid": "expression",
                "variavelContexto": "$intencoes_anteriores[$intencoes_anteriores.size()-1][0]",
            }],
            "nos": [{
                "uuid": "node",
                "condicao": "$intencoes_anteriores[$intencoes_anteriores.size()-1][0] != null",
                "filhos": [],
            }],
        }
        self.assertNotIn("ambiguous_context_variable_name", {item["code"] for item in validator.validate(document)["issues"]})


    def test_number_slot_reports_only_causal_zero_and_capture_type_contradictions(self) -> None:
        document = {"nos": [{
            "uuid": "frame", "condicao": "anything_else", "filhos": [], "slots": [
                {
                    "uuid": "positive-selector", "condicao": "@sys-number && slot_in_focus",
                    "respostas": [{"textoResposta": "Escolha uma opção de 1 a 5"}], "filhos": [],
                },
                {
                    "uuid": "zero-handler", "condicao": "@sys-number && slot_in_focus",
                    "respostas": [{"textoResposta": "Escolha uma opção"}],
                    "filhos": [{"uuid": "bad-zero", "condicao": "@sys-number < 1", "filhos": []}],
                },
                {
                    "uuid": "nps", "condicao": "slot_in_focus && @sys-number",
                    "respostas": [{"textoResposta": "Em uma escala de 0 a 10, qual sua nota?"}],
                    "filhos": [{"uuid": "zero", "condicao": "@sys-number:0", "filhos": []}],
                },
                {
                    "uuid": "document", "condicao": "slot_in_focus && @sys-number",
                    "respostas": [{"textoResposta": "Envie o arquivo"}],
                    "filhos": [{"uuid": "doc", "condicao": "$inputType:document", "filhos": []}],
                },
            ],
        }]}
        issues = {(item["node"], item["code"]) for item in validator.validate(document)["issues"]}
        self.assertNotIn(("slot:positive-selector", "sys_number_zero_handler_unreachable"), issues)
        self.assertIn(("slot:zero-handler", "sys_number_zero_handler_unreachable"), issues)
        self.assertIn(("slot:nps", "sys_number_zero_valid_but_not_captured"), issues)
        self.assertIn(("slot:document", "slot_capture_type_mismatch_document"), issues)


    def test_unsatisfiable_slot_enable_condition_is_separate_from_deliberate_false(self) -> None:
        document = {
            "variaveisContexto": [{"uuid": "flag", "variavelContexto": "flag"}],
            "nos": [{
                "uuid": "frame", "condicao": "anything_else", "filhos": [],
                "slots": [
                    {"uuid": "broken", "uuidVariavelContexto": "flag", "condicao": "@value", "condicaoSlots": "$flag && $flag == false"},
                    {"uuid": "disabled", "uuidVariavelContexto": "flag", "condicao": "@value", "condicaoSlots": "false"},
                ],
            }],
        }
        issues = {(item["node"], item["code"]) for item in validator.validate(document)["issues"]}
        self.assertIn(("slot:broken", "unsatisfiable_slot_enable_condition"), issues)
        self.assertNotIn(("slot:disabled", "unsatisfiable_slot_enable_condition"), issues)

    def test_legacy_order_ambiguity_is_one_provenance_finding_per_tie_set(self) -> None:
        document = {"nos": [
            {"uuid": "a", "sequencia": 1, "condicao": "#a", "filhos": []},
            {"uuid": "b", "sequencia": 1, "condicao": "#b", "filhos": []},
            {"uuid": "c", "sequencia": 1, "condicao": "#c", "filhos": []},
        ]}
        rows = [item for item in validator.validate(document)["issues"] if item["code"] == "legacy_order_ambiguous"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["node"], "root")
        self.assertEqual(rows[0]["severity"], "info")
        self.assertEqual(rows[0]["category"], "provenance")
        self.assertEqual(rows[0]["value"], {"sequence": 1, "nodes": ["a", "b", "c"]})

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

    def test_validates_spel_inside_nested_v1_dialog_node_context(self) -> None:
        document = {"dialog_nodes": [{
            "dialog_node": "context-node",
            "type": "standard",
            "context": {
                "good": "<? input.text.toLowerCase() ?>",
                "bad_operator": "prefix <? $ready && ?> suffix",
                "nested": {"values": ["literal", "<? (input.text ?>"]},
                "quoted_delimiter": "<? '?>'.contains('>') ?>",
                "literal_backslash": "<? @pattern.literal.replace('\\', '') ?>",
                "doubled_quote": "<? 'Tony''s ?> marker'.contains('x') ?>",
            },
        }]}
        issues = {(item["node"], item["field"], item["code"], item["value"]) for item in validator.validate(document)["issues"]}
        self.assertIn(("context-node", 'context["bad_operator"]', "context_spel_missing_right_operand", "$ready &&"), issues)
        self.assertIn(("context-node", 'context["nested"]["values"][1]', "context_spel_unclosed_parenthesis", "(input.text"), issues)
        self.assertFalse(any(item[2].startswith("context_spel_") and "good" in item[1] for item in issues))
        self.assertFalse(any(item[2].startswith("context_spel_") and "quoted_delimiter" in item[1] for item in issues))
        self.assertFalse(any(item[2].startswith("context_spel_") and "literal_backslash" in item[1] for item in issues))
        self.assertFalse(any(item[2].startswith("context_spel_") and "doubled_quote" in item[1] for item in issues))

    def test_validates_context_inside_normalized_legacy_node_and_slot_json(self) -> None:
        document = {"nos": [{
            "uuid": "legacy-node",
            "condicao": "anything_else",
            "json": json.dumps({"context": {"broken": "<? input.text", "ok": "<? input.text ?>"}}),
            "respostas": [],
            "slots": [{
                "uuid": "legacy-slot",
                "json": json.dumps({"context": {"nested": {"broken": "<? ?>"}}}),
                "filhos": [],
            }],
            "filhos": [],
        }]}
        issues = {(item["node"], item["field"], item["code"]) for item in validator.validate(document)["issues"]}
        self.assertIn(("legacy-node", 'json.context["broken"]', "context_spel_unclosed_template"), issues)
        self.assertIn(("slot:legacy-slot", 'json.context["nested"]["broken"]', "context_spel_empty_expression"), issues)

    def test_does_not_double_report_context_spel_when_legacy_json_is_invalid(self) -> None:
        document = {"nos": [{"uuid": "bad-json", "condicao": "anything_else", "json": '{"context":{"x":"<? bad"}', "respostas": [], "filhos": []}]}
        issues = [item for item in validator.validate(document)["issues"] if item["node"] == "bad-json"]
        self.assertTrue(any(item["code"] == "invalid_json_configuration" for item in issues))
        self.assertFalse(any(item["code"].startswith("context_spel_") for item in issues))


if __name__ == "__main__":
    unittest.main()
