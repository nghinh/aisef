"""Sức phân biệt theo task (`validation/bench_discriminating_power.py`).

Dữ liệu thật của hai cohort nằm ở `.bench*/` — gitignore, nên phép thử này dựng
một sổ **giả** trong thư mục tạm. Nó ghim hai thứ mà một phép đọc sai sẽ làm
lệch cả bảng: quy ước "dòng cuối thắng" khi một lượt có nhiều dòng, và việc một
FAIL vì hạ tầng bị loại khỏi phép so trong khi một PASS sau phiên bị cắt thì
không.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from validation import bench_discriminating_power as D  # noqa: E402


def _luot(task, client, attempt, outcome, **kw):
    return {"task_id": task, "client": client, "attempt": attempt, "outcome": outcome,
            "cost_usd": 0.0, "turns": 5, "duration_ms": 1000, "error": "", **kw}


class TestTuKiem(unittest.TestCase):
    def test_tu_kiem_cua_script_chay_duoc(self):
        D.tu_kiem()          # mọi assert ở đó là hợp đồng của script, chạy tại đây luôn


class TestDocSo(unittest.TestCase):
    """`thu_thap` trên một sổ giả: hai task, hai điều kiện, có dòng trùng."""

    def _so(self, tmp: Path, rows: list[dict]) -> Path:
        so = tmp / ".bench-gia"
        so.mkdir()
        (so / "results.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        return so

    def test_dong_cuoi_thang_va_ha_tang_bi_loai(self):
        rows = [
            # `t-tran`: hai nhánh đều PASS → 0 cặp có thông tin.
            *[_luot("bug-19", c, n, "PASS") for c in ("claude", "claude-bare") for n in (1, 2)],
            # `t-phanbiet` lượt 1 của nhánh AISEF ghi hai lần: FAIL rồi PASS.
            _luot("bug-20", "claude", 1, "FAIL"),
            _luot("bug-20", "claude", 1, "PASS"),
            _luot("bug-20", "claude", 2, "PASS"),
            _luot("bug-20", "claude-bare", 1, "FAIL"),
            # FAIL vì hết 1800 s: hạ tầng, không phải phán quyết của agent.
            _luot("bug-20", "claude-bare", 2, "FAIL", error="exceeded 1800s"),
        ]
        with tempfile.TemporaryDirectory() as td:
            so = self._so(Path(td), rows)
            sach, ghi_chu = D.thu_thap([so], ROOT / "tests" / "bench" / "tasks",
                                       loai_bo_ha_tang=True)
            tho, _ = D.thu_thap([so], ROOT / "tests" / "bench" / "tasks",
                                loai_bo_ha_tang=False)
        self.assertEqual(ghi_chu, [f"`{so}/run/` không còn cây làm việc — "
                                   "cột token của sổ này rỗng."])

        tran = sach["bug-19"][0]
        self.assertEqual((tran["n_a"], tran["n_b"], tran["co_thong_tin"], tran["D"]),
                         (2, 2, 0, 0.0))

        pb = sach["bug-20"][0]
        # Dòng cuối thắng: lượt 1 của nhánh AISEF là PASS, nên 2/2 PASS.
        self.assertEqual((pb["ghi_a"], pb["luot_a"], pb["n_a"]), (3, 2, 2))
        # Nhánh trần: lượt 1 FAIL giữ lại, lượt 2 bỏ vì hạ tầng → còn 1 lượt.
        self.assertEqual((pb["n_b"], pb["khong_dung_duoc"]), (1, 1))
        self.assertEqual((pb["cap"], pb["co_thong_tin"], pb["D"]), (2, 2, 1.0))
        self.assertEqual(D.nhom_task(sach["bug-20"]), D.PHAN_BIET)
        # Cách đọc "như đã chấm" giữ cả lượt hạ tầng lại → nhánh trần 0/2.
        self.assertEqual((tho["bug-20"][0]["n_b"], tho["bug-20"][0]["p1_b"]), (2, 0.0))

        # Task chưa từng chạy vẫn có dòng, và là `chưa đo` chứ không phải `chạm trần`.
        self.assertEqual(sach["bug-6"], [])
        self.assertEqual(D.nhom_task(sach["bug-6"]), D.CHUA_DO)

    def test_so_vang_mat_thi_neu_ten_chu_khong_bia_so(self):
        with tempfile.TemporaryDirectory() as td:
            thieu = Path(td) / ".bench-khong-co"
            sach, ghi_chu = D.thu_thap([thieu], ROOT / "tests" / "bench" / "tasks")
        self.assertIn("không có `results.jsonl`", ghi_chu[0])
        self.assertTrue(all(v == [] for v in sach.values()))


if __name__ == "__main__":
    unittest.main()
