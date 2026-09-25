"""P6 evidence records — computed from the code, never written by hand, with a --check twin (the P1–P5 contract).

WP-6.2 / ARCHITECTURE-EXCEPTION-V2-005: the record measures the amendment — journal format 3 (FMT3-1..8), the exact
nine failure codes of RFC §22.1, `budget_owner` on a format-3 provider request and the budgets projection that charges
it, the version-2 story_state, the reference models on format-3 traces, the lineage (V2-003 -> V2-005; V2-004
superseded, never applied), the sealed P5 records verified by identity, and the mutation results of every target the
amendment changed or added, by target. Each property is measured by running the named test case (the test is the
measurement); `--check` re-derives the record and fails if it differs from the committed one or if any property is
false. Records hold outcomes only — never a pid, a path, a duration or a wall-clock time.

    python -P validation/v2/p6_evidence.py            # write every record whose package is implemented
    python -P validation/v2/p6_evidence.py --check    # fail on drift or on a false property
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import sys
import unittest
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


def passed(case: unittest.TestCase) -> bool:
    """The named test ran and passed (a skip is not a pass)."""
    result = unittest.TestResult()
    case.run(result)
    return result.wasSuccessful() and result.testsRun == 1 and not result.skipped


def cases(module, cls: str, *names: str) -> dict[str, bool]:
    klass = getattr(module, cls)
    return {n: passed(klass(n)) for n in names}


def _lf_sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


#: The targets V2-005 changed (measured in their own phase's record) or added (P6).
V2_005_TARGET_MODULES = ("aisef2/control/owner.py", "aisef2/journal/event.py", "aisef2/journal/format3.py",
                         "aisef2/journal/projections/budgets.py", "aisef2/journal/projections/story_state.py",
                         "tests/v2/refmodel/budgets.py", "tests/v2/refmodel/story_state.py", "aisef2/runtime/run_scope.py",
                         "aisef2/runtime/sentinel.py", "aisef2/runtime/repair.py")


#: The orchestration path (WP-6.2) and the one format-3 function it added.
ORCHESTRATION_TARGET_MODULES = tuple(f"aisef2/orchestrate/{m}.py" for m in (
    "adapters", "gate", "merge", "proof", "quality", "review", "seam", "security", "story_runner", "workspace"))


def _mutation_by_target(modules: tuple[str, ...] = V2_005_TARGET_MODULES, functions: tuple[str, ...] = ()) -> dict:
    """Every mutation record's targets in `modules` (or the named `functions`), with currency and audited survivors."""
    mt = _module("aisef_v2_mutation", "validation/v2/mutation.py")
    out = {}
    for phase, rel in mt.RECORDS.items():
        p = ROOT / rel
        if not p.exists():
            continue
        for t in json.loads(p.read_text(encoding="utf-8"))["targets"]:
            if t["target"].split("::")[0] in modules or t["target"] in functions:
                survivors = list(t.get("survivors") or [])
                unaudited = [m for m in survivors if (t["target"], m) not in mt.AUDITED]
                out[t["target"]] = {"phase": phase, "mutants": t.get("mutants"), "killed": t.get("killed"),
                                    "survivors": len(survivors), "audited_equivalent": len(survivors) - len(unaudited),
                                    "unaudited": unaudited, "error": t.get("error"),
                                    "current": mt.source_digest((ROOT / t["target"].split("::")[0]).read_text(
                                        encoding="utf-8")) == t.get("source_sha256")}
    return dict(sorted(out.items()))


# --------------------------------------------------------------------------------------- WP-6.2 / V2-005

