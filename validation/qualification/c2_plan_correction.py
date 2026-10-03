"""PLAN-V2.2 CORRECTION 1 (owner ruling 'AISEF V2 — FINAL PLAN CORRECTION + DELIVERY RUN PREREGISTRATION / NO PROVIDER
CALL', 2026-10-02): the owner's planning decisions applied to the accepted PLAN-V2.2, and nothing else.

    python -P validation/qualification/c2_plan_correction.py --write    # -> closure-evidence/v2/cycle2/PLAN-V2.2-CORRECTION-1.json
    python -P validation/qualification/c2_plan_correction.py --check    # the committed record is what this tree derives

A plan-level (level 4) change only: eight obligations move to an existing implementation story (`DECISIONS`), which
leaves STORY-05-01 and STORY-05-03 without an obligation — they are no longer stories of the plan. No BehaviorContract,
ProductProofSpec, approval or requirement is touched: the plan is rebuilt from the accepted plan's own obligations, the
59 specs are the ones compiled under the persisted real approvals, and the record proves they are the accepted ones.
A moved obligation depends on the INTRODUCE criteria of every story its new story depends on — the authoring aid's own
rule (p10_contracts.build) — so its new story is ordered after the story that introduced the behaviour.

Static admission is the engine's nine checks under the persisted real approvals. No probe runs, no model is called.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_REL = "closure-evidence/v2/cycle2/PLAN-V2.2-CORRECTION-1.json"
PLAN_ID = "LEDGERLOCK-PLAN-V2.2-CORRECTION-1"
AUTHORITY = ("owner ruling 'AISEF V2 — FINAL PLAN CORRECTION + DELIVERY RUN PREREGISTRATION / NO PROVIDER CALL' "
             "(2026-10-02), decisions 1-4")
#: criterion -> (story, role, the owner's decision). The expected parent state is the role's own (§13).
DECISIONS = {
    "S-D3-05-01-1": ("STORY-04-02", "VERIFY", 1),
    "S-D3-05-01-2": ("STORY-04-01", "PRESERVE", 2),
    "AC-STORY-05-03-1:S-10-a": ("STORY-01-05", "PRESERVE", 3),
    "AC-STORY-05-03-1:S-12-a": ("STORY-01-05", "PRESERVE", 3),
    "AC-STORY-05-03-1:S-12-b": ("STORY-01-05", "PRESERVE", 3),
    "AC-STORY-05-03-2:S-12-a": ("STORY-01-05", "PRESERVE", 3),
    "AC-STORY-05-03-2:S-12-b": ("STORY-01-05", "PRESERVE", 3),
    "AC-STORY-05-03-2:S-12-c": ("STORY-01-05", "PRESERVE", 3),
}
REMOVED_STORIES = ("STORY-05-01", "STORY-05-03")          # decisions 3 and 4: no standalone execution story
#: decisions 2 and 3: the story each moved PRESERVE must come after
ORDERED_AFTER = {"S-D3-05-01-2": "STORY-03-01", **{c: "STORY-01-01" for c, d in DECISIONS.items() if d[2] == 3}}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build() -> dict:
    """The accepted plan, the corrected plan and what both are admitted against — under this tree's probe identities;
    `rebind` maps each of them back to the accepted one (validation/qualification/rebind.py)."""
    from aisef2.arch.enums import ObligationRole
    from aisef2.plan import static_admission as sa
    from aisef2.plan.obligation import EXPECTED_AT_PARENT, Plan
    from aisef2.probe import catalog
    from validation.qualification import c2_p9, rebind
    from validation.qualification import p5_acceptance as pa
    from validation.qualification import p10_contracts as aid
    old = aid.build()["plan"]
    compiled = c2_p9._compiled()
    contracts = pa.contracts()
    subst = rebind.spec_subst(rebind.rows(compiled, contracts), rebind.accepted_rows())
    if rebind.plan_back(old, subst).plan_hash != pa.ACCEPTED["plan_hash"]:
        raise SystemExit("the plan the correction starts from is not the accepted PLAN-V2.2")
    graph = aid.story_graph()
    introduce: dict[str, list[str]] = {}
    for o in old.obligations:
        if o.role is ObligationRole.INTRODUCE:
            introduce.setdefault(o.story_id, []).append(o.criterion_id)
    obligations = []
    for o in old.obligations:
        if o.criterion_id in DECISIONS:
            story, role, n = DECISIONS[o.criterion_id]
            role = ObligationRole[role]
            o = dataclasses.replace(o, story_id=story, role=role, expected_parent=EXPECTED_AT_PARENT[role],
                                    depends_on=tuple(c for s in sorted(graph[story]) for c in introduce.get(s, ())),
                                    ownership_rationale=f"{story} {role.value}s {o.criterion_id} (owner decision {n}, 2026-10-02)")
        obligations.append(o)
    new = Plan.create(id=PLAN_ID, baseline=old.baseline, obligations=tuple(obligations), plan_quality_policy=old.plan_quality_policy)
    inputs = sa.AdmissionInputs(aid.requirements(), {c.id: c for c in contracts.values()}, pa.load_approvals(),
                                {s.id: s for s in compiled.values()}, catalog.catalogue(), aid.calibrations(), catalog.registry())
    return {"old": old, "new": new, "inputs": inputs, "compiled": compiled, "contracts": contracts, "graph": graph, "rebind": subst}


def corrected_plan():
    return build()["new"]


def _admission(result) -> dict:
    return {"engine_digest": result.engine_digest, "admitted": result.admitted, "result_digest": result.result_digest,
            "checks": [{"number": c.number, "name": c.name, "passed": c.passed, "problems": list(c.problems)} for c in result.checks]}


def _coverage(plan, inputs) -> dict:
    """What the plan's obligations reach: the requirements (through each spec's contract) and the specs themselves."""
    reqs: dict[str, int] = {}
    for sid in sorted({o.product_proof_spec_id for o in plan.obligations}):
        for rid in inputs.contracts[inputs.specs[sid].contract_id].requirement_ids:
            reqs[rid] = reqs.get(rid, 0) + 1
    return {"requirements": dict(sorted(reqs.items())), "specs": len({o.product_proof_spec_id for o in plan.obligations})}


def _shape(plan) -> dict:
    stories: dict[str, dict[str, int]] = {}
    for o in plan.obligations:
        stories.setdefault(o.story_id, {})[o.role.value] = stories.setdefault(o.story_id, {}).get(o.role.value, 0) + 1
    return {"id": plan.id, "plan_hash": plan.plan_hash, "baseline": plan.baseline, "stories": len(stories),
            "obligations": len(plan.obligations), "obligations_by_story_and_role": {s: dict(sorted(v.items())) for s, v in sorted(stories.items())}}


def _rows(b: dict) -> list[list]:
    """[spec, contract id, contract hash, spec id, semantic hash, probe id, probe digest] in proposal order."""
    from validation.qualification import rebind
    now = rebind.rows(b["compiled"], b["contracts"])
    return [[sid, *(now[sid][k] for k in rebind.ROW)] for sid in rebind.accepted_rows()]


def record(b: dict | None = None) -> dict:
    from aisef2.arch.enums import ObligationRole
    from aisef2.plan import static_admission as sa
    from validation.qualification import c2_p9, rebind
    from validation.qualification import p5_acceptance as pa
    b = b or build()
    old, new, inputs = b["old"], b["new"], b["inputs"]
    engine = sa.StaticPlanAdmissionEngine()
    admitted = {"accepted_plan": _admission(engine.admit(old, inputs)), "corrected_plan": _admission(engine.admit(new, inputs)),
                "corrected_plan_without_approvals": _admission(engine.admit(new, dataclasses.replace(inputs, approvals=())))}
    # the 59 specs: compiled here under the real approvals, against what the owner accepted (the committed proposal
    # record) — equal up to probe identity: this tree's identities mapped back by the re-binding
    accepted = {s["spec_id"]: s for s in json.loads((ROOT / pa.PROPOSAL_REL).read_text(encoding="utf-8"))["specs"]}
    rows = _rows(b)
    spec_rows = [{"spec_id": r[0], "spec_hash_id": r[3], "semantic_hash": r[4],
                  "equal_to_accepted": rebind.back(r[1:], b["rebind"]) == [accepted[r[0]][k] for k in rebind.ROW]} for r in rows]
    by_criterion = {p.plan_hash: {o.criterion_id: o for o in p.obligations} for p in (old, new)}
    was, now = by_criterion[old.plan_hash], by_criterion[new.plan_hash]
    name = {s.id: sid for sid, s in b["compiled"].items()}
    moved = [{"criterion": c, "spec": name[now[c].product_proof_spec_id], "product_proof_spec_id": now[c].product_proof_spec_id,
              "owner_decision": DECISIONS[c][2],
              "from": {"story": was[c].story_id, "role": was[c].role.value, "expected_parent": was[c].expected_parent.value},
              "to": {"story": now[c].story_id, "role": now[c].role.value, "expected_parent": now[c].expected_parent.value},
              "ordered_after": ORDERED_AFTER.get(c),
              "ordered_after_holds": c not in ORDERED_AFTER or sa.depends_on_story(sa.story_graph(new), now[c].story_id, ORDERED_AFTER[c])}
             for c in DECISIONS]
    introducer = {p.plan_hash: {o.product_proof_spec_id: o.story_id for o in p.obligations if o.role is ObligationRole.INTRODUCE}
                  for p in (old, new)}
    stories_new = {o.story_id for o in new.obligations}
    body = {
        "record": "AISEF V2 — LEDGERLOCK PLAN-V2.2 CORRECTION 1 (owner planning decisions applied; plan only)",
        "authority": AUTHORITY,
        "status": "PLAN REGENERATED AND STATICALLY ADMITTED; not executed — no probe ran, no model was called, LedgerLock not run",
        "identities": {"aisef2_tree": c2_p9.C.git("rev-parse", "HEAD:aisef2"), "admission_engine_digest": engine.digest,
                       "generator": {"path": "validation/qualification/c2_plan_correction.py", "sha256": c2_p9.C.lf_sha(HERE / "c2_plan_correction.py")},
                       "accepted_proposal": {"path": pa.PROPOSAL_REL, "sha256": c2_p9.C.lf_sha(ROOT / pa.PROPOSAL_REL)},
                       "approvals": {"path": pa.APPROVALS_REL, "count": len(inputs.approvals), "approver": pa.OWNER}},
        "old_plan": _shape(old), "new_plan": _shape(new),
        "execution_order": c2_p9.order(new, b["graph"]),
        "moved_obligations": moved,
        "removed_stories": {s: {"obligations_left": sum(1 for o in new.obligations if o.story_id == s)} for s in REMOVED_STORIES},
        "static_admission": admitted,
        "proofs": {
            "product_proof_specs": {"count": len(rows), "all_equal_to_accepted": all(r["equal_to_accepted"] for r in spec_rows),
                                    "contract_spec_semantic_digest": _sha(json.dumps(rows, sort_keys=True).encode()),
                                    "rule": "sha256 of the JSON list of [spec, contract id, contract hash, spec id, semantic hash, "
                                            "probe id, probe digest] rows in proposal order (C2-ORCHESTRATION-CONFORMANCE-REPAIR (e))",
                                    "semantic_hash_changes": [r["spec_id"] for r in spec_rows if not r["equal_to_accepted"]],
                                    "spec_of_each_criterion_unchanged": {c: o.product_proof_spec_id for c, o in was.items()}
                                    == {c: o.product_proof_spec_id for c, o in now.items()},
                                    "specs": spec_rows},
            "requirement_coverage": {"old": _coverage(old, inputs), "new": _coverage(new, inputs),
                                     "unchanged": _coverage(old, inputs) == _coverage(new, inputs)},
            "no_orphan_obligation": {"criteria_old": len(was), "criteria_new": len(now), "same_criteria": set(was) == set(now),
                                     "every_spec_in_the_committed_derivation": all(o.product_proof_spec_id in inputs.specs for o in new.obligations),
                                     "obligations_in_a_removed_story": sum(1 for o in new.obligations if o.story_id in REMOVED_STORIES)},
            "introduce_uniqueness": {"introduce_specs_old": len(introducer[old.plan_hash]), "introduce_specs_new": len(introducer[new.plan_hash]),
                                     "introducing_story_of_each_spec_unchanged": introducer[old.plan_hash] == introducer[new.plan_hash],
                                     "introduce_obligations_new": sum(1 for o in new.obligations if o.role is ObligationRole.INTRODUCE)},
            "dependency_dag": {"criterion_graph_cycle": sa._cycle({o.criterion_id: dict.fromkeys(o.depends_on) for o in new.obligations}),
                               "story_graph_cycle": sa._cycle(sa.story_graph(new)),
                               "story_graph": {s: sorted(v) for s, v in sorted(sa.story_graph(new).items())}},
            "obligations_not_named_by_a_decision_unchanged": all(was[c] == now[c] for c in was if c not in DECISIONS),
            "stories_new_are_stories_old_minus_the_removed": stories_new == {o.story_id for o in old.obligations} - set(REMOVED_STORIES),
        },
    }
    body["problems"] = problems(body)
    body["verdict"] = "PLAN CORRECTION ADMITTED STATICALLY" if not body["problems"] else "PROBLEMS"
    return json.loads(json.dumps(body))


def problems(body: dict) -> list[str]:
    p, a = body["proofs"], body["static_admission"]
    out = [f"corrected plan, check {c['number']} {c['name']}: {'; '.join(c['problems'])}" for c in a["corrected_plan"]["checks"] if not c["passed"]]
    if not a["accepted_plan"]["admitted"]:
        out.append("the accepted plan is not admitted on this tree")
    if a["corrected_plan_without_approvals"]["admitted"]:
        out.append("admitted without any approval: the approval gate did not hold")
    s = p["product_proof_specs"]
    if s["count"] != 59 or not s["all_equal_to_accepted"] or s["semantic_hash_changes"] or not s["spec_of_each_criterion_unchanged"]:
        out.append("a ProductProofSpec differs from the accepted one")
    if not p["requirement_coverage"]["unchanged"]:
        out.append("requirement coverage changed")
    o = p["no_orphan_obligation"]
    if not (o["same_criteria"] and o["every_spec_in_the_committed_derivation"]) or o["obligations_in_a_removed_story"]:
        out.append("an obligation is orphaned or left in a removed story")
    if not p["introduce_uniqueness"]["introducing_story_of_each_spec_unchanged"]:
        out.append("INTRODUCE ownership changed")
    if p["dependency_dag"]["criterion_graph_cycle"] or p["dependency_dag"]["story_graph_cycle"]:
        out.append("the dependency graph has a cycle")
    if not p["obligations_not_named_by_a_decision_unchanged"] or not p["stories_new_are_stories_old_minus_the_removed"]:
        out.append("something outside the owner's decisions changed")
    out += [f"{m['criterion']}: not ordered after {m['ordered_after']}" for m in body["moved_obligations"] if not m["ordered_after_holds"]]
    out += [f"{m['criterion']}: not what the owner decided" for m in body["moved_obligations"]
            if (m["to"]["story"], m["to"]["role"]) != tuple(DECISIONS[m["criterion"]][:2])]
    return out


def currency(b: dict, rec: dict, committed: dict) -> dict:
    """The committed record against this tree's derivation `rec`, up to probe identity (validation/qualification/rebind.py):
    the re-bound identities mapped back, and the hashes over them — both plans' and the contract-spec digest — recomputed
    over the mapped-back content. Provenance tolerated: the kernel tree and this generator's sha256, each the committed
    value as of the commit that wrote the record and the derived one this tree's — the generator's only while build,
    record, check, currency and _rows are all that changed in it since."""
    from validation.qualification import c2_p9, rebind
    subst = dict(b["rebind"])
    subst.update({p.plan_hash: rebind.plan_back(p, b["rebind"]).plan_hash for p in (b["old"], b["new"])})
    subst[rec["proofs"]["product_proof_specs"]["contract_spec_semantic_digest"]] = \
        _sha(json.dumps(rebind.back(_rows(b), b["rebind"]), sort_keys=True).encode())
    written = c2_p9.C.git("log", "-1", "--format=%H", "--", OUT_REL)
    gen = "validation/qualification/c2_plan_correction.py"
    tolerated = {"identities.aisef2_tree": (c2_p9.C.git("rev-parse", f"{written}:aisef2"), c2_p9.C.git("rev-parse", "HEAD:aisef2"))}
    if rebind.code_moved(gen, written, ("build", "record", "check", "currency", "_rows")):
        tolerated["identities.generator.sha256"] = (rebind.lf_sha_at(written, gen), c2_p9.C.lf_sha(ROOT / gen))
    return rebind.compare(rec, committed, subst, tolerated)


def check() -> list[str]:
    b = build()
    rec = record(b)
    out = list(rec["problems"])
    path = ROOT / OUT_REL
    if not path.exists() or not currency(b, rec, json.loads(path.read_text(encoding="utf-8")))["current"]:
        out.append(f"{OUT_REL} is not what this tree derives")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.write:
        rec = record()
        if rec["problems"]:
            raise SystemExit("refused: " + "; ".join(rec["problems"]))
        (ROOT / OUT_REL).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(f"{OUT_REL}: {rec['verdict']}; {rec['old_plan']['plan_hash'][:12]} -> {rec['new_plan']['plan_hash'][:12]}; "
              f"stories {rec['old_plan']['stories']} -> {rec['new_plan']['stories']}; obligations {rec['new_plan']['obligations']}")
        return 0
    found = check()
    print("\n".join(found) if found else "PASS")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
