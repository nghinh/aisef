# PROBE-DIAGNOSTIC-GAP-001 — a safe diagnostic channel (DESIGN ONLY, not implemented)

**Status: OWNER_DECISION_REQUIRED; recommended design H-DIAG-001 (harness-only).** Owner ruling 'AISEF V2 — ATTEMPT-4
EVIDENCE FREEZE + RELEASE NO-GO + MEASURED REMEDIATION DESIGN' (2026-10-03) §F. Nothing is implemented. The finding is
`closure-evidence/v2/cycle2/PROBE-DIAGNOSTIC-GAP-001.json` (ESCALATED_MEASURED_BLOCKER). Method as in
`H-CONTEXT-AUTHORITY-001-DESIGN.md` (investigators, two independent designs, a judge, two adversarial skeptics; one
designer breach of "never execute opencode" — `--version` only, no session, no provider). **[M]** measured, **[I]** inferred.

Goal: keep enough harness-observed failure information to make a retry actionable, without exposing the hidden ProductProof
stimulus and without letting diagnostics become control state.

## 1. The investigation order

| Rung | Result |
|---|---|
| 1. A sanitized diagnostic in the existing `ProbeResult.reason` | **NOT FEASIBLE** |
| 2. An existing evidence-reference mechanism binding a private raw artifact (journal carries only a ref) | **FEASIBLE in the harness only**, as an out-of-journal record anchored to the journal by seq and execution; an optional sha256 ref can ride in an existing free-text field |
| 3. A ProbeResult / F5 extension | **Not needed** for the developer-safe layer. It is the route the gap record names for a raw message from the *exact* proof execution (`a_fix_would_need`), deferred for separate review — not a route that contradicts the ruling |

**Why rung 1 fails [M]:**
1. *Type.* `Executed.reason` is `IndeterminateReason | None`, a closed two-member enum (`aisef2/product/outcome.py:28-33,39-40`); the RFC says a reason is "never free text" (`docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md:528-529`).
2. *Validator.* A non-None reason on REFUTED raises "only INDETERMINATE carries a reason" (`outcome.py:49-50`).
3. *Routing.* `reason` is a routing key (`aisef2/control/routing.py:125-128`): a new value on a REFUTED result finds no row and becomes `UnroutableOutcome` instead of CONTRACT_UNSATISFIED / DEVELOPER — the owner and code would change.
4. *Agreement.* Implementer/verifier agreement is equality of the whole result (`aisef2/journal/format3.py:204`): a diagnostic differing between checkouts becomes VERIFIER_DISAGREEMENT.
5. *Absence.* The message never leaves the probe child: `do_call` keeps `"refuted:raised " + type(e).__name__` (`aisef2/probe/process_effect.py:562-563`), and `classify_failure` drops `Observation.detail` for OBSERVED (`aisef2/probe/protocol.py:185`). Capturing it in the proof means editing a PROBE_SOURCES file: `protocol.py` feeds all five probe digests and is byte-pinned by CYCLE2 R2; the process_effect digest feeds the semantic hash of 34 of the 59 specs and, through spec ids, the plan hash.
6. *Pins.* Tests pin `reason` None, the result shape and the exact `why` strings (e.g. `tests/v2/p1/test_outcome.py:86-97`, `tests/v2/p2/test_probe_protocol.py:162-163`, `tests/v2/test_probe_process_effect.py:405-413`).

**What rung 2 can bind to [M]:** the kernel has no artifact store or ref field (journal hashes are self-seals, code
identities or seq citations); the harness already binds raw artifacts by `{path, sha256}` in its run record (13/13
session logs and the journal verify). `format3.validate` accepts a sha256 string inside `provider/result.detail`, an
existing free-text field the harness fills (`aisef2/journal/format2.py:130-131`; `story_runner.py:225-226`); it refuses
a new top-level `probe/evaluated` key and any new event type.

## 2. H-DIAG-001 (all in `validation/qualification/c2_p9.py`)

### 2.1 TAP — the exact execution's facts
For `probe.process_effect` the harness's probe factory (`c2_p9.py:747`) returns a subclass that overrides only
`observe`: it calls the probe's own `observe`, keeps the returned `Observation` (kind, verdict, detail facts), and returns
the same frozen object. Identity, digest, enforcement and `evaluate` are inherited; the probe capability identity comes
from the catalog digest (`c2_p9.py:669`), so it does not change [M].
**Binding key — corrected by a skeptic [M]:** not `record_digest`. That digest is a content address: the implementer and
verifier records of one proof are identical (seq 7748 = 7751, `bba43611…`), and one digest recurs across admission and
proof runs (`f988e2a7…` at seq 7649, 7785, 7884, 7887, 7921, 8020, 8023; 414 records, 140 distinct digests). Each
observation is keyed by (spec id, candidate sha, checkout root, call ordinal) and mapped after the story to its
`probe/evaluated` seq and the journal chain link there.

