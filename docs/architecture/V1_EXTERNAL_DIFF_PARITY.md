# V1 External Diff Parity

**Status:** CURRENT  
**Ratification Date:** 2026-08-15  
**Scope:** Conversational Dialog State Machine and Tooling Engine.

## 1. Objective

Provide external-memory execution for official Dialog API V1 exports without altering the baseline output contract of `diff_engine.py`.

The objective of this specification is **exact functional parity**, not an unversioned redesign of the diff contract. The in-memory DOM engine remains the authoritative executable verification oracle.

## 2. Established Semantics Preserved

The baseline diff engine processes collections of objects containing `uuid` properties as identity maps. In contrast, `dialog_nodes` uses `dialog_node` as its primary identifier. The baseline comparator executes `compare_list()` and `SequenceMatcher` over the ordered list.

Key semantic invariants:

- Structural reordering produces positional sequence events;
- Insertions and deletions are position-aware;
- A `replace` block compares shared elements by position before emitting remainder items as add/remove;
- `SequenceMatcher` matching utilizes canonical `stable_item(item)` across all properties;
- `ignored_fields` applies during `find_differences()`, but does not alter the baseline alignment of the matcher;
- Non-UUID collections retain their established change reporting behavior for strict byte-level parity.

## 3. V1 External Pipeline Architecture

```text
Current / Candidate V1 JSON
        |
        +--> Root scan / transient flatten
        |
        +--> dialog_nodes ordered item refs
                |
                +--> Ordinal index
                +--> Source / spool byte range
                +--> Stable SHA-256 token
        |
        +--> Exact collision classification
        |
        +--> SequenceMatcher(tokens)
        |
        +--> Ordered work plan
                |
                +--> Equal    -> skip
                +--> Pair     -> bounded payload task
                +--> Delete   -> materialize single item
                +--> Insert   -> materialize single item
        |
        +--> Serial / parallel worker pool
        |
        +--> find_differences() semantic reducer
        |
        +--> Authoritative V1 diff JSON
```

## 4. Verification and Parity Proofs

Parity is validated by automated test suites comparing the JSON output of the in-memory DOM engine against the external memory engine across identical inputs, verifying exact byte-level parity.
