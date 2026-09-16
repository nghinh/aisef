"""Bảng chứng nhận cổng story (ADR-005 V9, T10) — mỗi tên trong `gate.CHECK_NAMES`
có **ba control**, theo Inspect `tests/scorer/*` và TB oracle/nop:

* `test_positive*` — bằng chứng tốt → PASSED, hoặc NOT_APPLICABLE có lý do;
* `test_negative*` — bằng chứng xấu / đột biến → FAILED (mục mà thiết kế không
  có FAILED thì phải **chặn**, và test nói vì sao);
* `test_env*` — môi trường hay cấu hình không cho kết luận → kết cục **có tên**
  (UNRUNNABLE/UNCONFIGURED `must_be_named`), hay khi thiết kế mục không có kết
  cục ấy thì là kết cục ở cột "khi không có bằng chứng" SOLUTION §12, có lý do
  — không bao giờ là PASSED im lặng.

`gate.qualification_table()` đọc tệp này bằng AST (lớp có `TEN`, ba tiền tố
phương thức) — báo cáo nghiệm thu in "mục cổng có đủ 3 control: n/N" từ đó.
Test meta ở cuối trượt khi một tên thiếu control, khi `gate.py` gọi `Check(...)`
với tên ngoài `CHECK_NAMES`, hay khi `CHECK_KIND` lệch bảng.

Mỗi control cũng kiểm **con trỏ** `evidence`: mục đọc sự kiện nào thì trỏ
đúng `seq` ấy; mục suy từ tham số (`phạm vi ghi`, `bảo mật`, `rà soát`) trỏ
rỗng — và rỗng là điều được khai.
"""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.gate import CHECK_KIND, CHECK_NAMES, CONTROLS, evaluate, qualification_table  # noqa: E402
from aisef.control.outcome import CHECK_KINDS, Outcome  # noqa: E402
from aisef.control.security import Finding, SecurityReport  # noqa: E402
from aisef.harness.observe import GUARD_SEEN, MOCKUP_MAP, TOOL_RUN, Event, EvidenceStore  # noqa: E402

GATE_PY = ROOT / "aisef" / "control" / "gate.py"


class Muc(unittest.TestCase):
    """Nền chung: một kho bằng chứng tạm, story `S-01`, cổng với tham số lành."""

    TEN = ""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = EvidenceStore(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def kho(self, sha: str = "") -> EvidenceStore:
        return EvidenceStore(self._tmp.name, candidate=sha) if sha else self.store

    def xanh(self, sha: str = "", ids=None, **detail) -> Event:
        """Sửa tệp → test → lint; trả sự kiện `test`. `failed_ids` làm test đỏ."""
        st = self.kho(sha)
        st.file_change("S-01", "src/a.py")
        d = dict(detail)
        if ids is not None:
            d.setdefault("test_format", "pytest")
            d["test_ids"] = list(ids)
        t = st.tool_run("S-01", "test", ok=not d.get("failed_ids"), detail=d)
        st.tool_run("S-01", "lint", ok=True)
        return t

    def gate(self, **kw):
        p = {"changed": ["src/a.py"], "write_scope": ["src"], "screens": [], "review_blocking": []}
        p.update(kw)
        return evaluate("S-01", self.store.read("S-01"), **p)

    def muc(self, g, ten: str | None = None):
        ten = ten or self.TEN
        return next(c for c in g.checks if c.name == ten)


class TestBangChungDungCandidate(Muc):
    """ADR-004 R1. Thiết kế không có FAILED: kết quả ở bản khác là **stale**
    (⚠ UNRUNNABLE — chạy lại, không phải sửa mã), nên control negative kiểm
    rằng nó chặn và không cho mục khác mượn kết quả của bản cũ."""

    TEN = "evidence matches candidate"

    def test_positive_moi_phep_kiem_o_dung_sha(self):
        t = self.xanh(sha="aaa")
        m = self.muc(self.gate(candidate="aaa"))
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertIn(t.seq, m.evidence)
        m = self.muc(self.gate())
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)
        self.assertIn("no candidate passed", m.detail)

    def test_negative_ket_qua_o_ban_cu_khong_lam_muc_khac_dat(self):
        self.xanh(sha="bbb")
        g = self.gate(candidate="aaa")
        self.assertTrue(self.muc(g).outcome.blocks)
        self.assertIn("test", [c.name for c in g.failures], "lần test ở bbb không được dùng cho aaa")

    def test_env_stale_la_unrunnable_neu_dung_hai_sha(self):
        """F1 (INV-A.2/D.1): freshness, not recency, decides. A check with no record for THIS candidate but a
        record at another SHA is stale — named with both SHAs, pointing at the foreign record."""
        self.xanh(sha="aaa")                                   # test + lint at aaa
        self.kho("bbb").tool_run("S-01", "test", ok=True)      # bbb: a test run, no lint run
        cu = [e for e in self.store.read("S-01").events if e.name == "lint"][-1]
        m = self.muc(self.gate(candidate="bbb"))
        self.assertIs(m.outcome, Outcome.UNRUNNABLE)
        self.assertTrue(m.outcome.must_be_named)
        self.assertIn("bbb", m.detail)
        self.assertIn("aaa", m.detail)
        self.assertEqual(m.evidence, [cu.seq], "trỏ đúng sự kiện stale, không trỏ cả tệp")

    def test_env_ban_ghi_cu_dung_candidate_van_hop_le_du_co_ban_ghi_moi_o_sha_khac(self):
        """The inverse (CF-06): a record fresh for this candidate stays valid however many records of OTHER
        builds were appended later — sequence is audit metadata, never correctness."""
        self.xanh(sha="aaa")
        self.kho("bbb").tool_run("S-01", "test", ok=True)
        m = self.muc(self.gate(candidate="aaa"))
        self.assertIs(m.outcome, Outcome.PASSED, m.detail)


