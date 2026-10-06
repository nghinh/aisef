"""V2.1 (E): the experiment harness (validation/experiments/harness.py), offline — the fake client of test_app_run plays
the agent of arm `direct`; nothing reaches a provider.

Frozen manifests (sealed, refused once edited, refused from a dirty tree), pairs that may differ only in the variable
under test, arm `direct` (the client once on the public task; the harness commits what it left), the hidden evaluator
run by AISEF's probes on the frozen candidate, the leak scan, the result record and its offline replay."""

from __future__ import annotations

import copy
import json
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle_cli, client, settings  # noqa: E402
from tests.v2.test_app_run import ROUTE, SETTINGS, ProductBase, git  # noqa: E402
from validation.experiments import harness as H  # noqa: E402

#: the hidden evaluator: one approved contract no arm is shown (add(10, -4) == 6, not the public example)
EVALUATOR = {"format": "aisef-v2-authoring/1", "name": "calc-hidden", "description": "hidden evaluator",
             "requirements_document": {"path": "docs/requirements.md"}, "product_roots": ["app", "tests"], "baseline": "HEAD",
             "requirements": [{"id": "R-ADD", "text": "add returns the sum", "source": "docs/requirements.md 1.1"}],
             "contracts": [{"id": "BC-HIDDEN-ADD", "requirement_ids": ["R-ADD"],
                            "subject": {"kind": "python_callable", "locator": "app.calc:add"},
                            "stimulus": {"args": [10, -4]}, "observable": {"returns": 6, "within_s": 10},
                            "polarity": "MUST_HOLD", "subject_absence": "REQUIRES_SUBJECT", "rationale": "hidden: 10 + -4"}],
             "stories": {"H": {"depends_on": [], "tests": ["tests/test_add.py"], "criteria": [
                 {"id": "H-ADD", "contract": "BC-HIDDEN-ADD", "role": "INTRODUCE", "depends_on": [], "why": "hidden",
                  "facts": {"requirement": "R-ADD", "section": "§1", "clause": "1.1", "clause_text": "add", "subject": "add"}}]}}}


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class Experiment(ProductBase):
    def setUp(self) -> None:
        super().setUp()
        doc, _ = bundle_cli.seal(EVALUATOR, repo=self.tmp / "source")
        self.evaluator = bundle_cli.approve(doc, "BC-HIDDEN-ADD", "human:experiment-owner", 1.0)
        self.evaluator_path = self.tmp / "hidden" / "evaluator.json"
        self.evaluator_path.parent.mkdir()
        self.evaluator_path.write_text(json.dumps(self.evaluator), encoding="utf-8")
        self.control = self.manifest("direct", {"policy": "none"}, ["opencode", "run", "<task>"])
        self.treatment = self.manifest("aisef", {"policy": "aisef run"}, ["aisef", "run", "..."])

    def manifest(self, arm, value, command):
        return H.seal({
            "format": H.FORMAT, "experiment_id": f"E-1-{arm}", "parent_experiment_id": None,
            "pair": {"pair_id": "P-1", "arm": arm}, "workload": {"id": "calc", "requirements_sha256": "r" * 64},
            "source": H.source_identity(self.tmp / "source", "HEAD"),
            "evaluator": H.evaluator_identity(self.evaluator_path), "bundle": {"sha256": "b" * 64}, "policy": {"sha256": "p" * 64},
            "command": {"argv": command, "sha256": H.sha(H.canonical(command))},
            "client": {"name": "opencode", "version": "0.0.0-fake", "adapter_version": "aisef2.app.client"},
            "model": {"declared": ROUTE, "route": ROUTE, "identity_confidence": "unverified", "reason": "a fake provider"},
            "environment": {"python": "3", "network": "none", "env_allowlist": ["PATH"]},
            "variable_under_test": {"name": "orchestration", "value": value},
            "limits": {"wall_s": 600, "tokens": 100000, "usd": None, "turns": 50},
            "stop_rule": {"kind": "fixed_n", "n": 1}, "created_at": "2026-10-06T00:00:00Z"})

    def test_a_manifest_is_sealed_and_an_edit_breaks_the_seal(self):
        self.assertEqual(H.check(self.control), [])
        edited = copy.deepcopy(self.control)
        edited["limits"]["tokens"] = 10**9
        self.assertIn("the seal does not bind this content: a frozen manifest is never edited", H.check(edited))
        exposed = H.seal({**self.control, "evaluator": {**self.control["evaluator"], "exposed_to_developer": True}})
        self.assertTrue(any("hidden" in p for p in H.check(exposed)))

    def test_a_pair_differs_in_the_variable_under_test_only(self):
        self.assertEqual(H.pair_problems(self.control, self.treatment), [])
        richer = H.seal({**self.treatment, "limits": {**self.treatment["limits"], "tokens": 200000}})
        self.assertTrue(any("limits.tokens" in p for p in H.pair_problems(self.control, richer)))

    def test_the_source_is_a_clean_commit(self):
        (self.tmp / "source" / "dirty.txt").write_text("x")
        with self.assertRaises(ValueError):
            H.source_identity(self.tmp / "source", "HEAD")

    def test_the_direct_arm_from_task_to_evaluated_result_and_its_replay(self):
        st = settings.load(SETTINGS)
        budget = client.Budget(st.budget, {k: 0 for k in client.Budget.KEYS}, self.tmp / "direct" / "sessions")
        kw = {"model": st.route, "env": client.environment(st.client_env, client.overlay(st.route, st.model_limit)),
              "budget": budget, "turn_cap": st.max_turns_per_session}
        arm = H.direct_arm(self.control, self.tmp / "direct", task="Implement docs/requirements.md.",
                           client_exe=str(self.client), session_kw=kw, timeout_s=60)
        self.assertTrue(arm["changed"])
        ws = self.tmp / "direct" / "ws"
        self.assertIn("def add", git(ws, "show", f"{arm['candidate']}:app/calc.py"))
        evaluation = H.evaluate(ws, arm["candidate"], self.evaluator)
        self.assertEqual((evaluation["total"], evaluation["satisfied"]), (1, 1))
        leaked = H.leaks(self.tmp / "direct" / "sessions", self.evaluator)
        self.assertEqual(leaked, [])
        from aisef2.app import usage
        u = usage.usage(self.tmp / "direct", [], None, {})
        rec = H.result(self.control, arm, evaluation, u, leaked)
        self.assertEqual((rec["manifest_sha256"], rec["escaped_defects"], rec["valid"], rec["usage"]["cost"]["value"]),
                         (self.control["manifest_sha256"], [], True, None))
        self.assertEqual(H.replay(rec, ws, self.evaluator), [])
        # the baseline (no change) is refuted by the same hidden evaluator: what the arm added is what was measured
        base = H.evaluate(ws, self.control["source"]["commit"], self.evaluator)
        self.assertEqual(base["satisfied"], 0)

    def test_a_session_that_saw_the_hidden_stimulus_invalidates_the_result(self):
        sessions = self.tmp / "s"
        sessions.mkdir()
        (sessions / "x.developer.1.jsonl").write_text(json.dumps({"type": "text", "part": {"text": json.dumps(
            {"args": [10, -4]}, sort_keys=True)}}) + "\n", encoding="utf-8")
        self.assertEqual(H.leaks(sessions, self.evaluator), [{"session": "x.developer.1.jsonl", "strings": 1}])


if __name__ == "__main__":
    unittest.main()
