"""Kiểm chứng guard — mỗi guard phải CHẶN THẬT ở đúng tình huống."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.harness.guardrails import (
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
)
from aisdlc.harness.observe import EvidenceStore  # noqa: E402


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
        self.assertIn("chưa khai write_scope", v.reason)

    def test_no_file_path_is_not_a_write(self):
        self.assertTrue(check_write_scope("", ["src"]).allowed)

    def test_multiple_scopes(self):
        scope = ["src/api", "tests"]
        self.assertTrue(check_write_scope("tests/test_api.py", scope).allowed)
        self.assertFalse(check_write_scope("docs/x.md", scope).allowed)

    def test_absolute_path_outside_project_blocked(self):
        v = check_write_scope("/etc/passwd", ["src"], project_root="/tmp/du-an")
        self.assertFalse(v.allowed)
        self.assertIn("ngoài thư mục dự án", v.reason)

    def test_reason_tells_agent_what_to_do(self):
        """Lý do được chuyển vào kết quả tool cho agent đọc — phải hành động được."""
        v = check_write_scope("x.py", ["src"])
        self.assertIn("write_scope", v.reason)
        self.assertIn("dừng lại và báo", v.reason)


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
        self.assertIn("dòng 3", v.reason)

    def test_clean_content_allowed(self):
        self.assertTrue(check_secrets("def cong(a, b):\n    return a + b\n").allowed)


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
        for cmd in ("git status", "git commit -m 'FR-01: x'", "pytest", "rm build/tmp.txt"):
            with self.subTest(cmd=cmd):
                self.assertTrue(check_destructive(cmd).allowed)


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
        self.assertIn("chưa có lần chạy test", v.reason)

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

        from aisdlc.harness.tools import aisdlc_command

        binary = aisdlc_command()
        self.assertIn(f"{binary} tool test", self.verdict().reason)
        if binary != "aisdlc":
            self.assertTrue(os.access(binary, os.X_OK))

    def test_stale_message_also_names_the_command(self):
        self.store.tool_run("S-01", "test", ok=True)
        self.store.file_change("S-01", "src/b.py")
        from aisdlc.harness.tools import aisdlc_command

        self.assertIn(f"{aisdlc_command()} tool test", self.verdict().reason)

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
        self.assertIn("nằm ngoài cây đang làm việc", v.reason)

    def test_chan_ca_khi_ra_gocdu_an_la_cha_cua_cay(self):
        """Gốc dự án là **cha** của worktree — đúng ca đã gặp thật."""
        v = self.guard("destructive", cwd="/tmp/par/.aisdlc/worktrees/S1",
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
            env={ENV_WORKDIR: "/tmp/par/.aisdlc/worktrees/S1"},
        )
        self.assertFalse(v.allowed)
        self.assertIn("/tmp/par/.aisdlc/worktrees/S1", v.reason)

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
        self.assertIn("không được dùng tool Write", v.reason)

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

    def test_guard_khac_cho_qua_thi_chi_ghi_nhip_tim(self):
        """Cho qua và không phải write-scope/diff-scope: không có gì để ghi
        ngoài nhịp tim "hook tới được" (một lần)."""
        record_outcome("git-stage", {"tool_name": "Bash", "tool_input": {"command": "ls"}},
                       ALLOW, env=self.env, artifact_root=str(self.root))
        ev = self.store.read("S-01")
        self.assertEqual([e.kind for e in ev.events], ["guard_seen"])


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
