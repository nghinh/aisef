import unittest

from app.calc import add


class TestAdd(unittest.TestCase):
    def test_add_returns_sum(self):
        self.assertEqual(add(2, 3), 5)

    def test_add_with_negatives(self):
        self.assertEqual(add(-1, -1), -2)

    def test_add_with_zero(self):
        self.assertEqual(add(0, 7), 7)


if __name__ == "__main__":
    unittest.main()
