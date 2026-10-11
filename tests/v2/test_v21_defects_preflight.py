"""V2.1 (B-03 survivor audit, defects found by two auditors of T25a): the provider preflight's transport keeps its own
contract — "a failed request keeps its HTTP status (0 only when no HTTP answer came) and says why in `transport_error`" —
for the answers an untrusted provider can give that it did not handle:

* a 2xx answer whose JSON is not an object ([] null "x" 7 ...) was returned as-is, and `preflight.run`'s first use of it
  (`body.get(...)`) raised AttributeError: no PREFLIGHT.json, a 'sent' row never answered, a traceback;
* an `http.client.HTTPException` that is not an OSError (IncompleteRead from a body cut short of its Content-Length,
  BadStatusLine from a garbled status line, InvalidURL, ...) was raised out of the transport and out of `preflight.run`;
* a JSON body nested deeper than the interpreter's recursion limit (RecursionError on 3.11-3.13) did the same.

Each is now an answer with its cause: an OPAQUE verdict, the request answered in the ledger, no key anywhere.
Loopback servers and fake answers only; no provider."""

from __future__ import annotations

import email.message
import http.client
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

from aisef2.app import preflight  # noqa: E402

KEY = "sk-test-secret-key-0007"
ENDPOINT = "https://router.invalid/v1"
NOT_OBJECT = "not a JSON object"
#: valid JSON, none of them an object
NON_OBJECTS = (b"[]", b"[1, 2]", b'[{"id": "up/model-1"}]', b"null", b'"x"', b"7", b"1.5", b"true", b"false")


class _Answer:
    """What urllib's opener returns (a context manager with status, headers and read())."""

    def __init__(self, raw: bytes | Exception, content_type: str | None = "application/json", status: int = 200):
        self.status, self._raw = status, raw
        self.headers = email.message.Message()
        if content_type:
            self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        if isinstance(self._raw, Exception):
            raise self._raw
        return self._raw


def _opener(answer):
    def open_(req, timeout=None):
        if isinstance(answer, Exception):
            raise answer
        return answer
    return mock.patch.object(preflight._OPENER, "open", open_)


def _call(answer, path="/models", body=None):
    with _opener(answer):
        return preflight.http_transport(ENDPOINT, KEY)(path, body)


class NonObjectAnswer(unittest.TestCase):
    def test_a_2xx_answer_that_is_not_an_object_is_a_failure_that_keeps_its_status_and_says_why(self):
        for raw in NON_OBJECTS:
            for ctype in ("application/json", None):
                with self.subTest(raw=raw, content_type=ctype):
                    self.assertEqual(_call(_Answer(raw, ctype)), (200, {"transport_error": NOT_OBJECT, "content_type": ctype}))
                    self.assertEqual(_call(_Answer(raw, ctype), "/chat/completions", {"model": "m"}),
                                     (200, {"transport_error": NOT_OBJECT, "content_type": ctype}))

    def test_an_object_answer_is_returned_unchanged(self):
        for raw, doc in ((b"{}", {}), (b"", {}), (b'{"data": []}', {"data": []}), (b'{"a": [1, {"b": null}]}', {"a": [1, {"b": None}]})):
            with self.subTest(raw=raw):
                self.assertEqual(_call(_Answer(raw)), (200, doc))

    def test_the_preflight_is_opaque_and_answers_every_request(self):
        for raw in (b"[]", b"null", b'"x"', b"7"):
            for failing in ("listing", "probes"):
                with self.subTest(raw=raw, failing=failing), tempfile.TemporaryDirectory() as t:
                    good_listing = json.dumps({"data": [{"id": "model-1", "owned_by": "up"}]}).encode()
                    good_probe = json.dumps({"model": "model-1", "system_fingerprint": "fp",
                                             "usage": {"prompt_tokens": 9, "completion_tokens": 1}}).encode()
                    answers = {"/models": raw if failing == "listing" else good_listing,
                               "/chat/completions": raw if failing == "probes" else good_probe}

                    def open_(req, timeout=None, answers=answers):
                        return _Answer(answers["/" + req.full_url.split("/v1/", 1)[1]])
                    with mock.patch.object(preflight._OPENER, "open", open_):
                        rec = preflight.run("router/up/model-1", 2, preflight.http_transport(ENDPOINT, KEY),
                                            pathlib.Path(t) / "pre", "model-1", "up")
                    self.assertEqual(rec["verdict"], "OPAQUE")
                    self.assertTrue(any(NOT_OBJECT in p for p in rec["problems"]), rec["problems"])
                    self.assertEqual(rec["accounting"]["unaccounted"], [])
                    self.assertEqual(rec["accounting"]["provider_requests"], 3)
                    self.assertEqual(json.loads((pathlib.Path(t) / "pre" / "PREFLIGHT.json").read_text(encoding="utf-8")), rec)
                    self.assertNotIn(KEY, json.dumps(rec))


