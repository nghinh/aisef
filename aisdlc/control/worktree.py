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


def commit_paths(path: Path, message: str, *, paths: list[str] | None = None) -> bool:
    """Chốt phần còn dở của một cây làm việc. False nghĩa là không có gì để chốt.

    Stage **đúng phạm vi ghi**, không `add -A` (bất biến 5). `diff-scope`
    thường đã xác nhận cây nằm trong phạm vi nên hai cách cho cùng kết quả —
    nhưng chỉ khi guard đã chạy. Stage theo phạm vi thì đúng cả khi nó chưa
    chạy, và đó mới là điều bất biến bảo vệ.
    """
    if not _git(path, "status", "--porcelain", check=False).stdout.strip():
        return False  # agent đã tự commit hết

    # Chỉ stage đường dẫn **có thật**: story khai một tệp rồi không tạo ra
    # nó là chuyện thường, nhất là khi nó trượt giữa chừng, và `git add`
    # với pathspec không khớp thì gãy cả lệnh. Bỏ đường rỗng không nới lỏng
    # gì — vẫn không phải `add -A`.
    co_that = [p for p in (paths or []) if (path / p).exists()]
    if co_that:
        _git(path, "add", "--", *co_that)
    else:
        _git(path, "add", "-u")  # không khai phạm vi: chỉ file đã theo dõi
    if not _git(path, "diff", "--cached", "--name-only", check=False).stdout.strip():
        return False
    _git(path, "commit", "-q", "-m", message)
    return True


def main_repo(path: Path | str) -> Path:
    """Kho chính của một đường dẫn, kể cả khi đang đứng trong worktree.

    Story chạy trong worktree riêng, nhưng bằng chứng và trạng thái phải
    ghi về **một gốc artifact duy nhất** (bất biến 2). Nếu không, mỗi story
    ghi vào gốc riêng của nó và cổng đọc ở gốc chính sẽ không thấy gì.
    """
    path = Path(path).resolve()
    proc = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return path
    common = Path(proc.stdout.strip())
    return common.parent if common.name == ".git" else path


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
    #: Nhánh chính đã được mang vào lúc nối lại, hoặc "" nếu không cần.
    #: Ghi ra để người đọc biết worktree này đứng trên nền nào.
    refreshed_from: str = ""


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


