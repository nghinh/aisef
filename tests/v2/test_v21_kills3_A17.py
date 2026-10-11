"""V2.1 (owner B-03, batch A17): requirement tests for survivors of aisef2/app/feedback.py::retry_feedback that the
triage proposed to leave as equivalent, and that hold only while the journal is the kernel's single-writer order.

`retry_feedback` is a pure function of the journal (module docstring, H-RETRY-001): what the developer is told on a
retry is what the journal says. Its two contracts that these tests pin:

* a REVIEW_FINDING bullet is followed by "the confirmed findings that blocked this attempt, as journaled" — the failing
  review rows of that failure's own attempt, once each, and nothing else (feedback.py L76);
* the verdict advice ("the candidate remains X ... inspect the implementation") is given only when the verdict is a
  verdict, and one other than the one the plan expects (feedback.py L95).

Every journal here is written through the kernel's own writer — format 3, the six projections' pre-check on each
append, the path RunScope.append takes — so what is tested is a journal the kernel admits. Not every one is a journal
the kernel's present stage order writes (each test says which); the contract fits all of them, and the stage order is
not a guarantee the format makes. If the format ever refuses one of them, building it raises here and the test is
retired with the mutants it pins becoming equivalent: that is the signal, not a flake."""

from __future__ import annotations

import dataclasses
import pathlib
import sys
import tempfile
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, feedback  # noqa: E402
from aisef2.arch.enums import BehaviorVerdict, EventType as T  # noqa: E402
from aisef2.journal.fold import Authority  # noqa: E402
from aisef2.journal.format3 import FORMAT, JournalWriter3  # noqa: E402
from aisef2.journal.projections import PROJECTIONS  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402

PARENT, CANDIDATE = "a" * 40, "c" * 40
#: the opening of feedback.REFUTED up to the verdict it names: the advice, whichever verdict it carries
ADVICE = feedback.REFUTED.split("{verdict}")[0]


class Journal:
    """A format-3 journal under construction, appended through Authority(JournalWriter3, the six projections)."""

    def __init__(self, case: unittest.TestCase, roles: dict[str, str]) -> None:
        tmp = tempfile.TemporaryDirectory()
        case.addCleanup(tmp.cleanup)
        self.writer = JournalWriter3(pathlib.Path(tmp.name) / "aisef-run.jsonl", clock=lambda: 0.0)
        case.addCleanup(self.writer.close)   # runs before the directory goes: an open file cannot be removed on Windows
        self.authority = Authority(self.writer, PROJECTIONS.values())
        self._checks: list[int] = []         # the gate rows not yet cited by a decision
        self._failure = -1
        self.put("run/begin", journal_format=FORMAT, run_id="run-A17")
        self.put("plan/frozen", plan_id="PLAN-CALC", plan_hash="f" * 64, roles=roles)

    def put(self, kind: str, cites: tuple[int, ...] = (), **data) -> int:
        return self.authority.append(T(kind), data, source_seqs=cites).seq

    def start(self, story: str, criterion: str, developer: tuple[str, str] = ("COMPLETED", "opencode exit 0, 3 turns")) -> None:
        """An attempt's opening in the kernel's order: begin, admission, the developer's request and its result."""
        self.put("story/begin", story_id=story, parent=PARENT)
        self.put("story/admitted", story_id=story, parent=PARENT, admitted=True, developer_call_permitted=True,
                 dispositions={criterion: "READY"})
        request = self.put("provider/request", story_id=story, criteria=[criterion], budget_owner="DEVELOPER")
        self.put("provider/result", (request,), story_id=story, outcome=developer[0], synthetic=False, detail=developer[1])

    def review(self, story: str, criterion: str) -> None:
        request = self.put("provider/request", story_id=story, criteria=[criterion], budget_owner="REVIEW")
        self.put("provider/result", (request,), story_id=story, outcome="COMPLETED", synthetic=False, detail="reviewed")

    def row(self, story: str, stage: str, passed: bool, detail: str) -> None:
        """One gate/check as orchestrate/gate.check writes it: no story_id, the story's name in the check."""
        self._checks.append(self.put("gate/check", gate="story", check=f"{story}:{stage}", passed=passed, detail=detail))

    def decide(self, passed: bool) -> None:
        cited, self._checks = tuple(self._checks), []
        self.put("gate/decision", cited, gate="story", passed=passed, projections=["story_state"])

    def fail(self, story: str, code: str, detail: str) -> None:
        self._failure = self.put("failure/observed", story_id=story, code=code, detail=detail)

    def close_attempt(self, story: str, then: str) -> None:
        if then == "story/commit":
            self.put(then, story_id=story, revision=CANDIDATE)
        else:
            self.put(then, (self._failure,), story_id=story)
        self.put("story/dispose", story_id=story)
        self.put("story/end", story_id=story)

    def events(self) -> list:
        """`(seq, type, data)` as Developer.implement hands them to retry_feedback (the events' own frozen data)."""
        return [(e.seq, e.type, e.data) for e in self.writer.events]


