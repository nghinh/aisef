# CYCLE-2 IMPLEMENTATION PLAN (PROPOSAL)

**Status.** Planning artefact (owner's "CLOSE CYCLE-1 / PREPARE CYCLE-2 ARCHITECTURE ONLY", 2026-09-28). Nothing in this
plan is authorized; no Cycle-2 production code exists. The scheduling source of truth is
[`cycle2-manifest.json`](cycle2-manifest.json); this document explains it.

## 1. The immutable Cycle-1 baseline

Cycle 2 builds on top of Cycle 1 and rewrites nothing of it. The baseline, verified read-only on 2026-09-28 and to be
bound by WP-2.0.1's freeze manifest:

| item | identity |
|---|---|
| semantic candidate | `7114177834da5a7e4a0fc2c7f8fa9d067e0abaa2` |
| aisef2 tree | `4d6081940f5b9dae47439f73f0157161e028d804` |
| closing commit of Cycle 1 | `503b3a22f872c212d237e70f03aaba7d83f54d67` (local suite 4762 OK; CI 36383314097 7/7) |
| RFC normative digest / freeze table | `84f3a85a…` / `d71b958b…` |
| effective lineage | APPROVAL → V2-001 → V2-002 → V2-003 → V2-005 → V2-006 (V2-004 was proposed, not applied) |
| F1–F11 | 11 PASS, 0 ratchet violations |
| P4 / P5 / P6 seals | `921c119e…` / `d06d4ae5…` / `93620298…` |
| P7 acceptance; Q0–Q3 summary; P7-FINDING-001 correction | `c7144a23…`; `5f036872…`; `3da6d2a6…` |
| P8 acceptance; Q4 DIFFERENTIAL / SUBJECT | `4f6e0b25…`; `2a076192…` / `4f99a4df…` |
| P9 acceptance; Q5 REPRODUCTION / SUBJECT | `7c508afc…`; `5f0ba2f7…` / `10c887a1…` |
| P10 LEDGERLOCK-REGRESSION / WORKLOAD | `5a0d2bdd…` / `d4321104…` |
| V1 evidence baseline; W0; V1 product tree | `4bb690ff…`; `a14c2f58…`; `4359f347…` |
| migration table (P6-sealed) | `157b46f6…` |
| the Cycle-1 probe | `probe.python_callable` @ `1961e84d…` |
| run histories | P7 151, P8 45, P9 11, P10 19 entries |

## 2. Objective and the measured need

Expand ProductProof coverage while preserving every Cycle-1 assurance property. The need is measured, not assumed:
the capability-gap matrix classifies LedgerLock's 77 criteria as 10 supported, 53 unsupported by kind (17
`cli_invocation`, 32 `process_effect`, 4 `file_artifact`), 8 unsupported by observable, 6 invalid because they name
tests; 28 carry an ambiguity flag that only the plan author can resolve. Cycle 2 addresses the 61 kind/observable gaps
with four probe designs, and leaves the 6 test-named criteria and the 28 ambiguities to explicit owner decisions
(DECISION-1..6 in the manifest).

## 3. Phases (P0–P10) and what each produces

- **C2-P0 Freeze / registry / reference fixture.** WP-2.0.1 binds the baseline above and generalises the Cycle-1 plan
  validator. WP-2.0.2 adds the probe registry catalogue and six Q0 checkers, each with a known-bad fixture. WP-2.0.3
  writes a stdlib reference implementation of LedgerLock from the frozen requirements with named mutants — the
  falsifiability fixture; never AISEF output, never the developer's candidate.
- **C2-P1 `file_artifact`.** Reads the git object store at the revision; `exists`, `content`, `grep_count`; `FULL`
  enforcement with the weakest path named. Closes the 4 prohibitions.
- **C2-P2 `cli_invocation`.** A harness that runs a module of the revision as `__main__` with argv, a workspace and
  pre-steps; the protocol on a dedicated channel (DESIGN-CHECK-1); four classes. Closes the 17 CLI criteria.
- **C2-P3 `process_effect`.** A closed scenario vocabulary over a fresh workspace; three classes; the `fault` step only
  after DECISION-2. Closes the 32 effect criteria (30 without the fault step).
