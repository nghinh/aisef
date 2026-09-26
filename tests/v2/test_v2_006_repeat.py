"""ARCHITECTURE-EXCEPTION-V2-006, RACE-10: every injected ordering, repeated — 102 real probe observations, a third
with the pump held back, a third with the exit reported before the pump runs, a third with both, each against the
record normal scheduling gives. Zero divergence, zero harness failures (RFC §9.4, F5).
"""

import pathlib
import random
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.probe.protocol import RevisionRef, run_probe  # noqa: E402
from aisef2.product.outcome import Executed  # noqa: E402
from tests.v2.p2.test_python_callable import PRODUCT, SHA, S, P, checkout, env, spec  # noqa: E402
from tests.v2.test_v2_006 import Ordering  # noqa: E402

REPEATS = 102


class Repeated(unittest.TestCase):
    def test_RACE_10_every_ordering_repeated_gives_the_normal_record(self):
        at = RevisionRef(SHA, checkout(PRODUCT))
        s = spec("app.calc:add", {"returns": 3}, {"args": [1, 2]})
        normal = run_probe(P, s, at, env())
        self.assertEqual(normal.result, Executed(S))
        rng = random.Random(6006)
        diverged, failures, exit_first = [], 0, 0
        for i in range(REPEATS):
            kind = i % 3
            ordering = Ordering(delay=rng.uniform(0.01, 0.06) if kind != 1 else 0.0, exit_first=kind != 0)
            with ordering as o:
                got = run_probe(P, s, at, env())
            failures += len(o.failures_after_close)
            exit_first += sum(o.exit_known_first)
            if got.record_digest != normal.record_digest:
                diverged.append((i, kind, got.result))
        self.assertEqual(diverged, [])
        self.assertEqual(failures, 0)
        self.assertEqual(exit_first, 2 * REPEATS // 3)     # the exit really was reported first in every such run


if __name__ == "__main__":
    unittest.main()
