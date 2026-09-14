"""Đợt tuyển cặp model↔CLI trước cột 2 (G5.3) — phép kiểm cho `tests/bench/_qualify.py`.

Không một lượt gọi model nào ở đây: phần đường ống chạy với `opencode` **GIẢ**
(chính script giả của `tests/bench/_selfcheck.py`, một bản trong kho chứ không
hai), phần số học là hàm thuần.

Ba lớp lỗi mà bộ này tồn tại để chặn, mỗi lớp đã có tiền lệ trong kho:

1. **Ngưỡng trôi sau khi thấy dữ liệu.** Hằng số trong mã phải khớp bảng §2.10
   của vùng ghim — phép kiểm ấy ở `test_meta.py::TestGiaoThucTuyenCapBiGhim`; ở
   đây kiểm rằng luật quyết định **dùng** đúng những hằng số đó ở cả bốn biên.
2. **Bằng chứng bịa.** Một bảng sinh từ client giả ghi vào
   `docs/BENCH-PAIR-QUALIFICATION.md` là bằng chứng đóng gate bịa, dù có banner.
3. **Đợt tuyển trôi khỏi hình dạng cohort.** Nếu đề bài / env / argv của phiên
   tuyển lệch khỏi `_runner.run` thì nó đo một thứ khác với thứ cột 2 sẽ chạy —
   và không ai thấy. So từng byte, qua sổ gọi của binary giả.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control import closure as CL  # noqa: E402
from aisef.control.gate import Outcome  # noqa: E402
from tests.bench import _qualify as Q  # noqa: E402
from tests.bench import _runner as R  # noqa: E402
from tests.bench import _selfcheck as S  # noqa: E402

#: Task rẻ nhất, chỉ để phép kiểm đường ống chạy nhanh. Task **đã đăng ký** của
#: đợt tuyển là `Q.TASK_TUYEN` và nó được kiểm ở `test_meta` chứ không ở đây.
TASK_RE = "bug-a2-multi-2"


def _dong(**kw) -> dict:
    """Một dòng sổ tối thiểu, mặc định là phiên sạch."""
    return {"client": "opencode", "note": "cặp-A", "task": Q.TASK_TUYEN, "nhan": "xong",
            "exit_status": "ok", "turn": 20, "giay": 250.0, "token": 1_300_000, **kw}


def _cohort(cat: int = 0, ha_tang: int = 0, loai: int = 0, tong: int = 28, **kw) -> list[dict]:
    xong = tong - cat - ha_tang
    return ([_dong(nhan="cắt", exit_status="infra", **kw) for _ in range(cat)]
            + [_dong(nhan="hạ tầng", exit_status="timeout", **kw) for _ in range(ha_tang)]
            + [_dong(nhan="xong", **kw) for _ in range(xong)]
            + [_dong(nhan="loại", exit_status="auth", **kw) for _ in range(loai)])


class TestNhanTungPhien(unittest.TestCase):
    """Một phiên bị cắt phải đọc ra khác một phiên timeout và khác một khoá sai."""

    def test_dau_hieu_cat_tach_khoi_ha_tang_khac(self):
        self.assertEqual(Q.phan_loai("infra", f"x {Q.DAU_HIEU_CAT} y"), "cắt")
        self.assertEqual(Q.phan_loai("infra", "Bad Gateway (HTTP 502)"), "hạ tầng")
        self.assertEqual(Q.phan_loai("timeout", "exceeded 1800s"), "hạ tầng")
        self.assertEqual(Q.phan_loai("rate_limit", "429"), "hạ tầng")

    def test_khoa_va_quyen_bi_loai_khoi_mau(self):
        """Một khoá bị từ chối không là tính chất của cặp — để nó vào mẫu số là để
        khoá hết hạn đọc thành 'cặp này sạch'."""
        self.assertEqual(Q.phan_loai("auth", "401"), "loại")
        self.assertEqual(Q.phan_loai("permission", ""), "loại")

    def test_phien_binh_thuong_va_tran_luot_van_la_phien_hop_le(self):
        self.assertEqual(Q.phan_loai("ok", ""), "xong")
        self.assertEqual(Q.phan_loai("max_turns", "61/60"), "xong")


class TestLuatPhanQuyet(unittest.TestCase):
    """Bốn biên của luật, đọc thẳng từ hằng số đã ghim."""

    def _pq(self, **kw) -> tuple[str, str]:
        [t] = Q.tong_hop(_cohort(**kw))
        return t["phan_quyet"], t["vi_sao"]

    def test_bien_dat(self):
        """4/28 = 0,143 ≤ 1/6 → đạt; 5/28 = 0,179 → không. Đây là chỗ trần sống."""
        self.assertEqual(self._pq(cat=4)[0], "QUALIFIED")
        self.assertEqual(self._pq(cat=5)[0], "NOT_QUALIFIED")

    def test_thieu_phien_hop_le_la_chua_ket_luan_khong_phai_truot(self):
        """Một cohort mỏng không được đọc thành 'cặp này xấu'."""
        pq, vi_sao = self._pq(cat=0, tong=27)
        self.assertEqual(pq, "INCONCLUSIVE")
        self.assertIn(f"27/{Q.SO_PHIEN_TUYEN}", vi_sao)

    def test_phien_bi_loai_keo_mau_xuong_duoi_san_thi_chua_ket_luan(self):
        pq, vi_sao = self._pq(cat=0, tong=26, loai=4)
        self.assertEqual(pq, "INCONCLUSIVE")
        self.assertIn("khoá/quyền", vi_sao)

    def test_khong_cat_phien_nao_nhung_hong_ha_tang_qua_nhieu_thi_truot(self):
        """Trần thứ hai là con số **đã đăng ký** của tiền đăng ký (1/3), không của tôi."""
        pq, vi_sao = self._pq(cat=0, ha_tang=10, tong=28)
        self.assertEqual(pq, "NOT_QUALIFIED")
        self.assertIn("hỏng hạ tầng", vi_sao)

    def test_client_khong_co_bo_phat_hien_thi_khong_bao_gio_dat(self):
        """Vắng mặt phép đo không được suy thành tỉ lệ 0 %."""
        [t] = Q.tong_hop(_cohort(cat=0, client="claude"))
        self.assertEqual(t["phan_quyet"], "INCONCLUSIVE")
        self.assertIn("không đo được", t["vi_sao"])
        self.assertNotIn("claude", Q.CLIENT_DO_DUOC)


class TestKhoangTinChuKhongChiMotDiem(unittest.TestCase):
    def test_bien_tren_95_phan_tram(self):
        """0/28 phiên sạch **không** chứng nhận 3,8 % — nó chỉ loại được > 10,2 %."""
        self.assertAlmostEqual(Q.cp_tren(0, 28), 0.1015, places=3)
        self.assertAlmostEqual(Q.cp_tren(4, 28), 0.2977, places=3)
        self.assertGreater(Q.cp_tren(4, 28), Q.cp_tren(0, 28))
        self.assertEqual(Q.cp_tren(0, 0), 1.0)


class TestLuatChonCap(unittest.TestCase):
    def test_tuyen_theo_ti_le_cat_roi_ha_tang_roi_thu_tu_chu(self):
        rows = (_cohort(cat=4, note="cặp-A") + _cohort(cat=1, note="cặp-B")
                + _cohort(cat=1, ha_tang=3, note="cặp-C"))
        chon = Q.chon_cap(Q.tong_hop(rows))
        self.assertEqual(chon["model"], "cặp-B")

    def test_khong_cap_nao_dat_thi_khong_chon_gi(self):
        self.assertIsNone(Q.chon_cap(Q.tong_hop(_cohort(cat=9))))


class TestBaoCaoDungHinhDangProbeG53Doc(unittest.TestCase):
    """Báo cáo phải qua được **chính** probe của cổng đóng dự án, không một bản
    mô phỏng nó: `closure.py` là thứ sẽ chấm, nên nó là thứ phải chấm ở đây."""

    def _probe(self, rows: list[dict]) -> CL.Probed:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs").mkdir()
            (root / "docs/BENCH-PAIR-QUALIFICATION.md").write_text(
                Q.bao_cao(rows, root=ROOT), encoding="utf-8")
            ctx = CL.Ctx(root=root, spec={},
                         criterion={"evidence": "docs/BENCH-PAIR-QUALIFICATION.md"})
            return CL.probe_pair_qualification(ctx)

    def test_mot_cap_dat_thi_probe_PASSED(self):
        p = self._probe(_cohort(cat=2))
        self.assertIs(p.outcome, Outcome.PASSED, p.detail)
        self.assertIn("cặp-A/opencode", p.detail)

    def test_khong_cap_nao_dat_thi_probe_WAIVER_PENDING_va_chan(self):
        p = self._probe(_cohort(cat=9))
        self.assertIs(p.outcome, Outcome.FAILED)
        self.assertIn("WAIVER_PENDING", p.detail)
        self.assertTrue(p.outcome.blocks)

    def test_chua_ket_luan_cung_chan(self):
        """`INCONCLUSIVE` không là giấy phép: probe chỉ đọc `có` thành đạt."""
        p = self._probe(_cohort(cat=0, tong=10))
        self.assertIs(p.outcome, Outcome.FAILED)

    def test_bang_khai_du_truong_phan_quyet_3_doi(self):
        bang = Q.bao_cao(_cohort(cat=2), root=ROOT)
        for cot in ("model", "client", "phiên tuyển", "phiên bị cắt (cut)", "tỉ lệ cắt (rate)",
                    "hỏng hạ tầng (timeout/infra)", "qualifies", "evidence"):
            with self.subTest(cot=cot):
                self.assertIn(cot, bang)

    def test_bao_cao_noi_gia_vang_mat_chu_khong_in_cot_do_la_so_khong(self):
        bang = Q.bao_cao(_cohort(cat=2), root=ROOT)
        self.assertIn("vắng mặt", bang)
        self.assertNotIn("0,00 USD |", bang)

    def test_bao_cao_tro_vao_giao_thuc_da_ghim_va_digest_cua_no(self):
        import hashlib
        import re
        vung = re.findall(Q.VUNG_GHIM, (ROOT / Q.GIAO_THUC).read_text(encoding="utf-8"))[0]
        d = hashlib.sha256(vung.strip("\n").encode("utf-8")).hexdigest()
        bang = Q.bao_cao(_cohort(cat=2), root=ROOT)
        self.assertIn(d[:16], bang, "báo cáo không nối dữ liệu với văn bản đã chấm nó")


class TestKhongGhiBangChungTuPhienGia(unittest.TestCase):
    """Ranh giới tin cậy: `docs/BENCH-PAIR-QUALIFICATION.md` là tệp probe G5.3 đọc."""

    def test_tu_choi_duong_dan_bang_chung_khi_so_co_phien_gia(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs").mkdir()
            ma = Q.viet_bao_cao(_cohort(cat=1, gia=True), "docs/BENCH-PAIR-QUALIFICATION.md",
                                root=root)
            self.assertEqual(ma, 2)
            self.assertFalse((root / "docs/BENCH-PAIR-QUALIFICATION.md").exists())

    def test_van_ghi_ra_duong_dan_khac_de_xem_thu(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs").mkdir()
            self.assertEqual(Q.viet_bao_cao(_cohort(cat=1, gia=True), "docs/thu.md", root=root), 0)
            self.assertIn(Q.BANNER_GIA, (root / "docs/thu.md").read_text(encoding="utf-8"))

    def test_so_that_thi_ghi_luon_ban_sao_duoc_commit(self):
        """`.aisef-qual/` bị gitignore; cột `evidence` phải trỏ vào thứ sống sót."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs").mkdir()
            rows = _cohort(cat=1)
            self.assertEqual(Q.viet_bao_cao(rows, "docs/BENCH-PAIR-QUALIFICATION.md", root=root), 0)
            sao = root / Q.SO_TRONG_KHO
            self.assertTrue(sao.is_file())
            self.assertEqual(len(sao.read_text(encoding="utf-8").splitlines()), len(rows))
            self.assertIn(Q.SO_TRONG_KHO,
                          (root / "docs/BENCH-PAIR-QUALIFICATION.md").read_text(encoding="utf-8"))

    def test_so_rong_khong_sinh_bao_cao_rong(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(Q.viet_bao_cao([], "docs/x.md", root=Path(d)), 2)


class _Gia(unittest.TestCase):
    """Nền cho phép kiểm đường ống: `opencode` GIẢ, không mạng, không model."""

    def setUp(self) -> None:
        from aisef.clients.opencode import OpenCodeAdapter

        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        fake = self.tmp / "opencode"
        fake.write_text(S._FAKE.replace("TOKEN", json.dumps(S.TOKEN)), encoding="utf-8")
        fake.chmod(0o755)
        self.log = self.tmp / "calls.jsonl"
        self.client = OpenCodeAdapter(binary=str(fake))
        self.giu = R.KEEP_DIR
        R.KEEP_DIR = self.tmp / "bench"
        self.cu = {k: os.environ.get(k) for k in
                   ("AISEF_SELFCHECK_LOG", "AISEF_SELFCHECK_MODE", "AISEF_SELFCHECK_GOLD")}
        os.environ["AISEF_SELFCHECK_LOG"] = str(self.log)
        os.environ.pop("AISEF_SELFCHECK_GOLD", None)
        self.addCleanup(self._tra_lai)

    def _tra_lai(self) -> None:
        R.KEEP_DIR = self.giu
        for k, v in self.cu.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self._tmp.cleanup()

    def _goi(self) -> list[dict]:
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines()]


