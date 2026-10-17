"""V2.1 (owner 2026-10-15, item 5, lane ocr-gate): what the Open Code Review binary says it is, asked BEFORE any review
command, and the line between that and the evidence of how it was built.

Before this gate the review stage checked the binary's sha256 against the operator's pin (`review_ocr.pinned`) and
compared the version only AFTER the review ran, from the manifest OCR itself wrote (`coverage`): a binary of the pinned
bytes the operator had pinned wrongly — any 64 hex — still ran its preview and its review (provider spend) before the
refusal, and `OCR["commit"]` was read by nobody. Now `Reviewer._ocr` asks `<exe> version` first, in a clean environment
(nothing inherited, an empty HOME that is its working directory, no repository, no route), parses its first line,
compares it with `OCR["version"]` and `OCR["commit"]`, and refuses (CapabilityUnrunnable, the refusal the sha256 check
already uses) before the preview and before the review — under advisory as under fix-loop.

What this proves, and does not: the version line is the binary's own word (a self-declaration). The sha256 identifies
the bytes; neither says how they were built. The session record states both, and says which is which.

Two layers here: `Gate` (the product's `Reviewer.review` over a script started by its shebang that records every start)
and `Chain` (the same through `aisef run`, the one decision path). The pure judgement and its table of answers are in
test_v21_ocr_declared.py."""

from __future__ import annotations

import contextlib
import hashlib
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
from aisef2.app import bundle, client, review_ocr  # noqa: E402
from aisef2.orchestrate.adapters import CapabilityUnrunnable  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402
from tests.v2 import test_v21_review_chain as chain  # noqa: E402
from tests.v2.test_v21_ocr_declared import ANSWERS, PINNED_LINE, REFUSED  # noqa: E402

POSIX = unittest.skipUnless(os.name == "posix", "the finder is a script started by its shebang")

#: the finder: records every start (argv, environment, working directory, what HOME held at that moment) in call-NN.json,
#: answers `version` as scenario.json says, and otherwise behaves as a complete review of the story's change
RECORDER = r'''import hashlib, json, os, pathlib, subprocess, sys, time
argv = sys.argv[1:]
here = pathlib.Path(__file__).parent
home = pathlib.Path(os.environ.get("HOME", ""))
(here / f"call-{len(sorted(here.glob('call-*.json'))):02d}.json").write_text(json.dumps({
    "argv": argv, "env": dict(os.environ), "cwd": os.getcwd(), "home": str(home),
    "home_listing": sorted(os.listdir(home)) if home.is_dir() else None}), encoding="utf-8")
sc = json.loads((here / "scenario.json").read_text(encoding="utf-8"))
if argv == ["version"]:
    time.sleep(sc["sleep"])
    sys.stdout.write(sc["text"])
    raise SystemExit(sc["exit"])
def opt(name):
    return argv[argv.index(name) + 1]
repo, base, head, out = opt("--repo"), opt("--from"), opt("--to"), opt("--output")
rows = subprocess.run(["git", "-C", repo, "diff", "--name-status", "--no-renames", base + ".." + head],
                      capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
paths = [r.split("\t", 1)[1] for r in rows if "\t" in r and not r.startswith("D")]
if "--preview" in argv:
    pathlib.Path(out).write_text(json.dumps({"files": [{"path": p, "status": "added", "insertions": 1, "deletions": 0,
                                                        "will_review": True} for p in paths], "total_files": len(paths)}),
                                 encoding="utf-8")
    raise SystemExit(0)
done = [{"item_id": hashlib.sha256("\x00".join(["review", "range", p, p]).encode("utf-8")).hexdigest(), "path": p}
        for p in paths]
manifest = {"schema_version": "ocr.run-manifest/v1", "operation": "review", "terminal_state": "complete",
            "input": {"mode": "range", "resolved_base": base, "resolved_head": head},
            "execution": {"ocr_version": "v1.12.12"},
            "coverage": {"selected": done, "completed": done, "reused": [], "failed": [], "waived": []}}
pathlib.Path(out).write_text(json.dumps({"status": "complete", "comments": [], "manifest": manifest,
                                         "tool_calls": {"failure_details": []}, "message": "reviewed",
                                         "summary": {"input_tokens": 300, "output_tokens": 60, "total_tokens": 360}}),
                             encoding="utf-8")
raise SystemExit(0)
'''


