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
    python -P validation/v2/mutation.py run --order TABLE.json target ...     # each chain in the table's order (§7.2;
                                                                              # TABLE from validation/v2/execution_order.py)
    python -P validation/v2/mutation.py --check            # every phase record current, every target killed or audited
"""

from __future__ import annotations

import ast
import contextlib
import copy
import filecmp
import hashlib
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time

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
#: the unmutated baseline. V2.1: tests/v2/test_v21_continue_integrity.py takes 257 s idle (real runs SIGKILLed at
#: synchronisation points), so 300 s would time out its baseline under the campaign's load; 900 s is about 3x it.
#: A kill by timeout is still named in the record, and the merge tools refuse a clock-only kill.
TIMEOUT = 900

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
for _t in ("aisef2/probe/cli_invocation.py::AGENT/op_invoke", "aisef2/probe/python_callable_v2.py::_watch",
           "aisef2/probe/python_callable_v2.py::_concluded", "aisef2/probe/python_callable_v2.py::_harness_argv",
           "aisef2/orchestrate/workspace.py::config_problems", "aisef2/probe/cli_invocation.py::AGENT/plain",
           "aisef2/probe/cli_invocation.py::AGENT/guarded", "aisef2/app/run.py::admit", "aisef2/app/run.py::check_git",
           "aisef2/app/run.py::check_repository", "aisef2/app/run.py::probe_interpreter", "aisef2/app/run.py::runspec_of",
           "aisef2/app/run.py::productproof", "aisef2/app/run.py::delivery", "aisef2/app/run.py::execute",
           "aisef2/app/verify.py::verify", "aisef2/app/client.py::read_session", "aisef2/app/client.py::Budget.__init__",
           "aisef2/app/client.py::Budget.spend", "aisef2/app/client.py::Budget.reached", "aisef2/app/client.py::environment",
           "aisef2/app/settings.py::load", "aisef2/app/settings.py::_count",
           "aisef2/app/bundle.py::load", "aisef2/app/client.py::session", "aisef2/app/cli.py::run",
           "aisef2/app/preflight.py::accounting", "aisef2/app/adapters.py::Developer.implement",
           "aisef2/app/adapters.py::Reviewer.review", "aisef2/app/preflight.py::run",
           "aisef2/app/preflight.py::fingerprint_fields"):
    S2_TARGETS[_t] = [*S2_TARGETS[_t], _S2_KILLS]
for _t in ("aisef2/probe/process_effect.py::HARNESS/ask",    # killed only by the clock: its bounded case runs first
           "aisef2/probe/cli_invocation.py::AGENT/send", "aisef2/app/client.py::wait_within"):
    S2_TARGETS[_t] = [_S2_KILLS, *S2_TARGETS[_t]]
# Final round K's findings, in a file of their own for the same reason (tests/v2/test_s2_kills_k.py says why each).
_S2_KILLS_K = "tests/v2/test_s2_kills_k.py"
for _t in ("aisef2/app/client.py::wait_within", "aisef2/probe/cli_invocation.py::AGENT/send"):
    S2_TARGETS[_t] = [_S2_KILLS_K, *S2_TARGETS[_t]]
S2_TARGETS["aisef2/app/bundle.py::Project.order"] = [*S2_TARGETS["aisef2/app/bundle.py::Project.order"], _S2_KILLS_K]
# OBS-S2-12: kills that hold whatever the string-hash seed, first in exactly these two kill sets (owner, 2026-10-05).
_S2_KILLS_DET = "tests/v2/test_s2_kills_deterministic.py"
for _t in ("aisef2/app/preflight.py::fingerprint_fields", "aisef2/app/client.py::Budget.spend"):
    S2_TARGETS[_t] = [_S2_KILLS_DET, *S2_TARGETS[_t]]
# RC2 (S6-SMOKE-1-PREFLIGHT-OPAQUE, owner 2026-10-05): the preflight's failure provenance, killed in a file of its own,
# first in exactly the kill sets of the two targets whose code the fix changed.
_S2_KILLS_RC2 = "tests/v2/test_s2_kills_rc2.py"
for _t in ("aisef2/app/preflight.py::run", "aisef2/app/preflight.py::identity_problems"):
    S2_TARGETS[_t] = [_S2_KILLS_RC2, *S2_TARGETS[_t]]
SUPERSEDED.update({t: "V2.0-S2" for t in S2_TARGETS})
for _phase in (K_NOWORK_TARGETS, P6_TARGETS, C2P2_TARGETS, C2P3_TARGETS, C2_P4_TARGETS):
    for _t in [t for t in _phase if t.split("::")[0] in (*_S2_CHANGED, "aisef2/orchestrate/story_runner.py",
                                                          "aisef2/probe/cli_invocation.py", "aisef2/probe/process_effect.py",
                                                          "aisef2/probe/python_callable_v2.py")]:
        SUPERSEDED.setdefault(_t, "V2.0-S2")
        del _phase[_t]
RECORDS["V2.0-S2"] = "closure-evidence/v2/release/S2-MUTATION.json"
# V2.1 REQUALIFICATION ROUND, B-03b (owner directive 2026-10-06, closure-evidence/v2/cycle2/RELEASE-DECISIONS.json
# seq 5). Every target of a module 2.1 changed is re-measured (the digest is whole-file), its kill set the earlier one
# with the 2.1 regression files after its first file; the new 2.1 modules (lineage, usage, review_ocr, review_verify,
# bundle_cli) and the names 2.1 added or changed in other modules are new targets. Not a target: names with no mutant,
# and aisef2/app/calibrations.py::CALIBRATIONS — generated data (validation/qualification/release_calibration.py
# rewrites it), proven by its calibration record and check 9, not by mutating its rows. S2_TARGETS stays whole (its
# record's reuse proof and criteria read it); the V2.0-S2 phase keeps only what V2.1 does not take over.
#: the semantic identity tests; tests/v2/test_v21_identity_bytes.py holds the byte/text-identity tests and is never a kill
#: file (ORD-1: they fail the null mutant of the modules they read — docs/v2.1/MUTATION-RUNNER-V2.md §6)
_V21_ID = "tests/v2/test_v21_identity.py"
_V21_REG = {
    "aisef2/plan/static_admission.py": [_V21_ID], "aisef2/probe/calibration.py": [_V21_ID],
    "aisef2/orchestrate/review.py": ["tests/v2/test_v21_review.py"],
    "aisef2/probe/file_artifact.py": ["tests/v2/test_v21_python_imports.py", _V21_ID],
    **{f"aisef2/probe/{p}.py": [_V21_ID] for p in ("cli_invocation", "process_effect", "python_callable_v2")},
    **{f"aisef2/orchestrate/{m}.py": ["tests/v2/test_v21_orchestration.py"] for m in ("story_runner", "workspace", "adapters")},
    "aisef2/app/adapters.py": [_V21_ID, "tests/v2/test_v21_review_chain.py"],
    "aisef2/app/bundle.py": ["tests/v2/test_v21_inputs.py", _V21_ID, "tests/v2/test_v21_review.py",
                             "tests/v2/test_v21_bundle_tools.py", "tests/v2/test_v21_continue_usage.py",
                             "tests/v2/test_v21_review_chain.py", "tests/v2/test_v21_continue_integrity.py"],
    "aisef2/app/cli.py": ["tests/v2/test_v21_inputs.py", "tests/v2/test_v21_bundle_tools.py",
                          "tests/v2/test_v21_continue_integrity.py"],
    "aisef2/app/client.py": ["tests/v2/test_v21_transport.py"],
    "aisef2/app/preflight.py": ["tests/v2/test_v21_transport.py", _V21_ID],
    "aisef2/app/run.py": ["tests/v2/test_v21_inputs.py", _V21_ID, "tests/v2/test_v21_verify.py",
                          "tests/v2/test_v21_continue_usage.py", "tests/v2/test_v21_review_chain.py",
                          "tests/v2/test_v21_continue_integrity.py"],
    "aisef2/app/settings.py": ["tests/v2/test_v21_inputs.py", _V21_ID, "tests/v2/test_v21_review.py",
                               "tests/v2/test_v21_verify.py", "tests/v2/test_v21_continue_usage.py",
                               "tests/v2/test_v21_review_chain.py", "tests/v2/test_v21_continue_integrity.py"],
    "aisef2/app/verify.py": ["tests/v2/test_v21_verify.py", "tests/v2/test_v21_continue_usage.py",
                             "tests/v2/test_v21_continue_integrity.py"],
    "aisef2/app/feedback.py": ["tests/v2/test_v21_review_chain.py"],
}


def _v21_kill(module: str, kill: list[str]) -> list[str]:
    """`kill` with the module's 2.1 regression files after its first file (each file once)."""
    return list(dict.fromkeys([kill[0], *_V21_REG.get(module, []), *kill[1:]]))


V21_TARGETS: dict[str, list[str]] = {
    t: _v21_kill(t.split("::")[0], k) for phase in (P2_TARGETS, P6_TARGETS, C2_P1_TARGETS, S2_TARGETS)
    for t, k in phase.items() if t.split("::")[0] in _V21_REG}
