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
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
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


class TestScopeInvariants(WorktreeTestCase):
    def test_absent_scope_does_not_stage_unrelated(self):
        from aisef.control.worktree import commit_paths

        (self.repo / "src/base.py").write_text("changed\n")
        self.assertFalse(commit_paths(self.repo, "scoped", paths=["missing"]))
        self.assertEqual(git(self.repo, "diff", "--cached", "--name-only"), "")

    def test_deletion_is_staged_alongside_existing_scope(self):
        from aisef.control.worktree import commit_paths

        (self.repo / "src/base.py").unlink()
        (self.repo / "new.py").write_text("new\n")
        self.assertTrue(commit_paths(self.repo, "scoped", paths=["src/base.py", "new.py"]))
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_prestaged_outside_scope_is_preserved_and_rejected(self):
        from aisef.control.worktree import commit_paths

        (self.repo / ".gitignore").write_text("changed\n")
        git(self.repo, "add", ".gitignore")
        before = git(self.repo, "rev-parse", "HEAD")
        with self.assertRaises(GitError):
            commit_paths(self.repo, "scoped", paths=["src"])
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)
        self.assertEqual(git(self.repo, "diff", "--cached", "--name-only").strip(), ".gitignore")


class TestCandidateInvariants(WorktreeTestCase):
    def test_changed_branch_cannot_merge_verified_sha(self):
        wt = self.wm.create("S-01")
        candidate = git(wt.path, "rev-parse", "HEAD").strip()
        self.commit_in(wt.path, "src/new.py", "unverified\n", "drift")
        before = git(self.repo, "rev-parse", "HEAD")
        result = self.wm.merge_story("S-01", expected_candidate=candidate)
        self.assertFalse(result.merged)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)

    def test_dirty_candidate_cannot_merge(self):
        wt = self.wm.create("S-01")
        candidate = git(wt.path, "rev-parse", "HEAD").strip()
        (wt.path / "src/base.py").write_text("unverified\n")
        self.assertFalse(self.wm.merge_story("S-01", expected_candidate=candidate).merged)

    def test_disjoint_merge_preserves_verified_parent(self):
        wt = self.wm.create("S-01")
        self.commit_in(wt.path, "src/story.py", "story\n", "story")
        candidate = git(wt.path, "rev-parse", "HEAD").strip()
        self.commit_in(self.repo, "src/main.py", "main\n", "main")
        result = self.wm.merge_story("S-01", expected_candidate=candidate)
        self.assertTrue(result.merged)
        self.assertIn(candidate, git(self.repo, "rev-list", "--parents", "-n", "1", "HEAD"))


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
        # git prints worktree paths with `/` on every OS
        self.assertIn(wt.path.as_posix(), _git(self.repo, "worktree", "list").stdout)

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
            capture_output=True, text=True, encoding="utf-8", errors="replace",
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
        self.assertIn("diverged", str(e.exception))

    def test_cau_hinh_client_chua_theo_doi_khong_chan_duoc_merge(self):
        """Lỗi 123 (todo-cli 2026-09-13). Harness tự chép `.claude/settings.json`
        vào worktree dưới dạng **chưa theo dõi**. Ngày dự án commit đúng đường
        dẫn ấy lên main, git từ chối merge ("untracked working tree files would
        be overwritten") — không tệp nào xung đột, nên thông báo không nêu được
        tên tệp nào và khuyên **xoá nhánh**, tức vứt việc đã commit vì một thứ
        dọn cây là xong."""
        wt = self.wm.create("S-05")
        (wt.path / "cua-story.txt").write_text("s", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=wt.path, check=True)
        subprocess.run(["git", "commit", "-qm", "story"], cwd=wt.path, check=True)
        # Harness chép vào worktree, không commit — đúng như `sync_client_config`.
        (wt.path / ".claude").mkdir(exist_ok=True)
        (wt.path / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8")

        # Dự án commit đúng đường dẫn ấy lên main.
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude" / "settings.json").write_text('{"hooks": {}}\n', encoding="utf-8")
        subprocess.run(["git", "add", "-f", ".claude/settings.json"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "main: commit hooks"], cwd=self.repo, check=True)

        self.assertEqual(self.wm.refresh("S-05", base="master"), "master")
        self.assertTrue((wt.path / "cua-story.txt").is_file(), "việc của story còn nguyên")

    def test_git_tu_choi_truoc_khi_xung_dot_thi_khong_khuyen_xoa_nhanh(self):
        """Không tệp nào xung đột nghĩa là merge chưa đi tới đó. Thông báo phải
        đưa lý do thật của git, và không được bảo người ta xoá nhánh."""
        wt = self.wm.create("S-06")
        (wt.path / "cua-story.txt").write_text("s", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=wt.path, check=True)
        subprocess.run(["git", "commit", "-qm", "story"], cwd=wt.path, check=True)
        # Tệp chưa theo dõi **không** thuộc CLIENT_CONFIG: harness không dọn hộ.
        (wt.path / "chung.txt").write_text("bản chưa theo dõi", encoding="utf-8")
        self.tien_main("chung.txt", "bản của main")

        with self.assertRaises(GitError) as e:
            self.wm.refresh("S-06", base="master")
        loi = str(e.exception)
        self.assertIn("chung.txt", loi, "phải nêu được tệp git nói")
        self.assertNotIn("delete the branch", loi)
        self.assertIn("clean the worktree", loi)



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

    def test_lam_moi_nhanh_duoc_khi_cau_hinh_client_da_commit(self):
        """Lỗi 39. Ghi đè cấu hình client lên một tệp **đã theo dõi** làm
        `git merge` từ chối chạy ("local changes would be overwritten"), nên
        worktree của story không nhận được bản sửa trên nhánh chính.

        Đo trên todo/STORY-01-02 2026-09-09: `aisef run` dừng với "cannot
        merge master into story branch — conflicts in unknown files", trong
        khi `git merge-tree` cho thấy hai nhánh gộp sạch. Không có xung đột
        nào cả: chính harness làm bẩn cây.
        """
        (self.repo / ".opencode" / "plugin").mkdir(parents=True)
        guard = self.repo / ".opencode" / "plugin" / "aisef-guard.ts"
        guard.write_text("// v1", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "commit plugin")

        wt = self.wm.create("S-04")                       # nhánh story ra đời ở đây
        (wt.path / "src" / "story.py").write_text("x = 1\n", encoding="utf-8")
        git(wt.path, "add", "-A")
        git(wt.path, "commit", "-qm", "story")

        self.wm.remove("S-04")                            # cuối lượt: harness dọn worktree

        guard.write_text("// v2 — compile chạy lại", encoding="utf-8")   # nhánh chính đi tiếp
        (self.repo / "src" / "tren-nhanh-chinh.py").write_text("y = 2\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "trunk moves on")

        again = self.wm.create("S-04")                    # lượt sau: dựng lại từ nhánh story
        self.assertTrue(again.refreshed_from, "không gộp được nhánh chính vào story")
        self.assertTrue((again.path / "src" / "tren-nhanh-chinh.py").is_file(),
                        "bản sửa trên nhánh chính chưa tới worktree")
        self.assertEqual((again.path / ".opencode" / "plugin" / "aisef-guard.ts")
                         .read_text(encoding="utf-8"), "// v2 — compile chạy lại")
        self.assertTrue((again.path / "src" / "story.py").is_file(), "mất việc của story")

    def test_ban_da_commit_khong_duoc_thang_ban_moi_bien_dich(self):
        """Lỗi 32. Dự án `todo` **commit** `.opencode/plugin/aisef-guard.ts`,
        nên worktree luôn checkout bản đã commit — bản `aisef compile` vừa
        sửa nằm ở gốc dự án mà không story nào dùng tới, và cả lượt chạy
        không có guard. Cấu hình client là artifact sinh ra: ghi đè."""
        (self.repo / ".opencode" / "plugin").mkdir(parents=True)
        guard = self.repo / ".opencode" / "plugin" / "aisef-guard.ts"
        guard.write_text("// hong", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "commit plugin")
        guard.write_text("// da sua", encoding="utf-8")     # compile chạy lại, chưa commit

        wt = self.wm.create("S-03")
        trong_wt = wt.path / ".opencode" / "plugin" / "aisef-guard.ts"
        self.assertEqual(trong_wt.read_text(encoding="utf-8"), "// da sua")

        guard.write_text("// sua lan hai", encoding="utf-8")  # worktree đã tồn tại
        self.wm.create("S-03")
        self.assertEqual(trong_wt.read_text(encoding="utf-8"), "// sua lan hai",
                         "worktree dùng lại vẫn phải nhận bản guard mới nhất")


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


class TestNhanhCuKhiTieuChiDoi(WorktreeTestCase):
    """Lỗi 143. Story hỏng **giữ** nhánh là cố ý: lượt sau đứng trên lượt
    trước. Nhưng khi người vận hành sửa tiêu chí — đúng việc thông báo chết
    kẹt bảo họ làm — thì các commit ấy trả lời một câu hỏi không còn được
    hỏi nữa, trong khi **mã tiêu chí** sống sót qua việc đánh số lại.

    Đo trên todo-oc STORY-04-02 ngày 2026-09-14: bỏ AC-1, gộp AC-2 với AC-3,
    nhánh vẫn mang `AC-STORY-04-02-1: textarea has a visible placeholder`.
    Người viết mã mở ra thấy mọi thứ đã xanh nên không viết gì trong 20 lượt.
    Phép kiểm nop chặn được (test cũ xanh ở điểm rẽ nhánh) nên không có PASS
    giả — nhưng lượt ấy mất trắng, và lượt sau y hệt sẽ ra thông báo chết kẹt
    đổ cho *kế hoạch* vừa được sửa đúng.
    """

    def setUp(self):
        super().setUp()
        from aisef.control.normalize import Story

        self.artifacts = Path(self._tmp.name) / "_bmad-output"
        self.artifacts.mkdir()
        self.story = Story(id="STORY-01-01", epic_id="EPIC-01", title="t",
                           acceptance_criteria=["nút mờ khi ô trống"])

    def _chay(self, story):
        from aisef.phases.run import _drop_branch_written_for_other_criteria

        _drop_branch_written_for_other_criteria(
            story, worktrees=self.wm, artifact_root=self.artifacts)

    def _nhanh_co_viec(self, story_id: str) -> str:
        wt = self.wm.create(story_id)
        (wt.path / "src" / "x.py").write_text("X = 1\n", encoding="utf-8")
        git(wt.path, "add", "-A")
        git(wt.path, "commit", "-qm", "attempt 1")
        sha = git(wt.path, "rev-parse", "HEAD").strip()
        self.wm.remove(story_id)          # worktree đi, nhánh ở lại
        return sha

    def test_lan_dau_chi_ghi_nho_khong_xoa_gi(self):
        sha = self._nhanh_co_viec(self.story.id)
        self._chay(self.story)
        self.assertTrue(self.wm.has_branch(self.story.id))
        self.assertEqual(
            git(self.repo, "rev-parse", self.wm.branch_for(self.story.id)).strip(), sha)

    def test_tieu_chi_khong_doi_thi_giu_nguyen_viec_cu(self):
        self._chay(self.story)
        sha = self._nhanh_co_viec(self.story.id)
        self._chay(self.story)
        self.assertTrue(self.wm.has_branch(self.story.id))
        self.assertEqual(
            git(self.repo, "rev-parse", self.wm.branch_for(self.story.id)).strip(), sha)

    def test_tieu_chi_doi_thi_bo_nhanh(self):
        from aisef.control.normalize import Story

        self._chay(self.story)
        self._nhanh_co_viec(self.story.id)
        sua = Story(id=self.story.id, epic_id="EPIC-01", title="t",
                    acceptance_criteria=["nút mờ khi ô trống, sáng khi có chữ"])
        self._chay(sua)
        self.assertFalse(self.wm.has_branch(self.story.id),
                         "nhánh viết cho tiêu chí cũ phải bị bỏ")
        self._chay(sua)                    # lần sau không còn gì để bỏ
        self.assertFalse(self.wm.has_branch(self.story.id))

    def test_pham_vi_ghi_doi_khong_phai_ly_do_bo_viec(self):
        """Thẻ story còn mang các đường dẫn harness tự thêm — chúng đổi theo
        bản nâng cấp khung, không nói gì về việc story là gì."""
        from aisef.control.normalize import Story

        self._chay(self.story)
        sha = self._nhanh_co_viec(self.story.id)
        self._chay(Story(id=self.story.id, epic_id="EPIC-01", title="t",
                         acceptance_criteria=list(self.story.acceptance_criteria),
                         write_scope=["src/", "tests/"]))
        self.assertTrue(self.wm.has_branch(self.story.id))
        self.assertEqual(
            git(self.repo, "rev-parse", self.wm.branch_for(self.story.id)).strip(), sha)
