# Changelog

## Unreleased

## 1.7.6 — 2026-09-16

One defect, found by the clean OpenCode replay of the second LedgerLock run
continued on the public `aisef==1.7.5` package (STORY-04-01 after the owner's
AC-4 arbitration; record
`closure-evidence/dogfood/ledgerlock-run2/replay-1.7.4-opencode/`, OBS-OC-3).
No feature, no gate softened, no waiver, nothing else touched; the regression
was red on 1.7.5 (`tests/test_retry_hygiene.py`: 9 red, 4 controls green — all
green on 1.7.6).

**A developer retry opens on a tree clean of out-of-scope changes (D-034, lỗi 188).**
Attempt 1's developer session ran `ruff format ledgerlock/ …`, which
reformatted `ledgerlock/ledger.py` and `ledgerlock/store.py` — cosmetic,
outside the write scope. The freeze rightly committed only in-scope paths and
the gate rightly failed `write scope`; but nothing restored the two files
before the retry. Attempts 2 and 3 opened on the same dirty tree, the OpenCode
`diff-scope` after-hook threw on every Bash/Write/Edit call from the first
`ls -la`, the developer could neither act nor revert (`git checkout --` and
`git reset --hard` are blocked, Write/Edit on the two files is outside scope),
and both sessions ended at the 80-turn cap having written nothing — 160 turns,
nothing graded, a story that could not complete without operator intervention.

Now, the moment a developer session ends, what it left outside the write scope
goes on record (`write-scope:violation`: attempt, tracked and untracked paths;
a path already dirty when the session opened is listed apart and not
attributed). Before the next developer attempt opens in a story worktree, the
harness restores the recorded tracked paths from the frozen candidate
(`git restore --source <candidate> --staged --worktree -- <paths>`), removes
only the recorded untracked ones, keeps every in-scope change — committed or
not — re-checks the tree, and records what it did (`retry:recovery`: failed
attempt, next attempt, candidate SHA, paths, actions, post-recovery status).
Dirt no attempt of this story is on record for is never touched, and the
attempt does not open on it either: the story stops with a reason naming the
paths, since a developer on that tree could only be blocked by the guard.
Trees left by 1.7.5 and earlier (no violation record) are read through the
last `gate:input`, whose `changed` list is exactly what the gate failed
`write scope` on. The write-scope message no longer says "Revert them" with no
permitted way to do so: it states that the harness restores these paths before
the next attempt and names the one allowed in-session move
(`git restore -- <paths>`). Reviewer-tree restoration is unchanged;
`--no-isolate` runs (the user's own tree) are recorded but never restored or
cleaned by the harness.

Unchanged on purpose: `run.max_turns`, reviewer semantics, Bandit/SAST, every
other open defect (D-002/D-003/D-011/D-024, all P2), the LedgerLock stories.

## 1.7.5 — 2026-09-16

One defect, found by the clean OpenCode replay of the second LedgerLock run on
the public `aisef==1.7.4` package (STORY-03-01; record
`closure-evidence/dogfood/ledgerlock-run2/replay-1.7.4-opencode/`). No feature,
no gate softened, no waiver, nothing else touched; the regression was red on
1.7.4 (`tests/test_baseline_provenance.py`: 10 red, 4 controls green — all
green on 1.7.5).

**A story's regression baseline is immutable within its epoch (D-033, lỗi 187).**
`run_baseline` ran on every `implement_story` invocation at the worktree HEAD,
so a story resumed from its own branch re-baselined at its previous candidate
(ca37cc44), and the `no baseline regression` check read the newest record.
The story's own earlier tests became "tests present at baseline"; when the
developer renamed two of them (dropping a wrong criterion code) the gate
scored "lost 2 tests present at baseline", and a candidate green on every
other check could not complete without operator intervention — nothing
present at story entry (parent 9cf22f5c) had been lost. Now the baseline is
captured **once per story epoch** (the acceptance-criteria fingerprint,
`acceptance.contract_fingerprint`, the same hash the `story:contract` note
carries) **at the integrated parent** when the story begins, and carries
`root` and `epoch`. Retries, resumed runs and `--verify-only` reuse that exact
record (`baseline REUSED` in the run log); a candidate the story produced never
becomes its baseline. The gate (`gate.authoritative_baseline`) scores against
the story-entry record for the current epoch — records from earlier releases
are accepted only when they stand at the branch point — so deleting or
renaming a test the story itself wrote is not a regression, while losing a
test that existed at story entry still is. A new baseline exists only for a
new epoch (criteria changed: the branch is discarded and the story restarts
from its base). Absent or provenance-invalid baseline → fail closed: the
producer records `BASELINE_UNAVAILABLE` instead of baselining a resumed
story's HEAD, and the check reads ⚠ UNRUNNABLE `BASELINE_UNAVAILABLE` when
records exist but none was captured at the parent for the current contract;
a journal with no baseline at all still reads "cannot compare"
(NOT_APPLICABLE), as before. The `tests verify story` level-1 comparison and
the nop control's parent fallback use the same selection.

Unchanged on purpose: the pytest node-id rename heuristic (`_class_of`) —
against the correct baseline the story's renamed tests are not baseline tests
at all, so no independent red case exists; recorded as backlog. Also unchanged:
`run.max_turns`, reviewer semantics, Bandit/SAST, every other open defect.

## 1.7.4 — 2026-09-15

One defect, found by the second LedgerLock dogfood run on the public
`aisef==1.7.3` package (intake `closure-evidence/dogfood/ledgerlock-run2/`).
No feature, no gate softened, no waiver, nothing else touched; the regression
was red on 1.7.3 (`tests/test_run2_review_recovery.py`: 6 tests and 2 subtests
red, 6 controls green — all green on 1.7.4; two existing reviewer-integrity
tests changed expectation with it, see below).

**A review that did not run is not a review verdict (D-032, lỗi 186).**
STORY-01-06: tests and lint green, security clean, the reviewer cut at
`max_turns` with no verdict. `review could not run: …` was stored as a blocking
review finding, the gate failed `review`, the loop's only recovery was a new
developer session, the developer correctly wrote nothing, two no-ops ended the
story as `sessions kept producing nothing to grade`, and a resume repeated it
exactly. A review now has three outcomes — `PASS`, `BLOCK`, `REVIEW_UNRUNNABLE`
— and the gate scores an execution failure (cut at `max_turns`, timeout,
transport failure, no valid verdict, reviewer modified the tree, candidate
moved during the session) as `review` ⚠ UNRUNNABLE, never ✗. The candidate is
kept exactly as frozen; only the review stage is re-run, on the same SHA, at
most two more times; no developer session is opened for it. If the reviewer
still produces no verdict the story ends `REVIEW_UNRUNNABLE`, naming the last
failure and the command that re-runs the review stage later
(`aisef run --verify-only --story <id>`). A structured `block` is still a
verdict and still returns the story to the developer; so do failed tests and
lint, as before. Evidence: the `review` tool run carries `outcome`, `unrunnable`
and `review_attempt`; every review execution is recorded against the candidate
SHA; the journal's `review.completed` step records `outcome`,
`review_executions` and `developer_attempts`. Prior review evidence is reused
only when it holds a completed verdict — an incomplete review, including the
1.7.3 shape `review could not run: …`, never satisfies freshness, and
`--verify-only` re-runs the review on the same candidate. A story resumed with
deterministic checks green on its HEAD and an incomplete last review resumes at
the review stage, without a developer session. `--verify-only` names the same
outcome when its single re-run is cut again. Two reviewer-integrity cases that
were `[block]` findings are execution failures now, retried the same way: a
reviewer that modified the working tree (reverted, as before) and a reviewer
that committed — the candidate moved — and the worktree is put back on the
frozen candidate so the retry reads the version being scored; the reviewer's
commit never becomes a candidate.

Unchanged on purpose: a reviewer answer with no JSON block is still read by the
text parser as a verdict (as since 1.4.x); Bandit/SAST behaviour; every other
open defect (D-002, D-003, D-011, D-024).

## 1.7.3 — 2026-09-15

A corrective release for the defects the first dogfood run of the public
`aisef==1.7.2` package found (LedgerLock, OpenCode 1.18.29, Windows 11, Docker
Desktop — intake `closure-evidence/dogfood/ledgerlock/`). No feature, no gate
softened, no waiver; every fix has a regression that was red on 1.7.2
(`tests/test_dogfood_ledgerlock.py`).

**A terminal plan deadlock rests on the structured verdict only (D-026, lỗi 180).**
The reviewer wrote "So [stuck] doesn't apply." in its reasoning; the text parser
split the tag out, exempted `[stuck]` from needing a path, and the union with the
JSON made one negated sentence the story's terminal verdict — while the JSON said
`block` with three real findings. Text still blocks (fail closed); only the
machine-readable verdict can end a story or an `improve` loop, and a `stuck`
verdict with no items keeps its synthesised line. `Attempt.plan_findings`,
evidence detail `plan`.

**The python preset's image now contains the tools it declares (D-028, lỗi 182).**
`python:3.12-slim` carried neither pytest nor ruff; every tool call is a fresh
`docker run --rm`; `aisef doctor` called the image "(matches stack)". The preset
names an image the harness **builds** from a pinned recipe
(`aisef.harness.verify_image`: base by digest, tools by version, name carrying
the recipe digest — `aisef-verify-python:<digest>`); `aisef doctor` builds it and
probes every declared tool where it will run; `aisef run` refuses to start
sessions when a declared image lacks a declared tool; tool evidence records the
image name **and** content id. Measured 2026-09-15: the old image — `MISSING`
pytest and ruff; the built image — both present, 15 s to build.

**A missing test runner is UNRUNNABLE, never a red test (D-029, lỗi 183).**
`No module named pytest` (exit 1) was read as "the most recent test run is still
failing" and sent three sessions after code that was not at fault. Every
non-passing tool run now carries an outcome kind in evidence and the run log —
`TEST_FAILED` / `TOOL_FAILED` / `TOOL_UNRUNNABLE` / `ENVIRONMENT_FAILURE`.

**The turn cap and the clock kill the whole process tree (D-027, lỗi 181).**
Sessions ran 75–186 turns against a cap of 40: `proc.kill()` hit the `opencode.CMD`
shim, node lived on holding the pipes. Clients spawn in their own process group;
the cap, the timeout and an interrupted orchestrator tear the group down
(`taskkill /T` on Windows, `killpg` elsewhere).

**Coverage data files are the test tool's, not the agent's (D-030, lỗi 184).**
`.coverage` / `tests/.coverage` no longer trip `diff-scope` and are taken back
out of the candidate before it is frozen.

**Parallel scheduling weighs the effective write scope (D-031, lỗi 185).** The
shared verification config files (`pytest.ini`, `conftest.py`, JS runner
configs) are a *bootstrap* grant: a story may create them undeclared only while
no story of the sprint has merged and the file does not exist. Two stories
holding the same grant do not run in one wave — `aisef run` re-splits a planned
wave at run time, the first story runs alone, and after it merges the rest run
in parallel as planned. A later story that must touch such a file declares it.

**`aisef status` names an orphaned claim (D-025, lỗi 179).** A `running` story
whose `claimed_by` is a dead process on this host is reported as `ORPHANED`;
the read model changes nothing on disk — the next `aisef run` reconciles, as
before, and the guide now says so.

Regression coverage: `tests/test_dogfood_ledgerlock.py` (30 tests), plus
existing tests updated where they scripted a text-only reviewer.

## 1.7.2 — 2026-09-15

**A release is identified by its product, not by which commit is HEAD (D-022).**
After 1.7.1 was published and G1 read PASSED, one documentation-sync commit —
touching nothing that ships — made G1.0 FAILED, because the criterion was
`HEAD == closure_target_sha` with a two-entry filename allowlist as the only
exception. Recording evidence *about* a release invalidated the release, so the
cure was another release whose evidence would invalidate it again: a loop with
no fixed point. The closure gate now models two planes. The **product plane**
(runtime source, package data, build configuration) is identified by
`release_source_sha`, a content digest over the tag's tree, and the wheel/sdist
digests on PyPI; the **assurance plane** (tests, evidence, records, docs) may
move after publication. G1.0 compares the product digest at HEAD with the one
at the release, and binds the artifacts observed on PyPI to the tag's blobs
member by member; commit-bound evidence is stale only when a product or
assurance path changed; a path no rule classifies is `UNRESOLVED` and blocks.
The classification lives in `docs/closure-gate.json#planes`, the mechanism in
`aisef.control.planes`, the release manifest in
`closure-evidence/releases/<version>.json`, written from the tag and public PyPI
by `validation/record_closure_evidence.py manifest`.

**G6 is bound to a release node (adjustment 8).** The external-validation record
must declare the product version, tag, `release_source_sha`, artifact digests,
protocol version and the digest of the immutable instructions bundle it
followed, and each is compared with the manifest and the bundle on disk. A
record for one release is not evidence about another; instructions edited after
the run cannot relabel an old record. The record lives inside the bundle at
`closure-evidence/external-validation/<version>/REPORT.md`.

**G6.1 read the onboarding digest under a key its writer never wrote (D-023).**
The probe looked for `sha256` and `version` and recomputed the digest with its
own copy of the algorithm, while `aisef.control.onboarding` writes `digest` and
hashes commands only. The first real record would have failed as "onboarding
surface changed". The copy is deleted; the probe reads through the writer.

Nothing else changed: no feature, no gate softened, no waiver. Regression
matrix in `tests/test_release_identity.py`, including the permanent fixed-point
invariant (release → validate → record → close converges without another
release unless the product changes).

## 1.7.1 — 2026-09-15

**A pinned path is the same string on every platform.** `aisef closure --pin`
built its record key with `str(path.relative_to(root))`, which on Windows yields
`docs\BENCH-PREREGISTRATION-C2.md` and elsewhere `docs/BENCH-PREREGISTRATION-C2.md`
— one file with two identities in a file that is committed and shared, so a pin
written on Windows is silently invisible to a probe reading it on Linux. The CLI
had the same bug in what it printed, disagreeing with the `REPORT_MD` constant it
echoes. Both now use `as_posix()`.


**Two POSIX assumptions in test helpers, found the moment CI could reach them.**
The full-history fix let the Windows job run tests that had never run there, and
16 of them failed for exactly two reasons. The closure-gate test helper pinned a
digest over bytes containing `\n` but wrote the file with default newline
translation, so on Windows the file held `\r\n` and every approval and pin test
read `contract is stale`. And the fake `opencode` used in bench selfcheck and
qualification is a Python script with a shebang and `chmod 0o755` — Windows does
not honour shebangs, so the adapter could not launch it, no session wrote its
log, and every attempt read as infrastructure failure. Neither is a product
defect. Both are fixed rather than skipped: the helper writes with `newline=""`
so the platform cannot rewrite the bytes a digest is taken over, and one shared
helper now materialises the fake client for all three call sites, adding a
one-line `.bat` launcher on Windows — same script, same stream, only the way the
OS starts it differs. Those three sites had duplicated the write-and-chmod, which
is why one platform bug appeared three times.


**The release CI checks out full history, so tests that rebuild a historical
commit run instead of erroring.** 1.7.1 is the corrected publishable release of
the 1.7 feature set; **1.7.0 was never published to PyPI**. The v1.7.0 tag was
pushed and its release workflow failed at the release-gate step with four
`git archive … exit 128` errors: the qualification-pipeline tests deliberately
rebuild a bench task from a commit in this repository's own history, and
`actions/checkout` clones at depth 1 by default, so that commit was absent. The
gate behaved correctly — `publish` was skipped and no invalid package reached
PyPI. The fix is `fetch-depth: 0` on every job that runs the whole suite; no test
was skipped and no materialization coverage was weakened. Two static checks now
hold the invariant, anchored on the command rather than the job name so a new
job running the suite is caught too. The functional 1.7 feature set is unchanged,
which is why this is a patch bump.

## 1.7.0 — 2026-09-15 (tagged, release CI failed, never published)

Everything below landed **after** `v1.6.0` was tagged and published, so none of it
is in the 1.6.0 wheel. Three of these paragraphs were first written into the 1.6.0
section by parallel agents and moved here: the release was already on PyPI, and a
changelog that credits a published release with fixes its artifact does not carry
is the same class of untrue statement this project spends its time removing.

**The closure gate asks about classification integrity over a cohort, not over
every row ever written.** G5.2 used to demand `exit_status` on every row of every
`.bench*/results.jsonl` in the tree. 339 of 411 rows were produced before that
field existed, and the only way to satisfy the old rule was to invent a status
for sessions that no longer exist — the same guess that turned three cut sessions
into C-1b's +0,06 artifact. A cohort is now declared in
`closure-evidence/cohorts/<id>.json` before it is scored, and the bar for one
backing a current claim is higher than the rule it replaces: identity bound to
the pre-registered protocol digest and the benchmark execution SHA, attempt rows
and a session ledger pinned by digest, every session carrying an explicit status,
retries reconciling as `sessions == infra_retries + 1`, no attempt whose final
session was cut carrying a non-infra exit status, no exclusion without a recorded
reason, and totals recomputed from the raw rows against a digest the report
itself must carry — so a report cannot drop a failing row, re-select its rows
after scoring, or state a number its own evidence does not produce. Cohorts
predating the schema stay `HISTORICAL_UNCLASSIFIABLE`: bytes pinned, never
rewritten, limitation recorded, and forbidden from naming a report.

**The retired-claim audit reads declared status instead of matching substrings.**
It failed in both directions on this repository. It missed `±0,08` because it
only knew the ASCII `±0.08` — retiring a number and restating it with a decimal
comma is not a correction — and it flagged the C-2 report for *explaining why*
`±0.08` was withdrawn, which is the opposite of asserting it. That is AD-22's
grep failing on `"http://"` inside URL validation, one gate over. A
`claim_registry` in the criteria file now lists each retired claim with every
surface form, and prose fences a mention with
`<!-- claim:WITHDRAWAL_EXPLANATION -->`. Text outside a region, inside a
`CURRENT_ASSERTION` region, or inside an unterminated region all count as current
assertions, so silence is never a shelter. The audited surface grew from four
files to eight, finally including the `BENCH-*` reports the contract always said
it covered.

**A frozen early-stop rule is enforced by the orchestrator, not by the operator
remembering it.** The C-2 pre-registration says two opening tasks at 6/6 across
both arms means the model is at the dataset ceiling — stop, report, do not burn
seven more hours for a column of 1,00s. On C-2 it fired after task two and ten
more tasks ran anyway. `tests/bench/stop_rule.json` transcribes the rule with its
source and that source's digest, `run-both` evaluates it after every task, and
the decision lands in `stop-decision.json`. Continuing past a fired rule now
requires `--ignore-stop-rule` and is recorded with `honoured=false` plus the
post-stop label, so data gathered afterwards cannot read as something the
protocol required. Already-collected data is never discarded: stopping means
stopping the scheduling of new tasks.

**Bench session metrics no longer merge cohorts.** The session-path pattern
matched `.bench*/run/<condition>/<task>/a<n>` but discarded the directory, so
three cohorts shared one key space and any overlap silently summed. Measured on
C-2: 90 keys for a 72-attempt cohort, 198 sessions, 35 cut. Scoped per directory
the truth is `.bench-c2` 72 sessions and **zero** cut, with all 35 cuts belonging
to C-1 and C-1b. The contaminated rates had already been published and two
conclusions built on them; both are corrected in the C-2 report. A second fault
fell out with it — one attempt vanished because the model printed its path
line-wrapped as `open-code` — so valid conditions now come from directories that
exist on disk rather than from strings a model emitted.

**A run records which client and which model produced it.** `agent_run` recorded
`spec.model` — the model *requested* — which is empty whenever no `route.*_model`
is configured. That is how all 145 sessions of the reviewer-qualification corpus
came to carry `model: ""`, and why its false-block and miss rates are "across
clients" rather than per client. It now records the model the **stream** reported,
with the requested one as fallback, plus a `client` field naming the adapter. Per
event, not per project: `todo-oc` holds both a `.claude/` and an `.opencode/`, and
evidence accumulates across runs. `reviewer_qual.report` splits every class count
by `client/model` — but only when the corpus holds more than one, because a column
of repeated `?/?` reads as "already split". `sprint START` and `pipeline START` in
`run.log` now name the client, which was the single most load-bearing fact about a
run and the one thing its own log did not say. Forward-looking only: no existing
corpus gains a `client=` line, so which client produced the four dogfood corpora
is still inference.

**A requirement was judged once per covering story, so the ledger reported 29
regressions that never happened** (bug 155). A story covering what earlier stories
already cover wrote those requirements red whenever one of *its own* criteria had
no test — todo-cli STORY-06-01 flipped five requirements belonging to three other
stories to REOPENED while all 65 tests in that run were green. The owning stories,
green in the same test event, wrote them green a moment later and the ledger
discarded that, correctly, because green on an unlanded candidate is not proof. Red
kept, green dropped, and which one survived came down to the order of a loop inside
a single event — which is not an ordering the ledger recognises. A requirement is
now judged once per run, aggregated before `observe` sees it: green from any story
whose criteria are all green in that run wins, and the absence stays recorded where
it belongs, on the criterion that lacks a test, as `untested`. Each false entry was
the kind that buys a paid repair story, and the O3 calibration had to work around
them as "artifacts". Re-measured with the same script: **29 → 4**, with the 15
confirmed regressors and the entire calibration table unchanged. The four that
remain are one run where the test tool never started, so nothing was read for any
story — a different absence, and a separate decision.

**`aisef report` and the dashboard reported one `gap` number for three different
absences** (ADR-009 O2). The ledger has known which kind each gap is since the
previous release, but `Ledger.summary()` did not carry the split, so the two reports
an operator actually reads showed a single total. The three counts now sit beside
the total in both — only when the corpus holds more than one kind, and never the
kinds counting zero. They cover every non-green behaviour, so they add up to
`gap + reopened` rather than to `gap`: printed beside `gap` alone, `todo-e2e` would
have read "1 gap · unbuilt 9". Re-measured over the four corpora: 167 behaviours,
49 non-green, 40 `unbuilt` · 4 `untested` · 5 `untraced`.

**A budget cap below what the project had already spent read as a framework bug**
(ADR-009 § Deferred). `run.cost_cap_usd` was validated for type and sign, never
against the project's own ledger, so a cap of `$0.50` on a project recording `$1.25`
spent was accepted at load and surfaced only later, as `BudgetGuard` refusing the
next paid call — the operator sees a refusal, not their own number. `aisef doctor`
now says it first, with both numbers and the fix, for `run.cost_cap_usd` and
`run.turn_cap`. Four states rather than pass/fail: no cap configured prints nothing
and never opens the ledger; cap above spend passes; cap at or below spend fails, at
equality too; and no ledger yet is neither pass nor fail, because there is nothing
to compare. The check never takes the ledger's lock and never writes it.

**The outward-facing pages claimed the opposite of what was measured.** The landing
page said AISEF "added governance and safety layers with near-zero measured cost
overhead" in the bullet immediately after one stating the harnessed arm spends 44 %
more turns. C-1 measured **+44 % turns and +51 % time**; C-1b measured +27 % turns.
The page asserted both at once and the false half was the marketing half. Also
corrected there: a benchmark bullet quoting only C-1's `0.64 vs 0.69`, which reads
as a measured degradation of 0.05 when the band is ±0.08 and C-1b reversed the sign;
a `$ aisef doctor` heading over seven facts that command does not print; and a test
count given as 1,913 in one place and 2,391 in another. `docs/SALEKIT.html` declared
**no `<meta charset>`** while containing UTF-8 em dashes, so twelve of them rendered
as `â€"` — found by loading the page in a browser rather than by reading it. Its
footer said `v0.8.0`, eight releases stale and predating PyPI. Stale counts fixed
across both: 58 → 69 config keys, 9 → 10 guards, 28 → 30 bench tasks, 175 → 207
real-agent sessions, "three cohorts" → four, 31 → 130 taxonomy rows. Both pages now
carry the reviewer-qualification rates as measured, and neither presents the model
review as a safety net, because the measurement says it is not one.

**The `tool-bypass` message promised a move the guard refused** (bug 156). Its
block text ends with "Narrowing a run for debugging (extra arguments, a single
file) is not blocked" — and on an npm / pnpm / yarn / bun project it printed that
sentence while blocking exactly that: `npm test -- tests/a.ts`. The command key
collapses those managers to `(manager, script)` so a flag-only difference cannot
slip past (a project declaring `npm test` must not be bypassed by `npm test
--silent`), but the same collapse discarded positional arguments, so a genuine
narrowed run carried the identity of the whole suite. A developer on a Node
project therefore had no legal way to narrow a run while debugging — the dead end
of bug 118, made worse by a guard contradicting itself in the same breath. The
collapse stays; narrowing is now decided on positional arguments — a token not
starting with `-` after the script name, or anything after `--`. Found twice
independently while re-measuring the two usage guides against the code, which is
also why both guides had written down the old workaround.

