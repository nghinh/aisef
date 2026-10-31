# V2.1 — interim handoff set (prepared while the campaign runs)

**This is not a release decision and records no acceptance.** The owner's decision (2026-10-30) is: run the
current campaign to completion, then hand off a go/no-go on the concrete final result set. No release now; the
gate is **not** changed to "all non-BUG survivors accepted"; **no owner acceptance of A-03 or any survivor is
recorded.** Standing limits hold: no push / tag / publish / paid provider / `APPROVE.sh` / self-acceptance /
reseal; workers, watchdog, snapshot and queue order untouched; no next campaign self-opened.

Candidate frozen at **8c7bdb44** (product tree `5f34a3f3` = `fce3d7b7`). Prepared 2026-10-30 ~20:20 +07.

---

## 1. Status — CAMPAIGN COMPLETE 2026-10-31 ~16:00 +07 (elapsed ~57.6 h)
- **90 / 90 targets measured · 0 missing · 0 infra / timeout / not-run** (reconciled: queue.txt ∩ records = all
  90; every claim carries a `done` marker; both workers wrote `.finished`; no `mutation.py` alive).
- **Mutants: 3593 · KILLED 3500 · SURVIVED 93 · kill rate 97.41% · 62 of 90 targets fully killed.**
- **Both Group-A measurement blockers done at head, 0 survivors:** A-01 `cli.py::_parser` **31/31 killed**; A-02
  `bundle_cli.py::_create` **3/3 killed**, with **all 5 of its T0 kill-tests PASSED this run — including
  `test_v21_continue_integrity.py` (PASS, 212.87 s)**, so the earlier observed T0 FAIL did not reproduce. **A-03
  soundness gate still applies to both** (a clean run is a clean environment, not closure of the async-SIGKILL window).
- **`campaign.done` written** (operator drain marker, after both `.finished` + all 90 measured + no `mutation.py`
  alive — asserts completion of measurement, NOT any verdict or acceptance). Workers imported to
  `mutation-workers/sw-w0`,`sw-w1`; results mirrored to `campaign-supp/results/`.
- **Handoff pipeline COMPLETE — see [GO-NO-GO.md](GO-NO-GO.md).** Rebuilt the 614-target `MUTATION.json`+`SUMMARY`
  at FINAL_HEAD 8c7bdb44 (90 measured + 524 reused, 0 MISSING, MUTATION_VERDICT **FAIL** on 7 unaudited survivors).
  Gates at head (true verdicts, nothing fixed to green): ruff **FAIL** (1 F541 in a helper), v2-gate **FAIL** (no
  2.1 RC/version/decision — release not prepared), macOS unit suite **FAIL** (19 = 17 record-currency meta-tests
  RED-by-design + 1 env + 1 macOS-TMPDIR artifact; **0 confirmed product defects**; `v1_evidence_guard` PASS).
  Linux/Windows suite not run (CI = push-gated). Daemons wound down on `campaign.done`; all exited clean.

## 2. Risk method (owner correction 2026-10-30)
Risk is classified by **possible consequence × strength of evidence**, never by the BUG/TEST-GAP/EQUIV label
alone. A survivor labelled "string emptied" can sit in a high-consequence area (a verdict, a secret, an access
boundary); a survivor labelled "And swapped" can sit in a path that by design changes nothing a verdict
depends on. Each row below states (a) the **consequence area** — what would be affected if the original had
the defect the mutant simulates — and (b) the **evidence** that bounds the *actual* effect, with one of:
**VERIFIED-bounded** (consumer read, effect shown), **LIGHT** (area reasoned, full read pending),
**UNVERIFIED**. Nothing here asserts "the product is correct" — only "no original-code defect confirmed within
the tested scope," and open rows stay open.

## 3. Coverage over all 614 targets (set-verified; `COVERAGE-614-TABLE.md`)
| part | n | status now |
|---|---:|---|
| **new_measure (campaign scope)** = MISSING(62) ∪ closure-affected | **90** | **90 measured-at-head · 0 not yet qualified** (0 infra/timeout) — complete |
| still-valid **measured-at-head** | **162** | valid without this campaign |
| still-valid **reused** (mechanical-proof) | **362** | valid without this campaign |
| **total** | **614** | 524 valid independent of the campaign + 90 in scope |

**All 90 scope targets now have a sound head measurement** (0 infra/timeout/not-run). Their MISSING/closure-affected
status retires on these measurements — except that A-03-gated targets' *soundness* still depends on the owner's
A-03 decision (a result exists for each; whether it is accepted as sound is the A-03 call).

