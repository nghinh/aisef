"""B03-R3 conf (owner decision, 2026-10-12): the locale of the subprocesses `aisef2.app.confine.measure` collects its
evidence with.

The owner: the measurement's evidence-collecting subprocess runs with locale C, so the text it parses is stable; the
locale used is recorded in the measurement's metadata; the user's session-wide locale and the application under test are
not touched. "An image that has only C/POSIX is not enough to show a difference: use an environment with another locale
or a check of exactly the environment passed down to the subprocess; keep simulated and real evidence apart."

What each class pins, through `confine.measure` (the entry point a run reaches):

* PassedDown          — the environment handed to each subprocess (the probe, `bwrap --version`): LC_ALL=C and LANG=C
                        and nothing else of the LANG / LANGUAGE / LC_* family, the rest of it what the session's own
                        wrapper gives; `os.environ`, and the environment `wrap` gives a REAL session, are untouched;
                        the report says which locale was used. SIMULATION: `subprocess.run` is a recorder.
* AtTheExecBoundary   — the same at the operating system: a stand-in `bwrap` EXECUTABLE saves its own environment; what
                        `subprocess.run` handed to the OS is what it read. POSIX only. A stand-in, not bubblewrap.
* RecordedGuest       — the REAL bubblewrap's environment, saved by a one-line wrapper that `exec`s it, in the Linux
                        guest (validation/v21/sandbox/r3_conf_guest.py locale; docs/v2.1/evidence/sandbox/r3-conf):
                        the same checks on what that run recorded.

NOT measured, anywhere: that a TRANSLATED message of `unshare` / `cat` / the shell differs and would not match
`USERNS_REFUSED` under another locale. The guest has the locales C, C.utf8 and POSIX only (recorded), no message
catalogue of another language is installed there, and nothing here installs one. It would need an image with a
non-English locale generated and its util-linux/coreutils catalogues present under the sandbox's /usr, then the same
`unshare --user true` probe run under LC_ALL=de_DE.UTF-8 (the refusal text no longer matching) and under C."""

from __future__ import annotations

import json
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

#: a caller whose environment carries four other locales (the owner's check)
CALLER = {"LANG": "vi_VN.UTF-8", "LC_ALL": "de_DE.UTF-8", "LC_MESSAGES": "fr_FR.UTF-8", "LANGUAGE": "ja"}
C = {"LC_ALL": "C", "LANG": "C"}
RUNS_NOTHING = "#!/bin/sh\nexit 97\n"


def family(env: dict) -> dict:
    """The locale family of an environment: LANG, LANGUAGE and every LC_*."""
    return {k: v for k, v in env.items() if k.startswith(("LANG", "LC_"))}


