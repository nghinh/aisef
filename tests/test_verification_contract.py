"""Hợp đồng kiểm định — "xong" nghĩa là gì cho **story này**.

Không phải một pha mới: cùng bộ máy `run_suite`, chỉ nói rõ story nào
phải qua loại nào. Bất biến quan trọng nhất giữ nguyên — `verify.X` để
trống là **chưa cấu hình**, không phải đạt.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control import gate as story_gate  # noqa: E402
from aisef.control.normalize import Story  # noqa: E402
from aisef.control.preflight import (  # noqa: E402
    BASE_CONTRACT,
    verification_contract,
)
from aisef.harness.observe import AGENT_RUN, TOOL_RUN, Evidence, Event  # noqa: E402
from aisef.phases.qa import KINDS  # noqa: E402


def story(**kw):
    base = dict(id="STORY-01-01", epic_id="EPIC-01", title="Story",
                acceptance_criteria=["Then chuyện gì đó xảy ra"],
                write_scope=["src/a.ts"])
    base.update(kw)
    return Story(**base)


class TestSuyRa(unittest.TestCase):
    def test_moi_story_deu_co_hop_dong_nen(self):
        self.assertEqual(verification_contract(story()), list(BASE_CONTRACT))

    def test_story_giao_dien(self):
        """Màn hình không dùng được bằng bàn phím là màn hình hỏng, dù mọi
        tiêu chí chấp nhận đều xanh — nên trợ năng là dấu hiệu **cấu
        trúc**, không đợi tiêu chí nhắc tới."""
        got = verification_contract(story(screens=["notes-list"]))
        for k in ("unit", "e2e", "accessibility", "mockup-map"):
            self.assertIn(k, got)

    def test_story_di_tru_du_lieu(self):
        got = verification_contract(story(
            acceptance_criteria=["Then hàm migration tiến chạy trong onupgradeneeded"]
        ))
        self.assertIn("migration", got)

    def test_story_cham_bao_mat(self):
        got = verification_contract(story(
            acceptance_criteria=["Then băm mật khẩu người dùng trước khi lưu"]
        ))
        self.assertIn("security", got)

    def test_story_co_nguong_hieu_nang(self):
        got = verification_contract(story(
            acceptance_criteria=["Then p95 dưới 200ms ở quy mô 10.000 bản ghi"]
        ))
        self.assertIn("perf", got)

    def test_nguong_khung_hinh_cung_la_hieu_nang(self):
        """"rớt khung hình", "bài đo", "ở quy mô N" đều là ngưỡng hiệu
        năng mà không dùng chữ "hiệu năng".

        Đo trên e9: TCCN 3 của STORY-01-04 đòi "bài đo AR-16 xác nhận
        ngưỡng ... ở quy mô này" và không khớp dấu hiệu nào — cổng
        `readiness` im lặng, rồi story bí ở lượt rà soát sau khi đã tiêu
        $10,49.
        """
        for cum in (
            "danh sách không rớt khung hình khi cuộn",
            "bài đo AR-16 xác nhận ngưỡng vẫn đạt ở quy mô 10.000",
            "thông lượng ghi đạt 500 bản ghi/giây",
        ):
            with self.subTest(cum=cum):
                self.assertIn("perf", verification_contract(
                    story(acceptance_criteria=[f"Then {cum}"])
                ), cum)

    def test_story_tu_khai_thi_lay_ban_khai(self):
        """Người lập kế hoạch biết thứ code không suy ra được."""
        got = verification_contract(story(
            verification_contract=["unit", "sit", "api-contract"],
            screens=["notes-list"],   # dấu hiệu cấu trúc **không** ghi đè bản khai
        ))
        self.assertEqual(got, ["unit", "sit", "api-contract"])

    def test_khong_lap_lai(self):
        got = verification_contract(story(
            screens=["a"], acceptance_criteria=["Then kịch bản E2E và trợ năng WCAG"]
        ))
        self.assertEqual(len(got), len(set(got)))

    def test_moi_loai_deu_co_that_trong_bo_kiem_dinh(self):
        """Hợp đồng nêu một loại không tồn tại thì không ai chạy được nó."""
        got = verification_contract(story(
            screens=["a"],
            acceptance_criteria=["Then migration chạy, p95 dưới 200ms, trợ năng WCAG"],
        ))
        for k in got:
            if k == "mockup-map":
                continue  # cổng riêng, không phải một loại của `run_suite`
            self.assertIn(k, KINDS, k)


class TestCong(unittest.TestCase):
    def evidence(self, **tools):
        ev = Evidence(story_id="STORY-01-01")
        ev.events.append(Event(kind=AGENT_RUN, name="x", ok=True, seq=1))
        seq = 2
        for name, (ok, detail) in tools.items():
            ev.events.append(Event(kind=TOOL_RUN, name=name, ok=ok,
                                   detail=detail or {}, seq=seq))
            seq += 1
        return ev

    def gate(self, contract, ev=None):
        return story_gate.evaluate(
            "STORY-01-01", ev or self.evidence(), changed=[],
            write_scope=["src"], screens=[], contract=contract, review_blocking=[],
        )

    def muc(self, g, ten):
        return next((c for c in g.checks if c.name == ten), None)

    def test_chua_cau_hinh_la_bo_qua_co_ghi_lai_khong_phai_dat_am_tham(self):
        """Bất biến của cả dự án: chưa chạy ≠ đạt."""
        g = self.gate(["unit", "e2e"])
        m = self.muc(g, "e2e")
        self.assertTrue(m.skipped)
        self.assertIn("does not count as passed", m.detail)

    def test_loai_da_chay_va_do_thi_chan(self):
        ev = self.evidence(e2e=(False, {"tail": "3 kịch bản đỏ"}))
        g = self.gate(["e2e"], ev)
        self.assertFalse(self.muc(g, "e2e").passed)
        self.assertFalse(g.passed)

    def test_loai_da_chay_va_xanh_thi_dat(self):
        ev = self.evidence(e2e=(True, {}))
        self.assertTrue(self.muc(self.gate(["e2e"], ev), "e2e").passed)

    def test_cong_cu_thieu_tren_may_duoc_ghi_la_bo_qua(self):
        ev = self.evidence(perf=(True, {"skipped": "chưa cài k6"}))
        m = self.muc(self.gate(["perf"], ev), "perf")
        self.assertTrue(m.skipped)
        self.assertIn("k6", m.detail)

    def test_loai_da_co_muc_rieng_khong_bi_lap(self):
        g = self.gate(["unit", "mockup-map", "security"])
        for ten in ("unit",):
            self.assertIsNone(self.muc(g, ten))

    def test_khong_co_hop_dong_thi_cong_khong_doi_gi_them(self):
        truoc = len(self.gate([]).checks)
        sau = len(self.gate(["e2e", "perf"]).checks)
        self.assertEqual(sau - truoc, 2)


class TestGhiVaoStory(unittest.TestCase):
    def test_hop_dong_hien_trong_tep_story_cho_agent_doc(self):
        from aisef.phases.story_split import render_story

        body = render_story(story(screens=["notes-list"]), None)
        self.assertIn("Definition of Done", body)
        self.assertIn("`accessibility`", body)
        self.assertIn("not** counted as passing", body)


if __name__ == "__main__":
    unittest.main()
