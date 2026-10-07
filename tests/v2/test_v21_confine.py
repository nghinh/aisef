"""V2.1 (F; REPORT §6, docs/v2.1/SANDBOX-LINUX.md): the confinement of the model sessions (aisef2/app/confine.py).

What runs everywhere (macOS too): the setting, the bubblewrap command line a session gets, and fail-closed — a run, a
`--check` or a session that asks for confinement and cannot have it refuses before any provider request and before
the client starts; and the measurement judges what it OBSERVES: a "bubblewrap" that runs the probe unconfined is
refused for what it let through, not for its name; and the path a confined run takes when the measurement holds —
every session started through bubblewrap, the record saying so. The boundary itself is measured on Linux by
validation/v21/sandbox (docker): this module never claims it."""

from __future__ import annotations

import contextlib
import functools
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import client, confine, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from tests.v2 import test_app_run as app_run  # noqa: E402 — the module, so its Command tests are not collected again
from tests.v2.test_app_run import SETTINGS, ProductBase, provider  # noqa: E402

#: what a run may ask for: the shared network (a session must reach its provider); "none" is measurement-only
SPEC = {"backend": "bwrap", "bwrap": "/usr/bin/bwrap", "network": "host", "read_only": []}
OCR = {"exe": "/opt/ocr", "sha256": "0" * 64, "timeout_min": 1, "max_tokens": 9}
#: a "bubblewrap" that confines nothing: it drops every option and runs the command
NOT_A_SANDBOX = '#!/bin/sh\nwhile [ $# -gt 0 ] && [ "$1" != "--" ]; do shift; done\n[ $# -gt 0 ] || exit 0\nshift\nexec "$@"\n'


def ro_binds(argv: list[str]) -> list[str]:
    return [src for src, _ in pairs(argv, "--ro-bind")]


def fake_bwrap(where: pathlib.Path, log: pathlib.Path | None = None) -> pathlib.Path:
    """NOT_A_SANDBOX, writing each command line it is given to `log` (one JSON array per line) first."""
    fake = where / "bwrap"
    record = (f'{sys.executable} -c "import json,sys; open(sys.argv[1], \'a\').write(json.dumps(sys.argv[2:]) + chr(10))" '
              f'{log} "$@"\n') if log else ""
    fake.write_text(NOT_A_SANDBOX.replace("\n", "\n" + record, 1))
    fake.chmod(0o755)
    return fake


def pairs(argv: list[str], flag: str) -> list[tuple[str, str]]:
    return [(argv[i + 1], argv[i + 2]) for i, a in enumerate(argv[:argv.index("--")]) if a == flag]


class Setting(unittest.TestCase):
    def test_absent_is_none_and_given_is_kept(self):
        self.assertIsNone(settings.load(SETTINGS).confinement)
        self.assertEqual(settings.load({**SETTINGS, "confinement": SPEC}).confinement, SPEC)

    def test_anything_else_is_refused(self):
        for bad, why in ((dict(SPEC, backend="docker"), "backend is bwrap"), (dict(SPEC, bwrap="bwrap"), "absolute path"),
                         (dict(SPEC, network="bridge"), "network is one of"), (dict(SPEC, read_only=["rel"]), "absolute paths"),
                         (dict(SPEC, read_only="/x"), "absolute paths"), ({**SPEC, "extra": 1}, "confinement is"),
                         (dict(SPEC, network="none"), "no route to its provider: it is a measurement-only profile"),
                         ({k: v for k, v in SPEC.items() if k != "read_only"}, "confinement is")):
            with self.subTest(bad=bad), self.assertRaisesRegex(settings.SettingsError, why):
                settings.load({**SETTINGS, "confinement": bad})

    def test_not_with_open_code_review_which_calls_the_model_outside_the_sessions(self):
        review = {"policy": "advisory", "min_severity": "high", "finder": "ocr", "ocr": OCR}
        self.assertEqual(settings.load({**SETTINGS, "review": review}).review["finder"], "ocr")
        with self.assertRaisesRegex(settings.SettingsError, "Open Code Review .* would call the model unconfined"):
            settings.load({**SETTINGS, "review": review, "confinement": SPEC})
        model = dict(review, finder="model")
        del model["ocr"]
        self.assertEqual(settings.load({**SETTINGS, "review": model, "confinement": SPEC}).confinement, SPEC)


