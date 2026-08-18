<div align="center">

# tare.tools — Dialog Engine

**Deterministic Conversational AST, Semantic Diff Engine, Hardened SpEL Evaluator, Topological Graph Analyzer, Symbolic Mutation Fuzzer, and Mission Control Triage Console for Enterprise Dialog Systems.**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)
[![High Performance](https://img.shields.io/badge/Accelerated-orjson%20%7C%20networkx%20%7C%20rich-purple.svg)](#performance-and-architecture)
[![Tests](https://img.shields.io/badge/Tests-148%20Passed%20(100%25)-success.svg)](#automated-testing)
[![Dual Distribution](https://img.shields.io/badge/Dual%20Dist-Modular%20%2B%20Ephemeral%20ADA-orange.svg)](#dual-distribution-strategy)
[![Live Web Console](https://img.shields.io/badge/Web%20Console-SIGNAL%20Live-blueviolet.svg)](https://augusto-scarvalho.github.io/tare.tools.dialog-engine/)

<p align="center">
  <a href="#why-dialog-engine-the-paradigm-shift">Why Dialog Engine?</a> •
  <a href="#feature-catalog--concrete-benefits">Features & Benefits</a> •
  <a href="#architectural-pillars">Architectural Pillars</a> •
  <a href="#dual-distribution-strategy">Dual Distribution</a> •
  <a href="#the-12-phase-validation-taxonomy">Validation Taxonomy</a> •
  <a href="#cli-command-reference">CLI Reference</a> •
  <a href="#python-library-api">Python API</a> •
  <a href="#mission-control-html-console">Mission Control UI</a> •
  <a href="#license">License</a>
</p>

</div>

---

## Why Dialog Engine? (The Paradigm Shift)

Enterprise conversational AI systems (IBM Watson Assistant, legacy dialog trees, and agentic conversational state graphs) are deeply nested, non-linear state machines containing thousands of nodes, dynamic Spring Expression Language (SpEL) conditions, multi-turn slot frames, and recursive digressions.

Traditional text-based diff tools (`git diff`) and naive JSON comparators fail completely due to three systemic limitations:

1. **False-Positive Diff Chaos:** Trivial JSON key reordering or sibling movement generates thousands of lines of spurious conflicts.
2. **Blindness to Dynamic SpEL Expressions:** Syntactic anomalies, unreachable branches, type contradictions, and shadowed conditions remain undetected until runtime failures in production.
3. **Scale & Digression Exhaustion:** Massive enterprise trees (28,000+ nodes, 80+ MB JSON exports) trigger out-of-memory crashes during naive DOM parsing, while recursive digressions corrupt conversation stack state.

```text
TRADITIONAL NAIVE DIFF (Spurious Key Noise & False Conflicts)
[Node A (line 40)] <--- Diff Chaos ---> [Node A (line 1200)]  [!] Key reordering creates false conflicts.

DETERMINISTIC DIALOG AST ENGINE (Semantic Invariant Preservation)
   +---> [Intent: #transfer] ---> [Slot: $amount (@sys-number)] ---> [Condition: $amount > 0]
   |                                                                          │
[Root Tree] -------------------- (Deterministic UUID Binding) -------------> [Success Node]
   |                                                                          ▲
   +---> [Digression: #help] ---> (Stack Preservation / Return) --------------+
```

### Comparative Capabilities

| Capability | Line-by-Line / Naive JSON Diff | tare.tools Dialog Engine |
|---|---|---|
| **Node Identity Resolution** | Fragile line / array index | **Immutable UUID & canonical AST ordering** |
| **SpEL Condition Analysis** | None (treated as raw strings) | **Static AST Lexer & fail-closed safe evaluation** |
| **Topology & Cycle Detection** | Manual inspection | **Graph cycle and infinite jump detection via NetworkX** |
| **Symbolic AST Mutation Fuzzing** | None | **Formal fault injection & Mutation Score calculation** |
| **Business Rule Audit & Blindspots** | False 100% (blind happy-path testing) | **Blindspot discovery & automatic gap scenario synthesis** |
| **High-Scale Parsing & Ingestion** | Slow in standard Python `json` | **Accelerated with `orjson` (Rust) — 166MB in 600ms** |
| **Universal Schema Discovery** | Single rigid schema | **Universal AST (Watson V1 flat + Enterprise nested)** |
| **Ephemeral AI Execution** | Requires heavy setup | **Single-file standalone bundle for ChatGPT ADA & Copilot** |

---

## Feature Catalog & Concrete Benefits

Every module within `tare.tools.dialog-engine` is engineered to resolve high-stakes engineering pain points in mission-critical conversational deployments:

### 1. Business Rule Audit & Test Blindspot Discovery (`audit-rules`)
* **The Problem:** QA teams often celebrate "100% tests passing", unaware that their 10–20 test scenarios only cover the happy path, leaving security guardrails and financial limits untested.
* **The Engine's Solution:** The rule mutator systematically inverts financial thresholds (`$score >= 750` $\to$ `< 750`), bypasses auth guards (`$user_authenticated` $\to$ `true`), and corrupts escalation intents (`#falar_atendente`). If the customer's tests still pass with 100% success, the engine flags a **Test Blindspot**.
* **Automatic Gap Synthesis:** The engine **synthesizes the missing JSON test scenario automatically** (`--synthesize-gaps`), bridging the gap with zero manual effort.
* **Concrete Example:**
  ```bash
  dialog-engine audit-rules bot_banking.json --scenarios tests.json --synthesize-gaps --gaps-out-dir ./synthesized_tests/
  ```

### 2. Symbolic AST & Automata Mutation Fuzzing (`mutate`)
* **The Problem:** How do we mathematically verify that our static validator catches every real bug without generating false alarms?
* **The Engine's Solution:** Implements 7 formal graph and predicate mutation operators ($M_{jump}, M_{topo}, M_{pred}, M_{dormant}, M_{contra}, M_{slot}, M_{meta}$) and computes the formal *Mutation Score* (Kill Rate).
* **Metamorphic Testing:** The neutral operator $M_{meta}$ applies cosmetic perturbations to prove mathematically that the engine maintains **Zero False Positives**.
* **Concrete Example:**
  ```bash
  dialog-engine mutate tests/fixtures/demo_banking_current.json
  # Result: Mutation Score: 100.0% (4/4 KILLED, 1 METAMORPHIC PASS)
  ```

### 3. Noise-Free Semantic AST Diff (`diff`)
* **The Problem:** A 5,000-line `git diff` generated by visual editor auto-formatting or key reordering makes pull request reviews impossible.
* **The Engine's Solution:** Indexes nodes by immutable UUID and normalizes keys canonically, surfacing only true semantic additions, deletions, and modifications with zero noise.
* **Concrete Example:**
  ```bash
  dialog-engine diff production.json candidate.json --format rich
  ```

### 4. Hardened SpEL Lexer & Sandbox Evaluator (`spel`)
* **The Problem:** Malformed Spring Expression Language statements (`<? $score >= 750 ? 'approved' : 'analysis' ?>`) with unclosed parentheses or syntax errors crash bot runtimes in production.
* **The Engine's Solution:** Static AST lexer with LRU caching that audits syntax without executing arbitrary code, blocks reflection or `__dunder__` attacks, and enforces *fail-closed* semantics.

### 5. Topological Graph & Infinite Loop Detection (`graph`)
* **The Problem:** Circular jumps (Node A $\to$ Node B $\to$ Node C $\to$ Node A) cause infinite loops that lock user sessions and generate runaway infrastructure costs.
* **The Engine's Solution:** Models dialog flows as directed graphs (`networkx.DiGraph`), detects cycles, and exports graph representations in JSON and Graphviz DOT.
* **Concrete Example:**
  ```bash
  dialog-engine graph bot.json --output-dot graph.dot
  ```

### 6. Universal Schema Introspection & Discovery (`explore`)
* **The Problem:** Needing separate tools for flat Watson V1 schemas and nested enterprise tree formats.
* **The Engine's Solution:** Losslessly normalizes between flat pointer trees (`dialog_nodes`) and deep hierarchical schemas (`nos/filhos/slots`), detecting channels (WhatsApp, Web, Voice) and multimodal elements (carousels, buttons).

### 7. SIGNAL Mission Control Triage Console (`triage_viewer.html`)
* **The Problem:** Non-technical conversational designers and business auditors struggling with terminal outputs or raw JSON.
* **The Engine's Solution:** Zero-install web console (hosted on GitHub Pages) featuring 14 engineering themes, instant search, deep node inspection drawer, and interactive mutation triage.

---

## Architectural Pillars

```text
                             TARE.TOOLS DIALOG ENGINE ARCHITECTURE
                             
   ┌───────────────────────┐     ┌────────────────────────┐     ┌───────────────────────┐
   │  Universal Schema &   │ ──► │  Hardened SpEL AST     │ ──► │  Topological Graph &  │
   │  AST Explorer         │     │  Lexer with LRU Cache  │     │  Cycle Detection      │
   │  (tare_dialog.explorer)│     │  (tare_dialog.spel)    │     │  (tare_dialog.graph)  │
   └───────────────────────┘     └────────────────────────┘     └───────────────────────┘
               │                             │                              │
               ▼                             ▼                              ▼
   ┌───────────────────────┐     ┌────────────────────────┐     ┌───────────────────────┐
   │ Semantic AST Diff     │     │ 12-Phase Validation    │     │ Symbolic Mutation &   │
   │ Engine with orjson    │     │ Single Issue Contract  │     │ Rule Auditor Engine   │
   │ (tare_dialog.diff)    │     │ (tare_dialog.validator)│     │ (tare_dialog.mutator) │
   └───────────────────────┘     └────────────────────────┘     └───────────────────────┘
```

---

## Dual Distribution Strategy

The project provides **two distinct distributions** ([ADR-0004](docs/adr/0004-dual-distribution-strategy-modular-and-ephemeral.md)):

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ 📦 DISTRIBUTION A — MODULAR PACKAGE (Engineering Workstations, Servers, CI) │
│    - Full src/tare_dialog package with orjson, networkx, pydantic, and rich. │
│    - CLI commands for mutate and audit-rules with rich terminal output.     │
│    - Interactive SIGNAL Mission Control Console (HTML).                     │
│    - 148 automated unit & integration tests (pytest).                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ ⚡ DISTRIBUTION B — EPHEMERAL STANDALONE (ChatGPT ADA & Copilot Sandboxes)   │
│    - Zero-install single file: dist/dialog_engine_standalone.py (~250 KB)   │
│    - Portable ZipApp executable: dist/dialog_engine.pyz (~57 KB)            │
│    - Upload directly to Code Interpreter / Sandboxes without pip!           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The 12-Phase Validation Taxonomy

The unified static validator (`tare_dialog.validator`) operates under a **Single Issue Contract** across 12 progressive phases:

| Phase | Rule Code | Semantic Invariant Description |
|---|---|---|
| **Phase 1** | `disabled_condition_false` | Flags intentionally disabled branches with explicit `false` conditions. |
| **Phase 2** | `invalid_spel_syntax` | Audits static SpEL syntax (unclosed parentheses, unclosed quotes). |
| **Phase 3** | `unresolved_jump_target` | Identifies jumps targeting nonexistent node UUIDs. |
| **Phase 4** | `sys_number_zero_not_captured` | Prevents bugs where prompts include 0 but capturing condition ignores zero. |
| **Phase 5** | `unsatisfiable_slot_enable` | Detects contradictory slot-enable conditions (`$var && $var == false`). |
| **Phase 6** | `slot_type_contradiction` | Identifies mismatches between capture conditions and processed input types. |
| **Phase 7** | `slot_depends_on_later_slot` | Detects slot conditions depending on variables filled by subsequent slots. |
| **Phase 8** | `slot_depends_on_optional_slot`| Warns on slot dependencies requiring variables from optional prior slots. |
| **Phase 9** | `digression_blocked_by_transition` | Audits digression nodes blocked by forced jump transitions. |
| **Phase 10** | `multiple_first_siblings` | Catches broken sibling groups with multiple initial sibling nodes. |
| **Phase 11** | `missing_root_anything_else` | Warns if root dialog level lacks a fallback `anything_else` node. |
| **Phase 12** | `too_many_response_types` | Validates element limits per conditional response block. |

---

## Installation & Quickstart

### Python Package Installation
```bash
# Clone the repository
git clone https://github.com/augusto-scarvalho/tare.tools.dialog-engine.git
cd tare.tools.dialog-engine

# Install high-performance dependencies
pip install -e .
```

### Run Test Suite (148 Automated Tests)
```bash
python -m pytest
```

---

## CLI Command Reference

The `dialog-engine` (or `tare-dialog`) CLI provides native `rich` terminal output:

### 1. Business Rule Audit & Test Blindspots (`audit-rules`)
```bash
# Audit business rules against test scenarios
dialog-engine audit-rules input/skill.json --scenarios tests/scenarios.json

# Generate compliance manifest and auto-synthesize missing test scenarios
dialog-engine audit-rules input/skill.json \
  --scenarios tests/scenarios.json \
  --audit-out dist/audit_manifest.json \
  --synthesize-gaps \
  --gaps-out-dir dist/synthesized_tests/
```

### 2. Symbolic AST Mutation Analysis (`mutate`)
```bash
# Execute formal mutation testing and compute Mutation Score
dialog-engine mutate input/skill.json

# Export mutated JSON variants for external fuzzing
dialog-engine mutate input/skill.json --output-dir dist/mutants/
```

### 3. Semantic AST Diff (`diff`)
```bash
# Rich formatted terminal diff
dialog-engine diff input/current.json input/candidate.json --format rich

# Generate Markdown diff report
dialog-engine diff input/current.json input/candidate.json --format markdown --output output/diff.md

# Generate structured JSON diff
dialog-engine diff input/current.json input/candidate.json --format json --output output/diff.json
```

### 4. Static Validation (`validate`)
```bash
# Rich terminal validation table
dialog-engine validate input/skill.json --rich

# Export full validation report in JSON
dialog-engine validate input/skill.json --output output/validation_report.json
```

### 5. Flow Graph & Cycle Detection (`graph`)
```bash
# Generate topological graph and reachability telemetry
dialog-engine graph input/skill.json --output-json output/graph.json

# Export Graphviz DOT visualization
dialog-engine graph input/skill.json --output-dot output/graph.dot
```

### 6. Universal Schema Introspection (`explore`)
```bash
# Full introspection of primitives, channels, and rich media
dialog-engine explore input/skill.json

# Lossless conversion between schemas (flat V1 <-> nested enterprise)
dialog-engine explore input/skill.json --convert-to v1 --output output/v1_skill.json
```

---

## Python Library API

```python
import tare_dialog as td

# 1. High-speed document loading (orjson)
doc = td.load_json("input/skill.json")

# 2. Audit business rules against test scenarios
scenarios = td.load_json("tests/scenarios.json")
report = td.evaluate_rules_against_scenarios(doc, scenarios)
print(f"Test Suite Protection Rate: {report['summary']['test_mutation_score_pct']}%")

# 3. Execute 12-phase static validation
val_report = td.validate(doc)
print(f"Total issues found: {val_report['summary']['issues']}")

# 4. Semantic AST diff between two versions
diff = td.summarize(doc_v1, doc_v2, td.DEFAULT_IGNORED_FIELDS)
print(f"Changes: +{diff['summary']['added']} ~{diff['summary']['changed']} -{diff['summary']['removed']}")

# 5. Safe SpEL condition evaluation
result = td.evaluate_condition("$balance > 100 && #confirm", context={"balance": 150}, intents=["confirm"])
assert result is True
```

---

## Mission Control HTML Console

The project includes [`triage_viewer.html`](triage_viewer.html), hosted live on [GitHub Pages](https://augusto-scarvalho.github.io/tare.tools.dialog-engine/):
- **14 Engineering Themes** (NASA Deep Space, Tokyo Night, Monokai Pro, Synthwave, etc.).
- **Advanced Filtering:** Filter by severity, audit phase, node UUID, and regression status.
- **Deep Inspection Drawer:** Side-by-side node JSON inspection, AST hierarchy, and mutation gap details.

---

## License

Distributed under the **Apache-2.0** License. See [LICENSE](LICENSE) and [NOTICE](NOTICE) for complete details.
