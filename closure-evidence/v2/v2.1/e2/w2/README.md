# E2 — workload W2 (brownfield): the evidence-discipline linter of `bread` plus a requirements delta

Lane W2 of the E2 controlled campaign (`docs/v2.1/EXPERIMENT-PLAN.md`; owner decision
`closure-evidence/v2/v2.1/round-5/OWNER-DECISION-2026-10-18-E2.md`). Prepared offline on 2026-10-18 13:01–13:16 +0700:
no provider request, no `opencode`, no `aisef run`; the mutation campaign's directories were not touched. Everything
below is a **technical proposal**; the owner approves the hidden evaluator and the arms' bundle (`APPROVE.sh`) before the
first run, and may reject the workload itself. Commands and outputs: `dry-check/commands.log`. Provenance: `PROVENANCE.json`.

## 1. What was chosen, and why not the brief's candidates

| | |
|---|---|
| source | `~/Downloads/projects/bread` at `6fde318ecac1e447f49d6b642707c78f17ddcb63` (2026-10-14): a working project of the owner, 418 commits, authors Nghi Nguyen 407 / "Claude Fable 5" 11, **never developed by AISEF** (no `.aisef/`, no `.opencode/`, no `closure-evidence/`, no commit mentioning aisef) |
| subtree | `infrastructure/ci/`: `evidence_discipline.py` (300 lines, stdlib only, `argparse` CLI; 300/300 lines blamed to Nghi Nguyen, introduced 2026-09-01), `test_evidence_discipline.py` (pytest, 16 tests), `run_registry.json` (16 valid run ids), the two `__init__.py` |
| baseline | one deterministic commit `cd7d5aaee2c9760004c75cf3bf6beecd5f04c772` (tree `96aa0e83…`, `files_sha256 635de23b…`): the five files by `git archive`, plus three files of this lane — `docs/requirements-delta.md` (the task), a three-line `README.md`, a five-line `.gitignore`. `init_repo.sh <new dir>` reproduces it; run twice, same sha |
| task | `baseline/docs/requirements-delta.md`: four maintainer changes — directory roots (§1), an explicit run registry with strict errors (§2), `--format json` (§3), what must not change (§4), unittest tests for the new behaviour (§5) |

**Deviations from the brief, stated.**

1. `~/Downloads/projects/todo-cli` and `todo-oc` **do not exist on this machine** (`find /Users/nghinh -maxdepth 6`,
   `mdfind`, `~/.Trash`: nothing). `~/Downloads/projects/todo` exists but is disqualified: its 24 commits are all authored
   "AI-SDLC", it carries `.aisef/`, `.opencode/` and `_bmad-output/`, and its code commits are AISEF V1 story runs
   (`STORY-01-02: candidate attempt 1`, …) — exactly what W2 must not measure on.
2. **A Node project cannot be the W2 subject.** The brief suggests `cli_invocation` of `node src/cli.js`; the probe runs a
   *Python module* (`runpy.run_module`) under `python -I -S -B` (`aisef2/probe/cli_invocation.py` §Subject) — no Node, and no
   site-packages either. So the repository had to be stdlib-only Python. Of everything under `~/Downloads/projects`
   (survey in `commands.log`), the only small, coherent, stdlib-only, hand-written unit with behaviour a probe can observe is
   this linter. `bread/packages/protocol/codegen.py` (also stdlib) was rejected: it writes to paths two directories above its
   own and shells out to `ruff`.
3. **A filtered subtree, not a whole repository.** The brief allows "a fresh repo from the filtered tree with one commit;
   record provenance" for stripping `.opencode/`; this lane applies the same mechanism to a subtree. The five files are the
   commit's bytes (blob ids in `PROVENANCE.json`); nothing of the owner's code was edited.
4. Three files in the baseline are **this lane's** (task, README, `.gitignore`). They are documentation and hygiene, not
   product code; they are listed with digests in `PROVENANCE.json`. The `.gitignore` exists so that a delivered `main`
   does not carry `__pycache__` (canary finding C-1), which would otherwise differ between arms by accident.
5. The story tests are **unittest** files the developer writes (`§5`), because the kernel runs story tests with
   `unittest` in a venv without pip (`aisef2/quality/test_execution.py` UNITTEST runner) and the existing test file is
   pytest. The existing pytest file stays as brownfield reality (`§4.1`); pytest is importable from the Homebrew
   interpreter on this machine, so an arm can run it.

