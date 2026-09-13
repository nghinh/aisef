"""Map mockup — hai nửa: nạp lát cắt, rồi đối chiếu route thật.

Nửa đối chiếu chạy thật: dựng một "ứng dụng" tĩnh bằng `http.server`, mở
route bằng chromium, đọc cây accessibility. Không giả lập chỗ nào, vì cái
cần chứng minh chính là chuỗi đó chạy được.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control.design_contract import load  # noqa: E402
from aisef.control.experience import parse_experience_file  # noqa: E402
from aisef.harness import browser  # noqa: E402
from aisef.harness.mockup_map import load_for_story, load_slice, prompt_section  # noqa: E402
from aisef.harness.mockup_verify import (  # noqa: E402
    AppServer,
    concrete_route,
    verify_screens,
)
from aisef.harness.observe import MOCKUP_MAP, EvidenceStore  # noqa: E402
from aisef.phases.mockup import extract  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
BROWSER_REASON = browser.availability(ROOT)


def build_contract(root: Path):
    (root / "mockups").mkdir(parents=True, exist_ok=True)
    for p in (FIX / "mockups").glob("*.html"):
        shutil.copy(p, root / "mockups" / p.name)
    extract(root, parse_experience_file(FIX / "bmad" / "EXPERIENCE.md"))
    return load(root)


@unittest.skipIf(BROWSER_REASON, f"không dựng được mockup: {BROWSER_REASON}")
class TestLoadHalf(unittest.TestCase):
    """6.7a — nạp đúng một màn hình, không hơn."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        cls.contract = build_contract(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_loads_only_the_named_screen(self):
        text = prompt_section(
            load_for_story(self.contract, ["danh-sach"], artifact_root=self.root)[0]
        )
        self.assertIn("danh-sach", text)
        for other in ("thung-rac", "cai-dat"):
            self.assertNotIn(other, text)
        self.assertNotIn("Screen `the`", text)

    def test_slice_carries_route_and_components(self):
        sl = load_slice(self.contract, "danh-sach", artifact_root=self.root)
        text = sl.as_prompt()
        self.assertIn("`/`", text)
        self.assertIn("Ghi chú mới", text)

    def test_slice_points_at_mockup_and_screenshot(self):
        sl = load_slice(self.contract, "danh-sach", artifact_root=self.root)
        self.assertTrue(sl.mockup_path.is_file())
        self.assertTrue(sl.screenshot_path.is_file())

    def test_sample_data_is_not_a_commitment(self):
        """Nội dung ví dụ trong `[data-sample]` không được thành cam kết —
        ứng dụng thật hiển thị dữ liệu khác, cổng sẽ đỏ mãi mãi."""
        sl = load_slice(self.contract, "danh-sach", artifact_root=self.root)
        names = [c.name for c in sl.screen.components]
        self.assertNotIn("Đặt lịch khám răng 2 phút trước", names)
        self.assertIn("link", sl.screen.data_roles)
        self.assertIn("Data region", sl.as_prompt())

    def test_validation_constraints_go_into_the_prompt(self):
        text = load_slice(self.contract, "danh-sach", artifact_root=self.root).as_prompt()
        self.assertIn("maxlength=120", text)

    def test_unknown_screen_is_reported_not_silently_empty(self):
        slices, missing = load_for_story(
            self.contract, ["danh-sach", "khong-co"], artifact_root=self.root
        )
        self.assertEqual(len(slices), 1)
        self.assertEqual(missing, ["khong-co"])

    def test_story_without_screens_says_so(self):
        text = prompt_section([])
        self.assertIn("does not build any screen", text)


class TestRouteRewrite(unittest.TestCase):
    def test_params_get_a_sample_value(self):
        self.assertEqual(concrete_route("/note/:id"), "/note/1")
        self.assertEqual(concrete_route("/blog/[slug]/edit"), "/blog/1/edit")

    def test_plain_route_untouched(self):
        self.assertEqual(concrete_route("/settings"), "/settings")


