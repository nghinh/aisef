"""W1-a dry check (offline; no provider, no client, no network). Run from anywhere:

    nice -n 19 /opt/homebrew/bin/python3 -P -B closure-evidence/v2/v2.1/e2/w1-a/dry-check/dry_check.py SCRATCH

1. init_repo.sh twice -> the baseline commit is reproducible (one sha).
2. `aisef bundle seal` of arms/authoring.json and evaluator/authoring.json against that baseline; the sealed,
   UNAPPROVED bundles are written beside their authoring documents (arms/bundle.json, evaluator/bundle.json) when
   they are not there yet, and compared byte for byte when they are.
3. `aisef bundle lint` of both: NOT_READY, and only for `to_approve` (admission is not run on an unapproved bundle).
4. Leak scan: harness.distinctive(evaluator) against docs/requirements.md, baseline/README.md, arms/authoring.json
   and arms/bundle.json the way harness.leaks reads a session stream; and the canonical stimulus/observable parts of
   the two bundles must be disjoint sets.
5. TECHNICAL approvals, in SCRATCH only, by `human:w1a-dry-check` — never the owner's, never committed — so that
   lint can run the nine static admission checks (expected READY) and the probes can run.
6. The probes on a reference candidate (dry-check/reference/ on top of the baseline, committed in SCRATCH) and on the
   bare baseline, with both bundles: harness.evaluate.
Everything observed is written to dry-check/RESULT.json; the exit status is 0 only if every expectation held."""
from __future__ import annotations

import filecmp
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
W1A = HERE.parent
ROOT = HERE.parents[5]      # closure-evidence/v2/v2.1/e2/w1-a/dry-check -> the AISEF repository root
sys.path.insert(0, str(ROOT))

from validation.experiments import harness as H  # noqa: E402

PY = sys.executable
ENV = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
APPROVER = "human:w1a-dry-check"


