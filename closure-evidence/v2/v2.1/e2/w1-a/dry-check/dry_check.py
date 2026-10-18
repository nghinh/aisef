"""W1-a dry check (offline; no provider, no client, no network). Run from anywhere:

    nice -n 19 /opt/homebrew/bin/python3 -P -B closure-evidence/v2/v2.1/e2/w1-a/dry-check/dry_check.py SCRATCH

1. init_repo.sh twice -> the baseline commit is reproducible (one sha).
2. `aisef bundle seal` of arms/authoring.json and evaluator/authoring.json against that baseline; the sealed,
   UNAPPROVED bundles are written beside their authoring documents (arms/bundle.json, evaluator/bundle.json) when
   they are not there yet, and compared byte for byte when they are.
3. `aisef bundle lint` of both: NOT_READY, and only for `to_approve` (admission is not run on an unapproved bundle).
4. Leak scan: harness.distinctive(evaluator) — the rule harness.leaks reads a session stream with — against every
   file of baseline/, direct-task.txt, arms/authoring.json and arms/bundle.json (its raw text and the canonical JSON
   of the document and of each stimulus/observable); the two bundles' distinctive sets must be disjoint.
5. TECHNICAL approvals, in SCRATCH only, by `human:w1a-dry-check` — never the owner's, never committed — so that
   lint can run the nine static admission checks (expected READY) and the probes can run.
6. The probes on a reference candidate (dry-check/reference/ on top of the baseline, committed in SCRATCH) and on the
   bare baseline, with both bundles: harness.evaluate, reported per contract (spec id -> contract id). Expected: the
   reference satisfies every contract of both bundles; the bare baseline satisfies exactly the hygiene check of the
   evaluator (HC-14, MUST_NOT_HOLD of an absent path) and the stdlib check of the arms (BC-STDLIB), every other
   contract INDETERMINATE or UNSATISFIED there.
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

from aisef2.app import bundle_cli  # noqa: E402
from aisef2.product.contract import BehaviorContract  # noqa: E402
from validation.experiments import harness as H  # noqa: E402

PY = sys.executable
ENV = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
APPROVER = "human:w1a-dry-check"
EVALUATOR_SIZE = 12
BASELINE_SATISFIES = {"arms": ["BC-STDLIB"], "evaluator": ["HC-14"]}


def sh(*argv, cwd=None, check=True) -> subprocess.CompletedProcess:
    p = subprocess.run(list(argv), cwd=cwd, env=ENV, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise SystemExit(f"FAILED ({p.returncode}): {' '.join(argv)}\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")
    return p


def aisef_bundle(*args, check=True) -> subprocess.CompletedProcess:
    return sh(PY, "-P", "-B", "-m", "aisef", "bundle", *args, cwd=ROOT, check=check)


def read(path) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def spec_to_contract(doc: dict) -> dict[str, str]:
    """spec id -> contract id, by the kernel's own minting (the ids harness.evaluate reports)."""
    refs = bundle_cli._refs()
    out = {}
    for x in doc["contracts"]:
        c = BehaviorContract.from_json(x)
        out[bundle_cli._mint(c, refs[c.subject.kind]).id] = c.id
    return out


def canonical_texts(doc: dict) -> str:
    """The document's canonical JSON and every contract's stimulus/observable in the compact form `distinctive`
    uses, so the scan does not depend on how the committed file was indented."""
    out = [json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False), json.dumps(doc, sort_keys=True)]
    for c in doc["contracts"]:
        out += [json.dumps(c["stimulus"], sort_keys=True), json.dumps(c["observable"], sort_keys=True)]
    return "\n".join(out)


