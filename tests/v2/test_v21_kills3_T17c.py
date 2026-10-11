"""V2.1 mutation-survivor batch T17c: `aisef2/app/feedback.py::retry_feedback` (H-RETRY-001) — what a retrying
developer is told about a failed proof and about the failures that are not one, as a pure function of the journal's
`(seq, type, data)` events and the plan's public facts.

No kill file of the target journals a `proof/verified`, so the pairing of a failure with the proof it names was never
exercised. Each journal here is written in the order `story_runner._attempt` writes it (probe records, proof, gate
rows, gate decision, failure), the owner of a failure is the taxonomy's, and the project is the public facts the
function reads (plan obligations, facts, specs, requirements path). Offline: no provider, no git, no client."""

from __future__ import annotations

import pathlib
import re
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import feedback  # noqa: E402
from aisef2.arch.enums import BehaviorVerdict, ObligationRole  # noqa: E402
from aisef2.control.owner import FailureCode, classify  # noqa: E402

CAND_A, CAND_B = "a" * 40, "b" * 40
#: criterion -> (story, role, subject): C-3 is a PRESERVE obligation of S2, a story that committed earlier
CRITERIA = {"C-1": ("S1", ObligationRole.INTRODUCE, "app.calc:add"),
            "C-2": ("S1", ObligationRole.INTRODUCE, "app.calc:sub"),
            "C-3": ("S2", ObligationRole.PRESERVE, "app.text:upper")}


def project() -> types.SimpleNamespace:
    """What `retry_feedback` reads of a bundle's Project: one obligation, one fact record and one spec (own identity,
    expectation SATISFIED) per criterion, and the requirements path."""
    obligations = tuple(types.SimpleNamespace(criterion_id=c, story_id=s, role=r, product_proof_spec_id=f"PPS-{c}")
                        for c, (s, r, _) in CRITERIA.items())
    facts = {c: {"requirement": f"R-{i}", "section": f"§{i}", "clause": f"R-{i}/1", "clause_text": f"the clause of {c}",
                 "subject": subject} for i, (c, (_, _, subject)) in enumerate(CRITERIA.items(), 1)}
    specs = {f"PPS-{c}": types.SimpleNamespace(id=f"PPS-{c}", contract_id=f"BC-{c}", probe_id="probe.python_callable",
                                               candidate_expectation=BehaviorVerdict.SATISFIED) for c in CRITERIA}
    return types.SimpleNamespace(plan=types.SimpleNamespace(obligations=obligations), facts=facts, specs=specs,
                                 requirements_path="docs/requirements.md")


class Journal:
    """Events `(seq, type, data)`, seq from 1, appended in the kernel's order, attempt after attempt."""

    def __init__(self) -> None:
        self.events: list[tuple[int, str, dict]] = []

    def add(self, kind: str, **data) -> int:
        self.events.append((len(self.events) + 1, kind, data))
        return len(self.events)

    def begin(self, story: str) -> int:
        return self.add("story/begin", story_id=story, parent="p" * 40)

    def prove(self, story: str, criterion: str, candidate: str, verdict: str) -> dict:
        """The criterion's two probe records, its proof and its gate row (two agreeing records at `candidate`, as
        orchestrate/proof.prove writes them); the seqs of the first two and of the proof."""
        who = {"story_id": story, "criterion_id": criterion}
        record = {"spec_id": f"PPS-{criterion}", "revision": candidate,
                  "result": {"behavior_verdict": verdict, "reason": f"the probe measured {verdict}"}}
        probes = [self.add("probe/evaluated", **who, record=record) for _ in range(2)]
        proof = self.add("proof/verified", **who, spec_id=f"PPS-{criterion}", semantic_hash="s" * 64,
                         candidate=candidate, agreement=True, verdict=verdict)
        held = verdict == "SATISFIED"
        self.add("gate/check", gate="story", check=f"{story}:proof:{criterion}", passed=held,
                 detail="verified" if held else FailureCode.CONTRACT_UNSATISFIED.value)
        return {"probes": probes, "proof": proof}

    def unverified(self, story: str, criterion: str, candidate: str, code: FailureCode) -> None:
        """A proof that did not become a `proof/verified` (the two records' instruments differ: PROBE_MISMATCH): the two
        probe records and the failing gate row of `orchestrate/proof.prove` + `_attempt`, and no proof event."""
        who = {"story_id": story, "criterion_id": criterion}
        record = {"spec_id": f"PPS-{criterion}", "revision": candidate,
                  "result": {"behavior_verdict": "SATISFIED", "reason": "the probe measured SATISFIED"}}
        for _ in range(2):
            self.add("probe/evaluated", **who, record=record)
        self.add("gate/check", gate="story", check=f"{story}:proof:{criterion}", passed=False, detail=code.value)

    def fail(self, story: str, code: FailureCode, detail: str) -> int:
        """The story's gate decision and the failure the kernel observed, with the taxonomy's owner."""
        self.add("gate/decision", gate="story", passed=False, projections=["story_state"])
        return self.add("failure/observed", story_id=story, code=code.value, owner=classify(code).owner.value,
                        detail=detail)

    def retry(self, story: str) -> None:
        self.add("story/retry", story_id=story)
        self.add("story/dispose", story_id=story)
        self.add("story/end", story_id=story)


