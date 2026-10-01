"""C2-P10 / WP-2.10.2 — the evidence record of model / profile freezing (RFC §23, §24, §28 rule 5).

Attestation is qualified against the local fixture provider (tests/v2/fixtures/provider/fixture_provider.py, an HTTP stub
on 127.0.0.1) and nothing else: no real provider is called and nothing is spent. The record holds, re-derived by
`--check` (the stub is deterministic):

    classifications   each fixture route class measured by `preflight` and classified (ATTESTED: the fixed model;
                      OPAQUE: the combo, the silent alias, the per-call aggregate, the unlisted and the unmeasured
                      route); the repository's configured development profile (OpenCode, 9router/mycombo) by role,
                      from its committed configuration and from the router facts recorded on 2026-09-18
    per_run           the ATTESTED fingerprint per run: a repeated preflight attests, a deployment change is DRIFT, an
                      alias is OPAQUE
    profiles          the content-addressed execution profiles and whether each bars sealing; the OPAQUE one is put to
                      the cohort machinery on a synthetic in-memory preregistration and refused
    observed_at_write the route the operator's ~/.config/opencode/opencode.json names, read from its `model` field
                      only, when present at --write; --check re-classifies the recorded route and does not re-read it

    python -P validation/qualification/c2_p10_profile.py --write
    python -P validation/qualification/c2_p10_profile.py --check
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import sys
from dataclasses import asdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.cohort import lifecycle as L  # noqa: E402
from aisef2.cohort.preregistration import CohortRefused  # noqa: E402
from tests.v2 import test_c2_p10_cohort as T  # noqa: E402  — the synthetic preregistration of the kill tests

OUT_REL = "closure-evidence/v2/cycle2/P10-PROFILE-FREEZE.json"
BASE = {"commit": "9bd16fa9c578bb91a0a6c0047d2ceb6e6ab3b414", "aisef2_tree": "37bf6457f350dd720a2214f04f3896c554ad0904"}
SOURCES = ("validation/v2/profile_freeze.py", "tests/v2/fixtures/provider/fixture_provider.py",
           "tests/v2/fixtures/provider/opencode.json", "tests/v2/fixtures/known_bad/profile_freeze.json",
           "tests/v2/test_c2_p10_profile_freeze.py", "validation/qualification/c2_p10_profile.py",
           "closure-evidence/hardening/w1/profiles/PROFILE-W1-OC-MYCOMBO-T40.json",
           "closure-evidence/hardening/w1/profiles/ROUTE-RESOLUTION-2026-09-18.json")
HOME_CONFIG = pathlib.Path.home() / ".config" / "opencode" / "opencode.json"
CLIENT = "aisef-preflight (validation/v2/profile_freeze.py)"
FIXTURE_ROUTES = (("FIX-FIXED", "fixture-model-1"), ("FIX-COMBO", "fixture-combo"), ("FIX-ALIAS", "fixture-alias"),
                  ("FIX-ROTATING", "fixture-rotating"), ("FIX-UNLISTED", "fixture-unlisted"))
VERDICT = "attestation qualified"


def _load(name: str, path: pathlib.Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pf = _load("aisef_v2_profile_freeze", ROOT / "validation" / "v2" / "profile_freeze.py")
fp = _load("aisef_v2_fixture_provider", ROOT / "tests" / "v2" / "fixtures" / "provider" / "fixture_provider.py")


def _sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def fixture_route(model: str):
    return pf.Route(client=CLIENT, provider="fixture", endpoint="fixture-provider (127.0.0.1 stub)", model=model)


def _entry(id_: str, source: str, route, measured, name: str = "model") -> dict:
    cap, why = pf.classify(route, measured, name)
    return {"id": id_, "source": source, "route": asdict(route), "measurement": measured, "grade": cap.grade.value,
            "reasons": why, "capability": cap.resolved()}


def _refusal(fn, *args) -> str:
    try:
        fn(*args)
    except (pf.AttestationRefused, CohortRefused) as e:
        return f"REFUSED {e}"
    return "ATTESTED"


def _sealing(rec: dict) -> str:
    try:
        L.seal(rec)
    except CohortRefused as e:
        return f"REFUSED {e}"
    return "not barred by the profile"


def build() -> dict:
    with fp.FixtureProvider() as fx:
        measured = {i: pf.preflight(fx.base_url, fixture_route(m)) for i, m in FIXTURE_ROUTES}
        again = pf.preflight(fx.base_url, fixture_route("fixture-model-1"))
        stub_requests = list(fx.requests)
    with fp.FixtureProvider(deployment="fp_fixture_1b") as fx:
        drifted = pf.preflight(fx.base_url, fixture_route("fixture-model-1"))
        stub_requests += fx.requests
    entries = [_entry(i, "fixture provider, measured", fixture_route(m), measured[i]) for i, m in FIXTURE_ROUTES]
    entries.append(_entry("FIX-UNMEASURED", "fixture route, configuration only (no preflight)",
                          fixture_route("fixture-model-1"), None))
    recorded = pf.recorded_measurement(ROOT)
    dev_caps = []
    for role, route in pf.configured_routes(ROOT).items():
        entries.append(_entry(f"DEV-{role.upper()}", f"configured development profile ({pf.DEV_PROFILE_REL}), "
                              "configuration only: no live preflight", route, None, f"model.{role}"))
        entries.append(_entry(f"DEV-{role.upper()}-RECORDED", "the same route against the router facts recorded on "
                              f"2026-09-18 ({pf.ROUTE_RESOLUTION_REL}); recorded, not re-measured", route, recorded,
                              f"model.{role}"))
        dev_caps.append(pf.classify(route, None, f"model.{role}")[0])
    fixed, _ = pf.classify(fixture_route("fixture-model-1"), measured["FIX-FIXED"])
    alias = fixture_route("fixture-alias")
    per_run = {
        "repeat_preflight_same_deployment": _refusal(pf.attest_run, fixed, fixture_route("fixture-model-1"), again),
        "deployment_changed": _refusal(pf.attest_run, fixed, fixture_route("fixture-model-1"), drifted),
        "alias_route": _refusal(pf.attest_run, fixed, alias, measured["FIX-ALIAS"]),
    }
    profiles = []
    for id_, caps, settings in (("PROFILE-FIXTURE-FIXED", [fixed], {}),
                                ("PROFILE-DEV-MYCOMBO", dev_caps,
                                 {"client_version": {"value": "1.18.31", "layer": "profile"}})):
        profile = pf.freeze_profile(caps, settings, BASE["commit"])
        rec = {**T.prereg(1), "execution_profile": profile,
               "model_route": {"capability": caps[0].name, "route": caps[0].tuple_["route"]}}
        profiles.append({"id": id_, "profile": profile, "profile_id": profile["runspec_hash"],
                         "aggregate_min_grade": profile["aggregate_min_grade"], "bars_sealing": pf.bars_sealing(profile),
                         "synthetic_seal": _sealing(rec)})
    return {
        "record": "AISEF V2 — CYCLE-2 C2-P10 / WP-2.10.2 MODEL / PROFILE FREEZE",
        "package": "WP-2.10.2", "phase": "C2-P10",
        "authority": "owner ruling 2026-09-30: explicit authorization of the C2-P10 scope (WP-2.10.1, WP-2.10.2); "
                     "machinery only — no cohort, no workload selected, no live provider",
        "base": BASE, "sources": {rel: _sha(rel) for rel in SOURCES},
        "measured_live": "nothing: no call to any real provider was made and nothing was spent",
        "live_provider_calls": 0,
        "measured_on_fixture": f"{len(stub_requests)} requests, every one to the fixture provider on 127.0.0.1 "
                               "(paths " + ", ".join(sorted({p for p, _ in stub_requests})) + ")",
        "rules": {"preflight_calls": pf.PREFLIGHT_CALLS, "loopback_only": list(pf.LOOPBACK),
                  "alias_owners": list(pf.ALIAS_OWNERS), "reasons": list(pf.REASONS),
                  "enforcement": pf.ENFORCEMENT.value, "weakest_path": pf.WEAKEST_PATH,
                  "opaque_binds": "only what the configuration names; never a model inferred from what an alias "
                                  "served",
                  "fingerprint": "sha256 of the canonical preflight facts (listing entry, one call's served model, "
                                 "deployment and finish reason): a drift detector, not proof of weights"},
        "what_was_measured": {
            "real_provider_live": [],
            "fixture_stub_live": [c["id"] for c in entries if c["source"] == "fixture provider, measured"]
                                 + [f"per_run.{k}" for k in per_run],
            "configuration_only_not_measured": [c["id"] for c in entries if "configuration only" in c["source"]],
            "recorded_2026_09_18_not_re_measured": [c["id"] for c in entries if c["id"].endswith("-RECORDED")]},
        "classifications": entries, "per_run": per_run, "profiles": profiles,
        "verdict": VERDICT,
    }


def observed_at_write() -> dict:
    if not HOME_CONFIG.is_file():
        return {"source": "~/.config/opencode/opencode.json", "present": False}
    route = pf.opencode_route(HOME_CONFIG)       # the `model` field only, in memory
    cap, why = pf.classify(route, None)
    developer = pf.configured_routes(ROOT)["developer"]
    return {"source": "~/.config/opencode/opencode.json — the `model` field only, read in memory; no key, endpoint "
                      "or option was read out, copied or recorded", "present": True, "route": asdict(route),
            "grade": cap.grade.value, "reasons": why, "same_route_as_committed_profile": route == developer}


def problems_of(rec: dict) -> list[str]:
    out = pf.record_problems(rec)
    grades = {c["id"]: c["grade"] for c in rec["classifications"]}
    want = {"FIX-FIXED": "ATTESTED", **{i: "OPAQUE" for i, _ in FIXTURE_ROUTES[1:]}, "FIX-UNMEASURED": "OPAQUE"}
    out += [f"{i} is {grades.get(i)}, not {g}" for i, g in want.items() if grades.get(i) != g]
    out += [f"{i} is {g}: the configured development profile is OPAQUE" for i, g in grades.items()
            if i.startswith("DEV-") and g != "OPAQUE"]
    run = rec["per_run"]
    if run["repeat_preflight_same_deployment"] != "ATTESTED" or not run["deployment_changed"].startswith(
            "REFUSED DRIFT") or not run["alias_route"].startswith("REFUSED OPAQUE"):
        out.append(f"per-run attestation does not hold: {run}")
    bars = {p["id"]: (p["bars_sealing"], p["synthetic_seal"].split(":")[0]) for p in rec["profiles"]}
    if bars != {"PROFILE-FIXTURE-FIXED": (False, "not barred by the profile"),
                "PROFILE-DEV-MYCOMBO": (True, "REFUSED OPAQUE_PROFILE")}:
        out.append(f"the sealing bar does not hold: {bars}")
    seen = rec.get("observed_at_write", {})
    if seen.get("present") and pf.classify(pf.Route(**seen["route"]), None)[0].grade.value != "OPAQUE":
        out.append("the configured route observed at write is not OPAQUE")
    return out


def render(rec: dict) -> str:
    return json.dumps(rec, indent=1, ensure_ascii=False) + "\n"


def check() -> list[str]:
    path = ROOT / OUT_REL
    if not path.exists():
        return [f"{OUT_REL} is missing"]
    committed = json.loads(path.read_text(encoding="utf-8"))
    rec = {**build(), "observed_at_write": committed.get("observed_at_write")}
    out = problems_of(rec)
    if render(committed) != render(rec):
        out.append(f"{OUT_REL} does not re-derive from the tree")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--write" in argv:
        rec = {**build(), "observed_at_write": observed_at_write()}
        problems = problems_of(rec)
        if not problems:
            (ROOT / OUT_REL).write_text(render(rec), encoding="utf-8")
            print(f"wrote {OUT_REL}: {rec['verdict']}")
    else:
        problems = check()
    for p in problems:
        print(f"FAIL  {p}")
    print(f"c2_p10_profile: {'FAIL' if problems else 'PASS'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
