"""Q2 — adequacy (RFC §27; owner §12–§15): product mutation on the exact candidate, probe capability calibration for
every probe digest and observation class in use, spec falsifiability, and the WP-5 engineering-quality properties
reconfirmed without turning them into product proof.

Mutation is not re-run here: the records were measured on the candidate's exact sources and each target carries the
source digest of the file it mutated; `mutation.check` re-derives every digest against this tree and fails closed on
any drift, any unaudited survivor, and any target with no mutants. Every timeout kill is named in the record.
"""

from __future__ import annotations

import dataclasses
import json
import sys
import time

from . import common as C

FIXTURES_REL = "tests/v2/fixtures/calibration"
SENSITIVITY_RFC_ROW = ("Engineering-test **sensitivity** (mutation at story scope) | when Q2 mutation infrastructure is stable "
                       "and its cost per story is measured")
QUALITY_MODULES = ("tests.v2.p5.test_test_execution", "tests.v2.p5.test_relevance", "tests.v2.p5.test_vacuity", "tests.v2.p5.test_adequacy")
QUALITY_PROPERTIES = {
    "TestExecution_two_axis_semantics": [("tests.v2.p5.test_test_execution", "Shape", "test_UNRUNNABLE_carries_no_outcome_no_selection_and_only_the_environment_owner"),
                                         ("tests.v2.p5.test_test_execution", "Shape", "test_EXECUTED_owner_follows_outcome_and_selection"),
                                         ("tests.v2.p5.test_test_execution", "Classify", "test_no_did_not_run_to_developer_edge_exists")],
    "relevance": [("tests.v2.p5.test_relevance", "Typed", "test_REL_1_an_executed_story_test_intersecting_a_changed_executable_line_is_RELEVANT"),
                  ("tests.v2.p5.test_relevance", "Typed", "test_REL_3_coverage_capability_unavailable_is_UNMEASURABLE_never_IRRELEVANT"),
                  ("tests.v2.p5.test_relevance", "ForReal", "test_REL_1_for_real")],
    "vacuity": [("tests.v2.p5.test_vacuity", "ForReal", "test_VAC_1_a_story_test_that_fails_by_assertion_once_the_product_change_is_neutralised_is_NON_VACUOUS"),
                ("tests.v2.p5.test_vacuity", "ForReal", "test_VAC_2_a_story_test_that_still_passes_is_VACUOUS")],
    "adequacy": [("tests.v2.p5.test_adequacy", "Exhaustive", "test_assembly_is_total_and_follows_the_precedence"),
                 ("tests.v2.p5.test_adequacy", "Exhaustive", "test_owner_blocking_and_charge_are_read_from_the_typed_facts_only")],
    "no_parent_developer_artefact": [("tests.v2.p5.test_vacuity", "ForReal", "test_VAC_12_an_unrunnable_parent_changes_nothing_because_the_parent_is_never_executed"),
                                     ("tests.v2.p5.test_vacuity", "Typed", "test_invariant_IX_is_structural"),
                                     ("tests.v2.p5.test_invariants", "NoDeveloperArtefactAtParent", None)],
    "INCOMPLETE_nonblocking": [("tests.v2.p5.test_adequacy", "Cases", "test_ADEQ_11_INDETERMINATE_vacuity_alone_is_INCOMPLETE_non_blocking_uncharged"),
                               ("tests.v2.p5.test_adequacy", "Cases", "test_ADEQ_12_UNMEASURABLE_relevance_alone_is_INCOMPLETE_non_blocking_uncharged"),
                               ("tests.v2.p5.test_adequacy", "Separation", "test_no_policy_object_decides_adequacy_blocking_and_INCOMPLETE_cannot_block_under_any"),
                               ("tests.v2.test_p6_stages", "Quality", "test_INCOMPLETE_is_recorded_and_never_a_failure")],
    "UNRUNNABLE_no_AdequacyOutcome": [("tests.v2.p5.test_adequacy", "Cases", "test_ADEQ_2_primary_UNRUNNABLE_has_no_outcome_and_the_environment_owner_the_typed_fact_carries"),
                                      ("tests.v2.p5.test_adequacy", "Cases", "test_ADEQ_3_regression_UNRUNNABLE_has_no_outcome_and_keeps_the_environment_owner"),
                                      ("tests.v2.test_p6_stages", "Quality", "test_UNRUNNABLE_is_TESTS_UNRUNNABLE_with_environment_provenance_and_no_outcome")],
    "no_path_to_product_proof": [("tests.v2.p5.test_adequacy", "Separation", "test_no_path_reaches_a_product_proof_a_journal_or_a_budget"),
                                 ("tests.v2.test_p6_orchestration", "Orchestration", "test_ORCH_14_a_change_of_engineering_adequacy_leaves_the_product_proof_unchanged")],
}


