# Changelog

## 1.2.25 — 2026-09-09

- **The security reviewer kept re-filing a finding against harness code**
  (bug 40). Each attempt hands the reviewer its own previous findings so it
  cannot re-rank yesterday's advice into today's blocker. When one of those
  findings names a file that is no longer in the diff, handing it back invites
  the reviewer to file it again — and it came back a tier higher, `high` then
  `critical`, against `.opencode/plugin/aisef-guard.ts`, which the harness
  writes and the story never touched. Prior findings are now filtered to files
  still in this candidate's diff.
- **A worktree left by a failed run never saw the trunk again** (bug 41).
  Reuse took a shortcut past `refresh()`, so fixes merged to the trunk between
  runs never arrived and the story failed again on something already fixed.
  Reuse now refreshes like a fresh worktree; the merge is a no-op when the
  trunk has not moved.

## 1.2.24 — 2026-09-09

- **"Conflicts in unknown files" where the branches merge cleanly** (bug 39).
  `create()` copied the generated client config — a tracked file — into the
  worktree *before* calling `refresh()`, and `git merge` refuses to run over a
  locally modified tracked file. `aisef run` stopped on todo/STORY-01-02 with
  a conflict report while `git merge-tree` merged the two branches without a
  single conflict. Refresh now happens first and the config is laid down
  after; `refresh()` also discards its own earlier copy before merging.

  Third consequence of one decision in 1.2.19 (overwrite the guard plugin so
  it can never be stale), after bug 37. The overwrite is still right — it is
  what stops a run going unguarded — but it has to happen where git is done
  looking.

## 1.2.23 — 2026-09-09

Both fixes are the same mistake in two places: a gate that judges *state*
where it means to judge *change*.

- **The reviewer saw the harness's own file and blocked the story** (bug 37).
  Since 1.2.19 the harness refreshes the guard plugin inside the worktree on
  every run, which leaves that tracked file modified. The structural checks
  filter `HARNESS_OWNED` correctly, but `review_diff` ran an unlimited
  `git diff`, so the reviewer blocked "modifies a file outside the effective
  write scope" and the security reviewer filed a high finding against
  generated harness code. todo/STORY-01-02 went stuck on it. The diff is now
  limited to the story's own changed paths.
- **A file the operator left uncommitted blocked every planning tool call**
  (bug 38). `.ai/config.json`, written by `aisef setup`, made `diff-scope`
  report "changed outside write_scope" 14 times in one Windows run and left
  the ux phase blocked. Planning and mockup phases now declare
  `AISEF_BASELINE_DIRTY` — what was already dirty when the phase opened — and
  the guard subtracts it. What the session really writes outside scope is
  still blocked.

## 1.2.22 — 2026-09-09

- **Planning phases inferred the guard's scope from what was absent**
  (bug 36). `plan` and `mockup` passed no environment to the client, so the
  guard fell back to the planning scope only as long as the host had no
  `AISEF_*` left over: a stale `AISEF_STORY_ID` in the shell flips it into
  story mode with an empty scope and denies every planning write. Both
  phases now declare `AISEF_WRITE_SCOPE`, `AISEF_STORY_ID`, `AISEF_PROJECT`
  and `AISEF_WORKDIR` outright.
- **A guard that blocked outside a story left no trace.** Nothing is recorded
  without a story id, so a blocked planning phase kept its reason inside the
  client's own session log. Blocks now reach `run.log` as
  `guard <kind> BLOCK <tool> · <reason>`.

## 1.2.21 — 2026-09-09

- **A sentence in the route field failed a story three times** (bug 35). The
  UX table's column is "Route/state", so the agent wrote prose in it, the
  mockup copied the sentence into `aisef-route`, the harness turned it into a
  URL, and the dev server answered with its 404 page. The mockup-map step
  then compared that error page against the contract and reported every
  component missing — with `preservation` calling it a regression. The only
  trace was `extra: heading "Error response"`.
  - the mockup gate now rejects a route that is not openable, before a story
    spends anything;
  - `render.mjs` treats HTTP >= 400 as *not compared*, not as an app missing
    its interface;
  - the mockup prompt asks for a real path when the document holds prose.
- A data region that renders nothing now says the list was empty at that URL
  and points at `app.dev_command`, instead of only naming the missing role.

## 1.2.20 — 2026-09-09

- **Windows: the guard rejected paths that were inside scope** (bug 34).
  `Path.relative_to` returns the native form, and every comparison after it
  is written in `/` — so `_bmad-output\project-context.md` was one segment
  matching nothing, and the plan phase stopped on a file plainly inside
  `_bmad-output`. `to_posix()` normalises where OS-produced paths meet
  story-declared ones, on Windows only: a backslash is a legal character in
  a POSIX filename, and reading it as a directory boundary would let
  `docs\evil.sh` at the root pass as being inside `docs/`.
  Same fix reaches `check_process_refs` and the test-path pattern.

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
