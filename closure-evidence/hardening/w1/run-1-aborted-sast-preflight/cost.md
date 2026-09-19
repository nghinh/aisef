# Spend attribution — `w1-run-1`

Unit: **input tokens** — the provider priced 0% of 12 sessions (0.00 USD recorded in total), so dollars here would be invented. With `p` = price per 1M input tokens and `q` = per 1M output:

    cost ≈ 12.51 × p + 0.105 × q

Cache reads are 0% of prompt tokens (0 cached vs 12,509,959 fresh); most price lists charge them far less, so they are counted separately.

⚠ At 0% cache, this client bills re-sent context as fresh `input`: the totals below are a sum over turns of the whole prompt and are **not** comparable with a corpus that caches.

Net VERIFIED per M input tokens: **0.00**

0 verified · 0 gap · 0 reopened → net **0** behaviours for 12,509,959 across 12 sessions (148 turns).

## Where the spend went

| class | sessions | turns | tokens | share |
|---|---|---|---|---|
| planning | 12 | 148 | 12,509,959 | 100% |

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

## By role

| role | sessions | turns | tokens | share |
|---|---|---|---|---|
| ? | 12 | 148 | 12,509,959 | 100% |
