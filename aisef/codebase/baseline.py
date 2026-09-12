"""Baseline builder — snapshot the current state of a brownfield project.

The output is ``baseline.md`` under ``_bmad-output/`` — a description of the
existing system that the agent uses as context when receiving change requests.
The framework treats source code as ground truth; stale brownfield docs are
acknowledged, not silently ignored.
"""

from __future__ import annotations

import os
import subprocess
from datetime import date
from pathlib import Path

from .detect import detect
from .provider import CodebaseGraphProvider, resolve

BASELINE_FILE = "baseline.md"

_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "dist",
    "build", ".next", ".nuxt", "target", "vendor", "_bmad-output",
    "graphify-out", ".aisef",
}


def _tree(project: Path, max_depth: int = 3, max_items: int = 200) -> str:
    """Shallow directory tree — enough to see structure, not enough to overflow."""
    lines: list[str] = []
    count = 0
    for root, dirs, files in os.walk(project):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
        depth = len(Path(root).relative_to(project).parts)
        if depth >= max_depth:
            dirs.clear()
            continue
        indent = "  " * depth
        for d in dirs:
            lines.append(f"{indent}{d}/")
            count += 1
            if count >= max_items:
                lines.append(f"{indent}  … (cắt ở {max_items})")
                return "\n".join(lines)
        for f in sorted(files)[:20]:
            lines.append(f"{indent}{f}")
            count += 1
            if count >= max_items:
                return "\n".join(lines)
    return "\n".join(lines)


def _git_info(project: Path) -> dict:
    """Basic git information."""
    info: dict = {}
    try:
        info["branch"] = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
        ).stdout.strip()
        info["commit_count"] = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=project, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
        ).stdout.strip()
        info["last_commit"] = subprocess.run(
            ["git", "log", "-1", "--format=%h %s", "--no-walk"],
            cwd=project, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
        ).stdout.strip()
        info["contributors"] = subprocess.run(
            ["git", "shortlog", "-sn", "--no-merges", "HEAD"],
            cwd=project, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        ).stdout.strip().count("\n") + 1
    except (subprocess.TimeoutExpired, OSError):
        pass
    return info


def _existing_docs(project: Path) -> list[str]:
    """Find existing documentation files."""
    docs: list[str] = []
    for name in ("README.md", "CHANGELOG.md", "CONTRIBUTING.md",
                 "ARCHITECTURE.md", "DESIGN.md"):
        if (project / name).is_file():
            docs.append(name)
    docs_dir = project / "docs"
    if docs_dir.is_dir():
        for f in sorted(docs_dir.iterdir()):
            if f.suffix.lower() in {".md", ".txt", ".rst"} and f.stat().st_size > 100:
                docs.append(f"docs/{f.name}")
    adr_dir = project / "docs" / "adr"
    if not adr_dir.is_dir():
        adr_dir = project / "docs" / "ADR"
    if adr_dir.is_dir():
        for f in sorted(adr_dir.iterdir()):
            if f.suffix.lower() == ".md":
                docs.append(f"docs/adr/{f.name}")
    return docs[:30]


def build_baseline(
    project: Path,
    *,
    provider: CodebaseGraphProvider | None = None,
    output: Path | None = None,
) -> str:
    """Build baseline.md — current-state snapshot.

    Returns Markdown content.  Writes to ``output`` if provided.
    """
    sig = detect(project)
    if not sig.is_brownfield:
        text = (
            "# Baseline — Greenfield\n\n"
            "Dự án chưa có mã nguồn — chế độ greenfield, bắt đầu từ requirements.md.\n"
        )
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding="utf-8")
        return text

    prov = provider or resolve(project)
    git = _git_info(project)
    docs = _existing_docs(project)
    tree = _tree(project)

    graph_section = ""
    if prov.name == "graphify":
        r = prov.build(project)
        if r.ok:
            graph_section = (
                f"\n## Đồ thị mã nguồn (Graphify)\n\n"
                f"- Nút: {r.nodes:,}\n"
                f"- Cạnh: {r.edges:,}\n"
            )
            if r.report:
                graph_section += f"\n### Tóm tắt kiến trúc\n\n{r.report[:3000]}\n"
    else:
        r = prov.build(project)
        graph_section = (
            f"\n## Bản đồ mã (basic — grep + import tĩnh)\n\n"
            f"- File mã: {r.nodes:,}\n"
            f"- Import edges: {r.edges:,}\n"
            f"- _(Cài `graphify` để có đồ thị đầy đủ: "
            f"`uv tool install graphifyy && graphify .`)_\n"
        )

    sections = [
        "# Baseline — Current-State Snapshot\n",
        f"_Dựng lúc {date.today().isoformat()} bằng `aisef baseline`._\n",
        f"\n## Tín hiệu brownfield\n\n{sig.summary}\n",
    ]

    if git:
        sections.append(
            f"\n## Git\n\n"
            f"- Nhánh: `{git.get('branch', '?')}`\n"
            f"- Số commit: {git.get('commit_count', '?')}\n"
            f"- Commit cuối: {git.get('last_commit', '?')}\n"
            f"- Người đóng góp: {git.get('contributors', '?')}\n"
        )

    langs = sorted(sig.languages.items(), key=lambda kv: -kv[1])
    if langs:
        sections.append(
            "\n## Ngôn ngữ\n\n"
            + "\n".join(f"- `.{ext}`: {n} file" for ext, n in langs[:10])
            + "\n"
        )

    if sig.config_files:
        sections.append(
            "\n## Build / Package\n\n"
            + "\n".join(f"- `{c}`" for c in sig.config_files[:10])
            + "\n"
        )

    if sig.ci_present:
        sections.append("\n## CI/CD\n\nCó cấu hình CI (`.github/workflows/` hoặc tương đương).\n")

    if sig.test_files:
        sections.append(f"\n## Test\n\n{sig.test_files} file test phát hiện được.\n")

    if sig.schema_files:
        sections.append(f"\n## Schema / Migration\n\n{sig.schema_files} file schema/migration.\n")

    if docs:
        sections.append(
            "\n## Tài liệu hiện có\n\n"
            + "\n".join(f"- `{d}`" for d in docs)
            + "\n\n> **Lưu ý**: mã nguồn là ground truth. Khi tài liệu mâu thuẫn với code, "
              "ghi nhận mâu thuẫn rõ ràng — không im lặng chọn bên nào.\n"
        )

    sections.append(f"\n## Cấu trúc thư mục\n\n```\n{tree}\n```\n")
    sections.append(graph_section)

    sections.append(
        "\n## Hướng dẫn cho agent\n\n"
        "1. **Bảo toàn**: không thay đổi kiến trúc / code / behavior hợp lệ hiện có "
        "trừ khi change request yêu cầu.\n"
        "2. **Ground truth**: code hiện tại là sự thật; tài liệu có thể stale — "
        "mọi mâu thuẫn phải được ghi nhận.\n"
        "3. **Blast radius**: trước khi thay đổi, chạy impact analysis để biết phạm vi ảnh hưởng.\n"
        "4. **Traceability**: mỗi thay đổi phải trace được tới requirement (mới hoặc hiện có) và test.\n"
    )

    text = "\n".join(sections)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    return text
