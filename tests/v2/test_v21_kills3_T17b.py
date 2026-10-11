"""Mutation-survivor batch T17b (V2.1, owner directive B-03): what a retrying developer is told about the failures
the kernel observed (aisef2/app/feedback.py::retry_feedback, H-RETRY-001).

The text is prompt only — no decision reads it — but the developer acts on it: it must say WHICH criterion failed
(the story, the criterion and its role, the requirement, the requirements path and section, the clause and its text),
WHICH proof decided it (contract, ProductProofSpec, probe, subject, the candidate revision, the probe status, the
verdict against the expectation, whether the verifier agrees) and WHERE in the journal. Every identifier must stay its
own token (a path fused with a section or a revision fused with a status names nothing), and N failures must be N
bullets, each with its own indented continuation lines.

The journals are written in the kernel's order (orchestrate/proof.py: two probe/evaluated, then proof/verified;
story_runner `_fail`: failure/observed; orchestrate/review.py: gate/check rows `<story>:review:<finding>`), the
bundle is the e2e fixture's, the function is called directly: no provider, no git, nothing but the journal's events
and the bundle's public facts. Identifiers are asserted as delimited tokens in order, not the connecting prose."""

from __future__ import annotations

import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, feedback  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402

SECTION = "§3.2 Totals"
CAND_A, CAND_B = "3f2a9c0d" * 5, "9b8a7c6d" * 5       # two different 40-hex revisions
PARENT = "e" * 40


def project(section: str = SECTION):
    """The e2e fixture's bundle (one story S1, one criterion C-ADD, INTRODUCE, expectation SATISFIED) whose fact for
    C-ADD names `section` — the public facts are strings; "" is a requirement with no section."""
    data = e2e.project_bundle("a" * 40)
    data["facts"]["C-ADD"]["section"] = section
    return bundle.load(data)


def spec_of(p):
    return p.specs[next(o.product_proof_spec_id for o in p.plan.obligations)]


def attempt(p, begin: int, *, candidate: str = CAND_A, agree: bool = True, code: str = "CONTRACT_UNSATISFIED",
            owner: str = "DEVELOPER") -> list:
    """One attempt of S1 that ended in a failure of C-ADD, as the kernel writes it from seq `begin`: story/begin, the
    two probe/evaluated records (equal results when the verifier agrees), proof/verified (the verdict only when they
    agree, `verified_payload`), failure/observed with the detail story_runner gives a proof's failure."""
    spec, about = spec_of(p), {"story_id": "S1", "criterion_id": "C-ADD"}
    results = [{"behavior_verdict": "REFUTED", "reason": "returned 6, expected 5"}] * 2 if agree else \
        [{"behavior_verdict": "SATISFIED", "reason": "returned 5"}, {"behavior_verdict": "REFUTED", "reason": "returned 6"}]
    proof = {**about, "spec_id": spec.id, "semantic_hash": spec.semantic_hash, "candidate": candidate, "agreement": agree}
    if agree:
        proof["verdict"] = "REFUTED"
    return [(begin, "story/begin", {"story_id": "S1", "parent": PARENT}),
            *((begin + 1 + i, "probe/evaluated", {**about, "record": {"spec_id": spec.id, "revision": candidate, "result": r}})
              for i, r in enumerate(results)),
            (begin + 3, "proof/verified", proof),
            (begin + 4, "failure/observed", {"story_id": "S1", "code": code, "owner": owner,
                                             "detail": f"proof of C-ADD: {code}"})]


