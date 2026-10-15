"""PM-1 (B-03 round 3, docs/v2.1/decisions/B03-R3-PROBE-MODULE-FINDINGS.md §2): a module that sits below a directory
without `__init__.py` is located like any other.

The controller of `cli_invocation` and of `process_effect` (HARNESS, B1) never imports the subject. It locates the
module by walking the dotted name with the import system's path finder. For a component that is an implicit namespace
portion, a finder call that names the *dotted* path builds a `_NamespacePath`, whose constructor reads
`sys.modules[<parent>].__path__` -- a module this process deliberately never imports -- so the walk raised `KeyError`
and the probe answered UNRUNNABLE / ENVIRONMENT for a layout CPython imports without complaint. The module contracts
(docstring "Subject") say the module is located with the import system's path finder; only a module that does not
resolve, or resolves only outside the checkout, is absent.

What these tests hold, each on real controller and subject processes (no injected process range):

* the premise: CPython, with the revision first on `sys.path` as the subject's process puts it, imports every present
  layout and fails on every absent one -- the answer the probes owe is CPython's;
* the controller's own `inside` / `resolve` (the text of the HARNESS, run in a `-I -S -B` process that never imports
  the subject) give CPython's origin for every layout, depth 1 to 4, regular and namespace components mixed, root
  and `src/`;
* both probes OBSERVE a nested layout (SATISFIED) and the run is EXECUTED -- never HARNESS_FAILED / UNRUNNABLE --
  with the same answer as `python_callable_v2`, whose agent imports and which never had the defect;
* an absent module below a namespace directory is SUBJECT_ABSENT without the "outside the revision" note, a module
  that raises on import is REFUTED (so the lookup located it and the subject's own import ran), a `__main__` below a
  namespace directory runs.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict  # noqa: E402
from aisef2.probe import cli_invocation as ci  # noqa: E402
from aisef2.probe import process_effect as pe_module  # noqa: E402
from aisef2.probe.protocol import ObservationKind as K, RevisionRef, run_probe  # noqa: E402
from aisef2.product.outcome import Executed  # noqa: E402
from tests.v2 import test_c2_cli_invocation as cli  # noqa: E402  (builders only: no test class is imported)
from tests.v2 import test_probe_process_effect as pe  # noqa: E402
from tests.v2 import test_python_callable_v2 as pc2  # noqa: E402

S, R = BehaviorVerdict.SATISFIED, BehaviorVerdict.REFUTED
OUTSIDE = "outside the revision"   # the identifying element of "resolves only outside the revision"
MOD = "def f():\n    return 1\n\n\ndef main(argv):\n    return 0\n"
EXITS_0 = {"exit_code": 0}

#: label -> (files, dotted module). Every one is imported by CPython with the revision first on the path.
PRESENT = {
    "a regular package, then a namespace directory": ({"pkg/__init__.py": "", "pkg/inner/mod.py": MOD},
                                                      "pkg.inner.mod"),
    "the same under src/": ({"src/pkg/__init__.py": "", "src/pkg/inner/mod.py": MOD}, "pkg.inner.mod"),
    "two namespace directories": ({"ns/inner/mod.py": MOD}, "ns.inner.mod"),
    "four namespace directories": ({"a/b/c/d/mod.py": MOD}, "a.b.c.d.mod"),
    "regular, namespace, namespace": ({"a/__init__.py": "", "a/b/c/mod.py": MOD}, "a.b.c.mod"),
    "namespace, regular, namespace": ({"a/b/__init__.py": "", "a/b/c/mod.py": MOD}, "a.b.c.mod"),
    "a namespace spanning the root and src/": ({"ns/inner/a.py": MOD, "src/ns/inner/mod.py": MOD}, "ns.inner.mod"),
    "control: one namespace directory": ({"ns/mod.py": MOD}, "ns.mod"),
    "control: regular all the way": ({"pkg/__init__.py": "", "pkg/sub/__init__.py": "", "pkg/sub/mod.py": MOD},
                                     "pkg.sub.mod"),
}
#: label -> (files, dotted module). CPython's import of every one fails: the module is not there.
ABSENT = {
    "a namespace directory lacking the module": ({"pkg/__init__.py": "", "pkg/inner/other.py": MOD}, "pkg.inner.mod"),
    "a plain module in the way of the directory": ({"pkg/__init__.py": "", "pkg/inner.py": MOD,
                                                    "pkg/inner/mod.py": MOD}, "pkg.inner.mod"),
    "a regular package at the root hides the namespace one under src/": ({"pkg/__init__.py": "",
                                                                          "src/pkg/inner/mod.py": MOD},
                                                                         "pkg.inner.mod"),
}
#: the same names, a module of the standard library being the parent: not a package, so CPython's import fails; the
#: controller must answer (a verdict that is never SATISFIED), not fail
SHADOWED = {
    "below queue": ({"queue/inner/mod.py": MOD}, "queue.inner.mod"),
    "below types": ({"types/inner/mod.py": MOD}, "types.inner.mod"),
    "below hmac": ({"hmac/inner/mod.py": MOD}, "hmac.inner.mod"),
    "below os (a module the subject's process holds)": ({"os/inner/mod.py": MOD}, "os.inner.mod"),
    "below json (a regular package of the standard library)": ({"json/inner/mod.py": MOD}, "json.inner.mod"),
    "below email (a regular package of the standard library)": ({"email/inner/mod.py": MOD}, "email.inner.mod"),
    "a namespace directory named like a standard-library package": ({"json/mod.py": MOD}, "json.mod"),
}

#: what the subject's process does: the revision first on `sys.path` (cli_invocation.AGENT), then the import
IMPORTS = ("import os, sys, importlib.util\n"
           "root = os.path.realpath(sys.argv[1])\n"
           "sys.path[:0] = [p for p in (root, os.path.join(root, 'src')) if os.path.isdir(p)]\n"
           "try:\n    spec = importlib.util.find_spec(sys.argv[2])\n"
           "except (ImportError, ValueError):\n    spec = None\n"
           "print(repr(None if spec is None or spec.origin is None\n"
           "           else os.path.relpath(os.path.realpath(spec.origin), root)))\n")
#: the controller's own two functions, as the HARNESS text carries them, in a process like the controller's
LOOKUP = ("import os, sys\n"
          "from importlib.machinery import PathFinder\n"
          "root = os.path.realpath(sys.argv[1])\n"
          "SEARCH = [p for p in (root, os.path.join(root, 'src')) if os.path.isdir(p)]\n"
          "%s\n"
          "spec = resolve(sys.argv[2], SEARCH)\n"
          "print(repr(None if spec is None or not inside(spec) or spec.origin is None "
          "else os.path.relpath(os.path.realpath(spec.origin), root)))\n")


def lookup_source(harness: str) -> str:
    """`inside` and `resolve` of a HARNESS text (adjacent top-level functions: the next `def` ends `resolve`)."""
    a, b = harness.index("def inside(spec):"), harness.index("def resolve(dotted, search):")
    return harness[a:harness.index("\ndef ", b + 1) + 1]


def run_python(code: str, *argv: str) -> str:
    done = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code, *argv], stdin=subprocess.DEVNULL,
                          capture_output=True, encoding="utf-8", check=False, timeout=60)
    return done.stdout.strip() if done.returncode == 0 else f"rc={done.returncode} {done.stderr.strip()[-200:]}"


class _Layouts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory(prefix="aisef2-pm1-", ignore_cleanup_errors=True)
        cls.addClassCleanup(tmp.cleanup)
        cls.tmp, cls.at = tmp.name, {}
        for group in (PRESENT, ABSENT, SHADOWED):
            for label, (files, _) in group.items():
                cls.at[label] = cls.checkout(label, files)

    @classmethod
    def checkout(cls, label, files):
        return os.path.realpath(pe.checkout(os.path.join(cls.tmp, str(len(os.listdir(cls.tmp)))), files))


class ThePremise(_Layouts):
    def test_cpython_locates_every_present_layout_and_none_of_the_absent_ones(self):
        for label, (_, dotted) in PRESENT.items():
            with self.subTest(layout=label):
                got = run_python(IMPORTS, self.at[label], dotted)
                self.assertTrue(got.endswith("mod.py'"), got)
        for label, (_, dotted) in ABSENT.items():
            with self.subTest(layout=label):
                self.assertEqual(run_python(IMPORTS, self.at[label], dotted), "None")


class TheControllersOwnLookup(_Layouts):
    """`resolve` + `inside` of both HARNESS scripts answer what CPython answers, in a process that holds neither the
    revision on its path nor the parent module in `sys.modules`.

    Pins HARNESS/resolve (cli_invocation, process_effect)."""

    def test_every_layout_is_located_where_cpython_locates_it(self):
        for harness_of in (ci, pe_module):
            code = LOOKUP % lookup_source(harness_of.HARNESS)
            for group in (PRESENT, ABSENT):
                for label, (_, dotted) in group.items():
                    with self.subTest(probe=harness_of.PROBE_ID, layout=label):
                        want = run_python(IMPORTS, self.at[label], dotted)
                        self.assertEqual(run_python(code, self.at[label], dotted), want)

    def test_a_namespace_directory_below_a_module_the_process_holds_is_located_not_a_failure(self):
        """`queue`, `types`, `hmac` and `os` are in `sys.modules` of the controller already, without a `__path__` (the
        verifier's residual of PM-1: `AttributeError`): the lookup answers with the file of the revision it finds. It
        never imports anything, so whether the module can be imported is the subject's process's answer, not its."""
        for harness_of in (ci, pe_module):
            code = LOOKUP % lookup_source(harness_of.HARNESS)
            for label, (_, dotted) in SHADOWED.items():
                with self.subTest(probe=harness_of.PROBE_ID, layout=label):
                    got = run_python(code, self.at[label], dotted)
                    self.assertTrue(got.endswith("mod.py'"), got)


class TheProbes(_Layouts):
    def effect(self, label, dotted, attr="f", observable=None):
        s = pe.spec(f"{dotted}:{attr}", [pe.call(None)], observable or {"returns": 1})
        at = RevisionRef(pe.SHA, self.at[label])
        return pe.P.observe(s, at, pe.env()), lambda: run_probe(pe.P, s, at, pe.env()).result

    def cli(self, label, locator, observable=None):
        s = cli.spec(locator, observable or EXITS_0)
        at = RevisionRef(cli.SHA, self.at[label])
        return cli.P.observe(s, at, cli.env()), lambda: run_probe(cli.P, s, at, cli.env()).result

    def test_a_present_layout_is_observed_by_both_probes_and_the_run_executes(self):
        for label, (_, dotted) in PRESENT.items():
            with self.subTest(layout=label, probe="process_effect"):
                o, run = self.effect(label, dotted)
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
                self.assertEqual(run(), Executed(S))
            with self.subTest(layout=label, probe="cli_invocation"):
                o, run = self.cli(label, f"{dotted}:main")
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)
                self.assertEqual(run(), Executed(S))

    def test_python_callable_v2_whose_agent_imports_gives_the_same_answer(self):
        for label, (_, dotted) in PRESENT.items():
            with self.subTest(layout=label):
                s = pc2.spec(f"{dotted}:f", {"returns": 1}, {})
                o = pc2.P.observe(s, RevisionRef(pc2.SHA, self.at[label]), pc2.env())
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)

    def test_an_absent_module_is_absent_without_the_outside_note(self):
        for label, (_, dotted) in ABSENT.items():
            for name, (o, _run) in (("process_effect", self.effect(label, dotted)),
                                    ("cli_invocation", self.cli(label, f"{dotted}:main"))):
                with self.subTest(layout=label, probe=name):
                    self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, R), o.detail)
                    self.assertNotIn(OUTSIDE, o.detail)

    def test_a_name_the_module_does_not_define_is_absent_not_a_harness_failure(self):
        files = {"pkg/__init__.py": "", "pkg/inner/mod.py": "X = 1\n"}
        self.at["no f"] = self.checkout("no f", files)
        o, _run = self.effect("no f", "pkg.inner.mod")
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, R), o.detail)
        self.assertIn("does not define f", o.detail)

    def test_a_module_below_a_namespace_directory_that_raises_on_import_is_refuted_by_its_own_import(self):
        files = {"pkg/__init__.py": "",
                 "pkg/inner/mod.py": "import no_such_dependency_xyz\n\n\ndef f():\n    return 1\n"}
        self.at["raises"] = self.checkout("raises", files)
        o, _run = self.effect("raises", "pkg.inner.mod")
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
        self.assertIn("importing the subject raised ModuleNotFoundError", json.loads(o.detail)["refuted"]["why"])
        o, _run = self.cli("raises", "pkg.inner.mod:f")
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
        self.assertEqual(json.loads(o.detail)["raised"], "ModuleNotFoundError")

    def test_a_layout_whose_import_fails_under_cpython_is_the_subjects_own_failure_never_an_environment_one(self):
        """CPython's import of every `SHADOWED` name fails (the standard library's module or package wins). The
        controller locates the file of the revision, the subject's process imports it and raises: a present subject that
        does not work -- OBSERVED, REFUTED, by the subject's own import -- exactly as `json/mod.py` always was."""
        for label, (_, dotted) in SHADOWED.items():
            with self.subTest(layout=label, probe="process_effect"):
                o, run = self.effect(label, dotted)
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
                self.assertEqual(json.loads(o.detail)["refuted"]["why"],
                                 "importing the subject raised ModuleNotFoundError")
                self.assertEqual(run(), Executed(R))
            with self.subTest(layout=label, probe="cli_invocation"):
                o, run = self.cli(label, f"{dotted}:main")
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
                self.assertEqual((json.loads(o.detail)["raised"], json.loads(o.detail)["exit_code"]),
                                 ("ModuleNotFoundError", 1))
                self.assertEqual(run(), Executed(R))

    def test_a_module_only_the_standard_library_has_is_outside_the_revision(self):
        for dotted in ("textwrap", "xml.dom.minidom"):
            self.at[dotted] = self.checkout(dotted, {"README.md": "nothing of the product here\n"})
            for name, (o, _run) in (("process_effect", self.effect(dotted, dotted)),
                                    ("cli_invocation", self.cli(dotted, f"{dotted}:main"))):
                with self.subTest(module=dotted, probe=name):
                    self.assertEqual((o.kind, o.verdict, o.detail), (K.SUBJECT_ABSENT, R, "resolves only outside the "
                                                                                          "revision"))


