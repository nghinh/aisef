# O1 — reviewer qualification: what changed, what it measures, what it says

ADR-009 `## Open` issue **O1** ("the reviewer's verdicts are not themselves
qualified") is closed. This is the handoff note: the code, the measurements, the
new test names, and a paragraph for `CHANGELOG.md`.

No model call was made. The corpus is 145 reviewer sessions already recorded on
disk plus the four project git repos; every number below is recomputable.

## What changed

| file | change |
|---|---|
| `aisef/control/reviewer_qual.py` | **new.** Scores every recorded reviewer session into one of six classes and reports false-block rate, miss rate, and a convention-free test–retest number. `python3 -m aisef.control.reviewer_qual <_bmad-output>…` prints the markdown. |
| `tests/test_reviewer_qualification.py` | **new.** Six classes × three controls (`positive` / `negative` / `env`), plus the extraction test (reads sessions from `evidence/*.jsonl`), the git test (`changed_between` over a real throwaway repo), and the meta tests. |
| `aisef/control/gate.py` | `qualification_table()`'s AST walk extracted to `controls_in(path, names)` so the reviewer table is read by the **same** reader as the gate table — two tables cannot drift into two meanings of "has a control". No behaviour change to the gate table. |
| `docs/ADR-009-phase-3-cross-tier-invariants.md` | O1 marked CLOSED with the measurement, the method, the residual ambiguity, and one correction to §1's claim about `Finding.id`. The edit is confined to the `### O1` block plus a three-line status note above it, in case another agent is editing O2–O4 in the same file. |

The six classes: `clean pass`, `miss`, `block corroborated`,
`block uncorroborated`, `false block`, `undecided`. `undecided` is a class, not
a default — a session the evidence cannot score is never counted as a pass in
either direction.

**Deliberately not done:** the table is not wired into `aisef report`. One line
next to the existing `**Story Gate:** gate checks with all 3 controls: n/N`
(`aisef/phases/report.py:157`) would surface it, using
`reviewer_qual.qualification_table()` exactly as that line uses the gate's. Left
out because `report.py` is a shared file and the parallel O2/O4 work lands
there; add it when those have merged.

## The measurement (2026-09-14)

Corpus: `todo-cli` (37 sessions), `todo-e2e` (28), `todo-oc` (24), `todo` (56)
= **145** `tool_run review` events in `_bmad-output/evidence/*.jsonl`,
2026-09-08 → 2026-09-13, every one a real client session (`ses_…`). The 146
files under `reviews/` are the *smaller* corpus: only 71 are reviewer reports
(the other 75 are security reports, retries included), and a re-run overwrites
the file while the evidence log keeps every session.

| class | todo-cli | todo-e2e | todo-oc | todo | all |
|---|---|---|---|---|---|
| clean pass | 15 | 9 | 12 | 7 | 43 |
| miss | 9 | 1 | 6 | 11 | **27** |
| block corroborated | 13 | 2 | 6 | 9 | 30 |
| block uncorroborated | 0 | 15 | 0 | 6 | **21** |
| false block | 0 | 0 | 0 | 6 | **6** |
| undecided | 0 | 1 | 0 | 17 | 18 |

- **false-block rate 10.5 %** (6 of 57 scored blocks) — a **floor**, see below.
- **miss rate 38.6 %** (27 of 70 scored passes); 34.3 % under the strictest
  reading (see below), so the honest statement is **34–39 %**.
- **undecided 12.4 %** (18 of 145): 16 harness-authored "no changes to review"
  lines that never had a model session, 1 `review:immutable`, 1
  `review:candidate`. Cross-checked two ways: the classifier finds 16 rows with
  no `agent_run …-review` in their window, and grepping the recorded findings
  for the literal "no changes to review" string finds the same 16.
- **test–retest: 11 of 20** consecutive pairs at an identical tree reversed the
  verdict — 6 `block → pass`, 5 `pass → block`. On identical bytes the judge
  contradicts itself more often than it repeats itself. This number depends on
  no convention at all; the two rates above do, because attributing the error
  to the *earlier* half of a reversed pair is a choice (stated in the module).
- **21 of 57 blocks (36.8 %) rest on the reviewer's word alone** — `review` was
  the only failing check that says anything about the candidate. In `todo-e2e`
  that is 15 of its 17 blocks: in that project the judge *is* the gate.
- Direction: 27 misses to 6 false blocks, ≈ 4.5 : 1. C11's single observation
  ("cổng máy bắt, người máy không") is the common direction, not the exception.

### Sample rows (quoted, not summarised)

False block — `todo/STORY-02-01`, candidate `d8ba1b2`, two sessions, identical
tree (`git diff d8ba1b2..d8ba1b2` empty):

- seq 48, `ses_f7aec40ee`, verdict **block**: `[block] tests/todo-list.spec.js:423
  — The AC-4 test does not verify immediate display because Playwright's
  toBeVisible auto-waits…`
- seq 59, `ses_f7aeab2fa`, verdict **pass**, filing only `should fix` items —
  one of them on the same file (`tests/todo-list.spec.js:381`).

Miss — `todo/STORY-01-02#1` seq 325, candidate `dd88027`: reviewer verdict
`pass`; the gate at the same attempt: `test` = *"the most recent test run is
still failing, the story cannot be finished"* and `preservation` =
*"regression: qa:accessibility, qa:e2e"*.

Miss (nop control, 20 of the 27) — `todo-cli/STORY-03-02#1` seq 46, candidate
`67e4ff5`: reviewer `pass`; `tests verify story` = *"tests verify nothing — still
green without story code (parent SHA a25a56d): AC-STORY-03-02-1: list --done
prints only done tasks, …"*. That is the reviewer's own review item 2 ("a test
that is always green regardless of code correctness").

## How ground truth is derived, and what stays ambiguous

**False block** needs positive evidence of reversal, read from the project's
**git repo**:

1. the next scorable session passed on an identical tree — the same candidate
   commit, or two commits `git diff` finds no difference between (for the same
   SHA the comparison is a string equality, not a `git` call; the printed reason
   says which), or
2. the next scorable session passed while `git diff` between the two candidates
   never touches any file the blocking findings named — and no changed file is
   named in their bodies either.

All six measured false blocks are of kind 1 and all six are the *same commit*:
a second reviewer session re-read the exact build the first one blocked and
passed it.

Both need a next session and two resolvable commits, so 10.5 % is a floor
(56 of 57 blocks were testable here; rule 2 contributed 0 rows after the body
check, so every measured false block is a same-tree reversal, and all six are
in `todo`, the only project that re-reviewed identical trees).

**Measured wrong first, corrected:** an earlier pass trusted `file_change`
events for "was there a code change" and reported **16** false blocks (28 %).
`todo-e2e/STORY-02-02` killed that: between the gate of attempt 1 and the review
of attempt 2 there is not one `file_change` event, yet
`git diff 4d4b99e face091` = `js/app.js`, `tests/todo.spec.js` — the file the
block named. Hook coverage is not code history; the module now reads git and
says so in its docstring.

**Miss** needs a check that says the *candidate* is defective:

- `FAILED` only. `UNRUNNABLE` also blocks the gate (`Outcome.blocks`) but says
  "could not run"; scoring "whatever blocked the gate" instead put **6** extra
  rows into `miss` (mostly `preservation` unrunnables — the corpus has 8 of
  those in total).
- not the `FAILED` reasons that are themselves evidence gaps: 17 of 44
  `tests verify story` failures say *"no test run at candidate"* or *"nothing to
  verify at parent SHA"*, and 2 of 3 `test` failures on a reviewer pass say
  *"files changed since the most recent test run"*. Counting those inflates the
  miss rate from 38.6 % to **48.6 %** (`NOT_A_DEFECT` in the module).
- only checks inside the reviewer's contract, taken from its own prompt
  (`kit/prompts/story-review.md`): `test`, `real tests`, `tests verify story`,
  `preservation`. `criteria have tests` is excluded because the prompt forbids
  re-counting it; `lint`, `TDD`, `no baseline regression`, `security` are never
  asked of it. Failures outside the contract are printed, not charged.
- `guard ran` and `evidence matches candidate` do not *corroborate* a block
  either (`PLUMBING`): they say the harness misfired, not that the code is bad.
  Three blocks moved from corroborated to uncorroborated once that was fixed.

**Residual ambiguity, stated plainly.**

1. Attribution in a reversed pair is a convention: the pipeline acted on the
   later verdict, so the earlier one is scored wrong. The pair only *proves*
   inconsistency. Reported both ways: the classes use the convention, the
   test–retest count does not.
2. All six same-tree reversals come from re-runs of one project. The rate is
   a floor everywhere else because the experiment (ask twice about identical
   bytes) only happened there.
3. Three of the five preservation misses fail only on a *screen* comparison
   (`mockup:*`) that a read-only reviewer cannot run itself — `todo-oc/STORY-04-01`
   seq 1933, `todo/STORY-01-02` seq 100 and 124. Dropping them gives
   24/70 = 34.3 %.
4. `block uncorroborated` (21 rows) is not "correct" — it is unfalsifiable from
   recorded evidence. Nothing on disk can settle those.
5. **Which client judged is not on disk.** `agent_run.detail` records
   `model: ""` and no client name, and `todo-oc` carries both a
   `.claude/settings.json` and a `.opencode/plugin`, so at least one project may
   mix clients. Tool-name casing does not discriminate either — guard events are
   lowercase in all four projects. The rates are therefore across clients. One
   cheap harness fix would settle it for the next pass: record client and model
   on `agent_run`.

   **The harness fix landed 2026-09-14** (`0957ddb`), and the two halves of what
   that does and does not buy have to be read together.

   *Recorded now.* `observe.py` writes both onto the event, and the scorer splits
   on them:

   ```
   grep -n '"model":\|"client": client' aisef/harness/observe.py
   # → "model": (getattr(result, "model", "") or model),
   # → "client": client,
   grep -n 'client/model' aisef/control/reviewer_qual.py
   # → Reviewer.engine is f"{client or '?'}/{model or '?'}"; report() emits a
   #   per-engine table only when the corpus holds more than one, and otherwise
   #   prints "Toàn corpus mang một `client/model`" instead of a column of `?/?`
   ```

   *Still not recorded.* The 145-session corpus this section measured carries
   neither field, and nothing writes them retroactively. **Every rate in § The
   measurement stays "across clients"** — the fix is forward-looking only, and
   the report's own single-engine branch will say `?/?` on that corpus rather
   than pretend it split. Re-measuring per client costs paid runs, not a
   recompute; until someone pays for them, the false-block and miss rates above
   are properties of the *ensemble* of whatever clients produced those four
   corpora.
6. `Finding.id` collapses only verbatim restatements (see the §1 correction
   below), so "355 findings declared" is a lower bound on restatement, and the
   174 lines the gate acted on were parsed by whichever harness version ran
   that day (pre-lỗi-141 text parsing inflated some counts; the scorer therefore
   scores the reviewer's **own JSON verdict**, not the merged text).

## Correction to ADR-009 §1

§1 claims a `Finding.id` is stable "regardless of how the agent rewrites the
wording". `findings._digest` hashes `body`, so re-wording changes the id. The
place-key `implement._finding_key` (tag + file + line) is what collapses
re-wordings and what fixed lỗi 141. Noted in the closed O1 section; the code
was not changed — making `id` wording-insensitive would need a decision about
what "the same defect" means, which is a separate question from O1.

## New test names

`tests/test_reviewer_qualification.py`

- `TestCleanPass::test_positive_cong_dong_y` / `test_negative_cong_truot_muc_trong_hop_dong` / `test_env_khong_co_gate_verdict_thi_khong_phai_pass_sach`
- `TestMiss::test_positive_pass_ung_vien_ma_nop_control_bat` / `test_negative_muc_truot_vi_thieu_bang_chung_khong_phai_sot` / `test_env_khong_kiem_duoc_thi_khong_phai_sot`
- `TestBlockCorroborated::test_positive_tang_may_cung_truot` / `test_negative_chi_review_truot_thi_khong_co_ai_xac_nhan` / `test_env_muc_duong_ong_truot_khong_xac_nhan_duoc_gi`
- `TestBlockUncorroborated::test_positive_mot_minh_review_chan_va_khong_gi_dao_lai` / `test_negative_co_tang_may_dong_y_thi_thanh_corroborated` / `test_env_phien_sau_pass_tren_cung_cay_thi_la_false_block`
- `TestFalseBlock::test_positive_dao_chieu_tren_cung_mot_cay` / `test_negative_tac_gia_da_sua_dung_tep_do_thi_khong_phai_chan_oan` / `test_negative_than_muc_ke_ten_tep_da_sua` / `test_env_hai_ung_vien_khong_phan_giai_duoc_thi_khong_ket_luan`
- `TestUndecided::test_positive_dong_do_harness_tu_sinh_khong_phai_phan_quyet` / `test_negative_phien_that_co_json_va_co_cong_thi_cham_duoc` / `test_env_phien_bi_huy_hay_khong_co_json_deu_co_ten`
- `TestDocSoLieu::test_hai_ti_le_deu_co_va_khong_chia_cho_khong`, `test_id_on_dinh_gop_loi_nhac_lai_mot_lan`
- `TestDocPhienTuDia::test_moi_phien_mot_hang_va_dong_harness_khong_co_phien`, `test_phien_bi_huy_duoc_ghi_nhan`
- `TestGitLaNguonSuThat::test_doc_dung_tep_da_doi_va_cung_cay_la_rong`, `test_khong_phan_giai_duoc_thi_None_khong_phai_rong`
- `TestBangChungNhan::test_moi_lop_co_du_ba_control`, `test_ten_TEN_trong_tep_nay_thuoc_CLASSES`, `test_classify_chi_tra_ten_trong_CLASSES`

### RED before GREEN

The work is additive, so the RED runs are mutations of the scorer showing each
control is load-bearing rather than decorative. Each mutation was applied to
`aisef/control/reviewer_qual.py`, the suite run, then the file restored:

| mutation | RED |
|---|---|
| `NOT_A_DEFECT = ()` | `TestMiss::test_negative_muc_truot_vi_thieu_bang_chung_khong_phai_sot` — `- miss / + clean pass` |
| `PLUMBING = ()` | `TestBlockCorroborated::test_env_muc_duong_ong_truot_khong_xac_nhan_duoc_gi` — `+ block uncorroborated` |
| false-block rule drops `and not set(noi) & set(r.changed_next) and not ke_ten` | `TestFalseBlock::test_negative_tac_gia_da_sua_dung_tep_do_thi_khong_phai_chan_oan` **and** `test_negative_than_muc_ke_ten_tep_da_sua` — `- false block / + block uncorroborated` |

Two more RED→GREEN pairs happened for real, not by mutation:

1. `tests/test_meta.py::TestKhongDocDauRaBangBangMaCuaMay::test_moi_lan_goi_tien_trinh_con_deu_khai_bang_ma`
   went RED on the first full-suite run — the new git helper in the test file
   called `subprocess.run(..., text=True)` without `encoding="utf-8"`, the
   cp1252-on-Windows hole from lỗi 99. Fixed in the helper (the gate was not
   touched); GREEN after.
2. One control was RED against the *first* version of the scorer and drove a
   real fix — `TestMiss::test_env_khong_kiem_duoc_thi_khong_phai_sot` failed
   with `AssertionError: 'unrunnable' not found in 'gate agreed'`: a
   `clean pass` was being reported without saying that an in-contract check had
   not concluded. `_one()` now names those checks in the reason, which is the
   same rule `Outcome.must_be_named` enforces one layer down.

Final state: `ruff check .` clean; full `python3 -m pytest -q` →
`2550 passed, 80 skipped, 1040 subtests passed` (the run before the encoding
fix was `1 failed, 2549 passed`).

## Paragraph for CHANGELOG.md

> **Reviewer qualification (ADR-009 O1).** The `review` check — the only
> `model-judge` check in the gate — now has the same three controls
> (positive / negative / env) as the machine checks, applied to the *judgement*
> rather than to the check: `aisef/control/reviewer_qual.py` scores every
> reviewer session recorded in `_bmad-output/evidence/*.jsonl` into six classes
> and reports both error rates, with `tests/test_reviewer_qualification.py`
> holding 3 × 6 controls read by the same AST reader as the gate table
> (`gate.controls_in`). Measured over 145 recorded sessions from the four
> dogfood projects: **false-block rate 10.5 %** (6/57 blocks, a floor — it needs
> a later session and two resolvable commits to see a reversal), **miss rate
> 38.6 %** (27/70 passes; 34.3 % under the strictest reading of the reviewer's
> contract), **12.4 % undecided** (never scored as a pass), and — the number
> that needs no convention — of 20 consecutive session pairs where `git diff`
> between the candidates is empty, **11 changed verdict** on identical bytes.
> 21 of 57 blocks rest on the judge's word alone with nothing on disk able to
> settle them. Direction confirms conformance probe C11 and quantifies it: the
> reviewer passes defective candidates about 4.5× more often than it blocks
> sound ones. Recompute with
> `python3 -m aisef.control.reviewer_qual <_bmad-output>…` — no model call.
