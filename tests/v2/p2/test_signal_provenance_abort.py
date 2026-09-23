"""SIG-PROBE-3 — ARCHITECTURE-EXCEPTION-V2-003: a subject that aborts its own process (RFC §9.3).

Kept apart from test_signal_provenance.py on purpose: `os.abort()` ends the process by SIGABRT, and macOS raises a
crash-reporter dialog for every such exit. This module is in no mutation kill set (SIG-PROBE-4 and the faked ranges
exercise the same code path), so a full suite run aborts a subject twice and a mutation run never does.
"""

import os
import pathlib
import signal
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, MeasurementPoint, ObligationRole, Owner  # noqa: E402
from aisef2.control.routing import route  # noqa: E402
from aisef2.probe.protocol import RevisionRef, run_probe  # noqa: E402
from aisef2.product.outcome import Executed, IndeterminateReason  # noqa: E402
from tests.v2.p2.test_python_callable import P, checkout, env, spec  # noqa: E402

SHA = "89abcdef0123456789abcdef0123456789abcdef"
NCS = IndeterminateReason.NON_CONTROLLER_SIGNAL


@unittest.skipUnless(os.name == "posix", "a process that ends itself by a signal (POSIX; Windows has no signal exit)")
class Abort(unittest.TestCase):
    def test_SIG_PROBE_3_a_subject_that_aborts_is_executed_and_indeterminate(self):
        at = RevisionRef(SHA, checkout({"app/__init__.py": "", "app/abort.py": "import os\n\n\ndef f():\n    os.abort()\n"}))
        s = spec("app.abort:f", {"returns": 1})
        observed = P.observe(s, at, env())
        self.assertEqual((observed.kind.value, observed.verdict), ("NON_CONTROLLER_SIGNAL", None))
        self.assertRegex(observed.detail, rf"^the process ended by signal {int(signal.SIGABRT)} after DISPATCHED, "
                                          r"and this controller's signal ledger is empty: it did not send it$")
        result = run_probe(P, s, at, env()).result
        self.assertEqual(result, Executed(BehaviorVerdict.INDETERMINATE, NCS))
        for point in MeasurementPoint:
            r = route(result, s, point, ObligationRole.INTRODUCE)
            self.assertIsNot(r.failure.owner, Owner.ENVIRONMENT)  # never the environment's, merely for being a signal


if __name__ == "__main__":
    unittest.main()
