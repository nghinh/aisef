"""Kiểm chứng guard — mỗi guard phải CHẶN THẬT ở đúng tình huống."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.harness.guardrails import (  # noqa: E402
    ENV_WRITE_SCOPE,
    GUARD_MATCHERS,
    check_destructive,
    check_git_stage,
    check_injection,
    check_secrets,
    check_write_scope,
    run_guard,
    scope_from_env,
)


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
        for kind in GUARD_MATCHERS:
            with self.subTest(guard=kind):
                self.assertTrue(run_guard(kind, {}, env={ENV_WRITE_SCOPE: "src"}).allowed)

    def test_every_guard_has_a_matcher(self):
        for kind in ("write-scope", "secret", "injection", "git-stage", "destructive"):
            self.assertIn(kind, GUARD_MATCHERS)

    def test_exit_code_convention(self):
        """Claude Code coi mã 2 là chặn (kiểm chứng ở spike S2)."""
        self.assertEqual(run_guard("git-stage", {"tool_input": {"command": "git add -A"}}).exit_code, 2)
        self.assertEqual(run_guard("git-stage", {"tool_input": {"command": "git status"}}).exit_code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
