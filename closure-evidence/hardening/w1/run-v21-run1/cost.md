# Spend attribution — `w1-run-v21-run1`

Unit: **input tokens** — the provider priced 0% of 15 sessions (0.00 USD recorded in total), so dollars here would be invented. With `p` = price per 1M input tokens and `q` = per 1M output:

    cost ≈ 12.67 × p + 0.112 × q

Cache reads are 14% of prompt tokens (2,115,456 cached vs 12,673,198 fresh); most price lists charge them far less, so they are counted separately.

⚠ At 14% cache, this client bills re-sent context as fresh `input`: the totals below are a sum over turns of the whole prompt and are **not** comparable with a corpus that caches.

Net VERIFIED per M input tokens: **0.00**

0 verified · 11 gap · 0 reopened → net **0** behaviours for 12,673,198 across 15 sessions (176 turns).

## Where the spend went

| class | sessions | turns | tokens | share |
|---|---|---|---|---|
| gate-blocked | 3 | 28 | 163,239 | 1% |
| planning | 12 | 148 | 12,509,959 | 99% |

Spend on stories that ended with a net VERIFIED behaviour: **0%**.

## Per story

Ledger columns **overlap** between stories (one FR can be covered by two), so they do not sum to the corpus counts above.

| story | attempts | tokens | share | passed | gate-blocked | turn-cap | env-failed | no-verdict | verified | gap | reopened | net |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| plan-epics | 0 | 5,687,131 | 45% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-architecture | 0 | 1,344,422 | 11% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-apply | 0 | 1,142,062 | 9% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-project-context | 0 | 960,795 | 8% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-ux | 0 | 675,905 | 5% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-prd | 0 | 642,950 | 5% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-help-version | 0 | 634,922 | 5% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-snapshot | 0 | 553,491 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-verify | 0 | 500,041 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-repair-tail | 0 | 368,240 | 3% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-01-01 | 1 | 163,239 | 1% | — | 163,239 | — | — | — | 0 | 11 | 0 | 0 |
| STORY-01-05 | 0 | 0 | 0% | — | — | — | — | — | 0 | 1 | 0 | 0 |
| STORY-04-01 | 0 | 0 | 0% | — | — | — | — | — | 0 | 1 | 0 | 0 |
| STORY-04-02 | 0 | 0 | 0% | — | — | — | — | — | 0 | 1 | 0 | 0 |
| STORY-04-03 | 0 | 0 | 0% | — | — | — | — | — | 0 | 1 | 0 | 0 |
| STORY-05-01 | 0 | 0 | 0% | — | — | — | — | — | 0 | 1 | 0 | 0 |
| STORY-05-02 | 0 | 0 | 0% | — | — | — | — | — | 0 | 1 | 0 | 0 |
| STORY-05-03 | 0 | 0 | 0% | — | — | — | — | — | 0 | 1 | 0 | 0 |

## What the gate blocked on

| check | blocks |
|---|---|
| TDD | 1 |
| tests verify story | 1 |

## By role

| role | sessions | turns | tokens | share |
|---|---|---|---|---|
| ? | 12 | 148 | 12,509,959 | 99% |
| developer | 1 | 21 | 119,659 | 1% |
| review | 1 | 5 | 32,478 | 0% |
| security | 1 | 2 | 11,102 | 0% |
