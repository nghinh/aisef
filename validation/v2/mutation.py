"""V2 mutation testing — AST mutants of one kernel function, each run against the tests that must kill it.

A mutant is **killed** when its kill tests fail (or time out) and **survives** when they pass. A survivor is a gap in
the tests unless it is individually audited as equivalent in `AUDITED`, with a reason; targets listed in
`NO_AUDIT` (the ContractSatisfaction mapping, frozen under F2) must be killed outright.

Kill tests are semantic by design. `compiler_digest` addresses the compiler's own source, so any mutant of the
compiler changes every spec id; tests that compare against committed specs would "kill" every mutant for that
reason alone, so they are never in a kill set.

The record binds each target's module source (LF-normalised sha256): editing a target makes the record stale and
`--check` fails until the mutation run is repeated.

One record per phase (`RECORDS`): a run writes each target into its phase's record, so a sealed phase's record is
never rewritten by a later phase's targets. A later phase that must re-measure an earlier phase's targets (their module
changed) takes them over (`SUPERSEDED`): the earlier record keeps its historical entries for them, reported as
superseded and never re-checked against the new source, so no target is counted twice.

A probe's child script (a module-level string constant that the probe runs in the subject's process) is code too:
`path::SCRIPT/function` names a function (or a module-level table) of the script bound to `SCRIPT`; its mutants are
made in the parsed script and written back into the constant, so the kill tests run the mutated script (C2-P3).

    python -P validation/v2/mutation.py run [target ...]   # run; writes closure-evidence/v2/P<n>-MUTATION.json
    python -P validation/v2/mutation.py --check            # every phase record current, every target killed or audited
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(pathlib.Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(1, str(pathlib.Path(__file__).resolve().parent))
import cleanup_authority as ca  # noqa: E402  — the runner's only way to signal a process (P4-FINDING-011)
RECORDS = {"P1": "closure-evidence/v2/P1-MUTATION.json", "P2": "closure-evidence/v2/P2-MUTATION.json",
           "P3": "closure-evidence/v2/P3-MUTATION.json", "P4": "closure-evidence/v2/P4-MUTATION.json",
           "P5": "closure-evidence/v2/P5-MUTATION.json", "P6": "closure-evidence/v2/P6-MUTATION.json",
           "C2-P1": "closure-evidence/v2/cycle2/P1-MUTATION.json",
           "C2-P2": "closure-evidence/v2/cycle2/P2-MUTATION.json",
           "C2-P3": "closure-evidence/v2/cycle2/P3-MUTATION.json",
           "C2-P4": "closure-evidence/v2/cycle2/P4-MUTATION.json",
           "C2-ORCH": "closure-evidence/v2/cycle2/C2-ORCH-MUTATION.json",
           "C2-P10": "closure-evidence/v2/cycle2/P10-MUTATION.json",
           "K-PRESAT-001": "closure-evidence/v2/cycle2/K-PRESAT-001-MUTATION.json",
           "K-NOWORK-001": "closure-evidence/v2/cycle2/K-NOWORK-001-MUTATION.json"}
OUT_REL = RECORDS["P1"]
#: per kill-test file. V2.0 S2: the B1 split runs a controller and an agent per evaluation, and the heaviest kill file
#: (tests/v2/test_python_callable_v2.py) takes 96 s on an idle machine — 120 s would let two workers' load time out
#: the unmutated baseline. A kill by timeout is still named in the record.
TIMEOUT = 300

#: target "path::function" -> the test files that must kill its mutants (semantic tests only; see module doc).
_CONTRACT_TESTS = ["tests/v2/p1/test_contract.py"]
P1_TARGETS: dict[str, list[str]] = {
    # WP-1.1: contract_hash and the canonical identity it is made of
    "aisef2/product/contract.py::contract_hash": _CONTRACT_TESTS,
    "aisef2/product/contract.py::content_of": _CONTRACT_TESTS,
    "aisef2/product/contract.py::plain": _CONTRACT_TESTS,
    "aisef2/product/contract.py::canonical": _CONTRACT_TESTS,
    "aisef2/product/contract.py::digest": _CONTRACT_TESTS,
    "aisef2/product/contract.py::freeze": _CONTRACT_TESTS,
    # WP-1.2: the compiler and the spec identities (semantic kill set only; never the committed corpus)
    "aisef2/product/compiler.py::compile_spec": ["tests/v2/p1/test_spec_compiler.py"],
    "aisef2/product/compiler.py::expectation_for": ["tests/v2/p1/test_spec_compiler.py"],
    "aisef2/product/spec.py::semantic_hash": ["tests/v2/p1/test_spec_compiler.py"],
    "aisef2/product/spec.py::spec_id": ["tests/v2/p1/test_spec_compiler.py"],
    # WP-1.3: the F2 satisfaction derivation (no audits accepted), subject absence, the EXECUTED invariants
    "aisef2/product/outcome.py::contract_satisfaction": ["tests/v2/p1/test_outcome.py"],
    "aisef2/product/outcome.py::on_subject_absent": ["tests/v2/p1/test_outcome.py"],
    "aisef2/product/outcome.py::__post_init__": ["tests/v2/p1/test_outcome.py"],
    # WP-1.4: the taxonomy and the routing table are data; both are mutated like functions
    "aisef2/control/owner.py::TAXONOMY": ["tests/v2/p1/test_routing.py", "tests/v2/p2/test_signal_provenance.py"],
    "aisef2/control/owner.py::classify": ["tests/v2/p1/test_routing.py"],
    "aisef2/control/owner.py::flatten": ["tests/v2/p1/test_routing.py", "tests/v2/p5/test_invariants.py"],  # + INV-PROSE-1
    "aisef2/control/routing.py::_EXECUTED": ["tests/v2/p1/test_routing.py", "tests/v2/p2/test_signal_provenance.py"],
    "aisef2/control/routing.py::route": ["tests/v2/p1/test_routing.py", "tests/v2/p2/test_signal_provenance.py"],
    # WP-5.5: the non-raising lookup story admission reads (§4: no boundary catches UnroutableOutcome)
    "aisef2/control/routing.py::row_for": ["tests/v2/p1/test_routing.py", "tests/v2/p2/test_signal_provenance.py",
                                           "tests/v2/p2/test_story_admission.py"],
}
_PROTOCOL_TESTS = ["tests/v2/p2/test_probe_protocol.py"]
_HARNESS_TESTS = ["tests/v2/p2/test_python_callable.py"]
#: the provenance split is measured by both: the harness's own cases and SIG-PROBE-1..10 (V2-003)
_SIGNAL_TESTS = ["tests/v2/p2/test_python_callable.py", "tests/v2/p2/test_signal_provenance.py"]
#: ARCHITECTURE-EXCEPTION-V2-006: the protocol reader and the exit's place in it are killed by the race tests too
_STREAM_TESTS = [*_SIGNAL_TESTS, "tests/v2/test_v2_006.py"]
_ADMISSION_TESTS = ["tests/v2/p2/test_static_admission.py"]
_BYTECODE_TESTS = ["tests/v2/test_p7_finding_001.py"]
P2_TARGETS: dict[str, list[str]] = {
    # WP-2.1: the only mapping from an observation to a ProbeResult, and the entry point that binds enforcement
    "aisef2/probe/protocol.py::classify_failure": _PROTOCOL_TESTS,
    "aisef2/probe/protocol.py::run_probe": _PROTOCOL_TESTS,
    # P2 correction (V2-002): no default verdict for an expired window; the sealed record and the only read of its
    # result (PROBE-BIND-1/2); the class a spec asks for is harness metadata (PROBE-META-1)
    "aisef2/probe/protocol.py::Observation.__post_init__": _PROTOCOL_TESTS,
    "aisef2/probe/protocol.py::ProbeRecord.__post_init__": _PROTOCOL_TESTS,
    "aisef2/probe/protocol.py::comparability": _PROTOCOL_TESTS,
    "aisef2/probe/protocol.py::bound_result": _PROTOCOL_TESTS,
    "aisef2/probe/protocol.py::ProbeRegistry.observation_class": _PROTOCOL_TESTS,
    # the reference harness: the watchdog/window split (TIME-1..5) and the per-class meaning of an expired window
    "aisef2/probe/python_callable.py::observe": [*_HARNESS_TESTS, *_BYTECODE_TESTS],
    # P7-FINDING-001 correction: bytecode isolation — the command line (isolated mode, -B, the external cache), the
    # fresh evaluation directory (creation, uniqueness, ownership), the in-tree refusal, the probe's own hooks
    "aisef2/probe/python_callable.py::_harness_argv": _BYTECODE_TESTS,
    "aisef2/probe/python_callable.py::_evaluation_dir": _BYTECODE_TESTS,
    "aisef2/probe/python_callable.py::_inside": _BYTECODE_TESTS,
    "aisef2/probe/python_callable.py::PythonCallableProbe.__init__": _BYTECODE_TESTS,
    "aisef2/probe/python_callable.py::window_of": _HARNESS_TESTS,
    "aisef2/probe/python_callable.py::observation_class": _HARNESS_TESTS,
    "aisef2/probe/python_callable.py::ON_DEADLINE": _HARNESS_TESTS,
    "aisef2/probe/python_callable.py::_harness_failure": [*_HARNESS_TESTS, "tests/v2/test_v2_006.py"],
    # V2-003 (§9.3): the provenance split — the controller's own ledger decides, never the signal number
    "aisef2/probe/python_callable.py::_after_dispatch": _SIGNAL_TESTS,
    "aisef2/probe/python_callable.py::_ended_without_result": _STREAM_TESTS,
    "aisef2/probe/python_callable.py::_signal_of": _SIGNAL_TESTS,
    # §35: the probe's identity — a source dropped here would reuse an old digest, and with it an old semantic_hash
    "aisef2/probe/python_callable.py::PROBE_SOURCES": _HARNESS_TESTS,
    "aisef2/probe/python_callable.py::_probe_digest": _HARNESS_TESTS,
    "aisef2/probe/python_callable.py::_watch": _STREAM_TESTS,
    "aisef2/probe/python_callable.py::_pump": _STREAM_TESTS,
    "aisef2/probe/python_callable.py::_next": _STREAM_TESTS,
    # WP-2.2: contrast to the candidate expectation, and the only way a calibration record is issued
    "aisef2/probe/calibration.py::demonstrates_contrast": ["tests/v2/p2/test_calibration.py"],
    "aisef2/probe/calibration.py::calibrate": ["tests/v2/p2/test_calibration.py"],
    # WP-2.3: the engine and each of its nine checks, with the graph helpers they rely on
    "aisef2/plan/static_admission.py::admit": _ADMISSION_TESTS,
    "aisef2/plan/static_admission.py::check_requirement_coverage": _ADMISSION_TESTS,
    "aisef2/plan/static_admission.py::check_contract_spec_integrity": _ADMISSION_TESTS,
    "aisef2/plan/static_admission.py::check_ownership": _ADMISSION_TESTS,
    "aisef2/plan/static_admission.py::check_dependency_dag": _ADMISSION_TESTS,
    "aisef2/plan/static_admission.py::check_contradictions": _ADMISSION_TESTS,
    "aisef2/plan/static_admission.py::check_proof_capability": _ADMISSION_TESTS,
    "aisef2/plan/static_admission.py::check_traceability": _ADMISSION_TESTS,
    "aisef2/plan/static_admission.py::check_plan_structure": _ADMISSION_TESTS,
    "aisef2/plan/static_admission.py::check_probe_calibration": _ADMISSION_TESTS,
    "aisef2/plan/static_admission.py::_cycle": _ADMISSION_TESTS,
    "aisef2/plan/static_admission.py::story_graph": _ADMISSION_TESTS,
    "aisef2/plan/static_admission.py::depends_on_story": _ADMISSION_TESTS,
    # WP-2.4: the §13 disposition table, the story gate and the ordering rule
    "aisef2/plan/story_admission.py::classify": ["tests/v2/p2/test_story_admission.py"],
    "aisef2/plan/story_admission.py::admit_story": ["tests/v2/p2/test_story_admission.py"],
    "aisef2/plan/story_admission.py::ordering_problems": ["tests/v2/p2/test_story_admission.py"],
    "aisef2/plan/story_admission.py::request_developer": ["tests/v2/p2/test_story_admission.py"],
    # WP-2.5: attribution through the DAG, the continuation after admission, the budget rule, plan quality
    "aisef2/plan/drift.py::attribute": ["tests/v2/p2/test_drift.py"],
    "aisef2/plan/drift.py::continue_story": ["tests/v2/p2/test_drift.py"],
    "aisef2/plan/drift.py::budget_problems": ["tests/v2/p2/test_drift.py"],
    "aisef2/plan/drift.py::plan_quality": ["tests/v2/p2/test_drift.py"],
}
_WRITER_TESTS = ["tests/v2/p3/test_journal_writer.py"]
_FOLD_TESTS = ["tests/v2/test_fold_oracle.py"]
_PROJECTION_TESTS = ["tests/v2/p3/test_control_projections.py"]
_REFMODEL_TESTS = ["tests/v2/p3/test_reference_models.py"]
P3_TARGETS: dict[str, list[str]] = {
    # WP-3.1: the envelope, append-site validation (with each rule and the citation check), the codec, the writer
    "aisef2/journal/event.py::Event.__post_init__": _WRITER_TESTS,
    "aisef2/journal/event.py::validate": _WRITER_TESTS,
    "aisef2/journal/event.py::_cites": _WRITER_TESTS,
    "aisef2/journal/event.py::_format_rule": _WRITER_TESTS,
    "aisef2/journal/event.py::_admission_rule": _WRITER_TESTS,
    "aisef2/journal/event.py::_drift_rule": _WRITER_TESTS,
    "aisef2/journal/event.py::_failure_rule": _WRITER_TESTS,
    "aisef2/journal/event.py::carried": _WRITER_TESTS,
    "aisef2/journal/event.py::decode": _WRITER_TESTS,
    "aisef2/journal/writer.py::JournalWriter.__init__": _WRITER_TESTS,
    "aisef2/journal/writer.py::append": _WRITER_TESTS,
    # WP-3.2: the one reader and a prefix's identity
    "aisef2/journal/compat.py::reconstruct": ["tests/v2/p3/test_format_compat.py", "tests/v2/p3/test_journal_writer.py"],
    "aisef2/journal/compat.py::Journal.head": ["tests/v2/p3/test_format_compat.py"],
    # WP-3.3: the pure fold, the incremental fold, the oracle, cache rows and the pre-append authority
    "aisef2/journal/fold.py::fold": _FOLD_TESTS,
    "aisef2/journal/fold.py::_frozen": _FOLD_TESTS,
    "aisef2/journal/fold.py::Folder.__init__": _FOLD_TESTS,
    "aisef2/journal/fold.py::Folder.peek": _FOLD_TESTS,
    "aisef2/journal/fold.py::Folder.advance": _FOLD_TESTS,
    "aisef2/journal/fold.py::oracle_problems": _FOLD_TESTS,
    "aisef2/journal/fold.py::cache_row": _FOLD_TESTS,
    "aisef2/journal/fold.py::_seal": _FOLD_TESTS,
    "aisef2/journal/fold.py::resume": _FOLD_TESTS,
    "aisef2/journal/fold.py::Authority.__init__": _FOLD_TESTS,
    "aisef2/journal/fold.py::Authority.append": _FOLD_TESTS,
    "aisef2/journal/projections/__init__.py::project": _FOLD_TESTS,
    # WP-3.4: every control decision the six projections produce — each step, and the rule tables they read
    "aisef2/journal/projections/story_state.py::StoryState.step": _PROJECTION_TESTS,
    "aisef2/journal/projections/story_state.py::_OUTCOMES": _PROJECTION_TESTS,
    "aisef2/journal/projections/story_state.py::_WITHIN": _PROJECTION_TESTS,
    "aisef2/journal/projections/failure_owner.py::FailureOwner.step": _PROJECTION_TESTS,
    "aisef2/journal/projections/budgets.py::Budgets.step": _PROJECTION_TESTS,
    "aisef2/journal/projections/retry_target.py::RetryTarget.step": _PROJECTION_TESTS,
    "aisef2/journal/projections/terminal_state.py::TerminalState.step": _PROJECTION_TESTS,
    "aisef2/journal/projections/terminal_state.py::_RUN": _PROJECTION_TESTS,
    "aisef2/journal/projections/terminal_state.py::_OUTCOME": _PROJECTION_TESTS,
    "aisef2/journal/projections/qualification_counters.py::QualificationCounters.step": _PROJECTION_TESTS,
    "aisef2/journal/projections/qualification_counters.py::metrics": _PROJECTION_TESTS,
    # WP-3.5: the independent reference models — mutated like the projections, killed by their calibration and the
    # differential (a mutant model that still agrees with the implementation everywhere is a gap in the harness)
    "tests/v2/refmodel/story_state.py::model": _REFMODEL_TESTS,
    "tests/v2/refmodel/story_state.py::_TABLE": _REFMODEL_TESTS,
    "tests/v2/refmodel/failure_owner.py::_attempts": _REFMODEL_TESTS,
    "tests/v2/refmodel/failure_owner.py::_read": _REFMODEL_TESTS,
    "tests/v2/refmodel/failure_owner.py::model": _REFMODEL_TESTS,
    "tests/v2/refmodel/budgets.py::_walk": _REFMODEL_TESTS,
    "tests/v2/refmodel/budgets.py::model": _REFMODEL_TESTS,
    "tests/v2/refmodel/retry_target.py::model": _REFMODEL_TESTS,
    "tests/v2/refmodel/terminal_state.py::model": _REFMODEL_TESTS,
    "tests/v2/refmodel/terminal_state.py::_RUN": _REFMODEL_TESTS,
    "tests/v2/refmodel/terminal_state.py::_INTERRUPT": _REFMODEL_TESTS,
    "tests/v2/refmodel/terminal_state.py::_SETTLED": _REFMODEL_TESTS,
    "tests/v2/refmodel/terminal_state.py::_OUTCOME": _REFMODEL_TESTS,
    "tests/v2/refmodel/qualification_counters.py::metrics": _REFMODEL_TESTS,
    "tests/v2/refmodel/qualification_counters.py::model": _REFMODEL_TESTS,
    "tests/v2/refmodel/qualification_counters.py::_COUNTED": _REFMODEL_TESTS,
}
_FORMAT2_TESTS = ["tests/v2/p4/test_format2.py"]
_SCOPE_TESTS = ["tests/v2/p4/test_story_scope.py"]
_RANGE_TESTS = ["tests/v2/p4/test_process_range.py"]
_TABLE_TESTS = ["tests/v2/p4/test_process_table.py"]
_RUN_TESTS = ["tests/v2/p4/test_run_scope.py"]
_SPEC_TESTS = ["tests/v2/p4/test_runspec.py"]
_BUDGET_TESTS = ["tests/v2/p4/test_budgets.py"]
_INT_TESTS = ["tests/v2/p4/test_interruption.py"]
P4_TARGETS: dict[str, list[str]] = {
    # WP-4.1: journal format 2 (schemas, the rules over the journal, the reader, the writer) and StoryScope
    **{f"aisef2/journal/format2.py::{f}": _FORMAT2_TESTS for f in (
        "validate", "_cites", "_attempt", "_open_acquisitions", "_acquired", "_released", "_capability", "_spec",
        "_invoked", "_tool_result", "_provider_result", "_tool_result_rule", "_provider_result_rule",
        "_synthetic_only_true", "_format_rule", "_str_map", "declared_format", "reconstruct", "DISPOSAL_RANK",
        "CLOSERS", "_GRADE_ORDER", "JournalWriter2.__init__", "JournalWriter2.append", "JournalWriter2.close")},
    **{f"aisef2/runtime/story_scope.py::{f}": _SCOPE_TESTS for f in (
        "StoryScope.acquire", "StoryScope.dispose", "StoryScope._record", "DisposalReport.ok",
        "Directory.__init__", "Directory.release")},
    # WP-4.2: measured range emptiness — the ownership walk (pure) and the POSIX range; the Windows job adapter
    # (_Job) and the Linux /proc reader run on CI, not on the developer machine this tool runs on
    **{f"aisef2/runtime/process_range.py::{f}": _TABLE_TESTS for f in ("descendants", "targets", "_ps_table")},
    **{f"aisef2/runtime/process_range.py::{f}": _RANGE_TESTS for f in (
        "_Posix.members", "_Posix.escaped", "_Posix.abort", "ProcessRange.start",
        "ProcessRange.wait", "ProcessRange.members", "ProcessRange.escaped", "ProcessRange.wait_empty",
        "ProcessRange._signal", "ProcessRange.release", "ProcessRange._abort", "ProcessRange._close_pipes")},
    **{f"aisef2/runtime/range_anchor.py::{f}": _RANGE_TESTS for f in ("_die", "_subreaper", "_reap_adopted")},
    **{f"aisef2/runtime/range_anchor.py::{f}": [*_RANGE_TESTS, "tests/v2/test_v2_006.py"] for f in ("main",)},
    "aisef2/runtime/process_range.py::_Job.controller_stopped": _RANGE_TESTS,
    "aisef2/runtime/process_range.py::ProcessRange.anchor_returncode": _RANGE_TESTS,
    "aisef2/runtime/story_scope.py::StoryScope.release": _SCOPE_TESTS,
    # WP-5.5: the invariant violation crosses the release thread (INV-EXC through the kernel's own boundary)
    "aisef2/runtime/story_scope.py::StoryScope._release": _SCOPE_TESTS + ["tests/v2/p5/test_invariants.py"],
    # WP-4.3: the lease, the lifetime order, the sentinel
    **{f"aisef2/runtime/run_scope.py::{f}": _RUN_TESTS for f in (
        "RunLease.acquire", "RunLease.release", "RunScope.begin", "RunScope.open_stories", "RunScope.shutdown",
        "RunScope._finish", "RunScope._fail", "RunScope.story")},
    # appends go on while an interruption closes what is open: the interruption tests kill that too
    "aisef2/runtime/run_scope.py::RunScope.append": _RUN_TESTS + _INT_TESTS,
    **{f"aisef2/runtime/sentinel.py::{f}": _RUN_TESTS for f in (
        "_fsync_dir", "_write", "read", "mark_open", "mark_clean", "residuals", "preflight")},
    # WP-4.4: identity grades and the RunSpec
    **{f"aisef2/runtime/capability.py::{f}": _SPEC_TESTS for f in (
        "CapabilityIdentity.__post_init__", "CapabilityIdentity.content", "CapabilityIdentity.identity",
        "CapabilityIdentity.resolved", "digest_of", "verified", "attested", "opaque")},
    **{f"aisef2/runtime/runspec.py::{f}": _SPEC_TESTS for f in (
        "RunSpec.revision", "RunSpec.resolved", "_is_locator", "runspec_hash", "resolve", "comparable", "q6_eligible")},
    # WP-4.5: the journal-derived retry decision
    **{f"aisef2/control/budget.py::{f}": _BUDGET_TESTS for f in ("charge", "developer_spend")},
    "aisef2/runtime/run_scope.py::RunScope.retry": _BUDGET_TESTS,
    # WP-4.6: provenance, closers, interruption, repair
    **{f"aisef2/runtime/tool.py::{f}": _INT_TESTS for f in (
        "outcome", "ToolCall._data", "ToolCall.dispatch", "ToolCall.finish", "ToolCall.close")},
    **{f"aisef2/runtime/repair.py::{f}": _INT_TESTS for f in ("closers", "repair", "repair_journal")},
    **{f"aisef2/runtime/run_scope.py::{f}": _INT_TESTS for f in (
        "RunScope._now", "RunScope.interrupt", "RunScope._second_interrupt_abandons")},
}
_EXEC_TESTS = ["tests/v2/p5/test_test_execution.py"]
_REL_TESTS = ["tests/v2/p5/test_relevance.py"]
P5_TARGETS: dict[str, list[str]] = {
    # WP-5.1: the typed shape, the only mapping from a runner's report, the cause classification, the adapters
    **{f"aisef2/quality/test_execution.py::{f}": _EXEC_TESTS for f in (
        "classify", "_cause_owner", "_owner_for", "unrunnable", "TestExecution.__post_init__", "DeveloperTests.owns",
        "DeveloperTests.__post_init__", "CollectionError.__post_init__", "Case.__post_init__", "_read_unittest",
        "_read_junit", "_norm", "project_top_level")},
    # WP-5.2: the story diff, what is line-addressable, the executable lines, the shape, the only measurement
    **{f"aisef2/quality/relevance.py::{f}": _REL_TESTS for f in (
        "measure", "story_diff", "line_addressable", "executable_lines", "RelevanceResult.__post_init__",
        "ChangedArtefact.__post_init__")},
}
P5_TARGETS["aisef2/quality/test_execution.py::_read_unittest"] = _EXEC_TESTS + _REL_TESTS  # it reads the measurement too
_VAC_TESTS = ["tests/v2/p5/test_vacuity.py"]
# WP-5.3: the only vacuity mapping, the deterministic reconstruction, the typed patch, the shape
P5_TARGETS.update({f"aisef2/quality/vacuity.py::{f}": _VAC_TESTS for f in (
    "evaluate", "neutralise", "_reverse", "file_patches", "VacuityResult.__post_init__", "Hunk.side")})
_ADQ_TESTS = ["tests/v2/p5/test_adequacy.py"]
# WP-5.4: the only assembly, its precedence lists, the positive construction, the shape, the owner read from typed facts
P5_TARGETS.update({f"aisef2/quality/adequacy.py::{f}": _ADQ_TESTS for f in (
    "assemble", "_defects", "_gaps", "_adequate", "EngineeringTestAdequacy.__post_init__", "Assembly.__post_init__",
    "Assembly.owner", "Assembly.developer_chargeable", "may_block")})
_INV_TESTS = ["tests/v2/p5/test_invariants.py"]
# WP-5.5: registration (fail closed), tier arming, mechanism resolution, the runtime guard; the evidence-origin
# boundary; the except-boundary audit
P5_TARGETS.update({f"aisef2/invariants/registry.py::{f}": _INV_TESTS for f in (
    "register", "arm", "resolve", "_load_script", "require_armed", "_arms", "test_directories")})
P5_TARGETS.update({f"aisef2/invariants/evidence.py::{f}": _INV_TESTS for f in ("admit", "harness_records")})
P5_TARGETS.update({f"validation/v2/except_boundaries.py::{f}": _INV_TESTS for f in (
    "audit_source", "_disposition", "_could_hold", "_resolve", "_caught", "_reraises_all", "_is_invariant_reraise",
    "audit", "check")})
# WP52-001: the destructive-site checker's discovery of callables handed over by reference, and the ledger check
P5_TARGETS.update({f"validation/v2/destructive_authority.py::{f}": ["tests/v2/p0/test_destructive_authority.py"]
                   for f in ("discover", "_references", "_destructive_ref", "_aliases", "_alias", "check")})
# WP-6.1: the generated V1 proof-mode migration table — derivation, alias resolution, the declaration-only path to
# SubjectAbsence, the inventory's classification, and the --check that refuses drift, a hand edit, an unknown mode
# or a defaulted row. Kill tests are self-contained (fake roots): the repository-level tests live in
# tests/v2/test_migration_table_repo.py and are not kill tests (the runner's tree copy holds no V1 evidence).
_MIG_TESTS = ["tests/v2/test_migration_table.py"]
_V2_005 = "tests/v2/test_v2_005.py"  # ARCHITECTURE-EXCEPTION-V2-005: kills the format-3 semantics of the targets it changed
P6_TARGETS: dict[str, list[str]] = {f"validation/v2/gen_migration_table.py::{f}": _MIG_TESTS for f in (
    "derive", "resolve", "declared", "cited", "read_v1", "_unknown", "without_v1_source", "_loss_code", "loss_report",
    "inventory", "problems", "compare", "check", "write")}
# WP-6.2 under ARCHITECTURE-EXCEPTION-V2-005: journal format 3 — the schema catalog, its rules, the format dispatch,
# the writer; the taxonomy, projection and reference-model targets it changed are re-run in their own phase's record
_FMT3_TESTS = ["tests/v2/test_v2_005.py", "tests/v2/p3/test_reference_models.py"]
P6_TARGETS.update({f"aisef2/journal/format3.py::{f}": _FMT3_TESTS for f in (
    "_budget_owner", "_checks", "_execution", "_format_rule", "_static_admission_rule", "_verified_payload_rule",
    "_adequacy_rule", "_failure_schema", "SCHEMAS", "_static_admitted", "_story_active", "_verified", "verified_proof",
    "_cites", "validate", "declared_format", "reconstruct", "JournalWriter3.append")})
# WP-6.2: the single authoritative orchestration path (aisef2/orchestrate). Every stage module is killed by the
# per-stage tests; the runner's two path functions by the real-path cases (ORCH-1..16, ORCH-SCHEMA-1..10) as well.
_ORCH_STAGES = ["tests/v2/test_p6_stages.py"]
_ORCH_PATH = [*_ORCH_STAGES, "tests/v2/test_p6_orchestration.py"]
P6_TARGETS.update({f"aisef2/orchestrate/{m}::{f}": _ORCH_STAGES for m, fs in (
    ("adapters.py", ("Implemented.__post_init__", "Finding.blocks", "ReadOnlyScope.read", "ReadOnlyScope.files",
                     "confine", "unconfine", "Merge.__post_init__")),
    ("gate.py", ("PROJECTIONS", "check", "decision")),
    ("merge.py", ("merge", "affected_preserve", "reprove")),
    ("proof.py", ("Ranged.__init__", "Party.__init__", "Party.run", "prove", "obligations_of")),
    ("quality.py", ("payload", "assess")),
    ("review.py", ("_result", "review")),
    ("seam.py", ("SeamRefusal.__init__", "resolve", "admit_legacy")),
    ("security.py", ("scan",)),
    ("story_runner.py", ("StoryResult.committed", "StoryResult.revision", "_Held.__init__", "_Held.__call__",
                         "_Held.release", "_committed", "_freeze_plan", "_fail", "_probe")),
    ("workspace.py", ("_NO_BACKGROUND_GIT", "git", "_sha", "Scratch.__init__", "Scratch.release", "Checkout.__init__",
                      "Checkout.release", "GitWorkspace.scratch", "GitWorkspace.checkout", "GitWorkspace.move",
                      "GitWorkspace.diff", "GitMerger.base", "GitMerger.merge", "GitMerger.revert", "commit_all")),
) for f in fs})
P6_TARGETS.update({f"aisef2/orchestrate/story_runner.py::{f}": _ORCH_PATH for f in ("run_story", "_attempt")})
P6_TARGETS["aisef2/journal/format3.py::verified_payload"] = [*_FMT3_TESTS, *_ORCH_STAGES]
# WP-6.3: the old-path audit — every function killed on synthetic trees; the audit's entry, comparison, inventory and
# proofs by the real-tree no-dual-authority cases as well (fail-closed in both directions, R1–R6)
_OPA_TESTS = ["tests/v2/test_old_path_audit.py"]
_OPA_REAL = [*_OPA_TESTS, "tests/v2/test_no_dual_authority.py"]
P6_TARGETS.update({f"validation/v2/old_path_audit.py::{f}": _OPA_TESTS for f in (
    "_lf", "_module_name", "_imports", "_dotted", "_qualify", "_defs", "def_digest", "_py_files", "legacy_imports",
    "_capabilities", "v2_reality", "reachable_modules", "v1_reality", "entrypoints", "legacy_references",
    "test_legacy_imports", "adapter_conditions", "_seam_before_first_event", "inventory_digest", "_function",
    "_kernel_rules", "developer_test_flows", "parent_execution_sites", "recency_sites", "journal_backing",
    "decision_table", "decision_problems", "render")})
P6_TARGETS.update({f"validation/v2/old_path_audit.py::{f}": _OPA_REAL for f in ("inventory", "proofs", "compare", "audit", "check")})
for _t in ("aisef2/journal/projections/budgets.py::Budgets.step", "aisef2/journal/projections/story_state.py::StoryState.step",
           "aisef2/journal/projections/story_state.py::_WITHIN", "aisef2/journal/projections/story_state.py::_OUTCOMES",
           "tests/v2/refmodel/budgets.py::_walk", "tests/v2/refmodel/budgets.py::model",
           "tests/v2/refmodel/story_state.py::_TABLE", "tests/v2/refmodel/story_state.py::model"):
    P3_TARGETS[_t] = [*P3_TARGETS[_t], _V2_005]
for _t in ("aisef2/runtime/repair.py::closers", "aisef2/runtime/repair.py::repair", "aisef2/runtime/repair.py::repair_journal",
           "aisef2/runtime/sentinel.py::residuals"):
    P4_TARGETS[_t] = [*P4_TARGETS[_t], _V2_005]
for _t in ("aisef2/control/owner.py::TAXONOMY", "aisef2/control/owner.py::classify", "aisef2/control/owner.py::flatten"):
    P1_TARGETS[_t] = [*P1_TARGETS[_t], _V2_005]
# Cycle 2, C2-P1 (WP-2.1.1): every function and table of the file_artifact probe, killed by its own module (the
# object-store rule on real repositories, the fault family FM2-FILE, the calibration fixtures, the pinned tables).
# Names that generate no mutant (PROBE_ID, WEAKEST_PATH, the integer caps, _PREFIX, _LOCATIONS, DIGEST, METADATA,
# PlainTree.__init__) are not targets: a run that cannot say NO proves nothing.
_FILE_ARTIFACT_TESTS = ["tests/v2/test_c2_file_artifact.py"]
C2_P1_TARGETS: dict[str, list[str]] = {f"aisef2/probe/file_artifact.py::{f}": _FILE_ARTIFACT_TESTS for f in (
    "PROBE_SOURCES", "CLASSES", "ON_DEADLINE", "NEWLINES", "MODES", "_HEX64", "_probe_digest", "window_of", "_compiles",
    "observation_class", "spec_class", "refusal", "expected_sha256", "verdict_of", "normalised", "content_facts",
    "grep_facts", "selected", "git_env", "run_git", "ObjectStore.__init__", "ObjectStore.run",
    "ObjectStore.holds_revision", "ObjectStore.lookup", "ObjectStore.entries", "ObjectStore.walk", "ObjectStore._parse",
    "ObjectStore.blob", "PlainTree._full", "PlainTree._row", "PlainTree.lookup", "PlainTree.entries", "PlainTree.walk",
    "PlainTree.blob", "entry", "read",
    "facts_of", "FileArtifactProbe.__init__", "FileArtifactProbe.enforcement",
    "FileArtifactProbe.harness_preconditions", "FileArtifactProbe.observe", "FileArtifactProbe._reader")}
# C2-P4 (WP-2.4.1, owner DECISION-6): the second python_callable identity. The P2 targets of python_callable.py that
# this module defines for itself (the frozen helpers it imports keep their P2 evidence), plus its own extensions:
# the class table, the hex/workspace validators, the placeholder substitution, the workspace writer.
_C2_P4_TESTS = ["tests/v2/test_python_callable_v2.py"]
_C2_P4_BYTECODE = ["tests/v2/test_python_callable_v2_bytecode.py"]   # PYC-1..9 rerun against the second identity
C2_P4_TARGETS: dict[str, list[str]] = {f"aisef2/probe/python_callable_v2.py::{f}": _C2_P4_TESTS for f in (
    "PROBE_SOURCES", "CLASSES", "ON_DEADLINE", "_probe_digest", "_is_hex", "_file_ok", "_workspace_ok", "observation_class",
    "spec_class", "verdict_of", "_substituted", "_unsubstituted", "_write_workspace", "PythonCallableV2Probe.enforcement",
    "_watch")}
C2_P4_TARGETS["aisef2/probe/python_callable_v2.py::observe"] = [*_C2_P4_TESTS, *_C2_P4_BYTECODE]
C2_P4_TARGETS.update({f"aisef2/probe/python_callable_v2.py::{f}": _C2_P4_BYTECODE
                      for f in ("_harness_argv", "PythonCallableV2Probe.__init__")})
# Cycle 2, C2-P2 (WP-2.2.1): the cli_invocation probe. The pure functions (classes, shapes, verdicts over fixture
# facts, the marker-file parser, the layout) are killed in-process; the harness (observe, the watch loop, the
# hard-exit and harness-failure rules, the command line) by the subprocess-backed cases, DESIGN-CHECK-1 and the
# FM2-CLI / FM2-PYC-CLI fault families. Scalar constants (PROBE_ID, STREAM_CAP, PLACEHOLDER, POLL_S, HARNESS) have no
# mutation site and are not targets; HARNESS, the child script, is killed through observe's cases.
#: the pure functions, the class table (WP-2.2.2) and the equality shape, comparator and verdict: in-process
_CLI_PURE = ["tests/v2/test_c2_cli_verdicts.py"]
#: the decision table over test doubles first (a mutant of the watch loop dies there in a second; the runner stops at
#: the first failing file), the real subjects only for what the doubles cannot say
_CLI_HARNESS = ["tests/v2/test_c2_cli_protocol.py", "tests/v2/test_c2_cli_invocation.py"]
#: WP-2.2.2: the two-invocation path on real subjects
_CLI_CALIBRATION = ["tests/v2/test_c2_cli_calibration.py"]
C2P2_TARGETS: dict[str, list[str]] = {
    **{f"aisef2/probe/cli_invocation.py::{f}": _CLI_PURE for f in (
        "_is_int", "_content_ok", "_bytes_of", "_name_ok", "_ws_key_ok", "_argv_ok", "_stimulus_ok", "_stream_shape_ok",
        "_file_shape_ok", "observation_class", "spec_class", "_sha_file", "_stream_fact", "_file_fact", "_stream_bytes",
        "_stream_matches", "_file_matches", "verdict_of", "_ws_name", "_substitute", "_public", "_child_env",
        "_protocol", "_prepare", "CLASSES", "ON_DEADLINE", "STREAM_SHAPES", "FILE_SHAPES",
        "CliInvocationProbe.enforcement", "CliInvocationProbe.harness_preconditions",
        "_normalization_ok", "_equality_ok", "_streams_ok", "_normalize", "_equal", "_half_ok", "_equality_verdict",
        "CLASS_TABLE", "QUANTIFIERS", "COMPARATORS")},
    **{f"aisef2/probe/cli_invocation.py::{f}": _CLI_HARNESS for f in (
        "PROBE_SOURCES", "_probe_digest", "_await", "CliInvocationProbe.__init__", "CliInvocationProbe.observe",
        "CliInvocationProbe._observe", "CliInvocationProbe._observe_in", "_preflight", "_watch", "_hard_exit",
        "_harness_failure", "_disposed")},
    "aisef2/probe/cli_invocation.py::CliInvocationProbe._observe_equality": [*_CLI_HARNESS[:1], *_CLI_CALIBRATION],
    "aisef2/probe/cli_invocation.py::_harness_argv": [*_CLI_PURE, *_CLI_HARNESS],
}
# Cycle 2, C2-P3 (WP-2.3.1): the process_effect scenario probe. The parent's pure functions and tables (the step
# vocabulary and its shapes, the scenario rules, the classes, the file observables, the placeholder substitution, the
# request layout, the RESULT conclusion) are killed in-process; the parent's harness (observe, the watch, the
# hard-exit rule) by the decision table over test doubles first, then the real subjects; every function of the child
# script HARNESS (the step dispatcher, the fault scope, the expect_raises attribute comparison, edit_jsonl, the file
# facts, the placeholder replaced back) by the real subjects, the only place the script runs, then the bytecode
# family (the subprocess step's isolation). SUBPROCESS (the subprocess step's boot) has no function: it is killed
# through PE-4 and FM2-PYC-EFFECT-2, never a target.
_PE_UNITS = ["tests/v2/test_probe_process_effect_units.py"]
_PE_REAL = ["tests/v2/test_probe_process_effect.py"]
_PE_PYC = ["tests/v2/test_probe_process_effect_bytecode.py"]
C2P3_TARGETS: dict[str, list[str]] = {
    **{f"aisef2/probe/process_effect.py::{f}": _PE_UNITS for f in (
        "CLASSES", "ON_DEADLINE", "STEPS", "FAULTS", "FAULTED", "FILE_SHAPES", "CLASS_TABLE", "_CONTENT",
        "_flat_ok", "_ws_path_ok", "_ident_ok", "_content_of", "_invocation_ok", "_workspace_ok", "_expect_ok",
        "_write_ok", "_edit_ok", "_subprocess_ok", "_fault_ok", "_SHAPES", "_step_ok", "_scenario_ok",
        "_FILE_SHAPE_OK", "_file_shape_ok", "observation_class", "spec_class", "_same", "_returns_hold",
        "_raises_hold", "_identity", "_jsonl_holds", "_FILE_HOLDS", "_files_hold", "_HOLDS", "verdict_of",
        "_substitute", "_resolved", "_observed_files", "_concluded", "PROBE_SOURCES", "_probe_digest",
        "ProcessEffectProbe.enforcement", "ProcessEffectProbe.harness_preconditions")},
    **{f"aisef2/probe/process_effect.py::{f}": [*_PE_UNITS, *_PE_REAL, *_PE_PYC] for f in (
        "_harness_argv", "_prepare", "ProcessEffectProbe.__init__", "ProcessEffectProbe.observe",
        "ProcessEffectProbe._observe_in", "_watch", "_hard_exit")},
    **{f"aisef2/probe/process_effect.py::HARNESS/{f}": [*_PE_REAL, *_PE_PYC] for f in (
        "emit", "inside", "resolve", "unws", "tagged", "same", "row_of", "count_lines", "file_fact", "files_now",
        "identity", "guarded", "target_of", "do_workspace", "do_construct", "do_call", "raised_as", "do_expect",
        "do_write", "do_edit", "do_subprocess", "do_fault", "HANDLERS", "run", "main")},
}
# C2-ORCHESTRATION-CONFORMANCE-REPAIR (owner ruling 2026-09-30): the repair changed story_runner.py and proof.py, and a
# source digest is whole-file, so every P6 target of the two modules is re-measured here, the conformance cases added
# to its kill set (after the stage tests, before the real-path cases); P6 keeps its historical entries for them.
_C2_ORCH_MODULES = ("aisef2/orchestrate/story_runner.py", "aisef2/orchestrate/proof.py")
C2_ORCH_TARGETS: dict[str, list[str]] = {
    t: [k[0], "tests/v2/test_c2_orchestration_conformance.py", *k[1:]]
    for t, k in P6_TARGETS.items() if t.split("::")[0] in _C2_ORCH_MODULES}
# Cycle 2, C2-P10 (WP-2.10.1): the evaluation-cohort machinery — every function of aisef2/cohort and every module-level
# table that generates a mutant (the hex patterns, the shape table, the identity components, the DEVELOPMENT_REGRESSION
# registry, the one-way successor table, the demoted states). SCHEMA (a bare string), FROZEN_INPUTS (tuple(SHAPES)) and
# MIN_WORKLOADS (an integer) have no mutation site and are not targets; the kill tests pin their values. Kill tests are in-process and read only the two frozen LedgerLock files.
_COHORT_TESTS = ["tests/v2/test_c2_p10_cohort.py"]
C2_P10_TARGETS: dict[str, list[str]] = {
    **{f"aisef2/cohort/preregistration.py::{f}": _COHORT_TESTS for f in (
        "_HEX40", "_HEX64", "CohortRefused.__init__", "_hex40", "_hex64", "_name", "_count", "_names",
        "SHAPES", "IDENTITY", "DEVELOPMENT_REGRESSION", "execution_profile", "runspec_of", "policy_of",
        "problems", "validate", "preregistration_hash", "frozen_inputs", "workload_identity", "shared",
        "development_regression")},
    **{f"aisef2/cohort/lifecycle.py::{f}": _COHORT_TESTS for f in (
        "NEXT", "DEMOTED", "EvaluationCohort.__post_init__", "EvaluationCohort.id",
        "EvaluationCohort.preregistration_hash", "EvaluationCohort.frozen_inputs", "EvaluationCohort.planned_runs",
        "EvaluationCohort.threshold", "EvaluationCohort.plan_quality_policy", "EvaluationCohort.workload", "seal",
        "advance", "_live", "record_run", "read_results", "observe_inputs", "_complete", "generalization")},
}
# K-PRESAT-001 (owner rulings 2026-10-01, 'BOUNDED CORRECTIVE PATCH' §3 and 'DETERMINISTIC REPAIR COMPLETION' §4): the
# correction changed story_runner.py, and a source digest is whole-file, so every C2-ORCH target of that module — and
# only those — is re-measured here, the K-PRESAT regression cases added to its kill set (after the stage tests); C2-ORCH
# keeps its historical entries for them, as P6 does.
K_PRESAT_TARGETS: dict[str, list[str]] = {
    t: [k[0], "tests/v2/test_c2_k_presat_001.py", *k[1:]]
    for t, k in C2_ORCH_TARGETS.items() if t.split("::")[0] == "aisef2/orchestrate/story_runner.py"}
#: target -> the phase that took it over; an earlier phase's record entry for it is historical (reported, not checked)
SUPERSEDED: dict[str, str] = {t: "C2-ORCH" for t in C2_ORCH_TARGETS}
for _t in C2_ORCH_TARGETS:
    del P6_TARGETS[_t]
SUPERSEDED.update({t: "K-PRESAT-001" for t in K_PRESAT_TARGETS})
for _t in K_PRESAT_TARGETS:
    del C2_ORCH_TARGETS[_t]
# K-NOWORK-001 (owner ruling 2026-10-02, 'K-NOWORK-001 MEASURED ARCHITECTURE CORRECTION'): the correction changed
# story_runner.py again, so the same targets are re-measured here, the K-NOWORK regression cases added to their kill set
# (after the stage tests); K-PRESAT-001 keeps its historical entries for them, and its record is not rewritten.
K_NOWORK_TARGETS: dict[str, list[str]] = {
    t: [k[0], "tests/v2/test_c2_k_nowork_001.py", *k[1:]] for t, k in K_PRESAT_TARGETS.items()}
SUPERSEDED.update({t: "K-NOWORK-001" for t in K_NOWORK_TARGETS})
for _t in K_NOWORK_TARGETS:
    del K_PRESAT_TARGETS[_t]
# V2.0 STABLE RELEASE, S2 — the single fix window (release charter §7–§8): B1 (the verdict channel: the controller /
# agent split of cli_invocation, process_effect and python_callable_v2), B4/B6 (workspace: the isolated git configuration, the refused
# repository configuration, the clean of each move), B7 (story_runner: no revert of a merge that changed nothing),
# KA-09 (adapters: confine and unconfine leave a symbolic link alone), B12/B3 (the product runtime, aisef2/app),
# B1-BLOCKS-STOP-001 (python_callable_v2 and cli_invocation: the deadline is the controller's own statement). A source
# digest is whole-file, so every target of a changed module is re-measured here, the S2 regression cases added to its
# kill set; the earlier phase keeps its historical entries (SUPERSEDED), as K-NOWORK-001 did. A target the change
# removed (`_hard_exit`, the old HARNESS dispatch) is not carried over; the new controller and agent functions are added.
_S2_KERNEL = ["tests/v2/test_release_s2_kernel.py"]
_APP = ["tests/v2/test_app_units.py", "tests/v2/test_app_run.py"]
_S2_CHANGED = ("aisef2/orchestrate/workspace.py", "aisef2/orchestrate/adapters.py")
S2_TARGETS: dict[str, list[str]] = {
    **{t: [k[0], *_S2_KERNEL, *k[1:]] for t, k in K_NOWORK_TARGETS.items()},
    **{t: [*k, *_S2_KERNEL] for t, k in P6_TARGETS.items() if t.split("::")[0] in _S2_CHANGED},
    **{f"aisef2/orchestrate/workspace.py::{f}": [*_ORCH_STAGES, *_S2_KERNEL] for f in ("_env", "config_problems")},
    **{t: k for t, k in C2P2_TARGETS.items() if not t.endswith("::_hard_exit")},
    **{f"aisef2/probe/cli_invocation.py::{f}": _CLI_HARNESS for f in ("_concluded", "_no_result", "_deadline", "_silent")},
    "aisef2/probe/cli_invocation.py::_mac": [*_CLI_PURE, *_CLI_HARNESS],
    **{f"aisef2/probe/cli_invocation.py::{s}/{f}": _CLI_HARNESS for s, fs in (
        ("AGENT", ("flush", "redirect", "send", "tagged", "plain", "op_import", "op_resolve", "op_value", "op_construct",
                   "guarded", "op_call", "op_invoke", "op_bye")),
        ("HARNESS", ("emit", "conclude", "deadline", "answer_to", "ask", "finish", "inside", "resolve", "sha",
                     "file_fact", "stream_fact", "invoke", "ended", "main"))) for f in fs},
    **{t: k for t, k in C2P3_TARGETS.items()
       if t.split("::")[1] not in ("_hard_exit", "HARNESS/HANDLERS", "HARNESS/raised_as", "HARNESS/tagged", "HARNESS/target_of")},
    **{f"aisef2/probe/process_effect.py::HARNESS/{f}": [*_PE_REAL, *_PE_PYC] for f in (
        "answer_to", "ask", "finish", "answered", "reported", "subject_call", "unresolved", "ended")},
    **{t: k for t, k in C2_P4_TARGETS.items() if not t.endswith("::observe")},
    "aisef2/probe/python_callable_v2.py::PythonCallableV2Probe.observe": [*_C2_P4_TESTS, *_C2_P4_BYTECODE],
    "aisef2/probe/python_callable_v2.py::_concluded": _C2_P4_TESTS,
    **{f"aisef2/probe/python_callable_v2.py::HARNESS/{f}": [*_C2_P4_TESTS, *_C2_P4_BYTECODE] for f in (
        "emit", "conclude", "deadline", "answer_to", "ask", "finish", "answered", "ended", "inside", "value_of", "main")},
    **{f"aisef2/app/{m}::{f}": _APP for m, fs in (
        ("run.py", ("kernel_digest", "calibrations", "admit", "check_git", "check_repository", "probe_interpreter", "regression_tests",
                    "runspec_of", "productproof", "delivery", "execute", "_close")),
        ("verify.py", ("verify",)),
        ("client.py", ("read_session", "Budget.__init__", "Budget.spend", "Budget.reached", "environment", "wait_within",
                       "session")),
        ("preflight.py", ("accounting", "run", "identity_problems", "fingerprint_fields", "deployment")),
        ("settings.py", ("_count", "load")),
        ("bundle.py", ("Project.order", "load")),
        ("adapters.py", ("attempt_of", "Developer.implement", "Reviewer.review")),
        ("cli.py", ("run",))) for f in fs},
}
# Survivors of the current-snapshot campaign (owner ruling 'MUTATION WORKER HANDOFF', 2026-10-04) are killed by cases in
# a file of their own, named only in the kill sets of the targets they were written for: re-measuring those targets
# leaves every other result's kill-test closure byte-identical.
_S2_KILLS = "tests/v2/test_s2_kills.py"
for _t in ("aisef2/probe/cli_invocation.py::AGENT/op_invoke",):
    S2_TARGETS[_t] = [*S2_TARGETS[_t], _S2_KILLS]
for _t in ("aisef2/probe/process_effect.py::HARNESS/ask",):   # killed only by the clock: its bounded case runs first
    S2_TARGETS[_t] = [_S2_KILLS, *S2_TARGETS[_t]]
SUPERSEDED.update({t: "V2.0-S2" for t in S2_TARGETS})
for _phase in (K_NOWORK_TARGETS, P6_TARGETS, C2P2_TARGETS, C2P3_TARGETS, C2_P4_TARGETS):
    for _t in [t for t in _phase if t.split("::")[0] in (*_S2_CHANGED, "aisef2/orchestrate/story_runner.py",
                                                          "aisef2/probe/cli_invocation.py", "aisef2/probe/process_effect.py",
                                                          "aisef2/probe/python_callable_v2.py")]:
        SUPERSEDED.setdefault(_t, "V2.0-S2")
        del _phase[_t]
RECORDS["V2.0-S2"] = "closure-evidence/v2/release/S2-MUTATION.json"
PHASE_TARGETS = {"P1": P1_TARGETS, "P2": P2_TARGETS, "P3": P3_TARGETS, "P4": P4_TARGETS, "P5": P5_TARGETS,
                 "P6": P6_TARGETS, "C2-P1": C2_P1_TARGETS, "C2-P2": C2P2_TARGETS, "C2-P3": C2P3_TARGETS, "C2-P4": C2_P4_TARGETS,
                 "C2-ORCH": C2_ORCH_TARGETS, "C2-P10": C2_P10_TARGETS, "K-PRESAT-001": K_PRESAT_TARGETS,
                 "K-NOWORK-001": K_NOWORK_TARGETS, "V2.0-S2": S2_TARGETS}
TARGETS: dict[str, list[str]] = {t: k for targets in PHASE_TARGETS.values() for t, k in targets.items()}
#: Targets whose survivors may not be audited away.
NO_AUDIT: set[str] = {"aisef2/product/outcome.py::contract_satisfaction"}
#: (target, mutant description) -> why the mutant is equivalent, each examined by hand. Only the independent reference
#: models have entries: their code is not edited to remove a dead field, because its author is not this session.
_DEAD_FLAG = ("the third field (whether the target state is also the outcome) is read only when the target state is "
              "not None (model: `if to is not None: ... if is_outcome`); this entry's target is None")
AUDITED: dict[tuple[str, str], str] = {
    ("tests/v2/refmodel/story_state.py::_TABLE", "L19 False->True"): _DEAD_FLAG,
    ("tests/v2/refmodel/story_state.py::_TABLE", "L20 False->True"): _DEAD_FLAG,
    ("tests/v2/refmodel/story_state.py::_TABLE", "L21 False->True"): _DEAD_FLAG,   # V2-005 rows: proof/verified,
    ("tests/v2/refmodel/story_state.py::_TABLE", "L22 False->True"): _DEAD_FLAG,   # tests/adequacy — target None
    ("tests/v2/refmodel/story_state.py::_TABLE", "L23 False->True"): _DEAD_FLAG,
    ("tests/v2/refmodel/budgets.py::model", "L75 True->False"): (
        "zip(strict=) over a four-name tuple and _walk's four-value return: the lengths are always equal, so strict "
        "never decides anything"),
    ("tests/v2/refmodel/qualification_counters.py::metrics", "L15 element 0 dropped"): (
        "`pre` is read only through len(pre): a one-element tuple per entry counts the same"),
    ("tests/v2/refmodel/qualification_counters.py::metrics", "L15 element 1 dropped"): (
        "`pre` is read only through len(pre): a one-element tuple per entry counts the same"),
    ("tests/v2/refmodel/qualification_counters.py::model", "L41 sorted() -> list()"): (
        "`unplanned` is read only for truthiness and inside the refusal message"),
    ("tests/v2/refmodel/qualification_counters.py::model", "L44 sorted() -> list()"): (
        "`misplaced` is read only for truthiness and inside the refusal message"),
}
#: What a run copies into its scratch tree.
COPY = ("aisef2", "tests/v2", "validation/v2", "docs/architecture", "docs/implementation/v2", "closure-evidence/v2",
        "aisef",   # the frozen V1 tree, read by the WIN-PID red-before reproducers; never a target
        "pyproject.toml")  # the console-script table the old-path audit inventories (tests/v2/test_no_dual_authority.py)

_SWAP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Is: ast.IsNot, ast.IsNot: ast.Is, ast.In: ast.NotIn,
         ast.NotIn: ast.In, ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE, ast.LtE: ast.Gt}


def source_digest(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _enum_members(module_src: str, root: pathlib.Path) -> dict[str, list[str]]:
    """Enum classes visible to the module (its own and those it imports from aisef2), by name -> members."""
    out: dict[str, list[str]] = {}
    tree = ast.parse(module_src)
    sources = [tree]
    for n in tree.body:
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("aisef2"):
            dep = root / (n.module.replace(".", "/") + ".py")
            if dep.exists():
                sources.append(ast.parse(dep.read_text(encoding="utf-8")))
    for t in sources:
        for c in ast.walk(t):
            if isinstance(c, ast.ClassDef) and any(getattr(b, "id", "") == "Enum" for b in c.bases):
                out[c.name] = [s.targets[0].id for s in c.body if isinstance(s, ast.Assign)
                               and isinstance(s.targets[0], ast.Name)]
    return out


def _inert(func: ast.AST, doc: ast.AST | None) -> set[int]:
    """Nodes that cannot change behaviour: the docstring, every annotation (postponed, never evaluated), and the message
    of a reference model's `raise Refused(...)` — a model answers a state or REFUSED; its refusal text is not part of
    that answer, and the harness never compares it (P3-PROJECTION-SEMANTICS.md: "raise Refused, any message")."""
    inert = [doc] if doc is not None else []
    inert += [a for n in ast.walk(func) if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call)
              and getattr(n.exc.func, "id", "") == "Refused" for a in [*n.exc.args, *(k.value for k in n.exc.keywords)]]
    a = func.args
    inert += [x.annotation for x in a.posonlyargs + a.args + a.kwonlyargs + [a.vararg, a.kwarg] if x and x.annotation]
    inert += [func.returns] if func.returns else []
    inert += [n.annotation for n in ast.walk(func) if isinstance(n, ast.AnnAssign)]
    return {id(n) for root in inert for n in ast.walk(root)}


def _script(tree: ast.Module, name: str) -> ast.Constant | None:
    """The child script bound to the module-level name `name`: a string constant holding Python source."""
    for n in tree.body:
        if isinstance(n, ast.Assign) and [getattr(t, "id", None) for t in n.targets] == [name] \
                and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
            return n.value
    return None


def _root(tree: ast.Module, name: str) -> tuple[ast.AST, set[int]] | None:
    """A function named `name` (minus its docstring and annotations), or the value of a module-level assignment
    to `name` — so a routing table or a taxonomy held as data is a mutation target like a function is. `Class.method`
    names the method of that class when one module has several methods of the same name; `SCRIPT/name` names one in
    the child script bound to `SCRIPT` (a node of the parsed script)."""
    script, _, inner = name.partition("/")
    if inner:
        const = _script(tree, script)
        return None if const is None else _root(ast.parse(const.value), inner)
    owner, _, name = name.rpartition(".")
    if owner:
        tree = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == owner), None)
        if tree is None:
            return None
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == name:
            doc = n.body[0] if n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant) \
                and isinstance(n.body[0].value.value, str) else None
            return n, _inert(n, doc)
    for n in tree.body:
        if isinstance(n, ast.Assign):
            names = [getattr(x, "id", None) for x in n.targets]
        elif isinstance(n, ast.AnnAssign) and n.value is not None:
            names = [getattr(n.target, "id", None)]
        else:
            continue
        if name in names:
            return n.value, set()
    return None


def mutants(module_src: str, func: str, enums: dict[str, list[str]]) -> list[tuple[str, str]]:
    """(description, mutated module source) for every mutation site inside the function or table `func`; for
    `SCRIPT/name`, the mutants of the child script's function written back into the script's constant."""
    script, _, inner = func.partition("/")
    if inner:
        tree = ast.parse(module_src)
        const = _script(tree, script)
        if const is None:
            raise SystemExit(f"child script {script} not found")
        out = []
        for desc, src in mutants(const.value, inner, enums):
            const.value = src
            out.append((f"{script} {desc}", ast.unparse(tree)))
        return out
    tree = ast.parse(module_src)
    found = _root(tree, func)
    if found is None:
        raise SystemExit(f"function or module-level table {func} not found")
    target, skip = found
    sites = [n for n in ast.walk(target) if n is not target and id(n) not in skip]
    out = []

    def emit(desc: str, node: ast.AST, apply) -> None:
        t2 = copy.deepcopy(tree)
        f2, skip2 = _root(t2, func)
        twin = [n for n in ast.walk(f2) if n is not f2 and id(n) not in skip2][sites.index(node)]
        if apply(twin, f2) is not False:
            out.append((f"L{getattr(node, 'lineno', getattr(target, 'lineno', 0))} {desc}",
                        ast.unparse(ast.fix_missing_locations(t2))))

    for node in sites:
        if isinstance(node, ast.Compare):
            for i, op in enumerate(node.ops):
                if type(op) in _SWAP:
                    emit(f"{type(op).__name__}->{_SWAP[type(op)].__name__}", node,
                         lambda n, _f, i=i: n.ops.__setitem__(i, _SWAP[type(n.ops[i])]()))
        elif isinstance(node, ast.BoolOp):
            emit(f"{type(node.op).__name__} swapped", node,
                 lambda n, _f: setattr(n, "op", ast.Or() if isinstance(n.op, ast.And) else ast.And()))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            emit("not removed", node, lambda n, _f: setattr(n, "op", ast.UAdd()))
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            emit(f"{node.value}->{not node.value}", node, lambda n, _f: setattr(n, "value", not n.value))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value:
            emit(f"string {node.value!r} emptied", node, lambda n, _f: setattr(n, "value", ""))
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in enums:
            for alt in enums[node.value.id]:
                if alt != node.attr:
                    emit(f"{node.value.id}.{node.attr}->{alt}", node, lambda n, _f, alt=alt: setattr(n, "attr", alt))
        elif isinstance(node, ast.Dict):
            for i in range(len(node.keys)):
                emit(f"dict entry {i} dropped", node,
                     lambda n, _f, i=i: (n.keys.pop(i), n.values.pop(i)))
        elif isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) > 1:
            for i in range(len(node.elts)):
                emit(f"element {i} dropped", node, lambda n, _f, i=i: n.elts.pop(i))
        elif isinstance(node, ast.If):
            emit("condition negated", node, lambda n, _f: setattr(n, "test", ast.UnaryOp(ast.Not(), n.test)))
        elif isinstance(node, ast.IfExp):
            emit("conditional negated", node, lambda n, _f: setattr(n, "test", ast.UnaryOp(ast.Not(), n.test)))
        elif isinstance(node, ast.Return) and node.value is not None \
                and not (isinstance(node.value, ast.Constant) and node.value.value is None):  # else: no change
            emit("returns None", node, lambda n, _f: setattr(n, "value", ast.Constant(None)))
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("sorted", "tuple") and len(node.args) == 1:
            emit(f"{node.func.id}() -> list()", node, lambda n, _f: setattr(n, "func", ast.Name("list", ast.Load())))
    return out


def _run_tests(root: pathlib.Path, tests: list[str], boundary: ca.Boundary) -> tuple[bool, int]:
    """(every kill test passed, processes the runner had to signal). Each run is a process range (WP-4.2): a timeout
    takes down the whole tree it started, not only the direct child (P2-RESIDUAL-ORPHAN-SUBJECT: leaked harness
    processes had skewed every later measurement). A mutant of the range code can break that containment — its tests
    run the mutated code — so a range that will not empty, or that something escaped, fails the run and is cleaned up
    here. P4-FINDING-011: what the range REPORTS (members, escapees, its group) is never permission; only
    `cleanup_authority` decides what is signalled, from its own reading of the host, and a candidate it cannot prove
    the runner's is RESIDUAL_OWNERSHIP_UNKNOWN — left alone, and the target fails."""
    from aisef2.runtime.process_range import ProcessRange
    from aisef2.runtime.story_scope import Residual
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    leaked = 0
    for rel in tests:
        path = pathlib.PurePosixPath(rel)
        # failfast: a mutant is killed by its first failing test; the rest of the file cannot change that verdict
        cmd = [sys.executable, "-m", "unittest", "discover", "-f", "-s", str(path.parent), "-t", "tests", "-p", path.name]
        r = ProcessRange(f"kill tests {rel}", cmd, cwd=root, env=env).start()
        code = r.wait(TIMEOUT)
        escaped = [p.pid for p in r.escaped()]  # reported while their parents are alive — checked, never trusted
        try:
            r.release()
        except Residual:
            reported = [p.pid for p in r.members()] + escaped
            anchor = getattr(getattr(r, "_anchor", None), "pid", None)
            report = ca.signal_owned(boundary, pids=reported, groups=[anchor] if anchor else ())
            _CLEANUP.extend(report.signalled)
            if report.residual_ownership_unknown:
                raise ca.Unproven(f"{rel}: {report.unproven}") from None
            return False, leaked + len(report.signalled)
        if code is None:
            _TIMED_OUT.append(rel)  # a kill by timeout is a kill, and the record says so (load can cause one)
            return False, leaked
        if code != 0:
            return False, leaked
    return True, leaked