@unittest.skipIf(BROWSER_REASON, f"không dựng được mockup: {BROWSER_REASON}")
class TestVerifyHalf(unittest.TestCase):
    """6.7b/6.7c — mở route thật, đối chiếu, và cổng phải chặn khi thiếu."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.artifacts = self.root / "_bmad-output"
        self.contract = build_contract(self.artifacts)
        self.app = self.root / "app"
        self.app.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def serve(self, body: str) -> Config:
        # `<meta charset>` không phải chi tiết vụn: thiếu nó thì trình duyệt
        # giải mã UTF-8 thành latin-1 và mọi tên gọi tiếng Việt lệch — trang
        # hỏng thật với người dùng, và cổng phát hiện đúng.
        page = (
            "<!doctype html><html lang=vi><head><meta charset=\"utf-8\">"
            "<title>App</title></head><body>" + body + "</body></html>"
        )
        (self.app / "index.html").write_text(page, encoding="utf-8")
        port = _free_port()
        return Config({
            **DEFAULTS,
            "app.dev_command": f"{sys.executable} -m http.server {port} --directory {self.app}",
            "app.base_url": f"http://127.0.0.1:{port}",
            "app.ready_timeout_seconds": 20,
        })

    def run_verify(self, cfg: Config):
        return verify_screens(
            self.root, self.contract, ["danh-sach"],
            config=cfg, story_id="STORY-01-01", artifact_root=self.artifacts,
        )

    def test_app_that_honours_the_contract_passes(self):
        cfg = self.serve(
            '<input type="search" aria-label="Tìm ghi chú">'
            "<button>Ghi chú mới</button>"
            '<ul><li><a href="#">Ghi chú thật từ cơ sở dữ liệu</a></li></ul>'
        )
        res = self.run_verify(cfg)
        self.assertTrue(res.passed, res.summary())

    def test_missing_component_fails_the_gate(self):
        """Thiếu một component đã hứa → cổng chặn. Đây là lý do cả hai nửa
        tồn tại."""
        cfg = self.serve(
            '<input type="search" aria-label="Tìm ghi chú">'
            '<ul><li><a href="#">Một ghi chú</a></li></ul>'
        )
        res = self.run_verify(cfg)
        self.assertFalse(res.passed)
        self.assertIn("Ghi chú mới", res.summary())

    def test_trang_404_khong_phai_ung_dung_thieu_component(self):
        """Lỗi 35. Trang lỗi của máy chủ **cũng là** một trang: nó có tiêu đề,
        có phần tử, và bộ so sánh chấm nó như thể ứng dụng dựng thiếu mọi thứ.

        Đo 2026-09-09 trên `todo`: route trong hợp đồng là một câu tiếng Anh
        ("Single initial document; no route change required"), `http.server`
        trả 404, cổng báo thiếu cả 6 component, và story đốt hết 3 lượt sửa mã
        không hỏng. Dấu vết duy nhất là `extra: heading "Error response"`.
        """
        cfg = self.serve("<button>Ghi chú mới</button>")
        self.contract.by_id("danh-sach").route = "/khong-he-co-duong-nay"
        res = self.run_verify(cfg)
        self.assertFalse(res.passed)
        ev = EvidenceStore(self.artifacts).read("STORY-01-01").last(MOCKUP_MAP, "danh-sach")
        self.assertIn("404", str(ev.detail.get("error", "")),
                      f"phải nói route không mở được, không phải 'thiếu component': {ev.detail}")

    def test_extra_component_only_warns(self):
        cfg = self.serve(
            '<input type="search" aria-label="Tìm ghi chú">'
            "<button>Ghi chú mới</button><button>Sắp xếp</button>"
            '<ul><li><a href="#">Một ghi chú</a></li></ul>'
        )
        res = self.run_verify(cfg)
        self.assertTrue(res.passed)
        self.assertIn("Sắp xếp", res.summary())

    def test_different_data_content_is_not_a_failure(self):
        """Ứng dụng hiển thị ghi chú thật, không phải ghi chú mẫu — đúng
        như mong đợi, và không được coi là lệch hợp đồng."""
        cfg = self.serve(
            '<input type="search" aria-label="Tìm ghi chú">'
            "<button>Ghi chú mới</button>"
            '<ul><li><a href="#">Hoàn toàn khác mockup</a></li></ul>'
        )
        self.assertTrue(self.run_verify(cfg).passed)

    def test_vung_du_lieu_rong_thi_chua_so_duoc_chu_khong_phai_thieu(self):
        """Lỗi 56. Danh sách rỗng và "chưa dựng ô tích" trông y hệt nhau ở đây,
        và story đầu tiên của một dự án **không có cách nào** làm nó khác đi:
        nó dựng vỏ trước khi có bất cứ thứ gì tạo được bản ghi, còn ứng dụng
        lưu trong trình duyệt thì dev server không có gì để gieo.

        Đo 2026-09-09: `todo` và `todo-e2e` cùng trượt vì `checkbox` thiếu
        trong một danh sách rỗng — cả hai đều không thể qua được. Vẫn báo ra,
        chỉ thôi chặn."""
        cfg = self.serve(
            '<input type="search" aria-label="Tìm ghi chú">'
            "<button>Ghi chú mới</button>"
        )
        res = self.run_verify(cfg)
        self.assertTrue(res.passed, res.summary())
        self.assertIn("data region was empty", res.summary())
        e = EvidenceStore(self.artifacts).read("STORY-01-01").last(MOCKUP_MAP)
        self.assertEqual(e.detail["missing_data_roles"], [])
        self.assertEqual(e.detail["unchecked_data_roles"], ["link"])

    def test_co_dong_ma_khong_co_vai_thi_van_chan(self):
        """Đối chứng: vùng dữ liệu **có** bản ghi mà không mang vai hợp đồng
        hứa — đây mới là lệch thật, và vẫn phải chặn."""
        cfg = self.serve(
            '<input type="search" aria-label="Tìm ghi chú">'
            "<button>Ghi chú mới</button>"
            "<ul><li>chỉ là chữ, không có liên kết</li></ul>"
        )
        res = self.run_verify(cfg)
        self.assertFalse(res.passed, res.summary())
        self.assertIn("has rows", res.summary())

    def test_evidence_records_the_comparison(self):
        cfg = self.serve("trống")
        self.run_verify(cfg)
        e = EvidenceStore(self.artifacts).read("STORY-01-01").last(MOCKUP_MAP)
        self.assertIsNotNone(e)
        self.assertFalse(e.ok)
        self.assertEqual(e.detail["screen_id"], "danh-sach")
        self.assertTrue(e.detail["missing"])

    def test_no_dev_command_is_reported_not_passed(self):
        """Không mở được ứng dụng thì **không** phải là đạt."""
        res = verify_screens(
            self.root, self.contract, ["danh-sach"],
            config=Config({**DEFAULTS, "app.base_url": f"http://127.0.0.1:{_free_port()}"}),
        )
        self.assertFalse(res.passed)
        self.assertIn("app.dev_command", res.unavailable)

    def test_story_without_screens_needs_no_app(self):
        res = verify_screens(self.root, self.contract, [], config=Config(dict(DEFAULTS)))
        self.assertTrue(res.passed)
        self.assertEqual(res.results, [])


class TestAppServerTrust(unittest.TestCase):
    """Lỗi 15: thứ đang trả lời ở cổng không phải app của story này."""

    def test_refuses_foreign_responder(self):
        from unittest import mock

        from aisef.harness import mockup_verify as mv

        s = AppServer("echo x", "http://127.0.0.1:1", cwd=Path("."))
        with mock.patch.object(mv, "_responds", return_value=True), \
                mock.patch.object(mv, "occupant", return_value="pid 1, cwd /x"):
            why = s.start()
        self.assertIn("another process", why)
        self.assertIn("pid 1", why)
        self.assertIsNone(s.proc)

    def test_windows_kills_the_tree_with_taskkill(self):
        """Windows has no process groups: only `taskkill /T` reaches the
        children, and a surviving dev server holds the port for the next
        story (bug 15's shape)."""
        from unittest import mock

        from aisef.harness import mockup_verify as mv

        proc = mock.Mock(pid=4242)
        with mock.patch.object(mv.sys, "platform", "win32"), \
             mock.patch.object(mv.subprocess, "call", return_value=0) as call:
            mv._kill_tree(proc)
        self.assertEqual(call.call_args[0][0][:4], ["taskkill", "/F", "/T", "/PID"])
        proc.wait.assert_called_once()

    @unittest.skipIf(sys.platform == "win32",
                     "process groups + os.kill are POSIX; Windows uses taskkill /T, "
                     "covered by test_windows_kills_the_tree_with_taskkill")
    def test_stop_kills_whole_process_group(self):
        import os
        import tempfile
        import time

        with tempfile.TemporaryDirectory() as d:
            pidfile = Path(d) / "child.pid"
            # cha = shell; con = sleep. Chỉ giết cha thì con sống sót (vite).
            cmd = f"sh -c 'sleep 30 & echo $! > {pidfile}; wait'"
            s = AppServer(cmd, "http://127.0.0.1:1", cwd=Path(d), ready_timeout=1)
            s.start()  # không bao giờ "sẵn sàng" — chỉ cần tiến trình đã chạy
            for _ in range(50):
                if pidfile.is_file() and pidfile.read_text(encoding="utf-8").strip():
                    break
                time.sleep(0.05)
            child = int(pidfile.read_text(encoding="utf-8").strip())
            s.stop()
            time.sleep(0.2)
            with self.assertRaises(ProcessLookupError):
                os.kill(child, 0)


class TestAppServer(unittest.TestCase):
    def test_url_join(self):
        s = AppServer("", "http://x:3000", cwd=Path("."))
        self.assertEqual(s.url_for("/note/1"), "http://x:3000/note/1")
        self.assertEqual(s.url_for("/"), "http://x:3000/")

    def test_dev_server_that_dies_is_reported(self):
        s = AppServer(f'"{sys.executable}" -c "raise SystemExit(3)"',
                      f"http://127.0.0.1:{_free_port()}", cwd=Path("."), ready_timeout=10)
        why = s.start()
        s.stop()
        self.assertIn("exited early", why)


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestDoiTenNhanThiPhaiNoiRa(unittest.TestCase):
    """Lỗi 44. Đổi tên nhãn là cách phổ biến nhất khiến một component "biến
    mất", và nói mỗi "missing" đẩy tác giả đi tìm một trường đang nằm ngay
    trên màn hình trước mặt.

    Đo trên todo/STORY-02-01 2026-09-09: cổng báo `missing: textbox
    "Description"` suốt 3 lượt, trong khi `textbox "Description (optional)"`
    nằm sẵn trong `extra` cả ba lần. Story cạn lượt.
    """

    def _ket_qua(self, ten_that: str):
        from aisef.harness.aria import Component, compare
        return compare(
            [Component(role="textbox", name="Description"),
             Component(role="button", name="Add Task")],
            [Component(role="textbox", name=ten_that),
             Component(role="button", name="Add Task")],
            screen_id="todo-list",
        )

    def test_chi_ra_ten_dang_hien(self):
        r = self._ket_qua("Description (optional)")
        self.assertEqual(r.renamed(), [('textbox "Description"',
                                        'textbox "Description (optional)"')])
        self.assertIn("Description (optional)", r.summary())
        self.assertIn("re-approve", r.summary())
        self.assertEqual(r.to_evidence()["renamed"],
                         [['textbox "Description"', 'textbox "Description (optional)"']])

    def test_khong_ghep_bua_thu_khong_lien_quan(self):
        r = self._ket_qua("Ngày hết hạn")
        self.assertEqual(r.renamed(), [], "hai tên không liên quan thì không được đoán")

    def test_khong_ghep_khac_vai(self):
        from aisef.harness.aria import Component, compare
        r = compare([Component(role="textbox", name="Description")],
                    [Component(role="heading", name="Description")], screen_id="s")
        self.assertEqual(r.renamed(), [], "cùng tên khác vai không phải đổi tên")


@unittest.skipIf(BROWSER_REASON, f"không dựng được mockup: {BROWSER_REASON}")
class TestTenKhaTruyCapTheoThuTuARIA(unittest.TestCase):
    """`render.mjs` rút `fields[].label` cho slot **Input constraints** của
    prompt developer (`harness/mockup_map.py`). Nó tính tên khả truy cập bằng
    `el.labels[0] || aria-label || placeholder` — ngược thứ tự chuẩn ARIA, và
    không xét `aria-labelledby` lần nào. Hệ quả: một mockup đúng chuẩn
    (`<label>Search</label>` kèm `aria-label="Tìm ghi chú"`) báo cho developer
    tên ràng buộc là "Search".

    Ghi cho người đọc sau: chỗ này **không** phải nguyên nhân của cổng
    `mockup map` — component đối chiếu qua ARIA snapshot của Playwright, vốn
    tính đúng. Tôi đã quy kết nhầm một lần rồi mới đo ra; sửa vì nó sai, không
    vì nó làm hỏng cổng.
    """

    def _label(self, html: str) -> str:
        import tempfile as _tf

        from aisef.harness import browser
        with _tf.TemporaryDirectory() as tmp:
            f = Path(tmp) / "m.html"
            f.write_text('<!doctype html><html lang=vi><head><meta charset="utf-8">'
                         "<title>t</title></head><body>" + html + "</body></html>",
                         encoding="utf-8")
            res = browser.render(
                [{"id": "s", "html": str(f), "png": str(f.with_suffix(".png"))}],
                project=ROOT)
            self.assertFalse(res.unavailable, res.unavailable)
            man = res.screens[0]
            self.assertFalse(man.error, man.error)
            return (man.fields[0]["label"] if man.fields else "")

    def test_aria_label_thang_nhan_goc(self):
        self.assertEqual(
            self._label('<label for="q">Search</label>'
                        '<input id="q" aria-label="Tìm ghi chú">'),
            "Tìm ghi chú")

    def test_aria_labelledby_thang_tat_ca(self):
        self.assertEqual(
            self._label('<span id="L">Nội dung ghi chú</span>'
                        '<label for="q">Search</label>'
                        '<input id="q" aria-label="khac" aria-labelledby="L">'),
            "Nội dung ghi chú")

    def test_khong_co_aria_thi_dung_nhan_goc(self):
        self.assertEqual(
            self._label('<label for="q">Nội dung ghi chú</label><input id="q">'),
            "Nội dung ghi chú")

    def test_chi_con_placeholder_hoac_title(self):
        self.assertEqual(self._label('<input placeholder="Tìm">'), "Tìm")
        self.assertEqual(self._label('<input title="Tìm">'), "Tìm")
