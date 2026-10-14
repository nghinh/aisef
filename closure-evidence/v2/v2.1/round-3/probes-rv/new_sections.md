### PM-11 — a UTF-8 byte-order mark is read as a syntax error **[verifier]**

**Claim.** `import_facts` decodes with `data.decode("utf-8")` (`file_artifact.py:265`) and hands the *text* to
`ast.parse`. A UTF-8 file that begins with a BOM keeps U+FEFF as its first character; `ast.parse` of that text raises
`SyntaxError` (an invalid non-printable character at line 1), while CPython compiles and imports the same bytes (the
tokenizer drops a BOM when it reads bytes). The probe answers `unparsable: pkg/m.py:1` and REFUTED for a file Python
runs. `grep_facts` has the same decode (L247): a `^`-anchored pattern does not match line 1 of such a file.

**Measured** (`rv-fa-bom.py`, `rv-fa-edge.py`, `rv-fa-bom-grep.py`; real `FileArtifactProbe`, `observe` and `run_probe`,
both readers; macOS CPython 3.14.7 and 3.12.14, Linux guest 3.14.8 — a **real run in the guest**):

| file | `observe` (repo reader and plain reader) | `run_probe` | CPython `compile(bytes)` |
|---|---|---|---|
| `import os` | OBSERVED SATISFIED (`matches: 0` expected) | Executed(SATISFIED) | compiles |
| BOM + `import os` | **OBSERVED REFUTED**, `unparsable: pkg/m.py:1` | **Executed(REFUTED)** | compiles |
| BOM + `import requests` | **OBSERVED REFUTED**, `unparsable: pkg/m.py:1` (the spec expected `matches: 1`) | **Executed(REFUTED)** | compiles |
| `grep_count` `^import requests` over a BOM file and a plain file | `matches: 1`, locations `[b.py, 2]` — the BOM file's line 1 is missed | — | — |