class _Retry(unittest.TestCase):
    def setUp(self) -> None:
        self.project = bundle.load(e2e.project_bundle(PARENT))

    def told(self, journal: Journal, story: str = "S1", project: bundle.Project | None = None) -> str:
        return feedback.retry_feedback(journal.events(), story, project or self.project)


class ReviewFindingsOfThisAttempt(_Retry):
    """retry_feedback L78, L80 — the findings listed under a REVIEW_FINDING bullet are the failing review rows
    (`<story>:review:<finding>`) of that failure's own attempt, between its story/begin and the failure: the developer
    fixes what it is told, so a row of another story, of another stage, or one told under an earlier failure of the
    same attempt misdirects the fix loop, and a finding left out leaves it a REVIEW_FINDING with nothing to act on."""

    def test_the_findings_of_a_story_whose_id_extends_this_one_at_a_colon_are_not_told(self):
        """Pins aisef2/app/feedback.py::retry_feedback [132, 138]: story/begin is the attempt's boundary. Story ids are
        free strings (bundle.py L83-95 checks only that depends_on names exist; PlanObligation only that they are not
        blank), so S1 can depend on a story named `S1:review`, whose rows are `S1:review:proof:C-LIB`: the prefix S1's
        filter matches. The order is the kernel's own (S1:review fails once and commits, then S1 is reviewed); only the
        id is unusual."""
        j = Journal(self, {"C-ADD": "INTRODUCE", "C-LIB": "INTRODUCE"})
        j.start("S1:review", "C-LIB")
        j.row("S1:review", "proof:C-LIB", False, "FINDING-OF-THE-OTHER-STORY")
        j.decide(False)
        j.fail("S1:review", "CONTRACT_UNSATISFIED", "proof of C-LIB: CONTRACT_UNSATISFIED")
        j.close_attempt("S1:review", "story/retry")
        j.start("S1:review", "C-LIB")
        j.row("S1:review", "proof:C-LIB", True, "verified")
        j.decide(True)
        j.close_attempt("S1:review", "story/commit")
        j.start("S1", "C-ADD")
        j.review("S1", "C-ADD")
        j.row("S1", "review:F-1", False, "FINDING-OF-S1")
        j.decide(False)
        j.fail("S1", "REVIEW_FINDING", "review: REVIEW_FINDING")
        told = self.told(j)
        self.assertIn("FINDING-OF-S1", told)
        self.assertNotIn("FINDING-OF-THE-OTHER-STORY", told)

    def test_a_failing_row_of_another_stage_is_not_a_finding(self):
        """Pins [133]: only `<story>:review:` rows are findings. The developer's row is failing (passed False) whenever
        its outcome is not COMPLETED — story_runner L233 — and that sets no failure, so the attempt goes on to the
        proofs and the review (the proofs here pass at the unchanged parent, as a probe that measured differently
        would let them): the order the kernel writes, with a row that is not a finding between begin and failure."""
        j = Journal(self, {"C-ADD": "INTRODUCE"})
        changed_nothing = "the developer changed nothing (exit 0, timed out False)"
        j.start("S1", "C-ADD", ("FAILED", changed_nothing))
        j.row("S1", "developer", False, changed_nothing)
        j.row("S1", "proof:C-ADD", True, "verified")
        j.review("S1", "C-ADD")
        j.row("S1", "review:F-1", False, "FINDING-OF-S1")
        j.decide(False)
        j.fail("S1", "REVIEW_FINDING", "review: REVIEW_FINDING")
        told = self.told(j)
        self.assertIn("FINDING-OF-S1", told)
        self.assertNotIn("changed nothing", told)

    def test_a_second_failure_of_one_attempt_is_told_only_the_findings_that_decided_it(self):
        """Pins [131, 137]: a failure is the boundary of the next one's findings. failure/observed has no state rule in
        story_state (the projection admits it at any point after story/begin), so an attempt may journal two; the
        kernel writes one per attempt (story_runner L332). Each failure is told "with the evidence that decided it"
        (feedback.py docstring): the first finding belongs to the first failure and is not repeated under the second."""
        j = Journal(self, {"C-ADD": "INTRODUCE"})
        j.start("S1", "C-ADD")
        j.review("S1", "C-ADD")
        j.row("S1", "review:F-1", False, "FINDING-ONE")
        j.decide(False)
        j.fail("S1", "REVIEW_FINDING", "review: REVIEW_FINDING")
        j.row("S1", "review:F-2", False, "FINDING-TWO")
        j.decide(False)
        j.fail("S1", "REVIEW_FINDING", "review: REVIEW_FINDING")
        told = self.told(j)
        first, second = [b for b in told.split("\n- ") if "REVIEW_FINDING" in b]
        self.assertIn("FINDING-ONE", first)
        self.assertNotIn("FINDING-TWO", first)
        self.assertIn("FINDING-TWO", second)
        self.assertNotIn("FINDING-ONE", second)

    def test_a_record_the_attempt_journals_after_the_review_rows_does_not_hide_them(self):
        """Pins [125]: the findings are the rows between the attempt's begin and its failure, whatever else the attempt
        journals in between. Here the security scanner's tool/invoked (a story-tagged record, orchestrate/security.py)
        follows the review rows before the failure is recorded — not today's order (the scan runs only after a review
        that blocks nothing), but one a later stage ordering writes; the developer must still be told the findings."""
        j = Journal(self, {"C-ADD": "INTRODUCE"})
        j.start("S1", "C-ADD")
        j.review("S1", "C-ADD")
        j.row("S1", "review:F-1", False, "FINDING-OF-S1")
        j.put("tool/invoked", story_id="S1", call_id="scanner-S1#1", tool="scanner")
        j.decide(False)
        j.fail("S1", "REVIEW_FINDING", "review: REVIEW_FINDING")
        self.assertIn("FINDING-OF-S1", self.told(j))


