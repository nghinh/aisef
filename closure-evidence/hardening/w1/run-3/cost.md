# Spend attribution — `w1-run-3`

Unit: **input tokens** — the provider priced 0% of 25 sessions (0.00 USD recorded in total), so dollars here would be invented. With `p` = price per 1M input tokens and `q` = per 1M output:

    cost ≈ 31.87 × p + 0.149 × q

Cache reads are 0% of prompt tokens (0 cached vs 31,868,689 fresh); most price lists charge them far less, so they are counted separately.

⚠ At 0% cache, this client bills re-sent context as fresh `input`: the totals below are a sum over turns of the whole prompt and are **not** comparable with a corpus that caches.

Net VERIFIED per M input tokens: **0.53**

17 verified · 5 gap · 0 reopened → net **17** behaviours for 31,868,689 across 25 sessions (435 turns).

## Where the spend went

| class | sessions | turns | tokens | share |
|---|---|---|---|---|
| passed | 5 | 80 | 5,335,419 | 17% |
| gate-blocked | 5 | 87 | 5,755,875 | 18% |
| turn-cap | 3 | 120 | 8,267,436 | 26% |
| planning | 12 | 148 | 12,509,959 | 39% |

Spend on stories that ended with a net VERIFIED behaviour: **61%**.

## Per story

Ledger columns **overlap** between stories (one FR can be covered by two), so they do not sum to the corpus counts above.

| story | attempts | tokens | share | passed | gate-blocked | turn-cap | env-failed | no-verdict | verified | gap | reopened | net |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| STORY-01-01 | 2 | 13,921,849 | 44% | 2,749,838 | 2,904,575 | 8,267,436 | — | — | 10 | 0 | 0 | 10 |
| plan-epics | 0 | 5,687,131 | 18% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-01-03 | 1 | 2,851,300 | 9% | — | 2,851,300 | — | — | — | 1 | 5 | 0 | 1 |
| STORY-01-02 | 1 | 2,585,581 | 8% | 2,585,581 | — | — | — | — | 7 | 0 | 0 | 7 |
| plan-architecture | 0 | 1,344,422 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-apply | 0 | 1,142,062 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-project-context | 0 | 960,795 | 3% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-ux | 0 | 675,905 | 2% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-prd | 0 | 642,950 | 2% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-help-version | 0 | 634,922 | 2% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-snapshot | 0 | 553,491 | 2% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-verify | 0 | 500,041 | 2% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-repair-tail | 0 | 368,240 | 1% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-01-05 | 0 | 0 | 0% | — | — | — | — | — | 2 | 0 | 0 | 2 |
| STORY-05-01 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |
| STORY-05-02 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |
| STORY-05-03 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |

## What the gate blocked on

| check | blocks |
|---|---|
| lint | 2 |
| criteria have tests | 1 |
| no baseline regression | 1 |
| preservation | 1 |
| review | 1 |
| test | 1 |
| tests verify story | 1 |

## By role

| role | sessions | turns | tokens | share |
|---|---|---|---|---|
| ? | 12 | 148 | 12,509,959 | 39% |
| developer | 5 | 155 | 10,495,299 | 33% |
| review | 4 | 110 | 7,498,353 | 24% |
| security | 4 | 22 | 1,365,078 | 4% |
