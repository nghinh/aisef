"""INV-MUTATION-AUTHORITY, the static half (owner authorization of 2026-09-24 §5): the destructive-call-site checker
A. discovers sites mechanically, B. fails on a site with no ledger row, C. fails on a row with no site, D. fails when a
declared authority source does not match the derivation, E. fails on an ambiguous derivation, F. fails closed on a
destructive API outside its taxonomy — and passes on this tree."""

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


def tree(files: dict, ledger: list) -> pathlib.Path:
    t = pathlib.Path(tempfile.mkdtemp(prefix="aisef2-da-"))
    for scope in da.SCOPES:
        (t / scope).mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        (t / rel).parent.mkdir(parents=True, exist_ok=True)
        (t / rel).write_text(text, encoding="utf-8")
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
        self.assertTrue(any("taxonomy does not cover" in p for p in problems), problems)
        shell = "import subprocess\n\n\ndef f(p):\n    subprocess.run(['rm', '-rf', p])\n"
        problems = da.check(tree({"tests/v2/t.py": shell}, []))
        self.assertTrue(any("shell" in p or "no ledger row" in p for p in problems), problems)
        row = {**ROW, "callable": "shell:['rm', '-rf', p]", "target": "", "target_kind": "shell"}
        problems = da.check(tree({"tests/v2/t.py": shell}, [row]))
        self.assertTrue(any("fail closed" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
