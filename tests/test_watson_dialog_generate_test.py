from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

from tare_dialog import topology

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = Path(os.environ.get("WATSON_DIALOG_GENERATE_TEST_PATH", ROOT / "src/tare_dialog/generate_test.py"))
SPEC = importlib.util.spec_from_file_location("watson_dialog_generate_test_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
generator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = generator
SPEC.loader.exec_module(generator)


class GenerateDialogTestTests(unittest.TestCase):
    def test_generates_and_validates_a_path_including_target(self) -> None:
        document = json.loads((ROOT / "tests/fixtures/dialog_session.json").read_text(encoding="utf-8"))
        scenario = generator.generate(document, "confirm")
        self.assertEqual(scenario["expect"]["selected_nodes"], ["start", "confirm"])
        self.assertTrue(scenario["generated"]["runner_passed"])
        self.assertEqual(scenario["generated"]["actual_selected_nodes"], ["start", "confirm"])

    def test_generates_one_scenario_per_topology_item_from_leaves_to_root(self) -> None:
        document = json.loads((ROOT / "tests/fixtures/dialog_session.json").read_text(encoding="utf-8"))
        suite = generator.generate_topology(document, topology.topology(document, "frame"))
        self.assertEqual(suite["order"], "leaves_to_root")
        self.assertEqual([scenario["generated"]["target"] for scenario in suite["scenarios"]], ["city-slot", "date-slot", "frame"])
        self.assertEqual([scenario["generated"]["topology_position"] for scenario in suite["scenarios"]], [1, 2, 3])
        self.assertEqual(suite["scenarios"][1]["generated"]["prerequisite_slots"], ["city-slot"])
        self.assertEqual(suite["summary"], {"scenarios": 3, "runner_passed": 3, "runner_failed": 0})

    def test_topology_order_adds_ancestors_after_descendants(self) -> None:
        document = json.loads((ROOT / "tests/fixtures/dialog_session.json").read_text(encoding="utf-8"))
        suite = generator.generate_topology(document, topology.topology(document, "start"))
        self.assertEqual([scenario["generated"]["target"] for scenario in suite["scenarios"]], ["confirm", "start"])


if __name__ == "__main__": unittest.main()