- **C2-P4 `python_callable` extensions.** `returns_bytes`, `equals`, `workspace`, `raises` attrs, at a new digest
  (or a second probe id, DECISION-6). Closes the 8 observable gaps.
- **C2-P5 Contract authoring aid.** Turns PLAN-V2.1's criteria into V2 contracts with recorded decisions, compiles and
  statically admits them, and produces a LedgerLock PLAN-V2.2 proposal for owner approval — a new development
  experiment under RFC §30, never a change to the P10 record.
- **C2-P6..P8 Qualification.** Q0–Q3, Q4, Q5 on the exact Cycle-2 candidate, harnesses reused, extended where the
  qualification plan says.
- **C2-P9 LedgerLock rerun.** DEVELOPMENT_REGRESSION, answering "can the expanded kernel execute more of the known
  workload correctly?"; verdicts separate; NOT_CLAIMED without DECISION-5.
- **C2-P10 External-validation machinery.** The cohort lifecycle and profile freezing as machinery, with no workload
  selected (RFC §33 trigger is an owner decision).

## 4. Preservation of the core invariants (per proposal)

| invariant | how every proposed kind preserves it |
|---|---|
| Requirement Authority | contracts still compile only from approved requirements (`require_approved`); no probe reads a requirement |
| Semantic Determinism | verdict = f(revision SHA, ProductProofSpec, capability identity): the hidden-authority matrix removes, binds or declares every other input |
| Independent Evidence | the implementer's and verifier's checkouts remain two witnesses; `file_artifact` reads the object store so both read the same bytes |
| Typed Ownership | probes emit `Observation` kinds only; `classify_failure` routes them; no new owner, code or reason |
| Reproducible Qualification | new probes are capability identities in the RunSpec; Q5 re-executes them; comparability requires equal tuples |
| Immutable Provenance | `semantic_hash` binds probe id, digest and the whole stimulus/observable; the Cycle-1 digest's hashes are untouched |
| No Prose As Control State | every observable is a typed shape; `detail` (traces, digests) is never read |
| Memory Is Context, Never Evidence | no probe reads a cache, a previous evaluation or a recording |
| No Developer Artefact Executed At Parent | workspaces and pre-steps are approved contract content; the contract rule refuses test names; admission at the parent runs the same harness-owned probes |

Especially: the verdict does not depend on wall-clock timing (no clock in verdict paths; Q0 checker), checkout
metadata (object store for content; `-B` and a fresh prefix for execution), stale caches (fresh evaluation directory),
developer test layout (Q1 invariance extended), ambient environment (allowlist + pinned locale/hash seed/TZ), or
previous execution residue (per-evaluation directory, range residual accounting).

## 5. What is explicitly not in Cycle 2

- No change to the control plane, journal, projections, admission engines, orchestration path or invariants. If a
  probe needs one, STOP and bring it to the owner as its own package.
- No Architecture Exception (the F5 report found none needed); if implementation finds one, STOP and draft it.
- No holdout workload; no cohort; no generalization statement.
- No LedgerLock retune of the Cycle-1 record; a V2.2 plan is a proposal for a new experiment.
- No `http_route` probe.

## 6. Estimated shape (for scheduling, not commitment)

| phase | packages | dominant risk |
|---|---|---|
| C2-P0 | 3 | the reference implementation must be independently correct (its own acceptance, mutants red) |
| C2-P1 | 1 | none material |
| C2-P2 | 2 | DESIGN-CHECK-1 on Windows (§9.4 equivalence) |
| C2-P3 | 2 | scenario vocabulary completeness vs closure; DECISION-2 |
| C2-P4 | 1 | DECISION-6 (digest change re-calibrates everything) |
| C2-P5 | 2 | 28 ambiguous criteria need decisions; six test-named need DECISION-3 |
| C2-P6..P8 | 3 | harness extensions must not weaken Q0–Q5 |
| C2-P9 | 1 | live provider availability (typed NOT_REACHED remains legitimate) |
| C2-P10 | 2 | RFC §33 trigger; alias routes cannot attest |