_V21_NEW = {
    "aisef2/app/lineage.py": (["tests/v2/test_v21_continue_usage.py", "tests/v2/test_v21_continue_integrity.py"], (
        "JOURNAL", "SPEND", "_sha", "claims", "events_of", "child_state", "process_started", "claimant", "_gone", "claim",
        "continued_by", "_git", "reconcile", "account_of", "predecessor_of", "lineage_account", "usage_lineage",
        "ANCHOR_LINE", "write_anchor", "read_anchor")),
    "aisef2/app/usage.py": (["tests/v2/test_v21_continue_usage.py", "tests/v2/test_v21_verify.py",
                             "tests/v2/test_v21_continue_integrity.py"], (
        "PRICE_KEYS", "CLASSES", "_DATE", "price_problem", "session_tokens", "_usd", "usage", "no_progress")),
    "aisef2/app/review_ocr.py": (["tests/v2/test_v21_review_ocr.py", "tests/v2/test_v21_review_chain.py"], (
        "OCR", "TERMINAL", "NOT_FULL", "SCRUB_PREFIXES", "NOT_REVIEWABLE", "REPRODUCER_FENCE", "item_id", "finding_id",
        "coverage", "findings", "reproducer_of", "environment", "argv", "pinned", "read_output", "scrubbed_names")),
    "aisef2/app/review_verify.py": (["tests/v2/test_v21_review.py", "tests/v2/test_v21_review_ocr.py",
                                     "tests/v2/test_v21_review_chain.py"], (
        "SEVERITIES", "POLICIES", "REPRODUCER_KEYS", "Verification.evidence", "severity_of", "reproducer_contract",
        "verify", "_canon", "_stimulus", "_scalars", "_NUMBER", "_states", "_approved_by_clause", "anchor", "blocks",
        "detail")),
    "aisef2/app/bundle_cli.py": (["tests/v2/test_v21_bundle_tools.py", _V21_ID, "tests/v2/test_v21_review.py",
                                  "tests/v2/test_v21_continue_usage.py", "tests/v2/test_v21_continue_integrity.py"], (
        "AUTHORING_KEYS", "CONTRACT_KEYS", "CRITERION_KEYS", "EXAMPLES", "RELEASES", "_earlier", "migrate", "_mint",
        "_refs", "_closed", "seal", "unapproved", "approve", "_spec_rows", "coverage", "lint", "explain", "init",
        "continue_from", "_read", "_write_new", "_create", "main")),
    # V2.1 (F, v21p/sandbox 9c36070): the sessions' bubblewrap confinement. Not targets: HOME, MARK, PROBE and
    # SURVIVOR_GRACE (no mutant), PROBE_TIMEOUT and SLEEPER (one tuple assignment: _root resolves a single name only)
    "aisef2/app/confine.py": (["tests/v2/test_v21_confine.py"], (
        "KEYS", "NETWORKS", "SYSTEM", "USERNS_REFUSED", "problem", "git_dir", "config_dir", "argv", "wrap", "_sections",
        "_mounts", "targets", "_worktree", "measure", "_probe", "_survivors", "namespaces", "_link", "_within", "_judge")),
    # names 2.1 added, or whose body 2.1 changed, in modules that already had targets (or none, feedback.py)
    **{f"aisef2/app/{m}.py": (["tests/v2/test_app_units.py", *_V21_REG[f"aisef2/app/{m}.py"], "tests/v2/test_app_run.py"], fs)
       for m, fs in (("adapters", ("Reviewer._model", "Reviewer._ocr", "Reviewer._verify", "tree_of", "_unchanged",
                                   "_bounded", "Reviewer.__init__")),
                     ("bundle", ("_HEX64", "_strings", "shape_problems", "read")),
                     ("run", ("layers_of", "outcomes_from", "unfinished", "_content_sha", "evidence_manifest",
                              "anchor_in", "anchor_of", "client_on_path")),
                     ("settings", ("OPTIONAL", "REVIEW_ABSENT", "FINDERS", "OCR_KEYS", "LOOPBACK", "endpoint_problem",
                                   "Settings.prices", "read")),
                     ("verify", ("_runspec_problems", "_spend")),
                     ("cli", ("_parser",)), ("client", ("Budget.account", "redact")), ("preflight", ("http_transport",)),
                     ("feedback", ("retry_feedback", "context_pack")))},
}
for _m, (_kill, _names) in _V21_NEW.items():
    V21_TARGETS.update({f"{_m}::{n}": list(_kill) for n in _names})
V21_TARGETS.update({
    "aisef2/probe/calibration.py::executing": ["tests/v2/p2/test_calibration.py", _V21_ID],
    "aisef2/probe/calibration.py::calibration_for": ["tests/v2/p2/test_calibration.py", _V21_ID],
    **{f"aisef2/probe/file_artifact.py::{n}": [*_V21_REG["aisef2/probe/file_artifact.py"], *_FILE_ARTIFACT_TESTS]
       for n in ("_MODULE_NAME", "import_facts", "DIGEST")},
    # B-01 (ARCHITECTURE-EXCEPTION-V2-007): the capability digest, sha256 of [PROBE_ID, CAPABILITY_VERSION, CLASSES]
    "aisef2/probe/cli_invocation.py::DIGEST": [_V21_ID, "tests/v2/test_c2_cli_calibration.py"],
    "aisef2/probe/process_effect.py::DIGEST": [_V21_ID, "tests/v2/test_probe_process_effect_units.py"],  # not
    # test_c2_effect_calibration.py: it imports validation/qualification, which the mutation copy does not hold (preflight)
    "aisef2/probe/python_callable_v2.py::DIGEST": [_V21_ID, *_C2_P4_TESTS],
})
# campaign 1's survivors (closure-evidence/v2/v2.1/campaign-1-stopped), then campaign 2's (runner v2 at 5719f1f):
# each target's own kill file, appended last
_V21_KILLS = {**{f"aisef2/app/adapters.py::{n}": "tests/v2/test_v21_kills_adapters.py"
                 for n in ("Reviewer._model", "Reviewer._verify", "Reviewer.__init__", "Reviewer.review", "_unchanged",
                           "tree_of")},
              **{f"aisef2/app/bundle.py::{n}": "tests/v2/test_v21_kills_bundle.py" for n in ("_strings", "read")},
              **{f"aisef2/app/bundle_cli.py::{n}": "tests/v2/test_v21_kills_bundle_cli.py" for n in ("coverage", "init")},
              "aisef2/app/cli.py::_parser": "tests/v2/test_v21_kills_cli.py",
              "aisef2/app/settings.py::endpoint_problem": "tests/v2/test_v21_kills_settings.py",
              "aisef2/app/usage.py::no_progress": "tests/v2/test_v21_kills_usage.py",
              "aisef2/app/lineage.py::claims": "tests/v2/test_v21_kills_lineage.py"}
for _t, _f in _V21_KILLS.items():
    V21_TARGETS[_t] = [*V21_TARGETS[_t], _f]
# the 2.1 product tracks merged for campaign 2 (owner decision B-03b: the new 2.1 modules are targets): each track's own
# test file, appended last, for the names it added to a module that already had targets and for the V2.1 targets whose
# body it changed and whose new behaviour that file tests. D4 (v21p/context 01e8aef): not targets, PACK_HEAD (no
# mutant) and PACK_MAX, PACK_LIST, PACK_ATTEMPTS (one tuple assignment). v21p/trace changes nothing under aisef2/.
_V21_TRACKS = {**{f"aisef2/app/{t}": "tests/v2/test_v21_confine.py"
                  for t in ("cli.py::run", "client.py::session", "run.py::execute", "run.py::client_on_path",
                            "settings.py::OPTIONAL", "settings.py::load")},
               **{f"aisef2/app/{t}": "tests/v2/test_v21_context_pack.py"
                  for t in ("adapters.py::Developer.implement", "feedback.py::context_pack")}}
for _t, _f in _V21_TRACKS.items():
    V21_TARGETS[_t] = [*V21_TARGETS[_t], _f]
SUPERSEDED.update({t: "V2.1" for t in V21_TARGETS})
for _phase in (P2_TARGETS, P6_TARGETS, C2_P1_TARGETS):
    for _t in [t for t in _phase if t in V21_TARGETS]:
        del _phase[_t]
RECORDS["V2.1"] = "closure-evidence/v2/v2.1/MUTATION.json"
PHASE_TARGETS = {"P1": P1_TARGETS, "P2": P2_TARGETS, "P3": P3_TARGETS, "P4": P4_TARGETS, "P5": P5_TARGETS,
                 "P6": P6_TARGETS, "C2-P1": C2_P1_TARGETS, "C2-P2": C2P2_TARGETS, "C2-P3": C2P3_TARGETS, "C2-P4": C2_P4_TARGETS,
                 "C2-ORCH": C2_ORCH_TARGETS, "C2-P10": C2_P10_TARGETS, "K-PRESAT-001": K_PRESAT_TARGETS,
                 "K-NOWORK-001": K_NOWORK_TARGETS, "V2.0-S2": {t: k for t, k in S2_TARGETS.items() if t not in V21_TARGETS},
                 "V2.1": V21_TARGETS}
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
#: Audits that name the mutant by its position (B-03, survivors of campaign 2). A description is not an identity: the
#: same line is mutated at each of its occurrences, so one description can be two mutants, one of them killable. An entry
#: is `{target, index, mutant, class, source_sha256, group, grounds, consumers_checked, exceptions_checked}` and counts
#: only for that position of that target's mutant list, at the module's digest it was written for, and only for a
#: SURVIVED mutant. `EQUIVALENT`: no observable difference, proved from the code. `AUDITED`: it differs, and no consumer
#: or contract the entry names depends on it. Neither is a kill, and the record keeps them apart from KILLED.
AUDITS_REL = "closure-evidence/v2/v2.1/mutation/SURVIVOR-AUDITS.json"
AUDIT_CLASSES = ("EQUIVALENT", "AUDITED")


