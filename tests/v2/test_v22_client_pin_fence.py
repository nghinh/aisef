"""ROADMAP-2.2 D4 + G2 — the optional client_pin and client_fence settings. A pin is the review_ocr pattern on the
client binary (bytes before anything runs, re-checked at every session start); a fence is limits DECLARED to the
client through its environment (per-worktree OPENCODE_PERMISSION, run-scoped XDG data/state/cache — never CONFIG —
and an output-token ceiling), recorded as declared, never claimed as measured. Absent, both are exactly 2.0.0."""
from __future__ import annotations

import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from aisef2.app import client, settings

BASE = {"format": "aisef-v2-run/1", "client": "opencode", "route": "prov/m",
        "provider": {"name": "prov", "endpoint": "https://api.example/v1", "api_key_env": None,
                     "served_model": "m", "listed_owner": None, "model_limit": {"context": 10, "output": 5}},
        "client_env": [], "budget": {"provider_requests": 9, "turns": 9, "input_tokens": 9, "output_tokens": 9},
        "max_turns_per_session": 3,
        "limits": {"DEVELOPER": 1, "PLAN": 1, "ENVIRONMENT": 1, "PROVIDER": 1, "INTEGRATION": 1, "REVIEW": 1,
                   "SECURITY": 1},
        "timeouts_s": {"developer": 5, "reviewer": 5, "tool": 5, "probe": 5}, "preflight": {"chat_probes": 2}}


class PinSetting(unittest.TestCase):
    def test_absent_is_none_and_exactly_the_old_rule(self):
        s = settings.load(BASE)
        self.assertIsNone(s.client_pin)
        self.assertIsNone(s.client_fence)

    def test_the_pin_is_an_absolute_path_and_a_sha256(self):
        for bad in ({"exe": "opencode", "sha256": "a" * 64},            # not absolute
                    {"exe": "/x/opencode", "sha256": "A" * 64},         # not lowercase hex
                    {"exe": "/x/opencode", "sha256": "a" * 63},         # not 64
                    {"exe": "/x/opencode"},                             # not closed
                    {"exe": "/x/opencode", "sha256": "a" * 64, "extra": 1}):
            with self.assertRaises(settings.SettingsError):
                settings.load({**BASE, "client_pin": bad})
        s = settings.load({**BASE, "client_pin": {"exe": "/x/opencode", "sha256": "a" * 64}})
        self.assertEqual(s.client_pin, {"exe": "/x/opencode", "sha256": "a" * 64})


class FenceSetting(unittest.TestCase):
    def test_the_fence_is_closed_world_with_fixed_values(self):
        for bad in ({}, {"external_directory": "everything"}, {"xdg": "operator"}, {"output_token_max": 0},
                    {"unknown": 1}):
            with self.assertRaises(settings.SettingsError):
                settings.load({**BASE, "client_fence": bad})
        s = settings.load({**BASE, "client_fence": {"external_directory": "workspace-only", "xdg": "run-scoped",
                                                    "output_token_max": 64000}})
        self.assertEqual(s.client_fence["xdg"], "run-scoped")

    def test_run_scoped_xdg_moves_data_state_cache_and_never_config(self):
        plain = client.environment((), {"a": 1})
        scoped = client.environment((), {"a": 1}, xdg_home="/run/client-xdg")
        self.assertEqual(scoped["XDG_DATA_HOME"], str(pathlib.PurePath("/run/client-xdg", "data")))
        self.assertEqual(scoped["XDG_STATE_HOME"], str(pathlib.PurePath("/run/client-xdg", "state")))
        self.assertEqual(scoped["XDG_CACHE_HOME"], str(pathlib.PurePath("/run/client-xdg", "cache")))
        self.assertEqual(scoped.get("XDG_CONFIG_HOME"), plain.get("XDG_CONFIG_HOME"))
        self.assertEqual(client.environment((), {"a": 1}), plain)      # no xdg_home: byte-for-byte 2.0.0


class _Range:
    """A stand-in process range capturing the env the session builds; it runs nothing and leaves nothing."""
    seen: dict = {}

    def __init__(self, name, argv, cwd, env, output):
        _Range.seen = {"argv": argv, "cwd": cwd, "env": env}

    def start(self):
        pass

    def wait(self, timeout):
        return 0


class SessionFence(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="aisef-fence-"))
        self.exe = self.tmp / "opencode"
        self.exe.write_bytes(b"#!/bin/sh\nexit 0\n")
        self.budget = client.Budget({k: 9 for k in client.Budget.KEYS}, {k: 0 for k in client.Budget.KEYS},
                                    self.tmp / "logs")
        self.kw = {"model": "prov/m", "env": {"PATH": "/nowhere"}, "budget": self.budget, "turn_cap": 3,
                   "exe": str(self.exe)}

    def _run(self, **extra) -> dict:
        with mock.patch.object(client, "ProcessRange", _Range), \
                mock.patch.object(client, "_release_session", return_value=[]):
            return client.session("s", "p", str(self.tmp / "wt"), self.tmp / "logs" / "s.jsonl", 5.0,
                                  **self.kw, **extra)

    def test_the_fence_is_composed_per_worktree_and_said_to_be_declared_only(self):
        s = self._run(fence={"external_directory": "workspace-only", "xdg": "run-scoped",
                             "output_token_max": 64000, "allow": ("/out/repo",)})
        env = _Range.seen["env"]
        allow = json.loads(env["OPENCODE_PERMISSION"])["external_directory"]
        wt = str(self.tmp / "wt")
        self.assertEqual(allow["*"], "deny")
        self.assertEqual((allow[wt], allow[f"{wt}/**"], allow["/out/repo"], allow["/out/repo/**"]),
                         ("allow", "allow", "allow", "allow"))
        self.assertEqual(env["OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"], "64000")
        self.assertIn("declared to the client", s["fence"])
        self.assertIn("NOT measured", s["fence"])
        (self.tmp / "logs" / "s.jsonl").unlink()
        bare = self._run()
        self.assertNotIn("fence", bare)
        self.assertNotIn("OPENCODE_PERMISSION", _Range.seen["env"])

    def test_the_pin_is_rechecked_at_the_moment_of_use(self):
        good = hashlib.sha256(self.exe.read_bytes()).hexdigest()
        s = self._run(pin_sha256=good)
        self.assertEqual(s["pinned_sha256"], good)
        (self.tmp / "logs" / "s.jsonl").unlink()
        with self.assertRaises(client.SessionRefused) as c:
            self._run(pin_sha256="0" * 64)
        self.assertIn("client_pin at the moment of use", str(c.exception))


if __name__ == "__main__":
    unittest.main()
