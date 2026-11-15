"""V2.2 (B-1 gap wave 2): mutation kill tests for Reviewer._ocr (aisef2/app/adapters.py).

One test per surviving mutant of the target. OCR is the one stand-in (the `_Finder` ProcessRange of
tests/v2/test_v21_defects_ocr.py, which writes the documents OCR writes from a scripted scenario); `git` is mocked
with a fixed `diff -z --name-status` emission so the row order is the test's own, not real git's (real git prints
rows path-sorted, which is exactly why the sorted()->list() mutants survived). No repository, no network, no real
binary: the project bundle is built from a literal baseline revision and every subprocess seam is patched."""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, client, review_ocr  # noqa: E402
from aisef2.orchestrate.adapters import CapabilityUnrunnable  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402
from tests.v2.test_v21_defects_ocr import _Finder  # noqa: E402  (the OCR stand-in)

BASE = "a1" * 20     # the story's parent: a literal revision — git is mocked, no repository exists
HEAD = "b2" * 20
#: rows in REVERSE Python-sort order: real git prints them sorted, which masks sorted()->list()
M_REVERSED = "M\0app/util.py\0M\0app/cli.py\0"
D_REVERSED = "D\0app/util.py\0D\0app/cli.py\0"
TOKENS = {"input": 300, "output": 60, "reasoning": 0, "cache": {"read": 0, "write": 0}}   # _Finder's summary, as written


