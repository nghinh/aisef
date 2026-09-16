# Phase 20 — W1 LedgerLock qualification (plan, written before any run)

Level W1 of docs/SCALE-QUALIFICATION.md: 12–20 stories (LedgerLock: 16 stories, 5 epics, dependency depth ≤ 4),
OpenCode first-class, Python, 6–12 h per run, **3 fresh runs** on an identical frozen requirements + environment
contract, ≥ 2 forced resumes per run, targeted historical replays, hidden oracle on every completed delivery.

## Reference project and environment

- Project: `~/Downloads/projects/ledgerlock-aiseftest-run2` — `docs/requirements.md` (7 511 bytes, §1–§14),
  `_bmad-output/stories.index.json` (16 stories, 5 epics; waves 6/2/2/3/2), `.ai/config.json` (`tools.test =
  python3 -m pytest -v`, `tools.lint = ruff …`, `sandbox.image = aisef-verify-python:b2c7afff2aed`, pypi hosts).
  A FRESH run starts from commit `8ff9f13` ("epics.md: split to 16 stories — second plan attempt passed"): the
  plan is approved and no story work exists. The checkout is copied per run (`w1-run-<n>/`), never reused.
- Environment on this host: docker 29.8.0 with the declared image present (id e456ae8a7c72); `opencode` 1.18.31
  routed to `9router/mycombo` (small model `9router/fast`). Recorded by Phase 17's manifest at run start.
- **Deviation to declare, not hide:** the SCALE table names Windows 11 as the W1 reference operator; the fresh runs
  here execute on macOS (this host). The framework's Windows behaviour is qualified by CI on the frozen candidate
  (Linux 3.11–3.14 + Windows 3.11), not by a W1 run. If the owner wants the Windows W1 row measured, the owner runs
  one W1 execution on the Windows machine with the same frozen candidate and this plan; nothing else changes.

## Hidden oracle (independent code, never visible to the run)

