"""V2.1 mutation survivors, batch T07b: aisef2/app/confine.py (namespaces, problem, targets, wrap).

Four requirements the confinement's existing tests (tests/v2/test_v21_confine.py) never asserted:

* the namespace comparison a real measurement makes (`namespaces(inside)`, no `outside`) is against this process's own
  /proc/self/ns/<n> links;
* the setting is a JSON object: its four keys are accepted in any order, and the refusal for a wrong shape names each
  of them as a word of its own;
* `targets` is, in order, the DESTINATION of every --bind/--ro-bind and the operand of every --tmpfs/--proc/--dev of a
  bubblewrap command line (what `_judge` compares each mount of the session with, and where the probe's `find`
  looks for unix sockets);
* the environment a confined session gets is the caller's with USERPROFILE, TEMP and TMP removed and nothing else
  lost, and its TMPDIR is a tmpfs the wrapper made.

Nothing here runs bubblewrap or a probe: command lines are only built, /proc is faked or read, and every file is in a
directory of the test's own."""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import confine, settings  # noqa: E402
from tests.v2 import test_app_run as app_run  # noqa: E402 — the module only: its tests are not collected again

#: what a run may ask for (alphabetical, as confine.KEYS is)
SPEC = {"backend": "bwrap", "bwrap": "/usr/bin/bwrap", "network": "host", "read_only": []}
KEYS = {"backend", "bwrap", "network", "read_only"}
NS = ("user", "pid", "net", "ipc", "uts", "mnt")


def words(text: str) -> set[str]:
    """The lower-case words of a message, `read_only` one word: what an operator reads the key names from."""
    return set(re.findall(r"[a-z_]+", text))


class DefaultOutsideIsThisProcess(unittest.TestCase):
    """`namespaces(inside)` with no `outside` — the call `_probe` makes on every real measurement — judges each link
    the probe read against this process's own /proc/self/ns/<n>: a different link is "own", an equal one "shared", a
    namespace this process has no link for "not measured". Pins aisef2/app/confine.py::namespaces [14, 15]."""

    @staticmethod
    def proc(links: dict[str, str]):
        """A stand-in for `os` as namespaces() uses it: only `links` exist, and each reads as its target."""
        def readlink(p):
            if p not in links:
                raise FileNotFoundError(p)
            return links[p]
        return types.SimpleNamespace(path=types.SimpleNamespace(exists=lambda p: p in links), readlink=readlink)

    def test_each_link_is_compared_with_this_processs_own_proc_link(self):
        links = {"/proc/self/ns/user": "user:[1]", "/proc/self/ns/pid": "pid:[7]"}
        with mock.patch.object(confine, "os", self.proc(links)):
            got = confine.namespaces({"user": "user:[2]", "pid": "pid:[7]", "net": "net:[3]"})
        # user differs from this process's link: own; pid equals it: shared; no /proc/self/ns/net here: not measured
        self.assertEqual(got, {"user": "own", "pid": "shared", "net": "not measured"})

    def test_every_namespace_whose_link_differs_inside_is_own(self):
        links = {f"/proc/self/ns/{n}": f"{n}:[10]" for n in NS}
        with mock.patch.object(confine, "os", self.proc(links)):
            got = confine.namespaces({n: f"{n}:[20]" for n in NS})
        self.assertEqual(got, dict.fromkeys(NS, "own"))

    @unittest.skipUnless(os.path.isdir("/proc/self/ns"), "needs this host's /proc/self/ns")
    def test_on_this_host_a_session_that_shares_every_link_is_shared(self):
        """The real /proc: what this process reads there, a probe that shared its namespaces would read too."""
        mine = {}
        for n in NS:
            try:
                link = os.readlink(f"/proc/self/ns/{n}")
            except OSError:
                continue
            if re.fullmatch(rf"{n}:\[\d+\]", link):
                mine[n] = link
        if not mine:
            self.skipTest("this host's /proc/self/ns links are not of the form <namespace>:[<inode>]")
        self.assertEqual(confine.namespaces(mine), dict.fromkeys(mine, "shared"))