## 4. Survivor ledger — FINAL: 90 finished targets, 93 survivors (62 of the 90 targets fully killed, 0 survivors)
All 93 survivors are bucketed below by consequence area; the two groups not expanded in §4a–§4e (`catalog`
capability fields and `diagnostics._parsed`) are the §5 TEST-GAP rows — added here for completeness so every
survivor sits in a consequence bucket. **No survivor is a CONFIRMED defect of a verdict, an obligation, data, a
secret, an access boundary, or evidence integrity.** The verdict function `run.py::delivery` and the A-01 parser
`cli.py::_parser` are both fully killed (0 survivors).
Grouped by the consequence area the site sits in; each row's **evidence** bounds the actual effect. **21 of the
41 targets are fully killed, 0 survivors**, including the delivery-verdict function `run.py::delivery` (46 mut)
and **the A-01 blocker `cli.py::_parser` (31/31)** — plus `adapters.Reviewer.review`/`._model`,
`client.read_session`/`.Budget.spend`/`.Budget.__init__`/`.Budget.reached`/`.wait_within`/`.environment`,
`run.py::layers_of`/`productproof`/`runspec_of`/`story_where`/`check_git`, `review_verify.preserve`,
`settings.endpoint_problem`, `diagnostics.Sink.report`, `runtime/process_range.ProcessRange.__init__`,
`probe/file_artifact GREP_WORKER/grep`. The all-killed verdict function independently corroborates §4a.

### 4a. Verdict / delivery path — area HIGH, all VERIFIED-bounded to no verdict change
- **`app/verify.py::verify` — 12 survivors.** `verify` re-derives the delivery verdict. Checked: the verdict
  comes from `R.delivery(project, events, outcomes, stop, errors)` (run.py:373-389), which reads `errors` by
  **`len()`/truthiness only** and never by key. So the five **L201** mutants (drop `"story"`/`"error"` keys,
  empty those keys, empty the value) leave each error a non-empty list element → count preserved → **verdict
  unchanged**. The others are message text (L103/L117/L152 `')'`, L134 `' the run printed'`, L111 `'no '`),
  a transparency **note** (L197 accepted-unaccounted — the fact stays in `continues.accepted_unaccounted`), and
  **order** (L180 `sorted()->list()`, whose `if differ:` still fires). **Evidence: VERIFIED-bounded — no
  surviving mutant changes the verdict or a recorded problem; only message/note/order text.**
- **`orchestrate/story_runner.py::_attempt` — 4 (S-01..S-04).** S-01/S-02 (PRESERVE→INTRODUCE/VERIFY) proven
  verdict- and evidence-neutral at `MeasurementPoint.CANDIDATE` (role-agnostic routing; role not journaled, not
  on `Proof`); developer regression still caught role-independently. S-03/S-04 = `_EscapedRange` journal label,
  not an identity/release key. **Evidence: VERIFIED-bounded.**
- **`app/run.py::execute` — 10 (S-14..S-23).** Record-serialization + refusal-message text: `--parent`/lineage
  message strings (condition and raise unchanged), STARTED/MANIFEST trailing newline and key order (verify is
  content-sha-faithful; the MANIFEST anchor re-sorts → invariant), the `stage` breadcrumb (overwritten on the
  normal path, read KeyError-safe). **Evidence: VERIFIED-bounded — verdict/anchor unaffected.**
- **`app/review_verify.py::reproducer_contract` — 7 (new this milestone).** Turns a finding's reproducer into a
  MUST_HOLD contract *or* a refusal string; both callers (`verify` L193, `anchor` L294) branch only on
  `isinstance(c, str)` → `UNVERIFIABLE`/`UNANCHORED`, never on the message content, and the id/rationale "no
  control path reads" (docstring L145-146). **5 survivors are refusal-MESSAGE text/order** (L160/L165/L172
  strings, L172 `')'`, L172 `sorted(product_roots)->list`) — each guard (L159/L164/L171) is untouched and still
  returns the refusal, so the refuse/accept decision is unchanged. **Evidence: VERIFIED-bounded cosmetic.** **2
  survivors are the L180 `except (ContractError, ValueError, TypeError)` tuple with element 0 / element 2
  dropped** — if `BehaviorContract.create()` raised that type it would propagate instead of being turned into a
  graceful refusal. Checked: this can only turn *graceful UNVERIFIABLE-with-reason* into *propagated error → story
  REFUSED, no verdict* (module docstring); it can never make an invalid reproducer into a valid blocking contract
  or flip a verdict to PASS. **Evidence: fail-safe direction VERIFIED-bounded; the error path itself is a
  TEST-GAP (uncovered) — kept open in §5.** (Kill set includes `test_v21_continue_integrity.py` → A-03-gated.)
