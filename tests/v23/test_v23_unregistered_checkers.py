"""PIN-57 Option C (owner ruling 2026-11-26 §3, ledger seq 14): the drift pins for what stays OUTSIDE cc.REGISTRY.

Always runs, in seconds, no gate. f5_gate and released_evidence are registered (57 -> 59) and covered by the Q0
round's own sweeps; f5_recorder (validation/v23/observe.py) is retained outside the registry ONLY while its
observation data cannot serve as qualification authority (docs/v2.3/evidence/PIN-57-MODULE-ROLES.md §3.3/§3.5), and
the B2 Tier-0 ground-truth modules are tooling, not checkers, until corpus.py --check becomes a gate (W6, the
promotion clause in q0_round.NOT_CHECKERS_V23). While they are outside the registry the Q0 anti-gaming sweeps
(tests/v23/test_v23_q0_round.py, Q0RoundV23) do not cover them, so this file pins:

* f5_recorder's calibration: cc.calibrate against its committed known-bad fixture, all three legs (the clean
  synthetic witness passes, the fixture is rejected for its named reason, an always-PASS mutant fails calibration);
* the retention CONDITION: no module or workflow outside validation/v23/impact.py passes `observations=` to the
  engine, `--observations` stays impact.py's own CLI input (validation/v23/observe.py may name it in prose — its
  docstring states this very condition), and impact.OBSERVATION_AUTHORITY stays the "none: ..." sentinel;
* the ground_truth absence: no validation, kernel or workflow file outside the package consumes it
  (validation/v23/q0_round.py NAMES the four files in its ruled NOT_CHECKERS_V23 list — naming, not consumption);
* the split itself: the registry carries the two ruled checkers, V23_CHECKERS carries exactly the recorder, and the
  seq-14 additions to NOT_CHECKERS_V23 are exactly the ruled five files.
"""
from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v23 import q0_round as Q  # noqa: E402

cc = Q.cc()


def _scan_files() -> list[pathlib.Path]:
    """Every file a gate could live in: the validators, the kernel, and the CI workflows (tests are not gates)."""
    return [*sorted((ROOT / "validation").rglob("*.py")), *sorted((ROOT / "aisef2").rglob("*.py")),
            *sorted((ROOT / ".github").rglob("*.yml")), *sorted((ROOT / ".github").rglob("*.yaml"))]


class UnregisteredCheckers(unittest.TestCase):
    """Ledger seq 14 (PIN-57 Option C): what stays outside the registry stays calibrated and stays unwired."""

    def test_the_registry_split_is_exactly_the_option_c_ruling(self):
        registered = {make().name for make in cc.REGISTRY}
        self.assertLessEqual({"f5_gate", "released_evidence"}, registered)
        self.assertEqual({make().name for make in cc.V23_CHECKERS}, {"f5_recorder"})
        self.assertNotIn("f5_recorder", registered)

    def test_the_seq14_scope_additions_are_exactly_the_ruled_five(self):
        seq13 = {"validation/v23/__init__.py", "validation/v23/ledger_digest.py",
                 "validation/v23/q0_round.py", "validation/v23/replay_v22.py"}
        self.assertEqual(Q.NOT_CHECKERS_V23 - seq13,
                         {"validation/v23/observe.py", "validation/v23/ground_truth/__init__.py",
                          "validation/v23/ground_truth/corpus.py", "validation/v23/ground_truth/labels.py",
                          "validation/v23/ground_truth/metrics.py"})

    def test_f5_recorder_stays_calibrated_against_its_committed_fixture(self):
        (make,) = cc.V23_CHECKERS
        r = cc.calibrate(make())
        self.assertTrue(r["clean_passes"], r)
        self.assertTrue(r["rejects_for_the_expected_reason"], r)
        self.assertTrue(r["calibrated"], r)
        self.assertFalse(cc.calibrate(cc.always_pass_mutant(make()))["calibrated"])

    def test_the_observations_input_of_the_engine_stays_unwired(self):
        owner = "validation/v23/impact.py"           # the parameter's module: API default None plus its own CLI
        docstring_ok = "validation/v23/observe.py"   # the recorder's docstring states the condition by name
        offenders = []
        for p in _scan_files():
            rel = p.relative_to(ROOT).as_posix()
            if rel == owner:
                continue
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if "observations=" in line or ("--observations" in line and rel != docstring_ok):
                    offenders.append(f"{rel}:{n}: {line.strip()}")
        self.assertEqual(offenders, [], "a gate wires observations into the engine: that re-opens PIN-57 Decision 2 "
                                        "for f5_recorder and needs registration/calibration or a new exact ruling")
        from validation.v23 import impact
        self.assertTrue(impact.OBSERVATION_AUTHORITY.startswith("none: "), impact.OBSERVATION_AUTHORITY)

    def test_no_gate_or_kernel_consumes_the_ground_truth_tooling(self):
        allowed = {"validation/v23/q0_round.py"}     # the ruled NOT_CHECKERS_V23 list names the files; it runs nothing
        offenders = []
        for p in _scan_files():
            rel = p.relative_to(ROOT).as_posix()
            if rel.startswith("validation/v23/ground_truth/") or rel in allowed:
                continue
            if "ground_truth" in p.read_text(encoding="utf-8"):
                offenders.append(rel)
        self.assertEqual(offenders, [], "a consumer of the ground-truth tooling appeared: the promotion clause "
                                        "(q0_round.NOT_CHECKERS_V23) requires registration and a new ruling first")


if __name__ == "__main__":
    unittest.main()
