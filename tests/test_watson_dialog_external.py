"""Parity and safety tests for external-memory indexing and semantic sharding."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import watson_dialog_external as external_module
from watson_dialog_external import CompactGraph, DialogSourceIndex
from watson_dialog_graph import build_graph
from watson_dialog_resources import ResourceBudget, resolve_jobs

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def edge_set(graph: dict) -> set[tuple[str, str, str]]:
    return {(edge["node"], edge["target"], edge["type"]) for edge in graph["edges"] if edge["type"] != "tree_restart"}


class ExternalMemoryIndexTests(unittest.TestCase):
    def test_legacy_compact_graph_has_exact_structural_parity(self) -> None:
        path = FIXTURES / "graph.json"
        incumbent = build_graph(json.loads(path.read_text(encoding="utf-8")))
        with DialogSourceIndex.open(path, max_bytes=0) as source_index:
            compact = CompactGraph.from_index(source_index)
            self.assertEqual(set(compact.vertex_ids), {vertex["id"] for vertex in incumbent["vertices"]})
            self.assertEqual(set(compact.iter_edges()), edge_set(incumbent))

    def test_v1_compact_graph_has_exact_structural_parity(self) -> None:
        path = FIXTURES / "dialog_v1.json"
        incumbent = build_graph(json.loads(path.read_text(encoding="utf-8")))
        with DialogSourceIndex.open(path, max_bytes=0) as source_index:
            compact = CompactGraph.from_index(source_index)
            self.assertEqual(set(compact.vertex_ids), {vertex["id"] for vertex in incumbent["vertices"]})
            self.assertEqual(set(compact.iter_edges()), edge_set(incumbent))

    def test_source_index_does_not_call_json_load(self) -> None:
        with mock.patch("json.load", side_effect=AssertionError("DOM load forbidden")):
            with DialogSourceIndex.open(FIXTURES / "graph.json", max_bytes=0) as source_index:
                self.assertEqual(source_index.summary()["records"], 6)
                self.assertEqual(source_index.load_record("jumping-child")["uuid"], "jumping-child")

    def test_large_flat_export_is_indexed_without_dom_materialization(self) -> None:
        document = {
            "nos": [
                {
                    "uuid": f"node-{i:05d}",
                    "nome": "payload-" + ("x" * 256),
                    "sequencia": i,
                    "condicao": "true",
                    "filhos": [],
                    "slots": [],
                }
                for i in range(4000)
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.json"
            path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            with mock.patch("json.load", side_effect=AssertionError("DOM load forbidden")):
                with DialogSourceIndex.open(path, max_bytes=0) as source_index:
                    self.assertEqual(source_index.summary()["graph_vertices"], 4000)
                    compact = CompactGraph.from_index(source_index)
                    self.assertEqual(compact.summary()["vertices"], 4000)
                    self.assertLess(compact.memory_bytes(), 250_000)


    def test_legacy_stream_fast_path_does_not_rescan_nested_children(self) -> None:
        document = {
            "nos": [{
                "uuid": "root",
                "nome": "root",
                "filhos": [{
                    "uuid": "child",
                    "nome": "child",
                    "filhos": [{"uuid": "leaf", "nome": "leaf", "filhos": [], "slots": []}],
                    "slots": [],
                }],
                "slots": [],
            }]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested.json"
            path.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            payload = path.read_bytes()
            marker = b'"filhos":'
            children_start = payload.index(marker) + len(marker)
            while payload[children_start] in b" \t\r\n":
                children_start += 1

            calls: list[int] = []
            original = external_module._MappedJson.value_end

            def counted(mapped: object, pos: int, limit: int | None = None) -> int:
                calls.append(pos)
                return original(mapped, pos, limit)

            with mock.patch.object(external_module._MappedJson, "value_end", new=counted):
                with DialogSourceIndex.open(path, max_bytes=0, capture_details=True) as source_index:
                    self.assertEqual(set(source_index.records), {"root", "child", "leaf"})
            self.assertNotIn(children_start, calls)

    def test_capture_details_spools_local_records_and_avoids_changed_root_rescan(self) -> None:
        path = FIXTURES / "graph.json"
        with DialogSourceIndex.open(path, max_bytes=0, capture_details=True) as source_index:
            self.assertGreater(source_index.summary()["local_spool_bytes"], 0)
            expected = source_index.load_local_record("root")
            with mock.patch.object(
                external_module._MappedJson,
                "object_fields",
                side_effect=AssertionError("changed-root rescan forbidden when local spool exists"),
            ):
                payload = source_index.local_record_bytes("root")
                self.assertEqual(json.loads(payload), expected)

    def test_legacy_stream_falls_back_safely_when_uuid_follows_children(self) -> None:
        # JSON object order is not normative.  The optimized path may need one
        # replay when the identifier appears after its nested container, but it
        # must remain semantically correct.
        raw = b'{"nos":[{"filhos":[{"uuid":"child","filhos":[],"slots":[]}],"uuid":"root","slots":[]}]}'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "uuid-after-children.json"
            path.write_bytes(raw)
            children_start = raw.index(b'"filhos":') + len(b'"filhos":')
            calls: list[int] = []
            original = external_module._MappedJson.value_end

            def counted(mapped: object, pos: int, limit: int | None = None) -> int:
                calls.append(pos)
                return original(mapped, pos, limit)

            with mock.patch.object(external_module._MappedJson, "value_end", new=counted):
                with DialogSourceIndex.open(path, max_bytes=0) as source_index:
                    self.assertEqual(source_index.records["child"].parent_id, "root")
            self.assertIn(children_start, calls)

    def test_semantic_sharding_is_complete_balanced_and_local(self) -> None:
        roots = []
        for root_index in range(8):
            children = []
            for child_index in range(50):
                node_id = f"r{root_index}-c{child_index:03d}"
                children.append({
                    "uuid": node_id,
                    "sequencia": child_index,
                    "condicao": "true",
                    "uuidEnviarPara": f"r{root_index}-c{(child_index + 7) % 50:03d}" if child_index % 10 == 0 else None,
                    "filhos": [],
                    "slots": [],
                })
            roots.append({
                "uuid": f"root-{root_index}",
                "folder": True,
                "sequencia": root_index,
                "condicao": "true",
                "filhos": children,
                "slots": [],
            })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graph.json"
            path.write_text(json.dumps({"nos": roots}), encoding="utf-8")
            with DialogSourceIndex.open(path, max_bytes=0) as source_index:
                compact = CompactGraph.from_index(source_index)
                plan = compact.semantic_shards(8, tolerance=1.15)
                assigned = [vertex for shard in plan["shards"] for vertex in shard["vertices"]]
                self.assertEqual(len(assigned), len(set(assigned)))
                self.assertEqual(set(assigned), set(compact.vertex_ids))
                self.assertLess(plan["metrics"]["max_load_ratio"], 1.25)

                shard_of = {vertex: shard["shard"] for shard in plan["shards"] for vertex in shard["vertices"]}
                semantic_cut = sum(shard_of[s] != shard_of[d] for s, d, _ in compact.iter_edges()) / len(compact.src)
                hash_shard = lambda value: int(hashlib.sha256(value.encode()).hexdigest()[:8], 16) % 8
                hash_cut = sum(hash_shard(s) != hash_shard(d) for s, d, _ in compact.iter_edges()) / len(compact.src)
                self.assertLess(semantic_cut, hash_cut * 0.35)

    def test_resource_budget_auto_jobs_is_conservative(self) -> None:
        budget = ResourceBudget(usable_cpus=16, available_memory_bytes=8 * 1024**3, temp_free_bytes=20 * 1024**3, max_jobs_cap=8)
        self.assertEqual(resolve_jobs("auto", 100, budget), 8)
        self.assertEqual(resolve_jobs("3", 100, budget), 3)
        self.assertEqual(budget.logical_shards(8, 100, oversubscription=4), 13)


if __name__ == "__main__":
    unittest.main()
