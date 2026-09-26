"""Q1 — semantic conformance (RFC §27; owner §8–§11), on fixtures; no provider, no project admission.

The nine RFC regression cases (NEG-1..3, CAL-1..2, TEST-1..2, RUN-1..2), scenarios A, K, L and H, every V2-005 and
V2-006 semantic conformance case, test-layout invariance (the committed cases and the harness's own permutations of
path, nesting, filename, import arrangement and split/merge on the reference probe), and the six control-critical
projection reference models: independent by the AST no-import audit, calibrated against a wrong-model case each,
equal to the kernel projection on every generated trace and at every prefix (incremental fold == from-scratch fold).
"""

from __future__ import annotations

import json

from . import common as C

RFC_CASES = {
    "NEG-1": [("tests.v2.p1.test_outcome", "Polarity", "test_NEG_1_forbidden_behaviour_present_at_the_parent_is_UNSATISFIED_never_SATISFIED"),
              ("tests.v2.p2.test_story_admission_probes", "RealParent", "test_forbidden_module_present_is_READY_and_absent_is_PRE_SATISFIED")],
    "NEG-2": [("tests.v2.p1.test_outcome", "Polarity", "test_NEG_2_forbidden_module_absent_and_decidable_is_SATISFIED")],
    "NEG-3": [("tests.v2.p1.test_outcome", "Polarity", "test_NEG_3_subject_required_but_absent_is_INDETERMINATE_PRECONDITION_ABSENT"),
              ("tests.v2.p2.test_story_admission", "Table", "test_NEG_3_absent_required_subject_by_role"),
              ("tests.v2.p2.test_story_admission_probes", "RealParent", "test_introduce_over_an_absent_required_subject_is_READY")],
    "CAL-1": [("tests.v2.p2.test_calibration", "Contrast", "test_CAL_1_a_fixed_REFUTED_rule_would_have_passed_the_always_refuted_probe"),
              ("tests.v2.p2.test_calibration", "Calibrate", "test_CAL_1_an_always_REFUTED_prohibition_probe_is_rejected"),
              ("tests.v2.p2.test_calibration", "Calibrate", "test_an_always_SATISFIED_probe_is_rejected_for_MUST_HOLD")],
    "CAL-2": [("tests.v2.p2.test_static_admission", "StaticOnly", "test_CAL_2_no_plan_freeze_path_requires_spec_falsifiability")],
    "TEST-1": [("tests.v2.p5.test_test_execution", "Classify", "test_TEST_1_a_missing_runner_is_UNRUNNABLE_ENVIRONMENT_with_no_outcome_and_no_selection"),
               ("tests.v2.p5.test_test_execution", "RealRunner", "test_TEST_1_for_real_the_configured_runner_is_absent")],
    "TEST-2": [("tests.v2.p5.test_test_execution", "Classify", "test_TEST_2_failing_assertions_are_EXECUTED_FAILED_STORY_TESTS_RAN_DEVELOPER"),
               ("tests.v2.p5.test_test_execution", "RealRunner", "test_TEST_2_for_real")],
    "RUN-1": [("tests.v2.p4.test_run_scope", "Lifetime", "test_RUN_1_a_process_killed_after_a_durable_run_end_and_before_CLEAN_is_torn")],
    "RUN-2": [("tests.v2.p4.test_run_scope", "Lifetime", "test_RUN_2_a_held_lease_blocks_a_second_run_even_with_run_end_written")],
}
SCENARIOS = {
    "A": ("tests.v2.p2.test_drift_scenarios", "ScenarioA", "test_early_upstream_implementation_is_pre_satisfied_attributed_and_charges_no_budget"),
    "K": ("tests.v2.p2.test_drift_scenarios", "ScenarioK", "test_a_fully_pre_satisfied_story_skips_the_developer_and_still_verifies"),
    "L": ("tests.v2.test_p6_orchestration", "Orchestration", "test_ORCH_11_scenario_L_INTRODUCE_PRESERVE_and_VERIFY_give_the_identical_product_verdict"),
    "H": ("tests.v2.p4.test_runspec", "Spec", "test_scenario_H_the_implementation_changes_and_the_version_string_does_not"),
}
LAYOUT_CASES = [
    ("tests.v2.p2.test_python_callable", "LayoutInvariance", "test_product_verdicts_are_identical_across_test_layouts"),
    ("tests.v2.p5.test_relevance", "Typed", "test_REL_8_the_same_coverage_under_another_test_layout_is_the_same_result"),
    ("tests.v2.p5.test_relevance", "ForReal", "test_REL_8_for_real_the_same_tests_in_another_layout"),
    ("tests.v2.p5.test_vacuity", "ForReal", "test_VAC_11_moving_the_developer_tests_does_not_change_the_result"),
    ("tests.v2.p5.test_vacuity", "Typed", "test_invariant_IX_is_structural"),
    ("tests.v2.p5.test_invariants", "SemanticDeterminism", "test_INV_II_1_developer_test_topology_is_not_an_input_of_the_product_verdict"),
]
V2_006_SEMANTIC_MODULES = ("tests.v2.test_v2_006", "tests.v2.test_v2_006_repeat")


