"""WP-2.3.1 — evidence for the `process_effect` scenario probe: closure-evidence/v2/cycle2/P3-EFFECT-HARNESS.json.

    --run            run the probe's test modules under the owned-process gate, read the PE / FM2-EFFECT / FM2-PYC rows
                     from an in-process run, bind every identity, the step vocabulary and the fault table (with their
                     digests), the C2-P3 mutation summary and the static checks; write the record (refused on any
                     problem)
    --bind-ci RUN    bind the CI measurements of the record's commit (every attempt, every job, per job id), as
                     validation/qualification/c2_cli_harness.py does

The record binds: the package and its parent commit (the evidence-complete C2-P2 candidate) with its aisef2 tree, the
candidate commit and its aisef2 tree, the probe identity (id, digest, the digest of each source), the catalog facts,
the Cycle-1 identities of validation/v2/cycle2_baseline.py, the platform, each test module's result run as
`python -P validation/v2/owned_run.py -- python -m unittest <module>` (Ran N, OK, owned-process counts), the rows with
their outcomes, STEPS and FAULTS as declared, the mutation summary of phase C2-P3, the static checks and the design
notes.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT_REL = "closure-evidence/v2/cycle2/P3-EFFECT-HARNESS.json"
MUTATION_REL = "closure-evidence/v2/cycle2/P3-MUTATION.json"
PACKAGE = "WP-2.3.1"
PARENT = "e063b76fd1cc625211dca1f8b64db9742e566e6a"
PARENT_AISEF2_TREE = "509653f3ea630564976dca4b3e8de5041517718a"
PROBE_REL = "aisef2/probe/process_effect.py"
TEST_MODULES = ("tests.v2.test_probe_process_effect_units", "tests.v2.test_probe_process_effect",
                "tests.v2.test_probe_process_effect_bytecode")
ROW_MODULES = TEST_MODULES
FAULT_ROWS = {
    **{f"FM2-EFFECT-{n}": f"test_FM2_EFFECT_{n}_" for n in range(1, 11)},
    "FM2-PYC-2": "test_FM2_PYC_2_",
    **{f"FM2-PYC-EFFECT-{n}": f"test_FM2_PYC_EFFECT_{n}_" for n in range(1, 6)},
}
FAULT_MEANING = {
    "FM2-EFFECT-1": "an unknown step kind: INVALID_SPEC at admission, nothing runs",
    "FM2-EFFECT-2": "a fault restoration failure (a controlled double of the request): HARNESS_FAILED, never a verdict",
    "FM2-EFFECT-3": "an exception in a non-final step: REFUTED with the step named, for every class",
    "FM2-EFFECT-4": "a subprocess step that leaves a process: the range's residual, stopped and recorded by its release "
                    "(§17.1), the observation unchanged (POSIX)",
    "FM2-EFFECT-5": "a second construct without declaration: refused at admission",
    "FM2-EFFECT-6": "a fault the subject swallows: observed by the file observable (equals_before)",
    "FM2-EFFECT-7": "a harness that crashes before opening the marker file: HARNESS_FAILED",
    "FM2-EFFECT-8": "a protocol line forged on stdout: captured bytes, never protocol",
    "FM2-EFFECT-9": "the process ending during a step: REFUTED with that step",
    "FM2-EFFECT-10": "a controller stop after DISPATCHED: an interruption, no result",
    "FM2-PYC-2": "P7-FINDING-001 case 2: two checkouts of one content, different dates, one verdict",
    "FM2-PYC-EFFECT-1": "in-tree stale bytecode with a matching header is never the subject",
    "FM2-PYC-EFFECT-2": "a subprocess step observes the source too",
    "FM2-PYC-EFFECT-3": "the probe writes no bytecode into the checkout",
    "FM2-PYC-EFFECT-4": "the cache is fresh, empty, outside the checkout and distinct per evaluation",
    "FM2-PYC-EFFECT-5": "without the external cache the stale bytecode decides: the reproducer detects the defect",
}
PE_CASES = {**{f"PE-{n}": f"test_PE_{n}_" for n in range(1, 9)}, "PE-ADV-1": "test_PE_ADV_1_",
            "PE-ADV-2": "test_PE_ADV_2_", "PE-Q0": "test_PE_Q0_"}
DESIGN_NOTES = [
    "the step vocabulary is a closed mapping STEPS (kind -> required, optional fields) with one typed shape per kind "
    "(_SHAPES keyed by the same vocabulary); the child script dispatches through HANDLERS keyed by it; an unknown kind "
    "gives the spec no class (UNSUPPORTED -> INVALID_SPEC at admission), never a default meaning; a scenario holds at "
    "most one workspace step (first) and one construct, distinct binding names, and every fault is followed by the "
    "call / expect_raises / subprocess step it applies to",
    "DECISION-2: FAULTS is a closed table in the module (so in the digest): id -> (module, attribute, exception type "
    "name); the parent puts the entry in the request; the child installs a stand-in whose first invocation raises, "
    "right before the next step's call, and in a finally restores the original and asserts it IS the original "
    "again; a failed restoration is a harness failure (HARNESS_FAILED); no callable, shell string, path or developer "
    "file can select or shape a fault, and nothing the subject returns can",
    "one window per scenario (within_s), from DISPATCHED to RESULT; an expired window is REFUTED for every class",
    "`<ws>` is the only placeholder, substituted at the head of strings of args, kwargs and argv (as `<ws>/x` -> the "
    "workspace path, `/`, `x`, on every platform); every reported string, exception attribute and JSON field has "
    "the workspace path (as given and resolved) replaced back by `<ws>` before comparison; JSON equality is exact "
    "(canonical text: true is not 1, 1 is not 1.0)",
    "the protocol channel, the watch and the evaluation directory are cli_invocation's, imported (marker file, "
    "_await/_protocol, _harness_failure, _preflight, _disposed, _child_env); every conclusion after DISPATCHED goes "
    "through python_callable._after_dispatch (C2-P2-FINDING-002); the child opens its capture descriptors with O_BINARY "
    "and pins the standard streams' newline (C2-P2-FINDING-001); every file the harness writes is written in binary",
    "a subprocess step runs the ExecutionEnv's interpreter (never the harness's sys.executable) with -I -B -X "
    "pycache_prefix=<fresh per step> -X utf8=1 and a probe-owned boot (SUBPROCESS) that puts the revision on the path "
    "and runs `-m module` as __main__, in the workspace, with the scrubbed environment; the child is a member of the "
    "probe's range",
    "the child script's functions are mutation targets (validation/v2/mutation.py `path::HARNESS/function`: the "
    "mutant is made in the parsed script and written back into the constant), killed by the real-subject module",
    "the tests live at the tests/v2 root (the test tiers are a closed enum of the frozen invariant registry); the "
    "calibration fixtures (tests/v2/fixtures/calibration/process_effect) are committed with the harness because Q0 "
    "PROBE_CATALOG_CLOSURE requires them for every class of a registered probe; their calibration records are "
    "WP-2.3.2's",
]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _identity(path: pathlib.Path) -> dict:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return {"sha256": _sha(data), "git_blob": hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()}


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, encoding="utf-8", check=True).stdout.strip()


def _module(name: str, path: pathlib.Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _cli():
    """The C2-P2 evidence harness, whose measurement functions (owned_run, in_process, rows_of, bind_ci) are reused."""
    return _module("aisef_v2_c2_cli_harness", ROOT / "validation" / "qualification" / "c2_cli_harness.py")


def render(record: dict) -> str:
    return json.dumps(record, indent=1, ensure_ascii=False) + "\n"


def _digest(value) -> str:
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def vocabulary() -> dict:
    from aisef2.probe import process_effect as pe
    steps = {k: {"required": list(r), "optional": list(o)} for k, (r, o) in pe.STEPS.items()}
    faults = {k: list(v) for k, v in pe.FAULTS.items()}
    return {"steps": steps, "steps_sha256": _digest(steps), "faults": faults, "faults_sha256": _digest(faults),
            "faulted": list(pe.FAULTED), "file_shapes": list(pe.FILE_SHAPES), "classes": list(pe.CLASSES),
            "on_deadline": {k: v.value for k, v in pe.ON_DEADLINE.items()}, "placeholder": pe.PLACEHOLDER,
            "digest_rule": "sha256 of the canonical JSON (sorted keys, no whitespace) of the table as declared"}


def identities() -> dict:
    cb = _module("aisef_v2_cycle2_baseline", ROOT / "validation" / "v2" / "cycle2_baseline.py")
    from aisef2.probe import catalog, process_effect as pe
    entry = catalog.entry_for(PROBE_REL)
    return {
        "package": PACKAGE, "parent": PARENT, "parent_aisef2_tree": PARENT_AISEF2_TREE,
        "head": _git("rev-parse", "HEAD"), "aisef2_tree": _git("rev-parse", "HEAD:aisef2"),
        "probe": {"id": pe.PROBE_ID, "digest": pe.DIGEST, "classes": list(pe.CLASSES),
                  "sources": {rel: _identity(ROOT / "aisef2" / rel) for rel in pe.PROBE_SOURCES},
                  "catalog": {"subject_kind": entry.subject_kind.value, "subject_process": entry.subject_process,
                              "protocol_channel": entry.protocol_channel, "stimulus_shape": entry.stimulus_shape,
                              "fixture_root": entry.fixture_root, "cycle": entry.cycle, "active": entry.active},
                  "enforcement": "PARTIAL", "weakest_path": pe.WEAKEST_PATH, "fault_witness": pe.FAULT_WITNESS},
        "tests": {m: _identity(ROOT / (m.replace(".", "/") + ".py")) for m in TEST_MODULES},
        "cycle1": {"semantic_candidate": cb.PARENT_COMMIT, "aisef2_tree": cb.PARENT_AISEF2_TREE,
                   "probe": dict(cb.CYCLE1_PROBE)},
        "cycle2_freeze_manifest": {"path": cb.OUT_REL, "sha256": _identity(ROOT / cb.OUT_REL)["sha256"]},
        "owner_decisions": {"path": cb.DECISIONS_REL, "sha256": _identity(ROOT / cb.DECISIONS_REL)["sha256"]},
        "hash_rule": "every sha256 here is over bytes with CRLF normalised to LF; git_blob = sha1 of the blob header "
                     "and the same bytes",
    }


def static_checks() -> dict:
    ps = _module("aisef_v2_probe_static_checks", ROOT / "validation" / "v2" / "probe_static_checks.py")
    cb = _module("aisef_v2_cycle2_baseline", ROOT / "validation" / "v2" / "cycle2_baseline.py")
    da = _module("aisef_v2_destructive_authority", ROOT / "validation" / "v2" / "destructive_authority.py")
    return {"probe_static_checks": ps.check(ROOT), "cycle2_baseline": cb.check(), "destructive_authority": da.check()}


def mutation_summary() -> dict:
    mu = _module("aisef_v2_mutation", ROOT / "validation" / "v2" / "mutation.py")
    path = ROOT / MUTATION_REL
    if not path.is_file():
        return {"record": MUTATION_REL, "present": False, "problems": [f"{MUTATION_REL} is missing"]}
    rec = json.loads(path.read_text(encoding="utf-8"))
    targets = [t for t in rec["targets"] if t["target"].startswith(PROBE_REL)]
    return {"record": MUTATION_REL, "present": True, "phase": "C2-P3",
            "source_sha256": sorted({t.get("source_sha256") for t in targets}),
            "targets": len(targets), "mutants": sum(t.get("mutants", 0) for t in targets),
            "killed": sum(t.get("killed", 0) for t in targets),
            "killed_by_timeout": sum(t.get("killed_by_timeout", 0) for t in targets),
            "child_script_targets": sum(1 for t in targets if "::HARNESS/" in t["target"]),
            "survivors": {t["target"]: t["survivors"] for t in targets if t.get("survivors")},
            "errors": {t["target"]: t["error"] for t in targets if t.get("error")},
            "problems": mu.problems_of(rec, ROOT, "C2-P3"),
            "per_target": {t["target"].split("::")[1]: {"mutants": t.get("mutants"), "killed": t.get("killed"),
                                                        "kill_tests": t.get("kill_tests")} for t in targets}}


def run() -> dict:
    h = _cli()
    problems: list[str] = []
    runs = {m: h.owned_run(m) for m in TEST_MODULES}
    for m, r in runs.items():
        if r["status"] != "OK" or r["exit"] != 0 or r["residual"]:
            problems.append(f"{m}: status {r['status']} exit {r['exit']} residual {r['residual']}")
    outcomes = {k: v for m in ROW_MODULES for k, v in h.in_process(m).items()}
    fault_rows = h.rows_of(outcomes, FAULT_ROWS)
    for row, r in fault_rows.items():
        r["meaning"] = FAULT_MEANING[row]
    cases = h.rows_of(outcomes, PE_CASES)
    for name, rows in (("fault", fault_rows), ("case", cases)):
        for row, r in rows.items():
            if r["outcome"] != "PASS" and not r["outcome"].startswith("SKIP"):
                problems.append(f"{name} row {row}: {r['outcome']}")
    static = static_checks()
    for name, found in static.items():
        if found:
            problems.append(f"{name}: {found}")
    mutation = mutation_summary()
    problems += [f"mutation: {p}" for p in mutation["problems"]]
    return {
        "record": "AISEF V2 — WP-2.3.1 PROCESS EFFECT HARNESS (probe.process_effect: scenario interpreter, closed step "
                  "vocabulary, DECISION-2 fault step, fault rows)",
        "work_package": PACKAGE,
        "identities": identities(),
        "platform": {"python": sys.version.split()[0], "platform": sys.platform},
        "vocabulary": vocabulary(),
        "tests": runs,
        "cases": cases,
        "fault_rows": fault_rows,
        "mutation": mutation,
        "static": static,
        "design_notes": DESIGN_NOTES,
        "problems": problems,
        "verdict": "HARNESS GREEN" if not problems else "NOT QUALIFIED",
    }


def bind_ci(run_id: int, out_rel: str = OUT_REL) -> dict:
    """c2_cli_harness.bind_ci over this record: every attempt, every job by id, the run of the record's commit."""
    h = _cli()
    h.OUT_REL = out_rel
    h.bind_ci(run_id)
    rec = json.loads((ROOT / out_rel).read_text(encoding="utf-8"))
    rec["cross_platform"]["rule"] = ("the record's commit's CI runs the whole unittest discovery, which includes the "
                                     "process_effect test modules on every platform of the matrix")
    (ROOT / out_rel).write_text(render(rec), encoding="utf-8")
    return rec["cross_platform"]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--bind-ci" in argv:
        cp = bind_ci(int(argv[argv.index("--bind-ci") + 1]))
        for a in cp["ci"]["attempts"]:
            for r in a["jobs"]:
                print(f"attempt {a['attempt']}: {r['job']:32s} {r['conclusion']:8s} tests {r['tests_run']}")
        print(f"bound CI run {cp['ci']['run']} into {OUT_REL}")
        return 0
    if "--run" in argv:
        rec = run()
        for p in rec["problems"]:
            print("FAIL ", p)
        for m, r in rec["tests"].items():
            print(f"{m}: Ran {r['ran']} {r['status']} exit {r['exit']} owned {r['owned_processes']}")
        print(f"cases {sum(1 for r in rec['cases'].values() if r['outcome'] == 'PASS')}/{len(rec['cases'])} PASS; fault "
              f"rows {sum(1 for r in rec['fault_rows'].values() if r['outcome'] == 'PASS')}/{len(rec['fault_rows'])} "
              f"PASS; mutation {rec['mutation'].get('killed')}/{rec['mutation'].get('mutants')} killed, survivors "
              f"{rec['mutation'].get('survivors')}")
        if rec["problems"]:
            return 1
        (ROOT / OUT_REL).write_text(render(rec), encoding="utf-8")
        print(f"wrote {OUT_REL}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
