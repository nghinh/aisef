"""V2.1 (owner B-03 round 3, item 5): a finding's full reproducer is kept — whole, secret-redacted, identified and bound
to the evidence — and a block needs it.

* `review_verify.preserve`: the artifact — its content, create-only, written whole before it becomes visible, a failure
  to keep is a reason and never an exception;
* `review_verify.artifact_problems`: what `aisef run --verify` says of a review row against the files;
* `run.evidence_manifest`: the manifest lists the artifacts and a directory without any lists what it always did;
* `adapters.Reviewer.review`: preserved before the row is built, a statement that names it, the run's secrets (the
  client environment, the provider key, OCR's token) out of everything persisted, and — when a finding that would
  block cannot be preserved — the review is refused (never a block on a cut statement, never a silent pass).

The same behaviour through `aisef run` (a real journal, a real manifest, `--verify`): test_v21_r3_detail_product.py.

Pins aisef2/app/review_verify.py::preserve, ::artifact_problems; aisef2/app/run.py::evidence_manifest;
aisef2/app/adapters.py::Reviewer.review"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle  # noqa: E402
from aisef2.app import review_verify as V  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.arch.enums import ControlProjection  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402

SECRET = "zq9-KEY-7f3a91c2b8"
TOKEN = "ocr-token-5d0c77e1aa"
HEAD = "a" * 40
MAIN = {"kind": "cli_invocation", "locator": "ledgerlock:__main__"}
REASON = "probe.cli_invocation refutes the behaviour R-9 is said to demand"


def finding(stimulus=None, **top) -> dict:
    f = {"id": "FND-7", "blocking": True, "severity": "high", "summary": "snapshot of a missing file must exit 3",
         "reproducer": {"clause": "R-9/3", "subject": dict(MAIN),
                        "stimulus": {"argv": ["snapshot", "<ws>/missing.jsonl"]} if stimulus is None else stimulus,
                        "observable": {"exit_code": 3, "within_s": 10}},
         "verification": {"status": V.CONFIRMED, "why": REASON, "probe": "probe.cli_invocation", "observed": "REFUTED"},
         "anchor": {"status": V.ANCHORED, "why": "clause R-9/3's approved outcome", "contracts": ["BC-1", "BC-2"]}}
    f.update(top)
    return f


class Scratch(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.out = self.tmp / "out"
        self.out.mkdir()
        self.folder = self.out / V.ARTIFACT_DIR

    def keep(self, f=None, **kw) -> V.Artifact | str:
        kw = {"story": "S1", "attempt": 2, "index": 0, "revision": HEAD, "session": "S1.reviewer.2.jsonl", **kw}
        return V.preserve(self.out, finding() if f is None else f, **kw)


class PreserveWritesTheWholeFinding(Scratch):
    def test_the_file_holds_the_whole_finding_with_the_run_s_secrets_replaced(self):
        stimulus = {"argv": ["snapshot", "--key", SECRET], "stdin": {"text": "x" * 5000 + SECRET + "tail"}}
        f = finding(stimulus)
        f["summary"] = f"uses {SECRET}"
        art = self.keep(f, secrets=(SECRET,))
        self.assertIsInstance(art, V.Artifact)
        self.assertEqual(art.path, "review-findings/S1.2.0.json")
        data = (self.out / art.path).read_bytes()
        self.assertEqual((art.sha256, art.size), (hashlib.sha256(data).hexdigest(), len(data)))
        self.assertTrue(data.isascii() and data.endswith(b"\n"))
        want = json.loads(json.dumps(f).replace(SECRET, V.REDACTED))
        self.assertEqual(json.loads(data), {
            "format": V.ARTIFACT_FORMAT, "story_id": "S1", "attempt": 2, "index": 0, "revision": HEAD,
            "session": "S1.reviewer.2.jsonl", "redacted": 3, "finding": want})
        self.assertNotIn(SECRET.encode(), data)
        self.assertEqual(len(json.loads(data)["finding"]["reproducer"]["stimulus"]["stdin"]["text"]), 5000 + 10 + 4)
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["S1.2.0.json"])     # no temporary left

    def test_a_secret_of_digits_written_as_a_number_is_replaced_in_the_file_too(self):
        pin = "1234567890"
        art = self.keep(finding({"args": [int(pin), 7], "stdin": {"text": f"pin={pin}"}}), secrets=(pin,))
        data = (self.out / art.path).read_bytes()
        self.assertNotIn(pin.encode(), data)
        doc = json.loads(data)
        self.assertEqual(doc["finding"]["reproducer"]["stimulus"],
                         {"args": [V.REDACTED, 7], "stdin": {"text": f"pin={V.REDACTED}"}})
        self.assertEqual(doc["redacted"], 2)

    def test_a_finding_with_nothing_to_replace_is_kept_exactly_and_says_so(self):
        f = finding({"argv": ["a"], "stdin": {"text": "é中\n"}})
        art = self.keep(f)
        doc = json.loads((self.out / art.path).read_bytes())
        self.assertEqual((doc["redacted"], doc["finding"]), (0, f))

    def test_two_findings_with_one_id_have_two_files(self):
        a = self.keep(finding(id="same"), index=0)
        b = self.keep(finding(id="same", summary="another"), index=1)
        self.assertEqual((a.path, b.path), ("review-findings/S1.2.0.json", "review-findings/S1.2.1.json"))
        self.assertNotEqual(a.sha256, b.sha256)
        self.assertEqual([json.loads((self.out / x.path).read_bytes())["index"] for x in (a, b)], [0, 1])

    def test_an_artifact_is_never_overwritten(self):
        first = self.keep()
        before = (self.out / first.path).read_bytes()
        again = self.keep(finding(summary="changed"))
        self.assertIsInstance(again, str)
        self.assertTrue(again.startswith("FileExistsError: "), again)
        self.assertIn("S1.2.0.json", again)
        self.assertIn("never overwritten", again)
        self.assertEqual((self.out / first.path).read_bytes(), before)

    def test_the_file_is_whole_before_it_is_visible_and_a_failed_write_leaves_nothing_visible(self):
        real, seen = os.replace, []

        def replace(src, dst):
            seen.append((pathlib.Path(dst).exists(), json.loads(pathlib.Path(src).read_bytes())["finding"]["id"]))
            real(src, dst)
        with mock.patch.object(V.os, "replace", replace):
            art = self.keep()
        self.assertEqual(seen, [(False, "FND-7")])      # complete, parseable, and the final name not yet taken
        self.assertTrue((self.out / art.path).is_file())
        for index, broken in ((5, "fsync"), (6, "replace")):
            with self.subTest(broken=broken), mock.patch.object(V.os, broken, side_effect=OSError(28, "No space left")):
                why = self.keep(index=index)
                self.assertIsInstance(why, str)
                self.assertIn("OSError", why)
                self.assertEqual(sorted(p.name for p in self.folder.glob("*.json")), ["S1.2.0.json"])   # what a reader globs

    def test_the_bytes_do_not_depend_on_the_order_of_the_finders_keys(self):
        a = {"id": "F", "summary": "s", "reproducer": {"clause": "R-9/3", "stimulus": {"argv": ["a"], "stdin": None}}}
        b = {"reproducer": {"stimulus": {"stdin": None, "argv": ["a"]}, "clause": "R-9/3"}, "summary": "s", "id": "F"}
        elsewhere = self.tmp / "out-2"
        elsewhere.mkdir()
        first = self.keep(a)
        second = V.preserve(elsewhere, b, story="S1", attempt=2, index=0, revision=HEAD, session="S1.reviewer.2.jsonl")
        self.assertEqual(first, second)         # path, sha256 and size
        self.assertEqual((self.out / first.path).read_bytes(), (elsewhere / second.path).read_bytes())

    def test_an_unsafe_story_id_is_written_with_underscores_and_its_digest(self):
        """An id that is not a file name as it stands is a name-safe prefix of at most 40 characters and the first 8 hex
        digits of the id's sha256 (reviewer fix: without them `STORY.1` and `STORY_1`, or two ids that share their
        first 40 characters, made one file name and the second story's review was refused every attempt)."""
        def digest(s: str) -> str:
            return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]
        self.assertEqual(self.keep(story="a b/c:d").path, f"review-findings/a_b_c_d-{digest('a b/c:d')}.2.0.json")
        self.assertEqual(self.keep(story="x" * 90, index=1).path,
                         "review-findings/" + "x" * 40 + f"-{digest('x' * 90)}.2.1.json")
        self.assertEqual(self.keep(story="a-b_c").path, "review-findings/a-b_c.2.0.json")     # a file name: as it is
        # a lone surrogate (json.loads yields one from "\ud800") has no UTF-8 form: the digest is of its escape, and the
        # file is still made (an id that cannot be hashed is not a reason to refuse a review)
        lone = "a\ud800b"
        art = self.keep(story=lone, index=3)
        self.assertIsInstance(art, V.Artifact, art)
        escaped = hashlib.sha256(lone.encode("utf-8", "backslashreplace")).hexdigest()[:8]
        self.assertEqual(art.path, f"review-findings/a_b-{escaped}.2.3.json")
        self.assertEqual(json.loads((self.out / art.path).read_bytes())["story_id"], lone)

    def test_two_story_ids_that_read_alike_have_two_files_and_each_is_its_own(self):
        longer = "ledgerlock-snapshot-command-handles-missing-file"     # shares its first 40 characters with the next
        pairs = (("STORY.1", "STORY_1"), ("feature/login", "feature_login"), (longer + "-A", longer + "-B"))
        for first, second in pairs:
            with self.subTest(first=first, second=second):
                a = self.keep(finding(summary="first"), story=first)
                b = self.keep(finding(summary="second"), story=second)
                self.assertIsInstance(a, V.Artifact, a)
                self.assertIsInstance(b, V.Artifact, b)
                self.assertNotEqual(a.path, b.path)
                docs = [json.loads((self.out / x.path).read_bytes()) for x in (a, b)]
                self.assertEqual([d["story_id"] for d in docs], [first, second])
                self.assertEqual([d["finding"]["summary"] for d in docs], ["first", "second"])
                for x in (a, b):
                    self.assertRegex(x.path, r"^review-findings/[A-Za-z0-9_.-]{1,80}\.json$")

    def test_a_name_that_is_not_one_leaves_no_file(self):
        why = self.keep(attempt=10 ** 100)
        self.assertTrue(why.startswith("ValueError: not a review artifact reference"), why)
        self.assertFalse(self.folder.exists())

    def test_a_failure_to_keep_is_a_reason_and_never_an_exception(self):
        unwritable = self.tmp / "no-such-run-directory"
        self.assertIn("FileNotFoundError", V.preserve(unwritable, finding(), story="S1", attempt=1, index=0, revision=HEAD))
        blocked = self.tmp / "blocked"
        blocked.mkdir()
        (blocked / V.ARTIFACT_DIR).write_text("a file where the directory goes")
        why = V.preserve(blocked, finding(), story="S1", attempt=1, index=0, revision=HEAD)
        self.assertIsInstance(why, str)
        self.assertTrue(why.startswith(("FileExistsError", "NotADirectoryError")), why)
        why = self.keep(attempt=object())                # not serialisable
        self.assertTrue(why.startswith("TypeError: "), why)

    def test_a_story_id_that_is_not_a_file_name_still_names_a_file_inside_the_directory(self):
        art = self.keep(story="../../x/..\\S 1" + "z" * 100)
        self.assertRegex(art.path, r"^review-findings/[A-Za-z0-9_.-]{1,80}\.json$")
        self.assertEqual([p.parent for p in self.out.rglob("*.json")], [self.folder])
        self.assertEqual(json.loads((self.out / art.path).read_bytes())["story_id"], "../../x/..\\S 1" + "z" * 100)


