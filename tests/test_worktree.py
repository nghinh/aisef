"""Kiểm chứng cô lập story bằng git worktree — chạy trên kho git thật."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.control.worktree import (  # noqa: E402
    GitError,
    WorktreeManager,
    safe_slug,
)


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {p.stderr}")
    return p.stdout


class WorktreeTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "T")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "base.py").write_text("VERSION = 1\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "init")
        self.wm = WorktreeManager(self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    def commit_in(self, wt_path: Path, rel: str, content: str, msg: str):
        f = wt_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        git(wt_path, "add", rel)
        git(wt_path, "commit", "-qm", msg)


class TestSlug(unittest.TestCase):
    def test_normal_id(self):
        self.assertEqual(safe_slug("STORY-01-02"), "STORY-01-02")

    def test_unsafe_characters_replaced(self):
        self.assertEqual(safe_slug("story/01 02:x"), "story-01-02-x")

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            safe_slug("///")


class TestLifecycle(WorktreeTestCase):
    def test_create_makes_worktree_and_branch(self):
        wt = self.wm.create("S-01")
        self.assertTrue(wt.path.is_dir())
        self.assertEqual(wt.branch, "story/S-01")
        self.assertIn("story/S-01", git(self.repo, "branch", "--list", "story/S-01"))

    def test_create_is_idempotent(self):
        a = self.wm.create("S-01")
        b = self.wm.create("S-01")
        self.assertEqual(a.path, b.path)

    def test_list_active(self):
        self.wm.create("S-01")
        self.wm.create("S-02")
        self.assertEqual(self.wm.list_active(), ["S-01", "S-02"])

    def test_remove_keeps_branch_by_default(self):
        """Công việc đã commit không được biến mất chỉ vì dọn thư mục."""
        self.wm.create("S-01")
        self.wm.remove("S-01")
        self.assertFalse(self.wm.path_for("S-01").exists())
        self.assertIn("story/S-01", git(self.repo, "branch", "--list", "story/S-01"))

    def test_remove_can_delete_branch(self):
        self.wm.create("S-01")
        self.wm.remove("S-01", delete_branch=True)
        self.assertEqual(git(self.repo, "branch", "--list", "story/S-01").strip(), "")

    def test_recreate_after_remove_reuses_branch(self):
        wt = self.wm.create("S-01")
        self.commit_in(wt.path, "src/a.py", "a\n", "FR-01: a")
        self.wm.remove("S-01")
        wt2 = self.wm.create("S-01")
        self.assertTrue((wt2.path / "src" / "a.py").exists())

    def test_not_a_repo_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(GitError):
                WorktreeManager(Path(d))


class TestParallelMerge(WorktreeTestCase):
    def test_disjoint_scopes_merge_cleanly(self):
        a = self.wm.create("S-A")
        b = self.wm.create("S-B")
        self.commit_in(a.path, "src/a.py", "def a(): ...\n", "FR-01: story A")
        self.commit_in(b.path, "src/b.py", "def b(): ...\n", "FR-02: story B")

        results = self.wm.merge_wave(["S-A", "S-B"])
        self.assertTrue(all(r.merged for r in results))
        self.assertTrue((self.repo / "src" / "a.py").exists())
        self.assertTrue((self.repo / "src" / "b.py").exists())

    def test_overlapping_writes_conflict_and_abort(self):
        """Hai story cùng sửa một file → conflict, và repo phải sạch sau abort."""
        c = self.wm.create("S-C")
        d = self.wm.create("S-D")
        self.commit_in(c.path, "src/base.py", "VERSION = 2\n", "FR-03: story C")
        self.commit_in(d.path, "src/base.py", "VERSION = 3\n", "FR-04: story D")

        r1 = self.wm.merge_story("S-C")
        self.assertTrue(r1.merged)

        r2 = self.wm.merge_story("S-D")
        self.assertFalse(r2.merged)
        self.assertIn("src/base.py", r2.conflicts)
        self.assertTrue(r2.scope_was_misdeclared)
        # abort đã đưa cây về trạng thái sạch
        self.assertEqual(git(self.repo, "status", "--porcelain").strip(), "")

    def test_wave_stops_at_first_conflict(self):
        """Không merge tiếp lên cây đang có vấn đề."""
        c = self.wm.create("S-C")
        d = self.wm.create("S-D")
        e = self.wm.create("S-E")
        self.commit_in(c.path, "src/base.py", "VERSION = 2\n", "FR-03: C")
        self.commit_in(d.path, "src/base.py", "VERSION = 3\n", "FR-04: D")
        self.commit_in(e.path, "src/e.py", "e\n", "FR-05: E")

        results = self.wm.merge_wave(["S-C", "S-D", "S-E"])
        self.assertEqual(len(results), 2)          # dừng ngay sau conflict
        self.assertTrue(results[0].merged)
        self.assertFalse(results[1].merged)
        self.assertFalse((self.repo / "src" / "e.py").exists())

    def test_worktree_dir_does_not_dirty_git_status(self):
        """Thư mục worktree nằm trong kho — phải tự loại khỏi git."""
        self.wm.create("S-A")
        self.assertEqual(git(self.repo, "status", "--porcelain").strip(), "")

    def test_clean_merge_is_not_flagged_as_misdeclared(self):
        a = self.wm.create("S-A")
        self.commit_in(a.path, "src/a.py", "a\n", "FR-01: A")
        r = self.wm.merge_story("S-A")
        self.assertFalse(r.scope_was_misdeclared)


class TestCommitStory(WorktreeTestCase):
    """Harness chốt phần agent để dở — merge chỉ thấy thứ đã commit."""

    def test_commits_only_inside_write_scope(self):
        """Bất biến 5: không `git add -A`. Stage theo phạm vi thì đúng cả
        khi guard chưa kịp chạy — và đó mới là thứ bất biến bảo vệ."""
        wt = self.wm.create("S-01")
        (wt.path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
        (wt.path / "rac.txt").write_text("không thuộc story\n", encoding="utf-8")

        self.assertTrue(self.wm.commit_story("S-01", "S-01: xong", paths=["src"]))
        tracked = subprocess.run(
            ["git", "-C", str(wt.path), "show", "--name-only", "--format=", "HEAD"],
            capture_output=True, text=True,
        ).stdout.split()
        self.assertIn("src/a.py", tracked)
        self.assertNotIn("rac.txt", tracked)

    def test_nothing_to_commit(self):
        self.wm.create("S-02")
        self.assertFalse(self.wm.commit_story("S-02", paths=["src"]))

    def test_unknown_story(self):
        self.assertFalse(self.wm.commit_story("S-99", paths=["src"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
