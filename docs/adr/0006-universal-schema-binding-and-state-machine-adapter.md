# ADR-0006: Universal Schema Binding, Semantic Decoupling, and On-Demand Mutation

## Status
**ACCEPTED** — Implemented in `src/tare_dialog/schema_adapter.py` and integrated across all Dialog Engine modules.

---

## Context & Problem

Enterprise conversational AI platforms utilize a wide variety of JSON schemas and export structures:
1. **IBM Watson Assistant V1 Classic:** Flat lists of `dialog_nodes` with pointer topologies (`parent`, `previous_sibling`) and SpEL expressions (`conditions`).
2. **IBM Watson Assistant V2 Actions:** Action-oriented representations with `actions`, `steps`, and `handlers`.
3. **Enterprise Nested & Custom Dialog Trees:** Deep hierarchical trees with localized property names (`nos`, `filhos`, `condicao`, `contexto`, `slots`).
4. **Alternative State Frameworks (Rasa, Botpress, Dialogflow, Generic Automata):** Formats utilizing `states`, `guards`, `transitions`, `memory`, `branches`.

### The Risk of Schema Coupling
If analysis tools (semantic diff, rule mutators, static validators, graph analyzers) rely on hardcoded property names (`node.get("condicao")` or `node.get("filhos")`), the engine becomes tightly coupled to a single vendor dialect, breaking portability across heterogeneous systems.

Furthermore, on massive enterprise trees (28,000+ nodes and 80+ MB JSON exports), eager deep-cloning (`deepcopy`) for tens of thousands of mutant variants exhausts available memory.

---

## Architectural Decision

We implement a **decoupled semantic adaptation layer** based on three core architectural tenets:

### 1. Vendor-Agnostic `SchemaBinding` & `KeyMapping`
A declarative abstraction translating arbitrary JSON formats into canonical **Universal Abstract Syntax Tree (UniversalDialogAST)** primitives:
- **Node Identifier:** `get_id(node)` ➔ maps `dialog_node`, `uuid`, `id`, `state_id`, `name`, `key`.
- **Title / Name:** `get_title(node)` ➔ maps `title`, `nome`, `name`, `label`.
- **Condition / Guard:** `get_condition(node)` & `set_condition(node, val)` ➔ maps `conditions`, `condicao`, `guard`, `when`.
- **Context / Memory:** `get_context(node)` & `set_context_variable(node, k, v)` ➔ maps `context`, `contexto`, `variables`, `state`.
- **Hierarchy & Children:** `get_children(node)` ➔ maps `children`, `filhos`, `branches`, `steps`.
- **Captures & Slots:** `get_slots(node)` ➔ maps `slots`, `parameters`, `entities_capture`.

### 2. Automatic Schema Discovery with Confidence Scoring (`SchemaBinding.discover`)
The engine inspects structural keys across the document and dynamically infers alignment to the canonical AST, calculating a confidence score and allowing user overrides via declarative `KeyMapping`.

### 3. Lazy On-Demand Mutant Materialization
Instead of cloning the entire baseline document upfront during discovery, each `RuleMutant` stores only its mutation delta (`node_id`, `new_cond`, `new_ctx_key`, `new_ctx_val`). The complete mutated document is generated lazily on demand when a test scenario is executed against it. This reduces discovery time for 29,000+ mutants to less than **0.6 seconds**.

---

## Architecture Diagram

```text
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │ UNKNOWN INPUT FORMAT (Watson V1, V2, Rasa, Nested Enterprise Trees)        │
  └─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │ 🧭 SCHEMA AUTO-DISCOVERY & BINDING (SchemaBinding.discover)                 │
  │    • Inspects structural keys and computes alignment matrix                 │
  │    • Supports declarative custom bindings (KeyMapping) or auto-inference   │
  └─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │ 💎 UNIVERSAL CANONICAL AST (UniversalDialogAST & Formal Invariants)         │
  │    • All modules operate EXCLUSIVELY upon canonical accessors:              │
  │      [Diff Engine] • [12-Phase Validator] • [AST Mutator] • [Rule Mutator] │
  └─────────────────────────────────────────────────────────────────────────────┘
```

---

## Consequences & Benefits

### Positive
- **100% Decoupled:** Operates across arbitrary enterprise conversational JSONs without source code modifications;
- **Extensible:** Integration with new platforms (Rasa, Botpress, LangGraph) requires only specifying a `KeyMapping`;
- **High Performance:** 36,135 nodes navigated in 0.10s and 29,202 mutants generated in 0.56s on 83 MB trees;
- **Auditability:** Audit manifests (`audit_manifest.json`) track schema alignment and curator decisions independently of vendor formats.
