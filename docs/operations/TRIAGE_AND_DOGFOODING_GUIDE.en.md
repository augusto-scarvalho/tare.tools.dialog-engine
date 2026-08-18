# Triage, Dogfooding, and Calibration Guide — Watson Dialog Tools

**Status:** Official Source of Truth  
**Version:** 1.0  
**Scope:** Finding classification criteria, dogfooding workflow, and continuous recalibration loop for Watson Assistant Dialog audit and validation tools.

---

## 1. What is the Dogfooding & Triage Process?

The objective of our tool suite is not merely to raise warnings on Watson Assistant JSON exports, but to enable human reviewers to audit and classify detector findings (*detector hits*) to feed back into the validator.

The decision chain follows the principle:
$$\text{Detector Hit} \longrightarrow \text{Root Cause} \longrightarrow \text{Runtime/Design Interpretation} \longrightarrow \text{Product Impact} \longrightarrow \text{Calibration Decision}$$

---

## 2. Decision Taxonomy (Triage Status Meanings)

When inspecting each finding in the triage interface, classify it under one of three core statuses:

### 🐞 **1. Confirmed Bug (Real Flow / Product Defect)**
* **Definition:** The validator identified an actual defect that **breaks the user journey, blocks conversational progress, or degrades user experience in production**.
* **Responsibility:** Dialog Content / Authoring in Watson Assistant.
* **Expected Action:**
  1. Record in triage as a Confirmed Bug.
  2. Create a backlog task for conversational flow repair in Watson Assistant.
* **Common Examples:**
  - **Zero not captured:** The prompt asks *"Rate from 0 to 10"*, but the slot capture condition uses bare `@sys-number` (which rejects `0` in Watson), making it impossible to input zero.
  - **Capture type mismatch:** The slot captures `@sys-number`, but child nodes inspect `$inputType:document` (PDFs/documents).
  - **Invalid SpEL syntax:** Expressions like `@entity:(value).literal` or `@entity(...)` that fail in IBM runtime.
  - **Logical contradiction:** Impossible slot enable condition, e.g., `$flag && $flag == false`.

---

### 🛡️ **2. False Positive / Intentional (Validator Calibration)**
* **Definition:** The validator raised a warning, but the bot flow is **correct and working according to intended design**. The issue lies in the **assumption or sensitivity of our detector**.
* **Responsibility:** Audit Tools (`watson_dialog_*.py` / Antigravity).
* **Expected Action:**
  1. Record as False Positive / Intentional.
  2. Add a *Rationale* note explaining the design context.
  3. Export triage so the developer/model can adjust validator rules.
* **Common Examples:**
  - Sentinel nodes or fallbacks with condition `true` accessed strictly via dynamic `Jump` from another module.
  - Context variables injected dynamically by webhooks or backend integrations (e.g., `$integrations`, `$user_claims`).
  - Digression intentionally blocked to ensure user completes a mandatory form/frame.

---

### 📦 **3. Technical Debt / Backlog (Non-Critical)**
* **Definition:** An actual structural imperfection in the JSON, but **without direct impact on customer experience in production**. Pertains to legacy code, dormant drafts, or non-critical formatting.
* **Responsibility:** Technical Debt / Periodic Maintenance.
* **Expected Action:**
  1. Keep classified as Technical Debt / Backlog.
  2. Validator classifies as `info` or `provenance` severity to avoid polluting high-priority (P0/P1) queues.
* **Common Examples:**
  - References to deleted entities/intents inside nodes marked `INATIVO` or `REVISAO`.
  - Branches intentionally disabled via `false` condition kept as historical drafts.
  - Sibling nodes with identical sequence numbers where relative order does not alter conversational output.

---

## 3. How to Use the Triage Console (`triage_viewer.html`)

1. **Corpus Selection:**
   - Switch in the header between **`CURRENT`** (production version) and **`CANDIDATE`** (release candidate version).
2. **Node Inspection (UUID):**
   - Click the **`🔍 Inspect Node`** button on any card to open the slide-over drawer showing:
     - Full ancestor breadcrumbs and hierarchy.
     - Execution metadata, jumps, and digression flags.
     - Formatted SpEL activation condition.
     - Slots, context variables, and event handlers.
     - Configured responses and child branches.
     - Raw JSON viewer with one-click copy button.
3. **Classification and Notes:**
   - Click the corresponding button (🐞 Confirmed Bug, 🛡️ False Positive, or 📦 Technical Debt).
   - Enter notes in the rationale input (crucial for calibrating false positives).
   - Progress is automatically persisted in the browser's `localStorage`.
4. **Exporting Decisions:**
   - **`📤 Export Triage (JSON)`**: Generates `watson_triage_decisions_<corpus>_<date>.json` for ingestion by assistant/CLI.
   - **`📄 Export Report (Markdown)`**: Generates an executive summary markdown report.
