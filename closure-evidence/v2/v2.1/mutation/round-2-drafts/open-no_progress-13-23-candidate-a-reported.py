"""CANDIDATE, NOT PART OF THE SUITE (batch R05, no_progress [13, 23]): what the test would be if the owner rules that
`no_progress` reports a committed attempt that observed failures like any other attempt (the original's behaviour on
the journal shape the writer admits and no producer writes). Passes on the unmutated module; kills 13 and 23."""

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
    def test_it_is_reported_as_repeating_the_attempt_before(self):
        events = [ev("failure/observed", code="TESTS_INADEQUATE", detail="q"), ev("story/retry"),
                  ev("failure/observed", code="TESTS_INADEQUATE", detail="q"), ev("story/commit")]
        self.assertEqual(usage.no_progress(events), [{"story": "S1", "attempts_repeating_the_one_before": [2],
                                                      "failures": ["TESTS_INADEQUATE: q"]}])


if __name__ == "__main__":
    unittest.main()
