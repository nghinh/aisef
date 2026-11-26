# PE8-CORRECTION-STATUS — deadline-integrity fix implemented in isolation; BLOCKED on a frozen-invariant conflict — 2026-11-27

**Owner ruling 2026-11-27 B/C.** The P0 correction is implemented in the isolated worktree/branch `pe8/deadline-integrity`
(off `c65591b3`). It is **complete and proven** against all five required controls, but it **cannot be completed or
integrated** without amending a frozen RFC §9.2 architectural invariant (`NO_CLOCK_IN_PROBE_FACTS`). Per the project norm
(STOP and return the exact conflict rather than weaken a frozen rule), this is surfaced for an owner ruling. **Nothing is
integrated; no invariant is amended; no capability identity is bumped yet.**

## 1. The fix (implemented)

The deadline is decided on the **controller's own monotonic clock**, from its authenticated `DISPATCHED` stamp to its
authenticated `COMPLETED` stamp — never from the times the parent happened to observe either marker.

- Controller (`HARNESS` template, `aisef2/probe/process_effect.py`): `import time`; `emit("DISPATCHED", repr(time.monotonic()))`
  at true dispatch; `emit("COMPLETED", repr(time.monotonic()))` immediately before `emit("RESULT", …)`. The stamps ride
  authenticated marker bodies (HMAC under the evaluation key), **not** the RESULT facts — so the observation `detail`
  (frozen evidence content) is byte-unchanged; only the probe bytes change.
- Parent (`_watch` + new `_overran`/`_stamp`): the `_await` on `RESULT` is only a liveness bound; a RESULT — even one
  observed late — is judged by `_overran`, which compares `COMPLETED − DISPATCHED` to `within_s`, fail-closed on missing,
  malformed or out-of-order stamps. The parent's own observation times are never consulted. A single window spans the
  whole scenario (no per-step reset). The subject (no key, stdout to null) cannot forge the stamps: the trust boundary
  holds.

## 2. Controls (owner ruling B) — all satisfied

Deterministic traces (`scratchpad/pe8_diag.py` before, `scratchpad/pe8_diag_after.py` after; one monotonic clock):

1. **Over-window 1.2s / within_s=1.0, DISPATCHED observed late → SUBJECT_DEADLINE/REFUTED for every δ** (0.00, 0.25, 0.50,
   1.00). Before the fix: δ≥0.25 gave OBSERVED/SATISFIED (the defect). After: SUBJECT_DEADLINE regardless of δ.
2. **On-time 0.8s whose RESULT is observed late (δ=0.5) → OBSERVED/SATISFIED.** A late-observed RESULT is not charged a
   deadline.
3. **Fail-closed:** missing/malformed (`abc`, `inf`)/out-of-order/empty DISPATCHED/missing COMPLETED → SUBJECT_DEADLINE,
   never a false PASS. Replayed or unauthenticated timing never enters `seen` (`ci._protocol` filters by MAC + nonce).
4. **Single window, no per-step reset:** elapsed is DISPATCHED→COMPLETED (the whole scenario). Two 0.6s steps (each
   < 1.0) total 1.2s → SUBJECT_DEADLINE.
5. **Existing PE_8 assertions intact:** `tests/v2/test_probe_process_effect.py::...test_PE_8...` passes unchanged; the
   whole probe suite passes **except** the one invariant below.

## 3. BLOCKER — `NO_CLOCK_IN_PROBE_FACTS` (RFC §9.2), a frozen invariant

`validation/v2/probe_static_checks.py` enforces three things under this rule: (1) **no clock in the child controller
scripts** (`HARNESS`/`SUBPROCESS`); (2) no clock in the RESULT/fact constructors; (3) no clock in the verdict functions.
Its stated principle: *"the clock may end an observation window; it never enters an observation."*

The fix keeps the clock **out of the facts and the verdict** (parts 2 and 3 preserved — the stamps are marker bodies, and
`verdict_of` is untouched). But it necessarily puts a clock **in the controller** (part 1), because the owner's directive
— elapsed measured from the controller's authenticated DISPATCHED to COMPLETED on a comparable monotonic timebase —
cannot be met any other way: the parent's own observation times are exactly what the directive forbids using, and there
is no clock-free way for the parent to learn the controller's true dispatch/completion instants.