class TestDuongOngTuyenCap(_Gia):
    def test_phien_bi_cat_vao_so_dung_nhan_va_ghi_ngay_sau_tung_phien(self):
        """7 phiên: trần cắt của cohort ấy là ⌊7/6⌋ = 1, nên một phiên cắt **không**
        dừng đợt — đủ để thấy sổ ghi tiếp sau phiên hỏng."""
        os.environ["AISEF_SELFCHECK_MODE"] = "cut:2"
        rows = Q.chay(self.client, task_id=TASK_RE, phien=7, note="cặp-giả",
                      thu_muc=self.tmp / "q", gia=True, out=io.StringIO())
        self.assertEqual([r["nhan"] for r in rows], ["xong", "cắt"] + ["xong"] * 5)
        self.assertEqual(rows[1]["exit_status"], "infra")
        self.assertIn(Q.DAU_HIEU_CAT, rows[1]["loi"])
        self.assertEqual(len(Q.doc_so(self.tmp / "q")), 7, "sổ phải đọc lại được từ đĩa")
        self.assertTrue(all(r["gia"] for r in Q.doc_so(self.tmp / "q")))

    def test_moi_phien_co_cay_lam_viec_rieng(self):
        """Dùng chung một cây thì phiên sau xoá bằng chứng của phiên trước."""
        os.environ["AISEF_SELFCHECK_MODE"] = "fix"
        rows = Q.chay(self.client, task_id=TASK_RE, phien=3, note="cặp-giả",
                      thu_muc=self.tmp / "q", gia=True, out=io.StringIO())
        self.assertEqual(len({r["ws"] for r in rows}), 3)

    def test_dung_som_khi_cap_khong_con_dat_duoc(self):
        """Trần của cohort 6 phiên là ⌊6/6⌋ = 1, nên phiên cắt thứ hai chốt xong
        phán quyết — mỗi phiên sau đó là tiền đổ vào câu trả lời đã biết."""
        os.environ["AISEF_SELFCHECK_MODE"] = "cut:1,2"
        rows = Q.chay(self.client, task_id=TASK_RE, phien=6, note="cặp-giả",
                      thu_muc=self.tmp / "q", gia=True, out=io.StringIO())
        self.assertEqual(len(rows), 2)

    def test_tran_thoi_gian_cat_dot_va_cho_ra_chua_ket_luan(self):
        os.environ["AISEF_SELFCHECK_MODE"] = "fix"
        rows = Q.chay(self.client, task_id=TASK_RE, phien=4, note="cặp-giả",
                      thu_muc=self.tmp / "q", tran_phut=0.0, gia=True, out=io.StringIO())
        self.assertEqual(rows, [])

    def test_phien_tuyen_giong_hinh_dang_nhanh_AISEF_cua_cohort(self):
        """Chống trôi: đề bài, env và argv của phiên tuyển phải bằng của
        `_runner.run` cho cùng task. Lệch là đo một thứ khác cột 2 sẽ chạy."""
        os.environ["AISEF_SELFCHECK_MODE"] = "fix"
        from tests.bench import _mine as M

        task = {t.id: t for t in M.load_tasks(M.TASKS_DIR, M.KEEP_DIR / "tasks")}[TASK_RE]
        R.run(task, self.client, attempts=1, bare=False, note="cohort")
        Q.chay(self.client, task_id=TASK_RE, phien=1, note="tuyển",
               thu_muc=self.tmp / "q", gia=True, out=io.StringIO())
        cohort, tuyen = self._goi()[0], self._goi()[-1]

        def _bo_duong_dan(o: dict) -> dict:
            ws = o["dir"]
            return {"argv": [a.replace(ws, "<WS>") for a in o["argv"]],
                    "prompt": o["prompt"].replace(ws, "<WS>"),
                    "env": o["env"]}

        self.assertEqual(_bo_duong_dan(cohort), _bo_duong_dan(tuyen))