class TestGuardCoChay(Muc):
    TEN = "guard ran"

    def setUp(self):
        super().setUp()
        self.store.tool_run("S-01", "test", ok=True)
        self.store.tool_run("S-01", "lint", ok=True)

    def test_positive_mot_dau_vet_la_du(self):
        e = self.store.record("S-01", Event(kind=GUARD_SEEN, name="git-stage"))
        m = self.muc(self.gate(guard_expected=True))
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertEqual(m.evidence, [e.seq])

    def test_negative_ky_vong_ma_khong_dau_vet(self):
        m = self.muc(self.gate(guard_expected=True))
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("hook cannot reach worktree", m.detail)
        self.assertEqual(m.evidence, [])

    def test_env_chua_bien_dich_hook_thi_khong_ky_vong_co_ly_do(self):
        """Không có ○ ở mục này: hook chưa biên dịch là quyết định của harness
        (không kỳ vọng), mục nói lý do và không phải đạt."""
        m = self.muc(self.gate(guard_expected=False))
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)
        self.assertIn("not compiled", m.detail)


class TestTest(Muc):
    TEN = "test"

    def test_positive_xanh_sau_lan_sua_cuoi(self):
        t = self.xanh()
        m = self.muc(self.gate())
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertEqual(m.evidence, [t.seq])

    def test_negative_do_hoac_sua_sau_khi_xanh(self):
        self.xanh(ids=["t"], failed_ids=["t"])
        self.assertIs(self.muc(self.gate()).outcome, Outcome.FAILED)
        self.store.tool_run("S-01", "test", ok=True)
        sua = self.store.file_change("S-01", "src/b.py")
        m = self.muc(self.gate())
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("src/b.py", m.detail)
        self.assertIn(sua.seq, m.evidence, "trỏ cả tệp sửa sau lần test cuối")

    def test_env_khong_chay_duoc_la_moi_truong_khong_phai_do(self):
        self.store.file_change("S-01", "src/a.py")
        self.store.tool_run("S-01", "test", ok=False,
                            detail={"unrunnable": "công cụ chưa cài hoặc không nạp được (module_not_found)"})
        self.store.tool_run("S-01", "lint", ok=True)
        m = self.muc(self.gate())
        self.assertIs(m.outcome, Outcome.UNRUNNABLE)
        self.assertTrue(m.outcome.must_be_named)
        self.assertIn("module_not_found", m.detail)


