# AISEF V2 — Cycle-1 implementation plan

**Status: plan only. P0 has not started.** No V2 code exists. No file under `aisef/` or `closure-evidence/`
(other than the new `closure-evidence/v2/` approval record) is modified.

<!-- GENERATED:architecture-baseline BEGIN — from cycle1-manifest.json; do not hand-edit -->

**Architecture baseline — frozen.**
[`docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md`](../../architecture/AISEF-V2-ARCHITECTURE-RFC.md), approved at commit `2fe672c`. Approval record
[`closure-evidence/v2/AISEF-V2-RFC-APPROVAL.json`](../../../closure-evidence/v2/AISEF-V2-RFC-APPROVAL.json), content-addressed `c23191bd71bc299d…`, amended by [`AISEF-V2-RFC-AMENDMENT-V2-001.json`](../../../closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-001.json) (`eaeb3130e2eefe9a…`, changes F2); [`AISEF-V2-RFC-AMENDMENT-V2-002.json`](../../../closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-002.json) (`eb1b9f1108fcf68a…`, changes F5); [`AISEF-V2-RFC-AMENDMENT-V2-003.json`](../../../closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-003.json) (`b8f618a235e7f508…`, changes F1, F2, F5); [`AISEF-V2-RFC-AMENDMENT-V2-005.json`](../../../closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-005.json) (`9b8636a22875c142…`, changes F1); [`AISEF-V2-RFC-AMENDMENT-V2-006.json`](../../../closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-006.json) (`a06c6a67929e3fdf…`, changes F5).
Current RFC normative digest `84f3a85aa39e94e2…`; freeze-table digest `d71b958b5a060784…` (originally `8f0d522d9db0322c…` / `c4d9895f921b707c…`). **F1–F11 frozen.**

<!-- GENERATED:architecture-baseline END -->

This document compiles the approved RFC into work packages. **It introduces no architecture concept, no control
semantic and no scope beyond RFC §32.**

Companion documents: [dependency graph](AISEF-V2-CYCLE1-DEPENDENCY-GRAPH.md) ·
[traceability matrix](AISEF-V2-CYCLE1-TRACEABILITY.md) · [evidence plan](AISEF-V2-CYCLE1-EVIDENCE-PLAN.md) ·
machine-readable [`cycle1-manifest.json`](cycle1-manifest.json).

---

## 1. Shape of the cycle

**37 packages: 33 implementation (P0–P6) + 4 qualification (P7–P10).** F1–F11 coverage: **11/11**, minimum 4
packages per frozen item.

**Scheduling source of truth.** [`cycle1-manifest.json`](cycle1-manifest.json) is the **only** source of
scheduling facts. Every table below marked *GENERATED* is rendered from it by
[`validation/v2/plan_validate.py`](../../../validation/v2/plan_validate.py) and verified by `--check`; editing one
by hand fails CI (PLANDEP-5). The dependency graph and the traceability matrix are generated in full.

**Phase barriers are strict.** A package is runnable only when its declared dependencies are complete **and** the
preceding phase is evidence-complete — all of its packages done, all required artefacts present, all exit checks
green. Parallelism is permitted **within a phase only**. The critical path is a consequence of that ordering, not
a goal: correctness and evidence ordering have priority over elapsed time.

<!-- GENERATED:phase-table BEGIN — from cycle1-manifest.json; do not hand-edit -->

| phase | packages | barrier | exit condition |
|---|---|---|---|
| **P0** Freeze / conformance scaffolding | 5 | — | architecture baseline mechanically identifiable and protected |
| **P1** Semantic core | 4 | P0 | polarity, NEG-1/2/3, compiler --check, hash stability, satisfaction mutation |
| **P2** Probe + admission | 5 | P1 | CAL-1, CAL-2, subject/harness separation, no provider call before admission, PRE_SATISFIED, layout invariance |
| **P3** Journal / projections | 5 | P2 | unknown-required refusal, time never folded, incremental == full, reference models, projection mutation |
| **P4** Story / run transaction | 6 | P3 | RUN-1, RUN-2, crash cases, range emptiness, budgets as projections |
| **P5** Engineering quality / invariants | 5 | P4 | TEST-1, TEST-2, collection-cause classification, vacuity three-valued, I-IX armed and uncontainable |
| **P6** Orchestration integration / V1 migration | 3 | P5 | single authoritative path, generated migration table, six removal proofs |
| **P7** Q0-Q3 | 1 | P6 | all four rungs green on the exact candidate |
| **P8** Q4 differential | 1 | P7 | 100000/100000, 0 unexplained |
| **P9** Q5 reproduction | 1 | P8 | reproduction green, tools re-executed |
| **P10** LedgerLock regression | 1 | P9 | verdicts separate, no generalization claim, no cohort sealed |

