"""Đọc skill từ đĩa.

Một skill là một thư mục chứa SKILL.md có YAML frontmatter. Đây là định dạng
chung của mọi nguồn ta nhập (BMAD, superpowers, ui-ux-pro-max,
cybersecurity-skills), nên chỉ cần một bộ đọc.

Không dùng PyYAML: frontmatter của skill chỉ gồm scalar và list phẳng, nên
parser stdlib ~40 dòng là đủ và bỏ được một dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

FRONTMATTER_FENCE = "---"


@dataclass(frozen=True)
class Skill:
    """Một skill đã đọc từ đĩa."""

    name: str
    path: Path
    description: str = ""
    domain: str = ""
    subdomain: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def verb(self) -> str:
        """Động từ mở đầu tên skill (`performing-x` → `performing`).

        Kho cybersecurity-skills đặt tên nhất quán theo động từ, nên đây là
        tín hiệu phân loại rẻ và ổn định.
        """
        return self.name.split("-", 1)[0].lower()


def parse_frontmatter(text: str) -> dict[str, object]:
    """Trích frontmatter YAML ở đầu file thành dict.

    Hỗ trợ đúng những gì skill dùng: `key: value`, khối gấp (`>-`, `|`) và
    list gạch đầu dòng. Trả dict rỗng nếu file không mở đầu bằng fence.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        return {}

    try:
        end = next(i for i, l in enumerate(lines[1:], 1) if l.strip() == FRONTMATTER_FENCE)
    except StopIteration:
        return {}  # fence không đóng — coi như không có frontmatter

    data: dict[str, object] = {}
    key: str | None = None
    folded: list[str] = []
    items: list[str] = []

    def flush() -> None:
        nonlocal key, folded, items
        if key is None:
            return
        if items:
            data[key] = list(items)
        elif folded:
            data[key] = " ".join(folded).strip()
        key, folded, items = None, [], []

    for raw in lines[1:end]:
        stripped = raw.strip()
        if not stripped:
            continue

        # phần tử list thuộc key hiện tại
        if stripped.startswith("- ") and key is not None:
            items.append(stripped[2:].strip())
            continue

        # dòng thụt vào = phần tiếp của khối gấp
        if raw.startswith((" ", "\t")) and key is not None:
            folded.append(stripped)
            continue

        if ":" not in stripped:
            continue

        flush()
        k, _, v = stripped.partition(":")
        key = k.strip()
        v = v.strip()
        if v in (">-", ">", "|", "|-", ""):
            folded = []  # giá trị nằm ở các dòng sau
        else:
            data[key] = v
            key = None

    flush()
    return data


def load_skill(skill_dir: Path) -> Skill | None:
    """Đọc một thư mục skill. Trả None nếu không phải skill hợp lệ."""
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return None

    try:
        fm = parse_frontmatter(md.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None

    tags = fm.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]

    return Skill(
        name=str(fm.get("name") or skill_dir.name),
        path=skill_dir,
        description=str(fm.get("description") or ""),
        domain=str(fm.get("domain") or ""),
        subdomain=str(fm.get("subdomain") or ""),
        tags=tuple(str(t) for t in tags),
    )


def scan(root: Path) -> list[Skill]:
    """Tìm mọi skill dưới `root`, sắp xếp theo tên cho ổn định."""
    if not root.is_dir():
        return []
    found = (load_skill(md.parent) for md in root.rglob("SKILL.md"))
    return sorted((s for s in found if s), key=lambda s: s.name)
