"""C2-P1..P4 integration — the evidence record of the ONE integrated Cycle-2 candidate:
closure-evidence/v2/cycle2/C2-INTEGRATION.json.

The owner's ruling (2026-09-29) integrates the four lanes into one candidate, preserving every lane's history and
evidence identities, resolving only mechanical conflicts, and re-running the Cycle-2 baseline guard, the checker
calibration, F1-F11, the V1 guard, the residual process checks and Linux + Windows CI; any semantic difference stops the
integration. This harness measures exactly that, from the live integrated tree:

    identities   base, integration HEAD, aisef2 tree, every lane head (an ancestor of HEAD) and the merge commits
    preserved    per lane: the probe module blob and every PROBE_SOURCES blob at the lane head == at HEAD; the lane's
                 calibration fixture tree at the lane head == at HEAD; the digest each lane record binds == the live digest
    catalog      every entry (id, digest, kind, active, cycle, declarations); problems_of == []; one active per kind
    calibrations every class of every catalog entry (active and inactive) re-calibrated by the frozen calibrate() here
    tests        every lane test module under validation/v2/owned_run.py (Ran N, OK, owned-process counts)
    checks       cycle2_baseline, probe_static_checks, mutation --check, checker_calibration --check,
                 freeze_conformance --check (F1-F11), v1_evidence_guard --check, destructive_authority, kernel_static_checks,
                 run_history, ruff — each as run, its exit and last line
    histories    every lane history and its closure record by digest

    python -P validation/qualification/c2_integration.py --run            # writes the record; refused on problems
    python -P validation/qualification/c2_integration.py --bind-ci RUN_ID # binds the CI jobs of the record's commit
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
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
OUT_REL = "closure-evidence/v2/cycle2/C2-INTEGRATION.json"
BASE = "77a437609fd59cd3c8d61d28472460ab9aa157f0"
#: phase -> the lane: its final head, its probe module(s), its evidence records, its fixture roots, its test modules
LANES = {
    "C2-P1": {"lane": "LANE A", "head": "ef0ebe9a5bd43ead45620bf8d12fe28ab3dcc441", "packages": ["WP-2.1.1"], "probes": ["aisef2/probe/file_artifact.py"],
              "records": ["closure-evidence/v2/cycle2/P1-FILE-ARTIFACT-CALIBRATION.json"],
              "fixtures": ["tests/v2/fixtures/calibration/file_artifact"],
              "tests": ["tests.v2.test_c2_file_artifact"]},
    "C2-P2": {"lane": "LANE B", "head": "e063b76fd1cc625211dca1f8b64db9742e566e6a", "packages": ["WP-2.2.1", "WP-2.2.2"],
              "probes": ["aisef2/probe/cli_invocation.py"],
              "records": ["closure-evidence/v2/cycle2/P2-CLI-HARNESS.json", "closure-evidence/v2/cycle2/P2-CLI-CALIBRATION.json"],
              "fixtures": ["tests/v2/fixtures/calibration/cli_invocation"],
              "tests": ["tests.v2.test_c2_cli_protocol", "tests.v2.test_c2_cli_verdicts", "tests.v2.test_c2_cli_invocation",
                        "tests.v2.test_c2_cli_calibration"]},
    "C2-P3": {"lane": "LANE D", "head": "099e019fb579cf2b400f72d15038c56b0f9f8f2a", "packages": ["WP-2.3.1", "WP-2.3.2"],
              "probes": ["aisef2/probe/process_effect.py"],
              "records": ["closure-evidence/v2/cycle2/P3-EFFECT-HARNESS.json", "closure-evidence/v2/cycle2/P3-EFFECT-CALIBRATION.json"],
              "fixtures": ["tests/v2/fixtures/calibration/process_effect"],
              "tests": ["tests.v2.test_probe_process_effect_units", "tests.v2.test_probe_process_effect",
                        "tests.v2.test_probe_process_effect_bytecode", "tests.v2.test_c2_effect_calibration"]},
    "C2-P4": {"lane": "LANE C", "head": "e4e02ff40564ce9cc12ac8088ec8780fa87a4b8e", "packages": ["WP-2.4.1"], "probes": ["aisef2/probe/python_callable_v2.py"],
              "records": ["closure-evidence/v2/cycle2/P4-PYTHON-CALLABLE-V2-CALIBRATION.json"],
              "fixtures": ["tests/v2/fixtures/calibration/python_callable_v2"],
              "tests": ["tests.v2.test_python_callable_v2", "tests.v2.test_python_callable_v2_bytecode"]},
}
CHECKS = (
    ["validation/v2/cycle2_baseline.py", "--check"],
    ["validation/v2/probe_static_checks.py", "--check"],
    ["validation/v2/mutation.py", "--check"],
    ["validation/v2/checker_calibration.py", "--check"],
    ["validation/v2/freeze_conformance.py", "--check"],
    ["validation/v2/v1_evidence_guard.py", "--check"],
    ["validation/v2/destructive_authority.py", "--check"],
    ["validation/v2/kernel_static_checks.py"],
    ["validation/v2/run_history.py"],
)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, encoding="utf-8", check=True).stdout.strip()


def _blob(rev: str, rel: str) -> str | None:
    r = subprocess.run(["git", "rev-parse", f"{rev}:{rel}"], cwd=ROOT, capture_output=True, encoding="utf-8")
    return r.stdout.strip() if r.returncode == 0 else None


def _identity(path: pathlib.Path) -> dict:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return {"sha256": hashlib.sha256(data).hexdigest(), "git_blob": hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()}


def _module(name: str, path: pathlib.Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _record_digest(rec: dict) -> str | None:
    """The probe digest a lane record binds, whichever of the lanes' two identity shapes it uses."""
    ids = rec.get("identities", {})
    return (ids.get("probe") or {}).get("digest") or (rec.get("probe") or {}).get("digest")


