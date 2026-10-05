"""V2.0 RC2 (S6-SMOKE-1-PREFLIGHT-OPAQUE): the provider preflight's fix, with deterministic cases — no clock, no
randomness, no machine state, no network beyond one loopback server.

* http_transport sends "stream": false on every POST (without it the router answered RC1's probe as an event stream:
  200, text/event-stream, a JSON object followed by "data: [DONE]"), and a failed request keeps its HTTP status — 0 only
  when no HTTP answer came — with its error or parse class and content type;
* preflight.run carries that provenance into the ledger and the observation, for the listing and every probe;
* identity_problems names it.

A file of its own, first in exactly the kill sets of preflight.run and preflight.identity_problems, so every other S2
result keeps a byte-identical kill-test closure (validation/qualification/s2_mutation_record.py)."""

from __future__ import annotations

import email.message
import http.server
import io
import json
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from aisef2.app import preflight  # noqa: E402

ROUTE = "router/up/model-1"
LISTING = {"data": [{"id": "up/model-1", "owned_by": "up"}]}
ANSWER = {"model": "model-1", "system_fingerprint": "fp-1", "usage": {"prompt_tokens": 9, "completion_tokens": 1}}
#: what the router answered RC1's probe (closure-evidence/v2/release/smoke/OBS-S6-1/diagnostic/A.json), shortened
EVENT_STREAM = (b'{"id":"x","object":"chat.completion","model":"model-1","choices":[{"index":0,"message":{"role":"assistant",'
                b'"content":"ok"},"finish_reason":"stop"}],"usage":{"prompt_tokens":90,"completion_tokens":9}}data: [DONE]\n\n')


def _headers(content_type: str | None) -> email.message.Message:
    h = email.message.Message()
    if content_type:
        h["Content-Type"] = content_type
    return h


class _Answer:
    def __init__(self, status: int, content_type: str | None, raw: bytes | Exception):
        self.status, self.headers, self._raw = status, _headers(content_type), raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        if isinstance(self._raw, Exception):
            raise self._raw
        return self._raw


