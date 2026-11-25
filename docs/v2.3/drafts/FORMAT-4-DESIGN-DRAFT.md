# AISEF v2.3 -- FORMAT-4 JOURNAL DESIGN (E6, lane L2-JOURNAL) -- DRAFT for the C-1 freeze

**Status:** DRAFT. Becomes frozen as contract C-1 (ACCELERATED-DELIVERY-PLAN.md sec. 2) only by an owner freeze;
after that, a change is an appended dated amendment, never an edit. This is the pacing link of the whole v2.3
plan (plan sec. 1): the ORCHESTRATION track and E2/E4 start only after this freeze.

**Covers (frozen inputs):** E6 + V21-10 + CODE-AUDIT #11 + #93 (MASTER-CHECKLIST rows; DAG sec. 1a W2 L2-JOURNAL);
consumer schemas for E2/E4 (reservation, segment digest), C7 (provider/attestation), G6 (closed-story marker),
C5 (closing identity), C3b (no_progress input); COMPATIBILITY-MATRIX rows J1-J8, rules CR-1..CR-7, test CT-2;
RELEASE-CHARTER sec. 4 (keep 2.2.0 readers or a versioned migration); owner decision V21-57 (default keep).

---

## 1. Measured facts that fix this design

| # | Fact | Evidence |
|---|---|---|
| M1 | The story lifecycle is defined twice and the two definitions diverge. The format-3 writer-validator admits `proof/verified` and `tests/adequacy` in ANY open attempt, BEGIN included (`_story_active`: "no open attempt" is the only refusal). The StoryState projection admits them only in ACTIVE, and `provider/request` only in ACTIVE, which the writer-validator never checks at all (no `_RULES` entry for it in f2 or f3). | `aisef2/journal/format3.py:173-177,218-220`; `aisef2/journal/projections/story_state.py:13-14`; `aisef2/journal/format2.py:235-238` |
| M2 | The asymmetry is reconstruct-vs-fold: `reconstruct` runs only the writer-validator, so a chain-consistent journal carrying `proof/verified` in a BEGIN attempt reconstructs cleanly and is refused only when a gate folds StoryState. | CODE-AUDIT #11 (:164); `format3.py:303-332`; `projections/__init__.py:34-39` |
| M3 | The shipped 2.2.0 kernel cannot emit the divergent journals: every production append goes through `Authority`, which peeks all six control projections before a byte is written, so an event StoryState refuses never reaches the log. The divergence is adversarial-input-only (V21-10 row: "the kernel never emits these", R1 NO). | `aisef2/journal/fold.py:134-158`; `runtime/run_scope.py:125` (`Authority(self._writer, PROJECTIONS.values())`); MASTER-CHECKLIST V21-10 |
| M4 | `VOCABULARY` and format 3's failure-code set are computed from the LIVE enums (`frozenset(t.value for t in EventType)`; `_enum(FailureCode)`), so adding any v2.3 EventType member or FailureCode member silently changes what the SEALED format 1-3 readers accept or skip. Formats 1/2 pin codes by literal (`FORMAT_2_CODES`); nothing pins the 29 event names or format 3's 22 codes. | `aisef2/journal/event.py:41`; `format3.py:137-139`; `control/owner.py:64` |
| M5 | Today: 29 `EventType` members; 22 `FailureCode` members (13 `FORMAT_2_CODES` + 9 V2-005); 6 `ControlProjection` members (closed list F11). StoryState is version 2, TerminalState version 1, Budgets version 2 (format-gated at >= 3 for `budget_owner`). | `arch/enums.py:133-162,190-196`; counted by AST on `owner.py`; `projections/{story_state.py:21,terminal_state.py:20,budgets.py:22}` |
| M6 | The production writer is wired in exactly one place: `RunScope.begin` constructs `JournalWriter3` and appends `run/begin {journal_format: 3}`. The three writers (`writer.py`, `JournalWriter2`, `JournalWriter3`) are the same P3 discipline with per-format `validate`/`reconstruct`; that triplication IS the sealed house pattern (FMT3-7: a sealed format's module is never rewritten). | `runtime/run_scope.py:123-125`; `journal/{writer.py:31-103,format2.py:333-412,format3.py:337-417}` |
| M7 | E5 (landed, W1b) fixed the production event sequences this table must legalize: typed `Stage` 1-13, the contained-fault tail (`provider/result{OUTCOME_UNKNOWN, synthetic}` closer, then `gate/check`, `gate/decision`, `failure/observed UNKNOWN`, `story/rollback`, `story/dispose`, releases, `story/end`), and the run.py:693 refusal branch, which reads only the words of `story/commit|rollback|retry` via `outcomes_from`. | `orchestrate/story_runner.py:57-93,409-473`; `app/run.py:393-401,693-696`; W1-DESIGN sec. 4 |
| M8 | `provider/result` carries no stream digest and `provider/request` no reservation; spend reconciliation trusts unchained on-disk session streams (E2/E4 gap, both "unimplemented"). `tests/adequacy` drops the audit inputs: `payload()` serializes outcome axes only -- no `Assembly.reason`, no vacuity `neutralised/attributed/reason`, no relevance `intersections/unmeasured` (#93). | CODE-AUDIT #12; `format2.py:130-132`; `orchestrate/quality.py:37-46` |
| M9 | `proof/verified` checks only key-presence of the cited `ProbeRecord` (`all(k in r ...)`), never seal validity, although every kernel record is sealed: `record_digest = digest(content_of(record, without="record_digest"))` and an edited record raises. The seal is mechanically re-derivable from the plain mapping the journal stores. | `format3.py:195`; `probe/protocol.py:200-214` (V21-10) |
| M10 | `no_progress` is already a pure derivation over `failure/observed` + `story/begin` + `story/retry|rollback` (report in RUN.json); C3b only needs that derivation as a journal projection -- no new event kind (NO_SIDE_RETRY_COUNTER). | `app/usage.py:118-142`; IMPROVEMENT-ROADMAP C3(b) |
| M11 | COMPAT-MATRIX already reserves the slot and the bound: J4 "format 4 ... NEW-ONLY; new reconstruct delegating 1-3 to format3.reconstruct unchanged; to add: FMT4-3 analogue of FMT3-3" = CT-2 (W2). CR-7: the signed-run discriminator lives inside the hash chain -- "format-4 run/begin declares the key fingerprint"; a format >= 4 run missing its signature/manifest/started file is REFUTED. CR-11: G6 resume applies only to format >= 4 journals. | COMPATIBILITY-MATRIX.md J4, CR-7, CR-11, CT-2 |
| M12 | File ownership (DAG sec. 4, W2b L2-JOURNAL): `orchestrate/quality.py` (payload() only), `journal/{event,format2,format3,writer,compat}.py`, NEW `journal/{format4,transitions}.py`, `journal/projections/{story_state,terminal_state,failure_owner,retry_target,qualification_counters}.py`. `arch/enums.py` is owned by NO W2 lane (read-only by DAG sec. 4 rule (a)); `runtime/{run_scope,repair}.py` and `projections/budgets.py` are L2-ACCOUNTING's; `journal/event.py` hunks wait for the L2-SIGN merge (plan sec. 3 item 6 [F]). | DEPENDENCY-DAG.md sec. 4 W2 table; ACCELERATED-DELIVERY-PLAN.md sec. 3 |

**Conclusion from M1-M4:** E6 is not only "merge two if-chains". Freezing one table is necessary but not
sufficient -- the sealed readers' vocabularies must be PINNED at the same freeze, or every later v2.3 enum
addition re-opens formats 1-3 semantics silently (the exact defect class M4 names). Both are in scope here.

---

## 2. Scope and non-goals

FORMAT-4 is the ONE new writer format for all of v2.3 (DAG: "one new writer format for all of v2.3", edge
E6 -> C7/G6/C5). Every v2.3 consumer that needs a new required event or field lands it HERE, at this freeze.
There is no format 5 in v2.3; a consumer whose need surfaces after the freeze either fits an OPTIONAL field
already admitted by these schemas or waits for v2.4.

Non-goals (stated so nobody waits on this freeze for them):
- N1. Signing mechanics (key generation, head signature, `--expect-pubkey` verification) are A2 / contract C-2.
  FORMAT-4 freezes only the `run/begin` field that CR-7 requires inside the chain (sec. 4.1).
- N2. Attestation probe semantics (cadence, drift rule, which prompts) are C7 / W3. FORMAT-4 freezes only the
  event envelope (sec. 4.4).
- N3. The resume algorithm and the fingerprint composition are G6 / W4. FORMAT-4 freezes the marker event and
  the field kinds (sec. 4.5).
- N4. Wave scheduling and the worktree manager are C5 / W4. FORMAT-4 freezes the serialized-append invariant
  statement, the optional worktree-base field and the run-close accounting rule (sec. 4.6).
- N5. Monetary budget enforcement (C2 caps) and reservation reconciliation (`charge max(reservation, stream)`)
  are E2's lane logic in usage/verify/budget; FORMAT-4 freezes the data (sec. 4.2-4.3).
- N6. The E1 verdict projection module itself (W2c, L2-AUTH). FORMAT-4 freezes the table API it reads (sec. 3.6).

---

## 3. The transition table -- NEW `aisef2/journal/transitions.py`

### 3.1 Form (normative)

The module MUST contain only pure values (JSON-foldable tuples/mappings of strings) plus one pure function.
No wall-clock, no prose-as-control, no import beyond `aisef2.arch.enums` (E6: "the table must be a pure value").

- `STORY_STATES`: the 13 story states, the full product of phase x outcome that the two existing validators
  jointly distinguish today (M1): `ABSENT`, `BEGIN`, `BEGIN_REFUSED` (begun, admission refused), `ACTIVE`,
  `DECIDED_COMMIT`, `DECIDED_ROLLBACK`, `DECIDED_RETRY`, `DISPOSED_COMMIT`, `DISPOSED_ROLLBACK`,
  `DISPOSED_RETRY`, `ENDED_COMMIT`, `ENDED_ROLLBACK`, `ENDED_RETRY`.
- `symbol_of(event_type, data) -> str`: the pure discriminant. Most types map to themselves; the three
  payload-dependent ones split: `story/admitted` -> `story/admitted:accepted | story/admitted:refused`
  (on `data["admitted"]`); nothing else reads data. It never raises: an unknown type returns the type string.
- `STORY`: `Mapping[(state, symbol), state]` -- the moves. Absence of a key = REFUSE. Rows (exactly the
  2.2.0 semantics of `story_state.py` + `_OUTCOMES`/`_WITHIN`, re-keyed):
  `(ABSENT, story/begin) -> BEGIN`; `(ENDED_RETRY, story/begin) -> BEGIN`;
  `(BEGIN, story/admitted:accepted) -> ACTIVE`; `(BEGIN, story/admitted:refused) -> BEGIN_REFUSED`;
  `(ACTIVE, story/commit) -> DECIDED_COMMIT`;
  `(BEGIN|BEGIN_REFUSED|ACTIVE, story/rollback) -> DECIDED_ROLLBACK`;
  `(BEGIN|BEGIN_REFUSED|ACTIVE, story/retry) -> DECIDED_RETRY`;
  `(DECIDED_x, story/dispose) -> DISPOSED_x`; `(DISPOSED_x, story/end) -> ENDED_x`.
- `WITHIN`: `Mapping[symbol, frozenset[state]]` -- events legal in a state without moving it:
  `probe/evaluated: {BEGIN, BEGIN_REFUSED, ACTIVE}`; `provider/request: {ACTIVE}`;
  `proof/verified: {ACTIVE}`; `tests/adequacy: {ACTIVE}`;
  `failure/observed: every state except ABSENT`;
  `story/plan-drift: {ACTIVE, BEGIN_REFUSED}` (P3-PROJECTION-SEMANTICS.md sec. 14 "MUST emit": a blocked story still records drift);
  `provider/result: every state except ABSENT` (closers may land during unwinding, M7);
  `story/completed: {ENDED_COMMIT}` (sec. 4.5).
  Resource/tool kinds are NOT in the table: their lifecycle rules stay format 2's, as written (sealed).
- `RUN`: the run-level table, lifted verbatim from `terminal_state.py:10-14` (`_RUN`), with symbols
  `run/interrupted:first | run/interrupted:abandoning` instead of the `(type, abandoned)` tuple key.
- `TABLE_DIGEST`: `product.contract.digest` of the canonical JSON of `{STORY_STATES, STORY, WITHIN, RUN}`,
  computed by a test and asserted as a literal -- consumers pin the table by this digest, and any edit to the
  values is a visible, reviewed diff of one line.

### 3.2 Consumers (all six; this is the whole point of E6)

1. **format4 validator** (sec. 5): the story-lifecycle legality of every f4 event IS a table lookup. No
   ad-hoc `_story_active`.
2. **format3 writer-validator** (sealed module, surgical edit -- see sec. 6 compat bound): `_story_active`
   and the `proof/verified`/`tests/adequacy` gating are re-derived from the table through a small adapter
   mapping f3's two-state view onto the table's states. Outcome on every kernel-producible journal is
   IDENTICAL (equivalence test, sec. 8 T10); the only behavior changes are the enumerated adversarial
   refusals of #11 and V21-10 (sec. 6).
3. **StoryState projection v3**: `step` is `STORY`/`WITHIN` lookups plus the attempt counter and the
   admitted flag it already keeps. Fold over every format <= 3 journal MUST equal v2's fold (J7 bound).
4. **TerminalState projection v2**: run-level part reads `RUN`; story-level part reads the outcome words
   off the table states. Same J7 bound.
5. **E1 verdict fold** (W2c, L2-AUTH): imports `STORY_STATES`/`STORY`/`symbol_of` to derive the delivery
   verdict as a fold; `run.py:693`'s `outcomes_from` words (`COMMIT/ROLLBACK/RETRY`) are exactly the
   table's `DECIDED_x` suffixes, so the refusal branch needs no change at this freeze.
6. **C3b no_progress projection** (W4, L4-MONITOR): attempt boundaries = the table's `story/begin` rows;
   failure identity = `failure/observed` code+detail as today (M10). No new event kind; nothing else frozen
   for it here.

---

## 4. FORMAT-4 schemas -- what changes against format 3, consumer by consumer

FORMAT-4 = format 3's schemas and rules, with the deltas below and the table as the story-lifecycle rule.
Everything not named here means EXACTLY what it means in format 3 (the f1/f2/f3 validators are reused for
unchanged kinds, the f3 pattern at `format3.py:143`). Two NEW event types enter the vocabulary:
`provider/attestation` and `story/completed` (31 total). New required fields appear ONLY in format-4
journals; formats 1-3 never admit them (CR-3).

### 4.1 `run/begin` (A2 / CR-7 / G6)

Required: `journal_format` (= 4), `run_id` (str), `kernel_digest` (hex64 -- the digest `run.py:93-100`
computes; G6/CR-11 needs it inside the chain), `signer` (hex64 -- sha256 fingerprint of the run's ephemeral
public key; CR-7: the signed-run discriminator lives inside the hash chain). Optional: `bundle_digest`
(hex64; G6 decides at W4 whether its fingerprint reads it from here -- open question Q4).
A format-4 journal without a valid signature is REFUTED by verify (CR-7); `signer` being required means
JournalWriter4 cannot start a run before A2 primitives exist -- the W2a -> W2b order is load-bearing (Q5).

### 4.2 `provider/request` (E2 -- owner-typed write-ahead reservation)

Required: format 3's fields (`story_id`, `criteria`, `budget_owner`) plus `reservation`: a mapping with
required keys `turns` (count | null) and `max_usd` (finite number >= 0 | null), nothing else. Null means
"explicitly unbounded", never "absent". The reservation is DATA, owner-typed by `budget_owner`; it is
written before dispatch (the request already is, M7) and reconciled at the result; a run killed between
request and result charges `max(reservation, stream)` (E2's lane logic, N5). Budgets projection stays v2:
its format >= 3 branch already covers 4, and request-counting semantics do not change.

### 4.3 `provider/result` (E4 -- stream segment sealed into the chain)

Required: format 2's fields plus `segment`: null, or a mapping with required keys `session` (nonempty str:
the stream file's run-relative path), `sha256` (hex64 over the exact byte range), `offset` (count), `bytes`
(count). Rule R-SEGMENT: `outcome == COMPLETED` => `segment` is non-null; `synthetic` (closer) => `segment`
is null (the torn-tail/SIGKILL segment is DEFINED as: no bytes are accounted by the closer -- repair charges
the reservation per E2); `FAILED` => either, and `detail` says which. Verify re-derives each segment digest
before re-deriving spend; a truncated or edited segment is a specific integrity FAIL, never an "unknown"
fallback (CODE-AUDIT #12 acceptance).

### 4.4 `provider/attestation` -- NEW type (C7)

Required: `session` (nonempty str), `expected` (nonempty str), `observed` (text), `passed` (bool),
`detail` (text). Optional: `story_id` (nonempty str). Cites nothing. WITHIN: any point after `run/begin`
and before `run/end` (attestation probes interleave across paid sessions at session boundaries). Probe
cadence, drift aggregation and cost routing through the preflight ledger are C7's (N2); C7 signs off on
this envelope AT this freeze because it cannot add required fields later (Q8).

### 4.5 `story/completed` -- NEW type (G6 closed-story marker)

Required: `story_id` (nonempty str), `revision` (sha), `fingerprint` (hex64). Cites exactly one
`story/commit` of the same `story_id`. WITHIN `{ENDED_COMMIT}`; at most one per story per run (rule).
Appended by the run driver (run.py finalize), never by `_attempt`. The fingerprint is the sha256 of the
canonical JSON G6 freezes at W4 over at least (bundle digest, kernel digest, route identity, base revision);
only the field kind and the binding rule freeze here (N3). CR-11 holds: resume reads markers only from
format >= 4 journals whose `run/begin.kernel_digest` matches.

### 4.6 C5 closing identity (G9 pattern: run parallel, append serial)

- The journal stays ONE serial append chain whatever C5 parallelizes (restating the P3 writer invariant;
  C5's executor serializes at the append point -- design reference G9).
- `story/resource-acquired` gains optional `base` (sha), written for `kind == WORKTREE`: the revision the
  per-story worktree was created at, so interleaved attempts stay attributable.
- Rule R-CLOSED (f4 `run/end` rule): `run/end` is REFUSED while any `provider/request` in the journal has
  no `provider/result` -- every request has exactly one accounted outcome before the run may close (G9's
  closing-identity core; the interrupt path already writes closers first, M7). The remaining G9 checks
  (attempt count vs session count, duplicate labels) are derivations in C5's verify step, not events.

### 4.7 `tests/adequacy` (#93 -- auditability of blocking quality verdicts)

Optional field `audit`: a mapping with keys `reason` (text: `Assembly.reason`), `vacuity` (null | mapping
`{neutralised: bool, attributed: text, reason: text}`), `relevance` (null | mapping `{intersections: count,
unmeasured: strs}`). Exact inner keys are fixed with the L2-JOURNAL `quality.payload()` edit at
implementation and frozen by the FMT4 schema test; the acceptance is #93's round-trip. OPTIONAL so that
synthetic test journals without assemblies stay writable; `payload()` always emits it in production.

### 4.8 `proof/verified` and probe-record sealing (V21-10 hardening)

Three f4 rules (defense in depth; the kernel never emits the negatives, M3):
- R-SEALED: each cited `probe/evaluated.record` must re-derive: `digest(record minus record_digest) ==
  record_digest` (`probe/protocol.py:207-210` semantics, re-derived from the plain mapping; Q3 verifies the
  plain-form equivalence on a golden record before the freeze -- fail-closed if not derivable).
- R-GATE: `gate/decision{passed: true}` is REFUSED when any cited `gate/check` has `passed: false`.
- R-COMMIT: `story/commit` is REFUSED when the attempt (since its `story/begin`) holds no `proof/verified`
  -- guarded by Q2 (K-NOWORK measurement) before the freeze; fallback form: "no `proof/verified` AND no
  `probe/evaluated`".
These rules also back-apply to format 3 READS as classified stricter findings (sec. 6).

### 4.9 Failure codes (V21-57, default keep)

f4's `failure/observed` code set = the 22 `FailureCode` members at v2.2.0, as a LITERAL frozenset
`FORMAT_4_CODES` (M4 fix). V21-57 default keep = no 23rd code. If the owner reverses at this freeze, the
new ENVIRONMENT+NOT_RETRYABLE code (PROBE_LIMIT family) enters `FORMAT_4_CODES` and the enum, and formats
1-3 never admit it (their sets are pinned, sec. 4.10).

### 4.10 Vocabulary and code-set pinning (sealed-reader protection; M4)

- `event.py`: `VOCABULARY` becomes the literal frozenset of the 29 v2.2.0 names (`V3_VOCABULARY`), used by
  the format 1-3 readers; a test asserts it equals the enum at the 2.2.0 member list. format4 defines its
  own `VOCABULARY4` = the live enum (31 names).
- `format3.py`: `_failure_schema` pins `FORMAT_3_CODES` (the 22 literals) instead of the live enum.
- Consequence pinned by test: a format <= 3 journal carrying an IGNORABLE event named
  `provider/attestation` or `story/completed` is still SKIPPED (as 2.2.0 skipped it), not refused -- the
  2.2.0 reader behavior is byte-stable against the enum growth (this is why the pin exists).

---

## 5. Reader and writer -- NEW `aisef2/journal/format4.py`

- `FORMAT = 4`; `KNOWN_FORMATS = (1, 2, 3, 4)`.
- `SCHEMAS` = f3's pattern: formats 1-3 kinds by their own validators where unchanged; the sec. 4 deltas
  re-declared; the two new kinds added. `_RULES` = f2/f3 rules for non-lifecycle kinds, PLUS the table
  (sec. 3) as the ONE story-lifecycle rule, PLUS R-SEALED/R-GATE/R-COMMIT/R-SEGMENT/R-CLOSED.
- `reconstruct(text)`: format 1-3 inputs DELEGATE to `format3.reconstruct` UNCHANGED (CR-1); format 4 by
  this module; anything else refused by number, never guessed (FMT3-5 pattern). Test FMT4-3 = CT-2:
  identical outcomes to `format3.reconstruct` on all 10 committed fixtures and the generated f1-f3 journals.
- `JournalWriter4`: the P3 discipline verbatim (M6): no update/delete verb, seq == index at four layers,
  validate + projection pre-check before a byte, fsync every append, truncate-and-poison on a failed write,
  never extends a journal of another format. It is a sibling module in the house pattern; the sealed
  triplicates are NOT refactored (FMT3-7; ponytail: the lazy diff here is the copy, not a shared base class
  threaded through three sealed files).
- Production flip: `RunScope.begin` constructs `JournalWriter4` and declares `{journal_format: 4, run_id,
  kernel_digest, signer[, bundle_digest]}` -- a hunk in `runtime/run_scope.py:123-125` owned by
  L2-ACCOUNTING (M12), landed in the SAME capability batch as E2/E4 (the required reservation/segment
  fields make the flip and the emission sites atomic).
- `runtime/repair.py` (L2-ACCOUNTING): closers for a format-4 journal are appended UNDER FORMAT 4 (CR-2:
  repair appends only closers of the journal's own declared format); the f4 closer schemas are f2's
  synthetic rules unchanged, `segment: null` per R-SEGMENT.

---

## 6. Compatibility, per event kind (the COMPAT-MATRIX bound, stated as the charter demands)

| Kind(s) | 2.2.0 readers | Contract class |
|---|---|---|
| Every format 1/2/3 journal, all 29 kinds | Read by the same code paths, delegation unchanged; fold of every projection over formats <= 3 equals 2.2.0's (J7) | MUST-READ-UNCHANGED |
| `proof/verified`, `tests/adequacy`, `provider/request` IN FORMAT-3 JOURNALS the kernel could never write (non-ACTIVE attempt; unsealed cited record; passed-over-failed decision; commit with no proof) | Now refused at reconstruct instead of (only, or never) at fold | Classified stricter finding under CR-4 (#11, V21-10); NOT a migration -- no kernel-written 2.2 journal contains these (M3), pinned by the equivalence corpus (T10) |
| `run/begin` f4 fields; `reservation`; `segment`; `audit`; `base`; `provider/attestation`; `story/completed` | A 2.2.0 reader refuses the WHOLE journal explicitly and loudly ("none of the formats this reader knows", `format3.py:313-314`) and never misreads it | NEW-ONLY (CR-3); no migration exists or is owed -- the artifact did not exist in 2.2 |
| Ignorable unknown types named like the new kinds inside format <= 3 journals | Still skipped (sec. 4.10 pin) | MUST-READ-UNCHANGED (behavior preserved BY the pin) |
| Projection folds (StoryState v3, TerminalState v2) | Old cache rows are discarded, never migrated (`fold.resume` version rule -- existing mechanism) | VERSIONED (J7's own rule) |

Per-kind statement required by the task: every format <= 3 kind is "2.2.0 readers keep working"; every new
kind/field is NEW-ONLY behind the format number, which is itself the versioned discriminator -- no kind
needs a data migration, and none is performed (CR-2: a journal is never migrated or re-declared).

---

## 7. FREEZE CONTENT -- exactly what consumers may rely on from C-1

Frozen (the consumers E2/E4, E1, C7, C5, G6, C3b may build against these and nothing else):
1. `aisef2/journal/transitions.py` public API: `STORY_STATES`, `STORY`, `WITHIN`, `RUN`, `symbol_of`,
   `TABLE_DIGEST` -- names, value shapes, and the table semantics of sec. 3.1.
2. `aisef2/journal/format4.py`: `FORMAT == 4`, `KNOWN_FORMATS`, `SCHEMAS` key sets + field kinds + rules of
   sec. 4 (including R-SEALED, R-GATE, R-COMMIT, R-SEGMENT, R-CLOSED), `reconstruct` delegation behavior,
   `JournalWriter4` discipline and constructor signature (path, clock).
3. The two new `EventType` values: `"provider/attestation"`, `"story/completed"`.
4. The pins: `V3_VOCABULARY` (29 literals), `FORMAT_3_CODES` (22 literals), `FORMAT_4_CODES` (22 literals,
   V21-57 keep).
5. `run/begin` format-4 payload key set `{journal_format, run_id, kernel_digest, signer[, bundle_digest]}`.
6. Projection versions: StoryState 3, TerminalState 2, Budgets 2 (unchanged), and the J7 equality bound.
NOT frozen (may change without an amendment): error-message texts, module-internal helper names, field
ORDER (storage is canonical JSON -- order is not observable), test file internals, the f3 adapter's shape.

Owner decisions carried AT this freeze (plan sec. 7 package #1 item 5), each with its default:
| Decision | Default | Effect if reversed |
|---|---|---|
| V21-57 (new ENVIRONMENT+NOT_RETRYABLE code) | KEEP (no new code) | +1 literal in `FORMAT_4_CODES` + enum; f1-f3 unaffected (pinned) |
| #11/V21-10 adversarial tightenings on format-3 READS | ACCEPT as classified stricter findings (CR-4 clause); no ledger entry | the tightening stays f4-only; f3 keeps the reconstruct/fold asymmetry as a declared limitation |
| `arch/enums.py` hunk ownership for the 2 new members (M12 gap) | the hunk rides L2-SIGN's W2a `event.py`-adjacent merge window; integrator records the single-writer exception | L2-JOURNAL granted a scoped exception instead |

---

## 8. Fault-matrix sketch for the transition table (`tests/v2/test_v23_transitions.py`, `test_v23_format4.py`)

Injection: hand-built `Event` sequences through `JournalWriter4` (append site), through `format4.reconstruct`
(decode site), and through `fold(StoryState3)` -- EVERY row must refuse at ALL THREE sites (that is the
theorem E6 buys; today T1/T2 pass two of three, M2).

| # | State | Event | Expected refusal |
|---|---|---|---|
| T1 | BEGIN (un-admitted) | proof/verified | refused at append AND reconstruct AND fold (#11's named negative) |
| T2 | BEGIN | tests/adequacy | same three-site refusal |
| T3 | BEGIN | provider/request | refused (today: writer-validator silent, projection refuses -- M1) |
| T4 | BEGIN_REFUSED | story/admitted (again) | refused: one admission per attempt |
| T5 | ACTIVE | story/begin | refused: no second begin of an open attempt |
| T6 | ENDED_COMMIT | story/begin | refused: only ENDED_RETRY may begin again |
| T7 | DECIDED_COMMIT | story/end | refused: dispose first |
| T8 | ENDED_ROLLBACK | story/completed | refused: marker only on ENDED_COMMIT; also T8b duplicate marker refused |
| T9 | any | gate/decision{true} citing a failed check | refused (R-GATE) |
| T10 | -- | EXHAUSTIVE oracle: for every (state, symbol) pair, format4 validator verdict == StoryState v3 verdict; and for every kernel-producible sequence (golden corpus: the E5 fault-matrix journals F1-F25/G1-G2 of test_v23_story_lifecycle + the p6 scenarios + the 10 committed fixtures), format3-with-table == format3-at-2.2.0, event for event | zero divergences |
| T11 | -- | proof/verified citing a record with a wrong `record_digest` | refused (R-SEALED); red-before: passes key-presence today |
| T12 | -- | story/commit in an attempt with no proof | refused (R-COMMIT; form per Q2) |
| T13 | -- | run/end with an unanswered provider/request | refused (R-CLOSED); the E5 interrupt path (closers first) still ends cleanly |
| T14 | -- | f4 provider/result COMPLETED with segment null / synthetic with segment non-null | refused (R-SEGMENT) |
| T15 | -- | f3 journal with ignorable "provider/attestation" | still SKIPPED (sec. 4.10 pin); red-before: would flip to refused without the pin |
| T16 | -- | FMT4-3 / CT-2: f4 reader == f3 reader on every f1-f3 fixture and generated journal | identical outcomes |
| T17 | -- | fold oracle (`oracle_problems`) for StoryState v3 and TerminalState v2 over the golden corpus | incremental == from-scratch |

---

## 9. File ownership and the single-writer schedule

L2-JOURNAL edits (W2b; only these):
| File | Edit |
|---|---|
| NEW `aisef2/journal/transitions.py` | the table (sec. 3) |
| NEW `aisef2/journal/format4.py` | schemas, rules, reader, writer (sec. 4-5) |
| `aisef2/journal/event.py` | `V3_VOCABULARY` pin only; lands AFTER the L2-SIGN merge of event.py (plan sec. 3 item 6 [F]) |
| `aisef2/journal/format3.py` | `FORMAT_3_CODES` pin; table-derived lifecycle rules; V21-10/R-SEALED/R-GATE/R-COMMIT back-application (sec. 6 bound) |
| `aisef2/journal/projections/story_state.py` | version 3, keyed off the table |
| `aisef2/journal/projections/terminal_state.py` | version 2, keyed off the table |
| `aisef2/journal/projections/{failure_owner,retry_target,qualification_counters}.py` | owned; expected NO edit (declared so the diff reviewer flags any) |
| `aisef2/orchestrate/quality.py` | `payload()` only: the `audit` field (#93) |
| NEW `tests/v2/test_v23_transitions.py`, `tests/v2/test_v23_format4.py`, fixtures `tests/v2/fixtures/journal/*f4*.jsonl` | sec. 8 |
| `aisef2/journal/{format2,writer,compat}.py` | owned; NO edit (sealed; writer.py is L4-PARALLEL's at W4a) |

Hunks that are NOT L2-JOURNAL's (requested from their owners; the C-1 freeze is their contract):
| File | Owner lane | Hunk |
|---|---|---|
| `aisef2/arch/enums.py` | NONE in W2 (M12 gap) -- see owner decision table sec. 7 | `EventType` += `PROVIDER_ATTESTATION`, `STORY_COMPLETED` |
| `aisef2/runtime/run_scope.py:123-125` | L2-ACCOUNTING (W2b) | JournalWriter4 flip + f4 run/begin payload |
| `aisef2/runtime/repair.py` | L2-ACCOUNTING | f4 closers (sec. 5) |
| `aisef2/orchestrate/story_runner.py` | L2-ACCOUNTING (E2, #39b window) | `reservation` on provider/request; `segment` on provider/result |
| `aisef2/app/client.py` | L2-ACCOUNTING (then C8) | segment accounting source |
| `aisef2/app/run.py` | L2-RECORD (E7) / L4-RESUME (G6) | `story/completed` emission at finalize (W4); run.py:693 unchanged now (M7) |
| `aisef2/journal/projections/budgets.py` | L2-ACCOUNTING | expected NO edit (sec. 4.2) |

Batch rule (LO discipline, CLAUDE.md): `transitions.py` + `format4.py` + tests can land green WITHOUT the
flip (format 4 not yet production-wired); the flip + E2/E4 emission + repair closers land as ONE capability
batch (CORE-2, week 15-21/12) with ONE integration measurement.

## 10. Kill-test plan -- F5 qualification of the touched targets (KERNEL-COUPLING-01)

- Every `aisef2/` byte above changes the kernel digest => the batch's F5 targeted qualification: every
  mutation target in `journal/{event,format3}.py`, `projections/{story_state,terminal_state}.py`,
  `orchestrate/quality.py` (payload) is re-MEASURED or VERIFIED_REUSE by the engine's own derivation --
  never hand-waved; 0 UNRESOLVED; known-bad still FAIL.
- NEW targets registered for `journal/transitions.py` (table lookups, `symbol_of`) and `journal/format4.py`
  (each rule R-*, the reader delegation, the writer's truncate-and-poison), with kill files
  `tests/v2/test_v23_transitions.py` and `tests/v2/test_v23_format4.py` -- each new rule has a mutant class
  that only its T-row kills (e.g. drop a STORY row -> T5/T6; invert R-GATE -> T9; skip seal re-derivation
  -> T11; drop the delegation -> T16).
- Dependent tier: `event.py`/`format3.py` sit in the static closure of most kill files; the fan-out is
  computed by the F5 engine (I2), not estimated here; it is paid ONCE at the CORE-2 batch measurement,
  which is why the flip is batched with E2/E4 (sec. 9).
- Pre-freeze cost flag for the owner: this batch's fan-out will rival E5's (journal is imported by
  everything); the execution-order lever (plan sec. 5a) should be signed before CORE-2 measures.

## 11. Declared limitations (written into the format4 docstring and this design)

- L1. The chain is still unkeyed until A2 integration lands; `signer` in `run/begin` is a declaration the
  verifier binds LATER (W2c) -- format 4 alone does not make a run authentic.
- L2. `reservation` is owner-typed DATA; nothing in the journal layer enforces a monetary cap (that is C2/E2
  lane logic). The journal guarantees only that the reservation existed before dispatch and is tamper-evident.
- L3. `segment` seals the LOCAL stream bytes the result accounted; it is not an attestation of what the
  provider actually served (that is C7's drift problem, and even C7 only samples).
- L4. Format <= 2 journals keep their own sealed rules entirely; the table governs the story-lifecycle rules
  of formats 3 (read-side, equivalence-bounded) and 4 only. The f2 resource/tool rules are reused, not re-derived.
- L5. The cache-row seal ceiling (`fold.py` docstring) is unchanged: gates still fold from scratch.
- L6. `TABLE_DIGEST` pins values, not meaning: a semantically wrong row that both writer and projection share
  is consistent and wrong together -- the golden corpus (T10) is the only check against that, and it covers
  kernel-producible sequences, not all 13 x 31 cells' real-world meaning.
- L7. R-COMMIT (and the rest of V21-10) is defense in depth against hand-built journals; it adds no guarantee
  about the kernel, which already cannot write the negatives (M3).

## 12. Open questions for the freeze (each with its default; STOP only where marked)

- **Q1 (integrator ruling needed; blocks the enums hunk, not the design):** owner of the two-line
  `arch/enums.py` EventType addition (M12). Default: rides L2-SIGN's W2a window, integrator logs the exception.
- **Q2 (measure before freeze):** does the K-NOWORK/ORCH-4 golden path commit with zero `proof/verified`
  in the attempt? If yes, R-COMMIT takes the guarded form (sec. 4.8). One offline run of the p6 doubles answers it.
- **Q3 (measure before freeze):** `digest(plain(record) minus record_digest) == record_digest` on a golden
  sealed ProbeRecord (plain-form equivalence of `content_of`). If not derivable, R-SEALED falls back to
  refusing records whose digest CANNOT be re-derived (fail-closed), and V21-10 notes the gap.
- **Q4:** `bundle_digest` in f4 `run/begin`: required, optional (default), or absent until G6's W4 design.
  RunScope does not currently receive it; required would add an L2-ACCOUNTING plumbing hunk.
- **Q5 (schedule risk, pacing item):** `signer` required => A2 primitives (W2a) MUST merge before the flip.
  If A2 slips past CORE-2, choose: slip the flip (default) or freeze `signer` as optional-until-A2 with a
  dated amendment (worse: violates CR-7's spirit).
- **Q6:** V21-57 -- confirm default keep at this freeze (owner package #1 item 5).
- **Q7:** ratify the f3 adversarial tightenings as CR-4 classified stricter findings (default) or keep them
  f4-only (then #11's reconstruct-refusal acceptance is met only for f4 and the checklist row needs an
  owner-accepted narrowing note).
- **Q8 (consumer sign-off at freeze):** C7 confirms the `provider/attestation` envelope (sec. 4.4) and E2/E4
  confirm `reservation`/`segment` key sets (sec. 4.2-4.3) BEFORE the freeze seals them -- a required-field
  regret afterwards is a format bump v2.3 does not have.
- **Q9:** does G6 also need a run-level completion marker (run closed cleanly, all stories accounted), or is
  R-CLOSED + `run/end` sufficient (default: sufficient; terminal_state already distinguishes ENDED/ABANDONED).
- **Q10:** `story/completed` emission on resumed runs (a resumed run re-marks reused stories or cites the
  predecessor?) -- G6's W4 design; the schema here admits both (marker cites this run's `story/commit` only,
  so reuse-without-replay in a NEW run journals its own admission trail instead). Default: no marker without
  a same-run commit.

---

## 13. Pre-freeze measurements and freeze-candidate status (appended 2026-11-26)

The two "measure before freeze" questions are now MEASURED; nothing above this line was edited.

- **Q2 = NO zero-proof commit on the golden path => R-COMMIT takes the STRICT form of sec. 4.8.** The K-NOWORK
  no-developer-work path (the one suspected zero-proof committer) commits WITH `proof/verified`: every obligation
  is proved at the candidate by both parties and again post-merge — `tests/v2/test_c2_k_nowork_001.py`
  `assertNoDeveloperWork` pins `[(c, True, "SATISFIED", parent)] * 2` per criterion and `5 * len(criteria)`
  `probe/evaluated` events. The only zero-`proof/verified` case in that family (case D, PRECONDITION_BROKEN)
  ROLLS BACK and never reaches `story/commit`. The fallback form ("no `proof/verified` AND no `probe/evaluated`")
  is therefore NOT taken.
- **Q3 = plain-form re-derivation HOLDS => R-SEALED takes its primary form.** Measured on golden sealed
  ProbeRecords of all three result shapes (`Executed`, `Executed` + `IndeterminateReason`, `Unrunnable`):
  `digest({k: v for k, v in plain(record).items() if k != "record_digest"}) == record_digest` in every case
  (script run 2026-11-26; `probe/protocol.py` seals with `digest(content_of(self, without="record_digest"))`
  and `content_of` is itself plain-form, so the journaled mapping re-derives byte-for-byte).
- **Q5 pacing prerequisite met:** the A2 primitives merged 2026-11-26 (`aisef2/journal/sign.py`,
  `sign.fingerprint` available to L2-ACCOUNTING) — the flip no longer waits on W2a; the default order stands.

**Freeze-candidate status:** with Q2/Q3 measured and Q5's prerequisite landed, every remaining open question
(Q1, Q4, Q6-Q10) carries a stated default and none is marked STOP. This document at its commit digest is the
C-1 freeze candidate; the freeze itself is an owner act (owner package #1, decision 5 names FORMAT-4 the highest
design-freeze priority but "does not automatically certify C-1"). No owner signature is synthesized here.
