# REPLAY CONDITION DEVIATION — run.max_turns

REPLAY CONDITION DEVIATION:
run.max_turns: 40 -> 80
reason: repeated route truncation under opencode/9router/mycombo
scope: LedgerLock replay only

- Recorded: 2026-09-16T00:18:23+00:00 (owner decision, 2026-09-16)
- Config file: `.ai/config.json` (project config; key added, previously absent → framework default 40)
- Old effective value: 40 (aisef 1.7.4 default `run.max_turns`)
- New value: 80
- Evidence for the decision (clean OpenCode replay, Phase 2, master 9cf22f5c): 5 of 6 developer sessions and 1 reviewer session hit the 40-turn cap; no infra failures; no no-op loop; no D-032 regression; no deadlock; STORY-03-01 exhausted 3 attempts, last candidate ca37cc44 (tests/lint/nop/TDD/security PASS; `criteria have tests` failed on a test named AC-STORY-03-01-6; reviewer cut at 40 turns).
- Not changed: AISEF product code, plan/stories/PRD/architecture, STORY-03-01 acceptance criteria, candidate ca37cc44 and its branch, the replay state.
- Rule: no further change to `run.max_turns` during this replay without owner approval; a session reaching 80 turns is preserved as evidence, not re-raised.
