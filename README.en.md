# Watson Assistant Dialog Diff & Tooling Suite

Semantic comparator, validator, test runner, graph engine, and triage console for Watson Assistant Dialog exports. Collections identified by `uuid` are compared by unique identifier, ensuring that key reordering produces no false positives.

## Structure

```text
input/
├── current.json       # currently published production export
└── candidate.json     # candidate export under evaluation
output/                # generated diffs and triage artifacts
watson_dialog_diff.py
watson_dialog_validate.py
watson_dialog_graph.py
watson_dialog_test.py
watson_dialog_shard.py
watson_dialog_topology.py
triage_viewer.html     # Interactive Triage & Knowledge Base Console
docs/
├── architecture/EXTERNAL_MEMORY_DIFF_AND_SHARDING.md
├── architecture/VALIDATION_AUDIT_CALIBRATION.md
├── operations/TRIAGE_AND_DOGFOODING_GUIDE.md
└── operations/LARGE_EXPORT_PLAYBOOK.md
```

Files under `input/` are ignored by Git. Test fixtures live strictly in `tests/fixtures/` and are synthetic and sanitized.

## CLI Usage

### 1. Semantic Diff
```bash
python3 watson_dialog_diff.py input/current.json input/candidate.json --output output/diff.md
```

Options:
- `--format json`: Structured machine-readable diff payload.
- `--include-timestamps`: Compares creation and modification timestamps.
- `--max-changes 50`: Limit of changes per modified entity in Markdown.
- `--engine auto|dom|external`: `auto` selects DOM for small files and bounded external engine for files > 16 MiB.
- `--index-backend auto|transient|mmap`: `transient` spools one document at a time; `mmap` uses strictly bounded memory scanning.

### 2. Validation & Diagnostic Suite
```bash
python3 watson_dialog_validate.py input/current.json --summary-only
```
Options:
- `--summary-only`: Output consolidated issue counts.
- `--check-variables`: Also validates context variables outside declared registry.
- `--max-input-bytes N`: Size guard limit in bytes (defaults to 50 MiB).

### 3. Graph Analysis & Reachability
```bash
python3 watson_dialog_graph.py input/current.json --format mermaid --output output/graph.mmd
```

### 4. Scenario Testing
```bash
python3 watson_dialog_test.py scenarios.json --skill input/current.json
```

## Large-Document Safety

1. **Size Guardrail**: `--max-input-bytes` applies before parsing.
2. **Preflight**: `preflight_check()` counts structure using `mmap` without full `json.load()`.
3. **Adaptive External Diff**: Compares digests first and only materializes modified branches.
4. **Zero Spurious Jumps**: Disregards tie-breaks on ambiguous legacy sequence sets.
