"""V2.1 (owner B-03, survivors batch T10a): the session stream of an Open Code Review, written by
aisef2/app/adapters.py::Reviewer._ocr.

A review by Open Code Review is not an OpenCode session, yet it is accounted and kept as one: its evidence is ONE
stream file in the run's sessions/ directory (anchored by EVIDENCE.json, read by client.read_session for the budget and
by usage for the account). `_ocr` writes it in two steps — a marker line before the review starts (a stream that exists
may have spent), then the preview document, the review document and the two lines every session stream has (the text
and the finished step with its tokens). Nothing reads the preview or the review document back from the stream: coverage
is decided on the variables the controller holds; the stream is the anchored copy of what that decision was made on, so
what these tests pin is what the copy contains.

The finder here is a script started by its shebang (a fake Open Code Review writing OCR's documents), the repository a
real git repository, and the entry point the public `Reviewer.review` — the kernel's own call.

Pins aisef2/app/adapters.py::Reviewer._ocr [25, 26, 27, 77, 78, 79, 80, 81, 82, 83, 84, 158-169, 206, 214, 236, 265]."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
import tempfile
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, client  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402

#: OCR's `message` of the review: a marker, never read for its wording — what is asserted is that it is carried
MARKER = "marker-4f27c9-ocr-message"
VERSION = "v1.12.12"       # the pinned OCR version (app/review_ocr.OCR): a manifest of another version is not complete

#: the finder: OCR's command line (`--repo --from --to --output [--preview]`) and documents (run-manifest v1, preview).
#: What it wrote it also keeps beside itself (wrote-*.json), so a test compares the stream with the file OCR wrote.
FINDER = r'''import hashlib, json, pathlib, subprocess, sys, time
argv = sys.argv[1:]
if argv == ["version"]:      # the identity gate asks before any review command
    print("open-code-review v1.12.12 (182898c) darwin/arm64")
    raise SystemExit(0)
here = pathlib.Path(__file__).parent
sc = json.loads((here / "scenario.json").read_text(encoding="utf-8"))
def opt(name):
    return argv[argv.index(name) + 1]
repo, base, head, out = opt("--repo"), opt("--from"), opt("--to"), opt("--output")
rows = subprocess.run(["git", "-C", repo, "diff", "--name-status", "--no-renames", base + ".." + head],
                      capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
paths = [r.split("\t", 1)[1] for r in rows if "\t" in r and not r.startswith("D")]
def write(kept, doc):
    text = json.dumps(doc)
    pathlib.Path(out).write_text(text, encoding="utf-8")
    (here / kept).write_text(text, encoding="utf-8")
if "--preview" in argv:
    write("wrote-preview.json", {"files": [{"path": p, "status": "added", "insertions": 1, "deletions": 0,
                                            "will_review": True} for p in paths], "total_files": len(paths)})
    raise SystemExit(0)
if sc["kind"] == "sleep":
    time.sleep(120)
if sc["kind"] == "crash":
    raise SystemExit(7)
done = [{"item_id": hashlib.sha256("\x00".join(["review", "range", p, p]).encode("utf-8")).hexdigest(), "path": p}
        for p in paths]
manifest = {"schema_version": "ocr.run-manifest/v1", "operation": "review", "terminal_state": "complete",
            "input": {"mode": "range", "resolved_base": base, "resolved_head": head},
            "execution": {"ocr_version": sc["version"]},
            "coverage": {"selected": done, "completed": done, "reused": [], "failed": [], "waived": []}}
write("wrote-review.json", {"status": "complete", "comments": [], "manifest": manifest,
                            "tool_calls": {"failure_details": []}, "message": sc["message"], "summary": sc["summary"]})
raise SystemExit(0)
'''


def review_once(tmp: pathlib.Path, kind: str, *, policy: str = "fix-loop", timeout_s: float = 60.0) -> types.SimpleNamespace:
    """One `Reviewer.review` of a candidate that adds app/extra.py, by the finder scripted as `kind`; what it left:
    the stream's path and lines, the documents the finder wrote, the reviewer and its result."""
    repo = tmp / "repo"
    baseline = e2e.make_repo(repo)
    (repo / "app" / "extra.py").write_text("VALUE = 1\n", encoding="utf-8")
    e2e.git(repo, "add", "-A")
    e2e.git(repo, "commit", "-q", "-m", "candidate")
    bin_ = tmp / "bin"
    bin_.mkdir()
    exe = bin_ / "ocr"
    exe.write_text(f"#!{sys.executable}\n" + FINDER, encoding="utf-8")
    exe.chmod(0o755)
    (bin_ / "scenario.json").write_text(json.dumps(
        {"kind": kind, "version": VERSION, "message": MARKER,
         "summary": {"input_tokens": 300, "output_tokens": 60, "cache_read_tokens": 40, "cache_write_tokens": 5}}),
        encoding="utf-8")
    logs = tmp / "out" / "sessions"
    budget = client.Budget({"provider_requests": 50, "turns": 50, "input_tokens": 10 ** 6, "output_tokens": 10 ** 6},
                           dict.fromkeys(client.Budget.KEYS, 0), logs)
    policy_ = {"policy": policy, "min_severity": "high", "finder": "ocr",
               "ocr": {"exe": str(exe), "sha256": hashlib.sha256(exe.read_bytes()).hexdigest(), "timeout_min": 1,
                       "max_tokens": 4000}}
    run = types.SimpleNamespace(events=[types.SimpleNamespace(type="story/begin", data={"story_id": "S1", "parent": baseline})],
                                state=lambda proj: {"S1": {"attempt": 1}})
    rev = ad.Reviewer(run, bundle.load(e2e.project_bundle(baseline)), logs, {"budget": budget, "secrets": ()}, timeout_s,
                      review=policy_, route={"url": "http://127.0.0.1:9/v1", "token": "fixture-token-value", "model": "m",
                                             "env": {"PATH": os.environ["PATH"]}})
    result = rev.review(types.SimpleNamespace(story_id="S1", root=str(repo)), ("C-ADD",))
    log = logs / "S1.reviewer.1.jsonl"
    text = log.read_text(encoding="utf-8")

    def wrote(name):
        p = bin_ / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    return types.SimpleNamespace(log=log, text=text, lines=text.splitlines(), rev=rev, result=result,
                                 preview=wrote("wrote-preview.json"), review=wrote("wrote-review.json"))


