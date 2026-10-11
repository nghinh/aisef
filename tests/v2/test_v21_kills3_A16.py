"""V2.1 (owner B-03, kills round 3, batch A16 — the audit batch of aisef2/app/review_verify.py's `_canon`, `_scalars`,
`_states` and `verify`): the one survivor of the batch whose audit did not hold up under review.

verify[23] (' is not calibrated for ' emptied) was audited by the implementer on the ground that "unqualified
observation" still names the cause. It does not: the reason is what a person triaging the journal / RUN.json reads to
learn *why* a finding was not verified, and the cause of this refusal is that the observation class is not calibrated
at the bytes that run — the word the module's own docstring, `aisef2/app/bundle_cli.py` and the calibration records
use. Without it the reason is a probe id run into a class and a consequence, indistinguishable by name from the other
UNVERIFIABLE causes (refused observation, no probe, did not execute). The sibling batch T16a pins the same cause token
for its own mutant; this file keeps A16 self-standing.

Not tested here, by design (audited, see the batch report): the other seven survivors of the batch are equivalent under
a stated invariant or differ only in the form or the explanatory prose of a recorded text."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_verify as V  # noqa: E402

PROBE = "probe.cli_invocation"
REPRODUCER = {"clause": "R-9/3", "subject": {"kind": "cli_invocation", "locator": "ledgerlock:__main__"},
              "stimulus": {"argv": ["snapshot", "<ws>/missing.jsonl"]}, "observable": {"exit_code": 3, "within_s": 20}}


class UncalibratedRefusalNamesItsCause(unittest.TestCase):
    """Pins aisef2/app/review_verify.py::verify [23]. A finding whose observation class no calibration qualifies at the
    bytes that run — the release ships no calibration, or the probe's bytes are not the calibrated ones — is
    UNVERIFIABLE and its probe never runs; the reason names the probe, the observation class and the cause: that the
    class is not calibrated."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = t.name

    def verify(self) -> V.Verification:
        return V.verify({"id": "F-1", "severity": "high", "reproducer": REPRODUCER}, requirements={"R-9": object()},
                        product_roots=("ledgerlock",), root=self.root, revision="0" * 40, timeout_s=60,
                        interpreter=sys.executable)

    def test_the_reason_names_the_probe_the_class_and_that_it_is_not_calibrated(self):
        for what, patch in (("the release ships no calibrations",
                             mock.patch("aisef2.app.run.calibrations", return_value=())),
                            ("the probe's bytes are not the calibrated ones",
                             mock.patch.object(V, "executing", lambda probe: "0" * 64))):
            with self.subTest(what), patch, \
                    mock.patch.object(V, "run_probe", side_effect=AssertionError("an uncalibrated observation ran")):
                v = self.verify()
                self.assertEqual((v.status, v.probe, v.observed), (V.UNVERIFIABLE, PROBE, None))
                self.assertEqual(v.evidence(), "")
                self.assertIn(PROBE, v.reason)             # the probe
                self.assertIn("exits", v.reason)           # the observation class that is not calibrated
                self.assertIn("not calibrated", v.reason)  # the cause: not a refused observation, not a probe that ran


if __name__ == "__main__":
    unittest.main()
