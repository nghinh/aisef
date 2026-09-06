"""Test control/complexity.py — story sizing, calibration, Spearman."""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from aisef.control.complexity import (
    ACCEPTANCE_WEIGHT,
    Component,
    FAN_IN_WEIGHT,
    SCREEN_STATE_WEIGHT,
    Score,
    VERIFIED_TOUCHED_WEIGHT,
    WRITE_SCOPE_WEIGHT,
    divergence,
    fan_in_counts,
    load_calibration,
    record,
    scope_paths,
    score_story,
    screen_states,
    spearman,
    split_suggestion,
    verified_touched,
)
from aisef.control.normalize import Story


def _story(
    sid="S-01",
    screens=(),
    ac=(),
    scope=(),
    depends_on=(),
) -> Story:
    return Story(
        id=sid,
        epic_id="EPIC-01",
        title="test",
        depends_on=list(depends_on),
        write_scope=list(scope),
        acceptance_criteria=list(ac),
        screens=list(screens),
    )


class TestComponent(unittest.TestCase):

    def test_points(self):
        c = Component("x", 3, 0.5)
        self.assertAlmostEqual(c.points, 1.5)

    def test_line_with_evidence(self):
        c = Component("x", 2, 1.0, evidence="foo")
        self.assertIn("foo", c.line())

    def test_line_without_evidence(self):
        c = Component("x", 0, 1.0)
        self.assertNotIn("(", c.line())


class TestScore(unittest.TestCase):

    def test_total(self):
        s = Score("S-01", (Component("a", 2, 1.0), Component("b", 3, 0.5)))
        self.assertAlmostEqual(s.total, 3.5)

    def test_get_existing(self):
        s = Score("S-01", (Component("a", 2, 1.0),))
        self.assertEqual(s.get("a").count, 2)

    def test_get_missing(self):
        s = Score("S-01", ())
        self.assertEqual(s.get("no").count, 0)

    def test_as_dict(self):
        s = Score("S-01", (Component("a", 1, 1.0),))
        d = s.as_dict()
        self.assertEqual(d["story_id"], "S-01")
        self.assertIn("a", d["components"])

    def test_explain(self):
        s = Score("S-01", (Component("a", 2, 1.0), Component("b", 0, 1.0)))
        text = s.explain()
        self.assertIn("a", text)
        self.assertNotIn("b", text)


class TestScopePaths(unittest.TestCase):

    def test_filters_lockfile(self):
        story = _story(scope=["src/app.py", "package-lock.json"])
        paths = scope_paths(story)
        self.assertEqual(paths, ["src/app.py"])

    def test_filters_manifest(self):
        story = _story(scope=["src/app.py", "package.json"])
        paths = scope_paths(story)
        self.assertEqual(paths, ["src/app.py"])

    def test_empty_scope(self):
        self.assertEqual(scope_paths(_story(scope=[])), [])


class TestFanInCounts(unittest.TestCase):

    def test_basic(self):
        stories = [_story("A", depends_on=["B"]), _story("C", depends_on=["B", "A"])]
        counts = fan_in_counts(stories)
        self.assertEqual(counts["B"], 2)
        self.assertEqual(counts["A"], 1)

    def test_no_deps(self):
        stories = [_story("A"), _story("B")]
        self.assertEqual(fan_in_counts(stories), {})


class TestScreenStates(unittest.TestCase):

    def test_no_screens(self):
        self.assertEqual(screen_states(_story()), [])

    def test_screens_no_experience(self):
        story = _story(screens=["scr-1", "scr-2"])
        result = screen_states(story)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(n == 1 for _, n in result))


class TestVerifiedTouched(unittest.TestCase):

    def test_none_ledger(self):
        self.assertEqual(verified_touched(_story(scope=["src/a.py"]), None), [])

    def test_empty_ledger(self):
        self.assertEqual(verified_touched(_story(scope=["src/a.py"]), {}), [])

    def test_own_story_excluded(self):
        ledger = {"behaviors": {"AC-01": {"status": "VERIFIED", "story": "S-01",
                                          "files": ["src/a.py"]}}}
        self.assertEqual(verified_touched(_story("S-01", scope=["src/a.py"]), ledger), [])

    def test_other_story_included(self):
        ledger = {"behaviors": {"AC-02": {"status": "VERIFIED", "story": "S-02",
                                          "files": ["src/a.py"]}}}
        result = verified_touched(_story("S-01", scope=["src/a.py"]), ledger)
        self.assertEqual(result, ["AC-02"])

    def test_reopened_by_self_included(self):
        ledger = {"behaviors": {"AC-03": {"status": "REOPENED", "story": "S-02",
                                          "regressed_by": "S-01#2",
                                          "files": ["src/a.py"]}}}
        result = verified_touched(_story("S-01", scope=["src/a.py"]), ledger)
        self.assertEqual(result, ["AC-03"])

    def test_no_scope_overlap(self):
        ledger = {"behaviors": {"AC-02": {"status": "VERIFIED", "story": "S-02",
                                          "files": ["src/b.py"]}}}
        self.assertEqual(verified_touched(_story("S-01", scope=["src/a.py"]), ledger), [])


