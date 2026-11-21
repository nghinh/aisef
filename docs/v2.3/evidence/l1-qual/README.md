# L1-QUAL — release qualification records bound by identity (W1, lane L1-QUAL)

Design: `docs/v2.3/W1-DESIGN.md` §3, §7 (#17), §8, §9 (N11, N12, N34); `docs/v2.3/CODE-AUDIT.md` #3, #17, #40, #104;
`docs/v2.3/DEPENDENCY-DAG.md` §4 (L1-QUAL). Placement corrected by Amendment A2: tests in `tests/v23/`, evidence here.
Base: `v23/lanes` at `1c457c0b` (L1-BUILD, L1-F2, L1-TESTENV, L1-CIGOV committed). Host of the local measurements:
Darwin 25.5.0 arm64, CPython 3.14.7, git 2.53.0. Every run used the mutation-worker env guard (no `opencode` on
`PATH`, XDG data/state/cache in scratch). No network, no paid call. Raw traces stay in scratch and are named here by
the first 16 hex digits of their sha256.

**Red-before runs** were made in a scratch copy of the tree (an APFS clone, its own `--shared` git clone at the same
HEAD, the base versions of the five modules restored). **Nothing below was measured on GitHub CI** (DISC-1).

## Items

| Item | Change | Tests | Red-before (measured) | After |
|---|---|---|---|---|
| EVID-COUPLING-01 / #3 (N11, N12, N34) | `release_calibration.resolve()` → `(record, state, basis)`; `RECORD_REL, STATE, BASIS = resolve()`. The newest record of the nearest version ≤ pyproject's is cited only with all inputs equal now: its rows = the shipped `calibrations.py` rows = the rows derived from the catalog (executing digests, classes, fixture paths), and each row's fixture trees = the record's sha256. Legacy record: byte-identical to its blob at `da3ea33f` (v2.2.0) → `VERIFIED_REUSE`, basis `identical-inputs:V<ver>`. A record written by the v2.3 writer, committed once at HEAD, from a clean tree → `MEASURED`. Anything else INVALIDATED / UNRESOLVED (never raises). `--write` writes nothing while current; otherwise re-demonstrates every class, appends a v2.3 record (`open "x"`) and rewrites `calibrations.py` only when its rows change. `--state` (0.2 s) prints the state. Consumers add `rc.state_problems()`: `p5_acceptance.reverify`, `v21_conformance_ruling.derive`, `q2` (release mode; an INVALIDATED record supplies no key). Their call sites still read `rc.RECORD_REL`. | `tests/v23/test_v23_version_bump.py` `Bump` (6), `tests/v23/test_v23_calibration_rows.py` `Resolve` (5), `Write` (2) | Base code, pyproject `2.3.0.dev0` (scratch copy): the 3 M5 unit tests fail (`V21Records` ×2, `test_qualification_release_mode::Subject.test_release_q2_reads_the_calibrations_the_rc_ships`), plus the GATED `Acceptance.test_the_acceptance_re_derives_on_this_tree` and `CommittedRuling.test_the_committed_ruling_is_what_this_tree_derives`; `p5_acceptance.py --check-v22` and `v21_conformance_ruling.py --check-v22` FAIL (`e2682646…`, `3539268b…`, `31a89a3f…`). On the base code, 22 of the 23 new tests fail or error. The one that passes is the both-records-present regression check (`013b49d6…`, `28130299…`, `eb4af85d…`) | New code, same bump (scratch copy): `--state` VERIFIED_REUSE `identical-inputs:V2.2.0`; `--write` "nothing written"; both `--check-v22` PASS; the three modules pass with and without `AISEF_SEALING=1`; `calibrations.py` sha256 `14285dcf…` before and after; `git status` shows no new record (`1237ffb9…`). Plus one negative fixture byte: `--state` INVALIDATED naming `probe.file_artifact exists` only; both `--check-v22` FAIL with that line; the 3 M5 tests fail; `calibrations.py` unchanged (`43ab717b…`, `46861812…`, `f2e6b62c…`) |
| #104 (a) | `release_calibration.shipped_rows()` (parsed from the file) and `derived_rows()` (catalog) | `ShippedRows` (2) | An extra hand-added row passes `test_v21_identity_bytes` (one direction); measured inside the test | The two-way check fails on that row, and `resolve()` gives INVALIDATED for it; 19 = 19 rows on this tree |
| #104 (b) | `resolve()` binds every row to its fixture-tree sha256 (no CI step needed for the binding) | `Resolve.test_one_negative_fixture_byte_invalidates_that_row_only…`, `…a_record_or_calibrations_py_changed…` (a tamper that makes the record agree with a changed fixture is refused by the v2.2.0 bytes) | — (no binding existed: rows carried no fixture digest) | One negative fixture byte → exactly that row INVALIDATED, `calibrations.py` byte-unchanged |
| #40 | `reverify()` returns PROBLEMS naming a missing 2.0 record (`<rel> is missing` + `history_problems()` + `proposal_history_problems()`) before any dereference | `MissingRecord` (2) | Base code: `TypeError: 'NoneType' object is not subscriptable` at `:804` (proposal) and `:851` (acceptance), both rounds; in-process removal and a real removal in the scratch copy (`013b49d6…`, `9d4286fa…`) | Both rounds, both records: verdict PROBLEMS, no traceback; with both records present the full body is derived and every committed-record check gives the same output as before (below) |
| #17 | `c2_closure_audit.py`: `freeze_states()` (each frozen row VERIFIED_REUSE / INVALIDATED, re-derived), `cite()` (refuses a non-current row), `--erratum` (writes once) and `--states`; `check()` accepts the C2-FINAL mismatch only while the erratum is exactly what the tree derives. Erratum: `docs/v2.3/evidence/l1-qual/C2-FINAL-FREEZE-ERRATUM.json` | `tests/v23/test_v23_c2_freeze_erratum.py` (6) | `--check` → `C2-FINAL: the first 43 entries are not the frozen ones`, exit 1 (base, `5c96b06a…`) | `--check` passes; C2-FINAL stays INVALIDATED, the other 12 rows VERIFIED_REUSE; `cite("C2-FINAL")` raises; an erratum claiming reuse, another freeze file, another history or other timing is refused and the row is reported again. `C2-HISTORY-FREEZE-CANDIDATE.json` and the history are unchanged (committed once) |

## What the erratum binds (measured, re-derived by `check()`)

* Freeze file sha256 `397cf619…`, written `2026-10-01T11:07:24Z`, `head_when_written` `3ed2c411…`. Its C2-FINAL row:
  `entry_count` 43, digest `7bbee75a…`, `file_sha256_when_written` `e16319c6…`.
* `C2-FINAL-RUN-HISTORY.json` now: 35 entries, sha256 `c765cdc1…`. Its committed versions on HEAD's history hold
  13, 24, 27 and 35 entries; the maximum is 35. The version at `head_when_written` holds 35. That commit is dated
  `2026-10-01T09:33:07Z`, before the freeze was written. `e16319c6…` is not the sha256 of any committed version.
* **Correction to CODE-AUDIT #17's wording:** it says the history "held 27 entries at write time". 27 is the count at
  `2dd12265` (REPORT_HEAD). At `head_when_written` the committed history already held 35. The conclusion does not
  change: 43 was never committed.

## Unchanged outputs (base copy vs this tree, paths normalised)

`p5_acceptance.py --check-v22` PASS and `v21_conformance_ruling.py --check-v22` PASS. `p5_acceptance.py --check-v21`
and `v21_conformance_ruling.py --check` FAIL; they did so on the base, with byte-identical output (v2.1 round
history). `release_calibration.py --check` PASS (33 s). These unit modules pass on both, with and without
`AISEF_SEALING=1`: `test_c2_p5_acceptance` 30, `test_qualification_release_mode` 11, `test_v21_conformance_ruling` 13,
`test_v21_identity_bytes` 4, `test_p5_plan_v22_proposal` 10, `test_c2_orchestration_conformance` 24,
`test_p5_falsifiability` 11 and `test_app_run` 17 (base `5c96b06a…` + `20e49d4b…`, after `26f49194…`).
`tests/test_meta.py`, `tests/v2/test_sealing_gate.py` and `tests/v2/test_v1_evidence_guard.py` pass.

## F5 / Q0 / sealing impact

* None of the touched paths is under a mutation COPY root, a target or a kill file. They are
  `validation/qualification/{release_calibration,p5_acceptance,q2,v21_conformance_ruling,c2_closure_audit}.py`,
  `tests/v23/*` and `docs/v2.3/evidence/l1-qual/*`. Under tier C they re-open **0** targets.
* The Q0 checkers (`validation/v2/checker_calibration.py` and what it loads) import none of these modules, so the Q0
  record does not move. `currency_dag.py` names p5/conformance only as text.
* The GATED tests that read these modules (`Acceptance.test_the_acceptance_re_derives_on_this_tree`,
  `KernelProvenance.test_on_this_tree_the_committed_proposal_is_current`,
  `CommittedRuling.test_the_committed_ruling_is_what_this_tree_derives`, the two `test_c2_orchestration_conformance`
  `Record` tests) give the same verdict before and after (PASS with `AISEF_SEALING=1`). The committed v2.2 records
  re-derive byte-for-byte, because the cited record path is still `V2.2.0-PROBE-CALIBRATIONS.json`.
* No existing test file was edited.

## Declared limits and simplifications

* The demonstration procedure is not an impact input. `aisef2/probe/calibration.py` and this generator can change
  without invalidating the record. A record proves contrast for the probe bytes (executing digest) and the fixture
  trees it names. The v2.2 rule bound neither.
* A legacy record is anchored to git history. It proves the bytes v2.2.0 committed, not who calibrated. A v2.3 record
  is anchored to HEAD and to "committed once".
* Versions are compared as `N.N.N[.devN]`. Any other version string (e.g. `rc1`) is UNRESOLVED.
* `--write` re-demonstrates every class (about 30 s), not only the changed rows. Per-row reuse was skipped; add it if
  the write cost matters.
* The in-suite N11/N12 tests patch the import-time constants to what `resolve()` gives. A subprocess test pins the
  real import-time binding under a version bump. The full bump with a real `pyproject.toml` edit was measured once, in
  the scratch copy (above).

## Not done here (with the reason)

* **CI step for `release_calibration.py --check` / `--state` (W1-DESIGN §7 gap-fill, L1-QUAL + L1-CIGOV).** The
  workflow files are L1-CIGOV's. #104 (b) is met through the binding instead. A one-line `tests.yml` step
  (`python -P validation/qualification/release_calibration.py --state`, 0.2 s) is left to L1-CIGOV / the integrator.
* **The W1 exit gate (§11 gate 4) on CI.** It has not run on GitHub (DISC-1).
* **Checklist ticks** (`MASTER-CHECKLIST.md` EVID-COUPLING-01 row, CODE-AUDIT rows). Those files are outside this
  lane; the integrator ticks them.