class TestKhongLamDoTestCoSan(Muc):
    TEN = "no baseline regression"

    def baseline(self, ids, **d) -> Event:
        return self.store.tool_run("S-01", "test:baseline", ok=True, detail={
            "baseline": True, "test_format": "pytest", "test_ids": list(ids),
            "failed_ids": [], "skipped_ids": [], **d,
        })

    def test_positive_test_co_san_con_xanh(self):
        b = self.baseline(["t1", "t2"])
        t = self.xanh(sha="aaa", ids=["t1", "t2"])
        m = self.muc(self.gate(candidate="aaa"))
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertEqual(m.evidence, [b.seq, t.seq])

    def test_negative_mot_test_co_san_do_thi_neu_ten(self):
        self.baseline(["t1", "t2"])
        self.xanh(sha="aaa", ids=["t1", "t2"], failed_ids=["t2"])
        m = self.muc(self.gate(candidate="aaa"))
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("broke 1 test", m.detail)
        self.assertIn("t2", m.detail)

    def test_env_baseline_khong_chay_duoc_hay_khong_doc_duoc_ten(self):
        self.store.tool_run("S-01", "test:baseline", ok=False,
                            detail={"baseline": True, "unrunnable": "công cụ chưa cài (exit 127)"})
        self.xanh()
        m = self.muc(self.gate())
        self.assertIs(m.outcome, Outcome.UNRUNNABLE)
        self.assertIn("exit 127", m.detail)
        self.baseline([], test_format="", test_note="vitest reporter mặc định không in tên test — thêm `--reporter=verbose`")
        self.xanh()
        m = self.muc(self.gate())
        self.assertIs(m.outcome, Outcome.UNCONFIGURED)
        self.assertTrue(m.outcome.must_be_named)
        self.assertIn("--reporter=verbose", m.detail)


class TestLint(Muc):
    TEN = "lint"

    def test_positive_lint_sach(self):
        self.xanh()
        m = self.muc(self.gate())
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertEqual(m.evidence, [self.store.read("S-01").last(TOOL_RUN, "lint").seq])

    def test_negative_lint_ban_kem_duoi_output(self):
        self.xanh()
        self.store.tool_run("S-01", "lint", ok=False, detail={"tail": "src/a.py:3:80 E501 dòng quá dài"})
        m = self.muc(self.gate())
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("E501", m.detail)

    def test_env_chua_khai_lenh_lint_la_chua_cau_hinh(self):
        self.xanh()
        s = self.store.tool_run("S-01", "lint", ok=False, detail={"skipped": "dự án chưa khai lệnh cho tool này"})
        m = self.muc(self.gate())
        self.assertIs(m.outcome, Outcome.UNCONFIGURED)
        self.assertTrue(m.outcome.must_be_named)
        self.assertIn("chưa khai lệnh", m.detail)
        self.assertEqual(m.evidence, [s.seq])


class TestPhamViGhi(Muc):
    """Suy từ `changed`/`write_scope` (cây git do `run_attempt` đọc), không từ
    sự kiện → `evidence` rỗng là điều được khai."""

    TEN = "write scope"

    def test_positive_tep_doi_nam_trong_pham_vi(self):
        self.xanh()
        m = self.muc(self.gate(changed=["src/a.py"], write_scope=["src"]))
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertEqual(m.evidence, [])

    def test_negative_tep_ngoai_pham_vi_neu_ten(self):
        self.xanh()
        m = self.muc(self.gate(changed=["src/a.py", "infra/deploy.yaml"]))
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("infra/deploy.yaml", m.detail)

    def test_env_story_chua_khai_write_scope_khong_phai_dat(self):
        """Không có ○: story chưa khai phạm vi mà đã đổi tệp thì không có gì
        để so — và không so được **không** cho qua (SOLUTION §12: ✗)."""
        self.xanh()
        m = self.muc(self.gate(changed=["src/a.py"], write_scope=[]))
        self.assertTrue(m.outcome.blocks)
        self.assertIn("write_scope", m.detail)
        m = self.muc(self.gate(changed=[], write_scope=[]))
        self.assertIs(m.outcome, Outcome.PASSED, "không đổi gì thì không có gì ngoài phạm vi")


