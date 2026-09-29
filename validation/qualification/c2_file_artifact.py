"""WP-2.1.1 (Cycle 2, C2-P1) — the `file_artifact` probe: calibration, tests, mutation, faults and static checks,
bound into one record.

    --run            REALLY calibrate the three classes over the committed fixtures, run the probe's test module
                     under the owned-process discipline, read the C2-P1 mutation record, run the static checks, and
                     write closure-evidence/v2/cycle2/P1-FILE-ARTIFACT-CALIBRATION.json (refused on any problem)
    --bind-ci RUN_ID add cross_platform from the GitHub API, per job id (as p0_reference_fixture.bind_ci)

The record binds: the package and its parent commit, the candidate commit and its aisef2 tree, the probe id and
digest with the digests of its sources, the inherited Cycle-1 identities (validation/v2/cycle2_baseline.py), the
platform, the three ProbeCapabilityCalibration records with the read path each fixture exercised, every fixture
file by CRLF-normalised sha256 and git blob, the unittest result with the owned-process residual counts, the
mutation totals with every survivor, the fault-family rows FM2-FILE-1..5 with their test ids and outcomes, and
the static checks (probe rules, catalog closure, Cycle-2 baseline guard, destructive authority, kernel rules).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PACKAGE = "WP-2.1.1"
PHASE = "C2-P1"
PARENT = "77a437609fd59cd3c8d61d28472460ab9aa157f0"
OUT_REL = "closure-evidence/v2/cycle2/P1-FILE-ARTIFACT-CALIBRATION.json"
MUTATION_REL = "closure-evidence/v2/cycle2/P1-MUTATION.json"
PROBE_REL = "aisef2/probe/file_artifact.py"
TEST_MODULE = "tests.v2.test_c2_file_artifact"
TEST_REL = "tests/v2/test_c2_file_artifact.py"
FIXTURES_REL = "tests/v2/fixtures/calibration/file_artifact"
#: the fault family of the qualification plan (FM2-FILE), each row with the tests that inject it
FAULT_ROWS = {
    "FM2-FILE-1": ("git absent: a probe constructed without a git binary refuses every observation (HARNESS_FAILED "
                   "-> UNRUNNABLE)", ["test_FM2_FILE_1_a_probe_constructed_without_git_refuses_every_observation"]),
    "FM2-FILE-2": ("revision not in the repository: HARNESS_FAILED, never SUBJECT_ABSENT",
                   ["test_FM2_FILE_2_a_revision_the_repository_does_not_hold_is_a_harness_failure_never_absence"]),
    "FM2-FILE-3": ("a binary file under a text grep is skipped and recorded; a file that is not UTF-8 leaves the "
                   "count unestablished (REFUTED, the file named)",
                   ["test_FM2_FILE_3_a_binary_file_under_a_text_grep_is_skipped_and_recorded",
                    "test_FM2_FILE_3_a_file_that_is_not_utf8_leaves_the_count_unestablished"]),
    "FM2-FILE-4": ("regex pattern over the cap: HARNESS_FAILED, never a verdict",
                   ["test_FM2_FILE_4_a_pattern_over_the_cap_is_a_harness_failure"]),
    "FM2-FILE-5": ("case-collision paths: read exactly from the tree (both entries readable, a third spelling absent)",
                   ["test_FM2_FILE_5_case_collision_paths_are_read_exactly_from_the_tree"]),
}
ADVERSARIAL = {
    "FA-ADV-1": ("a symlink entry is refused for content and grep and never followed as a component",
                 ["test_FA_ADV_1_a_symlink_entry_is_refused_for_content_and_grep_and_never_followed"]),
    "FA-ADV-2": ("a tree escape (absolute, '..', backslash, drive letter, empty or '.' component) is refused",
                 ["test_FA_ADV_2_a_tree_escape_is_refused"]),
    "FA-ADV-3": ("an always-REFUTED probe of the same shape and identity is not calibrated",
                 ["test_FA_ADV_3_an_always_REFUTED_probe_of_the_same_shape_is_not_calibrated"]),
}
CASES = {"FA-1": "test_FA_1_", "FA-2": "test_FA_2_", "FA-3": "test_FA_3_", "FA-Q0": "test_FA_Q0_"}
_TEST_LINE = re.compile(r"^(test_\w+) \((\S+)\)(?: \(.*\))? \.\.\. (ok|FAIL|ERROR|skipped.*|expected failure|unexpected success)$")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _norm(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def _identity(path: pathlib.Path) -> dict:
    data = _norm(path.read_bytes())
    return {"sha256": _sha(data), "git_blob": hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()}


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, encoding="utf-8", check=True).stdout.strip()


def _load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _module(name: str, path: pathlib.Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def render(record: dict) -> str:
    return json.dumps(record, indent=1, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------------------- identities

def identities() -> dict:
    from aisef2.probe import file_artifact as fa
    cb = _module("aisef_v2_cycle2_baseline", ROOT / "validation" / "v2" / "cycle2_baseline.py")
    rfc = _load("closure-evidence/v2/AISEF-V2-FREEZE-MANIFEST.json")
    return {
        "package": PACKAGE, "phase": PHASE,
        "parent": {"commit": PARENT, "aisef2_tree": _git("rev-parse", f"{PARENT}:aisef2")},
        "candidate": {"commit": _git("rev-parse", "HEAD"), "aisef2_tree": _git("rev-parse", "HEAD:aisef2")},
        "probe": {"id": fa.PROBE_ID, "digest": fa.DIGEST, "classes": list(fa.CLASSES),
                  "enforcement": fa.FileArtifactProbe().enforcement().value, "weakest_path": fa.WEAKEST_PATH,
                  "sources": {f"aisef2/{rel}": _identity(ROOT / "aisef2" / rel) for rel in fa.PROBE_SOURCES},
                  "digest_rule": "sha256 over '<source rel>\\0<LF-normalised bytes>\\0' for each of PROBE_SOURCES, in order"},
        "cycle1": {"semantic_candidate": cb.PARENT_COMMIT, "aisef2_tree": cb.PARENT_AISEF2_TREE,
                   "closing_commit": cb.CYCLE1_CLOSING_COMMIT, "probe": dict(cb.CYCLE1_PROBE)},
        "cycle2_manifest": {"path": cb.MANIFEST_REL, "sha256": _identity(ROOT / cb.MANIFEST_REL)["sha256"]},
        "cycle2_freeze_manifest": {"path": cb.OUT_REL, "sha256": _identity(ROOT / cb.OUT_REL)["sha256"]},
        "owner_decisions": {"path": cb.DECISIONS_REL, "sha256": _identity(ROOT / cb.DECISIONS_REL)["sha256"]},
        "rfc": {k: rfc.get(k) for k in ("rfc_normative_digest", "freeze_table_digest")},
        "hash_rule": "every sha256 here is over bytes with CRLF normalised to LF; git_blob = sha1 of the blob header "
                     "and the same bytes",
    }


# --------------------------------------------------------------------------------------- calibration

def calibrations() -> tuple[list[dict], list[str]]:
    """REALLY run `calibrate()` for every class over the committed fixtures; the record per class carries the
    read path each fixture exercised (from the probe's own detail) and the verdict observed on each side."""
    from aisef2.probe import file_artifact as fa
    from aisef2.probe.calibration import FIXTURE_REVISION, NotQualified, calibrate, calibration_env, fixture_spec
    from aisef2.probe.protocol import ProbeRegistry, RevisionRef
    probe, env, registry = fa.FileArtifactProbe(), calibration_env(sys.executable), ProbeRegistry([fa.METADATA])
    base = ROOT / FIXTURES_REL
    out, problems = [], []
    for cls in fa.CLASSES:
        pos, neg = base / cls / "positive", base / cls / "negative"
        names = (f"{FIXTURES_REL}/{cls}/positive", f"{FIXTURES_REL}/{cls}/negative")
        try:
            rec = calibrate(probe, cls, pos, neg, env, time.time, registry=registry, names=names)
        except NotQualified as e:
            problems.append(f"{cls}: {e}")
            continue
        sides = {}
        for side, fixture in (("positive", pos), ("negative", neg)):
            o = probe.observe(fixture_spec(probe, fixture), RevisionRef(FIXTURE_REVISION, str((fixture / "checkout").resolve())), env)
            detail = json.loads(o.detail[o.detail.index("{"):])
            sides[side] = {"kind": o.kind.value, "verdict": o.verdict.value, "read_path": detail["read"],
                           "facts": {k: v for k, v in detail.items() if k not in ("read", "revision")}}
        out.append({"probe_id": rec.probe_id, "probe_digest": rec.probe_digest, "observation_class": rec.observation_class,
                    "positive_fixture": rec.positive_fixture, "negative_fixture": rec.negative_fixture,
                    "demonstrated_at": rec.demonstrated_at, "observed": sides,
                    "note": "a committed fixture directory is not a repository top level, so the probe read the "
                            "directory tree at the fixture's checkout (read_path 'directory'); the object-store read "
                            "path is exercised by the test module on real repositories (FA-1)"})
    return out, problems


def fixture_identities() -> dict:
    base = ROOT / FIXTURES_REL
    return {p.relative_to(ROOT).as_posix(): _identity(p) for p in sorted(base.rglob("*")) if p.is_file()}


# --------------------------------------------------------------------------------------- the test module

def run_tests() -> dict:
    """The probe's test module, verbose, in a subprocess under the owned-process discipline
    (validation/v2/owned_run.py): the counts, the verdict, every test's outcome, and the residual counts."""
    argv = [sys.executable, "-P", "validation/v2/owned_run.py", "--", sys.executable, "-m", "unittest", "-v", TEST_MODULE]
    p = subprocess.run(argv, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
    text = (p.stdout or "") + "\n" + (p.stderr or "")
    ran = re.search(r"Ran (\d+) tests? in ([\d.]+)s", text)
    outcomes = {}
    for line in text.splitlines():
        m = _TEST_LINE.match(line.strip())
        if m:
            outcomes[m.group(1)] = m.group(3)
    owned = re.search(r"owned processes: before=(\d+) at_exit=(\d+) after=(\d+) escaped=(\d+) released_empty=(\w+)", text)
    verdict = "OK" if re.search(r"^OK(?: \(.*\))?$", text, re.M) else ("FAILED" if "FAILED" in text else "UNKNOWN")
    return {"argv": argv[1:], "exit": p.returncode, "ran": int(ran.group(1)) if ran else None,
            "seconds": float(ran.group(2)) if ran else None, "verdict": verdict,
            "failures": sorted(set(re.findall(r"^(?:FAIL|ERROR): (\S+)", text, re.M))),
            "skipped": sorted(t for t, o in outcomes.items() if o.startswith("skipped")),
            "outcomes": outcomes,
            "owned_processes": {"before": int(owned.group(1)), "at_exit": int(owned.group(2)), "after": int(owned.group(3)),
                                "escaped": int(owned.group(4)), "released_empty": owned.group(5) == "True"} if owned else None,
            "tail": text.strip().splitlines()[-6:]}


def rows_of(table: dict, outcomes: dict) -> list[dict]:
    return [{"id": rid, "fault" if rid.startswith("FM2") else "case": desc,
             "tests": [{"test": t, "outcome": outcomes.get(t, "NOT RUN")} for t in tests],
             "held": all(outcomes.get(t) == "ok" for t in tests)}
            for rid, (desc, tests) in table.items()]


def cases_of(outcomes: dict) -> dict:
    return {cid: {"tests": {t: o for t, o in outcomes.items() if t.startswith(prefix)},
                  "held": bool([t for t in outcomes if t.startswith(prefix)])
                  and all(o == "ok" for t, o in outcomes.items() if t.startswith(prefix))}
            for cid, prefix in CASES.items()}


# --------------------------------------------------------------------------------------- mutation and static checks

def mutation_summary() -> tuple[dict, list[str]]:
    mu = _module("aisef_v2_mutation", ROOT / "validation" / "v2" / "mutation.py")
    path = ROOT / MUTATION_REL
    if not path.is_file():
        return {"record": MUTATION_REL, "missing": True}, [f"{MUTATION_REL} is missing: run the C2-P1 mutation targets"]
    record = _load(MUTATION_REL)
    targets = [t for t in record["targets"] if t["target"] in mu.PHASE_TARGETS[PHASE]]
    problems = mu.problems_of(record, ROOT, PHASE)
    survivors = [{"target": t["target"], "mutant": m, "audited": (t["target"], m) in mu.AUDITED}
                 for t in targets for m in t.get("survivors", [])]
    return {"record": MUTATION_REL, "sha256": _identity(path)["sha256"], "targets": len(targets),
            "declared_targets": len(mu.PHASE_TARGETS[PHASE]),
            "mutants": sum(t.get("mutants", 0) for t in targets), "killed": sum(t.get("killed", 0) for t in targets),
            "killed_by_timeout": sum(t.get("killed_by_timeout", 0) for t in targets),
            "survivors": survivors, "per_target": {t["target"]: f"{t.get('killed')}/{t.get('mutants')}" for t in targets},
            "kill_tests": sorted({k for t in targets for k in t.get("kill_tests", [])})}, problems


def static_checks() -> tuple[dict, list[str]]:
    from aisef2.arch.enums import SubjectKind
    from aisef2.probe import catalog, file_artifact as fa, python_callable as pc
    ps = _module("aisef_v2_probe_static_checks", ROOT / "validation" / "v2" / "probe_static_checks.py")
    cb = _module("aisef_v2_cycle2_baseline", ROOT / "validation" / "v2" / "cycle2_baseline.py")
    da = _module("aisef_v2_destructive_authority", ROOT / "validation" / "v2" / "destructive_authority.py")
    ks = _module("aisef_v2_kernel_static_checks", ROOT / "validation" / "v2" / "kernel_static_checks.py")
    e = catalog.entry_for(PROBE_REL)
    src = (ROOT / PROBE_REL).read_text(encoding="utf-8")
    results = {
        "probe_rules": ps.check(ROOT),
        "probe_module_violations": ps.violations(PROBE_REL, src, ps.SOURCE_RULES,
                                                 {"subject_process": e.subject_process, "stimulus_shape": e.stimulus_shape} if e else None),
        "cycle2_baseline": cb.check(),
        "destructive_authority": da.check(ROOT),
        "kernel_rules": ks.check(ROOT),
        "catalog_entry": None if e is None else {
            "probe_id": e.probe_id, "probe_digest": e.probe_digest, "subject_kind": e.subject_kind.value,
            "classes": list(e.classes), "fixture_root": e.fixture_root, "subject_process": e.subject_process,
            "protocol_channel": e.protocol_channel, "stimulus_shape": e.stimulus_shape, "cycle": e.cycle, "active": e.active},
        "one_active_probe_for_file_artifact": [x.probe_id for x in catalog.CATALOG
                                               if x.active and x.subject_kind is SubjectKind.FILE_ARTIFACT] == [fa.PROBE_ID],
        "cycle1_probe_sources_unchanged": pc.DIGEST == cb.CYCLE1_PROBE["digest"],   # R2: the live digest is the frozen one
    }
    problems = [f"{name}: {found}" for name in ("probe_rules", "probe_module_violations", "cycle2_baseline",
                                                 "destructive_authority", "kernel_rules") if (found := results[name])]
    if e is None:
        problems.append(f"{PROBE_REL} is not registered in aisef2/probe/catalog.py")
    elif (e.probe_id, e.probe_digest) != (fa.PROBE_ID, fa.DIGEST):
        problems.append("the catalog entry's identity is not the module's")
    if not results["one_active_probe_for_file_artifact"]:
        problems.append("file_artifact does not have exactly one active probe")
    if not results["cycle1_probe_sources_unchanged"]:
        problems.append("a Cycle-1 probe source changed (R2)")
    return results, problems


# --------------------------------------------------------------------------------------- the record

def run() -> dict:
    import platform
    cal, problems = calibrations()
    tests = run_tests()
    if tests["verdict"] != "OK" or tests["exit"] != 0:
        problems.append(f"the test module did not pass: exit {tests['exit']}, {tests['verdict']}, {tests['failures']}")
    if tests["owned_processes"] is None:
        problems.append("the owned-process measurement line was not found")
    elif tests["owned_processes"]["after"] or tests["owned_processes"]["escaped"] or not tests["owned_processes"]["released_empty"]:
        problems.append(f"residual processes after the test module: {tests['owned_processes']}")
    faults = rows_of(FAULT_ROWS, tests["outcomes"])
    adversarial = rows_of(ADVERSARIAL, tests["outcomes"])
    cases = cases_of(tests["outcomes"])
    for row in faults + adversarial:
        if not row["held"]:
            problems.append(f"{row['id']}: {row['tests']}")
    for cid, c in cases.items():
        if not c["held"]:
            problems.append(f"{cid}: {c['tests'] or 'no test carries its prefix'}")
    mutation, mproblems = mutation_summary()
    problems += mproblems
    static, sproblems = static_checks()
    problems += sproblems
    record = {
        "record": "AISEF V2 — WP-2.1.1 FILE_ARTIFACT PROBE CALIBRATION (C2-P1)",
        "work_package": PACKAGE, "phase": PHASE,
        "identities": identities(),
        "platform": {"python": sys.version.split()[0], "platform": sys.platform, "machine": platform.machine(),
                     "git": subprocess.run(["git", "--version"], capture_output=True, encoding="utf-8").stdout.strip()},
        "read_path_rule": ("content, existence and matches are read from the object store at RevisionRef.sha when "
                           "the checkout root is itself a repository top level (git's own discovery, ceilinged at "
                           "the root's parent); a root that is not one (a committed fixture directory) is read as a "
                           "directory tree with the same refusal rules; the SHA's value never enters the decision"),
        "calibrations": cal,
        "fixtures": fixture_identities(),
        "tests": tests,
        "cases": cases,
        "fault_family": faults,
        "adversarial": adversarial,
        "mutation": mutation,
        "static": static,
        "problems": problems,
        "verdict": "CALIBRATED: 3/3 classes, tests OK, mutation killed or audited, static PASS" if not problems else "NOT QUALIFIED",
    }
    return record


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, encoding="utf-8", check=True).stdout


def bind_ci(run_id: int) -> dict:
    """Bind the CI measurements of the record's candidate commit: every attempt of the run, every job's conclusion,
    the unittest count read from its log when a log exists (by job id, never by name), and the check-run
    annotations when it does not. The run must be of the commit the record names."""
    rec = _load(OUT_REL)
    head = rec["identities"]["candidate"]["commit"]
    attempts = int(json.loads(_gh("run", "view", str(run_id), "--json", "attempt"))["attempt"])
    out = {"run": run_id, "commit": head, "attempts": []}
    for n in range(1, attempts + 1):
        jobs = json.loads(_gh("api", f"repos/nghinh/aisef/actions/runs/{run_id}/attempts/{n}/jobs"))["jobs"]
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
        "rule": "the candidate commit's CI runs the whole suite, which includes tests/v2/test_c2_file_artifact.py "
                "(the object-store rule, the fault family and the calibration fixtures) on every platform of the "
                "matrix; the probe and fixture bytes it measured are the ones this record binds by digest",
        "ci": out,
        "platforms": sorted({("windows" if "windows" in r["job"] else "linux") for a in out["attempts"] for r in a["jobs"]
                             if r["job"].startswith("unit")}),
    }
    (ROOT / OUT_REL).write_text(render(rec), encoding="utf-8")
    return rec["cross_platform"]


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
    if "--run" in argv:
        rec = run()
        for p in rec["problems"]:
            print("FAIL ", p)
        t, m = rec["tests"], rec["mutation"]
        print(f"calibrations: {len(rec['calibrations'])}/3; tests: {t['verdict']} ran {t['ran']} "
              f"(skipped {len(t['skipped'])}) owned {t['owned_processes']}; mutation: {m.get('killed')}/{m.get('mutants')} "
              f"killed over {m.get('targets')} targets, survivors {len(m.get('survivors', []))}; "
              f"faults held: {sum(r['held'] for r in rec['fault_family'])}/{len(rec['fault_family'])}; "
              f"adversarial held: {sum(r['held'] for r in rec['adversarial'])}/{len(rec['adversarial'])}")
        if rec["problems"]:
            return 1
        (ROOT / OUT_REL).write_text(render(rec), encoding="utf-8")
        print(f"wrote {OUT_REL}: {rec['verdict']}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
