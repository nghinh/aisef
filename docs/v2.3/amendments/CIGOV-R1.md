# CIGOV-R1: the release-decision ledger under the released-evidence guard

**Status: DECIDED 2026-11-22 — option (a), byte-prefix variant. See the Decision section.**

This came out of the L1-CIGOV review: finding CIGOV-R1, HIGH, reproduced. This file decides nothing on its own. Until
a decision is recorded at the end, the guard stays as it is and fails closed.

## The conflict

The released-evidence rules:

- **CR-13 / CT-6** (COMPATIBILITY-MATRIX) and **CODE-AUDIT #52 (b)**: every `closure-evidence/v2/**` blob at `399b775f`
  (and at tag `v2.2.0`) is unchanged at HEAD. Additions are allowed.
- `validation/v23/released_evidence_guard.py` enforces this by git blob id. It runs after the suite on all 6 unit legs
  (`tests.yml`). The suite checks it again in `HistoryKept`.

The ledger rules:

- **CR-14 / CT-5**: entries seq 1–12 of `RELEASE-DECISIONS.json` stay value-identical. New entries take seq 13 and
  up, strictly increasing.
- The ledger is `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json`. Its blob is `94c8ab6b` at `v2.2.0`, at
  `399b775f` and at the lane head.
- `validation/v2_release_gate.py` (`DECISIONS_REL`) reads that path.
- `docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT.md` appends seq 13 to it.

Two owner appends are planned:

1. ROUND-AUTH seq 13, needed for W1 exit gate 3.
2. The v2.3.0 `PRODUCTION_PUBLISH` entry that `v2_release_gate.py` needs before it allows publishing.

Each of them keeps CT-5 and fails CT-6 and #52 (b). The guard step goes red on every unit leg and `HistoryKept`
fails. On a release tag, the `tests` gate in `release.yml` then blocks `publish`.

COMPATIBILITY-MATRIX §5 STOP (c) covers "any immutable record or ledger entry would need editing". An append does not
edit an entry, but it does edit a blob that CR-13 makes immutable. So the choice belongs to the owner or the
integrator. A lane cannot fix this by itself.

## Measured

- **Review reproduction at lane head `19c83028`**, with the real tag and the real branch base. Trace sha256
  `6472277b24d6163d715e4d370362f83d5599a81f6c28b9ebdc4746166dc40658`, kept in scratch and not committed.
  - After the drafted seq 13 append, `--check` exits 1 and names the ledger for both pins.
  - `HistoryKept` fails, and `LedgerAppendOnly` (CT-5) passes.
  - With a further seq 14 `PRODUCTION_PUBLISH` entry, `v2_release_gate`'s ledger problems become `[]`, but the guard
    and `HistoryKept` still fail.
- **Pinned in the tree**, both in `tests/v23/test_v23_released_evidence_guard.py`:
  - `test_cigov_r1_open_a_ct5_append_to_the_ledger_fails_the_guard` records the conflict as measured.
  - `test_no_ledger_rewrite_passes` lists what every decision must keep red: an entry edited, the entries reordered,
    an entry deleted, another key changed.
- **Not measured:** an append is a D1 delta under a mutation COPY root (`validation/v23/impact.py` D1). Which F5
  targets it moves, if any, was not measured. Both options below touch that root.

## Not options

- An allowlist entry or an exception for the ledger path.
- Moving `BRANCH_BASE`. `RELEASED` pins the same blob, so this changes nothing.
- Skipping or conditioning the guard step, or `HistoryKept`, on the seq 13 commit.

## Option (a): a typed append-only rule for the ledger in the guard

This applies to the ledger only. Every other `closure-evidence/v2` path keeps blob identity.

For each protected revision R (`RELEASED`, `BRANCH_BASE`), the guard compares R with HEAD, and also with the working
tree. It passes only if all of these hold:

1. HEAD parses as a JSON object. Its keys, and every top-level value except `entries`, equal R's.
2. HEAD's `entries[:n]` equal R's `entries` by value, where n is the number of entries at R. A stricter variant, which
   is recommended: R's text up to the end of its last entry is also a byte prefix of HEAD's text. The seq 13 draft
   says "byte-identical", and CR-13 says "byte-immutable".