class _Fixture(unittest.TestCase):
    """One review per class (setUpClass); a subclass names the finder's scenario and the review's deadline. Under
    fix-loop a review that did not cover the candidate raises, so a subclass that reads its stream has a complete one."""

    KIND = "complete"
    POLICY = "fix-loop"
    TIMEOUT_S = 60.0
    r: types.SimpleNamespace

    @classmethod
    def setUpClass(cls) -> None:
        t = tempfile.TemporaryDirectory()
        cls.addClassCleanup(t.cleanup)
        cls.r = review_once(pathlib.Path(t.name).resolve(), cls.KIND, policy=cls.POLICY, timeout_s=cls.TIMEOUT_S)

    @property
    def docs(self) -> list[dict]:
        """The stream's lines, each parsed on its own (a line that is not one JSON document fails the test reading it)."""
        return [json.loads(ln) for ln in self.r.lines]


@unittest.skipUnless(os.name == "posix", "the finder is a script started by its shebang")
class CompleteReviewStream(_Fixture):
    """A complete review leaves a stream of five JSON documents, one per physical line, in the order a reader of the
    evidence follows: the marker, the preview, the review, the text, the finished step. The preview and the review lines
    each carry their run's exit status and the document OCR wrote (the files it would review and why not the others;
    the manifest, comments and summary the coverage decision was made on). The stream read as a session by the one
    reader of session streams (client.read_session) has OCR's message as its text and one finished step with tokens.

    Pins Reviewer._ocr [25, 26, 27, 77-84, 158-169, 206, 214, 236, 265]."""

    def test_the_stream_is_five_documents_one_per_line_in_order(self):
        self.assertEqual(len(self.r.lines), 5, self.r.text)      # a line missing, or two documents on one physical line
        self.assertTrue(self.r.text.endswith("\n"))
        docs = [json.loads(ln) for ln in self.r.lines]            # each line is one JSON document on its own
        self.assertEqual([d.get("type") for d in docs],
                         ["ocr_started", "ocr_preview", "ocr_output", "text", "step_finish"])
        self.assertTrue(docs[4]["part"]["tokens"], "the step's tokens are the review's (an unaccounted step has none)")

    def test_the_preview_line_holds_the_preview_ocr_wrote_and_its_exit_status(self):
        self.assertTrue(self.r.preview["files"], "the preview the finder wrote lists the candidate's file")
        line = self.docs[1]
        for key in ("type", "exit", "document"):
            self.assertIn(key, line)
        self.assertEqual((line["type"], line["exit"]), ("ocr_preview", 0))
        self.assertEqual(line["document"], self.r.preview)

    def test_the_review_line_holds_the_review_ocr_wrote_and_its_exit_status(self):
        self.assertTrue(self.r.review["manifest"], "the document the finder wrote carries the run manifest")
        line = self.docs[2]
        for key in ("type", "exit", "document"):
            self.assertIn(key, line)
        self.assertEqual((line["type"], line["exit"]), ("ocr_output", 0))
        self.assertEqual(line["document"], self.r.review)

    def test_the_stream_reads_as_a_session_whose_text_is_ocrs_message(self):
        seen = client.read_session(self.r.log)
        self.assertEqual(seen["text"], MARKER)
        self.assertEqual((seen["turns"], seen["steps_without_tokens"], seen["error"]), (1, 0, None))


