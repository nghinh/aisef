# B-03 round 3 — the open findings of the probe modules, classified

**Status: investigation only.** No product code, test or record was changed on this branch (`v21r3/probes`, BASE
`3dc827b`). Everything below is either *measured* (a script under `$OUT`, its exact output kept next to it) or says so.
The three names the REPORT carries (§0.4 "Việc cũ còn chờ": namespace-package, lỗi trước subprocess, `file_artifact`
RecursionError) were all I started with; the survivor audits and reviews of B-03 hold more, and the list below is every
open probe-module item I found, with its source.

## 0. The instruction, and one correction of how it was read

> Rà các phát hiện còn mở của probe module và phân loại rõ lỗi cần sửa, giới hạn đã biết hay quyết định cần chủ sở hữu.

Classes used, exactly one per item: **DEFECT** (the code does what its own contract says it must not; smallest correct
change given), **KNOWN_LIMIT** (acceptable, what it is, where it must be stated, what bounds it), **OWNER_DECISION** (a
requirement nobody defined; options and the effect of each).

"A fault before the subprocess" was read by the lead as *an exception raised in a probe before its child starts*. The
records say something else: it is the `fault` **step** of `process_effect` placed before a `subprocess` **step**
(A19 mutant 12 notes, T19b defect-1, triage T19 row 0). That is PM-2. The lead's reading is a real question too, so I
measured it (PM-6); it turned out to be a different, smaller matter.

## 1. The table

