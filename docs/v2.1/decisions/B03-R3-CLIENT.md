# B-03 round 3, WP client: a session's event stream is read by records that end at a line feed

Branch `v21r3/client`, from the integration head `643a6e0`. Product files: `aisef2/app/client.py` (`events`, new;
`read_session`), `aisef2/app/usage.py` (`session_tokens`), `aisef2/app/lineage.py` (`reconcile`, one expression),
`aisef2/app/confine.py` (`_lines`, new; `_sections`, `_mounts`, `_host_mounts`). Tests:
`tests/v2/test_v21_r3_client_stream.py` (17), `tests/v2/test_v21_r3_client_readers.py` (10). No existing test was
changed. Evidence: `$R3/out/client/` (scripts, outputs and `kc-*.json`; each is named where it is used).

## 1. What was asked

Not an owner decision: a follow-up the lead opened from WP range-fu's finding. In its words, `read_session`'s
`str.splitlines()` also splits at U+2028, U+2029, U+0085, `\x0b`, `\x0c`, `\x1c`-`\x1e`; an event that holds one is cut,
both halves fail `json.loads`, `except ValueError: continue` drops it silently. The task: reproduce through the real
parser, split at LF only, decide what a line that does not parse should do from who reads the result, look for the same
pattern in every reader under `aisef2/app/` (fix those where a cut changes a decision or loses evidence, list the rest
with a verdict; modules outside `aisef2/app/` are findings only), test through `read_session` and through the consumer
that matters, run `kill_check` over every changed function.

## 2. Reproduction (before: `643a6e0`; after: this branch)

`out/client/repro-script.py.txt` (the finding's script, unchanged) and `repro-chain.py.txt` (a scripted client process
whose stream is written raw, through `client.session`, the budget, the usage account and `Reviewer._model`):

| | text event | `read_session` text | budget turns / input | usage steps | model reviewer |
|---|---|---|---|---|---|
| before, separator U+2028 / U+2029 / U+0085 | holds one | `''` (lost) | 1 / 7 | 1 | `found=[]`, `parsed=False` |
| before, a space instead | none | 104 chars | 1 / 7 | 1 | `found=['F1']`, `parsed=True` |
| after, each separator | holds one | 104 chars | 1 / 7 | 1 | `found=['F1']`, `parsed=True` |

The step event was its own line, so the budget and the usage account were unchanged by a cut text event: the loss is the
model's text. What a cut `step_finish` costs (a field of the step that holds a separator) is in the tests, not here:
section 6, rows 3-4, 12.

Consequences of the lost text event in the product (each read in the code, then shown by a test): the reviewer's
`s["text"]` is `""` and `s["error"]` is `None`, so `_model` finds no `{...}`, returns no findings with `parsed=False`,
and the review COMPLETES with nothing found; an `error` event that held one is `None` too, so
`if s["error"] and not s["text"]: raise ProviderOutage` does not fire and a provider outage is "no findings" (a
fix-loop story goes on); a finished step that held one is a turn and tokens nobody counted (not even
`steps_without_tokens`: a cut step is not seen at all), against the ceilings that are "re-derived from the evidence".

## 3. What was measured about the premises