**The failure taxonomy's own header had drifted.** It said "147 lỗi · 124 dòng · mã
22–147" directly above the command that returns 132 rows, and conflated the highest
bug code with the number of bugs — 26 and 27 have no rows, so the real count is 153
against a highest code of 155. The header now states both, with the command for
each, and says the two-unit gap between the READMEs' figure and the true count is
deliberate and pinned by a meta-test.

**A second docs pass, eight more drifts, and one of them was the rule's own
document.** ADR-009 said three things at once about O1–O4: "All four closed",
"Three remain: O1, O2, O4", and "O2–O4 remain open" — while being the document
that states the rule *a statement of the form "N items remain" must carry the
list, on disk, in the same document*. All four are closed, and each stale
sentence was true when it was typed: the four closures merged from parallel
worktrees inside one day, so every count of the survivors was a number only its
own branch could see. Prose is the last tier here with no guard, which is why
the same thing happened to the config-key count twice — 58 to 68 at 06:00, and
stale at 06:04 when ADR-009 O3 added the 69th key from another worktree. Also
corrected: both READMEs still listed the Serena write-scope limitation the
roadmap had already retracted; ADR-007's header still said EXPERIMENTAL against
its own frozen addendum; and two "cannot be settled from disk" items are now
settled forward-only — `run.log` and `agent_run` record the client and the model
since 1.6.0, which tells the *next* reader what produced a corpus and tells us
nothing new about the 145 sessions already on disk. Two numbers were checked and
deliberately **not** changed: the 68 in the 2026-09-12 assessment was correct at
the SHA that section names, and V1-READINESS's conformance expiry was correct
four hours before the table was refreshed. Dated measurements get a dated note,
never a rewrite.

