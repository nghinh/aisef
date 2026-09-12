"""Replay cổng trên bằng chứng đã ghi (ADR-005 V4).

`gate:input` giữ 13 kwargs của `gate.evaluate`; replay cắt bằng chứng ở seq
ấy, chấm lại bằng luật **hiện tại**, so mục chặn với `gate:verdict` đã ghi.
Không gọi model: lời reviewer/security là thứ đã nằm trong bản ghi. Lượt
không có đầu vào thì nói không replay được — không đoán.
"""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.cli import EXIT_NOT_READY, EXIT_OK, EXIT_USAGE, main  # noqa: E402
from aisef.control import replay as R  # noqa: E402
from aisef.control.gate import StoryGate, evaluate  # noqa: E402
from aisef.control.outcome import Check, Outcome  # noqa: E402
from aisef.harness.observe import NOTE, Event, EvidenceStore  # noqa: E402

SID = "STORY-01-01"
SHA = "0123456789abcdef0123456789abcdef01234567"


class ReplayCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        (self.project / "docs").mkdir()
        (self.project / "docs" / "requirements.md").write_text("# yêu cầu\n", encoding="utf-8")
        self.root = self.project / "_bmad-output"
        self.store = EvidenceStore(self.root, candidate=SHA)

    def tearDown(self):
        self._tmp.cleanup()

    def kwargs(self, **over):
        kw = dict(changed=["src/a.py"], write_scope=["src"], screens=[], contract=[],
                  review_blocking=[], security=None, block_severities=["critical", "high"],
                  guard_expected=False, acceptance=0, coverage_min=None, added_tests=[],
                  candidate=SHA, preservation=[])
        kw.update(over)
        return kw

    def luot(self, attempt=1, *, lint_ok=True, **over):
        """Một lượt như `verify_candidate` ghi: phép kiểm → gate:input → verdict."""
        self.store.file_change(SID, "src/a.py")
        self.store.tool_run(SID, "test", ok=True)
        self.store.tool_run(SID, "lint", ok=lint_ok, detail={"tail": "E501"})
        kw = self.kwargs(**over)
        self.store.record(SID, Event(kind=NOTE, name="gate:input", detail={**kw, "attempt": attempt}))
        gate = evaluate(SID, self.store.read(SID), **R.kwargs_from({**kw, "attempt": attempt}))
        self.store.record(SID, Event(kind=NOTE, name="gate:verdict", ok=gate.passed,
                                     detail={"failures": [c.name for c in gate.failures], "attempt": attempt}))
        return gate

    def evidence(self):
        return EvidenceStore(self.root).read(SID)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--project", str(self.project), *args])
        return code, out.getvalue(), err.getvalue()


class TestReplayDungVerdictCu(ReplayCase):
    def test_cung_luat_thi_cung_muc_chan(self):
        goc = self.luot(1, lint_ok=False)
        self.assertFalse(goc.passed)
        [r] = R.replay(self.evidence())
        self.assertEqual(r.attempt, 1)
        self.assertEqual(r.candidate, SHA)
        self.assertEqual(r.recorded, ["lint"])
        self.assertEqual(r.now, ["lint"])
        self.assertEqual(r.changed(), [])
        self.assertIn("none — same blocking checks", r.summary())

    def test_luot_dat_cung_replay_dat(self):
        self.luot(1)
        [r] = R.replay(self.evidence())
        self.assertEqual(r.recorded, [])
        self.assertTrue(r.gate.passed, r.gate.summary())

    def test_cat_bang_chung_o_seq_dau_vao_khong_thay_luot_sau(self):
        """Lượt 2 chạy lint xanh; replay lượt 1 vẫn phải thấy lint đỏ như lúc chấm."""
        self.luot(1, lint_ok=False)
        self.luot(2)
        r1, r2 = R.replay(self.evidence())
        self.assertEqual(r1.now, ["lint"])
        self.assertEqual(r2.now, [])
        self.assertEqual([r.attempt for r in R.replay(self.evidence(), attempt=2)], [2])

    def test_security_dung_lai_tu_dong_da_ghi(self):
        self.luot(1, security={"findings": ["[high] SQL nối chuỗi ở src/a.py:3"], "error": ""})
        [r] = R.replay(self.evidence())
        self.assertIn("security", r.now)
        self.assertEqual(r.recorded, ["security"])


class TestReplayThayLuatDoi(ReplayCase):
    def test_sua_luat_thi_diff_neu_dung_muc(self):
        """Giả lập một luật cổng đổi: mục `rà soát` nay chặn — replay phải chỉ đúng nó,
        và chỉ nó, là 'nay ✗ (trước qua)'."""
        self.luot(1)

        def luat_moi(story_id, evidence, **kw):
            g = evaluate(story_id, evidence, **kw)
            g.checks = [Check("review", False, "luật mới") if c.name == "review" else c
                        for c in g.checks]
            return g

        with mock.patch.object(R, "evaluate", luat_moi):
            [r] = R.replay(self.evidence())
        self.assertEqual(r.changed(), ["review"])
        self.assertEqual(r.recorded, [])
        self.assertIn("review", r.now)
        rows = {name: (truoc, nay) for name, truoc, nay in r.rows()}
        self.assertEqual(rows["review"], ("·", Outcome.FAILED.mark))
        self.assertIn("≠", r.summary())

    def test_luat_noi_ra_thi_diff_chi_muc_het_chan(self):
        self.luot(1, lint_ok=False)

        def luat_noi(story_id, evidence, **kw):
            g = evaluate(story_id, evidence, **kw)
            g.checks = [Check("lint", True) if c.name == "lint" else c for c in g.checks]
            return g

        with mock.patch.object(R, "evaluate", luat_noi):
            [r] = R.replay(self.evidence())
        self.assertEqual(r.changed(), ["lint"])
        self.assertEqual(r.rows()[[n for n, _, _ in r.rows()].index("lint")], ("lint", "✗", Outcome.PASSED.mark))


