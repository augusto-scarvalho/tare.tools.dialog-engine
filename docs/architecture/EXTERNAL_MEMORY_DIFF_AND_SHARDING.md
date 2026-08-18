# External-Memory Diff, Compact Graph, and Semantic Work Sharding

**Status:** CURRENT for legacy exports where noted; PROPOSED where explicitly marked.  
**Scope:** Conversational Dialog State Machine and Tooling Engine.  
**Objective:** Enable semantic analysis of large dialog exports with predictable behavior across developer workstations, Windows/WSL, CI runners, and memory-constrained ephemeral runtimes.

## 1. Problem Statement

Legacy enterprise dialog exports use a deeply nested JSON hierarchy containing root collections, recursive trees, slots, sub-slots, jumps, and extensive payloads. The baseline path relies on standard JSON deserialization (`json.load()`), materializing the entire document into Python objects in memory.

While fast for small files, this approach encounters four systemic bottlenecks as exports grow:

1. Comparing two exports concurrently requires multiple times their raw byte size in memory;
2. `--summary-only` reduces stdout volume, but does not reduce DOM parsing peak memory;
3. Naive byte-by-byte tree scanners rescanning subtrees at each ancestor introduce quadratic overhead;
4. Naive multiprocessing prior to bounding work items multiplies memory usage rather than reducing latency.

The implemented architecture cleanly separates source storage, structural indexing, payload materialization, topological graph modeling, and work scheduling.

## 2. Invariants

The following invariants are mandatory correctness requirements:

- Authoritative JSON exports remain the single source of truth;
- The external engine never holds both full in-memory DOMs simultaneously;
- The `mmap` backend does not invoke `json.load()` during index construction;
- Cryptographic digests serve as fast rejection filters, never as the sole authority for semantic differences;
- Any digest mismatch may trigger extra verification work, but must never omit actual semantic changes;
- Detailed diffs always pass through the canonical `find_differences()` reducer;
- External diff outputs must be semantically identical to the in-memory DOM engine;
- Parallel workers receive only bounded local records, never the entire export document;
- Final output ordering is determined deterministically in the reducer, independent of worker completion order;
- Graph sharding preserves exact topology and invariants without modifying semantics;
- Production datasets remain strictly local and excluded from version control.

## 3. Architectural Overview

```text
                  current.json / candidate.json
                            |
                    size + ResourceBudget
                            |
              +-------------+--------------+
              |                            |
          DOM engine                  external engine
        small fast path                    |
              |                 +----------+----------+
              |                 |                     |
              |             transient                mmap
              |          one DOM at a time      strict external-memory
              |          + JSON record spool    + source byte offsets
              |                 |                     |
              |                 +----------+----------+
              |                            |
              |                       CompactGraph
              |                     + top-level diff
              |                            |
              |                 structural diff plan
              |                            |
              |                 +----------+----------+
              |                 |                     |
              |              serial                parallel
              |            worker pool           worker pool
              |                 |                     |
              |                 +----------+----------+
              |                            |
              |                     semantic reducer
              |                            |
              +----------------------------+
                            |
                    authoritative diff
```

## 4. Indexing Backends

### 4.1 Transient Backend
- Deserializes one DOM at a time into memory;
- Extracts structural metadata and writes individual node records to a temporary spool file;
- Frees the DOM before processing the candidate document;
- Halves peak memory while maintaining high throughput.

### 4.2 Mmap Backend
- Memory-maps the JSON file directly from disk;
- Uses a single-pass streaming scanner to locate byte offsets for each node, slot, and property;
- Materializes records strictly on demand;
- Guarantees low, bounded RAM usage regardless of input file size.

## 5. Topological CompactGraph & Cycle Analysis

The `CompactGraph` models transitions, jumps, digressions, and slot event handlers as a directed graph (`networkx.DiGraph`), providing:
- Deterministic reachability analysis;
- Cycle detection to flag infinite loops prior to deployment;
- Disconnected component and orphan node discovery.
