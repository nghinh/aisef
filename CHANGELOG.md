# Changelog

## Unreleased

- **`reject` requires the artifact to exist, like `approve` does** (bug 85).
  On an empty project `approve prd` refused with "no artifact" while `reject
  prd --note x` succeeded, recording a verdict on a document that did not
  exist yet. When the planning phase then produced it, the gate already
  carried a rejection written before there was anything to read.

- **A mistyped guard name blocks instead of passing** (bug 84). The bug-81
  fix — usage errors exit 1 — collided with the hook protocol, where any exit
  code other than 2 means "not blocked". So `aisef guard <typo>`, which a
  stale compiled hook can easily produce, silently disabled that guard. The
  guard subcommand exits 2 on a usage error and says "blocking, not
  allowing"; every other command keeps 1. When a command serves someone
  else's protocol, that protocol wins over the local convention.

- **`init --stack python` now writes a test command this machine can run**
  (bug 82). It wrote `python -m pytest -v`; macOS and most current Linux
  distributions have only `python3`, so `aisef tool test` answered `exit 127:
  No such file or directory: 'python'` on the very machine that had just
  written the config. The preset picks the interpreter `shutil.which` finds.
- **"Could not run" is now visible where it is read** (bug 83). The harness
  already classified a missing tool as unrunnable, but `aisef tool test`
  printed `✗ test — exit 127` and left the reason inside the evidence detail,
  so a reader goes looking for the bug in their own code. The summary line
  carries `○ … NOT RUNNABLE: <reason>`; real failures keep `✗`.

- **`aisef <command> --project <dir>` works now** (bug 80). The flag was
  declared only on the root parser, so the order people actually type — and
  that `git` and `docker` accept — came back as a usage error. It is declared
  on every subcommand as well, with `default=SUPPRESS` so that putting it
  before the command is not silently overwritten by the subparser's default.
- **A typo exits 1, not 2** (bug 81). `argparse` exits 2 on a usage error,
  which is this CLI's documented code for "not ready yet" (gate unapproved,
  doctor failing). A mistyped command therefore read to CI as "not yet done"
  and scripts carried on. Usage errors now exit 1; the not-ready cases still
  exit 2, and a test pins both.

## 1.4.0 — 2026-09-13

A minor, not a patch, because one behaviour genuinely changes: a turn cap
that used to be ignored now stops sessions. If a project relies on
OpenCode sessions running past `run.max_turns` (default 40) to the
half-hour timeout, raise the cap deliberately — the number is enforced now.

Everything here came out of the C-1 benchmark cohort (12 hard tasks, 3
attempts, 2 conditions, a non-frontier model) and the cost decomposition
that ran beside it, both reported in `docs/`.

- **`skills.inline` is gone.** ADR-003's mechanism B inlined the top-scoring
  skill's SKILL.md into the prompt. Two A/B runs on real agents reported
  `used` 0/0 in both branches while the inlined branch carried ~8.8k extra
  prompt characters and failed exactly as often. A flag that is off by
  default, that nobody turns on, and that has code to maintain is debt: the
  key is retired (an old project declaring it loads with a warning naming
  the measurement) and the code is deleted.
- **The OpenCode adapter enforces `run.max_turns`.** The CLI has no
  `--max-turns`, so the cap was a number nobody read — measured: a session
  declared a cap of 40, ran 61 turns and stopped only on the 1800s clock.
  The adapter now counts turns on the event stream, kills the process at the
  cap, and reports `max_turns` rather than `timeout`.
- **A session the CLI cut short is no longer counted as an agent failure.**
  When the model emits a tool call the CLI cannot parse, the session ends
  there; the adapter recognises that ending and marks the run retryable
  infrastructure.
- **Guard messages advise per command.** Recursive delete stays blocked
  whatever the target, but the message now explains why a path filter cannot
  save it and that caches need not be deleted — the one guard block measured
  in the C-1 cohort was a `__pycache__` cleanup told to "report to a human".

- **`aisef dashboard` prints the four numbers an operator asks weekly**: cost
  per ISO week, net VERIFIED behaviours and behaviours per dollar, open gaps,
  and the age of the conformance table. A provider that reports no cost says so
  rather than printing $0.00, and a missing `docs/CONFORMANCE.md` says "could
  not read" rather than an age of zero days.
- **The budget warns at 80% of a declared cap**, with the real numbers in the
  message, once per dimension (the flag is on disk, so a second process does
  not repeat it). Blocking at the cap was already there and still happens
  before the model call — but the first time anyone heard about it was the run
  stopping mid-story.

## 1.3.1 — 2026-09-12

