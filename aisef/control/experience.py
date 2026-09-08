"""Đọc `EXPERIENCE.md` — danh sách màn hình và hành vi của chúng.

BMAD sinh hai tài liệu UX: `DESIGN.md` (hệ thống thị giác) và
`EXPERIENCE.md` (luồng, màn hình, hành vi). Module này lấy ra thứ framework
cần để làm việc tiếp: **danh sách màn hình**.

Danh sách màn hình là bản lề của cả bước 3 và bước 4:

* mỗi màn hình phải có đúng một mockup (cổng máy đối chiếu hai chiều);
* story giao diện trỏ tới ``screen_id`` có thật;
* lúc viết code, agent chỉ được nạp **lát cắt của một màn hình**, không
  phải cả tệp hợp đồng.

Hình dạng bảng lấy từ mẫu chính BMAD ship kèm
(`assets/experience-example-shadcn.md`): mục ``## Information Architecture``
là bảng markdown, cột đầu là tên màn hình.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

#: Tên mục có thể khác nhau đôi chút giữa các lần sinh; nhận cả vài biến thể.
_IA_HEADINGS = ("information architecture", "surfaces", "screens", "màn hình",
                "kiến trúc thông tin")
_COMPONENT_HEADINGS = ("component patterns", "components", "thành phần",
                       "mẫu thành phần")
_STATE_HEADINGS = ("state patterns", "states", "trạng thái", "mẫu trạng thái")


def slugify(name: str) -> str:
    """`Project detail` → `project-detail`; bỏ dấu tiếng Việt."""
    text = unicodedata.normalize("NFD", name)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "screen"


#: Tên cột có thể gặp, theo vai trò. BMAD viết bảng bằng ngôn ngữ của dự
#: án, nên không thể trông vào **thứ tự** cột: một lần chạy thật đã cho ra
#: bảng `screen_id | Route | Đến từ | Mục đích` — đọc theo thứ tự thì
#: "Đến từ" bị lấy làm mục đích và route mất hẳn.
_COLUMNS: dict[str, tuple[str, ...]] = {
    "id": ("screen_id", "screen id", "id", "mã màn hình", "mã"),
    "name": ("surface", "screen", "màn hình", "tên", "name"),
    "route": ("route", "đường dẫn", "path", "url"),
    "reached_from": ("reached from", "đến từ", "vào từ", "entry", "lối vào", "reached"),
    "purpose": ("purpose", "mục đích", "vai trò", "description", "mô tả"),
}


@dataclass
class Screen:
    id: str
    name: str
    #: Đường dẫn màn hình này sẽ có trong ứng dụng, nếu tài liệu khai.
    route: str = ""
    reached_from: str = ""
    purpose: str = ""
    #: Component nêu trong bảng Component Patterns có nhắc tới màn hình này.
    components: list[str] = field(default_factory=list)
    #: Trạng thái phải dựng được (rỗng, lỗi, đang tải…).
    states: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "route": self.route,
            "reached_from": self.reached_from,
            "purpose": self.purpose,
            "components": self.components,
            "states": self.states,
        }


@dataclass
class Experience:
    screens: list[Screen] = field(default_factory=list)
    #: Tên component → luật hành vi, để đưa vào prompt sinh mockup.
    component_rules: dict[str, str] = field(default_factory=dict)

    def by_id(self, screen_id: str) -> Screen | None:
        return next((s for s in self.screens if s.id == screen_id), None)

    @property
    def ids(self) -> list[str]:
        return [s.id for s in self.screens]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_separator(line: str) -> bool:
    return bool(re.fullmatch(r"\|?[\s:|-]+\|?", line.strip())) and "-" in line


def _tables_in_section(text: str, headings: tuple[str, ...]) -> list[list[list[str]]]:
    """Mọi bảng markdown nằm trong các mục có tiêu đề khớp."""
    tables: list[list[list[str]]] = []
    marks = list(re.finditer(r"^(#{2,4})\s+(.+?)\s*$", text, re.MULTILINE))
    for i, m in enumerate(marks):
        if not any(h in m.group(2).lower() for h in headings):
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        rows: list[list[str]] = []
        for line in text[m.end():end].splitlines():
            if not line.strip().startswith("|"):
                if rows:
                    tables.append(rows)
                    rows = []
                continue
            if _is_separator(line):
                continue
            rows.append(_cells(line))
        if rows:
            tables.append(rows)
    return tables


def _strip_markup(text: str) -> str:
    return " ".join(text.replace("`", "").replace("**", "").split())


def _column_map(header: list[str]) -> dict[str, int]:
    """Vai trò → chỉ số cột, đọc từ hàng tiêu đề."""
    out: dict[str, int] = {}
    for i, cell in enumerate(header):
        label = _strip_markup(cell).lower()
        for role, names in _COLUMNS.items():
            if role in out:
                continue
            if any(label == n or label.startswith(n) for n in names):
                out[role] = i
                break
    return out


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return _strip_markup(row[index])


def parse_experience(text: str) -> Experience:
    """`EXPERIENCE.md` → danh sách màn hình đã chuẩn hoá."""
    exp = Experience()

    for table in _tables_in_section(text, _IA_HEADINGS):
        if not table:
            continue
        cols = _column_map(table[0])
        # Bảng không có tiêu đề nhận ra được: quay về thứ tự cũ.
        if not cols:
            cols = {"name": 0, "reached_from": 1, "purpose": 2}
            rows = table
        else:
            rows = table[1:]

        for row in rows:
            name = _cell(row, cols.get("name")) or _cell(row, cols.get("id"))
            ident = _cell(row, cols.get("id")) or name
            if not ident or ident.lower() in ("surface", "screen", "màn hình", "screen_id"):
                continue
            screen = Screen(
                id=slugify(ident),
                name=name or ident,
                route=_cell(row, cols.get("route")),
                reached_from=_cell(row, cols.get("reached_from")),
                purpose=_cell(row, cols.get("purpose")),
            )
            if not exp.by_id(screen.id):
                exp.screens.append(screen)

    _attach(exp, text, _COMPONENT_HEADINGS, "components")
    _attach(exp, text, _STATE_HEADINGS, "states")
    return exp


def _attach(exp: Experience, text: str, headings: tuple[str, ...], field_name: str) -> None:
    """Gắn component/trạng thái vào màn hình mà **cột phạm vi** có nhắc tới.

    Chỉ đọc cột thứ hai ("Use" / "Surface"), không đọc cột luật hành vi:
    luật của `Task row` có chữ "Click anywhere on row", và nếu quét cả dòng
    thì "anywhere" biến nó thành component của mọi màn hình — prompt sinh
    mockup sẽ đầy component không thuộc màn hình đó.
    """
    for table in _tables_in_section(text, headings):
        for row in table[1:] if len(table) > 1 else []:
            label = _strip_markup(row[0])
            if not label:
                continue
            scope = _strip_markup(row[1]).lower() if len(row) > 1 else ""
            if field_name == "components":
                exp.component_rules.setdefault(label, _strip_markup(" ".join(row[2:])))

            everywhere = "global" in scope or "anywhere" in scope or "mọi màn hình" in scope
            for screen in exp.screens:
                if everywhere or _mentions(scope, screen.name):
                    target = getattr(screen, field_name)
                    if label not in target:
                        target.append(label)


def _mentions(haystack: str, name: str) -> bool:
    """Khớp trọn từ, để "Search" không trúng "searchable"."""
    return re.search(rf"\b{re.escape(name.lower())}\b", haystack) is not None


def parse_experience_file(path: Path | str) -> Experience:
    return parse_experience(Path(path).read_text(encoding="utf-8", errors="replace"))
