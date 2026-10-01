"""C2-P10 / WP-2.10.1 — the evaluation-cohort machinery (RFC §28-§30), on synthetic preregistrations only.

Every preregistration here is built in memory from placeholder hashes; none names a selected workload and none is
written anywhere. The one real identity used is LedgerLock's, read from its frozen files, to show that it is refused.
These are the mutation kill tests of aisef2/cohort (validation/v2/mutation.py, phase C2-P10): every refusal is checked
by its code and its exact message.
"""

import copy
import hashlib
import json
import pathlib
import unittest
from types import MappingProxyType

from aisef2.arch.enums import Enforcement as E
from aisef2.cohort import lifecycle as L
from aisef2.cohort import preregistration as P
from aisef2.cohort.lifecycle import CohortState as S
from aisef2.cohort.preregistration import CohortRefused, Refusal as R
from aisef2.runtime.capability import attested, opaque, verified
from aisef2.runtime.runspec import resolve

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUTE = "fixture/fixture-model-1"
NAMES = ("kernel", "workload", "requirements", "plan_policy", "execution_profile", "prompts", "model_route",
         "run_count", "thresholds", "oracle", "metrics", "plan_quality_policy")


def _sha(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


def _file_sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def spec(grade: str = "ATTESTED"):
    model = attested("model", provider="fixture", endpoint="loopback:fixture", declared_model="fixture-model-1",
                     route=ROUTE, client="fixture-client", preflight={"served_model": "fixture-model-1"},
                     enforcement=E.FULL)
    if grade == "OPAQUE":
        model = opaque("model", E.FULL, provider="fixture", declared_model="fixture-combo", route=ROUTE)
    return resolve([verified("kernel", b"kernel bytes", E.FULL), model],
                   {"max_turns": {"value": 40, "layer": "profile"}}, "1" * 40)


def prereg(n: int = 1, *, grade: str = "ATTESTED", runs: int = 3) -> dict:
    """A synthetic preregistration; `n` gives it its own workload identity."""
    d = f"{n:x}"
    return {"schema": P.SCHEMA, "cohort_id": f"C-{n}", "kernel": {"aisef2_tree": "2" * 40},
            "workload": {"name": f"synthetic-{n}", "plan_baseline": (d * 40)[:40], "plan_hash": ("c" + d * 63)[:64]},
            "requirements": {"sha256": ("d" + d * 63)[:64]}, "plan_policy": {"sha256": "6" * 64},
            "execution_profile": P.execution_profile(spec(grade)), "prompts": {"sha256": "7" * 64},
            "model_route": {"capability": "model", "route": ROUTE}, "run_count": runs,
            "thresholds": {"delivery": ">=2/3 delivery complete"}, "oracle": {"sha256": "8" * 64},
            "metrics": ["delivery_verdict", "plan_quality_verdict"],
            "plan_quality_policy": {"max_pre_satisfied_introduce_ratio": 0.25, "max_fully_pre_satisfied_stories": None,
                                    "max_unattributed_plan_drift": 0}}


def ledgerlock(**workload) -> dict:
    """A preregistration naming LedgerLock's frozen identity, read from its files, under any name."""
    rec = prereg(9)
    plan = json.loads((ROOT / "closure-evidence/v2/P10/WORKLOAD.json").read_text(encoding="utf-8"))["plan"]
    rec["requirements"]["sha256"] = _file_sha("tests/v2/fixtures/workloads/ledgerlock-reference/REQUIREMENTS.md")
    rec["workload"].update({"name": "a-fresh-holdout", "plan_baseline": plan["baseline"], "plan_hash": plan["plan_hash"]})
    rec["workload"].update(workload)
    return rec


def evaluating(n: int = 1, runs: int = 3, done: int = 0, read: float | None = None) -> L.EvaluationCohort:
    c = L.advance(L.seal(prereg(n, runs=runs)), S.EVALUATING)
    for i in range(done):
        c = L.record_run(c, f"r{i + 1}")
    return c if read is None else L.read_results(c, read)


class Refuses(unittest.TestCase):
    def refused(self, code: R, why: str, fn, *args, **kwargs) -> CohortRefused:
        with self.assertRaises(CohortRefused) as cm:
            fn(*args, **kwargs)
        self.assertIs(cm.exception.code, code)
        self.assertEqual(cm.exception.why, why)
        self.assertEqual(str(cm.exception), f"{code.value}: {why}")
        return cm.exception


class Preregistration(Refuses):
    def test_the_schema_freezes_every_rfc_28_input_in_order(self):
        self.assertEqual(P.SCHEMA, "aisef2.cohort.preregistration/1")
        self.assertEqual(P.FROZEN_INPUTS, NAMES)
        self.assertEqual(P.IDENTITY, ("requirements_sha256", "plan_baseline", "plan_hash"))

    def test_a_valid_preregistration_and_its_frozen_form_have_no_problem(self):
        rec = prereg()
        self.assertEqual(P.problems(rec), [])
        frozen = P.validate(rec)
        self.assertIsInstance(frozen, MappingProxyType)
        self.assertIsInstance(frozen["metrics"], tuple)
        self.assertEqual(P.problems(frozen), [])
        self.assertEqual(P.validate(frozen), frozen)

    def test_not_an_object(self):
        self.assertEqual(P.problems(["x"]), ["a preregistration is a JSON object"])
        self.refused(R.PREREGISTRATION_INVALID, "a preregistration is a JSON object", P.validate, "x")

    def test_missing_and_unknown_keys_are_named_in_order(self):
        self.assertEqual(P.problems({}), [f"missing {k}" for k in sorted({"schema", "cohort_id", *NAMES})]
                         + [f"schema is not {P.SCHEMA}", "cohort_id is not a name"])
        extra = [f"x{i:02d}" for i in range(12)]
        rec = {**prereg(), **{k: 1 for k in reversed(extra)}}
        self.assertEqual(P.problems(rec), [f"unknown {k}" for k in extra])

    def test_schema_and_cohort_id(self):
        for bad in ({"schema": "aisef2.cohort.preregistration/2"}, {"cohort_id": " "}, {"cohort_id": 7}):
            rec = {**prereg(), **bad}
            want = "schema is not aisef2.cohort.preregistration/1" if "schema" in bad else "cohort_id is not a name"
            self.assertEqual(P.problems(rec), [want])
        self.refused(R.PREREGISTRATION_INVALID, "schema is not aisef2.cohort.preregistration/1; cohort_id is not a name",
                     P.validate, {**prereg(), "schema": None, "cohort_id": ""})

    def test_every_shape_is_checked(self):
        cases = [("kernel", {"aisef2_tree": "2" * 39}), ("kernel", {"aisef2_tree": "2" * 40, "extra": "x"}),
                 ("kernel", {"aisef2_tree": 2}), ("kernel", ["2" * 40]),
                 ("workload", {"name": " ", "plan_baseline": "3" * 40, "plan_hash": "4" * 64}),
                 ("workload", {"name": 5, "plan_baseline": "3" * 40, "plan_hash": "4" * 64}),
                 ("workload", {"name": "w", "plan_baseline": "3" * 64, "plan_hash": "4" * 64}),
                 ("workload", {"name": "w", "plan_baseline": "3" * 40, "plan_hash": "A" * 64}),
                 ("workload", {"name": "w", "plan_baseline": "3" * 40, "plan_hash": 4}),
                 ("requirements", {"sha256": "5" * 40}), ("plan_policy", {"sha256": "g" * 64}),
                 ("prompts", {}), ("oracle", {"sha256": None}),
                 ("model_route", {"capability": "", "route": ROUTE}), ("model_route", {"capability": "model"}),
                 ("run_count", 0), ("run_count", True), ("run_count", "3"), ("run_count", 3.0),
                 ("thresholds", {"delivery": ""}), ("thresholds", {"delivery": ">=2/3", "plan": "x"}),
                 ("metrics", []), ("metrics", ["a", "a"]), ("metrics", ["", "b"]), ("metrics", "ab"),
                 ("metrics", [1, 2]), ("metrics", {"a": 1})]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                self.assertEqual(P.problems({**prereg(), key: value}), [f"{key} is malformed"])

    def test_the_execution_profile_must_re_derive_from_its_content(self):
        good = prereg()["execution_profile"]
        self.assertEqual(P.runspec_of(good).runspec_hash, spec().runspec_hash)
        self.assertEqual(P.runspec_of(MappingProxyType(good)).aggregate_min_grade.value, "ATTESTED")
        for field, value in (("runspec_hash", "0" * 64), ("aggregate_min_grade", "VERIFIED"), ("extra", 1)):
            bad = {**copy.deepcopy(good), field: value}
            self.refused(R.PREREGISTRATION_INVALID, "execution_profile does not re-derive from its content",
                         P.runspec_of, bad)
            self.assertEqual(P.problems({**prereg(), "execution_profile": bad}),
                             ["execution_profile does not re-derive from its content"])
        no_grade = copy.deepcopy(good)
        del no_grade["capabilities"][0]["grade"]
        self.refused(R.PREREGISTRATION_INVALID, "execution_profile: KeyError('grade')", P.runspec_of, no_grade)
        no_revision = copy.deepcopy(good)
        del no_revision["settings"]["revision"]
        self.refused(R.PREREGISTRATION_INVALID, "execution_profile: KeyError('revision')", P.runspec_of, no_revision)
        for bad, kind in (({**good, "capabilities": [1]}, "TypeError("), (None, "TypeError("),
                          ({**good, "capabilities": [{**good["capabilities"][0], "grade": "BOGUS"}]}, "ValueError(")):
            with self.assertRaises(CohortRefused) as cm:
                P.runspec_of(bad)
            self.assertIs(cm.exception.code, R.PREREGISTRATION_INVALID)
            self.assertTrue(cm.exception.why.startswith(f"execution_profile: {kind}"), cm.exception.why)
            self.assertEqual(P.problems({**prereg(), "execution_profile": bad}), [cm.exception.why])

    def test_the_execution_profile_is_the_runspec_content(self):
        s = spec()
        self.assertEqual(P.execution_profile(s), {
            "capabilities": [c.content() for c in s.capabilities], "aggregate_min_grade": "ATTESTED",
            "settings": {"max_turns": {"value": 40, "layer": "profile"}, "revision": {"value": "1" * 40, "layer": "run"}},
            "runspec_hash": s.runspec_hash})

    def test_the_model_route_must_be_one_the_profile_binds(self):
        for route in ({"capability": "model", "route": "fixture/other"}, {"capability": "kernel", "route": ROUTE}):
            self.assertEqual(P.problems({**prereg(), "model_route": route}),
                             ["model_route is not a route the execution profile binds"])

    def test_the_plan_quality_policy_is_preregistered_exactly(self):
        policy = prereg()["plan_quality_policy"]
        self.assertEqual(P.policy_of(policy).max_pre_satisfied_introduce_ratio, 0.25)
        for bad in ({}, None, {**policy, "extra": 1}):
            self.refused(R.PREREGISTRATION_INVALID, "plan_quality_policy is malformed", P.policy_of, bad)
        why = "plan_quality_policy: max_pre_satisfied_introduce_ratio is a ratio in [0, 1] or None"
        self.refused(R.PREREGISTRATION_INVALID, why, P.policy_of, {**policy, "max_pre_satisfied_introduce_ratio": 2})
        self.assertEqual(P.problems({**prereg(), "plan_quality_policy": {**policy, "max_unattributed_plan_drift": -1}}),
                         ["plan_quality_policy: max_unattributed_plan_drift is a non-negative count or None"])

    def test_hashes_are_of_the_canonical_content(self):
        rec = prereg()
        self.assertEqual(P.preregistration_hash(rec), _sha(rec))
        self.assertEqual(P.preregistration_hash(P.validate(rec)), _sha(rec))
        self.assertEqual(P.frozen_inputs(rec), {k: _sha(rec[k]) for k in NAMES})

    def test_workload_identity_and_sharing(self):
        a, b = P.workload_identity(prereg(1)), P.workload_identity(prereg(2))
        self.assertEqual(a, {"requirements_sha256": "d" + "1" * 63, "plan_baseline": "1" * 40,
                             "plan_hash": "c" + "1" * 63})
        self.assertEqual(P.shared(a, b), [])
        self.assertEqual(P.shared(a, a), ["requirements_sha256", "plan_baseline", "plan_hash"])
        self.assertEqual(P.shared(a, {**b, "plan_hash": a["plan_hash"]}), ["plan_hash"])


class LedgerLock(Refuses):
    """RFC §30: identified by the frozen identity its records carry, never by a name."""

    def test_the_registry_is_bound_to_the_frozen_files(self):
        (entry,) = P.DEVELOPMENT_REGRESSION
        self.assertEqual(set(entry), {"label", "requirements_sha256", "plan_baseline", "plan_hash",
                                      "requirements_source", "workload_record", "workload_record_sha256"})
        self.assertEqual(entry["label"], "LedgerLock")
        self.assertTrue(entry["requirements_sha256"].startswith("3a6a9995"))
        self.assertTrue(entry["plan_baseline"].startswith("136a68dc"))
        self.assertEqual(entry["workload_record"], "closure-evidence/v2/P10/WORKLOAD.json")
        self.assertEqual(_file_sha(entry["requirements_source"]), entry["requirements_sha256"])
        self.assertEqual(_file_sha(entry["workload_record"]), entry["workload_record_sha256"])
        plan = json.loads((ROOT / entry["workload_record"]).read_text(encoding="utf-8"))["plan"]
        self.assertEqual((plan["baseline"], plan["plan_hash"]), (entry["plan_baseline"], entry["plan_hash"]))

    def test_ledgerlock_never_seals_under_any_name(self):
        why = ("LedgerLock is a development / regression benchmark permanently (RFC §30); "
               "same requirements_sha256, plan_baseline, plan_hash")
        self.assertEqual(P.development_regression(ledgerlock()), why)
        self.refused(R.DEVELOPMENT_REGRESSION, why, L.seal, ledgerlock())
        self.refused(R.DEVELOPMENT_REGRESSION, why, L.EvaluationCohort, ledgerlock(), S.SEALED)
        self.refused(R.DEVELOPMENT_REGRESSION, why, L.EvaluationCohort, ledgerlock(name="LedgerLock"), S.DEVELOPMENT,
                     exposed_reason="x")

    def test_one_identity_component_is_enough(self):
        fresh = prereg(9)["workload"]
        for keep, extra in (("requirements_sha256", {"plan_baseline": fresh["plan_baseline"], "plan_hash": fresh["plan_hash"]}),
                            ("plan_baseline", {"plan_hash": fresh["plan_hash"]}),
                            ("plan_hash", {"plan_baseline": fresh["plan_baseline"]})):
            rec = ledgerlock(**extra)
            if keep != "requirements_sha256":
                rec["requirements"]["sha256"] = prereg(9)["requirements"]["sha256"]
            why = f"LedgerLock is a development / regression benchmark permanently (RFC §30); same {keep}"
            self.refused(R.DEVELOPMENT_REGRESSION, why, L.seal, rec)
        self.assertIsNone(P.development_regression(prereg(9)))


class Lifecycle(Refuses):
    def test_the_one_way(self):
        self.assertEqual(L.NEXT, {S.SEALED: S.EVALUATING, S.EVALUATING: S.EXPOSED, S.EXPOSED: S.DEVELOPMENT})
        self.assertEqual(L.DEMOTED, (S.EXPOSED, S.DEVELOPMENT))
        self.assertEqual(L.MIN_WORKLOADS, 2)
        c = L.seal(prereg())
        steps = [(S.EVALUATING, None), (S.EXPOSED, "tuned against"), (S.DEVELOPMENT, None)]
        seen = [c]
        for to, reason in steps:
            c = L.advance(c, to, reason)
            seen.append(c)
            self.assertIs(c.state, to)
        self.assertEqual([x.exposed_reason for x in seen], [None, None, "tuned against", "tuned against"])
        for c in seen:
            for to in [*S, "HOLDOUT"]:
                if L.NEXT.get(c.state) is to:
                    continue
                name = getattr(to, "value", to)
                self.refused(R.NOT_FORWARD, f"{c.state.value} -> {name}: one way, one step at a time", L.advance, c, to)
        self.assertEqual(list(S), [S.SEALED, S.EVALUATING, S.EXPOSED, S.DEVELOPMENT])

    def test_exposure_records_its_reason(self):
        c = evaluating()
        self.refused(R.COHORT_INCONSISTENT, "EXPOSED records its exposed_reason", L.advance, c, S.EXPOSED)
        self.refused(R.COHORT_INCONSISTENT, "EXPOSED records its exposed_reason", L.advance, c, S.EXPOSED, " ")
        self.refused(R.COHORT_INCONSISTENT, "EVALUATING has no exposed_reason", L.advance, L.seal(prereg()),
                     S.EVALUATING, "early")
        x = L.advance(c, S.EXPOSED, "seen")
        self.refused(R.COHORT_INCONSISTENT, "DEVELOPMENT records its exposed_reason", L.EvaluationCohort,
                     prereg(), S.DEVELOPMENT)
        self.refused(R.COHORT_INCONSISTENT, "EXPOSED records its exposed_reason", L.EvaluationCohort, prereg(),
                     S.EXPOSED, exposed_reason=5)
        self.assertEqual(L.advance(x, S.DEVELOPMENT).exposed_reason, "seen")

    def test_the_cohort_reads_its_identity_from_the_preregistration(self):
        rec = prereg(3, runs=4)
        c = L.seal(rec)
        self.assertIs(c.state, S.SEALED)
        self.assertIsInstance(c.preregistration, MappingProxyType)
        self.assertEqual((c.id, c.planned_runs, c.threshold), ("C-3", 4, ">=2/3 delivery complete"))
        self.assertEqual(c.preregistration_hash, _sha(rec))
        self.assertIsInstance(c.frozen_inputs, MappingProxyType)
        self.assertEqual(dict(c.frozen_inputs), {k: _sha(rec[k]) for k in NAMES})
        self.assertEqual(c.plan_quality_policy, P.policy_of(rec["plan_quality_policy"]))
        self.assertEqual(c.workload, P.workload_identity(rec))
        self.assertEqual((c.runs_completed, c.results_read_at, c.exposed_reason, c.invalidated_runs, c.stale_inputs),
                         ((), None, None, (), ()))

    def test_the_constructor_holds_every_bar(self):
        self.refused(R.OPAQUE_PROFILE, "an OPAQUE aggregate_min_grade never seals (RFC §28 rule 5)",
                     L.seal, prereg(grade="OPAQUE"))
        self.refused(R.OPAQUE_PROFILE, "an OPAQUE aggregate_min_grade never seals (RFC §28 rule 5)",
                     L.EvaluationCohort, prereg(grade="OPAQUE"), S.DEVELOPMENT, exposed_reason="x")
        self.refused(R.PREREGISTRATION_INVALID, "run_count is malformed", L.seal, {**prereg(), "run_count": 0})
        self.refused(R.COHORT_INCONSISTENT, "state is a CohortState", L.EvaluationCohort, prereg(), "SEALED")

    def test_the_constructor_checks_its_own_fields(self):
        ok = evaluating(done=1)
        for name in ("runs_completed", "invalidated_runs", "stale_inputs"):
            for bad in (["a"], ("",), ("a", "a"), (1,)):
                self.refused(R.COHORT_INCONSISTENT, f"{name} is a tuple of distinct names",
                             L.EvaluationCohort, prereg(), S.EVALUATING, **{name: bad})
        self.refused(R.COHORT_INCONSISTENT, "more runs than were preregistered",
                     L.EvaluationCohort, prereg(), S.EVALUATING, runs_completed=("a", "b", "c", "d"))
        for t in (True, "1", float("nan"), float("inf")):
            self.refused(R.COHORT_INCONSISTENT, "results_read_at is a finite timestamp or None",
                         L.EvaluationCohort, prereg(), S.EVALUATING, results_read_at=t)
        for t in (5, 5.5):
            self.assertEqual(L.EvaluationCohort(prereg(), S.EVALUATING, results_read_at=t).results_read_at, t)
        for fields in ({"runs_completed": ("r1",)}, {"results_read_at": 1.0}):
            self.refused(R.COHORT_INCONSISTENT, "a SEALED cohort has run nothing and read nothing",
                         L.EvaluationCohort, prereg(), S.SEALED, **fields)
        self.assertEqual(ok.runs_completed, ("r1",))


class Seal(Refuses):
    def test_an_unrelated_cohort_does_not_hold_the_workload(self):
        self.assertIs(L.seal(prereg(2), prior=[L.seal(prereg(1)), evaluating(3, done=1)]).state, S.SEALED)

    def test_a_development_or_exposed_workload_never_seals_again(self):
        exposed = L.observe_inputs(evaluating(1, done=3, read=50.0), {})
        self.assertIs(exposed.state, S.EXPOSED)
        dev = L.advance(exposed, S.DEVELOPMENT)
        fresh = {**prereg(1), "prompts": {"sha256": "9" * 64}}
        self.refused(R.WORKLOAD_DEMOTED, "C-1 is EXPOSED: its workload never seals again", L.seal, fresh, [exposed])
        self.refused(R.WORKLOAD_DEMOTED, "C-1 is DEVELOPMENT: its workload never seals again", L.seal, fresh, [dev])
        renamed = copy.deepcopy(fresh)
        renamed["workload"]["name"] = "another-name"
        renamed["workload"]["plan_baseline"] = "e" * 40
        renamed["requirements"]["sha256"] = "e" * 64
        self.refused(R.WORKLOAD_DEMOTED, "C-1 is DEVELOPMENT: its workload never seals again", L.seal, renamed, (dev,))

    def test_an_observed_or_live_workload_is_held(self):
        fresh = {**prereg(1), "oracle": {"sha256": "9" * 64}}
        self.refused(R.WORKLOAD_OBSERVED, "C-1 read its results at 50.0", L.seal, fresh, [evaluating(1, read=50.0)])
        self.refused(R.WORKLOAD_ALREADY_SEALED, "C-1 still holds the workload (SEALED)", L.seal, fresh,
                     [L.seal(prereg(1))])
        self.refused(R.WORKLOAD_ALREADY_SEALED, "C-1 still holds the workload (EVALUATING)", L.seal, fresh,
                     [L.seal(prereg(2)), evaluating(1, done=2)])

    def test_only_an_invalidated_cohort_leaves_room_for_a_fresh_preregistration(self):
        old = evaluating(1, done=2)
        stale = L.observe_inputs(old, {**old.frozen_inputs, "prompts": "0" * 64})
        fresh = {**prereg(1), "prompts": {"sha256": "9" * 64}}
        self.assertEqual(L.seal(fresh, [stale]).preregistration_hash, _sha(fresh))
        self.refused(R.PREREGISTRATION_REUSED, "C-1 was invalidated under this preregistration", L.seal, prereg(1),
                     [stale])


class Evaluation(Refuses):
    def test_runs_never_demote(self):
        c = evaluating(runs=3)
        for i in (1, 2, 3):
            c = L.record_run(c, f"r{i}")
            self.assertEqual((c.state, c.exposed_reason), (S.EVALUATING, None))
        self.assertEqual(c.runs_completed, ("r1", "r2", "r3"))
        self.refused(R.RUNS_COMPLETE, "all 3 preregistered runs are recorded", L.record_run, c, "r4")
        self.refused(R.RUN_DUPLICATE, "r1 is already recorded", L.record_run, c, "r1")

    def test_runs_and_reads_need_a_live_evaluation(self):
        sealed = L.seal(prereg())
        self.refused(R.NOT_EVALUATING, "C-1 is SEALED", L.record_run, sealed, "r1")
        self.refused(R.NOT_EVALUATING, "C-1 is SEALED", L.read_results, sealed, 1.0)
        exposed = L.advance(evaluating(), S.EXPOSED, "x")
        self.refused(R.NOT_EVALUATING, "C-1 is EXPOSED", L.record_run, exposed, "r1")
        c = evaluating(done=1)
        stale = L.observe_inputs(c, {**c.frozen_inputs, "prompts": "0", "oracle": "0"})
        why = "oracle, prompts changed: a fresh preregistration is required"
        self.refused(R.PREREGISTRATION_STALE, why, L.record_run, stale, "r2")
        self.refused(R.PREREGISTRATION_STALE, why, L.read_results, stale, 1.0)

    def test_the_first_read_stands(self):
        c = L.read_results(evaluating(done=1), 100.0)
        self.assertEqual(c.results_read_at, 100.0)
        self.assertEqual(L.read_results(c, 200.0).results_read_at, 100.0)
        self.assertEqual(L.record_run(c, "r2").results_read_at, 100.0)


class Demotion(Refuses):
    def test_no_change_is_no_event(self):
        for c in (L.seal(prereg()), evaluating(done=2), evaluating(done=2, read=1.0)):
            self.assertIs(L.observe_inputs(c, dict(c.frozen_inputs)), c)

    def test_a_change_before_any_read_invalidates_the_completed_runs(self):
        c = evaluating(done=2)
        x = L.observe_inputs(c, {**c.frozen_inputs, "prompts": "0" * 64, "extra": "x"})
        self.assertEqual((x.state, x.runs_completed, x.invalidated_runs, x.stale_inputs, x.exposed_reason),
                         (S.EVALUATING, (), ("r1", "r2"), ("extra", "prompts"), None))
        y = L.observe_inputs(x, {})
        self.assertEqual(y.stale_inputs, tuple(sorted([*NAMES, "extra"])))
        self.assertEqual(L.observe_inputs(L.seal(prereg()), {}).stale_inputs, tuple(sorted(NAMES)))

    def test_a_change_after_the_read_demotes_to_exposed(self):
        c = evaluating(done=3, read=1234.5)
        x = L.observe_inputs(c, {**c.frozen_inputs, "execution_profile": "0" * 64})
        self.assertEqual((x.state, x.runs_completed, x.results_read_at),
                         (S.EXPOSED, ("r1", "r2", "r3"), 1234.5))
        self.assertEqual(x.exposed_reason, "frozen inputs changed after results were read at 1234.5: execution_profile")
        everything = L.observe_inputs(c, {})
        self.assertEqual(everything.exposed_reason,
                         f"frozen inputs changed after results were read at 1234.5: {', '.join(sorted(NAMES))}")
        self.assertIs(L.observe_inputs(x, {}), x)
        self.assertIs(L.observe_inputs(L.advance(x, S.DEVELOPMENT), {}).state, S.DEVELOPMENT)


class Generalization(Refuses):
    def test_two_independent_completed_evaluations_state_their_sample_sizes(self):
        a, b = evaluating(1, runs=3, done=3, read=1.0), evaluating(2, runs=2, done=2, read=2.0)
        self.assertEqual(L.generalization(iter([a, b])), {
            "workloads": [{"cohort": "C-1", "preregistration_hash": a.preregistration_hash, "sample_size": 3},
                          {"cohort": "C-2", "preregistration_hash": b.preregistration_hash, "sample_size": 2}],
            "workload_count": 2, "sample_size_total": 5})

    def test_fewer_than_two_workloads_is_no_generalization(self):
        why = "1 sealed workload(s); a generalization requires at least 2"
        self.refused(R.GENERALIZATION_REFUSED, why, L.generalization, [evaluating(1, done=3, read=1.0)])
        self.refused(R.GENERALIZATION_REFUSED, "0 sealed workload(s); a generalization requires at least 2",
                     L.generalization, [])

    def test_only_completed_sealed_evaluations_count(self):
        done = evaluating(1, done=3, read=1.0)
        stale = L.EvaluationCohort(prereg(2), S.EVALUATING, runs_completed=("r1", "r2", "r3"), results_read_at=1.0,
                                   stale_inputs=("prompts",))     # each case fails exactly one condition
        cases = [L.advance(evaluating(2, done=3, read=1.0), S.EXPOSED, "x"), evaluating(2, done=3),
                 evaluating(2, done=2, read=1.0), stale]
        for c in cases:
            self.refused(R.GENERALIZATION_REFUSED, "C-2 is not a completed sealed evaluation", L.generalization,
                         [done, c])
        self.refused(R.GENERALIZATION_REFUSED,
                     "C-2 is not a completed sealed evaluation; 1 sealed workload(s); a generalization requires at "
                     "least 2", L.generalization, [cases[0]])

    def test_workloads_must_be_independent(self):
        a = evaluating(1, done=3, read=1.0)
        twin = prereg(2)
        twin["requirements"] = dict(prereg(1)["requirements"])
        twin["workload"]["plan_baseline"] = prereg(1)["workload"]["plan_baseline"]
        b = L.read_results(L.record_run(L.record_run(L.record_run(L.advance(L.seal(twin), S.EVALUATING), "r1"), "r2"),
                                        "r3"), 2.0)
        self.refused(R.GENERALIZATION_REFUSED, "C-1 and C-2 are one workload (same requirements_sha256, plan_baseline)",
                     L.generalization, [a, b, evaluating(3, done=3, read=3.0)])


if __name__ == "__main__":
    unittest.main()
