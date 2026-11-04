"""V2.1 (F; REPORT §6, docs/v2.1/SANDBOX-LINUX.md): the confinement of the model sessions (aisef2/app/confine.py).

What runs everywhere (macOS too): the setting, the bubblewrap command line a session gets, and fail-closed — a run, a
`--check` or a session that asks for confinement and cannot have it refuses before any provider request and before
the client starts; and the measurement judges what it OBSERVES: a "bubblewrap" that runs the probe unconfined is
refused for what it let through, not for its name; and the path a confined run takes when the measurement holds —
every session started through bubblewrap, the record saying so. The boundary itself is measured on Linux by
validation/v21/sandbox (docker): this module never claims it. Every probe here that runs unconfined runs in a
disposable environment by construction (MEASURE), any other measurement gets a "bubblewrap" that runs nothing (one
that exits 97 at once, a directory or an absent path; the environment it would give the probe is the test's), and
each measuring test compares the host before and after (host_view): even when confinement — the very thing under
test — or the test's own set-up fails, nothing lands in the interpreter's site-packages, what a venv shares with
the interpreter (its standard library, its prefix), the tree or HOME."""

from __future__ import annotations

import copy
import functools
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import client, confine, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.runtime.process_range import ProcessRange  # noqa: E402
from tests.v2 import isolated_git  # noqa: E402
from tests.v2 import test_app_run as app_run  # noqa: E402 — the module, so its Command tests are not collected again
from tests.v2 import v21_r3_conf_rows as rows  # noqa: E402
from tests.v2.test_app_run import SETTINGS, ProductBase, provider  # noqa: E402

if str(ROOT / "validation" / "v2") not in sys.path:
    sys.path.insert(1, str(ROOT / "validation" / "v2"))
import cleanup_authority as ca  # noqa: E402  — INV-MUTATION-AUTHORITY: what the measurement reports is never permission

#: what a run may ask for: the shared network (a session must reach its provider); "none" is measurement-only
#: bwrap models a LINUX path on any host (confine.problem pins `startswith("/")`: the backend is Linux-only, so an
#: NT path is rightly refused); the OCR exe runs through the os-native `PurePath.is_absolute` check, so it is a path
#: absolute on THIS host. Nothing ever runs either binary; tests that run substitute their own.
SPEC = {"backend": "bwrap", "bwrap": "/usr/bin/bwrap", "network": "host", "read_only": []}
OCR = {"exe": str(pathlib.Path(tempfile.gettempdir(), "ocr")), "sha256": "0" * 64, "timeout_min": 1, "max_tokens": 9}
#: a "bubblewrap" that confines nothing: it drops every option and runs the command
NOT_A_SANDBOX = '#!/bin/sh\nwhile [ $# -gt 0 ] && [ "$1" != "--" ]; do shift; done\n[ $# -gt 0 ] || exit 0\nshift\nexec "$@"\n'
#: a "bubblewrap" for the tests that must never run anything under it: it runs no command, so a measurement that
#: reached its probe by a fault writes nothing anywhere
RUNS_NOTHING = "#!/bin/sh\nexit 97\n"


def _entries(d: str, deep: bool) -> dict:
    """{relative path: (size, mtime_ns) | "dir"} below `d` (its top level only unless `deep`), bytecode left out."""
    out = {}
    for root, dirs, files in os.walk(d):
        for x in files:
            st = os.lstat(os.path.join(root, x))
            out[os.path.relpath(os.path.join(root, x), d)] = (st.st_size, st.st_mtime_ns)
        out.update((os.path.relpath(os.path.join(root, x), d), "dir") for x in dirs if x != "__pycache__")
        dirs[:] = [x for x in dirs if deep and x != "__pycache__"]
    return out


def within(d: str | os.PathLike, p: str | os.PathLike) -> bool:
    """`p` is `d` or below it, both resolved."""
    d = os.path.realpath(d)
    return os.path.commonpath([d, os.path.realpath(p)]) == d


def base_paths() -> set[str]:
    """What a venv made from this interpreter still shares with it: its standard library (os.__file__ too), its
    installation prefix and the directory of its executable."""
    p = sysconfig.get_paths()
    return {p["stdlib"], sys.base_prefix, sys.base_exec_prefix, os.path.dirname(os.path.realpath(sys.executable)),
            os.path.dirname(os.__file__)}


