"""V2.1 D4: the controller-built context pack a retrying developer is given (aisef2/app/feedback.context_pack,
docs/v2.1/CONTEXT-PACK.md) — determinism, provenance, bounds, what it never holds (proof material, oracle internals,
another story, the run's secrets, agent text), its label, that no verdict, approval or budget path reads it; replayed on
the recorded 2.0.0 smoke-2 journal and carried through `aisef run` end to end. Offline: no provider, no model."""

from __future__ import annotations

import copy
import json
import pathlib
import random
import re
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, bundle_cli, client, feedback  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402

P, C = "p" * 40, "c" * 40
CITED = re.compile(r"\(journal seq (\d+(?:, \d+)*|\d+–\d+)\)")
CANARY = "CANARY-hidden-7f3a"


def attempt(begin: int, *, parent=P, candidate=C, detail="opencode exit 0, 3 turns", held=("C-ADD",), refuted=(),
            criteria=("C-ADD",), story="S1", extra=(), developer=True) -> list:
    """One ended attempt of `story` as the kernel journals it, from seq `begin`."""
    s, out = begin, []

    def put(kind, **data):
        nonlocal s
        out.append((s, kind, {"story_id": story, **data}))
        s += 1
    put("story/begin", parent=parent)
    put("story/admitted", admitted=True, dispositions=dict.fromkeys(criteria, "READY"))
    if developer:
        put("provider/request", budget_owner="DEVELOPER", criteria=list(criteria))
        put("provider/result", outcome="COMPLETED", synthetic=False, detail=detail)
    for c in held:
        put("probe/evaluated", record={"result": {"behavior_verdict": "SATISFIED"}, "stimulus": CANARY})
        put("proof/verified", candidate=candidate, criterion_id=c, verdict="SATISFIED", agreement=True,
            spec_id="PPS-" + CANARY, semantic_hash=CANARY)
    for c in refuted:
        put("proof/verified", candidate=candidate, criterion_id=c, verdict="REFUTED", agreement=True,
            spec_id="PPS-" + CANARY, semantic_hash=CANARY)
        put("failure/observed", code="CONTRACT_UNSATISFIED", owner="DEVELOPER", detail=f"proof of {c}: CONTRACT_UNSATISFIED")
    for kind, data in extra:
        put(kind, **data)
    put("story/end")
    return out


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.project = bundle.load(e2e.project_bundle("a" * 40))

    def pack(self, events, story="S1", secrets=()):
        return feedback.context_pack(events, story, self.project, secrets)


