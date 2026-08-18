"""Test suite ensuring integrity and semantic validity of the Watson Assistant Conformance Catalog."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "conformance" / "conformance_catalog.json"


class ConformanceCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(CATALOG_PATH.exists(), "Conformance catalog must exist at conformance/conformance_catalog.json")
        self.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    def test_catalog_structure_and_enums(self) -> None:
        self.assertIn("entries", self.catalog)
        self.assertIn("status_enum", self.catalog)
        self.assertIn("oracle_types", self.catalog)

        valid_statuses = set(self.catalog["status_enum"])
        valid_oracle_types = set(self.catalog["oracle_types"])

        for entry in self.catalog["entries"]:
            self.assertTrue(entry["id"].startswith("CONF-"), f"Entry id must follow CONF- prefix: {entry['id']}")
            self.assertIn(entry["status"], valid_statuses, f"Invalid status in {entry['id']}")
            self.assertIn(entry["oracle_type"], valid_oracle_types, f"Invalid oracle_type in {entry['id']}")
            self.assertTrue(entry["rule_source"].startswith("http"), f"rule_source must be a URL in {entry['id']}")
            self.assertTrue(len(entry["description"]) > 10, f"Description too short in {entry['id']}")
            self.assertTrue(len(entry["evidence_test"]) > 5, f"evidence_test missing in {entry['id']}")

    def test_all_categories_have_provenance(self) -> None:
        categories = {entry["category"] for entry in self.catalog["entries"]}
        expected_categories = {
            "tree_evaluation",
            "conditions",
            "spel_expression",
            "slots_and_handlers",
            "digressions",
            "transitions",
            "integrations_webhooks_actions",
        }
        self.assertTrue(expected_categories.issubset(categories))


if __name__ == "__main__":
    unittest.main()
