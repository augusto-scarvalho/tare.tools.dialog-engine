"""Tests for Universal Dialog AST Explorer and Polymorphic Schema Adapter."""

import unittest
from pathlib import Path
import json

from watson_dialog_diff import load_json
from watson_dialog_explorer import (
    detect_dialog_format,
    explore_document,
    introspect_primitives,
    UniversalDialogDocument,
    DialogNode,
    DialogResponse,
    DialogSlot,
    DialogJump,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class DialogExplorerTests(unittest.TestCase):
    def test_detects_official_watson_v1_format(self) -> None:
        doc = load_json(FIXTURES_DIR / "watson_official_skill.json")
        fmt = detect_dialog_format(doc)
        self.assertEqual(fmt, "watson_v1_flat")

    def test_detects_nested_enterprise_format(self) -> None:
        doc = load_json(FIXTURES_DIR / "validation_legacy.json")
        fmt = detect_dialog_format(doc)
        self.assertEqual(fmt, "enterprise_nested")

    def test_explores_official_watson_v1_skill(self) -> None:
        raw_doc = load_json(FIXTURES_DIR / "watson_official_skill.json")
        doc = explore_document(raw_doc)

        self.assertEqual(doc.name, "Customer Banking Skill")
        self.assertEqual(doc.language, "pt-br")
        self.assertEqual(len(doc.intents), 2)
        self.assertEqual(len(doc.entities), 2)

        # Check root nodes order
        root_ids = [r.id for r in doc.roots]
        self.assertIn("node_welcome", root_ids)
        self.assertIn("node_balance", root_ids)
        self.assertIn("node_transfer_frame", root_ids)
        self.assertIn("node_fallback", root_ids)

        # Check welcome node rich responses
        welcome = doc.get_node("node_welcome")
        self.assertIsNotNone(welcome)
        self.assertEqual(len(welcome.responses), 3)  # text, option, whatsapp integration
        self.assertEqual(welcome.tags, ["onboarding", "portal"])

        # Check options in response
        option_resp = next(r for r in welcome.responses if r.response_type == "option")
        self.assertEqual(option_resp.title, "Como posso te ajudar hoje?")
        self.assertEqual(len(option_resp.options), 2)

        # Check balance node image and context
        balance = doc.get_node("node_balance")
        self.assertIsNotNone(balance)
        self.assertEqual(balance.context.get("service_requested"), "balance")
        image_resp = next(r for r in balance.responses if r.response_type == "image")
        self.assertEqual(image_resp.media_urls, ["https://example.corp/media/chart.png"])
        self.assertEqual(image_resp.title, "Extrato Consolidado")

        # Check frame node and slot hierarchy
        frame = doc.get_node("node_transfer_frame")
        self.assertIsNotNone(frame)
        self.assertEqual(len(frame.slots), 1)
        slot = frame.slots[0]
        self.assertEqual(slot.variable_name, "destination_account")
        self.assertTrue(slot.required)
        self.assertEqual(len(slot.handlers), 3)  # focus, nomatch, filled

        # Check filled handler jump
        filled_handler = next(h for h in slot.handlers if h.event_name == "filled")
        self.assertIsNotNone(filled_handler.jump)
        self.assertEqual(filled_handler.jump.target_id, "node_confirmation")

    def test_explores_nested_enterprise_document(self) -> None:
        raw_doc = load_json(FIXTURES_DIR / "validation_legacy.json")
        doc = explore_document(raw_doc)

        self.assertEqual(doc.format_detected, "enterprise_nested")
        self.assertGreater(len(doc.roots), 0)
        self.assertGreater(len(doc.nodes), 0)

    def test_introspect_primitives_summary(self) -> None:
        raw_doc = load_json(FIXTURES_DIR / "watson_official_skill.json")
        summary = introspect_primitives(raw_doc)

        self.assertEqual(summary["format_detected"], "watson_v1_flat")
        self.assertEqual(summary["intents_count"], 2)
        self.assertEqual(summary["entities_count"], 2)
        self.assertTrue(summary["has_multimedia"])
        self.assertTrue(summary["has_slots"])
        self.assertTrue(summary["has_jumps"])
        self.assertIn("whatsapp", summary["discovered_channels"])
        self.assertIn("default", summary["discovered_channels"])
        self.assertIn("image", summary["discovered_response_types"])
        self.assertIn("option", summary["discovered_response_types"])
        self.assertIn("pause", summary["discovered_response_types"])
        self.assertGreater(summary["conditions_count"], 0)


if __name__ == "__main__":
    unittest.main()
