"""A loopback OpenAI-compatible provider for the integration run: the preflight's listing and chat probes, and Open
Code Review's tool-calling reviews (the first review finds the three-argument usage error, later ones nothing)."""
import json, sys, http.server, pathlib
state = pathlib.Path(sys.argv[2])
REPRO = {"clause": "R-CLI/1.2", "subject": {"kind": "cli_invocation", "locator": "app:__main__"},
         "stimulus": {"argv": ["1", "2", "3"]}, "observable": {"exit_code": 2, "within_s": 20}}
class H(http.server.BaseHTTPRequestHandler):
    def reply(self, doc):
        data = json.dumps(doc).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        with state.open("a") as f: f.write(json.dumps({"get": self.path, "auth": bool(self.headers.get("Authorization"))}) + "\n")
        self.reply({"data": [{"id": "model-1", "owned_by": "fake"}]})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        tools = [t["function"]["name"] for t in body.get("tools") or []]
        with state.open("a") as f:
            f.write(json.dumps({"post": self.path, "tools": bool(tools), "auth": bool(self.headers.get("Authorization"))}) + "\n")
        usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
        if not tools:   # a preflight chat probe
            return self.reply({"id": "p", "object": "chat.completion", "model": "model-1", "system_fingerprint": "fp-1",
                               "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                               "usage": usage})
        msgs = json.dumps(body.get("messages"))
        first = "return int(args[0]) + int(args[1])" in msgs and "if len(args) < 2" in msgs
        calls = []
        if first:
            calls.append({"id": "c1", "type": "function", "function": {"name": "code_comment", "arguments": json.dumps(
                {"comments": [{"path": "app/cli.py", "category": "bug", "severity": "high",
                               "existing_code": "    return int(args[0]) + int(args[1])",
                               "content": "three arguments are summed as two: a usage error must exit 2\n```aisef-reproducer\n"
                                          + json.dumps(REPRO) + "\n```"}]})}})
        calls.append({"id": "c2", "type": "function", "function": {"name": "task_done", "arguments": '{"state": "DONE"}'}})
        self.reply({"id": "r", "object": "chat.completion", "model": "model-1",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "", "tool_calls": calls},
                                 "finish_reason": "tool_calls"}], "usage": usage})
    def log_message(self, *a): pass
s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
pathlib.Path(sys.argv[1]).write_text(str(s.server_address[1]))
s.serve_forever()
