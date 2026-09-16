"""Bốn thuộc tính của một lần chặn **chỉ do người máy chấm** (G2.4b).

`review` là mục duy nhất trong `gate.CHECK_NAMES` do model chấm. Đo trên 145
phiên đã ghi: 21 trong 57 lần chặn chỉ dựa vào lời nó, 11 trong 20 cặp cùng
cây đảo phán quyết. Hợp đồng đóng dự án (`docs/PROJECT-CLOSURE-GATE.md` §5,
phán quyết 1 của chủ dự án) đòi bốn thuộc tính trước khi được miễn:

* **i** — nhận ra được một lần chặn chỉ-do-người-máy từ bản ghi;
* **ii** — phân biệt được với chặn tất định;
* **iii** — có đường thoát của **người**;
* **iv** — không giả dạng được thành bảo đảm tất định.

i/ii đã có sẵn (`CHECK_KIND` + `Check.as_dict` ghi `kind` vào mọi
`gate:verdict`). Tệp này chứng nhận **iii** — miễn trừ do người ký, buộc vào
đúng ứng viên — và **iv**: miễn trừ ấy không cứu được mục tất định nào, và
hiện ra là `◇ WAIVED` chứ không bao giờ là `✅ PASSED`.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.cli import EXIT_OK, EXIT_USAGE, main  # noqa: E402
from aisef.control.gate import REVIEW_WAIVER, evaluate, judge_only  # noqa: E402
from aisef.control.outcome import Outcome  # noqa: E402
from aisef.control.reviewer_qual import judge_only_audit  # noqa: E402
from aisef.harness.guardrails import ENV_STORY_ID  # noqa: E402
from aisef.harness.observe import NOTE, Event, EvidenceStore  # noqa: E402

SID = "STORY-01-01"
SHA = "0123456789abcdef0123456789abcdef01234567"
CHAN = ["[block] src/a.py:10 — mất dữ liệu khi lưu"]


class Nen(unittest.TestCase):
    """Một story, một ứng viên, test/lint xanh — chỉ reviewer chặn."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        (self.project / "docs").mkdir()
        (self.project / "docs" / "requirements.md").write_text("# yêu cầu\n", encoding="utf-8")
        self.root = self.project / "_bmad-output"
        self.store = EvidenceStore(self.root, candidate=SHA)

    def tearDown(self):
        self._tmp.cleanup()

    def kwargs(self, **over):
        kw = dict(changed=["src/a.py"], write_scope=["src"], screens=[], contract=[],
                  review_blocking=list(CHAN), candidate=SHA)
        kw.update(over)
        return kw

    def luot(self, *, lint_ok: bool = True, attempt: int = 1):
        """Một lượt như `verify_candidate` ghi: phép kiểm → gate:input → verdict."""
        self.store.file_change(SID, "src/a.py")
        self.store.tool_run(SID, "test", ok=True)
        self.store.tool_run(SID, "qa:fake-tests", ok=True, detail={"files": []})   # SS-01: the scan is always recorded
        self.store.tool_run(SID, "lint", ok=lint_ok, detail={"tail": "E501"})
        kw = self.kwargs(review_blocking=list(CHAN))
        self.store.record(SID, Event(kind=NOTE, name="gate:input",
                                     detail={**kw, "attempt": attempt}))
        g = self.cham(**kw)
        self.store.record(SID, Event(
            kind=NOTE, name="gate:verdict", ok=g.passed,
            detail={"failures": [c.name for c in g.failures], "attempt": attempt,
                    "checks": [c.as_dict() for c in g.checks]}))
        return g

    def cham(self, **over):
        return evaluate(SID, EvidenceStore(self.root).read(SID), **self.kwargs(**over))

    def muc(self, g, ten="review"):
        return next(c for c in g.checks if c.name == ten)

    def mien_tru(self, *, reason="reviewer đọc nhầm: `save` có test ở tầng trên",
                 candidate=SHA, by="nghi"):
        self.store.record(SID, Event(
            kind=NOTE, name=REVIEW_WAIVER, ok=False,
            detail={"candidate": candidate, "reason": reason, "by": by}))

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--project", str(self.project), *args])
        return code, out.getvalue(), err.getvalue()


