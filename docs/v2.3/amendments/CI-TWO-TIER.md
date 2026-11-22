# CI-TWO-TIER: the owner-approved two-tier F5 CI policy

**Status: APPLIED (owner ruling 2026-11-22 §4). Supersedes W1-DESIGN.md §11 exit gate 2's "the `mutation-incr` `gate`
job MUST fail for exactly those 327 targets" — for DEVELOPMENT pushes and PRs only. W1-DESIGN.md is frozen and is not
edited; this amendment records the supersession.**

## The ruling, verbatim (§4)

> Development CI must: Execute the F5 engine and required negative controls. Report all INVALIDATED and UNRESOLVED
> states. Never label incomplete evidence QUALIFIED. Fail on genuine checker malfunction, false-current reuse or
> negative-control regression. Frozen RC and production qualification must additionally fail whenever any mandatory
> target lacks valid MEASURED or VERIFIED_REUSE evidence. Implement and test these two distinct policies without
> allowlists masking qualification failures.

## What each tier runs

Both tiers are `validation/v23/ci_gate.py`, a thin wrapper that imports `validation/v23/impact.py`
(sha256 `79609ac7…`, unedited — the engine stays the only classification authority) and runs ONE classification,
plus four pinned in-process negative controls from `tests/v23/test_v23_impact.py` (each builds its own toy
repository; ~11 s): an inadmissible observation refused (R0), an incomplete observation refused (R1), a Δ ∩ S(F)
literal-directory hit INVALIDATED (R2, static tier), and the engine refusing a dirty tree. A control that fails, is
skipped, or cannot even be loaded fails the gate closed: a gate that cannot demonstrate its checker still refuses bad
evidence proves nothing about the evidence it accepts.

* **`--tier develop`** — `mutation-incr.yml` job `gate`, on every `release/**` push and PR. Prints the full truthful
  state table (the counts and per-rule breakdown exactly as `impact.py --classify` prints them) and the mandatory
  final line `EVIDENCE: INCOMPLETE (NOT QUALIFIED)` while any target lacks MEASURED or VERIFIED_REUSE evidence (the
  only other final line is `EVIDENCE: COMPLETE (RC-TIER CHECK STILL REQUIRED)`; no passing line ever says QUALIFIED).
  Exits 0 UNLESS, each named on stdout: **(a) checker malfunction** — the engine raised (an `engine`-component row or
  an exception), the table is malformed, the per-state counts do not match the rows, or the table does not cover the
  RECORDS × PHASE_TARGETS registry; **(b) false-current reuse** — a VERIFIED_REUSE row with no acceptance basis, a
  non-reuse row carrying one (F5-DISPOSITION-3: "No non-reuse row carries an acceptance basis"), or a basis that is
  not one the engine itself pins to the run's resolved basis commit (`v2.2.0-accepted@…` only on the pinned v2.2.0
  sha, `calibration@…`, the sha-pinned Option C ruling forms, `observation:…` only with `evidence.authority` "none");
  **(c) negative-control regression**.
* **`--tier rc`** — job `rc`, ONLY on release tags (`v[0-9]*.[0-9]*.[0-9]*`) or a manual dispatch with `tier=rc`.
  Everything develop does, PLUS exit non-zero naming the count whenever ANY target lacks valid MEASURED or
  VERIFIED_REUSE evidence. On today's tree that is truthfully 994 of 994 (667 INVALIDATED R2 + 327 UNRESOLVED I6,
  F5-DISPOSITION-3): the strict W1-DESIGN §11 gate-2 verdict lives here, unchanged.

## Why develop exits 0 with a truthful INCOMPLETE state

W1-DESIGN §11 gate 2 made the push gate fail on the 327 UNRESOLVED legacy targets. With 667 further R2 invalidations
(run 44974444809) every development push was permanently red, so the gate could no longer distinguish a regression
from the known backlog — the ruling's §4 separates the two: development CI reports the incomplete state truthfully
and red means something NEW broke (the checker, a reuse claim, or a control); the RC tier alone turns incompleteness
into a failure. Neither tier takes an exception list, a skip parameter, or any other mask — the v2.1.0 release-tag
exception mechanism does not apply here, and `tests/v23/test_v23_release_governance.py::IncrementalQualificationJob`
pins the string's absence from both the workflow and the gate.

## What does NOT change

F5 and VERIFIED_REUSE authority rules are untouched: the engine is still not a release authority, the F5 recorder is
still approved for development only and is not a VERIFIED_REUSE authority (owner ruling 2026-11-21), nothing here is
wired into `validation/v2/mutation.py check()` or any publish path, and the develop tier's exit 0 confers no
qualification — its own final line says so. Pins: `tests/v23/test_v23_ci_gate.py` (both tiers' exit behaviour) and
`tests/v23/test_v23_release_governance.py::IncrementalQualificationJob` (the workflow contract).
