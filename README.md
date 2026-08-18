<div align="center">

# tare.tools — Dialog Engine

**Deterministic Conversational AST, Semantic Diff Engine, SpEL Expression Evaluator, Scenario Generator, and Mission Control Triage Console for Enterprise Dialog Systems.**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-Zero%20(Pure%20Stdlib)-orange.svg)](#zero-external-runtime-dependencies)
[![Tests](https://img.shields.io/badge/Tests-132%20Passed%20(100%25)-success.svg)](#automated-testing)
[![Agentic Protocol](https://img.shields.io/badge/Agentic%20Protocol-tare.tools%2Fv1-purple.svg)](#agentic-integration)

<p align="center">
  <a href="#why-dialog-engine-the-paradigm-shift">Why Dialog Engine</a> •
  <a href="#key-architectural-pillars">Architectural Pillars</a> •
  <a href="#the-12-phase-validation-taxonomy">Validation Taxonomy</a> •
  <a href="#quickstart-and-installation">Quickstart</a> •
  <a href="#cli-command-reference">CLI Reference</a> •
  <a href="#python-library-api">Python Library</a> •
  <a href="#interactive-mission-control">Interactive UI</a> •
  <a href="#license-and-attribution">License</a>
</p>

</div>

---

## Why Dialog Engine? (The Paradigm Shift)

Enterprise conversational AI systems (IBM Watson Assistant, legacy dialog trees, and agentic workflows) rely on deeply nested, non-linear state machines containing thousands of nodes, dynamic Spring Expression Language (SpEL) conditions, multi-turn slots, and recursive digressions.

Traditional text-based diff tools (such as `git diff`) and naive JSON comparators completely break down on these trees due to three systemic failures:

1. **False-Positive Noise:** Trivial JSON key reordering or sibling movement generates thousands of lines of spurious diffs.
2. **Dynamic SpEL Blindness:** Syntactic errors, dead branches, variable type contradictions, and shadow conditions remain undetected until runtime.
3. **Scale & Digression Havoc:** Enterprise trees (1,000+ nodes, 80+ MB JSON exports) cause memory exhaustion during full DOM parsing, while recursive digressions corrupt conversation state.

```text
TRADITIONAL NAIVE DIFF (Spurious Key Noise & False Positives)
[Node A (line 40)] <--- Diff Chaos ---> [Node A (line 1200)]  [!] Key reordering creates fake conflicts.

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
| **Node Identity Resolution** | Fragile line / array index | **Immutable UUID & AST canonical ordering** |
| **SpEL Condition Analysis** | None (treated as raw strings) | **Static AST Lexer & fail-closed safe evaluation** |
| **Control Flow & Cycle Check** | Manual inspection | **Tarjan SCC graph cycle & dead-jump detection** |
| **Slot & Variable Lifecycles** | Untracked | **Disjoint condition reuse & contradiction triage** |
| **Large Tree Scalability** | OOM on 50MB+ trees | **Adaptive mmap indexing & compact graph sharding** |
| **Automated Scenario Synthesis** | Manual QA test writing | **Deterministic leaf-to-root scenario generation** |
| **Runtime Dependencies** | Heavy frameworks | **Pure Python 3.10+ stdlib (Zero external runtime dependencies)** |

---

## Key Architectural Pillars

```
                                 TARE.TOOLS DIALOG ENGINE ARCHITECTURE
                                 
   ┌───────────────────────┐     ┌────────────────────────┐     ┌───────────────────────┐
   │   Semantic Document   │ ──► │  Static AST & SpEL     │ ──► │ Topological Graph &   │
   │  Normalization Model  │     │   Safety Boundary      │     │    Diff Analyzer      │
   └───────────────────────┘     └────────────────────────┘     └───────────────────────┘
               │                             │                              │
               ▼                             ▼                              ▼
   ┌───────────────────────┐     ┌────────────────────────┐     ┌───────────────────────┐
   │ Adaptive Memory Mmap  │     │ Scenario Generator &   │     │ SIGNAL Mission Control│
   │  & Tree Shard Engine  │     │  Traceable Test Runner │     │  Triage Console (HTML)│
   └───────────────────────┘     └────────────────────────┘     └───────────────────────┘
```

### 1. Universal Dialog AST Explorer & Schema Discovery (`watson_dialog_explorer.py`)
Polymorphic introspector and bidirectional schema normalizer supporting:
- Official flat IBM Watson Assistant exports (V1 classic and V2 flat pointer topologies with `dialog_node`, `parent`, `previous_sibling`).
- Hierarchical / Nested enterprise dialog trees (`nos`, `filhos`, `respostas`, `slots`).
- Multichannel awareness (WhatsApp, Web Chat, Mobile App, Voice, Slack).
- Multimodal & rich media responses (text, images, carousels, cards, options, pauses, connect-to-agent).
- Lossless bidirectional conversion between formats.

### 2. Deterministic Semantic Diff Engine (`watson_dialog_diff.py`)
Compares dialog trees by unique identifier (`uuid`), evaluating structural additions, removals, and semantic modifications across nodes, responses, context variables, slots, and slot handlers without false positives from key reordering.

### 3. Hardened SpEL Expression Boundary (`watson_spel.py`)
Static AST lexer and sandboxed evaluator for Spring Expression Language (SpEL) subsets (`#intent`, `@entity`, `$context`, ternary operators, string methods, regex matches):
- **Recursion Depth Limits:** Capped at 50 frames to prevent stack exhaustion.
- **Memory Amplification Defense:** Capped against multiplicative expansion attacks.
- **Dunder Protection:** Rejection of `__dunder__` property traversals.
- **Safe Evaluation:** Fail-closed `UNKNOWN` / `FALSE` propagation on runtime anomalies.

### 4. Topological Graph & Jump Resolution (`watson_dialog_graph.py`)
Constructs deterministic directed acyclic/cyclic graphs of the conversation flow, resolving body jumps, response-condition jumps, slot handlers, and root digression anchors into DOT and JSON graph outputs.

### 5. Deterministic Scenario Runner (`watson_dialog_test.py`)
Traceable headless runner that validates multi-turn conversation sessions against dialog trees, supporting session slot state, digression returns, conditional response branching, and loop detection (safety cap at 50 turn iterations).

### 6. Adaptive External-Memory Sharding (`watson_dialog_shard.py`, `watson_dialog_external.py`)
Resource-aware execution for large-scale enterprise exports:
- Automatically selects fast in-memory DOM parsing for files `< 10 MB`.
- Switches to mmap-indexed single-pass tokenization and compact graph sharding for large exports (`> 10 MB`).

---

## The 12-Phase Validation Taxonomy

`watson_dialog_validate.py` categorizes issues into a 12-phase calibrated taxonomy:

| Phase | Category | Description & Calibrated Handling |
|---|---|---|
| **Phase 1** | `catalog_reference` | Verifies intent and entity references against valid catalog definitions. |
| **Phase 2** | `spel_syntax` | High-confidence lexical and syntax error reporting with byte offsets. |
| **Phase 3** | `control_flow` | Detects orphaned nodes, unresolvable jump targets, and infinite loops. |
| **Phase 4** | `numeric_capture` | Flags type contradictions in numeric slot extraction (e.g. conflicting defaults). |
| **Phase 5** | `conditional_slot_reuse` | Validates variable reuse across provably disjoint conditions. |
| **Phase 6** | `manual_entities` | Resolves custom entity extraction annotations. |
| **Phase 7** | `identical_capture_reuse` | Identifies duplicate variable writes with identical values (informational). |
| **Phase 8** | `mixed_slot_reuse` | Flags high-risk unconditional variable overwrites across disjoint turns. |
| **Phase 9** | `digression_status` | Audits state persistence and stack integrity during multi-hop digressions. |
| **Phase 10** | `root_cause_ledger` | Unifies cascading downstream validation errors into single causal issues. |
| **Phase 11** | `functional_patterns` | Maps conversational idioms into conformance profiles. |
| **Phase 12** | `warning_calibration` | Threshold-calibrated reporting with `--summary-only` high-signal filtering. |

---

## Quickstart and Installation

```bash
# Clone the repository
git clone https://github.com/augusto-scarvalho/tare.tools.dialog-engine.git
cd tare.tools.dialog-engine

# Run the full test suite (132 tests, pure stdlib)
python -m pytest
```

---

## CLI Command Reference

### 1. Universal Dialog Explorer & Introspection
```bash
# Introspect primitives, topology, channels, and rich media assets
python watson_dialog_explorer.py input/skill.json --introspect

# List discovered communication channels
python watson_dialog_explorer.py input/skill.json --channels

# List rich media and interactive components
python watson_dialog_explorer.py input/skill.json --multimedia

# Convert official Watson V1 skill to nested enterprise format
python watson_dialog_explorer.py input/skill.json --convert-to nested --output output/nested_tree.json

# Convert nested enterprise format to official IBM Watson Assistant V1 JSON
python watson_dialog_explorer.py input/nested.json --convert-to v1 --output output/official_v1.json
```

### 2. Semantic Diff
```bash
# Compare two exports and output a Markdown changelog
python watson_dialog_diff.py input/current.json input/candidate.json --output output/diff.md

# Output structured JSON diff
python watson_dialog_diff.py input/current.json input/candidate.json --format json --output output/diff.json
```

### 3. Validation & Quality Gates
```bash
# Validate export with single issue contract
python watson_dialog_validate.py input/candidate.json --output output/validation.json

# High-signal summary mode for CI pipelines
python watson_dialog_validate.py input/candidate.json --summary-only --max-issues 20
```

### 4. Graph Export
```bash
# Export topological graph to DOT and JSON
python watson_dialog_graph.py input/candidate.json --output-json output/graph.json --output-dot output/graph.dot
```

### 5. Condition & SpEL Analysis
```bash
# Extract and statically analyze all conditions across nodes and slots
python watson_dialog_conditions.py input/candidate.json --output output/condition_analysis.json
```

### 6. Automated Scenario Generation & Execution
```bash
# Generate candidate test scenarios from diff
python watson_dialog_generate_diff_tests.py input/current.json input/candidate.json --output output/scenarios/

# Run a test scenario against candidate export
python watson_dialog_test.py input/candidate.json tests/fixtures/dialog_test.json
```

---

## Python Library API

```python
import watson_dialog_diff as diff
import watson_dialog_validate as validate
import watson_spel as spel

# 1. Load and validate document
doc = diff.load_json("tests/fixtures/validation_legacy.json")
report = validate.validate(doc)
print(f"Validation Issues: {len(report['issues'])}")

# 2. Evaluate SpEL expression safely
context = {"user_tier": "GOLD", "balance": 1500}
result = spel.evaluate_condition("$user_tier == 'GOLD' and $balance >= 1000", context)
print(f"Condition Match: {result}")  # Output: True

# 3. Compare two dialog versions
current = diff.load_json("tests/fixtures/current.json")
candidate = diff.load_json("tests/fixtures/candidate.json")
diff_result = diff.diff_dialogs(current, candidate)
print(f"Nodes Added: {len(diff_result['nodes_added'])}")
```

---

## Interactive Mission Control & Triage Console

The repository includes a standalone, zero-dependency HTML5/CSS3 triage application (`triage_viewer.html`) powered by the **tare.tools SIGNAL Design System**:

- **14 Harmonious Color Themes:** Including Dark, Light, Cyberpunk, Amber CRT, Solarized, and Minimalist.
- **Node Inspection Drawer:** Deep JSON AST tree inspection with path hierarchy.
- **Dynamic Search & Filtering:** Filter issues by category, severity, node name, or UUID.
- **Bilingual Support:** Instant Portuguese / English localization switcher.
- **Zero Server Required:** Opens directly in any modern browser (`file://`).

```bash
# Regenerate the triage console with updated datasets
python generate_optimized_data.py
python generate_triage_html.py
```

---

## Automated Testing

The suite contains **127 automated tests** covering unit behavior, regression protection, large-scale synthetic scaling (1,000+ nodes), SpEL fuzzing, and Playwright end-to-end UI verification:

```bash
python -m pytest -v
```

---

## License and Attribution

Licensed under the [Apache License, Version 2.0](LICENSE).  
Copyright (c) 2026 Augusto Carvalho and tare.tools contributors.  
Part of the **tare.tools** Deterministic Engineering and Autonomous Agent OS ecosystem.
