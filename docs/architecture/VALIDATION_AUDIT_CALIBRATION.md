# Validation Audit Calibration

**Status:** CURRENT implementation contract
**Date:** 2026-08-15
**Scope:** legacy Watson Assistant Dialog validation confidence and false-positive control

## 1. Purpose

The validator is a screening and assurance instrument. A detector hit is not automatically a product defect. This slice calibrates the validator against the production-derived audit corpus so that output preserves uncertainty instead of promoting weak structural heuristics to warnings.

The immutable production-derived reports and manual cluster audits live under `.relay/evidence` and `.relay/audits`. They are operational evidence and are intentionally not tracked by Git. This document records the ratified implementation consequences only.

## 2. Before and after

On the private CURRENT export used for calibration:

| Metric | Before | After |
|---|---:|---:|
| total findings | 17,326 | 7,160 |
| errors | 2 | 2 |
| warnings | 17,018 | 92 |
| informational/provenance | 306 | 7,066 |

The decrease is not achieved by deleting evidence. Large ambiguous families are retained as lower-authority information or compressed provenance records.

The two syntactic errors remain unchanged.

## 3. Explicit `false` is deliberate disabled-node evidence

Watson Dialog supports `false` as a deliberate condition for disabling a branch or keeping a node available only through alternate control flow.

Therefore:

- conditions made unsatisfiable by an explicit `false` emit `disabled_condition_false` with severity `info`;
- accidental contradictions without explicit `false` remain `unsatisfiable_condition` warnings;
- graph reachability still treats both classes as unavailable through normal condition evaluation;
- the node itself is not deleted and can remain a valid jump target.

This preserves the distinction between **normal-flow reachability** and **configuration validity**.

## 4. Legacy ordering is provenance, not a product error

The normalized legacy export contains `sequencia`, but duplicate sequence values do not establish a unique relative order. The previous validator resolved ties with UUIDs and then used that invented order to make control-flow claims.

The calibrated contract is:

- duplicate sequence values emit one `legacy_order_ambiguous` record per `(sibling group, sequence)` tie set;
- category is `provenance` and severity is `info`;
- the value contains the sequence and all participating node IDs;
- no UUID tie-break is used to prove shadowing or duplicate-condition unreachability.

On the calibration export, 9,614 per-node warnings became 4,698 tie-set provenance records.

## 5. `anything_else` uses observable source order

For the normalized legacy representation, `anything_else_not_last_sibling` uses physical sibling-array order rather than synthetic sorting. Nodes marked by the local normalized status as `INATIVO` or `REVISAO` do not generate an active-flow ordering warning.

This rule does not claim that the project-local `status` field is an IBM API primitive. It is source evidence used to avoid an active-runtime claim about explicitly non-operational configuration.

## 6. Confidence-qualified shadows and duplicate conditions

`shadowed_by_always_true` and `duplicate_sibling_condition` are emitted only when:

1. every sibling in the group has a non-null unique sequence;
2. the relevant nodes and their ancestry are not explicitly non-operational (`INATIVO` / `REVISAO`) and are not under an unsatisfiable condition;
3. no observed Jump target enters the interval between the earlier node and the candidate.

This changes the production-derived counts from:

- `shadowed_by_always_true`: 4,388 → **3**;
- `duplicate_sibling_condition`: 306 → **16**.

The remaining rows are confidence-qualified control-flow claims rather than bulk heuristics.

## 7. Digression conflict calibration

The IBM digression constraint remains: forcing continuation through an active `true`/`anything_else` child or a forced transition can make digression-out ineffective.

The calibrated validator:

- skips active-flow digression claims on paths marked non-operational or statically unsatisfiable;
- ignores forcing children marked `INATIVO` or `REVISAO`;
- preserves forced-transition findings on operational paths.

Production-derived counts become:

- `digression_blocked_by_forcing_child`: **30**;
- `digression_blocked_by_transition`: **14**.

These are configuration-conflict warnings, not proof that the user journey fails.

## 8. Slot dependency correction

A slot condition that references the same context variable stored by that slot is not a dependency on a later slot merely because a later slot reuses the same variable.