def row(seq: int, story: str, fid: str, detail: str, passed: bool = True) -> dict:
    return {"seq": seq, "type": "gate/check", "data": {"gate": "story", "check": f"{story}:review:{fid}", "passed": passed,
                                                       "detail": detail}}


class ArtifactProblems(Scratch):
    """The verifier's half of the binding. Each case is one journal row against the files; `problems` refute the run,
    `notes` do not change its verdict."""

    def stated(self, f=None, art=None, **kw) -> str:
        f = f or finding()
        art = art or self.keep(f, **kw)
        return V.detail(f, V.Verification(V.CONFIRMED, REASON, "probe.cli_invocation", "REFUTED"), None, art)

    def check(self, *rows):
        return V.artifact_problems(self.out, list(rows))

    def assert_row(self, problem: str, tail: str, seq=9, check="S1:review:FND-7") -> None:
        """A problem names the row (its seq and check) and then what is wrong with it."""
        self.assertRegex(problem, rf"^review row {seq} \({check}\): {tail}")

    def test_a_row_whose_artifact_is_there_and_is_the_one_it_binds_has_no_problem(self):
        text = self.stated()
        self.assertEqual(self.check(row(9, "S1", "FND-7", f"blocking, corroborated by probe:p:REFUTED — {text}", False)),
                         ([], []))
        self.assertEqual(self.check(row(9, "S1", "FND-7", f"informational — {text}")), ([], []))

    def test_a_missing_or_unreadable_artifact_is_a_problem_naming_the_row_and_the_file(self):
        text = self.stated()
        next(self.folder.glob("*.json")).rename(self.tmp / "moved.json")
        problems, notes = self.check(row(9, "S1", "FND-7", f"informational — {text}"))
        self.assertEqual(notes, [])
        self.assertEqual(len(problems), 1)
        self.assert_row(problems[0], r"its artifact review-findings/S1\.2\.0\.json cannot be read \(FileNotFoundError\)$")

    def test_an_altered_artifact_is_a_problem_whatever_the_manifest_says(self):
        """The row binds the bytes through the hash-chained journal: rewriting the file and the manifest together does
        not make it the file the row names."""
        text = self.stated()
        path = next(self.folder.glob("*.json"))
        same_size = path.read_bytes().replace(b"FND-7", b"FND-8")
        self.assertEqual(len(same_size), path.stat().st_size)
        path.write_bytes(same_size)
        problems, _ = self.check(row(9, "S1", "FND-7", f"informational — {text}"))
        self.assertEqual(len(problems), 1)
        self.assert_row(problems[0], r"its artifact review-findings/S1\.2\.0\.json is not the file the row binds")
        path.write_bytes(same_size + b" ")
        problems, _ = self.check(row(9, "S1", "FND-7", f"x — {text}"))
        self.assert_row(problems[0], r"its artifact review-findings/S1\.2\.0\.json is not the file the row binds")

    def test_an_artifact_of_another_story_or_another_finding_is_not_this_rows(self):
        text = self.stated()
        for story, fid in (("S2", "FND-7"), ("S1", "OTHER")):
            with self.subTest(story=story, fid=fid):
                if fid == "OTHER":      # the row's statement names a finding the file does not hold
                    other = text.replace('"finding": "FND-7"', '"finding": "OTHER"')
                    problems, _ = self.check(row(9, story, fid, f"informational — {other}"))
                else:
                    problems, _ = self.check(row(9, story, fid, f"informational — {text}"))
                self.assertEqual(len(problems), 1)
                self.assert_row(problems[0], r"its artifact review-findings/S1\.2\.0\.json is not this story's statement "
                                             r"of this finding$", check=f"{story}:review:{fid}")

    def test_a_row_that_names_a_path_outside_the_directory_is_a_problem_and_nothing_is_read(self):
        text = self.stated()
        real = json.loads(text)["artifact"]["path"]
        for path in ("RUN.json", "review-findings/../RUN.json", "/etc/passwd", "review-findings/a/b.json",
                     "review-findings\\S1.2.0.json", "", "review-findings", "review-findings/.."):
            with self.subTest(path=path):
                forged = text.replace(real, path.replace("\\", "\\\\"))
                problems, _ = self.check(row(9, "S1", "FND-7", f"informational — {forged}"))
                self.assertEqual(len(problems), 1)
                self.assert_row(problems[0], rf"names {re.escape(repr(path))}, which is not a file of review-findings/$")

    def test_a_reference_that_is_not_a_reference_is_a_problem(self):
        text = self.stated()
        real = json.dumps(json.loads(text)["artifact"], sort_keys=True)
        for passed in (True, False):
            for ref in ('"review-findings/S1.2.0.json"', "[1, 2]", "7", "true"):
                with self.subTest(ref=ref, passed=passed):
                    forged = text.replace(real, ref)
                    self.assertNotEqual(forged, text)
                    problems, notes = self.check(row(9, "S1", "FND-7", f"informational — {forged}", passed))
                    self.assertEqual((len(problems), notes), (1, []))
                    self.assert_row(problems[0], r"its artifact reference .* is not a path, a size and a sha256$")

    def test_a_blocking_row_without_an_artifact_is_a_note_for_an_earlier_release_and_a_problem_for_this_one(self):
        old = V.detail(finding(), V.Verification(V.CONFIRMED, REASON, "probe.cli_invocation", "REFUTED"), None)    # no `artifact`
        problems, notes = self.check(row(4, "S1", "FND-7", f"blocking, corroborated by probe:p:REFUTED — {old}", False))
        self.assertEqual(problems, [])
        self.assertEqual(len(notes), 1)
        self.assert_row(notes[0], r"blocked on a statement with no preserved reproducer", seq=4)
        none = V.detail(finding(), V.Verification(V.CONFIRMED, REASON, "p", "REFUTED"), None, "OSError: disk full")
        problems, notes = self.check(row(4, "S1", "FND-7", f"blocking, corroborated by probe:p:REFUTED — {none}", False))
        self.assertEqual(notes, [])
        self.assertEqual(len(problems), 1)
        self.assert_row(problems[0], r"it blocked and names no artifact", seq=4)
        # a row that did not block says artifact: null as a fact, and is neither
        self.assertEqual(self.check(row(4, "S1", "FND-7", f"informational — {none}")), ([], []))

    def test_what_is_not_a_review_row_with_a_statement_is_not_read(self):
        text = self.stated()
        rows = [
            {"seq": 1, "type": "provider/result", "data": {"check": "S1:review:F", "detail": f"x — {text}"}},
            row(2, "S1", "F", "reviewed: no finding"),
            {"seq": 3, "type": "gate/check", "data": {"gate": "story", "check": "S1:review", "passed": True,
                                                      "detail": f"reviewed — {text}"}},
            row(4, "S1", "F", "informational — not json"),
            row(5, "S1", "F", "informational — [1, 2]"),
            row(6, "S1", "F", "advisory: a model review alone is never the sole blocking authority (D-002)", True),
            row(7, "S1", "F", "informational — " + json.dumps({"finding": "F"})),
            {"seq": 8, "type": "gate/check", "data": None},
            {"seq": 9, "type": "gate/check", "data": {"check": "S1:scan:ruff", "detail": "x — {}", "passed": True}},
        ]
        self.assertEqual(self.check(*rows), ([], []))