class Case(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(os.path.realpath(t.name))
        self.home = self.tmp / "home"
        (self.home / ".config" / "opencode").mkdir(parents=True)
        self.exe = self.tmp / "client" / "opencode"
        self.exe.parent.mkdir()
        self.exe.write_text("#!/bin/sh\n")
        self.bwrap = self.tmp / "bwrap"
        self.bwrap.write_text(RUNS_NOTHING)
        self.bwrap.chmod(0o755)
        self.spec = {"backend": "bwrap", "bwrap": str(self.bwrap), "network": "host", "read_only": []}
        self.environ = {"PATH": "/usr/bin:/bin", "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / ".config"),
                        **CALLER}


@unittest.skipUnless(os.name == "posix", "bubblewrap's stand-in is a POSIX file the process starts")
class PassedDown(Case):
    """Requirement: every subprocess `measure` starts to collect evidence — the probe and `bwrap --version` — gets
    LC_ALL=C and LANG=C and nothing else of the locale family, whatever the caller's environment holds; the rest of its
    environment is what a session's own wrapper gives; the caller's `os.environ` is left as it was; the locale a
    session gets is not the measurement's (`wrap` is shared with real sessions); the report records the locale used."""

    def measured(self, environ=None):
        calls, real = [], subprocess.run

        def run(argv, *a, **k):
            if isinstance(argv, list) and argv[:1] == [str(self.bwrap)]:
                calls.append((argv, k.get("env")))
                return subprocess.CompletedProcess(argv, 97, "bubblewrap 0.12.0\n" if argv[1:] == ["--version"] else "", "")
            return real(argv, *a, **k)        # git: the measurement's own repository and worktree
        before = dict(os.environ)
        with mock.patch.object(subprocess, "run", run):
            rep = confine.measure(self.spec, self.tmp / "run" / "confinement", str(self.exe), system="linux",
                                  environ=self.environ if environ is None else environ)
        self.assertEqual(dict(os.environ), before)
        return rep, calls

    def test_the_probe_and_the_version_query_get_the_c_locale_and_nothing_else_of_the_family(self):
        rep, calls = self.measured()
        self.assertEqual([argv[1:] == ["--version"] for argv, _ in calls], [True, False])
        for argv, env in calls:
            with self.subTest(call=argv[1:2]):
                self.assertEqual(family(env), C)
                self.assertNotIn("LC_MESSAGES", env)
                self.assertNotIn("LANGUAGE", env)

    def test_the_rest_of_the_environment_is_what_the_session_wrapper_gives(self):
        """What the probe is started with besides the locale is the wrapper's own result for the caller's PATH, HOME and
        XDG_CONFIG_HOME: nothing of the caller's other variables, nothing added."""
        _, calls = self.measured()
        [probe_env] = [env for argv, env in calls if argv[1:] != ["--version"]]
        self.assertEqual({k: v for k, v in probe_env.items() if k not in C}, {
            "PATH": "/usr/bin:/bin", "HOME": confine.HOME, "TMPDIR": "/tmp", "XDG_DATA_HOME": f"{confine.HOME}/.local/share",
            "XDG_STATE_HOME": f"{confine.HOME}/.local/state", "XDG_CACHE_HOME": f"{confine.HOME}/.cache",
            "XDG_CONFIG_HOME": str(self.home / ".config")})

    def test_a_session_keeps_its_own_locale(self):
        """`wrap` is the sessions' too: it must not carry the measurement's locale."""
        _, env = confine.wrap(self.spec, ["/bin/sh"], self.environ, str(self.tmp / "ws"), str(self.exe), system="linux")
        self.assertEqual(family(env), CALLER)

    def test_the_report_says_which_locale_the_measurement_used(self):
        rep, _ = self.measured()
        self.assertEqual(rep["locale"], C)
        self.assertEqual(confine.LOCALE, C)

    def test_what_the_report_says_is_what_was_passed_down(self):
        """The record is read from the environment the subprocesses got, not from the constant: with another locale
        the measurement's, both change together."""
        other = {"LC_ALL": "C.UTF-8", "LANG": "C.UTF-8"}
        with mock.patch.object(confine, "LOCALE", other):
            rep, calls = self.measured()
        self.assertEqual(rep["locale"], other)
        for _, env in calls:
            self.assertEqual(family(env), other)

    def test_a_caller_without_any_locale_gets_the_same(self):
        rep, calls = self.measured({k: v for k, v in self.environ.items() if k not in CALLER})
        self.assertEqual(rep["locale"], C)
        for _, env in calls:
            self.assertEqual(family(env), C)

    def test_only_the_session_wrappers_environment_is_a_source_of_the_measurements(self):
        """A locale-family variable inside the environment the wrapper built (a future key kept for the session) is
        dropped for the measurement's subprocesses too: the probe's `LC_*` are the measurement's alone."""
        calls, real = [], subprocess.run

        def run(argv, *a, **k):
            if isinstance(argv, list) and argv[:1] == [str(self.bwrap)]:
                calls.append(k.get("env"))
                return subprocess.CompletedProcess(argv, 97, "", "")
            return real(argv, *a, **k)
        real_wrap = confine.wrap

        def wrap_with_more(*a, **k):
            argv, env = real_wrap(*a, **k)
            return argv, {**env, "LC_CTYPE": "ja_JP.UTF-8", "LANGUAGE": "ja", "LANG": "ja_JP.UTF-8"}
        with mock.patch.object(subprocess, "run", run), mock.patch.object(confine, "wrap", wrap_with_more):
            confine.measure(self.spec, self.tmp / "run" / "confinement", str(self.exe), system="linux", environ=self.environ)
        self.assertEqual(len(calls), 2)
        for env in calls:
            self.assertEqual(family(env), C)


@unittest.skipUnless(os.name == "posix", "the stand-in is a POSIX shell script and `env` a POSIX tool")
class AtTheExecBoundary(Case):
    """Requirement: what the operating system hands the bubblewrap process is the same: a stand-in executable saves its
    own environment (`env`) and exits as a bubblewrap that runs nothing does."""

    def test_the_environment_the_stand_in_bubblewrap_received(self):
        saved = self.tmp / "saved"
        saved.mkdir()
        self.bwrap.write_text(f'#!/bin/sh\n/usr/bin/env > "{saved}/$$.env"\nexit 97\n')
        before = dict(os.environ)
        rep = confine.measure(self.spec, self.tmp / "run" / "confinement", str(self.exe), system="linux", environ=self.environ)
        self.assertEqual(dict(os.environ), before)
        files = sorted(saved.glob("*.env"))
        self.assertEqual(len(files), 2, [p.name for p in files])        # `--version`, then the probe
        for i, f in enumerate(files):          # (the file names hold a process id: never a label of a subtest)
            env = dict(line.split("=", 1) for line in f.read_text().splitlines() if "=" in line)
            with self.subTest(call=i):
                self.assertEqual(family(env), C)
        self.assertEqual(rep["locale"], C)
        self.assertEqual(rep["problems"][0].split(":")[0], "the sandbox did not run the probe (exit 97)")


class RecordedGuest(unittest.TestCase):
    """Requirement: the same of the REAL bubblewrap's environment, as recorded in the Linux guest."""

    RECORD = ROOT / "docs" / "v2.1" / "evidence" / "sandbox" / "r3-conf" / "locale-X1.json"

    def test_the_environment_the_real_bubblewrap_received(self):
        rec = json.loads(self.RECORD.read_text(encoding="utf-8"))["record"]
        self.assertEqual(rec["caller"], CALLER)
        self.assertEqual(len(rec["bubblewrap_calls"]), 2)        # `--version`, then the probe
        for call in rec["bubblewrap_calls"]:
            self.assertEqual(call["locale_family"], C)
            self.assertFalse({"LANGUAGE", "LC_MESSAGES"} & set(call["keys"]))
        self.assertEqual(rec["report"]["locale"], C)
        self.assertTrue(rec["os_environ_unchanged"])

    def test_the_measurement_that_ran_for_real_accepted_the_session_and_the_guest_has_no_other_locale(self):
        rec = json.loads(self.RECORD.read_text(encoding="utf-8"))["record"]
        self.assertEqual(rec["report"]["problems"], [])        # its refusal of a further user namespace read under C
        self.assertEqual(rec["report"]["bwrap_version"], "bubblewrap 0.12.0")
        self.assertEqual(rec["locales_in_the_guest"], ["C", "C.utf8", "POSIX"])     # a translation is NOT measured


if __name__ == "__main__":
    unittest.main()
