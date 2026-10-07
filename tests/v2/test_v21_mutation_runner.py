"""The mutation runner's own contract (docs/v2.1/MUTATION-RUNNER-V2.md), on toy targets and toy kill files built in a
temporary root and driven through the real `run_target` (and `mutants`, `_run_tests`, `main`), the real ProcessRange
and the real cleanup authority. Each case builds the situation a confirmed finding of the V2.1 runner audit described,
asserts the designed truth per mutant, and — where a protection can be switched off — shows the old failure with it
off, so a toy that no longer exercises the channel fails instead of passing vacuously. Not a kill file."""

from __future__ import annotations

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


def every(result: dict, key: str) -> list:
    """Every entry of `key` the result names, wherever the record keeps it (the target's own or its mutants')."""
    return [x for r in result.get("results", []) for x in r.get(key, [])]


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
                self.assertEqual(sorted({x["file"] for x in every(r, "residue")}), ["tests/v2/test_s.py"])
                self.assertEqual([x for x in every(r, "residue")][0]["added"], [".scratch"])
                self.assertEqual([res["mutant"] for res in r["results"] if res.get("residue")],
                                 ["L5 condition negated", "L4 True->False"])
        # the old failure (ORD-5 case S), with the restore switched off: the residue "kills" every later run of test_c
        with mock.patch.object(m, "_residue", lambda tg: {}):
            r = m.run_target(root, "aisef2/toy.py::tidy", ["tests/v2/test_s.py", "tests/v2/test_c.py"])
        self.assertEqual(killed(r), [True] * 8)

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
                got = {t["target"]: t for t in __import__("json").loads((root / rec).read_text(encoding="utf-8"))["targets"]}
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
        self.assertIn("at mutant 'L2 returns None'", r["error"])
        self.assertTrue(r["stopped"])
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
        self.assertRegex(r["error"], rf"^{m.ca.RESIDUAL_OWNERSHIP_UNKNOWN} before mutant 1 \(baseline\)")
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


if __name__ == "__main__":
    unittest.main()
