from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.harness.browser import RenderedScreen, RenderResult, availability  # noqa: E402
from aisef.harness.mockup_verify import concrete_route  # noqa: E402


class TestRenderedScreen(unittest.TestCase):
    def test_ok_when_no_error(self):
        s = RenderedScreen(id="s1")
        self.assertTrue(s.ok)

    def test_not_ok_when_error(self):
        s = RenderedScreen(id="s1", error="boom")
        self.assertFalse(s.ok)


class TestRenderResult(unittest.TestCase):
    def test_ok_empty_screens(self):
        r = RenderResult()
        self.assertTrue(r.ok)

    def test_not_ok_when_unavailable(self):
        r = RenderResult(unavailable="no node")
        self.assertFalse(r.ok)

    def test_not_ok_when_screen_has_error(self):
        r = RenderResult(screens=[RenderedScreen(id="x", error="fail")])
        self.assertFalse(r.ok)

    def test_ok_when_all_screens_ok(self):
        r = RenderResult(screens=[RenderedScreen(id="a"), RenderedScreen(id="b")])
        self.assertTrue(r.ok)

    def test_by_id_found(self):
        s = RenderedScreen(id="target")
        r = RenderResult(screens=[RenderedScreen(id="other"), s])
        self.assertIs(r.by_id("target"), s)

    def test_by_id_not_found(self):
        r = RenderResult(screens=[RenderedScreen(id="a")])
        self.assertIsNone(r.by_id("missing"))


class TestConcreteRoute(unittest.TestCase):
    def test_plain_route(self):
        self.assertEqual(concrete_route("/dashboard"), "/dashboard")

    def test_colon_param(self):
        self.assertEqual(concrete_route("/note/:id"), "/note/1")

    def test_bracket_param(self):
        self.assertEqual(concrete_route("/note/[id]"), "/note/1")

    def test_multiple_params(self):
        self.assertEqual(concrete_route("/a/:x/b/[y]"), "/a/1/b/1")

    def test_root(self):
        self.assertEqual(concrete_route("/"), "/")


class TestAvailability(unittest.TestCase):
    @patch("shutil.which", return_value=None)
    def test_no_node(self, _mock):
        reason = availability("/tmp/fake")
        self.assertIn("node", reason)


if __name__ == "__main__":
    unittest.main()
