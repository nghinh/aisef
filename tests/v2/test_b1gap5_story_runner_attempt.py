"""B1 amendment-6 anchor — the escaped developer range is journaled under its exact name.

The wave-3 follow-up audit (wf_84ecc918) confirmed two REAL_GAPs on story_runner._attempt: the resource name
f"developer {story_id} range" at the RangeEscaped arm (story_runner.py L249) is machine-read evidence — it is the
`resource` field of STORY_RESOURCE_ACQUIRED and of the RESIDUAL release, the `blocked_by` of the held checkout and
scratch, what runtime/repair.py copies into synthetic RESIDUAL events and what the sentinel reports to the next
run's preflight — yet no kill test drove the except arm. This file drives it with the p6 orchestration fixtures
(fake developer, no network) and pins the exact name. Shipped code is correct; these assertions fail only if a
regression reintroduces one of the audited mutations. No product change."""
from __future__ import annotations

import pathlib
import tempfile
import unittest

from aisef2.arch.enums import EventType as T
from aisef2.arch.enums import ObligationRole
from aisef2.orchestrate import story_runner as sr
from aisef2.orchestrate.quality import TestsPolicy
from aisef2.quality import test_execution as te
from aisef2.runtime.process_range import RangeEscaped
from aisef2.runtime.run_scope import RunScope

from tests.v2.p4.world import closed_after
from tests.v2.test_p6_orchestration import (ENV, LIMITS, PROBE, RUN_SPEC, SCAN_SCRIPT, Dev, GitMerger, GitWorkspace,
                                            Rev, Scan, contract, make_repo, obligation, plan_of)


class EscapedDev(Dev):
    """A developer session that leaves a live process its release cannot prove gone (PL-7)."""

    def implement(self, story_id, criteria, checkout):
        self.calls.append((story_id, criteria, checkout))
        raise RangeEscaped("pid 4242 outlived the session release")


class RangeEscapeNamesTheResource(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory(prefix="aisef2-b1gap5-")
        self.addCleanup(self._d.cleanup)
        self.tmp = pathlib.Path(self._d.name)
        self.repo, self.base = make_repo(self.tmp)
        (self.tmp / "ws").mkdir()
        (self.tmp / "merge").mkdir()
        (self.tmp / "run").mkdir()
        self.script = str(self.tmp / "scan.py")
        pathlib.Path(self.script).write_text(SCAN_SCRIPT, encoding="utf-8")
        self.clock = iter(float(n) for n in range(10 ** 6))
        self.run = closed_after(self, RunScope(self.tmp / "run", "run-b1gap5", spec=RUN_SPEC,
                                               clock=lambda: next(self.clock)))
        self.run.begin()
        self.c1, self.s1 = contract("C1", "app.calc:add", [1, 2], 3)

    def test_the_escaped_developer_range_is_journaled_under_its_exact_name(self):
        plan = plan_of(self.base, obligation("BC-C1", self.s1.id, "S1", ObligationRole.INTRODUCE))
        inputs = sr.StoryInputs({self.s1.id: self.s1}, PROBE, ENV, te.DeveloperTests("S1", ("tests/test_s1.py",)),
                                te.DeveloperTests("S1", ("tests/test_other.py",)),
                                te.Dependencies(frozenset(), frozenset({"app", "tests"})), te.UNITTEST)
        adapters = sr.Adapters(EscapedDev(), Rev(), Scan(self.script),
                               GitMerger(self.repo, "main", self.tmp / "merge"), GitWorkspace(self.repo, self.tmp / "ws"))
        try:
            sr.run_story(self.run, plan, "S1", inputs, adapters, sr.Policy(LIMITS, TestsPolicy(True), tool_timeout_s=60))
        except RangeEscaped:
            pass    # the arm re-raises by design; the journal is the assertion surface
        names = [e.data.get("resource") for e in self.run.events if str(e.type) == T.STORY_RESOURCE_ACQUIRED.value]
        self.assertIn("developer S1 range", names,
                      f"the escaped developer range was not journaled under its exact name (saw {names})")


if __name__ == "__main__":
    unittest.main()