class Transport(unittest.TestCase):
    """aisef2.app.preflight.http_transport: the request it makes and what it returns for each kind of answer."""

    def call(self, answer, path="/chat/completions", body=None, **kw):
        seen = []

        def urlopen(req, timeout):
            seen.append((req, timeout))
            if isinstance(answer, Exception):
                raise answer
            return answer
        with mock.patch.object(preflight.urllib.request, "urlopen", urlopen):
            got = preflight.http_transport("https://router.invalid/v1", "k-1", **kw)(path, body)
        return got, seen

    def test_a_post_asks_for_one_json_answer_and_a_get_sends_no_body(self):
        body = {"model": "up/model-1", "max_tokens": 16}
        got, seen = self.call(_Answer(200, "application/json", json.dumps(ANSWER).encode()), body=body)
        self.assertEqual(got, (200, ANSWER))
        req, timeout = seen[0]
        self.assertEqual((req.full_url, req.get_method(), timeout), ("https://router.invalid/v1/chat/completions", "POST", 60.0))
        self.assertEqual(req.data, b'{"model": "up/model-1", "max_tokens": 16, "stream": false}')
        self.assertEqual(body, {"model": "up/model-1", "max_tokens": 16})          # the caller's body is not changed
        self.assertEqual(sorted(req.header_items()), [("Authorization", "Bearer k-1"), ("Content-type", "application/json")])
        got, seen = self.call(_Answer(200, "application/json", json.dumps(LISTING).encode()), path="/models", timeout_s=7.0)
        self.assertEqual(got, (200, LISTING))
        self.assertEqual((seen[0][0].full_url, seen[0][0].get_method(), seen[0][0].data, seen[0][1]),
                         ("https://router.invalid/v1/models", "GET", None, 7.0))

    def test_an_empty_answer_is_an_empty_document(self):
        self.assertEqual(self.call(_Answer(200, None, b""), body={})[0], (200, {}))

    def test_an_answer_that_is_not_one_json_document_keeps_its_status_and_says_why(self):
        self.assertEqual(self.call(_Answer(200, "text/event-stream", EVENT_STREAM), body={})[0],
                         (200, {"transport_error": "JSONDecodeError", "content_type": "text/event-stream"}))
        self.assertEqual(self.call(_Answer(200, "text/html", b"<html>challenge</html>"), body={})[0],
                         (200, {"transport_error": "JSONDecodeError", "content_type": "text/html"}))
        self.assertEqual(self.call(_Answer(200, "application/json", b"\xff\xfe"), body={})[0],
                         (200, {"transport_error": "UnicodeDecodeError", "content_type": "application/json"}))
        self.assertEqual(self.call(_Answer(200, "application/json", ConnectionResetError("reset")), body={})[0],
                         (200, {"transport_error": "ConnectionResetError", "content_type": "application/json"}))

    def test_an_http_error_keeps_its_status_and_content_type(self):
        err = urllib.error.HTTPError("https://router.invalid/v1/chat/completions", 429, "Too Many Requests",
                                     _headers("application/json"), io.BytesIO(b'{"error": "slow down"}'))
        self.assertEqual(self.call(err, body={})[0], (429, {"transport_error": "HTTPError", "content_type": "application/json"}))
        bare = urllib.error.HTTPError("https://router.invalid/v1/models", 502, "Bad Gateway", None, None)
        self.assertEqual(self.call(bare, path="/models")[0], (502, {"transport_error": "HTTPError", "content_type": None}))

    def test_no_http_answer_is_status_0_with_the_error_class(self):
        for exc in (urllib.error.URLError(ConnectionRefusedError("refused")), TimeoutError("timed out"), ConnectionResetError("reset")):
            with self.subTest(exc=type(exc).__name__):
                self.assertEqual(self.call(exc, body={})[0], (0, {"transport_error": type(exc).__name__, "content_type": None}))

    def test_without_a_key_nothing_is_sent(self):
        with self.assertRaisesRegex(preflight.IdentityStop, "^no provider key: the key variable is not set"):
            preflight.http_transport("https://router.invalid/v1", "")


