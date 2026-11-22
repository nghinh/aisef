# Q0-1 — the run.py:693 evidence-contract transition: option mapping and red-before/green-after

Owner ruling 2026-11-22 §D: *"select and present the option that maintains an effective live v2.3 B1 check while
retaining exact v2.2 replay. Provide its mapping to Q-a/Q-b/Q-c and red-before/green-after evidence before committing
the incompatible evidence-contract transition."* This file is that presentation; it is committed BEFORE the commit
that carries the `run.py:693` hunk.

## 1. Mapping (E5-READINESS §3.2(B))

| Option | What it is | Live v2.3 B1 check | Exact v2.2 replay | Verdict |
|---|---|---|---|---|
| **Q-a** | a round-v2.3 `b1_bindings` clean: a moved B1 source is accepted ONLY while that target is MEASURED in round v2.3 at the live bytes | **yes** — the acceptance reads the committed round mutation record live, per target | **yes** — the v2.2 path and the known-bad fixture contract are byte-identical (measured below) | **SELECTED** |
| Q-b | an append-only round-v2.3 Q0 record | it is the container Q-a runs in (`validation/v23/q0_round.py`, built in W1b) — alone it does not check B1 against the live tree | yes | part of the frame, not the B1 check |
| Q-c | defer the hunk to W2b L2-RECORD | **no** — no live check; gate 5 and the R1 row would need amending | yes | rejected |

The selection criterion is the owner's own sentence: only Q-a keeps a live, version-aware, fail-closed B1 check.

## 2. The mechanism (commit carrying this file)

* `validation/v2/b1_bindings_check.py` — `problems(man, targets=None, *, kernel=None)`:
  * `kernel=` lets a calibration fixture bind its round's OWN aisef2 tree (the manifest's), so the Q0 known-bad
    stays byte-identical across kernel edits; the live CLI path is unchanged.
  * `_v23_accepts(t, e)` — round v2.3 only (`version_forward.ROUND`): a target whose source moved since the manifest
    froze is accepted ONLY while its newest COMMITTED round-v2.3 mutation entry measured exactly the live source
    (the entry's LF digest equals the live file's) and the entry is clean under the mutation rules. No entry, an
    uncommitted newest entry (I7), a digest mismatch, any open problem or a broken round record keeps the target
    red. The manifest `closure-evidence/v2/v2.2/B1-RISK-MANIFEST.json` is never re-pinned (OD-B1B stays the owner's,
    as does OD-Q0-1-W1B; seq 13 forbids deciding either here).
* `validation/v2/checker_calibration.py` `_b1_bindings` — the known-bad passes
  `kernel=man["frozen_bindings"]["aisef2_kernel_tree"]`; the clean filter (`kernel ` lines) is unchanged.

## 3. Red-before (measured on this tree, before the E5 commit)

With the E5 working-tree edit present and NO round mutation entries for run.py (scratchpad capture
`w1b/qa-red-before.json`, session 845c9f11): `b1_bindings` clean under `in_round("v2.3")` is red with
`"aisef2/app/run.py::<target>: aisef2/app/run.py moved since the manifest froze"` for the manifest's run.py targets,
and the known-bad observed stays `"kernel e865d65c80e2 is not the frozen 000000000000"` — byte-identical to the
committed v2.2 Q0 record's entry (verified: `observed == committed record: True`).

## 4. Green-after

* **Mechanism level (committed with this file):** `tests/v23/test_v23_mutation_round.py::QaAcceptance` —
  red before (no entry), red outside the round, GREEN with a committed clean entry at the live digest, and red again
  on each fail-closed edge (digest mismatch, uncommitted newest entry, open problems, a broken round record). All
  measured green.
* **Tree level:** lands with the W1b targeted measurement (the 25 `run.py` B1 targets + the 11 `story_runner`
  targets + `run.py::execute` + `_Stages.advance`); until that record is committed, `b1_bindings` stays truthfully
  red under the round. Scope and measured cost are written to the W1 report before the run (W1-DESIGN §10).

## 5. Unchanged

The v2.2 replay (`validation/v23/replay_v22.py`) still passes byte-identically: nothing here edits the v2.2 Q0
record, its fixture, the expected reason, or the manifest. The v2.2-round `problems()` path (no `in_round`) behaves
exactly as before — the acceptance is reachable only inside round v2.3.
