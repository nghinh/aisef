# AISEF v2.3 — W0 BASELINE (workspace, artifacts, inventory)

**Captured:** 2026-11-21 · **Branch:** `release/v2.3-big` (off master `399b775f`, the clean 2.2.0 line:
`v2.2.0` = `da3ea33f` plus the owner-approved README/docs/landing refresh; `pyproject` version `2.2.0`).
Per directive, `master`/`v2.3.0`/PyPI stay untouched until final owner sign-off; v2.3 work lives on this branch
and isolated worktrees.

## Immutable released baselines (do not alter)

| release | tag → commit | PyPI wheel / sdist sha256 (live, verified) |
|---|---|---|
| 2.2.0 | `v2.2.0` → `da3ea33f` | wheel `8c94dd6bd6ac…` · sdist `102cda44738a…` |
| 2.2.1 | — (**abandoned** 2026-11-21) | never published; the version bump orphaned version-derived evidence (`EVID-COUPLING-01`). README fix folded into v2.3; master force-restored to the 2.2.0 commit. |

Historical V1 / V2.0 / V2.1 / V2.2 evidence and `RELEASE-DECISIONS.json` ledger entries are **immutable**.

## Workspace state at W0

- `master` HEAD = `origin/master` = `399b775f` (clean 2.2.0; the 2.2.1 attempt was force-reverted, v2.2.1 tag deleted — nothing was published, PyPI stays at 2.2.0).
- `v2.2.0` = `da3ea33f` (frozen, tag intact); `pyproject` version `2.2.0`; suite green on this base (`test_c2_p5_acceptance` OK).
- Open PRs: 0. Backups: <mutation-server> <server backup job> cron re-enabled (2026-11-21); <backup-host> backup active. Disk: <mutation-server> 118G free after campaign-scratch cleanup.
- **Release governance:** `pypi` environment has **no protection rules** — see `RELEASE-GOVERNANCE-FINDING.md` (blocker `REL-GOV-01`).

## Static source inventory (counts, not yet a line-by-line audit)

| area | `.py` files | LOC |
|---|---|---|
| `aisef2/` (V2 kernel/runtime) | 94 | 20,868 |
| `aisef/` (legacy V1 framework) | 109 | 41,083 |
| `validation/` (qualification/release machinery) | 149 | 51,350 |
| `tests/` | 603 | 156,434 |
| `framework/` | 15 | 2,444 |
| `.github/workflows/` | 12 yml | — |

`aisef2/` packages: `app`, `orchestrate`, `journal`, `product`, `probe`, `plan`, `control`, `runtime`,
`invariants`, `quality`, `arch`, `cohort`.

Roadmap checkboxes in `docs/ROADMAP-2.2-CHECKLIST.md`: 67 checkbox lines. V21 backlog
(`docs/v2/V2.1-BACKLOG.md`): 88 findings (≈102 `V21-` reference lines).

> **Declared limit (directive §A):** these are automated-inventory counts. The per-module trust-boundary
> audit (`CODE-AUDIT.md`), the per-ID reconciliation (`MASTER-CHECKLIST.md`) and the frozen acceptance
> criteria are produced by the W0 audit pass that follows; no file is claimed inspected until it is.

## Frozen qualification baseline (from existing results — no new campaign)

Per directive §A ("Do not initiate a large campaign to obtain a baseline"), the v2.3 starting baseline is the
already-measured 2.2 qualification:

- **Full cross-platform CI, all green:** release run `44822406556` (2.2.0, `da3ea33f`) = **success** — unit
  ubuntu 3.11–3.14 + windows 3.11 + macos 3.12, lint, wheel, and the `AISEF_SEALING=1` sealing job. This is the
  frozen green matrix v2.3 must keep.
- **Mutation currency on the branch base:** `validation/v2/mutation.py --check` = **PASS** (2 informational
  `SUPERSEDED` liveness rows, not failures). Records current for the unchanged `aisef2` kernel `e865d65c`.
- **Mutation gate (committed record `V2.2.0-STATUS.json`):** risk-based, 177/177 targets measured, 0 MISSING;
  5,909 mutants = 5,782 killed + 127 audited-benign survivors; Windows-native 60/60; `checker_calibration` 57/57;
  `currency_dag` clean.
- **Packaging:** `packaging_check` (wheel+sdist hold exactly `aisef`+`aisef2`) passed on the 2.2.0/2.2.1 builds.
- **Reproducibility caveat:** the sdist inherits host file-permission bits (`repro_dist.py` keeps modes), so only a
  fresh-checkout build reproduces the frozen sdist — `RISK-REGISTER.md` `BUILD-REPRO-01` (cross-Python 3.12↔3.14
  is NOT the cause; measured identical from a clean tree).

No requalification of historically frozen evidence is performed (directive §C). The W1 F5 efficiency targets are
measured against this frozen baseline, cold-vs-incremental, with hardware reported.

## W0 freeze confirmations (2026-11-21)

**Git identity.** Commits authored as `AISEF Dev` (repo-local identity; e-mail configured, deliberately not
recorded here). All v2.3 commits carry the agent co-author trailer.

**Branch isolation.**
- `release/v2.3-big` is **local only** (not on `origin`) — `docs/v2.3/CODE-AUDIT.md` contains security findings
  and is held back from the public repo pending a disclosure review (owner ruling D).
- `master` = `origin/master` = `399b775f`; `release/v2.3-big` descends from it; one worktree.
- `v2.2.0` → `da3ea33f` (annotated tag object `92359a6d`), unchanged. Leftovers of the abandoned 2.2.1 attempt are
  gone: tag `v2.2.1` deleted, remote branch `release/v2.2.1` deleted, `master` force-restored.
