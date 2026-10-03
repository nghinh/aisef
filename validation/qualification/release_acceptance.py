"""V2.0 release charter §13 and §17: the ABSOLUTE release acceptance of the one release smoke — frozen before any
provider call, defined by the frozen requirements and the approved contracts alone (V1 is informational, never a gate).

    python -P validation/qualification/release_acceptance.py --freeze            # -> closure-evidence/v2/release/V2-RELEASE-ACCEPTANCE.json
    python -P validation/qualification/release_acceptance.py --check             # the frozen acceptance is this tree's bundle and suite
    python -P validation/qualification/release_acceptance.py --evaluate RUN_DIR  # RELEASE_SMOKE_PASS of a finished `aisef run` directory

The acceptance suite is every ProductProofSpec the bundle's approved contracts compile to, each put to its own probe
on the delivered `main` of the run — independently of the run's journal. A run passes only when ALL hold:

* the run directory verifies from its own journal (aisef2.app.verify: hash chain, digest, verdict re-derived);
* the delivery verdict is PASS: every planned story's last outcome is its commit, no budget stop, no refused story;
* ProductProof: every plan obligation delivered (satisfied at its last proof, by both parties, in a committed story);
* the acceptance suite: every spec SATISFIED on the delivered main (threshold: all of them);
* false acceptance 0: no spec the journal delivered is unsatisfied on the delivered main;
* framework false rollback / block 0: no story ends rolled back or blocked by a failure the framework owns
  (ENVIRONMENT, PLAN, INTEGRATION) — a developer's own failure is not the framework's;
* the route was attested (no identity violation), and no spend is unaccounted.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import pathlib
import subprocess
import sys
import tarfile
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_REL = "closure-evidence/v2/release/V2-RELEASE-ACCEPTANCE.json"
FRAMEWORK_OWNERS = ("ENVIRONMENT", "PLAN", "INTEGRATION")
PROBE_TIMEOUT_S = 60.0


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def suite(project) -> list[dict]:
    """The acceptance suite of a project bundle: every compiled spec, by id, with what pins it."""
    return [{"spec": s.id, "contract": s.contract_id, "semantic_hash": s.semantic_hash, "probe_id": s.probe_id,
             "probe_digest": s.probe_digest, "expectation": s.candidate_expectation.value}
            for s in sorted(project.specs.values(), key=lambda s: s.id)]


def frozen(project) -> dict:
    from validation.qualification import common as C
    return {
        "record": "AISEF V2.0 — RELEASE ACCEPTANCE (charter §13): frozen before the release smoke; V1 is informational only",
        "workload": project.name, "bundle_digest": project.digest, "plan_hash": project.plan.plan_hash,
        "requirements_document": {"path": project.requirements_path, "sha256": project.requirements_sha256},
        "stories": project.order(), "obligations": len(project.plan.obligations),
        "acceptance_suite": suite(project),
        "thresholds": {"run_verified": True, "delivery_verdict": "PASS", "stories_committed": "all",
                       "productproof_delivered": "all obligations", "acceptance_suite_satisfied": "all specs",
                       "false_acceptance": 0, "framework_false_rollback_or_block": 0, "preflight": "ATTESTED",
                       "unaccounted_spend": 0},
        "evaluator": {"path": "validation/qualification/release_acceptance.py", "sha256": C.lf_sha(HERE / "release_acceptance.py")},
        "v1": "INFORMATIONAL_ONLY",
    }


def delivered_main(run_dir: pathlib.Path, dest: pathlib.Path) -> tuple[str, pathlib.Path]:
    """The run's final main, as plain files (read from the run's own clone; the clone is only read)."""
    repo = run_dir / "repo"
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "main"], capture_output=True, encoding="utf-8", check=True).stdout.strip()
    data = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", sha], capture_output=True, check=True).stdout
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(dest, filter="data")
    return sha, dest


def acceptance(project, tree: pathlib.Path, sha: str, interpreter: str = sys.executable) -> dict:
    """Every spec of the suite put to its own probe on `tree` — whatever story owned it, whatever the journal says."""
    from aisef2.arch.enums import ContractSatisfaction, Enforcement, ProbeExecutionStatus
    from aisef2.probe import catalog
    from aisef2.probe.protocol import ExecutionEnv, RevisionRef, bound_result, run_probe
    from aisef2.product.outcome import contract_satisfaction
    env, at, rows = ExecutionEnv(interpreter, PROBE_TIMEOUT_S, Enforcement.PARTIAL), RevisionRef(sha, str(tree.resolve())), []
    for spec in sorted(project.specs.values(), key=lambda s: s.id):
        probe = next(e for e in catalog.CATALOG if e.probe_id == spec.probe_id).factory()
        result = bound_result(run_probe(probe, spec, at, env), spec=spec, revision=at.sha, enforcement=probe.enforcement())
        executed = result.status is ProbeExecutionStatus.EXECUTED
        rows.append({"spec": spec.id, "status": result.status.value,
                     "satisfaction": contract_satisfaction(result, spec).value if executed else None})
    ok = ContractSatisfaction.SATISFIED.value
    return {"revision": sha, "total": len(rows), "satisfied": sum(r["satisfaction"] == ok for r in rows),
            "not_satisfied": [r["spec"] for r in rows if r["satisfaction"] != ok], "specs": rows}


def framework_blocks(events: list[dict], committed: set[str], depends: dict[str, list[str]] | None = None) -> list[dict]:
    """Stories that did not commit and whose last observed failure the framework owns. One whose story depends (through
    `depends`, transitively) on a story that did not commit is marked `upstream_not_committed`: its block follows from
    that story's failure (e.g. PRECONDITION_BROKEN), it is not a false one."""
    depends = depends or {}

    def upstream(s: str, seen: frozenset = frozenset()) -> bool:
        return any(d not in committed or (d not in seen and upstream(d, seen | {s})) for d in depends.get(s, ()))
    last: dict[str, dict] = {}
    for e in events:
        if e["type"] == "failure/observed" and e["data"].get("story_id"):
            last[e["data"]["story_id"]] = e["data"]
    return [{"story": s, "code": f.get("code"), "owner": f.get("owner"), **({"upstream_not_committed": True} if upstream(s) else {})}
            for s, f in sorted(last.items()) if s not in committed and f.get("owner") in FRAMEWORK_OWNERS]