# --------------------------------------------------------------------------------------- identities and preservation

def identities() -> dict:
    head = _git("rev-parse", "HEAD")
    return {"base": BASE, "head": head, "aisef2_tree": _git("rev-parse", "HEAD:aisef2"),
            "base_aisef2_tree": _git("rev-parse", f"{BASE}:aisef2"),
            "merges": _git("rev-list", "--merges", "--reverse", f"{BASE}..HEAD").split(),
            "lanes": {ph: {"lane": ln["lane"], "head": ln["head"],
                           "is_ancestor": subprocess.run(["git", "merge-base", "--is-ancestor", ln["head"], "HEAD"],
                                                         cwd=ROOT).returncode == 0,
                           "commits": _git("rev-list", "--count", f"{BASE}..{ln['head']}")}
                      for ph, ln in LANES.items()}}


def preservation() -> dict:
    """Per lane: the probe module, every source its digest covers, its fixtures and its records are the lane head's
    bytes (git objects), and every record's probe digest is the live digest: the integration changed none of them."""
    out = {}
    for ph, ln in LANES.items():
        rows = []
        for rel in ln["probes"]:
            mod = importlib.import_module(rel[:-3].replace("/", "."))
            for src in {rel, *(f"aisef2/{s}" for s in mod.PROBE_SOURCES)}:
                rows.append({"path": src, "lane": _blob(ln["head"], src), "integrated": _blob("HEAD", src)})
            rows.append({"path": f"{rel} DIGEST", "lane": None, "integrated": mod.DIGEST})
        for rel in ln["fixtures"] + ln["records"]:
            rows.append({"path": rel, "lane": _blob(ln["head"], rel), "integrated": _blob("HEAD", rel)})
        digests = {}
        live = {rel: importlib.import_module(rel[:-3].replace("/", ".")).DIGEST for rel in ln["probes"]}
        for rel in ln["records"]:
            digests[rel] = {"bound": _record_digest(json.loads((ROOT / rel).read_text(encoding="utf-8"))),
                            "live": next(iter(live.values()))}
        out[ph] = {"objects": rows, "record_digests": digests,
                   "preserved": all(r["lane"] == r["integrated"] for r in rows if r["lane"] is not None)
                   and all(d["bound"] == d["live"] for d in digests.values())}
    return out


