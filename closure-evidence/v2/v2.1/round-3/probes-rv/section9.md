
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
| PM-3 | `repro-3b.py` (3eebd806…) | 3.14.7, 3.12.14 | identical: 95,094 / 9,996; `MemoryError` 5,967; parentheses 201. Guest: 43,499 by a smaller driver (the first pass 43,497: the threshold moves with the caller's stack depth); the unmodified script was killed silently by the guest's 1 GiB limit (flat list of 2 M elements) |
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
complete read) — and V21-25 (SATISFIED for `blocks` over a hanging import), which was recorded and not measured.

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
T18a, T19a, T19b, T21a, T21b, T27a. Result: identical in 11; **six tests red only on the patched tree**, exactly the ones
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
* §2.2: eight backlog rows, two of them (V21-24, V21-25) and V21-09 reproduced, five read.
* Corrections in place: PM-3's argument; PM-5's source and class; PM-6's class; PM-7's count of `ProcessRange` importers
  and the live instance; PM-2's no-bump caveat; §3's records bound to the `aisef2/` tree, the whole-file staleness of the
  mutation record and the non-additive hours; §3.7 and §3.8.
* Two statements of the first pass that were checked and stand: "no layout was found in which the controller resolves a
  *different* module than the subject's own import" (I tried the same set plus a namespace under an already-imported
  stdlib name, which fails the same way in CPython and the probe), and "R-3.1's 'RunSpec does not change' holds only for
  the per-probe entries" (`repro-6`).

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
