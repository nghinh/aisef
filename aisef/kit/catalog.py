"""Sổ đăng ký nguồn skill.

Trả lời ba câu cho mỗi nguồn: lấy skill ở đâu, chọn cái nào, và **có được
phép sao chép vào dự án đích không**.

Câu thứ ba không phải chuyện hình thức. Một kho không có file LICENSE mặc
định là "all rights reserved" — đóng gói lại và phát cho dự án khác là
việc không được làm. Nguồn như vậy đánh dấu ``redistribute: false``: đọc
để tham chiếu thì được, sao chép thì không. Có test giữ ranh giới đó.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

CATALOG_FILE = Path(__file__).with_name("catalog.json")


class CatalogError(ValueError):
    """Sổ đăng ký sai định dạng hoặc trỏ tới thứ không tồn tại."""


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
        """Có được sao chép skill của nguồn này vào dự án đích không."""
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
            raise CatalogError(f"không đọc được {p}: {e}") from e

        sources = []
        seen: set[str] = set()
        for entry in raw.get("sources", []):
            missing = [
                k for k in ("id", "repo", "commit", "redistribute", "local_path", "selection")
                if k not in entry
            ]
            if missing:
                raise CatalogError(f"nguồn {entry.get('id', '?')} thiếu: {', '.join(missing)}")
            if entry["id"] in seen:
                raise CatalogError(f"nguồn trùng id: {entry['id']}")
            seen.add(entry["id"])

            if not entry["commit"] or len(entry["commit"]) < 7:
                raise CatalogError(f"nguồn {entry['id']} phải ghim commit cụ thể")

            if entry.get("license") is None and entry["redistribute"]:
                raise CatalogError(
                    f"nguồn {entry['id']} không có license nhưng đặt redistribute=true"
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
            raise CatalogError("sổ đăng ký rỗng")
        return cls(sources)

    def by_id(self, source_id: str) -> Source:
        for s in self.sources:
            if s.id == source_id:
                return s
        raise KeyError(f"không có nguồn: {source_id}")

    def installable(self) -> list[Source]:
        return [s for s in self.sources if s.installable]

    def reference_only(self) -> list[Source]:
        return [s for s in self.sources if not s.installable]

    def verify_paths(self, references_root: Path) -> list[str]:
        """Kiểm mọi đường dẫn trong sổ có thật. Trả danh sách vấn đề."""
        problems = []
        for s in self.sources:
            for root in s.roots(references_root):
                if not root.is_dir():
                    problems.append(f"{s.id}: không có {root}")
        return problems
