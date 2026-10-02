"""The preparation of DELIVERY EXPERIMENT 1 (owner ruling 'AISEF V2 — FINAL PLAN CORRECTION + DELIVERY RUN
PREREGISTRATION / NO PROVIDER CALL', 2026-10-02) — deterministic: no model, no provider, no LedgerLock repository,
nothing run:

  the plan       PLAN-V2.2 CORRECTION 1 is the accepted plan with the owner's eight obligations moved and nothing else;
                 it is admitted statically; a mapping the engine cannot admit is refused, not worked around.
  the prompts    a VERIFY obligation is named as one; the two removed stories have no task.
  the budget     the owner's four hard ceilings, re-derived from the evidence; a ceiling reached or spend unaccounted
                 ends the experiment and nothing starts afterwards.
  the preflight  five accounted requests at most; one stable expected identity is ATTESTED, anything else is refused.
  the gate       the runner itself refuses without a verified attestation — and reaches no provider when it refuses.
  the verdict    PASS only when every story committed in the journal, within the budget, with everything preserved.
  the record     what the committed preregistration binds is what this tree holds.
"""

from __future__ import annotations

import copy
import json
import pathlib
import re
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
#: a client identity made up here, so nothing below depends on the machine: no OpenCode, no LedgerLock repository
OC = {"declared_route": "9router/mycombo", "version": "1.18.31", "binary_sha256": "0" * 64, "routing_config_digest": "1" * 64,
      "endpoint": "https://9router.vnteki.com/v1"}
ZERO = {"provider_requests": 0, "turns": 0, "input_tokens": 0, "output_tokens": 0}
BIG = {"provider_requests": 10**9, "turns": 10**9, "input_tokens": 10**15, "output_tokens": 10**15}
NOW = 1_800_000_000.0


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


def step(turn_input: int = 1000, output: int = 10, cache_read: int = 0, reasoning: int = 0) -> str:
    return json.dumps({"type": "step_finish", "part": {"tokens": {"input": turn_input, "output": output, "reasoning": reasoning,
                                                                  "cache": {"read": cache_read, "write": 0}}}}) + "\n"


def requests(n: int) -> list[dict]:
    return [{"type": "provider/request", "data": {"story_id": "S"}}] * n


