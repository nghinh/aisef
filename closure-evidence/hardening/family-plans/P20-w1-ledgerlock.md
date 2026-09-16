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
