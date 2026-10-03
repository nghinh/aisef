"""The client: one OpenCode session at a time, inside the kernel's owned process range, on the fixed route, with a built
environment, under the run's budget and a per-session turn cap. A session with any of those unbound is refused before
the client is looked up (V2.0 release charter §6).

The budget keeps no counter of its own: what was spent is re-derived, each time it is asked, from the evidence — the
preflight's accounting, the journal's provider/request events and the session streams (one file each). A provider
request is one session the run starts or one request of the preflight; a turn is a finished step; input counts prompt
and cached tokens together, output counts completion and reasoning tokens together, as the client reports them.
Anything that cannot be accounted for ends the run like a reached ceiling."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import time

from aisef2.runtime.process_range import ProcessRange

POLL_S = 5.0
#: what the client's telemetry cannot show (recorded with every account of the budget)
LIMITATION = ("spend is what the client reports per finished step: an HTTP request that finishes no step (a client "
              "retry, a failed request, the one in flight when a stop is issued) is not in the telemetry, and a stop is "
              "issued at the first reading that shows a ceiling reached, so totals can pass a ceiling by the steps "
              "finished since the reading before")


class SessionRefused(Exception):
    """A session that is not fully bound never starts."""


def read_session(log: pathlib.Path) -> dict:
    """What a session's event stream says so far: its text, its error, its turns, its tokens, and how many finished
    steps carry no token report."""
    text, error, turns, tokens, blind = [], None, 0, {"input": 0, "output": 0}, 0
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        part = ev.get("part") or {}
        if ev.get("type") == "text":
            text.append(str(part.get("text") or ""))
        elif ev.get("type") == "error":
            info = ev.get("error") or {}
            data = info.get("data") or {}
            error = f"{info.get('name') or 'error'}: {str(data.get('message') or '')[:200]}" + (
                f" (HTTP {data['statusCode']})" if data.get("statusCode") else "")
        elif ev.get("type") == "step_finish":
            turns += 1
            tk = part.get("tokens")
            if not isinstance(tk, dict) or not all(isinstance(tk.get(k), int) for k in ("input", "output")):
                blind += 1
                continue
            cache = tk.get("cache") or {}
            tokens["input"] += tk["input"] + int(cache.get("read") or 0) + int(cache.get("write") or 0)
            tokens["output"] += tk["output"] + int(tk.get("reasoning") or 0)
    return {"error": error, "text": "".join(text), "turns": turns, "tokens": tokens, "steps_without_tokens": blind}


class Budget:
    KEYS = ("provider_requests", "turns", "input_tokens", "output_tokens")

    def __init__(self, limits: dict, base: dict, logs: pathlib.Path, requests=lambda: 0) -> None:
        if sorted(limits) != sorted(self.KEYS) or sorted(k for k in base if k in self.KEYS) != sorted(self.KEYS):
            raise ValueError("a budget has the four ceilings, and a base that accounts for each of them")
        self.limits, self.base, self.logs, self.requests = dict(limits), {k: int(base[k]) for k in self.KEYS}, logs, requests

    def spend(self, live: pathlib.Path | None = None) -> dict:
        logs = sorted(self.logs.glob("*.jsonl")) if self.logs.is_dir() else []
        seen = {p: read_session(p) for p in logs}
        recorded = int(self.requests())
        unaccounted = [f"{len(logs)} sessions were started but {recorded} provider requests are recorded"] if len(logs) > recorded else []
        for p, x in seen.items():
            if x["steps_without_tokens"]:
                unaccounted.append(f"{p.name}: {x['steps_without_tokens']} finished steps report no tokens")
            if p != live and not x["turns"]:
                unaccounted.append(f"{p.name}: a session that started finished no step — what it sent is unknown")
        return {"provider_requests": self.base["provider_requests"] + recorded,
                "turns": self.base["turns"] + sum(x["turns"] for x in seen.values()),
                "input_tokens": self.base["input_tokens"] + sum(x["tokens"]["input"] for x in seen.values()),
                "output_tokens": self.base["output_tokens"] + sum(x["tokens"]["output"] for x in seen.values()),
                "sessions_started": len(logs), "requests_recorded": recorded, "unaccounted": unaccounted}

    def reached(self, live: pathlib.Path | None = None, in_progress: bool = False) -> str | None:
        """Why the run must end now — a ceiling reached, or spend that cannot be accounted for — or None. While a
        request is in progress (already recorded) the request ceiling ends the run only when EXCEEDED."""
        spent = self.spend(live)
        if spent["unaccounted"]:
            return "unaccounted: " + "; ".join(spent["unaccounted"])
        for k in self.KEYS:
            if spent[k] > self.limits[k] or (spent[k] == self.limits[k] and not (in_progress and k == "provider_requests")):
                return f"max_{k}: {spent[k]} of {self.limits[k]}"
        return None

    def exceeded(self) -> str | None:
        """Spend PAST a ceiling, or spend that cannot be accounted for: the run broke its budget. Spend exactly AT a
        ceiling is not that (review IR-02) — it only keeps more work from starting (`reached`)."""
        spent = self.spend()
        if spent["unaccounted"]:
            return "unaccounted: " + "; ".join(spent["unaccounted"])
        for k in self.KEYS:
            if spent[k] > self.limits[k]:
                return f"max_{k} exceeded: {spent[k]} of {self.limits[k]}"
        return None

    def account(self) -> dict:
        return {"limits": dict(self.limits), "preflight": dict(self.base), "spent": self.spend(), "reached": self.reached(),
                "limitation": LIMITATION}


def environment(names: tuple[str, ...], overlay: dict) -> dict:
    """The client's whole environment, built: the operator's PATH, HOME and locale, the variables the settings name,
    and the configuration overlay that fixes the route — nothing else of the caller's environment."""
    keep = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "SystemRoot", "WINDIR", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP",
            "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", *names)
    return {**{k: os.environ[k] for k in keep if k in os.environ}, "OPENCODE_CONFIG_CONTENT": json.dumps(overlay, sort_keys=True)}