| # | Fact | How |
|---|---|---|
| P1 | A JavaScript `JSON.stringify` writes U+2028, U+2029 and U+0085 raw (`e2 80 a8`, `e2 80 a9`, `c2 85`) and escapes U+000B, U+001F and a lone surrogate. | Node v26.0.0, `od -c` of the output (measured by this WP). |
| P2 | `json.loads` accepts those three raw inside a string and rejects raw U+0000-U+001F (strict), so `\x0b`, `\x0c`, `\x1c`-`\x1e` never occur raw in a valid record: of what `splitlines()` splits at, three characters matter for JSON, and a carriage return is whitespace between tokens. | Python 3.14; tests rows 1, 6, 7. |
| P3 | The client writes its stream straight to the log file (the child's stdout is the file); `redact` works on bytes; nothing re-encodes. A raw separator reaches the reader as written. | `client.session`, `client.redact`. |
| P4 | 67 session streams recorded by earlier runs of the real client (cycle-2 P10 attempts 1-4 and the 2.0.0 release smoke: `closure-evidence/v2/**/sessions/*.jsonl`) hold no raw U+2028/U+2029/U+0085, and `read_session` and `session_tokens` give the same account of every one before and after this change (diff of the two outputs: identical). | `out/client/compare-streams.py.txt`, `compare-usage.py.txt`; `streams-*.jsonl`, `usage-*.jsonl`. |
| P5 | The real OpenCode client was not run (not allowed). That it writes these characters raw is therefore **not established**; that a JavaScript encoder does is P1, and that the stream is read as written is P3. | - |
| P6 | `git worktree list --porcelain` prints a worktree path with U+2028 raw (git 2.53.0 here, 2.47.3 in the guest). | `out/client/gitprobe`, guest test. |
| P7 | The Linux kernel prints U+2028 raw in `/proc/self/mountinfo` (it escapes only space, tab, newline, backslash); `str.split()` with no argument also splits a mountinfo field at it. | Real guest run, section 8. |

## 4. The readers of `aisef2/app/` that split text, one by one

`grep -n "splitlines()\|\.split()\|\.split(\"\\n\")\|readlines\|isspace\|\\s" aisef2/app/*.py` and every `read_text`
that feeds a JSON-lines or line-ended reader. Verdict key: FIXED (exposed, a cut changed what was decided or lost
evidence; test in section 6), PINNED (not exposed because of what its writer does; a test fails first if that changes),
NOT EXPOSED (reason).

| File:line (head) | What is read | Verdict |
|---|---|---|
| `client.py` `events` (was `read_session` l.39) | the session stream: text, error, steps | FIXED |
| `usage.py` `session_tokens` (was l.50) | the same stream, for the usage account | FIXED (same defect; a second copy of the loop: both now call `client.events`) |
| `lineage.py:237` `reconcile` (was l.236) | `git worktree list --porcelain` blocks: a kernel worktree `wt-<story>` of an open story | FIXED: a path with a separator was cut, the worktree's name was the piece's, the unjournaled candidate it holds was not reported (a continuation must name it) |
| `confine.py` `_sections` (was l.206) | the probe's output inside the sandbox (mountinfo, sockets, HOME listing) | FIXED: a mount point or name with a separator was two rows, neither judged |
| `confine.py` `_mounts` (`left.split()`, found by the first test) | the fields of a mountinfo row | FIXED: `str.split()` ended the mount-point field at the separator: `at` was the prefix, the suffix became the options |
| `confine.py` `_host_mounts` (was l.255) | the controller's own `/proc/self/mountinfo` | FIXED: a host mount point with a separator made the table "not read whole" (`None`): no pseudo mount of any session could be shown to be the sandbox's, every run with confinement was refused |
| `lineage.py:219` | `git rev-list --parents`: hex object names | NOT EXPOSED (no character but hex and space) |
| `preflight.py:78` `accounting` | the preflight ledger, `json.loads` per `splitlines()` line, raises on a bad line | PINNED: `_append` writes `json.dumps(row)`, ASCII; a failure text with all three separators is written escaped and read back (`PreflightLedger`). A reader fed a cut line would raise (loudly: "ledger does not read"), never skip |
| `feedback.py:178` | its own `"\n".join` text | NOT EXPOSED (LF) |
| `feedback.py:118-119` | `" ".join(text.split())`: whitespace folded on purpose, secrets matched in the same form | NOT EXPOSED (intended) |
| `adapters.py:192` | `git diff -z`: NUL-ended | NOT EXPOSED |
| `review_ocr.py:50` | one JSON document; the reproducer fence needs a line feed | NOT EXPOSED |
| `run.py:537`, `verify.py:145` | `data.count(b"\n")` on bytes | NOT EXPOSED |
| `bundle_cli.py:159` | `isspace()` to decide quoting | NOT EXPOSED (a separator is quoted: the safe side) |

Outside `aisef2/app/` (findings only; nothing changed there):

| File:line | What is read | Verdict |
|---|---|---|
| `aisef2/orchestrate/workspace.py:195` | `git diff --name-only --diff-filter=U` of a conflicted merge, `splitlines()` | git C-quotes a non-ASCII path by default (measured: `"f\342\200\250g.txt"`); raw only when the repository sets `core.quotepath=false` (an `INERT_KEY`). Then a name is reported in two pieces; `if conflicts:` is unaffected. Low: names in a message |
| `aisef2/quality/relevance.py:101`, `vacuity.py:103` | the candidate's patch | REAL and silent for developer-controlled content (WP range-fu measured `[2, 5]` for `[2, 4]`, `opaque True`): for the quality module's owner |
| `aisef2/probe/file_artifact.py:250` | `grep_facts`: per `splitlines()` line of an observed file | a "line" there is a probe-contract question (a pattern that spans a separator counts differently from `grep`); developer-controlled file content: for the probe's owner |
| `aisef2/probe/cli_invocation.py:415` | `bytes.splitlines()`: LF/CR only | NOT EXPOSED to U+2028 |
| `aisef2/quality/test_execution.py:206` | the last line of stderr, in a message | text only |
| `aisef2/journal/format3.py:315`, `format2.py:311`, `compat.py:55` | `text.split("\n")` | NOT EXPOSED |
| `validation/qualification/release_smoke.py:284`, `validation/v21/context_gap.py:87,119` | session streams, evidence tooling | same pattern; not product; the 67 recorded streams hold none (P4) |

## 5. The decision

**D1. One reader of a session stream: `client.events(log)`.** It decodes the bytes (`utf-8`, `replace`) and splits at
`"\n"` only; a line that starts with `{` and parses is an event; anything else is skipped. `read_session` and
`usage.session_tokens` both read through it, so the budget's spend and the usage account the run reports are derived from
one reading of a stream and cannot disagree about which events it holds (there were two copies of the loop: fixing one
would have left the other cutting). Bytes, not `read_text`: text mode turns a lone carriage return into a line end, and a
carriage return is JSON whitespace; the test (row 6) fails under `read_text(...).split("\n")`.

**D2. What a line that does not parse does: skipped, as before; nothing is added to the record.** Who reads the result:
the budget (turns, tokens: ceilings), the usage account (the run's `usage`, which `verify` re-derives and compares
with the record), the model reviewer (text, error), the turn cap. The legitimate unparseable line is the torn last line
of a stream that was stopped mid-write (every stop the run issues makes one). A skipped non-last line is surfaced
nowhere today: the session record and `Budget.spend` have no field for it, and `usage()` cannot gain one without
making every recorded run's `usage` differ from its re-derivation (`verify.py:196` compares them whole). The task says
not to widen the contract beyond the defect, so it is not widened; whether it should be is a question for the owner
(section 9, Q1). What the fix changes is only the *cause*: a record that holds U+2028/U+2029/U+0085 is no longer a
line that does not parse.

**D3. The same cut elsewhere in `aisef2/app/`** is fixed where it changed a decision (section 4): a line is ended at
LF; a mountinfo field at a space (`re.findall(r"[^ ]+", ...)`, the grammar the kernel prints). `confine._lines` drops the
empty element after a final LF (what `splitlines()` did), so a truncated probe output and a table with a blank line
(`_host_mounts` still refuses it) are read as before.

Alternatives rejected, with the evidence:

* Stitching the halves of a cut line back (rejoin pieces that do not parse): a heuristic with no rule for which pieces
  go together; the cause (the split) is the thing to remove.
* `read_text(...).split("\n")`: leaves text mode's `"\r"` -> `"\n"`; test row 6 (a carriage return between two tokens)
  fails.
* A streaming `raw_decode` over the whole text: accepts what is not JSON-lines and, after a torn middle record, swallows
  the records after it. A wider contract than the defect.
* Fixing the two loops separately: they would drift again, and the budget and the usage account are meant to be one
  reading of one stream.
* `git worktree list --porcelain -z` in `reconcile`: needs git >= 2.36 and the helper `git()` that decodes in text mode
  is outside `aisef2/app/`. The LF-only reading is the minimum that removes the cut; a path that holds LF itself still
  needs `-z` (section 9).

## 6. Requirement -> test

`T` = `tests/v2/test_v21_r3_client_stream.py` (stream), `R` = `tests/v2/test_v21_r3_client_readers.py` (readers).

| # | Requirement | Test |
|---|---|---|
| 1 | an event that holds U+2028 / U+2029 / U+0085 is one event, read whole, with the events around it | T `ReadingAStream.test_an_event_that_holds_a_separator_is_read_whole` |
| 2 | the account of a stream with a separator in a text event equals that of the same stream without it | T `..._the_account_of_a_stream_with_a_separator_is_the_account_of_the_same_stream_without_it` |
| 3 | a finished step whose own field holds a separator is a turn with its tokens (read_session and session_tokens) | T `..._a_finished_step_that_holds_a_separator_is_counted_not_lost` |
| 4 | a step with no token report is still counted blind next to it | T `..._a_step_without_a_token_report_is_still_counted_blind_...` |
| 5 | an error event that holds one is the session's error | T `..._an_error_event_that_holds_a_separator_is_the_sessions_error` |
| 6 | a record ends at LF; CRLF records are read; a lone CR between tokens is whitespace | T `..._a_record_ends_at_a_line_feed_and_a_carriage_return_is_whitespace` |
| 7 | a line that is no event (torn last line cut after a separator, client log line, foreign bytes, `[1,2]`, a raw control character in a string) costs only itself; nothing raises | T `..._a_line_that_is_no_event_costs_only_itself` |
| 8 | an empty stream has no events | T `..._an_empty_stream_has_no_events` |
| 9 | `Budget.spend` of streams with a separator equals that without (turns, tokens, unaccounted) | T `TheAccounts.test_the_budgets_spend_is_the_same_...` |
| 10 | `usage.usage` equals that without | T `..._the_usage_account_is_the_same_...` |
| 11 | the budget's reading and the usage account's agree on every stream | T `..._the_two_accounts_agree_on_every_stream` |
| 12 | the turn cap counts a step that holds a separator (`wait_within`) | T `..._the_turn_cap_counts_a_finished_step_that_holds_a_separator` |
| 13 | the model reviewer's findings block with a separator is its findings, `parsed=True` | T `ModelReviewer.test_a_findings_block_that_holds_a_separator_is_the_reviews_findings` |
| 14 | `Reviewer.review` records that finding, its statement whole | T `..._the_review_records_the_finding_with_its_statement_whole` |
| 15 | an error with a separator is a provider outage, not "no findings" | T `..._an_error_that_holds_a_separator_is_a_provider_outage_not_no_findings` |
| 16-17 | the same through `client.session` with a client that is a real process (POSIX): session record, log bytes, reviewer, budget | T `RealSession.*` |
| 18 | a kernel worktree under a path with a separator is found (3 separators; the ordinary path control) | R `WorktreeListing.*` (premise checked: git prints it raw, else skipped) |
| 19 | the candidate item says whose candidate, where, and what happens to it | R `WorktreeListing.test_the_item_says_...` |
| 20 | the merge item says the story, the proved candidate and what is missing | R `MergeStatement.*` |
| 21 | probe output: a mount point, name and socket with a separator are one entry; `_mounts` reads the row | R `ProbeOutput.test_a_mount_point_a_name_and_a_socket_...` |
| 22 | a writable host mount whose path holds a separator is refused like any other (control: ordinary path) | R `ProbeOutput.test_a_writable_host_mount_...` |
| 23 | the host table with a separator mount is read (not `None`); a table with a non-row or blank line still is `None` | R `HostTable.*` |
| 24 | `_lines` semantics | R `Lines.test_lines` |
| 25 | the preflight ledger holds no raw separator and reads back whole (the writer pin) | R `PreflightLedger.*` |

Wrong implementations, each put in a copy of the tree and run against both files (`out/client/wrong.py.txt`,
`wrong-implementations.txt`): the integration head's `splitlines()` (run on its own tree, so rows 7, 8 and 24 error on
the functions it lacks) fails rows 1-6, 9-18 and 21-24 and passes the controls (rows 19, 20, 25); `read_text(...).split("\n")`
(text mode) fails row 6 only; a split that ends a line at U+2028/U+2029 but not at U+0085 fails the U+0085 case of rows
1, 3, 5, 9, 13 and row 6 (6 failures); `read_session` fixed with `session_tokens` left as it was fails rows 3, 10, 11 (7);
`_mounts` left on `str.split()` fails rows 21, 22, 23 (9: found that way, the first version of the fix missed it);
`_lines` as `splitlines()` fails rows 21-24 (10); the worktree listing left on `splitlines()` fails row 18 (3).

