"""V2.1 (B-03 round 3, WP client): a session's event stream is read by records, and a record ends at a line feed.

`client.read_session` (the budget's and the model reviewer's reading of a session) and `usage.session_tokens` (the
usage account's) cut the stream with `str.splitlines()`. U+2028, U+2029 and U+0085 are legal raw inside a JSON string —
JavaScript's `JSON.stringify` writes them raw — and `splitlines()` ends a line at each of them: the event was cut in
two, neither half parsed, and the event was dropped without a word. A model's text (the reviewer's findings block), an
error (a provider outage), a finished step's tokens (spend) were lost that way.

What is asserted, through the real readers and the real consumers:

* `ReadingAStream`  — `client.events` / `read_session`: an event that holds U+2028, U+2029 or U+0085 is one event; the
  account of a stream that holds one equals the account of the same stream without it; a carriage return is
  whitespace of a record, not the end of one; a line that is no event costs only itself.
* `TheAccounts`     — the budget (`Budget.spend`, `wait_within`'s turn cap) and the usage account (`session_tokens`,
  `usage`) read the same events: they never disagree about a stream.
* `ModelReviewer`   — `Reviewer._model` and `Reviewer.review`: the findings block of a text event that holds a
  separator reaches the review; an error event that holds one is a provider outage, not "no findings".
* `RealSession`     — the same through `client.session` with a client that is a real process (POSIX: a script run by
  its shebang), whose stream is written raw, as JavaScript writes it.

Nothing here runs the real client or reaches a provider."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, client, usage  # noqa: E402
from aisef2.arch.enums import ControlProjection  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402

#: the characters `str.splitlines()` ends a line at that JSON allows raw inside a string (U+0000-U+001F may not be:
#: `\x0b`, `\x0c` and `\x1c`-`\x1e` are escaped by every encoder, so a record never holds them raw)
SEPARATORS = (("U+2028", " "), ("U+2029", " "), ("U+0085", "\u0085"))
LIMITS = {"provider_requests": 99, "turns": 99, "input_tokens": 9999, "output_tokens": 9999}
ZERO = dict.fromkeys(LIMITS, 0)


def record(event: dict) -> str:
    """One record as JavaScript's JSON.stringify writes it: one line, every non-ASCII character raw."""
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    assert "\n" not in line and "\r" not in line
    return line


def text(t: str) -> dict:
    return {"type": "text", "part": {"type": "text", "text": t}}


def step(i: int, o: int, **part) -> dict:
    return {"type": "step_finish", "part": {"type": "step-finish", "reason": "stop", "cost": 0,
                                            "tokens": {"input": i, "output": o, "reasoning": 1, "cache": {"read": 2, "write": 0}},
                                            **part}}


def write(path: pathlib.Path, *lines: str, end: str = "\n") -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(end.join(lines).encode("utf-8") + (end.encode("utf-8") if lines else b""))
    return path


def stream_of(sep: str) -> list[str]:
    """A session: a text that holds `sep` (or a space), a step, a second text, a second step."""
    return [record(text(f"before{sep}after")), record(step(7, 3)), record(text("tail")), record(step(5, 2))]


ACCOUNT = ("error", "turns", "tokens", "steps_without_tokens")


