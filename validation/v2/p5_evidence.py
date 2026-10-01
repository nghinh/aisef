"""P5 evidence records — computed from the code, never written by hand, with a --check twin (the P3/P4 contract).

Each record carries `properties`, named facts measured on the implementation by running the named test case (the test
is the measurement); `--check` re-derives every record and fails if it differs from the committed one or if any
property is false. Records hold outcomes only — never a pid, a path, a duration or a wall-clock time — so a rebuild
is byte-identical on Linux, macOS and Windows (Q0 rebuilds them on every CI job).

Once P5 is sealed (`closure-evidence/v2/P5-FINAL-SEAL.json` binds each record by sha256), a record is a historical
measurement: `--check` verifies it by identity against the seal and reads its properties, and never re-derives or
rewrites it — a later phase's kernel grows the except-boundary count and changes mechanism sources, so a re-derivation
at a later HEAD could never be byte-identical (ARCHITECTURE-EXCEPTION-V2-005, owner §15: P5 evidence files are not
mutated). Regeneration refuses a sealed record.

    python -P validation/v2/p5_evidence.py            # write every unsealed record whose package is implemented
    python -P validation/v2/p5_evidence.py --check    # fail on drift or on a false property
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


# --------------------------------------------------------------------------------------- WP-5.4

def adequacy() -> dict:
    import ast
    t = _module("aisef_v2_p5_test_adequacy", "tests/v2/p5/test_adequacy.py")
    typed = cases(t, "Cases", "test_ADEQ_1_all_green_is_ADEQUATE",
                  "test_ADEQ_2_primary_UNRUNNABLE_has_no_outcome_and_the_environment_owner_the_typed_fact_carries",
                  "test_ADEQ_3_regression_UNRUNNABLE_has_no_outcome_and_keeps_the_environment_owner",
                  "test_ADEQ_4_the_story_tests_FAILED_is_INADEQUATE_DEVELOPER",
                  "test_ADEQ_5_NO_STORY_TESTS_MATCHED_is_INADEQUATE_DEVELOPER",
                  "test_ADEQ_6_a_developer_caused_collection_failure_is_INADEQUATE_DEVELOPER",
                  "test_ADEQ_7_an_integration_owned_collection_failure_is_never_charged_to_the_developer",
                  "test_ADEQ_8_VACUOUS_is_INADEQUATE_DEVELOPER", "test_ADEQ_9_IRRELEVANT_is_INADEQUATE_DEVELOPER",
                  "test_ADEQ_10_regressions_FAILED_is_INADEQUATE_DEVELOPER",
                  "test_ADEQ_11_INDETERMINATE_vacuity_alone_is_INCOMPLETE_non_blocking_uncharged",
                  "test_ADEQ_12_UNMEASURABLE_relevance_alone_is_INCOMPLETE_non_blocking_uncharged",
                  "test_ADEQ_13_FAILED_with_UNMEASURABLE_is_INADEQUATE_the_hard_defect_dominates",
                  "test_ADEQ_14_regressions_FAILED_with_INDETERMINATE_is_INADEQUATE",
                  "test_ADEQ_15_opposite_TDD_chronology_with_identical_typed_inputs_is_the_identical_result")
    real = cases(t, "ForReal", "test_ADEQ_1_for_real", "test_ADEQ_2_for_real_the_story_runner_cannot_execute",
                 "test_ADEQ_3_for_real_the_regression_runner_cannot_execute", "test_ADEQ_4_and_10_for_real",
                 "test_ADEQ_6_and_7_for_real_collection_failures_by_their_typed_owner",
                 "test_ADEQ_R_for_real_regression_selection_and_collection_by_their_typed_owner",
                 "test_ADEQ_16_for_real_a_pure_deletion_otherwise_green_is_INCOMPLETE",
                 "test_ADEQ_17_for_real_a_tests_only_diff_is_INADEQUATE_by_the_frozen_rules")
    whole = cases(t, "Exhaustive", "test_assembly_is_total_and_follows_the_precedence",
                  "test_owner_blocking_and_charge_are_read_from_the_typed_facts_only",
                  "test_ADEQ_R_the_regression_dimension_follows_the_same_typed_rules")
    shape = cases(t, "Shape", "test_the_fields_are_the_rfcs", "test_typed_executions_and_no_sensitivity",
                  "test_UNRUNNABLE_story_execution_carries_nothing_measured_and_no_outcome",
                  "test_EXECUTED_story_execution_carries_typed_measurements_of_tests_that_ran",
                  "test_UNRUNNABLE_regressions_carry_no_outcome",
                  "test_both_EXECUTED_the_outcome_is_defined_and_is_what_the_facts_assemble_to")
    sep = cases(t, "Separation", "test_no_path_reaches_a_product_proof_a_journal_or_a_budget",
                "test_no_prose_is_read_for_control_and_no_side_state_exists",
                "test_no_policy_object_decides_adequacy_blocking_and_INCOMPLETE_cannot_block_under_any")
    src = ast.parse((ROOT / "aisef2/quality/adequacy.py").read_text(encoding="utf-8"))
    names = {n.id for n in ast.walk(src) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(src) if isinstance(n, ast.Attribute)}
    adeq = lambda n: typed[next(k for k in typed if k.startswith(f"test_ADEQ_{n}_"))]  # noqa: E731
    return {
        "record": "AISEF V2 — P5 ADEQUACY",
        "work_package": "WP-5.4",
        "rfc": "§15, §15.3 (F1 payload enum AdequacyOutcome: ADEQUATE, INADEQUATE, INCOMPLETE); §31 process/tdd-chronology",
        "implementation": "aisef2/quality/adequacy.py",
        "model": {"inputs": "typed facts only: WP-5.1 TestExecution for the story's tests and for the regressions, WP-5.3 "
                  "Vacuity, WP-5.2 Relevance; process/tdd-chronology recorded verbatim when supplied",
                  "precedence": ["1 mandatory execution availability: story UNRUNNABLE or regressions UNRUNNABLE => outcome "
                                 "None, owner the typed ENVIRONMENT the execution carries",
                                 "2 developer-owned defects (§15.3) => INADEQUATE / DEVELOPER: FAILED, NO_STORY_TESTS_MATCHED, "
                                 "NOT_COLLECTABLE typed DEVELOPER, VACUOUS, IRRELEVANT of tests that ran; and under the same typed "
                                 "rules for the regressions: FAILED, NO_STORY_TESTS_MATCHED, NOT_COLLECTABLE typed DEVELOPER",
                                 "3 secondary gaps => INCOMPLETE / nobody / never blocks: INDETERMINATE vacuity, UNMEASURABLE "
                                 "relevance, regressions NOT_COLLECTABLE typed INTEGRATION",
                                 "4 ADEQUATE constructed positively: story tests PASSED, NON_VACUOUS, RELEVANT, regressions RAN and PASSED"],
                  "blocking": "may_block(outcome) states what §15.3 permits (INADEQUATE MAY, INCOMPLETE MUST NOT); no policy "
                              "object in aisef2 decides adequacy blocking at this commit",
                  "chronology": "process/tdd-chronology: a read-only copy on the Assembly, read for nothing"},
        "properties": {
            **{f"ADEQ_{n}": adeq(n) for n in range(1, 16)},
            "ADEQ_16": real["test_ADEQ_16_for_real_a_pure_deletion_otherwise_green_is_INCOMPLETE"],
            "ADEQ_17": real["test_ADEQ_17_for_real_a_tests_only_diff_is_INADEQUATE_by_the_frozen_rules"],
            "ADEQ_for_real_through_WP_5_1_to_5_3": all(real.values()),
            "UNRUNNABLE_produces_no_AdequacyOutcome": adeq(2) and adeq(3)
                and shape["test_UNRUNNABLE_story_execution_carries_nothing_measured_and_no_outcome"]
                and shape["test_UNRUNNABLE_regressions_carry_no_outcome"],
            "INCOMPLETE_never_blocks_never_charges_the_developer": adeq(7) and adeq(11) and adeq(12)
                and whole["test_owner_blocking_and_charge_are_read_from_the_typed_facts_only"]
                and sep["test_no_policy_object_decides_adequacy_blocking_and_INCOMPLETE_cannot_block_under_any"],
            "hard_defect_dominates_secondary_gap": adeq(13) and adeq(14),
            "precedence_total_over_333_well_formed_inputs": whole["test_assembly_is_total_and_follows_the_precedence"],
            "shape_refuses_every_contradiction": all(shape.values()),
            "tdd_chronology_recorded_never_consulted": adeq(15),
            "product_proof_journal_and_budget_unreachable": sep["test_no_path_reaches_a_product_proof_a_journal_or_a_budget"]
                and not names & {"ProductProofSpec", "ProbeResult", "CandidateProof", "VerifiedProof", "BehaviorVerdict",
                                 "ContractSatisfaction", "FailureCode", "EventType"},
            "owner_from_typed_facts_never_from_prose": sep["test_no_prose_is_read_for_control_and_no_side_state_exists"]
                and whole["test_owner_blocking_and_charge_are_read_from_the_typed_facts_only"],
            "INTEGRATION_never_converted_to_DEVELOPER": adeq(7) and real["test_ADEQ_6_and_7_for_real_collection_failures_by_their_typed_owner"],
            "no_failure_code_required": "FailureCode" not in names and "emit" not in names,
            "regression_dimension_same_typed_rules": whole["test_ADEQ_R_the_regression_dimension_follows_the_same_typed_rules"]
                and real["test_ADEQ_R_for_real_regression_selection_and_collection_by_their_typed_owner"],
        },
        "regression_dimension": {"ruling": "owner ruling after the WP-5.4 exit report (RFC §15 `regressions`: same typed rules; "
                                 "§15.0 rule 5): UNRUNNABLE => None; FAILED, NO_STORY_TESTS_MATCHED, NOT_COLLECTABLE typed "
                                 "DEVELOPER => INADEQUATE / DEVELOPER; NOT_COLLECTABLE typed INTEGRATION => INCOMPLETE, no "
                                 "developer charge, non-blocking; PASSED + STORY_TESTS_RAN => satisfied",
                                 "pinned_by": "Exhaustive.test_ADEQ_R_the_regression_dimension_follows_the_same_typed_rules"},
    }


# --------------------------------------------------------------------------------------- WP-5.5

def invariants() -> dict:
    import importlib
    from aisef2.errors import InvariantError
    from aisef2.invariants import registry as reg
    t = _module("aisef_v2_p5_test_invariants", "tests/v2/p5/test_invariants.py")
    registry = cases(t, "Registry", "test_the_nine_are_registered_with_frozen_titles_and_resolved_mechanisms",
                     "test_INV_REG_1_an_invariant_without_a_mechanism_is_refused",
                     "test_INV_REG_2_an_invariant_missing_from_one_tier_is_refused",
                     "test_INV_REG_3_an_invariant_declared_but_not_armed_is_refused",
                     "test_unknown_duplicate_omitted_or_retitled_invariants_are_refused",
                     "test_INV_MECH_1_a_mechanism_that_resolves_nowhere_is_refused",
                     "test_registry_and_document_drift_is_refused",
                     "test_the_document_renders_typed_identifiers_never_read_for_control",
                     "test_InvariantError_is_structurally_uncatchable_by_except_Exception_and_names_its_module")
    arming = cases(t, "Arming", "test_every_tier_arms_all_nine_before_its_first_test_module",
                   "test_arming_is_idempotent_and_fails_closed_without_touching_the_armed_state",
                   "test_a_runtime_guard_refuses_to_work_in_an_unarmed_process")
    escape = cases(t, "Uncontainable", "test_INV_EXC_1_raised_inside_except_Exception_it_escapes",
                   "test_INV_EXC_2_nested_broad_catches_all_let_it_escape",
                   "test_the_violation_escapes_the_kernels_own_boundaries", "test_the_audit_holds_over_the_whole_kernel",
                   "test_the_audit_flags_every_swallowing_pattern_and_accepts_every_re_raise",
                   "test_the_hierarchy_is_part_of_the_audit")
    one = cases(t, "RequirementAuthority", "test_INV_I_1_no_kernel_control_path_reads_requirement_text",
                "test_INV_I_2_an_unapproved_contract_cannot_become_product_truth",
                "test_INV_I_3_changing_a_requirement_or_contract_hash_invalidates_the_binding",
                "test_INV_I_4_an_artefacts_self_claims_grant_no_authority")
    two = cases(t, "SemanticDeterminism", "test_INV_II_1_developer_test_topology_is_not_an_input_of_the_product_verdict",
                "test_INV_II_2_wall_clock_time_does_not_control_verdicts_or_projections",
                "test_INV_II_3_component_import_order_does_not_alter_the_fold",
                "test_INV_II_4_the_same_frozen_inputs_give_the_same_run_identity")
    three = cases(t, "IndependentEvidence", "test_INV_III_1_the_implementer_cannot_manufacture_a_sealed_record",
                  "test_INV_III_2_the_verifier_scope_is_independently_acquired",
                  "test_INV_III_3_confinement_is_not_a_passable_parameter",
                  "test_INV_III_4_developer_tests_cannot_certify_product_proof")
    four = cases(t, "TypedOwnership", "test_INV_IV_no_owner_consumes_another_owners_budget",
                 "test_INV_IV_INCOMPLETE_and_UNRUNNABLE_never_charge_the_developer",
                 "test_INV_IV_retry_reads_typed_fields_only_and_keeps_no_counter")
    five = cases(t, "ReproducibleQualification", "test_INV_V_comparability_rejects_every_identity_mismatch")
    six = cases(t, "ImmutableProvenance", "test_INV_VI_abbreviated_shas_are_rejected_where_full_identity_is_required",
                "test_INV_VI_mutable_labels_cannot_replace_immutable_ids", "test_INV_VI_the_journal_is_append_only",
                "test_INV_VI_frozen_artefact_drift_is_detected", "test_INV_VI_verdict_identity_fields_are_immutable")
    seven = cases(t, "NoProseControl", "test_INV_PROSE_1_hostile_external_strings_never_become_control_values",
                  "test_INV_VII_an_external_owner_in_a_journal_payload_is_refused", "test_INV_VII_the_static_guards_stand")
    eight = cases(t, "MemoryIsContext", "test_INV_MEM_1_agent_or_context_text_cannot_enter_an_evidence_field",
                  "test_the_boundary_inspects_no_model_and_fails_closed")
    nine = cases(t, "NoDeveloperArtefactAtParent", "test_INV_PARENT_1_parent_developer_test_execution_is_refused_statically",
                 "test_INV_PARENT_1_the_apis_are_structurally_candidate_only",
                 "test_the_only_counterfactual_is_candidate_side_vacuity")
    authority = cases(t, "MutationAuthority", "test_INV_MUTATION_AUTHORITY_destructive_sites_of_the_invariant_code_are_ledgered")
    registered = reg.register()
    for tier in reg.Tier:
        importlib.import_module(tier.value.replace("/", "."))
    armed = reg.armed()
    eb = _module("aisef_v2_except_boundaries", "validation/v2/except_boundaries.py")
    audit = eb.audit(ROOT)
    return {
        "record": "AISEF V2 — P5 INVARIANTS",
        "work_package": "WP-5.5",
        "rfc": "§4 (F10: InvariantId I..IX, the frozen titles, every one armed with a named mechanism); §31",
        "implementation": "aisef2/invariants/registry.py, aisef2/invariants/evidence.py, aisef2/errors.py, "
                          "validation/v2/except_boundaries.py, kernel rule NO_DEVELOPER_ARTEFACT_AT_PARENT",
        "registry": {"invariants": [i.id.value for i in registered.invariants],
                     "mechanisms": {i.id.value: [f"{m.id} ({m.kind.value}) {m.ref}" for m in i.mechanisms] for i in registered.invariants},
                     "uncontainable": [f"{m.id} ({m.kind.value}) {m.ref}" for m in reg.UNCONTAINABLE],
                     "tiers": [t.value for t in reg.Tier], "registry_digest": registered.digest,
                     "mechanism_digest": registered.mechanism_digest, "document": reg.DOC_REL},
        "arming": {t.value: sorted(i.value for i in armed.get(t, ())) for t in reg.Tier},
        "except_boundaries": {"counts": audit["counts"], "problems": audit["problems"],
                              "invariant_error_base": [c.__name__ for c in InvariantError.__mro__[1:-1]]},
        "properties": {
            "I_to_IX_registered_with_resolved_mechanisms": registry["test_the_nine_are_registered_with_frozen_titles_and_resolved_mechanisms"]
                and [i.id.value for i in registered.invariants] == ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"],
            "registration_fails_closed": all(registry[k] for k in registry if "refused" in k),
            "INV_REG_1": registry["test_INV_REG_1_an_invariant_without_a_mechanism_is_refused"],
            "INV_REG_2": registry["test_INV_REG_2_an_invariant_missing_from_one_tier_is_refused"],
            "INV_REG_3": registry["test_INV_REG_3_an_invariant_declared_but_not_armed_is_refused"],
            "INV_MECH_1": registry["test_INV_MECH_1_a_mechanism_that_resolves_nowhere_is_refused"],
            "registry_docs_synchronized": registry["test_registry_and_document_drift_is_refused"],
            "armed_in_every_tier_before_the_tier_mounts": arming["test_every_tier_arms_all_nine_before_its_first_test_module"]
                and all(set(armed.get(t, ())) == set(reg.InvariantId) for t in reg.Tier),
            "runtime_guards_fail_closed_unarmed": arming["test_a_runtime_guard_refuses_to_work_in_an_unarmed_process"],
            "INV_EXC_1": escape["test_INV_EXC_1_raised_inside_except_Exception_it_escapes"],
            "INV_EXC_2": escape["test_INV_EXC_2_nested_broad_catches_all_let_it_escape"],
            "violation_escapes_the_kernels_own_boundaries": escape["test_the_violation_escapes_the_kernels_own_boundaries"],
            "except_boundary_audit_clean": escape["test_the_audit_holds_over_the_whole_kernel"] and audit["problems"] == []
                and set(audit["counts"]) <= {eb.RERAISES, eb.STRUCTURAL},
            "audit_flags_every_swallowing_pattern": escape["test_the_audit_flags_every_swallowing_pattern_and_accepts_every_re_raise"]
                and escape["test_the_hierarchy_is_part_of_the_audit"],
            "InvariantError_uncatchable_by_except_Exception": issubclass(InvariantError, BaseException)
                and not issubclass(InvariantError, Exception)
                and registry["test_InvariantError_is_structurally_uncatchable_by_except_Exception_and_names_its_module"],
            **{f"INV_I_{n}": one[k] for n, k in enumerate(one, 1)},
            **{f"INV_II_{n}": two[k] for n, k in enumerate(two, 1)},
            **{f"INV_III_{n}": three[k] for n, k in enumerate(three, 1)},
            "INV_IV_cross_charge_impossible": all(four.values()),
            "INV_V_comparability_rejects_mismatch": all(five.values()),
            "INV_VI_immutable_provenance": all(six.values()),
            "INV_PROSE_1": seven["test_INV_PROSE_1_hostile_external_strings_never_become_control_values"],
            "INV_VII_no_prose_control": all(seven.values()),
            "INV_MEM_1": eight["test_INV_MEM_1_agent_or_context_text_cannot_enter_an_evidence_field"],
            "INV_VIII_evidence_origin_boundary": all(eight.values()),
            "INV_PARENT_1": nine["test_INV_PARENT_1_parent_developer_test_execution_is_refused_statically"]
                and nine["test_INV_PARENT_1_the_apis_are_structurally_candidate_only"],
            "INV_IX_candidate_only": all(nine.values()),
            "INV_MUTATION_AUTHORITY_intact": all(authority.values()),
        },
    }


BUILDERS: dict[str, tuple[str, Callable[[], dict], str]] = {
    "WP-5.1": ("closure-evidence/v2/P5-TEST-EXECUTION.json", test_execution, "aisef2/quality/test_execution.py"),
    "WP-5.2": ("closure-evidence/v2/P5-RELEVANCE.json", relevance, "aisef2/quality/relevance.py"),
    "WP-5.3": ("closure-evidence/v2/P5-VACUITY.json", vacuity, "aisef2/quality/vacuity.py"),
    "WP-5.4": ("closure-evidence/v2/P5-ADEQUACY.json", adequacy, "aisef2/quality/adequacy.py"),
    "WP-5.5": ("closure-evidence/v2/P5-INVARIANTS.json", invariants, "aisef2/invariants/registry.py"),
}


def render(record: dict) -> str:
    return json.dumps(record, indent=1, ensure_ascii=False) + "\n"


def problems_of(record: dict) -> list[str]:
    props = record.get("properties") or {}
    out = [] if props else [f"{record.get('work_package')}: record carries no properties"]
    return out + [f"{record.get('work_package')}: property {k} is false" for k, v in props.items() if v is not True]


SEAL_REL = "closure-evidence/v2/P5-FINAL-SEAL.json"


def sealed(root: pathlib.Path = ROOT) -> dict[str, str]:
    """record path -> the sha256 the P5 seal binds it to; empty before the seal exists."""
    p = root / SEAL_REL
    if not p.exists():
        return {}
    seal = json.loads(p.read_bytes().replace(b"\r\n", b"\n"))
    return {v["path"]: v["sha256"] for v in seal["p5_evidence"].values()}


def _lf_sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def check(root: pathlib.Path = ROOT) -> list[str]:
    out = []
    bound = sealed(root)
    for rel, build, needs in BUILDERS.values():
        if not (root / needs).exists():
            continue
        if rel in bound:  # sealed: identity against the seal, properties as recorded; never re-derived
            committed = root / rel
            if not committed.exists():
                out.append(f"{rel} is missing")
            elif _lf_sha(committed) != bound[rel]:
                out.append(f"{rel} differs from the sha256 bound by {SEAL_REL}: a sealed record is never rewritten")
            else:
                out += problems_of(json.loads(committed.read_text(encoding="utf-8")))
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
    bound = sealed()
    for rel, build, needs in BUILDERS.values():
        if rel in bound:
            print(f"sealed  {rel}: bound by {SEAL_REL}; not regenerated")
        elif (ROOT / needs).exists():
            (ROOT / rel).write_text(render(build()), encoding="utf-8")
            print(f"wrote {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
