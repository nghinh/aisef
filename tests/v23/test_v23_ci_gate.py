"""validation/v23/ci_gate.py — the TWO-TIER F5 CI policy (owner ruling 2026-11-22 §4; amendments/CI-TWO-TIER.md).

The real 994-target classify takes ~16 minutes and refuses a dirty tree, so NO test here runs it: today's real table
is the committed evidence docs/v2.3/evidence/F5-DISPOSITION-3/DISPOSITION.json (the engine's own --json output at the
integrated W1 head: 667 INVALIDATED R2, 327 UNRESOLVED I6, 0 reuse), and every fabricated table goes through the REAL
impact.report() over fabricated State rows, so its counts are derived the engine's way. impact.classify and
impact.report are mocked in every gate call; tree cleanliness is irrelevant here. The negative controls are mocked
everywhere except test_the_pinned_controls_load_and_pass, which runs the real four (toy repositories, ~11 s)."""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import re
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v23 import ci_gate, impact  # noqa: E402

DISPOSITION = json.loads((ROOT / "docs/v2.3/evidence/F5-DISPOSITION-3/DISPOSITION.json").read_text(encoding="utf-8"))
ACCEPTED = f"v2.2.0-accepted@{impact.BASE}"
INCOMPLETE = "EVIDENCE: INCOMPLETE (NOT QUALIFIED)"
COMPLETE = "EVIDENCE: COMPLETE (RC-TIER CHECK STILL REQUIRED)"


def row(target: str, state: str, component: str = "", basis: str = "", evidence: dict | None = None) -> impact.State:
    return impact.State(target, state, component, "r", basis, [], dict(evidence or {}), 1)


def doc_of(rows: list, base_sha: str = impact.BASE) -> dict:
    """A state table built by the REAL impact.report() (counts and by_component derived, never hand-written)."""
    run = impact.Run(rows)
    run.base, run.head = "BASE", "HEAD"
    run.base_sha, run.head_sha = base_sha, "f" * 40
    return json.loads(json.dumps(impact.report(run)))   # the json round-trip report()'s --json output takes


