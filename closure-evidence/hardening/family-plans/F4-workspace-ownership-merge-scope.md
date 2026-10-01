# Fix family F4 — WORKSPACE OWNERSHIP / MERGE / SCOPE

Closes (frozen defect set): SS-17, SS-35, SS-36, SS-37, SS-38, SS-39, SS-40, SS-41, SS-42, SS-43, SS-53, D-011.
Invariants: INV-A.1, INV-A.3, INV-I.1, INV-I.2, INV-I.3, INV-J.1, INV-K.1, INV-O.1, INV-P.1.

Owner rules (Phase 10): ownership classes DEVELOPER / HARNESS / VERIFIER / CLIENT_GENERATED / PREEXISTING /
EXTERNAL_UNATTRIBUTED; *porcelain alone never determines blame*; *unattributed data is never deleted automatically*.

## 1. One ownership classifier (INV-I.1, INV-I.2)

`aisef/harness/ownership.py::classify(rel, *, session=None) -> Ownership` — the single answer to "whose path is
this", read by every consumer below instead of each keeping its own skip list:

| class | rule | consumers' treatment |
|---|---|---|
| HARNESS | `_bmad-output/{evidence,journal,approvals,sprint-status.json,…}`, `.aisef/` (`HARNESS_OWNED`) | invisible everywhere |
| VERIFIER | tool artifacts (`is_tool_artifact`: `.coverage`, reports, caches) and VENDOR segments (`node_modules`, `.venv`, `dist`, … — by path SEGMENT at any depth, one list) | never a write, never a violation, never deleted, never blocks a merge |
| CLIENT_GENERATED | `.claude/settings.json`, `.claude/settings.local.json`, `.opencode/`, client state files | as VERIFIER |
| DEVELOPER | a path the graded session wrote (`file_change` evidence of THIS story's sessions, or inside the write scope and changed since the session opened) | the candidate; scope-checked; restored/removed by recovery when out of scope |
| PREEXISTING | dirty or untracked before the session opened (the baseline snapshot the session declares — `ENV_BASELINE_DIRTY`), or present under a granted directory before the first session of the story | never staged into a candidate (SS-41), never a violation (SS-37), never deleted |
| EXTERNAL_UNATTRIBUTED | dirty, in no class above, no session of this story on record for it | stated by name; the run stops before opening a paid session (D-034 kept); never deleted |

`git status --porcelain -z` is parsed by one function that understands renames (`R`/`C` entries carry two NUL
fields — SS-35) and yields real paths only.

## 2. Consumers

- `changed_files` (guard + gate + reviewer diff): HARNESS / VERIFIER / CLIENT_GENERATED excluded by the classifier
  (SS-38 joins SS-36's `.coverage`); renames yield the new path (SS-35).
- `_tree_snapshot` → `_revert_reviewer_writes`: a reviewer that only produced VERIFIER / CLIENT_GENERATED paths did
  not modify the tree; `review:immutable` names DEVELOPER-class diffs only (SS-36).
- `_dirt_outside_scope` / `recover_out_of_scope`: VERIFIER and CLIENT_GENERATED paths are not dirt; nested vendor
  trees are neither a violation nor deleted (SS-39); PREEXISTING and EXTERNAL_UNATTRIBUTED paths are named, never
  removed (owner rule; D-034 stays).
- `commit_paths` (candidate freeze): stages DEVELOPER paths — inside the granted scope AND attributable to a session
  of this story (a `file_change` record, or changed against the session-open baseline); an operator fixture that
  pre-existed under `tests/` is not the developer's work (SS-41); the freeze records what it left out.
- `merge_story` dirt check: only DEVELOPER / EXTERNAL_UNATTRIBUTED dirt refuses the merge of a frozen candidate;
  VERIFIER / CLIENT_GENERATED / HARNESS paths never do (SS-17). The refusal names the class and the paths.
- Story sessions declare their baseline dirt to the guard exactly as planning and mockup do (`ENV_BASELINE_DIRTY`),
  so under `--no-isolate` an operator's uncommitted file is PREEXISTING, not the developer's first violation (SS-37).
- `aisef verify` without `--write-scope`: UNCONFIGURED, exit non-zero, and the generated CI step passes the scope
  it can compute (the story's declared + granted scope) or fails closed (SS-40).
- devsecops session env carries a write scope (`Dockerfile`, the CI path, the runbook, deploy files) and the guard
  reads it (SS-42).
- pre-deploy grades ONE tree: Dockerfile / CI workflow / runbook are checked in the same clean worktree of HEAD the
  suite ran in; the signed report binds committed content only (SS-43, INV-P.1/A.3).
- Scheduler: waves partition on declared scope + FILE grants (manifests, lockfiles) — two stories that may both write
  `pyproject.toml` do not share a wave; DIRECTORY grants (`tests/`) do not conflict by themselves — stories create
  distinct files there and the merge is exact (SS-53, INV-O.1). The split is logged with the shared file named.
- D-011 (bench artifacts at the framework root): the bench runner passes an explicit `--project` for every call and
  refuses a default `.`; `ro_ri_ngoai_workspace` stays as the detector. The register row's "not reproducible" note
  stands — the deterministic guard is what F4 ships, and the row is dispositioned FIXED-BY-CONSTRUCTION with the
  detector as the proof, not a claimed reproduction.

## 3. Definition of done

RED → GREEN: `test_sibling_scan.py::TestSS17/35/36/39`, `scan8a/test_group_c.py::TestSS37/38/40/41/42/43/53`; new
`tests/hardening/test_ownership.py` (one classifier: every class has a positive and a negative; porcelain rename;
unattributed never deleted; PREEXISTING never staged); fault cells FM-M-02, FM-W-03, FM-W-04 GREEN; INV-I.1, I.2,
I.3, J.1, K.1, O.1 PROVEN (A.1/A.3/P.1 lose their F4 reds); model: the ownership classes appear as scripted
workspace events (VERIFIER artifact, nested vendor, pre-existing dirt) and the differential agrees; full suite, ruff,
Linux + Windows CI.

## 4. Closure record (2026-09-16, branch hardening/systematic-v1) — implementation

- **One classifier** — `aisef/harness/ownership.py`: `Ownership` (HARNESS, VERIFIER, CLIENT_GENERATED, DEVELOPER,
  PREEXISTING, EXTERNAL_UNATTRIBUTED), `classify(rel, baseline=, session_writes=, scope=)`, `porcelain_entries`
  (a rename's original path is consumed, never a phantom — SS-35), `NOT_A_WRITE`. Consumers: `changed_files`
  (SS-35, SS-38 with SS-36's `.coverage`), `_tree_snapshot` → `_revert_reviewer_writes` and `_dirt_outside_scope`
  (SS-36, SS-39: a nested vendor tree is neither a mutation nor a violation nor deleted; D-034's rule that
  unattributed dirt is named and never removed stands), `merge_story` (SS-17: only an uncommitted WRITE refuses the
  merge, named), `commit_paths(exclude=)` + `freeze_candidate(preexisting=)` (SS-41: a path present and byte-identical
  before and after the session is PREEXISTING, unstaged, recorded in the journal as `preexisting_excluded`).
- **Scope declared where it was missing** — the developer session declares `AISEF_BASELINE_DIRTY` like planning and
  mockup (SS-37); the devsecops session carries `DEVSECOPS_SCOPE` in its env and the guard reads it (SS-42); a bare
  `aisef verify` is UNCONFIGURED and exits non-zero, and the generated CI step passes `--write-scope
  "$AISEF_WRITE_SCOPE"` from a repository variable, empty failing closed (SS-40).
- **One tree** — pre-deploy grades the Dockerfile, CI workflow and runbook at HEAD whenever the suite ran on the clean
  worktree of HEAD (`_tree_file`, `check_runbook(text=, present=)`); an uncommitted file never passes bound to a commit
  (SS-43).
- **Scheduler** — waves partition on declared scope + FILE grants (manifests, lockfiles); directory grants do not
  conflict by themselves (SS-53).
- **D-011** — an IMPLICIT project must be an AISEF project: `parser.main` records `project_defaulted`;
  `_artifact_root` raises `ConfigError` and writes nothing when the directory carries no marker (`.ai/config.json`,
  `docs/requirements.md`, `.aisef/`, `_bmad-output/`) — the framework root carries none, so the recorded leaking call
  would have been refused. FIXED BY CONSTRUCTION; the register's "not reproducible" note stands and the detector stays.

Members RED → GREEN (markers removed in this commit): SS-17, SS-35, SS-36, SS-37, SS-38, SS-39, SS-40, SS-41, SS-42,
SS-43, SS-53. New tests: `tests/hardening/test_ownership.py` (classifier positives and negatives, rename, tool/client/
harness paths, implicit-project refusal, explicit project honoured). Existing tests adapted (each names why): the SS-40
reproducer's precondition now asserts the CI step carries its scope source.

**Decision recorded — INV-O.1 read literally.** The registry says "stories that run in parallel have non-overlapping
EFFECTIVE write scopes"; `effective_write_scope` grants existing manifests to every story, so two stories both granted
`pyproject.toml` do not share a wave (SS-53) even after the bootstrap phase that D-031 (1.7.3) had exempted. The cost is
parallel width — a Python project whose stories all receive the manifest grant runs them one at a time — and it is now a
stated property of the scale contract (`docs/SCALE-QUALIFICATION.md`), not a hidden collision handled at merge. The two
tests that encoded the exemption were adapted, each naming why: the D-031 reunite test expects singleton waves; the G12
merge-to-done test injects its collision where it really arises (a trunk commit touching the manifest between the
story's freeze and its merge) instead of relying on two stories sharing a wave.

Other tests adapted to the F4 contracts (each names why): `aisef verify` on a clean tree without a scope is UNCONFIGURED
and non-zero, with `--write-scope` it passes; the parser leaves an absent `--project` as `None` so `main` can flag an
implicit project; the trunk-move detection reads the raw commit diff (harness paths included) so a harness-only trunk
change is still told apart from an agent escaping its worktree; the classifier does not treat the whole of
`_bmad-output` as harness — an agent editing the PRD while writing code stays visible.

**Final state at closure (this commit)**: differential 400 traces (seeds 0–399) and 2 000 traces (seeds 1000–2999) on the
extended vocabulary, all matched, 0 unexplained, `KNOWN = {}` (`differential-f4-400.json`, `differential-f4-2000.json`);
full suite 3 345 passed / 20 skipped / 19 expected-red, every expected-red tagged with a defect id of F5 or F6; ruff clean.
Frozen defect set {'OPEN': 16, 'FIXED': 56, 'SUPERSEDED': 1} of 73 (D-011 FIXED BY CONSTRUCTION with its disposition
recorded). Fault matrix {'GREEN': 63, 'RED': 6, 'NEEDS_TEST': 0}. Registry {'PROVEN': 39, 'PARTIAL': 10, 'MISSING': 1}. Linux and Windows CI on this commit are read from the PR checks.

CI on 397d52a (run 35110871918): 7/7 green — Linux 3.11–3.14, Windows 3.11, lint, wheel (2026-09-16).
