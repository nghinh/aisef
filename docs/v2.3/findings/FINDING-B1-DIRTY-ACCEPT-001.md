# FINDING-B1-DIRTY-ACCEPT-001 — dirty round evidence accepted as current B1 qualification (TRUST-CRITICAL)

**Classification: trust-critical defect** (owner ruling 2026-11-25 §1). Found by the owner's review of the E5
campaign manifest; reproduced, traced, fixed and adversarially reviewed before any W1b closure claim.

## The defect

At `6a52cef9`, the round-v2.3 B1 acceptance (`validation/v2/b1_bindings_check.py::_v23_accepts`, Q0-1 option Q-a)
accepted a moved B1 source whenever the newest COMMITTED round entry matched the live digest and
`mutation.target_problems(entry)` was empty. `target_problems` (runner-2 path `_problems_v2`) **never reads
`entry["identity"]`**: the engine's own rule — *"`dirty: true` can never become MEASURED"*
(`mutation.py::_v23_identity` docstring) — was enforced only at write time (the runner refuses to START from a dirty
tree), never at read time. The E5 campaign produced 33/37 entries with `identity.dirty = true` (the engine's own
append-after-every-target bookkeeping inside one invocation); **22 of the 25 B1 manifest targets were therefore
accepted as currently qualified on inadmissible evidence** (red-before capture: 22 named targets, evidence file
`red-before-live.txt` in the private finding folder, 2026-11-25T07:41:36Z at `6a52cef9`).

## Reproduction (independent)

An independently written negative test, authored from the ruling text alone in a pristine worktree at `6a52cef9`
with no fix present: `tests/v23/test_v23_b1_admissibility.py` — a committed, all-KILLED, confirmed-kill-bracket,
live-digest round entry differing ONLY in `identity.dirty`. On the unfixed tree the dirty case was **accepted**
(test red: `AssertionError: True is not false`); the clean control was accepted (isolating `dirty` as the deciding
factor and guarding against an over-broad fix). Adopted into the tree with the provenance maps filled (the shared
rule refuses an empty `closure`/`generator`/`env` as unproven; both variants carry the same full provenance).

## The complete acceptance path (traced)

```
b1_bindings_check.problems()  --(round v2.3, source moved)-->  _v23_accepts(t, e)
    = committed-prefix ok (v23_newest; I7 enforced)  AND  entry.source_sha256 == live LF digest
      AND  target_problems(entry) == []            <-- never reads identity: dirty/platform/env/generator/T0 unchecked
mutation.check()  --> target_problems(V23_NEW_TARGETS entries)   <-- same hole
                  --> v23_substituted(record, v23_newest map)    <-- substituted dirty entries into every historical
                                                                     record's validation, turning its reds green
```

Consumers of round entries at `6a52cef9` (the full set, by grep): `_v23_accepts`, `mutation.check()` (two uses),
`mutation --run-affected` (supersedes provenance only — correct to keep binding regardless of admissibility).
**No other path reads the round record**: the F5 engine (`validation/v23/impact.py`) does not read round entries;
`validation/v2/currency_dag.py` nodes, `validation/v23/q0_round.py` (its own calibration record) and the release
gates (`release_qualify.py`, tag workflows) do not read it. The Q0 `b1_bindings` checker reaches the entry only
through `_v23_accepts` (fixed below).

## The fix: ONE shared admissibility rule

`mutation.v23_admissible(entry, root) -> list[str]` — the single rule every consumer must pass before treating a
round entry as MEASURED or currently qualified. Fail closed on: non-runner-2; everything `_problems_v2` enforces
(source digest, enumeration, closed classes, confirmed kills, audited survivors, execution order); **a malformed
entry (any raise inside the legacy rules) refused as a problem, never a crash**; missing `identity` or any of
`measured_on/slice/closure/kill_files/generator/enum_modules/platform/env`; missing `env.tree_sha256` /
`env.runner_sha256`; **any identity digest map (`closure`, `kill_files`, `enum_modules`) that no longer matches the
live tree (stale evidence)**; missing or not-all-PASS `t0`; and **`identity.dirty = true`**. Wired into both acceptance
consumers: `_v23_accepts` uses it in place of `target_problems`, and `check()` uses it for `V23_NEW_TARGETS` and
filters the read-time substitution map to admissible entries only (an inadmissible entry leaves the historical
entry in force, so its red stays visible until a clean re-measure). Historical records, the 33 dirty entries and
their identities are untouched (append-only; no rebinding).

