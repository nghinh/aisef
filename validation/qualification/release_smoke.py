"""V2.0 release charter S6/§13-§17: V2.0-RELEASE-SMOKE-1 — rehearsed offline on the exact RC wheel, preregistered
once, run exactly once.

    python -P validation/qualification/release_smoke.py --rehearse W                  # -> smoke/REHEARSAL.json
    python -P validation/qualification/release_smoke.py --preregister W --out DIR     # -> smoke/PREREGISTRATION.json + SETTINGS.json
    python -P validation/qualification/release_smoke.py --check [W]                   # everything bound still holds
    python -P validation/qualification/release_smoke.py --run W                       # THE one paid smoke -> smoke/RESULT.json
    python -P validation/qualification/release_smoke.py --evaluate                    # the frozen acceptance on its run

The smoke is the product as shipped: the RC wheel (its digest the frozen RC's) installed into a fresh venv, and that
venv's `aisef run` on the release bundle, the LedgerLock repository at the plan's baseline and the preregistered
settings, into a run directory that does not exist and lies outside any repository. The rehearsal is the same command
with a fake client on PATH and a loopback fake provider. Nothing here retries, repairs, or changes a prompt, the plan,
the budget or the route (§16); `--run` writes smoke/STARTED.json before anything is spent and refuses whenever it
exists — there is no second smoke.

Budget envelope (§15): the flow the rehearsal exercises — a developer session and a review per attempt, at most
DEVELOPER + 1 attempts per story (the retry policy), the preflight's listing and chat probes — gives the structural
maximum of provider requests (one per session), 1 + chat_probes + stories * (DEVELOPER + 1) * 2, and of turns, that
many sessions at the per-session cap; the envelope is that estimate + 25 %, never above the owner's ceilings. Tokens
have no offline estimate (a fake client's are not a model's): their envelope is the ceiling.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import math
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SMOKE_REL = "closure-evidence/v2/release/smoke"
REHEARSAL_REL = f"{SMOKE_REL}/REHEARSAL.json"
PREREG_REL = f"{SMOKE_REL}/PREREGISTRATION.json"
SETTINGS_REL = f"{SMOKE_REL}/SETTINGS.json"
STARTED_REL = f"{SMOKE_REL}/STARTED.json"
RESULT_REL = f"{SMOKE_REL}/RESULT.json"
SCENARIOS = ("reference", "partial", "nothing")
#: charter §15: the owner's hard ceilings and the per-session cap
CEILINGS = {"provider_requests": 60, "turns": 700, "input_tokens": 60_000_000, "output_tokens": 400_000}
MAX_TURNS_PER_SESSION = 80
HEADROOM = 1.25
#: the route, provider identity, retry policy and timeouts attempt 4 ran with (c2_delivery_experiment.EXPERIMENT,
#: c2_p9.PROFILES["delivery-experiment-1"]): the owner-approved route of the V1-aligned profile
ROUTE = "9router/ds/deepseek-v4-pro"
PROVIDER = {"name": "9router", "endpoint": "https://9router.vnteki.com/v1", "api_key_env": None,
            "served_model": "deepseek-v4-pro", "listed_owner": "ds", "model_limit": {"context": 200000, "output": 32768}}
LIMITS = {"DEVELOPER": 2, "PLAN": 0, "ENVIRONMENT": 1, "PROVIDER": 1, "INTEGRATION": 0, "REVIEW": 1, "SECURITY": 1}
TIMEOUTS = {"developer": 2400, "reviewer": 900, "tool": 120, "probe": 60}
CHAT_PROBES = 3
SECRET = ("key", "token", "secret", "password", "auth")


def _sha_file(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _canon(o) -> bytes:
    return json.dumps(o, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load(rel: str) -> dict | None:
    p = ROOT / rel
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _write(rel: str, doc: dict) -> None:
    (ROOT / rel).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / rel).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def envelope(stories: int, limits: dict = LIMITS, chat_probes: int = CHAT_PROBES) -> dict:
    sessions = stories * (limits["DEVELOPER"] + 1) * 2
    estimate = {"provider_requests": 1 + chat_probes + sessions, "turns": sessions * MAX_TURNS_PER_SESSION}
    budget = {k: min(math.ceil(v * HEADROOM), CEILINGS[k]) for k, v in estimate.items()}
    budget.update({k: CEILINGS[k] for k in ("input_tokens", "output_tokens")})
    return {"budget": budget, "estimate": estimate, "headroom": HEADROOM, "ceilings": CEILINGS,
            "rule": "min(ceil(structural estimate * 1.25), ceiling); tokens: the ceiling (no offline estimate)"}


def settings_doc(budget: dict) -> dict:
    from aisef2.app import settings
    return {"format": settings.FORMAT, "client": "opencode", "route": ROUTE, "provider": dict(PROVIDER), "client_env": [],
            "budget": budget, "max_turns_per_session": MAX_TURNS_PER_SESSION, "limits": dict(LIMITS),
            "timeouts_s": dict(TIMEOUTS), "preflight": {"chat_probes": CHAT_PROBES}}


def client_identity(provider: str = PROVIDER["name"], environ=None) -> dict:
    """The client as this machine has it — never executed, no secret recorded: its binary's digest and the digest of
    what in its configuration decides where the route's sessions go."""
    from aisef2.app import client
    environ = os.environ if environ is None else environ
    exe = shutil.which("opencode", path=environ.get("PATH"))
    real = pathlib.Path(exe).resolve() if exe else None
    base = pathlib.Path(environ.get("XDG_CONFIG_HOME") or pathlib.Path(environ.get("HOME", "~")).expanduser() / ".config")
    routing = None
    try:
        prov = (json.loads((base / "opencode" / "opencode.json").read_text(encoding="utf-8")).get("provider") or {})[provider]
        opts = {k: v for k, v in (prov.get("options") or {}).items() if not any(s in k.lower() for s in SECRET)}
        routing = hashlib.sha256(_canon({"npm": prov.get("npm"), "options": opts, "models": sorted(prov.get("models") or {})})).hexdigest()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    endpoint, key = client.configured_provider(provider, environ)
    return {"binary": exe, "resolved": str(real) if real else None, "binary_sha256": _sha_file(real) if real else None,
            "routing_config_sha256": routing, "endpoint": endpoint, "key_present": bool(key)}


