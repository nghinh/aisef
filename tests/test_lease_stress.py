"""Nhiều tiến trình **cùng UID** tranh một lease: đúng một bên được.

ADR-009 hoãn phép thử này ("stress test `flock` đa tiến trình cùng UID"). Lý do
nó đáng chạy thật chứ không mô phỏng: `flock` cấp khoá theo **mô tả tệp mở**,
không theo tiến trình hay theo người dùng, nên hai luồng trong *cùng* một tiến
trình có thể cùng thắng trong khi hai tiến trình thì không. Chỉ tiến trình thật
mới trả lời đúng câu hỏi.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

#: Mỗi con chạy đoạn này: giành lease, in "WIN" hoặc "LOSE", giữ khoá tới khi
#: được bảo thả — nếu thả ngay thì con sau giành được và phép thử vô nghĩa.
CON = """
import os, sys, time
sys.path.insert(0, %(root)r)
from aisef.harness.server_identity import acquire_port_lease
fd = acquire_port_lease(__import__("pathlib").Path(%(root_run)r), "run-chung", "http://localhost:5173")
print("WIN" if fd is not None else "LOSE", flush=True)
time.sleep(%(giu)s)
"""


class TestTranhLeaseDaTienTrinh(unittest.TestCase):
    SO_CON = 50

    def test_chi_mot_tien_trinh_thang(self):
        """Người thắng **giữ khoá tới khi cha đọc xong mọi câu trả lời**.

        Bản đầu cho người thắng giữ 1,5 giây rồi thả: trên máy CI chậm, con thứ
        40 có thể khởi động *sau* lúc ấy và cũng thắng — phép thử sẽ đỏ vì máy
        chậm chứ không vì khoá hỏng. Ở đây cha giết con sau khi đọc, nên độ lệch
        khởi động bao nhiêu cũng không đổi kết quả.
        """
        with tempfile.TemporaryDirectory() as d:
            ma = CON % {"root": str(ROOT), "root_run": d, "giu": 600}
            procs = [subprocess.Popen([sys.executable, "-c", ma],
                                      stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
                     for _ in range(self.SO_CON)]
            try:
                ket = [(p.stdout.readline() or "").strip() for p in procs]
            finally:
                for p in procs:
                    p.kill()
                for p in procs:
                    p.wait(timeout=30)
        thang = ket.count("WIN")
        self.assertEqual(thang, 1, f"{thang}/{self.SO_CON} tiến trình cùng thắng: {ket[:8]}")
        self.assertEqual(ket.count("LOSE"), self.SO_CON - 1, ket[:8])

    def test_tha_roi_thi_nguoi_sau_gianh_duoc(self):
        """Khoá phải **nhả** khi tiến trình chết, nếu không một lần crash là
        khoá vĩnh viễn cho tới khi có người xoá tệp bằng tay."""
        with tempfile.TemporaryDirectory() as d:
            ma = CON % {"root": str(ROOT), "root_run": d, "giu": 0}
            for lan in range(3):
                out = subprocess.run([sys.executable, "-c", ma], capture_output=True,
                                     text=True, encoding="utf-8", errors="replace", timeout=60).stdout.strip()
                self.assertEqual(out.splitlines()[0], "WIN", f"lượt {lan + 1}: {out!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