<!-- GENERATED:phase-table END -->

**Critical path under barriers:**

<!-- GENERATED:critical-path BEGIN — from cycle1-manifest.json; do not hand-edit -->

**Length 32 packages.**

`WP-0.1` → `WP-0.4` → `WP-0.2` → `WP-0.3` → `WP-0.5` → `WP-1.1` → `WP-1.2` → `WP-1.3` → `WP-1.4` → `WP-2.1` → `WP-2.2` → `WP-2.3` → `WP-2.4` → `WP-2.5` → `WP-3.1` → `WP-3.3` → `WP-3.4` → `WP-3.5` → `WP-4.1` → `WP-4.3` → `WP-4.6` → `WP-5.1` → `WP-5.3` → `WP-5.4` → `WP-5.5` → `WP-6.1` → `WP-6.2` → `WP-6.3` → `QP-7` → `QP-8` → `QP-9` → `QP-10`

<!-- GENERATED:critical-path END -->

**No package may exit on "the code works."** Every exit criterion in the manifest names an artefact, a green
adversarial test, or a mechanical check.

---

## 2. What is being built on top of, not rebuilt

V1 leaves real infrastructure that cycle 1 **extends** rather than duplicates. This materially reduces scope and
is the reason 37 packages is a cycle rather than a programme:

| existing | reused by |
|---|---|
| `validation/mutate.py` + `validation/mutation-targets.json` (871 mutants, 59 targets) | every package with a mutation target |
| `aisef/invariants.yaml` + `aisef/control/invariants.py` + `tests/hardening/test_invariants_registry.py` — a registry **with a rendered-doc sync check already in the `--check` shape** | WP-5.5 |
| `tests/hardening/model.py`, `differential.py`, `policy_v2.py` — an independent reference-model harness with an AST no-import check | WP-3.5, QP-7, QP-8 |
| `validation/p12_run_100k.sh`, `p12_integrity.py`, `p12_coverage_report.py` | QP-8 |
| `tests/hardening/test_fault_matrix.py` (102 cells) | QP-7 |
| `validation/w0_qualification.py`, `p19_freeze.py` | QP-7, freeze plumbing |

New code lives under `aisef2/`, `validation/v2/` and `tests/v2/`. **`aisef/` is not modified during P0–P5.**
It is touched only in P6, and only to remove authority — never to add it.

---

## 3. Phases

### P0 — Freeze / conformance scaffolding (5 packages)

Strictly sequential: **`WP-0.1` → `WP-0.4` → `WP-0.2` → `WP-0.3` → `WP-0.5`.**

`WP-0.1` freeze manifest · `WP-0.4` V1 evidence migration guard · `WP-0.2` generated enum catalog with a
`--check` twin · `WP-0.3` F1–F11 conformance checks · `WP-0.5` known-bad fixtures calibrating every Q0 checker.

`WP-0.1` is the only package permitted before the guard, because it establishes the freeze identity the guard
protects. **Every other package — implementation and qualification — has `WP-0.4` as an explicit transitive
ancestor**, and check C proves it. Checker calibration (`WP-0.5`) closes the phase, so no later package can run
while any Q0 checker is still uncalibrated. A checker never observed failing is a cheap, fast, invisible source of
false assurance — the gap the adversarial review found.

### P1 — Semantic core (4 packages)