def sh(*argv, cwd=None, check=True) -> subprocess.CompletedProcess:
    p = subprocess.run(list(argv), cwd=cwd, env=ENV, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise SystemExit(f"FAILED ({p.returncode}): {' '.join(argv)}\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")
    return p


def aisef_bundle(*args, check=True) -> subprocess.CompletedProcess:
    return sh(PY, "-P", "-B", "-m", "aisef", "bundle", *args, cwd=ROOT, check=check)


def read(path) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def parts(bundle: dict) -> set[str]:
    return {json.dumps(p, sort_keys=True) for c in bundle["contracts"] for p in (c["stimulus"], c["observable"])}


def text_hits(marks: list[str], path: pathlib.Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return [m for m in marks if m in text or m.replace('"', '\\"') in text]


def approve_all(bundle_path: pathlib.Path, out_dir: pathlib.Path, stem: str) -> pathlib.Path:
    doc = read(bundle_path)
    here = bundle_path
    for n, c in enumerate(doc["contracts"], 1):
        nxt = out_dir / f"{stem}.approved-{n}.json"
        aisef_bundle("approve", str(here), "--contract", c["id"], "--approver", APPROVER, "--out", str(nxt))
        here = nxt
    return here


def main(scratch: pathlib.Path) -> int:
    scratch.mkdir(parents=True, exist_ok=True)
    result: dict = {"started": time.strftime("%Y-%m-%d %H:%M:%S %z"), "python": sys.version.split()[0],
                    "aisef_head": sh("git", "rev-parse", "HEAD", cwd=ROOT).stdout.strip(), "ok": True}
    problems: list[str] = []

    def expect(cond: bool, what: str) -> None:
        if not cond:
            problems.append(what)

    # 1. reproducible baseline
    shas = []
    for name in ("base-1", "base-2"):
        d = scratch / name
        shutil.rmtree(d, ignore_errors=True)
        shas.append(sh("sh", str(W1A / "init_repo.sh"), str(d)).stdout.strip().splitlines()[-1])
    base = scratch / "base-1"
    result["baseline"] = {"commit": shas[0], "reproducible": shas[0] == shas[1],
                          "clean": sh("git", "status", "--porcelain", cwd=base).stdout == "",
                          "files": sh("git", "ls-tree", "-r", "--name-only", "HEAD", cwd=base).stdout.split()}
    expect(result["baseline"]["reproducible"], "init_repo.sh is not reproducible")
    expect(result["baseline"]["clean"], "the baseline working tree is not clean")
    result["baseline"]["source_identity"] = H.source_identity(base, "HEAD")

    # 2. seal
    sealed: dict[str, pathlib.Path] = {}
    for which in ("arms", "evaluator"):
        out = scratch / f"{which}.sealed.json"
        out.unlink(missing_ok=True)
        rep = json.loads(aisef_bundle("seal", str(W1A / which / "authoring.json"), "--repo", str(base), "--out", str(out)).stdout)
        committed = W1A / which / "bundle.json"
        if not committed.exists():
            shutil.copyfile(out, committed)
        same = filecmp.cmp(out, committed, shallow=False)
        result[f"seal_{which}"] = {k: rep[k] for k in ("plan_hash", "specs", "approvals_kept", "to_approve")}
        result[f"seal_{which}"]["to_approve"] = len(rep["to_approve"])
        result[f"seal_{which}"]["committed_bundle_matches_fresh_seal"] = same
        result[f"seal_{which}"]["bundle_sha256"] = H.sha(committed.read_bytes())
        result[f"seal_{which}"]["plan_baseline"] = read(committed)["plan"]["baseline"]
        expect(same, f"{which}/bundle.json differs from a fresh seal")
        expect(read(committed)["plan"]["baseline"] == shas[0], f"{which}/bundle.json names another baseline")
        sealed[which] = committed

    # 3. lint, unapproved
    for which in ("arms", "evaluator"):
        p = aisef_bundle("lint", str(sealed[which]), check=False)
        rep = json.loads(p.stdout)
        result[f"lint_{which}_unapproved"] = {"exit": p.returncode, "verdict": rep["verdict"], "to_approve": len(rep["to_approve"]),
                                              "admission": rep["admission"], "criteria_without_calibration": rep["criteria_without_calibration"],
                                              "criteria_without_contract": rep["criteria_without_contract"],
                                              "uncovered": [r for r, v in rep["coverage"]["requirements"].items() if v["status"] != "COVERED"]}
        expect(p.returncode == 1 and rep["verdict"] == "NOT_READY", f"lint {which}: expected NOT_READY/exit 1")
        expect(rep["to_approve"] and isinstance(rep["admission"], str), f"lint {which}: NOT_READY for a reason other than approvals")
        expect(not rep["criteria_without_calibration"] and not rep["criteria_without_contract"], f"lint {which}: calibration/contract gaps")
        expect(not result[f"lint_{which}_unapproved"]["uncovered"], f"lint {which}: uncovered requirements")

    # 4. leaks
    evaluator = read(sealed["evaluator"])
    marks = H.distinctive(evaluator)
    scanned = {str(p.relative_to(W1A)): text_hits(marks, p) for p in
               (W1A / "baseline/docs/requirements.md", W1A / "baseline/README.md", W1A / "arms/authoring.json", sealed["arms"])}
    shared = sorted(parts(evaluator) & parts(read(sealed["arms"])))
    result["leaks"] = {"distinctive_strings": len(marks), "text_hits": scanned, "shared_canonical_parts": shared}
    expect(not any(scanned.values()), "a distinctive evaluator string appears in a public file")
    expect(not shared, "the evaluator and the arms' bundle share a stimulus or observable")
    expect(len(evaluator["contracts"]) in range(8, 13), "the evaluator holds 8-12 contracts")
    result["leaks"]["probe_kinds_evaluator"] = sorted({c["subject"]["kind"] for c in evaluator["contracts"]})

    # 5. technical approvals in scratch (never committed)
    approved: dict[str, pathlib.Path] = {}
    for which in ("arms", "evaluator"):
        for old in scratch.glob(f"{which}.approved-*.json"):
            old.unlink()
        approved[which] = approve_all(sealed[which], scratch, which)
        p = aisef_bundle("lint", str(approved[which]), check=False)
        rep = json.loads(p.stdout)
        result[f"lint_{which}_technically_approved"] = {"approver": APPROVER, "file": str(approved[which]), "exit": p.returncode,
                                                        "verdict": rep["verdict"], "admission": rep["admission"]}
        expect(p.returncode == 0 and rep["verdict"] == "READY", f"lint {which} (technically approved): expected READY")

    # 6. probes: the reference candidate and the bare baseline, with both bundles
    cand = scratch / "candidate"
    shutil.rmtree(cand, ignore_errors=True)
    sh("git", "clone", "--quiet", "--no-hardlinks", str(base), str(cand))
    for f in sorted((HERE / "reference").rglob("*.py")):
        rel = f.relative_to(HERE / "reference")
        (cand / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, cand / rel)
    sh("git", "add", "-A", cwd=cand)
    sh("git", "-c", "user.name=w1a-dry-check", "-c", "user.email=dry@w1a.invalid", "commit", "-q", "-m", "reference implementation", cwd=cand)
    rev = sh("git", "rev-parse", "HEAD", cwd=cand).stdout.strip()
    result["reference_candidate"] = {"commit": rev, "files": sorted(str(p.relative_to(HERE / "reference")) for p in (HERE / "reference").rglob("*.py"))}
    smoke = sh(PY, "-P", "-B", "-I", "-m", "unittest", "discover", "-s", "tests", "-t", ".", cwd=cand, check=False)
    result["reference_candidate"]["smoke_test_exit"] = smoke.returncode
    expect(smoke.returncode == 0, "the smoke test does not pass on the reference candidate")
    for which in ("arms", "evaluator"):
        doc = read(approved[which])
        for label, at in (("reference", rev), ("baseline", shas[0])):
            ev = H.evaluate(cand, at, doc)
            result[f"evaluate_{which}_{label}"] = ev
    expect(result["evaluate_evaluator_reference"]["not_satisfied"] == [], "the reference does not satisfy every hidden contract")
    expect(result["evaluate_arms_reference"]["not_satisfied"] == [], "the reference does not satisfy every arms' contract")
    # at the baseline only what holds of an empty package may hold: the stdlib-only checks over existing .py files
    base_ok = {w: result[f"evaluate_{w}_baseline"]["satisfied"] for w in ("arms", "evaluator")}
    result["baseline_satisfied"] = base_ok
    expect(base_ok["evaluator"] <= 1 and base_ok["arms"] <= 1, "the bare baseline satisfies more than the stdlib-only check")

    result["problems"] = problems
    result["ok"] = not problems
    result["finished"] = time.strftime("%Y-%m-%d %H:%M:%S %z")
    (HERE / "RESULT.json").write_text(json.dumps(result, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "problems": problems, "baseline": shas[0],
                      "evaluator": {k: result[f"evaluate_evaluator_{k}"]["satisfied"] for k in ("reference", "baseline")},
                      "arms": {k: result[f"evaluate_arms_{k}"]["satisfied"] for k in ("reference", "baseline")}}, indent=1))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(pathlib.Path(sys.argv[1]).resolve()))