def v2_005_schema() -> dict:
    from aisef2.arch.enums import EventType as T
    from aisef2.control.owner import FORMAT_2_CODES, TAXONOMY, V2_005_CODES, FailureCode
    from aisef2.journal import event as ev, format2 as f2, format3 as f3
    from aisef2.journal.projections import PROJECTIONS
    t = _module("aisef_v2_test_v2_005", "tests/v2/test_v2_005.py")
    catalog = cases(t, "Catalog", "test_FMT3_1_every_event_type_has_a_format_3_schema",
                    "test_FMT3_2_a_missing_schema_fails_the_catalog_check_and_the_reader")
    compat = cases(t, "Compatibility",
                   "test_FMT3_3_every_format_1_and_format_2_journal_reads_identically_through_the_format_3_reader",
                   "test_FMT3_5_a_reader_reads_a_journal_under_its_declared_format_and_guesses_nothing",
                   "test_FMT3_7_no_format_1_or_format_2_journal_is_rewritten_extended_or_upgraded")
    schemas = cases(t, "Schemas", "test_FMT3_4_a_missing_required_field_refuses_the_append_before_the_log_grows",
                    "test_FMT3_6_a_format_3_provider_request_names_one_of_the_three_budget_owners",
                    "test_FMT3_8_the_context_of_an_invariant_violation_cannot_affect_any_projection",
                    "test_a_static_admission_is_the_typed_result_once_per_plan",
                    "test_a_proof_is_two_cited_sealed_records_with_one_instrument_and_the_agreement_they_state",
                    "test_an_adequacy_record_is_the_typed_assembly_under_the_two_axis_rules")
    taxonomy = cases(t, "Taxonomy", "test_FailureCode_is_exactly_the_thirteen_historical_codes_and_the_nine_of_V2_005",
                     "test_each_of_the_nine_has_one_owner_one_retryability_and_its_own_budget",
                     "test_no_call_site_supplies_owner_or_retryability_and_no_prose_becomes_a_code",
                     "test_formats_1_and_2_carry_only_the_thirteen_and_format_3_carries_all",
                     "test_the_conformance_subcheck_pins_the_table_and_rejects_a_swapped_owner_or_retryability")
    budgets = cases(t, "BudgetsV2",
                    "test_version_2_reads_the_declared_format_and_charges_a_format_3_request_to_its_budget_owner",
                    "test_nothing_defaults_a_missing_or_foreign_budget_owner_under_format_3",
                    "test_under_formats_1_and_2_every_request_is_the_developers_as_frozen",
                    "test_a_review_or_security_request_needs_the_admission_and_names_only_its_criteria",
                    "test_a_retry_charges_the_failures_own_owner_and_never_the_developer_for_review_or_security",
                    "test_the_reference_model_agrees_on_format_3_traces_and_its_V2_005_calibration")
    story = cases(t, "StoryStateV2", "test_version_2_admits_a_proof_and_an_adequacy_record_in_an_active_attempt_only")
    runtime = cases(t, "Runtime", "test_the_run_scope_writes_format_3_and_its_journal_is_read_and_repaired_as_format_3",
                    "test_a_rerun_of_the_run_scope_reads_the_previous_format_3_journal_at_preflight")
    lineage = cases(t, "Lineage", "test_V2_005_is_the_fourth_link_after_V2_003_changing_exactly_F1",
                    "test_the_sealed_P5_records_are_verified_by_identity_never_rewritten")
    p5 = _module("aisef_v2_p5_evidence", "validation/v2/p5_evidence.py")
    fm = _module("aisef_v2_freeze_manifest", "validation/v2/freeze_manifest.py")
    links = fm.lineage(ROOT)[1]
    exc = json.loads((ROOT / "closure-evidence/v2/ARCHITECTURE-EXCEPTION-V2-005.json").read_text(encoding="utf-8"))
    conf = json.loads((ROOT / "closure-evidence/v2/F-CONFORMANCE.json").read_text(encoding="utf-8"))
    sub = {s["id"]: s["state"] for s in conf["subchecks"]}
    nine = {c: {"owner": TAXONOMY[FailureCode(c)].owner.value, "retryable": TAXONOMY[FailureCode(c)].budget is not None,
                "budget": TAXONOMY[FailureCode(c)].budget.value if TAXONOMY[FailureCode(c)].budget else None}
            for c in sorted(V2_005_CODES, key=[c.value for c in FailureCode].index)}
    mutation = _mutation_by_target()
    return {
        "record": "AISEF V2 — P6 V2-005 SCHEMA (journal format 3, the nine codes, budget_owner)",
        "work_package": "WP-6.2",
        "rfc": "§15.3, §16, §17.1, §20.1, §22, §22.1, §25, §26, §35 as amended by ARCHITECTURE-EXCEPTION-V2-005 (F1)",
        "implementation": "aisef2/journal/format3.py; aisef2/control/owner.py (+9 codes, FORMAT_2_CODES, V2_005_CODES); "
                          "aisef2/journal/event.py (formats 1 and 2 carry their historical code set); "
                          "aisef2/journal/projections/budgets.py v2, story_state.py v2; tests/v2/refmodel (independent); "
                          "aisef2/runtime (run_scope writes format 3; sentinel and repair read every format as written)",
        "format_3": {"version": f3.FORMAT, "known_formats": list(f3.KNOWN_FORMATS), "schemas": len(f3.SCHEMAS),
                     "writable": len(f3.WRITABLE), "event_types": len(T),
                     "new_schemas": sorted(set(f3.SCHEMAS) - set(f2.SCHEMAS) - set(ev.SCHEMAS)),
                     "re_declared": sorted(k for k in f3.SCHEMAS if k in (set(f2.SCHEMAS) | set(ev.SCHEMAS))
                                           and f3.SCHEMAS[k] is not f2.SCHEMAS.get(k, ev.SCHEMAS.get(k))),
                     "provider_request_requires_budget_owner": "budget_owner" in f3.SCHEMAS["provider/request"].required,
                     "budget_owners": [o.value for o in f3.BUDGET_OWNERS],
                     "format_1_writable": len(ev.SCHEMAS), "format_2_writable": len(f2.WRITABLE)},
        "failure_taxonomy": {"codes": len(FailureCode), "historical_formats_1_and_2": sorted(FORMAT_2_CODES),
                             "v2_005_format_3_only": nine},
        "projections": {k.value: p.version for k, p in PROJECTIONS.items()},
        "lineage": {"links": [pathlib.Path(x["record"]).name for x in links],
                    "frozen_items_changed_by_v2_005": links[-1]["frozen_items_changed"],
                    "exception_status": exc["status"], "v2_004": exc["supersedes"]["status"],
                    "schema_fit_audit_sha256": exc["promoted_from"]["sha256"],
                    "f_conformance": {k: sub.get(k) for k in ("F1.failure_taxonomy", "F1.journal_format_3")},
                    "p5_records_sealed": sorted(pathlib.Path(k).name for k in p5.sealed(ROOT))},
        "mutation_by_target": mutation,
        "properties": {
            "FMT3_1_every_event_type_has_a_schema": catalog["test_FMT3_1_every_event_type_has_a_format_3_schema"]
                and len(f3.SCHEMAS) == len(T) == 29,
            "FMT3_2_missing_schema_fails_catalog_check": catalog["test_FMT3_2_a_missing_schema_fails_the_catalog_check_and_the_reader"],
            "FMT3_3_format_1_and_2_journals_read_identically": compat[
                "test_FMT3_3_every_format_1_and_format_2_journal_reads_identically_through_the_format_3_reader"],
            "FMT3_4_missing_required_field_refused_before_log_growth": schemas[
                "test_FMT3_4_a_missing_required_field_refuses_the_append_before_the_log_grows"],
            "FMT3_5_no_format_read_under_another_formats_semantics": compat[
                "test_FMT3_5_a_reader_reads_a_journal_under_its_declared_format_and_guesses_nothing"],
            "FMT3_6_format_3_provider_request_requires_budget_owner": schemas[
                "test_FMT3_6_a_format_3_provider_request_names_one_of_the_three_budget_owners"]
                and "budget_owner" in f3.SCHEMAS["provider/request"].required
                and "budget_owner" not in ev.SCHEMAS["provider/request"].required,
            "FMT3_7_format_2_evidence_never_rewritten_or_upgraded": compat[
                "test_FMT3_7_no_format_1_or_format_2_journal_is_rewritten_extended_or_upgraded"],
            "FMT3_8_invariant_violated_context_affects_no_projection": schemas[
                "test_FMT3_8_the_context_of_an_invariant_violation_cannot_affect_any_projection"],
            "proof_verified_lossless_from_two_cited_sealed_records": schemas[
                "test_a_proof_is_two_cited_sealed_records_with_one_instrument_and_the_agreement_they_state"],
            "tests_adequacy_is_the_typed_two_axis_assembly": schemas["test_an_adequacy_record_is_the_typed_assembly_under_the_two_axis_rules"],
            "plan_static_admitted_once_per_plan": schemas["test_a_static_admission_is_the_typed_result_once_per_plan"],
            "exactly_nine_new_codes_no_tenth": taxonomy["test_FailureCode_is_exactly_the_thirteen_historical_codes_and_the_nine_of_V2_005"]
                and len(V2_005_CODES) == 9 and len(FailureCode) == 22,
            "one_owner_one_retryability_one_budget_per_code": taxonomy["test_each_of_the_nine_has_one_owner_one_retryability_and_its_own_budget"],
            "no_call_site_override_no_prose_code": taxonomy["test_no_call_site_supplies_owner_or_retryability_and_no_prose_becomes_a_code"],
            "old_formats_refuse_the_nine": taxonomy["test_formats_1_and_2_carry_only_the_thirteen_and_format_3_carries_all"],
            "F1_failure_taxonomy_subcheck_pins_the_table": taxonomy[
                "test_the_conformance_subcheck_pins_the_table_and_rejects_a_swapped_owner_or_retryability"]
                and sub.get("F1.failure_taxonomy") == "PASS" and sub.get("F1.journal_format_3") == "PASS",
            "budgets_v2_charges_budget_owner_never_defaults": all(budgets.values()) and PROJECTIONS[
                list(PROJECTIONS)[2]].version == 2,
            "review_and_security_never_charge_the_developer": budgets[
                "test_a_retry_charges_the_failures_own_owner_and_never_the_developer_for_review_or_security"],
            "reference_models_agree_on_format_3_traces": budgets["test_the_reference_model_agrees_on_format_3_traces_and_its_V2_005_calibration"],
            "story_state_v2_active_only": all(story.values()),
            "runtime_writes_format_3_reads_and_repairs_every_format": all(runtime.values()),
            "lineage_V2_003_to_V2_005_F1_only": lineage["test_V2_005_is_the_fourth_link_after_V2_003_changing_exactly_F1"]
                and [pathlib.Path(x["record"]).name for x in links][-2:] == ["AISEF-V2-RFC-AMENDMENT-V2-003.json",
                                                                              "AISEF-V2-RFC-AMENDMENT-V2-005.json"]
                and links[-1]["frozen_items_changed"] == ["F1"],
            "V2_004_superseded_never_applied": exc["supersedes"]["status"] == "SUPERSEDED — NEVER APPLIED"
                and not (ROOT / "closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-004.json").exists(),
            "P5_sealed_records_identity_verified_not_rewritten": lineage["test_the_sealed_P5_records_are_verified_by_identity_never_rewritten"]
                and p5.check(ROOT) == [],
            "mutation_every_v2_005_target_measured_current_no_unaudited_survivor": bool(mutation) and all(
                m["current"] and not m["error"] and isinstance(m["mutants"], int) and m["mutants"] > 0
                and m["unaudited"] == [] for m in mutation.values()),
        },
    }


