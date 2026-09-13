"""Gán chi tiêu vào kết cục — ADR-009 §Open O4.

Hai thứ ở đây dễ sai và sai thì không ai thấy: **đơn vị** của chi tiêu, và
**phiên nào thuộc lượt nào**. Nên test trung tâm không phải một bảng đẹp mà là
hai cái bẫy:

* nhà cung cấp trả giá cho *một phần* số phiên — lấy trung bình ra đô la là
  bịa; phải rơi về đếm token;
* một phiên chết vì trần lượt nằm ngay trước một phán quyết cổng — tính token
  của nó vào "cổng chặn" là giấu mất cái trần.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control import attribution as A  # noqa: E402
from aisef.control import ledger as L  # noqa: E402
from aisef.harness.observe import AGENT_RUN, NOTE, Event, EvidenceStore  # noqa: E402


class AttributionTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "_bmad-output"
        self.root.mkdir(parents=True)
        self.store = EvidenceStore(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def index(self, stories):
        (self.root / L.STORIES_INDEX).write_text(
            json.dumps({"stories": stories}, ensure_ascii=False), encoding="utf-8"
        )

    def agent(self, story: str, *, vao: int = 1000, ra: int = 10, cache: int = 0,
              exit_status: str = "ok", role: str = "developer", turns: int = 3,
              cost: float = 0.0) -> Event:
        return self.store.record(story, Event(
            kind=AGENT_RUN, name=story, cost_usd=cost,
            tokens={"input": vao, "output": ra, "cache_read": cache},
            detail={"turns": turns, "role": role, "exit_status": exit_status},
        ))

    def gate(self, story: str, ok: bool, failures=()) -> Event:
        return self.store.record(story, Event(
            kind=NOTE, name="gate:verdict", ok=ok,
            detail={"failures": list(failures)},
        ))

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        from aisef.cli import main

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--project", str(self.root.parent), *args])
        return code, out.getvalue(), err.getvalue()


class TestDonViChiTieu(AttributionTestCase):
    """Đô la chỉ là đơn vị khi nhà cung cấp định giá **mọi** phiên.

    Đo trên `todo` 14/09/2026: 1 trên 180 phiên có `cost_usd > 0`, 179 phiên
    còn lại báo 0. Chia tổng 0,79 USD cho 4 story ra 0,20 USD/story — sai hai
    bậc độ lớn, mà lại trông như một con số đã đo.
    """

    def test_gia_mot_phan_thi_khong_dung_do_la(self):
        self.agent("STORY-01-01", cost=0.50)
        self.agent("STORY-01-01", cost=0.0)
        att = A.build(self.root)
        self.assertEqual(att.unit, A.TOKENS)
        self.assertAlmostEqual(att.cost_coverage, 0.5)

    def test_gia_du_moi_phien_thi_dung_do_la(self):
        self.agent("STORY-01-01", cost=0.25)
        self.agent("STORY-01-01", cost=0.75)
        att = A.build(self.root)
        self.assertEqual(att.unit, A.USD)
        self.assertEqual(att.cost_coverage, 1.0)
        self.assertAlmostEqual(att.total().amount(A.USD), 1.0)

    def test_khong_co_cache_thi_bao_token_khong_so_sanh_duoc(self):
        self.agent("STORY-01-01", vao=5000, cache=0)
        att = A.build(self.root)
        self.assertEqual(att.cache_share, 0.0)
        self.assertIn("not** comparable", "\n".join(A.report_lines(att)))

    def test_co_cache_thi_dem_rieng(self):
        self.agent("STORY-01-01", vao=5000, cache=9000)
        att = A.build(self.root)
        self.assertEqual(att.total().cache_read, 9000)
        self.assertNotIn("not** comparable", "\n".join(A.report_lines(att)))

    def test_ti_le_cache_chu_khong_phai_co_hay_khong(self):
        """`todo-oc` **có** báo cache — trên 4 % token nhắc. Một cờ bật/tắt nói
        nó giống `todo-cli` (84 %), nên thứ phải đo là tỉ lệ."""
        self.agent("STORY-01-01", vao=96_000, cache=4_000)
        att = A.build(self.root)
        self.assertAlmostEqual(att.cache_share, 0.04)
        self.assertIn("not** comparable", "\n".join(A.report_lines(att)))


class TestPhienChetVi(AttributionTestCase):
    """Kết cục **của chính phiên** thắng phán quyết cổng đi sau nó.

    Đo trên `todo-oc`: `developer:max_turns | review:ok | security:ok |
    GATE=BLOCK(...)` — phiên developer bị trần lượt giết rồi cổng vẫn chấm lượt
    ấy. Nếu gán theo cổng thì 13 phiên `max_turns` của corpus đó biến thành
    "cổng chặn", và cái trần — nguyên nhân thật — không xuất hiện ở bảng nào.
    """

    def test_tran_luot_khong_bi_tinh_vao_cong_chan(self):
        self.agent("STORY-01-01", vao=9000, exit_status="max_turns")
        self.agent("STORY-01-01", vao=100, role="review")
        self.gate("STORY-01-01", False, ["review"])
        att = A.build(self.root)
        row = att.stories["STORY-01-01"]
        self.assertEqual(row.spend_of(A.TURN_CAP).input, 9000)
        self.assertEqual(row.spend_of(A.GATE_BLOCKED).input, 100)

    def test_ha_tang_chet_la_mot_lop_rieng(self):
        for trang_thai in ("infra", "error", "timeout"):
            self.agent("STORY-01-01", vao=1000, exit_status=trang_thai)
        self.agent("STORY-01-01", vao=50)
        self.gate("STORY-01-01", True)
        att = A.build(self.root)
        row = att.stories["STORY-01-01"]
        self.assertEqual(row.spend_of(A.ENV_FAILED).sessions, 3)
        self.assertEqual(row.spend_of(A.ENV_FAILED).input, 3000)
        self.assertEqual(row.spend_of(A.PASSED).input, 50)


class TestGanTheoThuTuSuKien(AttributionTestCase):
    """Gán theo thứ tự sự kiện, không theo số lượt — cùng phương pháp E4.

    Một story chạy lại thì "lượt 1" xuất hiện hai lần với hai phán quyết khác
    nhau; khoá theo số lượt sẽ dán nhãn của lần sau lên phiên của lần trước.
    """

    def test_hai_luot_hai_phan_quyet(self):
        self.agent("STORY-01-01", vao=700)
        self.gate("STORY-01-01", False, ["test", "TDD"])
        self.agent("STORY-01-01", vao=300)
        self.gate("STORY-01-01", True)
        att = A.build(self.root)
        row = att.stories["STORY-01-01"]
        self.assertEqual(row.spend_of(A.GATE_BLOCKED).input, 700)
        self.assertEqual(row.spend_of(A.PASSED).input, 300)
        self.assertEqual(row.attempts, 2)
        self.assertEqual(att.blocked_by, {"test": 1, "TDD": 1})

    def test_phien_khong_ai_cham_la_no_verdict(self):
        self.agent("STORY-01-01", vao=400)
        self.gate("STORY-01-01", False)
        self.agent("STORY-01-01", vao=600)     # chạy dở, không có phán quyết nào sau
        att = A.build(self.root)
        row = att.stories["STORY-01-01"]
        self.assertEqual(row.spend_of(A.NO_VERDICT).input, 600)
        self.assertEqual(att.blocked_by, {"unnamed": 1})

    def test_phien_pha_lap_ke_hoach_xep_rieng(self):
        self.agent("plan-prd", vao=2000, role="")
        self.agent("mockup-list", vao=1000, role="")
        self.agent("STORY-01-01", vao=500)
        self.gate("STORY-01-01", True)
        att = A.build(self.root)
        by = att.by_class()
        self.assertEqual(by[A.PLANNING].input, 3000)
        self.assertEqual(by[A.PASSED].input, 500)
        self.assertAlmostEqual(att.share(A.PLANNING), 3000 / 3500)


class TestTienMuaDuocGi(AttributionTestCase):
    def setUp(self):
        super().setUp()
        self.index([
            {"id": "STORY-01-01", "epic_id": "EPIC-01", "acceptance_criteria": ["a"]},
            {"id": "STORY-01-02", "epic_id": "EPIC-01", "acceptance_criteria": ["b"]},
        ])

    def _behaviour(self, story: str, bid: str, status: str):
        self.store.behavior(story, id=bid, status=status)

    def test_net_verified_tru_reopened(self):
        self.agent("STORY-01-01", vao=1_000_000)
        self._behaviour("STORY-01-01", "FR-1", "verified")
        self._behaviour("STORY-01-01", "FR-2", "verified")
        self._behaviour("STORY-01-01", "FR-2", "gap")        # đạt rồi hỏng -> reopened
        self.gate("STORY-01-01", True)
        att = A.build(self.root)
        self.assertEqual(att.verified, 1)
        self.assertEqual(att.reopened, 1)
        self.assertEqual(att.net_verified, 0)

    def test_net_verified_moi_trieu_token(self):
        self.agent("STORY-01-01", vao=2_000_000)
        self._behaviour("STORY-01-01", "FR-1", "verified")
        self._behaviour("STORY-01-01", "FR-2", "verified")
        self.gate("STORY-01-01", True)
        att = A.build(self.root)
        self.assertEqual(att.unit, A.TOKENS)
        self.assertAlmostEqual(att.per_unit(), 1.0)          # 2 hành vi / 2 M token

    def test_khong_tieu_gi_thi_khong_co_so(self):
        att = A.build(self.root)
        self.assertIsNone(att.per_unit())
        self.assertIn("nothing spent", "\n".join(A.report_lines(att)))

    def test_story_khong_mua_duoc_gi_nam_ngoai_phan_san_sinh(self):
        """Story chặn tới cùng: tiêu thật, hành vi ròng bằng 0."""
        self.agent("STORY-01-01", vao=300)
        self._behaviour("STORY-01-01", "FR-1", "verified")
        self.gate("STORY-01-01", True)
        self.agent("STORY-01-02", vao=700)
        self._behaviour("STORY-01-02", "FR-9", "gap")
        self.gate("STORY-01-02", False, ["review"])
        att = A.build(self.root)
        self.assertEqual(att.stories["STORY-01-02"].net_verified, 0)
        self.assertAlmostEqual(att.productive_share(), 0.3)

    def test_story_co_ke_hoach_nhung_chua_chay_van_co_dong(self):
        """Chưa chạy thì chi tiêu 0 — nhưng phải xuất hiện, không được biến mất."""
        self.agent("STORY-01-01", vao=100)
        self.gate("STORY-01-01", True)
        att = A.build(self.root)
        self.assertIn("STORY-01-02", att.stories)
        self.assertEqual(att.stories["STORY-01-02"].total().sessions, 0)


class TestLenhCost(AttributionTestCase):
    def test_in_bang_va_ghi_ra_tep(self):
        self.agent("STORY-01-01", vao=1234, exit_status="max_turns")
        self.agent("STORY-01-01", vao=10)
        self.gate("STORY-01-01", False, ["review"])
        out_path = self.root / "COST.md"
        code, out, err = self.run_cli("cost", "--out", str(out_path))
        self.assertEqual(code, 0, err)
        self.assertIn("Spend attribution", out)
        self.assertIn("turn-cap", out)
        self.assertIn("Net VERIFIED per", out)
        self.assertIn("Spend attribution", out_path.read_text(encoding="utf-8"))

    def test_khong_co_bang_chung_van_thoat_0(self):
        code, out, err = self.run_cli("cost")
        self.assertEqual(code, 0, err)
        self.assertIn("nothing spent", out)


if __name__ == "__main__":
    unittest.main()
