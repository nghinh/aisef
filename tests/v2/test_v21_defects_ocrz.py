"""V2.1 (owner B-03, kill round 3, fix cluster `ocrz`): Reviewer._ocr reads the changed paths NUL-separated.

`required` (the story's changed product paths) is the scope AISEF computes itself and checks OCR's manifest against
(app/review_ocr: "never taken from OCR"). Under git's default `core.quotepath` a path holding a byte >= 0x80, a
control character, a quote or a backslash is printed C-quoted (`"app/caf\\303\\251.py"`): its first path component
read as `"app`, which is no product root, so the row was dropped and the review's own scope omitted a file the
candidate changed - and coverage could be COMPLETE with OCR having completed only the ASCII files.

OCR is the one stand-in (a `ProcessRange` that writes the documents OCR writes from a scripted scenario); git, the
repository, the budget and the coverage judgement are real. The names live in the index and the commit only, so no
file of that name is made on the filesystem (and a host whose git refuses a name skips the test that needs it)."""

from __future__ import annotations

import hashlib
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

ASCII = ("app/cli.py", "app/util.py")


class EveryChangedPathIsInTheReviewsScope(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.repo = self.tmp / "repo"
        self.base = e2e.make_repo(self.repo)          # git's own defaults: core.quotepath is not set
        self.project = bundle.load(e2e.project_bundle(self.base))
        self.logs = self.tmp / "out" / "sessions"
        self.exe = self.tmp / "ocr"
        self.exe.write_bytes(b"the pinned binary\n")
        self.parent = self.base
        self.attempt = 0                              # a session's stream is never overwritten: one attempt per review

    def commit(self, message: str, *, add=(), remove=()) -> str:
        """A commit whose index adds `add` (each a copy of app/calc.py's blob) and removes `remove`; its revision."""
        blob = e2e.git(self.repo, "hash-object", "-w", "app/calc.py")
        try:
            for name in add:
                e2e.git(self.repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{name}")
            for name in remove:
                e2e.git(self.repo, "update-index", "--force-remove", "--", name)
        except subprocess.CalledProcessError:
            self.skipTest("this git refuses a path of that name")
        e2e.git(self.repo, "commit", "-q", "-m", message)
        return e2e.git(self.repo, "rev-parse", "HEAD")

    def reviewer(self) -> ad.Reviewer:
        events = [types.SimpleNamespace(type="story/begin", data={"story_id": "S1", "parent": self.parent})]
        limits = {"provider_requests": 100, "turns": 100, "input_tokens": 10 ** 7, "output_tokens": 10 ** 7}
        budget = client.Budget(limits, dict.fromkeys(limits, 0), self.logs, lambda: 50)
        review = {"policy": "advisory", "min_severity": "high", "finder": "ocr", "given": True,
                  "ocr": {"exe": str(self.exe), "sha256": hashlib.sha256(self.exe.read_bytes()).hexdigest(),
                          "timeout_min": 1, "max_tokens": 4000}}
        route = {"url": "http://127.0.0.1:9/v1", "token": "sk-test-not-a-key", "model": "model-1"}
        return ad.Reviewer(types.SimpleNamespace(events=events), self.project, self.logs, {"budget": budget}, 5.0,
                           review=review, route=route)

    def review(self, completed, head: str) -> tuple[list, dict, str]:
        self.attempt += 1
        with mock.patch.object(ad, "ProcessRange", _Finder(completed)):
            return self.reviewer()._ocr(types.SimpleNamespace(story_id="S1", root=str(self.repo)), self.attempt, head)

    def test_a_non_ascii_product_path_is_required_whatever_the_quotepath(self):
        """The two non-ASCII names (one under each product root) are required, whole, next to the ASCII ones, under
        git's default and under either value the repository's own configuration may set."""
        names = ["app/café.py", "tests/ünit.py", *ASCII]
        head = self.commit("a non-ASCII name", add=names)
        for quotepath in (None, "false", "true"):
            if quotepath:
                e2e.git(self.repo, "config", "core.quotepath", quotepath)
            with self.subTest(quotepath=quotepath):
                _, s, detail = self.review([], head)
                self.assertEqual(s["required"], sorted(names), detail)

    def test_a_name_git_always_quotes_is_required_whole(self):
        """A U+2028 (also a line break for str.splitlines), a TAB, a LF and a double quote in a name: git quotes each
        whatever core.quotepath says, and the quoted text names no product root."""
        names = ["app/a b.py", "app/t\tab.py", "app/n\nl.py", 'app/q"u.py']
        head = self.commit("names git quotes", add=names)
        _, s, detail = self.review([], head)
        self.assertEqual(s["required"], sorted(names), detail)

    def test_a_name_with_a_space_is_required_whole(self):
        """Pin (passes before the fix too): a space is not what git quotes, and the row must not be cut at it."""
        head = self.commit("a name with a space", add=["app/with space.py"])
        _, s, detail = self.review([], head)
        self.assertEqual(s["required"], ["app/with space.py"], detail)

    def test_a_rename_to_a_non_ascii_name_requires_the_new_path_and_lists_the_old_one_deleted(self):
        """git is asked with --no-renames: a rename is its deletion and its addition, each a row of one path."""
        head = self.commit("rename", add=["app/calç.py"], remove=["app/calc.py"])
        _, s, detail = self.review([], head)
        self.assertEqual(s["required"], ["app/calç.py"], detail)
        self.assertEqual(s["deleted"], ["app/calc.py"])

    def test_a_deleted_non_ascii_path_is_listed_whole_and_not_required(self):
        self.parent = self.commit("a non-ASCII name", add=["app/café.py"])
        head = self.commit("the story deletes it", remove=["app/café.py"])
        _, s, detail = self.review([], head)
        self.assertEqual(s["deleted"], ["app/café.py"], detail)
        self.assertEqual(s["required"], [])

    def test_a_non_ascii_path_outside_the_product_roots_is_not_in_scope(self):
        """Pin (passes before the fix too): only the product roots are the review's scope."""
        head = self.commit("a name outside", add=["docs/café.md", *ASCII])
        _, s, detail = self.review([], head)
        self.assertEqual(s["required"], sorted(ASCII), detail)
        self.assertEqual(s["deleted"], [])

    def test_a_review_that_completed_only_the_ascii_files_is_not_complete(self):
        """The consumer's reliance: OCR completing the ASCII files of a change that also holds a non-ASCII product file
        is INDETERMINATE and says which file it did not review; completing it too is COMPLETE."""
        head = self.commit("a non-ASCII name", add=["app/café.py", *ASCII])
        _, s, detail = self.review(ASCII, head)
        self.assertEqual(s["coverage"]["status"], review_ocr.INDETERMINATE, detail)
        self.assertTrue(any("app/café.py" in r for r in s["coverage"]["reasons"]), s["coverage"]["reasons"])
        _, s, detail = self.review([*ASCII, "app/café.py"], head)
        self.assertEqual(s["coverage"]["status"], review_ocr.COMPLETE, detail)

    def test_a_name_holding_a_carriage_return_is_never_silently_out_of_the_review(self):
        """Whatever the path is read as (the shared git helper reads stdout as text, which turns a CR into a LF),
        OCR having completed only the ASCII files is not COMPLETE: the file is in `required`."""
        head = self.commit("a name with a CR", add=["app/c\rr.py", *ASCII])
        _, s, detail = self.review(ASCII, head)
        self.assertEqual(len(s["required"]), 3, detail)
        self.assertNotEqual(s["coverage"]["status"], review_ocr.COMPLETE, detail)

    def test_output_that_is_not_rows_of_a_status_and_one_path_is_refused_with_its_cause(self):
        """A row this reader does not know (a rename or copy row carries two paths; a dangling status) is refused
        before any session starts, never read as another row's path."""
        head = self.commit("a change", add=["app/new.py"])
        for text in ("R100\0app/old.py\0app/new.py\0", "R100\0app/old.py\0", "A\0app/new.py\0M\0"):
            with self.subTest(text=text):
                done = subprocess.CompletedProcess([], 0, text, "")
                with mock.patch.object(ad, "git", return_value=done), self.assertRaises(CapabilityUnrunnable) as cm:
                    self.review([], head)
                self.assertIn("git diff", str(cm.exception))
                self.assertFalse(self.logs.exists())


if __name__ == "__main__":
    unittest.main()
