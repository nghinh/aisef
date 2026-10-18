# E2 dry run — the campaign driver on W1 and W2, offline (plan step "replay before spend")

Lane `lane/e2-dry-run`, 2026-10-18 15:11–15:40 +07, from `v2.1/probe-window` at `b278ffa7`. The whole E2 campaign
(`validation/experiments/campaign.py`: 2 workloads × 3 arms × 1 rep = 6 runs) driven on the real workloads
`../w1-a` and `../w2` with a **scripted fake client** and a **loopback fake provider**, so the plumbing, the manifests,
the pair checks, the evaluation, the rollback accounting and the records are proven before any paid run. No `opencode`
binary, no `aisef run` that could reach a provider, no network request: the only socket is `127.0.0.1:47311`, opened
and answered by this lane's own process. The mutation campaign's directories were not touched; nothing was killed.

**What this is not:** no owner approval (the technical approvals below live in scratch only; `APPROVE.sh` of each
workload is the owner's), no paid run, no release. The scratch root used: `<scratchpad>/e2-dry` (`$SCRATCH` below).

## 1. Files

| path | what |
|---|---|
| `tools/dryrun.py` | the one tool: `settings`, `template`, `setup`, `check`, `campaign`, `manifests`, `records` (its docstring is the runbook) |
| `tools/fake_opencode.py` | the scripted client, installed by `setup` as `$SCRATCH/client/opencode` (never under the real client's install directories); copies a reference slice per developer session, answers `{"findings": []}` as reviewer |
| `reference/w1/S1..S4/`, `reference/w2/S1..S3/` | the reference implementation **per story** (what the fake writes for `developer <story>`; `developer direct` writes every slice). W1: `../w1-a/dry-check/reference/` split by story plus the four test files §6.1 names. W2: **written by this lane** — the W2 lane has no reference (its dry check measures the baseline only), see §6 |
| `reference/w2/wrong-S3/` | the deliberate defect of the "wrong" mode (`AISEF_DRYRUN_WRONG=S3`): `--format json` forces exit 0, which §3.2 forbids — the arms' A-JSON and the hidden H-JSON refute it, H-JSON-ZERO does not |
| `settings-offline/arm-{direct,aisef,aisef-plus}.json` | `../settings/arm-*.json` with `provider.endpoint` → `http://127.0.0.1:47311/v1`, `provider.api_key_env` → `AISEF_DRYRUN_KEY`, `client_env` → `[AISEF_DRYRUN_KEY, AISEF_DRYRUN_WRONG]`; everything else (route `9router/mycombo`, `served_model`, `listed_owner`, budget, limits, timeouts, `review`) as the real ones. **Never the real endpoint.** |
| `CAMPAIGN-offline.json` | the campaign: 6 runs, `${SCRATCH}` and `${REPO}` placeholders (§2) |
| `records/` | the run's records copied out of `$SCRATCH/out` (§5) and the verbatim outputs of every step |

## 2. CAMPAIGN-offline.json and how the operator substitutes its paths

`tools/dryrun.py template` writes it: `run_id` `<workload>-r1-<arm>`, `workload` `{id, repo, commit, requirements_path,
task_text}`, `arm`, `settings_path`, `bundle_path`, `evaluator_path`, `rep 1`. The paths carry two placeholders, both
replaced by `tools/dryrun.py setup SCRATCH` into `$SCRATCH/CAMPAIGN-offline.json` (the file `run --campaign` is given;
`run` copies it to `OUT/CAMPAIGN.json`):

* `${SCRATCH}` — the setup directory: `${SCRATCH}/base/<workload>` (the baseline repository `init_repo.sh` built),
  `${SCRATCH}/approved/<workload>-{arms,evaluator}.json` (the technically approved copies, scratch only);
* `${REPO}` — the AISEF repository root: `${REPO}/closure-evidence/v2/v2.1/e2/dry-run/settings-offline/<arm>.json`.

`task_text` is `../w1-a/direct-task.txt` and `../w2/baseline/TASK.txt` (W2 has no `direct-task.txt`; its README §5
names `TASK.txt` as arm A's prompt), each without its final newline. `commit` is each arms' bundle's `plan.baseline`
(`e6901e56…`, `ceae06eb…`), which `setup` checks `init_repo.sh` reproduces. A paid campaign replaces the three
`settings_path` by the real settings and the two `${SCRATCH}/approved/*` by the owner's `approved.json` files.

## 3. Hermetic environment (`tools/dryrun.py campaign`)

PATH = `$SCRATCH/client : <python's dir> : <git's dir> : /usr/bin : /bin` (the process's own PATH held
`~/.opencode/bin` and `~/.npm-global/bin`; they are dropped before anything starts, and `opencode` on the new PATH is
asserted to be the fake); `XDG_CONFIG_HOME/DATA/STATE/CACHE` and `TMPDIR` under `$SCRATCH`; the client's configuration
`$SCRATCH/xdg/config/opencode/opencode.json` sends provider `9router` to the loopback endpoint with
`{env:AISEF_DRYRUN_KEY}`; `AISEF_DRYRUN_KEY` holds a fake value; `NINEROUTER_API_KEY` is removed from the environment
(never read, never printed). The loopback provider (`Provider` in `dryrun.py`, the tests' fake over HTTP) lists
`mycombo` owned by `combo` and serves every chat probe as `MiniMax-M3` under one fingerprint, so both arms' preflight
gate (`campaign.preflight_run` for the direct arm, the kernel's inside `aisef run`) attests — nothing is stubbed at the
module boundary. The campaign runs under `nice -n 19`, python `/opt/homebrew/bin/python3 -P -B` (3.14.7).

## 4. What was run, in order (commands and verbatim outputs in `records/`)

1. `settings`, `template`, `setup $SCRATCH` — baselines `e6901e56…` (W1) and `ceae06eb…` (W2) reproduced and clean;
   technical approvals of the four bundles in `$SCRATCH/approved/` by **`human:dry-run-agent`** (the brief's
   `agent:dry-run` is refused by the kernel, §6), every contract; `aisef bundle lint` READY, admitted, for all four;
   the fake client installed (sha256 in `records/SETUP.json`).
2. `check $SCRATCH` (`records/CHECK.json`): each reference slice applied story by story on a clone of the baseline, the
   story's tests run with the kernel's runner flags (`-E -s -B`, the candidate root as cwd), both approved bundles
   evaluated at every stage (`harness.evaluate`). Reference: W1 S4 → arms 13/13, evaluator 12/12 (tests OK, 15);
   W2 S3 → arms 7/7, evaluator 12/12 (tests OK, 10; the brownfield pytest file 26 passed). W2 wrong-S3 → arms 6/7,
   evaluator 11/12.
3. **Seal-only**: `campaign … run --max-runs 0` → `records/seal-only.txt`: 6 manifests sealed and paired, exit 3
   before the first arm. Independently, `manifests $SCRATCH` → `records/manifests-check-pair.txt`: `harness.check`
   PASS on all 6, `harness.pair_problems` PASS on all 4 pairings.
4. **Full run**, two invocations of the same campaign (the driver resumes on `RESULT.json`):
   `--max-runs 3` with no `AISEF_DRYRUN_WRONG` (the three W1 arms, reference mode) → `records/full-run-1-w1.txt`; then
   `AISEF_DRYRUN_WRONG=S3` for the rest (the three W2 arms, wrong mode) → `records/full-run-2-w2.txt`.
5. `replay --out` → `records/replay.txt`; `summary --out` → `records/summary.txt`; `records $SCRATCH` → the copies
   and `records/INDEX.json` (sha256 of every copied file, and the secret grep).

## 5. Results

Timeline (`date`): setup 15:26:26–15:26:28; check 15:26:28–15:28:14 (first run, re-run after fixing the checker's own
unittest flags: OK at 15:30); seal-only 15:30:54–15:30:55 (exit 3); W1 arms 15:31:22–15:33:27 (exit 3 at
`--max-runs 3`); W2 arms 15:33:5x–15:35:37 (exit 0: campaign done); replay 15:36:07–15:36:31 (exit 0, no output: every
candidate replays); summary 15:36:31; resume run 15:36:32 (`done (0 arms this invocation)`); records 15:37.

`records/out/campaign.log` (one line per arm, verbatim in the file):

| run | arm | exit | candidate | evaluation | valid | rollback | wall_s | requests |
|---|---|---|---|---|---|---|---|---|
| w1-a-r1-direct | direct | 0 | 3cd847f7 | **12/12** | true | false | 0.725 | 5 (4 preflight + 1 session) |
| w1-a-r1-aisef | aisef | 0 | 5eb33520 | **12/12** | true | false | 51.762 | 12 (4 + 4 developer + 4 reviewer) |
| w1-a-r1-aisef-plus | aisef+ | 0 | ad89f392 | **12/12** | true | false | 52.974 | 12 |
| w2-r1-direct (wrong S3) | direct | 0 | 11a22ded | **11/12** (escaped: H-JSON's spec) | true | false | 0.294 | 5 |
| w2-r1-aisef (wrong S3) | aisef | 1 | none | None (delivery FAIL) | true | **true** | 28.207 | 11 (4 + S1 2 + S2 2 + S3 developer ×3) |
| w2-r1-aisef-plus (wrong S3) | aisef+ | 1 | none | None (delivery FAIL) | true | **true** | 28.068 | 11 |

`summary` (`records/summary.txt`, one row per workload × arm): W1 `satisfied_mean 1.0` for all three arms,
`escaped_defects 0`, `false_rollbacks 0`, `requests 5/12/12`, `cost null`, `valid true`, `failed 0`,
`refused_identity 0`. W2: direct `satisfied_mean 0.9167`, `escaped_defects 1`; aisef and aisef+ `evaluated 0`,
`satisfied_mean null`, `failed 1`, `false_rollbacks 0`, `requests 11`; every row `cost null` (no price table: unknown,
never 0) and `valid true` (`evaluator_leaks []` in every RESULT.json).

The W2 aisef arms' RESULT.json carry the plan's false-rejection measure: `aisef_run.story_outcomes.S3 = [RETRY, RETRY,
ROLLBACK]` (S1, S2 COMMIT; `delivery_blocked_by: 1 of the plan's stories did not commit: ['S3']`), and
`false_rollbacks` names the three candidates the journal's `proof/verified` rows hold for S3, each `present: true` in
the arm's repository and each put to the hidden evaluator: 11/12, `passes: false` — so `false_rollback: false` (the
kernel rejected a genuinely defective story; the arms' A-JSON caught what the hidden H-JSON would have counted as
escaped — which is exactly what the direct arm shows). Every arm's `identity` is ATTESTED (the direct arm's
PREFLIGHT.json and the kernel's `preflight.verdict`), `configured_endpoint` the loopback.

Hygiene, from the records: no arm's `ws/.git` or kernel `run/repo/.git` names the baseline's source path (`grep -rlF`
over the W1 arms: 0 files); `records/INDEX.json` `secret_grep`: the fake key's value 0, `[REDACTED]` 0 (nothing was
redacted: no secret was used), `NINEROUTER` only as the variable's name in this tool's own "removed from the
environment" line of each `campaign` output (6), nowhere else (0). OUT is 3.2 MB; `records/` 324 KB (the session
streams are two lines each and are included).

## 6. Problems met, and where they are

| # | problem | where | what this lane did |
|---|---|---|---|
| 1 | The brief's approver `agent:dry-run` is refused: `aisef2/product/approval.py` (`ContractApproval`) accepts only `human:<name>`, and `bundle_cli.approve` passes the approver through | the kernel's rule vs the brief (not the driver, workloads or bundles) | technical approvals by `human:dry-run-agent`, scratch only; the owner's `APPROVE.sh` stays the real one |
| 2 | **W2 has no reference implementation**: `../w2/tools/dry_check.py` measures the baseline only, so nothing existed for a fake client to deliver | workload W2 (a dry-run gap, not a bundle defect) | wrote `reference/w2/` (§1: the delta in three story slices + three unittest files); `check`: arms 7/7, hidden 12/12, the brownfield pytest file 26 passed |
| 3 | **W1-a's reference has no tests**, while the arms' bundle's stories name `tests/test_digest.py` … `tests/test_cli.py` and the kernel's quality gate runs them (NON_VACUOUS and RELEVANT required) — the lane's reference alone cannot pass an `aisef run` | workload W1-a (reference incomplete for a kernel run) | wrote the four test files per story (`reference/w1/S*/tests/`); the kernel accepted every story (4 COMMIT in both aisef arms) |
| 4 | Arm A's prompt is `direct-task.txt` in W1-a but `baseline/TASK.txt` in W2 (inside the baseline tree, so it is also a file every arm sees) | workloads (naming differs between the two lanes) | the template reads each; no change to either lane |
| 5 | `run --max-runs 0` (the seal-only step) exits **3** (`--max-runs 0 reached`), the same code as a STOP file; an operator script must not read it as a failure | driver (exit-code semantics) | recorded; `manifests` gives an exit 0/1 verdict on the sealed manifests independently |
| 6 | `campaign.py run`'s stdout is block-buffered when redirected to a file: nothing appears until the process exits; `OUT/campaign.log` is the live view | driver (operability) | recorded; the operator tails `campaign.log` (or runs python with `-u`) |
| 7 | An `aisef` arm without `review` still runs one reviewer session per story (2.0.0's advisory rule): both aisef arms cost 4 + 2/story requests with no retry; each developer retry adds a session (W2 S3: 3 developer sessions under `limits.DEVELOPER 2`) — the plan's budget arithmetic should count this against the 58-request cap | plan/settings expectation (not a defect) | recorded in the request counts above |
| 8 | The driver sets the arms' PATH but neither sets nor checks `XDG_DATA_HOME/STATE/CACHE` or `TMPDIR`: with the real client these are the operator's to confine (as the offline test and this tool do), or the client writes under `~/.local/share/opencode` | driver (an operator obligation it does not enforce) | `campaign` sets them under `$SCRATCH` |
| 9 | `tools/leaks_w2.py` (W2's second leak scan, for backslash-holding stimuli `harness.leaks` misses inside a session's JSON) is not run by the driver | driver (W2 README §3's note stands) | not wired here; `harness.leaks` reported no leak in any arm |
| 10 | The reference check first ran the story tests under `python -I`, which drops the cwd from `sys.path` (errors on `import treesum`); the kernel's runner uses `-E -s -B` with the candidate root as cwd | this lane's checker only (fixed before the run) | fixed; recorded for anyone re-running tests by hand |

**No problem found in the bundles**: both baselines reproduce to the sha the bundles name; the approved copies lint READY
and admitted; every manifest's `baseline_problems` passed; the arms' bundles proved every reference story and refuted
the wrong one; the hidden evaluators scored the reference 12/12 and the wrong candidate 11/12 on exactly the planted
contract.

## 7. Not verified

* Any session of the real client, any provider request, `mycombo`'s identity, Windows or Linux: not this lane's.
* The owner's `APPROVE.sh` runs: not run; the lane directories `../w1-a/{arms,evaluator}` and `../w2/{arms,hidden}` still
  hold only their authoring/bundle/lint files (checked with `ls` before the commit).
* `tools/leaks_w2.py` (the W2 lane's second leak scan) was not wired into the driver: the driver's `harness.leaks`
  ran on every arm's sessions (`evaluator_leaks: []` everywhere); the W2 lane's note that `harness.leaks` misses a
  backslash-holding stimulus nested in a session's JSON stands.
