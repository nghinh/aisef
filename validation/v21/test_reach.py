"""validation/v21/reach.py: the watch list, the event merge, and the recorder on a toy tree (its controls).

Run by hand, from the repository root, through the wrapper:  python3 -B validation/v21/test_reach.py
It is not part of the suite (`tests/` does not import it) and is not a kill file; reach.py is outside mutation.COPY."""

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

from validation.v21 import reach as R  # noqa: E402

POSIX = os.name == "posix"
MONITORING = hasattr(sys, "monitoring")

RICH = '''
"""doc"""
from __future__ import annotations
import functools


def plain(a, b=1):
    def inner(x):
        return x
    return inner(a) + b


async def aplain():
    return 1


def deco(f):
    @functools.wraps(f)
    def wrapper(*a):
        return f(*a)
    return wrapper


@deco
def decorated():
    return 1


class C:
    x = 1

    def method(self):
        return 1

    def __private(self):
        return 2

    @property
    def p(self):
        return 3

    @p.setter
    def p(self, v):
        pass

    @staticmethod
    def static():
        return 4

    class Inner:
        def deep(self):
            return 5


def maker():
    class Local:
        def m(self):
            return 6
    def helper():
        return 7
    return Local, helper


def gen():
    yield 1


if __name__:   # not constant: the compiler keeps both branches
    def in_if():
        return 1
else:
    def in_else():
        return 2

try:
    def in_try():
        return 1
except Exception:
    def in_except():
        return 2

for _ in range(1):
    def in_for():
        return 1

with open("x") as _f:
    def in_with():
        return 1

match 1:
    case 1:
        def in_match():
            return 1

lam = lambda: 1
total = sum(i for i in range(3))
'''


def edit(src: str, old: str, new: str) -> str:
    assert src.count(old) == 1, (old, src.count(old))
    return src.replace(old, new)


def interpreter_names(src: str) -> set[str]:
    """The `co_qualname` of every function code object of `src` as the interpreter compiles it (lambdas, genexprs,
    class bodies and the module are not defs)."""
    out: set[str] = set()

    def walk(code):
        for c in code.co_consts:
            if hasattr(c, "co_qualname"):
                if not c.co_name.startswith("<") and c.co_flags & 0x2:   # CO_NEWLOCALS: a function, not a class body
                    out.add(c.co_qualname)
                walk(c)
    walk(compile(src, "x.py", "exec"))
    return out


