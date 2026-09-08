"""Kiểm chứng cổng máy — phải CHẶN THẬT khi tài liệu có vấn đề."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.control.machine_gate import check_all, check_prd, check_stories  # noqa: E402
from aisef.control.normalize import PRD, OpenQuestion, Requirement, parse_prd_file  # noqa: E402
from aisef.control.scheduler import Story  # noqa: E402

PRD_FIXTURE = ROOT / "tests" / "fixtures" / "bmad" / "prd.md"


def req(rid: str, *, criteria=("kiểm được",), kind="functional", title="Tiêu đề") -> Requirement:
    return Requirement(id=rid, kind=kind, title=title, acceptance_criteria=list(criteria))


def story(sid: str, *, deps=(), scope=("src/x.py",)) -> Story:
    return Story(id=sid, epic_id="E1", depends_on=tuple(deps), write_scope=tuple(scope))


class TestPrdGateOnRealDocument(unittest.TestCase):
    def test_real_prd_passes(self):
        r = check_prd(parse_prd_file(PRD_FIXTURE))
        self.assertTrue(r.passed, r.summary())

    def test_real_prd_surfaces_open_questions_as_warnings(self):
        r = check_prd(parse_prd_file(PRD_FIXTURE))
        self.assertTrue(any("open questions" in w for w in r.warnings))
        self.assertTrue(any("blocked by open questions" in w for w in r.warnings))


class TestPrdGate(unittest.TestCase):
    def test_empty_prd_fails(self):
        self.assertFalse(check_prd(PRD()).passed)

    def test_untestable_requirement_blocks(self):
        prd = PRD(requirements=[req("FR-1", criteria=())])
        r = check_prd(prd)
        self.assertFalse(r.passed)
        self.assertIn("FR-1", r.errors[0])

    def test_missing_title_blocks(self):
        prd = PRD(requirements=[req("FR-1", title="  ")])
        self.assertFalse(check_prd(prd).passed)

    def test_open_questions_warn_but_do_not_block(self):
        prd = PRD(
            requirements=[req("FR-1")],
            open_questions=[OpenQuestion(id="OQ-1", text="?", blocks=["FR-9"])],
        )
        r = check_prd(prd)
        self.assertTrue(r.passed)
        self.assertTrue(r.warnings)

    def test_missing_nfr_is_only_a_warning(self):
        r = check_prd(PRD(requirements=[req("FR-1")]))
        self.assertTrue(r.passed)
        self.assertTrue(any("non-functional" in w for w in r.warnings))


class TestStoryGate(unittest.TestCase):
    def test_empty_fails(self):
        self.assertFalse(check_stories([]).passed)

    def test_valid_stories_pass(self):
        stories = [story("S-1", scope=("src/a.py",)), story("S-2", scope=("src/b.py",))]
        self.assertTrue(check_stories(stories).passed)

    def test_missing_write_scope_blocks(self):
        r = check_stories([story("S-1", scope=())])
        self.assertFalse(r.passed)
        self.assertIn("write_scope", r.errors[0])

    def test_duplicate_id_blocks(self):
        r = check_stories([story("S-1"), story("S-1", scope=("src/b.py",))])
        self.assertFalse(r.passed)
        self.assertTrue(any("duplicate" in e for e in r.errors))

    def test_dependency_cycle_blocks(self):
        stories = [
            story("S-1", deps=("S-2",), scope=("src/a.py",)),
            story("S-2", deps=("S-1",), scope=("src/b.py",)),
        ]
        r = check_stories(stories)
        self.assertFalse(r.passed)
        self.assertTrue(any("cycle" in e for e in r.errors))

    def test_unknown_dependency_blocks(self):
        r = check_stories([story("S-1", deps=("KHONG-CO",))])
        self.assertFalse(r.passed)

    def test_too_many_acceptance_criteria_blocks(self):
        """Story quá lớn sẽ tràn ngữ cảnh trong một phiên."""
        r = check_stories([story("S-1")], story_ac_count={"S-1": 20})
        self.assertFalse(r.passed)
        self.assertTrue(any("split" in e for e in r.errors))

    def test_ac_limit_respects_config(self):
        cfg = Config({**DEFAULTS, "story.max_acceptance_criteria": 30})
        r = check_stories([story("S-1")], config=cfg, story_ac_count={"S-1": 20})
        self.assertTrue(r.passed)

    def test_too_wide_write_scope_blocks(self):
        wide = tuple(f"src/{i}.py" for i in range(20))
        r = check_stories([story("S-1", scope=wide)])
        self.assertFalse(r.passed)
        self.assertTrue(any("too many" in e for e in r.errors))


class TestTraceability(unittest.TestCase):
    def prd(self) -> PRD:
        return PRD(
            requirements=[req("FR-1"), req("FR-2"), req("FR-3")],
            open_questions=[OpenQuestion(id="OQ-1", text="?", blocks=["FR-3"])],
        )

    def test_uncovered_requirement_blocks(self):
        """Mất truy vết từ PRD tới code là lỗi chặn, không phải cảnh báo."""
        r = check_stories(
            [story("S-1")], self.prd(), story_fr_map={"S-1": ["FR-1"]}
        )
        self.assertFalse(r.passed)
        self.assertTrue(any("FR-2" in e for e in r.errors))

    def test_blocked_requirement_excluded_from_coverage(self):
        """FR-3 bị OQ-1 chặn nên không đòi story phủ nó."""
        r = check_stories(
            [story("S-1")], self.prd(), story_fr_map={"S-1": ["FR-1", "FR-2"]}
        )
        self.assertTrue(r.passed, r.summary())

    def test_story_touching_blocked_requirement_fails(self):
        r = check_stories(
            [story("S-1")], self.prd(), story_fr_map={"S-1": ["FR-1", "FR-2", "FR-3"]}
        )
        self.assertFalse(r.passed)
        self.assertTrue(any("blocked by open questions" in e for e in r.errors))

    def test_unknown_requirement_reference_warns(self):
        r = check_stories(
            [story("S-1")], self.prd(), story_fr_map={"S-1": ["FR-1", "FR-2", "FR-99"]}
        )
        self.assertTrue(any("FR-99" in w for w in r.warnings))


class TestCombine(unittest.TestCase):
    def test_merges_and_prefixes(self):
        a = check_prd(PRD())
        b = check_stories([])
        combined = check_all([a, b])
        self.assertFalse(combined.passed)
        self.assertTrue(all(e.startswith("[machine gate") for e in combined.errors))

    def test_all_passing_combines_to_pass(self):
        prd = PRD(requirements=[req("FR-1")])
        combined = check_all([check_prd(prd), check_stories([story("S-1")])])
        self.assertTrue(combined.passed)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestChuoiHoanToan(unittest.TestCase):
    """Epic bị xâu thành chuỗi thì máy chạy song song không với tới được.

    Đo trên e9: BMAD khai mỗi story phụ thuộc story ngay trước, cả 7 story
    của EPIC-01 thành 7 đợt. Máy chia đợt có, được kiểm bằng test đơn vị,
    và **không bao giờ chạy** — một năng lực đã tuyên bố mà không quan sát
    được lần nào.
    """

    def st(self, sid, deps=(), epic="EPIC-01", scope=("src/a.py",)):
        return Story(id=sid, epic_id=epic, title=sid,
                     depends_on=tuple(deps), write_scope=tuple(scope))

    def test_canh_bao_khi_moi_story_mot_dot(self):
        stories = [
            self.st("S-1"),
            self.st("S-2", ["S-1"], scope=("src/b.py",)),
            self.st("S-3", ["S-2"], scope=("src/c.py",)),
            self.st("S-4", ["S-3"], scope=("src/d.py",)),
        ]
        r = check_stories(stories)
        self.assertTrue(r.passed, r.errors)
        self.assertTrue(any("fully serialized" in w for w in r.warnings))
        self.assertTrue(any("EPIC-01" in w for w in r.warnings))

    def test_khong_canh_bao_khi_co_story_song_song(self):
        stories = [
            self.st("S-1"),
            self.st("S-2", ["S-1"], scope=("src/b.py",)),
            self.st("S-3", ["S-1"], scope=("src/c.py",)),
            self.st("S-4", ["S-2", "S-3"], scope=("src/d.py",)),
        ]
        r = check_stories(stories)
        self.assertFalse(any("fully serialized" in w for w in r.warnings))

    def test_epic_qua_nho_thi_khong_ket_luan(self):
        """Hai story nối nhau không nói lên gì về thói quen lập kế hoạch."""
        stories = [self.st("S-1"), self.st("S-2", ["S-1"], scope=("src/b.py",))]
        r = check_stories(stories)
        self.assertFalse(any("fully serialized" in w for w in r.warnings))

    def test_theo_tung_epic_khong_phai_ca_tap(self):
        """Epic chạy tuần tự với nhau; song song chỉ có nghĩa **trong** một
        epic. Tính trên cả tập thì con số ra khác và không nói lên gì."""
        stories = [
            self.st("S-1", epic="EPIC-01"),
            self.st("S-2", ["S-1"], epic="EPIC-01", scope=("src/b.py",)),
            self.st("S-3", ["S-2"], epic="EPIC-01", scope=("src/c.py",)),
            self.st("T-1", epic="EPIC-02", scope=("api/a.py",)),
            self.st("T-2", ["T-1"], epic="EPIC-02", scope=("api/b.py",)),
            self.st("T-3", ["T-1"], epic="EPIC-02", scope=("api/c.py",)),
        ]
        r = check_stories(stories)
        canh = [w for w in r.warnings if "fully serialized" in w]
        self.assertEqual(len(canh), 1)
        self.assertIn("EPIC-01", canh[0])
        self.assertNotIn("EPIC-02", canh[0])