### 2.2 REPRO — the raw message and the raise site
On a retry, before the developer session, the harness re-runs the probe's own `HARNESS` bytes (imported read-only, its
digest checked against the journaled `probe_digest`) on the refuted candidate in a disposable copy, under a passive
`sys.settrace` prefix that records the exception object and its frames under the candidate root. Accepted only if its
refuted step, kind and exception class equal the TAP's facts from **both** witnesses; otherwise `withheld`.
**Corrected by a skeptic [M]:** REPRO executes the code of a rejected candidate while the new attempt's worktree exists
(`story_runner.py:177-178,218`), as the harness user without confinement (`process_effect.py:162-166`). It may therefore
run only inside the confinement of DEVELOPER-CONFINEMENT-GAP-001, against a copy, with the new worktree verified pristine
afterwards. A leak of its process range (`RangeNotEmpty` / `RangeEscaped`) or a failed disposal is never swallowed: it is a
harness failure of the run, as for any owned range.

### 2.3 PRIVATE HARNESS DIAGNOSTIC
`{rule, binding{story, failure seq, proof seq, probe seqs, execution keys, spec id, semantic hash, probe id, probe
digest, candidate}, exact{refuted, trace} per witness, reproduction{relation: REPRODUCTION, consistent},
raw{exception, message, frames}, safe_text | withheld}` — held in memory during the run, written after the last model
session, committed only as `{relative path, sha256, binding}`. **It is private only where no later developer process can
read it**: the default preserve root is a sibling of the workload repository on the same host, and the measured hunting
sessions searched such siblings. Until confinement exists, no on-host location is private.

### 2.4 DEVELOPER_SAFE_DIAGNOSTIC — a closed template
```
Harness observation (H-DIAG-001; both witnesses agree): a call to <method> raised <Exception>.
Reproduced on candidate <sha>: raised at <relpath>:<line> in <def>: `<candidate source line, <=160 chars>`; entered at <relpath>:<line> in <def>.
No input value, exception message or step order is disclosed.
```
| Slot | Source | Rule |
|---|---|---|
| method | the spec's step | shown only if public: named by an approved contract's subject or the frozen requirements (derived from data, not hard-coded) |
| Exception | runtime class | shown only if builtin or named by an approved contract; else omitted |
| relpath, line | runtime frame | must be a file of the archived candidate and a line inside it |
| def | the enclosing definition from the archived file's static AST at that line | never the runtime `co_name` |
| source line | the archived candidate file at that line | static candidate content — the developer's own code |

For S-D3-05-01-1 on 695c7f2 it would read [I]: *a call to apply_batch raised ValueError. Reproduced on candidate 695c7f2:
raised at ledgerlock/ledger.py:128 in _coerce_op: `raise ValueError(f"delete op needs 4 fields, got {len(items)}")`;
entered at ledgerlock/ledger.py:194 in apply_batch.* Together with REQUIREMENTS.md §5 that is actionable; it discloses the
code template ("needs 4 fields"), not the runtime value ("got 5").

### 2.5 Delivery
`retry_feedback(events, story_id, facts, diagnostics=None)` stays a pure function; with `None` its output is byte-identical
to H-RETRY-001, so the pinned feedback (`tests/v2/test_c2_p9_harness.py:357-358`) holds. The safe text is committed
verbatim in the run record (sessions do not record prompts; only `prompt_sha256` is kept, so a hash alone would make the
delivered prompt unverifiable from git). Nothing new is journaled; optionally (owner choice) a sha256 ref in
`provider/result.detail`. Only the `(seq, type, data)` projection of a journal can be byte-identical across runs: every
event carries a wall-clock `time` (`aisef2/journal/event.py:57`).

### 2.6 Why diagnostics never become control
No kernel object holds them: verdict, owner, retryability, budget, gate, merge and expectation are computed from the
journal and kernel code. The TAP returns the probe's own frozen Observation. REPRO makes no provider call and runs before
the session's timeout starts. Every instrument failure gives `withheld` and the unchanged H-RETRY-001 text, except an
owned-range leak, which halts the run as a harness failure (2.2).

## 3. Leakage

- **Literal exclusion of every probe_input atom cannot be met.** The S-D3-05-01-1 stimulus contains `delete`, the keys
  `a`, `b`, `d`, the rids, and the integers 1-8 (`validation/qualification/p10_contracts.py:135-137,413-415`) [M]; the
  owner's own example ("delete operation received 5 fields but implementation accepts 4") contains three of them. The rule
  adopted instead is value provenance: no slot is filled from a probe_input *value* or from product runtime text.
- **Two slots are allowlisted tokens drawn from probe_input** (the method, the step kind); this is disclosed, and limited to
  public names. The step kind is not rendered as `expect_raises`, a word the standing disclosure test forbids
  (`tests/v2/test_c2_p9_harness.py:392`).
- **Structural residual [M]:** the subject is imported into the probe interpreter whose module-global `req` holds the whole
  scenario (`aisef2/probe/process_effect.py:431`; imports at `:523`, `:663`). Executed candidate code can therefore read
  the full stimulus without touching a file, and every candidate-controlled slot (which exception, which file and line) is
  a covert channel of a few bits per failing proof per retry. File-read confinement cannot shrink it; only the closed
  template bounds it. The owner must accept that bound (OD-F1) or require rung 3.
