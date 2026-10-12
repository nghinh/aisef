# B-03 round 3, WP usage: `usage.no_progress` and the journal boundary of `--verify`

Branch `v21r3/usage`, base `3dc827b`. Product files: `aisef2/app/usage.py` (`no_progress`), `aisef2/app/verify.py`
(`_projection_refusal`, new; `verify`, a seven-line wiring). Tests: `tests/v2/test_v21_r3_usage_no_progress.py`,
`tests/v2/test_v21_r3_usage_boundary.py`. No existing test was changed.

## 1. The owner's decision (item 4)

> Không phê chuẩn "miền A" chỉ dựa vào tên phương án. Tôi chọn nguyên tắc: Miền hành vi phải bao phủ mọi journal hợp lệ
> mà các đường sản phẩm được hỗ trợ có thể đưa đến `no_progress`, gồm run, continue, verify và import/migrate nếu có.
> Journal không hợp lệ phải được kiểm tra và từ chối ở ranh giới xác định. Đối chiếu nguyên tắc này với hồ sơ
> `mutation/no_progress-13-23.md`. Nếu miền A đáp ứng thì áp dụng và ghi rõ phạm vi. Nếu không, sửa đề xuất theo nguyên
> tắc trên. Không dùng "kernel hiện tại không sinh ra" làm căn cứ duy nhất để loại một đầu vào mà reader vẫn chấp nhận.
> Không xem thử nhiều journal là chứng minh tương đương. Hai mutant phải được kiểm chứng hành vi hoặc có hồ sơ tương đương
> đủ căn cứ, không tính thành KILLED nếu chỉ được audit.

Reading. (a) The function must have a defined, requirement-based answer on every journal a supported path can hand it.
(b) Anything else is refused by a check at a named place, before the function's answer is trusted. (c) "The kernel does
not write it" and "I tried many journals" are not grounds. (d) Each of the two mutants is verified by behaviour, or has
an equivalence record with real grounds; an audit is not a kill.

## 2. What the code shows (each point re-derived; the dossier's claims checked, not copied)

