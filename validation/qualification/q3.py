"""Q3 — fault injection (RFC §27; owner §16–§20): the full current fault matrix, each fault typed — execution status,
failure code, owner, retryability, budget target, terminal state, journal state, residual state — with the owner,
retryability and budget read from the taxonomy (`aisef2.control.owner.classify`), never from prose; the V2-006 race
family with its stress orderings A–G; the watchdog / anchor ownership proof asserted against the operating system;
the ProcessRange.wait deadline contract measured; and the frozen V1 102-cell matrix, which still runs on the same tree.

The rung runs on each qualification platform (Linux, Windows) and records the platform's own ownership mechanism.

Cycle 2 (QP-2.6; CYCLE2-QUALIFICATION-PLAN §4): the Cycle-2 families, each row typed the same way and run on the
Cycle-2 candidate — FM2-CLI-HARNESS, FM2-CLI-SUBJECT, FM2-CLI-STREAM (cli_invocation), FM2-FILE (file_artifact),
FM2-EFFECT (process_effect) and the bytecode family re-run under every new probe (FM2-PYC-CLI, FM2-PYC-EFFECT,
FM2-PYC-V2); the Cycle-1 families and the V1 matrix are unchanged and re-run.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import time

from . import common as C

EXECUTION = ("EXECUTED", "UNRUNNABLE", "INVALID_SPEC", "INTERRUPTED", "STAGE_FAILURE_TYPED", "REFUSED")
TERMINAL = ("BEGIN", "ACTIVE", "ENDED", "COMMIT", "ROLLBACK", "RETRY", "TORN", "CLEAN", "ABANDONED", "INTERRUPTED", "DISPOSING",
            "NOT_STARTED", "n/a")
RESIDUAL = ("RELEASED_EMPTY", "RESIDUAL_NAMED", "ABANDONED_NAMED", "NONE", "OS_ASSERTED_GONE", "NEVER_SIGNALLED")
MODULES = ("tests.v2.p4.test_interruption", "tests.v2.p4.test_run_scope", "tests.v2.p4.test_story_scope", "tests.v2.p4.test_process_range",
           "tests.v2.p4.test_process_table", "tests.v2.p2.test_signal_provenance", "tests.v2.p2.test_signal_provenance_abort",
           "tests.v2.test_p6_orchestration", "tests.v2.test_p6_stages", "tests.v2.p4.test_budgets", "tests.v2.p1.test_routing",
           "tests.v2.p2.test_probe_protocol", "tests.v2.p2.test_python_callable", "tests.v2.p5.test_test_execution",
           "tests.v2.p2.test_story_admission", "tests.v2.test_v2_005", "tests.v2.test_v2_006", "tests.v2.test_v2_006_repeat",
           "tests.v2.test_p7_finding_001",
           # Cycle 2
           "tests.v2.test_c2_cli_invocation", "tests.v2.test_c2_cli_protocol", "tests.v2.test_c2_file_artifact",
           "tests.v2.test_probe_process_effect", "tests.v2.test_probe_process_effect_bytecode",
           "tests.v2.test_python_callable_v2_bytecode")
V1_MATRIX_MODULES = ("tests.hardening.test_fault_matrix", "tests.hardening.test_compound_faults")


def _row(fid, cls, what, cases, *, execution, code=None, owner=None, retry=None, budget=None, terminal="n/a",
         journal="", residual="NONE", platforms=("linux", "windows", "darwin")):
    return {"id": fid, "class": cls, "fault": what, "cases": cases, "expected": {
        "execution_status": execution, "failure_code": code, "owner": owner, "retryability": retry, "budget_target": budget,
        "terminal_state": terminal, "journal_state": journal, "residual_state": residual}, "platforms": list(platforms)}


PYC = "tests.v2.test_p7_finding_001:Bytecode."
ORCH, ST, INT, RS, SS, PR, SP, PC, TE = ("tests.v2.test_p6_orchestration:Orchestration.", "tests.v2.test_p6_stages:", "tests.v2.p4.test_interruption:",
                                        "tests.v2.p4.test_run_scope:Lifetime.", "tests.v2.p4.test_story_scope:Scope.", "tests.v2.p4.test_process_range:",
                                        "tests.v2.p2.test_signal_provenance:", "tests.v2.p2.test_python_callable:", "tests.v2.p5.test_test_execution:")
BYTECODE_FAMILY = [
    # bytecode / cache state (P7-FINDING-001 correction, §25): none of these can change the product verdict; an
    # inability to run the case is UNRUNNABLE by the run's own typing, never FAILED
    _row("FM2-PYC-1", "bytecode", "in-tree stale bytecode with a matching timestamp and size", [PYC + "test_PYC_1_in_tree_stale_bytecode_with_a_matching_header_is_not_the_subject_the_source_is"],
         execution="EXECUTED", journal="probe/evaluated: the source's verdict; the in-tree bytecode is not the subject"),
    _row("FM2-PYC-2", "bytecode", "implementer and verifier checkouts with different file dates", [PYC + "test_PYC_2_two_checkouts_of_the_same_content_with_different_dates_observe_one_verdict",
                                                                                                    PYC + "test_PYC_11_a_size_and_whole_second_collision_cannot_split_the_two_parties_of_a_proof",
                                                                                                    "tests.v2.test_p7_finding_001:Revision.test_PYC_11b_two_worktrees_of_one_revision_with_committed_stale_bytecode_agree"],
         execution="EXECUTED", journal="proof/verified agreement True; one verdict from the source on both sides"),
    _row("FM2-PYC-3", "bytecode", "committed __pycache__ present at the revision", [PYC + "test_PYC_3_a_checkout_with_committed_bytecode_is_byte_identical_before_and_after_the_proof",
                                                                                     PYC + "test_PYC_4_the_probe_writes_no_bytecode_into_the_checkout"],
         execution="EXECUTED", journal="the checkout byte-identical before and after; git status unchanged; no bytecode written into it"),
    _row("FM2-PYC-4", "bytecode", "cache placement: fresh, empty, outside the checkout, distinct per party, never reused", [PYC + "test_PYC_5_the_bytecode_cache_is_fresh_empty_and_outside_the_checkout",
                                                                                                                            PYC + "test_PYC_5b_under_a_story_scratch_the_cache_lies_there_and_is_left_to_the_scratch",
                                                                                                                            PYC + "test_PYC_6_implementer_and_verifier_get_distinct_caches",
                                                                                                                            PYC + "test_PYC_7_an_evaluation_never_reuses_the_cache_of_the_one_before"],
         execution="EXECUTED", journal="the prefix under the story scratch (or the probe's own temporary directory), empty at launch, one per evaluation"),
    _row("FM2-PYC-5", "bytecode", "pre-existing external cache contamination attempt (an earlier evaluation's bytecode) and the environment route", [PYC + "test_PYC_7_an_evaluation_never_reuses_the_cache_of_the_one_before",
                                                                                                                                                     PYC + "test_PYC_8_isolated_mode_keeps_the_command_line_controls_and_drops_the_environment_route"],
         execution="EXECUTED", journal="a new prefix per evaluation; -I keeps -B and -X pycache_prefix and drops PYTHON* variables"),
    _row("FM2-PYC-6", "bytecode", "mechanism independence: -B removed (external cache alone) and external cache removed (-B alone)", [PYC + "test_PYC_9_without_B_the_external_cache_alone_keeps_the_stale_bytecode_out_and_the_checkout_unwritten",
                                                                                                                                       PYC + "test_PYC_10_without_the_external_cache_the_stale_bytecode_decides_the_verdict_the_reproducer_detects_the_defect"],
         execution="EXECUTED", journal="the external cache carries correctness; without it the deterministic reproducer detects the defect"),
    _row("FM2-PYC-7", "bytecode", "one revision across repeated fresh scopes", [PYC + "test_PYC_12_one_revision_across_repeated_fresh_scopes_observes_one_verdict"],
         execution="EXECUTED", journal="identical verdict on every evaluation"),
    _row("FM2-PYC-9", "bytecode", "an evaluation directory inside the checkout (the cache would be product state), or one that cannot be created", [PYC + "test_PYC_13_an_evaluation_directory_inside_the_checkout_is_refused_not_used",
                                                                                                                                                       PYC + "test_PYC_14_an_evaluation_directory_that_cannot_be_created_is_a_harness_failure"],
         execution="UNRUNNABLE", journal="the observation is a harness failure, so the probe is UNRUNNABLE, refused before any launch; nothing written into the checkout"),
    _row("FM2-PYC-8", "bytecode", "the finding's full path: a merged revision carrying stale bytecode, the developer's file dated into the collision", [ORCH + "test_DIAG_2_a_developer_file_dated_to_committed_stale_bytecode_no_longer_splits_the_two_parties_at_one_merged_revision",
                                                                                                                                                       ORCH + "test_DIAG_1_the_observation_writes_no_bytecode_and_the_merged_revision_of_S0_carries_none",
                                                                                                                                                       ORCH + "test_DIAG_3_on_the_natural_path_every_proof_agrees_whatever_the_checkouts_hold"],
         execution="EXECUTED", code="POST_MERGE_REGRESSION", owner="INTEGRATION", retry="NOT_RETRYABLE", budget=None, terminal="ENDED/ROLLBACK",
         journal="both parties REFUTED at the merged revision; proof/verified agreement True; POST_MERGE_REGRESSION; the merge reverted; no bytecode written by the observation"),
]
FAULT_MATRIX = [
    # provider
    _row("FM2-PROV-1", "provider", "developer session outage mid-story", [ORCH + "test_ORCH_2_a_developer_outage_mid_story_is_a_typed_PROVIDER_failure_with_no_cross_charge"],
         execution="STAGE_FAILURE_TYPED", code="PROVIDER_UNAVAILABLE", owner="PROVIDER", retry="RETRYABLE", budget="PROVIDER", terminal="ENDED/RETRY",
         journal="FAILURE_OBSERVED(PROVIDER_UNAVAILABLE) owner+retryable from the taxonomy; STORY_RETRY cites it; no developer charge", residual="RELEASED_EMPTY"),
    _row("FM2-PROV-2", "provider", "reviewer session outage", [ORCH + "test_ORCH_2b_a_reviewer_outage_stays_PROVIDER", ST + "Review.test_an_outage_a_capability_failure_and_a_failed_answer_are_typed"],
         execution="STAGE_FAILURE_TYPED", code="PROVIDER_UNAVAILABLE", owner="PROVIDER", retry="RETRYABLE", budget="PROVIDER", terminal="ENDED/RETRY",
         journal="FAILURE_OBSERVED(PROVIDER_UNAVAILABLE); never CAPABILITY_UNRUNNABLE", residual="RELEASED_EMPTY"),
    # tool
    _row("FM2-TOOL-1", "tool", "developer-test runner missing at the candidate", [ORCH + "test_ORCH_SCHEMA_4_tests_that_cannot_run_are_TESTS_UNRUNNABLE_with_no_developer_charge",
                                                                                   TE + "RealRunner.test_TEST_1_for_real_the_configured_runner_is_absent"],
         execution="UNRUNNABLE", code="TESTS_UNRUNNABLE", owner="ENVIRONMENT", retry="RETRYABLE", budget="ENVIRONMENT", terminal="ENDED/RETRY",
         journal="TESTS_ADEQUACY absent (no AdequacyOutcome); FAILURE_OBSERVED(TESTS_UNRUNNABLE) with environment provenance", residual="RELEASED_EMPTY"),
    _row("FM2-TOOL-2", "tool", "runner crashes before reporting", [TE + "RealRunner.test_a_runner_that_crashes_before_reporting_is_UNRUNNABLE"],
         execution="UNRUNNABLE", code="TESTS_UNRUNNABLE", owner="ENVIRONMENT", retry="RETRYABLE", budget="ENVIRONMENT", journal="typed TestExecution UNRUNNABLE, no outcome, no selection", residual="RELEASED_EMPTY"),
    _row("FM2-TOOL-3", "tool", "runner ended by a signal", [TE + "RealRunner.test_a_runner_ended_by_a_signal_is_UNRUNNABLE"],
         execution="UNRUNNABLE", code="TESTS_UNRUNNABLE", owner="ENVIRONMENT", retry="RETRYABLE", budget="ENVIRONMENT", journal="typed TestExecution UNRUNNABLE", residual="RELEASED_EMPTY"),
    _row("FM2-TOOL-4", "tool", "developer-test harness deadline", [TE + "RealRunner.test_the_harness_deadline_is_UNRUNNABLE_and_the_range_is_released"],
         execution="UNRUNNABLE", code="TESTS_UNRUNNABLE", owner="ENVIRONMENT", retry="RETRYABLE", budget="ENVIRONMENT", journal="typed TestExecution UNRUNNABLE", residual="RELEASED_EMPTY"),
    _row("FM2-TOOL-5", "tool", "developer tests inadequate under a blocking policy", [ORCH + "test_ORCH_SCHEMA_5_INADEQUATE_under_a_blocking_policy_is_TESTS_INADEQUATE_owned_by_DEVELOPER",
                                                                                     TE + "RealRunner.test_TEST_2_for_real"],
         execution="EXECUTED", code="TESTS_INADEQUATE", owner="DEVELOPER", retry="RETRYABLE", budget="DEVELOPER", terminal="ENDED/RETRY",
         journal="TESTS_ADEQUACY(INADEQUATE); FAILURE_OBSERVED(TESTS_INADEQUATE)", residual="RELEASED_EMPTY"),
    _row("FM2-TOOL-6", "tool", "security scanner ran and found", [ORCH + "test_ORCH_7_and_SCHEMA_8_a_scanner_that_ran_and_found_is_EXECUTED_and_SECURITY_FINDING",
                                                                    ST + "Security.test_a_scanner_that_ran_and_found_is_EXECUTED_with_a_row_per_finding"],
         execution="EXECUTED", code="SECURITY_FINDING", owner="SECURITY", retry="RETRYABLE", budget="SECURITY", terminal="ENDED/RETRY",
         journal="GATE_CHECK row per finding; FAILURE_OBSERVED(SECURITY_FINDING) from the adapter's typed result", residual="RELEASED_EMPTY"),
    # sandbox / environment
    _row("FM2-ENV-1", "sandbox_environment", "probe harness interpreter absent", [PC + "ProbeAbs.test_PROBE_ABS_1_harness_unavailable_is_UNRUNNABLE_ENVIRONMENT_with_no_verdict",
                                                                                 PC + "Observations.test_a_tool_absent_harness_is_named"],
         execution="UNRUNNABLE", code="PROBE_UNRUNNABLE", owner="ENVIRONMENT", retry="RETRYABLE", budget="ENVIRONMENT", journal="PROBE_EVALUATED UNRUNNABLE, no verdict", residual="RELEASED_EMPTY"),
    _row("FM2-ENV-2", "sandbox_environment", "review / security capability cannot run", [ORCH + "test_ORCH_6_and_SCHEMA_9_a_reviewer_environment_failure_is_CAPABILITY_UNRUNNABLE_ENVIRONMENT_never_DEVELOPER",
                                                                                          ST + "Security.test_a_scanner_that_cannot_start_or_report_is_CAPABILITY_UNRUNNABLE"],
         execution="UNRUNNABLE", code="CAPABILITY_UNRUNNABLE", owner="ENVIRONMENT", retry="RETRYABLE", budget="ENVIRONMENT", terminal="ENDED/RETRY",
         journal="FAILURE_OBSERVED(CAPABILITY_UNRUNNABLE); never DEVELOPER", residual="RELEASED_EMPTY"),
    _row("FM2-ENV-3", "sandbox_environment", "collection failure on a declared environment dependency (SS-81 A)",
         [TE + "RealRunner.test_collection_failure_on_a_declared_environment_dependency_is_UNRUNNABLE_ENVIRONMENT", TE + "Classify.test_rule_4_collection_cause_on_a_declared_environment_dependency_is_UNRUNNABLE_ENVIRONMENT"],
         execution="UNRUNNABLE", code="TESTS_UNRUNNABLE", owner="ENVIRONMENT", retry="RETRYABLE", budget="ENVIRONMENT", journal="typed TestExecution UNRUNNABLE with its collection cause", residual="RELEASED_EMPTY"),
    _row("FM2-ENV-4", "sandbox_environment", "probe harness timeout vs subject deadline", ["tests.v2.p2.test_probe_protocol:SubjectDeadline.test_TIME_1_a_harness_timeout_is_UNRUNNABLE",
                                                                                            PC + "Time.test_TIME_5_a_subject_timeout_is_never_ENVIRONMENT"],
         execution="UNRUNNABLE", code="PROBE_UNRUNNABLE", owner="ENVIRONMENT", retry="RETRYABLE", budget="ENVIRONMENT", journal="harness timeout UNRUNNABLE; a subject deadline is EXECUTED with the spec's verdict", residual="RELEASED_EMPTY"),
    # credentials
    _row("FM2-CRED-1", "credentials", "missing credential", ["tests.v2.p1.test_routing:Credentials.test_CRED_1_missing_credential_never_consumes_developer_budget"],
         execution="STAGE_FAILURE_TYPED", code="MISSING_CREDENTIAL", owner="ENVIRONMENT", retry="RESOLVED_BY_POLICY", budget="ENVIRONMENT", journal="FAILURE_OBSERVED(MISSING_CREDENTIAL); no developer charge"),
    _row("FM2-CRED-2", "credentials", "invalid / rejected credential", ["tests.v2.p1.test_routing:Credentials.test_CRED_2_invalid_credential_never_consumes_developer_or_provider_budget",
                                                                        "tests.v2.p1.test_routing:Credentials.test_CRED_3_invalid_credential_is_non_retryable",
                                                                        "tests.v2.p4.test_budgets:Budgets.test_D_006_a_credential_or_environment_rejection_never_consumes_the_developer_budget"],
         execution="STAGE_FAILURE_TYPED", code="INVALID_CREDENTIAL", owner="ENVIRONMENT", retry="NOT_RETRYABLE", budget=None, journal="FAILURE_OBSERVED(INVALID_CREDENTIAL); no budget charged (D-006)"),
    _row("FM2-CRED-3", "credentials", "provider outage distinct from an invalid credential", ["tests.v2.p1.test_routing:Credentials.test_CRED_4_provider_outage_is_distinct_from_invalid_credential"],
         execution="STAGE_FAILURE_TYPED", code="PROVIDER_UNAVAILABLE", owner="PROVIDER", retry="RETRYABLE", budget="PROVIDER", journal="FAILURE_OBSERVED(PROVIDER_UNAVAILABLE)"),
    # interruption
    _row("FM2-INT-1", "interruption", "controller stop attributed to the controller", [INT + "Interruption.test_INTERRUPT_SIG_1_a_controller_stop_is_attributed_to_the_controller"],
         execution="INTERRUPTED", terminal="INTERRUPTED", journal="the controller's signal ledger names the stop; no owner", residual="RELEASED_EMPTY"),
    _row("FM2-INT-2", "interruption", "a subject's signal exit never becomes an owner", [INT + "Interruption.test_INTERRUPT_SIG_2_a_subject_signal_exit_never_becomes_an_owner"],
         execution="EXECUTED", code="NON_CONTROLLER_SIGNAL", owner="INTEGRATION", retry="NOT_RETRYABLE", budget=None, journal="typed outcome table; no DEVELOPER or ENVIRONMENT owner invented"),
    _row("FM2-INT-3", "interruption", "closers distinguish not-started from outcome-unknown with no gap", [INT + "Interruption.test_INTERRUPT_SIG_3_closers_distinguish_not_started_from_outcome_unknown_and_leave_no_gap"],
         execution="INTERRUPTED", terminal="NOT_STARTED", journal="closers per story in story order at the last real time", residual="RELEASED_EMPTY"),
    _row("FM2-INT-4", "interruption", "an interrupted run disposes its scopes before it finishes and stays torn", [INT + "Interruption.test_an_interrupted_run_disposes_its_scopes_before_it_finishes_and_stays_torn"],
         execution="INTERRUPTED", terminal="TORN", journal="RUN_INTERRUPTED; run/end without CLEAN", residual="RELEASED_EMPTY"),
    _row("FM2-INT-5", "interruption", "a second interrupt during disposal abandons", [INT + "Interruption.test_a_second_interrupt_during_disposal_abandons_and_says_so",
                                                                                      INT + "Interruption.test_an_interrupt_during_disposal_only_asks_for_abandonment"],
         execution="INTERRUPTED", terminal="ABANDONED", journal="RUN_INTERRUPTED twice; abandonment names every remaining resource", residual="ABANDONED_NAMED"),
    _row("FM2-INT-6", "interruption", "real SIGINT mid-story", [INT + "RealSignals.test_SIGINT_mid_story_is_an_interruption_with_no_gap_and_nothing_left_running"],
         execution="INTERRUPTED", terminal="TORN", journal="interruption event closes the story; no gap", residual="OS_ASSERTED_GONE", platforms=("linux", "darwin")),
    _row("FM2-INT-7", "interruption", "real SIGKILL mid-story, repair closes the journal", [INT + "RealSignals.test_SIGKILL_mid_story_leaves_a_journal_that_repair_closes_and_a_tool_that_does_not_survive"],
         execution="INTERRUPTED", terminal="TORN", journal="repair appends synthetic closers at the last real time", residual="OS_ASSERTED_GONE", platforms=("linux", "darwin")),
    _row("FM2-INT-8", "interruption", "repair is idempotent, byte-identical, and refuses what it cannot extend", [INT + "Repair.test_repair_is_idempotent_and_byte_identical", INT + "Repair.test_repair_refuses_what_it_cannot_extend",
                                                                                                                  INT + "Repair.test_repair_journal_replaces_durably_or_leaves_the_journal_as_it_was"],
         execution="REFUSED", terminal="TORN", journal="durable replace or unchanged; never a partial rewrite"),
    _row("FM2-INT-9", "interruption", "controller stop of a probe is an interruption with no result", [SP + "AfterDispatch.test_SIG_PROBE_2_a_controller_stop_is_an_interruption_with_no_result"],
         execution="INTERRUPTED", journal="no PROBE_EVALUATED verdict", residual="RELEASED_EMPTY"),
    # writer close / CLEAN / lease
    _row("FM2-WRC-1", "writer_close_failure", "a journal writer that fails to close", [RS + "test_RUN_3_a_writer_that_fails_to_close_leaves_the_sentinel_open_and_the_lease_still_released_last"],
         execution="REFUSED", terminal="TORN", journal="sentinel left open; lease released last", residual="RESIDUAL_NAMED"),
    _row("FM2-CLEAN-1", "clean_failure", "CLEAN cannot be recorded", [RS + "test_RUN_4_a_clean_that_cannot_be_recorded_leaves_the_sentinel_open"],
         execution="REFUSED", terminal="TORN", journal="run/end durable, CLEAN absent", residual="RESIDUAL_NAMED"),
    _row("FM2-CLEAN-2", "clean_failure", "crash after a durable run/end before CLEAN (RUN-1)", [RS + "test_RUN_1_a_process_killed_after_a_durable_run_end_and_before_CLEAN_is_torn"],
         execution="INTERRUPTED", terminal="TORN", journal="RUN_END present, CLEAN absent -> TORN (conservative)", residual="RESIDUAL_NAMED"),
    _row("FM2-LEASE-1", "lease_conflict", "a second run while the first holds its lease (RUN-2)", [RS + "test_RUN_2_a_held_lease_blocks_a_second_run_even_with_run_end_written"],
         execution="REFUSED", terminal="n/a", journal="the second run writes nothing", residual="NONE"),
    _row("FM2-LEASE-2", "lease_conflict", "the lease is held before any state read and released last on a failed begin", [RS + "test_the_lease_is_held_before_any_state_read_and_a_failed_begin_still_releases_it_last"],
         execution="REFUSED", journal="no state read before the lease", residual="RELEASED_EMPTY"),
    # disposal
    _row("FM2-DISP-1", "disposal_failure", "a failing first disposer does not stop the rest", [SS + "test_SCOPE_2_a_failing_first_disposer_does_not_stop_the_rest_and_stays_recorded"],
         execution="REFUSED", terminal="DISPOSING", journal="the failure stays recorded; every other resource released", residual="RESIDUAL_NAMED"),
    _row("FM2-DISP-2", "disposal_failure", "a hanging release is residual at its bound", [SS + "test_a_hanging_release_is_residual_at_its_bound_and_disposal_goes_on"],
         execution="REFUSED", terminal="DISPOSING", journal="residual named at the bound", residual="RESIDUAL_NAMED"),
    _row("FM2-DISP-3", "disposal_failure", "abandonment names every remaining resource", [SS + "test_abandonment_names_every_remaining_resource_residual"],
         execution="INTERRUPTED", terminal="ABANDONED", journal="every remaining resource named", residual="ABANDONED_NAMED"),
    _row("FM2-DISP-4", "disposal_failure", "a broken journal during disposal still releases everything", [SS + "test_a_broken_journal_during_disposal_still_releases_everything"],
         execution="REFUSED", terminal="DISPOSING", journal="journal broken; releases still run", residual="RELEASED_EMPTY"),
    _row("FM2-DISP-5", "disposal_failure", "a range that will not empty is RESIDUAL, never a silent success", [PR + "Range.test_a_range_that_will_not_empty_is_residual_never_a_silent_success_and_blocks_by_default",
                                                                                                                 SS + "test_a_range_not_proved_empty_makes_what_it_could_write_to_residual_and_nothing_else"],
         execution="REFUSED", journal="RESIDUAL named; nothing it could write to is trusted", residual="RESIDUAL_NAMED"),
    _row("FM2-DISP-6", "disposal_failure", "an escaped child is detected, reported, never signalled", [PR + "Range.test_an_escaped_child_is_detected_reported_and_never_signalled"],
         execution="REFUSED", journal="escapee reported by pid; no signal without ownership proof", residual="NEVER_SIGNALLED", platforms=("linux", "darwin")),
    _row("FM2-DISP-7", "disposal_failure", "D-024: the range is proved empty before the worktree is removed", [PR + "Range.test_D_024_red_before_a_writing_grandchild_outlives_a_cleanup_that_trusts_the_direct_child",
                                                                                                                PR + "Range.test_D_024_green_after_the_range_is_proved_empty_before_the_worktree_is_removed"],
         execution="EXECUTED", journal="measured empty, then removed", residual="OS_ASSERTED_GONE"),
    _row("FM2-DISP-8", "disposal_failure", "a directory release measures that it is gone", ["tests.v2.p4.test_story_scope:Directories.test_a_directory_release_removes_it_and_measures_that_it_is_gone"],
         execution="EXECUTED", journal="release recorded after the measurement", residual="OS_ASSERTED_GONE"),
    _row("FM2-DISP-9", "disposal_failure", "a successful shutdown is refused while a story is open", [RS + "test_P3_RESIDUAL_DISPOSAL_ORDER_a_successful_shutdown_is_refused_while_a_story_is_open"],
         execution="REFUSED", terminal="TORN", journal="CLEAN refused", residual="RESIDUAL_NAMED"),
    # signal provenance
    _row("FM2-SIG-1", "signal_provenance", "a signal before dispatch is still UNRUNNABLE / ENVIRONMENT", [SP + "BeforeDispatch.test_SIG_PROBE_1_a_signal_before_dispatch_is_still_unrunnable_environment"],
         execution="UNRUNNABLE", code="PROBE_UNRUNNABLE", owner="ENVIRONMENT", retry="RETRYABLE", budget="ENVIRONMENT", journal="PROBE_EVALUATED UNRUNNABLE", residual="RELEASED_EMPTY"),
    _row("FM2-SIG-2", "signal_provenance", "a subject that signals itself after dispatch", [SP + "AfterDispatch.test_SIG_PROBE_4_a_subject_that_signals_itself_is_executed_and_indeterminate",
                                                                                            SP + "AfterDispatch.test_SIG_PROBE_10_the_ledger_decides_not_the_signal_number"],
         execution="EXECUTED", code="NON_CONTROLLER_SIGNAL", owner="INTEGRATION", retry="NOT_RETRYABLE", budget=None, journal="EXECUTED + INDETERMINATE(NON_CONTROLLER_SIGNAL); the ledger decides", residual="RELEASED_EMPTY"),
    _row("FM2-SIG-3", "signal_provenance", "a subject that aborts", ["tests.v2.p2.test_signal_provenance_abort:Abort.test_SIG_PROBE_3_a_subject_that_aborts_is_executed_and_indeterminate"],
         execution="EXECUTED", code="NON_CONTROLLER_SIGNAL", owner="INTEGRATION", retry="NOT_RETRYABLE", budget=None, journal="EXECUTED + INDETERMINATE(NON_CONTROLLER_SIGNAL)", residual="RELEASED_EMPTY", platforms=("linux",)),
    _row("FM2-SIG-4", "signal_provenance", "routing: no budget at the candidate, INTEGRATION after merge, never retried", [SP + "Routing.test_SIG_PROBE_5_at_the_candidate_it_charges_no_budget",
                                                                                                                             SP + "Routing.test_SIG_PROBE_7_after_merge_it_is_integration_and_never_retried",
                                                                                                                             SP + "Routing.test_the_taxonomy_fixes_owner_and_retryability_and_the_journal_holds_them",
                                                                                                                             SP + "Budgets.test_a_non_controller_signal_failure_is_not_retryable_from_the_journal"],
         execution="EXECUTED", code="NON_CONTROLLER_SIGNAL", owner="INTEGRATION", retry="NOT_RETRYABLE", budget=None, journal="FAILURE_OBSERVED carries owner+retryable from the taxonomy"),
    _row("FM2-SIG-5", "signal_provenance", "a job stop is the controller's only with its stop in the ledger", [PR + "Backends.test_a_job_stop_is_recognised_only_with_its_stop_in_the_ledger",
                                                                                                             INT + "Interruption.test_a_job_stop_is_the_controllers_only_with_its_stop_in_the_ledger"],
         execution="INTERRUPTED", journal="ledger entry TerminateJobObject / signal", residual="RELEASED_EMPTY"),
    _row("FM2-SIG-6", "signal_provenance", "F5 / F2 conformance: restoring signal-to-UNRUNNABLE or routing to DEVELOPER fails the freeze", [SP + "Conformance.test_SIG_PROBE_8_restoring_signal_after_dispatch_to_unrunnable_fails_F5",
                                                                                                                                              SP + "Conformance.test_SIG_PROBE_9_routing_the_reason_to_developer_or_environment_fails_F2"],
         execution="REFUSED", journal="conformance FAIL on the mutated reading"),
    # merge conflict / post-merge / verifier
    _row("FM2-MERGE-1", "merge_conflict", "conflicting change on the trunk", [ORCH + "test_ORCH_8_and_SCHEMA_3_a_merge_conflict_is_MERGE_CONFLICT_INTEGRATION_with_zero_developer_charge",
                                                                              ST + "Workspace.test_the_merger_types_merged_conflict_and_up_to_date_from_git", ST + "MergeStage.test_the_merge_outcome_is_typed_from_the_merger_or_flattened"],
         execution="STAGE_FAILURE_TYPED", code="MERGE_CONFLICT", owner="INTEGRATION", retry="NOT_RETRYABLE", budget=None, terminal="ENDED/ROLLBACK",
         journal="FAILURE_OBSERVED(MERGE_CONFLICT) from the typed merge outcome, never stderr; zero developer charge", residual="RELEASED_EMPTY"),
    _row("FM2-PM-1", "post_merge_regression", "a prior PRESERVE obligation regresses after merge", [ORCH + "test_ORCH_9_and_10_a_post_merge_regression_of_a_prior_PRESERVE_obligation_is_INTEGRATION_and_rolled_back",
                                                                                                    ST + "MergeStage.test_reprove_covers_the_story_then_the_affected_PRESERVE_and_stops_at_the_first_failure"],
         execution="EXECUTED", code="POST_MERGE_REGRESSION", owner="INTEGRATION", retry="NOT_RETRYABLE", budget=None, terminal="ENDED/ROLLBACK",
         journal="PROOF_VERIFIED at POST_MERGE UNSATISFIED; FAILURE_OBSERVED(POST_MERGE_REGRESSION); merge reverted", residual="RELEASED_EMPTY"),
    _row("FM2-PM-2", "post_merge_regression", "the merged revision cannot be reached: the merge is reverted", [ORCH + "test_ORCH_SCHEMA_10c_a_checkout_that_cannot_reach_the_merged_revision_reverts_the_merge"],
         execution="REFUSED", code="RESOURCE_ACQUISITION_FAILED", owner="ENVIRONMENT", retry="RETRYABLE", budget="ENVIRONMENT", terminal="ENDED/ROLLBACK", journal="merge reverted at the tip", residual="RELEASED_EMPTY"),
    _row("FM2-VER-1", "verifier_disagreement", "implementer and verifier disagree", [ORCH + "test_ORCH_5_and_SCHEMA_1_a_verifier_disagreement_is_VERIFIER_DISAGREEMENT_INTEGRATION_and_stops",
                                                                                     ST + "ProofStage.test_a_disagreement_is_VERIFIER_DISAGREEMENT_and_a_mismatch_is_PROBE_MISMATCH"],
         execution="EXECUTED", code="VERIFIER_DISAGREEMENT", owner="INTEGRATION", retry="NOT_RETRYABLE", budget=None, terminal="ENDED/ROLLBACK",
         journal="two cited sealed records, no agreement; never rerun until agreement", residual="RELEASED_EMPTY"),
    _row("FM2-VER-2", "verifier_disagreement", "probe mismatch between the two parties", [ORCH + "test_ORCH_SCHEMA_2_a_probe_mismatch_is_PROBE_MISMATCH_and_never_a_proof",
                                                                                          ST + "VerifiedPayload.test_agreement_is_result_equality_and_the_verdict_only_then"],
         execution="EXECUTED", code="PROBE_MISMATCH", owner="INTEGRATION", retry="NOT_RETRYABLE", budget=None, terminal="ENDED/ROLLBACK", journal="no PROOF_VERIFIED; FAILURE_OBSERVED(PROBE_MISMATCH)", residual="RELEASED_EMPTY"),
    # review
    _row("FM2-REV-1", "reviewer_security_environment", "review request budget and corroborated finding", [ORCH + "test_ORCH_SCHEMA_7_a_review_request_charges_the_REVIEW_budget_and_blocks_only_with_corroboration",
                                                                                                          ORCH + "test_ORCH_SCHEMA_7b_a_corroborated_review_finding_is_REVIEW_FINDING_owned_by_REVIEW"],
         execution="EXECUTED", code="REVIEW_FINDING", owner="REVIEW", retry="RETRYABLE", budget="REVIEW", terminal="ENDED/RETRY", journal="PROVIDER_REQUEST(REVIEW); GATE_CHECK rows; FAILURE_OBSERVED(REVIEW_FINDING) only corroborated", residual="RELEASED_EMPTY"),
    # resource acquisition
    _row("FM2-RES-1", "resource_acquisition", "a StoryScope resource cannot be acquired", [ORCH + "test_ORCH_SCHEMA_10_a_resource_that_cannot_be_acquired_is_RESOURCE_ACQUISITION_FAILED",
                                                                                           ORCH + "test_ORCH_SCHEMA_10b_a_checkout_that_cannot_reach_the_candidate_is_RESOURCE_ACQUISITION_FAILED"],
         execution="REFUSED", code="RESOURCE_ACQUISITION_FAILED", owner="ENVIRONMENT", retry="RETRYABLE", budget="ENVIRONMENT", terminal="ENDED/RETRY", journal="FAILURE_OBSERVED(RESOURCE_ACQUISITION_FAILED); never from stderr text", residual="RELEASED_EMPTY"),
    _row("FM2-RES-2", "resource_acquisition", "acquisition during or after disposal is refused and the offer released", [SS + "test_SCOPE_1_acquisition_during_or_after_disposal_is_refused_and_the_offer_released",
                                                                                                                         SS + "test_a_refused_journal_write_on_acquisition_releases_the_resource"],
         execution="REFUSED", terminal="DISPOSING", journal="no acquisition event", residual="RELEASED_EMPTY"),
    _row("FM2-RES-3", "resource_acquisition", "a target that cannot start leaves nothing running", [PR + "Range.test_start_failures_are_refused_and_leave_nothing_running"],
         execution="REFUSED", journal="RangeError SPAWN_FAILED", residual="OS_ASSERTED_GONE"),
    # plan / unknown
    _row("FM2-PLAN-1", "plan_contradiction", "the parent contradicts the plan's own record", ["tests.v2.p2.test_story_admission:Table.test_PLAN_OWNER_1_a_plan_contradiction_always_carries_PLAN",
                                                                                            "tests.v2.p2.test_story_admission:Table.test_PLAN_OWNER_2_a_plan_contradiction_consumes_no_retry_budget"],
         execution="EXECUTED", code="PLAN_CONTRADICTION", owner="PLAN", retry="NOT_RETRYABLE", budget=None, terminal="BEGIN", journal="STORY_ADMITTED blocked; no developer call"),
    _row("FM2-UNK-1", "unknown_flattening", "a non-AISEF error flattens to UNKNOWN and keeps the original as data", [ST + "RunnerHelpers.test_fail_carries_the_flattened_original_only_for_UNKNOWN",
                                                                                                                    "tests.v2.test_v2_005:Taxonomy.test_no_call_site_supplies_owner_or_retryability_and_no_prose_becomes_a_code"],
         execution="STAGE_FAILURE_TYPED", code="UNKNOWN", owner="INTEGRATION", retry="NOT_RETRYABLE", budget=None, journal="FAILURE_OBSERVED(UNKNOWN, original as data); never DEVELOPER"),
]
RACE = {"RACE-1": "tests.v2.test_v2_006:Race.test_RACE_1_a_READY_written_before_exit_is_observed_however_late_the_pump",
        "RACE-2": "tests.v2.test_v2_006:Race.test_RACE_2_READY_DISPATCHED_RESULT_then_immediate_exit_is_the_complete_result",
        "RACE-3": "tests.v2.test_v2_006:Race.test_RACE_3_the_exit_notice_before_the_pump_is_scheduled_gives_the_normal_result",
        "RACE-4": "tests.v2.test_v2_006:Race.test_RACE_4_one_party_late_the_other_normal_gives_identical_records",
        "RACE-4-story": "tests.v2.test_v2_006:StoryRace.test_RACE_4_a_story_with_one_party_late_on_every_proof_commits_with_agreement",
        "RACE-5": "tests.v2.test_v2_006:TrueEnd.test_RACE_5_a_harness_that_emits_nothing_and_exits_0_did_not_start_after_the_stream_closed",
        "RACE-6": "tests.v2.test_v2_006:TrueEnd.test_RACE_6_a_target_that_dies_before_READY_keeps_its_typed_outcome",
        "RACE-7": "tests.v2.test_v2_006:TrueEnd.test_RACE_7_a_partial_READY_then_exit_is_no_READY_never_a_guess",
        "RACE-8": "tests.v2.test_v2_006:AnchorHoldsNoWriter.test_RACE_8_the_output_stream_ends_when_the_target_ends_while_the_anchor_lives",
        "RACE-8-descendant": "tests.v2.test_v2_006:AnchorHoldsNoWriter.test_a_descendant_holding_the_writer_keeps_the_stream_open_until_it_ends",
        "RACE-9": "tests.v2.test_v2_006:TrueEnd.test_RACE_9_every_line_before_the_end_is_read_before_STREAM_CLOSED",
        "RACE-10": "tests.v2.test_v2_006_repeat:Repeated.test_RACE_10_every_ordering_repeated_gives_the_normal_record",
        "WAIT-CONTRACT": "tests.v2.test_v2_006:WaitContract.test_a_timed_out_wait_returns_only_once_the_monotonic_clock_has_passed_its_deadline"}
STRESS = {"A protocol lines before the exit notice": ["RACE-2", "RACE-3", "RACE-9"],
          "B exit notice before the scheduler delivers written lines": ["RACE-1", "RACE-4", "RACE-4-story", "RACE-10"],
          "C stream closure with no RESULT": ["RACE-5", "tests.v2.test_v2_006:NextAndPump.test_after_DISPATCHED_a_closed_stream_with_the_process_running_is_the_window_expiring",
                                              "tests.v2.test_v2_006:NextAndPump.test_a_stream_closed_while_the_process_runs_is_a_harness_timeout_at_the_watchdog"],
          "D READY absent": ["RACE-5", "RACE-7", "tests.v2.test_v2_006:NextAndPump.test_next_returns_only_complete_marked_lines_of_this_nonce"],
          "E target exits immediately after READY": ["harness:E"],
          "F anchor main exits early": ["harness:F", "tests.v2.p4.test_process_range:Anchor.test_an_anchor_whose_report_nobody_reads_ends_itself_and_its_group",
                                        "tests.v2.p4.test_process_range:Range.test_wait_says_none_at_once_when_the_anchor_is_gone_and_keeps_saying_it"],
          "G controller disappears before STARTED / ownership boundary": ["harness:G", "tests.v2.p4.test_process_range:Range.test_PROC_OWN_1_a_controller_that_dies_leaves_no_owned_process_alive",
                                                                          "tests.v2.p4.test_process_range:Range.test_a_controller_that_returns_without_disposing_exits_and_its_range_goes_with_it"]}


def _fault_E() -> dict:
    """A real harness that writes READY and exits 0 at once: before DISPATCHED, typed UNRUNNABLE — never a verdict."""
    from aisef2.arch.enums import ProbeExecutionStatus
    from aisef2.probe.protocol import RevisionRef, run_probe
    from aisef2.product.outcome import Unrunnable
    from tests.v2.p2.test_python_callable import PRODUCT, SHA, P, checkout, env, spec
    from tests.v2.test_v2_006 import harness
    src = ("import json, sys\nreq = json.load(open(sys.argv[1], encoding='utf-8'))\n"
           "sys.stdout.write('\\n%s READY %s \\n' % (req['mark'], req['nonce']))\nsys.stdout.flush()\n")
    at = RevisionRef(SHA, checkout(PRODUCT))
    with harness(src):
        result = run_probe(P, spec("app.calc:add"), at, env()).result
    return {"status": result.status.value, "detail": getattr(result, "detail", None), "typed_unrunnable": isinstance(result, Unrunnable),
            "ok": result.status is ProbeExecutionStatus.UNRUNNABLE and isinstance(result, Unrunnable) and "no DISPATCHED" in (getattr(result, "detail", "") or "")}


def _fault_H() -> dict:
    """P7-FINDING-001's deterministic reproducer, live: the old semantic candidate's probe (read from git) observes the
    stale bytecode of a constructed checkout, this tree's probe observes the source, the external cache alone
    carries that and -B alone does not (validation/qualification/p7_finding_001_reproducer.py)."""
    from validation.qualification import p7_finding_001_reproducer as rp
    record = rp.measure()
    return {"verdicts": record["verdicts"], "old_candidate": record["old_candidate"], "corrected_probe_digest": record["corrected_candidate"]["probe_digest"],
            "checkout_byte_identical_after_the_proof": record["corrected_candidate"]["checkout_byte_identical_after_the_proof"],
            "runs": {k: {"behavior_verdict": v["behavior_verdict"], "execution_status": v["execution_status"], "flags": v["harness_argv_flags"]} for k, v in record["runs"].items()},
            "ok": all(record["verdicts"].values()) and record["old_candidate"]["digest_is_the_one_the_candidate_declared"]}


def _fault_F() -> dict:
    """The anchor's main is terminated before its normal path completes (SIGKILL / TerminateProcess) while the target
    runs. Expected: the closed report path is told apart from an elapsed window at once, and after release no owned
    target survives — asserted against the OS by pid, through the platform's own mechanism."""
    from aisef2.runtime.process_range import ProcessRange
    from tests.v2.p4.test_process_range import alive, gone
    r = ProcessRange("q3-anchor-terminated", [sys.executable, "-c", "import time; time.sleep(60)"]).start()
    target, anchor = r.target_pid, r._anchor.pid
    before = {"target_alive": alive(target), "anchor_alive": alive(anchor)}
    r._anchor.kill()
    t = time.monotonic()
    closed = r.wait(2.0)
    closed_elapsed = time.monotonic() - t
    release_error = None
    try:
        r.release()
    except Exception as e:  # noqa: BLE001 — a residual is a typed refusal; recorded, then asserted against the OS
        release_error = f"{type(e).__name__}: {e}"
    return {"target": target, "anchor": anchor, "before": before, "wait_after_anchor_death": {"returned": closed, "elapsed_s": round(closed_elapsed, 3),
            "closed_path_at_once": closed is None and closed_elapsed < 1.0}, "release_error": release_error, "ledger": r.ledger,
            "target_gone_os": gone(target), "anchor_gone_os": gone(anchor), "members_after": [p.pid for p in r.members()],
            "ok": before["target_alive"] and closed is None and closed_elapsed < 1.0 and gone(target) and gone(anchor) and not r.members()}


