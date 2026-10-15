"""V2.1 (owner B-03, kill round 3, batch A10): kill tests for the survivors of aisef2/app/adapters.py::Reviewer._ocr.

`_ocr` is Open Code Review as the reviewer's finder: it reads what the story changed from the journal's parent and
git, runs OCR's preview then its review (a process each), writes the one session stream the budget and the evidence
read, and judges the review's coverage. It is driven here directly, as test_v21_kills_adapters.py drives the model
finder: a real git repository and a real Budget; the OCR binary is the one stand-in — a `ProcessRange` that writes
the documents OCR writes (its manifest v1 and its preview) from a scripted scenario, so nothing is spawned.

Classes, by behaviour:

* RefusalsBeforeTheFinderStarts — what an operator reading the journal's `provider/result` learns when the review is
  refused before OCR starts: the stream that exists, the story with no parent, the range git cannot list;
* IncompleteReview — the refusal and the detail of a review that did not cover the candidate: the status, each reason
  intact (a reason ends in a number and the next one begins with one);
* ANameGitPrintsOnTwoLines — a changed path with a character `str.splitlines` treats as a line break;
* DistinctScratchDirectories — two reviews of different (story, attempt) pairs never share a scratch directory."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import tempfile
import subprocess
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, client, review_ocr  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402

#: the product files the story changed: what the stand-in finder completes unless a test says otherwise
CHANGED = ("app/cli.py", "app/util.py")
BAD_PARENT = "deadbeef" * 5      # a well-formed revision the repository does not hold


class _Process:
    """One `ProcessRange` of the stand-in: records its name and command line, writes OCR's document, answers its exit."""

    def __init__(self, finder: "_Finder", name: str, argv: list[str], output=None) -> None:
        self.finder, self.name, self.argv, self.output = finder, name, argv, output
        self.preview = "--preview" in argv

    def opt(self, flag: str) -> str:
        return self.argv[self.argv.index(flag) + 1]

    def start(self) -> "_Process":
        if self.argv[1:] == ["version"]:      # the identity gate, before any review command: not a review, not a call
            self.output.write(f"open-code-review {review_ocr.OCR['version']} ({review_ocr.OCR['commit'][:7]}) darwin/arm64\n")
            self.output.flush()
            return self
        f, base, head = self.finder, self.opt("--from"), self.opt("--to")
        out = pathlib.Path(self.opt("--output"))
        f.calls.append({"name": self.name, "preview": self.preview, "output": out, "base": base, "head": head})
        if self.preview:
            doc = {"files": [{"path": p, "status": "added", "insertions": 1, "deletions": 0, "will_review": True}
                             for p in f.completed], "total_files": len(f.completed)}
        else:
            done = [{"item_id": review_ocr.item_id("range", p, p), "path": p} for p in f.completed]
            manifest = {"schema_version": review_ocr.MANIFEST_SCHEMA, "operation": "review", "terminal_state": f.state,
                        "input": {"mode": "range", "resolved_base": base, "resolved_head": head},
                        "execution": {"ocr_version": review_ocr.OCR["version"]},
                        "coverage": {"selected": done, "completed": done, "reused": [], "failed": [], "waived": []}}
            doc = {"status": f.state, "comments": [], "manifest": manifest,
                   "tool_calls": {"failure_details": [{"tool_name": "code_comment"}] * f.dropped},
                   "summary": {"input_tokens": 300, "output_tokens": 60, "total_tokens": 360}, "message": "reviewed"}
        out.write_text(json.dumps(doc), encoding="utf-8")
        return self

    def wait(self, timeout=None):
        return 0 if self.preview or self.argv[1:] == ["version"] else self.finder.exit_code

    def release(self) -> None:
        pass