Other inputs tried and found consistent with CPython (so *not* findings): a 5,000-digit integer literal, 300 nested
parentheses, 120 nested `if` levels, a tab/space mix — all `unparsable`, all `SyntaxError`/`IndentationError`/`TabError`
under `compile`; form feeds, CR-only and CRLF newlines, a PEP 263 `utf-8` cookie, a 3 MB line, an unpaired-surrogate
escape, `match`, PEP 695 generics, walrus — parse. Two that differ from CPython and are *documented*: a PEP 263
`latin-1` cookie over non-UTF-8 bytes is `undecodable` (the module's rule: "a file that is not UTF-8 leaves the count
unestablished"), and syntax newer than the host (`except A, B:`, a t-string) is `unparsable` on 3.12.14 and parses on 3.14.7
(the interpreter dependence PM-3 discusses).

**Consequence.** A *parse limitation of the harness* is returned as a verdict and charged to the developer — the
failure class V21-37 was created to end ("a line regex counted a docstring line beginning `from` as an import and
rolled back a correct story"; ADR-5), now by the replacement. Fail-closed for the gate (a correct story is refused,
nothing wrong is accepted), a **fault read as a verdict** by the owner's own test. At `review_verify` a REFUTED
reproducer is a CONFIRMED finding (`review_verify.py:141-143`). Likelihood is *not measured*: editors and PowerShell 5's
`-Encoding UTF8` write BOMs; a model writing through a tool normally does not. What it costs when it happens: one story,
silently (the detail is dropped, PM-8).

**Classification: DEFECT.** The module claims to count imports "by syntax, never by a line regex"; the syntax it reads
is not the syntax Python reads.

**Smallest correct change.** `data.decode("utf-8-sig")` at the two sites (L247, L265) — two tokens. *Validated on a
scratch copy* (`fix-bom/`): all four BOM rows above become SATISFIED on both readers, the non-BOM rows and the `latin-1`
row are unchanged, and `grep_count` finds both lines (`matches: 2`). Rejected: passing the bytes to `ast.parse` (honours
the BOM and PEP 263 cookies, but turns the documented `undecodable` rule into something else and changes the fact keys).

**Recalibration cost.** The same edit and the same four rows as PM-3 (file_artifact only; one `EXECUTION_DIGEST`).
Capability unchanged by my reading of ADR-2 — it makes the verdict follow CPython for an input nobody can have relied on
being REFUTED — recommended no bump, recorded in the fixing commit (a judgment, not a measured property).

**Reached from `aisef run`:** yes (`python_imports` and `grep_count` over candidate trees; reviewer reproducers).

**Tests the fixing WP should add (not written here).** A BOM file with only stdlib imports → `matches: 0`; BOM +
`import requests` → `matches: 1`; the same through `grep_count` with `^import requests` on line 1. A plausible wrong fix
that strips U+FEFF anywhere in the text (`replace`) must fail a file whose *second* line is a string containing U+FEFF
(its count must not change).

### PM-12 — a complete read is REFUTED when it took longer than its window **[verifier]**

**Claim.** `observe` takes the time only after `facts_of` has returned
(`expired = time.monotonic() - started > window`, `file_artifact.py:529`) and then answers `SUBJECT_DEADLINE` with the
class's `ON_DEADLINE` verdict, REFUTED for every class (L100-101), *over facts that are complete*. The read is one git
process per file (`reader.blob` → `git cat-file blob`, L322) plus three for the entry and the tree, so its time is
linear in the number of files selected. The window bounds git only through `ExecutionEnv.timeout_s`, a different clock.

**Measured** (`rv-fa-scale.py`, macOS CPython 3.14.7, a git repository of N tiny `.py` files, `python_imports`,
`matches: 0` expected, `timeout_s` 60):

| N files | `within_s` | answer | wall time |
|---|---|---|---|
| 50 | 30 | OBSERVED SATISFIED | 0.41 s |
| 50 | 0.05 | **SUBJECT_DEADLINE REFUTED** (the same, complete, facts) | 0.42 s |
| 400 | 30 | OBSERVED SATISFIED | 3.12 s |
| 400 | 0.05 | **SUBJECT_DEADLINE REFUTED** | 3.08 s |

≈ 7.7 ms per file on this host. With the `within_s` of 10 that the reviewer prompt and the shipped examples use
(`aisef2/app/adapters.py:34`, `app/examples/*.json`), about 1,300 files fit on this host. Windows, a loaded runner or
antivirus were **not measured**; process creation there is slower, so the bound is lower — an expectation, not a number.

**Consequence.** A slow host turns a SATISFIED read into REFUTED: a fault read as a verdict, host-load dependent, for
`python_imports` and `grep_count` over a large tree (and for `exists`/`content`, whose reads are 3–4 processes, only at
sub-second windows). Fail-closed. The rule is the RFC's (§9.2: "a read that did not complete in W is not an observation
of presence", module docstring), so the code does what it says; what is new is that the module's *own* clock decides it
after the fact and that its cost grows with the tree.

**Classification: KNOWN_LIMIT.** Documented rule; bounded by `within_s` × (≈ 8 ms per file here). State it in the REPORT
limits table with the figure. Two changes would remove it, neither a repair: a window checked *while* reading (a
HARNESS_FAILED/REFUTED on a read that did not finish, which changes a class-table row and needs a capability bump), or
`git cat-file --batch` (one process; no verdict change, digest and recalibration like PM-3).

### PM-13 — a spec's regex has no bound in the kernel's own process **[verifier]**

**Claim.** `grep_facts` runs `pattern.search(line)` for every line of every selected file, in the process that runs the
probe — the kernel's (`file_artifact.py:240-251`, called from `facts_of`). `PATTERN_CAP` (512 characters) bounds the
pattern's length, not its cost; `FILE_CAP` (4 MiB) bounds a file, not a line; the window is read after the match
(PM-12). Nothing in `observe`, `run_probe` or `story_runner._probe` puts a clock on it (read: `story_runner.py:349-362`
calls the factory and `run_probe` directly).

**Measured** (`rv-fa-redos.py`, macOS CPython 3.14.7, `grep_facts` directly; the pattern is a plausible author-written
"line of words", `^(\w+\s?)*$`, over `"a" * n + "!"`):

| line length | time |
|---|---|
| 19 | 0.02 s |
| 21 | 0.07 s |
| 23 | 0.30 s |
| 25 | 1.17 s |

×4 for every two characters; a 40-character line is ≈ 10 hours by extrapolation (**not run**). Of the nine distinct
`grep` patterns in the tracked JSON (the shipped LedgerLock workload, the P5 proposal, calibration fixtures) none has a
nested quantifier — measured by a text scan, not by running them.

**Consequence.** No verdict: the run stalls until someone kills it. The pattern is approved (approval is a semantic
check, not a complexity one); the line is the candidate's. A candidate that never meant to is enough (a minified or
generated file), and so is a hostile one.

