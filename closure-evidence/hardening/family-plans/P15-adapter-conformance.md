# Phase 15 — adapter conformance + one live smoke

**Deterministic (no model, `tests/hardening/adapters/test_conformance.py`, 46 tests: 45 green, 1 platform skip).** OpenCode and Claude Code are
driven by recorded streams through a fake CLI (`_fake_cli.py`), one provider condition at a time, the REAL
`run(RunSpec)` on each side, and the typed kernel outcome (`exit_status_of` + the `RunResult` fields the story loop
reads) compared side by side; every condition asserts each adapter's own result AND that both adapters land on the
same status. The five registered disagreements (AD-01 … AD-05) were closed by F2/F3 (typed outcomes; `exit_status_of`
reads the provider fields before the session text); no `expectedFailure` remains in the suite. Rule (owner
directive): live models are never called from these tests.

**One live smoke (`tests/conformance/`, `AISEF_CONFORMANCE=1`).** The conformance runner builds a real project, a real
worktree and real guards, then calls the real client; results are read from disk and from the guard's own records,
never from the agent's words. One client is smoked — OpenCode, the first-class W1 client (decision 2026-09-05) —
through its five probes (≈ $0.1–0.3 each). The run's `ClientRun` is merged into `docs/CONFORMANCE.md` by the
runner itself; the smoke's pass/fail per probe is recorded in this file's closure section verbatim, and a red probe
is a finding to register, never a reason to edit the runner. The smoke runs with no other CPU-heavy job on the
machine and after the deterministic suite is green on the same tree.

Definition of done: deterministic suite green (Linux + Windows CI); one live smoke executed and recorded with the
client version, model and per-probe outcome; any disagreement registered with provenance.
