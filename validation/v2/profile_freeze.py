"""C2-P10 / WP-2.10.2 — model / profile freeze for sealed evaluation (RFC §23, §24, §27 Q6 preconditions, §28 rule 5).

* `preflight` — the fixed-model preflight measurement on one exact route of an OpenAI-compatible endpoint: the
  provider's listing entry for the declared model (`GET /v1/models`: id, owned_by) and `PREFLIGHT_CALLS` minimal
  completions of it (`POST /v1/chat/completions`, temperature 0, one token), each reduced to what identifies the answerer:
  the served model id, the deployment identity when exposed (`system_fingerprint`), the finish reason — never content,
  never usage. **Loopback only**: any other host is refused before a socket opens (no real provider is called, nothing
  is spent; a live Q6 preflight needs its own authorization). No proxy is used.
* `classify` — alias detection, fail closed. A route is ATTESTED only when every rule holds: it was measured
  (`UNMEASURED` — a configuration names a route, it never proves one; `UNDER_MEASURED`), the provider lists the
  declared model (`NOT_LISTED`) and not as an alias (`LISTED_AS_ALIAS`), every call was served by the declared model
  (`SERVED_OTHER_MODEL` — a route that resolves to another id), and every call identically (`UNSTABLE` — a per-call
  aggregate route). Otherwise the route is OPAQUE. An OPAQUE identity binds only what the configuration names
  (provider, endpoint identity, declared model, route, client) — never a model inferred from what an alias served.
  ATTESTED binds RFC §23's minimum through aisef2.runtime.capability.attested: provider; endpoint identity; declared
  model; fixed route; client; deployment when exposed; and the locally measured preflight fingerprint — a drift
  detector, not proof of weights.
* `attest_run` — the ATTESTED fingerprint per run: a run's own preflight must classify ATTESTED with the frozen identity;
  an alias refuses OPAQUE, a changed fingerprint refuses DRIFT.
* `freeze_profile` — the content-addressed execution profile (runspec.resolve -> aisef2.cohort execution_profile): its
  id is its runspec_hash, its aggregate grade is computed; `bars_sealing` is the predicate the cohort's own constructor
  applies (aggregate OPAQUE).
* `opencode_route` — the route an OpenCode configuration names, read from its `model` field alone; keys, endpoints and
  options are never read out. `configured_routes` — the repository's configured development profile, from its committed
  identity (PROFILE-W1-OC-MYCOMBO-T40: client and per-role routes) and the router listing recorded on 2026-09-18.

Q0 checker (`check`): the configured development profile classifies OPAQUE on every role and binds no served model;
the committed record (closure-evidence/v2/cycle2/P10-PROFILE-FREEZE.json) re-classifies from its own measurements
(`record_problems`), so a recorded alias labelled ATTESTED fails.

    python -P validation/v2/profile_freeze.py --check
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import Enforcement, IdentityGrade  # noqa: E402
from aisef2.cohort import preregistration as P  # noqa: E402
from aisef2.product.contract import canonical  # noqa: E402
from aisef2.runtime.capability import CapabilityIdentity, attested, opaque  # noqa: E402
from aisef2.runtime.runspec import q6_eligible, resolve  # noqa: E402

RECORD_REL = "closure-evidence/v2/cycle2/P10-PROFILE-FREEZE.json"
DEV_PROFILE_REL = "closure-evidence/hardening/w1/profiles/PROFILE-W1-OC-MYCOMBO-T40.json"
ROUTE_RESOLUTION_REL = "closure-evidence/hardening/w1/profiles/ROUTE-RESOLUTION-2026-09-18.json"
PREFLIGHT_CALLS = 3
LOOPBACK = ("127.0.0.1", "localhost", "::1")
# ponytail: the one alias marker measured on this repository's router (owned_by "combo", 2026-09-18); an alias marked
# otherwise is still caught by SERVED_OTHER_MODEL or UNSTABLE, and a new marker is added here when one is measured.
ALIAS_OWNERS = ("combo",)
#: §24, named: what attestation cannot see
WEAKEST_PATH = ("a provider that switches the model behind a fixed id between two preflights and reports the declared "
                "id and deployment: the fingerprint detects drift at the next preflight, never between them")
ENFORCEMENT = Enforcement.PARTIAL    # the route is checked at each preflight, not on every call (WEAKEST_PATH)
REASONS = ("UNMEASURED", "UNDER_MEASURED", "NOT_LISTED", "LISTED_AS_ALIAS", "SERVED_OTHER_MODEL", "UNSTABLE")


class PreflightRefused(ValueError):
    """A preflight that may not run: a non-loopback endpoint, or a provider answer that is not a measurement."""


class AttestationRefused(ValueError):
    def __init__(self, code: str, why: str) -> None:
        super().__init__(f"{code}: {why}")
        self.code = code


@dataclass(frozen=True)
class Route:
    """What a configuration names: the client, the provider and its endpoint identity, the declared model id."""
    client: str
    provider: str
    endpoint: str
    model: str

    @property
    def route(self) -> str:
        return f"{self.provider}/{self.model}"


# --------------------------------------------------------------------------------------- measurement

def _json(opener, url: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def preflight(base_url: str, route: Route, calls: int = PREFLIGHT_CALLS) -> dict:
    """The preflight measurement of `route` at `base_url` (an execution locator, never identity). Loopback only."""
    host = urllib.parse.urlsplit(base_url).hostname
    if host not in LOOPBACK:
        raise PreflightRefused(f"LIVE_PROVIDER_REFUSED: {host!r} is not a loopback host — no real provider is called "
                               "under WP-2.10.2")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        listing = _json(opener, f"{base_url}/v1/models")["data"]
        entry = next(({"id": m["id"], "owned_by": m.get("owned_by")} for m in listing if m.get("id") == route.model),
                     None)
        answers = [_json(opener, f"{base_url}/v1/chat/completions",
                         {"model": route.model, "messages": [{"role": "user", "content": "preflight"}],
                          "max_tokens": 1, "temperature": 0}) for _ in range(calls)]
        return {"listing": entry, "calls": [{"served_model": a.get("model"), "deployment": a.get("system_fingerprint"),
                                             "finish_reason": a["choices"][0].get("finish_reason")} for a in answers]}
    except (OSError, KeyError, IndexError, TypeError, ValueError) as e:
        if isinstance(e, urllib.error.HTTPError):
            e.close()                       # an HTTP error holds its response open
        raise PreflightRefused(f"the provider's answer is not a measurement: {e!r}") from None


def classify(route: Route, measured: dict | None, name: str = "model") -> tuple[CapabilityIdentity, list[str]]:
    """The capability `name` of `route` given its preflight measurement (None: none was measured), and why it is
    not ATTESTED ([] when it is)."""
    calls = (measured or {}).get("calls") or []
    listing = (measured or {}).get("listing")
    why = []
    if measured is None:
        why.append("UNMEASURED")
    elif len(calls) < PREFLIGHT_CALLS:
        why.append("UNDER_MEASURED")
    if measured is not None and not listing:
        why.append("NOT_LISTED")
    if listing and listing.get("owned_by") in ALIAS_OWNERS:
        why.append("LISTED_AS_ALIAS")
    if any(c.get("served_model") != route.model for c in calls):
        why.append("SERVED_OTHER_MODEL")
    if any(c != calls[0] for c in calls):
        why.append("UNSTABLE")
    if why:
        return opaque(name, ENFORCEMENT, client=route.client, provider=route.provider, endpoint=route.endpoint,
                      declared_model=route.model, route=route.route), why
    return attested(name, provider=route.provider, endpoint=route.endpoint, declared_model=route.model,
                    route=route.route, client=route.client, preflight={"listing": listing, "served": calls[0]},
                    enforcement=ENFORCEMENT, deployment=calls[0].get("deployment")), []


def attest_run(frozen: CapabilityIdentity, route: Route, measured: dict | None) -> CapabilityIdentity:
    """A run's ATTESTED fingerprint: its own preflight must re-classify ATTESTED and equal the frozen identity."""
    now, why = classify(route, measured, frozen.name)
    if why:
        raise AttestationRefused("OPAQUE", f"{route.route}: {', '.join(why)}")
    if now.identity != frozen.identity:
        raise AttestationRefused("DRIFT", f"{route.route}: fingerprint {now.tuple_['fingerprint'][:12]} is not the "
                                          f"frozen {frozen.tuple_.get('fingerprint', '')[:12]}")
    return now


