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


def _mutation_by_target() -> dict:
    mt = _module("aisef_v2_mutation", "validation/v2/mutation.py")
    out = {}
    for phase, rel in mt.RECORDS.items():
        p = ROOT / rel
        if not p.exists():
            continue
        for t in json.loads(p.read_text(encoding="utf-8"))["targets"]:
            if t["target"].split("::")[0] in V2_005_TARGET_MODULES:
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


BUILDERS: dict[str, tuple[str, Callable[[], dict], str]] = {
    "WP-6.2/V2-005": ("closure-evidence/v2/P6-V2-005-SCHEMA.json", v2_005_schema, "aisef2/journal/format3.py"),
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
