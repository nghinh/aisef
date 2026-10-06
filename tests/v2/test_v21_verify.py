"""V2.1 (A, V2-02): `aisef run --verify` re-derives every field that could raise a verdict, from the journal and the
run's own evidence — never from RUN.json alone. On 2.0.0 (backlog V21-30, 360° security W4, claims W4) a RUN.json
edited alone still VERIFIED: `budget_stop`, `story_errors` and `failure` were read from the record. Here a run that
delivered its one story but spent past its output ceiling (FAIL, budget stop) is re-labelled PASS in RUN.json; the
settings are raised to hide the overspend; a session log is shortened together with the record; the evidence
manifest is rewritten too — each forgery is refuted, the last one only against the anchor the operator kept.
Offline: the fake client and the fake provider of test_app_run."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import settings  # noqa: E402
from aisef2.app.verify import verify  # noqa: E402
from tests.v2.test_app_run import SETTINGS, ProductBase  # noqa: E402

#: two sessions of 10 output tokens each (7 + 3 reasoning) and a 1-token... preflight: past 15 only after the reviewer
OVERSPEND = {**SETTINGS, "budget": {"provider_requests": 20, "turns": 50, "input_tokens": 100000, "output_tokens": 15}}


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class RecordAlone(ProductBase):
    def setUp(self) -> None:
        super().setUp()
        self.settings = settings.load(OVERSPEND)
        self.rec = self.execute()
        self.out = self.tmp / "out"
        from aisef2.app import run as R
        self.anchor = R.anchor_in(self.out)

    def forge(self, **fields) -> None:
        rec = json.loads((self.out / "RUN.json").read_text(encoding="utf-8"))
        rec.update(fields)
        (self.out / "RUN.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    def test_the_run_is_what_the_scenario_says(self):
        self.assertEqual(self.rec["story_outcomes"], {"S1": ["COMMIT"]})
        self.assertEqual(self.rec["delivery_verdict"], "FAIL")
        self.assertIn("max_output_tokens exceeded", self.rec["budget_stop"])
        self.assertEqual(verify(self.project, self.out)["verdict"], "VERIFIED")

    def test_a_budget_stop_removed_from_the_record_is_refuted(self):
        self.forge(budget_stop=None, delivery_verdict="PASS", delivery_blocked_by=[])
        v = verify(self.project, self.out)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertEqual(v["delivery_verdict"], "FAIL")
        self.assertTrue(any("re-derives FAIL" in p for p in v["problems"]), v["problems"])

    def test_raising_the_ceiling_in_the_record_is_refuted(self):
        raised = {**OVERSPEND, "budget": {**OVERSPEND["budget"], "output_tokens": 100}}
        self.forge(settings=raised, budget_stop=None, delivery_verdict="PASS", delivery_blocked_by=[])
        v = verify(self.project, self.out)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertTrue(any("runspec" in p for p in v["problems"]), v["problems"])

    def test_story_outcomes_that_are_not_the_journal_s_are_refuted(self):
        self.forge(story_outcomes={"S1": ["RETRY", "COMMIT"]})
        v = verify(self.project, self.out)
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertTrue(any("story outcomes" in p for p in v["problems"]), v["problems"])

    def test_a_session_log_shortened_with_the_record_is_refuted_by_the_manifest(self):
        log = sorted((self.out / "sessions").glob("*.reviewer.*.jsonl"))[0]
        lines = log.read_text(encoding="utf-8").splitlines()
        log.write_text("\n".join(x for x in lines if '"step_finish"' not in x) + "\n", encoding="utf-8")
        self.forge(budget_stop=None, delivery_verdict="PASS", delivery_blocked_by=[])
        v = verify(self.project, self.out)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertTrue(any("evidence manifest" in p for p in v["problems"]), v["problems"])

    def test_deleting_a_session_s_steps_is_unaccounted_spend_even_with_a_rewritten_manifest(self):
        log = sorted((self.out / "sessions").glob("*.reviewer.*.jsonl"))[0]
        lines = log.read_text(encoding="utf-8").splitlines()
        log.write_text("\n".join(x for x in lines if '"step_finish"' not in x) + "\n", encoding="utf-8")
        self.forge(budget_stop=None, delivery_verdict="PASS", delivery_blocked_by=[])
        from aisef2.app import run as R
        (self.out / R.MANIFEST).write_text(json.dumps(R.evidence_manifest(self.out), indent=1, sort_keys=True) + "\n",
                                           encoding="utf-8")
        v = verify(self.project, self.out)     # a session that started and finished no step: unaccounted = a stop
        self.assertEqual((v["verdict"], v["delivery_verdict"]), ("REFUTED", "FAIL"), v)

    def test_a_rewritten_manifest_is_refuted_only_against_the_anchor_the_operator_kept(self):
        anchor = self.anchor
        # a consistent forgery: the reviewer's tokens lowered in its stream, the record's spend lowered to match, the
        # stop removed, the verdict raised, the manifest re-made — everything inside the run directory agrees
        log = sorted((self.out / "sessions").glob("*.reviewer.*.jsonl"))[0]
        text = log.read_text(encoding="utf-8")
        self.assertIn('"output": 7', text)
        log.write_text(text.replace('"output": 7', '"output": 0').replace('"reasoning": 3', '"reasoning": 0'), encoding="utf-8")
        spent = dict(self.rec["budget"]["spent"], output_tokens=self.rec["budget"]["spent"]["output_tokens"] - 10)
        self.forge(budget_stop=None, delivery_verdict="PASS", delivery_blocked_by=[],
                   budget=dict(self.rec["budget"], spent=spent))
        from aisef2.app import run as R
        (self.out / R.MANIFEST).write_text(json.dumps(R.evidence_manifest(self.out), indent=1, sort_keys=True) + "\n",
                                           encoding="utf-8")
        # without the anchor this is indistinguishable from a real run: verification proves consistency, nothing more
        self.assertEqual(verify(self.project, self.out)["verdict"], "VERIFIED")
        v = verify(self.project, self.out, expect_anchor=anchor)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertTrue(any("anchor" in p for p in v["problems"]), v["problems"])

    def test_the_untouched_run_verifies_against_its_anchor(self):
        self.assertRegex(self.anchor, r"^[0-9a-f]{64}$")
        v = verify(self.project, self.out, expect_anchor=self.anchor)
        self.assertEqual(v["verdict"], "VERIFIED", v)


if __name__ == "__main__":
    unittest.main()
