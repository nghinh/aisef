"""Read skills from disk.

A skill is a directory containing SKILL.md with YAML frontmatter. This is the
common format across all sources we import (BMAD, superpowers, ui-ux-pro-max,
cybersecurity-skills), so a single reader suffices.

No PyYAML: skill frontmatter only has scalars and flat lists, so a ~40-line
stdlib parser is sufficient and avoids adding a dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

FRONTMATTER_FENCE = "---"


@dataclass(frozen=True)
class Skill:
    """A skill read from disk."""

    name: str
    path: Path
    description: str = ""
    domain: str = ""
    subdomain: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def verb(self) -> str:
        """Leading verb of the skill name (`performing-x` -> `performing`).

        The cybersecurity-skills repo names skills consistently by verb, so
        this is a cheap and stable classification signal.
        """
        return self.name.split("-", 1)[0].lower()


def parse_frontmatter(text: str) -> dict[str, object]:
    """Extract YAML frontmatter at the top of the file into a dict.

    Supports exactly what skills use: `key: value`, folded blocks (`>-`, `|`),
    and bulleted lists. Returns empty dict if the file doesn't start with a fence.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        return {}

    try:
        end = next(i for i, l in enumerate(lines[1:], 1) if l.strip() == FRONTMATTER_FENCE)
    except StopIteration:
        return {}  # unclosed fence — treat as no frontmatter

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

        # list item belonging to the current key
        if stripped.startswith("- ") and key is not None:
            items.append(stripped[2:].strip())
            continue

        # indented line = continuation of a folded block
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
            folded = []  # value is on subsequent lines
        else:
            data[key] = v
            key = None

    flush()
    return data


def load_skill(skill_dir: Path) -> Skill | None:
    """Read one skill directory. Returns None if not a valid skill."""
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
    """Find all skills under `root`, sorted by name for stability."""
    if not root.is_dir():
        return []
    found = (load_skill(md.parent) for md in root.rglob("SKILL.md"))
    return sorted((s for s in found if s), key=lambda s: s.name)