def _mutation() -> dict:
    import mutation as mt
    problems = mt.check(C.ROOT)
    phases = {}
    for phase, rel in mt.RECORDS.items():
        rec = json.loads((C.ROOT / rel).read_text(encoding="utf-8"))
        targets = rec["targets"]
        survivors = [{"target": t["target"], "mutant": s, "audit": mt.AUDITED.get((t["target"], s)),
                      "source_sha256": t["source_sha256"], "source_current": mt.source_digest(
                          (C.ROOT / t["target"].split("::")[0]).read_text(encoding="utf-8")) == t["source_sha256"]}
                     for t in targets for s in t.get("survivors", [])]
        timeouts = [{"target": t["target"], "mutant": r["mutant"], "timed_out": r["timed_out"]}
                    for t in targets for r in t.get("results", []) if r.get("timed_out")]
        phases[phase] = {"path": rel, "sha256": C.lf_sha(C.ROOT / rel), "targets": len(targets),
                         "mutants": sum(t["mutants"] for t in targets), "killed": sum(t["killed"] for t in targets),
                         "survivors": survivors, "unaudited": [s for s in survivors if not s["audit"]],
                         "killed_by_timeout_named": len(timeouts), "timeouts": timeouts,
                         "errors": [t["target"] for t in targets if t.get("error")]}
    audited_outside_refmodel = sorted(k[0] for k in mt.AUDITED if not k[0].startswith("tests/v2/refmodel/"))
    return {"check_problems": problems, "phases": phases,
            "totals": {"targets": sum(p["targets"] for p in phases.values()), "mutants": sum(p["mutants"] for p in phases.values()),
                       "killed": sum(p["killed"] for p in phases.values()), "survivors": sum(len(p["survivors"]) for p in phases.values()),
                       "unaudited": sum(len(p["unaudited"]) for p in phases.values()),
                       "killed_by_timeout_named": sum(p["killed_by_timeout_named"] for p in phases.values())},
            "audited_equivalents_outside_the_reference_models": audited_outside_refmodel,
            "no_audit_targets": sorted(mt.NO_AUDIT), "kernel_tree": C.KERNEL_TREE,
            "binding": "every target carries the sha256 of the source it mutated; mutation.check re-derives each against this tree"}


def _calibration() -> dict:
    """Owner §13: fresh, at the candidate, for every probe digest and observation class in use."""
    from aisef2.arch.enums import BehaviorVerdict as V
    from aisef2.probe import calibration as cal
    from aisef2.probe import python_callable as pc
    from aisef2.probe.protocol import ProbeRegistry
    probe = pc.PythonCallableProbe()
    registry = ProbeRegistry([pc.METADATA])
    env = cal.calibration_env(sys.executable)
    base = C.ROOT / FIXTURES_REL / "python_callable"
    fresh, problems = [], []
    for cls in pc.CLASSES:
        try:
            rec = cal.calibrate(probe, cls, base / cls / "positive", base / cls / "negative", env, time.time, registry=registry,
                                names=(f"{FIXTURES_REL}/python_callable/{cls}/positive", f"{FIXTURES_REL}/python_callable/{cls}/negative"))
            fresh.append({k: v for k, v in dataclasses.asdict(rec).items() if k != "demonstrated_at"} | {"qualified": True})
        except cal.NotQualified as e:
            fresh.append({"probe_id": probe.id, "probe_digest": probe.digest, "observation_class": cls, "qualified": False, "why": str(e)})
            problems.append(f"{cls}: {e}")
    committed = json.loads((C.ROOT / "closure-evidence/v2/P2-CALIBRATION.json").read_text(encoding="utf-8"))
    committed_keys = {(c["probe_id"], c["probe_digest"], c["observation_class"]) for c in committed["calibrations"]}
    in_use = {(pc.PROBE_ID, pc.DIGEST, cls) for cls in pc.CLASSES}
    fresh_keys = {(f["probe_id"], f["probe_digest"], f["observation_class"]) for f in fresh if f["qualified"]}
    contrast = {f"{e.value} expected, {o.value} observed": cal.demonstrates_contrast(e, o)
                for e in (V.SATISFIED, V.REFUTED) for o in (V.SATISFIED, V.REFUTED, V.INDETERMINATE)}
    if not in_use <= fresh_keys:
        problems.append(f"in use but not calibrated fresh: {sorted(in_use - fresh_keys)}")
    if committed_keys != in_use:
        problems.append(f"the committed calibration set differs from the classes in use: {sorted(committed_keys ^ in_use)}")
    return {"probe_digests_in_use": sorted({(p, d) for p, d, _ in in_use}), "observation_classes_in_use": list(pc.CLASSES),
            "fresh": fresh, "committed_record_keys": sorted(committed_keys), "in_use_all_calibrated_fresh": in_use <= fresh_keys,
            "old_digest_historical_only": all(c["probe_digest"] == pc.DIGEST for c in committed["calibrations"]),
            "contrast_table": contrast, "both_polarities_required": contrast["SATISFIED expected, REFUTED observed"]
            and contrast["REFUTED expected, SATISFIED observed"] and not contrast["SATISFIED expected, SATISFIED observed"]
            and not contrast["REFUTED expected, REFUTED observed"], "problems": problems}


