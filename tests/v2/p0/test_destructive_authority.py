"""INV-MUTATION-AUTHORITY, the static half (owner authorization of 2026-09-24 §5): the destructive-call-site checker
A. discovers sites mechanically, B. fails on a site with no ledger row, C. fails on a row with no site, D. fails when a
declared authority source does not match the derivation, E. fails on an ambiguous derivation, F. fails closed on a
destructive API outside its taxonomy, G. (MUT-AUTH-NEG-3) discovers a destructive callable handed over by reference —
addCleanup, an alias registered or called, partial, ExitStack.callback — and fails it without a row, H. (MUT-AUTH-NEG-4)
fails the same registered callable once its target is no longer test-created, I. fails closed on a registration the
taxonomy does not model or a callable passed by keyword — and passes on this tree."""

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT / "validation" / "v2") not in sys.path:
    sys.path.insert(0, str(ROOT / "validation" / "v2"))
import destructive_authority as da  # noqa: E402

GOOD = ("import subprocess\nimport sys\n\n\ndef f():\n    c = subprocess.Popen([sys.executable, '-c', 'pass'])\n"
        "    c.kill()\n")
ROW = {"path": "tests/v2/t.py", "scope": "f", "callable": "c.kill", "target": "c", "target_kind": "process",
       "authority_source": "TEST_CREATED_HANDLE", "justification": "j", "enforcement": "e"}


def tree(files: dict, ledger: list | None) -> pathlib.Path:
    """A throwaway tree with the checker's scopes; `ledger=None` writes no ledger file at all."""
    t = pathlib.Path(tempfile.mkdtemp(prefix="aisef2-da-"))
    for scope in da.SCOPES:
        (t / scope).mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        (t / rel).parent.mkdir(parents=True, exist_ok=True)
        (t / rel).write_text(text, encoding="utf-8")
    if ledger is not None:
        (t / da.LEDGER_REL).write_text(json.dumps({"sites": ledger}), encoding="utf-8")
    return t