class _Finder:
    """The pinned OCR binary behind `ProcessRange`: `completed` the paths its review completes, `exit_code` its review's
    exit status, `state` the manifest's terminal state, `dropped` how many code_comment calls failed."""

    def __init__(self, completed=CHANGED, exit_code: int = 0, state: str = "complete", dropped: int = 0) -> None:
        self.completed, self.exit_code, self.state, self.dropped = tuple(completed), exit_code, state, dropped
        self.calls: list[dict] = []

    def __call__(self, name, argv, *, cwd=None, env=None, output=None) -> _Process:
        return _Process(self, name, [str(a) for a in argv], output)


class _Ocr(unittest.TestCase):
    """A repository whose story S1 changed `CHANGED` over the baseline, a Reviewer on the OCR finder, a real Budget."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.base = e2e.make_repo(self.tmp / "repo")
        for rel in CHANGED:
            (self.tmp / "repo" / rel).write_text(f"# {rel}\n", encoding="utf-8")
        e2e.git(self.tmp / "repo", "add", "-A")
        e2e.git(self.tmp / "repo", "commit", "-q", "-m", "the story's change")
        self.head = e2e.git(self.tmp / "repo", "rev-parse", "HEAD")
        self.project = bundle.load(e2e.project_bundle(self.base))
        self.out = self.tmp / "out"
        self.logs = self.out / "sessions"
        self.begun = [("S1", self.base)]
        self.exe = self.tmp / "ocr"
        self.exe.write_bytes(b"the pinned binary\n")

    def scope(self, story: str = "S1"):
        return types.SimpleNamespace(story_id=story, root=str(self.tmp / "repo"))

    def reviewer(self, finder: _Finder, policy: str = "fix-loop") -> ad.Reviewer:
        events = [types.SimpleNamespace(type="story/begin", data={"story_id": s, "parent": p}) for s, p in self.begun]
        run = types.SimpleNamespace(events=events)
        limits = {"provider_requests": 100, "turns": 100, "input_tokens": 10 ** 7, "output_tokens": 10 ** 7}
        budget = client.Budget(limits, dict.fromkeys(limits, 0), self.logs, lambda: 50)
        review = {"policy": policy, "min_severity": "high", "finder": "ocr", "given": True,
                  "ocr": {"exe": str(self.exe), "sha256": hashlib.sha256(self.exe.read_bytes()).hexdigest(),
                          "timeout_min": 1, "max_tokens": 4000}}
        route = {"url": "http://127.0.0.1:9/v1", "token": "sk-test-not-a-key", "model": "model-1"}
        rev = ad.Reviewer(run, self.project, self.logs, {"budget": budget}, 5.0, review=review, route=route)
        patch = mock.patch.object(ad, "ProcessRange", finder)
        patch.start()
        self.addCleanup(patch.stop)
        return rev


class RefusalsBeforeTheFinderStarts(_Ocr):
    """What the journal's `provider/result` tells the operator when the review is refused before OCR starts. Each
    refusal names its object and its cause, and starts no process (`finder.calls` stays empty)."""

    def test_a_stream_that_exists_is_refused_naming_it_and_saying_it_exists_and_is_left_alone(self):
        """Pins aisef2/app/adapters.py::Reviewer._ocr [127]: the refusal of a review whose session stream already exists
        is a ProviderOutage (the budget's class) that names the stream and says it exists — without the cause it is
        indistinguishable from the budget's own refusal. The stream is never touched and nothing is started."""
        self.logs.mkdir(parents=True)
        stream = self.logs / "S1.reviewer.1.jsonl"
        stream.write_bytes(b'{"type": "text", "part": {"text": "evidence"}}\n')
        finder = _Finder()
        with self.assertRaises(ad.ProviderOutage) as c:
            self.reviewer(finder)._ocr(self.scope(), 1, self.head)
        self.assertIn(stream.name, str(c.exception))
        self.assertIn("exists", str(c.exception))
        self.assertEqual(stream.read_bytes(), b'{"type": "text", "part": {"text": "evidence"}}\n')
        self.assertEqual(finder.calls, [])

    def test_a_story_the_journal_gives_no_parent_is_refused_naming_it_and_the_missing_parent(self):
        """Pins aisef2/app/adapters.py::Reviewer._ocr [188]: the base of the review is the parent the story's
        `story/begin` names; with none, the refusal (a CapabilityUnrunnable) names the story and what is missing."""
        self.begun = []
        finder = _Finder()
        with self.assertRaises(ad.CapabilityUnrunnable) as c:
            self.reviewer(finder)._ocr(self.scope(), 1, self.head)
        self.assertIn("S1", str(c.exception))
        self.assertIn("parent", str(c.exception))
        self.assertEqual(finder.calls, [])

    def test_a_range_git_cannot_list_is_refused_naming_the_command_the_range_and_its_status(self):
        """Pins aisef2/app/adapters.py::Reviewer._ocr [189]: when `git diff` of the story's range fails the refusal
        names the command, the range (parent..candidate, abbreviated) and git's exit status."""
        self.begun = [("S1", BAD_PARENT)]
        status = ad.git(self.tmp / "repo", "diff", "--name-status", "--no-renames", f"{BAD_PARENT}..{self.head}").returncode
        self.assertNotEqual(status, 0)
        finder = _Finder()
        with self.assertRaises(ad.CapabilityUnrunnable) as c:
            self.reviewer(finder)._ocr(self.scope(), 1, self.head)
        said = str(c.exception)
        self.assertIn("git diff", said)
        self.assertRegex(said, rf"{BAD_PARENT[:7]}[0-9a-f]*\.\.{self.head[:7]}")      # parent..candidate, abbreviated
        self.assertRegex(said, rf"(?<![0-9a-f]){status}(?![0-9a-f])")       # git's status, not digits of an abbreviation
        self.assertEqual(finder.calls, [])


class IncompleteReview(_Ocr):
    """A review whose manifest does not show the candidate fully reviewed. Its reasons come from review_ocr.coverage
    in order; a reason may end in a number (`exit status 1`) and the next may begin with one (`3 code_comment call(s)
    failed`), so a refusal or a detail that runs them together misreports the exit status."""

    def reasons(self, rev: ad.Reviewer) -> list[str]:
        return rev.sessions[-1]["coverage"]["reasons"]

    def assert_apart(self, text: str, reasons: list[str]) -> None:
        """Every reason of the record is in `text` and none runs on into the next (a reason that ends in a number and
        the next that begins with one would read as another number)."""
        self.assertGreaterEqual(len(reasons), 2)
        for r in reasons:
            self.assertIn(r, text)
        for first, second in zip(reasons, reasons[1:], strict=False):
            self.assertNotIn(first + second, text)

    def test_under_fix_loop_the_refusal_states_the_status_and_each_reason_apart(self):
        """Pins aisef2/app/adapters.py::Reviewer._ocr [260], [243]: under fix-loop a review that did not cover the
        candidate is never a commit (CapabilityUnrunnable); its refusal states the coverage status and keeps the
        reasons — here the exit status and the failed code_comment calls — apart, so the exit status reads as OCR's."""
        finder = _Finder(exit_code=1, dropped=3)
        rev = self.reviewer(finder)
        with self.assertRaises(ad.CapabilityUnrunnable) as c:
            rev._ocr(self.scope(), 1, self.head)
        self.assertEqual(rev.sessions[-1]["coverage"]["status"], review_ocr.INDETERMINATE)
        self.assertIn(review_ocr.INDETERMINATE, str(c.exception))
        self.assert_apart(str(c.exception), self.reasons(rev))

    def test_under_advisory_the_detail_states_the_status_as_a_word_and_each_reason_apart(self):
        """Pins aisef2/app/adapters.py::Reviewer._ocr [271], [244]: under advisory the same review is recorded, not
        refused; the detail the run journals names the status as a word of its own (`coverage INDETERMINATE`, then its
        reasons) and keeps the reasons apart, with the exit status read as OCR's."""
        finder = _Finder(exit_code=1, dropped=3)
        rev = self.reviewer(finder, "advisory")
        found, s, detail = rev._ocr(self.scope(), 1, self.head)
        self.assertEqual(found, [])
        self.assertEqual(s["coverage"]["status"], review_ocr.INDETERMINATE)
        self.assertRegex(detail, rf"^coverage {review_ocr.INDETERMINATE}\b")
        self.assert_apart(detail, self.reasons(rev))


class ANameGitPrintsOnTwoLines(_Ocr):
    """git prints a changed path raw when `core.quotepath` is false (the repository's own configuration may set it:
    workspace.INERT_KEY allows it). `str.splitlines` also breaks at U+2028, so one row of `git diff --name-status`
    reaches the parser as two lines and the second has no tab."""

    def test_a_row_that_is_not_status_tab_path_never_breaks_the_review(self):
        """Pins aisef2/app/adapters.py::Reviewer._ocr [192]: a line of git's output that is not `<status>\\t<path>`
        is skipped, not unpacked — the review goes on (an untyped ValueError would leave the story begun and never
        ended, recorded REFUSED). It asserts only that the review runs and keeps the ordinary file: the name itself
        is still read as two lines (its first half taken for a path), a defect of the parser this test does not pin."""
        repo = self.tmp / "repo"
        e2e.git(repo, "config", "core.quotepath", "false")
        (repo / "app" / "plain.py").write_text("# plain\n", encoding="utf-8")
        e2e.git(repo, "add", "-A")
        blob = e2e.git(repo, "hash-object", "-w", "app/plain.py")
        try:       # the name lives in the index and the commit only: no file of that name is made on this filesystem
            e2e.git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},app/x\u2028y.py")
        except subprocess.CalledProcessError:
            self.skipTest("this git refuses a path holding U+2028")
        e2e.git(repo, "commit", "-q", "-m", "a name with a line separator")
        head = e2e.git(repo, "rev-parse", "HEAD")
        listed = ad.git(repo, "diff", "--name-status", "--no-renames", f"{self.base}..{head}").stdout
        self.assertIn("\u2028", listed)          # git printed it raw: the premise of the test
        finder = _Finder(completed=(*CHANGED, "app/plain.py"))
        rev = self.reviewer(finder, "advisory")
        _, s, _ = rev._ocr(self.scope(), 1, head)
        self.assertIn("app/plain.py", s["required"])
        self.assertEqual(len(finder.calls), 2)       # the preview and the review ran


