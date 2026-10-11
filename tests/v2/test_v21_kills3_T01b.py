"""V2.1 (mutation survivors, batch T01b): what `aisef bundle continue` (`bundle_cli.continue_from`) requires of the run
it continues from, and what it tells the operator and the next stage when it refuses or continues.

One real run is made for the whole file (the fake client of test_app_run: S1 commits, S2 does not). Every other run
directory is a `moved` directory: symlinks to that run's own directories plus the record, the journal or the clone an
operator can meet — a torn RUN.json, no record at all, another kernel's digest, a journal that committed nothing, a
clone that lacks the journal's last commit, commits on main nothing identifies. Offline: nothing here starts a client.

Pins aisef2/app/bundle_cli.py::continue_from [48, 92, 111, 112, 119, 122, 124, 135, 141, 146, 158, 159, 164, 167, 168,
172, 178]."""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import io
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
from aisef2.app import bundle, bundle_cli, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from tests.v2.test_app_run import ADD, FAKE_CLIENT, SETTINGS, TEST, client_config, git, make_repo, provider  # noqa: E402
from tests.v2.test_v21_continue_usage import AUTHORING  # noqa: E402

RECORD, STARTED = "RUN.json", R.STARTED
JOURNAL = pathlib.Path("run") / "journals" / "aisef-run.jsonl"

#: the one run of the file, built by setUpModule: `tmp`, `doc` (sealed and approved), `first` (the run directory), `s1`
#: (the revision the journal's story/commit of S1 names), `record` and `started` (the bytes of its two records)
FX = types.SimpleNamespace()


def setUpModule() -> None:
    if os.name != "posix":
        raise unittest.SkipTest("the fake client is a script started by its shebang")
    holder = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(holder.cleanup)
    tmp = pathlib.Path(holder.name).resolve()
    make_repo(tmp / "source")
    doc, _ = bundle_cli.seal(AUTHORING, repo=tmp / "source")
    for c in ("BC-ADD", "BC-MUL"):
        doc = bundle_cli.approve(doc, c, "human:t", 1.0)
    client = tmp / "client" / "opencode"
    client.parent.mkdir()
    client.write_text(f"#!{sys.executable}\nADD = {ADD!r}\nTEST = {TEST!r}\n" + FAKE_CLIENT, encoding="utf-8")
    client.chmod(0o755)
    (client.parent / "mode").write_text("write", encoding="utf-8")
    with mock.patch.object(ad, "scanner", lambda: ad.NoScanner()), mock.patch.dict(os.environ, client_config(tmp)):
        run = R.execute(bundle.load(doc), settings.load(SETTINGS), tmp / "source", tmp / "first", transport=provider(),
                        client_exe=str(client), cals=R.calibrations())
    assert run["story_outcomes"]["S1"] == ["COMMIT"], run["story_outcomes"]
    first = tmp / "first"
    events = format3.reconstruct((first / JOURNAL).read_text(encoding="utf-8")).events
    FX.tmp, FX.doc, FX.first = tmp, doc, first
    FX.s1 = next(e.data["revision"] for e in events if e.type == "story/commit")
    FX.record = (first / RECORD).read_bytes()
    FX.started = (first / STARTED).read_bytes()


class Case(unittest.TestCase):
    """Helpers; no tests of its own."""

    def scratch(self) -> pathlib.Path:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        return pathlib.Path(t.name).resolve()

    def moved(self, *, record: bytes | str | None = None, started: bytes | None = None,
              repo: pathlib.Path | None = None, journal: bytes | None = None) -> pathlib.Path:
        """A run directory of the shape `continue_from` reads: the real run's directories by symlink (its `repo` and
        its journal replaced when given), `record` as RUN.json and `started` as RUN.started.json (each only when
        given), and no EVIDENCE.json — the run was killed before it wrote one."""
        d = self.scratch() / "moved"
        d.mkdir()
        for entry in FX.first.iterdir():
            if entry.name not in (RECORD, STARTED, "EVIDENCE.json", "repo") and not (journal is not None and entry.name == "run"):
                os.symlink(entry, d / entry.name)
        os.symlink(repo or FX.first / "repo", d / "repo")
        if journal is not None:
            (d / JOURNAL).parent.mkdir(parents=True)
            (d / JOURNAL).write_bytes(journal)
        for name, data in ((RECORD, record), (STARTED, started)):
            if data is not None:
                (d / name).write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return d

    def refusal(self, run_dir: pathlib.Path, **kw) -> str:
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.continue_from(FX.doc, run_dir, **kw)
        return str(c.exception)

    def cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bundle_cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def clone_with_strays(self, n: int = 2) -> pathlib.Path:
        """A clone of the run's repository whose main holds `n` commits on top of the journal's last commit that no
        journaled operation accounts for (someone else's)."""
        clone = self.scratch() / "clone"
        git(FX.tmp, "clone", "-q", "--branch", "main", str(FX.first / "repo"), str(clone))
        for i in range(n):
            (clone / f"stray-{i}.txt").write_text(f"not the kernel's {i}\n", encoding="utf-8")
            git(clone, "add", "-A")
            git(clone, "commit", "-q", "-m", f"someone else {i}")
        return clone