# --------------------------------------------------------------------------------------- WP-6.2 / orchestration

#: The owner's required cases (WP-6.2 authorization §19) and the ten typed states of V2-005 §18, each measured by the
#: real-path test that implements it (tests/v2/test_p6_orchestration.py).
ORCH_CASES = {
    "ORCH-1": "test_ORCH_1_an_end_to_end_story_completes_through_the_real_path",
    "ORCH-2": "test_ORCH_2_a_developer_outage_mid_story_is_a_typed_PROVIDER_failure_with_no_cross_charge",
    "ORCH-2b": "test_ORCH_2b_a_reviewer_outage_stays_PROVIDER",
    "ORCH-3": "test_ORCH_3_an_admission_refusal_makes_no_provider_request",
    "ORCH-4": "test_ORCH_4_pre_satisfied_obligations_skip_the_developer_and_the_candidate_is_still_verified",
    "ORCH-5": "test_ORCH_5_and_SCHEMA_1_a_verifier_disagreement_is_VERIFIER_DISAGREEMENT_INTEGRATION_and_stops",
    "ORCH-6": "test_ORCH_6_and_SCHEMA_9_a_reviewer_environment_failure_is_CAPABILITY_UNRUNNABLE_ENVIRONMENT_never_DEVELOPER",
    "ORCH-7": "test_ORCH_7_and_SCHEMA_8_a_scanner_that_ran_and_found_is_EXECUTED_and_SECURITY_FINDING",
    "ORCH-8": "test_ORCH_8_and_SCHEMA_3_a_merge_conflict_is_MERGE_CONFLICT_INTEGRATION_with_zero_developer_charge",
    "ORCH-9": "test_ORCH_9_and_10_a_post_merge_regression_of_a_prior_PRESERVE_obligation_is_INTEGRATION_and_rolled_back",
    "ORCH-10": "test_ORCH_9_and_10_a_post_merge_regression_of_a_prior_PRESERVE_obligation_is_INTEGRATION_and_rolled_back",
    "ORCH-11": "test_ORCH_11_scenario_L_INTRODUCE_PRESERVE_and_VERIFY_give_the_identical_product_verdict",
    "ORCH-12": "test_ORCH_12_a_reviewer_confinement_parameter_is_impossible_by_API_shape",
    "ORCH-13": "test_ORCH_13_the_seam_refuses_a_HUMAN_DECLARATION_REQUIRED_row_before_any_provider_execution",
    "ORCH-14": "test_ORCH_14_a_change_of_engineering_adequacy_leaves_the_product_proof_unchanged",
    "ORCH-15": "test_ORCH_15_only_an_explicit_immutable_reference_selects_evidence",
    "ORCH-16": "test_ORCH_16_retry_state_derives_solely_from_the_journal_projection",
}
ORCH_SCHEMA_CASES = {
    "ORCH-SCHEMA-1": "test_ORCH_5_and_SCHEMA_1_a_verifier_disagreement_is_VERIFIER_DISAGREEMENT_INTEGRATION_and_stops",
    "ORCH-SCHEMA-2": "test_ORCH_SCHEMA_2_a_probe_mismatch_is_PROBE_MISMATCH_and_never_a_proof",
    "ORCH-SCHEMA-3": "test_ORCH_8_and_SCHEMA_3_a_merge_conflict_is_MERGE_CONFLICT_INTEGRATION_with_zero_developer_charge",
    "ORCH-SCHEMA-4": "test_ORCH_SCHEMA_4_tests_that_cannot_run_are_TESTS_UNRUNNABLE_with_no_developer_charge",
    "ORCH-SCHEMA-5": "test_ORCH_SCHEMA_5_INADEQUATE_under_a_blocking_policy_is_TESTS_INADEQUATE_owned_by_DEVELOPER",
    "ORCH-SCHEMA-6": "test_ORCH_SCHEMA_6_an_integration_owned_INCOMPLETE_collection_is_recorded_only",
    "ORCH-SCHEMA-7": "test_ORCH_SCHEMA_7_a_review_request_charges_the_REVIEW_budget_and_blocks_only_with_corroboration",
    "ORCH-SCHEMA-7b": "test_ORCH_SCHEMA_7b_a_corroborated_review_finding_is_REVIEW_FINDING_owned_by_REVIEW",
    "ORCH-SCHEMA-8": "test_ORCH_7_and_SCHEMA_8_a_scanner_that_ran_and_found_is_EXECUTED_and_SECURITY_FINDING",
    "ORCH-SCHEMA-9": "test_ORCH_6_and_SCHEMA_9_a_reviewer_environment_failure_is_CAPABILITY_UNRUNNABLE_ENVIRONMENT_never_DEVELOPER",
    "ORCH-SCHEMA-10": "test_ORCH_SCHEMA_10_a_resource_that_cannot_be_acquired_is_RESOURCE_ACQUISITION_FAILED",
}
STRUCTURAL_CASES = {
    "single_path": "test_SINGLE_PATH_one_entry_and_no_V1_authority",
    "verifier_independence": "test_VERIFIER_INDEPENDENCE_its_own_checkout_and_the_identical_instrument",
    "journal_authority": "test_JOURNAL_AUTHORITY_the_decision_cites_every_check_row_of_the_story_gate",
    "root_tier_and_static_rules": "test_ROOT_tier_arms_I_to_IX_and_the_static_rules_hold_over_the_package",
}
CONFINEMENT_WORDS = ("readonly", "read_only", "sandbox", "allow_write", "confinement", "writable")


