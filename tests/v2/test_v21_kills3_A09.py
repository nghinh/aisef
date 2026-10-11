"""V2.1 (owner B-03, kill round 3, batch A09): what `aisef2/app/lineage.py` reads out of a run directory — which session
streams are a request's own, and whether a journal's tail is torn.

Offline and portable: the journals are real format-3 journals written to a temporary run directory (the reader validates
them), the session streams are files of one `step_finish` line; no client, provider or git is involved."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import lineage  # noqa: E402
from aisef2.journal.event import GENESIS, Event, carried, encode, link  # noqa: E402

SHA = "a" * 40
STEP = json.dumps({"type": "step_finish", "part": {"tokens": {"input": 10, "output": 2}}}) + "\n"

PLAN = ("plan/frozen", {"plan_id": "PLAN-1", "plan_hash": "b" * 64, "roles": {"C1": "INTRODUCE", "C2": "INTRODUCE"}})


def begun(story: str, criterion: str) -> list[tuple]:
    return [("story/begin", {"story_id": story, "parent": SHA}),
            ("story/admitted", {"story_id": story, "parent": SHA, "admitted": True, "developer_call_permitted": True,
                                "dispositions": {criterion: "READY"}})]


def request(story: str, criterion: str, owner: str) -> tuple:
    return ("provider/request", {"story_id": story, "criteria": [criterion], "budget_owner": owner})


def result(story: str, request_seq: int) -> tuple:
    return ("provider/result", {"story_id": story, "outcome": "COMPLETED", "synthetic": False, "detail": ""}, (request_seq,))


def journal_text(*specs: tuple) -> str:
    """The stored text of a format-3 journal: run/begin, then the (type, data[, cited seqs]) specs, one line each."""
    rows = [("run/begin", {"journal_format": 3, "run_id": "a09"}, ()), *((s[0], s[1], s[2] if len(s) > 2 else ()) for s in specs)]
    out, prev = [], GENESIS
    for n, (type_, data, cites) in enumerate(rows):
        event = Event(n, type_, carried(type_, data), float(n), False, tuple(cites))
        prev = link(prev, event)
        out.append(encode(event, prev))
    return "".join(out)


class RunDirectory(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.run_dir = pathlib.Path(tmp.name) / "first"
        (self.run_dir / lineage.JOURNAL).parent.mkdir(parents=True)
        (self.run_dir / "sessions").mkdir()

    def journal(self, text: str) -> None:
        (self.run_dir / lineage.JOURNAL).write_text(text, encoding="utf-8", newline="")

    def stream(self, name: str) -> None:
        (self.run_dir / "sessions" / name).write_text(STEP, encoding="utf-8")


class InFlightRequestAttribution(RunDirectory):
    """A provider request with no result is unknown spend only when a session stream of ITS story and role exists
    (module docstring: "whose session stream exists"); a stream named after another story is that story's. Unknown spend
    stops a continuation's paid work until the operator accepts it, so a stream attributed to the wrong request is a
    spurious stop, and the accepted list the record keeps names a request that spent nothing unknown.

    Stream names are `{story_id}.{role}.{attempt}.jsonl` and a story id is any string of the bundle: story `api` has a
    stream `api.developer.1.jsonl`, story `api.developers-guide` has `api.developers-guide.reviewer.1.jsonl`.

    Pins aisef2/app/lineage.py::account_of [52]."""

    SPECS = (PLAN, *begun("api", "C1"), request("api", "C1", "DEVELOPER"),                       # seq 4: never answered
             *begun("api.developers-guide", "C2"), request("api.developers-guide", "C2", "REVIEW"),
             result("api.developers-guide", 7))                                                  # seq 7 answered

    def setUp(self) -> None:
        super().setUp()
        self.journal(journal_text(*self.SPECS))

    def test_a_stream_of_another_story_is_not_the_requests_own(self):
        self.stream("api.developers-guide.reviewer.1.jsonl")     # the other story's review: begins "api.developer"
        self.assertEqual(lineage.account_of(self.run_dir)["unaccounted"], [])

    def test_its_own_stream_makes_it_unknown_spend(self):
        self.stream("api.developers-guide.reviewer.1.jsonl")
        self.stream("api.developer.1.jsonl")
        unknown = lineage.account_of(self.run_dir)["unaccounted"]
        self.assertEqual(len(unknown), 1, unknown)
        for element in ("api", "DEVELOPER"):                      # which request: its story and its budget owner
            self.assertIn(element, unknown[0])
        self.assertRegex(unknown[0], r"\b4\b")                    # and its seq in the journal


class TornTail(RunDirectory):
    """`events_of` returns what its docstring says: the journal's events and whether its tail is torn (an append that did
    not complete). A torn tail is the verified prefix plus the flag: the events of the complete journal, flagged.

    Pins aisef2/app/lineage.py::events_of [2]."""

    SPECS = (PLAN, *begun("api", "C1"), request("api", "C1", "DEVELOPER"))

    def test_the_events_and_whether_the_tail_is_torn(self):
        whole = journal_text(*self.SPECS)
        self.journal(whole)
        events, torn = lineage.events_of(self.run_dir)
        self.assertEqual([e.type for e in events], ["run/begin", "plan/frozen", "story/begin", "story/admitted",
                                                    "provider/request"])
        self.assertIs(torn, False)
        next_line = journal_text(*self.SPECS, result("api", 4)).split("\n")[-2]
        self.journal(whole + next_line[: len(next_line) // 2])    # the writer died in the middle of the next append
        got = lineage.events_of(self.run_dir)
        self.assertEqual(len(got), 2)
        self.assertEqual([e.seq for e in got[0]], [e.seq for e in events])
        self.assertIs(got[1], True)


if __name__ == "__main__":
    unittest.main()
