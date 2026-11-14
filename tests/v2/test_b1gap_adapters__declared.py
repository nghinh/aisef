"""B1 gap kill tests for aisef2/app/adapters.py::_declared (mutation campaign survivors).

Function level, hermetic and offline: `_bounded` is replaced at the module boundary, so no process is ever
started and no binary is asked. Each test names the exact surviving mutant it kills."""

from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import review_ocr  # noqa: E402


class Declared(unittest.TestCase):
    """adapters._declared: the version question's guard and its clean-environment temporary directory."""

    # kills: L351 element 0 dropped  (except (OSError, RangeError) -> except (RangeError,))
    def test_an_oserror_while_asking_version_is_returned_as_could_not_be_started_not_raised(self):
        # OSError is the system failing to run the question at all (fork/FD/pipe: out.open, Popen, stdin.write);
        # it must come back as (None, why) so Reviewer._ocr refuses with CapabilityUnrunnable instead of crashing.
        with mock.patch.object(ad, "_bounded", side_effect=OSError("fork failed")):
            declared, why = ad._declared("/pinned/ocr", review_ocr.VERSION_TIMEOUT_S)
        self.assertIsNone(declared)
        self.assertIsInstance(why, str)
        self.assertIn("OSError", why)  # the guard reports the exception TYPE it caught, a semantic field of the arm

    # kills: L344 string 'aisef-ocr-version-' emptied
    def test_the_version_question_runs_in_a_temporary_directory_named_as_aisefs(self):
        # the directory name is machine-observable outside the message: the child sees it as its cwd and HOME,
        # and the operator identifies AISEF's leaked temp dirs by it
        seen = {}

        def fake_bounded(argv, cwd, env, out, timeout_s, name):
            seen["cwd"], seen["env"] = cwd, env
            out.write_text("open-code-review v1.12.12 (182898c) darwin/arm64\n", encoding="utf-8")
            return 0

        with mock.patch.object(ad, "_bounded", fake_bounded):
            declared, why = ad._declared("/pinned/ocr", review_ocr.VERSION_TIMEOUT_S)
        self.assertIsNone(why)
        self.assertEqual(declared["version"], "v1.12.12")  # the fake answer parsed: the call reached the parser
        home = pathlib.Path(seen["cwd"])
        self.assertEqual(home.name, "home")
        self.assertTrue(home.parent.name.startswith("aisef-ocr-version-"),
                        f"temp dir {home.parent.name!r} does not carry the aisef-ocr-version- marker")
        self.assertEqual(seen["env"]["HOME"], str(home))  # the same directory is the child's HOME


if __name__ == "__main__":
    unittest.main()