## Green-after (measured on the fixed tree)

* The independent test: 2/2 green (dirty refused, clean control accepted).
* Live B1 under `in_round("v2.3")`: the 22 dirty targets are red again (`moved since the manifest froze`); the
  clean entries stay accepted (OCR_CHECKS, calibrations, ocr_refusal + the 6 clean `destructive_authority` α-batch
  targets) — `green-after-live.txt`. (`_attempt`'s clean entry was accepted at that capture and later became
  inadmissible-stale when §5 strengthened its kill file — see E5-SURVIVOR-COVERAGE-DECISIONS.md; final admissible
  set: 9.)
* `mutation --check`: truthfully RED — 33 lines (1 dirty-named `_Stages.advance` + 32 resurfaced historical
  "re-run it" reds) = the owner-mandated NOT-QUALIFIED state for the dirty-measured targets (gated battery only;
  the ungated suite does not run this check).
* `tests/v23/test_v23_mutation_round.py` upgraded: the Q-a fixtures are now FULLY admissible real-rule entries (no
  mocking of the rule), with fail-closed cases for dirty, no-identity, no-T0, unaudited survivor, malformed entry.

## Status of the affected qualification claims

The E5 manifest's statement "all 25 manifest target rows accepted (Q-a)" is **retracted** (correction appended to
the manifest): 22 of those acceptances rested on dirty evidence and are **NOT QUALIFIED** until fresh, clean,
admissible evidence supersedes them (owner ruling §3/§6/§7). The three clean B1 targets (OCR_CHECKS, calibrations,
ocr_refusal) remain currently qualified on admissible evidence. No dirty record was edited or re-run here; the
clean re-measurement belongs to the separately-authorized final source-frozen RC campaign (one invocation per
target, committing the record in between).

## Independent adversarial review (20 agents, 3 lenses, every finding re-verified by a refuter)

Confirmed and fixed in the same change, each with a live probe red-before/green-after:
* **Fail-open: an identity that OMITS the `dirty` key was admissible** (`ident.get("dirty")` is falsy on absence).
  Now: "identity does not state dirty — cleanliness unproven, inadmissible"; test case added.
* **Crash-not-problem edges**: a non-dict entry, a truthy non-dict `identity.env`, a non-list `t0` each crashed the
  gate instead of refusing. Now typed-checked, fail closed as problems.
* **I7 silence regression**: filtering the substitution map dropped the uncommitted-entry (I7) stub, so `check()`
  lost its pre-fix red when the historical entry was still current. Now `check()` reports every I7 stub verbatim,
  and `v23_admissible` returns an error stub's own cause verbatim (the diagnostic is not downgraded).
* **Remediation deadlock**: `--run-affected` could never re-measure a `V23_NEW_TARGETS` member whose only entry is
  inadmissible (`new` required "no entry at all"; the engine never classifies these targets). Now a V23_NEW_TARGET
  is re-measurable while unmeasured OR its newest entry is inadmissible — the ruling's "re-measure cleanly" has a
  sanctioned path again.
* **Pre-existing**: `_v23_accepts` read the live source unguarded (a missing/non-UTF-8 source crashed the B1 gate);
  now refuses (False) fail-closed. `v23_admissible_map` (no callers) deleted.
Verified clean by the review: **no other reader** of the round record can treat the rejected evidence as MEASURED
or qualified (B1, Q0 via calibration, currency DAG, release gates, the F5 engine — surveyed independently); the
intended consequences on the real tree (b1: 22 moved-source reds return; `check()`: 0 → 35 truthful problems, gated
battery only) were re-measured and match the design.
