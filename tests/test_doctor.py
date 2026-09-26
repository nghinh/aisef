"""Doctor — kiểm hàm nội bộ không cần gọi model hay cài tool."""

from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.cli.doctor import _hook_paths_elsewhere  # noqa: E402


class TestHookPathsElsewhere(unittest.TestCase):
    def test_no_hooks_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(_hook_paths_elsewhere(Path(d)))

    def test_settings_same_project(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            claude = p / ".claude"
            claude.mkdir()
            (claude / "settings.json").write_text(
                f'{{"hooks": "aisef --project {p} guard"}}',
            )
            result = _hook_paths_elsewhere(p)
            self.assertEqual(result, [])

    def test_settings_different_project(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            claude = p / ".claude"
            claude.mkdir()
            (claude / "settings.json").write_text(
                '{"hooks": "aisef --project /other/proj guard"}',
            )
            result = _hook_paths_elsewhere(p)
            self.assertIn("/other/proj", result)

    def test_opencode_plugin_same_project(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            plugin_dir = p / ".opencode" / "plugin"
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "aisef-guard.ts").write_text(
                f'const PROJECT = "{p}";',
            )
            result = _hook_paths_elsewhere(p)
            self.assertEqual(result, [])

    def test_opencode_plugin_different_project(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            plugin_dir = p / ".opencode" / "plugin"
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "aisef-guard.ts").write_text(
                'const PROJECT = "/somewhere/else";',
            )
            result = _hook_paths_elsewhere(p)
            self.assertIn("/somewhere/else", result)

    def test_both_hooks_mixed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            claude = p / ".claude"
            claude.mkdir()
            (claude / "settings.json").write_text(
                f'{{"hooks": "aisef --project {p} guard"}}',
            )
            plugin_dir = p / ".opencode" / "plugin"
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "aisef-guard.ts").write_text(
                'const PROJECT = "/other/place";',
            )
            result = _hook_paths_elsewhere(p)
            self.assertEqual(result, ["/other/place"])


if __name__ == "__main__":
    unittest.main()


class TestDoctorNoiRoPhienAgentDangNhapBangGi(unittest.TestCase):
    """Biến môi trường nào quyết định danh tính của phiên agent — nêu tên, không nêu giá trị.

    Ngày 2026-09-12 một `ANTHROPIC_API_KEY` hết hạn trong shell ghi đè login
    `claude.ai` đang chạy được; triệu chứng duy nhất là mọi phiên trả 401 sau
    khi đốt hết thời gian chờ. `doctor` là nơi người vận hành nhìn *trước* khi
    trả tiền, nên nó phải nói ra điều này.
    """

    def _chay(self, env: dict) -> str:
        import io
        from contextlib import redirect_stdout
        from aisef.cli.doctor import cmd_doctor

        with tempfile.TemporaryDirectory() as d, \
             mock.patch.dict("os.environ", env, clear=False), \
             redirect_stdout(io.StringIO()) as ra:
            cmd_doctor(argparse.Namespace(project=d))
        return ra.getvalue()

    def test_neu_ten_bien_khi_co_khoa_trong_moi_truong(self):
        ra = self._chay({"ANTHROPIC_API_KEY": "sk-BI-MAT-KHONG-DUOC-IN"})
        self.assertIn("ANTHROPIC_API_KEY", ra)
        self.assertNotIn("sk-BI-MAT", ra, "giá trị khoá không bao giờ được in")

    def test_khong_co_khoa_thi_noi_client_tu_dang_nhap(self):
        import os as _os
        sach = {n: "" for n in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                                "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_BASE_URL")}
        with mock.patch.dict(_os.environ, sach, clear=False):
            ra = self._chay({})
        self.assertIn("agent credential", ra)
        self.assertIn("its own login", ra)


