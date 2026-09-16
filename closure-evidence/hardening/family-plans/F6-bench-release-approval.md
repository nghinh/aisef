# Fix family F6 — BENCH / RELEASE / APPROVAL

Closes (frozen defect set, the last 6 OPEN): SS-06, SS-07, SS-54, SS-55, SS-56, D-003. Fault cells FM-A-03,
FM-C-12. Invariants: INV-R.2, INV-F.3 (its last citation, SS-07), INV-P.1. (D-002 was SUPERSEDED in F3.)

Owner rules (Phase 10): *a closure probe reads identities, never existence*; *an approval binds to the digest of
everything it covers, and staleness cascades*; *a bench number belongs to exactly one cohort*.

## 1. Closure probes read identities (INV-R.2, INV-F.3)

- **SS-06** G4.5 `probe_evidence_at_candidate`: "in the corpus history" means ANCESTRY — `git merge-base
  --is-ancestor <candidate> HEAD` on the corpus checkout — never `rev-parse --verify` (object existence: a candidate
  frozen on a story branch nobody merged lives in the same object store). Story branches are merged with `git merge
  --no-edit` (never squashed), so a merged candidate is always an ancestor of the trunk head. The detail names the
  case: `candidate X is not an ancestor of HEAD — verified on a build nobody merged`.
- **SS-07** G4.4 `probe_review_and_security`: a stage counts only when a VERDICT is recorded. One predicate,
  `control/gate.py::verdict_recorded(event)` — no `unrunnable`, no UNRUNNABLE `outcome` (REVIEW_UNRUNNABLE /
  SECURITY_UNRUNNABLE / `StageOutcome.UNRUNNABLE`), no legacy "could not run" finding text — is the single
  definition; `implement._review_complete` delegates to it, and G4.4 uses it for `review` AND `security`. The gap
  detail says which: `S-1:review (recorded, but no verdict: exceeded 1800s)`.

## 2. Approvals bind to what they cover (INV-P.1)

