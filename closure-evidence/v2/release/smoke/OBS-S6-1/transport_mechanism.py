"""OBS-S6-1, offline (loopback only, no provider): what the RC's shipped preflight (aisef2/app/preflight.py) records for
each way a chat probe can answer, next to what it sent. usage (cwd = the release worktree): python3 -P transport_mechanism.py"""
import http.server, json, pathlib, sys, tempfile, threading
sys.path.insert(0, ".")
from aisef2.app import preflight

SEEN = []
MODE = {"m": "json"}


class H(http.server.BaseHTTPRequestHandler):
    def _out(self, code, ctype, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        self._out(200, "application/json", json.dumps({"data": [{"id": "ds/deepseek-v4-pro", "owned_by": "ds"}]}).encode())

    def do_POST(self):  # noqa: N802
        SEEN.append(json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0))))
        done = {"model": "deepseek-v4-pro", "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 1}}
        m = MODE["m"]
        if m == "json":
            self._out(200, "application/json", json.dumps(done).encode())
        elif m == "sse":    # an OpenAI-style stream, as a router sends when it streams by default
            chunk = {"model": "deepseek-v4-pro", "choices": [{"delta": {"content": "ok"}}]}
            self._out(200, "text/event-stream", f"data: {json.dumps(chunk)}\n\ndata: {json.dumps(done)}\n\ndata: [DONE]\n\n".encode())
        elif m == "html200":
            self._out(200, "text/html", b"<html>challenge</html>")
        elif m == "reset":
            self.close_connection = True
            self.connection.shutdown(2)
        elif m == "http400":
            self._out(400, "application/json", b'{"error": "bad request"}')

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}/v1"
out = {"sent_chat_body": None, "modes": {}}
call = preflight.http_transport(base, "not-a-key", timeout_s=5)
for m in ("json", "sse", "html200", "reset", "http400"):
    MODE["m"] = m
    raw = call("/chat/completions", {"model": "deepseek-v4-pro", "messages": [{"role": "user", "content": "x"}]})
    with tempfile.TemporaryDirectory() as t:
        rec = preflight.run("9router/ds/deepseek-v4-pro", 3, call, pathlib.Path(t) / "pf", "deepseek-v4-pro", "ds")
        ledger = (pathlib.Path(t) / "pf" / "LEDGER.jsonl").read_text(encoding="utf-8")
    out["modes"][m] = {"transport_returns": [raw[0], raw[1] if raw[0] == 0 else "<json body>"],
                       "recorded_probes": rec["observation"]["probes"], "problems": rec["problems"], "verdict": rec["verdict"],
                       "transport_error_in_record_or_ledger": "transport_error" in json.dumps(rec) or "transport_error" in ledger}
out["sent_chat_body"] = SEEN[-1]
out["sent_chat_body_has_stream_key"] = "stream" in SEEN[-1]
srv.shutdown()
print(json.dumps(out, indent=1, sort_keys=True))
