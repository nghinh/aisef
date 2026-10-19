# V2.1 candidate evidence — derived records (B-03, campaign 9)

`validation/v21/candidate_evidence.py` re-derives the round's generated records **at this tree** (commit `8fae707b`,
after the campaign-9 mutation record) into a directory **outside the repository**, compares each with its **sealed**
record, and never overwrites a sealed record. The full set and its `CANDIDATE-MANIFEST.json` (per-record sha256,
sealed sha256, and the exact differing JSON paths) are kept here only as a binary archive — a `.tar.gz`, because a
candidate JSON copy left loose in the tree is miscounted by the record generators' own tree scans.

- Archive: `CANDIDATE-EVIDENCE-8fae707b.tar.gz` (reproduce: `python3 -P validation/v21/candidate_evidence.py OUT` at `8fae707b`).
- Nothing sealed changed. These are candidate copies for the owner's re-seal decision, read by no release gate.

## Generated (7/7), diffs vs the sealed v2.0 / cycle-2 records

Almost every differing path is a **code-identity digest or hash** that moved because the fix window changed the code
(`aisef2_tree`, the four probe `digest`s, `plan_hash`, `proposal_digest`, per-spec `probe_digest` / `semantic_hash` /
`spec_hash_id`, engine/kernel digests), plus non-semantic guard `seconds`. Those are expected and carry no meaning
beyond "the code is the 2.1 code". The substantive deltas the owner should weigh when deciding to re-seal:

| Record | Paths | Substantive delta beyond digests |
|---|---:|---|
| `v2/P2-STATIC-ADMISSION.json` | 2 | none (engine/result digests only) |
| `v2/Q0-CHECKER-CALIBRATION.json` | 3 | **checker count 52 → 54** (two checkers added in the window) |
| `v2/release/AUTHORITY-INVENTORY.json` | 2 | **rows 245 → 247**; `summary.ACTIVE_V2_AUTHORITY` changed (two new authority-bearing sites) |
| `v2/cycle2/C2-P5-ACCEPTANCE.json` | 60 | **`verdict` re-derived** at the 2.1 tree; approvals-file commits/blobs; rest digests/seconds |
| `v2/cycle2/P5-PLAN-V2.2-PROPOSAL.json` | 60 | none (all identity digests / spec hashes) |
| `v2/cycle2/PLAN-V2.2-CORRECTION-1.json` | 60 | `moved_obligations[*].product_proof_spec_id` recomputed; rest digests/hashes |
| `v2/cycle2/K-NOWORK-001-REHEARSAL.json` | 12 | bound-file digests, before/after `plan_hash`, `kernel_digest` (rehearsal re-ran both kernels) |

## NOT generated (owner-decided, by rule)

- `C2-ORCHESTRATION-CONFORMANCE-REPAIR.json` — historical; `c2_orchestration_repair --write` refuses on 2.1. The 2.1
  behaviour changes are named instead in `CONFORMANCE-RULING.json` (`v21_conformance_ruling.py`).
- `release/S2-MUTATION.json` (+ the P2/P6/cycle-2-P1 2.0 mutation records) — never regenerated; superseded for 2.1 by
  `v2.1/MUTATION.json` (campaign 9). The 2.0 records stay history.
- The frozen 2.0 Q5 corpus — never edited; 2.1 changes are traced in `v21_q5_changes.py`.

Written 2026-10-20.