class ReviewerOcrGapKills(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        t = tempfile.TemporaryDirectory()
        cls.addClassCleanup(t.cleanup)
        tmp = pathlib.Path(t.name).resolve()
        cls.project = bundle.load(e2e.project_bundle(BASE))
        cls.exe = tmp / "ocr"
        cls.exe.write_bytes(b"the pinned binary\n")

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.logs = pathlib.Path(t.name).resolve() / "out" / "sessions"

    def review(self, completed, diff: str, kw_extra: dict | None = None) -> tuple[list, dict, str]:
        """rev._ocr with `git diff` mocked to emit `diff` and OCR mocked to have completed `completed`."""
        events = [types.SimpleNamespace(type="story/begin", data={"story_id": "S1", "parent": BASE})]
        limits = {"provider_requests": 100, "turns": 100, "input_tokens": 10 ** 7, "output_tokens": 10 ** 7}
        budget = client.Budget(limits, dict.fromkeys(limits, 0), self.logs, lambda: 50)
        review = {"policy": "advisory", "min_severity": "high", "finder": "ocr", "given": True,
                  "ocr": {"exe": str(self.exe), "sha256": hashlib.sha256(self.exe.read_bytes()).hexdigest(),
                          "timeout_min": 1, "max_tokens": 4000}}
        route = {"url": "http://127.0.0.1:9/v1", "token": "sk-test-not-a-key", "model": "model-1"}
        rev = ad.Reviewer(types.SimpleNamespace(events=events), self.project, self.logs,
                          {"budget": budget, **(kw_extra or {})}, 5.0, review=review, route=route)
        done = subprocess.CompletedProcess([], 0, diff, "")
        with mock.patch.object(ad, "git", return_value=done), \
                mock.patch.object(ad, "ProcessRange", _Finder(completed)):
            return rev._ocr(types.SimpleNamespace(story_id="S1", root="/no/such/checkout"), 1, HEAD)

    def stream(self) -> list[str]:
        """The session stream's lines, as written (no secret occurs in them, so redact rewrote nothing)."""
        text = (self.logs / "S1.reviewer.1.jsonl").read_text(encoding="utf-8")
        return text.splitlines()

    # kills: L239 condition negated
    def test_configured_needles_found_in_the_background_text_refuse_the_review(self):
        """With needles configured and the sealed content present in the OCR background (the project name is formatted
        into it), the review is refused before any session starts; negating `if needles:` skips the scan entirely."""
        with self.assertRaises(CapabilityUnrunnable) as cm:
            self.review([], M_REVERSED, kw_extra={"needles": {self.project.name: "BC-X"}})
        self.assertIn("BC-X", str(cm.exception))        # the hit names the contract, never the needle's value
        self.assertFalse(self.logs.exists())            # refused before any session evidence exists

    # kills: L238 Or swapped
    def test_configured_needles_are_scanned_not_replaced_by_the_empty_default(self):
        """`self.kw.get("needles") or {}` keeps a configured dict; swapping the BoolOp to `and` yields {} for every
        configured dict and None for none, so the refusal below never happens under the mutant."""
        with self.assertRaises(CapabilityUnrunnable) as cm:
            self.review([], M_REVERSED, kw_extra={"needles": {self.project.name: "BC-X"}})
        self.assertIn("the OCR review of S1", str(cm.exception))
        self.assertIn("BC-X", str(cm.exception))

    # kills: L238 string 'needles' emptied
    def test_needles_are_read_from_the_needles_key_and_the_rule_text_is_scanned(self):
        """The needle here occurs in rule_text only ("app/**" is an include pattern built from the product roots):
        reading kw.get("") instead of kw.get("needles") finds no needles and serves the review."""
        with self.assertRaises(CapabilityUnrunnable) as cm:
            self.review([], M_REVERSED, kw_extra={"needles": {"app/**": "BC-RULE"}})
        self.assertIn("BC-RULE", str(cm.exception))
        self.assertFalse(self.logs.exists())

    # kills: L225 sorted() -> list()
    def test_required_is_sorted_not_the_git_row_order(self):
        """`required` is serialized verbatim into the session record (and from there into sealed evidence): it is
        Python-sorted, not whatever order git printed the rows in."""
        _, s, _ = self.review(["app/cli.py", "app/util.py"], M_REVERSED)
        self.assertEqual(s["required"], ["app/cli.py", "app/util.py"])
        self.assertEqual(s["deleted"], [])

    # kills: L285 sorted() -> list()
    def test_deleted_is_sorted_not_the_git_row_order(self):
        """`deleted` has no re-sorting consumer at all — the session record is its only home, so its order is
        directly written file content."""
        _, s, _ = self.review([], D_REVERSED)
        self.assertEqual(s["deleted"], ["app/cli.py", "app/util.py"])
        self.assertEqual(s["required"], [])

    # kills: L269 dict entry 2 dropped
    def test_the_step_finish_tokens_object_declares_reasoning(self):
        """The step_finish line of the session stream (sealed evidence) carries the full token schema, the declared
        `reasoning: 0` included — readers defaulting a missing key to 0 is not license to drop it."""
        self.review(["app/cli.py", "app/util.py"], M_REVERSED)
        parts = [json.loads(line) for line in self.stream()]
        finish = [x for x in parts if x.get("type") == "step_finish"]
        self.assertEqual(len(finish), 1)
        self.assertEqual(finish[0]["part"]["tokens"], TOKENS)

    # kills: L269 string 'reasoning' emptied
    def test_the_step_finish_tokens_key_is_named_reasoning_not_empty(self):
        """Same written-evidence pin: the key is 'reasoning', not '' — a spurious empty key with the declared field
        missing changes the parsed step_finish shape although every total still reads 0."""
        self.review(["app/cli.py", "app/util.py"], M_REVERSED)
        parts = [json.loads(line) for line in self.stream()]
        tokens = next(x["part"]["tokens"] for x in parts if x.get("type") == "step_finish")
        self.assertEqual(tokens, TOKENS)
        self.assertNotIn("", tokens)

    # kills: L259 True->False (the exist_ok=True constant; the parents=True twin is equivalent — L232-233 creates
    # self.logs.parent before L259 on every path that reaches it)
    def test_a_review_runs_when_the_sessions_directory_already_exists(self):
        """Every real run reaches _ocr with the sessions directory already created (the developer stage wrote its
        stream there): mkdir must tolerate it, or no review can ever run."""
        self.logs.mkdir(parents=True)                  # a prior session's stream directory, as client.session leaves it
        _, s, _ = self.review(["app/cli.py", "app/util.py"], M_REVERSED)
        self.assertEqual(s["coverage"]["status"], review_ocr.COMPLETE)

    # kills: L278 True->False
    def test_the_session_stream_lines_are_canonically_serialized(self):
        """The four evidence lines after ocr_started are written with sort_keys=True: the stream is hashed into
        EVIDENCE.json, so the canonical bytes are the pinned behavior, not any parser's reading of them."""
        self.review(["app/cli.py", "app/util.py"], M_REVERSED)
        lines = self.stream()
        self.assertEqual(len(lines), 5)                # ocr_started + the four evidence lines
        for line in lines[1:]:                         # the ocr_started line is written before, not by L278
            self.assertEqual(line, json.dumps(json.loads(line), sort_keys=True))

    # kills: L299 string ')' emptied — WEAK_ASSERT escalation: the kill route is the detail message itself (owner
    # precedent that the journaled detail is a test-asserted observable); the smallest stable substring the mutant
    # destroys is the closing parenthesis after the reasons.
    def test_an_incomplete_review_s_detail_closes_its_reasons_parenthesis(self):
        _, s, detail = self.review([], M_REVERSED)     # nothing completed: INDETERMINATE with reasons, advisory returns
        self.assertEqual(s["coverage"]["status"], review_ocr.INDETERMINATE)
        self.assertTrue(s["coverage"]["reasons"])
        self.assertIn("coverage INDETERMINATE (", detail)
        self.assertTrue(detail.endswith(")"), detail)  # the reasons end with a list repr ']': only L299's ')' can close it


if __name__ == "__main__":
    unittest.main()
