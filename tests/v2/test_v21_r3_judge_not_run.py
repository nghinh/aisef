"""B-03 round 3 — `confine._judge`: a probe try that reported no exit status did not run, whatever text it carries.

`_judge`'s docstring: what the measurement shows that confinement must not allow "— or did not measure (a check that
could not run is a problem, never a pass)". A probe try is a check that ran only when the probe wrote its exit status
(`m rc $?`), and that status is what says what its text means: the kernel's wording of a refusal counts as a refusal
only with the exit status of a command that ran and failed (test_v21_kills3_A06 pins that for 127, whose loader text
is the same). A try WITHOUT a status is not a refusal, a pass or a readable canary: it is a check that did not run.

How a try loses its status in the real probe: the marker `@@aisef-confine rc N` is written by `printf`, at the start of
a line only when the text before it ended with a line feed. A command that ends its output without one (the canary
file, an `unshare` of another build) glues the marker to its last line, `_sections` no longer sees a marker, and the
try is left open. Before this file's change an open try was a bare list: with at most one body line `_probe` raised
ValueError at `rep["tried"]` (a traceback, not a refusal), and with exactly two body lines `_judge` unpacked them as an
exit status and a text and could judge the user-namespace check from them.

campaign 5 also left `rc in (None, 127)` -> `rc in (127,)` (`_judge` [100]) SURVIVED, for the same reason: the only way
to reach the None member by the producer was `_judge`'s own default.
"""

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
from tests.v2 import v21_r3_conf_rows as rows  # noqa: E402

WS = pathlib.PurePosixPath("/w/ws")
TOKEN = "TOKEN-0123456789abcdef"
UNMEASURED = "no refusal of a further user namespace was measured"
DID_NOT_RUN = "reported no exit status: the check did not run"
M = confine.MARK
REFUSALS = ("unshare: unshare failed: No space left on device", "unshare: unshare failed: Operation not permitted",
            "No space left on device", "Operation not permitted")


def clean_report() -> dict:
    """A measurement `_judge` finds nothing to say about (the workspace the only host-backed mount)."""
    return {"network": "host", "created_outside_workspace": {"kernel": False}, "setsid_survivors": [],
            "host_mounts": rows.HOST,
            "inside": {"capabilities": dict.fromkeys(("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"), "0000000000000000"),
                       "no_new_privs": "1", "namespaces": dict.fromkeys(("user", "pid", "ipc", "uts", "mnt"), "own"),
                       "routed_interfaces": [], "home_listing": [], "unix_sockets": [],
                       "mounts": [rows.mount("/"), {"at": str(WS), "access": "rw", "fs": "ext4"}],
                       "mount_targets": [str(WS)]}}


def tries_of(**changed) -> dict:
    tries = {"read_canary": (1, "cat: canary: No such file or directory"), "workspace": (0, "ok"),
             "read_git_directory": (0, "ref: refs/heads/main"), "user_namespace": (1, REFUSALS[0])}
    tries.update(changed)
    return tries


def judged(**changed) -> list[str]:
    return confine._judge(clean_report(), TOKEN, "", tries_of(**changed), "/nonexistent", WS)


def unmeasured(problems: list[str]) -> list[str]:
    return [p for p in problems if p.startswith(UNMEASURED)]


class AnExitStatusIsWhatMakesATextARefusal(unittest.TestCase):
    def test_the_clean_report_is_clean_and_a_refusal_with_its_status_is_not_a_problem(self):      # the controls
        self.assertEqual(judged(), [])
        for text in REFUSALS:
            with self.subTest(text=text):
                self.assertEqual(judged(user_namespace=(1, text)), [])

    def test_an_unshare_that_ran_and_said_something_else_is_not_a_refusal(self):
        for rc, text in ((1, "Segmentation fault"), (1, ""), (2, "unshare: unrecognized option '--user'"), (126, "x")):
            with self.subTest(rc=rc, text=text):
                self.assertEqual(len(unmeasured(judged(user_namespace=(rc, text)))), 1)

    def test_no_exit_status_is_never_a_refusal_whatever_the_text_beside_it_says(self):
        for text in ("",) + REFUSALS:
            with self.subTest(text=text):
                problems = judged(user_namespace=(None, text))
                [said] = unmeasured(problems)
                self.assertIn("None", said)
                self.assertTrue(any("user_namespace" in p and DID_NOT_RUN in p for p in problems), problems)

    def test_a_try_that_was_never_recorded_is_the_same_problem(self):
        tries = tries_of()
        del tries["user_namespace"]
        problems = confine._judge(clean_report(), TOKEN, "", tries, "/nonexistent", WS)
        self.assertEqual(len(unmeasured(problems)), 1, problems)