class TestMapMockup(Muc):
    TEN = "mockup map"

    def doi_chieu(self, screen: str, ok: bool, **detail) -> Event:
        return self.store.record("S-01", Event(kind=MOCKUP_MAP, name=screen, ok=ok,
                                               detail={"missing": [], "missing_data_roles": [], **detail}))

    def test_positive_man_hinh_khop(self):
        self.xanh()
        e = self.doi_chieu("danh-sach", True)
        m = self.muc(self.gate(screens=["danh-sach"]))
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertEqual(m.evidence, [e.seq])
        m = self.muc(self.gate(screens=[]))
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)
        self.assertIn("no UI", m.detail)

    def test_negative_thieu_component_neu_ten(self):
        self.xanh()
        self.doi_chieu("danh-sach", False, missing=['button "Ghi chú mới"'])
        m = self.muc(self.gate(screens=["danh-sach"]))
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("Ghi chú mới", m.detail)

    def test_env_harness_khong_doi_chieu_duoc_thi_neu_man(self):
        """Trình duyệt thiếu → không có `MOCKUP_MAP` nào. Không có ○: story
        giao diện chưa đối chiếu không được qua (SOLUTION §12: ✗), mục nêu màn."""
        self.xanh()
        m = self.muc(self.gate(screens=["danh-sach"]))
        self.assertTrue(m.outcome.blocks)
        self.assertIn("not compared: danh-sach", m.detail)
        self.assertEqual(m.evidence, [])


class TestTestThat(Muc):
    TEN = "real tests"

    def test_positive_khong_test_rong_khang_dinh(self):
        self.xanh()
        q = self.store.tool_run("S-01", "qa:fake-tests", ok=True, detail={"files": []})
        m = self.muc(self.gate())
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertEqual(m.evidence, [q.seq])

    def test_negative_test_rong_khang_dinh_neu_tep(self):
        self.xanh()
        self.store.tool_run("S-01", "qa:fake-tests", ok=False, detail={"files": ["tests/test_a.py"]})
        m = self.muc(self.gate())
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("tests/test_a.py", m.detail)

    def test_env_chua_quet_thi_khong_tro_su_kien_nao(self):
        """`run_attempt` luôn ghi `qa:fake-tests`, và từ F2 (SS-01) `qa.run_suite`
        cũng ghi cả khi sạch; chỉ bằng chứng chép tay mới thiếu. Vắng quét là
        "quét chưa chạy", không phải "quét sạch": UNRUNNABLE, `evidence` rỗng
        (INV-T.1 — vắng mặt không bao giờ sinh PASS)."""
        self.xanh()
        m = self.muc(self.gate())
        self.assertEqual(m.evidence, [])
        self.assertIs(m.outcome, Outcome.UNRUNNABLE)


class TestTieuChiCoTest(Muc):
    TEN = "criteria have tests"

    def test_positive_moi_tieu_chi_co_test_mang_ma(self):
        t = self.xanh(ids=["AC-S-01-1: a", "nhóm > AC-S-01-2: b"])
        m = self.muc(self.gate(acceptance=2))
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertEqual(m.evidence, [t.seq])
        self.assertIs(self.muc(self.gate(acceptance=0)).outcome, Outcome.NOT_APPLICABLE)
        # CTRF cũng là reporter in tên (ADR-005 V9)
        self.xanh(ids=["test_ac.py::test_AC_S_01_1_a", "test_ac.py::test_AC_S_01_2_b"], test_format="ctrf")
        self.assertIs(self.muc(self.gate(acceptance=2)).outcome, Outcome.PASSED)

    def test_negative_thieu_ma_thi_neu_dung_ma(self):
        self.xanh(ids=["AC-S-01-1: a"])
        m = self.muc(self.gate(acceptance=2))
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("AC-S-01-2", m.detail)

    def test_env_reporter_khong_in_ten_la_chua_cau_hinh(self):
        self.xanh(ids=[], test_format="", test_note="vitest reporter mặc định không in tên test — thêm `--reporter=verbose`")
        m = self.muc(self.gate(acceptance=2))
        self.assertIs(m.outcome, Outcome.UNCONFIGURED)
        self.assertTrue(m.outcome.must_be_named)
        self.assertFalse(m.outcome.counts_as_done)
        self.assertIn("--reporter=verbose", m.detail)