def review_attempt(begin: int, details: list[str]) -> list:
    """One attempt of S1 that stopped at the review: the REVIEW-budget request and result, one gate/check row per
    finding (orchestrate/review.py — `{gate, check "S1:review:<id>", passed, detail}`, no story_id; the blocking ones
    failed, an informational one passed), the gate decision and failure/observed REVIEW_FINDING."""
    out = [(begin, "story/begin", {"story_id": "S1", "parent": PARENT}),
           (begin + 1, "provider/request", {"story_id": "S1", "criteria": ["C-ADD"], "budget_owner": "REVIEW"}),
           (begin + 2, "provider/result", {"story_id": "S1", "outcome": "COMPLETED", "synthetic": False,
                                           "detail": f"{len(details) + 1} findings, parsed=True"}),
           (begin + 3, "gate/check", {"gate": "story", "check": "S1:review:F0", "passed": True, "detail": "informational"})]
    for i, d in enumerate(details):
        out.append((begin + 4 + i, "gate/check", {"gate": "story", "check": f"S1:review:F{begin}-{i}", "passed": False, "detail": d}))
    n = begin + 4 + len(details)
    return out + [(n, "gate/decision", {"gate": "story", "passed": False, "projections": ["story_state"]}),
                  (n + 1, "failure/observed", {"story_id": "S1", "code": "REVIEW_FINDING", "owner": "REVIEW",
                                               "detail": "review: REVIEW_FINDING"})]


def rows(text: str) -> list[list[str]]:
    """The told text as its rows: each bullet line ('- ') with the lines that follow it up to the next bullet."""
    out: list[list[str]] = []
    for line in text.splitlines():
        if line.startswith("- "):
            out.append([line])
        elif out:
            out[-1].append(line)
        else:
            out.append([line])
    return out


def tokens(line: str) -> list[str]:
    """The words of a line without the punctuation a sentence puts around them."""
    return [t.strip("()[],;:.") for t in line.split()]


def in_order(case: unittest.TestCase, line: str, elements: list[str]) -> None:
    """Each element is a whole token of `line`, after the one before it: an identifier fused with its neighbour is not
    one (`R-ADDdocs/requirements.md`, `DEVELOPERS1`, `1.1app.calc...`)."""
    toks, at = tokens(line), 0
    for el in elements:
        case.assertIn(el, toks[at:], f"{el!r} is not its own token (after position {at}) of: {line}")
        at += toks[at:].index(el) + 1


class Told(unittest.TestCase):
    def setUp(self) -> None:
        self.p = project()
        self.spec = spec_of(self.p)

    def told(self, events, p=None) -> str:
        return feedback.retry_feedback(events, "S1", p or self.p)

    def row(self, events, p=None) -> list[str]:
        """The one row told for `events`: its bullet line and at least the evidence line of the proof behind it."""
        r = rows(self.told(events, p))
        self.assertEqual(len(r), 1, r)
        self.assertGreaterEqual(len(r[0]), 2, r[0])
        return r[0]


class RequirementsLocation(Told):
    """The developer is pointed at the requirement in the authoritative document: the requirements path, then the
    criterion's section when the fact has one, and the path alone when it has none. Pins
    aisef2/app/feedback.py::retry_feedback [25, 44]."""

    def located(self, row: list[str]) -> str:
        """What the requirement id is followed by in parentheses on the bullet line."""
        found = re.search(rf"\b{re.escape(self.p.facts['C-ADD']['requirement'])} \(([^()]*)\)", row[0])
        self.assertIsNotNone(found, f"the requirement id is not followed by its location: {row[0]}")
        return found.group(1)

    def test_the_section_follows_the_path_as_its_own_tokens(self):
        where = self.located(self.row(attempt(self.p, 10)))
        self.assertEqual(where.split(), [self.p.requirements_path, *SECTION.split()], where)

    def test_a_requirement_with_no_section_is_located_by_the_path_alone(self):
        p = project(section="")
        where = self.located(self.row(attempt(p, 10), p))
        self.assertEqual(where, p.requirements_path)


