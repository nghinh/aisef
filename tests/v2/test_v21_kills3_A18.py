"""V2.1 mutation survivors, batch A18 — the controller script (`HARNESS`) of `probe.python_callable_v2`, audit batch.

One requirement is pinned here; the other ten survivors of the batch are audited, not tested (see the report).

* the controller is total over what the subject's process can say: a failure of an operation of the subject's process
  is a harness failure that says why, whatever the failure type is called — including when it is called nothing —
  and never an exception out of `observe()` (`Observation` refuses a HARNESS_FAILED without a reason).

Real checkouts run by the real probe, subject process included, as the existing cases of
`tests/v2/test_python_callable_v2.py` do; the fixtures are copied from its idioms (a line on the agent's own channel,
a module that replaces its own `sys.modules` entry), not subclassed.
"""

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import ProbeExecutionStatus  # noqa: E402
from aisef2.probe.protocol import ObservationKind as K, RevisionRef, run_probe  # noqa: E402
from tests.v2 import test_python_callable_v2 as base  # noqa: E402

PRODUCT = {
    "app/__init__.py": "",
    # the agent's own operation fails with a type whose name is '': the module replaces its sys.modules entry with an
    # object whose namespace raises one, and the agent's `vars()` of the imported module is outside its try blocks
    "app/nameless.py": (
        "import sys\n\n"
        "Nameless = type('', (Exception,), {})\n\n\n"
        "class Opaque:\n"
        "    @property\n"
        "    def __dict__(self):\n"
        "        raise Nameless()\n\n\n"
        "sys.modules[__name__] = Opaque()\n\n\n"
        "def f():\n"
        "    return 1\n"
    ),
    # a subject writing the agent's failure answer itself, on the agent's own channel (`__main__.WOUT`), to the
    # import's request number (1): the controller takes the first line of that number as the agent's answer
    "app/forged_failure.py": (
        "import os\nimport __main__\n\n"
        "os.write(__main__.WOUT, b'{\"n\": 1, \"agent_failure\": \"\"}\\n')\n\n\n"
        "def f():\n"
        "    return 1\n"
    ),
}


class NamelessAgentFailure(unittest.TestCase):
    """RFC section 9 / the module doc: an operation the subject's process fails to answer is a harness failure the
    controller reports — HARNESS_FAILED, UNRUNNABLE to the run, routed to the environment — whatever the failure type
    is called. The reason it reports is built from the failure type's name; a type with no name (a class made with
    `type('', ...)`, or a line a subject wrote itself) leaves nothing else to say it by, and `Observation` refuses a
    HARNESS_FAILED that says nothing. The controller therefore says it itself: the observation is still typed and
    still has a reason — not an `InvariantError` out of `observe()`, which would abort the probing of the story on a
    subject's say-so.

    Pins aisef2/probe/python_callable_v2.py::HARNESS/ended [27]."""

    @classmethod
    def setUpClass(cls):
        # the subject's process had this directory as its working directory: on Windows a just-ended member can still
        # hold it for a moment (C2-P2-FINDING-003), so a sharing violation at cleanup must not fail the case
        scratch = tempfile.TemporaryDirectory(prefix="aisef2-kills3-a18-", ignore_cleanup_errors=True)
        cls.addClassCleanup(scratch.cleanup)
        for rel, text in PRODUCT.items():
            path = pathlib.Path(scratch.name, rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        cls.at = RevisionRef(base.SHA, scratch.name)

    def test_a_failure_type_with_no_name_is_still_a_harness_failure_that_says_why(self):
        for locator in ("app.nameless:f", "app.forged_failure:f"):
            s = base.spec(locator, {"returns": 1})
            with self.subTest(locator=locator):
                seen = base.P.observe(s, self.at, base.env())
                self.assertEqual((seen.kind, seen.verdict), (K.HARNESS_FAILED, None), seen)
                self.assertTrue(seen.detail, "a HARNESS_FAILED says why (Observation's own invariant)")
                result = run_probe(base.P, s, self.at, base.env()).result
                self.assertIs(result.status, ProbeExecutionStatus.UNRUNNABLE)
                self.assertTrue(result.detail)


if __name__ == "__main__":
    unittest.main()
