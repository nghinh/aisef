# Phase 11 — registry: every invariant PROVEN

After F6 the registry is 45 PROVEN / 4 PARTIAL / 1 MISSING. The registry's own rule (docs/INVARIANTS.md): PROVEN when
deterministic, model and fault tests exist and are green; the rule tests refuse a PROVEN that cites a red reproducer or
is claimed by an OPEN member of the frozen set. Phase 11 supplies the missing evidence — a kernel fix where the
evidence exposes one — and promotes; nothing is promoted by editing a status.

| invariant | what is missing | what Phase 11 adds |
|---|---|---|
| INV-E.2 (validity ≠ latest / exists / SHA match) | no fault or model evidence of its own; it is proven piecewise by INV-A.2 / E.1 / P.1 cells | fault cell **FM-E-07** (Evidence, INJECTED): three records that each look valid by the old readings — the LATEST record at another candidate, an EXISTING legacy (schema-1, candidate-only) record, a record whose SHA MATCHES but whose tree digest differs (the D-035 shape) — and the gate scores none of them, stating stale / legacy with the pointer. Test `test_fault_matrix.py::TestEvidenceFaults::test_latest_exists_and_sha_match_each_score_nothing`; model evidence: the model's fresh-verdict decision (`test_state_model.py::TestKernelModel`). |
| INV-H.1 (no-op semantics) | evidence exists (2 deterministic, FM-D-01, FM-D-06) but was never re-examined after D-032 closed (F2) | verify every cited test is green, cite the model's T6/T6′ no-op scenarios; promote. |
| INV-N.2 (environment identity on every sandboxed result) | no fault evidence; and `_run_docker` returns its TIMEOUT and docker-invocation-error results WITHOUT `image`/`image_id` — a timed-out tool run cannot say which image it ran in | kernel: the image identity is computed once per run and every `SandboxResult` of the docker provider carries it (timeout, OSError, infra exit, success; the "image unavailable" refusal carries the name and an empty digest, stated). Fault cell **FM-N-03** (Tool, INJECTED: the sandboxed run times out / docker cannot be invoked → the record still names image and digest). Test `test_fault_matrix.py::TestToolFaults::test_a_failed_sandboxed_run_still_records_its_environment_identity`. |
| INV-Q.2 (owner decision = new epoch with deterministic invalidation) | no fault evidence composed end to end | compound cell **FM-C-13** (Compound, INJECTED: the owner amends a story's acceptance criteria after a failed attempt): the branch written for the old criteria is dropped and recorded, the contract note carries the new fingerprint, evidence of the old epoch is not fresh for the new one, and the readiness approval over the stories index is STALE. Test `test_compound_faults.py::TestCF13OwnerArbitrationIsAnEpoch`, composed from the existing pieces (`run._drop_branch_written_for_other_criteria`, `identity.fresh`, `ApprovalStore.status`). |
| INV-S.1 (replay contract) | MISSING — nothing exists | Phase 17 (`P16-evidence-schema-P17-replay-contract.md`); FM-X-01 and FM-C-09 turn GREEN there; the registry's 50th PROVEN lands with it. |

Definition of done: registry 49 PROVEN / 0 PARTIAL / 1 MISSING after this phase (50 / 0 / 0 after Phase 17); every
cited test exists and is green; the fault matrix gains FM-E-07, FM-N-03, FM-C-13 GREEN; the registry rule tests,
render, full suite, ruff, Linux + Windows CI green. No status is edited without the evidence row above.

## Closure record (2026-09-17, branch hardening/systematic-v1)

- **INV-E.2** — fault cell FM-E-07 (`TestEvidenceValidityFaults`): the LATEST record at another candidate, an
  EXISTING legacy record and a record whose SHA MATCHES over a different tree each score nothing; the stale one is
  named with its reason; the control record written under the exact identity is accepted. Model evidence: P3 (no
  pass on foreign evidence). PROVEN.
- **INV-H.1** — every cited test re-run green (2 deterministic, FM-D-01, FM-D-06); model evidence P5 (a no-op never
  terminates on stale evidence). PROVEN.
- **INV-N.2** — kernel: `_run_docker` computes the image identity once per run and every result carries it (the
  timed-out and the un-invokable results had none — RED before, GREEN after, `TestSandboxIdentityFaults`); the
  "image unavailable" refusal carries the name and an empty digest, stated. Fault cell FM-N-03. PROVEN.
- **INV-Q.2** — compound cell FM-C-13 (`TestCF13OwnerArbitrationIsAnEpoch`): amended criteria drop the branch, the
  contract note carries the new fingerprint, old-epoch evidence is not fresh, the readiness approval is STALE; the
  within-epoch control is fresh. Model evidence: P4 (the baseline stays within the epoch). PROVEN.
- **INV-S.1** — MISSING until Phase 17.

Registry 49 PROVEN / 0 PARTIAL / 1 MISSING. Fault matrix: FM-E-07, FM-N-03, FM-C-13 added GREEN (P11) —
70 GREEN / 2 RED (FM-X-01, FM-C-09 — INV-S.1, Phase 17) / 0 NEEDS_TEST, 72 scenarios. Registry and matrix rule tests green. Full suite / ruff / CI: full suite 3392 passed / 20 skipped / 0 expected-red / 0 failed (1444 subtests, 568 s), ruff clean; Linux + Windows CI recorded on the commit that carries this phase (see the F6 record for the Windows reaper cause it also fixes).

CI on 9e8fc77 (run of 2026-09-16, PR #6): 7/7 green — Linux 3.11–3.14, Windows 3.11, lint, wheel. Windows is green with the unified snapshot walker, the POSIX-only zombie collection and positive session ownership all in place: this family is re-qualified on both operating systems.
