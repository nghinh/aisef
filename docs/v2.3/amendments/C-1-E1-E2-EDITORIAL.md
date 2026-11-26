# C-1 editorial amendments E1 + E2 (owner ruling 2026-11-26 "A2′ Closure, Cohort Defect Disposition and RC Preparation" §5)

**Authority:** owner ruling 2026-11-26 §5, verbatim: "C-1 E1/E2 documentation amendments: APPROVED. Approve the two
non-behavioral editorial clarifications through dated amendments. Preserve the existing schema and acceptance
behavior; specifically, a FAILED event with empty `detail` remains valid. Do not introduce a new required field or a
stricter schema under an editorial change."

**Nature:** documentation-only. The frozen design file `docs/v2.3/drafts/FORMAT-4-DESIGN-DRAFT.md` stays
byte-identical to its C-1 freeze pin (blob `41506829d227d3380c2095b59813810807b28991`); this dated amendment is the
clarification record, exactly as A1/A2′ are. No schema, validator, table or test changes; `TABLE_DIGEST` and every
committed pin are untouched.

## E1 — §3.1 `symbol_of`: "nothing else reads data" read against the section's own RUN bullet

The frozen §3.1 text says the payload-dependent split is `story/admitted -> story/admitted:accepted |
story/admitted:refused` and that "nothing else reads data" — while the same section's `RUN` bullet keys the run
table by `run/interrupted:first | run/interrupted:abandoning`, a second payload-dependent split (it reads
`data["abandoned"]`, replacing `terminal_state.py`'s `(type, abandoned)` tuple key).

**Clarified reading (the only internally consistent one, and the one implemented):** `symbol_of` has exactly TWO
payload-dependent splits — `story/admitted` on `data["admitted"]` and `run/interrupted` on `data["abandoned"]` —
and "nothing else reads data" means nothing besides those two. The shipped `aisef2/journal/transitions.py` already
implements both splits; behavior is unchanged by this clarification.

## E2 — §4.3 `detail` is prose-only

§4.3's rule R-SEGMENT ends "`FAILED` => either, and `detail` says which". Clarified: `detail` is prose for humans —
no validator parses it, no acceptance rule conditions on its content, and **a `FAILED` event with empty `detail`
remains valid** (the owner ruling states this expressly). "Says which" is a writer convention, not a schema
obligation. Per the ruling, no new required field and no stricter schema are introduced; if non-empty `detail` is
ever to be required, that is a future owner schema decision, not this amendment.

## Status

`docs/v2.3/drafts/C-1-AMENDMENT-PROPOSALS.md` carries E1/E2 as proposals; this record closes them as APPROVED
(editorial) with the proposals text left as written (append-only history).
