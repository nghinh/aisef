# Spend attribution — `w1-run-1`

Unit: **input tokens** — the provider priced 0% of 74 sessions (0.00 USD recorded in total), so dollars here would be invented. With `p` = price per 1M input tokens and `q` = per 1M output:

    cost ≈ 128.48 × p + 0.513 × q

Cache reads are 0% of prompt tokens (0 cached vs 128,476,781 fresh); most price lists charge them far less, so they are counted separately.

⚠ At 0% cache, this client bills re-sent context as fresh `input`: the totals below are a sum over turns of the whole prompt and are **not** comparable with a corpus that caches.

Net VERIFIED per M input tokens: **0.54**

70 verified · 7 gap · 0 reopened → net **70** behaviours for 128,476,781 across 74 sessions (1,733 turns).

## Where the spend went

| class | sessions | turns | tokens | share |
|---|---|---|---|---|
| passed | 23 | 440 | 31,256,114 | 24% |
| gate-blocked | 17 | 265 | 19,021,012 | 15% |
| turn-cap | 22 | 880 | 65,689,696 | 51% |
| planning | 12 | 148 | 12,509,959 | 10% |

Spend on stories that ended with a net VERIFIED behaviour: **80%**.

## Per story

Ledger columns **overlap** between stories (one FR can be covered by two), so they do not sum to the corpus counts above.

| story | attempts | tokens | share | passed | gate-blocked | turn-cap | env-failed | no-verdict | verified | gap | reopened | net |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| STORY-01-06 | 3 | 16,680,317 | 13% | 4,878,848 | 6,028,840 | 5,772,629 | — | — | 8 | 0 | 0 | 8 |
| STORY-04-01 | 3 | 14,437,563 | 11% | 2,637,913 | 5,430,433 | 6,369,217 | — | — | 5 | 0 | 0 | 5 |
| STORY-04-02 | 1 | 13,031,772 | 10% | — | 772,559 | 12,259,213 | — | — | 0 | 7 | 0 | 0 |
| STORY-03-01 | 2 | 12,875,338 | 10% | 2,707,327 | 765,278 | 9,402,733 | — | — | 7 | 0 | 0 | 7 |
| STORY-03-02 | 2 | 11,169,358 | 9% | 2,424,645 | 2,758,195 | 5,986,518 | — | — | 5 | 0 | 0 | 5 |
| STORY-01-01 | 2 | 10,461,011 | 8% | 2,047,067 | 124,025 | 8,289,919 | — | — | 10 | 0 | 0 | 10 |
| STORY-02-01 | 2 | 8,879,206 | 7% | 3,704,228 | 2,234,763 | 2,940,215 | — | — | 7 | 0 | 0 | 7 |
| STORY-01-05 | 2 | 8,742,685 | 7% | 2,124,847 | 781,391 | 5,836,447 | — | — | 8 | 0 | 0 | 8 |
| STORY-01-04 | 2 | 8,277,222 | 6% | 2,536,408 | 125,528 | 5,615,286 | — | — | 7 | 0 | 0 | 7 |
| STORY-02-02 | 1 | 5,824,867 | 5% | 2,607,348 | — | 3,217,519 | — | — | 5 | 0 | 0 | 5 |
| plan-epics | 0 | 5,687,131 | 4% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-01-02 | 1 | 3,702,587 | 3% | 3,702,587 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-01-03 | 1 | 1,884,896 | 1% | 1,884,896 | — | — | — | — | 6 | 0 | 0 | 6 |
| plan-architecture | 0 | 1,344,422 | 1% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-apply | 0 | 1,142,062 | 1% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-project-context | 0 | 960,795 | 1% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-ux | 0 | 675,905 | 1% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-prd | 0 | 642,950 | 1% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-help-version | 0 | 634,922 | 0% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-snapshot | 0 | 553,491 | 0% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-verify | 0 | 500,041 | 0% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-repair-tail | 0 | 368,240 | 0% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-04-03 | 0 | 0 | 0% | — | — | — | — | — | 0 | 1 | 0 | 0 |
| STORY-05-01 | 0 | 0 | 0% | — | — | — | — | — | 4 | 0 | 0 | 4 |
| STORY-05-02 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |
| STORY-05-03 | 0 | 0 | 0% | — | — | — | — | — | 1 | 0 | 0 | 1 |

## What the gate blocked on

| check | blocks |
|---|---|
| review | 10 |
| lint | 5 |
| TDD | 3 |
| criteria have tests | 3 |
| test | 3 |
| tests verify story | 3 |

## By role

| role | sessions | turns | tokens | share |
|---|---|---|---|---|
| developer | 21 | 767 | 56,290,076 | 44% |
| review | 22 | 660 | 48,953,987 | 38% |
| ? | 12 | 148 | 12,509,959 | 10% |
| security | 19 | 158 | 10,722,759 | 8% |
