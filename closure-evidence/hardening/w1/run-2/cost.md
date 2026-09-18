# Spend attribution — `w1-run-2`

Unit: **input tokens** — the provider priced 0% of 19 sessions (0.00 USD recorded in total), so dollars here would be invented. With `p` = price per 1M input tokens and `q` = per 1M output:

    cost ≈ 23.94 × p + 0.136 × q

Cache reads are 0% of prompt tokens (0 cached vs 23,936,975 fresh); most price lists charge them far less, so they are counted separately.

⚠ At 0% cache, this client bills re-sent context as fresh `input`: the totals below are a sum over turns of the whole prompt and are **not** comparable with a corpus that caches.

Net VERIFIED per M input tokens: **0.00**

0 verified · 10 gap · 0 reopened → net **0** behaviours for 23,936,975 across 19 sessions (309 turns).

## Where the spend went

| class | sessions | turns | tokens | share |
|---|---|---|---|---|
| gate-blocked | 4 | 41 | 2,835,576 | 12% |
| turn-cap | 3 | 120 | 8,591,440 | 36% |
| planning | 12 | 148 | 12,509,959 | 52% |

Spend on stories that ended with a net VERIFIED behaviour: **0%**.

## Per story

Ledger columns **overlap** between stories (one FR can be covered by two), so they do not sum to the corpus counts above.

| story | attempts | tokens | share | passed | gate-blocked | turn-cap | env-failed | no-verdict | verified | gap | reopened | net |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| STORY-01-01 | 2 | 11,427,016 | 48% | — | 2,835,576 | 8,591,440 | — | — | 0 | 10 | 0 | 0 |
| plan-epics | 0 | 5,687,131 | 24% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-architecture | 0 | 1,344,422 | 6% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-apply | 0 | 1,142,062 | 5% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-project-context | 0 | 960,795 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-ux | 0 | 675,905 | 3% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-prd | 0 | 642,950 | 3% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-help-version | 0 | 634,922 | 3% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-snapshot | 0 | 553,491 | 2% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-verify | 0 | 500,041 | 2% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-repair-tail | 0 | 368,240 | 2% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-01-05 | 0 | 0 | 0% | — | — | — | — | — | 0 | 1 | 0 | 0 |
| STORY-05-02 | 0 | 0 | 0% | — | — | — | — | — | 0 | 1 | 0 | 0 |
| STORY-05-03 | 0 | 0 | 0% | — | — | — | — | — | 0 | 1 | 0 | 0 |

## What the gate blocked on

| check | blocks |
|---|---|
| TDD | 2 |
| tests verify story | 2 |
| lint | 1 |
| review | 1 |

## By role

| role | sessions | turns | tokens | share |
|---|---|---|---|---|
| ? | 12 | 148 | 12,509,959 | 52% |
| developer | 3 | 120 | 8,591,440 | 36% |
| review | 2 | 32 | 2,261,698 | 9% |
| security | 2 | 9 | 573,878 | 2% |