class TestCoverage(Muc):
    TEN = "coverage"

    def test_positive_du_nguong(self):
        t = self.xanh(ids=["t"], coverage=90.0)
        m = self.muc(self.gate(coverage_min=0.85))
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertEqual(m.evidence, [t.seq])

    def test_negative_duoi_nguong_kem_so(self):
        self.xanh(ids=["t"], coverage=60.0)
        m = self.muc(self.gate(coverage_min=0.85))
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("60% < 85%", m.detail)

    def test_env_runner_khong_in_so_la_chua_cau_hinh(self):
        self.xanh(ids=["t"], coverage=None)
        m = self.muc(self.gate(coverage_min=0.85))
        self.assertIs(m.outcome, Outcome.UNCONFIGURED)
        self.assertTrue(m.outcome.must_be_named)
        self.assertIn("--cov", m.detail)


class TestTDD(Muc):
    TEN = "TDD"

    def test_positive_do_truoc_xanh(self):
        do = self.store.tool_run("S-01", "test", ok=False)
        xanh = self.xanh()
        m = self.muc(self.gate(added_tests=["tests/x.test.js"]))
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertEqual(m.evidence, [do.seq, xanh.seq])
        self.assertIs(self.muc(self.gate(added_tests=[])).outcome, Outcome.NOT_APPLICABLE)

    def test_negative_xanh_ngay_lan_dau(self):
        self.xanh()
        m = self.muc(self.gate(added_tests=["tests/x.test.js"]))
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("green on first run", m.detail)

    def test_env_lan_bo_qua_khong_duoc_tinh_la_do(self):
        """Lần `test` chưa cấu hình (`skipped`) trông giống đỏ (ok=False) —
        môi trường không được giả làm lần đỏ của TDD."""
        self.store.tool_run("S-01", "test", ok=False, detail={"skipped": "dự án chưa khai lệnh cho tool này"})
        self.xanh()
        m = self.muc(self.gate(added_tests=["tests/x.test.js"]))
        self.assertIs(m.outcome, Outcome.FAILED)


class TestHopDongKiemDinh(Muc):
    """Họ mục `<kind>`: tên mục thật là tên loại trong hợp đồng kiểm định."""

    TEN = "<kind>"

    def test_positive_qa_kind_xanh(self):
        self.xanh()
        e = self.store.tool_run("S-01", "qa:e2e", ok=True)
        m = self.muc(self.gate(contract=["unit", "e2e"]), "e2e")
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertEqual(m.kind, CHECK_KIND["<kind>"])
        self.assertEqual(m.evidence, [e.seq])

    def test_negative_qa_kind_do_kem_duoi_output(self):
        self.xanh()
        self.store.tool_run("S-01", "qa:accessibility", ok=False, detail={"tail": "1 failed: thiếu aria-label"})
        m = self.muc(self.gate(contract=["accessibility"]), "accessibility")
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("aria-label", m.detail)

    def test_env_chua_chay_hay_bo_qua_la_chua_cau_hinh(self):
        self.xanh()
        m = self.muc(self.gate(contract=["perf"]), "perf")
        self.assertIs(m.outcome, Outcome.UNCONFIGURED)
        self.assertTrue(m.outcome.must_be_named)
        s = self.store.tool_run("S-01", "qa:perf", ok=False, detail={"skipped": "chưa khai lệnh `verify.perf`"})
        m = self.muc(self.gate(contract=["perf"]), "perf")
        self.assertIs(m.outcome, Outcome.UNCONFIGURED)
        self.assertIn("verify.perf", m.detail)
        self.assertEqual(m.evidence, [s.seq])


class TestBaoMat(Muc):
    """Đọc `SecurityReport` của phiên rà soát bảo mật (tham số) — `evidence`
    rỗng là điều được khai."""

    TEN = "security"

    def test_positive_khong_muc_chan(self):
        self.xanh()
        m = self.muc(self.gate(security=SecurityReport()))
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertEqual(m.evidence, [])

    def test_negative_muc_high_chan_kem_noi_dung(self):
        self.xanh()
        rep = SecurityReport(findings=[Finding("high", "os.system với chuỗi ghép từ input")])
        m = self.muc(self.gate(security=rep))
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("1 blocking item", m.detail)
        self.assertIn("os.system", m.detail)

    def test_env_chua_cau_hinh_ra_soat_bao_mat(self):
        self.xanh()
        m = self.muc(self.gate(security=None))
        self.assertIs(m.outcome, Outcome.UNCONFIGURED)
        self.assertTrue(m.outcome.must_be_named)
        self.assertFalse(m.outcome.counts_as_done)
        self.assertIn("security review not configured", m.detail)


