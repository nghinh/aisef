"""V2.1 (owner B-03 round 3, item 5) through `aisef run` with the MODEL finder (not Open Code Review): a finding that is
reproduced but not anchored does not block, is kept whole in its artifact with the secret of the run replaced, and the
run verifies.

The calc project, the model reviewer (a fake client that answers the review prompt with a scripted JSON): add(2, 2)
"must return 5" — reproduced (the candidate returns 4) but its clause's one approved contract (add(2, 3) == 5) shows no
constant outcome: UNANCHORED, triage. The reviewer's text carries the run's secret in its prose and in a field of its
own.

Pins aisef2/app/adapters.py::Reviewer.review, aisef2/app/review_verify.py::preserve"""

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
from tests.v2 import test_app_run as e2e  # noqa: E402
from tests.v2.test_app_run import SETTINGS, client_config, provider  # noqa: E402

SECRET = "s3cr3t-value-0123456789"


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class TheModelFinderKeepsAFindingThatDoesNotBlock(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._t = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._t.cleanup)
        cls.tmp = pathlib.Path(cls._t.name).resolve()
        cls.project = bundle.load(e2e.project_bundle(e2e.make_repo(cls.tmp / "source")))
        cls.client = cls.tmp / "client" / "opencode"
        cls.client.parent.mkdir()
        cls.client.write_text(f"#!{sys.executable}\nADD = {e2e.ADD!r}\nTEST = {e2e.TEST!r}\n" + e2e.FAKE_CLIENT)
        cls.client.chmod(0o755)
        (cls.client.parent / "mode").write_text("write")
        cls.finding = {"id": "add-misread", "blocking": True, "severity": "high",
                       "summary": f"add(2, 2) must return 5 (seen with {SECRET})",
                       "evidence": f"seen in a log: {SECRET}",
                       "reproducer": {"clause": "R-ADD/1.1", "subject": {"kind": "python_callable", "locator": "app.calc:add"},
                                      "stimulus": {"args": [2, 2]}, "observable": {"returns": 5, "within_s": 10}}}
        (cls.client.parent / "review.json").write_text(json.dumps({"findings": [cls.finding]}), encoding="utf-8")
        cfg = settings.load({**SETTINGS, "client_env": ["AISEF_TEST_SECRET"],
                             "review": {"policy": "fix-loop", "min_severity": "high"}})
        cls.out = cls.tmp / "out"
        env = {**client_config(cls.tmp), "AISEF_TEST_SECRET": SECRET}
        with mock.patch.dict(os.environ, env), mock.patch.object(ad, "scanner", lambda: ad.NoScanner()):
            cls.rec = R.execute(cls.project, cfg, cls.tmp / "source", cls.out, transport=provider(),
                                client_exe=str(cls.client), cals=e2e.calibrations())

    def rows(self):
        events = format3.reconstruct((self.out / "run" / "journals" / "aisef-run.jsonl").read_text(encoding="utf-8")).events
        return [e.data for e in events if e.type == "gate/check" and e.data["check"] == "S1:review:add-misread"]

    def test_it_does_not_block_and_the_story_commits(self):
        self.assertEqual((self.rec["story_outcomes"], self.rec["delivery_verdict"]), ({"S1": ["COMMIT"]}, "PASS"))
        (row,) = self.rows()
        self.assertTrue(row["passed"])

    def test_its_statement_names_an_artifact_holding_the_whole_finding_with_the_secret_replaced(self):
        (row,) = self.rows()
        d = json.loads(row["detail"].split(" — ", 1)[1])
        self.assertEqual((d["verification"], d["anchor"]), (V.CONFIRMED, V.UNANCHORED))
        ref = d["artifact"]
        data = (self.out / ref["path"]).read_bytes()
        self.assertEqual((ref["path"], ref["sha256"]), ("review-findings/S1.1.0.json", hashlib.sha256(data).hexdigest()))
        doc = json.loads(data)
        self.assertEqual(doc["finding"]["id"], "add-misread")
        self.assertEqual(doc["finding"]["reproducer"]["stimulus"], {"args": [2, 2]})
        self.assertEqual(doc["finding"]["evidence"], f"seen in a log: {V.REDACTED}")
        self.assertEqual(doc["finding"]["summary"], f"add(2, 2) must return 5 (seen with {V.REDACTED})")
        self.assertEqual(doc["finding"]["verification"]["status"], V.CONFIRMED)
        self.assertEqual(doc["session"], "S1.reviewer.1.jsonl")
        # the model's text was read from a stream that was redacted on its bytes: what the probe ran is what is kept
        self.assertEqual(doc["redacted"], 0)

    def test_the_secret_is_in_none_of_the_run_s_files_and_the_run_verifies(self):
        for p in (self.out / "RUN.json", self.out / "EVIDENCE.json", *(self.out / "run" / "journals").glob("*.jsonl"),
                  *(self.out / "sessions").glob("*.jsonl"), *(self.out / V.ARTIFACT_DIR).glob("*.json")):
            with self.subTest(file=p.name):
                self.assertNotIn(SECRET, p.read_text(encoding="utf-8"))
        v = verify(self.project, self.out)
        self.assertEqual((v["verdict"], v["problems"]), ("VERIFIED", []))
        manifest = json.loads((self.out / "EVIDENCE.json").read_text(encoding="utf-8"))
        self.assertIn("review-findings/S1.1.0.json", manifest["files"])


if __name__ == "__main__":
    unittest.main()