`slot_depends_on_later_slot` therefore ignores later slots whose context-variable name equals the current slot's own variable.

No strong duplicate-slot warning is created from variable reuse alone. Audit showed that `condicaoSlots`, slot ordering and conditional variants are necessary to interpret reuse safely.

## 9. `@sys-number`: causal diagnostics instead of blanket warnings

Bare `@sys-number` is not automatically a defect because many slots intentionally accept only positive selectors/domains.

The former blanket `sys_number_zero_not_accepted` warning is retired. The validator emits only narrower causal findings on operational paths:

### `sys_number_zero_handler_unreachable`

The capture condition does not accept zero, while a descendant handler explicitly checks `== 0`, `<= 0` or `< 1`.

Calibration export: **19** findings.

### `sys_number_zero_valid_but_not_captured`

The slot prompt explicitly declares a range beginning at zero and a child handles `@sys-number:0`, but the capture condition does not accept zero.

Calibration export: **2** findings.

### `slot_capture_type_mismatch_document`

The slot capture condition uses `@sys-number`, while descendant logic expects `$inputType:document`.

Calibration export: **2** findings representing one repeated root cause.

These diagnostics intentionally do not infer business validity of zero from syntax alone.

## 10. Slot enable-condition contradiction

The audit found one project configuration with the shape:

```text
$x && $x == false
```

The current general boolean solver does not yet relate variable truthiness to boolean equality. Expanding that solver is deliberately out of scope for this slice.

Instead, the validator has a narrow, test-backed detector for the directly proven contradiction (including reversed conjunct order) and emits `unsatisfiable_slot_enable_condition`.

Explicit `condicaoSlots: false` remains deliberate disabled configuration and is not reported by this rule.

## 11. Syntax/reference root-cause deduplication

If a condition contains an invalid direct entity call such as `@entity(...)`, the invalid call is already a syntactic root cause. The same called name is therefore not also emitted as `unknown_entity` merely because it is absent from the entity catalog.

Other unknown entity/intent references remain independent warnings.

## 12. Context-variable registry filtering

Expression-shaped entries in `variaveisContexto` are not interpreted as simple variable declarations for the hyphen ambiguity check. Only identifier-shaped names participate in `ambiguous_context_variable_name`.

This prevents an array index expression containing `-1` from being mistaken for a hyphenated variable name.

## 13. CURRENT × CANDIDATE after calibration

The calibrated high-confidence families are stable between the private CURRENT and CANDIDATE exports:

- 2 syntactic errors;
- 30 forcing-child digression conflicts;
- 14 transition digression conflicts;
- 3 strong always-true shadows;
- 16 strong duplicate-condition branches;
- 19 unreachable zero handlers;
- 2 document capture-type mismatches;
- 1 unsatisfiable slot-enable condition;
- unknown artifact references remain stable.

One zero-domain finding disappears in CANDIDATE because that slot no longer uses a numeric capture condition. This is **detector no longer applicable**, not evidence by itself that the business behavior was corrected.

CANDIDATE also adds five deliberate-false informational findings and six legacy-order tie sets.

## 14. Non-goals and OPEN work

This slice does **not**:

- make normalized `status` a universal IBM runtime primitive;
- implement a complete SpEL theorem prover;
- prove semantic equivalence of duplicate branches;
- automatically repair production exports;
- classify manual `*_escape` digression patterns as errors or valid by name;
- convert every production-derived audit judgement into a hard gate;
- deduplicate all findings into root-cause objects.

Future work may add a root-cause ledger/projection, richer boolean constraints, and confidence metadata while preserving this stable issue contract.

## 15. Assurance and rollback

Regression coverage includes:

- explicit-false classification while preserving graph reachability;
- ambiguous ordering and raw fallback order;
- Jump-aware shadow/duplicate claims;
- `INATIVO`/`REVISAO` control-flow filtering;
- same-variable slot dependency;
- causal zero diagnostics;
- document capture mismatch;
- self-false slot-enable contradiction;
- entity-call root-cause deduplication.

Mutation tests include dedicated regressions for these seams. Rollback is a normal Git revert of this calibration commit; `.relay` evidence remains append-only historical provenance.
