"""Kiểm chứng bộ dịch BMAD → mô hình của framework.

Fixture là PRD thật do BMAD sinh trong spike S6, không phải markdown bịa.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.normalize import (  # noqa: E402
    parse_architecture,
    parse_architecture_file,
    parse_prd,
    parse_prd_file,
)

PRD_FIXTURE = ROOT / "tests" / "fixtures" / "bmad" / "prd.md"


class TestRealPRD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prd = parse_prd_file(PRD_FIXTURE)

    def test_extracts_all_functional_requirements(self):
        self.assertEqual(len(self.prd.functional()), 17)

    def test_extracts_non_functional(self):
        self.assertEqual(len(self.prd.non_functional()), 7)

    def test_ids_are_unique(self):
        ids = [r.id for r in self.prd.requirements]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_functional_requirement_is_testable(self):
        """Yêu cầu không có tiêu chí kiểm chứng thì không nghiệm thu được."""
        self.assertEqual(self.prd.untestable(), [])

    def test_acceptance_criteria_extracted(self):
        fr1 = self.prd.by_id("FR-1")
        self.assertIsNotNone(fr1)
        self.assertEqual(fr1.title, "Tạo ghi chú")
        self.assertGreaterEqual(len(fr1.acceptance_criteria), 3)
        self.assertTrue(any("không có kết nối mạng" in c for c in fr1.acceptance_criteria))

    def test_nfr_has_title_and_description(self):
        nfr = self.prd.by_id("NFR-2")
        self.assertIn("trễ", nfr.title.lower())
        self.assertIn("200ms", nfr.description)

    def test_assumptions_collected(self):
        self.assertGreaterEqual(len(self.prd.assumptions), 10)
        self.assertTrue(all(a.strip() for a in self.prd.assumptions))

    def test_assumptions_deduplicated(self):
        self.assertEqual(len(self.prd.assumptions), len(set(self.prd.assumptions)))

    def test_open_questions_extracted(self):
        self.assertEqual(len(self.prd.open_questions), 8)

    def test_blocked_requirements_detected(self):
        """OQ-1 chặn FR-13..FR-15 — dải phải được mở ra thành từng mã."""
        self.assertEqual(sorted(self.prd.blocked_ids()), ["FR-13", "FR-14", "FR-15"])

    def test_blocking_question_carries_text(self):
        oq1 = next(q for q in self.prd.open_questions if q.id == "OQ-1")
        self.assertIn("định danh", oq1.text)
        self.assertEqual(oq1.blocks, ["FR-13", "FR-14", "FR-15"])

    def test_assumption_markers_stripped_from_description(self):
        """Ghi chú giả định là siêu dữ liệu, không thuộc nội dung yêu cầu."""
        for r in self.prd.requirements:
            with self.subTest(req=r.id):
                self.assertNotIn("[ASSUMPTION", r.description)

    def test_serialisable(self):
        d = self.prd.as_dict()
        self.assertEqual(len(d["requirements"]), 24)
        self.assertIn("open_questions", d)


class TestParsing(unittest.TestCase):
    def test_minimal_functional_requirement(self):
        prd = parse_prd(
            "#### FR-1: Đăng nhập\n\n"
            "Người dùng đăng nhập được.\n\n"
            "**Consequences (testable):**\n"
            "- Sai mật khẩu thì báo lỗi.\n"
            "- Đúng thì vào được trang chính.\n"
        )
        self.assertEqual(len(prd.functional()), 1)
        self.assertEqual(prd.by_id("FR-1").acceptance_criteria[0], "Sai mật khẩu thì báo lỗi.")

    def test_requirement_without_criteria_is_flagged(self):
        prd = parse_prd("#### FR-9: Mơ hồ\n\nLàm cho nó tốt hơn.\n")
        self.assertFalse(prd.by_id("FR-9").is_testable)
        self.assertEqual([r.id for r in prd.untestable()], ["FR-9"])

    def test_open_question_range_expansion(self):
        prd = parse_prd("**OQ-3 (chặn FR-2..FR-4)** — Câu hỏi gì đó.\n")
        self.assertEqual(prd.open_questions[0].blocks, ["FR-2", "FR-3", "FR-4"])

    def test_open_question_single_reference(self):
        prd = parse_prd("**OQ-5 (chặn FR-7)** — Câu hỏi khác.\n")
        self.assertEqual(prd.open_questions[0].blocks, ["FR-7"])

    def test_open_question_without_scope(self):
        prd = parse_prd("**OQ-6** — Không nêu phạm vi.\n")
        self.assertEqual(prd.open_questions[0].blocks, [])

    def test_requirement_records_referenced_questions(self):
        prd = parse_prd(
            "#### FR-2: X\n\nMô tả có nhắc OQ-4 ở đây.\n\n"
            "**Consequences (testable):**\n- Điều gì đó.\n"
        )
        self.assertIn("OQ-4", prd.by_id("FR-2").open_questions)

    def test_empty_document(self):
        prd = parse_prd("")
        self.assertEqual(prd.requirements, [])
        self.assertEqual(prd.assumptions, [])

    def test_document_without_requirements(self):
        prd = parse_prd("# Tài liệu\n\nChỉ là văn xuôi.\n")
        self.assertEqual(prd.functional(), [])

    def test_heading_levels_accepted(self):
        for hashes in ("##", "###", "####", "#####"):
            with self.subTest(level=hashes):
                prd = parse_prd(f"{hashes} FR-1: Tiêu đề\n\nMô tả.\n")
                self.assertEqual(len(prd.functional()), 1)

    def test_malformed_range_ignored(self):
        prd = parse_prd("**OQ-1 (chặn FR-9..FR-2)** — dải ngược.\n")
        self.assertEqual(prd.open_questions[0].blocks, ["FR-2", "FR-9"])

    def test_numbered_list_acceptance_criteria(self):
        prd = parse_prd(
            "### FR-1: Login\n\nLogin page.\n\n"
            "**Acceptance criteria:**\n"
            "1. Given valid credentials, then logged in\n"
            "2. Given invalid credentials, then error\n"
        )
        self.assertEqual(len(prd.functional()[0].acceptance_criteria), 2)

    def test_heading_style_nfr(self):
        prd = parse_prd(
            "### FR-1: X\n\nDesc.\n\n**Testable consequences:**\n- Works\n\n"
            "### NFR-1 — Performance\nUnder 200ms.\n\n"
            "### NFR-2 — Scale\n1000 users.\n"
        )
        self.assertEqual(len(prd.non_functional()), 2)
        self.assertEqual(prd.by_id("NFR-1").title, "Performance")
        self.assertIn("200ms", prd.by_id("NFR-1").description)

    def test_numbered_nfr_fallback(self):
        prd = parse_prd(
            "### FR-1: X\n\nDesc.\n\n**Testable consequences:**\n- OK\n\n"
            "### Non-functional Requirements\n\n"
            "1. Response time under 200ms\n"
            "2. Support 1000 concurrent users\n"
        )
        self.assertEqual(len(prd.non_functional()), 2)
        self.assertEqual(prd.by_id("NFR-1").title, "Response time under 200ms")


class TestArchitecture(unittest.TestCase):
    """Đọc architecture.md thật (26KB, 20 quyết định, do BMAD sinh)."""

    @classmethod
    def setUpClass(cls):
        path = ROOT / "tests" / "fixtures" / "bmad" / "architecture.md"
        if not path.is_file():
            raise unittest.SkipTest("chưa có fixture architecture.md")
        cls.arch = parse_architecture_file(path)

    def test_reads_every_decision(self):
        self.assertEqual(len(self.arch.decisions), 20)
        self.assertEqual(self.arch.decisions[0].id, "AR-1")

    def test_rule_and_prevents_split(self):
        d = self.arch.by_id("AR-1")
        self.assertIn("store/", d.rule)
        self.assertTrue(d.prevents)

    def test_binds_maps_requirements_to_decisions(self):
        self.assertIn("FR-2", self.arch.by_id("AR-1").binds)

    def test_selection_is_lookup_not_guesswork(self):
        """Nạp cả 26KB vào mỗi phiên vừa tốn vừa loãng; để agent tự chọn thì
        mỗi phiên chọn một kiểu. Mục `Binds:` cho đáp án tất định."""
        chosen = [d.id for d in self.arch.for_requirements(["FR-5", "FR-6"])]
        self.assertIn("AR-6", chosen)   # chuẩn hoá văn bản — đúng là của tìm kiếm
        self.assertNotIn("AR-13", chosen)  # dung lượng — không liên quan

    def test_universal_decisions_always_included(self):
        """`Binds: all` là luật nền. Coi nó là "không áp cho story nào" sẽ
        bỏ rơi đúng những luật quan trọng nhất."""
        chosen = [d.id for d in self.arch.for_requirements(["FR-17"])]
        self.assertIn("AR-2", chosen)
        self.assertIn("AR-19", chosen)

    def test_prompt_form_carries_the_rule(self):
        text = self.arch.by_id("AR-6").as_prompt()
        self.assertIn("AR-6", text)
        self.assertIn("Rule:", text)


class TestArchitectureRobustness(unittest.TestCase):
    def test_empty_document(self):
        self.assertEqual(parse_architecture("# trống\n").decisions, [])

    def test_decision_without_binds_is_universal(self):
        arch = parse_architecture("### AR-1 — Luật nền\n\n- **Rule:** luôn đúng.\n")
        self.assertTrue(arch.by_id("AR-1").universal)
        self.assertEqual([d.id for d in arch.for_requirements(["FR-99"])], ["AR-1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
