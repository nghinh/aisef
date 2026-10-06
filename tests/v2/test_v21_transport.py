"""V2.1 (A, V2-04): the preflight never follows a redirect with the provider key, and a session's stream is redacted
however the session ends. Measured on 2.0.0 by the 360° assessment (security W5, W8): urllib's default redirect
handler re-sent the Authorization header to the redirect target, and `client.session` redacted only after a normal
return — an interrupt or a failed budget read left the secret in the evidence. Loopback servers only; no provider."""

from __future__ import annotations

import http.server
import json
import pathlib
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import client, preflight  # noqa: E402


def _serve(handler) -> tuple[http.server.HTTPServer, str]:
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


class Redirect(unittest.TestCase):
    def setUp(self) -> None:
        self.seen: list[dict] = []
        seen = self.seen

        class Target(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(dict(self.headers))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"data": []}')

            def log_message(self, *a):
                pass
        self.target, target_url = _serve(Target)

        class Redirector(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", target_url + "/models")
                self.end_headers()

            def log_message(self, *a):
                pass
        self.redirector, self.url = _serve(Redirector)
        self.addCleanup(self.target.shutdown)
        self.addCleanup(self.redirector.shutdown)

    def test_a_redirect_is_refused_and_the_key_never_reaches_its_target(self):
        call = preflight.http_transport(self.url, "sk-test-secret-key-0001")
        code, body = call("/models")
        self.assertEqual(self.seen, [], "the redirect target received a request")
        self.assertEqual(code, 302)
        self.assertEqual(body.get("transport_error"), "redirect refused")

    def test_the_refusal_is_an_identity_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec = preflight.run("p/m", 2, preflight.http_transport(self.url, "sk-test-secret-key-0001"), pathlib.Path(tmp) / "pf")
        self.assertEqual(rec["verdict"], "OPAQUE")
        self.assertTrue(any("redirect refused" in p for p in rec["problems"]), rec["problems"])


SECRET = "operator-secret-value-0042"
#: a client that prints its environment's secret, then reports a step
CLIENT = f'''import json, sys
print(json.dumps({{"type": "text", "part": {{"text": "env: {SECRET}"}}}}), flush=True)
print(json.dumps({{"type": "step_finish", "part": {{"tokens": {{"input": 1, "output": 1}}}}}}), flush=True)
'''


class Redaction(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)
        exe = self.root / "fake-client"
        exe.write_text(f"#!{sys.executable}\n" + CLIENT)
        exe.chmod(0o755)
        self.exe = str(exe)
        self.budget = client.Budget({"provider_requests": 9, "turns": 9, "input_tokens": 999, "output_tokens": 999},
                                    {"provider_requests": 0, "turns": 0, "input_tokens": 0, "output_tokens": 0},
                                    self.root / "logs", lambda: 1)

    @unittest.skipUnless(sys.platform != "win32", "the fake client is a script started by its shebang")
    def test_an_interrupted_session_still_leaves_no_secret(self):
        log = self.root / "logs" / "s.jsonl"

        def interrupted(r, log_, *a, **k):
            r.wait(30)      # the client has printed the secret and exited
            raise KeyboardInterrupt
        with mock.patch.object(client, "wait_within", interrupted), self.assertRaises(KeyboardInterrupt):
            client.session("developer S1", "do it", str(self.root), log, 30, model="p/m", env={"PATH": ""},
                           budget=self.budget, turn_cap=5, exe=self.exe, secrets=(SECRET,))
        data = log.read_text(encoding="utf-8")
        self.assertNotIn(SECRET, data)
        self.assertIn("[REDACTED]", data)
        for line in data.splitlines():      # the stream is still JSON
            json.loads(line)


if __name__ == "__main__":
    unittest.main()
