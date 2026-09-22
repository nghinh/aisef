"""P4 evidence records — computed from the code, never written by hand, with a --check twin.

Same contract as `p3_evidence.py`: each record carries `properties`, named facts measured on the implementation;
`--check` re-derives every record and fails if it differs from the committed one or if any property is false. Records
hold outcomes only — never a pid, a temporary path, a duration or a wall-clock time — and nothing that differs between
operating systems, so a rebuild is byte-identical on Linux, macOS and Windows (Q0 rebuilds them on every CI job).
Scenario properties are measured by running the named test case: the test is the measurement.

    python -P validation/v2/p4_evidence.py            # write every record whose package is implemented
    python -P validation/v2/p4_evidence.py --check    # fail on drift or on a false property
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


# --------------------------------------------------------------------------------------- WP-4.1

def story_scope() -> dict:
    from aisef2.journal import event as ev
    from aisef2.journal import format2 as f2
    t2 = _module("aisef_v2_p4_test_format2", "tests/v2/p4/test_format2.py")
    ts = _module("aisef_v2_p4_test_story_scope", "tests/v2/p4/test_story_scope.py")
    fixtures = {p.name: ("declares format 2: format 1 refuses it, format 2 reads it" if f2.declared_format(
        p.read_bytes().decode("utf-8")) == 2 else "read the same by both readers")
        for p in sorted((ROOT / "tests/v2/fixtures/journal").glob("*.jsonl"))}
    fmt = cases(t2, "FormatOneIsUnchanged",
                "test_every_p3_fixture_reads_the_same_through_the_format_2_reader_but_one_that_declares_format_2",
                "test_format_1_schemas_are_the_same_objects_and_only_three_types_are_re_declared",
                "test_a_format_1_type_in_a_format_2_journal_is_judged_by_the_format_1_validator",
                "test_a_format_neither_1_nor_2_is_refused")
    fmt |= cases(t2, "FormatTwo", "test_the_format_1_writer_does_not_extend_a_format_2_journal_nor_the_format_2_writer"
                                  "_a_format_1_one", "test_a_format_2_journal_round_trips_and_keeps_the_format_1_reader"
                                                     "_rules", "test_synthetic_is_written_only_as_true_and_only_in_"
                                                               "format_2")
    journal = cases(t2, "Resources",
                    "test_acquisition_needs_a_begun_attempt_is_once_per_resource_and_is_in_non_increasing_rank",
                    "test_release_is_in_reverse_order_of_the_right_resource_once",
                    "test_an_acquisition_while_the_story_disposes_is_refused_and_a_new_attempt_starts_fresh")
    writer = cases(t2, "Writer2", "test_the_surface_has_no_update_or_delete_verb_and_every_append_is_fsyncd",
                   "test_a_failed_write_or_fsync_leaves_the_log_unchanged_and_poisons_the_writer",
                   "test_a_torn_tail_or_an_unknown_type_is_never_extended_and_the_seq_is_assigned_here")
    scope = cases(ts, "Scope",
                  "test_ordered_acquire_and_reverse_dispose_round_trip_through_the_journal",
                  "test_SCOPE_1_acquisition_during_or_after_disposal_is_refused_and_the_offer_released",
                  "test_an_acquisition_out_of_disposal_order_is_refused_and_released",
                  "test_SCOPE_2_a_failing_first_disposer_does_not_stop_the_rest_and_stays_recorded",
                  "test_a_range_not_proved_empty_makes_what_it_could_write_to_residual_and_nothing_else",
                  "test_a_hanging_release_is_residual_at_its_bound_and_disposal_goes_on",
                  "test_abandonment_names_every_remaining_resource_residual",
                  "test_a_broken_journal_during_disposal_still_releases_everything",
                  "test_SCOPE_3_the_same_resource_graph_gives_the_same_disposal_order_whatever_each_release_takes",
                  "test_a_story_scope_owns_no_journal_writer")
    return {
        "record": "AISEF V2 — P4 STORY SCOPE", "work_package": "WP-4.1", "rfc_sections": ["17", "17.1", "18", "35"],
        "frozen_items": ["F1", "F8"], "semantics": "docs/implementation/v2/P4-LIFETIME-SEMANTICS.md §1, §2",
        "journal_format": {"version": f2.FORMAT, "format_1_version": ev.FORMAT,
                           "new_schemas": sorted(set(f2.SCHEMAS) - set(ev.SCHEMAS)),
                           "re_declared_format_1_types": sorted(set(f2.SCHEMAS) & set(ev.SCHEMAS)),
                           "still_unwritable": sorted(ev.VOCABULARY - f2.WRITABLE),
                           "p3_fixtures": fixtures},
        "disposal_rank": {k.value: v for k, v in f2.DISPOSAL_RANK.items()},
        "format_cases": fmt, "journal_rules": journal, "writer": writer, "scope_cases": scope,
        "properties": {
            "format_1_immutable_and_read_the_same": all(fmt.values()),
            "resource_order_enforced_by_the_journal": all(journal.values()),
            "format_2_writer_keeps_the_p3_discipline": all(writer.values()),
            "SCOPE_1_acquire_during_disposal_refused": scope[
                "test_SCOPE_1_acquisition_during_or_after_disposal_is_refused_and_the_offer_released"],
            "SCOPE_2_remaining_resources_still_disposed_and_failure_recorded": scope[
                "test_SCOPE_2_a_failing_first_disposer_does_not_stop_the_rest_and_stays_recorded"]
                and scope["test_a_broken_journal_during_disposal_still_releases_everything"],
            "SCOPE_3_same_graph_same_disposal_order": scope[
                "test_SCOPE_3_the_same_resource_graph_gives_the_same_disposal_order_whatever_each_release_takes"],
            "no_resource_escapes_unaccounted": all(scope.values()),
            "story_scope_owns_no_journal_writer": scope["test_a_story_scope_owns_no_journal_writer"],
        },
    }


# --------------------------------------------------------------------------------------- WP-4.2

def range_emptiness() -> dict:
    tp = _module("aisef_v2_p4_test_process_range", "tests/v2/p4/test_process_range.py")
    real = cases(tp, "Range", "test_a_normal_tree_is_reaped_and_measured_empty",
                 "test_a_tree_that_exits_by_itself_is_released_without_a_signal",
                 "test_a_running_target_is_stopped_graceful_first",
                 "test_a_range_that_will_not_empty_is_residual_never_a_silent_success_and_blocks_by_default",
                 "test_D_024_red_before_a_writing_grandchild_outlives_a_cleanup_that_trusts_the_direct_child",
                 "test_D_024_green_after_the_range_is_proved_empty_before_the_worktree_is_removed",
                 "test_PROC_OWN_1_a_controller_that_dies_leaves_no_owned_process_alive",
                 "test_PROC_OWN_1_the_mutation_runner_timeout_takes_the_whole_tree_down",
                 "test_PROC_OWN_2_after_disposal_the_range_never_signals_again",
                 "test_start_failures_are_refused_and_leave_nothing_running")
    tt = _module("aisef_v2_p4_test_process_table", "tests/v2/p4/test_process_table.py")
    pids = cases(tt, "NoPidAncestry",
                 "test_WIN_PID_1_a_stale_parent_cycle_terminates_bounded_and_targets_nothing_unowned",
                 "test_WIN_PID_2_a_stale_parent_without_a_cycle_never_selects_the_unrelated_process",
                 "test_the_walk_keeps_true_edges_and_self_parents_and_unknown_times")
    return {
        "record": "AISEF V2 — P4 RANGE EMPTINESS", "work_package": "WP-4.2", "rfc_sections": ["17.1"],
        "frozen_items": ["F8"], "semantics": "docs/implementation/v2/P4-LIFETIME-SEMANTICS.md §3",
        "frozen_acceptance_property": "PID equality alone MUST NOT establish ownership",
        "ownership_mechanism": {
            "posix": "the session and process group of the anchor, the controller's unreaped child: the group id "
                     "cannot be reused while it can be signalled; members measured from /proc (Linux) or ps (macOS); "
                     "Linux: the anchor is a child subreaper, so orphaned escapees are seen",
            "windows": "a Job object with KILL_ON_JOB_CLOSE and no breakaway; the anchor is assigned before the target "
                       "starts; members and emptiness from the job's process list",
            "controller_death": "POSIX: the anchor sees end of file on its control pipe and kills its own group; "
                                "Windows: the job closes with the controller and kills every member"},
        "ladder": {"posix": ["cooperative SIGINT", "grace", "SIGTERM", "grace", "SIGKILL", "wait (unbounded unless "
                                                                                           "bounded by the caller)"],
                   "windows": ["TerminateJobObject", "wait"]},
        "os_asserted_on": "every job of the CI matrix runs tests/v2/p4/test_process_range.py (Linux 3.11-3.14, "
                          "Windows 3.11) and the whole suite inside validation/v2/owned_run.py; the completion record "
                          "binds those runs",
        "cases": real, "pid_cases": pids,
        "residuals_closed": {"V1-PF-001": "WIN-PID-1/2: ownership is the OS mechanism; the only process-table walk "
                                          "reports and never selects",
                             "P2-RESIDUAL-ORPHAN-SUBJECT": "every mutation kill-test run is a process range; a timeout "
                                                           "or a dead controller takes the whole tree down"},
        "properties": {
            "normal_tree_reaped_and_measured_empty": real["test_a_normal_tree_is_reaped_and_measured_empty"],
            "D_024_red_before": real[
                "test_D_024_red_before_a_writing_grandchild_outlives_a_cleanup_that_trusts_the_direct_child"],
            "D_024_green_after": real[
                "test_D_024_green_after_the_range_is_proved_empty_before_the_worktree_is_removed"],
            "WIN_PID_1_cycle_terminates_bounded_nothing_unowned_targeted": pids[
                "test_WIN_PID_1_a_stale_parent_cycle_terminates_bounded_and_targets_nothing_unowned"],
            "WIN_PID_2_unrelated_process_never_targeted": pids[
                "test_WIN_PID_2_a_stale_parent_without_a_cycle_never_selects_the_unrelated_process"],
            "PROC_OWN_1_controller_death_leaves_nothing_owned": real[
                "test_PROC_OWN_1_a_controller_that_dies_leaves_no_owned_process_alive"],
            "PROC_OWN_1_runner_timeout_takes_the_tree_down": real[
                "test_PROC_OWN_1_the_mutation_runner_timeout_takes_the_whole_tree_down"],
            "PROC_OWN_2_never_signalled_after_disposal": real[
                "test_PROC_OWN_2_after_disposal_the_range_never_signals_again"],
            "not_empty_is_residual_never_silent_success": real[
                "test_a_range_that_will_not_empty_is_residual_never_a_silent_success_and_blocks_by_default"],
            "every_case_green": all(real.values()) and all(pids.values()),
        },
    }


# --------------------------------------------------------------------------------------- WP-4.3

def run_lifetime() -> dict:
    from aisef2.runtime import run_scope as rs
    tr = _module("aisef_v2_p4_test_run_scope", "tests/v2/p4/test_run_scope.py")
    c = cases(tr, "Lifetime", "test_a_clean_run_follows_the_normative_order_and_releases_the_lease_last",
              "test_story_scopes_dispose_before_run_level_finalisation",
              "test_P3_RESIDUAL_DISPOSAL_ORDER_a_successful_shutdown_is_refused_while_a_story_is_open",
              "test_RUN_1_a_process_killed_after_a_durable_run_end_and_before_CLEAN_is_torn",
              "test_RUN_2_a_held_lease_blocks_a_second_run_even_with_run_end_written",
              "test_RUN_3_a_writer_that_fails_to_close_leaves_the_sentinel_open_and_the_lease_still_released_last",
              "test_RUN_4_a_clean_that_cannot_be_recorded_leaves_the_sentinel_open",
              "test_the_lease_is_held_before_any_state_read_and_a_failed_begin_still_releases_it_last",
              "test_the_preflight_names_the_previous_runs_residuals", "test_a_sentinel_marks_clean_only_its_own_open_run",
              "test_residuals_of_a_journal_that_cannot_be_read_are_named")
    ks = _module("aisef_v2_kernel_static_checks_p4", "validation/v2/kernel_static_checks.py")
    return {
        "record": "AISEF V2 — P4 RUN LIFETIME", "work_package": "WP-4.3", "rfc_sections": ["18", "18.1", "19"],
        "frozen_items": ["F8"], "semantics": "docs/implementation/v2/P4-LIFETIME-SEMANTICS.md §4",
        "begin_order": list(rs.BEGIN_ORDER), "shutdown_order": list(rs.SHUTDOWN_ORDER),
        "lease": "an exclusive non-blocking OS file lock (flock / LockFile), released by the OS with a dead process",
        "sentinel": "replace-after-fsync: OPEN before the journal opens, CLEAN only after the writer closed; OPEN "
                    "without CLEAN is TORN at the next preflight, which also names the previous journal's residuals",
        "f8_conformance": _conformance("F8.scopes_and_lifetime_order"), "cases": c,
        "properties": {
            "RUN_1_durable_run_end_without_clean_is_torn": c[
                "test_RUN_1_a_process_killed_after_a_durable_run_end_and_before_CLEAN_is_torn"],
            "RUN_2_a_held_lease_blocks_a_second_run": c[
                "test_RUN_2_a_held_lease_blocks_a_second_run_even_with_run_end_written"],
            "RUN_3_writer_close_failure_leaves_open": c[
                "test_RUN_3_a_writer_that_fails_to_close_leaves_the_sentinel_open_and_the_lease_still_released_last"],
            "RUN_4_clean_failure_leaves_open": c["test_RUN_4_a_clean_that_cannot_be_recorded_leaves_the_sentinel_open"],
            "lease_released_last_on_every_path": rs.SHUTDOWN_ORDER[-1] == "lease released" and all(c.values()),
            "P3_RESIDUAL_DISPOSAL_ORDER_enforced": c[
                "test_P3_RESIDUAL_DISPOSAL_ORDER_a_successful_shutdown_is_refused_while_a_story_is_open"],
            "story_scopes_dispose_before_run_finalisation": c["test_story_scopes_dispose_before_run_level_finalisation"],
            "no_gate_may_cite_the_sentinel": ks.check(ROOT, ("SENTINEL_IS_NOT_EVIDENCE",)) == [],
            "f8_conformance_pass": _conformance("F8.scopes_and_lifetime_order")["state"] == "PASS",
        },
    }


def _conformance(sub: str) -> dict:
    fc = _module("aisef_v2_freeze_conformance_p4", "validation/v2/freeze_conformance.py")
    s = next(x for x in fc.evaluate(*fc.load_inputs())["subchecks"] if x["id"] == sub)
    return {"state": s["state"], "detail": s["detail"]}


# --------------------------------------------------------------------------------------- WP-4.4

def runspec_identity() -> dict:
    tr = _module("aisef_v2_p4_test_runspec", "tests/v2/p4/test_runspec.py")
    g = cases(tr, "Grades", "test_verified_binds_a_locally_computed_digest_and_a_version_label_alone_is_refused",
              "test_attested_binds_the_whole_tuple_and_a_measured_fingerprint",
              "test_opaque_binds_what_is_known_and_the_shape_is_checked",
              "test_a_digest_covers_a_file_or_a_tree_and_there_is_no_fallback_for_a_missing_artefact",
              "test_the_resolved_payload_names_the_identity")
    sp = cases(tr, "Spec", "test_the_aggregate_is_the_weakest_grade_and_opaque_bars_q6",
               "test_runspec_hash_is_stable_and_total",
               "test_a_location_is_never_identity_and_the_full_revision_is_required",
               "test_scenario_H_the_implementation_changes_and_the_version_string_does_not",
               "test_comparability_needs_the_same_tuples_grades_and_enforcement")
    from aisef2.runtime import capability as cap
    return {
        "record": "AISEF V2 — P4 RUNSPEC IDENTITY", "work_package": "WP-4.4", "rfc_sections": ["23", "24"],
        "frozen_items": ["F9"], "semantics": "docs/implementation/v2/P4-LIFETIME-SEMANTICS.md §5",
        "grades": {"VERIFIED": "a sha256 digest computed locally over the executed artefact (a version label is "
                               "refused alone)", "ATTESTED": list(cap.ATTESTED_BINDING) + ["deployment when exposed"],
                   "OPAQUE": "what is known; bars Q6 and sealed cohorts"},
        "f9_conformance": _conformance("F9.cited_identities_and_runspec"), "grade_cases": g, "spec_cases": sp,
        "properties": {
            "scenario_H_detected_for_verified_graded_attested_otherwise": sp[
                "test_scenario_H_the_implementation_changes_and_the_version_string_does_not"],
            "OPAQUE_bars_Q6": sp["test_the_aggregate_is_the_weakest_grade_and_opaque_bars_q6"],
            "enforcement_change_breaks_comparability": sp[
                "test_comparability_needs_the_same_tuples_grades_and_enforcement"],
            "provider_and_model_identity_changes_visible": sp[
                "test_comparability_needs_the_same_tuples_grades_and_enforcement"],
            "checkout_path_is_a_locator_never_identity_full_sha_authoritative": sp[
                "test_a_location_is_never_identity_and_the_full_revision_is_required"],
            "runspec_hash_stable_and_total": sp["test_runspec_hash_is_stable_and_total"],
            "no_hidden_identity_fallback": g[
                "test_a_digest_covers_a_file_or_a_tree_and_there_is_no_fallback_for_a_missing_artefact"]
                and g["test_verified_binds_a_locally_computed_digest_and_a_version_label_alone_is_refused"],
            "every_case_green": all(g.values()) and all(sp.values()),
            "f9_conformance_pass": _conformance("F9.cited_identities_and_runspec")["state"] == "PASS",
        },
    }


# --------------------------------------------------------------------------------------- WP-4.5

def budgets() -> dict:
    tb = _module("aisef_v2_p4_test_budgets", "tests/v2/p4/test_budgets.py")
    c = cases(tb, "Budgets", "test_SS_64_a_cap_reached_in_one_budget_stops_there_and_never_falls_through",
              "test_D_006_a_credential_or_environment_rejection_never_consumes_the_developer_budget",
              "test_PRE_SATISFIED_and_PLAN_CONTRADICTION_consume_no_developer_budget",
              "test_only_a_typed_chargeable_outcome_charges_its_declared_budget",
              "test_no_approved_count_is_no_retry_and_no_failure_is_nothing_to_retry",
              "test_the_journal_rebuilt_from_scratch_gives_the_same_budgets_and_the_same_decisions",
              "test_the_budget_module_keeps_no_counter")
    ks = _module("aisef_v2_kernel_static_checks_p4", "validation/v2/kernel_static_checks.py")
    from aisef2.control.owner import TAXONOMY
    return {
        "record": "AISEF V2 — P4 BUDGETS", "work_package": "WP-4.5", "rfc_sections": ["17", "21", "22"],
        "frozen_items": ["F3", "F11"], "semantics": "docs/implementation/v2/P4-LIFETIME-SEMANTICS.md §6",
        "authority": "the budgets and retry_target projections of the journal prefix (P3, unchanged) and the resolved "
                     "retry counts; aisef2/control/budget.py counts nothing",
        "charged_budget_by_code": {c.value: (TAXONOMY[c].budget.value if TAXONOMY[c].budget else None)
                                   for c in TAXONOMY},
        "cases": c,
        "properties": {
            "SS_64_cap_never_falls_through": c[
                "test_SS_64_a_cap_reached_in_one_budget_stops_there_and_never_falls_through"],
            "D_006_no_developer_charge_for_credential_or_environment": c[
                "test_D_006_a_credential_or_environment_rejection_never_consumes_the_developer_budget"],
            "PRE_SATISFIED_and_PLAN_CONTRADICTION_charge_no_developer_budget": c[
                "test_PRE_SATISFIED_and_PLAN_CONTRADICTION_consume_no_developer_budget"],
            "only_typed_chargeable_outcomes_charge_their_budget": c[
                "test_only_a_typed_chargeable_outcome_charges_its_declared_budget"],
            "budgets_reconstruct_exactly_from_the_journal": c[
                "test_the_journal_rebuilt_from_scratch_gives_the_same_budgets_and_the_same_decisions"],
            "no_side_retry_counter": ks.check(ROOT, ("NO_SIDE_RETRY_COUNTER",)) == []
                and c["test_the_budget_module_keeps_no_counter"],
            "every_case_green": all(c.values()),
        },
    }


# --------------------------------------------------------------------------------------- WP-4.6

def interruption() -> dict:
    ti = _module("aisef_v2_p4_test_interruption", "tests/v2/p4/test_interruption.py")
    live = cases(ti, "Interruption", "test_a_tool_that_finishes_is_measured_and_its_range_released",
                 "test_INTERRUPT_SIG_1_a_controller_stop_is_attributed_to_the_controller",
                 "test_INTERRUPT_SIG_2_a_subject_signal_exit_never_becomes_an_owner", "test_the_outcome_table",
                 "test_INTERRUPT_SIG_3_closers_distinguish_not_started_from_outcome_unknown_and_leave_no_gap",
                 "test_an_interrupted_run_disposes_its_scopes_before_it_finishes_and_stays_torn",
                 "test_a_second_interrupt_during_disposal_abandons_and_says_so",
                 "test_interruptible_turns_a_keyboard_interrupt_into_an_interruption")
    rep = cases(ti, "Repair", "test_repair_closes_everything_open_synthetically_at_the_last_real_time",
                "test_repair_is_idempotent_and_byte_identical", "test_a_run_already_interrupted_is_abandoned_by_repair",
                "test_repair_refuses_what_it_cannot_extend")
    return {
        "record": "AISEF V2 — P4 INTERRUPTION", "work_package": "WP-4.6", "rfc_sections": ["17.1", "20.2"],
        "frozen_items": ["F1", "F8"], "semantics": "docs/implementation/v2/P4-LIFETIME-SEMANTICS.md §7",
        "provenance": "a tool's signal exit is CONTROLLER when its range's ledger holds that signal, UNKNOWN otherwise; "
                      "the tool layer writes no failure code for it",
        "closers": {"dispatched, completion unknown": "OUTCOME_UNKNOWN", "never dispatched": "NOT_STARTED",
                    "unreleased resource (repair)": "RESIDUAL", "every closer": "synthetic: true, at the last real "
                                                                                 "event's time"},
        "real_signal_cases": "RealSignals (SIGINT and SIGKILL to a controller mid-story) run on every POSIX CI job; "
                             "they are not part of this record, which is rebuilt identically on Windows",
        "live_cases": live, "repair_cases": rep,
        "residuals_closed": {"P2-RESIDUAL-SIGNAL-SOURCE": "for every process P4 owns (tools in ranges): provenance "
                                                          "recorded, a signal exit never an owner; the P2 probe harness "
                                                          "is not P4-owned — see the P4 report",
                             "P3-RESIDUAL-DISPOSAL-ORDER": "WP-4.3: a successful shutdown is refused while a story is "
                                                           "open; an interruption closes and names instead"},
        "properties": {
            "INTERRUPT_SIG_1_controller_stop_distinguishable": live[
                "test_INTERRUPT_SIG_1_a_controller_stop_is_attributed_to_the_controller"],
            "INTERRUPT_SIG_2_signal_exit_never_an_owner": live[
                "test_INTERRUPT_SIG_2_a_subject_signal_exit_never_becomes_an_owner"],
            "INTERRUPT_SIG_3_unknown_is_outcome_unknown_not_started_before_dispatch": live[
                "test_INTERRUPT_SIG_3_closers_distinguish_not_started_from_outcome_unknown_and_leave_no_gap"],
            "no_interruption_creates_a_gap": live[
                "test_INTERRUPT_SIG_3_closers_distinguish_not_started_from_outcome_unknown_and_leave_no_gap"]
                and rep["test_repair_closes_everything_open_synthetically_at_the_last_real_time"],
            "repair_idempotent_and_byte_identical": rep["test_repair_is_idempotent_and_byte_identical"],
            "abandonment_explicit": live["test_a_second_interrupt_during_disposal_abandons_and_says_so"]
                and rep["test_a_run_already_interrupted_is_abandoned_by_repair"],
            "scopes_dispose_before_run_finalisation_and_failures_stay_evidence": live[
                "test_an_interrupted_run_disposes_its_scopes_before_it_finishes_and_stays_torn"],
            "every_case_green": all(live.values()) and all(rep.values()),
        },
    }


BUILDERS: dict[str, tuple[str, Callable[[], dict], str]] = {
    "WP-4.1": ("closure-evidence/v2/P4-STORY-SCOPE.json", story_scope, "aisef2/runtime/story_scope.py"),
    "WP-4.2": ("closure-evidence/v2/P4-RANGE-EMPTINESS.json", range_emptiness, "aisef2/runtime/process_range.py"),
    "WP-4.3": ("closure-evidence/v2/P4-RUN-LIFETIME.json", run_lifetime, "aisef2/runtime/run_scope.py"),
    "WP-4.4": ("closure-evidence/v2/P4-RUNSPEC-IDENTITY.json", runspec_identity, "aisef2/runtime/runspec.py"),
    "WP-4.5": ("closure-evidence/v2/P4-BUDGETS.json", budgets, "aisef2/control/budget.py"),
    "WP-4.6": ("closure-evidence/v2/P4-INTERRUPTION.json", interruption, "aisef2/runtime/repair.py"),
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
    print("p4 evidence: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