def _fault_G() -> dict:
    """POSIX: the controller is gone before STARTED — the anchor's report pipe is closed before it writes. Expected: the
    anchor ends by its watchdog (its group, target included); the target is asserted gone by the OS (a nonce in its
    command line, searched in the host table). Windows: the job holds the target; PROC_OWN_1 asserts it."""
    import cleanup_authority as ca
    from aisef2.runtime import process_range as pr
    if os.name != "posix":
        return {"outcome": C.NOT_APPLICABLE, "why": "Windows: no process group; the Job Object is the ownership mechanism (PROC_OWN_1)"}
    nonce = f"q3-nonce-{os.getpid()}-{int(time.time() * 1000)}"
    a = subprocess.Popen([sys.executable, "-P", str(pr.ANCHOR)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding="utf-8",
                         start_new_session=True)
    a.stdout.close()
    a.stdin.write(json.dumps({"argv": [sys.executable, "-c", f"import time; time.sleep(60)  # {nonce}"], "cwd": None, "env": None}) + "\nGO\n")
    a.stdin.flush()
    code = a.wait(30)
    deadline = time.monotonic() + 10
    survivors = [p.pid for p in ca.host_table().values() if nonce in p.command]
    while survivors and time.monotonic() < deadline:
        time.sleep(0.2)
        survivors = [p.pid for p in ca.host_table().values() if nonce in p.command]
    return {"anchor_exit": code, "anchor_ended_by_its_watchdog": code == -9, "target_survivors_in_host_table": survivors,
            "ok": code == -9 and not survivors}


def _wait_contract() -> dict:
    """§19: when ProcessRange.wait reports a timeout (None with the target running), the monotonic deadline has elapsed."""
    from aisef2.runtime.process_range import ProcessRange
    r = ProcessRange("q3-wait-contract", [sys.executable, "-c", "import time; time.sleep(60)"]).start()
    samples, violations = [], []
    try:
        for rep in range(5):
            for timeout in (0.0, 0.02, 0.1, 0.25):
                deadline = time.monotonic() + timeout
                got = r.wait(timeout)
                slack_ms = (time.monotonic() - deadline) * 1000
                samples.append({"rep": rep, "timeout_s": timeout, "returned": got, "slack_ms": round(slack_ms, 3)})
                if got is not None or slack_ms < 0:
                    violations.append(samples[-1])
    finally:
        r.release()
    return {"samples": len(samples), "violations": violations, "min_slack_ms": min(s["slack_ms"] for s in samples),
            "max_slack_ms": max(s["slack_ms"] for s in samples), "ok": not violations}


def _watchdog_structure() -> dict:
    src = (C.ROOT / "aisef2/runtime/range_anchor.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    entry = [n for n in tree.body if isinstance(n, ast.If) and ast.unparse(n.test) == "__name__ == '__main__'"]
    main = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"), None)
    entry_ok = len(entry) == 1 and ast.unparse(entry[0]).splitlines()[1:] == ["    try:", "        main()", "    finally:", "        _die()"]
    main_has_no_eof_branch = main is not None and "if not line:" not in ast.unparse(main)
    return {"entry_is_try_main_finally_die": entry_ok, "main_has_no_watchdog_of_its_own": main_has_no_eof_branch,
            "release_output_called_in_main": main is not None and "_release_output()" in ast.unparse(main),
            "ok": entry_ok and main_has_no_eof_branch}


def _evidence_status() -> list[str]:
    return [ln for ln in C.git("status", "--porcelain", "--", "closure-evidence").splitlines() if not ln[3:].startswith(C.OUT_REL)]


FAULT_MATRIX += BYTECODE_FAMILY

CLIP, CLII, FAT, PEF, PEB, PCB = ("tests.v2.test_c2_cli_protocol:", "tests.v2.test_c2_cli_invocation:", "tests.v2.test_c2_file_artifact:",
                                 "tests.v2.test_probe_process_effect:", "tests.v2.test_probe_process_effect_bytecode:Bytecode.",
                                 "tests.v2.test_python_callable_v2_bytecode:BytecodeV2.")
_UNRUN = dict(execution="UNRUNNABLE", code="PROBE_UNRUNNABLE", owner="ENVIRONMENT", retry="RETRYABLE", budget="ENVIRONMENT",
              residual="RELEASED_EMPTY")
_INVALID = dict(execution="INVALID_SPEC", code="PROBE_INVALID_SPEC", owner="INTEGRATION", retry="NOT_RETRYABLE", budget=None)
_POSIX = ("linux", "darwin")
CYCLE2_FAMILY = [
    # cli_invocation — the harness (the probe's own machinery): every one a harness failure, never a verdict
    _row("FM2-CLI-HARNESS-1", "cli_harness", "interpreter absent", [CLIP + "FaultHarness.test_FM2_CLI_HARNESS_1_interpreter_absent"],
         journal="probe/evaluated UNRUNNABLE with no verdict; PROBE_UNRUNNABLE from the taxonomy", **_UNRUN),
    _row("FM2-CLI-HARNESS-2", "cli_harness", "evaluation directory uncreatable", [CLIP + "FaultHarness.test_FM2_CLI_HARNESS_2_evaluation_directory_uncreatable"],
         journal="probe/evaluated UNRUNNABLE; nothing created", **_UNRUN),
    _row("FM2-CLI-HARNESS-3", "cli_harness", "evaluation directory inside the checkout", [CLIP + "FaultHarness.test_FM2_CLI_HARNESS_3_evaluation_directory_inside_the_checkout_refused"],
         journal="refused before any launch; probe/evaluated UNRUNNABLE", **_UNRUN),
    _row("FM2-CLI-HARNESS-4", "cli_harness", "protocol file unwritable; workspace that cannot be laid out",
         [CLII + "FaultHarness.test_FM2_CLI_HARNESS_4_protocol_file_unwritable", CLIP + "FaultHarness.test_FM2_CLI_HARNESS_4b_workspace_that_cannot_be_laid_out"],
         journal="the harness did not start: probe/evaluated UNRUNNABLE", **_UNRUN),
    # cli_invocation — the subject
    _row("FM2-CLI-SUBJECT-1", "cli_subject", "a subject that never exits", [CLII + "FaultSubject.test_FM2_CLI_SUBJECT_1_a_subject_that_never_exits_gets_the_deadline_verdict_of_its_class"],
         execution="EXECUTED", journal="the subject deadline verdict of its class; never ENVIRONMENT (TIME-5)"),
    _row("FM2-CLI-SUBJECT-2", "cli_subject", "a non-controller signal ends the subject", [CLII + "FaultSubject.test_FM2_CLI_SUBJECT_2_a_non_controller_signal_is_executed_and_indeterminate"],
         execution="EXECUTED", code="NON_CONTROLLER_SIGNAL", owner="INTEGRATION", retry="NOT_RETRYABLE", budget=None,
         journal="EXECUTED indeterminate NON_CONTROLLER_SIGNAL; no ENVIRONMENT owner", platforms=_POSIX),
    _row("FM2-CLI-SUBJECT-3", "cli_subject", "a controller stop of the invocation", [CLII + "FaultSubject.test_FM2_CLI_SUBJECT_3_a_controller_stop_is_an_interruption_with_no_result",
                                                                                     CLIP + "FaultStream.test_C2_P2_FINDING_002_a_controller_stop_with_no_status_reported_is_an_interruption"],
         execution="INTERRUPTED", journal="the controller's signal ledger names the stop; no result; the range emptied", residual="RELEASED_EMPTY"),
    _row("FM2-CLI-SUBJECT-4", "cli_subject", "a stdout flood", [CLII + "FaultSubject.test_FM2_CLI_SUBJECT_4_a_stdout_flood_is_bounded"],
         execution="EXECUTED", journal="the captured stream capped and marked truncated; the exit still observed"),
    _row("FM2-CLI-SUBJECT-5", "cli_subject", "a forged protocol line on stdout, then a hard exit", [CLII + "FaultSubject.test_FM2_CLI_SUBJECT_5_a_forged_protocol_line_then_a_hard_exit_is_the_hard_exit"],
         execution="EXECUTED", journal="the forged line is captured subject bytes, never protocol; the hard exit is the observation"),
    _row("FM2-CLI-SUBJECT-6", "cli_subject", "nonzero exit shapes (SystemExit None / str / int, os._exit)", [CLII + "FaultSubject.test_FM2_CLI_SUBJECT_6_nonzero_exit_shapes"],
         execution="EXECUTED", journal="the exit code recorded verbatim beside the status"),
    # cli_invocation — the protocol channel
    _row("FM2-CLI-STREAM-1", "cli_stream", "exit before READY", [CLII + "FaultStream.test_FM2_CLI_STREAM_1_exit_before_READY",
                                                                 CLIP + "FaultStream.test_FM2_CLI_STREAM_1b_exit_before_READY_or_DISPATCHED_on_the_range"],
         journal="harness failure: probe/evaluated UNRUNNABLE", **_UNRUN),
    _row("FM2-CLI-STREAM-2", "cli_stream", "exit after DISPATCHED without RESULT", [CLIP + "FaultStream.test_FM2_CLI_STREAM_2_exit_after_DISPATCHED_without_RESULT",
                                                                                    CLII + "FaultStream.test_FM2_CLI_STREAM_2b_a_real_hard_exit_after_DISPATCHED"],
         execution="EXECUTED", journal="the subject's hard exit is the observation, decided by its class"),
    _row("FM2-CLI-STREAM-3", "cli_stream", "RESULT then late bytes on stdout", [CLII + "FaultStream.test_FM2_CLI_STREAM_3_RESULT_then_late_bytes_on_stdout"],
         execution="EXECUTED", journal="the bytes captured when the invocation returned; nothing after RESULT counts"),
    _row("FM2-CLI-STREAM-4", "cli_stream", "the subject closing or redirecting its descriptors", [CLII + "FaultStream.test_FM2_CLI_STREAM_4_the_subject_closing_or_redirecting_its_descriptors"],
         execution="EXECUTED", journal="the channel is not the subject's stdout: the result is unchanged"),
    _row("FM2-CLI-STREAM-5", "cli_stream", "marker file absent at exit or never opened (DESIGN-CHECK-1)",
         [CLII + "FaultStream.test_FM2_CLI_STREAM_5_marker_file_absent_at_exit", CLIP + "FaultStream.test_FM2_CLI_STREAM_5b_marker_file_never_opened"],
         journal="harness failure: probe/evaluated UNRUNNABLE", **_UNRUN),
    _row("FM2-CLI-DISPOSE-1", "cli_stream", "the evaluation directory disposed through a passing sharing violation (C2-P2-FINDING-003)",
         [CLIP + "FaultStream.test_C2_P2_FINDING_003_the_evaluation_directory_is_disposed_through_a_passing_sharing_violation"],
         execution="EXECUTED", journal="bounded retry on a sharing violation; any other failure raised at once"),
    # file_artifact
    _row("FM2-FILE-1", "file_artifact", "git absent", [FAT + "Refusals.test_FM2_FILE_1_a_probe_constructed_without_git_refuses_every_observation"],
         journal="every observation a harness failure: probe/evaluated UNRUNNABLE", **_UNRUN),
    _row("FM2-FILE-2", "file_artifact", "a revision the repository does not hold", [FAT + "ObjectStoreRule.test_FM2_FILE_2_a_revision_the_repository_does_not_hold_is_a_harness_failure_never_absence"],
         journal="harness failure, never subject absence: probe/evaluated UNRUNNABLE", **_UNRUN),
    _row("FM2-FILE-3", "file_artifact", "binary file under a text grep; a file that is not UTF-8",
         [FAT + "ObjectStoreRule.test_FM2_FILE_3_a_binary_file_under_a_text_grep_is_skipped_and_recorded",
          FAT + "ObjectStoreRule.test_FM2_FILE_3_a_file_that_is_not_utf8_leaves_the_count_unestablished"],
         execution="EXECUTED", journal="binary skipped and recorded; an undecodable file leaves the count unestablished (refuted, the file named)"),
    _row("FM2-FILE-4", "file_artifact", "regex pattern over the cap", [FAT + "Refusals.test_FM2_FILE_4_a_pattern_over_the_cap_is_a_harness_failure"],
         journal="harness failure, never a verdict: probe/evaluated UNRUNNABLE", **_UNRUN),
    _row("FM2-FILE-5", "file_artifact", "case-collision paths", [FAT + "ObjectStoreRule.test_FM2_FILE_5_case_collision_paths_are_read_exactly_from_the_tree"],
         execution="EXECUTED", journal="both entries read exactly from the tree; a third spelling absent"),
    _row("FM2-FILE-6", "file_artifact", "symlink entry; tree escape", [FAT + "ObjectStoreRule.test_FA_ADV_1_a_symlink_entry_is_refused_for_content_and_grep_and_never_followed",
                                                                       FAT + "Refusals.test_FA_ADV_2_a_tree_escape_is_refused"],
         execution="EXECUTED", journal="a link is never followed; an escaping locator is refused before any read"),
    # process_effect
    _row("FM2-EFFECT-1", "process_effect", "unknown step kind", [PEF + "FaultEffect.test_FM2_EFFECT_1_an_unknown_step_kind_is_INVALID_SPEC_at_admission_before_anything_runs"],
         journal="PROBE_INVALID_SPEC at admission; nothing runs", **_INVALID),
    _row("FM2-EFFECT-2", "process_effect", "fault restoration failure", [PEF + "FaultEffect.test_FM2_EFFECT_2_a_fault_restoration_failure_is_HARNESS_FAILED"],
         journal="harness failure, never a verdict: probe/evaluated UNRUNNABLE", **_UNRUN),
    _row("FM2-EFFECT-3", "process_effect", "exception in a non-final step", [PEF + "FaultEffect.test_FM2_EFFECT_3_an_exception_in_a_non_final_step_refutes_with_the_step_named"],
         execution="EXECUTED", journal="refuted with the step named, for every class"),
    _row("FM2-EFFECT-4", "process_effect", "a subprocess step that leaves a process", [PEF + "FaultEffect.test_FM2_EFFECT_4_a_subprocess_step_that_leaves_a_process_is_the_range_residual_never_the_probe_s"],
         execution="EXECUTED", journal="the range's residual, stopped and recorded by its release; the observation unchanged",
         residual="RESIDUAL_NAMED", platforms=_POSIX),
    _row("FM2-EFFECT-5", "process_effect", "a second construct without declaration", [PEF + "FaultEffect.test_FM2_EFFECT_5_a_second_construct_without_declaration_is_refused"],
         journal="refused at admission; nothing runs", **_INVALID),
    _row("FM2-EFFECT-6", "process_effect", "a fault the subject swallows", [PEF + "FaultEffect.test_FM2_EFFECT_6_a_fault_the_subject_swallows_is_observed_by_the_file_observable"],
         execution="EXECUTED", journal="observed by the file observable (equals_before)"),
    _row("FM2-EFFECT-7", "process_effect", "harness crashes before opening the marker file", [PEF + "FaultEffect.test_FM2_EFFECT_7_a_harness_that_crashes_before_opening_the_marker_file_is_HARNESS_FAILED"],
         journal="harness failure: probe/evaluated UNRUNNABLE", **_UNRUN),
    _row("FM2-EFFECT-8", "process_effect", "a protocol line forged on stdout", [PEF + "FaultEffect.test_FM2_EFFECT_8_a_protocol_line_forged_on_stdout_is_captured_bytes_never_protocol"],
         execution="EXECUTED", journal="captured bytes, never protocol"),
    _row("FM2-EFFECT-9", "process_effect", "the process ending during a step", [PEF + "FaultEffect.test_FM2_EFFECT_9_the_process_ending_during_a_step_refutes_with_that_step"],
         execution="EXECUTED", journal="refuted with that step"),
    _row("FM2-EFFECT-10", "process_effect", "a controller stop after DISPATCHED", [PEF + "FaultEffect.test_FM2_EFFECT_10_a_controller_stop_after_DISPATCHED_is_an_interruption_with_no_result"],
         execution="INTERRUPTED", journal="an interruption, no result", residual="RELEASED_EMPTY"),
    # the bytecode family under every new probe (CYCLE2-QUALIFICATION-PLAN §4 FM2-PYC-2): the checkout's bytecode is
    # never the subject, and the probe writes none into it
    _row("FM2-PYC-CLI", "bytecode_cycle2", "cli_invocation: stale in-tree bytecode, no bytecode written, fresh cache, mechanism load-bearing",
         [CLII + "Bytecode.test_FM2_PYC_CLI_1_in_tree_stale_bytecode_with_a_matching_header_is_never_the_subject",
          CLII + "Bytecode.test_FM2_PYC_CLI_2_the_probe_writes_no_bytecode_into_the_checkout",
          CLII + "Bytecode.test_FM2_PYC_CLI_3_the_cache_is_fresh_empty_outside_the_checkout_and_distinct_per_evaluation",
          CLII + "Bytecode.test_FM2_PYC_CLI_4_without_the_external_cache_the_stale_bytecode_decides_the_reproducer_detects_the_defect"],
         execution="EXECUTED", journal="the source's verdict at every checkout; the checkout unwritten"),
    _row("FM2-PYC-EFFECT", "bytecode_cycle2", "process_effect: stale in-tree bytecode (in the subject and in a subprocess step), two checkouts, cache",
         [PEB + "test_FM2_PYC_EFFECT_1_in_tree_stale_bytecode_with_a_matching_header_is_never_the_subject",
          PEB + "test_FM2_PYC_EFFECT_2_a_subprocess_step_observes_the_source_too",
          PEB + "test_FM2_PYC_EFFECT_3_the_probe_writes_no_bytecode_into_the_checkout",
          PEB + "test_FM2_PYC_EFFECT_4_the_cache_is_fresh_empty_outside_the_checkout_and_distinct_per_evaluation",
          PEB + "test_FM2_PYC_EFFECT_5_without_the_external_cache_the_stale_bytecode_decides_the_reproducer_detects_it",
          PEF + "Bytecode.test_FM2_PYC_2_two_checkouts_of_the_same_content_with_different_dates_observe_one_verdict"],
         execution="EXECUTED", journal="the source's verdict at every checkout; the checkout unwritten"),
    _row("FM2-PYC-V2", "bytecode_cycle2", "python_callable_v2: the frozen PYC-1..9 bodies rebound to the second identity",
         [PCB + n for n in ("test_FM2_PYC_V2_1_in_tree_stale_bytecode_with_a_matching_header_is_not_the_subject_the_source_is",
                            "test_FM2_PYC_V2_2_two_checkouts_of_the_same_content_with_different_dates_observe_one_verdict",
                            "test_FM2_PYC_V2_3_a_checkout_with_committed_bytecode_is_byte_identical_before_and_after_the_proof",
                            "test_FM2_PYC_V2_4_the_probe_writes_no_bytecode_into_the_checkout",
                            "test_FM2_PYC_V2_5_the_bytecode_cache_is_fresh_empty_and_outside_the_checkout",
                            "test_FM2_PYC_V2_5b_under_a_story_scratch_the_cache_lies_there_and_is_left_to_the_scratch",
                            "test_FM2_PYC_V2_6_implementer_and_verifier_get_distinct_caches",
                            "test_FM2_PYC_V2_7_an_evaluation_never_reuses_the_cache_of_the_one_before",
                            "test_FM2_PYC_V2_8_isolated_mode_keeps_the_command_line_controls_and_drops_the_environment_route",
                            "test_FM2_PYC_V2_9_without_B_the_external_cache_alone_keeps_the_stale_bytecode_out_and_the_checkout_unwritten")],
         execution="EXECUTED", journal="the source's verdict; the checkout byte-identical; one fresh cache per evaluation"),
]
FAULT_MATRIX += CYCLE2_FAMILY


def _taxonomy_check(rows: list[dict]) -> list[str]:
    """Owner, retryability and budget of every coded row are read from the taxonomy and must equal the row's."""
    from aisef2.arch.enums import EventType, Owner
    from aisef2.control.owner import FailureCode, Retryability, classify
    out = []
    events = {e.value for e in EventType} | {e.name for e in EventType}
    for r in rows:
        e = r["expected"]
        terminal_ok = e["terminal_state"] in TERMINAL or all(t in TERMINAL for t in e["terminal_state"].split("/"))
        if e["execution_status"] not in EXECUTION or not terminal_ok or e["residual_state"] not in RESIDUAL:
            out.append(f"{r['id']}: untyped vocabulary in the row")
        if e["owner"] is not None and e["owner"] not in {o.value for o in Owner}:
            out.append(f"{r['id']}: owner {e['owner']} is not an Owner")
        if e["retryability"] is not None and e["retryability"] not in {x.value for x in Retryability}:
            out.append(f"{r['id']}: retryability {e['retryability']} is not typed")
        for token in [t.strip("(),;") for t in e["journal_state"].replace("(", " ").replace(")", " ").split()]:
            if token.isupper() and "_" in token and token not in events and token not in {c.value for c in FailureCode} \
                    and token not in ("UNSATISFIED", "POST_MERGE", "NON_CONTROLLER_SIGNAL", "SPAWN_FAILED", "RESIDUAL") and not token.startswith("D-"):
                out.append(f"{r['id']}: journal token {token} names no event type or code")
        if e["failure_code"] is not None:
            cl = classify(FailureCode(e["failure_code"]))
            if (cl.owner.value, cl.retryability.value, cl.budget.value if cl.budget else None) != (e["owner"], e["retryability"], e["budget_target"]):
                out.append(f"{r['id']}: the taxonomy says ({cl.owner.value}, {cl.retryability.value}, {cl.budget.value if cl.budget else None})")
    return out


def run(ident: dict) -> dict:
    platform = C.platform_id()
    here = platform["os"]
    evidence_before = _evidence_status()
    problems: list[str] = []
    harness: list[str] = []
    outcomes: dict[str, dict] = {}
    module_counts = {}
    for m in MODULES:
        cases = C.run_module(m)
        module_counts[m] = C.counts(cases)
        outcomes.update({c["id"]: c for c in cases})
    taxonomy_problems = _taxonomy_check(FAULT_MATRIX)
    problems += [f"fault matrix typing: {p}" for p in taxonomy_problems]
    matrix = []
    for r in FAULT_MATRIX:
        rows = [outcomes.get(cid) or {"id": cid, "outcome": C.ERROR, "detail": "case not found in the run", "unrunnable": True} for cid in r["cases"]]
        applicable = here in r["platforms"]
        status = C.status_of(rows) if applicable else C.NOT_APPLICABLE
        matrix.append({**r, "applicable_here": applicable, "status": status, "outcomes": [{"id": x["id"], "outcome": x["outcome"]} for x in rows]})
        if applicable and status != C.GREEN:
            problems.append(f"{r['id']} ({r['class']}): {status}: " + "; ".join(C.problems_of(rows)))
    classes = sorted({r["class"] for r in FAULT_MATRIX})
    v1_cases = [c for m in V1_MATRIX_MODULES for c in C.run_module(m)]
    v1_matrix = json.loads((C.ROOT / "closure-evidence/hardening/fault-matrix.json").read_text(encoding="utf-8"))
    v1 = {"record": "closure-evidence/hardening/fault-matrix.json", "sha256": C.lf_sha(C.ROOT / "closure-evidence/hardening/fault-matrix.json"),
          "cells": len(v1_matrix["scenarios"]), "status_count": v1_matrix.get("status_count"), "counts": C.counts(v1_cases), "cases": v1_cases,
          "note": "the frozen V1 kernel's matrix, still run on the same tree; V1 authority is UNREACHABLE from V2 (P6-OLD-PATH-REMOVAL)"}
    if C.status_of(v1_cases) != C.GREEN:
        problems.append("the V1 fault matrix is not green: " + "; ".join(C.problems_of(v1_cases)))
    race = {k: outcomes.get(cid, {"outcome": C.ERROR, "detail": "not run"}) for k, cid in RACE.items()}
    from tests.v2 import test_v2_006_repeat as rep
    e, err_e = C.capture(_fault_E)
    f, err_f = C.capture(_fault_F)
    g, err_g = C.capture(_fault_G)
    h, err_h = C.capture(_fault_H)
    harness_faults = {"E": e if not err_e else {"ok": False, "error": err_e}, "F": f if not err_f else {"ok": False, "error": err_f},
                      "G": g if not err_g else {"ok": False, "error": err_g}, "H": h if not err_h else {"ok": False, "error": err_h}}
    for k, v in harness_faults.items():
        if v.get("outcome") == C.NOT_APPLICABLE:
            continue
        if "error" in v:
            harness.append(f"harness fault {k} could not run: {v['error'].splitlines()[0]}")
        elif not v.get("ok"):
            problems.append(f"harness fault {k} did not hold: {json.dumps(v, default=str)[:400]}")
    stress = {}
    for name, refs in STRESS.items():
        rows = []
        for ref in refs:
            if ref.startswith("harness:"):
                hv = harness_faults[ref[8:]]
                rows.append({"id": ref, "outcome": hv.get("outcome", C.PASS if hv.get("ok") else C.FAIL)})
            elif ref in RACE:
                rows.append({"id": ref, "outcome": race[ref]["outcome"]})
            else:
                rows.append({"id": ref, "outcome": outcomes.get(ref, {"outcome": C.ERROR})["outcome"]})
        stress[name] = {"status": C.GREEN if all(x["outcome"] in (C.PASS, C.NOT_APPLICABLE) for x in rows) else C.FAILED, "cases": rows}
        if stress[name]["status"] != C.GREEN:
            problems.append(f"stress {name}: {rows}")
    race_ok = all(v["outcome"] == C.PASS for v in race.values())
    if not race_ok:
        problems.append("the V2-006 race family diverges: " + "; ".join(f"{k}: {v['outcome']}" for k, v in race.items() if v["outcome"] != C.PASS))
    wait, err_w = C.capture(_wait_contract)
    if err_w:
        harness.append(f"wait contract could not be measured: {err_w.splitlines()[0]}")
    elif not wait["ok"]:
        problems.append(f"wait contract violated: {wait['violations']}")
    structure = _watchdog_structure()
    if not structure["ok"]:
        problems.append("the anchor's watchdog is not the script's entry")
    import destructive_authority as da
    authority = {"destructive_sites_problems": da.check(C.ROOT), "controller_derived_cleanup": "validation/v2/cleanup_authority.py (Q2 cases test_mutation_safety)"}
    if authority["destructive_sites_problems"]:
        problems.append("destructive authority not ledgered")
    dirty = sorted(set(_evidence_status()) ^ set(evidence_before))   # what the run itself changed under closure-evidence/
    if dirty:
        problems.append(f"evidence changed during the run: {dirty}")
    all_cases = list(outcomes.values()) + v1_cases
    status = C.status_of(all_cases, problems, harness)
    return {
        "record": "AISEF V2 — Q3 FAULT INJECTION", "rung": "Q3", "status": status, "at": C.now(), "subject": ident, "platform": platform,
        "ownership_mechanism": platform["range_mechanism"],
        "fault_matrix": {"classes": classes, "rows": len(matrix), "applicable_here": sum(1 for r in matrix if r["applicable_here"]),
                         "green_here": sum(1 for r in matrix if r["status"] == C.GREEN), "taxonomy_problems": taxonomy_problems,
                         "typing_rule": "owner, retryability and budget target of every coded row equal aisef2.control.owner.classify(code); "
                                        "execution, terminal, journal and residual states name kernel vocabulary only",
                         "matrix": matrix},
        "modules": module_counts, "v1_fault_matrix": v1,
        "v2_006_race": {"cases": race, "all_pass": race_ok, "RACE_10_observations": rep.REPEATS, "RACE_10_orderings": 3, "stress": stress,
                        "harness_faults": harness_faults,
                        "forbidden_remedies_absent": {"exit_driven_reader": "def _exited" not in (C.ROOT / "aisef2/probe/python_callable.py").read_text(encoding="utf-8"),
                                                      "drain_window": "_DRAIN_S" not in (C.ROOT / "aisef2/probe/python_callable.py").read_text(encoding="utf-8")}},
        "bytecode_isolation": {"family": [r["id"] for r in BYTECODE_FAMILY], "fault_H_reproducer_old_vs_corrected": harness_faults["H"]},
        "watchdog_anchor_ownership": {"structure": structure, "fault_F_anchor_terminated": harness_faults["F"], "fault_G_controller_gone_before_STARTED": harness_faults["G"],
                                      "cleanup_authority": authority},
        "process_range_wait_contract": {"measured": wait, "pinned_case": race["WAIT-CONTRACT"],
                                        "closed_report_path_distinguishable": (harness_faults["F"].get("wait_after_anchor_death") or {}).get("closed_path_at_once"),
                                        "rule": "a timeout None arrives only after the monotonic deadline; a closed-report None arrives at once; the reader tells them apart by the clock"},
        "evidence_unchanged_during_run": not dirty,
        "provider_calls": 0, "problems": problems, "harness_problems": harness, "cases": all_cases, "counts": C.counts(all_cases),
    }
