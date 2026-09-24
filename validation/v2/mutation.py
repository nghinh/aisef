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
never rewritten by a later phase's targets.

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
           "P5": "closure-evidence/v2/P5-MUTATION.json"}
OUT_REL = RECORDS["P1"]
TIMEOUT = 120

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
    "aisef2/control/owner.py::flatten": ["tests/v2/p1/test_routing.py"],
    "aisef2/control/routing.py::_EXECUTED": ["tests/v2/p1/test_routing.py", "tests/v2/p2/test_signal_provenance.py"],
    "aisef2/control/routing.py::route": ["tests/v2/p1/test_routing.py", "tests/v2/p2/test_signal_provenance.py"],
}
_PROTOCOL_TESTS = ["tests/v2/p2/test_probe_protocol.py"]
_HARNESS_TESTS = ["tests/v2/p2/test_python_callable.py"]
#: the provenance split is measured by both: the harness's own cases and SIG-PROBE-1..10 (V2-003)
_SIGNAL_TESTS = ["tests/v2/p2/test_python_callable.py", "tests/v2/p2/test_signal_provenance.py"]
_ADMISSION_TESTS = ["tests/v2/p2/test_static_admission.py"]
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
    "aisef2/probe/python_callable.py::observe": _HARNESS_TESTS,
    "aisef2/probe/python_callable.py::window_of": _HARNESS_TESTS,
    "aisef2/probe/python_callable.py::observation_class": _HARNESS_TESTS,
    "aisef2/probe/python_callable.py::ON_DEADLINE": _HARNESS_TESTS,
    "aisef2/probe/python_callable.py::_harness_failure": _HARNESS_TESTS,
    # V2-003 (§9.3): the provenance split — the controller's own ledger decides, never the signal number
    "aisef2/probe/python_callable.py::_after_dispatch": _SIGNAL_TESTS,
    "aisef2/probe/python_callable.py::_ended_without_result": _SIGNAL_TESTS,
    "aisef2/probe/python_callable.py::_signal_of": _SIGNAL_TESTS,
    # §35: the probe's identity — a source dropped here would reuse an old digest, and with it an old semantic_hash
    "aisef2/probe/python_callable.py::PROBE_SOURCES": _HARNESS_TESTS,
    "aisef2/probe/python_callable.py::_probe_digest": _HARNESS_TESTS,
    "aisef2/probe/python_callable.py::_watch": _SIGNAL_TESTS,
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
        "StoryScope.acquire", "StoryScope.dispose", "StoryScope._record", "StoryScope._release", "DisposalReport.ok",
        "Directory.__init__", "Directory.release")},
    # WP-4.2: measured range emptiness — the ownership walk (pure) and the POSIX range; the Windows job adapter
    # (_Job) and the Linux /proc reader run on CI, not on the developer machine this tool runs on
    **{f"aisef2/runtime/process_range.py::{f}": _TABLE_TESTS for f in ("descendants", "targets", "_ps_table")},
    **{f"aisef2/runtime/process_range.py::{f}": _RANGE_TESTS for f in (
        "_Posix.members", "_Posix.escaped", "_Posix.abort", "ProcessRange.start",
        "ProcessRange.wait", "ProcessRange.members", "ProcessRange.escaped", "ProcessRange.wait_empty",
        "ProcessRange._signal", "ProcessRange.release", "ProcessRange._abort", "ProcessRange._close_pipes")},
    **{f"aisef2/runtime/range_anchor.py::{f}": _RANGE_TESTS for f in ("main", "_die", "_subreaper", "_reap_adopted")},
    "aisef2/runtime/process_range.py::_Job.controller_stopped": _RANGE_TESTS,
    "aisef2/runtime/process_range.py::ProcessRange.anchor_returncode": _RANGE_TESTS,
    "aisef2/runtime/story_scope.py::StoryScope.release": _SCOPE_TESTS,
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
# WP52-001: the destructive-site checker's discovery of callables handed over by reference, and the ledger check
P5_TARGETS.update({f"validation/v2/destructive_authority.py::{f}": ["tests/v2/p0/test_destructive_authority.py"]
                   for f in ("discover", "_references", "_destructive_ref", "_aliases", "_alias", "check")})
PHASE_TARGETS = {"P1": P1_TARGETS, "P2": P2_TARGETS, "P3": P3_TARGETS, "P4": P4_TARGETS, "P5": P5_TARGETS}
TARGETS: dict[str, list[str]] = {t: k for targets in PHASE_TARGETS.values() for t, k in targets.items()}
#: Targets whose survivors may not be audited away.
NO_AUDIT: set[str] = {"aisef2/product/outcome.py::contract_satisfaction"}
#: (target, mutant description) -> why the mutant is equivalent, each examined by hand. Only the independent reference
#: models have entries: their code is not edited to remove a dead field, because its author is not this session.
_DEAD_FLAG = ("the third field (whether the target state is also the outcome) is read only when the target state is "
              "not None (model: `if to is not None: ... if is_outcome`); this entry's target is None")
AUDITED: dict[tuple[str, str], str] = {
    ("tests/v2/refmodel/story_state.py::_TABLE", "L18 False->True"): _DEAD_FLAG,
    ("tests/v2/refmodel/story_state.py::_TABLE", "L19 False->True"): _DEAD_FLAG,
    ("tests/v2/refmodel/story_state.py::_TABLE", "L20 False->True"): _DEAD_FLAG,
    ("tests/v2/refmodel/budgets.py::model", "L56 True->False"): (
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
        "aisef")  # the frozen V1 tree, read by the WIN-PID red-before reproducers; never a target

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


def _root(tree: ast.Module, name: str) -> tuple[ast.AST, set[int]] | None:
    """A function named `name` (minus its docstring and annotations), or the value of a module-level assignment
    to `name` — so a routing table or a taxonomy held as data is a mutation target like a function is. `Class.method`
    names the method of that class when one module has several methods of the same name."""
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
    """(description, mutated module source) for every mutation site inside the function or table `func`."""
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
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", str(path.parent), "-t", "tests", "-p", path.name]
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


def problems_of(record: dict, root: pathlib.Path = ROOT, phase: str = "P1") -> list[str]:
    seen = {t["target"] for t in record["targets"]}
    out = [f"{t} has no mutation result" for t in PHASE_TARGETS[phase] if t not in seen]
    out += [f"{t} belongs to {phase_of(t)}, not {phase}" for t in seen if t in TARGETS and phase_of(t) != phase]
    return out + [p for t in record["targets"] for p in target_problems(t, root)]


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
    for p in problems:
        print(f"FAIL  {p}")
    print("mutation: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