def freeze_profile(capabilities, settings: dict, revision: str) -> dict:
    """The content-addressed execution profile (its id is its runspec_hash)."""
    return P.execution_profile(resolve(capabilities, settings, revision))


def bars_sealing(profile: dict) -> bool:
    """The cohort constructor's own predicate: an OPAQUE aggregate grade never seals (RFC §28 rule 5)."""
    return not q6_eligible(P.runspec_of(profile))


# --------------------------------------------------------------------------------------- configured routes

def opencode_route(config_path: pathlib.Path) -> Route:
    """The route an OpenCode configuration names: its `model` field ("provider/model") and nothing else."""
    model = json.loads(pathlib.Path(config_path).read_text(encoding="utf-8"))["model"]
    provider, _, name = model.partition("/")
    return Route(client="opencode", provider=provider, endpoint=provider, model=name)


def configured_routes(root: pathlib.Path = ROOT) -> dict[str, Route]:
    """The repository's configured development profile, by role, from its committed identity."""
    identity = json.loads((root / DEV_PROFILE_REL).read_text(encoding="utf-8"))["identity"]
    out = {}
    for role, model in sorted(identity["routes"].items()):
        provider, _, name = model.partition("/")
        out[role] = Route(client=identity["client"], provider=provider, endpoint=provider, model=name)
    return out