`WP-1.1` contract + `SubjectAbsence` + `ContractApproval` · `WP-1.2` `ProductProofSpec` + pure compiler +
`semantic_hash` + `--check` · `WP-1.3` two-axis outcomes + `ContractSatisfaction` · `WP-1.4` `Owner` taxonomy +
frozen routing tables.

`WP-1.3` carries the correction that matters most: **planning must route on `ContractSatisfaction`, never on
raw `BehaviorVerdict`**, and NEG-1/2/3 are its acceptance tests. A static check asserts that no planning module
imports `BehaviorVerdict` for routing at all — the defect is made structurally unavailable, not merely tested
against.

### P2 — Probe + admission (5 packages)

`WP-2.1` probe protocol + enforcement · `WP-2.2` the two calibration contracts · `WP-2.3` `PlanObligation` +
`StaticPlanAdmissionEngine`/`Result` · `WP-2.4` `StoryAdmission` · `WP-2.5` `PRE_SATISFIED` / `PLAN_DRIFT`.

`WP-2.2` implements the **contrast** rule, and CAL-1 is its acceptance test: a `MUST_NOT_HOLD` probe that always
returns `REFUTED` must be rejected. `WP-2.3` asserts CAL-2 — that no plan-freeze path requires
`SpecFalsifiabilityEvidence`.

### P3 — Journal / projections (5 packages)

`WP-3.1` envelope + append-only writer · `WP-3.2` format compatibility · `WP-3.3` fold engine + from-scratch
oracle · `WP-3.4` the six control-critical projections · `WP-3.5` their independent reference models.

**`WP-3.4` and `WP-3.5` are deliberately separate packages** and `WP-3.5` carries an authorship-independence
constraint: the reference models must be written from the RFC text, not from the projection source, and are
mechanically barred from importing it. Merging them would destroy the only control against a projection and its
model being wrong in the same way.

### P4 — Story / run transaction (6 packages)

`WP-4.1` `StoryScope` ordered ownership · `WP-4.2` measured range emptiness · `WP-4.3` `RunScope` + lease +
sentinel · `WP-4.4` `RunSpec` + identity grades · `WP-4.5` budgets as projections · `WP-4.6` deterministic
disposal and interruption closers.

`WP-4.3` implements correction D: the **run lease is the outer boundary and is released last**. RUN-1 and RUN-2
are its acceptance tests. `WP-4.5` proves the absence of side retry counters — SS-64 and D-006 are its
reproducers.

### P5 — Engineering quality / invariants (5 packages)

`WP-5.1` typed test execution · `WP-5.2` relevance · `WP-5.3` candidate-side vacuity · `WP-5.4` adequacy
assembly · `WP-5.5` invariants I–IX.

`WP-5.1` carries correction C. Its acceptance tests include the four collection-cause cases, and a global
assertion that **no "did not run ⇒ developer" edge exists anywhere in the gate**. `WP-5.5` must demonstrate an
invariant violation *escaping* a `try/except` boundary — an invariant a `catch` can swallow is not an invariant.

### P6 — Orchestration integration / V1 migration (3 packages)

`WP-6.1` generated migration table · `WP-6.2` orchestration wiring · `WP-6.3` old-path removal proofs.

`WP-6.1` generates the V1 proof-mode mapping and **never infers `SubjectAbsence`** — unmapped cases are reported
for human declaration rather than defaulted, because inferring absence semantics from polarity is defect A2.
`WP-6.3` is the package that proves no dual authority survives: six explicit removal proofs, and the audit fails
closed on any authority it cannot enumerate.

### P7–P10 — Qualification

`QP-7` Q0→Q3 · `QP-8` Q4 fresh 100 000-trace differential · `QP-9` Q5 real-execution reproduction · `QP-10`
LedgerLock regression only.

**LedgerLock is permanently `DEVELOPMENT`.** `QP-10` may reveal regressions; its result may not be cited as a
generalization claim, and the verdict recorder asserts this. **No sealed cohort is started in cycle 1.**

---

## 4. Parallelism

**Within a phase only — never across a barrier.** Parallel work additionally requires all four of: frozen
interfaces already implemented; disjoint write scopes; disjoint evidence scopes; and no dependency on another
package's unverified semantics.

