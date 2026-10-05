"""Offline self-test of diag.py (loopback only): A gets an SSE 200, B a JSON 200; then A a dropped connection, B an HTML 200.
usage (cwd = the release worktree): python3 -P diag_selftest.py SCRATCH_DIR"""
import http.server, json, pathlib, subprocess, sys, threading

MODE = {"m": 0}
SEEN = []


class H(http.server.BaseHTTPRequestHandler):
    def _out(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers["Content-Length"]))
        SEEN.append({"body": body.decode(), "auth": self.headers.get("Authorization"), "ua": self.headers.get("User-Agent")})
        stream_false = b'"stream": false' in body
        if MODE["m"] == 0:
            if stream_false:
                self._out(200, "application/json", json.dumps({"model": "deepseek-v4-pro", "object": "chat.completion",
                          "choices": [{"finish_reason": "stop"}], "usage": {"prompt_tokens": 9, "completion_tokens": 1},
                          "echo": "loopback-test-key-not-a-secret-0123"}).encode())
            else:
                self._out(200, "text/event-stream", b'data: {"model": "deepseek-v4-pro", "choices": [{"delta": {"content": "ok"}}]}\n\n'
                                                     b'data: {"model": "deepseek-v4-pro", "usage": {"prompt_tokens": 9}}\n\ndata: [DONE]\n\n')
        elif not stream_false:
            self.close_connection = True
            self.connection.shutdown(2)
        else:
            self._out(200, "text/html", b"<html>challenge</html>")

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}/v1"
d = pathlib.Path(sys.argv[1])
here = pathlib.Path(__file__).parent
for m in (0, 1):
    MODE["m"] = m
    r = subprocess.run([sys.executable, "-P", str(here / "diag.py"), str(d / f"mode{m}"), "--loopback", url], capture_output=True, text=True)
    print(f"mode {m}: exit {r.returncode}", r.stdout[-2500:], r.stderr[-800:])
again = subprocess.run([sys.executable, "-P", str(here / "diag.py"), str(d / "mode0"), "--loopback", url], capture_output=True, text=True)
print("second run into the same directory refused:", again.returncode != 0 and "FileExistsError" in again.stderr)
print("requests seen:", len(SEEN), [s["ua"] for s in SEEN], all(s["auth"] == "Bearer loopback-test-key-not-a-secret-0123" for s in SEEN))
print("bodies:", SEEN[0]["body"], "|", SEEN[1]["body"])
for f in sorted(d.rglob("*.json*")):
    assert "loopback-test-key-not-a-secret-0123" not in f.read_text(), f
print("no key in any record")
srv.shutdown()