class TestScoreStory(unittest.TestCase):

    def test_basic_score(self):
        story = _story(ac=["AC-1", "AC-2"], scope=["src/a.py", "src/b.py"])
        score = score_story(story)
        self.assertEqual(score.get("acceptance").count, 2)
        self.assertEqual(score.get("write_scope").count, 2)
        expected = 2 * ACCEPTANCE_WEIGHT + 2 * WRITE_SCOPE_WEIGHT
        self.assertAlmostEqual(score.total, expected)

    def test_fan_in(self):
        story = _story(ac=["AC-1"])
        score = score_story(story, fan_in=3)
        self.assertEqual(score.get("fan_in").count, 3)

    def test_verified_touched_weight_is_zero(self):
        self.assertEqual(VERIFIED_TOUCHED_WEIGHT, 0.0)


class TestSpearman(unittest.TestCase):

    def test_perfect_positive(self):
        self.assertAlmostEqual(spearman([1, 2, 3], [10, 20, 30]), 1.0)

    def test_perfect_negative(self):
        self.assertAlmostEqual(spearman([1, 2, 3], [30, 20, 10]), -1.0)

    def test_too_few(self):
        self.assertTrue(math.isnan(spearman([1], [2])))

    def test_mismatched_length(self):
        self.assertTrue(math.isnan(spearman([1, 2], [3])))

    def test_ties(self):
        r = spearman([1, 1, 3], [10, 20, 30])
        self.assertFalse(math.isnan(r))


class TestDivergence(unittest.TestCase):

    def test_no_divergence(self):
        rows = {"S-01": {"total": 10, "threshold": 16, "first_turns": 30,
                         "max_turns_hit": False, "max_turns": 80, "attempts": 1}}
        self.assertEqual(divergence(rows), [])

    def test_too_high(self):
        rows = {
            f"S-{i:02d}": {"total": 10, "threshold": 16, "max_turns_hit": True,
                            "max_turns": 80, "first_turns": 80, "attempts": 1}
            for i in range(3)
        }
        msgs = divergence(rows)
        self.assertTrue(any("quá cao" in m for m in msgs))

    def test_too_low(self):
        rows = {
            f"S-{i:02d}": {"total": 20, "threshold": 16, "max_turns_hit": False,
                            "max_turns": 80, "first_turns": 10, "attempts": 1}
            for i in range(3)
        }
        msgs = divergence(rows)
        self.assertTrue(any("quá thấp" in m for m in msgs))


class TestSplitSuggestion(unittest.TestCase):

    def test_by_acceptance_criteria(self):
        story = _story(ac=["AC-1", "AC-2", "AC-3", "AC-4"], scope=["src/a.py"])
        score = score_story(story)
        suggestion = split_suggestion(story, score)
        self.assertIn("tiêu chí", suggestion)

    def test_no_criteria(self):
        story = _story(ac=[], scope=["src/a.py"])
        score = score_story(story)
        suggestion = split_suggestion(story, score)
        self.assertIn("phạm vi ghi", suggestion)


class TestCalibration(unittest.TestCase):

    def test_load_missing(self):
        self.assertEqual(load_calibration("/nonexistent"), {})

    def test_load_corrupt(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "complexity.json"
            p.write_text("not json")
            self.assertEqual(load_calibration(d), {})

    def test_record_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            ar = Path(d) / "_bmad-output"
            ar.mkdir()
            story = _story(ac=["AC-1"], scope=["src/a.py"])
            score = score_story(story)
            row = record(ar, story, score=score)
            self.assertEqual(row["story_id"], "S-01")
            loaded = load_calibration(ar)
            self.assertIn("S-01", loaded)


if __name__ == "__main__":
    unittest.main()
