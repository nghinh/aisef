"""Đọc EXPERIENCE.md — nguồn danh sách màn hình.

Kiểm trên hai tài liệu: fixture tiếng Việt của bộ test, và **mẫu do chính
BMAD ship kèm** (`assets/experience-example-shadcn.md`). Mẫu của BMAD là
thứ định nghĩa hình dạng thật; đọc được nó nghĩa là bộ đọc không bám vào
cách viết riêng của fixture.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.experience import (  # noqa: E402
    parse_experience,
    parse_experience_file,
    slugify,
)

FIX = ROOT / "tests" / "fixtures" / "bmad" / "EXPERIENCE.md"
BMAD_SAMPLE = (
    ROOT / "references" / "bmad-method" / "src" / "bmm-skills" / "plan"
    / "bmad-ux" / "assets" / "experience-example-shadcn.md"
)


class TestSlug(unittest.TestCase):
    def test_ascii(self):
        self.assertEqual(slugify("Project detail"), "project-detail")

    def test_vietnamese_diacritics_removed(self):
        self.assertEqual(slugify("Thùng rác"), "thung-rac")
        self.assertEqual(slugify("Đăng nhập"), "dang-nhap")

    def test_never_empty(self):
        self.assertEqual(slugify("///"), "screen")


class TestParseFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exp = parse_experience_file(FIX)

    def test_screens_in_document_order(self):
        self.assertEqual(
            self.exp.ids,
            ["danh-sach", "soan-thao", "tim-kiem", "the", "thung-rac", "cai-dat"],
        )

    def test_screen_carries_purpose_and_entry_point(self):
        s = self.exp.by_id("tim-kiem")
        self.assertIn("toàn văn", s.purpose)
        self.assertIn("Ô tìm", s.reached_from)

    def test_components_attached_by_scope_column(self):
        self.assertIn("Ô soạn thảo", self.exp.by_id("soan-thao").components)
        self.assertNotIn("Ô soạn thảo", self.exp.by_id("danh-sach").components)

    def test_global_components_attach_everywhere(self):
        for screen in self.exp.screens:
            self.assertIn("Chỉ báo ngoại tuyến", screen.components)

    def test_states_attached(self):
        self.assertIn("Không tìm thấy", self.exp.by_id("tim-kiem").states)
        self.assertNotIn("Không tìm thấy", self.exp.by_id("cai-dat").states)

    def test_component_rules_kept_for_the_mockup_prompt(self):
        self.assertIn("1 giây", self.exp.component_rules["Ô soạn thảo"])


class TestBangKhongNhacManHinhNao(unittest.TestCase):
    """Lỗi 98: cột thứ hai của bảng thành phần thường là **vùng trên màn
    hình** ("Header area"), còn bảng trạng thái nhiều khi chỉ có hai cột
    (`State | Treatment`) — không chỗ nào nhắc tên màn hình. Cả bảng rơi
    xuống đất, và với ứng dụng một màn hình thì không dòng nào **có thể**
    nhắc tới nó. Prompt dựng mockup vì thế trống, nên hai lượt dựng liên
    tiếp cho ra hai màn hình khác hẳn nhau."""

    MOT_MAN_HINH = """# EXPERIENCE

## Information Architecture

### Screen Inventory

| Screen | Route | Purpose |
|---|---|---|
| Note List | / | Create, search, and delete notes |

## Component Patterns

| Component | Use | Behavioral rules |
|---|---|---|
| Note textarea | Header area | Enter submits. |
| Search input | Between header and list | Real-time filter. |

## State Patterns

