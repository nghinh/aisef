"""Máy tắt giữa phiên agent — bằng chứng còn, trạng thái đúng, không mất lượt.

Đợt 4 mục 4.1. Hai phép thử, cố ý khác nhau về mức độ thật:

* một tiến trình **bị SIGKILL thật** trong lúc ghi bằng chứng — trả lời "tệp
  còn đọc được không";
* một tệp bằng chứng cụt đúng kiểu ấy chạy qua phần đếm lượt — trả lời "lượt
  dở dang có bị tính thành lượt đã dùng không".

Hai câu ấy là toàn bộ nội dung của DoD; phần còn lại (`git worktree` mồ côi)
đã có phép thử riêng ở `test_worktree.py`.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.harness.observe import AGENT_RUN, Event, EvidenceStore, NOTE, TOOL_RUN  # noqa: E402

#: Con: ghi sự kiện liên tục cho tới khi bị giết. Không bắt tín hiệu — mục đích
#: là *không* có cơ hội dọn dẹp, giống máy mất điện.
CON = """
import sys, time
sys.path.insert(0, %(root)r)
from aisef.harness.observe import Event, EvidenceStore, TOOL_RUN
store = EvidenceStore(%(kho)r)
i = 0
while True:
    i += 1
    store.record("STORY-01-01", Event(kind=TOOL_RUN, name="test", ok=True,
                                      detail={"i": i, "đệm": "x" * 400}))
"""


class TestGietGiuaChungThiBangChungVanDocDuoc(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "_bmad-output"

    def tearDown(self):
        self._tmp.cleanup()

    def test_sigkill_giua_luc_ghi_khong_lam_hong_so(self):
        ma = CON % {"root": str(ROOT), "kho": str(self.root)}
        proc = subprocess.Popen([sys.executable, "-c", ma])
        try:
            path = self.root / "evidence" / "STORY-01-01.jsonl"
            han = time.time() + 30
            while time.time() < han and not (path.is_file() and path.stat().st_size > 20_000):
                time.sleep(0.05)
            self.assertTrue(path.is_file(), "con chưa kịp ghi gì")
            # `proc.kill()` chứ không `os.kill(..., SIGKILL)`: trên Windows
            # không có SIGKILL, và phép thử này phải chạy ở cả ba hệ.
            proc.kill()
        finally:
            proc.wait(timeout=30)

        # Đọc lại: không được ném, và phải còn gần hết số sự kiện đã ghi.
        ev = EvidenceStore(self.root).read("STORY-01-01")
        self.assertGreater(len(ev.events), 10)
        so = [e.detail.get("i") for e in ev.events]
        self.assertEqual(so, sorted(so), "thứ tự sự kiện phải giữ nguyên")
        # Dòng cuối có thể cụt — mất **tối đa một** sự kiện, không mất cả tệp.
        tho = path.read_text(encoding="utf-8", errors="replace").splitlines()
        self.assertLessEqual(len(tho) - len(ev.events), 1,
                             "một dòng cụt không được làm mất dòng nào khác")

    def test_ghi_tiep_sau_khi_giet_khong_de_len_so_cu(self):
        """Chạy lại phải **nối tiếp**, không mở sổ mới: bằng chứng của lượt
        trước là thứ người rà soát đọc."""
        store = EvidenceStore(self.root)
        for i in range(3):
            store.record("STORY-01-01", Event(kind=TOOL_RUN, name="test", ok=True,
                                              detail={"i": i}))
        truoc = len(store.read("STORY-01-01").events)
        EvidenceStore(self.root).record(
            "STORY-01-01", Event(kind=AGENT_RUN, name="STORY-01-01#2", ok=True))
        sau = store.read("STORY-01-01")
        self.assertEqual(len(sau.events), truoc + 1)
        self.assertEqual([e.seq for e in sau.events], list(range(1, truoc + 2)),
                         "seq phải chạy tiếp, không đánh số lại từ 1")


class TestLuotDoDangKhongBiTinhLaLuotDaDung(unittest.TestCase):
    """Lượt bị giết **trước khi có phán quyết** không được tính là lượt đã
    dùng — nếu tính, một lần mất điện ăn mất một lượt trả tiền của story."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "_bmad-output"
        store = EvidenceStore(self.root)
        store.record("STORY-01-01", Event(kind=NOTE, name="gate:input", ok=True,
                                          detail={"attempt": 1}))
        store.record("STORY-01-01", Event(kind=AGENT_RUN, name="STORY-01-01#1", ok=True,
                                          detail={"turns": 5}))
        store.record("STORY-01-01", Event(kind=NOTE, name="gate:verdict", ok=False,
                                          detail={"attempt": 1, "failures": ["review"]}))
        store.record("STORY-01-01", Event(kind=AGENT_RUN, name="STORY-01-01#2", ok=True,
                                          detail={"turns": 3}))
        # … rồi máy tắt: lượt 2 không có `gate:verdict`, và dòng cuối cụt.
        path = self.root / "evidence" / "STORY-01-01.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write('{"kind": "tool_run", "name": "te')

    def tearDown(self):
        self._tmp.cleanup()

    def test_dong_cut_khong_lam_mat_su_kien_nao_khac(self):
        ev = EvidenceStore(self.root).read("STORY-01-01")
        self.assertEqual(len(ev.events), 4)

    def test_luot_bi_giet_khong_bi_xep_la_qua_cong(self):
        from aisef.cli.implement import _attempt_breakdown
        lop, muc, story = _attempt_breakdown(EvidenceStore(self.root))
        self.assertEqual(lop.get("passed", 0), 0, lop)
        self.assertEqual(lop.get("gate"), 1, lop)
        self.assertEqual(muc, {"review": 1})
        self.assertEqual(story, {"STORY-01-01": 2})

    def test_luot_bi_giet_hien_ra_la_khong_ghi_duoc_trang_thai(self):
        """Nó **phải** hiện ra ở đâu đó: một lượt biến mất khỏi bảng là một lượt
        không ai đi tìm. `unrecorded` là tên đúng — không đoán hộ nguyên nhân."""
        from aisef.cli.implement import _attempt_breakdown
        lop, _muc, _story = _attempt_breakdown(EvidenceStore(self.root))
        self.assertEqual(lop.get("unrecorded"), 1, lop)
        self.assertEqual(sum(lop.values()), 2, lop)


if __name__ == "__main__":
    unittest.main(verbosity=2)
