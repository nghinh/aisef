"""V2.1 mutation survivors, batch T07a: the confinement's read set, its mount-table parse and its probe-output parse
(aisef2/app/confine.py).

What runs everywhere (macOS and Windows too): nothing here starts bubblewrap or reads the host's own mount table. The
command line is built with the host's file system stubbed (a Linux host's /usr, /lib64 ... on any machine), and the
parses are fed literal text of the shape the probe prints and /proc/self/mountinfo has. Each class pins one behaviour
a reader of the boundary depends on:

* the system paths a session may READ (SystemPaths);
* the mounts the judge decides on, as parsed from mountinfo (MountInfo);
* the sections and tries the probe's output is read into (ProbeOutput);
* a read-only root written with a trailing slash (TrailingSlash);
* the stage a measurement refusal names (MeasurementStages);
* the client's configuration directory, XDG_CONFIG_HOME first (ConfigurationDirectory);
* a `.git` file that is not a pointer binds nothing (GitFile)."""

from __future__ import annotations

import contextlib
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
from aisef2.orchestrate import workspace  # noqa: E402

SPEC = {"backend": "bwrap", "bwrap": "/usr/bin/bwrap", "network": "host", "read_only": []}


def pairs(argv: list[str], flag: str) -> list[tuple[str, str]]:
    """The operands of each `flag SRC DEST` before the `--` that ends bubblewrap's own options."""
    return [(argv[i + 1], argv[i + 2]) for i, a in enumerate(argv[:argv.index("--")]) if a == flag]


def ro_binds(argv: list[str]) -> list[str]:
    return [src for src, _ in pairs(argv, "--ro-bind")]


@contextlib.contextmanager
def host_with(dirs=(), links=None):
    """A host whose file system has exactly these directories and these symbolic links ({path: target}); a link to a
    directory is a directory too, as on a merged-/usr host. Only the three calls argv() makes are stubbed."""
    links = dict(links or {})
    with mock.patch.object(confine.os.path, "isdir", lambda p: p in dirs or p in links), \
            mock.patch.object(confine.os.path, "islink", lambda p: p in links), \
            mock.patch.object(confine.os, "readlink", lambda p: links[p]):
        yield


class SystemPaths(unittest.TestCase):
    """Requirement: every path of confine.SYSTEM (/usr /etc /bin /sbin /lib /lib32 /lib64 /libx32) that exists on the
    host is made available to the session read-only — a directory as `--ro-bind P P`, a symbolic link as
    `--symlink <its target> P` (a merged-/usr host keeps its links) — one the host does not have is not named, and
    none is writable. A session without one of them cannot start the client or the probe (an interpreter, libc, the
    loader of x86-64 binaries, /bin/sh, the resolver and CA files).

    Pins aisef2/app/confine.py::SYSTEM [0, 1, 2, 3, 4, 5, 6, 7]."""

    DIRS = ("/usr", "/etc", "/lib32", "/lib64", "/libx32")
    LINKS = {"/bin": "usr/bin", "/sbin": "usr/sbin", "/lib": "usr/lib"}

    def test_every_system_path_the_host_has_is_bound_read_only(self):
        with host_with(self.DIRS, self.LINKS):
            argv = confine.argv(SPEC, ["client"], "/w/ws", [])
        # the order SYSTEM lists its paths in is not promised: each path exactly once, in any order
        self.assertEqual(sorted(pairs(argv, "--ro-bind")), sorted((d, d) for d in self.DIRS))
        self.assertEqual(sorted(pairs(argv, "--symlink")), sorted((target, path) for path, target in self.LINKS.items()))
        self.assertEqual(pairs(argv, "--bind"), [("/w/ws", "/w/ws")])        # the workspace is the only writable bind

    def test_a_path_the_host_does_not_have_is_not_named(self):
        with host_with(("/usr", "/etc", "/lib64"), {"/bin": "usr/bin"}):
            argv = confine.argv(SPEC, ["client"], "/w/ws", [])
        self.assertEqual(sorted(pairs(argv, "--ro-bind")), [("/etc", "/etc"), ("/lib64", "/lib64"), ("/usr", "/usr")])
        self.assertEqual(pairs(argv, "--symlink"), [("usr/bin", "/bin")])
        named = set(argv[:argv.index("--")])
        for absent in ("/sbin", "/lib", "/lib32", "/libx32"):
            self.assertNotIn(absent, named)