class _Dir(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(os.path.realpath(t.name))


class ReadingAStream(_Dir):
    """Requirement: a session's stream is a sequence of records each ended by a line feed. An event whose strings hold
    U+2028, U+2029 or U+0085 is one event, read whole; nothing else changes — a line that is not a JSON object is no
    event and costs only itself, a trailing carriage return is whitespace."""

    def test_an_event_that_holds_a_separator_is_read_whole(self):
        for label, sep in SEPARATORS:
            with self.subTest(separator=label):
                log = write(self.tmp / f"{label}.jsonl", *stream_of(sep))
                raw = log.read_bytes()
                self.assertIn(sep.encode("utf-8"), raw)                     # the premise: raw in the file ...
                self.assertEqual(raw.count(b"\n"), 4)                       # ... inside one line
                self.assertEqual(client.read_session(log), {
                    "error": None, "text": f"before{sep}aftertail", "turns": 2,
                    "tokens": {"input": 7 + 2 + 5 + 2, "output": 3 + 1 + 2 + 1}, "steps_without_tokens": 0})
                self.assertEqual([e["type"] for e in client.events(log)], ["text", "step_finish", "text", "step_finish"])

    def test_the_account_of_a_stream_with_a_separator_is_the_account_of_the_same_stream_without_it(self):
        plain = client.read_session(write(self.tmp / "plain.jsonl", *stream_of(" ")))
        for label, sep in SEPARATORS:
            with self.subTest(separator=label):
                got = client.read_session(write(self.tmp / f"{label}.jsonl", *stream_of(sep)))
                self.assertEqual({k: got[k] for k in ACCOUNT}, {k: plain[k] for k in ACCOUNT})
                self.assertEqual(plain["turns"], 2)      # and the account is not empty on both sides
                self.assertGreater(plain["tokens"]["input"], 0)

    def test_a_finished_step_that_holds_a_separator_is_counted_not_lost(self):
        """A step's own fields can hold one (`reason`, an id): cut, its tokens were spend nobody counted."""
        for label, sep in SEPARATORS:
            with self.subTest(separator=label):
                log = write(self.tmp / f"{label}.jsonl", record(step(11, 4, reason=f"stop{sep}now")), record(step(1, 1)))
                got = client.read_session(log)
                self.assertEqual((got["turns"], got["tokens"], got["steps_without_tokens"]),
                                 (2, {"input": 11 + 2 + 1 + 2, "output": 4 + 1 + 1 + 1}, 0))
                self.assertEqual(usage.session_tokens(log), {
                    "tokens": {"input": 12, "cache_read": 4, "cache_write": 0, "output": 5, "reasoning": 2},
                    "steps": 2, "steps_without_tokens": 0})

    def test_a_step_without_a_token_report_is_still_counted_blind_next_to_one_that_holds_a_separator(self):
        sep = " "
        log = write(self.tmp / "s.jsonl", record({"type": "step_finish", "part": {"reason": f"a{sep}b"}}), record(step(3, 2)))
        got = client.read_session(log)
        self.assertEqual((got["turns"], got["steps_without_tokens"], got["tokens"]), (2, 1, {"input": 5, "output": 3}))

    def test_an_error_event_that_holds_a_separator_is_the_sessions_error(self):
        for label, sep in SEPARATORS:
            with self.subTest(separator=label):
                err = {"type": "error", "error": {"name": "APIError", "data": {"message": f"bad{sep}gateway", "statusCode": 502}}}
                got = client.read_session(write(self.tmp / f"{label}.jsonl", record(err)))
                self.assertEqual(got["error"], f"APIError: bad{sep}gateway (HTTP 502)")

    def test_a_record_ends_at_a_line_feed_and_a_carriage_return_is_whitespace(self):
        """CRLF-ended records are read; so is a record whose JSON holds a lone carriage return between two tokens (it is
        whitespace there: neither a line end nor a reason to cut the record, as text mode's newline translation did)."""
        crlf = write(self.tmp / "crlf.jsonl", *stream_of(" "), end="\r\n")
        self.assertEqual(client.read_session(crlf)["text"], "before aftertail")
        self.assertEqual(client.read_session(crlf)["turns"], 2)
        spaced = write(self.tmp / "cr.jsonl", record(text("kept")).replace('"part"', '\r"part"', 1), record(step(1, 1)))
        self.assertIn(b"\r", spaced.read_bytes())
        got = client.read_session(spaced)
        self.assertEqual((got["text"], got["turns"]), ("kept", 1))

    def test_a_line_that_is_no_event_costs_only_itself(self):
        """The torn last line of a stream stopped mid-write, a line of the client's own, raw bytes, a JSON line that is
        not an object, a record with a control character raw inside a string (not JSON): each skipped; the events
        around them are counted, and nothing is raised."""
        torn = record(text("lost tail"))[:-6]            # cut inside the string, just after the separator
        lines = [record(text("a")), "client log: starting", "[1, 2]", '{"type": "text", "part": {"text": "x\x0by"}}',
                 record(step(2, 1)), "", record(text("b"))]
        log = write(self.tmp / "s.jsonl", *lines)
        log.write_bytes(log.read_bytes() + b"\xff\xfe not text\n" + torn.encode("utf-8"))
        got = client.read_session(log)
        self.assertEqual((got["text"], got["turns"], got["tokens"]), ("ab", 1, {"input": 4, "output": 2}))
        self.assertEqual([e["type"] for e in client.events(log)], ["text", "step_finish", "text"])

    def test_an_empty_stream_has_no_events(self):
        log = write(self.tmp / "empty.jsonl")
        self.assertEqual(client.events(log), [])
        self.assertEqual(client.read_session(log), {"error": None, "text": "", "turns": 0,
                                                    "tokens": {"input": 0, "output": 0}, "steps_without_tokens": 0})


class TheAccounts(_Dir):
    """Requirement: the budget and the usage account read the same events of a stream, so a stream with a separator
    in it is spent, counted against the ceilings and reported exactly as the same stream without it."""

    def sessions(self, name: str, sep: str) -> pathlib.Path:
        d = self.tmp / name / "sessions"
        write(d / "S1.developer.1.jsonl", *stream_of(sep))
        write(d / "S1.reviewer.1.jsonl", record(text(f"findings{sep}here")), record(step(10, 5, reason=f"stop{sep}")))
        return d

    def test_the_budgets_spend_is_the_same_with_and_without_a_separator(self):
        spent = {}
        for name, sep in (("plain", " "), ("sep", " "), ("nel", "\u0085")):
            spent[name] = client.Budget(LIMITS, ZERO, self.sessions(name, sep), lambda: 2).spend()
        self.assertEqual(spent["sep"], spent["plain"])
        self.assertEqual(spent["nel"], spent["plain"])
        self.assertEqual((spent["sep"]["turns"], spent["sep"]["input_tokens"], spent["sep"]["output_tokens"]), (3, 28, 13))
        self.assertEqual(spent["sep"]["unaccounted"], [])

    def test_the_usage_account_is_the_same_with_and_without_a_separator(self):
        got = {}
        for name, sep in (("plain", " "), ("sep", " ")):
            out = self.sessions(name, sep).parent
            got[name] = usage.usage(out, [], None, {})
        self.assertEqual(got["sep"], got["plain"])
        self.assertEqual(got["sep"]["tokens"], {"input": 22, "cache_read": 6, "cache_write": 0, "output": 10, "reasoning": 3})
        self.assertEqual([s["steps"] for s in got["sep"]["sessions"]], [2, 1])

    def test_the_two_accounts_agree_on_every_stream(self):
        for label, sep in SEPARATORS:
            with self.subTest(separator=label):
                log = write(self.tmp / f"{label}.jsonl", *stream_of(sep), record(step(9, 9, reason=f"x{sep}y")))
                seen, tokens = client.read_session(log), usage.session_tokens(log)
                self.assertEqual(seen["turns"], tokens["steps"])
                self.assertEqual(seen["steps_without_tokens"], tokens["steps_without_tokens"])
                t = tokens["tokens"]
                self.assertEqual(seen["tokens"], {"input": t["input"] + t["cache_read"] + t["cache_write"],
                                                  "output": t["output"] + t["reasoning"]})

    def test_the_turn_cap_counts_a_finished_step_that_holds_a_separator(self):
        """`wait_within` stops a session at its turn cap: a step cut in two was a step that was never counted."""
        sep = " "
        log = write(self.tmp / "logs" / "s.jsonl", record(step(1, 1, reason=f"stop{sep}")), record(step(1, 1, reason=f"stop{sep}")))
        budget = client.Budget(LIMITS, ZERO, self.tmp / "logs", lambda: 1)
        running = types.SimpleNamespace(wait=lambda timeout: None)      # a session that is still running
        code, stopped = client.wait_within(running, log, 2, budget, 2)    # returns at the first look; 2 s only bounds a failure
        self.assertEqual((code, stopped), (None, "session turn cap: 2 turns"))


class _Reviewing(_Dir):
    """A Reviewer over the two-story calc bundle and its repository, its story S1 at attempt 1 (composition: nothing
    of another module's TestCase is inherited)."""

    def setUp(self) -> None:
        super().setUp()
        e2e.make_repo(self.tmp / "repo")
        self.project = bundle.load(e2e.project_bundle("a" * 40))
        self.run = types.SimpleNamespace(events=[], state=lambda proj: {"S1": {"attempt": 1}}
                                         if proj is ControlProjection.STORY_STATE else None)
        self.scope = types.SimpleNamespace(story_id="S1", root=str(self.tmp / "repo"))

    FINDING = {"id": "F-sep", "blocking": True, "severity": "high",
               "summary": "the parser cuts a record at U+2028: it reads   as the end of a line", "reproducer": None}

    def findings_text(self, sep: str) -> str:
        return json.dumps({"findings": [dict(self.FINDING, summary=f"cut at{sep}here")]}, ensure_ascii=False)

    def reviewer(self, kw: dict | None = None, review: dict | None = None) -> ad.Reviewer:
        return ad.Reviewer(self.run, self.project, self.tmp / "logs", kw or {}, 30, review=review)

    def fake_session(self, events: list[str]):
        """`client.session` as it is when the process has ended: the stream is on disk, and the session's record is
        what `client.read_session` — the real reader — makes of it."""
        def session(name, prompt, cwd, log, timeout_s, **kw):
            write(log, *events)
            return {"exit": 0, "timed_out": False, "stopped": None, "started": True, **client.read_session(log),
                    "seconds": 0.0, "log": log.name}
        return session


class ModelReviewer(_Reviewing):
    """Requirement: the model reviewer's findings block reaches the review whatever characters its text holds; an
    error the provider answered with is an outage whatever characters its message holds. Before: a text or error event
    that held U+2028, U+2029 or U+0085 was dropped, the review had "no findings" (`parsed=False`) and the story went on
    as if the reviewer had found nothing."""

    def test_a_findings_block_that_holds_a_separator_is_the_reviews_findings(self):
        for label, sep in SEPARATORS:
            with self.subTest(separator=label):
                events = [record(text(self.findings_text(sep))), record(step(40, 20))]
                with mock.patch.object(client, "session", self.fake_session(events)):
                    found, s, _ = self.reviewer()._model(self.scope, 1)
                self.assertEqual([f["id"] for f in found], ["F-sep"])
                self.assertEqual(found[0]["summary"], f"cut at{sep}here")
                self.assertIs(s["parsed"], True)
                self.assertEqual((s["turns"], s["tokens"]), (1, {"input": 42, "output": 21}))

    def test_the_review_records_the_finding_with_its_statement_whole(self):
        sep = " "
        events = [record(text(self.findings_text(sep))), record(step(40, 20))]
        rev = self.reviewer(review={"policy": "fix-loop", "min_severity": "low", "finder": "model", "ocr": None, "given": True})
        with mock.patch.object(client, "session", self.fake_session(events)):
            reviewed = rev.review(self.scope, ("C-ADD",))
        self.assertEqual([f.id for f in reviewed.findings], ["F-sep"])
        self.assertTrue(reviewed.findings[0].blocking)
        self.assertIn(f"cut at{sep}here", reviewed.findings[0].detail)
        self.assertIn("1 findings", reviewed.detail)
        self.assertIn("parsed=True", reviewed.detail)

    def test_an_error_that_holds_a_separator_is_a_provider_outage_not_no_findings(self):
        sep = " "
        err = {"type": "error", "error": {"name": "APIError", "data": {"message": f"upstream{sep}down", "statusCode": 502}}}
        with mock.patch.object(client, "session", self.fake_session([record(err)])):
            with self.assertRaises(ad.ProviderOutage) as caught:
                self.reviewer()._model(self.scope, 1)
        self.assertIn("APIError", str(caught.exception))
        self.assertIn(f"upstream{sep}down", str(caught.exception))


CLIENT = '''import json, pathlib, sys
here = pathlib.Path(__file__).parent
for ev in json.loads((here / "events.json").read_text(encoding="utf-8")):
    sys.stdout.buffer.write(json.dumps(ev, ensure_ascii=False).encode("utf-8") + b"\\n")
    sys.stdout.buffer.flush()
'''


@unittest.skipUnless(os.name == "posix", "the fake client is a script run by its shebang")
class RealSession(_Reviewing):
    """Requirement: through `client.session` — a real process whose stdout is the stream, written raw — the session
    record holds what the client said, a separator or not."""

    def setUp(self) -> None:
        super().setUp()
        (self.tmp / "bin").mkdir()
        exe = self.tmp / "bin" / "fake-client"
        exe.write_text(f"#!{sys.executable}\n" + CLIENT, encoding="utf-8")
        exe.chmod(0o755)
        self.exe = str(exe)
        self.budget = client.Budget(LIMITS, ZERO, self.tmp / "logs", lambda: 1)

    def kw(self) -> dict:
        return {"model": "p/m", "env": {"PATH": ""}, "budget": self.budget, "turn_cap": 5, "exe": self.exe}

    def says(self, events: list[dict]) -> None:
        (self.tmp / "bin" / "events.json").write_text(json.dumps(events), encoding="utf-8")

    def test_a_session_whose_text_and_tokens_hold_separators_is_recorded_whole(self):
        sep = " "
        self.says([text(f"one{sep}two"), step(30, 6, reason=f"stop{sep}"), text(" three"), step(4, 1)])
        s = client.session("developer S1", "do it", str(self.tmp / "repo"), self.tmp / "logs" / "S1.developer.1.jsonl", 60,
                           **self.kw())
        self.assertEqual((s["exit"], s["error"], s["stopped"]), (0, None, None))
        self.assertEqual(s["text"], f"one{sep}two three")
        self.assertEqual((s["turns"], s["tokens"]), (2, {"input": 30 + 2 + 4 + 2, "output": 6 + 1 + 1 + 1}))
        self.assertIn(sep.encode("utf-8"), (self.tmp / "logs" / "S1.developer.1.jsonl").read_bytes())

    def test_the_reviewer_of_a_real_process_sees_a_findings_block_that_holds_a_separator(self):
        sep = " "
        self.says([text(self.findings_text(sep)), step(40, 20)])
        found, s, _ = self.reviewer(self.kw())._model(self.scope, 1)
        self.assertEqual([f["id"] for f in found], ["F-sep"])
        self.assertEqual(found[0]["summary"], f"cut at{sep}here")
        self.assertIs(s["parsed"], True)
        self.assertEqual(s["log"], "S1.reviewer.1.jsonl")
        spend = self.budget.spend()                 # and the budget re-derives the same turn from the same stream
        self.assertEqual((spend["turns"], spend["unaccounted"]), (1, []))


if __name__ == "__main__":
    unittest.main()