## 2. The two bundles

Built with `python -P -B -m aisef bundle seal … --repo <baseline>` against commit `cd7d5aae…`; both bind
`docs/requirements-delta.md` at sha256 `7b2c0bd3…`; **neither carries an approval** (`aisef bundle lint`: `NOT_READY`,
`to_approve` listed, admission not run — `arms/lint.json`, `hidden/lint.json`). With the owner's approvals both are READY:
`dry-check/baseline.json` shows `lint_verdict: READY`, `admission.admitted: true`, `criteria_without_calibration: []`
on technically approved copies (`human:w2-dry-check`, scratch only, never committed).

| bundle | file (sha256) | contracts / specs | stories | probe kinds and classes |
|---|---|---|---|---|
| arms (B, C run it) | `arms/bundle.json` `c0b52db9…`; plan `d6c8b613…` | 7 / 7 | S1 §1 → S2 §2 → S3 §3 | `cli_invocation` exits, exits_streams; `file_artifact` python_imports |
| **hidden** evaluator | `hidden/evaluator.json` `0dda8a59…`; plan `92b9572a…` | 10 / 10 | HS1, HS2, HS3 | `cli_invocation` exits, exits_streams, exits_files; `process_effect` scenario_returns; `file_artifact` python_imports |

The hidden contracts use **different data** from the public examples (other sentences, figures, run ids and file names —
none of them named here, since this README is scanned as a public artefact too), a different `within_s` (25 vs 30) and an
explicit `suffixes` on the stdlib check, so that no hidden stimulus or observable string equals a public one
(`dry-check/leaks.json`: `json_hits {}`, `plain_hits {}`).

| hidden contract | role | what it observes | at the baseline (measured) |
|---|---|---|---|
| H-DIR | INTRODUCE §1.1–1.2 | `--root <dir>`: `a.md` before `b.md` reported, `node_modules/` and a `.txt` not scanned (stdout regex), exit 1 | UNSATISFIED (exit 0, nothing scanned) |
| H-MISSING | INTRODUCE §1.4 | `--root <absent file>`: exit 2, stderr names the path | UNSATISFIED (exit 0) |
| H-REG-OK | INTRODUCE §2.1 | `--registry <ws file>`: both citation forms accepted, exit 0 | UNSATISFIED (argparse exit 2) |
| H-REG-BAD | INTRODUCE §2.2 | `valid_runs` a string: exit 2, stderr `run registry:` + path | UNSATISFIED |
| H-REG-MISSING | INTRODUCE §2.2–2.3 | `process_effect`: `cli_main([... --registry <absent>])` returns 2 | UNSATISFIED (raised SystemExit) |
| H-JSON | INTRODUCE §3.1 | `--format json`: stdout holds the report keys and the figure, exit 1 | UNSATISFIED (argparse exit 2) |
| H-CITED | PRESERVE §4.3 | a figure cited to a default-registry run id: exit 0 | SATISFIED |
| H-TARGET | PRESERVE §4.3 | `target:` and fenced lines not reported, the `observed:` line is | SATISFIED |
| H-REPORT | PRESERVE §3.2 | `--report` writes today's document byte for byte (`exits_files`) | SATISFIED |
| H-STDLIB | PRESERVE §4.2 | `python_imports` outside the stdlib in the linter: 0 | SATISFIED |

So the hidden evaluator **refutes the baseline on every INTRODUCE and holds on every PRESERVE** (10 EXECUTED; 4/10 SATISFIED),
which is what W2 needs: the escaped-defect rate of a candidate is measured against a baseline that is known to fail the
six and pass the four. The arms' bundle behaves alike (7 EXECUTED; 2/7 SATISFIED at the baseline: A-CITED, A-STDLIB).

## 3. Leak dry-check (`tools/dry_check.py`, records in `dry-check/`)

* Every distinctive JSON string of the hidden evaluator (`harness.distinctive`, 20 strings) and every plain stimulus string
  (`tools/leaks_w2.py`, 20 strings after excluding the public vocabulary `infrastructure` and `report.json`) was searched in
  the 21 public artefacts — the arms' authoring and bundle, the task text, the settings, this README, every file of the
  baseline tree: **0 hits of either kind**.
