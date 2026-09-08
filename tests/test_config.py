"""Kiểm chứng cấu hình và ngưỡng."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.config import CONFIG_PATH, DEFAULTS, Config, ConfigError  # noqa: E402


class ConfigTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, data: dict):
        p = self.root / CONFIG_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data), encoding="utf-8")
        return p


class TestDefaults(ConfigTestCase):
    def test_loads_without_file(self):
        c = Config.load(self.root, env={})
        self.assertEqual(c["coverage.min"], 0.85)
        self.assertEqual(c["run.max_parallel"], 3)
        self.assertEqual(c.source, "defaults")

    def test_every_documented_key_present(self):
        """10 khoá trong SOLUTION mục 13 phải có mặt."""
        c = Config.load(self.root, env={})
        for key in (
            "coverage.min", "story.max_acceptance_criteria",
            "story.max_write_scope_paths",
            "run.max_parallel", "run.max_turns", "run.timeout_seconds",
            "run.max_retries", "cost.warn_multiple", "security.block_severities",
            "verify.baseline", "clients.env_allow", "verify.nop",
        ):
            self.assertIn(key, c.values, key)

    def test_env_allow_mac_dinh_rong_va_la_danh_sach(self):
        """ADR-005 V2: không khai thì không biến nào của máy qua thêm."""
        c = Config.load(self.root, env={})
        self.assertEqual(c["clients.env_allow"], [])
        c = Config.load(self.root, env={"AISEF_CLIENTS_ENV_ALLOW": "NINEROUTER_, OPENAI_"})
        self.assertEqual(c["clients.env_allow"], ["NINEROUTER_", "OPENAI_"])

    def test_unknown_key_raises(self):
        with self.assertRaises(KeyError):
            Config.load(self.root, env={})["khong.ton.tai"]


class TestProjectFile(ConfigTestCase):
    def test_file_overrides_default(self):
        self.write({"coverage.min": 0.95})
        c = Config.load(self.root, env={})
        self.assertEqual(c["coverage.min"], 0.95)
        self.assertIn(CONFIG_PATH, c.source)

    def test_partial_file_keeps_other_defaults(self):
        self.write({"run.max_parallel": 8})
        c = Config.load(self.root, env={})
        self.assertEqual(c["run.max_parallel"], 8)
        self.assertEqual(c["coverage.min"], DEFAULTS["coverage.min"])

    def test_unknown_key_in_file_rejected(self):
        """Khoá lạ thường là gõ nhầm — báo ngay còn hơn im lặng bỏ qua."""
        self.write({"coverage.minimum": 0.9})
        with self.assertRaises(ConfigError) as ctx:
            Config.load(self.root, env={})
        self.assertIn("coverage.minimum", str(ctx.exception))

    def test_malformed_json_rejected(self):
        p = self.root / CONFIG_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{ hỏng", encoding="utf-8")
        with self.assertRaises(ConfigError):
            Config.load(self.root, env={})


class TestEnvOverride(ConfigTestCase):
    def test_env_beats_file(self):
        self.write({"run.max_parallel": 5})
        c = Config.load(self.root, env={"AISEF_RUN_MAX_PARALLEL": "9"})
        self.assertEqual(c["run.max_parallel"], 9)

    def test_float_from_env(self):
        c = Config.load(self.root, env={"AISEF_COVERAGE_MIN": "0.7"})
        self.assertEqual(c["coverage.min"], 0.7)

    def test_bool_from_env(self):
        c = Config.load(self.root, env={"AISEF_SANDBOX_ALLOW_DEGRADED": "false"})
        self.assertFalse(c["sandbox.allow_degraded"])

    def test_list_from_env(self):
        c = Config.load(self.root, env={"AISEF_SECURITY_BLOCK_SEVERITIES": "critical, high, medium"})
        self.assertEqual(c["security.block_severities"], ["critical", "high", "medium"])

    def test_bad_env_value_rejected(self):
        with self.assertRaises(ConfigError):
            Config.load(self.root, env={"AISEF_RUN_MAX_PARALLEL": "nhiều"})


class TestValidation(ConfigTestCase):
    def test_coverage_out_of_range(self):
        self.write({"coverage.min": 1.5})
        with self.assertRaises(ConfigError):
            Config.load(self.root, env={})

    def test_parallel_below_one(self):
        self.write({"run.max_parallel": 0})
        with self.assertRaises(ConfigError):
            Config.load(self.root, env={})

    def test_retries_can_be_zero(self):
        self.write({"run.max_retries": 0})
        self.assertEqual(Config.load(self.root, env={})["run.max_retries"], 0)

    def test_warn_multiple_must_exceed_one(self):
        """Cảnh báo khi vượt 1× trung vị thì gần như luôn kêu — vô nghĩa."""
        self.write({"cost.warn_multiple": 1.0})
        with self.assertRaises(ConfigError):
            Config.load(self.root, env={})

    def test_bool_not_accepted_as_int(self):
        """True là int trong Python — đừng để nó lọt vào ô số."""
        self.write({"run.max_parallel": True})
        with self.assertRaises(ConfigError):
            Config.load(self.root, env={})

    def test_int_accepted_where_float_expected(self):
        self.write({"cost.warn_multiple": 3})
        c = Config.load(self.root, env={})
        self.assertIsInstance(c["cost.warn_multiple"], float)

    def test_wrong_type_rejected(self):
        self.write({"run.max_turns": "nhiều"})
        with self.assertRaises(ConfigError):
            Config.load(self.root, env={})


class TestTemplate(ConfigTestCase):
    def test_writes_readable_template(self):
        c = Config.load(self.root, env={})
        p = c.write_template(self.root)
        self.assertTrue(p.is_file())
        self.assertEqual(json.loads(p.read_text(encoding="utf-8")), DEFAULTS)

    def test_template_reloads_cleanly(self):
        Config.load(self.root, env={}).write_template(self.root)
        self.assertEqual(Config.load(self.root, env={})["coverage.min"], DEFAULTS["coverage.min"])


class TestMembership(unittest.TestCase):
    def test_in_operator(self):
        cfg = Config(dict(DEFAULTS))
        self.assertIn("run.max_turns", cfg)
        self.assertNotIn("khong-co", cfg)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestKhoaDaGo(unittest.TestCase):
    """Knob không có mã đọc là lời hứa suông. Gỡ thì phải có di trú: dự án
    cũ nạp được, có cảnh báo, không lỗi."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / ".ai").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_khoa_da_go_khong_lam_vo_du_an_cu(self):
        import contextlib, io
        (self.root / ".ai" / "config.json").write_text(
            '{"story.max_context_tokens": 40000, "run.max_turns": 12}', encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            c = Config.load(self.root)
        self.assertEqual(c["run.max_turns"], 12)
        self.assertNotIn("story.max_context_tokens", c)
        self.assertIn("is retired", err.getvalue())
        self.assertIn("prompt_chars", err.getvalue())

    def test_khoa_la_van_la_loi(self):
        (self.root / ".ai" / "config.json").write_text('{"story.max_ctx": 1}', encoding="utf-8")
        with self.assertRaises(ConfigError):
            Config.load(self.root)

    def test_moi_khoa_da_go_deu_co_ly_do_co_ngay(self):
        from aisef.config import RETIRED
        for k, why in RETIRED.items():
            self.assertRegex(why, r"^20\d\d-\d\d-\d\d", k)
            self.assertNotIn(k, DEFAULTS, f"{k} vừa gỡ vừa còn trong DEFAULTS")