def _inside_repository(p: pathlib.Path) -> bool:
    return any((q / ".git").exists() for q in (p, *p.parents))


def _project():
    from aisef2.app import bundle
    from validation.qualification import release_bundle as rb
    return bundle.read(ROOT / rb.BUNDLE_REL)


def _frozen_rc() -> dict:
    from validation.qualification import release_rc as rc
    rec = _load(rc.OUT_REL)
    if rec is None:
        raise SystemExit(f"{rc.OUT_REL} is missing: the smoke runs the frozen RC only")
    return rec


def install(wheel: pathlib.Path, venv: pathlib.Path) -> pathlib.Path:
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True)
    bindir = venv / ("Scripts" if os.name == "nt" else "bin")
    subprocess.run([str(bindir / "python"), "-m", "pip", "install", "--quiet", "--no-index", "--no-deps", str(wheel)],
                   check=True, capture_output=True)
    return bindir / "aisef"


class _FakeProvider(http.server.BaseHTTPRequestHandler):
    def _send(self, doc: dict) -> None:
        body = json.dumps(doc).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):   # noqa: N802
        self._send({"data": [{"id": "fake-model", "owned_by": "rehearsal"}]})

    def do_POST(self):  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._send({"model": "fake-model", "system_fingerprint": "fp-rehearsal", "usage": {"prompt_tokens": 9, "completion_tokens": 1}})

    def log_message(self, *a):
        pass


