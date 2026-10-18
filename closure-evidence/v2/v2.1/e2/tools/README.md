# E2 launch kit — the operator's tools for the REAL E2 campaign

Lane `lane/e2-launch`, 2026-10-18, from `v2.1/probe-window` at `4a69c27e`. The dry run (`../dry-run/`) proved the
driver `validation/experiments/campaign.py` on both workloads with a fake client and a loopback provider. This kit is
what the operator runs to launch the paid campaign (18 runs = {w1-a, w2} × {direct, aisef, aisef+} × reps 1..3, plan
`docs/v2.1/EXPERIMENT-PLAN.md`) — built and tested here OFFLINE only, with the same fake client and loopback provider.
**Nothing in this lane ran the real client, an `aisef run` that could reach a provider, or a network request**; the
mutation campaign's directories and lock were not touched; no process was signalled.

## 1. Files

| file | what |
|---|---|
| `e2_setup.py D [--approver human:NAME] [--settings-dir DIR]` | builds the campaign directory `D` (§2); `--adopt-owner` replaces the provisional approvals by the owner's (§4) |
| `run_e2.sh D [MAX_RUNS]` | the one command of a launch or a resume: machine checks, the heavy lock, then `e2_launch.py` under it (§3) |
| `e2_launch.py D MAX_RUNS` | one invocation of the driver, hermetic (run by `run_e2.sh`, never by hand): client identity, store stats, the driver, replay, summary, records, secret scan |
| `e2_status.sh D` | one line: running?, STOP?, runs done/failed/refused of 18, requests, tokens, the last line of `campaign.log` |
| `test_launch_offline.sh [SCRATCH]` | the whole kit end to end, offline (§5): the only thing this lane executed |

Pinned: `validation/experiments/campaign.py` (the driver), `aisef2/` (the kernel), `../settings/arm-*.json` (the real
settings: endpoint `https://9router.vnteki.com/v1`, route `9router/mycombo`, served model `MiniMax-M3`, no price
table — every `cost` is `null`, never 0), `../w1-a/` and `../w2/` (the workloads), `../preflight-mycombo/tools/
xdg-opencode.json` (the client configuration shape), `../../isolation/tools/store_stat.py`, `../../campaign-9/tools/
heavy.sh` (the machine-wide lock, used by path).

## 2. The campaign directory `D` (`e2_setup.py`)

`D` is new and **outside the repository** (refused otherwise); everything of a campaign lives there, every path in
`CAMPAIGN-real.json` relative to it (the directory can be moved as a whole).

| under D | what |
|---|---|
| `base/w1-a`, `base/w2` | the baselines `init_repo.sh` builds; their commit is checked against the bundles' `plan.baseline` (`e6901e56…`, `ceae06eb…`) and the tree clean |
| `approved/<w>-{arms,evaluator}.json` | the four bundles approved (§4): the OWNER's `approved.json` when APPROVE.sh has written it, else PROVISIONAL |
| `settings/arm-*.json` | copies of `--settings-dir` (default `../settings`); the three must name one provider, endpoint and key variable |
| `client/config/opencode/opencode.json` | `XDG_CONFIG_HOME` of every run: provider `9router` at the settings' endpoint, `apiKey: {env:NINEROUTER_API_KEY}` — derived from the settings, never a value |
| `client/{data,state,cache}`, `home`, `tmp` | `XDG_DATA_HOME/STATE/CACHE`, `HOME`, `TMPDIR` of the hermetic run: the operator's own OpenCode store (`~/.local/share/opencode`) and configuration are never read or written |
| `CAMPAIGN-real.json` | 18 runs, **rep-major**: `w1-a-r1-direct, w1-a-r1-aisef, w1-a-r1-aisef-plus, w2-r1-direct, w2-r1-aisef, w2-r1-aisef-plus`, then rep 2, then rep 3 — so a stop after any multiple of six leaves complete pairs, and after six runs the plan's "re-estimate after 3 reps" has one rep of everything. `task_text` is `../w1-a/direct-task.txt` / `../w2/baseline/TASK.txt` without the final newline |
| `SETUP.json`, `APPROVALS.md` | the record of the step (aisef HEAD, baselines, approvals with sha256 and status, settings sha256, the run order) |
| `out/` | the driver's OUT (written by `run_e2.sh`): `<run_id>/MANIFEST.json` (sealed once, 18 at the first launch), `RESULT.json`, `arm/…`, `campaign.log`, `CAMPAIGN.json` |
| `launch/<stamp>/` | per invocation: `launch.json`, `store-before.json`, `store-after.json`, `exit.txt`, `end.json` |
| `run.log`, `replay.txt`, `summary.txt`, `records/` | the driver's output (appended per launch), the latest replay and summary, the copy for the repository (§3.3) |

