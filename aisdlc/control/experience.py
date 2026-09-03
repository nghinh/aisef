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
_IA_HEADINGS = ("information architecture", "surfaces", "screens", "màn hình")
_COMPONENT_HEADINGS = ("component patterns", "components")
_STATE_HEADINGS = ("state patterns", "states")


def slugify(name: str) -> str:
    """`Project detail` → `project-detail`; bỏ dấu tiếng Việt."""
    text = unicodedata.normalize("NFD", name)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "screen"


@dataclass
class Screen:
    id: str
    name: str
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


def parse_experience(text: str) -> Experience:
    """`EXPERIENCE.md` → danh sách màn hình đã chuẩn hoá."""
    exp = Experience()

    for table in _tables_in_section(text, _IA_HEADINGS):
        for row in table[1:] if len(table) > 1 else []:
            name = _strip_markup(row[0])
            if not name or name.lower() in ("surface", "screen", "màn hình"):
                continue
            screen = Screen(
                id=slugify(name),
                name=name,
                reached_from=_strip_markup(row[1]) if len(row) > 1 else "",
                purpose=_strip_markup(row[2]) if len(row) > 2 else "",
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
