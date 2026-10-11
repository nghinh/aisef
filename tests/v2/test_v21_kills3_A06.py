"""Mutation survivors of aisef2/app/confine.py, audit batch A06 (V2.1, owner directive B-03).

Of the 17 survivors of this batch three are real gaps; the rest are audited, equivalent or open (the dispositions are
in the batch report, not here). The three:

* `argv`'s own default for `writable`: a direct call of the public function that omits it binds the workspace
  read-write, as its docstring says. The only caller (`wrap`) always passes it, so nothing else shows it.
* the `argv` the measurement RECORDS is the command line it RAN, the probe script elided. The kill file asserts the
  literal tail of the record, not that it describes what was run, so a probe started with a different `$0` than the
  record names went unseen.
* `_judge`'s user-namespace check: an `unshare` that could not run (exit 127) is "no refusal measured" whatever it
  printed. The kill file feeds exit 127 only with texts that carry no refusal wording, so the exit status was never the
  deciding half of that condition; the dynamic loader exits 127 with the errno text appended, EPERM's included.

None of them runs bubblewrap. The measurement test uses a "bubblewrap" that runs nothing — it writes the arguments it
was given to a file and exits 0 — so the probe is never executed, confined or not; the judgement test hands `_judge`
the output text of the probe's user-namespace try, parsed by the module's own `_sections`."""

from __future__ import annotations

import os
import pathlib
import shlex
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import confine  # noqa: E402
from tests.v2 import test_v21_confine as base  # noqa: E402 — the module: its tests are not collected again


class ArgvDefault(unittest.TestCase):
    """`confine.argv(spec, command, workspace, read_only)` — `writable` omitted — binds the workspace read-write, and
    only `writable=False` (the model reviewer's checkout) binds it read-only: argv's docstring, "read-write ... unless
    not `writable`". Pins aisef2/app/confine.py::argv [1]."""

    def test_the_workspace_is_read_write_unless_asked_not_to_be(self):
        ws = os.path.join(os.sep, "w", "ws")
        writable = confine.argv(base.SPEC, ["/bin/true"], ws, [])
        self.assertEqual(base.pairs(writable, "--bind"), [(ws, ws)])
        self.assertNotIn(ws, base.ro_binds(writable))
        read_only = confine.argv(base.SPEC, ["/bin/true"], ws, [], writable=False)
        self.assertEqual(base.pairs(read_only, "--bind"), [])
        self.assertEqual(base.pairs(read_only, "--ro-bind")[-1], (ws, ws))


def clean_report(ws: pathlib.PurePath) -> dict:
    """A measurement `_judge` finds nothing to say about (the workspace the only host-backed mount)."""
    return {"network": "host", "created_outside_workspace": {"kernel": False}, "setsid_survivors": [],
            "inside": {"capabilities": dict.fromkeys(("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"), "0000000000000000"),
                       "no_new_privs": "1", "namespaces": dict.fromkeys(("user", "pid", "ipc", "uts", "mnt"), "own"),
                       "routed_interfaces": [], "home_listing": [], "unix_sockets": [],
                       "mounts": [{"at": "/", "access": "rw", "fs": "tmpfs"}, {"at": str(ws), "access": "rw", "fs": "ext4"}],
                       "mount_targets": [str(ws)]}}


