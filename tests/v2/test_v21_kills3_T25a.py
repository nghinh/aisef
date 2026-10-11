"""V2.1 mutation-survivor batch T25a: aisef2/app/preflight.py::http_transport.

What the shipped provider transport sends, and what it hands back to preflight.run, which unpacks
`code, body = transport(path, body)` and tests `body.get("transport_error")`. The transport is driven through its own
opener (`preflight._OPENER.open` is replaced by a function that answers, raises, or checks the request): no socket, no
clock, no provider, and nothing here depends on the wording of a message."""

from __future__ import annotations

import email.message
import io
import json
import pathlib
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import preflight  # noqa: E402

ENDPOINT = "https://router.invalid/v1"
KEY = "k-1"
ROUTE = "router/up/model-1"
LISTING = {"data": [{"id": "up/model-1", "owned_by": "up"}]}
ANSWER = {"model": "model-1", "system_fingerprint": "fp-1", "usage": {"prompt_tokens": 9, "completion_tokens": 1}}
BODY = {"model": "up/model-1", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 16, "temperature": 0}
#: what the router RC1 met answered a POST that did not ask for "stream": false (a JSON object, then "data: [DONE]")
EVENT_STREAM = b'{"id":"x","model":"model-1","choices":[]}data: [DONE]\n\n'


def _headers(content_type: str | None = None, **more: str) -> email.message.Message:
    h = email.message.Message()
    if content_type:
        h["Content-Type"] = content_type
    for k, v in more.items():
        h[k.replace("_", "-")] = v
    return h


class _Answer:
    """What the opener returns: a context manager with `.status`, `.headers` and `.read()` (or an error while reading)."""

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


def _json(doc: dict, status: int = 200) -> _Answer:
    return _Answer(status, "application/json", json.dumps(doc, ensure_ascii=False).encode("utf-8"))