def rehearse_one(aisef: pathlib.Path, project, scenario: str, t: pathlib.Path, endpoint: str, accepted: dict) -> dict:
    """One scenario through the installed wheel's `aisef run`: release_rehearsal's fake client on PATH, an isolated
    client configuration sending the provider to the loopback fake; then `--verify` and the release acceptance."""
    from validation.qualification import c2_k_nowork_001 as kn
    from validation.qualification import c2_p9
    from validation.qualification import p5_falsifiability as pf
    from validation.qualification import p10 as P10
    from validation.qualification import release_acceptance as A
    from validation.qualification import release_bundle as rb
    from validation.qualification import release_rehearsal as rr
    fake, xdg, out = t / "client", t / "xdg" / "opencode", t / "run"
    fake.mkdir(parents=True)
    xdg.mkdir(parents=True)
    partial = {f.name: f.read_text(encoding="utf-8") for f in sorted((ROOT / kn.MUTANTS / kn.PARTIAL).glob("*.py"))}
    (fake / "rehearsal.json").write_text(json.dumps({
        "scenario": scenario, "reference": pf.reference_modules(), "partial": partial, "test": kn.TEST,
        "repair_test": kn.TEST_REPAIR, "tests": {s: c2_p9.test_path(s) for s in project.stories}}), encoding="utf-8")
    (fake / "opencode").write_text(f"#!{sys.executable}\n" + rr.CLIENT, encoding="utf-8")
    (fake / "opencode").chmod(0o755)
    (xdg / "opencode.json").write_text(json.dumps({"provider": {"rehearsal": {"options": {
        "baseURL": endpoint, "apiKey": "rehearsal-not-a-key"}}}}), encoding="utf-8")
    doc = settings_doc(envelope(len(project.order()))["budget"])
    doc.update(route="rehearsal/fake-model", provider={**PROVIDER, "name": "rehearsal", "endpoint": endpoint,
                                                       "served_model": "fake-model", "listed_owner": "rehearsal"})
    (t / "settings.json").write_text(json.dumps(doc), encoding="utf-8")
    env = {**os.environ, "PATH": f"{fake}{os.pathsep}{os.environ.get('PATH', '')}", "XDG_CONFIG_HOME": str(xdg.parent)}
    bundle_path = str(ROOT / rb.BUNDLE_REL)
    r = subprocess.run([str(aisef), "run", "--project", bundle_path, "--settings", str(t / "settings.json"),
                        "--repo", str(P10.LEDGERLOCK_REPO), "--out", str(out)], capture_output=True, text=True,
                       encoding="utf-8", env=env, cwd=t, timeout=7200)
    v = subprocess.run([str(aisef), "run", "--verify", "--project", bundle_path, "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8", env=env, cwd=t, timeout=1800)
    rec = json.loads((out / "RUN.json").read_text(encoding="utf-8"))
    acc = A.evaluate(project, out, accepted)
    spent = (rec.get("budget") or {}).get("spent") or {}
    return {"exit": r.returncode, "verify_exit": v.returncode, "stderr_tail": r.stderr[-400:],
            "delivery_verdict": rec["delivery_verdict"], "story_outcomes": rec["story_outcomes"],
            "sessions": len(rec["sessions"]), "provider_requests": spent.get("provider_requests"),
            "unaccounted": spent.get("unaccounted"), "budget_stop": rec.get("budget_stop"),
            "release_smoke_pass": acc["RELEASE_SMOKE_PASS"], "acceptance_problems": acc["problems"],
            "false_acceptance": acc["false_acceptance"]}


def rehearsal_problems(results: dict) -> list[str]:
    out = [] if set(results) == set(SCENARIOS) else ["every scenario must be rehearsed"]
    for name in ("reference", "partial"):
        r = results.get(name)
        if r and (r["exit"], r["release_smoke_pass"]) != (0, "YES"):
            out.append(f"{name}: the run must deliver and pass the release acceptance: {r}")
    none = results.get("nothing")
    if none and (none["exit"] == 0 or none["release_smoke_pass"] != "NO" or none["false_acceptance"]):
        out.append(f"nothing: a false acceptance: {none}")
    out += [f"{n}: the run does not verify, or spend is unaccounted" for n, r in results.items() if r["verify_exit"] != 0 or r["unaccounted"]]
    return out


def rehearse(wheel: pathlib.Path, names=SCENARIOS) -> dict:
    from validation.qualification import release_acceptance as A
    project = _project()
    accepted = _load(A.OUT_REL) or A.frozen(project)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeProvider)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="aisef-smoke-rehearsal-") as t:
            t = pathlib.Path(t)
            aisef = install(wheel, t / "venv")
            endpoint = f"http://127.0.0.1:{server.server_address[1]}/v1"
            results = {n: rehearse_one(aisef, project, n, t / n, endpoint, accepted) for n in names}
    finally:
        server.shutdown()
    return {"record": "AISEF V2.0 — OFFLINE REHEARSAL OF RELEASE SMOKE #1 on the RC wheel (fake client, loopback fake "
                      "provider; no model, no network)",
            "wheel": {"name": wheel.name, "sha256": _sha_file(wheel)}, "bundle_digest": project.digest,
            "envelope": envelope(len(project.order())), "results": results, "problems": rehearsal_problems(results)}