def rows(told: str) -> list[str]:
    """One string per `- ` bullet of the feedback: the row and the lines under it."""
    return [r for r in re.split(r"\n(?=- )", told) if r]


def cited(row: str) -> dict[str, list[int]]:
    """The journal seqs a row's evidence line cites, by the role it labels each with: {'the proof': [4], ...}."""
    evidence = row.partition("journal seq ")[2]
    return {label: [int(n) for n in nums.split(", ")] for nums, label in re.findall(r"(\d+(?:, \d+)*) \(([^)]+)\)", evidence)}


class ProofFailureEvidence(unittest.TestCase):
    """H-RETRY-001: a failed proof is told with the evidence that decided it. S1 proves C-2 (held) and then C-1
    (REFUTED) at one candidate, as `_attempt` does — criteria in turn, the loop broken at the first failure — and the
    failure names `proof of C-1`.

    Pins aisef2/app/feedback.py::retry_feedback [47, 48, 49, 50, 121] (the cited seqs and the role each is cited as),
    [83, 84, 90, 91, 112] (the proof and the probe records are found), [101, 102, 103] (the pairing of the failure with
    its criterion's proof, and so every field of the row)."""

    def setUp(self) -> None:
        j = Journal()
        j.begin("S1")
        self.held = j.prove("S1", "C-2", CAND_A, "SATISFIED")
        self.refuted = j.prove("S1", "C-1", CAND_A, "REFUTED")
        self.failure = j.fail("S1", FailureCode.CONTRACT_UNSATISFIED, "proof of C-1: CONTRACT_UNSATISFIED")
        self.journal = j
        self.told = feedback.retry_feedback(j.events, "S1", project())

    def test_the_cited_seqs_are_the_two_probe_records_the_proof_and_this_failure(self) -> None:
        self.assertEqual(len(rows(self.told)), 1, self.told)
        self.assertEqual(cited(self.told), {"the probe records": self.refuted["probes"], "the proof": [self.refuted["proof"]],
                                            "this failure": [self.failure]}, self.told)
        # and each is the journal event it is cited as, of this story and this criterion
        kind = {q: (k, d.get("story_id"), d.get("criterion_id")) for q, k, d in self.journal.events}
        said = {label: [kind[q] for q in seqs] for label, seqs in cited(self.told).items()}
        self.assertEqual(said, {"the probe records": [("probe/evaluated", "S1", "C-1")] * 2,
                                "the proof": [("proof/verified", "S1", "C-1")],
                                "this failure": [("failure/observed", "S1", None)]})

    def test_the_row_states_the_criterion_its_clause_the_candidate_and_what_the_probes_measured(self) -> None:
        for element in ("criterion C-1 [INTRODUCE]", "R-1 (docs/requirements.md §1)", "clause R-1/1", "the clause of C-1",
                        "subject app.calc:add", "contract BC-C-1", "ProductProofSpec PPS-C-1",
                        f"candidate {CAND_A}", "probe status EXECUTED", "verdict REFUTED (expected SATISFIED)"):
            with self.subTest(element=element):
                self.assertIn(element, self.told)
        self.assertTrue(self.told.startswith("- CONTRACT_UNSATISFIED (owner DEVELOPER) "), self.told)

    def test_a_criterion_proved_earlier_in_the_attempt_is_not_what_the_failure_cites(self) -> None:
        for label, seqs in cited(self.told).items():
            with self.subTest(label=label):
                self.assertFalse(set(seqs) & {*self.held["probes"], self.held["proof"]})
        self.assertNotIn("the clause of C-2", self.told)
        self.assertNotIn("verdict SATISFIED", self.told)


