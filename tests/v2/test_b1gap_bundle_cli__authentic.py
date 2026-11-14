"""B1 gap kill tests for `aisef2/app/bundle_cli.py::_authentic` (v2.2 release-gate mutation campaign).

One surviving mutant: L905 `sorted()` -> `list()`. The EVIDENCE_MISMATCH refusal names the changed evidence files as
`sorted(...)[:5]` — deterministically the five lexicographically smallest. The existing kill test
(`test_v21_pw_lineage_continue.py::TheOperatorAsksForAnAnchor::test_the_mismatch_names_the_evidence_file_that_no_longer_matches`)
uses a single changed file, where `list(...) == sorted(...)` and the mutant is invisible. Here the stored manifest is
tampered with twenty entries the run directory does not hold, so under the mutant the message shows an arbitrary
set-iteration (hash-order) prefix instead of the sorted first five. Offline; hermetic (the Continuation fixture builds
its run directories in a TemporaryDirectory); no client, no provider."""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import run as R  # noqa: E402
from tests.v2.test_v21_pw_lineage_continue import Continuation  # noqa: E402


class TheMismatchNamesTheSmallestFive(Continuation):
    # Kills: L905 sorted() -> list()
    def test_the_changed_files_are_the_five_lexicographically_smallest_in_order(self):
        """Twenty evidence entries the manifest binds are not on disk: the refusal names exactly the five
        lexicographically smallest, in sorted order. The only observable effect of the mutant is this rendered list
        inside the message (hash order instead of sorted order), so the exact rendered sorted prefix is asserted —
        the smallest stable substring the mutant destroys."""
        run = self.run_dir(self.delivered(), manifest=True)
        stored = json.loads((run / R.MANIFEST).read_text(encoding="utf-8"))
        tampered = [f"tampered/{i:02d}.json" for i in range(20)]
        stored["files"].update({k: "0" * 64 for k in tampered})  # bound by the manifest, absent on disk: all changed
        (run / R.MANIFEST).write_text(json.dumps(stored), encoding="utf-8")
        err = self.refused(run, expect_anchor=R.anchor_of(stored))
        self.assertEqual(getattr(err, "code", None), "EVIDENCE_MISMATCH", str(err))
        self.assertIn(str(tampered[:5]), str(err))


if __name__ == "__main__":
    import unittest
    unittest.main()