class MountInfo(unittest.TestCase):
    """Requirement: each /proc/self/mountinfo line with a ' - ' separator, at least 6 fields before it and a
    filesystem type after it becomes {at: the mount point, octal escapes decoded (\\040 space, \\011 tab, \\012
    newline, \\134 backslash); access: 'ro' iff 'ro' is one of the comma-separated PER-MOUNT options (field 6, not the
    super options after the separator), else 'rw'; fs: the filesystem type}; any other line is skipped. The judge
    reads this list for 'mounted beyond what the wrapper names' (at), 'writable outside the workspace' (access, fs):
    a writable host-backed mount read as 'ro' passes the very check that exists to find it, a read-only bind read as
    'rw' refuses every run; the labels 'ro'/'rw' are the vocabulary of the record (RUN.json confinement.inside.mounts).

    Pins aisef2/app/confine.py::_mounts [11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]."""

    ROOT_FS = "1 0 0:30 / / rw,nosuid,nodev,relatime - tmpfs tmpfs rw"
    #: read-only per mount, an optional field before the separator, super options that say rw
    USR = "25 1 8:1 /usr /usr ro,relatime master:2 - ext4 /dev/sda1 rw,errors=remount-ro"
    #: the workspace: a space in its path is \040 in mountinfo; writable per mount, super options that say ro
    WS = r"26 1 8:1 /ws /w\040s/ws rw,relatime - ext4 /dev/sda1 ro"
    TMP = "27 1 0:31 / /tmp rw,nosuid,nodev - tmpfs tmpfs rw,size=1024k"
    #: a tab, a newline and a backslash in a mount point, and a space followed by a digit of the name ('\0401' is a space
    #: and a '1', not one escape); "ro" only as a part of another option
    ODD = r"28 1 0:32 / /a\134b\011c\012d\0401 rw,proto - tmpfs tmpfs rw"
    SKIPPED = ("29 1 0:5 / /no-separator rw tmpfs tmpfs rw",
               "30 1 0:5 / /five-fields - tmpfs tmpfs rw",
               "31 1 0:5 / /no-fs-type rw - ")
    SRV = "40 1 8:2 /srv /srv rw,relatime - ext4 /dev/sdb1 rw"

    def test_a_line_becomes_where_how_and_what_and_the_other_shapes_are_skipped(self):
        got = confine._mounts([self.ROOT_FS, self.USR, self.WS, *self.SKIPPED, self.TMP, self.ODD])
        self.assertEqual(got, [{"at": "/", "access": "rw", "fs": "tmpfs"},
                               {"at": "/usr", "access": "ro", "fs": "ext4"},
                               {"at": "/w s/ws", "access": "rw", "fs": "ext4"},
                               {"at": "/tmp", "access": "rw", "fs": "tmpfs"},
                               {"at": "/a\\b\tc\nd 1", "access": "rw", "fs": "tmpfs"}])

    def judged(self, lines, targets, ws="/w s/ws"):
        """_judge over a guest whose mount table is `lines`, everything else as a clean measurement shows it."""
        rep = {"network": "host", "created_outside_workspace": {}, "setsid_survivors": [],
               "inside": {"capabilities": dict.fromkeys(("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"), "0"),
                          "no_new_privs": "1", "namespaces": dict.fromkeys(("user", "pid", "ipc", "uts", "mnt"), "own"),
                          "routed_interfaces": [], "home_listing": [], "unix_sockets": [],
                          "mounts": confine._mounts(lines), "mount_targets": targets}}
        tries = {"read_canary": (1, ""), "workspace": (0, "ok"), "read_git_directory": (0, "ref: x"),
                 "user_namespace": (1, "unshare failed: No space left on device")}
        return confine._judge(rep, "tok", "", tries, "/nonexistent", pathlib.PurePosixPath(ws))

    def test_a_guest_with_a_read_only_system_and_its_workspace_is_clean(self):
        """Read-only host binds are not 'writable outside the workspace', and the workspace whose path holds a space
        (\\040 in mountinfo) is neither 'beyond' what the wrapper names nor 'writable'."""
        self.assertEqual(self.judged([self.ROOT_FS, self.USR, self.WS, self.TMP], ["/usr", "/w s/ws", "/tmp"]), [])

    def test_a_writable_host_backed_mount_outside_the_workspace_is_refused(self):
        said = self.judged([self.ROOT_FS, self.USR, self.WS, self.TMP, self.SRV], ["/usr", "/w s/ws", "/tmp", "/srv"])
        self.assertEqual(len(said), 1, said)
        self.assertTrue(said[0].startswith("writable outside the workspace"), said)
        self.assertIn("/srv", said[0])
        self.assertNotIn("/usr", said[0])
        self.assertNotIn("/w s/ws", said[0])


