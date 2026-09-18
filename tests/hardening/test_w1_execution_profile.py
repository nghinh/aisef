"""Negative controls for the W1 ExecutionProfile identity (owner decision "EXECUTION PROFILE NOT QUALIFIED", section 3).

W1 delivery qualification belongs to (Kernel, ExecutionProfile, Workload); a run copy must measure to its profile's exact
identity before the first model call. `measure` needs the frozen wheel and OpenCode, so these controls replace it with a
constructed identity and drive `profile_id` and `verify` to their answers — no run, no model, no network.
"""
from __future__ import annotations

import copy
import importlib.util
import os
import subprocess
import tempfile
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


WRAPPER = ROOT / "closure-evidence/hardening/w1/profiles/stage-env-ro-uv/bin/uv"
STAGE = {"resolved_uv": "closure-evidence/hardening/w1/profiles/stage-env-ro-uv/bin/uv", "wrapper_sha256": "w1",
         "real_uv": "/u/uv", "real_uv_version": "uv 0.11.3"}


class TestStageEnv(unittest.TestCase):
    """Owner decision "FIX SS-81 FAMILY", section 11: the reviewer/security dependency environment is part of the
    profile's identity; a profile that declares none keeps the id it always had."""

    def test_a_profile_without_a_stage_environment_keeps_its_id(self):
        self.assertEqual(ep.profile_id(BASE), ep.profile_id({**BASE, "stage_env": None}))

    def test_the_stage_environment_moves_the_id(self):
        self.assertNotEqual(ep.profile_id({**BASE, "stage_env": STAGE}),
                            ep.profile_id({**BASE, "stage_env": {**STAGE, "wrapper_sha256": "w2"}}))

    def _verify(self, profile_identity: dict, measured: dict) -> dict:
        m = {k: v for k, v in measured.items() if k != "route_resolution"}
        with mock.patch.object(ep, "measure", return_value=m):
            return ep.verify(profile_of(profile_identity), Path("/nonexistent"), Path("/nonexistent"))

    def test_a_copy_launched_without_the_profiles_wrapper_is_refused(self):
        plain = {"resolved_uv": "/u/uv", "wrapper_sha256": None, "real_uv": "/u/uv", "real_uv_version": "uv 0.11.3"}
        self.assertTrue(self._verify({**BASE, "stage_env": STAGE}, {**BASE, "stage_env": STAGE})["matches"])
        self.assertFalse(self._verify({**BASE, "stage_env": STAGE}, {**BASE, "stage_env": plain})["matches"])
        self.assertTrue(self._verify(BASE, {**BASE, "stage_env": plain})["matches"], "a profile without one ignores it")

    @unittest.skipUnless(os.name == "posix", "the wrapper is a POSIX shell script")
    def test_the_wrapper_makes_uv_read_only_for_the_verifier_sessions_only(self):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "uv"
            fake.write_text('#!/bin/sh\necho "F=${UV_FROZEN:-} S=${UV_NO_SYNC:-} E=${UV_PROJECT_ENVIRONMENT:-} A=$*"\n', encoding="utf-8")
            fake.chmod(0o755)
            base = {"PATH": os.environ.get("PATH", ""), "PROFILE_REAL_UV": str(fake), "PROFILE_VERIFIER_UV_ENV": "/outside"}

            def run(**env):
                return subprocess.run([str(WRAPPER), "run", "x.py"], env={**base, **env}, capture_output=True, text=True,
                                      check=True).stdout.strip()
            self.assertEqual(run(AISEF_DISALLOWED_TOOLS="Write,Edit"), "F=1 S=1 E=/outside A=run x.py")
            self.assertEqual(run(AISEF_DISALLOWED_TOOLS="Write,Edit", AISEF_STORY_ID="S-1"), "F= S= E= A=run x.py")
            self.assertEqual(run(AISEF_STORY_ID="S-1"), "F= S= E= A=run x.py")
            self.assertEqual(run(), "F= S= E= A=run x.py")

    @unittest.skipUnless(os.name == "posix", "the wrapper is a POSIX shell script")
    def test_stage_env_names_the_wrapper_on_path_and_the_real_uv_behind_it(self):
        with tempfile.TemporaryDirectory() as td:
            real = Path(td) / "real-uv"
            real.write_text('#!/bin/sh\necho "uv 9.9.9"\n', encoding="utf-8")
            real.chmod(0o755)
            wdir = Path(td) / "bin"
            wdir.mkdir()
            w = wdir / "uv"
            w.write_text(WRAPPER.read_text(encoding="utf-8").replace("/Users/nghinh/.local/bin/uv", str(real)), encoding="utf-8")
            w.chmod(0o755)
            got = ep.stage_env(f"{wdir}{os.pathsep}{td}")
            self.assertEqual((got["real_uv"], got["real_uv_version"]), (str(real), "uv 9.9.9"))
            self.assertEqual(got["wrapper_sha256"], ep._sha(w.read_bytes()))
            plain = ep.stage_env(td + os.pathsep)
            self.assertIsNone(plain["resolved_uv"], "no `uv` named on that path")
            self.assertEqual(ep.stage_env("/nonexistent-dir")["resolved_uv"], None)


if __name__ == "__main__":
    unittest.main()
