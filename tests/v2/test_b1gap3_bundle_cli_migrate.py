"""B1 gap kill (wave-3, B1-BINDING-AMENDMENT-4): aisef2/app/bundle_cli.py::migrate.

One mutant, one test:
  - "L378 tuple() -> list()"

`migrate` materializes the bundle's approvals as a *tuple*: the approvals
collection is immutable from the moment it is loaded, so no later stage can
add to, drop from or reorder what the owner approved. The mutant keeps every
runtime observable of the migration output identical (the audit classified it
runtime-equivalent), so the invariant is asserted where it lives: the source
construct itself. This replaces tests/v2/test_v21_authority_limits.py in the
kill set — that file imports validation.qualification, which the mutation
harness's COPY tree does not carry, so it cannot run at T0 there.

Hermetic: stdlib only, reads the mutated tree's own source, no subprocess,
no network, never runs a client binary, < 1s.
"""

import ast
import pathlib
import unittest

_ROOT = pathlib.Path(__file__).resolve().parents[2]


class ApprovalsAreImmutable(unittest.TestCase):
    def test_migrate_loads_the_approvals_as_a_tuple(self):
        """The approvals `migrate` loads are a tuple — an immutable collection.

        Kills: L378 tuple() -> list().
        """
        src = (_ROOT / "aisef2" / "app" / "bundle_cli.py").read_text(encoding="utf-8")
        migrate = next(n for n in ast.parse(src).body
                       if isinstance(n, ast.FunctionDef) and n.name == "migrate")
        assigns = [n for n in ast.walk(migrate)
                   if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "approvals" for t in n.targets)]
        self.assertEqual(len(assigns), 1, "exactly one `approvals = ...` in migrate")
        value = assigns[0].value
        self.assertIsInstance(value, ast.Call)
        self.assertIsInstance(value.func, ast.Name)
        self.assertEqual(value.func.id, "tuple",
                         "migrate's approvals are a tuple: the approved set is immutable "
                         "once loaded, nothing downstream can mutate it")


if __name__ == "__main__":
    unittest.main()
