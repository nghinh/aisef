# O4 — spend attributed to outcomes

Closes ADR-009 §Open **O4** ("spend is attributed to calls, not to outcomes").
Cost of this work: $0 — reading evidence already on disk, no model call.

---

## 1. What changed

| # | Change | File |
|---|---|---|
| 1 | New projection joining spend to the behaviour ledger | `aisef/control/attribution.py` (new, 387 lines) |
| 2 | `aisef cost [--out FILE]` — prints the attribution as Markdown | `aisef/cli/implement.py` (`cmd_cost`), `aisef/cli/parser.py` |
| 3 | Command documented (a meta test enforces this) | `docs/SOLUTION.md` §10 |
| 4 | O4 marked closed with its two corrections | `docs/ADR-009-phase-3-cross-tier-invariants.md` |
| 5 | 17 regression tests | `tests/test_attribution.py` (new) |

`attribution.py` is a **projection** in the same sense as `ledger.py`: it stores
nothing, and every number is recomputable from `evidence/*.jsonl` plus the
ledger. Nothing was added to the evidence schema, no gate was touched, no
threshold was loosened.

### The prior decomposition was reused, not replaced

`docs/E4-COST-DECOMPOSITION.md` is sound and its method is reused: count
tokens when the provider prices nothing, print the `p`/`q` conversion formula
rather than inventing dollars, and assign a session to a gate verdict by
**event order** rather than by attempt number (a story run twice has two
"attempt 1"s; keying on the number labels the first run's sessions with the
second run's verdict).

Reused, and independently confirmed. Running the new code on `todo-e2e`
reproduces E4's gate-verdict table byte for byte:

| bucket | E4, `framework/bench/cost_decomp` | `aisef cost`, new code |
|---|---|---|
| gate blocked | 61 sessions · 10,176,854 in | 61 sessions · 10,176,854 in |
| gate passed | 27 sessions · 2,969,818 in | 27 sessions · 2,969,818 in |
| never reached the gate | 8 sessions · 2,061,987 in | 8 sessions · 2,061,987 in |

E4 stops there. O4 adds the other half of the question — what the ledger says
those tokens *bought* — and two things E4 could not see: the turn-cap class, and
the unit guard.

### Three decisions that are not cosmetic

**The unit is read off the evidence, never assumed.** `cost_usd` is a unit only
when the provider filled it in for *every* session. `todo` reports a dollar
figure for **1 of 180** sessions and `$0.00` for the other 179; the one paid
session is a `mockup` run, not story work. Dividing that $0.79 by 4 stories
gives $0.20/story, a number wrong by two orders of magnitude that reads like a
measurement. So `unit = usd` only at 100% coverage; otherwise tokens plus the
`p`/`q` formula.

**A session's own exit status outranks the gate verdict that follows it.**
Measured on `todo-oc`: `developer:max_turns | review:ok | security:ok |
GATE=BLOCK(...)` — the turn cap killed the developer session and the gate still
scored that attempt. Attributing by the verdict alone turns 13 `max_turns`
sessions into "the gate blocked this", and the cap — 32% of that corpus's
spend — appears in no table.

**Cache share, not a cache boolean.** `todo-oc` *does* report cache reads — on
4% of its prompt tokens, against 84% for `todo-cli`. A boolean "reports
caching" makes the two look alike while one bills every re-sent prompt as fresh
`input` and the other does not. `Attribution.cache_share` carries the ratio and
the report refuses comparability below 25%.

---

## 2. Corpora: `e9` and `par` are gone

```
$ ls -d /Users/nghinh/Downloads/projects/e9 /Users/nghinh/Downloads/projects/par
ls: /Users/nghinh/Downloads/projects/e9: No such file or directory
ls: /Users/nghinh/Downloads/projects/par: No such file or directory

$ find /Users/nghinh -maxdepth 4 -type d \( -name e9 -o -name par \)
/Users/nghinh/.dartServer/.analysis-driver/e9
/Users/nghinh/Library/Messages/Attachments/e9
/Users/nghinh/.npm/_cacache/index-v5/e9
```

Three cache directories, no project. `docs/E4-COST-DECOMPOSITION.md` already
recorded the loss in September ("cây bằng chứng của e9 **không còn**"). **The
36x is a historical claim I could not reproduce**, and no number below is
derived from it.

What *is* recoverable is where the 36x came from arithmetically, because both
means sit in prose on disk:

| corpus | prose record | total | stories | mean |
|---|---|---|---|---|
| `e9` | `docs/E4-COST-DECOMPOSITION.md` ("corpus 496 $") | $496 | 7 | $70.9/story |
| `par` | `docs/STATUS-2026-09-05.md:129` ("3/3 story, $5,79") | $5.79 | 3 | $1.93/story |

$70.9 ÷ $1.93 = **36.7x**. So the famous 36x is one project's total divided by
its story count, over another's — a ratio of two means, each over a
single-digit number of stories. Section 5 shows why that construction cannot
carry the weight put on it.

Four corpora with intact evidence were used instead: `todo`, `todo-cli`,
`todo-e2e`, `todo-oc` (plus `todo-e3`, a plan-only stub, as an edge case).

---

## 3. Measured: one row per corpus

Rebuild any row with `python3 -m aisef --project ~/Downloads/projects/<name> cost`.

**No corpus can be priced in dollars.** Unit is input tokens everywhere, and
the corpora are **not summed** — `todo-oc` at 4% cache share is not comparable
with the other three at 46-84%.

| corpus | cache | sessions | turns | input tokens | net VERIFIED | per Mtok | passed | gate-blocked | turn-cap | env-failed | no-verdict | planning | productive |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `todo` | 46% | 180 | 2,041 | 85.15M | 22 | 0.26 | **16%** | 44% | 0% | 37% | 0% | 3% | 25% |
| `todo-cli` | 84% | 165 | 1,653 | 17.80M | 29 | 1.63 | **4%** | 32% | 52% | 2% | 8% | 2% | 14% |
| `todo-e2e` | 75% | 96 | 961 | 15.21M | 6 | 0.39 | **20%** | 67% | 0% | 0% | 0% | 14% | 16% |
| `todo-oc` | 4% | 97 | 3,185 | 267.03M | 44 | 0.16 | **22%** | 46% | 32% | 0% | 0% | 0% | 100% |

- *net VERIFIED* = ledger `verified − reopened`, the same definition
  `Ledger.metrics()['loops'][].marginal` already used.
- *per Mtok* = net VERIFIED per million input tokens.
- *passed* … *planning* = share of input tokens by session class.
- *productive* = share of spend on stories that ended with net VERIFIED > 0.

### The number that matters most

**The fraction of spend that bought a passing attempt is 4% to 22%.**
Between **78% and 96%** of every corpus went to sessions no gate ever passed.

Where the rest went, largest first per corpus:

| corpus | biggest single sink | second |
|---|---|---|
| `todo` | gate-blocked rework 44% | environment failures 37% (8 sessions) |
| `todo-cli` | turn-cap exhaustion 52% (**3 sessions of 165**) | gate-blocked rework 32% |
| `todo-e2e` | gate-blocked rework 67% | planning 14% |
| `todo-oc` | gate-blocked rework 46% | turn-cap exhaustion 32% (13 sessions) |

This is not pure waste — a blocking gate is what holds quality, and E4 said so
first. But it is where the money goes, and it is now measured rather than
assumed.

---

## 4. The decomposition into named causes

Six causes, each with its own number. No residual bucket.

**1. Turn-cap exhaustion — the single largest sink where it occurs.**
`todo-cli`: **3 sessions out of 165** consumed 9.33M of 17.80M input tokens
(**52%**), 40 turns each — exactly the default `run.max_turns = 40`
(`aisef/config.py:91`; that project sets no override). `todo-oc`: 13 sessions,
86.30M of 267.03M (**32%**), 120 turns each, against its declared
`run.max_turns = 120`. The cap is being enforced, precisely, and it is still
where a third to a half of the money goes.

Absent in `todo` and `todo-e2e` — which is itself the finding rather than a
lucky result. Both declare `run.max_turns = 40` *and* ran the OpenCode client,
whose `compile-report.json` records `"turn_limit: unsupported"`; the only thing
that could stop a session was `run.timeout_seconds = 1800`. So their runaway
sessions land in `env-failed` as timeouts: `todo`'s 8 env-failed sessions
average ~35 turns and 4M input tokens each. E4 §3 diagnosed exactly this ("a
wall-clock cap is not a cost cap"); the adapter fix landed 13/09, and comparing
these two pairs of corpora is the readout that shows it working.

**2. Unverifiable stories — 71% to 84% of spend in three of four corpora.**
Stories that consumed real sessions and ended with net VERIFIED ≤ 0:

| corpus | such stories | their spend | share of corpus |
|---|---|---|---|
| `todo` | STORY-02-02 | 61.88M | **73%** |
| `todo-cli` | STORY-03-02, 04-02, 05-02, 06-01 | 14.90M | **84%** |
| `todo-e2e` | STORY-01-01, 01-02, 02-03, 03-01, 05-01 | 10.74M | **71%** |
| `todo-oc` | — | 0 | **0%** |

`todo` STORY-02-02 alone is 73% of its corpus and finished at net **−4**
(0 verified, 6 gap, 4 reopened). `todo-cli` STORY-06-01 finished at net **−5**.
`todo-oc` is the clean counter-example: 7 of 7 stories ended net-positive, so
100% of its spend is productive — the *rate* is poor (0.16/Mtok) but nothing
was spent on a story that bought nothing.

**3. Gate-blocked rework — 32% to 67%, concentrated in three checks.**
Every corpus. What the gate blocks on, counted:

| corpus | top blocking checks |
|---|---|
| `todo-cli` | TDD 16 · review 16 · tests verify story 16 · security 10 · criteria have tests 9 |
| `todo-oc` | tests verify story 10 · preservation 8 · review 8 · accessibility 5 |
| `todo-e2e` (E4) | review 18 · tests verify story 3 · criteria have tests 2 |

`review` and `tests verify story` are in the top three of all three. E4's
conclusion — work the review loop, not the prompt — holds on two more corpora.

**4. Environment failures — 0% to 37%.**
`todo`: 8 sessions (`timeout`, `error`) burned 31.68M tokens, **37%** of the
corpus, at ~35 turns each — these are 1800s timeouts that had already done a
lot of work before dying. `todo-cli`: 12 `infra` sessions but only 283k tokens
(**2%**), because they died early. Same class, two orders of magnitude apart in
cost: the count of infra failures says nothing about their cost, only the
tokens do.

**5. Review rounds — 11% to 27% of spend; retries are noise.**

| corpus | developer | review | security | review/security retries |
|---|---|---|---|---|
| `todo` | 65 s / 70.94M (83%) | 41 s / 9.56M | 39 s / 2.41M | 2 s / 0.04M (**0.05%**) |
| `todo-cli` | 72 s / 14.51M (82%) | 37 s / 2.31M | 37 s / 0.52M | 6 s / 0.02M (**0.1%**) |
| `todo-e2e` | 34 s / 10.47M (69%) | 27 s / 1.68M | 27 s / 1.00M | — |
| `todo-oc` | 39 s / 192.55M (72%) | 24 s / 69.22M | 24 s / 4.95M | — |

The developer role is 69-83% of spend everywhere. `review-retry` /
`security-retry` — the thing "retries?" in the brief points at — is **under
0.15% in every corpus**. Ruled out as a cost cause.

**6. Planning overhead — 2% to 14%.**
`plan-*` / `mockup-*` sessions: 2% (`todo-cli`), 3% (`todo`), 14%
(`todo-e2e`), 0.1% (`todo-oc`). Real spend, buys no story behaviour directly,
and too small to explain anything. Also ruled out.

### Ruled out, stated plainly

- **Review/security retry rounds**: < 0.15% of spend in all four corpora.
- **Planning phase**: ≤ 14%, and lowest in the most expensive corpus.
- **Security sessions**: 2-3% of spend everywhere despite being 24-39 sessions.
- **Session count**: `todo-oc` has 97 sessions and 15x the tokens of
  `todo-e2e`'s 96. Counting sessions, attempts, or stories predicts nothing.

---

## 5. What actually explains a 36x — the mean is the artifact

The 36x was built as *total ÷ story count*. On every corpus that survives,
that construction is dominated by one story:

| corpus | stories with sessions | median story | biggest story | max/median | biggest story's net VERIFIED |
|---|---|---|---|---|---|
| `todo` | 4 | 9.69M | 61.88M | **6x** | **−4** |
| `todo-cli` | 11 | 0.23M | 14.19M | **63x** | **0** |
| `todo-e2e` | 10 | 0.50M | 7.26M | **14x** | **0** |
| `todo-oc` | 7 | 33.81M | 75.61M | **2x** | 16 |

In `todo-cli` the most expensive story costs **63x the median** — and bought
nothing. The within-corpus spread of a single project is larger than the 36x
gap the ADR treats as a mystery between two projects. A 36x difference between
two per-story means, each over 3 and 7 stories, therefore needs no exotic
explanation: **one runaway story is sufficient**, and in the corpora that
survive, one runaway story is what happens.

The prose record for `e9` is consistent with this. `docs/STATUS-2026-09-05.md`
names, for that corpus: bug 12 — "story đốt $28 qua 4 lượt" (one story, four
attempts, one mockup-contract defect); bug 21 — "hai story liên tiếp (01-05 rồi
01-06, ≈ $30) mà lỗi nằm ở harness: đòi test rồi cấm viết test"; and
STORY-01-05 "tổng cộng ≈ $51" on its own out of $496. Both defects are fixed.
The two figures may overlap on STORY-01-05, so **they are not added here** — but
either alone is a double-digit percentage of `e9`'s $496, spent on named harness
defects rather than on product work.

**Conclusion.** The 36x is not a property of two projects; it is a property of
dividing by a story count when one story dominates. The replacement is the
table in section 3: rate (net VERIFIED per unit) plus the class split, both
per story, neither averaged.

---

## 6. Tests

`tests/test_attribution.py` — 17 tests, 6 classes. The two load-bearing ones:

| test | what breaks without it |
|---|---|
| `TestDonViChiTieu::test_gia_mot_phan_thi_khong_dung_do_la` | a corpus priced on 1 of 180 sessions is averaged into dollars |
| `TestDonViChiTieu::test_gia_du_moi_phien_thi_dung_do_la` | a fully-priced corpus is needlessly demoted to tokens |
| `TestDonViChiTieu::test_khong_co_cache_thi_bao_token_khong_so_sanh_duoc` | uncached token totals are silently compared with cached ones |
| `TestDonViChiTieu::test_co_cache_thi_dem_rieng` | the incomparability warning fires on a caching corpus |
| `TestDonViChiTieu::test_ti_le_cache_chu_khong_phai_co_hay_khong` | 4% cache reads read as "reports caching", like 84% |
| `TestPhienChetVi::test_tran_luot_khong_bi_tinh_vao_cong_chan` | 52% of `todo-cli` disappears into "gate-blocked" |
| `TestPhienChetVi::test_ha_tang_chet_la_mot_lop_rieng` | 37% of `todo` disappears into "gate-blocked" |
| `TestGanTheoThuTuSuKien::test_hai_luot_hai_phan_quyet` | a re-run story's blocked tokens count as bought |
| `TestGanTheoThuTuSuKien::test_phien_khong_ai_cham_la_no_verdict` | abandoned sessions vanish from the total |
| `TestGanTheoThuTuSuKien::test_phien_pha_lap_ke_hoach_xep_rieng` | planning spend is charged to a story outcome |
| `TestTienMuaDuocGi::test_net_verified_tru_reopened` | a behaviour that broke again still counts as bought |
| `TestTienMuaDuocGi::test_net_verified_moi_trieu_token` | the rate arithmetic |
| `TestTienMuaDuocGi::test_khong_tieu_gi_thi_khong_co_so` | a 0-denominator rate is printed as 0.00 instead of "—" |
| `TestTienMuaDuocGi::test_story_khong_mua_duoc_gi_nam_ngoai_phan_san_sinh` | `productive_share` |
| `TestTienMuaDuocGi::test_story_co_ke_hoach_nhung_chua_chay_van_co_dong` | a planned-never-run story vanishes |
| `TestLenhCost::test_in_bang_va_ghi_ra_tep` | `aisef cost --out` |
| `TestLenhCost::test_khong_co_bang_chung_van_thoat_0` | empty project exits non-zero |

### RED before, GREEN after

An import error is a weak RED, so the RED run was taken with the module
**present** and its two load-bearing decisions made the naive way — unit = USD
whenever any dollar is recorded, and the gate verdict claiming every preceding
session regardless of `exit_status`:

```
$ python3 -m pytest tests/test_attribution.py -q      # naive decisions
>       self.assertEqual(row.spend_of(A.TURN_CAP).input, 9000)
E       AssertionError: 0 != 9000
>       self.assertEqual(row.spend_of(A.ENV_FAILED).sessions, 3)
E       AssertionError: 0 != 3
FAILED tests/test_attribution.py::TestDonViChiTieu::test_gia_mot_phan_thi_khong_dung_do_la
FAILED tests/test_attribution.py::TestPhienChetVi::test_ha_tang_chet_la_mot_lop_rieng
FAILED tests/test_attribution.py::TestPhienChetVi::test_tran_luot_khong_bi_tinh_vao_cong_chan
3 failed, 13 passed in 0.27s
```

The three failures land exactly on the three decisions, not on the plumbing.
With the real implementation:

```
$ python3 -m pytest tests/test_attribution.py -q
17 passed in 0.20s
```

Whole suite and lint in this worktree:

```
$ ruff check .
All checks passed!

$ python3 -m pytest -q
2539 passed, 80 skipped, 1027 subtests passed in 273.11s (0:04:33)
```

---

## 7. Left open, deliberately

- **No dollar corpus exists to validate against.** The USD path is covered by
  unit tests only; the first fully-priced real run should be re-read with
  `aisef cost` to confirm.
- **`aisef cost` prints, it does not gate.** No budget threshold reads
  `per_unit()` yet. That belongs with the `aisef doctor` "set down" hook already
  in ADR-009 §Deferred, and wants a second priced corpus before a number is
  picked.
- **`CACHE_SHARE_COMPARABLE = 0.25` is a knob, not a law.** Measured values are
  4 / 46 / 75 / 84%; any cut between 10% and 40% separates the same corpora. The
  measurement is in the comment next to the constant.
- **Turn-cap spend is charged to the cap, not to the check the attempt would
  have failed.** That is the honest split — the session never reached the gate —
  but it means `gate-blocked` understates rework on corpora that hit the cap.
- **`framework/bench/cost_decomp` was not deleted.** It is bench tooling outside
  the shipped package (`pyproject.toml` ships `aisef*` only) and has its own
  tests. `aisef cost` supersedes it for anything shipped; retiring it is a
  separate decision.

---

## 8. Paragraph for CHANGELOG.md

> **`aisef cost` — net VERIFIED behaviour per unit of spend (ADR-009 O4).** A new
> read-only command attributes spend to outcomes: it joins the behaviour ledger
> to `evidence/*.jsonl` and reports, per story, the spend split across six
> session classes (passed · gate-blocked · turn-cap · env-failed · no-verdict ·
> planning) against the net VERIFIED behaviours it produced. The unit is decided
> by the evidence, not assumed: dollars only when the provider priced *every*
> session, otherwise input tokens plus the price formula — measured on four
> corpora, three price 0% of sessions and the fourth prices 1 of 180, so
> averaging that record into dollars would be wrong by two orders of magnitude.
> Token totals carry their cache share, because a client reporting 4% cache reads
> bills re-sent context as fresh input and cannot be compared with one reporting
> 84%. Measured across `todo`, `todo-cli`, `todo-e2e` and `todo-oc`: only **4-22%
> of spend bought an attempt the gate passed**; the largest sinks are turn-cap
> exhaustion (52% of `todo-cli` in 3 sessions of 165), gate-blocked rework
> (32-67%), and stories that end with no net VERIFIED behaviour (71-84% of spend
> in three of four corpora). Review/security retry rounds (<0.15%) and the
> planning phase (≤14%) were measured and ruled out. The `e9`/`par` corpora
> behind the "36x per story" claim are no longer on disk; that figure is
> arithmetic over two prose means ($496/7 ÷ $5.79/3) and is not reproducible —
> but the within-corpus spread of a single surviving project reaches **63x**
> between its most expensive story and its median, so one runaway story is a
> sufficient explanation for a 36x gap between two per-story means.