class VerdictAdvice(_Retry):
    """retry_feedback L95 — a DEVELOPER-owned failure after an executed, agreed proof carries the advice "the candidate
    remains <verdict> for this approved contract; inspect the implementation against that clause" only when there is a
    verdict to name and it is not the verdict the plan expects for the criterion (an expected verdict is not a thing the
    candidate "remains" short of). The advice is the developer's recovery instruction on a retry: given when the
    verdict is the expected one it sends the developer to fix an implementation the proof found as required; and it is
    built from the proof's verdict, so a proof without one must not make the prompt builder raise (Developer.implement
    calls retry_feedback unguarded, and only ProviderOutage is caught around it)."""

    def spec(self):
        """The spec of C-ADD's obligation: the one the plan's expectation for that criterion is read from."""
        o = next(o for o in self.project.plan.obligations if o.criterion_id == "C-ADD")
        return self.project.specs[o.product_proof_spec_id]

    def proved(self, verdict: str | None, project: bundle.Project | None = None) -> str:
        """S1's attempt: C-ADD proved by two agreeing executed records with `verdict`, then the DEVELOPER's failure."""
        spec = self.spec()
        j = Journal(self, {"C-ADD": "INTRODUCE"})
        j.start("S1", "C-ADD")
        record = {"spec_id": spec.id, "revision": CANDIDATE, "semantic_hash": spec.semantic_hash,
                  "probe_id": spec.probe_id, "probe_digest": "d" * 64, "enforcement": "NONE",
                  "result": {"behavior_verdict": verdict, "reason": None}}
        a = j.put("probe/evaluated", story_id="S1", criterion_id="C-ADD", record=record)
        b = j.put("probe/evaluated", story_id="S1", criterion_id="C-ADD", record=record)
        verdict_field = {} if verdict is None else {"verdict": verdict}
        j.put("proof/verified", (a, b), story_id="S1", criterion_id="C-ADD", spec_id=spec.id,
              semantic_hash=spec.semantic_hash, candidate=CANDIDATE, agreement=True, **verdict_field)
        j.row("S1", "proof:C-ADD", False, "CONTRACT_UNSATISFIED")
        j.decide(False)
        j.fail("S1", "CONTRACT_UNSATISFIED", "proof of C-ADD: CONTRACT_UNSATISFIED")
        return self.told(j, project=project)

    def expected(self) -> str:
        return self.spec().candidate_expectation.value

    def test_the_advice_is_given_for_a_verdict_other_than_the_expected_one_and_not_for_the_expected_one(self):
        """Pins aisef2/app/feedback.py::retry_feedback [54]. Not today's journals: a DEVELOPER failure at the candidate
        is CONTRACT_UNSATISFIED or SUBJECT_ABSENT_AT_CANDIDATE (control/routing.py L82-83), so there the proof's
        verdict is never the expected one; the format ties neither failure/observed to a proof's verdict."""
        self.assertTrue(ADVICE.strip(), "the advice's opening words are the stem both assertions look for")
        expected = self.expected()
        other = "REFUTED" if expected != "REFUTED" else "SATISFIED"
        self.assertIn(feedback.REFUTED.format(verdict=other), self.proved(other))
        self.assertNotIn(ADVICE, self.proved(expected))

    def test_the_expected_verdict_is_the_plans_for_that_criterion_not_a_constant(self):
        """Also pins [54]: where the plan expects REFUTED (what a MUST_NOT_HOLD contract compiles to,
        product/compiler.py) REFUTED is the expected verdict and gets no advice, while SATISFIED is the verdict the
        developer is told the candidate remains. The one-contract fixture expects SATISFIED, so on it alone a guard
        that compared with the constant SATISFIED would pass."""
        spec = self.spec()
        expects_refuted = types.SimpleNamespace(id=spec.id, contract_id=spec.contract_id, probe_id=spec.probe_id,
                                                candidate_expectation=BehaviorVerdict.REFUTED)
        project = dataclasses.replace(self.project, specs={spec.id: expects_refuted})
        self.assertIn(feedback.REFUTED.format(verdict="SATISFIED"), self.proved("SATISFIED", project))
        self.assertNotIn(ADVICE, self.proved("REFUTED", project))

    def test_a_proof_that_carries_no_verdict_is_told_without_advice_and_without_raising(self):
        """Pins [53]. The format types a probe record only as an object and a proof's verdict as optional, present
        exactly when the two agreed results carry one (format3._verified): two agreeing results with a null verdict
        make a proof with none. The kernel's writers cannot produce it (Executed types the verdict)."""
        told = self.proved(None)
        self.assertIn("CONTRACT_UNSATISFIED", told)
        self.assertNotIn(ADVICE, told)


if __name__ == "__main__":
    unittest.main()