The sets below are **derived** from the manifest: packages in the same phase that reach the same scheduling level.
They are candidates; each still has to satisfy the four conditions above before it actually runs in parallel.

<!-- GENERATED:parallel-sets BEGIN — from cycle1-manifest.json; do not hand-edit -->

| phase | level | packages that may run in parallel |
|---|---|---|
| P3 | 16 | `WP-3.2`, `WP-3.3` |
| P4 | 20 | `WP-4.2`, `WP-4.3` |
| P4 | 21 | `WP-4.4`, `WP-4.5`, `WP-4.6` |
| P5 | 23 | `WP-5.2`, `WP-5.3` |

<!-- GENERATED:parallel-sets END -->

`WP-3.5` may never run in parallel with `WP-3.4`: it depends on it, and it must be authored independently from the
RFC text rather than from the projection source.

**Aggressive parallel scheduling is not reintroduced.** Behaviour-aware parallel scheduling remains deferred
(RFC §33); `FAM-SCHEDULER` is the family parallelism amplifies, and cycle 1 does not take that risk.

---

## 5. Stop rules

Implementation **STOPS immediately and reports** if:

1. F1–F11 appear internally contradictory in actual implementation;
2. a required RFC state cannot be represented without adding semantics;
3. an invariant cannot be mechanically enforced as specified;
4. V1 frozen evidence would need mutation;
5. a new P0/P1 architecture-level defect is found.

**Architecture is never repaired autonomously.** A stop produces an `ARCHITECTURE_EXCEPTION` record naming the
frozen item, the contradiction, a concrete reproducer, why the implementation cannot conform, the evidence
compatibility impact and a proposed replacement — and waits. No exception is approved by default.

Normal implementation defects do **not** invoke the stop rule: a bug is fixed, a missing test is added, and a
verifier already required by the RFC is added.

---

## 6. Implementation risks

Ordered by likelihood of actually biting.

1. **The probe taxonomy is an open RFC question (§36) and `WP-2.1` implements one probe kind.** If a second kind
   — `cli_invocation`, `http_route`, `file_artifact`, `process_effect` — cannot be expressed within the
   F5-frozen protocol, that is a **frozen-semantic contradiction and a STOP**, not a refactor. This is the
   highest-likelihood stop-rule trigger in the cycle. Mitigation: prototype a second kind against the protocol
   early inside `WP-2.1`, before the rest of P2 builds on it.
2. **Windows range emptiness (`WP-4.2`).** V1 already established Windows as a real constraint, not a
   formality. Job-object emptiness may be unavailable or unreliable in the CI image. Mitigation: exercise the
   Windows path in CI from the first commit of the package, not at the end.
3. **Reference-model authorship independence (`WP-3.5`) is a process constraint, not a mechanical one.** The
   AST no-import check is mechanical; "written from the RFC, by a different author, without reading the
   projection" is not enforceable by CI. This is a stated weakness: the control against a projection and its
   model failing identically is partly procedural.
4. **Q4 sequencing (`QP-8`).** A fresh 100 000-trace differential takes hours, and any kernel change invalidates
   it. A defect found in `QP-9` forces a re-run of `QP-8`. Mitigation: `QP-7` must be genuinely green, including
   mutation, before `QP-8` starts — which is what the ladder already requires.
5. **Two trees during P1–P5.** `aisef2/` exists alongside `aisef/` and is not wired until P6. The risk is that
   the transitional state is mistaken for dual authority. It is not: `aisef2/` is unreachable from any
   production path until `WP-6.2`, and `WP-6.3` proves the old path is gone afterwards.
6. **Collection-cause classification (`WP-5.1`) depends on the runner's structured output** and on a resolvable
   dependency manifest. Available for Python; for other targets the rule's own fallback applies — owner
   `INTEGRATION`, never `DEVELOPER`. Safe, but it means non-Python targets get weaker classification than the
   RFC's examples suggest.
7. **37 packages with real exit criteria is a large cycle.** The discipline that no package exits on "code
   works" is correct and it is also the main schedule pressure. The first thing to cut if the cycle runs long is
   named in RFC self-review C: the candidate-side vacuity control (`WP-5.3`), which is explicitly a secondary
   measurement whose `INDETERMINATE` never blocks.

