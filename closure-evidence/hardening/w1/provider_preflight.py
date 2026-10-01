"""Provider stability preflight (owner decision "CONTINUE W1 PROFILE QUALIFICATION", 2026-09-19, section 5).

Before a W1 run on a fixed route, prove the route is usable — lightweight, and before any paid run:
  1. the router lists the exact route as a fixed model (not a combo);
  2. N chat probes each answer 2xx — no 4xx authentication / model-support error — with ONE constant model identity;
  3. K OpenCode tool smokes (the client the profile uses) call tools: a file written with the exact content, a shell run;
  4. optionally, the profile's reviewer read-only environment on a prepared copy leaves the tree byte-identical.
If any requirement fails, no run copy is created. The summary (no timestamps) is what a profile's identity records.

    python3 closure-evidence/hardening/w1/provider_preflight.py 9router/cx/gpt-5.5 --out <json> [--probes 3] [--smokes 2]
        [--stage-copy <prepared copy> --venv <run venv> --stage-path <PATH>]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import execution_profile as ep  # noqa: E402

GLOBAL_OC = Path.home() / ".config/opencode/opencode.json"
PROMPT = ("Use your tools: create a file named probe.txt whose entire content is the word ready, then run `cat probe.txt` "
          "in the shell and tell me what it printed.")


def _provider(prov: str) -> tuple[str, str]:
    """(base URL, key) from the operator's OpenCode configuration — the key is never printed or recorded."""
    opts = json.loads(GLOBAL_OC.read_text(encoding="utf-8"))["provider"][prov]["options"]
    key = str(opts.get("apiKey") or "")
    m = re.fullmatch(r"\{env:([A-Za-z0-9_]+)\}", key)
    if m:
        key = os.environ.get(m.group(1), "")
    return str(opts.get("baseURL") or opts.get("baseUrl")).rstrip("/"), key


def _get(url: str, key: str, body: dict | None = None) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:300]
    except (OSError, ValueError) as e:
        return 0, f"{type(e).__name__}: {str(e)[:200]}"


def listing(base: str, key: str, model: str) -> dict:
    code, d = _get(base + "/models", key)
    rows = [x for x in (d.get("data", []) if isinstance(d, dict) else []) if x.get("id") == model]
    owner = rows[0].get("owned_by") if rows else None
    return {"http": code, "listed": bool(rows), "owned_by": owner,
            "route_kind": ("DYNAMIC_COMBO" if owner == "combo" else "FIXED_MODEL") if rows else None}


def chat_probe(base: str, key: str, model: str) -> dict:
    t = time.time()
    code, d = _get(base + "/chat/completions", key, {"model": model, "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
                                                     "max_tokens": 16, "stream": False})
    out = {"http": code, "seconds": round(time.time() - t, 1)}
    if isinstance(d, dict):
        out.update(answered_by=d.get("model"), usage=d.get("usage"))
    else:
        out["error"] = d
    return out


def tool_smoke(route: str, model: str, limit: dict, i: int) -> dict:
    d = ep.QUAL_WS / f"provider-smoke-{model.replace('/', '_')}-{i}"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    prov = route.split("/", 1)[0]
    (d / "opencode.json").write_text(json.dumps({"$schema": "https://opencode.ai/config.json",
                                                 "provider": {prov: {"models": {model: {"name": model, "limit": limit}}}}}, indent=2))
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    t = time.time()
    try:
        # `--dir`, as the kernel's OpenCode adapter passes it: OpenCode resolves its project from PWD, which a
        # subprocess's cwd does not change — without it the smoke ran against the caller's directory and failed with
        # "Unexpected server error" (measured 2026-09-19; the 2026-09-18 first smoke batch failed the same way)
        r = subprocess.run(["opencode", "run", "--format", "json", "--dir", str(d), "--model", route, PROMPT], cwd=d,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
                           env={**os.environ, "PWD": str(d)})
    except subprocess.TimeoutExpired:
        return {"ok": False, "timeout": True, "seconds": 300}
    ev = [json.loads(ln) for ln in r.stdout.splitlines() if ln.strip().startswith("{")]
    tools = [e.get("part", {}).get("tool") for e in ev if e.get("type") in ("tool_use", "tool")]
    errs = [str(e.get("error"))[:200] for e in ev if e.get("type") == "error"]
    f = d / "probe.txt"
    written = f.is_file() and f.read_text(encoding="utf-8").strip() == "ready"
    return {"ok": written and not errs and "bash" in tools and r.returncode == 0, "file_written": written, "tools": tools,
            "errors": errs, "exit": r.returncode, "seconds": round(time.time() - t, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("route", help="<provider>/<model>, e.g. 9router/cx/gpt-5.5")
    ap.add_argument("--probes", type=int, default=3)
    ap.add_argument("--smokes", type=int, default=2)
    ap.add_argument("--context", type=int, default=200000)
    ap.add_argument("--output", type=int, default=32768)
    ap.add_argument("--stage-copy", default="")
    ap.add_argument("--venv", default="")
    ap.add_argument("--stage-path", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    prov, model = a.route.split("/", 1)
    base, key = _provider(prov)
    lst = listing(base, key, model)
    probes = [chat_probe(base, key, model) for _ in range(a.probes)]
    identities = sorted({p.get("answered_by") for p in probes if p.get("answered_by")})
    smokes = [tool_smoke(a.route, model, {"context": a.context, "output": a.output}, i + 1) for i in range(a.smokes)]
    stage = (ep.stage_env_check(Path(a.stage_copy), Path(a.venv), a.stage_path)
             if a.stage_copy and a.venv and a.stage_path else None)
    req = {
        "exact_fixed_route_resolves": lst["listed"] and lst["route_kind"] == "FIXED_MODEL",
        "no_4xx_or_other_error_on_any_probe": all(p["http"] == 200 for p in probes),
        "tool_calling_works": bool(smokes) and all(s["ok"] for s in smokes),
        "model_identity_constant_between_probes": len(identities) == 1,
        "reviewer_read_only_environment_clean": stage["pass"] if stage is not None else "not measured here (driver preflight row)",
    }
    ok = all(v is True or isinstance(v, str) for v in req.values())
    summary = {"route": a.route, "route_kind": lst["route_kind"], "resolved_model": identities[0] if len(identities) == 1 else identities,
               "chat_probes": f"{sum(p['http'] == 200 for p in probes)}/{a.probes}", "tool_smokes": f"{sum(s['ok'] for s in smokes)}/{a.smokes}",
               "declared_limit": {"context": a.context, "output": a.output}}
    rec = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "route": a.route, "listing": lst, "chat_probes": probes,
           "tool_smokes": smokes, "stage_env_check": stage, "requirements": req, "pass": ok, "summary_for_identity": summary}
    Path(a.out).write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    for k, v in req.items():
        print(("ok " if v is True else ".. " if isinstance(v, str) else "!! ") + k + ("" if isinstance(v, bool) else f" ({v})"))
    print("provider preflight", "PASS" if ok else "FAIL", "|", json.dumps(summary))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
