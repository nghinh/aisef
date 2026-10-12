"""V2.1 mutation survivors of aisef2/app/confine.py::_probe, batch T05a: what the measurement hands the probe and what
it makes of what the probe printed — the operator's HOME listing and the unix sockets below the bound host directories.

Neither needs bubblewrap or a Linux kernel: the product's side of the probe is the argument list it is given and the
judgement of what it prints. The wrapper is the real `confine.wrap` (a real client directory, a worktree of a real run
repository, a real configuration directory; a "bubblewrap" that runs nothing), and subprocess.run answers the probe's
one call with a model of what the probe prints inside a sandbox the test describes (`Sandbox`): what lies at the path
the probe is given as HOME, which unix sockets exist, whether `find` is there. A sandbox that is as required gives no
problem at all (test_a_sandbox_as_required_is_not_refused), so each departure below is the only thing that refuses.
The model follows the probe's own text (aisef2/app/confine.py PROBE): `[ -e "$5" ]` then `ls -A -- "$5"`, and after
`shift 9` `find "$@" -type s` (GNU find with no operand walks the current directory, the workspace)."""

from __future__ import annotations

import os
import pathlib
import posixpath
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import confine  # noqa: E402
from tests.v2 import isolated_git  # noqa: E402
from tests.v2 import v21_r3_conf_rows as rows  # noqa: E402

SPEC = {"backend": "bwrap", "bwrap": "/usr/bin/bwrap", "network": "host", "read_only": []}
#: a "bubblewrap" that runs no command: a call that got past the model below would write nothing anywhere
RUNS_NOTHING = "#!/bin/sh\nexit 97\n"
NAMESPACES = ("user", "pid", "net", "ipc", "uts", "mnt")


