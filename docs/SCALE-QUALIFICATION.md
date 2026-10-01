# Scale qualification contract

AISEF claims a scale level only after that level has been qualified against this contract. A level is
qualified when every exit criterion below was measured on the frozen candidate named in the qualification
record, with the repeat count met, and the hidden oracle agreed with the framework's own verdicts. Claims above
the highest qualified level are not made — not in README, landing, salekit or release notes.

Qualification records live in `closure-evidence/hardening/` (W0: `AISEF-W0-QUALIFICATION.json`; W1:
`W1-LEDGERLOCK-*.json`). The framework safety properties that must repeat across runs are the same at every
level: state stays valid, evidence stays bound to its identity, failures are classified correctly, recovery stays
within the invariants, no false PASS, no manual state repair. Generated code is allowed to differ between runs;
framework correctness is not.

## Levels

| | W0 Synthetic kernel | W1 LedgerLock | W2 SaaS/API/UI/DB/Auth | W3 Workflow/Async/Role/Integration | W4 Enterprise modular | W5 Multi-service |
|---|---|---|---|---|---|---|
| story count | 0 (scripted scenarios) | 12–20 (reference: 16) | 30–50 | 60–100 | 120–180 | 250+ |
| dependency depth (longest story chain) | n/a | ≤ 4 | ≤ 6 | ≤ 8 | ≤ 10 | ≤ 12, across service boundaries |
| parallel width (stories per wave) | n/a | ≤ 3 planned; actual width = stories whose EFFECTIVE write scopes are disjoint (INV-O.1 — a manifest or lockfile granted to two stories serialises them; F4/SS-53) | ≤ 4, same rule | ≤ 6, same rule | ≤ 8, same rule | ≤ 12, same rule |
| shared-file contention | scripted (scope violations, manifests) | manifests + one shared module | manifests, migrations, shared schema, auth middleware | + event schemas, queue contracts, role matrices | + shared libraries across modules, generated clients | + cross-service API contracts, shared infra manifests |
| resume count exercised | every trace class (model) + scripted resume | ≥ 2 forced resumes per run | ≥ 3 | ≥ 5 | ≥ 8 | ≥ 12, incl. resume after host change |
| failure injection profile | full fault matrix (54 cells) + compound faults + 100 000 differential traces | targeted historical replays (D-032, baseline provenance, retry hygiene, D-035) + natural model failures | fault matrix subset run live: review cut, security cut, tool unrunnable, process death | + lease expiry, orphan reclaim, contract change mid-epic | + multi-host claim contention, budget exhaustion, approval invalidation mid-run | + partial service outage, cross-service merge conflict |
| evidence volume (events per run, order of magnitude) | 10^3 (scripted) | 10^3–10^4 | 10^4 | 10^4–10^5 | 10^5 | 10^5–10^6 |
| supported OS | Linux, Windows, macOS (CI matrix) | Windows 11 (reference operator) + Linux | Linux + Windows | Linux + Windows | Linux + Windows | Linux + Windows |
| supported clients | synthetic (no model) | OpenCode (first-class) | OpenCode + Claude Code | OpenCode + Claude Code | OpenCode + Claude Code | OpenCode + Claude Code |
| supported stacks | none (kernel only) | Python | Python, Node/TypeScript | + Go or Rust | + polyglot per module | + polyglot per service |
| expected duration | minutes (CI) | 6–12 h per run | 12–24 h | 24–48 h | 48–96 h | multi-day |
| required repeat runs | 1 (deterministic; seeds recorded) | 3 fresh runs, identical frozen requirements and environment contract | 3 | 2 | 2 | 1 + 1 resume-from-checkpoint |
| hidden oracle | reference model + differential harness | independent LedgerLock oracle (not visible to the run) | independent acceptance oracle per story set | same | same | same |
| exit criteria | 0 P0/P1; 0 unfixed confirmed defects from the frozen set; 0 NEEDS_TEST; 0 MISSING/PARTIAL invariants; 0 expected-red; 0 unexplained model/kernel gaps; fault matrix GREEN; 0 safety-significant mutation survivors; Linux + Windows CI green | false PASS = 0; manual state repair = 0; silent evidence substitution = 0; orphan state = 0; unexplained condition drift = 0; oracle run on every completed delivery; every framework-attributed stop classified correctly | W1 criteria + zero scheduler conflicts on shared files + resume count met | W2 + lease/orphan properties measured | W3 + multi-host properties measured | W4 + cross-service merge properties measured |

A model or project quality failure is allowed at any level when the framework classifies it correctly; it is
recorded separately from framework outcome. A framework misclassification is a qualification failure.

## What "qualified" means operationally

1. The candidate SHA, product digest, tool images, client adapters and environment are recorded before the first run.
2. No AISEF change during the runs. A defect found during a run is registered and the level is re-run after the fix.
3. Every run reaches a terminal state under the framework's own gates; no gate is waived.
4. The hidden oracle is run after the framework declares completion, and its verdict is recorded next to the framework's.
5. The qualification record lists every operator arbitration, every drift event and every remaining known defect of any severity.

## Current status

| level | status |
|---|---|
| W0 | **qualified** at candidate `0a7cab86086e` (2026-09-18; `closure-evidence/hardening/AISEF-W0-QUALIFICATION.json`, 11/11 criteria; Phase 12: 100 000 single-kernel traces on product tree `02a34e0e…`, 0 unexplained; default tool capabilities qualified on real images). The earlier qualification at `abad2a6af796` is **VOID** — W1 run 1 found SS-65 (P1) on that candidate; it is kept unedited under `closure-evidence/hardening/voided-abad2a6/` and is not qualification evidence for anything |
| W1 | in progress — 3 fresh LedgerLock runs on the frozen candidate (`closure-evidence/hardening/P19-FREEZE.json`); not claimed until `W1-LEDGERLOCK-SUMMARY.json` |
| W2–W5 | not qualified; not claimed |
