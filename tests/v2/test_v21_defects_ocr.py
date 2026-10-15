"""V2.1 (owner B-03, kill round 3, fix cluster `ocr`): Reviewer._ocr reads `git diff --name-status` as rows.

`required` (the story's changed product paths) is the scope AISEF computes itself and checks OCR's manifest against
(app/review_ocr: "never taken from OCR"). A path git prints with `core.quotepath=false` (the repository's own
configuration may set it: workspace.INERT_KEY allows it) is printed raw, and U+0085, U+2028 and U+2029 are
characters `str.splitlines` treats as line breaks although git ends a row with "\\n" only: the row of such a path
reached the parser as two lines, the second lost (it holds no tab) and the first read as a shorter path.

OCR is the one stand-in (a `ProcessRange` that writes the documents OCR writes from a scripted scenario); git, the
repository, the budget and the coverage judgement are real. The names live in the index and the commit only, so no
file of that name is made on the filesystem."""

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
from tests.v2 import test_app_run as e2e  # noqa: E402

CHANGED = ("app/cli.py", "app/util.py")
#: (name, the shorter path the old parser invented from it, the character): one changed path per line-break character
SEPARATED = (("app/a\u0085b.py", "app/a"), ("app/c d.py", "app/c"), ("app/e f.py", "app/e"))


#: what the pinned build prints for `version` (app/review_ocr.VERSION_LINE): the identity gate asks it first
VERSION_REPLY = f"open-code-review {review_ocr.OCR['version']} ({review_ocr.OCR['commit'][:7]}) darwin/arm64\n"


class _Process:
    def __init__(self, finder: "_Finder", argv: list[str], output=None) -> None:
        self.finder, self.argv, self.output = finder, argv, output
        self.preview = "--preview" in argv

    def start(self) -> "_Process":
        if self.argv[1:] == ["version"]:      # the identity gate, before any review command: not a review
            self.output.write(VERSION_REPLY)
            self.output.flush()
            return self
        opt = lambda flag: self.argv[self.argv.index(flag) + 1]    # noqa: E731
        base, head, out = opt("--from"), opt("--to"), pathlib.Path(opt("--output"))
        done = [{"item_id": review_ocr.item_id("range", p, p), "path": p} for p in self.finder.completed]
        if self.preview:
            doc = {"files": [{"path": p, "status": "added", "will_review": True} for p in self.finder.completed],
                   "total_files": len(self.finder.completed)}
        else:
            manifest = {"schema_version": review_ocr.MANIFEST_SCHEMA, "operation": "review", "terminal_state": "complete",
                        "input": {"mode": "range", "resolved_base": base, "resolved_head": head},
                        "execution": {"ocr_version": review_ocr.OCR["version"]},
                        "coverage": {"selected": done, "completed": done, "reused": [], "failed": [], "waived": []}}
            doc = {"status": "complete", "comments": [], "manifest": manifest, "tool_calls": {"failure_details": []},
                   "summary": {"input_tokens": 300, "output_tokens": 60, "total_tokens": 360}, "message": "reviewed"}
        out.write_text(json.dumps(doc), encoding="utf-8")
        return self

    def wait(self, timeout=None):
        return 0

    def release(self) -> None:
        pass


class _Finder:
    """The pinned OCR binary behind `ProcessRange`: `completed` is every path its preview lists and its review completes."""

    def __init__(self, completed) -> None:
        self.completed = tuple(completed)

    def __call__(self, name, argv, *, cwd=None, env=None, output=None) -> _Process:
        return _Process(self, [str(a) for a in argv], output)