class RecordOfTheRun(Case):
    """Which record of the predecessor is trusted. RUN.json is the record; a run killed before it wrote one still names
    its identities in RUN.started.json, and that is what a continuation falls back to — for a record that is not
    there AND for one that cannot be read (a torn write, a file that is not UTF-8). With neither, the run is refused
    by name as a typed refusal, so `aisef bundle continue` ends with status 2, never a traceback.

    Pins aisef2/app/bundle_cli.py::continue_from [48, 111, 112, 164]."""

    TORN = {"truncated JSON": b'{"bundle_digest": "', "empty": b"", "not UTF-8": b"\xff\xfe\x00"}

    def test_a_record_that_cannot_be_read_falls_back_to_the_started_record(self):
        _, whole = bundle_cli.continue_from(FX.doc, FX.first)
        self.assertTrue(whole["recorded"])
        for label, torn in self.TORN.items():
            with self.subTest(label):
                _, report = bundle_cli.continue_from(FX.doc, self.moved(record=torn, started=FX.started))
                self.assertIs(report["recorded"], False)
                self.assertEqual((report["carried"], report["baseline"], report["remaining"]),
                                 (whole["carried"], whole["baseline"], whole["remaining"]))
                self.assertEqual(report["baseline"], FX.s1)

    def test_the_command_continues_from_the_started_record_when_the_record_is_torn(self):
        bundle_file = self.scratch() / "bundle.json"
        bundle_file.write_text(json.dumps(FX.doc), encoding="utf-8")
        out = bundle_file.with_name("next.json")
        code, stdout, stderr = self.cli("continue", str(bundle_file), "--from-run",
                                        str(self.moved(record=self.TORN["truncated JSON"], started=FX.started)),
                                        "--out", str(out))
        self.assertEqual((code, stderr), (0, ""))
        self.assertIs(json.loads(stdout)["recorded"], False)
        self.assertTrue(out.is_file())

    def test_a_run_with_no_readable_record_is_refused_by_name_and_as_a_typed_refusal(self):
        cases = {"neither record": {}, "the started record torn": {"started": self.TORN["truncated JSON"]},
                 "the started record not UTF-8": {"started": self.TORN["not UTF-8"]},
                 "both records torn": {"record": self.TORN["truncated JSON"], "started": self.TORN["empty"]},
                 "the record torn and no started record": {"record": self.TORN["truncated JSON"]}}
        for label, files in cases.items():
            with self.subTest(label):
                moved = self.moved(**files)
                text = self.refusal(moved)
                self.assertIn(str(moved), text)
                self.assertIn("no run record", text)

    def test_the_command_refuses_a_directory_that_is_no_run_with_status_2(self):
        bundle_file = self.scratch() / "bundle.json"
        bundle_file.write_text(json.dumps(FX.doc), encoding="utf-8")
        for label, files in (("an empty directory", {}), ("a torn started record", {"started": b"{"})):
            with self.subTest(label):
                moved = self.moved(**files)
                out = bundle_file.with_name(f"next-{len(label)}.json")
                code, stdout, stderr = self.cli("continue", str(bundle_file), "--from-run", str(moved), "--out", str(out))
                self.assertEqual((code, stdout), (2, ""))
                self.assertTrue(stderr.startswith("refused: "), stderr)
                self.assertIn("no run record", stderr)
                self.assertFalse(out.exists())


class AnotherKernel(Case):
    """A run of another kernel is a new project, not a continuation; the refusal names the run and the kernel digest it
    recorded (the first 12 characters), which is how an operator finds the release that ran it.

    Pins aisef2/app/bundle_cli.py::continue_from [172]."""

    def test_the_refusal_names_the_run_and_the_kernel_it_ran(self):
        recorded = "c0ffee1234ab" + "9" * 28
        record = dict(json.loads(FX.record), kernel_digest=recorded)
        moved = self.moved(record=json.dumps(record))
        text = self.refusal(moved)
        self.assertIn("another kernel", text)
        self.assertIn(str(moved), text)
        self.assertIn(recorded[:12], text)
        self.assertNotIn(R.kernel_digest()[:12], text)


