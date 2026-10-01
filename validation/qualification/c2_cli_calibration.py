"""WP-2.2.2 — calibration evidence for the `cli_invocation` probe: closure-evidence/v2/cycle2/P2-CLI-CALIBRATION.json.

    --run            calibrate every class of the probe over its committed fixtures (real `calibrate()` runs, the
                     harness registry from the catalog), record the class table and the DECISION-1 declarations, the
                     equality design (DECISION-4), the test result under the owned-process gate and the C2-P2
                     mutation summary; write the record (refused on any problem)
    --bind-ci RUN    bind the CI measurements of the record's commit (as validation/qualification/c2_cli_harness.py)
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT_REL = "closure-evidence/v2/cycle2/P2-CLI-CALIBRATION.json"
HARNESS_REL = "closure-evidence/v2/cycle2/P2-CLI-HARNESS.json"
PROBE_ID = "probe.cli_invocation"
PACKAGE = "WP-2.2.2"
FIXTURES_REL = "tests/v2/fixtures/calibration/cli_invocation"
TEST_MODULES = ("tests.v2.test_c2_cli_calibration", "tests.v2.test_c2_cli_verdicts", "tests.v2.test_c2_cli_protocol",
                "tests.v2.test_c2_cli_invocation")
#: CLICAL-1..3 run real subjects (the calibration module); CLICAL-4, the class table, is in-process (the verdicts module)
ROW_MODULES = ("tests.v2.test_c2_cli_calibration", "tests.v2.test_c2_cli_verdicts")
CASES = {f"CLICAL-{n}": f"test_CLICAL_{n}_" for n in range(1, 5)}
EQUALITY_DESIGN = [
    "class `equality` (DECISION-4): the observable names stimulus_a, stimulus_b, the normalization policy "
    "(an optional non-empty newline turned into \\n, an optional strip_trailing_newline; {} compares the bytes as "
    "captured) and the comparator (bytes_equal | json_equal), plus the streams compared; all of them are probe "
    "input, so they enter semantic_hash with the revision and the probe identity; all four equality keys are "
    "required — one left out is refused at admission (UNSUPPORTED -> INVALID_SPEC), never defaulted",
    "json_equal over bytes that are not UTF-8 JSON (either side) is unequal (REFUTED), never an error: a decoding "
    "error is a ValueError like a JSON error",
    "two independent invocations of the same subject in two fresh evaluation directories (workspace, bytecode cache, "
    "protocol file, captures) under one observe(); the facts record that the directories are distinct; each half "
    "runs under the same bounded window and every half outcome other than a returned invocation is the "
    "observation (SUBJECT_ABSENT, SUBJECT_DEADLINE -> REFUTED, NON_CONTROLLER_SIGNAL, HARNESS_FAILED)",
    "SATISFIED iff both invocations returned, their exit codes are equal and, for every named stream, the "
    "normalised captured bytes are equal under the comparator; the comparator reads the two normalised results and "
    "nothing else — no clock, no cache, no checkout metadata, no residue of the first invocation",
    "quantifier semantics (DECISION-1): bounded_witness_measurement — two invocations witness equality, they do "
    "not prove it for every run; enforcement stays PARTIAL",
]


def _load_harness():
    import importlib.util
    name = "aisef_v2_c2_cli_harness"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "validation" / "qualification" / "c2_cli_harness.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def calibrations() -> tuple[list[dict], list[str]]:
    """One real `calibrate()` per class over the committed fixtures; a class that does not contrast is a problem."""
    from dataclasses import asdict
    from aisef2.probe import catalog, cli_invocation as ci
    from aisef2.probe.calibration import NotQualified, calibrate, calibration_env
    probe = ci.CliInvocationProbe()
    registry = catalog.registry()
    env = calibration_env(sys.executable)
    records, problems = [], []
    for cls in ci.CLASSES:
        pos, neg = (ROOT / FIXTURES_REL / cls / side for side in ("positive", "negative"))
        try:
            rec = calibrate(probe, cls, pos, neg, env, time.time, registry=registry,
                            names=(f"{FIXTURES_REL}/{cls}/positive", f"{FIXTURES_REL}/{cls}/negative"))
        except NotQualified as e:
            problems.append(f"{cls}: {e}")
            continue
        records.append(asdict(rec))
        try:   # the same fixtures reject the probe once they stop contrasting
            calibrate(probe, cls, neg, neg, env, time.time, registry=registry)
            problems.append(f"{cls}: a non-contrasting pair (negative, negative) was not rejected")
        except NotQualified:
            pass
    return records, problems


def probe_digest_change(current: str) -> dict:
    """WP-2.2.2 edits aisef2/probe/cli_invocation.py, so the probe digest differs from the one the WP-2.2.1 harness
    record binds. That record stays as committed, bound to its own commit (history, never rewritten); this record binds
    the new digest, and the integration binds the final one. Stated here from both records, not assumed."""
    rec = json.loads((ROOT / HARNESS_REL).read_text(encoding="utf-8"))
    previous = rec["identities"]["probe"]["digest"]
    out = {"wp_2_2_1_record": HARNESS_REL, "wp_2_2_1_commit": rec["identities"]["head"],
           "wp_2_2_1_probe_digest": previous, "this_probe_digest": current, "changed": previous != current,
           "rule": "the WP-2.2.1 harness record stays bound to its commit and digest (not regenerated); every C2-P2 "
                   "mutation target is re-run at this digest (P2-MUTATION.json binds the module source); the "
                   "integration binds the final digest"}
    if rec["identities"]["probe"]["id"] != PROBE_ID:
        out["problem"] = f"{HARNESS_REL} is not a record of {PROBE_ID}"
    return out


def class_table() -> dict:
    from aisef2.probe import cli_invocation as ci
    return {cls: {"quantifier": row["quantifier"], "domain": row["domain"], "enforcement": row["enforcement"],
                  "on_deadline": ci.ON_DEADLINE[cls].value,
                  "rows": [{"facts": facts, "verdict": verdict} for facts, verdict in row["rows"]]}
            for cls, row in ci.CLASS_TABLE.items()}


def run() -> dict:
    h = _load_harness()
    from aisef2.probe import cli_invocation as ci
    problems: list[str] = []
    records, cal_problems = calibrations()
    problems += cal_problems
    runs = {m: h.owned_run(m) for m in TEST_MODULES}
    for m, r in runs.items():
        if r["status"] != "OK" or r["exit"] != 0 or r["residual"]:
            problems.append(f"{m}: status {r['status']} exit {r['exit']} residual {r['residual']}")
    outcomes = {k: v for m in ROW_MODULES for k, v in h.in_process(m).items()}
    cases = h.rows_of(outcomes, CASES)
    for row, r in cases.items():
        if r["outcome"] != "PASS":
            problems.append(f"case {row}: {r['outcome']}")
    table = class_table()
    if set(table) != set(ci.CLASSES):
        problems.append(f"class table {sorted(table)} does not cover the classes {sorted(ci.CLASSES)}")
    for cls, row in table.items():
        if row["quantifier"] not in ci.QUANTIFIERS:
            problems.append(f"{cls}: quantifier {row['quantifier']!r} is not one of {ci.QUANTIFIERS}")
    static = h.static_checks()
    for name, found in static.items():
        if found:
            problems.append(f"{name}: {found}")
    mutation = h.mutation_summary()
    problems += [f"mutation: {p}" for p in mutation["problems"]]
    identities = h.identities()
    identities["package"] = PACKAGE
    digest_change = probe_digest_change(identities["probe"]["digest"])
    if digest_change.get("problem"):
        problems.append(digest_change["problem"])
    return {
        "record": "AISEF V2 — WP-2.2.2 CLI INVOCATION CALIBRATION (probe.cli_invocation: class calibrations, class table, "
                  "DECISION-1 declarations, DECISION-4 equality)",
        "work_package": PACKAGE,
        "rfc_sections": ["9.1", "9.1.1", "9.2"],
        "rule": "a counterexample produces the verdict opposite to candidate_expectation; a ProbeCapabilityCalibration "
                "exists only when the positive fixture is observed SATISFIED and the negative one REFUTED, both by the "
                "real probe over the committed fixtures with the observation class read from the catalog registry",
        "identities": identities,
        "probe_digest_change": digest_change,
        "platform": {"python": sys.version.split()[0], "platform": sys.platform},
        "calibrations": records,
        "fixtures": {cls: {side: {rel: h._identity(ROOT / FIXTURES_REL / cls / side / rel)
                                  for rel in ("request.json", "checkout/calib_cli.py")}
                           for side in ("positive", "negative")} for cls in ci.CLASSES},
        "class_table": table,
        "decision_1": {"quantifiers": list(ci.QUANTIFIERS),
                       "declared": {cls: row["quantifier"] for cls, row in table.items()},
                       "enforcement": "PARTIAL for every class; no class claims FULL",
                       "rule": "a verdict of a bounded witness measurement is never recorded as a proof of the "
                               "universal property; the class table names the witness (the declared invocation, "
                               "the window, the two invocations)"},
        "equality_design": EQUALITY_DESIGN,
        "tests": runs,
        "cases": cases,
        "mutation": mutation,
        "static": static,
        "problems": problems,
        "verdict": "CALIBRATED" if not problems else "NOT QUALIFIED",
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    h = _load_harness()
    if "--bind-ci" in argv:
        h.OUT_REL = OUT_REL
        cp = h.bind_ci(int(argv[argv.index("--bind-ci") + 1]))
        for a in cp["ci"]["attempts"]:
            for r in a["jobs"]:
                print(f"attempt {a['attempt']}: {r['job']:32s} {r['conclusion']:8s} tests {r['tests_run']}")
        print(f"bound CI run {cp['ci']['run']} into {OUT_REL}")
        return 0
    if "--run" in argv:
        rec = run()
        for p in rec["problems"]:
            print("FAIL ", p)
        for c in rec["calibrations"]:
            print(f"calibrated {c['observation_class']:14s} {c['probe_id']}@{c['probe_digest'][:12]}")
        for m, r in rec["tests"].items():
            print(f"{m}: Ran {r['ran']} {r['status']} exit {r['exit']} owned {r['owned_processes']}")
        print(f"classes {len(rec['calibrations'])}/{len(rec['class_table'])} calibrated; mutation "
              f"{rec['mutation'].get('killed')}/{rec['mutation'].get('mutants')} killed, survivors {rec['mutation'].get('survivors')}")
        if rec["problems"]:
            return 1
        (ROOT / OUT_REL).write_text(h.render(rec), encoding="utf-8")
        print(f"wrote {OUT_REL}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