def recorded_measurement(root: pathlib.Path = ROOT) -> dict:
    """The router facts recorded on 2026-09-18 for mycombo (its listing owner and the model each probe answered with),
    as a measurement — recorded, never re-measured here."""
    rr = json.loads((root / ROUTE_RESOLUTION_REL).read_text(encoding="utf-8"))
    calls = [{"served_model": p["answered_by"], "deployment": None, "finish_reason": None}
             for p in rr["probes"]["probe1"] if p.get("requested") == "mycombo" and "answered_by" in p]
    return {"listing": {"id": "mycombo", "owned_by": rr["mycombo"]["owned_by"]}, "calls": calls}


# --------------------------------------------------------------------------------------- the checker

def _binds_inferred(cap: dict, measured: dict | None, declared: str) -> list[str]:
    """The binding values that name a model the route served other than the one it declares."""
    served = {c.get("served_model") for c in (measured or {}).get("calls") or []} - {declared}
    return sorted(v for v in cap["binding"].values() if v in served)


def record_problems(record: dict) -> list[str]:
    """Every classification of the record re-derives from its own measurement; every profile from its content."""
    out = []
    for c in record.get("classifications", []):
        route = Route(**c["route"])
        cap, why = classify(route, c["measurement"], c["capability"]["name"])
        if (c["grade"], c["reasons"]) != (cap.grade.value, why):
            out.append(f"{c['id']}: recorded {c['grade']} {c['reasons']}, the measurement classifies "
                       f"{cap.grade.value} {why}")
        elif c["capability"] != cap.resolved():
            out.append(f"{c['id']}: the recorded capability is not the one its measurement derives")
        inferred = _binds_inferred(c["capability"], c["measurement"], route.model)
        if c["grade"] == IdentityGrade.OPAQUE.value and inferred:
            out.append(f"{c['id']}: an OPAQUE identity binds a model inferred from an alias: {inferred}")
        if c["grade"] == IdentityGrade.ATTESTED.value and c["capability"]["binding"].get("fingerprint") != \
                hashlib.sha256(canonical({"listing": c["measurement"]["listing"],
                                          "served": c["measurement"]["calls"][0]}).encode("utf-8")).hexdigest():
            out.append(f"{c['id']}: the fingerprint is not the sha256 of the recorded preflight")
    for p in record.get("profiles", []):
        spec = P.runspec_of(p["profile"])
        if (p["profile_id"], p["aggregate_min_grade"], p["bars_sealing"]) != (
                spec.runspec_hash, spec.aggregate_min_grade.value, not q6_eligible(spec)):
            out.append(f"{p['id']}: the profile's id, aggregate grade or sealing bar is not what its content derives")
    return out


def configured_problems(root: pathlib.Path = ROOT) -> list[str]:
    out = []
    for role, route in configured_routes(root).items():
        for source, measured in (("configuration", None), ("recorded router facts", recorded_measurement(root))):
            cap, why = classify(route, measured)
            if cap.grade is not IdentityGrade.OPAQUE:
                out.append(f"configured {role} route {route.route} ({source}) classifies {cap.grade.value}")
            if _binds_inferred(cap.resolved(), measured, route.model):
                out.append(f"configured {role} route {route.route} binds an inferred model")
    return out


def check(root: pathlib.Path = ROOT) -> list[str]:
    path = root / RECORD_REL
    if not path.exists():
        return configured_problems(root) + [f"{RECORD_REL} is missing"]
    return configured_problems(root) + record_problems(json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    problems = check(ROOT)
    for p in problems:
        print(f"FAIL  {p}")
    print(f"profile freeze: {'FAIL' if problems else 'PASS'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
