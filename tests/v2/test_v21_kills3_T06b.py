"""V2.1 mutation survivors of aisef2/app/confine.py::measure, batch T06b: what the measurement's report states, and what
environment its probe is given.

`measure` returns the dict `run.execute` stores as RUN.json["confinement"] (and raises RunRefused from its problems) and
`aisef run --check` prints. No code outside confine.py reads the header back (run.py reads `problems`, cli.py prints the
dict), so its readers are the operator of a refused run and the evidence harness (validation/v21/sandbox/linux_guest.py
`summary` reads bwrap_sha256; docs/v2.1/SANDBOX-LINUX.md §7 relies on it): what must hold is what the report is for,
stated from the call's own inputs.

Every measurement here runs under a "bubblewrap" that runs nothing (exit 97 at once) or is refused before any process
starts, in the test's own directory. The tests that build a repository and a client (ReportHeader, BinaryIdentity,
MeasureEnvironment) compare the host before and after (test_v21_confine.host_view); the uid tests are refused on the
platform check, before anything is made."""

from __future__ import annotations

import hashlib
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import confine  # noqa: E402
from tests.v2 import isolated_git  # noqa: E402
from tests.v2 import test_v21_confine as base  # noqa: E402 — the module, so its tests are not collected again

#: a "bubblewrap" that runs nothing; its bytes are the test's, so the digest the report names has an oracle
RUNS_NOTHING = base.RUNS_NOTHING.encode("utf-8")


class _Measured(unittest.TestCase):
    """The test's own directory: a "bubblewrap" file, a client, a repository with a worktree of it (a session's), the
    operator's configuration directories (HOME/.config/opencode and a $XDG_CONFIG_HOME/opencode), the operator's
    environment, and the setting. Not a test itself."""

    BWRAP = RUNS_NOTHING

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(os.path.realpath(t.name))
        self.addCleanup(base.host_unchanged, base.host_view())
        self.bwrap = self.tmp / "bwrap"
        self.bwrap.write_bytes(self.BWRAP)
        self.bwrap.chmod(0o755)
        self.home, self.xdg = self.tmp / "home", self.tmp / "xdg"
        (self.home / ".config" / "opencode").mkdir(parents=True)
        (self.xdg / "opencode").mkdir(parents=True)
        self.repo = self.tmp / "out" / "repo"
        self.repo.mkdir(parents=True)
        isolated_git.git(self.repo, "init", "-q", "-b", "main")
        isolated_git.git(self.repo, "commit", "-q", "--allow-empty", "-m", "base")
        self.ws = self.tmp / "out" / "work" / "ws" / "wt-S1"
        isolated_git.git(self.repo, "worktree", "add", "-q", "--detach", str(self.ws))
        self.exe = self.tmp / "client" / "opencode"
        self.exe.parent.mkdir()
        self.exe.write_text("#!/bin/sh\n")
        self.ro = [self.tmp / "ro-a", self.tmp / "ro-b"]
        for p in self.ro:
            p.mkdir()
        self.spec = {"backend": "bwrap", "bwrap": str(self.bwrap), "network": "host", "read_only": [str(p) for p in self.ro]}
        self.environ = {"PATH": f"{self.tmp / 'tools'}{os.pathsep}/usr/bin{os.pathsep}/bin", "HOME": str(self.home),
                        "XDG_CONFIG_HOME": str(self.xdg), "LANG": "C", "AISEF_SECRET": "an unrelated variable"}
        self.n = 0

    def measure(self, spec=None, exe="", system="linux", environ=None):
        """confine.measure of the setting in a new run-directory name, with the run's repository."""
        self.n += 1
        return confine.measure(self.spec if spec is None else spec, self.tmp / f"m{self.n}",
                               str(self.exe) if exe == "" else exe, self.repo, system=system,
                               environ=self.environ if environ is None else environ)


class ReportHeader(_Measured):
    """The report states the setting it measured and where — backend, bubblewrap, network, the operator's `read_only`
    paths, the client, the system — on a refusal as much as after a probe: on a refused run it is the whole record of
    what was asked (the problem text names only what was missing, or only the host).

    Pins aisef2/app/confine.py::measure [0, 1, 3, 5, 16, 17, 19, 21] (the header literal) and [42] (the refusal's
    `{**rep, "problems": ...}` keeps it)."""

    def says(self, rep: dict, spec: dict, client, system: str) -> None:
        self.assertEqual({k: rep.get(k) for k in confine.KEYS}, spec)
        self.assertEqual((rep.get("client"), rep.get("system")), (client, system))

    def refused(self, rep: dict) -> dict:
        """`rep` is a measurement refused before its probe: one problem, nothing observed."""
        self.assertEqual(len(rep["problems"]), 1, rep["problems"])
        self.assertNotIn("inside", rep)
        return rep

    def test_a_refusal_still_says_what_was_asked_and_where(self):
        missing = dict(self.spec, read_only=[*self.spec["read_only"], str(self.tmp / "gone")])
        for why, spec, exe, system in (
                ("not Linux", self.spec, str(self.exe), "darwin"),
                ("bubblewrap is a directory", dict(self.spec, bwrap=str(self.tmp)), str(self.exe), "linux"),
                ("a read_only path is missing", missing, str(self.exe), "linux"),
                ("no client", self.spec, None, "linux")):
            with self.subTest(why=why):
                rep = self.refused(self.measure(spec, exe, system))
                self.says(rep, spec, exe, system)

    @unittest.skipUnless(os.name == "posix", "the 'bubblewrap' is a POSIX script and the process table is read with ps")
    def test_a_measurement_that_reached_its_probe_says_it_too(self):
        rep = self.measure()
        self.assertIn("inside", rep)       # the probe was invoked (a "bubblewrap" that runs nothing: refused for that)
        self.says(rep, self.spec, str(self.exe), "linux")


