"""Engineering-quality checks on the candidate (RFC §15, WP-5 through WP-6.2): the story's tests, their vacuity and
relevance, and the regressions, run at the candidate checkout only (invariant IX), assembled by WP-5.4 and journaled
as `tests/adequacy` (format 3, V2-005). UNRUNNABLE is an environment failure with its own provenance
(TESTS_UNRUNNABLE); a result the assembly says MAY block (§15.3: INADEQUATE, and only that) blocks under the
project's preregistered stance (TESTS_INADEQUATE, DEVELOPER); INCOMPLETE is recorded and charged to nobody — it is
never a failure. No adequacy outcome is named or decided here: the assembly's own `may_block` is read."""

from __future__ import annotations

from dataclasses import dataclass

from aisef2.arch.enums import EventType as T, TestExecutionStatus
from aisef2.control.owner import Classification, FailureCode, classify
from aisef2.quality import test_execution as te
from aisef2.quality.adequacy import Assembly, assemble
from aisef2.quality.relevance import measure, story_diff
from aisef2.quality.test_execution import Dependencies, DeveloperTests, Runner
from aisef2.quality.vacuity import evaluate

__all__ = ["Dependencies", "DeveloperTests", "Runner", "TestsPolicy", "Quality", "assess", "payload"]


@dataclass(frozen=True, slots=True)
class TestsPolicy:
    """The project's preregistered stance on a result the assembly says may block (§15.3: INADEQUATE); it decides
    nothing about the outcome itself."""
    blocking: bool


@dataclass(frozen=True, slots=True)
class Quality:
    assembly: Assembly
    seq: int
    failure: Classification | None


def payload(story_id: str, assembly: Assembly) -> dict:
    """The typed assembly, field for field, as `tests/adequacy` carries it (V2-005 §4)."""
    a = assembly.adequacy
    d = {"story_id": story_id, "execution": te.to_json(a.execution), "vacuity": a.vacuity.value if a.vacuity else None,
         "relevance": a.relevance.value if a.relevance else None, "regressions": te.to_json(a.regressions),
         "outcome": a.outcome.value if a.outcome else None, "owner": assembly.owner.value if assembly.owner else None,
         "may_block": assembly.may_block, "developer_chargeable": assembly.developer_chargeable}
    if assembly.chronology is not None:
        d["chronology"] = dict(assembly.chronology)
    return d


def assess(run, story_id: str, candidate_root: str, patch: str, story_tests: te.DeveloperTests,
           regression_tests: te.DeveloperTests, deps: te.Dependencies, runner: te.Runner, policy: TestsPolicy, *,
           interpreter: str, timeout_s: float, on_range=None) -> Quality:
    """WP-5.1 -> 5.2 -> 5.3 -> 5.4 at the candidate, then the journal row and the typed failure the policy allows."""
    report, execution = te.execute(runner, candidate_root, story_tests, deps, interpreter=interpreter,
                                   targets=(*story_tests.paths, te.MEASURE), timeout_s=timeout_s, on_range=on_range)
    vacuity = relevance = None
    if execution.status is TestExecutionStatus.EXECUTED:
        relevance = measure(execution, report.result_set, story_tests, story_diff(patch), candidate_root).relevance
        vacuity = evaluate(runner, candidate_root, patch, story_tests, deps, (report, execution),
                           interpreter=interpreter, timeout_s=timeout_s, on_range=on_range).vacuity
    _, regressions = te.execute(runner, candidate_root, regression_tests, deps, interpreter=interpreter,
                                timeout_s=timeout_s, on_range=on_range)
    assembly = assemble(execution, vacuity, relevance, regressions)
    seq = run.append(T.TESTS_ADEQUACY, payload(story_id, assembly)).seq
    failure = None
    if assembly.outcome is None:
        failure = classify(FailureCode.TESTS_UNRUNNABLE)
    elif assembly.may_block and policy.blocking:
        failure = classify(FailureCode.TESTS_INADEQUATE)
    return Quality(assembly, seq, failure)
