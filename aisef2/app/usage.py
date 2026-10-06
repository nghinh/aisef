"""What a run used, re-derivable from its evidence (V2.1, proposal D): requests, tokens by class, time, retries, and
money only when the operator gave a price table — an unknown price is `null` with its reason, never 0.

Sources: each session's event stream (the client's per-step token report: uncached input, cache read, cache write,
output, reasoning), the preflight's ledger, and the journal (provider requests, retries, story outcomes). A step that
reports no tokens makes the session's tokens a lower bound and its cost unknown (`steps_without_tokens`); a session
that started and finished no step is unaccounted. Settings `prices` (optional):
{"currency": "USD", "input_per_mtok": x, "cache_read_per_mtok": x, "cache_write_per_mtok": x, "output_per_mtok": x,
 "source": "...", "effective_date": "YYYY-MM-DD"} — reasoning tokens priced as output.

`no_progress` reads the journal for retries that changed nothing: the same failures, attempt after attempt. It only
reports — a retry is decided by the failure taxonomy and its limits, never here (NO_SIDE_RETRY_COUNTER)."""

from __future__ import annotations

import json
import pathlib
import re
from typing import Mapping

PRICE_KEYS = ("currency", "input_per_mtok", "cache_read_per_mtok", "cache_write_per_mtok", "output_per_mtok", "source",
              "effective_date")
CLASSES = ("input", "cache_read", "cache_write", "output", "reasoning")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def price_problem(p) -> str | None:
    if not isinstance(p, Mapping) or sorted(p) != sorted(PRICE_KEYS):
        return f"prices hold exactly {list(PRICE_KEYS)}"
    for k in ("input_per_mtok", "cache_read_per_mtok", "cache_write_per_mtok", "output_per_mtok"):
        v = p[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
            return f"prices.{k} is a non-negative number (per million tokens)"
    if not (isinstance(p["source"], str) and p["source"]) or not (isinstance(p["effective_date"], str)
                                                                    and _DATE.fullmatch(p["effective_date"])):
        return "prices name their source and effective_date (YYYY-MM-DD)"
    if not isinstance(p["currency"], str) or not p["currency"]:
        return "prices.currency is named"
    return None


def session_tokens(log: pathlib.Path) -> dict:
    """One session's tokens by class, its finished steps and those that reported no tokens."""
    t = dict.fromkeys(CLASSES, 0)
    steps = blind = 0
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") != "step_finish":
            continue
        steps += 1
        tk = (ev.get("part") or {}).get("tokens")
        if not isinstance(tk, dict) or not all(isinstance(tk.get(k), int) for k in ("input", "output")):
            blind += 1
            continue
        cache = tk.get("cache") or {}
        t["input"] += tk["input"]
        t["cache_read"] += int(cache.get("read") or 0)
        t["cache_write"] += int(cache.get("write") or 0)
        t["output"] += tk["output"]
        t["reasoning"] += int(tk.get("reasoning") or 0)
    return {"tokens": t, "steps": steps, "steps_without_tokens": blind}


def _usd(t: Mapping, p: Mapping) -> float:
    return round((t["input"] * p["input_per_mtok"] + t["cache_read"] * p["cache_read_per_mtok"]
                  + t["cache_write"] * p["cache_write_per_mtok"]
                  + (t["output"] + t["reasoning"]) * p["output_per_mtok"]) / 1e6, 6)


def usage(out: pathlib.Path, events: list[dict], prices: Mapping | None, rec: Mapping) -> dict:
    """The run's account. `events` the journal's (seq, type, data) as dicts; `rec` the record (its timestamps)."""
    sessions, totals, unknown = [], dict.fromkeys(CLASSES, 0), []
    for log in sorted((out / "sessions").glob("*.jsonl")):
        s = session_tokens(log)
        for k in CLASSES:
            totals[k] += s["tokens"][k]
        partial = s["steps_without_tokens"] > 0 or s["steps"] == 0
        if partial:
            unknown.append(log.name)
        row = {"session": log.name, **s}
        if prices:
            row["cost"] = None if partial else _usd(s["tokens"], prices)
        sessions.append(row)
    try:
        from aisef2.app import preflight
        pre = preflight.accounting(out / "preflight" / "LEDGER.jsonl")
    except (OSError, ValueError, KeyError):
        pre = None
    requests = sum(1 for e in events if e["type"] == "provider/request")
    retried = [e["data"].get("story_id") for e in events if e["type"] == "story/retry"]    # the journal's decisions,
    retries = {s: retried.count(s) for s in sorted(set(retried))}                           # read — never a side counter
    started, finished = rec.get("started"), rec.get("finished")
    money: dict = {"value": None, "status": "unknown", "why": "the settings give no price table"}
    if prices:
        known = sum(r["cost"] for r in sessions if r.get("cost") is not None)
        if pre and isinstance(pre.get("input_tokens"), int) and isinstance(pre.get("output_tokens"), int):
            known += _usd({"input": pre["input_tokens"], "cache_read": 0, "cache_write": 0,
                           "output": pre["output_tokens"], "reasoning": 0}, prices)
        money = {"currency": prices["currency"], "source": prices["source"], "effective_date": prices["effective_date"],
                 "known": round(known, 6), "sessions_unknown": unknown,
                 "value": round(known, 6) if not unknown else None,
                 "status": "known" if not unknown else "partial: these sessions' cost is unknown (not 0)"}
    return {"provider_requests_journaled": requests, "sessions": sessions, "tokens": totals, "preflight": pre,
            "retries": retries, "wall_s": round(finished - started, 3) if isinstance(started, (int, float))
            and isinstance(finished, (int, float)) else None, "cost": money}


def no_progress(events: list[dict]) -> list[dict]:
    """Per story, consecutive failed attempts with the same failures (codes and details): retries that changed nothing
    the kernel can see. A report; the taxonomy alone decides a retry."""
    attempts: dict[str, list[list[str]]] = {}
    current: dict[str, list[str]] = {}
    for e in events:
        sid = e["data"].get("story_id")
        if e["type"] == "failure/observed":
            current.setdefault(sid, []).append(f"{e['data'].get('code')}: {e['data'].get('detail')}")
        elif e["type"] in ("story/retry", "story/rollback", "story/commit"):
            attempts.setdefault(sid, []).append(sorted(current.pop(sid, [])))
    out = []
    for sid, rows in attempts.items():
        same = [n for n in range(1, len(rows)) if rows[n] and rows[n] == rows[n - 1]]
        if same:
            out.append({"story": sid, "attempts_repeating_the_one_before": [n + 1 for n in same], "failures": rows[same[0]]})
    return out
