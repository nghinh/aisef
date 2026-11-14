"""B1 gap kill tests for aisef2/app/bundle_cli.py::lint.

`lint` sorts its two diagnostic lists (`criteria_without_calibration`, L788; `criteria_without_contract`,
L789). The surviving mutants replace each `sorted()` with `list()`, leaking plan-obligation order
(the insertion order of `_spec_rows`' dict). Every existing assertion re-sorts both sides, so an
order change cannot fail it; this file pins the sorted order exactly, on fixtures whose plan order
provably differs from sorted order. Offline; no provider; no run.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import calibrations as shipped  # noqa: E402
from tests.v2.test_v21_kills3_T03a import LEDGERLOCK_2_0_0, git, lint_of, run_main  # noqa: E402


def _plan_criteria(bundle_path: pathlib.Path) -> list[str]:
    """Unique criterion ids of the bundle's plan, in the plan's own (insertion) order."""
    doc = json.loads(bundle_path.read_text(encoding="utf-8"))
    return list(dict.fromkeys(o["criterion_id"] for o in doc["plan"]["obligations"]))


class LintDiagnosticListsAreSorted(unittest.TestCase):
    """The order of the two diagnostic lists is sorted order, not plan order."""

    @classmethod
    def setUpClass(cls) -> None:
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        d = pathlib.Path(tmp.name) / "calc-3-stories"
        code, _, err = run_main("init", "--example", "calc-3-stories", "--out", d)
        assert code == 0, err
        git(d / "repo", "init", "-q", "-b", "main")
        git(d / "repo", "add", "-A")
        git(d / "repo", "commit", "-q", "-m", "baseline")
        code, _, err = run_main("seal", d / "authoring.json", "--repo", d / "repo", "--out", d / "b0.json")
        assert code == 0, err
        cls.sealed = d / "b0.json"

    # Kills: L788 sorted() -> list()
    def test_criteria_without_calibration_is_in_sorted_order_not_plan_order(self):
        ids = _plan_criteria(self.sealed)
        # fixture preconditions: plan order and sorted order genuinely differ, so order is observable
        self.assertGreater(len(ids), 1)
        self.assertNotEqual(ids, sorted(ids))
        with mock.patch.object(shipped, "CALIBRATIONS", ()):
            code, report, err = lint_of(self.sealed)
        self.assertEqual(code, 1, err)
        # exact equality, left side NOT re-sorted: list() would leak plan order and fail here
        self.assertEqual(report["criteria_without_calibration"], sorted(ids))

    # Kills: L789 sorted() -> list()
    def test_criteria_without_contract_is_in_sorted_order_not_plan_order(self):
        ids = _plan_criteria(LEDGERLOCK_2_0_0)
        # fixture preconditions: every criterion lacks a contract here, and plan order != sorted order
        self.assertGreater(len(ids), 1)
        self.assertNotEqual(ids, sorted(ids))
        code, report, err = lint_of(LEDGERLOCK_2_0_0)
        self.assertEqual(code, 1, err)
        # exact equality, left side NOT re-sorted: list() would leak plan order and fail here
        self.assertEqual(report["criteria_without_contract"], sorted(ids))


if __name__ == "__main__":
    unittest.main()
