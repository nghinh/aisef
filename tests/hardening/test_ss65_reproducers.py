"""SS-65 — the original reproducers, written only against APIs that exist both before and after the fix
(`tools.detect_commands`, `tools.image_for`, `verify_image.recipe_for`, `<recipe>.dockerfile()`), so the same file is
RED on the frozen candidate abad2a6 and GREEN after the capability-model fix.

The defect: the tool a stack selects by default is not installed in the environment the same stack selects."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import tests  # noqa: E402,F401

from aisef.config import DEFAULTS, Config  # noqa: E402
from aisef.harness import tools, verify_image  # noqa: E402


def _selected_and_environment(marker: str, body: str = "") -> tuple[str, str, object]:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / marker).write_text(body, encoding="utf-8")
        exe = tools.detect_commands(tmp)["sast"].split()[0]
        image = tools.image_for(tmp, Config(dict(DEFAULTS)))
    return exe, image, verify_image.recipe_for(image)


class TestSS65PythonDefaultSastIsInThePythonImage(unittest.TestCase):
    def test_the_python_image_installs_the_sast_tool_python_selects(self):
        exe, image, recipe = _selected_and_environment("pyproject.toml")
        self.assertEqual(exe, "bandit", "precondition: the python profile selects bandit")
        self.assertIsNotNone(recipe, f"{image} is not a harness-built environment")
        self.assertIn(exe, recipe.dockerfile(), f"{image} never installs {exe}, which the python profile runs")


class TestSS65GoDefaultSastIsInTheGoImage(unittest.TestCase):
    def test_the_go_image_installs_the_sast_tool_go_selects(self):
        exe, image, recipe = _selected_and_environment("go.mod", "module x\n")
        self.assertEqual(exe, "gosec", "precondition: the go profile selects gosec")
        self.assertIsNotNone(recipe, f"{image} is not a harness-built environment: nothing guarantees {exe} in it")
        self.assertIn(exe, recipe.dockerfile(), f"{image} never installs {exe}, which the go profile runs")


if __name__ == "__main__":
    unittest.main()
