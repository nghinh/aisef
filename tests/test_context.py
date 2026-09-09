"""Bản đồ mã quanh phạm vi ghi (ADR-005 V7) — `harness/context.py`.

Ba điều phải đúng: bản đồ nói ra thứ ở **quanh** phạm vi (ai gọi, test nào
chạm) chứ không chép tệp; tên phổ biến không lấp bản đồ; và bản đồ không
bao giờ vượt ngân sách — vượt là ăn vào trần B5 mà không ai thấy.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control.normalize import Story  # noqa: E402
from aisef.harness.context import HEADING, prompt_section, repo_map, seeds_for  # noqa: E402


class ContextTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.p = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, body):
        f = self.p / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")
        return rel

    def du_an(self):
        self.write("src/a.ts", (
            'import { luuKho } from "./store"\n'
            "export function taoGhiChu(text: string) {\n  return luuKho(text)\n}\n"
            "export class BoDem {\n  dem = 0\n}\n"
        ))
        self.write("src/store.ts", "export function luuKho(t: string) { return t }\n")
        self.write("src/ui/app.ts", 'import { taoGhiChu } from "../a"\ntaoGhiChu("x")\n')
        self.write("tests/a.test.ts", 'import { taoGhiChu } from "../src/a"\ntest("t", () => taoGhiChu("y"))\n')
        self.write("src/khac.ts", "export const KHAC = 1\n")


class TestBanDoQuanhPhamVi(ContextTestCase):
    def test_skeleton_tep_goi_va_test_nhac(self):
        """AC của ADR-005 V7: scope `src/a.ts` → skeleton `a.ts`, tệp gọi
        `a.ts`, test nhắc `a.ts`; tệp không liên quan không xuất hiện."""
        self.du_an()
        out = repo_map(self.p, ["src/a.ts"])
        self.assertIn("`src/a.ts`", out)
        self.assertIn("export function taoGhiChu(text: string) …", out)   # chữ ký, thân → …
        self.assertNotIn("return luuKho", out)                          # không chép thân
        self.assertIn("`src/ui/app.ts` · taoGhiChu", out)                # gọi
        self.assertIn("`src/store.ts` · imported", out)              # được import
        self.assertIn("- `tests/a.test.ts` · taoGhiChu", out)           # test nhắc
        self.assertNotIn("khac.ts", out)
        self.assertLess(out.index("**In scope"), out.index("**1-hop neighbours"))
        self.assertLess(out.index("**1-hop neighbours"), out.index("**Tests referencing"))

    def test_chu_ky_nhieu_dong_va_so_dong_dung(self):
        """e9 `notes.ts`: `export function readNotesPage(` xuống dòng, và ba
        dòng trống phía trước từng làm số dòng lệch (regex `^\\s*`)."""
        self.write("src/n.ts", (
            "\n\n\nexport function readNotesPage(\n  store: Store,\n  from: number,\n"
            "): Promise<NotesPage> {\n  return x\n}\n"
            "export function AppShell({ onReload }: { onReload?: () => void }) {\n  return 1\n}\n"
            "export const APP_NAME = 1\nexport type Route = {\n  id: string\n}\n"
        ))
        out = repo_map(self.p, ["src/n.ts"])
        self.assertIn("  4 export function readNotesPage( store: Store, from: number, ): Promise<NotesPage> …", out)
        self.assertIn("  10 export function AppShell({ onReload }: { onReload?: () => void }) …", out)
        self.assertIn("  13 export const APP_NAME = 1 …", out)
        self.assertIn("  14 export type Route …", out)

    def test_python_skeleton_bang_ast(self):
        self.write("pkg/m.py", (
            "class Kho:\n    def __init__(self, path):\n        self.path = path\n"
            "    def luu(self, x: int) -> bool:\n        return True\n"
            "    def _rieng(self):\n        pass\n"
            "def tinh(a, b=1):\n    return a + b\n"
        ))
        out = repo_map(self.p, ["pkg/m.py"])
        self.assertIn("class Kho:", out)
        self.assertIn("    def luu(self, x: int) -> bool: …", out)
        self.assertIn("def tinh(a, b=1): …", out)
        self.assertNotIn("_rieng", out)
        self.assertNotIn("return a + b", out)

    def test_ten_pho_bien_khong_lot_lan_can(self):
        """Tên định nghĩa ở > 5 tệp (`render`) là tiếng ồn: tệp chỉ nhắc nó
        không được liệt kê là lân cận."""
        self.write("src/a.ts", "export function render() {}\nexport function duyNhat() {}\n")
        for i in range(6):
            self.write(f"src/w{i}.ts", "export function render() {}\n")
        self.write("src/goi-render.ts", "render()\n")
        self.write("src/goi-duy-nhat.ts", "duyNhat()\n")
        out = repo_map(self.p, ["src/a.ts"])
        self.assertIn("goi-duy-nhat.ts", out)
        self.assertNotIn("goi-render.ts", out)

    def test_khong_vuot_ngan_sach_va_chi_cho_tra(self):
        self.du_an()
        for i in range(30):
            self.write(f"src/g{i}.ts", f'import {{ taoGhiChu }} from "./a"\ntaoGhiChu("{i}")\n')
        for budget in (200, 500, 900):
            out = repo_map(self.p, ["src/a.ts"], budget, story_id="STORY-01-05")
            self.assertLessEqual(len(out), budget)
            self.assertIn("truncated — `aisef ctx --story STORY-01-05`", out)
        self.assertNotIn("truncated", repo_map(self.p, ["src/a.ts"], 0))

    def test_thu_muc_va_glob_la_pham_vi(self):
        self.du_an()
        self.assertIn("`src/store.ts`", repo_map(self.p, ["src"]).split("**1-hop neighbours")[0])
        self.assertIn("`src/ui/app.ts`", repo_map(self.p, ["src/**"]).split("**1-hop neighbours")[0])

    def test_hai_dau_sao_cho_cung_ket_qua_tren_moi_ban_python(self):
        """`src/**` và `src/**/*` phải ra cùng tệp.

        `Path.glob("src/**")` chỉ khớp **thư mục** ở Python ≤ 3.12; 3.13 mới
        cho khớp cả tệp. Gói khai hỗ trợ từ 3.11, nên phạm vi ghi viết kiểu
        `src/**` sẽ cho bản đồ rỗng ở nửa số bản được hỗ trợ nếu không chuẩn
        hoá (CI Linux 3.12 bắt được 2026-09-06, máy đo 3.14 thì không).
        """
        self.du_an()
        sao = repo_map(self.p, ["src/**"]).split("**1-hop neighbours")[0]
        sao_tep = repo_map(self.p, ["src/**/*"]).split("**1-hop neighbours")[0]
        self.assertEqual(sao, sao_tep)
        self.assertIn("`src/ui/app.ts`", sao)

    def test_ten_tep_khop_dinh_danh_story_xep_truoc(self):
        """Aider: tệp có tên khớp định danh được nhắc ×10 — `notes-list` trong
        story đẩy `notes-list.ts` lên trước tệp gọi nhiều hơn."""
        self.write("src/a.ts", "export function taoGhiChu() {}\n")
        self.write("src/notes-list.ts", "taoGhiChu()\n")
        self.write("src/khac.ts", "taoGhiChu()\ntaoGhiChu()\ntaoGhiChu()\n")
        out = repo_map(self.p, ["src/a.ts", "notes-list"])
        self.assertLess(out.index("notes-list.ts"), out.index("khac.ts"))

    def test_pham_vi_chua_co_tep_thi_noi_ra(self):
        out = repo_map(self.p, ["src/moi.ts", "taoGhiChu"])
        self.assertIn("no source files on disk", out)


class TestNhaCungCapNgoai(ContextTestCase):
    def test_lenh_ngoai_nhan_json_tra_van_ban(self):
        self.du_an()
        cmd = "python3 -c \"import json,sys; d=json.load(sys.stdin); print('MAP', d['budget'], *d['seeds'])\""
        out = repo_map(self.p, ["src/a.ts"], 500, command=cmd)
        self.assertIn("MAP 500 src/a.ts", out)
        self.assertIn("_Source: python3._", out)
        self.assertNotIn("In scope", out)

    def test_lenh_hong_thi_lui_ve_stdlib_va_noi_la_tho(self):
        self.du_an()
        out = repo_map(self.p, ["src/a.ts"], command="khong-co-lenh-nay --map")
        self.assertIn("failed", out.splitlines()[0])
        self.assertIn("**raw**", out.splitlines()[0])
        self.assertIn("export function taoGhiChu", out)


class TestHatGiongVaMucPrompt(ContextTestCase):
    def test_hat_giong_gom_pham_vi_duong_dan_kiem_dinh_va_dinh_danh(self):
        (self.p / "tests" / "e2e").mkdir(parents=True)
        (self.p / "_bmad-output" / "stories" / "EPIC-01").mkdir(parents=True)
        (self.p / "_bmad-output" / "stories" / "EPIC-01" / "STORY-01-05.md").write_text(
            "# STORY-01-05\n\nchạm nút tạo ghi chú ở `notes-list`, gọi `taoGhiChu`, id ngắn\n", encoding="utf-8")
        story = Story(id="STORY-01-05", epic_id="EPIC-01", title="t", write_scope=["src/a.ts"],
                      verification_contract=["e2e"])
        cfg = Config({**DEFAULTS, "verify.e2e": "npx playwright test tests/e2e"})
        got = seeds_for(story, self.p, artifact_root=self.p / "_bmad-output", config=cfg)
        self.assertEqual(got[0], "src/a.ts")
        self.assertIn("tests/e2e", got)
        self.assertIn("notes-list", got)
        self.assertIn("taoGhiChu", got)
        self.assertNotIn("id", got)            # < 5 ký tự
        self.assertNotIn("người", got)          # chữ thường tiếng Việt, không phải tên mã

    def test_muc_prompt_rong_khi_khong_co_ban_do(self):
        self.assertEqual(prompt_section(""), "")
        sec = prompt_section("bản đồ")
        self.assertTrue(sec.startswith(HEADING))
        self.assertIn("not ground truth", sec)
        self.assertIn("aisef ctx --story", sec)


class TestShellInjectionRegression(ContextTestCase):
    """Regression: _run_provider must split into argv, never shell=True."""

    def test_run_provider_splits_into_argv(self):
        import inspect
        from aisef.harness.context import _run_provider
        src = inspect.getsource(_run_provider)
        self.assertNotIn("shell=True", src)
        self.assertIn("split_command", src)  # POSIX shlex.split eats Windows path separators


if __name__ == "__main__":
    unittest.main()
