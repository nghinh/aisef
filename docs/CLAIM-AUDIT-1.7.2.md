# Claim audit — public surfaces at AISEF 1.7.2

Owner task, 2026-09-15: every current-state claim on the public surfaces must
be no stronger than the artifact behind it. Surfaces audited: `landingpage/`,
`README.md`, `README.vi.md`, `docs/SALEKIT.html`, `docs/USAGE-GUIDE.md`,
`docs/HUONG-DAN-SU-DUNG.md`, `docs/ROADMAP-POST-1.0.md`, `docs/SOLUTION.md`.
Historical records (ADRs, dated assessments, bench reports, the taxonomy, the
register, the closure contract, `CHANGELOG.md`) were read but not rewritten.

Status vocabulary: **VERIFIED** (a command or file in this repository
reproduces it now) · **MEASURED** (recorded once, artifact on disk, not
re-runnable for free) · **QUALIFIED** (true under a stated scope or limit) ·
**PENDING** (awaiting an event) · **HISTORICAL** (true of a past state,
presented as such) · **UNSUPPORTED** (no artifact; corrected).

## 1. Release and closure identity

| claim | status | artifact / command |
|---|---|---|
| current public version 1.7.2 | VERIFIED | `https://pypi.org/pypi/aisef/1.7.2/json`; `closure-evidence/releases/1.7.2.json` |
| release tag `v1.7.2` → `d092b25fb94ec463347e6a5a04d1cc43a7fc2df8` | VERIFIED | `git rev-list -n 1 v1.7.2`; `docs/closure-gate.json#closure_target_sha` |
| wheel `d97ca56d…`, sdist `7fe16a4f…` observed on PyPI, every member byte-equal to the tag | VERIFIED | `closure-evidence/releases/1.7.2.json#observed` (109 + 215 members, 0 mismatched, 0 unmapped) |
| closure 24 of 27, only G6.1–G6.3 open | HISTORICAL for 1.7.2 — the LedgerLock dogfood intake made G2.3 FAILED (D-026/D-028/D-029); 1.7.3 (tag `v1.7.3` = `cfee273`, released 2026-09-15) closed them and read 24 passed · 3 unrunnable again; the second LedgerLock run, on 1.7.3, found D-032 (P1) and 1.7.4 (tag `v1.7.4` = `9dcd402`, released 2026-09-15) closed it and read 24 passed · 3 unrunnable; the clean OpenCode replay of that run, on 1.7.4, found D-033 (P1) and 1.7.5 (tag `v1.7.5` = `2311624`, released 2026-09-16) closed it — 24 passed · 3 unrunnable, measured after the 1.7.5 manifest and bundle | `python3 bin/aisef closure`; `closure-evidence/releases/1.7.5.json`; `closure-evidence/dogfood/ledgerlock-run2/replay-1.7.4-opencode/REPLAY-OPENCODE.json` |
| zero waivers | VERIFIED | no `closure-evidence/closure-state.json`; report tally has no `waived` |
| C-2 = INCONCLUSIVE, not rerun | VERIFIED | `docs/BENCH-REPORT-C2.md` §1; `closure-evidence/cohorts/C-2.json`; G5.1/G5.2 PASSED |
| D-024 OPEN P3, non-blocking | VERIFIED | `docs/DEFECT-REGISTER.json`; G2.3 PASSED ("0 open P0/P1 of 24") |
| v1.7.0 = immutable failed release attempt, never on PyPI | VERIFIED | `closure-evidence/closure-target-chain.json`; `closure-evidence/v1.7.0-release-attempt.json`; PyPI 404 |
| v1.7.1 = previous public baseline, superseded as closure target by D-022 | VERIFIED | `closure-evidence/releases/1.7.1.json`; chain entry |
| G1.0 unmoved by evidence/documentation commits after the release | VERIFIED | `aisef closure` after commits `25ed1ed`, `ad0211e`, `7e34467`, `6ea40a0`, and this one; `tests/test_release_identity.py` |

## 2. G6 status — the special check

| surface | before | finding | after |
|---|---|---|---|
| `landingpage/index.html` "Not yet proven" | "…is in the hands of an external participant with a frozen instruction bundle" | **UNSUPPORTED**: no artifact shows a genuine external human has received or started the bundle. Bundle existence and owner acceptance of the handoff are not receipt. The LedgerLock dogfood run is AI-operated and is not G6. | "The G6 handoff bundle for the public 1.7.2 release is ready and frozen; independent external-human validation is awaited, and until a genuine participant's report is in, this line stands" |
| `README.md` / `README.vi.md` closure paragraph | "the three open criteria are external validation by a person outside the project" | consistent — names the requirement, not a participant | unchanged |
| `docs/ROADMAP-POST-1.0.md` | "1.7.2 is the release under G6 validation" | acceptable as *the release the G6 bundle targets*; no participant implied | unchanged |