class SettingIsAJsonObject(unittest.TestCase):
    """A JSON object has no key order that means anything: the four keys of the confinement setting are accepted in
    any order (a valid setting is never refused for how the operator wrote it), and a setting that is not the four
    keys is refused with a message that names each of them as a word of its own — the operator reads from it which
    keys the setting takes. Pins aisef2/app/confine.py::problem [31, 42]."""

    ORDERS = (("read_only", "network", "bwrap", "backend"), ("bwrap", "backend", "read_only", "network"))

    def test_the_order_of_the_keys_does_not_matter(self):
        for order in self.ORDERS:
            spec = {k: SPEC[k] for k in order}
            self.assertEqual(list(spec), list(order))
            with self.subTest(order=order):
                self.assertIsNone(confine.problem(spec))
                self.assertEqual(settings.load({**app_run.SETTINGS, "confinement": spec}).confinement, SPEC)

    def test_a_settings_file_that_writes_the_keys_in_another_order_is_read(self):
        """The operator's own path: a JSON file, read back by settings.read."""
        text = json.dumps({**app_run.SETTINGS, "confinement": {k: SPEC[k] for k in self.ORDERS[0]}})
        self.assertLess(text.index('"read_only"'), text.index('"backend"'))      # as written: not alphabetical
        with tempfile.TemporaryDirectory() as t:
            path = pathlib.Path(t) / "settings.json"
            path.write_text(text, encoding="utf-8")
            self.assertEqual(settings.read(path).confinement, SPEC)

    def test_a_setting_that_is_not_the_four_keys_names_each_key_as_a_word(self):
        wrong = (("a key too many", {**SPEC, "extra": 1}),
                 ("a key short", {k: v for k, v in SPEC.items() if k != "read_only"}),
                 ("a key misspelled", {**{k: v for k, v in SPEC.items() if k != "read_only"}, "readonly": []}),
                 ("a list", ["backend", "bwrap", "network", "read_only"]),
                 ("a string", "bwrap"))
        for what, bad in wrong:
            with self.subTest(what=what):
                why = confine.problem(bad)
                self.assertIsInstance(why, str)
                self.assertLessEqual(KEYS, words(why), why)
                with self.assertRaises(settings.SettingsError) as raised:
                    settings.load({**app_run.SETTINGS, "confinement": bad})
                self.assertLessEqual(KEYS, words(str(raised.exception)), str(raised.exception))


def mount_points(argv: list[str]) -> list[str]:
    """The mount points of a bubblewrap command line, read by walking its options with their arities (so an operand
    that looks like an option is an operand): the destination (second operand) of --bind and --ro-bind, the operand
    of --tmpfs, --proc and --dev; the command after `--` is not read. Independent of confine.targets, which scans
    for the flags."""
    head, out, i = argv[:argv.index("--")], [], 1
    arity = {"--bind": 2, "--ro-bind": 2, "--symlink": 2, "--tmpfs": 1, "--proc": 1, "--dev": 1, "--chdir": 1,
             "--cap-drop": 1}
    while i < len(head):
        if head[i] in ("--bind", "--ro-bind"):
            out.append(head[i + 2])
        elif head[i] in ("--tmpfs", "--proc", "--dev"):
            out.append(head[i + 1])
        i += 1 + arity.get(head[i], 0)
    return out


