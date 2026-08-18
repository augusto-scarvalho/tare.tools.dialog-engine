"""Tests verifying large document safety contracts, bounded summaries, and size guards."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import tare_dialog.diff_engine as diff
import tare_dialog.graph as graph
import tare_dialog.validator as validate


ROOT = Path(__file__).resolve().parents[1]
DIFF_CLI = ROOT / "src/tare_dialog/diff_engine.py"
VALIDATE_CLI = ROOT / "src/tare_dialog/validator.py"
GRAPH_CLI = ROOT / "src/tare_dialog/graph.py"


def generate_synthetic_large_dialog(node_count: int = 1500) -> dict:
    nodes = []
    for i in range(node_count):
        nodes.append({
            "uuid": f"node-{i:05d}",
            "nome": f"Node {i}",
            "condicao": f"#intent_{i % 50} && @entity_{i % 30}",
            "sequencia": i,
            "respostas": [
                {
                    "uuid": f"resp-{i:05d}",
                    "tipoRespostaNomeJSON": "text",
                    "idTipoResposta": 1,
                    "sequenciaBloco": 1,
                    "sequenciaItem": 1,
                }
            ],
            "filhos": [],
            "slots": [],
        })
    return {
        "intencoes": [{"uuid": f"intent-{i}", "nome": f"intent_{i}"} for i in range(50)],
        "entidades": [{"uuid": f"entity-{i}", "nome": f"entity_{i}"} for i in range(30)],
        "variaveisContexto": [],
        "nos": nodes,
    }


class LargeDocumentSafetyTests(unittest.TestCase):
    def test_load_json_rejects_exceeding_max_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "large.json"
            content = {"nos": [{"uuid": f"n{i}", "nome": "A" * 500} for i in range(200)]}
            file_path.write_text(json.dumps(content), encoding="utf-8")

            # Must fail when size exceeds limit
            with self.assertRaises(ValueError) as ctx:
                diff.load_json(file_path, max_bytes=1024)
            self.assertIn("excede o limite configurado", str(ctx.exception))

            # Must succeed when limit is adequate
            loaded = diff.load_json(file_path, max_bytes=10 * 1024 * 1024)
            self.assertEqual(len(loaded["nos"]), 200)

    def test_diff_summary_only_mode_reduces_memory_and_output(self) -> None:
        doc1 = generate_synthetic_large_dialog(300)
        doc2 = generate_synthetic_large_dialog(300)
        # Introduce modifications
        for i in range(50):
            doc2["nos"][i]["nome"] = f"Modified {i}"

        # Full summarize
        full_report = diff.summarize(doc1, doc2, diff.DEFAULT_IGNORED_FIELDS, summary_only=False)
        self.assertEqual(full_report["summary"]["changed"], 50)
        self.assertEqual(len(full_report["changes"]), 50)

        # Summary-only summarize
        summary_report = diff.summarize(doc1, doc2, diff.DEFAULT_IGNORED_FIELDS, summary_only=True)
        self.assertEqual(summary_report["summary"]["changed"], 50)
        self.assertEqual(len(summary_report["changes"]), 0)

    def test_cli_honors_environment_max_input_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            p1 = Path(temp_dir) / "doc1.json"
            p2 = Path(temp_dir) / "doc2.json"
            payload = {"nos": [{"uuid": "n1", "nome": "x" * 800}]}
            p1.write_text(json.dumps(payload), encoding="utf-8")
            p2.write_text(json.dumps(payload), encoding="utf-8")
            env = {**os.environ, "WATSON_DIALOG_MAX_BYTES": "500"}
            result = subprocess.run(
                [sys.executable, str(DIFF_CLI), str(p1), str(p2)],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("excede o limite configurado", result.stderr)

    def test_cli_diff_supports_max_input_bytes_and_summary_only(self) -> None:
        doc1 = generate_synthetic_large_dialog(100)
        doc2 = generate_synthetic_large_dialog(100)
        doc2["nos"][0]["nome"] = "Changed"

        with tempfile.TemporaryDirectory() as temp_dir:
            p1 = Path(temp_dir) / "doc1.json"
            p2 = Path(temp_dir) / "doc2.json"
            out = Path(temp_dir) / "out.json"
            p1.write_text(json.dumps(doc1), encoding="utf-8")
            p2.write_text(json.dumps(doc2), encoding="utf-8")

            # Test --summary-only flag
            res = subprocess.run(
                [sys.executable, str(DIFF_CLI), str(p1), str(p2), "--format", "json", "--summary-only", "--output", str(out)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res.returncode, 1)
            loaded = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(loaded["summary"]["changed"], 1)
            self.assertEqual(loaded["changes"], [])

            # Test --max-input-bytes flag rejects
            res_rejected = subprocess.run(
                [sys.executable, str(DIFF_CLI), str(p1), str(p2), "--max-input-bytes", "500"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res_rejected.returncode, 2)
            self.assertIn("excede o limite configurado", res_rejected.stderr)

    def test_validate_summary_only_and_max_issues(self) -> None:
        doc = generate_synthetic_large_dialog(200)
        # Create unknown intents
        for i in range(50):
            doc["nos"][i]["condicao"] = f"#unknown_intent_{i}"

        full_val = validate.validate(doc, summary_only=False)
        self.assertGreaterEqual(full_val["summary"]["issues"], 50)
        self.assertGreaterEqual(len(full_val["issues"]), 50)

        sum_val = validate.validate(doc, summary_only=True)
        self.assertGreaterEqual(sum_val["summary"]["issues"], 50)
        self.assertEqual(len(sum_val["issues"]), 0)

        capped_val = validate.validate(doc, max_issues=5)
        self.assertEqual(len(capped_val["issues"]), 5)

    def test_graph_summary_only_mode(self) -> None:
        doc = generate_synthetic_large_dialog(150)
        full_g = graph.build_graph(doc, summary_only=False)
        self.assertIn("vertices", full_g)
        self.assertEqual(len(full_g["vertices"]), 150)

        sum_g = graph.build_graph(doc, summary_only=True)
        self.assertNotIn("vertices", sum_g)
        self.assertIn("summary", sum_g)
        self.assertEqual(sum_g["summary"]["vertex_count"], 150)

    def test_scaling_synthetic_1000_nodes_execution_speed(self) -> None:
        doc = generate_synthetic_large_dialog(1000)
        start = time.perf_counter()
        report = validate.validate(doc, summary_only=True)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 2.0, "Validation of 1000 synthetic nodes must complete in under 2 seconds")
        self.assertEqual(report["summary"]["issues_by_severity"].get("error", 0), 0)


if __name__ == "__main__":
    unittest.main()
