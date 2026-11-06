# Đợt-2 round-2 acceptance status — owner's 5 decisions (2026-11-06)

Consolidates the execution of the owner's five decisions. **No v2.2 tag; Đợt 3 not started** (owner #5). Posture: Đợt-2 implementation is complete except where a measured finding reopened scope.

## Decision-by-decision

### #1 Mutation hardening — GO → **DONE**
- P1/P2/P3 hardening tests added (test-only; no registry/criteria change): [P1](../../../tests/v2/test_v22_hardening_p1_run_pin_fence.py), [P2](../../../tests/v2/test_v22_hardening_p2_tripwire.py), [P3](../../../tests/v2/test_v22_hardening_p3_register_runtime.py). Green on clean HEAD.
- **11/11 high gaps KILLED** (deterministic matrix, apply-mutation→run-test→revert; green baseline first): [MUTATION-WAVE2-HARDENING-RESULTS.md](./MUTATION-WAVE2-HARDENING-RESULTS.md), [MUTATION-WAVE2-KILL-MATRIX.json](./MUTATION-WAVE2-KILL-MATRIX.json).
- **Frozen-tuple claim verified: NO product defect.** On the real frozen data shape (`mappingproxy` + `tuple`), shipped `_fragments` produces the nested leaf; the mutant drops it. It is a regression-test gap, not a kernel defect → no kernel STOP for it. (The earlier "broken in production" wording described the *mutant's* invisibility; corrected.)
- **236 vs 238 reconciled:** 238 = 229 distinct + 9 duplicate placements; 0 missing, 1 adjacent extra, 0 severity disagreements; 0 critical under every count.

### #2 FINDING-WIN-OSKILL-001 — CONDITIONAL GO → **STOPPED at the kernel (re-approval needed)**
- Windows reproduction ran **RED on old code** (run [42172469919](https://github.com/nghinh/aisef/actions/runs/42172469919)) — but the measured failure is an uncaught `CalledProcessError` from `process_table()`, **not** the destructive `os.kill`: control never reaches the `os.kill` branch on that runner. [FINDING-WIN-OSKILL-001-REPRO-CORRECTION.md](./FINDING-WIN-OSKILL-001-REPRO-CORRECTION.md).
- Consequence: the presented Option A (fixes only `os.kill`) would **not** turn the repro GREEN — the real fix is larger (two latent hazards: H1 uncaught `process_table()` failure, H2 destructive `os.kill`). Per owner #2 (*"nếu có thay đổi ngoài phương án đã trình, dừng xin phê duyệt lại"*), **the kernel is NOT patched.** Revised (still authority-reducing) plan presented for re-approval.

### #3 HistoricalAttempt4 — GO → **DONE**
- Forensic guard moved to immutable evidence: `external_problems` no longer reads the live store; it checks a frozen, digest-bound snapshot, and for attempt-4 (no snapshot, by policy) records a transparent `LIMITATION:` — never a live read, never a fabricated snapshot, never counted as VERIFIED. [FORENSIC-GUARD-IMMUTABLE-EVIDENCE-PLAN.md §6](./FORENSIC-GUARD-IMMUTABLE-EVIDENCE-PLAN.md).
- `HistoricalAttempt4` 4/4 OK; this resolves the single local full-suite failure from round 1. ruff clean.

### #4 Reseal / Q5 / freeze_manifest — CONDITIONAL → **DRY-RUN prepared; reseal DEFERRED**
- Dry-run status + the five confirmations (design-guaranteed by the append-only amendment chain) in [RESEAL-COMPARISON-DOSSIER-AND-PLAN.md §7](./RESEAL-COMPARISON-DOSSIER-AND-PLAN.md). Reseal **deferred** because (1) owner #2 is an open finding — resealing would legitimize an unresolved finding (forbidden by owner #4), and (2) the Windows fix will re-stale the kernel records, so the reseal belongs on the *final* RC. No reseal performed; no record overwritten or back-dated.

### #5 Final acceptance — **PARTIAL; final PASS deferred**
- **This round's RC = owner #1 tests + owner #3 forensic guard only** (no kernel change — owner #2 stopped). Mutation targeted: the 11 high gaps are KILLED (#1). Full suite on this RC: launched on the committed RC (result relayed on completion). CI: triggered by the push (the `sealing` job is red by design on the unsealed tree; the win-oskill opt-in captured the RED).
- **Final acceptance PASS cannot be claimed**: owner #2 is reopened, so the RC is not final. A final PASS/FAIL + release gate belong on the RC that includes the approved Windows fix and the controlled reseal.

## Remaining risks / open items (for the owner's next decision)
1. **Owner #2 revised fix** — approve the larger Windows fix (H1 + H2), then: apply, prove repro GREEN, full regression + mutation targeted, decision-table preserved.
2. **Owner #4 reseal** — execute on the final RC after #2 lands (dry-run → owner approval of the digest manifest → append-only reseal → sealing green).
3. **Final acceptance** — full suite + mandatory CI + sealing + mutation targeted + verification on that final RC, with the PASS/FAIL + release gate report.

No tag. No Đợt 3.