class NothingCommitted(Case):
    """A run whose journal holds no story/commit has nothing to continue from: refused, naming the run and the reason
    (the journal's own account: it committed no story).

    Pins aisef2/app/bundle_cli.py::continue_from [119]."""

    def test_a_run_that_committed_no_story_is_refused_by_name(self):
        lines = (FX.first / JOURNAL).read_bytes().split(b"\n")
        first_commit = next(i for i, ln in enumerate(lines) if ln and json.loads(ln)["event"]["type"] == "story/commit")
        before = b"\n".join(lines[:first_commit]) + b"\n"
        self.assertEqual(sum(1 for e in format3.reconstruct(before.decode("utf-8")).events if e.type == "story/commit"), 0)
        moved = self.moved(record=FX.record, journal=before)
        text = self.refusal(moved)
        self.assertIn(str(moved), text)
        self.assertIn("committed no story", text)


class BaselineOfTheClone(Case):
    """The continuation's baseline is the journal's last commit and the run's own clone must hold it — as a COMMIT: an
    object that exists but is no commit (a tree a damaged or forged journal names) is no baseline. The refusal names
    the clone and the revision.

    Pins aisef2/app/bundle_cli.py::continue_from [122, 141]."""

    def test_a_clone_that_lacks_the_journals_last_commit_is_refused(self):
        moved = self.moved(record=FX.record, repo=FX.tmp / "source")      # the source repository: S1's commit is not in it
        text = self.refusal(moved)
        self.assertIn(str(moved / "repo"), text)
        self.assertIn(FX.s1[:12], text)
        self.assertIn("last commit", text)

    def test_an_object_that_is_no_commit_is_not_a_baseline(self):
        tree = git(FX.first / "repo", "rev-parse", f"{FX.s1}^{{tree}}")
        self.assertNotEqual(tree, FX.s1)
        real = format3.reconstruct

        def names_the_tree(text):
            journal = real(text)
            events = [dataclasses.replace(e, data={**e.data, "revision": tree}) if e.type == "story/commit" else e
                      for e in journal.events]
            return types.SimpleNamespace(events=events, torn_tail=journal.torn_tail)

        moved = self.moved(record=FX.record)
        with mock.patch.object(format3, "reconstruct", names_the_tree):
            # leave_out_unidentified: no later guard of the function answers before the one under test
            text = self.refusal(moved, leave_out_unidentified=True)
        self.assertIn(str(moved / "repo"), text)
        self.assertIn(tree[:12], text)
        self.assertIn("last commit", text)


class CommitsNothingIdentifies(Case):
    """Commits on main that no journaled operation of the run accounts for are never left out silently: the refusal
    names each one (the first 12 characters of its commit and the reason the report itself gives for it) and the flag
    that continues without them; with the flag, the report carries the same items and its `in_flight` says that effects
    are left out, how many, at which baseline, and in which field they are identified.

    Pins aisef2/app/bundle_cli.py::continue_from [124, 135, 167, 168]."""

    def setUp(self) -> None:
        self.moved_dir = self.moved(record=FX.record, repo=self.clone_with_strays(2))

    def test_the_refusal_names_each_commit_its_reason_and_the_flag_that_leaves_them_out(self):
        text = self.refusal(self.moved_dir)
        _, report = bundle_cli.continue_from(FX.doc, self.moved_dir, leave_out_unidentified=True)
        unidentified = [i for i in report["unconfirmed"] if not i["identified"]]
        self.assertEqual(len(unidentified), 2)
        self.assertEqual(len({i["commit"] for i in unidentified}), 2)
        for item in unidentified:
            self.assertIn(item["commit"][:12], text)
            self.assertIn(item["why"], text)
        self.assertIn("--leave-out-unidentified", text)

    def test_the_report_says_where_the_effects_left_out_are_listed(self):
        _, report = bundle_cli.continue_from(FX.doc, self.moved_dir, leave_out_unidentified=True)
        self.assertTrue(report["left_out_unidentified"])
        self.assertEqual(len(report["unconfirmed"]), 2)
        text = report["in_flight"]
        self.assertIn("unconfirmed", text)                    # the key that lists them ...
        self.assertTrue(report["unconfirmed"])                # ... exists in the report and is not empty
        self.assertTrue(re.search(rf"\b{len(report['unconfirmed'])}\b", text), text)
        self.assertIn(report["baseline"][:12], text)


