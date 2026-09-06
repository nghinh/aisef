"""Mã tiêu chí ↔ tên test (G5)."""

from __future__ import annotations

import unittest

from aisef.control.acceptance import ac_code, codes, coverage, missing


class TestMa(unittest.TestCase):
    def test_codes_are_one_based_and_stable(self):
        self.assertEqual(codes("STORY-01-01", 2), ["AC-STORY-01-01-1", "AC-STORY-01-01-2"])
        self.assertEqual(ac_code("S", 7), "AC-S-7")


class TestKhop(unittest.TestCase):
    def test_whole_code_only(self):
        ids = ["AC-S-10: mười", "AC-S-1: một"]
        self.assertEqual(coverage("S", 10, ids)[1], ["AC-S-1: một"])
        self.assertEqual(coverage("S", 10, ids)[10], ["AC-S-10: mười"])
        self.assertEqual(missing("S", 10, ids), list(range(2, 10)))

    def test_pytest_names_use_underscores(self):
        ids = ["test_ac.py::test_AC_STORY_01_01_1_chuoi_rong", "test_ac.py::TestNhom::test_AC_STORY_01_01_2_dao_tu"]
        self.assertEqual(missing("STORY-01-01", 2, ids), [])

    def test_vitest_path_prefixed_names(self):
        ids = ["src/a.test.ts > nhóm > AC-STORY-01-01-1: rỗng 3ms"]
        self.assertEqual(coverage("STORY-01-01", 1, ids)[1], ids)

    def test_case_insensitive_but_not_substring_of_other_story(self):
        self.assertEqual(missing("S-1", 1, ["ac-s-1-1 ok"]), [])
        self.assertEqual(missing("S-1", 1, ["XAC-S-1-1 ok"]), [1])       # dính chữ trước → không phải mã
        self.assertEqual(missing("S-1", 1, ["AC-S-11-1 ok"]), [1])       # story khác

    def test_no_test_ids_means_everything_missing(self):
        self.assertEqual(missing("S", 3, []), [1, 2, 3])
