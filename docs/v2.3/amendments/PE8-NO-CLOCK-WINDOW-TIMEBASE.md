# PE8-NO-CLOCK-WINDOW-TIMEBASE — scoped amendment of NO_CLOCK_IN_PROBE_FACTS — 2026-11-27

**Owner ruling 2026-11-27 B/C (PE8-DEADLINE-INTEGRITY). Cites RFC §9.2** (`docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md`,
"Harness timeout vs subject observation deadline", amended V2-002): a subject observation deadline is reached when the
harness "dispatched the subject and observed it, but the subject did not complete or emit the expected observation
within the bounded observation window the `ProductProofSpec` declares." The deadline must be measured on a timebase the
controller owns, from its authenticated `DISPATCHED` to its authenticated `COMPLETED`, never from the times the parent
happened to observe either marker.

## 1. What this amendment does

The Q0 static rule `NO_CLOCK_IN_PROBE_FACTS` (`validation/v2/probe_static_checks.py`) enforced the principle *"the clock
may end an observation window; it never enters an observation"* with three bans: (1) **no clock in any child script**,
(2) no clock inside a RESULT/fact constructor (`Observation`, `Executed`, `Unrunnable`, `InvalidSpec`, `ProbeRecord`),
(3) no clock inside a verdict function (`verdict_of`, `observation_class`, `spec_class`).

Ban (1) was a **blanket** controller-clock ban that assumed only the parent ever ends the window. The PE8
deadline-integrity fix (`aisef2/probe/process_effect.py`) measures the window on the controller's **own** monotonic
clock — `emit("DISPATCHED", repr(time.monotonic()))` at true dispatch and `emit("COMPLETED", repr(time.monotonic()))`
immediately before `emit("RESULT", …)` — so the elapsed is `COMPLETED − DISPATCHED`, judged against `within_s`, and a
RESULT the parent observed late is no longer charged a deadline merely for being seen late. That requires one clock read
in the controller, which ban (1) forbade.

This amendment **narrows ban (1) mechanically**, keeping bans (2) and (3) verbatim. It does **not** disable or remove
the invariant.

## 2. The mechanical exception (`probe_static_checks.py`)

A clock read in a child script is permitted **only** when all of the following hold (constants `WINDOW_CONTROLLER`,
`WINDOW_MARKERS`, `WINDOW_CLOCK`; helper `_window_stamps`):

- **only the `HARNESS` controller.** The child script is named exactly `HARNESS`. Every other child script — the
  `SUBPROCESS` boot and the subject's agent (`cli_invocation.AGENT`) — stays fully clock-free (import and read both
  banned).
- **only `time.monotonic()`.** No other clock (`time.time`, `perf_counter`, `process_time`, `datetime.now`, …) is
  exempt, even in the controller.
- **only as a window-stamp emit body.** The exempt node is the `time.monotonic` attribute that is the callee of a
  `time.monotonic()` call inside a positional body argument of an `emit(<marker>, …)` call whose first argument is a
  string literal in `{"DISPATCHED", "COMPLETED"}` (`_window_stamps` collects exactly those attribute nodes). **Every
  other `time.<attr>` access in the controller is flagged** — a different clock (`time.time`, `time.perf_counter`),
  `time.monotonic` under any other marker or outside an emit, and a callable alias (`m = time.time; m()`).
- **import of `time` only, as a plain `import time`.** The controller may bind the clock name **only** through a bare
  `import time` (no `asname`). `import time as x`, `from time import …` (so no clock function is ever bound as a bare
  name), and any other clock module (`datetime`) are all flagged. Combined with the attribute rule above, this means no
  clock value can be reached except `time.monotonic()` in a sanctioned stamp — aliasing and from-importing cannot evade
  the rule (regression closed before batch-1 integration).

The gates are conjunctive: a script named `HARNESS` that smuggles a clock outside the window-stamp pattern is still
flagged, and any script not named `HARNESS` keeps the full blanket ban (no clock import, no clock read) and gains nothing.

## 3. What stays unchanged (the invariant's principle, preserved)

- **The clock never enters the facts.** Ban (2) is untouched: a clock read inside any RESULT/fact constructor is still
  flagged. The stamps ride **authenticated marker bodies**, not the RESULT payload, so the observation `detail`
  (frozen evidence content) is byte-unchanged.
- **The clock never enters the verdict.** Ban (3) is untouched: a clock read in `verdict_of` / `observation_class` /
  `spec_class` is still flagged. `verdict_of` is not modified by the fix.
- **The subject/agent process stays clock-free.** The exception is scoped to the `HARNESS` controller; the subject
  cannot read the key (it holds none) and its stdout is captured, so it cannot forge, replay-shift or advance a stamp.
  The trust boundary is unchanged.
- **Fail-closed.** Missing, malformed, out-of-order or unauthenticated timing evidence yields `SUBJECT_DEADLINE`, never
  a false `OBSERVED`/`SATISFIED` (`process_effect._overran`/`_stamp`).
- **F4 precedence.** The deadline governs an ordinary `OBSERVED` RESULT only: a `NON_CONTROLLER_SIGNAL`
  (INV-MUTATION-AUTHORITY, §9.3), `SUBJECT_ABSENT` or `HARNESS_FAILED` outranks a measured overrun and is never masked.

## 4. Controls (owner ruling B)

- **Positive** (`tests/v2/test_probe_process_effect.py`): the real `process_effect.py` passes all six probe rules with
  its catalog facts (`test_PE_Q0…`); the sanctioned `DISPATCHED`/`COMPLETED` monotonic stamps pass clean
  (`test_PE_NO_CLOCK_window_timebase_amendment_is_scoped_to_the_controller`, positive case).
- **Negative** (same test, one subTest each, each still flagged): a clock under a non-window marker; a non-monotonic
  clock in a window marker; a monotonic read outside any emit; the controller importing `datetime`; a clock in the
  subject's agent; a clock in the subprocess boot; a clock in a RESULT/fact constructor; a clock in a verdict function.
- **Calibrated checker** (`validation/v2/checker_calibration.py::_probe_rule("no_clock_in_probe_facts", …)`): clean on
  this tree, and its committed known-bad fixture (`tests/v2/fixtures/known_bad/no_clock_in_probe_facts.json`) is
  **unchanged — frozen to its v2.2.0 bytes by the Q0P-1 contract** (a clock read inside an `Observation(...)` fact
  constructor, still banned by the unamended parts 2/3), rejected for the expected reason (`…bad.py:6`). The
  controller-scoping guarantee — a clock under a non-`DISPATCHED`/`COMPLETED` marker is still flagged, so the exception
  did not become a blanket controller pass — is proven by the negative subTests of
  `test_PE_NO_CLOCK_window_timebase_amendment_is_scoped_to_the_controller`, not by the frozen fixture.

## 5. Boundaries

Scoped to the one static rule — its enforcement logic and tests; the frozen v2.2 known-bad fixture is unchanged. No change to the RFC §9.2 normative text (it already defines the
subject observation deadline; this refines only the Q0 enforcement that implements its "clock never enters an
observation" principle). No frozen evidence altered. No capability-identity logic lives here (see the companion
`CAPABILITY_VERSION` 1→2 bump and `RELEASES["2.2.0"]` CR-8 entry). No production tag, master merge or publication.