**A verification run that timed out left the project's dev server holding its
port** (bug 154). The degraded runner — everything outside Docker — killed only
the direct child, so a server the project's own test command had started,
Playwright's `webServer`, survived it, reparented to PID 1 and kept port 8123.
On `todo-oc` such an orphan, whose working directory was a story worktree the
harness had since deleted, answered 404 to every path; 404 is not enough for
`reuseExistingServer` to reuse it, so the next `pre-deploy` failed `e2e` and
`accessibility` with `Address already in use` — a symptom that points at the
project rather than at the harness. Killing the orphan and rerunning, with
nothing in the project changed, turned both green. Commands now run in their own
process group and a timeout kills the whole tree, as the Docker path already did
with `docker rm -f`; interrupting by hand tears the tree down too, since the
child no longer receives the terminal's SIGINT.

**The release gate's dogfood acceptance check has not run since 2026-09-06.**
`release.yml` invokes the gate without `AISEF_ACCEPTANCE`, so that assertion
skips and the log reads `OK (skipped=1)` — which reads as covered. The corpus it
was written for (e9) no longer exists on any machine. Re-measured on `todo-oc`:
scope, story completion and the seven upstream human gates pass; `Dockerfile`,
`CI workflow`, `runbook`, `isolation` and `verification` do not, for reasons
that belong to that project, and the `pre-deploy` gate is unapproved because
approving it is a human decision. The test now states all of that where it
skips, and the release workflow prints the skip instead of swallowing it. The
assertion itself was not relaxed.

## 1.6.0 — 2026-09-14

Measured by reading the developer session OpenCode actually ran, not by
reasoning about what it should have run.

**A story could not pass the `TDD` check on OpenCode, ever** (bug 116). The
prompt tells the developer that only runs through `aisef tool` become
evidence and that the gate reads evidence, not claims. Across ten sessions on
`todo-cli`, the developer ran `npm test` directly ten times and `aisef tool
test` zero times — so every `test` event in the story's evidence came from the
harness's own verify pass, one green run per candidate, and red-before-green
had nothing to compare. A rule only the prompt states is not a rule. A new
guard, **`tool-bypass`**, blocks running the project's declared test/lint/sast
command directly and names the recorded command to use instead. Narrowing a
run for debugging (extra arguments, a single file) is not blocked — recording
a subset as `test` would make part of a suite look like a green one.

**A tool run that records nothing said `✅`** (bug 117). `aisef tool test`
outside a story session ran the command and recorded no evidence, with output
indistinguishable from a recorded run. It now says so.

**`TDD` no longer blocks what the nop control already cleared** (bug 118).
Red-before-green is a proxy for "do these tests verify the story"; the nop
control (ADR-005 V3) asks that question directly, by running the story's tests
at the parent SHA. On `todo-cli` STORY-01-02 the nop control passed and `TDD`
failed, and the story was blocked by the weaker of the two — with no legal
move left for the developer, whose implementation already existed from an
earlier attempt. A passing nop control now satisfies `TDD`, and says which
evidence proved it. `UNRUNNABLE`, `NOT_APPLICABLE` and `UNCONFIGURED` mean the
direct measurement did not answer, so `TDD` still stands alone there.

**The agent was handed a different build of `aisef` than the harness was
running** (bug 119). `aisef_argv()` returned the name `aisef` whenever that
name was on PATH. On the dogfood machine that name was a pipx install three
minor versions behind the source tree the harness ran from — so every guard
recorded across two days of runs came from code that had none of the fixes
under test, and nothing said so, because the old binary answers every call
successfully by the old rules. The name is now used only when `sys.argv[0]`
points at it; otherwise the harness hands over its own launcher. Version
strings were not used for this: `__version__` reads installed metadata, which
in a source checkout can match by accident.

**The nop control reported "not performed" when it had, in fact, worked**
(bug 120). Its worktree deliberately lacks the story's source, so at the parent
SHA the story's tests fail to import it — which is the control succeeding. The
generic rule that classifies "cannot find module" as a missing dependency
cannot tell that apart, and on a greenfield project's first story there are no
other tests whose names would prove the runner started. The run now compares
the missing module against the story's own changed files: the story's code
missing is the expected red; a real dependency missing still blocks.

**The compile report claimed a guard that was never wired** (bug 121). For
OpenCode it listed `completion` under "guards blocking at other hooks", while
the plugin it had just written has only `tool.execute.before` and
`tool.execute.after` — OpenCode's plugin API has no blocking equivalent of
`Stop`. `compile_for` read its claims off the guard table instead of the file
it generated. It now reports the hook points each client actually has;
`completion` is listed as post-hoc for OpenCode, and a test cross-checks every
"wired" guard against the plugin's own text. If you read `blocks_at_source`
from `compile-report.json`, OpenCode now reports `false` — 9 of 10 guards
still block at source; the flag means *all* of them do. The expectation that a
developer session leaves a guard trace now reads `guards_wired`, so the `guard
ran` gate check is unaffected.

**A story failed review on a sentence that raised nothing** (bug 122). The
text parser treats `[block]` anywhere in a line as a blocking item — correct
for a tag glued to the end of a sentence, wrong for one inside backticks,
where the reviewer is naming the tag rather than raising it. Measured twice in
one run: a reviewer thinking out loud ("whether this is a `[block]` or
`[should fix]`:"), and a reviewer recalling an earlier review while its own
JSON verdict said `pass` with no blockers. Both failed a story. A tag after a
backtick is no longer read as an item; real blockers still reach the gate
through the JSON block, which the two sources are unioned from.

**A rerun told you to delete a branch holding three attempts of committed
work** (bug 123). The harness copies `.claude/settings.json` and `.opencode/`
into each story worktree as untracked files; `refresh` cleared them with `git
checkout --`, which only restores *tracked* files. The day a project commits
one of those paths, git refuses the merge before reaching any conflict —
"untracked working tree files would be overwritten" — so no file was in
conflict, the message said "conflicts in unknown files", and it advised
deleting the branch. Untracked copies are now removed before the merge and put
back after; and when nothing is in conflict the error quotes git's own reason
and says to clean the worktree, which is what actually fixes it.

**Reviewers now see what the candidate already proves** (bug 124). A story
spent all three attempts blocked by a single security finding — "lstatSync
swallows ENOENT, so the symlink check never runs" — while the candidate
shipped a green test named `AC-STORY-01-01-4: save refuses to write to broken
symlink target`, and `lstat` on a broken symlink does not raise ENOENT at all;
it returns the link. The reviewer had no way to know either: its `validation`
slot read "standard gate only". Both review prompts now receive `proven`, the
story's criterion-tagged tests green at that exact candidate. This is not
absolution — a green test can sit over broken code, which is worth reporting —
but a blocking item that contradicts one of them must name the test and say
why it does not cover the case.

**`tool-bypass` no longer fires in review sessions** (bug 125). It blocked
`npm test` inside a reviewer's session in the same run the `proven` slot
landed — one fix stopping a reviewer from doing what the other had just asked
it to do. The guard exists so a run becomes evidence, and evidence is per
story; a reviewer deliberately has no story id, so `aisef tool test` would
record nothing for it either. It now applies only where a story id is present.

**A plan defect reported as a client problem, six sessions late** (bug 126).
A story whose four criteria had already been shipped by an earlier story
failed `tests verify story` twice with exactly those criteria — no test can be
red at the branch point for behaviour already on the main branch. The
developer worked that out and correctly wrote nothing, which the harness read
as a no-op session, spent the whole infrastructure budget reopening, and
reported as "sessions kept producing nothing to grade". Two graded attempts
failing that check with the same criteria now stop the story immediately, as a
plan deadlock that names the criteria and says to fix or drop them.

**A session that declines to write is a decision, not a failure to retry**
(bug 127). Cut sessions and no-op sessions shared one budget although they mean
opposite things: a cut session had work in flight, a session that ran clean and
wrote nothing has decided — and re-opening it with identical context returns
the same decision. Raising the infrastructure budget to survive a client with a
22–32% cut rate therefore made this case worse: one story spent six sessions on
a verdict it had after two. Two consecutive no-op sessions now stop the story,
a cut session breaks the streak, and the plan diagnosis from bug 126 is
preferred when the last graded verdict explains it.

**The planner's favourite split produces stories that cannot pass** (bug
128). On a full six-epic run, 4 of 13 stories died because their criteria had
already been delivered by an earlier story — more than every other cause
combined. Three epics were split as "implement command X" plus "error cases of
command X", against the same single file; any competent implementation of the
first covers both, and the second story then has no legal move, because its
tests are green before its own code exists. The `stories` gate now warns when
two stories in one epic declare exactly the same write scope (a warning, not a
block — splitting one file across two stories is sometimes right), and the
`epics` phase is told that a story must add behaviour no earlier story
delivers, and that separability is a property of code, not of prose. Replayed
against that plan, the warning names all four pairs and no others.

**`ledger.json` is refreshed when a sprint ends** (bug 129). The behaviour
ledger is a projection every consumer rebuilds from evidence, so nothing
depended on the file — but only `aisef report` and the improve loop wrote it,
so between runs it stood still. After a six-epic run it said every behaviour
was a `gap` while the projection held 34 verified and 5 reopened, and that file
gets committed as if it were the truth.

**A session that ran out of turns is now graded, if it left work** (bug 130).
`if not result.ok: return attempt` sat before the candidate freeze, so a
session that hit the turn cap was treated as a broken session even when its
work was sitting committed in the worktree. Measured after switching the model
behind the dogfood to MiniMax-M3: three sessions in a row hit the 40-turn cap,
each having committed 68 lines of tests, and the story spent its whole quality
budget without ever producing a gate verdict — so the next developer got no
feedback and the deadlock detectors had nothing to read. Running out of *turns*
is not the same as writing bad code; the gate decides that, and half-finished
work still fails `test`, `criteria have tests`, the nop control and review.
Infrastructure statuses still return early, because the retry costs no quality
attempt and regrades the same tree. Worth noting how it surfaced: the older
model wrote nothing and stopped, the newer one exhausted the cap — one gap, two
symptoms, and only one of them had ever been seen.

**The injection guard left a vanilla-JS story no legal way to render a list**
(bug 131). It blocked every `.innerHTML =`, including `innerHTML = ""` — which
cannot inject anything and is the ordinary way to clear a container before
rebuilding it with `createElement`, the very API the rule wants. Worse, it
answered with SQL advice ("use parameterization"), so an agent that had already
written an `escapeHtml` helper had no idea what would satisfy it: it spent two
40-turn sessions reading the harness's own evidence files trying to work out
the rule, and wrote nothing. The empty string literal is now exempt, everything
else still blocked, and each injection rule states its own alternative.

**A browser story could not satisfy `criteria have tests`** (bug 132). Its
acceptance criteria are behaviour in a page, so their codes can only live in
e2e test titles — and the check read names from the unit runner only. Two
layers were involved: `harness.tools.record` parsed test names only when the
tool was `test`, so an e2e suite recorded zero names even though `testlog` has
understood `playwright-list` all along. Measured on a single-screen app that
never passed a story in three runs; the agent read the framework's own source
to work out why, then ran out of turns.

Names are now parsed for every suite whose output a parser recognises, and the
check unions criterion-coded names from every green suite at the candidate,
naming which runners it read. The requirement is unchanged: each criterion
needs a test bearing its code, green at this build. A red suite contributes
nothing, and neither does a failed test inside a green one.

**The developer is told not to read the harness** (bug 133). Nine consecutive
sessions across three runs ended at the 40-turn cap with the working tree
unchanged. The transcripts show all forty turns going into `_bmad-output/`
evidence files and then `find / -name aisef`, hunting for the framework's source
to work out the gate rules. The prompt already carries what a story needs, and
knowing a gate's rules does not negotiate with them. Worth noting the older
model hid this: it wrote nothing and stopped early, so nobody saw what the turns
were being spent on.

**A suite that matched no tests is no longer reported as failing** (bug 134).
`verify.accessibility` is `playwright test --grep @a11y`; until some story
writes an `@a11y` test that command finds nothing, and every story of the
project was told accessibility had failed. "Not configured is not red" has been
the rule for the `test` tool since bugs 2 and 8 — the other verification kinds
never learned it. They now report it as unrunnable, with a reason that names
both possibilities, and still block the story, which is the honest outcome.

Bug 132's fix also needed a second pass: the `qa:*` recording path calls
`store.tool_run` directly and never went through `harness/tools.record`, so
e2e still recorded no test names. Caught because the next run printed exactly
the sentence the new gate message had been given for it.

**The isolation check no longer tells you to revert your own commit** (bug
135). It asks whether the main branch moved during a session, then reports one
cause: the agent escaped its worktree, revert it. A commit made by the operator
while a run was in flight looks identical from that angle, and "revert and
re-run" is then advice to throw away their own work. The two causes have
opposite remedies, and the tree says which: story source is one thing,
`_bmad-output/` is the harness's own record. When only harness artifacts moved,
the message says so and does not suggest reverting. Still fatal — that session
cannot be graded either way.

