"""Two-tier F5 CI gate (owner ruling 2026-11-22 §4) — a thin wrapper over validation/v23/impact.py.

    python3 -P validation/v23/ci_gate.py --tier develop|rc

The ruling's two policies, implemented as two tiers over ONE engine run (the engine is imported, never re-implemented
and never edited — its verdicts are the only classification authority here):

* `--tier develop` (every release/** push and PR): executes the F5 engine and the pinned negative controls, prints the
  full truthful state table (every MEASURED / VERIFIED_REUSE / INVALIDATED / UNRESOLVED count and the per-rule
  breakdown, exactly what `impact.py --classify` prints), and exits 0 with the mandatory final line
  `EVIDENCE: INCOMPLETE (NOT QUALIFIED)` while any target lacks MEASURED or VERIFIED_REUSE evidence. Incomplete
  evidence is reported, never relabelled: the only other final line is `EVIDENCE: COMPLETE (RC-TIER CHECK STILL
  REQUIRED)`. The develop tier exits non-zero only on the ruling's three failure conditions, each named on stdout:
  (a) checker malfunction — the engine raises, a row carries the `engine` component (an exception the engine caught),
      the table is malformed, the per-state counts do not match the rows, or the table does not cover the registry
      (every RECORDS x PHASE_TARGETS target of the checked-out harness; a table that cannot be read fails closed);
  (b) false-current reuse — a VERIFIED_REUSE row with no acceptance basis; a non-reuse (INVALIDATED / UNRESOLVED) row
      carrying one (F5-DISPOSITION-3: "No non-reuse row carries an acceptance basis"); or a VERIFIED_REUSE basis that
      is not one the engine itself pins to THIS run's resolved basis commit — `v2.2.0-accepted@<base>` only when the
      base is the pinned full v2.2.0 sha (impact.BASE), `calibration@<base>` otherwise, the sha-pinned Option C ruling
      forms, or `observation:<sha256>@<base>` carrying impact.OBSERVATION_AUTHORITY (owner ruling 2026-11-21: the
      recorder is not a VERIFIED_REUSE authority). All forms are derived from impact.py's own constants and report();
      no reuse rule is re-derived here;
  (c) negative-control regression — see the controls below.
* `--tier rc` (frozen RC and production qualification: tags, or a manual dispatch with tier=rc): everything the
  develop tier does, PLUS exit non-zero naming the count whenever ANY target lacks valid MEASURED or VERIFIED_REUSE
  evidence. Neither tier takes an exception list, a skip parameter or any other way to mask a qualification failure.

Negative controls (both tiers, in-process, before the engine run — ~11 s locally for all four): the pinned CONTROLS
below are real F5 negative tests from tests/v23/test_v23_impact.py, each building its own toy repository (so they run
on any checkout, dirty or clean) and each asserting the engine REFUSES bad evidence:

* test_r0_every_inadmissible_observation — an inadmissible observation (wrong outcome, missing witness, wrong tree,
  wrong platform/python, a read outside the run's tree) is refused (R0, UNRESOLVED);
* test_r1_incomplete_observations — an incomplete observation (lost events, unparsed lines, an unhooked word in S(F))
  is refused (R1, INVALIDATED);
* test_new_test_file_named_by_a_directory_constant — a Δ ∩ S(F) hit by a literal directory constant INVALIDATES
  (R2, static tier);
* test_n32_dirty_tree — the engine refuses a dirty working tree (every target UNRESOLVED, never a clean verdict).

A control that fails, errors, is skipped, or CANNOT EVEN BE LOADED is a gate failure: a gate that cannot demonstrate
its checker still refuses bad evidence proves nothing about the evidence it accepts, so the absence of controls is
itself a checker malfunction and the gate fails closed.

Exit codes: 0 pass; 1 rc-tier incompleteness; 2 a §4 failure condition (either tier).
Policy record: docs/v2.3/amendments/CI-TWO-TIER.md (supersedes W1-DESIGN §11 exit gate 2's always-fail for
DEVELOPMENT pushes; the rc tier keeps it). Read-only: this tool writes nothing.
"""

