# W1-a — a greenfield workload for E2: `treesum`

Lane W1-a of the E2 preparation (owner decision `../../round-5/OWNER-DECISION-2026-10-18-E2.md`; plan
`docs/v2.1/EXPERIMENT-PLAN.md`, workload W1 "greenfield, never used in AISEF's development"). One of two independent
designs; a judge picks. Written 2026-10-18 13:00–13:15 +07 on branch `lane/e2-w1-a`, offline: no provider, no client,
no network request, no `opencode`, no `aisef run`.

**What this is:** a public task (`baseline/docs/requirements.md`), a reproducible baseline repository
(`init_repo.sh`), the arms' bundle for B/C (`arms/`), the hidden evaluator (`evaluator/`, 12 contracts, **not
approved** — `evaluator/APPROVE.sh` holds the owner's commands) and an offline dry check with its record
(`dry-check/`). **What this is not:** no settings, no experiment manifests, no run, no owner approval, no acceptance
record.

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
nothing instead of raising; directory-walk order instead of string order; append mode; an uncaught
`FileNotFoundError` giving exit 1 instead of 2; a snapshot file inside the directory that lists itself).

Four stories (the arms' bundle; the public text names the same four test files in §6.1, so every arm reads the
same instruction):

| story | public clauses | what the developer builds | tests named |
|---|---|---|---|
| S1 | §1 | `treesum.digest.file_sha256(path)` | `tests/test_digest.py` |
| S2 | §2 | `treesum.snapshot.build(root)` — recursive, `/`-joined relative keys, `NotADirectoryError` | `tests/test_build.py` |
| S3 | §3, §4 | `dumps` / `loads` (the `<sha256>  <path>` text, sorted) and `compare` (`added`/`removed`/`changed`) | `tests/test_format.py` |
| S4 | §5 | `python -m treesum build DIR [-o FILE]` and `verify DIR FILE`, exit 0/1/2, self-exclusion of FILE inside DIR | `tests/test_cli.py` |

## 2. Files

