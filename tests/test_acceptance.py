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


class TestDanhTinhTieuChiOnDinh(unittest.TestCase):
    """Lỗi 159 — mã tiêu chí sinh từ **vị trí**, nên rút một tiêu chí làm mọi mã
    sau nó tụt bậc và phép thử cũ lặng lẽ thành bằng chứng cho tiêu chí **khác**.

    Corpus thật đã tạo ra ca này: marks-cli STORY-01-02 rút `AC-1.2-1`, và các
    phép thử tên `AC-STORY-01-02-1` (khẳng định stub `list` trả not-implemented)
    được người viết mã STORY-02-02 sửa tại chỗ thành khẳng định `(no bookmarks)`
    — nên chúng chứng minh hành vi của STORY-02-02 trong khi mã ấy sau khi tụt
    bậc là tiêu chí *"động từ lạ thì exit 1"*. `missing()` trả rỗng, nên
    `criteria have tests` **đạt** trên một bằng chứng gán sai.
    """

    TESTS = [
        "AC-STORY-01-02-1: stub cmdList returns not-implemented and exits 1",
        "AC-STORY-01-02-2: unknown verb exits 1 with a stderr line",
        "AC-STORY-01-02-3: real dispatch wires the four commands",
        "AC-STORY-01-02-4: package.json declares type module",
    ]

    def test_ma_mo_coi_phai_bi_phat_hien(self):
        """Sau khi rút một tiêu chí, `AC-…-4` không còn tiêu chí nào — phải nêu."""
        from aisef.control.acceptance import orphans
        self.assertEqual(orphans("STORY-01-02", 3, self.TESTS),
                         ["AC-STORY-01-02-4"])

    def test_khong_con_tieu_chi_nao_thi_moi_ma_deu_mo_coi(self):
        from aisef.control.acceptance import orphans
        self.assertEqual(len(orphans("STORY-01-02", 0, self.TESTS)), 4)

    def test_du_ma_thi_khong_bao_mo_coi(self):
        from aisef.control.acceptance import orphans
        self.assertEqual(orphans("STORY-01-02", 4, self.TESTS), [])

    def test_ma_cua_story_khac_khong_bi_tinh_la_mo_coi(self):
        """`AC-STORY-99-01-1` không phải mã của story này — im lặng, không báo."""
        from aisef.control.acceptance import orphans
        self.assertEqual(
            orphans("STORY-01-02", 3, [*self.TESTS[:3], "AC-STORY-99-01-1: khác"]),
            [])
