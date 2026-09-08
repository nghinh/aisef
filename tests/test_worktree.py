"""Kiểm chứng cô lập story bằng git worktree — chạy trên kho git thật."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.worktree import (  # noqa: E402
    _git,
    main_repo,
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
        (self.repo / ".gitignore").write_text(".aisef/\n", encoding="utf-8")
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

    def test_stray_dir_is_not_a_worktree(self):
        """Lỗi 13: thư mục còn sót (`.vite/` của vite sống sót) không phải
        worktree — phải dọn và tạo thật, không trả về thư mục thường."""
        stray = self.wm.path_for("S-01")
        (stray / ".vite").mkdir(parents=True)
        (stray / ".vite" / "deps.json").write_text("{}", encoding="utf-8")
        wt = self.wm.create("S-01")
        self.assertTrue((wt.path / ".git").exists())
        self.assertFalse((wt.path / ".vite").exists())
        self.assertIn(str(wt.path), _git(self.repo, "worktree", "list").stdout)

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


class TestMainRepo(WorktreeTestCase):
    def test_from_the_repo_itself(self):
        self.assertEqual(main_repo(self.repo), self.repo.resolve())

    def test_from_inside_a_worktree(self):
        """Bất biến 2 — một gốc artifact. Agent chạy trong worktree, nhưng
        bằng chứng phải ghi về gốc chính, nếu không cổng đọc ở gốc chính
        sẽ thấy story "chưa từng chạy test" dù nó vừa chạy."""
        wt = self.wm.create("S-77")
        self.assertEqual(main_repo(wt.path), self.repo.resolve())

    def test_outside_git_returns_the_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main_repo(tmp), Path(tmp).resolve())


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


class TestNhanhStoryKhongBiCu(WorktreeTestCase):
    """Nối lại nhánh có sẵn phải mang nhánh chính vào trước.

    Lỗi 38, đo trên dự án `par`: chạy lại sau khi sửa `.ai/config.json` và
    `package.json` trên main, `create` nối lại nhánh story cũ nên bản sửa
    không tới worktree. Ba story trượt vì đúng cái lỗi đã được vá — mất
    $9,56 và một vòng chẩn đoán.
    """

    def tien_main(self, ten="moi.txt", noi_dung="x"):
        (self.repo / ten).write_text(noi_dung, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", f"main: {ten}"], cwd=self.repo, check=True)

    def test_noi_lai_nhanh_cu_thi_mang_main_vao(self):
        wt = self.wm.create("S-01")
        (wt.path / "cua-story.txt").write_text("s", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=wt.path, check=True)
        subprocess.run(["git", "commit", "-qm", "story"], cwd=wt.path, check=True)
        self.wm.remove("S-01")

        self.tien_main("sua-cau-hinh.txt", "đã sửa")
        lai = self.wm.create("S-01")

        self.assertTrue((lai.path / "sua-cau-hinh.txt").is_file(),
                        "bản sửa trên main phải tới được worktree")
        self.assertTrue((lai.path / "cua-story.txt").is_file(),
                        "công việc của story không được mất")
        self.assertTrue(lai.refreshed_from, "phải ghi lại đã mang nhánh nào vào")

    def test_nhanh_moi_khong_can_mang_gi(self):
        wt = self.wm.create("S-02")
        self.assertEqual(wt.refreshed_from, "", "nhánh mới đã rẽ từ main rồi")

    def test_khong_de_ra_commit_merge_rong(self):
        """Chạy lại khi main không tiến thì không được đẻ commit thừa."""
        self.wm.create("S-03")
        self.wm.remove("S-03")
        lai = self.wm.create("S-03")
        self.assertEqual(lai.refreshed_from, "")

    def test_dung_nhau_thi_bao_chu_khong_chay_tiep(self):
        """Story đứng trên trunk cũ mà cứ chạy là làm việc trên nền sai;
        giấu đi thì lỗi chỉ hiện ở lần merge cuối đợt, xa chỗ gây ra."""
        wt = self.wm.create("S-04")
        (wt.path / "chung.txt").write_text("bản của story", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=wt.path, check=True)
        subprocess.run(["git", "commit", "-qm", "story sửa"], cwd=wt.path, check=True)
        self.wm.remove("S-04")

        self.tien_main("chung.txt", "bản của main")
        with self.assertRaises(GitError) as e:
            self.wm.create("S-04")
        self.assertIn("chung.txt", str(e.exception))



class TestCauHinhClientVaoWorktree(WorktreeTestCase):
    """`.claude/settings.json` và `.opencode/` chưa commit vẫn phải có
    trong worktree — không thì guard không tới (hợp quy OpenCode C1)."""

    def test_untracked_client_config_is_carried(self):
        (self.repo / ".gitignore").write_text(".claude/\n.opencode/\n", encoding="utf-8")
        git(self.repo, "add", ".gitignore")
        git(self.repo, "commit", "-qm", "ignore client config")
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
        (self.repo / ".opencode" / "plugin").mkdir(parents=True)
        (self.repo / ".opencode" / "plugin" / "aisef-guard.ts").write_text("// g", encoding="utf-8")
        wt = self.wm.create("S-01")
        self.assertTrue((wt.path / ".claude" / "settings.json").is_file())
        self.assertTrue((wt.path / ".opencode" / "plugin" / "aisef-guard.ts").is_file())
        # Không làm bẩn cây: vẫn gitignore, không có gì để commit.
        self.assertEqual(git(wt.path, "status", "--porcelain").strip(), "")

    def test_nothing_to_carry_is_fine(self):
        wt = self.wm.create("S-02")
        self.assertFalse((wt.path / ".opencode").exists())


class TestWorktreeTam(WorktreeTestCase):
    """ADR-005 V6: worktree tách tạm ở đúng SHA, gỡ khi xong — kể cả khi lỗi."""

    def test_dung_sha_khong_phai_cay_va_go_sau_with(self):
        sha = git(self.repo, "rev-parse", "HEAD").strip()
        (self.repo / "src" / "base.py").write_text("VERSION = 2\n", encoding="utf-8")  # cây bẩn
        with self.wm.temporary(sha) as p:
            self.assertTrue((p / ".git").exists())
            self.assertEqual((p / "src" / "base.py").read_text(encoding="utf-8"), "VERSION = 1\n",
                             "từ SHA, không từ cây đang sửa")
            self.assertEqual(git(p, "rev-parse", "HEAD").strip(), sha)
            self.assertEqual(git(p, "branch", "--show-current").strip(), "", "tách, không tạo nhánh")
        self.assertFalse(p.exists())
        self.assertEqual(len(git(self.repo, "worktree", "list").strip().splitlines()), 1)

    def test_loi_ben_trong_van_go(self):
        sha = git(self.repo, "rev-parse", "HEAD").strip()
        with self.assertRaises(RuntimeError):
            with self.wm.temporary(sha) as p:
                raise RuntimeError("giữa chừng")
        self.assertFalse(p.exists())

    def test_sha_la_thi_nem_loi_khong_de_rac(self):
        with self.assertRaises(GitError):
            with self.wm.temporary("0000000"):
                pass
        self.assertEqual([d.name for d in self.wm.root.iterdir() if d.is_dir()], [])