def evaluate(project, run_dir: pathlib.Path, accepted: dict) -> dict:
    from aisef2.app import run as R
    from aisef2.app.verify import verify
    from aisef2.journal import format3
    from aisef2.product.contract import plain
    from validation.qualification import common as C
    problems: list[str] = []
    if accepted.get("bundle_digest") != project.digest or accepted.get("acceptance_suite") != suite(project):
        problems.append("the frozen acceptance is not this bundle's")
    if (accepted.get("evaluator") or {}).get("sha256") != C.lf_sha(HERE / "release_acceptance.py"):
        problems.append("this evaluator is not the frozen one")
    rec = json.loads((run_dir / "RUN.json").read_text(encoding="utf-8"))
    v = verify(project, run_dir)
    journal = format3.reconstruct((run_dir / rec["journal"]["path"]).read_text(encoding="utf-8")) if rec.get("journal") else None
    events = [{"seq": e.seq, "type": e.type, "data": plain(e.data)} for e in journal.events] if journal else []
    verdict, blocked, committed = R.delivery(project, events, rec.get("story_outcomes") or {}, rec.get("budget_stop"),
                                             rec.get("story_errors") or [])
    pp = R.productproof(project, events, committed) if events else {"total": len(project.plan.obligations), "delivered": 0, "obligations": []}
    with tempfile.TemporaryDirectory(prefix="aisef-acceptance-") as t:
        sha, tree = delivered_main(run_dir, pathlib.Path(t) / "main")
        acc = acceptance(project, tree, sha, str(run_dir / "probe-python" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")))
    claimed = {r["spec"] for r in pp["obligations"] if r["delivered"]}
    false_acceptance = sorted(claimed & set(acc["not_satisfied"]))
    blocks = framework_blocks(events, committed, {s: v["depends_on"] for s, v in project.stories.items()})
    pre = rec.get("preflight") or {}
    unaccounted = ((rec.get("budget") or {}).get("spent") or {}).get("unaccounted", ["no budget account"])
    checks = {"run_verified": v["verdict"] == "VERIFIED", "delivery_verdict": verdict == "PASS",
              "stories_committed": committed == set(project.order()),
              "productproof_delivered": pp["delivered"] == pp["total"] == len(project.plan.obligations),
              "acceptance_suite_satisfied": acc["satisfied"] == acc["total"] == len(project.specs),
              "false_acceptance": not false_acceptance, "framework_false_rollback_or_block": not [b for b in blocks if not b.get("upstream_not_committed")],
              "preflight": pre.get("verdict") == "ATTESTED", "unaccounted_spend": not unaccounted}
    problems += [f"{k} does not hold" for k, ok in checks.items() if not ok]
    return {"run": str(run_dir), "bundle_digest": project.digest, "delivery_verdict": verdict, "delivery_blocked_by": blocked,
            "verification": v, "productproof": {k: pp[k] for k in ("total", "delivered")},
            "acceptance": {k: acc[k] for k in ("revision", "total", "satisfied", "not_satisfied")},
            "false_acceptance": false_acceptance, "framework_false_rollback_or_block": blocks, "checks": checks,
            "problems": problems, "RELEASE_SMOKE_PASS": "YES" if not problems else "NO"}


def main(argv: list[str] | None = None) -> int:
    from aisef2.app import bundle
    from validation.qualification import release_bundle as rb
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--evaluate", type=pathlib.Path)
    a = ap.parse_args(argv)
    project = bundle.read(ROOT / rb.BUNDLE_REL)
    if a.freeze:
        if (ROOT / OUT_REL).exists():
            print(f"{OUT_REL} exists: a frozen acceptance is never rewritten", file=sys.stderr)
            return 1
        (ROOT / OUT_REL).write_text(json.dumps(frozen(project), indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"froze {OUT_REL}: {len(project.specs)} specs, {len(project.plan.obligations)} obligations")
        return 0
    accepted = json.loads((ROOT / OUT_REL).read_text(encoding="utf-8"))
    if a.check:
        want = frozen(project)
        bad = [k for k in want if k != "evaluator" and accepted.get(k) != want[k]]
        print("release acceptance: " + ("PASS" if not bad else f"FAIL {bad}"))
        return 1 if bad else 0
    out = evaluate(project, a.evaluate, accepted)
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0 if out["RELEASE_SMOKE_PASS"] == "YES" else 1


if __name__ == "__main__":
    sys.exit(main())
