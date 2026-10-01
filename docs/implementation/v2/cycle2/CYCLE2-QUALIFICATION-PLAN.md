# CYCLE-2 QUALIFICATION PLAN

**Status.** Planning artefact (owner's "CLOSE CYCLE-1 / PREPARE CYCLE-2 ARCHITECTURE ONLY", 2026-09-28). Q0–Q5 are not
weakened; each rung says how a new probe kind enters it, which Cycle-1 harness is reused unchanged, and where an
extension is needed. Every Cycle-2 semantic candidate restarts the ladder from Q0 (the rule Cycle 1 followed for every
new candidate); Cycle-1 records stay as they are, cited, never regenerated.

## 0. What a Cycle-2 candidate is

A Cycle-2 semantic candidate is a commit whose `aisef2` tree differs from `4d6081…` only by the probe kinds of the
taxonomy proposal (and their registry entries). The control plane, the journal, the projections, the admission engines,
the orchestration path and the invariants are unchanged; if any of them must change, that is a separate owner decision
with its own package, not a side effect of a probe. The Cycle-1 baseline (candidate `7114177…`, tree `4d6081…`) is
cited as the parent of the first Cycle-2 candidate in the Cycle-2 freeze manifest.

## 1. Q0 — static integrity

Reused unchanged: schemas, provenance, enum catalogs, ownership graph, no-prose-control walker, `time`-not-read check,
checker calibration, the `StaticPlanAdmissionEngine` rules, `old_path_audit`, `destructive_authority`.

Extensions (each with a known-bad calibration fixture, as every Q0 checker must have):

| checker | what it proves | known-bad fixture |
|---|---|---|
| probe registry closure | every `SubjectKind` with a probe has exactly one `ProbeMetadata` entry per digest; every observation class the registry names has a calibration record path | an entry whose class has no record |
| no clock in probes | no `time.time`/`datetime.now`/`perf_counter` reads inside a verdict path of any probe (the window deadline is the harness's, marked) | a probe reading `time.time` in `verdict_of` |
| no test-artefact resolution | no probe source names or discovers `tests/`, `test_*`, `conftest` | a probe with a `tests/` literal |
| scenario vocabulary closed | the `process_effect` step kinds are an enum; the dispatcher has no default branch | a dispatcher with a fallthrough |
| placeholder single-token | `<ws>` is the only substitution; no f-string or format over stimulus text | a second token |
| protocol channel discipline | cli_invocation and process_effect harness scripts never write protocol lines to the subject's stdout | a harness emitting READY on stdout |

## 2. Q1 — semantic conformance

Reused: the reference-model differential for the six projections (probe kinds do not enter the projections), the
admission engines' fixtures, the adversarial micro-workloads.

Extensions:

- **Observation-class tables.** For each kind, a table (class × observation facts → verdict) written from the RFC and
  the taxonomy proposal, tested exhaustively on fixture facts, including the expired-window verdict per class (§9.2)
  and `SUBJECT_ABSENT` under both `subject_absence` declarations (§10.2).
- **Test-layout invariance extended** (ARCH-LESSON-001): the same `cli_invocation` and `process_effect` specs under
  every layout of the fixture story's developer tests give identical product verdicts.
- **Independence of the two witnesses.** The implementer's and the verifier's checkouts of one revision give the same
  verdict for every new kind on a fixture set that includes committed bytecode, CRLF files and an executable-bit
  difference (the P7-FINDING-001 family generalised).
- **DESIGN-CHECK-1.** The protocol channel of a stdout-owning subject: the same exit under every scheduling of exit
  and channel close gives the same result (§9.4), on Linux and Windows.

## 3. Q2 — adequacy: mutation, calibration, falsifiability

- **ProbeCapabilityCalibration** for every (probe id, digest, class): `cli_invocation` ×3, `file_artifact` ×3,
  `process_effect` ×3, `python_callable` at its new digest ×(4 existing + 3 new). Positive and negative fixtures
  committed under `tests/v2/fixtures/calibration/<kind>/<class>/{positive,negative}/{request.json, checkout/}`. An
  always-SATISFIED or always-REFUTED probe cannot obtain a record (`calibrate` requires contrast on both fixtures) —
  this is CAL-1 as Cycle 1 sealed it, reused unchanged.
- **SpecFalsifiabilityEvidence** for every spec that will back qualified evidence, by `controlled_product_mutation` of
  a **reference implementation** of the workload committed as a fixture (never AISEF output, never the developer's
  candidate): one mutant per spec that the spec must refute. The V1 W1 oracle's reference implementation
  (`closure-evidence/hardening/w1/oracle/reference`, read-only) is the model for how such a fixture is written; Cycle 2
  writes its own under `tests/v2/fixtures/`.
- **Mutation** (`validation/v2/mutation.py`): new P2-class targets for every function of the new probes and the
  scenario interpreter; kill sets are the class tables and the calibration tests; the AUDITED-survivor allowance stays
  restricted to `tests/v2/refmodel/`.
- **Engineering-test sensitivity** stays deferred (RFC §33) unless the owner reopens it.

## 4. Q3 — fault injection

Reused: the fault server, the Q3 harness (`validation/qualification/q3.py`), the process-range faults, the interruption
and repair cases, the bytecode family FM2-PYC-1..9.

New families (each row typed, each with the vocabulary check that forbids untyped tokens in journal text):

| family | rows |
|---|---|
| FM2-CLI-HARNESS | interpreter absent; evaluation dir uncreatable; dir inside the checkout; protocol file unwritable |
| FM2-CLI-SUBJECT | never exits (deadline verdict per class); non-controller signal; controller stop (interrupted, no result); stdout flood; forged protocol line on stdout; nonzero exit shapes; `SystemExit(None/str)` normalisation |
| FM2-CLI-STREAM | exit before READY; exit after DISPATCHED without RESULT; RESULT then late bytes; channel closed by the subject; Windows temp-file marker absent (DESIGN-CHECK-1) |
| FM2-FILE | git absent; revision unknown; symlink entry; binary under text grep; regex cap exceeded; case-collision path |
| FM2-EFFECT | unknown step kind (INVALID_SPEC at admission); `fault` restoration failure (HARNESS_FAILED); exception in a non-final step; subprocess step residual (range residual); reconstruct without declaration |
| FM2-PYC-2 | the bytecode family re-run under cli_invocation and process_effect: committed stale bytecode, same-size rewrite, same-second dates — every checkout observes the source |

Environment/provider faults of Cycle 1 are unchanged and re-run on the new candidate.

## 5. Q4 — differential at scale

The six control-critical projections are unaffected by probe kinds: a probe's result enters the journal as a
`probe/evaluated` record and is routed by the same tables. The Q4 harness (`validation/qualification/q4.py`) is reused
**unchanged**; its generator already draws every disposition and code. One extension only: the generator's
`probe/evaluated` record should carry each of the new probe ids in some traces so the coverage table names them
(a coverage key, not a semantic change). 100,000 fresh traces on the exact Cycle-2 candidate, the same stop rules.

## 6. Q5 — real-execution reproduction

The Q5 harness (`validation/qualification/q5.py`) replays the model stream only and re-executes everything else; probe
kinds are "everything else", so the mechanism is reused unchanged. Extensions:

- **Corpus items** proved by each new kind (a CLI-proved story, a file-artifact prohibition, a scenario-proved story,
  a bytes-returning python_callable), recorded on the Cycle-2 candidate; the recording is expectation, the
  reproduction re-executes the probes.
- **Tool ledger** rows for the new probes' subprocesses (argv normalised with `<ws>`, exit, stream digests), read from
  the `probe/evaluated` records' `detail`.
- **Tokens**: the evaluation directory becomes `<TMP>`; nothing else is normalised (the frozen normalization digest
  changes and is re-frozen for Cycle 2).
- The adversarial cases of QP-9 are re-run on the new corpus: a changed request does not bind; a changed tool (now:
  a changed scanner *and* a changed probe fixture) is a diff.

## 7. Exit criteria of the Cycle-2 ladder

Q0–Q3 GREEN on the exact candidate on Linux 3.11–3.14 and Windows; Q4 100,000/100,000 with one kernel digest; Q5
GREEN with the extended corpus; mutation 0 unaudited survivors; every new observation class calibrated; every spec
that backs qualified evidence falsifiable; F1–F11 11 PASS with no ratchet regression; the Cycle-1 baseline byte-identical.