#: Cấu hình client mà `compile` sinh ra và dự án có thể không commit.
CLIENT_CONFIG = (".claude/settings.json", ".opencode")


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

    def has_branch(self, story_id: str) -> bool:
        """Nhánh story còn đó không — worktree gỡ rồi thì đây là nơi giữ
        công việc, và là ứng viên của lượt kiểm-lại."""
        return self._branch_exists(self.branch_for(story_id))

    def create(self, story_id: str, *, base: str | None = None,
               refresh: bool = True) -> Worktree:
        """Tạo worktree cho story. Idempotent: đã có thì trả về cái đang có.

        Nhánh có sẵn thì **mang nhánh chính vào trước khi giao cho agent**
        — trừ khi ``refresh=False``: lượt kiểm-lại (ADR-004 R13) chấm đúng
        ứng viên đã đóng băng ở HEAD nhánh story, và một commit merge là một
        bản mới làm mọi bằng chứng cũ thành stale.
        Không làm thế thì story chạy lại vẫn đứng trên trunk lúc nó rẽ ra:
        bản sửa cấu hình, bản vá công cụ, và công việc của story đã merge
        ở đợt trước đều không tới nơi. Đo trên dự án `par`:
        `story/STORY-01-01` rẽ từ `e0a6b4e`, bản vá lệnh test nằm ở
        `963dae3`, và story trượt vì đúng cái lỗi đã được sửa trên main.

        Merge chứ không rebase: rebase viết lại lịch sử agent đã commit,
        và conflict giữa chừng một chuỗi commit thì không ai gỡ nổi.
        """
        path, branch = self.path_for(story_id), self.branch_for(story_id)
        if (path / ".git").exists():
            return Worktree(story_id, path, branch)
        if path.exists():
            # Thư mục có mà không phải worktree (lỗi 13, đo 2026-09-05 trên
            # e9 A/B): tiến trình vite sống sót sau khi gỡ worktree ghi lại
            # `.vite/` vào đúng chỗ ấy; lần chạy sau tưởng worktree còn, agent
            # làm việc trong một thư mục thường nằm **trong repo chính**, guard
            # so diff với repo chính và chặn mọi Bash — 16 lần chặn, $0 việc.
            # Thư mục ấy là của harness: không phải worktree thì là rác.
            shutil.rmtree(path)
            _git(self.repo, "worktree", "prune")

        self._ensure_root()
        co_san = self._branch_exists(branch)
        args = ["worktree", "add", "-q"]
        if co_san:
            args += [str(path), branch]  # nhánh có sẵn — nối lại, không tạo mới
        else:
            args += [str(path), "-b", branch]
            if base:
                args.append(base)
        _git(self.repo, *args)
        self._carry_client_config(path)

        # Tính trước rồi mới dựng: `Worktree` là bất biến, và giữ nó bất
        # biến đáng hơn một dòng ngắn.
        mang_vao = self.refresh(story_id, base=base) if co_san and refresh else ""
        return Worktree(story_id, path, branch, refreshed_from=mang_vao)

    def _carry_client_config(self, path: Path) -> list[str]:
        """Chép cấu hình client do `compile` sinh vào worktree khi nó chưa
        được commit. Claude nhận `--settings` tường minh, nhưng OpenCode chỉ
        đọc `.opencode/` của thư mục nó chạy — không chép thì guard không
        tới. Đo ở hợp quy 2026-09-05: OpenCode C1 `rm -rf` chạy thật, tệp
        mất, vì worktree không có plugin."""
        chep = []
        for rel in CLIENT_CONFIG:
            src, dst = self.repo / rel, path / rel
            if not src.exists() or dst.exists():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            chep.append(rel)
        return chep

    def refresh(self, story_id: str, *, base: str | None = None) -> str:
        """Mang nhánh chính vào nhánh story. Trả tên nhánh nguồn, hoặc "".

        Conflict thì abort và **ném lỗi**: story đứng trên trunk cũ mà cứ
        chạy tiếp là làm việc trên nền sai, và giấu chuyện đó đi thì lỗi
        chỉ hiện ra ở lần merge cuối đợt, xa chỗ gây ra nó.
        """
        path = self.path_for(story_id)
        goc = base or self._current_branch()
        if not goc or not path.is_dir():
            return ""
        # Đã chứa đầu nhánh chính rồi thì không cần merge — tránh đẻ ra
        # một commit merge rỗng mỗi lần chạy lại.
        dau = _git(self.repo, "rev-parse", goc, check=False).stdout.strip()
        if dau and _git(
            path, "merge-base", "--is-ancestor", dau, "HEAD", check=False
        ).returncode == 0:
            return ""

        proc = _git(path, "merge", "--no-edit", goc, check=False)
        if proc.returncode == 0:
            return goc
        dung = [
            l.strip()
            for l in _git(path, "diff", "--name-only", "--diff-filter=U",
                          check=False).stdout.splitlines()
            if l.strip()
        ]
        _git(path, "merge", "--abort", check=False)
        raise GitError(
            f"{story_id}: không mang được `{goc}` vào nhánh story — đụng "
            f"{', '.join(dung[:5]) or 'không rõ file'}. Nhánh story đã rẽ quá "
            f"xa; gỡ nhánh rồi chạy lại, hoặc hợp nhất bằng tay."
        )

    def _current_branch(self) -> str:
        out = _git(self.repo, "rev-parse", "--abbrev-ref", "HEAD", check=False).stdout.strip()
        return "" if out in ("", "HEAD") else out

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

    def commit_story(
        self, story_id: str, message: str = "", *, paths: list[str] | None = None
    ) -> bool:
        """Chốt công việc còn dở trong worktree của story.

        Agent được khuyến khích tự commit từng phần, nhưng phần còn dở thì
        harness chốt: merge chỉ nhìn thấy thứ đã commit, nên bỏ bước này
        thì story "xong" mà công việc không sang được nhánh chính.

        Stage **đúng phạm vi ghi của story**, không `add -A` (bất biến 5).
        `diff-scope` vừa xác nhận cây nằm trong phạm vi nên hai cách cho
        cùng kết quả — nhưng chỉ khi guard đã chạy. Stage theo phạm vi thì
        đúng cả khi nó chưa chạy, và đó mới là điều bất biến bảo vệ.
        """
        path = self.path_for(story_id)
        if not path.is_dir():
            return False
        return commit_paths(path, message or f"{story_id}: hoàn tất", paths=paths)

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
