"""Kiểm chứng cổng phê duyệt của con người."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.control.approvals import (  # noqa: E402
    GATE_ARTIFACTS,
    GATE_ORDER,
    ApprovalStore,
    Gate,
    Status,
    parse_auto_approve,
)


class ApprovalTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = ApprovalStore(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, gate: Gate, text: str) -> Path:
        """Ghi mọi artifact của cổng. Trả về file chính."""
        written = []
        for name in GATE_ARTIFACTS[gate]:
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            written.append(p)
        return written[0]


class TestBasicFlow(ApprovalTestCase):
    def test_unknown_gate_is_pending(self):
        self.assertIs(self.store.status(Gate.PRD), Status.PENDING)

    def test_approve_then_approved(self):
        self.write(Gate.PRD, "# PRD v1")
        self.store.approve(Gate.PRD, by="nghi")
        self.assertIs(self.store.status(Gate.PRD), Status.APPROVED)

    def test_reject_requires_note(self):
        self.write(Gate.PRD, "# PRD v1")
        with self.assertRaises(ValueError):
            self.store.reject(Gate.PRD, note="   ")

    def test_reject_records_note(self):
        self.write(Gate.PRD, "# PRD v1")
        self.store.reject(Gate.PRD, note="thiếu chỉ tiêu phi chức năng")
        self.assertIs(self.store.status(Gate.PRD), Status.CHANGES_REQUESTED)
        self.assertIn("phi chức năng", self.store.load(Gate.PRD).note)

    def test_history_preserved_across_decisions(self):
        self.write(Gate.PRD, "# PRD v1")
        self.store.reject(Gate.PRD, note="sửa mục 3")
        self.write(Gate.PRD, "# PRD v2")
        rec = self.store.approve(Gate.PRD, by="nghi")
        self.assertEqual(len(rec.history), 1)
        self.assertEqual(rec.history[0]["status"], Status.CHANGES_REQUESTED.value)


class TestContentBinding(ApprovalTestCase):
    def test_editing_artifact_invalidates_approval(self):
        """Phê duyệt gắn với nội dung — sửa file thì hết hiệu lực."""
        self.write(Gate.PRD, "# PRD v1")
        self.store.approve(Gate.PRD, by="nghi")
        self.assertIs(self.store.status(Gate.PRD), Status.APPROVED)

        self.write(Gate.PRD, "# PRD v1 — thêm một mục")
        self.assertIs(self.store.status(Gate.PRD), Status.STALE)

    def test_restoring_content_restores_approval(self):
        self.write(Gate.PRD, "# PRD v1")
        self.store.approve(Gate.PRD, by="nghi")
        self.write(Gate.PRD, "đã đổi")
        self.assertIs(self.store.status(Gate.PRD), Status.STALE)
        self.write(Gate.PRD, "# PRD v1")
        self.assertIs(self.store.status(Gate.PRD), Status.APPROVED)


class TestCascade(ApprovalTestCase):
    def test_reapproving_upstream_makes_downstream_stale(self):
        """Duyệt lại PRD thì Architecture đã duyệt phải cần xem lại."""
        self.write(Gate.PRD, "# PRD v1")
        self.write(Gate.ARCHITECTURE, "# Arch v1")
        self.store.approve(Gate.PRD, by="nghi")
        self.store.approve(Gate.ARCHITECTURE, by="nghi")
        self.assertIs(self.store.status(Gate.ARCHITECTURE), Status.APPROVED)

        # PRD đổi và được duyệt lại → Architecture dựa trên bản cũ
        self.write(Gate.PRD, "# PRD v2")
        self.store.approve(Gate.PRD, by="nghi")
        self.assertIs(self.store.status(Gate.PRD), Status.APPROVED)
        self.assertIs(self.store.status(Gate.ARCHITECTURE), Status.STALE)

    def test_blocking_lists_unapproved_upstream(self):
        self.write(Gate.PRD, "# PRD")
        self.store.approve(Gate.PRD, by="nghi")
        blocking = self.store.blocking(Gate.EPICS)
        self.assertNotIn(Gate.PRD, blocking)
        self.assertIn(Gate.ARCHITECTURE, blocking)
        self.assertIn(Gate.UX_SPEC, blocking)

    def test_first_gate_has_no_blockers(self):
        self.assertEqual(self.store.blocking(Gate.PRD), [])


class TestAutoApprove(ApprovalTestCase):
    def test_auto_is_marked_as_auto(self):
        """Phải truy được artifact nào chưa từng có người thật xem."""
        self.write(Gate.PRD, "# PRD")
        rec = self.store.auto_approve(Gate.PRD)
        self.assertIs(self.store.status(Gate.PRD), Status.APPROVED)
        self.assertTrue(rec.was_auto)

    def test_human_approval_is_not_auto(self):
        self.write(Gate.PRD, "# PRD")
        rec = self.store.approve(Gate.PRD, by="nghi")
        self.assertFalse(rec.was_auto)

    def test_parse_none_and_empty(self):
        self.assertEqual(parse_auto_approve(None), frozenset())
        self.assertEqual(parse_auto_approve(""), frozenset())

    def test_parse_all(self):
        self.assertEqual(parse_auto_approve("all"), frozenset(GATE_ORDER))

    def test_parse_subset(self):
        got = parse_auto_approve("prd, architecture")
        self.assertEqual(got, frozenset({Gate.PRD, Gate.ARCHITECTURE}))

    def test_parse_rejects_unknown_gate(self):
        with self.assertRaises(ValueError) as ctx:
            parse_auto_approve("prd,khong-ton-tai")
        self.assertIn("khong-ton-tai", str(ctx.exception))


class TestDurability(ApprovalTestCase):
    def test_survives_new_store_instance(self):
        self.write(Gate.PRD, "# PRD")
        self.store.approve(Gate.PRD, by="nghi")
        # người khác, tiến trình khác, cùng thư mục
        self.assertIs(ApprovalStore(self.root).status(Gate.PRD), Status.APPROVED)

    def test_corrupt_record_reads_as_pending(self):
        self.write(Gate.PRD, "# PRD")
        self.store.approve(Gate.PRD, by="nghi")
        (self.root / "approvals" / "prd.json").write_text("{ hỏng", encoding="utf-8")
        self.assertIs(self.store.status(Gate.PRD), Status.PENDING)

    def test_summary_covers_every_gate(self):
        self.assertEqual(len(self.store.summary()), len(GATE_ORDER))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestStorySuaKhongLamStaleCongStories(unittest.TestCase):
    """Story sửa (`STORY-RP-*`, ADR-004 R3) do cổng `improve` quản, không phải cổng `stories`.

    Đo e9 2026-09-06 05:44: vòng 1 thêm hai story sửa vào chỉ mục → `stories` và
    `readiness` đã duyệt thành stale → lần gọi `improve` kế bị chính vòng trước chặn.
    """

    def setUp(self):
        import json
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = ApprovalStore(self.root)
        self.json = json
        self.index = {"stories": [{"id": "STORY-01-01", "epic_id": "EPIC-01", "write_scope": ["src"]}],
                      "epics": [{"id": "EPIC-01"}]}
        self.ghi(self.index)
        for g in GATE_ORDER:
            if g is Gate.STORIES:
                break
            (self.root / GATE_ARTIFACTS[g][0]).write_text("x", encoding="utf-8")
            self.store.approve(g, by="t")
        self.store.approve(Gate.STORIES, by="t")

    def tearDown(self):
        self._tmp.cleanup()

    def ghi(self, data):
        (self.root / "stories.index.json").write_text(self.json.dumps(data, ensure_ascii=False, indent=1),
                                                       encoding="utf-8")

    def test_dot_chay_cua_epic_sua_doi_moi_vong_khong_stale(self):
        """Lỗi 28 (e9 06:50): vòng 4/5 thay `waves["EPIC-RP-01"]` → stale lại
        dù lỗi 25 đã lọc story/epic sửa. Đổi đợt chạy của epic **thật** vẫn stale."""
        data = self.json.loads(self.json.dumps(self.index))
        data["waves"] = {"EPIC-01": [["STORY-01-01"]], "EPIC-RP-01": [["STORY-RP-04"]]}
        self.ghi(data)
        self.store.approve(Gate.STORIES, by="t")
        data["waves"]["EPIC-RP-01"] = [["STORY-RP-05"]]
        self.ghi(data)
        self.assertIs(self.store.status(Gate.STORIES), Status.APPROVED)
        data["waves"]["EPIC-01"] = [["STORY-01-01"], ["STORY-01-02"]]
        self.ghi(data)
        self.assertIs(self.store.status(Gate.STORIES), Status.STALE)

    def test_them_story_sua_khong_stale(self):
        self.assertIs(self.store.status(Gate.STORIES), Status.APPROVED)
        data = self.json.loads(self.json.dumps(self.index))
        data["stories"].append({"id": "STORY-RP-01", "epic_id": "EPIC-RP-EPIC-01", "repair_of": "AC-STORY-01-01-1"})
        data["epics"].append({"id": "EPIC-RP-EPIC-01"})
        self.ghi(data)
        self.assertIs(self.store.status(Gate.STORIES), Status.APPROVED)
        # Đã có story sửa rồi mà đổi story **thật** thì vẫn stale — băm lọc chỉ bỏ story sửa.
        self.store.approve(Gate.STORIES, by="t")
        data["stories"][0]["write_scope"] = ["src", "tests"]
        self.ghi(data)
        self.assertIs(self.store.status(Gate.STORIES), Status.STALE)

    def test_doi_story_that_van_stale_khi_chua_co_story_sua(self):
        data = self.json.loads(self.json.dumps(self.index)); data["stories"][0]["write_scope"] = ["lib"]
        self.ghi(data)
        self.assertIs(self.store.status(Gate.STORIES), Status.STALE)

