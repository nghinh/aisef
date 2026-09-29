"""WP-2.4.1 (C2-P4) — the P7-FINDING-001 bytecode family PYC-1..9 rerun against `probe.python_callable_v2`.

The case bodies are the frozen ones of tests/v2/test_p7_finding_001.py (subclassed, not copied): that module's probe
names are rebound to the second identity for the duration of each case, so the same stale-bytecode states, the same
command-line and cache assertions and the same controlled mutants (`WithoutB`, `WithoutPrefix`) measure this probe.
Kill set for the C2-P4 targets `_harness_argv` and `PythonCallableV2Probe.__init__`.
"""

import pathlib
import re
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.probe import python_callable_v2 as pc2  # noqa: E402
from tests.v2 import test_p7_finding_001 as p7  # noqa: E402

CASE = re.compile(r"test_PYC_(\d+)(b?)_(.*)")


class BytecodeV2(p7.Bytecode):
    def setUp(self):
        rebind = mock.patch.multiple(p7, pc=pc2, PythonCallableProbe=pc2.PythonCallableV2Probe)
        rebind.start()
        self.addCleanup(rebind.stop)
        super().setUp()


for _name in dir(p7.Bytecode):
    _m = CASE.fullmatch(_name)
    if _m and 1 <= int(_m.group(1)) <= 9:
        setattr(BytecodeV2, f"test_FM2_PYC_V2_{_m.group(1)}{_m.group(2)}_{_m.group(3)}", getattr(p7.Bytecode, _name))
    if _name.startswith("test_"):
        setattr(BytecodeV2, _name, None)   # the frozen names run in their own module, not again here


if __name__ == "__main__":
    unittest.main()
