# Amendment A2 — placement of new v2.3 tests, code, design text and evidence (decided by the integrator, 2026-11-21)

*A new file under the freeze rule of W1-DESIGN.md (line 3: a change is an appended, dated amendment, never an edit).
This file records the rationale and the measured proof; it changes no rule of §2.9 and adds no exception.*

## Rule

| What | Where |
|---|---|
| New test modules | `tests/v23/` — a package whose `__init__.py` is an empty, 0-byte file (identical in every track) |
| New code | `validation/v23/` |
| New design text | a new file `docs/v2.3/amendments/<ID>.md` (never appended to W1-DESIGN.md) |
| New evidence | a new file under `docs/v2.3/evidence/<topic>/` — never under `closure-evidence/v2.3/` (tests/v2/test_v1_evidence_guard.py protects every tracked file under `closure-evidence/` except `closure-evidence/v2/`) and never under `closure-evidence/v2/` (a COPY root: a new file there is in Δ) |

An existing test or code file is edited only where W1-DESIGN §8 / DEPENDENCY-DAG §4 assigns it to the lane.
`tests/v2/test_v23_impact.py` moved to `tests/v23/test_v23_impact.py` (`git mv`, commit `164081cf`); it needed no
path change (it finds the repository root with `parents[2]` at either depth).

## Why (the mechanism, from the code)

1. **Every kill file's S(F) holds every `tests/v2` file.** `tests/v2/__init__.py:4` imports
   `aisef2.invariants.registry` (to `arm` the tier), so registry.py is in the s2 closure of every kill file under
   `tests/v2`. `registry.py:40` binds `TESTS_V2 = "tests/v2"`, and `test_directories()` (`registry.py:244-250`)
   enumerates `root / TESTS_V2` with `glob`/`rglob` at run time. A string constant of two or more path components that
   names a directory adds every file under it to S(F) (§2.9 D2 (b), `impact._Ctx._literal`).
2. **So any new `tests/v2` file re-opens every target under the frozen R6.** With Amendment A1 withdrawn, R6 judges
   Δ ∩ S(F); a new `.py` file has module status "new". Disposition 2 shows the cost: 667 / 667 targets that pass I6
   were INVALIDATED (R6), all because of the impact tests' own new file at `tests/v2/test_v23_impact.py`.
3. **`tests/v23` is outside every `mutation.COPY` root.** COPY (`validation/v2/mutation.py:1543-1547`) has `tests/v2`
   as a root, not `tests/`. A path outside COPY is never in D1's Δ (`impact._Ctx._delta` diffs only COPY roots) and is
   never copied into a runner tree (`mutation._pristine`), so no kill-file run can import, list or read it. The D2 (d)
   discovery set is taken under `dirname(F)` (`impact._Ctx._discovery`: `p.startswith(d + "/")`), and
   `"tests/v23/…"` does not start with `"tests/v2/"`.

This is structural decoupling: the tests of the engine and the recorder are not inputs of any kill file. It is not an
exception, an allowlist or a narrowing of any rule: a new or changed `tests/v2` file still re-opens every target that
passes I6, exactly as the frozen R6 says, and §2.8 still governs edits of existing test files.

## Measured proof (the engine's own S(F), W1-DESIGN §2.9 D2, at base ∪ head)

Computed with `validation/v23/impact.py` `_Ctx.S(F)` for every distinct kill file of `mutation.TARGETS` at head, with
basis `da3ea33f3b695aaca73e87a704145a0193aced23` (v2.2.0). Record:
[`docs/v2.3/evidence/f5-observe/A2-SF-TESTS-V23.json`](../evidence/f5-observe/A2-SF-TESTS-V23.json).

| Head | Probe | Kill files whose S(F) holds it | Δ paths that match |
|---|---|--:|---|
| `164081cf` (the move: tests at `tests/v23/`) | any `tests/v23/**` path | **0 / 262** | none |
| `75080a80` (recorder, engine and `tests/v23/test_v23_observe.py`, `tests/v23/fixtures/` added) | any `tests/v23/**` path | **0 / 262** | none |
| `1e25ef84` (before: tests at `tests/v2/test_v23_impact.py`) | `tests/v2/test_v23_impact.py` | **262 / 262** | `tests/v2/test_v23_impact.py` (A) |

No kill file's S(F) contains any `tests/v23/**` path; none is hidden. The lane's later commits add or change only
files outside every COPY root that no kill file imports (`validation/v23/observe.py`, `tests/v23/**`, docs, evidence).

## What this does not claim

* It does not make any target reusable: without observations every target with Δ ≠ ∅ still stops at R1 (or earlier).
* If a kill file ever imported a `tests/v23` module or named `tests/v23` by a literal, that file would join S(F)
  through the s2 closure; it would still not be in Δ nor in the runner's tree, and the run would fail in the runner
  (the module is not there). The decoupling holds as long as `tests/v23` stays outside COPY (W1-DESIGN §8 adds
  `validation/v23`, not `tests/v23`, for new runs).

## Correction (2026-11-22)

The evidence row is corrected as above (the integrator's corrected A2). The three records this lane had written under `closure-evidence/v2.3/f5-observe/` were moved with `git mv` to `docs/v2.3/evidence/f5-observe/` (bytes unchanged); every reference was updated.