| # | Fact | Where | How checked |
|---|---|---|---|
| F1 | At BASE `no_progress` closes an attempt at `story/retry`, `story/rollback` **and `story/commit`**; each closer appends the sorted failures seen since the previous closer. Mutants 13/23 take `story/commit` out. | `usage.py:130` (BASE) | read; baseline `kill_check` at BASE: 33 mutants, 31 KILLED, **13 and 23 SURVIVED** (`kc-baseline-no_progress-BASE.json`, with the registered kill files) |
| F2 | The kernel's story runner journals one `failure/observed` in an attempt that fails (`_fail`, then retry or rollback citing it) and none in an attempt that commits. `_fail` is the only product writer of `failure/observed`. | `story_runner.py:142-146`, `:329-342`; `git grep FAILURE_OBSERVED -- aisef2` (one writer) | read + grep |
| F3 | The projections **admit** `failure/observed` in any state once the story began, and `story/commit` from ACTIVE: a committed attempt that observed failures is a journal the writer's own authority accepts (INV-A is enforced by nothing but F2's control flow). Nothing of a story can follow its commit (INV-B is enforced). | `story_state.py:10-14`, `:37-39`, `:49-53`; `terminal_state.py:39-52` | enumeration over admitted journals: INV-A is broken in 18,952 of 100,337 (one story, up to 10 events) and in 8,387,736 of 42,579,530 (two stories, up to 10); INV-B in **0** of both |
| F4 | The reader checks schemas, citations, `seq == index`, the chain; it does not fold the projections. `--verify` takes what it reconstructs. At BASE, a chained, schema-valid journal whose story commits twice, or commits with no admission before it, and a record derived from it, is **VERIFIED with delivery PASS**. | `format3.py:266-332`; `verify.py` (BASE) | measured at BASE with the new boundary tests: both cases `VERIFIED`, `delivery_verdict: PASS`, `journal_events` 8 and 10 |
| F5 | `no_progress` has two product callers: `run.py:495` (RUN.json, from the writer's in-memory events) and `verify.py` (BASE `:166`, now `:194`: re-derivation from the journal bytes). No continue, lineage, bundle or repair path calls it. | `git grep no_progress -- aisef2` | grep (callers table, report) |
| F6 | Words of the requirement: function docstring "consecutive **failed** attempts with the same failures ... retries that changed nothing"; module docstring "retries that changed nothing"; `USAGE-2.1.md:86-87` "`no_progress` (retry lặp lại đúng các lỗi cũ — chỉ báo cáo)"; `TRACEABILITY.md:686` P-5.3c "báo các attempt liên tiếp có cùng tập lỗi" (it says attempts, not failed ones); the source sentence (§5.3) is about steps that produce no code change, evidence or hypothesis. A committed attempt merged code: it is progress. | `usage.py` (docstrings), the two docs | read |
| F7 | Domain A ("journals the kernel writes") does **not** satisfy the principle: `--verify` hands the function journals outside A (F3, F4), the reader accepts them, and the dossier's own §6 lists a shape where the original reports a *committed* attempt as a repeated failed one. | dossier §4 "weakest link", §6 | F3 + F4 above |

Where my brief and the code differ: none of substance. The brief's "the likely change is to drop `story/commit`" is
right but not sufficient: carrying a failure observed *between* an outcome and the next `story/begin` into the next
attempt is the same defect in another place (§3, D1).

## 3. The decision

**D1. `no_progress` is defined by attempt, as the kernel defines one.** An attempt is *failed* when it ended in
`story/retry` or `story/rollback`. Its failures are the `failure/observed` its story journaled after the later of the
attempt's `story/begin` and the story's previous outcome, up to the outcome. Rows are the failed attempts' failure sets
(sorted), compared consecutively as before. Consequently:

* a committed attempt is progress and is never reported, whatever failures it observed (nothing follows a commit: INV-B);
* a failure observed after an outcome and before the next `story/begin` is not the next attempt's (it had not begun) and
  is not in any row: the report compares what the retry *reacted to* (what the attempt had observed when it ended) with
  what the next attempt observed;
* a list with no `story/begin` for a story (a unit-test list, not a journal) keeps its old meaning: an outcome starts
  the next attempt. Every existing test of the function stays as it was.

The code: drop `story/commit` from the closers and clear a story's pending failures at its `story/begin`. Three lines.

**D2. `verify` refuses a journal the control projections refuse, before anything is re-derived from it.** After
`format3.reconstruct`, the six projections (`PROJECTIONS`, the writer's `Authority`) are advanced event by event over
the reconstructed events (`_projection_refusal`, `Folder.advance`, the same step the writer's pre-check runs). At the
first refusal verify is REFUTED with a finding that names the projection, the event type and the seq and carries the
projection's own reason, and `events` stays empty exactly as for a journal that does not reconstruct: no outcome,
delivery verdict, ProductProof account, usage or `no_progress` is re-derived from it (`journal_events: 0`).

Where: at the reconstruction step, not in the V2.1 usage branch. Every re-derived value (outcomes, delivery verdict,
ProductProof, spend, `no_progress`) is a function of the same events; the usage branch runs only for V2.1 records, a
2.0.0 record would have slipped past it, and F4's PASS needs no usage account at all.

**Why the projections and not a rule of mine.** They are the authority the writer used on every append. A journal the
kernel's writer could have written is admitted by construction (the reader, projections and writer are byte-identical
between the 2.0.0 release `ca26313` and BASE: `git diff ca26313 3dc827b -- aisef2/journal aisef2/runtime/run_scope.py
aisef2/control aisef2/arch` is empty). I added no verify-only rule: in particular INV-A is **not** made a rule. The
projections admit a committed attempt that observed failures, so the function answers it (D1) rather than the boundary
refusing it.

### Alternatives considered

| | What | Why not |
|---|---|---|
| A | Keep `story/commit` a closer, add INV-A as a verify-only rule ("domain A made true by a check") | invents a journal-validity rule the writer does not have; the owner asked that the function cover the valid journals, and the valid set is the projections'. Also leaves a re-measurement of every consumer of the old answer. |
| B | Only drop `story/commit` (mutant 13 as product) | answers the commit shape but carries a failure journaled after an outcome into the next attempt: the report would call attempt 2 a repeat of attempt 1 when attempt 2 never observed that failure (test `test_a_late_failure_does_not_make_a_different_attempt_look_like_a_repeat`; 59,372 of the 59,650 admitted one-story journals (up to 13 events) where BASE and the new function differ are this class). |
| C | Attach a late failure to the attempt it followed (the projections' attribution: `failure_owner`/`budgets` keep it until the next begin) | defined, but needs lookahead to keep begin-less lists meaning what the existing tests say (a begin pre-scan, or deferred rows), and it changes *which attempt's set* a failure the retry decision never saw is in. Not required by the principle. Left as a decision (§9, D-LATE). |
| D | Put the check in `aisef2/journal` (shared by every reader) | the other readers do not reach `no_progress` and are not this WP's files; one helper, in verify, can be moved when the owner decides they must refuse too (§9, D-READERS). |

## 4. Requirement → test

`tests/v2/test_v21_r3_usage_no_progress.py` (journals written through `Authority(JournalWriter3, PROJECTIONS)`: admitted by
construction; read back with `format3.reconstruct` as `--verify` reads):

| Requirement | Test |
|---|---|
| a committed attempt that observed the failures of the one before is not reported (owner's shape) | `CommittedAttemptIsProgress.test_a_committed_attempt_that_observed_the_failures_before_it_is_not_reported` |
| failed attempts before a commit are still compared; the commit is not one of them | `...test_the_failed_attempts_before_a_commit_are_still_compared_and_the_commit_is_not_one_of_them` |
| commit at once / after a different failure; several failures in the committed attempt; a failure after the commit | `...test_a_commit_after_a_different_failure_or_at_once_reports_nothing`, `...test_several_failures_in_a_committed_attempt_are_nobodys`, `...test_a_failure_after_a_commit_is_nobodys_either` |
| rollback ends a failed attempt; every repeat listed, first names the failures; an attempt with no outcome is not failed | `FailedAttemptsAreCompared` (3 tests) |
| a failure after the outcome (after the outcome event / dispose / end) is not the next attempt's, nor makes a different attempt look like a repeat, nor changes a report when after the last outcome | `FailuresOutsideAnAttempt` (3 tests, 3 places each) |
| a story is compared with itself; the report's order is that of each story's first outcome; another story's begin does not discard pending failures | `StoriesAreCompared` (3 tests) |

`tests/v2/test_v21_r3_usage_boundary.py`:

| Requirement | Test |
|---|---|
| 8 journals the reader accepts and the projections refuse (story_state ×4, failure_owner, budgets, qualification_counters, terminal_state) are REFUTED naming projection, event type and seq; nothing re-derived | `RefusedJournals.test_each_is_refuted_by_a_finding_naming_the_projection_the_event_and_its_seq` |
| the helper returns (projection, type, seq, reason) for the first refused event in seq order | `...test_the_helper_names_the_first_event_in_seq_order_and_the_first_projection_to_refuse_it` |
| a journal that would deliver is not VERIFIED as delivering (commit with no admission; second commit) | `...test_a_journal_that_would_deliver_is_not_verified_as_delivering` |
| the projection's reason is in the finding; the operator's `aisef run --verify` exits 1 with it | `...test_the_projection_s_reason_is_in_the_finding`, `...test_the_operator_sees_the_finding_and_exit_status_1` |
| kernel-shaped journals, committed-attempt-with-failures, failures after an outcome, formats 1 and 2 are admitted and VERIFIED; the re-derived `no_progress` is the new definition's | `AdmittedJournals` (4 tests) |
| honest journals of record are admitted: the 2.0.0 release smoke run (1,834 events, bound to the sha the record names), the reader's fixtures that reconstruct (formats 1 and 2) | `JournalsOfRecord` (2 tests) |
| through the entry points that write and re-derive RUN.json on a journal the story runner wrote: a story that fails twice the same way is reported (attempt 2), equals the re-derivation, and is VERIFIED through the boundary (POSIX only: fake client) | `ExecutedRun` (1 test) |
| the premise "no event of type '' reaches the function": the reader of every format refuses a line of that type with a valid chain | `EmptyType` (2 tests) |

## 5. Evidence: what is real, what is simulated

* **Real kernel code, real files.** Every test builds journals with the real writers, real projections and the real
  reader, and runs the real `verify`. No provider, no client, no network. Nothing here ran in the Linux guest and none
  was needed: both changes are pure functions of journal bytes (no process, path, locale or clock). Windows was not run;
  the tests use `pathlib`, `tempfile`, binary writes and no POSIX-only call.
* **Real client and provider:** the V2.0.0 release smoke run's journal (`closure-evidence/v2/release/smoke-2`, 1,834
  events) is admitted (test, and `verify` on the run directory with the migrated release bundle gives the same findings
  at BASE and here, none of them a projection's).
* **Simulation of the provider, real kernel:** the 85 admitted format-3 journals found under the scratchpad (fault
  windows of refuters 1-3, test-suite runs with the fake client): `aisef run` code paths, fake developer/provider.
* **Neither real run nor simulation of a run:** the exhaustive enumeration (in-memory projections over an alphabet of
  nine events) is a model of "every admitted journal up to a length". It is supplementary evidence that the function
  agrees with a second statement of the requirement; it is **not** a proof, not a kill, and not what makes the two
  mutants resolved.

## 6. Measured

| What | Result | Basis |
|---|---|---|
| BASE `no_progress`, registered kill files (A20, T20a, kills_usage) | 33 mutants, 31 KILLED, **2 SURVIVED (13, 23)** | `kill_check` at BASE, reproduces the dossier |
| changed `no_progress`, same files + `test_v21_r3_usage_no_progress.py` | **35 mutants, 35 KILLED, 0 survived** | `kill_check`, `kc-no_progress.json`; the new file alone kills `L138 string 'story/begin' emptied` |
| `_projection_refusal` (new) | 9 mutants, 9 KILLED | `kc-_projection_refusal.json`, the boundary file |
| `verify` (199 mutants), the boundary file alone | 107 KILLED, 92 SURVIVED. **All 16 mutants on the lines this change added or moved (149-155) are KILLED.** The 92 sit on unchanged lines: 57 are killed by the registered A22, R01, T22a, T22b, defects_verify and test_v21_verify; 24 more by the campaign's other five files (test_app_units, test_s2_kills, test_app_run, continue_usage, continue_integrity); **11 survive** those six files: the same 11 the campaign recorded for BASE's `verify` as surviving all of its eleven files (matched by mutated text: `sorted()`, ` the run printed`, the `errors` entries, `no `, `)` x3; not re-run here against the other five), each already AUDITED or EQUIVALENT in `SURVIVOR-AUDITS.json` against BASE's source hash, an entry now stale | `kc-verify.json`, `kc-verify-survivors-registered.json`, `kc-verify-24-with-the-campaigns-other-five.json` (clean roots) |
| New tests against the BASE function | 8 of 14 `no_progress` tests FAIL on `git show 3dc827b:aisef2/app/usage.py`; the boundary tests that go through `verify` show `VERIFIED` + `PASS` at BASE for the two journals that would deliver | `wrong_impls.py`; BASE tree run |
| Distinct journals found (1,218 files, 101 distinct by sha256): formats 1 / 2 / 3 | 4 / 1 / 89 admitted: 4 + 1 + 85; refused by a projection: 4 (all format 3); do not reconstruct: 7 (the reader's own refusal fixtures and a corrupted copy) | `measure_journals.py` |
| The 4 refused | two `JournalWriter3` mini-journals of `test_v21_defects_verify.Dirs.run_dir` (a `provider/request` with no `story/begin`; used by lineage tests, never given to verify), one writer experiment (a retry after a commit), one named `forged`. None was written by a kernel run | provenance read from the generating scripts |
| BASE vs changed `no_progress` on the 94 readable distinct journals | 87 identical (23 with a non-empty report); 7 differ: 5 admitted (writer/RunScope experiments that inject a failure before a commit or after an outcome), 2 refused | `compare_old_new.py` |
| RUN.json records with a `no_progress` field | 32 found; 29 resolve their journal by name or sha; record == BASE == changed on all 29 (16 with a non-empty report). None is committed in the repository: its two RUN.json are 2.0.0 records without `usage` | `compare_old_new.py` |
| Enumeration, one story, <= 10 events after plan/frozen | 100,337 admitted journals; changed function == the independent oracle on all; BASE differs on 384 (368: a failure after an outcome; 16: a committed attempt that observed failures); INV-B (an event of the story after its commit) broken in 0, INV-A in 18,952 | `enumerate_admitted.py` (simulation, see §5) |
| Enumeration, one story, <= 13 events after plan/frozen | 2,733,181 admitted journals; changed function == the oracle on all; BASE differs on 59,650 (59,372 and 278, the same two classes) | idem (an earlier version of the script, without the INV counters) |
| Enumeration, two stories, <= 10 events after plan/frozen | 42,579,530 admitted journals; changed function == the oracle on all; BASE differs on 1,448 (1,216: a failure after an outcome; 232: a committed attempt that observed failures); INV-B broken in 0, INV-A in 8,387,736 | idem (110 minutes) |
| The release smoke run directory under `verify`, bundle migrated to this tree's probes | identical findings at BASE and here (the bundle digest, the RunSpec re-derivation and the ProductProof account, all three caused by the 2.0 to 2.1 differences, not by this change); none is a projection's; `journal_events` 1,834 | `verify_release.py` |

Test modules run, alone, under the guard wrapper: the 27 that import `usage` or `verify` (two of them new) plus
`p0.test_destructive_authority`, `p4.test_mutation_safety`, `test_meta`: all OK (no failure, no error, no skip),
including the executed-run modules (`test_app_run`, `test_v21_continue_integrity`, `test_v21_verify`, ...) whose
honest journals now pass through the boundary. Expected red or stale after a product change: `test_c2_k_nowork_001` (1
failure: "the kernel changed since the record"), Q0 `checker_calibration --check` 52/54 against 53/54 at BASE (the new
red is `execution_order`, derived from T0-SWEEP-4 and stale for the same reason). Green: `p2.test_mutation_targets`,
`test_v21_mutation_record`, `test_s2_mutation_record`, `test_v21_mutation_runner`.

## 7. The two old mutants (13 and 23)

**Resolved by the product change. Neither KILLED nor AUDITED, and no equivalence is claimed.** The function they were
derived from no longer exists: `story/commit` is not a closer. Mutant 13's closers are now the product's. Mutant 23's
`''` closer would differ from the product only on an event whose type is `''`; the reader of every format refuses
such a line (`Event.__post_init__`, `event.py:64-65`, reached by `decode`, `event.py:298`; `EmptyType` tests it with a
valid chain and a faithful encoder as control) and the writer takes only a typed `EventType` (`format3.py:384`). That
is an argument about a function that is gone; it is not offered as a kill.

What replaces them is a behaviour, verified: a commit does not close a failed attempt, and a failure outside an attempt
is not the next attempt's. It is pinned by tests that fail on a function that does otherwise (8 of 14 on the BASE
function). That reinsertion is a wrong implementation I ran by hand, not a runner mutant: the runner's catalogue drops
or empties elements and never adds one. The changed function's own mutants are the 35 above, all killed. The lead retires
the two rows when the target is re-measured (its source hash changed).

## 8. Residual risks, and what is not established

* **Late failures (D1, second bullet).** The control projections attribute a failure journaled after an outcome to the
  attempt it followed (`failure_owner`, `budgets` keep it until the next begin). The function does not put it in that
  attempt's row, and does not put it in the next one: it reports what the attempt had observed when it ended. On a
  journal with such a failure the answer can differ from "the attempt's whole failure set". No producer writes that
  shape; the decision is flagged (D-LATE).
* **Consistency, not authenticity.** Without `--expect-anchor` a forger can still write a journal the projections
  admit. The boundary refuses the lifecycle violations, which a forger no longer gets past by deriving the record from
  the journal; it adds nothing against an admitted, consistent rewrite (`ANCHOR-THREAT-MODEL.md` is unchanged).
* **Other readers.** `bundle continue` (`bundle_cli.py:432`, trusts `story/commit` for the continuation's baseline),
  `lineage.events_of` (`lineage.py:99`, the spend), `repair` (folds the projections, no product caller) and the
  sentinel read journals with `format3.reconstruct` and do not refuse a projection-violating one. None reaches
  `no_progress`; they are outside the owner's principle as worded and outside this WP's files (D-READERS).
* **Cost.** The fold is linear in the events with a state copy per step (about a millisecond per event here; 1,834
  events in about a second). Not measured at 100,000 events.
* **Formats 1 and 2.** No supported path ever wrote them as a run directory (the format-3 switch, `175ba3a`, precedes
  the product runtime, `6b0b90d`); `verify` reads them through the same reader and the boundary admits the 4 + 1
  fixtures and journals the real format-1/2 writers produce under `Authority` (simulation). No honest run directory of
  those formats exists to check.
* **Not run.** Windows; the Linux guest (not needed: pure functions of journal bytes); a real client or provider (the
  2.0.0 smoke journal is the only real-client journal, and it is old); journals of a kernel earlier than 2.0.0.
* **Bounded model.** The enumeration uses two failure codes, at most two stories, 13 (one story) or 10 (two stories)
  events. It is a conformance check against a second statement of the requirement written by the same author.
* **Non-ProjectionError.** `_projection_refusal` catches `ProjectionError` only. A projection that raised something
  else on an event the reader accepted would surface as "the journal does not reconstruct: <type>" through the existing
  handler, still a finding. None of the 101 journals did; I did not prove none can.
* **Docs.** `USAGE-2.1.md:86` says "retry lặp lại đúng các lỗi cũ" and `TRACEABILITY.md:686` "các attempt liên tiếp
  có cùng tập lỗi": both still true; only the function docstring says "failed". Not edited (not this WP's files).

## 9. Decisions needed

* **D-LATE.** A failure journaled after an attempt's outcome and before the next `story/begin`: ignored (this change)
  or attached to the attempt it followed (the projections' attribution). The second needs lookahead to keep the
  begin-less unit-test lists meaning what the existing tests say: a pre-scan for stories that have a `story/begin`
  (about three lines) and four to six new tests. No producer writes the shape.
* **D-READERS.** Whether `bundle continue`, `lineage.events_of` and `repair` must also refuse a journal the
  projections refuse. `_projection_refusal` would move to `aisef2/journal` to be shared.
* **D-INVA.** Whether "failure then commit in one attempt" should be impossible (a projection refusing `story/commit`
  while the attempt has an open failure). That changes journal semantics (projection version, frozen items). This WP
  answers the shape instead (D1) and does not touch the projections.
