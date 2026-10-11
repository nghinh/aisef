"""Mutation-survivor batch T17a (V2.1 campaign 2): aisef2/app/feedback.py::retry_feedback and ::context_pack.

Both functions build text a retrying developer is given, from the run's journal only. What these tests pin is what that
reader relies on, through the public function and a journal written in the kernel's order (story_runner,
orchestrate.proof) — no provider, no git, no model:

* `retry_feedback` (H-RETRY-001): whose failures it tells; the probe status and the verdict against the plan's
  expectation it states for a failed proof; and the one instruction a row can carry — inspect the implementation
  against the clause, naming the observed verdict — given only for an executed refutation, owned by the developer,
  that the independent verifier agrees with.
* `context_pack` (V2.1 D4, docs/v2.1/CONTEXT-PACK.md): an attempt that ended before its admission is listed, not a
  crash; a run secret that contains another is replaced whole; the criteria that held are named in name order with
  their seqs in that order; every citation of the pack closes and cites real events of the story.

The project is a stand-in that holds only what the two functions read: plan.obligations, specs, facts and
requirements_path."""

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

P, C = "p" * 40, "c" * 40
CITED = re.compile(r"\(journal seq (\d+(?:, \d+)*|\d+–\d+)\)")
#: more criteria than a pack line names (two beyond PACK_LIST), all S1's, all on a SATISFIED expectation
MANY = tuple(f"C-{i:02d}" for i in range(feedback.PACK_LIST + 2))


def _obligation(criterion: str, story: str, role: str, spec: str):
    return types.SimpleNamespace(criterion_id=criterion, story_id=story, role=types.SimpleNamespace(value=role),
                                 product_proof_spec_id=spec)


def world():
    """Two stories. S1 introduces C-1 (expected SATISFIED), verifies C-4 (a MUST_NOT_HOLD contract: expected REFUTED)
    and the MANY criteria; S2 owns C-3."""
    expected = {"PPS-1": "SATISFIED", "PPS-3": "SATISFIED", "PPS-4": "REFUTED"}
    specs = {sid: types.SimpleNamespace(id=sid, contract_id="BC-" + sid[4:], probe_id="probe.callable",
                                        candidate_expectation=types.SimpleNamespace(value=value))
             for sid, value in expected.items()}
    obligations = [_obligation("C-1", "S1", "INTRODUCE", "PPS-1"), _obligation("C-3", "S2", "PRESERVE", "PPS-3"),
                   _obligation("C-4", "S1", "VERIFY", "PPS-4")]
    obligations += [_obligation(c, "S1", "INTRODUCE", "PPS-1") for c in MANY]
    facts = {c: {"requirement": f"R-{n}", "section": f"§{n}", "clause": f"R-{n}/1", "clause_text": f"text of clause {n}",
                 "subject": f"pkg.mod{n}:fn"} for c, n in (("C-1", 1), ("C-3", 3), ("C-4", 4))}
    return types.SimpleNamespace(plan=types.SimpleNamespace(obligations=tuple(obligations)), specs=specs, facts=facts,
                                 requirements_path="docs/requirements.md")


class Journal:
    """`(seq, type, data)` events appended in the order the kernel journals them."""

    def __init__(self) -> None:
        self.events: list = []

    def add(self, kind: str, story: str = "S1", **data) -> int:
        seq = len(self.events) + 1
        self.events.append((seq, kind, {"story_id": story, **data}))
        return seq