- `aisef2/` kernel tree at `399b775f` = `e865d65c` = the 2.2.0 RC2 kernel (no kernel change since v2.2.0). Changes
  since v2.2.0: README ×2, docs ×3, landingpage ×1, closure-evidence ×9, validation ×1 (`c2_closure_audit.py`).

**CI / measurement baseline** — last all-green full matrix, release run `44822406556` (v2.2.0, `da3ea33f`):

| job | wall (min) | job | wall (min) |
|---|---|---|---|
| unit ubuntu 3.11 | 47.2 | unit windows 3.11 | **84.4** |
| unit ubuntu 3.12 | 58.8 | unit macos 3.12 | **84.9** |
| unit ubuntu 3.13 | 43.3 | sealing (`AISEF_SEALING=1`) | 56.3 |
| unit ubuntu 3.14 | 59.6 | lint / wheel / staging / publish | 0.5 / 0.9 / 0.5–0.7 / 0.7 |

Critical path ≈ **85 min** (macOS/Windows unit legs). Suite size **8,282 tests** (ubuntu 3.12, 4,187.6 s). Current
`master` `399b775f`: CI run `44854057309` = **success, all 9 jobs** (lint, wheel, ubuntu 3.11/3.12/3.13/3.14, windows
3.11, macos 3.12 — 87.4 min, sealing), completed 2026-11-21 03:34Z. This is the authoritative current baseline: the
branch base is green on the full matrix.

**Non-gating workflow (CODE-AUDIT #30, ACCEPTED_LIMITATION):** `diagnostic.yml` is the legacy P7-FINDING-001
ORCH_9/10 reproducer (mechanism found `d9a7bb7c`), triggered only on `hardening/systematic-v1`; it is not a v2.3 gate.
Add `release/**` to its triggers only when a v2.3 diagnosis needs it.

**Independent CI confirmation of EVID-COUPLING-01:** run `44845163565` on the abandoned `c9a3cbb6` failed on all six
unit legs + sealing — 8,282 tests, failures=2 + errors=1, all `V2.2.1-PROBE-CALIBRATIONS.json is missing`:
`test_c2_p5_acceptance.V21Records.{test_the_committed_re_verification_is_current_only_exactly_with_every_guard_run,
test_each_re_verification_check_refuses_for_its_own_reason}` and
`test_qualification_release_mode.Subject.test_release_q2_reads_the_calibrations_the_rc_ships` (the third one was not
caught by the local targeted run — every version-keyed consumer must be enumerated by F5).

**Build baseline.** `setuptools==84.0.0` pinned in `[build-system]`; CI builds with CPython **3.12**
(`staging.yml`); `SOURCE_DATE_EPOCH` = commit time via `release_rc.py --epoch`; sdist re-packed by `repro_dist.py`.
Published 2.2.0: wheel `8c94dd6b…`, sdist `102cda44…`. Measured: from a **fresh checkout**, wheel and sdist are
byte-identical between local CPython 3.14 (zlib 1.2.12) and CI CPython 3.12. A build from a working tree whose
files carry non-git permission bits (two files at `0600`) yields a different sdist (mode-only difference) —
`BUILD-REPRO-01` (corrected root cause: `repro_dist.py` preserves filesystem modes).

**Qualification baseline on `399b775f`.** `validation/v2/mutation.py --check` PASS; `release_calibration.py --check`
PASS; `test_c2_p5_acceptance` + `test_qualification_release_mode` OK.

## W0 artifact inventory (frozen at the W0 freeze commit)

| Artifact | Content |
|---|---|
| `BASELINE.md` | this file — released baselines, workspace, identity, branch isolation, CI/build/qualification baselines |
| `RELEASE-GOVERNANCE-FINDING.md` | REL-GOV-01 (pypi env has no required reviewer) |
| `RELEASE-CHARTER.md` | v2.3 claims, non-goals, gates, publication rule |
| `RISK-REGISTER.md` | REL-GOV-01, EVID-COUPLING-01, BUILD-REPRO-01 (corrected root cause), KERNEL-COUPLING-01 (measured), EVID-PLATFORM-01, EVID-SCALE-01 |
| `CODE-AUDIT.md` | 104 defects / 106 rows (#6 and #39 split a/b; P1 3 / P2 43 / P3 60 by row) with location, impact, adjudication, dup-of, wave/lane, acceptance criterion; 20 subsystem maps |
| `MASTER-CHECKLIST.md` | 147 unique IDs (135 inherited + 5 split residuals + C3b + 6 risk IDs), untruncated evidence, every W0-closure correction annotated |
| `DEPENDENCY-DAG.md` | wave table (every open ID + defect in exactly one wave), edge list, critical path, lanes + file ownership, owner-gated decisions, exit gates |
| `COMPATIBILITY-MATRIX.md` | frozen contracts for released v2.2 artifacts + historical evidence |
| `THREAT-MODEL.md` | assets, actors, boundaries with enforcing code, threats, non-goals, allowed claims |
| `ARCHITECTURE.md` | shipped v2.2 architecture + v2.3 target per wave (W1 section amended by W1-DESIGN) |
| `MUTATION-IMPACT-BASELINE.md` | measured inventory, per-mutant/target/campaign cost, blast radius, cold-vs-incremental protocol |
| `W1-DESIGN.md` | frozen F5 design + EVID-COUPLING-01, E5 (W1b), REL-GOV-01, BUILD-REPRO-01, F2, AUTHCHK; exact files; negatives N1–N34 + NA1–NA9; measurement protocol; exit gates; STOPs |