class Gate(unittest.TestCase):
    def gate(self, tier: str, doc, controls=(), registry=None) -> tuple[int, str]:
        """ci_gate.main with the engine mocked to answer `doc`: (exit code, stdout)."""
        if registry is None:
            rows = doc.get("states") if isinstance(doc, dict) else None
            registry = frozenset(s["target"] for s in rows) if isinstance(rows, list) else frozenset()
        out = io.StringIO()
        with mock.patch.object(ci_gate, "run_controls", lambda: list(controls)), \
                mock.patch.object(impact, "classify", lambda *a, **k: mock.sentinel.run), \
                mock.patch.object(impact, "report", lambda states, observations=None: doc), \
                mock.patch.object(ci_gate, "_registry", lambda: registry), \
                contextlib.redirect_stdout(out):
            code = ci_gate.main(["--tier", tier])
        return code, out.getvalue()

    def assert_no_passing_qualified(self, out: str) -> None:
        """The word QUALIFIED never appears except inside the mandated 'NOT QUALIFIED'."""
        for m in re.finditer("QUALIFIED", out):
            self.assertEqual(out[max(m.start() - 4, 0):m.start()], "NOT ", out[max(m.start() - 30, 0):m.end()])

    # ---- the develop tier on today's real table

    def test_develop_exits_0_on_todays_real_table_and_reports_it(self):
        code, out = self.gate("develop", DISPOSITION)
        self.assertEqual(code, 0, out)
        self.assertEqual(out.strip().splitlines()[-1], INCOMPLETE)   # the mandatory final line
        self.assertRegex(out, r"INVALIDATED\s+667 targets\s+17322 mutants")
        self.assertRegex(out, r"UNRESOLVED\s+327 targets\s+10078 mutants")
        self.assertRegex(out, r"MEASURED\s+0 targets")
        self.assertRegex(out, r"VERIFIED_REUSE\s+0 targets")
        self.assertRegex(out, r"INVALIDATED R2\s+667")               # the per-rule breakdown, as --classify prints it
        self.assertRegex(out, r"UNRESOLVED I6\s+327")
        self.assertNotIn("CI-GATE FAIL", out)
        self.assert_no_passing_qualified(out)

    def test_rc_exits_nonzero_on_todays_real_table_and_names_the_count(self):
        code, out = self.gate("rc", DISPOSITION)
        self.assertEqual(code, 1, out)
        self.assertIn("CI-GATE FAIL (rc tier): 994 of 994 targets lack valid MEASURED or VERIFIED_REUSE evidence", out)
        self.assertEqual(out.strip().splitlines()[-1], INCOMPLETE)

    def test_rc_passes_only_a_fully_measured_or_reused_table(self):
        doc = doc_of([row("a.py::f", "VERIFIED_REUSE", basis=ACCEPTED), row("b.py::g", "MEASURED", basis=ACCEPTED)])
        for tier in ("rc", "develop"):
            with self.subTest(tier):
                code, out = self.gate(tier, doc)
                self.assertEqual(code, 0, out)
                self.assertEqual(out.strip().splitlines()[-1], COMPLETE)
                self.assert_no_passing_qualified(out)
        doc = doc_of([row("a.py::f", "VERIFIED_REUSE", basis=ACCEPTED), row("b.py::g", "UNRESOLVED", "I6")])
        code, out = self.gate("rc", doc)
        self.assertEqual(code, 1, out)
        self.assertIn("1 of 2 targets lack valid MEASURED or VERIFIED_REUSE evidence", out)

    # ---- (a) checker malfunction

    def test_a_malformed_table_fails_either_tier(self):
        good = doc_of([row("a.py::f", "INVALIDATED", "R2"), row("b.py::g", "UNRESOLVED", "I6")])
        miscounted = json.loads(json.dumps(good))
        miscounted["counts"]["INVALIDATED"]["n"] += 1
        unknown = doc_of([row("a.py::f", "QUARANTINED"), row("b.py::g", "UNRESOLVED", "I6")])
        engine = doc_of([row("a.py::f", "UNRESOLVED", "engine"), row("b.py::g", "UNRESOLVED", "I6")])
        cases = {"counts do not sum to the rows": miscounted, "an unknown state": unknown,
                 "a row the engine raised on": engine, "an empty table": doc_of([]),
                 "not a table at all": None, "states missing": {"counts": {}}}
        for name, doc in cases.items():
            for tier in ("develop", "rc"):
                with self.subTest(f"{name} / {tier}"):
                    code, out = self.gate(tier, doc)
                    self.assertEqual(code, 2, out)
                    self.assertIn("CI-GATE FAIL (checker malfunction)", out)
                    self.assertNotIn("EVIDENCE:", out)   # a broken checker labels nothing, not even INCOMPLETE
        with self.subTest("the table does not cover the registry"):
            code, out = self.gate("develop", good, registry=frozenset({"a.py::f", "b.py::g", "zz.py::q"}))
            self.assertEqual(code, 2, out)
            self.assertIn("registry targets missing", out)

    # ---- (b) false-current reuse

    def test_false_current_reuse_fails_either_tier(self):
        obs = f"observation:{'a' * 64}@{impact.BASE}"
        cases = {
            "VERIFIED_REUSE with no acceptance basis": doc_of([row("a.py::f", "VERIFIED_REUSE")]),
            "a non-reuse row carrying an acceptance basis":
                doc_of([row("a.py::f", "INVALIDATED", "R2", basis=ACCEPTED)]),
            "an accepted basis naming another commit":
                doc_of([row("a.py::f", "VERIFIED_REUSE", basis=f"v2.2.0-accepted@{'1' * 40}")]),
            "the accepted label on a run whose basis is not the pinned v2.2.0 sha":
                doc_of([row("a.py::f", "VERIFIED_REUSE", basis=f"v2.2.0-accepted@{'1' * 40}")], base_sha="1" * 40),
            "an observation basis without the no-authority marking":
                doc_of([row("a.py::f", "VERIFIED_REUSE", basis=obs)]),
        }
        for name, doc in cases.items():
            for tier in ("develop", "rc"):
                with self.subTest(f"{name} / {tier}"):
                    code, out = self.gate(tier, doc)
                    self.assertEqual(code, 2, out)
                    self.assertIn("CI-GATE FAIL (false-current reuse)", out)
        for name, doc in {   # the engine's own forms pass
            "the pinned accepted basis": doc_of([row("a.py::f", "VERIFIED_REUSE", basis=ACCEPTED)]),
            "a calibration basis": doc_of([row("a.py::f", "VERIFIED_REUSE", basis=f"calibration@{'1' * 40}")],
                                          base_sha="1" * 40),
            "the sha-pinned ruling": doc_of([row("a.py::f", "VERIFIED_REUSE",
                                                 basis=f"ruling:{impact.RULING_ID}@{impact.RULING_SHA256}")]),
            "an observation basis with authority none":
                doc_of([row("a.py::f", "VERIFIED_REUSE", basis=obs,
                            evidence={"authority": impact.OBSERVATION_AUTHORITY})]),
        }.items():
            with self.subTest(name):
                code, out = self.gate("develop", doc)
                self.assertEqual(code, 0, out)

    # ---- (c) negative controls

    def test_a_broken_negative_control_fails_before_the_engine_runs(self):
        code, out = self.gate("develop", DISPOSITION, controls=["ran 3/4 controls, 1 failures"])
        self.assertEqual(code, 2, out)
        self.assertIn("CI-GATE FAIL (negative-control regression)", out)
        self.assertNotIn("F5 impact", out)   # no table from a gate whose checker is not demonstrably refusing
        self.assertNotIn("EVIDENCE:", out)

    def test_controls_that_cannot_be_loaded_fail_closed(self):
        with mock.patch.object(ci_gate, "CONTROLS",
                               ("tests.v23.test_v23_impact.ImpactTest.test_does_not_exist",)):
            self.assertNotEqual(ci_gate.run_controls(), [])

    def test_the_pinned_controls_load_and_pass(self):
        """The real four controls (R0, R1, R2-static, dirty tree) on toy repositories: the only slow test here."""
        self.assertEqual(ci_gate.run_controls(), [])


if __name__ == "__main__":
    unittest.main()
