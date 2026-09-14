# Handoff — O3: preservation radius calibrated (2026-09-14)

Closes issue **O3** of `docs/ADR-009-phase-3-cross-tier-invariants.md`. The full
record, including the calibration table and the ground-truth derivation, now
lives in that ADR under *Closed — O3: preservation radius, calibrated
(2026-09-14)*. This file is the short version plus the paragraph for
`CHANGELOG.md`.

## What changed

| file | change |
|---|---|
| `aisef/config.py` | new knob `story.verified_touched_weight` (default **0.0**, `float` in `_TYPES`, rejected when negative), with the whole calibration table in the comment above it |
| `aisef/control/complexity.py` | `read_ledger` now returns the **evidence projection** (`ledger.build`), with `ledger.json` filling in only behaviours evidence does not mention; `score_story` takes `config=` and reads the knob; `VERIFIED_TOUCHED_WEIGHT` restated as a calibrated default rather than a pin |
| `aisef/control/preflight.py` | `story_size_defect` passes its `cfg` into `score_story` so the gate honours the knob |
| `aisef/phases/run.py` | the per-story score recorded into `complexity.json` passes `config` too, so the recorded row reflects the configured weight |
| `validation/o3_preservation_radius.py` | **new**, re-runnable: regenerates every number in the ADR from `_bmad-output/` on disk. No model calls, no network |
| `docs/ADR-009-phase-3-cross-tier-invariants.md` | O3 moved out of *Open* (now "the three remaining semantic issues") into a *Closed* section carrying the measurement |
| `docs/SOLUTION.md` | §13 threshold table: new knob row, and the `story.max_complexity` row no longer says the neighbour dimension is "recorded but not yet scored" |
| `docs/STABILITY.md` | config-key count 68 → 69 |
| `docs/ROADMAP-POST-1.0.md` | the ADR-009 anchor it links to was renamed; O3 now points at the *Closed* section |
| `tests/test_story_size.py`, `tests/test_config.py` | the five tests listed below |

`VERIFIED_TOUCHED_WEIGHT = 0.0` is unchanged as the module default, so
`tests/test_complexity.py::test_verified_touched_weight_is_zero` still holds.

## Measurements

Reproduce with `python3 validation/o3_preservation_radius.py --counts`.

**`e9` is not on this machine.** `find /Users/nghinh/Downloads/projects -maxdepth 2
-name "*e9*"` returns nothing; `find /Users/nghinh -maxdepth 4 -type d -name "e9"`
returns only `~/Library/Messages/Attachments/e9`, `~/.dartServer/...` and
`~/.npm/_cacache/index-v5/e9`, none of them a corpus.
The three stories the ADR's pinning note cited (02-03, 03-03, 05-01) are
therefore **not reproducible** and are not in the table. Corpora used:
`todo-oc`, `todo-cli`, `todo`, `todo-e2e`. `marks-cli` is excluded — it was the
live dogfood run while this was measured (`find ... -mmin -120` showed 92 files
written there and none in the other four).

**A stale input had to be fixed first.** `complexity.read_ledger` read
`ledger.json`, which is refreshed only at the end of a sprint or by `aisef
report`, while the preservation gate and the developer's preservation slot both
reproject from evidence (`implement._ledger`, whose docstring already names this
exact problem). Measured: **24 of 32** recorded stories were scored against
fewer neighbours than the projection held — todo-e2e STORY-05-01 recorded 0
against a projection of 9, and **12 of the 15** real regressors were scored at 0,
so the dimension a weight multiplies was inert exactly where it mattered.
Projection cost, measured on the four corpora: 44–350 ms for 0.8–6 MB of
evidence.

**Ground truth.** A story counts as having broken a neighbour only when the
recorded run proves it, from either source: the gate's own `preservation` check
recorded `failed` in a `gate:verdict` note, or a ledger `REOPENED` entry
corroborated by red evidence at the same instant (the named criterion red for an
`ac`, a criterion of the owning story red for `fr`/`nfr`, a red `qa:*` run or a
failed `mockup_map`). 32 scored stories, **15** confirmed regressors, 17 clean.

**The table** (blocked = score crosses `story.max_complexity` = 16.0 once the
neighbour dimension is weighted):

| weight | blocked | innocent blocked | regressors caught | regressions missed |
|---:|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 | 15 |
| 0.25 | 0 | 0 | 0 | 15 |
| 0.5 | 0 | 0 | 0 | 15 |
| 1.0 | 0 | 0 | 0 | 15 |
| 1.5 | 3 | 2 | 1 | 14 |
| 2.0 | 6 | 3 | 3 | 12 |
| 2.5 | 7 | 3 | 4 | 11 |
| 3.0 | 10 | 4 | 6 | 9 |
| 4.0 | 14 | 6 | 8 | 7 |
| 5.0 | 18 | 7 | 11 | 4 |

Chosen value **0.0**: nothing at or below 1.0 changes a single verdict (the 0.5
the note pinned back included), the first verdict a larger weight changes is a
false block (todo-oc STORY-04-03, blocked once w passes 1.08, which broke
nothing) and the first
true positive only arrives at 1.11, and buying 11 of 15 regressors costs
blocking 7 of the 17 clean stories. Spearman(neighbour count, broke a
neighbour) = **0.235**; mean count 3.13 for regressors against 2.12 for clean.

