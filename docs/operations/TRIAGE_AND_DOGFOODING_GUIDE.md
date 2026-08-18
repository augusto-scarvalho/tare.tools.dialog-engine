# Triage, Dogfooding, and Curation Guide

**Status:** Official Source of Truth  
**Version:** 1.0  
**Scope:** Finding classification criteria, dogfooding workflow, and calibration taxonomy for Dialog Engine verification tools.

---

## 1. Dogfooding & Triage Workflow

The goal of the engine is not merely to emit static warnings, but to provide a deterministic curation instrument where human reviewers audit findings (*detector hits*) and record authoritative feedback:

$$\text{Detector Hit} \longrightarrow \text{Root Cause Analysis} \longrightarrow \text{Runtime / Design Context} \longrightarrow \text{Product Impact} \longrightarrow \text{Curation Decision}$$

---

## 2. Decision Taxonomy (Curation Statuses)

When inspecting findings in the web console (`triage_viewer.html`), classify each item into one of three core statuses:

### 🐞 **1. Confirmed Bug (Active Product / Flow Defect)**
* **Definition:** The engine detected a real defect that **breaks the conversational journey, blocks the user, or degrades production runtime behavior**.
* **Ownership:** Dialog Design / Content Engineering.
* **Expected Action:**
  1. Record as Confirmed Bug in the triage console.
  2. Open an issue in the dialog repository backlog to fix the root cause.
* **Common Examples:**
  - **Zero Not Captured:** Prompt asks *"Rate us from 0 to 10"*, but capturing condition `@sys-number` rejects `0`, trapping users in a reprompt loop.
  - **Capture Type Mismatch:** Slot condition expects `@sys-number`, but child nodes process `$inputType:document` (PDF/files).
  - **Invalid SpEL Syntax:** Expressions calling `.literal` on booleans or invoking entities as functions (`@entity(...)`) that trigger runtime crashes.
  - **Direct Contradiction:** Slot enable conditions that are mathematically impossible (`$flag && $flag == false`).

---

### 🛡️ **2. False Positive / Intentional Design (Validator Calibration)**
* **Definition:** The engine flagged a rule, but the conversation flow is **correct and operates according to deliberate system design**. The discrepancy stems from over-sensitivity in the static heuristic.
* **Ownership:** Static Analysis Tooling (`tare_dialog.validator`).
* **Expected Action:**
  1. Record as False Positive / Intentional.
  2. Add a rationale note explaining the system architecture.
  3. Export the curated manifest so rules can be recalibrated.
* **Common Examples:**
  - Sentinel fallback nodes with condition `true` reached exclusively via dynamic jumps from external modules.
  - Dynamic context variables injected by backend webhooks (e.g. `$integrations`, `$user_claims`).
  - Digressions intentionally disabled to guarantee required frame completion.

---

### 📦 **3. Technical Debt / Backlog (Non-Breaking Flaw)**
* **Definition:** The finding indicates a legitimate structural flaw, but **does not directly disrupt the end-user experience in production**. It represents legacy configuration or dead code.
* **Ownership:** Architectural Technical Debt / Routine Maintenance.
* **Expected Action:**
  1. Classify as Technical Debt / Backlog.
  2. The validator marks the severity as `info` or `provenance`, keeping high-priority queues (P0/P1) clean.
* **Common Examples:**
  - References to deleted entities/intents inside nodes marked `INACTIVE` or `REVIEW`.
  - Deliberately disabled branches with condition `false` preserved for historical reference.
  - Legacy sibling nodes with identical sequence numbers where relative order does not alter output.

---

## 3. Using the SIGNAL Mission Control Web Console (`triage_viewer.html`)

1. **Open Console:** Launch `triage_viewer.html` in your browser.
2. **Import Report:** Click **"Import"** and select `dist/audit_manifest.json` or `validation_report.json`.
3. **Inspect Nodes:** Select any item in the left sidebar to open the deep inspection drawer.
4. **Record Curation Decisions:** Click **Confirmed Bug**, **False Positive**, or **Technical Debt** and add review notes.
5. **Export Manifest:** Click **"Export JSON"** to download the signed compliance manifest for CI/CD deployment.
