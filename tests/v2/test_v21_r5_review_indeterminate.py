"""V2.1 (owner's fix window of 2026-10-15; RV-2 of docs/v2.1/decisions/B03-R4-REVIEW.md section 6): an observation the
probe could not decide is not said to be a proof that the finding does not reproduce.

The module's own contract (aisef2/app/review_verify.py, docstring): a finding is CONFIRMED when the probe REFUTES the
stated behaviour; the reason of a NOT_REPRODUCED says what the probe saw. A probe that ran and decided nothing —
`Executed(INDETERMINATE, reason)`: the subject is not in the candidate (PRECONDITION_ABSENT) or its process ended by a
signal the controller did not send (NON_CONTROLLER_SIGNAL) — has shown the candidate nothing, and `Verification.observed`
carries that verdict. Before this file `verify` gave the one sentence "observes the stated behaviour: the finding does
not reproduce" for every verdict but REFUTED, and since round 3 the journaled statement prints it beside
`observed: INDETERMINATE`.

Pinned here: the reason of an INDETERMINATE names the probe, the verdict and the typed cause and makes neither claim of a
SATISFIED one ("observes the stated behaviour", "does not reproduce"); a SATISFIED one still says the finding does not
reproduce; the statement holds the reason whole, for every probe and cause. NOT pinned, by the suite's rule (a reason
holds its identifying element and the class of its cause, never the wording around them): the sentence's other words.
The status an INDETERMINATE carries is not changed by this window (NOT_REPRODUCED, pinned in T15a): it never blocks."""

from __future__ import annotations

import json
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import review_verify as V  # noqa: E402
from aisef2.arch.enums import BehaviorVerdict, SubjectKind  # noqa: E402
from aisef2.probe import catalog  # noqa: E402
from aisef2.product.outcome import Executed, IndeterminateReason  # noqa: E402
from tests.v2 import test_v21_kills3_T15a as T  # noqa: E402 — the module: its tests are not collected again
from tests.v2 import test_v21_review_chain as C  # noqa: E402 — likewise

PROBE = catalog.active()[SubjectKind.CLI_INVOCATION].probe_id
#: what a SATISFIED verdict licenses and an INDETERMINATE one does not
CLAIMS = ("observes the stated behaviour", "does not reproduce")


def decided_nothing(case: unittest.TestCase, v: V.Verification, cause: str | None = None) -> None:
    case.assertEqual(v.observed, "INDETERMINATE", v)
    case.assertIn(PROBE, v.reason)
    case.assertIn("INDETERMINATE", v.reason)
    if cause:
        case.assertIn(cause, v.reason)
    for claim in CLAIMS:
        case.assertNotIn(claim, v.reason, v)
    case.assertNotEqual(v.status, V.CONFIRMED, v)
    case.assertEqual(v.evidence(), "")


@T.PROBE_RUNS
class WhatTheRealProbeSaw(T.Checkout):
    """The kernel's real probe, in a process of its own, on a real checkout."""

    def test_a_subject_the_candidate_lacks_is_undecided(self):
        f = T.finding()
        v = self.verify(f, self.checkout(without=("__main__.py",)))
        decided_nothing(self, v, "PRECONDITION_ABSENT")
        a = V.anchor(f, T.PROJECT)
        self.assertEqual(a.status, V.ANCHORED)     # a finding that would block, were it CONFIRMED: the reason matters
        self.assertFalse(V.blocks(v, f, "fix-loop", "low", a))

    def test_a_shown_behaviour_is_still_said_not_to_reproduce(self):
        v = self.verify(T.finding(), self.checkout())     # the reference exits 3 on a missing file: SATISFIED
        self.assertEqual(v.observed, "SATISFIED", v)
        self.assertIn(PROBE, v.reason)
        self.assertIn("does not reproduce", v.reason)
        self.assertNotIn("INDETERMINATE", v.reason)

    def test_the_statement_holds_the_reason_whole(self):
        f = T.finding()
        v = self.verify(f, self.checkout(without=("__main__.py",)))
        stated = json.loads(V.detail(f, v, V.anchor(f, T.PROJECT), None))
        self.assertEqual(stated["why"], v.reason)
        self.assertEqual(stated["observed"], "INDETERMINATE")
        self.assertIn("INDETERMINATE", stated["why"])
        for claim in CLAIMS:
            self.assertNotIn(claim, stated["why"])
        self.assertNotIn("elided", stated)