def _audit_entry_problem(e) -> str | None:
    if not isinstance(e, dict):
        return "not an object"
    for k, kind in (("target", str), ("mutant", str), ("class", str), ("group", str), ("grounds", str)):
        if not isinstance(e.get(k), kind) or not e[k].strip():
            return f"{k} is missing or empty"
    if not isinstance(e.get("index"), int) or isinstance(e.get("index"), bool) or e["index"] < 0:
        return "index is not a position"
    if e["class"] not in AUDIT_CLASSES:
        return f"class {e['class']!r} is neither of {AUDIT_CLASSES}"
    if not _SHA256.fullmatch(str(e.get("source_sha256"))):
        return "source_sha256 is not a digest"
    for k in ("consumers_checked", "exceptions_checked"):
        v = e.get(k)
        if not isinstance(v, list) or not v or not all(isinstance(x, str) and x.strip() for x in v):
            return f"{k} is missing, empty or not a list of text"
    return None


_AUDITS_CACHE: dict[tuple[str, int, int], tuple[dict, list[str]]] = {}


def audits_at(root: pathlib.Path = ROOT) -> tuple[dict[tuple[str, int, str], dict], list[str]]:
    """The positional audits of the tree at `root` (AUDITS_REL): ({(target, index, mutant): entry}, problems). A
    malformed entry, a repeated position or a file that is not an object with `entries` is a problem and counts for
    nothing; no file is no audits and no problem."""
    path = root / AUDITS_REL
    try:
        st = path.stat()
    except OSError:
        return {}, []
    key = (str(path), st.st_mtime_ns, st.st_size)
    if key in _AUDITS_CACHE:
        return _AUDITS_CACHE[key]
    found: dict[tuple[str, int, str], dict] = {}
    problems: list[str] = []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        entries = doc["entries"] if isinstance(doc, dict) else None
        if not isinstance(entries, list):
            raise ValueError("no `entries` list")
    except (OSError, ValueError, KeyError) as exc:
        out = ({}, [f"{AUDITS_REL}: unreadable: {exc}"])
        _AUDITS_CACHE[key] = out
        return out
    for n, e in enumerate(entries):
        why = _audit_entry_problem(e)
        if why:
            problems.append(f"{AUDITS_REL}: entry {n}: {why}")
            continue
        k = (e["target"], e["index"], e["mutant"])
        if k in found:
            problems.append(f"{AUDITS_REL}: entry {n}: {k[0]} [{k[1]}] is audited twice")
            continue
        found[k] = e
    _AUDITS_CACHE.clear()
    _AUDITS_CACHE[key] = (found, problems)
    return found, problems


def audit_of(root: pathlib.Path, target: str, index: int, mutant: str, source_sha256: str | None) -> dict | None:
    """The positional audit that covers mutant `index` of `target` (description `mutant`) in a result measured on a
    module with digest `source_sha256`, or None. The V2.0 entries of AUDITED are by description, and read as before."""
    e = audits_at(root)[0].get((target, index, mutant))
    return e if e is not None and e["source_sha256"] == source_sha256 and target not in NO_AUDIT else None


#: What a run copies into its scratch tree.
COPY = ("aisef2", "tests/v2", "validation/v2", "docs/architecture", "docs/implementation/v2", "closure-evidence/v2",
        "docs/v2.1",   # the bundle-authoring schema and the S-10-a drafts two V2.1 kill files read
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


def _write_version(path: pathlib.Path, src: str, last: int) -> int:
    """Write one version of the mutated file with a whole-second mtime strictly above every earlier version's (BC-1).
    A timestamp .pyc is accepted when (int mtime, size) match its header, so two versions of one size written in one
    second share a .pyc, and the second runs the first one's code: whichever process wrote it (`-I` children ignore
    PYTHONDONTWRITEBYTECODE and PYTHONPYCACHEPREFIX) and wherever it lives (BC-2, BC-4). With a stamp no earlier version
    had, no cached .pyc of another version can be accepted. Stamps may run ahead of the clock by about a second per
    fast mutant; no aisef2 code and no kill test reads the mutated module's mtime (BC-1 verifier)."""
    path.write_text(src, encoding="utf-8")
    stamp = max(last + 1, int(time.time()))
    os.utime(path, (stamp, stamp))
    return stamp


#: The kill-test environment is an allowlist (§2.2): the worker env's keys and, on Windows, what Python needs to start
#: there; an operator shell's PYTHON* variables never reach a kill test, so a run from a shell and one from a worker
#: are the same. HOME, TMPDIR and XDG_* are fresh directories of each run, removed after it (FS-1, FS-3, ORD-5, PL-8).
ENV_KEEP = ("PATH", "LANG", "USER", "LOGNAME", "SYSTEMROOT", "SystemRoot", "WINDIR")
_FRESH = {"HOME": "home", "TMPDIR": "tmp", "XDG_CONFIG_HOME": "config", "XDG_DATA_HOME": "data", "XDG_STATE_HOME": "state",
          "XDG_CACHE_HOME": "cache", **({"USERPROFILE": "home", "TEMP": "tmp", "TMP": "tmp"} if os.name == "nt" else {})}
#: every kill-file run carries `AISEF_MUTATION_RUN=<worker>:<run>`: how a detached leftover that names no tree is found
#: (PL-1) — a candidate, never proof (a child given its own environment does not carry it)
TOKEN = "AISEF_MUTATION_RUN"
#: an unproven leftover is watched this long for its own exit, never signalled (PL-7); still alive after it, the target
#: and the worker stop. Long enough for a short-lived helper to end by itself — the 8 s detached sleep of
#: test_v21_continue_integrity.py, or ORD-7's 30 s escapee — since in an order that never reaches its file the same
#: target is classified, so a stop here is an order-dependent fate (ORD-7); paid only while something is left running
SETTLE_S = 60.0


class _Stop(ca.Unproven):
    """The target and the worker stop: a leftover the authority cannot prove (RESIDUAL_OWNERSHIP_UNKNOWN), or a host
    table that cannot be read. `leaked` names what was found."""

    def __init__(self, why: str, leaked: list | None = None):
        super().__init__(why)
        self.code, _, self.detail = why.partition(": ")
        self.leaked = leaked or []


class _Target:
    """One target's working state: its scratch directory (trees, run directories — never inside a tree), the ownership
    boundary, the tree and its base manifest, the version of the mutated file in it and its stamp, the run counter, the
    kill set (declared order: T0's) and the order a mutant's chain runs it in, the unmutated module the bracket's
    control runs on, and T0's reference per file. A plain class, not a dataclass: callers load this module by path
    without a sys.modules entry (p2, p4 tests)."""

    def __init__(self, rel, scratch, boundary, worker, tree=None, pristine=None, tests=(), last=0, order=None):
        self.rel, self.scratch, self.boundary, self.worker, self.tree = rel, scratch, boundary, worker, tree
        self.pristine, self.tests, self.last = pristine, list(tests), last   # pristine None: the caller's own tree
        self.order = list(order or tests)   # a permutation of `tests` (run_target checks it); default: declared order
        self.holder = self.base = self.version = self.null = None
        self.seq, self.ref = 0, {}   # ref: file -> T0's {"ref": [counts, skipped tests], "first_test"}


def _worker(root: pathlib.Path) -> str:
    """A stable name of the worker that runs from `root`: a restarted worker finds what an earlier run of it left (PL-3)."""
    return hashlib.sha256(str(pathlib.Path(root).resolve()).encode()).hexdigest()[:12]


def _pristine(root: pathlib.Path, dst: pathlib.Path) -> tuple[pathlib.Path, str]:
    """The COPY parts of `root`, taken once (per `main()`, before any record is written) with `__pycache__` and the
    runner's own record files left out — by exact path, never a name pattern — so a live record never enters a tree
    (FS-4); and the tree's digest: sha256 over the sorted (path, sha256 of bytes) pairs, no mtimes."""
    records = {os.path.normpath(root / r) for r in RECORDS.values()}

    def skip(d, names):
        return [n for n in names if n == "__pycache__" or os.path.normpath(os.path.join(d, n)) in records]
    for part in COPY:
        src = root / part
        if src.is_dir():
            shutil.copytree(src, dst / part, ignore=skip)
        elif src.exists() and os.path.normpath(src) not in records:
            (dst / part).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst / part)
    h = hashlib.sha256()
    for p in sorted(x for x in dst.rglob("*") if x.is_file()):
        h.update(p.relative_to(dst).as_posix().encode() + b"\0" + hashlib.sha256(p.read_bytes()).digest())
    return dst, h.hexdigest()


def _manifest(tree: pathlib.Path, skip: str | None) -> dict[str, tuple]:
    """relpath -> ("d", mode) for a directory, (kind, size, mtime_ns, mode) for anything else (lstat). `__pycache__`
    subtrees are left out (bytecode is `_write_version`'s); so is the mutated file, checked by its bytes. Directory
    mtimes are never compared: creating `__pycache__` changes them (FS-1 verifier (c))."""
    out = {}
    for d, dirs, files in os.walk(tree):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for x in dirs + files:
            rel = pathlib.Path(os.path.relpath(os.path.join(d, x), tree)).as_posix()
            st = os.lstat(os.path.join(d, x))
            if stat.S_ISDIR(st.st_mode):
                out[rel] = ("d", st.st_mode)
            elif rel != skip:
                out[rel] = ("l" if stat.S_ISLNK(st.st_mode) else "f", st.st_size, st.st_mtime_ns, st.st_mode)
    return out


def _write(tg: _Target, src: str) -> None:
    tg.version, tg.last = src, _write_version(tg.tree / tg.rel, src, tg.last)


