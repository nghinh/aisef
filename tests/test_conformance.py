"""Hợp đồng của bộ hợp quy: bảng đọc lại được, và "được phát hành không"
là code — không phải cảm giác khi nhìn bảng."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.control import conformance as C  # noqa: E402


def run(client, *cells, version="1.0", at="2026-09-05T00:00:00+00:00"):
    r = C.ClientRun(client=client, version=version, at=at)
    for pid, ok in zip([p[0] for p in C.PROBES], cells):
        r.results.append(C.ProbeResult(pid, ok, detail=f"{pid} quan sát"))
    return r


class TestBangDocLaiDuoc(unittest.TestCase):
    def test_vong_tron_markdown(self):
        rep = C.Report(runs=[run("claude", True, True, True, True, True),
                             run("opencode", True, False, True, True, True)],
                       generated="2026-09-05")
        back = C.parse(rep.to_markdown())
        self.assertEqual(back.generated, "2026-09-05")
        self.assertEqual([r.client for r in back.runs], ["claude", "opencode"])
        self.assertTrue(back.run_for("claude").passed)
        self.assertFalse(back.run_for("opencode").passed)
        self.assertEqual(back.run_for("opencode").cell("C2"), "✗")

    def test_bang_neu_ro_opencode_khong_chan_phat_hanh(self):
        md = C.Report(runs=[run("claude", *[True] * 5)]).to_markdown()
        self.assertIn("không chặn phát hành", md)
        self.assertIn("bằng chứng", md)


class TestDuocPhatHanhKhong(unittest.TestCase):
    def rep(self, *runs, generated="2026-09-05"):
        return C.Report(runs=list(runs), generated=generated)

    def test_claude_du_va_moi_thi_duoc(self):
        ok, why = C.release_ready(self.rep(run("claude", *[True] * 5)), today=date(2026, 9, 10))
        self.assertTrue(ok, why)

    def test_bang_cu_hon_14_ngay_thi_khong(self):
        ok, why = C.release_ready(self.rep(run("claude", *[True] * 5)), today=date(2026, 9, 25))
        self.assertFalse(ok); self.assertIn("cũ", why)

    def test_claude_co_o_do_thi_khong(self):
        ok, why = C.release_ready(self.rep(run("claude", True, False, True, True, True)),
                                  today=date(2026, 9, 6))
        self.assertFalse(ok); self.assertIn("C2", why)

    def test_claude_thieu_phep_thi_khong(self):
        ok, why = C.release_ready(self.rep(run("claude", True, True, True)), today=date(2026, 9, 6))
        self.assertFalse(ok); self.assertIn("thiếu", why)

    def test_opencode_do_khong_chan(self):
        """Quyết định 2026-09-05: OpenCode hạng hai."""
        ok, _ = C.release_ready(self.rep(run("claude", *[True] * 5), run("opencode", *[False] * 5)),
                                today=date(2026, 9, 6))
        self.assertTrue(ok)

    def test_chua_co_cot_claude_thi_khong(self):
        ok, why = C.release_ready(self.rep(run("opencode", *[True] * 5)), today=date(2026, 9, 6))
        self.assertFalse(ok); self.assertIn("claude", why)


class TestBangThatNeuCo(unittest.TestCase):
    def test_bang_trong_kho_neu_ton_tai_thi_doc_duoc(self):
        p = ROOT / C.REPORT_PATH
        if not p.is_file():
            self.skipTest("chưa có docs/CONFORMANCE.md")
        rep = C.parse(p.read_text(encoding="utf-8"))
        self.assertTrue(rep.runs, "bảng không đọc ra client nào")


if __name__ == "__main__":
    unittest.main()


class TestChiPhiKhongMatKhiGhep(unittest.TestCase):
    """Ghép cột client thứ hai đọc lại bảng: chi phí cột đầu phải còn."""

    def test_cost_survives_roundtrip(self):
        from aisdlc.control import conformance as C
        r = C.ClientRun(client="claude", version="1")
        r.results = [C.ProbeResult("C1", True, "d", 0.31), C.ProbeResult("C2", True, "d", 0.29)]
        rep2 = C.parse(C.Report(runs=[r]).to_markdown())
        self.assertAlmostEqual(rep2.run_for("claude").cost_usd, 0.60, places=2)


class TestBoChayHopQuyPhanMay(unittest.TestCase):
    """Phần không cần agent thật của `tests/conformance/_runner.py`."""

    def test_opencode_tools_from_stderr(self):
        from tests.conformance import _runner as R
        text = ("\x1b[0m> build · m\n\x1b[0m$ \x1b[0mrm -rf x\n→ Read src/a.js [offset=1]\n← Write src/b.md\n"
                "✗ Write src/ping.py failed\n✱ Glob \"src/*.js\" in . · 1 match\nĐã xong.\n")
        self.assertEqual(R.opencode_tools(text), ["Bash", "Read", "Write", "Write", "Glob"])

    def test_session_env_is_not_inherited(self):
        import os
        from unittest import mock
        from tests.conformance import _runner as R
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "x",
                                          "ANTHROPIC_API_KEY": "k"}):
            env = R.env_for(Path("/p"), Path("/p/w"), "S-1")
        self.assertNotIn("CLAUDECODE", env)
        self.assertNotIn("CLAUDE_CODE_ENTRYPOINT", env)
        self.assertEqual(env["ANTHROPIC_API_KEY"], "k")
