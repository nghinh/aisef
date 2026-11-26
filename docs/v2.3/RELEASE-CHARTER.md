# AISEF v2.3 — RELEASE CHARTER (frozen at W0)

Freezes the v2.3 product claim, the mandatory release gates and the non-negotiable rules **before** any product
code change (directive §C). Per-capability acceptance criteria are enumerated in `MASTER-CHECKLIST.md` (one row
per roadmap/V21 ID, from the W0 audit); this charter freezes the envelope they must satisfy. Extends, never
weakens, `docs/v2/V2-STABLE-RELEASE-CHARTER.md`.

## 1. The v2.3 product claim (what 2.3 asserts)

v2.3 is **one** major release on the `aisef run` V2 runtime that must deliver, each with falsifiable evidence:

1. **Usable authoring & approval** — a new engineer, from a clean `pip install`, drafts + approves a bundle and
   reads a verdict using shipped CLI only, no framework-internals editing (`B4/B6/G4`).
2. **Evidence-bound delivery kernel** with a typed stage lifecycle and deterministic `finally` (`E5/E6/E7`).
3. **Incremental qualification** with provably-valid evidence reuse — typed `MEASURED|VERIFIED_REUSE|INVALIDATED|
   UNRESOLVED`, fail-closed, no `source_sha256` rebinding, ≥50% qualification wall-time reduction on representative
   scoped changes with detection unchanged (`F5/F2`).
4. **Authentic evidence & honest accounting** — signed/keyed head anchored outside developer-writable data,
   `--verify --expect-pubkey` fails any consistent adversarial rewrite when the external anchor is trusted;
   provider spend reserved/reconciled under SIGKILL, never silently 0 (`A2/E1/E2/E4/E3`).
5. **A verified security boundary** — developer/test/probe confined with declared read/write/network policy and
   real escape canaries on Linux/macOS; no raw provider key in the developer process/logs/prompts (`D1/D2/D3/C7`).
6. **Crash-safe resume & cost-aware, parallel orchestration** — same-run `--resume` that never replays unaccounted
   spend or rewrites signed history; DAG-parallel stories with one authoritative serialized journal (`G6/C1/C5/G9/
   C6/C10`).
7. **An agent-independent acceptance gateway** — `grade` an approved bundle against another agent's git diff with
   zero dependency on OpenCode generation (`B5/C8`).
8. **Independent ground-truth evaluation** — a frozen oracle corpus + ≥3 representative repos + ≥2 external
   evaluators, reporting false-accept/false-reject by contract scope separately (`B2`).

Any ID that cannot be delivered without weakening an invariant is a **STOP for owner decision**, never a silent
deferral to 2.4 (directive §B, §F).

## 2. Mandatory release gates (frozen; from directive §E)

A v2.3 production tag requires **all** of, with no allowlist masking:

- Unit: Ubuntu CPython **3.11–3.14**, macOS **3.12**, **native Windows 3.11** — all green.
- `AISEF_SEALING=1` sealing, lint (`ruff`), wheel+sdist build, clean install, offline end-to-end `aisef run`,
  `aisef demo`, signed `--verify` (+ expected-bad controls), versioned-evidence read of historical 2.2 runs.
- Deterministic wheel/sdist whose SHA **exactly** matches the frozen RC and the published PyPI files.
- Mutation/qualification green on the changed scope with 0 false-current reuse; seeded known-bad calibration still
  **FAIL**.
- **REL-GOV-01 closed**: the `pypi` environment has a real required-reviewer gate, verified by observing the
  `publish` job enter `status: waiting`. (See `RELEASE-GOVERNANCE-FINDING.md`.)
- No P0/P1 trust/secret/false-PASS/integrity defect; 0 known unresolved mandatory evidence.

A platform leg may be added to the support matrix **only after native end-to-end proof** — a native-Windows unit
pass alone never establishes live-Windows `aisef run` support.

## 3. KPI proofs (frozen)

- **Efficiency:** frozen cold-vs-incremental on no-op / one-function / shared-helper / kill-test / cross-platform
  changes; target **≥50%** faster qualification wall time without weakening detection; baseline + hardware reported.