def _new_tree(tg: _Target) -> None:
    """A fresh tree from the pristine copy, the version under test written into it (stamped), its base manifest taken;
    the old tree is removed (its own TemporaryDirectory). The boundary names the scratch directory, which holds every
    tree, so it does not move."""
    holder = tempfile.TemporaryDirectory(dir=tg.scratch, prefix="tree-", ignore_cleanup_errors=True)
    tree = pathlib.Path(holder.name) / "tree"
    shutil.copytree(tg.pristine, tree)
    old, tg.holder, tg.tree = tg.holder, holder, tree
    if tg.version is not None:
        _write(tg, tg.version)
    tg.base = _manifest(tree, tg.rel)
    if old is not None:
        old.cleanup()


def _residue(tg: _Target) -> dict:
    """What a run left in the tree: paths added or removed, and paths whose type, mode or content changed (a file only
    touched, or rewritten with its own bytes, is not residue — except a `.py` source, whose mtime is half of what its
    cached bytecode is checked against); the mutated file must still hold the version under test, with its stamp.
    Empty when the tree is the pristine copy plus that version."""
    now = _manifest(tg.tree, tg.rel)
    base = tg.base

    def same(k):
        a, b = now[k], base[k]
        if a[0] != b[0] or a[-1] != b[-1] or a[0] == "d":
            return a == b
        if a[0] == "l":
            return os.readlink(tg.tree / k) == os.readlink(tg.pristine / k)
        if k.endswith(".py") and a[2] != b[2]:   # a source touched in place: a .pyc of other bytes can match it again
            return False
        return filecmp.cmp(tg.tree / k, tg.pristine / k, shallow=False)
    added, removed = sorted(set(now) - set(base)), sorted(set(base) - set(now))
    changed = sorted(k for k in set(now) & set(base) if now[k] != base[k] and not same(k))
    try:   # stamps are whole seconds, so any touch or rewrite of the mutated file shows in its mtime (BC-1 lens)
        held = (tg.tree / tg.rel).read_text(encoding="utf-8") == tg.version and \
            (tg.tree / tg.rel).stat().st_mtime_ns == tg.last * 10**9
    except (OSError, UnicodeDecodeError):
        held = False
    changed += [] if held else [tg.rel]
    # the cwd is the tree, so '../x' and '../../x' are reachable too: the tree's holder must hold only the tree, and the
    # target's scratch only that holder and its own pristine copy (filesystem-state lens: residue beside the tree)
    beside = sorted(set(os.listdir(tg.tree.parent)) - {"tree"})
    scratch = sorted(set(os.listdir(tg.scratch)) - {tg.tree.parent.name, *(
        [tg.pristine.name] if tg.pristine.parent == tg.scratch else [])})
    return {k: v[:50] for k, v in (("added", added), ("removed", removed), ("changed", changed), ("beside", beside),
                                   ("scratch", scratch)) if v}


def _env(run: pathlib.Path, token: str) -> dict[str, str]:
    env = {k: os.environ[k] for k in ENV_KEEP if k in os.environ}
    for k, d in _FRESH.items():
        (run / d).mkdir(exist_ok=True)
        env[k] = str(run / d)
    return {**env, TOKEN: token}


def _watch(pids) -> list[int]:
    """The pids still in the authority's host table after at most SETTLE_S, polled — nothing is signalled (PL-7)."""
    deadline = time.monotonic() + SETTLE_S
    while True:
        table = ca.host_table()
        left = [p for p in pids if p in table]
        if not left or time.monotonic() >= deadline:
            return left
        time.sleep(0.25)


def _clean(boundary: ca.Boundary, pids, groups, table=None) -> ca.Report:
    """Signal what the authority proves the runner's (the only signal path: INV-MUTATION-AUTHORITY), then watch every
    pid named, signalled or not, until it is gone; one still alive after SETTLE_S stops the target and the worker."""
    try:
        report = ca.signal_owned(boundary, pids=pids, groups=groups, table=table)
        left = _watch(pids)
    except OSError as e:
        raise _Stop(f"HOST_TABLE_UNREADABLE: {e}") from None
    if left:
        raise _Stop(f"{ca.RESIDUAL_OWNERSHIP_UNKNOWN}: alive after {SETTLE_S}s: {left}; unproven {report.unproven}")
    return report


def _leftovers(tg: _Target, table: dict) -> dict[int, ca.Host]:
    """What this worker left running: processes carrying its token (PL-1), naming the target's scratch directory, which
    holds its trees and run directories (`ca.strays`; the union keeps command-line matching, since code under mutation
    builds scrubbed environments — PL-6 verifier), or working inside it (`ca.cwd_under`: a helper given its own
    environment and no scratch path still has the cwd it inherited — PL-1 (3), process-env prover). Candidates only."""
    found = {p.pid: p for p in ca.strays(tg.boundary, table)}
    found.update((p.pid, p) for p in ca.carriers(f"{TOKEN}={tg.worker}:", table))
    found.update((p.pid, p) for p in ca.cwd_under(tg.boundary.root + os.sep, table, tg.boundary.since))
    return found


def _settle(tg: _Target) -> tuple[list[dict], list[dict]]:
    """(leaked, cleanup) after a run: every leftover, signalled only with the authority's proof, the rest watched for
    their own exit; `_Stop` when one outlives SETTLE_S. POSIX: on Windows a kill test's range is a job with no breakaway."""
    if os.name != "posix":
        return [], []
    try:
        table = ca.host_table()
        found = _leftovers(tg, table)
    except OSError as e:
        raise _Stop(f"HOST_TABLE_UNREADABLE: {e}") from None
    if not found:
        return [], []
    leaked = [{"pid": p.pid, "command": p.command[:120]} for p in found.values()]
    try:
        report = _clean(tg.boundary, sorted(found), sorted({p.pgid for p in found.values()}), table)
    except _Stop as e:
        raise _Stop(str(e), [dict(x, proved=False) for x in leaked]) from None
    proved = {s["id"] for s in report.signalled}
    return [dict(x, proved=x["pid"] in proved) for x in leaked], report.signalled


def _earlier(worker: str) -> list[int]:
    """Processes an earlier run of this worker left (its token, or one of its scratch directories in the command line),
    still alive after SETTLE_S: a restarted worker never runs beside them (PL-3 verifier (e)). Nothing is signalled:
    they were born before this run's boundary, so nothing about them can be proven."""
    if os.name != "posix":
        return []
    table = ca.host_table()
    mark = ca.Boundary(os.getpid(), 0.0, os.path.join(tempfile.gettempdir(), f"aisef-mut-{worker}-"))
    found = {p.pid for p in ca.strays(mark, table)} | {p.pid for p in ca.carriers(f"{TOKEN}={worker}:", table)} | \
        {p.pid for p in ca.cwd_under(mark.root, table)}
    return _watch(sorted(found)) if found else []


#: The release ladder's last stage is bounded at this call site (VS-7/PL-5); ProcessRange's own default (no limit) stays,
#: as tests/v2/p4 asserts it. A range still not empty after it is a residual: INFRA, never a kill. One budget per run:
#: the second release() after a RangeNotEmpty gets only what the first left of it, so a run holds its worker at most
#: TIMEOUT + RELEASE_WAIT_S + both ladders' graces (2 x 4 s) + the settle (process-env prover: it was about 2x)
RELEASE_WAIT_S = 60.0
#: the normalised output tail a non-PASS row keeps (every row keeps its sha256)
TAIL = 1500
#: the per-mutant classes (§4.1); only KILLED and SURVIVED are verdicts
CLASSES = ("KILLED", "SURVIVED", "TIMEOUT", "INFRA", "NOT_RUN")
#: test files that are part of the suite and never kill evidence: each holds only tests that fail the null mutant of
#: every target they could be a kill file for (byte and text identity, ORD-1) — the module docstring's rule, the same as
#: the compiler_digest tests'. A kill set naming one is refused.
NOT_KILL_FILES = ("tests/v2/test_v21_identity_bytes.py",)

_RAN = re.compile(r"^Ran (\d+) tests? in [\d.]+s$", re.M)
_END = re.compile(r"^(OK|FAILED)(?: \((.*)\))?$", re.M)
_HEAD = re.compile(r"^={70}\n(FAIL|ERROR|UNEXPECTED SUCCESS): (.+)$", re.M)   # a line a test prints is not the report
_TEST = re.compile(r"^(\w+) \(([\w.]+)\)", re.M)
_SKIP = re.compile(r"^ *(\S+ \([\w.]+\)(?: \[[^\n]*\]| \([^\n]*\))?)(?:\n[^\n]*)? \.\.\. skipped", re.M)


def _summary(text: str) -> dict | None:
    """unittest's own summary of a run (`-v`), read only after the LAST `Ran N tests in` line, so text a test prints
    cannot forge it: ran, status, counts, the skipped tests, the first test the run listed, and `first` — the first
    failure's signature: its whole header line (a subtest's [msg] or (params) included) and the class of the exception
    its traceback ended in. None when there is none (a crash, a signal, exit 5, os._exit)."""
    runs = list(_RAN.finditer(text))
    end = _END.search(text, runs[-1].end()) if runs else None
    if not end:
        return None
    body = text[:runs[-1].start()]
    counts = {k.strip().replace(" ", "_"): int(v) for k, v in (p.split("=", 1) for p in (end[2] or "").split(", ") if "=" in p)}
    first, head = None, _HEAD.search(body)
    if head:
        block = body[head.end():].split("\n" + "=" * 70 + "\n", 1)[0].split("Traceback (most recent call last):\n")
        exc = next((ln.split(":", 1)[0] for ln in block[-1].splitlines() if ln and not ln[0].isspace()), "") \
            if len(block) > 1 else ""
        first = f"{head[1]}: {head[2]}" + (f" | {exc}" if exc else "")
    test = next((t[2] for t in _TEST.finditer(body) if t[2].endswith("." + t[1]) and not t[2].startswith("unittest.")), None)
    return {"ran": int(runs[-1][1]), "status": end[1], **counts, "first": first,
            "skipped_tests": sorted(x[1] for x in _SKIP.finditer(body)), "first_test": test}


