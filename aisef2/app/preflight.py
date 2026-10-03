"""The provider preflight: before any session, the fixed route is measured on its OpenAI-compatible endpoint — the
model listing and `chat_probes` one-token completions — and attested only when every answer was served by the declared
model, under one deployment fingerprint (or none exposed by every answer). Anything else is an identity stop: the run
does not start. Every request is written to the ledger before it is sent and after it returns, and counted in the
run's budget (requests, tokens). The fingerprint is a drift detector, never a claim about model weights."""

from __future__ import annotations

import json
import os
import pathlib
import urllib.error
import urllib.request

NOT_EXPOSED = "NOT_EXPOSED"
PROBE_PROMPT = "Reply with the single word: ok"


class IdentityStop(Exception):
    """The route cannot be attested: no session may start."""


def http_transport(endpoint: str, key_env: str, timeout_s: float = 60.0):
    """(path, body | None) -> (status, json): GET when `body` is None, else POST; the key read from `key_env` here and
    sent as a bearer token, never recorded."""
    key = os.environ.get(key_env)
    if not key:
        raise IdentityStop(f"the provider key variable {key_env} is not set")

    def call(path: str, body: dict | None = None) -> tuple[int, dict]:
        req = urllib.request.Request(endpoint + path, data=None if body is None else json.dumps(body).encode("utf-8"),
                                     method="GET" if body is None else "POST",
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as r:
                return r.status, json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            return e.code, {}
        except (urllib.error.URLError, OSError, ValueError) as e:
            return 0, {"transport_error": type(e).__name__}
    return call


def _append(ledger: pathlib.Path, row: dict) -> None:
    with ledger.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def accounting(ledger: pathlib.Path) -> dict:
    """What the preflight spent, from its ledger alone: a request sent and never answered is unaccounted."""
    rows = [json.loads(x) for x in ledger.read_text(encoding="utf-8").splitlines()] if ledger.exists() else []
    sent = {r["n"] for r in rows if r["event"] == "sent"}
    done = {r["n"]: r for r in rows if r["event"] == "done"}
    return {"provider_requests": len(sent), "turns": 0,
            "input_tokens": sum(int(r.get("input_tokens") or 0) for r in done.values()),
            "output_tokens": sum(int(r.get("output_tokens") or 0) for r in done.values()),
            "unaccounted": sorted(sent - set(done))}


def run(route: str, chat_probes: int, transport, directory: pathlib.Path) -> dict:
    """Measure the route; the observation and the verdict ATTESTED or OPAQUE (with every problem named)."""
    directory.mkdir(parents=True, exist_ok=False)
    ledger = directory / "LEDGER.jsonl"
    model = route.split("/", 1)[1]
    obs: dict = {"route": route, "declared_model": model, "listing": None, "probes": []}
    n = 1
    _append(ledger, {"n": n, "event": "sent", "kind": "listing"})
    code, body = transport("/models")
    _append(ledger, {"n": n, "event": "done", "http": code})
    row = next((x for x in (body.get("data") or []) if isinstance(x, dict) and x.get("id") == model), None)
    obs["listing"] = {"http": code, "listed": row is not None, "id": (row or {}).get("id"), "owned_by": (row or {}).get("owned_by")}
    for _ in range(chat_probes):
        n += 1
        _append(ledger, {"n": n, "event": "sent", "kind": "chat"})
        code, body = transport("/chat/completions", {"model": model, "messages": [{"role": "user", "content": PROBE_PROMPT}],
                                                     "max_tokens": 1, "temperature": 0})
        usage = body.get("usage") or {}
        _append(ledger, {"n": n, "event": "done", "http": code, "input_tokens": usage.get("prompt_tokens") or 0,
                         "output_tokens": usage.get("completion_tokens") or 0})
        obs["probes"].append({"http": code, "served_model": body.get("model"),
                              "system_fingerprint": body.get("system_fingerprint") or NOT_EXPOSED})
    problems = identity_problems(obs)
    rec = {"observation": obs, "problems": problems, "verdict": "OPAQUE" if problems else "ATTESTED",
           "accounting": accounting(ledger)}
    (directory / "PREFLIGHT.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return rec


def identity_problems(obs: dict) -> list[str]:
    out = []
    if obs["listing"]["http"] != 200 or not obs["listing"]["listed"]:
        out.append(f"the provider does not list the declared model {obs['declared_model']}")
    for i, p in enumerate(obs["probes"]):
        if p["http"] != 200:
            out.append(f"probe {i}: HTTP {p['http']}")
        elif p["served_model"] != obs["declared_model"]:
            out.append(f"probe {i}: served by {p['served_model']!r}, not the declared model (an alias or a re-route)")
    fingerprints = {p["system_fingerprint"] for p in obs["probes"]}
    if len(fingerprints) > 1:
        out.append(f"the deployment changed between probes ({len(fingerprints)} fingerprints)")
    return out


def fingerprint_fields(obs: dict) -> dict:
    """The measured fields the ATTESTED capability's fingerprint binds."""
    return {"declared_model": obs["declared_model"], "listed_id": obs["listing"]["id"], "owned_by": obs["listing"]["owned_by"],
            "served_models": sorted({p["served_model"] for p in obs["probes"]}),
            "system_fingerprint": sorted({p["system_fingerprint"] for p in obs["probes"]})}


def deployment(obs: dict) -> str | None:
    fps = {p["system_fingerprint"] for p in obs["probes"]}
    return next(iter(fps)) if len(fps) == 1 and NOT_EXPOSED not in fps else None
