"""The mutation runner's own contract (docs/v2.1/MUTATION-RUNNER-V2.md), on toy targets and toy kill files built in a
temporary root and driven through the real `run_target` (and `mutants`, `_run_tests`, `main`), the real ProcessRange
and the real cleanup authority. Each case builds the situation a confirmed finding of the V2.1 runner audit described,
asserts the designed truth per mutant, and — where a protection can be switched off — shows the old failure with it
off, so a toy that no longer exercises the channel fails instead of passing vacuously. Not a kill file."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import pathlib
import re
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
DEFAULT_SETTLE_S = m.SETTLE_S   # before any test patches it


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

    @unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
    def test_a_touched_source_is_residue_so_the_stamp_cannot_be_lost(self):
        """Bytecode lens: a kill file that rewrites the mutated module with its own bytes puts the wall clock back into
        its mtime, and BC-1's same-second collision returns (3 of 5 false SURVIVED in the prover's toy, with no error).
        A source only touched counts as residue, so T0 refuses such a file; one that touches another source too."""
        touch = {"test_t.py": """
            import os, pathlib, unittest
            ROOT = pathlib.Path(__file__).resolve().parents[2]
            class T(unittest.TestCase):
                def test_rewrites_a_source_with_its_own_bytes(self):
                    p = ROOT / os.environ.get("TOY_TOUCH", "aisef2/toy.py")
                    p.write_bytes(p.read_bytes())
            """}
        root = toy(self.dir, BC_MODULE, {**BC_KILL, **touch})
        for rel in ("aisef2/toy.py", "aisef2/__init__.py"):
            with self.subTest(rel), mock.patch.dict(os.environ, {"TOY_TOUCH": rel}), \
                    mock.patch.object(m, "ENV_KEEP", (*m.ENV_KEEP, "TOY_TOUCH")):
                r = m.run_target(root, "aisef2/toy.py::v", ["tests/v2/test_k.py", "tests/v2/test_t.py"])
                self.assertEqual(r["error"], "kill tests fail on the unmutated tree (T0 null mutant): "
                                             "tests/v2/test_t.py: PASS (left residue)")
                self.assertEqual(r["t0"][1]["residue"], {"changed": [rel]})
                self.assertFalse(r["t0"][0].get("residue"))       # a file that only reads the tree is not touched by it
        self.assertEqual(killed(m.run_target(root, "aisef2/toy.py::v", ["tests/v2/test_k.py"])), BC_TRUTH)


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


def no_remeasure(tg, rel, rows, row, src, why):
    """The runner before `_remeasure` (fix 10): an unconfirmed FAIL is INFRA, never measured again — for controls."""
    row.update(outcome="INFRA", why=f"kill not confirmed: {why}")
    return row


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
        # (the old runner counted each as a kill: 8/8; here the bracket's control fails on the dirty tree too, and the
        # fresh re-measure, which would rebuild the tree, is off as well)
        with mock.patch.object(m, "_residue", lambda tg: {}), mock.patch.object(m, "_remeasure", no_remeasure):
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

    def test_what_a_run_leaves_beside_the_tree_is_residue_too(self):
        """Filesystem-state lens: the cwd is the tree, so '../outside.txt' lands in the tree's holder, which the
        manifest did not cover; it masked the kills of `test_a` (it sees the file already there) in both orders, and
        the bracket could not help (its runs started dirty too). Now the holder must hold only the tree: the run that
        left it names it on its row and a new holder is built. Something left in the target's scratch itself
        ('../../x') cannot be removed by the runner, so the target stops."""
        par = ("import pathlib\n\n\ndef mark(flag=False, other=False):\n    if flag:\n"
               "        pathlib.Path('../outside.txt').write_text('x')\n        return 2\n    if other:\n"
               "        pathlib.Path('../outside.txt').write_text('y')\n    return 1\n")
        files = {
            "test_a.py": """
                import pathlib, unittest
                from aisef2.toy import mark
                OUT = pathlib.Path("..").resolve() / "outside.txt"
                class A(unittest.TestCase):
                    def test_mark_leaves_the_directory_beside_the_tree_alone(self):
                        before = OUT.exists()
                        mark()
                        self.assertEqual(OUT.exists(), before)
                """,
            "test_b.py": """
                import unittest
                from aisef2.toy import mark
                class B(unittest.TestCase):
                    def test_mark_returns_one(self):
                        self.assertEqual(mark(), 1)
                """,
            "test_s.py": """
                import pathlib, unittest
                class S(unittest.TestCase):
                    def test_writes_into_the_scratch(self):
                        (pathlib.Path("../..").resolve() / "x").write_text("x")
                """}
        root = toy(self.dir, par, files)
        found = m.mutants(par, "mark", {})   # two of them are both called "L4 False->True": compared by position
        writes = [any(w in s for w in ("def mark(flag=True", "other=True)", "if not flag", "if not other")) for _, s in found]
        truth = ["KILLED" if w or d == "L10 returns None" else "SURVIVED" for w, (d, _) in zip(writes, found, strict=True)]
        self.assertEqual(sum(writes), 4)
        a, b = "tests/v2/test_a.py", "tests/v2/test_b.py"
        for order in ([a, b], [b, a]):
            with self.subTest(order=order):
                r = m.run_target(root, "aisef2/toy.py::mark", order)
                self.assertEqual(classes(r), truth)
                self.assertTrue([x for _, x in rows_of(r) if x.get("residue") == {"beside": ["outside.txt"]}])
        # the old failure, with the holder left unchecked: what the first writing run left decides later runs
        real = m._residue
        with mock.patch.object(m, "_residue", lambda tg: {k: v for k, v in real(tg).items() if k != "beside"}):
            r = m.run_target(root, "aisef2/toy.py::mark", [b, a])
        self.assertNotEqual(classes(r), truth)
        r = m.run_target(root, "aisef2/toy.py::mark", [b, "tests/v2/test_s.py"])
        self.assertTrue(r["stopped"])
        self.assertEqual(r["error"], "RESIDUE_UNREMOVABLE before mutant 1 (T0 tests/v2/test_s.py): ['x'] left in the "
                                     "target's scratch directory")

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
        # the old failure (PL-1): without the token scan (and the cwd scan, which the old runner did not have either)
        # the helper is invisible, and the target "completes" beside it
        sentinel, pidfile = self.dir / "stop-2", self.dir / "helper-2.pid"
        self.addCleanup(sentinel.touch)
        root = toy(self.dir / "2", POSITIVE, leaky(sentinel, pidfile))
        with mock.patch.object(m.ca, "carriers", lambda prefix, table=None: []), \
                mock.patch.object(m.ca, "cwd_under", lambda prefix, table=None, since=None: []):
            r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_l.py"])
        pid = self.helper_pid(pidfile)
        self.assertNotIn("error", r)
        self.assertTrue(alive(pid))
        self.end_helper(pid, sentinel)

    def test_a_helper_with_its_own_environment_is_found_by_its_cwd(self):
        """PL-1 (3), process-env prover: a helper spawned with `env={'PATH': ...}` carries no token and names no scratch
        path; only its cwd — the tree it inherited — shows it. The old scan missed it, so later runs started beside it
        (order alone flipped 5 of 8 mutants in the prover's toy, with a clean record). Now the cwd scan finds it: it is
        unprovable (re-parented), never signalled, and the target stops at the mutant that left it."""
        files = leaky(self.sentinel, self.pidfile)
        files["test_l.py"] = files["test_l.py"].replace("start_new_session=True,",
                                                        "start_new_session=True, env={'PATH': os.environ['PATH']},")
        files["test_l.py"] = files["test_l.py"].replace("import subprocess, sys", "import os, subprocess, sys")
        root = toy(self.dir, POSITIVE, files)
        r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_l.py"])
        pid = self.helper_pid()
        self.assertIn(f"{m.ca.RESIDUAL_OWNERSHIP_UNKNOWN} at mutant 'L2 returns None' (tests/v2/test_l.py)", r["error"])
        self.assertEqual(classes(r), ["INFRA", "NOT_RUN"])
        self.assertEqual([(x["pid"], x["proved"]) for x in r["leaked"]], [(pid, False)])
        self.assertTrue(alive(pid), "an unproven helper is never signalled")
        self.end_helper(pid)
        # the old failure: without the cwd scan the helper is invisible, and the target "completes" beside it
        sentinel, pidfile = self.dir / "stop-2", self.dir / "helper-2.pid"
        self.addCleanup(sentinel.touch)
        files = {k: v.replace(str(self.sentinel), str(sentinel)).replace(str(self.pidfile), str(pidfile))
                 for k, v in files.items()}
        root = toy(self.dir / "2", POSITIVE, files)
        with mock.patch.object(m.ca, "cwd_under", lambda prefix, table=None, since=None: []):
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

    def test_a_host_table_that_cannot_be_read_stops_instead_of_reading_as_empty(self):
        """Process-env lens: one `ps` read that exits non-zero with no output made `_settle` report nothing and `_watch`
        report every pid gone while a token-carrying helper was alive — fail-open. Now the authority's readers raise
        when `ps` fails or does not list itself, and the runner stops (HOST_TABLE_UNREADABLE); nothing is signalled."""
        root = toy(self.dir, POSITIVE, leaky(self.sentinel, self.pidfile, when="True"))
        real = subprocess.Popen
        fakes = {"exit 1, no output": "raise SystemExit(1)",
                 "exit 0, without itself": "print('    1     0     1 Mon Jan  1 00:00:00 2024 /sbin/launchd')"}
        for name, script in fakes.items():
            def popen(argv, *a, script=script, **kw):
                return real([sys.executable, "-c", script], *a, **kw) if argv[0] == "ps" else real(argv, *a, **kw)
            with self.subTest(name), mock.patch.object(m.ca.subprocess, "Popen", popen):
                self.assertRaises(OSError, m.ca.host_table)
                if sys.platform == "darwin":   # Linux reads /proc for environments, not ps
                    self.assertRaises(OSError, m.ca.carriers, "X=", {})
        tg = m._Target("aisef2/toy.py", self.dir, m.ca.establish(self.dir), m._worker(root))
        # detached by a double fork, so not the runner's descendant: unprovable, never signalled; it carries the token
        subprocess.run([sys.executable, "-c", "import subprocess, sys\nsubprocess.Popen(sys.argv[1:], start_new_session="
                        "True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)",
                        sys.executable, "-c", HELPER, str(self.sentinel), str(self.pidfile)],
                       env={**os.environ, m.TOKEN: f"{tg.worker}:1"}, check=True)
        pid = self.helper_pid()
        with self.assertRaises(m._Stop) as cm:
            m._settle(tg)   # the helper is found, unproven (not a descendant now), and outlives the grace
        self.assertEqual(cm.exception.code, m.ca.RESIDUAL_OWNERSHIP_UNKNOWN)

        def broken(argv, *a, **kw):
            return real([sys.executable, "-c", fakes["exit 1, no output"]], *a, **kw) if argv[0] == "ps" \
                else real(argv, *a, **kw)
        with mock.patch.object(m.ca.subprocess, "Popen", broken):
            with self.assertRaises(m._Stop) as cm:
                m._settle(tg)
            self.assertEqual(cm.exception.code, "HOST_TABLE_UNREADABLE")
            with self.assertRaises(OSError):
                m._watch([pid])
        self.assertTrue(alive(pid))
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

    def test_the_pids_release_names_are_read_from_its_list_not_from_command_text(self):
        """Process-env prover: the pids of a Residual were taken with re.findall(r'\\((\\d+), ') over its message, which
        holds command lines the code under test controls: an escapee whose source says `max(1, 2)` made the runner
        watch launchd and stop ('alive after ...: [1]'). They are now read from the list release() ends its message
        with, after the exact prefix rebuilt from the range's own name and ledger; another shape stops the target."""
        class R:
            name, ledger = "kill tests tests/v2/test_x.py", [{"stage": "cooperative"}, {"stage": "kill"}]
        from aisef2.runtime.process_range import RangeEscaped, RangeNotEmpty
        esc = RangeEscaped(f"{R.name}: processes left the range and are alive: [(4242, 'python -c x = max(1, 2)')]")
        full = RangeNotEmpty(f"{R.name}: not empty after ['cooperative', 'kill']: [(7, 'os.setpgid(0, G)'), (8, 'b')]")
        self.assertEqual(m._named(R, esc, False), [4242])
        self.assertEqual(m._named(R, full, True), [7, 8])
        self.assertEqual(sorted({int(x) for x in re.findall(r"\((\d+), ", str(esc))}), [1, 4242])  # old
        for bad in (RangeEscaped("something else: [(1, 'x')]"), RangeNotEmpty(f"{R.name}: not empty after []: [(1, 'x')]")):
            with self.subTest(bad=str(bad)), self.assertRaises(m._Stop):
                m._named(R, bad, isinstance(bad, RangeNotEmpty))
        # on a real range: an in-group child leaves a 2 s escapee whose source holds '(1, '
        root = toy(self.dir, POSITIVE, {"test_p.py": """
            import subprocess, sys, time, unittest
            from aisef2.toy import positive
            E = "import time; time.sleep(2); x = max(1, 2)"
            B = "import subprocess, sys, time\\nsubprocess.Popen([sys.executable, '-c', sys.argv[1]], start_new_session=True)\\ntime.sleep(30)\\n"
            class P(unittest.TestCase):
                def test_leaves_an_escapee_through_a_member(self):
                    if positive(5) is None:
                        subprocess.Popen([sys.executable, "-c", B, E])
                        time.sleep(0.7)
            """})
        with mock.patch.object(m, "SETTLE_S", 5.0):
            r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_p.py"])
            self.assertEqual(classes(r), ["SURVIVED", "SURVIVED"], r.get("error"))
            self.assertTrue(rows_of(r)[0][1]["residual"].startswith("RangeEscaped"), rows_of(r)[0][1])
            self.assertNotIn(1, [x["pid"] for x in rows_of(r)[0][1]["leaked"]])
            # the old failure, with the substring regex: pid 1 is watched, and the target stops
            with mock.patch.object(m, "_named", lambda r_, e, ne: [int(x) for x in re.findall(r"\((\d+), ", str(e))]):
                r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_p.py"])
        self.assertTrue(r["stopped"])
        self.assertIn("alive after 5.0s: [1]", r["error"])
        time.sleep(2.5)   # the escapee ends itself

    def test_an_escapee_that_ends_within_the_grace_does_not_make_the_order_decide(self):
        """ORD-7: `test_e` hangs beside a detached helper that lives about 6 s. In [plain, test_e] plain kills both
        mutants first; in [test_e, plain] the helper is reached, and with a grace shorter than its life the target
        stopped at mutant 1 (INFRA, then NOT_RUN): the order decided the target's fate. With a grace longer than the
        helper's life it settles by itself (never signalled), the TIMEOUT row keeps its outcome, and both orders give
        the same classes. The default grace covers the real helpers measured (8 s, and ORD-7's 30 s escapee)."""
        self.assertGreaterEqual(DEFAULT_SETTLE_S, 30)
        root = toy(self.dir, POSITIVE, {
            "test_e.py": """
                import subprocess, sys, unittest
                from aisef2.toy import positive
                class E(unittest.TestCase):
                    def test_hangs_beside_a_short_lived_helper(self):
                        if positive(5) is not True:
                            subprocess.Popen([sys.executable, "-c", "import time; time.sleep(6)"], start_new_session=True,
                                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            while True:
                                pass
                """,
            "test_plain.py": """
                import unittest
                from aisef2.toy import positive
                class P(unittest.TestCase):
                    def test_positive(self):
                        self.assertIs(positive(5), True)
                        self.assertIs(positive(-1), False)
                """})
        e, plain = "tests/v2/test_e.py", "tests/v2/test_plain.py"
        with mock.patch.object(m, "TIMEOUT", 2):
            with mock.patch.object(m, "SETTLE_S", 15.0):
                runs = [m.run_target(root, "aisef2/toy.py::positive", k) for k in ([plain, e], [e, plain])]
            self.assertEqual([classes(r) for r in runs], [["KILLED", "KILLED"]] * 2)
            self.assertFalse([r for r in runs if r.get("stopped")])
            self.assertEqual([x["outcome"] for _, x in rows_of(runs[1]) if x["file"] == e], ["TIMEOUT", "TIMEOUT"])
            self.assertFalse([s for r in runs for x in r["results"] for s in x.get("cleanup", [])])   # nothing signalled
            # the old failure: a grace shorter than the helper's life, and the order decides
            r = m.run_target(root, "aisef2/toy.py::positive", [e, plain])   # setUp's 1 s grace
        self.assertTrue(r["stopped"])
        self.assertEqual(classes(r), ["INFRA", "NOT_RUN"])
        time.sleep(7)   # the helper ends itself

    @unittest.skipUnless(sys.platform == "darwin", "the repopulating group was measured on macOS (process-env prover)")
    def test_one_release_budget_per_run(self):
        """Process-env prover (pl5r150): after a RangeNotEmpty the runner signals the group and calls release() again,
        which ran the whole ladder with a fresh RELEASE_WAIT_S, so one run held its worker about twice the stated bound
        (129 s at the default). P, in its own group inside the anchor's session (never reached by the group signals),
        keeps the range's group repopulated; the target stops (the range would not empty), and the run's release takes
        one budget plus both ladders' graces, not two budgets. P ends on its sentinel; nothing signals it."""
        root = toy(self.dir, POSITIVE, {"test_r.py": f"""
            import os, subprocess, sys, time, unittest
            P = '''
            import os, sys, time
            G, end, stop = int(sys.argv[1]), time.time() + 60, sys.argv[2]
            open(sys.argv[3], "w").write(str(os.getpid()))
            def waiter():
                r, w = os.pipe()
                pid = os.fork()
                if pid == 0:
                    os.close(w)
                    os.read(r, 1)
                    try:
                        os.setpgid(0, G)
                    except OSError:
                        os._exit(3)
                    time.sleep(3)
                    os._exit(0)
                os.close(r)
                return pid, w
            spare = [waiter() for _ in range(4)]
            def activate():
                pid, w = spare.pop(0)
                os.write(w, b"g")
                os.close(w)
                spare.append(waiter())
                return pid
            active = {{activate(), activate()}}
            while time.time() < end and not os.path.exists(stop):
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    time.sleep(0.001)
                elif pid in active:
                    active.discard(pid)
                    active.add(activate())
            '''
            class R(unittest.TestCase):
                def test_leaves_the_group_repopulated(self):
                    import textwrap
                    subprocess.Popen([sys.executable, "-c", textwrap.dedent(P), str(os.getpgrp()), {str(self.sentinel)!r},
                                      {str(self.pidfile)!r}], process_group=0, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(0.5)
            """})
        wait = 8.0
        with mock.patch.object(m, "RELEASE_WAIT_S", wait):
            r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_r.py"])
        pid = self.helper_pid()
        row = r["t0"][0]
        self.assertTrue(r["stopped"])
        self.assertIn("the range would not empty", r["error"])
        self.assertIn("not empty after ['cooperative', 'terminate', 'kill', 'cooperative', 'terminate', 'kill']", r["error"])
        from aisef2.runtime.process_range import GRACE_S
        grace = sum(GRACE_S)
        self.assertLess(row["overhead_s"], wait + 2 * grace + 3, row)   # two budgets took 2 x (wait + grace)
        self.assertGreater(row["overhead_s"], wait + grace)
        self.end_helper(pid)

    @unittest.skipUnless(sys.platform == "darwin", "the group-rejoin mechanism was measured on macOS (VS-7 verifier)")
    def test_a_range_that_never_empties_is_bounded_and_never_a_kill(self):
        """VS-7/PL-5: the test ignores SIGINT and SIGTERM, so the ladder reaches SIGKILL; its child leaves the group
        first and rejoins it once the group SIGKILL has killed its parent (the unreaped anchor keeps the group alive).
        The old runner waited without limit (wait_s None). Now release() gives up after RELEASE_WAIT_S, the row is
        INFRA (`residual: RangeNotEmpty`), the group is signalled by the authority with its proof (the anchor is the
        runner's own, unreaped child), and nothing is left running."""
        root = toy(self.dir, POSITIVE, {"test_g.py": f"""
            import os, signal, sys, time, unittest
            from aisef2.toy import positive
            class G(unittest.TestCase):
                def test_hangs_and_leaves_a_rejoining_child(self):
                    if positive(5) is not None:
                        return
                    group, parent = os.getpgrp(), os.getpid()
                    for s in (signal.SIGINT, signal.SIGTERM):
                        signal.signal(s, signal.SIG_IGN)
                    if os.fork() == 0:
                        try:
                            os.setpgid(0, 0)
                            while os.getppid() == parent:
                                time.sleep(0.002)
                            os.setpgid(0, group)
                            end = time.time() + 60
                            while time.time() < end and not os.path.exists({str(self.sentinel)!r}):
                                time.sleep(0.05)
                        finally:
                            os._exit(0)
                    time.sleep(1000)
            """})
        begun = time.monotonic()
        with mock.patch.object(m, "TIMEOUT", 2), mock.patch.object(m, "RELEASE_WAIT_S", 3):
            r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_g.py"])
        self.assertLess(time.monotonic() - begun, 60)
        self.assertEqual(classes(r), ["INFRA", "SURVIVED"])
        row = rows_of(r)[0][1]
        self.assertTrue(row["residual"].startswith("RangeNotEmpty"), row)
        self.assertEqual((row["outcome"], row["judged_before_release"]), ("INFRA", "TIMEOUT"))
        self.assertEqual([s["kind"] for s in row["cleanup"]], ["group"])   # the authority's proof, the group it created
        self.assertEqual(row["cleanup"][0]["proof"]["runner"], os.getpid())
        self.assertNotIn("stopped", r)


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


def anchor_guard() -> str:
    """Source of `our_anchor()` for a toy kill test that signals its parent (INV-MUTATION-AUTHORITY): the parent's pid
    when it is the range anchor this test process's run started — a child of this process running range_anchor.py,
    leader of the toy's own group and session — else 0, and nothing is signalled. That pid stays the anchor, or its
    zombie, until this process reaps it after wait() returns, so a signal to it cannot reach another process."""
    from aisef2.runtime.process_range import ANCHOR
    return textwrap.dedent(f"""
        import os, subprocess

        def our_anchor():
            pp = os.getppid()
            ps = subprocess.run(["ps", "-o", "ppid=,command=", "-p", str(pp)], capture_output=True, text=True)
            ppid, _, command = ps.stdout.strip().partition(" ")
            proven = pp > 1 and os.getpgrp() == os.getsid(0) == pp and ppid == "{os.getpid()}" and \\
                command.endswith(" -P " + {str(ANCHOR)!r})
            return pp if proven else 0
        """)


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
                                     [("test_fault.py", "unconfirmed", "FAIL"), ("test_fault.py", "control", "PASS"),
                                      ("test_fault.py", "control", "PASS"), ("test_fault.py", "rerun", "PASS"),
                                      ("test_fault.py", None, "PASS"),   # re-measured on a fresh tree: the fault is gone
                                      ("test_strong.py", None, "FAIL"), ("test_strong.py", "control", "PASS"),
                                      ("test_strong.py", "control", "PASS"), ("test_strong.py", "rerun", "FAIL")])
                    self.assertTrue(first[4]["fresh"])
                    self.assertIn("kill not confirmed", first[0]["why"])
            flag.write_text("")

    @unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
    def test_an_unconfirmed_fail_is_measured_again_on_a_fresh_tree(self):
        """Fix 10 (`_remeasure`), one toy per open finding; each also with the fresh re-measure off (the old INFRA):
        - VS-5 in a file: a one-shot infrastructure error in test_a stopped the file (-f) before test_b's valid kill;
          the fault was gone by the bracket, so the mutant was INFRA. Now the whole file runs again: KILLED by test_b.
        - VS-6 (b): test_b reads state test_a sets, so `-k test_b` fails on the unmutated module too and the valid kill
          was never confirmed. Bracketed whole: KILLED.
        - VS-6, nondeterminism: a file that fails every other run of itself, whatever the mutant. The second control
          catches it; re-measured, it passes: SURVIVED, the truth (it never reads the mutant's answer).
        - FS-2's mechanism, order-equivalence prover: test_p writes a fixture's __pycache__ (on a wrong answer only),
          which the tree checks do not see; test_q asserts there is none. Both orders: every mutant SURVIVED."""
        d = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))
        flag, count = d / "fault", d / "count"
        files = {
            "test_mix.py": f"""
                import pathlib, unittest
                from aisef2.toy import positive
                FLAG = pathlib.Path({str(flag)!r})
                class T(unittest.TestCase):
                    def test_a_infra(self):
                        if FLAG.exists() and FLAG.read_text() == "once":
                            FLAG.write_text("")
                            raise OSError(28, "No space left on device")
                    def test_b_assert(self):
                        self.assertIs(positive(5), True)
                        self.assertIs(positive(-1), False)
                """,
            "test_ord.py": """
                import unittest
                from aisef2.toy import positive
                STATE = {}
                class T(unittest.TestCase):
                    def test_a_compute(self):
                        STATE["v"] = (positive(5), positive(-1))
                    def test_b_check(self):
                        self.assertEqual(STATE["v"], (True, False))
                """,
            "test_flaky.py": f"""
                import pathlib, unittest
                from aisef2.toy import positive
                C = pathlib.Path({str(count)!r})
                class T(unittest.TestCase):
                    def test_flaky(self):
                        n = int(C.read_text()) if C.exists() else 0
                        C.write_text(str(n + 1))
                        positive(5)
                        self.assertEqual(n % 2, 0, "a flake")
                """,
            "test_p_pyc.py": """
                import pathlib, sys, unittest
                from aisef2.toy import positive
                FX = pathlib.Path(__file__).resolve().parent / "fixtures"
                class P(unittest.TestCase):
                    def test_p(self):
                        if positive(-1) is not False:   # only a wrong answer loads the fixture, whose bytecode lands beside it
                            sys.path.insert(0, str(FX))
                            import fxmod  # noqa: F401
                """,
            "test_q_nopyc.py": """
                import pathlib, unittest
                FX = pathlib.Path(__file__).resolve().parent / "fixtures"
                class Q(unittest.TestCase):
                    def test_the_fixture_holds_no_bytecode(self):
                        self.assertFalse((FX / "__pycache__").exists())
                """,
            "fixtures/fxmod.py": "X = 1\n"}
        root = toy(d, POSITIVE, files)
        cases = {"VS-5": (["tests/v2/test_mix.py"], ["KILLED", "KILLED"], ["INFRA", "KILLED"]),
                 "VS-6 (b)": (["tests/v2/test_ord.py"], ["KILLED", "KILLED"], ["INFRA", "INFRA"]),
                 "parity": (["tests/v2/test_flaky.py"], ["SURVIVED", "SURVIVED"], ["INFRA", "SURVIVED"]),
                 "pycache pq": (["tests/v2/test_p_pyc.py", "tests/v2/test_q_nopyc.py"], ["SURVIVED", "SURVIVED"], None),
                 "pycache qp": (["tests/v2/test_q_nopyc.py", "tests/v2/test_p_pyc.py"], ["SURVIVED", "SURVIVED"], None)}
        for name, (kill, truth, old) in cases.items():
            for remeasure in (True, False):
                if not remeasure and old is None:
                    continue
                flag.write_text("")
                count.write_text("0")
                with self.subTest(name, remeasure=remeasure), contextlib.ExitStack() as stack:
                    if name == "VS-5":
                        stack.enter_context(after_t0(flag, "once"))
                    if not remeasure:
                        stack.enter_context(mock.patch.object(m, "_remeasure", no_remeasure))
                    r = m.run_target(root, "aisef2/toy.py::positive", kill)
                    self.assertEqual(classes(r), truth if remeasure else old, r.get("error"))
                    if remeasure:
                        self.assertEqual(m.target_problems(r, root),
                                         [] if truth[0] == "KILLED" else [f"aisef2/toy.py::positive: unaudited survivor {x!r}"
                                                                          for x in r["survivors"]])
                        self.assertTrue(rows_of(r, "unconfirmed"))   # the path was taken, so the toy is not vacuous
        # pycache, [q, p] without the fresh re-measure: the cache mutant 1 left decides mutant 2 (the prover's 1 SURVIVED,
        # 5 INFRA in that order)
        with mock.patch.object(m, "_remeasure", no_remeasure):
            r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_q_nopyc.py", "tests/v2/test_p_pyc.py"])
        self.assertEqual(classes(r), ["SURVIVED", "INFRA"])

    @unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
    def test_a_fault_a_passing_run_leaves_for_the_next_is_never_a_kill(self):
        """PL-2, process-env prover: a fixed port bound without SO_REUSEADDR fails a run started within TIME_WAIT of a
        passing one, and a passing run recreates it. Aligned, the mutant's first run failed (T0's TIME_WAIT), the
        control passed (it had expired) and left a new one, and the re-run failed with the same signature: a survivor
        recorded as a confirmed kill, with a clean record. Here a flag outside the tree stands for that kernel state:
        every PASS leaves it, the next run fails on it and clears it. The second control is the run it now fails."""
        d = self.enterContext(tempfile.TemporaryDirectory())
        busy = pathlib.Path(d) / "port"
        root = toy(pathlib.Path(d), POSITIVE, {"test_port.py": f"""
            import pathlib, unittest
            from aisef2.toy import positive
            BUSY = pathlib.Path({str(busy)!r})
            class P(unittest.TestCase):
                def test_binds_the_fixed_port(self):
                    positive(5)
                    if BUSY.exists() and BUSY.read_text() == "busy":
                        BUSY.write_text("")
                        self.fail("EADDRINUSE: the port is still in TIME_WAIT")
                    BUSY.write_text("busy")
            """})
        r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_port.py"])
        self.assertEqual(classes(r), ["SURVIVED", "SURVIVED"])   # the truth: the test never reads the mutant's answer
        why = rows_of(r, "unconfirmed")[0][1]["why"]
        self.assertTrue(why.startswith("kill not confirmed: the unmutated module PASS, then FAIL"), why)
        with mock.patch.object(m, "_remeasure", no_remeasure):   # without the fresh re-measure (fix 10): INFRA, not a kill
            busy.write_text("")
            self.assertEqual(classes(m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_port.py"]))[0], "INFRA")
        # the old failure, with one control: the first mutant is a confirmed kill, and nothing in the record says why not
        busy.write_text("")
        with mock.patch.object(m, "BRACKET", (m.BRACKET[0], m.BRACKET[2])):
            r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_port.py"])
        self.assertEqual(classes(r)[0], "KILLED")

    @unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
    def test_a_lost_report_channel_is_not_a_timeout(self):
        """VS-3: the test kills its own range anchor; wait() returns at once. That is INFRA, judged by the clock before
        release(), and no TIMEOUT. A real expiry (TIMEOUT patched to 2 s) is TIMEOUT. The toy signals its parent only
        once `anchor_guard` has proven it the range anchor this test's run started; unproven, the toy FAILs and signals
        nothing (INV-MUTATION-AUTHORITY)."""
        d = self.enterContext(tempfile.TemporaryDirectory())
        root = toy(pathlib.Path(d), POSITIVE, {"test_x.py": anchor_guard() + textwrap.dedent("""
            import signal, time, unittest
            from aisef2.toy import positive

            class X(unittest.TestCase):
                def test_x(self):
                    if positive(5) is None:
                        anchor = our_anchor()
                        self.assertTrue(anchor, "the parent is not the range anchor this test started")
                        os.kill(anchor, signal.SIGKILL)
                        time.sleep(30)
                    if positive(5) is False:
                        while True:
                            pass
            """)})
        # the guard's own negative: a parent that is not the anchor (this process, for a plain child) proves nothing
        plain = subprocess.run([sys.executable, "-c", anchor_guard() + "print(our_anchor())"], capture_output=True,
                               text=True, check=True)
        self.assertEqual(plain.stdout.strip(), "0")
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

    def test_the_error_says_which_unclassified_mutants_a_re_run_cannot_resolve(self):
        """Classification prover, VS-6 (a): a mutant whose kill test dies with no summary is INFRA for good, and the
        error still said 're-run them'. It now says how many a re-run cannot confirm, and that they need a kill test or
        a ruling; the prefix the merge tools and the tests read is unchanged."""
        def out(*whys):
            return m._summarise({"results": [{"mutant": f"m{i}", "class": "INFRA", "killed": False,
                                              "files": [{"file": "f", "outcome": "INFRA", "why": w}]}
                                             for i, w in enumerate(whys)]})["error"]
        self.assertEqual(out("kill not confirmed: the unmutated module FAIL"),
                         "UNCLASSIFIED: 1 mutant(s) neither killed nor survived {'INFRA': 1} — re-run them")
        self.assertEqual(out("exit -9, no unittest summary", "kill not confirmed: the unmutated module FAIL"),
                         "UNCLASSIFIED: 2 mutant(s) neither killed nor survived {'INFRA': 2} — 1 end a kill test with no "
                         "unittest summary (a signal, os._exit), which a re-run cannot confirm: each needs a kill test or "
                         "a ruling; re-run the rest")

    def test_timed_out_does_not_depend_on_the_order(self):
        """Order-equivalence prover: `timed_out` was written in execution order, so two orders of one kill set gave
        different record bytes for a TIMEOUT-class mutant, against section 7.1 (5). It is now sorted."""
        def entry(order):
            return m._classify({"mutant": "x", "files": [{"file": f, "outcome": o} for f, o in order]})["timed_out"]
        rows = [("tests/v2/test_small.py", "TIMEOUT"), ("tests/v2/test_big.py", "TIMEOUT"), ("tests/v2/test_ok.py", "PASS")]
        self.assertEqual(entry(rows), entry(rows[::-1]))
        self.assertEqual(entry(rows), ["tests/v2/test_big.py", "tests/v2/test_small.py"])

    def test_a_survivor_is_read_in_the_order_its_chain_ran(self):
        """ORD-4: a SURVIVED needs one PASS per kill file in the order its chain ran them — the declared order, or the
        `execution_order` the record names, which must be the kill set itself, in another order."""
        d = self.enterContext(tempfile.TemporaryDirectory())
        root = toy(pathlib.Path(d), POSITIVE, {})
        src, target = (root / "aisef2/toy.py").read_text(encoding="utf-8"), "aisef2/toy.py::positive"
        descs = [x for x, _ in m.mutants(src, "positive", {})]
        a, b = "tests/v2/test_a.py", "tests/v2/test_b.py"

        def problems(ran, files=None):
            return m.target_problems({
                "target": target, "runner": 2, "kill_tests": [a, b], "source_sha256": m.source_digest(src),
                "mutants": len(descs), "killed": 0, "survivors": descs, "t0": [],
                **({"execution_order": {"files": files, "from": "this test"}} if files else {}),
                "results": [{"mutant": x, "class": "SURVIVED", "killed": False,
                             "files": [{"file": f, "outcome": "PASS"} for f in ran]} for x in descs]}, root)
        not_ran = [f"{target}: inconsistent record: mutant {x!r}: SURVIVED without one PASS per kill file" for x in descs]
        with mock.patch.dict(m.AUDITED, {(target, x): "audited for this test" for x in descs}):
            self.assertEqual(problems([a, b]), [])
            self.assertEqual(problems([b, a], [b, a]), [])
            self.assertEqual(problems([b, a]), not_ran)
            self.assertEqual(problems([a, b], [b, a]), not_ran)
            self.assertEqual(problems([a], [a]), [f"{target}: inconsistent record: execution order {[a]!r} is not the "
                                                  "kill set in another order, or names no measurement"])

    def test_the_record_check_and_the_runner_agree_on_what_an_execution_order_is(self):
        """Final verifier: `_problems_v2` read `(execution_order or {}).get("files", kill_tests)`: `{}` and `None` were
        the declared order with no problem, a list crashed --check (AttributeError), `files: null` crashed it
        (TypeError), and an entry with no `from` passed. Now each malformed value is an inconsistent record — the same
        rule run_target refuses it with (a null one aside: run_target's None is no table, and it never writes one) —
        and is never read as the declared order."""
        d = self.enterContext(tempfile.TemporaryDirectory())
        root = toy(pathlib.Path(d), POSITIVE, {})
        src, target = (root / "aisef2/toy.py").read_text(encoding="utf-8"), "aisef2/toy.py::positive"
        descs = [x for x, _ in m.mutants(src, "positive", {})]
        a, b = "tests/v2/test_a.py", "tests/v2/test_b.py"
        for order in ({}, None, [a, b], {"files": None, "from": "x"}, {"from": "x"}, {"files": [a, b]},
                      {"files": [a, b], "from": None}, {"files": [a, 1], "from": "x"}, {"files": "ab", "from": "x"}):
            with self.subTest(order=order):
                if order is not None:   # run_target's None is "no table"; the runner never writes the key as null
                    refused = m.run_target(root, target, [a, b], order=order)
                    self.assertEqual((refused["error"], classes(refused), refused["execution_order"]),
                                     (m._order_problem(order, [a, b]), ["NOT_RUN"] * 2, order))
                record = {"target": target, "runner": 2, "kill_tests": [a, b], "source_sha256": m.source_digest(src),
                          "mutants": len(descs), "killed": 0, "survivors": descs, "t0": [], "execution_order": order,
                          "results": [{"mutant": x, "class": "SURVIVED", "killed": False,
                                       "files": [{"file": f, "outcome": "PASS"} for f in (a, b)]} for x in descs]}
                with mock.patch.dict(m.AUDITED, {(target, x): "audited for this test" for x in descs}), \
                        mock.patch.object(m, "PHASE_TARGETS", {"TOY": {target: [a, b]}}), \
                        mock.patch.object(m, "TARGETS", {target: [a, b]}):
                    self.assertEqual(m.target_problems(record, root),
                                     [f"{target}: inconsistent record: {m._order_problem(order, [a, b])}"])
                    self.assertEqual(m.problems_of({"targets": [record]}, root, "TOY"), m.target_problems(record, root))

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
    def test_a_runner_failure_outside_a_mutant_keeps_what_was_measured_and_names_what_did_not_run(self):
        """VS-4, classification prover: ca.establish failing for the 2nd target escaped main() with a traceback (no
        entry, no STOPPED or NOT RUN line), and an OSError(24) making T0's 2nd run directory escaped run_target and
        main (no record at all). A run directory failing inside a mutant's chain crashed _classify on a row with no
        outcome. Now each is a RUNNER_EXCEPTION stop that keeps every row measured, and main() names what did not run."""
        d = self.enterContext(tempfile.TemporaryDirectory())
        root = toy(pathlib.Path(d), POSITIVE + "\n\ndef other(x):\n    return x < 0\n", faulty(pathlib.Path(d) / "no"))
        targets = {"aisef2/toy.py::positive": ["tests/v2/test_strong.py"], "aisef2/toy.py::other": ["tests/v2/test_weak.py"]}
        rec = "closure-evidence/v2/toy/MUTATION.json"
        (root / rec).parent.mkdir(parents=True)
        real_establish, calls = m.ca.establish, []

        def establish(scratch):
            calls.append(scratch)
            if len(calls) == 2:
                raise BlockingIOError(35, "Resource temporarily unavailable")
            return real_establish(scratch)
        with mock.patch.object(m.ca, "establish", establish), mock.patch.object(m, "ROOT", root), \
                mock.patch.object(m, "RECORDS", {"TOY": rec}), mock.patch.object(m, "PHASE_TARGETS", {"TOY": targets}), \
                mock.patch.object(m, "TARGETS", targets), mock.patch("builtins.print") as out:
            self.assertEqual(m.main(["run", *targets]), 3)
        got = {t["target"]: t for t in json.loads((root / rec).read_text(encoding="utf-8"))["targets"]}
        self.assertEqual(classes(got["aisef2/toy.py::positive"]), ["KILLED", "KILLED"])
        self.assertTrue(got["aisef2/toy.py::other"]["error"].startswith("RUNNER_EXCEPTION before the target: BlockingIOError"))
        self.assertTrue(got["aisef2/toy.py::other"]["stopped"])
        lines = [c.args[0] for c in out.call_args_list]
        self.assertTrue([x for x in lines if x.startswith("STOPPED aisef2/toy.py::other: RUNNER_EXCEPTION")])
        self.assertIn("NOT RUN []", lines[-1])
        real_tmp, made = tempfile.TemporaryDirectory, []

        def tmp(*a, **kw):   # the run directories only; every other directory is made as usual
            if kw.get("prefix") == "run-":
                made.append(1)
                if len(made) == fail_at:
                    raise OSError(24, "Too many open files")
            return real_tmp(*a, **kw)
        kill = ["tests/v2/test_weak.py", "tests/v2/test_strong.py"]
        for fail_at, where in ((2, "before mutant 1 (T0 tests/v2/test_strong.py)"), (3, "at mutant 'L2 returns None' "
                                                                                      "(tests/v2/test_weak.py)")):
            made.clear()
            with self.subTest(fail_at=fail_at), mock.patch.object(m.tempfile, "TemporaryDirectory", tmp):
                r = m.run_target(root, "aisef2/toy.py::positive", kill)
                self.assertEqual(r["error"], f"RUNNER_EXCEPTION {where}: OSError(24, 'Too many open files')")
                self.assertTrue(r["stopped"])
                rows = [*r["t0"], *(x for res in r["results"] for x in res.get("files", []))]
                self.assertEqual([x["outcome"] for x in rows], ["PASS", "PASS", "INFRA"][3 - fail_at:])   # all kept, well formed
                self.assertEqual(classes(r), ["NOT_RUN", "NOT_RUN"] if fail_at == 2 else ["INFRA", "NOT_RUN"])

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

# --------------------------------------------------------------------------------------------- §5 T0

#: real V2.1 targets the null-mutant identities are checked on (pure: no kill file runs), SCRIPT targets included
NULL_SAMPLE = ("aisef2/app/run.py::admit", "aisef2/probe/process_effect.py::HARNESS/ask",
               "aisef2/probe/cli_invocation.py::AGENT/send", "aisef2/probe/cli_invocation.py::_harness_argv",
               "aisef2/probe/python_callable_v2.py::HARNESS/emit", "aisef2/probe/file_artifact.py::DIGEST",
               "aisef2/app/adapters.py::_bounded", "aisef2/plan/static_admission.py::check_contradictions")
#: probe() reads x["probe"]; test_text pins that text, which ast.unparse writes as x['probe'] (ORD-1)
ORD1_MODULE = 'def probe(x):\n    return x["probe"] if x else None\n'
ORD1_FILES = {
    "test_sem.py": """
        import unittest
        from aisef2.toy import probe
        class Sem(unittest.TestCase):
            def test_an_empty_request_has_no_probe(self):
                self.assertIsNone(probe({}))
        """,
    "test_text.py": """
        import pathlib, unittest
        from aisef2 import toy
        class Text(unittest.TestCase):
            def test_the_module_says_it_this_way(self):
                self.assertIn('x["probe"]', pathlib.Path(toy.__file__).read_text(encoding="utf-8"))
        """}
#: generator order: L2 returns None, L2 conditional negated, L2 string 'probe' emptied — only the second changes probe({})
ORD1_TRUTH = ["SURVIVED", "KILLED", "SURVIVED"]


class T0(unittest.TestCase):
    """ORD-1, PL-4, VS-6: the baseline is the null mutant made by mutants()' own rewrite, each kill file on its own; a
    file that fails it is refused for the target, never used as kill evidence."""

    def test_the_null_mutant_is_the_rewrite_every_mutant_gets(self):
        import ast
        for target in NULL_SAMPLE:
            rel, func = target.split("::")
            src = (ROOT / rel).read_text(encoding="utf-8")
            null = m.null_mutant(src, func)
            script, _, inner = func.partition("/")
            with self.subTest(target):
                if inner:   # the module with the script left out is the same; the script parses to the same tree
                    a, b = ast.parse(null), ast.parse(src)
                    ca_, cb = m._script(a, script), m._script(b, script)
                    self.assertEqual(ca_.value, ast.unparse(ast.parse(cb.value)))
                    self.assertEqual(ast.dump(ast.parse(ca_.value)), ast.dump(ast.parse(cb.value)))
                    ca_.value = cb.value = ""
                    self.assertEqual(ast.dump(a), ast.dump(b))
                else:
                    self.assertEqual(ast.dump(ast.parse(null)), ast.dump(ast.parse(src)))
                found = m.mutants(src, func, m._enum_members(src, ROOT))
                self.assertTrue(found)
                for desc, mutated in found:
                    self.assertEqual(m.null_mutant(mutated, func), mutated, desc)   # the rewrite of a mutant is itself

    @unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
    def test_a_kill_file_that_pins_the_text_is_refused_not_used(self):
        """ORD-1 on a toy: test_text pins source text that every mutant's rewrite changes. The old baseline (the
        original bytes) let it 'kill' all 3 mutants, 0 survivors against a truth of 2. T0 refuses it, names it, and runs
        it once on the original (which passes): a rewrite-sensitive file, not a broken snapshot."""
        d = self.enterContext(tempfile.TemporaryDirectory())
        root = toy(pathlib.Path(d), ORD1_MODULE, ORD1_FILES)
        both = ["tests/v2/test_sem.py", "tests/v2/test_text.py"]
        r = m.run_target(root, "aisef2/toy.py::probe", both)
        self.assertRegex(r["error"], r"^kill tests fail on the unmutated tree \(T0 null mutant\): tests/v2/test_text\.py: "
                                     r"FAIL FAIL: test_the_module_says_it_this_way .* \| AssertionError$")
        self.assertEqual([x["outcome"] for x in r["t0"]], ["PASS", "FAIL"])
        self.assertEqual([(x["file"], x["outcome"]) for x in r["original"]], [("tests/v2/test_text.py", "PASS")])
        self.assertEqual(classes(r), ["NOT_RUN"] * 3)
        self.assertEqual(classes(m.run_target(root, "aisef2/toy.py::probe", both[:1])), ORD1_TRUTH)
        # the old failure, with the original bytes as the baseline: every mutant "killed" by the text pin
        with mock.patch.object(m, "null_mutant", lambda src, func: src):
            self.assertEqual(classes(m.run_target(root, "aisef2/toy.py::probe", both)), ["KILLED"] * 3)

    @unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
    def test_the_t0_command_runs_t0_alone_and_writes_nothing(self):
        d = self.enterContext(tempfile.TemporaryDirectory())
        root = toy(pathlib.Path(d), ORD1_MODULE, ORD1_FILES)
        targets = {"aisef2/toy.py::probe": ["tests/v2/test_sem.py", "tests/v2/test_text.py"]}
        rec = "closure-evidence/v2/toy/MUTATION.json"
        with mock.patch.object(m, "ROOT", root), mock.patch.object(m, "RECORDS", {"TOY": rec}), \
                mock.patch.object(m, "PHASE_TARGETS", {"TOY": targets}), mock.patch.object(m, "TARGETS", targets), \
                mock.patch("builtins.print") as out:
            self.assertEqual(m.main(["t0", *targets]), 1)
            self.assertEqual(m.main(["t0", *targets, "--tests", "tests/v2/test_sem.py"]), 0)
            # order-equivalence prover: a refused kill set printed "T0 ...: PASS" and exited 0 (no T0 row ran at all)
            self.assertEqual(m.main(["t0", *targets, "--tests", m.NOT_KILL_FILES[0]]), 1)
        lines = [c.args[0] for c in out.call_args_list]
        self.assertEqual(lines.pop(), f"T0 aisef2/toy.py::probe: not a kill file: {list(m.NOT_KILL_FILES[:1])} (NOT_KILL_FILES)")
        self.assertEqual([json.loads(x)["outcome"] for x in lines if x.startswith("{")],
                         ["PASS", "FAIL", "PASS", "PASS"])   # T0 sem, T0 text, the original text, then sem alone
        self.assertEqual([x for x in lines if x.startswith("T0 ")][-1], "T0 aisef2/toy.py::probe: PASS")
        self.assertFalse((root / rec).exists())

# --------------------------------------------------------------------------------------------- §6 kill sets


class KillSets(unittest.TestCase):
    """ORD-1, §6: a file of byte- and text-identity tests is part of the suite and never kill evidence."""

    def test_no_kill_set_names_a_byte_identity_file(self):
        named = {f for kill in m.TARGETS.values() for f in kill}
        self.assertEqual(sorted(named & set(m.NOT_KILL_FILES)), [])
        self.assertTrue(all((ROOT / f).is_file() for f in m.NOT_KILL_FILES))
        self.assertIn(m._V21_ID, named)   # the semantic half keeps its name, and every kill set that named it

    def test_a_kill_set_naming_one_is_refused_before_anything_runs(self):
        with tempfile.TemporaryDirectory() as d:
            root = toy(pathlib.Path(d), POSITIVE, {})
            r = m.run_target(root, "aisef2/toy.py::positive", ["tests/v2/test_v21_identity_bytes.py"])
        self.assertIn("not a kill file: ['tests/v2/test_v21_identity_bytes.py']", r["error"])
        self.assertEqual(classes(r), ["NOT_RUN", "NOT_RUN"])
        self.assertNotIn("t0", r)

    def test_an_execution_order_that_is_not_the_kill_set_is_refused_before_anything_runs(self):
        """ORD-4: an execution order runs the declared kill set, every file once, and names the measurement it came
        from; anything else refuses the target, with the declared `kill_tests` and the order given both kept."""
        a, b = "tests/v2/test_a.py", "tests/v2/test_b.py"
        with tempfile.TemporaryDirectory() as d:
            root = toy(pathlib.Path(d), POSITIVE, {})
            for order in ({"files": [a], "from": "x"}, {"files": [b, a, a], "from": "x"}, {"files": [b, a]}):
                with self.subTest(order=order):
                    r = m.run_target(root, "aisef2/toy.py::positive", [a, b], order=order)
                    self.assertIn("is not the kill set in another order, or names no measurement", r["error"])
                    self.assertEqual((r["kill_tests"], r["execution_order"]), ([a, b], order))
                    self.assertEqual(classes(r), ["NOT_RUN", "NOT_RUN"])
                    self.assertNotIn("t0", r)

    def test_main_takes_each_targets_order_from_the_table_and_the_rest_in_declared_order(self):
        """`run --order TABLE`: a target the table lists gets its entry, with the table's path and sha256; any other
        target the declared order; a table naming a target that does not exist stops main before anything runs."""
        a, b = "tests/v2/test_a.py", "tests/v2/test_b.py"
        targets = {"aisef2/toy.py::positive": [a, b], "aisef2/toy.py::other": [a, b]}
        calls = []

        def fake(root, target, tests, pristine=None, on_mutant=None, t0_only=False, order=None):
            calls.append((target, tests, order))
            return m._summarise({"target": target, "runner": 2, "kill_tests": list(tests), "mutants": 0, "results": []})
        with tempfile.TemporaryDirectory() as d:
            root = toy(pathlib.Path(d), POSITIVE + "\n\ndef other(x):\n    return x\n", {})
            table = pathlib.Path(d) / "order.json"
            raw = json.dumps({"aisef2/toy.py::positive": {"files": [b, a], "from": "T0 seconds (this test)"}}).encode()
            table.write_bytes(raw)
            with mock.patch.object(m, "ROOT", root), mock.patch.object(m, "RECORDS", {"TOY": "rec.json"}), \
                    mock.patch.object(m, "PHASE_TARGETS", {"TOY": targets}), mock.patch.object(m, "TARGETS", targets), \
                    mock.patch.object(m, "run_target", fake), mock.patch("builtins.print"):
                m.main(["run", "--order", str(table), *targets])
                self.assertEqual(calls, [
                    ("aisef2/toy.py::positive", [a, b], {"files": [b, a], "from": "T0 seconds (this test)",
                                                         "table": str(table), "table_sha256": hashlib.sha256(raw).hexdigest()}),
                    ("aisef2/toy.py::other", [a, b], None)])
                table.write_text(json.dumps({"aisef2/toy.py::gone": {"files": [a, b], "from": "x"}}), encoding="utf-8")
                calls.clear()
                with self.assertRaisesRegex(SystemExit, "not a mutation target in the execution-order table"):
                    m.main(["run", "--order", str(table), *targets])
                self.assertEqual(calls, [])

    def test_main_refuses_a_table_with_any_bad_entry_before_the_first_target_runs(self):
        """Final verifier: a bad entry was refused only at its target's turn — after every earlier target had run —
        and its NOT_RUN entry replaced that target's result in the record. main now checks every entry of the table
        (the targets it runs and the ones it does not) with run_target's own rule before the first target runs."""
        a, b = "tests/v2/test_a.py", "tests/v2/test_b.py"
        first, second = "aisef2/toy.py::positive", "aisef2/toy.py::other"
        targets = {first: [a, b], second: [a, b]}
        calls = []

        def fake(root, target, tests, pristine=None, on_mutant=None, t0_only=False, order=None):
            calls.append(target)
            return m._summarise({"target": target, "runner": 2, "kill_tests": list(tests), "mutants": 0, "results": []})
        good = {"files": [b, a], "from": "T0 seconds (this test)"}
        with tempfile.TemporaryDirectory() as d:
            root = toy(pathlib.Path(d), POSITIVE + "\n\ndef other(x):\n    return x\n", {})
            record = root / "rec.json"
            kept = json.dumps({"record": "toy", "targets": [{"target": second, "kept": "the earlier result"}]}) + "\n"
            record.write_text(kept, encoding="utf-8")
            table = pathlib.Path(d) / "order.json"
            with mock.patch.object(m, "ROOT", root), mock.patch.object(m, "RECORDS", {"TOY": "rec.json"}), \
                    mock.patch.object(m, "PHASE_TARGETS", {"TOY": targets}), mock.patch.object(m, "TARGETS", targets), \
                    mock.patch.object(m, "run_target", fake), mock.patch("builtins.print"):
                for bad in ({"files": [a], "from": "x"}, {"files": [b, a, a], "from": "x"}, {"files": [a, a], "from": "x"},
                            {"files": [b, a]}, {"files": [b, a], "from": ""}, {"from": "x"}, {}, [b, a], None):
                    for argv in ([first, second], [first]):   # the bad entry's target runs second, or not at all
                        with self.subTest(bad=bad, argv=argv):
                            table.write_text(json.dumps({first: good, second: bad}), encoding="utf-8")
                            with self.assertRaises(SystemExit) as stop:
                                m.main(["run", "--order", str(table), *argv])
                            why = (f"execution order {bad.get('files') if isinstance(bad, dict) else bad!r} is not the "
                                   "kill set in another order, or names no measurement")
                            self.assertEqual(stop.exception.code, f"execution-order table refused, nothing ran: "
                                                                  f"{ {second: why} }")
                            self.assertEqual((calls, record.read_text(encoding="utf-8")), ([], kept))
                table.write_text(json.dumps({first: good, second: {**good, "files": [a, b]}}), encoding="utf-8")
                m.main(["run", "--order", str(table), first])   # every entry valid: it runs
                self.assertEqual(calls, [first])

    def test_run_misuse_is_refused_before_anything_runs(self):
        """Final verifier: `run A --order T` ran A in declared order and refused only after it; `run --order` raised
        IndexError; `run --order T` ran every target of every phase. Each is refused, with a message and a non-zero
        exit, before any target runs and before any record is written; so is a name that is not a target."""
        a, b = "tests/v2/test_a.py", "tests/v2/test_b.py"
        targets = {"aisef2/toy.py::positive": [a, b]}
        calls = []

        def fake(root, target, tests, pristine=None, on_mutant=None, t0_only=False, order=None):
            calls.append(target)
            return m._summarise({"target": target, "runner": 2, "kill_tests": list(tests), "mutants": 0, "results": []})
        with tempfile.TemporaryDirectory() as d:
            root = toy(pathlib.Path(d), POSITIVE, {})
            table = pathlib.Path(d) / "order.json"
            table.write_text(json.dumps({"aisef2/toy.py::positive": {"files": [b, a], "from": "x"}}), encoding="utf-8")
            with mock.patch.object(m, "ROOT", root), mock.patch.object(m, "RECORDS", {"TOY": "rec.json"}), \
                    mock.patch.object(m, "PHASE_TARGETS", {"TOY": targets}), mock.patch.object(m, "TARGETS", targets), \
                    mock.patch.object(m, "run_target", fake), mock.patch("builtins.print"):
                for argv in (["run", *targets, "--order", str(table)], ["run", "--order"], ["run", "--order", str(table)],
                             ["run", "--order", str(table), *targets, "--order", str(table)],
                             ["run", *targets, "aisef2/toy.py::gone"]):
                    with self.subTest(argv=argv):
                        with self.assertRaises(SystemExit) as stop:
                            m.main(argv)
                        # a message (str): the interpreter prints it and exits 1
                        self.assertRegex(stop.exception.code, r"^usage: mutation\.py run --order TABLE\.json TARGET\.\.\. |"
                                                              r"^not a mutation target: \['aisef2/toy\.py::gone'\]$")
                self.assertEqual(calls, [])
                self.assertFalse((root / "rec.json").exists())
                m.main(["run", "--order", str(table), *targets])   # the same table, used as the usage says: it runs
                self.assertEqual(calls, list(targets))


# --------------------------------------------------------------------------------------------- §7 order independence

#: f's mutants, generator order, and the class each must get in every order: every kind of evidence at least once
ORDER_MODULE = "def f(x, verbose=False):\n    if x > 0:\n        return 'pos'\n    return 'neg'\n"
ORDER_TRUTH = {"L2 condition negated": "KILLED",      # a/k FAIL; h hangs on it first in some orders (TIMEOUT, then a kill)
               "L4 returns None": "INFRA",            # i dies by SIGKILL on it, reproducibly; nothing else sees it
               "L1 False->True": "SURVIVED",          # nothing tests verbose; c leaves .scratch in the tree for it
               "L2 Gt->LtE": "KILLED",
               "L3 returns None": "KILLED",           # i is INFRA on it too: a kill after an infrastructure row
               "L4 string 'neg' emptied": "TIMEOUT",  # only h sees it, and hangs
               "L3 string 'pos' emptied": "KILLED"}   # same size as its predecessor (a TIMEOUT): the bytecode channel
ORDER_FILES = {
    "test_a.py": """
        import pathlib, unittest
        from aisef2.toy import f
        class A(unittest.TestCase):
            def test_positive(self):
                self.assertFalse(pathlib.Path(".scratch").exists())
                self.assertEqual(f(1), "pos")
        """,
    "test_h.py": """
        import unittest
        from aisef2.toy import f
        class H(unittest.TestCase):
            def test_negative_or_hang(self):
                while f(-1) in ("pos", ""):
                    pass
        """,
    "test_i.py": """
        import os, signal, unittest
        from aisef2.toy import f
        class I(unittest.TestCase):
            def test_dies_on_none(self):
                if f(-1) is None or f(1) is None:
                    os.kill(os.getpid(), signal.SIGKILL)
        """,
    "test_c.py": """
        import pathlib, unittest
        from aisef2.toy import f
        class C(unittest.TestCase):
            def test_leaves_scratch_for_verbose(self):
                if f.__defaults__ == (True,):
                    pathlib.Path(".scratch").write_text("x")
        """,
    "test_k.py": """
        import pathlib, subprocess, sys, unittest
        TREE = str(pathlib.Path(__file__).resolve().parents[2])
        class K(unittest.TestCase):
            def test_positive_through_an_isolated_child(self):
                code = f"import sys; sys.path.insert(0, {TREE!r}); from aisef2.toy import f; print(f(1))"
                out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True).stdout
                self.assertEqual(out.strip(), "pos")
        """}


def old_stop_rule(tg, entry, src):
    """The old runner's loop, for the control: stop at the first run that does not PASS and call it a kill."""
    rows = entry["files"] = []
    m._write(tg, src)
    for rel in tg.tests:
        if m._run_file(tg, rel, rows)["outcome"] != "PASS":
            rows[-1]["outcome"] = "FAIL"
            entry["killed_by"] = {"file": rel}
            return


@unittest.skipUnless(POSIX, "the runner's process ranges and cleanup authority are measured on POSIX")
class Order(unittest.TestCase):
    """The owner's rule: a reorder never changes a class, on a sample with killed, survivor, timeout and infrastructure
    cases (§7). Five kill files in every rotation (each file in each position, each pair in both relative orders) — as
    the declared kill set, and as the execution order of one declared set (ORD-4: an execution-order table); each
    protection switched off in turn must change a class, so the toy cannot pass vacuously."""

    KILL = ["tests/v2/test_a.py", "tests/v2/test_h.py", "tests/v2/test_i.py", "tests/v2/test_c.py", "tests/v2/test_k.py"]

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = toy(pathlib.Path(cls._tmp.name), ORDER_MODULE, ORDER_FILES)
        cls.orders = [cls.KILL[i:] + cls.KILL[:i] for i in range(len(cls.KILL))]
        cls.table = [{"files": o, "from": f"the declared set, rotated to {o[0]} (this test)"} for o in cls.orders[1:]]
        with mock.patch.object(m, "TIMEOUT", 2):
            cls.runs = [m.run_target(cls.root, "aisef2/toy.py::f", order) for order in cls.orders]
            cls.reordered = [m.run_target(cls.root, "aisef2/toy.py::f", cls.KILL, order=o) for o in cls.table]

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def run_with(self, order, **patches):
        with mock.patch.object(m, "TIMEOUT", 2), contextlib.ExitStack() as stack:
            for name, value in patches.items():
                stack.enter_context(mock.patch.object(m, name, value))
            return m.run_target(self.root, "aisef2/toy.py::f", order)

    def test_the_sample_covers_every_kind_of_evidence(self):
        src = (self.root / "aisef2/toy.py").read_text(encoding="utf-8")
        found = m.mutants(src, "f", {})
        self.assertEqual([d for d, _ in found], list(ORDER_TRUTH))
        self.assertTrue({"KILLED", "SURVIVED", "TIMEOUT", "INFRA"} <= set(ORDER_TRUTH.values()))
        sizes, truth = [len(s) for _, s in found], list(ORDER_TRUTH.values())
        self.assertTrue(any(sizes[i] == sizes[i + 1] and truth[i] != truth[i + 1] for i in range(len(sizes) - 1)))
        rows = {(o[0], d, x["file"]): x["outcome"] for o, r in zip(self.orders, self.runs, strict=True) for d, x in rows_of(r)}
        self.assertIn("TIMEOUT", {v for (first, d, f), v in rows.items() if d == "L2 condition negated" and f.endswith("_h.py")})
        self.assertIn("INFRA", {v for (first, d, f), v in rows.items() if d == "L3 returns None" and f.endswith("_i.py")})
        self.assertTrue(any(x.get("residue") for r in self.runs for _, x in rows_of(r)))

    def test_every_order_gives_every_mutant_its_designed_class(self):
        for order, r in zip(self.orders, self.runs, strict=True):
            with self.subTest(first=order[0]):
                self.assertEqual(dict(zip([x["mutant"] for x in r["results"]], classes(r), strict=True)), ORDER_TRUTH)
                self.assertNotIn("stopped", r)
                self.assertEqual(r["error"], self.runs[0]["error"])   # UNCLASSIFIED: the TIMEOUT and the INFRA mutant
                kills = sum(c == "KILLED" for c in classes(r))
                self.assertEqual(len(rows_of(r, "control")), 2 * kills)    # every kill bracketed exactly once
                self.assertEqual(len(rows_of(r, "rerun")), kills)
        for key in ("classes", "killed", "survivors"):
            self.assertEqual(len({json.dumps(r[key]) for r in self.runs}), 1, key)
        self.assertEqual(len({json.dumps([x["mutant"] for x in r["results"] if "timed_out" in x]) for r in self.runs}), 1)

    def test_a_run_s_outcome_does_not_depend_on_what_ran_before_it(self):
        seen: dict = {}
        for r in self.runs:
            for d, x in rows_of(r):
                key = (d, x["file"])
                got = (x["outcome"], x.get("first"), x.get("exit"), x["tail_sha256"] if x["outcome"] in ("PASS", "FAIL") else "")
                self.assertEqual(seen.setdefault(key, got), got, key)
        self.assertGreater(len(seen), 20)

    def test_an_execution_order_changes_no_class_and_the_record_only_where_it_must(self):
        """ORD-4: the declared kill set run in each other rotation an execution-order table gives. The record keeps the
        declared `kill_tests` and names the order and its measurement (`execution_order`); every class, the target's
        fields, T0 and the verdict are the declared order's; and the record differs from it only there and in which
        reproduced FAIL came first: each (mutant, file) has the same rows in every order, a mutant not killed ran every
        file in the table's order, and a kill is the first file in that order whose FAIL reproduces, nothing after it."""
        def said(x):   # a run without its clock, and its tail hash only where it is stable (PASS, FAIL)
            return {k: v for k, v in x.items() if k not in ("seconds", "overhead_s", "tail", "tail_sha256")} | (
                {"tail_sha256": x["tail_sha256"]} if x["outcome"] in ("PASS", "FAIL") else {})

        def rest(r):
            return {**{k: v for k, v in r.items() if k not in ("execution_order", "t0", "results")},
                    "t0": [said(x) for x in r["t0"]],
                    "results": [{k: v for k, v in x.items() if k not in ("files", "killed_by")} for x in r["results"]]}
        groups: dict = {}
        for r in [*self.runs, *self.reordered]:
            for x in r["results"]:
                for f in dict.fromkeys(y["file"] for y in x["files"]):
                    got = [said(y) for y in x["files"] if y["file"] == f]
                    self.assertEqual(groups.setdefault((x["mutant"], f), got), got, (x["mutant"], f))
        reproduces = {k for k, g in groups.items() if any("role" not in y and y["outcome"] == "FAIL" for y in g)}
        ref, moved = self.runs[0], 0
        self.assertNotIn("execution_order", ref)   # no table: the declared order, as before
        for o, r in zip(self.table, self.reordered, strict=True):
            with self.subTest(first=o["files"][0]):
                self.assertEqual((r["kill_tests"], r["execution_order"]), (self.KILL, o))
                self.assertEqual(dict(zip([x["mutant"] for x in r["results"]], classes(r), strict=True)), ORDER_TRUTH)
                self.assertTrue(any(z.get("residue") for _, z in rows_of(r)))   # the residue case, in this order too
                self.assertEqual(rest(r), rest(ref))
                self.assertEqual(m.target_problems(r, self.root), m.target_problems(ref, self.root))
                for x, y in zip(r["results"], ref["results"], strict=True):
                    ran = list(dict.fromkeys(z["file"] for z in x["files"]))
                    if x["class"] != "KILLED":
                        self.assertEqual(ran, o["files"])
                        continue
                    first = next(f for f in o["files"] if (x["mutant"], f) in reproduces)
                    self.assertEqual((x["killed_by"]["file"], ran), (first, o["files"][:o["files"].index(first) + 1]))
                    self.assertTrue(m._confirmed(x))
                    moved += x["killed_by"]["file"] != y["killed_by"]["file"]
        self.assertGreater(moved, 0)   # the order decided which reproduced FAIL came first, and nothing else

    def test_each_protection_switched_off_changes_a_class(self):
        fixed = int((self.root / "aisef2/toy.py").stat().st_mtime) + 1

        def same_second(path, text, last):
            path.write_text(text, encoding="utf-8")
            os.utime(path, (fixed, fixed))
            return fixed
        controls = {"the stamp (§1)": ({"_write_version": same_second}, self.KILL[::-1]),
                    "the tree restore (§2)": ({"_residue": lambda tg: {}, "_remeasure": no_remeasure},
                                              ["tests/v2/test_c.py", "tests/v2/test_a.py",
                                                                           *self.KILL[1:3], self.KILL[4]]),
                    "the per-run classification (§3, §4)": ({"_mutant": old_stop_rule}, self.KILL)}
        for name, (patches, order) in controls.items():
            with self.subTest(name):
                r = self.run_with(order, **patches)
                got = dict(zip([x["mutant"] for x in r["results"]], [x["class"] for x in r["results"]], strict=True))
                self.assertNotEqual(got, ORDER_TRUTH)


if __name__ == "__main__":
    unittest.main()
