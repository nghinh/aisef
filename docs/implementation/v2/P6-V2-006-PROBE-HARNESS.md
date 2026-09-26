# V2-006 — protocol stream vs process lifecycle in the probe harness (P6-FINDING-001)

**Status.** Applied under "AISEF V2 — OWNER RESOLUTION OF P6-FINDING-001 / ARCHITECTURE EXCEPTION V2-006 / PROBE
HARNESS READY/EOF ORDERING" (2026-09-26). RFC §9.4 (new), F5 row amended; records
`closure-evidence/v2/ARCHITECTURE-EXCEPTION-V2-006.json`, `closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-006.json`;
evidence `closure-evidence/v2/P6-V2-006-PROBE-HARNESS.json` (builder `validation/v2/p6_evidence.py`, `--check`
twin). Tests: `tests/v2/test_v2_006.py` (RACE-1..9, the reader's units), `tests/v2/test_v2_006_repeat.py` (RACE-10).

## 1. The defect

The reference probe (`aisef2/probe/python_callable.py`) decided "before DISPATCHED" from two channels racing in one
queue: the target's protocol lines, read by `_pump` from the output pipe, and the anchor's exit notice, put by
`_exited` when `run.wait()` returned. The anchor itself held the output pipe open (its fd 2 was the pipe the target
inherited), so the pipe never reached end of file while the protocol was being read, and the exit notice was the only
end the reader could see. When the exit notice won the race, an already-written READY was never read, and a target
that had written READY, DISPATCHED and RESULT and exited 0 was recorded as "the harness did not start (exit 0, no
READY)" — a false UNRUNNABLE on one party, a false VERIFIER_DISAGREEMENT between two. Four Linux CI jobs in P6 hit it;
the fourth printed both records.

## 2. The fix — two facts, never collapsed

| fact | channel | who publishes it | used for |
|---|---|---|---|
| the protocol stream reached its end of file | the target's output pipe | the one pump, after every line it read (`STREAM_CLOSED`) | the end of the protocol |
| the process exited | the anchor's report | `run.wait()`, asked only after `STREAM_CLOSED` | how it ended (§9.3 provenance), or the watchdog/window |

* **Truthful end of file.** `range_anchor._release_output()` points the anchor's fd 2 at the null device right after
  the spawn: the target (and its descendants) are the stream's only writers.
* **Pump-completion barrier.** `_pump` puts `("LINE", line)` for every line, then `("STREAM_CLOSED", "")` from the
  same thread; nothing can overtake a line. `_next` returns only complete (newline-terminated) lines carrying the mark
  and the nonce, then `STREAM_CLOSED` for good.
* **Exit after the stream.** Before DISPATCHED, "ended before READY/DISPATCHED" needs the stream closed, the exit
  reported and the line unread; a stream closed while the process runs at the watchdog is a harness timeout. After
  DISPATCHED, a stream closed without RESULT is judged by the exit's provenance (§9.3), or as the window expiring if the
  process still runs at W.
* **No timing window.** `_exited` and the 2 s post-exit drain `_DRAIN_S` are gone. The watchdog and the subject's window
  keep their §9.2 meaning.

## 3. Measured

| | base (b41a01e) | this candidate |
|---|---|---|
| 50 ms pump lag on both parties, real stories | 6/6 not committed | 0/6 |
| 50 ms pump lag on one party | 4/4 VERIFIER_DISAGREEMENT | 0/4 |
| 500 ms pump lag | — | 0/3 |
| race cases (18) | 13 fail | 18 pass |
| F5.protocol_stream_vs_process_lifecycle | FAIL on 5 points | PASS |
| RACE-10: 102 observations, three injected orderings | diverges | 0 divergence, 0 harness failures |

RACE-2, RACE-3, RACE-9 and the probe-level RACE-4 pass on the base only because their exit-first injection consumes
the anchor's report the base's exit-driven reader waited on; the delayed-pump cases, RACE-8 and the reader's units
discriminate.

## 4. Scope, determined mechanically

* Freeze table: only the F5 row changes (row digests at the base vs now). Conformance: one subcheck added
  (`F5.protocol_stream_vs_process_lifecycle`), none changed or removed.
* Probe identity: the digest changes (`c335293e…` → `ac434a42…`); `P2-PROBE-PROTOCOL` and `P2-CALIBRATION` are
  re-derived and calibration is re-established by execution (the V2-003 precedent).
* F4, consequential: `semantic_hash` binds the probe digest — the same contract compiles to a different hash — but no
  stored spec binds the old digest; specs compiled against `probe.python_callable` get new hashes when compiled.
* Mutation: every target of `python_callable.py` (13, now including `_pump` and `_next`) and `range_anchor.py` (4)
  re-measured into the P2 and P4 records. `_release_output` has no mutant under the tool's operators; RACE-8 and the F5
  check hold it.
* Historical: P1–P5 seals, `ARCHITECTURE-EXCEPTION-V2-003.json` and `P4-COMPLETION-CORRECTION-V2-003.json` stay
  byte-identical (checked in the evidence record); no P3–P5 evidence record re-derives differently.

## 5. Decisions the owner should see

* **A descendant that inherited the stream keeps it open.** The end of file is the writers' truth: if the harness exits
  while a child it spawned still holds the output, the protocol is not over — after DISPATCHED that reads as the window
  expiring (the process tree is still running at W), before DISPATCHED as a harness timeout at the watchdog.
* **A protocol line must be terminated.** An unterminated final fragment is never a protocol line (RACE-7), so a
  partial READY is "no READY", deterministically.
* **An out-of-order protocol tag before DISPATCHED** is reported as "the harness broke its protocol: X before Y"
  (previously an opaque "did not start (exit None, …)" after a 5 s wait).

## 6. The anchor's watchdog (P6-FINDING-002, found while re-measuring)

Re-measuring `range_anchor.py::main` — required, since V2-006 changed the module — stopped the mutation runner with
RESIDUAL_OWNERSHIP_UNKNOWN three times: a mutant with no SIGINT handler (an interrupt ended `main`, and the interpreter
then waited forever on the reporter and reaper threads) and a mutant with the end-of-file branch inverted (the anchor
spun on end of file). Both left orphaned anchors whose ownership the runner cannot prove on macOS, which has no
subreaper; the runner correctly refused to signal them, and they were stopped by verified PID (operator notes in the
diagnostics folder). The same mutant of the base anchor leaks the same way (3/3): the committed measurement of `main`
predates the fail-closed ownership proof, and V2-006 is the first change to the module since.

The defect under it is real: the watchdog lived inside `main`, the function it guards. An exception out of `main` after
the spawn — STARTED written to a report pipe nobody reads — made the base anchor exit 120 and leave the target running
with no watchdog.

* **Fix.** The watchdog is the script's entry: `main` reads its control stream until end of file and returns, and
  `try: main() finally: _die()` ends the anchor by `_die` (its group, itself included) however `main` ends, or by
  `EXIT`. The documented behaviour — end of file on stdin kills the anchor's group — is unchanged; no frozen item moves.
* **Test.** `tests/v2/p4/test_process_range.py::Anchor::test_an_anchor_whose_report_nobody_reads_ends_itself_and_its_group`:
  base anchor FAIL (120 ≠ −9), this candidate PASS.
* **Measured after.** Both formerly leaking mutants are killed with no stray; `main` and the other three anchor targets are
  re-measured on this source into `P4-MUTATION.json`.
