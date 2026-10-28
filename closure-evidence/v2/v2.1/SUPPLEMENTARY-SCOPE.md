# V2.1 — the single supplementary measurement scope (owner decision 2026-10-28, step 5)

**Merged measurement head:** `fce3d7b7` + the two kill-test edits (`tests/v2/test_v21_pm8_diagnostics.py`,
`tests/v2/test_v21_fa_grep_worker.py`, branch `v2.1/survivor-kills`). Product code is unchanged — only
the two test files gained a method each.

**This is one scope, measured once** (not "62 then more"): the union of the 62 MISSING and every target
whose kill-test closure now includes an edited test file.

## The scope

| group | targets | mutants (est.) |
|---|---:|---:|
| 62 MISSING | 62 | 2457 |
| closure-affected by the 2 edited tests | 36 | 1641 |
| **UNION (measure once)** | **90** | **3587** |

### Union breakdown with grounds

| sub-group | targets | mutants | why it must be measured |
|---|---:|---:|---|
| MISSING only | 54 | 1946 | reuse-proof fails at head (46 kill-test closure changed; 16 product module changed) and not in the mw0/mw1 199-slice |
| MISSING **and** test-affected | 8 | 511 | both reasons; counted once |
| test-affected only | 28 | 1130 | kill-test closure now includes an edited file |
| &nbsp;&nbsp;— previously reuse | 10 | 436 | was reusable; the edited kill-test file changes its closure |
| &nbsp;&nbsp;— previously measured-at-head (of the 180) | 18 | 694 | mw0/mw1 measured these at `fce3d7b7`; editing the kill-test makes that measurement stale |

The 18 previously-at-head targets are the unavoidable cost of editing a kill-test: their fresh
measurement no longer matches the merged head. After this scope, 180 − 18 = **162** of the mw0/mw1
at-head results stay valid and are reused; the 90 are re-measured.

Edited-file reach: `test_v21_pm8_diagnostics.py` is in the closure of **26** targets,
`test_v21_fa_grep_worker.py` of **10** (8 overlap the 62 MISSING).

### Largest targets in scope (mutants)

| mutants | target | in scope because |
|---:|---|---|
| 366 | `aisef2/app/run.py::execute` | MISSING + test-affected |
| 324 | `aisef2/orchestrate/story_runner.py::_attempt` | MISSING |
| 303 | `aisef2/app/adapters.py::Reviewer._ocr` | MISSING |
| 211 | `aisef2/app/verify.py::verify` | test-affected |
| 143 | `aisef2/app/cli.py::run` | MISSING |
| 138 | `aisef2/probe/file_artifact.py::FileArtifactProbe.observe` | test-affected |
| 128 | `aisef2/app/client.py::session` | MISSING |
| 123 | `aisef2/app/diagnostics.py::artifact_problems` | test-affected |
| 114 | `aisef2/app/bundle.py::shape_problems` | MISSING |
| 103 | `aisef2/app/diagnostics.py::Sink._document` | test-affected |

## Duration estimate — **multi-day**

Measured throughput, 2 workers, **mutation-compute wall time only** (excludes survivor audit + the
suites), 3587 mutants:

| rate | wall time | days |
|---|---:|---:|
| fast mix ~88 mut/h | 41 h | **1.7** |
| giant-heavy ~63 mut/h | 57 h | **2.4** |
| worst giants ~40 mut/h | 90 h | **3.7** |

Giant-heavy (`run.execute` 366, `_attempt` 324, `_ocr` 303) dominates, so the middle-to-high end is
likelier: **plan for ~2.5–3.5 days of mutation compute at 2 workers**, plus survivor audit and the
macOS/Linux suites afterward (not in the above).

## Gating notes (before launch)

- `_create` and `_parser` are inside this scope (both MISSING). Their kill sets include
  `test_v21_continue_integrity.py`, whose T0 soundness is the **open `continue_integrity` finding**
  ([OLD-BLOCKERS-RECONCILIATION.md](OLD-BLOCKERS-RECONCILIATION.md)). Measuring them produces a result
  but does **not** retire that finding; it stays an explicit blocker. ~97 targets use that kill-test.
- Mandatory checks: `ruff` is green on both edits; both edited test files pass in full (108 tests +
  230 subtests). The **whole-repo gate/suite on the merged branch has not been run yet** — I propose to
  run it as launch prep *after* approval, not now, since the scope numbers are structural and would not
  change with suite results, and a 33-min suite run shouldn't precede the go/no-go on a multi-day campaign.
- Isolation unchanged: 2 workers, PATH with no real `opencode`, scratch XDG, disk watchdog, per-target
  record writes. No push / tag / publish / paid-provider / self-acceptance.

## Decision needed (time cost)

This is a multi-day campaign (~2.5–3.5 days mutation compute at 2 workers, giant-heavy). Per the
directive I am **stopping here for the owner to decide the time cost** before launch. Options the owner
may choose: approve 2 workers as-is; free host disk to allow more workers (faster); or defer.