class BinaryIdentity(_Measured):
    """The report names the bubblewrap whose boundary it claims by the sha256 of the file's bytes — a version string
    does not identify a build; SANDBOX-LINUX.md §7 and the evidence harness read it.

    Pins aisef2/app/confine.py::measure [53]."""

    BWRAP = RUNS_NOTHING + b"# the bytes of this build, and no other\n"

    @unittest.skipUnless(os.name == "posix", "the 'bubblewrap' is a POSIX script and the process table is read with ps")
    def test_it_is_the_digest_of_the_files_bytes(self):
        rep = self.measure()
        self.assertIn("inside", rep)
        self.assertEqual(rep.get("bwrap_sha256"), hashlib.sha256(self.BWRAP).hexdigest())


class _Os:
    """`os` as confine sees it: every attribute the real one's, except getuid — the one given, or none (Windows)."""

    def __init__(self, **own) -> None:
        vars(self).update(own)

    def __getattr__(self, name: str):
        if name == "getuid":
            raise AttributeError(name)
        return getattr(os, name)


class OperatorUid(unittest.TestCase):
    """The report holds the operator's uid where the platform has one — operator_can (os.access for the operator's real
    uid) has no subject without it — and None where it has none: a host without os.getuid (Windows) still gets the
    "Linux-only" refusal from `aisef run --check`, never a traceback.

    Pins aisef2/app/confine.py::measure [6, 22, 23, 45]."""

    def measured(self, standin=None) -> dict:
        with tempfile.TemporaryDirectory() as t, mock.patch.object(confine, "os", standin or os):
            return confine.measure(base.SPEC, pathlib.Path(t) / "m", None, system="win32", environ={})

    def test_it_is_what_the_platform_says(self):
        self.assertEqual(self.measured(_Os(getuid=lambda: 4242)).get("operator_uid"), 4242)

    @unittest.skipUnless(hasattr(os, "getuid"), "no os.getuid on this platform")
    def test_it_is_the_operators_real_uid_on_posix(self):
        self.assertEqual(self.measured().get("operator_uid"), os.getuid())

    def test_a_host_without_getuid_is_refused_not_crashed(self):
        rep = self.measured(_Os())      # raises AttributeError if the uid is asked of a platform that has none
        self.assertIn("operator_uid", rep)
        self.assertIsNone(rep["operator_uid"])
        self.assertIn("win32", rep["problems"][0])


class MeasureEnvironment(_Measured):
    """The probe runs under the session's own wrapper with the session's own PATH, HOME and XDG_CONFIG_HOME — the
    operator's values — and nothing else of the operator's environment (the locale, LANG, is the one other name the
    measurement keeps; whether it must be is left open: mutants 40 and 49): the tools it resolves are the run's, and the
    wrapper binds $XDG_CONFIG_HOME/opencode (SANDBOX-LINUX.md §2) exactly as a session's does for the same environment.

    Pins aisef2/app/confine.py::measure [37, 46] (PATH) and [39, 48] (XDG_CONFIG_HOME)."""

    def captured(self) -> tuple[dict, list[str], dict]:
        """(the environment `wrap` was given, its command line, the environment it returns — the probe's), the
        measurement stopped at the wrapper."""
        seen, real = [], confine.wrap

        def spy(*a, **k):
            r = real(*a, **k)
            seen.append((dict(a[2]), *r))
            raise confine.Unavailable("captured, not run")
        with mock.patch.object(confine, "wrap", spy):
            rep = self.measure()
        self.assertEqual(rep["problems"], ["captured, not run"])
        [got] = seen
        return got

    def test_the_probe_gets_the_runs_path_and_configuration_and_nothing_else_of_the_operators(self):
        given, _, inside = self.captured()
        for k in ("PATH", "HOME", "XDG_CONFIG_HOME"):
            self.assertEqual(given.get(k), self.environ[k], k)
        self.assertNotIn("AISEF_SECRET", given)
        self.assertNotIn("AISEF_SECRET", inside)
        self.assertLessEqual(set(given), {"PATH", "HOME", "XDG_CONFIG_HOME", "LANG"})
        self.assertEqual(inside.get("PATH"), self.environ["PATH"])        # what the probe's shell resolves its tools by
        self.assertEqual(inside.get("XDG_CONFIG_HOME"), str(self.xdg))    # its opencode/ directory, read-only

    def test_the_measured_wrapper_binds_the_configuration_a_session_binds(self):
        _, argv, _ = self.captured()
        session_env = {k: v for k, v in self.environ.items() if k != "AISEF_SECRET"}
        session, _ = confine.wrap(self.spec, [str(self.exe), "run"], session_env, str(self.ws), str(self.exe), system="linux")
        self.assertIn(str(self.xdg / "opencode"), base.ro_binds(session))
        self.assertIn(str(self.xdg / "opencode"), base.ro_binds(argv))
        self.assertNotIn(str(self.home / ".config" / "opencode"), base.ro_binds(argv))
        self.assertEqual(base.ro_binds(argv), base.ro_binds(session))


if __name__ == "__main__":
    unittest.main()