- **SS-55** the readiness digest covers the verifier configuration: `content_hash(Gate.READINESS)` adds a virtual
  part `verifier-config:<identity.verifier_config_digest(Config.load(project, env={}))>` (the same digest F1 stamps
  on every verdict; `tools.*`, `verify.*`, `coverage.*`, `security.*`, `review.*`; the project is the artifact
  root's parent). Weakening `coverage.min` or narrowing `security.block_severities` after the approval makes
  readiness STALE. The file-based config is what a person approved; an environment override is the operator's
  session and is already part of every verdict's identity.
- **SS-56** staleness cascades on CONTENT, not only on a later decision: `status(gate)` is STALE when any upstream
  gate's status is STALE (the upstream artifact was edited after its approval), in addition to the existing
  `_upstream_decided_after`. Programmatic callers and CLI entry points then agree (`blocking()` is unchanged).
- **SS-54** every repair story is inside SOME approval's digest: `content_hash(Gate.IMPROVE)` covers the repair
  slice of the stories index (stories / epics whose id carries `REPAIR_PREFIX`, and repair waves) — exactly the
  complement `_artifact_hash` removes from `stories` / `readiness` — beside `LOOP-REPORT-*.md`. Under `--auto` the
  owner's flag waives the gate for the next round; that waiver is written to the run log with the round number and
  the gate's status at that moment, so a repair story never executes without a digest that saw it.

## 3. Bench integrity (D-003)

- `tests/bench/_analyze.cut_sessions` / `session_rows` merged `.bench` and `.bench-c1b` sessions on the
  `(condition, task, attempt)` key when called without `bench_dir` (the report's own call site). A bench number
  belongs to exactly one cohort: `session_rows` defaults `bench_dir` to the cohort directory the report collects
  from (`_mine`'s resolver: `AISEF_BENCH_DIR`, default `.bench`), so a session from another cohort never lands on
  this cohort's key; the row carries `bench_dir`. No reproducer existed: `tests/bench/test_bench.py` gains one
  (two cohorts, one shared task: the count is 1, not 2), confirmed RED before the fix.

## 4. Definition of done

RED → GREEN: `scan8a/test_group_a.py::TestSS06/07`, `scan8a/test_group_d.py::TestSS54/55/56`, the new D-003 test;
`test_compound_faults.py::TestCF12` (approval invalidated while stopped, then resume) and `test_fault_matrix` FM-A-03;
existing closure/approval tests adapted where they encoded the old reading (each names why); fault cells FM-A-03,
FM-C-12 GREEN; INV-R.2, INV-F.3, INV-P.1 PROVEN; the model's approval states are untouched (no kernel path the
differential exercises changes — the closure probes and approvals are outside the story loop), so the differential
is re-run once (400) as a regression control only; full suite, ruff, Linux + Windows CI. After F6 the frozen defect
set has 0 OPEN members and no `expectedFailure` marker names a frozen-set id.

## 5. Closure record (2026-09-17, branch hardening/systematic-v1)

Implemented as designed:

- **Closure probes.** G4.5 asks ancestry (`_is_ancestor`: `git merge-base --is-ancestor <candidate> HEAD`), never
  object existence; the detail names the case. G4.4 counts a stage only when a verdict is recorded:
  `control/gate.py::verdict_recorded` is the one definition (no `unrunnable`, no `…UNRUNNABLE` outcome, no legacy
  "could not run" finding), `implement._review_complete` delegates to it, and the gap detail says "recorded, no
  verdict: <why>" when a record exists without a verdict.
- **Approvals.** `content_hash(READINESS)` adds the verifier-config digest F1 stamps on every verdict (file-based
  config of the artifact root's parent, `env={}`); `content_hash(IMPROVE)` adds the repair slice of the stories index
  (exactly what `_artifact_hash` removes for `stories`/`readiness`); `status()` is STALE when any upstream gate's
  status is STALE (content cascade beside the decision cascade); under `--auto` the improve loop writes the waiver
  to the run log with the round number and the gate's status.
- **Bench.** `session_rows` defaults `bench_dir` to the cohort the report collects from (`R.KEEP_DIR`); a cohort in
  another directory is measurable when named and never merged when not. The reproducer was written first and was RED
  (the `.bench-c1b` session counted, and cut, in the `.bench` row); the older "count a cohort in another directory"
  test now asserts both halves of the rule and names D-003.

Members RED → GREEN (markers removed in this commit): SS-06, SS-07, SS-54, SS-55, SS-56; compound CF-12; D-003
FIXED with disposition and a new reproducer. Existing closure and approval suites passed unchanged (274 tests); the
improve suite passed unchanged (43). No kernel path the differential exercises changed (closure probes and approvals
are outside the story loop); the 400-trace differential is re-run as a regression control only.

Final numbers (2026-09-17): regression-control differential `differential-f6-400.json` 400/400 matched, 0
unexplained. Full suite 3372 passed / 20 skipped / 2 expected-red (both INV-S.1, Phase 17) / 0 failed (1444
subtests, 568 s); ruff clean. The Windows-only walker fix (`_snapshot_win32`, see the F5 record) landed after that
suite run started; it is compile-checked and its POSIX-reachable callers passed, and this commit's Windows CI job is
its test. Fault matrix 67 GREEN / 2 RED / 0 NEEDS_TEST (the 2 RED are FM-X-01 and FM-C-09, INV-S.1 replay, Phase 17).
Registry 45 PROVEN / 4 PARTIAL / 1 MISSING (INV-R.2, INV-F.3, INV-P.1 promoted; INV-E.2, H.1, N.2, Q.2 remain PARTIAL
for Phase 11; INV-S.1 MISSING for Phase 17). Defect set 72 FIXED / 1 SUPERSEDED / 0 OPEN. No `expectedFailure` marker
names a frozen-set id. Linux + Windows CI: recorded here when the run completes.
