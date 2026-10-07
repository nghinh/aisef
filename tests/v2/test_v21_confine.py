"""V2.1 (F; REPORT §6, docs/v2.1/SANDBOX-LINUX.md): the confinement of the model sessions (aisef2/app/confine.py).

What runs everywhere (macOS too): the setting, the bubblewrap command line a session gets, and fail-closed — a run, a
`--check` or a session that asks for confinement and cannot have it refuses before any provider request and before
the client starts; and the measurement judges what it OBSERVES: a "bubblewrap" that runs the probe unconfined is
refused for what it let through, not for its name. The boundary itself is measured on Linux by
validation/v21/sandbox (docker): this module never claims it."""

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

from aisef2.app import client, confine, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from tests.v2.test_app_run import SETTINGS, Command, ProductBase, provider  # noqa: E402

SPEC = {"backend": "bwrap", "bwrap": "/usr/bin/bwrap", "network": "none", "read_only": []}
#: a "bubblewrap" that confines nothing: it drops every option and runs the command
NOT_A_SANDBOX = '#!/bin/sh\nwhile [ $# -gt 0 ] && [ "$1" != "--" ]; do shift; done\n[ $# -gt 0 ] || exit 0\nshift\nexec "$@"\n'


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
                         ({k: v for k, v in SPEC.items() if k != "read_only"}, "confinement is")):
            with self.subTest(bad=bad), self.assertRaisesRegex(settings.SettingsError, why):
                settings.load({**SETTINGS, "confinement": bad})


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
        argv, _ = self.wrap()
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

    def test_network_host_shares_the_network_and_says_so(self):
        argv, _ = self.wrap(network="host")
        self.assertIn("--share-net", argv)
        self.assertNotIn("--unshare-net", argv)


class FailClosed(unittest.TestCase):
    def test_a_host_that_is_not_linux_has_no_backend(self):
        with self.assertRaisesRegex(confine.Unavailable, "Linux-only .* this host is darwin: no backend"):
            confine.wrap(SPEC, ["x"], {}, "/w", system="darwin")
        with tempfile.TemporaryDirectory() as t:
            rep = confine.measure(SPEC, pathlib.Path(t) / "c", system="darwin")
        self.assertEqual(rep["problems"], ["confinement is Linux-only (bubblewrap); this host is darwin: no backend"])

    def test_a_missing_bubblewrap_or_read_only_path_is_refused(self):
        with self.assertRaisesRegex(confine.Unavailable, "not an executable at /nonexistent/bwrap"):
            confine.wrap(dict(SPEC, bwrap="/nonexistent/bwrap"), ["x"], {}, "/w", system="linux")
        with self.assertRaisesRegex(confine.Unavailable, "do not exist: \\['/nonexistent/ro'\\]"):
            confine.wrap(dict(SPEC, bwrap=sys.executable, read_only=["/nonexistent/ro"]), ["x"], {}, "/w", system="linux")

    @unittest.skipUnless(os.name == "posix", "the probe is a POSIX shell script")
    def test_what_is_measured_decides_not_the_name_of_the_tool(self):
        """A 'bubblewrap' that runs the probe unconfined: refused for what the probe could do."""
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(os.path.realpath(t))
            fake = tmp / "bwrap"
            fake.write_text(NOT_A_SANDBOX)
            fake.chmod(0o755)
            where = tmp / "run" / "confinement"
            rep = confine.measure(dict(SPEC, bwrap=str(fake)), where, system="linux",
                                  environ={"PATH": "/usr/bin:/bin", "HOME": str(tmp)})
            self.assertIn("a file of the run directory was readable", rep["problems"])
            self.assertIn("a file was created in the run directory", rep["problems"])
            self.assertTrue(any(p.startswith("a process the session left outlived it") for p in rep["problems"]), rep["problems"])
            self.assertTrue(rep["created_outside_workspace"]["run_directory"])
            self.assertFalse((where / "written-from-inside").exists())     # the probe's own file, removed
            self.assertEqual(rep["tried"]["workspace"]["exit"], 0)
            self.assertEqual(rep["argv"][-4:], ["/bin/sh", "-c", "<PROBE>", "probe"])

    @unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
    def test_a_session_that_cannot_be_confined_never_starts_the_client(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(os.path.realpath(t))
            exe = tmp / "opencode"
            exe.write_text(f"#!/bin/sh\ntouch {tmp / 'ran'}\n")
            exe.chmod(0o755)
            limits = {"provider_requests": 9, "turns": 9, "input_tokens": 9, "output_tokens": 9}
            budget = client.Budget(limits, dict.fromkeys(limits, 0), tmp / "logs", lambda: 0)
            with self.assertRaisesRegex(client.SessionRefused, "bubblewrap is not an executable|confinement is Linux-only"):
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
                                                  "executable|confinement is Linux-only)"):
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


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class Check(unittest.TestCase):
    setUp, cli = Command.setUp, Command.cli

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


if __name__ == "__main__":
    unittest.main()
