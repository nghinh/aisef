"""validation/v21/read_set.py on a toy tree: the recorder of the read-set v21_snapshot_delta.py --read-set consumes.
Real kill files run through the runner's own `_run_file` (real ProcessRange, real cleanup authority). Every channel the
recorder relies on has a control that switches it off and shows what it then misses, so a toy that stopped exercising a
channel fails instead of passing vacuously: the child hook (a child that does not inherit it reads unseen), the os.stat
wrapper, and the filter of the interpreter's own walk to find code (without it every kill file lists the root and
looks up every sibling test file). Not a kill file."""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import v21_snapshot_delta as D  # noqa: E402
from validation.v2 import mutation as M  # noqa: E402
from validation.v21 import read_set as RS  # noqa: E402

POSIX = os.name == "posix"
COPY = ("pkg", "data", "data2", "tests")
INIT = "tests/v2/__init__.py"
T = "tests/v2/test_{}.py"

TREE = {
    "pkg/__init__.py": "", "pkg/mod.py": "VALUE = 1\n",
    "pkg/registry.py": """
        import os
        import pathlib


        def names(directory):
            return sorted(os.listdir(directory))


        def txt(directory):   # pathlib's walk: the stdlib's frames sit between this file and the scandir
            return sorted(p.name for p in pathlib.Path(directory).rglob("*.txt"))
        """,
    "data/a.txt": "a", "data/c.txt": "c", "data/sub/b.txt": "b", "data2/we\tird/x.txt": "x",
    "tests/__init__.py": "", INIT: "",
    T.format("nothing"): """
        import unittest
        class K(unittest.TestCase):
            def test(self): self.assertTrue(True)
        """,
    T.format("opens"): """
        import unittest
        import pkg.mod
        class K(unittest.TestCase):
            def test(self): self.assertEqual(open("data/a.txt").read(), "a")
        """,
    T.format("lists"): """
        import os, unittest
        class K(unittest.TestCase):
            def test(self):
                self.assertEqual(os.listdir("data/sub"), ["b.txt"])
                with os.scandir("data") as it:
                    self.assertEqual(sorted(e.name for e in it), ["a.txt", "c.txt", "sub"])
        """,
    T.format("registry"): """
        import unittest
        from pkg import registry
        class K(unittest.TestCase):
            def test(self):
                self.assertEqual(registry.names("data/sub"), ["b.txt"])
                self.assertEqual(registry.txt("data"), ["a.txt", "b.txt", "c.txt"])   # data and data/sub
        """,
    T.format("two_callers"): """
        import os, unittest
        from pkg import registry
        class K(unittest.TestCase):
            def test(self):
                self.assertEqual(registry.names("data"), ["a.txt", "c.txt", "sub"])   # data: by the registry ...
                with os.scandir("data") as it:   # ... and by this file
                    self.assertEqual(sorted(e.name for e in it), ["a.txt", "c.txt", "sub"])
        """,
    T.format("child_lists"): """
        import subprocess, sys, unittest
        class K(unittest.TestCase):
            def test(self):   # each child is hooked: its own stack tells who listed
                a = subprocess.run([sys.executable, "-c", "from pkg import registry; print(registry.names('data/sub'))"],
                                   capture_output=True, text=True)
                b = subprocess.run([sys.executable, "-c", "import os; print(os.listdir('data/sub'))"],
                                   capture_output=True, text=True)
                self.assertEqual((a.stdout.strip(), b.stdout.strip()), ("['b.txt']", "['b.txt']"))
        """,
    T.format("odd_names"): """
        import os, unittest
        class K(unittest.TestCase):
            def test(self):   # a tab and a backslash in a name: one field of an event line each
                self.assertEqual(os.listdir("data2/we\\tird"), ["x.txt"])
        """,
    T.format("stats"): """
        import os, unittest
        class K(unittest.TestCase):
            def test(self): self.assertTrue(os.path.exists("data/c.txt"))
        """,
    T.format("child"): """
        import subprocess, sys, unittest
        class K(unittest.TestCase):
            def test(self):   # inherits the environment, PYTHONPATH with it
                r = subprocess.run([sys.executable, "-c", "print(open('data/a.txt').read())"], capture_output=True, text=True)
                self.assertEqual(r.stdout.strip(), "a")
        """,
    T.format("child_env"): """
        import os, subprocess, sys, unittest
        class K(unittest.TestCase):
            def test(self):   # its own environment: no PYTHONPATH, so the hook is not loaded
                r = subprocess.run([sys.executable, "-c", "print(open('data/c.txt').read())"], capture_output=True,
                                   text=True, env={"PATH": os.environ["PATH"]})
                self.assertEqual(r.stdout.strip(), "c")
        """,
    T.format("child_pythonpath"): """
        import os, subprocess, sys, unittest
        class K(unittest.TestCase):
            def test(self):   # the environment copied, PYTHONPATH replaced: the hook's directory is gone
                r = subprocess.run([sys.executable, "-c", "print(open('data/c.txt').read())"], capture_output=True,
                                   text=True, env={**os.environ, "PYTHONPATH": os.getcwd()})
                self.assertEqual(r.stdout.strip(), "c")
        """,
    T.format("child_isolated"): """
        import subprocess, sys, unittest
        class K(unittest.TestCase):
            def test(self):   # inherits PYTHONPATH, and -I ignores it
                r = subprocess.run([sys.executable, "-I", "-c", "print(open('data/c.txt').read())"], capture_output=True, text=True)
                self.assertEqual(r.stdout.strip(), "c")
        """,
    T.format("child_other"): """
        import subprocess, unittest
        class K(unittest.TestCase):
            def test(self):   # not a Python process
                self.assertEqual(subprocess.run(["/bin/cat", "data/a.txt"], capture_output=True, text=True).stdout, "a")
        """,
    T.format("dirfd"): """
        import os, unittest
        class K(unittest.TestCase):
            def test(self):   # b.txt is relative to the directory's fd, not to the working directory
                fd = os.open("data/sub", os.O_RDONLY)
                try:
                    self.assertTrue(os.stat("b.txt", dir_fd=fd))
                finally:
                    os.close(fd)
        """,
    T.format("fails"): """
        import unittest
        class K(unittest.TestCase):
            def test(self):
                open("data/c.txt").read()
                self.fail("after reading data/c.txt")
        """,
}
FILES = {k: textwrap.dedent(v) for k, v in TREE.items()}
KILL = sorted(k for k in FILES if k.startswith("tests/v2/test_"))
PASSING = [k for k in KILL if k != T.format("fails")]


