# C-1 — FORMAT-4 DESIGN FREEZE (owner ruling 2026-11-26, recorded 2026-11-26)

**Authority:** OWNER RULING "ACCELERATED EXECUTION, C-1 FREEZE AND ORDER-TABLE" §1, issued through the owner
channel 2026-11-26: "Approve freezing the exact design." Recorded here verbatim as to identities; this record
adds nothing to the ruling and grants nothing beyond it.

## The frozen objects (verified against committed bytes at HEAD b0809b7b before recording — no mismatch)

| Object | Identity (ruling) | Verified 2026-11-26 |
|---|---|---|
| `docs/v2.3/drafts/FORMAT-4-DESIGN-DRAFT.md` | git blob `41506829d227d3380c2095b59813810807b28991` | MATCH (`git rev-parse HEAD:…`) |
| same, file sha256 | `313f803547c518618386f991c5f8036ebf3173800a78c5f2d388f73ead4b5141` | MATCH (`git show HEAD:… \| shasum -a 256`) |
| `docs/v2.3/drafts/FORMAT-4-FREEZE-PACKAGE.md` | git blob `2c81d92669823e860f34ed5dd01df7a3e673b012` | MATCH |

## Scope of the freeze (ruling §1)

The documented Q1–Q10 resolutions, the versioned event vocabulary, the transition table, the reservation and
stream fields, the signing envelope, and the formats 1–3 compatibility requirements. **V21-57 remains KEEP.**
Post-freeze changes require a dated, scoped amendment — never a silent design edit. The two frozen files above
are now change-controlled under this rule.

## Released lanes (ruling §1, effective immediately)

L2-JOURNAL (`transitions.py`, `format4.py`, projections, required tests); L2-ACCOUNTING (E2/E4 reservation +
stream integration); L4-PARALLEL (C5); L4-RESUME (G6); other ORCHESTRATION work whose declared prerequisites
are satisfied.

## Conditions carried with the release

- The FORMAT-4 **production flip** requires an independent adversarial review of the transition invariants and
  ALL mandatory negative controls; single-author engineering sign-offs do not substitute (ruling §1; the Q8
  shared-engineer caveat in the freeze package is thereby answered: independent review is mandatory at the flip).
- Single-writer file ownership and historical format compatibility are preserved (plan §2 schedule; design §6).
- Pacing (design §12 / A2 §12): the flip also waits on the A2 installation/signing gates (ruling §5).