class UserNamespaceCheckThatCouldNotRun(unittest.TestCase):
    """The probe's `unshare --user true` is a measured refusal only when unshare RAN and the kernel said no: exit 127
    is the shell's and the dynamic loader's "could not be run" status, and the text with it is whatever went wrong — a
    loader failure on a library it cannot map ends in the errno text, "Operation not permitted" among them, the very
    wording of a seccomp or LSM refusal. A check that could not run is a problem, never a pass (`_judge`'s docstring;
    SANDBOX-LINUX.md, the measurement paragraph). Pins aisef2/app/confine.py::_judge [98]."""

    TOKEN = "TOKEN-0123456789abcdef"

    def judged(self, rc: int, text: str) -> list[str]:
        """`_judge` on the probe output of a clean measurement whose user-namespace try exited `rc` printing `text`,
        parsed by the module's own `_sections`."""
        ws, m = pathlib.PurePosixPath("/w/ws"), confine.MARK
        out = "\n".join([f"{m}try read_canary", "cat: canary: No such file or directory", f"{m}rc 1",
                         f"{m}try workspace", "ok", f"{m}rc 0",
                         f"{m}try read_git_directory", "ref: refs/heads/main", f"{m}rc 0",
                         f"{m}try user_namespace", text, f"{m}rc {rc}"]) + "\n"
        _, _, tries = confine._sections(out)
        self.assertEqual(tries["user_namespace"][0], rc)
        return confine._judge(clean_report(ws), self.TOKEN, out, tries, "/nonexistent", ws)

    def test_exit_127_is_never_a_measured_refusal_whatever_it_printed(self):
        loader = ("unshare: error while loading shared libraries: libcap-ng.so.0: failed to map segment from shared "
                  "object: Operation not permitted")
        problems = self.judged(127, loader)
        unmeasured = [p for p in problems if p.startswith("no refusal of a further user namespace was measured")]
        self.assertEqual(len(unmeasured), 1, problems)
        self.assertIn("127", unmeasured[0])

    def test_a_refusal_the_kernel_gave_is_one_by_either_of_its_wordings(self):
        for text in ("unshare: unshare failed: No space left on device", "unshare: unshare failed: Operation not permitted"):
            with self.subTest(text=text):
                self.assertEqual(self.judged(1, text), [])


def runs_nothing_and_logs(where: pathlib.Path, log: pathlib.Path) -> pathlib.Path:
    """A "bubblewrap" that runs no command: `--version` is answered; any other call writes its arguments to `log`,
    each followed by a NUL (the probe script holds newlines), and exits 0 with no output."""
    fake = where / "bwrap"
    fake.write_text('#!/bin/sh\n[ "$1" = "--version" ] && { echo "bubblewrap 0.0-test"; exit 0; }\n'
                    f"printf '%s\\0' \"$@\" > {shlex.quote(str(log))}\n", encoding="utf-8")
    fake.chmod(0o755)
    return fake


@unittest.skipUnless(os.name == "posix", "the stand-in for bubblewrap is a POSIX shell script")
class RecordedCommandLine(unittest.TestCase):
    """The measurement's `argv` is its evidence of what ran: the bubblewrap command line the probe was started with,
    the probe script itself elided ("<PROBE>"). It must equal what the wrapper was actually given — an auditor
    reproduces the measurement from it. Pins aisef2/app/confine.py::measure [26] (the probe's `$0`, which the record
    names from a literal of its own)."""

    def test_the_recorded_argv_is_the_command_line_that_ran(self):
        self.addCleanup(base.host_unchanged, base.host_view())
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(os.path.realpath(t))
            log = tmp / "argv.nul"
            fake = runs_nothing_and_logs(tmp, log)
            exe = tmp / "client" / "opencode"
            exe.parent.mkdir()
            exe.write_text("#!/bin/sh\n", encoding="utf-8")
            rep = confine.measure(dict(base.SPEC, bwrap=str(fake)), tmp / "run" / "confinement", str(exe),
                                  system="linux", environ={"PATH": "/usr/bin:/bin", "HOME": str(tmp / "home")})
            ran = [a.decode("utf-8") for a in log.read_bytes().split(b"\0")[:-1]]
        self.assertIn(confine.PROBE, ran)          # the stand-in was given the probe: the measurement reached it
        i = ran.index(confine.PROBE)
        # bwrap <options> -- sh -c <script> <$0> <$1..$9> <the bound directories>: the record keeps the command line up
        # to and including $0 and puts "<PROBE>" where the script stood; the probe's own arguments (nonce paths) are
        # not part of it
        self.assertEqual(rep["argv"], [str(fake), *ran[:i], "<PROBE>", ran[i + 1]])


if __name__ == "__main__":
    unittest.main()
