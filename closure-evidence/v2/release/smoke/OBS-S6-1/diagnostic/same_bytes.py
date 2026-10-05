"""A's request vs the RC1 shipped transport's, captured raw on loopback (request line, headers, body)."""
import pathlib, socket, subprocess, sys, threading
sys.path.insert(0, ".")
from aisef2.app import preflight
cap = []
def serve(s):
    while True:
        c, _ = s.accept(); buf = b""
        while b"\r\n\r\n" not in buf: buf += c.recv(65536)
        head, _, body = buf.partition(b"\r\n\r\n")
        n = int([l.split(b":")[1] for l in head.split(b"\r\n") if l.lower().startswith(b"content-length")][0])
        while len(body) < n: body += c.recv(65536)
        cap.append((head, body)); c.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}"); c.close()
s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(); threading.Thread(target=serve, args=(s,), daemon=True).start()
url = f"http://127.0.0.1:{s.getsockname()[1]}/v1"
key = "loopback-test-key-not-a-secret-0123"
preflight.http_transport(url, key)("/chat/completions", {"model": "ds/deepseek-v4-pro", "messages": [{"role": "user", "content": preflight.PROBE_PROMPT}],
                                   "max_tokens": preflight.PROBE_MAX_TOKENS, "temperature": 0})
d = pathlib.Path(sys.argv[1]); r = subprocess.run([sys.executable, "-P", sys.argv[2], str(d), "--loopback", url], capture_output=True, text=True)
assert r.returncode == 0, r.stderr
norm = lambda h: sorted(l for l in h.split(b"\r\n")[1:] if not l.lower().startswith(b"host:"))
print("request line equal:", cap[0][0].split(b"\r\n")[0] == cap[1][0].split(b"\r\n")[0], cap[0][0].split(b"\r\n")[0])
print("headers equal (but Host port):", norm(cap[0][0]) == norm(cap[1][0]), [l.split(b":")[0] for l in norm(cap[0][0])])
print("A body byte-identical:", cap[0][1] == cap[1][1]); print("B body = A + stream:false:", cap[2][1] == cap[0][1][:-1] + b', "stream": false}')
print("B headers equal but Content-Length:", [l for l in norm(cap[0][0]) if not l.lower().startswith(b"content-length")] == [l for l in norm(cap[2][0]) if not l.lower().startswith(b"content-length")])
