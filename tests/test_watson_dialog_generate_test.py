from __future__ import annotations

import json
import unittest
from pathlib import Path

import watson_dialog_generate_test as generator


ROOT = Path(__file__).resolve().parents[1]


class GenerateDialogTestTests(unittest.TestCase):
    def test_generates_and_validates_a_path_including_target(self) -> None:
        document = json.loads((ROOT / "tests/fixtures/dialog_session.json").read_text(encoding="utf-8"))
        scenario = generator.generate(document, "confirm")
        self.assertEqual(scenario["expect"]["selected_nodes"], ["start", "confirm"])
        self.assertTrue(scenario["generated"]["runner_passed"])
        self.assertEqual(scenario["generated"]["actual_selected_nodes"], ["start", "confirm"])


if __name__ == "__main__": unittest.main()
