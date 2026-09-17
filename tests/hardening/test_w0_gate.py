"""INV-T.QUALIFICATION-REGISTER — the W0 builder may say QUALIFIED only when the COMPLETE current defect register holds
no OPEN P0/P1, whenever an entry was registered. Found 2026-09-17: the builder read only the frozen fix families and
printed QUALIFIED with SS-65 (P1) OPEN in `additions_after_freeze`."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401

from validation import w0_qualification as W  # noqa: E402

NEEDED = ("hardening-defect-set.json", "fault-matrix.json", "differential-p12-summary.json", "mutation-results.json")


def _row(rows, name):
    return next(r for r in rows if r["criterion"] == name)


class TestAPostFreezeP1RefusesQualification(unittest.TestCase):
    def _criteria_with(self, mutate):
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp)
            for name in NEEDED:
                if (W.EV / name).is_file():
                    shutil.copy(W.EV / name, ev / name)
            ds = json.loads((ev / "hardening-defect-set.json").read_text(encoding="utf-8"))
            for fam in ds["defects_by_fix_family"].values():          # a clean frozen register as the base line
                for m in fam:
                    m["status"] = "FIXED"
            ds["additions_after_freeze"] = [dict(m, status="FIXED") for m in ds.get("additions_after_freeze", [])]
            ds["counts"]["by_status"] = {"OPEN": 0}
            mutate(ds)
            (ev / "hardening-defect-set.json").write_text(json.dumps(ds), encoding="utf-8")
            with mock.patch.object(W, "EV", ev):
                return W.criteria({"all_green": True})

    def test_control_a_clean_register_holds(self):
        rows = self._criteria_with(lambda ds: None)
        self.assertTrue(_row(rows, "0 P0/P1 open")["holds"])
        self.assertTrue(_row(rows, "0 unfixed confirmed defects from the frozen set")["holds"])

    def test_a_p1_registered_after_the_freeze_refuses(self):
        def add(ds):
            ds["additions_after_freeze"].append({"id": "SS-999", "severity": "P1", "status": "OPEN"})
            ds["counts"]["by_status"]["OPEN"] = 1
        rows = self._criteria_with(add)
        self.assertFalse(_row(rows, "0 P0/P1 open")["holds"])
        self.assertEqual(_row(rows, "0 P0/P1 open")["measured"]["open_p0_p1"], ["SS-999"])

    def test_a_p0_registered_after_the_freeze_refuses(self):
        def add(ds):
            ds["additions_after_freeze"].append({"id": "SS-998", "severity": "P0", "status": "open"})
            ds["counts"]["by_status"]["OPEN"] = 1
        self.assertFalse(_row(self._criteria_with(add), "0 P0/P1 open")["holds"])

    def test_a_register_whose_counts_disagree_with_its_entries_refuses(self):
        def stale(ds):
            ds["additions_after_freeze"].append({"id": "SS-997", "severity": "P2", "status": "OPEN"})
        row = _row(self._criteria_with(stale), "0 unfixed confirmed defects from the frozen set")
        self.assertFalse(row["holds"])
        self.assertFalse(row["measured"]["scan_agrees_with_declared_counts"])

    def test_a_member_listed_twice_counts_once(self):
        def dup(ds):
            fam = next(iter(ds["defects_by_fix_family"].values()))
            ds["additions_after_freeze"].append(dict(fam[0]))          # the same id, same status: provenance copy
        row = _row(self._criteria_with(dup), "0 unfixed confirmed defects from the frozen set")
        self.assertTrue(row["holds"], row["measured"])

    def test_two_copies_that_disagree_refuse(self):
        def split(ds):
            fam = next(iter(ds["defects_by_fix_family"].values()))
            ds["additions_after_freeze"].append(dict(fam[0], status="OPEN", severity="P1"))
            ds["counts"]["by_status"]["OPEN"] = 1
        self.assertFalse(_row(self._criteria_with(split), "0 P0/P1 open")["holds"])

    def test_the_capability_matrix_must_match_the_candidates_product_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp)
            for name in NEEDED:
                if (W.EV / name).is_file():
                    shutil.copy(W.EV / name, ev / name)
            name = "default tool capabilities qualified on real images for this product tree (INV-N.DEFAULT-CAPABILITY)"
            with mock.patch.object(W, "EV", ev), mock.patch.object(W, "_aisef_tree", return_value="t1"):
                self.assertFalse(_row(W.criteria({}, "sha"), name)["holds"], "no matrix → not qualified")
                (ev / "tool-capability-matrix.json").write_text(json.dumps({"pass": True, "aisef_tree": "t0"}), encoding="utf-8")
                self.assertFalse(_row(W.criteria({}, "sha"), name)["holds"], "a matrix of another tree → not qualified")
                (ev / "tool-capability-matrix.json").write_text(json.dumps({"pass": True, "aisef_tree": "t1"}), encoding="utf-8")
                self.assertTrue(_row(W.criteria({}, "sha"), name)["holds"])


if __name__ == "__main__":
    unittest.main()
