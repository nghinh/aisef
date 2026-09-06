"""Cổng cỡ story: P2-12 (trạng thái màn hình) + ADR-004 R5 (điểm tổng hợp).

Đo 2026-09-05 trên e9: 11 và 18 trạng thái đều chạm max_turns ở lượt đầu.
Hồi cứu B4 trên 23 story thật: điểm năm chiều tương quan Spearman 0,88 với
lượt developer lượt đầu; ngưỡng 16 tách 01-04/01-05 khỏi 01-03 và `par`.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control import complexity, preflight  # noqa: E402
from aisef.control.experience import Experience, Screen  # noqa: E402
from aisef.control.normalize import Story  # noqa: E402
from aisef.phases.plan import PHASES, build_prompt  # noqa: E402
from aisef.phases.story_split import GATE_MEMO  # noqa: E402


def exp(**states):
    return Experience(screens=[Screen(id=k, name=k, states=[f"s{i}" for i in range(n)])
                               for k, n in states.items()])


def story(screens, *, ac=1, scope=("src/a.ts",), sid="STORY-01-05", deps=()):
    return Story(id=sid, epic_id="EPIC-01", title="Sửa ghi chú",
                 acceptance_criteria=[f"Then xong {i}" for i in range(ac)],
                 write_scope=list(scope), depends_on=list(deps), screens=screens)


class TestComponents(unittest.TestCase):
    """Từng chiều của điểm đếm đúng thứ nó nói là đang đếm."""

    def test_screen_states_count_only_screens_this_story_builds_first(self):
        s4, s5 = story(["notes-list"], sid="STORY-01-04"), story(["notes-list", "note-editor"])
        owned = preflight.screen_owners([s4, s5])
        e = exp(**{"notes-list": 9, "note-editor": 4})
        self.assertEqual(complexity.screen_states(s4, experience=e, owned=owned),
                         [("notes-list", 9)])
        # 01-05 chạm màn của 01-04 (tính 1) và dựng note-editor (4).
        self.assertEqual(complexity.screen_states(s5, experience=e, owned=owned),
                         [("notes-list", 1), ("note-editor", 4)])

    def test_acceptance_criteria_component(self):
        sc = complexity.score_story(story([], ac=7))
        self.assertEqual(sc.get("acceptance").count, 7)
        self.assertEqual(sc.get("acceptance").points, 7 * complexity.ACCEPTANCE_WEIGHT)

    def test_write_scope_skips_lockfiles_and_manifests(self):
        s = story([], scope=["package.json", "package-lock.json", "pnpm-lock.yaml",
                             "yarn.lock", "bun.lockb", "src/main.tsx", "index.html"])
        self.assertEqual(complexity.scope_paths(s), ["src/main.tsx", "index.html"])
        self.assertEqual(complexity.score_story(s).get("write_scope").count, 2)

    def test_fan_in_counts_dependents(self):
        stories = [story([], sid="STORY-01-01"),
                   story([], sid="STORY-01-02", deps=["STORY-01-01"]),
                   story([], sid="STORY-01-03", deps=["STORY-01-01"])]
        self.assertEqual(complexity.fan_in_counts(stories), {"STORY-01-01": 2})
        sc = complexity.score_story(stories[0], fan_in=2)
        self.assertEqual(sc.get("fan_in").points, 2 * complexity.FAN_IN_WEIGHT)

    def test_verified_behaviours_touched_come_from_ledger_when_present(self):
        s = story([], scope=["src/store/notes.ts"])
        ledger = {"behaviors": {
            "AC-STORY-01-04-1": {"status": "verified", "files": ["src/store/notes.ts"]},
            "AC-STORY-01-04-2": {"status": "verified", "files": ["src/ui/other.tsx"]},
            "AC-STORY-01-04-3": {"status": "gap", "files": ["src/store/notes.ts"]},
        }}
        self.assertEqual(complexity.verified_touched(s, ledger), ["AC-STORY-01-04-1"])
        self.assertEqual(complexity.score_story(s, ledger=ledger).get("verified_touched").points,
                         complexity.VERIFIED_TOUCHED_WEIGHT)

    def test_ledger_records_name_the_owner_story_not_files(self):
        """Sổ R2 ghi `story` sở hữu; tệp tra qua write_scope của story ấy."""
        ledger = {"behaviors": {
            "AC-STORY-01-04-1": {"status": "VERIFIED", "story": "STORY-01-04"},
            "AC-STORY-01-04-2": {"status": "GAP", "story": "STORY-01-04"},
            "AC-STORY-01-05-1": {"status": "VERIFIED", "story": "STORY-01-05"},
        }}
        scopes = {"STORY-01-04": ["src/a.ts"], "STORY-01-05": ["src/b.ts"]}
        s = story([], scope=("src/a.ts",), sid="STORY-01-06")
        self.assertEqual(complexity.verified_touched(s, ledger, scopes), ["AC-STORY-01-04-1"])
        # Điểm đếm theo story láng giềng, không theo hành vi: 31 hành vi của 3
        # story không đắt gấp 31 lần một hành vi (đo e9 STORY-01-07, 2026-09-06).
        nhieu = {"behaviors": {f"AC-STORY-01-0{k}-{i}": {"status": "VERIFIED", "story": f"STORY-01-0{k}"}
                               for k in (4, 5, 6) for i in range(1, 8)}}
        nhieu["behaviors"].update({f"FR-{i}": {"status": "VERIFIED", "story": "STORY-01-04"} for i in range(10)})
        scopes3 = {f"STORY-01-0{k}": ["src/a.ts"] for k in (4, 5, 6)}
        with mock.patch.object(complexity, "read_scopes", return_value=scopes3):
            # 31 hành vi, trừ 7 của chính STORY-01-06 (story đang chấm) = 24, thuộc 2 láng giềng.
            self.assertEqual(len(complexity.verified_touched(s, nhieu, scopes3)), 24)
            comp = complexity.score_story(s, ledger=nhieu).get("verified_touched")
            self.assertEqual(comp.count, 2)
            self.assertEqual(comp.points, 2 * complexity.VERIFIED_TOUCHED_WEIGHT)
        # Chạy lại chính story sở hữu: hành vi của nó là mục tiêu, không phải thứ phải giữ.
        s5 = story([], scope=("src/b.ts",), sid="STORY-01-05")
        self.assertEqual(complexity.verified_touched(s5, ledger, scopes), [])
        # Không có chỉ mục → không tra được tệp → 0, không bịa.
        self.assertEqual(complexity.verified_touched(s, ledger), [])

    def test_reopened_do_chinh_story_van_phai_giu(self):
        """Lỗi 27 (par B3, 2026-09-06): lượt 1 của STORY-01-06 làm AC-01-04-1 REOPENED;
        lượt 2 phải còn thấy nó. REOPENED do story khác thì không phải việc của nó."""
        ledger = {"behaviors": {
            "AC-STORY-01-04-1": {"status": "reopened", "story": "STORY-01-04",
                                 "regressed_by": "STORY-01-06#1@abc1234"},
            "AC-STORY-01-04-2": {"status": "reopened", "story": "STORY-01-04",
                                 "regressed_by": "STORY-01-05#2"},
            "AC-STORY-01-04-3": {"status": "verified", "story": "STORY-01-04"},
        }}
        scopes = {"STORY-01-04": ["src/a.ts"]}
        s = story([], scope=("src/a.ts",), sid="STORY-01-06")
        self.assertEqual(complexity.verified_touched(s, ledger, scopes),
                         ["AC-STORY-01-04-1", "AC-STORY-01-04-3"])

    def test_scopes_come_from_stories_index(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "_bmad-output"; root.mkdir()
            (root / "stories.index.json").write_text(json.dumps({"stories": [
                {"id": "STORY-01-04", "write_scope": ["src/a.ts"]}]}), encoding="utf-8")
            (root / "ledger.json").write_text(json.dumps({"behaviors": {
                "AC-STORY-01-04-1": {"status": "VERIFIED", "story": "STORY-01-04"}}}), encoding="utf-8")
            s = story([], scope=("src/a.ts",), sid="STORY-01-06")
            self.assertEqual(complexity.read_scopes(d), {"STORY-01-04": ["src/a.ts"]})
            comp = complexity.score_story(s, project=Path(d)).get("verified_touched")
            self.assertEqual((comp.count, comp.points), (1, complexity.VERIFIED_TOUCHED_WEIGHT))

    def test_missing_ledger_scores_zero_not_a_guess(self):
        """Sổ hành vi là việc của R2 — thiếu thì chiều này = 0, không bịa."""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "_bmad-output").mkdir()
            sc = complexity.score_story(story([], scope=["src/a.ts"]), project=Path(d))
        self.assertEqual(sc.get("verified_touched").count, 0)

    def test_total_is_the_sum_and_explains_itself(self):
        s = story(["note-editor"], ac=7, scope=["src/a.ts", "src/b.ts"], deps=[])
        sc = complexity.score_story(s, experience=exp(**{"note-editor": 4}), fan_in=1)
        self.assertEqual(sc.total, 4 + 7 + 2 * 0.5 + 1)
        self.assertIn("screen_states 4×1", sc.explain())
        self.assertIn("write_scope 2×0.5", sc.explain())


class TestStorySize(unittest.TestCase):
    def setUp(self):
        self.cfg = Config({**DEFAULTS, "tools.test": "npm test", "tools.lint": "npx tsc"})

    def test_e9_note_editor_shape_is_blocked(self):
        s = story(["notes-list", "note-editor"], ac=7)
        with mock.patch.object(preflight, "_experience",
                               return_value=exp(**{"notes-list": 11, "note-editor": 7})):
            d = preflight.story_size_defect(s, project=Path("."), config=self.cfg)
            self.assertIsNotNone(d)
            self.assertEqual(d.kind, "story")
            self.assertTrue(d.blocks_run)
            self.assertIn("18 trạng thái màn hình", d.evidence)
            pf = preflight.check_story(s, project=Path("."), config=self.cfg)
        self.assertFalse(pf.executable)
        self.assertTrue(any(m.capability == "size" for m in pf.story_defects))

    def test_touching_a_screen_built_by_an_earlier_story_counts_one(self):
        """01-05 chạm notes-list (của 01-04) và dựng note-editor: không gánh cả hai."""
        s4 = story(["notes-list"], sid="STORY-01-04")
        s5 = story(["notes-list", "note-editor"])
        owned = preflight.screen_owners([s4, s5])
        self.assertEqual(owned, {"notes-list": "STORY-01-04", "note-editor": "STORY-01-05"})
        with mock.patch.object(preflight, "_experience",
                               return_value=exp(**{"notes-list": 11, "note-editor": 7})):
            self.assertIsNone(preflight.story_size_defect(
                s5, project=Path("."), config=self.cfg, owned=owned))
            d4 = preflight.story_size_defect(s4, project=Path("."), config=self.cfg, owned=owned)
        self.assertIsNotNone(d4)
        self.assertIn("11 trạng thái màn hình", d4.evidence)

    def test_done_story_is_not_measured(self):
        """Cổng cỡ story là phép kiểm trước execution: story đã xong thì bỏ qua."""
        with mock.patch.object(preflight, "_experience", return_value=exp(**{"notes-list": 11})):
            s4 = story(["notes-list"], sid="STORY-01-04")
            pf = preflight.check_story(s4, project=Path("."), config=self.cfg,
                                       done={"STORY-99-99"})
            self.assertTrue(any(m.capability == "size" for m in pf.story_defects))
            pf = preflight.check_story(s4, project=Path("."), config=self.cfg,
                                       done={"STORY-99-99", s4.id})
        self.assertFalse(any(m.capability == "size" for m in pf.story_defects))

    def test_size_defect_is_reported_once(self):
        """Cổng in cùng một lỗi hai lần thì người đọc tưởng có hai vấn đề."""
        s = story(["notes-list", "note-editor"], ac=7)
        with mock.patch.object(preflight, "_experience",
                               return_value=exp(**{"notes-list": 11, "note-editor": 7})):
            pf = preflight.check_story(s, project=Path("."), config=self.cfg)
        self.assertEqual([m.capability for m in pf.missing].count("size"), 1)

    def test_small_ui_story_passes(self):
        with mock.patch.object(preflight, "_experience", return_value=exp(**{"tags": 4})):
            self.assertIsNone(preflight.story_size_defect(
                story(["tags"]), project=Path("."), config=self.cfg))

    def test_no_experience_counts_one_state_per_screen(self):
        with mock.patch.object(preflight, "_experience", return_value=None):
            self.assertIsNone(preflight.story_size_defect(
                story(["a", "b", "c"]), project=Path("."), config=self.cfg))

    def test_screen_state_threshold_is_config(self):
        with mock.patch.object(preflight, "_experience", return_value=exp(**{"tags": 4})):
            cfg = Config({**DEFAULTS, "story.max_screen_states": 3})
            self.assertIsNotNone(preflight.story_size_defect(
                story(["tags"]), project=Path("."), config=cfg))

    def test_story_with_no_screens_can_still_be_too_big(self):
        """e9 01-01: 0 màn hình, 9 đường dẫn, 7 tiêu chí — 61 lượt lượt đầu.
        Chiều màn hình một mình không thấy nó; điểm tổng hợp thì có."""
        s = story([], ac=12, scope=[f"src/f{i}.ts" for i in range(12)], sid="STORY-01-01")
        with mock.patch.object(preflight, "_experience", return_value=None):
            d = preflight.story_size_defect(s, project=Path("."), config=self.cfg, fan_in=2)
        self.assertIsNotNone(d)
        self.assertIn("story.max_complexity", d.evidence)
        self.assertIn("acceptance 12×1", d.evidence)

    def test_complexity_threshold_is_config(self):
        s = story([], ac=12, scope=[f"src/f{i}.ts" for i in range(12)])
        cfg = Config({**DEFAULTS, "story.max_complexity": 100.0})
        with mock.patch.object(preflight, "_experience", return_value=None):
            self.assertIsNone(preflight.story_size_defect(
                s, project=Path("."), config=cfg, fan_in=2))

    def test_calibrated_threshold_separates_e9_0104_0105_from_0103_and_par(self):
        """B4: cùng ngưỡng mặc định, hai story đắt bị chặn, phần còn lại không."""
        e = exp(**{"notes-list": 9, "note-editor": 4})
        s4 = story(["notes-list"], ac=7, scope=[f"src/f{i}.ts" for i in range(13)],
                   sid="STORY-01-04")
        s5 = story(["notes-list", "note-editor"], ac=7,
                   scope=[f"src/g{i}.ts" for i in range(10)], sid="STORY-01-05")
        s3 = story([], ac=4, scope=["bench/seed.ts", "bench/bench.ts", "bench/README.md"],
                   sid="STORY-01-03")
        par = story([], ac=2, scope=["src/slugify.js", "src/slugify.test.js"],
                    sid="STORY-01-01")
        owned = preflight.screen_owners([s4, s5])
        with mock.patch.object(preflight, "_experience", return_value=e):
            chan = {s.id: preflight.story_size_defect(
                s, project=Path("."), config=self.cfg, owned=owned, fan_in=1) is not None
                for s in (s4, s5, s3, par)}
        self.assertEqual(chan, {"STORY-01-04": True, "STORY-01-05": True,
                                "STORY-01-03": False, "STORY-01-01": False})


class TestSplitSuggestion(unittest.TestCase):
    """Gợi ý chẻ phải **tất định** — người lập kế hoạch đọc là làm được."""

    def test_many_screens_split_by_screen(self):
        s = story(["notes-list", "note-editor"])
        e = exp(**{"notes-list": 9, "note-editor": 4})
        out = complexity.split_suggestion(s, complexity.score_story(s, experience=e),
                                          experience=e)
        self.assertIn("mỗi màn một story", out)
        self.assertIn("`notes-list` (9 trạng thái)", out)
        self.assertIn("`note-editor` (4 trạng thái)", out)

    def test_one_screen_splits_primary_states_from_edge_states(self):
        e = Experience(screens=[Screen(id="notes-list", name="notes-list", states=[
            "Mở nguội", "Kho rỗng", "Đang offline", "Focus"])])
        s = story(["notes-list"])
        out = complexity.split_suggestion(s, complexity.score_story(s, experience=e),
                                          experience=e)
        self.assertIn("trạng thái chính (Mở nguội)", out)
        self.assertIn("Kho rỗng, Đang offline, Focus", out)

    def test_no_screen_splits_by_acceptance_clusters(self):
        s = story([], ac=7, scope=["src/a.ts", "src/b.ts"])
        out = complexity.split_suggestion(s, complexity.score_story(s))
        self.assertIn("TCCN 1–4", out)
        self.assertIn("TCCN 5–7", out)

    def test_suggestion_reaches_the_need_and_is_stable(self):
        s = story(["notes-list", "note-editor"], ac=7)
        e = exp(**{"notes-list": 9, "note-editor": 4})
        with mock.patch.object(preflight, "_experience", return_value=e):
            a = preflight.story_size_defect(s, project=Path("."))
            b = preflight.story_size_defect(s, project=Path("."))
        self.assertIn("mỗi màn một story", a.remedy)
        self.assertIn("mỗi màn một story", a.line())
        self.assertEqual(a.line(), b.line(), "cùng dữ liệu phải cho cùng câu chữ")


class TestCalibrationTable(unittest.TestCase):
    """Bảng hiệu chuẩn tự ghi: điểm dự đoán ↔ lượt developer thật."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "_bmad-output"
        self.root.mkdir(parents=True)
        self.addCleanup(self.tmp.cleanup)

    def evidence(self, story_id, runs):
        from aisef.harness.observe import AGENT_RUN, Event, EvidenceStore

        store = EvidenceStore(self.root)
        for name, turns, err in runs:
            store.record(story_id, Event(kind=AGENT_RUN, name=name, ok=not err,
                                         detail={"turns": turns, "error": err}))

    def test_observed_reads_first_developer_attempt_only(self):
        self.evidence("STORY-01-05", [
            ("STORY-01-05#1", 91, "max_turns"),
            ("STORY-01-05-review", 69, ""),      # rà soát không phải lượt developer
            ("STORY-01-05#2", 49, ""),
            ("STORY-01-05#1", 72, ""),           # lần chạy lại sau — không ghi đè
        ])
        got = complexity.observed(self.root, "STORY-01-05", max_turns=90)
        self.assertEqual(got["first_turns"], 91)
        self.assertEqual(got["attempts"], 2)
        self.assertTrue(got["max_turns_hit"])

    def test_record_then_load_round_trip(self):
        self.evidence("STORY-01-04", [("STORY-01-04#1", 20, "")])
        s = story(["notes-list"], ac=7, sid="STORY-01-04")
        sc = complexity.score_story(s, experience=exp(**{"notes-list": 9}))
        row = complexity.record(self.root, s, score=sc)
        self.assertEqual(row["total"], sc.total)
        self.assertEqual(row["components"]["screen_states"]["count"], 9)
        self.assertEqual(row["first_turns"], 20)
        rows = complexity.load_calibration(self.root)
        self.assertEqual(rows["STORY-01-04"]["total"], sc.total)
        self.assertEqual(rows["STORY-01-04"]["threshold"], DEFAULTS["story.max_complexity"])

    def test_no_calibration_file_is_not_an_error(self):
        self.assertEqual(complexity.load_calibration(self.root), {})
        self.assertEqual(complexity.divergence({}), [])

    def test_divergence_flags_threshold_too_high(self):
        rows = {f"S{i}": {"total": 5.0, "threshold": 16.0, "first_turns": 40,
                          "attempts": 3, "max_turns": 40, "max_turns_hit": True}
                for i in range(2)}
        out = complexity.divergence(rows)
        self.assertEqual(len(out), 1)
        self.assertIn("quá cao", out[0])

    def test_divergence_flags_threshold_too_low(self):
        rows = {f"S{i}": {"total": 20.0, "threshold": 16.0, "first_turns": 12,
                          "attempts": 1, "max_turns": 40, "max_turns_hit": False}
                for i in range(2)}
        out = complexity.divergence(rows)
        self.assertEqual(len(out), 1)
        self.assertIn("quá thấp", out[0])

    def test_one_diverging_story_is_not_enough(self):
        rows = {"S0": {"total": 5.0, "threshold": 16.0, "first_turns": 40,
                       "attempts": 3, "max_turns": 40, "max_turns_hit": True}}
        self.assertEqual(complexity.divergence(rows), [])

    def test_doctor_reports_the_divergence(self):
        import argparse

        from aisef.cli import doctor

        (self.root / complexity.CALIBRATION_FILE).write_text(json.dumps({
            "version": 1,
            "stories": {f"STORY-01-0{i}": {
                "total": 5.0, "threshold": 16.0, "first_turns": 40, "attempts": 3,
                "max_turns": 40, "max_turns_hit": True} for i in (1, 2)},
        }), encoding="utf-8")
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            doctor.cmd_doctor(argparse.Namespace(project=str(self.root.parent)))
        self.assertIn("ngưỡng cỡ story khớp dữ liệu", buf.getvalue())
        self.assertIn("quá cao", buf.getvalue())

    def test_spearman_matches_a_hand_computed_case(self):
        self.assertAlmostEqual(complexity.spearman([1, 2, 3], [10, 20, 30]), 1.0)
        self.assertAlmostEqual(complexity.spearman([1, 2, 3], [30, 20, 10]), -1.0)
        # hạng đồng không được làm nổ phép tính
        self.assertAlmostEqual(complexity.spearman([1, 1, 3], [10, 20, 30]), 0.866, places=3)


class TestGateMemo(unittest.TestCase):
    def test_epics_prompt_carries_last_gate_errors(self):
        epics = next(p for p in PHASES if p.id == "epics")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "_bmad-output"
            root.mkdir()
            self.assertNotIn("KHÔNG ĐẠT", build_prompt(epics, project=Path(d)))
            (root / GATE_MEMO).write_text(json.dumps(
                {"errors": ["STORY-01-05 quá lớn: 18 trạng thái"], "warnings": []}),
                encoding="utf-8")
            text = build_prompt(epics, project=Path(d))
            self.assertIn("KHÔNG ĐẠT", text)
            self.assertIn("18 trạng thái", text)


if __name__ == "__main__":
    unittest.main()
