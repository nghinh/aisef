# Spend attribution — `w1-run-minimax-ro-2`

Unit: **input tokens** — the provider priced 0% of 42 sessions (0.00 USD recorded in total), so dollars here would be invented. With `p` = price per 1M input tokens and `q` = per 1M output:

    cost ≈ 76.81 × p + 0.315 × q

Cache reads are 0% of prompt tokens (0 cached vs 76,810,450 fresh); most price lists charge them far less, so they are counted separately.

⚠ At 0% cache, this client bills re-sent context as fresh `input`: the totals below are a sum over turns of the whole prompt and are **not** comparable with a corpus that caches.

Net VERIFIED per M input tokens: **0.64**

49 verified · 5 gap · 0 reopened → net **49** behaviours for 76,810,450 across 42 sessions (1,011 turns).

## Where the spend went

| class | sessions | turns | tokens | share |
|---|---|---|---|---|
| passed | 21 | 634 | 46,637,640 | 61% |
| gate-blocked | 8 | 149 | 10,763,588 | 14% |
| turn-cap | 1 | 80 | 6,899,263 | 9% |
| planning | 12 | 148 | 12,509,959 | 16% |

Spend on stories that ended with a net VERIFIED behaviour: **65%**.

## Per story

Ledger columns **overlap** between stories (one FR can be covered by two), so they do not sum to the corpus counts above.

| story | attempts | tokens | share | passed | gate-blocked | turn-cap | env-failed | no-verdict | verified | gap | reopened | net |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| STORY-02-02 | 2 | 14,163,083 | 18% | — | 7,263,820 | 6,899,263 | — | — | 0 | 5 | 0 | 0 |
| STORY-01-01 | 1 | 8,567,659 | 11% | 8,567,659 | — | — | — | — | 10 | 0 | 0 | 10 |
| STORY-01-04 | 2 | 8,416,304 | 11% | 4,916,536 | 3,499,768 | — | — | — | 7 | 0 | 0 | 7 |
| STORY-01-06 | 1 | 7,725,958 | 10% | 7,725,958 | — | — | — | — | 8 | 0 | 0 | 8 |
| STORY-01-05 | 1 | 6,902,537 | 9% | 6,902,537 | — | — | — | — | 8 | 0 | 0 | 8 |
| STORY-01-02 | 1 | 6,845,894 | 9% | 6,845,894 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-02-01 | 1 | 6,250,096 | 8% | 6,250,096 | — | — | — | — | 7 | 0 | 0 | 7 |
| plan-epics | 0 | 5,687,131 | 7% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-01-03 | 1 | 5,428,960 | 7% | 5,428,960 | — | — | — | — | 6 | 0 | 0 | 6 |
| plan-architecture | 0 | 1,344,422 | 2% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-apply | 0 | 1,142,062 | 1% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-project-context | 0 | 960,795 | 1% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-ux | 0 | 675,905 | 1% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-prd | 0 | 642,950 | 1% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-help-version | 0 | 634,922 | 1% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-snapshot | 0 | 553,491 | 1% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-verify | 0 | 500,041 | 1% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-repair-tail | 0 | 368,240 | 0% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-03-01 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |
| STORY-05-01 | 0 | 0 | 0% | — | — | — | — | — | 3 | 1 | 0 | 3 |
| STORY-05-02 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |
| STORY-05-03 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |

## What the gate blocked on

| check | blocks |
|---|---|
| review | 3 |
| criteria have tests | 1 |
| test | 1 |

## By role

| role | sessions | turns | tokens | share |
|---|---|---|---|---|
| developer | 10 | 503 | 38,689,475 | 50% |
| review | 10 | 303 | 21,910,405 | 29% |
| ? | 12 | 148 | 12,509,959 | 16% |
| security | 10 | 57 | 3,700,611 | 5% |