def preregister(wheel: pathlib.Path, side: pathlib.Path) -> dict:
    from validation.qualification import common as C
    from validation.qualification import p10 as P10
    from validation.qualification import release_acceptance as A
    from validation.qualification import release_bundle as rb
    from validation.qualification import release_rc as rc
    project, frozen = _project(), _frozen_rc()
    env = envelope(len(project.order()))
    settings = settings_doc(env["budget"])
    side = side.expanduser().resolve()
    rehearsal = _load(REHEARSAL_REL)
    problems = rc.check(frozen)
    if frozen["artifacts"]["sha256"].get(wheel.name) != _sha_file(wheel):
        problems.append(f"{wheel.name} is not the frozen RC's wheel")
    if rehearsal is None or rehearsal["problems"] or rehearsal["wheel"]["sha256"] != _sha_file(wheel):
        problems.append("no passing offline rehearsal of this wheel")
    if not (ROOT / A.OUT_REL).exists():
        problems.append(f"{A.OUT_REL} is not frozen (§13: frozen before the smoke)")
    if side.exists() or _inside_repository(side):
        problems.append(f"{side} exists or lies inside a repository")
    who = client_identity()
    if who["endpoint"] != PROVIDER["endpoint"] or not who["key_present"] or not who["binary_sha256"]:
        problems.append(f"the client is absent, or its configuration does not send {PROVIDER['name']} to {PROVIDER['endpoint']} with a key")
    rec = {
        "record": "AISEF V2.0 — RELEASE SMOKE #1 PREREGISTRATION (charter §15): bound before any provider call",
        "rc": {"sha": frozen["rc"]["sha"], "version": frozen["rc"]["version"], "kernel_digest": frozen["kernel"]["digest"],
               "wheel": {"name": wheel.name, "sha256": _sha_file(wheel)}},
        "plan": {"bundle": rb.BUNDLE_REL, "bundle_digest": project.digest, "plan_hash": project.plan.plan_hash,
                 "stories": project.order(), "obligations": len(project.plan.obligations)},
        "acceptance": {"path": A.OUT_REL, "sha256": C.lf_sha(ROOT / A.OUT_REL) if (ROOT / A.OUT_REL).exists() else None},
        "rehearsal": {"path": REHEARSAL_REL, "sha256": C.lf_sha(ROOT / REHEARSAL_REL) if rehearsal else None},
        "productproof_set": sorted(project.specs), "route": ROUTE, "provider": dict(PROVIDER), "identity_grade": "ATTESTED",
        "prompts": "aisef2/app/feedback.py and aisef2/app/adapters.py of the RC, bound by its kernel digest",
        "client": who, "retry_policy": dict(LIMITS), "envelope": env, "max_turns_per_session": MAX_TURNS_PER_SESSION,
        "timeouts_s": dict(TIMEOUTS),
        "stop_rules": ["the preflight does not attest the route: identity stop, no session",
                       "a budget ceiling reached, or spend that cannot be accounted for: the run ends",
                       "a session at its turn cap ends; its story is judged by its proofs",
                       "no attempt beyond the retry policy; no second smoke; no repair, prompt, plan, budget or route change (§16)"],
        "settings": {"path": SETTINGS_REL, "sha256": hashlib.sha256(_canon(settings)).hexdigest()},
        "repository": {"path": str(P10.LEDGERLOCK_REPO), "baseline": project.plan.baseline},
        "side_directory": str(side), "run_directory": str(side / "run"),
        "preservation": "nothing under the side directory is ever removed: the venv, the inputs, stdout/stderr, the run "
                        "directory (raw journal, RUN.json, the clone with every candidate and merge, session streams, preflight)",
        "command": ["<side>/venv/bin/aisef", "run", "--project", "<side>/inputs/project.json", "--settings",
                    "<side>/inputs/settings.json", "--repo", str(P10.LEDGERLOCK_REPO), "--out", "<side>/run"],
        "problems": problems, "verdict": "PREREGISTERED" if not problems else "PROBLEMS",
    }
    return {"record": rec, "settings": settings}


