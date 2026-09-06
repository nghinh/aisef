"""Lấy kho nguồn skill về máy, theo đúng commit đã ghim trong catalog.

Trước đây `aisdlc setup` đòi thư mục ``references/`` đã clone sẵn nằm cạnh
dự án. Điều đó chỉ đúng khi framework chạy từ bản sao kho nguồn: người cài
bằng ``pip install aisef`` không có cách nào có được thư mục ấy, và
``setup`` dừng ngay ở dòng đầu.

Nguồn skill là tài sản của **framework**, không phải của dự án đích — nên
nó thuộc cache của người dùng, dùng chung cho mọi dự án. Mỗi nguồn được
lấy đúng ``commit`` catalog ghim: skill đổi giữa chừng thì kế hoạch cài
đổi theo mà không ai biết, và bản dựng hết tái lập được.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .catalog import Catalog, Source

#: Biến môi trường cho phép trỏ sang thư mục nguồn khác (CI, máy ngoại tuyến).
ENV_REFS = "AISDLC_REFERENCES"

CLONE_TIMEOUT = 300


def default_root() -> Path:
    """Nơi chứa nguồn skill: cache của người dùng, không phải trong dự án."""
    if env := os.environ.get(ENV_REFS):
        return Path(env).expanduser().resolve()
    base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    return Path(base).expanduser().resolve() / "ai-sdlc" / "references"


@dataclass
class FetchReport:
    fetched: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed

    def summary(self) -> str:
        dong = []
        for i in self.fetched:
            dong.append(f"  ✅ lấy về {i}")
        for i in self.already:
            dong.append(f"  ○ đã có   {i}")
        for i, ly_do in self.failed:
            dong.append(f"  ✗ hỏng    {i} — {ly_do}")
        return "\n".join(dong) or "  (không nguồn nào cần lấy)"


def _dir_of(source: Source, root: Path) -> Path:
    """Thư mục đích của một nguồn, khớp với cách `Source.roots` tra đường."""
    return Path(root).parent / source.local_path


def _at_commit(d: Path, commit: str) -> bool:
    try:
        r = subprocess.run(
            ["git", "-C", str(d), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and r.stdout.strip() == commit


def _clone(source: Source, dest: Path) -> str:
    """Clone nông đúng một commit. Trả chuỗi rỗng nếu xong, ngược lại là lỗi."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tam = dest.with_name(dest.name + ".dang-lay")
    shutil.rmtree(tam, ignore_errors=True)
    try:
        for cmd in (
            ["git", "init", "--quiet", str(tam)],
            ["git", "-C", str(tam), "remote", "add", "origin", source.repo],
            ["git", "-C", str(tam), "fetch", "--quiet", "--depth", "1",
             "--no-tags", "origin", source.commit],
            ["git", "-C", str(tam), "checkout", "--quiet", "FETCH_HEAD"],
        ):
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=CLONE_TIMEOUT)
            if r.returncode != 0:
                loi = (r.stderr or r.stdout).strip().splitlines()
                return loi[-1] if loi else f"git trả mã {r.returncode}"
    except subprocess.TimeoutExpired:
        return f"quá {CLONE_TIMEOUT}s"
    except OSError as e:
        return str(e)
    shutil.rmtree(dest, ignore_errors=True)
    tam.replace(dest)
    return ""


def ensure(
    root: Path | str | None = None,
    *,
    catalog: Catalog | None = None,
    only: list[str] | None = None,
) -> FetchReport:
    """Bảo đảm mọi nguồn trong catalog có mặt ở `root`, đúng commit đã ghim.

    Nguồn nào đã đúng commit thì không đụng tới — gọi lại nhiều lần không
    tốn gì. Một nguồn hỏng không làm chết các nguồn còn lại: `setup` vẫn
    cài được phần lấy được, và báo rõ phần thiếu.
    """
    root = Path(root) if root is not None else default_root()
    cat = catalog or Catalog.load()
    bao = FetchReport()
    for source in cat.sources:
        if only and source.id not in only:
            continue
        dest = _dir_of(source, root)
        if _at_commit(dest, source.commit):
            bao.already.append(source.id)
            continue
        loi = _clone(source, dest)
        (bao.fetched if not loi else bao.failed).append(
            source.id if not loi else (source.id, loi)
        )
    return bao
