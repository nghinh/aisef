"""Parser output test runner — trên output **thật** (tests/fixtures/testlog/)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from aisef.harness.testlog import parse

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


class TestUnittestVerbose(unittest.TestCase):
    """`python -m unittest -v` — bộ test của chính kho, bench V8 chấm theo tên."""

    def test_ten_day_du_ke_ca_khi_co_docstring(self):
        log = parse(fx("unittest-v"))
        self.assertEqual(log.format, "unittest")
        self.assertEqual(log.passed, ["tests.test_worktree.TestCreate.test_create_is_idempotent"])
        # docstring đẩy "... FAIL" xuống dòng sau; phần traceback lặp tên ca đỏ không được đếm hai lần
        self.assertEqual(log.failed, ["tests.test_worktree.TestCreate.test_stray_dir_is_not_a_worktree",
                                      "tests.test_worktree.TestCreate.test_list_active"])
        self.assertEqual(log.skipped, ["tests.test_worktree.TestCreate.test_bo_qua",
                                       "tests.test_worktree.TestCreate.test_du_kien_do"])

    def test_python_cu_chi_in_lop_thi_noi_them_ten(self):
        log = parse("test_a (tests.test_x.TestY) ... ok\n\nRan 1 test in 0.001s\n\nOK\n")
        self.assertEqual(log.passed, ["tests.test_x.TestY.test_a"])


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
        self.assertEqual(set(ev), {"test_format", "test_ids", "failed_ids", "skipped_ids", "coverage"})
        self.assertEqual(ev["failed_ids"], ["AC-STORY-01-01-3: thất bại"])


class TestCtrf(unittest.TestCase):
    """CTRF (ADR-005 V9) — fixture **thật**: pytest-json-ctrf 0.5.3 và
    vitest-ctrf-json-reporter 0.0.3 (vitest 3), cùng bốn ca như `pytest-v`."""

    def test_pytest_json_ctrf(self):
        log = parse((FIX / "ctrf-pytest.json").read_text(encoding="utf-8"))
        self.assertEqual(log.format, "ctrf")
        self.assertEqual(log.passed, ["test_ac.py::test_AC_STORY_01_01_1_chuoi_rong",
                                      "test_ac.py::test_AC_STORY_01_01_2_dao_tu"])
        self.assertEqual(log.failed, ["test_ac.py::TestNhom::test_AC_STORY_01_01_3_that_bai"])
        self.assertEqual(log.skipped, ["test_ac.py::TestNhom::test_bo_qua"])

    def test_vitest_ctrf_ghep_file_vao_ten(self):
        """Reporter vitest chỉ có `name` lá + `filePath`: ghép `file > tên` để cùng
        hình dạng với `--reporter=verbose` (cổng `_la()` đọc phần sau `>`)."""
        log = parse((FIX / "ctrf-vitest.json").read_text(encoding="utf-8"))
        self.assertEqual(log.format, "ctrf")
        self.assertEqual(log.passed, ["src/dao.test.ts > AC-STORY-01-01-1: chuỗi rỗng trả về rỗng",
                                      "src/dao.test.ts > AC-STORY-01-01-2: đảo từ"])
        self.assertEqual(log.failed, ["src/dao.test.ts > AC-STORY-01-01-3: thất bại"])
        self.assertEqual(log.skipped, ["src/dao.test.ts > bỏ qua"])

    def test_json_chen_giua_output_runner(self):
        """`pytest --ctrf=/dev/stdout`: JSON nằm giữa text của pytest — vẫn đọc."""
        text = fx("pytest-q") + "\n" + (FIX / "ctrf-pytest.json").read_text(encoding="utf-8") + "\n1 failed\n"
        log = parse(text)
        self.assertEqual(log.format, "ctrf")
        self.assertEqual(len(log.test_ids), 4)

    def test_suite_pending_va_json_la(self):
        log = parse(json.dumps({"results": {"tests": [
            {"name": "a", "status": "passed", "suite": "nhóm", "filePath": "t.spec.ts"},
            {"name": "b", "status": "pending"}, {"name": "c", "status": "other"}]}}))
        self.assertEqual(log.passed, ["t.spec.ts > nhóm > a"])
        self.assertEqual(log.skipped, ["b", "c"], "pending/other không phải xanh")
        self.assertEqual(parse(json.dumps({"results": {"tests": "x"}})).format, "")
        self.assertEqual(parse('{"a": 1}').format, "")

    def test_evidence_shape_giong_dinh_dang_khac(self):
        ev = parse((FIX / "ctrf-pytest.json").read_text(encoding="utf-8")).to_evidence()
        self.assertEqual(set(ev), {"test_format", "test_ids", "failed_ids", "skipped_ids", "coverage"})