A same-day patch. 1.3.0 shipped a project template that froze all 68 defaults
into every new project, a Windows path bug in memory scoping, and a retry loop
that treated "please wait" as "try again immediately". None of it changes a
gate's verdict; all of it was found by running the thing.

### Fixes

- **`init` no longer freezes the framework's defaults into your project**
  (measured today: `.ai/config.json` went from **68 keys to 4**). Writing every
  default meant two things went wrong quietly: a newcomer could not tell which
  line mattered, and when the framework changed a default — which has happened,
  `context.max_preservation_chars` 1500 → 1200 — every existing project silently
  kept the old number forever. The file now carries only what the project
  actually decided plus the keys you *must* declare (today: `tools.test`).
  Reading is unchanged: `load` still merges with `DEFAULTS`, so nothing is lost.
- **A backslash path no longer slips past memory scoping** (bug 75, Windows).
  Scope matching compared raw strings, so a record scoped to `src\work` did not
  match a query for `src/work` — the record simply never came back, with no
  error. Both sides are normalised to POSIX form before comparison, and
  `src/work` still does not cover `src/workers/job.py`.
- **A rate limit is "wait, then retry", and the harness was not waiting.**
  `429` now has its own exit status, and `retry_delay_seconds` reads the delay
  the provider actually stated (`Retry-After` header, error body, or prose like
  "try again in 27s"), capped at 300 s so an absurd number cannot turn a retry
  into a hang. Retrying instantly spent the whole infra budget in seconds
  against a provider that was only asking for a pause.
- **An expired or missing key is no longer retried as infrastructure.** `401`
  and friends map to `auth`, which is outside the retry set, and the error now
  names the credential environment variables it looked at — names only, never
  values. Measured before the fix: three attempts, 176 s each, $0 recorded,
  nothing learned.
- **The published wheel no longer carries the benchmark's fake agent.**
  `SimulatedWeakAdapter` existed to fake a weak agent for bench runs and was
  shipping to every user; it now lives in `tests/bench/`.

- **Every stack preset now writes a test command that prints test names.**
  `init --stack python` wrote `python -m pytest`, and `doctor` then told you two
  gate checks would be "not configured" — on a project you had just created, in
  the first minute. Adding `-v` (and `--reporter=verbose` for vitest, `-v` for
  go) costs no dependency and closes that. Coverage still needs a plugin, so it
  is still yours to declare.

### Added

- **`aisef status --attempts`** — where attempts actually end, read from
  evidence rather than from memory: how many passed, how many were blocked at
  the gate and by which check, how many never reached a verdict. On a real
  10-story project it reported 34 attempts, 26% passed, and `review` as 18 of
  19 gate blocks.
- **`aisef doctor` names the agent credential it found** (again, names only).
- `RunResult.model` records which model actually answered, so two cohorts run
  behind the same alias can be told apart afterwards.

## 1.3.0 — 2026-09-12

Sixty-one commits had accumulated behind `v1.2.31` (2026-09-09): seven real
bugs from a greenfield end-to-end run, three cross-tier invariants, the v1.3
benchmark protocol, and this release's own housekeeping. Nothing here changes
a gate's verdict on evidence that was already correct.

### Cross-tier invariants (ADR-009)

- **Findings are objects now, not lines of text.** Every advisory claim is a
  `Finding` (`aisef/control/findings.py`) with a stable 16-hex id computed over
  `(source, trust, file, line, body, behavior_id, scope)`, an explicit
  lifecycle (`OPEN / CLOSED / REOPENED / SUPERSEDED / STUCK`), and one rule that
  closes bug 61 for good: closing without evidence requires both
  `force_prescription_match=True` and a matching `previous_prescription`. A
  reviewer can no longer reject the fix it prescribed by rewording the
  complaint. `agent` trust is rejected at construction; reviewer and security
  records must carry a 64-hex `contract_authority` digest.
- **The dev server now belongs to a candidate.** `AppServer` takes an optional
  `lease_root` / `run_id`, holds a non-blocking flock over
  `.aisef/lease/port-<run_id>.lock`, and probes `GET /_aisef/identity` before
  it believes a server is ready. Two runs of the same project can no longer
  grade each other's app — the failure mode that made a whole branch look
  blank in the September 5 A/B.
- **Budget is reserved before the call, not counted after it.**
  `BudgetGuard.reserve(...)` short-circuits when no caps are set, otherwise it
  locks the ledger, refuses an oversized estimate, settles the real cost on
  success and refunds on exception. Two defects in that seam were found by the
  wire-up harness on the same day and closed: the flock was carried on a file
  that `os.replace` swaps out from under it (now a sidecar lock), and the cap
  check ignored in-flight reservations, so two parallel calls each under the
  cap could both spend.
