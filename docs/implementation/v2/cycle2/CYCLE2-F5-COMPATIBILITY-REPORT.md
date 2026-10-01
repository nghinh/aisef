# CYCLE-2 F5 COMPATIBILITY REPORT

**Status.** Planning artefact (owner's "CLOSE CYCLE-1 / PREPARE CYCLE-2 ARCHITECTURE ONLY", 2026-09-28). This is the first
hard gate of the study: before any probe kind is proposed for implementation, does it fit the frozen probe protocol as
Cycle 1 sealed it? Verdicts are one of `F5_COMPATIBLE`, `F5_REQUIRES_ARCHITECTURE_EXCEPTION`, `INSUFFICIENT_EVIDENCE`.
No code was written; the verdicts rest on the frozen text and the sealed implementation, cited by anchor.

## 1. What F5 freezes (the yardstick)

From the RFC's normative freeze table (digest `d71b958b…`, effective lineage through V2-006), F5 is:

| frozen element | anchor | consequence for a new probe kind |
|---|---|---|
| `Probe` protocol: `id`, `digest`, `enforcement()`, `harness_preconditions()`, `evaluate(spec, at, env) -> ProbeResult` | RFC §9; `aisef2/probe/protocol.py::Probe` | a new kind is a new object satisfying this protocol; the protocol itself does not change |
| the observation-harness / subject split | §9 | harness failure → `UNRUNNABLE` (ENVIRONMENT); subject absence and subject deadline are observations, never `UNRUNNABLE` |
| harness timeout vs subject observation deadline | §9.2 (V2-002) | every observable must assign a verdict to an expired window or be `INVALID_SPEC` at admission |
| signal provenance after dispatch | §9.3 (V2-003) | the controller's signal ledger is the only authority; a non-controller signal → `EXECUTED + INDETERMINATE(NON_CONTROLLER_SIGNAL)` |
| protocol stream vs process lifecycle | §9.4 (V2-006) | the protocol ends at its own end of file; no timing window orders the two channels |
| `ProbeResult` fields (`Executed`, `Unrunnable`, `InvalidSpec`), `Observation` kinds | `protocol.py::Observation`, `classify_failure` | a probe reports a typed `Observation`; `classify_failure` is the only mapping to a result |
| the two calibration contracts, each demonstrating contrast to `candidate_expectation` | §9.1.1, §9.1.2; `calibration.py` | every new observation class needs a `ProbeCapabilityCalibration` with positive and negative fixtures; every qualified spec needs `SpecFalsifiabilityEvidence` |

Adjacent frozen items that a probe kind touches without changing:

- **F4** freezes the compiler contract and the inputs to `semantic_hash` (subject, stimulus, observable, `subject_absence`, `candidate_expectation`, probe id and digest). The *vocabulary inside* `stimulus` and `observable` is not frozen: it is a JSON mapping whose meaning the probe's registered observation class gives (`ProbeMetadata.observation_class`, PROBE-META-1). `Subject.kind` already enumerates `cli_invocation`, `file_artifact`, `process_effect`, `http_route` (F4, `SubjectKind`).
- **F2** freezes the two-axis outcomes; new probes produce only `EXECUTED × {SATISFIED, REFUTED, INDETERMINATE}`, `UNRUNNABLE`, `INVALID_SPEC`.
- **F9** freezes the four identities; a new probe is a new capability identity tuple in the RunSpec, and a new probe id/digest in `semantic_hash`.
- **F10** invariant IX: probes are harness-owned; the probe API takes no developer-authored path.

## 2. Verdict per kind

### 2.1 `cli_invocation` — **F5_COMPATIBLE**

- **Protocol fit.** A `HarnessProbe` subclass with its own harness script: it resolves the subject module *inside the revision* (the python_callable `inside()` rule), then dispatches `runpy.run_module` with the stimulus argv under `-I -B -X pycache_prefix=<fresh>`. It reports `Observation` kinds exactly as python_callable does: `HARNESS_FAILED` (interpreter cannot launch, working directory cannot be created, protocol channel cannot open), `UNSUPPORTED` (an observable with no class), `SUBJECT_ABSENT` (the module does not resolve inside the revision), `OBSERVED`, `SUBJECT_DEADLINE`, `NON_CONTROLLER_SIGNAL`.
- **§9.2.** The observable declares `within_s`; the class assigns a verdict to an expired window (`REFUTED` for `exits`, `REFUTED` for stream and file shapes; a spec that wants `SATISFIED` on expiry declares `blocks`). No global rule.
- **§9.3 / §9.4.** The subject owns stdout and stderr, so the protocol stream cannot share them. The design puts the protocol on a harness-owned result file plus the wrapper's exit; the stream/lifecycle rule applies to that file's close, and the existing `_watch` pump-completion barrier is reused on a dedicated pipe (fd 3 on POSIX, a named pipe or a temp file on Windows). This is the one place where the design must be shown, not assumed: **DESIGN-CHECK-1** in the taxonomy proposal specifies it and Q3's fault family FM2-CLI-STREAM covers it.
- **Calibration.** Classes `exits`, `exits_streams`, `exits_files`, each with positive and negative fixtures (a fixture module that exits 0 with a shaped stderr; a mutant that exits 1 or writes to stdout).
- **No exception needed.** No new `Owner`, `ProbeExecutionStatus`, `BehaviorVerdict`, event type or plane.

### 2.2 `file_artifact` — **F5_COMPATIBLE**

- **Protocol fit.** No subprocess: the probe reads the revision. Classes `exists`, `content` (sha256 of the committed blob), `grep_count` (regex over the committed text files under a directory). Absence of the path is `SUBJECT_ABSENT`; for a prohibition the contract declares `ABSENCE_IS_DECIDABLE` (NEG-2/NEG-3 in §10.2) and `classify_failure` takes the observable's verdict over the absent subject.
- **§9.2.** A pure read has a trivial window; the class still declares the verdict for an expiry (`REFUTED`) so admission check 9 has a meaning.
- **§9.3 / §9.4.** Not engaged: nothing is dispatched.
- **Enforcement.** `FULL` is claimable only with the weakest path named: a symlink or a path that resolves outside the revision root is refused (`HARNESS_FAILED`), and content is read from git's object store (`git cat-file` by the revision SHA), never from the working file, so autocrlf, mode bits and editors cannot become authorities.
- **No exception needed.**

### 2.3 `process_effect` — **F5_COMPATIBLE**, with one owner decision (DECISION-2) that is not an architecture exception

- **Protocol fit.** A scenario probe: one harness process per evaluation, a fresh workspace directory, a closed typed step vocabulary (`workspace`, `construct`, `call`, `expect_raises`, `write`, `edit_jsonl`, `subprocess`, `fault`), and file/return observables read after the last step. Observation kinds as in 2.1.
- **§9.2.** One bounded window for the whole scenario (the spec's `within_s`), not per step: a scenario that does not finish is one expired window with the class's assigned verdict. This is a design choice inside §9.2, not a change to it.
- **§9.3 / §9.4.** Same harness/protocol discipline as python_callable (the protocol on the harness's own stdout, the subject's prints redirected to a captured file so they cannot forge protocol lines — the nonce rule already in the python_callable harness).
- **The `fault` step.** "A simulated crash (e.g. patching `os.replace` to raise)" is a controlled fault inside the subject's process, declared in the contract's stimulus, executed by the harness. F5 does not forbid it (the harness owns the observation; the fault is harness input, not a developer artefact), and F2/F10 are untouched. It is nonetheless a new *kind of stimulus* and the owner must sanction it explicitly (DECISION-2). If declined, criteria 01-04-5 and 03-01-5 stay unprovable and must be restated by the plan author.
- **No exception needed.**

### 2.4 richer `python_callable` observables — **F5_COMPATIBLE**

- `returns_bytes` (hex of the returned bytes), `equals` over a non-callable subject (a constant), and a `workspace` stimulus (fixture files the harness writes into a fresh directory and passes by absolute path in place of `<ws>/…` placeholders). Each is a new observation class of the same probe at a **new digest**: every Cycle-1 `semantic_hash` that cites the old digest keeps its meaning (F4: the hash binds the digest), and Cycle-2 specs cite the new one. Q2 re-calibrates every class of the new digest, the old classes included.
- Instance methods and multi-call sequences are **not** added to python_callable: they are `process_effect` scenarios, so python_callable stays a one-call, one-value probe.
- **No exception needed.**

### 2.5 `http_route` — **INSUFFICIENT_EVIDENCE**

- LedgerLock's requirements exclude a network listener (§2 non-goals). No criterion of the P10 workload has this kind (matrix: 0). No other workload is authorized. There is no measured need, so no schema is designed and no verdict on protocol fit is claimed. It stays deferred with its trigger: a workload authorized by the owner whose requirements name an HTTP surface.

## 3. What would require an Architecture Exception (none is proposed)

The study looked for anything that cannot be expressed without changing frozen semantics:

| candidate | frozen item | finding |
|---|---|---|
| a verdict other than SATISFIED/REFUTED for an expired window | F5 §9.2 | not needed: every class assigns one |
| a probe keeping its own signal ledger or PID tree for the scenario's subprocess step | F5 §9.3 | not needed: the step runs inside the same owned range; the controller's ledger is the authority |
| a new `IndeterminateReason` for "scenario aborted at step k" | F2 | not needed: a step that raises is `OBSERVED` with the observable's verdict (`expect_raises`) or `REFUTED`; a harness failure is `UNRUNNABLE`; a spoiled observation is `NON_CONTROLLER_SIGNAL` |
| a new event type for scenario traces | F1 | not needed: the trace is inside `probe/evaluated`'s record `detail`, never read for control |
| a new `Owner` for fixture failures | F3 | not needed: a fixture the harness cannot write is `HARNESS_FAILED` → ENVIRONMENT; a fixture the spec mis-declares is `UNSUPPORTED` → INVALID_SPEC |
| `Subject.kind` members | F4 | already present |

Therefore no `ARCHITECTURE-EXCEPTION-V2-007` proposal is drafted. If implementation finds that any observable of `process_effect` needs a verdict the classes above cannot assign, the rule of this task applies: STOP and draft the exception, do not implement around it.

## 4. Summary table

| kind | verdict | new observation classes | calibration fixtures | owner decision |
|---|---|---|---|---|
| cli_invocation | F5_COMPATIBLE | exits, exits_streams, exits_files | 3 × (positive, negative) | none |
| file_artifact | F5_COMPATIBLE | exists, content, grep_count | 3 × (positive, negative) | none |
| process_effect | F5_COMPATIBLE | scenario_returns, scenario_raises, scenario_files | 3 × (positive, negative) | DECISION-2 (`fault` step) |
| python_callable (extended) | F5_COMPATIBLE | returns_bytes, equals, workspace-backed returns/raises | re-calibrate all classes at the new digest | none |
| http_route | INSUFFICIENT_EVIDENCE | — | — | a workload with a measured need |