- **Secrets:** exact known secret values are replaced and counted (`c2_p9.redact`) in the private record; the safe template
  carries no runtime text.

## 4. Flags

| Flag | Value | Justification |
|---|---|---|
| PROBERESULT_SHAPE_CHANGE_REQUIRED | **NO** | `Executed`, `ProbeRecord` and `classify_failure` are untouched; REFUTED keeps reason None |
| EVENT_VOCABULARY_CHANGE_REQUIRED | **NO** | no event type, no payload key; an optional ref uses the existing `provider/result.detail` text |
| PROBE_DIGEST_CHANGE_REQUIRED | **NO** | no PROBE_SOURCES file changes; the TAP inherits the digest; REPRO reuses `HARNESS` read-only and refuses on a digest mismatch |
| PRODUCT_SEMANTIC_HASH_INVALIDATION_REQUIRED | **NO** | probe digest, probe input and expectation unchanged (`aisef2/product/spec.py:68-75`); spec ids and plan hash unchanged |
| Q0_Q1_Q2_Q3_REQUALIFICATION_REQUIRED | **YES — identity only, and already pending** | the design adds tests under `tests/v2`, and any change there "is a new candidate, restarted from Q0" (`validation/qualification/common.py:34-37`); that restart is already required because the Q0-Q3 subject is pinned to c11615a (kernel 254d8f55, tests/v2 fb9d8e17) while HEAD carries c2717d2e / 67caa348. No rung's semantics are touched by this design |
| Q4_INVALIDATED | **NO** (by this design) | Q4 binds the kernel, the reference models, the generator and its own harness, none changed; Q4-FINAL is already stale for the current kernel digest 94b1aea4 |
| Q5_INVALIDATED | **NO** (by this design) | Q5 binds its harness, fixtures, the F1/F9 files and the kernel, none changed; Q5-FINAL is already invalid for c2717d2e (its pre-satisfied item 61 → 53 events) |

**Qualification invalidation scope.** (1) The harness files' shas (`c2_p9.py`, and `c2_delivery_experiment.py` for the
rule name in `harness_identity`) → the RunSpec `harness` setting → template and resolved hash → a new preregistration and
attestation: a new attempt identity, which needs owner authorisation ("no attempt 5"). (2) Before any harness edit,
attempt 4 is historicalised (`HISTORICAL[4]`, evidence commit 9b919a3) and the attempt-4 preregistration tests that compare
the bound harness shas with the working tree (`tests/v2/test_c2_delivery_experiment.py:714-752`) move to the historical
check, as was done for attempt 3. (3) The K-NOWORK-001 rehearsal re-bound (it binds `c2_p9.py`). (4) Q0-Q3 restart by
identity (pending anyway). (5) No kernel, probe, spec, plan, Q4 or Q5 invalidation by H-DIAG-001 itself. The
**preconditions carry their own scope**: confinement chosen at S2/S3, or any move of the probe's evaluation directories
inside PROBE_SOURCES, is a kernel/probe change (probe digest, 34 semantic hashes, Q0-Q5).

## 5. Preconditions and owner decisions

- **Preconditions (the channel is not deployable alone).**
  (a) DEVELOPER-CONFINEMENT-GAP-001 closed for the developer *and* for developer-authored code the harness or kernel
  executes (probe subjects, developer tests, REPRO), as write and egress confinement, with a per-run client data
  directory — the operator's OpenCode store already holds 62 copies of a hidden scenario fragment [M].
  (b) H-CONTEXT-AUTHORITY-001 corrected generically (CTX-001): in attempt 4 the developer had the root cause in hand
  (STORY-04-02 attempt 3, #237) and still stopped because of the workspace's V1 write-scope prose (#241), so a diagnostic
  alone would not have fixed attempt 4.
- **OD-F1. Disclosure set and leakage standard:** value provenance with the bounded covert channel of §3 (recommended),
  or the enum line only (no raise site; cannot express the owner's 4-versus-5 example), or rung 3.
- **OD-F2. Binding:** exact-execution facts from the TAP plus a consistency-gated reproduction for the raw message
  (recommended), or rung 3 for a raw message from the exact execution.
- **OD-F3. Journal ref:** none (recommended) or a sha256 ref in `provider/result.detail`.
- **OD-F4. Order and authorisation:** confinement, then CTX-001, then H-DIAG-001; one new attempt identity for the
  combination, which the current authority forbids.
- **OD-F5. Record keeping:** PROBE-DIAGNOSTIC-GAP-001 stays a kernel-level finding; H-DIAG-001 would be recorded as a
  harness mitigation, labelled as such — it covers `probe.process_effect` refutations that raise, not other probe kinds.

## 6. Ceilings, deliberately

Only `probe.process_effect`; no diagnostic for refutations without an exception (wrong value, files, exit codes, faults,
deadlines), because describing those reveals the expectation; no diagnostic for parent-admission failures; threads and
subprocess steps are not traced; a product that disables tracing gives `withheld`. Add any of these when one actually
blocks a retry.