**One full `aisef qa` pass could mark every later story stale forever** (bug
136). `evidence matches candidate` reported stale evidence while all twelve of
the attempt's own records carried the right build. The culprits were `qa:unit`,
`qa:security` and `qa:mutation` — kinds the story does not declare, left at an
old SHA by an earlier full QA pass. The story will never re-run them, so their
records sit at that candidate permanently and the check blocks every story of
the project. Only checks the gate actually scores for a story can make its
evidence stale now; a kind the story *does* declare still can, which is the
question ADR-004 R1 exists to ask.

**Accessible names follow the ARIA order** (correctness, not a measured
failure). `render.mjs` computed a field's name as `labels[0] || aria-label ||
placeholder`, which inverts the spec and never looked at `aria-labelledby`. The
value feeds the "Input constraints" block of the developer prompt, so a mockup
that is correct by the spec — `<label>Search</label>` with `aria-label="Tìm ghi
chú"` — told the developer the constraint belonged to a field called "Search".
Order is now `aria-labelledby` → `aria-label` → `<label>` → placeholder →
title, verified in Chromium in both directions.

Recorded plainly because the first diagnosis was wrong: this is *not* what made
the mockup-map gate fail on the browser project. Component matching goes
through Playwright's own ARIA snapshot, which was already correct. Fixed
because it is wrong, not because it broke a gate — and it gets no bug number,
since nothing was measured failing because of it.

**Gate messages for e2e and accessibility were five lines of access log**
(bug 137). Playwright's `webServer` writes one line per HTTP request into the
same stream as the test results, so the tail of a failing run said `GET /
HTTP/1.1 200` five times and nothing about which test failed. `ToolResult.tail`
was given a noise filter for exactly this in September — for the `test` tool
only; the `qa:*` path had its own truncation. It now shares the filter, and
falls back to the raw tail when filtering leaves nothing.

**The egress guard blocked localhost** (bug 138). On a web story whose dev
server is `localhost:8123` — the address `app.base_url` declares and the
harness itself opens — the developer was blocked from looking at the page it
had just built. Localhost is not egress: nothing leaves the machine, and the
rule exists to stop undeclared connections *out*. This machine is now exempt by
all its names. A URL-parsing bug came with it: the host pattern stopped at `[`,
so `http://[::1]:8123/` yielded a host of `"["`. IPv6 literals are parsed now,
and an IPv6 address that is not this machine still blocks.

**A block now records which rule decided it** (bug 139). The role's tool
allowlist and the escaped-workdir check run at the orchestration layer for
every guard kind — deliberately, so all clients enforce them — so whichever
guard the client happened to invoke first took the credit. Evidence read `guard
injection BLOCK write · this role is not allowed to use tool write`, and anyone
auditing blocks by name would go and fix the injection rule. `Verdict` carries
a `rule` now; evidence and the run log use it, keeping `invoked_as` so the
original guard is not lost.

**The harness raced itself for the app port** (bug 140). The e2e suite runs
Playwright with a `webServer` on the same port as `app.base_url` immediately
before the mockup comparison, and does not always release it in time. The
comparison then refused the port as "already occupied by another process — not
this story's app", while printing a working directory that was exactly this
story's worktree. The screen went uncompared, so a behaviour verified through
it could not be re-verified, and `preservation` blocked the story as
unverifiable.

Bug 15's rule stands — a stranger's app must never be graded — so the port is
reclaimed only when the occupant's working directory is our own tree. And the
question asked afterwards is whether the *port* freed, not whether the pid is
gone: a child stays a zombie until reaped, so `os.kill(pid, 0)` keeps
succeeding long after it stops listening.