class Checker(unittest.TestCase):
    def test_this_tree_passes_and_every_site_is_ledgered(self):
        self.assertEqual(da.check(ROOT), [])
        sites, _ = da.discover(ROOT)
        self.assertGreater(len(sites), 20)
        self.assertTrue(all(r["verdict"] == "PASS" for r in da.audit(ROOT)))

    def test_A_discovery_is_mechanical_and_names_the_site(self):
        sites, problems = da.discover(tree({"tests/v2/t.py": GOOD}, [ROW]))
        self.assertEqual(problems, [])
        self.assertEqual([(s.scope, s.callable, s.target, s.kind) for s in sites], [("f", "c.kill", "c", "process")])
        self.assertEqual(da.check(tree({"tests/v2/t.py": GOOD}, [ROW])), [])

    def test_B_a_site_with_no_row_fails(self):
        problems = da.check(tree({"tests/v2/t.py": GOOD}, []))
        self.assertTrue(any("no ledger row" in p for p in problems), problems)

    def test_C_a_row_with_no_site_fails(self):
        problems = da.check(tree({"tests/v2/t.py": "x = 1\n"}, [ROW]))
        self.assertTrue(any("no longer exists" in p for p in problems), problems)

    def test_D_a_declared_source_the_derivation_does_not_match_fails(self):
        claim = ("import os\nimport pathlib\n\n\ndef f():\n    pid = int(pathlib.Path('/tmp/s.pid').read_text())\n"
                 "    os.kill(pid, 9)\n")
        row = {**ROW, "callable": "os.kill", "target": "pid"}
        problems = da.check(tree({"tests/v2/t.py": claim}, [row]))
        self.assertTrue(any("not bound in its scope to a handle the test created" in p for p in problems), problems)
        row = {**ROW, "callable": "os.kill", "target": "pid", "authority_source": "LIVENESS_PROBE_SIGNAL_0"}
        problems = da.check(tree({"tests/v2/t.py": claim}, [row]))
        self.assertTrue(any("literal 0" in p for p in problems), problems)
        row = {**ROW, "callable": "os.kill", "target": "pid", "authority_source": "KNOWN_SAFE"}
        problems = da.check(tree({"tests/v2/t.py": claim}, [row]))
        self.assertTrue(any("not one of the closed set" in p for p in problems), problems)

    def test_E_an_ambiguous_derivation_fails(self):
        ambiguous = "def f(c):\n    c.kill()\n"  # a parameter of unknown origin
        problems = da.check(tree({"tests/v2/t.py": ambiguous}, [ROW]))
        self.assertTrue(any("not bound in its scope" in p for p in problems), problems)

    def test_F_a_destructive_api_outside_the_taxonomy_fails_closed(self):
        problems = da.check(tree({"tests/v2/t.py": "import psutil\n"}, []))
        self.assertEqual(problems, ["tests/v2/t.py:1: imports psutil: a process API the taxonomy does not cover — fail closed"])
        problems = da.check(tree({"tests/v2/t.py": "from psutil import Process\n"}, []))
        self.assertEqual(problems, ["tests/v2/t.py:1: imports psutil: a process API the taxonomy does not cover — fail closed"])
        shell = "import subprocess\n\n\ndef f(p):\n    subprocess.run(['rm', '-rf', p])\n"
        problems = da.check(tree({"tests/v2/t.py": shell}, []))
        self.assertTrue(any("shell" in p or "no ledger row" in p for p in problems), problems)
        row = {**ROW, "callable": "shell:['rm', '-rf', p]", "target": "", "target_kind": "shell"}
        problems = da.check(tree({"tests/v2/t.py": shell}, [row]))
        self.assertTrue(any("fail closed" in p for p in problems), problems)

    def test_A2_every_direct_shape_names_its_target_and_sites_come_in_one_order(self):
        text = ("import os\nimport pathlib\nimport shutil\nimport signal\nimport subprocess\nimport sys\n\n\ndef f(d, tid):\n"
                "    c = subprocess.Popen([sys.executable])\n    if d:\n        c.kill()  # nested: the walk reaches it after the next line\n"
                "    c.terminate()\n    c.send_signal(9)\n"
                "    pathlib.Path(d).unlink()\n    pathlib.Path(d).rmdir()\n    os.remove(d)\n    os.kill(c.pid, 9)\n"
                "    shutil.rmtree(d)\n    signal.pthread_kill(tid, 9)\n    os.killpg(c.pid, 9)\n")
        later = "import os\n" + "\n" * 30 + "\ndef g(p):\n    os.remove(p)\n"   # a lower path at a higher line number
        sites, _ = da.discover(tree({"tests/v2/zz.py": text, "tests/v2/aa.py": later}, []))
        self.assertEqual([(s.path, s.callable, s.target, s.kind) for s in sites], [
            ("tests/v2/aa.py", "os.remove", "p", "path"),
            ("tests/v2/zz.py", "c.kill", "c", "process"), ("tests/v2/zz.py", "c.terminate", "c", "process"),
            ("tests/v2/zz.py", "c.send_signal", "c", "process"), ("tests/v2/zz.py", "pathlib.Path(d).unlink", "pathlib.Path(d)", "path"),
            ("tests/v2/zz.py", "pathlib.Path(d).rmdir", "pathlib.Path(d)", "path"), ("tests/v2/zz.py", "os.remove", "d", "path"),
            ("tests/v2/zz.py", "os.kill", "c.pid", "process"), ("tests/v2/zz.py", "shutil.rmtree", "d", "path"),
            ("tests/v2/zz.py", "signal.pthread_kill", "tid", "process"), ("tests/v2/zz.py", "os.killpg", "c.pid", "process_group")])
        self.assertEqual([s.node.lineno for s in sites[1:]], sorted(s.node.lineno for s in sites[1:]))

    def test_G_MUT_AUTH_NEG_3_a_destructive_callable_passed_by_reference_without_a_row_fails(self):
        shapes = {
            "addCleanup": "import shutil\nimport tempfile\nimport unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n"
                          "        d = tempfile.mkdtemp()\n        self.addCleanup(shutil.rmtree, d, True)\n",
            "alias+register": "import atexit\nimport os\nimport subprocess\nimport sys\n\n\ndef f():\n    c = subprocess.Popen([sys.executable])\n"
                              "    callback = os.kill\n    atexit.register(callback, c.pid, 9)\n",
            "partial": "import functools\nimport shutil\nimport tempfile\n\n\ndef f():\n    d = tempfile.mkdtemp()\n"
                       "    functools.partial(shutil.rmtree, d)()\n",
            "ExitStack.callback": "import contextlib\nimport shutil\nimport tempfile\n\n\ndef f():\n    d = tempfile.mkdtemp()\n"
                                  "    with contextlib.ExitStack() as stack:\n        stack.callback(shutil.rmtree, d)\n",
            "alias call": "import os\nimport subprocess\nimport sys\n\n\ndef f():\n    c = subprocess.Popen([sys.executable])\n"
                          "    callback = os.kill\n    callback(c.pid, 9)\n",
        }
        for shape, text in shapes.items():
            with self.subTest(shape=shape):
                sites, _ = da.discover(tree({"tests/v2/t.py": text}, []))
                self.assertEqual(len(sites), 1, shape)
                problems = da.check(tree({"tests/v2/t.py": text}, []))
                self.assertTrue(any("no ledger row" in p for p in problems), (shape, problems))
        sites, _ = da.discover(tree({"tests/v2/t.py": shapes["addCleanup"]}, []))
        self.assertEqual((sites[0].callable, sites[0].target, sites[0].kind), ("addCleanup->shutil.rmtree", "d", "path"))
        sites, _ = da.discover(tree({"tests/v2/t.py": shapes["alias+register"]}, []))
        self.assertEqual((sites[0].callable, sites[0].target, sites[0].kind), ("register->callback=os.kill", "c.pid", "process"))
        sites, _ = da.discover(tree({"tests/v2/t.py": shapes["alias call"]}, []))
        self.assertEqual((sites[0].callable, sites[0].target, sites[0].kind), ("callback=os.kill", "c.pid", "process"))
        module_alias = ("import atexit\nimport os\nimport subprocess\nimport sys\n\nCALLBACK = os.kill\n\n\ndef f():\n"
                        "    c = subprocess.Popen([sys.executable])\n    atexit.register(CALLBACK, c.pid, 9)\n    CALLBACK(c.pid, 9)\n")
        sites, _ = da.discover(tree({"tests/v2/t.py": module_alias}, []))
        self.assertEqual([(s.callable, s.target) for s in sites], [("register->CALLBACK=os.kill", "c.pid"), ("CALLBACK=os.kill", "c.pid")])
        not_aliases = ("import os\n\n\nclass K:\n    callback = os.kill  # a class attribute: not a name any method can use bare\n\n"
                       "    def m(self, o, pid):\n        callback = os.kill\n        o.callback(pid)  # someone else's method, not the alias\n"
                       "        self.callback(pid, 0)  # an attribute of self, not the bare name\n")
        sites, _ = da.discover(tree({"tests/v2/t.py": not_aliases}, []))
        self.assertEqual(sites, [])
        in_method = ("import os\nimport subprocess\nimport sys\nimport unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n"
                     "        c = subprocess.Popen([sys.executable])\n        callback = os.kill  # a method-local alias\n"
                     "        callback(c.pid, 9)\n        self.addCleanup(callback, c.pid, 9)\n")
        sites, _ = da.discover(tree({"tests/v2/t.py": in_method}, []))
        self.assertEqual([(s.scope, s.callable, s.target) for s in sites],
                         [("T.test_x", "callback=os.kill", "c.pid"), ("T.test_x", "addCleanup->callback=os.kill", "c.pid")])
        row = {**ROW, "callable": "addCleanup->shutil.rmtree", "target": "d", "target_kind": "path", "scope": "T.test_x",
               "authority_source": "TEST_CREATED_PATH"}
        self.assertEqual(da.check(tree({"tests/v2/t.py": shapes["addCleanup"]}, [row])), [])  # ledgered: passes

    def test_H_MUT_AUTH_NEG_4_the_registered_callable_stays_but_its_target_is_no_longer_test_created(self):
        drifted = ("import pathlib\nimport shutil\nimport unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n"
                   "        d = pathlib.Path('/tmp/subject.out').read_text().strip()  # a path the subject reported\n"
                   "        self.addCleanup(shutil.rmtree, d, True)\n")
        row = {**ROW, "callable": "addCleanup->shutil.rmtree", "target": "d", "target_kind": "path", "scope": "T.test_x",
               "authority_source": "TEST_CREATED_PATH"}
        problems = da.check(tree({"tests/v2/t.py": drifted}, [row]))
        self.assertTrue(any("is not a path this test created" in p for p in problems), problems)
        bound_method = ("import subprocess\nimport sys\nimport unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n"
                        "        c = subprocess.Popen([sys.executable])\n        self.addCleanup(c.kill)\n")
        sites, _ = da.discover(tree({"tests/v2/t.py": bound_method}, []))
        self.assertEqual((sites[0].callable, sites[0].target, sites[0].kind), ("addCleanup->c.kill", "c", "process"))

    def test_I_an_unmodelled_registration_or_a_keyword_passed_callable_fails_closed(self):
        unknown = "import shutil\nimport tempfile\n\n\ndef schedule(fn, *a):\n    pass\n\n\ndef f():\n    d = tempfile.mkdtemp()\n    schedule(shutil.rmtree, d)\n"
        keyword = ("import shutil\nimport tempfile\nimport unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n"
                   "        d = tempfile.mkdtemp()\n        self.addCleanup(function=shutil.rmtree, path=d)\n")
        for shape, text, callable_ in (("unknown", unknown, "schedule->shutil.rmtree"), ("keyword", keyword, "addCleanup->function=shutil.rmtree")):
            with self.subTest(shape=shape):
                sites, _ = da.discover(tree({"tests/v2/t.py": text}, []))
                self.assertEqual([(s.callable, s.kind) for s in sites], [(callable_, "callback_unmodelled")])
                row = {**ROW, "callable": callable_, "target": sites[0].target, "target_kind": "callback_unmodelled",
                       "scope": sites[0].scope, "authority_source": "TEST_CREATED_PATH"}
                problems = da.check(tree({"tests/v2/t.py": text}, [row]))
                self.assertTrue(any("does not model" in p and "fail closed" in p for p in problems), problems)

    def test_J_the_ledger_check_names_every_problem_exactly(self):
        where = "tests/v2/t.py:7 [f] c.kill(c)"
        self.assertEqual(da.check(tree({"tests/v2/t.py": GOOD}, [])),
                         [f"{where}: destructive site with no ledger row — its authority source is undeclared"])
        self.assertEqual(da.check(tree({"tests/v2/t.py": GOOD}, None)), ["validation/v2/destructive_sites.json is missing"])
        k = "('tests/v2/t.py', 'f', 'c.kill', 'c')"
        self.assertEqual(da.check(tree({"tests/v2/t.py": GOOD}, [ROW, ROW])), [f"ledger: duplicate row for {k}"])
        for field in ("target_kind", "authority_source", "justification", "enforcement"):
            with self.subTest(field=field):
                problems = da.check(tree({"tests/v2/t.py": GOOD}, [{**ROW, field: ""}]))
                self.assertEqual(problems[0], f"ledger row {k}: missing ['{field}']")
        self.assertEqual(da.check(tree({"tests/v2/t.py": GOOD}, [{**ROW, "target_kind": "path"}]))[0],
                         "tests/v2/t.py:7: ledger says target_kind 'path', the site acts on a process")
        self.assertEqual(da.check(tree({"tests/v2/t.py": "x = 1\n"}, [ROW])), [f"ledger row {k} points to a site that no longer exists"])
        self.assertEqual(da.check(tree({"tests/v2/t.py": GOOD}, [{**ROW, "occurrences": 2}])), [f"ledger row {k}: occurrences 2, found 1"])
        shell = "import subprocess\n\n\ndef f(p):\n    subprocess.run(['rm', '-rf', p])\n"
        row = {**ROW, "callable": "shell:['rm', '-rf', p]", "target": "", "target_kind": "shell"}
        self.assertEqual(da.check(tree({"tests/v2/t.py": shell}, [row]))[0],
                         "tests/v2/t.py:5: a shell-level destructive command (shell:['rm', '-rf', p]) has no statically "
                         "verifiable authority — fail closed")
        unknown = "import shutil\nimport tempfile\n\n\ndef schedule(fn, *a):\n    pass\n\n\ndef f():\n    d = tempfile.mkdtemp()\n    schedule(shutil.rmtree, d)\n"
        row = {**ROW, "callable": "schedule->shutil.rmtree", "target": "", "target_kind": "callback_unmodelled", "scope": "f",
               "authority_source": "TEST_CREATED_PATH"}
        problems = da.check(tree({"tests/v2/t.py": unknown}, [row]))
        self.assertEqual(problems[0], "tests/v2/t.py:11: a destructive callable handed by reference to a registration the "
                                      "taxonomy does not model (schedule->shutil.rmtree) — its target cannot be derived; fail closed")


if __name__ == "__main__":
    unittest.main()
