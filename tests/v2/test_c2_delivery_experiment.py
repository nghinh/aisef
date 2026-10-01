"""The preparation of DELIVERY EXPERIMENT 1 (owner ruling 'AISEF V2 — FINAL PLAN CORRECTION + DELIVERY RUN
PREREGISTRATION / NO PROVIDER CALL', 2026-10-02) — deterministic: no model, no provider, no LedgerLock repository,
nothing run:

  the plan       PLAN-V2.2 CORRECTION 1 is the accepted plan with the owner's eight obligations moved and nothing else;
                 it is admitted statically; a mapping the engine cannot admit is refused, not worked around.
  the prompts    a VERIFY obligation is named as one; the two removed stories have no task.
  the ceilings   a session stops at the turn cap, a run at its token ceilings, and nothing starts past them.
  the record     what the committed preregistration binds is what this tree holds.
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import ObligationRole, ParentExpectation  # noqa: E402
from aisef2.plan import static_admission as sa  # noqa: E402
from tests.v2 import test_c2_p9_harness as harness  # noqa: E402
from validation.qualification import c2_delivery_experiment as dx  # noqa: E402
from validation.qualification import c2_p9  # noqa: E402
from validation.qualification import c2_plan_correction as pc  # noqa: E402

OLD_HASH = "27b679d9513f3dc2f9b5da68a694a3ef1baff50f87eae9903721415a4670a669"
SPEC_DIGEST = "83a73da271805c470db4da55f50f542950494aa8b50a31e5b6f07e5364415745"
OC = {"declared_route": "9router/mycombo", "version": "1.18.31", "binary_sha256": "0" * 64}


def step(turn_input: int = 1000, output: int = 10, cache_read: int = 0, reasoning: int = 0) -> str:
    return json.dumps({"type": "step_finish", "part": {"tokens": {"input": turn_input, "output": output, "reasoning": reasoning,
                                                                  "cache": {"read": cache_read, "write": 0}}}}) + "\n"


class PlanCorrection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = pc.build()
        cls.rec = pc.record()

    def test_the_committed_record_is_what_this_tree_derives(self):
        self.assertEqual(pc.check(), [])
        self.assertEqual(self.rec["verdict"], "PLAN CORRECTION ADMITTED STATICALLY")

    def test_the_eight_obligations_are_where_the_owner_put_them(self):
        new = {o.criterion_id: o for o in self.b["new"].obligations}
        want = {"S-D3-05-01-1": ("STORY-04-02", ObligationRole.VERIFY, ParentExpectation.UNCONSTRAINED),
                "S-D3-05-01-2": ("STORY-04-01", ObligationRole.PRESERVE, ParentExpectation.SATISFIED_AT_PARENT)}
        want.update({o.criterion_id: ("STORY-01-05", ObligationRole.PRESERVE, ParentExpectation.SATISFIED_AT_PARENT)
                     for o in self.b["old"].obligations if o.story_id == "STORY-05-03"})
        self.assertEqual(len(want), 8)
        self.assertEqual(set(want), set(pc.DECISIONS))
        for c, (story, role, expected) in want.items():
            with self.subTest(criterion=c):
                self.assertEqual((new[c].story_id, new[c].role, new[c].expected_parent), (story, role, expected))
        graph = sa.story_graph(self.b["new"])
        self.assertTrue(sa.depends_on_story(graph, "STORY-04-01", "STORY-03-01"))      # decision 2
        self.assertTrue(sa.depends_on_story(graph, "STORY-01-05", "STORY-01-01"))      # decision 3

    def test_the_two_standalone_stories_are_gone_and_nothing_else_changed(self):
        old, new = self.b["old"], self.b["new"]
        self.assertEqual((old.plan_hash, len(old.obligations), len({o.story_id for o in old.obligations})), (OLD_HASH, 67, 9))
        self.assertEqual((len(new.obligations), len({o.story_id for o in new.obligations})), (67, 7))
        self.assertNotEqual(new.plan_hash, old.plan_hash)
        self.assertEqual({o.story_id for o in old.obligations} - {o.story_id for o in new.obligations}, {"STORY-05-01", "STORY-05-03"})
        was = {o.criterion_id: o for o in old.obligations}
        for o in new.obligations:
            if o.criterion_id not in pc.DECISIONS:
                self.assertEqual(o, was[o.criterion_id])
            self.assertEqual(o.product_proof_spec_id, was[o.criterion_id].product_proof_spec_id)

    def test_the_59_specs_and_what_they_cover_are_the_accepted_ones(self):
        p = self.rec["proofs"]
        s = p["product_proof_specs"]
        self.assertEqual((s["count"], s["all_equal_to_accepted"], s["semantic_hash_changes"], s["contract_spec_semantic_digest"]),
                         (59, True, [], SPEC_DIGEST))
        self.assertTrue(p["requirement_coverage"]["unchanged"])
        self.assertEqual(p["requirement_coverage"]["new"]["specs"], 59)
        self.assertTrue(p["introduce_uniqueness"]["introducing_story_of_each_spec_unchanged"])
        self.assertEqual(p["no_orphan_obligation"]["obligations_in_a_removed_story"], 0)
        self.assertEqual((p["dependency_dag"]["criterion_graph_cycle"], p["dependency_dag"]["story_graph_cycle"]), (None, None))

    def test_static_admission_is_nine_of_nine_and_needs_the_approvals(self):
        a = self.rec["static_admission"]
        self.assertEqual([c["passed"] for c in a["corrected_plan"]["checks"]], [True] * 9)
        self.assertTrue(a["accepted_plan"]["admitted"])
        self.assertFalse(a["corrected_plan_without_approvals"]["admitted"])

    def test_a_mapping_the_engine_cannot_admit_is_refused(self):
        # the six PRESERVEs put into the story that INTRODUCEs their specs: two parent expectations for one spec in one story
        wrong = {c: ("STORY-01-01", "PRESERVE", 3) for c, d in pc.DECISIONS.items() if d[2] == 3}
        with mock.patch.dict(pc.DECISIONS, wrong):
            b = pc.build()
        r = sa.StaticPlanAdmissionEngine().admit(b["new"], b["inputs"])
        self.assertFalse(r.admitted)
        self.assertEqual([c.name for c in r.checks if not c.passed], ["contradictions"])

    def test_a_record_that_claims_a_change_outside_the_decisions_has_a_problem(self):
        for path, value in ((("proofs", "requirement_coverage", "unchanged"), False),
                            (("proofs", "introduce_uniqueness", "introducing_story_of_each_spec_unchanged"), False),
                            (("proofs", "product_proof_specs", "semantic_hash_changes"), ["S-10-a"]),
                            (("proofs", "obligations_not_named_by_a_decision_unchanged"), False)):
            body = copy.deepcopy(self.rec)
            at = body
            for k in path[:-1]:
                at = at[k]
            at[path[-1]] = value
            with self.subTest(path=path):
                self.assertTrue(pc.problems(body))
        body = copy.deepcopy(self.rec)
        body["moved_obligations"][0]["to"]["story"] = "STORY-04-01"
        self.assertIn("S-D3-05-01-1: not what the owner decided", pc.problems(body))


class Prompts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = pc.corrected_plan()
        cls.tasks, _, cls.by_criterion = c2_p9.prompts(cls.plan, harness.epics(), harness.REQUIREMENTS)

    def test_seven_stories_have_a_task_and_the_removed_two_have_none(self):
        self.assertEqual(sorted(self.tasks), ["STORY-01-01", "STORY-01-05", "STORY-02-01", "STORY-02-02", "STORY-03-01", "STORY-04-01",
                                              "STORY-04-02"])
        for prompt in self.tasks.values():
            for token in harness.LEGACY_TOKENS:
                self.assertNotIn(token, prompt)

    def test_a_verify_obligation_is_named_as_one_only_where_there_is_one(self):
        self.assertTrue(self.by_criterion["S-D3-05-01-1"].startswith("- [VERIFY] R-3.3 "))
        for story, prompt in self.tasks.items():
            with self.subTest(story=story):
                self.assertEqual("VERIFY: it must be true when this story is done" in prompt, story == "STORY-04-02")
                self.assertEqual("[VERIFY]" in prompt, story == "STORY-04-02")

    def test_the_moved_preserves_are_in_their_new_story_s_task(self):
        self.assertIn(self.by_criterion["S-D3-05-01-2"], self.tasks["STORY-04-01"])
        for c in ("AC-STORY-05-03-1:S-10-a", "AC-STORY-05-03-2:S-12-c"):
            self.assertTrue(self.by_criterion[c].startswith("- [PRESERVE] "))
            self.assertIn(self.by_criterion[c], self.tasks["STORY-01-05"])
        self.assertIn("ledgerlock/ (the package directory)", self.tasks["STORY-01-05"])


class Ceilings(unittest.TestCase):
    def test_a_ceiling_is_reached_at_the_number_not_after_it(self):
        c = c2_p9.Ceiling(80, 1000, 100)
        self.assertIsNone(c.reached(79, {"input": 999, "output": 99}))
        self.assertEqual(c.reached(80, {"input": 0, "output": 0}), "max_turns: stopped at 80 turns (cap 80)")
        self.assertEqual(c.reached(1, {"input": 1000, "output": 0}), "max_input_tokens: 1000 of 1000 over the run")
        self.assertEqual(c.reached(1, {"input": 0, "output": 100}), "max_output_tokens: 100 of 100 over the run")
        c.used["input"] = 600
        self.assertEqual(c.reached(1, {"input": 400, "output": 0}), "max_input_tokens: 1000 of 1000 over the run")   # over the run
        self.assertFalse(c.exhausted)
        c.used["input"] = 1000
        self.assertTrue(c.exhausted)
        self.assertEqual(c.reached(), "max_input_tokens: 1000 of 1000 over the run")           # nothing may start

    def test_a_session_s_stream_counts_steps_cached_and_reasoning_tokens(self):
        with tempfile.TemporaryDirectory() as d:
            log = pathlib.Path(d) / "s.jsonl"
            log.write_text("not json\n" + step(1000, 10) + step(500, 5, cache_read=2000, reasoning=7) + '{"type": "text", "part": {"text": "ok"}}\n',
                           encoding="utf-8")
            self.assertEqual(c2_p9.read_session(log), {"error": None, "text": "ok", "turns": 2, "tokens": {"input": 3500, "output": 22}})

    def session(self, ceiling, lines_per_wait: str, exits_after: int | None = None):
        """`wait_within` over a range that writes `lines_per_wait` to the stream on every wait and never (or after n waits) exits."""
        test = self

        class Range:
            waits = 0

            def wait(self, timeout):
                test.assertLessEqual(timeout, c2_p9.POLL_S)
                Range.waits += 1
                with log.open("a", encoding="utf-8") as fh:
                    fh.write(lines_per_wait)
                return 0 if exits_after is not None and Range.waits >= exits_after else None
        with tempfile.TemporaryDirectory() as d:
            log = pathlib.Path(d) / "s.jsonl"
            log.write_text("", encoding="utf-8")
            return c2_p9.wait_within(Range(), log, 600.0, ceiling), Range.waits

    def test_a_running_session_is_stopped_at_the_turn_cap(self):
        (code, stopped), waits = self.session(c2_p9.Ceiling(80, 10**12, 10**12), step())
        self.assertEqual((code, stopped, waits), (None, "max_turns: stopped at 80 turns (cap 80)", 80))

    def test_a_running_session_is_stopped_at_the_run_s_token_ceiling(self):
        ceiling = c2_p9.Ceiling(80, 10_000, 10**12)
        ceiling.used["input"] = 7_000                                                         # earlier sessions of the run
        (code, stopped), waits = self.session(ceiling, step(1000))
        self.assertEqual((code, stopped, waits), (None, "max_input_tokens: 10000 of 10000 over the run", 3))

    def test_a_session_that_ends_under_the_ceilings_is_not_stopped(self):
        (code, stopped), waits = self.session(c2_p9.Ceiling(80, 10**12, 10**12), step(), exits_after=5)
        self.assertEqual((code, stopped, waits), (0, None, 5))

    def test_no_session_starts_at_a_spent_ceiling(self):
        ceiling = c2_p9.Ceiling(80, 1000, 100)
        ceiling.used["output"] = 100
        with tempfile.TemporaryDirectory() as d, mock.patch.object(c2_p9.shutil, "which", return_value=None):   # a start would fail on None
            s = c2_p9.opencode_session("developer S", "prompt", d, pathlib.Path(d) / "s.jsonl", 60.0, model="p/m", ceiling=ceiling)
        self.assertEqual((s["exit"], s["turns"], s["timed_out"]), (None, 0, False))
        self.assertEqual(s["error"], s["stopped"])                                             # the adapters answer the kernel with a provider refusal
        self.assertEqual(s["stopped"], "max_output_tokens: 100 of 100 over the run")
        self.assertEqual(ceiling.account()["stops"], [{"session": "developer S", "reason": s["stopped"], "started": False}])


class Preregistration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = json.loads((ROOT / dx.OUT_REL).read_text(encoding="utf-8"))
        cls.plan = pc.corrected_plan()

    def test_the_record_binds_what_this_tree_holds(self):
        r = self.rec
        self.assertEqual((r["verdict"], r["problems"]), ("PREREGISTERED — READY FOR AN OWNER DECISION; NOT AUTHORIZED", []))
        self.assertIs(r["run_authorized"], False)
        self.assertEqual(r["provider_calls_made_preparing_this"], 0)
        self.assertEqual(r["plan"]["plan_hash"], self.plan.plan_hash)
        self.assertEqual(r["plan"]["correction"]["sha256"], c2_p9.C.lf_sha(ROOT / pc.OUT_REL))
        self.assertEqual(r["kernel"]["tree"], c2_p9.C.git("rev-parse", "HEAD:aisef2"))
        self.assertEqual((r["kernel"]["commit"], r["harness"]["includes"]),
                         ("d427299376d7af48d3dd6d86242bf5def6a43003", "7630dbe5d0aa7f873e26a573ce2b9962bb0c72c2"))
        for f in r["harness"]["files"]:
            with self.subTest(file=f["path"]):
                self.assertEqual(f["sha256"], c2_p9.C.lf_sha(ROOT / f["path"]))
        self.assertIn(f"KT={r['kernel']['tree']}", (ROOT / "validation/qualification/c2_p9_run.sh").read_text(encoding="utf-8"))
        self.assertEqual((r["workload"]["start_sha"], r["workload"]["requirements_sha256"]), (self.plan.baseline, c2_p9.P10.REQUIREMENTS_SHA256))

    def test_three_developer_attempts_one_fixed_route_and_the_ceilings(self):
        r = self.rec
        self.assertEqual((r["profile"]["developer_attempts_per_story"], r["profile"]["limits"]["DEVELOPER"]), (3, 2))
        self.assertEqual(r["model"]["roles"], {"developer": dx.EXPERIMENT["route"], "reviewer": dx.EXPERIMENT["route"]})
        self.assertIs(r["model"]["dynamic_alias"], False)
        overlay = r["model"]["client_configuration_overlay"]
        self.assertEqual((overlay["model"], overlay["small_model"]), (dx.EXPERIMENT["route"],) * 2)
        self.assertNotIn("mycombo", json.dumps([r["capabilities"], r["runspec_settings"], overlay]))
        dev = next(c for c in r["capabilities"] if c["name"] == "developer")
        self.assertEqual((dev["binding"]["route"], dev["binding"]["resolved_model"], dev["binding"]["route_kind"], dev["grade"], dev["enforcement"]),
                         (dx.EXPERIMENT["route"], "deepseek-v4-pro", "FIXED_MODEL", "OPAQUE", "PARTIAL"))
        self.assertEqual({k: v["value"] for k, v in r["runspec_settings"].items() if k.startswith("max_")},
                         {k: dx.EXPERIMENT[k] for k in ("max_turns", "max_input_tokens", "max_output_tokens")})
        self.assertEqual(r["runspec_settings"]["plan_hash"]["value"], self.plan.plan_hash)
        self.assertRegex(r["runspec_hash"], r"^[0-9a-f]{64}$")

    def test_the_runspec_hash_binds_the_route_the_ceilings_the_plan_and_the_kernel_commit(self):
        from aisef2.runtime.runspec import resolve

        def h(**change) -> str:
            caps, layers, _ = c2_p9.runspec_inputs(self.plan, c2_p9.EXPERIMENT, OC, {**dx.fixed(), **change})
            return resolve(caps, layers, self.plan.baseline).runspec_hash
        base = h()
        self.assertEqual(base, h())
        for change in ({"route": "9router/mycombo"}, {"resolved_model": "other"}, {"max_turns": 81}, {"max_input_tokens": 1},
                       {"max_output_tokens": 1}, {"kernel_commit": "0" * 40}):
            with self.subTest(change=change):
                self.assertNotEqual(h(**change), base)
        caps, layers, _ = c2_p9.runspec_inputs(pc.build()["old"], c2_p9.EXPERIMENT, OC, dx.fixed())
        self.assertNotEqual(resolve(caps, layers, self.plan.baseline).runspec_hash, base)

    def test_a_run_under_the_profile_is_the_preregistered_attempt_only(self):
        with self.assertRaises(SystemExit) as x:
            c2_p9.main(["--run", "--attempt", "4", "--profile", c2_p9.EXPERIMENT])
        self.assertIn("preregistered as attempt 3 only", str(x.exception))

    def test_a_preflight_must_show_the_preregistered_model_on_the_fixed_route(self):
        good = {"pass": True, "route": dx.EXPERIMENT["route"],
                "summary_for_identity": {"route_kind": "FIXED_MODEL", "resolved_model": "deepseek-v4-pro"}}
        self.assertEqual(dx.preflight_problems(good), [])
        for change in ({"pass": False}, {"route": "9router/mycombo"},
                       {"summary_for_identity": {"route_kind": "DYNAMIC_COMBO", "resolved_model": "deepseek-v4-pro"}},
                       {"summary_for_identity": {"route_kind": "FIXED_MODEL", "resolved_model": "MiniMax-M3"}},
                       {"summary_for_identity": {"route_kind": "FIXED_MODEL", "resolved_model": ["a", "b"]}}):
            with self.subTest(change=change):
                self.assertTrue(dx.preflight_problems({**good, **change}))

    def test_the_oracle_s_outcomes_are_reconciled_with_its_own_totals(self):
        out = ("test_oracle.py::TestAcceptance::test_a PASSED [ 50%]\ntest_oracle.py::TestAcceptance::test_b FAILED [100%]\n"
               "=========== 1 failed, 1 passed in 0.10s ===========\n")
        self.assertEqual(dx.parse_oracle(out), {"results": {"TestAcceptance::test_a": "PASSED", "TestAcceptance::test_b": "FAILED"},
                                                "total": 2, "passed": 1, "not_passed": ["TestAcceptance::test_b"], "complete": True})
        self.assertFalse(dx.parse_oracle(out.replace("1 failed, 1 passed", "1 failed, 2 passed"))["complete"])
        self.assertFalse(dx.parse_oracle("")["complete"])

    def test_readiness_was_measured_on_reference_implementations(self):
        ready = self.rec["final_evaluation"]["readiness_measured_without_a_provider"]
        self.assertEqual(ready["v2_final_proof_on_the_p5_reference_fixture"], {"total": 59, "satisfied": 59, "not_satisfied": []})
        v = ready["v1_oracle_on_its_calibration_reference"]
        self.assertEqual((v["total"], v["passed"], v["complete"]), (9, 9, True))
        self.assertTrue(self.rec["final_evaluation"]["v1_oracle"]["unchanged_since_calibration"])


class RunRecord(unittest.TestCase):
    """What the run's record says of a run that stopped early (no model: the measurement is made up here)."""

    def record(self, events: list[dict], results: dict) -> dict:
        plan = pc.corrected_plan()
        caps, layers, kernel = c2_p9.runspec_inputs(plan, c2_p9.EXPERIMENT, OC, dx.fixed())
        exp = {**dx.fixed(), "plan": plan, "authority": dx.AUTHORITY, "preregistration": {"path": dx.OUT_REL},
               "plan_correction": {"path": pc.OUT_REL}}
        m = {"started": 0.0, "results": results, "errors": [], "events": events, "state": {}, "run_identity": {}, "final_main": "f" * 40,
             "preserved": {}, "profile": c2_p9.EXPERIMENT, "experiment": exp, "ceiling": c2_p9.Ceiling(80, 1, 1).account(),
             "baseline": {"baseline": plan.baseline}, "oc": OC, "plan": plan, "specs": {s.id: s for s in c2_p9._compiled().values()},
             "tasks": {}, "sessions": [], "caps": caps, "layers": layers, "kernel": kernel}
        with tempfile.TemporaryDirectory() as d:
            return c2_p9.record(pathlib.Path(d), m)

    def test_a_run_stopped_after_its_committed_stories_is_not_a_delivery_pass(self):
        events = [{"seq": 1, "type": "gate/decision", "data": {"story_id": "STORY-01-01"}},
                  {"seq": 2, "type": "story/commit", "data": {"story_id": "STORY-01-01", "revision": "a" * 40}}]
        self.assertEqual(c2_p9.P10.delivery_verdict_of(events, plan_admitted=True), "PASS")     # the journal alone: every story IN IT committed
        stories = c2_p9.order(pc.corrected_plan(), pc.build()["graph"])
        results = {"STORY-01-01": ["COMMIT"], **{s: ["NOT_RUN: the run's token ceiling was reached"] for s in stories[1:]}}
        rec = self.record(events, results)
        self.assertEqual(rec["delivery_verdict"], "FAIL")
        self.assertEqual(rec["stories_not_committed"], stories[1:])
        self.assertEqual((rec["semantic_candidate"], rec["aisef2_tree"]), (dx.EXPERIMENT["kernel_commit"], dx.EXPERIMENT["kernel_tree"]))
        self.assertEqual(rec["plan_identity"]["plan_hash"], pc.corrected_plan().plan_hash)
        self.assertEqual(rec["execution_profile"]["fixed_model"], {"route": dx.EXPERIMENT["route"], "resolved_model": "deepseek-v4-pro",
                                                                  "route_kind": "FIXED_MODEL"})
        self.assertEqual(rec["execution_profile"]["developer_attempts_per_story"], 3)

    def test_every_story_committed_is_a_pass(self):
        stories = c2_p9.order(pc.corrected_plan(), pc.build()["graph"])
        events = [{"seq": n, "type": t, "data": {"story_id": s, "revision": "a" * 40}}
                  for n, (s, t) in enumerate((s, t) for s in stories for t in ("gate/decision", "story/commit"))]
        rec = self.record(events, {s: ["COMMIT"] for s in stories})
        self.assertEqual((rec["delivery_verdict"], rec["stories_not_committed"]), ("PASS", []))


if __name__ == "__main__":
    unittest.main()