def cycle1_identity() -> dict:
    cb = _module("aisef_v2_cycle2_baseline", ROOT / "validation" / "v2" / "cycle2_baseline.py")
    from aisef2.probe import python_callable as pc
    sources = {rel: {"parent": _blob(cb.PARENT_COMMIT, rel), "integrated": _blob("HEAD", rel)}
               for rel in ("aisef2/probe/protocol.py", "aisef2/probe/python_callable.py")}
    return {"probe_id": pc.PROBE_ID, "live_digest": pc.DIGEST, "frozen_digest": cb.CYCLE1_PROBE["digest"],
            "digest_unchanged": pc.DIGEST == cb.CYCLE1_PROBE["digest"], "sources": sources,
            "sources_unchanged": all(s["parent"] == s["integrated"] for s in sources.values())}


# --------------------------------------------------------------------------------------- catalog and calibrations

def catalog_state() -> dict:
    from aisef2.probe import catalog
    return {"entries": [{"probe_id": e.probe_id, "probe_digest": e.probe_digest, "subject_kind": e.subject_kind.value,
                         "active": e.active, "cycle": e.cycle, "classes": list(e.classes), "module": e.module,
                         "fixture_root": e.fixture_root, "subject_process": e.subject_process,
                         "protocol_channel": e.protocol_channel, "stimulus_shape": e.stimulus_shape}
                        for e in catalog.CATALOG],
            "problems": catalog.problems_of(catalog.CATALOG),
            "active": {k.value: e.probe_id for k, e in catalog.active().items()}}


def calibrations() -> list[dict]:
    """Every class of every catalog entry, active or not, re-calibrated here by the frozen calibrate()."""
    from aisef2.probe import catalog
    from aisef2.probe.calibration import NotQualified, calibrate, calibration_env
    registry, out = catalog.registry(), []
    for e in catalog.CATALOG:
        base = ROOT / "tests/v2/fixtures/calibration" / e.fixture_root
        for cls in e.classes:
            names = (f"tests/v2/fixtures/calibration/{e.fixture_root}/{cls}/positive",
                     f"tests/v2/fixtures/calibration/{e.fixture_root}/{cls}/negative")
            try:
                rec = calibrate(e.factory(), cls, base / cls / "positive", base / cls / "negative",
                                calibration_env(sys.executable), time.time, registry=registry, names=names)
                out.append({**dataclasses.asdict(rec), "active": e.active, "qualified": True})
            except NotQualified as err:
                out.append({"probe_id": e.probe_id, "observation_class": cls, "active": e.active, "qualified": False,
                            "reason": str(err)})
    return out


# --------------------------------------------------------------------------------------- tests, checks, histories

