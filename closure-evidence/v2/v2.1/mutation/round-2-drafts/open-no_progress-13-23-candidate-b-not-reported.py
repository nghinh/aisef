"""CANDIDATE, NOT PART OF THE SUITE (batch R05, no_progress [13, 23]): what the test would be if the owner rules that a
committed attempt is not a "failed attempt" (the docstring's literal reading: "consecutive failed attempts with the
same failures"). FAILS on the unmutated module: it is the test that would go with dropping "story/commit" from
usage.py:130 (a product change), after which mutants 13 and 23 no longer exist."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import usage  # noqa: E402


def ev(kind, **data):
    return {"type": kind, "data": {"story_id": "S1", **data}}


class CommittedAttemptThatObservedTheSameFailures(unittest.TestCase):
    def test_it_is_not_a_failed_attempt_and_is_not_reported(self):
        events = [ev("failure/observed", code="TESTS_INADEQUATE", detail="q"), ev("story/retry"),
                  ev("failure/observed", code="TESTS_INADEQUATE", detail="q"), ev("story/commit")]
        self.assertEqual(usage.no_progress(events), [])


if __name__ == "__main__":
    unittest.main()
