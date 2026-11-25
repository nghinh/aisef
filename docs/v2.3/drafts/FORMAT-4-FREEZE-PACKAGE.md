# AISEF v2.3 — C-1 FREEZE PACKAGE for FORMAT-4 (owner directive 2026-11-26 P1)

**Date:** 2026-11-26. **Prepared by:** integrator (lane L2-JOURNAL engineer).
**The freeze is an owner act: the package prepares it.** Nothing here synthesizes an owner signature;
the owner issues the freeze line of §5 (or does not).

---

## 1. The freeze object

| Field | Value |
|---|---|
| Path | `docs/v2.3/drafts/FORMAT-4-DESIGN-DRAFT.md` (430 lines, §13 measurements appended 2026-11-26) |
| git blob sha1 (post §7.1 pointer fix, 2026-11-26) | `41506829d227d3380c2095b59813810807b28991` |
| file sha256 | `313f803547c518618386f991c5f8036ebf3173800a78c5f2d388f73ead4b5141` |
| Working tree vs HEAD | clean — file on disk == blob |

The owner's freeze line (§5) cites exactly these two digests. What is frozen vs not frozen is the
draft's own §7 list; this package adds nothing to it.

---

## 2. Decision-5 elements → draft sections

| # | Decision-5 element | Where frozen |
|---|---|---|
| 1 | Versioned event vocabulary | Draft §4.10: `V3_VOCABULARY` (29 literals), `FORMAT_3_CODES` / `FORMAT_4_CODES` (22 literals each, V21-57 keep), `VOCABULARY4` = live enum (31) |
| 2 | Lifecycle transition schema | Draft §3: `transitions.py` — 13 `STORY_STATES`, `STORY`, `WITHIN`, `RUN`, `symbol_of`, `TABLE_DIGEST`; six consumers §3.2 |
| 3 | Reservation / stream fields | Draft §4.2–4.3: `provider/request.reservation{turns, max_usd}` (null = explicitly unbounded); `provider/result.segment{session, sha256, offset, bytes}` + rule R-SEGMENT |
| 4 | Signing envelope | Draft §4.1 (`run/begin` requires `signer` = sha256 fingerprint of the run's ephemeral pubkey, inside the chain per CR-7) + A2 draft §3.1 (seal payload `aisef-v2-seal/1` over `{run_id, kernel_digest, journal id/head, anchor}`, `SEAL.json` outside the manifest) |
| 5 | Compatibility requirements | Draft §6: per-kind classes MUST-READ-UNCHANGED / NEW-ONLY (CR-3) / classified-stricter (CR-4) / VERSIONED, under COMPAT-MATRIX rows J1–J8, rules CR-1..CR-7, test CT-2 (= FMT4-3) |

---

## 3. Q-resolution table

| Q | Status | Resolution (one line) |
|---|---|---|
| Q1 | **RESOLVED AS INTEGRATOR** | Enums hunk rides L2-SIGN's W2a merge window per the draft's own default; this package is the logged single-writer exception (entry below). |
| Q2 | **MEASURED** (draft §13) | NO zero-proof commit on the golden path — K-NOWORK commits WITH `proof/verified` (`assertNoDeveloperWork` pins 2× SATISFIED per criterion; case D rolls back) ⇒ R-COMMIT takes the STRICT form of §4.8. |
| Q3 | **MEASURED** (draft §13) | Plain-form re-derivation HOLDS on golden sealed ProbeRecords of all three result shapes (script run 2026-11-26) ⇒ R-SEALED takes its primary form. |
| Q4 | DEFAULT = freeze proposal | `bundle_digest` in f4 `run/begin` is OPTIONAL; G6 decides at W4 whether its fingerprint reads it from there. |
| Q5 | **PREREQUISITE MET** | A2 primitives merged 2026-11-26, commit `648a660b` (`aisef2/journal/sign.py`, `sign.fingerprint`); the JournalWriter4 flip no longer waits on W2a. |
| Q6 | DEFAULT = freeze proposal | V21-57 KEEP: no 23rd FailureCode; `FORMAT_4_CODES` = the 22 v2.2.0 literals. |
| Q7 | DEFAULT = freeze proposal | f3 adversarial tightenings ratified as CR-4 classified stricter findings (no ledger entry); not f4-only. |
| Q8 | Consumer sign-off | Checklist below. |
| Q9 | DEFAULT = freeze proposal | No run-level completion marker; R-CLOSED + `run/end` is sufficient (TerminalState already distinguishes ENDED/ABANDONED). |
| Q10 | DEFAULT = freeze proposal | No `story/completed` without a same-run `story/commit`; a resumed run journals its own admission trail instead of re-citing the predecessor's. |

### Q1 single-writer exception — log entry

| Field | Value |
|---|---|
| File | `aisef2/arch/enums.py` (owned by NO W2 lane, DAG §4 rule (a) read-only — reason **M12**) |
| Hunk owner (content) | lane **L2-JOURNAL** (the two members are FORMAT-4's, draft §4) |
| Rider (merge window) | lane **L2-SIGN**, W2a window (per A2 draft §12, which already lists the hunk) |
| Members | `EventType.PROVIDER_ATTESTATION` (`"provider/attestation"`), `EventType.STORY_COMPLETED` (`"story/completed"`) |
| Reason | M12: no W2 lane owns `arch/enums.py`; a scoped two-line exception through an open merge window beats granting a lane standing write access |
| Status at logging | PENDING MERGE — commit `648a660b` (W2a primitives) does NOT contain the hunk (verified: neither member is in `arch/enums.py` at HEAD); it lands in a later merge of the still-open W2a window |
| Logged | 2026-11-26, integrator, in this package |

### Q8 consumer sign-off checklist

The three lanes below share ONE engineer with L2-JOURNAL; each review is real but not independent.
The owner should weigh these sign-offs with that caveat in view.

| Consumer | Surface | Sections | Status |
|---|---|---|---|
| E2/E4 (L2-ACCOUNTING) | `reservation` + `segment` key sets | §4.2–4.3 | engineering-reviewed 2026-11-26, same-engineer caveat declared |
| C7 (L3-CLIENT) | `provider/attestation` envelope | §4.4 | engineering-reviewed 2026-11-26, same-engineer caveat declared |
| G6 (L4-RESUME) | `story/completed` marker + field kinds | §4.5 | engineering-reviewed 2026-11-26, same-engineer caveat declared |

---

## 4. Negative controls — concrete test plan (expands draft §8)

Sites: **A** = append (`JournalWriter4`), **R** = reconstruct (`format4.reconstruct`), **F** = fold
(StoryState v3 / TerminalState v2). Every lifecycle row must refuse at all three sites (the E6 theorem).
Refusal TEXTS are not frozen (§7); the frozen SHAPE is: a refusal that names the format/rule, the event
kind, and the offending seq — never a silent skip, never an unspecific "invalid journal".
**Class: RED-BEFORE** = behavior changes vs 2.2.0 on that input (adversarial-only, M3; CR-4 classified
stricter per Q7). **NEW-SURFACE** = the input could not exist before format 4 (CR-3). **PIN** = control
proving 2.2.0 behavior is preserved.

### 4a. The five named rules

| Rule | Red-before case (input that passes somewhere today) | Expected refusal shape | Test file | Class |
|---|---|---|---|---|
| R-SEALED | `proof/verified` citing a `probe/evaluated.record` whose `record_digest` does not re-derive — today f3 checks key-presence only (M9); passes A+R, survives F | refusal naming `proof/verified`, the cited seq, and seal/`record_digest` mismatch (T11) | `tests/v2/test_v23_format4.py` | RED-BEFORE (f4 + f3 reads per Q7) |
| R-GATE | `gate/decision{passed: true}` citing a `gate/check{passed: false}` — today no writer-validator rule (V21-10) | refusal naming `gate/decision`, the failed cited check's seq (T9) | `tests/v2/test_v23_format4.py` | RED-BEFORE |
| R-COMMIT | `story/commit` in an attempt holding no `proof/verified` — today accepted by f3 reconstruct (#11 family); STRICT form per Q2 | refusal naming `story/commit`, the story_id, "no proof/verified in attempt" (T12) | `tests/v2/test_v23_format4.py` | RED-BEFORE |
| R-SEGMENT | f4 `provider/result` COMPLETED with `segment: null`, or synthetic closer with non-null `segment`; plus an edited/truncated segment whose sha256 no longer re-derives at verify | schema refusal naming `provider/result`, outcome, segment nullity rule (T14); verify: specific integrity FAIL, never "unknown" (#12 acceptance) | `tests/v2/test_v23_format4.py` | NEW-SURFACE |
| R-CLOSED | f4 `run/end` while a `provider/request` has no `provider/result`; companion positive: the E5 interrupt path (closers first, M7) still ends cleanly | refusal naming `run/end` and the unanswered request's seq/story (T13) | `tests/v2/test_v23_format4.py` | NEW-SURFACE |

### 4b. Lifecycle (§3 table) controls

| Control | Case | Refusal shape | Test file | Class |
|---|---|---|---|---|
| T1/T2 | `proof/verified` / `tests/adequacy` in BEGIN (un-admitted) — today passes A+R, refused only at F (M1/M2) | three-site refusal naming state BEGIN and the symbol | `tests/v2/test_v23_transitions.py` | RED-BEFORE (A+R sites) |
| T3 | `provider/request` in BEGIN — today writer-validator silent (M1) | three-site refusal, `WITHIN[provider/request] = {ACTIVE}` | `tests/v2/test_v23_transitions.py` | RED-BEFORE (A+R sites) |
| T4–T7 | double admission; second `begin` of open attempt; `begin` after ENDED_COMMIT; `end` before `dispose` | refusal naming (state, symbol) with no `STORY` row | `tests/v2/test_v23_transitions.py` | three-site consolidation (refused at F today) |
| T8/T8b | `story/completed` on ENDED_ROLLBACK; duplicate marker on ENDED_COMMIT | refusal: marker only in `{ENDED_COMMIT}`, at most one per story per run | `tests/v2/test_v23_transitions.py` | NEW-SURFACE |
| T10 | EXHAUSTIVE oracle: all (state, symbol) cells f4-validator == StoryState v3; golden corpus (E5 F1–F25/G1–G2, p6 scenarios, 10 fixtures) f3-with-table == f3-at-2.2.0 event-for-event | zero divergences | `tests/v2/test_v23_transitions.py` | PIN (bounds Q7's tightening to the enumerated negatives) |

### 4c. Remaining §4 schema deltas

| Delta | Case | Refusal shape | Test file | Class |
|---|---|---|---|---|
| §4.1 `run/begin` f4 fields | missing `signer`/`kernel_digest`/`run_id`; non-hex64 values; `journal_format` ≠ declared writer format | schema refusal naming `run/begin` and the missing/malformed key | `tests/v2/test_v23_format4.py` | NEW-SURFACE |
| §4.2 `reservation` | key absent; extra key; `max_usd` negative/non-finite; `turns` non-count — null ≠ absent pinned both ways | schema refusal naming `provider/request.reservation` and the key | `tests/v2/test_v23_format4.py` | NEW-SURFACE |
| §4.4 `provider/attestation` | missing required key; empty `session`/`expected`; placed before `run/begin`/after `run/end` | schema/WITHIN refusal naming the kind | `tests/v2/test_v23_format4.py` | NEW-SURFACE |
| §4.5 `story/completed` fields | missing `fingerprint`; citing a `story/commit` of another story_id; citing a non-commit | schema/citation refusal naming the kind and the cited seq | `tests/v2/test_v23_format4.py` | NEW-SURFACE |
| §4.6 `base` on `story/resource-acquired` | `base` on `kind != WORKTREE`; non-sha value | schema refusal naming the field | `tests/v2/test_v23_format4.py` | NEW-SURFACE |
| §4.7 `tests/adequacy.audit` | malformed inner mapping (wrong vacuity/relevance keys); absence stays legal (OPTIONAL) | schema refusal naming `audit` and the inner key | `tests/v2/test_v23_format4.py` | NEW-SURFACE |
| §4.10 vocabulary pin | T15: f≤3 journal carrying ignorable `provider/attestation` / `story/completed` — still SKIPPED exactly as 2.2.0; red-before WITHOUT the pin (would flip to refused) | no refusal — skip behavior asserted byte-stable | `tests/v2/test_v23_format4.py` | PIN |
| §4.9 code pin | f≤3 `failure/observed` with a code outside the 22 literals refused as 2.2.0 refused it, even after any enum growth | 2.2.0-identical refusal | `tests/v2/test_v23_format4.py` | PIN |
| §5 delegation | T16 (= FMT4-3/CT-2): f4 reader == `format3.reconstruct` on all 10 committed fixtures + generated f1–f3 journals; unknown format number refused by number, never guessed | identical outcomes; "unknown format" refusal | `tests/v2/test_v23_format4.py` | PIN |
| §3.1 fold oracle | T17: `oracle_problems` for StoryState v3 + TerminalState v2 over the golden corpus | incremental == from-scratch | `tests/v2/test_v23_transitions.py` | PIN |

Kill coverage: each rule has a mutant class only its T-row kills (draft §10) — drop a STORY row → T5/T6;
invert R-GATE → T9; skip seal re-derivation → T11; drop delegation → T16. Measured once at the CORE-2
batch (LÔ discipline), not per-control.

---

## 5. The freeze line (the owner issues this; nobody else)

> FREEZE C-1 = FORMAT-4-DESIGN-DRAFT.md @ blob `41506829d227d3380c2095b59813810807b28991` / sha256
> `313f803547c518618386f991c5f8036ebf3173800a78c5f2d388f73ead4b5141` with the Q-resolution table of
> FORMAT-4-FREEZE-PACKAGE.md @ \<its digest at issuance\>; amendments only, dated, after this line.

The package digest is filled at issuance (this file's blob sha at the commit the owner cites — it cannot
be written inside the file it digests). After the line: changes to the draft are appended dated
amendments, never edits (draft header rule).

---

## 6. What this freeze unfreezes (plan §2)

1. **ORCHESTRATION track start** — the whole track waits on C-1 by directive ("toàn track ← C-1"):
   L4-PARALLEL (C5), L4-REVIEWER (C6), L4-CONTEXT (C10/G10), L4-RESUME (G6), L4-MONITOR (C1, C3b).
2. **E2/E4** (L2-ACCOUNTING) — may build against §4.2–4.3 reservation/segment key sets.
3. **JournalWriter4 flip pacing** — A2 W2a primitives already merged (`648a660b`, Q5 met), so the flip
   is paced only by the CORE-2 capability batch (flip + E2/E4 emission + repair closers, ONE measurement,
   draft §9); E1/A2-INT (W2c) additionally awaits C-2.

## 7. Inconsistencies found while assembling (reported, not fixed)

1. **Dangling cross-reference in the draft — FIXED PRE-FREEZE (2026-11-26):** §3.1 `WITHIN` cited a bare
   "(sec. 14…)" for `story/plan-drift`; the real target is `docs/implementation/v2/P3-PROJECTION-SEMANTICS.md`
   §14 "MUST emit" (also cited by `aisef2/journal/projections/story_state.py:62`). The draft now names it
   explicitly; the digests in §1 and §6 of this package are the post-fix digests.
2. **Contract-vs-checklist namespace collision:** the plan's contract "C-5" (E5 Stage lifecycle, already
   landed) is not the draft's consumer "C5" (closing identity / parallel stories, L4-PARALLEL). Both
   documents use both names consistently in context, but a reviewer reading "C5 ← C-1" cold can misread it.
3. **Enums hunk not yet landed:** A2 draft §12 lists the `arch/enums.py` +2-members hunk among W2a
   L2-SIGN edits, but the landed W2a commit `648a660b` does not contain it (neither member exists in
   `arch/enums.py` at HEAD). Not a contradiction — the W2a window is still open — but the Q1 exception
   entry above records it as PENDING MERGE so the freeze does not imply it landed.
4. The task brief referenced plan §2 "contracts C-1..C-8"; the plan enumerates C-1..C-7 (C-5 and C-7
   marked landed). The brief's "C-8" was the briefing's own slip (ClientAdapter is contract C-3, whose
   MASTER-CHECKLIST row id happens to be #C8) — the plan text is correct as it stands.