#: kill-test runs the current mutant ended by timeout (drained per mutant into its result)
_TIMED_OUT: list[str] = []
#: every signal the runner sent for the current mutant, each with the authority's proof (drained into its result)
_CLEANUP: list[dict] = []


def _reap_strays(work: pathlib.Path, boundary: ca.Boundary) -> int:
    """Signal, by group, every process still running from the mutated tree after its kill tests, and count them (the
    count also carries what a broken range left behind, see `_run_tests`). A mutant of the range code can break the
    very containment its tests rely on (a mutated anchor that leaves its group and ignores EOF outlived a P4 run and
    spun for 40 minutes, skewing every later timeout). Candidates come from the authority's own host table, and each is
    signalled only with its proof (P4-FINDING-011); one it cannot prove is RESIDUAL_OWNERSHIP_UNKNOWN. POSIX: on
    Windows the kill tests' own ranges are jobs with no breakaway."""
    if os.name != "posix":
        return 0
    found = ca.strays(boundary)
    report = ca.signal_owned(boundary, pids=[p.pid for p in found], groups=sorted({p.pgid for p in found}))
    _CLEANUP.extend(report.signalled)
    if report.residual_ownership_unknown:
        raise ca.Unproven(f"strays of {work}: {report.unproven}")
    return len(report.signalled)


