"""Mockup bỏ quên `data-state` → hợp đồng ôm cả trang gồm nhiều trạng thái.

Đo 2026-09-05 trên e9 (note-editor): 32 component, 4 lần "Thêm thẻ", story
đốt $28 qua 4 lượt mà không thể qua bước map mockup. Cổng máy mockup phải
chặn từ trước, và hợp đồng phải gộp trùng.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.control.design_contract import ScreenContract, build  # noqa: E402
from aisdlc.control.experience import Experience, Screen  # noqa: E402
from aisdlc.control.machine_gate import check_design_contract  # noqa: E402

ONE_STATE = (ROOT / "tests" / "fixtures" / "aria" / "mockup.txt").read_text(encoding="utf-8")
GALLERY = ONE_STATE + ONE_STATE  # hai trạng thái dựng cạnh nhau, không đánh dấu

EXP = Experience(screens=[Screen(id="s1", name="S1", route="/s1")])


def rendered(snapshot: str, primary: str = ""):
    scr = SimpleNamespace(
        id="s1", error="", route="/s1", html="", png="", snapshot=snapshot,
        primary_snapshot=primary, sample_snapshots=[], annotation_snapshots=[],
        declared_states=[], fields=[], unresolved=[], console_errors=[],
    )
    return SimpleNamespace(by_id=lambda sid: scr if sid == "s1" else None)


class TestWholePageContract(unittest.TestCase):
    def test_no_primary_with_duplicates_blocks_gate(self):
        c = build(EXP, rendered(GALLERY))
        s = c.by_id("s1")
        self.assertTrue(s.whole_page)
        self.assertGreater(len(s.components), 0)
        self.assertEqual(s.duplicates, len(s.components))  # mỗi component hai lần
        errs = check_design_contract(c, EXP).errors
        self.assertTrue(any("data-state" in e and "s1" in e for e in errs), errs)

    def test_primary_declared_passes(self):
        c = build(EXP, rendered(GALLERY, primary=ONE_STATE))
        s = c.by_id("s1")
        self.assertFalse(s.whole_page)
        self.assertEqual(s.duplicates, 0)
        self.assertFalse(any("data-state" in e for e in check_design_contract(c, EXP).errors))

    def test_single_state_without_marker_is_fine(self):
        # Một trạng thái, không trùng — cả trang chính là trạng thái ấy.
        c = build(EXP, rendered(ONE_STATE))
        self.assertTrue(c.by_id("s1").whole_page)
        self.assertFalse(any("data-state" in e for e in check_design_contract(c, EXP).errors))

    def test_roundtrip_keeps_flags(self):
        s = ScreenContract.from_dict(ScreenContract(id="x", whole_page=True, duplicates=3).as_dict())
        self.assertTrue(s.whole_page)
        self.assertEqual(s.duplicates, 3)


if __name__ == "__main__":
    unittest.main()
