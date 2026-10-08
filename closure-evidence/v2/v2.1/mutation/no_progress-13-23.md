# `usage.no_progress`, mutants 13 and 23: equivalence dossier

**Status: OPEN. Both mutants are SURVIVED. They are not killed and not audited.** They remain open survivors of
`aisef2/app/usage.py::no_progress` until the owner rules. This dossier argues that the two mutants are equivalent to the
original on the domain the kernel supports. That argument does not turn either mutant into a kill.
`validation/v2/mutation.py:1614-1618` keeps a SURVIVED mutant as an "unaudited survivor" until an `AUDITED` entry
exists. No such entry exists, and none is applied here. The entries the process would need are drafted in
`no_progress-13-23.exception-request.json` (PROPOSED, NOT APPLIED).

Code base. Every `file:line` below refers to `v2.1/foundation` 3e6ebf1. `git diff --quiet 5719f1f 3e6ebf1 -- aisef2/`
passes, so the kernel is byte-identical to the snapshot campaign 2 measures (5719f1f). `aisef2/orchestrate/story_runner.py`
is also byte-identical from d622e71, the commit that introduced `no_progress`, through 3e6ebf1
(`git diff --quiet d622e71 3e6ebf1 -- aisef2/orchestrate/story_runner.py`).

## 1. The two mutants

`no_progress` (`aisef2/app/usage.py:113-129`; module `source_sha256` f7812cbd90a2e96f3736dfab2554af79a0bc25ecc6052fbbb8f0fe3507b50223)
has 33 mutants from `mutation.mutants(src, "no_progress", mutation._enum_members(src, root))`. This dossier covers two
of them.

