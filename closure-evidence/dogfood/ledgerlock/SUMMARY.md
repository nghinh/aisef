# LedgerLock dogfood — intake summary (2026-09-15)

Derived record. The evidence is the per-finding files `F-1.json` … `F-9.json`
in this directory, written under `docs/DOGFOOD-FINDING-INTAKE.md`. Source
package: `ledgerlock-dogfood-evidence/20260915-154214+0700` (zip sha256
`a57594a02da163aa343c91c5bfb8d6aa76ce0fc54692b0f14265a1a9000ce5fe`, MANIFEST
digest `b8d57952866a68be056f312bd118a3261fee47a7736934cef8fc3bc0156e25ad`) plus
the orchestrator `run.log` (326 lines). Run: AI-operated, `aisef 1.7.2` from
public PyPI, OpenCode 1.18.29 via `opencode.CMD`, Windows 11, Docker Desktop
4.61.0, `python:3.12-slim`. This is **not** G6; nothing here touches
`closure-evidence/external-validation/1.7.2/`.

## STOP conditions raised

- **P1 `FRAMEWORK_PRODUCT_DEFECT` × 3 in 1.7.2** — F-2 (D-026), F-4 (D-028),
  F-5 (D-029). Per §4 of the intake procedure: stop, owner decides. Each needs a
  `PRODUCT_AFFECTING` change; that is a new patch release and a new G6 bundle
  and execution.
- No `FALSE_NEGATIVE_GATE`: no story was marked done; every wrong outcome in
  this run failed closed.
- No `UNRESOLVED` class. F-9 has `requires_product_change: unresolved` (the
  provenance gap, not the class).

## Findings

| id | class | sev | hidden oracle | affects closure | product change | register | regression (branch `dogfood/ledgerlock-red`) |
|---|---|---|---|---|---|---|---|
| F-1 orphaned `running` after orchestrator death; `status` silent about a dead claim | FRAMEWORK_PRODUCT_DEFECT | P2 | n/a | no | yes | D-025 | `TestStatusNamesADeadClaim` RED · `TestOrphanedRunningClaimIsReclaimedOnTheNextRun` GREEN |
| F-2 `[stuck] doesn't apply` in prose → terminal plan deadlock | FRAMEWORK_PRODUCT_DEFECT | **P1** | n/a | **yes** | yes | D-026 | `TestStuckMentionIsNotAPlanVerdict` RED (2) · control GREEN |
| F-3 turn cap not enforced through `opencode.CMD` | CLIENT_ADAPTER_DEFECT | P2 | n/a | no | yes | D-027 | `TestTurnCapKillsTheWholeProcessTree` launcher RED · direct child GREEN |
| F-4 python preset image has no pytest/ruff; doctor says "matches stack" | FRAMEWORK_PRODUCT_DEFECT | **P1** | n/a | **yes** | yes | D-028 | none (docker reproduction in the record) |
| F-5 `No module named pytest` read as "tests still failing" | FRAMEWORK_PRODUCT_DEFECT | **P1** | n/a | **yes** | yes | D-029 | `TestMissingTestRunnerIsUnrunnableNotRed` RED |
| F-6 `.coverage` written by the test tool counted as the agent's change | FALSE_POSITIVE_GATE | P2 | n/a | no | yes | D-030 | `TestCoverageDataFileIsNotAStoryChange` RED |
| F-7 reviewer `block` verdict with only should-fix findings | MODEL_FAILURE | P3 | n/a | no | no | — | none (fail-closed as designed; message wording P3) |
| F-8 same-wave stories all create `conftest.py`/`pytest.ini` | FRAMEWORK_PRODUCT_DEFECT | P2 (latent) | n/a | no | yes | D-031 | none (no merge reached) |
| F-9 sandbox image mutated mid-run, unattributed; no image digest in evidence | ENVIRONMENT/INFRA | P2 | n/a | no | unresolved | — | not reproducible from the package |

Counts per class: FRAMEWORK_PRODUCT_DEFECT 5 · CLIENT_ADAPTER_DEFECT 1 ·
FALSE_POSITIVE_GATE 1 · MODEL_FAILURE 1 · ENVIRONMENT/INFRA 1 ·
FALSE_NEGATIVE_GATE 0 · NOT_A_FRAMEWORK_DEFECT 0 · PLANNING_DEFECT 0 ·
PROJECT_REQUIREMENT_AMBIGUITY 0 · UNRESOLVED 0.

## The priority finding, stated exactly

The owner's hypothesis was "aisef did not reconcile". Measured: the
reconciliation path (`reconcile_all`, run first by `aisef run` and
`aisef improve`) works on the exact preserved state — both stories return to
`pending`, `claimed_by` is cleared, both can be claimed. What is confirmed is
narrower: (a) nothing *between* runs reconciles, and no public document says
that re-running does; (b) `aisef status` prints `running` for a claim whose
`HOST:PID` no longer exists. Why the orchestrator and both OpenCode sessions
died together after 15:03:09 is **not in the evidence** (no exit code, no
traceback, no operator note, no event log); no cause is asserted.

## Closure impact, measured

Registering D-025…D-031 (three of them P1) moved G2.3:

```
python3 bin/aisef closure   →   1 failed · 23 passed · 3 unrunnable
                                BLOCKED — 4 of 27 block: G2.3, G6.1, G6.2, G6.3
```

Before this intake the same command read 24 passed · 3 unrunnable (only G6
open). G2.3 is not waiver-eligible for P1. The G6 bundle, the release manifest
and the product tree are unchanged (G1.0 PASSED).

## Not recorded

One P3 note from the first pass of the analysis ("ledger reason staleness")
could not be re-derived from the package and is not recorded; a finding that
cannot be pointed at a file is not a finding.