- **`app/review_verify.py::verify` — 3 (new this milestone).** This is the verdict-bearing reproducer run
  (returns `Verification` with status CONFIRMED / NOT_REPRODUCED / INDETERMINATE / UNVERIFIABLE). **L225 and L234
  are the reason-TEXT of the CONFIRMED and INDETERMINATE returns** (`' is said to demand'`, `'): neither confirmed
  nor ruled out'`) — the status enum and `v.value` are unchanged; downstream branches on the status, not the
  prose. **Evidence: VERIFIED-bounded cosmetic — the verdict status is intact.** **L204 drops `RecursionError`
  from `except (OverflowError, RecursionError)`** guarding `observation_class(...)`; if it raised RecursionError it
  would propagate instead of returning `no_meaning` (UNVERIFIABLE). Same fail-safe shape as `reproducer_contract`:
  it can only turn graceful UNVERIFIABLE → propagated error / story REFUSED; it **cannot** produce a wrong
  CONFIRMED or NOT_REPRODUCED. **Evidence: fail-safe VERIFIED-bounded; the error path is a TEST-GAP (§5).**
- **`app/verify.py::_runspec_problems` — 1 (new).** L72 `')'` dropped from the problem message
  `(re-derived {…}, journaled {…})`. The guard at L70 (`derived != spec["runspec_hash"]`) is untouched and still
  returns a non-empty problem list, which is how the caller detects the problem; only the message punctuation
  changes. **Evidence: VERIFIED-bounded cosmetic — the runspec-mismatch problem is still reported.**
- **`app/run.py::evidence_manifest` — 1 (new this milestone).** L432 `sorted()->list()` on
  `glob("*.json")` of the diagnostics artifact dir. The manifest is a **dict keyed by relative path** (L433-434),
  and the evidence anchor is `_sha(json.dumps(manifest, sort_keys=True, …))` (`anchor_of`, L447) — **anchor is
  invariant to the files' insertion order**, and dict equality on re-derivation is order-independent. Same shape
  as the already-closed S-21/S-22 sort-key survivors. **Evidence: VERIFIED-bounded — the manifest content and the
  evidence anchor are identical; only the transient glob insertion order of a canonically re-sorted dict changes.
  Not an evidence-integrity defect.**
- **`app/run.py::unfinished` — 1 (new this milestone).** L410 `sorted()->list()` on the list of refused story
  ids. Consumed at `verify.py:183` → `refused` → `errors` (L201) → `R.delivery(…, errors)`, which reads `errors`
  by `len()`/truthiness only (run.py:387) and is re-derived at verify time (not stored ordered). **Evidence:
  VERIFIED-bounded — the order of refused stories changes no verdict and no stored evidence.**

### 4b. Access / secrets / scope — area HIGH, enforcement VERIFIED intact; report fields only
- **`app/cli.py::run` — 2.** L88 `'aisef-confine-'` emptied is only the **prefix of a `TemporaryDirectory`
  name** (cli.py:88); `confine.measure(...)` runs in that dir regardless → **confinement enforcement intact**,
  prefix cosmetic. L108 `': '` = a readiness-print message separator. **Evidence: VERIFIED-bounded.**
- **`app/run.py::check_repository` — 1 (new this milestone).** L237 `'aisef-check-'` emptied — the **prefix of a
  `TemporaryDirectory` name** again (same class as `cli.py::run` L88); the repo is still cloned into that dir and
  checked. **Evidence: VERIFIED-bounded cosmetic — behaviour intact, only the temp-dir name prefix changes.**
