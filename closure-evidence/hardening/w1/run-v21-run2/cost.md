# Spend attribution — `w1-run-v21-run2`

Unit: **input tokens** — the provider priced 0% of 57 sessions (0.00 USD recorded in total), so dollars here would be invented. With `p` = price per 1M input tokens and `q` = per 1M output:

    cost ≈ 14.80 × p + 0.208 × q

Cache reads are 70% of prompt tokens (35,098,496 cached vs 14,797,597 fresh); most price lists charge them far less, so they are counted separately.

Net VERIFIED per M input tokens: **4.53**

67 verified · 8 gap · 0 reopened → net **67** behaviours for 14,797,597 across 57 sessions (600 turns).

## Where the spend went

| class | sessions | turns | tokens | share |
|---|---|---|---|---|
| passed | 30 | 291 | 1,584,890 | 11% |
| gate-blocked | 15 | 161 | 702,748 | 5% |
| planning | 12 | 148 | 12,509,959 | 85% |

Spend on stories that ended with a net VERIFIED behaviour: **15%**.

## Per story

Ledger columns **overlap** between stories (one FR can be covered by two), so they do not sum to the corpus counts above.

| story | attempts | tokens | share | passed | gate-blocked | turn-cap | env-failed | no-verdict | verified | gap | reopened | net |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| plan-epics | 0 | 5,687,131 | 38% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-architecture | 0 | 1,344,422 | 9% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-apply | 0 | 1,142,062 | 8% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-project-context | 0 | 960,795 | 6% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-ux | 0 | 675,905 | 5% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-prd | 0 | 642,950 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-help-version | 0 | 634,922 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-snapshot | 0 | 553,491 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-verify | 0 | 500,041 | 3% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-04-01 | 3 | 432,535 | 3% | — | 432,535 | — | — | — | 1 | 8 | 0 | 1 |
| STORY-03-01 | 3 | 388,281 | 3% | 118,068 | 270,213 | — | — | — | 7 | 0 | 0 | 7 |
| mockup-repair-tail | 0 | 368,240 | 2% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-03-02 | 1 | 204,081 | 1% | 204,081 | — | — | — | — | 5 | 0 | 0 | 5 |
| STORY-01-01 | 1 | 191,092 | 1% | 191,092 | — | — | — | — | 11 | 0 | 0 | 11 |
| STORY-01-05 | 1 | 190,325 | 1% | 190,325 | — | — | — | — | 8 | 0 | 0 | 8 |
| STORY-01-04 | 1 | 160,540 | 1% | 160,540 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-01-06 | 1 | 154,525 | 1% | 154,525 | — | — | — | — | 8 | 0 | 0 | 8 |
| STORY-02-02 | 1 | 153,720 | 1% | 153,720 | — | — | — | — | 6 | 0 | 0 | 6 |
| STORY-02-01 | 1 | 145,663 | 1% | 145,663 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-01-03 | 1 | 136,519 | 1% | 136,519 | — | — | — | — | 6 | 0 | 0 | 6 |
| STORY-01-02 | 1 | 130,357 | 1% | 130,357 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-04-02 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |
| STORY-04-03 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |
| STORY-05-01 | 0 | 0 | 0% | — | — | — | — | — | 6 | 0 | 0 | 6 |
| STORY-05-02 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |
| STORY-05-03 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |

## What the gate blocked on

| check | blocks |
|---|---|
| security | 5 |

## By role

| role | sessions | turns | tokens | share |
|---|---|---|---|---|
| ? | 12 | 148 | 12,509,959 | 85% |
| developer | 15 | 290 | 1,473,603 | 10% |
| review | 15 | 118 | 583,563 | 4% |
| security | 15 | 44 | 230,472 | 2% |