class ManifestBindsTheArtifacts(Scratch):
    def lay(self, files: dict) -> None:
        for rel, data in files.items():
            p = self.out / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)

    def test_the_artifacts_are_listed_with_the_digest_the_row_binds(self):
        self.lay({"RUN.json": b"{}", "RUN.started.json": b"{}", "run/journals/aisef-run.jsonl": b"j\n",
                  "sessions/S1.reviewer.1.jsonl": b"s\n", "preflight/LEDGER.jsonl": b"l\n", "repo/x.json": b"x"})
        art = self.keep()
        self.lay({"review-findings/S1.2.0.json.tmp": b"half", "review-findings/notes.txt": b"x",
                  "review/S1.1/output.json": b"o"})
        files = R.evidence_manifest(self.out)["files"]
        self.assertEqual(sorted(files), ["RUN.json", "RUN.started.json", "preflight/LEDGER.jsonl", art.path,
                                         "run/journals/aisef-run.jsonl", "sessions/S1.reviewer.1.jsonl"])
        self.assertEqual(files[art.path], art.sha256)

    def test_a_run_directory_with_no_review_findings_lists_exactly_what_it_always_did(self):
        self.lay({"RUN.json": b"{}", "RUN.started.json": b"{}", "run/journals/aisef-run.jsonl": b"j\n",
                  "sessions/S1.reviewer.1.jsonl": b"s\n", "preflight/PREFLIGHT.json": b"p"})
        m = R.evidence_manifest(self.out)
        self.assertEqual(m["format"], "aisef-v2-evidence/1")       # not bumped: nothing changes for such a run
        self.assertEqual(m["files"], {
            "RUN.json": R._content_sha(self.out / "RUN.json"), "RUN.started.json": hashlib.sha256(b"{}").hexdigest(),
            "run/journals/aisef-run.jsonl": hashlib.sha256(b"j\n").hexdigest(),
            "sessions/S1.reviewer.1.jsonl": hashlib.sha256(b"s\n").hexdigest(),
            "preflight/PREFLIGHT.json": hashlib.sha256(b"p").hexdigest()})
        self.keep()
        self.assertEqual(len(R.evidence_manifest(self.out)["files"]), 6)       # only the kept finding's file is new

    def test_every_group_is_listed_in_name_order(self):
        """The manifest is a mapping and nothing reads its order; each group is listed in name order, so that the
        same directory is always the same document, whatever order its files were created or the file system lists
        them in."""
        scrambled = (7, 2, 11, 5, 0, 9, 3, 10, 1, 8, 4, 6)      # twelve names: 1 in 479,001,600 to come out sorted by luck
        self.lay({f"{group}/f{n:02d}.jsonl": b"x" for group in ("sessions", "run/journals", "preflight")
                  for n in scrambled})
        for index in scrambled:                    # created out of order
            self.keep(finding(summary=str(index)), index=index)
        listed = list(R.evidence_manifest(self.out)["files"])
        for group in ("sessions/", "run/journals/", "preflight/", "review-findings/"):
            members = [k for k in listed if k.startswith(group)]
            self.assertEqual(len(members), 12, group)
            self.assertEqual(members, sorted(members), group)

    def test_changing_a_kept_finding_changes_the_run_s_anchor(self):
        self.lay({"RUN.json": b"{}"})
        art = self.keep()
        before = R.anchor_of(R.evidence_manifest(self.out))
        (self.out / art.path).write_bytes((self.out / art.path).read_bytes().replace(b"FND-7", b"FND-8"))
        self.assertNotEqual(R.anchor_of(R.evidence_manifest(self.out)), before)


