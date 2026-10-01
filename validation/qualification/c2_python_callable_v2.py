"""WP-2.4.1 (C2-P4) — the evidence record of `probe.python_callable_v2`, the second python_callable identity.

Owner DECISION-6 (closure-evidence/v2/cycle2/OWNER-DECISIONS.json): the Cycle-1 probe implementation and digest stay
unchanged; new observation classes ship under a second identity with independent probe_id, digest, capability
calibration, falsifiability evidence, mutation evidence and Q0/Q1/Q2 coverage. This harness binds, from the live tree:

    identities      the package, the parent commit, the candidate HEAD and its lane commits, the aisef2 tree
    cycle1          the Cycle-1 identity proof: the live digest of probe.python_callable equals the frozen one and the
                    two source files equal the parent's blobs and the freeze manifest's identities
    probe           the second identity: id, digest, every source's identity, classes, enforcement, weakest path
    catalog         every entry: id, digest, active, cycle — exactly one active PYTHON_CALLABLE entry
    calibrations    the seven ProbeCapabilityCalibration records from REAL calibrate() runs over the committed fixtures
    fixtures        every fixture file by identity
    tests           the two test modules under validation/v2/owned_run.py (Ran N, OK, owned-process counts) and the
                    PYC family rows (test_FM2_PYC_V2_*) with their outcomes
    mutation        the C2-P4 summary from closure-evidence/v2/cycle2/P4-MUTATION.json, validated by mutation.py
    static          the Q0 checkers and ruff, as run
    decision_6      the owner decision, verbatim

    python -P validation/qualification/c2_python_callable_v2.py --run            # writes the record; refused on problems
    python -P validation/qualification/c2_python_callable_v2.py --bind-ci RUN_ID # binds the CI jobs of the record's commit
    python -P validation/qualification/c2_python_callable_v2.py --check          # the committed record still binds the tree
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT_REL = "closure-evidence/v2/cycle2/P4-PYTHON-CALLABLE-V2-CALIBRATION.json"
MUTATION_REL = "closure-evidence/v2/cycle2/P4-MUTATION.json"
DECISIONS_REL = "closure-evidence/v2/cycle2/OWNER-DECISIONS.json"
FIXTURE_REL = "tests/v2/fixtures/calibration/python_callable_v2"
PROBE_REL = "aisef2/probe/python_callable_v2.py"
PACKAGE, PHASE = "WP-2.4.1", "C2-P4"
PARENT = "77a437609fd59cd3c8d61d28472460ab9aa157f0"
TEST_MODULES = ("tests.v2.test_python_callable_v2", "tests.v2.test_python_callable_v2_bytecode")
PYC_ROW = re.compile(r"(test_FM2_PYC_V2_\w+) \([^)]*\)[\s\S]*?\.\.\. (ok|FAIL|ERROR|skipped[^\n]*)")
STATIC = (
    ["validation/v2/probe_static_checks.py", "--check"],
    ["validation/v2/cycle2_baseline.py", "--check"],
    ["validation/v2/kernel_static_checks.py"],
    ["validation/v2/destructive_authority.py", "--check"],
    ["validation/v2/mutation.py", "--check"],
)


def _module(name: str, path: pathlib.Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rf = _module("aisef_v2_p0_reference_fixture", ROOT / "validation" / "qualification" / "p0_reference_fixture.py")
cb = _module("aisef_v2_cycle2_baseline", ROOT / "validation" / "v2" / "cycle2_baseline.py")
mu = _module("aisef_v2_mutation", ROOT / "validation" / "v2" / "mutation.py")


def _git(*args: str) -> str:
    return rf._git(*args)


def identities() -> dict:
    base = rf.identities()
    return {**base, "package": PACKAGE, "phase": PHASE, "parent": PARENT,
            "lane_commits": _git("rev-list", "--reverse", f"{PARENT}..HEAD").split(),
            "parent_is_an_ancestor": subprocess.run(["git", "merge-base", "--is-ancestor", PARENT, "HEAD"], cwd=ROOT).returncode == 0}


# --------------------------------------------------------------------------------------- the two identities

def cycle1_identity_proof() -> dict:
    from aisef2.probe import python_callable as pc
    freeze = rf._load(cb.OUT_REL)["cycle1"]["probe_sources"]
    sources = {}
    for rel in cb.PROBE_SOURCES:
        live = cb.file_identity(ROOT / rel)
        sources[rel] = {"live": live, "parent_blob": _git("rev-parse", f"{PARENT}:{rel}"), "frozen": freeze[rel],
                        "unchanged": live["git_blob"] == _git("rev-parse", f"{PARENT}:{rel}") and live == freeze[rel]}
    return {"probe_id": pc.PROBE_ID, "live_digest": pc.DIGEST, "frozen_digest": cb.CYCLE1_PROBE["digest"],
            "digest_unchanged": pc.DIGEST == cb.CYCLE1_PROBE["digest"], "sources": sources,
            "baseline_guard": cb.check() == []}


def probe_identity() -> dict:
    from aisef2.probe import python_callable_v2 as pc2
    probe = pc2.PythonCallableV2Probe()
    return {"probe_id": pc2.PROBE_ID, "digest": pc2.DIGEST, "module": PROBE_REL,
            "sources": {rel: cb.file_identity(ROOT / "aisef2" / rel) for rel in pc2.PROBE_SOURCES},
            "digest_rule": "sha256 over each source's repository-relative name, NUL, its bytes with CRLF normalised to "
                           "LF, NUL — in PROBE_SOURCES order; the Cycle-1 module is a source because the frozen helpers "
                           "are imported from it",
            "classes": list(pc2.CLASSES), "on_deadline": {c: v.value for c, v in pc2.ON_DEADLINE.items()},
            "enforcement": probe.enforcement().value, "weakest_path": pc2.WEAKEST_PATH,
            "harness_preconditions": list(probe.harness_preconditions()), "placeholder": pc2.PLACEHOLDER}


def catalog_state() -> dict:
    from aisef2.probe import catalog
    return {"entries": [{"probe_id": e.probe_id, "probe_digest": e.probe_digest, "subject_kind": e.subject_kind.value,
                         "active": e.active, "cycle": e.cycle, "classes": list(e.classes), "module": e.module,
                         "fixture_root": e.fixture_root} for e in catalog.CATALOG],
            "problems": catalog.problems_of(catalog.CATALOG),
            "active": {k.value: e.probe_id for k, e in catalog.active().items()}}


# --------------------------------------------------------------------------------------- calibration and fixtures

def calibrations() -> list[dict]:
    from aisef2.probe import catalog, python_callable_v2 as pc2
    from aisef2.probe.calibration import NotQualified, calibrate, calibration_env
    probe, registry, base = pc2.PythonCallableV2Probe(), catalog.registry(), ROOT / FIXTURE_REL
    out = []
    for cls in pc2.CLASSES:
        pos, neg = base / cls / "positive", base / cls / "negative"
        names = (f"{FIXTURE_REL}/{cls}/positive", f"{FIXTURE_REL}/{cls}/negative")
        try:
            rec = calibrate(probe, cls, pos, neg, calibration_env(sys.executable), time.time, registry=registry, names=names)
            out.append({**dataclasses.asdict(rec), "qualified": True})
        except NotQualified as e:
            out.append({"observation_class": cls, "qualified": False, "reason": str(e)})
    return out


def fixture_identities() -> dict:
    base = ROOT / FIXTURE_REL
    return {p.relative_to(ROOT).as_posix(): cb.file_identity(p) for p in sorted(base.rglob("*")) if p.is_file()}


# --------------------------------------------------------------------------------------- tests

def run_tests() -> list[dict]:
    out = []
    for module in TEST_MODULES:
        with tempfile.TemporaryDirectory(prefix="c2-owned-") as t:
            measure = pathlib.Path(t) / "owned.json"
            cmd = [sys.executable, "-P", "validation/v2/owned_run.py", "--out", str(measure), "--",
                   sys.executable, "-m", "unittest", "-v", module]
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
            owned = json.loads(measure.read_text(encoding="utf-8")) if measure.is_file() else None
        text = r.stdout + r.stderr
        ran = re.search(r"Ran (\d+) tests? in ([\d.]+)s", text)
        out.append({"module": module, "command": cmd[1:], "exit": r.returncode,
                    "ran": int(ran.group(1)) if ran else None, "seconds": float(ran.group(2)) if ran else None,
                    "ok": r.returncode == 0 and bool(re.search(r"^OK$", text, re.M)),
                    "failing": sorted(set(re.findall(r"(?:ERROR|FAIL): (\S+) \(", text))),
                    "owned": {k: owned.get(k) for k in ("owned_before", "owned_at_exit", "owned_after", "escaped",
                                                        "released_empty", "harness_orphans_before",
                                                        "harness_orphans_after")} if owned else None,
                    "pyc_rows": [{"test": name, "outcome": outcome} for name, outcome in PYC_ROW.findall(text)]})
    return out


# --------------------------------------------------------------------------------------- mutation and static checks

def mutation_summary() -> dict:
    path = ROOT / MUTATION_REL
    if not path.is_file():
        return {"record": MUTATION_REL, "present": False, "problems": [f"{MUTATION_REL} is missing"]}
    rec = json.loads(path.read_text(encoding="utf-8"))
    problems = mu.problems_of(rec, ROOT, PHASE)
    targets = [t for t in rec["targets"] if t["target"] in mu.PHASE_TARGETS[PHASE]]
    return {"record": MUTATION_REL, "present": True, "problems": problems,
            "targets": len(targets), "expected_targets": len(mu.PHASE_TARGETS[PHASE]),
            "mutants": sum(t.get("mutants", 0) for t in targets), "killed": sum(t.get("killed", 0) for t in targets),
            "killed_by_timeout": sum(t.get("killed_by_timeout", 0) for t in targets),
            "survivors": {t["target"]: t["survivors"] for t in targets if t.get("survivors")},
            "errors": {t["target"]: t["error"] for t in targets if t.get("error")},
            "per_target": [{"target": t["target"], "mutants": t.get("mutants"), "killed": t.get("killed"),
                            "kill_tests": t.get("kill_tests"), "source_sha256": t.get("source_sha256")} for t in targets]}


def static_checks() -> list[dict]:
    out = []
    for argv in STATIC:
        r = subprocess.run([sys.executable, "-P", *argv], cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
        lines = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip()]
        out.append({"command": ["python", "-P", *argv], "exit": r.returncode, "last_line": lines[-1] if lines else ""})
    ruff = shutil.which("ruff")
    if ruff:
        r = subprocess.run([ruff, "check", "."], cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
        out.append({"command": ["ruff", "check", "."], "exit": r.returncode, "last_line": (r.stdout + r.stderr).strip().splitlines()[-1]})
    else:
        out.append({"command": ["ruff", "check", "."], "exit": None, "last_line": "ruff not on PATH; CI's lint job is the measurement"})
    return out


def decision_6() -> dict:
    return next(d for d in rf._load(DECISIONS_REL)["decisions"] if d["id"] == "DECISION-6")


# --------------------------------------------------------------------------------------- the record

def run() -> dict:
    ids = identities()
    c1 = cycle1_identity_proof()
    probe = probe_identity()
    cat = catalog_state()
    cal = calibrations()
    tests = run_tests()
    mut = mutation_summary()
    static = static_checks()
    problems = []
    if not ids["parent_is_an_ancestor"]:
        problems.append(f"HEAD does not descend from the accepted parent {PARENT[:12]}")
    if not c1["digest_unchanged"] or not all(s["unchanged"] for s in c1["sources"].values()) or not c1["baseline_guard"]:
        problems.append("the Cycle-1 probe identity changed (DECISION-6, R2)")
    if probe["digest"] == c1["live_digest"]:
        problems.append("the second identity shares the Cycle-1 digest")
    if cat["problems"] or cat["active"] != {"python_callable": probe["probe_id"]}:
        problems.append(f"catalog: {cat['problems'] or cat['active']}")
    if sorted(e["probe_id"] for e in cat["entries"]) != sorted([c1["probe_id"], probe["probe_id"]]):
        problems.append("the catalog does not hold exactly the two python_callable identities")
    for rec in cal:
        if not rec["qualified"] or rec.get("probe_digest") != probe["digest"]:
            problems.append(f"calibration {rec['observation_class']}: {rec.get('reason', 'not at the live digest')}")
    if [r["observation_class"] for r in cal] != probe["classes"]:
        problems.append("a declared class has no calibration record")
    for t in tests:
        if not t["ok"] or not t["ran"]:
            problems.append(f"{t['module']}: exit {t['exit']}, ran {t['ran']}, failing {t['failing']}")
        if t["owned"] and (t["owned"]["owned_after"] or t["owned"]["escaped"] or not t["owned"]["released_empty"]):
            problems.append(f"{t['module']}: owned-process residual {t['owned']}")
    rows = [r for t in tests for r in t["pyc_rows"]]
    if len(rows) != 10 or any(r["outcome"] != "ok" for r in rows):
        problems.append(f"PYC family: {len(rows)} rows, outcomes {sorted({r['outcome'] for r in rows})}")
    problems += mut["problems"]
    for s in static:
        if s["exit"] not in (0, None):
            problems.append(f"{' '.join(s['command'])}: exit {s['exit']} — {s['last_line']}")
    return {
        "record": "AISEF V2 — WP-2.4.1 PROBE.PYTHON_CALLABLE_V2 CALIBRATION (C2-P4: the second python_callable identity)",
        "work_package": PACKAGE,
        "phase": PHASE,
        "authority": "owner DECISION-6 'KEEP_CYCLE1_PROBE_SECOND_IDENTITY' (AISEF V2 — CYCLE-2 OWNER DECISIONS / "
                     "WP-2.0.1 AUTHORIZATION, 2026-09-28); CYCLE2-PROBE-TAXONOMY-PROPOSAL §5; "
                     "CYCLE2-F5-COMPATIBILITY-REPORT §2.4",
        "identities": ids,
        "platform": {"python": sys.version.split()[0], "platform": sys.platform},
        "cycle1_identity": c1,
        "probe": probe,
        "catalog": cat,
        "calibrations": cal,
        "fixtures": fixture_identities(),
        "tests": tests,
        "test_placement": "tests/v2/test_python_callable_v2*.py live in the ROOT tier: aisef2/invariants/registry.py's "
                          "Tier enum is closed and is not this package's to edit, so tests/v2/c2/ could not be armed",
        "pyc_family": rows,
        "mutation": mut,
        "static": static,
        "decision_6": decision_6(),
        "semantics": {
            "unchanged_from_cycle1": ["protocol lines READY/DISPATCHED/RESULT with a per-evaluation nonce on captured "
                                      "stdout", "harness watchdog vs subject window (§9.2)", "signal provenance (§9.3)",
                                      "pump-completion barrier (§9.4)", "bytecode isolation (-I -B -X pycache_prefix)",
                                      "the meaning of exists/returns/raises/blocks"],
            "added": ["returns_bytes", "equals (non-callable subject; a callable subject is UNSUPPORTED -> INVALID_SPEC)",
                      "raises_attrs", "the workspace stimulus with the one placeholder <ws>"],
            "expectations": "compared through aisef2.product.contract.plain (the JSON form of the spec's frozen data); "
                            "the Cycle-1 probe's json round-trip raises TypeError on a nested returns expectation — "
                            "measured on the frozen module, not changed",
        },
        "problems": problems,
        "verdict": "QUALIFIED" if not problems else "NOT QUALIFIED",
    }


def bind_ci(run_id: int) -> dict:
    """Bind the CI jobs of the record's commit (every attempt, every job, the unittest count from the log when one
    exists, the annotations when not) — as p0_reference_fixture.bind_ci, for this record."""
    rec = rf._load(OUT_REL)
    head = rec["identities"]["head"]
    attempts = int(json.loads(rf._gh("run", "view", str(run_id), "--json", "attempt"))["attempt"])
    out = {"run": run_id, "commit": head, "attempts": []}
    for n in range(1, attempts + 1):
        jobs = json.loads(rf._gh("api", f"repos/nghinh/aisef/actions/runs/{run_id}/attempts/{n}/jobs"))["jobs"]
        rows = []
        for j in sorted(jobs, key=lambda x: x["name"]):
            if j["head_sha"] != head:
                raise SystemExit(f"run {run_id} attempt {n} is of {j['head_sha'][:7]}, not {head[:7]}")
            log = subprocess.run(["gh", "api", "--allow-escape-sequences", f"repos/nghinh/aisef/actions/jobs/{j['id']}/logs"],
                                 cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
            text = log.stdout or ""
            available = log.returncode == 0 and bool(text.strip()) and "<Error>" not in text[:300]
            m = re.search(r"Ran (\d+) tests", text) if available else None
            ann = subprocess.run(["gh", "api", f"repos/nghinh/aisef/check-runs/{j['id']}/annotations"], cwd=ROOT,
                                 capture_output=True, encoding="utf-8", errors="replace")
            annotations = [a.get("message", "") for a in json.loads(ann.stdout or "[]")] if ann.returncode == 0 else []
            failing = sorted(set(re.findall(r"(?:ERROR|FAIL): \S+ \((\S+)\)", text))) if available else []
            rows.append({"job": j["name"], "job_id": j["id"], "conclusion": j["conclusion"], "started_at": j["started_at"],
                         "completed_at": j["completed_at"], "tests_run": int(m.group(1)) if m else None,
                         "log_available": available, "failing_tests": failing, "annotations": annotations})
        out["attempts"].append({"attempt": n, "jobs": rows})
    rec["cross_platform"] = {
        "rule": "the record's commit's CI runs the whole suite, tests/v2/test_python_callable_v2*.py included, on every "
                "platform of the matrix; the probe and fixture bytes it measured are the ones this record binds by digest",
        "ci": out,
        "platforms": sorted({("windows" if "windows" in r["job"] else "linux") for a in out["attempts"] for r in a["jobs"]
                             if r["job"].startswith("unit")}),
    }
    (ROOT / OUT_REL).write_text(rf.render(rec), encoding="utf-8")
    return rec["cross_platform"]


def check() -> list[str]:
    """The committed record still binds this tree: the probe, its sources, the fixtures, the catalog, the Cycle-1 proof."""
    path = ROOT / OUT_REL
    if not path.is_file():
        return [f"{OUT_REL} is missing"]
    rec = json.loads(path.read_text(encoding="utf-8"))
    out = []
    if rec.get("problems"):
        out.append("the record was written with problems")
    live = probe_identity()
    for key in ("probe_id", "digest", "sources", "classes", "on_deadline"):
        if rec["probe"].get(key) != live[key]:
            out.append(f"probe {key} changed since the record")
    if rec["fixtures"] != fixture_identities():
        out.append("a calibration fixture changed since the record")
    if rec["catalog"]["entries"] != catalog_state()["entries"]:
        out.append("the catalog changed since the record")
    c1 = cycle1_identity_proof()
    if not c1["digest_unchanged"] or not all(s["unchanged"] for s in c1["sources"].values()):
        out.append("the Cycle-1 probe identity changed")
    if {c["observation_class"] for c in rec["calibrations"]} != set(live["classes"]) \
            or any(c.get("probe_digest") != live["digest"] for c in rec["calibrations"]):
        out.append("the calibration records do not cover every class at the live digest")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--bind-ci" in argv:
        cp = bind_ci(int(argv[argv.index("--bind-ci") + 1]))
        for a in cp["ci"]["attempts"]:
            for r in a["jobs"]:
                print(f"attempt {a['attempt']}: {r['job']:32s} {r['conclusion']:8s} tests {r['tests_run']} "
                      f"{'(no log; ' + '; '.join(r['annotations'])[:90] + ')' if not r['log_available'] else ''}")
        print(f"bound CI run {cp['ci']['run']} into {OUT_REL}")
        return 0
    if "--check" in argv:
        problems = check()
        for p in problems:
            print("FAIL ", p)
        print(f"python_callable_v2 evidence: {'FAIL' if problems else 'PASS'}")
        return 1 if problems else 0
    if "--run" in argv:
        rec = run()
        for p in rec["problems"]:
            print("FAIL ", p)
        cal = ", ".join(f"{c['observation_class']}={'ok' if c['qualified'] else 'NOT'}" for c in rec["calibrations"])
        print(f"probe {rec['probe']['probe_id']}@{rec['probe']['digest'][:12]}; cycle-1 unchanged: "
              f"{rec['cycle1_identity']['digest_unchanged']}; calibrations: {cal}")
        for t in rec["tests"]:
            print(f"{t['module']}: ran {t['ran']} ok={t['ok']} owned_after={t['owned'] and t['owned']['owned_after']}")
        m = rec["mutation"]
        print(f"mutation: {m.get('killed')}/{m.get('mutants')} killed over {m.get('targets')}/{m.get('expected_targets')} "
              f"targets; survivors {m.get('survivors')}; problems {m['problems']}")
        if rec["problems"]:
            return 1
        (ROOT / OUT_REL).write_text(rf.render(rec), encoding="utf-8")
        print(f"wrote {OUT_REL}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