---

## 7. Architecture exceptions discovered during planning

**None.**

One sequencing question was examined and resolved without an exception: `WP-2.4` must assert that no
`provider/request` precedes story admission, but the journal arrives in P3. The assertion runs in P2 against the
RFC's `JournalWriter` interface with an **in-memory test double**, and is re-verified against the durable
journal by `WP-6.3` ("every control decision is journal-backed"). A test double is not a second authoritative
path and adds no semantics; the owner's prohibition on dual authoritative paths is satisfied because the double
never exists in a production path.

The probe taxonomy (risk 1) is an open implementation question the RFC already records in §36, not a
contradiction — but it is the one most likely to become one.

### 7.1 Finding during plan correction — `PLAN-FINDING-001`

Running the full suite while validating this plan **modified a V1 closure-evidence file**:
`tests/hardening/test_state_model.py` rewrites `closure-evidence/hardening/state-model-results.json` on every
run, and its content depends on test order — this run dropped the entire `conformance` section (+1/−129 lines).

It was restored with `git checkout`, and its blob verified equal to the file's last intended commit `612efce`
(`da27db6b`). **No mutated version was ever committed.**

This is a normal implementation defect in V1 *test* code, not an architecture exception. It matters to the plan
because **`WP-0.4`'s guard would fail every CI run the moment it lands.** The fix is therefore recorded inside
`WP-0.4` as a discovered prerequisite: redirect that write to a non-evidence scratch path in the same change that
introduces the guard, with a new adversarial test — *a full-suite run leaves every file under `closure-evidence/`
outside `v2/` byte-identical* — and a matching exit criterion. The change touches V1 test code only; never V1
evidence and never `aisef/`.

It is also direct evidence that the guard is necessary: until `WP-0.4` lands, the V1 evidence that the freeze
record binds by hash can be silently rewritten by an ordinary test run.

### 7.2 Finding during P0 exit verification — `PLAN-FINDING-002`

`WP-0.4` lists `.githooks/pre-commit (extend)` among its expected files, but the repository has never had a
`.githooks/` directory or any committed hook — there was nothing to extend. The hook was **created**: it runs the
same detective check CI runs (`v1_evidence_guard.py --check`) at commit time, and `.gitattributes` keeps it LF on a
Windows checkout. Tests prove a staged V1 change is refused and a V2 change is not.

It is opt-in per clone (`git config core.hooksPath .githooks`), so it adds no guarantee: the enforcement grade
stays **DETECTIVE**, enforced in CI. A plan wording error, not an architecture exception.

---

## 8. Final self-review

### A · Coverage — **PASS**

Every F1–F11 item maps to implementation packages and to evidence artefacts. Computed from the manifest:
**11/11 covered**, minimum 4 packages per item (F10), maximum 10 (F3, F11). The mapping is in the
[traceability matrix](AISEF-V2-CYCLE1-TRACEABILITY.md) §1, which is derived from the manifest rather than
hand-written, with a `--check` twin in `WP-0.1`.

### B · Ordering — **PASS** (direction **and** completeness)

**Corrected after owner review.** The original check proved only that no dependency points into a later phase.
That does not prove that all required dependencies exist, and three were missing: `WP-0.4` was not an ancestor of
the rest of P0; no phase barrier stopped phase N+1 starting before phase N was evidence-complete; and `WP-6.2`
could be wired without `WP-2.4` or `WP-2.5`. The prose also claimed `WP-0.5` could run straight after `WP-0.1`
while the graph said otherwise.

Now checked by [`validation/v2/plan_validate.py`](../../../validation/v2/plan_validate.py), five checks:

| check | proves |
|---|---|
| A `dependency_direction` | no dependency points into a later phase |
| B `phase_barrier_completeness` | every phase's barrier is its predecessor, **and** independently that no package is runnable before its predecessor phase completes |
| C `guard_ancestry` | every package other than `WP-0.1` and `WP-0.4` has `WP-0.4` as an **explicit** transitive ancestor |
| D `orchestration_semantics` | `WP-6.2` explicitly requires `WP-2.5` and effectively requires all of P2–P5 |
| E `qualification_chain` | `QP-7` < `QP-8` < `QP-9` < `QP-10`, with `QP-7` gated on P6 being complete |

