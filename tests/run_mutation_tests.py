"""Run targeted mutation tests without requiring a third-party mutation tool."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "watson_dialog_diff.py"
MUTANTS = (
    ("timestamps_are_not_ignored", 'DEFAULT_IGNORED_FIELDS = {"dataCriacao", "dataModificacao"}', "DEFAULT_IGNORED_FIELDS = set()"),
    ("uuid_matching_is_disabled", 'return {str(item["uuid"]): item for item in value}', "return None"),
    ("embedded_json_is_not_decoded", 'path.rsplit(".", 1)[-1] == "json"', 'path.rsplit(".", 1)[-1] == "not_json"'),
    ("tag_order_is_considered", 'if path.rsplit(".", 1)[-1] == "tags":', "if False:"),
    ("cli_never_signals_a_diff", 'return 1 if report["changes"] else 0', "return 0"),
)


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    killed = 0
    for name, original, replacement in MUTANTS:
        if original not in source:
            print(f"ERRO {name}: alvo da mutação não encontrado")
            return 2
        with tempfile.TemporaryDirectory() as directory:
            mutant = Path(directory) / "watson_dialog_diff.py"
            mutant.write_text(source.replace(original, replacement, 1), encoding="utf-8")
            environment = {**os.environ, "WATSON_DIALOG_DIFF_PATH": str(mutant)}
            result = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
        if result.returncode:
            killed += 1
            print(f"KILLED  {name}")
        else:
            print(f"SURVIVED {name}")
    print(f"Mutation score: {killed}/{len(MUTANTS)} mutantes detectados")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
