"""validation/qualification/v21_mutation_record.py: the V2.1 phase's reuse proof and accounting (owner B-03b) — the
V2.0-S2 standard applied to mutation.V21_TARGETS, and a kept worker history never replaced."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from validation.qualification import v21_mutation_record as R  # noqa: E402
from validation.v2 import mutation as m  # noqa: E402
from tests.v2.test_s2_mutation_record import _row  # noqa: E402
from tests.v2 import isolated_git  # noqa: E402


class Phase(unittest.TestCase):
    def test_the_phase_takes_over_every_stale_module_target_and_s2_stays_whole(self):
        self.assertEqual(len(m.S2_TARGETS), 261)
        self.assertEqual(m.PHASE_TARGETS["V2.1"], m.V21_TARGETS)
        self.assertEqual(m.RECORDS["V2.1"], "closure-evidence/v2/v2.1/MUTATION.json")
        self.assertEqual(list(m.RECORDS)[-1], "V2.1")          # last: readers that walk RECORDS let the newest win
        for t in m.V21_TARGETS:
            self.assertEqual(m.phase_of(t), "V2.1", t)
            self.assertEqual(m.SUPERSEDED[t], "V2.1", t)
        for t, k in m.S2_TARGETS.items():                    # every S2 target is re-measured, its kill set kept first
            self.assertIn(t, m.V21_TARGETS)
            self.assertEqual(m.V21_TARGETS[t][0], k[0])
            self.assertEqual([f for f in m.V21_TARGETS[t] if f in k], list(dict.fromkeys(k)))
        for rel in ("aisef2/app/lineage.py", "aisef2/app/usage.py", "aisef2/app/review_ocr.py", "aisef2/app/review_verify.py",
                    "aisef2/app/bundle_cli.py"):
            self.assertTrue(any(t.startswith(rel + "::") for t in m.V21_TARGETS), rel)
        self.assertNotIn("aisef2/app/calibrations.py::CALIBRATIONS", m.TARGETS)

    def test_the_criteria_and_the_snapshot_are_frozen_before_any_result(self):
        import json
        self.assertEqual(R.criteria_sha256(), R.FROZEN_CRITERIA_SHA256)
        manifest = json.loads((ROOT / "closure-evidence/v2/v2.1/REQUALIFICATION-MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(R.SNAPSHOT, manifest["snapshot"])


class Proof(unittest.TestCase):
    TARGET = "aisef2/app/review_verify.py::blocks"

    def result(self, **over) -> dict:
        src = (ROOT / self.TARGET.split("::")[0]).read_text(encoding="utf-8")
        descs = [d for d, _ in m.mutants(src, self.TARGET.split("::")[1], m._enum_members(src, ROOT))]
        return {"target": self.TARGET, "kill_tests": list(m.V21_TARGETS[self.TARGET]),
                "results": [{"mutant": d, "killed": True} for d in descs], **over}

    def test_a_result_measured_at_head_is_usable(self):
        self.assertEqual(R.proof(ROOT, self.result(), "HEAD")[0], [])

    def test_a_different_kill_set_a_different_mutant_list_an_error_or_another_phase_is_not(self):
        self.assertEqual(R.proof(ROOT, self.result(kill_tests=["tests/v2/test_v21_review.py"]), "HEAD")[0],
                         ["its kill set is not the current one"])
        self.assertEqual(R.proof(ROOT, self.result(results=[]), "HEAD")[0], ["its mutants are not the current generator's"])
        self.assertEqual(R.proof(ROOT, self.result(error="boom"), "HEAD")[0], ["the run errored: boom"])
        self.assertEqual(R.proof(ROOT, {**self.result(), "target": "aisef2/journal/format3.py::verified_payload"}, "HEAD")[0],
                         ["not a V2.1 target"])


class Account(unittest.TestCase):
    def test_every_v21_target_is_accounted_for_exactly_once_and_a_survivor_never_passes(self):
        a = R.S2.account([_row(t) for t in m.V21_TARGETS], m.V21_TARGETS)
        self.assertEqual((len(a["chosen"]), a["accounted_exactly_once"], a["not_passing"]), (len(m.V21_TARGETS), True, {}))
        t = next(iter(m.V21_TARGETS))
        a = R.S2.account([_row(t, survivors=["m0"], timed_out=1)], m.V21_TARGETS)
        self.assertEqual(a["not_passing"][t], ["1 unaudited survivor(s): ['m0']", "1 mutant(s) killed only by the clock"])


class ImportWorker(unittest.TestCase):
    def test_a_kept_history_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as t:
            root, wt = pathlib.Path(t) / "root", pathlib.Path(t) / "wt"
            wt.mkdir()
            isolated_git.git(wt, "init", "-q")       # no GIT_* variable or git configuration of the caller reaches it
            isolated_git.git(wt, "commit", "-q", "--allow-empty", "-m", "s")
            log = pathlib.Path(t) / "w.log"
            log.write_text("ran\n", encoding="utf-8")
            kept = R.import_worker("A", wt, "finished", log, root)
            self.assertTrue(kept.is_file())
            with self.assertRaises(FileExistsError):
                R.import_worker("A", wt, "again", log, root)
            self.assertEqual([h["worker"] for h in R.histories(root)], ["A"])

    def test_its_git_never_reaches_the_callers_repository(self):
        """Run from a pre-commit hook of a linked worktree, a test inherits GIT_DIR and GIT_INDEX_FILE (absolute paths):
        the kept-history test's git runs in its own temporary repository all the same, and the caller's — with a file
        staged — is left as it was, byte for byte."""
        with tempfile.TemporaryDirectory() as t:
            bait = pathlib.Path(os.path.realpath(t)) / "bait"
            bait.mkdir()
            isolated_git.git(bait, "init", "-q", "-b", "main")
            isolated_git.git(bait, "commit", "-q", "--allow-empty", "-m", "bait")
            (bait / "dev.txt").write_text("staged by the developer\n", encoding="utf-8")
            isolated_git.git(bait, "add", "dev.txt")
            git_dir = bait / ".git"

            def files() -> dict:
                return {p.relative_to(git_dir).as_posix(): p.read_bytes() for p in git_dir.rglob("*") if p.is_file()}
            before, result = files(), unittest.TestResult()
            with mock.patch.dict(os.environ, {"GIT_DIR": str(git_dir), "GIT_INDEX_FILE": str(git_dir / "index"),
                                              "GIT_WORK_TREE": str(bait)}):
                ImportWorker("test_a_kept_history_is_never_replaced").run(result)
            self.assertEqual((result.testsRun, result.errors, result.failures), (1, [], []))
            self.assertEqual(files(), before)


if __name__ == "__main__":
    unittest.main()