def run_target(root: pathlib.Path, target: str, tests: list[str]) -> dict:
    rel, func = target.split("::")
    with tempfile.TemporaryDirectory() as t:
        work = pathlib.Path(t) / "tree"
        for part in COPY:
            src = root / part
            if src.is_dir():
                shutil.copytree(src, work / part, ignore=shutil.ignore_patterns("__pycache__"))
            elif src.exists():
                (work / part).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, work / part)
        path = work / rel
        original = path.read_text(encoding="utf-8")
        boundary = ca.establish(work)  # P4-FINDING-011: the runner's own ownership boundary, before any worker
        try:
            clean, leaked = _run_tests(work, tests, boundary)
        except ca.Unproven as e:
            return {"target": target, "error": f"{ca.RESIDUAL_OWNERSHIP_UNKNOWN}: {e}", "mutants": []}
        if not clean or leaked:
            return {"target": target, "error": f"kill tests fail on the unmutated tree (leaked {leaked})",
                    "mutants": []}
        results = []
        for desc, src in mutants(original, func, _enum_members(original, work)):
            path.write_text(src, encoding="utf-8")
            _TIMED_OUT.clear()
            _CLEANUP.clear()
            try:
                passes, leaked = _run_tests(work, tests, boundary)
                strays = _reap_strays(work, boundary) + leaked
            except ca.Unproven as e:
                path.write_text(original, encoding="utf-8")
                return {"target": target, "error": f"{ca.RESIDUAL_OWNERSHIP_UNKNOWN} at mutant {desc!r}: {e}",
                        "mutants": [], "cleanup": list(_CLEANUP)}
            killed = not passes
            result = {"mutant": desc, "killed": killed}
            if _TIMED_OUT:
                result["timed_out"] = list(_TIMED_OUT)  # killed by the clock, not by an assertion: named, so a
                #                                          loaded machine cannot pass off a timeout as evidence
            if strays:
                result["strays_reaped"] = strays
            if _CLEANUP:
                result["cleanup"] = list(_CLEANUP)  # each signal with the authority's proof of ownership
            results.append(result)
        path.write_text(original, encoding="utf-8")
    survivors = [r["mutant"] for r in results if not r["killed"]]
    return {"target": target, "kill_tests": tests, "source_sha256": source_digest(original),
            "mutants": len(results), "killed": len(results) - len(survivors),
            "survivors": survivors, "strays_reaped": sum(r.get("strays_reaped", 0) for r in results),
            "killed_by_timeout": sum(1 for r in results if r.get("timed_out")), "results": results}