def host_view() -> dict:
    """What no test here may change on the host, whatever the code under test computes: the entries at the top of this
    interpreter's site-packages and of what a venv shares with it (base_paths), and every file of the kernel tree
    (aisef2/) — names, sizes, mtimes — and the names at the top of the repository and of the account's home (other
    programs keep files there up to date, so new names only)."""
    try:
        import pwd
        homes = {os.path.expanduser("~"), pwd.getpwuid(os.getuid()).pw_dir}
    except (ImportError, KeyError):
        homes = {os.path.expanduser("~")}
    return {"exact": {**{f"site {p}": _entries(p, False) for p in {sysconfig.get_paths()[k] for k in ("purelib", "platlib")}},
                      **{f"base {p}": _entries(p, False) for p in base_paths() if os.path.isdir(p)},
                      "kernel": _entries(str(ROOT / "aisef2"), True)},
            "names": {f"names {p}": set(os.listdir(p)) for p in {*homes, str(ROOT)} if os.path.isdir(p)}}


def host_unchanged(before: dict) -> None:
    """Fails when anything appeared in, left or changed in the interpreter's site or the kernel tree, or a name
    appeared at the top of the repository or of the home, since `before` (host_view)."""
    after = host_view()
    bad = {k: {"new": sorted(set(v) - set(before["exact"][k])), "gone": sorted(set(before["exact"][k]) - set(v)),
               "changed": sorted(n for n in set(v) & set(before["exact"][k]) if v[n] != before["exact"][k][n])}
           for k, v in after["exact"].items() if v != before["exact"][k]}
    bad.update({k: {"new": sorted(v - before["names"][k])} for k, v in after["names"].items() if v - before["names"][k]})
    if bad:
        raise AssertionError(f"a test changed the host outside its own directories: {bad}")


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


#: `measure_in_range`'s child: confine.measure as a run calls it, the probe's own call recorded (its sleep, its timeout).
#: An unconfined probe's files are left where it made them (INV-MUTATION-AUTHORITY), so every place it can write is the
#: test's BY CONSTRUCTION, not by a patch a fault could get around: the child's interpreter is a throwaway venv (its
#: site-packages, however the code computes it, is the test's), the aisef2 it imports is a throwaway copy installed
#: there (so is the kernel directory), and its cwd, HOME, TMPDIR and XDG directories are the test's. What the venv
#: still shares with its base interpreter (base_paths: the standard library, the prefix, the executable's directory)
#: is not the test's: the test's directory must not lie in it, and no file the probe writes may either. It checks all
#: of that before it measures — and, before the probe runs, that each file the probe is given to write ($2-$4, $6,
#: $8, $9) is in the test's directory — and refuses otherwise: a broken construction never reaches the probe.
MEASURE = r'''import json, os, pathlib, sys, sysconfig
from unittest import mock
from aisef2.app import confine
io = pathlib.Path(sys.argv[1])
a = json.loads(io.read_text(encoding="utf-8"))
tmp = os.path.realpath(a["tmp"])
def within(d, p):
    return os.path.commonpath([os.path.realpath(d), os.path.realpath(p)]) == os.path.realpath(d)
def refuse(what):
    io.write_text(json.dumps({"refused": what}), encoding="utf-8")
    sys.exit(3)
p = sysconfig.get_paths()
base = {p["stdlib"], sys.base_prefix, sys.base_exec_prefix, os.path.dirname(os.path.realpath(sys.executable)),
        os.path.dirname(os.__file__)}
seen = {"interpreter": sys.prefix, "kernel": confine.__file__, "cwd": os.getcwd(), "where": a["where"], "client": a["exe"],
        **{k: p[k] for k in ("purelib", "platlib")},
        **{k: os.environ.get(k, "/") for k in ("HOME", "TMPDIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
                                               "XDG_CACHE_HOME")}}
outside = {k: v for k, v in seen.items() if not within(tmp, v)}
shared = {k: v for k, v in seen.items() if any(within(b, v) for b in base)}
if outside or shared:
    refuse({"outside the test's directory": outside, "in the base interpreter": shared})
real, probes = confine.subprocess.run, []
def spy(argv, *x, **k):
    if confine.PROBE in argv:       # after PROBE: "probe", then $1..$9 — $7 is its sleep
        at = argv[argv.index(confine.PROBE) + 1:]
        bad = [at[i] for i in (2, 3, 4, 6, 8, 9) if not within(tmp, at[i]) or any(within(b, at[i]) for b in base)]
        if bad:
            refuse({"the probe would write": bad})
        probes.append((at[7], k["timeout"]))
    return real(argv, *x, **k)
with mock.patch.object(confine.subprocess, "run", spy):
    rep = confine.measure(a["spec"], pathlib.Path(a["where"]), a["exe"], system="linux", environ=a["environ"])
io.write_text(json.dumps({"rep": rep, "probes": probes}), encoding="utf-8")
'''
#: what the venv's own interpreter says it is: the paths measure_in_range checks before it copies anything there
VENV_PATHS = ("import json, sys, sysconfig; p = sysconfig.get_paths(); "
              "print(json.dumps({'prefix': sys.prefix, 'purelib': p['purelib'], 'platlib': p['platlib']}))")


