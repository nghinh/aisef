"""V2.1 mutation survivors, batch T05c: aisef2/app/confine.py::_probe — the measurement's two subprocess calls (the
`bwrap --version` read and the probe itself) and the sleeper the probe leaves.

What a reader of the measurement relies on, and what these tests pin (through `confine.measure`, the entry point a run
and `aisef run --check` use):

* a probe that cannot be started (an exec failure) or that hangs (over its limit) is a RECORDED refusal — a report whose
  problems[0] says the sandbox did not run the probe and names the cause class — never an exception out of measure():
  run.execute stores measure()'s report and refuses the run from it, and `--check` prints ready:false from it; an
  exception ends both in a traceback and loses the report;
* a `bwrap --version` that cannot be read is recorded under `bwrap_version` as an "unavailable" marker that names the
  exception class (a reader of the record — validation/v21/sandbox/linux_guest.py copies it into its evidence — tells a
  version string from a failed read by it), and the measurement goes on;
* the probe's sleeper lives SLEEPER seconds plus a fixed six-digit fraction: a longer one would stay for years on the
  operator's host if the sandbox failed to kill it, and the fraction's fixed width is what keeps one measurement's
  value from being a substring of another's (`_survivors` matches by substring; the sandbox validators find the
  sleeper by its "sleep 120." prefix: validation/v21/sandbox/linux_guest.py, teardown_race.py).

Nothing here runs bubblewrap or any probe: both calls are scripted (the file given as bubblewrap exits 97 and would
write nothing even if a call reached it), and the process table is empty."""

from __future__ import annotations

import itertools
import os
import pathlib
import secrets
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


class Scripted:
    """`subprocess.run` as `confine._probe` sees it. The `bwrap --version` call and the probe call are scripted: each
    script is called with the call's argv and keyword arguments and returns the CompletedProcess to give back or the
    exception to raise (given the argv and the timeout, a TimeoutExpired is the one subprocess.run raises). Everything
    else (the measurement's own git) goes to the real thing."""

    def __init__(self, bwrap: str, version, probe) -> None:
        self.bwrap, self.version, self.probe = bwrap, version, probe
        self.real, self.calls, self.argv = subprocess.run, [], {}

    def __call__(self, argv, *a, **k):
        if isinstance(argv, list) and argv == [self.bwrap, "--version"]:
            kind, script = "version", self.version
        elif isinstance(argv, list) and confine.PROBE in argv:
            kind, script = "probe", self.probe
        else:
            return self.real(argv, *a, **k)
        self.calls.append(kind)
        self.argv[kind] = argv
        out = script(argv, k)
        if isinstance(out, BaseException):
            raise out
        return out


def completed(returncode=0, stdout="", stderr=""):
    return lambda argv, k: subprocess.CompletedProcess(argv, returncode, stdout, stderr)


def raises(exc):
    """A scripted call that raises `exc` — an instance, or a callable (argv, kwargs) -> instance."""
    return lambda argv, k: exc(argv, k) if callable(exc) else exc


def times_out(argv, k):
    return subprocess.TimeoutExpired(argv, k["timeout"])


class Probe(unittest.TestCase):
    """A measurement of a "bubblewrap" whose two calls are scripted; the report, and the calls made."""

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
        self.n = 0

    def assertDidNotRun(self, rep, exit_status):
        """problems[0] refuses a probe that did not run, and says which exit status it ended with (None: it never
        returned one). The identifying elements, not the sentence around them."""
        first = rep["problems"][0]
        self.assertIn("did not run the probe", first)
        self.assertIn(f"exit {exit_status}", first)
        return first

    def measure(self, version=None, probe=None, nonce: int | None = None):
        """(report, Scripted) of one measurement. `version` and `probe` default to a call that returns at once (bubblewrap
        1.2.3; the probe exiting 97 with nothing on its output). `nonce`: what the probe's file names and its sleeper's
        fraction are made from (secrets.token_hex(8), read as hex), else the real one."""
        run = Scripted(str(self.bwrap), version or completed(0, "bubblewrap 1.2.3\n"), probe or completed(97))
        real_hex = secrets.token_hex

        def token_hex(nbytes=None):
            if nonce is not None and nbytes == 8:
                return f"{nonce:016x}"
            return real_hex(nbytes)
        self.n += 1
        with mock.patch.object(subprocess, "run", run), mock.patch.object(confine.secrets, "token_hex", token_hex), \
                mock.patch.object(process_range, "process_table", lambda: {}):
            rep = confine.measure(self.spec, self.tmp / f"m{self.n}", str(self.exe), system="linux", environ=self.environ)
        return rep, run


