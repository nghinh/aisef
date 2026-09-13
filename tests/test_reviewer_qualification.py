"""Bảng chứng nhận **phán quyết** của reviewer (ADR-009 O1) — mỗi lớp trong
`reviewer_qual.CLASSES` có **ba control**, đúng ba control của bảng cổng
(`tests/test_gate_qualification.py`, ADR-005 V9):

* `test_positive*` — bằng chứng tốt → lớp ấy được gọi ra, kèm lý do có chữ;
* `test_negative*` — bằng chứng đột biến → **không** ra lớp ấy, mà ra lớp đúng;
* `test_env*` — thiếu bằng chứng để kết luận → `undecided` có lý do, hay lớp
  khác có lý do — không bao giờ là một `pass` im lặng.

`reviewer_qual.qualification_table()` đọc tệp này bằng AST (lớp có `TEN`, ba
tiền tố phương thức) qua **cùng** bộ đọc với bảng cổng (`gate.controls_in`).
Test meta ở cuối trượt khi một lớp thiếu control, khi `classify` trả tên ngoài
`CLASSES`, hay khi một lý do rỗng.

Hàng ở đây là hàng **tổng hợp**: các control chấm `classify`, không chấm corpus.
Hai phép kiểm cuối chấm hai chỗ có I/O thật: đọc phiên từ `evidence/*.jsonl`
và hỏi git "giữa hai ứng viên đổi những tệp nào".
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.findings import Finding, SOURCE_REVIEWER, Trust  # noqa: E402
from aisef.control.gate import CONTROLS  # noqa: E402
from aisef.control.reviewer_qual import (  # noqa: E402
    CLASSES, Judgement, changed_between, classify, judgements, qualification_table, rates,
)
from aisef.harness.observe import AGENT_RUN, NOTE, Event, EvidenceStore  # noqa: E402

#: Lý do `tests verify story` trượt vì **code**, không vì thiếu bằng chứng.
NOP_THAT = "tests verify nothing — still green without story code (parent SHA abc1234): AC-S-01-1: x"
TEST_DO = "the most recent test run is still failing, the story cannot be finished."
XANH = (("test", "passed", ""), ("tests verify story", "passed", ""))


def hang(**kw) -> Judgement:
    """Một phán quyết lành: phiên thật, có JSON, cổng xanh, reviewer `pass`."""
    base = dict(story="S-01", attempt=1, candidate="aaa1111", seq=10, verdict="pass",
                findings=(), blocking=(), acted=(), session="ses_x", invalid="",
                gate_checks=XANH, changed_next=None, project="proj")
    base.update(kw)
    return Judgement(**base)          # type: ignore[arg-type]


def muc(file: str = "js/app.js", body: str = "AC 1 test asserts nothing") -> Finding:
    return Finding.make(source=SOURCE_REVIEWER, trust=Trust.REVIEWER.value,
                        severity="high", file=file, line=12, body=body)


def lop(*rows: Judgement) -> list[str]:
    return [c for _, c, _ in classify(list(rows))]


def ly_do(*rows: Judgement) -> list[str]:
    return [w for _, _, w in classify(list(rows))]


class Lop(unittest.TestCase):
    TEN = ""

    def assertLop(self, rows, muon):
        """Lớp của hàng **đầu** là `muon`."""
        self.assertEqual(lop(*rows)[0], muon)
        self.assertTrue(ly_do(*rows)[0].strip(), "lớp nào cũng phải có lý do")


class TestCleanPass(Lop):
    TEN = "clean pass"

    def test_positive_cong_dong_y(self):
        self.assertLop([hang()], "clean pass")

    def test_negative_cong_truot_muc_trong_hop_dong(self):
        self.assertLop([hang(gate_checks=(("tests verify story", "failed", NOP_THAT),))], "miss")

    def test_env_khong_co_gate_verdict_thi_khong_phai_pass_sach(self):
        self.assertLop([hang(gate_checks=None)], "undecided")


class TestMiss(Lop):
    TEN = "miss"

    def test_positive_pass_ung_vien_ma_nop_control_bat(self):
        r = hang(gate_checks=(("test", "passed", ""), ("tests verify story", "failed", NOP_THAT)))
        self.assertLop([r], "miss")
        self.assertIn("tests verify story", ly_do(r)[0])

    def test_negative_muc_truot_vi_thieu_bang_chung_khong_phai_sot(self):
        # `tests verify story` cũng FAILED, nhưng lý do là "không có lần chạy
        # test ở ứng viên" — không ai biết code sai hay không.
        r = hang(gate_checks=(("tests verify story", "failed",
                               "no test run at candidate — cannot determine which tests are green"),))
        self.assertLop([r], "clean pass")

    def test_env_khong_kiem_duoc_thi_khong_phai_sot(self):
        # UNRUNNABLE chặn cổng nhưng nói "không chạy được": không phải lỗi bỏ sót.
        r = hang(gate_checks=(("preservation", "unrunnable",
                               "cannot verify at candidate aaa: AC-S-02-1 — no test with code"),))
        self.assertLop([r], "clean pass")
        self.assertIn("unrunnable", ly_do(r)[0])


class TestBlockCorroborated(Lop):
    TEN = "block corroborated"

    def test_positive_tang_may_cung_truot(self):
        r = hang(verdict="block", blocking=(muc(),), acted=("[block] js/app.js:12 — x",),
                 gate_checks=(("test", "failed", TEST_DO), ("review", "failed", "1 blocking item")))
        self.assertLop([r], "block corroborated")
        self.assertIn("test", ly_do(r)[0])

    def test_negative_chi_review_truot_thi_khong_co_ai_xac_nhan(self):
        r = hang(verdict="block", blocking=(muc(),),
                 gate_checks=(("test", "passed", ""), ("review", "failed", "1 blocking item")))
        self.assertLop([r], "block uncorroborated")

    def test_env_muc_duong_ong_truot_khong_xac_nhan_duoc_gi(self):
        # `guard ran` trượt = guard không chạy tới; nó không nói code sai.
        r = hang(verdict="block", blocking=(muc(),),
                 gate_checks=(("guard ran", "failed", "no guard event recorded"),
                              ("review", "failed", "1 blocking item")))
        self.assertLop([r], "block uncorroborated")


class TestBlockUncorroborated(Lop):
    TEN = "block uncorroborated"

    def test_positive_mot_minh_review_chan_va_khong_gi_dao_lai(self):
        r = hang(verdict="block", blocking=(muc(),),
                 gate_checks=(("review", "failed", "1 blocking item"),))
        self.assertLop([r], "block uncorroborated")

    def test_negative_co_tang_may_dong_y_thi_thanh_corroborated(self):
        r = hang(verdict="block", blocking=(muc(),),
                 gate_checks=(("test", "failed", TEST_DO),))
        self.assertLop([r], "block corroborated")

    def test_env_phien_sau_pass_tren_cung_cay_thi_la_false_block(self):
        a = hang(verdict="block", blocking=(muc(),), seq=10, changed_next=(),
                 gate_checks=(("review", "failed", "1 blocking item"),))
        b = hang(seq=20, attempt=2)
        self.assertLop([a, b], "false block")


class TestFalseBlock(Lop):
    TEN = "false block"

    def test_positive_dao_chieu_tren_cung_mot_cay(self):
        a = hang(verdict="block", blocking=(muc(),), seq=10, changed_next=(),
                 gate_checks=(("review", "failed", "1 blocking item"),))
        b = hang(seq=20, attempt=2)
        self.assertLop([a, b], "false block")
        self.assertIn("identical tree", ly_do(a, b)[0])

    def test_negative_tac_gia_da_sua_dung_tep_do_thi_khong_phai_chan_oan(self):
        a = hang(verdict="block", blocking=(muc(file="js/app.js"),), seq=10,
                 changed_next=("js/app.js",),
                 gate_checks=(("review", "failed", "1 blocking item"),))
        b = hang(seq=20, attempt=2, candidate="bbb2222")
        self.assertLop([a, b], "block uncorroborated")

    def test_negative_than_muc_ke_ten_tep_da_sua(self):
        # Mục trỏ tệp test (không đổi) nhưng thân mục kể `index.html` (đổi):
        # sửa index.html là đã trả lời nó — todo-oc/STORY-01-01 seq=2659.
        a = hang(verdict="block", seq=10, changed_next=("index.html",),
                 blocking=(muc(file="e2e/s.spec.js", body="resolves before index.html renders"),),
                 gate_checks=(("review", "failed", "1 blocking item"),))
        b = hang(seq=20, attempt=2, candidate="bbb2222")
        self.assertLop([a, b], "block uncorroborated")

    def test_env_hai_ung_vien_khong_phan_giai_duoc_thi_khong_ket_luan(self):
        a = hang(verdict="block", blocking=(muc(),), seq=10, changed_next=None,
                 gate_checks=(("review", "failed", "1 blocking item"),))
        b = hang(seq=20, attempt=2, candidate="bbb2222")
        self.assertLop([a, b], "block uncorroborated")
        self.assertNotIn("false", lop(a, b)[0])


class TestUndecided(Lop):
    TEN = "undecided"

    def test_positive_dong_do_harness_tu_sinh_khong_phai_phan_quyet(self):
        r = hang(session="", verdict="", acted=("no changes to review: …",))
        self.assertLop([r], "undecided")
        self.assertIn("harness", ly_do(r)[0])

    def test_negative_phien_that_co_json_va_co_cong_thi_cham_duoc(self):
        self.assertNotEqual(lop(hang())[0], "undecided")

    def test_env_phien_bi_huy_hay_khong_co_json_deu_co_ten(self):
        for r, chu in ((hang(invalid="review:immutable"), "review:immutable"),
                       (hang(verdict=""), "no JSON verdict"),
                       (hang(gate_checks=None), "no gate:verdict")):
            with self.subTest(r=chu):
                self.assertLop([r], "undecided")
                self.assertIn(chu, ly_do(r)[0])


class TestDocSoLieu(unittest.TestCase):
    """`rates` in cả hai tỉ lệ, và không cái nào trốn sau một pass."""

    def test_hai_ti_le_deu_co_va_khong_chia_cho_khong(self):
        a = hang(verdict="block", blocking=(muc(),), seq=10, changed_next=(),
                 gate_checks=(("review", "failed", "1 blocking item"),))
        b = hang(seq=20, attempt=2)
        c = hang(seq=30, attempt=3, story="S-02",
                 gate_checks=(("tests verify story", "failed", NOP_THAT),))
        so = rates(classify([a, b, c]))
        self.assertEqual(so["false block"], 1)
        self.assertEqual(so["miss"], 1)
        self.assertEqual(so["false block rate"], 1.0)
        self.assertEqual(so["miss rate"], 0.5)
        self.assertEqual(so["same-tree consecutive pairs"], 1)
        self.assertEqual(so["same-tree verdict reversals"], 1)
        self.assertEqual(rates([])["miss rate"], -1.0)      # rỗng: -1, không phải 0

    def test_id_on_dinh_gop_loi_nhac_lai_mot_lan(self):
        # Cùng (file, line, body) → cùng `Finding.id` → một mục.
        self.assertEqual(muc().id, muc().id)
        self.assertNotEqual(muc().id, muc(body="viết lại bằng từ khác").id)


class TestDocPhienTuDia(unittest.TestCase):
    """Đọc phiên review từ `evidence/*.jsonl`: ghép phiên, bắt dòng của harness."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = EvidenceStore(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _phien(self, *, sha: str, verdict: str, findings: list[dict], attempt: int,
               session: str = "ses_a", co_phien: bool = True):
        if co_phien:
            self.store.record("S-01", Event(kind=AGENT_RUN, name="S-01-review", ok=True,
                                            detail={"session_id": session, "candidate": sha}))
            self.store.record("S-01", Event(kind=NOTE, name="review:verdict", ok=True,
                                            detail={"verdict": verdict, "findings": findings,
                                                    "candidate": sha}))
        self.store.tool_run("S-01", "review", ok=not findings,
                            detail={"findings": [f"[block] {f['file']}" for f in findings
                                                 if f["tag"] == "block"],
                                    "attempt": attempt, "candidate": sha})
        self.store.record("S-01", Event(kind=NOTE, name="gate:verdict", ok=True, detail={
            "attempt": attempt, "failures": [], "candidate": sha,
            "checks": [{"name": "test", "outcome": "passed", "detail": ""}]}))

    def test_moi_phien_mot_hang_va_dong_harness_khong_co_phien(self):
        self._phien(sha="aaa", verdict="block", attempt=1, session="ses_1", findings=[
            {"tag": "block", "file": "js/a.js", "line": "3", "why": "vacuous", "behavior_id": ""},
            {"tag": "should fix", "file": "js/a.js", "line": "9", "why": "nit", "behavior_id": ""}])
        self._phien(sha="aaa", verdict="pass", attempt=2, session="ses_2", findings=[])
        self._phien(sha="aaa", verdict="", attempt=3, findings=[], co_phien=False)
        rows = judgements(self.store.read("S-01"), project="p")
        self.assertEqual([r.session for r in rows], ["ses_1", "ses_2", ""])
        self.assertEqual([len(r.findings) for r in rows], [2, 0, 0])
        self.assertEqual([len(r.blocking) for r in rows], [1, 0, 0])
        self.assertEqual([r.verdict for r in rows], ["block", "pass", ""])
        self.assertEqual(lop(*rows)[2], "undecided")

    def test_phien_bi_huy_duoc_ghi_nhan(self):
        self.store.record("S-01", Event(kind=AGENT_RUN, name="S-01-review", ok=True,
                                        detail={"session_id": "ses_1", "candidate": "aaa"}))
        self.store.tool_run("S-01", "review:immutable", ok=False, detail={"changed": ["x.py"]})
        self.store.tool_run("S-01", "review", ok=False,
                            detail={"findings": ["[block] reviewer modified the working tree"],
                                    "attempt": 1, "candidate": "aaa"})
        self.store.record("S-01", Event(kind=NOTE, name="gate:verdict", ok=False,
                                        detail={"attempt": 1, "checks": [], "candidate": "aaa"}))
        rows = judgements(self.store.read("S-01"), project="p")
        self.assertEqual(rows[0].invalid, "review:immutable")
        self.assertEqual(lop(*rows), ["undecided"])