@unittest.skipUnless(os.name == "posix", "the finder is a script started by its shebang")
class ReviewThatWroteNoDocument(_Fixture):
    """A finder that exits 7 without writing its document: the review line carries that exit status and no document
    (the key is present, null) while the preview line keeps the preview's own status 0 and document, and the stream has
    no text — read_session says '' (an absent message is not a message)."""

    KIND = "crash"
    POLICY = "advisory"

    def test_the_review_line_carries_its_exit_status_and_a_null_document(self):
        self.assertEqual([d.get("type") for d in self.docs],
                         ["ocr_started", "ocr_preview", "ocr_output", "text", "step_finish"])
        review = self.docs[2]
        self.assertIn("exit", review)
        self.assertIn("document", review)
        self.assertEqual((review["exit"], review["document"]), (7, None))
        preview = self.docs[1]
        self.assertEqual((preview["exit"], preview["document"]), (0, self.r.preview))

    def test_the_stream_has_no_text(self):
        self.assertEqual(client.read_session(self.r.log)["text"], "")


@unittest.skipUnless(os.name == "posix", "the finder is a script started by its shebang")
class ReviewStoppedAtItsDeadline(_Fixture):
    """A review whose deadline has run out (a zero deadline: the finder, which would sleep, is released before it can
    write anything) has exit null on both of its runs' lines, a null review document, and no text. `exit` null is the
    deadline: a status of 0 or an absent key is not."""

    KIND = "sleep"
    POLICY = "advisory"
    TIMEOUT_S = 0.0

    def test_the_lines_carry_a_null_exit_and_the_review_a_null_document(self):
        for line in (self.docs[1], self.docs[2]):
            self.assertIn("exit", line)
            self.assertIsNone(line["exit"])
        self.assertIn("document", self.docs[1])
        self.assertIn("document", self.docs[2])
        self.assertIsNone(self.docs[2]["document"])

    def test_the_text_is_empty_not_the_word_none(self):
        self.assertEqual(client.read_session(self.r.log)["text"], "")


if __name__ == "__main__":
    unittest.main()
