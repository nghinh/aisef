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
