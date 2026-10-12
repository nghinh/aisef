# B-03 round 3 — the open findings of the probe modules, classified

**Status: investigation only.** No product code, test or record was changed on this branch (`v21r3/probes`, BASE
`3dc827b`). Everything below is either *measured* (a script under `$OUT`, its exact output kept next to it) or says so.
The three names the REPORT carries (§0.4 "Việc cũ còn chờ": namespace-package, lỗi trước subprocess, `file_artifact`
RecursionError) were all I started with; the survivor audits and reviews of B-03 hold more, and the list below is every
open probe-module item I found, with its source.

**Verified (`v21r3/probes-rv`, stacked on `v21r3/probes`).** A second engineer re-ran every reproduction below from a
fresh checkout, re-measured the numbers this document states, re-checked each classification against the code and
the consequence class, searched for open items the first pass did not find, and challenged the recalibration cost.
The result is §9. Statements corrected in place are marked **[verifier]**. What the first pass missed: it did not read
`docs/v2/V2.1-BACKLOG.md` (38 rows, ten of them about the probe modules), so PM-5 and PM-8 have a second source and eight
backlog rows were unlisted (§2.2); three items nobody had recorded were found by measuring (PM-11 a UTF-8 BOM read as
a syntax error, PM-12 a complete read refuted because it took longer than its window, PM-13 an unbounded regex run in
the kernel's own process); and PM-6 is reclassified (one of its two escape sites is a DEFECT by the rule this
document applies to PM-3).

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
| PM-5 | The answers the subject's process relays (exit code, returned value) are the subject's own claim; hostile candidate code can make a broken product SATISFIED | triage T21 row 47; T21a report summary; T21a review issue 7; A18 review issue 5; **[verifier]** V2.1 backlog V21-26 (IR-B2), which says "no false PASS" — measured otherwise | **OWNER_DECISION** (+ a text DEFECT in three docstrings, §PM-5) | **yes**, by a hostile candidate only | only with candidate code written to do it | docs, or a redesign (cli exit status) |
| PM-6 | Host-side faults before the controller starts (evaluation directory, `_prepare`, `open(harness.log)`, range start): UNRUNNABLE or an exception, never a verdict | the lead's reading; measured here | **[verifier] DEFECT (low)** for the unguarded `open(harness.log)` and the NUL-in-argv admission; KNOWN_LIMIT for the rest (first pass: KNOWN_LIMIT) | no | yes | the same two files as PM-1 — no extra digest, no extra row |
| PM-7 | `EXECUTION_DIGEST` does not cover `runtime/process_range.py`, `range_anchor.py` (or `product/outcome.py`): their edits leave every calibration row valid | TRACEABILITY R-3.1; 360° §3.1 | **OWNER_DECISION** | no | identity only (the RunSpec's `kernel` capability *does* change) | `PROBE_SOURCES` of three probes |
| PM-8 | `classify_failure` drops `Observation.detail` for OBSERVED: the file, step or cause a refutation names reaches no record | `closure-evidence/v2/cycle2/PROBE-DIAGNOSTIC-GAP-001.json` (open); triage T27 row 4; **[verifier]** V2.1 backlog V21-04 | **OWNER_DECISION** (already recorded; not re-opened) | no | yes | `probe/protocol.py` — frozen, Cycle-1 identity |
| PM-9 | A count of 0 over a selection of zero files is SATISFIED (`python_imports`, `grep_count`) | T27a review issue 6 | **OWNER_DECISION** | partly (vacuous truth) | yes | `file_artifact.py` |
| PM-10 | Cosmetic diagnostics: `locations` in breadth-first order; an empty absence note for a bare directory that shadows a stdlib package; a memoryview result read as a type name by `process_effect`, as bytes by `python_callable_v2` | triage T27 row 19; A19 review issue 3; T19b review issue 5 | **KNOWN_LIMIT** | no | no | none |
| PM-11 **[verifier]** | A UTF-8 file with a byte-order mark is `unparsable` for `python_imports` although CPython compiles and imports it; `grep_count` misses a `^`-anchored match on its first line | none — found by measuring | **DEFECT** | **yes**: a parser limitation is REFUTED and charged to the developer (and a REFUTED reproducer is a CONFIRMED review finding) | yes | `file_artifact.py` → file_artifact (4 rows) — same edit as PM-3 |
| PM-12 **[verifier]** | `file_artifact` decides the window after the read: a read that *completed* is REFUTED (SUBJECT_DEADLINE) when it took longer than `within_s`; one `git cat-file` process per file makes the time linear in the files | none — found by measuring | **KNOWN_LIMIT** (documented §9.2 rule) with a measured bound | yes, host-load dependent (REFUTED over a complete SATISFIED read) | yes | none unless the rule changes (a class-table change: bump) |
| PM-13 **[verifier]** | `grep_count` runs the spec's regex in the kernel's own process with nothing but the after-the-fact window to bound it; a pattern with nested quantifiers over a long candidate line does not return | none — found by measuring | **OWNER_DECISION** | no verdict: a hang (denial of service of the run) | yes | `file_artifact.py` (4 rows) if bounded inside the probe |

Reading the last column: a probe-file byte edit leaves **0 of 19** shipped calibration rows matching the bytes that run for
the probes it changes (§3), so every DEFECT fix is paid for with one recalibration and one mutation re-measure of the
changed module. PM-1, PM-2, PM-3 and PM-4 should be one window (§4); **[verifier]** so should PM-11 (the same file as
PM-3), the DEFECT part of PM-6 (the same two files as PM-1) and — if the owner takes option (a) — PM-7.

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

**[verifier]** Three precisions, none of which changes the class. (1) At the PARENT the subject is absent only for a
story that *introduces* the module; for a PRESERVE or VERIFY obligation over a module that already sits below a
no-`__init__` directory, the probe is UNRUNNABLE at the parent and `story_admission.classify` returns
`PROBE_UNRUNNABLE` (`plan/story_admission.py:81-83`; `BLOCKING`, L47): the story is never started. (2) In
`review_verify.verify` an UNRUNNABLE reproducer is UNVERIFIABLE (`app/review_verify.py:138-140`): the finding cannot
become CONFIRMED, so it cannot block (ADR-7: a finding blocks only when the probe reproduces it) — PM-1 costs the
review gate its blocking power for these layouts, it never invents a block. (3) `python_callable_v2` is *not*
defective: its controller never resolves (the agent imports, `python_callable_v2.py:348`); it recalibrates only
because its digest includes `cli_invocation.py`'s bytes. Reproduced by the verifier on macOS 3.14.7, macOS 3.12.14
and the Linux guest 3.14.8 (§9).

**[verifier] One residual the sketch does not cover** (`rv-ns-stdlib.py`, BASE and the sketch applied, macOS 3.14.7):
a no-`__init__` directory *below a name the controller has already imported as a plain module* — `queue/inner/mod.py`,
`types/inner/mod.py`, `hmac/inner/mod.py` — gives HARNESS_FAILED "the harness raised AttributeError" (`sys.modules[parent]`
exists and has no `__path__`), identically with and without the sketch; the sketch stubs only when the parent is *absent*
from `sys.modules`. CPython's own import of those names also fails (rc 1), and `json/inner/mod.py` — `json` is a
package — is answered OBSERVED REFUTED "importing the subject raised …", which is the right shape. So the honest answer
for the first three is REFUTED (or SUBJECT_ABSENT), not an environment failure; the fix is to build the stand-in
whenever the parent is not a *package* (`not hasattr(sys.modules.get(parent), "__path__")`), and to restore what was
there. *Validated on a scratch copy* (`fix-tree2/`, both HARNESS copies edited, the residual run through process_effect
only): `queue`, `types`, `hmac` → OBSERVED REFUTED, `json` unchanged, L0–L5 unchanged. Reach: a project directory named like `queue`, `types` or `hmac` that is not a regular package — rare, and
the same retry-until-budget outcome as PM-1.

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

**[verifier] The no-bump judgment rests on a scan of this repository only.** The scan (re-done: 41 `"step": "fault"`
occurrences in tracked files, none directly followed by `subprocess`; the one text hit is two adjacent scenarios of
`validation/qualification/c2_effect_calibration.py`) cannot see a bundle of a 2.0.0 user from PyPI, and the shipped
docstring *tells* an author that `subprocess` is faultable. With no bump such a spec keeps its capability digest and
turns INVALID_SPEC at admission — its approvals and plan ids unchanged, its run refused. That is the right outcome
for a spec that today passes vacuously, but it is the one case where "same capability digest, other meaning" happens,
so the owner should rule on it knowingly (the alternative, a bump of process_effect's capability, re-binds every
process_effect spec through `aisef bundle migrate`, ADR-2). The reviewer path is no way in either: a reviewer's
`[fault, subprocess]` reproducer would be SATISFIED → NOT_REPRODUCED, and a finding blocks only when ANCHORED to an
approved contract that expects it (`review_verify.py` module docstring), of which none exists. The T19b batch
(`test_v21_kills3_T19b.py` docstring) had already framed the same two ways, deliver or refuse; the first pass's
point stands that refusing is verdict-safe and delivering is a capability.

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
| Linux guest CPython 3.14.8 (8 MiB stack) | 43,497 (**[verifier]** 43,499 with a different driver script: the threshold moves by a few with the caller's stack depth) |
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
DEVELOPER, charged to the developer) would be a function of the host's stack, not of the revision. **[verifier] What
the first pass attributed to `cli_invocation`'s docstring is narrower and the argument needs two corrections.**
(a) That docstring (`cli_invocation.py:56-63`) says a verdict is "a function of the revision, the spec and the probe
identity, never of the platform the harness runs on", in the passage about newline handling; it is a stated principle,
not "the one thing" a verdict must never be. (b) `python_imports` is *already* interpreter-dependent by design and
documented so: it parses with "this interpreter's `ast`" and compares against that interpreter's
`sys.stdlib_module_names` (the facts carry `stdlib_of: python 3.x`), so a 3.14-only construct is REFUTED "unparsable" on
a 3.11 host (measured with the PEP 758 `except A, B:` form: parses on 3.14, not on 3.12). Host dependence alone is
therefore a weak reason. The reasons that carry the choice are the next two: the module docstring says an
unparsable file "leaves the count unestablished" — a *syntax* statement about the file, which a stack limit is not — and,
by the admission table (`plan/story_admission.py:classify`, `TABLE`: an INTRODUCE obligation expects UNSATISFIED at the
parent), a REFUTED answer for a file the host cannot parse would be accepted as the parent's evidence of absence (read,
not run), where UNRUNNABLE blocks admission; and at `review_verify` REFUTED is CONFIRMED (`review_verify.py:141-143`).
The `MemoryError` clause cannot be told from a real out-of-memory by type; scoped to the
one `ast.parse` call, the cost of that confusion is one UNRUNNABLE retry. **The cost of refusing is the one of PM-1:**
UNRUNNABLE is ENVIRONMENT and retryable, the developer is not charged and not told (detail dropped, PM-8), so a story
over a host-unparsable file retries until the budget ends — refusing replaces a loud failure with a silent one. If the
owner prefers REFUTED the two lines change place; say so.

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

