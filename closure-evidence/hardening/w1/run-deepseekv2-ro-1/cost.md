# Spend attribution — `w1-run-deepseekv2-ro-1`

Unit: **input tokens** — the provider priced 0% of 51 sessions (0.00 USD recorded in total), so dollars here would be invented. With `p` = price per 1M input tokens and `q` = per 1M output:

    cost ≈ 14.55 × p + 0.189 × q

Cache reads are 66% of prompt tokens (28,488,192 cached vs 14,551,485 fresh); most price lists charge them far less, so they are counted separately.

Net VERIFIED per M input tokens: **4.47**

65 verified · 9 gap · 0 reopened → net **65** behaviours for 14,551,485 across 51 sessions (511 turns).

## Where the spend went

| class | sessions | turns | tokens | share |
|---|---|---|---|---|
| passed | 30 | 275 | 1,561,978 | 11% |
| gate-blocked | 9 | 88 | 479,548 | 3% |
| planning | 12 | 148 | 12,509,959 | 86% |

Spend on stories that ended with a net VERIFIED behaviour: **13%**.

## Per story

Ledger columns **overlap** between stories (one FR can be covered by two), so they do not sum to the corpus counts above.

| story | attempts | tokens | share | passed | gate-blocked | turn-cap | env-failed | no-verdict | verified | gap | reopened | net |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| plan-epics | 0 | 5,687,131 | 39% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-architecture | 0 | 1,344,422 | 9% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-apply | 0 | 1,142,062 | 8% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-project-context | 0 | 960,795 | 7% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-ux | 0 | 675,905 | 5% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-prd | 0 | 642,950 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-help-version | 0 | 634,922 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-snapshot | 0 | 553,491 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-verify | 0 | 500,041 | 3% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-repair-tail | 0 | 368,240 | 3% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-03-02 | 3 | 351,230 | 2% | 83,045 | 268,185 | — | — | — | 5 | 0 | 0 | 5 |
| STORY-03-01 | 1 | 213,093 | 1% | 213,093 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-04-01 | 1 | 211,363 | 1% | — | 211,363 | — | — | — | 0 | 9 | 0 | 0 |
| STORY-01-01 | 1 | 187,325 | 1% | 187,325 | — | — | — | — | 9 | 0 | 0 | 9 |
| STORY-01-06 | 1 | 184,027 | 1% | 184,027 | — | — | — | — | 8 | 0 | 0 | 8 |
| STORY-01-05 | 1 | 172,532 | 1% | 172,532 | — | — | — | — | 8 | 0 | 0 | 8 |
| STORY-01-02 | 1 | 155,194 | 1% | 155,194 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-02-01 | 1 | 150,247 | 1% | 150,247 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-02-02 | 1 | 146,548 | 1% | 146,548 | — | — | — | — | 6 | 0 | 0 | 6 |
| STORY-01-03 | 1 | 144,099 | 1% | 144,099 | — | — | — | — | 6 | 0 | 0 | 6 |
| STORY-01-04 | 1 | 125,868 | 1% | 125,868 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-04-02 | 0 | 0 | 0% | — | — | — | — | — | 0 | 1 | 0 | 0 |
| STORY-04-03 | 0 | 0 | 0% | — | — | — | — | — | 0 | 1 | 0 | 0 |
| STORY-05-01 | 0 | 0 | 0% | — | — | — | — | — | 6 | 0 | 0 | 6 |
| STORY-05-02 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |
| STORY-05-03 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |

## What the gate blocked on

| check | blocks |
|---|---|
| TDD | 1 |
| criteria have tests | 1 |
| review | 1 |
| security | 1 |
| tests verify story | 1 |

## By role

| role | sessions | turns | tokens | share |
|---|---|---|---|---|
| ? | 12 | 148 | 12,509,959 | 86% |
| developer | 13 | 258 | 1,419,832 | 10% |
| review | 13 | 66 | 426,214 | 3% |
| security | 13 | 39 | 195,480 | 1% |