class Walker(unittest.TestCase):
    def test_the_qualified_names_are_the_interpreters(self):
        funcs, _ = R.functions(RICH)
        self.assertEqual(set(funcs), interpreter_names(RICH))
        for q in ("plain.<locals>.inner", "C.method", "C.__private", "C.p",
                  "C.Inner.deep", "maker.<locals>.Local.m", "maker.<locals>.helper", "deco.<locals>.wrapper", "in_match"):
            self.assertIn(q, funcs)

    def test_a_name_defined_twice_is_one_entry_that_holds_both(self):
        funcs, _ = R.functions(RICH)
        self.assertEqual(len(funcs["C.p"]), 2)

    def test_comments_and_layout_are_not_changes(self):
        c = R.changed(RICH, RICH.replace("return 1", "return 1  # a comment").replace("\n\n\n", "\n\n\n\n"))
        self.assertEqual((c["names"], c["module"], c["removed"]), ({}, "unchanged", []))

    def test_a_body_change_flags_that_function_and_no_other(self):
        c = R.changed(RICH, edit(RICH, "return 4", "return 44"))
        self.assertEqual(c["names"], {"C.static": "changed"})
        self.assertEqual(c["module"], "unchanged")

    def test_a_nested_defs_change_is_the_nested_defs_alone(self):
        c = R.changed(RICH, edit(RICH, "def inner(x):\n        return x", "def inner(x):\n        return x + 1"))
        self.assertEqual(c["names"], {"plain.<locals>.inner": "changed"})   # `plain` runs the same statements

    def test_the_enclosing_functions_own_statement_is_its_own_change(self):
        c = R.changed(RICH, edit(RICH, "return inner(a) + b", "return inner(a) - b"))
        self.assertEqual(c["names"], {"plain": "changed"})

    def test_a_default_or_a_decorator_belongs_to_the_function_that_has_it(self):
        c = R.changed(RICH, edit(RICH, "def plain(a, b=1):", "def plain(a, b=2):"))
        self.assertEqual(c["names"], {"plain": "changed"})
        c = R.changed(RICH, edit(RICH, "    @staticmethod\n    def static():", "    def static():"))
        self.assertEqual(c["names"], {"C.static": "changed"})

    def test_a_decorator_of_a_nested_def_is_evaluated_by_the_enclosing_function(self):
        c = R.changed(RICH, edit(RICH, "    @functools.wraps(f)\n    def wrapper", "    @functools.lru_cache\n    def wrapper"))
        self.assertEqual(c["names"], {"deco": "changed", "deco.<locals>.wrapper": "changed"})

    def test_a_new_function_is_new_and_a_removed_one_is_listed_not_watched(self):
        c = R.changed(RICH, RICH + "\n\ndef added():\n    return 1\n")
        self.assertEqual((c["names"], c["module"]), ({"added": "new"}, "unchanged"))   # a def alone is no module statement
        c = R.changed(RICH + "\n\ndef added():\n    return 1\n", RICH)
        self.assertEqual((c["names"], c["removed"]), ({}, ["added"]))

    def test_a_docstring_alone_is_its_own_kind(self):
        c = R.changed(RICH, edit(RICH, "def aplain():\n", 'def aplain():\n    """now documented"""\n'))
        self.assertEqual(c["names"], {"aplain": "docstring"})
        c = R.changed(RICH, edit(RICH, '"""doc"""', '"""other doc"""'))
        self.assertEqual((c["names"], c["module"]), ({}, "docstring"))

    def test_module_statements_are_not_functions(self):
        for old, new in (("lam = lambda: 1", "lam = lambda: 2"), ("import functools", "import functools\nimport os"),
                         ("    x = 1\n", "    x = 2\n"), ("class C:", "class C(dict):"), ("total = sum(i for i in range(3))",
                                                                                      "total = sum(i for i in range(4))")):
            with self.subTest(new):
                c = R.changed(RICH, edit(RICH, old, new))
                self.assertEqual((c["names"], c["module"]), ({}, "changed"))

    def test_an_annotation_is_evaluated_at_the_def_only_without_the_future_import(self):
        deferred = "from __future__ import annotations\n\n\ndef f(x: int):\n    return x\n"
        eager = "\n\ndef f(x: int):\n    return x\n"
        for src in (deferred, eager):
            c = R.changed(src, src.replace("x: int", "x: str"))
            self.assertEqual(c["names"], {"f": "changed"})   # f's own signature differs either way
        mod = R.changed(deferred + "class K:\n    def g(self, y: int): pass\n",
                        deferred + "class K:\n    def g(self, y: str): pass\n")
        self.assertEqual(mod["module"], "unchanged")   # not evaluated where the def stands
        mod = R.changed(eager + "class K:\n    def g(self, y: int): pass\n", eager + "class K:\n    def g(self, y: str): pass\n")
        self.assertEqual(mod["module"], "changed")

    def test_the_module_statements_that_differ_are_named_by_kind_and_line(self):
        c = R.changed(RICH, edit(RICH, "import functools", "import functools\nimport os"))
        self.assertEqual([(m["kind"], m["text"]) for m in c["module_statements"]], [("Import", "import os")])
        c = R.changed(RICH, edit(RICH, '"""doc"""', '"""other doc"""'))
        self.assertEqual([m["kind"] for m in c["module_statements"]], ["docstring"])
        c = R.changed(RICH, edit(RICH, "    x = 1\n", "    x = 2\n"))
        self.assertEqual([(m["kind"], m["text"]) for m in c["module_statements"]], [("ClassDef", "class C:")])
        c = R.changed(RICH, RICH + "\n\ndef added():\n    return 1\n")
        self.assertEqual(c["module_statements"], [])   # a def with nothing to evaluate is no statement
        c = R.changed(RICH, RICH + "\n\nclass Added(Exception):\n    pass\n\n\nLIMIT = 3\n")
        self.assertEqual([m["text"] for m in c["module_statements"]], ["class Added(Exception):", "LIMIT = 3"])

    def test_a_new_file_is_all_new(self):
        c = R.changed(None, RICH)
        self.assertEqual(c["module"], "new")
        self.assertEqual(set(c["names"]), interpreter_names(RICH))
        self.assertEqual(set(c["names"].values()), {"new"})


