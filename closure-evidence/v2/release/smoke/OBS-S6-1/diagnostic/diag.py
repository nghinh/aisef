"""S6-SMOKE-1-PREFLIGHT-OPAQUE — the owner's two diagnostic provider requests (ruling 2026-10-05), each sent ONCE:
A = exactly the RC1 preflight chat probe (aisef2/app/preflight.py http_transport + run: same URL, body bytes, method,
headers, urllib opener, 60 s timeout); B = byte-identical but for an added "stream": false. No retry, no OpenCode, no
session, journal or workload. Never records the key or the Authorization value.
usage (cwd = the release worktree, the operator's environment): python3 -P diag.py OUT_DIR   (OUT_DIR must not exist)
offline self-test only: python3 -P diag.py OUT_DIR --loopback http://127.0.0.1:PORT/v1 (a fake key; never the provider)"""
import hashlib, json, os, pathlib, platform, re, sys, time, urllib.error, urllib.request
sys.path.insert(0, ".")
from aisef2.app import client, preflight

out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=False)           # no second run of this script: the directory exists after the first
ledger = out / "LEDGER.jsonl"
settings = json.loads(pathlib.Path("closure-evidence/v2/release/smoke/SETTINGS.json").read_text(encoding="utf-8"))
endpoint, route = settings["provider"]["endpoint"], settings["route"]
if "--loopback" in sys.argv:
    endpoint, key = sys.argv[sys.argv.index("--loopback") + 1], "loopback-test-key-not-a-secret-0123"
    assert endpoint.startswith("http://127.0.0.1:")
else:
    configured, key = client.configured_provider(settings["provider"]["name"])
    assert configured == endpoint and key and settings["provider"]["api_key_env"] is None, "not the smoke's provider path"
model = route.split("/", 1)[1]
body_a = {"model": model, "messages": [{"role": "user", "content": preflight.PROBE_PROMPT}],
          "max_tokens": preflight.PROBE_MAX_TOKENS, "temperature": 0}
data_a = json.dumps(body_a).encode("utf-8")
data_b = json.dumps({**body_a, "stream": False}).encode("utf-8")
assert data_b == data_a[:-1] + b', "stream": false}'   # byte-identical but for the added key
SECRETS = [key, *(p for p in re.split(r"[^A-Za-z0-9]+", key) if len(p) >= 8)]
HEADERS_KEPT = ("content-type", "content-length", "transfer-encoding", "content-encoding", "server", "cf-ray", "cf-cache-status")
FIRST = 768


def redact(s: str) -> str:
    for x in sorted(SECRETS, key=len, reverse=True):
        s = s.replace(x, "<REDACTED>")
    return re.sub(r"(?i)bearer\s+\S+", "Bearer <REDACTED>", s)


def append(row):
    with ledger.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def shape(raw: bytes) -> str:
    t = raw.lstrip()[:16]
    return ("EMPTY" if not t else "JSON" if t[:1] in (b"{", b"[") else "SSE" if t.startswith((b"data:", b"event:", b":"))
            else "HTML" if t[:1] == b"<" else "OTHER")


def sse_facts(text: str) -> dict:
    models, usage, n = set(), None, 0
    for line in text.splitlines():
        if line.startswith("data:") and line[5:].strip() not in ("", "[DONE]"):
            n += 1
            try:
                d = json.loads(line[5:].strip())
            except ValueError:
                continue
            if isinstance(d, dict):
                models.add(str(d.get("model")))
                usage = d.get("usage") or usage
    return {"data_events": n, "models": sorted(models), "usage": usage}