def text_hits(marks: list[str], text: str) -> list[str]:
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
        result[f"seal_{which}"]["contracts"] = [c["id"] for c in read(committed)["contracts"]]
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
                                              "stray": rep["coverage"]["criteria_citing_no_requirement_of_the_bundle"],
                                              "uncovered": [r for r, v in rep["coverage"]["requirements"].items() if v["status"] != "COVERED"]}
        expect(p.returncode == 1 and rep["verdict"] == "NOT_READY", f"lint {which}: expected NOT_READY/exit 1")
        expect(rep["to_approve"] and isinstance(rep["admission"], str), f"lint {which}: NOT_READY for a reason other than approvals")
        expect(not rep["criteria_without_calibration"] and not rep["criteria_without_contract"], f"lint {which}: calibration/contract gaps")
        expect(not result[f"lint_{which}_unapproved"]["uncovered"] and not result[f"lint_{which}_unapproved"]["stray"],
               f"lint {which}: uncovered requirements or stray criteria")

    # 4. leaks
    evaluator, arms = read(sealed["evaluator"]), read(sealed["arms"])
    marks = H.distinctive(evaluator)
    arms_marks = H.distinctive(arms)
    texts = {"direct-task.txt": (W1A / "direct-task.txt").read_text(encoding="utf-8"),
             "arms/authoring.json": (W1A / "arms" / "authoring.json").read_text(encoding="utf-8"),
             "arms/bundle.json (raw)": sealed["arms"].read_text(encoding="utf-8"),
             "arms/bundle.json (canonical)": canonical_texts(arms)}
    for f in sorted(p for p in (W1A / "baseline").rglob("*") if p.is_file()):
        texts[f"baseline/{f.relative_to(W1A / 'baseline').as_posix()}"] = f.read_text(encoding="utf-8", errors="replace")
    scanned = {where: text_hits(marks, text) for where, text in texts.items()}
    shared = sorted(set(marks) & set(arms_marks))
    result["leaks"] = {"evaluator_distinctive_strings": len(marks), "arms_distinctive_strings": len(arms_marks),
                       "scanned": sorted(texts), "text_hits": scanned, "shared_distinctive_strings": shared,
                       "probe_kinds_evaluator": sorted({c["subject"]["kind"] for c in evaluator["contracts"]})}
    expect(not any(scanned.values()), "a distinctive evaluator string appears in a public file")
    expect(not shared, "the evaluator and the arms' bundle share a distinctive stimulus or observable")
    expect(len(evaluator["contracts"]) == EVALUATOR_SIZE, f"the evaluator holds {EVALUATOR_SIZE} contracts")

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

    # 6. probes: the reference candidate and the bare baseline, with both bundles, per contract
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
        names = spec_to_contract(doc)
        for label, at in (("reference", rev), ("baseline", shas[0])):
            ev = H.evaluate(cand, at, doc)
            ev["by_contract"] = {names.get(r["spec"], r["spec"]): {"status": r["status"], "satisfaction": r["satisfaction"]}
                                 for r in ev["specs"]}
            ev["not_satisfied"] = sorted(names.get(s, s) for s in ev["not_satisfied"])
            result[f"evaluate_{which}_{label}"] = ev
        expect(result[f"evaluate_{which}_reference"]["not_satisfied"] == [], f"the reference does not satisfy every {which} contract")
        held = sorted(c for c, r in result[f"evaluate_{which}_baseline"]["by_contract"].items() if r["satisfaction"] == "SATISFIED")
        expect(held == BASELINE_SATISFIES[which], f"the bare baseline satisfies {held} of {which}, expected {BASELINE_SATISFIES[which]}")
    result["baseline_satisfied"] = {w: sorted(c for c, r in result[f"evaluate_{w}_baseline"]["by_contract"].items()
                                              if r["satisfaction"] == "SATISFIED") for w in ("arms", "evaluator")}

    result["problems"] = problems
    result["ok"] = not problems
    result["finished"] = time.strftime("%Y-%m-%d %H:%M:%S %z")
    (HERE / "RESULT.json").write_text(json.dumps(result, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    summary = {"ok": result["ok"], "problems": problems, "baseline": shas[0],
               "contracts": {w: result[f"seal_{w}"]["specs"] for w in ("arms", "evaluator")},
               "lint_unapproved": {w: (result[f"lint_{w}_unapproved"]["verdict"], result[f"lint_{w}_unapproved"]["to_approve"],
                                       result[f"lint_{w}_unapproved"]["admission"]) for w in ("arms", "evaluator")},
               "lint_technically_approved": {w: (result[f"lint_{w}_technically_approved"]["verdict"],
                                                 result[f"lint_{w}_technically_approved"]["admission"]) for w in ("arms", "evaluator")},
               "leaks": {k: result["leaks"][k] for k in ("evaluator_distinctive_strings", "arms_distinctive_strings",
                                                          "shared_distinctive_strings")},
               "leak_hits": {k: len(v) for k, v in result["leaks"]["text_hits"].items()},
               "evaluator": {k: result[f"evaluate_evaluator_{k}"]["satisfied"] for k in ("reference", "baseline")},
               "arms": {k: result[f"evaluate_arms_{k}"]["satisfied"] for k in ("reference", "baseline")},
               "by_contract": {f"{w}_{k}": {c: r["satisfaction"] or r["status"] for c, r in result[f"evaluate_{w}_{k}"]["by_contract"].items()}
                               for w in ("arms", "evaluator") for k in ("reference", "baseline")}}
    print(json.dumps(summary, indent=1))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(pathlib.Path(sys.argv[1]).resolve()))