class TestNhanRaChanChiDoNguoiMay(Nen):
    """G2.4b-i: câu hỏi "có tầng tất định nào đứng sau không" trả lời được."""

    def test_chi_review_chan_thi_la_chan_chi_do_nguoi_may(self):
        self.luot()
        self.assertTrue(judge_only(self.cham()))

    def test_co_muc_tat_dinh_cung_chan_thi_khong_phai(self):
        self.luot(lint_ok=False)
        self.assertFalse(judge_only(self.cham()))

    def test_cong_dat_thi_khong_phai(self):
        self.luot()
        self.assertFalse(judge_only(self.cham(review_blocking=[])))


class TestDuongThoatCuaNguoi(Nen):
    """G2.4b-iii: người ký được, và cổng đọc chữ ký ấy."""

    def test_mien_tru_bien_review_thanh_waived_chu_khong_thanh_passed(self):
        self.luot()
        self.assertIs(self.muc(self.cham()).outcome, Outcome.FAILED)
        self.mien_tru()
        m = self.muc(self.cham())
        self.assertIs(m.outcome, Outcome.WAIVED)
        self.assertFalse(m.outcome.blocks)
        self.assertTrue(m.outcome.counts_as_done)
        self.assertEqual(m.outcome.mark, "◇")
        self.assertIn("nghi", m.detail)
        self.assertIn("đọc nhầm", m.detail)
        self.assertEqual(m.kind, "model-judge")
        self.assertTrue(m.evidence, "mục miễn trừ phải trỏ về sự kiện đã ghi")

    def test_khong_co_muc_chan_thi_mien_tru_khong_doi_gi(self):
        """Miễn trừ không biến một `pass` thành `waived`: không có gì để miễn."""
        self.luot()
        self.mien_tru()
        self.assertIs(self.muc(self.cham(review_blocking=[])).outcome, Outcome.PASSED)

    def test_mien_tru_o_ung_vien_khac_khong_tinh(self):
        """Buộc vào ứng viên: người đọc **bản dựng ấy**, không phải bản sau."""
        self.luot()
        self.mien_tru(candidate="f" * 40)
        self.assertIs(self.muc(self.cham()).outcome, Outcome.FAILED)

    def test_mien_tru_khong_ly_do_khong_tinh(self):
        """Miễn trừ không lý do là miễn trừ không đọc được — bỏ qua."""
        self.luot()
        self.mien_tru(reason="   ")
        self.assertIs(self.muc(self.cham()).outcome, Outcome.FAILED)


class TestKhongGiaDangDuoc(Nen):
    """G2.4b-iv: miễn trừ chỉ chạm đúng mục `review`."""

    def test_mien_tru_khong_cuu_duoc_mot_muc_tat_dinh(self):
        self.luot(lint_ok=False)
        self.mien_tru()
        g = self.cham()
        self.assertIs(self.muc(g, "review").outcome, Outcome.WAIVED)
        self.assertIs(self.muc(g, "lint").outcome, Outcome.FAILED)
        self.assertFalse(g.passed, "mục tất định vẫn phải chặn")

    def test_ban_ghi_noi_ro_waived_chu_khong_noi_passed(self):
        self.luot()
        self.mien_tru()
        d = self.muc(self.cham()).as_dict()
        self.assertEqual(d["outcome"], "waived")
        self.assertEqual(d["kind"], "model-judge")
        self.assertTrue(d["skipped"], "waived là bỏ qua có chữ ký, không phải đạt")


