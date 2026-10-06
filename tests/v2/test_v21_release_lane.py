"""V2.1 (A, 360° P0-3): the release tooling follows the version pyproject.toml says — a 2.0.x patch needs no constant
edited. On 2.0.0 `release_rc` hard-coded RC2 / VERSION 2.0.0 and the gate one status file: with pyproject at 2.0.1 a
staging build took 2.0.0's RC epoch, `--verify-dist` compared against 2.0.0's wheel and the gate could never pass.
2.0.0 itself reads exactly as released (RC2, V2.0-RC2-FREEZE.json, Q0-Q3-RC2, V2-STABLE-STATUS.json). Offline;
every record is written under a temporary root."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import release_rc as R  # noqa: E402

_s = importlib.util.spec_from_file_location("v2_release_gate", ROOT / "validation" / "v2_release_gate.py")
G = importlib.util.module_from_spec(_s)
_s.loader.exec_module(G)


class Tree(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)
        (self.root / R.RELEASE_DIR).mkdir(parents=True)

    def version(self, v: str) -> None:
        (self.root / "pyproject.toml").write_text(f'[project]\nname = "aisef"\nversion = "{v}"\n', encoding="utf-8")

    def frozen(self, name: str, epoch: int = 1790000000) -> None:
        (self.root / R.RELEASE_DIR / name).write_text(json.dumps({"rc": {"source_date_epoch": epoch}}), encoding="utf-8")


class Subject(Tree):
    def test_2_0_0_reads_as_released(self):
        self.version("2.0.0")
        self.frozen("V2.0-RC1-FREEZE.json")
        self.frozen("V2.0-RC2-FREEZE.json")
        self.assertEqual(R.subject(self.root), ("2.0.0", "RC2", "RC2", "closure-evidence/v2/release/V2.0-RC2-FREEZE.json"))

    def test_the_repository_is_2_0_0_s_record_unchanged(self):
        self.assertEqual((R.RC, R.TAG, R.OUT_REL), ("RC2", "RC2", "closure-evidence/v2/release/V2.0-RC2-FREEZE.json"))

    def test_a_patch_version_has_its_own_candidates_never_2_0_0_s(self):
        self.version("2.0.1")
        self.frozen("V2.0-RC2-FREEZE.json")
        self.assertEqual(R.subject(self.root), ("2.0.1", "RC1", "2.0.1-RC1", "closure-evidence/v2/release/V2.0.1-RC1-FREEZE.json"))
        for n in (1, 2, 10):
            self.frozen(f"V2.0.1-RC{n}-FREEZE.json")
        self.frozen("V2.0.1-RCx-FREEZE.json")       # not a candidate name
        self.assertEqual(R.frozen_rcs("2.0.1", self.root), ["RC1", "RC2", "RC10"])
        self.assertEqual(R.subject(self.root)[1:3], ("RC10", "2.0.1-RC10"))
        self.assertEqual(R.frozen_rcs("2.0.0", self.root), ["RC2"])

    def test_a_patch_build_before_its_freeze_takes_its_own_commit_s_time(self):
        self.version("2.0.1")
        self.frozen("V2.0-RC2-FREEZE.json", epoch=1790000000)
        _, _, _, rel = R.subject(self.root)
        with mock.patch.object(R, "ROOT", self.root), mock.patch.object(R, "OUT_REL", rel), \
                mock.patch.object(R, "_git", return_value=b"1800000000\n"):
            self.assertEqual(R.epoch(), 1800000000)
            self.frozen("V2.0.1-RC1-FREEZE.json", epoch=1795000000)
            self.assertEqual(R.epoch(), 1795000000)


class Freeze(Tree):
    def test_freeze_writes_the_version_s_next_candidate_and_never_rewrites_one(self):
        self.version("2.0.1")
        sums = self.root / "SHA256SUMS"
        sums.write_text("", encoding="utf-8")

        def fake(sha, text, run, rel=None):
            return {"rc": {"sha": sha}, "problems": [], "verdict": "FROZEN", "rel": rel}
        with mock.patch.object(R, "ROOT", self.root), mock.patch.object(R, "VERSION", "2.0.1"), \
                mock.patch.object(R, "freeze", fake):
            self.assertEqual(R.main(["--freeze", "a" * 40, "--sums", str(sums), "--ci-run", "1"]), 0)
            self.assertEqual(R.main(["--freeze", "b" * 40, "--sums", str(sums), "--ci-run", "2"]), 0)
        self.assertEqual(R.frozen_rcs("2.0.1", self.root), ["RC1", "RC2"])
        first = json.loads((self.root / R.freeze_rel("2.0.1", "RC1")).read_text(encoding="utf-8"))
        self.assertEqual(first["rc"]["sha"], "a" * 40)


class Gate(unittest.TestCase):
    OK = {"seq": 3, "approver": "human:owner", "decision": {"PRODUCTION_PUBLISH": "AUTHORIZED", "VERSION": "2.0.1"}}

    def test_each_release_has_its_own_status_file(self):
        self.assertEqual(G.status_rel("2.0.0"), "closure-evidence/v2/release/V2-STABLE-STATUS.json")
        self.assertEqual(G.status_rel("2.0.1"), "closure-evidence/v2/release/V2.0.1-STATUS.json")

    def test_a_patch_passes_on_its_own_status_and_candidate(self):
        ready = {"FINAL_RELEASE_READY": "PASS", "OPEN_BLOCKERS": []}
        ok = G.problems("2.0.1", "2.0.1", ready, {"entries": [self.OK]}, {"rc": {"version": "2.0.1"}}, [])
        self.assertEqual(ok, [])
        blocked = G.problems("2.0.1", "2.0.1", dict(ready, OPEN_BLOCKERS=["X"]), {"entries": [self.OK]},
                             {"rc": {"version": "2.0.1"}}, [])
        self.assertEqual(blocked, ["closure-evidence/v2/release/V2.0.1-STATUS.json: OPEN_BLOCKERS is ['X'], not []"])
        self.assertTrue(G.problems("2.0.1", "2.0.1", ready, {"entries": [self.OK]}, {"rc": {"version": "2.0.0"}}, []))


if __name__ == "__main__":
    unittest.main()
