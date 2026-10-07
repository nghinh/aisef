"""The mutation runner's own contract (docs/v2.1/MUTATION-RUNNER-V2.md), on toy targets and toy kill files built in a
temporary root and driven through the real `run_target` (and `mutants`, `_run_tests`, `main`), the real ProcessRange
and the real cleanup authority. Each case builds the situation a confirmed finding of the V2.1 runner audit described,
asserts the designed truth per mutant, and — where a protection can be switched off — shows the old failure with it
off, so a toy that no longer exercises the channel fails instead of passing vacuously. Not a kill file."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v2 import mutation as m  # noqa: E402

POSIX = os.name == "posix"


def toy(base: pathlib.Path, module: str, files: dict[str, str], name: str = "toy") -> pathlib.Path:
    """A root holding aisef2/<name>.py and the kill files tests/v2/<file> (dedented)."""
    root = base / "root"
    for rel, text in {"aisef2/__init__.py": "", f"aisef2/{name}.py": module, "tests/v2/__init__.py": "",
                      **{f"tests/v2/{k}": textwrap.dedent(v) for k, v in files.items()}}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def killed(result: dict) -> list[bool]:
    return [r["killed"] for r in result["results"]]


# --------------------------------------------------------------------------------------------- §1 bytecode

#: v(1) is all the kill file asks, through an isolated child that writes its bytecode into the tree (BC-2)
BC_MODULE = "def v(x):\n    if x == 1:\n        return 'aa'\n    return 'bb'\n"
BC_KILL = {"test_k.py": """
    import pathlib, subprocess, sys, unittest
    TREE = str(pathlib.Path(__file__).resolve().parents[2])
    class K(unittest.TestCase):
        def test_v1_through_an_isolated_child(self):
            code = f"import sys; sys.path.insert(0, {TREE!r}); from aisef2.toy import v; print(v(1))"
            out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True).stdout
            self.assertEqual(out.strip(), "aa")
    """}
#: generator order: condition negated, L4 returns None, Eq->NotEq, L3 returns None, 'bb' emptied, 'aa' emptied
BC_TRUTH = [True, False, True, True, False, True]


class Bytecode(unittest.TestCase):
    """BC-1, BC-2, BC-4, ORD-3: a version of the mutated file never runs another version's bytecode."""

    def setUp(self) -> None:
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = pathlib.Path(d.name)
        self.mod = self.dir / "bcmod.py"

    def child(self, *flags: str, env: dict | None = None) -> str:
        code = f"import sys; sys.path.insert(0, {str(self.dir)!r}); import bcmod; print(bcmod.V)"
        return subprocess.run([sys.executable, *flags, "-c", code], capture_output=True, text=True, check=True,
                              env=env).stdout.strip()

    def test_a_same_size_same_second_version_reuses_the_cache_without_the_stamp(self):
        """The trap is live on this host: an -I child writes the .pyc, a -B child with PYTHONDONTWRITEBYTECODE reads
        it for a different version of one size written in the same whole second."""
        self.mod.write_text("V = 'A'\n", encoding="utf-8")
        second = int(self.mod.stat().st_mtime)
        os.utime(self.mod, (second, second))
        self.assertEqual(self.child("-I"), "A")
        self.mod.write_text("V = 'B'\n", encoding="utf-8")
        os.utime(self.mod, (second, second))
        self.assertEqual(self.child("-B", env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}), "A")

    def test_write_version_makes_the_next_import_compile_the_new_bytes(self):
        prefix = self.dir / "prefix"
        last = m._write_version(self.mod, "V = 'A'\n", 0)
        self.assertEqual(self.child("-I"), "A")
        for i, value in enumerate("BCDEFGHIJKLMNOPQRSTU"):
            last = m._write_version(self.mod, f"V = '{value}'\n", last)
            with self.subTest(i=i):
                self.assertEqual(self.child("-B", env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}), value)
                self.assertEqual(self.child("-I"), value)
                # BC-4: a cache under a pycache prefix is refused the same way, wherever it lives
                self.assertEqual(self.child(env={**os.environ, "PYTHONPYCACHEPREFIX": str(prefix)}), value)

    def test_stamps_are_strictly_increasing_whole_seconds_above_the_original(self):
        self.mod.write_text("V = 0\n", encoding="utf-8")
        original = int(self.mod.stat().st_mtime)
        last, seen = original, []
        begun = time.monotonic()
        for i in range(30):
            last = m._write_version(self.mod, f"V = {i % 10}\n", last)
            st = self.mod.stat()
            self.assertEqual(st.st_mtime, int(st.st_mtime))      # whole seconds: an ns-only stamp is worse than none
            seen.append(int(st.st_mtime))
        self.assertLess(time.monotonic() - begun, 5)
        self.assertEqual(seen, sorted(set(seen)))
        self.assertGreater(seen[0], original)

    @unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
    def test_consecutive_same_size_mutants_are_classified_by_their_own_bytes(self):
        root = toy(self.dir, BC_MODULE, BC_KILL)
        src = (root / "aisef2/toy.py").read_text(encoding="utf-8")
        found = m.mutants(src, "v", {})
        sizes = [len(s) for _, s in found]
        # not vacuous: same-size neighbours whose designed classes differ, so a stale .pyc would show
        self.assertTrue(any(sizes[i] == sizes[i + 1] and BC_TRUTH[i] != BC_TRUTH[i + 1] for i in range(len(found) - 1)))
        self.assertEqual(killed(m.run_target(root, "aisef2/toy.py::v", ["tests/v2/test_k.py"])), BC_TRUTH)
        # the old failure, with the stamp switched off: every version in one whole second
        fixed = int((root / "aisef2/toy.py").stat().st_mtime) + 1

        def same_second(path, text, last):
            path.write_text(text, encoding="utf-8")
            os.utime(path, (fixed, fixed))
            return fixed
        with mock.patch.object(m, "_write_version", same_second):
            self.assertNotEqual(killed(m.run_target(root, "aisef2/toy.py::v", ["tests/v2/test_k.py"])), BC_TRUTH)


