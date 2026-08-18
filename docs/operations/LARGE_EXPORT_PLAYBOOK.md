# Playbook — Large Enterprise Dialog Exports

**Status:** CURRENT operational guidance.  
**Scope:** Safe operational usage on private and enterprise conversational datasets.

## 1. Operational Principle

Real production exports are local operational inputs, never versioned source code.

```text
input/current.json
input/candidate.json
```

These paths are ignored by `.gitignore`. Never force-add them with `git add -f`. Versioned fixtures belong exclusively in `tests/fixtures/` and must be synthetic and sanitized.

## 2. Preflight Inspection

Before running a full AST diff or deep validation on multi-megabyte exports:

```bash
dialog-engine explore input/current.json
```

Or execute a summarized diff:

```bash
dialog-engine diff input/current.json input/candidate.json --format json --output output/summary.json
```

## 3. Engine Selection Guidelines

### Automatic (Recommended Default)
```bash
dialog-engine diff input/current.json input/candidate.json --engine auto
```
Evaluates input file size and currently available system RAM.

### Fast Path / Verification Oracle
```bash
dialog-engine diff input/current.json input/candidate.json --engine dom
```
Provides maximum throughput when memory is not constrained.

### External Memory Execution
```bash
dialog-engine diff input/current.json input/candidate.json --engine external --index-backend auto
```
Enforces bounded RAM usage for multi-gigabyte or constrained runtime environments.

## 4. Quality Gates & Production Rollout

1. Run static validation: `dialog-engine validate input/candidate.json --rich`
2. Run rule mutation fuzzer: `dialog-engine audit-rules input/candidate.json --scenarios tests/scenarios.json`
3. If test blindspots exist, synthesize missing scenarios: `--synthesize-gaps`
4. Inspect and curate findings using the SIGNAL Mission Control console (`triage_viewer.html`).