Correct status: **PENDING** — G6 handoff ready
(`closure-evidence/external-validation/1.7.2/`, record
`1.7.2.bundle.json`, instructions digest `376c6e60…`), awaiting independent
external-human validation. No participant is named anywhere.

## 3. Numeric claims, re-bound to their measurement

| number | where | status | measurement (scope named) |
|---|---|---|---|
| 3,122 tests, 0 failing | landing, sales kit, README (via USAGE-GUIDE) | VERIFIED | `python3 -m unittest discover -s tests -q` at `7e34467`: `Ran 3122 tests … OK (skipped=19)`. Same tree under pytest: 3103 passed / 19 skipped (`closure-evidence/suite.json`, commit `8493b7c`). 3122 − 19 = 3103; the two scopes agree. The earlier 3,075 was the same command on 1.7.1. |
| 19 skipped | USAGE-GUIDE §… | VERIFIED | same runs; skips are the Docker-only and history-dependent tests |
| 36,208 lines of Python | sales kit | VERIFIED | `find aisef -name '*.py' -print0 \| xargs -0 cat \| wc -l` at HEAD (all lines, `aisef/` only). Earlier 31,913 was the same command on 1.7.1's tree. |
| 185 taxonomy rows; 31 register entries (20 CLOSED, 11 OPEN: D-002, D-003, D-011 P2; D-024 P3; D-025…D-031 from the LedgerLock dogfood intake, of which D-026, D-028, D-029 are P1) | README, sales kit | VERIFIED (re-bound 2026-09-15 after the intake; was 178 / 24 / 4 OPEN) | `docs/FAILURE-TAXONOMY.md` max id 185 (`tests/test_meta.py` binds README to it); `docs/DEFECT-REGISTER.json`; `closure-evidence/dogfood/ledgerlock/`. Sales kit's "130 defects in the taxonomy" was stale → 178 → 185. |
| 11 cause classes | README, sales kit | VERIFIED | `docs/FAILURE-TAXONOMY.md` § "Mười một lớp nguyên nhân" |
| 70 config keys | landing, HUONG-DAN, USAGE-GUIDE §18, STABILITY | VERIFIED | `python3 -c "from aisef.config import DEFAULTS; print(len(DEFAULTS))"` → 70; `tests/test_meta.py` binds STABILITY to it. USAGE-GUIDE §18 said 69 → 70. Landing's "0 mandatory" was ambiguous (`tools.test` defaults to `""` and must be declared for tests to run) → "every key has a default". |
| 34 CLI verbs (33 project verbs + `aisef closure`) | USAGE-GUIDE §17, HUONG-DAN | VERIFIED | `aisef --help` / `argparse` subparser choices = 34. Both guides said 33 and omitted `closure`; corrected in prose only — no fenced `aisef` line was added, because USAGE-GUIDE's fenced commands are part of the G6.1 onboarding digest. |
| 14 frozen verbs | USAGE-GUIDE, STABILITY | VERIFIED | `docs/STABILITY.md` § CLI commands |
| 10 guards, 3 lifecycle moments | landing, sales kit | VERIFIED | `len(GUARD_MATCHERS)` = 10; `aisef.clients.compile.HOOK_EVENTS` = PreToolUse, PostToolUse, Stop |
| 10 / 9 guards wired (Claude / OpenCode) | USAGE-GUIDE | VERIFIED | `aisef compile` on public 1.7.2: Claude 8 before-action + completion + diff-scope; OpenCode 8 + diff-scope |
| 48 gate controls = 16 × 3, all present | landing, sales kit, README, guides | VERIFIED | `aisef.control.gate.qualification_table()` → 16 rows, each positive/negative/env true |
| 18 reviewer cells = 6 × 3 | landing, sales kit | VERIFIED | `aisef.control.reviewer_qual.qualification_table()` → 6 classes, each with 3 controls |
| 0 dependencies | landing, sales kit, README | VERIFIED | `pyproject.toml` `dependencies = []`; `pip list` in a fresh venv after `pip install aisef==1.7.2` shows only `aisef` |
| 150 skills installed by `aisef setup` | quickstart step 8 | QUALIFIED | measured on public 1.7.2 with the quickstart's sample `requirements.md` (python stack): `installed 150 · total 150`. A different requirements text gave 118 — the count depends on the detected stack. |
| 91 MB reference cache | README, guides, quickstart | VERIFIED | `du -sh ~/.cache/aisef/references` → 91M on 2026-09-15 (was written as "about 93 MB") |
| conformance 10/10, Claude + OpenCode, 2026-09-08 | landing, sales kit, README | QUALIFIED | `docs/CONFORMANCE.md`; G3.1 PASSED with 7 days left of the 14-day window (expires 2026-09-22). Owner ruling 5: not re-run to refresh a timestamp. |
| 4 agent roles, 3 evidence tools, 4 sandbox levels, 5 named guarantees, 8 human gates | landing, README | VERIFIED | `harness.routing.ROLES`, `harness.tools.TOOLS`, `harness.sandbox.Level`/`Guarantee`, `control.approvals.GATE_ORDER` |
| 30 bench tasks, 28 valid | ROADMAP | VERIFIED | `tests/bench/tasks/` (30 dirs); `invalid_reason` set on `bug-6`, `bug-15` |
| 411 recorded attempts; 339 before `exit_status` existed | landing | MEASURED | `docs/PROJECT-CLOSURE-GATE.md` (G5.2 discussion, "339 of 411 rows"); raw rows in the gitignored `.bench*/results.jsonl` |
| 12 of 340 cross-arm pairs informative (3.5 %), 25 of 30 tasks never separated | landing | MEASURED | `docs/BENCH-TASK-DISCRIMINATION.md`; recompute: `python3 validation/bench_discriminating_power.py` |
| C-1 0.64 vs 0.69, +44 % turns, +51 % wall-clock, guard fired once in 72 | README, landing | HISTORICAL/MEASURED | `docs/BENCH-REPORT-C1.md` |
| C-1b +27 % turns; its +0.06 does not survive re-reading | landing | HISTORICAL/MEASURED | `docs/BENCH-REPORT-C1B.md`; withdrawal in `docs/BENCH-REPORT-C2.md` §5 |
| C-2 1.51× tokens, 11 of 12 at ceiling, bare 36/36, AISEF 0.97 vs 1.00 | landing, README table (row added) | MEASURED | `docs/BENCH-REPORT-C2.md` §1–§2 |
| "four cohorts, four nulls" | landing | QUALIFIED | reworded to name them: v0.3.0 (saturated), C-1 (null), C-1b (artifact, withdrawn), C-2 (inconclusive). README's table now lists all four. |
| 4–22 % of spend bought a gate-passed attempt | landing, USAGE-GUIDE | MEASURED | `docs/handoff/o4-cost-per-outcome.md` §… ("4 %, 16 %, 20 %, 22 %" across four corpora); `aisef cost` |
| review layer: false block 10.5 % (6/57, floor), miss 34–39 % (27/70), 11 of 20 reversals | landing, USAGE-GUIDE, HUONG-DAN | MEASURED | `docs/O1-RECOMPUTE-AFTER-158.md`; `docs/PROJECT-CLOSURE-GATE.md` G2.4; recompute: `python3 validation/recompute_reviewer_qual.py` |
| crash recovery: three paths + a real SIGKILL mid-write | landing | VERIFIED | `tests/test_crash_recovery.py` |
| 67 % of input tokens into blocked attempts; review 18 of 31 blocks | README | HISTORICAL/MEASURED | `docs/E4-COST-DECOMPOSITION.md` (todo-e2e) |