class TheMainOfANamespaceDirectory(unittest.TestCase):
    """`<module>:__main__` of cli_invocation: a package is run through its `__main__` submodule, looked up by the same
    finder under the same rule. Pins HARNESS/main (cli_invocation) at the `__main__` lookup."""

    MAIN = "import sys\nsys.exit(0)\n"

    def see(self, name, files, locator):
        root = pe.checkout(os.path.join(self.tmp.name, name), files)
        s = cli.spec(locator, EXITS_0)
        return cli.P.observe(s, RevisionRef(cli.SHA, root), cli.env())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aisef2-pm1-main-", ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)

    def test_a_main_below_namespace_directories_runs(self):
        for name, files, locator in (("two", {"a/b/__main__.py": self.MAIN}, "a.b:__main__"),
                                     ("three", {"a/b/c/__main__.py": self.MAIN}, "a.b.c:__main__"),
                                     ("regular_above", {"pkg/__init__.py": "", "pkg/sub/__main__.py": self.MAIN},
                                      "pkg.sub:__main__")):
            with self.subTest(layout=name):
                o = self.see(name, files, locator)
                self.assertEqual((o.kind, o.verdict), (K.OBSERVED, S), o.detail)

    def test_a_namespace_package_without_a_main_is_absent(self):
        o = self.see("nomain", {"a/b/x.py": self.MAIN}, "a.b:__main__")
        self.assertEqual((o.kind, o.verdict), (K.SUBJECT_ABSENT, R), o.detail)

    def test_a_directory_named_main_is_the_subjects_own_failure_not_a_harness_failure(self):
        """CPython: `runpy` refuses a package without a `__main__` module ("cannot be directly executed" -- an
        ImportError), a directory named `__main__` being no module. That is the answer: REFUTED by the subject's own
        run (exit 1), where the lookup used to end the controller (HARNESS/main, the `__main__` lookup)."""
        o = self.see("dirmain", {"pkg/__init__.py": "", "pkg/__main__/x.py": self.MAIN}, "pkg:__main__")
        self.assertEqual((o.kind, o.verdict), (K.OBSERVED, R), o.detail)
        self.assertEqual((json.loads(o.detail)["raised"], json.loads(o.detail)["exit_code"]), ("ImportError", 1))


if __name__ == "__main__":
    unittest.main()