def below(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def dollar(probe: list[str], n: int) -> str:
    """The probe's $n: its argument list is `-c PROBE probe $1 ... $9 <bound host directories>`."""
    return probe[probe.index(confine.PROBE) + 1 + n]


def bound(probe: list[str]) -> list[str]:
    """What follows $9: the directories the probe's `find` is given."""
    return probe[probe.index(confine.PROBE) + 11:]


def pairs(argv: list[str], flag: str) -> list[tuple[str, str]]:
    return [(argv[i + 1], argv[i + 2]) for i, a in enumerate(argv[:argv.index("--")]) if a == flag]


class Sandbox:
    """What a session sees, as the probe prints it. `home`: {path: entries `ls -A` lists there}, a path not in it is
    not there (`[ -e "$5" ]` is false). `sockets`: the unix sockets that exist at these host paths, reachable wherever
    a bound directory leads to them. `find`: whether the sandbox has it. Everything else is a session that is as
    required: no capability, no_new_privs, own namespaces, the mounts the wrapper names, the canary unreadable, the
    workspace writable, a further user namespace refused."""

    def __init__(self, home: dict | None = None, sockets=(), find: bool = True) -> None:
        self.home, self.sockets, self.find = home or {}, list(sockets), find

    def printed(self, argv: list[str]) -> str:
        wrapper = argv[:argv.index("--")]
        home, roots = dollar(argv, 5), bound(argv)
        mounts = [("/", "rw", "tmpfs")]
        for i, flag in enumerate(wrapper):
            if flag in ("--ro-bind", "--bind"):
                mounts.append((wrapper[i + 2], "ro" if flag == "--ro-bind" else "rw", "ext4"))
            elif flag in ("--tmpfs", "--dev"):
                mounts.append((wrapper[i + 1], "rw", "tmpfs"))
            elif flag == "--proc":
                mounts.append((wrapper[i + 1], "rw", "proc"))
        out = ["@@aisef-confine uid 1000"]
        out += [f"@@aisef-confine ns {n} {n}:[{4026532000 + i}]" for i, n in enumerate(NAMESPACES)]
        out += ["@@aisef-confine section status", *(f"{k}:\t0000000000000000" for k in ("CapInh", "CapPrm", "CapEff",
                                                                                         "CapBnd", "CapAmb")),
                "NoNewPrivs:\t1", "Seccomp:\t2", "@@aisef-confine section mountinfo"]
        out += [f"{n} 1 0:{n} / {at.replace(' ', chr(92) + '040')} {acc},relatime - {fs} {fs} {acc}"
                for n, (at, acc, fs) in enumerate(mounts, 20)]
        out += ["@@aisef-confine section route", "Iface\tDestination\tGateway",
                "@@aisef-confine section netdev", "Inter-|   Receive", " face |bytes", "    lo: 0 0",
                "@@aisef-confine section home", *self.home.get(home, [])]
        for name, rc, said in (("read_canary", 1, "cat: canary: No such file or directory"),
                               ("write_run_directory", 1, "Read-only file system"), ("write_kernel", 1, "Read-only file system"),
                               ("write_interpreter_site", 1, "Read-only file system"),
                               ("write_client_directory", 1, "Read-only file system"),
                               ("write_git_directory", 1, "Read-only file system"), ("read_git_directory", 0, "ref: refs/heads/main"),
                               ("workspace", 0, "ok"), ("user_namespace", 1, "unshare: unshare failed: No space left on device"),
                               ("setsid", 0, "")):
            out += [f"@@aisef-confine try {name}", *([said] if said else []), f"@@aisef-confine rc {rc}"]
        out.append("@@aisef-confine section sockets")
        if self.find:
            if roots:       # find <dir>... -type s: below each directory it was given
                out += [s for r in roots for s in self.sockets if below(s, r)]
            else:           # no operand: ".", the current directory (--chdir: the workspace)
                cwd = wrapper[wrapper.index("--chdir") + 1]
                out += ["./" + posixpath.relpath(s, cwd) for s in self.sockets if below(s, cwd)]
            out.append("@@aisef-confine sockets listed")
        out.append("@@aisef-confine end")
        return "\n".join(out) + "\n"


@unittest.skipUnless(os.name == "posix", "the probe's paths are POSIX paths: the HOME check compares them as such")
class Session(unittest.TestCase):
    """A run repository, the client's directory, an operator HOME with a client configuration directory (which the
    wrapper binds read-only) and a directory the operator lists in `read_only`; `measure` runs confine.measure as a run
    calls it, the probe's call answered by a Sandbox."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(os.path.realpath(t.name))
        self.bwrap = self.tmp / "bwrap"
        self.bwrap.write_text(RUNS_NOTHING)
        self.bwrap.chmod(0o755)
        self.home, self.ro, self.run_dir = self.tmp / "home", self.tmp / "ro", self.tmp / "out"
        (self.home / ".config" / "opencode").mkdir(parents=True)
        self.ro.mkdir()
        repo = self.run_dir / "repo"
        repo.mkdir(parents=True)
        isolated_git.git(repo, "init", "-q", "-b", "main")
        isolated_git.git(repo, "commit", "-q", "--allow-empty", "-m", "base")
        self.exe = self.tmp / "client" / "opencode"
        self.exe.parent.mkdir()
        self.exe.write_text("#!/bin/sh\n")
        self.ws = self.run_dir / "confinement" / "ws"      # the measurement's workspace: a worktree `where/ws`

    def measure(self, sandbox: Sandbox, environ: dict | None = None, read_only=()) -> tuple[dict, list[str]]:
        """(report, the probe's command line) of one measurement; exactly one probe call is made."""
        spec = dict(SPEC, bwrap=str(self.bwrap), read_only=[str(p) for p in read_only])
        calls, real_run, real_namespaces = [], subprocess.run, confine.namespaces

        def run(argv, *a, **k):
            if isinstance(argv, list) and confine.PROBE in argv:
                calls.append(list(argv))
                # as Popen: an argument that is not a string (a None) is a TypeError, not a probe that ran
                return subprocess.CompletedProcess(argv, 0, sandbox.printed([os.fspath(x) for x in argv]), "")
            if isinstance(argv, list) and argv[1:] == ["--version"]:
                return subprocess.CompletedProcess(argv, 0, "bubblewrap 0.0.0\n", "")
            return real_run(argv, *a, **k)       # git, for the measurement's worktree

        def own(inside, outside=None):           # the host's own links, as a Linux /proc would read them
            return real_namespaces(inside, {n: f"{n}:[1]" for n in inside})
        env = environ if environ is not None else {"PATH": "/usr/bin:/bin", "HOME": str(self.home)}
        with mock.patch.object(subprocess, "run", run), mock.patch.object(confine, "namespaces", own), \
                mock.patch.object(confine, "_survivors", lambda command: []), rows.host_table():
            rep = confine.measure(spec, self.run_dir / "confinement", str(self.exe), self.run_dir / "repo",
                                  system="linux", environ=env)
        self.assertEqual(len(calls), 1, rep["problems"])
        return rep, calls[0]


class CleanSession(Session):
    def test_a_sandbox_as_required_is_not_refused(self):
        """The model's baseline: HOME shows only `.config`, the way to the client's configuration directory (SANDBOX-
        LINUX.md §5), a socket in the workspace, find present: no problem, and the record keeps both listings. What the
        departures below refuse is theirs. It asserts the whole clean outcome, so it also fails on each mutant the
        classes below pin (aisef2/app/confine.py::_probe [13, 23, 77, 90, 123, 124, 155, 160])."""
        rep, _ = self.measure(Sandbox(home={str(self.home): [".config"]}, sockets=[str(self.ws / "own.sock")]),
                              read_only=[self.ro])
        self.assertEqual(rep["problems"], [])
        self.assertEqual(rep["inside"]["home_listing"], [".config"])
        self.assertEqual(rep["inside"]["unix_sockets"], [str(self.ws / "own.sock")])


class HomeListing(Session):
    """The probe lists the operator's HOME as the session sees it; a session that sees more than the way to what is
    mounted can read the operator's secrets (~/.ssh, ~/.aws), so the run is refused naming it.
    Pins aisef2/app/confine.py::_probe [13, 90, 123]."""

    def test_the_probe_is_given_the_operators_home(self):
        _, probe = self.measure(Sandbox())
        self.assertEqual(dollar(probe, 5), str(self.home))

    def test_a_home_that_shows_more_than_the_way_to_a_mount_is_refused_naming_the_entry(self):
        rep, _ = self.measure(Sandbox(home={str(self.home): [".config", ".ssh"]}))
        self.assertEqual(rep["inside"]["home_listing"], [".config", ".ssh"])     # the record keeps what it saw
        refused = [p for p in rep["problems"] if p.startswith("HOME shows more than")]
        self.assertEqual(len(refused), 1, rep["problems"])
        self.assertIn(".ssh", refused[0])
        self.assertNotIn(".config", refused[0])         # the way to a mount is not the exposure
        self.assertEqual(rep["problems"], refused)

    def test_without_a_home_the_probe_is_given_a_path_that_is_not_there_and_no_home_is_judged(self):
        """HOME absent from the environment: a report (not a crash), the probe's $5 the "/nonexistent" the judgement
        takes as 'no HOME to check' — neither None nor an empty string."""
        rep, probe = self.measure(Sandbox(), environ={"PATH": "/usr/bin:/bin"})
        self.assertEqual(dollar(probe, 5), "/nonexistent")
        self.assertEqual(rep["inside"]["home_listing"], [])
        self.assertEqual(rep["problems"], [])


class UnixSockets(Session):
    """A read-only mount does not stop a connect to a unix socket below it (SANDBOX-LINUX.md §5), so the probe is
    given every host directory the wrapper binds and the measurement refuses one that has a socket. Pins
    aisef2/app/confine.py::_probe [23, 160] (the directories), [77, 124] (find present or absent), [155] (the list)."""

    def test_the_probe_is_given_every_host_directory_the_wrapper_binds_and_none_of_its_own_mounts(self):
        _, probe = self.measure(Sandbox(), read_only=[self.ro])
        self.assertEqual(sorted(bound(probe)),
                         sorted(dst for flag in ("--ro-bind", "--bind") for _, dst in pairs(probe, flag)))
        for want in (self.ro, self.exe.parent, self.run_dir / "repo" / ".git", self.home / ".config" / "opencode", self.ws):
            self.assertIn(str(want), bound(probe))
        for synthetic in ("/proc", "/dev", "/tmp", confine.HOME):      # the sandbox's own: no host directory
            self.assertNotIn(synthetic, bound(probe))

    def test_a_socket_below_a_bound_read_only_directory_is_refused_naming_it(self):
        ctl, own = self.ro / "sock" / "ctl", self.ws / "own.sock"
        rep, _ = self.measure(Sandbox(sockets=[str(ctl), str(own)]), read_only=[self.ro])
        self.assertEqual(sorted(rep["inside"]["unix_sockets"]), sorted([str(ctl), str(own)]))
        refused = [p for p in rep["problems"] if "unix socket outside the workspace is reachable" in p]
        self.assertEqual(len(refused), 1, rep["problems"])
        self.assertIn(str(ctl), refused[0])
        self.assertNotIn(str(own), refused[0])          # one in the workspace is the session's own
        self.assertEqual(rep["problems"], refused)

    def test_a_sandbox_without_find_is_a_problem_not_a_pass(self):
        """No `sockets listed` in the transcript: the sockets are unknown (None, not an empty list) and the run is
        refused for it — 'a check that could not run is a problem, never a pass'."""
        rep, _ = self.measure(Sandbox(find=False))
        self.assertIsNone(rep["inside"]["unix_sockets"])
        self.assertEqual(len(rep["problems"]), 1, rep["problems"])
        self.assertIn("unix sockets could not be listed", rep["problems"][0])

    def test_find_that_listed_nothing_is_a_clean_listing(self):
        rep, _ = self.measure(Sandbox(), read_only=[self.ro])
        self.assertEqual(rep["inside"]["unix_sockets"], [])
        self.assertEqual(rep["problems"], [])


if __name__ == "__main__":
    unittest.main()