## 3. The operator's order of operations

```sh
cd <AISEF repository root>                       # the checkout holding this lane (aisef2/, validation/, closure-evidence/)
PY="nice -n 19 /opt/homebrew/bin/python3 -P -B"; T=closure-evidence/v2/v2.1/e2/tools
D=/path/outside/the/repository/e2-campaign       # new

# 0 (optional, recommended): the owner's approvals first, so they bind the runs themselves (§4)
#    PYTHONPATH=. sh closure-evidence/v2/v2.1/e2/w1-a/APPROVE.sh human:<name>
#    (cd closure-evidence/v2/v2.1/e2/w2 && zsh APPROVE.sh human:<name>)
$PY $T/e2_setup.py $D                            # 1: D built; the approvals' status printed and in D/APPROVALS.md
export NINEROUTER_API_KEY=…                      # 2: the key, in THIS shell's environment only (never an argument, never printed)
zsh $T/run_e2.sh $D 6                            # 3: rep 1 (six runs), then look; or 18 for everything
zsh $T/e2_status.sh $D                           # 4: progress, any time (reads records only)
tail -f $D/out/campaign.log                      #    the live view (run.log is the driver's stdout, flushed per line: -u)
zsh $T/run_e2.sh $D 18                           # 5: the rest (a run with RESULT.json is skipped: resume)
```

`run_e2.sh` **refuses** (exit 2) while the heavy lock `<scratchpad>/heavy.lock.d` is held by a live job or any
`mutation.py run` process exists (campaign 9 must be finished — it does not wait behind it), without
`NINEROUTER_API_KEY` in the environment, and (exit 3) while `D/out/STOP` exists. Then it takes the heavy lock
through `campaign-9/tools/heavy.sh` (by path; the lock's owner line reads `e2-campaign <pid> <time>`) and runs
`e2_launch.py` under it, nice 19.

### 3.1 What one launch does (`e2_launch.py`, recorded in `D/launch/<stamp>/launch.json`)

1. The client: `CLIENT_EXE` from the environment, else the first `opencode` on the operator's PATH — `launch.json`
   says which (`client.from`), its realpath and sha256; its `--version` is run in the hermetic environment (below)
   and becomes the driver's `--client-version`. A file not named exactly `opencode` is refused (the driver's rule).
