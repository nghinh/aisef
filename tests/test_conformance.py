"""Hợp đồng của bộ hợp quy: bảng đọc lại được, và "được phát hành không"
là code — không phải cảm giác khi nhìn bảng."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control import conformance as C  # noqa: E402


def run(client, *cells, version="1.0", at="2026-09-05T00:00:00+00:00"):
    r = C.ClientRun(client=client, version=version, at=at)
    # phép thử cố tình truyền ít ô hơn số probe — cắt theo bên ngắn hơn
    for pid, ok in zip([p[0] for p in C.PROBES], cells, strict=False):
        r.results.append(C.ProbeResult(pid, ok, detail=f"{pid} quan sát"))
    return r


class TestBangDocLaiDuoc(unittest.TestCase):
    def test_vong_tron_markdown(self):
        rep = C.Report(runs=[run("claude", *[True] * len(C.PROBES)),
                             run("opencode", True, False, *[True] * (len(C.PROBES) - 2))],
                       generated="2026-09-05")
        back = C.parse(rep.to_markdown())
        self.assertEqual(back.generated, "2026-09-05")
        self.assertEqual([r.client for r in back.runs], ["claude", "opencode"])
        self.assertTrue(back.run_for("claude").passed)
        self.assertFalse(back.run_for("opencode").passed)
        self.assertEqual(back.run_for("opencode").cell("C2"), "✗")
        # C10 là mã hai chữ số đầu tiên — regex đọc lại `C\d` thì mất nó và
        # cột claude thành "thiếu C10" dù bảng ghi ✅.
        self.assertEqual(back.run_for("claude").cell("C10"), "✅")
        self.assertEqual(back.run_for("claude").results[-1].detail, "C10 quan sát")

    def test_bang_neu_ro_opencode_khong_chan_phat_hanh(self):
        md = C.Report(runs=[run("claude", *[True] * len(C.PROBES))]).to_markdown()
        self.assertIn("does not block release", md)
        self.assertIn("evidence", md)


class TestDuocPhatHanhKhong(unittest.TestCase):
    def rep(self, *runs, generated="2026-09-05"):
        return C.Report(runs=list(runs), generated=generated)

    def test_claude_du_va_moi_thi_duoc(self):
        ok, why = C.release_ready(self.rep(run("claude", *[True] * len(C.PROBES))), today=date(2026, 9, 10))
        self.assertTrue(ok, why)

    def test_bang_cu_hon_14_ngay_thi_khong(self):
        ok, why = C.release_ready(self.rep(run("claude", *[True] * len(C.PROBES))), today=date(2026, 9, 25))
        self.assertFalse(ok); self.assertIn("old", why)

    def test_claude_co_o_do_thi_khong(self):
        ok, why = C.release_ready(self.rep(run("claude", True, False, *[True] * (len(C.PROBES) - 2))),
                                  today=date(2026, 9, 6))
        self.assertFalse(ok); self.assertIn("C2", why)

    def test_claude_thieu_phep_thi_khong(self):
        ok, why = C.release_ready(self.rep(run("claude", True, True, True)), today=date(2026, 9, 6))
        self.assertFalse(ok); self.assertIn("missing", why)

    def test_opencode_do_khong_chan(self):
        """Quyết định 2026-09-05: OpenCode hạng hai."""
        ok, _ = C.release_ready(self.rep(run("claude", *[True] * len(C.PROBES)), run("opencode", *[False] * len(C.PROBES))),
                                today=date(2026, 9, 6))
        self.assertTrue(ok)

    def test_chua_co_cot_claude_thi_khong(self):
        ok, why = C.release_ready(self.rep(run("opencode", *[True] * len(C.PROBES))), today=date(2026, 9, 6))
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
        from aisef.control import conformance as C
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
        """Bộ hợp quy dùng đúng `child_env` của harness: `CLAUDE*` và canary
        ngoài allowlist vắng, `ANTHROPIC_*` và biến vô hiệu credential git có."""
        import os
        from unittest import mock
        from tests.conformance import _runner as R
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "x",
                                          "ANTHROPIC_API_KEY": "k", "NGHI_CANARY_TOKEN": "c"}):
            env = R.env_for(Path("/p"), Path("/p/w"), "S-1")
        self.assertNotIn("CLAUDECODE", env)
        self.assertNotIn("CLAUDE_CODE_ENTRYPOINT", env)
        self.assertNotIn("NGHI_CANARY_TOKEN", env)
        self.assertEqual(env["ANTHROPIC_API_KEY"], "k")
        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(env["AISEF_STORY_ID"], "S-1")

    def test_remote_gia_tra_401_va_ghi_authorization(self):
        import http.client
        from tests.conformance import _runner as R
        srv, url = R.start_fake_remote()
        try:
            for headers in ({}, {"Authorization": "Basic Zzp0"}):
                conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
                conn.request("GET", "/x.git/info/refs?service=git-receive-pack", headers=headers)
                resp = conn.getresponse()
                self.assertEqual(resp.status, 401)
                resp.read()
                conn.close()
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertTrue(url.startswith("http://127.0.0.1:"))
        self.assertEqual(srv.seen, [False, True])

    def test_moi_phep_thu_khong_co_ky_tu_ong_trong_bang(self):
        """`|` trong ô làm vỡ bảng markdown và regex đọc lại (`env | sort` ở C9
        từng làm cột claude thành "thiếu C9" dù ô ghi ✅)."""
        for pid, what, proves in C.PROBES:
            with self.subTest(probe=pid):
                self.assertNotIn("|", what + proves)

    def test_het_gio_la_ket_cuc_cua_phep_thu_khong_nem_xuyen_bang(self):
        """2026-09-06: OpenCode treo ở C4 → `TimeoutExpired` ném xuyên `probe_all`,
        cột OpenCode giữ số cũ, C9/C10 thành "—". Hết giờ phải thành một ô ✗
        có lý do, và bản ghi thô vẫn được giữ để tra."""
        import tempfile
        from unittest import mock
        from tests.conformance import _runner as R
        with tempfile.TemporaryDirectory() as d, mock.patch.object(R, "TIMEOUT", 1):
            proc = R._run(["sleep", "5"], Path(d), Path(d), "S-T", reviewer=False)
            self.assertEqual(proc.returncode, -1)
            self.assertEqual(proc.stderr, "quá 1s")
            self.assertIn("quá 1s", R._raw(Path(d), "S-T"))
