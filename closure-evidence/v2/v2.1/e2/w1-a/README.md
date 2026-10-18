# W1-a — a greenfield workload for E2: `treesum`

Lane W1-a of the E2 preparation (owner decision `../../round-5/OWNER-DECISION-2026-10-18-E2.md`; plan
`docs/v2.1/EXPERIMENT-PLAN.md`, workload W1 "greenfield, never used in AISEF's development"). One of two independent
designs; a judge picks. Written 2026-10-18 13:00–13:15 +07 on branch `lane/e2-w1-a` (3555699); the judge's verdict
applied 2026-10-18 13:53–14:15 +07 on `lane/e2-w1-a-2` (W1-FIX: six defects, four grafts from lane W1-b, re-sealed,
dry check re-run — §5); HC-08's fixture corrected 2026-10-18 14:37–14:50 +07 on `lane/e2-w1-a-3` (W1-3: two paths per
kind, the seven alternative orders enumerated and measured — §4, §5 item 8; the evaluator re-sealed, the arms' bundle
untouched). Offline throughout: no provider, no client, no network request, no `opencode`, no `aisef run`.

**What this is:** a public task (`baseline/docs/requirements.md`), a reproducible baseline repository
(`init_repo.sh`), the one-line prompt of arm A (`direct-task.txt`), the arms' bundle for B/C (`arms/`, 13 contracts),
the hidden evaluator (`evaluator/`, 12 contracts, **not approved** — `APPROVE.sh` holds the owner's commands for both
bundles) and an offline dry check with its record (`dry-check/`). **What this is not:** no settings, no experiment
manifests, no run, no owner approval, no acceptance record.

## 1. The workload