| State | Treatment |
|---|---|
| App load (no notes) | Empty state message. |
| Search no results | "No notes match". |
"""

    def test_ca_bang_thuoc_ve_man_hinh_duy_nhat(self):
        from aisef.control.experience import parse_experience
        s = parse_experience(self.MOT_MAN_HINH).screens[0]
        self.assertEqual(s.components, ["Note textarea", "Search input"])
        self.assertEqual(s.states, ["App load (no notes)", "Search no results"])

    def test_bang_co_nhac_man_hinh_thi_khong_gan_bua(self):
        """Có một dòng khớp là bảng ấy **có** khai phạm vi — những dòng còn
        lại không khớp là cố ý, không được vơ vào."""
        from aisef.control.experience import parse_experience
        doc = self.MOT_MAN_HINH.replace(
            "| Note List | / | Create, search, and delete notes |",
            "| Note List | / | Create notes |\n| Settings | /settings | Preferences |",
        ).replace("| Note textarea | Header area |", "| Note textarea | Note List |")
        exp = parse_experience(doc)
        self.assertEqual(exp.by_id("note-list").components, ["Note textarea"])
        self.assertEqual(exp.by_id("settings").components, [])


class TestKhaiKhongCoGiaoDien(unittest.TestCase):
    """Lỗi 107: tài liệu phải **khai** được là sản phẩm không có giao diện —
    "không có màn hình nào" và "quên viết bảng màn hình" có cùng hình dạng dữ
    liệu, và hai tình huống ấy phải xử khác nhau."""

    def _co(self, dong: str) -> bool:
        from aisef.control.experience import parse_experience
        return parse_experience(f"# X\n\n{dong}\n").headless

    def test_cac_cach_viet_that(self):
        for dong in ("**Screens:** none — no graphical surface",
                     "Screens: none - this is a CLI tool, no screens",
                     "**Screens**: none — headless service",
                     "Screens: none — không có giao diện đồ hoạ"):
            with self.subTest(dong=dong):
                self.assertTrue(self._co(dong))

    def test_khong_nhan_bua(self):
        for dong in ("Screens: none yet, coming in v2",
                     "The app has one screen: the note list.",
                     "## Screen Inventory\n\n| Screen | Route |\n|---|---|\n| A | / |"):
            with self.subTest(dong=dong):
                self.assertFalse(self._co(dong))


class TestGanTheoLenhVaKhongVoBua(unittest.TestCase):
    """Bảng trạng thái của một CLI mô tả hành vi **theo lệnh** (`done <n>`),
    không theo tên hiển thị của màn hình (`Complete Task`)."""

    CLI = """# EXPERIENCE

## Information Architecture

### Screen Inventory

| Screen | Route | Purpose |
|---|---|---|
| Help | `--help` | Usage summary |
| Add Task | `add "<title>"` | Create a task |
| Complete Task | `done <id>` | Mark done |

## State Patterns