def failed_proof(j: Journal, criterion: str, *, story: str = "S1", code: str = "CONTRACT_UNSATISFIED",
                 owner: str = "DEVELOPER", result: dict | None = None, verdict: str | None = "REFUTED",
                 agreement: bool = True) -> dict:
    """One failed proof as story_runner journals it: the criterion's two probe records, the proof that rests on them,
    the failure that cites it. `result` is what both records carry (an executed one has a behavior_verdict);
    `verdict` is the proof's (absent from the payload when None, as for a probe that did not execute)."""
    result = {"behavior_verdict": "REFUTED", "reason": "measured"} if result is None else result
    record = {"result": result, "revision": C}
    probes = [j.add("probe/evaluated", story, criterion_id=criterion, record=record) for _ in range(2)]
    proof = {"candidate": C, "agreement": agreement, "spec_id": "PPS-" + criterion, "semantic_hash": "f" * 64}
    if verdict is not None:
        proof["verdict"] = verdict
    return {"probes": probes, "proof": j.add("proof/verified", story, criterion_id=criterion, **proof),
            "failure": j.add("failure/observed", story, code=code, owner=owner, detail=f"proof of {criterion}: {code}")}


def passed_proof(j: Journal, criterion: str, *, story: str) -> None:
    for _ in range(2):
        j.add("probe/evaluated", story, criterion_id=criterion,
              record={"result": {"behavior_verdict": "SATISFIED", "reason": "measured"}, "revision": C})
    j.add("proof/verified", story, criterion_id=criterion, candidate=C, agreement=True, verdict="SATISFIED",
          spec_id="PPS-" + criterion, semantic_hash="f" * 64)


def rows_of(text: str) -> list[str]:
    """The rows of a feedback text: a line that starts with '- ' and the indented lines that follow it."""
    rows: list[str] = []
    for line in text.split("\n"):
        if line.startswith("- "):
            rows.append(line)
        elif rows:
            rows[-1] += "\n" + line
    return rows


_HEAD, _TAIL = feedback.REFUTED.split("{verdict}")


def reading(row: str) -> dict:
    """What a developer reads off one failed-proof row: the probe status, the verdict against the expectation, the
    verifier's agreement, and the verdict the advice names (None: the row carries no advice)."""
    status = re.search(r"probe status (not EXECUTED|EXECUTED)\b", row)
    verdict = re.search(r"verdict (\w+) \(expected (\w+)\)", row)
    verifier = re.search(r"the independent verifier (agrees|disagrees)", row)
    advice = re.search(re.escape(_HEAD) + r"(\w+)" + re.escape(_TAIL), row)
    return {"status": status and status[1], "verdict": verdict and (verdict[1], verdict[2]),
            "verifier": verifier and verifier[1], "advice": advice and advice[1]}


def evidence(row: str):
    """The journal seqs a row cites: (the two probe records, the proof, the failure)."""
    m = re.search(r"Evidence: journal seq (\d+(?:, \d+)*) \(the probe records\), (\d+) \(the proof\), "
                  r"(\d+) \(this failure\)", row)
    return m and ([int(x) for x in m[1].split(", ")], int(m[2]), int(m[3]))