class TestCliKhongTieuGiKhiChuaDuocPhep(unittest.TestCase):
    """`--du-toan` là hoá đơn: nó phải in ra được mà không gọi client, không cần
    `AISEF_BENCH=1`, và không ghi một dòng sổ nào."""

    def _chay(self, argv: list[str]) -> tuple[int, str]:
        import contextlib
        import io

        from tests.bench.__main__ import main

        ra = io.StringIO()
        with contextlib.redirect_stdout(ra), contextlib.redirect_stderr(ra):
            ma = main(argv)
        return ma, ra.getvalue()

    def test_du_toan_in_hoa_don_va_khong_chay_gi(self):
        cu = os.environ.pop("AISEF_BENCH", None)
        try:
            ma, ra = self._chay(["qualify", "--client", "opencode", "--du-toan"])
        finally:
            if cu is not None:
                os.environ["AISEF_BENCH"] = cu
        self.assertEqual(ma, 0)
        self.assertIn("KHÔNG chạy gì", ra)
        self.assertIn(f"**{Q.SO_PHIEN_TUYEN}**", ra)
        self.assertIn("0,00 USD", ra)
        self.assertIn("không nói gì", ra, "hoá đơn phải nói rõ giá 0,00 không đo được gì")

    def test_du_toan_in_luat_quyet_dinh_va_so_phien_cap_xau_thuong_ton(self):
        ra = Q.du_toan("opencode", "", Q.TASK_TUYEN, Q.SO_PHIEN_TUYEN)
        self.assertIn("≤ 4 phiên bị cắt trên 28 phiên hợp lệ", ra)
        self.assertIn("≈ 17 phiên", ra)
        self.assertIn("35 % giờ phiên", ra)

    def test_khong_co_AISEF_BENCH_thi_khong_chay_client_that(self):
        cu = os.environ.pop("AISEF_BENCH", None)
        try:
            ma, ra = self._chay(["qualify", "--client", "opencode", "--note", "x"])
        finally:
            if cu is not None:
                os.environ["AISEF_BENCH"] = cu
        self.assertEqual(ma, 1)
        self.assertIn("AISEF_BENCH=1", ra)

    def test_thieu_note_thi_khong_chay(self):
        """`mycombo` là alias: một đợt không có lời khai model không đọc được về sau.

        `R.ENABLED` đọc `AISEF_BENCH` lúc **nhập module**, nên phép kiểm vá thẳng
        vào cờ ấy — đặt biến môi trường ở đây thì đã muộn, và nó cũng là cách duy
        nhất đi được tới nhánh sau khi không dựng một client thật.
        """
        from unittest.mock import patch

        with patch.object(R, "ENABLED", True):
            ma, ra = self._chay(["qualify", "--client", "opencode"])
        self.assertEqual(ma, 2)
        self.assertIn("--note", ra)