| State | Behavior |
|---|---|
| Whitespace-only title | `add "   "` is rejected with a message. |
| Unknown task id | `done <n>` prints an error and exits non-zero. |
| Store file unparseable | Error on stderr, exit non-zero. |
"""

    def test_trang_thai_gan_theo_ten_lenh(self):
        from aisef.control.experience import parse_experience
        exp = parse_experience(self.CLI)
        self.assertEqual(exp.by_id("add-task").states, ["Whitespace-only title"])
        self.assertEqual(exp.by_id("complete-task").states, ["Unknown task id"])

    def test_khong_gan_bua_cho_moi_man_hinh_khi_co_nhieu_man_hinh(self):
        """Lỗi 106: gắn cả bảng cho mọi màn hình thì mỗi màn hình của một CLI
        nhận đủ 9 trạng thái lỗi toàn ứng dụng, và cổng cỡ story chặn sạch kế
        hoạch. "Không nhắc ai" chỉ rõ nghĩa khi tài liệu có **một** màn hình."""
        from aisef.control.experience import parse_experience
        exp = parse_experience(self.CLI)
        # `Store file unparseable` không nhắc lệnh nào — không màn hình nào nhận.
        for screen in exp.screens:
            self.assertNotIn("Store file unparseable", screen.states)
        self.assertEqual(exp.by_id("help").states, [])

    def test_route_dang_duong_dan_khong_thanh_tu_khoa(self):
        """`/tasks` mà thành từ khoá thì mọi câu nói về "tasks" đều gắn vào."""
        from aisef.control.experience import parse_experience
        exp = parse_experience(
            "# EXPERIENCE\n\n## Information Architecture\n\n### Screen Inventory\n\n"
            "| Screen | Route | Purpose |\n|---|---|---|\n"
            "| Board | /tasks | Kanban |\n| Settings | /settings | Prefs |\n\n"
            "## State Patterns\n\n| State | Behavior |\n|---|---|\n"
            "| Empty | No tasks yet. |\n"
        )
        self.assertEqual(exp.by_id("board").states, [])


class TestParseBmadSample(unittest.TestCase):
    """Mẫu của chính BMAD — hình dạng thật, không phải cách viết của ta."""

    @classmethod
    def setUpClass(cls):
        if not BMAD_SAMPLE.is_file():
            raise unittest.SkipTest("chưa clone references/bmad-method")
        cls.exp = parse_experience_file(BMAD_SAMPLE)

    def test_reads_the_information_architecture_table(self):
        self.assertEqual(
            self.exp.ids, ["today", "projects", "project-detail", "search", "settings"]
        )

    def test_behaviour_prose_does_not_leak_into_scope(self):
        """Luật của `Task row` chứa chữ "Click anywhere on row" — quét cả
        dòng thì "anywhere" biến nó thành component của mọi màn hình."""
        self.assertNotIn("Task row", self.exp.by_id("settings").components)
        self.assertIn("Task row", self.exp.by_id("today").components)

    def test_global_component_still_attaches_everywhere(self):
        for screen in self.exp.screens:
            self.assertIn("Command palette", screen.components)


class TestRealBmadOutput(unittest.TestCase):
    """Bảng do BMAD sinh trong một lượt chạy thật: `screen_id | Route |
    Đến từ | Mục đích`. Đọc theo **thứ tự** cột thì "Đến từ" bị lấy làm
    mục đích và route mất hẳn — nên phải đọc theo tiêu đề."""

    TEXT = (
        "## Information Architecture\n\n"
        "| `screen_id` | Route | Đến từ | Mục đích |\n|---|---|---|---|\n"
        "| `notes-list` | `/` | Mở ứng dụng | Danh sách Ghi chú |\n"
        "| `note-editor` | `/note/:id` | Chạm hàng ghi chú | Đọc và sửa một Ghi chú |\n"
    )

    def setUp(self):
        self.exp = parse_experience(self.TEXT)

    def test_ids_from_the_id_column(self):
        self.assertEqual(self.exp.ids, ["notes-list", "note-editor"])

    def test_route_captured(self):
        self.assertEqual(self.exp.by_id("note-editor").route, "/note/:id")

    def test_purpose_is_not_the_entry_point(self):
        s = self.exp.by_id("notes-list")
        self.assertEqual(s.purpose, "Danh sách Ghi chú")
        self.assertEqual(s.reached_from, "Mở ứng dụng")

    def test_header_row_is_not_a_screen(self):
        self.assertNotIn("screen-id", self.exp.ids)


class TestRobustness(unittest.TestCase):
    def test_no_information_architecture_section(self):
        self.assertEqual(parse_experience("# Trống\n\nkhông có bảng nào.\n").screens, [])

    def test_duplicate_surface_kept_once(self):
        text = (
            "## Information Architecture\n\n"
            "| Surface | Reached from | Purpose |\n|---|---|---|\n"
            "| Home | mở app | trang đầu |\n| Home | menu | trang đầu |\n"
        )
        self.assertEqual(parse_experience(text).ids, ["home"])

    def test_table_without_all_columns(self):
        text = "## Screens\n\n| Surface |\n|---|\n| Home |\n"
        s = parse_experience(text).by_id("home")
        self.assertEqual(s.name, "Home")
        self.assertEqual(s.purpose, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestChiBangDanhMucMoiLaManHinh(unittest.TestCase):
    """Lỗi 51. Một tài liệu có nhiều bảng dưới cùng một heading, và chỉ một
    trong số đó là danh mục màn hình.

    Đo 2026-09-09 trên todo-e2e: dưới `## Information Architecture` có
    `### Screen Inventory` (`Screen | Route | Purpose`, 1 dòng) và
    `### Tasks → surfaces` (`Need | Surface | Notes`, 6 dòng ánh xạ nhu cầu
    sang chỗ). Parser đọc cả hai → 6 component thành 6 "màn hình", và bước
    mockup sẽ dựng 6 tệp không ai yêu cầu. Chữ `Surface` quá phổ biến để tin
    một mình; khi đã có bảng khai đích danh màn hình thì bảng mờ hơn không
    phải danh mục.
    """

    DOC = """# EXPERIENCE

## Information Architecture

### Screen Inventory

| Screen | Route | Purpose |
|---|---|---|
| Todo List | `/` | Create and manage tasks |

### Tasks to surfaces

| Need | Surface | Notes |
|---|---|---|
| Create a task | Task input card on Todo List | FR-1 |
| See all tasks | Task list region on Todo List | FR-5 |
"""

    def test_chi_lay_bang_khai_dich_danh(self):
        from aisef.control.experience import parse_experience
        exp = parse_experience(self.DOC)
        self.assertEqual([s.id for s in exp.screens], ["todo-list"])

    def test_khong_co_bang_manh_thi_van_dung_bang_yeu(self):
        """Giữ hành vi cũ: tài liệu chỉ có cột `Surface` vẫn đọc được."""
        from aisef.control.experience import parse_experience
        doc = """# EXPERIENCE

## Surfaces

| Surface | Purpose |
|---|---|
| Danh sach | Xem tat ca |
"""
        exp = parse_experience(doc)
        self.assertEqual([s.id for s in exp.screens], ["danh-sach"])
