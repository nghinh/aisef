# Spend attribution — `w1-run-deepseek-ro-1`

Unit: **input tokens** — the provider priced 0% of 58 sessions (0.00 USD recorded in total), so dollars here would be invented. With `p` = price per 1M input tokens and `q` = per 1M output:

    cost ≈ 15.21 × p + 0.218 × q

Cache reads are 74% of prompt tokens (43,323,904 cached vs 15,212,434 fresh); most price lists charge them far less, so they are counted separately.

Net VERIFIED per M input tokens: **4.60**

70 verified · 7 gap · 0 reopened → net **70** behaviours for 15,212,434 across 58 sessions (668 turns).

## Where the spend went

| class | sessions | turns | tokens | share |
|---|---|---|---|---|
| passed | 34 | 340 | 1,867,995 | 12% |
| gate-blocked | 11 | 100 | 506,742 | 3% |
| turn-cap | 1 | 80 | 327,738 | 2% |
| planning | 12 | 148 | 12,509,959 | 82% |

Spend on stories that ended with a net VERIFIED behaviour: **14%**.

## Per story

Ledger columns **overlap** between stories (one FR can be covered by two), so they do not sum to the corpus counts above.

| story | attempts | tokens | share | passed | gate-blocked | turn-cap | env-failed | no-verdict | verified | gap | reopened | net |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| plan-epics | 0 | 5,687,131 | 37% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-architecture | 0 | 1,344,422 | 9% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-apply | 0 | 1,142,062 | 8% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-project-context | 0 | 960,795 | 6% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-ux | 0 | 675,905 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-prd | 0 | 642,950 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-04-02 | 3 | 639,790 | 4% | — | 312,052 | 327,738 | — | — | 0 | 7 | 0 | 0 |
| mockup-help-version | 0 | 634,922 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-snapshot | 0 | 553,491 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-verify | 0 | 500,041 | 3% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-repair-tail | 0 | 368,240 | 2% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-04-01 | 2 | 295,723 | 2% | 101,033 | 194,690 | — | — | — | 5 | 0 | 0 | 5 |
| STORY-03-02 | 1 | 230,033 | 2% | 230,033 | — | — | — | — | 5 | 0 | 0 | 5 |
| STORY-03-01 | 1 | 213,099 | 1% | 213,099 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-02-02 | 1 | 195,900 | 1% | 195,900 | — | — | — | — | 5 | 0 | 0 | 5 |
| STORY-01-05 | 1 | 178,264 | 1% | 178,264 | — | — | — | — | 8 | 0 | 0 | 8 |
| STORY-01-06 | 1 | 174,836 | 1% | 174,836 | — | — | — | — | 8 | 0 | 0 | 8 |
| STORY-02-01 | 1 | 167,415 | 1% | 167,415 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-01-04 | 1 | 165,042 | 1% | 165,042 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-01-01 | 1 | 161,485 | 1% | 161,485 | — | — | — | — | 10 | 0 | 0 | 10 |
| STORY-01-02 | 1 | 144,540 | 1% | 144,540 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-01-03 | 1 | 136,348 | 1% | 136,348 | — | — | — | — | 6 | 0 | 0 | 6 |
| STORY-04-03 | 0 | 0 | 0% | — | — | — | — | — | 0 | 1 | 0 | 0 |
| STORY-05-01 | 0 | 0 | 0% | — | — | — | — | — | 4 | 0 | 0 | 4 |
| STORY-05-02 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |
| STORY-05-03 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |

## What the gate blocked on

| check | blocks |
|---|---|
| TDD | 2 |
| review | 2 |
| tests verify story | 2 |

## By role

| role | sessions | turns | tokens | share |
|---|---|---|---|---|
| ? | 12 | 148 | 12,509,959 | 82% |
| developer | 15 | 378 | 1,890,843 | 12% |
| review | 15 | 92 | 559,261 | 4% |
| security | 15 | 41 | 226,951 | 1% |
| review-retry | 1 | 9 | 25,420 | 0% |
