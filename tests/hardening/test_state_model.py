"""Phase 6 — model-based / state-space testing.

Part 1 (`TestKernelModel`): the reference kernel model (`model.py`) is driven with N seeded random
traces (default 10,000; `AISEF_MODEL_TRACES` overrides) and the ten owner properties are asserted
after EVERY transition. A violation is a specification bug and a hard failure. Coverage of terminal
classes and transitions is written to a test-owned scratch file (`RESULTS`). The committed
`closure-evidence/hardening/state-model-results.json` is frozen V1 evidence and a test run never rewrites it.

Part 2 (`TestConformance`): the real `implement_story` is driven through the synthetic client on
scripted scenarios and its terminal class is compared with the model's. A deviation that is not a
registered defect is a NEW kernel defect and fails; a registered deviation must still deviate (when the
fix lands, the entry in KNOWN_DEVIATIONS must be removed in the same commit).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401

from tests.hardening import model as M  # noqa: E402

TRACES = int(os.environ.get("AISEF_MODEL_TRACES", "10000"))
#: Runtime coverage output — a test-owned scratch file, never closure-evidence/. The committed file of the same
#: name is frozen V1 evidence (PLAN-FINDING-001). It sits directly in the temp directory, which always exists:
#: TestConformance sorts first and writes without creating a parent, exactly as it did with the old path.
RESULTS = Path(tempfile.gettempdir()) / "aisef-state-model-results.json"


class TestKernelModel(unittest.TestCase):
    """Ten properties over TRACES seeded traces; each test filters the violations it owns."""

    violations: list[str] = []
    terminal: Counter = Counter()
    events: Counter = Counter()
    steps = 0

    @classmethod
    def setUpClass(cls):
        cls.violations, cls.terminal, cls.events, cls.steps = [], Counter(), Counter(), 0
        for seed in range(TRACES):
            k, bad = M.run_trace(seed)
            cls.violations.extend(bad)
            cls.terminal[f"{k.s.status}:{k.s.terminal_reason or k.s.stage}"] += 1
            for ev, _, _ in k.s.trace:
                cls.events[ev] += 1
            cls.steps += len(k.s.trace)
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        RESULTS.write_text(json.dumps({
            "traces": TRACES, "steps": cls.steps, "violations": cls.violations[:50], "violation_count": len(cls.violations),
            "terminal_classes": dict(cls.terminal.most_common()), "events_exercised": dict(cls.events.most_common()),
            "model": "tests/hardening/model.py (docs/ASSURANCE-KERNEL.md §6)",
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    def _only(self, prefix: str):
        bad = [v for v in self.violations if f": {prefix}:" in v or f" {prefix}/" in v]
        self.assertEqual(bad, [], f"{len(bad)} violations of {prefix} in {TRACES} traces; first: {bad[:3]}")

    def test_property_1_unrunnable_review_is_never_developer_quality(self): self._only("P1")
    def test_property_2_recovery_invalidates_dependent_evidence(self): self._only("P2")
    def test_property_3_no_pass_on_foreign_evidence(self): self._only("P3")
    def test_property_4_resume_keeps_the_baseline_within_the_epoch(self): self._only("P4")
    def test_property_5_noop_never_terminates_on_stale_evidence(self): self._only("P5")
    def test_property_6_running_needs_a_live_lease(self): self._only("P6")
    def test_property_7_complete_needs_every_proof(self): self._only("P7")
    def test_property_8_verification_never_mutates_the_candidate(self): self._only("P8")
    def test_property_9_plan_conflict_is_not_developer_work(self): self._only("P9")
    def test_property_10_environment_failure_is_not_behavioural_evidence(self): self._only("P10")

    def test_no_violation_at_all_and_every_event_and_terminal_class_was_reached(self):
        self.assertEqual(self.violations, [])
        every = {e for pool in M.EVENTS.values() for e in pool}
        self.assertEqual(every - set(self.events), set(), "an event the generator never produced is an untested transition")
        for cls_ in ("done:COMPLETE", "blocked:REVIEW_UNRUNNABLE", "blocked:owner declined: plan", "failed:did not pass gate",
                     "blocked:credential rejected", "blocked:isolation breach", "blocked:owner declined: merge"):
            self.assertIn(cls_, self.terminal, f"terminal class {cls_} never reached in {TRACES} traces")


# ------------------------------------------------------------ conformance against the real kernel

from tests.hardening import differential as D  # noqa: E402

# (label, developer steps, review steps, security steps, options) — the same vocabulary as the differential harness
SCENARIOS = [
    ("C1 happy path", ["CHANGED"], ["PASS"], ["PASS"], {}),
    ("C2 review unrunnable then pass", ["CHANGED"], ["UNRUNNABLE", "PASS"], ["PASS"], {}),
    ("C3 review unrunnable exhausted", ["CHANGED"], ["UNRUNNABLE"], ["PASS"], {}),
    ("C4 security unrunnable then pass", ["CHANGED"], ["PASS"], ["UNRUNNABLE", "PASS"], {}),
    ("C5 review block then pass", ["CHANGED"], ["BLOCK", "PASS"], ["PASS"], {}),
    ("C6 review stuck", ["CHANGED"], ["STUCK"], ["PASS"], {}),
    ("C7 developer no-op twice with nothing frozen", ["NOOP"], ["PASS"], ["PASS"], {}),
    ("C8 context exit then pass", ["CONTEXT", "CHANGED"], ["PASS"], ["PASS"], {}),
    ("C9 credential rejected", ["AUTH"], ["PASS"], ["PASS"], {}),
    ("C10 test tool unrunnable", ["CHANGED"], ["PASS"], ["PASS"], {"test_tool_missing": True}),
    ("C11 budget rejected in review", ["CHANGED"], ["BUDGET"], ["PASS"], {}),
    ("C12 scope violation then no-op", ["SCOPE_VIOLATION", "NOOP"], ["PASS"], ["PASS"], {}),
    ("C13 reviewer mutates then pass", ["CHANGED"], ["MUTATE", "PASS"], ["PASS"], {}),
    ("C14 security block then pass", ["CHANGED"], ["PASS"], ["BLOCK", "PASS"], {}),
    ("C15 trunk commit", ["TRUNK_COMMIT"], ["PASS"], ["PASS"], {}),
    ("C16 two out-of-scope blocks are a plan conflict", ["CHANGED"], ["BLOCK_OUTSIDE"], ["PASS"], {"max_retries": 2}),
    ("C17 red tests then green", ["CHANGED_RED", "CHANGED"], ["PASS"], ["PASS"], {}),
    ("C18 zero output on a retry", ["CHANGED", "ZERO_OUTPUT"], ["BLOCK", "PASS"], ["PASS"], {}),
]


class TestConformance(unittest.TestCase):
    """Real kernel (synthetic client, real worktree) vs the reference model on scripted scenarios. A difference
    must be attributed to a registered open defect (differential.KNOWN, emptied as families close); anything else
    is a NEW kernel defect. A registered deviation must still deviate — when the fix lands, its entry goes."""

    def test_real_kernel_matches_the_model_except_where_a_registered_defect_says_otherwise(self):
        results = []
        for label, dev, rev, sec, opt in SCENARIOS:
            sc = D.Scenario(0, dev, rev, sec, **opt)
            with self.subTest(scenario=label):
                real, model = D.real_run(sc), D.model_run(sc)
                diff = real.diff(model)
                known = D.attribute(sc)
                results.append({"scenario": label, "real": real.terminal, "model": model.terminal, "diff": diff,
                                "known_deviation": known})
                if known:
                    self.assertNotEqual(diff, [], f"{label}: the real kernel now agrees with the model — {known} is fixed; "
                                                  f"remove its rule from differential.KNOWN")
                else:
                    self.assertEqual(diff, [], f"{label}: real ≠ model (an unregistered kernel defect): {diff}\n"
                                               f"real events {real.events}\nmodel {model.events}")
        data = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
        data["conformance"] = results
        RESULTS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
