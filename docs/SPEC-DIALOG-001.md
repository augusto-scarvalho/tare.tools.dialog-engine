# SPEC-DIALOG-001: Topological dialogue engine and statechart protocol

- **Status:** `CANONICAL_SSOT`
- **Canonical repository:** `tare.tools.dialog-engine`
- **Governing decision:** [ADR 0007](adr/0007-dialog-engine-north-star.md)
- **Version:** 1.0.0
- **Relocated from:** `tare.tools.library@d5473e69:specs/SPEC-DIALOG-001.md`

## Purpose

Specify the topological conversation engine, hierarchical state machines and
schema-agnostic dialogue-protocol fuzzing.

## Verifiable acceptance criteria

- **AC-01 — Schema-agnostic ingestion:** raw transcripts are converted into a
  canonical AST without depending on a proprietary provider format.
- **AC-02 — Statechart turn transitions:** conversational states such as
  dispute, convergence, questioning and consensus follow a finite,
  deterministic transition matrix.
- **AC-03 — Multi-seat quorum evaluation:** deliberation verdicts require an
  explicit configurable quorum and explicit confidence scores.

