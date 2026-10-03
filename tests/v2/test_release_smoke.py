"""The release smoke's preregistration logic (validation/qualification/release_smoke.py, charter §15-§17): the budget
envelope never exceeds the owner's ceilings, the client identity carries no secret, and the rehearsal refuses a false
acceptance or a delivery that does not pass."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import release_smoke as S  # noqa: E402


class Envelope(unittest.TestCase):
    def test_seven_stories_under_the_ceilings(self):
        e = S.envelope(7)
        self.assertEqual(e["estimate"], {"provider_requests": 46, "turns": 3360})
        self.assertEqual(e["budget"], {"provider_requests": 58, "turns": 700, "input_tokens": 60_000_000, "output_tokens": 400_000})

    def test_never_above_a_ceiling(self):
        self.assertEqual(S.envelope(50)["budget"]["provider_requests"], 60)


class ClientIdentity(unittest.TestCase):
    def test_the_key_is_neither_recorded_nor_part_of_the_routing_digest(self):
        with tempfile.TemporaryDirectory() as t:
            cfg = pathlib.Path(t) / "opencode"
            cfg.mkdir()
            doc = {"provider": {"9router": {"npm": "x", "options": {"baseURL": S.PROVIDER["endpoint"], "apiKey": "sk-secret-1"}}}}
            (cfg / "opencode.json").write_text(json.dumps(doc), encoding="utf-8")
            env = {"XDG_CONFIG_HOME": t, "PATH": t}
            one = S.client_identity(environ=env)
            doc["provider"]["9router"]["options"]["apiKey"] = "sk-secret-2"
            (cfg / "opencode.json").write_text(json.dumps(doc), encoding="utf-8")
            two = S.client_identity(environ=env)
            doc["provider"]["9router"]["options"]["baseURL"] = "https://elsewhere.invalid/v1"
            (cfg / "opencode.json").write_text(json.dumps(doc), encoding="utf-8")
            three = S.client_identity(environ=env)
        self.assertNotIn("sk-secret", json.dumps(one))
        self.assertEqual(one, two)
        self.assertEqual((one["endpoint"], one["key_present"], one["binary"]), (S.PROVIDER["endpoint"], True, None))
        self.assertNotEqual(one["routing_config_sha256"], three["routing_config_sha256"])


class Rehearsal(unittest.TestCase):
    OK = {"exit": 0, "verify_exit": 0, "release_smoke_pass": "YES", "false_acceptance": [], "unaccounted": [],
          "visible_outside_the_context_policy": []}
    FB = {**OK, "retry_prompts": ["STORY-04-01"], "retry_prompts_naming_the_refuted_criterion": ["STORY-04-01"]}
    NONE = {**OK, "exit": 1, "release_smoke_pass": "NO"}

    def good(self, **change) -> dict:
        return {"reference": self.OK, "partial": self.OK, "feedback": self.FB, "nothing": self.NONE, **change}

    def test_a_good_rehearsal_has_no_problem(self):
        self.assertEqual(S.rehearsal_problems(self.good()), [])

    def test_each_failure_is_a_problem(self):
        cases = {"a missing scenario": {k: v for k, v in self.good().items() if k != "feedback"},
                 "a reference that does not pass": self.good(reference={**self.OK, "release_smoke_pass": "NO"}),
                 "a false acceptance": self.good(nothing={**self.NONE, "release_smoke_pass": "YES"}),
                 "nothing exits 0": self.good(nothing={**self.NONE, "exit": 0}),
                 "an unverified run": self.good(reference={**self.OK, "verify_exit": 1}),
                 "unaccounted spend": self.good(partial={**self.OK, "unaccounted": ["x"]}),
                 "superseded context visible": self.good(partial={**self.OK, "visible_outside_the_context_policy": ["AGENTS.md"]}),
                 "a feedback scenario that never retried": self.good(feedback={**self.FB, "retry_prompts": [],
                                                                               "retry_prompts_naming_the_refuted_criterion": []}),
                 "a retry that does not name the refuted criterion": self.good(
                     feedback={**self.FB, "retry_prompts_naming_the_refuted_criterion": []}),
                 "a feedback scenario that did not deliver": self.good(feedback={**self.FB, "release_smoke_pass": "NO"})}
        for name, results in cases.items():
            with self.subTest(name):
                self.assertTrue(S.rehearsal_problems(results))


class Gate(unittest.TestCase):
    """Owner ruling §14: no preregistration before S0-S5 PASS and the rehearsal's three criteria."""
    GOOD = {"criteria": dict(S.CRITERIA)}

    def test_every_phase_and_criterion_must_hold(self):
        from unittest import mock
        with mock.patch.object(S, "phases", return_value={k: "PASS" for k in S.PHASES}):
            self.assertEqual(S.gate(self.GOOD), [])
            self.assertEqual(len(S.gate(None)), len(S.CRITERIA))
            for k in S.CRITERIA:
                with self.subTest(k):
                    self.assertEqual(len(S.gate({"criteria": {**S.CRITERIA, k: "other"}})), 1)
        with mock.patch.object(S, "phases", return_value={**{k: "PASS" for k in S.PHASES}, "S5_QUALIFIED": "NOT_STARTED"}):
            self.assertEqual(S.gate(self.GOOD), ["S5_QUALIFIED is NOT_STARTED, not PASS"])


@unittest.skipUnless((ROOT / S.HISTORY[4] / "JOURNAL.json").exists() and
                     __import__("validation.qualification.release_workload", fromlist=["x"]).source_repo().exists(),
                     "the paid attempts' evidence or the LedgerLock workload is not here")
class Measured(unittest.TestCase):
    """Owner ruling §8 and §9 on the release bundle: public feedback for every obligation; the budget estimate."""

    @classmethod
    def setUpClass(cls):
        from aisef2.app import bundle
        from validation.qualification import release_bundle as rb
        cls.project = bundle.load(rb.build()["bundle"])

    def test_every_obligation_refuted_would_be_told_in_public_facts(self):
        d = S.feedback_coverage(self.project)
        self.assertEqual((d["obligations"], d["told_in_public_facts"], d["missing"]), (67, 67, {}))

    def test_a_feedback_that_drops_the_clause_is_caught(self):
        from unittest import mock
        from aisef2.app import feedback
        with mock.patch.object(feedback, "retry_feedback", return_value="- CONTRACT_UNSATISFIED (owner DEVELOPER)"):
            self.assertEqual(len(S.feedback_coverage(self.project)["missing"]), 67)

    def test_the_estimate_is_derived_from_the_preserved_attempts(self):
        e = S.estimate(self.project)
        self.assertEqual((e["estimate"]["tokens"], e["estimate"]["with_25pct_headroom"]), (292694, 365868))
        self.assertTrue(e["estimate"]["within_owner_ceiling"])
        self.assertEqual(e["pre_satisfied_in_every_paid_attempt"], ["STORY-02-01", "STORY-02-02"])
        self.assertEqual(e["failed_in_the_paid_attempts"], ["STORY-03-01", "STORY-04-01", "STORY-04-02"])
        self.assertFalse(any(v["within_owner_ceiling"] for v in e["sensitivity"].values()))

    def test_the_estimate_follows_its_evidence(self):
        h = S.measured()
        h[4]["sessions"][("STORY-01-01", "developer", 1)] = 200_000          # a costlier first session raises its price
        # ... and the role's maximum, which prices STORY-04-01's never-measured first developer session (was 67,966)
        self.assertEqual(S.estimate(self.project, h)["estimate"]["tokens"], 292694 + (200_000 - 51083) + (200_000 - 67966))


if __name__ == "__main__":
    unittest.main()