| ID | Finding | Source in the records | Class | A fault read as a verdict? | Reached from `aisef run`? | The fix touches → probes whose `EXECUTION_DIGEST` changes (rows to re-demonstrate) |
|---|---|---|---|---|---|---|
| PM-1 | A subject below a directory with no `__init__.py` (under a package or another such directory) is never located: `resolve()` raises `KeyError`, the probe answers UNRUNNABLE | A19 defect-1; A21 defect-1; both reviews; REPORT §0.4 "namespace-package" | **DEFECT** | no: UNRUNNABLE / ENVIRONMENT, retryable. (Before the B1 split, `cli_invocation` answered REFUTED for the same layouts) | yes | `cli_invocation.py`, `process_effect.py` → cli_invocation, process_effect, python_callable_v2 (15 rows) |
| PM-2 | A `fault` step before a `subprocess` step is admitted, never delivered to the child (`fired: false`), and the scenario is judged on the unfaulted run | T19b defect-1; A19 mutant 12 + review issue 2; triage T19 row 0; REPORT §0.4 "lỗi trước subprocess" | **DEFECT** | **yes**: a product that fails under the fault is SATISFIED; the record keeps the verdict only | only through an authored plan (none shipped, none calibrated) | `process_effect.py` → process_effect (3 rows) |
| PM-3 | `ast.parse` raising `RecursionError` / `MemoryError` on a valid deeply nested file escapes `observe` and `run_probe` | T27a defect-1; T27a review issue 4; triage T27 row 9; REPORT §0.4 "RecursionError" | **DEFECT** | no: an exception; the story is recorded REFUSED, delivery FAIL | yes | `file_artifact.py` → file_artifact (4 rows) |
| PM-4 | `file_artifact` detail inaccuracies: `unparsable` reads `x.py:None` for a NUL byte on ≥ 3.12; the module docstring's "Absence" paragraph omits `python_imports` | triage T27 rows 9, 30; T27a report + review issue 5 | **DEFECT** (cosmetic; ride with PM-3) | no | detail is dropped on the run path (PM-8) | same edit as PM-3 |
| PM-5 | The answers the subject's process relays (exit code, returned value) are the subject's own claim; hostile candidate code can make a broken product SATISFIED | triage T21 row 47; T21a report summary; T21a review issue 7; A18 review issue 5 | **OWNER_DECISION** | **yes**, by a hostile candidate only | only with candidate code written to do it | docs, or a redesign (cli exit status) |
| PM-6 | Host-side faults before the controller starts (evaluation directory, `_prepare`, `open(harness.log)`, range start): UNRUNNABLE or an exception, never a verdict | the lead's reading; measured here | **KNOWN_LIMIT** | no | yes | none |
| PM-7 | `EXECUTION_DIGEST` does not cover `runtime/process_range.py`, `range_anchor.py` (or `product/outcome.py`): their edits leave every calibration row valid | TRACEABILITY R-3.1; 360° §3.1 | **OWNER_DECISION** | no | identity only (the RunSpec's `kernel` capability *does* change) | `PROBE_SOURCES` of three probes |
| PM-8 | `classify_failure` drops `Observation.detail` for OBSERVED: the file, step or cause a refutation names reaches no record | `closure-evidence/v2/cycle2/PROBE-DIAGNOSTIC-GAP-001.json` (open); triage T27 row 4 | **OWNER_DECISION** (already recorded; not re-opened) | no | yes | `probe/protocol.py` — frozen, Cycle-1 identity |
| PM-9 | A count of 0 over a selection of zero files is SATISFIED (`python_imports`, `grep_count`) | T27a review issue 6 | **OWNER_DECISION** | partly (vacuous truth) | yes | `file_artifact.py` |
| PM-10 | Cosmetic diagnostics: `locations` in breadth-first order; an empty absence note for a bare directory that shadows a stdlib package; a memoryview result read as a type name by `process_effect`, as bytes by `python_callable_v2` | triage T27 row 19; A19 review issue 3; T19b review issue 5 | **KNOWN_LIMIT** | no | no | none |

Reading the last column: a probe-file byte edit leaves **0 of 19** shipped calibration rows matching the bytes that run for
the probes it changes (§3), so every DEFECT fix is paid for with one recalibration and one mutation re-measure of the
changed module. PM-1, PM-2, PM-3 and PM-4 should be one window (§4).

## 2. The findings

### PM-1 — a module below a directory without `__init__.py` is never located

**Claim.** `resolve(dotted, search)` of the controller script walks the dotted name with
`PathFinder.find_spec(<prefix>, <parent's locations>)`. For a component that is an implicit namespace portion that call
builds a `_NamespacePath`, whose constructor reads `sys.modules[<parent>].__path__`; the controller deliberately never
imports the subject, so `KeyError` ends the lookup. Code at BASE: `aisef2/probe/process_effect.py:514-523` (the
`HARNESS` script, called at L727, `inside` at L511) and `aisef2/probe/cli_invocation.py:760-768` (called at L802). A
depth-1 namespace (`ns/mod.py`) is not affected: its parent path is `sys.path`.

**Measured** (`repro-1`, `repro-1b`; real checkouts, real controller/agent processes, no injection). Premise on every
layout: CPython itself imports the module and `f() == 1` (rc 0).

| layout | process_effect | cli_invocation | python_callable_v2 |
|---|---|---|---|
| `ns/mod.py` (control) | OBSERVED SATISFIED | OBSERVED SATISFIED | OBSERVED SATISFIED |
| `pkg/__init__.py` + `pkg/inner/mod.py` | **HARNESS_FAILED** "the harness raised KeyError" | **HARNESS_FAILED** "controller ended without a result (exit 1)" | OBSERVED SATISFIED |
| the same under `src/` | HARNESS_FAILED | HARNESS_FAILED | OBSERVED SATISFIED |
| `ns/inner/mod.py` | HARNESS_FAILED | HARNESS_FAILED | OBSERVED SATISFIED |
| `ns/reg/__init__.py` + `ns/reg/mod.py`, all-regular (controls) | OBSERVED SATISFIED | OBSERVED SATISFIED | OBSERVED SATISFIED |
| `a/b/__main__.py`, `:__main__` (N2) | — | HARNESS_FAILED | — |

`run_probe` gives `Unrunnable` for every HARNESS_FAILED row. Same on macOS CPython 3.14.7, macOS 3.12.14 and the Linux
guest 3.14.8 (`repro-1.out`, `.py312.out`, `.guest.out`). History (`repro-1.v2.0.0.out`, `repro-1.pre-b1.out`):
`v2.0.0` behaves as BASE; at `098dd7a^` (before the B1 controller/subject split) `process_effect` was already
UNRUNNABLE and `cli_invocation` answered **REFUTED** — a fault read as a verdict — which the split turned into a
harness failure. The defect is older than B1 and no released version answered wrongly.

Other layouts tried (`repro-1b`), all consistent with CPython: a namespace spanning root and `src/` (found), a regular
package in `src/` shadowing a namespace directory at the root (`SUBJECT_ABSENT`, as CPython's import fails),
a namespace directory named like a stdlib package (`json/mod.py`: CPython's import fails because the stdlib's regular
package wins; the probe answers OBSERVED/REFUTED "importing the subject raised ModuleNotFoundError", a present subject
that does not work — as the module's contract says), and a module that exists only in the stdlib (`SUBJECT_ABSENT`,
"resolves only outside the revision"). No layout was found in which the controller resolves a *different* module than
the subject's own import.

**Consequence.** Fail-closed, never a verdict. The route is `PROBE_UNRUNNABLE`, owner ENVIRONMENT, retryable
(`aisef2/control/owner.py:89`), at the CANDIDATE point (at the parent the subject is simply absent): the developer is
not charged and is not told, `detail` being dropped (PM-8), so a developer who forgot `__init__.py` in a subpackage —
the most common layout slip, per A21's reviewer — retries until the budget ends. Relied on by: `admit_story`
(`plan/story_admission.py:154`), `prove`/`reprove` (`orchestrate/proof.py:73`), `review_verify.verify`
(`app/review_verify.py:135`), the calibration records.

**Classification: DEFECT.** The module contract (`process_effect.py` docstring "Subject", `cli_invocation.py` docstring
"Subject") says the module is located with the import system's path finder; only a module that does not resolve or
resolves outside the checkout is absent.

**Smallest correct change** (`fix-sketch-PM-1-namespace.diff`, about 15 added lines and one import in each HARNESS script): around each
`find_spec`, install for that one lookup a stand-in `types.ModuleType(<parent>)` carrying the parent's location list in
`sys.modules`, freeze the resulting locations to a plain list while it is there, remove it in a `finally`. It keeps the
B1 property (the controller imports nothing of the subject; the stand-in is not subject code). *Validated on a scratch
copy, not on the branch:* L1–L3 and N2 become OBSERVED/SATISFIED, every control is unchanged (`repro-1.fixed-copy.out`,
`repro-1b.fixed-copy.out`), and 19/19 classes still contrast on the committed fixtures (`repro-7.fixed-copy.out`).
Rejected: importing the parent in the controller (breaks B1); `PathFinder._get_spec` (private API); a hand-written
directory walk (re-implements the finder; divergence risk).

**Recalibration cost.** See §3. `EXECUTION_DIGEST` changes for cli_invocation (`ab017381…` → `dcb9b7b1…` on the
scratch copy), process_effect (`3b39d380…` → `5a4a2d9c…`) and python_callable_v2 (`e9f8dcdd…` → `b0b716f9…`, which
imports `cli_invocation.py`'s bytes), not for file_artifact. Capability `DIGEST` is unchanged and **no
`CAPABILITY_VERSION` bump is needed**: what a class means does not change; a layout that had no observation gets one,
so no earlier approval can have relied on a verdict there (ADR-V2.1 ADR-2's own criterion).

**Reached from `aisef run`:** yes (catalog probes → `story_runner` → `prove`/`admit_story`). I called `observe` and
`run_probe` — the calls the kernel makes — not a full run (no provider).

**Tests the fixing WP should add (not written here).**

| requirement | test | a plausible wrong fix it must fail |
|---|---|---|
| a module below a no-`__init__` directory is located and run, for both probes | L1, L2, L3 × {process_effect `returns`, cli_invocation `exits`} → OBSERVED SATISFIED, with the same premise subprocess as `repro-1` | "resolve returns None for a namespace parent" (→ SUBJECT_ABSENT); "swallow KeyError as absent" |
| `:__main__` of a nested namespace package is located | N2 | a fix that only repairs the callable form |
| where CPython's import fails the probe does not invent a module | N4 → SUBJECT_ABSENT, N5 → OBSERVED REFUTED | a fix that walks directories without the "regular package wins" rule |

### PM-2 — a fault before a subprocess step is admitted and never delivered

**Claim.** `FAULTED = ("call", "expect_raises", "subprocess")` (`process_effect.py:145`; `_scenario_ok`, L269-278)
admits `[fault, subprocess]`; the module docstring says that step "sees one controlled fault" and that "the step's trace
records the fault and whether it fired". `HARNESS/guarded` (L574-592) patches `os.<attr>` in the **controller's own
process** around `subprocess.run` (`do_subprocess`, L682-692); the child is another interpreter and never sees it, and
the controller makes no call to the four patched attributes inside `subprocess.run`. So `fired` is always `false`, and no
verdict reads `fired` (`verdict_of`, L395).

**Measured** (`repro-2`, real checkouts, production `FAULTS`). Two products with one `save()` — *tolerant* (catches
`OSError`, writes the file another way) and *fragile* (lets it escape):

| scenario | tolerant | fragile |
|---|---|---|
| `[fault os.replace, call save]`, observable `returns: true` | SATISFIED, `fired: true` | **REFUTED**, `refuted: raised OSError`, `fired: true` |
| `[fault os.replace, subprocess -m cli]`, `exit 0` + `a.txt` has 1 line | SATISFIED, `fired: false` | **SATISFIED**, `fired: false` |

The fragile product's CLI, run with `os.replace` raising once *inside the child*, exits 1 (last line of the output).
`run_probe`'s record is `Executed(SATISFIED)` — no trace, no `fired`: nothing recorded afterwards shows the fault did not
happen. Reproduced on macOS 3.14.7, 3.12.14, Linux guest 3.14.8. Scan of every tracked JSON/JSONL: 3 scenarios have a
fault step followed by a step, none followed by `subprocess`; the shipped calibration uses `fault` only before
`call`/`expect_raises` (`validation/qualification/c2_effect_calibration.py:164-176`), `subprocess` only without a fault
(L178).

**Consequence.** The one place where a *missing fault* is reported as a verdict: a fault-tolerance obligation over a CLI
subprocess passes for a product that is not fault-tolerant. Bounded: the enforcement is PARTIAL and `FAULT_WITNESS` says
a fault step is a bounded witness; a contract deriving a crash property declares `bounded_witness_measurement`. Relied
on by the same gate as PM-1.

**Classification: DEFECT.** The requirement is defined (docstring above; commit `7de6d79`'s message: "installs a one-shot
stand-in right before the next call / expect_raises / subprocess step") and the code violates it. DECISION-2 as the owner
approved it (`closure-evidence/v2/cycle2/OWNER-DECISIONS.json`) names a closed, harness-owned, deterministic,
range-bounded fault vocabulary and does not mention `subprocess`; the taxonomy proposal
(`docs/implementation/v2/cycle2/CYCLE2-PROBE-TAXONOMY-PROPOSAL.md:153`) says "for the next `call` only"; the two criteria it was approved for (01-04-5, 03-01-5) are crash simulations of a call. The other
agents called this "owner's design decision"; the smallest correct change is not one.

**Smallest correct change** (`fix-sketch-PM-2-fault-subprocess.diff`, one line plus the docstring and the pins): drop
`"subprocess"` from `FAULTED`, so admission refuses `[fault, subprocess]` (UNSUPPORTED → INVALID_SPEC, a hard blocker
that says so). Validated on a scratch copy: the scenario is `UNSUPPORTED` / `InvalidSpec`, `fault → call` unchanged
(`repro-2.fixed-copy.out`). *The alternative* — deliver the patch into the child through the `SUBPROCESS` boot — is a new
capability (a patch executing in a second interpreter), changes what the scenario measures (so it needs a
`CAPABILITY_VERSION` bump and a `bundle migrate`) and nobody uses it; it is the owner's to want, not a repair.

**Recalibration cost.** `EXECUTION_DIGEST` of process_effect only (3 rows); python_callable_v2 does not import
`process_effect.py`. Pins that change: `tests/v2/test_probe_process_effect_units.py:104` and `:180`
(`pe.FAULTED == (…, "subprocess")`; every `FAULTED` kind accepted), and `tests/v2/test_v21_kills3_T19b.py::FaultBeforeSubprocess`
(its docstring already says "if the owner takes the second way this class goes"). After the refusal the controller-side
`guarded` is dead code (`do_subprocess` is its only caller): its 27 mutants (`HARNESS/guarded`; 14 killed by T19b, the A19
EQUIVALENT audits 12, 17, 20-26) lose their only path, so the fixing change should delete `guarded` and let `do_subprocess`
call `subprocess.run` directly, and remap the audits. **One judgment for the owner:** the
removal narrows the stimulus grammar, which ADR-2's wording would bump; nothing approved can have used the combination
(scan above) and a spec that did would become INVALID_SPEC, not silently different, so I recommend **no bump**, recorded
in the fixing commit.

**Reached from `aisef run`:** only if a bundle authors the scenario (admission accepts it today; `spec_class` returned
`scenario_files` in `repro-2`). None shipped.

**Tests proposed.** `[fault, subprocess]` has no class (`spec_class` None) and `run_probe` returns `InvalidSpec`;
`[fault, call]` and `[fault, expect_raises]` still run and fire (`trace[...].fired is True`); a plausible wrong fix —
refusing only inside `observe` while `spec_class` still admits — must fail the `spec_class` assertion.

### PM-3 — a deeply nested valid file raises out of the probe

**Claim.** `import_facts` (`aisef2/probe/file_artifact.py:258-286`) catches `(UnicodeDecodeError)` and
`(SyntaxError, ValueError)` around `ast.parse` (L265-269). A file that is valid Python but nests past the compiler's
stack raises `RecursionError` (and a chain of ~6,000 unary operators or conditional expressions raises `MemoryError`,
CPython's own parser limit), which escapes `import_facts` → `facts_of` → `observe` (it catches `Refused` only).

**Measured** (`repro-3`, `repro-3b`). `x = 1` + `+1` × 100,000 on both readers (a real git repository's object store —
what `aisef run` uses — and a plain directory): `observe` and `run_probe` **raise** `RecursionError`. Controls: a syntax
error → OBSERVED REFUTED naming `pkg/deep.py:2`; a NUL byte → OBSERVED REFUTED naming `pkg/deep.py:None`; a parsable
file with one import → `matches: 1`.

First failing size of `x = 1` + `+1` × N (binary-operator, attribute and call chains):

| host | RecursionError from N = |
|---|---|
| macOS CPython 3.14.7 | 95,094 |
| Linux guest CPython 3.14.8 (8 MiB stack) | 43,497 |
| macOS CPython 3.12.14 | 9,996 |

and `MemoryError` from N = 5,967 on all three for `not`-chains, unary minus chains and chained conditionals; a flat list (2,097,152 elements on macOS, 262,144 in the guest)
and nested parentheses (`SyntaxError` from 201) are not affected.

**Consequence.** Fail-closed at run level: the exception propagates out of `run_story`; `aisef2/app/run.py:466` records
the story as `REFUSED: RecursionError` in `story_errors`, `delivery` becomes FAIL ("N stories were refused",
`app/run.py:252`; pinned by `tests/v2/test_app_units.py:450`), the run goes on. No verdict. A direct caller
(`review_verify.verify`, calibration, the qualification harness) gets the exception. Reach is narrow — a machine-generated
or adversarial source file — and real.

**Classification: DEFECT.** `Probe.evaluate` returns a typed result; an exception is outside the protocol
(`protocol.py` docstring: "a harness failure ... is UNRUNNABLE"), and the module's own rule for a resource limit on a
selected file is "a harness refusal, never a verdict" (`FILE_CAP`, L107).

**Smallest correct change** (`fix-sketch-PM-3-4-file-artifact.diff`): `except (RecursionError, MemoryError): raise
Refused(...)` beside the existing `except`. *Refuse, not refute* — the T27a agent proposed REFUTED ("count unestablished");
the table above is why I do not: the same file parses on one host and not on another, so a REFUTED verdict (owner
DEVELOPER, charged to the developer) would be a function of the host, which `cli_invocation`'s docstring names as the one
thing a verdict must never be. The `MemoryError` clause cannot be told from a real out-of-memory by type; scoped to the
one `ast.parse` call, the cost of that confusion is one UNRUNNABLE retry. If the owner prefers REFUTED the two lines
change place; say so.

**Validated on a scratch copy:** the deep file → `Unrunnable` on both readers; syntax error and parsable controls
unchanged (`repro-3.fixed-copy.out`).

**Recalibration cost.** `EXECUTION_DIGEST` of file_artifact only (4 rows); capability unchanged (an exception becomes a
typed refusal; no class changes meaning), no bump.

**Reached from `aisef run`:** yes — `python_imports` over candidate trees at PARENT, CANDIDATE and POST_MERGE, and
reviewer reproducers through `review_verify`.

**Tests proposed.** Patch `fa.ast.parse` to raise `RecursionError` / `MemoryError` (the host-independent way, as
`test_a_nul_byte_is_no_count_and_no_crash_on_every_interpreter` does for the 3.11 `ValueError`) and require
`HARNESS_FAILED` / `Unrunnable` naming the file on both readers; the same file *without* the patch must not be needed.
A wrong fix that returns `unparsable` (REFUTED) must fail the `HARNESS_FAILED` assertion.

### PM-4 — `file_artifact` detail inaccuracies (ride with PM-3)

* `except (SyntaxError, ValueError)` formats `f"{rel}:{getattr(e, 'lineno', None)}"` (L269). A NUL byte is a
  `SyntaxError` with `lineno None` from CPython 3.12 (a `ValueError` up to 3.11): `pkg/deep.py:None` (measured,
  `repro-3.out`). The documented "the file and line named" cannot name a line there; `…:?` keeps the existing pin
  `tests/v2/test_v21_kills3_T27a.py:243` (`startswith("x.py:")`) valid (the sketch uses it).
* The module docstring's "Absence" paragraph names `grep_count` only; `observe` (L545) applies the rule to
  `python_imports` too (06d4e62 added the class and the tuple entry, not the sentence).

Both are DEFECTs of *text*; no consumer reads the value (PM-8 drops it on the run path). They are not worth a
recalibration on their own — a docstring edit changes `EXECUTION_DIGEST` like any byte (§3) — so they go in the same
edit as PM-3 or wait for it.

### PM-5 — the subject's relayed answers are the subject's own claim

**Claim.** The subject's code runs in the agent process (`cli_invocation.AGENT`, L514-680), shared by `cli_invocation`,
`process_effect` and `python_callable_v2`. It answers each controller request with `send({... "code", "raised",
"returned" ...})`; the controller builds the verdict from those answers. Code of the revision can reach the agent's own
namespace (`import __main__` → `OPS`, `send`, `WOUT`, `request`) and answer for itself. The module docstring of `cli_invocation.py` (B1, "Controller and subject process") claims
"Code of the revision therefore cannot ... build the facts the verdict is decided from"; its WEAKEST_PATH paragraph says the
subject "builds no fact"; `process_effect.WEAKEST_PATH` says "the controller alone builds the facts". For the relayed
answers that is not so.

**Measured** (`repro-5`; the probes are real, the *product is a simulated hostile candidate* — a module that rewrites
`__main__.OPS["call"]` at import and, in `main`, answers its own invocation and the closing exchange on the agent's
channel). Over a `main()` that raises and a `compute()` that returns 999:

| probe, observable | honest module | hostile module |
|---|---|---|
| cli_invocation `exits {exit_code: 0}` | REFUTED | **SATISFIED** |
| process_effect `returns 1` | REFUTED | **SATISFIED** |
| python_callable_v2 `returns 1` | REFUTED | **SATISFIED** |

The `process_effect` and `python_callable_v2` forgery is one assignment (`OPS["call"] = …`); `cli_invocation` needs the
reviewer's four-line form because the import happens inside the invocation (T21a review, `forge_send.py`). The same
module answering with a malformed `agent_failure` produces HARNESS_FAILED, not a verdict (`repro-5b`; A18 issue 5): a
hostile candidate can force UNRUNNABLE and, as above, SATISFIED. What the controller reads itself (workspace files,
capture files, the step trace, the process's own exit when it ends) stays authentic.

**Consequence.** Fail-open, for adversarial candidate code only; there is no benign path. The precondition is not
imaginary: in attempt 4 a developer session read `aisef2/probe/process_effect.py` and the hidden stimulus
(`DEVELOPER-CONFINEMENT-GAP-001`, OPEN). I did not read those sessions and do not claim any session forged an answer.
Both implementer and verifier run the same probe, so agreement does not help.

**Classification: OWNER_DECISION.** No cheap correct change exists, and it is not a regression of B1: charter §7's
required property ("candidate code cannot manufacture, spoof, emit, overwrite or directly control the authoritative
ProbeResult/verdict channel", "Do NOT require full hostile-host isolation") is met for the *channel*; the relayed values
are its input. Options:

| option | effect |
|---|---|
| (a) Accept and state it: a one-sentence limit in the B1 docstrings / `WEAKEST_PATH` and in REPORT's limits table (the A1 `.pth` row's company), "isolation, not a sandbox: a candidate that rewrites the agent's operation table controls what the probe is told" | no behaviour change; an edit of probe docstrings changes three `EXECUTION_DIGEST`s (§3) — put the sentence in docs first (REPORT, `ANCHOR-THREAT-MODEL.md`), in the module on the next probe window |
| (b) For `cli_invocation` exits classes only: have the controller start the invocation as its *own* child and read `returncode` from the OS | closes the exit-code forgery; breaks "pre-steps invoke the same subject in the same child process, in order"; does nothing for `returns`/`raises` classes, whose value must be serialised by the subject's own process; a redesign |
| (c) Hide the agent's names (`OPS`, `send`, `WOUT`) behind a function scope | raises the bar for a hurried model; `sys._getframe`, `gc`, `inspect` still reach them — an obstacle, not a boundary; I would not call it a fix |

I recommend (a) now. Whether the claim in the B1 docstring should be corrected, and whether (b) is wanted, is the
owner's.

### PM-6 — host-side faults before the controller starts

The lead's reading. **Measured** (`repro-4`, `repro-4b`; **[REAL]** = real inputs, **[SIM]** = a fault injected by
monkeypatch, the probe's own handlers real):

| input / injected fault | process_effect and cli_invocation |
|---|---|
| [REAL] scratch directory that does not exist | HARNESS_FAILED "cannot be created: FileNotFoundError" → Unrunnable |
| [REAL] workspace names `a` and `a/b` | HARNESS_FAILED "cannot be prepared: FileExistsError" → Unrunnable |
| [REAL] NUL byte in a `subprocess` argv (admitted: `_subprocess_ok` takes any `str`) | HARNESS_FAILED "the harness raised ValueError" → Unrunnable, *ENVIRONMENT* for what is a plan-authoring error |
| [REAL] `[fault, subprocess]` of a module that does not exist | OBSERVED REFUTED (the child exits non-zero) |
| [SIM] `_evaluation_dir` / `_prepare` raise `OSError`; `ProcessRange.start` raises `OSError` | HARNESS_FAILED → Unrunnable |
| [SIM] `_prepare` or `ProcessRange.start` raise `ValueError`; `open(harness.log)` raises `OSError(EMFILE)` | **no result: the exception propagates out of `observe`** |
| [SIM] `on_range` raises after the range started | exception; the range is left to its acquirer (1 member until released) |

**Consequence.** No fault became a verdict, in any row. Two inconsistencies: a non-`OSError` (or an `open` failure
outside the `try`, `process_effect.py:883`, `cli_invocation.py:1013`) escapes as an exception instead of the
documented UNRUNNABLE — contained at run level exactly as PM-3 (`REFUSED`, delivery FAIL) — and a plan-authoring
error can read as an environment fault. For `on_range`, `StoryScope.acquire` releases the resource itself before it
raises (`runtime/story_scope.py:90-105`, read, not run), so no range leaks on the product path; a direct caller's hook
that raises owns the release.

**Classification: KNOWN_LIMIT** — fail-closed, bounded by the run-level containment, not worth a recalibration alone.
State it in the module docstrings' "harness preconditions" paragraph on the next window; the NUL-in-argv check
(`_subprocess_ok`: reject `"\0"` in an argv element) is one line to take with PM-2 if the owner wants INVALID_SPEC there.

### PM-7 — `EXECUTION_DIGEST` and the runtime files (TRACEABILITY R-3.1)

**Claim and correction.** `PROBE_SOURCES` of process_effect is `protocol.py`, `python_callable.py`,
`cli_invocation.py`, `process_effect.py`; `runtime/process_range.py` (imported) and `range_anchor.py` (run) decide what
the probe observes about a process and are outside. TRACEABILITY R-3.1 says the calibration rows **and the RunSpec** do
not change; that holds for the RunSpec's per-probe capability entries only. **Measured** (`repro-6`, scratch copies, one byte changed in each):

| edited file | probes whose `EXECUTION_DIGEST` changes | the RunSpec's `kernel` capability |
|---|---|---|
| `runtime/process_range.py`, `runtime/range_anchor.py` (even a semantic edit: `members()` returns `[]`) | none | changes |
| `product/outcome.py` | none | changes |
| `probe/protocol.py` | all five, **including the frozen Cycle-1 probe** `1961e84d…` | changes |
| `probe/cli_invocation.py` | cli_invocation, process_effect, python_callable_v2 | changes |
| `probe/process_effect.py` / `file_artifact.py` / `python_callable_v2.py` | that probe only | changes |

So the *run's identity* does cover the runtime (`kernel_digest()` hashes every `.py` of `aisef2`,
`app/run.py:77-84`, bound at `runspec_of` L210); what a runtime edit does **not** do is invalidate the calibration rows,
the evidence that the probe contrasts.

**Consequence.** No wrong verdict by itself; a latent drift of the *evidence* from the code. The guards that remain are the
full suite and the mutation kill sets, not check 9.

**Classification: OWNER_DECISION** (ADR-2 recorded it as adapted: "chưa phủ runtime/dependency như §9.2 mục 3"). Options:
(a) add the two runtime files to `PROBE_SOURCES` of the three probes that use `ProcessRange` (cheap, exactly R-3.1; `python_callable.py`'s Cycle-1
identity must not change); (b) the transitive closure of what a probe imports from `aisef2` (any kernel edit then forces
recalibration — arguably right, certainly churny; not sized here); (c) keep, state it in REPORT as a limit. If (a): take it
in the same window as PM-1 (those probes recalibrate anyway; afterwards a runtime edit costs one recalibration, which is
the intended effect).

### PM-8 — the observation detail never reaches a record (PROBE-DIAGNOSTIC-GAP-001)

Already a recorded, escalated finding (`closure-evidence/v2/cycle2/PROBE-DIAGNOSTIC-GAP-001.json`, design
`docs/implementation/v2/cycle2/PROBE-DIAGNOSTIC-CHANNEL-DESIGN.md`, status OWNER_DECISION_REQUIRED). It matters here
because it is why PM-1 is silent and why `unparsable`'s file name (PM-3, PM-4) is visible only to a direct `observe`
caller: `classify_failure` (`probe/protocol.py:185`) turns OBSERVED into `Executed(verdict)`; `repro-3` shows the
run-level result for a named unparsable file is `Executed(REFUTED, reason=None)`. **Not re-opened.** Constraint to carry
to its decision: `protocol.py` is part of the frozen Cycle-1 identity (`test_the_cycle1_probe_keeps_its_one_frozen_digest`,
the Q0 `cycle2_baseline` guard); an edit there is a re-freeze, not a recalibration (§3, `repro-6`).

### PM-9 — an empty selection is a vacuous SATISFIED

**Measured** (`repro-8`, 8a): `python_imports {matches: 0}` over `path:README.md` (a single non-`.py` file), over a
directory with no `.py`, and over a directory holding only a dot-file → OBSERVED SATISFIED with `files: 0, matches: 0`;
`grep_count {matches: 0}` likewise. Pinned as intended by T27a (`test_a_single_non_python_file_is_not_selected`) and
visible only in the facts (PM-8). Reachable: a prohibition that is the *only* obligation guarding a tree whose `.py`
files were moved or renamed. **OWNER_DECISION:** what a count over zero files means — vacuous truth (today), count
unestablished (REFUTED), or refused. The vacuous reading is the usual one for a universally quantified prohibition and
presence is protected by `exists`/behaviour obligations; the cost of the other readings is a spec that cannot be
satisfied by an empty-but-valid tree. No change recommended without the decision.

### PM-10 — three cosmetic diagnostics (KNOWN_LIMIT)

All measured in `repro-8`; none touches a verdict.

* `locations` follow `ast.walk` (breadth first): an import inside a function is listed after every module-level one
  (`[['pkg/m.py', 5, ['yaml']], ['pkg/m.py', 2, ['requests']]]`), and the 50-entry cap keeps the first 50 in that order.
* A bare directory `json/` (no `__init__.py`) in the revision with subject `json.decoder:JSONDecoder`: `SUBJECT_ABSENT`
  with an empty note; CPython's import takes the stdlib `json.decoder` (outside), so "resolves only outside the
  revision" would be the accurate note (A19 review issue 3; the verdict is the same).
* A function returning a `memoryview`: `process_effect` reports `last_unserializable: "memoryview"` and
  `returns_bytes_hex` is REFUTED; `python_callable_v2`'s `returns_bytes` reads it as bytes and is SATISFIED. Documented in
  both module docstrings; the two probes differ by design.

Where to state: the REPORT limits table (one line each). No code change.

## 3. What a probe-file change invalidates (measured, shared by PM-1…PM-4, PM-7)

1. **Calibration rows.** `aisef2/app/calibrations.py` holds 19 rows keyed by each active probe's `EXECUTION_DIGEST`.
   `repro-9`: BASE has a row for 19/19 classes; on the scratch copy with PM-1…PM-4 applied, **0/19** (per probe:
   file_artifact 0/4, python_callable_v2 0/7, cli_invocation 0/5, process_effect 0/3). With no row, static admission
   check 9 refuses every plan that uses the probe, `review_verify` answers UNVERIFIABLE ("not calibrated at the bytes that
   run"), and `tests/v2/test_v21_identity_bytes.py::ThreeIdentities::test_the_shipped_calibrations_name_every_class_at_the_bytes_that_run_now`
   is red — until `python -P validation/qualification/release_calibration.py --write`, which re-demonstrates the 19
   classes (about 25 s, `demonstrated_at` of the shipped rows), rewrites `aisef2/app/calibrations.py` and writes the
   next record, `closure-evidence/v2/release/V2.1.0.dev0-PROBE-CALIBRATIONS-3.json` (a record is never rewritten). The
   same loop on the scratch copy with PM-1…PM-4 applied: 19/19 classes contrast, 0 problems (`repro-7.fixed-copy.out`).
2. **Which probes change with which file** (`repro-6`; `PROBE_SOURCES` read for the rest): `protocol.py` and
   `python_callable.py` → all four (python_callable, cli, effect, pc2) and the frozen Cycle-1 digest `1961e84d…`
   (so neither is touched here); `cli_invocation.py` → cli, effect, pc2 (15 rows); `process_effect.py` → effect (3);
   `file_artifact.py` → file_artifact (4); `python_callable_v2.py` → pc2 (7). Capability `DIGEST` — what specs, plans and
   approvals bind — changes only with `CAPABILITY_VERSION`; none of PM-1…PM-4 needs it (judgment flagged for PM-2).
3. **Records that name the old bytes** (`git grep` of the four digests): `closure-evidence/v2/v2.1/P5-FALSIFIABILITY.json`
   (regenerated by `validation/qualification/p5_falsifiability.py`), the Q0/C2-P5 re-verification and the
   calibration record family (history stays as committed), and the mutation record (below). `ARCHITECTURE-EXCEPTION-V2-007.json`
   quotes digests as history.
4. **Mutation record.** `MUTATION.json` at BASE: `cli_invocation.py` 86 targets / 1,769 mutants, `process_effect.py`
   79 / 1,653, `file_artifact.py` 45 / 763, `python_callable_v2.py` 31 / 768 (importer of cli_invocation's script).
   A changed function has a new `source_sha256`, so its positional survivor audits are unmapped and must be remapped
   (`SURVIVOR-AUDITS.json`, entries keyed by target + index + description + source digest; 38 of the 213 are in
   these modules). At campaign 3's rate (7,867 mutants in 14.5 h on four workers) the upper bound is ≈ 8 h for a
   cli_invocation edit with its importers, ≈ 3 h for process_effect, ≈ 1.5 h for file_artifact alone — an estimate;
   the delta tool decides the real set.
5. **Run identity.** Any `aisef2` edit changes the RunSpec `kernel` capability (`repro-6`); runs recorded before and
   after differ in `runspec_hash` by construction.
6. **Existing tests against the patched scratch copy** (`modules2.base.txt`, `modules2.fixed-copy.txt`; real runs, macOS
   3.14.7). Two scratch trees of BASE — one untouched, one with the PM-1…PM-4 sketches — each with `tests/`,
   `validation/` and the `closure-evidence`/`docs` files the tests read; 29 modules: the direct probe test modules and the
   B-03 kill files of A18, A19, A21, T18a/b, T19a/b, T21a/b, T27a (the other 37 modules that import `aisef2.probe` are
   record checkers and orchestration tests; not run). Identical results (all OK) in both: `test_probe_process_effect`
   (24 tests), `test_c2_cli_invocation` (32), `test_c2_cli_protocol` (18), `test_c2_file_artifact` (40),
   `test_python_callable_v2` (33), `test_v21_identity` (13), `test_v21_python_imports` (5), A19 (3), A21 (2), T27a (12),
   T18a/b, T19a, T21a/b and the calibration, protocol and Cycle-1 `python_callable` modules. **Red only on the patched copy:**
   `test_probe_process_effect_units::Vocabulary` ×2 (`test_the_scenario_rules`,
   `test_the_step_vocabulary_is_closed_and_each_kind_has_exactly_its_typed_fields` — PM-2's pins),
   `test_v21_kills3_T19b::FaultBeforeSubprocess` ×2 (PM-2), and `test_v21_identity_bytes::ThreeIdentities` ×2
   (`test_the_shipped_calibrations_name_every_class_at_the_bytes_that_run_now`, `test_calibrations_of_other_bytes_admit_nothing`
   — the calibration rows, until regenerated). Nothing else flipped: the existing A19/A21 namespace tests and T27a's
   `startswith("x.py:")` pin hold under the sketches. (A first pass, `modules.*.txt`, ran before the trees held the
   evidence files; its Q0 failures were identical in both trees and are artefacts of the incomplete scratch tree.)

## 4. Recommended order (one window, paid once)

1. PM-1, PM-2, PM-3 (+ PM-4's two lines) in one change set: three files, four short edits (diffs in `$OUT`), the
   `existing_tests_changed` of PM-2, new tests for each.
2. If the owner picks PM-7 (a): the same window.
3. `release_calibration.py --write`, then the delta and the re-measure of the three changed modules and the importers of
   `cli_invocation.py`, then the records the lead regenerates.
4. PM-5 (a), PM-6, PM-10: text in REPORT now; in the modules on that window.

Decisions only the owner can make: PM-5 (accept and state, or commission a design), PM-7 (scope of the identity), PM-9
(empty selection), PM-8 (already open), and one judgment inside PM-2 (no `CAPABILITY_VERSION` bump) plus the refuse-vs-
refute choice inside PM-3.

## 5. Searched, and found not to be probe-module items

* `docs/v2.1/REPORT.md` §0.4; STATUS B-03; TRACEABILITY (R-3.1 and the "open" rows); memory
  `aisef-trang-thai-2026-10-08-b03.md`; `ROUND-2.md`; `SURVIVOR-AUDITS.json` (213 entries; 38 in `aisef2/probe/`, none OPEN);
  round-1 hand-overs `kills3/out/*/report.json` and their `review/report.json` (every `defects`, `issues`, `owner`
  note of A18, A19, A21, A27, T18a/b, T19a/b, T21a/b, T27a); the triage `triage/out/T*.json` (`unlisted_finding` of
  T18, T19, T21, T27); `kills3/ledger.json`, `unresolved.json`, `kills4/R2-UNRESOLVED.json`.
* Ledger by module for `aisef2/probe/`: cli_invocation 49 KILLED / 7 AUDITED / 2 EQUIVALENT; file_artifact 31 / 1 / 0;
  process_effect 53 / 2 / 16; python_callable_v2 66 / 9 / 1. **No OPEN and no DEFECT mutant** — every item above was
  found beside a batch, not as a survivor.
* Not probe modules: `confine._probe` (T05a defect-1, T05c — the sandbox's own measurement probe, fixed in
  `beb974b`); `review_verify.detail` (R06, Q-DETAIL); the three probe files in `site-packages` (incident record 2026-10-07;
  `rm` awaits the owner); `kill_check --only` on script targets (tool; fixed `6288f07`).
* Test-strength notes by reviewers with no product consequence (T19b review issue 4: a guard that ran `call()` twice would
  survive; `_watch` awaiting `STEP` instead of `RESULT` survives one class) — test gaps, not findings.

## 6. Real, simulated, neither

* **Real runs (macOS arm64):** CPython 3.14.7 (all scripts), CPython 3.12.14 (`repro-1`, `-2`, `-3`, `-3b`).
* **Real runs in the Linux guest** (`guest.sh … X1`, image `aisef-sandbox-measure`, CPython 3.14.8, Linux 7.0.12-linuxkit
  aarch64, git 2.47.3): `repro-1`, `-2`, `-3`, `-3b` — identical results except the PM-3 threshold.
* **Simulations (labelled in the output):** `repro-4`/`-4b` [SIM] rows (injected faults); `repro-5`/`-5b` (the hostile
  candidate is a module I wrote); every `fixed-copy` run (a patched scratch copy under `$OUT`, never the branch).
* **Neither:** the §3 mutation and time figures are read/estimated; PM-6's `StoryScope.acquire` is read, not run; the
  CAPABILITY_VERSION judgments are my reading of ADR-2.

## 7. Not established

* No full `aisef run` was executed (no provider); reachability is by the call path and by calling `observe`/`run_probe`.
* Python 3.11 and 3.13, and Windows, were not measured (3.11 is where `ast.parse` raised `MemoryError` earlier;
  `x.py:None` is 3.12+).
* How often a model-written layout omits `__init__.py`, or a candidate file is that deep: not measured. PM-1's
  likelihood rests on a reviewer's remark.
* PM-5 forges three observable shapes (cli `exits`, effect `returns`, pc2 `returns`); `exits_streams`, `blocks`,
  `equality`, `raises` were not tried. No developer session was read for forgery.
* The existing tests were run against the patched scratch copy for the 29 modules of §3.6; the full suite was not.
* PM-7 option (b) was not sized.

## 8. Reproduction index (`$OUT` = `scratchpad/m21/r3/out/probes`)

| script (sha256 prefix) | what | output |
|---|---|---|
| `repro-1.py.txt` (8a776cb4…) | PM-1, six layouts × three probes | `repro-1.out`, `.py312.out`, `.guest.out`, `.v2.0.0.out`, `.pre-b1.out`, `.fixed-copy.out` |
| `repro-1b.py.txt` (f2592a30…) | PM-1, `__main__`, src/, shadowing | `repro-1b.out`, `.fixed-copy.out` |
| `repro-2.py.txt` (62f904f3…) | PM-2 | `repro-2.out`, `.py312.out`, `.guest.out`, `.fixed-copy.out` |
| `repro-3.py.txt` (31e6f8a4…) | PM-3, PM-4 | `repro-3.out`, `.py312.out`, `.guest.out`, `.fixed-copy.out` |
| `repro-3b.py.txt` (3eebd806…) | PM-3 thresholds | `repro-3b.out` (3.14.7 and 3.12.14), `repro-3b.guest.out` |
| `repro-4.py.txt` (433a0215…), `repro-4b.py.txt` (017b8d7c…) | PM-6 | `repro-4.out`, `repro-4b.out` |
| `repro-5.py.txt` (ad72518d…), `repro-5b.py.txt` (4e9da539…) | PM-5 | `repro-5.out`, `repro-5b.out` |
| `repro-6.py.txt` (0a495698…) | PM-7, §3.2 | `repro-6.out` |
| `repro-7.py.txt` (d1862954…) | §3.1 calibrate loop | `repro-7.base.out`, `repro-7.fixed-copy.out` |
| `repro-8.py.txt` (087ffb68…) | PM-9, PM-10 | `repro-8.out` |
| `repro-9.py.txt` (e1737c0a…) | §3.1 rows at the running bytes | `repro-9.base.out`, `repro-9.fixed-copy.out` |
| `fix-sketch-PM-*.diff` | the three diffs against BASE | — |
| `modules.base.txt`, `modules.fixed-copy.txt` (first pass), `modules2.base.txt`, `modules2.fixed-copy.txt` | existing probe tests, BASE vs patched copy (§3.6) | — |

Run from the worktree root as `py.sh probes -I <script>`; the interpreter line is the first line of each output.