#: the runner's own temp names (§15): a scratch directory is `aisef-mut-<worker>-<8>` (worker: 12 hex), a run directory
#: `run-<8>` or a tree `tree-<8>` in it, a run's TMPDIR `<run>/tmp`, and a test's default mkdtemp name `tmp<8>` in that
#: (8 = tempfile's random characters). Only the run, tree and mkdtemp names are replaced, never the text around them and
#: not the scratch name (one per target: a directory of another target or worker stays a different name).
_RUNNER_DIR = re.compile(r"(?<![\w.-])(?P<scratch>aisef-mut-[0-9a-f]{12}-[a-z0-9_]{8})(?P<sep>[\\/]+)(?P<kind>run|tree)-(?P<name>[a-z0-9_]{8})(?![a-z0-9_])")
_MKDTEMP = re.compile(r"(?<!<)(?P<run><run#\d+>)(?P<sep>[\\/]+tmp[\\/]+)(?P<name>tmp[a-z0-9_]{8})(?![a-z0-9_])")   # (?<!<): not a doubled literal


def signature(first: str | None) -> str | None:
    """What the bracket compares (§15): the failure's `first` — header line and exception class — with the runner's own
    run, tree and mkdtemp names replaced by `<run#n>`, `<tree#n>`, `<mkdtemp#n>` (n: order of first appearance in this
    header, so which names coincide is kept) and nothing else: a path under the run's TMPDIR in a subTest label is the
    same failure on every run, while another test, subtest, parameter, exception class or directory is not. A `<` already
    in the header is doubled first, so a literal `<run#1>` is not a replaced name. A pure function of the recorded
    `first`: the record check applies it to the row as written, and the record keeps the header as the run printed it."""
    if not isinstance(first, str):
        return first
    text = first.replace("<", "<<")
    if "aisef-mut-" not in text:   # no runner name: nothing to replace, and no scan of a long header
        return text
    seen: dict[tuple[str, ...], int] = {}
    count: dict[str, int] = {}

    def number(kind: str, *name: str) -> int:   # the name, never the separators: `/` and `//` are one directory
        if (kind, *name) not in seen:
            count[kind] = count.get(kind, 0) + 1
            seen[kind, *name] = count[kind]
        return seen[kind, *name]

    text = _RUNNER_DIR.sub(lambda m_: f"{m_['scratch']}{m_['sep']}<{m_['kind']}#{number(m_['kind'], m_['scratch'], m_['name'])}>", text)
    return _MKDTEMP.sub(lambda m_: f"{m_['run']}{m_['sep']}<mkdtemp#{number('mkdtemp', m_['run'], m_['name'])}>", text)


def _counts(s: dict) -> list[int]:
    return [s.get("ran", 0), s.get("skipped", 0), s.get("expected_failures", 0), s.get("unexpected_successes", 0)]


def _outcome(code: int | None, elapsed: float, s: dict | None, ref: list | None) -> tuple[str, str | None]:
    """PASS / FAIL / TIMEOUT / INFRA for one run, from the exit status and the elapsed time taken before release()
    (VS-3) and the summary. `ref`: T0's [counts, skipped tests] for this file; None for T0 itself and for one test."""
    if code is None:   # WaitContract (tests/v2/test_v2_006.py): a real timeout never returns before its deadline
        return ("TIMEOUT", None) if elapsed >= TIMEOUT else ("INFRA", f"report channel lost after {elapsed:.2f}s")
    if s is None:
        return "INFRA", f"exit {code}, no unittest summary"            # a signal, exit 5, a crash, os._exit
    bad = s.get("failures", 0) + s.get("errors", 0) + s.get("unexpected_successes", 0)
    if code == 0 and s["status"] == "OK" and not bad:
        if ref is None:
            return ("PASS", None) if s["ran"] > s.get("skipped", 0) else ("INFRA", "every test skipped")   # VS-6
        if [_counts(s), s["skipped_tests"]] != ref:
            return "INFRA", f"counts {_counts(s)} or skipped tests differ from T0's {ref[0]}"           # VS-6
        return "PASS", None
    if code == 1 and s["status"] == "FAILED" and bad:
        return ("FAIL", None) if s["first"] else ("INFRA", "no failing test named")
    return "INFRA", f"exit {code} with {s['status']} {_counts(s)}"


def _select(first: str, first_test: str | None) -> str | None:
    """The `-k` pattern that runs only what failed: the failing test (a subtest's whole test), or the class whose
    setUpClass/tearDownClass failed; for a module-level failure (an import, setUpModule) the file's first test, which
    imports the module and sets it up. None: the whole file."""
    m = re.match(r"(\w+) \(([\w.]+)\)", first.split(": ", 1)[1])
    if m and m[2].endswith("." + m[1]) and not m[2].startswith("unittest."):
        return f"*{m[2]}"
    if m and m[1] in ("setUpClass", "tearDownClass"):
        return f"*{m[2]}.*"
    return f"*{first_test}" if first_test else None


def _tail(text: str, tg: _Target, run: pathlib.Path) -> str:
    """The output, normalised so two identical outcomes hash identically across runs and orders (ORD-6 verifier)."""
    for path, name in ((run, "<run>"), (tg.tree, "<tree>"), (tg.scratch, "<scratch>")):
        text = text.replace(os.path.realpath(path), name).replace(str(path), name)
    text = re.sub(r"(<run>[\\/]+tmp[\\/]+)tmp[a-z0-9_]{8}(?![a-z0-9_])", r"\1<mkdtemp>", text)   # a test's own mkdtemp
    text = re.sub(r"^(Ran \d+ tests?) in [\d.]+s$", r"\1", text, flags=re.M)
    return re.sub(r"0x[0-9a-fA-F]+", "0x?", text)[-TAIL:]


def _named(r, residual: Exception, not_empty: bool) -> list[int]:
    """The pids release() named: the `[(pid, command), ...]` its message ends with, read structurally after the exact
    prefix release() writes, rebuilt from the range's own name and ledger — so no text in a command line (which the
    code under test controls: '(1, ' in an escapee's source) can add a pid (process-env prover). A message of another
    shape stops the target: what it names is unknown."""
    head = (f"{r.name}: not empty after {[s['stage'] for s in r.ledger]}: " if not_empty
            else f"{r.name}: processes left the range and are alive: ")
    text = str(residual)
    try:
        if not text.startswith(head):
            raise ValueError(text[:120])
        return [int(pid) for pid, _ in ast.literal_eval(text[len(head):])]
    except (ValueError, TypeError, SyntaxError) as e:
        raise _Stop(f"{ca.RESIDUAL_OWNERSHIP_UNKNOWN}: release() named processes in a form not read: {e}") from None