def _orchestrate_static() -> dict:
    """What the package's source says, by AST: imports of the frozen kernel, the codes it can emit, the seam's place,
    the confinement API's shape, and each module's digest."""
    import ast
    import inspect
    from aisef2.control.owner import FailureCode, V2_005_CODES
    from aisef2.orchestrate import adapters, seam, story_runner
    mt = _module("aisef_v2_mutation", "validation/v2/mutation.py")
    modules, v1_imports, codes = {}, [], set()
    for rel in ORCHESTRATION_TARGET_MODULES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        tree = ast.parse(text)
        modules[rel] = mt.source_digest(text)
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                v1_imports += [f"{rel}: {a.name}" for a in n.names if a.name == "aisef" or a.name.startswith("aisef.")]
            elif isinstance(n, ast.ImportFrom) and n.module and (n.module == "aisef" or n.module.startswith("aisef.")):
                v1_imports.append(f"{rel}: {n.module}")
            elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "FailureCode":
                codes.add(n.attr)
    run_story_src = inspect.getsource(story_runner.run_story)
    parameters = sorted({f"{m.__name__.rsplit('.', 1)[-1]}.{name}.{p}" for m in (story_runner, adapters)
                         for name, f in inspect.getmembers(m, inspect.isfunction) for p in inspect.signature(f).parameters
                         if any(w in p for w in CONFINEMENT_WORDS)})
    return {
        "modules": modules,
        "v1_imports": v1_imports,
        "failure_codes_emitted": sorted(codes, key=[c.value for c in FailureCode].index),
        "v2_005_codes_emitted": sorted(c for c in V2_005_CODES if c in codes),
        "seam": {"module": "aisef2/orchestrate/seam.py", "entry": "admit_legacy",
                 "before_the_story_begins": run_story_src.index("admit_legacy") < run_story_src.index("_freeze_plan")
                 and "admit_legacy" in run_story_src.split("\n")[2],
                 "refuses": seam.HUMAN_DECLARATION_REQUIRED},
        "confinement": {"derived_by": "aisef2/orchestrate/adapters.py::confine(story_id, checkout)",
                        "parameters": list(inspect.signature(adapters.confine).parameters),
                        "confinement_like_parameters_in_api": parameters},
        "run_story_signature": list(inspect.signature(story_runner.run_story).parameters),
    }