## 7. Mutants (`kill_check`, the runner's own bracket; files named, nothing else used)

Every mutant of every changed or new function, run with the files below plus the target's registered files that
are quick (T0: the unmutated module PASSes with each; all PASS). Each run is from a lean root, a `git archive` of
commit `6c2cfac` without `closure-evidence/{hardening,v2/v2.1,v2/cycle2,v2/P7-FINDING-001}` (no named file reads
them; `test_s2_kills` reads `closure-evidence/v2/release`, which is kept), one root per worker: the runner's worker
identity is the hash of its root, so a first attempt with four workers in one root saw each other's processes as
leftovers and stopped (`NOT_RUN`); those results are discarded and kept under `out/client/invalid-same-root/`.

| function | mutants | KILLED | SURVIVED | killed by (file, count) | record |
|---|---|---|---|---|---|
| `confine.py::_host_mounts` | 16 | 16 | 0 | test_v21_r3_client_readers.py 13, test_v21_r3_conf_policy.py 3 | `kc-_host_mounts.json` |
| `confine.py::_lines` | 4 | 4 | 0 | test_v21_r3_client_readers.py 4 | `kc-_lines.json` |
| `confine.py::_mounts` | 46 | 46 | 0 | test_v21_r3_client_readers.py 35, test_v21_kills3_T07a.py 11 | `kc-_mounts.json` |
| `confine.py::_sections` | 44 | 44 | 0 | test_v21_r3_client_readers.py 30, test_v21_kills3_T07a.py 14 | `kc-_sections.json` |
| `client.py::events` | 6 | 6 | 0 | test_v21_r3_client_stream.py 6 | `kc-events.json` |
| `client.py::read_session` | 77 | 77 | 0 | test_v21_r3_client_stream.py 72, test_app_units.py 3, test_s2_kills.py 2 | `kc-read_session.json` |
| `lineage.py::reconcile` | 148 | 148 | 0 | test_v21_r3_client_readers.py 99, test_v21_kills3_T08a.py 46, test_v21_continue_usage.py 2, test_v21_kills3_A08.py 1 | `kc-reconcile.json` |
| `usage.py::session_tokens` | 37 | 37 | 0 | test_v21_r3_client_stream.py 32, test_v21_kills3_T20a.py 5 | `kc-session_tokens.json` |

