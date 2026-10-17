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

Optional (V2.1): "review", "prices", "confinement" (app/confine: the client's sessions under bubblewrap, Linux only).
"""

from __future__ import annotations

import json
import math
import pathlib
import urllib.parse
from dataclasses import dataclass
from typing import Mapping

from aisef2.arch.enums import Owner

FORMAT = "aisef-v2-run/1"
CLIENTS = ("opencode",)
BUDGET_KEYS = ("provider_requests", "turns", "input_tokens", "output_tokens")
PROVIDER_KEYS = ("api_key_env", "endpoint", "listed_owner", "model_limit", "name", "served_model")
KEYS = ("format", "client", "route", "provider", "client_env", "budget", "max_turns_per_session", "limits", "timeouts_s",
        "preflight")
#: V2.1: optional keys. Absent, the run is exactly a 2.0.0 run and the record says which rule applied:
#: review — {"policy": "fix-loop" | "advisory", "min_severity": "low" | "medium" | "high" | "critical"} (app/review_verify),
#:   and optionally "finder": "model" (the default, 2.0.0's model reviewer) | "ocr" with "ocr": {"exe": <absolute path>,
#:   "sha256": <the binary's>, "timeout_min": n, "max_tokens": n} (app/review_ocr). With finder "ocr" — under either
#:   policy: no story commits without its review — the run asks the binary before it starts anything (the pin, then its
#:   `version`; app/run.ocr_identity, `aisef run --check` too) and the review asks again at the moment of use
#: prices — the price table money is computed with (app/usage); absent, every cost is unknown (null), never 0
#: confinement — {"backend": "bwrap", "bwrap": <absolute path>, "network": "host", "read_only": [<absolute path>, ...]}
#:   (app/confine): every session the client starts (developer, model reviewer) confined, egress NOT confined ("none" is
#:   measurement-only: no route to the provider); measured before the first provider request, the run refused otherwise.
#:   Not with review.finder "ocr": Open Code Review calls the model outside the client's sessions, unconfined
OPTIONAL = ("review", "prices", "confinement")
#: what an absent `review` means: 2.0.0's rule (no finding blocks), named, never a silent default
REVIEW_ABSENT = {"policy": "advisory", "min_severity": "critical", "finder": "model", "ocr": None, "given": False}
FINDERS = ("model", "ocr")
OCR_KEYS = ("exe", "max_tokens", "sha256", "timeout_min")


class SettingsError(ValueError):
    """The settings do not bound a run: refused (fail closed)."""


#: the only hosts a plaintext (http) endpoint may name — the provider key travels in clear otherwise
LOOPBACK = ("127.0.0.1", "localhost", "::1")


def endpoint_problem(endpoint) -> str | None:
    """Why `endpoint` cannot carry the provider key, or None: https to a named host, or http to a loopback host —
    decided on the parsed URL (a host that merely begins with "localhost" is not loopback), with no credentials,
    query or fragment in it."""
    if not isinstance(endpoint, str):
        return "the provider endpoint is a URL string"
    try:
        u = urllib.parse.urlsplit(endpoint)
        host, _port = u.hostname, u.port        # a malformed port raises here
    except ValueError as e:
        return f"the provider endpoint is not a URL: {e}"
    if u.scheme not in ("https", "http") or not host:
        return "the provider endpoint is an https URL (or http to a loopback address) with a host"
    if u.username is not None or u.password is not None or u.query or u.fragment:
        return "the provider endpoint carries no credentials, query or fragment (the key is sent as a header)"
    if u.scheme == "http" and host not in LOOPBACK:
        return f"the provider endpoint is https (or http to {', '.join(LOOPBACK)}): {host} is not loopback"
    return None


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
    review: dict = None     # V2.1: the review policy; REVIEW_ABSENT when the settings name none
    confinement: dict | None = None     # V2.1 (F): app/confine's setting; None: the sessions are not confined

    @property
    def prices(self) -> dict | None:
        """V2.1: the operator's price table (app/usage), or None: then every cost is unknown, never 0."""
        return self.content.get("prices")

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
    if sorted(k for k in data if k not in OPTIONAL) != sorted(KEYS):
        raise SettingsError(f"run settings hold exactly {sorted(KEYS)} (and optionally {list(OPTIONAL)}); these hold "
                            f"{sorted(data)} — nothing is defaulted")
    review = dict(REVIEW_ABSENT)
    if "review" in data:
        from aisef2.app.review_verify import POLICIES, SEVERITIES
        r = data["review"]
        if not isinstance(r, Mapping) or not {"min_severity", "policy"} <= set(r) <= {"min_severity", "policy", "finder", "ocr"} \
                or r["policy"] not in POLICIES or r["min_severity"] not in SEVERITIES:
            raise SettingsError(f"review is {{policy: one of {list(POLICIES)}, min_severity: one of {list(SEVERITIES)}}}"
                                f" and optionally finder: one of {list(FINDERS)}")
        finder = r.get("finder", "model")
        if finder not in FINDERS or (finder == "ocr") != ("ocr" in r):
            raise SettingsError(f"review.finder is one of {list(FINDERS)}; review.ocr is given exactly when it is ocr")
        ocr = None
        if finder == "ocr":
            o = r["ocr"]
            if not isinstance(o, Mapping) or sorted(o) != list(OCR_KEYS) or not isinstance(o["exe"], str) \
                    or not pathlib.PurePath(o["exe"]).is_absolute() \
                    or not (isinstance(o["sha256"], str) and len(o["sha256"]) == 64
                            and all(ch in "0123456789abcdef" for ch in o["sha256"])):
                raise SettingsError(f"review.ocr is {{{', '.join(OCR_KEYS)}}}: the binary by absolute path and its sha256")
            ocr = {"exe": o["exe"], "sha256": o["sha256"], "timeout_min": _count(o["timeout_min"], "review.ocr.timeout_min"),
                   "max_tokens": _count(o["max_tokens"], "review.ocr.max_tokens")}
        review = {"policy": r["policy"], "min_severity": r["min_severity"], "finder": finder, "ocr": ocr, "given": True}
    if "prices" in data:
        from aisef2.app.usage import price_problem
        why = price_problem(data["prices"])
        if why:
            raise SettingsError(why)
    if "confinement" in data:
        from aisef2.app.confine import problem
        why = problem(data["confinement"])
        if why:
            raise SettingsError(why)
        if review["finder"] == "ocr":
            raise SettingsError("confinement covers the client's sessions only: Open Code Review (review.finder ocr) "
                                "would call the model unconfined — not both")
    if data["client"] not in CLIENTS:
        raise SettingsError(f"client is one of {CLIENTS}")
    route = data["route"]
    if not isinstance(route, str) or route.count("/") < 1 or not all(route.split("/", 1)):
        raise SettingsError("route is <provider>/<model>, one fixed route")
    p = data["provider"]
    if not isinstance(p, Mapping) or sorted(p) != list(PROVIDER_KEYS) or p["name"] != route.split("/", 1)[0]:
        raise SettingsError(f"provider is {{{', '.join(PROVIDER_KEYS)}}}, its name the route's provider")
    problem = endpoint_problem(p["endpoint"])
    if problem:
        raise SettingsError(problem)
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
    if not isinstance(pre, Mapping) or set(pre) != {"chat_probes"}:
        raise SettingsError("preflight names chat_probes")
    probes = _count(pre["chat_probes"], "preflight.chat_probes", 2)
    if 1 + probes > budget["provider_requests"]:     # the preflight's requests are the budget's too (review ADV-09)
        raise SettingsError(f"the preflight's {1 + probes} requests exceed budget.provider_requests {budget['provider_requests']}")
    return Settings(data["client"], route, p["name"], str(p["endpoint"]).rstrip("/"), p["api_key_env"], p["served_model"],
                    p["listed_owner"], model_limit, tuple(env),
                    budget, _count(data["max_turns_per_session"], "max_turns_per_session"), limits, timeouts, probes,
                    dict(data), review, dict(data["confinement"]) if "confinement" in data else None)


def read(path: str | pathlib.Path) -> Settings:
    """The settings of the file at `path`; a file that cannot be read or is not JSON is refused."""
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise SettingsError(f"{path}: cannot be read ({type(e).__name__}: {e})") from e
    try:
        data = json.loads(text)
    except ValueError as e:
        raise SettingsError(f"{path}: not JSON ({e})") from e
    return load(data)