def measure_in_range(tmp: pathlib.Path, spec: dict, where: pathlib.Path, exe: pathlib.Path) -> tuple[dict, list, pathlib.Path]:
    """(report, the probe's calls, the child's site-packages) of confine.measure run as the target of a process range
    this test starts, in the disposable environment MEASURE checks (a venv in `tmp` holding a copy of this tree's
    aisef2), so the sleeper an unconfined probe leaves is provably the test's — never a pid the measurement reports
    (INV-MUTATION-AUTHORITY): on macOS (no setsid) it stays in the range's group, which release() signals; on Linux
    setsid takes it out of the group and the range's anchor, a subreaper, adopts it, so cleanup_authority proves it
    from its own reading of the host (the anchor the test's child, both born after the boundary) and only then signals
    it. One it cannot prove is never signalled: release() raises RangeEscaped and the test fails. Nothing is copied
    into the venv until it is shown to be the test's: its prefix, purelib and platlib in `tmp`, and `tmp` not in what
    it shares with its base interpreter."""
    io = tmp / "measure.json"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(tmp / "venv")], check=True)
    py = tmp / "venv" / "bin" / "python"
    paths = json.loads(subprocess.run([str(py), "-I", "-c", VENV_PATHS], capture_output=True, encoding="utf-8",
                                      check=True).stdout)
    outside = {k: v for k, v in paths.items() if not within(tmp, v)}
    shared = sorted(b for b in base_paths() if within(b, tmp))
    if outside or shared:
        raise AssertionError(f"the venv is not the test's (outside {tmp}: {outside}; {tmp} in the base interpreter's "
                             f"{shared}): nothing was copied into it")
    site = pathlib.Path(paths["purelib"])
    shutil.copytree(ROOT / "aisef2", site / "aisef2", ignore=shutil.ignore_patterns("__pycache__"))
    own = {k: tmp / "child" / k.lower() for k in ("cwd", "HOME", "TMPDIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
                                                  "XDG_STATE_HOME", "XDG_CACHE_HOME")}
    for d in own.values():
        d.mkdir(parents=True)
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": os.environ.get("LANG", "C"),
           **{k: str(d) for k, d in own.items() if k != "cwd"}}
    io.write_text(json.dumps({"spec": spec, "where": str(where), "exe": str(exe), "tmp": str(tmp),
                              "environ": {"PATH": "/usr/bin:/bin", "HOME": str(tmp)}}), encoding="utf-8")
    boundary = ca.establish(tmp)
    with open(tmp / "measure.log", "wb") as log:
        r = ProcessRange("confine.measure", [str(py), "-I", "-B", "-c", MEASURE, str(io)], cwd=own["cwd"], env=env,
                         output=log, grace_s=(0.1, 2.0), wait_s=10.0).start()
    try:
        r.wait(confine.PROBE_TIMEOUT + 60)
        # every process cleanup_authority PROVES is the runner's (born after the boundary, parent chain to the runner;
        # the runner itself excluded), not only the anchor's direct children. Under CI load a probe can exceed
        # PROBE_TIMEOUT so the timeout SIGKILLs only the direct bwrap child; the setsid'd sleeper then re-parents to the
        # anchor under a surviving probe shell, so its ppid is that shell, not the anchor — the old `ppid == r.group`
        # filter missed it and release() raised RangeEscaped on the live escapee. signal_owned only ever signals
        # proven-owned processes (INV-MUTATION-AUTHORITY: an independent controller view), so widening the selection is
        # sound; on macOS (no setsid) nothing extra is owned at this point, so the path is unchanged.
        adopted = [p.pid for p in ca.owned(boundary).values() if p.pid != r.group]
        ca.signal_owned(boundary, pids=adopted)
    finally:
        r.release()
    out = json.loads(io.read_text(encoding="utf-8"))
    if "refused" in out:
        raise AssertionError(f"the measurement's child refused to measure outside a disposable environment: {out['refused']}")
    if "rep" not in out:
        raise AssertionError(f"the measurement did not answer: {(tmp / 'measure.log').read_text(errors='replace')[-2000:]}")
    return out["rep"], out["probes"], site


