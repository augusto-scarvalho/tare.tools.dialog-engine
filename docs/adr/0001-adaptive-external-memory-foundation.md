# ADR-0001 — Adaptive External-Memory Foundation for Watson Dialog Engine

**Status:** ACCEPTED  
**Date:** 2026-08-15  
**Scope:** Conversational Dialog State Machine and Tooling Engine.

## Context

The toolkit must compare and analyze JSON exports that can exceed typical limits for ephemeral and serverless runtimes. The in-memory DOM engine is fast, but its memory footprint scales rapidly when both documents expand into native Python objects.

Several alternatives were evaluated, including SQLite, pickle, Parquet/Arrow, LMDB, and a custom record spool. The concrete operational problem does not require a full relational database: the JSON export is already authoritative, and we primarily require structural metadata, local random access, and deterministic work partitioning.

## Decision

Adopt the following architectural foundation:

```text
Authoritative JSON
  -> Adaptive index backend
       -> transient: one-DOM-at-a-time + temporary JSON records
       -> mmap: source-backed single-pass + temporary local-record spool
  -> Compact metadata & digests
  -> CompactGraph
  -> Semantic work items / shards
  -> Incumbent semantic reducer / oracle
```

In-memory DOM remains available as a fast path and verification oracle.

## Why Not SQLite by Default

SQLite is robust, but introduces a relational boundary that does not align with the dominant tree-diffing workload. We do not need SQL execution, arbitrary joins, or persistent ACID transactions for scratch analysis paths. It remains a valid technical option if relational storage needs emerge.

## Why Not Pickle

Pickle does not provide indexing on its own, creates tight coupling to Python object representations, and introduces deserialization security risks for untrusted external inputs.

## Why Not Parquet as the Core Foundation

Parquet is suited for columnar analytics and reusable datasets. However, operational tree diffing starts from a hierarchical JSON document and frequently needs to materialize individual semantic records. Enforcing an upfront Parquet conversion for every run would add latency and schema overhead without proven reuse.

## Why Not Arrow IPC as a Mandatory Requirement

Arrow IPC is advantageous for zero-copy memory mapping, but PyArrow introduces a large dependency. It can be used as an optional acceleration layer without changing existing contracts.

## Why JSON Local Spool

A standard `TemporaryFile` containing local JSON records:
- Is straightforward to audit and inspect;
- Does not execute arbitrary code during deserialization;
- Operates reliably across Windows and POSIX;
- Enables low-overhead offset seek operations;
- Automatically cleans up on file closure;
- Eliminates subtree rescans;
- Avoids rigid schema requirements.

## Digest Policy

Digests are used as fast-path match indicators for unchanged branches. They do not replace explicit AST comparisons for changed records.

## Decision Review Criteria

Review this architecture if:
- Input JSON files routinely exceed 1 GB where mmap indexing requires binary columnar storage;
- Persistent multi-run query caches justify an embedded DuckDB/SQLite index;
- Zero-copy native extensions (C++/Rust) become standard deployment dependencies.
