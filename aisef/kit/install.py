"""Install skills into the target project.

Deliberately split into two steps: ``plan()`` decides what to install (pure
computation, no disk I/O), ``apply()`` writes. This makes ``--dry-run``
genuine rather than simulated, and the decision logic — the part most likely
to have bugs — testable without copying hundreds of directories.

**Copy, don't symlink.** The target project must be self-contained: hand it
to someone else, push to CI, or open on a machine without the ``references/``
directory and it still works. Symlinks save disk but break the project the
moment it leaves this machine.

**Idempotent.** A second run doesn't duplicate, and removes skills no longer
selected — otherwise changing the stack and re-installing would leave stale
artifacts from the previous run.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .catalog import Catalog, Source
from .detect_stack import Stack
from .security_filter import Verdict, classify_all, select_for_stack
from .skills import Skill, scan

#: Where skills live in the target project. This is the path Claude Code reads.
SKILLS_DIR = ".claude/skills"

#: Skills authored by the framework itself — lives in this repo, not an
#: external source, so no commit pinning or license check needed.
OWN_SKILLS = Path(__file__).resolve().parent / "skills"

#: Marker file for framework-installed skills — allows cleanup on next run
#: without touching user-added skills.
MARKER = ".aisef-managed"
#: Legacy marker name from 0.1.0 when the CLI/module was named `aisdlc`.
#: Still **read** so skills installed by the old version are recognized as
#: framework-managed — otherwise they'd be left on disk forever. Only the
#: new name is **written**.
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
    """Select skills from one source. Returns (list, skip reason if any)."""
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
                seen.add(s.name)  # ui-ux has a copy in cli/assets — take only one
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
    """Decide what to install. Does not touch the target project's disk."""
    cat = catalog or Catalog.load()
    refs = Path(references_root)
    result = InstallPlan()
    seen_names: set[str] = set()

    # Framework skills come first: they define the framework's contract, so
    # when a name collides with an external source, ours must win.
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
                continue  # skill name collision between two sources — first wins
            seen_names.add(ps.name)
            result.skills.append(ps)

    result.skills.sort(key=lambda s: (s.source_id, s.name))
    return result


def apply(plan_: InstallPlan, project: Path | str) -> InstallReport:
    """Write skills to the project. Idempotent; removes deselected skills."""
    dest_root = Path(project) / SKILLS_DIR
    dest_root.mkdir(parents=True, exist_ok=True)
    report = InstallReport()

    wanted = {ps.name: ps for ps in plan_.skills}

    # Remove framework-installed skills that are no longer selected. Only
    # touch directories with the marker file — user-added skills are kept.
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
    """Quick comparison: same file list and same SKILL.md content.

    Doesn't hash the entire tree — skills are static content pinned by commit,
    and hashing hundreds of directories per run costs more than the value it
    provides.
    """
    src_md, dest_md = src / "SKILL.md", dest / "SKILL.md"
    if not (src_md.is_file() and dest_md.is_file()):
        return False
    if src_md.read_bytes() != dest_md.read_bytes():
        return False
    src_names = {p.name for p in src.iterdir()}
    dest_names = {p.name for p in dest.iterdir()} - {MARKER, MARKER_LEGACY}
    return src_names == dest_names
