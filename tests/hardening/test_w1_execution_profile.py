"""Negative controls for the W1 ExecutionProfile identity (owner decision "EXECUTION PROFILE NOT QUALIFIED", section 3).

W1 delivery qualification belongs to (Kernel, ExecutionProfile, Workload); a run copy must measure to its profile's exact
identity before the first model call. `measure` needs the frozen wheel and OpenCode, so these controls replace it with a
constructed identity and drive `profile_id` and `verify` to their answers — no run, no model, no network.
"""
from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("execution_profile_for_tests", ROOT / "closure-evidence/hardening/w1/execution_profile.py")
ep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ep)

BASE = {
    "kernel": {"candidate_sha": "af94372d", "product_tree": "02a34e0e", "wheel_sha256": "2e08d43b"},
    "client": "opencode", "client_version": "1.18.31",
    "routes": {r: "9router/cx/gpt-5.6-sol" for r in ep.ROLES},
    "max_turns": 80, "max_retries": 2, "max_infra_retries": -1,
    "context_window": {r: {"context": 200000, "output": 32768} for r in ep.ROLES},
    "small_model": "9router/fast",
    "sandbox_tool_profile": {"sandbox.image": "aisef-verify-python:84adf1d8eaf9", "tools": {}, "capability_matrix_sha256": "m"},
    "guard_digest": "g", "prompt_catalog_digest": "p", "client_config_digest": "c", "cost_cap_usd": 80.0,
    "route_resolution": {r: {"route_kind": "FIXED_MODEL", "resolved_model": "gpt-5.6-sol"} for r in ep.ROLES},
}


def profile_of(identity: dict) -> dict:
    return {"profile": "PROFILE-TEST", "profile_id": ep.profile_id(identity), "identity": identity}


class TestProfileId(unittest.TestCase):
    def test_the_id_is_stable_for_equal_identities(self):
        self.assertEqual(ep.profile_id(BASE), ep.profile_id(copy.deepcopy(BASE)))

    def test_every_profile_field_moves_the_id(self):
        for field in ep.CONFIG_FIELDS:
            changed = copy.deepcopy(BASE)
            changed[field] = {"changed": field}
            self.assertNotEqual(ep.profile_id(BASE), ep.profile_id(changed), field)

    def test_the_resolved_model_moves_the_id(self):
        changed = copy.deepcopy(BASE)
        changed["route_resolution"]["developer"]["resolved_model"] = "MiniMax-M3"
        self.assertNotEqual(ep.profile_id(BASE), ep.profile_id(changed))

    def test_a_dynamic_route_is_a_different_profile_from_a_fixed_one(self):
        changed = copy.deepcopy(BASE)
        for r in ep.ROLES:
            changed["route_resolution"][r]["route_kind"] = "DYNAMIC_COMBO"
        self.assertNotEqual(ep.profile_id(BASE), ep.profile_id(changed))


class TestVerify(unittest.TestCase):
    def _verify(self, measured: dict) -> dict:
        m = {k: v for k, v in measured.items() if k != "route_resolution"}
        with mock.patch.object(ep, "measure", return_value=m):
            return ep.verify(profile_of(BASE), Path("/nonexistent"), Path("/nonexistent"))

    def test_an_identical_copy_matches(self):
        self.assertTrue(self._verify(copy.deepcopy(BASE))["matches"])

    def test_a_copy_left_on_the_old_turn_budget_is_refused(self):
        got = copy.deepcopy(BASE); got["max_turns"] = 40
        out = self._verify(got)
        self.assertFalse(out["matches"]); self.assertEqual(list(out["differences"]), ["max_turns"])

    def test_one_role_on_another_model_is_refused(self):
        got = copy.deepcopy(BASE); got["routes"]["reviewer"] = "9router/mycombo"
        out = self._verify(got)
        self.assertFalse(out["matches"]); self.assertIn("routes", out["differences"])

    def test_a_different_kernel_is_refused(self):
        got = copy.deepcopy(BASE); got["kernel"]["product_tree"] = "84014c98"
        self.assertFalse(self._verify(got)["matches"])

    def test_a_changed_client_configuration_is_refused(self):
        got = copy.deepcopy(BASE); got["client_config_digest"] = "someone edited opencode.json"
        self.assertFalse(self._verify(got)["matches"])


class TestRedaction(unittest.TestCase):
    def test_secrets_never_enter_the_digest_input(self):
        red = ep._redact({"provider": {"x": {"options": {"apiKey": "sk-live", "baseURL": "u"}}}, "token": "t"})
        self.assertEqual(red["provider"]["x"]["options"]["apiKey"], "<redacted>")
        self.assertEqual(red["token"], "<redacted>")
        self.assertEqual(red["provider"]["x"]["options"]["baseURL"], "u")


if __name__ == "__main__":
    unittest.main()