class Evidence(unittest.TestCase):
    """A temporary attempt directory: the session streams, the journal's events and the preflight's accounting."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)
        self.logs = self.dir / c2_p9.SESSIONS
        self.logs.mkdir()
        self.events: list[dict] = []

    def budget(self, base=None, **limits) -> c2_p9.Budget:
        return c2_p9.Budget({**BIG, **limits}, base or ZERO, self.logs, lambda: sum(1 for e in self.events if e["type"] == "provider/request"))

    def session(self, name: str, text: str) -> pathlib.Path:
        self.events += requests(1)
        (self.logs / name).write_text(text, encoding="utf-8")
        return self.logs / name


class BudgetFromEvidence(Evidence):
    def test_spend_is_what_the_preflight_the_journal_and_the_streams_show_and_nothing_else(self):
        b = self.budget(base={"provider_requests": 5, "turns": 3, "input_tokens": 9000, "output_tokens": 90})
        self.assertEqual({k: b.spend()[k] for k in b.KEYS}, {"provider_requests": 5, "turns": 3, "input_tokens": 9000, "output_tokens": 90})
        self.session("S.developer.1.jsonl", step(1000, 10) + step(500, 5, cache_read=2000, reasoning=7))
        self.session("S.reviewer.1.jsonl", step(100, 1))
        want = {"provider_requests": 7, "turns": 6, "input_tokens": 12600, "output_tokens": 113}
        self.assertEqual({k: b.spend()[k] for k in b.KEYS}, want)
        self.assertEqual(b.spend()["unaccounted"], [])
        self.assertFalse([k for k in vars(b) if k not in ("limits", "base", "logs", "requests")])     # it holds no count of its own
        again = self.budget(base=b.base)                                                               # another object, the same evidence
        self.assertEqual(again.spend(), b.spend())
        self.assertEqual(b.account()["spent"], b.spend())

    def test_each_ceiling_ends_the_experiment_when_reached_or_exceeded(self):
        self.session("S.developer.1.jsonl", step(1000, 10) * 3)
        for limits, why in (({"turns": 4}, None), ({"turns": 3}, "max_turns: 3 of 3"), ({"turns": 2}, "max_turns: 3 of 2"),
                            ({"input_tokens": 3001}, None), ({"input_tokens": 3000}, "max_input_tokens: 3000 of 3000"),
                            ({"output_tokens": 31}, None), ({"output_tokens": 30}, "max_output_tokens: 30 of 30"),
                            ({"provider_requests": 2}, None), ({"provider_requests": 1}, "max_provider_requests: 1 of 1")):
            with self.subTest(limits=limits):
                self.assertEqual(self.budget(**limits).reached(), why)

    def test_the_request_that_reaches_the_request_ceiling_may_run_and_nothing_after_it(self):
        b = self.budget(base={**ZERO, "provider_requests": 5}, provider_requests=60)       # the preflight's five are in the sixty
        self.events += requests(55)                                                         # the journal records the 60th request
        self.assertIsNone(b.reached(in_progress=True))                                      # it may run
        self.assertEqual(b.reached(), "max_provider_requests: 60 of 60")                    # once it is over, the experiment has ended
        self.events += requests(1)
        self.assertEqual(b.reached(in_progress=True), "max_provider_requests: 61 of 60")    # the 61st never starts

    def test_spend_that_cannot_be_accounted_for_ends_the_experiment(self):
        (self.logs / "ghost.jsonl").write_text(step(), encoding="utf-8")                   # a session the journal does not record
        self.assertEqual(self.budget().reached(), "unaccounted: 1 sessions were started but 0 provider requests are recorded")
        self.events += requests(1)
        self.assertIsNone(self.budget().reached())
        blind = self.session("S.developer.1.jsonl", '{"type": "step_finish", "part": {}}\n')
        self.assertIn("S.developer.1.jsonl: 1 finished steps report no tokens", self.budget().reached())
        blind.write_text(step(), encoding="utf-8")
        empty = self.session("S.reviewer.1.jsonl", "")
        self.assertIn("S.reviewer.1.jsonl: a session that started finished no step", self.budget().reached())
        self.assertIsNone(self.budget().reached(empty, in_progress=True))                   # a running session may have no step yet

    def test_a_stream_counts_steps_cached_and_reasoning_tokens(self):
        log = self.session("s.jsonl", "not json\n" + step(1000, 10) + step(500, 5, cache_read=2000, reasoning=7)
                           + '{"type": "text", "part": {"text": "ok"}}\n')
        self.assertEqual(c2_p9.read_session(log), {"error": None, "text": "ok", "turns": 2, "tokens": {"input": 3500, "output": 22},
                                                   "steps_without_tokens": 0})

    def running(self, budget, lines_per_wait: str, exits_after: int | None = None, turn_cap: int | None = None):
        """`wait_within` over a range that writes `lines_per_wait` to its stream on every wait and never (or after n) exits."""
        test, log = self, self.session("S.developer.1.jsonl", "")

        class Range:
            waits = 0

            def wait(self, timeout):
                test.assertLessEqual(timeout, c2_p9.POLL_S)
                Range.waits += 1
                with log.open("a", encoding="utf-8") as fh:
                    fh.write(lines_per_wait)
                return 0 if exits_after is not None and Range.waits >= exits_after else None
        return c2_p9.wait_within(Range(), log, 600.0, budget, turn_cap), Range.waits

    def test_a_running_session_is_stopped_when_the_global_turn_ceiling_is_reached(self):
        (self.logs / "S0.developer.1.jsonl").write_text(step() * 690, encoding="utf-8")     # earlier sessions of the experiment
        self.events += requests(1)
        (code, stopped), waits = self.running(self.budget(turns=dx.EXPERIMENT["budget"]["turns"]), step(), turn_cap=80)
        self.assertEqual((code, stopped, waits), (None, "max_turns: 700 of 700", 10))       # the experiment's ceiling, before the session's cap

    def test_a_running_session_is_stopped_at_the_token_ceilings(self):
        (code, stopped), waits = self.running(self.budget(base={**ZERO, "input_tokens": 7000}, input_tokens=10_000), step(1000))
        self.assertEqual((code, stopped, waits), (None, "max_input_tokens: 10000 of 10000", 3))

    def test_a_session_that_ends_under_the_budget_is_not_stopped(self):
        (code, stopped), waits = self.running(self.budget(), step(), exits_after=5)
        self.assertEqual((code, stopped, waits), (0, None, 5))

    def test_a_session_at_its_own_turn_cap_is_stopped_and_the_experiment_goes_on(self):
        b = self.budget(**dx.EXPERIMENT["budget"])
        (code, stopped), waits = self.running(b, step(), turn_cap=dx.EXPERIMENT["max_turns_per_session"])
        self.assertEqual((code, stopped, waits), (None, "session turn cap: 80 turns", 80))
        self.assertIsNone(b.reached())                                                      # no experiment ceiling was reached by it
        self.assertEqual(b.spend()["turns"], 80)                                            # and its turns are in the experiment's total

    def test_the_smoke_probe_has_its_own_turn_cap(self):
        (code, stopped), waits = self.running(self.budget(), step(), turn_cap=10)
        self.assertEqual((code, stopped, waits), (None, "session turn cap: 10 turns", 10))

    def test_no_session_starts_once_the_budget_is_reached_and_none_overwrites_evidence(self):
        self.session("S.developer.1.jsonl", step(output=100))
        b = self.budget(output_tokens=100)
        self.events += requests(1)                                                          # the kernel journaled the next request
        with mock.patch.object(c2_p9.shutil, "which", return_value=None):                   # a start would fail on None
            s = c2_p9.opencode_session("reviewer S", "prompt", str(self.dir), self.logs / "S.reviewer.1.jsonl", 60.0, model="p/m", budget=b)
            again = c2_p9.opencode_session("developer S", "prompt", str(self.dir), self.logs / "S.developer.1.jsonl", 60.0, model="p/m",
                                           budget=self.budget())
        self.assertEqual((s["started"], s["exit"], s["turns"], s["timed_out"], s["log"]), (False, None, 0, False, None))
        self.assertEqual(s["error"], s["stopped"])                           # the adapters answer the kernel with a provider refusal
        self.assertEqual(s["stopped"], "max_output_tokens: 100 of 100")
        self.assertFalse((self.logs / "S.reviewer.1.jsonl").exists())        # a session that did not start leaves no stream
        self.assertEqual((again["started"], again["stopped"]), (False, "S.developer.1.jsonl exists: a session's evidence is never overwritten"))

    def test_the_experiment_s_budget_is_the_owner_s(self):
        self.assertEqual(dx.EXPERIMENT["budget"], {"provider_requests": 60, "turns": 700, "input_tokens": 60_000_000, "output_tokens": 400_000})
        self.assertEqual(dx.EXPERIMENT["max_turns_per_session"], 80)
        shape = dx.EXPERIMENT["preflight_shape"]
        self.assertEqual((shape["smokes"], shape["smoke_max_turns"], shape["smoke_timeout_s"]), (1, 10, 300.0))
        self.assertEqual(sorted(dx.EXPERIMENT["budget"]), sorted(c2_p9.Budget.KEYS))
        with self.assertRaises(ValueError):
            c2_p9.Budget({"turns": 1}, ZERO, self.logs)


class Provider:
    """The router, faked: its model listing and its chat completions. Every call is recorded; nothing leaves the process."""

    def __init__(self, owner="ds", models=("deepseek-v4-pro",) * 3, usage=True, http=200, breaks_at=None, system_fingerprints=None):
        self.owner, self.models, self.usage, self.http, self.breaks_at, self.calls = owner, models, usage, http, breaks_at, []
        self.system_fingerprints = system_fingerprints

    def __call__(self, path, body=None):
        self.calls.append(path)
        if self.breaks_at == len(self.calls):
            raise RuntimeError("the connection dropped")
        if path == "/models":
            return 200, {"data": [{"id": "ds/deepseek-v4-pro", "object": "model", "owned_by": self.owner}, {"id": "mycombo", "owned_by": "combo"}]}
        i = sum(1 for c in self.calls if c == "/chat/completions") - 1
        return self.http, {"model": self.models[i], "object": "chat.completion",
                           **({"system_fingerprint": self.system_fingerprints[i]} if self.system_fingerprints else {}),
                           "usage": {"prompt_tokens": 2090, "completion_tokens": 12, "total_tokens": 2102} if self.usage else None}


def smoke(steps: int = 3, **over):
    """The smoke session, faked: it leaves its stream where the real one does and reports what the real one reports."""
    def run(pre, i, budget):
        run.calls += 1
        (pre / c2_p9.SESSIONS / f"smoke.{i}.jsonl").write_text(step(12_000, 40) * steps, encoding="utf-8")
        return {**dx.OK_SMOKE, "stopped": None, "timed_out": False, "started": True, "turns": steps, **over}
    run.calls = 0
    return run


class Attempt(unittest.TestCase):
    """A temporary attempt directory and a preregistration that binds this process's own machine-independent identity."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.attempt = pathlib.Path(tmp.name) / "attempt-3"
        self.attempt.mkdir()
        self.prereg = {"runspec_template_hash": dx.runspec(OC).runspec_hash, "note": "the fields the gate reads of a preregistration"}

    def attest(self, provider=None, smoke_=None, at=NOW):
        self.provider, self.smoke = provider or Provider(), smoke_ or smoke()
        return dx.attest(self.attempt, oc=OC, prereg=self.prereg, transport=self.provider, smoke=self.smoke, now=lambda: at)

    def gate(self, now=NOW + 60) -> list[str]:
        return dx.gate_problems(self.attempt, self.prereg, OC, now)

    def tamper(self, change) -> None:
        path = self.attempt / dx.ATTESTATION
        att = json.loads(path.read_text(encoding="utf-8"))
        change(att)
        path.write_text(json.dumps(att), encoding="utf-8")