def _orchestrate_trace() -> dict:
    """The normal path, run once for real (ORCH-1's fixture): the journal's event types in order, the story gate's
    rows, the resources acquired and released — outcomes only, no sha, no path."""
    e2e = _module("aisef_v2_test_p6_orchestration", "tests/v2/test_p6_orchestration.py")
    from aisef2.arch.enums import ControlProjection as P
    case = e2e.Orchestration("test_ORCH_1_an_end_to_end_story_completes_through_the_real_path")
    case.setUp()
    try:
        r = case.story(case.s1_plan(), "S1", case.s1_dev())
        events = list(case.run.events)
        checks = [(e.data["check"], e.data["passed"]) for e in events if e.type == "gate/check"]
        decision = [e for e in events if e.type == "gate/decision"][-1]
        budgets = case.run.state(P.BUDGETS)
        return {"committed": r.committed, "attempts": [a.outcome for a in r.attempts],
                "event_types": [e.type for e in events],
                "story_gate_rows": checks,
                "decision_cites_every_row": list(decision.source_seqs) == [e.seq for e in events if e.type == "gate/check"],
                "resources_acquired": [e.data["resource"] for e in events if e.type == "story/resource-acquired"],
                "resources_released": [(e.data["resource"], e.data["status"]) for e in events
                                       if e.type == "story/resource-released"],
                "provider_requests": [e.data["budget_owner"] for e in events if e.type == "provider/request"],
                "proofs": [(e.data["criterion_id"], e.data["agreement"], e.data.get("verdict")) for e in events
                           if e.type == "proof/verified"],
                "adequacy": [(e.data["outcome"], e.data["owner"]) for e in events if e.type == "tests/adequacy"],
                "budgets": json.loads(json.dumps({k: budgets[k] for k in ("format", "developer", "review", "security", "retries")},
                                                 default=dict)),
                "story_state": dict(case.run.state(P.STORY_STATE)["S1"])}
    finally:
        case.doCleanups()