class HostGuard(unittest.TestCase):
    def test_it_fails_on_what_appeared_changed_or_left_since_its_view(self):
        """host_unchanged against a doctored view — never by writing the host."""
        view = host_view()
        host_unchanged(view)
        f = next(n for n, v in view["exact"]["kernel"].items() if v != "dir")
        top = sorted(view["names"][f"names {ROOT}"])[0]
        for doctor, said in ((lambda b: b["exact"]["kernel"].pop(f), f"'new': [{f!r}]"),
                             (lambda b: b["exact"]["kernel"].update({f: (-1, 0)}), f"'changed': [{f!r}]"),
                             (lambda b: b["exact"]["kernel"].update({"gone.py": (0, 0)}), "'gone': ['gone.py']"),
                             (lambda b: b["names"][f"names {ROOT}"].discard(top), f"'new': [{top!r}]")):
            before = copy.deepcopy(view)
            doctor(before)
            with self.subTest(said=said), self.assertRaisesRegex(AssertionError, re.escape(said)):
                host_unchanged(before)
        self.assertIn(f"base {os.path.dirname(os.__file__)}", view["exact"])     # the standard library a venv shares

    @unittest.skipUnless(os.name == "posix", "the probe is a POSIX shell script")
    def test_nothing_is_copied_or_probed_outside_the_tests_directory(self):
        """measure_in_range copies nothing into a venv that is not the test's (its interpreter answering a site
        elsewhere: round 1's E1); and MEASURE refuses, before the probe runs, a probe file outside the test's
        directory — here a kernel copy whose interpreter-site file is in the base interpreter's standard library.
        The bubblewrap runs nothing, so a guard that failed would show as a measurement, not as a write."""
        real_run, real_copy = subprocess.run, shutil.copytree
        with tempfile.TemporaryDirectory() as t:
            tmp, bait = pathlib.Path(os.path.realpath(t)) / "m", pathlib.Path(os.path.realpath(t)) / "bait"
            bait.mkdir()

            def lying(argv, *a, **k):
                if isinstance(argv, list) and VENV_PATHS in argv:
                    return subprocess.CompletedProcess(argv, 0, json.dumps(dict.fromkeys(("prefix", "purelib", "platlib"),
                                                                                         str(bait))), "")
                return real_run(argv, *a, **k)

            def faulty(src, dst, *a, **k):
                done = real_copy(src, dst, *a, **k)     # copytree's own recursion comes back through here
                c = pathlib.Path(dst, "app", "confine.py")
                if c.exists():   # the copy is the committed text, or the runner's null mutant of it (ast.unparse: 'purelib')
                    c.write_text(re.sub(r"""get_paths\(\)\[(['"])purelib\1\]\) / probe_file""",
                                        'get_paths()["stdlib"]) / probe_file', c.read_text(encoding="utf-8")), encoding="utf-8")
                return done
            for patch, refused in ((mock.patch.object(subprocess, "run", lying), "the venv is not the test's .* nothing was "
                                    "copied into it"),
                                   (mock.patch.object(shutil, "copytree", faulty), "refused .*'the probe would write': \\['"
                                    + re.escape(sysconfig.get_paths()["stdlib"]))):
                (tmp / "client").mkdir(parents=True)
                fake = tmp / "bwrap"
                fake.write_text(RUNS_NOTHING)
                fake.chmod(0o755)
                (tmp / "client" / "opencode").write_text("#!/bin/sh\n")
                with self.subTest(refused=refused), patch, self.assertRaisesRegex(AssertionError, refused):
                    measure_in_range(tmp, dict(SPEC, bwrap=str(fake)), tmp / "run" / "confinement", tmp / "client" / "opencode")
                self.assertEqual(os.listdir(bait), [])
                tmp = tmp.with_name(tmp.name + "2")