class Preflight(Attempt):
    def test_a_stable_expected_identity_is_attested_in_five_accounted_requests(self):
        rec = self.attest()
        self.assertEqual((rec["verdict"], rec["problems"], rec["identity_grade"]), ("ATTESTED", [], "ATTESTED"))
        self.assertEqual(self.provider.calls, ["/models"] + ["/chat/completions"] * 3)
        self.assertEqual(self.smoke.calls, 1)
        self.assertEqual(rec["accounting"], {"provider_requests": 5, "turns": 3, "input_tokens": 3 * 2090 + 3 * 12_000,
                                             "output_tokens": 3 * 12 + 3 * 40, "unaccounted": []})
        rows = dx.ledger_rows(self.attempt / dx.PREFLIGHT_DIR)
        self.assertEqual([(r["n"], r["event"], r.get("kind")) for r in rows],
                         [(n, e, k if e == "sent" else None) for n, k in enumerate(["listing", "chat", "chat", "chat", "smoke"], 1) for e in ("sent", "done")])
        for name in ("developer", "reviewer"):
            cap = rec["capabilities"][name]
            self.assertEqual((cap["grade"], cap["enforcement"]), ("ATTESTED", "PARTIAL"))
            self.assertEqual({k: v for k, v in cap["binding"].items() if k != "fingerprint"}, dx.allowed_identity(OC))
            self.assertRegex(cap["binding"]["fingerprint"], r"^[0-9a-f]{64}$")
        self.assertEqual(sorted(rec["capabilities"]["developer"]["binding"]), ["client", "declared_model", "endpoint", "fingerprint", "provider", "route"])
        self.assertEqual(rec["deployment_identity"], "NOT_EXPOSED")                     # this provider exposed none: none is bound
        self.assertEqual(rec["resolved_runspec_hash"], dx.runspec(OC, rec["fingerprint_fields"]).runspec_hash)
        self.assertEqual(self.gate(), [])                                               # and it unlocks delivery

    def test_the_fingerprint_binds_the_observable_fields_and_no_time_or_token_count(self):
        a = self.attest()["fingerprint_fields"]
        self.assertEqual(a["declared_models"], ["deepseek-v4-pro"])
        self.assertEqual((a["route"], a["listing"]["owned_by"], a["limits_declared_to_the_client"]),
                         (dx.EXPERIMENT["route"], "ds", dx.EXPERIMENT["model_limit"]))
        self.assertEqual(a["response"]["usage_fields"], ["completion_tokens", "prompt_tokens", "total_tokens"])
        self.assertEqual(a["tool_calling"], [dx.OK_SMOKE])
        self.assertNotIn("2090", json.dumps(a))
        other = Attempt()
        other.setUp()
        self.addCleanup(other.doCleanups)
        b = other.attest(smoke_=smoke(steps=7), at=NOW + 86_400)["fingerprint_fields"]  # another day, another number of turns
        self.assertEqual(a, b)

    def test_a_deployment_identity_is_bound_only_when_the_provider_exposes_one_stable_value(self):
        rec = self.attest(Provider(system_fingerprints=("fp_44709d6fcb",) * 3))
        self.assertEqual((rec["verdict"], rec["deployment_identity"]), ("ATTESTED", "system_fingerprint:fp_44709d6fcb"))
        self.assertEqual(rec["capabilities"]["developer"]["binding"]["deployment"], "system_fingerprint:fp_44709d6fcb")
        self.assertEqual(rec["resolved_runspec_hash"], dx.runspec(OC, rec["fingerprint_fields"], "system_fingerprint:fp_44709d6fcb").runspec_hash)
        self.assertNotEqual(rec["resolved_runspec_hash"], dx.runspec(OC, rec["fingerprint_fields"]).runspec_hash)
        self.assertEqual(rec["runspec_template_hash"], dx.runspec(OC).runspec_hash)      # the template never carries one
        self.assertEqual(self.gate(), [])
        self.tamper(lambda att: att.update(deployment_identity="NOT_EXPOSED"))
        self.assertIn("the deployment identity recorded is not what the observation exposes", self.gate())
        other = self._fresh()
        rec = Attempt.attest(other, Provider(system_fingerprints=("fp_a", "fp_b", "fp_a")))
        self.assertEqual((rec["verdict"], rec["deployment_identity"]), ("ATTESTED", "EXPOSED_NOT_STABLE:2_values"))
        self.assertNotIn("deployment", rec["capabilities"]["developer"]["binding"])      # not one stable value: none is bound, none made up
        self.assertEqual(rec["fingerprint_fields"]["response"]["system_fingerprint"], ["fp_a", "fp_b"])   # the fingerprint still binds what was seen
        self.assertEqual(other.gate(), [])

    def test_another_model_answering_is_not_attested_and_the_preflight_stops_at_once(self):
        rec = self.attest(Provider(models=("MiniMax-M3",) * 3))
        self.assertEqual((rec["verdict"], rec["identity_grade"], rec["capabilities"], rec["resolved_runspec_hash"]), (dx.CANNOT, "OPAQUE", {}, None))
        self.assertIn("answered by MiniMax-M3, not deepseek-v4-pro", rec["problems"])
        self.assertEqual((self.provider.calls, self.smoke.calls), (["/models", "/chat/completions"], 0))     # no further probe, no smoke
        self.assertEqual(rec["accounting"]["provider_requests"], 2)
        self.assertTrue(self.gate())

    def test_a_model_identity_that_is_not_stable_is_not_attested(self):
        rec = self.attest(Provider(models=("deepseek-v4-pro", "deepseek-v4", "deepseek-v4-pro")))
        self.assertEqual(rec["verdict"], dx.CANNOT)
        self.assertEqual((len(self.provider.calls), self.smoke.calls), (3, 0))
        rec = Attempt.attest(self._fresh(), Provider(models=(None, None, None)))
        self.assertEqual(rec["verdict"], dx.CANNOT)

    def _fresh(self):
        other = Attempt()
        other.setUp()
        self.addCleanup(other.doCleanups)
        return other

    def test_a_routing_alias_is_not_attested_and_no_model_call_is_made(self):
        rec = self.attest(Provider(owner="combo"))
        self.assertEqual((rec["verdict"], self.provider.calls, self.smoke.calls), (dx.CANNOT, ["/models"], 0))

    def test_a_smoke_whose_tool_calling_fails_refuses_without_relabelling(self):
        rec = self.attest(smoke_=smoke(file_written=False))
        self.assertEqual((rec["verdict"], rec["identity_grade"]), ("REFUSED", "OPAQUE"))
        self.assertTrue(self.gate())

    def test_a_request_that_cannot_be_accounted_for_locks_delivery(self):
        rec = self.attest(Provider(usage=False))
        self.assertEqual(rec["verdict"], "REFUSED")
        self.assertIn("unaccounted: request 2 (chat) reports no usage", rec["problems"])
        self.assertEqual((self.provider.calls, self.smoke.calls), (["/models", "/chat/completions"], 0))     # nothing is sent after it
        rec = Attempt.attest(self._fresh(), smoke_=smoke(steps=0))
        self.assertIn("unaccounted: request 5 (smoke) finished 0 steps, 0 without tokens", rec["problems"])
        broke = self._fresh()
        rec = Attempt.attest(broke, Provider(breaks_at=3))
        self.assertEqual(rec["verdict"], "REFUSED")
        self.assertIn("unaccounted: request 3 (chat) was sent and has no result", rec["problems"])
        self.assertTrue(broke.gate())

    def test_a_preflight_is_made_once(self):
        self.attest(Provider(models=("MiniMax-M3",) * 3))
        again = Provider()
        with self.assertRaises(SystemExit) as x:
            dx.attest(self.attempt, oc=OC, prereg=self.prereg, transport=again, smoke=smoke())
        self.assertIn("already holds a preflight", str(x.exception))
        self.assertEqual(again.calls, [])                                               # refused before any request

    def test_the_preflight_s_spend_is_the_base_of_the_experiment_s_budget(self):
        rec = self.attest()
        logs = self.attempt / c2_p9.SESSIONS
        b = c2_p9.Budget(dx.EXPERIMENT["budget"], rec["accounting"], logs, lambda: 0)
        self.assertEqual({k: b.spend()[k] for k in b.KEYS}, {k: rec["accounting"][k] for k in b.KEYS})
        self.assertIsNone(b.reached())


