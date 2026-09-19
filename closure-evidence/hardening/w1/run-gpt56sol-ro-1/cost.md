# Spend attribution — `w1-run-gpt56sol-ro-1`

Unit: **input tokens** — the provider priced 0% of 34 sessions (0.00 USD recorded in total), so dollars here would be invented. With `p` = price per 1M input tokens and `q` = per 1M output:

    cost ≈ 13.65 × p + 0.160 × q

Cache reads are 44% of prompt tokens (10,565,888 cached vs 13,652,407 fresh); most price lists charge them far less, so they are counted separately.

Net VERIFIED per M input tokens: **1.25**

17 verified · 5 gap · 0 reopened → net **17** behaviours for 13,652,407 across 34 sessions (332 turns).

## Where the spend went

| class | sessions | turns | tokens | share |
|---|---|---|---|---|
| passed | 6 | 71 | 515,963 | 4% |
| gate-blocked | 7 | 107 | 586,301 | 4% |
| env-failed | 9 | 6 | 40,184 | 0% |
| planning | 12 | 148 | 12,509,959 | 92% |

Spend on stories that ended with a net VERIFIED behaviour: **8%**.

## Per story

Ledger columns **overlap** between stories (one FR can be covered by two), so they do not sum to the corpus counts above.

| story | attempts | tokens | share | passed | gate-blocked | turn-cap | env-failed | no-verdict | verified | gap | reopened | net |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| plan-epics | 0 | 5,687,131 | 42% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-architecture | 0 | 1,344,422 | 10% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-apply | 0 | 1,142,062 | 8% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-project-context | 0 | 960,795 | 7% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-01-01 | 3 | 766,237 | 6% | 279,674 | 486,563 | — | — | — | 10 | 0 | 0 | 10 |
| plan-ux | 0 | 675,905 | 5% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-prd | 0 | 642,950 | 5% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-help-version | 0 | 634,922 | 5% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-snapshot | 0 | 553,491 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-verify | 0 | 500,041 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-repair-tail | 0 | 368,240 | 3% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-01-02 | 1 | 236,289 | 2% | 236,289 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-01-03 | 3 | 139,922 | 1% | — | 99,738 | — | 40,184 | — | 1 | 5 | 0 | 1 |
| STORY-01-05 | 0 | 0 | 0% | — | — | — | — | — | 2 | 0 | 0 | 2 |
| STORY-05-01 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |
| STORY-05-02 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |
| STORY-05-03 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |

## What the gate blocked on

| check | blocks |
|---|---|
| review | 5 |
| security | 3 |
| TDD | 1 |
| tests verify story | 1 |

## By role

| role | sessions | turns | tokens | share |
|---|---|---|---|---|
| ? | 12 | 148 | 12,509,959 | 92% |
| developer | 8 | 129 | 589,123 | 4% |
| review | 7 | 37 | 344,237 | 3% |
| security | 7 | 18 | 209,088 | 2% |