- **`app/client.py::session` — 3.** L299 entry drop = the result's `redacted` report field; `redact(log,
  secrets)` runs unconditionally at client.py:297 → **redaction enforcement intact**, only the report of it
  changes. L302 `'left_range_gone'` key drop/empty = the scope-disposal *report*; `_release_session(r)` runs at
  client.py:295 → **disposal intact**, only its naming in the result changes. **Evidence: VERIFIED-bounded to
  report-field transparency, not enforcement.**
- **`app/diagnostics.py::access_of` — 3 (new this milestone).** L103 empties the dummy command `["true"]` and the
  workspace path parts `"work"`/`"ws"` used to compute who can read the diagnostics folder. The result is stored
  as the Sink's **reported label only** (`diagnostics_access`/`access`, diagnostics.py L191/L231). Checked:
  secret **redaction is unconditional** (`review_verify.redacted(doc, self._forms)` at L194, `_forms` built from
  the secrets in `__init__`, independent of the access level) and artifact permissions come from `_keep`'s
  `O_EXCL`/`0o700` — so the access level gates **neither** redaction **nor** permissions. The guarded failure path
  returns `NOT_INSPECTED` (the explicitly *weaker* claim, L110), so a mutated value can only weaken/alter the
  label, never over-state protection. **Evidence: VERIFIED-bounded to a report-field; enforcement independent.**

### 4c. Diagnostics — area by design NON-VERDICT
- **`app/diagnostics.py::artifact_problems` — 8** (L315 `And` swapped, L286/L303 element drop, L311/L312/L320
  strings). Diagnostics are **operator observations that no verdict depends on** (verify.py:175 "no verdict";
  the L320 string itself says "no verdict depends on it"). The `And`-swap can change *which* observation is
  reported, not any verdict. **Evidence: LIGHT — non-verdict by design; the exact observation-accuracy effect
  of the `And`-swap not fully read.**
- **`app/diagnostics.py::Sink._document` — 2** (L196 `True->False`, L197 `False->True`). Diagnostics-sink
  recording booleans. **Evidence: LIGHT — non-verdict area; the two flips' effect on recorded diagnostic flags
  not fully read.**
- **`app/diagnostics.py::Sink._keep` — 3 (new this milestone).** Writes a diagnostic artifact create-only. **L216
  message string** of the `FileExistsError` emptied — the guard `if final.exists()` (L215) and the `raise` + the
  `O_WRONLY|O_CREAT|O_EXCL` write (L217) are untouched, so the **"an artifact is never overwritten"
  (INV-MUTATION-AUTHORITY) property holds regardless** — only the message text changes. **L210 trailing `"\n"`
  drop and `sort_keys=True→False`** change how the diagnostic artifact's JSON is serialized; the file is hashed
  into the manifest consistently at write and re-read, so no anchor mismatch arises within a run, and the artifact
  is a non-verdict sink output. **Evidence: VERIFIED-bounded — overwrite-protection intact (safety property
  preserved); the serialization change is non-verdict and self-consistent in the manifest.**
- **`app/diagnostics.py::_identity` — 1 (new).** L257 `sort_keys=True→False` in `json.dumps([story, *record
  values], …)`. The argument is a **list** of (expected) scalars, so `sort_keys` has no effect unless a record
  value is itself a dict. Non-verdict diagnostic identity text. **Evidence: LIGHT — probably EQUIV (no dict keys
  to sort); not upgraded to EQUIV without confirming every record value is scalar. Kept open in §5.**
- **`app/diagnostics.py::tapped` — 1 (new this milestone).** L248 drops entry 2 (`"__doc__"`) from the namespace
  of the dynamically-built probe subclass that taps `observe()` into the sink. The `"observe"` entry (0) was
  killed; dropping `"__doc__"` loses only the wrapper class's docstring, not its behaviour. **Evidence:
  VERIFIED-bounded cosmetic — observe() tap intact, only the generated class's docstring is absent.**
- **`app/diagnostics.py::_parsed` — 1 (detail in §5).** L119 drops `RecursionError` from `except (ValueError,
  RecursionError)` around `json.loads(detail)`. Non-verdict diagnostic detail parsing; fail-safe (deeply nested
  JSON would propagate instead of returning the raw text). **Evidence: TEST-GAP — uncovered error path, §5.**
- **`app/diagnostics.py::Sink.__init__` — 2 (new this milestone).** L140 `tuple(secrets)->list` and L144
  `tuple(dict.fromkeys(…))->list` — `self.secrets` and the redaction forms `self._forms` become lists instead of
  tuples. Both are iterated only (L143 comprehension; `review_verify.redacted(doc, self._forms)` iterates), so
  list vs tuple is behaviourally identical and **redaction is not weakened**. **Evidence: VERIFIED-bounded /
  EQUIV — collection type change on iterated-only internals, no observable difference.**

### 4d. Probe / cost — area moderate, LIGHT
- **`probe/file_artifact.py::FileArtifactProbe.observe` — 1.** L877 `'grep'` emptied — a probe-kind/label
  string. **Evidence: LIGHT — likely a label, not a selector; not fully read.**
- **`probe/file_artifact.py::grep_facts` — 7** (target 10, record flushing from scratch). L502/L477/L518 =
  worker-ended refusal/diagnostic message text (`'the worker '`, `' before it gave its result'`, the
  not-retried-here explanation, `')'` punctuation); L517 element 0/2 dropped = items in the probe's grep output.
  Same probe/non-verdict class as `observe` — operator observation, no verdict depends on it. **Evidence: LIGHT
  — message text clearly cosmetic; the L517 element-drops' effect on reported grep facts not fully read, open.**
- **`probe/file_artifact.py::_worker_facts` — 1** (new this heartbeat). L423 `')'` emptied — a `)` dropped from
  the embedded grep-worker source template string. Same probe family; `_worker_facts` validates/shapes a
  subprocess worker's returned facts (BAD_RESULT guarding), which feed operator observations, not a verdict.
  **Evidence: LIGHT — a punctuation drop in the worker-source template; it survived, so the exact embedded
  program text is not covered by a real-subprocess kill test. Probe/non-verdict; kept open, no verdict/data/
  secret/access consequence.**
- **`probe/file_artifact.py::_stopped` — 1 (new this milestone).** L550 — a char in the watchdog-stop message
  (the `{timeout_s:g}` display format). `_stopped` builds the operator message for a probe watchdog timeout; the
  message itself states "this is a stop of the harness and never a verdict." **Evidence: VERIFIED-bounded — a
  display-format char in a self-declared non-verdict stop message.**
- **`app/adapters.py::Reviewer._ocr` — 9 (S-05..S-13).** Cost/token dict shape (`reasoning` folds into the
  CLASSES-fixed totals, defaulted to 0 → cost byte-identical), evidence-list ordering (`required`/`deleted`),
  run-label and coverage-message text, and a `mkdir(parents=…)` robustness flag. **Evidence: VERIFIED-bounded
  for cost/text/order; S-09 (`mkdir` parents) and S-10 (L265 bool) remain open.**
- **`probe/catalog.py::CatalogEntry.capability_version` + `.capability_changes` — 2 + 2 (detail in §5).** L66/L67
  flip `compare=False→True` / `hash=False→True` on two dataclass fields (0/2 killed each). EQUIV in the normal
  path (both default `None` → `None==None`); behaviourally different only when a probe module declares a non-None
  CAPABILITY_VERSION/CHANGES and two entries are compared — and `aisef bundle migrate` reads those field *values*
  directly, not via entry equality. **Evidence: TEST-GAP (zero kill coverage of these field flags), consequence
  LIGHT (probe-catalog entry equality in a capability-versioned edge case; no confirmed approval-carryover
  effect), §5.**

### 4e. Input validation / bundle parse — area HIGH (trust boundary), guard VERIFIED killed
- **`app/bundle.py::shape_problems` — 2** (new this heartbeat). Both survivors are at **L99**, the
  **error-message formatting** continuation of a `raise BundleError(...)` — `')'` dropped from the message
  string and `sorted(s)->list(s)` inside `f" (it holds {sorted(s)})"`. The line only executes when a story
  object has already failed the guard at **L97** (`sorted(s) != ["depends_on","tests"]`); that guard's own
  `sorted()` mutation was **KILLED** separately, so the accept/reject decision is covered and unchanged. The two
  survivors change only the text and key-ordering *inside the rejection message*. **Evidence: VERIFIED-bounded —
  no validation bypass; the malformed bundle is still rejected, only the error string differs.** (Kill set
  includes `test_v21_continue_integrity.py` → A-03-gated for soundness like the others.)
- **`app/bundle_cli.py::_write_new` — 2 (new this milestone).** L997 drops the trailing `"\n"` and flips
  `sort_keys=True→False` when the `aisef bundle` tool **writes a new** bundle file (via `_create`, create-only,
  never overwrites — L993). These change only the serialization of a tool-authored bundle; a bundle is consumed by
  `bundle.load`/`shape_problems` through order/whitespace-independent JSON parsing, and the requirements sha is
  over the requirements file, not the bundle text. **Evidence: VERIFIED-bounded — bundle-tool write formatting;
  the produced bundle parses identically and no stored identity is over the bundle's bytes.**

## 5. Unresolved items (kept open and public — not closed by this handoff)
| id | where | class | why open |
|----|-------|-------|----------|
| S-05, S-06 | `_ocr` L219/L272 `sorted()->list()` | **TEST-GAP** | evidence-list ordering determinism not proven out-of-requirement |
| S-09 | `_ocr` L246 `mkdir(parents=True→False)` | **TEST-GAP** | missing-parent robustness uncovered |
| S-10 | `_ocr` L265 `True→False` | **UNDET** | bool mapping unconfirmed |
| — | `reproducer_contract` L180 `except` drops `ContractError`/`TypeError` | **TEST-GAP** | error path uncovered; consequence fail-safe (refuse/REFUSED, never wrongly block or pass) but the graceful-refusal behaviour is untested |
| — | `review_verify.verify` L204 `except` drops `RecursionError` | **TEST-GAP** | error path uncovered; consequence fail-safe (UNVERIFIABLE→REFUSED, never a wrong CONFIRMED/NOT_REPRODUCED) but untested |
| — | `diagnostics._parsed` L119 `except` drops `RecursionError` | **TEST-GAP** | error path uncovered; non-verdict diagnostic detail parsing; fail-safe (deeply nested JSON would propagate instead of returning raw text) but untested |
| — | `catalog.CatalogEntry.capability_version`/`.capability_changes` L66/L67 `compare=False→True`, `hash=False→True` (0/2 killed each) | **TEST-GAP** | zero kill coverage of these dataclass field flags; EQUIV in the normal path (fields default None → `None==None`), behaviourally different only when a module declares a non-None CAPABILITY_VERSION/CHANGES and two entries are compared; `bundle migrate` reads the field *values* directly, not via entry equality, so no approval-carryover consequence confirmed |
| — | `artifact_problems` L315 `And` swapped (+7) | consequence LIGHT | non-verdict, but observation-accuracy effect unread |
| — | `Sink._document` L196/L197 bool flips | consequence LIGHT | diagnostic-flag effect unread |
| — | `file_artifact.observe` L877 `'grep'` | consequence LIGHT | label-vs-selector unread |
| — | `diagnostics._identity` L257 `sort_keys=True→False` | consequence LIGHT | probably EQUIV (list, no dict keys); non-verdict; not confirmed every record value is scalar |

None is a **confirmed** risk to a verdict, an obligation, data, a secret, access, or evidence integrity — so
none triggers the urgent-report rule. They are open because evidence is LIGHT or the gap is a real test gap,
not because they are known-safe.

## 6. A-03 — `continue_integrity` (owner-decision item; NOT accepted here)
- **Observed, not reproduced:** a single T0 FAIL of `test_v21_continue_integrity.py` on a clean tree, **only for
  `bundle_cli.py::_create`**; `_parser`, `execute` and the ~95 others merely share the kill-test (no observed
  T0 FAIL; `execute` measured clean this run). The external async-SIGKILL "request sent, result/usage not yet
  journaled" window is **not reproduced and not ruled out**; a clean campaign does not close it.
- **Owner options (none applied without explicit approval):** (1) fix — one controlled fault-injection, only if
  a real defect reproduces, batched into the single final fix-window; (2) limit support scope — ship with a
  documented limitation; (3) accept as scoped exception. **Status: OPEN in Group A.**

## 7. Exceptions / decisions that will need the owner at go/no-go
1. **A-03** — pick (1)/(2)/(3) above.
2. **`_parser` (queue #31) and `_create` (#61)** — still ~20 / ~50 positions out; if the campaign ends before
   both are soundly measured at head, decide whether their missing head-mutation evidence is a release blocker
   or a documented limitation (they are A-03-gated for soundness regardless).
3. **A-04** — the release gate + unit suite have **not** been run at 8c7bdb44 on any platform; the full unit
   suite is RED-by-design (19 record-currency meta-tests on the unsealed branch; green only by resealing =
   forbidden). To be run at drain; a RED gate is reported cause-by-cause, never substituted by a release note.
4. **The LIGHT-evidence survivors (§5)** — accept as open limitations, or fund a bounded read to close them.

## 8. What happens at drain (the plan, unchanged)
import each worker → rebuild MUTATION.json + SUMMARY (reuse 162 + 362) → finish the ledger for all 90 →
build + `--check` → run `v2-gate` + unit suite at 8c7bdb44 on macOS and Linux (Windows per policy) → **true
verdict, FAIL/blocker acceptable** → present ONE consolidated go/no-go: the items that actually block release,
the minimal fix for each, the re-measure scope and cost, and the release-or-narrow-scope choice if unfixed.
No next campaign to raise the kill rate. The owner decides on that concrete result set.
