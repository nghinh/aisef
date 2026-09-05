"""Parser output test runner — trên output **thật** (tests/fixtures/testlog/)."""

from __future__ import annotations

import unittest
from pathlib import Path

from aisdlc.harness.testlog import parse

FIX = Path(__file__).parent / "fixtures" / "testlog"


def fx(name: str) -> str:
    return (FIX / f"{name}.txt").read_text(encoding="utf-8")


class TestNodeSpec(unittest.TestCase):
    def test_all_pass_par(self):
        log = parse(fx("node-test-pass"))
        self.assertEqual(log.format, "node-spec")
        self.assertEqual((len(log.passed), len(log.failed), len(log.skipped)), (20, 0, 0))
        self.assertIn("giữ chữ số", log.passed)

    def test_fail_skip_and_suite_line_is_not_a_test(self):
        log = parse(fx("node-test-fail"))
        self.assertEqual(log.passed, ["AC-STORY-01-01-1: chuỗi rỗng trả về rỗng", "AC-STORY-01-01-2: đảo từ"])
        self.assertEqual(log.failed, ["AC-STORY-01-01-3: thất bại"])   # không lặp từ "failing tests:"
        self.assertEqual(log.skipped, ["bỏ qua"])
        self.assertNotIn("nhóm", log.test_ids)


class TestNodeTap(unittest.TestCase):
    def test_tap_par(self):
        log = parse(fx("node-test-tap"))
        self.assertEqual(log.format, "node-tap")
        self.assertEqual(len(log.passed), 20)
        self.assertEqual(log.failed, [])

    def test_tap_suite_and_directives(self):
        text = ("TAP version 13\n# Subtest: nhóm\n    # Subtest: a\n    ok 1 - a\n      ---\n      type: 'test'\n      ...\n"
                "    not ok 2 - b\n      ---\n      type: 'test'\n      ...\n    ok 3 - c # SKIP chưa làm\n      ---\n"
                "      type: 'test'\n      ...\nnot ok 1 - nhóm\n  ---\n  type: 'suite'\n  ...\n1..1\n")
        log = parse(text)
        self.assertEqual((log.passed, log.failed, log.skipped), (["a"], ["b"], ["c"]))


class TestVitest(unittest.TestCase):
    def test_verbose_e9(self):
        log = parse(fx("vitest-verbose"))
        self.assertEqual(log.format, "vitest")
        self.assertEqual(len(log.passed), 86)
        self.assertTrue(all(" > " in t for t in log.passed))
        self.assertEqual(log.note, "")

    def test_default_reporter_has_no_names(self):
        log = parse(fx("vitest-default"))
        self.assertEqual(log.format, "vitest")
        self.assertEqual(log.test_ids, [])
        self.assertIn("--reporter=verbose", log.note)

    def test_fail_and_skip_marks(self):
        log = parse(" RUN  v5.0.0 /w\n ✓ src/a.test.ts > x > ok 1ms\n × src/a.test.ts > x > hỏng 2ms\n ↓ src/a.test.ts > x > bỏ\n")
        self.assertEqual(log.failed, ["src/a.test.ts > x > hỏng"])
        self.assertEqual(log.skipped, ["src/a.test.ts > x > bỏ"])


class TestPytest(unittest.TestCase):
    def test_verbose(self):
        log = parse(fx("pytest-v"))
        self.assertEqual(log.format, "pytest")
        self.assertEqual(log.passed, ["test_ac.py::test_AC_STORY_01_01_1_chuoi_rong",
                                      "test_ac.py::test_AC_STORY_01_01_2_dao_tu"])
        self.assertEqual(log.failed, ["test_ac.py::TestNhom::test_AC_STORY_01_01_3_that_bai"])
        self.assertEqual(log.skipped, ["test_ac.py::TestNhom::test_bo_qua"])

    def test_quiet_only_knows_failures(self):
        log = parse(fx("pytest-q"))
        self.assertEqual(log.failed, ["test_ac.py::TestNhom::test_AC_STORY_01_01_3_that_bai"])
        self.assertEqual(log.passed, [])
        self.assertIn("-v", log.note)


class TestCoverageVaLa(unittest.TestCase):
    def test_pytest_cov_total(self):
        log = parse(fx("pytest-v") + "\n---------- coverage ----------\nTOTAL     120     10    92%\n")
        self.assertEqual(log.coverage, 92.0)

    def test_istanbul_all_files(self):
        log = parse(fx("vitest-verbose") + "\nAll files |   87.5 |    70 |   90 |   87.5 |\n")
        self.assertEqual(log.coverage, 87.5)

    def test_unknown_output_does_not_guess(self):
        log = parse("Đã chạy.\nTests passed!\n")
        self.assertEqual((log.format, log.test_ids, log.coverage), ("", [], None))

    def test_evidence_shape(self):
        ev = parse(fx("node-test-fail")).to_evidence()
        self.assertEqual(set(ev), {"test_format", "test_ids", "failed_ids", "coverage"})
        self.assertEqual(ev["failed_ids"], ["AC-STORY-01-01-3: thất bại"])