class ExecutedRefutation(unittest.TestCase):
    """A failed proof is told with the probe status and the verdict against the plan's expectation for that criterion
    (owner ruling §8), the verifier's agreement and the journal seqs it rests on; an executed refutation owned by the
    developer that the verifier agrees with also carries the instruction to inspect the implementation, naming the
    observed verdict.

    Pins aisef2/app/feedback.py::retry_feedback [34, 45, 65, 92, 93, 95, 118, 129, 135, 140] (what is stated of an
    executed proof) and [6, 35, 36, 51, 52, 82] (the advice is given)."""

    def setUp(self) -> None:
        self.project = world()
        self.j = Journal()
        self.j.add("story/begin", parent=P)

    def told(self, story: str = "S1") -> str:
        (row,) = rows_of(feedback.retry_feedback(self.j.events, story, self.project))
        return row

    def test_it_states_the_status_the_verdict_against_the_expectation_and_the_advice(self):
        seen = failed_proof(self.j, "C-1")
        row = self.told()
        self.assertEqual(reading(row), {"status": "EXECUTED", "verdict": ("REFUTED", "SATISFIED"), "verifier": "agrees",
                                        "advice": "REFUTED"})
        self.assertEqual(evidence(row), (seen["probes"], seen["proof"], seen["failure"]))
        by_seq = {s: k for s, k, _ in self.j.events}
        self.assertEqual([by_seq[s] for s in (*seen["probes"], seen["proof"], seen["failure"])],
                         ["probe/evaluated", "probe/evaluated", "proof/verified", "failure/observed"])

    def test_the_expectation_is_the_plan_s_for_that_criterion_not_a_constant(self):
        """C-4 is a MUST_NOT_HOLD contract: the plan expects REFUTED, so REFUTED is the contract holding (no advice) and
        SATISFIED is the refutation the developer is told about, with that verdict named."""
        for observed, advice in (("SATISFIED", "SATISFIED"), ("REFUTED", None)):
            with self.subTest(observed=observed):
                j = Journal()
                j.add("story/begin", parent=P)
                failed_proof(j, "C-4", result={"behavior_verdict": observed, "reason": "measured"}, verdict=observed)
                (row,) = rows_of(feedback.retry_feedback(j.events, "S1", self.project))
                self.assertEqual(reading(row), {"status": "EXECUTED", "verdict": (observed, "REFUTED"),
                                                "verifier": "agrees", "advice": advice})

    def test_a_subject_the_candidate_does_not_establish_is_advised_with_the_verdict_it_was_observed_to_have(self):
        """SUBJECT_ABSENT_AT_CANDIDATE (routing: CANDIDATE, INDETERMINATE, PRECONDITION_ABSENT) is the developer's too:
        the verdict the advice names is the observed one, not a fixed word."""
        failed_proof(self.j, "C-1", code="SUBJECT_ABSENT_AT_CANDIDATE",
                     result={"behavior_verdict": "INDETERMINATE", "reason": "PRECONDITION_ABSENT"},
                     verdict="INDETERMINATE")
        self.assertEqual(reading(self.told()), {"status": "EXECUTED", "verdict": ("INDETERMINATE", "SATISFIED"),
                                                "verifier": "agrees", "advice": "INDETERMINATE"})


class AdviceIsWithheld(unittest.TestCase):
    """The advice tells the developer to look in its implementation, so it is given only when every ground holds: the
    probe executed (else there is nothing observed to inspect), the verifier agrees (the sentence says so), the
    failure is the developer's (an INTEGRATION-owned executed failure is one the taxonomy refuses to attribute to a
    product cause: control/owner.py NON_CONTROLLER_SIGNAL), and the observed verdict is not the expectation. Each case
    differs from the advised one in exactly one ground. A kernel journal never has one of these grounds without the
    next (a verdict is journaled only for an agreed, executed proof), so the cases that isolate a ground are built by
    hand: the grounds are the function's own, and a row without them would tell the developer something false.

    Pins aisef2/app/feedback.py::retry_feedback [6, 24, 26, 35, 36], and through the advised case the lookups of the
    guard [34, 51, 52, 65, 82, 92, 93, 129, 135, 140]."""

    def setUp(self) -> None:
        self.project = world()

    def row(self, **kw) -> str:
        j = Journal()
        j.add("story/begin", parent=P)
        failed_proof(j, "C-1", **kw)
        (row,) = rows_of(feedback.retry_feedback(j.events, "S1", self.project))
        return row

    def test_the_one_case_that_holds_every_ground_is_advised(self):
        self.assertEqual(reading(self.row())["advice"], "REFUTED")

    def test_each_ground_gates_it(self):
        cases = {
            "the probe did not execute": {"result": {"detail": "harness launch failed"}},
            "the verifier disagrees": {"agreement": False},
            "the owner is not the developer": {"code": "NON_CONTROLLER_SIGNAL", "owner": "INTEGRATION",
                                               "result": {"behavior_verdict": "INDETERMINATE", "reason": "signal"},
                                               "verdict": "INDETERMINATE"},
            "the verdict is the expectation": {"result": {"behavior_verdict": "SATISFIED", "reason": "measured"},
                                               "verdict": "SATISFIED"},
            "the proof carries no verdict": {"verdict": None},
        }
        for name, kw in cases.items():
            with self.subTest(name):
                self.assertIsNone(reading(self.row(**kw))["advice"])