def _falsifiability() -> dict:
    """Owner §14: SpecFalsifiabilityEvidence, by execution, for every spec that can back qualified product evidence
    (its probe is a registered executable probe); every other stored spec is classified mechanically, never waived."""
    from aisef2.arch.enums import BehaviorVerdict as V
    from aisef2.probe import calibration as cal
    from aisef2.probe import python_callable as pc
    from aisef2.probe.protocol import RevisionRef, bound_result, run_probe
    from aisef2.product.outcome import Executed
    from aisef2.product.spec import ProductProofSpec
    probe = pc.PythonCallableProbe()
    env = cal.calibration_env(sys.executable)
    base = C.ROOT / FIXTURES_REL / "python_callable"
    executable = {pc.PROBE_ID: pc.DIGEST}
    inventory, problems = [], []

    def walk(o, where):
        if isinstance(o, dict):
            if {"semantic_hash", "probe_id", "candidate_expectation", "probe_input"} <= set(o):
                kind = ("EXECUTABLE_PROBE_CURRENT_DIGEST" if executable.get(o["probe_id"]) == o.get("probe_digest")
                        else "EXECUTABLE_PROBE_HISTORICAL_DIGEST" if o["probe_id"] in executable
                        else "DECLARED_FIXTURE_PROBE_IDENTITY")
                inventory.append({"where": where, "spec_id": o.get("id"), "contract_id": o.get("contract_id"), "probe_id": o["probe_id"],
                                  "probe_digest": o.get("probe_digest"), "semantic_hash": o["semantic_hash"], "classification": kind})
            for k, v in o.items():
                walk(v, f"{where}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{where}[{i}]")
    for b in ("tests/v2/fixtures", "closure-evidence/v2"):
        for p in sorted((C.ROOT / b).rglob("*.json")):
            try:
                walk(json.loads(p.read_text(encoding="utf-8")), p.relative_to(C.ROOT).as_posix())
            except (ValueError, UnicodeDecodeError):
                continue
    for s in inventory:
        if s["classification"] == "EXECUTABLE_PROBE_CURRENT_DIGEST":
            problems.append(f"stored executable spec without a fixture to falsify it against: {s['where']} — Q2 cannot demonstrate it")
    # the specs that can back qualified product evidence in cycle 1 are the reference probe's, compiled from a
    # subject the harness can observe: one per observation class and polarity, falsified by the opposite fixture
    evidence = []
    for cls in pc.CLASSES:
        pos, neg = base / cls / "positive", base / cls / "negative"
        for side, fixture, counter, expectation in (("positive", pos, neg, V.SATISFIED), ("negative", neg, pos, V.REFUTED)):
            request = json.loads((fixture / "request.json").read_text(encoding="utf-8"))
            spec = ProductProofSpec.create(contract_id=f"QUALIFICATION:{cls}:{side}", probe_id=probe.id, probe_digest=probe.digest,
                                           probe_input=request, candidate_expectation=expectation, compiler_id="qualification",
                                           compiler_digest="0" * 64)
            at = RevisionRef(cal.FIXTURE_REVISION, str((counter / "checkout").resolve()))
            result = bound_result(run_probe(probe, spec, at, env), spec=spec, revision=at.sha, enforcement=probe.enforcement())
            observed = result.behavior_verdict if isinstance(result, Executed) else None
            ev = (cal.SpecFalsifiabilityEvidence(spec.id, spec.semantic_hash, "fixture_construction",
                                                 f"{FIXTURES_REL}/python_callable/{cls}/{'negative' if side == 'positive' else 'positive'}",
                                                 observed) if observed is not None else None)
            row = {"spec_id": spec.id, "semantic_hash": spec.semantic_hash, "probe_id": probe.id, "probe_digest": probe.digest,
                   "observation_class": cls, "candidate_expectation": expectation.value, "mechanism": "fixture_construction",
                   "counterexample_ref": ev.counterexample_ref if ev else None, "observed": observed.value if observed else repr(result),
                   "problems": cal.falsifiability_problems(ev, spec) if ev else ["the counterexample did not execute to a verdict"]}
            evidence.append(row)
            if row["problems"]:
                problems.append(f"{cls}/{side}: {row['problems']}")
    fields = [f.name for f in dataclasses.fields(ProductProofSpec)]
    plan_fields = [f for f in fields if "plan" in f or "story" in f or "obligation" in f]
    if plan_fields:
        problems.append(f"a plan fact is a ProductProofSpec field: {plan_fields}")
    return {"rule": "required for every spec whose probe is a registered executable probe; a declared fixture probe identity (fixture.*) "
                    "has no executable probe in the registry and can back no qualified product evidence — classified, not waived",
            "stored_spec_inventory": inventory,
            "inventory_counts": {k: sum(1 for s in inventory if s["classification"] == k)
                                 for k in ("EXECUTABLE_PROBE_CURRENT_DIGEST", "EXECUTABLE_PROBE_HISTORICAL_DIGEST", "DECLARED_FIXTURE_PROBE_IDENTITY")},
            "evidence": evidence, "product_proof_spec_fields": fields, "plan_fact_fields": plan_fields, "problems": problems}


