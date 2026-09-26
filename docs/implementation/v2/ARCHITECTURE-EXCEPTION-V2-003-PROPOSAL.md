# ARCHITECTURE-EXCEPTION-V2-003 — PROPOSED, NOT APPLIED

**Status:** proposed by the P4 implementation; awaiting an owner decision. Nothing in P1, P2 or P3 was changed.

**Frozen item affected:** F5 — the probe protocol's observation-harness / subject split (and, through the probe digest,
F4: every `python_callable` spec's `semantic_hash`).

## The contradiction

The P4 owner decision requires, for WP-4.6 (which owns `P2-RESIDUAL-SIGNAL-SOURCE`):

* **INTERRUPT-SIG-2** — a subject crash or signal exit MUST NOT silently become ENVIRONMENT solely because the process
  exited by signal;
* **INTERRUPT-SIG-3** — when provenance is genuinely unknowable, use the OUTCOME_UNKNOWN / interruption path rather
  than invent PRODUCT, DEVELOPER or ENVIRONMENT certainty.

and, in the same decision, forbids P4 to change F5 probe semantics or F2/F5 routing ("STOP and report an architecture
exception").

The P2 probe (`aisef2/probe/python_callable.py`, sealed with P2) classifies a harness process that dies by a signal
after `DISPATCHED` as `HARNESS_FAILED` -> `UNRUNNABLE` -> `PROBE_UNRUNNABLE`, owner ENVIRONMENT, retryable. Its own
docstring records why: "a process killed by a signal cannot be told apart from the environment killing it". P2's test
`test_a_kill_by_signal_after_dispatch_cannot_be_told_from_the_environment` pins that behaviour.

## Reproducer (measured on the P3-sealed tree, 2026-09-22)

The real P2 probe, run on two subjects that end their own process by a signal after the harness said `DISPATCHED`:

| subject | probe result | routed (CANDIDATE, INTRODUCE) |
|---|---|---|
| `os.abort()` (SIGABRT) | `UNRUNNABLE` — "the harness process was killed by signal 6 mid-observation" | `PROBE_UNRUNNABLE`, ENVIRONMENT, retryable |
| `os.kill(os.getpid(), SIGTERM)` | `UNRUNNABLE` — "... killed by signal 15 mid-observation" | `PROBE_UNRUNNABLE`, ENVIRONMENT, retryable |

The subject's own crash is charged to the environment budget, solely because it exited by a signal — the case
INTERRUPT-SIG-2 names.

## Why P4 cannot conform without it

The classification happens inside the P2 probe, which returns a frozen `ProbeResult`; routing it is F2. P4 could only
reach the required behaviour by overriding a P2 probe result (an F2 routing change) or by editing the probe (an F5
change, which also changes its digest). Both are what the decision forbids P4 to do alone.

## What P4 already provides

For every process P4 owns (tool operations in their own process ranges, `aisef2/runtime/tool.py`), INTERRUPT-SIG-1..3
hold: the range's signal ledger gives provenance (`CONTROLLER` or `UNKNOWN`), a signal exit is recorded as
`SIGNALLED` with that provenance and never as an owner, and an interruption closes an operation `OUTCOME_UNKNOWN`
(dispatched) or `NOT_STARTED` (not yet dispatched). The mechanism the probe would need exists; the probe does not use
it.

## Options for the owner

1. **Provenance-split (recommended).** The probe harness runs inside a P4 process range. After `DISPATCHED`, a signal
   exit whose signal the controller's ledger holds is an interruption, not a measurement: no `ProbeResult` is recorded
   and the story's interruption path writes `OUTCOME_UNKNOWN`. A signal exit the controller did not send is
   `EXECUTED` with an `INDETERMINATE` verdict and a new `IndeterminateReason` (for example `SUBJECT_SIGNALLED`), whose
   owner route the owner fixes in the F2 table (never ENVIRONMENT by default). Before `DISPATCHED`, a signal death stays
   a harness failure (`UNRUNNABLE`), as V2-002 froze.
2. **All post-dispatch signal exits are the subject's** (`EXECUTED` / `REFUTED`, like a non-signal exit). Simple, but
   it invents DEVELOPER certainty for a signal the environment may have sent — what INTERRUPT-SIG-3 forbids.
3. **Keep P2 as it is** and record the probe path as an accepted residual of INTERRUPT-SIG-2.

## Evidence-compatibility impact (options 1 and 2)

`python_callable.py` is part of the probe digest, so every `python_callable` `ProductProofSpec` gets a new
`semantic_hash` (§35: evidence under the old digest stays valid for the old id and is not reused). The
`ProbeCapabilityCalibration` for the new digest must be re-established; P2's mutation targets in `python_callable.py`
are re-run; option 1 also amends F2 (a routing row) and F5 (the harness/subject rule for post-dispatch signals). The P2
seal stays a record of what P2 delivered.
