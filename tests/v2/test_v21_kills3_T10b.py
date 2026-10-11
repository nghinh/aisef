"""V2.1 mutation survivors, batch T10b: the session row Open Code Review's reviewer leaves in the run record.

`Reviewer._ocr` (aisef2/app/adapters.py) appends one row to the reviewer's `sessions` for every review the finder ran;
aisef2/app/run.py writes that list to RUN.json's `sessions` (minus `text`: the stream already holds it). The row is the
record's only account of the finder's session — how it ended, which story and attempt it reviewed, what produced the
review, which stream holds the evidence, what it spent. Nothing on the product path reads it back (`--verify`
re-derives tokens and turns from the streams and binds the record by the manifest), so a wrong or missing field is
caught by no one but a test of the row.

The finder is the fake Open Code Review of tests/v2/test_v21_review_chain.py (a script pinned by its sha256 writing
OCR's documents), with one change: its summary reports cache tokens and its message carries the route's token, so the
spend and the redaction are visible in the row. The review is driven through the public `Reviewer.review` over a real
git checkout and the real budget; a whole `aisef run` per scenario takes ~20 s and adds nothing to the row (run.py only
strips `text`). Nothing reaches a real client, model or provider. POSIX only: the finder is a script started by its
shebang."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
import tempfile
import time
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, client, review_ocr  # noqa: E402
from aisef2.arch.enums import ControlProjection  # noqa: E402
from tests.v2 import test_v21_review_chain as chain  # noqa: E402
from tests.v2.test_app_run import git  # noqa: E402

TOKEN = "sk-test-not-a-key-T10b-0123456789"
MESSAGE = "T10b review message"
#: the keys of a model session's row (client.session's) that the OCR row states on every path, under their names
ROW_KEYS = {"exit", "timed_out", "stopped", "started", "error", "turns", "tokens", "seconds", "log", "redacted",
            "story_id", "attempt", "finder"}


def _finder_source() -> str:
    """The review chain's fake finder, its summary with cache tokens and its message with the route's token."""
    old = '"total_tokens": 360}, "message": "reviewed"}'
    if chain.FAKE_OCR.count(old) != 1:
        raise RuntimeError("the fake finder's document changed: this fixture must follow it")
    return chain.FAKE_OCR.replace(
        old, '"total_tokens": 405, "cache_read_tokens": 40, "cache_write_tokens": 5},\n'
             f'       "message": "{MESSAGE} " + __import__("os").environ["OCR_LLM_TOKEN"]}}')


@unittest.skipUnless(os.name == "posix", "the finder is a script started by its shebang")
class _Finder(unittest.TestCase):
    """A story's candidate in a git checkout, the scripted finder, and a Reviewer over them (no test of its own)."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.repo = self.tmp / "repo"
        (self.repo / "app").mkdir(parents=True)
        (self.repo / "docs").mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "app" / "__init__.py").write_text("")
        (self.repo / "docs" / "requirements.md").write_text(chain.REQUIREMENTS)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "baseline")
        self.base = git(self.repo, "rev-parse", "HEAD")
        for rel, text in chain.answer(chain.FIXED).items():
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text(text)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "candidate")
        self.project = bundle.load(chain.cli_bundle(self.base))
        self.logs = self.tmp / "out" / "sessions"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.ocr = self.bin / "ocr"
        self.ocr.write_text(f"#!{sys.executable}\n" + _finder_source())
        self.ocr.chmod(0o755)

    def review(self, kind: str = "complete", attempt: int = 1, timeout_s: float = 60, raises=None):
        """One review of story S1's candidate by the scripted finder; its reviewer row (the last the Reviewer holds)."""
        (self.bin / "scenarios.json").write_text(json.dumps([{"kind": kind}]), encoding="utf-8")
        run = types.SimpleNamespace(
            events=[types.SimpleNamespace(type="story/begin", data={"story_id": "S1", "parent": self.base})],
            state=lambda proj: {"S1": {"attempt": attempt}} if proj is ControlProjection.STORY_STATE else None)
        budget = client.Budget({"provider_requests": 20, "turns": 50, "input_tokens": 100000, "output_tokens": 10000},
                               dict.fromkeys(client.Budget.KEYS, 0), self.logs, lambda: 0)
        policy = {"policy": "fix-loop", "min_severity": "high", "finder": "ocr",
                  "ocr": {"exe": str(self.ocr), "sha256": hashlib.sha256(self.ocr.read_bytes()).hexdigest(),
                          "timeout_min": 1, "max_tokens": 4000}}
        self.policy = policy
        reviewer = ad.Reviewer(run, self.project, self.logs, {"budget": budget}, timeout_s, review=policy,
                               route={"url": "http://127.0.0.1:9/v1", "token": TOKEN, "model": "model-1",
                                      "env": {"PATH": os.environ["PATH"]}})
        scope = types.SimpleNamespace(story_id="S1", root=str(self.repo))
        began = time.monotonic()
        if raises is None:
            reviewer.review(scope, ())
        else:
            with self.assertRaises(raises):
                reviewer.review(scope, ())
        self.elapsed = time.monotonic() - began     # the whole review call: what the row's `seconds` is a part of
        self.assertEqual(len(reviewer.sessions), 1)
        return reviewer.sessions[0]

    def field(self, row: dict, key: str):
        self.assertIn(key, row, f"the session row names no {key!r}")
        return row[key]

    @staticmethod
    def recorded(row: dict) -> dict:
        """What run.py puts in RUN.json's sessions for this row: every key but `text` (the stream already holds it)."""
        return {k: v for k, v in row.items() if k != "text"}


