"""V2.1 product defects of aisef2/app/confine.py found by the mutation-survivor audit (owner directive B-03): the
requirement each audit wrote the test of, failing on the code as it was.

1. The measurement refuses a session that can connect to a unix socket below a host directory the wrapper binds in
   (SANDBOX-LINUX.md §5 Sockets: "none is listed under any host directory bound in"; a read-only mount does not stop
   a connect). Which directories the probe's `find` is given was decided by the PATH of the mount, so a host
   directory bound where a synthetic mount of the sandbox lies (`--tmpfs /tmp`, `--dev /dev`, `--proc /proc`,
   `--tmpfs <HOME>`: `read_only: ["/tmp"]` binds the host's /tmp over the tmpfs) was never searched and its sockets (tmux,
   ssh-agent, X11) neither showed in `inside.unix_sockets` nor refused the run. It is decided by the OPTION: the
   host directories are what `--bind` / `--ro-bind` name.
2. A `read_only` entry written with a trailing slash (`settings` accepts any absolute path) is bound as written and the
   kernel prints its mount point without the slash: it is the directory the operator named, not a mount "beyond what
   the wrapper names", and the run is not refused for it.
3. A probe that hangs is a recorded refusal whose reason names the limit it exceeded: subprocess's own text for it
   starts with the whole command line, and the reason (cut at 300 characters) never reached the number.

Nothing here needs bubblewrap or a Linux kernel: the product's side of the probe is the argument list it is given and
what it makes of what the probe printed. The wrapper is the real `confine.wrap` (a real client directory, a worktree
of a real run repository, a real configuration directory; a "bubblewrap" that runs nothing), and subprocess.run
answers the probe's one call with a model of what the probe prints in a sandbox that is as required, built from the
wrapper's own command line (`transcript`): the mounts it names, the sockets that lie below a host directory it binds
in, and what `find` prints below the directories it was given."""

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
from tests.v2 import isolated_git  # noqa: E402

M = confine.MARK
SPEC = {"backend": "bwrap", "bwrap": "/usr/bin/bwrap", "network": "host", "read_only": []}
#: a "bubblewrap" that runs no command: a call that got past the model below would write nothing anywhere
RUNS_NOTHING = "#!/bin/sh\nexit 97\n"
NAMESPACES = ("user", "pid", "net", "ipc", "uts", "mnt")
ZERO = "0000000000000000"
POSIX = unittest.skipUnless(os.name == "posix", "the probe's paths are POSIX paths: the HOME check compares them as such")


def below(path: str, root: str) -> bool:
    return path == root.rstrip("/") or path.startswith(root.rstrip("/") + "/")


def roots_of(probe: list[str]) -> list[str]:
    """What follows the probe's $9: the directories its `find` is given (`-c PROBE probe $1 ... $9 <directories>`)."""
    return probe[probe.index(confine.PROBE) + 11:]


def host_binds(probe: list[str]) -> list[str]:
    """The destinations of the wrapper's --bind / --ro-bind: the host directories the session can see."""
    wrapper = probe[:probe.index("--")]
    return [wrapper[i + 2] for i, a in enumerate(wrapper) if a in ("--bind", "--ro-bind")]