class _Reviewer(unittest.TestCase):
    """A Reviewer whose finder is stubbed: the checkout is a real git repository, `found` is the finder's list."""

    RV = V

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        e2e.make_repo(self.tmp / "repo")
        self.project = bundle.load(e2e.project_bundle("a" * 40))
        self.run = types.SimpleNamespace(events=[], state=lambda proj: {"S1": {"attempt": 2}}
                                         if proj is ControlProjection.STORY_STATE else None)
        self.folder = self.tmp / V.ARTIFACT_DIR

    def reviewer(self, policy="fix-loop", secrets=(), route=None, **review):
        return ad.Reviewer(self.run, self.project, self.tmp / "sessions", {"secrets": secrets}, 5,
                           review={"policy": policy, "min_severity": "low", "finder": "model", "ocr": None, "given": True,
                                   **review}, route=route)

    def review(self, rev, found, verdict=V.CONFIRMED, anchor=V.ANCHORED, session=None):
        """Reviewer.review with the finder, the probe and the anchor stubbed: what `found` is verified to be."""
        seen = []

        def verify(f, root, head):
            seen.append(json.loads(json.dumps(f)))
            return V.Verification(verdict, REASON, "probe.cli_invocation", "REFUTED" if verdict == V.CONFIRMED else None)
        a = V.Anchor(anchor, "clause R-9/3's approved outcome", ("BC-1",))
        s = session if session is not None else {"parsed": True, "log": "S1.reviewer.2.jsonl"}
        scope = types.SimpleNamespace(story_id="S1", root=str(self.tmp / "repo"))
        with mock.patch.object(rev, "_model", return_value=(found, s, None)), mock.patch.object(rev, "_verify", verify), \
                mock.patch.object(V, "anchor", return_value=a):
            result = rev.review(scope, ("C-ADD",))
        return result, s, seen

    def make_unwritable(self) -> None:
        self.folder.write_text("a file where the directory goes")


