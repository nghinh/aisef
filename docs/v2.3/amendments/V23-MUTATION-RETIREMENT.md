# V23-MUTATION-RETIREMENT — scoped amendment — 2026-11-27

**Owner ruling 2026-11-27 "V23 Mutation Retirement and CI Closure", §1–3: CONDITIONAL GO.**

## 1. What this amendment does

C-1 §3 (CORE-2, commit `b939506c`) consolidated three historical projection symbols — each a data table read by an
if-chain — verbatim into the single lifecycle transition table `aisef2/journal/transitions.py`. This amendment
introduces a **separate, v2.3-era retirement mapping** in `validation/v2/mutation.py` so the mutation gate reads those
three gone symbols as retired provenance (not as "target changed — re-run it") while their successors keep every
measurement obligation.

| retired symbol (source identity) | successor (registered target) | migration evidence |
|---|---|---|
| `aisef2/journal/projections/story_state.py::_OUTCOMES` | `aisef2/journal/transitions.py::STORY` | `transitions.py` docstring §3, `TABLE_DIGEST` pin |
| `aisef2/journal/projections/story_state.py::_WITHIN` | `aisef2/journal/transitions.py::WITHIN` | same |
| `aisef2/journal/projections/terminal_state.py::_RUN` | `aisef2/journal/transitions.py::RUN` | same (lifted verbatim, `transitions.py` §14) |

`symbol_of` is an **additional new authority**, not a retired-symbol replacement, and is NOT in the mapping.

## 2. Retirement rationale

Each retired symbol is **provably absent** from the current source (`mutation._root` resolves it to `None`), **present
in its historical record** (`closure-evidence/v2/P3-MUTATION.json`, untouched), and **mapped to a registered successor**
that is a surface of the approved transition-table migration. The migration's mutation coverage *grew*
(STORY 102 + WITHIN 25 + RUN 44 + symbol_of 23 mutants vs the retired _OUTCOMES 18 + _WITHIN 7 + _RUN 46) and the table
is kill-linked to its `TABLE_DIGEST` pin (`tests/v2/test_v23_transitions.py`). The independent adversarial review of the
LANE-A migration (commit `4b13b672`) found no coverage weakening.

## 3. Strict boundaries (owner §1–3), preserved

- **No qualification bypass.** Retirement only stops demanding a *fresh measurement of a symbol that no longer exists*.
  It grants the successor **nothing**: `STORY`, `WITHIN`, `RUN`, `symbol_of` each retain their own measurement
  obligation and remain visible in `mutation.check()` as `"has no mutation result"`.
- **The 100 pre-existing stale targets stay visible.** The blocker count is not silently reduced (see §5).
- **Enforced by the qualification path, not merely callable.** The integrity checks ride `mutation.check()`, which is the
  calibrated `mutation` checker's `clean()` (`validation/v2/checker_calibration.py::_mutation`) that
  `validation/v23/q0_round.py::problems` evaluates for Q0 — so a resurrected/invalid/provenance-less mapping turns the
  Q0 mutation checker red, and a retired target can never qualify an unmeasured successor (the four successors stay red
  there). Proven by `V23Retirement::test_the_integrity_control_is_enforced_by_the_mutation_qualification_path`.
- **Narrow to the v2.3 era.** `superseded()` interprets the mapping under phase `P3` only; the frozen v2.1/v2.2 replay
  records never hold these symbols. `V21_RETIRED`, `SUPERSEDED`, `PHASE_TARGETS` and the legacy supersession tables are
  **unchanged**.
- **No frozen evidence altered.** `closure-evidence/v2/P3-MUTATION.json` and every released record are byte-for-byte
  unchanged; survivor audits are untouched.
- **Fail-closed.** A resurrected symbol, a missing/invalid successor, or missing historical provenance each refuses the
  retirement (`mutation.v23_retirement_problems`), proven by the negative controls in
  `tests/v2/p2/test_mutation_targets.py::V23Retirement`.

## 4. Controls (owner §2)

Positive: the live mapping is exactly the three, valid, and all three are absent from source; each retired symbol is
dropped from re-check while its successor keeps its obligation. Negative (fail-closed), one test each:
**missing successor**, **invalid mapping**, **resurrected legacy symbol**, **missing historical provenance**,
**unmeasured successor stays a blocker (and unrelated stale targets are not hidden)**, **narrow to the v2.3 era
(v2.1/v2.2 replay never interpreted; `V21_RETIRED` unchanged)**, and **the integrity control is enforced by the
mutation qualification path** (the calibrated `mutation` checker goes red on a broken mapping).

## 5. Before / after `mutation.check()` (owner §2 — exact findings, not only unit tests)

- **Before:** 107 problems, including three `"… ::_OUTCOMES/_WITHIN/_RUN: target changed since the mutation run —
  re-run it"` lines (a gone symbol cannot be re-run).
- **After:** 104 problems. The only change is the removal of those three lines. **Added: none.**
- **Unchanged and still visible:** the four successor obligations
  (`transitions.py::{STORY,WITHIN,RUN,symbol_of} has no mutation result`) and all **100** pre-existing stale targets
  — measured breakdown: 33 `old_path_audit.py` + 25 `app/run.py` + 19 `journal/format3.py` + 11 `orchestrate/story_runner.py`
  + 9 `journal/event.py` + 2 `projections/terminal_state.py` + 1 `projections/story_state.py`
  (e.g. `validation/v2/old_path_audit.py::check: target changed …`). The mutation gate remains a **standing blocker**.
  (The earlier "68" figure was a pre-CORE-2 count at `68c247d2`; the current tree's measured figure is 100 — the
  later v2.3 commits staled targets in `format3.py`, `event.py` and the projections.)

## 6. Verification

Unit + negative controls green (`tests/v2/p2/test_mutation_targets.py`, 15 tests); run again under `AISEF_SEALING=1`;
v2.2 historical replay unaffected (the change is narrow to phase `P3`). Independent adversarial review of the final diff
obtained before integration. No production tag, master merge, PyPI publication, mass remeasurement or full RC campaign.