class TestGitLaNguonSuThat(unittest.TestCase):
    """"Có sửa gì giữa hai ứng viên" hỏi git, không hỏi `file_change`."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self._git("init", "-q")
        self._git("config", "user.email", "t@t")
        self._git("config", "user.name", "t")
        (self.repo / "a.txt").write_text("1\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-qm", "one")
        self.a = self._git("rev-parse", "HEAD").strip()
        (self.repo / "b.txt").write_text("2\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-qm", "two")
        self.b = self._git("rev-parse", "HEAD").strip()

    def tearDown(self):
        self._tmp.cleanup()

    def _git(self, *args) -> str:
        # `encoding="utf-8"` là bắt buộc, không phải trang trí: `text=True` mà
        # không khai bảng mã thì runner Windows đọc cp1252 và luồng chết im
        # lặng (lỗi 99) — `tests/test_meta.py` quét đúng chỗ này.
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True,
                              text=True, encoding="utf-8", check=False).stdout

    def test_doc_dung_tep_da_doi_va_cung_cay_la_rong(self):
        self.assertEqual(changed_between(self.repo, self.a, self.b), ("b.txt",))
        self.assertEqual(changed_between(self.repo, self.a, self.a), ())

    def test_khong_phan_giai_duoc_thi_None_khong_phai_rong(self):
        # `()` nghĩa là "cùng cây" và dẫn tới kết luận false block; commit mất
        # phải trả `None` để không kết luận gì.
        self.assertIsNone(changed_between(self.repo, self.a, "0" * 40))
        self.assertIsNone(changed_between(self.repo, "", self.b))
        self.assertIsNone(changed_between(self.repo / "khong-co", self.a, self.b))


class TestBangChungNhan(unittest.TestCase):
    """Test meta: bảng đọc từ tệp này khớp `CLASSES`, `classify` không trả tên lạ."""

    def test_moi_lop_co_du_ba_control(self):
        table = qualification_table(Path(__file__))
        self.assertEqual(set(table), set(CLASSES))
        for ten, cols in table.items():
            with self.subTest(lop=ten):
                thieu = [c for c in CONTROLS if not cols[c]]
                self.assertFalse(thieu, f"lớp `{ten}` thiếu control {thieu}")

    def test_ten_TEN_trong_tep_nay_thuoc_CLASSES(self):
        import ast
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        ten = {n.value.value for cls in tree.body if isinstance(cls, ast.ClassDef)
               for n in cls.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
               and any(isinstance(t, ast.Name) and t.id == "TEN" for t in n.targets)}
        self.assertEqual(ten - {""}, set(CLASSES))

    def test_classify_chi_tra_ten_trong_CLASSES(self):
        moi = [hang(), hang(verdict="block", blocking=(muc(),)), hang(session=""),
               hang(gate_checks=None), hang(invalid="review:candidate"),
               hang(gate_checks=(("tests verify story", "failed", NOP_THAT),))]
        for r, cls, why in classify(moi):
            with self.subTest(seq=r.seq, cls=cls):
                self.assertIn(cls, CLASSES)
                self.assertTrue(why.strip())


if __name__ == "__main__":
    unittest.main()