class TestRaSoat(Muc):
    """Đọc `review_blocking` (lời reviewer đã lọc ở `run_attempt`, tham số) —
    `evidence` rỗng là điều được khai."""

    TEN = "review"

    def test_positive_khong_con_muc_chan(self):
        self.xanh()
        m = self.muc(self.gate(review_blocking=[]))
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertEqual(m.evidence, [])

    def test_negative_muc_chan_kem_noi_dung(self):
        self.xanh()
        m = self.muc(self.gate(review_blocking=["[chặn] src/a.py:10 — mất dữ liệu khi lưu"]))
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("mất dữ liệu", m.detail)

    def test_env_chua_ra_soat_khong_phai_dat(self):
        """Không có ⚠/○: phiên rà soát không chạy được thì story chưa được rà
        soát — chặn với lý do ấy (SOLUTION §12: ✗ chưa rà soát)."""
        self.xanh()
        m = self.muc(self.gate(review_ran=False))
        self.assertTrue(m.outcome.blocks)
        self.assertIn("independent review not run", m.detail)


class TestBaoToan(Muc):
    TEN = "preservation"
    GIU = [{"id": "AC-S-02-1", "kind": "ac", "story": "S-02"}]

    def test_positive_hanh_vi_story_khac_con_xanh(self):
        t = self.xanh(sha="aaa", ids=["AC-S-02-1: giữ"])
        m = self.muc(self.gate(candidate="aaa", preservation=self.GIU))
        self.assertIs(m.outcome, Outcome.PASSED)
        self.assertIn("still green", m.detail)
        self.assertEqual(m.evidence, [t.seq])
        m = self.muc(self.gate(candidate="aaa", preservation=[]))
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)

    def test_negative_hoi_quy_neu_ten(self):
        self.xanh(sha="aaa", ids=["AC-S-02-1: giữ"], failed_ids=["AC-S-02-1: giữ"])
        m = self.muc(self.gate(candidate="aaa", preservation=self.GIU))
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("regression", m.detail)
        self.assertIn("AC-S-02-1", m.detail)

    def test_env_khong_kiem_duoc_o_ung_vien_khong_phai_dat(self):
        self.xanh(sha="aaa", ids=["t_khac"])
        m = self.muc(self.gate(candidate="aaa", preservation=self.GIU))
        self.assertIs(m.outcome, Outcome.UNRUNNABLE)
        self.assertTrue(m.outcome.must_be_named)
        self.assertIn("cannot verify", m.detail)
        self.assertIn("AC-S-02-1", m.detail)


