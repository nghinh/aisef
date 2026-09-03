"""Sổ prompt — prompt là mã nguồn, không phải chuỗi rải trong code.

Ba lý do prompt phải nằm ở đây thay vì nằm rải trong hàm gọi:

* **có phiên bản.** Bằng chứng mỗi story ghi lại tên + phiên bản prompt.
  Chất lượng tụt sau một lần sửa prompt thì còn lần được ra nguyên nhân.
* **kiểm được.** Test dựng prompt với ngữ cảnh giả và kiểm nội dung, không
  cần gọi model.
* **thiếu biến là lỗi.** Chỗ trống không được điền sẽ lặng lẽ thành khoảng
  trắng, và agent sẽ làm việc với một bản hướng dẫn khuyết mà không ai
  biết. Ở đây nó ném lỗi.

Cú pháp chỗ trống là ``{{ ten_bien }}`` chứ không dùng ``str.format``: thân
prompt có ngoặc nhọn thật (ví dụ JSON, mã nguồn), và ``format`` sẽ vấp.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..kit.skills import FRONTMATTER_FENCE, parse_frontmatter

PROMPT_DIR = Path(__file__).resolve().parent.parent / "kit" / "prompts"

_SLOT = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")


class PromptError(ValueError):
    pass


def _body_of(text: str) -> str:
    """Phần sau frontmatter."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        return text
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == FRONTMATTER_FENCE:
            return "\n".join(lines[i + 1:])
    return text


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    role: str
    body: str
    path: Path | None = None

    @property
    def slots(self) -> list[str]:
        return sorted(set(_SLOT.findall(self.body)))

    @property
    def stamp(self) -> str:
        """Dấu ghi vào bằng chứng: `story-implement@3`."""
        return f"{self.name}@{self.version}"

    def render(self, context: dict[str, object], *, allow_empty: tuple[str, ...] = ()) -> str:
        missing = [s for s in self.slots if s not in context]
        if missing:
            raise PromptError(f"{self.name}: thiếu biến {', '.join(missing)}")

        blank = [
            s for s in self.slots
            if s not in allow_empty and not str(context.get(s, "")).strip()
        ]
        if blank:
            raise PromptError(
                f"{self.name}: biến rỗng {', '.join(blank)} — prompt khuyết sẽ "
                f"làm agent làm việc với hướng dẫn thiếu mà không ai biết"
            )

        return _SLOT.sub(lambda m: str(context[m.group(1)]), self.body)


@dataclass
class Catalog:
    prompts: dict[str, Prompt] = field(default_factory=dict)

    def get(self, name: str) -> Prompt:
        if name not in self.prompts:
            raise PromptError(
                f"prompt không có: {name}. Có: {', '.join(sorted(self.prompts))}"
            )
        return self.prompts[name]

    def __contains__(self, name: object) -> bool:
        return name in self.prompts


def load_catalog(directory: Path | str = PROMPT_DIR) -> Catalog:
    catalog = Catalog()
    directory = Path(directory)
    if not directory.is_dir():
        return catalog

    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text), _body_of(text)
        name = str(meta.get("name") or path.stem)
        try:
            version = int(str(meta.get("version") or 1))
        except ValueError:
            version = 1
        catalog.prompts[name] = Prompt(
            name=name,
            version=version,
            role=str(meta.get("role") or ""),
            body=body.strip(),
            path=path,
        )
    return catalog
