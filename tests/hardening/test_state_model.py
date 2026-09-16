"""Phase 6 — model-based / state-space testing.

Part 1 (`TestKernelModel`): the reference kernel model (`model.py`) is driven with N seeded random
traces (default 10,000; `AISEF_MODEL_TRACES` overrides) and the ten owner properties are asserted
after EVERY transition. A violation is a specification bug and a hard failure. Coverage of terminal
classes and transitions is recorded in `closure-evidence/hardening/state-model-results.json`.

Part 2 (`TestConformance`): the real `implement_story` is driven through the synthetic client on
scripted scenarios and its terminal class is compared with the model's. A deviation that is not a
registered defect is a NEW kernel defect and fails; a registered deviation must still deviate (when the
fix lands, the entry in KNOWN_DEVIATIONS must be removed in the same commit).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import tests  # noqa: E402,F401

from aisef.clients.synthetic import Script, Step, SyntheticClientAdapter  # noqa: E402
from tests.hardening import model as M  # noqa: E402
from tests.test_implement import ImplementTestCase  # noqa: E402
from tests.test_retry_hygiene import HygieneCase  # noqa: E402

TRACES = int(os.environ.get("AISEF_MODEL_TRACES", "10000"))
RESULTS = ROOT / "closure-evidence/hardening/state-model-results.json"


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

def _expect(events: list[str]) -> tuple[bool, int, int]:
    k = M.Kernel(0)
    for ev in events:
        if k.s.terminal:
            break
        k.apply(ev)
    return (k.s.status in (M.VERIFIED, M.DONE), k.s.developer_sessions, k.s.quality_attempts)


class _Fresh(ImplementTestCase):
    def runTest(self):
        pass


def _real(client, *, worktree: bool = False, **cfg) -> tuple[bool, int, int]:
    """Run the real loop on a fresh project (or story worktree) and return the same triple."""
    case = HygieneCase("runTest") if worktree else _Fresh("runTest")
    case.setUp()
    try:
        if not worktree:
            subprocess.run(["git", "config", "user.email", "t@t"], cwd=case.project, check=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=case.project, check=True)
            out = case.implement(client, config=case.config(**cfg)) if cfg else case.implement(client)
        else:
            out = case.implement(client, retries=2)
        return (out.done, client.develop_calls, out.quality_attempts)
    finally:
        case.tearDown()


VIOL = {"ledgerlock/cli.py": "def main(argv=None):\n    return 0\n\n\ndef repair(argv):\n    return 0\n",
        "ledgerlock/ledger.py": "def repair_tail(lines):\n    return {\n        'ok': False}\n"}

SCENARIOS = [
    ("C1 happy path", Script(), {},
     ["DEVELOP_CHANGED", "TEST_PASS", "REVIEW_PASS", "SECURITY_PASS"], False),
    ("C2 review unrunnable then pass", Script(review=[Step.unrunnable(), Step.passes()]), {},
     ["DEVELOP_CHANGED", "TEST_PASS", "REVIEW_UNRUNNABLE", "REVIEW_PASS", "SECURITY_PASS"], False),
    ("C3 review unrunnable exhausted", Script(review=[Step.unrunnable()]), {},
     ["DEVELOP_CHANGED", "TEST_PASS", "REVIEW_UNRUNNABLE", "REVIEW_UNRUNNABLE", "REVIEW_UNRUNNABLE", "REVIEW_UNRUNNABLE"], False),
    ("C4 security unrunnable then pass", Script(security=[Step.unrunnable(), Step.passes()]), {},
     ["DEVELOP_CHANGED", "TEST_PASS", "REVIEW_PASS", "SECURITY_UNRUNNABLE", "SECURITY_PASS"], False),
    ("C5 review block then pass", Script(review=[Step.block(), Step.passes()]), {},
     ["DEVELOP_CHANGED", "TEST_PASS", "REVIEW_BLOCK", "DEVELOP_CHANGED", "TEST_PASS", "REVIEW_PASS", "SECURITY_PASS"], False),
    ("C6 review stuck", Script(review=[Step.stuck()]), {},
     ["DEVELOP_CHANGED", "TEST_PASS", "REVIEW_STUCK"], False),
    ("C7 developer no-op twice with nothing frozen", Script(developer=[Step.noop()]), {},
     ["DEVELOP_NOOP", "DEVELOP_NOOP"], False),
    ("C8 context window then changed", Script(developer=[Step.context(), Step.changed()]), {},
     ["DEVELOP_CONTEXT", "DEVELOP_CHANGED", "TEST_PASS", "REVIEW_PASS", "SECURITY_PASS"], False),
    ("C9 credential rejected", Script(developer=[Step.auth()]), {},
     ["DEVELOP_AUTH"], False),
    ("C10 test tool unrunnable", Script(), {"tools.test": "aisef-no-such-runner-xyz"},
     ["DEVELOP_CHANGED", "TEST_UNRUNNABLE", "TEST_UNRUNNABLE", "TEST_UNRUNNABLE", "TEST_UNRUNNABLE"], False),
    ("C11 review budget rejection", Script(review=[Step.budget(), Step.passes()]), {},
     ["DEVELOP_CHANGED", "TEST_PASS", "REVIEW_UNRUNNABLE", "REVIEW_PASS", "SECURITY_PASS"], False),
    ("C12 scope violation then honest no-op (D-035)", Script(developer=[Step.scope_violation(VIOL), Step.noop()]), {},
     ["DEVELOP_SCOPE_VIOLATION", "TEST_PASS", "REVIEW_PASS", "SECURITY_PASS", "DEVELOP_NOOP", "TEST_PASS", "REVIEW_PASS", "SECURITY_PASS"], True),
    ("C13 reviewer mutates then pass", Script(review=[Step.mutate(), Step.passes()]), {},
     ["DEVELOP_CHANGED", "TEST_PASS", "REVIEW_MUTATE", "REVIEW_PASS", "SECURITY_PASS"], False),
    ("C14 security block then pass", Script(security=[Step.block(), Step.passes()]), {},
     ["DEVELOP_CHANGED", "TEST_PASS", "REVIEW_PASS", "SECURITY_BLOCK", "DEVELOP_CHANGED", "TEST_PASS", "REVIEW_PASS", "SECURITY_PASS"], False),
    ("C15 developer commits on the trunk", Script(developer=[Step.trunk_commit()]), {},
     ["DEVELOP_TRUNK_COMMIT"], True),
]

#: scenario → registered defect whose fix will make the real kernel agree with the model
KNOWN_DEVIATIONS = {
    "C4 security unrunnable then pass": "SS-13",
    "C8 context window then changed": "SS-15",
    "C10 test tool unrunnable": "SS-14",
    "C11 review budget rejection": "SS-12",
    "C12 scope violation then honest no-op (D-035)": "D-035",
}


class TestConformance(unittest.TestCase):
    """Real kernel vs reference model on scripted scenarios (no model calls)."""

    def test_real_kernel_matches_the_model_except_where_a_registered_defect_says_otherwise(self):
        results = []
        for label, script, cfg, events, worktree in SCENARIOS:
            with self.subTest(scenario=label):
                expected = _expect(events)
                client = SyntheticClientAdapter(script)
                try:
                    actual = _real(client, worktree=worktree, **cfg)
                except Exception as e:  # a crash is the worst deviation
                    actual = (f"EXCEPTION {type(e).__name__}", client.develop_calls, -1)
                known = KNOWN_DEVIATIONS.get(label)
                results.append({"scenario": label, "expected": expected, "actual": actual, "known_deviation": known})
                if known:
                    self.assertNotEqual(actual, expected, f"{label}: the real kernel now agrees with the model — {known} is fixed; remove it from KNOWN_DEVIATIONS")
                else:
                    self.assertEqual(actual, expected, f"{label}: real (done, developer sessions, quality attempts) ≠ model — an unregistered kernel defect")
        out = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
        out["conformance"] = results
        RESULTS.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
