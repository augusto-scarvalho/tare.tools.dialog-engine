"""Tests for shared document indexing, preflight checks, and model normalization."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from watson_dialog_document import DialogIndex, preflight_check


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


class WatsonDialogDocumentTests(unittest.TestCase):
    def test_preflight_check_on_legacy_and_v1_fixtures(self) -> None:
        legacy_meta = preflight_check(FIXTURES / "current.json")
        self.assertEqual(legacy_meta.format_type, "legacy")
        self.assertGreater(legacy_meta.node_count, 0)
        self.assertTrue(legacy_meta.is_safe)

        v1_meta = preflight_check(FIXTURES / "dialog_v1.json")
        self.assertEqual(v1_meta.format_type, "v1")
        self.assertGreater(v1_meta.node_count, 0)
        self.assertTrue(v1_meta.is_safe)

    def test_preflight_exceeding_byte_limit_raises_error(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            preflight_check(FIXTURES / "current.json", max_bytes=10)
        self.assertIn("excede o limite configurado", str(ctx.exception))

    def test_dialog_index_traversal_and_ancestors(self) -> None:
        legacy_doc = json.loads((FIXTURES / "dialog_session.json").read_text(encoding="utf-8"))
        index = DialogIndex(legacy_doc)
        summary = index.summary()
        self.assertGreater(summary["total_nodes"], 0)
        self.assertGreaterEqual(summary["root_nodes"], 1)

        # Roots inspection
        roots = index.get_roots()
        self.assertTrue(any(r["uuid"] == "start" for r in roots))

        # Hierarchy lookups
        child = index.get_node("confirm")
        self.assertIsNotNone(child)
        self.assertEqual(index.get_parent("confirm"), "start")
        ancestors = index.get_ancestors("confirm")
        self.assertEqual(len(ancestors), 1)
        self.assertEqual(ancestors[0]["uuid"], "start")

    def test_dialog_index_v1_normalization(self) -> None:
        v1_doc = json.loads((FIXTURES / "dialog_v1.json").read_text(encoding="utf-8"))
        index = DialogIndex(v1_doc)
        self.assertGreater(index.summary()["total_nodes"], 0)
        roots = index.get_roots()
        self.assertTrue(len(roots) > 0)


if __name__ == "__main__":
    unittest.main()
