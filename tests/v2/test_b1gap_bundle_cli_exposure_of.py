"""B1 gap kill tests for aisef2/app/bundle_cli.py::exposure_of (pin L507).

Each mutant drops one element of the except tuple `(KeyError, TypeError, ValueError)` at L507, so the raw
exception from loading a bad old bundle escapes instead of B.BundleError. Library callers catch B.BundleError;
these tests call exposure_of directly (the CLI's outer handler at L1161 masks the type) and pin both the raised
type and the `from e` cause chain. Offline, no files, no subprocess."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle as B  # noqa: E402
from aisef2.app import bundle_cli  # noqa: E402


class ExposureOfRefusesABundleThatDoesNotLoad(unittest.TestCase):
    # kills: L507 element 0 dropped
    def test_a_bundle_missing_contracts_raises_bundle_error_caused_by_keyerror(self):
        with self.assertRaises(B.BundleError) as c:
            bundle_cli.exposure_of({"approvals": []})
        self.assertIs(type(c.exception.__cause__), KeyError)        # L505 old["contracts"], caught at L507

    # kills: L507 element 1 dropped
    def test_a_bundle_with_none_contracts_raises_bundle_error_caused_by_typeerror(self):
        with self.assertRaises(B.BundleError) as c:
            bundle_cli.exposure_of({"contracts": None, "plan": None})
        self.assertIs(type(c.exception.__cause__), TypeError)       # iterating None at L505, caught at L507

    # kills: L507 element 2 dropped
    def test_a_plan_with_an_invalid_role_raises_bundle_error_caused_by_plain_valueerror(self):
        old = {"contracts": [],
               "plan": {"obligations": [{"criterion_id": "C-1", "product_proof_spec_id": "PPS-" + "a" * 64,
                                         "story_id": "S1", "role": "NOT-A-ROLE",
                                         "expected_parent": "UNSATISFIED_AT_PARENT",
                                         "depends_on": [], "ownership_rationale": "r"}]}}
        with self.assertRaises(B.BundleError) as c:
            bundle_cli.exposure_of(old)
        self.assertIs(type(c.exception.__cause__), ValueError)      # ObligationRole('NOT-A-ROLE') in B._plan, plain ValueError


if __name__ == "__main__":
    unittest.main()