class DistinctScratchDirectories(_Ocr):
    """A review's scratch directory (rule, background, OCR's documents and logs, its HOME) is made exclusively, so two
    reviews that name one directory make the second fail untyped. Attempts are an unbounded count (settings limits)."""

    PAIRS = (("S1", 1), ("S1", 2), ("S2", 1), ("S1", 11), ("S11", 1))

    def test_every_story_and_attempt_pair_reviews_in_a_directory_of_its_own(self):
        """Pins aisef2/app/adapters.py::Reviewer._ocr [129]: the directory is told apart by story AND attempt — one
        story's attempts, two stories' first attempts and `S1` at attempt 11 against `S11` at attempt 1 (the names run
        together are one) are five reviews in five directories, all of which run."""
        self.begun = [(story, self.base) for story in ("S1", "S2", "S11")]
        finder = _Finder()
        rev = self.reviewer(finder)
        for story, attempt in self.PAIRS:
            rev._ocr(self.scope(story), attempt, self.head)
        dirs = [c["output"].parent for c in finder.calls if not c["preview"]]
        self.assertEqual(len(dirs), len(self.PAIRS))
        self.assertEqual(len(set(dirs)), len(self.PAIRS))
        self.assertEqual([s["coverage"]["status"] for s in rev.sessions], [review_ocr.COMPLETE] * len(self.PAIRS))


if __name__ == "__main__":
    unittest.main()