def _http_error(code: int, content_type: str | None = "application/json", **more: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(f"{ENDPOINT}/x", code, "refused", _headers(content_type, **more), io.BytesIO(b"{}"))


def _header(req, name: str) -> str:
    """A request header by name, case-insensitively ('' when absent)."""
    return {k.lower(): v for k, v in req.header_items()}.get(name.lower(), "")


def _credential(req) -> tuple[str, str]:
    """(scheme, token) of the Authorization header; the scheme's case is not part of the contract (RFC 7235)."""
    scheme, _, token = _header(req, "Authorization").partition(" ")
    return scheme.lower(), token


def _media_type(req) -> str:
    """The media type of the Content-Type header, without its parameters (`; charset=utf-8`), lower-cased."""
    return _header(req, "Content-Type").split(";")[0].strip().lower()


def _opener(reply, seen: list | None = None):
    """The function that replaces `_OPENER.open`: `reply` is an answer, an exception, or a function of the request."""
    def open_(req, timeout=None):
        if seen is not None:
            seen.append(req)
        out = reply(req) if callable(reply) else reply
        if isinstance(out, BaseException):
            raise out
        return out
    return open_


def _call(reply, path: str = "/chat/completions", body: dict | None = None, **kw):
    """(what http_transport returned, the requests it made)"""
    seen: list = []
    with mock.patch.object(preflight._OPENER, "open", _opener(reply, seen)):
        got = preflight.http_transport(ENDPOINT, KEY, **kw)(path, body)
    return got, seen


class SuccessAnswer(unittest.TestCase):
    """A 2xx answer is returned as exactly (status it carried, JSON document it held): the pair preflight.run unpacks.

    Pins aisef2/app/preflight.py::http_transport [10, 20, 21, 22, 23, 24, 25, 49, 58]."""

    def test_a_post_and_a_get_come_back_with_their_status_and_document(self):
        for status, path, body, doc in ((200, "/chat/completions", BODY, ANSWER), (200, "/models", None, LISTING),
                                        (202, "/chat/completions", BODY, {"note": "café", "n": 1})):
            with self.subTest(status=status, path=path):
                got, _ = _call(_json(doc, status), path=path, body=body)
                self.assertEqual(got, (status, doc))      # a tuple of two: a list or a 1-tuple is not equal

    def test_an_empty_answer_is_an_empty_document(self):
        """'No content' is read as `{}` (not as a parse failure): the answer then has no `transport_error`, which is
        what preflight.run's failure() tests. Pins [55] (and [49] on its empty-body side)."""
        for status in (200, 204):
            with self.subTest(status=status):
                self.assertEqual(_call(_Answer(status, None, b""), body={})[0], (status, {}))


class FailureIsData(unittest.TestCase):
    """A request that fails, and an answer that cannot be read as one JSON document, are returned to preflight.run as
    (status, {transport_error: class name, content_type}) and never raised: 0 when no HTTP answer came, else the status
    the answer carried. An HTTP error answer is the same pair, its class 'HTTPError' (a 3xx: 'redirect refused') and its
    content type read from the error's own headers.

    Pins aisef2/app/preflight.py::http_transport [13, 14, 15, 29, 30, 44, 45, 48, 53, 54] and, for the HTTP error answer,
    [41, 43, 51, 52, 59]."""

    def test_no_http_answer_is_status_0_with_the_error_class(self):
        for exc, name in ((urllib.error.URLError(ConnectionRefusedError("refused")), "URLError"),
                          (TimeoutError("timed out"), "TimeoutError"), (ConnectionResetError("reset"), "ConnectionResetError")):
            with self.subTest(error=name):
                self.assertEqual(_call(exc, body={})[0], (0, {"transport_error": name, "content_type": None}))

    def test_an_answer_that_is_not_one_json_document_keeps_its_status_and_content_type(self):
        for raw, ctype, name in ((EVENT_STREAM, "text/event-stream", "JSONDecodeError"),
                                 (b"<html>challenge</html>", "text/html", "JSONDecodeError"),
                                 (b"\xff\xfe", "application/json", "UnicodeDecodeError"),
                                 (ConnectionResetError("reset"), "application/json", "ConnectionResetError")):
            with self.subTest(error=name, content_type=ctype):
                self.assertEqual(_call(_Answer(200, ctype, raw), body={})[0],
                                 (200, {"transport_error": name, "content_type": ctype}))

    def test_an_http_error_keeps_its_status_and_content_type_and_names_its_class(self):
        for err, want in ((_http_error(429), (429, {"transport_error": "HTTPError", "content_type": "application/json"})),
                          (_http_error(503, "text/plain"), (503, {"transport_error": "HTTPError", "content_type": "text/plain"})),
                          (_http_error(401, None), (401, {"transport_error": "HTTPError", "content_type": None})),
                          (_http_error(400, "text/plain"), (400, {"transport_error": "HTTPError", "content_type": "text/plain"})),
                          *((_http_error(c, None, Location="https://elsewhere.invalid/"),
                             (c, {"transport_error": "redirect refused", "content_type": None})) for c in (302, 303, 307, 308))):
            with self.subTest(code=want[0]):
                self.assertEqual(_call(err, body={})[0], want)

    def test_an_http_error_without_a_header_object_has_no_content_type(self):
        bare = urllib.error.HTTPError(f"{ENDPOINT}/models", 502, "Bad Gateway", None, None)
        self.assertEqual(_call(bare, path="/models")[0], (502, {"transport_error": "HTTPError", "content_type": None}))


class RequestSent(unittest.TestCase):
    """The request the router reads: the key as a bearer credential on every request, the body declared as JSON, and the
    caller's body with "stream": false added (without it the router answers as an event stream).

    Pins aisef2/app/preflight.py::http_transport [18, 19, 37, 47, 56, 57, 60, 61] (and the caller-asks-for-a-stream
    case, a reviewer's own variant of the same requirement)."""

    def test_every_request_carries_the_key_as_a_bearer_credential(self):
        for path, body in (("/models", None), ("/chat/completions", BODY)):
            with self.subTest(path=path):
                (req,) = _call(_json({}), path=path, body=body)[1]
                self.assertEqual(_credential(req), ("bearer", KEY))

    def test_a_post_carries_the_key_and_declares_its_body_as_json(self):
        """The two headers the router reads on a POST, looked up by name: other headers and a media type's parameters
        (`; charset=utf-8`) are not part of the contract."""
        (req,) = _call(_json(ANSWER), body=BODY)[1]
        self.assertEqual(_credential(req), ("bearer", KEY))
        self.assertEqual(_media_type(req), "application/json")

    def test_a_post_body_is_the_callers_body_and_stream_false(self):
        body = dict(BODY)
        (req,) = _call(_json(ANSWER), body=body)[1]
        self.assertEqual((req.get_method(), req.full_url), ("POST", f"{ENDPOINT}/chat/completions"))
        sent = json.loads(req.data.decode("utf-8"))
        self.assertIs(sent["stream"], False)              # the boolean false, not another falsy value, not absent
        self.assertEqual(sent, {**BODY, "stream": False})   # model, messages, max_tokens, temperature all travel
        self.assertEqual(body, BODY)                       # and the caller's own dict is not changed

    def test_a_caller_that_asks_for_a_stream_does_not_get_one(self):
        """The transport reads one JSON answer, so `"stream": false` is the transport's, not the caller's, to set."""
        (req,) = _call(_json(ANSWER), body={**BODY, "stream": True})[1]
        sent = json.loads(req.data.decode("utf-8"))
        self.assertIs(sent["stream"], False)
        self.assertEqual({k: v for k, v in sent.items() if k != "stream"}, BODY)

    def test_a_get_sends_no_body(self):
        """Not pinned to a mutant of this batch (the GET/POST selection mutants are killed by the target's own kill set):
        a listing is asked for with a body-less GET."""
        (req,) = _call(_json(LISTING), path="/models")[1]
        self.assertEqual((req.get_method(), req.data, req.full_url), ("GET", None, f"{ENDPOINT}/models"))


def _router(req):
    """A router that holds every request to the contract: the bearer key, a JSON media type on a POST, the declared
    model and its messages, and one JSON answer only when "stream" is false (an event stream otherwise, as RC1's did)."""
    if _credential(req) != ("bearer", KEY):
        return _http_error(401)
    if req.get_method() == "GET":
        return _json(LISTING)
    if _media_type(req) != "application/json":
        return _http_error(415)
    body = json.loads(req.data)
    if body.get("model") != "up/model-1" or not body.get("messages"):
        return _http_error(400)
    if body.get("stream") is not False:
        return _Answer(200, "text/event-stream", EVENT_STREAM)
    return _json(ANSWER)


class OverPreflight(unittest.TestCase):
    """The shipped transport under preflight.run: a route that answers per the contract is attested, and a probe that
    fails is recorded (ledger row and observation) with its status, class and content type.

    Pins aisef2/app/preflight.py::http_transport [10, 13, 14, 15, 18, 19, 20, 21, 22, 23, 24, 25, 29, 30, 37, 44, 45, 47,
    48, 49, 53, 54, 56, 57, 58, 60, 61]."""

    def run_preflight(self, reply):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(preflight._OPENER, "open", _opener(reply)):
            d = pathlib.Path(t) / "pre"
            rec = preflight.run(ROUTE, 2, preflight.http_transport(ENDPOINT, KEY), d, "model-1", "up")
            rows = [json.loads(x) for x in (d / "LEDGER.jsonl").read_text(encoding="utf-8").splitlines()]
        return rec, rows

    def test_a_route_that_answers_per_the_contract_is_attested(self):
        rec, _ = self.run_preflight(_router)       # _router answers 401/415/400/event-stream to a request off the contract
        self.assertEqual((rec["verdict"], rec["problems"]), ("ATTESTED", []))

    def test_a_probe_answered_with_a_challenge_page_is_recorded_with_its_class_and_content_type(self):
        rec, rows = self.run_preflight(lambda req: _Answer(200, "text/html", b"<html>challenge</html>")
                                       if req.get_method() == "POST" else _router(req))
        failed = {"http": 200, "transport_error": "JSONDecodeError", "content_type": "text/html"}
        (done,) = [r for r in rows if r["event"] == "done" and r["n"] == 2]
        self.assertEqual({k: done[k] for k in failed}, failed)
        self.assertEqual({k: rec["observation"]["probes"][0][k] for k in failed}, failed)
        self.assertEqual(rec["verdict"], "OPAQUE")
        for element in ("probe 0", "200", "text/html", "JSONDecodeError"):
            self.assertIn(element, rec["problems"][0])

    def test_a_probe_that_gets_no_answer_is_recorded_as_status_0_with_the_error_class(self):
        rec, rows = self.run_preflight(lambda req: ConnectionResetError("reset") if req.get_method() == "POST" else _router(req))
        want = {"http": 0, "transport_error": "ConnectionResetError", "content_type": None}
        (done,) = [r for r in rows if r["event"] == "done" and r["n"] == 2]
        self.assertEqual({k: done[k] for k in want}, want)
        self.assertEqual(rec["verdict"], "OPAQUE")
        for element in ("probe 0", "HTTP 0", "ConnectionResetError"):
            self.assertIn(element, rec["problems"][0])


if __name__ == "__main__":
    unittest.main()
