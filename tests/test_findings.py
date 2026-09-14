"""Structured finding model — every branch pinned."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.control.findings import (  # noqa: E402
    Finding, FindingBook, TransitionError,
    Trust, Severity, Status,
    SOURCE_REVIEWER, REVIEWER_TRUST,
    apply_transition,
)


class TestConstruction(unittest.TestCase):
    def test_minimum_finding(self):
        f = Finding.make(SOURCE_REVIEWER, Trust.REVIEWER.value,
                         Severity.HIGH.value, body="unsafe eval")
        self.assertEqual(f.severity, "high")
        self.assertEqual(f.status, "open")
        self.assertEqual(len(f.id), 16)

    def test_rejects_agent_trust(self):
        with self.assertRaises(ValueError):
            Finding.make(SOURCE_REVIEWER, Trust.AGENT.value,
                         Severity.LOW.value, body="x")

    def test_rejects_unknown_source(self):
        with self.assertRaises(ValueError):
            Finding.make("made-up", Trust.REVIEWER.value,
                         Severity.LOW.value, body="x")

    def test_id_is_stable_across_construction(self):
        a = Finding.make(SOURCE_REVIEWER, Trust.REVIEWER.value,
                         Severity.HIGH.value, file="a.py", line=10, body="x")
        b = Finding.make(SOURCE_REVIEWER, Trust.REVIEWER.value,
                         Severity.HIGH.value, file="a.py", line=10, body="x")
        self.assertEqual(a.id, b.id)

    def test_id_changes_with_body(self):
        a = Finding.make(SOURCE_REVIEWER, Trust.REVIEWER.value,
                         Severity.HIGH.value, file="a.py", line=10, body="x")
        b = Finding.make(SOURCE_REVIEWER, Trust.REVIEWER.value,
                         Severity.HIGH.value, file="a.py", line=10, body="y")
        self.assertNotEqual(a.id, b.id)


class TestDangDongNguoiRaSoatThucSuViet(unittest.TestCase):
    """Lỗi 158: `_LINE_RE` chỉ nhận `[low|medium|high|critical] tệp:dòng thân`,
    trong khi `kit/prompts/story-review.md` dặn người rà soát viết
    `[block] đường/dẫn:dòng — thân`. Đo trên bằng chứng đã ghi của năm corpus:
    **177 dòng chặn, 0 dòng phân giải được**, nên `Finding.id` không bao giờ
    được tính trên đầu ra thật và `implement._same_complaint_by_finding` luôn
    trả False — kể cả bên trong `deadlock_reason`, chỗ quyết định có ngừng đốt
    lượt hay không. Phép thử cũ xanh vì nó cho parser ăn `[high] src/pay.py:42`,
    một hình dạng production **không bao giờ** sinh ra (lỗi đa dạng cú pháp).
    """

    def _one(self, line):
        return Finding.parse_lines([line], source=SOURCE_REVIEWER, trust="reviewer")

    def test_the_nguoi_ra_soat_that_phan_giai_duoc(self):
        got = self._one("[block] bin/marks.js:12 — lstatSync swallows ENOENT")
        self.assertEqual(len(got), 1, "dạng prompt dặn viết mà không đọc được")
        self.assertEqual(got[0].file, "bin/marks.js")
        self.assertEqual(got[0].line, 12)
        self.assertNotIn("—", got[0].body[:2])   # dấu ngăn không phải thân

    def test_bon_the_cua_prompt_deu_doc_duoc_va_doi_dung_muc(self):
        for tag, sev in (("block", "high"), ("stuck", "high"),
                         ("should fix", "medium"), ("suggestion", "low")):
            with self.subTest(tag=tag):
                got = self._one(f"[{tag}] a/b.js:3 — chuyện gì đó")
                self.assertEqual(len(got), 1, f"[{tag}] không đọc được")
                self.assertEqual(got[0].severity, sev)

    def test_dang_cu_van_doc_duoc(self):
        self.assertEqual(len(self._one("[high] src/pay.py:42 body here")), 1)


class TestRoundTrip(unittest.TestCase):
    def test_line_round_trip(self):
        f = Finding.make(SOURCE_REVIEWER, Trust.REVIEWER.value,
                         Severity.CRITICAL.value, file="src/auth.py",
                         line=42, body="use of eval")
        self.assertEqual(
            f.format_line(),
            "[critical] src/auth.py:42  use of eval")

    def test_parse_lines_accepts_canonical_form(self):
        lines = [
            "[high] src/a.py:1  body one",
            "[low] src/b.py:2  body two",
            "",                              # blank
            "free-form prose",               # not a finding
            "[medium] c.py:3  body three",
        ]
        out = Finding.parse_lines(lines, source=SOURCE_REVIEWER,
                                  trust=Trust.REVIEWER.value)
        self.assertEqual(len(out), 3)
        self.assertEqual([f.severity for f in out], ["high", "low", "medium"])

    def test_reviewer_only_includes_admissible_trust(self):
        # Agent trust is filtered at construction; the open() entry point
        # for memory-observed notes is the parse path, and parse never
        # produces agent-authored findings.
        for trust in (Trust.AGENT,):
            with self.assertRaises(ValueError):
                Finding.make(SOURCE_REVIEWER, trust.value, Severity.LOW.value,
                             body="x")


class TestLifecycle(unittest.TestCase):
    def _f(self, prescription: str = "use a parser"):
        return Finding.make(
            SOURCE_REVIEWER, Trust.REVIEWER.value,
            Severity.HIGH.value, file="x.py", line=1, body="unsafe",
            prescription=prescription, behavior_id="AC-1-1",
        )

    def test_open_to_closed_requires_evidence(self):
        with self.assertRaises(TransitionError):
            apply_transition(self._f(), to=Status.CLOSED)

    def test_open_to_closed_with_evidence_works(self):
        opened = self._f()
        closed = apply_transition(opened, to=Status.CLOSED,
                                  evidence="tests pass")
        self.assertEqual(closed.status, "closed")

    def test_open_to_stuck_allowed(self):
        opened = self._f()
        stuck = apply_transition(opened, to=Status.STUCK)
        self.assertEqual(stuck.status, "stuck")

    def test_closed_to_reopened_requires_evidence(self):
        opened = self._f()
        closed = apply_transition(opened, to=Status.CLOSED, evidence="ok")
        with self.assertRaises(TransitionError):
            apply_transition(closed, to=Status.REOPENED)

    def test_reopened_to_closed_with_new_evidence(self):
        opened = self._f()
        closed = apply_transition(opened, to=Status.CLOSED, evidence="ok")
        reopened = apply_transition(closed, to=Status.REOPENED,
                                    evidence="regression at HEAD")
        self.assertEqual(reopened.status, "reopened")
        closed2 = apply_transition(reopened, to=Status.CLOSED,
                                   evidence="re-fixed")
        self.assertEqual(closed2.status, "closed")

    def test_prescription_match_closes_without_evidence(self):
        # Bug 61 pattern: reviewer prescribed "5.5s observation window",
        # author implemented it, reviewer then failed for having one.
        # When the new prescription matches the old, the close is allowed
        # even without fresh evidence — the author did what was asked.
        f1 = self._f(prescription="add a 5.5s observation window")
        f2 = apply_transition(f1, to=Status.CLOSED,
                              force_prescription_match=True,
                              previous_prescription=f1.prescription)
        self.assertEqual(f2.status, "closed")

    def test_goalpost_shift_refused(self):
        f1 = self._f(prescription="add a 5.5s observation window")
        # Reviewer rewrote its prescription to a harder requirement.
        with self.assertRaises(TransitionError):
            apply_transition(f1, to=Status.CLOSED,
                             force_prescription_match=True,
                             previous_prescription=f1.prescription + " — "
                             "deterministic timer control required")


class TestBook(unittest.TestCase):
    def test_blocking_returns_only_open_reopened_high_critical(self):
        book = FindingBook()
        book.add(Finding.make(SOURCE_REVIEWER, Trust.REVIEWER.value,
                              Severity.LOW.value, body="low"))
        book.add(Finding.make(SOURCE_REVIEWER, Trust.REVIEWER.value,
                              Severity.HIGH.value, body="high"))
        closed = apply_transition(
            Finding.make(SOURCE_REVIEWER, Trust.REVIEWER.value,
                         Severity.CRITICAL.value, body="crit"),
            to=Status.CLOSED, evidence="x",
        )
        book.add(closed)
        ids = sorted(book.blocking_ids())
        self.assertEqual(len(ids), 1)
        self.assertEqual(book.findings[1].id, ids[0])

    def test_to_lines_round_trip(self):
        book = FindingBook()
        book.add(Finding.make(SOURCE_REVIEWER, Trust.REVIEWER.value,
                              Severity.HIGH.value, file="x.py", line=1,
                              body="text"))
        rendered = book.to_lines()
        parsed = Finding.parse_lines(rendered, source=SOURCE_REVIEWER,
                                     trust=Trust.REVIEWER.value)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].body, "text")


class TestReviewerTrust(unittest.TestCase):
    def test_admissible_review_trust_classes(self):
        # Mirrors the trust ranking the user specified.
        self.assertIn(Trust.HUMAN.value, REVIEWER_TRUST)
        self.assertIn(Trust.DETERMINISTIC.value, REVIEWER_TRUST)
        self.assertIn(Trust.GATE.value, REVIEWER_TRUST)
        self.assertIn(Trust.SECURITY.value, REVIEWER_TRUST)
        self.assertIn(Trust.REVIEWER.value, REVIEWER_TRUST)
        self.assertIn(Trust.LANDED.value, REVIEWER_TRUST)
        self.assertNotIn(Trust.AGENT.value, REVIEWER_TRUST)


if __name__ == "__main__":
    unittest.main()
