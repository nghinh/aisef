"""What a run used, re-derivable from its evidence (V2.1, proposal D): requests, tokens by class, time, retries, and
money only when the operator gave a price table — an unknown price is `null` with its reason, never 0.

Sources: each session's event stream (the client's per-step token report: uncached input, cache read, cache write,
output, reasoning), the preflight's ledger, and the journal (provider requests, retries, story outcomes). A step that
reports no tokens makes the session's tokens a lower bound and its cost unknown (`steps_without_tokens`); a session
that started and finished no step is unaccounted. The preflight's spend is unknown, and so the cost `partial`, when its
ledger is there and does not read, or holds a request sent and never answered (what `lineage.account_of` lists as
unaccounted) — never counted as 0; no ledger at all is no preflight spend. Settings `prices` (optional):
{"currency": "USD", "input_per_mtok": x, "cache_read_per_mtok": x, "cache_write_per_mtok": x, "output_per_mtok": x,
 "source": "...", "effective_date": "YYYY-MM-DD"} — reasoning tokens priced as output.

`no_progress` reads the journal for retries that changed nothing: the same failures, attempt after attempt. It only
reports — a retry is decided by the failure taxonomy and its limits, never here (NO_SIDE_RETRY_COUNTER). It is a
function of any journal the six control projections admit (`aisef run --verify` refuses the others before it is
asked: aisef2/app/verify.py), not only of the journals the kernel's story runner happens to write."""

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
    from aisef2.app import preflight
    gaps = ["these sessions' cost is unknown (not 0)"] if unknown else []      # why the run's cost is not a figure
    try:
        pre = preflight.accounting(out / "preflight" / "LEDGER.jsonl")     # an absent ledger is no preflight spend: 0
    except Exception:  # noqa: BLE001 — a ledger that is there and the reader refuses is a preflight not known
        pre = None
        gaps.append("the preflight's ledger does not read: its cost is unknown (not 0)")
    else:
        if pre.get("unaccounted"):      # what lineage.account_of lists: spend that is unknown, not 0
            gaps.append(f"preflight requests {pre['unaccounted']} were sent and never answered: their cost is unknown "
                        "(not 0)")
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
                 "value": None if gaps else round(known, 6),
                 "status": "partial: " + "; ".join(gaps) if gaps else "known"}
    return {"provider_requests_journaled": requests, "sessions": sessions, "tokens": totals, "preflight": pre,
            "retries": retries, "wall_s": round(finished - started, 3) if isinstance(started, (int, float))
            and isinstance(finished, (int, float)) else None, "cost": money}


def no_progress(events: list[dict]) -> list[dict]:
    """Per story, consecutive failed attempts with the same failures (codes and details): retries that changed nothing
    the kernel can see. A report; the taxonomy alone decides a retry.

    An attempt is *failed* when it ended in `story/retry` or `story/rollback`; its failures are the `failure/observed`
    its story journaled after the later of the attempt's `story/begin` and the story's previous outcome, up to that
    outcome. A committed attempt is progress and is never reported, whatever failures it observed — a commit is not a
    retry, and no attempt follows it. A failure observed after an attempt's outcome and before the story's next
    `story/begin` is nobody's for this report: not the next attempt's, which had not begun."""
    attempts: dict[str, list[list[str]]] = {}
    current: dict[str, list[str]] = {}
    for e in events:
        sid = e["data"].get("story_id")
        if e["type"] == "failure/observed":
            current.setdefault(sid, []).append(f"{e['data'].get('code')}: {e['data'].get('detail')}")
        elif e["type"] == "story/begin":
            current.pop(sid, None)     # a new attempt: what the story observed since its last outcome is not its own
        elif e["type"] in ("story/retry", "story/rollback"):
            attempts.setdefault(sid, []).append(sorted(current.pop(sid, [])))
    out = []
    for sid, rows in attempts.items():
        same = [n for n in range(1, len(rows)) if rows[n] and rows[n] == rows[n - 1]]
        if same:
            out.append({"story": sid, "attempts_repeating_the_one_before": [n + 1 for n in same], "failures": rows[same[0]]})
    return out