| path | what |
|---|---|
| `baseline/` | the baseline repository's content: `README.md`, `.gitignore` (`__pycache__/`, so a `git add -A` after a client session commits no bytecode — canary finding C-1), `docs/requirements.md` (**the public task text, identical for every arm**), `treesum/__init__.py` (empty), `tests/__init__.py` (empty; `unittest discover -s tests -t .` needs it), `tests/test_smoke.py` (the one test the task names) |
| `init_repo.sh DEST` | a clean git repository with one commit of `baseline/`, **reproducible** (fixed identity and dates, modes 0644, no user/system git config): commit `e6901e56033d6a30d51e36404d82e4c8d758f99e`, tree `0f759f57e89b59283eac5670d1241274e97b4181`; `harness.source_identity`: archive sha256 `c557e08b3c6307a5af8092002bc4231ad8ac7c2102eeaa1638c382eec0142c32` (20480 bytes), files sha256 `c01f60eeb379acc1ae83fa6db55d524908ee5df2185122fa188413a9f9169e68`. `docs/requirements.md` sha256 `630740d3ec0c1343444024726f30758ca0dd3406b3b66f83c8e5be00c10cf373` (the manifest's `workload.requirements_sha256`) |
| `arms/authoring.json`, `arms/bundle.json` | the arms' bundle (B `aisef`, C `aisef+`): authoring source and the sealed, unapproved bundle (`aisef bundle seal --repo <init_repo.sh output>`), 8 contracts, plan `PLAN-treesum-arms`, plan hash `0a141fde…`, baseline `e6901e56…`; file sha256 `e07cd6b51bb3dc94ed90e841417d0c7b2c04cd0131233a513fb4cef06ad3a00a` |
| `evaluator/authoring.json`, `evaluator/bundle.json` | the hidden evaluator: 12 contracts, plan `PLAN-treesum-hidden`, plan hash `9433f170…`, baseline `e6901e56…`, **approvals: none**; file sha256 `d5818db4c13c18625f129b251a5e864681c68eafe18f2aa9e2e7ce70929e069e` |
| `evaluator/APPROVE.sh` | the twelve `aisef bundle approve` commands (chained, `human:$NAME`) and the final lint — the owner runs it; nothing here ran it |
| `dry-check/dry_check.py`, `dry-check/RESULT.json` | the offline dry check (§5) and what it observed |
| `dry-check/reference/treesum/` | a reference implementation used by the dry check only, never given to an arm (the arms start from `baseline/`; this directory is not in it) |

## 3. The arms' bundle (what B and C are accepted against)

Every contract tests an example the public text itself gives, or the public text's own rule on the simplest input;
nothing of the hidden evaluator is in it (§5, leak scan). The developer sees the public facts (clause, clause text,
subject) and never a stimulus or an expectation (`aisef2/app/bundle.py`, FACT_FIELDS).

| contract | class | checks |
|---|---|---|
| BC-DIGEST | python_callable `returns` | `file_sha256` of the §1.1 example `hello\n` |
| BC-BUILD | python_callable `returns` | `build` of a flat two-file directory |
| BC-DUMPS | python_callable `returns` | the §3.1 example text, from a dict handed in reverse order |
| BC-LOADS | python_callable `returns` | the §3.1 example text parses back |
| BC-COMPARE | python_callable `returns` | one added, one changed, nothing removed (the empty list present) |
| BC-CLI-BUILD | cli_invocation `exits_streams` | `build DIR`: the text on stdout, exit 0 |
| BC-CLI-VERIFY | cli_invocation `exits_streams` | `verify DIR FILE` with a matching snapshot: nothing printed, exit 0 |
| BC-STDLIB | file_artifact `python_imports` | PRESERVE (S1, S4): no import outside the stdlib in `treesum/` — holds at the baseline (empty package) |

Roles: INTRODUCE for each new behaviour; PRESERVE of `BC-DIGEST` in S2, `BC-BUILD` in S3, `BC-DUMPS` and `BC-STDLIB`
in S4, each depending on the criterion that introduced it (static check 5). Windows: 10 s callables, 20 s CLI, 30 s
file artifact.

## 4. The hidden evaluator — per contract, why a faithful implementation satisfies it

None of the twelve inputs or expectations appears in the public text or the arms' bundle; the *rule* each one
instantiates does (the clause column). "Fails" names the shortcut the contract was written to catch. Evidence: the
reference implementation (a direct transcription of the clauses) is SATISFIED on all 12 and the bare baseline on 1
(HC-11, which holds of the smoke test and must keep holding) — `dry-check/RESULT.json`.

| id | probe class | what it checks | public rule | a faithful implementation satisfies it because… | fails |
|---|---|---|---|---|---|
| HC-01 | python_callable `returns` | `file_sha256` of a zero-byte file is `e3b0c442…` | 1.1 "the SHA-256 of the file's bytes" | the SHA-256 of no bytes is that constant; hashing the opened file's bytes gives it | hashing the path or the name; treating an empty read as an error |
| HC-02 | python_callable `raises` | `build(<a file>)` raises `NotADirectoryError` | 2.3 "exists and is not a directory raises NotADirectoryError" | the clause names the type; one `isdir` check | `os.walk`/`rglob` over a file yield nothing: `{}` is returned |
| HC-03 | python_callable `returns` | `loads` of a text with a leading empty line, a whitespace-only line and no final newline | 3.2 "empty lines and whitespace-only lines are ignored; a final line without `\n` is read like any other" | the clause states each of the three | `text.split("\n")` with every piece parsed; `text.strip()` then a format that demands the final `\n` |
| HC-04 | python_callable `raises` | `loads("not-a-digest  one.txt\n")` raises `ValueError` | 3.2 "a line that is not `<64 lowercase hex>`, two spaces, `<path>` raises ValueError" | the digest field is validated, as the clause demands | `line.split("  ")` without validating the digest |
| HC-05 | python_callable `returns` | `compare` with every category non-empty, two entries where order shows, inputs in scrambled key order, one unchanged entry | 4.1 "each a list of paths in ascending order"; "changed: in both whose digests differ" | set differences sorted, as 4.1 says | lists in dict/iteration order; an unchanged entry in `changed`; a missing empty key |
| HC-06 | cli_invocation `exits_streams` | `build DIR` over `z.txt`, `a/m.txt`, `a/b/c.txt` prints `a/b/c.txt`, `a/m.txt`, `z.txt` in that order, exit 0 | 2.1 (recursive, `/`), 3.1 (ascending path, plain string order), 5.2 | `dumps` sorts the full relative path as a string | walk order (`z.txt` before the subdirectory; or `a/m.txt` before `a/b/c.txt` by directory level); `os.sep` on Windows |
| HC-07 | cli_invocation `exits_files` (+ `pre`) | `build DIR -o FILE` run twice (pre-step, then main): FILE holds exactly one snapshot, exit 0 | 5.3 "creating it, or replacing its previous content" | the file is opened for writing (truncating) each time | append mode; writing to stdout as well |
| HC-08 | cli_invocation `exits_streams` | `verify` with one added, one removed and one changed path prints `added a/m.txt`, `removed old.txt`, `changed z.txt` in that order, exit 1 | 5.4 "one line per difference, in ascending order of path", "exits 1 when there is at least one" | lines are sorted by path across the three kinds | lines grouped by kind; exit 0 with output; missing word or extra formatting |
| HC-09 | cli_invocation `exits_streams` | `verify DIR <missing FILE>`: exit 2, stdout empty | 5.5 "a FILE that cannot be read … exits 2 with a message on standard error and nothing on standard output" | the clause states the status and the empty stdout | an uncaught `FileNotFoundError` (traceback, exit 1) |
| HC-10 | cli_invocation `exits` | `python -m treesum frobnicate` exits 2 | 5.5 "an unknown or missing subcommand … exits 2" | argparse does it; a hand parser returns 2 as the clause says | `return 1`, or `print` and exit 0 |
| HC-11 | file_artifact `python_imports` | no import statement in `tests/*.py` names a module outside the stdlib and `treesum` | 6.1 "tests import nothing outside the standard library and treesum" | the tests use `unittest` | `import pytest` |
| HC-12 | process_effect `scenario_files` | in one workspace: `build . -o ./snap.sum` exits 0; `verify . ./snap.sum` exits 0; the harness changes `b.txt`; `verify` exits 1; at the end `snap.sum` has **2** lines and `a.txt` is as it was | 5.3 "when FILE lies inside DIR, FILE is not an entry of the snapshot"; 5.4 "… it is ignored, as in 5.3"; 5.4 exit codes | the relative path of FILE under DIR is dropped on both sides, so the second invocation sees no `added snap.sum`; a changed file is a difference | the snapshot lists itself (3 lines); `verify` right after `build` exits 1; the tool rewrites files it reads |

Each contract is `MUST_HOLD`, `REQUIRES_SUBJECT`: an absent function or module is INDETERMINATE (not satisfied),
never a pass. Every class used is calibrated in this release (`lint`: `criteria_without_calibration: []`).

## 5. Dry check (offline; `dry-check/dry_check.py`, record `dry-check/RESULT.json`)

Command, from the AISEF repository root at `2ac9b80` (this lane's files added), 2026-10-18 13:04:23–13:04:54 +07,
Python 3.14.7, git 2.53.0:

    nice -n 19 /opt/homebrew/bin/python3 -P -B closure-evidence/v2/v2.1/e2/w1-a/dry-check/dry_check.py <scratch>

Observed (`RESULT.json`, `"ok": true`, `"problems": []`):

1. `init_repo.sh` twice → the same commit `e6901e56…`; the working tree is clean; `harness.source_identity` accepts it.
2. `aisef bundle seal … --repo <that repository>`: arms 8 specs, evaluator 12 specs, both with `approvals_kept: 0`;
   the committed `bundle.json` files equal a fresh seal byte for byte.
3. `aisef bundle lint` on both committed bundles: exit 1, `NOT_READY`, `to_approve` 8 and 12, admission "not run: an
   unapproved contract does not compile", `criteria_without_calibration: []`, `criteria_without_contract: []`, no
   uncovered requirement — **NOT_READY only for the missing approvals**, as expected.
4. Leak scan: `harness.distinctive(evaluator)` = 24 strings (12 stimuli + 12 observables, each ≥ 12 characters),
   matched the way `harness.leaks` reads a session (raw and with escaped quotes) against `baseline/docs/requirements.md`,
   `baseline/README.md`, `arms/authoring.json`, `arms/bundle.json`: **0 hits each**. The canonical stimulus/observable
   parts of the two bundles are disjoint sets. The evaluator uses all four probe kinds.
5. Technical approvals **in scratch only**, by `human:w1a-dry-check` (not the owner's; not committed; the scratch
   files are named in `RESULT.json`): `lint` → exit 0, `READY`, admission `admitted: true`, `failed: []` (the nine
   static checks, engine `7668fc35…`) for both bundles.
6. Probes (`harness.evaluate`, this interpreter, PROBE_TIMEOUT_S of `release_acceptance`): the reference candidate
   (`dry-check/reference/` on the baseline, commit `8fdd000a…` in scratch, smoke test exit 0) — evaluator **12/12
   SATISFIED**, arms **8/8**; the bare baseline `e6901e56…` — evaluator **1/12** (HC-11), arms **1/8** (BC-STDLIB), the
   other 11 and 7 INDETERMINATE (absent subject under REQUIRES_SUBJECT). What the arms add is what is measured.

First run of the dry check failed on the smoke test (`unittest discover -s tests -t .` refuses a start directory that
is not importable): `tests/__init__.py` was added to the baseline and both bundles re-sealed. The earlier baseline
sha `797940f7…` is void.

Not verified here: `settings.load` (not this lane); the 18 manifests and `pair_problems` (the E2 orchestrator's, once
the model/route settings exist); any session of a real client; Windows or Linux (the probes ran on macOS; the CLI
contracts' `<ws>` paths and `/`-joined keys are platform-neutral by the probes' construction, the reference joins with
`/` explicitly).

## 6. Limits, and notes for the run

* **The model.** The owner's decision names `mycombo` on 9router (`https://9router.vnteki.com/v1`): a router alias
  whose backing model varies per request (MiniMax-M3 was seen) and that may answer in OpenAI or Anthropic shape. The
  manifest's `model` must therefore carry `identity_confidence: provider_reported` (or `unverified`) with that reason,
  and the result records keep `served_model` per session; the three arms of a pair cannot be promised the same
  backing model — a known limit of E2 with this route, to be recorded, not hidden. The `listed_owner` under which the
  alias is listed is found by the lane that is allowed provider traffic; nothing here queried the router.
* **PM-5.** `python_callable_v2`, `cli_invocation` and `process_effect` report what the subject's own process answers;
  code written to recognise the probe can misreport. The hidden evaluator mitigates by not being seen, not by sandboxing.
* **HC-11's window is 20 s** where BC-STDLIB's is 30 s, and its stimulus adds `suffixes: [".py"]`: both are legitimate
  per-contract choices, and they are also what keeps its canonical parts distinct from the arms' stdlib contract
  (the leak scan is by string). Its subject is `tests/`, the arms' is `treesum/`.
* The python_callable probe's workspace is flat, so every nested-directory behaviour is tested through the CLI
  (HC-06, HC-07, HC-08); the process_effect workspace is flat too, which is why HC-12 exercises the self-exclusion rule
  (FILE inside DIR) rather than a nested tree.
* `init_repo.sh` fixes identity and dates so the commit is the sha the bundles name; a repository made any other way
  has another baseline and `aisef run --check` refuses the bundles (by design).
* The public text requires Python 3.11+; the dry check ran the reference on 3.14.7 only.
* Not in the evaluator (left for the owner to add if wanted): a `file_artifact content` contract pinning
  `docs/requirements.md` to `630740d3…` (a delivery that rewrites the task text), and a `FileNotFoundError` contract
  for `file_sha256` (1.2) — both dropped to stay within 12 and to keep every contract a behaviour.

## 7. What the owner decides

1. Pick a design (this one or W1-b).
2. Read the twelve contracts of `evaluator/bundle.json` and run `NAME=<name> sh evaluator/APPROVE.sh` (writes
   `evaluator/approved.json`, lints it READY). The arms' bundle is approved the same way, per contract
   (`aisef bundle approve arms/bundle.json --contract BC-… --approver human:<name> --out …`); the canary's "technical
   approval" precedent (`../../canary/APPROVAL-TRACE.md`) applies to it if the owner prefers.
3. The E2 orchestrator then freezes the manifests against `init_repo.sh`'s commit and the approved evaluator's sha256.
