"""QP-2.9 preflight (owner ruling 2026-09-30): before any live developer/reviewer call, can the current authoritative
path prove every story of the owner-approved LedgerLock PLAN-V2.2?

    python -P validation/qualification/c2_p9_preflight.py --run     # -> closure-evidence/v2/cycle2/P10/QP-2.9-PREFLIGHT.json

Measured, never assumed: for each story of the plan, the probe identities its specs are bound to (compiled here under
the persisted real approvals); then, with the orchestration exactly as it is (aisef2/orchestrate/story_runner.py), what
happens when a story's probe factories are handed to it — `story_runner._probe` is called with them, and a spec of the
story is put to the one probe a single factory yields (`run_probe`). Nothing runs a subject and no model is called.

A story whose specs span more than one probe kind cannot be proved without changing the orchestration (a factory per
spec's probe identity), which the owner's global stop rules and the Cycle-2 manifest forbid without a separate owner
decision ("changing journal/projection/admission/orchestration to support a probe"). When any such story exists, QP-2.9
STOPS here, before execution, and this record is the preserved evidence of the exact trigger.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import common as C  # noqa: E402

OUT_REL = "closure-evidence/v2/cycle2/P10/QP-2.9-PREFLIGHT.json"
TRIGGER = ("changing journal/projection/admission/orchestration to support a probe (owner's global stop rules, 2026-09-30); "
           "Cycle-2 manifest stop rule: 'a control-plane, journal, projection, admission or orchestration change is needed "
           "for a probe: STOP, separate owner decision'")


def measure() -> dict:
    from aisef2.arch.enums import Enforcement
    from aisef2.errors import InvariantError
    from aisef2.orchestrate import story_runner as sr
    from aisef2.probe import catalog
    from aisef2.probe.calibration import FIXTURE_REVISION
    from aisef2.probe.protocol import ExecutionEnv, RevisionRef, run_probe
    from aisef2.product.compiler import ProbeRef, compile_spec
    from aisef2.product.outcome import InvalidSpec
    from aisef2.quality import test_execution as te
    from validation.qualification import p5_acceptance as pa
    aid = pa._aid()
    reqs, real, contracts = aid.requirements(), pa.load_approvals(), pa.contracts()
    refs = {k: ProbeRef(e.probe_id, e.probe_digest) for k, e in catalog.active().items()}
    specs = {sid: compile_spec(c, requirements=reqs, approvals=real, probes=refs) for sid, c in contracts.items()}
    plan = aid.build()["plan"]
    if plan.plan_hash != pa.ACCEPTED["plan_hash"]:
        raise SystemExit("the plan is not the owner-approved one")
    by_id = {s.id: (sid, s) for sid, s in specs.items()}
    # the harness wiring C2-ORCHESTRATION-CONFORMANCE-REPAIR requires: every registered probe by id, the catalog's own constructor
    factories = {e.probe_id: (lambda on_range, scratch, f=e.factory: f(on_range=on_range, scratch=scratch)) for e in catalog.CATALOG}
    graph = aid.story_graph()
    env = ExecutionEnv(sys.executable, 30.0, Enforcement.PARTIAL)
    stories = {}
    for story in sorted({o.story_id for o in plan.obligations}):
        sids = sorted({by_id[o.product_proof_spec_id][0] for o in plan.obligations if o.story_id == story})
        pids = sorted({specs[s].probe_id for s in sids})
        inputs = sr.StoryInputs({specs[s].id: specs[s] for s in sids}, factories, env,
                                te.DeveloperTests(story, ("tests/test_ledger.py",)), te.DeveloperTests(story, ("tests/test_ledger.py",)),
                                te.Dependencies(frozenset(), frozenset({"ledgerlock", "tests"})), te.UNITTEST)
        resolved = {}
        for s in sids:     # a party resolves each spec's own probe (story_runner._probe with the spec)
            try:
                probe = sr._probe(inputs, None, None, specs[s])
                resolved[s] = None if probe is None else [probe.id, probe.digest]
            except InvariantError as e:
                resolved[s] = f"{type(e).__name__}: {e}"
        party = {"accepted": all(resolved[s] == [specs[s].probe_id, specs[s].probe_digest] for s in sids),
                 "resolved_by_spec": resolved}
        # the one probe a single factory yields, given a spec of the story bound to another identity
        single = factories[pids[0]](None, None)
        foreign = next((s for s in sids if specs[s].probe_id != single.id), None)
        crossed = None
        if foreign:
            r = run_probe(single, specs[foreign], RevisionRef(FIXTURE_REVISION, str(ROOT)), env).result
            crossed = {"probe": single.id, "spec": foreign, "spec_probe": specs[foreign].probe_id, "result": type(r).__name__,
                       "invalid_spec": isinstance(r, InvalidSpec), "detail": getattr(r, "detail", "")[:300]}
        stories[story] = {"specs": sids, "obligations": sum(1 for o in plan.obligations if o.story_id == story),
                          "probe_ids": pids, "kinds": len(pids), "depends_on": sorted(graph.get(story, ())),
                          "orchestration_party_probe": party, "single_probe_on_a_foreign_spec": crossed,
                          "provable_by_the_current_path": party["accepted"]}
    blocked = sorted(s for s, v in stories.items() if not v["provable_by_the_current_path"])
    reachable = sorted(s for s, v in stories.items() if v["provable_by_the_current_path"] and not set(v["depends_on"]) & set(blocked))
    return {"plan": {"id": plan.id, "plan_hash": plan.plan_hash, "stories": len(stories), "obligations": len(plan.obligations)},
            "approvals": {"count": len(real), "approver": sorted({a.approver for a in real})},
            "stories": stories, "blocked_stories": blocked, "runnable_and_unblocked": reachable,
            "orchestration_source": {"path": "aisef2/orchestrate/story_runner.py", "sha256": C.lf_sha(ROOT / "aisef2/orchestrate/story_runner.py"),
                                     "rule_measured": "story_runner._probe(inputs, on_range, scratch, spec): the factory of the spec's own probe "
                                                      "identity (C2-ORCHESTRATION-CONFORMANCE-REPAIR); run_probe still refuses a spec "
                                                      "bound to another probe identity (InvalidSpec)"}}


def run() -> dict:
    started = time.monotonic()
    m = measure()
    stop = bool(m["blocked_stories"])
    rec = {
        "record": "AISEF V2 — QP-2.9 PREFLIGHT: can the current authoritative path prove the owner-approved LedgerLock PLAN-V2.2?",
        "authority": "owner ruling 2026-09-30 (QP-2.9 authorized after QP-2.8; global stop rules)",
        "subject": {"head": C.git("rev-parse", "HEAD"), "aisef2_tree": C.git("rev-parse", "HEAD:aisef2"),
                    "semantic_candidate": C.CYCLE2_SEMANTIC_CANDIDATE, "kernel_tree": C.CYCLE2_KERNEL_TREE},
        "benchmark_class": "DEVELOPMENT_REGRESSION", "generalization": "NONE", "plan_quality_policy": "DO_NOT_PREREGISTER (DECISION-5)",
        **m,
        "model_calls": 0, "subjects_executed": 0,
        "stop": {"triggered": stop, "rule": TRIGGER if stop else None,
                 "what_it_would_take": "an orchestration change in story_runner (a probe factory per spec's probe identity instead of "
                                       "exactly one per story) — a separate owner decision; not implemented here" if stop else None},
        "verdict": ("QP-2.9 STOPPED BEFORE EXECUTION — STOP RULE: proving a PLAN-V2.2 story whose specs span more than one probe kind "
                    "requires an orchestration change") if stop else "PREFLIGHT PASSED — every story provable by the current path",
        "seconds": round(time.monotonic() - started, 1), "at": C.now(),
    }
    C.write(OUT_REL, rec)
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", action="store_true", required=True)
    ap.parse_args(argv)
    rec = run()
    print(rec["verdict"])
    for s, v in rec["stories"].items():
        print(f"  {s}: {v['probe_ids']} provable={v['provable_by_the_current_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