class OwnGit(unittest.TestCase):
    def test_the_set_up_git_never_reaches_the_callers_repository(self):
        """Run from a pre-commit hook of a linked worktree, a test inherits GIT_DIR and GIT_INDEX_FILE (absolute paths):
        CommandLine's git runs in its own temporary repository all the same, and the caller's is left as it was."""
        with tempfile.TemporaryDirectory() as t:
            bait = pathlib.Path(os.path.realpath(t)) / "bait"
            bait.mkdir()
            isolated_git.git(bait, "init", "-q", "-b", "main")
            isolated_git.git(bait, "commit", "-q", "--allow-empty", "-m", "bait")
            before, result = _entries(str(bait / ".git"), True), unittest.TestResult()
            with mock.patch.dict(os.environ, {"GIT_DIR": str(bait / ".git"), "GIT_INDEX_FILE": str(bait / ".git" / "index"),
                                              "GIT_WORK_TREE": str(bait)}):
                CommandLine("test_the_measured_wrapper_is_the_sessions_own").run(result)
            self.assertEqual((result.testsRun, result.errors, result.failures), (1, [], []))
            self.assertEqual(_entries(str(bait / ".git"), True), before)

    def test_a_hook_in_the_tests_repository_never_runs(self):
        """A git whose compiled-in template directory carries an executable hook copies it into every repository a test
        initialises (GIT_TEMPLATE_DIR and the configuration are not read; that directory is): isolated_git.git runs git
        with the hook path the null device, as the runner's own git does, so no hook in a test's repository runs."""
        with tempfile.TemporaryDirectory() as t:
            repo = pathlib.Path(t) / "r"
            repo.mkdir()
            isolated_git.git(repo, "init", "-q", "-b", "main")
            hook = repo / ".git" / "hooks" / "pre-commit"
            hook.parent.mkdir(exist_ok=True)
            hook.write_text("#!/bin/sh\necho ran > hook-ran\n", encoding="utf-8")
            hook.chmod(0o755)
            isolated_git.git(repo, "commit", "-q", "--allow-empty", "-m", "base")
            self.assertFalse((repo / "hook-ran").exists())


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
        self.addCleanup(host_unchanged, host_view())
        self.bwrap = self.tmp / "bwrap"
        self.bwrap.write_text(RUNS_NOTHING)       # nothing here runs it: the command line is only built
        self.bwrap.chmod(0o755)
        self.home, self.run_dir = self.tmp / "home", self.tmp / "out"
        (self.home / ".config" / "opencode").mkdir(parents=True)
        repo = self.run_dir / "repo"
        repo.mkdir(parents=True)
        # isolated_git.git: no GIT_* variable of the caller (a hook's GIT_DIR / GIT_INDEX_FILE would take these to the
        # developer's repository), no system or global configuration
        isolated_git.git(repo, "init", "-q", "-b", "main")
        isolated_git.git(repo, "commit", "-q", "--allow-empty", "-m", "base")
        self.ws = self.run_dir / "work" / "ws" / "wt-S1"
        isolated_git.git(repo, "worktree", "add", "-q", "--detach", str(self.ws))
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
        bare = self.tmp / "bare-home"       # a HOME whose .config has no opencode/ directory
        (bare / ".config").mkdir(parents=True)
        self.env["HOME"] = str(bare)
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
        self.assertNotIn("confinement", isolated_git.git(self.run_dir / "repo", "worktree", "list", "--porcelain"))