class ReviewerKeepsTheEvidence(_Reviewer):
    def test_a_blocking_finding_blocks_on_its_artifact_and_the_row_names_it(self):
        f = {"id": "F1", "blocking": True, "severity": "high", "summary": f"key {SECRET}",
             "reproducer": {"clause": "R-ADD/1", "subject": {"kind": "python_callable", "locator": "app.calc:add"},
                            "stimulus": {"args": [2, 2], "pad": "x" * 4000 + SECRET},
                            "observable": {"returns": 5, "within_s": 10}}}
        r, s, probed = self.review(self.reviewer(secrets=(SECRET,)), [f])
        (t,) = r.findings
        self.assertEqual((t.id, t.blocks, t.corroborated_by), ("F1", True, ("probe:probe.cli_invocation:REFUTED",)))
        d = json.loads(t.detail)
        self.assertLessEqual(len(t.detail), V.SUMMARY_MAX)
        self.assertEqual((d["verification"], d["anchor"], d["severity"], d["clause"]), (V.CONFIRMED, V.ANCHORED, "high", "R-ADD/1"))
        art = d["artifact"]
        self.assertEqual(art["path"], "review-findings/S1.2.0.json")
        data = (self.tmp / art["path"]).read_bytes()
        self.assertEqual((art["sha256"], art["bytes"]), (hashlib.sha256(data).hexdigest(), len(data)))
        doc = json.loads(data)
        self.assertEqual((doc["story_id"], doc["attempt"], doc["index"], doc["revision"], doc["session"], doc["redacted"]),
                         ("S1", 2, 0, e2e.git(self.tmp / "repo", "rev-parse", "HEAD"), "S1.reviewer.2.jsonl", 2))
        self.assertEqual(doc["finding"]["id"], "F1")
        self.assertEqual(doc["finding"]["verification"]["status"], V.CONFIRMED)
        self.assertEqual(doc["finding"]["anchor"]["status"], V.ANCHORED)
        self.assertEqual(len(doc["finding"]["reproducer"]["stimulus"]["pad"]), 4000 + len(V.REDACTED))
        # nowhere the secret; and the probe ran the reproducer as the finder wrote it
        for where in (t.detail, data.decode(), json.dumps(s["findings"]), r.detail):
            self.assertNotIn(SECRET, where)
        self.assertEqual(probed[0]["reproducer"]["stimulus"]["pad"], "x" * 4000 + SECRET)
        self.assertEqual(s["findings"][0]["verification"]["status"], V.CONFIRMED)    # RUN.json keeps what it kept
        self.assertEqual(s["findings"][0]["summary"], f"key {V.REDACTED}")

    def test_the_finders_own_token_is_a_secret_of_the_run_too(self):
        f = finding(stimulus={"args": [TOKEN]})
        r, s, _ = self.review(self.reviewer(route={"url": "u", "token": TOKEN, "model": "m"}), [f])
        data = (self.tmp / json.loads(r.findings[0].detail)["artifact"]["path"]).read_bytes()
        for where in (r.findings[0].detail, data.decode(), json.dumps(s["findings"])):
            self.assertNotIn(TOKEN, where)
        self.assertEqual(json.loads(data)["redacted"], 1)

    def test_the_id_that_names_the_gate_row_carries_no_secret_either(self):
        r, s, _ = self.review(self.reviewer(secrets=(SECRET,)), [finding(id=f"id-{SECRET}"), finding(id="plain")])
        self.assertEqual([t.id for t in r.findings], [f"id-{V.REDACTED}", "plain"])
        self.assertEqual([f["id"] for f in s["findings"]], [f"id-{V.REDACTED}", "plain"])

    def test_two_findings_of_one_review_have_two_files_in_the_order_the_finder_gave_them(self):
        found = [finding(id="same"), finding(id="same", summary="the second")]
        r, _, _ = self.review(self.reviewer(), found)
        paths = [json.loads(t.detail)["artifact"]["path"] for t in r.findings]
        self.assertEqual(paths, ["review-findings/S1.2.0.json", "review-findings/S1.2.1.json"])
        self.assertEqual([json.loads((self.tmp / p).read_bytes())["finding"]["summary"] for p in paths],
                         ["snapshot of a missing file must exit 3", "the second"])

    def test_a_finding_that_would_block_and_cannot_be_kept_refuses_the_review(self):
        """A confirmed, anchored finding whose reproducer cannot be preserved is not grounds to block on its cut
        statement and is not dropped: the review is refused, ENVIRONMENT's CAPABILITY_UNRUNNABLE, saying which finding
        and why."""
        self.make_unwritable()
        f = finding(id="F-lost", stimulus={"argv": ["x" * 5000]})
        with self.assertRaises(ad.CapabilityUnrunnable) as c:
            self.review(self.reviewer(), [f])
        msg = str(c.exception)
        self.assertIn("F-lost", msg)
        self.assertRegex(msg, r"FileExistsError|NotADirectoryError")
        self.assertIn("could not be preserved", msg)
        self.assertIn("every finding discarded", msg)
        self.assertNotIn("x" * 50, msg)

    def test_the_finding_id_in_that_refusal_is_redacted(self):
        self.make_unwritable()
        with self.assertRaises(ad.CapabilityUnrunnable) as c:
            self.review(self.reviewer(secrets=(SECRET,)), [finding(id=f"id-{SECRET}")])
        self.assertNotIn(SECRET, str(c.exception))
        self.assertIn(f"id-{V.REDACTED}", str(c.exception))

    def test_a_finding_that_would_not_block_is_reported_with_why_it_has_no_artifact(self):
        self.make_unwritable()
        for verdict, anchor in ((V.CONFIRMED, V.UNANCHORED), (V.NOT_REPRODUCED, V.ANCHORED), (V.UNVERIFIABLE, V.ANCHORED)):
            with self.subTest(verdict=verdict, anchor=anchor):
                r, s, _ = self.review(self.reviewer(), [finding(stimulus={"argv": ["x" * 5000]})], verdict, anchor)
                (t,) = r.findings
                self.assertFalse(t.blocks)
                d = json.loads(t.detail)
                self.assertIsNone(d["artifact"])
                self.assertRegex(d["artifact_why"], r"FileExistsError|NotADirectoryError")
                self.assertEqual(d["verification"], verdict)
                self.assertIn("elided", d)      # the cut is marked, and there is no artifact to refer to
                self.assertLessEqual(len(t.detail), V.SUMMARY_MAX)

    def test_under_advisory_nothing_blocks_so_nothing_is_refused(self):
        self.make_unwritable()
        r, _, _ = self.review(self.reviewer(policy="advisory"), [finding()])
        self.assertEqual([t.blocks for t in r.findings], [False])
        self.assertIsNone(json.loads(r.findings[0].detail)["artifact"])

    def test_a_cut_statement_is_never_what_blocks(self):
        """With the artifact the finding blocks and its statement names the file; with the same finding and no way to
        keep it, no blocking finding comes back — whatever the cut statement would have said."""
        f = finding(stimulus={"argv": ["x" * 5000]})
        kept, _, _ = self.review(self.reviewer(), [f])
        self.assertTrue(kept.findings[0].blocks)
        self.assertIn("artifact", json.loads(kept.findings[0].detail))
        self.folder.rename(self.tmp / "kept")      # a run directory of its own: the artifact cannot be made again
        self.make_unwritable()
        with self.assertRaises(ad.CapabilityUnrunnable):
            self.review(self.reviewer(), [f])


if __name__ == "__main__":
    unittest.main()