def target_problems(t: dict, root: pathlib.Path = ROOT) -> list[str]:
    """The verdict on one target's result: unchanged since the run, mutants generated, every survivor accounted for."""
    if t.get("error"):
        return [f"{t['target']}: {t['error']}"]
    out = []
    rel = t["target"].split("::")[0]
    if source_digest((root / rel).read_text(encoding="utf-8")) != t["source_sha256"]:
        out.append(f"{t['target']}: target changed since the mutation run — re-run it")
    if t["mutants"] == 0:
        out.append(f"{t['target']}: no mutants generated — a run that cannot say NO proves nothing")
    for m in t["survivors"]:
        if t["target"] in NO_AUDIT:
            out.append(f"{t['target']}: survivor {m!r} (must be fully killed; audits not accepted)")
        elif (t["target"], m) not in AUDITED:
            out.append(f"{t['target']}: unaudited survivor {m!r}")
    return out


def phase_of(target: str) -> str:
    return next(ph for ph, targets in PHASE_TARGETS.items() if target in targets)


def superseded(record: dict, phase: str) -> list[str]:
    """The targets of `record` (phase `phase`) that a later phase took over: historical entries, never re-checked."""
    return [t["target"] for t in record["targets"] if SUPERSEDED.get(t["target"], phase) != phase]


