"""Skill source registry.

Answers three questions per source: where to get the skills, which ones to
pick, and **whether they may be copied into the target project**.

The third question is not a formality. A repo with no LICENSE file defaults
to "all rights reserved" -- repackaging and distributing to another project
is not allowed. Such sources are marked ``redistribute: false``: reading for
reference is fine, copying is not. Tests enforce that boundary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

CATALOG_FILE = Path(__file__).with_name("catalog.json")


class CatalogError(ValueError):
    """Catalog has invalid format or references something that does not exist."""


@dataclass(frozen=True)
class Source:
    id: str
    repo: str
    commit: str
    license: str | None
    redistribute: bool
    local_path: str
    skill_roots: tuple[str, ...]
    selection: str  # all | allowlist | filtered | reference_only
    allowlist: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    role: str = ""
    notes: str = ""

    @property
    def installable(self) -> bool:
        """Whether skills from this source may be copied into the target project."""
        return self.redistribute and self.selection != "reference_only"

    def roots(self, references_root: Path) -> list[Path]:
        base = Path(references_root).parent / self.local_path
        return [base / r for r in self.skill_roots]


@dataclass
class Catalog:
    sources: list[Source] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | str = CATALOG_FILE) -> Catalog:
        p = Path(path)
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise CatalogError(f"cannot read {p}: {e}") from e

        sources = []
        seen: set[str] = set()
        for entry in raw.get("sources", []):
            missing = [
                k for k in ("id", "repo", "commit", "redistribute", "local_path", "selection")
                if k not in entry
            ]
            if missing:
                raise CatalogError(f"source {entry.get('id', '?')} missing fields: {', '.join(missing)}")
            if entry["id"] in seen:
                raise CatalogError(f"duplicate source id: {entry['id']}")
            seen.add(entry["id"])

            if not entry["commit"] or len(entry["commit"]) < 7:
                raise CatalogError(f"source {entry['id']} must pin a specific commit")

            if entry.get("license") is None and entry["redistribute"]:
                raise CatalogError(
                    f"source {entry['id']} has no license but sets redistribute=true"
                )

            sources.append(
                Source(
                    id=entry["id"],
                    repo=entry["repo"],
                    commit=entry["commit"],
                    license=entry.get("license"),
                    redistribute=bool(entry["redistribute"]),
                    local_path=entry["local_path"],
                    skill_roots=tuple(entry.get("skill_roots", ())),
                    selection=entry["selection"],
                    allowlist=tuple(entry.get("allowlist", ())),
                    requires=tuple(entry.get("requires", ())),
                    role=entry.get("role", ""),
                    notes=entry.get("notes", ""),
                )
            )
        if not sources:
            raise CatalogError("catalog is empty")
        return cls(sources)

    def by_id(self, source_id: str) -> Source:
        for s in self.sources:
            if s.id == source_id:
                return s
        raise KeyError(f"source not found: {source_id}")

    def installable(self) -> list[Source]:
        return [s for s in self.sources if s.installable]

    def reference_only(self) -> list[Source]:
        return [s for s in self.sources if not s.installable]

    def verify_paths(self, references_root: Path) -> list[str]:
        """Verify all paths in the catalog exist. Return list of problems."""
        problems = []
        for s in self.sources:
            for root in s.roots(references_root):
                if not root.is_dir():
                    problems.append(f"{s.id}: not found {root}")
        return problems
