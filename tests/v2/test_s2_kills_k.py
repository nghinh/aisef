"""V2.0-S2 mutation: cases for what final round K found (owner ruling 'MUTATION WORKER HANDOFF' and its follow-ups,
2026-10-04). A file of its own, named only in the kill sets of the targets it was written for, so the round-K results of
every other target keep a byte-identical kill-test closure (validation/qualification/s2_mutation_record.py).

* client.wait_within L153 'And swapped' and cli_invocation AGENT/send L27 "'\\n' emptied" — a case earlier in
  tests/v2/test_s2_kills.py reaches the mutant first and waits until the runner's clock ends it (wait_within's loop never
  ends once the process has exited; without the newline a reader waiting for the agent's line waits for ever), and a
  kill by the clock alone does not pass. This file runs FIRST in those two kill sets: ClientWaitWithin and AgentSend,
  imported, fail at once.
* bundle.Project.order L64 'sorted() -> list()' — the stories would run in the iteration order of a set of strings,
  which string hashing randomizes per process: the existing cases killed it only when that order was not name order."""

from __future__ import annotations

import pathlib
import sys
import types
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from aisef2.app import bundle  # noqa: E402
from tests.v2.test_s2_kills import AgentSend  # noqa: E402,F401  cli_invocation AGENT/send L27
from tests.v2.test_s2_kills import ClientWaitWithin  # noqa: E402,F401  client.wait_within L153


class AppProjectOrder(unittest.TestCase):
    """aisef2.app.bundle.Project.order L64: independent stories run in name order, whatever order this process's string
    hashing gives their set — the names are chosen so that the two orders differ here."""

    def test_ties_are_broken_by_name_not_by_hash_order(self):
        for k in range(100):
            names = [f"story-{k}-{c}" for c in "fbdaec"]
            if list({n for n in names}) != sorted(names):     # the set order.order() would follow without sorted()
                break
        else:
            self.fail("no name set whose hash order differs from name order")
        project = types.SimpleNamespace(plan=types.SimpleNamespace(obligations=tuple(types.SimpleNamespace(story_id=n) for n in names)),
                                        stories={n: {"depends_on": []} for n in names})
        self.assertEqual(bundle.Project.order(project), sorted(names))


if __name__ == "__main__":
    unittest.main()