class Gate(Attempt):
    """The runner's own gate (ruling §5): each of these is REFUSED, and none can make a provider call — the gate has
    no transport, and the runner reaches nothing else before it."""

    def setUp(self):
        super().setUp()
        self.attest()
        self.assertEqual(self.gate(), [])

    def assertRefused(self, *needles: str, now=NOW + 60) -> None:
        found = self.gate(now)
        self.assertTrue(found)
        for needle in needles:
            self.assertTrue(any(needle in p for p in found), (needle, found))

    def test_no_attestation_record(self):
        empty = self._other()
        self.assertEqual(dx.gate_problems(empty, self.prereg, OC, NOW), ["no attestation record at ATTESTATION.json: the provider preflight has not "
                                                                         "unlocked delivery"])

    def _other(self) -> pathlib.Path:
        d = self.attempt.parent / "empty"
        d.mkdir()
        return d

    def test_an_opaque_identity(self):
        def opaque(att):
            att["identity_grade"] = "OPAQUE"
            for cap in att["capabilities"].values():
                cap["grade"] = "OPAQUE"
        self.tamper(opaque)
        self.assertRefused("developer is OPAQUE, not ATTESTED", "the model identity grade is OPAQUE")

    def test_the_wrong_model(self):
        def wrong(att):
            for p in att["observation"]["probes"]:
                p["model"] = "MiniMax-M3"
        self.tamper(wrong)
        self.assertRefused("observed: answered by MiniMax-M3, not deepseek-v4-pro")
        self.setUp()
        self.tamper(lambda att: att["capabilities"]["developer"]["binding"].update(declared_model="MiniMax-M3"))
        self.assertRefused("developer's attested tuple is not the one this preregistration and observation give: ['declared_model']")

    def test_the_wrong_route(self):
        self.tamper(lambda att: att["observation"].update(route="9router/mycombo"))
        self.assertRefused("observed: route 9router/mycombo: not the fixed route")
        self.setUp()
        self.tamper(lambda att: att.update(route="9router/mycombo"))
        self.assertRefused("bound to another route, model or client")

    def test_the_wrong_runspec(self):
        self.tamper(lambda att: att.update(resolved_runspec_hash="0" * 64))
        self.assertRefused("the resolved RunSpec hash is not the one the attested tuple gives")
        self.setUp()
        self.tamper(lambda att: att.update(runspec_template_hash="0" * 64))
        self.assertRefused("the RunSpec template is not the preregistered one")
        self.setUp()
        self.prereg = {**self.prereg, "runspec_template_hash": "0" * 64}                 # a preregistration with other settings
        self.assertRefused("the RunSpec template is not the preregistered one", "bound to another preregistration")

    def test_a_stale_attestation_or_another_experiment_s(self):
        self.assertRefused("the attestation is stale", now=NOW + dx.EXPERIMENT["attestation_max_age_s"] + 1)
        self.assertRefused("the attestation is stale", now=NOW - 1)                      # made after this run began: not this run's
        self.tamper(lambda att: att["experiment"].update(attempt=2))
        self.assertRefused("not of this experiment and attempt")
        self.setUp()
        self.tamper(lambda att: att["preregistration"].update(sha256="0" * 64))
        self.assertRefused("bound to another preregistration")
        self.setUp()
        self.tamper(lambda att: att.update(plan_hash=OLD_HASH))
        self.assertRefused("bound to another plan or kernel")
        self.setUp()
        self.tamper(lambda att: att.update(enforcement_identity="0" * 64))
        self.assertRefused("bound to another enforcement identity")
        self.setUp()
        self.tamper(lambda att: att.update(client="opencode 9.9.9"))
        self.assertRefused("bound to another route, model or client")

    def test_an_altered_fingerprint(self):
        self.tamper(lambda att: att["capabilities"]["reviewer"]["binding"].update(fingerprint="0" * 64))
        self.assertRefused("reviewer's attested tuple is not the one this preregistration and observation give: ['fingerprint']")
        self.setUp()
        self.tamper(lambda att: att["fingerprint_fields"].update(declared_models=["other"]))
        self.assertRefused("the fingerprinted fields are not what the observation shows")
        self.setUp()
        self.tamper(lambda att: att["observation"]["smokes"][0].update(shell_tool_called=False))     # the observation behind the fingerprint
        self.assertRefused("observed: smoke 1: tool calling did not behave")

    def test_a_preflight_whose_requests_its_ledger_does_not_account_for(self):
        ledger = self.attempt / dx.PREFLIGHT_DIR / dx.LEDGER
        ledger.write_text("".join(ledger.read_text(encoding="utf-8").splitlines(keepends=True)[:-1]), encoding="utf-8")
        self.assertRefused("the preflight's requests are not accounted for by its ledger")
        self.setUp()
        self.tamper(lambda att: att["accounting"].update(input_tokens=1))
        self.assertRefused("the record and the ledger differ")

    def test_the_runner_itself_refuses_and_reaches_no_provider(self):
        explode = mock.Mock(side_effect=AssertionError("reached past the gate"))
        cases = {"no record": lambda: self._other(), "opaque": lambda: (self.tamper(lambda a: a.update(identity_grade="OPAQUE")), self.attempt)[1]}
        for name, make in cases.items():
            self.setUp()
            where = make()
            with self.subTest(case=name), mock.patch.object(dx, "check", return_value=[]), mock.patch.object(dx, "machine", return_value=OC), \
                    mock.patch.object(dx, "committed", return_value=self.prereg), mock.patch.object(dx.time, "time", return_value=NOW + 60), \
                    mock.patch.object(c2_p9, "opencode_session", explode), mock.patch.object(c2_p9.P10, "ledgerlock_baseline", explode), \
                    mock.patch.object(c2_p9.P10, "opencode_identity", explode), mock.patch.object(dx, "default_transport", explode):
                with self.assertRaises(SystemExit) as x:
                    c2_p9.run(where, preserve_to=where / "kept.git", profile=c2_p9.EXPERIMENT)
                self.assertTrue(str(x.exception).startswith("REFUSED: delivery is locked — "), x.exception)
        explode.assert_not_called()

    def test_the_direct_invocation_of_the_runner_is_refused_with_the_real_preregistration(self):
        # nothing patched but what could reach a provider: the committed preregistration, this machine, an attempt
        # directory without a preflight (a temporary one — the experiment's own directory is never touched by a test)
        explode = mock.Mock(side_effect=AssertionError("a provider was reached"))
        where = self._other()
        with mock.patch.object(c2_p9, "opencode_session", explode), mock.patch.object(dx, "default_transport", explode):
            with self.assertRaises(SystemExit) as x:
                c2_p9.run(where, preserve_to=where / "kept.git", profile=c2_p9.EXPERIMENT)
        self.assertTrue(str(x.exception).startswith("REFUSED: delivery is locked — "), x.exception)
        explode.assert_not_called()
        self.assertEqual(sorted(p.name for p in where.iterdir()), [])                   # and it left nothing behind

    def test_a_run_under_the_profile_is_the_preregistered_attempt_only(self):
        with self.assertRaises(SystemExit) as x:
            c2_p9.main(["--run", "--attempt", "4", "--profile", c2_p9.EXPERIMENT])
        self.assertIn("preregistered as attempt 3 only", str(x.exception))


