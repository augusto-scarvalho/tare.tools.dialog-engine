# Validation Audit and Calibrated Findings

**Status:** Calibrated Architecture Reference.  
**Objective:** Maintain high-precision diagnostics while distinguishing active product bugs from technical debt and design smells.

## 1. Detector Hit vs Product Defect

The validator enforces a strict separation:
- **Active Product Bugs (P0/P1):** Unreachable handlers for zero numbers, document/number capture type mismatches, SpEL syntax defects, and unsatisfiable slot enable conditions.
- **Design Smells & Runtime Facts:** Digression restrictions overridden by jumps or forcing children, marked as `info` or `EXPECTED_RUNTIME_CONSTRAINT`.
- **Dormant Debt:** Missing catalog entities/intents inside nodes marked `INATIVO` or `REVISAO`, emitted as `info`.

## 2. Zero-Handler Capture Calibration

A bare `@sys-number` condition in Watson Assistant does not match `0`. However, the validator does not flag every bare numeric slot. It flags **only** slots where:
1. The slot's child logic explicitly provides handlers for `< 1`, `<= 0`, or `== 0` (`sys_number_zero_handler_unreachable`).
2. The slot prompt includes a range starting at zero (e.g. `0 a 10` or `0-10`) and defines `@sys-number:0` (`sys_number_zero_valid_but_not_captured`).
3. The slot capture condition expects numbers, but child nodes process `$inputType:document` (`slot_capture_type_mismatch_document`).