class EachFailureIsToldWithItsOwnAttemptsProof(unittest.TestCase):
    """The prompt of attempt 3: C-1 was refuted in attempt 1 at candidate A and again in attempt 2 at candidate B, so
    the journal holds a later proof of the criterion than the first failure. Each row is told with the last proof
    before ITS failure and that proof's own two probe records, in increasing order probe < proof < failure.

    Pins aisef2/app/feedback.py::retry_feedback [60] (the proof is the last one BEFORE the failure), [64] (the probe
    records are the two last before that proof), [83] (a cited proof precedes its failure)."""

    def setUp(self) -> None:
        j = Journal()
        self.attempts = []
        for candidate in (CAND_A, CAND_B):
            j.begin("S1")
            refuted = j.prove("S1", "C-1", candidate, "REFUTED")
            failure = j.fail("S1", FailureCode.CONTRACT_UNSATISFIED, "proof of C-1: CONTRACT_UNSATISFIED")
            j.retry("S1")
            self.attempts.append((candidate, refuted, failure))
        j.begin("S1")                                     # attempt 3 begins; its developer is asked what happened
        self.told = feedback.retry_feedback(j.events, "S1", project())

    def test_every_row_cites_its_own_attempts_records_in_journal_order(self) -> None:
        told = rows(self.told)
        self.assertEqual(len(told), 2, self.told)
        for row, (_, refuted, failure) in zip(told, self.attempts, strict=True):
            with self.subTest(failure=failure):
                self.assertEqual(cited(row), {"the probe records": refuted["probes"], "the proof": [refuted["proof"]],
                                              "this failure": [failure]}, row)
                self.assertLess(max(refuted["probes"]), refuted["proof"])
                self.assertLess(refuted["proof"], failure)

    def test_every_row_states_the_candidate_its_attempt_was_proved_at(self) -> None:
        for row, (candidate, _, _) in zip(rows(self.told), self.attempts, strict=True):
            other = CAND_B if candidate == CAND_A else CAND_A
            with self.subTest(candidate=candidate):
                self.assertIn(f"candidate {candidate}", row)
                self.assertNotIn(other, row)


class PreservedCriterionIsToldWithThisStorysProof(unittest.TestCase):
    """V21-38: a PRESERVE obligation of a committed story is re-proved at the retrying story's candidate under the
    retrying story's id, after the story's own criteria. C-3 (S2's) was proved SATISFIED under S2 at candidate A; S1's
    candidate B refutes it. The row cites S1's records of C-3 — not S2's earlier proof of the same criterion, not the
    proof of S1's own C-1 that came first.

    Pins aisef2/app/feedback.py::retry_feedback [58] (the events are this story's), [59] (they are the failure's
    criterion's)."""

    def setUp(self) -> None:
        j = Journal()
        j.begin("S2")
        self.earlier = j.prove("S2", "C-3", CAND_A, "SATISFIED")
        j.add("story/commit", story_id="S2", revision=CAND_A)
        j.add("story/end", story_id="S2")
        j.begin("S1")
        self.own = j.prove("S1", "C-1", CAND_B, "SATISFIED")
        self.refuted = j.prove("S1", "C-3", CAND_B, "REFUTED")
        self.failure = j.fail("S1", FailureCode.CONTRACT_UNSATISFIED, "proof of C-3: CONTRACT_UNSATISFIED")
        self.told = feedback.retry_feedback(j.events, "S1", project())

    def test_the_row_cites_this_storys_records_of_the_preserved_criterion(self) -> None:
        self.assertEqual(cited(self.told), {"the probe records": self.refuted["probes"], "the proof": [self.refuted["proof"]],
                                            "this failure": [self.failure]}, self.told)

    def test_the_row_states_the_candidate_and_verdict_of_this_story_s_proof(self) -> None:
        self.assertIn("S1, criterion C-3 [PRESERVE]", self.told)
        self.assertIn(f"candidate {CAND_B}", self.told)
        self.assertNotIn(CAND_A, self.told)
        self.assertIn("verdict REFUTED (expected SATISFIED)", self.told)


class ProofThatNeverBecameAProofIsNotToldWithAnotherProof(unittest.TestCase):
    """A proof can fail without a `proof/verified` of its own (PROBE_MISMATCH: the two records are not comparable, no
    proof event). Then the failure has no proof of THIS story for THIS criterion to cite and is told as the bare row —
    the code, the owner and the journaled reason — never with the evidence of another criterion's proof of the same
    story (the criteria that held earlier in the attempt) or of another story's proof of the same criterion (a PRESERVE
    obligation of a committed story): a developer told that the failing criterion's probe EXECUTED, at a candidate, with
    a verdict, from a proof that is not its own would be misled about what was measured.

    Pins aisef2/app/feedback.py::retry_feedback [58] (the records paired with a failure are this story's) and [59]
    (they are this criterion's) — the scoping itself, which the cited-evidence tests above reach only through a
    proof that exists; [101, 102] (the same keys emptied) are pinned there."""

    CODE = FailureCode.PROBE_MISMATCH

    def assertBare(self, told: str, criterion: str) -> None:
        self.assertEqual(len(rows(told)), 1, told)
        self.assertTrue(told.startswith(f"- {self.CODE.value} (owner {classify(self.CODE).owner.value})"), told)
        self.assertIn(f"proof of {criterion}", told)
        for evidence in ("journal seq", "candidate", "probe status", "verdict", "ProductProofSpec", "clause"):
            with self.subTest(evidence=evidence):
                self.assertNotIn(evidence, told)

    def test_a_criterion_that_held_earlier_in_the_attempt_is_not_its_evidence(self) -> None:
        j = Journal()
        j.begin("S1")
        j.prove("S1", "C-1", CAND_A, "SATISFIED")                      # held, then C-2's two records do not compare
        j.unverified("S1", "C-2", CAND_A, self.CODE)
        j.fail("S1", self.CODE, f"proof of C-2: {self.CODE.value}")
        self.assertBare(feedback.retry_feedback(j.events, "S1", project()), "C-2")

    def test_another_storys_proof_of_the_same_criterion_is_not_its_evidence(self) -> None:
        j = Journal()
        j.begin("S2")
        j.prove("S2", "C-3", CAND_A, "SATISFIED")                      # S2 proved C-3 and committed
        j.add("story/commit", story_id="S2", revision=CAND_A)
        j.add("story/end", story_id="S2")
        j.begin("S1")                                                  # S1 re-proves C-3 as a PRESERVE (V21-38)
        j.unverified("S1", "C-3", CAND_B, self.CODE)
        j.fail("S1", self.CODE, f"proof of C-3: {self.CODE.value}")
        self.assertBare(feedback.retry_feedback(j.events, "S1", project()), "C-3")