class ProbeOutput(unittest.TestCase):
    """Requirement: _sections(out) -> (values, sections, tries). '@@aisef-confine <word> <rest>' gives
    values[word] = rest ('ns <name> <link>' gives values['ns'][name] = link); the lines after 'section X' are
    sections['X']; the lines after 'try X' up to 'rc N' are the try's output, tries['X'] = (N, those lines kept apart (not
    run together), stripped, its first 300 characters); a line outside any section or try (before the first mark, after an
    rc, after a single value) is ignored, never an error. The capabilities, mounts, routes, sockets and namespaces the
    judge decides on, and every recorded denial text, are read from these.

    Pins aisef2/app/confine.py::_sections [17, 23, 25, 42, 43]."""

    M = confine.MARK

    def test_values_sections_and_tries(self):
        out = "\n".join([
            "a stray line before the first mark",
            f"{self.M}uid 1000",
            f"{self.M}ns user user:[4026531837]",
            f"{self.M}ns pid pid:[4026532000]",
            f"{self.M}section status",
            "Name:\tsh",
            "CapEff:\t0000000000000000",
            f"{self.M}section mountinfo",
            "1 0 0:30 / / rw - tmpfs tmpfs rw",
            f"{self.M}try workspace",
            "ok",
            f"{self.M}rc 0",
            "a stray line after an rc",
            f"{self.M}try read_canary",
            "cat: a: No such file or directory",
            "cat: b: Permission denied",
            f"{self.M}rc 1",
            f"{self.M}try long",
            "  " + "a" * 300 + "b" * 100 + "  ",
            f"{self.M}rc 2",
            f"{self.M}try padded",
            "",
            "  denied  ",
            "",
            f"{self.M}rc 3",
            f"{self.M}section sockets",
            "/w/ws/control.sock",
            f"{self.M}sockets listed",
            "a stray line after a single value",
            f"{self.M}end",
        ])
        values, sections, tries = confine._sections(out)
        self.assertEqual(values, {"uid": "1000", "ns": {"user": "user:[4026531837]", "pid": "pid:[4026532000]"},
                                  "sockets": "listed", "end": ""})
        self.assertEqual(sections, {"status": ["Name:\tsh", "CapEff:\t0000000000000000"],
                                    "mountinfo": ["1 0 0:30 / / rw - tmpfs tmpfs rw"],
                                    "sockets": ["/w/ws/control.sock"]})
        self.assertEqual(tries["workspace"], (0, "ok"))
        rc, said = tries["read_canary"]
        first, second = "cat: a: No such file or directory", "cat: b: Permission denied"
        self.assertEqual(rc, 1)
        self.assertIn(first, said)
        self.assertIn(second, said)
        self.assertLess(said.index(first), said.index(second))
        self.assertNotIn(first + second, said)      # the lines of a multi-line denial are not run together
        self.assertEqual(tries["long"], (2, "a" * 300))      # stripped, and its first 300 characters
        self.assertEqual(tries["padded"], (3, "denied"))     # stripped on both ends
        self.assertEqual(sorted(tries), ["long", "padded", "read_canary", "workspace"])


