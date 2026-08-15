from __future__ import annotations
import json
import unittest
from pathlib import Path
import watson_dialog_topology as topology

ROOT = Path(__file__).resolve().parents[1]

class TopologyTests(unittest.TestCase):
    def test_returns_ancestors_slots_handlers_and_children_without_jumps(self) -> None:
        document = json.loads((ROOT / "tests/fixtures/graph.json").read_text(encoding="utf-8"))
        result = topology.topology(document, "slot-reprompt")
        self.assertEqual([item["uuid"] for item in result["ancestors"]], ["root", "customer-name", "slot-reprompt"])
        self.assertEqual(result["descendants"]["kind"], "slot_handler")
        root = topology.topology(document, "root")["descendants"]
        self.assertEqual(root["slots"][0]["kind"], "slot")
        self.assertEqual(root["slots"][0]["handlers"][0]["uuid"], "slot-reprompt")

if __name__ == "__main__": unittest.main()
