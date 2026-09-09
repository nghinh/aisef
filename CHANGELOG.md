# Changelog

## 1.2.19 — 2026-09-09

Three real failures found by running the framework, two of them silent.

- **OpenCode ran with every guard disabled** (bug 32). `aisef_command()`
  falls back to `<python> -m aisef.cli` when `aisef` is not on PATH, and that
  three-word command was carried as one string into both clients — read back
  as one filename containing spaces. A guard call that cannot start is not a
  block, so a whole run finishes unguarded with evidence identical to a
  well-behaved agent. Measured on `todo`: 46 sessions, 0 guard events.
  `aisef_argv()` now returns argv, the plugin emits an array, and a guard
  that cannot run refuses the action instead of allowing it.
- **Windows could not start either client** (bug 33). `WinError 2` on the
  `.cmd` shim npm/bun installs, then `WinError 206` because the prompt rode
  on a command line Windows caps at 32767 characters. Binaries are resolved
  before exec, the prompt goes to stdin, and `ENV_KEEP` no longer hands a
  Windows child a POSIX-only environment.
- **A worktree kept a stale guard.** Projects that commit
  `.opencode/plugin/aisef-guard.ts` checked out the committed blob, so a
  plugin `aisef compile` had just fixed never reached a story. Generated
  client config is now overwritten on every worktree create.
- `run.log` states the reason for each failed check instead of only naming
  it; mockup verification that could not run scores *unconfigured*, not a
  green pass.

## 1.0.0 — 2026-09-08

First stable release. The harness is feature-complete for single-machine,
multi-client story execution with evidence-bound gates.

### Highlights

- **Conformance parity**: Claude and OpenCode both pass 10/10 probes (C1–C10).
- **Crash recovery**: `reconcile_all()` at every `aisef run` start; 3 recovery
  scenarios (roll-forward, undo, stale).
- **Egress guard V12**: `check_egress()` with host extraction, wildcard matching,
  `sandbox.allow_hosts` config.
- **Credential isolation**: Docker S1–S5 all pass; local provider honestly
  documented as unsupported.
- **Zero mandatory config**: all 58 keys have sensible defaults; projects work
  with no `.ai/config.json`.
- **ADR-006**: reconciles 6 exit conditions — 3 met, 3 deferred to post-1.0
  with evidence and rationale.
- **Dogfood evidence**: par (Node.js) + calc (Python) + bench (15+ bug-fix
  tasks, 96 runs) demonstrate framework robustness across project types.
- **1913 tests passing**, zero external dependencies, Python >= 3.11.

### Known limitations

- Distributed execution (multi-machine) is deferred to post-1.0.
- External user validation is pending (post-1.0 adoption milestone).
- Local sandbox provider does not isolate credentials (use Docker).
- OpenCode + Serena writes `.serena/` files outside declared write_scope;
  the harness correctly rejects these — a known agent-side limitation.

## 0.8.0

- Brownfield support: `CodebaseGraphProvider`, delta planning, blast radius.
- Handoff and `skill_use` frozen as evidence kinds.

## 0.7.0

- OKL (Operational Knowledge Layer): ADR-002, skill registry + router.
- Evidence-driven epic improvement (ADR-004).

## 0.6.0

- Harness absorption pattern (ADR-005).
- Bench protocol v0.3.0 with 27-task challenge set.

## 0.5.0 / 0.5.1

- Handoff contract and skill graph (ADR-003).
- Sandbox conformance probes S1–S5.

## 0.4.0 / 0.4.1

- TDD gate (G8): red-before-green, test delta detection.
- Story gate checks expanded to 16 with 3 controls each.

## 0.3.0 / 0.3.1

- Conformance probes C1–C10.
- Multi-client runner infrastructure.

## 0.2.0

- PyPI package `aisef`, CLI entry point `aisef`.
- Zero external dependencies.

## 0.1.0

- Initial release: 8 human gates, story execution, evidence store,
  worktree isolation, journal, state machine.
