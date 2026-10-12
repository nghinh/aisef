"""V2.1 (owner B-03 round 3, item 5) through `aisef run`: a blocked finding whose reproducer is far longer than the
journaled statement and holds the run's secret.

One real run (a fake developer, a fake Open Code Review finder that answers with a scripted comment, the real probe,
the real journal, manifest and `--verify`): attempt 1's candidate violates a clause the approved contracts anchor, the
finder's reproducer is 4,000+ characters of stdin with the secret in it; attempt 2 fixes it. What is asserted is what a
reader of the run directory relies on:

* the blocked row's statement is valid JSON within the bound and still says which finding, which clause, that it was
  CONFIRMED and ANCHORED, why, what was cut and how much, and where the whole reproducer is;
* that file holds the whole reproducer (its tail included), secret-redacted, names the candidate the probe ran at, and
  is the file the row binds by sha256 and the manifest lists;
* no secret of the run is in the record, the journal, the manifest, the streams, the artifact, the statement or the
  retry prompt the developer was given;
* `--verify` accepts the run and refuses it when the artifact is altered, removed or unreferenced — with the manifest
  rewritten to match too (the journal row binds it), and with no manifest at all.

The review work files the finder itself writes (`review/<story>.<attempt>/output.json`) are not in this scope: see
docs/v2.1/decisions/B03-R3-detail.md, residual risks.

Pins aisef2/app/adapters.py::Reviewer.review, aisef2/app/review_verify.py::detail, ::preserve, ::artifact_problems,
aisef2/app/run.py::evidence_manifest, aisef2/app/verify.py::verify"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
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

SECRET = "s3cr3t-value-0123456789"
TAIL = "END-OF-STDIN-MARKER"
#: attempt 1's finding: three arguments are a usage error (clause 1.2, exit 2 on two approved stimuli); the stdin
#: is what makes it long — the secret early, the tail marker after 4,000 characters
LONG = {"clause": "R-CLI/1.2", "subject": C.MAIN,
        "stimulus": {"argv": ["1", "2", "3"], "stdin": {"text": f"key={SECRET} " + "x" * 4000 + TAIL}},
        "observable": {"exit_code": 2, "within_s": 20}}
LIGHT = ("RUN.json", "RUN.started.json", "EVIDENCE.json", "run", "sessions", "preflight", V.ARTIFACT_DIR)


@unittest.skipUnless(os.name == "posix", "the fake client and the fake finder are scripts started by their shebang")
class ABlockedFindingLongerThanItsStatement(unittest.TestCase):
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
        cls.project = bundle.load(C.cli_bundle(git(src, "rev-parse", "HEAD")))
        cls.bin = cls.tmp / "bin"
        cls.bin.mkdir()
        for name, body in (("opencode", C.FAKE_DEVELOPER), ("ocr", C.FAKE_OCR)):
            (cls.bin / name).write_text(f"#!{sys.executable}\n" + body)
            (cls.bin / name).chmod(0o755)
        ocr = cls.bin / "ocr"
        review = {"policy": "fix-loop", "min_severity": "high", "finder": "ocr",
                  "ocr": {"exe": str(ocr), "sha256": hashlib.sha256(ocr.read_bytes()).hexdigest(), "timeout_min": 1,
                          "max_tokens": 4000}}
        cfg = settings.load({**SETTINGS, "review": review, "client_env": ["AISEF_TEST_SECRET"]})
        (cls.bin / "answers.json").write_text(json.dumps([C.answer(C.DEFECTIVE), C.answer(C.FIXED)]), encoding="utf-8")
        (cls.bin / "scenarios.json").write_text(json.dumps([{"reproducers": [LONG], "summary": f"uses {SECRET}"}, {}]),
                                                encoding="utf-8")
        cls.out = cls.tmp / "out"
        env = mock.patch.dict(os.environ, {**client_config(cls.tmp), "AISEF_TEST_SECRET": SECRET})
        scanner = mock.patch.object(ad, "scanner", lambda: ad.NoScanner())
        with env, scanner:
            cls.rec = R.execute(cls.project, cfg, src, cls.out, transport=provider(), client_exe=str(cls.bin / "opencode"),
                                cals=R.calibrations())
        cls.events = format3.reconstruct((cls.out / "run" / "journals" / "aisef-run.jsonl").read_text(encoding="utf-8")).events
        cls.blocked = [e.data for e in cls.events if e.type == "gate/check" and e.data["check"].startswith("S1:review:")
                       and e.data["passed"] is False]

    # ------------------------------------------------------------------------------------------- the statement

    def statement(self) -> dict:
        (b,) = self.blocked
        return json.loads(b["detail"].split(" — ", 1)[1])

    def test_the_run_blocked_on_the_finding_and_fixed_it(self):
        self.assertEqual((self.rec["story_outcomes"], self.rec["delivery_verdict"]), ({"S1": ["RETRY", "COMMIT"]}, "PASS"))
        self.assertEqual([e.data["code"] for e in self.events if e.type == "failure/observed"], ["REVIEW_FINDING"])
        self.assertIn("probe:probe.cli_invocation:REFUTED", self.blocked[0]["detail"])

    def test_the_blocked_row_is_valid_json_within_the_bound_and_says_what_decided_it(self):
        text = self.blocked[0]["detail"].split(" — ", 1)[1]
        self.assertLessEqual(len(text), V.SUMMARY_MAX)
        d = json.loads(text)
        self.assertEqual((d["verification"], d["anchor"], d["observed"], d["clause"], d["severity"]),
                         (V.CONFIRMED, V.ANCHORED, "REFUTED", "R-CLI/1.2", "high"))
        self.assertIn("BC-USAGE-0", d["anchor_why"])
        self.assertIn("refutes", d["why"])
        self.assertEqual(d["reproducer"]["subject"], C.MAIN)
        self.assertEqual(d["reproducer"]["observable"], {"exit_code": 2, "within_s": 20})
        # the conditions to reproduce, as far as the statement reaches, and that it was cut and by how much
        shown = d["reproducer"]["stimulus"]
        self.assertIsInstance(shown, str)
        self.assertIn('"argv": ["1", "2", "3"]', shown)
        self.assertNotIn(TAIL, shown)
        whole = json.dumps({**LONG["stimulus"], "stdin": {"text": f"key={V.REDACTED} " + "x" * 4000 + TAIL}},
                           ensure_ascii=False, sort_keys=True)
        self.assertEqual(d["elided"]["stimulus"], len(whole) - len(shown))

    def test_the_statement_names_the_artifact_and_it_is_the_file_with_that_digest(self):
        ref = self.statement()["artifact"]
        self.assertEqual(ref["path"], "review-findings/S1.1.0.json")
        data = (self.out / ref["path"]).read_bytes()
        self.assertEqual((ref["sha256"], ref["bytes"]), (hashlib.sha256(data).hexdigest(), len(data)))
        self.assertEqual(sorted(p.name for p in (self.out / V.ARTIFACT_DIR).iterdir()), ["S1.1.0.json"])

    def test_the_artifact_holds_the_whole_reproducer_redacted_and_the_candidate_it_ran_at(self):
        doc = json.loads((self.out / "review-findings" / "S1.1.0.json").read_bytes())
        stdin = doc["finding"]["reproducer"]["stimulus"]["stdin"]["text"]
        self.assertEqual(stdin, f"key={V.REDACTED} " + "x" * 4000 + TAIL)       # the tail the statement could not hold
        self.assertEqual(doc["redacted"], 2)      # the stimulus's, and the finder's prose
        self.assertEqual((doc["format"], doc["story_id"], doc["attempt"], doc["index"]), (V.ARTIFACT_FORMAT, "S1", 1, 0))
        self.assertEqual((doc["finding"]["verification"]["status"], doc["finding"]["anchor"]["status"]),
                         (V.CONFIRMED, V.ANCHORED))
        self.assertEqual(doc["finding"]["reproducer"]["observable"], {"exit_code": 2, "within_s": 20})
        reviewed = json.loads(sorted(self.bin.glob("review-*.json"))[0].read_text())
        self.assertEqual(doc["revision"], reviewed[reviewed.index("--to") + 1])    # what the finder was given and the probe ran
        self.assertEqual(doc["session"], "S1.reviewer.1.jsonl")

    def test_the_second_attempt_found_nothing_and_kept_nothing(self):
        self.assertEqual(len(list((self.out / V.ARTIFACT_DIR).glob("*.json"))), 1)
        self.assertEqual([r["check"] for r in (e.data for e in self.events if e.type == "gate/check")
                          if r["check"].startswith("S1:review") and r["passed"]], ["S1:review"])

    # ------------------------------------------------------------------------------------------------ secrets

    def test_the_secret_is_in_nothing_the_run_persisted_for_its_reviewers_findings(self):
        persisted = [self.out / "RUN.json", self.out / "EVIDENCE.json", self.out / "RUN.started.json",
                     *(self.out / "run" / "journals").glob("*.jsonl"), *(self.out / "sessions").glob("*.jsonl"),
                     *(self.out / V.ARTIFACT_DIR).glob("*.json"), *self.bin.glob("prompt-*.txt")]
        self.assertGreater(len(persisted), 8)
        for p in persisted:
            with self.subTest(file=p.name):
                self.assertNotIn(SECRET, p.read_text(encoding="utf-8"))

    def test_the_developer_is_told_the_finding_as_stated_on_its_retry(self):
        first, second = (p.read_text(encoding="utf-8") for p in sorted(self.bin.glob("prompt-*.txt")))
        self.assertNotIn("REVIEW_FINDING", first)
        self.assertIn("REVIEW_FINDING (owner REVIEW)", second)
        self.assertIn(self.statement()["artifact"]["path"], second)
        self.assertIn('"elided"', second)
        self.assertNotIn(SECRET, second)

    def test_the_record_keeps_the_finding_the_finder_made_with_the_secret_out(self):
        rec = json.loads((self.out / "RUN.json").read_text(encoding="utf-8"))
        found = [f for s in rec["sessions"] for f in s.get("findings", [])]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["verification"]["status"], V.CONFIRMED)
        self.assertEqual(found[0]["summary"], f"uses {V.REDACTED}")
        self.assertEqual(found[0]["reproducer"]["stimulus"]["stdin"]["text"], f"key={V.REDACTED} " + "x" * 4000 + TAIL)

    # ------------------------------------------------------------------------------------------- the binding

    def light_copy(self, name: str) -> pathlib.Path:
        dst = self.tmp / name
        dst.mkdir()
        for rel in LIGHT:
            src = self.out / rel
            (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst / rel)
        return dst

    def test_the_manifest_lists_the_artifact_and_the_run_verifies(self):
        manifest = json.loads((self.out / "EVIDENCE.json").read_text(encoding="utf-8"))
        ref = self.statement()["artifact"]
        self.assertEqual(manifest["files"][ref["path"]], ref["sha256"])
        v = verify(self.project, self.out)
        self.assertEqual((v["verdict"], v["problems"], v["notes"]), ("VERIFIED", [], []))
        self.assertEqual(R.anchor_of(manifest), v["evidence_anchor"])
        copy = self.light_copy("pristine")
        self.assertEqual(verify(self.project, copy)["verdict"], "VERIFIED")

    def test_an_altered_artifact_is_refuted_by_the_manifest_and_by_the_row(self):
        copy = self.light_copy("altered")
        path = copy / "review-findings" / "S1.1.0.json"
        path.write_bytes(path.read_bytes().replace(b'"attempt": 1', b'"attempt": 7'))
        v = verify(self.project, copy)
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertTrue(any("review-findings/S1.1.0.json" in p and "manifest" in p for p in v["problems"]), v["problems"])
        self.assertTrue(any("is not the file the row binds" in p for p in v["problems"]), v["problems"])

    def test_a_removed_artifact_is_refuted(self):
        copy = self.light_copy("removed")
        (copy / "review-findings" / "S1.1.0.json").rename(copy / "elsewhere")
        v = verify(self.project, copy)
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertTrue(any("cannot be read" in p for p in v["problems"]), v["problems"])
        self.assertTrue(any("manifest" in p for p in v["problems"]), v["problems"])

    def test_an_artifact_rewritten_with_the_manifest_made_again_is_still_not_the_file_the_row_binds(self):
        """The journal is the binding: a consistent rewrite of the file and of EVIDENCE.json is caught by the row, and
        by the anchor the run printed."""
        copy = self.light_copy("rewritten")
        path = copy / "review-findings" / "S1.1.0.json"
        path.write_bytes(path.read_bytes().replace(b'"index": 0', b'"index": 9'))
        (copy / "EVIDENCE.json").write_text(json.dumps(R.evidence_manifest(copy), indent=1, sort_keys=True) + "\n",
                                            encoding="utf-8")
        v = verify(self.project, copy, expect_anchor=R.anchor_in(self.out))
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertTrue(any("is not the file the row binds" in p for p in v["problems"]), v["problems"])
        self.assertTrue(any("evidence anchor" in p for p in v["problems"]), v["problems"])
        self.assertFalse(any("manifest does not match" in p for p in v["problems"]), v["problems"])

    def test_without_a_manifest_the_row_still_binds_the_artifact(self):
        copy = self.light_copy("no-manifest")
        (copy / "EVIDENCE.json").rename(copy / "was-EVIDENCE.json")
        self.assertEqual(verify(self.project, copy)["verdict"], "VERIFIED")        # as a run of an earlier release
        path = copy / "review-findings" / "S1.1.0.json"
        path.write_bytes(path.read_bytes() + b"\n")
        v = verify(self.project, copy)
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertTrue(any("is not the file the row binds" in p for p in v["problems"]), v["problems"])

    def test_a_file_in_the_directory_no_row_names_is_refuted_by_the_manifest(self):
        copy = self.light_copy("extra")
        (copy / "review-findings" / "S1.1.1.json").write_text("{}\n", encoding="utf-8")
        v = verify(self.project, copy)
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertTrue(any("review-findings/S1.1.1.json" in p for p in v["problems"]), v["problems"])


if __name__ == "__main__":
    unittest.main()