def run(ident: dict) -> dict:
    import destructive_authority as da
    import p5_evidence as p5
    problems: list[str] = []
    harness: list[str] = []
    mutation, err = C.capture(_mutation)
    if err:
        harness.append(f"mutation records could not be read: {err}")
    else:
        problems += [f"mutation: {p}" for p in mutation["check_problems"]]
        if mutation["totals"]["unaudited"] or mutation["audited_equivalents_outside_the_reference_models"]:
            problems.append("an unaudited survivor, or an audit outside the reference models")
    authority = {"destructive_sites_problems": da.check(C.ROOT),
                 "cases": C.run_module("tests.v2.p4.test_mutation_safety") + C.run_module("tests.v2.p2.test_mutation_targets")
                 + C.run_module("tests.v2.p5.test_invariants", classes=("MutationAuthority",))}
    if authority["destructive_sites_problems"]:
        problems.append(f"destructive authority: {authority['destructive_sites_problems']}")
    calibration, err = C.capture(_calibration)
    if err:
        harness.append(f"calibration could not run: {err}")
    else:
        problems += [f"calibration: {p}" for p in calibration["problems"]]
    fixed_probes = C.run_module("tests.v2.p2.test_calibration")
    falsifiability, err = C.capture(_falsifiability)
    if err:
        harness.append(f"falsifiability could not run: {err}")
    else:
        problems += [f"falsifiability: {p}" for p in falsifiability["problems"]]
    quality_modules = [c for m in QUALITY_MODULES for c in C.run_module(m)]
    quality = {}
    for prop, refs in QUALITY_PROPERTIES.items():
        rows = []
        for module, cls, name in refs:
            rows += C.run_module(module, classes=(cls,)) if name is None else [C.run_case(module, cls, name)]
        quality[prop] = {"status": C.status_of(rows), "cases": rows}
    p5_identity = p5.check(C.ROOT)
    if p5_identity:
        problems.append(f"P5 records: {p5_identity}")
    cases = authority["cases"] + fixed_probes + quality_modules + [c for q in quality.values() for c in q["cases"]]
    return {
        "record": "AISEF V2 — Q2 ADEQUACY", "rung": "Q2", "status": C.status_of(cases, problems, harness), "at": C.now(),
        "subject": ident, "platform": C.platform_id(),
        "product_mutation": mutation, "inv_mutation_authority": authority,
        "probe_capability_calibration": calibration, "fixed_verdict_probes_rejected": {"counts": C.counts(fixed_probes), "cases": fixed_probes},
        "spec_falsifiability": falsifiability,
        "engineering_quality": {"properties": quality, "modules": {"counts": C.counts(quality_modules), "cases": quality_modules},
                                "sensitivity": {"status": "DEFERRED_BY_RFC", "rfc_row": SENSITIVITY_RFC_ROW,
                                                "scope": "not measured in Q2 cycle 1; not expanded (owner §15)"},
                                "p5_records_identity_problems": p5_identity},
        "provider_calls": 0, "problems": problems, "harness_problems": harness, "cases": cases, "counts": C.counts(cases),
    }