`treesum`: a stdlib-only Python package and CLI that records the SHA-256 of every file under a directory
(`build`) and reports what changed (`verify`), with a one-line-per-file text format and exit codes 0 / 1 / 2.
Chosen because (a) nothing like it was used in AISEF's development (not calc, LedgerLock, teamflow, todo-*; `grep -rli
treesum` over the repository found nothing before this lane); (b) every requirement is machine-checkable by one of the
four probe classes — a returned value, a raised type, an exit code with exact stdout, a file's bytes after two
invocations, a scenario of subprocesses with a file edit between them; (c) a reference implementation is ~90 lines
(`dry-check/reference/`), so 30 minutes of model time is realistic; (d) the public text states rules (sorted
output, exit 2 on misuse, replace-not-append, self-exclusion of the snapshot file) whose *instances* can be tested
without appearing in the text — the classic places a hurried implementation goes wrong (`os.walk` over a file yields
nothing instead of raising; directory-walk order instead of string order; append mode; printing as well as writing;
an uncaught `FileNotFoundError` giving exit 1 instead of 2; a snapshot file inside the directory that lists itself).

Four stories (the arms' bundle; the public text names the same four test files in §6.1, so every arm reads the
same instruction). Every story also names `tests/test_smoke.py` (§6.1: "given and must keep passing"): the kernel runs
a story's named tests on its own clean interpreter, which is where 6.1 is enforced (§6, limits).

| story | public clauses | what the developer builds | tests named |
|---|---|---|---|
| S1 | §1 (1.1, 1.2) | `treesum.digest.file_sha256(path)` | `tests/test_digest.py` |
| S2 | §2 (2.1, 2.3) | `treesum.snapshot.build(root)` — recursive, `/`-joined relative keys, `NotADirectoryError` | `tests/test_build.py` |
| S3 | §3, §4 (3.1, 3.2, 3.3, 4.1) | `dumps` / `loads` (the `<sha256>  <path>` text, sorted; the full 3.2 rule) and `compare` (`added`/`removed`/`changed`) | `tests/test_format.py` |
| S4 | §5 (5.2, 5.3, 5.4, 5.5) | `python -m treesum build DIR [-o FILE]` and `verify DIR FILE`, exit 0/1/2, self-exclusion of FILE inside DIR | `tests/test_cli.py` |

## 2. Files, and the approval commands

| path | what |
|---|---|
| `baseline/` | the baseline repository's content: `README.md`, `.gitignore` (`__pycache__/`, so a `git add -A` after a client session commits no bytecode — canary finding C-1), `docs/requirements.md` (**the public task text, identical for every arm**), `treesum/__init__.py` (empty), `tests/__init__.py` (empty; `unittest discover -s tests -t .` needs it), `tests/test_smoke.py` (the one test the task names) |
| `init_repo.sh DEST` | a clean git repository with one commit of `baseline/`, **reproducible** (fixed identity and dates, modes 0644, no user/system git config): commit `e6901e56033d6a30d51e36404d82e4c8d758f99e`, tree `0f759f57e89b59283eac5670d1241274e97b4181`; `harness.source_identity`: archive sha256 `c557e08b3c6307a5af8092002bc4231ad8ac7c2102eeaa1638c382eec0142c32` (20480 bytes), files sha256 `c01f60eeb379acc1ae83fa6db55d524908ee5df2185122fa188413a9f9169e68`. `docs/requirements.md` sha256 `630740d3ec0c1343444024726f30758ca0dd3406b3b66f83c8e5be00c10cf373` (the manifest's `workload.requirements_sha256`). Unchanged by W1-FIX |
| `direct-task.txt` | the one-line prompt proposed for arm A `direct` (grafted from W1-b: implement `docs/requirements.md`, stdlib only, tests under `tests/`, keep `tests/test_smoke.py`, do not run `git commit` — the harness commits the working tree); the orchestrator fixes it in the manifest |
| `arms/authoring.json`, `arms/bundle.json` | the arms' bundle (B `aisef`, C `aisef+`): authoring source and the sealed, unapproved bundle (`aisef bundle seal --repo <init_repo.sh output>`), **13 contracts**, 13 requirement clauses, plan `PLAN-treesum-arms`, plan hash `bb092751…`, baseline `e6901e56…`; file sha256 `80acc8509b0110b8ac72845d1331b47108d5e0d3b54a250da95307513364c254` |
| `evaluator/authoring.json`, `evaluator/bundle.json` | the hidden evaluator: **12 contracts**, plan `PLAN-treesum-hidden`, plan hash `d1278ede…`, baseline `e6901e56…`, **approvals: none**; file sha256 `d004a92b4671ea3ca0a31dac84e2d836ca1728327de55369aa7d4b8577070465` (W1-3; the W1-FIX seal `3d87c632…`, plan hash `cba80e98…`, is void) |
| `APPROVE.sh human:<name>` | the owner's `aisef bundle approve` commands for **both** bundles (arms first, then the evaluator), one contract per command, chained into new files; lints each (expected READY); never overwrites (below). Not run by the lane on the lane's files |
| `dry-check/dry_check.py`, `dry-check/RESULT.json` | the offline dry check (§5) and what it observed, per contract |
| `dry-check/reference/treesum/` | a reference implementation used by the dry check only, never given to an arm (the arms start from `baseline/`; this directory is not in it) |

**The approval commands** (the owner's; from the AISEF repository root, `PYTHONPATH` set to it, `PY` overriding the
interpreter if wanted):

    PYTHONPATH=. sh closure-evidence/v2/v2.1/e2/w1-a/APPROVE.sh human:<your name>

which runs, for the arms' bundle and then the hidden evaluator, one command per contract —

    python3 -P -B -m aisef bundle approve <dir>/bundle.json       --contract <first id>  --approver human:<name> --out <dir>/approved-1.json
    python3 -P -B -m aisef bundle approve <dir>/approved-1.json   --contract <second id> --approver human:<name> --out <dir>/approved-2.json
    ...                                                                                                         --out <dir>/approved-N.json
    ln <dir>/approved-N.json <dir>/approved.json
    python3 -P -B -m aisef bundle lint <dir>/approved.json          # expected: READY, admission admitted

— the arms' thirteen ids in the order `BC-DIGEST BC-DIGEST-MISSING BC-BUILD BC-BUILD-MISSING BC-DUMPS BC-LOADS
BC-ROUNDTRIP BC-COMPARE BC-CLI-BUILD BC-CLI-BUILD-OUT BC-CLI-VERIFY BC-CLI-USAGE BC-STDLIB`, the evaluator's twelve
`HC-01 … HC-09 HC-12 HC-13 HC-14`. The bundle tools create every output exclusively (`O_EXCL`), `ln` refuses an existing
target, and the script refuses a directory that already holds an `approved*.json`: the approved chains are written
beside the bundles once and never over. The script refuses an approver that is not `human:<name>`. An approval is a
human's statement about a contract: read each one (`authoring.json`, and §4 for the hidden ones) before running it.
The canary's "technical approval" precedent (`../../canary/APPROVAL-TRACE.md`) applies to the arms' bundle if the
owner prefers.

## 3. The arms' bundle (what B and C are accepted against)

Every contract tests an example the public text itself gives, or the public text's own rule on the simplest input;
nothing of the hidden evaluator is in it (§5, leak scan). The developer sees the public facts (clause, clause text,
subject) and never a stimulus or an expectation (`aisef2/app/bundle.py`, FACT_FIELDS). After W1-FIX the facts cover
every clause the hidden evaluator instantiates (1.2, 2.3, 3.2 in full, 5.3, 5.5 added; 3.3 added for §3's own sake).

| contract | class | clause | checks |
|---|---|---|---|
| BC-DIGEST | python_callable `returns` | 1.1 | `file_sha256` of the §1.1 example `hello\n` |
| BC-DIGEST-MISSING | python_callable `raises` | 1.2 | `file_sha256("<ws>/absent.txt")` raises `FileNotFoundError` |
| BC-BUILD | python_callable `returns` | 2.1 | `build` of a flat two-file directory |
| BC-BUILD-MISSING | python_callable `raises` | 2.3 | `build("<ws>/nowhere")` (does not exist) raises `NotADirectoryError` |
| BC-DUMPS | python_callable `returns` | 3.1 | the §3.1 example text, from a dict handed in reverse order |
| BC-LOADS | python_callable `returns` | 3.2 (full clause in the facts) | the §3.1 example text parses back |
| BC-ROUNDTRIP | python_callable `returns` | 3.3 | `loads` of `dumps(s)` for one three-entry `s` with a nested path (`sub/c.txt`) is `s` |
| BC-COMPARE | python_callable `returns` | 4.1 | one added, one changed, nothing removed (the empty list present) |
| BC-CLI-BUILD | cli_invocation `exits_streams` | 5.2 | `build DIR`: the text on stdout, exit 0 |
| BC-CLI-BUILD-OUT | cli_invocation `exits_files` | 5.3 | `build DIR -o FILE` on the two-file directory: FILE holds the §3.1 text, exit 0 |
| BC-CLI-VERIFY | cli_invocation `exits_streams` | 5.4 | `verify DIR FILE` with a matching snapshot: nothing printed, exit 0 |
| BC-CLI-USAGE | cli_invocation `exits` | 5.5 | `python -m treesum` with no arguments (a missing subcommand) exits 2 |
| BC-STDLIB | file_artifact `python_imports` | preamble | PRESERVE (S1, S4): no import outside the stdlib in `treesum/` — holds at the baseline (empty package) |

Roles: INTRODUCE for each new behaviour (S1: 1.1, 1.2; S2: 2.1, 2.3; S3: 3.1, 3.2, 3.3, 4.1; S4: 5.2, 5.3, 5.4, 5.5);
PRESERVE of `BC-DIGEST` in S2, `BC-BUILD` in S3, `BC-DUMPS` and `BC-STDLIB` in S4, each depending on the criterion that
introduced it (static check 5). Windows: 10 s callables, 20 s CLI, 30 s file artifact — the hidden evaluator's are
15 / 25 / 45 / 60 s, which is what keeps a hidden observable that states the same rule (`raises NotADirectoryError`)
a different canonical string from the public one (§5, §6).

## 4. The hidden evaluator — per contract, why a faithful implementation satisfies it

None of the twelve inputs or expectations appears in the public text or the arms' bundle; the *rule* each one
instantiates does (the clause column), and after W1-FIX every such clause is also a fact the developer of B/C sees.
"Fails" names the shortcut the contract was written to catch. Evidence: the reference implementation (a direct
transcription of the clauses) is SATISFIED on all 12 and the bare baseline on exactly 1 (HC-14, the hygiene check,
which holds of an empty package and must keep holding) — `dry-check/RESULT.json`, `by_contract`.

| id | probe class | what it checks | public rule | a faithful implementation satisfies it because… | fails |
|---|---|---|---|---|---|
| HC-01 | python_callable `raises` | `file_sha256("<ws>/missing")` raises `FileNotFoundError` | 1.2 "a path that does not exist raises FileNotFoundError" | opening the path for reading raises it; the clause names the type | catching `OSError` and returning an empty or placeholder digest; `os.path.exists` guard returning `None` |
| HC-02 | python_callable `raises` | `build(<a file>)` raises `NotADirectoryError` | 2.3 "exists and is not a directory raises NotADirectoryError" | the clause names the type; one `isdir` check | `os.walk`/`rglob` over a file yield nothing: `{}` is returned; an `exists` check alone (the public BC-BUILD-MISSING passes it) |
| HC-03 | python_callable `returns` | `loads` of a text with a leading empty line, a whitespace-only line and no final newline | 3.2 "empty lines and whitespace-only lines are ignored; a final line without `\n` is read like any other" | the clause states each of the three | `text.split("\n")` with every piece parsed; `text.strip()` then a format that demands the final `\n` |
| HC-04 | python_callable `raises` | `loads("not-a-digest  one.txt\n")` raises `ValueError` | 3.2 "a line that is not `<64 lowercase hex>`, two spaces, `<path>` raises ValueError" | the digest field is validated, as the clause demands | `line.split("  ")` without validating the digest |
| HC-05 | python_callable `returns` | `compare` with every category non-empty, two entries where order shows, inputs in scrambled key order, one unchanged entry | 4.1 "each a list of paths in ascending order"; "changed: in both whose digests differ" | set differences sorted, as 4.1 says | lists in dict/iteration order; an unchanged entry in `changed`; a missing empty key |
| HC-06 | cli_invocation `exits_streams` | `build DIR` over `z.txt`, `a/m.txt`, `a/b/c.txt` prints `a/b/c.txt`, `a/m.txt`, `z.txt` in that order, exit 0 | 2.1 (recursive, `/`), 3.1 (ascending path, plain string order), 5.2 | `dumps` sorts the full relative path as a string | walk order (`z.txt` before the subdirectory; or `a/m.txt` before `a/b/c.txt` by directory level); `os.sep` on Windows |
| HC-07 | cli_invocation `exits_files` (+ `pre`) | `build DIR -o FILE` run twice (pre-step, then main): FILE holds exactly one snapshot, exit 0 | 5.3 "creating it, or replacing its previous content" | the file is opened for writing (truncating) each time | append mode (FILE holds two snapshots). `exits_files` sees FILE and the exit code only — standard output is HC-13's |
| HC-08 | cli_invocation `exits_streams` | `verify` where `a.txt` and `e.txt` changed, `b.txt` and `f.txt` were added and `c.txt` and `g.txt` removed prints `changed a.txt`, `added b.txt`, `removed c.txt`, `changed e.txt`, `added f.txt`, `removed g.txt` in that order, exit 1 | 5.4 "one line per difference, in ascending order of path", "exits 1 when there is at least one" | lines are sorted by path across the three kinds | lines grouped by kind: the path order a b c e f g alternates the kinds changed/added/removed/changed/added/removed, so each of the six kind-grouped orders and the whole-line sort prints another order — all seven enumerated and measured, §5 item 8; exit 0 with output; missing word or extra formatting |
| HC-09 | cli_invocation `exits_streams` | `verify DIR <missing FILE>`: exit 2, stdout empty | 5.5 "a FILE that cannot be read … exits 2 with a message on standard error and nothing on standard output" | the clause states the status and the empty stdout | an uncaught `FileNotFoundError` (traceback, exit 1) |
| HC-12 | process_effect `scenario_files` | in one workspace: `build . -o ./snap.sum` exits 0; `verify . ./snap.sum` exits 0; the harness changes `b.txt`; `verify` exits 1; at the end `snap.sum` has **2** lines and `a.txt` is as it was | 5.3 "when FILE lies inside DIR, FILE is not an entry of the snapshot"; 5.4 "… it is ignored, as in 5.3"; 5.4 exit codes | the relative path of FILE under DIR is dropped on both sides, so the second invocation sees no `added snap.sum`; a changed file is a difference | the snapshot lists itself (3 lines); `verify` right after `build` exits 1; the tool rewrites files it reads |
| HC-13 | cli_invocation `exits_streams` | `build DIR -o FILE` (once): exit 0 and stdout **empty** — HC-07's sibling | 5.3 "with nothing on standard output" | the text goes to FILE instead of stdout | printing the text as well as writing the file (HC-07 cannot see this: `exits_files` carries no stream) |
| HC-14 | file_artifact `exists`, polarity MUST_NOT_HOLD, ABSENCE_IS_DECIDABLE | `treesum/__pycache__` is not an entry of the delivered tree — **hygiene**, not a behaviour | none of `docs/requirements.md`: the baseline `.gitignore` (`__pycache__/`); canary finding C-1 (bytecode committed in a delivered main) | the agent commits source; `.gitignore` keeps a `git add -A` from taking the cache | a delivery that commits `__pycache__/` (`git add -f`, a rewritten `.gitignore`) |

Eleven contracts are `MUST_HOLD`, `REQUIRES_SUBJECT`: an absent function or module is INDETERMINATE (not satisfied),
never a pass. HC-14 is `MUST_NOT_HOLD`, `ABSENCE_IS_DECIDABLE`: the absence of the path is the satisfied case, decided.
Every class used is calibrated in this release (`lint`: `criteria_without_calibration: []`). Classes: python_callable
×5, cli_invocation ×5, process_effect ×1, file_artifact ×1.

**Changes from the judged version (W1-FIX).** HC-01 (the empty file's digest, near-free) was swapped for 1.2's
`FileNotFoundError`. HC-08's fixture was changed: the judged one (`a/m.txt` added, `old.txt` removed, `z.txt`
changed) sorted the paths in the same order as a kind grouping (added, removed, changed), so it could not tell the
two apart. The W1-FIX fixture (`a.txt` changed, `m.txt` added, `z.txt` removed) still had one path per kind, so
exactly one of the six kind-grouped orders — changed, added, removed — coincided with the path order and this
README's "any grouping fails" overclaimed; **W1-3** (`lane/e2-w1-a-3`) made it two paths per kind, interleaved
(a changed, b added, c removed, e changed, f added, g removed): no kind grouping can put the two `changed` lines at
positions 1 and 4, and the dry check now measures that over all seven alternatives (§5 item 8) instead of arguing
it. HC-13 was added as HC-07's sibling because `exits_files` cannot carry stdout. HC-11 (`file_artifact
python_imports` over `tests/`) was removed: its subject `path:tests` defeated the kernel's test-artefact rule by prefix
(`_TEST_ARTEFACT` sees `/tests/` and `tests.`, not `path:tests`; W1-b hit the rule with `tests/`), and its `allowed:
["treesum"]` refuted a legitimate `from tests.helpers import …` — the hygiene check HC-14 (W1-b's C-1 graft) takes its
place. HC-10 (`frobnicate` exits 2) was dropped to stay at twelve: argparse gives it for free, the public BC-CLI-USAGE
now states 5.5's rule on the simplest misuse, and HC-09 keeps the 5.5 instance where the real shortcut lives (an
uncaught `FileNotFoundError`). Every hidden window was set to 15 / 25 / 45 / 60 s (§3, §6).

## 5. Dry check (offline; `dry-check/dry_check.py`, record `dry-check/RESULT.json`)

Command, from the AISEF repository root at `eb96b28` plus this lane's changes (W1-3; the W1-FIX runs of 14:08–14:10
+07 at `3555699` are superseded), Python 3.14.7, git 2.53.0, `PATH` stripped of every directory holding an executable
`opencode` (`command -v opencode` → none), `HOME`/`XDG_*`/`TMPDIR` under a scratch directory (the overrides were
honoured: the runner printed the scratch paths, nothing was written under them), `NINEROUTER_API_KEY` unset, under
`nice -n 19` — run twice, 2026-10-18: the first 14:42:04 → 14:42:40 +07 (the evaluator's seal written after the stale
W1-FIX one was removed; its record was superseded), the second 14:42:50 → 14:43:26 +07 (the committed seals compared;
`RESULT.json` is the second run):

    nice -n 19 /opt/homebrew/bin/python3 -P -B closure-evidence/v2/v2.1/e2/w1-a/dry-check/dry_check.py <scratch>

Observed (`RESULT.json`, `"ok": true`, `"problems": []`, both runs):

1. `init_repo.sh` twice → the same commit `e6901e56…`; the working tree is clean; `harness.source_identity` accepts it
   (archive `c557e08b…`, files `c01f60ee…`, tree `0f759f57…` — unchanged from the judged version: the baseline did not
   move).
2. `aisef bundle seal … --repo <that repository>`: arms 13 specs, evaluator 12 specs, both with `approvals_kept: 0`;
   the committed `bundle.json` files equal a fresh seal byte for byte (`committed_bundle_matches_fresh_seal: true`,
   second run). Arms plan hash `bb092751…` (unchanged: the arms' bundle is byte-identical to W1-FIX, sha256
   `80acc850…`), evaluator `d1278ede…` (W1-3).
3. `aisef bundle lint` on both committed bundles: exit 1, `NOT_READY`, `to_approve` 13 and 12, admission "not run: an
   unapproved contract does not compile", `criteria_without_calibration: []`, `criteria_without_contract: []`, no
   uncovered requirement, no stray criterion — **NOT_READY only for the missing approvals**, as expected.
4. Leak scan: `harness.distinctive(evaluator)` = **23** strings (12 stimuli + 12 observables ≥ 12 characters; HC-14's
   `{}` stimulus is below the threshold), `distinctive(arms)` = **26**; matched the way `harness.leaks` reads a session
   (raw and with escaped quotes) against **every file of `baseline/`** (`.gitignore`, `README.md`,
   `docs/requirements.md`, `tests/__init__.py`, `tests/test_smoke.py`, `treesum/__init__.py`), `direct-task.txt`,
   `arms/authoring.json`, and `arms/bundle.json` **raw and canonical** (the document's canonical JSON and each
   stimulus/observable in the compact form `distinctive` uses): **0 hits each** of ten scanned texts. The two bundles'
   distinctive sets are **disjoint**. The evaluator uses all four probe kinds.
5. Technical approvals **in scratch only**, by `human:w1a-dry-check` (not the owner's; not committed; the scratch
   files are named in `RESULT.json`): `lint` → exit 0, `READY`, admission `admitted: true`, `failed: []` (the nine
   static checks, engine `7668fc35…`) for both bundles.
6. Probes (`harness.evaluate`, this interpreter, PROBE_TIMEOUT_S of `release_acceptance`), reported per contract
   (`by_contract`: spec id → contract id by the kernel's own minting): the reference candidate (`dry-check/reference/`
   on the baseline, smoke test exit 0) — evaluator **12/12 SATISFIED**, arms **13/13**; the bare baseline `e6901e56…`
   — evaluator **1/12** (HC-14 SATISFIED; HC-01…HC-09, HC-12, HC-13 INDETERMINATE: absent subject under
   REQUIRES_SUBJECT), arms **1/13** (BC-STDLIB; the other twelve INDETERMINATE). What the arms add is what is measured.
7. `APPROVE.sh`, on a **copy** of `arms/` and `evaluator/` in scratch with the dry-check approver: both chains written
   (13 + 12 files, `approved.json` linked), both lints `READY`; a second invocation refused (`approved-1.json exists`,
   exit 2); the approver `nobody` refused (exit 2). Nothing was written beside the lane's files. Re-run in W1-3 on a
   fresh copy of the re-sealed evaluator (14:46:00 → 14:46:11 +07, same environment as the dry check): the same
   observations — 13 + 12 approvals, both lints `READY` (`admitted: true`), both refusals exit 2, `arms/` and
   `evaluator/` of the lane still hold only `authoring.json` and `bundle.json`.
8. HC-08's refutation power, measured from the fixture itself (`hc08_orders` in `RESULT.json`; W1-3): the kinds
   derived from the workspace and the snapshot text are a changed, b added, c removed, e changed, f added, g removed
   (two of each); the path-ordered interleaving equals the contract's expected stdout; and each of the seven
   alternative orders differs from it:

   | order (each kind's lines in path order) | stdout, as lines | equals expected |
   |---|---|---|
   | **expected = path order** | changed a, added b, removed c, changed e, added f, removed g | — |
   | added removed changed | added b, added f, removed c, removed g, changed a, changed e | false |
   | added changed removed | added b, added f, changed a, changed e, removed c, removed g | false |
   | removed added changed | removed c, removed g, added b, added f, changed a, changed e | false |
   | removed changed added | removed c, removed g, changed a, changed e, added b, added f | false |
   | changed added removed | changed a, changed e, added b, added f, removed c, removed g | false |
   | changed removed added | changed a, changed e, removed c, removed g, added b, added f | false |
   | whole-line sort (`sorted(lines)`) | added b, added f, changed a, changed e, removed c, removed g | false |

   The whole-line sort coincides with the alphabetical kind grouping (added, changed, removed), so seven rows cover
   six distinct outputs. The reference is SATISFIED on HC-08 (item 6), so the expected text is also what a faithful
   implementation prints; the dry check fails if any row were `true` or if a kind had fewer than two paths.

The judged version's first dry run had added `tests/__init__.py` to the baseline (the earlier baseline sha `797940f7…`
is void); W1-FIX changed nothing in `baseline/`.

Not verified here: `settings.load` (not this lane); the 18 manifests and `pair_problems` (the E2 orchestrator's, once
the model/route settings exist); any session of a real client; Windows or Linux (the probes ran on macOS; the CLI
contracts' `<ws>` paths and `/`-joined keys are platform-neutral by the probes' construction, the reference joins with
`/` explicitly); the owner's own `APPROVE.sh` run on the lane's files.

## 6. Known limits, and notes for the run

* **The model.** The owner's decision names `mycombo` on 9router (`https://9router.vnteki.com/v1`): a router alias
  whose backing model varies per request (MiniMax-M3 was seen) and that may answer in OpenAI or Anthropic shape. The
  manifest's `model` must therefore carry `identity_confidence: provider_reported` (or `unverified`) with that reason,
  and the result records keep `served_model` per session; the three arms of a pair cannot be promised the same
  backing model — a known limit of E2 with this route, to be recorded, not hidden. The `listed_owner` under which the
  alias is listed is found by the lane that is allowed provider traffic; nothing here queried the router.