class ProbeThatDidNotRun(unittest.TestCase):
    """PROBE_UNRUNNABLE is ENVIRONMENT-owned and retryable, so its row reaches a retrying developer: the probe records
    carry no behavior_verdict, and the row says the probe was not EXECUTED, states no verdict against the expectation,
    gives no advice, and tells nothing of the records' own detail (H-RETRY-001: no observation detail is invented).

    Pins aisef2/app/feedback.py::retry_feedback [6, 24, 26, 45, 65, 95, 119]."""

    def test_it_is_told_as_not_executed_with_no_verdict_and_no_advice(self):
        j = Journal()
        j.add("story/begin", parent=P)
        seen = failed_proof(j, "C-1", code="PROBE_UNRUNNABLE", owner="ENVIRONMENT",
                            result={"detail": "harness launch failed: ENOENT /scratch/secret-path"}, verdict=None)
        (row,) = rows_of(feedback.retry_feedback(j.events, "S1", world()))
        self.assertEqual(reading(row), {"status": "not EXECUTED", "verdict": None, "verifier": "agrees", "advice": None})
        self.assertEqual(evidence(row), (seen["probes"], seen["proof"], seen["failure"]))
        self.assertNotIn("secret-path", row)


class WhoseFailures(unittest.TestCase):
    """The retrying developer of a story is told that story's failures and no other: not another story's failure (its
    criterion and code stay out), and no row for an event that is not a failure (a story's begin, probe, admission
    and provider records are not rows). Every row cites its own criterion's records only.

    Pins aisef2/app/feedback.py::retry_feedback [10]."""

    def setUp(self) -> None:
        self.project = world()
        j = self.j = Journal()
        j.add("story/begin", "S2", parent=P)
        self.s2 = failed_proof(j, "C-3", story="S2")
        j.add("story/begin", "S1", parent=P)
        j.add("story/admitted", "S1", admitted=True, dispositions={"C-1": "READY"})
        j.add("provider/request", "S1", budget_owner="DEVELOPER", criteria=["C-1"])
        j.add("provider/result", "S1", outcome="COMPLETED", synthetic=False, detail="opencode exit 0, 3 turns")
        passed_proof(j, "C-3", story="S1")      # S2's criterion, preserved at S1's candidate: S1's own record
        self.first = failed_proof(j, "C-1", story="S1")
        j.add("story/end", "S1")
        j.add("story/begin", "S1", parent=P)
        self.second = failed_proof(j, "C-1", story="S1")
        j.add("story/begin", "S1", parent=P)

    def test_a_story_is_told_only_its_own_failures_in_journal_order(self):
        rows = rows_of(feedback.retry_feedback(self.j.events, "S1", self.project))
        self.assertEqual([evidence(r) for r in rows],
                         [(s["probes"], s["proof"], s["failure"]) for s in (self.first, self.second)])
        text = "\n".join(rows)
        for other in ("C-3", "S2", "None"):
            self.assertNotIn(other, text)

    def test_the_other_story_is_told_its_own(self):
        rows = rows_of(feedback.retry_feedback(self.j.events, "S2", self.project))
        self.assertEqual([evidence(r) for r in rows], [(self.s2["probes"], self.s2["proof"], self.s2["failure"])])
        self.assertNotIn("C-1", rows[0])


