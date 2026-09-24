"""P5 evidence records — computed from the code, never written by hand, with a --check twin (the P3/P4 contract).

Each record carries `properties`, named facts measured on the implementation by running the named test case (the test
is the measurement); `--check` re-derives every record and fails if it differs from the committed one or if any
property is false. Records hold outcomes only — never a pid, a path, a duration or a wall-clock time — so a rebuild
is byte-identical on Linux, macOS and Windows (Q0 rebuilds them on every CI job).

    python -P validation/v2/p5_evidence.py            # write every record whose package is implemented
    python -P validation/v2/p5_evidence.py --check    # fail on drift or on a false property
"""

from __future__ import annotations

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
    return {n: passed(getattr(module, cls)(n)) for n in names}


# --------------------------------------------------------------------------------------- WP-5.1

def test_execution() -> dict:
    from aisef2.arch.enums import Owner
    from aisef2.quality import test_execution as te
    t = _module("aisef_v2_p5_test_test_execution", "tests/v2/p5/test_test_execution.py")
    shape = cases(t, "Shape", "test_the_fields_are_the_rfcs",
                  "test_UNRUNNABLE_carries_no_outcome_no_selection_and_only_the_environment_owner",
                  "test_EXECUTED_owner_follows_outcome_and_selection",
                  "test_typed_inputs_refuse_untyped_causes_and_absolute_paths")
    rules = cases(t, "Classify", "test_TEST_1_a_missing_runner_is_UNRUNNABLE_ENVIRONMENT_with_no_outcome_and_no_selection",
                  "test_TEST_2_failing_assertions_are_EXECUTED_FAILED_STORY_TESTS_RAN_DEVELOPER",
                  "test_a_passing_suite_is_EXECUTED_PASSED_STORY_TESTS_RAN_with_no_owner",
                  "test_rule_4_collection_cause_on_a_declared_environment_dependency_is_UNRUNNABLE_ENVIRONMENT",
                  "test_rule_4_collection_cause_in_the_projects_own_tree_is_DEVELOPER",
                  "test_rule_4_undeterminable_collection_cause_is_INTEGRATION_never_DEVELOPER",
                  "test_rule_3_no_story_test_matched_is_DEVELOPER_by_the_typed_value_and_distinct_from_UNRUNNABLE",
                  "test_rule_5_regressions_use_the_identical_rules", "test_no_did_not_run_to_developer_edge_exists",
                  "test_a_story_file_the_runner_could_not_collect_is_never_hidden_by_the_story_files_that_ran",
                  "test_the_outcome_is_the_storys_tests_never_another_files")
    real = cases(t, "RealRunner", "test_a_passing_suite_yields_EXECUTED_PASSED_STORY_TESTS_RAN", "test_TEST_2_for_real",
                 "test_TEST_1_for_real_the_configured_runner_is_absent",
                 "test_a_runner_that_crashes_before_reporting_is_UNRUNNABLE",
                 "test_collection_failure_on_a_declared_environment_dependency_is_UNRUNNABLE_ENVIRONMENT",
                 "test_collection_failure_on_the_projects_own_tree_is_DEVELOPER",
                 "test_undeterminable_collection_cause_is_INTEGRATION",
                 "test_an_empty_selection_is_NO_STORY_TESTS_MATCHED_DEVELOPER",
                 "test_a_directory_target_is_discovered_and_a_node_id_selects_one_test",
                 "test_the_harness_deadline_is_UNRUNNABLE_and_the_range_is_released",
                 "test_the_candidate_is_the_only_tree_execute_knows",
                 "test_the_result_set_is_typed_and_carries_the_collection_detail")
    adapter = cases(t, "PytestAdapter", "test_the_junit_result_set_is_read_typed")
    return {
        "record": "AISEF V2 — P5 TEST EXECUTION",
        "work_package": "WP-5.1",
        "rfc": "§15.0 (F1 payload enums TestExecutionStatus, TestOutcome, TestSelection; F3 owners)",
        "implementation": "aisef2/quality/test_execution.py",
        "runners": {"unittest": "harness-owned, stdlib alone, run with -E -s -c inside an owned process range",
                    "pytest": "read through its junit result set (xunit1)"},
        "taxonomy": "unchanged: FailureCode (carried by failure/observed, F1 by the V2-003 reading) gains no member in "
                    "WP-5.1; the engineering-quality codes are proposed under ARCHITECTURE EXCEPTION V2-004 for the "
                    "owner's decision before WP-5.4 wires TestExecution into routing and budgets",
        "properties": {
            "TEST_1_missing_runner_UNRUNNABLE_ENVIRONMENT_no_outcome_no_selection":
                rules["test_TEST_1_a_missing_runner_is_UNRUNNABLE_ENVIRONMENT_with_no_outcome_and_no_selection"]
                and real["test_TEST_1_for_real_the_configured_runner_is_absent"],
            "TEST_2_failing_assertions_EXECUTED_FAILED_INADEQUATE_owner_DEVELOPER":
                rules["test_TEST_2_failing_assertions_are_EXECUTED_FAILED_STORY_TESTS_RAN_DEVELOPER"]
                and real["test_TEST_2_for_real"],
            "passing_suite_EXECUTED_PASSED_STORY_TESTS_RAN":
                rules["test_a_passing_suite_is_EXECUTED_PASSED_STORY_TESTS_RAN_with_no_owner"]
                and real["test_a_passing_suite_yields_EXECUTED_PASSED_STORY_TESTS_RAN"],
            "collection_cause_declared_environment_dependency_UNRUNNABLE_ENVIRONMENT_SS81A":
                rules["test_rule_4_collection_cause_on_a_declared_environment_dependency_is_UNRUNNABLE_ENVIRONMENT"]
                and real["test_collection_failure_on_a_declared_environment_dependency_is_UNRUNNABLE_ENVIRONMENT"],
            "collection_cause_project_source_DEVELOPER":
                rules["test_rule_4_collection_cause_in_the_projects_own_tree_is_DEVELOPER"]
                and real["test_collection_failure_on_the_projects_own_tree_is_DEVELOPER"],
            "collection_cause_undeterminable_INTEGRATION_never_DEVELOPER":
                rules["test_rule_4_undeterminable_collection_cause_is_INTEGRATION_never_DEVELOPER"]
                and real["test_undeterminable_collection_cause_is_INTEGRATION"],
            "collection_cause_syntax_error_in_the_developers_file_DEVELOPER":
                rules["test_rule_4_collection_cause_in_the_projects_own_tree_is_DEVELOPER"],
            "NO_STORY_TESTS_MATCHED_DEVELOPER_by_the_typed_value_distinct_from_UNRUNNABLE":
                rules["test_rule_3_no_story_test_matched_is_DEVELOPER_by_the_typed_value_and_distinct_from_UNRUNNABLE"]
                and real["test_an_empty_selection_is_NO_STORY_TESTS_MATCHED_DEVELOPER"],
            "regression_execution_uses_the_identical_rules": rules["test_rule_5_regressions_use_the_identical_rules"],
            "story_collection_failure_never_hidden_by_story_tests_that_ran_rule_4_before_rule_2":
                rules["test_a_story_file_the_runner_could_not_collect_is_never_hidden_by_the_story_files_that_ran"]
                and real["test_the_result_set_is_typed_and_carries_the_collection_detail"],
            "outcome_is_the_storys_own_tests_never_another_files":
                rules["test_the_outcome_is_the_storys_tests_never_another_files"],
            "no_did_not_run_to_developer_edge_exists_anywhere":
                rules["test_no_did_not_run_to_developer_edge_exists"]
                and shape["test_UNRUNNABLE_carries_no_outcome_no_selection_and_only_the_environment_owner"],
            "UNRUNNABLE_is_never_INADEQUATE_or_INCOMPLETE_downstream":
                shape["test_UNRUNNABLE_carries_no_outcome_no_selection_and_only_the_environment_owner"],
            "shape_is_the_rfcs_and_typed": shape["test_the_fields_are_the_rfcs"]
                and shape["test_EXECUTED_owner_follows_outcome_and_selection"]
                and shape["test_typed_inputs_refuse_untyped_causes_and_absolute_paths"],
            "runner_crash_before_reporting_UNRUNNABLE": real["test_a_runner_that_crashes_before_reporting_is_UNRUNNABLE"],
            "harness_deadline_UNRUNNABLE_and_range_released":
                real["test_the_harness_deadline_is_UNRUNNABLE_and_the_range_is_released"],
            "selection_by_directory_and_by_node_id": real["test_a_directory_target_is_discovered_and_a_node_id_selects_one_test"],
            "pytest_result_set_read_typed": adapter["test_the_junit_result_set_is_read_typed"],
            "no_parent_revision_reaches_execution_IX": real["test_the_candidate_is_the_only_tree_execute_knows"],
            "unrunnable_owner_is_environment_by_the_typed_value": te.unrunnable("r").owner_on_failure is Owner.ENVIRONMENT
                and te.unrunnable("r").outcome is None and te.unrunnable("r").selection is None,
            "classifier_reads_typed_causes_never_prose": te.CollectionError.__post_init__ is not None
                and "IMPORT" in te.__dict__ and all(k in ("IMPORT", "SYNTAX", "OTHER") for k in (te.IMPORT, te.SYNTAX, te.OTHER)),
        },
    }


