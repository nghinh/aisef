# E5 targeted campaign — frozen manifest (owner direction 2026-11-23: "E5 TARGETED CAMPAIGN CONTROL")

**This is the bounded W1b targeted measurement, not the final source-frozen RC qualification campaign.** Launched
2026-11-22 21:12:02Z, four env-guarded workers, each a `git clone --shared --no-checkout` of this repository checked
out DETACHED at the one E5 commit. Frozen before any result is accepted; the measured results, worker parity proof
and merge verification are appended below the FROZEN line only.

## Identity (point 1 of the direction — proved again at merge from every entry's own identity block)

| What | Value |
|---|---|
| Committed source SHA (all four workers) | `9b30df4414eb17d1d3e854ce42f644b3232e0b56` |
| Kernel tree at that commit (`9b30df44:aisef2`) | the E5 kernel tree (story_runner + run.py refusal branch only since v2.2.0's `e865d65c…`) |
| Target registry / generator / runner | `validation/v2/mutation.py` at the same commit (each entry records `identity.env.runner_sha256`) |
| Execution environment | `--run-affected` worker: PATH without the real opencode, scratch XDG homes, `/opt/homebrew/bin/python3` (3.14.7); each entry records `identity.platform` and `identity.env` (ENV_KEEP, _FRESH, TIMEOUT, SETTLE_S, BRACKET, COPY, tree_sha256) |
| Merge-time parity rule | every new entry across all four workers must agree on `identity.measured_on == 9b30df44…`, `identity.env.tree_sha256`, `identity.env.runner_sha256`, `identity.platform` and `identity.dirty == false`, or the merge REFUSES |

## Scope: 37 targets, ~1,882 mutants (point 2)

**Selection rationale.** Exactly the trust-critical set the W1b milestone's own edits re-open (owner ruling
2026-11-22 §C targeted qualification / §E "only the defensible affected trust-critical targets"):

* the **25 `aisef2/app/run.py::*` B1-manifest targets** (1,087 manifest mutants) — the whole-file v2.2 mutation rule
  and the B1 bindings re-open ALL of them on the `run.py:693` hunk, and the Q0-1 **Q-a** acceptance requires each to
  be MEASURED at the live bytes before a moved B1 source is accepted;
* the **11 `aisef2/orchestrate/story_runner.py::*` targets** (781 mutants at the E5 commit — `_attempt` 696,
  including ≈370 new handler/enum-swap mutants; the frozen design estimated 482) — every slice carries E5's
  additions (I1);
* the **new round target `aisef2/orchestrate/story_runner.py::_Stages.advance`** (7 mutants), kill file
  `tests/v2/test_v23_story_lifecycle.py`;
* `_attempt` and `run.py::execute` kill sets grow by the E5 fault matrix at measurement time
  (`mutation.V23_KILL_APPEND`, appended LAST; the import-time tables stay byte-identical).

**Excluded affected targets (point 5 — never relabelled).** The F5 engine at `9b30df44` classifies 667 INVALIDATED
(653 I4 from the seq-13 `tests/v2/sealing_gate.py` wiring — every kill file whose closure holds the changed `sealing`
segment — and 14 I1) and 327 UNRESOLVED (I6, no platform evidence). Outside the 37 above, **none of them is measured
here and none is labelled qualified**: they stay truthfully INVALIDATED / UNRESOLVED in every engine report until the
owner's separately-authorized final source-frozen RC campaign. The two `validation/v2/destructive_authority.py` I1
targets hold committed round-v2.3 entries (measured 2026-11-22, 202 mutants) that satisfy the v2.2-rule check; the
engine itself does not yet read round entries, so its I1 verdict for them stands in engine output and is reported
as-is.

## Partitions (point 2)

| Worker | Targets | Est. mutants |
|---|---|---|
| wa | `story_runner.py::_attempt` | 696 |
| wb | `run.py::execute` + 6 further run.py targets | ≈459 + share |
| wc | the 10 other story_runner targets + `_Stages.advance` + 9 run.py targets | ≈85 + 7 + share |
| wd | the remaining 9 run.py targets | share of 1,087 |

Exact per-worker target lists: the launch artifacts (`w{a,b,c,d}.targets`) preserved with the worker logs.

