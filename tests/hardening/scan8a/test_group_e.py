"""Phase 8A — sites found by the harness itself while resolving the debt (SS-59 lives in test_fault_matrix.py)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import tests  # noqa: E402,F401

from aisef.clients.synthetic import Script, SyntheticClientAdapter  # noqa: E402
from aisef.harness.observe import EvidenceStore  # noqa: E402
from tests.test_implement import ImplementTestCase  # noqa: E402


class TestSS60ADoneStoryHasAFrozenCandidate(ImplementTestCase):
    """SS-60 — `ImplementTestCase` has no entry commit, so `freeze_candidate` records `candidate:frozen ok=False
    (cannot read HEAD)`; the gate then scores `evidence matches candidate` NOT_APPLICABLE and the story completes
    DONE bound to no candidate at all. Invariant A.2: a passing verdict names the candidate it graded."""

    @unittest.expectedFailure   # SS-60 — DONE with candidate "" (found by group A's fixture check, 2026-09-16)
    def test_a_story_whose_freeze_failed_is_not_done(self):
        out = self.implement(SyntheticClientAdapter(Script()))
        ev = EvidenceStore(self.artifacts).read(self.story.id)
        frozen_failed = [e for e in ev.events if e.name == "candidate:frozen" and not e.ok]
        self.assertTrue(frozen_failed, "precondition: the freeze must have failed on this fixture")
        self.assertFalse(out.done and not ev.candidate, f"DONE with candidate {ev.candidate!r} after a failed freeze")