if __name__ == "__main__":
    unittest.main()


class TestTienKiemTruocKhiTuyen(unittest.TestCase):
    """Chủ dự án, ràng buộc 2: *trước* bất kỳ phiên tuyển model↔CLI **thật** nào,
    phải kiểm và ghi bốn thứ — `PREREG_FROZEN` đúng, `protocol_digest` bằng bản
    ghim, selfcheck 19/19, và ngưỡng đã cố định trước khi có dữ liệu. *"Do not
    launch qualification if any of these is false."*

    Vì sao là một cửa chặn chứ không phải một bản ghi: một bản ghi kiểm xong rồi
    vẫn phóng được. Cửa nằm ở đúng lệnh tiêu tiền.
    """

    def test_tien_kiem_dat_tren_kho_that(self):
        from tests.bench import _qualify as Q
        ok, hong, rec = Q.tien_kiem()
        self.assertTrue(ok, f"tiền kiểm hỏng: {hong}")
        self.assertTrue(rec["prereg_frozen"])
        self.assertRegex(rec["protocol_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual((rec["selfcheck_passed"], rec["selfcheck_total"]), (19, 19))
        self.assertTrue(rec["thresholds_fixed_before_data"])

    def test_selfcheck_thieu_thi_tien_kiem_hong(self):
        """Không có bản ghi selfcheck là *không biết*, và không biết thì không phóng."""
        from tests.bench import _qualify as Q
        ok, hong, _ = Q.tien_kiem(selfcheck=Path("/khong/co/that.json"))
        self.assertFalse(ok)
        self.assertTrue(any("selfcheck" in h for h in hong), hong)

    def test_mot_hang_so_lech_van_ban_ghim_thi_tien_kiem_hong(self):
        """Đổi ngưỡng trong mã mà không ghim lại văn bản: bar hậu nghiệm."""
        from tests.bench import _qualify as Q
        goc = Q.SO_PHIEN_TUYEN
        try:
            Q.SO_PHIEN_TUYEN = goc + 1
            ok, hong, _ = Q.tien_kiem()
            self.assertFalse(ok)
            self.assertTrue(any("SO_PHIEN_TUYEN" in h for h in hong), hong)
        finally:
            Q.SO_PHIEN_TUYEN = goc
