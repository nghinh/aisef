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

    def test_every_p2_target_resolves(self):
        for target in mu.P2_TARGETS:
            rel, func = target.split("::")
            with self.subTest(target=target):
                self.assertIsNotNone(mu._root(ast.parse((ROOT / rel).read_text(encoding="utf-8")), func))


if __name__ == "__main__":
    unittest.main()