class TestTestCoKiemDuocStory(Muc):
    """ADR-005 V3 nop control: test mang mã tiêu chí phải đỏ khi không có mã
    của story. Cấp 1 so `test:baseline`, cấp 2 đọc `test:nop` — trỏ cả ba
    sự kiện đã đọc. Bộ phép đầy đủ ở `test_gate.py::TestTestCoKiemDuocStory`."""

    TEN = "tests verify story"
    AC = "tests/test_a.py::test_AC_S_01_1_x"

    def baseline(self, ids, **d) -> Event:
        return self.store.tool_run("S-01", "test:baseline", ok=True, detail={
            "baseline": True, "test_format": "pytest", "test_ids": list(ids),
            "failed_ids": [], "skipped_ids": [], **d})

    def nop(self, ids=None, failed=(), **d) -> Event:
        detail = {"nop": True, "parent": "cha0000", "files": ["tests/test_a.py"], **d}
        if ids is not None:
            detail.update({"test_format": "pytest", "test_ids": list(ids), "failed_ids": list(failed)})
        return self.kho("aaa").tool_run("S-01", "test:nop", ok=not failed and ids is not None, detail=detail)

    def test_positive_test_mang_ma_do_o_sha_cha(self):
        b = self.baseline(["t1"])
        t = self.xanh(sha="aaa", ids=[self.AC, "t1"])
        n = self.nop([self.AC, "t1"], failed=[self.AC])
        m = self.muc(self.gate(candidate="aaa", acceptance=1))
        self.assertIs(m.outcome, Outcome.PASSED, m.detail)
        self.assertEqual(m.evidence, [b.seq, t.seq, n.seq])
        # story không thêm/sửa tệp test → không áp dụng, có lý do, vẫn trỏ nop
        n2 = self.nop(files=[], skipped="story không thêm/sửa tệp test")
        m = self.muc(self.gate(candidate="aaa", acceptance=1))
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)
        self.assertIn(n2.seq, m.evidence)

    def test_negative_xanh_o_sha_cha_hay_xanh_san_o_baseline_neu_ten(self):
        self.baseline(["t1"])
        self.xanh(sha="aaa", ids=[self.AC, "t1"])
        self.nop([self.AC, "t1"])
        m = self.muc(self.gate(candidate="aaa", acceptance=1))
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("still green without story code", m.detail)
        self.assertIn(self.AC, m.detail)
        # cấp 1: mã gắn vào test đã xanh ở baseline — ✗ dù nop đỏ
        self.baseline([self.AC, "t1"])
        self.xanh(sha="aaa", ids=[self.AC, "t1"])
        self.nop([self.AC, "t1"], failed=[self.AC])
        m = self.muc(self.gate(candidate="aaa", acceptance=1))
        self.assertIs(m.outcome, Outcome.FAILED)
        self.assertIn("tagged existing tests", m.detail)

    def test_env_nop_khong_chay_duoc_hay_khong_in_ten_khong_phai_dat(self):
        self.baseline(["t1"])
        self.xanh(sha="aaa", ids=[self.AC, "t1"])
        self.nop(unrunnable="công cụ chưa cài (exit 127)")
        m = self.muc(self.gate(candidate="aaa", acceptance=1))
        self.assertIs(m.outcome, Outcome.UNRUNNABLE)
        self.assertIn("exit 127", m.detail)
        # reporter không in tên, bộ test đỏ ở SHA cha: không biết của ai → ○
        self.kho("aaa").tool_run("S-01", "test", ok=True)
        self.kho("aaa").tool_run("S-01", "test:nop", ok=False, detail={"nop": True, "files": ["tests/test_a.py"]})
        m = self.muc(self.gate(candidate="aaa", acceptance=1))
        self.assertIs(m.outcome, Outcome.UNCONFIGURED)
        self.assertTrue(m.outcome.must_be_named)
        # tắt bởi cấu hình → –, có tên knob
        self.kho("aaa").tool_run("S-01", "test:nop", ok=False,
                                 detail={"nop": True, "disabled": True, "skipped": "tắt bởi cấu hình `verify.nop`"})
        m = self.muc(self.gate(candidate="aaa", acceptance=1))
        self.assertIs(m.outcome, Outcome.NOT_APPLICABLE)
        self.assertIn("verify.nop", m.detail)


