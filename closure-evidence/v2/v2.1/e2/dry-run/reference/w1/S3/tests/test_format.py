import unittest

from treesum.snapshot import compare, dumps, loads

A = "b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060"
B = "f2c82decdd7181cf98945929a62598db7e6b477e11f6e0eb0ae97020eff151ad"


class Format(unittest.TestCase):
    def test_dumps_sorted(self):
        self.assertEqual(dumps({"b.txt": B, "a.txt": A}), f"{A}  a.txt\n{B}  b.txt\n")
        self.assertEqual(dumps({}), "")

    def test_loads_lenient_lines(self):
        self.assertEqual(loads(f"\n{A}  a.txt\n   \n{B}  b.txt"), {"a.txt": A, "b.txt": B})

    def test_loads_rejects_bad_line(self):
        with self.assertRaises(ValueError):
            loads("not-a-digest  one.txt\n")

    def test_roundtrip(self):
        s = {"sub/c.txt": A, "a.txt": B, "b.txt": A}
        self.assertEqual(loads(dumps(s)), s)

    def test_compare(self):
        old = {"a.txt": A, "c.txt": A, "same.txt": B}
        new = {"a.txt": B, "b.txt": A, "same.txt": B}
        self.assertEqual(compare(old, new), {"added": ["b.txt"], "removed": ["c.txt"], "changed": ["a.txt"]})
        self.assertEqual(compare({}, {}), {"added": [], "removed": [], "changed": []})


if __name__ == "__main__":
    unittest.main()
