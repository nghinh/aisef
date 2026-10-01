# P6 — the single authoritative orchestration path (WP-6.2)

**Status.** Implemented under "AISEF V2 — WP-6.2 EXECUTION AUTHORIZATION / SINGLE AUTHORITATIVE ORCHESTRATION
PATH" and ARCHITECTURE-EXCEPTION-V2-005 (journal format 3, the nine typed codes, `budget_owner`). Evidence:
`closure-evidence/v2/P6-ORCHESTRATION.json` (builder `validation/v2/p6_evidence.py`, `--check` twin). Tests:
`tests/v2/test_p6_orchestration.py` (the real path, ORCH-1..16 and ORCH-SCHEMA-1..10) and `tests/v2/test_p6_stages.py`
(each stage on its own; the mutation kill tests). The package is `aisef2/orchestrate/`; WP-6.3 removes the seam.

## 1. The path

One entry, `story_runner.run_story(run, plan, story_id, inputs, adapters, policy)`. Per attempt, in this order, each
stage writing typed events to the run's format-3 journal and one `gate/check` row under the story gate:

| stage | row | journal | typed failure |
|---|---|---|---|
| seam (before the story begins) | — | nothing | `SeamRefusal` (an exception, no event) |
| resources: scratch, implementer checkout, verifier checkout | `resources` | `story/resource-acquired` (SCRATCH 4, WORKTREE 3 — non-increasing rank) | RESOURCE_ACQUISITION_FAILED |
| StoryAdmission at the frozen parent (P2, real probe) | `admission` | `probe/evaluated`, `story/admitted` | the blocking obligation's own decision |
| developer (only for READY criteria) | `developer` | `provider/request` budget_owner DEVELOPER, `provider/result` | PROVIDER_UNAVAILABLE |
| candidate proof, two parties | `proof:<criterion>` | two `probe/evaluated`, `proof/verified` citing both | PROBE_MISMATCH, VERIFIER_DISAGREEMENT, or the routed product failure |
| engineering quality at the verifier's checkout (WP-5) | `quality` | `tests/adequacy` | TESTS_UNRUNNABLE; TESTS_INADEQUATE under the project's stance |
| reviewer, confined | `review:<finding>` / `review` | `provider/request` budget_owner REVIEW, `provider/result` | REVIEW_FINDING, PROVIDER_UNAVAILABLE, CAPABILITY_UNRUNNABLE |
| scanner, confined, as a P4 tool call | `security:<finding>` / `security` | `tool/invoked`, `tool/result` | SECURITY_FINDING, CAPABILITY_UNRUNNABLE |
| merge | `merge` | — | MERGE_CONFLICT (INTEGRATION), UNKNOWN for a broken merger |
| post-merge re-proof: the story's obligations, then every committed story's PRESERVE obligation | `post-merge:<criterion>` | two `probe/evaluated`, `proof/verified` per criterion | POST_MERGE_REGRESSION and the merge reverted |
| decision | — | `gate/decision` citing every row of the attempt | — |
| outcome | — | `story/commit`, or `failure/observed` then `story/retry` (budget.charge) or `story/rollback` | — |
| disposal | — | `story/dispose`, releases in reverse order, `story/end` | — |

A retry is decided by `budget.charge` over the journal (retry_target and budgets projections); the runner keeps no
counter. A failed attempt is never re-run to green: the next attempt begins at the branch tip again, with its own
admission and its own developer call.

## 2. Decisions the owner should see

* **Confinement is derived.** `adapters.confine(story_id, checkout)` removes the write bits of the verifier's own
  checkout and returns a `ReadOnlyScope`; the reviewer and the scanner receive that scope and nothing else. No
  function of the package takes a readonly / sandbox / allow_write / confinement parameter (measured in the record).
* **Verifier independence.** The verifier probes in a second worktree the implementer never touches, moved to the
  same candidate; the instrument identity (probe id, digest, enforcement, semantic hash) must be identical or the
  two records are PROBE_MISMATCH, never a proof. Disagreement is VERIFIER_DISAGREEMENT, INTEGRATION, never arbitrated.
* **Immutable references.** A developer's candidate, a merge, a revert take full SHAs only; a branch name is refused
  by API shape (`Implemented`, `GitMerger.merge`, `GitMerger.revert`).
* **Post-merge re-proof before commit.** `story/commit` is written only after the merged revision has been
  re-proved; a regression reverts the branch to the merge's first parent (`update-ref` with the old value checked).
* **No deletion by name.** Nothing in the package calls `rmtree`/`unlink`: git removes the worktree it registered,
  the scratch directory is its `TemporaryDirectory` handle's own cleanup; a directory that survives is a `Residual`
  (INV-MUTATION-AUTHORITY; the destructive-site ledger has no row under `aisef2/orchestrate/`).
* **The project's stance on INADEQUATE** lives in `Policy.tests` (`TestsPolicy.blocking`) and reads the assembly's
  `may_block` only; no adequacy outcome is named or decided outside `aisef2/quality` (P5's separation test holds).
* **Resource names within an attempt.** The journal admits a resource name once per attempt, so every process range
  is acquired under its own name plus the stage and party that started it (`Ranged`, `_Held`).
* **Scenario L.** The same spec at the same revision gives the identical `proof/verified` payload for INTRODUCE,
  PRESERVE and VERIFY (ORCH-11 runs three stories through the real path and compares).

## 3. The compatibility seam

`aisef2/orchestrate/seam.py` — `admit_legacy(modes, table, declarations)`, called by `run_story` before anything is
journaled. A V1 proof mode is resolved against the generated migration table (WP-6.1); a row left
HUMAN_DECLARATION_REQUIRED is refused unless a typed `SubjectAbsence` declaration is given. It executes no V1
authority, calls no V1 judge, infers nothing, and selects no V1 evidence. Nothing else in `aisef2` reads the table or a
V1 name; WP-6.3 removes the module.

## 4. Adapters

`Developer.implement(story_id, criteria, checkout) -> Implemented`, `Reviewer.review(scope, criteria) -> Reviewed`,
`Scanner.argv(scope, report) / read(report, exit_code) -> Scanned`, `Merger.base / merge / revert`,
`Workspace.scratch / checkout / move / diff`. Real implementations: `GitWorkspace`, `GitMerger` (typed from git's exit
status and unmerged-path list, never from text). The developer, reviewer and scanner are capabilities the run
supplies; a model-backed developer adapter is not part of WP-6.2.