Files named per target (what the lead registers; the registered files stay): `events`, `read_session`,
`session_tokens`: `tests/v2/test_v21_r3_client_stream.py` (with `test_s2_kills.py`, `test_app_units.py`,
`test_v21_transport.py` for `read_session`; `test_v21_kills3_T20a.py`, `test_v21_continue_usage.py`,
`test_v21_verify.py`, `test_v21_continue_integrity.py` for `session_tokens`); `_lines`, `_sections`, `_mounts`,
`_host_mounts`, `reconcile`: `tests/v2/test_v21_r3_client_readers.py` (with the conf and T07a / T08a / A08 /
continue files the runs list). `events` and `confine._lines` are new functions: not in the registry yet. The
registered `test_app_run.py` (an end-to-end run) was not needed to kill any `read_session` mutant and was not run in
these records; it passes (section 10).

Dispositions: **no mutant survived on the final head.** One intermediate result is kept: `reconcile` run at `91b19ee`
(before the statement tests) had 142 KILLED and 6 SURVIVED, the six string mutants of the `why` of the candidate item
([138]-[140]: the story, the worktree, "never journaled ... developed again") and of the merge item ([145]-[147]) — the
same six the old record lists as survivors, shifted by one index. They are statements an operator reads in
`aisef bundle continue`'s report, so not harmless: KILLED by `WorktreeListing.test_the_item_says_whose_candidate_...`
and `MergeStatement.test_the_kernels_merge_in_flight_is_stated` (`kc-reconcile-survivors-final.json`: 6 of 6 KILLED
with the five-file set; `kc-reconcile.json`: the full run at `6c2cfac`, 148 of 148). The earlier records are in
`out/client/kc-earlier-91b19ee/`.