class TheProbeCannotBeRunOrHangs(Probe):
    """A probe whose own subprocess call raises is a recorded refusal, not an exception out of measure().

    Pins aisef2/app/confine.py::_probe [60, 61, 102, 103, 104, 105]."""

    def assertRecordedRefusal(self, rep, run, *named):
        self.assertEqual(run.calls, ["version", "probe"])        # the measurement reached the probe's own call
        first = self.assertDidNotRun(rep, None)
        for want in named:
            self.assertIn(want, first)
        # nothing was measured, so nothing is judged: no check of the probe's output is invented from the failure
        self.assertEqual(len(rep["problems"]), 1, rep["problems"])
        self.assertEqual(rep["setsid_survivors"], [])
        self.assertEqual(rep["tried"], {})
        self.assertEqual(rep["left_on_host"], [])

    def test_an_exec_failure_of_the_probe_is_a_problem_not_a_crash(self):
        """The wrapper cannot be executed at all (a bubblewrap of another architecture, a text file made executable):
        subprocess raises OSError. The report is returned and problems[0] names the class and the system's reason."""
        rep, run = self.measure(probe=raises(OSError(8, "Exec format error")))
        self.assertRecordedRefusal(rep, run, "OSError", "Exec format error")

    def test_a_probe_over_its_limit_is_a_problem_not_a_crash(self):
        """The sandbox hangs: subprocess raises TimeoutExpired (a SubprocessError, not an OSError), with the command line
        and the probe's limit it was given. The report is returned and problems[0] names the cause class."""
        rep, run = self.measure(probe=raises(times_out))
        self.assertRecordedRefusal(rep, run, "TimeoutExpired")


class TheVersionReadCannotFail(Probe):
    """A `bwrap --version` that raises is recorded as an "unavailable" marker under `bwrap_version`; the measurement
    goes on to the probe and its own verdict.

    Pins aisef2/app/confine.py::_probe [40, 41, 134, 135]."""

    def assertMarked(self, rep, run, cls):
        self.assertEqual(run.calls, ["version", "probe"])        # it went on to the probe
        self.assertIn("bwrap_version", rep)                     # the key a reader looks the version up under
        v = rep["bwrap_version"]
        self.assertTrue(v.startswith("unavailable"), v)         # a failed read is not a version string
        self.assertIn(cls, v)                                   # and says what failed
        self.assertDidNotRun(rep, 97)                           # and the probe's own verdict is the problem

    def test_an_exec_failure_is_marked_unavailable_and_names_the_class(self):
        rep, run = self.measure(version=raises(OSError(8, "Exec format error")))
        self.assertMarked(rep, run, "OSError")

    def test_a_hung_version_call_is_marked_unavailable_and_names_the_class(self):
        rep, run = self.measure(version=raises(times_out))
        self.assertMarked(rep, run, "TimeoutExpired")

    def test_a_version_that_was_read_is_the_tools_own_text(self):
        """The other shape of the field: the first read's stdout, stripped — never the marker."""
        rep, run = self.measure(version=completed(0, "bubblewrap 0.9.0\n"))
        self.assertEqual(run.calls, ["version", "probe"])
        self.assertEqual(rep["bwrap_version"], "bubblewrap 0.9.0")


class TheSleeperHasAFixedWidthDuration(Probe):
    """The probe's `$7`: SLEEPER seconds and a six-digit fraction (zero-padded) made from the nonce, so it is a value no
    other process has, lives about two minutes and is never a prefix of another measurement's value.

    Pins aisef2/app/confine.py::_probe [50, 138]."""

    #: the probe's nonce (secrets.token_hex(8), read as hex) -> the fraction its sleeper carries: the nonce's last six
    #: decimal digits, zero-padded. Written out, not derived, so the test cannot agree with a wrong rule by sharing it.
    FRACTION = {0: "000000", 7: "000007", 99_999: "099999", 100_000: "100000", 123_456: "123456", 999_999: "999999",
                1_000_000: "000000", 1_000_007: "000007", 2**64 - 1: "551615"}

    def sleep_of(self, nonce: int) -> str:
        rep, run = self.measure(nonce=nonce)
        argv = run.argv["probe"]
        at = argv[argv.index(confine.PROBE) + 1:]       # "probe", then $1..$9: $7 is the sleep
        self.assertEqual(at[0], "probe")
        return at[7]

    def test_the_value_is_the_sleeper_and_six_fraction_digits_whatever_the_nonce(self):
        for nonce, fraction in self.FRACTION.items():
            with self.subTest(nonce=nonce):
                sleep = self.sleep_of(nonce)
                self.assertEqual(sleep, f"{confine.SLEEPER}.{fraction}")
                self.assertTrue(confine.SLEEPER <= float(sleep) < confine.SLEEPER + 1, sleep)    # two minutes, not years

    def test_one_measurements_value_is_never_inside_anothers(self):
        """`_survivors` finds a sleeper by `command in pr.command` ("sleep <value>"): measurements running together must
        not report each other's sleepers — no value may be a substring of another's command line."""
        values = [self.sleep_of(n) for n in (7, 70, 700, 7000, 70_000, 700_000)]
        self.assertEqual(len(set(values)), len(values))
        for a, b in itertools.permutations(values, 2):
            with self.subTest(a=a, b=b):
                self.assertNotIn(f"sleep {a}", f"sleep {b}")


if __name__ == "__main__":
    unittest.main()