class RunSpecs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fields = {"route": dx.EXPERIMENT["route"], "declared_models": ["deepseek-v4-pro"]}
        cls.template, cls.resolved = dx.runspec(OC), dx.runspec(OC, cls.fields)

    def test_the_template_is_opaque_and_the_resolved_runspec_attests_the_model(self):
        grade = lambda spec: {c.name: c.grade.value for c in spec.capabilities if c.name in ("developer", "reviewer")}   # noqa: E731
        self.assertEqual(grade(self.template), {"developer": "OPAQUE", "reviewer": "OPAQUE"})
        self.assertEqual(grade(self.resolved), {"developer": "ATTESTED", "reviewer": "ATTESTED"})
        self.assertNotEqual(self.template.runspec_hash, self.resolved.runspec_hash)
        self.assertEqual(self.resolved.settings["preregistered_template_hash"]["value"], self.template.runspec_hash)
        self.assertNotIn("preregistered_template_hash", self.template.settings)
        dev = next(c for c in self.template.capabilities if c.name == "developer")
        self.assertEqual(dict(dev.tuple_), dx.allowed_identity(OC))

    def test_the_resolved_hash_is_derived_from_the_tuple_deterministically(self):
        self.assertEqual(dx.runspec(OC, dict(self.fields)).runspec_hash, self.resolved.runspec_hash)
        self.assertNotEqual(dx.runspec(OC, {**self.fields, "declared_models": ["other"]}).runspec_hash, self.resolved.runspec_hash)
        self.assertNotEqual(dx.runspec({**OC, "version": "9.9.9"}, self.fields).runspec_hash, self.resolved.runspec_hash)
        self.assertNotEqual(dx.runspec({**OC, "routing_config_digest": "2" * 64}, self.fields).runspec_hash, self.resolved.runspec_hash)

    def test_the_template_binds_the_budget_the_plan_the_kernel_commit_the_route_and_the_preflight(self):
        s = self.template.settings
        self.assertEqual(dict(s["budget"]["value"]), dx.EXPERIMENT["budget"])
        self.assertEqual((s["plan_hash"]["value"], s["kernel_commit"]["value"], s["experiment"]["value"]),
                         (pc.corrected_plan().plan_hash, dx.EXPERIMENT["kernel_commit"], c2_p9.EXPERIMENT))
        self.assertEqual(s["max_turns_per_session"]["value"], 80)
        for key, change in (("budget", {**dx.EXPERIMENT["budget"], "turns": 701}), ("max_turns_per_session", 81), ("route", "9router/mycombo"),
                            ("resolved_model", "other"),
                            ("kernel_commit", "0" * 40), ("preflight_shape", {**dx.EXPERIMENT["preflight_shape"], "smokes": 2})):
            with self.subTest(key=key), mock.patch.dict(dx.EXPERIMENT, {key: change}):
                self.assertNotEqual(dx.runspec(OC).runspec_hash, self.template.runspec_hash)
        self.assertNotIn("mycombo", json.dumps([c.resolved() for c in self.template.capabilities]))


