"""Bước mockup: dựng trang thật trong chromium, trích hợp đồng, chạy cổng.

Không có bản giả nào ở đây — mockup là HTML thật, được Playwright mở thật.
Trích hợp đồng bằng regex trên nguồn HTML sẽ "đạt" cả với thứ CSS đã ẩn
đi, nên bài test cũng phải đi qua trình duyệt thì mới nói lên điều gì.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.design_contract import CONTRACT_FILE, load  # noqa: E402
from aisef.control.experience import parse_experience, parse_experience_file  # noqa: E402
from aisef.control.machine_gate import check_design_contract  # noqa: E402
from aisef.control.normalize import Story  # noqa: E402
from aisef.harness import browser  # noqa: E402
from aisef.phases.mockup import (  # noqa: E402
    MockupResult,
    build_prompt,
    extract,
    write_index,
)

FIX = ROOT / "tests" / "fixtures"
EXPERIENCE = FIX / "bmad" / "EXPERIENCE.md"
MOCKUPS = FIX / "mockups"

BROWSER_REASON = browser.availability(ROOT)


class MockupTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)          # đóng vai _bmad-output
        (self.root / "mockups").mkdir()
        for p in MOCKUPS.glob("*.html"):
            shutil.copy(p, self.root / "mockups" / p.name)
        shutil.copy(EXPERIENCE, self.root / "EXPERIENCE.md")
        self.exp = parse_experience_file(self.root / "EXPERIENCE.md")

    def tearDown(self):
        self._tmp.cleanup()

    def fix_search_screen(self) -> None:
        """Vá hai lỗi cố ý trong mockup tìm kiếm."""
        p = self.root / "mockups" / "tim-kiem.html"
        text = p.read_text(encoding="utf-8")
        text = text.replace(
            '<meta name="aisef-screen" content="tim-kiem">',
            '<meta name="aisef-screen" content="tim-kiem">\n'
            '<meta name="aisef-route" content="/search">',
        )
        text = text[: text.index("<p data-unresolved")] + "</body></html>\n"
        p.write_text(text, encoding="utf-8")


class TestPrompt(unittest.TestCase):
    def test_prompt_carries_only_this_screen(self):
        exp = parse_experience_file(EXPERIENCE)
        p = build_prompt(exp.by_id("tim-kiem"), exp, Path("/x/_bmad-output"))
        self.assertIn("screen_id: tim-kiem", p)
        self.assertIn("aisef-mockup-html", p)
        self.assertIn("mockups/tim-kiem.html", p)
        self.assertNotIn("Thùng rác", p)  # không rò màn hình khác

    def test_prompt_includes_component_rules_and_states(self):
        exp = parse_experience_file(EXPERIENCE)
        p = build_prompt(exp.by_id("soan-thao"), exp, Path("/x/_bmad-output"))
        self.assertIn("Ô soạn thảo", p)
        self.assertIn("1 giây", p)          # luật hành vi đi kèm
        self.assertIn("data-unresolved", p)


@unittest.skipIf(BROWSER_REASON, f"không dựng được mockup: {BROWSER_REASON}")
class TestExtractContract(MockupTestCase):
    def test_contract_written_and_reloadable(self):
        contract, _ = extract(self.root, self.exp)
        self.assertTrue((self.root / CONTRACT_FILE).is_file())
        again = load(self.root)
        self.assertEqual(again.ids, contract.ids)

    def test_route_read_from_meta(self):
        contract, _ = extract(self.root, self.exp)
        self.assertEqual(contract.by_id("danh-sach").route, "/")
        self.assertEqual(contract.by_id("soan-thao").route, "/note/:id")

    def test_components_come_from_the_rendered_page(self):
        """`<h1 hidden>` nằm trong HTML nhưng người dùng không thấy — nó
        không phải cam kết, và cây accessibility đúng là không có nó."""
        contract, _ = extract(self.root, self.exp)
        names = [c.name for c in contract.by_id("danh-sach").components]
        self.assertIn("Ghi chú mới", names)
        self.assertIn("Tìm ghi chú", names)
        self.assertNotIn("Ghi chú", names)

    def test_state_section_marked_as_annotation_still_commits(self):
        """Lỗi 96: model đánh `data-annotation` lên chính `<section
        data-state="primary">`. Cả cây con bị trừ khỏi cam kết, hợp đồng còn
        **0 thành phần** trong khi mockup có đủ ô nhập, nút, ô tìm kiếm — và
        cổng vẫn PASS, nên khâu đối chiếu về sau không so gì cả."""
        p = self.root / "mockups" / "danh-sach.html"
        p.write_text(
            p.read_text(encoding="utf-8").replace(
                '<section data-state="primary">',
                '<section data-state="primary" data-annotation>', 1),
            encoding="utf-8",
        )
        contract, _ = extract(self.root, self.exp)
        names = [c.name for c in contract.by_id("danh-sach").components]
        self.assertIn("Ghi chú mới", names)
        self.assertIn("Tìm ghi chú", names)

    def test_only_the_primary_state_is_a_commitment(self):
        """Ứng dụng thật ở một thời điểm chỉ ở **một** trạng thái. Gộp cả
        "rỗng" lẫn "có kết quả" vào cam kết thì không màn hình thật nào
        khớp nổi, và cổng đỏ vì lý do sai."""
        contract, _ = extract(self.root, self.exp)
        screen = contract.by_id("danh-sach")
        names = [c.name for c in screen.components]
        self.assertIn("Ghi chú mới", names)
        self.assertNotIn("Trạng thái: có ghi chú", names)   # chú thích tài liệu
        self.assertIn("primary", screen.states)

    def test_validation_attributes_captured(self):
        contract, _ = extract(self.root, self.exp)
        field = contract.by_id("danh-sach").fields[0]
        self.assertEqual(field["type"], "search")
        self.assertEqual(field["maxlength"], "120")

    def test_fields_come_from_the_primary_state_only(self):
        """Một ô tìm kiếm dựng lại ở 11 trạng thái sẽ thành 11 ràng buộc
        giống hệt nhau — người đọc hợp đồng không biết đó là một hay mười
        một ô."""
        contract, _ = extract(self.root, self.exp)
        names = [f["name"] for f in contract.by_id("danh-sach").fields]
        self.assertEqual(names, ["q"])

    def test_the_meta_cua_ban_cu_van_doc_duoc(self):
        """Mockup do 0.1.0 dựng mang thẻ `aisdlc-screen`/`aisdlc-route`.

        Đổi tên ở 0.2.0 mà chỉ đọc tên mới thì mọi dự án đã dựng mockup bằng
        bản cũ bị cổng map mockup báo "không khai route" — trong khi chúng khai
        đúng. Bản dựng đọc tên mới trước, tên cũ sau.
        """
        p = self.root / "mockups" / "the.html"
        p.write_text(p.read_text(encoding="utf-8")
                     .replace("aisef-screen", "aisdlc-screen")
                     .replace("aisef-route", "aisdlc-route"), encoding="utf-8")
        contract, _ = extract(self.root, self.exp)
        man = contract.by_id("the")
        self.assertIsNotNone(man, "màn hình mang thẻ tên cũ phải vẫn được nhận")
        self.assertTrue(man.route, "route khai bằng thẻ tên cũ phải đọc được")

    def test_slice_is_one_screen_only(self):
        """Bước viết code chỉ được nạp lát cắt một màn hình."""
        contract, _ = extract(self.root, self.exp)
        one = contract.slice_for("the")
        self.assertEqual(one["id"], "the")
        self.assertNotIn("thung-rac", str(one))

    def test_slice_of_unknown_screen_is_none(self):
        contract, _ = extract(self.root, self.exp)
        self.assertIsNone(contract.slice_for("khong-co"))


@unittest.skipIf(BROWSER_REASON, f"không dựng được mockup: {BROWSER_REASON}")
class TestGate(MockupTestCase):
    def test_unresolved_marker_blocks(self):
        _, gate = extract(self.root, self.exp)
        self.assertFalse(gate.passed)
        self.assertTrue(any("unresolved" in e for e in gate.errors))

    def test_missing_route_blocks(self):
        _, gate = extract(self.root, self.exp)
        self.assertTrue(any("route" in e for e in gate.errors))

    def test_passes_when_every_screen_is_complete(self):
        self.fix_search_screen()
        _, gate = extract(self.root, self.exp)
        self.assertTrue(gate.passed, gate.summary())

    def test_unresolved_items_are_grouped_by_question(self):
        """52 chỗ chưa chốt trên 5 màn thường quy về 4–5 câu hỏi. Liệt kê
        từng chỗ thì người duyệt thấy một bức tường; gom lại thì thấy đúng
        việc phải làm."""
        from aisef.control.design_contract import DesignContract, ScreenContract

        contract = DesignContract(screens=[
            ScreenContract(id="a", route="/a", unresolved=[
                "UX-OQ-1: dark mode?", "UX-OQ-2: tên sản phẩm?"]),
            ScreenContract(id="b", route="/b", unresolved=[
                "UX-OQ-1: dark mode?", "DESIGN.md thiếu bề mặt báo lỗi"]),
        ])
        exp = parse_experience(
            "## Information Architecture\n\n| Surface |\n|---|\n| a |\n| b |\n"
        )
        gate = check_design_contract(contract, exp)
        blob = gate.summary()
        self.assertIn("4 unresolved spots", blob)
        self.assertIn("UX-OQ-1 (2 spots)", blob)
        self.assertIn("thiếu bề mặt báo lỗi", blob)   # ví dụ cho nhóm không mã

    def test_missing_mockup_blocks(self):
        (self.root / "mockups" / "cai-dat.html").unlink()
        _, gate = extract(self.root, self.exp)
        self.assertTrue(any("cai-dat" in e for e in gate.errors))

    def test_story_pointing_at_a_screen_that_does_not_exist_blocks(self):
        """Mã màn hình sai thì lúc viết code agent nạp rỗng rồi tự dựng
        theo phán đoán — đúng thứ bước map mockup sinh ra để ngăn."""
        self.fix_search_screen()
        contract, _ = extract(self.root, self.exp)
        stories = [Story(id="STORY-01-01", epic_id="EPIC-01", title="x", screens=["danh-sach"]),
                   Story(id="STORY-02-01", epic_id="EPIC-02", title="y", screens=["tim-kem"])]
        gate = check_design_contract(contract, self.exp, stories)
        self.assertFalse(gate.passed)
        self.assertTrue(any("STORY-02-01" in e for e in gate.errors))

    def test_screen_with_no_story_only_warns(self):
        self.fix_search_screen()
        contract, _ = extract(self.root, self.exp)
        stories = [Story(id="STORY-01-01", epic_id="EPIC-01", title="x", screens=["danh-sach"])]
        gate = check_design_contract(contract, self.exp, stories)
        self.assertTrue(gate.passed)
        self.assertTrue(any("not built by any story" in w for w in gate.warnings))


@unittest.skipIf(BROWSER_REASON, f"không dựng được mockup: {BROWSER_REASON}")
class TestScreenshots(MockupTestCase):
    def test_screenshot_written_next_to_the_mockup(self):
        extract(self.root, self.exp)
        self.assertTrue((self.root / "mockups" / "danh-sach.png").is_file())


class TestIndexPage(MockupTestCase):
    def test_index_lists_every_screen(self):
        res = MockupResult(experience=self.exp)
        path = write_index(self.root, res)
        html = path.read_text(encoding="utf-8")
        for screen in self.exp.screens:
            self.assertIn(f"{screen.id}.html", html)
        self.assertIn("6 screen(s)", html)

    def test_index_escapes_content(self):
        self.exp.screens[0].purpose = 'nguy <script>alert("x")</script>'
        html = write_index(self.root, MockupResult(experience=self.exp)).read_text(encoding="utf-8")
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)


class TestBrowserUnavailable(unittest.TestCase):
    def test_missing_browser_is_a_gate_error_not_a_silent_pass(self):
        """Thiếu trình duyệt thì hợp đồng không tồn tại — cổng phải trượt,
        không được coi như đạt."""
        import aisef.phases.mockup as mod

        real = mod.browser.render
        mod.browser.render = lambda *a, **k: browser.RenderResult(unavailable="chưa cài playwright")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                exp = parse_experience_file(EXPERIENCE)
                contract, gate = extract(Path(tmp), exp)
                self.assertFalse(gate.passed)
                self.assertEqual(contract.screens, [])
                self.assertTrue(any("playwright" in e for e in gate.errors))
        finally:
            mod.browser.render = real



class TestDuAnKhongCoGiaoDien(unittest.TestCase):
    """Một CLI không có màn hình nào để dựng. Trước đây khung đòi bằng được
    một bảng màn hình, nên planner ánh xạ 6 lệnh thành 6 "màn hình" và mọi
    story mang hợp đồng browser + mockup-map + accessibility cho thứ không có
    DOM. Nhưng "không khai màn hình" cũng là hình dạng của một dự án UI quên
    viết bảng — nên tài liệu phải **khai** ra mình thuộc loại nào."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_khai_khong_giao_dien_thi_hop_dong_rong_va_cong_qua(self):
        from aisef.control.design_contract import CONTRACT_FILE
        from aisef.phases.mockup import generate as run_mockup

        (self.root / "_bmad-output").mkdir()
        (self.root / "_bmad-output" / "EXPERIENCE.md").write_text(
            "# Taskbook — Experience\n\n**Screens:** none — no graphical surface\n\n"
            "## Command Signatures\n\n`taskbook add \"<title>\"`\n",
            encoding="utf-8")
        res = run_mockup(self.root, client=None)
        self.assertEqual(res.error, "")
        self.assertTrue((self.root / "_bmad-output" / CONTRACT_FILE).is_file())
        self.assertTrue(res.gate.passed)
        self.assertIn("no graphical surface", " ".join(res.gate.warnings))

    def test_quen_viet_bang_van_la_loi(self):
        from aisef.phases.mockup import generate as run_mockup

        (self.root / "_bmad-output").mkdir()
        (self.root / "_bmad-output" / "EXPERIENCE.md").write_text(
            "# App\n\nMột màn hình duy nhất, danh sách ghi chú.\n", encoding="utf-8")
        res = run_mockup(self.root, client=None)
        self.assertIn("does not list any screens", res.error)


