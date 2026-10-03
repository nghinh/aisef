"""The run settings (`FORMAT`): every value that decides what a run may spend and whom it talks to, explicit — there is
no default route, client, budget, turn cap or retry limit (V2.0 release charter §6: a run never starts the default
model, an inherited environment, unlimited turns or tokens, or an unattested route).

    {"format": "aisef-v2-run/1",
     "client": "opencode",
     "route": "<provider>/<model>",                       # given to the client explicitly
     "provider": {"name": "<provider>", "endpoint": "https://.../v1",
                  "api_key_env": "<VARIABLE>" | null,       # null: the client's own configuration holds the key
                  "served_model": "<model>",                # the model the provider reports serving the route
                  "listed_owner": "<owner>" | null,         # the owner its model listing names (null: not checked)
                  "model_limit": {"context": n, "output": n}},  # declared to the client for the route's model
     "client_env": ["<VARIABLE>", ...],                   # the only operator variables the client receives
     "budget": {"provider_requests": n, "turns": n, "input_tokens": n, "output_tokens": n},
     "max_turns_per_session": n,
     "limits": {"DEVELOPER": n, "PLAN": n, "ENVIRONMENT": n, "PROVIDER": n, "INTEGRATION": n, "REVIEW": n, "SECURITY": n},
     "timeouts_s": {"developer": s, "reviewer": s, "tool": s, "probe": s},
     "preflight": {"chat_probes": n}}
"""

from __future__ import annotations

import json
import math
import pathlib
from dataclasses import dataclass
from typing import Mapping

from aisef2.arch.enums import Owner

FORMAT = "aisef-v2-run/1"
CLIENTS = ("opencode",)
BUDGET_KEYS = ("provider_requests", "turns", "input_tokens", "output_tokens")
PROVIDER_KEYS = ("api_key_env", "endpoint", "listed_owner", "model_limit", "name", "served_model")
KEYS = ("format", "client", "route", "provider", "client_env", "budget", "max_turns_per_session", "limits", "timeouts_s",
        "preflight")


class SettingsError(ValueError):
    """The settings do not bound a run: refused (fail closed)."""


@dataclass(frozen=True)
class Settings:
    client: str
    route: str
    provider: str
    endpoint: str
    api_key_env: str | None
    served_model: str
    listed_owner: str | None
    model_limit: dict[str, int]
    client_env: tuple[str, ...]
    budget: dict[str, int]
    max_turns_per_session: int
    limits: dict[Owner, int]
    timeouts_s: dict[str, float]
    chat_probes: int
    content: dict           # the settings as given, for the RunSpec and the record

    @property
    def model(self) -> str:
        return self.route.split("/", 1)[1]


def _count(v, name: str, minimum: int = 1) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or v < minimum:
        raise SettingsError(f"{name} is an integer >= {minimum}, not {v!r}")
    return v


def load(data: Mapping) -> Settings:
    if not isinstance(data, Mapping) or data.get("format") != FORMAT:
        raise SettingsError(f"not run settings of format {FORMAT}")
    if sorted(data) != sorted(KEYS):
        raise SettingsError(f"run settings hold exactly {sorted(KEYS)}; these hold {sorted(data)} — nothing is defaulted")
    if data["client"] not in CLIENTS:
        raise SettingsError(f"client is one of {CLIENTS}")
    route = data["route"]
    if not isinstance(route, str) or route.count("/") < 1 or not all(route.split("/", 1)):
        raise SettingsError("route is <provider>/<model>, one fixed route")
    p = data["provider"]
    if not isinstance(p, Mapping) or sorted(p) != list(PROVIDER_KEYS) or p["name"] != route.split("/", 1)[0]:
        raise SettingsError(f"provider is {{{', '.join(PROVIDER_KEYS)}}}, its name the route's provider")
    if not str(p["endpoint"]).startswith(("https://", "http://127.0.0.1", "http://localhost")):
        raise SettingsError("the provider endpoint is https (or a loopback address)")
    if p["api_key_env"] is not None and not (isinstance(p["api_key_env"], str) and p["api_key_env"]):
        raise SettingsError("provider.api_key_env names a variable, or is null (the client's configuration holds the key)")
    if not (isinstance(p["served_model"], str) and p["served_model"]):
        raise SettingsError("provider.served_model is the model the provider reports serving the route")
    if p["listed_owner"] is not None and not (isinstance(p["listed_owner"], str) and p["listed_owner"]):
        raise SettingsError("provider.listed_owner is the owner the model listing names, or null")
    lim = p["model_limit"]
    if not isinstance(lim, Mapping) or sorted(lim) != ["context", "output"]:
        raise SettingsError("provider.model_limit is {context, output}")
    model_limit = {k: _count(lim[k], f"provider.model_limit.{k}") for k in ("context", "output")}
    env = data["client_env"]
    if not isinstance(env, list) or not all(isinstance(x, str) and x for x in env):
        raise SettingsError("client_env is the list of operator variable names the client receives")
    b = data["budget"]
    if not isinstance(b, Mapping) or sorted(b) != sorted(BUDGET_KEYS):
        raise SettingsError(f"budget names exactly {list(BUDGET_KEYS)}")
    budget = {k: _count(b[k], f"budget.{k}") for k in BUDGET_KEYS}
    lim = data["limits"]
    if not isinstance(lim, Mapping) or sorted(lim) != sorted(o.value for o in Owner):
        raise SettingsError(f"limits name every owner {[o.value for o in Owner]}")
    limits = {Owner(k): _count(v, f"limits.{k}", 0) for k, v in lim.items()}
    t = data["timeouts_s"]
    if not isinstance(t, Mapping) or sorted(t) != ["developer", "probe", "reviewer", "tool"]:
        raise SettingsError("timeouts_s names developer, reviewer, tool and probe")
    timeouts = {}
    for k, v in t.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise SettingsError(f"timeouts_s.{k} is a positive number of seconds")
        timeouts[k] = float(v)
    pre = data["preflight"]
    if not isinstance(pre, Mapping) or sorted(pre) != ["chat_probes"]:
        raise SettingsError("preflight names chat_probes")
    probes = _count(pre["chat_probes"], "preflight.chat_probes", 2)
    if 1 + probes > budget["provider_requests"]:     # the preflight's requests are the budget's too (review ADV-09)
        raise SettingsError(f"the preflight's {1 + probes} requests exceed budget.provider_requests {budget['provider_requests']}")
    return Settings(data["client"], route, p["name"], str(p["endpoint"]).rstrip("/"), p["api_key_env"], p["served_model"],
                    p["listed_owner"], model_limit, tuple(env),
                    budget, _count(data["max_turns_per_session"], "max_turns_per_session"), limits, timeouts, probes,
                    dict(data))


def read(path: str | pathlib.Path) -> Settings:
    return load(json.loads(pathlib.Path(path).read_text(encoding="utf-8")))