- New knobs, all default-off: `run.cost_cap_usd`, `run.turn_cap`,
  `run.wall_clock_cap_seconds`, `run.qualify_preflight`.
- `validation/phase3_wireup_e2e.py` checks all four seams end to end and
  writes `validation/phase3-report.md` — 16/16 at this release.

### Bugs found by measurement on a real greenfield run

- **A third of the reviewer's blocking findings never reached the author**
  (bug 64). The key used to reconcile the prose verdict against the JSON one
  was `(tag, file)` with the line number deliberately dropped — so three
  findings in one file collapsed into one key, the two sets compared equal, and
  the mismatch alarm built exactly for this case went blind with them.
- **A tag pasted after a sentence was not read as a finding** (bug 65). The
  model opened with a lead-in sentence and put `[block] path:line` after the
  full stop; the parser only recognised tags at the start of a line.
- **A story resumed after an interruption re-submitted the rejected candidate**
  (bug 66). The reviewer's blocking words lived in a local variable of the
  retry loop and died with the process, while the evidence survived on disk.
  The rerun opened attempt 1 with empty feedback and burned a paid attempt
  re-submitting what had just been rejected.
- **The reviewer never checked its own prescription against the write scope**
  (bug 67). The `[stuck]` rule only fired when the *author* claimed a deadlock.
  A correct finding whose only fix lay outside the story's write scope cost two
  attempts before the gate could conclude anything.
- **An attempt where the agent wrote nothing still cost a full gate run**
  (bugs 68 and 69). `changed_files` answers "what did this story change",
  measured against `base_ref` — correct for the reviewer's diff, wrong as an
  answer to "did this session write anything". On a retry the previous
  attempt's work made a silent session look like a productive one: candidate
  frozen, nop + test + lint + e2e + a11y + mockup + review + security all run,
  one attempt consumed. The first-attempt variant slipped past both the old
  zero-output check (it *did* call tools) and the first fix.
- **My own no-op guard buried finished work under "already known"** (bug 70).
  The fix above assumed a gate verdict is a pure function of the tree. It is
  not: the gate also reads the spec and the prompt, and both can change between
  attempts. A story whose previous block was caused by an architecture
  decision — since corrected — was told a rerun would produce the same result,
  while its branch already carried the finished feature.

### Windows, and a credential that was retried three times

These landed after the version bump and before the tag, because a release that
is broken on a declared platform is not a release.

- **The phase-2 locks used a POSIX-only flag** (bug 71). `BudgetGuard` and the
  dev-server lease opened their lock files with `os.O_CLOEXEC`, which does not
  exist on Windows — every reservation and every lease raised there, so the
  whole phase-2 seam was dead on half the supported operating systems. Windows
  CI caught it on its first run against this code.
- **The memory store's atomic write was atomic only on POSIX** (bug 72).
  `os.replace` is refused on Windows while any handle to the destination is
  open, so a reader overlapping a writer crashed the write. `_compat` now owns
  both: `open_lock_fd` picks the flag by name, `atomic_replace` retries briefly
  on Windows and nowhere else.
- **A rejected credential is no longer treated as an infrastructure error.** A
  401 carries the same marker as a transient API failure, so the harness
  retried it — 176 seconds per attempt, $0 recorded, three times, on a
  credential that would be rejected identically each time. `auth` is now its
  own exit status, outside the retryable set, and the message names the
  environment variable that decided who the session was (the name, never the
  value) instead of printing `401`.

- **The simulator shelled out to a tool Windows does not have** (bug 73).
  `gold.patch` was applied with GNU `patch`; on Windows there is none, and
  because "no applier" and "did not apply" both returned an empty list, five
  bench tests failed with no diagnostic at all. It now applies through
  `git apply` inside an initialised scratch repository — the mode where a hunk
  that will not place is an error rather than a `Skipped patch` line with exit
  0 — and falls back to `patch` where that is available.

- **Line endings, on both sides of the simulator's write** (bug 74). Applying
  gold and then reverting left the tree dirty on Windows: the write translated
  `\n` to `\r\n`, and the revert wrote the blob's bytes into a working tree
  that had been checked out with `core.autocrlf`. Writes now disable
  translation explicitly, and reverting goes through `git checkout` so git
  applies the same filters it used on the way out.

- **`doctor` says which credential an agent session will use.** Names only,
  never values: an expired key in the operator's shell outranks the client's
  own login, and the only previous symptom was every session returning 401
  after burning its full wall-clock.

