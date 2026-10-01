# Spend attribution — `w1-run-deepseek-ro-2`

Unit: **input tokens** — the provider priced 0% of 50 sessions (0.00 USD recorded in total), so dollars here would be invented. With `p` = price per 1M input tokens and `q` = per 1M output:

    cost ≈ 15.01 × p + 0.202 × q

Cache reads are 70% of prompt tokens (35,259,392 cached vs 15,013,565 fresh); most price lists charge them far less, so they are counted separately.

Net VERIFIED per M input tokens: **4.66**

70 verified · 7 gap · 0 reopened → net **70** behaviours for 15,013,565 across 50 sessions (604 turns).

## Where the spend went

| class | sessions | turns | tokens | share |
|---|---|---|---|---|
| passed | 33 | 322 | 1,814,358 | 12% |
| gate-blocked | 3 | 44 | 214,005 | 1% |
| no-verdict | 2 | 90 | 475,243 | 3% |
| planning | 12 | 148 | 12,509,959 | 83% |

Spend on stories that ended with a net VERIFIED behaviour: **12%**.

## Per story

Ledger columns **overlap** between stories (one FR can be covered by two), so they do not sum to the corpus counts above.

| story | attempts | tokens | share | passed | gate-blocked | turn-cap | env-failed | no-verdict | verified | gap | reopened | net |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| plan-epics | 0 | 5,687,131 | 38% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-architecture | 0 | 1,344,422 | 9% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-apply | 0 | 1,142,062 | 8% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-project-context | 0 | 960,795 | 6% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-04-02 | 1 | 689,248 | 5% | — | 214,005 | — | — | 475,243 | 0 | 7 | 0 | 0 |
| plan-ux | 0 | 675,905 | 5% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-prd | 0 | 642,950 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-help-version | 0 | 634,922 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-snapshot | 0 | 553,491 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-verify | 0 | 500,041 | 3% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-repair-tail | 0 | 368,240 | 2% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-03-01 | 1 | 197,866 | 1% | 197,866 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-02-02 | 1 | 179,752 | 1% | 179,752 | — | — | — | — | 5 | 0 | 0 | 5 |
| STORY-01-05 | 1 | 173,317 | 1% | 173,317 | — | — | — | — | 8 | 0 | 0 | 8 |
| STORY-04-01 | 1 | 172,636 | 1% | 172,636 | — | — | — | — | 5 | 0 | 0 | 5 |
| STORY-01-01 | 1 | 168,021 | 1% | 168,021 | — | — | — | — | 10 | 0 | 0 | 10 |
| STORY-03-02 | 1 | 159,685 | 1% | 159,685 | — | — | — | — | 5 | 0 | 0 | 5 |
| STORY-01-02 | 1 | 156,851 | 1% | 156,851 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-01-04 | 1 | 156,286 | 1% | 156,286 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-02-01 | 1 | 155,489 | 1% | 155,489 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-01-06 | 1 | 151,099 | 1% | 151,099 | — | — | — | — | 8 | 0 | 0 | 8 |
| STORY-01-03 | 1 | 143,356 | 1% | 143,356 | — | — | — | — | 6 | 0 | 0 | 6 |
| STORY-04-03 | 0 | 0 | 0% | — | — | — | — | — | 0 | 1 | 0 | 0 |
| STORY-05-01 | 0 | 0 | 0% | — | — | — | — | — | 4 | 0 | 0 | 4 |
| STORY-05-02 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |
| STORY-05-03 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |

## What the gate blocked on

| check | blocks |
|---|---|
| TDD | 1 |
| tests verify story | 1 |

## By role

| role | sessions | turns | tokens | share |
|---|---|---|---|---|
| ? | 12 | 148 | 12,509,959 | 83% |
| developer | 14 | 335 | 1,850,501 | 12% |
| review | 12 | 88 | 489,774 | 3% |
| security | 12 | 33 | 163,331 | 1% |