class TestLenhKyMienTru(Nen):
    """Đường thoát phải **gọi được**: một lệnh người gõ, không phải một hàm."""

    def _da_cham(self):
        self.luot()

    def test_thieu_ly_do_la_loi_dung_lenh(self):
        self._da_cham()
        code, _, err = self.run_cli("gate", SID, "--waive-review")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("--reason", err)

    def test_trong_phien_agent_thi_tu_choi(self):
        """Agent không tự ký miễn trừ cho chính mình — `AISEF_STORY_ID` là dấu."""
        self._da_cham()
        with mock.patch.dict(os.environ, {ENV_STORY_ID: SID}):
            code, _, err = self.run_cli("gate", SID, "--waive-review", "--reason", "x")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn(ENV_STORY_ID, err)

    def test_review_khong_chan_thi_khong_co_gi_de_mien(self):
        self.store.file_change(SID, "src/a.py")
        self.store.record(SID, Event(kind=NOTE, name="gate:input",
                                     detail={**self.kwargs(review_blocking=[]), "attempt": 1}))
        code, _, err = self.run_cli("gate", SID, "--waive-review", "--reason", "x")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("review", err)

    def test_ghi_xong_thi_cong_cham_lai_ra_waived(self):
        self._da_cham()
        with mock.patch.dict(os.environ, {"AISEF_APPROVER": "nghi"}, clear=False):
            os.environ.pop(ENV_STORY_ID, None)
            code, out, err = self.run_cli("gate", SID, "--waive-review",
                                          "--reason", "reviewer đọc nhầm")
        self.assertEqual(code, EXIT_OK, err)
        self.assertIn(SHA[:7], out)
        e = EvidenceStore(self.root).read(SID).last(NOTE, REVIEW_WAIVER)
        self.assertIsNotNone(e)
        self.assertEqual(e.detail["candidate"], SHA)
        self.assertEqual(e.detail["by"], "nghi")
        self.assertIs(self.muc(self.cham()).outcome, Outcome.WAIVED)


class TestBangKiemTraG24b(unittest.TestCase):
    """Bản kiểm tra máy đọc được — `closure-evidence/judge-only-audit.json`."""

    def test_bon_thuoc_tinh_deu_duoc_cham_va_json_hoa_duoc(self):
        a = judge_only_audit()
        self.assertEqual(sorted(a["properties"]), ["G2.4b-i", "G2.4b-ii", "G2.4b-iii", "G2.4b-iv"])
        for pid, p in a["properties"].items():
            with self.subTest(thuoc_tinh=pid):
                self.assertTrue(p["assertions"], "thuộc tính không có phép kiểm nào")
                self.assertEqual(p["holds"], all(ok for _, ok in p["assertions"]))
        self.assertEqual(a["all_hold"], all(p["holds"] for p in a["properties"].values()))
        self.assertTrue(a["all_hold"], json.dumps(a["properties"], ensure_ascii=False, indent=1))
        json.dumps(a)

    def test_do_duoc_tren_bang_chung_da_ghi(self):
        """Phần `measured` đếm từ `gate:verdict` trên đĩa, không gọi model."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "_bmad-output"
            store = EvidenceStore(root, candidate=SHA)
            store.record(SID, Event(kind=NOTE, name="gate:verdict", ok=False, detail={
                "failures": ["review"], "attempt": 1,
                "checks": [{"name": "review", "outcome": "failed", "kind": "model-judge"},
                           {"name": "lint", "outcome": "passed", "kind": "deterministic"}]}))
            store.record(SID, Event(kind=NOTE, name="gate:verdict", ok=False, detail={
                "failures": ["review", "lint"], "attempt": 2,
                "checks": [{"name": "review", "outcome": "failed", "kind": "model-judge"},
                           {"name": "lint", "outcome": "failed", "kind": "deterministic"}]}))
            m = judge_only_audit({"tmp": root})["measured"]
        self.assertEqual(m["gate_records"], 2)
        self.assertEqual(m["blocking_records"], 2)
        self.assertEqual(m["judge_only_records"], 1)
        self.assertEqual(m["checks_without_kind"], 0)
        self.assertEqual(m["checks_by_kind"]["model-judge"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