| index | description (the record's key) | line 122 becomes |
|---|---|---|
| 13 | `L122 element 2 dropped` | `elif e['type'] in ('story/retry', 'story/rollback'):` |
| 23 | `L122 string 'story/commit' emptied` | `elif e['type'] in ('story/retry', 'story/rollback', ''):` |

The original line 122 is `elif e["type"] in ("story/retry", "story/rollback", "story/commit"):`. Under both mutants,
`story/commit` no longer closes an attempt. Only retry and rollback append a row and pop the failures collected so far.
The mutant source is `ast.unparse` output, so a textual diff also shows quoting and line-joining changes everywhere in
the module. Line 122 is the only semantic change.

How they were measured. Pilot attempt 2, lane `l2-ord`, at 5719f1f, runner 2, table order
(`closure-evidence/v2/v2.1/pilot/attempt-2/l2-ord.record.json`; reused by campaign 2, `CAMPAIGN-2-START.json`
`reuse_table` row 4). Its kill set was `test_v21_verify.py`, `test_v21_continue_usage.py` and
`test_v21_continue_integrity.py`. Result: 33 mutants, 29 KILLED, 4 SURVIVED (13, 14, 23, 24), with every kill file
PASSing for each survivor. After the snapshot, 144b028 added `tests/v2/test_v21_kills_usage.py`, which does not exist at
5719f1f. A hand check in a COPY tree showed it kills 14 and 24 (3 of 3 runs each). That was not a mutation run. 13 and
23 pass it. `CAMPAIGN-2-START.json` `after_the_campaign` schedules `no_progress` to be re-measured with that kill file
under manifest revision 3. That run has not happened.

## 2. The lemma, from the code

Take one story S. The original appends one row per closer of S (retry, rollback or commit). Each row is
`sorted(current.pop(S, []))`, the failures of S observed since S's previous closer. `same` keeps index n when
`rows[n] and rows[n] == rows[n-1]`. The output lists `n + 1` for each kept n, and `failures = rows[same[0]]`. The order
of the output is the order in which each story's first closer occurred (`attempts.items()`).

**INV-B.** After a `story/commit` of S, no retry, rollback, commit or begin of S follows. Under INV-B, the commit is
S's last closer, and until it the two versions pop the same failures at the same events. The mutant's rows are therefore
the original's rows without the last row C, the commit's row. Dropping the last row can remove only C's own index from
`same`. Every other index, and `rows[same[0]]`, depends only on rows both versions share.

**INV-A.** No failure/observed of S is open when S commits. Under INV-A, C = `[]`, so C's index is never in `same`.

**Order.** If S has output, then S has at least two rows in the mutant. By INV-B its first closer is a retry or a
rollback, the same event in both versions, so S's key is inserted at the same position. A story whose only closer is a
commit has the row `[[]]` in the original, which produces no output, and has no key in the mutant.

**Therefore**, INV-A and INV-B together imply `orig(x) == m13(x)`. When INV-B holds, the two differ exactly when the
committed attempt observed failures and they were the same set as the attempt before it.

**m23 == m13.** Mutant 23 differs from mutant 13 only on an event whose type is `''`. No event that reaches
`no_progress` has that type. The writer takes only a typed `EventType` (`format3.py:384`), and none of the 29
`EventType` values is `''`. The reader keeps only `VOCABULARY` types and refuses unknown required ones
(`format3.py:322-328`); `''` is not in `VOCABULARY`. Both facts were measured in-process.

## 3. The input domain, from the public contract and the real callers

**The contract.** The `no_progress` docstring reads "Per story, consecutive failed attempts with the same failures
(codes and details) ... A report; the taxonomy alone decides a retry" (`usage.py:114-115`). The module docstring adds
that it "reads the journal for retries that changed nothing" (`usage.py:11-12`). The user-facing docs say RUN.json
carries `no_progress`, meaning retries that repeat the same failures, report only (`docs/v2.1/USAGE-2.1.md:86-87`). The
traceability doc says "consecutive attempts with the same set of failures" (`docs/v2.1/TRACEABILITY.md:686`, P-5.3c).
Nothing in the contract names a committed attempt that observed failures.

**The callers.** `git grep no_progress -- '*.py'` finds exactly two product callers. Everything else is a test or
`validation/v2/mutation.py`.

- `aisef2/app/run.py:495` writes `RUN.json`'s `no_progress`. Its input is the in-memory event list of this run's
  RunScope (`run.py:481`), built after `_close_run` (`run.py:478`, `:509-522`).
- `aisef2/app/verify.py:147-148` re-derives the value from the journal bytes RUN.json names (`verify.py:99-117`) and
  compares it with the record. It does this only when `rec["usage"]` is a dict without `"error"` (`verify.py:142`),
  which means only for V2.1 records.

**How every input event is written.**

- The only RunScope is built at `run.py:421`, and the only journal writer at `run_scope.py:121`, with its Authority at
  `:122`. JournalWriter (`journal/writer.py`) and JournalWriter2 are never instantiated in `aisef2`.
- Every event goes through `RunScope.append` (`run_scope.py:142-146`), then `Authority.append` (`fold.py:145-155`),
  then `JournalWriter3.append` (`format3.py:376-409`). The writer runs the six projections' check (`format3.py:389-390`)
  before `os.write` (`:395`).
- A failed write poisons the writer (`format3.py:380-381`, `:399-406`).

Path by path:

| path | what reaches `no_progress` | why INV-A and INV-B hold | measured by |
|---|---|---|---|
| **Fresh run** (`aisef run`) | run.py:495: the events of one new journal. `--out` must not exist (`run.py:335-336`). The writer reads an existing file only if there is one (`format3.py:346`), so the journal starts empty | INV-B: projection pre-check on every append. INV-A: story_runner (section 4) | refuters 1-3 (finished runs; shapes bC, bFRbC, bFRbFRbC, bFRbFRbFRbC, bFRbFB, ...) |
| **Continued run** (`aisef run --parent`) | Only the child's own new journal. The predecessor is read for the claim and the spend only: `lineage.claim` (`run.py:368`), `lineage_account` (`:371`), `verify._spend` (`verify.py:53-63`). `lineage.usage_lineage` calls `usage.usage`, never `no_progress` (`lineage.py:305-327`) | Same as a fresh run: the child's journal is fresh. A predecessor's committed story is a CARRIED story that begins and commits in the child (bC) | refuters 1-3: every captured child list starts at the child's own `run/begin` |
| **Killed run + continuation** | The killed run itself: none. It has no RUN.json (only `RUN.started.json`, `run.py:338-344`), and verify REFUTES it at `verify.py:70-72`, before line 148. The continuation: as above | The disk journal is a prefix of the kernel's appends. Both invariants look only backward, so they survive any prefix | refuters 1-3 (SIGKILL after failure/observed, after retry, after commit, at claim-before-begin; measured 0 calls of `no_progress` on the killed run) |
| **Torn tail** | `verify.py:148` gets the complete-line prefix. The reader drops the last, incomplete line (`format3.py:315-316`), and verify reports it (`verify.py:114-115`). A torn journal is never extended (`format3.py:348-349`) | Prefix closure | refuter 2 (short write of commit); refuter 3 (cut copies) |
| **Reconciliation** (`aisef bundle continue`) | None. `continue_from` reads the predecessor journal for its `story/commit` list only (`bundle_cli.py:395-401`) and calls `lineage.reconcile` (`bundle_cli.py:407`; `lineage.py:177-230`). It writes a new bundle and journals nothing. It refuses a run of another kernel (`bundle_cli.py:391-393`) | n/a | refuter 2 (merge moved main / commit not journaled, then continue) |
| **Verify** (`aisef run --verify`) | The bytes run.py wrote; or a complete-line prefix of them; or, in the double fault (fsync and ftruncate both fail, `format3.py:395-404`), memory plus one more complete event. That extra event passed the pre-check, was the kernel's own append, and nothing follows it. If SIGINT lands between `os.write` and `_events.append` (`format3.py:395-409`; only OSError poisons the writer), the next append repeats the seq. The journal then fails to reconstruct, `events` stays `[]`, and every version returns `[]` | Same bytes, a prefix, or one more event in story_runner's own order | refuter 2 and 3 (double fault on commit, on retry, on failure/observed); the SIGINT race was reasoned about, not run |
| **Verify of a directory the kernel did not write** | Outside the domain. Without `--expect-anchor`, verify proves "consistency, not authenticity" (`verify.py:9-12`). With it, a rewritten directory is REFUTED (`verify.py:91-92`) | Not enforced: see the weakest link | — |
| **Interrupt, shutdown, refused story** | The closers `interrupt` and `shutdown` write are `run/interrupted`, a synthetic `provider/result`, `resource-released`, `run/dispose-begin` and `run/end` (`run_scope.py:178-193`, `:204-248`). A story that raises is recorded REFUSED and never runs again (`run.py:466-470`). Each story runs once, in order (`run.py:450`; `bundle.py:114-126`), and the only caller of `run_story` is `run.py:462` | No story commit follows an open failure | refuters 1-3 (SIGINT between `_fail` and retry; faults in `budget.charge` and `Developer.implement`) |
| **Import / migrate / repair** | None. There is no import subcommand. `aisef bundle` has init, seal, approve, lint, explain, continue and migrate (`bundle_cli.py:476-502`). `aisef run` has run, `--check` and `--verify` (`aisef2/app/cli.py:28-50`). `aisef/cli/parser.py:186-189` only forwards `run` and `bundle`. `migrate` reads and writes bundles only. `repair_journal` (`runtime/repair.py:98`) has no product caller, and it writes only tool/result, provider/result, resource-released, run/interrupted and run/end (`repair.py:37-71`) | n/a | grep; refuter 3 |

The supported domain is therefore: event lists of journals the kernel writes, complete-line prefixes of those journals,
and the double-fault journal that holds one more kernel append.

## 4. The invariants and the code that enforces them

| invariant | enforced by | where |
|---|---|---|
| **INV-B.** After S's commit, no retry, rollback, commit or begin of S follows. | The write-time projection pre-check, on every append. The reader does not re-check it. | `story_state.py:10-11`: commit only from ACTIVE; retry and rollback only from BEGIN or ACTIVE. `:37-38`: begin only after ENDED with outcome RETRY. `terminal_state.py:39-52`: an outcome needs the story RUNNING with nothing pending; after a COMMIT end the story is "COMMIT", and begin needs "OPEN". Measured refusals: refuter 3's `out/writer-probe.json` (begin again after rollback or commit, retry or rollback after commit, a second commit: all REFUSED). |
| **INV-A.** When S commits, no failure/observed of S is open in that attempt. | **story_runner's control flow only.** | `story_runner.py:142-146`: `_fail` is the only product writer of failure/observed (`git grep FAILURE_OBSERVED -- 'aisef2/*.py'`). `:328-329`: commit only when `failure is None`. `:331-338`: otherwise `_fail`, then the pure `budget.charge` (`control/budget.py:34-50`), then `run.retry` (`run_scope.py:155-161`) or rollback. `:340-342`: then only dispose, resource-released and end before the next begin (`:168`). `failure` is one local per attempt, so a failed attempt journals exactly one failure/observed. |
| **Fresh journal, single writer.** Every event on run.py:495 was appended in this process, through RunScope, Authority and JournalWriter3, into a journal that started empty. | Code structure | `run.py:335-336`, `:421`, `:481`; `run_scope.py:121-122`, `:142-146`; `format3.py:346`, `:384`. |
| **Poisoned writer.** After a failed append nothing more is written. Disk can exceed memory by at most one complete event, and only if ftruncate fails too. | `JournalWriter3._broken` | `format3.py:380-381`, `:395-406`. |
| **Prefix closure.** Both invariants look only backward, so every prefix of a list that satisfies them also satisfies them. | Logic, plus the reader dropping only the torn last line | `format3.py:315-316`; `verify.py:114-115`. |
| **Two callers.** No continue, lineage, bundle, migrate or repair path calls `no_progress` or gives it a predecessor's events. | Call graph (grep), not a runtime check | `run.py:495`, `verify.py:148`; `lineage.py:313` calls `usage.usage`. |
| **No empty type.** No input event has type `''`, so m23 = m13. | Writer type check, reader vocabulary | `format3.py:384`, `:322-328`. |

### The weakest link

**INV-A is enforced by nothing but `story_runner._attempt`'s control flow (`story_runner.py:328-338`).** No
journal-level rule backs it. The projections admit failure/observed in any state once a story has begun
(`story_state.py:13-14`, `FAILURE_OBSERVED: None`), and they admit commit from ACTIVE. The verify reader runs no
projections at all. Refuter 3 measured the gap: replaying a kernel journal through Authority over a fresh JournalWriter3,
then appending failure/observed just before the commit, was ACCEPTED. Two consequences follow:

1. The equivalence is a property of today's story_runner, not of the journal format. A future change that journals a
   failure in an attempt that still commits would make mutants 13 and 23 distinguishable, and no current test would
   notice. Examples are a non-blocking finding journaled as failure/observed, or a failure recorded and then recovered
   within the attempt.
2. On the verify path without `--expect-anchor`, the domain is bounded only by verify's stated scope ("consistency, not
   authenticity", `verify.py:9-12`), not by a check. A hand-written, format-valid, self-consistent run directory with
   failure then commit in one attempt is VERIFIED by one version and REFUTED by the other. The RUN.json value and the
   re-derivation then come from different versions.

A lesser point: the call-graph facts (two callers, `run_story` called once, no dynamic `EventType`) rest on grep at
3e6ebf1, not on a runtime guard.

## 5. Samples (supplementary only; the argument is sections 2-4)

All runs used `env -i` with the guarded PATH (no `opencode`; checked with `command -v`), HOME and TMPDIR in scratch,
cwd in scratch, and `python3 -B` 3.14. Scratch is
`/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/wf-followups/`.
It is not durable: macOS cleans `/tmp`.

| sample | by | result |
|---|---|---|
| Exhaustive enumeration of {FX, FY, R, B, C} per story, with `no_progress` read from the worktree by `ast` (no repo import): `A-dossier/lemma.py` (sha256 3399f75a…, the earlier `A-domain-verdict/lemma.py` with its path changed to this worktree) | re-run 2026-10-08, 15.9 s | One story, length ≤ 8: 488,281 sequences. 109,226 satisfy INV-A and INV-B, and **0** of them differ. 1,656 differ with only INV-A broken, and 37,560 with INV-B broken. Two stories, length ≤ 6: 1,111,111 sequences. 464,701 satisfy both, and **0** differ. 3,992 differ with only INV-A broken, and 11,480 with INV-B broken. m13 == m23 on all of them. Identical to the earlier run. |
| `kills2/diff_noprogress.py` (sha256 d8867066…, unchanged), mutants from `mutation.mutants` on this worktree. Real journals are every `aisef-run.jsonl` under the scratchpad (with `m21/` pruned, never entered) plus the worktree's `closure-evidence`. Generated journals follow the kernel's grammar with seed 20261008 | re-run 2026-10-08, 13.2 s | 141 journal files read (61 distinct by sha256; one more file was deleted by another session's run while I listed them). All 141 are identical across orig, m13 and m23; 91 have a non-empty report; 0 attempts commit after an observed failure. 200,000 generated: 0 differ, 62,027 non-empty. On `[F, R, F, C]` the original gives `[2]` and both mutants give `[]`. Commit 144b028 reported 116 journals in its earlier run of the same script, with a smaller scratch. |
| Refuter 1: lineage kill (`A-ref-lineage-kill/`) | earlier agent | Killed, interrupted and superseded-claim runs, then `--parent`. Every list run.py and verify.py passed is identical across the three versions, and verify gives the same verdict under each. |
| Refuter 2: recovery windows (`A-ref-recovery-windows/`) | earlier agent | 25 harness tests (the 11 `test_v21_continue_integrity` windows, plus retry-history windows and double faults); 126 inputs; 0 differences; 0 INV-A or INV-B breaks; 20 verify verdicts identical. |
| Refuter 3: verify, import, interleave (`A-ref-verify-import-interleave/`) | earlier agent | 28 journals, including the 1,834-event release smoke `closure-evidence/v2/release/smoke-2/run-1/aisef-run.jsonl`, which has a story that repeated failures and then committed. 0 differences; 20 verify verdicts identical. The writer probe is described in section 4. |

None of these is a kill and none replaces the argument. All three refuters built their runs from fault injection and
the repo's fake developer and provider. None of them used a real client or provider, or ran on Windows.

## 6. Outside the domain: shapes the format admits but no producer writes

| shape (one story) | admitted by | original | m13 / m23 |
|---|---|---|---|
| `F_x, R, F_x, C`: failure then commit in one attempt, the same set as the attempt before | writer and projections (`story_state.py:13-14`, measured ACCEPTED); reader | `[{"attempts_repeating_the_one_before": [2], ...}]`: the **committed** attempt reported as a repeated failed attempt | `[]` |
| `F_x, C`, or a commit row that differs from the row before | writer and projections | same as the mutants | same |
| a closer or begin after a commit (INV-B broken), e.g. `F_x, R, C, F_x, R` | **refused** by the projections; accepted only by the reader (a forged directory) | `[]` (rows `[x], [], [x]`) | `[2]` (rows `[x], [x]`) |
| failure/observed after a commit | writer and projections (measured ACCEPTED) | no effect: no closer can follow | no effect |

On the only admitted shape that separates them, the first row, the original reports an attempt that **committed** as
one of the "consecutive failed attempts" (`usage.py:114`). The mutants report nothing, which is the docstring's literal
reading. A regression test that pins the original's answer there would pin behaviour the contract does not ask for, and
arguably contradicts. A test that pins the docstring's answer fails on the original, which would be a product change
(section 8). That is why no regression test is added.

## 7. The domain question the owner has to settle

Whether 13 and 23 are equivalent depends on which domain is chosen. The same choice affects the kill of mutant 24.

- **Domain A, journals the kernel writes (section 3).** 13 and 23 are equivalent. Mutant 24 (`L123 sorted() -> list()`)
  is then equivalent too, because a failed attempt journals exactly one failure/observed (`story_runner.py:332`; one
  `failure` per attempt). Yet `tests/v2/test_v21_kills_usage.py` kills mutant 24 with two-failure attempts, an input
  from domain B. That test's docstring justifies it: "The journal admits several failures in one attempt". A kill on a
  wider input than the domain is still a kill, and set semantics is the contract ("the same set of failures", P-5.3c).
  The asymmetry should be acknowledged, not hidden.
- **Domain B, journals the writer and projections admit.** 13 and 23 are **not** equivalent. On the separating shape
  the docstring favours the mutants' answer, so the original carries a latent defect there. The consistent resolution
  is the product change in section 8 plus a regression test for the docstring's answer, not an audit.

## 8. The optional product change (NOT applied)

The change is to drop `"story/commit"` from the tuple at `usage.py:122`, which makes the product equal to mutant 13.
It was previewed in memory only (`A-dossier/change_preview.py`); no file was written.

- **Supported journals (domain A): no change in behaviour.** This is the lemma of section 2. Both unit tests that call
  `no_progress` directly give the same output: `test_v21_continue_usage.py:76-84` and `test_v21_kills_usage.py`,
  measured.
- **Unsupported journals.** On `F_x, R, F_x, C` the result changes from `[2]` to `[]`, matching the docstring. On
  shapes that break INV-B (refused by the projections, reachable only by a forged directory) the outputs differ as in
  section 6, row 3.
- **Its own mutants.** The changed function has 31 mutants, and all 31 differ from it on the inputs of those two unit
  tests (a crash counts as a difference). That is an in-memory lower bound, not a mutation run.
- **Cost against snapshot 5719f1f** (owner directive 1):

| file | targets | tests / harness | evidence to re-measure |
|---|---|---|---|
| `aisef2/app/usage.py` (source_sha256 f7812cbd… → fb3cbe8e5038543ce7c2f824318d0bc4b761dd82444371eb6ebe5ddfd5c6353a) | all 8 of usage.py's V2.1 targets (`PRICE_KEYS`, `CLASSES`, `_DATE`, `price_problem`, `session_tokens`, `_usd`, `usage`, `no_progress`) go stale: `--check` reports "target changed since the mutation run", and `v21_mutation_record.proof` refuses reuse ("the target file changed") | their kill sets: `test_v21_continue_usage.py`, `test_v21_verify.py`, `test_v21_continue_integrity.py`, plus `test_v21_kills_usage.py` for `no_progress` | re-measure those 8 targets |
| the same file, through the import closure | **424 of the 466** V2.1 targets have a kill set whose import closure at 5719f1f contains `aisef2/app/usage.py` (`S2.closure`, 21 of 45 kill files; `A-dossier/closure_scope.py`). Their results would carry `other_code_changed: ["aisef2/app/usage.py"]` (`v21_mutation_record.py:60`, `:68`). That is reported, not blocking | every kill file that imports run.py, verify.py or usage.py | none mechanically required, but under owner directive 1 a result from 5719f1f may be bound to the new HEAD only with a stated basis. The lemma says the change is invisible on kernel-written journals; that is an argument, not a measurement of those 424 results |
| `aisef2/` as a whole | `run.kernel_digest()` covers every `.py` in `aisef2` (`run.py:77-84`), so the digest changes | `aisef bundle continue` refuses a run of another kernel (`bundle_cli.py:391-393`) | run directories from 5719f1f could no longer be continued by the changed kernel |

This change is the owner's to order, as a separate product change with its own re-measurement. It is not a reason by
itself to change code, and it is not applied here. Making it during campaign 2 would move the foundation off the
snapshot being measured.

A heavier alternative would enforce INV-A in the journal: a projection that refuses `story/commit` while a
failure/observed of the same attempt is open. That changes journal semantics (projection version, frozen items) and is
listed only for completeness.

## 9. Side findings (not about these mutants; the same under all three versions; nothing changed)

1. **Verify refutes an honest record.** When a story journaled a RETRY and the run was then interrupted, or the story
   was refused, verify REFUTES the run's own RUN.json with "the record's story outcomes are not the journal's for
   [...]". Refuters 1-3 measured it (e.g. `A-ref-recovery-windows/analyse.out`: `test_sigint_between_fail_and_retry`
   first run). I confirmed the cause by reading the code. `run.py:463` records `results[story]` only when `run_story`
   returns, and `:468` replaces it with `["REFUSED: ..."]`. A KeyboardInterrupt leaves it unset. Meanwhile
   `verify.py:118-122` re-derives `["RETRY", ...]` from the journal. This is a candidate product issue for the owner.
2. **Failure after commit is accepted.** The writer accepts failure/observed for a story already in state COMMIT
   (`story_state.py:13-14`). It is harmless to `no_progress`, because no closer can follow.

## 10. What was not done

- No `mutation.py run` or `t0`, no full suite, no COPY tree. The only repo tests run were the pre-commit checks
  (`tests/test_meta.py`).
- I did not run any supported path end to end myself; refuters 1-3 did, and section 5 reports their measurements. The
  SIGINT race between `os.write` and the in-memory append was reasoned about by refuter 1 and not run. The double fault
  was run by refuters 2 and 3.
- I did not check Windows, use a real client or provider, or check kernels before d622e71. Records written before
  V2.1 never reach the comparison at `verify.py:142`.
- I made no edit to `validation/v2/mutation.py`, `aisef2/` or any test. `tests/v2/p2/test_mutation_targets.py:30` and
  `validation/qualification/q2.py:90,331` would refuse the proposed audit as written; see the exception request.
- Only this worktree was used. Nothing under `scratchpad/m21/`, `heavy.lock` or the campaign worktrees was touched.
- One scratch text edit (patching my own `change_preview.py`) ran `python3` without the `env -i` guard, with cwd in
  scratch and no repo import. Every other python run was guarded.
