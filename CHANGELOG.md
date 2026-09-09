# Changelog

## Unreleased

- **The reviewer graded the first story against the whole PRD** (bug 58). A
  story whose single acceptance criterion is "the document has these
  elements" was blocked three times for having no submit handler, not reading
  storage, and not persisting — the work of three later stories. Nothing in
  the review prompt distinguished "not done" from "another story does it", and
  the only way out was for the author to build the next stories' work, which
  then fails *those* stories' nop control. The reviewer now receives the plan,
  one line per story, and is told plainly: a requirement whose story has not
  run is not this story's debt.

- **A failing test run logged 40 lines of HTTP access log.** Playwright's
  `webServer` writes into the same stream as the results; server access lines
  are dropped before the tail is taken (the full text stays in the evidence
  log).

- **A 99-test Playwright run read as zero tests** (bug 57). The fix for bug 43
  matched its own fixture — a single-project config. The moment
  `playwright.config` declares `projects`, which is the default for anything
  testing more than one browser, every line carries a `[chromium] › ` tag and
  the pattern matched nothing; `criteria have tests`, `coverage`,
  `no baseline regression`, `tests verify story` and `preservation` all went
  back to reporting that they could not read test names. The new fixture is
  cut from a real three-browser run, and a test name now keeps its browser tag
  so one browser skipping a case cannot hide another browser passing it.

- **A story that builds the shell was told its list is missing a checkbox**
  (bug 56). Roles that appear only inside the mockup's sample rows were
  compared by "is this role anywhere on the page", so an empty list and an
  unbuilt feature looked identical — and the advice the message gave
  (`app.dev_command` must serve an environment that already holds a record)
  is not achievable for a browser-stored app, or for the first story of a
  project, which builds the shell before anything can create a record. These
  roles are still reported, and now block only when the data region actually
  rendered rows.

- **The first story of every new project failed the gate forever** (bug 55).
  `no baseline regression` and `tests verify story` both reported
  `unrunnable · tool not installed or cannot load (no such file or directory)`
  on a machine that had run the same suite three minutes earlier. The nop
  control runs at the parent SHA, where a greenfield project has no
  `package.json` yet — this story creates it — so npm exits 254 with `ENOENT`,
  whose text matches the missing-tool table. A missing **manifest** is now told
  apart from a missing **tool**: at the parent that means no project, which is
  the strongest form of the answer nop is asking for (PASSED), and there were
  no tests to regress (NOT_APPLICABLE). The same holds one commit later, when
  the manifest exists but `node_modules` does not: dependencies live in the
  worktree the story is about to build, and a project root that never
  installed them has nothing to lend. A real `command not found` still
  blocks.

- **Every command line was split and quoted with POSIX rules** (bug 54). On
  Windows `shlex.split` ate the backslashes out of absolute paths — a project
  command naming `C:\Python\python.exe` lost its program entirely — and
  `shlex.quote` wrapped the framework's own command in single quotes, which
  `cmd.exe` treats as ordinary characters, so every prompt and every guard hook
  named a program that does not exist. Splitting and joining now go through
  `split_command` / `quote_command`, which follow the host's rules.

- Windows CI: the compile report and `Config.source` print POSIX separators
  like every other path the framework shows; `remove_tree` is public, because
  `shutil.rmtree(..., ignore_errors=True)` leaves read-only `.git/objects`
  behind and the next `mkdir` fails.

## 1.2.31 — 2026-09-09

- **"5 files changed since the most recent test run" when nothing had
  changed** (bug 47). todo/STORY-02-01 was refused three attempts running,
  taking `no baseline regression` and `tests verify story` down with it, while
  the log showed `tool=test PASS` after the candidate was frozen.
  `stale_since_last_test` compared `seq`, and a file written by a build from
  before 1.2.26 carries restarted numbering — six `file_change` events with
  seq 161-166 recorded 33 minutes *before* the test run at seq 144. By time,
  nothing had changed at all. Comparison is now by position in the
  time-ordered list, here and in the `diff-scope` guard.

  1.2.26 fixed the ordering `read()` returns; this is the other side of the
  same coin — when a field stops being trustworthy, every reader of it has to
  be found, not just the one that surfaced the problem.

## 1.2.30 — 2026-09-09

- **A TypeScript story failed write-scope on its own compiler output**
  (bug 46). `tsc` rewrites `*.tsbuildinfo` on every build, so the guard
  blocked every bash command with "2 files changed outside write_scope:
  tsconfig.app.tsbuildinfo, tsconfig.node.tsbuildinfo", and the reviewer spent
  2 of its 7 blocking findings telling the author to revert a file the next
  build recreates. Same class as `node_modules` — it appears because the story
  *ran*, not because it *wrote* — but `VENDOR_PATHS` matches directories and
  this is a suffix. Excluded in `changed_files`, which is the one place write
  scope, the diff-scope guard and the reviewer's diff all read.
- The nop control called a command that **could not start** "tests red at
  parent (expected)". A control that never ran now says so.

## 1.2.29 — 2026-09-09

- **Windows could not run any project command** (bug 45). `npm test`,
  `npm run lint` and `npm audit` all came back `[WinError 2] The system cannot
  find the file specified`, exit 127, reported as "tool not installed" — on a
  machine with npm installed and working. Same cause as 1.2.19's client
  launcher, one layer down: `npm` is a `.cmd` shim on Windows, which
  `CreateProcess` cannot execute and `subprocess` will not find because it
  does not search `PATHEXT`. Every host command — project tools and the app
  dev server — now goes through the same resolution.

## 1.2.28 — 2026-09-09

- **"Missing component" now names the component it was renamed to** (bug 44).
  todo/STORY-02-01 spent all three attempts on `mockup map ✗ missing: textbox
  "Description"` while `textbox "Description (optional)"` sat in the evidence's
  `extra` list every single time — the agent had read the story's "optional
  Description" as label text. A renamed label is the most common way a
  component goes missing, and reporting only the absence sends the author
  hunting for a field that is on the screen in front of them. The gate and the
  result summary now pair them and say which one the mockup pins.

## 1.2.27 — 2026-09-09

- **Playwright test names are read now** (bug 43). Its `list` reporter prints
  every test name, but the parser did not know the shape, so `criteria have
  tests`, `coverage`, `no baseline regression` and `tests verify story` all
  scored *unconfigured* on every Playwright project — and told the operator to
  switch to a reporter that prints names, which theirs already did. Playwright
  is the runner this framework drives for mockup and e2e checks, so the gap
  sat in the middle of its own house. The fixture is real `todo` output.

## 1.2.26 — 2026-09-09

- **Every gate could read an older run's result** (bug 42). `_next_seq` read
  the last 4096 bytes to find the highest sequence number — an O(1) shortcut
  with no guard on its ceiling. One event longer than that window (a review
  verdict with findings) leaves the window holding a single truncated line,
  nothing parses, and the function answers `1`: numbering restarts mid-file.
  `read()` sorted by that number, so an old run's events sorted *after* the
  current ones and every "latest result" check read the wrong build. The gate
  reported evidence recorded three candidates back while test, lint, qa,
  mockup, review and security had all just run and recorded against the
  current one. Measured on todo/STORY-01-02: 3 restarts in one file, each
  immediately after a line over 4 KB.

  The window now grows until it parses, and `read()` orders by time then
  sequence, which also heals files already written with restarted numbering.

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
