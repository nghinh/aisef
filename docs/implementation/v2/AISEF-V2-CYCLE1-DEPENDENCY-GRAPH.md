# AISEF V2 — Cycle-1 dependency graph

Derived from [`cycle1-manifest.json`](cycle1-manifest.json). Ordering is validated mechanically: **no package
depends on a package in a later phase** (checked, 0 violations).

---

## 1. Phase chain

```
P0 ──► P1 ──► P2 ──► P3 ──► P4 ──► P5 ──► P6 ──► P7 ──► P8 ──► P9 ──► P10
 │      │      │      │      │      │      │      │      │      │      │
 │      │      │      │      │      │      │      │      │      │      └ LedgerLock regression only
 │      │      │      │      │      │      │      │      │      └ Q5 real-execution reproduction
 │      │      │      │      │      │      │      │      └ Q4 100k differential
 │      │      │      │      │      │      │      └ Q0→Q3
 │      │      │      │      │      │      └ orchestration + V1 migration
 │      │      │      │      │      └ engineering quality + invariants
 │      │      │      │      └ story/run transaction
 │      │      │      └ journal + projections
 │      │      └ probe + admission
 │      └ semantic core
 └ freeze + conformance scaffolding
```

## 2. Package graph

```
P0  WP-0.1 freeze manifest
     ├─► WP-0.2 enum catalog (--check)
     ├─► WP-0.4 V1 evidence guard          [parallel]
     └─► WP-0.3 F1–F11 conformance ──► WP-0.5 Q0 checker calibration

P1  WP-0.3 ──► WP-1.1 contract/SubjectAbsence/approval
               └─► WP-1.2 spec + compiler + semantic_hash
                     └─► WP-1.3 two-axis + ContractSatisfaction
                           └─► WP-1.4 Owner taxonomy + routing

P2  WP-1.3 ──► WP-2.1 probe protocol + enforcement
               └─► WP-2.2 calibration (contrast rule)
                     └─► WP-2.3 PlanObligation + StaticPlanAdmission
                           └─► WP-2.4 StoryAdmission
                                 └─► WP-2.5 PRE_SATISFIED / PLAN_DRIFT

P3  WP-1.4 ──► WP-3.1 event envelope + append-only writer
               ├─► WP-3.2 format compatibility      [parallel]
               └─► WP-3.3 fold engine + oracle
                     └─► WP-3.4 six control projections
                           └─► WP-3.5 reference models   [different author]

P4  WP-3.4 ──► WP-4.1 StoryScope ordered ownership
               ├─► WP-4.2 measured range emptiness   [parallel]
               └─► WP-4.3 RunScope + lease + sentinel
                     ├─► WP-4.4 RunSpec + identity grades
                     ├─► WP-4.5 budgets as projections   (also ◄ WP-3.4)
                     └─► WP-4.6 disposal + interruption   (also ◄ WP-3.2)

P5  WP-1.4 ──► WP-5.1 typed TestExecution
               ├─► WP-5.2 relevance                  [parallel]
               └─► WP-5.3 candidate-side vacuity      [parallel]
                     └─► WP-5.4 adequacy assembly  (◄ WP-5.2, WP-5.3)
                           └─► WP-5.5 invariants I–IX  (also ◄ WP-3.4)

P6  WP-2.3 ──► WP-6.1 generated migration table
     WP-6.1 + WP-4.6 + WP-5.5 ──► WP-6.2 orchestration wiring
                                   └─► WP-6.3 old-path removal proofs

P7+ WP-6.3 ──► QP-7 (Q0→Q3) ──► QP-8 (Q4) ──► QP-9 (Q5) ──► QP-10 (LedgerLock)
```

## 3. Critical path — 19 packages

```
WP-0.1 → WP-0.2 → WP-0.3 → WP-1.1 → WP-1.2 → WP-1.3 → WP-1.4
       → WP-3.1 → WP-3.3 → WP-3.4 → WP-4.1 → WP-4.3 → WP-4.6
       → WP-6.2 → WP-6.3 → QP-7 → QP-8 → QP-9 → QP-10
```

Note what is **not** on it: the whole of P2 (probe + admission) and most of P5 run off the critical path,
because P4 depends on the projections (`WP-3.4`) rather than on admission. P2 must still finish before `WP-6.2`
can wire the orchestration, so it has slack but not unlimited slack.

The two longest-pole items in practice are `WP-4.2` (Windows range emptiness, off the critical path but
historically the slowest thing in this project) and `QP-8` (hours of wall clock, and invalidated by any
subsequent kernel change).

## 4. Ordering constraints beyond the graph

| constraint | why |
|---|---|
| `WP-0.4` lands before any package writes | the V1 evidence guard must exist before there is anything to guard against |
| `WP-0.5` lands before any Q0 checker is trusted | an uncalibrated checker is invisible false assurance |
| `WP-3.5` is authored **after and independently of** `WP-3.4` | a reference model written from the projection source is not independent evidence |
| `WP-2.1` prototypes a second probe kind before P2 proceeds | risk 1: if a second kind does not fit the F5-frozen protocol, that is a STOP, and it should be found early |
| `WP-4.2` exercises Windows in CI from its first commit | Windows is a real constraint, established in V1 |
| `QP-7` fully green before `QP-8` starts | a Q4 run invalidated by a later fix costs hours |

## 5. Resolved sequencing question

`WP-2.4` (P2) must assert that no `provider/request` precedes story admission, but the journal arrives in P3.
The assertion runs in P2 against the RFC's `JournalWriter` **interface** with an in-memory test double, and is
re-verified against the durable journal by `WP-6.3`. The double never exists in a production path, so this is
not a dual authoritative path and adds no semantics.
