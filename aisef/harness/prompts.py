"""Prompt catalog — prompts are source code, not strings scattered in call sites.

Three reasons prompts live here instead of inline in calling functions:

* **Versioned.** Evidence for each story records the prompt name + version.
  Quality drops after a prompt edit can still be traced to the cause.
* **Testable.** Tests build a prompt with mock context and check its content
  without calling a model.
* **Missing variables are errors.** An unfilled slot silently becomes
  whitespace, and the agent works with incomplete instructions unnoticed.
  Here it raises an error.

Slot syntax is ``{{ var_name }}`` rather than ``str.format``: the prompt body
contains real braces (e.g. JSON, source code), and ``format`` would choke.
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
    """The part after frontmatter."""
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
        """Stamp recorded in evidence: `story-implement@3`."""
        return f"{self.name}@{self.version}"

    def render(self, context: dict[str, object], *, allow_empty: tuple[str, ...] = ()) -> str:
        missing = [s for s in self.slots if s not in context]
        if missing:
            raise PromptError(f"{self.name}: missing variables {', '.join(missing)}")

        blank = [
            s for s in self.slots
            if s not in allow_empty and not str(context.get(s, "")).strip()
        ]
        if blank:
            raise PromptError(
                f"{self.name}: empty variables {', '.join(blank)} — incomplete prompt will "
                f"make the agent work with missing instructions unnoticed"
            )

        return _SLOT.sub(lambda m: str(context[m.group(1)]), self.body)


@dataclass
class Catalog:
    prompts: dict[str, Prompt] = field(default_factory=dict)

    def get(self, name: str) -> Prompt:
        if name not in self.prompts:
            raise PromptError(
                f"prompt not found: {name}. Available: {', '.join(sorted(self.prompts))}"
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