class AnyTryThatDidNotReportIsNamed(unittest.TestCase):
    """Not only the user-namespace one: a canary try without a status is not "the canary was unreadable", and a
    workspace or git-directory try without one is not a pass."""

    def test_each_try_without_a_status_is_a_problem_that_names_it(self):
        for name in ("read_canary", "workspace", "read_git_directory", "user_namespace", "setsid"):
            with self.subTest(name=name):
                problems = judged(**{name: (None, "ok" if name == "workspace" else "")})
                self.assertTrue(any(name in p and DID_NOT_RUN in p for p in problems), problems)

    def test_several_are_named_together_in_one_problem_each_as_a_token_of_its_own(self):
        problems = judged(read_canary=(None, ""), setsid=(None, ""))
        [said] = [p for p in problems if DID_NOT_RUN in p]
        for name in ("read_canary", "setsid"):      # the operator reads the names: one must not run into the next
            self.assertRegex(said, rf"(?<![A-Za-z_]){name}(?![A-Za-z_])")


class AMarkerThatRanIntoItsTextLeavesATryWithoutAStatus(unittest.TestCase):
    """The producer itself, `_sections`, on probe output as `printf` writes it when a command ended without a line
    feed: the try is reported as one that did not report, never as a pass and never as a crash."""

    def probe_output(self, user_namespace_lines: list[str]) -> str:
        return "\n".join([f"{M}try read_canary", "cat: canary: No such file or directory", f"{M}rc 1",
                          f"{M}try workspace", "ok", f"{M}rc 0",
                          f"{M}try read_git_directory", "ref: refs/heads/main", f"{M}rc 0",
                          f"{M}try user_namespace", *user_namespace_lines, f"{M}end"]) + "\n"

    def judged_from(self, out: str):
        _, _, tries = confine._sections(out)
        return tries, confine._judge(clean_report(), TOKEN, out, tries, "/nonexistent", WS)

    def test_one_line_of_text_with_the_marker_glued_to_it(self):
        tries, problems = self.judged_from(self.probe_output([f"{REFUSALS[0]}{M}rc 1"]))
        self.assertEqual(tries["user_namespace"], (None, f"{REFUSALS[0]}{M}rc 1"))
        self.assertIn(REFUSALS[0], tries["user_namespace"][1])
        self.assertTrue(any("user_namespace" in p and DID_NOT_RUN in p for p in problems), problems)
        self.assertEqual(len(unmeasured(problems)), 1, problems)

    def test_two_lines_of_text_are_not_read_as_a_status_and_a_text(self):
        """Before the change: `rc, said = ['first', 'second']`, and a refusal wording in the second line passed."""
        tries, problems = self.judged_from(self.probe_output(["unshare: first line", f"{REFUSALS[1]}{M}rc 1"]))
        self.assertIsNone(tries["user_namespace"][0])
        # its text is what the probe wrote, line by line, as a try that reported has it
        self.assertEqual(tries["user_namespace"], (None, f"unshare: first line\n{REFUSALS[1]}{M}rc 1"))
        self.assertNotEqual(problems, [])
        self.assertEqual(len(unmeasured(problems)), 1, problems)

    def test_a_try_that_reported_is_left_as_it_was(self):
        tries, problems = self.judged_from(self.probe_output([REFUSALS[0], f"{M}rc 1"]))
        self.assertEqual(tries["user_namespace"], (1, REFUSALS[0]))
        self.assertEqual(problems, [])


@unittest.skipUnless(os.name == "posix", "bubblewrap's stand-in is a POSIX file the process starts")
class TheMeasurementRefusesInsteadOfCrashing(unittest.TestCase):
    """Through `confine.measure` (the real `_probe`, its subprocess answered with the output of a probe whose
    `unshare` text had no line feed): a refusal with the check named, `rep["tried"]` recording an exit of None."""

    def test_a_probe_whose_last_try_never_reported_is_refused_with_that_try_named(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(os.path.realpath(t))
            home = tmp / "home"
            (home / ".config" / "opencode").mkdir(parents=True)
            exe = tmp / "client" / "opencode"
            exe.parent.mkdir()
            exe.write_text("#!/bin/sh\n")
            bwrap = tmp / "bwrap"
            bwrap.write_text("#!/bin/sh\nexit 97\n")
            bwrap.chmod(0o755)
            spec = {"backend": "bwrap", "bwrap": str(bwrap), "network": "host", "read_only": []}
            environ = {"PATH": "/usr/bin:/bin", "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")}
            out = "\n".join([f"{M}try workspace", "ok", f"{M}rc 0",
                             f"{M}try user_namespace", f"{REFUSALS[0]}{M}rc 1", f"{M}end"]) + "\n"
            real = subprocess.run

            def run(argv, *a, **k):
                if isinstance(argv, list) and argv[:1] == [str(bwrap)]:
                    return subprocess.CompletedProcess(argv, 0, "bubblewrap 0.12.0\n" if argv[1:] == ["--version"] else out, "")
                return real(argv, *a, **k)
            with mock.patch.object(subprocess, "run", run):
                rep = confine.measure(spec, tmp / "run" / "confinement", str(exe), system="linux", environ=environ)
        self.assertEqual(rep["tried"]["user_namespace"]["exit"], None)
        self.assertTrue(any("user_namespace" in p and DID_NOT_RUN in p for p in rep["problems"]), rep["problems"])


if __name__ == "__main__":
    unittest.main()
