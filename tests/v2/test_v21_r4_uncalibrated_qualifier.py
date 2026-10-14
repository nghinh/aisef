"""B-03 round 4 — `review_verify.verify`: the refusal of an observation no calibration qualifies says the BYTES are why.

The module's own definition of the cause (aisef2/app/review_verify.py, docstring): a probe's observation is not
evidence unless the probe is calibrated "for that class at the bytes that run" — the calibration record is keyed by
the probe id, the digest of the code that EXECUTES (`executing(factory)`) and the observation class (`calibration_for`:
"a record for another digest qualifies nothing"). The refusal is one constant for two states an operator tells apart
only by that qualifier: no calibration at all, and a calibration of other bytes — which is what a changed probe file
produces (the shipped release holds a row for each of its 19 pairs; after an edit of a probe module none is at the
bytes that run: docs/v2.1/decisions/B03-R3-PROBE-MODULE-FINDINGS.md, PM-7).

Campaign 5 left the tail of the constant emptied (`' at the bytes that run: an unqualified observation corroborates
nothing'`, `verify` [24]) SURVIVED with an audit "nothing reads the reason". Two independent re-verifications
disagreed on whether the qualifier is a requirement: one found it the only element of the text that carries the cause
and owed a test, the other held that the unmutated text never separated the two causes. This file states the
requirement they agree on: the documented qualifier is in the reason when the calibration is of other bytes. The
consequence clause that follows it is explanatory (D-002 is enforced by `blocks`, not by this text) and is not pinned."""

from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_verify as V  # noqa: E402
from tests.v2 import test_v21_kills3_T16a as T  # noqa: E402 — the module: its tests are not collected again


class ACalibrationOfOtherBytes(T.VerifyBase):
    def refused(self, patch):
        with patch, mock.patch.object(V, "run_probe", side_effect=AssertionError("an unqualified observation ran")):
            return self.verify(T.SNAPSHOT_MISSING)

    def test_the_reason_names_the_bytes_that_run_as_the_cause(self):
        v = self.refused(mock.patch.object(V, "executing", lambda probe: "0" * 64))     # a row exists, for other bytes
        self.untriaged(v, probe=T.PROBE)
        self.assertIn("not calibrated", v.reason)
        self.assertIn("at the bytes that run", v.reason)

    def test_the_class_and_the_probe_are_still_the_identifying_elements(self):
        v = self.refused(mock.patch.object(V, "executing", lambda probe: "0" * 64))
        self.assertIn(T.PROBE, v.reason)
        self.assertIn("exits", v.reason)


if __name__ == "__main__":
    unittest.main()
