# ARCHITECTURE-EXCEPTION-V2-004 — PROPOSED, NOT APPLIED

**Status:** proposed by the P5 implementation (WP-5.1, 2026-09-24) under the owner's "P5 ENTRY HARNESS CORRECTION /
RESUME WP-5.1" §7; awaiting an owner decision. Nothing in the taxonomy was changed: WP-5.1 ships with `FailureCode`
exactly as sealed with P4.

**Frozen item affected:** F1 — the journal's event payload vocabulary. `FailureCode` is not defined by the RFC and no
F-conformance subcheck pins its member set (`F1.payload_enum.*` pins the six enums the RFC defines: AdequacyOutcome,
Relevance, TestExecutionStatus, TestOutcome, TestSelection, Vacuity), but `failure/observed` carries
`code: _enum(FailureCode)` (`aisef2/journal/event.py`), and the accepted V2-003 analysis reads that as "F1 freezes
those": growing the taxonomy was declared an F1 impact and done only inside an owner-decided exception. The same
reading applies here, so the growth is **not** already authorized by the RFC or the amendment lineage
(V2-001 … V2-003), and the WP-5.1 manifest names only `aisef2/quality/test_execution.py` and F3.

## What WP-5.4 will need

RFC §15.0 fixes the **owners** of every test-execution outcome (rule 1: UNRUNNABLE → ENVIRONMENT, environment retry
policy; rules 2–3: EXECUTED+FAILED and NO_STORY_TESTS_MATCHED → DEVELOPER; rule 4: an undeterminable collection cause
→ INTEGRATION, never charged to the developer). RFC §22 fixes that **retryability and budget are properties of the
typed code, fixed once in the taxonomy**, that the retry engine reads only `owner` and `retryable`, and that budgets are
projections of the journal. WP-5.1 delivers the typed `TestExecution` with `owner_on_failure` (F3 owners only). To
make an engineering-quality failure a `failure/observed` event — the only way it can reach the owner routing, the
retry policy and the budget projections (WP-4.5) — WP-5.4 needs typed codes for it. Today `FailureCode` has none:
`CONTRACT_UNSATISFIED` is a product-proof code (§10.3), and `UNKNOWN` is reserved for a non-AISEF error flattened with
its original retained (§22).

## Proposed members (the WP-5.1 measurement, reverted before commit)

| code | owner (§15.0) | retryability (§22) | budget |
|---|---|---|---|
| `TESTS_UNRUNNABLE` | ENVIRONMENT | RESOLVED_BY_POLICY (the environment retry policy, rule 1) | ENVIRONMENT |
| `TESTS_INADEQUATE` | DEVELOPER | RESOLVED_BY_POLICY (the developer quality budget as the resolved policy says, §15.3) | DEVELOPER |
| `TESTS_NOT_COLLECTABLE_UNDETERMINED` | INTEGRATION | NOT_RETRYABLE (a retry would measure the same thing) | none |

Measured on the reverted tree: the P1 pinned taxonomy test grew by the same three rows and 368/368 `TAXONOMY` mutants,
6/6 `classify`, 21/21 `flatten` were killed (diagnostic run F2, DIAGNOSTIC_ONLY, not gate evidence).

## Evidence-compatibility impact

* **F1**: affected by growth of a payload enumeration — declared, exactly as V2-003 declared it. No existing member
  changes meaning; no sealed journal holds the new values; a format-2 reader meeting an unknown code refuses rather
  than misreads (`_enum` rejects it).
* **F2 / F3 / F5**: unaffected — no owner is added (the Owner set stays capped), no routing row of the product-proof
  table changes, no probe semantics change.
* **Journal format**: WP-5.4 already carries a required format bump (the `tests/adequacy` event schema, RFC §35). Binding
  the growth to that bump (format 3) makes the compatibility statement exact: a format-2 journal never contains the
  codes, a format-3 reader knows them.

## Options for the owner

1. **Grow `FailureCode` by the three codes at WP-5.4, bound to journal format 3** (recommended): F1 declared affected
   under this exception; the codes enter the taxonomy, the P1 pinned table and the P1/P3/P4 records that snapshot the
   taxonomy in the same WP-5.4 commit that bumps the format.
2. Grow by the three codes now, at WP-5.1, on format 2 (the V2-003 shape): same declaration, one commit earlier, with
   the "older reader refuses" argument standing alone.
3. Do not grow the taxonomy: WP-5.4 keeps engineering-quality outcomes out of `failure/observed` and out of the budget
   projections. This contradicts §22 ("retryability is a property of the typed code, fixed once in the taxonomy") and
   §15.3's developer quality budget, so it is listed for completeness only.

Until the owner decides, WP-5.2 and WP-5.3 (relevance, vacuity) do not need the codes; WP-5.4 does.
