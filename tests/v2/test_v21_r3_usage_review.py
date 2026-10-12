"""V2.1 (owner B-03, round 3, item 4), independent review of WP usage: the two requirements the WP's own tests left to
a wrong implementation.

* "consecutive": `no_progress` compares an attempt with the attempt BEFORE it (the docstring: "consecutive failed
  attempts with the same failures"). A failure set that an older attempt had, and the attempt before this one did not,
  is not a retry that changed nothing. A function that compared with ANY earlier attempt passed every test of the WP
  and of the registered kill files, and the runner's catalogue cannot generate it.
* the boundary sits where the journal is reconstructed, not in the V2.1 usage branch: a record of a release before 2.1
  has no `usage` account at all, and the journal it names is refused all the same. (The WP's tests build only
  records that carry `usage`, so a refusal placed inside that branch would have passed them.)

Offline; journals are written through the real writer in a temporary directory."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import verify  # noqa: E402
from aisef2.arch.enums import EventType as T  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402
from tests.v2.test_v21_r3_usage_no_progress import SHA, TESTS, UNSAT, Script, events_of, repeat, report, written  # noqa: E402


class ConsecutiveMeansTheAttemptBefore(unittest.TestCase):
    def test_a_failure_set_an_older_attempt_had_is_not_a_repeat(self):
        def build(j: Script) -> None:
            j.attempt([UNSAT], "retry")
            j.attempt([TESTS], "retry")
            j.attempt([UNSAT], "rollback")        # the same as attempt 1, which is not the attempt before it
        self.assertEqual(report(build), [])

    def test_the_attempt_before_decides_even_when_an_older_one_matches_too(self):
        def build(j: Script) -> None:
            j.attempt([UNSAT], "retry")
            j.attempt([TESTS], "retry")
            j.attempt([TESTS], "retry")           # repeats attempt 2
            j.attempt([UNSAT], "rollback")        # repeats attempt 1 only: not the one before it
        self.assertEqual(report(build), [repeat("S1", [3], TESTS)])


class TheBoundaryIsWhereTheJournalIsReconstructed(unittest.TestCase):
    """A record of a release before 2.1: no `usage`, no `no_progress`, no evidence manifest. The journal it names breaks
    the lifecycle (a story commits with no admitted attempt) and is chained and schema-valid; the record agrees with
    it, derived from it with the verifier's own functions."""

    def test_a_record_without_a_usage_account_is_refused_by_the_projection(self):
        def delivered_without_admission(j: Script) -> None:
            j.put(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
            a = j.put(T.GATE_CHECK, {"gate": "story:S1", "check": "proof", "passed": True, "detail": "verified"}).seq
            j.put(T.GATE_DECISION, {"gate": "story:S1", "passed": True, "projections": ("story_state",)}, (a,))
            j.commit()
            j.close()

        text = written(delivered_without_admission, checked=False)
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp).resolve() / "out"
            (out / "run" / "journals").mkdir(parents=True)
            data = text.encode("utf-8")
            (out / "run" / "journals" / "aisef-run.jsonl").write_bytes(data)
            project = bundle.load(e2e.project_bundle("a" * 40))
            events = events_of(text)
            outcomes = R.outcomes_from(events)
            verdict, blocked, committed = R.delivery(project, events, outcomes, None, [])
            rec = {"format": R.FORMAT, "bundle_digest": project.digest, "story_errors": [], "budget_stop": None,
                   "failure": None, "story_outcomes": outcomes, "delivery_verdict": verdict,
                   "delivery_blocked_by": blocked, "productproof": R.productproof(project, events, committed),
                   "journal": {"path": "run/journals/aisef-run.jsonl", "sha256": hashlib.sha256(data).hexdigest(),
                               "lines": data.count(b"\n")}}
            self.assertNotIn("usage", rec)
            self.assertEqual(verdict, "PASS", "the record agrees with the journal: that is the forger's best case")
            (out / "RUN.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            v = verify(project, out)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertTrue(any("story_state refuses story/commit" in p for p in v["problems"]), v["problems"])
        self.assertEqual(v["journal_events"], 0)
        self.assertNotEqual(v["delivery_verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
