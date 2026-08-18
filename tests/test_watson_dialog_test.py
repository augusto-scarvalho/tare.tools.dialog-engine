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
MODULE_PATH = Path(os.environ.get("WATSON_DIALOG_TEST_PATH", ROOT / "src/tare_dialog/test_runner.py"))
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

    def test_accepts_and_normalizes_a_v1_dialog_payload(self) -> None:
        document = json.loads((FIXTURES / "dialog_v1.json").read_text(encoding="utf-8"))
        result = runner.run_scenario(document, {"turns": [
            {"input": {"text": "reservar"}, "intents": [{"name": "book"}], "entities": {}},
            {"dialog_stack": [{"dialog_node": "booking-city"}], "input": {"text": "Paris"}, "entities": {"city": ["Paris"]}},
        ]})
        self.assertEqual([item["selected"]["node"] for item in result["turns"]], ["booking-focus", "booking-filled"])
        self.assertEqual(result["turns"][1]["context"], {"city": "Paris"})
        events = [item["handler_event"] for item in result["turns"][1]["trace"] if item["event"] == "slot_handler"]
        self.assertEqual(events, ["input", "filled"])

    def test_v1_slot_handlers_follow_the_documented_event_order(self) -> None:
        document = json.loads((FIXTURES / "dialog_v1.json").read_text(encoding="utf-8"))
        result = runner.run_scenario(document, {"turns": [
            {"input": {"text": "reservar"}, "intents": [{"name": "book"}], "entities": {}},
            {"dialog_stack": [{"dialog_node": "booking-city"}], "input": {"text": "ajuda"}, "intents": [{"name": "help"}], "entities": {}},
        ]})
        self.assertEqual(result["turns"][1]["selected"]["node"], "booking-generic")
        events = [item["handler_event"] for item in result["turns"][1]["trace"] if item["event"] == "slot_handler"]
        self.assertEqual(events, ["input", "generic"])

    def test_v1_slot_nomatch_runs_after_input_when_no_handler_matches(self) -> None:
        document = json.loads((FIXTURES / "dialog_v1.json").read_text(encoding="utf-8"))
        result = runner.run_scenario(document, {"turns": [
            {"input": {"text": "reservar"}, "intents": [{"name": "book"}], "entities": {}},
            {"dialog_stack": [{"dialog_node": "booking-city"}], "input": {"text": "não sei"}, "entities": {}},
        ]})
        self.assertEqual(result["turns"][1]["selected"]["node"], "booking-nomatch")
        events = [item["handler_event"] for item in result["turns"][1]["trace"] if item["event"] == "slot_handler"]
        self.assertEqual(events, ["input", "nomatch"])

    def test_digression_returns_without_overloading_dialog_stack(self) -> None:
        document = {"nos": [
            {"uuid": "order", "sequencia": 0, "condicao": "#order", "inDigressionOut": True, "respostas": [], "filhos": [
                {"uuid": "order-size", "sequencia": 0, "condicao": "#size", "respostas": [], "filhos": []},
            ]},
            {"uuid": "weather", "sequencia": 1, "condicao": "#weather", "inDigressionIn": True, "inRetornoDigression": True, "respostas": [], "filhos": []},
        ]}
        result = runner.run_scenario(document, {"turns": [
            {"input": {"text": "pedido"}, "intents": [{"name": "order"}]},
            {"input": {"text": "tempo"}, "intents": [{"name": "weather"}]},
            {"input": {"text": "grande"}, "intents": [{"name": "size"}]},
        ]})
        self.assertEqual([item["selected"]["node"] for item in result["turns"]], ["order", "weather", "order-size"])
        self.assertEqual(result["turns"][1]["dialog_stack_after"], [{"dialog_node": "order"}])
        self.assertIn({"event": "digression", "from": "order", "target": "weather", "returns": True}, result["turns"][1]["trace"])
        self.assertIn({"event": "digression_return", "node": "weather", "to": "order"}, result["turns"][1]["trace"])

    def test_digressions_can_return_recursively(self) -> None:
        document = {"nos": [
            {"uuid": "order", "sequencia": 0, "condicao": "#order", "inDigressionOut": True, "respostas": [], "filhos": [
                {"uuid": "order-size", "sequencia": 0, "condicao": "#size", "respostas": [], "filhos": []},
            ]},
            {"uuid": "help-primary", "sequencia": 1, "condicao": "#help_primary", "inDigressionIn": True, "inDigressionOut": True, "inRetornoDigression": True, "respostas": [], "filhos": [
                {"uuid": "help-primary-finish", "sequencia": 0, "condicao": "#resume_primary", "respostas": [], "filhos": []},
            ]},
            {"uuid": "help-secondary", "sequencia": 2, "condicao": "#help_secondary", "inDigressionIn": True, "inRetornoDigression": True, "respostas": [], "filhos": []},
        ]}
        result = runner.run_scenario(document, {"turns": [
            {"input": {"text": "pedido"}, "intents": [{"name": "order"}]},
            {"input": {"text": "ajuda principal"}, "intents": [{"name": "help_primary"}]},
            {"input": {"text": "mais ajuda"}, "intents": [{"name": "help_secondary"}]},
            {"input": {"text": "voltar"}, "intents": [{"name": "resume_primary"}]},
            {"input": {"text": "grande"}, "intents": [{"name": "size"}]},
        ]})
        self.assertEqual([item["selected"]["node"] for item in result["turns"]], ["order", "help-primary", "help-secondary", "help-primary-finish", "order-size"])
        self.assertEqual(result["turns"][2]["dialog_stack_after"], [{"dialog_node": "help-primary"}])
        self.assertIn({"event": "digression_return", "node": "help-secondary", "to": "help-primary"}, result["turns"][2]["trace"])
        self.assertIn({"event": "digression_return", "node": "help-primary-finish", "to": "order"}, result["turns"][3]["trace"])

    def test_jump_from_a_digression_discards_returns_for_any_target(self) -> None:
        document = {"nos": [
            {"uuid": "order", "sequencia": 0, "condicao": "#order", "inDigressionOut": True, "respostas": [], "filhos": [
                {"uuid": "order-size", "sequencia": 0, "condicao": "#size", "respostas": [], "filhos": []},
            ]},
            {"uuid": "restart", "sequencia": 1, "condicao": "#restart", "inDigressionIn": True, "inRetornoDigression": True, "uuidEnviarPara": "new-flow", "jumpSelector": "user_input", "respostas": [], "filhos": []},
            {"uuid": "new-flow", "sequencia": 2, "condicao": "#finish", "respostas": [], "filhos": []},
        ]}
        result = runner.run_scenario(document, {"turns": [
            {"input": {"text": "pedido"}, "intents": [{"name": "order"}]},
            {"input": {"text": "novo fluxo"}, "intents": [{"name": "restart"}]},
            {"input": {"text": "terminar"}, "intents": [{"name": "finish"}]},
            {"input": {"text": "novo pedido"}, "intents": [{"name": "order"}]},
            {"input": {"text": "grande"}, "intents": [{"name": "size"}]},
        ]})
        self.assertEqual([item["selected"]["node"] if item["selected"] else None for item in result["turns"]], ["order", "restart", "new-flow", "order", "order-size"])
        self.assertEqual(result["turns"][1]["dialog_stack_after"], [{"dialog_node": "new-flow"}])
        self.assertFalse(result["turns"][1]["branch_exited"])
        self.assertEqual(result["turns"][2]["dialog_stack_after"], [{"dialog_node": "root"}])
        self.assertEqual(result["turns"][4]["dialog_stack_after"], [{"dialog_node": "root"}])
        self.assertIn({"event": "digression_return_abandoned", "node": "restart", "target": "new-flow", "returns": 1}, result["turns"][1]["trace"])
        self.assertNotIn("digression_return", [item["event"] for item in result["turns"][1]["trace"]])

    def test_skip_user_input_from_a_digression_also_discards_returns(self) -> None:
        document = {"nos": [
            {"uuid": "order", "sequencia": 0, "condicao": "#order", "inDigressionOut": True, "respostas": [], "filhos": [
                {"uuid": "order-size", "sequencia": 0, "condicao": "#size", "respostas": [], "filhos": []},
            ]},
            {"uuid": "diversion", "sequencia": 1, "condicao": "#diversion", "inDigressionIn": True, "inRetornoDigression": True, "jumpSelector": "move_on", "respostas": [], "filhos": [
                {"uuid": "diversion-next", "sequencia": 0, "condicao": "true", "respostas": [], "filhos": []},
            ]},
        ]}
        result = runner.run_scenario(document, {"turns": [
            {"input": {"text": "pedido"}, "intents": [{"name": "order"}]},
            {"input": {"text": "outro assunto"}, "intents": [{"name": "diversion"}]},
        ]})
        self.assertEqual([item["selected"]["node"] for item in result["turns"]], ["order", "diversion-next"])
        self.assertEqual(result["turns"][1]["dialog_stack_after"], [{"dialog_node": "root"}])
        self.assertIn({"event": "digression_return_abandoned", "node": "diversion", "target": "diversion-next", "returns": 1}, result["turns"][1]["trace"])

    def test_action_results_are_injected_from_the_scenario_without_network(self) -> None:
        document = {"nos": [{"uuid": "quote", "sequencia": 0, "condicao": "#quote", "actions": [{"name": "get_quote"}], "respostas": [], "filhos": []}]}
        result = runner.run_scenario(document, {
            "input": {"text": "cotação"}, "intents": [{"name": "quote"}],
            "effects": {"actions": {"quote": {"context": {"currency": "BRL"}, "result_variable": "quote_result", "result": {"amount": 42}}}},
        })
        self.assertEqual(result["turns"][0]["context"], {"currency": "BRL", "quote_result": {"amount": 42}})
        self.assertIn({"event": "callout", "node": "quote", "kind": "action", "result": "applied", "context_keys": ["currency"]}, result["turns"][0]["trace"])

    def test_v1_response_condition_jump_takes_precedence(self) -> None:
        document = {"dialog_nodes": [
            {"dialog_node": "source", "type": "standard", "conditions": "#go", "next_step": {"behavior": "jump_to", "dialog_node": "node-target", "selector": "response"}},
            {"dialog_node": "response", "type": "response_condition", "parent": "source", "conditions": "#go", "next_step": {"behavior": "jump_to", "dialog_node": "response-target", "selector": "response"}},
            {"dialog_node": "node-target", "type": "standard", "conditions": "false", "previous_sibling": "source"},
            {"dialog_node": "response-target", "type": "standard", "conditions": "false", "previous_sibling": "node-target"},
        ]}
        result = runner.run_scenario(document, {"input": {"text": "ir"}, "intents": [{"name": "go"}]})
        self.assertEqual(result["selected"]["node"], "response-target")

    def test_stops_a_turn_after_more_than_fifty_executions_of_one_node(self) -> None:
        document = {"nos": [{"uuid": "loop", "sequencia": 0, "condicao": "#loop", "uuidEnviarPara": "loop", "jumpSelector": "body", "respostas": [], "filhos": []}]}
        result = runner.run_scenario(document, {"input": {"text": "loop"}, "intents": [{"name": "loop"}]})
        executions = [item for item in result["turns"][0]["trace"] if item["event"] == "node_execution" and item["node"] == "loop"]
        self.assertEqual(len(executions), 51)
        self.assertEqual(executions[-1]["count"], 51)
        self.assertIn({"event": "error", "code": "node_execution_limit", "node": "loop", "executions": 51, "limit": 50}, result["turns"][0]["trace"])

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