class CommandLine(unittest.TestCase):
    """The command line of a confined session, built for Linux (on any host: nothing runs)."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(os.path.realpath(t.name))
        self.bwrap = self.tmp / "bwrap"
        self.bwrap.write_text(NOT_A_SANDBOX)
        self.bwrap.chmod(0o755)
        self.home, self.run_dir = self.tmp / "home", self.tmp / "out"
        (self.home / ".config" / "opencode").mkdir(parents=True)
        repo = self.run_dir / "repo"
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
                        "-m", "base"], check=True)
        self.ws = self.run_dir / "work" / "ws" / "wt-S1"
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "--detach", str(self.ws)], check=True)
        self.exe = self.tmp / "client" / "opencode"
        self.exe.parent.mkdir()
        self.exe.write_text("#!/bin/sh\n")
        self.spec = dict(SPEC, bwrap=str(self.bwrap))
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(self.home), "LANG": "C"}

    def wrap(self, **over):
        return confine.wrap({**self.spec, **over}, [str(self.exe), "run", "the prompt"], self.env, str(self.ws), str(self.exe),
                            system="linux")

    def test_its_own_namespaces_no_privilege_and_the_client_command_unchanged(self):
        argv, _ = self.wrap(network="none")
        self.assertEqual(argv[0], str(self.bwrap))
        for flag in ("--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-net", "--disable-userns",
                     "--die-with-parent", "--new-session"):
            self.assertIn(flag, argv[:argv.index("--")])
        self.assertNotIn("--share-net", argv)
        self.assertEqual(argv[argv.index("--cap-drop") + 1], "ALL")
        self.assertEqual(argv[argv.index("--") + 1:], [str(self.exe), "run", "the prompt"])
        self.assertEqual(argv[argv.index("--chdir") + 1], str(self.ws))

    def test_the_workspace_is_the_only_writable_host_path_and_it_is_bound_last(self):
        argv, _ = self.wrap(read_only=[str(self.tmp)])     # the workspace lies below a read-only path
        self.assertEqual(pairs(argv, "--bind"), [(str(self.ws), str(self.ws))])
        last_ro = max(i for i, a in enumerate(argv) if a == "--ro-bind")
        self.assertGreater(argv.index("--bind"), last_ro)
        ro = [src for src, dst in pairs(argv, "--ro-bind") if src == dst]
        self.assertEqual(len(ro), len(pairs(argv, "--ro-bind")))
        for want in (str(self.exe.parent), str((self.run_dir / "repo" / ".git").resolve()),
                     str(self.home / ".config" / "opencode"), str(self.tmp)):
            self.assertIn(want, ro)
        for never in (str(self.home), str(self.run_dir), str(ROOT / "aisef2")):    # HOME, the run directory, the kernel
            self.assertNotIn(never, ro)

    def test_home_is_an_empty_tmpfs_and_the_client_still_finds_its_configuration(self):
        argv, env = self.wrap()
        self.assertIn(("--tmpfs", confine.HOME), list(zip(argv, argv[1:], strict=False)))
        self.assertEqual(env["HOME"], confine.HOME)
        self.assertTrue(all(env[k].startswith(confine.HOME) for k in ("XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME")))
        self.assertEqual(env["XDG_CONFIG_HOME"], str(self.home / ".config"))   # its opencode/ directory, read-only
        (self.home / ".config" / "opencode").rmdir()
        _, env = self.wrap()
        self.assertEqual(env["XDG_CONFIG_HOME"], f"{confine.HOME}/.config")

    def test_the_reviewers_workspace_is_bound_read_only(self):
        """writable=False (the model reviewer's session): the checkout it reviews is bound read-only, last; no
        host path is writable."""
        argv, _ = confine.wrap(self.spec, [str(self.exe)], self.env, str(self.ws), str(self.exe), system="linux", writable=False)
        self.assertEqual(pairs(argv, "--bind"), [])
        self.assertEqual(pairs(argv, "--ro-bind")[-1], (str(self.ws), str(self.ws)))
        self.assertEqual(argv[argv.index("--chdir") + 1], str(self.ws))
        self.assertEqual(ro_binds(argv)[:-1], ro_binds(self.wrap()[0]))     # otherwise the developer's wrapper

    def test_network_host_shares_the_network_and_says_so(self):
        argv, _ = self.wrap(network="host")
        self.assertIn("--share-net", argv)
        self.assertNotIn("--unshare-net", argv)

    def test_a_client_directory_that_holds_home_or_the_workspace_is_refused(self):
        for exe, held in ((self.home / "opencode", "HOME"), (self.run_dir / "opencode", "the workspace"),
                          (self.tmp / "opencode", "HOME")):
            exe.write_text("#!/bin/sh\n")
            with self.subTest(exe=exe), self.assertRaisesRegex(confine.Unavailable, f"holds {held}: bound read-only"):
                confine.wrap(self.spec, [str(exe)], self.env, str(self.ws), str(exe), system="linux")
        # HOME not in the env the client gets: the user's home (~) still counts
        exe = self.home / "opencode"
        with mock.patch.object(confine.os.path, "expanduser", lambda p: str(self.home) if p == "~" else p), \
                self.assertRaisesRegex(confine.Unavailable, "holds HOME: bound read-only"):
            confine.wrap(self.spec, [str(exe)], {"PATH": "/usr/bin:/bin"}, str(self.ws), str(exe), system="linux")

    def test_a_directory_is_not_bubblewrap(self):
        with self.assertRaisesRegex(confine.Unavailable, "not an executable file at"):
            self.wrap(bwrap=str(self.tmp))
        rep = confine.measure(dict(self.spec, bwrap=str(self.tmp)), self.tmp / "m", str(self.exe), system="linux",
                              environ=self.env)
        self.assertEqual(rep["problems"], [f"bubblewrap is not an executable file at {self.tmp}"])

    def test_an_unreadable_bubblewrap_is_a_problem_not_a_crash(self):
        with mock.patch.object(confine.pathlib.Path, "read_bytes", side_effect=PermissionError(13, "Permission denied")):
            rep = confine.measure(self.spec, self.tmp / "m", str(self.exe), system="linux", environ=self.env)
        self.assertEqual(rep["problems"], [f"bubblewrap at {self.bwrap} could not be read: PermissionError"])
        self.assertFalse((self.tmp / "m" / "ws").exists())

    def test_the_measured_wrapper_is_the_sessions_own(self):
        """measure() binds what a session's wrapper binds: the client's directory, the run repository's git directory,
        the configuration — only the workspace differs; and it leaves no worktree in the run's repository."""
        session, _ = self.wrap(read_only=[str(self.home / ".config")])
        seen = []
        real = confine.wrap

        def spy(*a, **k):
            r = real(*a, **k)
            seen.append(r[0])
            raise confine.Unavailable("captured, not run")
        with mock.patch.object(confine, "wrap", spy):
            rep = confine.measure(dict(self.spec, read_only=[str(self.home / ".config")]), self.run_dir / "confinement",
                                  str(self.exe), self.run_dir / "repo", system="linux", environ=self.env)
        self.assertEqual(rep["problems"], ["captured, not run"])
        self.assertEqual(ro_binds(seen[-1]), ro_binds(session))
        self.assertIn(str((self.run_dir / "repo" / ".git").resolve()), ro_binds(seen[-1]))
        self.assertEqual(pairs(seen[-1], "--bind"), [(str(self.run_dir / "confinement" / "ws"),) * 2])
        listed = subprocess.run(["git", "-C", str(self.run_dir / "repo"), "worktree", "list", "--porcelain"],
                                capture_output=True, text=True, check=True).stdout
        self.assertNotIn("confinement", listed)


class FailClosed(unittest.TestCase):
    def test_a_host_that_is_not_linux_has_no_backend(self):
        with self.assertRaisesRegex(confine.Unavailable, "Linux-only .* this host is darwin: no backend"):
            confine.wrap(SPEC, ["x"], {}, "/w", system="darwin")
        with tempfile.TemporaryDirectory() as t:
            rep = confine.measure(SPEC, pathlib.Path(t) / "c", system="darwin")
            self.assertFalse((pathlib.Path(t) / "c").exists())      # nothing is made on the host
        self.assertEqual(rep["problems"], ["confinement is Linux-only (bubblewrap); this host is darwin: no backend"])

    def test_a_missing_bubblewrap_or_read_only_path_is_refused(self):
        with self.assertRaisesRegex(confine.Unavailable, "not an executable file at /nonexistent/bwrap"):
            confine.wrap(dict(SPEC, bwrap="/nonexistent/bwrap"), ["x"], {}, "/w", system="linux")
        with self.assertRaisesRegex(confine.Unavailable, "do not exist: \\['/nonexistent/ro'\\]"):
            confine.wrap(dict(SPEC, bwrap=sys.executable, read_only=["/nonexistent/ro"]), ["x"], {}, "/w", system="linux")

    @unittest.skipUnless(os.name == "posix", "the probe is a POSIX shell script")
    def test_what_is_measured_decides_not_the_name_of_the_tool(self):
        """A 'bubblewrap' that runs the probe unconfined: refused for what the probe could do."""
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(os.path.realpath(t))
            fake = fake_bwrap(tmp)
            exe = tmp / "client" / "opencode"
            exe.parent.mkdir()
            exe.write_text("#!/bin/sh\n")
            where = tmp / "run" / "confinement"
            rep = confine.measure(dict(SPEC, bwrap=str(fake)), where, str(exe), system="linux",
                                  environ={"PATH": "/usr/bin:/bin", "HOME": str(tmp)})
            for pid in rep["setsid_survivors"]:     # the unconfined probe's sleeper: not left running after the test
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGKILL)
            for want in ("a file of the run directory was readable", "a file was created in the run directory",
                         "a file was created in the client directory", "a file was created in the git directory"):
                self.assertIn(want, rep["problems"])
            self.assertTrue(any(p.startswith("a process the session left outlived it") for p in rep["problems"]), rep["problems"])
            # unconfined, no namespace is the probe's own: "shared" on Linux, "not measured" where /proc has none
            for n in ("user", "pid", "ipc", "uts", "mnt"):
                self.assertTrue(any(p.startswith(f"the {n} namespace is not the session's own (") for p in rep["problems"]),
                                (n, rep["problems"]))
            self.assertNotIn("own", rep["inside"]["namespaces"].values())
            self.assertTrue(rep["created_outside_workspace"]["run_directory"])
            # the probe's own files, wherever confinement failed to stop them, removed
            probe_dirs = (where, confine.pathlib.Path(confine.__file__).resolve().parents[1], exe.parent, where / "repo" / ".git")
            self.assertEqual([p for d in probe_dirs for p in d.glob("*") if p.name.startswith(("written-", ".aisef-confine-probe-"))], [])
            self.assertEqual(rep["tried"]["workspace"]["exit"], 0)
            self.assertEqual(rep["tried"]["read_git_directory"]["exit"], 0)
            self.assertEqual(rep["argv"][-4:], ["/bin/sh", "-c", "<PROBE>", "probe"])

    @unittest.skipUnless(os.name == "posix", "the probe is a POSIX shell script")
    def test_a_probe_that_did_not_exit_0_is_refused_even_when_it_reached_its_end(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(os.path.realpath(t))
            fake = fake_bwrap(tmp)
            fake.write_text(fake.read_text().replace('exec "$@"', '"$@"; exit 3'))
            exe = tmp / "client" / "opencode"
            exe.parent.mkdir()
            exe.write_text("#!/bin/sh\n")
            rep = confine.measure(dict(SPEC, bwrap=str(fake)), tmp / "run" / "confinement", str(exe), system="linux",
                                  environ={"PATH": "/usr/bin:/bin", "HOME": str(tmp)})
            for pid in rep["setsid_survivors"]:
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGKILL)
        self.assertTrue(rep["problems"][0].startswith("the sandbox did not run the probe (exit 3): "), rep["problems"])
        self.assertIn("setsid", rep["tried"])     # the probe ran to its end: only its exit refuses it

    def test_a_sleeper_still_dying_when_bubblewrap_returned_is_no_survivor(self):
        """The PID namespace's teardown can still be killing the probe's sleeper when bubblewrap returns (measured: 1 in
        400 measurements): one gone within SURVIVOR_GRACE is no survivor; one alive throughout it is, once it has passed."""
        from aisef2.runtime import process_range
        mine, other = (process_range.Proc(9, 1, None, None, "sleep 30.000001"), process_range.Proc(8, 1, None, None, "sleep 30.000002"))
        dying = mock.Mock(side_effect=[{9: mine, 8: other}, {9: mine, 8: other}, {8: other}])
        with mock.patch.object(process_range, "process_table", dying):
            self.assertEqual(confine._survivors("sleep 30.000001"), [])
        self.assertEqual(dying.call_count, 3)       # it looked again until the sleeper was gone
        alive = mock.Mock(return_value={9: mine, 8: other})
        with mock.patch.object(process_range, "process_table", alive), mock.patch.object(confine, "SURVIVOR_GRACE", 0.3):
            t = time.monotonic()
            self.assertEqual(confine._survivors("sleep 30.000001"), [9])
            self.assertGreaterEqual(time.monotonic() - t, 0.3)      # not before the grace has passed
        self.assertGreater(alive.call_count, 1)

    @unittest.skipUnless(os.name == "posix", "a real process table")
    def test_a_killed_sleeper_is_no_survivor_a_live_one_is(self):
        """Real processes: a sleeper killed (left unreaped: a zombie) is no survivor; one alive is. Two things each drop
        the killed one — the table leaves zombies out, and its command line no longer shows the sleeper (macOS `ps`:
        `<defunct>`; Linux: an empty /proc/<pid>/cmdline) — so this does not single out the zombie filter."""
        value = f"31.{os.getpid() % 10**6:06d}"      # no other process has it
        with mock.patch.object(confine, "SURVIVOR_GRACE", 0.3):
            live = subprocess.Popen(["sleep", value])
            try:
                self.assertEqual(confine._survivors(f"sleep {value}"), [live.pid])
                live.kill()
                self.assertEqual(confine._survivors(f"sleep {value}"), [])
            finally:
                live.kill()
                live.wait()

    @unittest.skipUnless(os.name == "posix", "the probe is a POSIX shell script")
    def test_the_sleeper_outlives_a_probe_that_used_all_its_time_and_the_grace(self):
        """A survivor is dropped only by being gone, so the probe's sleeper must not reach its own end before the last
        look: it lives longer than the probe's time limit plus SURVIVOR_GRACE plus 1 s for that look, so a probe that
        exits 0 just inside its limit still leaves a survivor alive to be seen."""
        real, probes = subprocess.run, []

        def spy(argv, *a, **k):
            if confine.PROBE in argv:       # the probe's $7 is its sleep: after PROBE, "probe" and $1..$6
                probes.append((argv[argv.index(confine.PROBE) + 8], k["timeout"]))
            return real(argv, *a, **k)
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(os.path.realpath(t))
            exe = tmp / "client" / "opencode"
            exe.parent.mkdir()
            exe.write_text("#!/bin/sh\n")
            with mock.patch.object(confine.subprocess, "run", spy):
                rep = confine.measure(dict(SPEC, bwrap=str(fake_bwrap(tmp))), tmp / "run" / "confinement", str(exe),
                                      system="linux", environ={"PATH": "/usr/bin:/bin", "HOME": str(tmp)})
            for pid in rep["setsid_survivors"]:
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGKILL)
        [(sleep, timeout)] = probes
        self.assertGreater(float(sleep), timeout + confine.SURVIVOR_GRACE + 1)
        self.assertTrue(rep["setsid_survivors"])     # the sleeper it looks for is this one: unconfined, it survived

    def test_no_client_no_measurement(self):
        """Without the client the session's wrapper cannot be built, so nothing is measured: a problem, and the
        measurement's worktree is removed."""
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(os.path.realpath(t))
            fake = fake_bwrap(tmp)
            where = tmp / "run" / "confinement"
            rep = confine.measure(dict(SPEC, bwrap=str(fake)), where, None, system="linux",
                                  environ={"PATH": "/usr/bin:/bin", "HOME": str(tmp)})
            self.assertEqual(rep["problems"], ["the client (opencode) is not on the PATH the run gives it: the session's "
                                               "wrapper cannot be measured"])
            self.assertFalse((where / "ws").exists())

    def test_a_namespace_counts_as_own_only_when_both_links_were_read_and_differ(self):
        self.assertEqual(confine.namespaces({"user": "user:[1]", "pid": "pid:[7]"}, {"user": "user:[2]", "pid": "pid:[7]"}),
                         {"user": "own", "pid": "shared"})
        for inside, outside in (("readlink: /proc/self/ns/user: No such file or directory", "user:[2]"), ("user:[1]", None),
                                ("pid:[1]", "user:[2]"), ("", "user:[2]"), (None, "user:[2]")):
            with self.subTest(inside=inside, outside=outside):
                self.assertEqual(confine.namespaces({"user": inside}, {"user": outside}), {"user": "not measured"})

    def test_each_check_refuses_on_its_own(self):
        """One departure at a time from a clean measurement: each check names it (none of them may be dropped)."""
        ws = pathlib.Path("/w/ws")

        def judged(change=lambda rep, tries: None, out="", home="/nonexistent"):
            rep = {"network": "host", "created_outside_workspace": {"kernel": False}, "setsid_survivors": [],
                   "inside": {"capabilities": dict.fromkeys(("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"), "0000000000000000"),
                              "no_new_privs": "1", "namespaces": dict.fromkeys(("user", "pid", "ipc", "uts", "mnt"), "own"),
                              "routed_interfaces": [], "home_listing": [], "unix_sockets": [],
                              "mounts": [{"at": "/", "access": "rw", "fs": "tmpfs"}, {"at": str(ws), "access": "rw", "fs": "ext4"}],
                              "mount_targets": [str(ws)]}}
            tries = {"read_canary": (1, "No such file or directory"), "workspace": (0, "ok"),
                     "read_git_directory": (0, "ref: x"), "user_namespace": (1, "unshare failed: No space left on device")}
            change(rep, tries)
            return confine._judge(rep, "tok", out, tries, home, ws)
        self.assertEqual(judged(), [])

        def inside(**kv):
            return lambda rep, tries: rep["inside"].update(kv)
        cases = [
            (dict(change=lambda rep, tries: tries.update(read_canary=(0, ""))), "a file of the run directory was readable"),
            (dict(change=lambda rep, tries: tries.pop("read_canary")), "a file of the run directory was readable"),
            (dict(out="tok"), "a file of the run directory was readable"),
            (dict(change=lambda rep, tries: rep["created_outside_workspace"].update(kernel=True)), "a file was created in the kernel"),
            (dict(change=lambda rep, tries: rep.update(setsid_survivors=[42])), "a process the session left outlived it: [42]"),
            (dict(change=lambda rep, tries: tries.update(workspace=(1, "ok"))), "the workspace was not writable"),
            (dict(change=lambda rep, tries: tries.update(workspace=(0, ""))), "the workspace was not writable"),
            (dict(change=lambda rep, tries: tries.pop("workspace")), "the workspace was not writable"),
            (dict(change=inside(no_new_privs="0")), "NoNewPrivs is 0, not 1"),
            (dict(change=inside(no_new_privs=None)), "NoNewPrivs is None, not 1"),
            (dict(change=inside(mounts=[])), "the mounts could not be read"),
            (dict(change=inside(mounts=[{"at": "/", "access": "rw", "fs": "tmpfs"}, {"at": "/srv", "access": "rw", "fs": "ext4"}],
                                mount_targets=[str(ws), "/srv"])), "writable outside the workspace: ['/srv']"),
            (dict(change=inside(home_listing=[".config", ".ssh"],
                                mounts=[{"at": "/", "access": "rw", "fs": "tmpfs"}, {"at": "/h/.config/opencode", "access": "ro", "fs": "ext4"}],
                                mount_targets=["/h/.config/opencode"]), home="/h"),
             "HOME shows more than the way to what is mounted: ['.ssh']"),
            (dict(change=lambda rep, tries: (rep.update(network="none"), rep["inside"]["namespaces"].update(net="shared"))),
             "the net namespace is not the session's own (shared)"),
            (dict(change=lambda rep, tries: (rep.update(network="none"), rep["inside"]["namespaces"].update(net="own"),
                                             rep["inside"].update(routed_interfaces=["eth0"]))),
             "network none has routes on ['eth0'] (a reachable network)"),
            # a path that only shares a prefix with an allowed one is outside it (/w/ws2 beside /w/ws, /usrlocal-extra beside /usr)
            (dict(change=inside(unix_sockets=["/w/ws2/control.sock"])),
             "a unix socket outside the workspace is reachable (read-only does not stop a connect): ['/w/ws2/control.sock']"),
            (dict(change=inside(mounts=[{"at": "/", "access": "rw", "fs": "tmpfs"}, {"at": str(ws), "access": "rw", "fs": "ext4"},
                                        {"at": "/usrlocal-extra", "access": "ro", "fs": "ext4"}], mount_targets=[str(ws), "/usr"])),
             "mounted beyond what the wrapper names: ['/usrlocal-extra']"),
        ]
        for k in ("CapInh", "CapPrm", "CapEff", "CapAmb"):
            for v in ("0000000000000001", None):
                cases.append((dict(change=lambda rep, tries, k=k, v=v: rep["inside"]["capabilities"].update({k: v})),
                              f"{k} is {v}, not 0"))
        for n in ("user", "pid", "ipc", "uts", "mnt"):
            for v in ("shared", "not measured"):
                cases.append((dict(change=lambda rep, tries, n=n, v=v: rep["inside"]["namespaces"].update({n: v})),
                              f"the {n} namespace is not the session's own ({v})"))
            cases.append((dict(change=lambda rep, tries, n=n: rep["inside"]["namespaces"].pop(n)),
                          f"the {n} namespace is not the session's own (not measured)"))
        for kw, want in cases:
            with self.subTest(want=want):
                self.assertIn(want, judged(**kw))
        self.assertEqual(judged(inside(home_listing=[".config"], mounts=[{"at": "/", "access": "rw", "fs": "tmpfs"},
                                                                       {"at": "/h/.config/opencode", "access": "ro", "fs": "ext4"}],
                                       mount_targets=["/h/.config/opencode"]), home="/h"), [])
        self.assertEqual(judged(inside(mounts=[{"at": "/", "access": "rw", "fs": "tmpfs"}, {"at": str(ws), "access": "rw", "fs": "ext4"},
                                               {"at": "/usr/local", "access": "ro", "fs": "ext4"}], mount_targets=[str(ws), "/usr"],
                                       unix_sockets=[str(ws / "s" / "own.sock")])), [])     # below a named path: within it

    def test_a_check_that_did_not_run_is_a_problem_never_a_pass(self):
        """The user-namespace denial counts only when the kernel's refusal is seen; unshare absent or no try at all
        is 'not measured'; and the mounts must be what the wrapper names."""
        ws = pathlib.Path("/w/ws")
        rep = {"network": "host", "created_outside_workspace": {}, "setsid_survivors": [],
               "inside": {"capabilities": dict.fromkeys(("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"), "0"),
                          "no_new_privs": "1", "namespaces": dict.fromkeys(("user", "pid", "ipc", "uts", "mnt"), "own"),
                          "routed_interfaces": [], "home_listing": [], "unix_sockets": [],
                          "mounts": [{"at": "/", "access": "rw", "fs": "tmpfs"}, {"at": str(ws), "access": "rw", "fs": "ext4"}],
                          "mount_targets": [str(ws)]}}
        tries = {"read_canary": (1, ""), "workspace": (0, "ok"), "read_git_directory": (0, "ref: x"),
                 "user_namespace": (1, "unshare: unshare failed: No space left on device")}
        self.assertEqual(confine._judge(rep, "tok", "", tries, "/nonexistent", ws), [])
        for userns in ((127, "unshare: absent"), (1, "unshare: unknown option"), None):
            t = {**tries, "user_namespace": userns} if userns else {k: v for k, v in tries.items() if k != "user_namespace"}
            with self.subTest(userns=userns):
                self.assertTrue(any(p.startswith("no refusal of a further user namespace was measured")
                                    for p in confine._judge(rep, "tok", "", t, "/nonexistent", ws)))
        self.assertIn("a user namespace could be created", confine._judge(rep, "tok", "", {**tries, "user_namespace": (0, "")},
                                                                          "/nonexistent", ws))
        self.assertIn("the workspace's git directory was not readable (git would not work in the session)",
                      confine._judge(rep, "tok", "", {**tries, "read_git_directory": (1, "No such file")}, "/nonexistent", ws))
        extra = {**rep, "inside": {**rep["inside"], "mounts": [*rep["inside"]["mounts"], {"at": "/srv", "access": "ro", "fs": "ext4"}],
                                   "unix_sockets": ["/run/x.sock", str(ws / "own.sock")]}}
        said = confine._judge(extra, "tok", "", tries, "/nonexistent", ws)
        self.assertIn("mounted beyond what the wrapper names: ['/srv']", said)
        self.assertTrue(any("unix socket outside the workspace is reachable" in p and "/run/x.sock" in p and "own.sock" not in p
                            for p in said), said)
        self.assertIn("the reachable unix sockets could not be listed (no find in the sandbox)",
                      confine._judge({**rep, "inside": {**rep["inside"], "unix_sockets": None}}, "tok", "", tries, "/nonexistent", ws))

    @unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
    def test_a_session_that_cannot_be_confined_never_starts_the_client(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(os.path.realpath(t))
            exe = tmp / "opencode"
            exe.write_text(f"#!/bin/sh\ntouch {tmp / 'ran'}\n")
            exe.chmod(0o755)
            limits = {"provider_requests": 9, "turns": 9, "input_tokens": 9, "output_tokens": 9}
            budget = client.Budget(limits, dict.fromkeys(limits, 0), tmp / "logs", lambda: 0)
            with self.assertRaisesRegex(client.SessionRefused, "bubblewrap is not an executable file|confinement is Linux-only"):
                client.session("n", "p", str(tmp), tmp / "logs" / "s.jsonl", 5, model="fakeprov/m", env={"PATH": "/usr/bin:/bin"},
                               budget=budget, turn_cap=3, exe=str(exe), confine=dict(SPEC, bwrap="/nonexistent/bwrap"))
            self.assertFalse((tmp / "ran").exists())
            self.assertFalse((tmp / "logs" / "s.jsonl").exists())


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class RunFailClosed(ProductBase):
    def test_a_run_that_asks_for_confinement_it_cannot_have_sends_nothing_and_records_why(self):
        self.settings = settings.load({**SETTINGS, "confinement": dict(SPEC, bwrap="/nonexistent/bwrap")})
        transport = provider()
        with self.assertRaisesRegex(R.RunRefused, "confinement was asked for and is not provided: (bubblewrap is not an "
                                                  "executable file|confinement is Linux-only)"):
            self.execute(transport=transport)
        self.assertEqual(transport.calls, [])
        rec = json.loads((self.tmp / "out" / "RUN.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["failure"]["stage"], "confinement")
        self.assertTrue(rec["confinement"]["problems"])
        self.assertFalse((self.tmp / "out" / "sessions").exists())

    def test_without_the_setting_the_record_has_no_confinement_and_the_sessions_are_not_wrapped(self):
        rec = self.execute()
        self.assertEqual(rec["delivery_verdict"], "PASS", rec)
        self.assertNotIn("confinement", rec)
        self.assertFalse(any("confinement" in s for s in rec["sessions"]))

    def test_a_confined_run_starts_every_session_through_bubblewrap_and_says_so(self):
        """The path a run takes when the measurement holds (stubbed here: macOS has no backend; the boundary is
        measured by validation/v21/sandbox): measured with the sessions' client and the run's repository, every
        developer and reviewer session started through the bubblewrap command line, each record and RUN.json saying so."""
        log = self.tmp / "bwrap.log"
        fake = fake_bwrap(self.tmp, log)
        spec = dict(SPEC, bwrap=str(fake))
        self.settings = settings.load({**SETTINGS, "confinement": spec})
        calls = []

        def measured(spec, where, exe, repo, **kw):
            calls.append((exe, repo, where))
            return {"network": spec["network"], "problems": [], "stub": "measurement stubbed"}
        with mock.patch.object(confine, "measure", measured), \
                mock.patch.object(confine, "wrap", functools.partial(confine.wrap, system="linux")):
            rec = self.execute()
        self.assertEqual(rec["delivery_verdict"], "PASS", rec)
        out = self.tmp / "out"
        self.assertEqual(calls, [(str(self.client), out / "repo", out / "confinement")])
        self.assertEqual(json.loads((out / "RUN.json").read_text(encoding="utf-8"))["confinement"]["stub"], "measurement stubbed")
        self.assertEqual(sorted(s["role"] for s in rec["sessions"]), ["developer", "reviewer"])
        self.assertEqual({s["role"]: s["confinement"] for s in rec["sessions"]},
                         {"developer": "bwrap network=host", "reviewer": "bwrap network=host workspace=read-only"})
        started = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(started), 2)
        for argv in started:
            cut = argv.index("--")
            self.assertEqual(argv[cut + 1], str(self.client))
            for flag in ("--unshare-user", "--unshare-pid", "--share-net", "--disable-userns", "--die-with-parent"):
                self.assertIn(flag, argv[:cut])
            self.assertIn(str(self.client.parent), ro_binds(argv))
            self.assertIn(str((out / "repo" / ".git").resolve()), ro_binds(argv))
        role = {argv[argv.index("--title", argv.index("--")) + 1].split()[0]: argv for argv in started}
        developer, reviewer = role["developer"], role["reviewer"]
        self.assertEqual(len(pairs(developer, "--bind")), 1)      # the developer writes its workspace, nothing else
        self.assertTrue(pairs(developer, "--bind")[0][0].startswith(str(out / "work" / "ws")))
        self.assertEqual(pairs(reviewer, "--bind"), [])           # the reviewer writes nothing of the host
        checkout = reviewer[reviewer.index("--chdir") + 1]
        self.assertEqual(pairs(reviewer, "--ro-bind")[-1], (checkout, checkout))
        self.assertTrue(checkout.startswith(str(out / "work" / "ws")))


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class Check(unittest.TestCase):
    setUp, cli = app_run.Command.setUp, app_run.Command.cli

    def test_check_is_not_ready_when_confinement_is_not_provided(self):
        (self.tmp / "settings.json").write_text(json.dumps({**SETTINGS, "confinement": dict(SPEC, bwrap="/nonexistent/bwrap")}),
                                                encoding="utf-8")
        from tests.v2.test_app_run import calibrations
        with mock.patch.object(R, "calibrations", calibrations):
            code, out, _ = self.cli("--check", "--project", str(self.tmp / "project.json"), "--settings",
                                    str(self.tmp / "settings.json"), "--repo", str(self.tmp / "source"))
        doc = json.loads(out)
        self.assertEqual((code, doc["ready"], doc["admission"]["admitted"]), (2, False, True))
        self.assertTrue(doc["confinement"]["problems"])

    def test_check_measures_with_the_client_on_the_runs_path(self):
        (self.tmp / "settings.json").write_text(json.dumps({**SETTINGS, "confinement": SPEC}), encoding="utf-8")
        exe = self.tmp / "bin" / "opencode"
        exe.parent.mkdir()
        exe.write_text("#!/bin/sh\n")
        exe.chmod(0o755)
        seen = []
        from tests.v2.test_app_run import calibrations
        with mock.patch.object(R, "calibrations", calibrations), \
                mock.patch.object(confine, "measure", lambda spec, where, client: seen.append(client) or {"problems": []}), \
                mock.patch.dict(os.environ, {"PATH": f"{exe.parent}{os.pathsep}/usr/bin{os.pathsep}/bin"}):
            code, out, _ = self.cli("--check", "--project", str(self.tmp / "project.json"), "--settings",
                                    str(self.tmp / "settings.json"), "--repo", str(self.tmp / "source"))
        self.assertEqual((code, json.loads(out)["ready"], seen), (0, True, [str(exe)]))


if __name__ == "__main__":
    unittest.main()