## 4. Present-tense claims that were historical

| surface | claim | correction |
|---|---|---|
| README, README.vi | "The dogfood acceptance scope is EPIC-01 of `e9` … `e9` is the framework's acceptance corpus" | `e9` is no longer on disk and is not the closure corpus. Now: the closure corpus is `marks-cli` (owner ruling 2), 7/7 done, PRE_DEPLOY signed 2026-09-14, G4.1–G4.7 PASSED; the `e9` scope is stated as history. |
| README, README.vi | benchmark table "Three cohorts, three null results" ending at C-1 | C-2 row added; "four null or inconclusive results". |

## 5. Unsupported comparatives

| surface | claim | correction |
|---|---|---|
| sales kit | "Ten capabilities that no other agent framework offers in combination" | no external systems matrix exists (that is Part II research) → "each measured on real agents…; no claim of uniqueness is made beyond that table" |
| sales kit | "a principle no other tool enforces" | removed |
| sales kit | four "World first" badges | "Measured" |

No "world #1" or equivalent remains on any audited surface.

## 6. Constraints held

- Product plane: no file under `aisef/`, `pyproject.toml` or license files
  changed (`planes.changes` from `d092b25` to HEAD: PRODUCT 0, UNRESOLVED 0).
- G6 bundle: `closure-evidence/external-validation/1.7.2/` and
  `1.7.2.bundle.json` untouched; instructions digest `376c6e60…` recomputes.
- Onboarding digest before and after every documentation edit:
  `8b25f481373a6ee6d7dbe9bec3918726465ce02e8d52ea0af8ea1b49dec95b73`
  (`python3 -m aisef.control.onboarding`, exit 0). No command in README
  Install/Quick Start, USAGE-GUIDE or the protocol's Protocol section changed.
- Tests, closure semantics, verification semantics, benchmark protocol,
  release manifest: unchanged.
- Known potential G6 documentation finding, not pre-classified and not coached
  around: the frozen `QUICKSTART.md` in the bundle expects `aisef-1.7.1` in
  steps 1–2 while `INSTRUCTIONS.md` pins 1.7.2 (see
  `docs/G6-RETURN-PLAYBOOK.md` §E).
- GitHub Releases: none created; the `CHANGELOG.md` 1.7.2 entry is the draft
  if one is wanted later.
