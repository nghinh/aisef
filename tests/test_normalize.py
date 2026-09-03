"""Kiểm chứng bộ dịch BMAD → mô hình của framework.

Fixture là PRD thật do BMAD sinh trong spike S6, không phải markdown bịa.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.control.normalize import parse_prd, parse_prd_file  # noqa: E402

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