def _run_file(tg: _Target, rel: str, rows: list, *, select: str | None = None, failfast: bool = True,
              role: str | None = None, fresh: bool = False) -> dict:
    """One run of kill file `rel` — or of what `select` names in it — on the version in the tree, in a clean environment
    (§2), judged from the exit status and the elapsed time taken before release() (VS-3). After it, in this order: its
    leftovers are settled (`_settle`; a process the authority cannot prove stops the target), the run directory is
    removed, and the tree is checked and rebuilt when it differs. All of it goes on this run's own row (PL-4), which is
    in `rows` before anything can stop the target. Only `cleanup_authority` signals anything (P4-FINDING-011)."""
    from aisef2.runtime.process_range import ProcessRange, RangeError, RangeNotEmpty
    from aisef2.runtime.story_scope import Residual
    tg.seq += 1
    begun, elapsed = time.monotonic(), 0.0
    row: dict = {"file": rel, **({"role": role} if role else {}), **({"select": select} if select else {}),
                 **({"fresh": True} if fresh else {})}
    rows.append(row)
    holder = None
    path = pathlib.PurePosixPath(rel)
    # failfast: a mutant is killed by its first failing test; -v names every test and every skip
    cmd = [sys.executable, "-m", "unittest", "discover", "-v", *(["-f"] if failfast else []), "-s", str(path.parent),
           "-t", "tests", "-p", path.name, *(["-k", select] if select else [])]
    try:
        holder = tempfile.TemporaryDirectory(dir=tg.scratch, prefix="run-")
        run = pathlib.Path(holder.name)
        log = run / "kill-test.log"   # beside the run's own directories, never in the tree (OBS-S2-3)
        try:
            with open(log, "wb") as out:
                r = ProcessRange(f"kill tests {rel}", cmd, cwd=tg.tree, env=_env(run, f"{tg.worker}:{tg.seq}"),
                                 output=out, wait_s=RELEASE_WAIT_S).start()
        except (OSError, RangeError) as e:   # VS-4 (b): fork EAGAIN, EMFILE, SPAWN_FAILED — the chain goes on
            r = None
            row.update(outcome="INFRA", why=f"start failed: {type(e).__name__}: {e}")
        if r is not None:
            t = time.monotonic()
            code = r.wait(TIMEOUT)
            elapsed = time.monotonic() - t
            row.update(exit=code, seconds=round(elapsed, 2))
            escaped = [p.pid for p in r.escaped()]   # reported while their parents are alive — checked, never trusted
            residual, released = None, time.monotonic()
            try:
                r.release()
            except Residual as e:
                residual = e
            text = log.read_bytes().decode("utf-8", "replace").replace("\r\n", "\n")
            s = _summary(text)
            outcome, why = _outcome(code, elapsed, s, tg.ref.get(rel, {}).get("ref") if select is None else None)
            row.update(outcome=outcome, why=why)
            if s is not None:
                row.update({k: v for k, v in s.items() if k not in ("status", "skipped_tests", "first_test") and v} |
                           ({"skipped_tests": s["skipped_tests"]} if s["skipped_tests"] else {}) |
                           ({"first_test": s["first_test"]} if role == "t0" and s["first_test"] else {}))
            tail = _tail(text, tg, run)
            row["tail_sha256"] = hashlib.sha256(tail.encode()).hexdigest()
            if outcome != "PASS":
                row["tail"] = tail
            if residual is not None:
                row["residual"] = f"{type(residual).__name__}: {str(residual)[:300]}"
                pids = sorted({p.pid for p in r.members()} | set(escaped) |
                              set(_named(r, residual, isinstance(residual, RangeNotEmpty))))
                anchor = None if r._reaped else r._anchor.pid   # a reaped anchor's group no longer exists (PL-5 (b))
                row.setdefault("leaked", []).extend({"pid": p, "at": "release"} for p in pids)
                report = _clean(tg.boundary, pids, [anchor] if anchor else [])
                row.setdefault("cleanup", []).extend(report.signalled)
                if isinstance(residual, RangeNotEmpty):   # the range would not empty under its own ladder: no verdict
                    row.update(judged_before_release=outcome, outcome="INFRA", why=f"residual: {row['residual']}")
                    r._wait = max(0.0, RELEASE_WAIT_S - (time.monotonic() - released))   # what the budget has left
                    try:
                        r.release()   # its group is gone now: reap the anchor
                    except Residual as e:
                        raise _Stop(f"{ca.RESIDUAL_OWNERSHIP_UNKNOWN}: the range would not empty: {e}") from None
                # RangeEscaped whose escapees are gone (signalled with proof, or gone by themselves within SETTLE_S):
                # the run started clean and keeps its outcome; what it left is named on its row (PL-1, PL-7 verifiers)
        leaked, signalled = _settle(tg)
        if leaked:
            row.setdefault("leaked", []).extend(leaked)
            row.setdefault("cleanup", []).extend(signalled)
        try:
            holder.cleanup()
        except OSError as e:
            row.update(outcome="INFRA", why=f"run directory not removed: {e}")
        if tg.pristine is not None:
            residue = _residue(tg)
            if residue:
                row["residue"] = residue
                if "scratch" in residue:   # nothing the runner may remove holds it (no destructive site): stop
                    raise _Stop(f"RESIDUE_UNREMOVABLE: {residue['scratch']} left in the target's scratch directory")
                _new_tree(tg)   # a new holder too, so what was left beside the tree goes with the old one
    except _Stop as e:
        row.setdefault("outcome", "INFRA")
        row["stopped"] = str(e)
        row.setdefault("leaked", []).extend(e.leaked)
        raise
    except Exception as e:   # the runner's own failure (EMFILE making the run directory, ...): unknown state (VS-4)
        row.setdefault("outcome", "INFRA")
        row["stopped"] = f"RUNNER_EXCEPTION: {e!r}"
        raise _Stop(row["stopped"]) from e
    finally:
        if holder is not None:
            with contextlib.suppress(OSError):
                holder.cleanup()
        row["overhead_s"] = round(time.monotonic() - begun - elapsed, 2)
    return row


def mutant_class(outcomes: list[str]) -> str:
    """A function of the multiset of per-file outcomes (a FAIL here is a confirmed one): order cannot change it (§7)."""
    if "FAIL" in outcomes:
        return "KILLED"
    if all(o == "PASS" for o in outcomes):
        return "SURVIVED"
    if all(o in ("PASS", "TIMEOUT") for o in outcomes):
        return "TIMEOUT"
    return "INFRA"


#: the bracket's runs after a FAIL, in order: the unmutated module twice, then the mutant (role, which version, wanted)
BRACKET = (("control", "null", "PASS"), ("control", "null", "PASS"), ("rerun", "mutant", "FAIL"))


def _confirm(tg: _Target, rel: str, rows: list, row: dict, src: str, fresh: bool = False) -> str:
    """'' when `row`'s FAIL is confirmed, else why not: right away and each in a clean environment, the unmutated module
    PASSES what failed (`_select`) twice in a row, then the mutant FAILS it again with the same signature. Twice: a
    fault that a passing run leaves for the next one (a fixed port's TIME_WAIT) failed the mutant's re-run after the
    control had passed, and a single control confirmed it (PL-2, process-env prover); the second control's run is the
    one that fault now fails. `fresh`: the whole file each time, each in a tree rebuilt from the pristine copy
    (`_remeasure`). The mutant's version is in the tree afterwards."""
    sel = None if fresh else _select(row["first"], tg.ref[rel]["first_test"])
    why = ""
    for i, (role, version, want) in enumerate(BRACKET):
        if fresh:
            tg.version = tg.null if version == "null" else src
            _new_tree(tg)
        else:
            _write(tg, tg.null if version == "null" else src)
        x = _run_file(tg, rel, rows, select=sel, role=role, fresh=fresh)
        if x["outcome"] != want or (role == "rerun" and signature(x.get("first")) != signature(row["first"])):
            why = (f"the unmutated module {'PASS, then ' if i else ''}{x['outcome']}" if role == "control" else
                   f"the mutant again {x['outcome']} {x.get('first') or x.get('why') or ''}".rstrip())
            break
    _write(tg, src)
    return why


def _mutant(tg: _Target, entry: dict, src: str) -> None:
    """Every kill file in execution order (the declared one, unless a table gives another: §7), each run clean. A FAIL
    is a kill only when the bracket confirms it (`_confirm`), in place or, failing that, once more on a fresh tree
    (`_remeasure`). Then — and only then — the remaining files are skipped. Anything else leaves that file's row PASS,
    TIMEOUT or INFRA and the chain goes on: a timeout or an infrastructure fault never decides a kill and never hides
    a later valid one (VS-1, VS-2, VS-5, PL-2, ORD-2)."""
    rows = entry["files"] = []
    _write(tg, src)
    for rel in tg.order:
        row = _run_file(tg, rel, rows)
        if row["outcome"] == "FAIL" and (why := _confirm(tg, rel, rows, row, src)):
            row = _remeasure(tg, rel, rows, row, src, why)
        if row["outcome"] == "FAIL":   # confirmed: the only early stop
            entry["killed_by"] = {"file": rel, "first": row["first"], "seconds": row.get("seconds")}
            return


def _remeasure(tg: _Target, rel: str, rows: list, row: dict, src: str, why: str) -> dict:
    """A FAIL the bracket did not confirm in place: the file is measured once more from scratch — the whole file, in a
    tree rebuilt from the pristine copy — and that run is the file's (`row` keeps its place in the record as
    `unconfirmed`). So a fault that is gone by the bracket no longer hides a valid kill later in the same file (VS-5, the
    failfast case), a test that cannot run alone under -k is bracketed whole (VS-6 (b)), and state the tree checks do
    not see (a __pycache__ a run wrote — FS-2's mechanism, order-equivalence prover) cannot decide it. A FAIL there is
    bracketed the same way, whole file, each run in a new tree; not confirmed again, the file is INFRA."""
    row.update(role="unconfirmed", why=f"kill not confirmed: {why}; re-measured on a fresh tree")
    tg.version = src
    _new_tree(tg)
    again = _run_file(tg, rel, rows, fresh=True)
    if again["outcome"] == "FAIL" and (why := _confirm(tg, rel, rows, again, src, fresh=True)):
        again.update(outcome="INFRA", why=f"kill not confirmed: {why}")
    return again


def _classify(entry: dict, stopped: str | None = None) -> dict:
    primary = [r["outcome"] for r in entry.get("files", []) if "role" not in r]
    cls = "INFRA" if stopped else mutant_class(primary)
    entry.update({"class": cls, "killed": cls == "KILLED"} | ({"why": stopped} if stopped else {}))
    if cls == "TIMEOUT":   # the legacy key, only for the TIMEOUT class: S2.account refuses it, and it cannot depend on order
        entry["timed_out"] = sorted({r["file"] for r in entry["files"] if "role" not in r and r["outcome"] == "TIMEOUT"})
    signals = [s for r in entry.get("files", []) for s in r.get("cleanup", [])]
    if signals:
        entry.update(strays_reaped=len(signals), cleanup=signals)   # each signal with the authority's proof
    return entry


def _baseline(tg: _Target, rows: list) -> list[str]:
    """T0 (§5): the null mutant — the module as `mutants()` rewrites it, nothing mutated — against each kill file on its
    own, the whole file, in a clean environment. Each must PASS, leave nothing behind and run at least one test; its
    counts and skipped tests are the reference every later PASS of the file must match (VS-6). A file that fails the
    null fails every mutant whatever it does (ORD-1: byte- and text-identity assertions), so it is refused, never used.
    Returns why each file that did not pass is refused."""
    _write(tg, tg.null)
    refused = []
    for rel in tg.tests:
        row = _run_file(tg, rel, rows, failfast=False, role="t0")
        if row["outcome"] == "PASS" and not row.get("residue") and not row.get("leaked"):
            tg.ref[rel] = {"ref": [_counts(row), row.get("skipped_tests", [])], "first_test": row.get("first_test")}
        else:
            refused.append(f"{rel}: {row['outcome']} {row.get('first') or row.get('why') or ''}".rstrip()
                           + (" (left residue)" if row.get("residue") else "") + (" (left processes)" if row.get("leaked") else ""))
    return refused