class Run(unittest.TestCase):
    """aisef2.app.preflight.run: a failed request's provenance in the ledger and the observation, whole."""

    def run_with(self, listing, probe):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t) / "pre"
            rec = preflight.run(ROUTE, 2, lambda path, body=None: listing if body is None else probe, d, "model-1", "up")
            rows = [json.loads(x) for x in (d / "LEDGER.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(json.loads((d / "PREFLIGHT.json").read_text(encoding="utf-8")), rec)
        return rec, rows

    def test_probes_answered_as_an_event_stream(self):
        failed = {"transport_error": "JSONDecodeError", "content_type": "text/event-stream"}
        rec, rows = self.run_with((200, LISTING), (200, failed))
        self.assertEqual(rows, [
            {"n": 1, "event": "sent", "kind": "listing"}, {"n": 1, "event": "done", "http": 200},
            {"n": 2, "event": "sent", "kind": "chat"}, {"n": 2, "event": "done", "http": 200, "input_tokens": 0, "output_tokens": 0, **failed},
            {"n": 3, "event": "sent", "kind": "chat"}, {"n": 3, "event": "done", "http": 200, "input_tokens": 0, "output_tokens": 0, **failed}])
        probe = {"http": 200, "served_model": None, "system_fingerprint": preflight.NOT_EXPOSED, **failed}
        self.assertEqual(rec["observation"]["listing"], {"http": 200, "listed": True, "id": "up/model-1", "owned_by": "up"})
        self.assertEqual(rec["observation"]["probes"], [probe, probe])
        self.assertEqual((rec["verdict"], rec["problems"]), ("OPAQUE", ["probe 0: HTTP 200 (text/event-stream: JSONDecodeError)",
                                                                       "probe 1: HTTP 200 (text/event-stream: JSONDecodeError)"]))

    def test_a_listing_with_no_http_answer(self):
        failed = {"transport_error": "URLError", "content_type": None}
        rec, rows = self.run_with((0, failed), (200, ANSWER))
        self.assertEqual(rows[:2], [{"n": 1, "event": "sent", "kind": "listing"}, {"n": 1, "event": "done", "http": 0, **failed}])
        self.assertEqual(rows[3], {"n": 2, "event": "done", "http": 200, "input_tokens": 9, "output_tokens": 1})
        self.assertEqual(rec["observation"]["listing"], {"http": 0, "listed": False, "id": None, "owned_by": None, **failed})
        self.assertEqual(rec["observation"]["probes"][0], {"http": 200, "served_model": "model-1", "system_fingerprint": "fp-1"})
        self.assertEqual(rec["problems"], ["the provider does not list the declared model up/model-1 (None: URLError)"])


class IdentityProblems(unittest.TestCase):
    """aisef2.app.preflight.identity_problems: each failure named with its status, content type and error class."""

    def obs(self, listing=None, probes=()):
        return {"declared_model": "up/model-1", "expected_served_model": "model-1", "expected_listed_owner": "up",
                "listing": listing or {"http": 200, "listed": True, "id": "up/model-1", "owned_by": "up"},
                "probes": [{"system_fingerprint": "fp-1", **p} for p in probes]}

    def test_each_failure_is_named_with_what_the_transport_said(self):
        ok = {"http": 200, "served_model": "model-1"}
        self.assertEqual(preflight.identity_problems(self.obs(probes=[ok])), [])
        self.assertEqual(preflight.identity_problems(self.obs(probes=[ok, {"http": 200, "served_model": None, "transport_error": "JSONDecodeError",
                                                                        "content_type": "text/html"}])),
                         ["probe 1: HTTP 200 (text/html: JSONDecodeError)"])
        self.assertEqual(preflight.identity_problems(self.obs(probes=[{"http": 503, "served_model": None, "transport_error": "HTTPError",
                                                                       "content_type": "text/plain"}])),
                         ["probe 0: HTTP 503 (text/plain: HTTPError)"])
        self.assertEqual(preflight.identity_problems(self.obs(probes=[{"http": 502, "served_model": None}])), ["probe 0: HTTP 502"])
        self.assertEqual(preflight.identity_problems(self.obs(listing={"http": 403, "listed": False, "id": None, "owned_by": None,
                                                                       "transport_error": "HTTPError", "content_type": "text/html"},
                                                              probes=[ok])),
                         ["the provider does not list the declared model up/model-1 (text/html: HTTPError)"])
        self.assertEqual(preflight.identity_problems(self.obs(listing={"http": 200, "listed": False, "id": None, "owned_by": None},
                                                              probes=[ok])),
                         ["the provider does not list the declared model up/model-1"])


class _Router(http.server.BaseHTTPRequestHandler):
    """A loopback router that answers like the one RC1 met: an event stream unless asked for "stream": false."""

    def do_GET(self):  # noqa: N802
        self._send(200, "application/json", json.dumps(LISTING).encode())

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if body.get("stream") is False:
            self._send(200, "application/json", json.dumps(ANSWER).encode())
        else:
            self._send(200, "text/event-stream", EVENT_STREAM)

    def _send(self, code, ctype, raw):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


class OverLoopback(unittest.TestCase):
    """The shipped transport and preflight against a loopback router answering as the release route's did."""

    def test_the_route_is_attested(self):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Router)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            endpoint = f"http://127.0.0.1:{srv.server_address[1]}/v1"
            with tempfile.TemporaryDirectory() as t:
                rec = preflight.run(ROUTE, 3, preflight.http_transport(endpoint, "k-1"), pathlib.Path(t) / "pre", "model-1", "up")
            self.assertEqual((rec["verdict"], rec["problems"]), ("ATTESTED", []))
            self.assertEqual(rec["accounting"], {"provider_requests": 4, "turns": 0, "input_tokens": 27, "output_tokens": 3, "unaccounted": []})
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