def overlay(route: str) -> dict:
    """The client configuration overlay: the model and the small model are the one fixed route."""
    return {"model": route, "small_model": route}


def wait_within(r, log: pathlib.Path, timeout_s: float, budget: Budget, turn_cap: int) -> tuple[int | None, str | None]:
    deadline, code, stopped = time.monotonic() + timeout_s, None, None
    while code is None and not stopped and time.monotonic() < deadline:
        code = r.wait(min(POLL_S, max(0.0, deadline - time.monotonic())))
        if code is None:
            stopped = budget.reached(log, in_progress=True)
            if not stopped and read_session(log)["turns"] >= turn_cap:
                stopped = f"session turn cap: {turn_cap} turns"
    return code, stopped


REDACTED = b"[REDACTED]"


def redact(log: pathlib.Path, secrets) -> int:
    """Every occurrence of a secret value in the session's stream replaced (a tool the model ran may print its
    environment); how many. The stream stays JSON: the values are replaced inside their strings."""
    data = log.read_bytes()
    count = 0
    for s in sorted({x.encode("utf-8") for x in secrets if x}, key=len, reverse=True):
        count += data.count(s)
        data = data.replace(s, REDACTED)
    if count:
        log.write_bytes(data)
    return count


def session(name: str, prompt: str, cwd: str, log: pathlib.Path, timeout_s: float, *, model: str | None = None,
            env: dict | None = None, budget: Budget | None = None, turn_cap: int | None = None, exe: str | None = None,
            secrets: tuple[str, ...] = ()) -> dict:
    """One `opencode run --format json` session in a process range of its own; its event stream goes to `log`. Nothing
    starts when anything is unbound, when the evidence shows the budget reached or spend unaccounted, or when `log`
    exists (a session's evidence is never overwritten); the range is released when the budget or the turn cap is
    reached while it runs."""
    unbound = [k for k, v in (("model", model), ("env", env), ("budget", budget), ("turn_cap", turn_cap)) if v is None]
    if unbound:
        raise SessionRefused(f"a model session needs a fixed route, a built environment, a budget and a turn cap; "
                             f"unbound: {', '.join(unbound)}")
    started = time.monotonic()
    stopped = f"{log.name} exists: a session's evidence is never overwritten" if log.exists() else budget.reached(in_progress=True)
    code = None
    if not stopped:
        exe = exe or shutil.which("opencode", path=env.get("PATH"))
        if not exe:
            raise SessionRefused("the client (opencode) is not on the PATH the run gives it")
        argv = [exe, "run", "--format", "json", "--model", model, "--title", name, "--dir", cwd, prompt]
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w", encoding="utf-8") as fh:
            r = ProcessRange(name, argv, cwd=cwd, env=env, output=fh)
            r.start()
            try:
                code, stopped = wait_within(r, log, timeout_s, budget, turn_cap)
            finally:
                r.release()
        redacted = redact(log, secrets)
        seen = read_session(log)
        return {"exit": code, "timed_out": code is None and not stopped, "stopped": stopped, "started": True,
                "error": seen["error"], "text": seen["text"], "turns": seen["turns"], "tokens": seen["tokens"],
                "seconds": round(time.monotonic() - started, 1), "log": log.name, "redacted": redacted}
    return {"exit": None, "timed_out": False, "stopped": stopped, "started": False, "error": stopped, "text": "", "turns": 0,
            "tokens": {"input": 0, "output": 0}, "seconds": 0.0, "log": None}