def check(pre: dict, wheel: pathlib.Path | None = None, started: bool = False) -> list[str]:
    """What the preregistration bound, re-derived here: anything moved refuses the run."""
    from validation.qualification import common as C
    from validation.qualification import release_rc as rc
    project, frozen = _project(), _frozen_rc()
    out = rc.check(frozen)
    if (frozen["rc"]["sha"], frozen["kernel"]["digest"]) != (pre["rc"]["sha"], pre["rc"]["kernel_digest"]):
        out.append("the frozen RC is not the preregistered one")
    if wheel is not None and _sha_file(wheel) != pre["rc"]["wheel"]["sha256"]:
        out.append("the wheel is not the preregistered one")
    if (project.digest, project.plan.plan_hash) != (pre["plan"]["bundle_digest"], pre["plan"]["plan_hash"]):
        out.append("the bundle is not the preregistered one")
    for name in ("acceptance", "rehearsal"):
        p = ROOT / pre[name]["path"]
        if not p.exists() or C.lf_sha(p) != pre[name]["sha256"]:
            out.append(f"{pre[name]['path']} is not the preregistered one")
    settings = _load(SETTINGS_REL)
    if settings is None or hashlib.sha256(_canon(settings)).hexdigest() != pre["settings"]["sha256"]:
        out.append(f"{SETTINGS_REL} is not the preregistered settings")
    if client_identity() != pre["client"]:
        out.append("the client (binary or routing configuration) is not the preregistered one")
    if not started and pathlib.Path(pre["side_directory"]).exists():
        out.append(f"{pre['side_directory']} exists: the smoke's directory is never reused")
    return out + pre["problems"]


def run(wheel: pathlib.Path) -> int:
    """THE one smoke. STARTED.json is written before anything is spent; the run is never repeated."""
    from validation.qualification import p10 as P10
    from validation.qualification import release_bundle as rb
    pre = _load(PREREG_REL)
    if pre is None or pre["verdict"] != "PREREGISTERED":
        raise SystemExit("no preregistration: the smoke does not run")
    if (ROOT / STARTED_REL).exists():
        raise SystemExit(f"{STARTED_REL} exists: the one release smoke has started; there is no second (§16)")
    problems = check(pre, wheel)
    if problems:
        raise SystemExit("the preregistration does not hold: " + "; ".join(problems))
    side = pathlib.Path(pre["side_directory"])
    (side / "inputs").mkdir(parents=True)
    shutil.copyfile(ROOT / rb.BUNDLE_REL, side / "inputs" / "project.json")
    shutil.copyfile(ROOT / SETTINGS_REL, side / "inputs" / "settings.json")
    shutil.copyfile(wheel, side / "inputs" / wheel.name)
    _write(STARTED_REL, {"record": "AISEF V2.0 — RELEASE SMOKE #1 STARTED (written before any provider call; never a second)",
                         "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "preregistration_sha256": _sha_file(ROOT / PREREG_REL),
                         "wheel_sha256": _sha_file(wheel), "side_directory": str(side)})
    aisef = install(side / "inputs" / wheel.name, side / "venv")
    argv = [str(aisef), "run", "--project", str(side / "inputs" / "project.json"), "--settings",
            str(side / "inputs" / "settings.json"), "--repo", str(P10.LEDGERLOCK_REPO), "--out", str(side / "run")]
    t0 = time.time()
    with open(side / "stdout.txt", "wb") as so, open(side / "stderr.txt", "wb") as se:
        code = subprocess.run(argv, stdout=so, stderr=se, cwd=side).returncode
    t1 = time.time()
    v = subprocess.run([str(aisef), "run", "--verify", "--project", str(side / "inputs" / "project.json"), "--out",
                        str(side / "run")], capture_output=True, text=True, encoding="utf-8", cwd=side)
    run_json = side / "run" / "RUN.json"
    _write(RESULT_REL, {"record": "AISEF V2.0 — RELEASE SMOKE #1 RESULT (the run as it ended; evaluated by --evaluate)",
                        "argv": argv, "exit": code, "seconds": round(t1 - t0, 1), "verify_exit": v.returncode,
                        "verify_stdout_tail": v.stdout[-2000:],
                        "run_json_sha256": _sha_file(run_json) if run_json.exists() else None, "side_directory": str(side)})
    return code


