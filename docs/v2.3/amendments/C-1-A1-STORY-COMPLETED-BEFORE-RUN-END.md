# C-1 — AMENDMENT A1 (owner ruling 2026-11-26 §1, APPROVED; recorded and implemented 2026-11-26)

**Normative text (ruling, verbatim):** "An event of type `story/completed` MUST appear before `run/end`.
A completed-story marker must never be appended after the run has closed. Violations MUST be refused at both
journal append and reconstruction, identifying the offending event, sequence and rule."

**Scope:** amends the frozen C-1 FORMAT-4 contract (amendments/C-1-FORMAT-4-FREEZE.md) by ADDING the run/end
bound to §4.5's `story/completed` rules. The frozen design file is NOT rewritten (its digest stands); this dated
amendment is the change record, per the freeze's own rule.

**Implementation:** `aisef2/journal/format4.py::_completed4` — one branch mirroring `_attestation4`'s existing
before-run/end rule, refusing with `"story/completed at seq N: … before run/end … (C-1 amendment A1)"`. The rule
lives in the shared f4 validation model, so it fires at BOTH the append (JournalWriter4) and reconstruct sites by
construction.

## Required verification (ruling §1) — all performed 2026-11-26

| Requirement | Result |
|---|---|
| Red-before/green-after for finding C1 | red-before = the adversarial probe (aisef-private-evidence/2026-11-26-advrev-f4/probe.py: the exact sequence ACCEPTED at A and R pre-A1); green-after = `tests/v2/test_v23_format4.py::StoryCompletedEnvelope::test_a1_marker_after_run_end_refused_at_all_three_sites` (the same sequence REFUSED, message pinned with event+seq+rule) |
| Append, reconstruct, fold consistent on the forbidden sequence | the test refuses at A and R via the shared `refused` helper AND folds the stream through the live `TerminalState`, which refuses the same forged marker ("after the run is ENDED") — three sites agree |
| No alteration of valid historical format-1/2/3 journals | the rule is registered only in format4's `_rules()` for the f4-only kind `story/completed`; formats ≤3 delegate unchanged (pinned by the existing T16 delegation tests and the f3 fixture suite, all green) |
| No weakening of G6 fold-before-trust | G6-RESUME-DESIGN-DRAFT.md addendum 2026-11-26 unchanged: fold-before-trust stays NORMATIVE — defense in depth, not replaced by A1 |
| Independent adversarial review | queued as its own lane immediately after this landing (reviewer ≠ implementer); its report files against the flip gate with the first review |
