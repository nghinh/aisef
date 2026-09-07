"""Thay đổi này chạm tới đâu — ngữ cảnh cho người rà soát.

Mục đáng giá nhất là `untested_symbols`: khuôn thất bại lặp lại nhiều
nhất trên e9 là "code có mặt nhưng không test nào chứng minh nó chạy" —
`registerSW` ở STORY-01-01, `roving tabindex` và `watchNotes` ở
STORY-01-04. Ba story, cùng một khuôn.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.impact import (  # noqa: E402
    COMMON_DEFS,
    ImpactReport,
    analyse,
    builtin,
    is_test_path,
    refs,
    symbols,
    weights,
)


class ImpactTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.p = Path(self._tmp.name)
        for d in ("src", "src/ui", "tests"):
            (self.p / d).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, body):
        f = self.p / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")
        return rel


class TestBuiltin(ImpactTestCase):
    def du_an(self):
        self.write("src/main.ts", (
            'export function registerSW() { navigator.serviceWorker.register("/sw.js") }\n'
            "export function watchNotes(cb) { return cb }\n"
            'export const APP_NAME = "ghi-chu"\n'
        ))
        self.write("src/ui/app.ts", 'import { registerSW } from "../main"\nregisterSW()\n')
        self.write("tests/app.test.ts", (
            'import { APP_NAME } from "../src/main"\n'
            'test("ten", () => expect(APP_NAME).toBe("ghi-chu"))\n'
        ))

    def test_tim_ra_ten_khong_test_nao_nhac_toi(self):
        """Đúng thứ người rà soát chặn ba lần trên e9."""
        self.du_an()
        r = builtin(self.p, ["src/main.ts"])
        self.assertEqual(r.untested_symbols, ["registerSW", "watchNotes"])

    def test_tim_ra_noi_dung_va_test_lien_quan(self):
        self.du_an()
        r = builtin(self.p, ["src/main.ts"])
        self.assertEqual(r.callers, ["src/ui/app.ts"])
        self.assertEqual(r.related_tests, ["tests/app.test.ts"])
        self.assertIn("APP_NAME", r.changed_symbols)

    def test_tep_trong_diff_khong_tinh_la_noi_dung(self):
        """Chính tệp vừa sửa không phải "nơi dùng" của chính nó."""
        self.du_an()
        r = builtin(self.p, ["src/main.ts", "src/ui/app.ts"])
        self.assertNotIn("src/ui/app.ts", r.callers)

    def test_test_viet_canh_code_van_duoc_tinh(self):
        """Story hay viết test trong cùng lượt; test nằm trong diff mà
        không được tính thì mọi tên đều thành "không có test"."""
        self.write("src/moi.ts", "export function tinhTong(a, b) { return a + b }\n")
        self.write("src/moi.test.ts", (
            'import { tinhTong } from "./moi"\ntest("tong", () => tinhTong(1, 2))\n'
        ))
        r = builtin(self.p, ["src/moi.ts", "src/moi.test.ts"])
        self.assertEqual(r.untested_symbols, [])
        self.assertIn("src/moi.test.ts", r.related_tests)

    def test_bo_qua_thu_muc_phu_thuoc(self):
        self.du_an()
        self.write("node_modules/x/index.ts", "registerSW()\n")
        self.write(".claude/skills/x/scripts/process.py", "registerSW()\n")   # skill của agent, không phải mã dự án
        r = builtin(self.p, ["src/main.ts"])
        self.assertNotIn("node_modules/x/index.ts", r.callers)
        self.assertEqual(r.callers, ["src/ui/app.ts"])

    def test_khong_co_ten_xuat_khau_thi_noi_thang(self):
        self.write("src/rong.ts", "const cucBo = 1\n")
        r = builtin(self.p, ["src/rong.ts"])
        self.assertTrue(r.empty)
        self.assertIn("không thấy tên xuất khẩu", r.note)

    def test_luon_bao_la_tho(self):
        """Dò theo tên trùng là dính, gọi động không thấy — người đọc phải
        biết mức tin cậy."""
        self.du_an()
        self.assertTrue(builtin(self.p, ["src/main.ts"]).degraded)


class TestGiamTrong(ImpactTestCase):
    """Ba luật của Aider (ADR-005 V7): tên định nghĩa ở > 5 tệp ×0,1,
    `_private` bỏ, đếm √n. Trước đây `save`/`render` lấp `callers` rồi bị
    cắt lặng ở 12 mục — tệp gọi thật rơi ra ngoài danh sách."""

    def kho_ten_pho_bien(self):
        self.write("src/main.ts", "export function render() {}\nexport function watchNotes() {}\n")
        for i in range(COMMON_DEFS + 1):
            self.write(f"src/w{i}.ts", "export function render() {}\n")
        for i in range(15):
            self.write(f"src/chi-render-{i:02}.ts", "render()\n")
        self.write("src/goi-that.ts", "watchNotes()\n")

    def test_ten_o_sau_tep_khong_lot_callers(self):
        self.kho_ten_pho_bien()
        r = builtin(self.p, ["src/main.ts"])
        self.assertEqual(r.callers, ["src/goi-that.ts"])

    def test_do_truoc_sau_so_tep_callers(self):
        """Không giảm trọng: 22 tệp, tệp gọi thật đứng sau 15 tệp `chi-render-*`
        và 6 tệp `w*` → rơi ngoài 12 mục; có giảm trọng: 1 tệp, đúng tệp."""
        self.kho_ten_pho_bien()
        khong_giam = {rel for per in refs(self.p, ["render", "watchNotes"]).values() for rel in per}
        khong_giam = sorted(khong_giam - {"src/main.ts"})
        self.assertEqual(len(khong_giam), 15 + COMMON_DEFS + 1 + 1)
        self.assertGreater(khong_giam.index("src/goi-that.ts"), 12)
        self.assertEqual(len(builtin(self.p, ["src/main.ts"]).callers), 1)

    def test_trong_so_theo_ba_luat(self):
        self.kho_ten_pho_bien()
        w = weights(self.p, ["render", "watchNotes", "_rieng"])
        self.assertEqual(w, {"render": 0.1, "watchNotes": 1.0, "_rieng": 0.0})

    def test_symbols_bo_private_va_ten_ngan(self):
        self.write("src/x.py", "def _rieng():\n    pass\ndef ok():\n    pass\nclass KhoLuu:\n    pass\n")
        self.assertEqual(symbols(self.p, ["src/x.py"]), {"src/x.py": [("KhoLuu", 5, "class")]})

    def test_refs_dem_so_lan_mot_luot_quet(self):
        self.write("src/a.ts", "export function luuKho() {}\n")
        self.write("src/b.ts", "luuKho(); luuKho()\n")
        self.assertEqual(refs(self.p, ["luuKho"])["luuKho"], {"src/a.ts": 1, "src/b.ts": 2})

    def test_can_bac_hai_xep_truoc(self):
        """√n: tệp nhắc 100 lần đứng trước tệp nhắc 1 lần, nhưng chỉ hơn 10
        lần điểm chứ không 100 — không đè được tên có trọng số đầy."""
        self.write("src/main.ts", "export function watchNotes() {}\n")
        self.write("src/nhieu.ts", "watchNotes()\n" * 100)
        self.write("src/it.ts", "watchNotes()\n")
        self.assertEqual(builtin(self.p, ["src/main.ts"]).callers, ["src/nhieu.ts", "src/it.ts"])


class TestProviderNgoai(ImpactTestCase):
    def test_lenh_ngoai_duoc_dung_khi_cau_hinh(self):
        ket = {
            "changed_symbols": ["capNhatGhiChu"],
            "callers": ["src/ui/list.tsx"],
            "related_tests": ["tests/list.test.ts"],
            "flows": ["mở ứng dụng → tải danh sách"],
        }
        cmd = f"python3 -c \"import json;print(json.dumps({ket!r}))\""
        r = analyse(self.p, ["src/a.ts"], command=cmd)
        self.assertEqual(r.callers, ["src/ui/list.tsx"])
        self.assertEqual(r.flows, ["mở ứng dụng → tải danh sách"])
        self.assertFalse(r.degraded)

    def test_lenh_hong_thi_lui_ve_ban_dung_san_va_noi_ra(self):
        """Trả rỗng im lặng là tệ nhất: người rà soát không phân biệt được
        "không có ảnh hưởng" với "không ai tính"."""
        self.write("src/main.ts", "export function motHam() { return 1 }\n")
        r = analyse(self.p, ["src/main.ts"], command="khong-co-lenh-nay --json")
        self.assertTrue(r.degraded)
        self.assertIn("chạy hỏng", r.note)
        self.assertIn("motHam", r.changed_symbols)

    def test_json_hong_cung_lui_ve(self):
        self.write("src/main.ts", "export function motHam() { return 1 }\n")
        r = analyse(self.p, ["src/main.ts"], command="echo 'không phải json'")
        self.assertTrue(r.degraded)

    def test_khoa_la_bi_bo_qua_khoa_thieu_thanh_rong(self):
        """Một công cụ ngoài đổi định dạng không đáng làm hỏng cả lượt."""
        r = ImpactReport.from_json({"affected": ["a.ts"], "vo_nghia": 1}, source="x")
        self.assertEqual(r.callers, ["a.ts"])
        self.assertEqual(r.related_tests, [])


class TestPrompt(ImpactTestCase):
    def test_rong_thi_noi_la_chua_cau_hinh_khong_im_lang(self):
        self.assertIn("Chưa có phân tích ảnh hưởng", ImpactReport().as_prompt())

    def test_noi_ro_nguon_va_gioi_han(self):
        r = ImpactReport(changed_symbols=["a"], source="thử", degraded=True)
        out = r.as_prompt()
        self.assertIn("thử", out)
        self.assertIn("thô", out)
        self.assertIn("không phải chân lý", out)

    def test_cat_bot_khi_qua_dai(self):
        r = ImpactReport(callers=[f"f{i}.ts" for i in range(40)], source="x")
        out = r.as_prompt()
        self.assertIn("còn 28", out)

    def test_khong_co_in_dam_long_nhau(self):
        r = ImpactReport(untested_symbols=["a"], source="x")
        self.assertNotIn("**Tên **", r.as_prompt())


class TestNhanDangTest(unittest.TestCase):
    def test_nhan_dung_duong_dan_test(self):
        for p in ("tests/a.ts", "src/a.test.ts", "src/a.spec.tsx",
                  "__tests__/a.js", "e2e/mua-hang.spec.ts", "test_x.py"):
            with self.subTest(p=p):
                self.assertTrue(is_test_path(p), p)

    def test_khong_nhan_nham_ma_thuong(self):
        for p in ("src/latest.ts", "src/contest.ts", "src/protest/a.ts"):
            with self.subTest(p=p):
                self.assertFalse(is_test_path(p), p)


class TestReviewerNhanDuoc(unittest.TestCase):
    """Regression bắt buộc: blast-radius trả caller/test thì người rà soát
    phải nhận được — không phải chỉ tính rồi bỏ đó."""

    def test_impact_di_vao_prompt_ra_soat(self):
        import tempfile

        from aisef.harness.prompts import load_catalog

        prompt = load_catalog().get("story-review")
        self.assertIn("{{ impact }}", prompt.body)

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "src").mkdir()
            (p / "src" / "main.ts").write_text(
                "export function registerSW() { return 1 }\n", encoding="utf-8"
            )
            out = builtin(p, ["src/main.ts"]).as_prompt()
            self.assertIn("registerSW", out)


class TestShellInjectionRegression(unittest.TestCase):
    """Regression: _run_command must use shlex.split, never shell=True."""

    def test_run_command_uses_shlex_split(self):
        import inspect
        from aisef.control.impact import _run_command
        src = inspect.getsource(_run_command)
        self.assertNotIn("shell=True", src)
        self.assertIn("shlex.split", src)


if __name__ == "__main__":
    unittest.main()
