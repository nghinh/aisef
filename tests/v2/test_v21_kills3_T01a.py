"""Mutation survivors of `aisef2/app/bundle_cli.py::continue_from` (campaign 2, batch T01a): what the operator, and a
script of theirs, takes from `aisef bundle continue` — the report it prints as JSON and the continuation bundle it
writes.

One real run is made once (the fake developer of test_app_run delivers the one-story calc bundle). `continue_from`
never writes into the run it continues, so every test reads the same finished run, or a twin of it (its record,
manifest and start record copied, its journal and clone linked) when it needs a run in another state: killed before
its record, claimed by an earlier continuation, or of another bundle. Offline: the fake client and provider of
test_app_run; nothing here starts a provider request."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import pathlib
import re
import shlex
import shutil
import signal
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, bundle_cli, cli, lineage, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from tests.v2.test_app_run import (ADD, FAKE_CLIENT, SETTINGS, TEST, client_config, make_repo, project_bundle,  # noqa: E402
                                   provider)
from tests.v2.test_v21_continue_usage import AUTHORING  # noqa: E402


def _seal_and_approve(authoring: dict, repo: pathlib.Path) -> dict:
    doc, _ = bundle_cli.seal(authoring, repo=repo)
    for contract in ("BC-ADD", "BC-MUL"):
        doc = bundle_cli.approve(doc, contract, "human:t", 1.0)
    return doc


class World:
    """The one-story calc bundle `doc` (S1: add), its finished run `first` and the means to make twins of that run."""

    def __init__(self, tmp: pathlib.Path) -> None:
        self.tmp = tmp
        self.source = tmp / "source"
        self.doc = project_bundle(make_repo(self.source))
        client = tmp / "client" / "opencode"
        client.parent.mkdir()
        client.write_text(f"#!{sys.executable}\nADD = {ADD!r}\nTEST = {TEST!r}\n" + FAKE_CLIENT)
        client.chmod(0o755)
        (client.parent / "mode").write_text("write")
        self.first = tmp / "first"
        with mock.patch.object(ad, "scanner", lambda: ad.NoScanner()), mock.patch.dict(os.environ, client_config(tmp)):
            rec = R.execute(bundle.load(self.doc), settings.load(SETTINGS), self.source, self.first,
                            client_exe=str(client), cals=R.calibrations(), transport=provider())
        if rec["story_outcomes"] != {"S1": ["COMMIT"]}:
            raise RuntimeError(f"the fixture run is not the one these tests need: {rec['story_outcomes']}")
        events = format3.reconstruct((self.first / "run" / "journals" / "aisef-run.jsonl").read_text(encoding="utf-8")).events
        #: the revision the journal's last story/commit names: the continuation's baseline
        self.baseline = [e.data["revision"] for e in events if e.type == "story/commit"][-1]
        self.anchor = R.anchor_in(self.first)
        if not self.anchor:
            raise RuntimeError("the finished fixture run has no evidence manifest")

    def twin(self, name: str, *, record: bool = True, manifest: bool = True, digest: str | None = None) -> pathlib.Path:
        """A run directory of its own that is `first` seen as: `record` — RUN.json present (with `digest` as its
        bundle_digest when given); `manifest` — EVIDENCE.json present; always the start record RUN.started.json, the
        journal and the clone (linked). Without both a twin is a run killed before it wrote its record."""
        d = self.tmp / name
        d.mkdir()
        for link in ("run", "repo"):
            os.symlink(self.first / link, d / link)
        shutil.copyfile(self.first / R.STARTED, d / R.STARTED)
        if manifest:
            shutil.copyfile(self.first / R.MANIFEST, d / R.MANIFEST)
        if record:
            rec = json.loads((self.first / "RUN.json").read_text(encoding="utf-8"))
            (d / "RUN.json").write_text(json.dumps(dict(rec, bundle_digest=digest or rec["bundle_digest"])), encoding="utf-8")
        return d


W: World


def setUpModule() -> None:
    global W
    if os.name != "posix":
        raise unittest.SkipTest("the fake client is a script started by its shebang")
    tmp = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(tmp.cleanup)
    W = World(pathlib.Path(tmp.name).resolve())


@contextlib.contextmanager
def _within(seconds: int):
    """A call that must return: a hang becomes a failure here, not a timeout of whoever runs the file."""
    def fire(signum, frame):
        raise AssertionError(f"did not return within {seconds} s")
    old = signal.signal(signal.SIGALRM, fire)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


class ReportOfAFinishedRun(unittest.TestCase):
    """The report of a run that wrote its record and its manifest names that run, hands over the anchor an operator
    gives `aisef run --verify --expect-anchor`, and says the record was read.
    Pins aisef2/app/bundle_cli.py::continue_from [33, 68] (run), [34, 69] (evidence_anchor), [12, 35, 70] (recorded)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.doc, cls.report = bundle_cli.continue_from(W.doc, W.first)

    def test_the_run_is_the_directory_the_continuation_was_asked_of(self):
        self.assertEqual(self.report["run"], str(W.first))

    def test_the_evidence_anchor_is_the_one_its_manifest_gives(self):
        self.assertEqual(self.report["evidence_anchor"], W.anchor)
        self.assertRegex(self.report["evidence_anchor"], r"\A[0-9a-f]{64}\Z")     # what --expect-anchor accepts (cli.run)

    def test_the_record_was_read(self):
        self.assertIs(self.report["recorded"], True)