# --------------------------------------------------------------------------------------------- §2 clean environment

#: tidy() writes .scratch into the cwd (the tree) only for its mutants "condition negated" and "True->False"
TIDY = ("import pathlib\n\n\ndef tidy(flag=True):\n    if flag:\n        return 'clean'\n"
        "    pathlib.Path('.scratch').write_text('x')\n    return 'dirty'\n")
TIDY_FILES = {
    "test_s.py": """
        import unittest
        from aisef2.toy import tidy
        class S(unittest.TestCase):
            def test_tidy_runs(self):
                tidy()
        """,
    "test_c.py": """
        import pathlib, unittest
        class C(unittest.TestCase):
            def test_the_tree_has_no_scratch(self):
                self.assertFalse(pathlib.Path(".scratch").exists())
        """}


def rows_of(result: dict, role: str | None = None) -> list[tuple[str, dict]]:
    """(mutant, row) for every kill-file run of every mutant; `role` None: the primary runs only."""
    return [(r["mutant"], x) for r in result.get("results", []) for x in r.get("files", []) if x.get("role") == role]


def classes(result: dict) -> list[str]:
    return [r["class"] for r in result["results"]]


@unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
class Env(unittest.TestCase):
    """FS-1, FS-3, FS-4, ORD-5, PL-8: every kill-file run starts in a clean tree, HOME, XDG and TMPDIR."""

    def setUp(self) -> None:
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = pathlib.Path(d.name)

    def test_a_mutant_that_writes_the_tree_cannot_decide_a_later_file_or_mutant(self):
        root = toy(self.dir, TIDY, TIDY_FILES)
        for order in (["tests/v2/test_s.py", "tests/v2/test_c.py"], ["tests/v2/test_c.py", "tests/v2/test_s.py"]):
            with self.subTest(order=order):
                r = m.run_target(root, "aisef2/toy.py::tidy", order)
                self.assertEqual(killed(r), [False] * 8, r)          # the designed truth: no kill file tests tidy()
                left = [(d, x["file"], x["residue"]) for d, x in rows_of(r) if x.get("residue")]
                self.assertEqual(left, [(d, "tests/v2/test_s.py", {"added": [".scratch"]})
                                        for d in ("L5 condition negated", "L4 True->False")])   # on the run that left it
        # the old failure (ORD-5 case S), with the restore switched off: the residue decides every later run of test_c
        # (the old runner counted each as a kill: 8/8; here the bracket's control fails on the dirty tree too)
        with mock.patch.object(m, "_residue", lambda tg: {}):
            r = m.run_target(root, "aisef2/toy.py::tidy", ["tests/v2/test_s.py", "tests/v2/test_c.py"])
        self.assertEqual([x["outcome"] for _, x in rows_of(r) if x["file"] == "tests/v2/test_c.py"], ["INFRA"] * 8)
        self.assertEqual(classes(r), ["INFRA"] * 8)

    def test_home_xdg_tmpdir_are_fresh_and_removed_per_run(self):
        mark = f"aisef-leak-{os.getpid()}-{time.monotonic_ns()}"
        files = {
            "test_k.py": f"""
                import os, pathlib, tempfile, unittest
                class K(unittest.TestCase):
                    def test_leaves_state_in_its_home_xdg_and_tmpdir(self):
                        pathlib.Path(os.environ["HOME"], ".k").write_text("x")
                        pathlib.Path(os.environ["XDG_CONFIG_HOME"], "k").write_text("x")
                        tempfile.mkdtemp(prefix={mark!r})
                        self.assertTrue(os.environ["{m.TOKEN}"])
                """,
            "test_h.py": """
                import os, pathlib, tempfile, unittest
                class H(unittest.TestCase):
                    def test_sees_none_of_it(self):
                        self.assertFalse(pathlib.Path(os.environ["HOME"], ".k").exists())
                        self.assertFalse(pathlib.Path(os.environ["XDG_CONFIG_HOME"], "k").exists())
                        self.assertNotIn("PYTHONDONTWRITEBYTECODE", os.environ)
                """}
        root = toy(self.dir, TIDY, files)
        kill = ["tests/v2/test_k.py", "tests/v2/test_h.py"]
        with mock.patch.dict(os.environ, {"PYTHONDONTWRITEBYTECODE": "1"}):   # an operator shell's: never passed on
            r = m.run_target(root, "aisef2/toy.py::tidy", kill)
        self.assertNotIn("error", r)
        self.assertEqual(killed(r), [False] * 8)
        self.assertEqual([p for p in os.listdir(tempfile.gettempdir()) if p.startswith(mark)], [])   # FS-3
        # the old failure (ORD-5 H, PL-8): one HOME for every run, and test_h fails on the unmutated tree
        shared = self.dir / "shared"
        real = m._env

        def one_home(run, token):
            env = real(run, token)
            for k in ("HOME", "XDG_CONFIG_HOME"):
                pathlib.Path(shared, k).mkdir(parents=True, exist_ok=True)
                env[k] = str(shared / k)
            return env
        with mock.patch.object(m, "_env", one_home):
            r = m.run_target(root, "aisef2/toy.py::tidy", kill)
        self.assertIn("kill tests fail on the unmutated tree", r["error"])

    def test_the_live_record_never_enters_a_tree(self):
        rec = "closure-evidence/v2/toy/MUTATION.json"
        files = {"test_r.py": f"""
            import pathlib, unittest
            from aisef2.toy import tidy
            class R(unittest.TestCase):
                def test_no_mutation_record_in_this_tree(self):
                    tidy()
                    self.assertFalse((pathlib.Path(__file__).resolve().parents[2] / {rec!r}).exists())
            """}
        root = toy(self.dir, TIDY + "\n\ndef other(flag=True):\n    return 'o' if flag else 'p'\n", files)
        (root / rec).parent.mkdir(parents=True)
        (root / rec).write_text('{"targets": []}\n', encoding="utf-8")   # a record an earlier run wrote
        targets = {"aisef2/toy.py::tidy": ["tests/v2/test_r.py"], "aisef2/toy.py::other": ["tests/v2/test_r.py"]}
        for order in (list(targets), list(reversed(targets))):
            with self.subTest(order=order), mock.patch.object(m, "ROOT", root), \
                    mock.patch.object(m, "RECORDS", {"TOY": rec}), mock.patch.object(m, "PHASE_TARGETS", {"TOY": targets}), \
                    mock.patch.object(m, "TARGETS", targets), mock.patch("builtins.print"):
                m.main(["run", *order])
                got = {t["target"]: t for t in json.loads((root / rec).read_text(encoding="utf-8"))["targets"]}
                self.assertEqual(sorted(got), sorted(targets))
                self.assertEqual([t.get("error") for t in got.values()], [None, None])
                self.assertEqual(len({t["tree_sha256"] for t in got.values()}), 1)
        # the old failure (FS-4): a copy that takes the live record along fails the kill file on the unmutated tree
        with mock.patch.object(m, "RECORDS", {}):
            self.assertIn("kill tests fail on the unmutated tree",
                          m.run_target(root, "aisef2/toy.py::tidy", ["tests/v2/test_r.py"])["error"])