## Logs and checkpoints (point 3)

Every worker writes one line per finished mutant (`MUTANT …`, PL-6 checkpoints) and appends its record after every
target; the full logs, target lists and the launch script are preserved in the session's campaign directory and
copied beside the private W1b report before cleanup. The clones' V23 records are merged APPEND-ONLY into
`closure-evidence/v2/v2.3/MUTATION.json` (committed-prefix rule), worker by worker in a fixed order, after the
verification of point 1/4 passes; survivors get individual audits in `closure-evidence/v2/v2.3/SURVIVOR-AUDITS.json`
or stay red.

---
FROZEN before results; measured results are appended below, never edited above.

## Measured results (appended after the drain, 2026-11-25)

* **Completed: 37/37 targets, 1,880 mutants** (worker partitions wa 696 / wb 522 / wc 416 / wd 246; the frozen
  estimate said ~1,882). **1,837 KILLED, 43 SURVIVED, 0 TIMEOUT / 0 INFRA / 0 NOT_RUN; no failed targets.**
* **Wall time 52.3 h** (launch 2026-11-22 21:12:02Z → last worker 2026-11-25 01:32Z); worker time ≈ 105 h
  (wd 8.3 h, wc 13.4 h, wa 30.9 h, wb 52.3 h).
* **Identity parity:** all 43 new entries agree on `measured_on = 9b30df44…`, `env.tree_sha256`,
  `env.runner_sha256` and `platform`; merge verified the committed prefix, unique target ownership, full mutant
  enumeration and all-PASS T0 per worker.
* **`identity.dirty` finding:** 33/37 entries carry `dirty: true` — the engine appends the round record after every
  target inside one invocation, so every target after a worker's first sees the clone dirty by exactly
  `closure-evidence/v2/v2.3/MUTATION.json` (verified live per clone at merge; the measured COPY trees come from the
  one pristine FS-4 snapshot, proved by the tree_sha256 parity). Nothing is relabelled: the identities stay
  `dirty: true`, the merge acceptance is recorded here, and the F5 engine's rule that a dirty identity can never
  become MEASURED stands — those targets are re-measured cleanly (one invocation per target, committing the record
  in between) under the owner's separately-authorized final source-frozen RC campaign.
* **Survivors: 43, every one audited individually** (`closure-evidence/v2/v2.3/SURVIVOR-AUDITS.json`, 8 clusters):
  three enum/label clusters unobserved in named corners of the frozen matrix — `_attempt` L418 (stage label when a
  fault precedes the first advance; 12), L438+L439 (the landed-before-POST_MERGE containment row; 12), L317
  (role-independent CANDIDATE routing; 2) — candidate tightening rows for W2; plus diagnostic prose (L84 ×3,
  L445/L470 ×4, L485/L487 ×3), a temp-dir prefix (L238), report row order (L411), a dead `exist_ok` (L647), the
  initial `stage` placeholder (L492/L493 ×2) and byte-format-independent manifest writes (L732 ×2).
* **Post-merge gates:** `validation/v2/mutation.py --check` PASS at the record commit; round-v2.3 `b1_bindings`
  under `in_round("v2.3")`: all 25 manifest target rows accepted (Q-a), only the owner-held `kernel ` pin line
  remains (filtered by the calibration consumer per Q0-1 §2; OD-B1B unchanged).

## Correction (appended 2026-11-25; owner ruling 2026-11-25 §1 — nothing above is edited)

The post-merge-gates bullet above reported "all 25 manifest target rows accepted (Q-a)". That acceptance is
**retracted for the 22 targets whose only round evidence is dirty** (FINDING-B1-DIRTY-ACCEPT-001): the acceptance
path never read `identity.dirty`, which is a trust-critical defect, now fixed by the shared admissibility rule
`mutation.v23_admissible`. Current state: the 3 clean-measured B1 targets (`OCR_CHECKS`, `calibrations`,
`ocr_refusal`) are accepted on admissible evidence; the 22 dirty-measured ones are NOT QUALIFIED until fresh, clean
evidence supersedes their entries; `mutation --check` truthfully reports the dirty set as needing re-measure.
