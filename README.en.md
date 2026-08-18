<div align="center">

# tare.tools — Dialog Engine

**Deterministic Conversational AST, Semantic Diff Engine, Hardened SpEL Evaluator, Topological Graph Analyzer, and Mission Control Triage Console for Enterprise Dialog Systems.**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)
[![High Performance](https://img.shields.io/badge/Accelerated-orjson%20%7C%20networkx%20%7C%20rich-purple.svg)](#performance-and-architecture)
[![Tests](https://img.shields.io/badge/Tests-132%20Passed%20(100%25)-success.svg)](#automated-testing)
[![Dual Distribution](https://img.shields.io/badge/Dual%20Dist-Modular%20%2B%20Ephemeral%20ADA-orange.svg)](#dual-distribution-strategy)

<p align="center">
  <a href="#why-dialog-engine-the-paradigm-shift">Why Dialog Engine?</a> •
  <a href="#architectural-pillars">Architectural Pillars</a> •
  <a href="#dual-distribution-strategy">Dual Distribution</a> •
  <a href="#the-12-phase-validation-taxonomy">Validation Taxonomy</a> •
  <a href="#installation--quickstart">Quickstart</a> •
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
| **Slot & Variable Lifecycles** | Untracked | **Type contradiction and disjoint reuse detection** |
| **High-Scale Parsing & Ingestion** | Slow in standard Python `json` | **Accelerated with `orjson` (Rust) — 166MB in 600ms** |
| **Universal Schema Discovery** | Single rigid schema | **Universal AST (Watson V1 flat + Enterprise nested)** |
| **Ephemeral AI Execution** | Requires heavy setup | **Single-file standalone bundle for ChatGPT ADA & Copilot** |

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
   │ Semantic AST Diff     │     │ 12-Phase Validation    │     │ SIGNAL Mission Control│
   │ Engine with orjson    │     │ Single Issue Contract  │     │ Triage Console (HTML) │
   │ (tare_dialog.diff)    │     │ (tare_dialog.validator)│     │ (tare_dialog.triage)  │
   └───────────────────────┘     └────────────────────────┘     └───────────────────────┘
```

### 1. Universal Dialog AST Explorer & Schema Discovery (`tare_dialog.explorer`)
Polymorphic introspector and lossless bidirectional schema normalizer supporting:
- **Classic Flat Watson V1:** Pointer-based topologies (`dialog_node`, `parent`, `previous_sibling`).
- **Hierarchical Enterprise Trees:** Deeply nested JSON (`nos`, `filhos`, `respostas`, `slots`).
- **Omnichannel Intelligence:** Native channel recognition (WhatsApp, Web Chat, Mobile App, Voice, Slack).
- **Multimodal Components:** Rich text, images, carousels, options/buttons, pauses, and agent handoffs.

### 2. Semantic AST Diff Engine (`tare_dialog.diff_engine`)
Compares dialog trees by UUID, detecting additions, removals, and semantic modifications across nodes, responses, context variables, slots, and handlers without false positives from key reordering.

### 3. Hardened SpEL Expression Boundary (`tare_dialog.spel`)
Static AST lexer and safe evaluator for the Spring Expression Language subset used in dialog systems (`#intent`, `@entity`, `$context`, ternary operators, string methods, regex matches):
- **LRU Caching:** High-speed tokenization across trees with tens of thousands of nodes.
- **Dunder Protection:** Rejection of `__dunder__` property traversals and reflection.
- **Fail-Closed:** Safe `UNKNOWN` / `FALSE` propagation on runtime anomalies.

### 4. Topological Graph & Jump Resolution (`tare_dialog.graph`)
Models conversation flow as a directed graph (`networkx.DiGraph`), detecting:
- Infinite jump cycles and loops (`find_graph_cycles()`).
- Dead branches and unreachable nodes blocked by contradictory boolean conditions.
- Graph export to JSON and Graphviz DOT formats.

---

## Dual Distribution Strategy

The engine is published in **two distinct distributions** ([ADR-0004](docs/adr/0004-dual-distribution-strategy-modular-and-ephemeral.md)):

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ 📦 DISTRIBUTION A — MODULAR PACKAGE (Engineering Workstations, Servers, CI) │
│    - Modern package layout (src/tare_dialog) with orjson, networkx & rich.  │
│    - Memory-mapped sharding engine for giant exports (>100,000 nodes).      │
│    - Interactive SIGNAL Mission Control triage console (HTML).              │
│    - Full test suite with 132 automated tests (pytest).                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ ⚡ DISTRIBUTION B — EPHEMERAL STANDALONE (ChatGPT ADA & M365 Copilot Sandbox)│
│    - Monolithic zero-install script: dist/dialog_engine_standalone.py (~220K)│
│    - Portable Python ZipApp executable: dist/dialog_engine.pyz (~50 KB)     │
│    - Drop directly into Code Interpreter / Copilot without pip install!     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The 12-Phase Validation Taxonomy

The static validator (`tare_dialog.validator`) operates under a **unified issue contract** classified into 12 progressive phases:

| Phase | Rule Code | Semantic Invariant Description |
|---|---|---|
| **Phase 1** | `disabled_condition_false` | Flags deactivated unreachable nodes with literal `false` condition. |
| **Phase 2** | `invalid_spel_syntax` | Audits static SpEL syntax (unbalanced parentheses, unclosed quotes). |
| **Phase 3** | `unresolved_jump_target` | Identifies jumps targeting nonexistent UUIDs. |
| **Phase 4** | `sys_number_zero_not_captured` | Prevents bug where prompt accepts 0 but `@sys-number` capture rejects zero. |
| **Phase 5** | `unsatisfiable_slot_enable` | Flags logical contradictions in slot enable rules (`$var && $var == false`). |
| **Phase 6** | `slot_type_contradiction` | Detects mismatch between capture entity and input handler type. |
| **Phase 7** | `slot_depends_on_later_slot` | Flags slot whose condition depends on a variable captured by a later slot. |
| **Phase 8** | `slot_depends_on_optional_slot`| Warns on dependency on a variable captured by an optional earlier slot. |
| **Phase 9** | `digression_blocked_by_transition` | Audits nodes with outgoing digression blocked by forced transitions. |
| **Phase 10** | `multiple_first_siblings` | Detects sibling groups with more than one node marked as first sibling. |
| **Phase 11** | `missing_root_anything_else` | Flags absence of a root fallback node with `anything_else` condition. |
| **Phase 12** | `too_many_response_types` | Validates component limits per conditional response block. |

---

## Installation & Quickstart

### Install as Python Package
```bash
# Clone the repository
git clone https://github.com/augusto-scarvalho/tare.tools.dialog-engine.git
cd tare.tools.dialog-engine

# Install high-performance dependencies
pip install -e .
```

### Run Full Test Suite
```bash
python -m pytest
```

---

## CLI Command Reference

The unified CLI `dialog-engine` (or `tare-dialog`) provides rich terminal formatting:

### 1. Schema Discovery & AST Introspection (`explore`)
```bash
# Complete introspection of primitives, channels, and media
dialog-engine explore input/skill.json

# List communication channels
dialog-engine explore input/skill.json --channels

# List multimedia and rich response components
dialog-engine explore input/skill.json --multimedia

# Convert between formats (v1 flat <-> enterprise nested)
dialog-engine explore input/skill.json --convert-to v1 --output output/v1_skill.json
```

### 2. Semantic AST Diff (`diff`)
```bash
# Rich colored terminal diff table
dialog-engine diff input/current.json input/candidate.json --format rich

# Generate Markdown diff report
dialog-engine diff input/current.json input/candidate.json --format markdown --output output/diff.md

# Generate structured JSON diff
dialog-engine diff input/current.json input/candidate.json --format json --output output/diff.json
```

### 3. Static Validation (`validate`)
```bash
# Rich terminal table with severity coloring
dialog-engine validate input/skill.json --rich

# Export full validation report to JSON
dialog-engine validate input/skill.json --output output/validation_report.json
```

### 4. Flow Graph & Cycle Detection (`graph`)
```bash
# Generate topological graph JSON
dialog-engine graph input/skill.json --output-json output/graph.json

# Export Graphviz DOT visualization
dialog-engine graph input/skill.json --output-dot output/graph.dot
```

### 5. Test Scenario Execution (`test`)
```bash
# Execute deterministic test scenario against dialog
dialog-engine test input/skill.json tests/fixtures/scenario.json --output output/trace.json
```

---

## Python Library API

```python
import tare_dialog as td

# 1. Load document with ultra-fast orjson parsing
doc = td.load_json("input/skill.json")

# 2. Explore and normalize AST
ast_doc = td.explore_document(doc)
print(f"Format: {ast_doc.source_format} | Total Nodes: {len(ast_doc.nodes)}")

# 3. Execute 12-phase static validation
report = td.validate(doc)
print(f"Total issues found: {report['summary']['issues']}")

# 4. Compute semantic AST diff between two versions
diff = td.summarize(doc_v1, doc_v2, td.DEFAULT_IGNORED_FIELDS)
print(f"Changes: +{diff['summary']['added']} ~{diff['summary']['changed']} -{diff['summary']['removed']}")

# 5. Evaluate SpEL condition with security sandbox
result = td.evaluate_condition("$amount > 100 && #confirm", context={"amount": 150}, intents=["confirm"])
assert result is True
```

---

## Mission Control HTML Console

The project includes an interactive triage console [`triage_viewer.html`](triage_viewer.html) built with the **SIGNAL Design System**, featuring:
- **14 Visual Engineering Themes** (NASA Deep Space, Tokyo Night, Monokai Pro, Synthwave, etc.).
- **Advanced Filtering:** Filter by severity, validation phase, node UUID, and change status.
- **Deep Inspection Panel:** Raw JSON inspector, AST breadcrumbs, and change diff view.

---

## License

Distributed under the **Apache-2.0** License. See [LICENSE](LICENSE) and [NOTICE](NOTICE) for full details.
