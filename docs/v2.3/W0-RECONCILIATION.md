# AISEF v2.3 — W0 reconciliation of counts (45 → 104 defects, 135 → 147 IDs)

Owner direction 2026-11-21: reconcile the updated counts against the earlier 45 / 135 with explicit provenance for every added entry; no duplicates, no scope inflation.

## 1. Defects: 45 → 104 (106 rows)

* **#1–#45** — the W0 source audit (`wi04fhzj6`, 15 subsystem lanes), unchanged in number; adjudicated at the W0 closure.
* **#46–#104 (59)** — the W0-closure gap-fill (`wtyqyc77n`, 5 lanes), run because the first audit's completeness critic named these surfaces **unread** (CODE-AUDIT, last section). Each row below gives its lane key, source lane and the existing checklist item(s) it folds into (`maps_to`, from the adjudication pass `wbe8sbl46`).
* **106 rows** — #6 and #39 are each one defect split into a/b because their fixes land in two waves; not new defects.
* **Severity:** the five gap-fill P1 candidates were adversarially verified (`wbe8sbl46` VerifyP1); all were reproduced and downgraded to P2. P1 stays 3 (#1 REL-GOV-01, #2 E5, #3 EVID-COUPLING-01).

| CA# | gap key | source lane | folds into existing item(s) | dup-of |
|---|---|---|---|---|
| 46 | G1-1 | authority checkers | INV-MUTATION-AUTHORITY, F5, EVID-COUPLING-01, ROADMAP-2.2 F1, WP-0.5 | — |
| 47 | G1-2 | authority checkers | INV-MUTATION-AUTHORITY, WP52-001 | — |
| 48 | G1-3 | authority checkers | INV-MUTATION-AUTHORITY, WP52-001 | — |
| 49 | G1-4 | authority checkers | INV-MUTATION-AUTHORITY, B-03c, V21-74 | — |
| 50 | G1-5 | authority checkers | INV-MUTATION-AUTHORITY, FINDING-WIN-OSKILL-001 | — |
| 51 | G1-6 | authority checkers | INV-MUTATION-AUTHORITY, B-03c | — |
| 52 | G1-7 | authority checkers | WP-0.4, COMPAT-MATRIX | — |
| 53 | G1-8 | authority checkers | WP-5.5, RFC §4 | — |
| 54 | G1-9 | authority checkers | WP-3.5 | — |
| 55 | G1-10 | authority checkers | V2-003, RFC §9.3 | — |
| 56 | G1-11 | authority checkers | RFC §9.2 | — |
| 57 | G1-12 | authority checkers | B-03c | — |
| 58 | G1-13 | authority checkers | INV-MUTATION-AUTHORITY | — |
| 59 | G1-14 | authority checkers | INV-MUTATION-AUTHORITY, WP-0.4 | — |
| 60 | G2-1 | lineage + cohort | V21-41, V21-80, V21-77 | V21-41(a) |
| 61 | G2-2 | lineage + cohort | V21-77, V21-78, V21-79 | — |
| 62 | G2-3 | lineage + cohort | V21-80, G6 | — |
| 63 | G2-4 | lineage + cohort | V21-41 | — |
| 64 | G2-5 | lineage + cohort | C2-P10, WP-2.10.1, COH-ADV-15 | — |
| 65 | G2-6 | lineage + cohort | C2-P10, WP-2.10.1 | — |
| 66 | G2-7 | lineage + cohort | C2-P10, WP-2.10.1 | — |
| 67 | G3-1 | plan / admission | RFC §12, B6b | — |
| 68 | G3-2 | plan / admission | RFC §14, C5 | — |
| 69 | G3-3 | plan / admission | EVID-COUPLING-01, F5 | — |
| 70 | G3-4 | plan / admission | RFC §12, F5, COMPAT-MATRIX | — |
| 71 | G3-5 | plan / admission | RFC §12, B4 | — |
| 72 | G3-6 | plan / admission | RFC §12, E6, FORMAT-4 | — |
| 73 | G3-7 | plan / admission | RFC §14, V2-005 | — |
| 74 | G3-8 | plan / admission | V21-13, K-NOWORK-001, CODE-AUDIT #11 (same dual-encoding class) | — |
| 75 | G3-9 | plan / admission | RFC §29 | — |
| 76 | G3-10 | plan / admission | RFC §13 | — |
| 77 | G3-11 | plan / admission | F5, CODE-AUDIT #33 (same attestation-gap class) | — |
| 78 | G3-12 | plan / admission | PROBE-BIND-1 | — |
| 79 | G4-1 | quality / anti-gaming | WP-5.2, RFC §15.2, RFC §24 | — |
| 80 | G4-2 | quality / anti-gaming | WP-5.1, WP-5.4, RFC §15.0, D1 | — |
| 81 | G4-3 | quality / anti-gaming | WP-5.1, E5, CODE-AUDIT #2 (family) | — |
| 82 | G4-4 | quality / anti-gaming | WP-5.3, RFC §15.1 | — |
| 83 | G4-5 | quality / anti-gaming | RFC §15.0, RFC §15.3 | — |
| 84 | G4-6 | quality / anti-gaming | WP-5.2, WP-5.3 | — |
| 85 | G4-7 | quality / anti-gaming | WP-5.3, E5 | — |
| 86 | G4-8 | quality / anti-gaming | RFC §15.1 | — |
| 87 | G4-9 | quality / anti-gaming | RFC §15.0 | — |
| 88 | G4-10 | quality / anti-gaming | WP-5.2, WP-5.3 | — |
| 89 | G4-11 | quality / anti-gaming | INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE, RFC §15.0 | — |
| 90 | G4-12 | quality / anti-gaming | SS-96, WP-5.1 | — |
| 91 | G4-13 | quality / anti-gaming | WP-5.1 | — |
| 92 | G4-14 | quality / anti-gaming | WP-5.4 | — |
| 93 | G4-15 | quality / anti-gaming | V2-005, FORMAT-4, EVID-COUPLING-01 | — |
| 94 | G4-16 | quality / anti-gaming | RFC §17, WP-5.4 | — |
| 95 | G5-1 | secondary overlaps | G1, V21-02, DEVELOPER-CONFINEMENT-GAP-001 | — |
| 96 | G5-2 | secondary overlaps | G1, V21-15 | — |
| 97 | G5-3 | secondary overlaps | G1 | — |
| 98 | G5-4 | secondary overlaps | H-RETRY-001, G4 | — |
| 99 | G5-5 | secondary overlaps | G4, CODE-AUDIT #2 | — |
| 100 | G5-6 | secondary overlaps | V21-02, D1 | — |
| 101 | G5-7 | secondary overlaps | V21-02, V21-04, V21-72, PM-8 | — |
| 102 | G5-8 | secondary overlaps | V21-03, KA-09, D1 | — |
| 103 | G5-9 | secondary overlaps | CODE-AUDIT #23 (same class) | — |
| 104 | G5-10 | secondary overlaps | EVID-COUPLING-01, CODE-AUDIT #3 | — |

26 of 59 gap-fill defects fold into an existing checklist ID (same capability, now with a concrete defect and acceptance criterion); the rest map to the owning capability named in `maps_to` (invariant, work package or roadmap item). **No gap-fill defect adds a capability outside the v2.3 plan.**

**Duplicate scan.** Every gap-fill defect was compared with #1–#45 by cited file. 17 pairs share a file; each was read and judged **distinct** (different line range, root cause and fix):

| gap | vs | why distinct |
|---|---|---|
| #62 (lineage `--parent` accepts a superseded child) | #18, #41, #42 (`run.py` finally / kernel_digest order / no_progress coupling) | different function and failure |
| #68 (§14 drift attribution never performed) | #18, #41, #42 | different function and failure |
| #72 (admission event never emitted) | #11 (lifecycle encoded twice) | different events and fix |
| #77 (no mutation targets for `plan/obligation.py`) | #14, #15 (Option C ruling check / no test), #32 (stale `require_armed` record) | different targets |
| #95, #96, #97 (tripwire: size/encoding skip, composite needles, marker false-positive) | #19 (tripwire blind to the git object store) | different scan defects of the same module |
| #100 (anchor reasons embed sealed observables) | #4 (within_s excluded), #24 (redundant recomputation) | different defects |
| #103 (RuffScanner raises untyped errors) | #23 (mkdir without exist_ok), #25 (OCR identity self-declared) | different defects |

The one real duplicate found, **#60 ≡ V21-41(a)** (same site `lineage.py:264`), is recorded as such and is fixed once (W3 L3-PLATFORM).

## 2. Backlog IDs: 135 → 147

| Added | Count | Provenance | Scope effect |
|---|---|---|---|
| V21-61b, V21-65b, V21-42b, V21-71b | 4 | NEEDS_SPLIT findings of the ID-quality lanes: each is the undecided or unfixed **residual** of an existing V21 row whose fixed part is now ALREADY_FIXED | none (same backlog item, finer) |
| V21-72 → V21-72a + V21-72b | +1 | critic: one ID spanned two waves/lanes | none (split) |
| C3b | 1 | plan W4 names "C3b bounded owner-ratified no_progress control"; the checklist had only C3a (DAG R1) | already in the plan |
| REL-GOV-01, EVID-COUPLING-01, BUILD-REPRO-01, KERNEL-COUPLING-01, EVID-PLATFORM-01, EVID-SCALE-01 | 6 | RISK-REGISTER rows (measured W0 risks), tracked as checklist rows so each has a wave and acceptance | tracking only — release-integrity work the owner ruling already requires |
| **Total** | **+12** | 135 + 4 + 1 + 1 + 6 = **147** | |

The original reconciliation produced 136 dispositions for 135 unique IDs (V21-44 appeared twice); it was merged into one row. No ID was removed; IDs whose status changed (e.g. V21-74/V21-87 → NOT_APPLICABLE by the delegated ruling) keep their row with the reason.

