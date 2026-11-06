# Đợt-2 closing blocker report (owner #7)

Owner #7 (2026-11-06): *Present a report closing the remaining blockers with technical evidence before asking for the next decision. Đợt 3 not started; no release tag.*

This consolidates the technical closure of all five open blockers from the owner's 7 decisions. **Posture held: Đợt-2 implementation scope is closed (owner #1); overall acceptance is NOT claimed PASS and v2.2 is NOT tagged (owner #1/#7). Đợt 3 not started.**

HEAD = `2047205a` (master). All evidence below is committed under `closure-evidence/v2/v2.2/`.

## Blocker status

### #6 — CI unit Ubuntu 3.11 (owner: "check immediately; don't treat CI as PASS while a mandatory job is red")

**Cause determined and re-verified.** Run [42151025036](https://github.com/nghinh/aisef/actions/runs/42151025036) at HEAD:

| job | result |
|---|---|
| unit (ubuntu 3.11 / 3.12 / 3.13 / 3.14) | ✓ green |
| unit (windows 3.11), unit (macos 3.12) | ✓ green |
| lint, wheel | ✓ green |
| **sealing** | ✗ red — **by design** (record-currency tier on unsealed master) |

The original 3.11 failure was `test_v21_confine.py::test_what_is_measured_decides_not_the_name_of_the_tool` timing out on the **product** `PROBE_TIMEOUT=60` under CI saturation (owner #3 said keep that constant as-is). Proof it is infra-load, not a mechanism bug: the same test runs **locally unloaded in 2.936s → OK**, and on the re-run the 3.11 cell is **green**. The only red is `sealing`, which the job's own header documents as expected-red on an unsealed tree — closed by the owner-#4 reseal, not a code fix. **Not claimed PASS while it is red** (owner #6 honored): greening it is the owner's reseal act.

### #3 — Mutation 236 real gaps (owner: classify by risk/invariant/control-path/exploitability; prioritized hardening list; no registry change, no criteria change)

Full risk classification with adversarial verification: **0 critical, 11 high, 41 medium, 186 low** (238 classified; 114 on control-path; 9 direct-exploit; 149 adversarially re-examined). Evidence: [MUTATION-WAVE2-HARDENING-PRIORITY.md](./MUTATION-WAVE2-HARDENING-PRIORITY.md) + `.json`.

The 11 high gaps are **survived mutants** (shipped code is correct; the gap is a missing regression guard) and collapse to **three test-only hardening items**, no product/registry change:
1. **P1** — one `run.execute()` integration test with a pinned+fenced settings (kills 4 high *direct*: client-pin admission, declared-fence confinement, TOCTOU pin re-check).
2. **P2** — four tripwire serve-surface assertions (kills 6 high: fail-closed `except` arm, `_canonical` separators, non-ASCII escaped spelling, frozen-tuple recursion — the last is silently broken in production).
3. **P3** — one `register_runtime` fail-closed assertion (kills 1 high *indirect*).

Scope guard honored: no registry expansion, no acceptance-criteria change; applying the three is a separate owner go (test-only, so no frozen-kernel approval needed).

### #2 — FINDING-WIN-OSKILL-001 (owner: Option A approved in principle; implement only after proving Windows repro + authority preserved + regression; STOP at invariant/frozen-kernel)

Package ready, **STOPPED at the kernel boundary** (owner condition): [FINDING-WIN-OSKILL-001-AUTHORITY-AND-REGRESSION.md](./FINDING-WIN-OSKILL-001-AUTHORITY-AND-REGRESSION.md).
- **(b) authority preserved** — Option A *reduces* authority (query-only `OpenProcess`+`GetExitCodeProcess` replaces a latent `TerminateProcess`); `_is_gone`'s decision table is unchanged; INV-MUTATION-AUTHORITY satisfied (strict-subset direction).
- **(a) Windows repro** — opt-in, `workflow_dispatch`-only CI job [win-oskill-repro.yml](../../../.github/workflows/win-oskill-repro.yml) runs the one repro test on `windows-latest`; RED = reproduction, GREEN = fixed. Never on push/PR (cannot affect mandatory CI). Dispatch pending; its RED result attaches here before Option A is acted on.
- **(c) regression** — plan to move the repro test into `tests/v2/` with a POSIX companion pinning the decision table.
- **STOP:** Option A edits `aisef2/app/client.py` (frozen kernel). ~8-line diff is ready, **not applied**; awaiting separate owner approval.

### #5 — HistoricalAttempt4 forensic guard (owner: plan to move to immutable evidence; keep verification meaning; do not merely skip)

Plan ready: [FORENSIC-GUARD-IMMUTABLE-EVIDENCE-PLAN.md](./FORENSIC-GUARD-IMMUTABLE-EVIDENCE-PLAN.md). Sub-check 4 of `external_problems` reads the **live** `opencode.db` and trips on any legitimate client activity after `attempt-n.finished` (the owner-approved B1/B7 canary wrote sessions on 2026-11-05/06 → the one local-suite failure; machine-local, CI-immune, 0% code-diff). Fix: snapshot attempt-n's own session rows into the preserved evidence with a digest and compare the **frozen snapshot**, not the live DB (keeps the "external footprint un-tampered" meaning; stops failing on unrelated growth; not a skip). For attempt-4 specifically, where no era snapshot exists, fall back to the scoped-to-journal-named-ids check + an evidence note — no fabrication. Awaiting owner go.

### #4 — Reseal / Q5 / freeze_manifest (owner: prepare comparison dossier + controlled reseal plan; no overwrite/back-date/evidence loss; execute only after owner approves manifest + provenance plan)

Dossier + plan ready: [RESEAL-COMPARISON-DOSSIER-AND-PLAN.md](./RESEAL-COMPARISON-DOSSIER-AND-PLAN.md). The `sealing` red = **17 record-currency records** stale because approved Đợt-2 commits post-date the last seal (mapped to their generators in the dossier). The reseal mechanism is already provenance-preserving: `freeze_manifest` **appends amendments** binding each prior record by sha256 with before/after digests — "the original approval record never changes" — and a broken-link check makes the chain tamper-evident. Plan: dry-run change manifest → owner approval → append amendments (no overwrite, no back-date, history byte-identical) → re-run sealing green. **No reseal performed.**

## What remains for overall acceptance (the owner's next decisions)

Đợt-2 code scope is closed and green on every mandatory tier except the by-design `sealing` red. Overall acceptance PASS + a v2.2 tag become grantable only after the owner decides, in whatever order:

1. **Apply the 3 mutation hardening tests** (#3) — test-only, no product change.
2. **Approve FINDING Option A** (#2) — separate frozen-kernel approval, after the Windows repro RED evidence is captured.
3. **Approve the forensic-guard immutable-evidence change** (#5).
4. **Approve the reseal change manifest + provenance plan** (#4) — this is what greens `sealing` and makes CI fully green.

None of these is started beyond the prepared plans/tests above. No Đợt 3. No tag. Awaiting the owner's next decision.