So the fix is consistent with the invariant's **principle** (the clock only ends the window; it never enters an
observation) but violates its current **enforcement** (part 1's blanket ban on a controller clock, which assumed only the
parent ever ends the window).

**Proposed minimal amendment (for owner ruling, NOT applied):** refine part 1 to permit the controller's authenticated
window-ending stamps (the `DISPATCHED`/`COMPLETED` marker bodies used solely by `_overran` to end the window),
while keeping parts 2 and 3 intact (a clock in the facts or in a verdict function stays forbidden). This preserves the
principle verbatim and moves only the enforcement to match it. It touches `probe_static_checks.py`, the rule's known-bad
fixture, the `no_clock_in_probe_facts` calibration, and the RFC §9.2 text — a frozen-invariant change requiring owner
authority.

## 4. Capability / digest impact (owner ruling C; CLASSIFICATION, not applied)

The probe has three identities (ARCHITECTURE-EXCEPTION-V2-007):

- **EXECUTION_DIGEST** (`_probe_digest()`, the probe bytes): **changes** (the HARNESS template and `_watch` changed). Per
  the architecture note, a byte change needs the probe's **calibrations demonstrated again** before anything admits — new
  v2.3 calibration rows for `probe.process_effect`, not a reuse of the obsolete identity.
- **CAPABILITY_VERSION**: must bump **1 → 2** by hand — the change alters a **verdict rule** (a late-observed overrun is
  now correctly REFUTED). This is the hand-bump the note reserves for a change to what a class observes.
- **DIGEST** (`sha256([PROBE_ID, CAPABILITY_VERSION, CLASSES])`): **changes** with CAPABILITY_VERSION; CLASSES unchanged.
- **Consumers:** specs/approvals/plans binding the old DIGEST become invalid for the new capability (correct). Bundles
  (`bundle.py` ProbeRef) and format3/format4 records bind `probe_digest`; a v2.2.0 bundle holds the old digest.
  **CR-8:** retain historical 2.2.0 bundle verification through the approved versioned mechanism (the old capability
  preserved for replay, the new one for v2.3+); do not rewrite frozen evidence.
- **Mutation:** editing `process_effect.py` stales any mutation target there; the source must be committed cleanly before
  any targeted F5 re-measurement (no mass campaign).

## 4a. Independent adversarial review (owner ruling C) — patch

An independent adversarial review of the patch confirmed the three security goals: the **trust boundary holds** (the
subject holds no key and its stdout is captured, so it cannot forge, replay-shift or falsely-advance a stamp — only
`ci._protocol`-authenticated marker bodies reach `_overran`); **no false PASS exists** (every genuine-overrun / missing /
malformed (`inf`/`nan`) / out-of-order / boundary input yields SUBJECT_DEADLINE); and **the parent's observation times
never influence the verdict** (used only as a finite liveness bound). The hang and harness-failure paths are preserved.

It raised one CONCERN, now **fixed**: `_overran` originally preempted `_concluded` for *every* over-window RESULT,
demoting a slow NON_CONTROLLER_SIGNAL (a §9.3 / INV-MUTATION-AUTHORITY signal-ledger integrity event) or HARNESS_FAILED
(infra fault) to SUBJECT_DEADLINE/REFUTED. `_watch` now applies the deadline **only when `_concluded` yields an OBSERVED
kind**, so a signal / absent / harness event outranks a measured overrun and is never masked (verified: over-window +
`subject_signal` → NON_CONTROLLER_SIGNAL; + `harness_failure` → HARNESS_FAILED; + normal SATISFIED → SUBJECT_DEADLINE).
The inclusive boundary (`elapsed == within_s` is within) is now documented in `_overran`.

## 5. Why this is a STOP

Completing the fix requires (a) amending a frozen RFC §9.2 invariant and (b) bumping the probe capability identity with a
CR-8 version-forward of 2.2.0 bundle verification and a fresh v2.3 calibration. Both are owner-authority changes. The fix
is implemented and proven in isolation; it is **not** integrated, the invariant is **not** amended, and the identity is
**not** bumped, pending the owner's ruling on §3 and §4.