3. Every appended entry is a whole JSON object. Every seq is an int, and the seqs are strictly increasing.
4. Deleting or renaming the ledger still fails.

What changes and what does not:

- The CT-6 and #52 (b) texts are amended to name this rule for this one file.
- `v2_release_gate.py` and the seq 13 draft stay unchanged.

Tests (throwaway repo). The red-before is the current pin.

- These pass: a prefix-keeping append of one entry, and of two entries.
- These fail:
  - an entry from 1 to n edited, reordered or deleted;
  - a top-level key changed;
  - a re-indentation of the old entries (under the byte variant);
  - a non-integer or non-increasing seq;
  - a non-ledger edit.
- The same commit inverts `test_cigov_r1_open_…` and updates `HistoryKept`.

Cost: the guard and its tests only, in `validation/v23/` and `tests/v23/`. No COPY-root file changes, and no mutation
target changes.

## Option (b): the v2.3 ledger moves to a new file

- `v2_release_gate.py` (`DECISIONS_REL`) and the seq 13 draft change.
- The rule that the latest ruling wins has to span both files.
- It needs owner authority, because charter G9 names the ledger.
- The new file's location has to respect the placement rules (Amendment A2).

## Recommendation (not a decision)

Option (a) with the byte-prefix variant:

- It keeps one ledger and every reader of it.
- The old entries stay byte-identical.
- Every other released record keeps blob identity.

Option (b) needs more owner authority, and it changes the release gate.

## Until decided

- **#52 (b) / CT-6** is marked **CONFLICTS WITH CT-5**, not DONE.
- If the owner's seq 13 commit lands before a decision, the guard step on all 6 unit legs and `HistoryKept` go red.
- If a v2.3.0 tag is pushed before a decision, the `tests` gate blocks `publish`.

## Decision

**Option (a), byte-prefix variant. 2026-11-22.**

Authority: integrator ruling, taken under — and constrained by — the owner ruling of 2026-11-22 (pasted verbatim by
the owner into the working session; preserved outside the public repository), whose §D rules: "CIGOV-R1 must preserve
ledger authority and mandatory CI enforcement, with no authorization cycle or silent bypass." The same ruling's §B
approves the exact seq-13 R6 proposal (canonical ruling digest
`a1469d009f2456fccde4a3b3e3706a993e6bc1524b5512873dbcefe6ccec01f0`), which appends to the ledger at its charter-G9
path, so option (b) — moving the ledger — would move the approved draft's bytes and its digest, and is foreclosed.

How option (a) meets §D, point by point:

- **Ledger authority preserved**: the ledger alone may grow by whole appended entries (CT-5 / CR-14's own released
  contract); its protected bytes up to the final protected entry stay a byte prefix, every other top-level value stays
  equal, and entry seqs stay strictly increasing integers.
- **Mandatory CI enforcement preserved**: the guard step still runs on all 6 unit legs and in `HistoryKept`; it is
  never skipped or conditioned; every other `closure-evidence/v2/**` path keeps git-blob identity; an edit, reorder,
  deletion, re-indentation, rename or non-monotonic append of the ledger stays red (the full red set is pinned in
  `tests/v23/test_v23_released_evidence_guard.py::ThrowawayRepo.test_no_ledger_rewrite_passes` and
  `test_deleting_or_renaming_the_ledger_still_fails`).
- **No authorization cycle**: the rule is static and structural — `ledger_problems` reads no authority field and no
  content of the ledger it checks beyond shape, prefix and seqs, so no entry can authorize its own acceptance.
- **No silent bypass**: there is no allowlist and no exception — the one path is named in the module and checked by a
  stricter typed rule, with the red-before kept as the superseded pin
  (`test_cigov_r1_open_a_ct5_append_to_the_ledger_fails_the_guard`, measured at `57f9d68e` and in every CI run to it).

Implemented in `validation/v23/released_evidence_guard.py` (`ledger_problems`, ledger-aware `committed_changes`,
`ledger_worktree_problems`); CT-6's row and CODE-AUDIT #52 (b) are amended to name this rule for this one file. The
`v2_release_gate.py` reader and the seq-13 draft are unchanged, exactly as option (a) requires.