**Classification: OWNER_DECISION.** The module says no subject code runs and the window bounds the read; nobody defined
what bounds a spec's own pattern. Options: (a) run `grep_count`'s matching in a bounded child like every other probe
(a process, a deadline, a digest change, a recalibration of file_artifact's four rows, PARTIAL → what enforcement?);
(b) refuse at admission a pattern with a quantified group containing a quantifier (a lint: cheap, incomplete);
(c) accept and state: patterns are approved and trusted. Nothing here is recommended without that decision.

## 2.2 Open items of the V2.1 backlog that live in `aisef2/probe/` **[verifier]**

The first pass did not read `docs/v2/V2.1-BACKLOG.md` (38 rows; the charter's §21 register of what 2.0 deferred). Ten
rows name a probe file. Two are PM-5 (V21-26) and PM-8 (V21-04); two are closed in V2.1 and not probe-module findings
any more (V21-37 by `python_imports`, V21-38 by ADR-4); six are listed here and are **not** in PM-1…PM-10. "Ran" =
reproduced by the verifier through the real entry point; "read" = established from the code only.

| row | what the backlog says | status at BASE | evidence | class | cost if changed |
|---|---|---|---|---|---|
| V21-24 | a subject that truncates and rewrites the marker file turns its own observation into HARNESS_FAILED (ENVIRONMENT) instead of REFUTED | **open**; reproduced | **ran** (`rv-marker.py`, the test module's own `app.forge:rewrite`): `returns 1`, `returns 2`, `blocks` all HARNESS_FAILED — never SATISFIED; one detail reads "the harness did not start (exit 0, no READY): tool absent or broken", which is untrue | **KNOWN_LIMIT** (fail-closed; misattributes the owner; a channel the subject cannot hold is a catalog decision, per the row) | digests of the three marker-file probes |
| V21-25 | `blocks` is SATISFIED when the *import*, not the call, outlasts the window | **open**; reproduced | **ran** (`rv-backlog.py`): a module that sleeps at import → `blocks` SUBJECT_DEADLINE **SATISFIED** (the call was never made); the same module with a plain `serve()` → REFUTED | **KNOWN_LIMIT** today (documented window semantics, Cycle-1 class table); a **fault read as a verdict** of one class; the owner's call is whether to arm the deadline at the call | a class-table change: capability bump of `python_callable_v2` and `cli_invocation` `blocks` |
| V21-09 | UNRUNNABLE and INVALID_SPEC serialise alike in the sealed record | **open**; reproduced | **ran** (`rv-backlog.py`): `ProbeRecord.record_digest` is *equal* for `Unrunnable("x")` and `InvalidSpec("x")` while `result` differs | **KNOWN_LIMIT** (low; no verdict uses the digest to tell them apart) | `protocol.py` / `product/outcome.py`: frozen Cycle-1 identity — a re-freeze |
| V21-15 | candidate code can shift ownership away from DEVELOPER | **open**; the mechanism is measured twice | **ran**: V21-24 above and PM-5b (a malformed `agent_failure` → HARNESS_FAILED); PM-1 is the benign instance (a layout, not an attack, is charged to ENVIRONMENT). The row's "leak scan sees only verbatim JSON" part was **not** examined | **KNOWN_LIMIT** (low) | — |
| V21-07 | `file_artifact`'s FULL weakest path can be defeated by a same-user process | **open**; not reproducible here | **read**: the object store is immutable at a SHA; a *plain directory* (fixtures, direct callers) is read file by file, so a concurrent same-user writer is a race. Charter §2/D-05: a same-user adversary is a non-claim | **KNOWN_LIMIT** — the docstring's "Enforcement: FULL" should say "for the object store" | docstring: file_artifact's digest |
| V21-01 | `ProbeRecord.record_digest` binds no witness | **open** | **read** (`protocol.py`); charter D-08 defers it | **KNOWN_LIMIT** (deferred by the charter) | frozen identity |
| V21-32 | `cli_invocation._concluded`'s `harness_failure` branch is unreachable from today's controller | **open**; still so | **read**: `cli_invocation.HARNESS` never emits `harness_failure` facts; `process_effect._concluded`'s is reachable (a `Leak`); unit-tested | **KNOWN_LIMIT** (cosmetic: dead defensive code) | — |
| V21-33 | the AGENT shared with `python_callable_v2` answers ops this probe's controller never sends | **open**; still so | **read**: `invoke` and `bye` are the only ops the cli controller sends (`cli_invocation.py:772-777`) | **KNOWN_LIMIT** (cosmetic; widens nothing: only the controller writes the agent's stdin) | AGENT bytes: all three digests |

Also documented as a non-claim, not a probe finding: `tests/v2/test_v21_identity.py` (module docstring) says test code
"runs as the operator's user and can still change that interpreter or the installed kernel (V2-05 is the sandbox)"; the
backlog row is V21-28 (`aisef2/app/run.py`, not this package).