class TestBangChungNhan(Muc):
    """Test meta: bảng đọc từ tệp này khớp `CHECK_NAMES`, `gate.py` không gọi
    tên lạ, `CHECK_KIND` đóng, và sau `evaluate` mọi mục có `kind`, ≥ 10 mục
    trỏ sự kiện."""

    def test_moi_ten_co_du_ba_control(self):
        table = qualification_table(Path(__file__))
        self.assertEqual(set(table), set(CHECK_NAMES))
        for ten, cols in table.items():
            with self.subTest(muc=ten):
                thieu = [c for c in CONTROLS if not cols[c]]
                self.assertFalse(thieu, f"mục `{ten}` thiếu control {thieu}")

    def test_ten_TEN_trong_tep_nay_thuoc_CHECK_NAMES(self):
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        ten = {n.value.value for cls in tree.body if isinstance(cls, ast.ClassDef)
               for n in cls.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
               and any(isinstance(t, ast.Name) and t.id == "TEN" for t in n.targets)}
        self.assertEqual(ten - {""}, set(CHECK_NAMES))

    def test_moi_Check_trong_gate_dung_ten_trong_CHECK_NAMES(self):
        tree = ast.parse(GATE_PY.read_text(encoding="utf-8"))
        bien = {t.id: n.value.value for n in ast.walk(tree)
                if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
                for t in n.targets if isinstance(t, ast.Name)}
        goi = [n for n in ast.walk(tree)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Check" and n.args]
        self.assertGreaterEqual(len(goi), 30, "regex/AST lệch với gate.py")
        for call in goi:
            a = call.args[0]
            if isinstance(a, ast.Constant):
                ten = a.value
            elif isinstance(a, ast.Name) and a.id == "kind":
                ten = "<kind>"           # họ mục theo hợp đồng kiểm định
            elif isinstance(a, ast.Name) and a.id in bien:
                ten = bien[a.id]
            else:
                self.fail(f"gate.py:{call.lineno} Check(...) với tên không đọc được tĩnh")
            with self.subTest(line=call.lineno, ten=ten):
                self.assertIn(ten, CHECK_NAMES, f"gate.py:{call.lineno} dùng tên ngoài CHECK_NAMES")

    def test_CHECK_KIND_dong_va_hop_le(self):
        self.assertEqual(set(CHECK_KIND), set(CHECK_NAMES))
        for ten, kind in CHECK_KIND.items():
            with self.subTest(muc=ten):
                self.assertIn(kind, CHECK_KINDS)

    def bang_chung_day_du(self):
        """Một story có mọi loại bằng chứng, ở ứng viên `aaa`."""
        self.store.tool_run("S-01", "test:baseline", ok=True, detail={
            "baseline": True, "test_format": "pytest", "test_ids": ["t0", "AC-S-02-1: giữ"],
            "failed_ids": [], "skipped_ids": []})
        st = self.kho("aaa")
        st.record("S-01", Event(kind=GUARD_SEEN, name="git-stage"))
        st.file_change("S-01", "src/a.py")
        st.tool_run("S-01", "test", ok=False, detail={"test_format": "pytest", "test_ids": ["AC-S-01-1: a"],
                                                      "failed_ids": ["AC-S-01-1: a"]})
        st.tool_run("S-01", "test", ok=True, detail={"test_format": "pytest", "coverage": 90.0,
                                                     "test_ids": ["t0", "AC-S-01-1: a", "AC-S-02-1: giữ"],
                                                     "failed_ids": []})
        st.tool_run("S-01", "lint", ok=True)
        st.tool_run("S-01", "qa:fake-tests", ok=True, detail={"files": []})
        st.record("S-01", Event(kind=MOCKUP_MAP, name="danh-sach", ok=True,
                                detail={"missing": [], "missing_data_roles": []}))
        st.tool_run("S-01", "qa:e2e", ok=True)
        return self.gate(candidate="aaa", screens=["danh-sach"], contract=["unit", "e2e"],
                         security=SecurityReport(), guard_expected=True, acceptance=1,
                         coverage_min=0.85, added_tests=["tests/test_a.py"],
                         preservation=[{"id": "AC-S-02-1", "kind": "ac", "story": "S-02"}])

    def test_moi_muc_co_kind_va_it_nhat_10_muc_tro_su_kien(self):
        g = self.bang_chung_day_du()
        self.assertTrue(g.passed, g.summary())
        self.assertEqual(len(g.checks), len(CHECK_NAMES))
        for c in g.checks:
            with self.subTest(muc=c.name):
                self.assertIn(c.kind, CHECK_KINDS, f"mục `{c.name}` không có kind")
        rong = {c.name for c in g.checks if not c.evidence}
        self.assertEqual(rong, {"write scope", "security", "review"}, "mục rỗng phải là mục suy từ tham số")
        self.assertGreaterEqual(len(g.checks) - len(rong), 10)

    def test_as_dict_xuat_kind_va_evidence_json_hoa_duoc(self):
        g = self.bang_chung_day_du()
        rows = [c.as_dict() for c in g.checks]
        json.dumps(rows)
        self.assertTrue(all({"kind", "evidence"} <= set(r) for r in rows))
        self.assertTrue(all(isinstance(s, int) for r in rows for s in r["evidence"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