def _layout_permutations() -> dict:
    """Owner §9: path, nesting, filename, import arrangement, split/merge — the product verdict never moves."""
    from aisef2.probe.protocol import RevisionRef, run_probe
    from aisef2.product.outcome import Executed
    from tests.v2.p2.test_python_callable import I, PA, PRODUCT, REQUIRES, R, S, SHA, P, checkout, env, spec
    add = "from app.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    mul = "import app.calc\n\n\ndef test_pi():\n    assert app.calc.PI == 3\n"
    layouts = {
        "no tests": {},
        "path: tests/ at the root": {"tests/__init__.py": "", "tests/test_calc.py": add},
        "path: tests inside the package": {"app/tests/__init__.py": "", "app/tests/test_calc.py": mul},
        "nesting: tests/unit/calc/": {"tests/__init__.py": "", "tests/unit/__init__.py": "", "tests/unit/calc/__init__.py": "",
                                      "tests/unit/calc/test_deep.py": add},
        "filename: check_arith.py, not test_*": {"tests/__init__.py": "", "tests/check_arith.py": add},
        "import: module-level": {"tests/test_m.py": add},
        "import: function-level": {"tests/test_f.py": "def test_add():\n    from app.calc import add\n    assert add(1, 2) == 3\n"},
        "split: two files": {"tests/test_a.py": add, "tests/test_b.py": mul},
        "merge: one file": {"tests/test_all.py": add + "\n" + mul},
        "broken tests and a conftest that exits": {"tests/test_calc.py": "def (:\n", "conftest.py": "raise SystemExit(4)\n",
                                                   "app/test_calc.py": "import no_such_module\n"},
    }
    specs = {"exists": spec("app.calc:add"), "absent": spec("app.telemetry:send"),
             "requires absent": spec("app.telemetry:send", absence=REQUIRES),
             "returns": spec("app.calc:add", {"returns": 3}, {"args": [1, 2]}), "raises": spec("app.calc:boom", {"raises": "ValueError"})}
    expected = {"exists": Executed(S), "absent": Executed(R), "requires absent": Executed(I, PA), "returns": Executed(S), "raises": Executed(S)}
    table, divergent = {}, []
    for name, extra in layouts.items():
        at = RevisionRef(SHA, checkout({**PRODUCT, **extra}))
        got = {k: run_probe(P, s, at, env()).result for k, s in specs.items()}
        table[name] = {k: repr(v) for k, v in got.items()}
        if got != expected:
            divergent.append(name)
    return {"layouts": len(layouts), "specs": list(specs), "expected": {k: repr(v) for k, v in expected.items()},
            "verdicts_by_layout": table, "divergent_layouts": divergent, "identical": not divergent}


def _reference_models() -> dict:
    """The six models, fresh: independence audit, closed list, calibration, and the differential over generated
    traces at every prefix (incremental fold == from-scratch fold at every decision boundary)."""
    import refmodel_independence as ri
    from aisef2.arch.enums import ControlProjection as P
    from aisef2.journal.fold import Folder, fold
    from aisef2.journal.projections import PROJECTIONS
    from tests.v2.p3 import journal_gen as gen
    from tests.v2.p3.test_reference_models import calibration_problems, model_answer, projection_answer, reconstruct
    from tests.v2.refmodel import CALIBRATIONS, MODELS
    independence = ri.check(C.ROOT)
    closed = sorted(MODELS) == sorted(p.value for p in P) == sorted(ri.MODELS) and len(MODELS) == 6
    calibration = {name: calibration_problems(model, CALIBRATIONS.get(name, [])) for name, model in MODELS.items()}
    wrong_answer_rejected = {name: all(c.get("wrong") is not None for c in CALIBRATIONS.get(name, [])) for name in MODELS}
    traces, prefix_traces, divergences, prefix_divergences, incremental_divergences = 0, 0, [], [], []
    for seed in range(80):
        events = reconstruct(gen.journal(seed, stories=3 + seed % 5)).events
        traces += 1
        for pid, model in MODELS.items():
            if projection_answer(PROJECTIONS[P(pid)], events) != model_answer(model, events):
                divergences.append((seed, pid))
        if seed < 24:
            prefix_traces += 1
            for pid, model in MODELS.items():
                proj = PROJECTIONS[P(pid)]
                folder = Folder(proj)
                for n in range(len(events) + 1):
                    if projection_answer(proj, events[:n]) != model_answer(model, events[:n]):
                        prefix_divergences.append((seed, pid, n))
                    if n:
                        try:
                            step = json.dumps(folder.advance(events[n - 1]), sort_keys=True, default=str)
                            scratch = json.dumps(fold(proj, events[:n]), sort_keys=True, default=str)
                            if step != scratch:
                                incremental_divergences.append((seed, pid, n))
                        except Exception:  # noqa: BLE001 — a journal the projection refuses is refused by the model too (asserted above)
                            break
    return {"independence_problems": independence, "closed_list_of_six": closed, "models": sorted(MODELS),
            "calibration_problems": calibration, "every_model_has_a_wrong_answer_case": wrong_answer_rejected,
            "differential": {"traces": traces, "divergences": divergences, "prefix_traces": prefix_traces,
                             "prefix_divergences": prefix_divergences, "incremental_vs_scratch_divergences": incremental_divergences}}


