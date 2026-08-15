"""Tests for deterministic single-turn dialog scenario execution."""

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
MODULE_PATH = Path(os.environ.get("WATSON_DIALOG_TEST_PATH", ROOT / "watson_dialog_test.py"))
FIXTURES = ROOT / "tests" / "fixtures"
SPEC = importlib.util.spec_from_file_location("watson_dialog_test_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


class WatsonDialogTestRunnerTests(unittest.TestCase):
    def document(self) -> dict:
        return json.loads((FIXTURES / "dialog_test.json").read_text(encoding="utf-8"))

    def scenario(self, name: str) -> dict:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def test_selects_the_first_matching_node_and_records_a_trace(self) -> None:
        result = runner.run_scenario(self.document(), self.scenario("scenario_cancel.json"))
        self.assertTrue(result["passed"])
        self.assertEqual(result["selected"]["node"], "cancel")
        conditions = [item for item in result["turns"][0]["trace"] if item["event"] == "condition"]
        self.assertEqual(conditions, [{"event": "condition", "scope": "root", "node": "cancel", "name": "cancelamento", "condition": "#cancelar && @produto:cartão && $whatsapp", "result": "true"}])

    def test_uses_anything_else_only_after_prior_siblings_do_not_match(self) -> None:
        result = runner.run_scenario(self.document(), self.scenario("scenario_fallback.json"))
        self.assertTrue(result["passed"])
        self.assertEqual(result["selected"]["node"], "fallback")
        self.assertEqual([item["result"] for item in result["turns"][0]["trace"] if item["event"] == "condition"], ["false", "true"])

    def test_session_supports_children_jumps_and_slots(self) -> None:
        document = json.loads((FIXTURES / "dialog_session.json").read_text(encoding="utf-8"))
        child = runner.run_scenario(document, self.scenario("scenario_session_children.json"))
        slots = runner.run_scenario(document, self.scenario("scenario_session_slots.json"))
        jump = runner.run_scenario(document, {"input": {"text": "pular"}, "intents": [{"name": "jump"}], "entities": {}, "context": {"approved": True}, "expect": {"selected_node": "jump-target"}})
        body = runner.run_scenario(document, {"input": {"text": "direto"}, "intents": [{"name": "body"}], "entities": {}, "context": {}, "expect": {"selected_node": "body-target"}})
        self.assertTrue(child["passed"])
        self.assertEqual(child["turns"][0]["dialog_stack_after"], [{"dialog_node": "start"}])
        self.assertTrue(slots["passed"])
        self.assertEqual(slots["turns"][1]["context"], {"city": "Paris", "date": "2026-08-16"})
        self.assertTrue(jump["passed"])
        self.assertIn({"event": "jump", "node": "jump-source", "target": "jump-target", "mode": "condition"}, jump["turns"][0]["trace"])
        self.assertTrue(body["passed"])
        self.assertIn({"event": "direct_response", "node": "body-target"}, body["turns"][0]["trace"])

    def test_cursor_starts_evaluation_at_a_specific_uuid(self) -> None:
        document = json.loads((FIXTURES / "dialog_session.json").read_text(encoding="utf-8"))
        result = runner.run_scenario(document, self.scenario("scenario_cursor.json"))
        self.assertTrue(result["passed"])
        self.assertEqual(result["turns"][0]["dialog_stack_before"], [{"dialog_node": "jump-target"}])
        self.assertEqual([item["node"] for item in result["turns"][0]["trace"] if item["event"] == "condition"], ["jump-target", "body-source"])

    def test_accepts_the_v1_dialog_stack_list(self) -> None:
        document = json.loads((FIXTURES / "dialog_session.json").read_text(encoding="utf-8"))
        result = runner.run_scenario(document, {
            "dialog_stack": [{"dialog_node": "jump-target"}],
            "input": {"text": "direto"},
            "intents": [{"name": "body"}],
            "entities": {},
            "context": {},
            "expect": {"selected_node": "body-target"},
        })
        self.assertTrue(result["passed"])
        self.assertEqual(result["turns"][0]["dialog_stack_before"], [{"dialog_node": "jump-target"}])

    def test_enters_a_matching_folder_without_selecting_the_folder(self) -> None:
        document = {"nos": [
            {"uuid": "folder", "nome": "grupo", "folder": True, "sequencia": 0, "condicao": "#topic", "respostas": [], "filhos": [
                {"uuid": "inside", "sequencia": 0, "condicao": "#topic", "respostas": [], "filhos": []},
            ]},
            {"uuid": "after", "sequencia": 1, "condicao": "true", "respostas": [], "filhos": []},
        ]}
        matched = runner.run_scenario(document, {"input": {"text": "x"}, "intents": [{"name": "topic"}], "expect": {"selected_node": "inside"}})
        missed = runner.run_scenario(document, {"input": {"text": "x"}, "intents": [], "expect": {"selected_node": "after"}})
        self.assertTrue(matched["passed"])
        self.assertEqual(matched["turns"][0]["trace"][0]["event"], "folder_condition")
        self.assertTrue(missed["passed"])

    def test_start_conditions_are_limited_to_the_first_turn(self) -> None:
        document = {"nos": [
            {"uuid": "conversation-start", "sequencia": 0, "condicao": "conversation_start", "respostas": [], "filhos": []},
            {"uuid": "welcome", "sequencia": 1, "condicao": "welcome", "respostas": [], "filhos": []},
            {"uuid": "fallback", "sequencia": 2, "condicao": "true", "respostas": [], "filhos": []},
        ]}
        start = runner.run_scenario(document, {"turns": [{"input": {"text": "oi"}}, {"input": {"text": "oi de novo"}}]})
        welcome = runner.run_scenario({"nos": [
            {"uuid": "welcome", "sequencia": 0, "condicao": "welcome", "respostas": [], "filhos": []},
            {"uuid": "fallback", "sequencia": 1, "condicao": "true", "respostas": [], "filhos": []},
        ]}, {"turns": [{"input": {}}, {"input": {}}]})
        self.assertEqual([item["selected"]["node"] for item in start["turns"]], ["conversation-start", "fallback"])
        self.assertEqual([item["selected"]["node"] for item in welcome["turns"]], ["welcome", "fallback"])

    def test_slot_handler_is_selected_and_slot_stack_is_preserved(self) -> None:
        document = {"nos": [{
            "uuid": "frame", "sequencia": 0, "condicao": "#book", "respostas": [], "filhos": [], "slots": [{
                "uuid": "city-slot", "uuidVariavelContexto": "city-var", "indicadorObrigatorio": True, "condicao": "@city", "filhos": [{
                    "uuid": "city-help", "uuidSlot": "city-slot", "sequencia": 0, "condicao": "#help", "jumpSelector": "reprompt", "respostas": [], "filhos": [],
                }],
            }],
        }] , "variaveisContexto": [{"uuid": "city-var", "variavelContexto": "city"}]}
        result = runner.run_scenario(document, {"turns": [
            {"input": {"text": "reservar"}, "intents": [{"name": "book"}], "entities": {}},
            {"dialog_stack": [{"dialog_node": "city-slot"}], "input": {"text": "ajuda"}, "intents": [{"name": "help"}], "entities": {}},
        ]})
        self.assertEqual([item["selected"]["node"] for item in result["turns"]], ["frame", "city-help"])
        self.assertEqual(result["turns"][1]["dialog_stack_after"], [{"dialog_node": "city-slot", "state": "in_progress"}])
        self.assertIn({"event": "slot_handler", "scope": "slot:city-slot", "node": "city-help", "action": "reprompt"}, result["turns"][1]["trace"])

    def test_matching_conditional_response_jump_overrides_node_jump(self) -> None:
        document = {"nos": [
            {"uuid": "source", "sequencia": 0, "condicao": "#go", "uuidEnviarPara": "node-target", "jumpSelector": "body", "respostas": [
                {"uuid": "conditional", "sequenciaBloco": 1, "sequenciaItem": 1, "condicao": "#go", "uuidEnviarPara": "response-target", "jumpSelector": "body"},
            ], "filhos": []},
            {"uuid": "node-target", "sequencia": 1, "condicao": "false", "respostas": [], "filhos": []},
            {"uuid": "response-target", "sequencia": 2, "condicao": "false", "respostas": [], "filhos": []},
        ]}
        result = runner.run_scenario(document, {"input": {"text": "ir"}, "intents": [{"name": "go"}], "expect": {"selected_node": "response-target"}})
        self.assertTrue(result["passed"])
        self.assertIn({"event": "response_jump", "node": "source", "target": "response-target", "mode": "body"}, result["turns"][0]["trace"])

    def test_cli_reports_failed_expectations_and_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "first.json", Path(directory) / "second.json"
            command = [sys.executable, str(MODULE_PATH), str(FIXTURES / "dialog_test.json"), str(FIXTURES / "scenario_cancel.json"), str(FIXTURES / "scenario_fallback.json"), "--output"]
            one = subprocess.run([*command, str(first)], check=False, capture_output=True, text=True)
            two = subprocess.run([*command, str(second)], check=False, capture_output=True, text=True)
            self.assertEqual(one.returncode, 0)
            self.assertEqual(two.returncode, 0)
            self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
