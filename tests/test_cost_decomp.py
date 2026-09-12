"""Phân rã chi phí: gán token vào đúng lượt, kể cả khi story chạy lại."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from framework.bench.cost_decomp.__main__ import (  # noqa: E402
    doc, ly_do_chan, phan_vai, report, theo_ket_cuc, theo_vai)


def _agent(story: str, name: str, vao: int, ra: int) -> dict:
    return {"kind": "agent_run", "name": name, "ok": True, "_story": story,
            "tokens": {"input": vao, "output": ra, "cache_read": 0}, "detail": {"turns": 3}}


def _gate(story: str, ok: bool, attempt: int, failures=()) -> dict:
    return {"kind": "note", "name": "gate:verdict", "ok": ok, "_story": story,
            "detail": {"attempt": attempt, "failures": list(failures)}}


class TestPhanVai(unittest.TestCase):
    def test_doc_vai_tu_ten_phien(self):
        self.assertEqual(phan_vai("STORY-01-02#3"), "developer")
        self.assertEqual(phan_vai("STORY-01-02-review"), "reviewer")
        self.assertEqual(phan_vai("STORY-01-02-security"), "security")
        self.assertEqual(phan_vai("plan-EPIC-01"), "khác")


class TestGanTheoThuTuChuKhongTheoSoLuot(unittest.TestCase):
    """Một story chạy lại thì "lượt 1" xuất hiện hai lần với hai phán quyết.

    Khoá theo số lượt sẽ dán nhãn của lần chạy sau lên phiên của lần chạy
    trước — token của một lượt bị chặn sẽ bị tính là token đã mua được gì đó.
    """

    def setUp(self):
        self.events = [
            _agent("S", "S#1", 100, 10),          # lần chạy A, lượt 1
            _agent("S", "S-review", 50, 5),
            _gate("S", False, 1, ["review"]),     # … bị chặn
            _agent("S", "S#1", 200, 20),          # lần chạy B, **cũng là lượt 1**
            _gate("S", True, 1),                  # … cho qua
            _agent("S", "S#2", 7, 1),             # chưa có phán quyết nào theo sau
        ]

    def test_hai_lan_chay_cung_so_luot_khong_lan_nhan(self):
        ra = theo_ket_cuc(self.events)
        self.assertEqual(ra["lượt bị cổng chặn"]["in"], 150)
        self.assertEqual(ra["lượt bị cổng chặn"]["phien"], 2)
        self.assertEqual(ra["lượt cổng cho qua"]["in"], 200)
        self.assertEqual(ra["chưa tới cổng"]["in"], 7)

    def test_moi_phien_duoc_dem_dung_mot_lan(self):
        ra = theo_ket_cuc(self.events)
        self.assertEqual(sum(v["phien"] for v in ra.values()),
                         sum(1 for d in self.events if d["kind"] == "agent_run"))

    def test_token_theo_vai_cong_lai_bang_tong(self):
        tv = theo_vai(self.events)
        self.assertEqual(sum(v["in"] for v in tv.values()), 357)
        self.assertEqual(tv["reviewer"]["in"], 50)

    def test_dem_ly_do_chan(self):
        self.assertEqual(ly_do_chan(self.events), {"review": 1})


class TestDocTuDia(unittest.TestCase):
    def test_doc_va_bao_cao_tu_cay_that(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ev = root / "_bmad-output" / "evidence"
            ev.mkdir(parents=True)
            (ev / "STORY-01-01.jsonl").write_text(
                "\n".join(json.dumps({k: v for k, v in e.items() if k != "_story"})
                          for e in (_agent("S", "S#1", 100, 10), _gate("S", False, 1, ["review"]))),
                encoding="utf-8")
            events = doc(root)
            self.assertEqual([e["_story"] for e in events], ["STORY-01-01"] * 2)
            ra = report(root)
        self.assertIn("lượt bị cổng chặn", ra)
        self.assertIn("không trả về chi phí", ra)   # cost_usd = 0 thì không bịa ra đô la

    def test_khong_co_bang_chung_thi_noi_ra_chu_khong_no(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIn("Không có bằng chứng", report(Path(d)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
