# OWNER SCOPE AMENDMENT — external B2 evaluation REMOVED from v2.3 release scope (2026-11-26)

**Authority/provenance:** OWNER RULING "REMOVE EXTERNAL B2 EVALUATION FROM RELEASE SCOPE", delivered by the owner
as a verbatim paste into the working Claude Code session on 2026-11-26, effective immediately. Operative text,
verbatim: "I have decided to remove the external independent ground-truth evaluation requirement from AISEF
v2.3.0. I will organize my own evaluation team separately at a later stage. This decision supersedes all previous
instructions requiring two external evaluators, three real-world repositories, B2 external outreach, B2-SPEND
approval, or an external oracle evaluation before v2.3 release."

## Removed from v2.3 mandatory delivery/release scope (ruling §1)

Recruitment of two external evaluators; evaluation against three representative external repositories; B2 outreach
and evaluator screening; B2-SPEND approval, procurement, compensation and spending-ledger preparation; the
2026-12-08 B2-SPEND deadline; B2-ORACLE-SIGNED as a required owner action; B2-MEASURE as a prerequisite for
RC-FREEZE; external ground-truth evaluation as a mandatory W6 exit gate. The DAG edge
`CODE-FREEZE → B2-MEASURE → RC-FREEZE` and the mandatory B2-ORACLE-SIGNED dependency are removed; RC-FREEZE
depends only on the remaining genuine mandatory prerequisites.

**Status label (mandated):** `REMOVED_FROM_V2.3_RELEASE_SCOPE_BY_OWNER` — never PASSED or QUALIFIED. No claim is
made that external independent validation, false-acceptance rates or cross-repository generalization have been
demonstrated.

## Execution facts at the moment of the ruling

No outreach message was ever sent; no candidate was contacted; no account was created; zero USD was spent; no
B2-SPEND ledger was opened. The prepared outreach kit (private evidence, 2026-11-26-b2-evaluators/) is banner-
stopped and retained as historical prep only.

## Preserved (ruling §3, §5)

- B2 Tier-0 code, tests and evidence stay (validation/v23/ground_truth/**, tests/v2/test_v23_ground_truth.py,
  B2 research docs): useful, non-interfering; tests remain in normal CI. Further B2-specific engineering stops
  unless independently required by another retained capability.
- **B5 (independent acceptance gateway / grading) remains in scope** — the ruling removes the external evaluation
  campaign, not the product's ability to grade externally produced code.
- Every other quality/security gate is unchanged: native 3-OS CI, full unit+regression, F5 mutation qualification
  and provenance, Q0 calibration, signed evidence and historical compatibility, journal integrity/accounting/
  resume correctness, confinement and negative controls, build reproducibility and sealing, P0/P1 rejection,
  release governance and final owner publication approval.

## Later owner-led evaluation (ruling §2)

A separate activity the owner organizes independently — NOT a prerequisite for CODE-FREEZE, RC-FREEZE, release
qualification or v2.3.0 publication. No new mandatory evaluation deadline is created and the requirement is not
moved to another release gate.

Frozen records and historical owner ledgers remain immutable; this amendment is the dated scope-change record.
