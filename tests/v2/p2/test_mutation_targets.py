"""The mutation tool locates every P2 target, including a method named by its class (`Class.method`) where one module
has several methods of that name (protocol.py's `__post_init__`s)."""

import ast
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
_s = importlib.util.spec_from_file_location("p2_mutation_tool", ROOT / "validation" / "v2" / "mutation.py")
mu = importlib.util.module_from_spec(_s)
_s.loader.exec_module(mu)


class Locator(unittest.TestCase):
    def test_a_class_qualified_name_picks_that_class_method(self):
        tree = ast.parse("class A:\n    def f(self):\n        return 1\n\n\nclass B:\n    def f(self):\n        return 2\n")
        self.assertEqual(mu._root(tree, "B.f")[0].lineno, 7)
        self.assertEqual(mu._root(tree, "f")[0].lineno, 2)
        self.assertIsNone(mu._root(tree, "C.f"))

    def test_a_return_of_None_is_not_mutated_into_itself(self):
        got = [d for d, _ in mu.mutants("def f(x):\n    if x:\n        return None\n    return x\n", "f", {})]
        self.assertEqual([d for d in got if "returns None" in d], ["L4 returns None"])

    def test_a_reference_models_refusal_message_is_not_a_mutation_site(self):
        src = "def f(x):\n    if x > 1:\n        raise Refused(f'seq {x}: refused ' + 'here')\n    return x\n"
        got = [d for d, _ in mu.mutants(src, "f", {})]
        self.assertEqual(sorted(got), sorted(["L2 Gt->LtE", "L2 condition negated", "L4 returns None"]))
        self.assertTrue(all(k[0].startswith("tests/v2/refmodel/") and v for k, v in mu.AUDITED.items()))

    def test_every_target_resolves(self):
        for target in mu.TARGETS:
            rel, func = target.split("::")
            with self.subTest(target=target):
                self.assertIsNotNone(mu._root(ast.parse((ROOT / rel).read_text(encoding="utf-8")), func))


class TableAuthorityMigration(unittest.TestCase):
    """Owner directive 2026-11-26 LANE A §1: story_state._OUTCOMES/_WITHIN and terminal_state._RUN were consolidated
    into aisef2/journal/transitions.py (STORY/WITHIN/RUN/symbol_of). These adversarial controls prove the mutation
    coverage moved WITH the authority and did not silently disappear."""

    TABLE = "aisef2/journal/transitions.py"
    MOVED = ("STORY", "WITHIN", "RUN", "symbol_of")
    RETIRED = ("aisef2/journal/projections/story_state.py::_OUTCOMES",
               "aisef2/journal/projections/story_state.py::_WITHIN",
               "aisef2/journal/projections/terminal_state.py::_RUN")

    def test_the_moved_authority_is_targeted_resolves_and_generates_mutants(self):
        src = (ROOT / self.TABLE).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for sym in self.MOVED:
            with self.subTest(surface=sym):
                self.assertIn(f"{self.TABLE}::{sym}", mu.TARGETS, "not registered as a mutation target")
                self.assertIsNotNone(mu._root(tree, sym), "does not resolve in the source")
                self.assertTrue(mu.mutants(src, sym, {}), "generates no mutants — coverage vanished")
                # killed by the table's own digest pin: a value mutation cannot survive it
                self.assertIn("tests/v2/test_v23_transitions.py", mu.TARGETS[f"{self.TABLE}::{sym}"])

    def test_the_retired_symbols_cannot_linger_as_dead_targets(self):
        for gone in self.RETIRED:
            rel, func = gone.split("::")
            with self.subTest(target=gone):
                self.assertNotIn(gone, mu.TARGETS, "consolidated symbol still registered as a target")
                self.assertIsNone(mu._root(ast.parse((ROOT / rel).read_text(encoding="utf-8")), func),
                                  "consolidated symbol still present in the source")

    def test_a_table_value_mutation_is_caught_by_the_digest_pin(self):
        # the kill mechanism, demonstrated: any edit to a table value moves TABLE_DIGEST, which
        # tests/v2/test_v23_transitions.py asserts as a literal (C-1 §3.1) — so the mutant is killed
        import aisef2.journal.transitions as tr
        from aisef2.product.contract import digest
        self.assertEqual(digest(tr._digest_form()), tr.TABLE_DIGEST)                    # the pin matches the live table
        form = tr._digest_form()
        form["STORY"] = [row for row in form["STORY"] if row != ["ACTIVE", "story/commit", "DECIDED_COMMIT"]]
        self.assertNotEqual(digest(form), tr.TABLE_DIGEST)                              # drop one move -> pin breaks -> killed


if __name__ == "__main__":
    unittest.main()