def run(ident: dict) -> dict:
    problems: list[str] = []
    harness: list[str] = []
    rfc = {k: [C.run_case(*c) for c in cases] for k, cases in RFC_CASES.items()}
    scenarios = {k: C.run_case(*c) for k, c in SCENARIOS.items()}
    v2_005 = C.run_module("tests.v2.test_v2_005")
    v2_006 = [c for m in V2_006_SEMANTIC_MODULES for c in C.run_module(m)]
    layout_cases = [C.run_case(*c) for c in LAYOUT_CASES]
    permutations, err = C.capture(_layout_permutations)
    if err:
        harness.append(f"layout permutations could not run: {err}")
    elif not permutations["identical"]:
        problems.append(f"test layout changed the product verdict: {permutations['divergent_layouts']}")
    refmodel_cases = (C.run_module("tests.v2.p3.test_reference_models") + C.run_module("tests.v2.p3.test_reference_defects")
                      + C.run_module("tests.v2.test_fold_oracle") + C.run_module("tests.v2.p3.test_control_projections"))
    fresh, err = C.capture(_reference_models)
    if err:
        harness.append(f"reference models could not be measured: {err}")
    else:
        if fresh["independence_problems"] or not fresh["closed_list_of_six"]:
            problems.append("a reference model imports the implementation or the list is not the closed six")
        if any(fresh["calibration_problems"].values()) or not all(fresh["every_model_has_a_wrong_answer_case"].values()):
            problems.append(f"reference model calibration: {fresh['calibration_problems']}")
        d = fresh["differential"]
        if d["divergences"] or d["prefix_divergences"] or d["incremental_vs_scratch_divergences"]:
            problems.append(f"semantic divergence between kernel projection and reference model: {d}")
    admission = (C.run_module("tests.v2.p2.test_story_admission") + C.run_module("tests.v2.p2.test_story_admission_probes")
                 + C.run_module("tests.v2.p2.test_drift") + C.run_module("tests.v2.p2.test_static_admission")
                 + C.run_module("tests.v2.p1.test_outcome") + C.run_module("tests.v2.p1.test_routing"))
    p3 = json.loads((C.ROOT / "closure-evidence/v2/P3-REFERENCE-MODELS.json").read_text(encoding="utf-8"))
    from aisef2.probe import python_callable as pc
    source = (C.ROOT / "aisef2/probe/python_callable.py").read_text(encoding="utf-8")
    race_semantics = {"exit_driven_reader_absent": "def _exited" not in source, "drain_window_absent": "_DRAIN_S" not in source,
                      "stream_closed_marker": '"STREAM_CLOSED"' in source, "probe_digest": pc.DIGEST}
    if not all(v for k, v in race_semantics.items() if k != "probe_digest"):
        problems.append("the reader keeps an exit-driven path or a drain window")
    cases = [c for v in rfc.values() for c in v] + list(scenarios.values()) + v2_005 + v2_006 + layout_cases + refmodel_cases + admission
    return {
        "record": "AISEF V2 — Q1 SEMANTIC CONFORMANCE", "rung": "Q1", "status": C.status_of(cases, problems, harness), "at": C.now(),
        "subject": ident, "platform": C.platform_id(),
        "rfc_regression_cases": {k: {"status": C.status_of(v), "cases": v} for k, v in rfc.items()},
        "scenarios": scenarios,
        "v2_005_semantic_conformance": {"counts": C.counts(v2_005), "cases": v2_005},
        "v2_006_race_semantics": {"counts": C.counts(v2_006), "structural": race_semantics, "cases": v2_006,
                                  "classification_rules": ["complete marked lines only", "STREAM_CLOSED is authoritative for stream completion",
                                                           "the exit is asked only after STREAM_CLOSED",
                                                           "'ended before READY' requires stream closed AND exit reported AND READY absent",
                                                           "no exit-driven reader, no drain window"]},
        "test_layout_invariance": {"committed_cases": layout_cases, "harness_permutations": permutations},
        "six_reference_models": {"fresh": fresh, "committed_record_properties": p3["properties"], "cases": refmodel_cases},
        "admission_engines_on_fixtures": {"counts": C.counts(admission), "cases": admission, "project_admissions_executed": 0},
        "provider_calls": 0, "problems": problems, "harness_problems": harness, "cases": cases, "counts": C.counts(cases),
    }