class PackCase(unittest.TestCase):
    """Fixtures for the context pack (docs/v2.1/CONTEXT-PACK.md) read as the retrying developer reads it: attempt
    lines, the criteria held and not proved, each with its journal seqs. It has no test of its own."""

    def setUp(self) -> None:
        self.project = world()

    def pack(self, j: Journal, secrets=()) -> str:
        return feedback.context_pack(j.events, "S1", self.project, secrets)

    @staticmethod
    def attempt(j: Journal, *, parent: str = P, candidate: str = C, detail: str = "opencode exit 0, 3 turns",
                developer: bool = True, admitted: bool = True, criteria=("C-1",), proved=()) -> dict:
        """One ended attempt as story_runner journals it: begin, admission, the developer's request and result, the
        proofs at the candidate (SATISFIED, the verifier agreeing), the end."""
        seen = {"begin": j.add("story/begin", parent=parent)}
        if admitted:
            j.add("story/admitted", admitted=True, dispositions=dict.fromkeys(criteria, "READY"))
        if developer:
            j.add("provider/request", budget_owner="DEVELOPER", criteria=list(criteria))
            seen["result"] = j.add("provider/result", outcome="COMPLETED", synthetic=False, detail=detail)
        seen["proofs"] = {c: j.add("proof/verified", criterion_id=c, candidate=candidate, verdict="SATISFIED",
                                   agreement=True, spec_id="PPS-1", semantic_hash="f" * 64) for c in proved}
        seen["end"] = j.add("story/end")
        return seen

    @staticmethod
    def block(text: str, n: int) -> list[str]:
        """The pack's lines of attempt `n`: its '- attempt n:' line and the indented lines under it."""
        lines, out = text.split("\n"), []
        for i, line in enumerate(lines):
            if line.startswith(f"- attempt {n}:"):
                out = [line]
                for more in lines[i + 1:]:
                    if not more.startswith("  "):
                        break
                    out.append(more)
        return out


class AttemptThatEndedBeforeAdmission(PackCase):
    """RESOURCE_ACQUISITION_FAILED is journaled before any admission (story_runner: the resources are acquired first),
    so the attempt has a begin, a failure and an end and no story/admitted: it is listed with its range, claims no
    criteria as left unproved, and building the pack does not raise (Developer.implement builds it on the retry path,
    and story_runner handles only ProviderOutage from it: any other exception propagates out of the attempt).

    Pins aisef2/app/feedback.py::context_pack [52, 80]."""

    def test_it_is_listed_and_names_no_criteria(self):
        j = Journal()
        begin = j.add("story/begin", parent=P)
        j.add("gate/check", check="S1:resources", passed=False, detail="resources: scratch")
        j.add("failure/observed", code="RESOURCE_ACQUISITION_FAILED", owner="ENVIRONMENT", detail="resources: scratch")
        j.add("story/retry")
        j.add("story/dispose")
        end = j.add("story/end")
        second = self.attempt(j, criteria=("C-1", "C-4"))      # admitted, ended with no proof recorded
        j.add("story/begin", parent=P)
        text = self.pack(j)
        first = self.block(text, 1)
        self.assertEqual(len(first), 1, first)       # the attempt's own line, no held or no-proof line under it
        self.assertEqual(CITED.findall(first[0]), [str(begin), f"{begin}–{end}"])
        later = self.block(text, 2)                  # an admitted attempt still says which criteria had no proof
        self.assertEqual(len(later), 2, later)
        self.assertIn("no proof recorded", later[1])
        self.assertTrue("C-1" in later[1] and "C-4" in later[1], later[1])
        self.assertEqual(CITED.findall(later[1]), [f"{second['begin']}–{second['end']}"])


class RunSecretsReplacedWhole(PackCase):
    """The developer result is the one free text the pack carries to the model provider, with the run's secrets
    replaced. A secret that contains another must be replaced whole, whichever order the secrets arrive in and
    wherever in the longer one the shorter sits (its start, or after a prefix that sorts the longer one first):
    none of the longer secret's characters beyond the shorter one may stay, at each place the result holds it.

    Pins aisef2/app/feedback.py::context_pack [72]."""

    def test_the_tail_of_a_longer_secret_does_not_survive_a_shorter_one_that_it_contains(self):
        short = "sk-run"
        for long_ in ("sk-run-0123456789", "abc-sk-run-0123456789"):
            j = Journal()
            self.attempt(j, detail=f"developer outage: auth {long_} rejected; again {long_}")
            j.add("story/begin", parent=P)
            for secrets in ((short, long_), (long_, short)):
                with self.subTest(secrets=secrets):
                    text = self.pack(j, secrets)
                    self.assertIn("developer outage: auth [REDACTED] rejected; again [REDACTED]", text)
                    self.assertNotIn("0123456789", text)
                    self.assertNotIn(short, text)