def orchestration() -> dict:
    from aisef2.arch.enums import InvariantId
    from aisef2.invariants.registry import Tier, armed
    e2e = _module("aisef_v2_test_p6_orchestration", "tests/v2/test_p6_orchestration.py")
    stages = _module("aisef_v2_test_p6_stages", "tests/v2/test_p6_stages.py")
    orch = {k: passed(e2e.Orchestration(n)) for k, n in ORCH_CASES.items()}
    schema = {k: passed(e2e.Orchestration(n)) for k, n in ORCH_SCHEMA_CASES.items()}
    structural = {k: passed(e2e.Orchestration(n)) for k, n in STRUCTURAL_CASES.items()}
    stage_results = {}
    for name, cls in sorted(vars(stages).items()):
        if isinstance(cls, type) and issubclass(cls, unittest.TestCase) and cls.__module__ == stages.__name__ \
                and name not in ("Journal",):
            for t in unittest.TestLoader().getTestCaseNames(cls):
                stage_results[f"{name}.{t}"] = passed(cls(t))
    ks = _module("aisef_v2_kernel_static_checks", "validation/v2/kernel_static_checks.py")
    eb = _module("aisef_v2_except_boundaries", "validation/v2/except_boundaries.py")
    da = _module("aisef_v2_destructive_authority", "validation/v2/destructive_authority.py")
    p5 = _module("aisef_v2_p5_evidence", "validation/v2/p5_evidence.py")
    static = _orchestrate_static()
    audit = eb.audit(ROOT)
    mine = [b for b in audit["boundaries"] if b["path"].startswith("aisef2/orchestrate/")]
    destructive = da.check(ROOT)
    sites, _ = da.discover(ROOT)
    trace = _orchestrate_trace()
    mutation = _mutation_by_target(ORCHESTRATION_TARGET_MODULES, ("aisef2/journal/format3.py::verified_payload",))
    return {
        "record": "AISEF V2 — P6 ORCHESTRATION (the single authoritative story path)",
        "work_package": "WP-6.2",
        "rfc": "§5, §13–§17, §20.1, §22, §25, §26, §31 (as amended by ARCHITECTURE-EXCEPTION-V2-005)",
        "implementation": static["modules"],
        "path": {"entry": "aisef2/orchestrate/story_runner.py::run_story", "signature": static["run_story_signature"],
                 "stages": [c for c, _ in trace["story_gate_rows"]], "trace": trace},
        "static": {k: v for k, v in static.items() if k != "modules"},
        "invariants": {"root_tier_armed": sorted(i.value for i in armed().get(Tier.ROOT, ())),
                       "kernel_static_rules": ks.check(ROOT),
                       "except_boundaries_in_orchestrate": {"count": len(mine),
                                                            "dispositions": sorted({b["disposition"] for b in mine}),
                                                            "problems": audit["problems"]},
                       "destructive_sites_in_orchestrate": [f"{s.path}:{s.node.lineno}" for s in sites
                                                            if s.path.startswith("aisef2/orchestrate/")],
                       "destructive_authority_problems": destructive,
                       "p5_sealed_records": sorted(pathlib.Path(k).name for k in p5.sealed(ROOT))},
        "cases": {"orchestration": orch, "schema": schema, "structural": structural},
        "stage_tests": {"count": len(stage_results), "passed": sum(stage_results.values()),
                        "failed": sorted(k for k, v in stage_results.items() if not v)},
        "mutation_by_target": mutation,
        "properties": {
            "ORCH_1_to_16_pass_through_the_real_path": all(orch.values()) and len(orch) == 17,
            "ORCH_SCHEMA_1_to_10_pass": all(schema.values()) and len(schema) == 11,
            "single_path_no_V1_authority": structural["single_path"] and static["v1_imports"] == []
                and static["run_story_signature"] == ["run", "plan", "story_id", "inputs", "adapters", "policy"],
            "normal_path_commits_and_disposes": trace["committed"] and trace["attempts"] == ["COMMIT"]
                and trace["story_state"]["state"] == "ENDED"
                and all(s == "RELEASED" for _, s in trace["resources_released"])
                and len(trace["resources_acquired"]) == len(trace["resources_released"]),
            "no_provider_request_before_admission": trace["event_types"].index("story/admitted")
                < trace["event_types"].index("provider/request"),
            "decision_cites_every_gate_row": trace["decision_cites_every_row"] and structural["journal_authority"],
            "post_merge_reproof_before_commit": trace["event_types"].index("story/commit")
                > max(i for i, t in enumerate(trace["event_types"]) if t == "proof/verified"),
            "verifier_independent_identical_instrument": structural["verifier_independence"],
            "confinement_derived_never_a_parameter": static["confinement"]["confinement_like_parameters_in_api"] == []
                and static["confinement"]["parameters"] == ["story_id", "checkout"] and orch["ORCH-12"],
            "seam_explicit_before_the_story_and_refuses_undeclared_rows": static["seam"]["before_the_story_begins"]
                and orch["ORCH-13"],
            "all_nine_V2_005_codes_reachable_from_the_path": len(static["v2_005_codes_emitted"]) == 9,
            "no_code_outside_the_taxonomy": all(c in {x.value for x in __import__("aisef2.control.owner", fromlist=["FailureCode"]).FailureCode}
                                                for c in static["failure_codes_emitted"]),
            "root_tier_arms_I_to_IX": set(armed().get(Tier.ROOT, ())) == set(InvariantId) and structural["root_tier_and_static_rules"],
            "kernel_static_rules_hold": ks.check(ROOT) == [],
            "except_boundaries_audited": audit["problems"] == [] and len(mine) > 0,
            "no_destructive_site_in_orchestrate": destructive == []
                and not any(s.path.startswith("aisef2/orchestrate/") for s in sites),
            "P5_sealed_records_untouched": p5.check(ROOT) == [],
            "every_stage_test_passes": stage_results and all(stage_results.values()),
            "mutation_every_orchestration_target_measured_current_no_unaudited_survivor": bool(mutation) and all(
                m["current"] and not m["error"] and isinstance(m["mutants"], int) and m["mutants"] > 0
                and m["unaudited"] == [] for m in mutation.values())
                and set(mutation) >= {t for t in _module("aisef_v2_mutation", "validation/v2/mutation.py").P6_TARGETS
                                      if t.split("::")[0] in ORCHESTRATION_TARGET_MODULES},
        },
    }


BUILDERS: dict[str, tuple[str, Callable[[], dict], str]] = {
    "WP-6.2/V2-005": ("closure-evidence/v2/P6-V2-005-SCHEMA.json", v2_005_schema, "aisef2/journal/format3.py"),
    "WP-6.2/ORCH": ("closure-evidence/v2/P6-ORCHESTRATION.json", orchestration, "aisef2/orchestrate/story_runner.py"),
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
        for p in problems:
            print(f"FAIL  {p}")
        print("p6 evidence: " + ("FAIL" if problems else "PASS"))
        return 1 if problems else 0
    for rel, build, needs in BUILDERS.values():
        if (ROOT / needs).exists():
            record = build()
            for p in problems_of(record):
                print(f"FAIL  {p}")
            (ROOT / rel).write_text(render(record), encoding="utf-8")
            print(f"wrote {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
