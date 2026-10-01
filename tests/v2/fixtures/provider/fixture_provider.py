"""C2-P10 / WP-2.10.2 — a local, deterministic OpenAI-compatible fixture provider: the only provider attestation is
qualified against. It binds 127.0.0.1 on an ephemeral port, serves two routes, and never forwards anything:

    GET  /v1/models            {"data": [{"id", "owned_by"}...]}
    POST /v1/chat/completions  {"model": <served>, "system_fingerprint": <deployment>, "choices": [{"finish_reason"}]}

Its models, each the shape of a route class the alias detection must tell apart:

    fixture-model-1    a fixed model: listed, serves itself, one deployment (the `deployment` knob simulates a change)
    fixture-model-2    a second fixed model, the one the aliases resolve to
    fixture-combo      listed as owned_by "combo"; each call is served by the next model of a rotation
    fixture-alias      listed like a fixed model, but every call is served by fixture-model-2
    fixture-rotating   listed and served under its own id, but each call by another deployment (a per-call aggregate)
    fixture-unlisted   served under its own id and absent from the listing

    with FixtureProvider() as p:      # p.base_url, p.requests (every request path and model it received)
        ...
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTED = {"fixture-model-1": "fixture", "fixture-model-2": "fixture", "fixture-combo": "combo",
          "fixture-alias": "fixture", "fixture-rotating": "fixture"}
ROTATION = ("fixture-model-1", "fixture-model-2")


class FixtureProvider:
    def __init__(self, deployment: str = "fp_fixture_1") -> None:
        self.deployment = deployment
        self.requests: list[tuple[str, str | None]] = []
        self._calls: dict[str, int] = {}
        self._lock = threading.Lock()

    def answer(self, model: str) -> tuple[str, str]:
        """(served model, deployment) for one call to `model`."""
        with self._lock:
            n = self._calls[model] = self._calls.get(model, -1) + 1
        if model == "fixture-combo":
            return ROTATION[n % len(ROTATION)], "fp_combo"
        if model == "fixture-alias":
            return "fixture-model-2", "fp_fixture_2"
        if model == "fixture-rotating":
            return model, f"fp_rotating_{n % 2}"
        return model, self.deployment if model == "fixture-model-1" else f"fp_{model}"

    def __enter__(self) -> "FixtureProvider":
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                pass

            def _send(self, code: int, body: dict) -> None:
                data = json.dumps(body).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                provider.requests.append((self.path, None))
                if self.path != "/v1/models":
                    return self._send(404, {"error": "not found"})
                self._send(200, {"object": "list", "data": [{"id": k, "object": "model", "owned_by": v}
                                                            for k, v in LISTED.items()]})

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
                provider.requests.append((self.path, body.get("model")))
                if self.path != "/v1/chat/completions":
                    return self._send(404, {"error": "not found"})
                served, deployment = provider.answer(body.get("model", ""))
                self._send(200, {"id": "fixture", "object": "chat.completion", "model": served,
                                 "system_fingerprint": deployment,
                                 "choices": [{"index": 0, "finish_reason": "length",
                                              "message": {"role": "assistant", "content": "ok"}}],
                                 "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()