class HowTheFinderEnded(_Finder):
    """The row says how the finder ended — `exit` its exit status (None when it was stopped at its deadline),
    `timed_out` whether it was, `started` that it ran (a session the budget refused is never a row) — and `stopped`
    that the budget did not stop it, `error` that its stream holds no client error. An auditor reading RUN.json to
    learn why a review gave no coverage, or where an unaccounted spend came from, takes these at their word.

    Pins aisef2/app/adapters.py::Reviewer._ocr [29, 30, 31, 32, 33, 89, 90, 91, 92, 93, 106, 107]"""

    def assert_row(self, row: dict, exit_code, timed_out: bool) -> None:
        self.assertLessEqual(ROW_KEYS, set(row))
        self.assertNotIn("", row)
        self.assertEqual(self.field(row, "exit"), exit_code)
        self.assertIs(self.field(row, "timed_out"), timed_out)
        self.assertIs(self.field(row, "started"), True)
        self.assertIsNone(self.field(row, "stopped"))
        self.assertIsNone(self.field(row, "error"))

    def test_a_review_that_completed(self):
        self.assert_row(self.review(), 0, False)

    def test_a_review_the_provider_failed(self):
        row = self.review("provider", raises=ad.ProviderOutage)       # the fake finder exits 1 with a provider failure
        self.assert_row(row, 1, False)

    def test_a_review_stopped_at_its_deadline(self):
        row = self.review("sleep", timeout_s=3, raises=ad.CapabilityUnrunnable)     # it wrote nothing: no exit status
        self.assert_row(row, None, True)


class WhichSessionThisIs(_Finder):
    """The row names what it is the session of: the story, the attempt (two reviews of one story are told apart), what
    produced the review (the settings' finder kind and the pinned version) and the stream under <out>/sessions that
    holds its evidence — the stream whose turns and tokens the row copies.

    Pins aisef2/app/adapters.py::Reviewer._ocr [38, 40, 41, 43, 98, 100, 101, 103, 179]"""

    def test_a_second_review_of_the_story(self):
        row = self.review(attempt=2)
        self.assertLessEqual(ROW_KEYS, set(row))
        self.assertNotIn("", row)
        self.assertEqual((self.field(row, "story_id"), self.field(row, "attempt")), ("S1", 2))
        kind, _, version = self.field(row, "finder").partition(" ")
        self.assertEqual((kind, version), (self.policy["finder"], review_ocr.OCR["version"]))
        log = self.field(row, "log")
        self.assertEqual(log, "S1.reviewer.2.jsonl")
        self.assertTrue((self.logs / log).is_file())
        seen = client.read_session(self.logs / log)
        self.assertEqual((row["turns"], row["tokens"]), (seen["turns"], seen["tokens"]))


class WhatTheFinderSpent(_Finder):
    """The row accounts the session: its finished steps (`turns`: the finder's one step), its tokens (input counting
    cache reads and writes, output), its wall time (`seconds`: a measurement, so never a value to compare, only part of
    the review call that made it) and how many secret occurrences were removed from its stream (`redacted`: the markers
    the stream now holds), with the stream holding none of them afterwards. The review document's message is the
    stream's text: it is held under `text`, the one key run.py strips, so no session's text reaches RUN.json (under no
    other key, and never with the route's token in it).

    Pins aisef2/app/adapters.py::Reviewer._ocr [35, 36, 37, 39, 94, 95, 96, 97, 99]"""

    def test_a_completed_review(self):
        row = self.review()
        self.assertLessEqual(ROW_KEYS, set(row))
        self.assertNotIn("", row)
        self.assertEqual(self.field(row, "turns"), 1)
        self.assertEqual(self.field(row, "tokens"), {"input": 300 + 40 + 5, "output": 60})
        seconds = self.field(row, "seconds")        # a measurement: the finder's wall time, a part of the call's
        self.assertTrue(isinstance(seconds, (int, float)) and not isinstance(seconds, bool), seconds)
        self.assertTrue(0 <= seconds <= self.elapsed + 0.1, (seconds, self.elapsed))     # (+ the row's rounding to 0.1 s)
        stream = (self.logs / row["log"]).read_text(encoding="utf-8")
        redacted = self.field(row, "redacted")
        self.assertTrue(isinstance(redacted, int) and not isinstance(redacted, bool))
        self.assertGreater(redacted, 0)             # the finder's document carries the route's token, twice in the stream
        self.assertEqual(redacted, stream.count("[REDACTED]"))      # one marker for each occurrence removed
        self.assertIn(MESSAGE, stream)              # the document's message is in the stream ...
        self.assertNotIn(TOKEN, stream)             # ... without the route's token
        self.assertIn("[REDACTED]", stream)
        self.assertNotIn(TOKEN, json.dumps(row))
        self.assertNotIn(MESSAGE, json.dumps(self.recorded(row)))   # ... and it is not in the record


if __name__ == "__main__":
    unittest.main()
