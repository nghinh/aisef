"""V2.0 release: the LedgerLock project bundle (aisef-v2-project/1) that `aisef run` executes in the release smoke —
the corrected plan (PLAN-V2.2 CORRECTION 1) re-bound to this release's probe identities, and nothing else changed.

    python -P validation/qualification/release_bundle.py --print    # the re-binding proof, nothing written
    python -P validation/qualification/release_bundle.py --write    # -> closure-evidence/v2/release/LEDGERLOCK-PROJECT.json
                                                                     #    and LEDGERLOCK-REBIND.json
    python -P validation/qualification/release_bundle.py --check    # the committed files are what this tree derives

Why a re-binding: B1 (the verdict channel) changed the probes' sources, hence their digests, hence the id of every
ProductProofSpec that binds one. The plan is rebuilt exactly as c2_plan_correction builds it — the authoring aid's
plan under this tree's catalog, the owner's decisions applied — and then mapped back: each obligation's spec replaced by
the committed correction's spec of the same contract must give back the committed corrected plan's hash. That is the
proof that only the probe identities moved (criteria, stories, roles, expected parents, dependencies, contracts,
approvals and requirements are the ones the owner accepted). No probe runs, no model is called.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BUNDLE_REL = "closure-evidence/v2/release/LEDGERLOCK-PROJECT.json"
REBIND_REL = "closure-evidence/v2/release/LEDGERLOCK-REBIND.json"
PLAN_ID = "LEDGERLOCK-PLAN-V2.2-CORRECTION-1-REBOUND-V2.0"
DESCRIPTION = "LedgerLock is a small Python library and CLI (the package `ledgerlock/`, Python standard library only)."


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rebound() -> dict:
    """The corrected plan under this tree's probes, and the proof it is the committed one with only spec ids moved
    (the probe-identity re-binding, validation/qualification/rebind.py)."""
    from aisef2.plan.obligation import Plan
    from validation.qualification import c2_plan_correction as pc
    from validation.qualification import rebind
    committed = json.loads((ROOT / pc.OUT_REL).read_text(encoding="utf-8"))
    b = pc.build()                          # the owner's decisions applied to PLAN-V2.2 under this tree's probes
    compiled, corrected = b["compiled"], b["new"]
    was_id = {r["spec_id"]: r["spec_hash_id"] for r in committed["proofs"]["product_proof_specs"]["specs"]}
    plan = Plan.create(id=PLAN_ID, baseline=corrected.baseline, obligations=corrected.obligations,
                       plan_quality_policy=corrected.plan_quality_policy)
    back = rebind.plan_back(plan, b["rebind"], id=pc.PLAN_ID)
    moved = sorted(k for k in was_id if compiled[k].id != was_id[k])
    return {"plan": plan, "compiled": compiled, "graph": b["graph"],
            "proof": {"committed_correction": {"path": pc.OUT_REL, "plan_hash": committed["new_plan"]["plan_hash"]},
                      "mapped_back_plan_hash": back.plan_hash,
                      "only_spec_ids_moved": back.plan_hash == committed["new_plan"]["plan_hash"],
                      "specs": len(was_id), "spec_ids_moved": len(moved),
                      "spec_ids": {k: {"was": was_id[k], "now": compiled[k].id, "probe": compiled[k].probe_id,
                                       "probe_digest": compiled[k].probe_digest} for k in moved}}}


def build() -> dict:
    from aisef2.app import bundle
    from aisef2.app import run as R
    from aisef2.orchestrate.workspace import git
    from validation.qualification import c2_p9
    from validation.qualification import p5_acceptance as pa
    from validation.qualification import p10 as P10
    from validation.qualification import p10_contracts as aid
    r = rebound()
    plan = r["plan"]
    blob = git(P10.LEDGERLOCK_REPO, "cat-file", "blob", f"{plan.baseline}:docs/requirements.md")
    if blob.returncode != 0:
        raise SystemExit(f"the LedgerLock repository does not hold the baseline's requirements: {blob.stderr.strip()[:200]}")
    requirements_md = blob.stdout
    facts = {c: {k: f[k] for k in bundle.FACT_FIELDS} for c, f in c2_p9.obligation_facts(plan, requirements_md).items()}
    stories = sorted({o.story_id for o in plan.obligations})
    doc = bundle.dump(name="LedgerLock", description=DESCRIPTION, requirements_path="docs/requirements.md",
                      requirements_sha256=_sha(requirements_md.encode("utf-8")), product_roots=sorted(c2_p9.PROJECT),
                      requirements=aid.requirements().values(), contracts=pa.contracts().values(),
                      approvals=pa.load_approvals(), plan=plan, facts=facts,
                      stories={s: {"depends_on": sorted(set(r["graph"].get(s, ())) & set(stories)), "tests": [c2_p9.test_path(s)]}
                               for s in stories})
    project = bundle.load(json.loads(json.dumps(doc)))
    admission = R.admit(project, R.calibrations())
    record = {
        "record": "AISEF V2.0 — THE LEDGERLOCK PROJECT BUNDLE FOR THE RELEASE SMOKE (the corrected plan re-bound to this "
                  "release's probe identities)",
        "status": "EXPORTED; not executed — no probe ran, no model was called",
        "generator": {"path": "validation/qualification/release_bundle.py", "sha256": c2_p9.C.lf_sha(HERE / "release_bundle.py")},
        "aisef2_tree": c2_p9.C.git("rev-parse", "HEAD:aisef2"),
        "bundle": {"path": BUNDLE_REL, "digest": project.digest, "plan_id": plan.id, "plan_hash": plan.plan_hash,
                   "baseline": plan.baseline, "stories": len(stories), "obligations": len(plan.obligations),
                   "execution_order": project.order(), "attempt_4_order": c2_p9.order(plan, r["graph"])},
        "requirements_document": {"sha256": _sha(requirements_md.encode("utf-8")), "frozen": P10.REQUIREMENTS_SHA256},
        "rebinding": r["proof"],
        "admission_with_shipped_calibrations": admission,
    }
    record["problems"] = problems(record)
    record["verdict"] = "READY" if not record["problems"] else "PROBLEMS"
    return {"bundle": doc, "record": record}


def problems(rec: dict) -> list[str]:
    out = []
    if not rec["rebinding"]["only_spec_ids_moved"]:
        out.append("mapped back, the re-bound plan is not the committed corrected plan: more than the probe identities moved")
    if rec["requirements_document"]["sha256"] != rec["requirements_document"]["frozen"]:
        out.append("the baseline's requirements document is not the frozen one")
    if rec["bundle"]["execution_order"] != rec["bundle"]["attempt_4_order"]:
        out.append("the bundle's story order is not the order attempt 4 ran")
    if not rec["admission_with_shipped_calibrations"]["admitted"]:
        out.append(f"the re-bound plan is not admitted with the shipped calibrations: "
                   f"{rec['admission_with_shipped_calibrations']['failed']}")
    return out


def _render(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--print", action="store_true")
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    b = build()
    if a.print:
        print(_render({k: v for k, v in b["record"].items() if k != "rebinding"} | {"rebinding": {
            k: v for k, v in b["record"]["rebinding"].items() if k != "spec_ids"}}))
        return 0 if not b["record"]["problems"] else 1
    if a.write:
        if b["record"]["problems"]:
            print("\n".join(b["record"]["problems"]), file=sys.stderr)
            return 1
        (ROOT / BUNDLE_REL).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / BUNDLE_REL).write_text(_render(b["bundle"]), encoding="utf-8")
        (ROOT / REBIND_REL).write_text(_render(b["record"]), encoding="utf-8")
        print(f"wrote {BUNDLE_REL} (digest {b['record']['bundle']['digest'][:16]}) and {REBIND_REL}")
        return 0
    bad = [rel for rel, body in ((BUNDLE_REL, b["bundle"]), (REBIND_REL, b["record"]))
           if not (ROOT / rel).exists() or (ROOT / rel).read_text(encoding="utf-8") != _render(body)]
    print("release bundle: " + ("PASS" if not bad and not b["record"]["problems"] else f"FAIL {bad} {b['record']['problems']}"))
    return 0 if not bad and not b["record"]["problems"] else 1


if __name__ == "__main__":
    sys.exit(main())