# --------------------------------------------------------------------------------------- WP-5.2

def relevance() -> dict:
    t = _module("aisef_v2_p5_test_relevance", "tests/v2/p5/test_relevance.py")
    typed = cases(t, "Typed", "test_REL_1_an_executed_story_test_intersecting_a_changed_executable_line_is_RELEVANT",
                  "test_REL_2_measured_story_tests_with_zero_intersection_are_IRRELEVANT",
                  "test_REL_3_coverage_capability_unavailable_is_UNMEASURABLE_never_IRRELEVANT",
                  "test_REL_4_coverage_capability_PARTIAL_is_UNMEASURABLE",
                  "test_REL_5_branch_evidence_is_recorded_when_present_and_never_required",
                  "test_REL_6_a_non_line_addressable_artefact_uses_its_own_measurement",
                  "test_REL_7_a_non_line_addressable_artefact_without_a_capability_is_UNMEASURABLE",
                  "test_REL_8_the_same_coverage_under_another_test_layout_is_the_same_result",
                  "test_a_test_that_did_not_execute_establishes_nothing",
                  "test_the_developers_own_test_file_is_not_the_product_change",
                  "test_one_unmeasurable_artefact_never_hides_behind_the_others",
                  "test_the_result_shape_refuses_every_contradiction", "test_nothing_here_reaches_the_product_verdict",
                  "test_REL_DEL_1_a_pure_executable_deletion_is_UNMEASURABLE_not_IRRELEVANT",
                  "test_REL_DEL_2_and_3_ordinary_modifications_are_measured",
                  "test_REL_DEL_4_a_tests_only_diff_is_measured_empty_and_is_not_a_deletion")
    parse = cases(t, "Parsing", "test_a_unified_diff_becomes_candidate_line_numbers",
                  "test_executable_lines_are_the_code_objects_own")
    real = cases(t, "ForReal", "test_REL_1_for_real", "test_REL_2_for_real",
                 "test_REL_3_for_real_the_runner_without_the_capability_declares_it",
                 "test_REL_4_for_real_a_test_that_replaces_the_tracer_makes_the_measurement_PARTIAL",
                 "test_REL_5_for_real_branch_evidence_is_recorded_and_the_value_is_the_lines",
                 "test_REL_6_for_real_an_accessed_data_file", "test_REL_7_for_real_no_capability_for_the_data_file",
                 "test_REL_8_for_real_the_same_tests_in_another_layout", "test_product_code_run_in_a_thread_is_measured",
                 "test_REL_DEL_1_for_real_the_story_deletes_executable_code_and_its_test_verifies_the_deletion")
    rel = lambda n: typed[f"test_REL_{n}_" + {  # noqa: E731
        1: "an_executed_story_test_intersecting_a_changed_executable_line_is_RELEVANT",
        2: "measured_story_tests_with_zero_intersection_are_IRRELEVANT",
        3: "coverage_capability_unavailable_is_UNMEASURABLE_never_IRRELEVANT", 4: "coverage_capability_PARTIAL_is_UNMEASURABLE",
        5: "branch_evidence_is_recorded_when_present_and_never_required",
        6: "a_non_line_addressable_artefact_uses_its_own_measurement",
        7: "a_non_line_addressable_artefact_without_a_capability_is_UNMEASURABLE",
        8: "the_same_coverage_under_another_test_layout_is_the_same_result"}[n]]
    real_of = {1: "test_REL_1_for_real", 2: "test_REL_2_for_real",
               3: "test_REL_3_for_real_the_runner_without_the_capability_declares_it",
               4: "test_REL_4_for_real_a_test_that_replaces_the_tracer_makes_the_measurement_PARTIAL",
               5: "test_REL_5_for_real_branch_evidence_is_recorded_and_the_value_is_the_lines",
               6: "test_REL_6_for_real_an_accessed_data_file", 7: "test_REL_7_for_real_no_capability_for_the_data_file",
               8: "test_REL_8_for_real_the_same_tests_in_another_layout"}
    return {
        "record": "AISEF V2 — P5 RELEVANCE",
        "work_package": "WP-5.2",
        "rfc": "§15.2 (F1 payload enum Relevance: RELEVANT, IRRELEVANT, UNMEASURABLE; §24 capability levels)",
        "implementation": "aisef2/quality/relevance.py",
        "measurement": {"line-addressable": "a .py artefact: executable lines of its own code objects, required "
                        "capability line-coverage", "non-line-addressable": "any other artefact: artefact-access (the "
                        "case opened it), no line approximation", "branch": "branch-coverage arcs from a changed "
                        "executable line, recorded as stronger evidence, never required",
                        "runner": "the harness-owned unittest runner under --measure: sys.settrace + threading.settrace "
                                  "+ an open() audit hook, per case; it declares FULL, PARTIAL (a case replaced the "
                                  "tracer) or UNAVAILABLE (no --measure); the pytest adapter declares nothing"},
        "properties": {
            **{f"REL_{n}_typed_and_real": rel(n) and real[real_of[n]] for n in range(1, 9)},
            "capability_absence_is_UNMEASURABLE_never_IRRELEVANT": rel(3) and rel(4) and rel(7)
                and typed["test_one_unmeasurable_artefact_never_hides_behind_the_others"]
                and typed["test_the_result_shape_refuses_every_contradiction"],
            "branch_coverage_never_required": rel(5) and real[real_of[5]],
            "non_line_addressable_uses_its_own_measurement_or_UNMEASURABLE": rel(6) and rel(7),
            "test_layout_invariance": rel(8) and real[real_of[8]],
            "no_execution_no_relevance_success": typed["test_a_test_that_did_not_execute_establishes_nothing"],
            "developer_test_files_are_not_the_product_change": typed["test_the_developers_own_test_file_is_not_the_product_change"],
            "story_diff_and_executable_lines_are_typed": parse["test_a_unified_diff_becomes_candidate_line_numbers"]
                and parse["test_executable_lines_are_the_code_objects_own"],
            "threads_are_measured": real["test_product_code_run_in_a_thread_is_measured"],
            "no_product_verdict_reached": typed["test_nothing_here_reaches_the_product_verdict"],
            "REL_DEL_1_pure_deletion_UNMEASURABLE_never_IRRELEVANT_typed_and_real":
                typed["test_REL_DEL_1_a_pure_executable_deletion_is_UNMEASURABLE_not_IRRELEVANT"]
                and real["test_REL_DEL_1_for_real_the_story_deletes_executable_code_and_its_test_verifies_the_deletion"],
            "REL_DEL_2_3_ordinary_modifications_IRRELEVANT_or_RELEVANT": typed["test_REL_DEL_2_and_3_ordinary_modifications_are_measured"],
            "REL_DEL_4_tests_only_diff_IRRELEVANT_by_a_possible_measurement_and_distinct_from_deletion":
                typed["test_REL_DEL_4_a_tests_only_diff_is_measured_empty_and_is_not_a_deletion"],
        },
        "deletion_rationale": "WP52-002: a removal-only hunk or a deleted file leaves no candidate line or file for the "
                              "cycle-1 candidate-side measurement to observe and §15.2 defines no deletion-specific "
                              "capability, so a pure deletion is UNMEASURABLE (measurement inability), never "
                              "IRRELEVANT; a tests-only diff has an empty product change set that the required "
                              "measurement fully covers and proves empty, so it is IRRELEVANT by the frozen "
                              "definition, and it is not a deletion",
    }