## 8. Real, simulated, neither

* **Real, host (macOS, Python 3.14.7, git 2.53.0):** both new files (27 tests) pass; the 73 test modules that import a
  changed module (section 10); `kill_check` of every changed function.
* **Real, in the Linux guest** (`$R3/guest.sh`, profile X1, Python 3.14.8, git 2.47.3, bubblewrap 0.12.0, kernel
  7.0.12-linuxkit; the tree is a `git archive` of commit `283f499`): the two new files and nine existing confinement /
  client / lineage modules, 200 tests, OK, none skipped (`guest-tests-output.txt`); and a **real kernel table** read by
  the real readers (`guest-real-output.txt`, `guest-real-mountinfo.py.txt`): a bind mount at a path with U+2028 in a
  user+mount namespace, the controller's own `/proc/self/mountinfo`: 16 lines by LF, 17 by `splitlines()`;
  `_host_mounts()` is `None` before the change and 16 rows (the mount among them) after; and a real bubblewrap session
  with `--bind` to such a path: its mountinfo is 15 lines, `_sections` gave 16 and `_mounts` 14 rows (the bind mount not
  found) before, 15 and 15 (found) after.
* **Simulation:** every stream in the tests is synthetic, written the way JavaScript writes (P1); the `client` of the
  `RealSession` tests is a script, a real process but not OpenCode; `HostTable` patches `Path.read_text`; `ProbeOutput`
  feeds literal probe text of the shape the probe prints; `ModelReviewer` replaces `client.session` with a function
  that writes the stream and returns what the real `read_session` makes of it.
