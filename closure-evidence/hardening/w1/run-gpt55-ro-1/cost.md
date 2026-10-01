# Spend attribution — `w1-run-gpt55-ro-1`

Unit: **input tokens** — the provider priced 0% of 51 sessions (0.00 USD recorded in total), so dollars here would be invented. With `p` = price per 1M input tokens and `q` = per 1M output:

    cost ≈ 14.88 × p + 0.221 × q

Cache reads are 61% of prompt tokens (22,880,768 cached vs 14,881,175 fresh); most price lists charge them far less, so they are counted separately.

Net VERIFIED per M input tokens: **3.49**

52 verified · 2 gap · 0 reopened → net **52** behaviours for 14,881,175 across 51 sessions (538 turns).

## Where the spend went

| class | sessions | turns | tokens | share |
|---|---|---|---|---|
| passed | 21 | 185 | 1,265,491 | 9% |
| gate-blocked | 15 | 190 | 1,019,367 | 7% |
| env-failed | 3 | 15 | 86,358 | 1% |
| planning | 12 | 148 | 12,509,959 | 84% |

Spend on stories that ended with a net VERIFIED behaviour: **16%**.

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
| STORY-01-05 | 3 | 561,935 | 4% | 207,099 | 354,836 | — | — | — | 8 | 0 | 0 | 8 |
| mockup-snapshot | 0 | 553,491 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-02-01 | 3 | 508,484 | 3% | 127,930 | 380,554 | — | — | — | 7 | 0 | 0 | 7 |
| mockup-verify | 0 | 500,041 | 3% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-01-01 | 2 | 412,170 | 3% | 128,193 | 283,977 | — | — | — | 10 | 0 | 0 | 10 |
| mockup-repair-tail | 0 | 368,240 | 2% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-01-06 | 1 | 257,069 | 2% | 257,069 | — | — | — | — | 8 | 0 | 0 | 8 |
| STORY-01-02 | 1 | 243,061 | 2% | 243,061 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-01-03 | 1 | 158,421 | 1% | 158,421 | — | — | — | — | 6 | 0 | 0 | 6 |
| STORY-01-04 | 1 | 143,718 | 1% | 143,718 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-02-02 | 0 | 86,358 | 1% | — | — | — | 86,358 | — | 3 | 2 | 0 | 3 |
| STORY-03-01 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |
| STORY-05-01 | 0 | 0 | 0% | — | — | — | — | — | 3 | 1 | 0 | 3 |
| STORY-05-02 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |
| STORY-05-03 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |

## What the gate blocked on

| check | blocks |
|---|---|
| review | 4 |
| TDD | 1 |
| tests verify story | 1 |

## By role

| role | sessions | turns | tokens | share |
|---|---|---|---|---|
| ? | 12 | 148 | 12,509,959 | 84% |
| developer | 15 | 312 | 1,602,061 | 11% |
| review | 12 | 50 | 423,006 | 3% |
| security | 12 | 28 | 346,149 | 2% |
