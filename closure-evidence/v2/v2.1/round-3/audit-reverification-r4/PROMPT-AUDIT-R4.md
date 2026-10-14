# Verify three new survivor audits (AISEF 2.1, B-03 round 4): your batch

You are a skeptic. Campaign 6 (snapshot `a770fbb`; the code is the same at HEAD `9a4f1b3`) left 26 survivors; 23 had
audits that were carried and re-verified; THREE are new and were drafted by the engineer who wrote the code they live
in (round 4 changed `confine._sections`, `confine._judge`, `process_range._Posix.abort`). A draft by the author is not an
audit until someone who did not write it has tried to break it. Your batch is `$SP/m21/r4/audit/batches/N1.json`
(`target`, `index` = the mutant's position at HEAD, `mutant`, `class`, `group`, `grounds`, `consumers_checked`).

The owner's rule (in spirit): AUDITED is not KILLED and is reported apart; an audit names the consumers *per mutant*
and the exceptions *actually looked for*; a string is not harmless because it is a string (a refusal, a status, an
identifying element is read by an operator or a verifier); never lump. EQUIVALENT needs a proof from the code.

## Setup
```
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
REPO=/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/v21
HEAD=9a4f1b3d3ad2fbb96bc424427aab925a48aeeb02
WT=$SP/m21/r4/audit/wt/$BATCH-$K                  # K = your copy letter (a or b)
git -C $REPO worktree add --detach $WT $HEAD
```
Python only through `$SP/m21/kills3/py.sh $BATCH-$K ...` from `$WT` (never `python3`, never the real `opencode`, no
network, no docker, no `kill`). See a mutant as a diff: `$SP/m21/kills3/py.sh $BATCH-$K $SP/m21/r3/tools/mutant_view.py
TARGET INDEX...`. The change under audit: `git -C $REPO diff 289885e HEAD -- aisef2/app/confine.py aisef2/runtime/process_range.py`;
its decision doc: `docs/v2.1/decisions/B03-R4-REVIEW.md`; the test: `tests/v2/test_v21_r3_judge_not_run.py`.

## For each entry decide (cite file:line at HEAD)
1. Is the mutant what the entry says (same line, same function)?
2. Is every consumer/producer/test/document the grounds name real and as described, and is there a consumer the draft
   missed (grep `aisef2/`, `validation/`, `tests/`, `docs/`)?
3. Can you build an input on which the mutant's OBSERVABLE result differs in a way a reader depends on? Try to refute.
   Run the mutant against the registered kill files of the target (`validation/v2/mutation.py` `V21_TARGETS`) and
   against the other test modules that reach `confine` — a test that kills it and is not registered refutes the audit.
4. Would a requirement test be natural for it (a contract the module states)? Say which, as a sketch.

## Output (`$SP/m21/r4/audit/out/$BATCH-$K.json`, and your final answer)
`{batch, copy, entries: [{target, index, mutant, class_before, verdict: "CONFIRMED"|"REVISED"|"REFUTED"|"NOT_DECIDED",
class_after, grounds, consumers_checked[], exceptions_checked[], refutation, note}]}` — every entry exactly once.
CONFIRMED: grounds hold (refresh cites). REVISED: conclusion holds, grounds corrected (give them). REFUTED: a test is
owed (the input, the reader, a sketch). Never round up. Remove your checkout at the end
(`git -C $REPO worktree remove --force $WT`). Do not edit the repository. Do not look at the other copy's output.