@POSIX
class Gate(unittest.TestCase):
    """`Reviewer.review` of a candidate by the recording finder: what it was started with, in what order, and what the
    operator is told. One repository per test method (the review's own `work` directory never overwrites)."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.repo = self.tmp / "repo"
        self.baseline = e2e.make_repo(self.repo)
        (self.repo / "app" / "extra.py").write_text("VALUE = 1\n", encoding="utf-8")
        e2e.git(self.repo, "add", "-A")
        e2e.git(self.repo, "commit", "-q", "-m", "candidate")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.exe = self.bin / "ocr"
        self.exe.write_text(f"#!{sys.executable}\n" + RECORDER, encoding="utf-8")
        self.exe.chmod(0o755)
        self.logs = self.tmp / "out" / "sessions"
        # what the operator's own environment holds: none of it may reach the version question
        env = mock.patch.dict(os.environ, {"AISEF_GATE_OPERATOR_SECRET": "operator-value-0123", "OCR_LLM_TOKEN": "op-token"})
        env.start()
        self.addCleanup(env.stop)

    def answer(self, name: str) -> None:
        text, code, sleep = ANSWERS[name]
        (self.bin / "scenario.json").write_text(json.dumps({"text": text, "exit": code, "sleep": sleep}), encoding="utf-8")

    def reviewer(self, policy: str, *, sha256: str | None = None) -> ad.Reviewer:
        budget = client.Budget({"provider_requests": 50, "turns": 50, "input_tokens": 10 ** 6, "output_tokens": 10 ** 6},
                               dict.fromkeys(client.Budget.KEYS, 0), self.logs)
        pin = {"policy": policy, "min_severity": "high", "finder": "ocr", "given": True,
               "ocr": {"exe": str(self.exe), "sha256": sha256 or hashlib.sha256(self.exe.read_bytes()).hexdigest(),
                       "timeout_min": 1, "max_tokens": 4000}}
        run = types.SimpleNamespace(events=[types.SimpleNamespace(type="story/begin",
                                                                  data={"story_id": "S1", "parent": self.baseline})],
                                    state=lambda proj: {"S1": {"attempt": 1}})
        return ad.Reviewer(run, bundle.load(e2e.project_bundle(self.baseline)), self.logs,
                           {"budget": budget, "secrets": ()}, 60.0, review=pin,
                           route={"url": "http://127.0.0.1:9/v1", "token": "fixture-token-value", "model": "m",
                                  "env": {"PATH": os.environ["PATH"]}})

    def review(self, policy: str = "fix-loop", **kw):
        rev = self.reviewer(policy, **kw)
        return rev, rev.review(types.SimpleNamespace(story_id="S1", root=str(self.repo)), ("C-ADD",))

    def calls(self) -> list[dict]:
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(self.bin.glob("call-*.json"))]

    # ---- the pinned build: asked first, in a clean environment, then reviewed, and the record says what it is
    def test_the_pinned_build_is_asked_first_then_previews_then_reviews(self):
        self.answer("pinned")
        _, result = self.review()
        calls = self.calls()
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0]["argv"], ["version"])
        self.assertEqual([c["argv"][0] for c in calls[1:]], ["review", "review"])
        self.assertIn("--preview", calls[1]["argv"])
        self.assertNotIn("--preview", calls[2]["argv"])
        self.assertEqual(result.outcome.name, "COMPLETED")

    def test_the_version_question_runs_in_a_clean_environment_and_an_empty_home_that_is_its_directory(self):
        self.answer("pinned")
        self.review()
        asked = self.calls()[0]
        home = asked["home"]
        want = {"PATH": "/usr/bin:/bin", "HOME": home, "USERPROFILE": home, "OCR_NO_UPDATE": "1"}
        # the interpreter of the script adds its own (PEP 538's locale coercion, macOS's text encoding): not the controller's
        got = {k: v for k, v in asked["env"].items() if k not in ("LC_CTYPE", "__CF_USER_TEXT_ENCODING")}
        self.assertEqual(got, want)
        self.assertEqual(os.path.realpath(asked["cwd"]), os.path.realpath(home))     # its working directory is that HOME
        self.assertEqual(asked["home_listing"], [])                                   # empty when it started
        for inside in (self.repo, self.tmp / "out"):
            self.assertFalse(pathlib.Path(os.path.realpath(home)).is_relative_to(os.path.realpath(inside)), (home, inside))
        self.assertFalse(pathlib.Path(home).exists())                                 # and gone afterwards
        review_calls = self.calls()[1:]
        self.assertTrue(all("OCR_LLM_TOKEN" in c["env"] for c in review_calls))       # the route is for the review alone

    def test_the_session_says_what_the_binary_declared_and_that_it_is_not_build_evidence(self):
        self.answer("pinned")
        rev, _ = self.review()
        (s,) = rev.sessions
        ident = s["identity"]
        self.assertEqual(ident["declared"], {"version": "v1.12.12", "commit": "182898c", "platform": "darwin/arm64",
                                             "line": PINNED_LINE})
        self.assertEqual(ident["sha256_checked"], hashlib.sha256(self.exe.read_bytes()).hexdigest())
        self.assertIn("self-declaration", ident["declared_by"])
        self.assertIn("not build evidence", ident["declared_by"])
        self.assertEqual(s["finder"], "ocr v1.12.12")

    # ---- anything else: refused before any review command, under both policies
    def test_a_binary_that_is_not_the_pinned_build_runs_no_review_command_whatever_the_policy(self):
        for policy in ("advisory", "fix-loop"):
            for name in REFUSED:
                with self.subTest(policy=policy, answer=name):
                    before = len(self.calls())           # what earlier answers left is not this one's: counted, not removed
                    self.answer(name)
                    # a shorter bound only for the binary that never answers (long enough for the script to start and
                    # record itself); every other answer gets the real one, so a slow interpreter start under load
                    # is not mistaken for "did not answer in time"
                    bound = mock.patch.object(review_ocr, "VERSION_TIMEOUT_S", 3.0, create=True) \
                        if ANSWERS[name][2] else contextlib.nullcontext()
                    with bound, self.assertRaises(CapabilityUnrunnable) as cm:
                        self.review(policy)
                    said = str(cm.exception)
                    for word in REFUSED[name]:
                        self.assertIn(word, said)
                    self.assertEqual([c["argv"] for c in self.calls()[before:]], [["version"]],
                                     "only the version question ran")
                    self.assertEqual(list(self.logs.glob("*")) if self.logs.exists() else [], [], "no stream was opened")
                    self.assertFalse((self.logs.parent / "review").exists(), "no review work directory was made")

    def test_a_refusal_leaves_no_session_and_no_spend(self):
        self.answer("another version")
        rev = self.reviewer("fix-loop")
        with self.assertRaises(CapabilityUnrunnable):
            rev.review(types.SimpleNamespace(story_id="S1", root=str(self.repo)), ("C-ADD",))
        self.assertEqual(rev.sessions, [])

    def test_a_binary_that_cannot_be_started_is_refused_not_raised(self):
        self.answer("pinned")
        self.exe.chmod(0o644)       # readable, so the sha256 check passes; not executable
        with self.assertRaises(CapabilityUnrunnable) as cm:
            self.review()
        self.assertIn("could not be started", str(cm.exception))
        self.assertEqual(self.calls(), [])

    def test_the_bytes_are_checked_before_the_version_is_asked(self):
        self.answer("pinned")
        with self.assertRaises(CapabilityUnrunnable) as cm:
            self.review(sha256="0" * 64)
        self.assertIn("not the pinned", str(cm.exception))
        self.assertEqual(self.calls(), [], "a binary that is not the pinned bytes is never started, not even for `version`")

    def test_the_question_has_its_own_bound_whatever_the_review_s_deadline(self):
        """The review's deadline (here none at all) is for the review; the version question is answered at once by a
        build that is the pinned one, so the deadline of the review must not refuse it."""
        self.answer("pinned")
        rev = self.reviewer("advisory")      # a review that timed out is recorded under advisory, refused under fix-loop
        rev.timeout_s = 0.0
        _, s, _ = rev._ocr(types.SimpleNamespace(story_id="S1", root=str(self.repo)), 1, e2e.git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(s["identity"]["declared"]["version"], "v1.12.12")
        self.assertTrue(s["timed_out"])             # and the review itself did time out, at its own deadline


@POSIX
class Chain(chain.ChainBase):
    """Through `aisef run`: a binary that is not the pinned build never reviews the candidate, the story is never
    committed on it, and the operator reads both sides in the journal.

    The run's own preflight asks the binary first (test_v21_ocr_preflight.py: a binary that is wrong from the start is
    refused there, before any session). What is tested here is the review's own question at the moment of use, so
    the binary answers as the pinned build the first time — the preflight's — and as `name` every time after: a
    binary that said one thing before the developer worked and another when it was to review."""

    def identity(self, name: str) -> None:
        text, code, sleep = ANSWERS[name]
        (self.bin / "identity.json").write_text(json.dumps({"text": text, "exit": code, "sleep": sleep, "after_asks": 1}),
                                                encoding="utf-8")

    def started(self) -> list[list[str]]:
        p = self.bin / "calls.jsonl"
        return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    def assert_refused_before_any_review(self, name: str, policy: str) -> None:
        self.identity(name)
        rec = self.run_with([chain.FIXED], [{}], policy=policy)
        self.assertEqual((rec["story_outcomes"], rec["delivery_verdict"]), ({"S1": ["RETRY", "ROLLBACK"]}, "FAIL"), name)
        self.assertEqual(self.failures(), ["CAPABILITY_UNRUNNABLE", "CAPABILITY_UNRUNNABLE"])
        said = [e.data["detail"] for e in self.events() if e.type == "provider/result" and "reviewer cannot run" in e.data["detail"]]
        self.assertEqual(len(said), 2, said)
        for word in REFUSED[name]:
            self.assertTrue(all(word in d for d in said), (name, word, said))
        self.assertEqual(set(map(tuple, self.started())), {("version",)}, "only the version question was ever asked")
        self.assertEqual(len(self.started()), 3, "the preflight's question, then one at the moment of each of two reviews")
        self.assertEqual(list(self.bin.glob("review-*.json")), [])
        self.assertEqual(git_main(self), self.baseline)
        self.assertEqual([s["role"] for s in rec["sessions"]], ["developer", "developer"])     # no reviewer session at all

    def test_another_release_is_never_reviewed_with_under_fix_loop(self):
        self.assert_refused_before_any_review("another version", "fix-loop")

    def test_another_commit_is_never_reviewed_with_under_advisory_either(self):
        self.assert_refused_before_any_review("another commit", "advisory")

    def test_a_binary_that_prints_no_version_is_never_reviewed_with(self):
        self.assert_refused_before_any_review("no version command", "fix-loop")

    def test_the_pinned_build_is_asked_once_per_review_and_commits(self):
        rec = self.run_with([chain.FIXED], [{}])
        self.assertEqual(rec["story_outcomes"], {"S1": ["COMMIT"]})
        kinds = ["version" if a == ["version"] else "preview" if "--preview" in a else "review" for a in self.started()]
        # the first question is the run's preflight (before the clone and every session); the second is the review's
        # own, at the moment of use, before its preview and its review
        self.assertEqual(kinds, ["version", "version", "preview", "review"])
        (s,) = [x for x in rec["sessions"] if x["role"] == "reviewer"]
        self.assertEqual(s["identity"]["declared"]["version"], "v1.12.12")
        self.assertIn("self-declaration", s["identity"]["declared_by"])


def git_main(case: unittest.TestCase) -> str:
    return e2e.git(case.out / "repo", "rev-parse", "main")


if __name__ == "__main__":
    unittest.main()
