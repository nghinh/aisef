# V2.1 supplementary mutation campaign (owner decision 2026-10-28, approved 2026-10-29)

Closes the V2.1 mutation-qualification gap by **measuring** the 90-target supplementary scope at the pinned
merged head — not by accepting results to reach PASS. Local only: no push / tag / publish / release / paid
provider / `APPROVE.sh` / self-acceptance.

## Pinned measurement head
- **Commit:** `d043231e11b677b0c9a551c8d978f486315411fe` (branch `v2.1/probe-window`, merge of `50812da2`).
- **Product identity:** `aisef2/` tree object SHA `5f34a3f32bb101e007db67922e694efdd9c7dcad` — **byte-identical to
  `fce3d7b7`** (`git rev-parse fce3d7b7:aisef2 == d043231e:aisef2`). The only change vs `fce3d7b7` is the two
  verified kill-test edits (`tests/v2/test_v21_pm8_diagnostics.py`, `tests/v2/test_v21_fa_grep_worker.py`).
- Preflight gates + digests: [PREFLIGHT-SNAPSHOT.md](../PREFLIGHT-SNAPSHOT.md).

## Scope (90 targets, measured once)
- [SUPPLEMENTARY-SCOPE.md](../SUPPLEMENTARY-SCOPE.md): 62 MISSING ∪ 36 closure-affected = 90 targets, ~3587 mutants.
- 614-target partition set-verified: 90 new_measure + 162 still-valid-measured + 362 still-valid-reused = 614
  ([COVERAGE-614-TABLE.md](../COVERAGE-614-TABLE.md), pairwise disjoint, union == V21_TARGETS).

## How it runs (reused from campaign-9, which ran 10/10 clean)
- `tools/make_queue.py` → `queue.txt` (largest mutant-estimate first) + `queue.tsv`.
- `tools/qworker.sh C NAME SNAP` ×2 (w0, w1): atomic-claim a queue line, run `mutation.py run TARGET` inside its
  own detached worktree at `SNAP`, hermetic (`env -i`, PATH with every `opencode`-bearing dir removed, own
  HOME/XDG/TMPDIR, each run under `owned_run.py` → no provider call). Checkpoint only between targets.
- `tools/watchdog.sh C` — every 300 s logs `progress.py`; disk tiers (owner): **WARN < 15 GiB**, graceful **STOP
  < 10 GiB** (finish current target), **SIGTERM floor < 6 GiB** (only this campaign's `mutation.py run`, cwd
  checked by `lsof` — INV-MUTATION-AUTHORITY). Nothing is ever deleted; user data and `goe-*` untouched.
- `tools/sync.sh C D` — mirror the scratch campaign dir to the durable `run/` dir every 600 s (worktrees excluded).
- `tools/launch.sh C D SNAP` — starts all four, detached.

Operational dir `C` lives in the session scratchpad; the durable mirror `D` is `campaign-supp/run/`.

## Blockers kept open (do not auto-close on a green run)
- `confine.py::argv` family **`_create`, `_parser`** are in scope but their kill sets include
  `test_v21_continue_integrity.py`; measuring them produces a result but does **not** retire the open
  **`continue_integrity`** finding ([OLD-BLOCKERS-RECONCILIATION.md](../OLD-BLOCKERS-RECONCILIATION.md)).
- A T0-fail / missing-summary target is recorded in its true class (INFRA / TIMEOUT / NOT_RUN), never retried to green.

## Handoff when the queue drains (step 5)
`tools/import_supp.sh C` → `v21_mutation_record.py --import` each worker's history → rebuild MUTATION.json +
MUTATION-SUMMARY.json (reusing the 162 + 362 valid results) → audit the new survivors with evidence → build +
`--check` → run the macOS/Linux gate/suite at the committed head. Only genuinely-affected re-measurement if any
edit is made. Verdict reported honestly even if blockers remain.
