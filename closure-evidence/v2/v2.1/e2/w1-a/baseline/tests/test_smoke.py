import unittest


class Smoke(unittest.TestCase):
    def test_package_imports(self):
        import treesum
        self.assertIsNotNone(treesum)


if __name__ == "__main__":
    unittest.main()