class Preregistration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = json.loads((ROOT / dx.OUT_REL).read_text(encoding="utf-8"))
        cls.plan = pc.corrected_plan()

    def test_the_record_binds_what_this_tree_holds(self):
        r = self.rec
        self.assertEqual((r["verdict"], r["problems"]), ("PREREGISTERED — THE FINAL OWNER BUDGET; ONE RUN", []))
        self.assertTrue(r["run_authorized"].startswith("ONE RUN, by the owner's ruling"))
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

    def test_the_owner_s_budget_three_attempts_and_one_fixed_route(self):
        r = self.rec
        b = r["budget"]
        self.assertEqual((b["max_provider_requests"], b["max_total_turns"], b["max_turns_per_session"], b["max_combined_input_tokens"],
                          b["max_output_plus_reasoning_tokens"]), (60, 700, 80, 60_000_000, 400_000))
        self.assertEqual(r["runspec"]["settings"]["max_turns_per_session"]["value"], 80)
        self.assertEqual(b["accounting_limitation"], c2_p9.ACCOUNTING_LIMITATION)
        self.assertEqual(dict(r["runspec"]["settings"]["budget"]["value"]), dx.EXPERIMENT["budget"])
        self.assertEqual((r["profile"]["developer_attempts_per_story"], r["profile"]["limits"]["DEVELOPER"]), (3, 2))
        self.assertEqual(r["model"]["roles"], {"developer": dx.EXPERIMENT["route"], "reviewer": dx.EXPERIMENT["route"]})
        overlay = r["model"]["client_configuration_overlay"]
        self.assertEqual((overlay["model"], overlay["small_model"]), (dx.EXPERIMENT["route"],) * 2)
        self.assertNotIn("mycombo", json.dumps([r["runspec"], overlay, r["model"]["allowed_identity"]]))
        self.assertEqual(r["preflight"]["provider_requests_at_most"], 5)

    def test_the_template_hash_is_the_preregistered_identity_and_the_old_runspec_is_gone(self):
        r = self.rec
        self.assertRegex(r["runspec_template_hash"], r"^[0-9a-f]{64}$")
        self.assertNotIn("c7d4ed17", json.dumps(r))
        self.assertNotIn("runspec_hash", r)
        self.assertEqual((r["runspec"]["template_grade"]["by_capability"]["developer"], r["runspec"]["resolved_grade_when_attested"]["aggregate_min_grade"]),
                         ("OPAQUE", "ATTESTED"))
        dev = next(c for c in r["runspec"]["template_capabilities"] if c["name"] == "developer")
        self.assertEqual(dev["binding"], r["model"]["allowed_identity"])
        self.assertEqual({k: v for k, v in r["model"]["allowed_identity"].items() if k != "client"},
                         {"provider": "9router", "endpoint": "https://9router.vnteki.com/v1", "declared_model": "deepseek-v4-pro",
                          "route": "9router/ds/deepseek-v4-pro"})                      # no deployment is preregistered: it is bound only if exposed
        self.assertRegex(r["model"]["allowed_identity"]["client"], r"^opencode \S+ binary-sha256:[0-9a-f]{64} routing-config-sha256:[0-9a-f]{64}$")
        s = r["model"]["stable_declared_identity"]
        self.assertEqual((s["models_that_answered"], s["upstreams_listed"]), (["deepseek-v4-pro"], ["ds"]))
        self.assertGreaterEqual(s["recorded_preflights_on_the_route"], 10)

    def test_the_oracle_is_calibrated_under_this_interpreter(self):
        o = self.rec["final_evaluation"]["v1_oracle"]
        ready = self.rec["final_evaluation"]["readiness_measured_without_a_provider"]
        self.assertEqual((o["ORACLE_RUNTIME_DIFFERENCE"], o["ORACLE_CALIBRATION_EQUIVALENCE"]), ("coverage 7.16.2 vs 7.16.1", "PASS"))
        self.assertTrue(o["unchanged_since_calibration"])
        self.assertEqual(ready["v2_final_proof_on_the_p5_reference_fixture"], {"total": 59, "satisfied": 59, "not_satisfied": []})
        v, m = ready["v1_oracle_on_its_calibration_reference"], ready["v1_oracle_calibration_mutants"]
        self.assertEqual((v["total"], v["passed"], v["complete"]), (9, 9, True))
        self.assertEqual((m["total"], m["killed"], m["survived"]), (10, 10, []))
        self.assertEqual(sorted(m["mutants"]), sorted(f"M{i}" for i in range(1, 11)))
        self.assertEqual(v["interpreter"], o["interpreter"])

    def test_a_surviving_mutant_or_another_budget_is_a_problem(self):
        body = copy.deepcopy(self.rec)
        body["final_evaluation"]["v1_oracle"]["ORACLE_CALIBRATION_EQUIVALENCE"] = "FAIL"
        self.assertTrue(any(p.startswith("ORACLE_ENVIRONMENT_NOT_EQUIVALENT") for p in dx.problems(body)))
        body = copy.deepcopy(self.rec)
        body["budget"]["max_total_turns"] = 701
        self.assertIn("the budget is not the owner's", dx.problems(body))
        body = copy.deepcopy(self.rec)
        body["model"]["stable_declared_identity"]["models_that_answered"] = ["deepseek-v4-pro", "MiniMax-M3"]
        self.assertTrue(any(p.startswith(dx.CANNOT) for p in dx.problems(body)))

    def test_the_oracle_s_outcomes_are_reconciled_with_its_own_totals(self):
        out = ("test_oracle.py::TestAcceptance::test_a PASSED [ 50%]\ntest_oracle.py::TestAcceptance::test_b FAILED [100%]\n"
               "=========== 1 failed, 1 passed in 0.10s ===========\n")
        self.assertEqual(dx.parse_oracle(out), {"results": {"TestAcceptance::test_a": "PASSED", "TestAcceptance::test_b": "FAILED"},
                                                "total": 2, "passed": 1, "not_passed": ["TestAcceptance::test_b"], "complete": True})
        self.assertFalse(dx.parse_oracle(out.replace("1 failed, 1 passed", "1 failed, 2 passed"))["complete"])
        self.assertFalse(dx.parse_oracle("")["complete"])