class RowIdentifiers(Told):
    """Each identifier of a failure's row is a token of its own, in the order the developer reads them: the bullet
    line names the typed failure and its owner, the story, the criterion and its role, the requirement with its path,
    section and clause; the evidence line the contract, spec, probe, subject, candidate and the probe's outcome
    (H-RETRY-001, owner ruling §8). Pins aisef2/app/feedback.py::retry_feedback [67, 68, 69, 70, 71, 72, 73, 74, 76,
    77, 78, 79, 80]."""

    def setUp(self) -> None:
        super().setUp()
        self.row_ = self.row(attempt(self.p, 10))

    def test_the_bullet_line_names_the_failure_the_criterion_and_the_clause(self):
        line = self.row_[0]
        fact = self.p.facts["C-ADD"]
        in_order(self, line, ["CONTRACT_UNSATISFIED", "DEVELOPER", "S1", "C-ADD", "INTRODUCE", fact["requirement"],
                              self.p.requirements_path, *SECTION.split(), fact["clause"]])
        self.assertIn(fact["clause_text"], line)     # the clause text, whole
        # ruling §8: the criterion is told as 'criterion <id> [' — the form release_smoke.feedback_coverage requires
        self.assertIn("criterion C-ADD [", line)

    def test_the_evidence_line_names_the_contract_spec_probe_subject_and_candidate(self):
        spec, line = self.spec, self.row_[1]
        subject = self.p.facts["C-ADD"]["subject"]
        in_order(self, line, [spec.contract_id, spec.id, spec.probe_id, subject, CAND_A, "EXECUTED", "REFUTED",
                              "SATISFIED"])
        self.assertIn(f"subject {subject}", line)      # ruling §8: the subject is told as 'subject <subject>'


class VerdictAgainstExpectation(Told):
    """Owner ruling §8: the evidence line tells the verdict the proof measured against the verdict the contract
    expects, as `verdict V (expected E)` — the form release_smoke.feedback_coverage requires of every obligation. Pins
    aisef2/app/feedback.py::retry_feedback [96, 97, 98, 130]."""

    def test_the_measured_verdict_is_told_against_the_expected_one(self):
        evidence = self.row(attempt(self.p, 10))[1]
        self.assertIn("verdict REFUTED (expected SATISFIED)", evidence)
        self.assertEqual(self.spec.candidate_expectation.value, "SATISFIED")


class CandidateOfTheProof(Told):
    """The row names the revision the proof measured, in full and as its own token — the commit the verdict is about,
    each row its own when one criterion fails in two attempts. Pins aisef2/app/feedback.py::retry_feedback [117]."""

    def test_each_row_carries_its_own_candidate_revision(self):
        r = rows(self.told(attempt(self.p, 10, candidate=CAND_A) + attempt(self.p, 20, candidate=CAND_B)))
        self.assertEqual([len(x) for x in r], [3, 3], r)
        for row, cand, other in ((r[0], CAND_A, CAND_B), (r[1], CAND_B, CAND_A)):
            self.assertIn(cand, tokens(row[1]), row[1])
            self.assertNotIn(other, row[1])


class RowLayout(Told):
    """N failures are N bullet lines ('- '), each followed by its own indented lines — the evidence line, then the
    advice line when the advice applies (an executed, agreed REFUTED proof of the developer's) — so the prompt's
    list reads as a list and the advice is not glued to the evidence. Pins aisef2/app/feedback.py::retry_feedback
    [37, 55, 66, 75]."""

    def test_a_row_is_a_bullet_an_indented_evidence_line_and_an_indented_advice_line(self):
        row = self.row(attempt(self.p, 10))
        self.assertEqual(len(row), 3, row)
        self.assertTrue(row[0].startswith("- CONTRACT_UNSATISFIED"), row[0])
        self.assertTrue(row[1].startswith("  ") and row[2].startswith("  "), row)
        self.assertIn(self.spec.contract_id, tokens(row[1]))      # the evidence is the continuation line, not the bullet
        self.assertNotIn(self.spec.contract_id, tokens(row[0]))
        self.assertIn("REFUTED", tokens(row[2]))                # the advice names the observed verdict

    def test_each_failure_is_its_own_bullet(self):
        text = self.told(attempt(self.p, 10, candidate=CAND_A) + attempt(self.p, 20, candidate=CAND_B))
        lines = text.splitlines()
        self.assertEqual(sum(ln.startswith("- ") for ln in lines), 2, text)
        self.assertTrue(all(ln.startswith(("- ", "  ")) for ln in lines), text)
        self.assertEqual([len(r) for r in rows(text)], [3, 3])


