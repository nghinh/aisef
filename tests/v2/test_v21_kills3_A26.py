"""V2.1 (owner B-03, kills round 3, batch A26): tests for survivors of aisef2/app/settings.py's `REVIEW_ABSENT` and
`endpoint_problem` that the triage proposed not to test and the audit of those claims did not support.

`REVIEW_ABSENT` — no entry point's behaviour differs for an emptied member of the sentinel (every consumer compares
against the one non-default member: `== "fix-loop"`, `== "ocr"`, a truthy `given`), so the requirement that is left is
the one the module states for it: it is the *named* rule an absent `review` means (settings.py L50), i.e. a review
the operator could also have written. That is a property of the sentinel against `load`'s own vocabulary and keys
(and the one value the documentation names for 2.0.0's rule, `advisory`), not a spelling of the rest.

`endpoint_problem` — the refusal of plaintext http to a host that is not loopback is an operator-facing contract; the
verdict that the host is the reason is part of it (tests/v2/test_v21_kills_settings.py, registered for the target after
campaign 2's snapshot, already pins the whole sentence; this one asserts the elements)."""

from __future__ import annotations

import copy
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import settings  # noqa: E402
from tests.v2.test_app_run import SETTINGS  # noqa: E402


class AbsentReviewIsTheNamedRuleAnOperatorCouldWrite(unittest.TestCase):
    """REVIEW_ABSENT: settings that name no `review` run 2.0.0's rule, *named* ("never a silent default",
    settings.py L50), and the stand-in is what `load` hands out as `Settings.review` and `Reviewer(review=None)` uses
    in place of a loaded review. A stand-in is only as good as its fit: it carries every key a loaded review carries
    (a reader may index any of them — `finder` is indexed in `load` itself, `ocr` by the OCR finder), its policy is the
    one the documentation names for 2.0.0's rule ("advisory keeps 2.0.0's behaviour: nothing blocks",
    review_verify.py), and its floor and finder are members of the vocabulary `load` accepts for a given review.

    No entry point's behaviour differs for an emptied member (every reader compares with the one non-default member), so
    these are kills by the invariant, not by a run: the second test fails on each mutant because the stand-in stops
    being a review `load` would produce for the same rule, and for the policy also because it stops being the
    documented one. The first test only ties the sentinel to what `load` returns; it kills nothing by itself.

    Pins aisef2/app/settings.py::REVIEW_ABSENT [3, 4, 5, 6, 7]: the `ocr` and `given` keys and the policy, floor and
    finder values (and, by the same property, the `finder` key [2])."""

    def test_the_absent_review_is_what_load_hands_out_when_the_settings_name_none(self):
        s = settings.load(copy.deepcopy(SETTINGS))
        self.assertEqual(s.review, settings.REVIEW_ABSENT)

    def test_the_absent_rule_is_the_review_the_operator_could_have_named(self):
        absent = settings.REVIEW_ABSENT
        self.assertEqual(absent["policy"], "advisory")      # 2.0.0's rule: a finding never blocks (review_verify.blocks)
        named = {"policy": absent["policy"], "min_severity": absent["min_severity"]}
        try:
            loaded = settings.load({**copy.deepcopy(SETTINGS), "review": named}).review
        except settings.SettingsError as e:
            self.fail(f"the rule an absent review stands for cannot be written as a review: {e}")
        # the same keys, the same finder and OCR pin; only `given` differs: the record binds a review the settings name
        self.assertEqual(loaded, {**absent, "given": True})
        self.assertIs(absent["given"], False)


class PlaintextEndpointToAnotherHost(unittest.TestCase):
    """endpoint_problem: plaintext http to a host that is not loopback is refused, and the refusal tells the operator
    which host is the reason — the host, then that it is not loopback — not only the rule it broke (the allowed hosts).
    The words around are not asserted: "evil.example is not a loopback host" is the same refusal.

    Pins aisef2/app/settings.py::endpoint_problem [31]."""

    def refusal(self, endpoint: str) -> str:
        doc = copy.deepcopy(SETTINGS)
        doc["provider"]["endpoint"] = endpoint
        with self.assertRaises(settings.SettingsError) as c:
            settings.load(doc)
        return str(c.exception)

    def test_the_refusal_says_that_this_host_is_not_loopback(self):
        for endpoint, host in (("http://evil.example/v1", "evil.example"), ("http://10.0.0.1:8080/v1", "10.0.0.1"),
                               ("http://localhost.example.com/v1", "localhost.example.com")):
            with self.subTest(endpoint):
                msg = self.refusal(endpoint)
                self.assertRegex(msg, r"\bendpoint\b")        # the object refused: the provider's endpoint
                self.assertIn(host, msg)
                verdict = msg.rpartition(host)[2]             # what the refusal says of the host follows its name
                self.assertIn("loopback", verdict)
                self.assertRegex(verdict, r"\b(?:not|non)\b")     # ...and it is that the host is not (non-) loopback


if __name__ == "__main__":
    unittest.main()