from __future__ import annotations

import argparse
import collections
import io
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v23 import impact  # noqa: E402  (classify/report: the only classification authority)

#: the pinned negative-control set (see the module docstring for what each one proves)
CONTROLS = (
    "tests.v23.test_v23_impact.ImpactTest.test_r0_every_inadmissible_observation",
    "tests.v23.test_v23_impact.ImpactTest.test_r1_incomplete_observations",
    "tests.v23.test_v23_impact.ImpactTest.test_new_test_file_named_by_a_directory_constant",
    "tests.v23.test_v23_impact.ImpactTest.test_n32_dirty_tree",
)
#: a reuse's evidence states; everything else lacks valid MEASURED or VERIFIED_REUSE evidence
COMPLETE = ("MEASURED", "VERIFIED_REUSE")
_OBS_BASIS = re.compile(r"observation:[0-9a-f]{64}@([0-9a-f]{40})\Z")


def _registry() -> frozenset[str]:
    """Every RECORDS x PHASE_TARGETS target of the checked-out harness (in CI the checkout IS head)."""
    from validation.v2 import mutation as m
    return frozenset(t for phase in m.RECORDS for t in (m.PHASE_TARGETS.get(phase) or ()))


def run_controls() -> list[str]:
    """[] when every pinned control loads, runs and passes; otherwise why not (fail closed: a control that cannot be
    loaded or does not run is a gate failure, not a pass)."""
    loader, suite = unittest.TestLoader(), unittest.TestSuite()
    for name in CONTROLS:
        try:
            suite.addTests(loader.loadTestsFromName(name))
        except Exception as e:  # noqa: BLE001 — fail closed, whatever the loader raised
            return [f"control {name} cannot be loaded ({type(e).__name__}: {e})"]
    if suite.countTestCases() != len(CONTROLS):
        return [f"{suite.countTestCases()} of {len(CONTROLS)} controls loaded: a missing control is a gate failure"]
    buf = io.StringIO()
    res = unittest.TextTestRunner(stream=buf, verbosity=1).run(suite)
    if res.testsRun != len(CONTROLS) or res.skipped or not res.wasSuccessful():
        return [f"ran {res.testsRun}/{len(CONTROLS)} controls, {len(res.failures)} failures, {len(res.errors)} errors, "
                f"{len(res.skipped)} skipped:\n{buf.getvalue()}"]
    return []


def table_problems(doc: dict, registry: frozenset[str]) -> list[str]:
    """(a) checker malfunction: why `doc` is not a well-formed, registry-covering state table, or []."""
    out: list[str] = []
    states = doc["states"]
    if not isinstance(states, list) or not states:
        return ["the state table is empty: the engine classified nothing"]
    rows: collections.Counter = collections.Counter()
    for s in states:
        if s.get("state") not in impact.STATES:
            out.append(f"{s.get('target')}: unknown state {s.get('state')!r}")
        if s.get("component") == "engine":
            out.append(f"{s.get('target')}: the engine raised ({s.get('reason')})")
        rows[s.get("state")] += 1
    for st in impact.STATES:
        n = (doc["counts"].get(st) or {}).get("n")
        if n != rows.get(st, 0):
            out.append(f"counts[{st}] says {n}, the table holds {rows.get(st, 0)} such rows")
    total = sum((c or {}).get("n", 0) for c in doc["counts"].values())
    if total != len(states):
        out.append(f"counts sum to {total}, the table holds {len(states)} rows")
    missing = sorted(registry - {s.get("target") for s in states})
    if missing:
        out.append(f"{len(missing)} registry targets missing from the table (first: {missing[0]})")
    return out


