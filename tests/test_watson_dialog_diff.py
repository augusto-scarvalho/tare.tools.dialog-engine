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
from types import SimpleNamespace
from unittest.mock import patch


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

    def test_external_engine_has_exact_parity_on_flat_fixture(self) -> None:
        current_path = FIXTURES / "current.json"
        candidate_path = FIXTURES / "candidate.json"
        ignored = set(diff.DEFAULT_IGNORED_FIELDS)
        incumbent = diff.summarize(diff.load_json(current_path), diff.load_json(candidate_path), ignored)
        external = diff.summarize_external_paths(
            current_path,
            candidate_path,
            ignored,
            max_bytes=0,
            jobs=1,
        )
        self.assertEqual(external, incumbent)

    def test_external_engine_preserves_nested_paths_moves_and_slots(self) -> None:
        current = {
            "nos": [
                {
                    "uuid": "root-a",
                    "nome": "A",
                    "filhos": [{"uuid": "move", "nome": "Mover", "filhos": [], "slots": []}],
                    "slots": [{
                        "uuid": "slot-a",
                        "identificador": "cidade",
                        "filhos": [{"uuid": "slot-child", "nome": "Antes", "filhos": [], "slots": []}],
                    }],
                },
                {"uuid": "root-b", "nome": "B", "filhos": [], "slots": []},
            ]
        }
        candidate = {
            "nos": [
                {
                    "uuid": "root-a",
                    "nome": "A",
                    "filhos": [{"uuid": "new-child", "nome": "Novo", "filhos": [], "slots": []}],
                    "slots": [{
                        "uuid": "slot-a",
                        "identificador": "cidade",
                        "filhos": [{"uuid": "slot-child", "nome": "Depois", "filhos": [], "slots": []}],
                    }],
                },
                {
                    "uuid": "root-b",
                    "nome": "B",
                    "filhos": [{"uuid": "move", "nome": "Mover", "filhos": [], "slots": []}],
                    "slots": [],
                },
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            current_path = Path(directory) / "current.json"
            candidate_path = Path(directory) / "candidate.json"
            current_path.write_text(json.dumps(current), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            ignored = set(diff.DEFAULT_IGNORED_FIELDS)
            incumbent = diff.summarize(current, candidate, ignored)
            external = diff.summarize_external_paths(
                current_path,
                candidate_path,
                ignored,
                max_bytes=0,
                jobs=1,
            )
            self.assertEqual(external, incumbent)

    def test_external_engine_include_timestamps_is_not_false_negative(self) -> None:
        current = {"nos": [{"uuid": "node", "nome": "N", "dataModificacao": "2026-01-01", "filhos": [], "slots": []}]}
        candidate = {"nos": [{"uuid": "node", "nome": "N", "dataModificacao": "2026-02-01", "filhos": [], "slots": []}]}
        with tempfile.TemporaryDirectory() as directory:
            current_path = Path(directory) / "current.json"
            candidate_path = Path(directory) / "candidate.json"
            current_path.write_text(json.dumps(current), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            incumbent = diff.summarize(current, candidate, set())
            external = diff.summarize_external_paths(current_path, candidate_path, set(), max_bytes=0, jobs=1)
            self.assertEqual(external, incumbent)

    def test_cli_external_parallel_is_deterministic_and_matches_dom(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            current_path = directory_path / "current.json"
            candidate_path = directory_path / "candidate.json"
            dom_output = directory_path / "dom.json"
            external_output = directory_path / "external.json"
            current = {
                "nos": [
                    {"uuid": f"node-{index:03d}", "nome": f"N {index}", "valor": index, "filhos": [], "slots": []}
                    for index in range(40)
                ]
            }
            candidate = json.loads(json.dumps(current))
            for index in (3, 9, 17, 31):
                candidate["nos"][index]["valor"] += 100
            current_path.write_text(json.dumps(current), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            base = [sys.executable, str(MODULE_PATH), str(current_path), str(candidate_path), "--format", "json", "--max-input-bytes", "0"]
            dom = subprocess.run([*base, "--engine", "dom", "--output", str(dom_output)], check=False, capture_output=True, text=True)
            external = subprocess.run(
                [*base, "--engine", "external", "--jobs", "2", "--output", str(external_output)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(dom.returncode, 1, dom.stderr)
            self.assertEqual(external.returncode, 1, external.stderr)
            self.assertEqual(external_output.read_bytes(), dom_output.read_bytes())

    def test_v1_external_diff_matches_dom_for_change_insert_remove_and_reorder(self) -> None:
        current = {
            "dialog_nodes": [
                {"dialog_node": "a", "type": "standard", "conditions": "#a", "title": "A"},
                {"dialog_node": "b", "type": "standard", "conditions": "#b", "title": "B"},
                {"dialog_node": "c", "type": "standard", "conditions": "#c", "title": "C"},
            ],
            "metadata": {"version": 1},
        }
        candidate = {
            "dialog_nodes": [
                {"dialog_node": "b", "type": "standard", "conditions": "#b2", "title": "B"},
                {"dialog_node": "a", "type": "standard", "conditions": "#a", "title": "A"},
                {"dialog_node": "d", "type": "standard", "conditions": "#d", "title": "D"},
            ],
            "metadata": {"version": 2},
        }
        with tempfile.TemporaryDirectory() as directory:
            current_path = Path(directory) / "current.json"
            candidate_path = Path(directory) / "candidate.json"
            current_path.write_text(json.dumps(current), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            ignored = set(diff.DEFAULT_IGNORED_FIELDS)
            incumbent = diff.summarize(current, candidate, ignored)
            for backend in ("mmap", "transient"):
                external = diff.summarize_external_paths(
                    current_path,
                    candidate_path,
                    ignored,
                    max_bytes=0,
                    jobs=2,
                    index_backend=backend,
                )
                self.assertEqual(external, incumbent, backend)

    def test_v1_external_summary_only_uses_atomic_dom_count(self) -> None:
        current = {"dialog_nodes": [{"dialog_node": "a", "title": "A", "conditions": "#a", "output": {"x": 1, "y": 2}}]}
        candidate = {"dialog_nodes": [{"dialog_node": "a", "title": "A2", "conditions": "#b", "output": {"x": 3, "y": 4}}]}
        with tempfile.TemporaryDirectory() as directory:
            current_path = Path(directory) / "current.json"
            candidate_path = Path(directory) / "candidate.json"
            current_path.write_text(json.dumps(current), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            ignored = set(diff.DEFAULT_IGNORED_FIELDS)
            incumbent = diff.summarize(current, candidate, ignored, summary_only=True)
            external = diff.summarize_external_paths(
                current_path,
                candidate_path,
                ignored,
                summary_only=True,
                max_bytes=0,
                jobs=2,
                index_backend="mmap",
            )
            self.assertEqual(external, incumbent)
            self.assertGreater(external["summary"]["changed"], 1)

    def test_v1_external_ignored_timestamp_alignment_matches_dom(self) -> None:
        current = {
            "dialog_nodes": [
                {"dialog_node": "a", "title": "A", "dataModificacao": "2026-01-01"},
                {"dialog_node": "b", "title": "B"},
            ]
        }
        candidate = {
            "dialog_nodes": [
                {"dialog_node": "a", "title": "A", "dataModificacao": "2026-02-01"},
                {"dialog_node": "b", "title": "B"},
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            current_path = Path(directory) / "current.json"
            candidate_path = Path(directory) / "candidate.json"
            current_path.write_text(json.dumps(current), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            ignored = set(diff.DEFAULT_IGNORED_FIELDS)
            incumbent = diff.summarize(current, candidate, ignored)
            external = diff.summarize_external_paths(
                current_path,
                candidate_path,
                ignored,
                max_bytes=0,
                jobs=1,
                index_backend="mmap",
            )
            self.assertEqual(external, incumbent)

    def test_v1_cli_external_is_byte_exact_with_dom(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            current_path = directory_path / "current.json"
            candidate_path = directory_path / "candidate.json"
            dom_output = directory_path / "dom.json"
            external_output = directory_path / "external.json"
            current = {
                "dialog_nodes": [
                    {"dialog_node": f"n-{index:03d}", "type": "standard", "conditions": f"#{index}", "title": f"N {index}"}
                    for index in range(80)
                ]
            }
            candidate = json.loads(json.dumps(current))
            candidate["dialog_nodes"][11]["conditions"] = "#changed"
            candidate["dialog_nodes"].insert(25, {"dialog_node": "inserted", "type": "standard", "conditions": "#new"})
            candidate["dialog_nodes"].pop(61)
            current_path.write_text(json.dumps(current), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            base = [sys.executable, str(MODULE_PATH), str(current_path), str(candidate_path), "--format", "json", "--max-input-bytes", "0"]
            dom = subprocess.run([*base, "--engine", "dom", "--output", str(dom_output)], check=False, capture_output=True, text=True)
            external = subprocess.run(
                [*base, "--engine", "external", "--index-backend", "mmap", "--jobs", "2", "--output", str(external_output)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(dom.returncode, 1, dom.stderr)
            self.assertEqual(external.returncode, 1, external.stderr)
            self.assertEqual(external_output.read_bytes(), dom_output.read_bytes())

    def test_auto_engine_selection_is_resource_aware_above_threshold(self) -> None:
        mib = 1024 * 1024
        with tempfile.TemporaryDirectory() as directory:
            current_path = Path(directory) / "current.json"
            candidate_path = Path(directory) / "candidate.json"
            with current_path.open("wb") as file:
                file.truncate(20 * mib)
            with candidate_path.open("wb") as file:
                file.truncate(20 * mib)

            fat = diff.ResourceBudget(usable_cpus=16, available_memory_bytes=64 * 1024**3, temp_free_bytes=100 * 1024**3, max_jobs_cap=16)
            constrained = diff.ResourceBudget(usable_cpus=4, available_memory_bytes=1 * 1024**3, temp_free_bytes=20 * 1024**3, max_jobs_cap=4)
            unknown = diff.ResourceBudget(usable_cpus=2, available_memory_bytes=None, temp_free_bytes=None, max_jobs_cap=2)

            self.assertEqual(diff.choose_diff_engine(current_path, candidate_path, budget=fat), "dom")
            self.assertEqual(diff.choose_diff_engine(current_path, candidate_path, budget=constrained), "external")
            self.assertEqual(diff.choose_diff_engine(current_path, candidate_path, budget=unknown), "external")
            self.assertEqual(diff.choose_diff_engine(current_path, candidate_path, requested="external", budget=fat), "external")
            with patch.dict(os.environ, {"WATSON_DIALOG_EXTERNAL_THRESHOLD_BYTES": str(1 * mib)}):
                self.assertEqual(diff.choose_diff_engine(current_path, candidate_path, budget=fat), "external")

    def test_auto_engine_small_file_remains_dom_fast_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            current_path = Path(directory) / "current.json"
            candidate_path = Path(directory) / "candidate.json"
            current_path.write_text("{}", encoding="utf-8")
            candidate_path.write_text("{}", encoding="utf-8")
            constrained = diff.ResourceBudget(usable_cpus=1, available_memory_bytes=32 * 1024**2, temp_free_bytes=None, max_jobs_cap=1)
            self.assertEqual(diff.choose_diff_engine(current_path, candidate_path, budget=constrained), "dom")

    def test_ordered_sequence_tokens_detect_digest_collision_exactly(self) -> None:
        class FakeIndex:
            def __init__(self, values: dict[int, bytes]) -> None:
                self.values = values

            def ordered_item_stable_bytes(self, ref: SimpleNamespace) -> bytes:
                return self.values[ref.ordinal]

        left = SimpleNamespace(ordinal=0, stable_digest="forced-collision")
        same = SimpleNamespace(ordinal=1, stable_digest="forced-collision")
        different = SimpleNamespace(ordinal=2, stable_digest="forced-collision")
        index = FakeIndex({0: b'{"a":1}', 1: b'{"a":1}', 2: b'{"a":2}'})
        current_tokens, candidate_tokens = diff._ordered_sequence_tokens(index, [left], index, [same, different])
        self.assertEqual(current_tokens[0], candidate_tokens[0])
        self.assertNotEqual(current_tokens[0], candidate_tokens[1])


if __name__ == "__main__":
    unittest.main()
