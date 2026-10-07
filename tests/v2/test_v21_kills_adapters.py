"""V2.1 (owner B-03b): kill tests for the survivors of aisef2/app/adapters.py's V2.1 mutation targets, each class named
by the target and the mutants it kills. In the kill set of exactly the targets it kills (validation/v2/mutation.py)."""

from __future__ import annotations

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
from aisef2.app import bundle, client  # noqa: E402
from aisef2.arch.enums import ControlProjection  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402


class _Reviewer(unittest.TestCase):
    """A Reviewer over the two-story calc bundle and its repository (no test of its own)."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        e2e.make_repo(self.tmp / "repo")
        self.project = bundle.load(e2e.project_bundle("a" * 40))
        self.run = types.SimpleNamespace(events=[], state=lambda proj: {"S1": {"attempt": 2}}
                                         if proj is ControlProjection.STORY_STATE else None)


class ReviewerModel(_Reviewer):
    """Reviewer._model — "L137 string 'reviewer ' emptied", "L138 string '.reviewer.' emptied", "L139 string 'reviewer'
    emptied": the model review's session is the reviewer's by the title the client is run with (`--title`), by the name
    of its evidence log (the run's sessions/ directory) and by the role its session record carries into RUN.json."""

    def test_the_review_session_is_titled_logged_and_recorded_as_the_reviewer_s(self):
        calls = []

        def fake(name, prompt, cwd, log, timeout_s, **kw):
            calls.append((name, log.name))
            return {"exit": 0, "timed_out": False, "stopped": None, "started": True, "error": None,
                    "text": '{"findings": []}', "turns": 1, "tokens": {"input": 1, "output": 1}, "seconds": 0.0, "log": log.name}
        rev = ad.Reviewer(self.run, self.project, self.tmp / "logs", {}, 5)
        with mock.patch.object(client, "session", fake):
            found, s, _ = rev._model(types.SimpleNamespace(story_id="S1", root=str(self.tmp / "repo")), 3)
        self.assertEqual(found, [])
        self.assertEqual(calls, [("reviewer S1", "S1.reviewer.3.jsonl")])
        self.assertEqual((s["role"], s["story_id"], s["attempt"], s["log"]), ("reviewer", "S1", 3, "S1.reviewer.3.jsonl"))
        self.assertEqual(rev.sessions, [s])


class ReviewerVerify(_Reviewer):
    """Reviewer._verify — "L233 string 'no reproducer: the finding states no observable behaviour' emptied": a finding
    with no reproducer is UNVERIFIABLE, and the reason the run records for the operator (finding.verification.why) says
    why; no probe is run for it."""

    def test_a_finding_without_a_reproducer_is_unverifiable_for_a_stated_reason_and_runs_nothing(self):
        rev = ad.Reviewer(self.run, self.project, self.tmp / "logs", {}, 5)
        with mock.patch.object(ad.review_verify, "verify", side_effect=AssertionError("no probe for a finding without one")):
            for finding in ({"id": "F1"}, {"id": "F2", "reproducer": "run it"}, {"id": "F3", "reproducer": None}):
                with self.subTest(finding=finding):
                    v = rev._verify(finding, str(self.tmp / "repo"), "a" * 40)
                    self.assertEqual((v.status, v.reason), (ad.review_verify.UNVERIFIABLE,
                                                            "no reproducer: the finding states no observable behaviour"))


class ReviewerInit(_Reviewer):
    """Reviewer.__init__ — "L104 Or swapped" (`sys.executable or interpreter`): the interpreter the run gives the review is
    the one its probes run under (app/run: the run's probe interpreter, V2.1 A1); without one, this Python."""

    def test_the_verification_runs_the_probe_under_the_interpreter_the_run_gave(self):
        seen = []

        def verify(finding, **kw):
            seen.append(kw["interpreter"])
            return ad.review_verify.Verification(ad.review_verify.UNVERIFIABLE, "stub")
        finding = {"id": "F1", "reproducer": {"kind": "python_callable"}}
        with mock.patch.object(ad.review_verify, "verify", verify):
            ad.Reviewer(self.run, self.project, self.tmp / "logs", {}, 5, interpreter="/opt/run/bin/python3")._verify(
                finding, str(self.tmp / "repo"), "a" * 40)
            ad.Reviewer(self.run, self.project, self.tmp / "logs", {}, 5)._verify(finding, str(self.tmp / "repo"), "a" * 40)
        self.assertEqual(seen, ["/opt/run/bin/python3", sys.executable])


class ReviewerReview(_Reviewer):
    """Reviewer.review — "L111 string 'the checkout to review has no revision' emptied", "L116 string 'the finder'
    emptied", "L127 string 'the verification' emptied", "L123 dict entry 0/1/2 dropped", "L123 string 'anchor'/'status'/
    'why'/'contracts' emptied", "L130 string ', ' emptied", "L132 string ', confirmed=' emptied": what the review
    refuses says why and during which stage; each finding's record carries its anchor (status, why, contracts) next to
    its verification; the review's detail names the OCR coverage and how many findings were confirmed."""

    RV = ad.review_verify

    def scope(self, root=None):
        return types.SimpleNamespace(story_id="S1", root=str(root or self.tmp / "repo"))

    def reviewer(self, **review):
        return ad.Reviewer(self.run, self.project, self.tmp / "logs", {}, 5,
                           review={"policy": "fix-loop", "min_severity": "low", "finder": "model", "ocr": None,
                                   "given": True, **review})

    def test_a_checkout_with_no_revision_is_refused_saying_so(self):
        (self.tmp / "plain").mkdir()
        with self.assertRaises(ad.CapabilityUnrunnable) as c:
            self.reviewer().review(self.scope(self.tmp / "plain"), ("C-ADD",))
        self.assertEqual(str(c.exception), "the checkout to review has no revision")

    def test_a_change_to_the_checkout_names_the_stage_it_happened_in(self):
        repo = self.tmp / "repo"

        def touch(name):
            def run(*a, **k):
                (repo / name).write_text("changed\n")
                return ([{"id": "F1"}], {}, None) if name == "by-finder.txt" else self.RV.Verification(self.RV.UNVERIFIABLE, "x")
            return run
        rev = self.reviewer()
        with mock.patch.object(rev, "_model", touch("by-finder.txt")), self.assertRaises(ad.CapabilityUnrunnable) as c:
            rev.review(self.scope(), ("C-ADD",))
        self.assertEqual(str(c.exception), "the reviewed checkout changed during the finder: ['by-finder.txt'] "
                                           "(every finding discarded)")
        (repo / "by-finder.txt").unlink()
        rev = self.reviewer()
        with mock.patch.object(rev, "_model", return_value=([{"id": "F1"}], {}, None)), \
                mock.patch.object(rev, "_verify", touch("by-verification.txt")), self.assertRaises(ad.CapabilityUnrunnable) as c:
            rev.review(self.scope(), ("C-ADD",))
        self.assertEqual(str(c.exception), "the reviewed checkout changed during the verification: ['by-verification.txt'] "
                                           "(every finding discarded)")

    def test_the_findings_record_carries_its_anchor_and_the_detail_counts_the_confirmed(self):
        rev, s = self.reviewer(), {"parsed": True}
        found = [{"id": "F1", "severity": "high", "reproducer": {"kind": "python_callable"}}, {"id": "F2"}]
        with mock.patch.object(rev, "_model", return_value=(found, s, None)), \
                mock.patch.object(rev, "_verify", return_value=self.RV.Verification(self.RV.CONFIRMED, "reproduced", "pc2", "VIOLATED")), \
                mock.patch.object(self.RV, "anchor", return_value=self.RV.Anchor(self.RV.ANCHORED, "clause C1", ("BC-ADD",))):
            r = rev.review(self.scope(), ("C-ADD",))
        self.assertEqual(s["findings"][0]["anchor"], {"status": "ANCHORED", "why": "clause C1", "contracts": ["BC-ADD"]})
        self.assertNotIn("anchor", s["findings"][1])          # no reproducer, nothing to anchor
        self.assertEqual(s["findings"][0]["verification"], {"status": self.RV.CONFIRMED, "why": "reproduced", "probe": "pc2",
                                                            "observed": "VIOLATED"})
        # F2 is CONFIRMED by the (stubbed) probe but has no reproducer to anchor: under fix-loop it does not block
        self.assertEqual([(f.id, f.blocks) for f in r.findings], [("F1", True), ("F2", False)])
        self.assertEqual(r.detail, "2 findings, parsed=True, confirmed=1")

    def test_the_ocr_review_s_detail_names_its_coverage(self):
        rev = self.reviewer(finder="ocr")
        with mock.patch.object(rev, "_ocr", return_value=([], {}, "coverage COMPLETE")):
            self.assertEqual(rev.review(self.scope(), ("C-ADD",)).detail, "0 findings, coverage COMPLETE")


class Unchanged(_Reviewer):
    """_unchanged — "L262 string ' (every finding discarded)' emptied", "L266 sorted() -> list()", "L267 string ': '
    emptied", "L267 string ' (every finding discarded)' emptied": a review whose checkout moved says what moved — a new
    HEAD, or the changed paths in order — and that every finding was discarded."""

    def test_a_moved_head_or_changed_paths_are_named_in_order_and_every_finding_discarded(self):
        repo = self.tmp / "repo"
        head = e2e.git(repo, "rev-parse", "HEAD")
        before = ad.tree_of(str(repo))
        names = ["zeta.txt", "alpha.txt", "mid.txt", "kilo.txt", "echo.txt", "yank.txt", "bravo.txt", "papa.txt"]
        for name in names:     # eight: an unsorted set order is in sorted order by chance once in 40 320 runs
            (repo / name).write_text("x\n")
        with self.assertRaises(ad.CapabilityUnrunnable) as c:
            ad._unchanged(str(repo), head, before, "the finder")
        self.assertEqual(str(c.exception), f"the reviewed checkout changed during the finder: {sorted(names)} "
                                           "(every finding discarded)")
        e2e.git(repo, "add", "-A")
        e2e.git(repo, "commit", "-qm", "moved")
        with self.assertRaises(ad.CapabilityUnrunnable) as c:
            ad._unchanged(str(repo), head, before, "the verification")
        self.assertEqual(str(c.exception), f"the reviewed checkout changed during the verification: HEAD is no longer "
                                           f"{head[:12]} (every finding discarded)")


class TreeOf(_Reviewer):
    """tree_of — "L244 element 0 dropped" (directories not recorded), "L248 string 'link:' emptied", "L250 string 'dir'
    emptied", "L243 string '.git' emptied", "L255 string 'unreadable:' emptied": the checkout's record holds every entry
    but .git — a file by its sha256, a link by its target, a directory as one — so that a review which adds an empty
    directory or turns a directory into a link is caught by _unchanged, and git's own bookkeeping is not a change."""

    def test_the_record_distinguishes_each_kind_of_entry_and_leaves_out_git(self):
        import hashlib
        import os
        repo = self.tmp / "repo"
        (repo / "sub").mkdir()
        (repo / "sub" / "f.txt").write_text("x\n")
        os.symlink("sub/f.txt", repo / "link")
        locked = repo / "locked.txt"
        locked.write_text("secret\n")
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o600)
        t = ad.tree_of(str(repo))
        self.assertEqual(t["sub"], "dir")
        self.assertEqual(t["sub/f.txt"], hashlib.sha256(b"x\n").hexdigest())
        self.assertEqual(t["link"], "link:sub/f.txt")
        if os.geteuid() != 0:     # root reads a 000 file
            self.assertEqual(t["locked.txt"], "unreadable:PermissionError")
        self.assertEqual([k for k in t if k == ".git" or k.startswith(".git/")], [])

    def test_an_empty_directory_or_a_directory_turned_into_a_link_named_dir_is_a_change(self):
        import os
        repo = self.tmp / "repo"
        head = e2e.git(repo, "rev-parse", "HEAD")
        (repo / "d").mkdir()
        before = ad.tree_of(str(repo))
        (repo / "empty").mkdir()
        with self.assertRaises(ad.CapabilityUnrunnable) as c:
            ad._unchanged(str(repo), head, before, "the finder")
        self.assertIn("['empty']", str(c.exception))
        (repo / "empty").rmdir()
        (repo / "d").rmdir()
        os.symlink("dir", repo / "d")          # a link whose target reads like a directory's record
        with self.assertRaises(ad.CapabilityUnrunnable) as c:
            ad._unchanged(str(repo), head, before, "the finder")
        self.assertIn("['d']", str(c.exception))


if __name__ == "__main__":
    unittest.main()
