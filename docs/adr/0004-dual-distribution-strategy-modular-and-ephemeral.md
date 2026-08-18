# ADR-0004 — Dual Distribution Strategy: Modular and Ephemeral (ChatGPT ADA & Copilot)

**Status:** ACCEPTED  
**Date:** 2026-08-18  
**Scope:** `tare.tools.dialog-engine`

---

## 1. Context & Operational Challenge

The `tare.tools.dialog-engine` ecosystem operates across two fundamentally distinct runtime environments:

1. **Engineering Workstations, Servers, & CI/CD Pipelines (Local & Cloud):**
   - Developer environments, GitHub Actions CI/CD workflows, test orchestrators, and autonomous coding agents.
   - Requires modular packaging, external memory sharding for large JSON exports (100 MB+), rich terminal rendering (`rich`), interactive HTML triage interfaces (`triage_viewer.html`), and a full `pytest` test suite.

2. **Ephemeral Runtimes & AI Sandboxes (ChatGPT Advanced Data Analysis / ADA & Copilot Studio):**
   - Disposable sandboxes with strict runtime constraints:
     - **Zero External Dependencies:** No dynamic `pip install` internet access;
     - **Ephemeral Lifecycle:** Fast cold-starts (< 100ms) with per-cell execution timeouts;
     - **Single-File Distribution:** Direct file upload and 1-line import without unzipping packages (`import dialog_engine_standalone as de`).

---

## 2. Architectural Decision

Formally establish a **Dual Distribution Strategy** managed via an automated bundling pipeline (`scripts/build_standalone.py`):

```text
                               SRC (Modular Package: src/tare_dialog/)
              ┌─────────────────────────────────────────────────────────────┐
              │ spel.py, diff_engine.py, validator.py, schema_adapter.py... │
              └──────────────────────────────┬──────────────────────────────┘
                                             │
                    ┌────────────────────────┴────────────────────────┐
                    ▼                                                 ▼
      [DISTRIBUTION A — MODULAR PACKAGE]            [DISTRIBUTION B — EPHEMERAL STANDALONE]
      - pyproject.toml / pytest                     - dist/dialog_engine_standalone.py (~255 KB)
      - High-performance orjson, networkx, rich     - dist/dialog_engine.pyz (ZipApp executable)
      - Multi-core multiprocessing                  - Single-file zero-install for ChatGPT ADA
      - Interactive SIGNAL Web Console              - 1-line import for Python sandboxes
```

---

## 3. Distribution Specifications

### 📦 Distribution A — Modular Package
* **Target Audience:** Developers, QA Engineers, CI/CD runners, and Python application servers.
* **Components:**
  - Modern `src/tare_dialog` package (`pyproject.toml`).
  - High-performance hardware acceleration via `orjson`, `networkx`, and `pydantic`.
  - Interactive SIGNAL Mission Control web console (`triage_viewer.html`).
  - Automated test suite with 151 unit and integration tests.

### ⚡ Distribution B — Ephemeral Standalone (Zero-Install)
* **Target Audience:** ChatGPT Code Interpreter / ADA, Microsoft 365 Copilot Studio, AWS Lambda, edge runtimes.
* **Generated Artifacts:**
  1. `dist/dialog_engine_standalone.py` (~255 KB): Standalone pure Python stdlib monolith with inlined AST lexer, validator, diff engine, schema adapter, and scenario runner.
  2. `dist/dialog_engine.pyz` (~59 KB): Portable Python ZipApp executable runnable via `python dialog_engine.pyz <command>`.

---

## 4. Consequences & Guarantees

* **Unified AST Semantics:** Both distributions execute the exact same canonical algorithms, guaranteeing zero behavioral drift between developer workstations and ephemeral AI sandboxes.
* **Continuous Parity Testing:** The test suite verifies both distributions on every build to guarantee 100% functional parity.