class FailureThatIsNotAProof(unittest.TestCase):
    """A failure whose detail is not `proof of <criterion>: ...` has no proof to cite: it is told with its code, its
    owner and the typed reason the kernel journaled — the only evidence there is (an engineering-quality verdict, a
    merge outcome, a developer outage), which is what the developer is meant to act on.

    Pins aisef2/app/feedback.py::retry_feedback [57] (the detail is read from the failure's `detail`)."""

    def test_each_row_carries_the_owner_and_the_journaled_reason(self) -> None:
        failures = ((FailureCode.TESTS_INADEQUATE, "engineering quality: TESTS_INADEQUATE"),
                    (FailureCode.PROVIDER_UNAVAILABLE, "developer outage: upstream returned 503 twice"),
                    (FailureCode.MERGE_CONFLICT, "merge: MERGE_CONFLICT"))
        j = Journal()
        j.begin("S1")
        for code, detail in failures:
            j.fail("S1", code, detail)
        told = feedback.retry_feedback(j.events, "S1", project())
        self.assertEqual(len(rows(told)), len(failures), told)
        for row, (code, detail) in zip(rows(told), failures, strict=True):
            with self.subTest(code=code.value):
                self.assertTrue(row.startswith(f"- {code.value} (owner {classify(code).owner.value})"), row)
                self.assertIn(detail, row)


class ReviewFindingBullets(unittest.TestCase):
    """Under a REVIEW_FINDING row the confirmed findings that blocked THAT attempt are listed, as journaled — the
    failing `<story>:review:<id>` rows written between the attempt's `story/begin` and its failure. At the prompt of
    attempt 3 the journal holds two blocked attempts of S1 (F1 and F2, then F3): F3 is all the second bullet lists.

    Pins aisef2/app/feedback.py::retry_feedback [124, 136] (the boundary is this story's own latest begin or failure)."""

    DETAIL = {f: f"blocking, corroborated by probe:probe.cli:REFUTED — {f}'s statement" for f in ("F1", "F2", "F3")}

    def setUp(self) -> None:
        j = Journal()
        for findings in (("F1", "F2"), ("F3",)):
            j.begin("S1")
            j.prove("S1", "C-1", CAND_A, "SATISFIED")
            j.add("provider/request", story_id="S1", criteria=["C-1"], budget_owner="REVIEW")
            j.add("provider/result", story_id="S1", outcome="COMPLETED", synthetic=False, detail="findings, parsed=True")
            for f in findings:
                j.add("gate/check", gate="story", check=f"S1:review:{f}", passed=False, detail=self.DETAIL[f])
            j.add("gate/check", gate="story", check="S1:review:F9", passed=True, detail="informational")
            j.fail("S1", FailureCode.REVIEW_FINDING, "review: REVIEW_FINDING")
            j.retry("S1")
        j.begin("S1")
        self.told = feedback.retry_feedback(j.events, "S1", project())

    def test_each_bullet_lists_only_the_findings_that_blocked_its_attempt(self) -> None:
        told = rows(self.told)
        self.assertEqual(len(told), 2, self.told)
        under = []
        for row in told:
            head, *findings = [line.strip() for line in row.splitlines()]
            self.assertTrue(head.startswith("- REVIEW_FINDING (owner REVIEW)"), row)
            under.append(findings)
        self.assertEqual(under, [[self.DETAIL["F1"], self.DETAIL["F2"]], [self.DETAIL["F3"]]], self.told)


if __name__ == "__main__":
    unittest.main()