def evaluate() -> dict:
    from validation.qualification import release_acceptance as A
    pre, res = _load(PREREG_REL), _load(RESULT_REL)
    if pre is None or res is None:
        raise SystemExit("no smoke to evaluate")
    out = A.evaluate(_project(), pathlib.Path(pre["run_directory"]), _load(A.OUT_REL))
    return {**res, "evaluation": out, "RELEASE_SMOKE_PASS": out["RELEASE_SMOKE_PASS"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--rehearse", type=pathlib.Path, metavar="WHEEL")
    mode.add_argument("--preregister", type=pathlib.Path, metavar="WHEEL")
    mode.add_argument("--check", nargs="?", const="", metavar="WHEEL")
    mode.add_argument("--run", type=pathlib.Path, metavar="WHEEL")
    mode.add_argument("--evaluate", action="store_true")
    ap.add_argument("--out", type=pathlib.Path, help="--preregister: the smoke's side directory (must not exist)")
    ap.add_argument("--print", action="store_true", help="--rehearse: print, do not write the record")
    a = ap.parse_args(argv)
    if a.rehearse:
        rec = rehearse(a.rehearse)
        if not a.print:
            _write(REHEARSAL_REL, rec)
        print(json.dumps(rec, indent=1, sort_keys=True) if a.print else f"{REHEARSAL_REL}: problems {rec['problems']}")
        return 1 if rec["problems"] else 0
    if a.preregister:
        if (ROOT / PREREG_REL).exists():
            raise SystemExit(f"{PREREG_REL} exists: a preregistration is never rewritten")
        if a.out is None:
            ap.error("--preregister needs --out")
        b = preregister(a.preregister, a.out)
        if b["record"]["problems"]:
            print(json.dumps(b["record"]["problems"], indent=1))
            return 1
        _write(SETTINGS_REL, b["settings"])
        _write(PREREG_REL, b["record"])
        print(f"wrote {PREREG_REL} and {SETTINGS_REL}")
        return 0
    if a.check is not None:
        pre = _load(PREREG_REL)
        problems = ["no preregistration"] if pre is None else check(pre, pathlib.Path(a.check) if a.check else None,
                                                                      started=(ROOT / STARTED_REL).exists())
        print("release smoke preregistration: " + ("PASS" if not problems else "FAIL " + "; ".join(problems)))
        return 1 if problems else 0
    if a.run:
        return run(a.run)
    rec = evaluate()
    _write(RESULT_REL, rec)
    print(f"{RESULT_REL}: RELEASE_SMOKE_PASS={rec['RELEASE_SMOKE_PASS']} {rec['evaluation']['problems']}")
    return 0 if rec["RELEASE_SMOKE_PASS"] == "YES" else 1


if __name__ == "__main__":
    sys.exit(main())
