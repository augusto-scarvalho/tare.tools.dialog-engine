<div align="center">

# tare.tools — Dialog Engine

**Deterministic Conversational AST, Semantic Diff Engine, Hardened SpEL Evaluator, Topological Graph Analyzer, Symbolic Mutation Fuzzer, Decoupled Schema Binding Adapter, and Mission Control Triage Console for Enterprise Dialog Systems.**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)
[![High Performance](https://img.shields.io/badge/Accelerated-orjson%20%7C%20networkx%20%7C%20rich-purple.svg)](#performance-and-architecture)
[![Tests](https://img.shields.io/badge/Tests-151%20Passed%20(100%25)-success.svg)](#automated-testing)
[![Dual Distribution](https://img.shields.io/badge/Dual%20Dist-Modular%20%2B%20Ephemeral%20ADA-orange.svg)](#dual-distribution-strategy)
[![Live Web Console](https://img.shields.io/badge/Web%20Console-SIGNAL%20Live-blueviolet.svg)](https://augusto-scarvalho.github.io/tare.tools.dialog-engine/)

<p align="center">
  🌐 <b>Languages:</b> <b>🇺🇸 English (en-US)</b> | <a href="README.pt-BR.md">🇧🇷 Português (pt-BR)</a>
</p>

<p align="center">
  <a href="#why-dialog-engine-the-paradigm-shift">Why Dialog Engine?</a> •
  <a href="#universal-schema-binding--total-decoupling">Universal Schema Adapter</a> •
  <a href="#real-world-practical-examples-what-we-solve">Real-World Examples</a> •
  <a href="#automated-test-generation--curation">Test Generation & Curation</a> •
  <a href="#feature-catalog--benefits">Features & Benefits</a> •
  <a href="#the-12-phase-validation-taxonomy">Validation Taxonomy</a> •
  <a href="#cli-command-reference">CLI Reference</a> •
  <a href="#python-library-api">Python API</a> •
  <a href="#mission-control-html-console">SIGNAL Console</a>
</p>

</div>

---

## Why Dialog Engine? (The Paradigm Shift)

Enterprise conversational AI systems (IBM Watson Assistant, legacy dialog trees, and agentic conversational state graphs) are deeply nested, non-linear state machines containing thousands of nodes, dynamic Spring Expression Language (SpEL) conditions, multi-turn slot frames, and recursive digressions.

Traditional text-based diff tools (`git diff`) and naive JSON comparators fail completely due to three systemic limitations:

1. **False-Positive Diff Chaos:** Trivial JSON key reordering or sibling movement generates thousands of lines of spurious conflicts.
2. **Blindness to Dynamic SpEL Expressions:** Syntactic anomalies, unreachable branches, type contradictions, and shadowed conditions remain undetected until runtime failures in production.
3. **Scale & Digression Exhaustion:** Massive enterprise trees (28,000+ nodes, 80+ MB JSON exports) trigger out-of-memory crashes during naive DOM parsing, while recursive digressions corrupt conversation stack state.

```mermaid
flowchart TD
    subgraph NaiveDiff ["❌ TRADITIONAL NAIVE DIFF (Line/Key Noise)"]
        direction LR
        N1["[Node A (line 40)]"] <-.->|Spurious Diff Chaos| N2["[Node A (line 1200)]"]
    end

    subgraph ASTDiff ["✅ DETERMINISTIC DIALOG AST ENGINE (Semantic Invariants)"]
        Root["[Root Tree]"] --> Intent["[Intent: #transfer]"]
        Intent --> Slot["[Slot: $amount (@sys-number)]"]
        Slot --> Cond["[Condition: $amount > 0]"]
        Cond --> Success["[Success Node]"]
        Root -.->|Deterministic UUID Binding| Success
        Root --> Digression["[Digression: #help]"]
        Digression -->|Stack Return| Success
    end

    classDef naiveStyle fill:#331c24,stroke:#f38ba8,stroke-width:2px,color:#f38ba8;
    classDef astStyle fill:#182820,stroke:#a6e3a1,stroke-width:2px,color:#a6e3a1;

    class N1,N2 naiveStyle;
    class Root,Intent,Slot,Cond,Success,Digression astStyle;
```

---

## Universal Schema Binding & Total Decoupling (`SchemaBinding`)

The Dialog Engine is **100% agnostic to vendor-specific key names and proprietary JSON schemas**. Powered by `tare_dialog.schema_adapter` ([ADR-0006](docs/adr/0006-universal-schema-binding-and-state-machine-adapter.md)), the engine dynamically discovers and binds any conversational state machine into the canonical **Universal Abstract Syntax Tree (UniversalDialogAST)**:

```mermaid
flowchart TD
    subgraph Inputs ["1. Heterogeneous State Machines & Dialog JSONs"]
        W1["🔵 Watson V1 Flat<br/>(dialog_nodes, conditions, parent)"]
        W2["🟣 Watson V2 Actions<br/>(actions, steps, handlers)"]
        Ent["🟢 Custom Enterprise Schemas<br/>(flow_nodes, subflows, predicates, memory_frame)"]
        Rasa["🟠 Rasa / Custom Agent Graphs<br/>(states, guard, transitions)"]
    end

    subgraph Adapter ["2. Universal Schema Discovery"]
        Discovery["🧭 Automated Schema & Confidence Discovery<br/>• Structural key alignment matrix<br/>• Declarative custom key bindings"]
    end

    subgraph CoreAST ["3. Universal Dialog AST"]
        AST["💎 Canonical AST Primitives & Invariants<br/>Mutator • Rule Auditor • AST Diff • Validator • Graph"]
    end

    W1 --> Discovery
    W2 --> Discovery
    Ent --> Discovery
    Rasa --> Discovery

    Discovery --> AST

    classDef inStyle fill:#1e1e2e,stroke:#89b4fa,stroke-width:2px,color:#cdd6f4;
    classDef adStyle fill:#2d1b4e,stroke:#cba6f7,stroke-width:2px,color:#cdd6f4;
    classDef astStyle fill:#182820,stroke:#a6e3a1,stroke-width:2px,color:#a6e3a1;

    class W1,W2,Ent,Rasa inStyle;
    class Discovery adStyle;
    class AST astStyle;
```

### Auto-Discovery in Code:
```python
from tare_dialog import SchemaBinding

# 1. Automatic Schema Discovery with Confidence Scoring
binding = SchemaBinding.discover(unknown_document)
print(f"Schema: {binding.schema_name} (Confidence: {binding.confidence_score * 100}%)")

# 2. Agnostic Node Iteration (Zero hardcoded keys!)
for node in binding.iter_all_nodes(unknown_document):
    node_id = binding.get_id(node)
    cond = binding.get_condition(node)
    ctx = binding.get_context(node)
```

---

## Real-World Practical Examples (What We Solve)

To understand how **Dialog Engine** protects high-stakes conversational agents in banking, insurance, and telecommunications, consider **5 real-world production cases** where generic tools fail:

---

### 🚨 Example 1: The "Silent Bug" in Credit Underwriting (Rule Mutation & Test Blindspots)

* **The Scenario:** A banking assistant evaluates user credit scores to approve credit card limit increases.
* **The Code in Dialog Node:**
  ```json
  {
    "dialog_node": "node_credit_underwriting",
    "context": {
      "limit_evaluation": "<? ($user_score >= 750 && $account_months > 6) ? 'approved' : 'analysis' ?>"
    }
  }
  ```
* **The False Sense of Security:** The QA team has 5 automated tests (check balance, view invoices, request help). All pass with 100% success.
* **What the Rule Mutator (`dialog-engine audit-rules`) does:**
  1. The engine **inverts the business logic**: flips `>= 750` to `< 750` (denying good credit and approving bad debtors!).
  2. Runs the existing test scenarios against the mutated bot.
  3. **Result:** All 5 tests still pass with 100% green!
  4. **The Engine Alert:** 
     `[🔴 FINANCIAL RISK] Test Blindspot Detected: No existing test validates the credit underwriting threshold in node_credit_underwriting!`
* **The Automatic Solution:** Using `--synthesize-gaps`, the engine **synthesizes the missing JSON test scenario automatically**:
  ```json
  {
    "id": "gap_test_credit_score_high",
    "name": "[Auto-Synthesized] Verify Credit Approval for High Score",
    "turns": [
      {
        "input": {"text": "I want to increase my limit", "context": {"user_score": 800, "account_months": 12}},
        "expected": {"node": "node_credit_underwriting"}
      }
    ]
  }
  ```

---

### 🚨 Example 2: The Number Slot "Zero" Trap (12-Phase Static Validation)

* **The Scenario:** A customer satisfaction prompt asks:
  > *"On a scale from 0 to 10, how likely are you to recommend us?"*
* **The Slot Configuration in the Bot:**
  ```json
  {
    "variable": "$nps_score",
    "conditions": "@sys-number > 0"
  }
  ```
* **The Production Failure:** The prompt explicitly accepts `0`, but the slot condition `@sys-number > 0` **discards zero**.
  - When an unsatisfied customer enters `0`, the bot loops: *"Sorry, I didn't understand. Enter a number from 0 to 10"*. The user abandons the chat.
* **How Dialog Engine catches it:**
  **Phase 4** (`sys_number_zero_not_captured`) audits both the natural language prompt and the SpEL AST condition, flagging the contradiction prior to deployment:
  ```text
  [⚠️ SEMANTIC WARNING] slot_nps_rating: The prompt includes zero in its domain ("0 to 10"),
  but the capture condition (@sys-number > 0) rejects zero!
  ```

---

### 🚨 Example 3: The 3,000-Line "Ghost Diff" (Semantic AST Diff)

* **The Scenario:** A conversational curator merely updated a node title from *"Main Menu"* to *"Start Menu"* in a visual web studio. The visual tool exported the JSON with reordered object keys.
* **In Traditional `git diff`:**
  ```diff
  - "title": "Main Menu",
  - "conditions": "#menu",
  - "responses": [ ... ],
  + "conditions": "#menu",
  + "responses": [ ... ],
  + "title": "Start Menu"
  @@ ... 3,200 lines of spurious conflict in Pull Request ... @@
  ```
  *(PR reviews become impossible — reviewers cannot find the actual change).*
* **In `dialog-engine diff`:**
  ```text
  ============================================================
    tare.tools — Semantic AST Diff Report
  ============================================================
  Nodes Added:   0
  Nodes Removed: 0
  Nodes Changed: 1

  ~ [node_main_menu] Main Menu -> Start Menu
    • title: "Main Menu" -> "Start Menu"
  ============================================================
  ```
  *(Instant surgical identification with zero noise).*

---

### 🚨 Example 4: The Hidden Infinite Loop in Digression (Topological Graph)

* **The Scenario:**
  1. Node `Welcome` jumps to `CheckAuthentication`.
  2. `CheckAuthentication` jumps to `OptionsMenu`.
  3. During later maintenance, a fallback jump was added to `OptionsMenu` pointing back to `Welcome`.
* **The Production Failure:** The user types "hello" and the assistant enters an **infinite loop of 50 turns per execution**, exhausting backend resources and API quotas.
* **How Dialog Engine catches it:**
  The `dialog-engine graph` module constructs a directed graph (`networkx.DiGraph`) and blocks the CI/CD pipeline:
  ```text
  [🔴 GRAPH CYCLE DETECTED] Infinite loop found:
  node_welcome -> node_auth_check -> node_menu_options -> node_welcome
  ```

---

### 🚨 Example 5: The Unclosed SpEL Parenthesis (Hardened SpEL Sandbox)

* **The Scenario:** A curator typed a compound SpEL condition with a typo:
  ```json
  "conditions": "#invoice_query && ($channel == 'whatsapp' || ($client_type == 'corp'"
  ```
  *(Missing the closing parenthesis `)` at the end).*
* **The Production Failure:** In Watson Assistant or Copilot Studio, when a user triggers this route, the engine crashes and outputs the system fallback error: *"Sorry, an unexpected error occurred."*
* **How Dialog Engine catches it:**
  The static lexer `tare_dialog.spel` audits expressions without executing arbitrary code:
  ```text
  [❌ SYNTACTIC ERROR] node_invoice_query: context_spel_unclosed_parenthesis
  Expression: ($channel == 'whatsapp' || ($client_type == 'corp'
  Error: Unclosed parenthesis detected at character index 36.
  ```

---

## Automated Test Generation & Curation

Even if your project has zero tests today, **Dialog Engine automatically synthesizes and runs your full test suite**:

```mermaid
flowchart TD
    subgraph Sources ["1. Conversational Input Sources"]
        Topology["🌐 Dialog AST Topology"]
        Diff["📝 Semantic AST Diff"]
        Rules["⚖️ Business Logic Conditions"]
    end

    subgraph Engines ["2. Synthesis Engines"]
        TopoGen["🌲 Topology Test Synthesis<br/>generate-tests"]
        DiffGen["🎯 Diff-Targeted Synthesis<br/>generate-diff-tests"]
        RuleAudit["🔬 Mutation Blindspot Synthesis<br/>audit-rules --synthesize-gaps"]
    end

    subgraph Runner ["3. Execution & Verification"]
        RunnerCore["⚡ In-Memory Deterministic Runner<br/>dialog-engine test<br/>(Sub-millisecond execution, zero network)"]
        Reports["📊 Test Evidence & Coverage Reports"]
    end

    Topology --> TopoGen
    Diff --> DiffGen
    Rules --> RuleAudit

    TopoGen --> RunnerCore
    DiffGen --> RunnerCore
    RuleAudit --> RunnerCore

    RunnerCore --> Reports

    classDef srcStyle fill:#1e1e2e,stroke:#89b4fa,stroke-width:2px,color:#cdd6f4;
    classDef engStyle fill:#2d1b4e,stroke:#cba6f7,stroke-width:2px,color:#cdd6f4;
    classDef runStyle fill:#182820,stroke:#a6e3a1,stroke-width:2px,color:#cdd6f4;

    class Topology,Diff,Rules srcStyle;
    class TopoGen,DiffGen,RuleAudit engStyle;
    class RunnerCore,Reports runStyle;
```

---

## Feature Catalog & Benefits

| Module / CLI | Key Capability | Tangible Engineering Benefit |
|---|---|---|
| **`schema_adapter`** | Universal Schema Binding & Discovery | Complete decoupling from vendor JSON names with automatic semantic alignment. |
| **`generate-tests`** | Automated Test Generation | Automatic synthesis of conversational test scenarios from node topology. |
| **`generate-diff-tests`** | Diff-Driven Test Synthesis | Targeted test generation exclusively for changed/added nodes. |
| **`audit-rules`** | Business Rule Audit & Test Blindspots | Injects business faults and automatically synthesizes missing JSON test scenarios. |
| **`mutate`** | Symbolic AST & Automata Mutation | 7 formal operators and metamorphic testing proving 100% detection and 0 false alarms. |
| **`diff`** | Noise-Free Semantic AST Diff | Node matching by immutable UUID, eliminating false conflicts from JSON key ordering. |
| **`validate`** | 12-Phase Static Validator | Single quality contract covering SpEL syntax, topology, slots, handoffs, and causality. |
| **`spel`** | Hardened SpEL Lexer & Sandbox | Static syntax auditing and fail-closed evaluation with LRU caching and dunder protection. |
| **`graph`** | Topological Graph & Cycle Detection | Early discovery of infinite loops with export to JSON and Graphviz DOT. |
| **`explore`** | Universal Schema Introspection | Lossless bidirectional normalization between Watson V1 flat and enterprise nested schemas. |
| **SIGNAL Console** | Web Triage Console (HTML) | Zero-install web application with 14 engineering themes, instant search, and curation drawer. |

---

## Architectural Pillars

```mermaid
flowchart TD
    subgraph Layer1 ["1. Core Ingestion & Dynamic Evaluation"]
        Schema["🧭 Universal Schema Adapter<br/>tare_dialog.schema_adapter"]
        Spel["⚡ Hardened SpEL AST & Lexer<br/>tare_dialog.spel"]
        Graph["🌐 Topological Graph & Cycle Detector<br/>tare_dialog.graph"]
    end

    subgraph Layer2 ["2. Analysis, Validation & Fuzzing"]
        Diff["🔍 Semantic AST Diff Engine<br/>tare_dialog.diff"]
        Validator["🛡️ 12-Phase Static Validator<br/>tare_dialog.validator"]
        Mutator["🧬 Symbolic Mutation Fuzzer<br/>tare_dialog.mutator"]
    end

    subgraph Layer3 ["3. Cockpit & User Interfaces"]
        CLI["💻 Rich Terminal CLI<br/>dialog-engine"]
        SIGNAL["🖥️ SIGNAL Mission Control Web Console<br/>triage_viewer.html"]
    end

    Schema --> Diff
    Spel --> Validator
    Graph --> Mutator

    Diff --> CLI
    Validator --> CLI
    Mutator --> CLI

    CLI --> SIGNAL

    classDef l1Style fill:#1e1e2e,stroke:#89b4fa,stroke-width:2px,color:#cdd6f4;
    classDef l2Style fill:#2d1b4e,stroke:#cba6f7,stroke-width:2px,color:#cdd6f4;
    classDef l3Style fill:#182820,stroke:#a6e3a1,stroke-width:2px,color:#a6e3a1;

    class Schema,Spel,Graph l1Style;
    class Diff,Validator,Mutator l2Style;
    class CLI,SIGNAL l3Style;
```

---

## Dual Distribution Strategy

The project provides **two distinct distributions** ([ADR-0004](docs/adr/0004-dual-distribution-strategy-modular-and-ephemeral.md)):

```mermaid
flowchart LR
    subgraph DistA ["📦 DISTRIBUTION A: MODULAR PACKAGE (CLI / CI / Server)"]
        direction TB
        A1["• Full <code>src/tare_dialog</code> package<br/>• orjson, networkx, pydantic, rich<br/>• CLI: mutate, audit-rules, generate-tests<br/>• SIGNAL Mission Control Console (HTML)<br/>• 151 pytest automated test suites"]
    end

    subgraph DistB ["⚡ DISTRIBUTION B: EPHEMERAL STANDALONE (Sandboxes / Copilot)"]
        direction TB
        B1["• Zero-install single script: <code>dist/dialog_engine_standalone.py</code><br/>• Portable ZipApp executable: <code>dist/dialog_engine.pyz</code> (~59 KB)<br/>• Direct upload to ChatGPT Code Interpreter & Copilot Sandboxes"]
    end

    classDef distAStyle fill:#2d1b4e,stroke:#cba6f7,stroke-width:2px,color:#cdd6f4;
    classDef distBStyle fill:#182820,stroke:#a6e3a1,stroke-width:2px,color:#a6e3a1;

    class DistA distAStyle;
    class DistB distBStyle;
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

### Run Test Suite (151 Automated Tests)
```bash
python -m pytest
```

---

## CLI Command Reference

The `dialog-engine` (or `tare-dialog`) CLI provides native `rich` terminal output:

### 1. Automated Test Generation (`generate-tests` & `generate-diff-tests`)
```bash
# Synthesize conversational test scenario reaching a target node
dialog-engine generate-tests input/skill.json node_card_invoice --output tests/test_invoice.json

# Synthesize targeted tests for changes between two versions
dialog-engine generate-diff-tests current.json candidate.json --output tests/diff_tests.json

# Execute scenario in deterministic in-memory runner
dialog-engine test input/skill.json tests/test_invoice.json
```

### 2. Business Rule Audit & Test Blindspots (`audit-rules`)
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

### 3. Symbolic AST Mutation Analysis (`mutate`)
```bash
# Execute formal mutation testing and compute Mutation Score
dialog-engine mutate input/skill.json

# Export mutated JSON variants for external fuzzing
dialog-engine mutate input/skill.json --output-dir dist/mutants/
```

### 4. Semantic AST Diff (`diff`)
```bash
# Rich formatted terminal diff
dialog-engine diff input/current.json input/candidate.json --format rich

# Generate Markdown diff report
dialog-engine diff input/current.json input/candidate.json --format markdown --output output/diff.md

# Generate structured JSON diff
dialog-engine diff input/current.json input/candidate.json --format json --output output/diff.json
```

### 5. Static Validation (`validate`)
```bash
# Rich terminal validation table
dialog-engine validate input/skill.json --rich

# Export full validation report in JSON
dialog-engine validate input/skill.json --output output/validation_report.json
```

### 6. Flow Graph & Cycle Detection (`graph`)
```bash
# Generate topological graph and reachability telemetry
dialog-engine graph input/skill.json --output-json output/graph.json

# Export Graphviz DOT visualization
dialog-engine graph input/skill.json --output-dot output/graph.dot
```

---

## Python Library API

```python
import tare_dialog as td

# 1. High-speed document loading with auto-discovered schema
doc = td.load_json("input/skill.json")
binding = td.SchemaBinding.discover(doc)
print(f"Schema: {binding.schema_name} (Confidence: {binding.confidence_score * 100}%)")

# 2. Audit business rules against test scenarios
scenarios = td.load_json("tests/scenarios.json")
report = td.evaluate_rules_against_scenarios(doc, scenarios, binding=binding)
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
- **Interactive Curation:** Approve/reject mutants and export signed compliance manifests with 1-click.

---

## Ecosystem Family

| Repository | Role | Technology |
|---|---|---|
| **[`tare.tools.os`](https://github.com/augusto-scarvalho/tare.tools.os)** | Agent Operating System & Central Swarm Orchestrator | Python, AsyncIO, Submodules |
| **[`tare.tools.kernel`](https://github.com/augusto-scarvalho/tare.tools.kernel)** | 5-Plane Agent OS Core Runtime & Sandboxing | Python, SQLite WAL, bwrap |
| **[`tare.tools.specgraph`](https://github.com/augusto-scarvalho/tare.tools.specgraph)** | Spec-Driven Development & Causal Matrix | Python AST, Tree-Sitter, Schemas |
| **[`tare.tools.backlog-graph`](https://github.com/augusto-scarvalho/tare.tools.backlog-graph)** | Deterministic DAG Task Backlog Engine | Python (Pure Stdlib), CAS |
| **[`tare.tools.dialog-engine`](https://github.com/augusto-scarvalho/tare.tools.dialog-engine)** | Topological Interaction & AST Dialog Graphs (This Repo) | Python, Statecharts, orjson |
| **[`tare.tools.research`](https://github.com/augusto-scarvalho/tare.tools.research)** | Scientific Papers, ADRs & Knowledge Hub | Markdown, GitHub Pages, Jekyll |

---

## License

Distributed under the **Apache-2.0** License. See [LICENSE](LICENSE) and [NOTICE](NOTICE) for complete details.