`closure-evidence/hardening/w1/oracle/test_oracle.py` — written from §14 (acceptance) and the behaviours it rests
on, driving the delivered project ONLY through the surfaces the requirements name: the CLI (`verify`, `snapshot
--out`, `apply --batch`, `repair-tail`, exact exit codes §9) and the library (`Ledger`, `ConflictError`,
`apply_batch` with `(op, key, value, rid, ts)` tuples §5/§13). Asserts: fresh-ledger verify exits 0; snapshot bytes
deterministic and NFC-keyed in byte order (NFC/NFD forms are one key); a batch commits atomically and append-only;
repair-tail removes exactly a truncated tail, is a no-op on a clean chain, refuses mid-chain corruption; tamper is
detected (exit 5); coverage ≥ 85 % under `unittest discover`; no third-party or side-channel imports; replays append
nothing, a different rid conflicts (ConflictError / exit 4), tombstones conflict like live values. Calibrated against
the archived run-2 delivery (5/16 stories): every failure is an unimplemented behaviour, none is a usage error — the
oracle speaks the requirements' surface. It runs with `AISEF_W1_PROJECT=<delivered copy>` from an interpreter that
has `coverage` (the oracle's own venv), AFTER the framework declares a terminal state, and never edits the project.
A framework DONE with a red oracle test = FALSE PASS (exit criterion); a framework BLOCKED/FAILED with a red oracle
test = a correctly classified product failure, recorded separately.

## Procedure per fresh run (identical for runs 1–3)

1. `git worktree`/copy at `8ff9f13` → `w1-run-<n>`; confirm approvals (PRD, architecture, epics, stories, readiness)
   are APPROVED for that tree's digests (Phase 6 approvals binding); record the manifest (`aisef run` captures it).
2. `aisef run --client opencode` on the frozen candidate (Phase 19 SHA; the wheel installed in a clean venv, never
   the checkout). No AISEF change during the run. No gate waived. No manual state repair.
3. Forced resumes: twice per run, at a wave boundary chosen before the run (after EPIC-01 wave 3 and after EPIC-03
   wave 1), the orchestrator is killed (SIGTERM to the process group) and `aisef run` is started again; the resume
   is recorded (journal reconcile records, lease reclaim, evidence freshness).
4. At the terminal state: `aisef status`, `aisef closure`-style probes over the run, the run log, the replay manifest
   and every drift record are archived under `closure-evidence/hardening/w1/run-<n>/`; then the hidden oracle runs
   and its per-test result is archived beside the framework's per-story verdict.
5. Historical replays (deterministic, $0): `aisef replay` over the archived 1.7.4 evidence
   (`closure-evidence/dogfood/ledgerlock-run2/replay-1.7.4*/`) with the frozen candidate — D-032 (an unrunnable
   review is UNRUNNABLE, never a verdict), D-035 (a verdict over a changed tree is stale), baseline provenance (the
   baseline root is the epoch's parent), retry hygiene (out-of-scope writes restored and recorded); each expected
   classification is stated before the replay and compared after.

## Exit criteria (per SCALE-QUALIFICATION, measured per run and across the 3)

false PASS = 0 · manual state repair = 0 · silent evidence substitution = 0 · orphan state = 0 · unexplained
condition drift = 0 (every drift record explained) · oracle run on every completed delivery · every
framework-attributed stop classified correctly (a model/product failure is allowed when classified correctly and is
recorded separately). Generated code may differ between runs; framework correctness may not.

## Cost and time (to be MEASURED on run 1, reported before runs 2 and 3)

No budget ledger survives from run 2 (`_bmad-output/budget.json` absent), so the per-run cost is unknown. Estimate
from the story count and the retry budget: 16 stories × up to 3 attempts × ≈ $0.5–1.5 per session ≈ $25–70 per run,
6–12 h wall clock. Run 1 is executed with `run.cost_cap_usd` set to $80 as a safety cap (the cap is a stop, not a
waiver); its measured cost and duration are reported before runs 2 and 3 start. If the measured runtime or cost is
excessive, the number is reported first — the target (3 runs) is not reduced unilaterally.

## Records

`closure-evidence/hardening/W1-LEDGERLOCK-<n>.json` per run (candidate SHA, manifest, per-story framework verdict,
oracle results, resumes, drift records, cost, duration, every operator arbitration) and
`W1-LEDGERLOCK-SUMMARY.json` across the three; `docs/SCALE-QUALIFICATION.md` status row updated only from those.

## Preparation record (2026-09-17, before the freeze)

- Fresh copy made: `~/Downloads/projects/w1-run-1` = clone of the reference project at `8ff9f13`, branch `w1-run-1`,
  plus one project-side commit `fd4c644` (`run.cost_cap_usd = 80` — the plan's safety cap; a project config, not an
  AISEF change). The copy has the 16-story index, the 7 gate approvals and no run state (`aisef status`: no stories
  registered).
- **Expected arbitration, stated before the run:** under the frozen candidate the `readiness` approval reads STALE
  although `stories.index.json` and `design-contract.json` are byte-identical to what the owner approved — Phase 16
  / SS-55 added the verifier-configuration digest to the readiness hash, and `approvals.py` states that a hash-method
  change stales previously signed `stories`/`readiness` approvals once. At W1 start the operator re-approves
  `readiness` for the same content and records that re-approval (gate, digest before/after, reason) in the run's W1
  record as arbitration #1. No other gate is expected to change; any other STALE is a finding, not an arbitration.
- The oracle's interpreter: `scratchpad/w1-oracle-venv` (coverage 7.16.1, pytest 9.1.1); the oracle itself is
  unchanged since its calibration.

## Sanity-check additions (2026-09-17, owner rules C and D — before the freeze)

- **Oracle v2 (rule C).** v1's calibration against the archived run-2 delivery is disowned: every expectation was
  re-derived from the frozen requirements alone and the corrections are recorded (C1–C7). The oracle is calibrated
  on `oracle/reference/` — a LedgerLock written from §3–§9/§12/§13, never from AISEF output — and ten one-line
  mutants, each of which turns its target test red (`oracle/CALIBRATION.json`). `ORACLE-INDEPENDENCE.json`: PASS
  (8/8 checks); it pins the oracle's sha256, which W1 verifies before every oracle run. Seven assumptions the
  requirements leave open carry a predeclared arbitration each: an assumption failure is escalated to the owner,
  never counted as FALSE PASS or product failure, never fixed by editing the oracle.
- **Arbitration #1 restated in the required form (rule D)** — `ARBITRATION-PREDECLARED.json`, measured on the W1
  copy: only `readiness` is STALE; recomputing the signed hash method over its two artifacts reproduces the stored
  digest exactly, so the artifacts are byte-identical to what the owner signed and the hash-method change is the
  only cause. Procedure at W1 start, so that the arbitration is not a hidden waiver: `aisef run` is started WITHOUT
  re-approval and WITHOUT `--force`; the kernel's own refusal on the STALE gate is recorded (exit, message, no agent
  call); only then is `readiness` re-approved through `aisef approve readiness` for the identical content, recorded
  (seq, digest before/after, decided_by, note = ARB-1), and the gate statuses are measured again. No new epoch; no
  approval invalidated. The owner has not separately signed this re-approval: if the owner rejects it, the re-approval
  and every run resting on it are void.
- **Step 5 restated precisely (rehearsed on e5d451b, `w1/HISTORICAL-REPLAY-rehearsal-e5d451b.json`, PASS).** The archive
  keeps the 1.7.4 replays' evidence as flat `<STORY>.evidence.jsonl` files; `aisef replay` needs the story index, story
  files and config of the state that produced them, now kept as `w1/historical-replay/state-1.7.4{,-opencode}/`
  (README records provenance; replaying the archived files over the snapshot reproduces the working copy row for
  row). A bare layout mis-keys the story (`STORY-01-06.evidence`) and flips `criteria have tests` — a fixture
  artefact, not kernel behaviour, and the reason `w1/historical_replay.py` renames the files. Expected
  classifications, stated before the frozen run and reproduced in the rehearsal: 13 attempts; exactly five changed
  rows — STORY-01-06 attempt 3 @ eed6f87 (`no baseline regression`, `TDD`, `tests verify story` ✗→✅: the epoch
  root's baseline seq 2 is compared, not the resume's re-run seq 41 that 1.7.4 chose by recency; verdict stays
  FAIL on `guard ran` + `review`) and STORY-03-01 attempts 3 and 5 @ 01c1d30 (`no baseline regression` ✗→✅,
  FAIL→PASS — the archive's own OBS-OC-1 baseline-provenance defect, 1.7.5's correction reproduced: seq 2 at
  9cf22f5c compared, seq 393 at the story's own candidate ignored). D-032 on archived records: the 1.7.3 review
  record is a structured ok=False and stays ✗ (prose never upgrades a legacy record); the typed UNRUNNABLE of the
  1.7.4 opencode record (STORY-04-01 attempt 3) stays ⚠. D-035 and retry hygiene are run-loop properties `aisef
  replay` cannot exercise on archived evidence; the runner executes `test_verdict_freshness`, `test_retry_hygiene`
  and `test_baseline_provenance` on the candidate instead (29 passed). Any other changed row on the frozen candidate
  is a finding.
- **Procedure additions from the driver rehearsal (scratch copy of w1-run-1, dry wheel venv, $0 — `w1/w1_driver.py`).**
  (1) *Guard plugin*: the reference project has no `.opencode/plugin`; `aisef run` then records `guard ran` as not
  applicable for every story (guards not compiled), and a compiled-but-uncommitted plugin fails `guard ran` in every
  worktree (the 1.7.4 replay's warning). Preparation step, per run, before `kernel-first`: `aisef compile --client
  opencode --bin <run venv>/bin/aisef` with the CANDIDATE's aisef, then commit `.opencode/` and the compile report to the
  run copy (a project-side commit like the cost cap; the plugin embeds the candidate binary's path; OpenCode's
  capability report — dir_allowlist unsupported, tool_allowlist emulated, turn_limit unsupported — is archived with
  the run). (2) *Known environment condition*: `aisef doctor` reports `tools.sast` (auto-detected `bandit -q -r .` for a
  pyproject project) missing in `aisef-verify-python:b2c7afff2aed`; the gate reads no sast (run-2's F-B), so the
  reference environment is kept as is and every sast TOOL_UNRUNNABLE record must be typed correctly — recorded, not
  fixed. (3) *Kernel path first, measured*: `aisef run --client opencode` on the stale readiness with no `--force`
  exits 2 with `gate not approved: readiness`, no agent session, no story evidence; only then `aisef approve
  readiness --note ARB-1`, after which exactly one gate changed (readiness → approved). (4) *Finish*: the hidden oracle
  runs on a clean `git clone --branch master` of the run copy, never on the run's working tree; the oracle's sha is
  checked against ORACLE-INDEPENDENCE.json before every run; a red oracle test is a FALSE PASS iff every story
  covering its FRs (`w1/oracle-fr-map.json`, predeclared) is DONE, or the run is complete; otherwise it is a
  correctly classified product failure. (5) *Forced resumes*: SIGTERM to the `aisef run` process group at the first
  `wave=EPIC-01/w3 DONE` and `wave=EPIC-03/w1 DONE` lines of run.log, `aisef run` started again; survivors of the
  kill and 90 s after the resume start are measured and recorded, never silently killed. (6) *Stall*: no log growth
  for 2 h → SIGTERM, recorded as a measured stop.
- **Trunk topology corrected (rehearsal finding, 2026-09-17).** The fresh copy had been prepared as branch `w1-run-1`
  (8ff9f13 + fd4c644) while its `master` and `origin/*` still carried run-2's delivered state (47b3eb7, 5 stories,
  the `ledgerlock/` package). The run loop integrates into the CURRENT branch (`control/worktree.py` resolves HEAD), so
  the run itself would have been fresh, but the driver's finish clones `master` and nothing should be able to fetch a
  delivery from a remote. Preparation now: `git checkout -B master w1-run-1`, `git branch -D w1-run-1`,
  `git remote remove origin` — master = fd4c644 (8ff9f13 + the cost-cap commit), no `ledgerlock/` at master, no
  remotes, one branch. The driver's prepare phase asserts exactly this (`fresh_topology_ok`: HEAD on master, only the
  named preparation commits after 8ff9f13, no `ledgerlock/`, no remotes) before anything else runs. Runs 2 and 3 are
  prepared the same way from the reference project at 8ff9f13.