* **The leak scan is string-based.** It matches the compact JSON of each hidden stimulus/observable (and its
  `\"`-escaped form). A reviewer's reproducer (`adapters.py` asks the model reviewer for `{"stimulus": …,
  "observable": …}` in the same grammar) could by coincidence equal one and mark a result `valid: false`
  conservatively; the hidden-only windows (15/25/45/60 s against the arms' 10/20/30 s) and the unusual inputs make such
  a coincidence unlikely, and it changes no verdict — a conservative false `valid`, never a false pass.
* **No hidden check combines two faults.** Each contract instantiates one rule on one input (a missing FILE, a root
  that is a file, an append, a print beside a write); an implementation whose order of checks differs (validate DIR
  before or after reading FILE, for instance) is treated alike. Escaped defects per the plan = hidden contracts not
  SATISFIED on the delivered main, counted one per contract.
* **The reference is one implementation, not the oracle.** It shows the twelve contracts are jointly satisfiable by a
  stdlib-only program of about 90 lines and that eleven of them are indeterminate on the baseline; it does not show
  that every faithful implementation satisfies them — the argument for that is §4, per contract.
* **Two hidden instances share their rule with a public one.** HC-01 (1.2, a missing path) and the pair HC-09/HC-13
  (5.5 exit 2; 5.3 nothing on stdout) have public siblings (BC-DIGEST-MISSING, BC-CLI-USAGE, BC-CLI-BUILD-OUT) that
  state the same clause on another input, by the judge's fairness requirement: a hidden result there measures whether
  the rule generalised past the public example, not a rule the developer was never shown. HC-02 (a root that is a
  file) is deliberately the other half of 2.3 from the public BC-BUILD-MISSING (a root that does not exist): an
  `exists` guard passes the public one and fails the hidden one.
* **6.1 cannot be a contract.** The kernel refuses any subject that names a test artefact (`aisef2/product/contract.py`
  `_TEST_ARTEFACT`: "a contract names the product, never a test"), so neither "tests import nothing outside the stdlib
  and treesum" nor "`tests/test_smoke.py` keeps passing" can be a hidden or public contract — the judged HC-11 only
  seemed to be one because `path:tests` slipped past the pattern. 6.1 is carried by the stories' `tests` lists (every
  story names its own file and `tests/test_smoke.py`; the kernel runs them on its clean probe interpreter, where an
  `import pytest` fails) and by the public text; nothing hidden checks it.
* **PM-5.** `python_callable_v2`, `cli_invocation` and `process_effect` report what the subject's own process answers;
  code written to recognise the probe can misreport. The hidden evaluator mitigates by not being seen, not by sandboxing.
* **One hidden check holds on the baseline** (HC-14, hygiene): a candidate that delivers nothing scores 1/12, never
  0/12 — as W1-b's two preservation checks.
* The python_callable probe's workspace is flat, so every nested-directory behaviour is tested through the CLI
  (HC-06, HC-07, HC-08, HC-13); the process_effect workspace is flat too, which is why HC-12 exercises the
  self-exclusion rule (FILE inside DIR) rather than a nested tree.
* `init_repo.sh` fixes identity and dates so the commit is the sha the bundles name; a repository made any other way
  has another baseline and `aisef run --check` refuses the bundles (by design).
* The public text requires Python 3.11+; the dry check ran the reference on 3.14.7 only.
* Not in the evaluator (left for the owner to add if wanted): a `file_artifact content` contract pinning
  `docs/requirements.md` to `630740d3…` (a delivery that rewrites the task text); the dropped HC-10 (an unknown
  subcommand exits 2), if the owner would rather have thirteen hidden contracts than twelve.

## 7. What the owner decides

1. Pick a design (this one or W1-b).
2. Read the twelve contracts of `evaluator/bundle.json` and the thirteen of `arms/bundle.json`, then run
   `PYTHONPATH=. sh closure-evidence/v2/v2.1/e2/w1-a/APPROVE.sh human:<name>` (§2): writes `arms/approved.json` and
   `evaluator/approved.json`, lints both READY.
3. The E2 orchestrator then freezes the manifests against `init_repo.sh`'s commit and the approved evaluator's sha256.

## 8. How the harness takes it (for the orchestrator)

* Arm A: `init_repo.sh` → `source_identity(repo, "e6901e56…")`; `direct_arm(manifest, out, task=<direct-task.txt>, …)`.
* Arms B/C: the same repository (`--repo`), `--project arms/approved.json` (after `APPROVE.sh`), settings differing
  only in `review`; the plan's `tests` per story are the four files of §1 plus `tests/test_smoke.py`.
* Evaluation: `harness.evaluate(repo, candidate, evaluator/approved.json)` and `harness.leaks(sessions, evaluator)`.
  Keep this directory out of every arm's workspace: the arms get a clone of the baseline repository and nothing else.