class OneNameStatusRowIsOneRow(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.repo = self.tmp / "repo"
        self.base = e2e.make_repo(self.repo)
        e2e.git(self.repo, "config", "core.quotepath", "false")       # git prints a non-ASCII path raw
        self.project = bundle.load(e2e.project_bundle(self.base))
        self.logs = self.tmp / "out" / "sessions"
        self.exe = self.tmp / "ocr"
        self.exe.write_bytes(b"the pinned binary\n")
        self.parent = self.base

    def commit(self, message: str, *, add=(), remove=()) -> str:
        """A commit whose index adds `add` (name -> an existing blob) and removes `remove`; returns its revision."""
        blob = e2e.git(self.repo, "hash-object", "-w", "app/calc.py")
        try:
            for name in add:
                e2e.git(self.repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{name}")
            for name in remove:
                e2e.git(self.repo, "update-index", "--force-remove", "--", name)
        except subprocess.CalledProcessError:
            self.skipTest("this git refuses a path holding a line-break character")
        e2e.git(self.repo, "commit", "-q", "-m", message)
        return e2e.git(self.repo, "rev-parse", "HEAD")

    def review(self, completed, head: str) -> tuple[list, dict, str]:
        events = [types.SimpleNamespace(type="story/begin", data={"story_id": "S1", "parent": self.parent})]
        limits = {"provider_requests": 100, "turns": 100, "input_tokens": 10 ** 7, "output_tokens": 10 ** 7}
        budget = client.Budget(limits, dict.fromkeys(limits, 0), self.logs, lambda: 50)
        review = {"policy": "advisory", "min_severity": "high", "finder": "ocr", "given": True,
                  "ocr": {"exe": str(self.exe), "sha256": hashlib.sha256(self.exe.read_bytes()).hexdigest(),
                          "timeout_min": 1, "max_tokens": 4000}}
        route = {"url": "http://127.0.0.1:9/v1", "token": "sk-test-not-a-key", "model": "model-1"}
        rev = ad.Reviewer(types.SimpleNamespace(events=events), self.project, self.logs, {"budget": budget}, 5.0,
                          review=review, route=route)
        with mock.patch.object(ad, "ProcessRange", _Finder(completed)):
            return rev._ocr(types.SimpleNamespace(story_id="S1", root=str(self.repo)), 1, head)

    def test_a_changed_path_holding_a_line_break_character_is_required_whole(self):
        """The row of U+0085, U+2028 and U+2029 paths is one row each: `required` names each changed path whole and
        no shorter path git did not list (the names the old parser invented are not in it)."""
        head = self.commit("names with a line-break character", add=[n for n, _ in SEPARATED])
        listed = ad.git(self.repo, "diff", "--name-status", "--no-renames", f"{self.base}..{head}").stdout
        for name, _ in SEPARATED:
            self.assertIn(name, listed)             # git printed it raw: the premise of the test
        _, s, _ = self.review([], head)
        for name, invented in SEPARATED:
            with self.subTest(path=name):
                self.assertIn(name, s["required"], f"required = {s['required']}")
                self.assertNotIn(invented, s["required"])

    def test_a_review_that_completed_only_the_shorter_names_does_not_cover_the_candidate(self):
        """Coverage is judged against the whole changed paths: a manifest that completes `app/a`, `app/c` and `app/e`
        (files of the change in their own right) but not the changed paths is not COMPLETE, and names the whole paths."""
        head = self.commit("names with a line-break character", add=[n for n, _ in SEPARATED])
        _, s, detail = self.review([i for _, i in SEPARATED], head)
        self.assertNotEqual(s["coverage"]["status"], review_ocr.COMPLETE, detail)
        said = " ".join(s["coverage"]["reasons"])
        for name, _ in SEPARATED:     # a reason lists paths as Python reprs: the character is escaped there
            self.assertTrue(name in said or repr(name)[1:-1] in said, said)

    def test_a_review_that_completed_the_whole_names_covers_the_candidate(self):
        head = self.commit("names with a line-break character", add=[n for n, _ in SEPARATED])
        _, s, detail = self.review([n for n, _ in SEPARATED], head)
        self.assertEqual(s["coverage"]["status"], review_ocr.COMPLETE, detail)

    def test_a_deleted_path_holding_a_line_break_character_is_listed_whole_and_not_required(self):
        self.parent = self.commit("a name with a line-break character", add=[n for n, _ in SEPARATED])
        head = self.commit("the story deletes them", remove=[n for n, _ in SEPARATED])
        _, s, _ = self.review([], head)
        self.assertEqual(s["deleted"], sorted(n for n, _ in SEPARATED))
        self.assertEqual(s["required"], [])

    def test_ordinary_rows_are_read_as_before(self):
        """Pin (passes before the fix too): added and modified product paths are `required`, sorted; a deleted one is
        `deleted`; a path outside the product roots is neither."""
        (self.repo / "app" / "util.py").write_text("# util\n", encoding="utf-8")
        (self.repo / "app" / "cli.py").write_text("# cli\n", encoding="utf-8")
        e2e.git(self.repo, "rm", "-q", "--", "app/calc.py")     # the story deletes it: git removes it from tree and index
        (self.repo / "docs" / "notes.md").write_text("# notes\n", encoding="utf-8")
        e2e.git(self.repo, "add", "-A")
        e2e.git(self.repo, "commit", "-q", "-m", "ordinary change")
        head = e2e.git(self.repo, "rev-parse", "HEAD")
        _, s, _ = self.review([], head)
        self.assertEqual(s["required"], ["app/cli.py", "app/util.py"])
        self.assertEqual(s["deleted"], ["app/calc.py"])


if __name__ == "__main__":
    unittest.main()
