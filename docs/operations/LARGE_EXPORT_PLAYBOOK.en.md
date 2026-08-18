# Playbook — Large Watson Assistant Exports

**Status:** CURRENT operational guidance.  
**Scope:** Safe memory-bounded operations on production exports (> 50 MiB).

## 1. Operational Principle

Real customer exports are local input, never source code.
```text
input/current.json
input/candidate.json
```
These files are ignored by `input/*.json`. Never force-add them to Git.

## 2. Preflight

Before full diff execution:
```bash
python3 watson_dialog_shard.py input/current.json --summary-only --max-input-bytes 0
```
Or execute diff in summary mode:
```bash
python3 watson_dialog_diff.py \
  input/current.json input/candidate.json \
  --engine external \
  --summary-only \
  --format json \
  --max-input-bytes 0 \
  --output output/summary.json
```

## 3. Engine Selection

- **Automatic (Recommended):** `--engine auto`
- **Bounded External Engine:** `--engine external --index-backend auto`
- **Parallel Workers:** `--jobs auto` (parallelizes only modified subtrees).