def _run_tests(root: pathlib.Path, tests: list[str], boundary: ca.Boundary) -> tuple[bool, int]:
    """(every kill file PASSes, processes the runner signalled): each file in order, judged as a T0 run is, stopping at
    the first that does not pass, in the caller's own tree (never checked). For callers outside the runner
    (tests/v2/p4/test_process_range.py PROC-OWN-1); `ca.Unproven` when a leftover cannot be proven."""
    with tempfile.TemporaryDirectory() as t:
        tg = _Target(None, pathlib.Path(t), boundary, _worker(root), root)
        rows: list[dict] = []
        for rel in tests:
            if _run_file(tg, rel, rows, failfast=False)["outcome"] != "PASS":
                break
        signalled = sum(len(r.get("cleanup", [])) for r in rows)
        return all(r["outcome"] == "PASS" for r in rows) and len(rows) == len(tests), signalled


def null_mutant(module_src: str, func: str) -> str:
    """The module exactly as `mutants()` writes every mutant of `func`, with nothing mutated: `ast.unparse` of the
    module and, for a `SCRIPT/fn` target, the child script itself re-unparsed inside its constant first (ORD-1
    verifier (b): the script is reformatted too, so a module-level null is not the same rewrite)."""
    tree = ast.parse(module_src)
    script, _, inner = func.partition("/")
    if inner:
        const = _script(tree, script)
        if const is None:
            raise SystemExit(f"child script {script} not found")
        const.value = ast.unparse(ast.parse(const.value))
    return ast.unparse(tree)


_SHA256 = re.compile(r"[0-9a-f]{64}")


def _order_problem(order, kill: list[str]) -> str | None:
    """Why `order` is not an execution order of the kill set `kill` (§7.2), None when it is: an object whose `files` is
    `kill` in some order (the same files, each as often) and whose `from` names the measurement the order came from —
    the record's path and sha256 ({"path", "sha256"}: validation/v2/execution_order.py writes it). One rule for main
    (every table entry, before anything runs), run_target and the record check."""
    files = order.get("files") if isinstance(order, dict) else order
    src = order.get("from") if isinstance(order, dict) else None
    if not isinstance(order, dict) or not isinstance(files, list) or not all(isinstance(f, str) for f in files) \
            or sorted(files) != sorted(kill) or not isinstance(src, dict) or not isinstance(src.get("path"), str) \
            or not src["path"] or not _SHA256.fullmatch(str(src.get("sha256"))):
        return f"execution order {files!r} is not the kill set in another order, or names no measurement"
    return None


def committed(root: pathlib.Path, path: pathlib.Path, raw: bytes) -> tuple[str, str | None]:
    """(`path` relative to `root` when it is inside it, else as given; HEAD's commit when `raw` is that file's bytes at
    HEAD of the repository whose top `root` is, else None). Read-only git; no git, no repository: None."""
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path), None

    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    try:
        top, head, blob = git("rev-parse", "--show-toplevel"), git("rev-parse", "--verify", "HEAD"), git("cat-file", "blob", f"HEAD:{rel}")
    except OSError:
        return rel, None
    ok = (top.returncode == head.returncode == blob.returncode == 0 and blob.stdout == raw
          and pathlib.Path(top.stdout.decode().strip()).resolve() == root.resolve())
    return rel, head.stdout.decode().strip() if ok else None


def run_target(root: pathlib.Path, target: str, tests: list[str], pristine: tuple[pathlib.Path, str] | None = None,
               on_mutant=None, t0_only: bool = False, order: dict | None = None) -> dict:
    """Measure one target (§2–§4). `pristine`: the copy `main()` took once ((path, tree digest)); a direct caller passes
    none and gets one of its own. `order`: an execution-order table's entry, {"files": the kill set in the order each
    mutant's chain runs it, "from": {"path", "sha256"} of the measurement that order came from, ...} (main adds the
    table's path, sha256 and commit), kept whole as `execution_order`; the
    record's `kill_tests` stays the declared list (proof() and the frozen criteria pin it: ORD-4), and T0 still runs
    the files in declared order. None: the declared order, and no `execution_order`. Everything this target writes
    lives in one scratch directory, removed at the end.
    `on_mutant(entry)` is called as each mutant completes (main's checkpoint line). An ownership failure stops the
    target: the finished mutants are kept as measured, the current one is INFRA, the rest NOT_RUN (VS-4)."""
    rel, func = target.split("::")
    worker = _worker(root)
    out: dict = {"target": target, "runner": 2, "kill_tests": list(tests),
                 **({"execution_order": order} if order is not None else {})}
    with tempfile.TemporaryDirectory(prefix=f"aisef-mut-{worker}-", ignore_cleanup_errors=True) as t:
        scratch = pathlib.Path(t)
        src_root, tree_sha = pristine or _pristine(root, scratch / "pristine")
        original = (src_root / rel).read_text(encoding="utf-8")
        found = mutants(original, func, _enum_members(original, src_root))
        out.update(source_sha256=source_digest(original), tree_sha256=tree_sha, mutants=len(found))
        results = out["results"] = [{"mutant": d, "class": "NOT_RUN", "killed": False} for d, _ in found]
        if [k for k in tests if k in NOT_KILL_FILES]:
            out["error"] = f"not a kill file: {[k for k in tests if k in NOT_KILL_FILES]} (NOT_KILL_FILES)"
            return _summarise(out)
        if order is not None and (why := _order_problem(order, tests)):
            out["error"] = why
            return _summarise(out)
        tg, where = None, "before the target"
        try:   # establish, the first tree and T0 are inside too: an exception there keeps the rows and stops (VS-4)
            tg = _Target(rel, scratch, ca.establish(scratch), worker, pristine=src_root, tests=list(tests),
                         last=int((src_root / rel).stat().st_mtime),   # the checkout's own (copy2): stamps are above it
                         order=order and order["files"])
            tg.null, tg.version = null_mutant(original, func), original
            _new_tree(tg)
            _settle(tg)   # what an earlier target of this worker left
            where = "before mutant 1 (T0 {file})"
            refused = _baseline(tg, out.setdefault("t0", []))
            if refused:   # each refused file once more on the original bytes: a broken snapshot, or a rewrite-sensitive file
                out["error"] = "kill tests fail on the unmutated tree (T0 null mutant): " + "; ".join(refused)
                _write(tg, original)
                for rel_ in [r["file"] for r in out["t0"] if r["outcome"] != "PASS" or r.get("residue") or r.get("leaked")]:
                    _run_file(tg, rel_, out.setdefault("original", []), failfast=False, role="original")
            for i, (desc, src) in enumerate([] if refused or t0_only else found):
                where = f"at mutant {desc!r} ({{file}})"
                entry = results[i] = {"mutant": desc}
                try:
                    _mutant(tg, entry, src)
                except _Stop as e:
                    _classify(entry, f"{e}")
                    raise
                except Exception as e:   # unknown state: this mutant has no verdict, and nothing more runs
                    _classify(entry, f"RUNNER_EXCEPTION: {e!r}")
                    raise _Stop(f"RUNNER_EXCEPTION: {e!r}") from e
                _classify(entry)
                if on_mutant:
                    on_mutant(entry)
        except Exception as e:   # a stop, or the runner's own failure outside a mutant's chain: nothing more runs
            stop = e if isinstance(e, _Stop) else _Stop(f"RUNNER_EXCEPTION: {e!r}")
            rows = [*out.get("t0", []), *out.get("original", []), *(x for r in results for x in r.get("files", []))]
            file = next((r["file"] for r in reversed(rows) if r.get("stopped")), "?")
            out.update(error=f"{stop.code} {where.format(file=file)}: {stop.detail}", stopped=True,
                       **({"leaked": stop.leaked} if stop.leaked else {}))
        finally:
            if tg is not None and tg.holder is not None:
                tg.holder.cleanup()
    return _summarise(out)


def _summarise(out: dict) -> dict:
    res = out["results"]
    classes = {c: sum(1 for r in res if r["class"] == c) for c in CLASSES}
    out.update(killed=classes["KILLED"], survivors=[r["mutant"] for r in res if not r["killed"]], classes=classes,
               killed_by_timeout=classes["TIMEOUT"], strays_reaped=sum(r.get("strays_reaped", 0) for r in res))
    open_ = {c: n for c, n in classes.items() if c not in ("KILLED", "SURVIVED") and n}
    if open_ and not out.get("error"):   # the frozen merge tools refuse an errored result: no audit can excuse these
        # a run that ends with no unittest summary (a signal, os._exit) is never confirmed, so re-running such a mutant
        # gives INFRA again: it needs a kill test or a ruling (lead decision Q1; classification prover, VS-6 (a))
        silent = sum(1 for r in res if r["class"] == "INFRA" and any(
            "no unittest summary" in (x.get("why") or "") for x in r.get("files", []) if "role" not in x))
        out["error"] = (f"UNCLASSIFIED: {sum(open_.values())} mutant(s) neither killed nor survived {open_} — "
                        + ("re-run them" if not silent else f"{silent} end a kill test with no unittest summary (a signal, "
                           f"os._exit), which a re-run cannot confirm: each needs a kill test or a ruling; re-run the rest"))
    return out


def _confirmed(r: dict) -> bool:
    """A KILLED entry carries its bracket (`BRACKET`): the killing row FAIL, then two control PASSes and the re-run FAIL
    with the same signature, on the same file."""
    kb, rows = r.get("killed_by") or {}, r.get("files", [])
    for i, x in enumerate(rows):
        sx = signature(x.get("first"))
        if "role" not in x and x["file"] == kb.get("file") and x["outcome"] == "FAIL" and isinstance(sx, str) and \
                sx == signature(kb.get("first")):
            got = [(y.get("role"), y["file"], y["outcome"], signature(y.get("first")) if y.get("role") == "rerun" else None)
                   for y in rows[i + 1:i + 1 + len(BRACKET)]]
            return got == [(role, x["file"], want, sx if role == "rerun" else None) for role, _, want in BRACKET]
    return False


