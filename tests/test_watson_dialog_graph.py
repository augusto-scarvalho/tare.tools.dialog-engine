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
        self.assertEqual(graph["summary"]["slots"], 1)
        self.assertEqual(vertices["slot:customer-name"]["kind"], "slot")
        self.assertTrue(vertices["slot:customer-name"]["required"])
        self.assertEqual(vertices["slot-reprompt"]["kind"], "slot_child")
        self.assertIn(("root", "first-child", "contains"), edges)
        self.assertIn(("root", "slot:customer-name", "contains_slot"), edges)
        self.assertIn(("slot:customer-name", "slot-reprompt", "slot_branch"), edges)
        self.assertIn(("first-child", "jumping-child", "next_evaluation"), edges)
        self.assertIn(("jumping-child", "target", "jump"), edges)

    def test_json_and_dot_outputs_are_deterministic(self) -> None:
        graph = self.graph()
        first = json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True)
        second = json.dumps(self.graph(), ensure_ascii=False, indent=2, sort_keys=True)
        self.assertEqual(first, second)
        self.assertIn('"jumping-child" -> "target" [label="jump"]', graph_module.dot(graph))

    def test_unresolved_jump_is_reported(self) -> None:
        document = {"nos": [{"uuid": "source", "uuidEnviarPara": "missing", "respostas": [], "filhos": []}]}
        graph = graph_module.build_graph(document)
        self.assertEqual(graph["unresolved_jumps"], [{"node": "source", "target": "missing", "type": "jump"}])

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
