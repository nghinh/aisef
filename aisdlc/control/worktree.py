"""Cô lập story chạy song song bằng git worktree.

Chia đợt theo ``write_scope`` chỉ tránh được đụng *nội dung file*. Ba thứ
vẫn đụng nếu nhiều story chạy chung một thư mục làm việc:

* ``git add`` / ``git commit`` đồng thời tranh ``index.lock``;
* test đồng thời tranh cổng mạng, cơ sở dữ liệu, file tạm;
* cài phụ thuộc đồng thời làm hỏng ``node_modules`` / venv.

Mỗi story trong một đợt vì thế chạy trong worktree riêng, có nhánh riêng.
Worktree dùng chung ``.git`` nên tạo nhanh và tốn ít đĩa.

Hết đợt, các nhánh được **merge tuần tự** vào nhánh chính. Xem
``merge_story`` để hiểu vì sao conflict ở đây là tín hiệu chứ không phải
sự cố. Cơ chế đã kiểm chứng ở spike S5 (`docs/SPIKE-REPORT.md`).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

#: Nơi chứa worktree, tương đối so với gốc repo.
WORKTREE_ROOT = ".aisdlc/worktrees"

#: Tiền tố nhánh của story.
BRANCH_PREFIX = "story/"

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class GitError(RuntimeError):
    """Lệnh git thất bại."""


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc


def safe_slug(story_id: str) -> str:
    """Biến id story thành mảnh tên nhánh/thư mục an toàn."""
    slug = _SAFE.sub("-", story_id).strip("-")
    if not slug:
        raise ValueError(f"story id không dùng được: {story_id!r}")
    return slug


@dataclass(frozen=True)
class Worktree:
    story_id: str
    path: Path
    branch: str


@dataclass
class MergeResult:
    story_id: str
    branch: str
    merged: bool
    conflicts: list[str] = field(default_factory=list)
    message: str = ""

    @property
    def scope_was_misdeclared(self) -> bool:
        """Conflict nghĩa là hai story đã chạm cùng vùng.

        Bộ lập lịch chỉ xếp chung đợt những story có ``write_scope`` rời
        nhau, nên nếu merge vẫn đụng thì phạm vi đã khai sai.
        """
        return bool(self.conflicts)


class WorktreeManager:
    """Tạo, dọn và hợp nhất worktree của story."""

    def __init__(self, repo: Path, *, root: str = WORKTREE_ROOT):
        self.repo = Path(repo).resolve()
        self.root = self.repo / root
        if not (self.repo / ".git").exists():
            raise GitError(f"{self.repo} không phải kho git")

    # ------------------------------------------------------------ tạo, dọn

    def path_for(self, story_id: str) -> Path:
        return self.root / safe_slug(story_id)

    def branch_for(self, story_id: str) -> str:
        return f"{BRANCH_PREFIX}{safe_slug(story_id)}"

    def create(self, story_id: str, *, base: str | None = None) -> Worktree:
        """Tạo worktree cho story. Idempotent: đã có thì trả về cái đang có."""
        path, branch = self.path_for(story_id), self.branch_for(story_id)
        if path.exists():
            return Worktree(story_id, path, branch)

        self._ensure_root()
        args = ["worktree", "add", "-q"]
        if self._branch_exists(branch):
            args += [str(path), branch]  # nhánh có sẵn — nối lại, không tạo mới
        else:
            args += [str(path), "-b", branch]
            if base:
                args.append(base)
        _git(self.repo, *args)
        return Worktree(story_id, path, branch)

    def remove(self, story_id: str, *, delete_branch: bool = False) -> None:
        """Gỡ worktree. Không xoá nhánh trừ khi được yêu cầu — công việc
        đã commit không được biến mất chỉ vì dọn thư mục."""
        path = self.path_for(story_id)
        if path.exists():
            _git(self.repo, "worktree", "remove", "--force", str(path), check=False)
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
        _git(self.repo, "worktree", "prune", check=False)
        if delete_branch:
            _git(self.repo, "branch", "-D", self.branch_for(story_id), check=False)

    def list_active(self) -> list[str]:
        """Id story đang có worktree."""
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir() if p.is_dir())

    # ------------------------------------------------------------ hợp nhất

    def merge_story(self, story_id: str, *, into: str | None = None) -> MergeResult:
        """Merge nhánh story vào nhánh chính.

        Conflict thì **abort ngay** và trả danh sách file đụng. Không tự gỡ:
        theo bộ lập lịch, hai story chung đợt lẽ ra không thể chạm cùng vùng,
        nên conflict là bằng chứng ``write_scope`` khai sai — cần người xem
        lại phần chẻ story, không phải cần một lần merge khéo hơn.
        """
        branch = self.branch_for(story_id)
        if into:
            _git(self.repo, "checkout", "-q", into)

        proc = _git(self.repo, "merge", "--no-edit", branch, check=False)
        if proc.returncode == 0:
            return MergeResult(story_id, branch, True, message=proc.stdout.strip())

        conflicts = [
            l.strip()
            for l in _git(self.repo, "diff", "--name-only", "--diff-filter=U", check=False).stdout.splitlines()
            if l.strip()
        ]
        _git(self.repo, "merge", "--abort", check=False)
        return MergeResult(
            story_id,
            branch,
            False,
            conflicts=conflicts,
            message=(proc.stderr or proc.stdout).strip(),
        )

    def merge_wave(self, story_ids: list[str], *, into: str | None = None) -> list[MergeResult]:
        """Merge cả một đợt, **tuần tự** theo thứ tự truyền vào.

        Dừng ngay khi gặp conflict đầu tiên: merge tiếp lên một cây đang
        có vấn đề chỉ làm khó lần nguyên nhân.
        """
        results: list[MergeResult] = []
        for sid in story_ids:
            r = self.merge_story(sid, into=into)
            results.append(r)
            if not r.merged:
                break
        return results

    # ------------------------------------------------------------ nội bộ

    def _ensure_root(self) -> None:
        """Tạo thư mục worktree và **tự loại nó khỏi git**.

        Worktree nằm bên trong kho nên nếu không ignore, mọi ``git status``
        đều bẩn thêm một dòng ``?? .aisdlc/`` — đủ để làm hỏng phép kiểm
        "cây sạch sau khi abort merge", và dễ bị nuốt vào commit. Đặt một
        ``.gitignore`` chứa ``*`` ngay trong thư mục là cách tự loại trừ
        gọn nhất, không phải sửa ``.gitignore`` của dự án.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        marker = self.root / ".gitignore"
        if not marker.exists():
            marker.write_text("*\n", encoding="utf-8")

    def _branch_exists(self, branch: str) -> bool:
        return _git(
            self.repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False
        ).returncode == 0