STORIES = ["STORY-01-01", "STORY-01-05", "STORY-02-01", "STORY-02-02", "STORY-03-01", "STORY-04-01", "STORY-04-02"]
KEPT = {"path": "/kept.git", "final_tree": "t" * 40, "missing": []}


def journal(committed: list[str], rolled_back: tuple[str, ...] = ()) -> list[dict]:
    rows = [(s, t) for s in committed for t in ("gate/decision", "story/commit")] + [(s, t) for s in rolled_back for t in ("gate/decision", "story/rollback")]
    return [{"seq": n, "type": t, "data": {"story_id": s, "revision": "a" * 40}} for n, (s, t) in enumerate(rows)]


class FalsePass(unittest.TestCase):
    """Ruling §8: a delivery verdict is PASS only when every planned story committed — in the journal. Made-up
    measurements, no model."""

    def record(self, events: list[dict], results: dict, reached: str | None = None, preserved: dict | None = None) -> dict:
        plan = pc.corrected_plan()
        caps, layers, kernel = c2_p9.runspec_inputs(plan, c2_p9.EXPERIMENT, OC, dx.fixed(OC), {})
        exp = {**dx.fixed(OC), "plan": plan, "authority": dx.AUTHORITY, "preregistration": {"path": dx.OUT_REL},
               "plan_correction": {"path": pc.OUT_REL}, "attestation": {"path": "ATTESTATION.json"}}
        m = {"started": 0.0, "results": results, "errors": [], "events": events, "state": {}, "run_identity": {}, "final_main": "f" * 40,
             "preserved": KEPT if preserved is None else preserved, "profile": c2_p9.EXPERIMENT, "experiment": exp,
             "budget": {"limits": dx.EXPERIMENT["budget"], "spent": {}, "reached": reached},
             "baseline": {"baseline": plan.baseline}, "oc": OC, "plan": plan, "specs": {s.id: s for s in c2_p9._compiled().values()},
             "tasks": {}, "sessions": [], "caps": caps, "layers": layers, "kernel": kernel}
        with tempfile.TemporaryDirectory() as d:
            return c2_p9.record(pathlib.Path(d), m)

    def test_the_plan_s_stories_are_the_seven(self):
        self.assertEqual(c2_p9.order(pc.corrected_plan(), pc.build()["graph"]), STORIES)

    def test_zero_stories_run(self):
        rec = self.record([], {})
        self.assertNotEqual(rec["delivery_verdict"], "PASS")
        self.assertEqual(rec["stories_not_committed"], STORIES)

    def test_the_first_stories_committed_then_a_budget_stop(self):
        events = journal(STORIES[:3])
        self.assertEqual(c2_p9.P10.delivery_verdict_of(events, plan_admitted=True), "PASS")     # the journal alone: every story IN IT committed
        results = {**{s: ["COMMIT"] for s in STORIES[:3]}, **{s: ["NOT_RUN: max_turns: 700 of 700"] for s in STORIES[3:]}}
        rec = self.record(events, results, reached="max_turns: 700 of 700")
        self.assertEqual((rec["delivery_verdict"], rec["stories_not_committed"]), ("FAIL", STORIES[3:]))
        self.assertEqual(rec["delivery_pass_blocked_by"], ["4 of the plan's stories did not commit", "the budget ended the experiment: max_turns: 700 of 700"])

    def test_the_final_story_never_starts(self):
        rec = self.record(journal(STORIES[:6]), {s: ["COMMIT"] for s in STORIES[:6]})
        self.assertEqual((rec["delivery_verdict"], rec["stories_not_committed"]), ("FAIL", STORIES[6:]))

    def test_one_story_has_no_journal_events(self):
        rec = self.record(journal(STORIES[:4] + STORIES[5:]), {s: ["COMMIT"] for s in STORIES})     # the harness says COMMIT; the journal does not
        self.assertEqual((rec["delivery_verdict"], rec["stories_not_committed"]), ("FAIL", [STORIES[4]]))

    def test_a_story_whose_last_journal_outcome_is_a_rollback_is_not_delivered(self):
        rec = self.record(journal(STORIES[:6], rolled_back=(STORIES[6],)), {s: ["COMMIT"] for s in STORIES})
        self.assertEqual((rec["delivery_verdict"], rec["stories_not_committed"]), ("FAIL", [STORIES[6]]))

    def test_all_seven_stories_successful_is_the_only_pass(self):
        rec = self.record(journal(STORIES), {s: ["COMMIT"] for s in STORIES})
        self.assertEqual((rec["delivery_verdict"], rec["stories_not_committed"], rec["delivery_pass_blocked_by"]), ("PASS", [], []))
        self.assertEqual((rec["semantic_candidate"], rec["aisef2_tree"]), (dx.EXPERIMENT["kernel_commit"], dx.EXPERIMENT["kernel_tree"]))
        self.assertEqual(rec["plan_identity"]["plan_hash"], pc.corrected_plan().plan_hash)
        self.assertEqual(rec["execution_profile"]["developer_attempts_per_story"], 3)
        self.assertEqual(rec["execution_profile"]["aggregate_min_grade"] in ("ATTESTED", "OPAQUE"), True)      # OPAQUE only where ruff is absent

    def test_all_seven_committed_but_the_budget_was_reached_is_not_a_pass(self):
        rec = self.record(journal(STORIES), {s: ["COMMIT"] for s in STORIES}, reached="max_provider_requests: 60 of 60")
        self.assertEqual((rec["delivery_verdict"], rec["delivery_pass_blocked_by"]), ("FAIL", ["the budget ended the experiment: max_provider_requests: 60 of 60"]))
        rec = self.record(journal(STORIES), {s: ["COMMIT"] for s in STORIES}, reached="unaccounted: x.jsonl: a session that started finished no step")
        self.assertEqual(rec["delivery_verdict"], "FAIL")

    def test_all_seven_committed_but_not_preserved_is_not_a_pass(self):
        for preserved in ({**KEPT, "missing": ["c" * 40]}, {"path": "/kept.git", "error": "OSError", "missing": ["<not preserved>"]}, {**KEPT, "final_tree": None}):
            with self.subTest(preserved=preserved):
                rec = self.record(journal(STORIES), {s: ["COMMIT"] for s in STORIES}, preserved=preserved)
                self.assertEqual((rec["delivery_verdict"], rec["delivery_pass_blocked_by"]), ("FAIL", ["the run's revisions are not all preserved"]))

    def test_a_pass_is_confirmed_only_with_the_product_requirements(self):
        good_proof, good_oracle = {"total": 59, "satisfied": 59}, {"complete": True, "total": 9, "passed": 9}
        self.assertTrue(dx.confirmed("PASS", good_proof, good_oracle))
        for verdict, proof, oracle in (("FAIL", good_proof, good_oracle), ("PASS", {"total": 59, "satisfied": 58}, good_oracle),
                                       ("PASS", good_proof, {"complete": True, "total": 9, "passed": 8}),
                                       ("PASS", good_proof, {"complete": False, "total": 9, "passed": 9}),
                                       ("PASS", good_proof, {"complete": True, "total": 0, "passed": 0}), ("NOT_REACHED", good_proof, good_oracle)):
            with self.subTest(verdict=verdict, proof=proof, oracle=oracle):
                self.assertFalse(dx.confirmed(verdict, proof, oracle))


