# CYCLE-2 EXTERNAL VALIDATION PLAN

**Status.** Planning artefact (owner's "CLOSE CYCLE-1 / PREPARE CYCLE-2 ARCHITECTURE ONLY", 2026-09-28). A separate path
from the development benchmark: how AISEF could ever support a generalization statement. No workload is selected or
exposed here; nothing is sealed. RFC §28 and §30 are the authority; RFC §33 defers the machinery until "a workload that
has never been tuned against exists" — that trigger is an owner decision this plan prepares for, not one it takes.

## 1. Two paths that never meet

| | development / regression (LedgerLock) | external validation (future sealed workloads) |
|---|---|---|
| purpose | does the current kernel regress on a known workload? | does the kernel deliver on workloads it was never tuned against? |
| classification | `DEVELOPMENT_REGRESSION`, permanently | `SEALED` → `EVALUATING` → `EXPOSED` → `DEVELOPMENT`, one way |
| may back a generalization claim | never (mechanically refused) | only with ≥ N independently sealed workloads and stated sample sizes |
| plan revisions | allowed (they make it development) | none between preregistration and results |
| recorder | `validation/qualification/p10.py` (Cycle 1) | the cohort machinery of WP-2.10.1 |

## 2. Workload selection rules

1. **Never tuned against.** No AISEF plan, prompt, profile, kernel change or defect fix may have been made with the
   workload in view. Provenance is recorded: who authored the requirements, when, and an attestation that no AISEF
   member saw them before sealing.
2. **Authored outside the kernel's history.** The requirements are written by a party without access to the AISEF
   repository, or drawn from a corpus fixed before the workload's selection date.
3. **Independent domain.** Not a ledger, hash chain or CLI-over-JSONL variant; at least two domains across the set
   (for example a stateless data transformation, a small HTTP service — which would justify `http_route`, a
   file-format converter).
4. **Provable with the qualified probe kinds only.** Every acceptance criterion must be expressible as a contract of a
   kind whose calibration exists at the sealing digest; a workload needing an unqualified kind is not eligible until
   that kind is qualified — the gap matrix method is applied at sealing, and the result is part of the preregistration.
5. **Hidden oracle.** An independent acceptance oracle (as W1's, written from the requirements alone) exists before
   sealing and is hashed into the preregistration; it is never edited after results are read.
6. **Size bound.** Stories and criteria within the limits the plan-quality policy names, so runs complete inside the
   preregistered budget.

## 3. Preregistration (written and hashed before any run)

The `EvaluationCohort` record of RFC §28 with `frozen_inputs` covering:

- kernel identity: semantic candidate SHA, aisef2 tree, wheel digest;
- workload identity: requirements hash, baseline repository SHA, hidden-oracle digest;
- plan policy: the `StaticPlanAdmissionEngine` digest and the admission result of the frozen plan;
- execution profile, content-addressed: interpreter digest, git digest, every probe id and digest, scanner and
  runner identities, limits — the `runspec_hash`;
- prompts catalogue digest;
- model route: a fixed model identifier with an ATTESTED preflight fingerprint (provider, endpoint, declared model,
  route, client, fingerprint); a routing alias that may change the underlying model per call (such as a "combo"
  route) is `OPAQUE` and **bars sealing** (RFC §28.5);
- run count and the delivery threshold (for example "≥ 2/3 delivery complete");
- the `PlanQualityPolicy` thresholds (RFC §29) — absent thresholds mean `plan_quality_verdict = NOT_CLAIMED` for the
  whole cohort, decided now, not after results;
- metrics and their derivations (all projections of the journal).

`preregistration_hash` binds the above; the record is committed before the first run.

## 4. Lifecycle (RFC §28), mechanised in WP-2.10.1

- `SEALED`: preregistration committed; no run yet; `aggregate_min_grade` ≠ `OPAQUE` or the seal is refused.
- `EVALUATING`: the preregistered runs execute; no framework modification between runs; a change to any
  `frozen_inputs` hash invalidates completed runs and requires a fresh preregistration.
- reading results sets `results_read_at`; any change to a `frozen_inputs` hash **after** that timestamp transitions
  the cohort to `EXPOSED` with `exposed_reason` recorded — mechanised, not a policy.
- `EXPOSED` workloads may be run for regression and never back a generalization claim.
- `DEVELOPMENT` is terminal; LedgerLock starts and stays there.

Every transition is a typed refusal or a typed move; there is no administrative override.

## 5. Minimum evidence before any generalization statement

- at least **3 independently sealed workloads** across **≥ 2 domains**, each with **≥ 3 preregistered runs**;
- the statement names the sample size per workload and in total (RFC §28.6), the kernel identity, the profile identity
  and the plan-quality policy under which it holds;
- a statement is about *this* capability set on *these* workloads; `assurance_kernel` and `delivery` remain distinct
  fields (RFC §27, Q6 conclusions).

Fewer than that: no statement, only per-workload delivery verdicts.

## 6. Capability identity requirements for a sealed run

- every capability in the RunSpec is `VERIFIED` (digest) or `ATTESTED` (preflight); `OPAQUE` anywhere bars sealing;
- enforcement levels enter `runspec_hash`; runs under `PARTIAL` are not compared with runs under `FULL`;
- the same `runspec_hash` across the cohort's runs; a different one is a different cohort.

## 7. Model / profile freezing

- fixed model identifier, fixed provider endpoint, fixed client version (binary digest), fixed prompts catalogue;
- a preflight per run measuring the declared model id, limits and tool-calling behaviour → fingerprint; a fingerprint
  drift between runs is recorded and demotes comparability (the runs are not one cohort);
- the Cycle-1 development profile (OpenCode 1.18.31 over `9router/mycombo`) is a per-call routing alias and is
  therefore not eligible for a sealed cohort; it remains fine for `DEVELOPMENT_REGRESSION`.

## 8. What this plan does not do

- It selects no workload and exposes none; it seals nothing.
- It makes no claim about generalization; AISEF currently supports none (RFC §30).
- It does not weaken the regression path: LedgerLock stays `DEVELOPMENT_REGRESSION` and is rerun in Cycle 2 only to
  answer the regression question.