class WrapFixture(unittest.TestCase):
    """A client, a workspace, a configuration directory and an executable file standing for bubblewrap — all in a
    directory of the test's own; wrap() only builds a command line, nothing runs."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(os.path.realpath(t.name))
        self.bwrap = self.tmp / "bwrap"
        self.bwrap.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
        self.bwrap.chmod(0o755)
        self.home, self.ws, self.extra = self.tmp / "home", self.tmp / "ws", self.tmp / "extra"
        for d in (self.home / ".config" / "opencode", self.ws, self.extra):
            d.mkdir(parents=True)
        self.exe = self.tmp / "client" / "opencode"
        self.exe.parent.mkdir()
        self.exe.write_text("#!/bin/sh\n", encoding="utf-8")
        self.spec = dict(SPEC, bwrap=str(self.bwrap))

    def wrap(self, env, spec=None, command=None, **kw):
        return confine.wrap(spec or self.spec, command or [str(self.exe), "run", "the prompt"], env, str(self.ws),
                            str(self.exe), system="linux", **kw)


class TargetsAreMountPoints(WrapFixture):
    """`targets(full)` is where a bubblewrap command line mounts something: the DESTINATION of every --bind and
    --ro-bind (the mount point mountinfo shows, never the source) and the operand of every --tmpfs, --proc and --dev,
    and nothing else — no --symlink or --chdir operand, nothing after the first `--`. `_judge` refuses any mount of the
    session that lies within none of them, and `_probe` lists unix sockets below them; a wrong list refuses every
    confined run, or looks for sockets in the wrong places. Both only ask whether a path is among them, so the order is
    not asserted (the workspace-last order of the command line itself is test_v21_confine's). Pins
    aisef2/app/confine.py::targets [5-20]."""

    def test_a_literal_command_line_of_every_kind_of_option(self):
        # a source that is not the destination (--ro-bind /s1 /d1), a --chdir operand and a --symlink operand that are
        # not mounts, a mount (--dev /v) directly before the first `--`, and a command that has a mount-like option of
        # its own and a `--` of its own after the wrapper's
        full = ["bwrap", "--unshare-user", "--chdir", "/d2", "--ro-bind", "/s1", "/d1", "--bind", "/s2", "/d2", "--tmpfs", "/t",
                "--proc", "/p", "--symlink", "usr/bin", "/bin", "--dev", "/v",
                "--", "x", "--bind", "/n", "/n", "--", "--tmpfs", "/m"]
        want = ["/d1", "/d2", "/t", "/p", "/v"]
        self.assertEqual(sorted(confine.targets(full)), sorted(want))
        self.assertEqual(sorted(mount_points(full)), sorted(want))       # the helper below reads it the same way

    def test_the_command_line_wrap_builds_names_its_own_mounts(self):
        """Every option kind the wrapper really emits (read-only system and `read_only` paths, the client's and
        configuration directories, /proc, /dev, two tmpfs, the workspace): the list is the command line's own mounts,
        whatever the command after `--` looks like, for the developer's wrapper and the reviewer's (workspace
        read-only)."""
        env = {"PATH": "/usr/bin:/bin", "HOME": str(self.home), "LANG": "C"}
        for writable in (True, False):
            argv, _ = self.wrap(env, dict(self.spec, read_only=[str(self.extra)]), [str(self.exe), "--tmpfs", "/not-a-mount"],
                                writable=writable)
            got = confine.targets(argv)
            with self.subTest(writable=writable):
                self.assertEqual(sorted(got), sorted(mount_points(argv)))
                for want in (str(self.ws), "/proc", "/dev", "/tmp", confine.HOME, str(self.exe.parent), str(self.extra),
                             str(self.home / ".config" / "opencode")):
                    self.assertIn(want, got)
                self.assertNotIn("/not-a-mount", got)
                self.assertNotIn("--bind", got)


class SessionEnvironment(WrapFixture):
    """The environment a confined session starts with is the caller's — PATH, the locale, the variables the settings
    name (the provider's key) and OPENCODE_CONFIG_CONTENT (the overlay that fixes model and small_model to the
    attested route) arrive with their values — every one the caller gave, but for USERPROFILE, TEMP and TMP, which
    name host profile and temp locations that are not in the sandbox, and HOME and TMPDIR, which the wrapper sets:
    TMPDIR is a tmpfs the wrapper made, never the operator's. Pins
    aisef2/app/confine.py::wrap [21, 22, 39, 40, 41, 57, 58, 59]."""

    def setUp(self) -> None:
        super().setUp()
        self.host_tmp = str(self.tmp / "host-tmp")
        #: what app/client.environment can hand over: its allowlist (PATH, HOME, USERPROFILE, SYSTEMROOT, WINDIR, LANG,
        #: LC_ALL, TMPDIR, TEMP, TMP, XDG_*) and the variables the settings name, plus the overlay
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(self.home), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                    "SYSTEMROOT": "C:\\Windows", "WINDIR": "C:\\Windows", "TMPDIR": self.host_tmp,
                    "USERPROFILE": str(self.tmp / "profile"), "TEMP": str(self.tmp / "temp"), "TMP": str(self.tmp / "tmp"),
                    "PROVIDER_API_KEY": "key-for-the-provider", "OPENCODE_CONFIG_CONTENT": json.dumps({"model": "p/m"})}

    def test_the_callers_variables_arrive_with_their_values(self):
        _, inside = self.wrap(self.env)
        for k in self.env:
            if k not in ("USERPROFILE", "TEMP", "TMP", "HOME", "TMPDIR"):
                with self.subTest(k=k):
                    self.assertEqual(inside.get(k), self.env[k])
        self.assertIn("OPENCODE_CONFIG_CONTENT", inside)

    def test_no_host_profile_or_temp_location_arrives(self):
        _, inside = self.wrap(self.env)
        for k in ("USERPROFILE", "TEMP", "TMP"):
            with self.subTest(k=k):
                self.assertNotIn(k, inside)

    def test_tmpdir_names_a_tmpfs_the_wrapper_made(self):
        argv, inside = self.wrap(self.env)
        head = argv[:argv.index("--")]
        tmpfs = [head[i + 1] for i, a in enumerate(head) if a == "--tmpfs"]
        self.assertIn(inside.get("TMPDIR"), tmpfs)
        self.assertNotEqual(inside["TMPDIR"], self.host_tmp)
        self.assertTrue(inside["TMPDIR"].startswith("/"), inside["TMPDIR"])     # a path, not an unset variable


if __name__ == "__main__":
    unittest.main()