class ReportOfARunKilledBeforeItsRecord(unittest.TestCase):
    """A run with no RUN.json and no manifest is continued from its start record: the report says its record was
    not read, and has no anchor to hand over (None, not a made-up value).
    Pins aisef2/app/bundle_cli.py::continue_from [139] (recorded False in this case); the absent anchor is None beside
    [34, 69]."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.killed = W.twin("killed", record=False, manifest=False)
        cls.doc, cls.report = bundle_cli.continue_from(W.doc, cls.killed)

    def test_it_was_continued_from_the_start_record_alone(self):
        self.assertFalse((self.killed / "RUN.json").exists())
        self.assertEqual((self.report["carried"], self.report["baseline"]), (["S1"], W.baseline))

    def test_the_record_was_not_read(self):
        self.assertIs(self.report["recorded"], False)

    def test_there_is_no_anchor(self):
        self.assertIsNone(self.report["evidence_anchor"])
        self.assertEqual(self.report["run"], str(self.killed))


class DescriptionOfTheContinuation(unittest.TestCase):
    """The continuation bundle's description keeps the original's and names the predecessor's anchor as a word of its
    own — the operator copies it from there to `--expect-anchor`; a run without a manifest is said to have none, never
    printed as `None` and never given an anchor it does not have.
    Pins aisef2/app/bundle_cli.py::continue_from [29] (description changed), [95] (anchor separable), [130] (anchor
    when there is one)."""

    def test_a_finished_run_names_its_anchor(self):
        doc, _ = bundle_cli.continue_from(W.doc, W.first)
        self.assertIn(W.doc["description"], doc["description"])
        # a token of its own: set off from the text before it by whitespace (surrounding punctuation is not the contract)
        self.assertIn(W.anchor, [w.strip("()[]{}<>\"'`.,;:") for w in doc["description"].split()], doc["description"])

    def test_a_run_without_a_manifest_names_no_anchor_and_not_none(self):
        run = W.twin("no-manifest", manifest=False)
        doc, _ = bundle_cli.continue_from(W.doc, run)
        self.assertIn(W.doc["description"], doc["description"])
        self.assertNotIn("None", doc["description"])
        self.assertIsNone(re.search(r"[0-9a-f]{64}", doc["description"]))


class CarriedStory(unittest.TestCase):
    """The committed stories' criteria are carried by one synthetic story the report names (`carried_as`): it is a
    story of the continuation bundle, the plan holds the carried criterion on it as VERIFY, and it is never a story
    the project already has — a project's own CARRIED keeps its criteria and its role.
    Pins aisef2/app/bundle_cli.py::continue_from [31, 66] (carried_as), [57] (a name taken is not reused: the mutant
    never leaves the loop). The documented id is CARRIED (USAGE-2.1 §5); the id under a collision is not promised, so
    it is read from the report and asserted to be nobody else's."""

    def test_the_report_names_the_story_that_carries_the_committed_criteria(self):
        doc, report = bundle_cli.continue_from(W.doc, W.first)
        carried = report["carried_as"]
        self.assertEqual(carried, "CARRIED")
        self.assertIn(carried, doc["stories"])
        plan = bundle.load(doc).plan
        self.assertEqual({o.criterion_id: (o.story_id, o.role.value) for o in plan.obligations},
                         {"C-ADD": (carried, "VERIFY")})

    def test_a_story_already_named_carried_is_not_collided_with(self):
        authoring = copy.deepcopy(AUTHORING)
        authoring["stories"]["CARRIED"] = authoring["stories"].pop("S2")       # S2 (mul), not done, is now CARRIED
        doc = _seal_and_approve(authoring, W.source)
        run = W.twin("collision", digest=bundle.load(doc).digest)
        with _within(20):
            out, report = bundle_cli.continue_from(doc, run)
        carried = report["carried_as"]
        self.assertNotIn(carried, bundle.load(doc).stories)     # not S1, not the project's own CARRIED (the spelling is free)
        self.assertEqual((report["carried"], report["remaining"]), (["S1"], ["CARRIED"]))
        self.assertEqual(out["stories"], {carried: {"depends_on": [], "tests": ["tests/test_add.py"]},
                                          "CARRIED": {"depends_on": [carried], "tests": ["tests/test_mul.py"]}})
        plan = bundle.load(out).plan
        self.assertEqual({o.criterion_id: (o.story_id, o.role.value) for o in plan.obligations},
                         {"C-ADD": (carried, "VERIFY"), "C-MUL": ("CARRIED", "INTRODUCE")})