class TestLuotKhongCoDauVao(ReplayCase):
    def test_verdict_khong_co_input_la_khong_replay_duoc(self):
        """Bằng chứng trước V4: chỉ có `gate:verdict` — nêu số lượt, không đoán kwargs."""
        self.store.tool_run(SID, "test", ok=True)
        self.store.record(SID, Event(kind=NOTE, name="gate:verdict", ok=False,
                                     detail={"failures": ["lint"], "attempt": 1}))
        self.assertEqual(R.replay(self.evidence()), [])
        self.assertEqual(R.unreplayable(self.evidence()), [1])

    def test_input_co_verdict_thi_khong_tinh_la_thieu(self):
        self.luot(1)
        self.assertEqual(R.unreplayable(self.evidence()), [])


class TestLenhGateReplay(ReplayCase):
    def test_in_bang_va_noi_khong_goi_model(self):
        self.luot(1, lint_ok=False)
        code, out, _ = self.run_cli("gate", "--replay", SID)
        self.assertEqual(code, EXIT_OK, out)
        self.assertIn("no model calls", out)
        self.assertIn("lint", out)
        self.assertIn("replayed 1/1 attempts", out)

    def test_luot_truoc_v4_thi_noi_khong_replay_duoc(self):
        self.store.record(SID, Event(kind=NOTE, name="gate:verdict", ok=True,
                                     detail={"failures": [], "attempt": 1}))
        code, out, _ = self.run_cli("gate", "--replay", SID)
        self.assertEqual(code, EXIT_NOT_READY)
        self.assertIn("not replayable", out)
        self.assertIn("gate:input", out)
        self.assertIn("replayed 0/1 attempts", out)

    def test_all_gom_moi_story(self):
        self.luot(1)
        EvidenceStore(self.root, candidate=SHA).record("STORY-01-02", Event(
            kind=NOTE, name="gate:verdict", ok=True, detail={"failures": [], "attempt": 1}))
        code, out, _ = self.run_cli("gate", "--replay", "--all")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("STORY-01-01 attempt 1", out)
        self.assertIn("STORY-01-02 attempt 1: not replayable", out)
        self.assertIn("replayed 1/2 attempts", out)

    def test_thieu_story_va_thieu_replay_la_loi_dung(self):
        self.assertEqual(self.run_cli("gate", "--replay")[0], EXIT_USAGE)
        self.assertEqual(self.run_cli("gate", SID)[0], EXIT_USAGE)


class TestPairsByPosition(unittest.TestCase):
    """Bug 47 + 42. ``_pairs`` used to compare ``inp.seq < v.seq``
    to match ``gate:input`` with the next ``gate:verdict``.  When a
    long event wrote past the read-tail window, ``seq`` reset, so an
    earlier verdict looked like a later one.  The fixture is built so
    the seq ordering is *inverted*: the older verdict carries a
    higher seq than the input.  Pairing must still find the right
    verdict by position in the time-sorted event list."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pairs_selects_verdict_by_position_not_seq(self):
        path = EvidenceStore(self.root).path("S")
        path.parent.mkdir(parents=True, exist_ok=True)
        events = [
            # input, attempt 1, with newer higher seq because a buggy
            # build reset the counter before this write.
            {"kind": "note", "name": "gate:input", "seq": 200, "at": 100.0,
             "detail": {"attempt": 1, "candidate": "c"}},
            # verdict for attempt 1, written earlier by an older build.
            {"kind": "note", "name": "gate:verdict", "seq": 10, "at": 200.0,
             "detail": {"attempt": 1}},
            # input, attempt 2.
            {"kind": "note", "name": "gate:input", "seq": 300, "at": 300.0,
             "detail": {"attempt": 2, "candidate": "c"}},
            # verdict for attempt 2.
            {"kind": "note", "name": "gate:verdict", "seq": 12, "at": 400.0,
             "detail": {"attempt": 2}},
        ]
        path.write_text(
            "\n".join(__import__("json").dumps(e) for e in events) + "\n",
            encoding="utf-8")
        ev = EvidenceStore(self.root).read("S")
        pairs = R._pairs(ev)
        self.assertEqual(len(pairs), 2)
        # First input pairs with the verdict at at=200 (the only one in
        # its time window — input at 100, next input at 300).
        first_inp, first_v = pairs[0]
        self.assertEqual(first_inp.detail["attempt"], 1)
        self.assertIsNotNone(first_v)
        self.assertEqual(first_v.detail["attempt"], 1)
        self.assertEqual(first_v.at, 200.0,
                          "the verdict with seq=10 (old) at at=200.0 is correct;"
                          " a seq-based search would match a later verdict with seq=12")


if __name__ == "__main__":
    unittest.main()