Each has a negative fixture (PLANDEP-1..4) that removes one required edge and is proven to fail, plus PLANDEP-5 for
document drift. Results are in [`AISEF-V2-CYCLE1-DEPENDENCY-GRAPH.md`](AISEF-V2-CYCLE1-DEPENDENCY-GRAPH.md) §6.

One case remains a deliberate design choice rather than a violation: `WP-2.4` (P2) asserts that no
`provider/request` precedes story admission, while the journal lands in P3. The P2 assertion runs against the
RFC's `JournalWriter` interface with an in-memory test double and is re-verified against the durable journal by
`WP-6.3`. A test double introduces no semantics and never exists in a production path. It is recorded in the
manifest's `additional_constraints` so it is a scheduling fact with a source, not prose.

### C · Scope — **PASS**

Every package maps to RFC §32 or is directly necessary to verify it:

| §32 item | packages |
|---|---|
| 1 contracts, specs, probes, two-axis | `WP-1.1`–`WP-1.4`, `WP-2.1`, `WP-2.2` |
| 2 admission | `WP-2.3`–`WP-2.5` |
| 3 journal, projections, oracle, reference models | `WP-3.1`–`WP-3.5` |
| 4 transaction, sentinel, identity | `WP-4.1`–`WP-4.6` |
| 5 invariants armed and uncontainable | `WP-5.5` |
| 6 Q0 static integrity, Q1 invariance, Q3 fault injection | `WP-0.1`–`WP-0.5`, `QP-7` |
| addition: `EngineeringTestAdequacy` | `WP-5.1`–`WP-5.4` |
| addition: `ContractApproval` | `WP-1.1` |
| §31 migration; wiring required for §32 to exist at all | `WP-6.1`–`WP-6.3` |
| §27 ladder; §30 LedgerLock | `QP-8`, `QP-9`, `QP-10` |

**Nothing was added to cycle 1.** The deferred list in RFC §33 is unchanged: sensitivity testing, sealed-cohort
machinery, toolchain identity, behaviour-aware parallel scheduling, branch-coverage relevance and journal
compaction all remain out.

### D · Simplification — **PASS**

New code lives in `aisef2/{product,probe,plan,journal,runtime,control,quality,invariants,orchestrate}`,
`validation/v2/` and `tests/v2/`. Each module answers a named RFC obligation; none is speculative.

Two packages deserve their justification stated, since neither appears verbatim in the owner's phase lists:

- `WP-4.4` (`RunSpec` + identity grades) — required by RFC §18.1's begin order ("resolve/freeze `RunSpec`") and
  by §23. Without it `RunScope` cannot start and F9 has no implementation.
- `WP-0.2` (generated enum catalog) — required by RFC §27's Q0 row, which demands catalogs that are fail-closed
  in both directions, and by F2/F3/F6/F7 conformance.

No new subsystem exists that an RFC section does not oblige.

### E · V1 safety — **PASS**

- `WP-0.4` records the sha256 of every file under `closure-evidence/` (excluding the new `v2/` directory) and
  rejects any commit or run that would modify one, including the voided W0 record and the external-validation
  directories.
- `aisef/` is **not modified during P0–P5**. It is touched only in P6, and only to remove authority.
- All cycle-1 evidence is written under `closure-evidence/v2/`.
- No V1 artefact is migrated, moved or rewritten. The V1 proof-mode migration (`WP-6.1`) **reads** V1 plan data
  and emits a new generated table; it writes nothing into V1 paths.

### Stop-rule check at planning time

No stop-rule condition is met. F1–F11 showed no internal contradiction while being compiled into packages; every
required RFC state has a representation; every invariant has a named mechanical enforcement; no V1 evidence
needs mutation; and no new P0/P1 architecture-level defect was found.

**Architecture exceptions discovered: none.**