class TrailingSlash(unittest.TestCase):
    """Requirement: _within(p, roots) is True for a path BELOW a root whether the root is written '/data' or
    '/data/' (problem() accepts any absolute string as a read_only path, and the entries reach the judge as written),
    and False for a sibling that only shares a prefix ('/data2'). Without it a read_only '/opt/tool/' makes every
    mount below it 'mounted beyond what the wrapper names': a refusal of a setting that is valid.

    Pins aisef2/app/confine.py::_within [4]. (That the root itself, '/data' for '/data/', is not within it is a
    defect of the unmutated code, found with this batch and reported, not fixed here: it is not asserted below.)"""

    def test_a_path_below_a_root_with_a_trailing_slash_is_within_it(self):
        for root in ("/data", "/data/"):
            with self.subTest(root=root):
                self.assertTrue(confine._within("/data/sub", [root]))
                self.assertTrue(confine._within("/data/sub/deeper", [root]))
                self.assertFalse(confine._within("/data2", [root]))
                self.assertFalse(confine._within("/dat", [root]))

    def test_a_mount_below_a_read_only_path_written_with_a_trailing_slash_is_not_beyond(self):
        ws = pathlib.PurePosixPath("/w/ws")
        rep = {"network": "host", "created_outside_workspace": {}, "setsid_survivors": [],
               "inside": {"capabilities": dict.fromkeys(("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"), "0"),
                          "no_new_privs": "1", "namespaces": dict.fromkeys(("user", "pid", "ipc", "uts", "mnt"), "own"),
                          "routed_interfaces": [], "home_listing": [], "unix_sockets": [],
                          "mounts": [{"at": "/", "access": "rw", "fs": "tmpfs"}, {"at": str(ws), "access": "rw", "fs": "ext4"},
                                     {"at": "/data/sub", "access": "ro", "fs": "ext4"},
                                     {"at": "/data2", "access": "ro", "fs": "ext4"}],
                          "mount_targets": [str(ws), "/data/"]}}
        tries = {"read_canary": (1, ""), "workspace": (0, "ok"), "read_git_directory": (0, "ref: x"),
                 "user_namespace": (1, "unshare failed: No space left on device")}
        said = confine._judge(rep, "tok", "", tries, "/nonexistent", ws)
        self.assertEqual(len(said), 1, said)
        self.assertTrue(said[0].startswith("mounted beyond what the wrapper names"), said)
        self.assertIn("/data2", said[0])        # the sibling is beyond; what is below /data/ is not
        self.assertNotIn("/data/sub", said[0])


class MeasurementStages(unittest.TestCase):
    """Requirement: a measurement that cannot make its repository or its worktree is a recorded problem (the run's
    refusal text and `--check`'s confinement.problems), and the problem names WHICH stage failed — the repository, or
    the workspace as a worktree of it — and where (the repository's path; git's own reason for the worktree), so the
    operator can tell the two apart. Nothing runs under confinement.

    Pins aisef2/app/confine.py::_worktree [43]."""

    def measured(self, fails):
        """(where, report) of confine.measure with git stubbed: `fails(args)` says whether that git call fails."""
        def git(repo, *args):
            bad = fails(args)
            return subprocess.CompletedProcess(["git", *args], 1 if bad else 0, "", "boom: out of space" if bad else "")
        with tempfile.TemporaryDirectory() as t:
            where = pathlib.Path(os.path.realpath(t)) / "run" / "confinement"
            with mock.patch.object(workspace, "git", git):
                rep = confine.measure(SPEC, where, None, system="linux", environ={"PATH": "/usr/bin:/bin"})
        return where, rep

    def test_a_repository_that_cannot_be_made_is_named_with_its_path(self):
        where, rep = self.measured(lambda args: True)
        [said] = rep["problems"]
        self.assertIn(str(where / "repo"), said)
        reason = said.replace(str(where / "repo"), "")      # what is said besides the path
        self.assertIn("repository", reason)
        self.assertNotIn("worktree", reason)

    def test_a_worktree_that_cannot_be_made_is_told_from_the_repository_stage(self):
        where, rep = self.measured(lambda args: "worktree" in args)
        [said] = rep["problems"]
        self.assertIn(str(where / "repo"), said)
        reason = said.replace(str(where / "repo"), "")
        self.assertIn("worktree", reason)
        self.assertIn("boom: out of space", reason)        # git's reason
        self.assertNotIn("repository", reason)