class Pack(Fixture):
    def test_nothing_ended_means_no_pack(self):
        self.assertEqual(self.pack([]), "")
        self.assertEqual(self.pack([(1, "story/begin", {"story_id": "S1", "parent": P})]), "")
        self.assertEqual(self.pack([(7, "failure/observed", {"story_id": "S1", "code": "X", "owner": "DEVELOPER"})]), "")

    def test_what_an_earlier_attempt_left_is_stated_with_its_journal_seqs(self):
        ev = attempt(10, refuted=("C-ADD",), held=(), criteria=("C-ADD", "C-OTHER")) + \
            attempt(30, candidate=P, detail="the developer changed nothing (exit None, timed out False)", held=("C-ADD",))
        ev.append((50, "story/begin", {"story_id": "S1", "parent": P}))
        text = self.pack(ev)
        self.assertTrue(text.startswith(feedback.PACK_HEAD))
        self.assertIn(f"- this attempt starts again at the parent {P[:12]} (journal seq 50)", text)
        self.assertIn(f"- attempt 1: parent {P[:12]} (journal seq 10); developer result: opencode exit 0, 3 turns "
                      f"(journal seq 13); candidate {C[:12]} (journal seq 14)", text)
        self.assertIn("never proved at that revision (the attempt ended before their proof): C-OTHER (journal seq 10–", text)
        self.assertIn("developer result: the developer changed nothing (exit None, timed out False) (journal seq 33); the "
                      "revision proved was the parent itself — that attempt changed nothing (journal seq 35)", text)
        self.assertIn("held at that revision, the verifier agreeing: C-ADD (1.1) (journal seq 35)", text)

    def test_every_item_cites_journal_events_of_this_story_that_say_what_it_states(self):
        ev = attempt(10, refuted=("C-ADD",), held=("C-X",), criteria=("C-ADD", "C-X", "C-Y")) + attempt(40, candidate=P)
        ev.append((70, "story/begin", {"story_id": "S1", "parent": P}))
        by_seq = {s: (k, d) for s, k, d in ev}
        for line in self.pack(ev).splitlines()[1:]:
            with self.subTest(line=line):
                cites = CITED.findall(line)
                self.assertTrue(cites, line)
                for c in cites:
                    lo, _, hi = c.partition("–")
                    seqs = range(int(lo), int(hi) + 1) if hi else [int(x) for x in c.split(", ")]
                    for s in seqs:
                        self.assertIn(s, by_seq)
                        self.assertEqual(by_seq[s][1].get("story_id"), "S1")
                if "held" in line:
                    self.assertTrue(all(by_seq[int(s)][0] == "proof/verified" and by_seq[int(s)][1]["verdict"] == "SATISFIED"
                                        for s in CITED.findall(line)[0].split(", ")))

    def test_only_the_attempt_s_candidate_counts_and_its_first_proof_of_a_criterion(self):
        merged = (("proof/verified", {"candidate": "m" * 40, "criterion_id": "C-POST", "verdict": "SATISFIED", "agreement": True}),
                  ("proof/verified", {"candidate": C, "criterion_id": "C-ADD", "verdict": "REFUTED", "agreement": True}))
        text = self.pack(attempt(10, criteria=("C-ADD", "C-POST"), extra=merged))
        self.assertIn("held at that revision, the verifier agreeing: C-ADD (1.1) (journal seq 15)", text)
        self.assertIn("never proved at that revision (the attempt ended before their proof): C-POST (journal seq", text)
        self.assertNotIn("m" * 12, text)
        disagreed = attempt(10, held=(), extra=(("proof/verified", {"candidate": C, "criterion_id": "C-ADD",
                                                                    "verdict": "SATISFIED", "agreement": False}),))
        self.assertNotIn("held at that revision", self.pack(disagreed))

    def test_an_identical_journal_gives_identical_bytes_whatever_order_it_arrives_in(self):
        ev = attempt(10, refuted=("C-ADD",), held=("C-Z", "C-B")) + attempt(40, candidate=P)
        once = self.pack(ev)
        shuffled = copy.deepcopy(ev)
        random.Random(4).shuffle(shuffled)
        self.assertEqual(self.pack(json.loads(json.dumps(shuffled))).encode("utf-8"), once.encode("utf-8"))
        self.assertEqual(self.pack(list(ev)), once)

    def test_it_is_bounded(self):
        many = tuple(f"C-{i:03d}" for i in range(200))
        ev = [e for n in range(10) for e in attempt(1000 * n, held=many[:100], criteria=many)]
        text = self.pack(ev)
        self.assertLessEqual(len(text), feedback.PACK_MAX)
        self.assertIn("- 6 earlier attempt(s) not shown (journal seq 0–", text)
        self.assertIn("and 88 more", text)
        self.assertNotIn("- attempt 6:", text)
        self.assertIn("C-011 and 88 more", text)     # PACK_LIST names per line
        self.assertNotIn("C-012", text)
        long = self.pack(attempt(1, detail="x" * 5000, held=many, criteria=many))
        self.assertLessEqual(len(long), feedback.PACK_MAX)
        self.assertIn("x" * 300 + " (journal seq 4)", long)     # one long result cannot crowd out the rest
        self.assertIn("held at that revision", long)
        narrow = mock.patch.multiple(feedback, PACK_MAX=300)
        with narrow:
            cut = self.pack(ev)
        self.assertLessEqual(len(cut), 300)
        self.assertTrue(cut.startswith(feedback.PACK_HEAD + "\n") and cut.endswith(
            "[the context pack stops here: bounded at 300 characters]"), cut)     # whole lines kept, then the mark

    def test_it_never_holds_proof_material_another_story_or_the_run_s_secrets(self):
        secret = "sk-test-0123456789abcdef"
        ev = attempt(10, refuted=("C-ADD",), detail=f"developer outage: auth {secret} rejected", extra=(
            ("gate/check", {"check": "S1:review:F1", "detail": CANARY, "passed": False}),
            ("tool/result", {"detail": CANARY}), ("tests/adequacy", {"reason": CANARY}),
            ("provider/request", {"budget_owner": "REVIEW"}), ("provider/result", {"detail": "review " + CANARY})))
        ev += attempt(100, story="S2", detail=CANARY, candidate="d" * 40)
        text = self.pack(ev, secrets=(secret, ""))
        for hidden in (CANARY, secret, "PPS-", "stimulus", "d" * 12):
            self.assertNotIn(hidden, text)
        self.assertIn("developer outage: auth [REDACTED] rejected", text)
        cut = self.pack(attempt(10, detail="x" * 290 + secret), secrets=(secret,))     # a secret across the 300 cut
        self.assertIn("x" * 290 + "[REDACTED] (journal seq 13)", cut)
        self.assertNotIn(secret[:6], cut)

    def test_a_review_result_is_never_taken_for_the_developer_s(self):
        review = (("provider/request", {"budget_owner": "REVIEW"}), ("provider/result", {"detail": "3 findings"}))
        with_developer, without = self.pack(attempt(10, extra=review)), self.pack(attempt(10, extra=review, developer=False))
        self.assertIn("developer result: opencode exit 0, 3 turns", with_developer)
        self.assertIn("no developer result (journal seq 10–", without)
        for text in (with_developer, without):
            self.assertNotIn("3 findings", text)

    def test_it_is_labelled_context_and_no_verdict_approval_or_budget_path_reads_it(self):
        self.assertIn("context only — no verdict, approval or budget reads it", feedback.PACK_HEAD)
        readers = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "aisef2").rglob("*.py")
                         if "context_pack" in p.read_text(encoding="utf-8"))
        self.assertEqual(readers, ["aisef2/app/adapters.py", "aisef2/app/feedback.py"])
        src = (ROOT / "aisef2/app/adapters.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("context_pack("), 1)
        self.assertIn("feedback.context_pack(events, story_id, self.project", src.split("def implement", 1)[1].split("def ", 1)[0])


class Prompt(Fixture):
    """The developer's prompt on a retry: the pack between what the kernel observed and the instruction."""

    def setUp(self) -> None:
        super().setUp()
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        e2e.make_repo(self.tmp / "repo")
        self.events = []
        self.run = types.SimpleNamespace(events=self.events, state=lambda proj: {"S1": {"attempt": 2}})
        self.prompts = []

        def fake(name, prompt, cwd, log, timeout_s, **kw):
            self.prompts.append(prompt)
            return {"exit": 0, "timed_out": False, "stopped": None, "started": True, "error": None, "text": "",
                    "turns": 1, "tokens": {"input": 1, "output": 1}, "seconds": 0.0, "log": log.name}
        p = mock.patch.object(client, "session", fake)
        p.start()
        self.addCleanup(p.stop)

    def implement(self, events, secrets=()):
        self.events[:] = [types.SimpleNamespace(seq=s, type=k, data=d) for s, k, d in events]
        ad.Developer(self.run, self.project, self.tmp / f"logs{len(self.prompts)}", {"secrets": secrets}, 5).implement(
            "S1", ("C-ADD",), str(self.tmp / "repo"))
        return self.prompts[-1]

    def test_without_an_ended_attempt_the_prompt_is_2_0_s(self):
        failure = [(7, "failure/observed", {"story_id": "S1", "code": "X", "owner": "DEVELOPER"})]
        before = feedback.task(self.project, "S1") + ("\n\nA previous attempt of this story was not accepted; the kernel "
                                                      "observed:\n- X (owner DEVELOPER): \nFix the implementation.")
        self.assertEqual(self.implement(failure), before)

    def test_on_a_retry_the_pack_sits_before_the_instruction(self):
        ev = attempt(10, candidate=P, held=(), detail="the developer changed nothing (exit 0, timed out False)",
                     refuted=("C-ADD",)) + [(30, "story/begin", {"story_id": "S1", "parent": P})]
        prompt = self.implement(ev, secrets=("never-shown-secret",))
        told = feedback.retry_feedback(ev, "S1", self.project)
        pack = feedback.context_pack(ev, "S1", self.project)
        self.assertTrue(pack)
        self.assertTrue(prompt.endswith(f"observed:\n{told}\n{pack}\nFix the implementation."), prompt[-400:])
        self.assertIn("the revision proved was the parent itself — that attempt changed nothing", prompt)


class RecordedSmoke2(unittest.TestCase):
    """Offline replay on recorded evidence: the 2.0.0 release smoke-2's journal (closure-evidence, read only). Its
    STORY-04-02 attempt 3 was told two REFUTED proofs, the second 'at candidate d8bab70…' — the parent itself, attempt 2
    having changed nothing in 80 turns (docs/v2.1/CONTEXT-PACK.md §1). The bundle is migrated (V2-007) in memory."""

    def test_the_pack_states_what_the_journal_knew_at_the_third_request(self):
        root = ROOT / "closure-evidence/v2/release"
        project = bundle.load(bundle_cli.migrate(json.loads((root / "LEDGERLOCK-PROJECT.json").read_text(encoding="utf-8")))[0])
        lines = (root / "smoke-2/run-1/aisef-run.jsonl").read_text(encoding="utf-8").splitlines()
        ev = [(e["seq"], e["type"], e["data"]) for e in (json.loads(x)["event"] for x in lines if x.strip()) if e["seq"] < 1584]
        text = feedback.context_pack(ev, "STORY-04-02", project)
        self.assertIn("- this attempt starts again at the parent d8bab70eaa47 (journal seq 1540)", text)
        self.assertIn("- attempt 1: parent d8bab70eaa47 (journal seq 1318); developer result: opencode exit 0, 12 turns "
                      "(journal seq 1363); candidate 9872144728a3 (journal seq 1371)", text)
        self.assertIn("developer result: the developer changed nothing (exit None, timed out False) (journal seq 1474); "
                      "the revision proved was the parent itself — that attempt changed nothing (journal seq 1482)", text)
        self.assertIn("never proved at that revision (the attempt ended before their proof): S-9-e (R-9/3), S-9-f (R-9/5), "
                      "S-D3-05-01-1 (R-3.3/2) (journal seq 1318–1428)", text)
        self.assertEqual(text.count("held at that revision"), 2)
        self.assertNotIn("PPS-", text)
        self.assertLessEqual(len(text), feedback.PACK_MAX)


TWICE = r'''import json, pathlib, sys
argv = sys.argv[1:]
if argv == ["--version"]:
    print("0.0.0-fake")
    raise SystemExit(0)
here = pathlib.Path(__file__).parent
title, cwd = argv[argv.index("--title") + 1], pathlib.Path(argv[argv.index("--dir") + 1])
if title.startswith("developer"):
    n = len(list(here.glob("prompt-*.txt")))
    (here / f"prompt-{n}.txt").write_text(argv[-1])
    if n:                                   # the first attempt changes nothing; the retry writes the story
        (cwd / "app" / "calc.py").write_text(ADD)
        (cwd / "tests").mkdir(exist_ok=True)
        (cwd / "tests" / "__init__.py").write_text("")
        (cwd / "tests" / "test_add.py").write_text(TEST)
print(json.dumps({"type": "text", "part": {"text": '{"findings": []}' if title.startswith("reviewer") else "done"}}))
print(json.dumps({"type": "step_finish", "part": {"tokens": {"input": 120, "output": 7, "reasoning": 3,
                                                             "cache": {"read": 10, "write": 0}}}}))
'''


@unittest.skipUnless(sys.platform != "win32", "the fake client is a script started by its shebang")
class ThroughTheRun(e2e.ProductBase):
    """M3: `aisef run` (run.execute) with a fake client whose first developer session changes nothing."""

    def test_the_retry_is_told_the_first_attempt_changed_nothing_and_the_journal_says_so_at_the_cited_seqs(self):
        self.client.write_text(f"#!{sys.executable}\nADD = {e2e.ADD!r}\nTEST = {e2e.TEST!r}\n" + TWICE)
        rec = self.execute()
        self.assertEqual(rec["story_outcomes"], {"S1": ["RETRY", "COMMIT"]}, rec.get("failure"))
        first, retry = (self.client.parent / f"prompt-{i}.txt" for i in (0, 1))
        self.assertNotIn(feedback.PACK_HEAD, first.read_text())
        text = retry.read_text()
        self.assertIn(feedback.PACK_HEAD, text)
        self.assertTrue(text.endswith("\nFix the implementation."))
        by_seq = {e.seq: e for e in self.journal().events}
        m = re.search(r"developer result: the developer changed nothing \(exit 0, timed out False\) \(journal seq (\d+)\); "
                      r"the revision proved was the parent itself — that attempt changed nothing \(journal seq (\d+)\)", text)
        self.assertIsNotNone(m, text)
        result, proof = by_seq[int(m[1])], by_seq[int(m[2])]
        self.assertEqual((result.type, result.data["outcome"]), ("provider/result", "FAILED"))
        begin = next(e for e in self.journal().events if e.type == "story/begin")
        self.assertEqual((proof.type, proof.data["candidate"]), ("proof/verified", begin.data["parent"]))
        self.assertEqual(rec["delivery_verdict"], "PASS")
        self.assertNotIn(feedback.PACK_HEAD, (self.tmp / "out" / "run" / "journals" / "aisef-run.jsonl").read_text())


if __name__ == "__main__":
    unittest.main()
