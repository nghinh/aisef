"""Kiểm chứng đối chiếu mockup trên aria snapshot THẬT của Playwright.

Ba fixture do spike S7 sinh ra bằng `page.locator('body').ariaSnapshot()`
trên chromium: mockup (hợp đồng), app đủ, app thiếu một component và thừa
một component.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.harness.aria import (  # noqa: E402
    Component,
    compare,
    compare_snapshots,
    parse_aria_snapshot,
)

FIX = ROOT / "tests" / "fixtures" / "aria"


def snap(name: str) -> str:
    return (FIX / f"{name}.txt").read_text(encoding="utf-8")


class TestParse(unittest.TestCase):
    def test_extracts_contract_roles(self):
        comps = parse_aria_snapshot(snap("mockup"))
        roles = [c.role for c in comps]
        for r in ("heading", "textbox", "checkbox", "button", "link"):
            self.assertIn(r, roles)

    def test_drops_plain_text_nodes(self):
        """`- text: Email` là chi tiết trình bày, không phải hợp đồng."""
        self.assertNotIn("text", [c.role for c in parse_aria_snapshot(snap("mockup"))])

    def test_drops_unnamed_components(self):
        comps = parse_aria_snapshot('- button\n- button "Lưu"\n')
        self.assertEqual(comps, [Component("button", "Lưu")])

    def test_keeps_vietnamese_names(self):
        names = [c.name for c in parse_aria_snapshot(snap("mockup"))]
        self.assertIn("Ghi nhớ đăng nhập", names)
        self.assertIn("Quên mật khẩu?", names)

    def test_empty_snapshot(self):
        self.assertEqual(parse_aria_snapshot(""), [])

    def test_ignores_non_matching_lines(self):
        self.assertEqual(parse_aria_snapshot("rác\n  - /url: /forgot\n"), [])


class TestCompareRealPages(unittest.TestCase):
    def test_matching_app_passes(self):
        r = compare_snapshots(snap("mockup"), snap("app-good"), screen_id="SCREEN-01")
        self.assertTrue(r.passed)
        self.assertEqual(r.missing, [])
        self.assertEqual(r.extra, [])
        self.assertEqual(r.matched, len(r.contract))

    def test_missing_component_fails(self):
        r = compare_snapshots(snap("mockup"), snap("app-bad"), screen_id="SCREEN-01")
        self.assertFalse(r.passed)
        self.assertEqual([str(c) for c in r.missing], ['checkbox "Ghi nhớ đăng nhập"'])

    def test_extra_component_is_only_a_warning(self):
        """App thật được phép thêm phần tử — không chặn."""
        r = compare_snapshots(snap("mockup"), snap("app-bad"))
        self.assertIn('button "Đăng nhập bằng Google"', [str(c) for c in r.extra])
        # vẫn fail, nhưng vì `missing`, không phải vì `extra`
        self.assertTrue(r.missing)

    def test_extra_alone_does_not_fail(self):
        contract = [Component("button", "Lưu")]
        actual = [Component("button", "Lưu"), Component("button", "Trợ giúp")]
        r = compare(contract, actual)
        self.assertTrue(r.passed)
        self.assertEqual(len(r.extra), 1)

    def test_evidence_shape(self):
        r = compare_snapshots(snap("mockup"), snap("app-bad"),
                              screen_id="SCREEN-01", route="/login")
        ev = r.to_evidence()
        self.assertEqual(ev["screen_id"], "SCREEN-01")
        self.assertEqual(ev["route"], "/login")
        self.assertEqual(ev["matched"], ev["contract_components"] - 1)
        self.assertFalse(ev["passed"])

    def test_summary_readable(self):
        text = compare_snapshots(snap("mockup"), snap("app-bad"), screen_id="SCREEN-01").summary()
        self.assertIn("FAIL", text)
        self.assertIn("missing", text)


class TestCompareSemantics(unittest.TestCase):
    def test_order_does_not_matter(self):
        """Mockup và app có thể sắp xếp khác nhau mà vẫn đúng hợp đồng."""
        a = [Component("button", "Lưu"), Component("textbox", "Tên")]
        r = compare(a, list(reversed(a)))
        self.assertTrue(r.passed)

    def test_role_mismatch_counts_as_missing(self):
        """Cùng tên nhưng sai vai trò là sai hợp đồng."""
        r = compare([Component("button", "Tìm")], [Component("link", "Tìm")])
        self.assertFalse(r.passed)
        self.assertEqual(str(r.missing[0]), 'button "Tìm"')

    def test_empty_contract_always_passes(self):
        self.assertTrue(compare([], [Component("button", "X")]).passed)

    def test_empty_actual_fails_when_contract_exists(self):
        r = compare([Component("button", "Lưu")], [])
        self.assertFalse(r.passed)
        self.assertEqual(r.matched, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
