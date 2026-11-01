"""ROADMAP-2.2 F1 — the sealing tier cannot lose a check silently. Two closures:

* The tree <-> the list: every test carrying the `@sealing` gate is in `sealing_gate.GATED`, and every listed id
  exists in the tree with the gate on it — found by AST over tests/, so a decorator added without listing it, or an
  entry whose test was moved or renamed, is a failure on every branch, env or no env.
* The CI wiring: tests.yml holds a `sealing` job restricted to master and tags that runs the suite under
  AISEF_SEALING=1 with a full-history checkout — the job that keeps the record-currency tier measured (and honestly
  RED until the owner reseals), while branch/PR signal stays the product's."""
from __future__ import annotations

import ast
import pathlib
import re
import unittest

from tests.v2 import sealing_gate

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _gated_in_tree() -> set[str]:
    found: set[str] = set()
    for p in sorted((ROOT / "tests").rglob("test_*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        rel = p.relative_to(ROOT).as_posix()
        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
            def marked(node) -> bool:
                return any(isinstance(d, ast.Name) and d.id == "sealing"
                           or isinstance(d, ast.Attribute) and d.attr == "sealing" for d in node.decorator_list)
            if marked(cls):
                found.add(f"{rel}::{cls.name}")
            for fn in [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                if marked(fn):
                    found.add(f"{rel}::{cls.name}.{fn.name}")
    return found


class GateClosure(unittest.TestCase):
    def test_the_gated_tests_and_the_list_are_the_same_set(self):
        found = _gated_in_tree()
        listed = set(sealing_gate.GATED)
        self.assertEqual(sorted(found - listed), [], "gated in the tree but not listed in sealing_gate.GATED")
        self.assertEqual(sorted(listed - found), [], "listed in sealing_gate.GATED but not gated in the tree "
                                                     "(moved, renamed, or the decorator was dropped)")

    def test_the_list_is_closed_and_well_formed(self):
        self.assertEqual(len(set(sealing_gate.GATED)), len(sealing_gate.GATED))
        for entry in sealing_gate.GATED:
            self.assertRegex(entry, r"^tests/v2/.+\.py::[A-Za-z_]\w*(\.[A-Za-z_]\w*)?$")
            self.assertTrue((ROOT / entry.split("::")[0]).is_file(), entry)


class CiWiring(unittest.TestCase):
    def test_tests_yml_holds_the_master_and_tag_sealing_job(self):
        text = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
        m = re.search(r"\n  sealing:\n(.*?)(?=\n  [A-Za-z_][\w-]*:|\Z)", text, re.S)
        self.assertIsNotNone(m, "tests.yml has no `sealing` job")
        job = m.group(1)
        code = "\n".join(ln for ln in job.split("\n") if not ln.lstrip().startswith("#"))
        self.assertIn("github.ref == 'refs/heads/master' || github.ref_type == 'tag'", code)
        self.assertIn("AISEF_SEALING=1", code)
        self.assertIn("unittest discover -s tests", code)
        self.assertIn("actions/checkout", code)
        self.assertRegex(code, r"fetch-depth:\s*0")


if __name__ == "__main__":
    unittest.main()
