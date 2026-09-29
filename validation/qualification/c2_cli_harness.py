"""WP-2.2.1 — evidence for the `cli_invocation` probe harness: closure-evidence/v2/cycle2/P2-CLI-HARNESS.json.

    --run            run the harness test module under the owned-process gate, the DESIGN-CHECK-1 matrix, the fault
                     rows and the static checks; bind every identity; write the record (refused on any problem)
    --bind-ci RUN    bind the CI measurements of the record's commit (every attempt, every job, per job id)

The record binds: the package and its parent commit, the candidate commit and its aisef2 tree, the probe identity
(id, digest, the digest of each source), the Cycle-1 identities of validation/v2/cycle2_baseline.py, the platform,
the test-module result run as `python -P validation/v2/owned_run.py -- python -m unittest <module>` (Ran N, OK,
owned-process counts), the DESIGN-CHECK-1 matrix (variant x repetition -> (kind, verdict, hard_exit), all equal per
variant), the fault rows FM2-CLI-HARNESS-1..4, FM2-CLI-SUBJECT-1..6, FM2-CLI-STREAM-1..5 and FM2-PYC-CLI-1..4 with
their outcomes (read from a second, in-process run of the same module), the C2-P2 mutation summary, the static checks
and the design notes.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT_REL = "closure-evidence/v2/cycle2/P2-CLI-HARNESS.json"
MUTATION_REL = "closure-evidence/v2/cycle2/P2-MUTATION.json"
PACKAGE = "WP-2.2.1"
PARENT = "77a437609fd59cd3c8d61d28472460ab9aa157f0"
PROBE_REL = "aisef2/probe/cli_invocation.py"
TEST_MODULES = ("tests.v2.test_c2_cli_invocation", "tests.v2.test_c2_cli_verdicts")
FAULT_ROWS = {
    **{f"FM2-CLI-HARNESS-{n}": f"test_FM2_CLI_HARNESS_{n}_" for n in range(1, 5)},
    **{f"FM2-CLI-SUBJECT-{n}": f"test_FM2_CLI_SUBJECT_{n}_" for n in range(1, 7)},
    **{f"FM2-CLI-STREAM-{n}": f"test_FM2_CLI_STREAM_{n}_" for n in range(1, 6)},
    **{f"FM2-PYC-CLI-{n}": f"test_FM2_PYC_CLI_{n}_" for n in range(1, 5)},
}
CLI_CASES = {f"CLI-{n}": f"test_CLI_{n}_" for n in (*range(1, 10), "Q0")}
DESIGN_NOTES = [
    "protocol channel: a harness-owned marker file inside the evaluation directory on every platform (the taxonomy "
    "proposal suggested fd 3 on POSIX; the owned process range launches the target through an anchor that forwards "
    "no extra descriptor, and the runtime is out of scope) — a design choice inside F5, not an exception",
    "the subject's stdout and stderr are redirected at the descriptor level onto capture files, one pair per "
    "invocation; a protocol line the subject writes to stdout is captured bytes, never protocol",
    "the parent polls the marker file (complete lines, mark and nonce only; an unterminated last line is never a "
    "line), asks the range for the exit with a non-blocking wait at each poll, and re-reads the file to its end "
    "after the exit before concluding (RFC §9.4 applied to the file)",
    "the watchdog runs until DISPATCHED; the spec's window until RESULT; at the window's end the process's presence "
    "is measured on the range (members) before SUBJECT_DEADLINE is concluded; a hard exit (no RESULT, an exit "
    "status) is OBSERVED with the process's exit code and the capture files as the streams; a signal exit is "
    "NON_CONTROLLER_SIGNAL unless the controller's ledger holds the signal (ProbeInterrupted)",
    "UTF-8 mode is pinned on the command line (-X utf8=1) beside the bytecode prefix, because -I discards every "
    "PYTHON* variable (the P7-FINDING-001 lesson applied to the locale row of the hidden-authority matrix)",
    "the tests live at the tests/v2 root (test_c2_cli_invocation.py, test_c2_cli_verdicts.py): the test tiers are a "
    "closed enum of the frozen invariant registry, and a new package under tests/v2 fails registration",
    "the calibration fixtures (tests/v2/fixtures/calibration/cli_invocation/<class>/{positive,negative}) are "
    "committed with the harness because Q0 PROBE_CATALOG_CLOSURE requires them for every class of a registered "
    "probe; their calibration records are WP-2.2.2's",
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


def render(record: dict) -> str:
    return json.dumps(record, indent=1, ensure_ascii=False) + "\n"


def identities() -> dict:
    cb = _module("aisef_v2_cycle2_baseline", ROOT / "validation" / "v2" / "cycle2_baseline.py")
    from aisef2.probe import catalog, cli_invocation as ci
    entry = catalog.entry_for(PROBE_REL)
    return {
        "package": PACKAGE, "parent": PARENT,
        "head": _git("rev-parse", "HEAD"), "aisef2_tree": _git("rev-parse", "HEAD:aisef2"),
        "probe": {"id": ci.PROBE_ID, "digest": ci.DIGEST, "classes": list(ci.CLASSES),
                  "sources": {rel: _identity(ROOT / "aisef2" / rel) for rel in ci.PROBE_SOURCES},
                  "catalog": {"subject_kind": entry.subject_kind.value, "subject_process": entry.subject_process,
                              "protocol_channel": entry.protocol_channel, "stimulus_shape": entry.stimulus_shape,
                              "cycle": entry.cycle, "active": entry.active},
                  "on_deadline": {k: v.value for k, v in ci.ON_DEADLINE.items()},
                  "enforcement": "PARTIAL", "weakest_path": ci.WEAKEST_PATH, "stream_cap": ci.STREAM_CAP},
        "tests": {m: _identity(ROOT / (m.replace(".", "/") + ".py")) for m in TEST_MODULES},
        "cycle1": {"semantic_candidate": cb.PARENT_COMMIT, "aisef2_tree": cb.PARENT_AISEF2_TREE,
                   "probe": dict(cb.CYCLE1_PROBE)},
        "cycle2_freeze_manifest": {"path": cb.OUT_REL, "sha256": _identity(ROOT / cb.OUT_REL)["sha256"]},
        "owner_decisions": {"path": cb.DECISIONS_REL, "sha256": _identity(ROOT / cb.DECISIONS_REL)["sha256"]},
        "hash_rule": "every sha256 here is over bytes with CRLF normalised to LF; git_blob = sha1 of the blob header "
                     "and the same bytes",
    }


# --------------------------------------------------------------------------------------- measurements

def owned_run(module: str) -> dict:
    """The module under the owned-process gate: `Ran N`, OK/FAILED, the owned-process line, exit status."""
    cmd = [sys.executable, "-P", str(ROOT / "validation" / "v2" / "owned_run.py"), "--", sys.executable, "-m",
           "unittest", module]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
    text = r.stdout + r.stderr
    ran = re.search(r"Ran (\d+) tests? in ([\d.]+)s", text)
    owned = re.search(r"owned processes: (.*)$", text, re.M)
    status = re.search(r"^(OK|FAILED)(?: \((.*)\))?$", text, re.M)
    return {"command": cmd[2:], "exit": r.returncode, "ran": int(ran.group(1)) if ran else None,
            "seconds": float(ran.group(2)) if ran else None, "status": status.group(1) if status else None,
            "status_detail": status.group(2) if status and status.group(2) else "",
            "owned_processes": owned.group(1) if owned else None,
            "residual": None if not owned else int(re.search(r"after=(\d+)", owned.group(1)).group(1))}


def in_process(module: str) -> dict[str, str]:
    """Every test of `module` by outcome (PASS / FAIL / ERROR / SKIP: reason), from one in-process run."""
    suite = unittest.defaultTestLoader.loadTestsFromName(module)
    out: dict[str, str] = {}

    def walk(s):
        for t in s:
            if isinstance(t, unittest.TestSuite):
                walk(t)
            else:
                out[t.id()] = "PASS"
    walk(suite)   # before the run: a suite drops its tests once they have run
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    for t, _ in result.failures:
        out[t.id()] = "FAIL"
    for t, _ in result.errors:
        out[t.id()] = "ERROR"
    for t, reason in result.skipped:
        out[t.id()] = f"SKIP: {reason}"
    return out


def rows_of(outcomes: dict[str, str], table: dict[str, str]) -> dict[str, dict]:
    out = {}
    for row, prefix in table.items():
        hits = {k: v for k, v in outcomes.items() if k.rsplit(".", 1)[-1].startswith(prefix)}
        out[row] = {"tests": sorted(hits), "outcome": next(iter(hits.values())) if len(hits) == 1
                    else ("PASS" if hits and all(v == "PASS" for v in hits.values()) else "MISSING" if not hits
                          else "; ".join(f"{k.rsplit('.', 1)[-1]}={v}" for k, v in sorted(hits.items())))}
    return out


def design_check_1(reps: int = 3) -> dict:
    from tests.v2 import test_c2_cli_invocation as t
    from aisef2.probe.protocol import RevisionRef
    at = RevisionRef(t.SHA, t.checkout(t.PRODUCT))
    matrix = t.design_check_1(at, reps=reps)
    return {"repetitions": reps,
            "variants": {name: {"observed": [list(x) for x in seen], "expected": list(t.EXPECTED_DESIGN_CHECK_1[name]),
                                "all_equal": len(set(seen)) == 1 and seen[0] == t.EXPECTED_DESIGN_CHECK_1[name]}
                         for name, seen in matrix.items()},
            "all_equal": all(len(set(seen)) == 1 and seen[0] == t.EXPECTED_DESIGN_CHECK_1[name]
                             for name, seen in matrix.items()),
            "rule": "per variant, every repetition reports the same (kind, verdict, hard_exit); the variants differ "
                    "only in how the subject's exit is scheduled against the marker file's last write"}


def static_checks() -> dict:
    ps = _module("aisef_v2_probe_static_checks", ROOT / "validation" / "v2" / "probe_static_checks.py")
    cb = _module("aisef_v2_cycle2_baseline", ROOT / "validation" / "v2" / "cycle2_baseline.py")
    return {"probe_static_checks": ps.check(ROOT), "cycle2_baseline": cb.check()}


def mutation_summary() -> dict:
    mu = _module("aisef_v2_mutation", ROOT / "validation" / "v2" / "mutation.py")
    path = ROOT / MUTATION_REL
    if not path.is_file():
        return {"record": MUTATION_REL, "present": False, "problems": [f"{MUTATION_REL} is missing"]}
    rec = json.loads(path.read_text(encoding="utf-8"))
    targets = [t for t in rec["targets"] if t["target"].startswith(PROBE_REL)]
    return {"record": MUTATION_REL, "present": True, "phase": "C2-P2",
            "targets": len(targets), "mutants": sum(t.get("mutants", 0) for t in targets),
            "killed": sum(t.get("killed", 0) for t in targets),
            "killed_by_timeout": sum(t.get("killed_by_timeout", 0) for t in targets),
            "survivors": {t["target"]: t["survivors"] for t in targets if t.get("survivors")},
            "errors": {t["target"]: t["error"] for t in targets if t.get("error")},
            "problems": mu.problems_of(rec, ROOT, "C2-P2"),
            "per_target": {t["target"].split("::")[1]: {"mutants": t.get("mutants"), "killed": t.get("killed"),
                                                        "kill_tests": t.get("kill_tests")} for t in targets}}


def run() -> dict:
    problems: list[str] = []
    runs = {m: owned_run(m) for m in TEST_MODULES}
    for m, r in runs.items():
        if r["status"] != "OK" or r["exit"] != 0 or r["residual"]:
            problems.append(f"{m}: status {r['status']} exit {r['exit']} residual {r['residual']}")
    outcomes = in_process(TEST_MODULES[0])
    fault_rows = rows_of(outcomes, FAULT_ROWS)
    cli_rows = rows_of(outcomes, CLI_CASES)
    for name, rows in (("fault", fault_rows), ("case", cli_rows)):
        for row, r in rows.items():
            if r["outcome"] not in ("PASS",) and not r["outcome"].startswith("SKIP"):
                problems.append(f"{name} row {row}: {r['outcome']}")
    dc1 = design_check_1()
    if not dc1["all_equal"]:
        problems.append("DESIGN-CHECK-1: a variant did not give one result across its repetitions")
    static = static_checks()
    for name, found in static.items():
        if found:
            problems.append(f"{name}: {found}")
    mutation = mutation_summary()
    problems += [f"mutation: {p}" for p in mutation["problems"]]
    return {
        "record": "AISEF V2 — WP-2.2.1 CLI INVOCATION HARNESS (probe.cli_invocation: harness, DESIGN-CHECK-1, fault rows)",
        "work_package": PACKAGE,
        "identities": identities(),
        "platform": {"python": sys.version.split()[0], "platform": sys.platform},
        "tests": runs,
        "cases": cli_rows,
        "design_check_1": dc1,
        "fault_rows": fault_rows,
        "mutation": mutation,
        "static": static,
        "design_notes": DESIGN_NOTES,
        "problems": problems,
        "verdict": "HARNESS GREEN" if not problems else "NOT QUALIFIED",
    }


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, encoding="utf-8", check=True).stdout


def bind_ci(run_id: int) -> dict:
    """As validation/qualification/p0_reference_fixture.bind_ci: every attempt of the run, every job by id, the
    unittest count read from its own log, the annotations when there is no log; the run must be of the record's commit."""
    rec = json.loads((ROOT / OUT_REL).read_text(encoding="utf-8"))
    head = rec["identities"]["head"]
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
        "rule": "the record's commit's CI runs the whole unittest discovery, which includes tests/v2/test_c2_cli_invocation.py "
                "and tests/v2/test_c2_cli_verdicts.py on every platform of the matrix",
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
                print(f"attempt {a['attempt']}: {r['job']:32s} {r['conclusion']:8s} tests {r['tests_run']}")
        print(f"bound CI run {cp['ci']['run']} into {OUT_REL}")
        return 0
    if "--run" in argv:
        rec = run()
        for p in rec["problems"]:
            print("FAIL ", p)
        for m, r in rec["tests"].items():
            print(f"{m}: Ran {r['ran']} {r['status']} exit {r['exit']} owned {r['owned_processes']}")
        print(f"DESIGN-CHECK-1 all equal: {rec['design_check_1']['all_equal']}; fault rows: "
              f"{sum(1 for r in rec['fault_rows'].values() if r['outcome'] == 'PASS')}/{len(rec['fault_rows'])} PASS; "
              f"mutation: {rec['mutation'].get('killed')}/{rec['mutation'].get('mutants')} killed, "
              f"survivors {rec['mutation'].get('survivors')}")
        if rec["problems"]:
            return 1
        (ROOT / OUT_REL).write_text(render(rec), encoding="utf-8")
        print(f"wrote {OUT_REL}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
