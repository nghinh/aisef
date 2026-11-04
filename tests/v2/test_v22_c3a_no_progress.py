"""ROADMAP-2.2 C3a — feedback.no_progress_note: one line for the retry prompt when the journal shows a story's recent
attempts failed with the same evidence as the one before. A report of the journal (usage.no_progress); it governs no
retry — the failure taxonomy does. Nothing to repeat yet (one failed attempt) ⇒ "". The developer adapter folds the
note into the retry prompt after the kernel's observed failures (adapters.Developer.implement)."""
from __future__ import annotations

import unittest

from aisef2.app import feedback


def _fail(seq, detail, code="CONTRACT_UNSATISFIED"):
    return (seq, "failure/observed", {"story_id": "S1", "code": code, "owner": "DEVELOPER", "detail": detail})


class NoProgressNote(unittest.TestCase):
    def test_two_attempts_with_the_same_evidence_get_the_note(self):
        events = [(1, "story/begin", {"story_id": "S1"}), _fail(2, "the sum is wrong"),
                  (3, "story/retry", {"story_id": "S1"}), (4, "story/begin", {"story_id": "S1"}),
                  _fail(5, "the sum is wrong"), (6, "story/retry", {"story_id": "S1"})]
        note = feedback.no_progress_note(events, "S1")
        self.assertTrue(note.startswith("No progress: 1 attempt(s) failed with the same evidence"), note)
        self.assertIn("governs no retry", note)
        self.assertNotIn("\n", note)                 # one line

    def test_one_failed_attempt_has_no_note(self):
        events = [(1, "story/begin", {"story_id": "S1"}), _fail(2, "the sum is wrong"),
                  (3, "story/retry", {"story_id": "S1"})]
        self.assertEqual(feedback.no_progress_note(events, "S1"), "")

    def test_different_evidence_each_attempt_is_progress_no_note(self):
        events = [(1, "story/begin", {"story_id": "S1"}), _fail(2, "the sum is wrong"),
                  (3, "story/retry", {"story_id": "S1"}), (4, "story/begin", {"story_id": "S1"}),
                  _fail(5, "a different problem"), (6, "story/retry", {"story_id": "S1"})]
        self.assertEqual(feedback.no_progress_note(events, "S1"), "")

    def test_a_committed_attempt_is_not_no_progress(self):
        # a commit is progress, never reported, whatever it observed (usage.no_progress's rule)
        events = [(1, "story/begin", {"story_id": "S1"}), _fail(2, "x"), (3, "story/retry", {"story_id": "S1"}),
                  (4, "story/begin", {"story_id": "S1"}), _fail(5, "x"), (6, "story/commit", {"story_id": "S1"})]
        self.assertEqual(feedback.no_progress_note(events, "S1"), "")


if __name__ == "__main__":
    unittest.main()