* Controls on synthetic session streams: a hidden stimulus with no backslash → `harness.leaks` reports it (positive); a
  public stimulus and a public sentence → nothing reported (negative); a session naming one hidden file and one hidden
  sentence → `leaks_w2` reports it (3 strings).
* **A limit of `harness.leaks`, measured, not fixed here:** a hidden stimulus whose JSON holds a backslash (`\n` inside a
  workspace file's text) nested in a session's own JSON is *not* found by its quote-only escape (`escaped` control: harness
  0, leaks_w2 1). W2's stimuli are files, so most of them hold `\n`. The orchestrator should scan every arm's sessions with
  **both**: `harness.leaks(sessions, evaluator)` and
  `python -P -B tools/leaks_w2.py hidden/evaluator.json <sessions dir> --strings dry-check/plain-strings.json`. A fix in
  `harness.py` (search the JSON-string-escaped form too) is a one-line change that this lane did not make, so as not to
  alter the measurement tool from a workload lane.

## 4. Settings proposals for arms B and C — and the `mycombo` identity limit

`settings-B.json` (no `review`: the 2.0.0 advisory rule) and `settings-C.json` (`review: fix-loop, high`) load under
`aisef2.app.settings.load` and differ in that one key. Caps are the plan's: 58 requests, 700 turns, 30 M input, 0.5 M
output, 80 turns per session, `preflight.chat_probes 2`. No `prices` key: 9router's price for `mycombo` is unknown here, so
every cost is `null`, never 0 (`app/usage`).

**Not verified, and the provider lane's to settle:** `route 9router/mycombo`, `served_model "mycombo"`, `listed_owner null`,
`model_limit {200000, 32768}` are placeholders. The preflight attests a route only when the listing names the model and
**every chat probe is served by `served_model`** (`aisef2/app/preflight.py`); `mycombo` is a router alias whose backing model
varies per request (MiniMax-M3 seen) and answers in OpenAI or Anthropic shape. If the answers report the backing model, the
preflight is an identity stop and no AISEF arm starts — a known limit to record in the result (`identity_confidence`), not
to hide. The direct arm has no preflight and is not stopped by it; a pair whose B/C arms cannot start is then a result
record of its own, not a comparison.

## 5. How the orchestrator runs W2

1. `zsh closure-evidence/v2/v2.1/e2/w2/init_repo.sh <new dir>` → `cd7d5aaee2c9760004c75cf3bf6beecd5f04c772`;
   `harness.source_identity(<dir>, "HEAD")` must give `files_sha256 635de23b…` (`PROVENANCE.json`).
2. Owner: `zsh APPROVE.sh human:<name>` → `hidden/approved.json` (keep it out of every arm's reach) and `arms/approved.json`;
   `aisef bundle lint` on both prints READY.
3. Manifests (18 runs ÷ 2 workloads = 9 here: 3 arms × 3 repeats) with `workload.id w2`,
   `workload.requirements_sha256 7b2c0bd3…`, `source` from step 1, `evaluator` = `harness.evaluator_identity(hidden/approved.json)`,
   `bundle.sha256` of `arms/approved.json` for B/C; `pair_problems` empty per pair.
4. Arm A: `harness.direct_arm(manifest, out, task=<baseline/TASK.txt>, …)`. Arms B/C:
   `python -P -B -m aisef run --project arms/approved.json --settings settings-{B,C}.json --repo <dir> --out <run> --anchor-out <file>`
   (after `--check`).
5. Per arm: `harness.evaluate(<candidate repo>, <candidate sha>, hidden/approved.json)`; `harness.leaks` **and** `tools/leaks_w2.py`
   on the sessions; `harness.result(...)`; `harness.replay` offline.

## 6. What this lane did not do / not verified

* No run of any arm; no provider traffic; no `opencode`. Whether `mycombo` passes the preflight: not verified (provider lane).
* The approvals: none written. The dry check approved *copies* in the scratchpad as `human:w2-dry-check` for the measurement
  only; those files are not in the repository.
* The baseline's behaviour under the arms' developer sessions (e.g. whether a weak model touches `test_evidence_discipline.py`)
  is unmeasured; the hidden evaluator does not depend on that file.
* `tests/v2/test_v21_experiment.py` ran green (5 tests, 4.0 s) in this worktree; no other test file was run.
