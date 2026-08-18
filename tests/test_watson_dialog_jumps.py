from __future__ import annotations

import json
import unittest
from pathlib import Path

from tare_dialog import jumps

ROOT = Path(__file__).resolve().parents[1]


class IncomingJumpsTests(unittest.TestCase):
    def test_lists_named_jump_sources_for_target(self) -> None:
        document = json.loads((ROOT / "tests/fixtures/graph.json").read_text(encoding="utf-8"))
        report = jumps.incoming_jumps(document, "target")
        self.assertEqual(report["summary"], {"incoming_jumps": 1})
        self.assertEqual(report["sources"], [{"node": "jumping-child", "name": "Filho com salto", "condition": None, "jump_selector": "body"}])


if __name__ == "__main__": unittest.main()