def build(base: pathlib.Path) -> pathlib.Path:
    root = base / "root"
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def snapshot(root: pathlib.Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


@unittest.skipUnless(POSIX, "exercised on POSIX only: the child channel is by inherited environment and /bin/cat")
class ToyRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.root = build(pathlib.Path(cls._tmp.name))
        cls.private = pathlib.Path(cls._tmp.name) / "tmp"   # where every scratch directory of the recorder goes
        cls.private.mkdir()
        cls.before = snapshot(cls.root)
        for p in (mock.patch.object(M, "COPY", COPY), mock.patch.object(tempfile, "tempdir", str(cls.private))):
            p.start()
            cls.addClassCleanup(p.stop)
        cls.doc = RS.record(cls.root, KILL)
        cls.after = snapshot(cls.root)
        cls.kf = cls.doc["kill_files"]

    def control(self, controls, files):
        return RS.record(self.root, files, controls)["kill_files"]

    # -- what each kill file read: exact, relative to the one that reads nothing --------------------------------------

    def test_each_kill_file_has_exactly_what_it_read(self):
        nothing = T.format("nothing")
        base = set(self.kf[nothing]["opened"]) - {nothing}
        self.assertEqual(base, {INIT, "tests/v2"})   # the package its import opens, the directory discover looked up
        reg = {"pkg/__init__.py", "pkg/registry.py"}
        extra = {"opens": {"data/a.txt", "pkg/__init__.py", "pkg/mod.py"}, "stats": {"data/c.txt"},
                 "lists": set(), "child": {"data/a.txt"}, "child_env": set(), "child_isolated": set(),
                 "child_pythonpath": set(), "registry": reg, "two_callers": reg, "child_lists": reg,
                 "child_other": set(), "dirfd": {"data/sub"}}
        for name, more in extra.items():
            with self.subTest(name):
                f = T.format(name)
                self.assertEqual(self.kf[f]["opened"], sorted(base | {f} | more))
        self.assertEqual(self.kf[nothing]["listed"], [])
        listing = {"lists": ["data", "data/sub"], "registry": ["data", "data/sub"],   # listdir, scandir, rglob
                   "two_callers": ["data"], "child_lists": ["data/sub"], "odd_names": ["data2/we\tird"]}
        for name, listed in listing.items():
            self.assertEqual(self.kf[T.format(name)]["listed"], listed, name)
        for f in PASSING:
            if f not in {T.format(n) for n in listing}:
                self.assertEqual(self.kf[f]["listed"], [], f)

    def test_each_listed_directory_is_attributed_to_the_file_of_the_tree_that_made_the_listing(self):
        """listed_by: the innermost file of the tree on the stack; listed_via: up to four of them, the callers too."""
        k = {n: self.kf[T.format(n)] for n in ("lists", "registry", "two_callers", "child_lists", "nothing")}
        reg, mine = "pkg/registry.py", {n: T.format(n) for n in ("lists", "registry", "two_callers", "child_lists")}
        self.assertEqual(k["lists"]["listed_by"], {"data": [mine["lists"]], "data/sub": [mine["lists"]]})   # its own call
        self.assertEqual(k["registry"]["listed_by"], {"data": [reg], "data/sub": [reg]})   # pathlib's frames are not files of the tree
        self.assertEqual(k["registry"]["listed_via"], {d: [reg, mine["registry"]] for d in ("data", "data/sub")})
        self.assertEqual(k["two_callers"]["listed_by"],   # the union over the events of a directory
                         {"data": sorted([reg, mine["two_callers"]])})
        self.assertEqual(k["child_lists"]["listed_by"], {"data/sub": sorted([reg, "<native>"])})   # a -c child, hooked
        self.assertEqual(k["child_lists"]["listed_via"], {"data/sub": sorted([reg, "<native>"])})
        self.assertEqual(k["nothing"]["listed_by"], {})
        odd = self.kf[T.format("odd_names")]
        self.assertEqual((odd["listed"], odd["listed_by"]), (["data2/we\tird"], {"data2/we\tird": [T.format("odd_names")]}))
        for f, e in self.kf.items():   # one entry per listed directory, no other
            self.assertEqual(sorted(e["listed_by"]), e["listed"], f)
            self.assertEqual(sorted(e["listed_via"]), e["listed"], f)
            for d, via in e["listed_via"].items():
                self.assertTrue(set(e["listed_by"][d]) <= set(via), (f, d))
        # the same directory by the registry-like file in one kill file and by the kill file itself in another
        self.assertNotEqual(k["registry"]["listed_by"]["data/sub"], k["lists"]["listed_by"]["data/sub"])

    def test_a_kill_files_own_path_is_among_what_it_opened_and_every_row_has_its_outcome(self):
        self.assertEqual(sorted(self.kf), PASSING)
        for f, e in self.kf.items():
            with self.subTest(f):
                self.assertIn(f, e["opened"])
                self.assertEqual(e["outcome"], "PASS")
                self.assertIsInstance(e["seconds"], float)
                self.assertEqual((e["opened"], e["listed"]), (sorted(set(e["opened"])), sorted(set(e["listed"]))))

    # -- the child channel, with its controls ------------------------------------------------------------------------

    def test_a_child_that_inherits_the_hook_is_seen(self):
        e = self.kf[T.format("child")]
        self.assertIn("data/a.txt", e["opened"])
        self.assertEqual(e["children"], {"started": 1, "python": 1, "python_unhooked": 0, "other": 0, "hooked": 1,
                                         "unobserved": 0})

    def test_a_child_with_its_own_environment_is_not_seen_and_is_counted(self):
        for name, read in (("child_env", "data/c.txt"), ("child_isolated", "data/c.txt"),
                           ("child_pythonpath", "data/c.txt")):
            with self.subTest(name):
                e = self.kf[T.format(name)]
                self.assertNotIn(read, e["opened"])
                self.assertEqual(e["children"], {"started": 1, "python": 1, "python_unhooked": 1, "other": 0,
                                                 "hooked": 0, "unobserved": 1})

    def test_a_child_that_is_not_python_is_counted_as_unobserved(self):
        e = self.kf[T.format("child_other")]
        self.assertNotIn("data/a.txt", e["opened"])
        self.assertEqual(e["children"], {"started": 1, "python": 0, "python_unhooked": 0, "other": 1, "hooked": 0,
                                         "unobserved": 1})

    def test_the_launch_events_and_the_hooked_processes_agree(self):
        """What the launch says will load the hook is what did: python - python_unhooked == hooked, per kill file."""
        for f, e in self.kf.items():
            k = e["children"]
            with self.subTest(f):
                self.assertEqual(k["python"] - k["python_unhooked"], k["hooked"])
                self.assertEqual(k["started"], k["python"] + k["other"])

    def test_the_limits_name_the_kill_files_whose_children_are_unobserved(self):
        m = self.doc["limits"]["measured_children"]
        self.assertEqual(m["kill_files_with_unobserved_children"],
                         [T.format(n) for n in ("child_env", "child_isolated", "child_other", "child_pythonpath")])
        self.assertEqual((m["started"], m["python"], m["python_unhooked"], m["other"], m["hooked"]), (7, 6, 3, 1, 3))
        self.assertTrue(self.doc["limits"]["text"])

    def test_control_with_the_child_hook_off_the_childs_read_is_missing(self):
        on = self.kf[T.format("child")]
        off = self.control(("no-children",), [T.format("child")])[T.format("child")]
        self.assertIn("data/a.txt", on["opened"])
        self.assertNotIn("data/a.txt", off["opened"])
        self.assertEqual((off["children"]["hooked"], off["children"]["python_unhooked"]), (0, 1))

    def test_control_with_the_stat_wrapper_off_a_lookup_is_missing(self):
        f = T.format("stats")
        self.assertIn("data/c.txt", self.kf[f]["opened"])
        self.assertNotIn("data/c.txt", self.control(("no-stat",), [f])[f]["opened"])

    def test_control_the_interpreters_own_walk_is_left_out_and_shown_when_recorded(self):
        f = T.format("nothing")
        walk = self.control(("own-walk",), [f])[f]
        self.assertEqual(self.kf[f]["listed"], [])
        self.assertTrue({".", "tests", "tests/v2"} <= set(walk["listed"]))   # the import system's and the loader's
        siblings = {k for k in KILL if k != f}
        self.assertFalse(siblings & set(self.kf[f]["opened"]))
        self.assertTrue(siblings <= set(walk["opened"]))   # the loader's isfile of every file beside the kill file

    def test_a_lookup_relative_to_an_fd_is_not_taken_for_one_relative_to_the_cwd(self):
        f = T.format("dirfd")
        self.assertNotIn("b.txt", self.kf[f]["opened"])
        with mock.patch.object(RS, "HOOK", RS.HOOK.replace('if k.get("dir_fd") is None:', "if True:")):   # control
            self.assertIn("b.txt", self.control((), [f])[f]["opened"])

    # -- failing kill files, the consumer, residue -------------------------------------------------------------------

    def test_a_failing_kill_file_is_recorded_with_what_it_read_but_is_not_measured(self):
        f = T.format("fails")
        self.assertNotIn(f, self.kf)
        e = self.doc["not_passed"][f]
        self.assertEqual(e["outcome"], "FAIL")
        self.assertIn("data/c.txt", e["opened"])   # read before it failed
        self.assertIn(f, e["opened"])
        self.assertFalse(self.doc["complete"])
        self.assertIn("none of them is measured and none clears anything", self.doc["note"])

    def test_a_kill_file_that_does_not_open_itself_is_not_measured(self):
        f = T.format("nothing")
        real = RS.merge

        def merge(events, tree):
            got = real(events, tree)
            return {**got, "opened": [p for p in got["opened"] if p != f]}
        with mock.patch.object(RS, "merge", merge):
            doc = RS.record(self.root, [f])
        self.assertEqual(doc["kill_files"], {})
        self.assertIn("its own path is not among the files it opened", doc["not_passed"][f]["why"])

    def test_a_runner_stop_leaves_the_rest_not_measured(self):
        a, b = T.format("nothing"), T.format("opens")
        with mock.patch.object(M, "_run_file", side_effect=M._Stop("RESIDUAL_OWNERSHIP_UNKNOWN: x")):
            doc = RS.record(self.root, [a, b])
        self.assertEqual((doc["kill_files"], doc["not_passed"][a]["outcome"], doc["complete"]), ({}, "INFRA", False))
        self.assertIn("RESIDUAL_OWNERSHIP_UNKNOWN", doc["not_passed"][a]["why"])
        self.assertIn("not reached", doc["not_measured"][b])

    def test_a_kill_file_that_is_not_in_the_tree_is_not_measured(self):
        doc = RS.record(self.root, ["tests/v2/test_absent.py", T.format("nothing")])
        self.assertEqual(sorted(doc["kill_files"]), [T.format("nothing")])
        self.assertIn("not a file of the runner's tree", doc["not_measured"]["tests/v2/test_absent.py"])
        self.assertFalse(doc["complete"])

    def test_the_document_validates_against_the_delta_tools_loader(self):
        head = "a" * 40
        path = pathlib.Path(self._tmp.name) / "R.json"
        path.write_text(json.dumps({"commit": head, **self.doc}), encoding="utf-8")
        got = D._read_set(path, head)   # the function --read-set is read by; it refuses a bad path or a missing own path
        self.assertEqual(sorted(got), PASSING)   # the failing one is not "measured": it stays not measured there
        for f, (opened, listed, by) in got.items():
            self.assertEqual((sorted(opened), sorted(listed)), (self.kf[f]["opened"], self.kf[f]["listed"]))
            self.assertEqual(by, {d: frozenset(c) for d, c in self.kf[f]["listed_by"].items()})

    def test_nothing_is_written_to_the_tree_and_no_scratch_directory_or_process_is_left(self):
        from validation.v2 import cleanup_authority as ca
        self.assertEqual(self.before, self.after)
        self.assertEqual(os.listdir(self.private), [])
        self.assertEqual([p.command for p in ca.host_table().values() if str(self.private) in p.command], [])


@unittest.skipUnless(POSIX, "exercised on POSIX only (a symlinked tree)")
class Merge(unittest.TestCase):
    """The merge of one run's event files, on hand-written events (no process): spellings, escapes, outside, caches."""

    def test_paths_are_made_relative_to_the_tree_under_either_spelling_and_what_is_outside_is_dropped(self):
        with tempfile.TemporaryDirectory() as t:
            base = pathlib.Path(t)
            real = base / "real"
            real.mkdir()
            link = base / "link"
            link.symlink_to(real)
            tree = link / "tree"   # given unresolved; the process saw the resolved spelling
            (real / "tree").mkdir()
            ev = base / "ev"
            ev.mkdir()
            r = str(real / "tree")
            (ev / "10.ev").write_text("\n".join([
                "P\t10\t1", f"o\t{r}/a.txt", f"o\t{tree}/b.txt", f"l\t{r}\t{r}/reg.py\t{tree}/t/test_a.py", f"s\t{r}/d/e.txt",
                f"o\t{r}/__pycache__/a.cpython-314.pyc", f"o\t{base}/outside.txt", f"o\t{r}x/near.txt",
                f"o\t{r}/we\\\\ird\\nname", "C\tsubprocess.Popen\t1\t1", "C\tos.system\t0\t0",
                f"l\t{r}/d\t{r}/other.py",   # a second event of another file: the union is per directory
                f"l\t{r}\t{r}/other.py\t{r}/reg.py",
                f"l\t{r}/e\t{base}/outside.py\t{r}x/near.py",   # no caller of the tree: <native>
                f"l\t{r}/f",   # an event with no caller field at all: <native> too
                f"l\t{r}/g\t{r}/we\\\\ird\\tname.py", ""]), encoding="utf-8")
            (ev / "11.ev").write_text(f"P\t11\t10\nC\tsubprocess.Popen\t1\t0\nl\t{r}/d\t{r}/child.py\n",
                                      encoding="utf-8")
            got = RS.merge(ev, tree)
        self.assertEqual(got["opened"], ["a.txt", "b.txt", "d/e.txt", "we\\ird\nname"])
        self.assertEqual(got["listed"], [".", "d", "e", "f", "g"])
        self.assertEqual(got["listed_by"], {".": ["other.py", "reg.py"], "d": ["child.py", "other.py"], "e": ["<native>"],
                                            "f": ["<native>"], "g": ["we\\ird\tname.py"]})
        self.assertEqual(got["listed_via"], {".": ["other.py", "reg.py", "t/test_a.py"], "d": ["child.py", "other.py"],
                                             "e": ["<native>"], "f": ["<native>"], "g": ["we\\ird\tname.py"]})
        self.assertEqual(got["children"], {"started": 3, "python": 2, "python_unhooked": 1, "other": 1, "hooked": 1,
                                           "unobserved": 2})


@unittest.skipUnless(POSIX, "exercised on POSIX only (a hooked child process)")
class Callers(unittest.TestCase):
    """The hook's stack walk on a stack built by hand (code objects of chosen file names, called through one another):
    stdlib frames take no slot, the innermost file of the tree is `listed_by`, at most four distinct files in
    `listed_via`, innermost first, a file twice counts once."""

    CHILD = textwrap.dedent("""
        import os, sys
        tree, names = sys.argv[1], sys.argv[2:]
        fn = lambda: os.listdir(os.path.join(tree, "data"))   # <string>: not a file of the tree
        for name in reversed(names):   # outermost first; each frame is a code object of its own file name
            ns = {"nxt": fn}
            exec(compile("def f():\\n    return nxt()\\n", name.replace("@", tree), "exec"), ns)
            fn = ns["f"]
        fn()
        """)

    def run_child(self, names, env_extra=None):
        with tempfile.TemporaryDirectory() as t:
            base = pathlib.Path(t)
            tree, events, hook = base / "tree", base / "ev", base / "hook"
            for d in (tree / "data", events, hook):
                d.mkdir(parents=True)
            (hook / "sitecustomize.py").write_text(RS.hook_source(events, tree), encoding="utf-8")
            env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(hook), **(env_extra or {})}
            r = subprocess.run([sys.executable, "-c", self.CHILD, str(tree), *names], cwd=tree, env=env,
                               capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stderr), (0, ""))
            return RS.merge(events, tree)

    def test_a_stdlib_frame_takes_no_slot_and_the_innermost_file_of_the_tree_is_the_lister(self):
        mine = [f"@/pkg/{c}.py" for c in "abcdeFe"]   # outermost first: e innermost, e twice, F, d, c, b, a
        stdlib = [f"/fake/lib/python3/s{i}.py" for i in range(5)]   # inside it: five files, none of the tree
        got = self.run_child([*mine, *stdlib])
        self.assertEqual(got["listed"], ["data"])
        self.assertEqual(got["listed_by"], {"data": ["pkg/e.py"]})
        self.assertEqual(got["listed_via"], {"data": ["pkg/F.py", "pkg/c.py", "pkg/d.py", "pkg/e.py"]})   # not a, b: four

    def test_a_stack_with_no_file_of_the_tree_is_native(self):
        got = self.run_child(["/fake/lib/python3/s0.py", "/elsewhere/other.py"])
        self.assertEqual((got["listed_by"], got["listed_via"]), ({"data": ["<native>"]}, {"data": ["<native>"]}))