class FailClosed(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(host_unchanged, host_view())

    def test_a_host_that_is_not_linux_has_no_backend(self):
        with self.assertRaisesRegex(confine.Unavailable, "Linux-only .* this host is darwin: no backend"):
            confine.wrap(SPEC, ["x"], {}, "/w", system="darwin")
        with tempfile.TemporaryDirectory() as t:
            fake = pathlib.Path(t) / "bwrap"        # a fault past the host check still reaches no probe
            fake.write_text(RUNS_NOTHING)
            fake.chmod(0o755)
            rep = confine.measure(dict(SPEC, bwrap=str(fake)), pathlib.Path(t) / "c", system="darwin",
                                  environ={"PATH": "/usr/bin:/bin", "HOME": t})
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
            rep, _, site = measure_in_range(tmp, dict(SPEC, bwrap=str(fake)), where, exe)   # its sleeper not left running
            for want in ("a file of the run directory was readable", "a file was created in the run directory",
                         "a file was created in the client directory", "a file was created in the git directory",
                         "a file was created in the kernel", "a file was created in the interpreter site"):
                self.assertIn(want, rep["problems"])
            self.assertTrue(any(p.startswith("a process the session left outlived it") for p in rep["problems"]), rep["problems"])
            # unconfined, no namespace is the probe's own: "shared" on Linux, "not measured" where /proc has none
            for n in ("user", "pid", "ipc", "uts", "mnt"):
                self.assertTrue(any(p.startswith(f"the {n} namespace is not the session's own (") for p in rep["problems"]),
                                (n, rep["problems"]))
            self.assertNotIn("own", rep["inside"]["namespaces"].values())
            self.assertTrue(rep["created_outside_workspace"]["run_directory"])
            # the probe's own files, wherever confinement did not stop them: left where it made them and named in the
            # refusal, nothing removed — they are the subject's (INV-MUTATION-AUTHORITY; the measurement used to delete
            # them). MEASURE's kernel and interpreter site are the test's venv and its copy: the real ones get none
            probe_dirs = (where, site / "aisef2", site, exe.parent, where / "repo" / ".git")
            left = [str(p) for d in probe_dirs for p in d.glob("*") if p.name.startswith(("written-", ".aisef-confine-probe-"))]
            self.assertEqual(len(left), 5, left)
            self.assertEqual(sorted(rep["left_on_host"]), sorted(left))
            self.assertIn(f"the probe's files are left where confinement did not stop them; nothing was removed, the "
                          f"operator removes them: {rep['left_on_host']}", rep["problems"])
            self.assertEqual(list(pathlib.Path(confine.__file__).resolve().parents[1].glob(".aisef-confine-probe-*")), [])
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
            rep, _, _ = measure_in_range(tmp, dict(SPEC, bwrap=str(fake)), tmp / "run" / "confinement", exe)
        self.assertTrue(rep["problems"][0].startswith("the sandbox did not run the probe (exit 3): "), rep["problems"])
        self.assertIn("setsid", rep["tried"])     # the probe ran to its end: only its exit refuses it
        self.assertTrue(rep["left_on_host"])      # its files are named even though nothing else was judged
        self.assertEqual(rep["problems"][1:], [f"the probe's files are left where confinement did not stop them; nothing "
                                               f"was removed, the operator removes them: {rep['left_on_host']}"])

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

    def test_the_grace_used_is_survivor_grace_so_a_sleeper_ending_just_after_it_is_still_a_survivor(self):
        """A survivor is dropped only by being gone, and the sleeper's lifetime is set against SURVIVOR_GRACE: a longer
        grace than that lets a real survivor reach its own end inside it and go unreported (fail-open). On a clock of
        the test's own, a sleeper alive until just after SURVIVOR_GRACE is a survivor, judged once the grace passed."""
        from aisef2.runtime import process_range
        mine, other = (process_range.Proc(9, 1, None, None, "sleep 30.000001"), process_range.Proc(8, 1, None, None, "sleep 30.000002"))
        clock, ends = [0.0], confine.SURVIVOR_GRACE + 0.5
        fake = types.SimpleNamespace(monotonic=lambda: clock[0], sleep=lambda s: clock.__setitem__(0, clock[0] + s))

        def table():
            return {9: mine, 8: other} if clock[0] < ends else {8: other}
        with mock.patch.object(process_range, "process_table", table), mock.patch.object(confine, "time", fake):
            self.assertEqual(confine._survivors("sleep 30.000001"), [9])
        self.assertGreaterEqual(clock[0], confine.SURVIVOR_GRACE)

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
        exits 0 just inside its limit still leaves a survivor alive to be seen (the probe's call: MEASURE's spy)."""
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(os.path.realpath(t))
            exe = tmp / "client" / "opencode"
            exe.parent.mkdir()
            exe.write_text("#!/bin/sh\n")
            rep, probes, _ = measure_in_range(tmp, dict(SPEC, bwrap=str(fake_bwrap(tmp))), tmp / "run" / "confinement", exe)
        [(sleep, timeout)] = probes
        self.assertGreater(float(sleep), timeout + confine.SURVIVOR_GRACE + 1)
        self.assertTrue(rep["setsid_survivors"])     # the sleeper it looks for is this one: unconfined, it survived

    def test_no_client_no_measurement(self):
        """Without the client the session's wrapper cannot be built, so nothing is measured: a problem, and the
        measurement's worktree is removed."""
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(os.path.realpath(t))
            fake = tmp / "bwrap"
            fake.write_text(RUNS_NOTHING)
            fake.chmod(0o755)
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
        ws = pathlib.PurePosixPath("/w/ws")     # the report models a LINUX sandbox: its paths stay POSIX on any host

        def judged(change=lambda rep, tries: None, out="", home="/nonexistent"):
            rep = {"network": "host", "created_outside_workspace": {"kernel": False}, "setsid_survivors": [],
                   "host_mounts": rows.HOST,
                   "inside": {"capabilities": dict.fromkeys(("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"), "0000000000000000"),
                              "no_new_privs": "1", "namespaces": dict.fromkeys(("user", "pid", "ipc", "uts", "mnt"), "own"),
                              "routed_interfaces": [], "home_listing": [], "unix_sockets": [],
                              "mounts": [rows.mount("/"), {"at": str(ws), "access": "rw", "fs": "ext4"}],
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
            (dict(change=inside(mounts=[rows.mount("/"), {"at": "/srv", "access": "rw", "fs": "ext4"}],
                                mount_targets=[str(ws), "/srv"])), "writable outside the workspace: ['/srv']"),
            (dict(change=inside(home_listing=[".config", ".ssh"],
                                mounts=[rows.mount("/"), {"at": "/h/.config/opencode", "access": "ro", "fs": "ext4"}],
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
            (dict(change=inside(mounts=[rows.mount("/"), {"at": str(ws), "access": "rw", "fs": "ext4"},
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
        self.assertEqual(judged(inside(home_listing=[".config"], mounts=[rows.mount("/"),
                                                                       {"at": "/h/.config/opencode", "access": "ro", "fs": "ext4"}],
                                       mount_targets=["/h/.config/opencode"]), home="/h"), [])
        self.assertEqual(judged(inside(mounts=[rows.mount("/"), {"at": str(ws), "access": "rw", "fs": "ext4"},
                                               {"at": "/usr/local", "access": "ro", "fs": "ext4"}], mount_targets=[str(ws), "/usr"],
                                       unix_sockets=[str(ws / "s" / "own.sock")])), [])     # below a named path: within it

    def test_a_check_that_did_not_run_is_a_problem_never_a_pass(self):
        """The user-namespace denial counts only when the kernel's refusal is seen; unshare absent or no try at all
        is 'not measured'; and the mounts must be what the wrapper names."""
        ws = pathlib.PurePosixPath("/w/ws")     # the report models a LINUX sandbox: its paths stay POSIX on any host
        rep = {"network": "host", "created_outside_workspace": {}, "setsid_survivors": [], "host_mounts": rows.HOST,
               "inside": {"capabilities": dict.fromkeys(("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"), "0"),
                          "no_new_privs": "1", "namespaces": dict.fromkeys(("user", "pid", "ipc", "uts", "mnt"), "own"),
                          "routed_interfaces": [], "home_listing": [], "unix_sockets": [],
                          "mounts": [rows.mount("/"), {"at": str(ws), "access": "rw", "fs": "ext4"}],
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
