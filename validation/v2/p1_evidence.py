"""P1 evidence records — computed from the code, never written by hand, with a --check twin.

Every record carries `properties`: named facts measured on the implementation. `--check` re-derives each record and
fails if it differs from the committed one **or** if any property is false, so a record cannot certify a property
the code no longer has.

    python -P validation/v2/p1_evidence.py            # write every record whose package is implemented
    python -P validation/v2/p1_evidence.py --check    # fail on drift or on a false property
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import pathlib
import sys
from typing import Callable

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _module(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _rfc():
    fc = _module("aisef_v2_freeze_conformance", "validation/v2/freeze_conformance.py")
    return fc.RFC((ROOT / fc.RFC_REL).read_text(encoding="utf-8"))


def _raises(fn: Callable, *exc: type[BaseException]) -> bool:
    try:
        fn()
    except exc:
        return True
    return False


# --------------------------------------------------------------------------------------- WP-1.1

def contract_shapes() -> dict:
    from aisef2.arch.enums import Polarity, SubjectAbsence, SubjectKind
    from aisef2.product.approval import ContractApproval, Requirement, UnapprovedContract, require_approved
    from aisef2.product.contract import BehaviorContract, ContractError, Subject
    ks = _module("aisef_v2_kernel_static_checks", "validation/v2/kernel_static_checks.py")
    rfc = _rfc()
    base = dict(id="BC-REF", requirement_ids=("REQ-REF",), subject=Subject(SubjectKind.CLI_INVOCATION, "app.cli:main"),
                stimulus={"argv": ["--quiet"]}, observable={"stdout": "empty"}, polarity=Polarity.MUST_NOT_HOLD,
                subject_absence=SubjectAbsence.REQUIRES_SUBJECT, rationale="reference contract")
    ref = BehaviorContract.create(**base)
    req = Requirement.create(id="REQ-REF", text="reference requirement", source="evidence")
    ok = ContractApproval(req.id, req.requirement_hash, ref.id, ref.contract_hash, "human:evidence", 0.0, ())
    variants = {"id": "BC-X", "requirement_ids": ("REQ-REF", "REQ-X"),
                "subject": Subject(SubjectKind.CLI_INVOCATION, "app.cli:other"), "stimulus": {"argv": []},
                "observable": {"stdout": "x"}, "polarity": Polarity.MUST_HOLD,
                "subject_absence": SubjectAbsence.ABSENCE_IS_DECIDABLE, "rationale": "reworded"}
    bound = {f: BehaviorContract.create(**{**base, f: v}).contract_hash != ref.contract_hash for f, v in variants.items()}
    named = ["tests/test_cli.py", "pkg.tests.test_cli", "cli_test.py", "conftest.py", "x.py::test_a", "pytest"]
    edited_req = Requirement.create(id="REQ-REF", text="edited", source="evidence")
    shapes = {c.__name__: {"rfc": rfc.dataclasses.get(c.__name__), "code": [f.name for f in dataclasses.fields(c)]}
              for c in (Requirement, ContractApproval, Subject, BehaviorContract)}
    return {
        "record": "AISEF V2 — P1 CONTRACT SHAPES", "work_package": "WP-1.1", "rfc_sections": ["6", "7"],
        "shapes": shapes,
        "reference_contract_hash": ref.contract_hash,
        "contract_hash_bound_fields": bound,
        "properties": {
            "shapes_equal_rfc": all(s["rfc"] == s["code"] for s in shapes.values()),
            "contract_hash_binds_every_field": set(bound) == {f.name for f in dataclasses.fields(BehaviorContract)}
                                               - {"contract_hash"} and all(bound.values()),
            "contract_hash_binds_subject_absence": bound["subject_absence"],
            "rationale_edit_detected": _raises(lambda: dataclasses.replace(ref, rationale="edited"), ContractError),
            "supplied_hash_verified": _raises(lambda: BehaviorContract(**base, contract_hash="0" * 64), ContractError),
            "json_round_trip_is_identity": BehaviorContract.from_json(json.loads(json.dumps(ref.to_json()))) == ref,
            "approval_binds_both_hashes": not _raises(lambda: require_approved(ref, {req.id: req}, [ok]),
                                                      UnapprovedContract),
            "requirement_edit_invalidates_approval": _raises(
                lambda: require_approved(ref, {req.id: edited_req}, [ok]), UnapprovedContract),
            "contract_edit_invalidates_approval": _raises(
                lambda: require_approved(BehaviorContract.create(**{**base, "rationale": "x"}), {req.id: req}, [ok]),
                UnapprovedContract),
            "unapproved_contract_refused": _raises(lambda: require_approved(ref, {req.id: req}, []), UnapprovedContract),
            "model_cannot_approve": _raises(lambda: ContractApproval(req.id, req.requirement_hash, ref.id,
                                                                     ref.contract_hash, "model:any", 0.0, ()),
                                            ContractError),
            "test_artefacts_rejected": all(_raises(lambda n=n: Subject(SubjectKind.PYTHON_CALLABLE, n), ContractError)
                                           for n in named),
            "subject_absence_never_inferred": _raises(lambda: BehaviorContract.create(**{**base, "subject_absence": None}),
                                                      ContractError),
            "no_prose_control": ks.check(ROOT, ("NO_PROSE_CONTROL",)) == [],
        },
    }


# --------------------------------------------------------------------------------------- WP-1.2

def spec_compiler() -> dict:
    import os
    import subprocess
    from aisef2.arch.enums import BehaviorVerdict, Polarity, SubjectAbsence, SubjectKind
    from aisef2.product.approval import ContractApproval, Requirement, UnapprovedContract
    from aisef2.product.compiler import COMPILER_DIGEST, COMPILER_ID, COMPILER_SOURCES, ProbeRef, compile_spec
    from aisef2.product.contract import BehaviorContract, Subject
    from aisef2.product.spec import ProductProofSpec
    gs = _module("aisef_v2_gen_specs", "validation/v2/gen_specs.py")
    rfc = _rfc()
    req = Requirement.create(id="R", text="evidence", source="WP-1.2")
    probes = {SubjectKind.CLI_INVOCATION: ProbeRef("probe.cli", "c" * 64)}
    base = dict(id="C", requirement_ids=("R",), subject=Subject(SubjectKind.CLI_INVOCATION, "app.cli:main"),
                stimulus={"argv": ["--quiet"]}, observable={"stream": "stdout"}, polarity=Polarity.MUST_NOT_HOLD,
                subject_absence=SubjectAbsence.REQUIRES_SUBJECT, rationale="evidence")

    def compiled(probes=probes, **over):
        c = BehaviorContract.create(**{**base, **over})
        a = ContractApproval("R", req.requirement_hash, c.id, c.contract_hash, "human:evidence", 0.0, ())
        return compile_spec(c, requirements={"R": req}, approvals=[a], probes=probes)

    ref = compiled()
    semantic = {"subject": dict(subject=Subject(SubjectKind.CLI_INVOCATION, "app.cli:x")),
                "stimulus": dict(stimulus={"argv": []}), "observable": dict(observable={"stream": "stderr"}),
                "polarity": dict(polarity=Polarity.MUST_HOLD),
                "subject_absence": dict(subject_absence=SubjectAbsence.ABSENCE_IS_DECIDABLE)}
    changes = {k: compiled(**v).semantic_hash != ref.semantic_hash for k, v in semantic.items()}
    changes["probe_digest"] = compiled(probes={SubjectKind.CLI_INVOCATION: ProbeRef("probe.cli", "d" * 64)}
                                       ).semantic_hash != ref.semantic_hash
    corpus = gs.derive(ROOT / gs.CORPUS_REL)
    code = ("import sys, json; sys.path[:0] = [sys.argv[1], sys.argv[1] + '/validation/v2']; import gen_specs;"
            "print(json.dumps(gen_specs.derive(gen_specs.ROOT / gen_specs.CORPUS_REL), sort_keys=True))")
    runs = {seed: subprocess.run([sys.executable, "-I", "-c", code, str(ROOT)], capture_output=True, encoding="utf-8",
                                 env={**os.environ, "PYTHONHASHSEED": seed}, check=True).stdout.strip()
            for seed in ("0", "1", "2024")}
    specs = {cid: json.loads(text) for cid, text in corpus.items()}
    fields = [f.name for f in dataclasses.fields(ProductProofSpec)]
    return {
        "record": "AISEF V2 — P1 SPEC COMPILER", "work_package": "WP-1.2", "rfc_sections": ["8", "35"],
        "compiler": {"id": COMPILER_ID, "digest": COMPILER_DIGEST, "sources": list(COMPILER_SOURCES)},
        "corpus": {cid: {"spec_id": s["id"], "semantic_hash": s["semantic_hash"],
                         "candidate_expectation": s["candidate_expectation"],
                         "subject_absence": s["probe_input"]["subject_absence"]} for cid, s in sorted(specs.items())},
        "semantic_hash_changes_with": changes,
        "cross_process": {"seeds": sorted(runs), "identical": len(set(runs.values())) == 1},
        "properties": {
            "shape_equals_rfc": fields == rfc.dataclasses.get("ProductProofSpec"),
            "no_plan_fact": not {"story_id", "plan_id", "expected_parent", "parent_expectation"} & set(fields),
            "plan_field_is_a_type_error": _raises(lambda: dataclasses.replace(ref, story_id="S"), TypeError),
            "expectation_follows_polarity": compiled(polarity=Polarity.MUST_HOLD).candidate_expectation
                                            is BehaviorVerdict.SATISFIED
                                            and ref.candidate_expectation is BehaviorVerdict.REFUTED,
            "unapproved_contract_cannot_compile": _raises(lambda: compile_spec(
                BehaviorContract.create(**base), requirements={"R": req}, approvals=[], probes=probes),
                UnapprovedContract),
            "every_semantic_change_changes_semantic_hash": all(changes.values()),
            "semantic_hash_binds_subject_absence": changes["subject_absence"],
            "prose_edit_keeps_semantic_hash": compiled(rationale="reworded").semantic_hash == ref.semantic_hash,
            "deterministic_across_processes": len(set(runs.values())) == 1
                                              and json.loads(next(iter(runs.values()))) == corpus,
            "check_round_trip_byte_identical": gs.check() == [],
        },
    }


# --------------------------------------------------------------------------------------- WP-1.3

def outcome_polarity() -> dict:
    from aisef2.arch.enums import BehaviorVerdict as V, ContractSatisfaction as CS, ProbeExecutionStatus
    from aisef2.errors import InvariantError
    from aisef2.product.outcome import (Executed, IndeterminateReason, InvalidSpec, Unrunnable,
                                        contract_satisfaction, on_subject_absent)
    from aisef2.product.spec import ProductProofSpec
    fc = _module("aisef_v2_freeze_conformance", "validation/v2/freeze_conformance.py")
    ks = _module("aisef_v2_kernel_static_checks", "validation/v2/kernel_static_checks.py")
    corpus = ROOT / "tests/v2/fixtures/p1/corpus/specs"

    def spec(cid):
        return ProductProofSpec.from_json(json.loads((corpus / f"{cid}.json").read_text(encoding="utf-8")))

    def neg(case, cid, observed, observation):
        s = spec(cid)
        sat = contract_satisfaction(observed, s)
        return {"case": case, "contract": cid, "candidate_expectation": s.candidate_expectation.value,
                "subject_absence": s.probe_input["subject_absence"], "observation": observation,
                "observed_verdict": observed.behavior_verdict.value,
                "reason": observed.reason and observed.reason.value, "contract_satisfaction": sat.value}

    # P1 has no probe: the one physical fact "the subject is not there", as the existence observable sees it.
    absent = V.REFUTED
    decidable = [spec(c) for c in ("BC-LICENSE", "BC-NO-TELEMETRY")]
    cases = [neg("NEG-1", "BC-QUIET-STDOUT", Executed(V.SATISFIED), "fixture: the CLI writes to stdout"),
             neg("NEG-2", "BC-NO-TELEMETRY", on_subject_absent(spec("BC-NO-TELEMETRY"), observed=absent),
                 "fixture: existence observable over the absent module -> REFUTED"),
             neg("NEG-3", "BC-QUIET-STDOUT", on_subject_absent(spec("BC-QUIET-STDOUT"), observed=None),
                 "none: REQUIRES_SUBJECT, the subject is absent")]
    same_absence = {s.contract_id: contract_satisfaction(on_subject_absent(s, observed=absent), s).value
                    for s in decidable}
    oracle = fc._satisfaction_matches_rfc(_rfc())
    return {
        "record": "AISEF V2 — P1 OUTCOME POLARITY", "work_package": "WP-1.3", "rfc_sections": ["10", "10.1", "10.2"],
        "neg_cases": cases,
        "same_absence_by_contract": same_absence,
        "note": "NEG dispositions (READY / PRE_SATISFIED / PRECONDITION_BROKEN) are StoryAdmission's (WP-2.4); "
                "this record proves the satisfaction each disposition is routed on",
        "rfc_oracle": {"state": oracle["state"], "detail": oracle["detail"], "table": oracle.get("table")},
        "properties": {
            "NEG_1_unsatisfied_never_satisfied": cases[0]["contract_satisfaction"] == CS.UNSATISFIED.value,
            "NEG_2_satisfied": cases[1]["contract_satisfaction"] == CS.SATISFIED.value,
            "NEG_3_indeterminate_precondition_absent": cases[2]["contract_satisfaction"] == CS.INDETERMINATE.value
                                                       and cases[2]["reason"] == "PRECONDITION_ABSENT",
            "verdict_only_inside_executed": not hasattr(Unrunnable("x"), "behavior_verdict")
                                            and not hasattr(InvalidSpec("x"), "behavior_verdict"),
            "indeterminate_requires_typed_reason": _raises(lambda: Executed(V.INDETERMINATE), InvariantError),
            "satisfaction_undefined_without_execution": all(_raises(lambda r=r: contract_satisfaction(r, spec("BC-LICENSE")),
                                                                    InvariantError)
                                                            for r in (Unrunnable("x"), InvalidSpec("x"))),
            "satisfaction_equals_rfc_function": oracle["state"] == "PASS",
            "absence_is_an_observation_never_unrunnable": all(
                on_subject_absent(spec(c), observed=seen).status is ProbeExecutionStatus.EXECUTED
                for c, seen in (("BC-QUIET-STDOUT", None), ("BC-NO-TELEMETRY", absent), ("BC-VERSION", None),
                                ("BC-LICENSE", absent))),
            "requires_subject_absent_is_indeterminate_precondition_absent": all(
                on_subject_absent(spec(c), observed=None) == Executed(V.INDETERMINATE,
                                                                      IndeterminateReason.PRECONDITION_ABSENT)
                for c in ("BC-QUIET-STDOUT", "BC-VERSION")),
            "requires_subject_refuses_a_vacuous_verdict": all(
                _raises(lambda v=v: on_subject_absent(spec("BC-VERSION"), observed=v), InvariantError) for v in V),
            "decidable_absence_verdict_is_the_observation": all(
                on_subject_absent(s, observed=v) == Executed(v) for s in decidable for v in (V.SATISFIED, V.REFUTED)),
            "decidable_absence_has_no_default_verdict": all(
                _raises(lambda s=s, v=v: on_subject_absent(s, observed=v), InvariantError)
                for s in decidable for v in (None, V.INDETERMINATE)),
            "same_absence_positive_existence_unsatisfied_negative_existence_satisfied":
                same_absence == {"BC-LICENSE": CS.UNSATISFIED.value, "BC-NO-TELEMETRY": CS.SATISFIED.value},
            "no_kernel_code_infers_a_verdict_from_the_absence_declaration":
                ks.check(ROOT, ("NO_VERDICT_FROM_ABSENCE_DECLARATION",)) == [],
            "no_planning_module_routes_on_raw_verdict": ks.check(ROOT, ("NO_RAW_VERDICT_ROUTING",)) == [],
        },
    }


# --------------------------------------------------------------------------------------- WP-1.4

def routing_table() -> dict:
    import itertools
    from aisef2.arch.enums import (BehaviorVerdict as V, MeasurementPoint as MP, ObligationRole, Owner,
                                   ProbeExecutionStatus, StoryAdmissionDisposition)
    from aisef2.control.owner import TAXONOMY, FailureCode, Retryability, classify
    from aisef2.control.routing import UnroutableOutcome, route
    from aisef2.errors import InvariantError
    from aisef2.product.outcome import (Executed, IndeterminateReason, InvalidSpec, Unrunnable, contract_satisfaction,
                                        on_subject_absent)
    from aisef2.product.spec import ProductProofSpec
    fc = _module("aisef_v2_freeze_conformance", "validation/v2/freeze_conformance.py")
    ks = _module("aisef_v2_kernel_static_checks", "validation/v2/kernel_static_checks.py")
    specs = {p.stem: ProductProofSpec.from_json(json.loads(p.read_text(encoding="utf-8")))
             for p in sorted((ROOT / "tests/v2/fixtures/p1/corpus/specs").glob("*.json"))}
    results = [None, Unrunnable("x"), InvalidSpec("x"), Executed(V.SATISFIED), Executed(V.REFUTED),
               Executed(V.INDETERMINATE, IndeterminateReason.PRECONDITION_ABSENT)]
    rows = []
    for point, result, (cid, spec), role in itertools.product(MP, results, specs.items(), ObligationRole):
        r = route(result, spec, point, role)
        executed = isinstance(result, Executed)
        rows.append({"point": point.value, "role": role.value, "spec": cid,
                     "candidate_expectation": spec.candidate_expectation.value,
                     "status": result.status.value if result else None,
                     "verdict": result.behavior_verdict.value if executed else None,
                     "reason": result.reason.value if executed and result.reason else None,
                     "satisfaction": contract_satisfaction(result, spec).value if executed else None,
                     "code": r.failure.code.value if r.failure else None,
                     "owner": r.failure.owner.value if r.failure else None,
                     "retryability": r.failure.retryability.value if r.failure else None,
                     "budget": r.failure.budget.value if r.failure and r.failure.budget else None,
                     "disposition": r.disposition.value if r.disposition else None,
                     "decided_by": r.decided_by})
    by_key = {}
    for row in rows:
        if row["satisfaction"]:
            by_key.setdefault((row["point"], row["role"], row["satisfaction"], row["reason"]), set()).add(
                (row["code"], row["disposition"], row["decided_by"]))
    absent = on_subject_absent(specs["BC-QUIET-STDOUT"], observed=None)  # a REQUIRES_SUBJECT contract, subject absent

    def at(point, role, result=absent):
        return route(result, specs["BC-QUIET-STDOUT"], point, role)
    mp1, mp2 = at(MP.PARENT, ObligationRole.INTRODUCE), at(MP.CANDIDATE, ObligationRole.INTRODUCE)
    mp3 = at(MP.POST_MERGE, ObligationRole.INTRODUCE)
    mp4 = [at(p, r, Unrunnable("x")) for p, r in itertools.product(MP, ObligationRole)]
    missing, invalid = classify(FailureCode.MISSING_CREDENTIAL), classify(FailureCode.INVALID_CREDENTIAL)
    outage = classify(FailureCode.PROVIDER_UNAVAILABLE)
    oracle = fc._routing_matches_rfc(_rfc())
    return {
        "record": "AISEF V2 — P1 ROUTING TABLE", "work_package": "WP-1.4", "rfc_sections": ["22", "10", "10.3"],
        "amended_by": "ARCHITECTURE-EXCEPTION-V2-001",
        "taxonomy": {c.value: {"owner": TAXONOMY[c].owner.value, "retryability": TAXONOMY[c].retryability.value,
                               "budget": TAXONOMY[c].budget.value if TAXONOMY[c].budget else None,
                               "rule": TAXONOMY[c].rule} for c in FailureCode},
        "retry_count": "not in the taxonomy — the resolved execution policy (RunSpec / project / evaluation "
                       "configuration) supplies it",
        "owner_mp": {"OWNER-MP-1": {"owner": None if not mp1.failure else mp1.failure.owner.value,
                                    "disposition": mp1.disposition and mp1.disposition.value},
                     "OWNER-MP-2": mp2.failure.owner.value, "OWNER-MP-3": mp3.failure.owner.value,
                     "OWNER-MP-4": sorted({r.failure.owner.value for r in mp4})},
        "routing": rows,
        "rfc_table_comparison": {"state": oracle["state"], "detail": oracle["detail"]},
        "properties": {
            "routing_total_over_legal_space": len(rows) == len(MP) * len(results) * len(specs) * len(ObligationRole),
            "routing_equals_rfc_tables": oracle["state"] == "PASS",
            "OWNER_MP_1_parent_introduce_ready_no_owner": mp1.failure is None
                                                          and mp1.disposition is StoryAdmissionDisposition.READY,
            "OWNER_MP_2_candidate_subject_absent_developer": mp2.failure.owner is Owner.DEVELOPER,
            "OWNER_MP_3_post_merge_subject_lost_integration": mp3.failure.owner is Owner.INTEGRATION,
            "OWNER_MP_4_unrunnable_environment_everywhere": all(r.failure.owner is Owner.ENVIRONMENT for r in mp4),
            "parent_preserve_verify_precondition_broken_plan": all(
                at(MP.PARENT, role).failure.owner is Owner.PLAN for role in (ObligationRole.PRESERVE, ObligationRole.VERIFY)),
            "reason_alone_never_decides_owner": len({r["owner"] for r in rows if r["reason"]}) > 1,
            "CRED_1_missing_never_developer_budget": missing.owner is Owner.ENVIRONMENT and missing.budget is not Owner.DEVELOPER,
            "CRED_2_invalid_never_developer_or_provider_budget": invalid.owner is Owner.ENVIRONMENT
                                                                 and invalid.budget not in (Owner.DEVELOPER, Owner.PROVIDER),
            "CRED_3_invalid_not_retryable": invalid.retryability is Retryability.NOT_RETRYABLE,
            "CRED_4_provider_outage_distinct": outage.owner is Owner.PROVIDER and invalid.owner is not Owner.PROVIDER
                                               and outage.code is not invalid.code,
            "refuted_never_environment": all(r["owner"] != "ENVIRONMENT" for r in rows if r["verdict"] == "REFUTED"),
            "only_unrunnable_routes_to_environment": all((r["owner"] == "ENVIRONMENT") == (r["status"] == "UNRUNNABLE")
                                                         for r in rows),
            "unrunnable_never_developer": all(r["owner"] != "DEVELOPER" for r in rows if r["status"] == "UNRUNNABLE"),
            "no_did_not_run_to_developer_edge": all(r["owner"] != "DEVELOPER" for r in rows
                                                    if r["status"] != ProbeExecutionStatus.EXECUTED.value),
            "routes_on_satisfaction_never_raw_verdict": all(len(v) == 1 for v in by_key.values()),
            "unmapped_outcome_fails_closed": _raises(lambda: route(object(), specs["BC-VERSION"], MP.CANDIDATE),
                                                     UnroutableOutcome)
                                             and _raises(lambda: route(absent, specs["BC-QUIET-STDOUT"], MP.PARENT),
                                                         UnroutableOutcome)
                                             and _raises(lambda: classify("DEVELOPER"), InvariantError),
            "owner_set_exactly_F3": [o.value for o in Owner] == _rfc().enums.get("Owner"),
            "every_taxonomy_owner_in_F3": all(isinstance(TAXONOMY[c].owner, Owner) for c in FailureCode),
            "retryable_only_in_taxonomy": ks.check(ROOT, ("RETRYABLE_ONLY_IN_TAXONOMY",)) == [],
            "no_raw_verdict_routing": ks.check(ROOT, ("NO_RAW_VERDICT_ROUTING",)) == [],
        },
    }


#: package -> (record path, builder, module that must exist before the record is built)
BUILDERS: dict[str, tuple[str, Callable[[], dict], str]] = {
    "WP-1.1": ("closure-evidence/v2/P1-CONTRACT-SHAPES.json", contract_shapes, "aisef2/product/contract.py"),
    "WP-1.2": ("closure-evidence/v2/P1-SPEC-COMPILER.json", spec_compiler, "aisef2/product/compiler.py"),
    "WP-1.3": ("closure-evidence/v2/P1-OUTCOME-POLARITY.json", outcome_polarity, "aisef2/product/outcome.py"),
    "WP-1.4": ("closure-evidence/v2/P1-ROUTING-TABLE.json", routing_table, "aisef2/control/routing.py"),
}


def render(record: dict) -> str:
    return json.dumps(record, indent=1, ensure_ascii=False) + "\n"


def problems_of(record: dict) -> list[str]:
    props = record.get("properties") or {}
    out = [] if props else [f"{record.get('work_package')}: record carries no properties"]
    return out + [f"{record.get('work_package')}: property {k} is false" for k, v in props.items() if v is not True]


def check(root: pathlib.Path = ROOT) -> list[str]:
    out = []
    for rel, build, needs in BUILDERS.values():
        if not (root / needs).exists():
            continue
        fresh = build()
        out += problems_of(fresh)
        committed = root / rel
        if not committed.exists():
            out.append(f"{rel} is missing")
        elif committed.read_text(encoding="utf-8") != render(fresh):
            out.append(f"{rel} is stale: regenerate it")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--check" in argv:
        problems = check()
    else:
        problems = []
        for rel, build, needs in BUILDERS.values():
            if (ROOT / needs).exists():
                record = build()
                problems += problems_of(record)
                if not problems_of(record):
                    (ROOT / rel).write_text(render(record), encoding="utf-8")
                    print(f"wrote {rel}")
    for p in problems:
        print(f"FAIL  {p}")
    print("p1 evidence: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
