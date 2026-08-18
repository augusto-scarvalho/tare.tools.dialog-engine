"""Tests for the deterministic Watson Assistant directed graph."""

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
MODULE_PATH = Path(os.environ.get("WATSON_DIALOG_GRAPH_PATH", ROOT / "watson_dialog_graph.py"))
FIXTURE = ROOT / "tests" / "fixtures" / "graph.json"
SPEC = importlib.util.spec_from_file_location("watson_dialog_graph_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
graph_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = graph_module
SPEC.loader.exec_module(graph_module)


class WatsonDialogGraphTests(unittest.TestCase):
    def graph(self) -> dict:
        return graph_module.build_graph(graph_module.load_json(FIXTURE))

    def test_graph_models_tree_slots_sibling_order_and_jumps(self) -> None:
        graph = self.graph()
        vertices = {vertex["id"]: vertex for vertex in graph["vertices"]}
        self.assertTrue(all(set(edge) == {"node", "target", "type"} for edge in graph["edges"]))
        edges = {(edge["node"], edge["target"], edge["type"]) for edge in graph["edges"]}
        self.assertEqual(graph["summary"]["dialog_nodes"], 5)
        self.assertEqual(graph["summary"]["folders"], 1)
        self.assertEqual(graph["summary"]["slots"], 1)
        self.assertTrue(vertices["root"]["folder"])
        self.assertFalse(vertices["first-child"]["folder"])
        self.assertEqual(vertices["slot:customer-name"]["kind"], "slot")
        self.assertTrue(vertices["slot:customer-name"]["required"])
        self.assertEqual(vertices["slot-reprompt"]["kind"], "slot_child")
        self.assertIn(("root", "first-child", "contains"), edges)
        self.assertIn(("root", "first-child", "folder_entry"), edges)
        self.assertIn(("root", "slot:customer-name", "contains_slot"), edges)
        self.assertIn(("slot:customer-name", "slot-reprompt", "slot_branch"), edges)
        self.assertIn(("first-child", "jumping-child", "next_evaluation"), edges)
        self.assertIn(("jumping-child", "target", "jump"), edges)

    def test_json_and_dot_outputs_are_deterministic(self) -> None:
        graph = self.graph()
        first = json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True)
        second = json.dumps(self.graph(), ensure_ascii=False, indent=2, sort_keys=True)
        self.assertEqual(first, second)
        dot = graph_module.dot(graph)
        self.assertIn('"root" [label="[folder] Entrada\\\\n#inicio", shape="folder"', dot)
        self.assertIn('"jumping-child" -> "target" [label="jump"]', dot)

    def test_unresolved_jump_is_reported(self) -> None:
        document = {"nos": [{"uuid": "source", "uuidEnviarPara": "missing", "respostas": [], "filhos": []}]}
        graph = graph_module.build_graph(document)
        self.assertEqual(graph["unresolved_jumps"], [{"node": "source", "target": "missing", "type": "jump"}])

    def test_jump_to_root_is_a_tree_restart_not_an_unresolved_jump(self) -> None:
        graph = graph_module.build_graph({"nos": [{"uuid": "restart", "uuidEnviarPara": "root", "respostas": [], "filhos": []}]})
        self.assertIn({"node": "restart", "target": "root", "type": "tree_restart"}, graph["edges"])
        self.assertEqual(graph["unresolved_jumps"], [])

    def test_normalizes_v1_nodes_and_reports_execution_features(self) -> None:
        document = {"dialog_nodes": [
            {"dialog_node": "frame", "type": "frame", "conditions": "#book", "actions": [{"name": "x"}]},
            {"dialog_node": "slot", "type": "slot", "parent": "frame", "variable": "city", "conditions": "@city"},
            {"dialog_node": "focus", "type": "event_handler", "parent": "slot", "event_name": "focus", "conditions": "true"},
        ]}
        graph = graph_module.build_graph(document)
        vertices = {vertex["id"]: vertex for vertex in graph["vertices"]}
        self.assertEqual(vertices["focus"]["kind"], "event_handler")
        self.assertTrue(vertices["frame"]["has_action"])
        self.assertEqual(graph["summary"]["event_handlers"], 1)
        self.assertEqual(graph["summary"]["callouts"], 1)

    def test_lists_root_digression_targets_without_expanding_them_into_edges(self) -> None:
        graph = graph_module.build_graph({"nos": [
            {"uuid": "topic", "nome": "Tópico", "inDigressionIn": True, "inRetornoDigression": True, "respostas": [], "filhos": []},
        ]})
        self.assertEqual(graph["digression_targets"], [{"node": "topic", "name": "Tópico", "returns": True}])
        self.assertEqual(graph["summary"]["digression_targets"], 1)

    def test_reachability_combines_conditions_structure_and_body_jumps(self) -> None:
        document = {
            "nos": [
                {"uuid": "rescue", "sequencia": 0, "condicao": "#go", "jumpSelector": "body", "uuidEnviarPara": "rescued", "respostas": [], "filhos": []},
                {"uuid": "disabled", "sequencia": 1, "condicao": "false", "respostas": [], "filhos": [{"uuid": "disabled-child", "sequencia": 0, "respostas": [], "filhos": []}]},
                {"uuid": "rescued", "sequencia": 2, "condicao": "false", "respostas": [], "filhos": []},
                {"uuid": "catchall", "sequencia": 3, "condicao": "true", "respostas": [], "filhos": []},
                {"uuid": "after-catchall", "sequencia": 4, "condicao": "#later", "respostas": [], "filhos": []},
            ]
        }
        result = graph_module.build_graph(document)["reachability"]
        unreachable = {item["node"]: item["reasons"] for item in result["unreachable"]}
        self.assertIn("disabled", unreachable)
        self.assertIn("disabled_condition_false", unreachable["disabled"])
        self.assertIn("disabled-child", unreachable)
        self.assertIn("after-catchall", unreachable)
        self.assertNotIn("rescued", unreachable)
        self.assertEqual(result["summary"]["body_jump_exceptions"], 1)

    def test_cli_generates_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "graph.json"
            result = subprocess.run(
                [sys.executable, str(MODULE_PATH), str(FIXTURE), "--output", str(output)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