### Benchmark v1.3

- Client adapters drain stdout concurrently and keep the partial stream when a
  run times out, so a timeout no longer reads as zero data.
- Twelve harder tasks (`bug-a2-multi-*`, `-state-*`, `-sec-*`): 108 fail-to-pass
  and ~750 pass-to-pass tests, averaging 4.5 source modules per fix against the
  1.4 of the v0.3.0 set.
- `SimulatedWeakAdapter` — a deterministic four-strategy control that costs
  nothing and, crucially, is reported for what it is: it never invokes a hook,
  so AISEF ≡ bare on it is expected and says nothing about guards.
- `tests/bench/tasks/MANIFEST.sha256` pins the fixture bytes; the dataset is
  frozen under the protocol, and the corrected simulator re-run is recorded
  next to the original numbers rather than replacing them.

### Documentation that can no longer drift

- Three counts in the documentation had drifted from their sources:
  `STABILITY.md` said 58 config keys where `DEFAULTS` had 68, both READMEs said
  thirty-one bugs where the taxonomy had reached 70, and the taxonomy's own
  section heading still said "22–63". All three are corrected, and four
  meta-tests now read the source and fail if any of them drifts again.
- Every relative link in `docs/`, both READMEs and this file is checked for a
  target that exists — and, for anchors, a heading that generates it. The test
  was written because `BENCH-REPORT-v1.3.md` was pointing at a bench phase
  queue that had never been written down; that queue now exists in
  `docs/EXECUTION-PLAN.md`.
- The four remaining semantic issues from the pre-Phase-2 audit are written
  down in `ADR-009 § Open`, reconstructed from on-disk evidence with that
  provenance stated, because the original list was never recorded anywhere.

### Tooling

- `ruff` is now a CI gate with an explicit rule set (`F`, `B`, `E9`) chosen by
  measurement, and the deferred families each carry a reason in
  `pyproject.toml`. Enabling it caught a live defect introduced in the same
  session, which is the argument for having it.
- A wheel-smoke CI job installs the built wheel into a clean environment and
  checks the three things unit tests cannot: the command runs, the packaged
  runtime data (prompts, rules, skills, assets, catalog) is really inside the
  wheel, and a blank project can be initialised by the installed command. This
  is the bug-31 class — a wheel whose hooks pointed at a path that did not
  exist, valid syntax, no guard running at all.

### Bugs 54–63 — Windows CI and the greenfield run that preceded it

- **An MCP server's own notes killed a story** (bug 62). Serena writes
  `.serena/memories/*.md` into whatever tree it is pointed at, on its first
  call — which is every session. `diff-scope` saw a file outside `write_scope`
  and blocked every command the agent ran, all three attempts, and seven other
  gate checks went red as a consequence. Same class as `node_modules` and
  `*.tsbuildinfo`: it appears because the story *ran*, not because the story
  *wrote* it. The framework does not choose the user's MCP servers and must not
  fail their stories for having them.

- **The write-scope message cut off before naming the file** (bug 63). It
  printed the twenty-seven-entry scope list first and the offending file last,
  and every consumer folds the message to one line. Offending files come first
  now.

- **The reviewer rejected the fix it had prescribed** (bug 61). Round 2 asked
  for "a defined post-load quiet period"; the author added one; round 3 blocked
  the same line because a defined window is finite, and asked for deterministic
  timer control instead. The story spent all three attempts doing exactly what
  it was told. The rule against moving goalposts only covered promoting
  *should fix* to *block*; it now covers rejecting your own prescription, and
  names `[stuck]` as the outcome when no change the author can make would
  satisfy the criterion.

- **An infra retry in the plan phase left no line in the log** (bug 60).
  `todo-e3`'s ux phase failed twice with `APIError: SSE read timed out`, was
  correctly classified as infrastructure and retried both times — and the log
  showed one motionless `phase=ux START` for thirty-six minutes. The story
  loop has logged this since ADR-005 V11; the plan loop never did. Agent
  `START` lines now also carry the timeout, so silence has a readable bound.

- **On Windows the OpenCode client was launched with its flags inside
  `cmd.exe`'s own arguments** (bug 59). `build_command` inserted `--format
  json` at index 2, which is right when the resolved program is one token and
  wrong when it is three — and it is three on Windows, where `opencode` is a
  `.cmd` shim and resolves to `cmd.exe /c <shim>`. The client ran as `cmd /c
  --format json opencode.cmd run …`. Bug 32's shape a third time: a command is
  not a word. argv is now built in order.

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