def transcript(probe: list[str], sockets: list[str], extra_mounts: tuple[str, ...] = ()) -> str:
    """What the probe prints in a sandbox that is as required — no capability, no_new_privs, own namespaces, the canary
    unreadable, the workspace writable, a further user namespace refused — with the mounts the wrapper names as the
    kernel prints them (a mount point has no trailing slash) and `extra_mounts` besides. `sockets` are unix sockets
    of the host: one is reachable when it lies below a host directory the wrapper binds in, and `find` prints it when
    it lies below a directory it was given."""
    wrapper = probe[:probe.index("--")]
    mounts = [("/", "rw", "tmpfs")]
    for i, flag in enumerate(wrapper):
        if flag in ("--ro-bind", "--bind"):
            mounts.append((wrapper[i + 2].rstrip("/") or "/", "ro" if flag == "--ro-bind" else "rw", "ext4"))
        elif flag in ("--tmpfs", "--dev"):
            mounts.append((wrapper[i + 1], "rw", "tmpfs"))
        elif flag == "--proc":
            mounts.append((wrapper[i + 1], "rw", "proc"))
    mounts += [(at, "ro", "ext4") for at in extra_mounts]
    out = ["@@aisef-confine uid 1000", *(f"@@aisef-confine ns {n} {n}:[{4026532000 + i}]" for i, n in enumerate(NAMESPACES)),
           "@@aisef-confine section status", *(f"{k}:\t{ZERO}" for k in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")),
           "NoNewPrivs:\t1", "Seccomp:\t2", "@@aisef-confine section mountinfo",
           *(f"{n} 1 0:{n} / {at} {acc},relatime - {fs} {fs} {acc}" for n, (at, acc, fs) in enumerate(mounts, 20)),
           "@@aisef-confine section route", "Iface\tDestination\tGateway",
           "@@aisef-confine section netdev", "Inter-|   Receive", " face |bytes", "    lo: 0 0",
           "@@aisef-confine section home"]
    for name, rc, said in (("read_canary", 1, "cat: canary: No such file or directory"),
                           ("write_run_directory", 1, "Read-only file system"), ("write_kernel", 1, "Read-only file system"),
                           ("write_interpreter_site", 1, "Read-only file system"),
                           ("write_client_directory", 1, "Read-only file system"),
                           ("write_git_directory", 1, "Read-only file system"), ("read_git_directory", 0, "ref: refs/heads/main"),
                           ("workspace", 0, "ok"), ("user_namespace", 1, "unshare: unshare failed: No space left on device"),
                           ("setsid", 0, "")):
        out += [f"@@aisef-confine try {name}", *([said] if said else []), f"@@aisef-confine rc {rc}"]
    out += ["@@aisef-confine section sockets", *(s for r in roots_of(probe) for s in sockets if below(s, r)),
            "@@aisef-confine sockets listed", "@@aisef-confine end"]
    return "\n".join(out) + "\n"


def hangs(argv, k):
    """The probe's call as subprocess.run ends one that outlives its limit: the command line and the limit it was given."""
    raise subprocess.TimeoutExpired(argv, k["timeout"])


class Case(unittest.TestCase):
    """A run repository, the client's directory, an operator HOME with a client configuration directory (which the
    wrapper binds read-only) and a directory the operator lists in `read_only`."""

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
        self.environ = {"PATH": "/usr/bin:/bin", "HOME": str(self.home)}
        self.n = 0

    def measure(self, read_only=(), sockets=(), extra_mounts=(), probe=None) -> tuple[dict, list[str]]:
        """(report, the probe's command line) of one measurement as a run makes it; the probe's call is answered by
        `transcript`, or by `probe` (a callable given the call's argv and keyword arguments)."""
        spec = dict(SPEC, bwrap=str(self.bwrap), read_only=[str(p) for p in read_only])
        calls, real_run, real_namespaces = [], subprocess.run, confine.namespaces

        def run(argv, *a, **k):
            if isinstance(argv, list) and confine.PROBE in argv:
                calls.append(list(argv))
                if probe is not None:
                    return probe(argv, k)
                return subprocess.CompletedProcess(argv, 0, transcript(argv, list(sockets), tuple(extra_mounts)), "")
            if isinstance(argv, list) and argv[1:] == ["--version"]:
                return subprocess.CompletedProcess(argv, 0, "bubblewrap 0.0.0\n", "")
            return real_run(argv, *a, **k)       # git, for the measurement's worktree

        def own(inside, outside=None):           # the host's own links, as a Linux /proc would read them
            return real_namespaces(inside, {n: f"{n}:[1]" for n in inside})
        self.n += 1
        with mock.patch.object(subprocess, "run", run), mock.patch.object(confine, "namespaces", own), \
                mock.patch.object(confine, "_survivors", lambda command: []):
            rep = confine.measure(spec, self.run_dir / f"confinement{self.n}", str(self.exe), self.run_dir / "repo",
                                  system="linux", environ=dict(self.environ))
        self.assertEqual(len(calls), 1, rep["problems"])
        return rep, calls[0]

    def assert_refused_for(self, read_only, socket: str, **kw) -> None:
        """The session can reach `socket` (it lies below a host directory the wrapper binds in): the measurement lists
        it and refuses the run naming it."""
        rep, probe = self.measure(read_only=read_only, sockets=[socket], **kw)
        self.assertTrue(any(below(socket, d) for d in host_binds(probe)), host_binds(probe))     # the premise
        self.assertIn(socket, rep["inside"]["unix_sockets"], f"the probe's find was given {roots_of(probe)}")
        refused = [p for p in rep["problems"] if "a unix socket outside the workspace is reachable" in p]
        self.assertEqual(len(refused), 1, rep["problems"])
        self.assertIn(socket, refused[0])
        self.assertEqual(rep["problems"], refused)       # and nothing else is wrong with the session


@POSIX
class SocketsBelowAHostDirectoryBoundAtASyntheticMount(Case):
    """The probe's directories are the host's, chosen by the option that binds them, whatever their path."""

    def test_control_a_plain_bound_directory_is_listed_and_refuses(self):
        self.assert_refused_for([self.ro], str(self.ro / "sock" / "ctl"))

    def test_a_session_as_required_is_not_refused(self):
        """The model's baseline: nothing bound in has a socket (one in the workspace is the session's own)."""
        ws = self.run_dir / "confinement1" / "ws"
        rep, _ = self.measure(read_only=[self.ro], sockets=[str(ws / "own.sock")])
        self.assertEqual(rep["inside"]["unix_sockets"], [str(ws / "own.sock")])
        self.assertEqual(rep["problems"], [])

    @unittest.skipUnless(os.path.isdir("/tmp"), "a host with a /tmp")
    def test_the_hosts_tmp_bound_over_the_synthetic_tmpfs(self):
        self.assert_refused_for(["/tmp"], "/tmp/tmux-1000/default")

    @unittest.skipUnless(os.path.isdir("/dev"), "a host with a /dev")
    def test_the_hosts_dev_bound_over_the_synthetic_dev(self):
        self.assert_refused_for(["/dev"], "/dev/log")

    def test_a_host_directory_at_the_homes_own_path(self):
        home = self.tmp / "aisef-home"
        home.mkdir()
        with mock.patch.object(confine, "HOME", str(home)):     # HOME is the constant "/aisef-home": a host directory of that name
            self.assert_refused_for([home], str(home / "agent.sock"))

    def test_the_client_installed_in_a_directory_named_like_a_synthetic_mount(self):
        """The same by another way in: the client's own directory is bound read-only (not `read_only`); one that is
        the path of the sandbox's HOME is a host directory like any other."""
        home = self.tmp / "aisef-home"
        home.mkdir()
        exe = home / "opencode"
        exe.write_text("#!/bin/sh\n")
        self.exe = exe
        with mock.patch.object(confine, "HOME", str(home)):
            self.assert_refused_for([], str(home / "agent.sock"))

    def test_the_directories_are_exactly_the_host_directories_the_wrapper_binds(self):
        """Every host directory bound in is searched, wherever the path leads; the sandbox's own mounts (--proc, --dev,
        --tmpfs) are not host directories and are not."""
        _, probe = self.measure(read_only=[self.ro])
        self.assertEqual(sorted(roots_of(probe)), sorted(host_binds(probe)))
        for want in (self.ro, self.exe.parent, self.run_dir / "repo" / ".git", self.home / ".config" / "opencode"):
            self.assertIn(str(want), roots_of(probe))
        self.assertEqual(roots_of(probe)[-1], str(self.run_dir / "confinement1" / "ws"))     # the workspace, bound last
        for own in ("/proc", "/dev", "/tmp", confine.HOME):
            self.assertNotIn(own, roots_of(probe))
        for path in ("/tmp", "/dev", "/proc"):
            if not os.path.isdir(path):
                continue
            with self.subTest(read_only=path):
                _, probe = self.measure(read_only=[path])
                self.assertEqual(sorted(roots_of(probe)), sorted(host_binds(probe)))
                self.assertIn(path, roots_of(probe))


@POSIX
class AReadOnlyPathWrittenWithATrailingSlash(Case):
    """`confinement.read_only` takes any absolute path; a directory written with a trailing slash is that directory."""

    def test_its_mount_is_not_beyond_what_the_wrapper_names(self):
        rep, probe = self.measure(read_only=[f"{self.ro}/"])
        self.assertIn(f"{self.ro}/", host_binds(probe))     # bound as written: the kernel prints it without the slash
        self.assertEqual(rep["problems"], [])

    def test_several_slashes_are_the_same_directory(self):
        rep, _ = self.measure(read_only=[f"{self.ro}//"])
        self.assertEqual(rep["problems"], [])

    def test_a_socket_below_it_is_still_listed_and_refuses(self):
        self.assert_refused_for([f"{self.ro}/"], str(self.ro / "sock" / "ctl"))

    def test_a_mount_that_only_shares_its_prefix_is_still_beyond(self):
        """Fail closed: `<dir>-extra` is not below `<dir>/`, nor `<dir>` itself below a root that merely begins with it."""
        sibling = f"{self.ro}-extra"
        self.assertFalse(confine._within(sibling, [f"{self.ro}/"]))      # the predicate, wherever the temp directory lies
        self.assertTrue(confine._within(f"{self.ro}/inner", [f"{self.ro}/"]))
        if below(str(self.ro), "/tmp"):   # a mount below the sandbox's own /tmp tmpfs is named by the wrapper (Linux CI)
            self.skipTest("the temp directory lies below the sandbox's /tmp: the measurement below is not about it")
        rep, _ = self.measure(read_only=[f"{self.ro}/"], extra_mounts=[sibling])
        self.assertEqual(rep["problems"], [f"mounted beyond what the wrapper names: ['{sibling}']"])

    def test_a_mount_below_it_is_not_beyond(self):
        rep, _ = self.measure(read_only=[f"{self.ro}/"], extra_mounts=[f"{self.ro}/inner"])
        self.assertEqual(rep["problems"], [])


class Within(unittest.TestCase):
    """`_within(path, roots)`: the path is a root or lies below one — a root written with a trailing slash is the same
    directory, and one that only shares its beginning is not."""

    def test_a_root_with_or_without_a_trailing_slash_is_the_same_directory(self):
        for root in ("/data", "/data/", "/data//"):
            with self.subTest(root=root):
                self.assertTrue(confine._within("/data", [root]))
                self.assertTrue(confine._within("/data/sub/file", [root]))
                self.assertFalse(confine._within("/data2", [root]))
                self.assertFalse(confine._within("/dat", [root]))

    def test_the_root_directory_holds_every_path(self):
        self.assertTrue(confine._within("/srv/a", ["/"]))
        self.assertTrue(confine._within("/", ["/"]))


@POSIX
class AProbeThatHangs(Case):
    """The probe's own call raises TimeoutExpired: a recorded refusal (never an exception out of measure()) whose
    reason names the limit the probe exceeded, so the operator reads how long it was given."""

    def test_the_recorded_reason_names_the_limit(self):
        limit = 4242.5      # nothing a path or a pid looks like
        with mock.patch.object(confine, "PROBE_TIMEOUT", limit):
            rep, _ = self.measure(probe=hangs)
        first = rep["problems"][0]
        self.assertTrue(first.startswith("the sandbox did not run the probe (exit None): "), first)
        self.assertIn("TimeoutExpired", first)
        self.assertIn(str(limit), first)
        self.assertEqual(len(rep["problems"]), 1, rep["problems"])

    def test_another_failure_of_the_call_still_names_its_class_and_reason(self):
        def fails(argv, k):
            raise OSError(8, "Exec format error")
        rep, _ = self.measure(probe=fails)
        first = rep["problems"][0]
        self.assertTrue(first.startswith("the sandbox did not run the probe (exit None): "), first)
        self.assertIn("OSError", first)
        self.assertIn("Exec format error", first)
        self.assertEqual(len(rep["problems"]), 1, rep["problems"])


if __name__ == "__main__":
    unittest.main()
