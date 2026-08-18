# ADR-0005 — Package Modularization (`src/tare_dialog`) and Performance Acceleration (`orjson`, `networkx`, `rich`, `pydantic`)

**Status:** ACCEPTED  
**Date:** 2026-08-18  
**Scope:** `tare.tools.dialog-engine`

---

## 1. Context & Operational Challenge

With the formal establishment of the Dual Distribution Strategy ([ADR-0004](0004-dual-distribution-strategy-modular-and-ephemeral.md)), the artificial constraint of "zero external dependencies" on the core development package was eliminated.

Parsing massive JSON exports containing 28,000+ nodes (83 MB+) and tens of thousands of SpEL expressions in pure Python without C/Rust native acceleration offered clear opportunities for performance enhancements and modernized Developer Experience (DX).

---

## 2. Architectural Decision

1. **Adopt Canonical `src-layout` (`src/tare_dialog`):**
   - Consolidated legacy root modules into a cohesive package namespace (`tare_dialog.explorer`, `tare_dialog.diff_engine`, `tare_dialog.validator`, `tare_dialog.spel`, `tare_dialog.graph`, `tare_dialog.triage`, `tare_dialog.cli`, `tare_dialog.schema_adapter`).
   - Retained transparent backwards-compatibility shims at the repository root (`watson_*.py`).

2. **Acceleration via High-Performance Libraries:**
   - **`orjson` (Rust C-Extension):** Transparently accelerates JSON deserialization and cryptographic digest computation (`load_json()`, `stable_item()`), speeding up multi-megabyte parsing.
   - **`networkx`:** Models conversational flow as a directed graph (`DiGraph`), providing cycle detection algorithms (`find_graph_cycles()`), strongly connected components analysis, and reachability proofs.
   - **`pydantic` v2:** Typed modeling and validation for AST nodes, rich response payloads, and universal schema definitions.
   - **`rich`:** Formatted terminal user interface with color-coded tables, panels, and syntax highlighting (`--format rich`, `--rich`).

3. **Internal AST & SpEL Optimizations:**
   - **LRU Cache (`@functools.lru_cache`):** Caches token streams and syntax diagnostic trees across identical SpEL expressions found throughout enterprise trees.
   - **Slotted Dataclasses (`slots=True`):** Reduces the memory footprint of `Token` and node instances.

---

## 3. Consequences & Gains

* **100% Semantic Parity:** Full test suite passes with 100% green status across all supported Python versions.
* **Seamless Standalone Generation:** The standalone builder (`scripts/build_standalone.py`) automatically strips package-only dependencies and produces single-file artifacts for ChatGPT ADA and Microsoft 365 Copilot Studio.
