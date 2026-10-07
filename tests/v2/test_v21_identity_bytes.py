"""V2.1: the byte- and text-identity tests of tests/v2/test_v21_identity.py, moved here unchanged (ORD-1, V2.1 runner
audit; docs/v2.1/MUTATION-RUNNER-V2.md §6). Part of the suite; never a mutation kill file (validation/v2/mutation.py
NOT_KILL_FILES). Each method asserts on the probe modules' current bytes, or on source text, so it fails the null mutant
— ast.unparse of the unchanged module — of the modules it reads, and would "kill" every mutant of them whatever the
mutation did: mutation.py's own rule, the one that keeps the compiler_digest tests out of every kill set. The semantic
assertions stay in tests/v2/test_v21_identity.py, which is a kill file."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, bundle_cli  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.calibrations import CALIBRATIONS  # noqa: E402
from aisef2.probe import catalog  # noqa: E402
from aisef2.probe import cli_invocation as ci  # noqa: E402
from aisef2.probe import process_effect as pe  # noqa: E402
from aisef2.probe import python_callable_v2 as pc2  # noqa: E402
from aisef2.probe.calibration import calibration_env, executing  # noqa: E402

LEDGERLOCK_2_0_0 = ROOT / "closure-evidence/v2/release/LEDGERLOCK-PROJECT.json"


class ThreeIdentities(unittest.TestCase):
    def test_the_shipped_calibrations_name_every_class_at_the_bytes_that_run_now(self):
        have = {(r["probe_id"], r["probe_digest"], r["observation_class"]) for r in CALIBRATIONS}
        for e in catalog.CATALOG:
            if e.active:
                for cls in e.classes:
                    self.assertIn((e.probe_id, executing(e.factory), cls), have,
                                  "a probe's bytes changed: run validation/qualification/release_calibration.py --write")

    def test_calibrations_of_other_bytes_admit_nothing(self):
        stale = tuple(dict(r, probe_digest="0" * 64) for r in CALIBRATIONS)
        project = bundle.load(bundle_cli.migrate(json.loads(LEDGERLOCK_2_0_0.read_text(encoding="utf-8")))[0])
        self.assertTrue(R.admit(project, R.calibrations())["admitted"])
        a = R.admit(project, R.calibrations(stale))
        self.assertFalse(a["admitted"])
        self.assertEqual([f["check"] for f in a["failed"]], ["9. probe_calibration"])
        self.assertIn("executing", a["failed"][0]["problems"][0])


@unittest.skipUnless(os.name == "posix", "the venv layout and the marker are POSIX here")
class PthChannel(unittest.TestCase):
    """The reproducer: a `.pth` in an interpreter's site-packages runs under `-I`, never under `-S`; every launch of
    an active probe carries `-S`; and a probe evaluation on an interpreter holding such a file never runs it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)
        self.python = R.probe_interpreter(self.tmp / "venv")
        site = subprocess.run([self.python, "-I", "-c", "import site; print(site.getsitepackages()[0])"],
                              capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()
        self.marker = self.tmp / "pth-ran"
        pathlib.Path(site, "zz_inject.pth").write_text(
            f"import pathlib; pathlib.Path({str(self.marker)!r}).write_text('ran')\n", encoding="utf-8")

    def test_every_active_probe_launch_carries_minus_S(self):
        for mod in (ci, pc2, pe):
            with self.subTest(mod.PROBE_ID):
                src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
                self.assertNotIn('"-I", "-B"', src)                    # no launch without -S: controller, agent, subject
                self.assertGreaterEqual(src.count('"-I", "-S", "-B"'), 2)
                self.assertEqual(mod._harness_argv("/py", "/a", "/c")[1:4], ["-I", "-S", "-B"])

    def test_the_run_gives_the_probes_this_interpreter_and_the_tests_their_own(self):
        self.assertEqual(calibration_env(sys.executable).interpreter, sys.executable)
        src = (ROOT / "aisef2/app/run.py").read_text(encoding="utf-8")
        self.assertIn('env = ExecutionEnv(sys.executable, settings.timeouts_s["probe"]', src)
        self.assertIn("test_interpreter=python)", src)
        self.assertIn('python = probe_interpreter(out / "test-python")', src)


if __name__ == "__main__":
    unittest.main()
