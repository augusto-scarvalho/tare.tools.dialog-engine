"""Behavioral tests for the deterministic Watson Assistant JSON diff."""

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
MODULE_PATH = Path(os.environ.get("WATSON_DIALOG_DIFF_PATH", ROOT / "watson_dialog_diff.py"))
FIXTURES = ROOT / "tests" / "fixtures"
SPEC = importlib.util.spec_from_file_location("watson_dialog_diff_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
diff = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = diff
SPEC.loader.exec_module(diff)


class WatsonDialogDiffTests(unittest.TestCase):
    def report(self, current: dict, candidate: dict, include_timestamps: bool = False) -> dict:
        ignored = set() if include_timestamps else diff.DEFAULT_IGNORED_FIELDS
        return diff.summarize(current, candidate, ignored)

    def test_identical_document_has_no_changes(self) -> None:
        document = {"nos": [{"uuid": "node-1", "nome": "Boas-vindas", "tags": ["inicio"]}]}
        report = self.report(document, document)
        self.assertEqual(report["summary"], {"added": 0, "removed": 0, "changed": 0})
        self.assertEqual(report["changes"], [])

    def test_uuid_lists_ignore_reordering(self) -> None:
        current = {"entidades": [{"uuid": "a", "nome": "A"}, {"uuid": "b", "nome": "B"}]}
        candidate = {"entidades": [{"uuid": "b", "nome": "B"}, {"uuid": "a", "nome": "A"}]}
        self.assertEqual(self.report(current, candidate)["changes"], [])

    def test_tags_ignore_order_but_report_additions(self) -> None:
        current = {"nos": [{"uuid": "node", "nome": "N", "tags": ["produto", "vip"]}]}
        reordered = {"nos": [{"uuid": "node", "nome": "N", "tags": ["vip", "produto"]}]}
        candidate = {"nos": [{"uuid": "node", "nome": "N", "tags": ["vip", "produto", "novo"]}]}
        self.assertEqual(self.report(current, reordered)["changes"], [])
        changes = self.report(current, candidate)["changes"]
        self.assertEqual([(change["path"], change["kind"], change["after"]) for change in changes], [("tags", "added", "novo")])

    def test_reports_responses_unkeyed_lists_and_embedded_json(self) -> None:
        current = {
            "nos": [{
                "uuid": "node",
                "nome": "N",
                "respostas": [{"uuid": "answer", "textoResposta": "antes"}],
                "itens": ["um", "dois"],
                "json": '{"media":{"url":"antes.png","tipo":"imagem"}}',
            }]
        }
        candidate = {
            "nos": [{
                "uuid": "node",
                "nome": "N",
                "respostas": [{"uuid": "answer", "textoResposta": "depois"}],
                "itens": ["um", "três"],
                "json": '{"media":{"url":"depois.png","tipo":"imagem"}}',
            }]
        }
        changes = self.report(current, candidate)["changes"]
        by_path = {change["path"]: change for change in changes}
        self.assertEqual(by_path["respostas[uuid=answer].textoResposta"]["after"], "depois")
        self.assertEqual(by_path["itens[1]"]["after"], "três")
        self.assertEqual(by_path["json.media.url"]["after"], "depois.png")

    def test_synthetic_export_fixtures_cover_main_dialog_fields(self) -> None:
        current = diff.load_json(FIXTURES / "current.json")
        candidate = diff.load_json(FIXTURES / "candidate.json")
        changes = self.report(current, candidate)["changes"]
        self.assertEqual(len(changes), 4)
        self.assertEqual(
            {(change["path"], change["kind"]) for change in changes},
            {
                ("tags", "added"),
                ("respostas[uuid=resposta-demo].textoResposta", "changed"),
                ("itens[1]", "changed"),
                ("json.media.url", "changed"),
            },
        )

    def test_timestamps_are_optional(self) -> None:
        current = {"intencoes": [{"uuid": "intent", "nome": "saldo", "dataModificacao": "2026-01-01"}]}
        candidate = {"intencoes": [{"uuid": "intent", "nome": "saldo", "dataModificacao": "2026-02-01"}]}
        self.assertEqual(self.report(current, candidate)["changes"], [])
        included = self.report(current, candidate, include_timestamps=True)["changes"]
        self.assertEqual(included[0]["path"], "dataModificacao")

    def test_cli_exit_codes_and_json_bytes_are_deterministic(self) -> None:
        current = {"nos": []}
        candidate = {"nos": [{"nome": "novo", "uuid": "node", "tags": ["a", "b"]}]}
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            current_path = directory_path / "current.json"
            candidate_path = directory_path / "candidate.json"
            first_output = directory_path / "first.json"
            second_output = directory_path / "second.json"
            current_path.write_text(json.dumps(current), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            command = [sys.executable, str(MODULE_PATH), str(current_path), str(candidate_path), "--format", "json"]
            first = subprocess.run([*command, "--output", str(first_output)], check=False, capture_output=True, text=True)
            second = subprocess.run([*command, "--output", str(second_output)], check=False, capture_output=True, text=True)
            equal = subprocess.run([sys.executable, str(MODULE_PATH), str(current_path), str(current_path)], check=False, capture_output=True, text=True)
            self.assertEqual(first.returncode, 1)
            self.assertEqual(second.returncode, 1)
            self.assertEqual(first_output.read_bytes(), second_output.read_bytes())
            self.assertEqual(equal.returncode, 0)

    def test_invalid_json_is_reported(self) -> None:
        with self.assertRaises(ValueError):
            diff.load_json(FIXTURES / "invalid.json")


if __name__ == "__main__":
    unittest.main()