## Two findings that are not O3

1. **29 uncorroborated `REOPENED` entries** across the four corpora. The
   clearest is todo-cli STORY-06-01: five requirements flipped to REOPENED while
   all 65 of its tests were green, because that story `covers` the same
   requirements as three earlier stories and had one criterion with no test, so
   its own rollup wrote them red — and `Ledger.observe` keeps that red while
   discarding the green written for the same requirement moments later in the
   same loop (green on an unlanded candidate returns early). Whoever takes **O2**
   should look here.

   **Corrected 2026-09-14 — this one was taken, and it was a defect, not an
   artifact** (bug 155 in `docs/FAILURE-TAXONOMY.md`). The text above stands as
   what the measurement saw. `_observe_tests` now judges a requirement **once per
   test run** rather than once per story that covers it: green from any story
   whose criteria are all green in that run wins, and the absence stays recorded
   on the criterion it belongs to (`untested`). Ordering rule made explicit: the
   ledger orders events by `(at, sid, seq)` and the order of `targets` *inside*
   one event is not an ordering, so the verdicts are aggregated before
   `Ledger.observe` sees them — the unlanded-candidate early return is unchanged.
   Same script, no change to what counts as corroboration: **29 → 4**
   uncorroborated (todo-oc 5→0, todo-cli 5→0, todo-e2e 15→0, todo 4→4); the 15
   confirmed regressors and the whole calibration table above are unchanged. The
   remaining 4 are one `todo` instant where the runner never started, so no test
   name existed for anyone — `untraced`, a different absence and a separate
   decision.
2. **File overlap is the wrong predicate**, which is the substance of O3's own
   complaint, and the weight was never the lever. The predicate is nearly always
   true: **27 of 32** stories touch at least one neighbour — 15 of 15 regressors,
   but also 12 of 17 clean ones. A signal that fires on 84% of stories cannot
   rank the 47% that regress, whatever it is multiplied by. Two recorded
   observations point at the fix: the ledger's requirement records carry no paths
   at all and are reached only through the owning story's *declared* write scope
   (todo-cli STORY-06-01 changed one file, a new integration test, overlapped
   nothing on declared scope or actual changed files, and still saw five
   requirements of three other stories change status during its run), and that
   declared scope is a plan artifact that need not match what the story changed.
   Scope preservation by behaviour — re-verify the neighbour's criteria at the
   candidate — rather than by a bigger number.

## New test names

In `tests/test_story_size.py::TestComponents`:

- `test_lang_gieng_doc_tu_bang_chung_khong_tu_ledger_json_cu`
  — RED before the fix (`AssertionError: Lists differ: [] != ['AC-STORY-01-04-1']`),
  GREEN after.
- `test_trong_so_lang_gieng_la_nut_cau_hinh`
  — RED before (`TypeError: score_story() got an unexpected keyword argument
  'config'`), GREEN after.
- `test_ledger_json_van_dung_khi_chua_co_bang_chung`
  — guard: a hand-written/legacy `ledger.json` with no evidence must still count.
  Green before and after; it is what stops the fix from throwing the file away.

In `tests/test_config.py::TestValidation`:

- `test_trong_so_lang_gieng_khong_duoc_am`
  — RED before the range check (`AssertionError: ConfigError not raised`), GREEN
  after. A negative weight would make the size gate *more* permissive the wider
  the blast radius.
- `test_trong_so_lang_gieng_nhan_gia_tri_duong`
  — a project may raise the knob; 2.5 loads.

## Paragraph for CHANGELOG.md

> **O3 closed — the preservation radius weight is calibrated, not pinned.**
> `story.verified_touched_weight` is now a config knob (default `0.0`) with its
> calibration table beside it in `aisef/config.py`, and
> `validation/o3_preservation_radius.py` regenerates that table from recorded
> dogfood evidence. Over 32 stories from four corpora — 15 of which really did
> break a VERIFIED behaviour of another story, confirmed by the gate's own
> `preservation` verdict or by a REOPENED entry backed by a named red test — no
> weight at or below 1.0 changes a single verdict, the first verdict a larger
> weight changes is a false block, and catching 11 of the 15 regressors would
> cost blocking 7 of the 17 clean stories (Spearman 0.235). Calibrating it
> required fixing the input first: `complexity.read_ledger` read `ledger.json`,
> refreshed only at the end of a sprint, so 24 of those 32 stories — and 12 of
> the 15 regressors — had been scored against fewer neighbours than the evidence
> projection held; it now reads the same projection the preservation gate reads.
> The measurement also says the weight was never the lever: file overlap is true
> for 27 of the 32 stories — 15 of 15 regressors but also 12 of 17 clean ones —
> and a signal that fires on 84% of stories cannot rank the 47% that regress,
> whatever it is multiplied by. Scoping preservation by behaviour rather than by
> file is work for the next iteration, not for a bigger number.