class EveryTypedCause(T.Checkout):
    """The verdict is the probe's: here it is injected (an Executed INDETERMINATE for each reason the protocol types, a
    calibration present), so the reason's words are decided by `verify` alone and on every platform."""

    def undecided(self, reason: IndeterminateReason) -> V.Verification:
        with mock.patch.object(V, "run_probe", return_value=object()), \
                mock.patch.object(V, "bound_result", return_value=Executed(BehaviorVerdict.INDETERMINATE, reason)), \
                mock.patch.object(V, "calibration_for", return_value=object()):     # the table is not what is under test
            return self.verify(T.finding(), self.tmp)

    def test_each_cause_is_named(self):
        for reason in IndeterminateReason:
            with self.subTest(reason=reason.value):
                decided_nothing(self, self.undecided(reason), reason.value)

    def test_the_reason_fits_the_statement_for_every_probe_and_cause(self):
        """`detail` bounds a reason at WHY_MAX and says `elided` when it cut: the longest probe id with the longest cause
        fits whole."""
        ids = [e.probe_id for e in catalog.active().values()]
        causes = [r.value for r in IndeterminateReason]
        for reason in IndeterminateReason:
            v = self.undecided(reason)
            worst = len(v.reason) - len(PROBE) - len(reason.value) + max(map(len, ids)) + max(map(len, causes))
            self.assertLessEqual(worst, V.WHY_MAX, v.reason)


class OnTheProductPath(C.ChainBase):
    """`aisef run`'s engine with the suite's scripted developer and finder (the probe is the real one): a candidate that
    ends its own process by SIGKILL on one argument, and an anchored finding that says that argument must exit 2. The
    probe could not observe an exit; the story is committed (nothing was confirmed) and every record of the finding says
    so in the probe's own terms."""

    KILLS = ("import os, signal\n\n\ndef main(args):\n    if args == ['kill']:\n        os.kill(os.getpid(), signal.SIGKILL)\n"
             "    if len(args) != 2:\n        return 2\n    return int(args[0]) + int(args[1])\n")

    def test_the_journal_run_json_and_artifact_say_it_was_undecided(self):
        rec = self.run_with([self.KILLS], [{"reproducers": [C.reproducer("R-CLI/1.2", ["kill"], 2)], "severity": "high"}])
        self.assertEqual(rec["story_outcomes"], {"S1": ["COMMIT"]})
        self.assertEqual(self.failures(), [])
        rows = [r for r in self.review_rows() if r["check"] != "S1:review"]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["passed"])
        stated = json.loads(rows[0]["detail"].split(" — ", 1)[1])
        self.assertEqual((stated["anchor"], stated["observed"]), ("ANCHORED", "INDETERMINATE"))
        reviewer = next(s for s in rec["sessions"] if s["role"] == "reviewer")
        kept = json.loads((self.out / stated["artifact"]["path"]).read_text(encoding="utf-8"))["finding"]["verification"]
        for where, why, observed in (("the statement", stated["why"], stated["observed"]),
                                     ("RUN.json", reviewer["findings"][0]["verification"]["why"],
                                      reviewer["findings"][0]["verification"]["observed"]),
                                     ("the artifact", kept["why"], kept["observed"])):
            with self.subTest(where):
                decided_nothing(self, V.Verification(V.NOT_REPRODUCED, why, PROBE, observed), "NON_CONTROLLER_SIGNAL")


if __name__ == "__main__":
    unittest.main()
