# ADR-0003 — Resource-Aware Automatic Engine Selection

**Status:** ACCEPTED  
**Date:** 2026-08-15  
**Scope:** Conversational Dialog State Machine and Tooling Engine.

## Context

The semantic diff engine provides three execution paths:

- **In-Memory DOM:** Highest throughput when both documents fit comfortably in RAM;
- **External Transient:** Single-DOM-at-a-time + temporary spool, cutting peak memory in half;
- **External Mmap:** Source-backed strict memory fallback for resource-constrained sandboxes.

The legacy policy for `--engine auto` relied strictly on file size: files below 16 MiB used DOM, while larger files defaulted to external memory.

Empirical benchmarks demonstrate that file size alone is an insufficient proxy on heterogeneous infrastructure. On a modern workstation with dozens of gigabytes of free RAM, forcing external memory for moderately sized exports adds unnecessary overhead. A resource-aware policy provides the optimal trade-off between throughput and safety.

## Decision

`--engine auto` evaluates both file size and currently available system memory:

```text
largest file < 16 MiB
    -> DOM (Fast path)

largest file >= 16 MiB
    -> If available system RAM is unknown: external
    -> Estimate DOM peak = 10 × (current bytes + candidate bytes)
    -> DOM selected only if estimated peak <= 30% of available RAM
    -> Otherwise: external
```

Once `external` is selected, `--index-backend auto` independently chooses between `transient` and `mmap` based on single-DOM budget constraints.

## Overrides & Compatibility

### `--engine dom|external`
Explicit CLI flags maintain complete precedence.

### `WATSON_DIALOG_EXTERNAL_THRESHOLD_BYTES`
The legacy environment variable remains supported:
- If explicitly set and the largest file is below the value: DOM;
- If explicitly set and the largest file meets/exceeds the value: external.

## Positive Consequences

- High-memory workstations automatically use the high-throughput DOM path;
- Memory-constrained CI runners and cloud sandboxes gracefully fall back to external memory;
- Unknown memory conditions default safely to conservative bounds;
- Zero configuration required for optimal out-of-the-box performance.
