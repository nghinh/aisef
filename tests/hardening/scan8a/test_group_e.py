"""Phase 8A — sites found by the harness itself while resolving the debt (SS-59 lives in test_fault_matrix.py)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import tests  # noqa: E402,F401

from aisef.clients.synthetic import Script, SyntheticClientAdapter  # noqa: E402
from aisef.harness.observe import EvidenceStore  # noqa: E402
from tests.test_implement import ImplementTestCase  # noqa: E402


class TestSS60ADoneStoryHasAFrozenCandidate(ImplementTestCase):
    """SS-60 — a project whose HEAD is unborn: `freeze_candidate` records `candidate:frozen ok=False (cannot read
    HEAD)`; the 1.7.6 gate then scored `evidence matches candidate` NOT_APPLICABLE and the story completed DONE
    bound to no candidate at all. Invariant A.2: a passing verdict names the candidate it graded."""

    def setUp(self):
        super().setUp()
        # back to an unborn HEAD: the fixture's entry commit is what SS-60 is about NOT having
        import shutil
        shutil.rmtree(self.project / ".git")
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)

    # GREEN since F1 (SS-60: typed freeze outcome / session-bound proofs), 2026-09-16
    def test_a_story_whose_freeze_failed_is_not_done(self):
        out = self.implement(SyntheticClientAdapter(Script()))
        ev = EvidenceStore(self.artifacts).read(self.story.id)
        frozen_failed = [e for e in ev.events if e.name == "candidate:frozen" and not e.ok]
        self.assertTrue(frozen_failed, "precondition: the freeze must have failed on an unborn HEAD")
        self.assertFalse(out.done, f"DONE with candidate {ev.candidate!r} after a failed freeze: {out.summary()[:200]}")
        self.assertTrue(any(a.infra and not a.noop for a in out.attempts), "the failed freeze is an environment outcome, not the developer's")
