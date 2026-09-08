"""Cài skill vào dự án đích.

Tách làm hai bước có chủ đích: ``plan()`` quyết định cài gì (thuần tính
toán, không đụng đĩa), ``apply()`` mới ghi. Nhờ đó ``--dry-run`` là thật
chứ không phải mô phỏng, và phần quyết định — vốn là chỗ dễ sai — kiểm
được bằng test mà không cần chép hàng trăm thư mục.

**Sao chép, không tạo liên kết.** Dự án đích phải tự đứng được: đưa cho
người khác, đẩy lên CI, hay mở trên máy không có thư mục ``references/``
thì vẫn chạy. Liên kết tượng trưng tiết kiệm đĩa nhưng đổi lấy một dự án
gãy khi rời khỏi máy này.

**Idempotent.** Chạy lại lần hai không nhân bản, và xoá skill không còn
được chọn — nếu không, đổi stack rồi cài lại sẽ để lại rác của lần trước.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .catalog import Catalog, Source
from .detect_stack import Stack
from .security_filter import Verdict, classify_all, select_for_stack
from .skills import Skill, scan

#: Nơi skill nằm trong dự án đích. Đây là đường dẫn Claude Code đọc.
SKILLS_DIR = ".claude/skills"

#: Skill do chính framework viết — nằm trong repo, không phải kho ngoài,
#: nên không cần ghim commit hay xét giấy phép.
OWN_SKILLS = Path(__file__).resolve().parent / "skills"

#: File đánh dấu skill do framework cài — để dọn lần sau mà không đụng
#: skill người dùng tự thêm.
MARKER = ".aisef-managed"
#: Tên đánh dấu của 0.1.0, khi lệnh và module còn tên `aisdlc`. Vẫn **đọc**
#: để skill cài bằng bản cũ được nhận là của framework — không nhận thì lần
#: cài sau bỏ sót chúng lại trên đĩa mãi. Chỉ **ghi** tên mới.
MARKER_LEGACY = ".aisdlc-managed"


@dataclass(frozen=True)
class PlannedSkill:
    name: str
    source_id: str
    path: Path
    reason: str


@dataclass
class InstallPlan:
    skills: list[PlannedSkill] = field(default_factory=list)
    skipped_sources: list[tuple[str, str]] = field(default_factory=list)

    def by_source(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self.skills:
            counts[s.source_id] = counts.get(s.source_id, 0) + 1
        return counts

    def summary(self) -> str:
        lines = [f"will install {len(self.skills)} skills:"]
        for src, n in sorted(self.by_source().items()):
            lines.append(f"  {src:12} {n}")
        for src, why in self.skipped_sources:
            lines.append(f"  {src:12} skipped — {why}")
        return "\n".join(lines)


@dataclass
class InstallReport:
    installed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.installed) + len(self.unchanged)

    def summary(self) -> str:
        return (
            f"installed {len(self.installed)} · unchanged {len(self.unchanged)} · "
            f"removed {len(self.removed)} · total {self.total}"
        )


def _select_from_source(
    source: Source,
    references_root: Path,
    stack: Stack,
    requirements_text: str,
) -> tuple[list[PlannedSkill], str | None]:
    """Chọn skill của một nguồn. Trả (danh sách, lý do bỏ qua nếu có)."""
    if not source.installable:
        return [], f"reference only (license: {source.license or 'none'})"

    if "frontend_or_mobile" in source.requires and not stack.has_ui:
        return [], "project has no UI"

    found: list[Skill] = []
    for root in source.roots(references_root):
        found.extend(scan(root))

    if not found:
        return [], "no skills found"

    if source.selection == "all":
        chosen = found
        reason = "entire source"

    elif source.selection == "allowlist":
        allow = set(source.allowlist)
        seen: set[str] = set()
        chosen = []
        for s in found:
            if s.name in allow and s.name not in seen:
                seen.add(s.name)  # ui-ux có bản sao ở cli/assets — chỉ lấy một
                chosen.append(s)
        reason = "in allowlist"

    elif source.selection == "filtered":
        results = classify_all(source.roots(references_root)[0])
        keep = [r for r in results if r.verdict is Verdict.KEEP]
        selected = select_for_stack(keep, stack.as_dict(), requirements_text=requirements_text)
        chosen = [r.skill for r in selected]
        reason = "passed two-tier filter, matching stack"

    else:
        return [], f"unknown selection mode: {source.selection}"

    return (
        [PlannedSkill(s.name, source.id, s.path, reason) for s in chosen],
        None,
    )


def plan(
    project: Path | str,
    stack: Stack,
    *,
    references_root: Path | str,
    requirements_text: str = "",
    catalog: Catalog | None = None,
) -> InstallPlan:
    """Quyết định cài gì. Không đụng đĩa của dự án đích."""
    cat = catalog or Catalog.load()
    refs = Path(references_root)
    result = InstallPlan()
    seen_names: set[str] = set()

    # Skill của framework đứng trước: chúng định nghĩa hợp đồng của framework,
    # nên khi trùng tên với kho ngoài thì bản của ta phải thắng.
    for skill in scan(OWN_SKILLS) if OWN_SKILLS.is_dir() else []:
        seen_names.add(skill.name)
        result.skills.append(
            PlannedSkill(skill.name, "aisef", skill.path, "framework skill")
        )

    for source in cat.sources:
        chosen, skip_reason = _select_from_source(source, refs, stack, requirements_text)
        if skip_reason:
            result.skipped_sources.append((source.id, skip_reason))
            continue
        for ps in chosen:
            if ps.name in seen_names:
                continue  # tên skill trùng giữa hai nguồn — nguồn trước thắng
            seen_names.add(ps.name)
            result.skills.append(ps)

    result.skills.sort(key=lambda s: (s.source_id, s.name))
    return result


def apply(plan_: InstallPlan, project: Path | str) -> InstallReport:
    """Ghi skill vào dự án. Idempotent, dọn skill không còn được chọn."""
    dest_root = Path(project) / SKILLS_DIR
    dest_root.mkdir(parents=True, exist_ok=True)
    report = InstallReport()

    wanted = {ps.name: ps for ps in plan_.skills}

    # Gỡ skill do framework cài mà lần này không còn chọn. Chỉ đụng thư mục
    # có file đánh dấu — skill người dùng tự thêm được giữ nguyên.
    for existing in dest_root.iterdir():
        if not existing.is_dir() or existing.name in wanted:
            continue
        if (existing / MARKER).exists() or (existing / MARKER_LEGACY).exists():
            shutil.rmtree(existing, ignore_errors=True)
            report.removed.append(existing.name)

    for name, ps in wanted.items():
        dest = dest_root / name
        if dest.exists():
            if _same_content(ps.path, dest):
                report.unchanged.append(name)
                continue
            shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(ps.path, dest, dirs_exist_ok=False)
        (dest / MARKER).write_text(
            f"source={ps.source_id}\nreason={ps.reason}\n", encoding="utf-8"
        )
        report.installed.append(name)

    return report


def _same_content(src: Path, dest: Path) -> bool:
    """So nhanh: cùng danh sách file và cùng nội dung SKILL.md.

    Không băm toàn bộ cây — skill là nội dung tĩnh đã ghim theo commit, và
    băm hàng trăm thư mục mỗi lần chạy tốn hơn giá trị nó mang lại.
    """
    src_md, dest_md = src / "SKILL.md", dest / "SKILL.md"
    if not (src_md.is_file() and dest_md.is_file()):
        return False
    if src_md.read_bytes() != dest_md.read_bytes():
        return False
    src_names = {p.name for p in src.iterdir()}
    dest_names = {p.name for p in dest.iterdir()} - {MARKER, MARKER_LEGACY}
    return src_names == dest_names