class TestHopDongYeuDiThiNoiRa(unittest.TestCase):
    """`--force` chạy lại agent, và lượt hai không phải lượt một: bản đo trên
    `todo-oc` mất ô tìm kiếm và 2/3 trạng thái. Hợp đồng là thứ khâu kiểm
    đối chiếu ứng dụng thật, nên hợp đồng nghèo đi là cổng nhạt đi."""

    def _hop_dong(self, *, components, states, fields=()):
        from aisef.control.design_contract import DesignContract, ScreenContract
        from aisef.harness.aria import Component
        return DesignContract(screens=[ScreenContract(
            id="note-list",
            components=[Component(r, n) for r, n in components],
            states=list(states),
            fields=[{"name": f} for f in fields],
        )])

    def test_mat_thanh_phan_va_trang_thai_thi_canh_bao(self):
        from aisef.phases.mockup import _mat_bot_so_voi_ban_truoc
        cu = self._hop_dong(
            components=[("textbox", "New note"), ("searchbox", "Search notes")],
            states=["primary", "empty"], fields=["search-input"])
        moi = self._hop_dong(
            components=[("textbox", "New note")], states=["primary"])
        canh = _mat_bot_so_voi_ban_truoc(cu, moi)
        self.assertEqual(len(canh), 1)
        self.assertIn("Search notes", canh[0])
        self.assertIn("empty", canh[0])
        self.assertIn("search-input", canh[0])

    def test_khong_mat_gi_thi_im_lang(self):
        from aisef.phases.mockup import _mat_bot_so_voi_ban_truoc
        cu = self._hop_dong(components=[("textbox", "New note")], states=["primary"])
        moi = self._hop_dong(
            components=[("textbox", "New note"), ("button", "Add")],
            states=["primary", "empty"])
        self.assertEqual(_mat_bot_so_voi_ban_truoc(cu, moi), [])

    def test_man_hinh_moi_khong_bi_coi_la_mat(self):
        from aisef.control.design_contract import DesignContract
        from aisef.phases.mockup import _mat_bot_so_voi_ban_truoc
        moi = self._hop_dong(components=[("textbox", "x")], states=["primary"])
        self.assertEqual(_mat_bot_so_voi_ban_truoc(DesignContract(), moi), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