2. `store_stat.py $HOME` → `store-before.json` (os.stat of the operator's OpenCode store: nothing opened).
3. The hermetic environment of the driver and so of every arm: `PATH = <client's dir>:<python's dir>:<git's dir>:
   /usr/bin:/bin` (never `~/.opencode/bin` or `~/.npm-global/bin` unless the client is there — asserted:
   `opencode` on that PATH is the client's realpath), `HOME=D/home`, `XDG_CONFIG_HOME=D/client/config`,
   `XDG_DATA_HOME/STATE/CACHE=D/client/{data,state,cache}`, `TMPDIR=D/tmp`, `LANG`, `PYTHONPATH=<repo>`,
   `PYTHONDONTWRITEBYTECODE=1`, and `NINEROUTER_API_KEY` copied from the operator's environment — in the child's
   environment only; `launch.json` records variable NAMES. Nothing else of the operator's environment.
4. `python3 -u -P -B validation/experiments/campaign.py run --campaign D/CAMPAIGN-real.json --out D/out --client-exe
   <client> --client-version "<its --version>" --max-runs MAX_RUNS`, cwd `D`, stdout+stderr appended to `D/run.log`
   (header lines `=== <time> launch <stamp> …` and `=== <time> driver exit <code> wall_s <s>`). The driver's exit: 0
   done, 3 stopped (`--max-runs` reached or `D/out/STOP`), 2 refused before any arm (a manifest or pair problem, the
   client not on PATH) — recorded in `exit.txt`; never read as a failure by the launcher.
5. `campaign.py replay --out D/out` → `D/replay.txt` (empty = every recorded candidate re-evaluates to its record)
   and `campaign.py summary --out D/out` → `D/summary.txt` (one JSON row per workload × arm).
6. `store_stat.py $HOME` → `store-after.json`; `before == after` printed and in `end.json` (`store_equal`).
7. `D/records/` rebuilt (§3.3) and the **secret scan of the whole of D** (not `.git` objects): the number of files
   holding the key's value, counted in-process (the value is never printed; any hit: exit 1 and "do not copy D
   anywhere"), and mixed-case tokens of 40+ characters (upper, lower and digit together; a sha256, a labelled
   `PPS-<sha256>`, a path component do not qualify) listed masked for the operator to judge. Then the rsync command
   (§3.3) is printed, never run.

### 3.2 STOP and resume

`touch D/out/STOP` — the driver stops before the next run (the run in flight finishes and is recorded); the launcher
then still replays, summarises and copies the records. To resume: `rm D/out/STOP; zsh $T/run_e2.sh $D 18` — runs
with a `RESULT.json` are skipped, the sealed manifests reused (never rewritten), a new `launch/<stamp>/`. The plan's
budget rule is the operator's: `summary.txt` gives `requests` and `tokens` per workload × arm (`cost` stays `null`
without a price table); `e2_status.sh` sums them.

### 3.3 Where the records go

The launcher never writes under the repository. `D/records/` holds the copy for it: from `D/out`, every
`MANIFEST.json`, `RESULT.json`, `arm/ARM.json`, both `PREFLIGHT.json`, `arm/run/RUN.json`, `EVIDENCE.json`, the
kernel's journal, every session stream (`arm/sessions/*.jsonl`, `arm/run/sessions/*.jsonl` — the kernel redacts
the key in them, `app/client.redact`), `run.stdout/stderr`, `exit.txt`, `campaign.log`, `CAMPAIGN.json`; from `D`:
`SETUP.json`, `APPROVALS.md`, `CAMPAIGN-real.json`, `run.log`, `replay.txt`, `summary.txt`, `approved/`, `settings/`,
the client configuration (an `{env:…}` reference) and `launch/`. Never the arms' workspaces or the kernel's repository
clones. `records/INDEX.json`: sha256 and size of every copy, and the secret scan. The command printed at the end:

    rsync -a D/records/ <repo>/closure-evidence/v2/v2.1/e2/runs/<YYYY-MM-DD>/

The operator runs it after reading the scan's lines, then commits `closure-evidence/v2/v2.1/e2/runs/<date>/` as a
record (not this lane: this lane commits no run).

## 4. What is provisional, and how the owner's approval replaces it

The kernel compiles a contract only with an approval by `human:<name>` (`aisef2/product/approval.py`;
`bundle_cli.approve` passes the approver through). `e2_setup.py` therefore approves each of the four sealed bundles
(`../w1-a/{arms,evaluator}/bundle.json`, `../w2/{arms/bundle,hidden/evaluator}.json`) with `--approver`, default
**`human:orchestrator-provisional`** — a TECHNICAL approval of scratch copies so the kernel can run and the hidden
evaluator can score; it records no owner acceptance of any contract. `D/APPROVALS.md` states this per bundle.

The owner's approval is `APPROVE.sh` of each lane (`aisef bundle approve`, one contract per command, written beside the
bundle as `approved.json`; this lane did not run it — `ls` of the four bundle directories still shows only
`authoring.json`, `bundle.json`[, `lint.json`]). It replaces the provisional one in two ways:

* **Before setup** (recommended): `e2_setup.py` finds `<lane>/<dir>/approved.json`, checks its contracts and
  requirements (ids and hashes) are those of the sealed bundle, and copies it — `APPROVALS.md` says `owner`. The
  sealed manifests then bind the owner-approved files (`bundle.sha256`, `evaluator.sha256`).