* **Neither:** that the real OpenCode client writes these characters raw (P5). No run of it, no paid call.

## 9. Not established, residual risks, owner questions

* **Q1 (owner).** Should a line that starts with `{`, does not parse and is **not** the last line of a session's stream
  be accounted for (e.g. a `Budget.spend` `unaccounted` reason, so the run ends like a reached ceiling) instead of being
  skipped? Today it is skipped silently; a torn last line is routine (every stop the run issues makes one) and must stay
  skipped. Rare real causes of a non-last bad line: a client bug; `client.redact` replacing a numeric secret inside a
  token count. Not done here: it changes when runs end, and `usage()`'s record format cannot gain a field without
  breaking `verify` of every recorded run.
* A raw carriage return in a mount point or a worktree path is still cut: mountinfo does not escape it, and the readers
  go through text mode (`Path.read_text`, `subprocess.run(text=True)`, `workspace.git` in `orchestrate/`), which makes it
  a line end. `Path.read_text(newline=)` exists from Python 3.13 only (the floor is 3.11), and the conf tests patch
  `Path.read_text`; not changed, not measured.
* A path that holds a line feed in `git worktree list --porcelain` needs `-z`; not handled.
* The lone-CR-separated stream (a writer that ends records with CR only) was read as separate records through text
  mode and is now one line that does not parse. No writer is known to do it; the JSON-lines convention is LF (CRLF is
  read).
* `usage.py` now imports `client` (one reader of one stream); `client` does not import `usage`; no cycle.
* `events` catches `ValueError` only, as the loops it replaces did: a record nested past the parser's depth is a
  `RecursionError` on 3.11-3.13 and was and is not caught there. Not changed (not the defect).
* Windows and the 3.11-3.13 interpreters were not run here. `RealSession` is POSIX-only (a script run by its shebang);
  `WorktreeListing` skips a subtest whose file system or git does not hold or print the character raw.
* The findings of section 4 outside `aisef2/app/` are open for their owners (quality, probe, orchestrate).
* `tests.v2.test_c2_delivery_experiment.PlanCorrection.test_the_committed_record_is_what_this_tree_derives` fails
  (the committed `PLAN-V2.2-CORRECTION-1.json` is not what this tree derives): it fails identically on `643a6e0`
  (checked in a detached worktree of that commit), so it is not caused by this change; a sealed-record checker the
  lead regenerates.

## 10. Test runs

Host (macOS 25.5, Python 3.14.7, git 2.53.0), through `$SP/m21/kills3/py.sh`, product code as of `6c2cfac`:

| Run | Result |
|---|---|
| `tests.v2.test_v21_r3_client_stream`, `tests.v2.test_v21_r3_client_readers` | 17 + 10 tests OK |
| the 73 modules that import `client`, `usage`, `confine` or `lineage` (`out/client/importers.txt`, `modules-importers.txt`, `modules-result-*.txt`), which include `test_v21_review_chain`, `test_v21_transport`, `test_v21_continue_usage`, `tests.v2.p0.test_destructive_authority` (13), `tests.v2.p4.test_mutation_safety` (10) | 966 tests; 72 modules OK; 4 tests skipped (`test_v21_kills3_T07b` 1; `test_v21_review_chain` 3: the real-binary class needs `AISEF_TEST_OCR_EXE`); 1 module red: `test_c2_delivery_experiment` (1 failure, below) |
| `tests.test_v21_traceability`, `validation/v21/traceability_check.py` | 9 OK; 88 rows OK |
| sealed-record checkers | `tests.v2.p2.test_mutation_targets` 4 OK; `tests.v2.test_v21_mutation_record` 7 OK; `tests.v2.test_c2_k_nowork_001` 1 failure (`kernel.after.kernel_digest is not this tree's aisef2`); `test_c2_delivery_experiment.PlanCorrection.test_the_committed_record_is_what_this_tree_derives` 1 failure (`PLAN-V2.2-CORRECTION-1.json is not what this tree derives`) |
| Linux guest, X1 | 200 tests OK, none skipped (section 8) |

The two sealed-record failures are the checkers the task names as expected-stale after a product change; both are also
red on `643a6e0` (each re-run there in a detached worktree of that commit, same assertion), so this change did not
turn them red. They are the lead's to regenerate; nothing was done about them.