#: a detached helper that names no tree: it writes its pid, then lives until its sentinel exists (at most 120 s) — it
#: ends itself; nothing here ever signals it (INV-MUTATION-AUTHORITY)
HELPER = ("import os, sys, time\nopen(sys.argv[2], 'w').write(str(os.getpid()))\nend = time.time() + 120\n"
          "while not os.path.exists(sys.argv[1]) and time.time() < end:\n    time.sleep(0.1)\n")
POSITIVE = "def positive(x):\n    return x > 0\n"   # mutants: L2 returns None, L2 Gt->LtE


def leaky(sentinel: pathlib.Path, pidfile: pathlib.Path, when: str = "positive(5) is None") -> dict[str, str]:
    return {"test_l.py": f"""
        import subprocess, sys, unittest
        from aisef2.toy import positive
        class L(unittest.TestCase):
            def test_leaves_a_detached_helper(self):
                if {when}:
                    subprocess.Popen([sys.executable, "-c", {HELPER!r}, {str(sentinel)!r}, {str(pidfile)!r}],
                                     start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        """}


def alive(pid: int) -> bool:
    return pid in m.ca.host_table()   # the authority's own reading: a question, no signal


def wait_gone(pid: int, s: float = 20.0) -> bool:
    end = time.monotonic() + s
    while alive(pid) and time.monotonic() < end:
        time.sleep(0.1)
    return not alive(pid)


@unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
class Proc(unittest.TestCase):
    """PL-1, PL-3, PL-4, PL-6: leftovers are found by token or by naming the scratch, signalled only with proof, and an
    unprovable one stops the target and the worker — never signalled, never run beside."""

    def setUp(self) -> None:
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = pathlib.Path(d.name)
        self.sentinel, self.pidfile = self.dir / "stop", self.dir / "helper.pid"
        self.addCleanup(self.sentinel.touch)   # whatever happens, the helper ends itself
        settle = mock.patch.object(m, "SETTLE_S", 1.0)
        settle.start()
        self.addCleanup(settle.stop)

    def helper_pid(self, pidfile: pathlib.Path | None = None) -> int:
        pidfile = pidfile or self.pidfile
        end = time.monotonic() + 10
        while not pidfile.exists() and time.monotonic() < end:
            time.sleep(0.05)
        return int(pidfile.read_text())

    def end_helper(self, pid: int, sentinel: pathlib.Path | None = None) -> None:
        (sentinel or self.sentinel).touch()
        self.assertTrue(wait_gone(pid), f"the helper {pid} did not end itself")

    def test_a_detached_helper_that_names_no_tree_is_found_by_its_token(self):
        root = toy(self.dir, POSITIVE, leaky(self.sentinel, self.pidfile))
        r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_l.py"])
        pid = self.helper_pid()
        self.assertIn(m.ca.RESIDUAL_OWNERSHIP_UNKNOWN, r["error"])
        self.assertIn("at mutant 'L2 returns None' (tests/v2/test_l.py)", r["error"])
        self.assertTrue(r["stopped"])
        self.assertEqual(classes(r), ["INFRA", "NOT_RUN"])   # the leaking mutant has no verdict; nothing ran after it
        self.assertFalse(r.get("cleanup"))                # nothing was signalled
        self.assertEqual([(x["pid"], x["proved"]) for x in r["leaked"]], [(pid, False)])
        self.assertTrue(alive(pid), "an unproven helper is never signalled")
        self.end_helper(pid)
        # the old failure (PL-1): without the token scan the helper is invisible, and the target "completes" beside it
        sentinel, pidfile = self.dir / "stop-2", self.dir / "helper-2.pid"
        self.addCleanup(sentinel.touch)
        root = toy(self.dir / "2", POSITIVE, leaky(sentinel, pidfile))
        with mock.patch.object(m.ca, "carriers", lambda prefix, table=None: []):
            r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_l.py"])
        pid = self.helper_pid(pidfile)
        self.assertNotIn("error", r)
        self.assertTrue(alive(pid))
        self.end_helper(pid, sentinel)

    def test_a_baseline_stray_is_blamed_on_the_baseline(self):
        root = toy(self.dir, POSITIVE, leaky(self.sentinel, self.pidfile, when="True"))
        r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_l.py"])
        pid = self.helper_pid()
        self.assertRegex(r["error"], rf"^{m.ca.RESIDUAL_OWNERSHIP_UNKNOWN} before mutant 1 \(T0 tests/v2/test_l.py\)")
        self.assertEqual(classes(r), ["NOT_RUN", "NOT_RUN"])
        self.assertNotIn("L2", r["error"])
        self.assertTrue(alive(pid))
        self.end_helper(pid)

    def test_an_outside_process_naming_the_tree_is_never_signalled(self):
        """An operator's `tail -f <tree>/...` stands in: a process that names the target's scratch directory, born
        before the runner's boundary. It is never signalled, and the target stops instead of running beside it."""
        root = toy(self.dir, POSITIVE, {"test_p.py": """
            import unittest
            from aisef2.toy import positive
            class P(unittest.TestCase):
                def test_positive(self):
                    self.assertTrue(positive(5))
            """})
        outside = []
        real = m.ca.establish

        def establish(scratch):
            p = subprocess.Popen([sys.executable, "-c", HELPER, str(self.sentinel), str(self.pidfile), str(scratch)],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.addCleanup(p.wait, 30)
            outside.append(p)
            self.helper_pid()
            time.sleep(1.1)   # births are whole seconds: strictly older than the boundary
            return real(scratch)
        with mock.patch.object(m.ca, "establish", establish):
            r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_p.py"])
        self.assertIn(m.ca.RESIDUAL_OWNERSHIP_UNKNOWN, r["error"])
        self.assertEqual([x["pid"] for x in r["leaked"]], [outside[0].pid])
        self.assertIsNone(outside[0].poll(), "a process the runner cannot prove is never signalled")
        self.sentinel.touch()
        self.assertEqual(outside[0].wait(30), 0)

    def test_a_restarted_worker_never_runs_beside_what_an_earlier_run_left(self):
        """PL-3 verifier (e): the token names the worker, not the invocation, so a restart finds the earlier leftover."""
        root = toy(self.dir, POSITIVE, leaky(self.sentinel, self.pidfile))
        targets = {"aisef2/toy.py::positive": ["tests/v2/test_l.py"]}
        env = {k: v for k, v in os.environ.items()} | {m.TOKEN: f"{m._worker(root)}:7"}
        p = subprocess.Popen([sys.executable, "-c", HELPER, str(self.sentinel), str(self.pidfile)], env=env,
                             start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        self.addCleanup(p.wait, 30)
        self.helper_pid()
        with mock.patch.object(m, "ROOT", root), mock.patch.object(m, "PHASE_TARGETS", {"TOY": targets}), \
                mock.patch.object(m, "RECORDS", {"TOY": "closure-evidence/v2/toy/MUTATION.json"}), \
                mock.patch.object(m, "TARGETS", targets), mock.patch("builtins.print") as out:
            self.assertEqual(m.main(["run", *targets]), 3)
        self.assertIn("STOPPED before the first target", out.call_args_list[0].args[0])
        self.assertFalse((root / "closure-evidence/v2/toy/MUTATION.json").exists())
        self.assertIsNone(p.poll())
        self.sentinel.touch()
        self.assertEqual(p.wait(30), 0)

    def test_an_ownership_failure_mid_target_keeps_what_was_measured(self):
        """VS-4, PL-6: a process that is not the runner's (reparented, born after the boundary, not a descendant)
        names the scratch after mutant 1; the target stops at mutant 2 — mutant 1 kept as measured, nothing signalled."""
        root = toy(self.dir, POSITIVE, {"test_p.py": """
            import unittest
            from aisef2.toy import positive
            class P(unittest.TestCase):
                def test_positive(self):
                    positive(5)
            """})
        seen = []
        real = m.ca.establish

        def establish(scratch):
            seen.append(scratch)
            return real(scratch)

        def after(entry):   # detached by a double fork: reparented, so not the runner's descendant — unprovable
            if entry["mutant"] == "L2 returns None":
                subprocess.run([sys.executable, "-c", "import subprocess, sys\nsubprocess.Popen(sys.argv[1:], "
                                "start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                                "stderr=subprocess.DEVNULL)", sys.executable, "-c", HELPER, str(self.sentinel),
                                str(self.pidfile), str(seen[0])], check=True)
                self.helper_pid()
        with mock.patch.object(m.ca, "establish", establish):
            r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_p.py"], on_mutant=after)
        pid = self.helper_pid()
        self.assertEqual(classes(r), ["SURVIVED", "INFRA"])
        self.assertIn("at mutant 'L2 Gt->LtE' (tests/v2/test_p.py)", r["error"])
        self.assertTrue(r["stopped"])
        self.assertEqual([x["pid"] for x in r["leaked"]], [pid])
        self.assertFalse([s for res in r["results"] for s in res.get("cleanup", [])])
        self.assertTrue(alive(pid), "a process the runner cannot prove is never signalled")
        self.end_helper(pid)

    def test_a_short_lived_escapee_settles_instead_of_aborting(self):
        """PL-7: a timed-out test's watchdog leaves the range and exits within a poll of its parent's death. Whether
        release() still saw it alive is scheduling; the class is TIMEOUT every time, never a target error."""
        root = toy(self.dir, POSITIVE, {"test_h.py": """
            import os, subprocess, sys, unittest
            from aisef2.toy import positive
            DOG = "import os, sys, time\\nwhile os.getppid() == int(sys.argv[1]):\\n    time.sleep(0.25)\\n"
            class H(unittest.TestCase):
                def test_hangs_with_a_watchdog_beside_it(self):
                    if positive(5) is None:
                        subprocess.Popen([sys.executable, "-c", DOG, str(os.getpid())], start_new_session=True)
                        while True:
                            pass
            """})
        with mock.patch.object(m, "TIMEOUT", 2):
            for i in range(3):
                with self.subTest(i=i):
                    r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_h.py"])
                    self.assertEqual(classes(r), ["TIMEOUT", "SURVIVED"], r.get("error"))
                    self.assertNotIn("stopped", r)
                    self.assertTrue(r["results"][0]["timed_out"])


#: kill files whose fault the test switches on after T0 (a flag file outside the tree names the fault)
FAULTS = {
    "sigkill": "os.kill(os.getpid(), signal.SIGKILL)",
    "sigterm": "os.kill(os.getpid(), signal.SIGTERM)",
    "exit5": "os._exit(5)",
    "importerror": "import validation.qualification  # noqa",
    "emfile": "raise OSError(24, 'Too many open files')",
    "helper": "self.assertEqual(subprocess.run([sys.executable, '-c', 'raise SystemExit(1)']).returncode, 0)",
}


def faulty(flag: pathlib.Path) -> dict[str, str]:
    """test_weak passes for every mutant of POSITIVE; test_fault performs the fault the flag names, once it exists."""
    branches = "\n".join(f"                    if fault == {k!r}:\n                        {v}" for k, v in FAULTS.items())
    return {
        "test_weak.py": """
            import unittest
            from aisef2.toy import positive
            class W(unittest.TestCase):
                def test_runs(self):
                    positive(5)
            """,
        "test_fault.py": f"""
            import os, pathlib, signal, subprocess, sys, unittest
            FLAG = pathlib.Path({str(flag)!r})
            class F(unittest.TestCase):
                def test_the_host(self):
                    fault = FLAG.read_text().strip() if FLAG.exists() else ""
                    if fault.startswith("once:"):
                        FLAG.write_text("")
                        fault = fault[5:]
{branches}
            """,
        "test_strong.py": """
            import unittest
            from aisef2.toy import positive
            class S(unittest.TestCase):
                def test_positive(self):
                    self.assertIs(positive(5), True)
                    self.assertIs(positive(-1), False)
            """}


def after_t0(flag: pathlib.Path, fault: str):
    """`_baseline` wrapped: the fault is switched on once T0 has passed — an infrastructure event after the baseline."""
    real = m._baseline

    def baseline(tg, rows):
        refused = real(tg, rows)
        flag.write_text(fault)
        return refused
    return mock.patch.object(m, "_baseline", baseline)


SUMMARIES = {
    "ok": ("test_a (v2.t.A.test_a) ... ok\n\n" + "-" * 70 + "\nRan 1 test in 0.001s\n\nOK\n",
           {"ran": 1, "status": "OK", "first": None, "skipped_tests": [], "first_test": "v2.t.A.test_a"}),
    "skips": ("test_a (v2.t.A.test_a)\nIts docstring. ... skipped 'no'\ntest_b (v2.t.A.test_b) ... expected failure\n"
              "test_c (v2.t.A.test_c) ... \n  test_c (v2.t.A.test_c) [s] ... skipped 'sub'\n\n" + "-" * 70 +
              "\nRan 3 tests in 0.001s\n\nOK (skipped=2, expected failures=1)\n",
              {"ran": 3, "status": "OK", "skipped": 2, "expected_failures": 1, "first": None,
               "skipped_tests": ["test_a (v2.t.A.test_a)", "test_c (v2.t.A.test_c) [s]"], "first_test": "v2.t.A.test_a"}),
    "subtest": ("test_b (v2.t.A.test_b) ... \n  test_b (v2.t.A.test_b) [q] ... FAIL\n\n" + "=" * 70 +
                "\nFAIL: test_b (v2.t.A.test_b) [q]\n" + "-" * 70 + "\nTraceback (most recent call last):\n"
                "  File \"t.py\", line 3, in test_b\n    self.assertEqual(x, 'p')\nAssertionError: 'q' != 'p'\n- q\n+ p\n\n\n"
                + "-" * 70 + "\nRan 1 test in 0.001s\n\nFAILED (failures=1)\n",
                {"ran": 1, "status": "FAILED", "failures": 1, "first": "FAIL: test_b (v2.t.A.test_b) [q] | AssertionError",
                 "skipped_tests": [], "first_test": "v2.t.A.test_b"}),
    "import": ("v2.t (unittest.loader._FailedTest.v2.t) ... ERROR\n\n" + "=" * 70 +
               "\nERROR: v2.t (unittest.loader._FailedTest.v2.t)\n" + "-" * 70 +
               "\nImportError: Failed to import test module: v2.t\nTraceback (most recent call last):\n  File \"x\", line 1\n"
               "ModuleNotFoundError: No module named 'validation'\n\n\n" + "-" * 70 + "\nRan 1 test in 0.000s\n\nFAILED (errors=1)\n",
               {"ran": 1, "status": "FAILED", "errors": 1, "skipped_tests": [], "first_test": None,
                "first": "ERROR: v2.t (unittest.loader._FailedTest.v2.t) | ModuleNotFoundError"}),
    "forged": ("test_a (v2.t.A.test_a) ... Ran 9 tests in 0.1s\n\nOK\nFAIL\n\n" + "=" * 70 + "\nFAIL: test_a (v2.t.A.test_a)\n"
               + "-" * 70 + "\nTraceback (most recent call last):\n  File \"t\", line 1\nAssertionError: no\n\n" + "-" * 70
               + "\nRan 1 test in 0.002s\n\nFAILED (failures=1)\n",
               {"ran": 1, "status": "FAILED", "failures": 1, "first": "FAIL: test_a (v2.t.A.test_a) | AssertionError",
                "skipped_tests": [], "first_test": "v2.t.A.test_a"}),
    "no tests": ("\n" + "-" * 70 + "\nRan 0 tests in 0.000s\n\nNO TESTS RAN\n", None),
    "crash": ("Traceback (most recent call last):\nImportError: Start directory is not importable\n", None),
}


class Outcome(unittest.TestCase):
    """VS-1, VS-3, VS-5, VS-6, ORD-6: each run is PASS, FAIL, TIMEOUT or INFRA, judged from unittest's own summary,
    the exit status and the clock; only a FAIL the bracket confirms is a kill."""

    def test_the_summary_is_unittests_own_after_the_last_ran_line(self):
        for name, (text, want) in SUMMARIES.items():
            with self.subTest(name):
                self.assertEqual(m._summary(text), want)

    def test_each_outcome_from_the_exit_the_clock_and_the_summary(self):
        ok, fail = m._summary(SUMMARIES["ok"][0]), m._summary(SUMMARIES["subtest"][0])
        skipped = m._summary(SUMMARIES["skips"][0].replace("OK (skipped=2, expected failures=1)", "OK (skipped=3)")
                             .replace("Ran 3", "Ran 3"))
        nameless = dict(fail, first=None)
        ref = [m._counts(ok), []]
        cases = [((None, m.TIMEOUT + 0.01, None, None), ("TIMEOUT", None)),
                 ((None, 0.04, None, None), ("INFRA", "report channel lost after 0.04s")),
                 ((-9, 1.0, None, None), ("INFRA", "exit -9, no unittest summary")),
                 ((5, 1.0, None, None), ("INFRA", "exit 5, no unittest summary")),
                 ((0, 1.0, None, None), ("INFRA", "exit 0, no unittest summary")),          # os._exit(0)
                 ((0, 1.0, ok, None), ("PASS", None)),
                 ((0, 1.0, ok, ref), ("PASS", None)),
                 ((0, 1.0, ok, [[1, 1, 0, 0], []]), ("INFRA", "counts [1, 0, 0, 0] or skipped tests differ from T0's [1, 1, 0, 0]")),
                 ((0, 1.0, skipped, None), ("INFRA", "every test skipped")),
                 ((1, 1.0, fail, ref), ("FAIL", None)),
                 ((1, 1.0, nameless, ref), ("INFRA", "no failing test named")),
                 ((2, 1.0, fail, ref), ("INFRA", "exit 2 with FAILED [1, 0, 0, 0]")),
                 ((0, 1.0, fail, ref), ("INFRA", "exit 0 with FAILED [1, 0, 0, 0]"))]
        for args, want in cases:
            with self.subTest(args=args[:2]):
                self.assertEqual(m._outcome(*args), want)

    def test_the_bracket_runs_only_what_failed(self):
        self.assertEqual(m._select("FAIL: test_b (v2.t.A.test_b) [q] | AssertionError", "v2.t.A.test_a"), "*v2.t.A.test_b")
        self.assertEqual(m._select("FAIL: test_c (v2.t.A.test_c) (i=2) | AssertionError", None), "*v2.t.A.test_c")
        self.assertEqual(m._select("ERROR: setUpClass (v2.t.C) | RuntimeError", "v2.t.A.test_a"), "*v2.t.C.*")
        self.assertEqual(m._select("ERROR: setUpModule (v2.t) | RuntimeError", "v2.t.A.test_a"), "*v2.t.A.test_a")
        self.assertEqual(m._select("ERROR: v2.t (unittest.loader._FailedTest.v2.t) | ImportError", "v2.t.A.test_a"),
                         "*v2.t.A.test_a")

    @unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
    def test_an_infrastructure_fault_after_the_baseline_is_never_a_kill(self):
        """VS-1, PL-2: with the fault on after T0, the old runner recorded both true survivors as killed, whatever the
        fault. Now every faulted row is INFRA — a signal, exit 5, an import or EMFILE error, a helper's exit surfacing as
        an assertion — no mutant is KILLED, and the target is refused. Without the fault: 2 SURVIVED."""
        d = self.enterContext(tempfile.TemporaryDirectory())
        flag = pathlib.Path(d) / "fault"
        root = toy(pathlib.Path(d), POSITIVE, faulty(flag))
        kill = ["tests/v2/test_weak.py", "tests/v2/test_fault.py"]
        self.assertEqual(classes(m.run_target(root, "aisef2/toy.py::positive", kill)), ["SURVIVED", "SURVIVED"])
        for fault in FAULTS:
            with self.subTest(fault), after_t0(flag, fault):
                r = m.run_target(root, "aisef2/toy.py::positive", kill)
                self.assertEqual(classes(r), ["INFRA", "INFRA"], r.get("error"))
                self.assertTrue(all(x["outcome"] == "INFRA" for d_, x in rows_of(r) if x["file"] == kill[1]))
                self.assertRegex(r["error"], r"^UNCLASSIFIED: 2 mutant")
                self.assertEqual(len([p for p in m.target_problems(r, root) if " is INFRA (" in p]), 2)
            flag.write_text("")

    @unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
    def test_a_transient_fault_never_decides_a_kill_nor_hides_a_later_one(self):
        """VS-5, PL-2 (transient): the first run after T0 hits an infrastructure ERROR that is gone by the bracket's
        control. It is not confirmed, so that row is INFRA and the chain goes on: test_strong supplies the valid kill,
        in the order that puts the fault first and in the one that does not."""
        d = self.enterContext(tempfile.TemporaryDirectory())
        flag = pathlib.Path(d) / "fault"
        root = toy(pathlib.Path(d), POSITIVE, faulty(flag))
        for kill in (["tests/v2/test_fault.py", "tests/v2/test_strong.py"], ["tests/v2/test_strong.py", "tests/v2/test_fault.py"]):
            with self.subTest(kill=kill), after_t0(flag, "once:emfile"):
                r = m.run_target(root, "aisef2/toy.py::positive", kill)
                self.assertEqual(classes(r), ["KILLED", "KILLED"])
                self.assertEqual([x["killed_by"]["file"] for x in r["results"]], ["tests/v2/test_strong.py"] * 2)
                self.assertEqual(m.target_problems(r, root), [])
                if kill[0].endswith("test_fault.py"):
                    first = r["results"][0]["files"]
                    self.assertEqual([(x["file"][9:], x.get("role"), x["outcome"]) for x in first],
                                     [("test_fault.py", None, "INFRA"), ("test_fault.py", "control", "PASS"),
                                      ("test_fault.py", "rerun", "PASS"), ("test_strong.py", None, "FAIL"),
                                      ("test_strong.py", "control", "PASS"), ("test_strong.py", "rerun", "FAIL")])
                    self.assertIn("kill not confirmed", first[0]["why"])
            flag.write_text("")

    @unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
    def test_a_lost_report_channel_is_not_a_timeout(self):
        """VS-3: the test kills its own range anchor; wait() returns at once. That is INFRA, judged by the clock before
        release(), and no TIMEOUT. A real expiry (TIMEOUT patched to 2 s) is TIMEOUT."""
        d = self.enterContext(tempfile.TemporaryDirectory())
        root = toy(pathlib.Path(d), POSITIVE, {"test_x.py": """
            import os, signal, time, unittest
            from aisef2.toy import positive
            class X(unittest.TestCase):
                def test_x(self):
                    if positive(5) is None:
                        os.kill(os.getppid(), signal.SIGKILL)
                        time.sleep(30)
                    if positive(5) is False:
                        while True:
                            pass
            """})
        with mock.patch.object(m, "TIMEOUT", 2):
            r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_x.py"])
        lost, real = (rows_of(r)[0][1], rows_of(r)[1][1])
        self.assertEqual(classes(r), ["INFRA", "TIMEOUT"])
        self.assertRegex(lost["why"], r"^report channel lost after 0\.\d\ds$")
        self.assertLess(lost["seconds"], 1.5)
        self.assertEqual((real["outcome"], real["exit"]), ("TIMEOUT", None))
        self.assertGreaterEqual(real["seconds"], 2)

    @unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
    def test_a_vacuous_pass_is_never_a_pass(self):
        """VS-6: a file whose every test is skipped is refused at T0; a mutant that skips one more test, or that exits 0
        before unittest's summary (os._exit), is INFRA, not SURVIVED."""
        d = self.enterContext(tempfile.TemporaryDirectory())
        root = toy(pathlib.Path(d), POSITIVE, {
            "test_none.py": """
                import unittest
                @unittest.skip("never runs here")
                class N(unittest.TestCase):
                    def test_n(self):
                        pass
                """,
            "test_v.py": """
                import os, unittest
                from aisef2.toy import positive
                class V(unittest.TestCase):
                    @unittest.skipIf(positive(0) is None, "the mutant skips me")
                    def test_skippable(self):
                        pass
                    def test_exit(self):
                        if positive(5) is False:
                            os._exit(0)
                """})
        r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_none.py"])
        self.assertIn("tests/v2/test_none.py: INFRA every test skipped", r["error"])
        r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_v.py"])
        self.assertEqual(classes(r), ["INFRA", "INFRA"])
        self.assertEqual([x["why"] for _, x in rows_of(r)],
                         ["counts [2, 1, 0, 0] or skipped tests differ from T0's [2, 0, 0, 0]", "exit 0, no unittest summary"])


class Classify(unittest.TestCase):
    """VS-2, VS-4, ORD-2, ORD-6 and the record: the class is a function of the outcomes, a timeout or an
    infrastructure event never stops the chain, and the record says which file killed and why."""

    def test_the_class_is_a_function_of_the_multiset_of_outcomes(self):
        import itertools
        for n in range(1, 5):
            for combo in itertools.combinations_with_replacement(("PASS", "FAIL", "TIMEOUT", "INFRA"), n):
                with self.subTest(combo):
                    self.assertEqual(len({m.mutant_class(list(p)) for p in itertools.permutations(combo)}), 1)
        self.assertEqual([m.mutant_class(x) for x in (["PASS", "FAIL"], ["PASS"], ["TIMEOUT", "PASS"], ["TIMEOUT", "INFRA"])],
                         ["KILLED", "SURVIVED", "TIMEOUT", "INFRA"])

    @unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
    def test_a_timeout_is_never_a_kill_and_never_stops_the_chain(self):
        """VS-2, ORD-2: test_hang hangs on both mutants. Old runner: hang first, both 'killed' with timed_out (a
        clock-only kill that --check passed); hang last, both killed; with a weak file, 2 of 2 'killed'. Now: KILLED in
        both orders, with no timed_out, and TIMEOUT 2 of 2 with the weak file — which ran for every mutant."""
        d = self.enterContext(tempfile.TemporaryDirectory())
        files = faulty(pathlib.Path(d) / "no-fault")
        files["test_hang.py"] = """
            import unittest
            from aisef2.toy import positive
            class H(unittest.TestCase):
                def test_hang(self):
                    while positive(5) is not True:
                        pass
            """
        root = toy(pathlib.Path(d), POSITIVE, files)
        hang, strong, weak = "tests/v2/test_hang.py", "tests/v2/test_strong.py", "tests/v2/test_weak.py"
        with mock.patch.object(m, "TIMEOUT", 2):
            first, last, alone = (m.run_target(root, "aisef2/toy.py::positive", k)
                                  for k in ([hang, strong], [strong, hang], [hang, weak]))
        for r in (first, last):
            self.assertEqual(classes(r), ["KILLED", "KILLED"])
            self.assertFalse([x for x in r["results"] if "timed_out" in x])
            self.assertEqual(m.target_problems(r, root), [])
        self.assertEqual([x["outcome"] for _, x in rows_of(first)][:2], ["TIMEOUT", "FAIL"])
        self.assertEqual(classes(alone), ["TIMEOUT", "TIMEOUT"])
        self.assertEqual([x["timed_out"] for x in alone["results"]], [[hang], [hang]])
        self.assertEqual([x["file"] for _, x in rows_of(alone)], [hang, weak, hang, weak])
        self.assertEqual(alone["killed_by_timeout"], 2)
        problems = m.target_problems(alone, root)
        self.assertEqual(len([p for p in problems if "is TIMEOUT" in p]), 2)
        from validation.qualification import s2_mutation_record as S2
        row = {"worker": "w", "measured_on": "x", "target": alone["target"], "result": alone, "why": [], "current": True,
               "at_final_head": True, "other_code_changed": []}
        audited = frozenset((alone["target"], d_) for d_ in alone["survivors"])   # even audited, it never passes
        self.assertIn(alone["target"], S2.account([row], {alone["target"]: []}, audited)["not_passing"])

    @unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
    def test_a_start_failure_is_one_infra_row_and_the_chain_and_the_worker_go_on(self):
        """VS-4 (b): the third kill-file run of the target cannot start (fork EAGAIN). That row is INFRA, the mutant is
        INFRA, every other mutant is classified, and main() goes on to the next target: the record holds both."""
        from aisef2.runtime import process_range
        d = self.enterContext(tempfile.TemporaryDirectory())
        root = toy(pathlib.Path(d), POSITIVE, faulty(pathlib.Path(d) / "no-fault"))
        real, calls = process_range.ProcessRange.start, []

        def start(self_):
            calls.append(1)
            if len(calls) == 3:
                raise BlockingIOError(35, "Resource temporarily unavailable")
            return real(self_)
        targets = {"aisef2/toy.py::positive": ["tests/v2/test_strong.py", "tests/v2/test_weak.py"],
                   "aisef2/toy.py::other": ["tests/v2/test_weak.py"]}
        (root / "aisef2/toy.py").write_text(POSITIVE + "\n\ndef other(x):\n    return x < 0\n", encoding="utf-8")
        rec = "closure-evidence/v2/toy/MUTATION.json"
        (root / rec).parent.mkdir(parents=True)
        with mock.patch.object(process_range.ProcessRange, "start", start), mock.patch.object(m, "ROOT", root), \
                mock.patch.object(m, "RECORDS", {"TOY": rec}), mock.patch.object(m, "PHASE_TARGETS", {"TOY": targets}), \
                mock.patch.object(m, "TARGETS", targets), mock.patch("builtins.print"):
            self.assertNotEqual(m.main(["run", *targets]), 3)
        got = {t["target"]: t for t in json.loads((root / rec).read_text(encoding="utf-8"))["targets"]}
        self.assertEqual(sorted(got), sorted(targets))
        first = got["aisef2/toy.py::positive"]
        self.assertEqual(classes(first), ["INFRA", "KILLED"])
        self.assertRegex(rows_of(first)[0][1]["why"], r"^start failed: BlockingIOError")
        self.assertNotIn("stopped", first)
        self.assertEqual(classes(got["aisef2/toy.py::other"]), ["SURVIVED", "SURVIVED"])

    @unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
    def test_the_record_says_which_file_killed_and_why(self):
        """ORD-6: an assertion kill, a file that vanishes (exit 5) and an environment ImportError gave byte-identical
        records ({mutant, killed: true}). Now: KILLED with the failing test named, INFRA exit 5, INFRA not confirmed."""
        d = self.enterContext(tempfile.TemporaryDirectory())
        flag = pathlib.Path(d) / "fault"
        root = toy(pathlib.Path(d), POSITIVE, faulty(flag))
        r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_strong.py"])
        self.assertEqual([x["killed_by"] for x in r["results"]],
                         [{"file": "tests/v2/test_strong.py", "first": "FAIL: test_positive (v2.test_strong.S.test_positive) "
                           "| AssertionError", "seconds": x["killed_by"]["seconds"]} for x in r["results"]])
        self.assertEqual([m._confirmed(x) for x in r["results"]], [True, True])
        for fault, why in (("exit5", "exit 5, no unittest summary"), ("importerror", "kill not confirmed: the unmutated module FAIL")):
            with self.subTest(fault), after_t0(flag, fault):
                r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_fault.py"])
                self.assertEqual(classes(r), ["INFRA", "INFRA"])
                self.assertTrue(rows_of(r)[0][1]["why"].startswith(why), rows_of(r)[0][1]["why"])
            flag.write_text("")

    def test_a_hand_edited_record_is_refused(self):
        """§4.3: the record's own consistency — a KILLED with no confirmed bracket, a survivor list that is not the
        unkilled mutants — is refused, and an INFRA mutant is never excused by an audit."""
        src = (ROOT / "aisef2/app/review_verify.py").read_text(encoding="utf-8")
        target = "aisef2/app/review_verify.py::blocks"
        descs = [x for x, _ in m.mutants(src, "blocks", m._enum_members(src, ROOT))]
        ok = {"target": target, "runner": 2, "kill_tests": ["tests/v2/test_x.py"], "source_sha256": m.source_digest(src),
              "mutants": len(descs), "killed": 0, "survivors": [], "t0": [],
              "results": [{"mutant": x, "class": "KILLED", "killed": True} for x in descs]}
        problems = m.target_problems(dict(ok, killed=len(descs)))
        self.assertEqual(len(problems), len(descs))
        self.assertTrue(all("KILLED without a confirmed kill" in p for p in problems))
        forged = dict(ok, results=[dict(ok["results"][0], **{"class": "INFRA", "killed": False}), *ok["results"][1:]],
                      survivors=[], killed=len(descs) - 1)
        with mock.patch.dict(m.AUDITED, {(target, descs[0]): "an audit cannot excuse an INFRA mutant"}):
            problems = m.target_problems(forged)
        self.assertIn(f"{target}: mutant {descs[0]!r} is INFRA (see its rows): neither killed nor survived — re-run it", problems)
        self.assertIn(f"{target}: inconsistent record: survivors are not the mutants that were not killed", problems)

    def test_historical_records_read_as_before(self):
        """§8: every committed record of P1..V2.0-S2 is read by the unchanged legacy branch and checks as it did at
        c9c736f (no problem); V2.1 refuses a result of a runner that does not classify."""
        for phase, rel in m.RECORDS.items():
            if phase != "V2.1" and m.PHASE_TARGETS[phase]:
                with self.subTest(phase):
                    record = json.loads((ROOT / rel).read_text(encoding="utf-8"))
                    self.assertFalse([t for t in record["targets"] if t.get("runner")])
                    self.assertEqual(m.problems_of(record, ROOT, phase), [])
        t = next(iter(m.V21_TARGETS))
        legacy = {"target": t, "kill_tests": m.V21_TARGETS[t], "source_sha256": "0", "mutants": 1, "killed": 1, "survivors": [],
                  "results": [{"mutant": "x", "killed": True}]}
        problems = m.problems_of({"targets": [legacy]}, ROOT, "V2.1")
        self.assertIn(f"{t}: measured by a runner that does not classify — re-measure", problems)


if __name__ == "__main__":
    unittest.main()