class HttpClientErrors(unittest.TestCase):
    def test_every_http_client_exception_is_an_answer_naming_its_class(self):
        for exc in (http.client.IncompleteRead(b'{"data": [', 100), http.client.BadStatusLine("garbage"),
                    http.client.LineTooLong("header line"), http.client.InvalidURL("nonnumeric port"),
                    http.client.ResponseNotReady("idle"), http.client.HTTPException("a message that names " + KEY)):
            with self.subTest(exc=type(exc).__name__):
                name = type(exc).__name__
                # raised while the body is read: an HTTP answer came, its status and content type stay
                self.assertEqual(_call(_Answer(exc)), (200, {"transport_error": name, "content_type": "application/json"}))
                self.assertEqual(_call(_Answer(exc, None)), (200, {"transport_error": name, "content_type": None}))
                # raised before any answer: status 0
                self.assertEqual(_call(exc), (0, {"transport_error": name, "content_type": None}))

    def test_a_failed_request_never_carries_the_key(self):
        for exc in (http.client.HTTPException(f"Authorization: Bearer {KEY}"), http.client.BadStatusLine(KEY),
                    ValueError(KEY), RecursionError(KEY)):
            with self.subTest(exc=type(exc).__name__):
                self.assertNotIn(KEY, json.dumps(_call(exc)))
                self.assertNotIn(KEY, json.dumps(_call(_Answer(exc))))

    def test_a_json_body_nested_beyond_the_parser_is_an_answer_not_a_traceback(self):
        deep = b"[" * 60000 + b"]" * 60000          # RecursionError on 3.11-3.13; a list on 3.14: a failure either way
        status, doc = _call(_Answer(deep))
        self.assertEqual((status, doc["content_type"]), (200, "application/json"))
        self.assertIn(doc["transport_error"], ("RecursionError", NOT_OBJECT))
        with mock.patch.object(preflight.json, "loads", side_effect=RecursionError("maximum recursion depth exceeded")):
            self.assertEqual(_call(_Answer(b"[[[")), (200, {"transport_error": "RecursionError", "content_type": "application/json"}))


def _serve(handler) -> tuple[http.server.HTTPServer, str]:
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _handler(raw: bytes):
    """A server that reads the whole request, then writes `raw` verbatim (a status line included) and closes."""
    class H(http.server.BaseHTTPRequestHandler):
        def _answer(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.wfile.write(raw)

        do_GET = do_POST = _answer

        def log_message(self, *a):
            pass
    return H


class OnTheWire(unittest.TestCase):
    """The same answers from a real HTTP exchange, through urllib and http.client themselves."""

    def serve(self, raw: bytes) -> str:
        srv, url = _serve(_handler(raw))
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return url

    def test_a_body_cut_short_of_its_content_length(self):
        url = self.serve(b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n" + b'{"data": [')
        self.assertEqual(preflight.http_transport(url, KEY, 10.0)("/models"),
                         (200, {"transport_error": "IncompleteRead", "content_type": "application/json"}))

    def test_a_garbled_status_line(self):
        url = self.serve(b"garbage\r\n\r\n")
        self.assertEqual(preflight.http_transport(url, KEY, 10.0)("/models"),
                         (0, {"transport_error": "BadStatusLine", "content_type": None}))

    def test_a_json_array_is_not_a_verdict(self):
        url = self.serve(b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n[]")
        self.assertEqual(preflight.http_transport(url, KEY, 10.0)("/models"),
                         (200, {"transport_error": NOT_OBJECT, "content_type": "application/json"}))

    def test_the_preflight_over_each_is_opaque_with_every_request_answered(self):
        for name, raw, want in (
                ("truncated", b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{", "IncompleteRead"),
                ("garbled", b"garbage\r\n\r\n", "BadStatusLine"),
                ("array", b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n[]", NOT_OBJECT)):
            with self.subTest(name), tempfile.TemporaryDirectory() as t:
                rec = preflight.run("router/up/model-1", 1, preflight.http_transport(self.serve(raw), KEY, 10.0),
                                    pathlib.Path(t) / "pre", "model-1", "up")
                self.assertEqual(rec["verdict"], "OPAQUE")
                self.assertTrue(any(want in p for p in rec["problems"]), rec["problems"])
                self.assertEqual(rec["accounting"]["unaccounted"], [])
                self.assertTrue((pathlib.Path(t) / "pre" / "PREFLIGHT.json").is_file())


if __name__ == "__main__":
    unittest.main()