* **After runs**: `e2_setup.py $D --adopt-owner` (between two invocations of `run_e2.sh`, never during one) checks
  every owner file exists, holds the same contracts and requirements, lints READY; keeps the provisional copies under
  `D/approved/provisional/`; replaces `D/approved/*.json`; appends to `APPROVALS.md`; prints the replay command.
  `campaign.py replay --out D/out` then evaluates every recorded candidate under the owner-approved evaluator
  (`RESULT.json.evaluator_path` is the replaced file; nothing printed = the same evaluation). What this cannot change:
  the runs already made used the provisional bundle copies, and their manifests bind those files' sha256.

## 5. The offline test (`test_launch_offline.sh`) — what this lane executed

The kit end to end with `e2_setup.py … --approver human:test --settings-dir ../dry-run/settings-offline` (endpoint
`http://127.0.0.1:47311/v1`, key variable `AISEF_DRYRUN_KEY`), then `E2_OFFLINE=1 CLIENT_EXE=<scratch>/fakebin/opencode
run_e2.sh D 2`. PATH is set to `<scratch>/fakebin:/opt/homebrew/bin:/usr/bin:/bin` before anything runs (no
`~/.opencode/bin`, no `~/.npm-global/bin`), `NINEROUTER_API_KEY` and `CLIENT_EXE` unset, `TMPDIR` under the scratch.

`E2_OFFLINE=1` in `run_e2.sh`: no heavy lock, no campaign-9 check, no key check (campaign 9 was running during this
lane). In `e2_launch.py`: the client is refused unless byte-identical to `../dry-run/tools/fake_opencode.py`; the
settings must name the dry run's loopback endpoint; `dryrun.Provider` (the loopback fake provider of the dry run,
imported from `../dry-run/tools/dryrun.py`) answers from a daemon thread of the launcher's own process — the only
socket, gone with the process; the fake key `AISEF_DRYRUN_KEY`; `store_stat` on `D/home`. Everything else is the real
code path: the same hermetic environment, the same driver invocation, replay, summary, records, scan.

Result (2026-10-18 16:18:40–16:20:04 +07, `test rc=0`; the verbatim output is in the lane's report): 18 manifests
sealed and paired; `w1-a-r1-direct` 12/12 and `w1-a-r1-aisef` 12/12 (identity ATTESTED, valid), stopped at
`--max-runs 2` (driver exit 3); replay silent; two summary rows; `opencode` resolved to the fake on the test's PATH
and on the recorded hermetic PATH; env names in `launch.json` hold `AISEF_DRYRUN_KEY`, not `NINEROUTER_API_KEY`; no
key value and no `NINEROUTER` string under D; `store_equal true`; 60 record files; status line `done 2/18 failed 0
refused 0 requests 17 tokens in 1080 out 63 | …`.

Also checked by hand: `run_e2.sh` in real mode on the test's D refused at once with `the heavy lock is held by a live
job: campaign9 42612 …` (exit 2, nothing started); `--adopt-owner` exercised on a scratch COPY of the lane directories
holding approvals by a scratch `human:owner-scratch-test` (the repository's lane directories untouched): the four
files replaced, the provisional copies kept, and `campaign.py replay` on the two recorded candidates afterwards silent
(exit 0: the same evaluation under the adopted evaluator).

## 6. Not verified

* Any real session, any provider request, the real client's `--version` or its behaviour under `HOME=D/home` and the
  `XDG_*` directories (the preflight-only run `../preflight-mycombo/` is the only evidence the real client's config
  shape routes `9router` as the settings say), Windows or Linux.
* The STOP path (`D/out/STOP`) was not exercised (the lane creates no STOP file anywhere); the driver's own STOP check
  is the dry run's and the driver's unit tests'.
* The real-mode checks `mutation.py run` process present / `NINEROUTER_API_KEY` unset were not reached (the lock check
  fires first while campaign 9 runs).
* The 40+ mixed-case token heuristic on real session streams (base64 or JWT-like strings would be listed; the
  operator judges them).
