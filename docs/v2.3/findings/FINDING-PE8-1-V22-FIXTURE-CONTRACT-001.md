# FINDING-PE8-1-V22-FIXTURE-CONTRACT-001 — PE8-1 overwrote a frozen v2.2 Q0 known-bad fixture

Status: **RESOLVED** — owner chose remediation 1 (restore the frozen fixture), applied 2026-11-27 (integration HOLD maintained; not pushed)
Discovered: 2026-11-27, during PE8-2 / calibration round-version §4 verification (Lead Integrator)
Branch: `integ/pe8-batch1` (to land on `release/v2.3-big`); offending commit **869aa80f**

## What

The PE8-1 scoped NO_CLOCK amendment (commit `869aa80f`) **rewrote in place** the frozen
v2.2 Q0 known-bad fixture `tests/v2/fixtures/known_bad/no_clock_in_probe_facts.json`:

- v2.2.0 case (frozen): a **probe** reading `time.monotonic()` into an `Observation(...)` `detail`
  — `expect: NO_CLOCK_IN_PROBE_FACTS aisef2/probe/bad.py:6`.
- 869aa80f case: a **HARNESS controller** reading `time.monotonic()` under a `READY` marker
  — `expect: …bad.py:1`, plus an explanatory `note`.

`validation/v23/q0_round.py::contract_problems` pins every v2.2 Q0 checker's known-bad fixture
to its **v2.2.0 bytes** (LF-normalised). The rewrite trips it:

```
v2.2 Q0 checker no_clock_in_probe_facts: its known-bad fixture
tests/v2/fixtures/known_bad/no_clock_in_probe_facts.json is not its v2.2.0 bytes
```

`tests/v23/test_v23_q0_round.py::Q0Contract::test_this_tree_keeps_every_v22_contract` FAILS on the
integrated tree. The contract is explicit and allowlist-free (`q0_round.py:158`):
**"No exception list: changing a contract needs a new q0_round.py, a new patch and a new ruling."**

This violates the standing constraint **"preserve historical v2.2 replay."** No new q0_round.py,
patch, or ruling accompanied the fixture change — the owner's PE8-1 approval was for the *checker
rule* amendment (mechanically constrained), not for rewriting the frozen v2.2 fixture.

Scope check: among `tests/v2/fixtures/known_bad/`, only this fixture was **modified**. `f5_gate.json`,
`f5_recorder.json`, `released_evidence.json` are *new* v2.3 (seq-14/PIN-57) checker fixtures, not
v2.2 contracts, and are correctly ignored by `contract_problems`.

## Why the rewrite was unnecessary (verified)

The amendment narrows **only** part 1 of NO_CLOCK_IN_PROBE_FACTS (the HARNESS controller window
stamp). A clock read in a probe's fact constructor (the v2.2.0 fixture's `Observation(...detail=…)`)
is banned by parts 2/3, which the amendment leaves **unchanged**. So the v2.2.0 fixture remains a
valid known-bad case under the amended rule. Restoring the v2.2.0 bytes was measured to keep
everything green:

| check | with v2.2.0 fixture restored |
|---|---|
| `no_clock_in_probe_facts` calibration | `calibrated: True`, `rejects_for_the_expected_reason: True`, observed `…bad.py:6: a clock read inside Observation(...)` |
| `q0_round.contract_problems` | `[]` |
| `probe_static_checks --check` | PASS (6 rules) |
| `tests/v23/test_v23_q0_round.py` | 26 passed, 10 skipped, 17 subtests |

No coverage is lost: the controller-scoping guarantee (a clock under a non-DISPATCHED/COMPLETED
marker is still flagged) is demonstrated independently by
`tests/v2/test_probe_process_effect.py::test_PE_NO_CLOCK_window_timebase_amendment_is_scoped_to_the_controller`
(PASS), and the four aliased/from-import evasions by the negative cases a378fe76 added there.

## Remediation options (owner's call — the contract names exactly these two)

1. **Restore the frozen fixture (recommended).** `git checkout v2.2.0 -- <fixture>`; update the one
   doc paragraph (`docs/v2.3/amendments/PE8-NO-CLOCK-WINDOW-TIMEBASE.md:74–77`) to state the v2.2
   known-bad fixture is unchanged and the controller-`READY` scoping is proven by the test above.
   Minimal, reversible, preserves the amendment's rule change and all coverage. Verified green.
2. **Legitimately change the v2.2 contract** via "a new q0_round.py, a new patch and a new ruling"
   (`q0_round.py:158`) — heavier; only if there is a reason the frozen v2.2 fixture must change.

The PE8-1 **rule tightening** in `validation/v2/probe_static_checks.py` (a378fe76/869aa80f) is sound
and is **not** in question — only the frozen-fixture overwrite.