class EarlierClaimOnThePredecessor(unittest.TestCase):
    """`already_continued_by` tells the operator that an earlier continuation claimed this run and never began: None
    when no claim names it, else the run the newest claim names and its state (UNBEGUN: no record and no journal;
    ENDED_UNBEGUN: a record — a refusal — and no journal). A child that began is refused instead (not here).
    Pins aisef2/app/bundle_cli.py::continue_from [36, 71, 80] (the key and its condition), [96, 131] (run), [97, 132]
    (state)."""

    def report_of(self, run: pathlib.Path) -> dict:
        return bundle_cli.continue_from(W.doc, run)[1]

    def test_a_run_nobody_claimed(self):
        self.assertIsNone(self.report_of(W.first)["already_continued_by"])
        self.assertIsNone(self.report_of(W.twin("unclaimed"))["already_continued_by"])

    def test_a_claim_whose_child_left_nothing(self):
        run, dead = W.twin("claimed-dead"), W.tmp / "dead"
        lineage.claim(run, dead, 1.0)
        self.assertEqual(self.report_of(run)["already_continued_by"], {"run": str(dead), "state": "UNBEGUN"})

    def test_the_newest_claim_names_a_child_that_ended_without_beginning(self):
        run, refused_once, refused = W.twin("claimed-twice"), W.tmp / "refused-1", W.tmp / "refused-2"
        for child in (refused_once, refused):          # a refusal after the claim: a record, no journal
            child.mkdir()
            (child / "RUN.json").write_text(json.dumps({"failure": {"type": "RunRefused", "stage": "claim"}}), encoding="utf-8")
            lineage.claim(run, child, 1.0)             # the earlier child ended: its claim is superseded by evidence
        self.assertEqual([n for n, _ in lineage.claims(run)], [1, 2])
        self.assertEqual(self.report_of(run)["already_continued_by"], {"run": str(refused), "state": "ENDED_UNBEGUN"})


class NextCommand(unittest.TestCase):
    """`next` is the command the operator runs: an `aisef run` that continues this run in its own clone, with the
    bundle, the settings and the new run directory left for them to fill.
    Pins aisef2/app/bundle_cli.py::continue_from [44, 79] (the key), [102] (aisef run --project --repo), [103]
    (--parent), [104] (--settings --out)."""

    def test_it_parses_as_an_aisef_run_of_the_continuation(self):
        if re.search(r"\s", str(W.first)):
            self.skipTest("`next` does not quote the run directory (defect-1): a path with whitespace is not a command line")
        _, report = bundle_cli.continue_from(W.doc, W.first)
        words = shlex.split(re.sub(r"<[^<>]*>", "BUNDLE.json", report["next"]))      # the operator's bundle: one path
        self.assertEqual(words[:2], ["aisef", "run"])
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            try:
                a = cli._parser().parse_args(words[2:])
            except SystemExit:
                self.fail(f"not an aisef run command line: {report['next']!r}: {stderr.getvalue()}")
        self.assertEqual((a.project, a.parent, a.repo), (pathlib.Path("BUNDLE.json"), W.first, W.first / "repo"))
        self.assertIsNotNone(a.settings)
        self.assertIsNotNone(a.out)
        self.assertFalse(a.check or a.verify)


class BaselineRequirementsDocument(unittest.TestCase):
    """The continuation's baseline must hold the bundle's requirements document: a bundle whose document is not the one
    at the journal's baseline is a new project, and `continue_from` refuses it before anything is claimed. The
    refusal names the document and the baseline and says it is not the bundle's.
    Pins aisef2/app/bundle_cli.py::continue_from [18] (present with another sha256), [125, 126] (the refusal)."""

    def refusal(self, name: str, doc: dict) -> str:
        run = W.twin(name, digest=bundle.load(doc).digest)         # the same run, as the run of this bundle
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.continue_from(doc, run)
        return str(c.exception)

    def assert_names_the_document_and_the_baseline(self, message: str) -> None:
        self.assertIn("requirements document", message)
        self.assertIn(W.baseline[:12], message)
        self.assertIn("not the bundle's", message)

    def test_a_document_there_with_another_sha256_is_refused(self):
        doc = copy.deepcopy(W.doc)
        doc["requirements_document"]["sha256"] = "1" * 64
        self.assert_names_the_document_and_the_baseline(self.refusal("another-sha", doc))

    def test_a_document_missing_at_the_baseline_is_refused(self):
        doc = copy.deepcopy(W.doc)
        doc["requirements_document"]["path"] = "docs/absent.md"
        self.assert_names_the_document_and_the_baseline(self.refusal("absent", doc))

    def test_the_bundles_own_document_is_continued(self):
        _, report = bundle_cli.continue_from(W.doc, W.first)
        self.assertEqual(report["baseline"], W.baseline)


if __name__ == "__main__":
    unittest.main()