class TestDoctorTranNganSachSoVoiSoChi(unittest.TestCase):
    """Trần ngân sách thấp hơn số dự án đã tiêu là cấu hình sai, và `doctor`
    phải nói ra **trước** khi chạy: nếu không, lần gọi trả tiền kế tiếp bị
    `BudgetGuard` chặn và người vận hành đọc ra đó là lỗi của khung thay vì là
    con số của chính mình (ADR-009, mục Deferred).
    """

    NHAN = "budget cap above recorded spend"

    def _chay(self, cfg: dict | None = None, so: dict | None = None) -> str:
        import io
        import json
        from contextlib import redirect_stdout

        from aisef.cli.doctor import cmd_doctor

        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            if cfg is not None:
                (p / ".ai").mkdir()
                (p / ".ai" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
            if so is not None:
                (p / "_bmad-output").mkdir()
                (p / "_bmad-output" / "budget.json").write_text(
                    json.dumps(so), encoding="utf-8")
            with redirect_stdout(io.StringIO()) as ra:
                cmd_doctor(argparse.Namespace(project=str(p)))
        return ra.getvalue()

    def test_khong_dat_tran_thi_khong_mo_so(self):
        """Chưa đặt trần thì không phải trả một lần I/O nào cho tính năng này."""
        from aisef.control import budget

        with mock.patch.object(budget.BudgetLedger, "load",
                               side_effect=AssertionError("mở sổ khi chưa đặt trần")):
            ra = self._chay()
        self.assertNotIn(self.NHAN, ra)

    def test_tran_con_cho_thi_dat(self):
        ra = self._chay({"run.cost_cap_usd": 5.0}, {"spent_usd": 1.25})
        self.assertIn(f"✅ {self.NHAN}", ra)
        self.assertIn("$1.25", ra)
        self.assertIn("$5.00", ra)

    def test_live_reservations_are_listed_with_their_owner(self):
        """F5 / SS-52: `doctor` names every live reservation and its owner, and counts the dead or expired ones
        it would release (it writes nothing)."""
        import os
        import socket
        import time
        now = time.time()
        ra = self._chay({"run.cost_cap_usd": 5.0}, {"spent_usd": 1.0, "reservations": [
            {"id": "r-live", "owner": f"{socket.gethostname()}:{os.getpid()}", "est_usd": 0.75, "expires_at": now + 600},
            {"id": "r-old", "owner": "other-host:1", "est_usd": 2.0, "expires_at": now - 1}]})
        self.assertIn("budget reservations", ra)
        self.assertIn("1 live: r-live by", ra)
        self.assertIn("1 dead or expired", ra)
        self.assertNotIn("r-old by", ra)

    def test_tran_thap_hon_so_da_tieu_thi_chan(self):
        ra = self._chay({"run.cost_cap_usd": 0.5}, {"spent_usd": 1.25})
        self.assertIn(f"✗ {self.NHAN}", ra)
        self.assertIn("$0.50", ra)
        self.assertIn("$1.25", ra)
        self.assertIn("run.cost_cap_usd", ra)
        # Nêu ra thôi chưa đủ: phải tính vào danh sách chặn, vì chạy tiếp là mất lượt.
        self.assertRegex(ra, r"✗ missing:.*" + self.NHAN)

    def test_tran_bang_so_da_tieu_cung_la_chan(self):
        """Bằng nhau cũng chặn: lượt kế tiếp nào cũng vượt trần."""
        ra = self._chay({"run.turn_cap": 40}, {"spent_turns": 40})
        self.assertIn(f"✗ {self.NHAN}", ra)
        self.assertIn("40", ra)

    def test_doctor_khong_ghi_vao_so(self):
        """`doctor` chẩn đoán, không sửa: sổ chi và khoá của nó phải y nguyên."""
        import io
        import json
        from contextlib import redirect_stdout

        from aisef.cli.doctor import cmd_doctor

        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / ".ai").mkdir()
            (p / ".ai" / "config.json").write_text(json.dumps({"run.cost_cap_usd": 0.5}))
            (p / "_bmad-output").mkdir()
            so = p / "_bmad-output" / "budget.json"
            so.write_text(json.dumps({"spent_usd": 1.25}))
            truoc = (so.read_bytes(), sorted(x.name for x in (p / "_bmad-output").iterdir()))
            with redirect_stdout(io.StringIO()):
                cmd_doctor(argparse.Namespace(project=str(p)))
            self.assertEqual(
                truoc, (so.read_bytes(), sorted(x.name for x in (p / "_bmad-output").iterdir())))

    def test_chua_co_so_thi_khong_ket_luan(self):
        """Không có sổ để so là "không biết" — không phải đạt, cũng không phải chặn."""
        ra = self._chay({"run.cost_cap_usd": 5.0})
        self.assertIn(f"○ {self.NHAN}", ra)
        self.assertNotIn(f"✅ {self.NHAN}", ra)
        self.assertNotRegex(ra, r"✗ missing:.*" + self.NHAN)
