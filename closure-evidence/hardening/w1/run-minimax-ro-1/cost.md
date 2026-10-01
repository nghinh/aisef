# Spend attribution — `w1-run-minimax-ro-1`

Unit: **input tokens** — the provider priced 0% of 69 sessions (0.00 USD recorded in total), so dollars here would be invented. With `p` = price per 1M input tokens and `q` = per 1M output:

    cost ≈ 204.17 × p + 0.672 × q

Cache reads are 0% of prompt tokens (0 cached vs 204,171,588 fresh); most price lists charge them far less, so they are counted separately.

⚠ At 0% cache, this client bills re-sent context as fresh `input`: the totals below are a sum over turns of the whole prompt and are **not** comparable with a corpus that caches.

Net VERIFIED per M input tokens: **0.34**

70 verified · 7 gap · 0 reopened → net **70** behaviours for 204,171,588 across 69 sessions (2,377 turns).

## Where the spend went

| class | sessions | turns | tokens | share |
|---|---|---|---|---|
| passed | 30 | 913 | 74,236,294 | 36% |
| gate-blocked | 18 | 608 | 52,359,423 | 26% |
| turn-cap | 8 | 640 | 58,637,517 | 29% |
| no-verdict | 1 | 68 | 6,428,395 | 3% |
| planning | 12 | 148 | 12,509,959 | 6% |

Spend on stories that ended with a net VERIFIED behaviour: **74%**.

## Per story

Ledger columns **overlap** between stories (one FR can be covered by two), so they do not sum to the corpus counts above.

| story | attempts | tokens | share | passed | gate-blocked | turn-cap | env-failed | no-verdict | verified | gap | reopened | net |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| STORY-04-02 | 2 | 41,391,582 | 20% | — | 11,252,575 | 23,710,612 | — | 6,428,395 | 0 | 7 | 0 | 0 |
| STORY-04-01 | 3 | 30,971,195 | 15% | 2,142,326 | 14,309,366 | 14,519,503 | — | — | 5 | 0 | 0 | 5 |
| STORY-01-06 | 2 | 21,482,437 | 11% | 8,956,044 | 5,611,009 | 6,915,384 | — | — | 8 | 0 | 0 | 8 |
| STORY-01-05 | 2 | 19,350,699 | 9% | 2,850,777 | 8,919,649 | 7,580,273 | — | — | 8 | 0 | 0 | 8 |
| STORY-01-01 | 2 | 18,166,308 | 9% | 9,697,842 | 2,556,721 | 5,911,745 | — | — | 10 | 0 | 0 | 10 |
| STORY-03-02 | 2 | 17,759,692 | 9% | 8,049,589 | 9,710,103 | — | — | — | 5 | 0 | 0 | 5 |
| STORY-03-01 | 1 | 11,901,841 | 6% | 11,901,841 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-01-04 | 1 | 8,968,228 | 4% | 8,968,228 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-02-02 | 1 | 7,647,887 | 4% | 7,647,887 | — | — | — | — | 5 | 0 | 0 | 5 |
| plan-epics | 0 | 5,687,131 | 3% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| STORY-02-01 | 1 | 5,614,879 | 3% | 5,614,879 | — | — | — | — | 7 | 0 | 0 | 7 |
| STORY-01-03 | 1 | 5,199,994 | 3% | 5,199,994 | — | — | — | — | 6 | 0 | 0 | 6 |
| STORY-01-02 | 1 | 3,206,887 | 2% | 3,206,887 | — | — | — | — | 7 | 0 | 0 | 7 |
| plan-architecture | 0 | 1,344,422 | 1% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| mockup-apply | 0 | 1,142,062 | 1% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-project-context | 0 | 960,795 | 0% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-ux | 0 | 675,905 | 0% | — | — | — | — | — | 0 | 0 | 0 | 0 |
| plan-prd | 0 | 642,950 | 0% | — | — | — | — | — | 0 | 0 | 0 | 0 |
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
| TDD | 5 |
| tests verify story | 5 |
| review | 4 |
| lint | 1 |

## By role

| role | sessions | turns | tokens | share |
|---|---|---|---|---|
| developer | 20 | 1,298 | 114,533,131 | 56% |
| review | 19 | 706 | 60,189,593 | 29% |
| security | 18 | 225 | 16,938,905 | 8% |
| ? | 12 | 148 | 12,509,959 | 6% |
