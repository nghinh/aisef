"""B1 gap wave 2 — kill tests for aisef2/app/verify.py::_invariant_problems.

One test per surviving mutant. The kill route here is the malformed-digest problem MESSAGE
(owner precedent: the exception/problem message is a test-asserted observable), so the test
asserts the exact message, whose "the record's invariant " prefix the mutant destroys.
"""
from __future__ import annotations

import unittest

from aisef2.app.verify import _invariant_problems


class InvariantProblemsMessage(unittest.TestCase):
    # kills: L119 string "the record's invariant " emptied
    def test_a_malformed_digest_problem_names_the_record_s_invariant_field(self):
        rec = {"invariants": {"code_mechanism_digest": "a" * 64}}  # registry_digest absent -> None
        problems, said = _invariant_problems(rec)
        self.assertEqual(said, [])
        self.assertEqual(
            problems,
            ["the record's invariant registry_digest is not a 64-hex sha256: None"],
        )


if __name__ == "__main__":
    unittest.main()
