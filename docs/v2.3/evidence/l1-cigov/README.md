# L1-CIGOV — release-path governance (W1, lane L1-CIGOV)

Design: `docs/v2.3/W1-DESIGN.md` §5, §6, §7, §8 (placement corrected by Amendment A2: tests in `tests/v23/`, evidence here).
Base: `v23/lanes` at `36fdda8d` (L1-BUILD, L1-F2, L1-TESTENV committed). Host of the local measurements: Darwin 25.5.0
arm64, CPython 3.14.7 (unit tests) and 3.12.14 (the two smoke venvs), git 2.53.0. Kill-test and engine runs used the
mutation-worker env guard (no `opencode` on `PATH`, XDG data/state/cache in scratch). No network, no paid call. Raw
traces stay in scratch and are named here by sha256.

**Nothing below was measured on GitHub CI.** Every workflow change runs only once the branch is on GitHub (DISC-1).

## Items

| Item | Change | Tests | Red-before (measured) | After |
|---|---|---|---|---|
| REL-GOV-01 / #1 | `validation/qualification/release_governance.py` (`problems(env, policies)`, GET-only CLI); `release.yml` job `governance` (`contents: read`, `actions: read`); `v2-gate` needs it, `publish` needs `v2-gate` | `tests/v23/test_v23_release_governance.py` `Predicate`, `Cli`, `PublishNeedsGovernance` (17 neutralisations, the probe workflow, the 2.2.0 release.yml; CIGOV-R2: every publish job deploys to exactly `pypi`, the environment the guard reads, in scalar or `name:` form) | 14 failures + 2 errors in that file before the workflow edits (trace `c8c25cd3…`); `release.yml` at `v2.2.0` has no checkpoint; CIGOV-R2: the 4 environment edits (removed, renamed, expression, mapping to another name) were not found, 4 failures (trace `d74c8d3c…`) | 29/29 pass |
| #6 (non-A2) | `tests/installed_product_smoke.py`: asserts `aisef demo`'s three rows; `--writer` has another installed `aisef` write the run, the candidate verify it, and requires RUN.json `kernel_digest` = `c2d356b1…`; `staging.yml` install job runs both (2.2.0 wheel by `pip --require-hashes` on its frozen sha256) | `DemoRows`, `SmokeWiring`, `StagingRunsBoth` | the base smoke has no demo check and no writer mode (`de8318dd…`); the staging pin failed | local installed run: plain PASS (18 s, `5bd0e26b…`), `--writer` PASS (5 s, `65a01ea4…`) |
| #29 | `conformance.yml` dispatch-only | `NoScheduledPaidSecret` | `conformance.yml` scheduled with `secrets.ANTHROPIC_API_KEY` (test on `v2.2.0`'s file, and on the base) | pass; `pins.yml` (schedule + `GITHUB_TOKEN` only) passes |
| #30 | none (ACCEPTED_LIMITATION, recorded in `docs/v2.3/BASELINE.md`) | `DiagnosticIsNotAGate` | — | pass |
| #52 (a) | `tests.yml` unit job (all 6 legs): a step fails when `git status --porcelain=v1 --untracked-files=all -- closure-evidence/` is non-empty | `EvidenceUntouchedBySuite` (static order/skip pins; the step's own bash run in a throwaway repo: added, rewritten, deleted → exit 1; clean, git-ignored → 0) | the V1 guard ignores `closure-evidence/v2/` (`tests/v2/test_v1_evidence_guard.py::test_changes_under_v2_are_ignored`); the step was absent | pass |
| #52 (b), CT-6 | `validation/v23/released_evidence_guard.py`; baseline `docs/v2.3/evidence/released-evidence/V2.2.0-RELEASED-EVIDENCE-BASELINE.json` (6,339 files at `da3ea33f`, digest `08bed2ae…`, recomputed independently with `git ls-tree`); `tests.yml` step after the suite | `tests/v23/test_v23_released_evidence_guard.py` (11), `HistoryKept` | throwaway repo: committed edit, deletion and baseline edit each PASS the V1 guard (`d56f71fd…`) | each FAILs the new guard; an addition passes; live HEAD PASS (0.26 s). **CONFLICTS WITH CT-5, not DONE** (CIGOV-R1, OPEN): the ledger is a protected blob, so the planned seq 13 / v2.3.0 appends FAIL; decision in `docs/v2.3/amendments/CIGOV-R1.md` |
| CT-5 | — | `LedgerAppendOnly` | — | entries 1–12 equal `v2.2.0`'s; seq 1..12 strictly increasing. Conflicts with CT-6 on the ledger (CIGOV-R1) |
| CI-INCR | NEW `.github/workflows/mutation-incr.yml`: `gate` (release/** push, PR) = `impact.py --classify`; `plan` (dispatch) = `--classify --affected`; F5 engine only | `IncrementalQualificationJob` | no workflow existed | pass |
| BUILD-REPRO CI | `staging.yml`: toolchain record + `dist/*.whl` normalisation in `build`; NEW job `repro` (3.11–3.14: fresh, perturbed copy, tag `v2.2.0`) | `tests/v23/test_v23_repro_contract.py` (L1-BUILD's pins, 16) | 4 `ContractPinnedToCi` tests fail on the base `staging.yml` | 16/16 pass |

## Measurements

* **F5 engine on this head (what `gate` will print).** `validation/v23/impact.py --classify` at `36fdda8d`: 0 MEASURED,
  0 VERIFIED_REUSE, 667 INVALIDATED (R6), 327 UNRESOLVED (I6); exit 1; 805 s wall on the local host (trace
  `4cc62570…`). Same counts as `F5-DISPOSITION-2`. So `gate` FAILs truthfully, with no allowlist. These edits add no
  path under a mutation COPY root, so they move no F5 state.
* **Release governance, live.** Not read: no network from this lane. The recorded W0 state
  (`RELEASE-GOVERNANCE-FINDING.md`: `protection_rules: []`, no deployment policy) gives FAIL in `Predicate`.

## Not done here (with the reason)

* **The pause itself.** The owner's W1 tag-push probe (`docs/v2.3/drafts/relgov/RUNBOOK.md`) and the W6 observation
  are owner actions. Its evidence goes to `docs/v2.3/evidence/rel-gov-01/` (the runbook is updated for A2).
* **The `measure` job of W1-DESIGN §7.** It is not in `mutation-incr.yml`: re-measuring the INVALIDATED set needs a
  runner path (`--run-affected`) that does not exist on the branch, and this lane runs the engine only.
* **Every CI leg.** None of the new or changed jobs has run on GitHub (DISC-1).

## Owner notices

1. **`pypi` environment (REL-GOV-01).** `governance` fails every stable-tag run until `pypi` has a Required reviewer
   and a single tag deployment policy (`v[0-9]*.[0-9]*.[0-9]*`), admin bypass off. The agent never changes settings.
2. **Master's paid cron (#29).** `master`'s own `conformance.yml` keeps its weekly `schedule:` with
   `ANTHROPIC_API_KEY` until the owner-authorized merge to master. To stop it earlier, disable that workflow on GitHub.
   That is an owner action.
3. **Unit legs and evidence (#52 a).** The new step makes a leg red when the suite leaves `closure-evidence/` dirty.
   No full suite was run here, so it is unknown whether today's suite does that on a CI runner. A red leg would be
   a real finding, not a reason to drop the step.
4. **Ledger appends vs the released-evidence guard (CIGOV-R1, OPEN).** `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json`
   is a blob CT-6 / #52 (b) protect and a ledger CT-5 lets grow. The seq 13 ROUND-AUTH commit and the v2.3.0
   `PRODUCTION_PUBLISH` entry each turn the guard step (all 6 unit legs) and `HistoryKept` red, and on a release tag
   block `publish`. Decide `docs/v2.3/amendments/CIGOV-R1.md` before the seq 13 commit. No exception was added.