class ConfigurationDirectory(unittest.TestCase):
    """Requirement: the client's configuration directory is resolved as the client resolves it
    (app.client.configured_provider): XDG_CONFIG_HOME when set — even when $HOME/.config/opencode also exists —
    else $HOME/.config. The session binds that directory read-only and its XDG_CONFIG_HOME is that base: a session
    that ran on another configuration than the one the run attested would call another provider.

    Pins aisef2/app/confine.py::config_dir [7]."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(os.path.realpath(t.name))
        self.home, self.xdg = self.tmp / "home", self.tmp / "xdg"
        (self.home / ".config" / "opencode").mkdir(parents=True)
        (self.xdg / "opencode").mkdir(parents=True)
        self.bwrap = self.tmp / "bwrap"
        self.bwrap.write_text("#!/bin/sh\nexit 97\n")       # only its existence and mode are looked at: nothing runs
        self.bwrap.chmod(0o755)
        self.exe = self.tmp / "client" / "opencode"
        self.exe.parent.mkdir()
        self.exe.write_text("#!/bin/sh\n")
        self.ws = self.tmp / "ws"
        self.ws.mkdir()

    def wrap(self, env):
        return confine.wrap(dict(SPEC, bwrap=str(self.bwrap)), [str(self.exe)], env, str(self.ws), str(self.exe), system="linux")

    def test_xdg_config_home_is_read_first(self):
        env = {"PATH": "/usr/bin:/bin", "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.xdg)}
        self.assertEqual(confine.config_dir(env), (str(self.xdg), os.path.join(str(self.xdg), "opencode")))
        argv, inside = self.wrap(env)
        self.assertIn(os.path.join(str(self.xdg), "opencode"), ro_binds(argv))
        self.assertNotIn(str(self.home / ".config" / "opencode"), ro_binds(argv))
        self.assertEqual(inside["XDG_CONFIG_HOME"], str(self.xdg))

    def test_xdg_config_home_alone_is_enough(self):
        env = {"PATH": "/usr/bin:/bin", "XDG_CONFIG_HOME": str(self.xdg)}      # no HOME at all
        self.assertEqual(confine.config_dir(env), (str(self.xdg), os.path.join(str(self.xdg), "opencode")))


class GitFile(unittest.TestCase):
    """Requirement: a workspace whose `.git` is a file that is not a 'gitdir: <path>' pointer — of any bytes, valid
    UTF-8 or not — has no common git directory: git_dir() returns None and wrap() binds nothing extra for it; it never
    raises (client.session catches only Unavailable around wrap(): an exception ends the story with a traceback). A
    pointer is followed, so that what the session binds read-only is what git wrote and nothing else.

    Pins aisef2/app/confine.py::git_dir [8, 10]."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(os.path.realpath(t.name))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.secret = self.tmp / "secret"       # a directory a malformed file's text would resolve to, if it were read
        self.secret.mkdir()
        self.bwrap = self.tmp / "bwrap"
        self.bwrap.write_text("#!/bin/sh\nexit 97\n")
        self.bwrap.chmod(0o755)
        self.exe = self.tmp / "client" / "opencode"
        self.exe.parent.mkdir()
        self.exe.write_text("#!/bin/sh\n")
        self.ws = self.tmp / "ws"
        self.ws.mkdir()

    def wrap(self):
        env = {"PATH": "/usr/bin:/bin", "HOME": str(self.home)}
        return confine.wrap(dict(SPEC, bwrap=str(self.bwrap)), [str(self.exe)], env, str(self.ws), str(self.exe), system="linux")[0]

    def test_a_gitfile_that_is_not_a_pointer_binds_nothing_and_never_raises(self):
        baseline = ro_binds(self.wrap())        # a workspace with no `.git` at all
        self.assertIsNone(confine.git_dir(str(self.ws)))
        for what, content in (("text the size of the prefix, then a path", b"x" * 8 + str(self.secret).encode()),
                              ("a ref", b"ref: refs/heads/main\n"),
                              ("empty", b""),
                              ("not UTF-8", b"\xff\xfe\x00\xff"),
                              ("not UTF-8, then a path", b"\xff" * 8 + str(self.secret).encode())):
            with self.subTest(what=what):
                (self.ws / ".git").write_bytes(content)
                self.assertIsNone(confine.git_dir(str(self.ws)))
                bound = ro_binds(self.wrap())
                self.assertEqual(bound, baseline)
                self.assertNotIn(str(self.secret), bound)

    def test_a_pointer_is_followed(self):
        """The control of the test above: a real pointer names the directory that is bound."""
        (self.ws / ".git").write_text(f"gitdir: {self.secret}\n", encoding="utf-8")
        self.assertEqual(confine.git_dir(str(self.ws)), str(self.secret))
        self.assertIn(str(self.secret), ro_binds(self.wrap()))


if __name__ == "__main__":
    unittest.main()