- **Usability:** clean wheel install → no-key `demo` < 10 min; first guided bundle < 30 min (measured, not asserted).
- **Real value:** ≥3 repos, ≥2 external evaluators, in-scope/out-of-scope truth not conflated, real or
  clearly-estimated wallclock/tokens/USD.

## 4. Non-negotiable rules (frozen; from directive §D)

- **Trust invariants unchanged or stronger.** No false PASS, no allowlist hiding defects, no fake re-measurement,
  no `source_sha256` rebinding to pass old results as new bytes. Reuse needs a positively-bound, adversarially
  validated equivalence proof. Historical V1/V2.0/V2.1/V2.2 evidence and owner ledgers are **immutable**.
- **Compatibility:** keep the shipped 2.2.0 CLI/bundle/format readers, or provide an explicitly versioned migration
  with tests; never retroactively claim 2.2 signatures/proofs.
- **Economics:** zero paid GitHub; zero new paid model/AI trials without an owner-approved scoped cap + spend
  ledger; offline/fake-client first.
- **Bounded qualification:** classify PRODUCT_DEFECT / TEST_DEFECT / ENVIRONMENT / STALE_RECORD / EQUIVALENT /
  ACCEPTED_LIMITATION / UNKNOWN. UNKNOWN is never accepted; a platform failure is never PASS without native proof.
- **One public release:** `master`, `v2.3.0`, PyPI untouched until a separate final owner authorization. v2.3 work
  lives on `release/v2.3-big` + isolated worktrees/PRs.
- **Security/ops:** no disabling security tools, no secret leakage, no unattended destructive cleanup, no
  root/sudo/cron changes without owner-controlled action; keep backups/recovery copies.

## 5. Owner decision points (ask only for these — directive §F)

(1) a genuinely incompatible trust/architecture ruling; (2) paid provider/cloud spend; (3) privileged operations
or secrets; (4) release/tag/PyPI irreversible publication; (5) a mandatory blocker whose only remedy would weaken
an invariant or the agreed full scope.

---

## Amendment 2026-11-26 — external B2 evaluation removed from v2.3 release scope

[SCOPE AMENDMENT 2026-11-26: REMOVED_FROM_V2.3_RELEASE_SCOPE_BY_OWNER — see amendments/SCOPE-B2-EXTERNAL-REMOVED.md]

This charter is frozen at W0, so the owner ruling of 2026-11-26 is applied by this appended, dated amendment —
no inline edit. The following clauses are struck as v2.3 release / W6 exit requirements. Mandated status:
`REMOVED_FROM_V2.3_RELEASE_SCOPE_BY_OWNER` — never PASSED or QUALIFIED; no claim is made that external
independent validation, false-acceptance rates or cross-repository generalization have been demonstrated.

- **§1 claim 8** (lines 28–29): "**Independent ground-truth evaluation** — a frozen oracle corpus + ≥3
  representative repos + ≥2 external evaluators, reporting false-accept/false-reject by contract scope
  separately (`B2`)." — removed as a mandatory v2.3 product claim. B2 Tier-0 code, tests and research docs are
  retained (ruling §3); further B2-specific engineering stops unless another retained capability requires it.
- **§3 KPI "Real value"** (lines 56–57): "≥3 repos, ≥2 external evaluators, in-scope/out-of-scope truth not
  conflated, real or clearly-estimated wallclock/tokens/USD." — removed as a mandatory KPI proof.

**Not weakened** (ruling §5): every §2 mandatory release gate, the §3 "Efficiency" and "Usability" KPI proofs,
and every §4 non-negotiable rule are unchanged. **B5** (agent-independent acceptance gateway, §1 claim 7)
**stays in scope**. Owner-led evaluation happens separately after release (ruling §2) and is NOT a prerequisite
for CODE-FREEZE, RC-FREEZE, release qualification or v2.3.0 publication; the requirement is not moved to any
other gate and no new mandatory evaluation deadline is created.