class VerifierAgreement(Told):
    """The evidence line tells whether the independent verifier agreed, as the verifier's agreement: 'agrees' for the
    agreement every retry delivers, 'disagrees' for a proof the two records split on (a story's final failure, replayed
    from a finished journal), with no advice sentence for a disagreement; the agreement is the proof's own flag (a
    proof that agrees on a probe that could not look has no verdict and is still told as agreeing). Pins
    aisef2/app/feedback.py::retry_feedback [46, 81, 99, 100, 120]."""

    def test_an_agreeing_verifier_is_told_as_agreeing(self):
        evidence = self.row(attempt(self.p, 10, agree=True))[1]
        self.assertRegex(evidence, r"\bverifier agrees\b")
        self.assertNotIn("disagrees", evidence)

    def test_a_disagreeing_verifier_is_told_as_disagreeing_and_gets_no_advice(self):
        row = self.row(attempt(self.p, 10, agree=False, code="VERIFIER_DISAGREEMENT", owner="INTEGRATION"))
        self.assertRegex(row[1], r"\bverifier disagrees\b")
        self.assertNotRegex(row[1], r"\bverifier agrees\b")
        self.assertIn("VERIFIER_DISAGREEMENT", tokens(row[0]))
        self.assertEqual(len(row), 2, row)

    def test_the_agreement_is_the_proofs_flag_not_the_presence_of_a_verdict(self):
        # both records agree that the probe could not look (an Unrunnable result has no behavior_verdict): the proof
        # carries agreement true and no verdict (`verified_payload`); the verifier agrees, it is not told as disagreeing
        about = {"story_id": "S1", "criterion_id": "C-ADD"}
        result = {"detail": "the harness could not start the subject"}
        events = [(10, "story/begin", {"story_id": "S1", "parent": PARENT}),
                  *((11 + i, "probe/evaluated", {**about, "record": {"spec_id": self.spec.id, "revision": CAND_A,
                                                                      "result": result}}) for i in range(2)),
                  (13, "proof/verified", {**about, "spec_id": self.spec.id, "semantic_hash": self.spec.semantic_hash,
                                          "candidate": CAND_A, "agreement": True}),
                  (14, "failure/observed", {"story_id": "S1", "code": "PROBE_UNRUNNABLE", "owner": "ENVIRONMENT",
                                            "detail": "proof of C-ADD: PROBE_UNRUNNABLE"})]
        evidence = self.row(events)[1]
        self.assertRegex(evidence, r"\bverifier agrees\b")
        self.assertNotIn("disagrees", evidence)


class ReviewFindingRows(Told):
    """A REVIEW_FINDING failure is followed by the confirmed findings that blocked that attempt — the failing review
    gate/check rows of the attempt, in order, each indented under the bullet it belongs to (the finding and its
    reproducer are the developer's recovery instruction), and not another attempt's. Pins
    aisef2/app/feedback.py::retry_feedback [85]."""

    D1 = 'blocking, corroborated by probe — add(2, 3) returns 6, expected 5; reproducer {"argv": ["2", "3"]}'
    D2 = 'blocking, corroborated by tests — add(0, 0) returns 1, expected 0; reproducer {"argv": ["0", "0"]}'
    D3 = 'blocking, corroborated by probe — add(-1, 1) returns 2, expected 0; reproducer {"argv": ["-1", "1"]}'

    def test_each_blocking_finding_is_indented_under_its_own_failure_in_order(self):
        events = review_attempt(10, [self.D1, self.D2]) + review_attempt(30, [self.D3]) + [
            (50, "story/begin", {"story_id": "S1", "parent": PARENT})]
        r = rows(self.told(events))
        self.assertEqual(len(r), 2, r)
        for row in r:
            self.assertTrue(row[0].startswith("- REVIEW_FINDING"), row[0])
            self.assertTrue(all(ln.startswith("  ") for ln in row[1:]), row)
        self.assertEqual([[ln.strip() for ln in row[1:]] for row in r], [[self.D1, self.D2], [self.D3]])


if __name__ == "__main__":
    unittest.main()
