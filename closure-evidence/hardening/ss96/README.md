# SS-96 — an absence routed to the developer

## What the kernel did

`tests verify story` and `TDD` read the same evidence. When the nop control at the parent SHA could not run,
the first reported `UNRUNNABLE` with failure owner `ENVIRONMENT` — correct — and the second reported `FAILED`
("tests green on first run — not proven to verify anything"). `_absent_stages` returns nothing as soon as any
check has FAILED, so the attempt was routed to the developer instead of to the stage that could not answer.

## The reproducer

`reproducer_lifecycle.py` — one story, one CHANGE_REQUIRED criterion, a candidate that is correct, and a parent
whose evidence for that criterion is `DEPENDENCY_UNRUNNABLE` for a reason outside the story.

| `run.max_retries` = 2 | before | after |
| --- | --- | --- |
| developer sessions | 3 | 1 |
| quality attempts | 3 | 1 |
| stage re-verifies | 0 | 3 |
| terminal | `QUALITY_BLOCK` | `ENVIRONMENT_FAILURE` |
| checks FAILED | `TDD` | none |
| checks UNRUNNABLE | `tests verify story` | `TDD`, `tests verify story` |

A correct story was failed, and its whole developer budget was spent, because evidence could not run.

## The sibling sweep

`sweep_every_stage.py` makes each stage's evidence absent in turn. Before the fix, two stages were wrong and
three were already right — which is what located the single converting check:

| stage absent | before | after |
| --- | --- | --- |
| nop / parent evidence | `QUALITY_BLOCK`, 2 quality attempts, 0 stage retries | `ENVIRONMENT_FAILURE`, 1, 3 |
| test tool | `QUALITY_BLOCK`, 2 quality attempts, 0 stage retries | `ENVIRONMENT_FAILURE`, 1, 3 |
| lint | `ENVIRONMENT_FAILURE`, 1 quality attempt, 3 stage retries | unchanged |
| review | `UNRUNNABLE`, 1 quality attempt, 2 review re-executions | unchanged |
| security | `UNRUNNABLE`, 1 quality attempt, 2 security re-executions | unchanged |

## Why the 14/14 conformance report missed it

`CONFORMANCE-BEFORE-FIX.json` is the corrected suite run against the defective kernel: 20 mismatches over
scenarios G, H, O and P. The earlier suite reported 0 because its reference model had taken two fields from the
kernel rather than from the approved policy — the budget rule ("anything blocking that is not PLAN-owned spends a
developer session") and each scenario's terminal, both written down after watching the kernel — and because it
never compared the environment/stage budget or the retry target at all. The model now derives the whole lifecycle
from the failure owner, and both missing fields are compared.

## The fix

One branch in `aisef/control/gate.py::evaluate`: with no red run recorded and the nop control `UNRUNNABLE`, the
TDD check is `UNRUNNABLE` carrying the control's own reason. The kernel's existing routing does the rest.
Registered as `INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE` (P1) and held by
`tests/hardening/test_unrunnable_routing.py`.