class Preservation(unittest.TestCase):
    """Ruling §9: every revision the journal cites is pinned, and one that is missing keeps the temporary repository."""

    def test_every_revision_a_real_journal_cites_is_collected(self):
        events = json.loads((ROOT / "closure-evidence/v2/cycle2/P10/attempt-2/JOURNAL.json").read_text(encoding="utf-8"))
        cited, trees = set(), set()

        def walk(o, e, path=()):
            if isinstance(o, dict):
                for k, v in o.items():
                    walk(v, e, path + (k,))
            elif isinstance(o, list):
                for v in o:
                    walk(v, e, path)
            elif isinstance(o, str) and re.fullmatch(r"[0-9a-f]{40}", o):
                (trees if (e["type"], path) == ("capability/resolved", ("binding", "tree")) else cited).add(o)
        for e in events:
            walk(e["data"], e)
        got = set(c2_p9.run_shas(events, [], None))
        self.assertTrue(cited)
        self.assertEqual(cited - got, set())                 # story parents, proved candidates, commits, probe revisions, the baseline
        self.assertEqual(got & trees, set())                 # the kernel's tree id is not a revision of the run

    def test_session_candidates_and_final_main_are_among_them(self):
        events = [{"type": "probe/evaluated", "data": {"record": {"revision": "e" * 40}}}, {"type": "story/admitted", "data": {"parent": "b" * 40}}]
        self.assertEqual(c2_p9.run_shas(events, [{"candidate": "d" * 40}, {"candidate": None}], "f" * 40), sorted(x * 40 for x in "bdef"))

    def test_a_missing_revision_keeps_the_temporary_repository(self):
        self.assertTrue(c2_p9.may_remove(KEPT))
        for preserved in (None, {**KEPT, "missing": ["c" * 40]}, {**KEPT, "final_tree": None}, {"error": "x", "missing": ["<not preserved>"]}):
            self.assertFalse(c2_p9.may_remove(preserved))


if __name__ == "__main__":
    unittest.main()