class Cli(unittest.TestCase):
    """main(): the HEAD check, the file arguments, the exit status and the document written to --out."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = pathlib.Path(d.name)
        self.root = build(self.dir)
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-qm", "toy")
        self.head = self.git("rev-parse", "HEAD")
        p = mock.patch.object(M, "COPY", COPY)
        p.start()
        self.addCleanup(p.stop)

    def git(self, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True, encoding="utf-8",
                              check=True, env=env).stdout.strip()

    def run_main(self, *args):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                code = RS.main(["--out", str(self.dir / "R.json"), *args], root=self.root)
            except SystemExit as e:
                code = e.code
        return code, err.getvalue()

    @unittest.skipUnless(POSIX, "exercised on POSIX only")
    def test_a_record_at_head_is_written_with_its_commit_and_exits_0(self):
        code, _ = self.run_main("--files", T.format("opens"), T.format("nothing"))
        self.assertEqual(code, 0)
        doc = json.loads((self.dir / "R.json").read_text(encoding="utf-8"))
        self.assertEqual((doc["commit"], doc["complete"]), (self.head, True))
        self.assertEqual(len(D._read_set(self.dir / "R.json", self.head)), 2)

    @unittest.skipUnless(POSIX, "exercised on POSIX only")
    def test_a_kill_file_that_fails_exits_1_and_the_loader_does_not_take_it_as_measured(self):
        code, err = self.run_main("--files", T.format("fails"), T.format("nothing"), "--commit", self.head)
        self.assertEqual(code, 1)
        self.assertIn("none clears anything", err)
        self.assertEqual(sorted(D._read_set(self.dir / "R.json", self.head)), [T.format("nothing")])

    def test_a_live_mutation_record_is_not_a_change_of_the_tree(self):
        (self.root / "data/live.json").write_text("{}", encoding="utf-8")   # a record the runner's copy leaves out
        self.git("add", "-A")
        self.git("commit", "-qm", "record")
        (self.root / "data/live.json").write_text("{\"changed\": 1}", encoding="utf-8")
        with mock.patch.object(M, "RECORDS", {"X": "data/live.json"}):
            self.assertEqual(RS.head_of(self.root, None), self.git("rev-parse", "HEAD"))
        with self.assertRaises(SystemExit):   # control: a file that is not one
            with contextlib.redirect_stderr(io.StringIO()):
                RS.head_of(self.root, None)

    def test_a_changed_tree_a_foreign_commit_and_a_bad_path_are_refused(self):
        (self.root / "data/a.txt").write_text("changed", encoding="utf-8")
        code, err = self.run_main("--files", T.format("nothing"))
        self.assertEqual(code, 2)
        self.assertIn("differs from HEAD", err)
        self.assertFalse((self.dir / "R.json").exists())
        self.git("checkout", "--", "data/a.txt")
        self.assertEqual(self.run_main("--files", T.format("nothing"), "--commit", "0" * 40)[0], 2)
        self.assertEqual(self.run_main("--files", "../x.py")[0], 2)
        self.assertEqual(self.run_main("--files", "/etc/passwd")[0], 2)
        self.assertFalse((self.dir / "R.json").exists())


class Targets(unittest.TestCase):
    def test_the_default_files_are_the_distinct_kill_files_of_the_v21_targets(self):
        files = RS.kill_files()
        self.assertEqual(files, sorted({f for ks in M.V21_TARGETS.values() for f in ks}))
        self.assertTrue(files and not set(files) & set(M.NOT_KILL_FILES))
        self.assertTrue(all((ROOT / f).is_file() for f in files))


if __name__ == "__main__":
    unittest.main()