def problems_of(record: dict, root: pathlib.Path = ROOT, phase: str = "P1") -> list[str]:
    old = set(superseded(record, phase))
    targets = [t for t in record["targets"] if t["target"] not in old]
    seen = {t["target"] for t in targets}
    out = [f"{t} has no mutation result" for t in PHASE_TARGETS[phase] if t not in seen]
    out += [f"{t} belongs to {phase_of(t)}, not {phase}" for t in seen if t in TARGETS and phase_of(t) != phase]
    return out + [p for t in targets for p in target_problems(t, root)]


def check(root: pathlib.Path = ROOT) -> list[str]:
    out = []
    for phase, rel in RECORDS.items():
        if not PHASE_TARGETS[phase]:
            continue
        path = root / rel
        out += problems_of(json.loads(path.read_text(encoding="utf-8")), root, phase) if path.exists() \
            else [f"{rel} is missing"]
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["run"]:
        chosen = argv[1:] or list(TARGETS)
        for phase, rel in RECORDS.items():
            mine = [t for t in chosen if t in PHASE_TARGETS[phase]]
            if not mine:
                continue
            out = ROOT / rel
            record = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {
                "record": f"AISEF V2 — {phase} MUTATION", "tool": "validation/v2/mutation.py", "targets": []}
            kept = [t for t in record["targets"] if t["target"] not in mine and t["target"] in PHASE_TARGETS[phase]]
            fresh = []
            for target in mine:  # the record is written after every target: a run that dies keeps what it measured
                t = run_target(ROOT, target, TARGETS[target])
                fresh.append(t)
                record["targets"] = sorted(kept + fresh, key=lambda x: x["target"])
                out.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
                print(f"{t['target']}: {t.get('killed')}/{t.get('mutants')} killed; survivors {t.get('survivors')}"
                      + (f" ERROR {t['error']}" if t.get("error") else ""), flush=True)
        unknown = [t for t in chosen if t not in TARGETS]
        if unknown:
            raise SystemExit(f"not a mutation target: {unknown}")
    problems = check()
    for phase, rel in RECORDS.items():
        if (ROOT / rel).exists():
            for t in superseded(json.loads((ROOT / rel).read_text(encoding="utf-8")), phase):
                print(f"SUPERSEDED  {phase} {t}: historical, taken over by {SUPERSEDED[t]}")
    for p in problems:
        print(f"FAIL  {p}")
    print("mutation: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