def _problems_v2(t: dict, root: pathlib.Path) -> list[str]:
    """The verdict on a runner-2 result (§4.3): the legacy rules, and every mutant is KILLED (a confirmed kill) or
    SURVIVED (every kill file PASSed); any other class is refused and no audit excuses it (VS-2, VS-4)."""
    name, res = t["target"], t.get("results", [])
    out = [f"{name}: {t['error']}"] if t.get("error") else []
    if source_digest((root / name.split("::")[0]).read_text(encoding="utf-8")) != t.get("source_sha256"):
        out.append(f"{name}: target changed since the mutation run — re-run it")
    if not t.get("mutants"):
        out.append(f"{name}: no mutants generated — a run that cannot say NO proves nothing")
    for i, r in enumerate(res):
        d, cls = r["mutant"], r.get("class")
        if cls == "SURVIVED":
            if name in NO_AUDIT:
                out.append(f"{name}: survivor {d!r} (must be fully killed; audits not accepted)")
            elif (name, d) not in AUDITED and audit_of(root, name, i, d, t.get("source_sha256")) is None:
                out.append(f"{name}: unaudited survivor {d!r}")
        elif cls != "KILLED":
            out.append(f"{name}: mutant {d!r} is {cls} ({r.get('why') or 'see its rows'}): neither killed nor survived — re-run it")
    bad = [] if len(res) == t.get("mutants") else ["the results do not list every mutant"]
    # the order each chain ran the kill set in: the declared one, or `execution_order` when the record has the key —
    # read by the runner's own rule; a malformed one is refused and never read as the declared order (ran: None)
    why = _order_problem(t["execution_order"], t["kill_tests"]) if "execution_order" in t else None
    ran = None if why else t["execution_order"]["files"] if "execution_order" in t else t["kill_tests"]
    bad += [why] if why else []
    if "execution_order" in t and not why:   # and its table: the path and sha256 main stamps, committed at the run's HEAD
        eo = t["execution_order"]
        if not isinstance(eo.get("table"), str) or not _SHA256.fullmatch(str(eo.get("table_sha256"))):
            bad.append("execution_order names no table and its sha256")
        elif not eo.get("table_commit"):
            out.append(f"{name}: execution-order table {eo['table']} was not a file committed at the run's HEAD — "
                       "commit it and re-run")
    bad += [] if t.get("survivors") == [r["mutant"] for r in res if r.get("class") != "KILLED"] else \
        ["survivors are not the mutants that were not killed"]
    bad += [] if t.get("killed") == sum(r.get("class") == "KILLED" for r in res) else ["killed is not the KILLED count"]
    for r in res:
        d, rows = r["mutant"], r.get("files", [])
        if r.get("killed") != (r.get("class") == "KILLED"):
            bad.append(f"mutant {d!r}: killed is not its class")
        if r.get("class") == "KILLED" and not _confirmed(r):
            bad.append(f"mutant {d!r}: KILLED without a confirmed kill")
        passed = [x["file"] for x in rows if "role" not in x and x["outcome"] == "PASS"]
        if r.get("class") == "SURVIVED" and ran is not None and passed != ran:
            bad.append(f"mutant {d!r}: SURVIVED without one PASS per kill file")
    if not t.get("error") and any(x.get("outcome") != "PASS" for x in t.get("t0", [])):
        bad.append("a T0 row did not pass")
    return out + [f"{name}: inconsistent record: {b}" for b in bad]


def target_problems(t: dict, root: pathlib.Path = ROOT) -> list[str]:
    """The verdict on one target's result: unchanged since the run, mutants generated, every survivor accounted for.
    A runner-2 result (`"runner": 2`) is read by `_problems_v2`; every other record — every historical one — by the
    rules below, unchanged."""
    if t.get("runner") == 2:
        return _problems_v2(t, root)
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
    if phase == "V2.1":   # no result of a runner that did not classify enters V2.1 (VS-1, BC-3, ORD-1)
        out += [f"{t['target']}: measured by a runner that does not classify — re-measure" for t in targets
                if t.get("runner") != 2]
    if phase == "V2.1":   # a malformed positional audit counts for nothing, and is said so
        out += audits_at(root)[1]
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


def _checkpoint(entry: dict) -> None:
    """One line per finished mutant (PL-6): the worker log keeps it byte for byte, so a worker killed mid-target loses
    nothing it measured."""
    print("MUTANT " + json.dumps(entry, ensure_ascii=False), flush=True)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["t0"]:   # T0 only, nothing written: `t0 TARGET... [--tests FILE...]` (--tests: a diagnostic kill set)
        targets, _, files = [x for x in argv[1:]], None, None
        if "--tests" in targets:
            i = targets.index("--tests")
            targets, files = targets[:i], targets[i + 1:]
        unknown = [t for t in targets if t not in TARGETS]
        if unknown or not targets:
            raise SystemExit(f"not a mutation target: {unknown or 'none named'}")
        failed = 0
        for target in targets:
            r = run_target(ROOT, target, files or TARGETS[target], t0_only=True)
            for row in [*r.get("t0", []), *r.get("original", [])]:
                print(json.dumps({"target": target, **{k: v for k, v in row.items() if k != "tail"}}, ensure_ascii=False))
            bad = r.get("stopped") or not r.get("t0") or any(   # no T0 row: the kill set was refused before T0
                x["outcome"] != "PASS" or x.get("residue") or x.get("leaked") for x in r.get("t0", []))
            failed += bool(bad)
            print(f"T0 {target}: " + (r["error"] if bad else "PASS"), flush=True)
        return 1 if failed else 0
    if argv[:1] == ["run"]:
        chosen, table, stamp = argv[1:], {}, {}
        # misuse is refused before anything runs, never read another way (`run A --order T` ran A, then refused)
        if "--order" in chosen[1:] or (chosen[:1] == ["--order"] and len(chosen) < 3):
            raise SystemExit("usage: mutation.py run --order TABLE.json TARGET... (--order once, first, with a table "
                             "and the targets it is for)")
        if chosen[:1] == ["--order"]:   # validation/v2/execution_order.py's table: {"orders": {target: entry}, ...}
            path, chosen = pathlib.Path(chosen[1]), chosen[2:]
            try:
                raw = path.read_bytes()
                table = json.loads(raw).get("orders")
            except (OSError, ValueError, AttributeError) as e:
                raise SystemExit(f"execution-order table refused, nothing ran: {path}: {e}") from None
            if not isinstance(table, dict):
                raise SystemExit(f"execution-order table refused, nothing ran: {path} has no `orders` object")
            rel, commit = committed(ROOT, path, raw)   # the record ties each result to the committed table
            stamp = {"table": rel, "table_sha256": hashlib.sha256(raw).hexdigest(), "table_commit": commit}
            if not commit:
                print(f"WARNING execution-order table {rel} is not a file committed at HEAD: --check refuses every "
                      "result it orders", flush=True)
            if unknown := [x for x in table if x not in TARGETS]:
                raise SystemExit(f"not a mutation target in the execution-order table: {unknown}")
            # every entry, before the first target runs: a bad one refused at its turn came after hours of earlier
            # targets, and its errored entry replaced that target's result in the record
            if bad := {x: why for x, e in table.items() if (why := _order_problem(e, TARGETS[x]))}:
                raise SystemExit(f"execution-order table refused, nothing ran: {bad}")
        if unknown := [t for t in chosen if t not in TARGETS]:
            raise SystemExit(f"not a mutation target: {unknown}")
        chosen = chosen or list(TARGETS)
        worker = _worker(ROOT)
        try:
            left = _earlier(worker)
        except OSError as e:
            print(f"STOPPED before the first target: HOST_TABLE_UNREADABLE: {e}", flush=True)
            return 3
        if left:  # a restarted worker never runs beside what an earlier run of it left (PL-3 verifier (e))
            print(f"STOPPED before the first target: an earlier run of this worker left {left} alive", flush=True)
            return 3
        with tempfile.TemporaryDirectory(prefix=f"aisef-pristine-{worker}-") as p:
            pristine = _pristine(ROOT, pathlib.Path(p) / "tree")   # once, before any record is written (FS-4)
            done: set[str] = set()
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
                    try:
                        t = run_target(ROOT, target, TARGETS[target], pristine, on_mutant=_checkpoint,
                                       order={**table[target], **stamp} if target in table else None)
                    except Exception as e:   # outside run_target's own guard (its copy, mutants()): named, never lost
                        t = _summarise({"target": target, "runner": 2, "kill_tests": list(TARGETS[target]), "mutants": 0,
                                        "results": [], "error": f"RUNNER_EXCEPTION before the target: {e!r}",
                                        "stopped": True})
                    done.add(target)
                    fresh.append(t)
                    record["targets"] = sorted(kept + fresh, key=lambda x: x["target"])
                    out.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
                    print(f"{t['target']}: {t.get('killed')}/{t.get('mutants')} killed; classes {t.get('classes')}; "
                          f"survivors {t.get('survivors')}" + (f" ERROR {t['error']}" if t.get("error") else ""), flush=True)
                    if t.get("stopped"):   # the worker never runs beside a process it cannot prove its own
                        rest = [x for x in chosen if x in TARGETS and x not in done]   # targets run phase by phase
                        print(f"STOPPED {target}: {t['error']}\nNOT RUN {rest}", flush=True)
                        return 3
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
