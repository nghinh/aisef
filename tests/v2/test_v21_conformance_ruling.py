"""validation/qualification/v21_conformance_ruling.py (owner B-03d) and the cycle-2 conformance record's 2.1 refusal: the
ruling is written once and never over a 2.0 or cycle-2 record, --check names a sha drift, a missing and an extra row, each
row's behaviour tests exist, release_differences reads only a committed ruling; c2_orchestration_repair --write and its
(b) job refuse before measuring on 2.1. Needs validation/qualification (not in the mutation runner's copy; not a kill file)."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import c2_orchestration_repair as rp  # noqa: E402
from validation.qualification import q5  # noqa: E402
from validation.qualification import v21_conformance_ruling as R  # noqa: E402


def _sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


class Writer(unittest.TestCase):
    def test_every_path_in_the_repository_outside_v2_1_is_refused_before_anything_is_derived(self):
        for rel in ("closure-evidence/v2/CONFORMANCE-RULING.json", "closure-evidence/v2/cycle2/CONFORMANCE-RULING.json",
                    "closure-evidence/v2/release/CONFORMANCE-RULING.json", "docs/CONFORMANCE-RULING.json"):
            with self.subTest(rel), mock.patch.object(R, "derive", side_effect=AssertionError("derived")):
                self.assertEqual(R.main(["--write", "--out", rel]), 2)
                self.assertFalse((ROOT / rel).exists())
        with mock.patch.object(R, "derive", side_effect=AssertionError("derived")):   # an existing 2.0 record
            self.assertEqual(R.main(["--write", "--out", rp.OUT_REL]), 2)

    def test_the_output_is_opened_with_mode_x_and_a_problem_writes_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            kept = pathlib.Path(t) / "kept.json"
            kept.write_text("kept", encoding="utf-8")
            with mock.patch.object(R, "derive", side_effect=AssertionError("derived")):
                self.assertEqual(R.write(kept), 2)                           # refused up front
            with mock.patch.object(R, "refused", return_value=None), mock.patch.object(R, "dirty", return_value=[]), \
                    mock.patch.object(R, "derive", return_value=({"conformance": {"rows": []}}, [])):
                self.assertEqual(R.write(kept), 2)                           # and by the open itself (mode "x")
                fresh = pathlib.Path(t) / "fresh.json"
                self.assertEqual(R.write(fresh), 0)
                self.assertEqual(json.loads(fresh.read_text(encoding="utf-8")), {"conformance": {"rows": []}})
            self.assertEqual(kept.read_text(encoding="utf-8"), "kept")
            with mock.patch.object(R, "dirty", return_value=[]), mock.patch.object(R, "derive", return_value=({}, ["a problem"])):
                self.assertEqual(R.write(pathlib.Path(t) / "none.json"), 2)
            self.assertFalse((pathlib.Path(t) / "none.json").exists())
            with mock.patch.object(R, "dirty", return_value=[" M aisef2/x.py"]), mock.patch.object(R, "derive", side_effect=AssertionError):
                self.assertEqual(R.write(pathlib.Path(t) / "dirty.json"), 2)  # an uncommitted tree is never written from


class Derivation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rec, cls.problems = R.derive()

    def test_this_tree_derives_a_ruling_with_no_problem(self):
        self.assertEqual(self.problems, [])

    def test_one_row_per_file_2_1_changed_that_the_cycle_2_record_reports_each_bound_to_its_bytes(self):
        rows = self.rec["conformance"]["rows"]
        self.assertEqual([r["path"] for r in rows], sorted(R.ROWS))
        for r in rows:
            with self.subTest(r["path"]):
                self.assertEqual(r["sha256_2_1"], rp._lf((ROOT / r["path"]).read_bytes()))
                self.assertNotEqual(r["sha256_v2_0_0"], r["sha256_2_1"])
                self.assertTrue(r["change"] and r["backlog"] and r["owner_approval"] and r["requirement"])
        found = {x.split(" ", 2)[1] for x in rp.check() if x.startswith("(d) ")}
        self.assertEqual({r["path"] for r in rows}, {p for p in found if p in R.ROWS})
        # every file the record reports changed has a row: catalog.py too, which V2.0's B1 changed and the 2.1 probe window
        # changed again (the capability a catalog entry carries: owner item 1 of 2026-10-15), so it is ruled like the others
        self.assertEqual(found - {r["path"] for r in rows}, set())

    def test_each_row_s_behaviour_tests_exist_and_a_missing_one_is_named(self):
        for r in self.rec["conformance"]["rows"]:
            with self.subTest(r["path"]):
                self.assertTrue(r["behaviour_tests"])
                self.assertEqual(R.missing_tests(r["behaviour_tests"]), [])
        bad = ["tests.v2.test_c2_orchestration_conformance.Record.test_none",
               "tests.v2.test_c2_orchestration_conformance.NoSuchClass.test_15_the_record_binds_this_tree_and_old_and_new_agree_on_every_single_probe_story",
               "tests.v2.no_such_module.Record.test_15"]
        self.assertEqual(R.missing_tests(bad), bad)

    def test_the_owner_text_is_verbatim_and_v21_37_is_not_owner_approved(self):
        a = self.rec["authority"]
        self.assertTrue(a["quoted_verbatim"])
        self.assertEqual((a["decision"]["seq"], a["decision"]["part"], a["decision"]["approver"]), (5, "B-03d", "human:owner"))
        self.assertIn("did not write or sign", self.rec["recorded_by"])
        row = next(r for r in self.rec["conformance"]["rows"] if r["path"] == "aisef2/probe/file_artifact.py")
        self.assertIn("V21-37: NOT owner-approved", row["owner_approval"])

    def test_the_engine_digest_is_not_tolerated_and_the_record_is_history(self):
        i = self.rec["identity"]
        self.assertIn("NOT tolerated", i["engine_digest"])
        self.assertTrue(set(i["moved_from_the_record"]) <= set(R.IDENTITY_WHY))
        self.assertNotIn(None, i["probe_sources_moved_from_the_record"].values())
        h = self.rec["history"]
        self.assertTrue(h["is_its_v2_0_0_blob"])
        self.assertIn("never re-written on 2.1", h["c2_orchestration_repair_write"])

    def test_check_names_a_sha_drift_a_missing_row_an_extra_row_and_a_stale_section(self):
        rows = self.rec["conformance"]["rows"]
        first = rows[0]["path"]

        def check_of(doc: dict) -> list[str]:
            with tempfile.TemporaryDirectory() as t, mock.patch.object(R, "derive", return_value=(self.rec, [])):
                p = pathlib.Path(t) / "ruling.json"
                p.write_text(json.dumps(doc), encoding="utf-8")
                return R.check(p)
        self.assertEqual(check_of(self.rec), [])
        drift = copy.deepcopy(self.rec)
        drift["conformance"]["rows"][0]["sha256_2_1"] = "0" * 64
        self.assertEqual([x.split(" is ")[0] for x in check_of(drift)], [f"row {first}: sha256_2_1"])
        missing = copy.deepcopy(self.rec)
        del missing["conformance"]["rows"][0]
        self.assertEqual(check_of(missing), [f"row {first}: missing — 2.1 changed it and the cycle-2 record reports it"])
        extra = copy.deepcopy(self.rec)
        extra["conformance"]["rows"].append({**rows[0], "path": "aisef2/orchestrate/proof.py"})
        self.assertEqual(check_of(extra), ["row aisef2/orchestrate/proof.py: extra — not a file 2.1 changed that the cycle-2 record reports"])
        stale = copy.deepcopy(self.rec)
        stale["authority"]["owner_text"][0] = "a paraphrase"
        self.assertEqual(check_of(stale), ["stale: authority.owner_text[0]"])
        moved = copy.deepcopy(self.rec)
        moved["written_at"]["head"] = "0" * 40                               # when it was written is not compared
        self.assertEqual(check_of(moved), [])
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(len(R.check(pathlib.Path(t) / "none.json")), 1)


class Tolerated(unittest.TestCase):
    def _git(self, root: pathlib.Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                       capture_output=True, check=True)

    def test_only_a_committed_ruling_names_anything(self):
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            with mock.patch.object(R, "ROOT", root):
                self.assertEqual(R.tolerated(), {})                          # no ruling
                p = root / R.OUT_REL
                p.parent.mkdir(parents=True)
                p.write_text(json.dumps({"conformance": {"rows": [{"path": "a.py", "sha256_2_1": "f" * 64}]}}), encoding="utf-8")
                self.assertEqual(R.tolerated(), {})                          # not in a repository
                self._git(root, "init", "-q")
                self.assertEqual(R.tolerated(), {})                          # not committed
                self._git(root, "add", "-A")
                self._git(root, "commit", "-q", "-m", "ruling")
                self.assertEqual(R.tolerated(), {"a.py": "f" * 64})
                p.write_text(json.dumps({"conformance": {"rows": [{"path": "b.py", "sha256_2_1": "e" * 64}]}}), encoding="utf-8")
                self.assertEqual(R.tolerated(), {})                          # edited after its commit


class CommittedRuling(unittest.TestCase):
    def test_the_committed_ruling_is_what_this_tree_derives(self):
        """Red until the ruling is generated on the final 2.1 tree and committed (the lead's step); then any change to a
        file it names, to its reasons or to the Q5 data it carries makes it stale."""
        self.assertEqual(R.check(), [])
        self.assertTrue(R.tolerated(), f"{R.OUT_REL} is not committed as it is")


class CycleTwoRecord(unittest.TestCase):
    """c2_orchestration_repair.py --write on 2.1 would re-measure (b) on a corpus without post-merge-regression and
    overwrite the historical record: it refuses before measuring anything."""

    def test_write_refuses_before_measuring_on_2_1(self):
        before = _sha(rp.OUT_REL)
        with mock.patch.object(rp, "materialise", side_effect=AssertionError("measured")), \
                mock.patch.object(rp, "in_kernel", side_effect=AssertionError("measured")), \
                mock.patch.object(rp, "matrix", side_effect=AssertionError("measured")):
            with self.assertRaises(SystemExit) as e:
                rp.write()
        self.assertIn("refused before measuring: q5.CORPUS has no ['post-merge-regression']", str(e.exception))
        self.assertIn("is cycle-2 history and is never re-written on 2.1", str(e.exception))
        self.assertEqual(_sha(rp.OUT_REL), before)
        with self.assertRaises(SystemExit):
            rp.main(["--write"])
        self.assertEqual(_sha(rp.OUT_REL), before)

    def test_the_b_job_refuses_before_executing_an_item(self):
        with mock.patch.object(q5, "execute", side_effect=AssertionError("executed")), self.assertRaises(SystemExit) as e:
            rp._job_q5()
        self.assertIn("never re-written on 2.1", str(e.exception))

    def test_the_refusal_is_exactly_a_missing_cycle_1_item(self):
        corpus = [type("Item", (), {"id": i})() for i in rp.CYCLE1_ITEMS]
        with mock.patch.object(q5, "CORPUS", corpus):
            self.assertIsNone(rp.cycle1_items_refusal())
        with mock.patch.object(q5, "CORPUS", corpus[1:]):
            self.assertIn(f"has no [{rp.CYCLE1_ITEMS[0]!r}]", rp.cycle1_items_refusal())


if __name__ == "__main__":
    unittest.main()
