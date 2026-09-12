"""Phép thử cho lớp tương thích hệ điều hành.

Lỗi 71/72 (CI Windows 2026-09-12): mã khoá và ghi nguyên tử của phase 2/3 viết
bằng hằng và ngữ nghĩa chỉ có trên POSIX — `os.O_CLOEXEC` không tồn tại trên
Windows (mọi phiên `reserve`/lease chết bằng `AttributeError`), và `os.replace`
trên Windows từ chối khi còn bất kỳ handle nào mở tệp đích (`PermissionError`
WinError 5, kho bộ nhớ có người đọc chen vào lúc ghi).

Máy đo là macOS nên hai lớp này chỉ lộ trên CI. Phép thử dưới đây giả lập
Windows chứ không đợi CI: cái đắt nhất của lỗi hệ điều hành là vòng lặp "đẩy
rồi chờ mười ba phút".
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aisef import _compat  # noqa: E402


class TestMoLockFdChayDuocTrenMoiHeDieuHanh(unittest.TestCase):
    def test_mo_duoc_va_ghi_duoc(self):
        with tempfile.TemporaryDirectory() as d:
            fd = _compat.open_lock_fd(Path(d) / "x.lock")
            try:
                self.assertIsInstance(fd, int)
                os.write(fd, b"\0")
            finally:
                os.close(fd)

    def test_chon_dung_co_theo_he_dieu_hanh(self):
        """POSIX có `O_CLOEXEC`, Windows chỉ có `O_NOINHERIT`; đọc theo tên là
        điểm khác giữa "chạy" và `AttributeError` ở mọi phiên trên Windows."""
        class ChiPosix:
            O_CLOEXEC = 0x0100

        class ChiWindows:
            O_NOINHERIT = 0x0080

        class KhongCoGi:
            pass

        self.assertEqual(_compat._no_inherit_flag(ChiPosix), 0x0100)
        self.assertEqual(_compat._no_inherit_flag(ChiWindows), 0x0080)
        self.assertEqual(_compat._no_inherit_flag(KhongCoGi), 0, "không có cờ thì không nổ")
        self.assertNotEqual(_compat._NO_INHERIT, 0, "hệ điều hành này phải có một trong hai")


class TestGhiNguyenTuChiuDuocNgUNghiaWindows(unittest.TestCase):
    def test_thay_the_binh_thuong(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d) / "a", Path(d) / "b"
            src.write_text("mới", encoding="utf-8")
            dst.write_text("cũ", encoding="utf-8")
            _compat.atomic_replace(src, dst)
            self.assertEqual(dst.read_text(encoding="utf-8"), "mới")
            self.assertFalse(src.exists())

    def test_tren_windows_thu_lai_khi_dich_dang_mo(self):
        """Handle của người đọc đóng lại giữa chừng ⇒ lần thử sau thành công."""
        goi = {"n": 0}

        def replace(a, b):
            goi["n"] += 1
            if goi["n"] < 3:
                raise PermissionError(5, "Access is denied")

        with mock.patch.object(_compat, "_WIN", True), \
             mock.patch.object(_compat.os, "replace", replace), \
             mock.patch.object(_compat.time, "sleep", lambda _s: None):
            _compat.atomic_replace("a", "b", attempts=5, delay=0)
        self.assertEqual(goi["n"], 3)

    def test_tren_windows_van_nem_khi_khong_bao_gio_thanh_cong(self):
        """Thử lại có biên: lỗi quyền thật vẫn phải nổi lên, không nuốt."""
        def replace(a, b):
            raise PermissionError(5, "Access is denied")

        with mock.patch.object(_compat, "_WIN", True), \
             mock.patch.object(_compat.os, "replace", replace), \
             mock.patch.object(_compat.time, "sleep", lambda _s: None), \
             self.assertRaises(PermissionError):
            _compat.atomic_replace("a", "b", attempts=3, delay=0)

    def test_tren_posix_khong_thu_lai(self):
        """POSIX không có ngữ nghĩa ấy: lỗi quyền là lỗi thật, nổi lên ngay."""
        goi = {"n": 0}

        def replace(a, b):
            goi["n"] += 1
            raise PermissionError(13, "Permission denied")

        with mock.patch.object(_compat, "_WIN", False), \
             mock.patch.object(_compat.os, "replace", replace), \
             self.assertRaises(PermissionError):
            _compat.atomic_replace("a", "b", attempts=9, delay=0)
        self.assertEqual(goi["n"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