**A review reported 29 blocking items when it had found 2** (bug 141). A
reviewer that deliberates at length mentions its tags mid-sentence ("This is a
[block].", "the [block] tag is fine for this review") and restates its
conclusions in every summary section. The text parser counted all of them, so
the next developer received the same two problems fourteen times and the
operator read "29 blocking items" — while that same review's JSON verdict
declared exactly two.

The review prompt's format is `[tag] path:line — description`, and the path is
what separates raising an item from talking about one. A text item now needs a
real path token to count; `[stuck]` is exempt, being a verdict about the plan
with no file to point at. Restatements of the same item collapse, with
unlocated items deduped by their own text so two distinct ones stay two.
Replayed over eight real review files: 29 becomes 2, matching the JSON, and the
genuine blockers in the other reviews survive.

**All four remaining semantic issues of ADR-009 are closed** (O1–O4). Each was
measured on recorded corpora — no new model calls — and each produced a number
worth stating plainly.

**O1 — the reviewer is now qualified as a check.** `aisef/control/reviewer_qual.py`
scores every recorded reviewer session into six closed classes using what the
other layers proved at the same candidate, with the same three controls as the
machine checks. Over 145 sessions: **false-block rate 10.5%** (6 of 57 blocks, a
floor), **miss rate 34–39%** (27 of 70 passes), 12.4% undecided and never counted
as a pass. Direction is roughly 4.5 misses per false block, so probe C11's single
observation was the common case rather than the exception. The number that needs
no convention to interpret: of 20 consecutive reviews of an identical tree, **11
reversed the verdict**.

**O2 — a GAP now says what kind of gap it is.** `Behaviour.gap_kind` is projected
from the reason sentence the ledger already writes, so `ledger.json` gains no
hand-writable field. Over 167 behaviours: 40 `unbuilt`, 4 `untested`, 5
`untraced` — and those 5 were every criterion of one story whose test reporter
was not installed, which `improve` would otherwise have turned into five paid
repair stories. `untested` routes to a test-only story whose write scope *is* the
verification paths, so the guard enforces the distinction instead of prose asking
for it. One correction to the issue as written: the case it describes — behaviour
and test both present, only the trace tag missing — is not derivable from
recorded evidence at all, and has zero instances on disk.

**O3 — the preservation radius is calibrated, and stays at 0.** The weight is now
`story.verified_touched_weight` with the calibration table beside it in
`aisef/config.py`, regenerated from evidence by `validation/o3_preservation_radius.py`.
Nothing below 1.0 changes a single verdict; the first verdict any larger weight
changes is a *false* block; catching 11 of 15 real regressors costs blocking 7 of
17 clean stories. The finding that matters more than the coefficient: file overlap
is true of 27 of 32 stories, so it cannot rank the 47% that regress. That is a
predicate problem — preservation needs to be scoped by behaviour — not a weight
problem.

**O4 — `aisef cost` attributes spend to outcomes.** Only **4–22% of spend bought
an attempt the gate passed**; 78–96% went to sessions no gate ever passed. Named
causes, not a residual bucket: turn-cap exhaustion (52% of one corpus in 3
sessions of 165), stories that ended net ≤ 0 (71–84% of spend in three of four
corpora), gate-blocked rework (32–67%), environment failures (37% vs 2% between
two corpora). Review and security retry rounds are under 0.15% everywhere — ruled
out. The unit is stated per corpus and never averaged across kinds: the provider
priced 0% of sessions in three corpora and 1 of 180 in the fourth, so dollars
would have been invented. The command reproduces the prior E4 decomposition byte
for byte as a cross-check.

Two corpora the ADR's numbers rested on, `e9` and `par`, **are not on this
machine**. The 36x per-story cost gap is therefore a historical claim we could not
reproduce, and it is now labelled as one. It also needs no exotic explanation:
within a single surviving corpus the priciest story costs 63x the median and
bought nothing.

**Five defects found while measuring**, each with a regression test (bugs
149–153): a gap's reason froze at first observation so `gap_kind` could never
escalate; the trace-stuck marker matched only Vietnamese while the prompt
prescribes English; story complexity scored against the end-of-sprint
`ledger.json` while the gate reprojects from evidence, so 12 of 15 real
regressors were scored against fewer neighbours than existed — calibrating on
that would have been calibrating on a bug; `STABILITY.md`, a frozen API contract,
declared 9 guards against 10 in the code; and two bench runs sharing a directory
deleted each other's kept worktrees, which are cited as published evidence.

**The documentation was re-measured against the code** and thirteen drifts fixed.
The roadmap's claim that Serena write-scope interop blocks OpenCode from
completing dogfood runs is false — `todo-oc` merged 7 of 7 through OpenCode, and
the fix shipped in v1.3.0 by a route none of the item's three proposals named.
What still stands is narrower and now written that way. Counts corrected across
the board: 63 bugs to 147, 9 guards to 10, 58 config keys to 68, one release tag
three versions stale. Three claims that could not be settled from disk are
labelled unverified with the measurement that would settle them — including that
`run.log` never records which client a run used, which is worth fixing on its own.

**The benchmark is ready for its second column.** Correcting my own earlier
framing: the real-model wiring already existed and had run twice — cohorts C-1
and C-1b, both against real `9router/mycombo`, with deltas of −0.06 and +0.06.
Same model, same harness, sign flip: that is the shape of noise, and it sets the
band at ±0.08. Four measurement holes are now closed: token counts were sitting
unread in evidence while both reports called the cost column absent (one session
records 98,392 in / 1,487 out / 581,444 cache-read at $0.00); infrastructure
failures are classified and retried once, with the status on every row, without
excluding them from `pass@1` — 6 of 9 cut sessions still passed, so dropping them
is not a neutral correction; concurrent runs take a lock; and `--max-minutes`
gives a stopping rule that works when the cost cap cannot, since 72 attempts
against a turn-cap-exhausting model is 36 hours worst case. The selfcheck drives
the real runner and scorer against a fake binary, proves the two columns differ
in exactly the harness — byte-identical prompt, guard plugin on one side — and
labels itself as not a measurement. Pre-registration for the run is on disk
before any data exists.

**A story may no longer deliver a placeholder** (bug 148). marks-cli stopped at
EPIC-02 wave 1 with two of seven stories merged. STORY-01-02 had shipped a
dispatcher whose commands answer "not implemented", and its criterion — a stub
command exits 1, writes one `marks: ` line, nothing to stdout — went into the
ledger as VERIFIED behaviour.

That killed the epic twice over. Preservation blocked STORY-02-01, the story that
implements `add`, for breaking a behaviour it is required to break. And the stub's
blanket failure has the same observable signature as STORY-02-01's own error-path
criterion — exit 1, one stderr line, store untouched — so that criterion was
already satisfied at the branch point and no test for it could be red. The story
deadlocked and the four stories behind it were never reached.

This is neither developer overshoot (142) nor a plan that repeats itself in prose
(128). The epics prompt now forbids a story whose deliverable is scaffolding, and
requires every criterion to be falsifiable at the branch point: it must assert
something not already true of the code that exists. The machine gate refuses
criteria that describe a placeholder, naming the story and the matched words.
Replayed against the real marks-cli plan it flags STORY-01-02 and none of the
other six.

**A `write_scope` pointing outside the project is now an error** (bug 147).
The residue of 146: the planner's out-of-repo entries survived the fix, and the
scope-width warning counted `tmp` and `foo` among the project's root modules.
Such an entry grants nothing — the guard refuses any write outside the project
root before it looks at scope — but it misleads every later reader and the plan
has no signal telling it to drop them.

**Runtime paths named in criteria are no longer treated as deliverables**
(bug 146). With 144 and 145 in place the gate could finally see marks-cli's
criteria, and it immediately reported three files STORY-01-01 had to create:
`/tmp/x.json`, `./.marks.json`, `/foo/.marks.json`. None is a source file —
they are the store path under `MARKS_FILE` and an example working directory,
named in Given clauses.

The `.gitignore` exemption that exists for exactly this case never applied:
`git check-ignore --stdin` fails the entire batch on the first path outside the
repository, and the caller read the empty result as "nothing is ignored". So one
mention of `/tmp/x.json` also cost `./.marks.json` its exemption.

Worse, the advice attached to the error — add it to `write_scope` — is what the
planner then did, producing a write scope pointing outside the repository. That
authorizes nothing (the write-scope guard refuses any write outside the project
root before it ever matches scope), but it makes the plan wrong and the error
permanent. Absolute paths and paths climbing out of the project are now skipped,
and filtered out before git is asked.

**A plan where every story had zero acceptance criteria passed every gate**
(bugs 144, 145). Found on the first run of a third dogfood project: `aisef plan`
reported six stories, and all six story cards printed `(none — machine gate will
block)` under Acceptance Criteria while the machine gate reported no errors.

The planner had written the label as plain text — `Acceptance criteria:`, no
bold, no heading — and listed criteria as bullets carrying their own codes. The
block regex knew only the bold and heading forms, so it matched nothing; the
bullet-splitting code that would have handled the rest was never reached. The
label is now recognised standing alone, anchored to its line and required to end
at the colon, so prose that merely mentions acceptance criteria opens no block.

The gate had a ceiling on criteria count and no floor. A story with none is not
a small story but an unverifiable one: `criteria have tests` has nothing to look
for and `tests verify story` returns PASSED on its "story declares no criteria"
branch. Zero is now an error that names the stories and both likely causes — the
document has none, or its criteria are in a shape the parser cannot read yet.

**A story branch is discarded when its criteria change** (bug 143). A failed
story keeps its branch on purpose — the next attempt builds on the last one —
but nothing tied that branch to the criteria it was written for. Amend the
story, which is exactly what the plan-deadlock message asks for, and the old
commits come back to answer a question no longer being asked.

On todo-oc STORY-04-02 the branch still carried `AC-STORY-04-02-1: textarea has
a visible placeholder` after AC-1 was dropped and AC-2/AC-3 were merged. The
developer opened a tree where everything already passed and wrote nothing in
twenty turns. The nop control held — those tests are green at the parent SHA, so
the gate refused the attempt — and the next attempt recovered, committing
"tighten tests so they fail at parent SHA". So the run was not lost; what it
cost was a whole attempt spent discovering the contamination and a second one
spent rewriting a previous attempt's tests, work that exists only because the
branch was carried across a contract change. The case the nop control cannot
hold is a stale test that *is* red at the parent: it passes the control while
its code labels behaviour it does not test.

The criteria are now fingerprinted into evidence each run — the criteria alone,
not the story card, whose harness-added scope paths move with every framework
upgrade. A changed fingerprint drops the branch and says so in `run.log`.
`--verify-only` is exempt: it grades the candidate that is already there.

**The developer now sees the whole plan, not just its own epic's status**
(bug 142). Four todo-cli stories deadlocked on `tests verify story` — their
criteria were already green at the branch point — and the git history named the
cause: STORY-03-01's developer had written `--done`/`--open` filtering, all of
STORY-03-02, and STORY-04-01's had written the `task not found` error path, all
of STORY-04-02. Not a planner writing redundant stories (bug 128's case) but a
developer working past its criteria.

Behaviour shipped early is already on the branch when the later story starts,
so no test that story's developer writes can be red at its branch point, and
the story becomes undeliverable — two sessions burned, then a hand edit to the
plan. The reviewer has had the plan-wide `roadmap` slot since bug 58; the
developer role never got it. It does now, with the consequence spelled out and
the measured cases named.

A third case, todo-oc STORY-04-03, reads differently: STORY-01-01 had already
written `role="main"` and `aria-live`, all of that story — and was right to,
because `qa:accessibility` grades every story. There the plan was at fault for
carrying an accessibility story at all. So the instruction excludes baseline
quality: accessible markup, validation and error handling are part of doing
your own story well. What you leave alone is what another story exists to
deliver.

**`run.infra_retries`** gives infrastructure errors their own retry budget.
They score nothing, so they never charged `run.max_retries` — but they shared
its budget, and on a client with a measured session-cut rate (22–32% on
OpenCode/mycombo, 2026-09-13) a story can spend everything on sessions that
produced no verdict. `-1`, the default, keeps the old coupling.

## 1.5.0 — 2026-09-13

A minor, not a patch, because two behaviours change.

- **Parallel stories corrupted the sprint state on Windows** (bug 115). The
  state store locks with a file lock, which is the right tool for another
  process and not enough for another thread on Windows, where a byte-range
  lock belongs to the process — so the second thread of a wave took it
  happily. Both then wrote through the same shared `sprint-status.json.tmp`,
  and one died with `PermissionError: [WinError 5]` on the rename, taking the
  whole sprint with it. A per-path `threading.RLock` now wraps the file lock,
  and each writer's temp file carries its own pid and thread id. Caught by
  Windows CI; 2 455 tests were green on Linux and macOS.

**An API key now goes only to the client that authenticates with it.**
`ANTHROPIC_*` used to be in the shared environment allowlist, so every client
session received the host's Anthropic key — and a client that can read such a
key uses it *instead of* its own login. If you run OpenCode against an
Anthropic-compatible endpoint using `ANTHROPIC_*` variables, add
`"clients.env_allow": ["ANTHROPIC_"]` to `.ai/config.json`.

**The acceptance report's traceability column asks whether the requirement has
tests**, not whether a test command exited 0 in one of its sessions. Projects
whose test runner ran zero tests will see `—` where they used to see ✅. The
number under it, `AC w/ Test`, was always the honest one.

Everything below came out of one day of running two projects end to end
through the framework — a browser app and a command-line tool, both driven by
a non-frontier model, both starting from a hand-written `docs/requirements.md`.
Every entry has a regression test and a row in `docs/FAILURE-TAXONOMY.md`;
`docs/DOGFOOD-2026-09-13.md` is the report.

- **The "criteria demand a file the story may not write" check was switched
  off for every English-language project** (bug 114). It filters backticked
  paths by proximity to a mutation verb, and every verb in that table was
  Vietnamese except `commit` — so the check returned nothing, silently and
  completely, on any English project. Measured: a story whose acceptance
  criterion named four `lib/commands/*.js` files outside its write scope
  passed the stories gate, and the guard blocked those writes three attempts
  and about twenty agent sessions later. English verbs added; paths covered by
  `.gitignore` are skipped, since a file git ignores never appears as an
  out-of-scope change and so cannot need write scope. A keyword heuristic is a
  heuristic *per language*, and a missing language turns it off rather than
  degrading it — so `_NETWORK_MARKERS` and `_IMPACT_MARKERS` got their English
  entries too, preventively, with no measured failure behind them.

  Validated on the plan that exposed it: the stories gate blocked, the
  split-retry loop sent it back to the planner, and the new plan's thirteen
  stories carry write scopes that contain the files their criteria name —
  zero gate errors.

- **The project's linter no longer lints the framework's own skills**
  (bug 113). `aisef setup` installs 155 skills into `.claude/`, and the
  project has to commit them — a story worktree is a checkout, so an
  uncommitted skill is absent where the session runs. Every linter the project
  configures therefore reads them: `npx eslint .` reported 116 `no-undef`
  errors in skill scripts and failed a story's lint check. The `node`, `react`
  and `python` presets now exclude `.claude`, `.aisef` and `.opencode`, and so
  does the fake-test scan behind the blocking `real tests` check — git lists
  those files as the project's, and they are not.

- **`doctor` resolves `npm test` before judging it** (bug 112). It read the
  command string, which for `npm test` says nothing, and told a project that
  had just enabled `--experimental-test-coverage` to add
  `--experimental-test-coverage`. Evidence first: if a recorded test run
  carries a coverage number, that settles it; otherwise the npm script is
  resolved through `package.json` and then read.

- **`**And** when …` opens a new acceptance criterion** (bug 111). Same
  chaining habit as bug 91, different keyword: every story in a plan came out
  with exactly one criterion, including stories that plainly described two
  scenarios. Two scenarios in one criterion means one test carrying that code
  satisfies the gate for both. Re-splitting the same `epics.md` — no model
  call — took the plan from 1/1/1/1/1 criteria to 1/2/4/2/2.

- **The framework's own installed skills counted as the project's source code**
  (bug 109). The skip list also existed twice — `baseline.py` kept its own copy
  of the literal, and that copy is the one its directory tree walked, so fixing
  one place left the baseline still listing all 155 installed skills. There is
  one list now. `aisef setup` writes 155 skills under `.claude/skills`, 213 of
  them carrying Python scripts, and the brownfield scan counted every one: a
  freshly created Node project read as brownfield with 216 source files and
  `py` as its main language. A survey of a project has to subtract the
  surveyor's own footprint.

- **`aisef plan` says when it is planning over existing code** (bug 110).
  Planning reads `docs/requirements.md` and nothing else, so a repository with
  code already in it gets planned as if the directory were empty. Measured:
  the first story was "Initialize Node.js project structure" with a criterion
  opening "Given a fresh directory with no files", for a repository whose
  `package.json` already had every field it asked for — its tests were green
  at the parent SHA, the nop control correctly refused them, and three
  attempts went into work already done. The brownfield mechanism existed
  (`aisef baseline`); nothing pointed at it. The warning also fires on a
  manifest alone — the run that found this had one source file and a
  `package.json` — and a greenfield baseline now names what is already on disk
  (`package.json` — `type`, `bin`, scripts, no runtime dependencies) instead of
  saying only "no source code yet".

- **A project that runs `node --test` is no longer granted write scope over
  four test frameworks it does not use** (bug 108). The scope narrows by the
  framework named in the test command; node's built-in runner was not in the
  table, so it fell through to "a JS project gets every JS test config" —
  jest, vitest, cypress and mocha config files, in a project that has never
  had any of them. A write scope is a permission.

- **A project can say it has no graphical surface** (bug 107). The ux step
  required a screen inventory from every project — "a single-screen app still
  needs its one row" — so a command-line tool had its six commands mapped onto
  six screens, and every story came out carrying a browser, mockup-map and
  accessibility contract for something with no DOM. `EXPERIENCE.md` can now
  say `**Screens:** none — no graphical surface`; the ux prompt asks for that
  line from a CLI, a library or a service; the mockup gate passes with a
  warning and writes an empty contract without needing a browser. A UI project
  that simply forgot its table is still an error, which is why the document
  declares it rather than the gate guessing from an empty list.

- **Eleven stories vanished because the planner wrote `Story 01-01`**
  (bug 105). The size gate asked for a split, the agent split correctly and
  rewrote the headings with a hyphen instead of a dot — the same shape the
  framework uses for story ids everywhere it speaks to a reader. The parser
  accepted only `Story 1.1`, so the next pass reported "no readable stories
  found in epics.md" and the plan pipeline stopped. `Story 01-01`,
  `Story STORY-01-01` and `STORY-01-01` are now read too.

- **The experience tables attach by command as well as by name, and the
  whole-table fallback is for single-screen documents only** (bug 106). A CLI
  state table describes behaviour by command (`done <n> prints …`), never by
  the screen's display name, so name matching found nothing and the bug 98
  fallback gave all six command surfaces all nine application-wide error
  states — which put every story over `story.max_screen_states` and blocked
  the entire plan. Widening a match also widens whatever counts its results.

- **The traceability table asks whether the requirement has tests** (bug 104).
  It read "some test command exited 0 in a session of a covering story", which
  a runner with no test files satisfies: the top table of the acceptance
  report showed ✅ for requirements the same report scored `AC w/ Test 0/6`,
  in a story that failed. Now every criterion of a covering story needs a
  test carrying its code — the same measure the per-story column shows.

- **Coverage from `node --test`, and no coverage number without tests**
  (bug 103). Node prefixes every line of its coverage table with `ℹ `, which
  neither coverage pattern matched, so a project that had just enabled
  `--experimental-test-coverage` was told by the gate to add `--coverage`. The
  same run shows the other half of the problem: with no test files at all,
  node prints `all files | 100.00` — a ratio with no denominator. A coverage
  number is now dropped when no test ran, and says why.

- **"Recurring infrastructure error" for a session that simply did nothing**
  (bug 102). A session that writes nothing is flagged `infra` so it does not
  consume one of the story's quality attempts — correct accounting. But the
  same flag was also read as the diagnosis, so a story that ended after an
  agent ran seventeen turns and changed no file reported an infrastructure
  fault, pointing the reader at the provider. Accounting and diagnosis are now
  separate; the reason says sessions kept producing nothing to grade.

- **`criteria have tests` names the runner it read.** An agent that puts the
  criteria codes in its e2e test titles was told "no tests with codes …" with
  no hint that only the unit run is read there.

- **An API key now goes only to the client that authenticates with it**
  (bug 101). `ANTHROPIC_` sat in the shared env allowlist, so every client
  session received the host's Anthropic key — including OpenCode sessions
  meant to run through the project's own router. A client that reads such a
  key uses it *instead of* its own login, as `aisef doctor` itself says, so
  the run authenticates against, and bills, an account nobody chose. Each
  adapter now declares what it authenticates with (`claude`: `ANTHROPIC_`;
  `opencode`: nothing), the shared list keeps only `LC_` and `AISEF_`, and a
  project that wants more says so in `clients.env_allow`.

  **Upgrade note:** if you run OpenCode against an Anthropic-compatible
  endpoint using `ANTHROPIC_*` variables, add `"clients.env_allow":
  ["ANTHROPIC_"]` to `.ai/config.json`.

- **`aisef run` says when guards are not compiled — or compiled but not
  committed.** Stories run in a worktree, which is a fresh checkout: an
  uncommitted `.opencode/plugin` is simply absent there, and the session runs
  with no guard at all while the gate fails `guard ran` afterwards. `doctor`
  had said this for a while; now the run says it too, before the session
  starts. The story gate already
  records `guard ran: not applicable — hooks not compiled for this client`,
  which is honest but arrives after the session is paid for. Until now a
  project that had never run `aisef compile` started a run exactly like one
  that had, and the difference is whether anything can block a write at the
  source. One line before the first session, naming the command that fixes it.

- **A missing file is not a guard block** (bug 100). The OpenCode adapter put
  every failed tool call into `guard_messages`, and `guard_blocked` means "the
  agent tried to do something forbidden" — it goes into the evidence, the
  acceptance report, and the benchmark's guard counts. A real run recorded a
  guard block whose entire content was `File not found: index.html`. The
  Claude adapter had always filtered through `GUARD_MESSAGE`, whose own
  docstring warns about exactly this.
  Guard output now carries a marker — `aisef guard <kind>:` — printed by the
  guard itself, so it survives a compiled plugin that only forwards stderr,
  and both adapters recognise the same thing. Messages thrown by an
  out-of-date plugin are still recognised.

- **Windows CI: the test that read a child process with the machine's codec**
  (bug 99). `subprocess.run(..., text=True)` decodes with the locale encoding —
  cp1252 on the runner — while every `aisef` process deliberately speaks UTF-8.
  The mismatch raises inside `communicate()`'s reader thread, which does not
  propagate: the call returns with `stdout=None`, indistinguishable from a
  program that printed nothing. Three red Windows runs and a "cause unknown"
  note in the test came out of that. Nineteen call sites in the test suite now
  name the encoding (the library code already did), and a meta-test walks the
  AST of `aisef/` and `tests/` to keep it that way.

- **The mockup prompt was empty because the experience tables named no screen**
  (bug 98). Components attach to a screen when the table's scope column names
  it — but the real column holds a region ("Header area", "List area"), and the
  state table has only two columns, `State | Treatment`, with no scope column
  at all. So a screen with five documented components and five documented
  states got neither, and the mockup agent was asked to build it from the
  purpose line alone: three runs of the same prompt produced three different
  screens, one of them missing the search box entirely. A table where no row
  names any screen is a table about the whole app; a table where some rows
  match is scoped on purpose and is left alone.

- **The readiness gate stopped contradicting itself** (bug 97). It printed
  "STORY-04-03 missing prerequisites to run: configure `app.dev_command`" and,
  ten lines below, "✅ 7 stories are all executable". The first came from the
  stories index — recorded when stories were split, before mockups existed and
  before anyone had configured a tool; the second was computed on the spot. A
  warning contradicted by the conclusion under it teaches the approver to skip
  both. Provisioning warnings are now recomputed at the readiness gate; the
  rest of the recorded gate (cycles, serialized epics) still holds and is left
  alone, and the stories gate still shows what it recorded.

- **"configure `tools.lint`" now says where the key goes** — `.ai/config.json`,
  named once per story, since there is no `aisef config` command.

- **One misplaced attribute emptied the design contract, and the gate passed**
  (bug 96). The mockup agent put `data-annotation` — the marker for "this part
  is documentation, not a commitment" — on the `<section data-state="primary">`
  itself, so the extractor subtracted the entire state subtree and wrote a
  contract with zero components, for a screen whose mockup had a textarea, an
  Add button and a search box. Nothing failed: the gate carries only a warning
  for an empty component list, and the later mockup-map step compares an empty
  contract against anything at all and passes. A state section is never an
  annotation, so the extractor now says so; re-extracting the same HTML
  recovered all three components without another model call.

- **Architecture decisions bound to NFRs reached no session at all** (bug 93).
  A decision declaring `Binds: NFR-1, NFR-3` parsed to an empty list, because
  the reference scanner only knew `FR-`; an empty list is not "binds
  everything" either, since bindings *were* declared. So in a real run the two
  decisions that defined the project — the localStorage key every note is
  stored under, and the 500 ms UI budget — were injected into no story's
  prompt. Non-functional codes now parse, a declared-but-unreadable binding
  list falls back to universal rather than to nothing, and a decision bound
  only to non-functional requirements is treated as cross-cutting, because
  stories declare the functional requirements they cover and would never join
  with it. The same fix bounds a decision's section at the next heading: the
  last one used to swallow the rest of the document.

- **A rule that continues past its own line is no longer cut off** (bug 94).
  `**Rule:** Every note is an object with exactly three fields:` reached the
  agent exactly like that — the table naming the three fields sat on the
  following lines and was dropped. A markdown field label opens a block, not
  a line.

- **Mockup state names are identifiers, not sentences** (bug 95). The skill's
  example used state names in its own language, so an all-English project got
  `data-state="không có ghi chú"` in its design contract — a value used for
  selecting and comparing, not for reading. The skill now calls for ASCII
  slugs (`primary`, `empty`, `no-results`) and leaves prose to
  `data-annotation`.

- **The acceptance-criteria parser was a way around the story-size gate**
  (bug 91). Blocked for writing a story with nine acceptance criteria, the
  planner did not split the story — it chained the scenarios as `**And**
  **Given** …`, and `_GIVEN` only recognised a line *starting* with
  `**Given**`. Six scenarios parsed as one criterion, the size gate passed,
  and the story file handed the agent a single `AC-…-1` code covering all six
  — which the behaviour ledger can mark VERIFIED on the strength of the first.
  The same blind spot ran the other way for unbolded `Given/When/Then`:
  every line counted as its own criterion, failing the gate on stories that
  were the right size. Any threshold counted on parsed output makes the parser
  part of the gate.

- **Stories keep their role block** (bug 92). `As a … / I want … / So that …`
  had to be three lines; real planner output folds the purpose into the
  I-want line, and writes `so I can` or `so it` more often than `so that`
  (six of seven stories in the run that found this). Every story file lost
  the block entirely, so the implementing agent never read who the story was
  for.

- **One epic, not one per heading** (bug 89). BMAD writes an `## Epic List`
  summary and then a detail section per epic, both headed `Epic N: …`, so
  `stories.index.json` carried two EPIC-01 entries: one with the goal and no
  stories, one with the stories and no goal. Sections sharing a number now
  merge.

- **The PRD gate no longer warns about requirements that are there**
  (bug 88). `- **NFR-1:** …` — the bold span holding the ID alone — was not a
  shape the parser knew, so a PRD with four non-functional requirements was
  recorded in the approval evidence as having none. A false warning in a
  SHA-bound record is worse than no warning: it teaches the approver to
  doubt a correct document.

- **The story-split step writes to the run log** (bug 90). It is code rather
  than a model call, so it never passed through `run_phase` and left no
  trace; when the size gate sent the pipeline back to re-run epics, the only
  log an operator has showed `phase=epics START` twice in a row with nothing
  between them. The split-retry loop also had no test until now.

- **`gate --replay` compares what the evidence actually recorded** (bug 87).
  `gate:verdict` has stored all seventeen checks with their outcomes since
  ADR-005 V4, but replay read only the blocking-check list, printed `·` for
  everything else, and reported "diff: none". A check drifting from `passed`
  to `unconfigured` — the exact silent degradation this tool exists to catch —
  was invisible. Replay now diffs outcome by outcome, falls back to
  blocking-only for pre-V4 records, and says which comparison it is making.
  Re-scoring all 21 recorded attempts of a real project with today's rules
  reproduces every verdict, check for check.

- **A cut session now actually reaches the retry path** (bug 86). The previous
  release recognised the signature and set `error` plus a retryable flag — on a
  result whose `ok` was still `True`, because OpenCode exits 0 when it thinks
  the session ended normally, and `exit_status_of` returns "ok" on the first
  line without reading `error`. Measured on the C-1b cohort: eight of
  twenty-four attempts ended on a cut session and the retry fired zero times.
  `ok` now also requires an empty `error`, and the test drives a real process
  that exits 0 rather than only the stream parser.

- **`reject` requires the artifact to exist, like `approve` does** (bug 85).
  On an empty project `approve prd` refused with "no artifact" while `reject
  prd --note x` succeeded, recording a verdict on a document that did not
  exist yet. When the planning phase then produced it, the gate already
  carried a rejection written before there was anything to read.

- **A mistyped guard name blocks instead of passing** (bug 84). The bug-81
  fix — usage errors exit 1 — collided with the hook protocol, where any exit
  code other than 2 means "not blocked". So `aisef guard <typo>`, which a
  stale compiled hook can easily produce, silently disabled that guard. The
  guard subcommand exits 2 on a usage error and says "blocking, not
  allowing"; every other command keeps 1. When a command serves someone
  else's protocol, that protocol wins over the local convention.

- **`init --stack python` now writes a test command this machine can run**
  (bug 82). It wrote `python -m pytest -v`; macOS and most current Linux
  distributions have only `python3`, so `aisef tool test` answered `exit 127:
  No such file or directory: 'python'` on the very machine that had just
  written the config. The preset picks the interpreter `shutil.which` finds.
- **"Could not run" is now visible where it is read** (bug 83). The harness
  already classified a missing tool as unrunnable, but `aisef tool test`
  printed `✗ test — exit 127` and left the reason inside the evidence detail,
  so a reader goes looking for the bug in their own code. The summary line
  carries `○ … NOT RUNNABLE: <reason>`; real failures keep `✗`.

- **`aisef <command> --project <dir>` works now** (bug 80). The flag was
  declared only on the root parser, so the order people actually type — and
  that `git` and `docker` accept — came back as a usage error. It is declared
  on every subcommand as well, with `default=SUPPRESS` so that putting it
  before the command is not silently overwritten by the subparser's default.
- **A typo exits 1, not 2** (bug 81). `argparse` exits 2 on a usage error,
  which is this CLI's documented code for "not ready yet" (gate unapproved,
  doctor failing). A mistyped command therefore read to CI as "not yet done"
  and scripts carried on. Usage errors now exit 1; the not-ready cases still
  exit 2, and a test pins both.

## 1.4.0 — 2026-09-13

A minor, not a patch, because one behaviour genuinely changes: a turn cap
that used to be ignored now stops sessions. If a project relies on
OpenCode sessions running past `run.max_turns` (default 40) to the
half-hour timeout, raise the cap deliberately — the number is enforced now.

Everything here came out of the C-1 benchmark cohort (12 hard tasks, 3
attempts, 2 conditions, a non-frontier model) and the cost decomposition
that ran beside it, both reported in `docs/`.

- **`skills.inline` is gone.** ADR-003's mechanism B inlined the top-scoring
  skill's SKILL.md into the prompt. Two A/B runs on real agents reported
  `used` 0/0 in both branches while the inlined branch carried ~8.8k extra
  prompt characters and failed exactly as often. A flag that is off by
  default, that nobody turns on, and that has code to maintain is debt: the
  key is retired (an old project declaring it loads with a warning naming
  the measurement) and the code is deleted.
- **The OpenCode adapter enforces `run.max_turns`.** The CLI has no
  `--max-turns`, so the cap was a number nobody read — measured: a session
  declared a cap of 40, ran 61 turns and stopped only on the 1800s clock.
  The adapter now counts turns on the event stream, kills the process at the
  cap, and reports `max_turns` rather than `timeout`.
- **A session the CLI cut short is no longer counted as an agent failure.**
  When the model emits a tool call the CLI cannot parse, the session ends
  there; the adapter recognises that ending and marks the run retryable
  infrastructure.
- **Guard messages advise per command.** Recursive delete stays blocked
  whatever the target, but the message now explains why a path filter cannot
  save it and that caches need not be deleted — the one guard block measured
  in the C-1 cohort was a `__pycache__` cleanup told to "report to a human".

- **`aisef dashboard` prints the four numbers an operator asks weekly**: cost
  per ISO week, net VERIFIED behaviours and behaviours per dollar, open gaps,
  and the age of the conformance table. A provider that reports no cost says so
  rather than printing $0.00, and a missing `docs/CONFORMANCE.md` says "could
  not read" rather than an age of zero days.
- **The budget warns at 80% of a declared cap**, with the real numbers in the
  message, once per dimension (the flag is on disk, so a second process does
  not repeat it). Blocking at the cap was already there and still happens
  before the model call — but the first time anyone heard about it was the run
  stopping mid-story.

## 1.3.1 — 2026-09-12

A same-day patch. 1.3.0 shipped a project template that froze all 68 defaults
into every new project, a Windows path bug in memory scoping, and a retry loop
that treated "please wait" as "try again immediately". None of it changes a
gate's verdict; all of it was found by running the thing.

### Fixes

- **`init` no longer freezes the framework's defaults into your project**
  (measured today: `.ai/config.json` went from **68 keys to 4**). Writing every
  default meant two things went wrong quietly: a newcomer could not tell which
  line mattered, and when the framework changed a default — which has happened,
  `context.max_preservation_chars` 1500 → 1200 — every existing project silently
  kept the old number forever. The file now carries only what the project
  actually decided plus the keys you *must* declare (today: `tools.test`).
  Reading is unchanged: `load` still merges with `DEFAULTS`, so nothing is lost.
- **A backslash path no longer slips past memory scoping** (bug 75, Windows).
  Scope matching compared raw strings, so a record scoped to `src\work` did not
  match a query for `src/work` — the record simply never came back, with no
  error. Both sides are normalised to POSIX form before comparison, and
  `src/work` still does not cover `src/workers/job.py`.
- **A rate limit is "wait, then retry", and the harness was not waiting.**
  `429` now has its own exit status, and `retry_delay_seconds` reads the delay
  the provider actually stated (`Retry-After` header, error body, or prose like
  "try again in 27s"), capped at 300 s so an absurd number cannot turn a retry
  into a hang. Retrying instantly spent the whole infra budget in seconds
  against a provider that was only asking for a pause.
- **An expired or missing key is no longer retried as infrastructure.** `401`
  and friends map to `auth`, which is outside the retry set, and the error now
  names the credential environment variables it looked at — names only, never
  values. Measured before the fix: three attempts, 176 s each, $0 recorded,
  nothing learned.
- **The published wheel no longer carries the benchmark's fake agent.**
  `SimulatedWeakAdapter` existed to fake a weak agent for bench runs and was
  shipping to every user; it now lives in `tests/bench/`.

- **Every stack preset now writes a test command that prints test names.**
  `init --stack python` wrote `python -m pytest`, and `doctor` then told you two
  gate checks would be "not configured" — on a project you had just created, in
  the first minute. Adding `-v` (and `--reporter=verbose` for vitest, `-v` for
  go) costs no dependency and closes that. Coverage still needs a plugin, so it
  is still yours to declare.

### Added

- **`aisef status --attempts`** — where attempts actually end, read from
  evidence rather than from memory: how many passed, how many were blocked at
  the gate and by which check, how many never reached a verdict. On a real
  10-story project it reported 34 attempts, 26% passed, and `review` as 18 of
  19 gate blocks.
- **`aisef doctor` names the agent credential it found** (again, names only).
- `RunResult.model` records which model actually answered, so two cohorts run
  behind the same alias can be told apart afterwards.

## 1.3.0 — 2026-09-12

Sixty-one commits had accumulated behind `v1.2.31` (2026-09-09): seven real
bugs from a greenfield end-to-end run, three cross-tier invariants, the v1.3
benchmark protocol, and this release's own housekeeping. Nothing here changes
a gate's verdict on evidence that was already correct.

### Cross-tier invariants (ADR-009)

- **Findings are objects now, not lines of text.** Every advisory claim is a
  `Finding` (`aisef/control/findings.py`) with a stable 16-hex id computed over
  `(source, trust, file, line, body, behavior_id, scope)`, an explicit
  lifecycle (`OPEN / CLOSED / REOPENED / SUPERSEDED / STUCK`), and one rule that
  closes bug 61 for good: closing without evidence requires both
  `force_prescription_match=True` and a matching `previous_prescription`. A
  reviewer can no longer reject the fix it prescribed by rewording the
  complaint. `agent` trust is rejected at construction; reviewer and security
  records must carry a 64-hex `contract_authority` digest.
- **The dev server now belongs to a candidate.** `AppServer` takes an optional
  `lease_root` / `run_id`, holds a non-blocking flock over
  `.aisef/lease/port-<run_id>.lock`, and probes `GET /_aisef/identity` before
  it believes a server is ready. Two runs of the same project can no longer
  grade each other's app — the failure mode that made a whole branch look
  blank in the September 5 A/B.
- **Budget is reserved before the call, not counted after it.**
  `BudgetGuard.reserve(...)` short-circuits when no caps are set, otherwise it
  locks the ledger, refuses an oversized estimate, settles the real cost on
  success and refunds on exception. Two defects in that seam were found by the
  wire-up harness on the same day and closed: the flock was carried on a file
  that `os.replace` swaps out from under it (now a sidecar lock), and the cap
  check ignored in-flight reservations, so two parallel calls each under the
  cap could both spend.
- New knobs, all default-off: `run.cost_cap_usd`, `run.turn_cap`,
  `run.wall_clock_cap_seconds`, `run.qualify_preflight`.
- `validation/phase3_wireup_e2e.py` checks all four seams end to end and
  writes `validation/phase3-report.md` — 16/16 at this release.

### Bugs found by measurement on a real greenfield run

- **A third of the reviewer's blocking findings never reached the author**
  (bug 64). The key used to reconcile the prose verdict against the JSON one
  was `(tag, file)` with the line number deliberately dropped — so three
  findings in one file collapsed into one key, the two sets compared equal, and
  the mismatch alarm built exactly for this case went blind with them.
- **A tag pasted after a sentence was not read as a finding** (bug 65). The
  model opened with a lead-in sentence and put `[block] path:line` after the
  full stop; the parser only recognised tags at the start of a line.
- **A story resumed after an interruption re-submitted the rejected candidate**
  (bug 66). The reviewer's blocking words lived in a local variable of the
  retry loop and died with the process, while the evidence survived on disk.
  The rerun opened attempt 1 with empty feedback and burned a paid attempt
  re-submitting what had just been rejected.
- **The reviewer never checked its own prescription against the write scope**
  (bug 67). The `[stuck]` rule only fired when the *author* claimed a deadlock.
  A correct finding whose only fix lay outside the story's write scope cost two
  attempts before the gate could conclude anything.
- **An attempt where the agent wrote nothing still cost a full gate run**
  (bugs 68 and 69). `changed_files` answers "what did this story change",
  measured against `base_ref` — correct for the reviewer's diff, wrong as an
  answer to "did this session write anything". On a retry the previous
  attempt's work made a silent session look like a productive one: candidate
  frozen, nop + test + lint + e2e + a11y + mockup + review + security all run,
  one attempt consumed. The first-attempt variant slipped past both the old
  zero-output check (it *did* call tools) and the first fix.
- **My own no-op guard buried finished work under "already known"** (bug 70).
  The fix above assumed a gate verdict is a pure function of the tree. It is
  not: the gate also reads the spec and the prompt, and both can change between
  attempts. A story whose previous block was caused by an architecture
  decision — since corrected — was told a rerun would produce the same result,
  while its branch already carried the finished feature.

### Windows, and a credential that was retried three times

These landed after the version bump and before the tag, because a release that
is broken on a declared platform is not a release.

- **The phase-2 locks used a POSIX-only flag** (bug 71). `BudgetGuard` and the
  dev-server lease opened their lock files with `os.O_CLOEXEC`, which does not
  exist on Windows — every reservation and every lease raised there, so the
  whole phase-2 seam was dead on half the supported operating systems. Windows
  CI caught it on its first run against this code.
- **The memory store's atomic write was atomic only on POSIX** (bug 72).
  `os.replace` is refused on Windows while any handle to the destination is
  open, so a reader overlapping a writer crashed the write. `_compat` now owns
  both: `open_lock_fd` picks the flag by name, `atomic_replace` retries briefly
  on Windows and nowhere else.
- **A rejected credential is no longer treated as an infrastructure error.** A
  401 carries the same marker as a transient API failure, so the harness
  retried it — 176 seconds per attempt, $0 recorded, three times, on a
  credential that would be rejected identically each time. `auth` is now its
  own exit status, outside the retryable set, and the message names the
  environment variable that decided who the session was (the name, never the
  value) instead of printing `401`.

- **The simulator shelled out to a tool Windows does not have** (bug 73).
  `gold.patch` was applied with GNU `patch`; on Windows there is none, and
  because "no applier" and "did not apply" both returned an empty list, five
  bench tests failed with no diagnostic at all. It now applies through
  `git apply` inside an initialised scratch repository — the mode where a hunk
  that will not place is an error rather than a `Skipped patch` line with exit
  0 — and falls back to `patch` where that is available.

- **Line endings, on both sides of the simulator's write** (bug 74). Applying
  gold and then reverting left the tree dirty on Windows: the write translated
  `\n` to `\r\n`, and the revert wrote the blob's bytes into a working tree
  that had been checked out with `core.autocrlf`. Writes now disable
  translation explicitly, and reverting goes through `git checkout` so git
  applies the same filters it used on the way out.

- **`doctor` says which credential an agent session will use.** Names only,
  never values: an expired key in the operator's shell outranks the client's
  own login, and the only previous symptom was every session returning 401
  after burning its full wall-clock.

### Benchmark v1.3

- Client adapters drain stdout concurrently and keep the partial stream when a
  run times out, so a timeout no longer reads as zero data.
- Twelve harder tasks (`bug-a2-multi-*`, `-state-*`, `-sec-*`): 108 fail-to-pass
  and ~750 pass-to-pass tests, averaging 4.5 source modules per fix against the
  1.4 of the v0.3.0 set.
- `SimulatedWeakAdapter` — a deterministic four-strategy control that costs
  nothing and, crucially, is reported for what it is: it never invokes a hook,
  so AISEF ≡ bare on it is expected and says nothing about guards.
- `tests/bench/tasks/MANIFEST.sha256` pins the fixture bytes; the dataset is
  frozen under the protocol, and the corrected simulator re-run is recorded
  next to the original numbers rather than replacing them.

### Documentation that can no longer drift

- Three counts in the documentation had drifted from their sources:
  `STABILITY.md` said 58 config keys where `DEFAULTS` had 68, both READMEs said
  thirty-one bugs where the taxonomy had reached 70, and the taxonomy's own
  section heading still said "22–63". All three are corrected, and four
  meta-tests now read the source and fail if any of them drifts again.
- Every relative link in `docs/`, both READMEs and this file is checked for a
  target that exists — and, for anchors, a heading that generates it. The test
  was written because `BENCH-REPORT-v1.3.md` was pointing at a bench phase
  queue that had never been written down; that queue now exists in
  `docs/EXECUTION-PLAN.md`.
- The four remaining semantic issues from the pre-Phase-2 audit are written
  down in `ADR-009 § Open`, reconstructed from on-disk evidence with that
  provenance stated, because the original list was never recorded anywhere.

### Tooling

- `ruff` is now a CI gate with an explicit rule set (`F`, `B`, `E9`) chosen by
  measurement, and the deferred families each carry a reason in
  `pyproject.toml`. Enabling it caught a live defect introduced in the same
  session, which is the argument for having it.
- A wheel-smoke CI job installs the built wheel into a clean environment and
  checks the three things unit tests cannot: the command runs, the packaged
  runtime data (prompts, rules, skills, assets, catalog) is really inside the
  wheel, and a blank project can be initialised by the installed command. This
  is the bug-31 class — a wheel whose hooks pointed at a path that did not
  exist, valid syntax, no guard running at all.

### Bugs 54–63 — Windows CI and the greenfield run that preceded it

- **An MCP server's own notes killed a story** (bug 62). Serena writes
  `.serena/memories/*.md` into whatever tree it is pointed at, on its first
  call — which is every session. `diff-scope` saw a file outside `write_scope`
  and blocked every command the agent ran, all three attempts, and seven other
  gate checks went red as a consequence. Same class as `node_modules` and
  `*.tsbuildinfo`: it appears because the story *ran*, not because the story
  *wrote* it. The framework does not choose the user's MCP servers and must not
  fail their stories for having them.

- **The write-scope message cut off before naming the file** (bug 63). It
  printed the twenty-seven-entry scope list first and the offending file last,
  and every consumer folds the message to one line. Offending files come first
  now.

- **The reviewer rejected the fix it had prescribed** (bug 61). Round 2 asked
  for "a defined post-load quiet period"; the author added one; round 3 blocked
  the same line because a defined window is finite, and asked for deterministic
  timer control instead. The story spent all three attempts doing exactly what
  it was told. The rule against moving goalposts only covered promoting
  *should fix* to *block*; it now covers rejecting your own prescription, and
  names `[stuck]` as the outcome when no change the author can make would
  satisfy the criterion.

- **An infra retry in the plan phase left no line in the log** (bug 60).
  `todo-e3`'s ux phase failed twice with `APIError: SSE read timed out`, was
  correctly classified as infrastructure and retried both times — and the log
  showed one motionless `phase=ux START` for thirty-six minutes. The story
  loop has logged this since ADR-005 V11; the plan loop never did. Agent
  `START` lines now also carry the timeout, so silence has a readable bound.

- **On Windows the OpenCode client was launched with its flags inside
  `cmd.exe`'s own arguments** (bug 59). `build_command` inserted `--format
  json` at index 2, which is right when the resolved program is one token and
  wrong when it is three — and it is three on Windows, where `opencode` is a
  `.cmd` shim and resolves to `cmd.exe /c <shim>`. The client ran as `cmd /c
  --format json opencode.cmd run …`. Bug 32's shape a third time: a command is
  not a word. argv is now built in order.

- **The reviewer graded the first story against the whole PRD** (bug 58). A
  story whose single acceptance criterion is "the document has these
  elements" was blocked three times for having no submit handler, not reading
  storage, and not persisting — the work of three later stories. Nothing in
  the review prompt distinguished "not done" from "another story does it", and
  the only way out was for the author to build the next stories' work, which
  then fails *those* stories' nop control. The reviewer now receives the plan,
  one line per story, and is told plainly: a requirement whose story has not
  run is not this story's debt.

- **A failing test run logged 40 lines of HTTP access log.** Playwright's
  `webServer` writes into the same stream as the results; server access lines
  are dropped before the tail is taken (the full text stays in the evidence
  log).

- **A 99-test Playwright run read as zero tests** (bug 57). The fix for bug 43
  matched its own fixture — a single-project config. The moment
  `playwright.config` declares `projects`, which is the default for anything
  testing more than one browser, every line carries a `[chromium] › ` tag and
  the pattern matched nothing; `criteria have tests`, `coverage`,
  `no baseline regression`, `tests verify story` and `preservation` all went
  back to reporting that they could not read test names. The new fixture is
  cut from a real three-browser run, and a test name now keeps its browser tag
  so one browser skipping a case cannot hide another browser passing it.

- **A story that builds the shell was told its list is missing a checkbox**
  (bug 56). Roles that appear only inside the mockup's sample rows were
  compared by "is this role anywhere on the page", so an empty list and an
  unbuilt feature looked identical — and the advice the message gave
  (`app.dev_command` must serve an environment that already holds a record)
  is not achievable for a browser-stored app, or for the first story of a
  project, which builds the shell before anything can create a record. These
  roles are still reported, and now block only when the data region actually
  rendered rows.

- **The first story of every new project failed the gate forever** (bug 55).
  `no baseline regression` and `tests verify story` both reported
  `unrunnable · tool not installed or cannot load (no such file or directory)`
  on a machine that had run the same suite three minutes earlier. The nop
  control runs at the parent SHA, where a greenfield project has no
  `package.json` yet — this story creates it — so npm exits 254 with `ENOENT`,
  whose text matches the missing-tool table. A missing **manifest** is now told
  apart from a missing **tool**: at the parent that means no project, which is
  the strongest form of the answer nop is asking for (PASSED), and there were
  no tests to regress (NOT_APPLICABLE). The same holds one commit later, when
  the manifest exists but `node_modules` does not: dependencies live in the
  worktree the story is about to build, and a project root that never
  installed them has nothing to lend. A real `command not found` still
  blocks.

- **Every command line was split and quoted with POSIX rules** (bug 54). On
  Windows `shlex.split` ate the backslashes out of absolute paths — a project
  command naming `C:\Python\python.exe` lost its program entirely — and
  `shlex.quote` wrapped the framework's own command in single quotes, which
  `cmd.exe` treats as ordinary characters, so every prompt and every guard hook
  named a program that does not exist. Splitting and joining now go through
  `split_command` / `quote_command`, which follow the host's rules.

- Windows CI: the compile report and `Config.source` print POSIX separators
  like every other path the framework shows; `remove_tree` is public, because
  `shutil.rmtree(..., ignore_errors=True)` leaves read-only `.git/objects`
  behind and the next `mkdir` fails.

## 1.2.31 — 2026-09-09

- **"5 files changed since the most recent test run" when nothing had
  changed** (bug 47). todo/STORY-02-01 was refused three attempts running,
  taking `no baseline regression` and `tests verify story` down with it, while
  the log showed `tool=test PASS` after the candidate was frozen.
  `stale_since_last_test` compared `seq`, and a file written by a build from
  before 1.2.26 carries restarted numbering — six `file_change` events with
  seq 161-166 recorded 33 minutes *before* the test run at seq 144. By time,
  nothing had changed at all. Comparison is now by position in the
  time-ordered list, here and in the `diff-scope` guard.

  1.2.26 fixed the ordering `read()` returns; this is the other side of the
  same coin — when a field stops being trustworthy, every reader of it has to
  be found, not just the one that surfaced the problem.

## 1.2.30 — 2026-09-09

- **A TypeScript story failed write-scope on its own compiler output**
  (bug 46). `tsc` rewrites `*.tsbuildinfo` on every build, so the guard
  blocked every bash command with "2 files changed outside write_scope:
  tsconfig.app.tsbuildinfo, tsconfig.node.tsbuildinfo", and the reviewer spent
  2 of its 7 blocking findings telling the author to revert a file the next
  build recreates. Same class as `node_modules` — it appears because the story
  *ran*, not because it *wrote* — but `VENDOR_PATHS` matches directories and
  this is a suffix. Excluded in `changed_files`, which is the one place write
  scope, the diff-scope guard and the reviewer's diff all read.
- The nop control called a command that **could not start** "tests red at
  parent (expected)". A control that never ran now says so.

## 1.2.29 — 2026-09-09

- **Windows could not run any project command** (bug 45). `npm test`,
  `npm run lint` and `npm audit` all came back `[WinError 2] The system cannot
  find the file specified`, exit 127, reported as "tool not installed" — on a
  machine with npm installed and working. Same cause as 1.2.19's client
  launcher, one layer down: `npm` is a `.cmd` shim on Windows, which
  `CreateProcess` cannot execute and `subprocess` will not find because it
  does not search `PATHEXT`. Every host command — project tools and the app
  dev server — now goes through the same resolution.

## 1.2.28 — 2026-09-09

- **"Missing component" now names the component it was renamed to** (bug 44).
  todo/STORY-02-01 spent all three attempts on `mockup map ✗ missing: textbox
  "Description"` while `textbox "Description (optional)"` sat in the evidence's
  `extra` list every single time — the agent had read the story's "optional
  Description" as label text. A renamed label is the most common way a
  component goes missing, and reporting only the absence sends the author
  hunting for a field that is on the screen in front of them. The gate and the
  result summary now pair them and say which one the mockup pins.

## 1.2.27 — 2026-09-09

- **Playwright test names are read now** (bug 43). Its `list` reporter prints
  every test name, but the parser did not know the shape, so `criteria have
  tests`, `coverage`, `no baseline regression` and `tests verify story` all
  scored *unconfigured* on every Playwright project — and told the operator to
  switch to a reporter that prints names, which theirs already did. Playwright
  is the runner this framework drives for mockup and e2e checks, so the gap
  sat in the middle of its own house. The fixture is real `todo` output.

## 1.2.26 — 2026-09-09

- **Every gate could read an older run's result** (bug 42). `_next_seq` read
  the last 4096 bytes to find the highest sequence number — an O(1) shortcut
  with no guard on its ceiling. One event longer than that window (a review
  verdict with findings) leaves the window holding a single truncated line,
  nothing parses, and the function answers `1`: numbering restarts mid-file.
  `read()` sorted by that number, so an old run's events sorted *after* the
  current ones and every "latest result" check read the wrong build. The gate
  reported evidence recorded three candidates back while test, lint, qa,
  mockup, review and security had all just run and recorded against the
  current one. Measured on todo/STORY-01-02: 3 restarts in one file, each
  immediately after a line over 4 KB.

  The window now grows until it parses, and `read()` orders by time then
  sequence, which also heals files already written with restarted numbering.

## 1.2.25 — 2026-09-09

- **The security reviewer kept re-filing a finding against harness code**
  (bug 40). Each attempt hands the reviewer its own previous findings so it
  cannot re-rank yesterday's advice into today's blocker. When one of those
  findings names a file that is no longer in the diff, handing it back invites
  the reviewer to file it again — and it came back a tier higher, `high` then
  `critical`, against `.opencode/plugin/aisef-guard.ts`, which the harness
  writes and the story never touched. Prior findings are now filtered to files
  still in this candidate's diff.
- **A worktree left by a failed run never saw the trunk again** (bug 41).
  Reuse took a shortcut past `refresh()`, so fixes merged to the trunk between
  runs never arrived and the story failed again on something already fixed.
  Reuse now refreshes like a fresh worktree; the merge is a no-op when the
  trunk has not moved.

## 1.2.24 — 2026-09-09

- **"Conflicts in unknown files" where the branches merge cleanly** (bug 39).
  `create()` copied the generated client config — a tracked file — into the
  worktree *before* calling `refresh()`, and `git merge` refuses to run over a
  locally modified tracked file. `aisef run` stopped on todo/STORY-01-02 with
  a conflict report while `git merge-tree` merged the two branches without a
  single conflict. Refresh now happens first and the config is laid down
  after; `refresh()` also discards its own earlier copy before merging.

  Third consequence of one decision in 1.2.19 (overwrite the guard plugin so
  it can never be stale), after bug 37. The overwrite is still right — it is
  what stops a run going unguarded — but it has to happen where git is done
  looking.

## 1.2.23 — 2026-09-09

Both fixes are the same mistake in two places: a gate that judges *state*
where it means to judge *change*.

- **The reviewer saw the harness's own file and blocked the story** (bug 37).
  Since 1.2.19 the harness refreshes the guard plugin inside the worktree on
  every run, which leaves that tracked file modified. The structural checks
  filter `HARNESS_OWNED` correctly, but `review_diff` ran an unlimited
  `git diff`, so the reviewer blocked "modifies a file outside the effective
  write scope" and the security reviewer filed a high finding against
  generated harness code. todo/STORY-01-02 went stuck on it. The diff is now
  limited to the story's own changed paths.
- **A file the operator left uncommitted blocked every planning tool call**
  (bug 38). `.ai/config.json`, written by `aisef setup`, made `diff-scope`
  report "changed outside write_scope" 14 times in one Windows run and left
  the ux phase blocked. Planning and mockup phases now declare
  `AISEF_BASELINE_DIRTY` — what was already dirty when the phase opened — and
  the guard subtracts it. What the session really writes outside scope is
  still blocked.

## 1.2.22 — 2026-09-09

- **Planning phases inferred the guard's scope from what was absent**
  (bug 36). `plan` and `mockup` passed no environment to the client, so the
  guard fell back to the planning scope only as long as the host had no
  `AISEF_*` left over: a stale `AISEF_STORY_ID` in the shell flips it into
  story mode with an empty scope and denies every planning write. Both
  phases now declare `AISEF_WRITE_SCOPE`, `AISEF_STORY_ID`, `AISEF_PROJECT`
  and `AISEF_WORKDIR` outright.
- **A guard that blocked outside a story left no trace.** Nothing is recorded
  without a story id, so a blocked planning phase kept its reason inside the
  client's own session log. Blocks now reach `run.log` as
  `guard <kind> BLOCK <tool> · <reason>`.

## 1.2.21 — 2026-09-09

- **A sentence in the route field failed a story three times** (bug 35). The
  UX table's column is "Route/state", so the agent wrote prose in it, the
  mockup copied the sentence into `aisef-route`, the harness turned it into a
  URL, and the dev server answered with its 404 page. The mockup-map step
  then compared that error page against the contract and reported every
  component missing — with `preservation` calling it a regression. The only
  trace was `extra: heading "Error response"`.
  - the mockup gate now rejects a route that is not openable, before a story
    spends anything;
  - `render.mjs` treats HTTP >= 400 as *not compared*, not as an app missing
    its interface;
  - the mockup prompt asks for a real path when the document holds prose.
- A data region that renders nothing now says the list was empty at that URL
  and points at `app.dev_command`, instead of only naming the missing role.

## 1.2.20 — 2026-09-09

- **Windows: the guard rejected paths that were inside scope** (bug 34).
  `Path.relative_to` returns the native form, and every comparison after it
  is written in `/` — so `_bmad-output\project-context.md` was one segment
  matching nothing, and the plan phase stopped on a file plainly inside
  `_bmad-output`. `to_posix()` normalises where OS-produced paths meet
  story-declared ones, on Windows only: a backslash is a legal character in
  a POSIX filename, and reading it as a directory boundary would let
  `docs\evil.sh` at the root pass as being inside `docs/`.
  Same fix reaches `check_process_refs` and the test-path pattern.

## 1.2.19 — 2026-09-09

Three real failures found by running the framework, two of them silent.

- **OpenCode ran with every guard disabled** (bug 32). `aisef_command()`
  falls back to `<python> -m aisef.cli` when `aisef` is not on PATH, and that
  three-word command was carried as one string into both clients — read back
  as one filename containing spaces. A guard call that cannot start is not a
  block, so a whole run finishes unguarded with evidence identical to a
  well-behaved agent. Measured on `todo`: 46 sessions, 0 guard events.
  `aisef_argv()` now returns argv, the plugin emits an array, and a guard
  that cannot run refuses the action instead of allowing it.
- **Windows could not start either client** (bug 33). `WinError 2` on the
  `.cmd` shim npm/bun installs, then `WinError 206` because the prompt rode
  on a command line Windows caps at 32767 characters. Binaries are resolved
  before exec, the prompt goes to stdin, and `ENV_KEEP` no longer hands a
  Windows child a POSIX-only environment.
- **A worktree kept a stale guard.** Projects that commit
  `.opencode/plugin/aisef-guard.ts` checked out the committed blob, so a
  plugin `aisef compile` had just fixed never reached a story. Generated
  client config is now overwritten on every worktree create.
- `run.log` states the reason for each failed check instead of only naming
  it; mockup verification that could not run scores *unconfigured*, not a
  green pass.

## 1.0.0 — 2026-09-08

First stable release. The harness is feature-complete for single-machine,
multi-client story execution with evidence-bound gates.

### Highlights

- **Conformance parity**: Claude and OpenCode both pass 10/10 probes (C1–C10).
- **Crash recovery**: `reconcile_all()` at every `aisef run` start; 3 recovery
  scenarios (roll-forward, undo, stale).
- **Egress guard V12**: `check_egress()` with host extraction, wildcard matching,
  `sandbox.allow_hosts` config.
- **Credential isolation**: Docker S1–S5 all pass; local provider honestly
  documented as unsupported.
- **Zero mandatory config**: all 58 keys have sensible defaults; projects work
  with no `.ai/config.json`.
- **ADR-006**: reconciles 6 exit conditions — 3 met, 3 deferred to post-1.0
  with evidence and rationale.
- **Dogfood evidence**: par (Node.js) + calc (Python) + bench (15+ bug-fix
  tasks, 96 runs) demonstrate framework robustness across project types.
- **1913 tests passing**, zero external dependencies, Python >= 3.11.

### Known limitations

- Distributed execution (multi-machine) is deferred to post-1.0.
- External user validation is pending (post-1.0 adoption milestone).
- Local sandbox provider does not isolate credentials (use Docker).
- OpenCode + Serena writes `.serena/` files outside declared write_scope;
  the harness correctly rejects these — a known agent-side limitation.

## 0.8.0

- Brownfield support: `CodebaseGraphProvider`, delta planning, blast radius.
- Handoff and `skill_use` frozen as evidence kinds.

## 0.7.0

- OKL (Operational Knowledge Layer): ADR-002, skill registry + router.
- Evidence-driven epic improvement (ADR-004).

## 0.6.0

- Harness absorption pattern (ADR-005).
- Bench protocol v0.3.0 with 27-task challenge set.

## 0.5.0 / 0.5.1

- Handoff contract and skill graph (ADR-003).
- Sandbox conformance probes S1–S5.

## 0.4.0 / 0.4.1

- TDD gate (G8): red-before-green, test delta detection.
- Story gate checks expanded to 16 with 3 controls each.

## 0.3.0 / 0.3.1

- Conformance probes C1–C10.
- Multi-client runner infrastructure.

## 0.2.0

- PyPI package `aisef`, CLI entry point `aisef`.
- Zero external dependencies.

## 0.1.0

- Initial release: 8 human gates, story execution, evidence store,
  worktree isolation, journal, state machine.
