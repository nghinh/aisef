# Minimal state snapshots for the historical replays (P20 step 5)

The archive `closure-evidence/dogfood/ledgerlock-run2/replay-1.7.4*/` keeps the 1.7.4 replays' evidence as flat files
(`<STORY>.evidence.jsonl`). `aisef replay` scores evidence against the story it belongs to, so it needs the story index,
the story files and the project config of the state the evidence was produced in. `state-1.7.4/` and
`state-1.7.4-opencode/` are those three things, copied on 2026-09-17 from the 1.7.4 replay working copies the flat
files came from (`_bmad-output/stories.index.json`, `_bmad-output/stories/**`, `.ai/config.json`; nothing else).
Provenance checks at copy time: the archived STORY-01-06 (1.7.4) and STORY-04-01 files are byte-identical to the
working copies' evidence; the archived STORY-03-01 is a prefix of its working copy (the archive was taken before the
later phases continued that story). Replaying the archived files over `state-1.7.4/` reproduces the working copy's
replay row for row (every attempt, every check) — measured before the snapshot was committed.

`../historical_replay.py` builds a temporary project from a snapshot plus the archived evidence (renamed
`<STORY>.jsonl`), runs the replay with the candidate under test, and compares every row with the classifications it
states in advance. The archive itself is never modified.
