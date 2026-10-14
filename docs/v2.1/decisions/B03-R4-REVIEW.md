# B-03 round 4 — what an independent review of the last survivors found, and how the change was scoped

Status: **written before the re-measurement it names**; the numbers of that measurement are in
`closure-evidence/v2/v2.1/campaign-6/` and in `docs/v2.1/REPORT.md` §0 once it is done. Nothing was pushed, tagged or
published; no paid provider was called; Docker was not touched.

Rule of the round (the owner's, 2026-10-12): the aim is the right behaviour and the evidence for it; a mutation record
turning PASS is never the reason to choose a requirement; an audit is not a kill; a result is kept only on a specific
dependency basis; no rule is relaxed to avoid the cost of a measurement.

## 1. What campaign 5 left, and what was done with each

Campaign 5 (528 targets, 13,566 mutants, one snapshot `289885e`) ended 13,361 KILLED, 203 SURVIVED, 2 TIMEOUT,
0 INFRA, 0 NOT_RUN. Seven of those were not covered by any kill or audit (the other 196 survivors were carried audits,
re-verified: §5).

| mutant | what it is | disposition |
|---|---|---|
| `process_range._Posix.abort` ×2 (L187 `is None` → `is not None`, negated) | a live anchor is left running; the P4 test that waits for it never returned: TIMEOUT 900 s each | **KILLED** by `tests/v2/test_v21_r3_range_abort.py` (a stand-in anchor and recording `os.killpg`/`os.kill`: no process, no signal) |
| `confine._judge` [100] (`rc in (None, 127)` → `(127,)`) | the None member | **KILLED** by `tests/v2/test_v21_r3_judge_not_run.py`, which states the contract of the input (below) instead of resting on what `_sections` builds |
| `confine._judge` [135, 136, 138, 139] (the defaults of two `dict.get` of one line) | a default is read only when the key is absent; an absent key makes the first operand True in the original and in each mutant | the two `.get` of one key were **replaced by one unpacking** (`rc, said = tries.get("workspace", (None, ""))`): the defaults are now load-bearing (a wrong-length default raises when the key is absent, which the existing absent-key test sees); the four mutants are gone, not audited |

## 2. The independent review (one agent, given the code and the questions, not my conclusions)

It asked: are the four defaults equivalent for EVERY input; what separates [100]; do the two new kill files test the
requirement. Its findings, each reproduced here:

1. **A real fail-open in the measurement, not a mutant (fixed).** The probe writes `@@aisef-confine rc N` with
   `printf`; the marker is at the start of a line only when the text before it ended with a line feed. A command that
   ends its output without one glues the marker to its last line, `_sections` no longer sees a marker, and the try is
   left an open list. Then: with at most one body line `_probe` raised `ValueError` at `rep["tried"]` (a traceback,
   not a refusal); with exactly two body lines `_judge` unpacked them as an exit status and a text and could judge the
   user-namespace check from them; and a canary try with no status was **no problem at all** (`[0] == 0` was False).
   The audit that carried "a list never reaches `_judge`: an unclosed try means no `m end`" was wrong: `m end` is
   written regardless. Fixed at the producer: `_sections` reports a try that never gave a status as `(None, its text)`,
   and `_judge` names every try with status None ("did not run"); no change for a try that reported.
   Tests: `test_v21_r3_judge_not_run.py` — red on the committed code (11 failures, 3 errors), green on the fix; the
   same through `confine.measure` with its subprocess answered by a canned probe output.
2. **`_Posix.abort` masked the failure that led to it (fixed).** `abort()` let `ProcessLookupError`/`PermissionError`
   out when the anchor ended between `poll()` and `killpg` (macOS answers EPERM for a group of zombies); `_abort`
   then never reached `anchor.wait()` and the pipe close, and the start failure was replaced by that error. Tolerated
   as `signal()` of the same class is; any other `OSError` still propagates. Tests: `test_v21_r3_range_abort.py`
   (red on the committed code: 2 errors).
3. **The four defaults are not equivalent for every Python input** — only for every `tries` the module builds and any
   well-behaved mapping (a `get` that reads its default, or a value whose `[0]` removes the key, separates them). They
   were not kept as "EQUIVALENT" for that reason; §1.
4. **Test quality** (both new kill files rewritten): the first version of the `_judge` test compared whole messages
   (a harmless rewording would have failed it: a false alarm) and its controls only tested the accepting side; the
   first abort test stubbed `os.killpg` only (a variant signalling through `os.kill` would have reached a real pid),
   never adopted the anchor, and held one tautological assertion. All changed.

## 3. Scope of the re-measurement: what it is, and the basis for what is NOT re-measured

Changed code since campaign 5's snapshot: `aisef2/app/confine.py` (`_sections`, `_judge`) and
`aisef2/runtime/process_range.py` (`_Posix.abort`) — the latter is imported by every probe module and by the runner.
The campaign-5 route (a reach recorder that hooks the children that inherit its PYTHONPATH) cannot say a function was
NOT executed by a child that builds its own environment: 1,002 of the 1,090 Python children it saw were unobserved.
It could not give a basis here either, so every target would have been re-measured again (24 h).

The change in behaviour is narrow and describable: each differs from the old code ONLY on a class of inputs
(`_sections`/`_judge`: a try with no exit status or not a `(status, text)` pair; `abort`: `killpg` raising ESRCH/EPERM).
`validation/v21/trace_paths.py` marks exactly those paths in the runner's fresh copy of the tree — every process that
runs that tree's product code writes a line, whatever its environment — and runs every kill file once:
`closure-evidence/v2/v2.1/campaign-6/trace.json`. A kill file with no hit never reached the changed behaviour, so its
outcome on the unmutated tree is the old code's. Controls: each mark is reached by a `-E -S` child with its own env.
Rules applied: a target whose module file changed (all of `confine.py`, all of `process_range.py`), whose kill set
changed (`_judge`, `wrap`, `_Posix.abort`), or one of whose kill files has a hit (or did not PASS under the marks, so
was not measured) is re-measured; the rest stand on: target file identical, kill set identical, kill-test closure
identical, generator identical (the record's own proof), the read-set at the new head (no data they read changed), and
the trace.

What this basis does NOT cover, and says so: a mutant of ANOTHER module that manufactured the very input (a probe
output with a try that has no status) is not covered by a trace of the unmutated tree; none can — the probe output
comes from the bubblewrap process the test supplies, not from product code of another module.

The numbers: `closure-evidence/v2/v2.1/campaign-6/SCOPE.json` (one row per target with its role and why).

## 4. Findings kept as known limits (not changed)

* `abort()` and `signal()` are tolerant of an absent group, but `_abort` does not catch an `OSError` of
  `anchor.wait()`/the pipe close (no way to see it fail).
* The probe's glued marker is now refused fail-closed; the probe script itself was not changed (its text is part of the
  recorded `argv`, and a leading blank line in front of every marker would alter every section's text).

## 5. The carried audits

122 carried audits were re-verified by 18 independent skeptic agents (two copies per batch, a and b, each re-deriving
the claim at the snapshot, applying the mutant, running the tests): `closure-evidence/v2/v2.1/round-3/audit-reverification/`.
Dispositions are in §6.

## 6. The re-verification of the carried audits: dispositions

122 entries, 18 agents (9 batches x two copies, blind to each other). `apply_audits.py` (kept beside the reports) turns the
verdicts into the audit file; the rule it applies: an entry stays only when neither copy refuted it, and its grounds
become the (first) revised copy's, with the earlier ones kept as `grounds_before`.

| outcome | entries | what it means |
|---|---|---|
| CONFIRMED by both | 73 | the claim holds at the snapshot; the cites were refreshed |
| REVISED (one or both copies), class unchanged | 43 | the conclusion holds; a written ground was stale or wrong (a reader added by round 3, a cite, a test that now asserts the value) |
| REFUTED by both, a test already kills it | 4 | `wrap` [42-44] (`test_v21_r3_conf_locale` asserts the probe's environment value for value), `findings` [52] (`T12b`'s second test): registered; not an audit |
| REFUTED by both, a test is owed | 1 | `_canon` [4]: since round 3 the statement bounds `anchor_why` on its JSON encoding, the escape evicts the contract ids: `test_v21_r4_anchor_nonascii.py` |
| the copies disagree | 1 | `verify` [24] ("at the bytes that run"): one refuted, one confirmed, both agree on the facts; the test states what they agree on (`test_v21_r4_uncalibrated_qualifier.py`) |

Optional tests the agents sketched and that nothing owes (the audits stand): an `assertIn` for the closing parenthesis or
the label of a few refusal messages (`pinned` [11], `read_anchor` [5], `write_anchor` [5], `continue_from` [115]), and a
one-line artifact assertion for the finding's `source`. A test of a message's wording is not written to move a number
(round 1's rule); each is the owner's to want.

Side findings of the agents, none a mutant, none fixed here (each is fail-closed or documentation):

| id | finding | measured | class |
|---|---|---|---|
| RV-1 | `reproducer_contract` raises `RecursionError` for a reproducer nested ~3,000 levels (800 is fine): the review stage ends with the story REFUSED, no verdict | `scratchpad` probe, kept as `round-3/r4/recursion_probe.py` | defect (low, fail-closed); same class as PM-3 (`file_artifact`): one bounded-depth fix in a probe window |
| RV-2 | the NOT_REPRODUCED sentence ("observes the stated behaviour: the finding does not reproduce") is false for INDETERMINATE, and since round 3 the statement prints `observed=INDETERMINATE` beside it | read | wording; the ruling is the owner's (open since V2.1-backlog) |
| RV-3 | the refusals of `check_repository` and `--parent` lose a label token under a mutant; whether `run.py:149` should name `shown` | read | owner question about the product's wording |
| RV-4 | `test_v21_kills3_T25a`'s docstring lists preflight `http_transport` [13, 14] as pinned (numbering of an earlier enumeration): they survive it and every preflight test; only a `get_type_hints`/return-annotation test separates them | measured by two agents | test docstring is stale; the audits stand |
| RV-5 | `test_c2_k_nowork_001` is red on the unmutated snapshot: the K-NOWORK record's `kernel.after.kernel_digest` is not this tree's `aisef2/` (stale after round 3) | measured | the record is regenerated on the final tree (§ the order of derived records) |

## 7. The seven survivors campaign 6 left without an audit (and the second round of skeptics)

Campaign 6 ended with 26 survivors; 19 carried an audit, 7 did not. All seven were new: they live in the lines round 4
changed. The author drafted audits; two blind skeptic copies tried to break them (`round-3/audit-reverification-r4/`);
the strengthened test and a new kill file killed the others.

| mutant | what it is | disposition |
|---|---|---|
| `_sections` [32], [33], [48] | the tuple `(None, text)` of a try that never reported: element dropped, the join's separator emptied | KILLED: the test written for them existed and was registered for `_judge` only (the same shape as the six refuted audits); registered for `_sections`, and its assertions made exact (the whole tuple) |
| `_judge` [169] | `', '` of the list of names: the checks ran together | KILLED: the names asserted as tokens |
| `_probe` [109] | the canary file written without its trailing line feed | draft audit "refused either way"; **REFUTED by both copies**: without the line feed the breach is recorded as a try that never reported — "did not run" is the first line of the refusal of a check that read the file, in RUN.json and `--check`, and the replay of the record (`_judge` over `tried`) loses the finding. KILLED by `tests/v2/test_v21_r4_probe_record.py` (the real probe through /bin/sh, every write redirected into the test's directory) |
| `_judge` [45] | `sorted()` -> `list()` of the names | draft audit "deterministic either way"; both copies: live order is the probe's, a replay from the sorted record is alphabetical — the report is not its own record. KILLED by the same file |
| `_judge` [106] | the lead-in `the probe's ` of the message | **AUDITED** (both copies REVISED the grounds and kept the class): the names and the cause words stay; the one reader the draft missed (`validation/v21/sandbox/run.sh:67`, `'did not run' in p`) matches the tail the mutant keeps |

Side finding fixed in the same commit: `run.sh`'s "bwrap ran" heuristic matched the round-4 message ("the check did not
run") and printed "bwrap ran: NO" for a probe that ran with a try that never reported; it now matches the old specific
message (`the sandbox did not run the probe`).