def reuse_problems(doc: dict) -> list[str]:
    """(b) false-current reuse: every basis violation, derived from impact.py's own constants and report(), or []."""
    base_sha = (doc.get("base") or {}).get("sha") or ""
    ruling = f"ruling:{impact.RULING_ID}@{impact.RULING_SHA256}"
    pinned = ({f"v2.2.0-accepted@{base_sha}", ruling} if base_sha == impact.BASE
              else {f"calibration@{base_sha}", f"calibration@{base_sha}+{ruling}"} if base_sha else set())
    out: list[str] = []
    for s in doc["states"]:
        target, state, basis = s.get("target"), s.get("state"), s.get("basis") or ""
        if state == "VERIFIED_REUSE":
            m = _OBS_BASIS.fullmatch(basis)
            if not basis:
                out.append(f"{target}: VERIFIED_REUSE with no acceptance basis")
            elif m is not None:
                if m.group(1) != base_sha or (s.get("evidence") or {}).get("authority") != impact.OBSERVATION_AUTHORITY:
                    out.append(f"{target}: an observation basis not pinned to this run's basis commit with "
                               f"evidence.authority 'none' (owner ruling 2026-11-21): {basis!r}")
            elif basis not in pinned:
                out.append(f"{target}: basis {basis!r} is not a basis the engine pins to this run's resolved basis "
                           f"commit {base_sha or '<none resolved>'}")
        elif state in ("INVALIDATED", "UNRESOLVED") and basis:
            out.append(f"{target}: a non-reuse row carries an acceptance basis {basis!r} (F5-DISPOSITION-3)")
    return out


def _print_table(doc: dict) -> None:
    """The same table `impact.py --classify` prints: counts, the per-rule breakdown, the platform split."""
    print(f"F5 impact  base {doc['base']['sha']}  head {doc['head']['sha']}  run: {doc['run']}")
    for s, c in doc["counts"].items():
        print(f"  {s:<15} {c['n']:>5} targets {c['mutants']:>7} mutants")
    for k, c in doc["by_component"].items():
        print(f"    {k:<26} {c['n']:>5} {c['mutants']:>7}")
    for k, n in doc["platform"].items():
        print(f"  platform {k:<22} {n:>5}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--tier", choices=("develop", "rc"), required=True,
                    help="develop: truthful report, fail only on §4 (a)-(c); rc: additionally fail on any incomplete target")
    a = ap.parse_args(argv)
    controls = run_controls()
    for p in controls:
        print(f"CI-GATE FAIL (negative-control regression): {p}")
    if controls:
        return 2
    try:
        doc = impact.report(impact.classify(impact.ROOT, impact.BASE, "HEAD"))
        _print_table(doc)
        bad = table_problems(doc, _registry())
        reuse = [] if bad else reuse_problems(doc)
        incomplete = [] if bad else [s for s in doc["states"] if s.get("state") not in COMPLETE]
        total = len(doc["states"])
    except Exception as e:  # noqa: BLE001 — a table the gate cannot even read fails closed
        print(f"CI-GATE FAIL (checker malfunction): {type(e).__name__}: {e}")
        return 2
    for p in bad:
        print(f"CI-GATE FAIL (checker malfunction): {p}")
    if bad:
        return 2   # the table is not trustworthy: no evidence line can be derived from it
    for p in reuse:
        print(f"CI-GATE FAIL (false-current reuse): {p}")
    rc_failed = a.tier == "rc" and incomplete
    if rc_failed:
        print(f"CI-GATE FAIL (rc tier): {len(incomplete)} of {total} targets lack valid MEASURED or "
              f"VERIFIED_REUSE evidence")
    print("EVIDENCE: INCOMPLETE (NOT QUALIFIED)" if incomplete else "EVIDENCE: COMPLETE (RC-TIER CHECK STILL REQUIRED)")
    return 2 if reuse else 1 if rc_failed else 0


if __name__ == "__main__":
    sys.exit(main())
