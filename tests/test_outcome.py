"""Một kiểu kết cục, một bảng ký hiệu, ba nơi hiển thị (G7)."""

from __future__ import annotations

import unittest

from aisdlc.control.outcome import MARK, Check, Outcome
from aisdlc.control.gate import StoryGate
from aisdlc.phases.qa import KINDS, KindResult


class TestBangKyHieu(unittest.TestCase):
    def test_unconfigured_and_unrunnable_never_look_like_passed(self):
        for o in Outcome:
            if o.must_be_named:
                self.assertNotEqual(MARK[o], MARK[Outcome.PASSED], o)
        self.assertEqual(len(set(MARK.values())), len(Outcome))

    def test_three_questions(self):
        self.assertEqual({o for o in Outcome if o.blocks}, {Outcome.FAILED, Outcome.UNRUNNABLE})
        self.assertEqual({o for o in Outcome if o.counts_as_done},
                         {Outcome.PASSED, Outcome.WAIVED, Outcome.NOT_APPLICABLE})
        self.assertEqual({o for o in Outcome if o.must_be_named},
                         {Outcome.UNCONFIGURED, Outcome.UNRUNNABLE})


class TestCheck(unittest.TestCase):
    def test_bool_is_passed_or_failed_only(self):
        self.assertIs(Check("lint", True).outcome, Outcome.PASSED)
        self.assertIs(Check("lint", False).outcome, Outcome.FAILED)

    def test_every_non_passed_line_carries_a_reason(self):
        for o in Outcome:
            if o is Outcome.PASSED:
                continue
            line = Check("k", o).line()
            self.assertIn(" — ", line, o)
            self.assertTrue(line.startswith(f"  {MARK[o]} k"), line)

    def test_unconfigured_does_not_block_but_is_not_done(self):
        c = Check("e2e", Outcome.UNCONFIGURED)
        self.assertTrue(c.passed)             # không chặn cổng story
        self.assertFalse(c.outcome.counts_as_done)
        self.assertEqual(c.as_dict()["outcome"], "unconfigured")

    def test_story_gate_blocks_only_on_blocking_outcomes(self):
        g = StoryGate("S-1", checks=[Check("a", Outcome.UNCONFIGURED), Check("b", Outcome.NOT_APPLICABLE)])
        self.assertTrue(g.passed)
        g.checks.append(Check("c", Outcome.UNRUNNABLE, "npm chưa cài"))
        self.assertFalse(g.passed)
        self.assertEqual([c.name for c in g.failures], ["c"])


class TestKindResultCungBang(unittest.TestCase):
    """`qa` hiển thị cùng ký hiệu với `gate`/`deploy` — không tự vẽ bảng riêng."""

    def test_marks_match(self):
        unit = KINDS["unit"]
        self.assertTrue(KindResult(unit, skipped="chưa khai lệnh").line().startswith(f"  {MARK[Outcome.UNCONFIGURED]}"))
        self.assertTrue(KindResult(unit, unrunnable="npm ci").line().startswith(f"  {MARK[Outcome.UNRUNNABLE]}"))
        self.assertTrue(KindResult(unit, ran=True, ok=False).line().startswith(f"  {MARK[Outcome.FAILED]}"))
        self.assertTrue(KindResult(unit, ran=True, ok=True).line().startswith(f"  {MARK[Outcome.PASSED]}"))
        self.assertTrue(KindResult(unit, skipped="x").line(waived=True).startswith(f"  {MARK[Outcome.WAIVED]}"))

    def test_outcome_property(self):
        unit = KINDS["unit"]
        self.assertIs(KindResult(unit, ran=True, ok=False).outcome, Outcome.FAILED)
        self.assertIs(KindResult(unit, unrunnable="x").outcome, Outcome.UNRUNNABLE)
