"""Parse `EXPERIENCE.md` -- the list of screens and their behaviors.

BMAD produces two UX documents: `DESIGN.md` (visual system) and
`EXPERIENCE.md` (flows, screens, behaviors). This module extracts what the
framework needs to proceed: the **screen list**.

The screen list is the hinge for both phase 3 and phase 4:

* each screen must have exactly one mockup (machine gate cross-checks both
  directions);
* UI stories point to a real ``screen_id``;
* when coding, the agent may only load a **single-screen slice**, not the
  entire contract file.

The table shape follows BMAD's canonical template
(`assets/experience-example-shadcn.md`): an ``## Information Architecture``
section containing a markdown table whose first column is the screen name.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

#: Section headings may vary slightly between generation runs; accept several variants.
_IA_HEADINGS = ("information architecture", "surfaces", "screens", "screen",
                "pages", "page", "views", "view", "routes",
                "màn hình", "kiến trúc thông tin")
_COMPONENT_HEADINGS = ("component patterns", "components", "thành phần",
                       "mẫu thành phần")
_STATE_HEADINGS = ("state patterns", "states", "trạng thái", "mẫu trạng thái")


def slugify(name: str) -> str:
    """`Project detail` -> `project-detail`; strips Vietnamese diacritics."""
    text = unicodedata.normalize("NFD", name)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "screen"


#: Known column names by role. BMAD writes tables in the project's language,
#: so column **order** is unreliable: a real run produced
#: `screen_id | Route | Reached from | Purpose` -- reading by position would
#: misassign "Reached from" as purpose and lose the route entirely.
_COLUMNS: dict[str, tuple[str, ...]] = {
    "id": ("screen_id", "screen id", "id", "mã màn hình", "mã"),
    "name": ("surface", "screen", "page", "view", "màn hình", "tên", "name"),
    "route": ("route", "đường dẫn", "path", "url"),
    "reached_from": ("reached from", "đến từ", "vào từ", "entry", "lối vào", "reached"),
    "purpose": ("purpose", "mục đích", "vai trò", "description", "mô tả"),
}


@dataclass
class Screen:
    id: str
    name: str
    #: Route this screen will have in the application, if declared in the document.
    route: str = ""
    reached_from: str = ""
    purpose: str = ""
    #: Components from the Component Patterns table that mention this screen.
    components: list[str] = field(default_factory=list)
    #: States that must be renderable (empty, error, loading, etc.).
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
    #: Component name -> behavior rules, for inclusion in mockup generation prompts.
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
    """All markdown tables inside sections whose headings match."""
    tables: list[list[list[str]]] = []
    marks = list(re.finditer(r"^(#{2,6})\s+(.+?)\s*$", text, re.MULTILINE))
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
    """Role -> column index, read from the header row."""
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
    """`EXPERIENCE.md` -> normalized screen list."""
    exp = Experience()

    for table in _tables_in_section(text, _IA_HEADINGS):
        if not table:
            continue
        cols = _column_map(table[0])
        # No recognizable header: fall back to positional column order.
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
    """Attach components/states to screens mentioned in the **scope column**.

    Only reads the second column ("Use" / "Surface"), not the behavior-rule
    column: `Task row`'s rule says "Click anywhere on row", and scanning the
    full row would make "anywhere" attach it to every screen -- the mockup
    prompt would be filled with components that don't belong.
    """
    for table in _tables_in_section(text, headings):
        for row in table[1:] if len(table) > 1 else []:
            label = _strip_markup(row[0])
            if not label:
                continue
            scope = _strip_markup(row[1]).lower() if len(row) > 1 else ""
            if field_name == "components":
                exp.component_rules.setdefault(label, _strip_markup(" ".join(row[2:])))

            everywhere = any(k in scope for k in ("global", "anywhere", "everywhere",
                                                     "all screens", "all pages", "every",
                                                     "mọi màn hình"))
            for screen in exp.screens:
                if everywhere or _mentions(scope, screen.name):
                    target = getattr(screen, field_name)
                    if label not in target:
                        target.append(label)


def _mentions(haystack: str, name: str) -> bool:
    """Whole-word match, so "Search" does not hit "searchable"."""
    return re.search(rf"\b{re.escape(name.lower())}\b", haystack) is not None


def parse_experience_file(path: Path | str) -> Experience:
    return parse_experience(Path(path).read_text(encoding="utf-8", errors="replace"))
