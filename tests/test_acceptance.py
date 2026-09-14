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


class TestDanhTinhBenTheoNoiDung(unittest.TestCase):
    """Lỗi 159, nửa còn lại: `orphans()` chỉ bắt được ca **rút** tiêu chí, vì nó
    đếm. **Đảo thứ tự** hai tiêu chí không đổi số lượng, không để lại mã mồ côi
    nào, mà vẫn tráo bằng chứng của hai tiêu chí cho nhau — nên đếm là không đủ.

    Danh tính bền phải đến từ **nội dung** tiêu chí, không từ vị trí. Cặp
    `(mã, vân tay nội dung)` cho danh tính ấy mà không phải đổi tên phép thử:
    phép thử mang mã `AC-S-1` chỉ còn là bằng chứng cho tiêu chí 1 khi vân tay
    của tiêu chí 1 hôm nay đúng bằng vân tay lúc phép thử được ghi công.
    """

    A = "Given an unknown verb, When it runs, Then it exits 1."
    B = "Given package.json is inspected, Then it declares type module."

    def test_dao_thu_tu_bi_phat_hien_du_so_luong_khong_doi(self):
        from aisef.control.acceptance import drift, identities
        truoc = identities("STORY-01-02", [self.A, self.B])
        sau = identities("STORY-01-02", [self.B, self.A])
        self.assertEqual(drift(truoc, sau),
                         ["AC-STORY-01-02-1", "AC-STORY-01-02-2"])

    def test_khong_doi_thi_khong_truot(self):
        from aisef.control.acceptance import drift, identities
        x = identities("STORY-01-02", [self.A, self.B])
        self.assertEqual(drift(x, identities("STORY-01-02", [self.A, self.B])), [])

    def test_ngat_dong_khac_nhau_khong_tinh_la_truot(self):
        """Thẻ story sinh lại từ `epics.md`; ngắt dòng đổi mà nghĩa không đổi
        thì báo truợt là báo động giả."""
        from aisef.control.acceptance import drift, identities
        truoc = identities("S", ["Given an unknown verb,\n  When it runs."])
        sau = identities("S", ["Given an unknown   verb, When it runs.  "])
        self.assertEqual(drift(truoc, sau), [])

    def test_rut_tieu_chi_thi_ma_con_lai_deu_truot(self):
        """Ca marks-cli thật: rút tiêu chí đầu làm mã 1 mang nội dung cũ của 2."""
        from aisef.control.acceptance import drift, identities
        C = "Given a handler returns arrays, Then the dispatcher writes them."
        truoc = identities("S", ["placeholder", self.A, self.B, C])
        sau = identities("S", [self.A, self.B, C])
        self.assertEqual(drift(truoc, sau), ["AC-S-1", "AC-S-2", "AC-S-3"])

    def test_mot_phep_thu_mang_hai_ma_la_gan_nhap_nhang(self):
        """Một phép thử tên `AC-S-1 AC-S-2` thoả **cả hai** tiêu chí trong khi
        chứng minh một hành vi — đúng một đường đạt-sai của mục cấu trúc."""
        from aisef.control.acceptance import overloaded
        self.assertEqual(
            overloaded("S", ["AC-S-1 and AC-S-2: both at once", "AC-S-3: fine"]),
            {"AC-S-1 and AC-S-2: both at once": ["AC-S-1", "AC-S-2"]})

    def test_mot_ma_mot_phep_thu_thi_khong_nhap_nhang(self):
        from aisef.control.acceptance import overloaded
        self.assertEqual(overloaded("S", ["AC-S-1: one", "AC-S-1: also one"]), {})

    def test_ma_story_khac_trong_cung_ten_khong_tinh(self):
        from aisef.control.acceptance import overloaded
        self.assertEqual(overloaded("S", ["AC-S-1 vs AC-T-2: khác story"]), {})