def run_tests() -> list[dict]:
    out = []
    for ph, ln in LANES.items():
        for module in ln["tests"]:
            with tempfile.TemporaryDirectory(prefix="c2-int-owned-") as t:
                measure = pathlib.Path(t) / "owned.json"
                cmd = [sys.executable, "-P", "validation/v2/owned_run.py", "--out", str(measure), "--",
                       sys.executable, "-m", "unittest", module]
                r = subprocess.run(cmd, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
                owned = json.loads(measure.read_text(encoding="utf-8")) if measure.is_file() else None
            text = r.stdout + r.stderr
            ran = re.search(r"Ran (\d+) tests? in ([\d.]+)s", text)
            out.append({"phase": ph, "module": module, "exit": r.returncode, "ran": int(ran.group(1)) if ran else None,
                        "seconds": float(ran.group(2)) if ran else None,
                        "ok": r.returncode == 0 and bool(re.search(r"^OK", text, re.M)),
                        "failing": sorted(set(re.findall(r"(?:ERROR|FAIL): (\S+) \(", text))),
                        "owned": {k: owned.get(k) for k in ("owned_before", "owned_at_exit", "owned_after", "escaped",
                                                            "released_empty")} if owned else None})
    return out


def run_checks() -> list[dict]:
    out = []
    for argv in CHECKS:
        r = subprocess.run([sys.executable, "-P", *argv], cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
        lines = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip()]
        out.append({"command": ["python", "-P", *argv], "exit": r.returncode, "last_line": lines[-1] if lines else ""})
    ruff = shutil.which("ruff")
    if ruff:
        r = subprocess.run([ruff, "check", "."], cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
        out.append({"command": ["ruff", "check", "."], "exit": r.returncode,
                    "last_line": (r.stdout + r.stderr).strip().splitlines()[-1]})
    return out


def histories() -> dict:
    rh = _module("aisef_v2_run_history", ROOT / "validation" / "v2" / "run_history.py")
    out = {}
    for ph in ("C2-P0", *LANES, "C2-INTEGRATION"):
        rel = rh.HISTORIES.get(ph)
        if rel is None or not (ROOT / rel).exists():
            out[ph] = {"path": rel, "present": False}
            continue
        entries = json.loads((ROOT / rel).read_text(encoding="utf-8"))["entries"]
        seal = rh.SEALS.get(ph)
        out[ph] = {"path": rel, "present": True, "entries": len(entries), "sha256": _identity(ROOT / rel)["sha256"],
                   "failed": [{"seq": e["seq"], "commit": e["commit"][:7], "job": e["job"], "classification": e["classification"]}
                              for e in entries if e["result"] == "FAIL"],
                   "closed_by": {"path": seal, "sha256": _identity(ROOT / seal)["sha256"]} if seal and (ROOT / seal).exists() else None}
    return out


# --------------------------------------------------------------------------------------- the record

def run() -> dict:
    ids, kept, c1, cat = identities(), preservation(), cycle1_identity(), catalog_state()
    cals, tests, checks, hist = calibrations(), run_tests(), run_checks(), histories()
    problems = []
    for ph, ln in ids["lanes"].items():
        if not ln["is_ancestor"]:
            problems.append(f"{ph}: lane head {ln['head'][:12]} is not merged into HEAD")
    for ph, p in kept.items():
        if not p["preserved"]:
            problems.append(f"{ph}: a lane object or a record's probe digest differs in the integrated tree (semantic difference: STOP)")
    if not (c1["digest_unchanged"] and c1["sources_unchanged"]):
        problems.append("the Cycle-1 probe identity changed")
    if cat["problems"]:
        problems.append(f"catalog: {cat['problems']}")
    expected_active = {"python_callable": "probe.python_callable_v2", "file_artifact": "probe.file_artifact",
                       "cli_invocation": "probe.cli_invocation", "process_effect": "probe.process_effect"}
    if cat["active"] != expected_active:
        problems.append(f"catalog active entries {cat['active']} != {expected_active}")
    for c in cals:
        if not c["qualified"]:
            problems.append(f"calibration {c['probe_id']}/{c['observation_class']}: {c['reason']}")
    for t in tests:
        if not t["ok"] or not t["ran"]:
            problems.append(f"{t['module']}: exit {t['exit']}, ran {t['ran']}, failing {t['failing']}")
        if t["owned"] and (t["owned"]["owned_after"] or t["owned"]["escaped"] or not t["owned"]["released_empty"]):
            problems.append(f"{t['module']}: owned-process residual {t['owned']}")
    for c in checks:
        if c["exit"] != 0:
            problems.append(f"{' '.join(c['command'])}: exit {c['exit']} — {c['last_line']}")
    return {
        "record": "AISEF V2 — CYCLE-2 INTEGRATION OF C2-P1, C2-P2, C2-P3, C2-P4 INTO ONE CANDIDATE",
        "id": "AISEF-V2-CYCLE2-INTEGRATION",
        "authority": "owner ruling 'AISEF V2 — CYCLE-2 OWNER RULING / C2-P0 ACCEPTED / AUTHORIZE MAXIMUM SAFE PARALLEL "
                     "EXECUTION' (2026-09-29): integrate P1+P2+P3+P4 into ONE candidate, preserve lane histories and "
                     "evidence identities, resolve only mechanical conflicts, re-run the Cycle-2 baseline, the checker "
                     "calibration, F1-F11, the V1 guard, Linux + Windows CI and the residual process checks; STOP on any "
                     "semantic difference",
        "identities": ids,
        "mechanical_conflicts": {"files": ["aisef2/probe/catalog.py", "validation/v2/mutation.py",
                                           "tests/v2/test_cycle2_wp201.py"],
                                 "rule": "union of the lanes' own registrations (catalog imports and entries; C2 mutation "
                                         "records, target tables and PHASE_TARGETS); the WP-2.0.1 catalog test states the "
                                         "union's truth (the Cycle-1 identity first and inactive at its frozen digest, the "
                                         "second identity active, more kinds active beside it); any other conflict stops"},
        "platform": {"python": sys.version.split()[0], "platform": sys.platform},
        "preservation": kept,
        "cycle1_identity": c1,
        "catalog": cat,
        "calibrations": cals,
        "tests": tests,
        "checks": checks,
        "histories": hist,
        "problems": problems,
        "verdict": "INTEGRATED — NO SEMANTIC DIFFERENCE" if not problems else "NOT INTEGRATED",
    }


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, encoding="utf-8", check=True).stdout


def bind_ci(run_id: int) -> dict:
    rec = json.loads((ROOT / OUT_REL).read_text(encoding="utf-8"))
    head = rec["identities"]["head"]
    attempts = int(json.loads(_gh("run", "view", str(run_id), "--repo", "nghinh/aisef", "--json", "attempt"))["attempt"])
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
            om = re.search(r"owned processes: (before=\d+ at_exit=\d+ after=\d+ escaped=\d+ released_empty=\w+)", text)
            rows.append({"job": j["name"], "job_id": j["id"], "conclusion": j["conclusion"],
                         "started_at": j["started_at"], "completed_at": j["completed_at"],
                         "tests_run": int(m.group(1)) if m else None, "log_available": available,
                         "failing_tests": sorted(set(re.findall(r"(?:ERROR|FAIL): \S+ \((\S+)\)", text))) if available else [],
                         "owned_processes": om.group(1) if om else None,
                         "v1_guard": bool(re.search(r"V1 evidence guard \(DETECTIVE\): PASS", text)),
                         "v1_pf_001_lines": len(re.findall(r"_kill_tree_win32|MemoryError", text))})
        out["attempts"].append({"attempt": n, "jobs": rows})
    rec["cross_platform"] = {"rule": "the integrated candidate's CI runs the whole suite — every lane's tests included — on "
                                     "Linux 3.11-3.14 and Windows 3.11", "ci": out}
    (ROOT / OUT_REL).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
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
        print(f"head {rec['identities']['head'][:12]} aisef2 {rec['identities']['aisef2_tree'][:12]}; "
              f"calibrations {sum(c['qualified'] for c in rec['calibrations'])}/{len(rec['calibrations'])}; "
              f"tests {sum(t['ok'] for t in rec['tests'])}/{len(rec['tests'])} modules; "
              f"checks {sum(c['exit'] == 0 for c in rec['checks'])}/{len(rec['checks'])}; verdict {rec['verdict']}")
        if rec["problems"]:
            return 1
        (ROOT / OUT_REL).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {OUT_REL}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
