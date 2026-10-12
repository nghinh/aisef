"""V2.1 (owner B-03 round 3, item 5) through `aisef run`: "if there is no full artifact, a cut piece is not a reproducer
with grounds to block the story" — and a confirmed finding is not silently passed either.

* A confirmed, anchored finding whose artifact cannot be preserved (the write fails — SIMULATED here: the keeping
  function reports ENOSPC; the real failures of `preserve` are in test_v21_r3_detail_artifact.py) does not block on
  its cut statement and does not pass the story: the review is refused, CAPABILITY_UNRUNNABLE (owner ENVIRONMENT),
  with the finding and the reason in the journal, and the story is never committed on it. A run that kept no
  artifact has exactly the evidence manifest it always had.

Pins aisef2/app/adapters.py::Reviewer.review, aisef2/app/review_verify.py::preserve, aisef2/app/run.py::evidence_manifest"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, settings  # noqa: E402
from aisef2.app import review_verify as V  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import verify  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from tests.v2 import test_v21_review_chain as C  # noqa: E402
from tests.v2.test_app_run import SETTINGS, client_config, git, provider  # noqa: E402


@unittest.skipUnless(os.name == "posix", "the fake client and the fake finder are scripts started by their shebang")
class WithoutItsArtifactAFindingNeverBlocksAndTheStoryIsNeverCommittedOnIt(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._t = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._t.cleanup)
        cls.tmp = pathlib.Path(cls._t.name).resolve()
        src = cls.tmp / "source"
        src.mkdir()
        git(src, "init", "-q", "-b", "main")
        (src / "app").mkdir()
        (src / "app" / "__init__.py").write_text("")
        (src / "docs").mkdir()
        (src / "docs" / "requirements.md").write_text(C.REQUIREMENTS)
        git(src, "add", "-A")
        git(src, "commit", "-q", "-m", "baseline")
        cls.baseline = git(src, "rev-parse", "HEAD")
        cls.project = bundle.load(C.cli_bundle(cls.baseline))
        cls.bin = cls.tmp / "bin"
        cls.bin.mkdir()
        for name, body in (("opencode", C.FAKE_DEVELOPER), ("ocr", C.FAKE_OCR)):
            (cls.bin / name).write_text(f"#!{sys.executable}\n" + body)
            (cls.bin / name).chmod(0o755)
        ocr = cls.bin / "ocr"
        review = {"policy": "fix-loop", "min_severity": "high", "finder": "ocr",
                  "ocr": {"exe": str(ocr), "sha256": hashlib.sha256(ocr.read_bytes()).hexdigest(), "timeout_min": 1,
                          "max_tokens": 4000}}
        cfg = settings.load({**SETTINGS, "review": review})
        (cls.bin / "answers.json").write_text(json.dumps([C.answer(C.DEFECTIVE)]), encoding="utf-8")
        long = {**C.THREE_ARGS, "stimulus": {"argv": ["1", "2", "3"], "stdin": {"text": "x" * 4000}}}
        (cls.bin / "scenarios.json").write_text(json.dumps([{"reproducers": [long]}]), encoding="utf-8")
        cls.out = cls.tmp / "out"
        cls.keeping = mock.patch.object(V, "preserve", return_value="OSError: [Errno 28] No space left on device")
        with mock.patch.dict(os.environ, client_config(cls.tmp)), mock.patch.object(ad, "scanner", lambda: ad.NoScanner()), \
                cls.keeping as kept:
            cls.rec = R.execute(cls.project, cfg, src, cls.out, transport=provider(), client_exe=str(cls.bin / "opencode"),
                                cals=R.calibrations())
        cls.kept = kept
        cls.events = format3.reconstruct((cls.out / "run" / "journals" / "aisef-run.jsonl").read_text(encoding="utf-8")).events

    def test_the_story_is_not_committed_and_main_is_the_baseline(self):
        self.assertEqual((self.rec["story_outcomes"], self.rec["delivery_verdict"]), ({"S1": ["RETRY", "ROLLBACK"]}, "FAIL"))
        self.assertEqual(git(self.out / "repo", "rev-parse", "main"), self.baseline)
        self.assertEqual(self.kept.call_count, 2)       # one finding per review, two reviews

    def test_the_failure_is_the_environments_review_capability_not_a_review_finding(self):
        codes = [(e.data["code"], e.data["owner"]) for e in self.events if e.type == "failure/observed"]
        self.assertEqual(codes, [("CAPABILITY_UNRUNNABLE", "ENVIRONMENT")] * 2)

    def test_the_journal_says_which_finding_and_why(self):
        results = [e.data["detail"] for e in self.events if e.type == "provider/result" and "cannot run" in e.data["detail"]]
        self.assertEqual(len(results), 2)
        for text in results:
            self.assertIn("could not be preserved", text)
            self.assertIn("No space left on device", text)
            self.assertIn("ocr-", text)         # the finding's id
        self.assertEqual([e for e in self.events if e.type == "gate/check" and ":review:" in e.data["check"]], [])

    def test_no_cut_statement_was_journaled_for_a_block(self):
        self.assertNotIn("blocking, corroborated", "".join(e.data.get("detail", "") for e in self.events
                                                          if e.type == "gate/check"))

    def test_a_run_that_kept_no_artifact_has_the_manifest_it_always_had(self):
        manifest = json.loads((self.out / "EVIDENCE.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["format"], "aisef-v2-evidence/1")
        self.assertEqual(sorted(manifest["files"]), [
            "RUN.json", "RUN.started.json", "preflight/LEDGER.jsonl", "preflight/PREFLIGHT.json",
            "run/journals/aisef-run.jsonl", "sessions/S1.developer.1.jsonl", "sessions/S1.developer.2.jsonl",
            "sessions/S1.reviewer.1.jsonl", "sessions/S1.reviewer.2.jsonl"])
        self.assertEqual(manifest, R.evidence_manifest(self.out))
        self.assertEqual(verify(self.project, self.out)["verdict"], "VERIFIED")


if __name__ == "__main__":
    unittest.main()
