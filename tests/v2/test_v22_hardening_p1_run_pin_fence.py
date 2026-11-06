"""ROADMAP-2.2 wave-2 hardening P1 — run.execute client_pin / client_fence integration guard (owner #1 GO).

Pins four wave-2 survived-mutant gaps on `aisef2/app/run.py::execute`: the `getattr(settings,"client_pin",...)`
and `getattr(settings,"client_fence",...)` names, and the `pin_sha256` / `fence` session-kw wiring. No test
drove execute() with a pinned+fenced settings, so emptying a getattr name (→ always None) or dropping a kw
entry was indistinguishable from 'absent'. This drives the real, offline end-to-end path (the demo harness:
fake developer + loopback provider, no network, no credentials) with a pin and a fence declared. Shipped code
is correct; these assertions fail only if a regression reintroduces one of those mutations. No product change."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from aisef2.app import demo, settings
from aisef2.app import run as R


@unittest.skipUnless(os.name == "posix", "reuses the demo's shebang-started fake developer")
class RunExecutePinFence(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(tempfile.mkdtemp(prefix="aisef-p1-"))
        self.addCleanup(shutil.rmtree, self.t, ignore_errors=True)
        # the demo's offline XDG: the only provider is the loopback one, so the endpoint check matches
        (self.t / "xdg" / "opencode").mkdir(parents=True)
        (self.t / "xdg" / "opencode" / "opencode.json").write_text(json.dumps(
            {"provider": {"fakeprov": {"options": {"baseURL": demo.SETTINGS["provider"]["endpoint"],
                                                   "apiKey": "{env:AISEF_DEMO_NO_KEY}"}}}}), encoding="utf-8")
        self.client = self.t / "client" / "opencode"
        self.client.parent.mkdir()
        self.client.write_text(f"#!{sys.executable}\nBODIES = {demo.BODIES!r}\nTEST = {demo.TEST!r}\n" + demo.FAKE_CLIENT)
        self.client.chmod(0o755)
        self.good = hashlib.sha256(self.client.read_bytes()).hexdigest()
        (self.client.parent / "mode").write_text("correct")
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.t / "xdg")}):
            self.project, self.source = demo.build(self.t)

    def _execute(self, out, **extra):
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.t / "xdg")}):
            return R.execute(self.project, settings.load({**demo.SETTINGS, **extra}), self.source, out,
                             client_exe=str(self.client), transport=demo.loopback())

    def test_a_mismatched_client_pin_refuses_before_any_session(self):
        # 'client_pin' emptied → getattr(settings,"",None) is always None → the pre-run identity check is skipped
        # and a wrong binary runs unpinned. Shipped refuses, naming client_pin, before any session starts.
        with self.assertRaises(R.RunRefused) as c:
            self._execute(self.t / "pin-bad", client_pin={"exe": str(self.client), "sha256": "0" * 64})
        self.assertIn("client_pin", str(c.exception))

    def test_a_matched_pin_and_declared_fence_reach_every_session(self):
        rec = self._execute(self.t / "ok",
                            client_pin={"exe": str(self.client), "sha256": self.good},
                            client_fence={"external_directory": "workspace-only", "xdg": "run-scoped",
                                          "output_token_max": 64000})
        # the declared fence's run-scoped XDG dirs are built ('client_fence' emptied / the xdg mkdir drop)
        for sub in ("data", "state", "cache"):
            self.assertTrue((self.t / "ok" / "client-xdg" / sub).is_dir(),
                            f"fence run-scoped XDG '{sub}' was not built")
        # pin_sha256 reaches a session (the pin_sha256 kw-entry drop) and the fence is declared to a session
        # (the fence kw-entry drop). `any` tolerates preflight-probe sessions that carry neither.
        self.assertTrue(rec["sessions"], "the run recorded no sessions")
        self.assertTrue(any(s.get("pinned_sha256") == self.good for s in rec["sessions"]),
                        "no session carried the pinned sha256 (pin_sha256 kw entry dropped?)")
        self.assertTrue(any("declared to the client" in s.get("fence", "") for s in rec["sessions"]),
                        "no session carried the declared fence (fence kw entry dropped?)")


if __name__ == "__main__":
    unittest.main()