class CarriedStory(Case):
    """What the continuation says about the stories it folded into CARRIED: their tests, as one sorted list (the
    bundle's bytes, and so its digest, do not depend on a set's iteration order, which differs between processes), and
    for each carried obligation its provenance — the committing story, the run (the predecessor's evidence anchor) and
    the criterion — as separable words.

    Pins aisef2/app/bundle_cli.py::continue_from [92, 158, 159]."""

    def test_the_carried_story_lists_the_done_tests_sorted(self):
        names = [f"tests/test_{w}.py" for w in ("zulu", "yankee", "xray", "whiskey", "victor", "uniform", "tango",
                                                "sierra", "romeo", "quebec", "papa", "oscar")]
        self.assertNotEqual(names, sorted(names))
        authoring = copy.deepcopy(AUTHORING)
        authoring["stories"]["S1"]["tests"] = names
        doc, _ = bundle_cli.seal(authoring, repo=FX.tmp / "source")
        for c in ("BC-ADD", "BC-MUL"):
            doc = bundle_cli.approve(doc, c, "human:t", 1.0)
        record = dict(json.loads(FX.record), bundle_digest=bundle.load(doc).digest)   # the same run, this bundle
        out, report = bundle_cli.continue_from(doc, self.moved(record=json.dumps(record)))
        self.assertEqual(report["carried"], ["S1"])
        self.assertEqual(out["stories"][report["carried_as"]]["tests"], sorted(names))
        self.assertEqual(bundle.load(out).stories[report["carried_as"]]["tests"], sorted(names))

    def test_a_carried_obligation_names_its_story_its_run_and_its_criterion_as_separate_words(self):
        doc, report = bundle_cli.continue_from(FX.doc, FX.first)
        anchor = R.anchor_in(FX.first)
        self.assertEqual(report["evidence_anchor"], anchor)
        self.assertRegex(anchor, r"^[0-9a-f]{64}$")
        carried = [o for o in bundle.load(doc).plan.obligations if o.story_id == report["carried_as"]]
        self.assertEqual([o.criterion_id for o in carried], ["C-ADD"])
        for o in carried:
            words = re.findall(r"[\w-]+", o.ownership_rationale)
            for element in ("S1", o.criterion_id):
                self.assertIn(element, words, o.ownership_rationale)
            # the run: a word that is a prefix of its anchor, as long as the module's other identities (12 characters
            # and more) — how many of the 64 it shows is the writer's choice, and a fused word is not that word
            self.assertTrue(any(len(w) >= 12 and anchor.startswith(w) for w in words), o.ownership_rationale)


class PredecessorWithoutManifest(Case):
    """A run killed before it wrote its evidence manifest has no evidence anchor. The continuation says so where the
    anchor would be — in the bundle's description and in the rationale of each carried obligation — and does not leave
    that place empty, where 'no anchor' could not be told from 'anchor missing'.

    Pins aisef2/app/bundle_cli.py::continue_from [146, 178]."""

    def test_the_description_and_the_rationale_say_there_is_no_manifest(self):
        anchored_doc, _ = bundle_cli.continue_from(FX.doc, FX.first)
        doc, report = bundle_cli.continue_from(FX.doc, self.moved(started=FX.started))   # killed before its record
        self.assertIsNone(report["evidence_anchor"])
        self.assertIs(report["recorded"], False)
        self.assertTrue(doc["description"].startswith(FX.doc["description"]))
        # where the anchor would be, the description names what is missing (the manifest: the product's own word for it)
        self.assertRegex(doc["description"][len(FX.doc["description"]):], r"\bmanifest\b")
        # where the anchor is, there is a marker: as many tokens as with an anchor (a 64-hex word), never fewer
        self.assertGreaterEqual(len(doc["description"].split()), len(anchored_doc["description"].split()))

        def rationales(d):
            return [o.ownership_rationale for o in bundle.load(d).plan.obligations if o.story_id == report["carried_as"]]

        (without,), (anchored,) = rationales(doc), rationales(anchored_doc)
        # the slot holds a marker, not its wording: the literal is cut by the anchor's [:16] ('without a manife' —
        # defect-1 of batch T01b), so only that the slot is occupied is pinned here
        self.assertGreaterEqual(len(without.split()), len(anchored.split()), without)
        words = re.findall(r"[\w-]+", without)
        self.assertIn("S1", words)
        self.assertIn("C-ADD", words)
        self.assertIsNone(re.search(r"[0-9a-f]{16}", without), without)       # no anchor is claimed


if __name__ == "__main__":
    unittest.main()
