"""V2.1 mutation survivors of aisef2/app/usage.py::usage, round 2 batch R05: what the run's cost status tells the
operator when the cost is not a figure.

`usage()["cost"]["status"]` is the only place that says WHY `value` is `null` (RUN.json is read by the operator; `--verify`
and the lineage re-derive it with the same function and compare, so a status that lost its words is still VERIFIED).
After the preflight fix there are two preflight causes besides an unknown session, and the status must let the reader
tell them apart:

* a preflight request that was sent and never answered (its cost is unknown, never 0): the status names the requests
  and that they were never answered (PreflightRequestNeverAnswered);
* several causes at once: each stays a clause of its own, told apart from the next (SeveralCauses).

Pins aisef2/app/usage.py::usage [94, 118].

`no_progress` 13 and 23 (a story/commit closing an attempt) are not tested here: the module's contract does not say
what a committed attempt that observed failures is, and the owner has not ruled (OPEN, see the batch report). Offline,
no network, no client."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import usage  # noqa: E402

PRICES = {"currency": "USD", "input_per_mtok": 1.0, "cache_read_per_mtok": 0.1, "cache_write_per_mtok": 1.25,
          "output_per_mtok": 4.0, "source": "test table", "effective_date": "2026-10-06"}
#: one finished step of one million uncached input tokens: exactly 1.0 at PRICES
STEP = json.dumps({"type": "step_finish", "part": {"tokens": {"input": 1_000_000, "output": 0, "reasoning": 0,
                                                             "cache": {"read": 0, "write": 0}}}})
BLIND = json.dumps({"type": "step_finish", "part": {}})      # a finished step that reports no tokens
ANSWERED = ('{"n": 1, "event": "sent", "kind": "chat"}\n'
            '{"n": 1, "event": "done", "http": 200, "input_tokens": 1000000, "output_tokens": 0}\n')
#: requests 2 and 3 were written as sent (the ledger line precedes the request) and never got their `done` row
UNANSWERED = ANSWERED + '{"n": 2, "event": "sent", "kind": "chat"}\n{"n": 3, "event": "sent", "kind": "chat"}\n'
UNREADABLE = "{not json"        # a ledger that is there and that the reader refuses


class RunDirectory(unittest.TestCase):
    """A run directory of its own per call: one session of exactly 1.0, a blind session when asked, a ledger when given."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = pathlib.Path(t.name).resolve()
        self.count = 0

    def cost(self, *, blind: bool = False, ledger: str | None = None) -> dict:
        self.count += 1
        out = self.root / f"run-{self.count}"
        (out / "sessions").mkdir(parents=True)
        (out / "sessions" / "S1.developer.1.jsonl").write_text(STEP + "\n", encoding="utf-8")
        if blind:
            (out / "sessions" / "S2.reviewer.1.jsonl").write_text(BLIND + "\n", encoding="utf-8")
        if ledger is not None:
            (out / "preflight").mkdir()
            (out / "preflight" / "LEDGER.jsonl").write_text(ledger, encoding="utf-8")
        return usage.usage(out, [], PRICES, {})["cost"]


class PreflightRequestNeverAnswered(RunDirectory):
    """A preflight request sent and never answered spent an unknown amount: the run's cost is `partial` and its status
    says which requests, and that they were never answered — the cause the operator has to chase, and the one that
    separates it from a ledger the reader cannot read (the status of that one names the ledger). Without the cause the
    status would read `partial: preflight requests [2, 3]`, a list of numbers with nothing said about them.

    Pins aisef2/app/usage.py::usage [94]."""

    def test_the_status_names_the_requests_and_that_they_were_never_answered(self):
        cost = self.cost(ledger=UNANSWERED)
        self.assertIsNone(cost["value"], cost)                  # not 1.0: the unknown is not counted as 0
        self.assertTrue(cost["status"].startswith("partial"), cost)
        for n in (2, 3):                                        # which requests: the answered one is not among them
            self.assertRegex(cost["status"], rf"\b{n}\b")
        self.assertNotRegex(cost["status"], r"\b1\b")
        self.assertIn("never answered", cost["status"])         # what became of them
        self.assertIn("unknown", cost["status"])                # and what that does to the cost: unknown, not a figure

    def test_a_ledger_that_does_not_read_is_another_cause(self):
        status = self.cost(ledger=UNREADABLE)["status"]
        self.assertTrue(status.startswith("partial"), status)
        self.assertIn("ledger", status)
        self.assertNotIn("never answered", status)              # no request is known to have been sent at all


class SeveralCauses(RunDirectory):
    """When more than one thing makes the cost unknown — a session that reported no tokens and a preflight that is not
    known — the status gives both, each as it reads alone, with something between them: the reader can tell one cause
    from the other and count them. The causes are taken from the module's own single-cause statuses, so the test pins
    neither their wording nor the delimiter, only that two causes are two.

    Pins aisef2/app/usage.py::usage [118]."""

    def reasons(self, status: str) -> str:
        head, colon, rest = status.partition(":")
        self.assertEqual((head, colon), ("partial", ":"), status)
        return rest.strip()

    def test_two_causes_are_not_run_together(self):
        for name, ledger in {"a request never answered": UNANSWERED, "a ledger that does not read": UNREADABLE}.items():
            with self.subTest(name):
                session = self.reasons(self.cost(blind=True, ledger=ANSWERED)["status"])      # the sessions alone
                preflight = self.reasons(self.cost(ledger=ledger)["status"])                  # the preflight alone
                both = self.cost(blind=True, ledger=ledger)
                self.assertIsNone(both["value"], both)
                self.assertNotEqual(session, preflight)
                got = self.reasons(both["status"])
                self.assertIn(session, got)
                self.assertIn(preflight, got)
                self.assertGreater(len(got), len(session) + len(preflight))     # a delimiter stands between the two


if __name__ == "__main__":
    unittest.main()