**[verifier]** Re-run (`repro-5`, `repro-5b`: output identical to the first pass). Two corrections.

1. *This is already a recorded backlog row, and its text says the opposite of the measurement.* V21-26 (IR-B2, severity
   low, V2.1_BACKLOG) names exactly this mechanism and concludes "every answer describes behaviour the subject controls
   anyway (return, raise, exit), so no false PASS beyond the timing case fixed by B1-BLOCKS-STOP-001"; its reproducer
   column reads "not separately measured". The table above is that measurement: a `main()` that raises is SATISFIED
   for `exit_code: 0`. What the subject controls is what the *probe is told*, not what its code does when a user runs
   it (`python -m` would end in a traceback). The backlog's remedy ("docstrings to narrow") is right, its claim is not.
2. *The class is two things.* The limit — a same-user process cannot be made unable to lie about its own result
   without a redesign — is what charter §7 ("candidate code cannot manufacture … the authoritative channel", "do NOT
   require full hostile-host isolation") and D-04/D-05 leave out of 2.0: a KNOWN_LIMIT, and the owner's decision is only
   whether to commission option (b). The three sentences that say otherwise — `cli_invocation.py:72-73` ("cannot …
   build the facts the verdict is decided from"), `cli_invocation.py:118` and `process_effect.py:91` ("builds no fact" /
   "cannot … build a fact"), and the two `WEAKEST_PATH` constants — are a DEFECT of text: one edit, in the PM-1 window
   (their bytes are in the digests anyway), and no decision is needed to make a false sentence true. The first pass
   listed it only as an owner question.

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

**[verifier] Re-run (`repro-4`, `repro-4b`: identical). The classification is inconsistent with PM-3 and is changed.**
PM-3 is a DEFECT because "`Probe.evaluate` returns a typed result; an exception is outside the protocol"; the same
rule gives a DEFECT for the one site in this table that is reachable without a bug elsewhere: `open(harness.log)`
(`process_effect.py:883`, `cli_invocation.py:1013`) sits *above* the `try` that turns `OSError` into HARNESS_FAILED, so
a full disk or an exhausted descriptor table — the very faults `harness_preconditions` lists under "evaluation
directory: creatable" — leaves `observe` as a raw `OSError` where `_prepare`'s identical `OSError` is typed. It is
two lines, in the two files PM-1 already edits, so it costs no digest and no row beyond PM-1's. The NUL-in-argv case is
the same kind: a spec that can never run is admitted, then blamed on the environment; INVALID_SPEC at admission is the
protocol's own answer and is one line in `_subprocess_ok` (a plan-authoring error should not be retryable). What stays a
KNOWN_LIMIT is the non-`OSError` rows, which need a bug in the harness itself ([SIM] only) and which the run-level
containment bounds, and `on_range` raising after `start` (the acquirer releases). Neither `repro-4` nor `repro-4b`
exercises the descriptor-table case for real; it is [SIM].

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

**[verifier] This round makes the finding concrete, and one count is corrected.** (1) `v21r3/range` edits
`aisef2/runtime/process_range.py` — `ProcessRange.release()` becomes single-flight, a method every probe's `observe`
calls in its `finally` — and is merged on `v21r3/integ` (493ae64). Measured on that tree: `repro-9` finds a row for
19/19 classes at the bytes that run, i.e. the merge leaves every calibration row valid, exactly as R-3.1 says; `repro-7`
(the 19-class contrast loop, ≈25 s) on the same tree gives 19/19 contrast, 0 problems. So the evidence *is* good for
this edit — but nothing in the repository records it, and check 9 would have said "calibrated" if it were not. The
decision is therefore not hypothetical, and it must be taken **before** the one `release_calibration.py --write` of the
window: taken afterwards it costs a second recalibration and a second record. (2) *Four* probes import `ProcessRange`
(`process_effect.py:112`, `python_callable_v2.py:91`, `cli_invocation.py:143` and the frozen Cycle-1
`python_callable.py:77`); three can take the files into `PROBE_SOURCES`, the fourth is frozen by CYCLE2-FREEZE-MANIFEST
rule R2 — so option (a) leaves the superseded Cycle-1 probe outside, which is acceptable only because
`python_callable_v2` is the active identity for `python_callable`.

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
(`expired = time.monotonic() - started > window`, `file_artifact.py:539`) and then answers `SUBJECT_DEADLINE` with the
class's `ON_DEADLINE` verdict, REFUTED for every class (L100-101), *over facts that are complete*. The read is one git
process per file (`ObjectStore.blob` → `git cat-file blob`, L356) plus three for the entry and the tree, so its time is
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
probe — the kernel's (`file_artifact.py:238-258`, the match at L251, called from `facts_of`). `PATTERN_CAP` (512 characters) bounds the
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
rows concern the probe modules. Two are PM-8 (V21-04) and PM-5 (V21-26); the other eight are listed here and are
**not** in PM-1…PM-10. (V21-37, closed by `python_imports`, and V21-38, closed by ADR-4, are no longer probe-module
rows.) "Ran" = reproduced by the verifier through the real entry point; "read" = established from the code only.

| row | what the backlog says | status at BASE | evidence | class | cost if changed |
|---|---|---|---|---|---|
| V21-24 | a subject that truncates and rewrites the marker file turns its own observation into HARNESS_FAILED (ENVIRONMENT) instead of REFUTED | **open**; reproduced | **ran** (`rv-marker.py`, the test module's own `app.forge:rewrite`): `returns 1`, `returns 2`, `blocks` all HARNESS_FAILED — never SATISFIED; one detail reads "the harness did not start (exit 0, no READY): tool absent or broken", which misdescribes what happened | **KNOWN_LIMIT** (fail-closed; misattributes the owner; a channel the subject cannot hold is a catalog decision, per the row) | digests of the three marker-file probes |
| V21-25 | `blocks` is SATISFIED when the *import*, not the call, outlasts the window | **open**; reproduced | **ran** (`rv-backlog.py`): a module that sleeps at import → `blocks` SUBJECT_DEADLINE **SATISFIED** (the call was never made); the same module with a plain `serve()` → REFUTED | **KNOWN_LIMIT** today (documented window semantics, Cycle-1 class table); a **fault read as a verdict** of one class; the owner's call is whether to arm the deadline at the call | a class-table change: capability bump of `python_callable_v2` and `cli_invocation` `blocks` |
| V21-09 | UNRUNNABLE and INVALID_SPEC serialise alike in the sealed record | **open**; reproduced | **ran** (`rv-backlog.py`): `ProbeRecord.record_digest` is *equal* for `Unrunnable("x")` and `InvalidSpec("x")` while `result` differs | **KNOWN_LIMIT** (low; no verdict uses the digest to tell them apart) | `protocol.py` / `product/outcome.py`: frozen Cycle-1 identity — a re-freeze |
| V21-15 | candidate code can shift ownership away from DEVELOPER | **open**; the mechanism is measured twice | **ran**: V21-24 above and PM-5b (a malformed `agent_failure` → HARNESS_FAILED); PM-1 is the benign instance (a layout, not an attack, is charged to ENVIRONMENT). The row's "leak scan sees only verbatim JSON" part was **not** examined | **KNOWN_LIMIT** (low) | — |
| V21-07 | `file_artifact`'s FULL weakest path can be defeated by a same-user process | **open**; not reproducible here | **read**: the object store is immutable at a SHA; a *plain directory* (fixtures, direct callers) is read file by file, so a concurrent same-user writer is a race. Charter §2/D-05: a same-user adversary is a non-claim | **KNOWN_LIMIT** — the docstring's "Enforcement: FULL" should say "for the object store" | docstring: file_artifact's digest |
| V21-01 | `ProbeRecord.record_digest` binds no witness | **open** | **read** (`protocol.py`); charter D-08 defers it | **KNOWN_LIMIT** (deferred by the charter) | frozen identity |
| V21-32 | `cli_invocation._concluded`'s `harness_failure` branch is unreachable from today's controller | **open**; still so | **read**: `cli_invocation.HARNESS` never emits `harness_failure` facts; `process_effect._concluded`'s is reachable (a `Leak`); unit-tested | **KNOWN_LIMIT** (cosmetic: dead defensive code) | — |
| V21-33 | the AGENT shared with `python_callable_v2` answers ops this probe's controller never sends | **open**; still so | **read**: `invoke` and `bye` are the only ops the cli controller sends (`cli_invocation.py:753` and `:786`) | **KNOWN_LIMIT** (cosmetic; widens nothing: only the controller writes the agent's stdin) | AGENT bytes: all three digests |

Also documented as a non-claim, not a probe finding: `tests/v2/test_v21_identity.py` (module docstring) says test code
"runs as the operator's user and can still change that interpreter or the installed kernel (V2-05 is the sandbox)"; the
backlog row is V21-28 (`aisef2/app/run.py`, not this package).

## 3. What a probe-file change invalidates (measured, shared by PM-1…PM-4, PM-7, PM-11)

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
   **[verifier] Incomplete in one respect.** Those are the records that name a *probe* digest. A second set names the
   `aisef2/` *tree* and is staled by any product edit, probe or not: `git grep` of BASE's tree id
   (`b5563bd5969d4dff7685158a80311c023b031565`) finds `P5-FALSIFIABILITY.json`, `P5-PLAN-V2.2-PROPOSAL.json`,
   `PLAN-V2.2-CORRECTION-1.json`, `REQUALIFICATION-MANIFEST-4.json` (written once: a change of scope is revision 5) and the
   REFUSED C2-P5 re-verification. K-NOWORK-001, the Q5 kernel comparison and the conformance ruling are chained on those
   (they were regenerated in dependency order for 70ca84c; `git log 13513a1 70ca84c`). That cost belongs to the round's
   product changes as a whole — `usage`, `conf`, `detail` and `range` edit `aisef2/` too — so the *marginal* price of the
   probe window on top of them is the rows, the re-measure and the probe-bound records, which is what this section sizes;
   the *absolute* price of the round is paid once, after the last product edit.
4. **Mutation record.** `MUTATION.json` at BASE: `cli_invocation.py` 86 targets / 1,769 mutants, `process_effect.py`
   79 / 1,653, `file_artifact.py` 45 / 763, `python_callable_v2.py` 31 / 768 (importer of cli_invocation's script).
   A changed function has a new `source_sha256`, so its positional survivor audits are unmapped and must be remapped
   (`SURVIVOR-AUDITS.json`, entries keyed by target + index + description + source digest; 38 of the 213 are in
   these modules). At campaign 3's rate (7,867 mutants in 14.5 h on four workers) the upper bound is ≈ 8 h for a
   cli_invocation edit with its importers, ≈ 3 h for process_effect, ≈ 1.5 h for file_artifact alone — an estimate;
   the delta tool decides the real set.
   **[verifier]** Two precisions. The staleness test is by *whole file*: `validation/v2/mutation.py:_problems_v2` compares
   `source_digest(<the target's file>)` with the record's `source_sha256` (L1891), so one byte of `cli_invocation.py`
   stales all 86 of its targets, not the changed function's. And the three figures above do not add: "≈ 8 h with its
   importers" already contains process_effect's ≈ 3 h (it imports `cli_invocation`). The window PM-1 + PM-2 + PM-3 + PM-11
   changes three files — 1,769 + 1,653 + 763 = 4,185 mutants, ≈ 7.7 h, ≈ 9.1 h if `python_callable_v2`'s 768 are
   re-measured too (its own bytes are unchanged, so the freshness test would *not* ask for it; whether to run them is a
   decision). Target and mutant counts recounted from `closure-evidence/v2/v2.1/MUTATION.json`: 86/1,769, 79/1,653, 45/763, 31/768 — as stated.
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
   **[verifier] Re-run on two full checkouts** (`tests.base.txt`, `tests.fix.txt`: this branch, and a detached worktree
   of the same commit with the three sketches applied; unittest, one process per module, macOS 3.14.7): see §9.4. The
   result matches the paragraph above module for module.
7. **[verifier] Static rules.** `validation/v2/probe_static_checks.py --check` (the six Q0 probe rules, including
   `SINGLE_PLACEHOLDER_TOKEN` and `CLOSED_DISPATCH_IN_SCENARIO_PROBES`, which scan the HARNESS strings the PM-1 sketch
   edits): PASS (6 rules) on BASE and PASS on the three sketches applied. The first pass did not report this.
8. **[verifier] Sequencing with the rest of the round.** None of the other round-3 branches edits `aisef2/probe/`
   (`git diff --name-only 3dc827b v21r3/{conf,detail,range,usage,e2e}`); `range` edits `runtime/process_range.py`. The
   single `release_calibration.py --write` must come after the last edit of any `PROBE_SOURCES` file *and*, if PM-7 (a)
   is chosen, after `process_range.py` and `range_anchor.py` are final — writing it earlier and choosing (a) later costs
   a second recalibration and a second record.

## 4. Recommended order (one window, paid once)

1. PM-1, PM-2, PM-3 (+ PM-4's two lines) in one change set: three files, four short edits (diffs in `$OUT`), the
   `existing_tests_changed` of PM-2, new tests for each. **[verifier]** Add PM-11 (two tokens, same file as PM-3), PM-6's
   two lines (`open(harness.log)` under the `try`; NUL in argv refused at admission) and the corrected sentences of PM-5
   (three docstrings, two `WEAKEST_PATH` constants) — all in the same two or three files, all in the same digests.
2. If the owner picks PM-7 (a): the same window, and *before* step 3.
3. `release_calibration.py --write`, then the delta and the re-measure of the three changed modules and the importers of
   `cli_invocation.py`, then the records the lead regenerates.
4. PM-5 (a), PM-6, PM-10: text in REPORT now; in the modules on that window. **[verifier]** PM-12 and the backlog rows
   of §2.2 (V21-24, -25, -09, -15, -07, -01): one line each in REPORT's limits table.

Decisions only the owner can make: PM-5 (accept and state, or commission a design), PM-7 (scope of the identity), PM-9
(empty selection), PM-8 (already open), and one judgment inside PM-2 (no `CAPABILITY_VERSION` bump) plus the refuse-vs-
refute choice inside PM-3. **[verifier]** Also PM-13 and V21-25 — the complete list is §9.7.

## 5. Searched, and found not to be probe-module items

* `docs/v2.1/REPORT.md` §0.4; STATUS B-03; TRACEABILITY (R-3.1 and the "open" rows); memory
  `aisef-trang-thai-2026-10-08-b03.md`; `ROUND-2.md`; `SURVIVOR-AUDITS.json` (213 entries; 38 in `aisef2/probe/`, none OPEN);
  round-1 hand-overs `kills3/out/*/report.json` and their `review/report.json` (every `defects`, `issues`, `owner`
  note of A18, A19, A21, A27, T18a/b, T19a/b, T21a/b, T27a); the triage `triage/out/T*.json` (`unlisted_finding` of
  T18, T19, T21, T27); `kills3/ledger.json`, `unresolved.json`, `kills4/R2-UNRESOLVED.json`.
* Ledger by module for `aisef2/probe/`: cli_invocation 49 KILLED / 7 AUDITED / 2 EQUIVALENT; file_artifact 31 / 1 / 0;
  process_effect 53 / 2 / 16; python_callable_v2 66 / 9 / 1. **No OPEN and no DEFECT mutant** — every item above was
  found beside a batch, not as a survivor.
* **[verifier] Not searched by the first pass, searched by the verifier:** `docs/v2/V2.1-BACKLOG.md` (38 rows; the ten
  that name `aisef2/probe/` are PM-5/V21-26, PM-8/V21-04 and §2.2; V21-37 and V21-38 are closed in V2.1), the probe
  modules' own docstrings and `ponytail:`/limit markers (one: `file_artifact.py:377`, a per-entry `listdir` in the plain
  reader, "a fixture tree is small"), `tests/v2/test_v21_identity.py` and `…_identity_bytes.py` (no open item; the
  non-claim of the identity docstring is V21-28), the TRACEABILITY "open" rows (P-9.3 "structurally different correct
  implementations still pass" is the family PM-1 and PM-11 belong to; no row names either), `V2-RELEASE-FINDINGS.json`
  (`v2_1_backlog.ids` only: the rows are the markdown), the `kills3/out/*` reports a second time, the P5 mutant fixture
  `MUTANTS.json` M5-13-a ("`__init__.py` absent: the package becomes a namespace package" — a depth-1 namespace, which
  every probe observes correctly, L0).
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
* **[verifier]** Real runs by the verifier: every script of §9.1 on the hosts named there (guest: `repro-1`, `repro-2`,
  `rv-fa-bom.py`, a threshold driver); PM-11, PM-12, PM-13, V21-24, V21-25, V21-09 through the real entry points. Simulated by
  the verifier: nothing new (the hostile module of PM-5 and the [SIM] rows of PM-6 are the first pass's).
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
* **[verifier]** See §9.6. In particular: Windows and 3.11/3.13, the BOM's likelihood, the hour-scale ReDoS, and the full
  suite under the sketches.

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

**[verifier]** `$OUT_RV` = `scratchpad/m21/r3/out/probes-rv`; the first pass's scripts re-run there as `repro-*.py` with
`rv-repro-*.out`, `.py312.out`, `.guest.out`.

| script (sha256 prefix) | what | output |
|---|---|---|
| `rv-fa-bom.py` (8e74657a…) | PM-11, both readers, observe and run_probe, against CPython | stdout above; guest and 3.12 identical |
| `rv-fa-edge.py` (0db04f12…) | PM-11 and the pathological inputs of `import_facts` against `compile(bytes)` | 3.14.7, 3.12.14 |
| `rv-fa-bom-grep.py` (5ea499f6…) | PM-11, `grep_count` line 1 | — |
| `rv-fa-scale.py` (c05387df…) | PM-12, 50 and 400 files, two windows | — |
| `rv-fa-redos.py` (7639ea4a…) | PM-13, backtracking growth | — |
| `rv-backlog.py` (26458643…) | V21-25, V21-09 | — |
| `rv-marker.py` (93c4d9af…) | V21-24 through the test module's `app.forge:rewrite` | — |
| `rv-scan-fault.py` (d5660c1a…) | PM-2's scan: 41 fault steps in tracked files, none before `subprocess` | — |
| `rv-ns-stdlib.py` (c2e5111f…) | PM-1's residual: a nested namespace below an already-imported plain module, BASE and sketch | — |
| `runtests.sh` | §9.4: 17 modules on two checkouts | `tests.base.txt`, `tests.fix.txt` |

## 9. Verification (`v21r3/probes-rv`) **[verifier]**

Scope: an independent re-run of everything this document states as measured, a check of each classification against the
code and the consequence class ("can a fault be reported as a verdict?"), a search for open items the first pass did not
find, and a challenge of the recalibration cost. Everything was run through `py.sh probes-rv` from a checkout of this
branch (`$OUT_RV` = `scratchpad/m21/r3/out/probes-rv`; scripts and outputs kept there). Hosts: macOS arm64 CPython 3.14.7
and 3.12.14; the Linux guest (`guest.sh … X1`, CPython 3.14.8). The real `opencode` binary, the network and any provider
were not used.

### 9.1 Reproductions re-run

| item | script (sha256 prefix) | hosts | result against the first pass |
|---|---|---|---|
| PM-1 | `repro-1.py` (8a776cb4…) | 3.14.7, 3.12.14, guest 3.14.8 | identical: L1–L3 HARNESS_FAILED for process_effect and cli_invocation (6 per host), controls and python_callable_v2 OBSERVED SATISFIED |
| PM-1 | `repro-1b.py` (f2592a30…) | 3.14.7 | identical (N2 HARNESS_FAILED; N4 SUBJECT_ABSENT; N5 REFUTED; N6 SUBJECT_ABSENT) |
| PM-2 | `repro-2.py` (62f904f3…) | 3.14.7, 3.12.14, guest | identical: `fault → subprocess` SATISFIED, `fired: false`, for both products; the fragile CLI exits 1 with the fault inside the child |
| PM-3, PM-4 | `repro-3.py` (31e6f8a4…) | 3.14.7 | identical but for git object ids; `RecursionError` out of `observe` and `run_probe` on both readers; `pkg/deep.py:None` |
| PM-3 | `repro-3b.py` (3eebd806…) | 3.14.7, 3.12.14 | identical: 95,094 / 9,996; `MemoryError` 5,967; parentheses 201. Guest: 43,499 by a smaller driver (the first pass 43,497: the threshold moves with the caller's stack depth); the unmodified script produced no output in the guest — the likely cause is the container's 1 GiB limit on its 2 M-element flat-list case; not diagnosed |
| PM-5 | `repro-5.py`, `repro-5b.py` | 3.14.7 | identical: three forged SATISFIED over honest REFUTED; a malformed `agent_failure` is HARNESS_FAILED |
| PM-6 | `repro-4.py`, `repro-4b.py` | 3.14.7 | identical ([REAL] and [SIM] rows as labelled) |
| PM-7 | `repro-6.py` (0a495698…) | 3.14.7 | identical |
| PM-9, PM-10 | `repro-8.py` (087ffb68…) | 3.14.7 | identical |
| §3.1 | `repro-9.py`, `repro-7.py` | 3.14.7 | BASE 19/19 rows, 19/19 contrast; three sketches applied: 0/19 rows, 19/19 contrast, 0 problems (≈25 s) |

Not re-run: the `v2.0.0` and pre-B1 history of PM-1 (the first pass's `v200-tree`, `pre-b1-tree`); read, not run — the pre-B1
`cli_invocation` answered OBSERVED REFUTED for L1–L3 in `repro-1.pre-b1.out`, which is the only place in this document where
a layout was read as a refutation.

### 9.2 Classifications

| item | first pass | verifier | why |
|---|---|---|---|
| PM-1 | DEFECT | **DEFECT** (confirmed) | reproduced on three hosts; the fix, applied by `patch` to a scratch copy, makes L1–L3 SATISFIED and leaves the controls |
| PM-2 | DEFECT | **DEFECT** (confirmed) | reproduced; the no-bump judgment needs the caveat above (PyPI 2.0.0 bundles are unscanned) |
| PM-3 | DEFECT | **DEFECT** (confirmed); the *argument* for refusing is corrected | host dependence alone is weak (python_imports is interpreter-dependent by design); the admission table and the review gate are the real reasons; the silent-retry cost is stated |
| PM-4 | DEFECT (cosmetic) | **DEFECT** (cosmetic) (confirmed) | — |
| PM-5 | OWNER_DECISION | **OWNER_DECISION** for option (b); **KNOWN_LIMIT** for the limit; a **DEFECT of text** in three docstrings and two constants | V21-26 already records the mechanism and asserts "no false PASS"; measured otherwise |
| PM-6 | KNOWN_LIMIT | **DEFECT (low)** for `open(harness.log)` and NUL-in-argv admission; KNOWN_LIMIT for the rest | the same rule that makes PM-3 a DEFECT; no extra digest |
| PM-7 | OWNER_DECISION | **OWNER_DECISION** (confirmed), now with a live instance and a sequencing constraint | `v21r3/range` edits `process_range.py`; 19/19 rows stay "valid" |
| PM-8 | OWNER_DECISION (recorded) | **OWNER_DECISION** (confirmed; = V21-04) | — |
| PM-9 | OWNER_DECISION | **OWNER_DECISION** (confirmed) | reproduced |
| PM-10 | KNOWN_LIMIT | **KNOWN_LIMIT** (confirmed) | reproduced |

The *consequence* column was re-derived, not copied: PM-2 is the only first-pass item where a missing stimulus is
reported as a verdict (SATISFIED, fail-open); PM-1, PM-3, PM-6 produce no verdict (UNRUNNABLE or an exception —
fail-closed; at the review gate an UNRUNNABLE reproducer cannot block, by design). The verifier adds two that *do*
produce a verdict from a fault of the harness — **PM-11** (REFUTED over a file CPython runs) and **PM-12** (REFUTED over a
complete read) — and V21-25 (SATISFIED for `blocks` over a hanging import), which the backlog records and which is re-measured here.

### 9.3 The fix sketches, applied

`patch -p1` of the three first-pass diffs onto a copy of `aisef2/` (and, for the test runs, a detached worktree of the
same commit):

* `repro-1` on the patched copy: L0–L5 × {process_effect, cli_invocation, python_callable_v2} all OBSERVED SATISFIED;
  `EXECUTION_DIGEST`s `cli_invocation dcb9b7b1…`, `python_callable_v2 b0b716f9…` (as the first pass), `process_effect
  1bf8d960…` (with PM-2's one-line edit also applied; the first pass's `5a4a2d9c…` is PM-1 alone).
* `validation/v2/probe_static_checks.py --check`: PASS (6 rules) on BASE and on the patched copy.
* the 19-class contrast loop: 19/19 contrast, 0 problems; `repro-9`: 0/19 rows match, as the first pass found.
* the BOM change (PM-11, `fix-bom/`): `rv-fa-bom.py` and `rv-fa-edge.py` give the CPython-consistent answers; the
  `latin-1`-cookie row is unchanged.

### 9.4 Existing tests, base against patched (full checkouts)

Seventeen modules, one `unittest` process each (`tests.base.txt`, `tests.fix.txt`): the units and kill files of
process_effect (`test_probe_process_effect_units`, `test_probe_process_effect`), file_artifact (`test_c2_file_artifact`,
`test_v21_python_imports`), cli_invocation (`test_c2_cli_invocation`, `test_c2_cli_protocol`), python_callable_v2
(`test_python_callable_v2`), identity (`test_v21_identity`, `test_v21_identity_bytes`) and the B-03 kill files A19, A21,
T18a, T19a, T19b, T21a, T21b, T27a. Result: identical in 14 modules; **six tests, in three modules, red only on the patched tree**, exactly the ones
the first pass listed —

* `test_probe_process_effect_units::Vocabulary::test_the_scenario_rules`,
  `…::test_the_step_vocabulary_is_closed_and_each_kind_has_exactly_its_typed_fields` (PM-2's `FAULTED` pins, L104 and L180);
* `test_v21_kills3_T19b::FaultBeforeSubprocess::test_the_scenario_is_admitted_runs_and_is_observed`,
  `…::test_the_subprocess_step_exits_as_declared_through_the_guard` (PM-2);
* `test_v21_identity_bytes::ThreeIdentities::test_the_shipped_calibrations_name_every_class_at_the_bytes_that_run_now`,
  `…::test_calibrations_of_other_bytes_admit_nothing` (the calibration rows, until regenerated).

The A19/A21 namespace tests, T18a/T21a's `inside` tests and T27a's `startswith("x.py:")` pin pass under all three
sketches. The other 37 modules that import `aisef2.probe` and the full suite were not run.

### 9.5 What the verifier added

* PM-11, PM-12, PM-13 (above), each with a script and its output under `$OUT_RV`.
* §2.2: eight backlog rows — V21-24, V21-25 and V21-09 reproduced, V21-15's mechanism measured through V21-24 and PM-5b,
  four (V21-07, V21-01, V21-32, V21-33) read.
* Corrections in place: PM-3's argument; PM-5's source and class; PM-6's class; PM-7's count of `ProcessRange` importers
  and the live instance; PM-2's no-bump caveat; §3's records bound to the `aisef2/` tree, the whole-file staleness of the
  mutation record and the non-additive hours; §3.7 and §3.8.
* Two statements of the first pass that were checked and stand: "no layout was found in which the controller resolves a
  *different* module than the subject's own import" (the verifier added one layout class — below an already-imported
  plain module — and it is *not* a case of resolving a different module: it is HARNESS_FAILED where CPython also fails,
  see PM-1's residual), and "R-3.1's 'RunSpec does not change' holds only for the per-probe entries" (`repro-6`).

### 9.6 Not established by the verifier

* Windows, CPython 3.11 and 3.13: not measured. PM-12's Windows bound and PM-11's likelihood are expectations.
* `release_calibration.py --write`, the mutation re-measure, `kill_check` and the full suite were not run; the hours are
  arithmetic on `MUTATION.json` at campaign 3's rate.
* PM-13: the exponential growth is measured to 1.17 s; the hour-scale figure is extrapolated.
* V21-01, V21-07 and V21-15's "leak scan" part were read, not reproduced.
* The fix sketches were validated on scratch copies, not on the branch, and not with new tests.

### 9.7 Decisions only the owner can make (updated)

PM-5 (commission the exit-status redesign, or accept and state — the false sentences are corrected either way); PM-7
(scope of the identity, **before** the one recalibration); PM-9 (what a count over zero files means); PM-8 (already
open); **PM-13** (what bounds a spec's pattern); **V21-25** (arm `blocks` at the call or keep the documented window);
and three judgments inside the DEFECT fixes: PM-2's no-bump (and the 2.0.0 bundles it cannot see), PM-3's
refuse-or-refute (with the silent-retry cost stated), PM-11's no-bump.
