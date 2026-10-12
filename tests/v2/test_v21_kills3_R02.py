"""V2.1 mutation survivors, round 2, batch R02: aisef2/app/confine.py::_probe — what the operator is told when the
probe's own subprocess call fails.

`confine.measure` returns the report `run.execute` stores as RUN.json["confinement"] and refuses the run from
(`problems`), and `aisef run --check` prints. A probe that cannot be started, or that hangs, must be a RECORDED refusal
that says so — never an exception out of `measure` (an exception ends both in a traceback and loses the report). Two
things about that refusal were not pinned by the earlier kill files:

* the exception clause of the probe's call names `subprocess.SubprocessError`, the base of every error of the module,
  not only its timeout: a failure that is neither an OSError nor a TimeoutExpired is the same recorded refusal. The
  earlier files raised TimeoutExpired, which the clause before it takes, so the second half of the tuple was never the
  deciding one;
* a probe that ran past its limit says how long the limit is, with its unit: the exception's own text (which begins
  with the whole command line, the probe script included) is replaced by the module's, so the number and "seconds" are
  all the operator is told about the limit.

The six survivors of this batch that are NOT tested here are the owner's decisions (the file-system types the host
guard exempts: _judge [142, 143, 157, 158]; the locale the probe runs in: measure [40, 49]); the batch report states
the question of each.

Nothing here runs bubblewrap or a probe: both subprocess calls of the measurement are scripted, the file given as
bubblewrap exits 97 and would write nothing even if a call reached it, and the process table is empty."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import confine  # noqa: E402
from aisef2.runtime import process_range  # noqa: E402

#: a "bubblewrap" that runs no command: even a call that reached it (an unscripted one) writes nothing anywhere
RUNS_NOTHING = "#!/bin/sh\nexit 97\n"


class ScriptedRun:
    """`subprocess.run` as `confine._probe` sees it: the `bwrap --version` call answers at once, the probe's call
    (the one whose command line holds the probe script) is given to `probe(argv, kwargs)`, which returns the
    CompletedProcess or the exception to raise. Every other call (the measurement's own git) goes to the real thing."""

    def __init__(self, bwrap: str, probe) -> None:
        self.bwrap, self.probe = bwrap, probe
        self.real, self.probe_calls = subprocess.run, []

    def __call__(self, argv, *a, **k):
        if isinstance(argv, list) and argv == [self.bwrap, "--version"]:
            return subprocess.CompletedProcess(argv, 0, "bubblewrap 1.2.3\n", "")
        if isinstance(argv, list) and confine.PROBE in argv:
            self.probe_calls.append(k)
            out = self.probe(argv, k)
            if isinstance(out, BaseException):
                raise out
            return out
        return self.real(argv, *a, **k)


class ProbeCallFails(unittest.TestCase):
    """A measurement of a "bubblewrap" whose probe call is scripted: the report, and the keyword arguments the probe's
    call was made with."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(os.path.realpath(t.name))
        self.bwrap = self.tmp / "bwrap"
        self.bwrap.write_text(RUNS_NOTHING)
        self.bwrap.chmod(0o755)
        self.exe = self.tmp / "client" / "opencode"
        self.exe.parent.mkdir()
        self.exe.write_text("#!/bin/sh\n")
        self.spec = {"backend": "bwrap", "bwrap": str(self.bwrap), "network": "host", "read_only": []}
        self.environ = {"PATH": "/usr/bin:/bin", "HOME": str(self.tmp / "home")}

    def measure(self, probe) -> tuple[dict, ScriptedRun]:
        run = ScriptedRun(str(self.bwrap), probe)
        with mock.patch.object(subprocess, "run", run), mock.patch.object(process_range, "process_table", lambda: {}):
            rep = confine.measure(self.spec, self.tmp / "m", str(self.exe), system="linux", environ=self.environ)
        self.assertEqual(len(run.probe_calls), 1)       # the measurement reached the probe's own call
        return rep, run

    def refusal(self, rep: dict) -> str:
        """The one problem of a measurement whose probe did not run, and nothing was measured or judged from it."""
        self.assertEqual(len(rep["problems"]), 1, rep["problems"])
        self.assertEqual(rep["tried"], {})
        self.assertEqual(rep["left_on_host"], [])
        return rep["problems"][0]


class AnyFailureOfTheProbeCallIsARecordedRefusal(ProbeCallFails):
    """A failure of the probe's call that is a `subprocess.SubprocessError` but neither a timeout nor an OSError (the
    interpreter raises one when the child's failure report cannot be read: "Bad exception data from child") is
    returned as the refusal "the sandbox did not run the probe (exit None)" naming the exception class and its
    reason, as an exec failure and a timeout are — the run is refused with its record, not ended by a traceback.

    Pins aisef2/app/confine.py::_probe [61]."""

    def test_a_subprocess_error_that_is_not_a_timeout_is_a_problem_not_a_crash(self):
        reason = "Bad exception data from child: b''"
        rep, _ = self.measure(lambda argv, k: subprocess.SubprocessError(reason))
        first = self.refusal(rep)
        self.assertIn("did not run the probe", first)
        self.assertIn("exit None", first)
        self.assertIn("SubprocessError", first)
        self.assertIn(reason, first)


class AProbeOverItsLimitSaysHowLongTheLimitIs(ProbeCallFails):
    """A probe that ran past its limit is refused with the limit it ran past: the number of seconds the call was given
    (`timeout=`), with its unit. The exception's own text, which begins with the whole bubblewrap command line, is not
    what the operator reads; a bare number is not a duration.

    Pins aisef2/app/confine.py::_probe [166]."""

    def test_the_refusal_names_the_limit_and_its_unit(self):
        rep, run = self.measure(lambda argv, k: subprocess.TimeoutExpired(argv, k["timeout"]))
        first = self.refusal(rep)
        self.assertIn("did not run the probe", first)
        self.assertIn("TimeoutExpired", first)
        limit = run.probe_calls[0]["timeout"]
        self.assertIn(f"{limit} seconds", first)


if __name__ == "__main__":
    unittest.main()
