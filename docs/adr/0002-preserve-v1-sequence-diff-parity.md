# ADR-0002 — Preserving V1 Positional Diff Semantics During External-Memory Migration

**Status:** ACCEPTED  
**Date:** 2026-08-15  
**Scope:** Conversational Dialog State Machine and Tooling Engine.

## Context

`dialog_nodes` in official V1 exports identifies nodes by the `dialog_node` property. While it might seem natural to treat the collection purely as an unordered key-value map, the baseline DOM engine processes list sequences via `SequenceMatcher` and evaluates position blocks.

The migration to external memory is an optimization for execution efficiency and memory scaling, not an authorization to alter established report contracts without verification.

## Decision

The V1 external engine must preserve exact behavioral parity with the baseline DOM engine:

- Ordered item references;
- Stable canonical matching digests;
- Collision verification via canonical byte comparison;
- `SequenceMatcher(..., autojunk=False)` configuration;
- Identical pairing, deletion, and insertion event planning;
- Exact semantic reducer integration with `find_differences()`;
- Strict reproduction of legacy non-UUID collection behavior for byte-level parity.

## Positive Consequences

- Parity can be validated via deterministic byte-by-byte comparison;
- No behavioral drift is hidden inside low-level performance improvements;
- Clean fallback to in-memory DOM remains guaranteed;
- V1 gains external memory capabilities without creating conflicting report schemas;
- Future identity-aware diff modes can be benchmarked against a stable, reproducible baseline.

## Negative Consequences & Trade-offs

- V1 structural reordering continues to report positional shifts in sequence;
- Non-UUID reports retain historical duplication patterns in `changes[]`.

These aspects represent compatibility debt, not defects in the external memory engine.

## Rejected Alternatives

### Re-indexing `dialog_nodes` by `dialog_node`
**REJECTED for parity.** While conceptually cleaner, it breaks byte-level parity with historical test baselines.

### Normalizing V1 to Legacy Tree Before Diffing
**REJECTED.** Lossy normalization strips custom or unmodeled V1 fields, preventing authoritative comparison of the raw source document.

### Materializing Entire `dialog_nodes` in External Memory
**REJECTED.** Defeats the primary goal of bounded memory footprint for multi-megabyte exports.