class HeldCriteriaByName(PackCase):
    """docs/v2.1/CONTEXT-PACK.md §2 (deterministic): the criteria that held at an attempt's revision are listed by
    name, the first PACK_LIST of them then 'and N more', each followed in the same order by the seq of its own proof,
    whatever order the proofs were journaled in.

    Pins aisef2/app/feedback.py::context_pack [87]."""

    def test_they_are_named_in_name_order_with_their_own_seqs_whatever_the_journal_order(self):
        j = Journal()
        seen = self.attempt(j, criteria=MANY, proved=tuple(reversed(MANY)))     # C-13 proved first, C-00 last
        j.add("story/begin", parent=P)
        (held,) = [ln for ln in self.pack(j).split("\n") if ln.startswith("  held at that revision")]
        m = re.search(r": (.*) and (\d+) more \(journal seq (\d+(?:, \d+)*)\)$", held)
        self.assertIsNotNone(m, held)
        shown = MANY[:feedback.PACK_LIST]
        self.assertEqual(m[1].split(", "), list(shown))
        self.assertEqual(int(m[2]), len(MANY) - feedback.PACK_LIST)
        self.assertEqual([int(s) for s in m[3].split(", ")], [seen["proofs"][c] for c in shown])


class EveryCitationCloses(PackCase):
    """docs/v2.1/CONTEXT-PACK.md §2: every line of the pack other than its head cites the journal as
    '(journal seq N)', '(journal seq N, M)' or '(journal seq N–M)', each a real event of the story. A citation that
    does not close cannot be read back by seq, and on a line with a second citation the count of '(journal seq'
    exceeds the count of closed ones.

    Pins aisef2/app/feedback.py::context_pack [96, 120]."""

    def test_the_line_for_attempts_not_shown_cites_the_first_begin_to_the_last_omitted_end(self):
        j = Journal()
        seen = [self.attempt(j, parent=chr(ord("a") + n) * 40) for n in range(feedback.PACK_ATTEMPTS + 2)]
        j.add("story/begin", parent=P)
        text = self.pack(j)
        (line,) = [ln for ln in text.split("\n") if "not shown" in ln]
        self.assertEqual(re.match(r"- (\d+) earlier", line)[1], "2")
        self.assertEqual(line.count("(journal seq"), 1)
        self.assertEqual(CITED.findall(line), [f"{seen[0]['begin']}–{seen[1]['end']}"])
        by_seq = {s: k for s, k, _ in j.events}
        self.assertEqual((by_seq[seen[0]["begin"]], by_seq[seen[1]["end"]]), ("story/begin", "story/end"))
        for ln in text.split("\n")[1:]:
            with self.subTest(line=ln[:60]):
                self.assertEqual(ln.count("(journal seq"), len(CITED.findall(ln)), ln)

    def test_an_attempt_with_no_developer_result_cites_its_range_and_every_citation_on_its_line_closes(self):
        j = Journal()
        refused = self.attempt(j, developer=False)                       # admitted, no developer called, nothing proved
        no_work = self.attempt(j, developer=False, candidate=P, proved=("C-1",))     # K-NOWORK: the candidate is the parent
        j.add("story/begin", parent=P)
        text = self.pack(j)
        for n, seen in ((1, refused), (2, no_work)):
            first = self.block(text, n)[0]
            with self.subTest(attempt=n):
                self.assertEqual(first.count("(journal seq"), len(CITED.findall(first)), first)
                self.assertIn(f"{seen['begin']}–{seen['end']}", CITED.findall(first))
        self.assertEqual(self.block(text, 2)[0].count("(journal seq"), 3)       # begin, range, the proof of the parent
        for ln in text.split("\n")[1:]:
            with self.subTest(line=ln[:60]):
                self.assertEqual(ln.count("(journal seq"), len(CITED.findall(ln)), ln)


if __name__ == "__main__":
    unittest.main()