def send(name: str, data: bytes) -> dict:
    req = urllib.request.Request(endpoint + "/chat/completions", data=data, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    rec = {"request": name, "url": endpoint + "/chat/completions", "method": "POST", "body": data.decode("utf-8"),
           "body_sha256": hashlib.sha256(data).hexdigest(), "headers_sent": ["Authorization: <REDACTED>",
           "Content-Type: application/json", f"User-Agent: {req.get_header('User-agent') or 'Python-urllib/%d.%d' % sys.version_info[:2]}"],
           "timeout_s": 60.0}
    append({"event": "sent", "request": name, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    t0 = time.monotonic()
    raw, status, headers, err = b"", None, {}, None
    try:
        with urllib.request.urlopen(req, timeout=60.0) as r:
            status, headers = r.status, {k.lower(): v for k, v in r.headers.items()}
            raw = r.read()
        transport = "RESPONSE"
    except urllib.error.HTTPError as e:
        status, headers, transport = e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, "HTTPError"
        try:
            raw = e.read()
        except OSError:
            pass
        e.close()
    except (urllib.error.URLError, OSError, ValueError) as e:
        transport = type(e).__name__
        err = {"class": type(e).__name__, "reason_class": type(getattr(e, "reason", None)).__name__ if hasattr(e, "reason") else None,
               "text": redact(str(e))[:300]}
    except Exception as e:  # noqa: BLE001 — a class the shipped transport does not catch (it would end that run): record it
        transport = type(e).__name__
        err = {"class": type(e).__name__, "uncaught_by_shipped_transport": True, "text": redact(str(e))[:300]}
    elapsed = round(time.monotonic() - t0, 3)
    (out / f"{name}.raw-status.json").write_text(json.dumps({"transport": transport, "status": status, "elapsed_s": elapsed,
        "content_type": headers.get("content-type"), "error": err, "body_bytes": len(raw)}), encoding="utf-8")   # before any post-processing
    try:                                      # exactly the shipped parse: json.loads(r.read().decode("utf-8") or "{}")
        json.loads(raw.decode("utf-8") or "{}")
        parse = "JSON" if transport in ("RESPONSE", "HTTPError") else "NO_RESPONSE"
    except ValueError as e:
        parse = type(e).__name__
    text = raw.decode("utf-8", errors="backslashreplace")
    rec.update(transport_result=transport, transport_error=err, http_status=status, content_type=headers.get("content-type"),
               response_headers={k: headers[k] for k in HEADERS_KEPT if k in headers}, elapsed_s=elapsed,
               body_bytes=len(raw), body_sha256=hashlib.sha256(raw).hexdigest(), body_shape=shape(raw),
               shipped_parse=parse, shipped_transport_would_return=status if (transport == "HTTPError" or (status and parse == "JSON")) else 0,
               first_bytes=redact(text[:FIRST]), first_bytes_limit=FIRST, redacted=redact(text) != text)
    try:
        facts(rec, parse, raw, text)
    except Exception as e:  # noqa: BLE001 — the measurement is kept whatever the post-processing does
        rec["postprocess_error"] = type(e).__name__
    (out / f"{name}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    append({"event": "done", "request": name, "http_status": status, "transport_result": transport, "elapsed_s": elapsed})
    return rec


def facts(rec, parse, raw, text):
    if parse == "JSON" and raw:
        d = json.loads(text)
        if isinstance(d, dict):
            rec["json_facts"] = {"model": d.get("model"), "object": d.get("object"), "system_fingerprint": d.get("system_fingerprint"),
                                 "usage": d.get("usage"), "finish_reason": ((d.get("choices") or [{}])[0] or {}).get("finish_reason")}
    elif rec["body_shape"] == "SSE":
        rec["sse_facts"] = sse_facts(text)


doc = {"record": "S6-SMOKE-1-PREFLIGHT-OPAQUE — the two owner-authorized diagnostic requests (each sent once, no retry)",
       "ruling": "owner 2026-10-05: exactly two diagnostic provider requests, A the shipped RC1 probe, B with stream:false",
       "python": platform.python_version(), "route": route, "endpoint": endpoint,
       "A": send("A", data_a)}
doc["B"] = send("B", data_b)
for x in (doc["A"], doc["B"]):
    assert key not in json.dumps(x)
(out / "DIAGNOSTIC.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({n: {k: doc[n].get(k) for k in ("transport_result", "transport_error", "http_status", "content_type", "elapsed_s",
                                                   "body_bytes", "body_shape", "shipped_parse", "shipped_transport_would_return",
                                                   "json_facts", "sse_facts", "redacted")} for n in ("A", "B")}, indent=1))