def git(cwd: pathlib.Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args], capture_output=True,
                       text=True, check=True)
    return r.stdout.strip()


class FromGit(unittest.TestCase):
    def test_the_watch_list_of_a_diff(self):
        with tempfile.TemporaryDirectory() as t:
            repo = pathlib.Path(t)
            files = {"aisef2/__init__.py": "", "aisef2/a.py": "def f():\n    return 1\n\n\ndef g():\n    return 2\n",
                     "aisef2/gone.py": "def h():\n    return 1\n", "aisef2/same.py": "def k():\n    return 1\n",
                     "validation/v2/cleanup_authority.py": "def c():\n    return 1\n",
                     "validation/v2/other.py": "def o():\n    return 1\n", "aisef2/data.json": "{}\n"}
            for rel, text in files.items():
                (repo / rel).parent.mkdir(parents=True, exist_ok=True)
                (repo / rel).write_text(text, encoding="utf-8")
            git(repo, "init", "-q")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "base")
            base = git(repo, "rev-parse", "HEAD")
            (repo / "aisef2/a.py").write_text("def f():\n    return 11\n\n\ndef g():\n    return 2\n", encoding="utf-8")
            (repo / "aisef2/new.py").write_text("X = 1\n\n\ndef n():\n    return 1\n", encoding="utf-8")
            (repo / "aisef2/same.py").write_text("def k():\n    return 1  # only a comment\n", encoding="utf-8")
            (repo / "validation/v2/cleanup_authority.py").write_text("def c():\n    return 2\n", encoding="utf-8")
            (repo / "validation/v2/other.py").write_text("def o():\n    return 2\n", encoding="utf-8")
            (repo / "aisef2/data.json").write_text('{"a": 1}\n', encoding="utf-8")
            (repo / "aisef2/gone.py").unlink()
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "head")
            head = git(repo, "rev-parse", "HEAD")
            watch, modules, diff = R.watch_from_diff(repo, base, head)
        self.assertEqual(watch, {"aisef2/a.py": ["f"], "aisef2/new.py": ["n"], "validation/v2/cleanup_authority.py": ["c"]})
        self.assertEqual(modules, {"aisef2/a.py": "unchanged", "aisef2/new.py": "new",
                                   "validation/v2/cleanup_authority.py": "unchanged"})
        self.assertEqual(diff["deleted_files"], ["aisef2/gone.py"])
        self.assertEqual(diff["files"]["aisef2/same.py"]["names"], {})   # a comment: not watched
        self.assertNotIn("aisef2/same.py", watch)
        self.assertEqual(diff["outside_scope"], ["aisef2/data.json", "validation/v2/other.py"])   # named, never dropped

    def test_a_hand_list(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "w.json"
            p.write_text(json.dumps({"watch": {"aisef2/x.py": ["B", "A", "<module>"]}}), encoding="utf-8")
            self.assertEqual(R.watch_from_file(p), {"aisef2/x.py": ["A", "B"]})
            p.write_text(json.dumps({"../x.py": ["A"]}), encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as e:
                R.watch_from_file(p)
            self.assertEqual(e.exception.code, 2)


class Merge(unittest.TestCase):
    def merged(self, files: dict[str, str]) -> dict:
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            for name, text in files.items():
                (d / name).write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
            return R.merge(d)

    def test_the_earliest_process_is_the_test_process_and_children_are_told_apart(self):
        got = self.merged({
            "10-200.rch": "P\t10\t1\t200\tpython -m unittest discover\nH\ta.py\tf\nH\ta.py\t<module>\nL\tsubprocess.Popen\t1\t1\t\n",
            "11-300.rch": "P\t11\t10\t300\tpython -c <code>\nH\ta.py\tg\nH\ta.py\tf\n",
            "12-310.rch": "P\t12\t10\t310\tgit status\n",
        })
        self.assertEqual(got["executed"], [["a.py", "f"], ["a.py", "g"]])
        self.assertEqual(got["executed_in_children"], [["a.py", "f"], ["a.py", "g"]])
        self.assertEqual(got["loaded"], ["a.py"])
        self.assertEqual((got["processes"], got["children"]), (3, {"hooked": 2, "unhooked_python": 0, "other": 0}))

    def test_a_function_only_the_test_process_ran_is_not_a_childs(self):
        got = self.merged({"1-5.rch": "P\t1\t0\t5\tpython\nH\ta.py\tf\n", "2-9.rch": "P\t2\t1\t9\tpython\n"})
        self.assertEqual((got["executed"], got["executed_in_children"]), ([["a.py", "f"]], []))

    def test_launches_are_counted_by_what_the_launch_says(self):
        got = self.merged({"1-5.rch": "P\t1\t0\t5\tpython\nL\tsubprocess.Popen\t1\t0\tpython -I -B -c <code>\n"
                                      "L\tos.system\t0\t0\t\nL\tsubprocess.Popen\t1\t1\t\n"
                                      "L\tsubprocess.Popen\t1\t0\tpython -I -B -c <code>\n"})
        self.assertEqual(got["children"], {"hooked": 0, "unhooked_python": 2, "other": 1})
        self.assertEqual(got["unhooked_python_argv"], {"python -I -B -c <code>": 2})

    def test_a_copy_of_the_tree_is_executed_and_another_version_is_named_apart(self):
        got = self.merged({"1-5.rch": "P\t1\t0\t5\tpython\nH\ta.py\tf\nC\ta.py\tg\nC\ta.py\tf\nX\ta.py\th\nX\ta.py\t<module>\n"})
        self.assertEqual(got["executed"], [["a.py", "f"], ["a.py", "g"]])   # g: only through a copy of the same bytes
        self.assertEqual(got["executed_from_copy_only"], [["a.py", "g"]])
        self.assertEqual(got["other_version"], [["a.py", "h"]])   # not executed: it is not the code measured
        self.assertEqual(got["loaded"], [])

    def test_a_line_that_is_not_one_is_counted_not_trusted(self):
        got = self.merged({"1-5.rch": "P\t1\t0\t5\tpython\nH\tonly-one-field\nnonsense\nH\ta.py\tf\n"})
        self.assertEqual((got["executed"], got["unparsed_lines"]), ([["a.py", "f"]], 2))

    def test_a_pid_counted_twice_is_one_process(self):   # a preexec_fn child registers, then execs
        got = self.merged({"1-5.rch": "P\t1\t0\t5\tpython\n", "1-8.rch": "P\t1\t0\t8\tpython\n"})
        self.assertEqual(got["processes"], 1)


@unittest.skipUnless(POSIX and MONITORING, "the hook is sys.monitoring (3.12+); the controls fork and kill a child")
class Recorder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = R.run_controls()

    def test_every_control_is_as_expected(self):
        for k, v in self.res["controls"].items():
            with self.subTest(k):
                self.assertTrue(v["ok"], v)
        self.assertEqual(sorted(self.res["controls"]), sorted(R.CONTROLS))

    def test_the_controls_state_what_they_expect(self):   # a control with no expectation proves nothing
        c = self.res["controls"]
        self.assertEqual(c["b"]["expected"], [[], ["aisef2/toy.py"]])
        self.assertEqual(c["d"]["expected"], [[], [0, 1]])
        self.assertEqual(c["g"]["expected"], [["PASS", "PASS"], ["FAIL", "FAIL"]])

    def test_a_kill_file_that_fails_is_recorded_but_not_measured(self):
        c = R.changed(R._TOY_BASE, R._TOY)
        with tempfile.TemporaryDirectory() as t:
            root = R._toy_tree(pathlib.Path(t))
            doc = R.record(root, [R._F, R._T.format("a")], {R._TOY_FILE: sorted(c["names"])}, {R._TOY_FILE: c["module"]})
        self.assertNotIn(R._F, doc["kill_files"])
        self.assertEqual(doc["not_passed"][R._F]["outcome"], "FAIL")
        self.assertIn(R._T.format("a"), doc["kill_files"])
        self.assertFalse(doc["complete"])
        self.assertIn("none of them is under kill_files", doc["note"])

    def test_a_pass_whose_own_import_was_not_seen_is_not_measured(self):
        c = R.changed(R._TOY_BASE, R._TOY)
        with tempfile.TemporaryDirectory() as t:
            root = R._toy_tree(pathlib.Path(t))
            with mock.patch.object(R, "HOOK", "pass\n"):   # a hook that records nothing
                doc = R.record(root, [R._T.format("a")], {R._TOY_FILE: sorted(c["names"])})
        self.assertEqual(doc["kill_files"], {})
        self.assertEqual(doc["not_passed"][R._T.format("a")]["outcome"], "PASS")
        self.assertIn("nothing measured", doc["not_passed"][R._T.format("a")]["why"])

    def test_an_unhooked_child_is_shown_by_what_it_was_started_as(self):
        c = R.changed(R._TOY_BASE, R._TOY)
        with tempfile.TemporaryDirectory() as t:
            root = R._toy_tree(pathlib.Path(t))
            doc = R.record(root, [R._T.format("d")], {R._TOY_FILE: sorted(c["names"])}, {R._TOY_FILE: c["module"]})
        e = doc["kill_files"][R._T.format("d")]
        self.assertEqual((e["executed"], e["children"]["unhooked_python"]), ([], 1))
        (words, n), = e["unhooked_python_argv"].items()
        self.assertEqual(n, 1)
        self.assertTrue(words.endswith("-c <code>"), words)   # the payload of -c is not copied

    def test_the_plain_mode_runs_the_same_files_with_no_hook(self):
        c = R.changed(R._TOY_BASE, R._TOY)
        with tempfile.TemporaryDirectory() as t:
            root = R._toy_tree(pathlib.Path(t))
            doc = R.record(root, [R._T.format("a")], {R._TOY_FILE: sorted(c["names"])}, hooked=False)
        self.assertEqual(doc["mode"], "plain")
        self.assertEqual(sorted(doc["kill_files"][R._T.format("a")]), ["outcome", "seconds"])

    def test_the_hook_is_not_loaded_into_the_runner_and_its_text_has_no_placeholder(self):
        text = R.hook_source(pathlib.Path("/ev"), pathlib.Path("/tree"), {"aisef2/x.py": ["f"]})
        self.assertNotIn("@", text)
        compile(text, "sitecustomize.py", "exec")
        self.assertNotIn("aisef-reach", sys.modules)
        self.assertIn("'<module>'", text)

    def test_main_end_to_end_on_a_toy_repository(self):
        """git diff -> watch list -> the runner's own _run_file -> merge -> the document, through main()."""
        v1 = "def f():\n    return 1\n\n\ndef g():\n    return 2\n"
        files = {"aisef2/__init__.py": "", "aisef2/toy.py": v1, "tests/v2/__init__.py": "",
                 "tests/v2/test_calls_f.py": "import unittest\nfrom aisef2 import toy\n\n\nclass K(unittest.TestCase):\n"
                                             "    def test(self):\n        self.assertEqual(toy.f(), 11)\n",
                 "tests/v2/test_calls_g.py": "import unittest\nfrom aisef2 import toy\n\n\nclass K(unittest.TestCase):\n"
                                             "    def test(self):\n        self.assertEqual(toy.g(), 2)\n",
                 "tests/v2/test_imports.py": "import unittest\nfrom aisef2 import toy\n\n\nclass K(unittest.TestCase):\n"
                                             "    def test(self):\n        self.assertTrue(toy)\n"}
        with tempfile.TemporaryDirectory() as t:
            repo = pathlib.Path(t) / "repo"
            for rel, text in files.items():
                (repo / rel).parent.mkdir(parents=True, exist_ok=True)
                (repo / rel).write_text(text, encoding="utf-8")
            git(repo, "init", "-q")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "base")
            base = git(repo, "rev-parse", "HEAD")
            (repo / "aisef2/toy.py").write_text(v1.replace("return 1", "return 11"), encoding="utf-8")
            git(repo, "commit", "-q", "-a", "-m", "head")
            out = pathlib.Path(t) / "R.json"
            with contextlib.redirect_stderr(io.StringIO()):
                code = R.main(["--base", base, "--out", str(out), "--files", "tests/v2/test_calls_f.py",
                               "tests/v2/test_calls_g.py", "tests/v2/test_imports.py"], root=repo)
            doc = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual((doc["watch"], doc["watch_size"], doc["modules"]), ({"aisef2/toy.py": ["f"]}, 1,
                                                                            {"aisef2/toy.py": "unchanged"}))
        self.assertEqual((doc["base"], doc["head"] == doc["commit"], doc["complete"]), (base, True, True))
        kf = doc["kill_files"]
        self.assertEqual(kf["tests/v2/test_calls_f.py"]["executed"], [["aisef2/toy.py", "f"]])
        self.assertEqual(kf["tests/v2/test_calls_g.py"]["executed"], [])   # imports the changed file, runs another function
        self.assertEqual(kf["tests/v2/test_imports.py"]["executed"], [])
        for v in kf.values():
            self.assertEqual((v["loaded"], v["module_statements_executed"], v["outcome"]), (["aisef2/toy.py"], [], "PASS"))
        self.assertTrue(doc["limits"])

    def test_main_refuses_without_a_watch_source(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as e:
            R.main(["--out", "/nonexistent/out.json"])
        self.assertEqual(e.exception.code, 2)


@unittest.skipUnless(POSIX and MONITORING, "the hook is sys.monitoring (3.12+); the launches are real processes")
class Launches(unittest.TestCase):
    """One child process is one launch (V2.1 fix window, owner decision of 2026-10-15, item 6; the same test as
    tests/v2/test_v21_read_set.py::Launches, for this tool's own copy of the hook). subprocess.Popen raises its own
    event and may make an os.posix_spawn of its own (Linux with glibc's POSIX_SPAWN_CLOSEFROM; macOS with
    close_fds=False): the same child. The traced code reports the pid of every process it really started and the record
    must hold one launch per pid; a direct os.posix_spawn is a launch of its own."""

    CHILD = textwrap.dedent("""
        import json, os, subprocess, sys
        sh, started, via = "/bin/sh", [], []
        def spy(event, a):
            if event == "os.posix_spawn":
                via.append(sys._getframe(1).f_code.co_name)   # the function that called os.posix_spawn
        sys.addaudithook(spy)
        for kw in ({}, {"close_fds": False}):   # posix_spawn on Linux / fork_exec on macOS; posix_spawn on both
            p = subprocess.Popen([sh, "-c", "true"], **kw)
            p.wait()
            started.append([p.pid, False])
        p = subprocess.Popen([sys.executable, "-I", "-c", "pass"], close_fds=False)   # Python that will not load the hook
        p.wait()
        started.append([p.pid, True])
        pid = os.posix_spawn(sh, [sh, "-c", "true"], os.environ)   # the traced code's own, no Popen behind it
        os.waitpid(pid, 0)
        started.append([pid, False])
        print(json.dumps({"started": started, "via": via}))
        """)

    def test_a_popen_that_posix_spawns_is_one_launch_and_a_direct_posix_spawn_is_another(self):
        with tempfile.TemporaryDirectory() as t:
            base = pathlib.Path(t)
            tree, events, hook = base / "tree", base / "ev", base / "hook"
            for d in (tree, events, hook):
                d.mkdir()
            (hook / "sitecustomize.py").write_text(R.hook_source(events, tree, {}), encoding="utf-8")
            env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(hook)}
            r = subprocess.run([sys.executable, "-c", self.CHILD], cwd=tree, env=env, capture_output=True, text=True,
                               encoding="utf-8")
            self.assertEqual((r.returncode, r.stderr), (0, ""))
            out, got = json.loads(r.stdout), R.merge(events)
        pids = [p for p, _ in out["started"]]
        python = [p for p, py in out["started"] if py]
        self.assertEqual(len(set(pids)), 4)
        self.assertGreaterEqual(out["via"].count("_posix_spawn"), 2)   # close_fds=False twice: the path really was taken
        self.assertEqual(out["via"].count("<module>"), 1)              # and one call is the traced code's own
        self.assertEqual(got["children"], {"hooked": 0, "unhooked_python": len(python),
                                           "other": len(pids) - len(python)})


if __name__ == "__main__":
    unittest.main()