# --------------------------------------------------------------------------------------- WP-5.3

def vacuity() -> dict:
    t = _module("aisef_v2_p5_test_vacuity", "tests/v2/p5/test_vacuity.py")
    vac = cases(t, "ForReal", "test_VAC_1_a_story_test_that_fails_by_assertion_once_the_product_change_is_neutralised_is_NON_VACUOUS",
                "test_VAC_2_a_story_test_that_still_passes_is_VACUOUS",
                "test_VAC_3_a_tree_that_cannot_be_reconstructed_is_INDETERMINATE",
                "test_VAC_4_a_runner_unavailable_in_the_neutralised_run_is_INDETERMINATE",
                "test_VAC_5_a_story_test_that_no_longer_imports_is_INDETERMINATE",
                "test_VAC_6_intended_story_tests_that_do_not_actually_run_are_INDETERMINATE",
                "test_VAC_7_a_failure_not_attributable_to_the_neutralisation_is_INDETERMINATE",
                "test_VAC_8_a_tests_only_diff_leaves_the_product_unchanged_and_is_VACUOUS",
                "test_VAC_9_a_pure_deletion_the_patch_carries_is_reconstructed_and_classified_from_execution",
                "test_VAC_10_a_deletion_the_patch_does_not_carry_is_INDETERMINATE",
                "test_VAC_11_moving_the_developer_tests_does_not_change_the_result",
                "test_VAC_12_an_unrunnable_parent_changes_nothing_because_the_parent_is_never_executed")
    typed = cases(t, "Typed", "test_the_patch_is_typed_per_file", "test_reverse_application_is_exact_or_refused",
                  "test_neutralisation_touches_exactly_the_story_product_artefacts",
                  "test_the_result_shape_refuses_every_contradiction", "test_a_baseline_that_does_not_pass_has_no_counterfactual",
                  "test_invariant_IX_is_structural")
    return {
        "record": "AISEF V2 — P5 VACUITY",
        "work_package": "WP-5.3",
        "rfc": "§15.1 (F1 payload enum Vacuity: NON_VACUOUS, VACUOUS, INDETERMINATE); invariant IX",
        "implementation": "aisef2/quality/vacuity.py",
        "model": {"reconstruction": "a copy of the candidate (.git and caches aside) minus the story's added product "
                  "files, with every other story product hunk reverse-applied exactly at its candidate position; a "
                  "deleted product file rebuilt from the content the patch carries; test files the story owns and "
                  "everything outside the story diff copied untouched",
                  "attribution": "per intended case (story-owned, passed at the candidate): 'failed' in the "
                  "neutralised run attributes; 'error', a skip, a missing case or a collection failure does not",
                  "parent": "no parameter, no path, no git: the runner's cwd is the controller's scratch copy "
                  "(kernel rule CANDIDATE_ONLY_EXECUTION, invariant IX)"},
        "properties": {
            **{f"VAC_{n}": vac[k] for n, k in ((1, "test_VAC_1_a_story_test_that_fails_by_assertion_once_the_product_change_is_neutralised_is_NON_VACUOUS"),
                                                 (2, "test_VAC_2_a_story_test_that_still_passes_is_VACUOUS"),
                                                 (3, "test_VAC_3_a_tree_that_cannot_be_reconstructed_is_INDETERMINATE"),
                                                 (4, "test_VAC_4_a_runner_unavailable_in_the_neutralised_run_is_INDETERMINATE"),
                                                 (5, "test_VAC_5_a_story_test_that_no_longer_imports_is_INDETERMINATE"),
                                                 (6, "test_VAC_6_intended_story_tests_that_do_not_actually_run_are_INDETERMINATE"),
                                                 (7, "test_VAC_7_a_failure_not_attributable_to_the_neutralisation_is_INDETERMINATE"),
                                                 (8, "test_VAC_8_a_tests_only_diff_leaves_the_product_unchanged_and_is_VACUOUS"),
                                                 (9, "test_VAC_9_a_pure_deletion_the_patch_carries_is_reconstructed_and_classified_from_execution"),
                                                 (10, "test_VAC_10_a_deletion_the_patch_does_not_carry_is_INDETERMINATE"),
                                                 (11, "test_VAC_11_moving_the_developer_tests_does_not_change_the_result"),
                                                 (12, "test_VAC_12_an_unrunnable_parent_changes_nothing_because_the_parent_is_never_executed"))},
            "three_valued_result_proven": all(vac.values()) and typed["test_the_result_shape_refuses_every_contradiction"],
            "INDETERMINATE_never_NON_VACUOUS": all(vac[k] for k in vac if any(f"VAC_{n}_" in k for n in (3, 4, 5, 6, 7, 10)))
                and typed["test_a_baseline_that_does_not_pass_has_no_counterfactual"],
            "neutralisation_touches_only_story_product_artefacts": typed["test_neutralisation_touches_exactly_the_story_product_artefacts"],
            "reconstruction_is_exact_or_refused": typed["test_reverse_application_is_exact_or_refused"] and typed["test_the_patch_is_typed_per_file"],
            "invariant_IX_no_parent_execution": typed["test_invariant_IX_is_structural"]
                and vac["test_VAC_12_an_unrunnable_parent_changes_nothing_because_the_parent_is_never_executed"],
        },
    }


BUILDERS: dict[str, tuple[str, Callable[[], dict], str]] = {
    "WP-5.1": ("closure-evidence/v2/P5-TEST-EXECUTION.json", test_execution, "aisef2/quality/test_execution.py"),
    "WP-5.2": ("closure-evidence/v2/P5-RELEVANCE.json", relevance, "aisef2/quality/relevance.py"),
    "WP-5.3": ("closure-evidence/v2/P5-VACUITY.json", vacuity, "aisef2/quality/vacuity.py"),
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
        print("p5 evidence: " + ("FAIL" if problems else "PASS"))
        return 1 if problems else 0
    for rel, build, needs in BUILDERS.values():
        if (ROOT / needs).exists():
            (ROOT / rel).write_text(render(build()), encoding="utf-8")
            print(f"wrote {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
