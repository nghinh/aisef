# AISEF 2.1 — full suite on the determined commit (B-03 round 4c)

| | |
|---|---|
| commit | `45554e0c19bc56c8dc6854fa96ccdb6d34a108d4` (branch `v2.1/foundation`; a clean detached worktree, `git status` empty before and after) |
| command | `python3 -P validation/v2/owned_run.py --out … -- python3 -m unittest discover -v -s tests`, under `env -i` with a fresh HOME / XDG_* / TMPDIR, PATH without any directory holding an `opencode` executable, under the machine-wide heavy lock (`campaign-3/tools/run-suite.sh`) |
| machine | macOS Darwin 25.5.0 arm64, Python 3.14.7 (`/opt/homebrew/bin/python3`) |
| time | 2026-10-14T18:55:56Z → 2026-10-14T19:56:55Z (3,654.9 s of tests) |
| result | **Ran 7305 tests — OK (skipped=85), exit 0** |
| failures / errors | **0 / 0** |
| owned processes | before 0, at exit 0, after 0, escaped 0, released empty (posix-session-and-group, 3,658 s) |
| the operator's real OpenCode store | stat'ed before and after: identical (`real-store-before.json`, `real-store-after.json`) |
| hermetic proof | env names, empty roots, `which opencode` = none, before and after (`hermetic-proof-*.json`) |

## What this run is, and is not

* It is the suite on **`45554e0` and nothing else**. Commits after it that touch only `closure-evidence/` (this record)
  do not carry its result: the checkers that read evidence were run again on the new HEAD (below).
* The pre-run at `1043186` had 7 failures (the suite's encoding rule for two child-process calls and six records that
  had been removed to be regenerated). Nothing was skipped, loosened or re-oracled to get here: the two calls name an
  encoding; the records were regenerated in dependency order by their own tools (see `README.md`).
* 85 skips, all by an explicit condition of the test (`-v` output, `suite-45554e0/suite.txt`): 41 mock-up/playwright not
  installed on this machine, 19 `references/` not cloned, 10 `AISEF_TEST_DOCKER=1` (needs a daemon), 3 the real Open Code
  Review binary (`AISEF_TEST_OCR_EXE`), 2 release-only (`AISEF_RELEASE=1`), 2 dogfood (`AISEF_DOGFOOD=1` and `claude`),
  1 SIGABRT crash-reporter dialog (`AISEF_ABORT_SUBJECT=1`), and the rest an absent optional fixture or an abstract
  base class. None is a test this round disabled.
* Not covered: Windows, Linux CI (no push), the Docker-gated tests, a live model.
