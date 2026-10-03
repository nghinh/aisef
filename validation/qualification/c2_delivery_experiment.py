"""DELIVERY EXPERIMENT 1 — the preregistration and the execution guard of ONE LedgerLock delivery run on the corrected
kernel and the corrected plan (owner rulings 'FINAL PLAN CORRECTION + DELIVERY RUN PREREGISTRATION' and 'DELIVERY
EXPERIMENT EXECUTION GUARD', 2026-10-02). PREPARED, NOT EXECUTED: the run needs a separate owner authorization.

    python -P validation/qualification/c2_delivery_experiment.py --write   # the preregistration record; measures readiness; no provider call
    python -P validation/qualification/c2_delivery_experiment.py --check   # the committed record is what this tree and this machine derive
    python -P validation/qualification/c2_delivery_experiment.py --check --after-run   # the same once the run's result is preserved
    python -P validation/qualification/c2_delivery_experiment.py --attest  # PART OF THE PAID RUN: the provider preflight (calls the provider)
    python -P validation/qualification/c2_delivery_experiment.py --check-historical   # every attempt already run, against its own records

**An attempt that has run is historical** (`HISTORICAL`): its preregistration, attestation, journal and records are
immutable evidence, verified against what they themselves state — the commit that froze them, the commit the run
executed on, the content digests the preregistration bound — never against the sources HEAD holds, and never re-derived.

**The sequence of the paid run**, each step a refusal when it fails: the preregistration is re-derived on this tree and
machine -> the provider preflight (`attest`) -> the ATTESTED identity tuple is built from what it observed -> the tuple
and its fingerprint are verified -> the resolved RunSpec is frozen -> only then does `c2_p9.run` unlock delivery
(`require_unlocked`, called by the runner itself — the run script is not the enforcement boundary).

**The preflight** makes at most five provider requests, each written to a ledger before it is sent and after it
answers: the router's model listing, three chat probes, and — only when the listing and every probe showed the one
expected model — one bounded OpenCode smoke session. It is part of the experiment's budget. It is written once: an
attempt that holds a preflight, passed or failed, is never preflighted again.

**The identity** is the kernel's own ATTESTED grade (RFC §23; aisef2/runtime/capability.py), nothing new: provider,
endpoint, declared model, route, client (its version, binary digest and the digest of its routing configuration),
deployment only when the provider exposes one (else NOT_EXPOSED: none is made up), and the fingerprint of the observable preflight fields. The fingerprint is
a drift detector, not a claim about model weights. A provider that does not show one stable declared model is not
attested: MODEL_IDENTITY_CANNOT_BE_ATTESTED, and delivery stays locked.

**The budget** (c2_p9.Budget) is the owner's four hard ceilings, re-derived from the ledger, the journal and the
session streams; it keeps no count of its own, and what cannot be accounted for ends the experiment.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import c2_p9  # noqa: E402
from validation.qualification import c2_plan_correction as pc  # noqa: E402

C, P10 = c2_p9.C, c2_p9.P10
#: the CURRENT attempt's preregistration — attempt 4's, as amended before any run; attempt 3's is historical evidence
#: (HISTORICAL) and never rewritten
OUT_REL = "closure-evidence/v2/cycle2/DELIVERY-EXPERIMENT-1-ATTEMPT-4-PREREGISTRATION-AMENDED.json"
#: a preregistration that never ran and was replaced before any provider call: kept byte for byte, never current again
SUPERSEDED_BEFORE_RUN = {"closure-evidence/v2/cycle2/DELIVERY-EXPERIMENT-1-ATTEMPT-4-PREREGISTRATION.json": {
    "sha256": "49c6880da481abf0bf54db6d1d48ed1d80b33407dcc7b0946b78da5473aa0e6d", "reason": "OWNER_OUTPUT_BUDGET_AMENDMENT",
    "ruling": "'AISEF V2 — OWNER AUTHORIZATION: DELIVERY EXPERIMENT ATTEMPT 4 / ONE PAID ATTEMPT ONLY' §1"}}
AUTHORITY = ("owner rulings 'AISEF V2 — FINAL PLAN CORRECTION + DELIVERY RUN PREREGISTRATION / NO PROVIDER CALL', 'AISEF V2 — "
             "DELIVERY EXPERIMENT EXECUTION GUARD / DETERMINISTIC ONLY / NO DELIVERY RUN YET' and 'AISEF V2 — SINGLE PAID DELIVERY "
             "EXPERIMENT / FINAL OWNER AUTHORIZATION WITH HARD COST BOUND' (2026-10-02) for the experiment's design and budget; attempt 3 "
             "ran once under 'FINAL REBIND + SINGLE PAID DELIVERY EXPERIMENT' and is final; attempt 4 was prepared under 'ATTEMPT-3 "
             "HISTORICALIZATION + H-PROMPT-002 + H-RETRY-001' (2026-10-03) §F, its held preregistration 49c6880d… SUPERSEDED_BEFORE_RUN "
             "(OWNER_OUTPUT_BUDGET_AMENDMENT), and exactly ONE run of this amended preregistration is authorized by 'AISEF V2 — OWNER "
             "AUTHORIZATION: DELIVERY EXPERIMENT ATTEMPT 4 / ONE PAID ATTEMPT ONLY' (2026-10-03): no attempt 5")
W1 = "closure-evidence/hardening/w1"
ORACLE_REL = f"{W1}/oracle/test_oracle.py"
ORACLE_INDEPENDENCE_REL = f"{W1}/ORACLE-INDEPENDENCE.json"
ORACLE_REFERENCE_REL = f"{W1}/oracle/reference"
ORACLE_CALIBRATE_REL = f"{W1}/oracle/calibrate.py"
V1_FREEZE_REL = "closure-evidence/hardening/P19-FREEZE.json"
V1_PREFLIGHT_REL = f"{W1}/provider_preflight.py"
#: QP-2.9 attempt 2 and the V1 runs on the same route: what the budget is compared with (never what it is derived from)
MEASURED_REL = "closure-evidence/v2/cycle2/P10/attempt-2/LEDGERLOCK-REGRESSION.json"
#: Why the experiment may not start, or None: while a reason stands, neither the preflight nor the runner starts, and only
#: the owner's ruling clears it. The K-NOWORK-001 hold stood from 6d5a062 to 5c7c5a6; 'FINAL REBIND' cleared it at 06ceb23
#: for exactly attempt 3, which then ran once and is final. Attempt 4 was held from f8e535c until the owner's ruling
#: 'OWNER AUTHORIZATION: DELIVERY EXPERIMENT ATTEMPT 4 / ONE PAID ATTEMPT ONLY' authorized exactly one run of it, with
#: the amended budget below; nothing else of the experiment changed.
HOLD = None
EXPERIMENT = {
    "id": c2_p9.EXPERIMENT,
    "attempt": 4,                                       # the next attempt directory of closure-evidence/v2/cycle2/P10
    "kernel_commit": "4f6dfc197acfd9146357e5781326843bc09982e5",    # K-NOWORK-001 (on K-PRESAT-001, d427299): unchanged since attempt 3
    "kernel_tree": "c2717d2ed98b76bd3d284a37c47103b5dc2bd020",
    "harness_includes": "dd79f46e8636637f595e288081bffe555f2d35d8",   # H-RETRY-001, on H-PROMPT-002 and the historical verifier
    # the route of the V1 baseline profile PROFILE-W1V2.1-OC-DEEPSEEKV4PRO-T80-RO (same plan base, max_retries 2)
    "provider": "9router", "endpoint": "https://9router.vnteki.com/v1",
    "route": "9router/ds/deepseek-v4-pro", "route_kind": "FIXED_MODEL", "resolved_model": "deepseek-v4-pro",
    "listing_owner": "ds",                              # the upstream the router's listing must name for the route (never "combo")
    "model_limit": {"context": 200000, "output": 32768},
    # THE OWNER'S HARD BUDGET ('SINGLE PAID DELIVERY EXPERIMENT / FINAL OWNER AUTHORIZATION' §B; the output ceiling amended
    # from 400 000 to 700 000 by 'OWNER AUTHORIZATION: DELIVERY EXPERIMENT ATTEMPT 4' §1): over the whole experiment,
    # preflight included — a bounded V1-aligned envelope (V1 on this route: 600-668 turns, 50-58M input)
    "budget": {"provider_requests": 60, "turns": 700, "input_tokens": 60_000_000, "output_tokens": 700_000},
    "max_turns_per_session": 80,                        # §C: a developer or reviewer session; the smoke session has its own cap
    "preflight_shape": {"listing": 1, "chat_probes": 3, "chat_probe_max_tokens": 16, "smokes": 1, "smoke_max_turns": 10,
                        "smoke_timeout_s": 300.0},
    "attestation_max_age_s": 3600,
}
HARNESS_FILES = ("validation/qualification/c2_p9.py", "validation/qualification/c2_p9_run.sh",
                 "validation/qualification/c2_delivery_experiment.py", "validation/qualification/c2_plan_correction.py")
ATTESTATION = "ATTESTATION.json"
PREFLIGHT_DIR = "preflight"
LEDGER = "LEDGER.jsonl"
CANNOT = "MODEL_IDENTITY_CANNOT_BE_ATTESTED"
SMOKE_PROMPT = ("Use your tools: create a file named probe.txt whose entire content is the word ready, then run `cat probe.txt` "
                "in the shell and tell me what it printed.")           # the V1 preflight's tool smoke, word for word
#: fields of the router's listing row that would be declared limits, bound into the fingerprint when exposed
LIMIT_FIELDS = ("context_length", "context_window", "max_tokens", "max_output_tokens", "max_completion_tokens")
SECRET_KEY = re.compile(r"key|token|secret|authorization|password", re.I)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def attempt_path() -> pathlib.Path:
    return ROOT / c2_p9.attempt_dir(EXPERIMENT["attempt"])


# ------------------------------------------------------------------------------------- the client and its identity

def client_config() -> dict:
    """The client configuration laid over the operator's own for every session of the experiment: the model AND the
    small model are the one fixed route (nothing can fall to a routing alias), and the route's model is declared."""
    provider, model = EXPERIMENT["route"].split("/", 1)
    return {"model": EXPERIMENT["route"], "small_model": EXPERIMENT["route"],
            "provider": {provider: {"models": {model: {"name": model, "limit": EXPERIMENT["model_limit"]}}}}}


def client_env() -> dict:
    return {**os.environ, "OPENCODE_CONFIG_CONTENT": json.dumps(client_config(), sort_keys=True)}


def client_resolution() -> dict:
    """What the client resolves under `client_env`, read from `opencode debug config` — local, no request is made. Only
    the two model fields and the declaration are taken from its output (which holds the operator's key): nothing else
    of it is kept, printed or recorded."""
    exe = shutil.which("opencode")
    if not exe:
        return {"client_present": False}
    with tempfile.TemporaryDirectory(prefix="aisef2-dx-client-") as d:
        out = subprocess.run([exe, "debug", "config"], capture_output=True, encoding="utf-8", errors="replace", env=client_env(), cwd=d,
                             timeout=120).stdout
    top = {k: (m.group(1) if (m := re.search(rf'^  "{k}": "([^"]*)"', out, re.M)) else None) for k in ("model", "small_model")}
    return {"client_present": True, **top, "route_model_declared": f'"{EXPERIMENT["route"].split("/", 1)[1]}"' in out,
            "resolves_to_the_fixed_route": top["model"] == top["small_model"] == EXPERIMENT["route"]}


def machine() -> dict:
    """The client as this machine has it: OpenCode's binary and version, and — from the operator's configuration, without
    any secret — the route's provider endpoint and the digest of everything in it that decides routing."""
    oc = P10.opencode_identity()
    cfg = pathlib.Path(os.environ.get("XDG_CONFIG_HOME") or (pathlib.Path.home() / ".config")) / "opencode" / "opencode.json"
    endpoint = digest = None
    try:
        prov = (json.loads(cfg.read_text(encoding="utf-8")).get("provider") or {}).get(EXPERIMENT["provider"]) or {}
        opts = {k: v for k, v in (prov.get("options") or {}).items() if not SECRET_KEY.search(k)}
        endpoint = str(opts.get("baseURL") or opts.get("baseUrl") or "").rstrip("/") or None
        digest = _sha(_canon({"overlay": client_config(), "npm": prov.get("npm"), "options": opts, "models": sorted(prov.get("models") or {})}))
    except (OSError, ValueError):
        pass
    return {**oc, "endpoint": endpoint, "routing_config_digest": digest}


def allowed_identity(oc: dict) -> dict:
    """The model identity the preflight is ALLOWED to find — every field of the kernel's ATTESTED binding except the
    fingerprint it measures. The client is one string: who it is, its version, its binary and its routing configuration."""
    return {"provider": EXPERIMENT["provider"], "endpoint": EXPERIMENT["endpoint"], "declared_model": EXPERIMENT["resolved_model"],
            "route": EXPERIMENT["route"],
            "client": f"opencode {oc.get('version')} binary-sha256:{oc.get('binary_sha256')} routing-config-sha256:{oc.get('routing_config_digest')}"}


#: the frozen requirements, in this repository: the prompts are derived from them (byte-identical to LedgerLock's at its
#: plan commit — P10.REQUIREMENTS_SHA256 — or nothing is preregistered)
REQUIREMENTS_REL = "tests/v2/fixtures/workloads/ledgerlock-reference/REQUIREMENTS.md"


def harness_identity() -> dict:
    """What the developer is given, by content: the seven prompts (H-PROMPT-002) and the code that builds them and the
    retry feedback (H-RETRY-001), c2_p9.py. The RunSpec binds it, so another prompt or feedback is another RunSpec."""
    req = (ROOT / REQUIREMENTS_REL).read_bytes()
    if _sha(req) != P10.REQUIREMENTS_SHA256:
        raise SystemExit(f"{REQUIREMENTS_REL} is not the frozen requirements")
    tasks, _, _ = c2_p9.prompts(pc.corrected_plan(), req.decode("utf-8"))
    prompts = {s: _sha(t.encode("utf-8")) for s, t in sorted(tasks.items())}
    return {"c2_p9_sha256": C.lf_sha(ROOT / "validation/qualification/c2_p9.py"), "prompts_sha256": prompts,
            "prompt_set_sha256": _sha(_canon(prompts)), "prompt_rule": "H-PROMPT-002", "retry_feedback": "H-RETRY-001"}


def fixed(oc: dict) -> dict:
    """What the RunSpec binds of the experiment (c2_p9.runspec_inputs)."""
    return {**EXPERIMENT, "experiment": EXPERIMENT["id"], "identity": allowed_identity(oc), "harness": harness_identity(),
            "developer_timeout_s": c2_p9.DEV_TIMEOUT_S, "reviewer_timeout_s": c2_p9.REVIEW_TIMEOUT_S}


def runspec(oc: dict, preflight: dict | None = None, deployment: str | None = None):
    """The experiment's RunSpec: the TEMPLATE (no preflight: the model is OPAQUE) or the RESOLVED one (the model
    ATTESTED with the fingerprint of `preflight` — and the deployment, when the provider exposed one — and the
    template's hash among its settings)."""
    from aisef2.runtime.runspec import resolve
    plan = pc.corrected_plan()
    caps, layers, _ = c2_p9.runspec_inputs(plan, c2_p9.EXPERIMENT, oc, {**fixed(oc), "deployment": deployment}, preflight)
    return resolve(caps, layers, plan.baseline)


def enforcement_identity(spec) -> dict:
    by = {c.name: c.enforcement.value for c in spec.capabilities}
    return {"by_capability": by, "probe_execution_env": "PARTIAL", "sha256": _sha(_canon({"by_capability": by, "probe_execution_env": "PARTIAL"}))}


# ----------------------------------------------------------------------------- the preflight: ledger and accounting

def ledger_append(pre: pathlib.Path, entry: dict) -> None:
    """One line, on disk before the caller goes on: a request is in the ledger before it is sent."""
    with (pre / LEDGER).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def ledger_rows(pre: pathlib.Path) -> list[dict]:
    path = pre / LEDGER
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []


def preflight_accounting(pre: pathlib.Path, kinds: tuple[str, ...] = ("listing", "chat", "smoke")) -> dict:
    """What the preflight spent, from its ledger and its smoke streams — the one explicit accounting record folded into
    the experiment's total before delivery is unlocked. A request that was sent and has no result, a chat probe
    without its usage, a smoke that finished no step or a step without tokens: unaccounted."""
    rows = ledger_rows(pre)
    sent = {r["n"]: r for r in rows if r["event"] == "sent" and r["kind"] in kinds}
    done = {r["n"]: r for r in rows if r["event"] == "done"}
    out = {"provider_requests": len(sent), "turns": 0, "input_tokens": 0, "output_tokens": 0, "unaccounted": []}
    for n, s in sorted(sent.items()):
        d = done.get(n)
        if d is None:
            out["unaccounted"].append(f"request {n} ({s['kind']}) was sent and has no result")
        elif s["kind"] == "chat":
            u = d.get("usage")
            if isinstance(u, dict) and all(isinstance(u.get(k), int) for k in ("prompt_tokens", "completion_tokens")):
                out["input_tokens"] += u["prompt_tokens"]
                out["output_tokens"] += u["completion_tokens"]
            else:
                out["unaccounted"].append(f"request {n} (chat) reports no usage")
        elif s["kind"] == "smoke":
            log = pre / c2_p9.SESSIONS / s["log"]
            x = c2_p9.read_session(log) if log.exists() else {"turns": 0, "tokens": {"input": 0, "output": 0}, "steps_without_tokens": 0}
            out["turns"] += x["turns"]
            out["input_tokens"] += x["tokens"]["input"]
            out["output_tokens"] += x["tokens"]["output"]
            if not x["turns"] or x["steps_without_tokens"]:
                out["unaccounted"].append(f"request {n} (smoke) finished {x['turns']} steps, {x['steps_without_tokens']} without tokens")
    return out


# --------------------------------------------------------------------------------- the preflight: what it observes

OK_SMOKE = {"exit": 0, "file_written": True, "shell_tool_called": True, "errors": 0}


def identity_problems(obs: dict, complete: bool = True) -> list[str]:
    """Why the listing and the chat probes do not show the one stable declared identity the experiment preregistered.
    `complete` False judges the probes made so far (the preflight stops at the first that is wrong)."""
    out, listing, probes, want = [], obs.get("listing") or {}, obs.get("probes") or [], EXPERIMENT["preflight_shape"]["chat_probes"]
    if obs.get("route") != EXPERIMENT["route"]:
        out.append(f"route {obs.get('route')}: not the fixed route {EXPERIMENT['route']}")
    if listing.get("http") != 200 or not listing.get("listed"):
        out.append("the router does not list the route's model")
    elif listing.get("owned_by") != EXPERIMENT["listing_owner"]:
        out.append(f"the router names the upstream {listing.get('owned_by')!r}, not {EXPERIMENT['listing_owner']!r} (a combo is a routing alias)")
    models = sorted({str(p.get("model")) for p in probes})
    if any(p.get("http") != 200 for p in probes):
        out.append(f"a chat probe answered HTTP {sorted({p.get('http') for p in probes if p.get('http') != 200})}")
    elif any(not p.get("model") for p in probes) or len(models) > 1:
        out.append(f"the provider shows no one stable declared model: {models}")
    elif probes and models != [EXPERIMENT["resolved_model"]]:
        out.append(f"answered by {models[0]}, not {EXPERIMENT['resolved_model']}")
    if complete and len(probes) != want and not out:
        out.append(f"{len(probes)} of {want} chat probes were made")
    return out


def observation_problems(obs: dict) -> list[str]:
    """Why what the preflight observed does not unlock delivery: the identity, then the smoke probe's tool calling."""
    out, smokes, want = identity_problems(obs), obs.get("smokes") or [], EXPERIMENT["preflight_shape"]["smokes"]
    if not out:
        if len(smokes) != want:
            out.append(f"{len(smokes)} of {want} smoke probes ran")
        out += [f"smoke {i + 1}: tool calling did not behave ({ {k: s.get(k) for k in (*OK_SMOKE, 'stopped', 'timed_out')} })"
                for i, s in enumerate(smokes)
                if {k: s.get(k) for k in OK_SMOKE} != OK_SMOKE or s.get("stopped") or s.get("timed_out")]
    return out


NOT_EXPOSED = "NOT_EXPOSED"


def deployment_identity(obs: dict) -> str:
    """The provider's deployment identity AS EXPOSED: the `system_fingerprint` of its responses when every probe carries
    one and it is the same one. When no probe carries any: NOT_EXPOSED. When it is exposed but not one stable value, no
    deployment is bound either (the values stay in the fingerprint): none is ever made up."""
    values = [p.get("system_fingerprint") for p in obs.get("probes") or []]
    if values and all(isinstance(v, str) and v for v in values) and len(set(values)) == 1:
        return f"system_fingerprint:{values[0]}"
    return NOT_EXPOSED if not any(values) else f"EXPOSED_NOT_STABLE:{len({str(v) for v in values})}_values"


def bound_deployment(obs: dict) -> str | None:
    d = deployment_identity(obs)
    return d if d.startswith("system_fingerprint:") else None


def fingerprint_fields(obs: dict) -> dict:
    """The observable preflight fields the fingerprint binds, canonically — stable ones only (no time, no token count,
    no request id), so the same provider behaviour gives the same fingerprint on another day."""
    listing, probes = obs.get("listing") or {}, obs.get("probes") or []
    return {"route": obs.get("route"),
            "listing": {k: listing.get(k) for k in ("id", "object", "owned_by")}, "declared_limits_exposed": listing.get("limits") or {},
            "declared_models": sorted({str(p.get("model")) for p in probes}),
            "response": {"object": sorted({str(p.get("object")) for p in probes}),
                         "system_fingerprint": sorted({str(p.get("system_fingerprint")) for p in probes}),
                         "usage_fields": sorted({k for p in probes for k in (p.get("usage") or {})})},
            "limits_declared_to_the_client": EXPERIMENT["model_limit"],
            "tool_calling": [{k: s.get(k) for k in OK_SMOKE} for s in obs.get("smokes") or []]}


def _v1_preflight():
    """The V1 provider preflight module, for its two proven primitives only: reading the operator's endpoint and key
    (the key is never printed or recorded) and one HTTP request without a retry."""
    spec = importlib.util.spec_from_file_location("aisef_w1_provider_preflight", ROOT / V1_PREFLIGHT_REL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def default_transport():
    v1 = _v1_preflight()
    base, key = v1._provider(EXPERIMENT["provider"])
    if base != EXPERIMENT["endpoint"]:
        raise SystemExit(f"REFUSED: the operator's endpoint for {EXPERIMENT['provider']} is not the preregistered one")
    return lambda path, body=None: v1._get(base + path, key, body)


def run_smoke(pre: pathlib.Path, i: int, budget) -> dict:
    """The preregistered smoke probe: one OpenCode session on the fixed route under the fixed client overlay, in an
    empty repository, bounded by its own turn cap and timeout and by the experiment's budget."""
    shape = EXPERIMENT["preflight_shape"]
    log = pre / c2_p9.SESSIONS / f"smoke.{i}.jsonl"
    with tempfile.TemporaryDirectory(prefix="aisef2-dx-smoke-") as d:
        subprocess.run(["git", "init", "-q"], cwd=d, check=True, capture_output=True)
        s = c2_p9.opencode_session(f"preflight smoke {i}", SMOKE_PROMPT, d, log, shape["smoke_timeout_s"], model=EXPERIMENT["route"],
                                   env=client_env(), budget=budget, turn_cap=shape["smoke_max_turns"])
        probe = pathlib.Path(d) / "probe.txt"
        written = probe.is_file() and probe.read_text(encoding="utf-8", errors="replace").strip() == "ready"
    tools, errors = [], 0
    if log.exists():
        text, _ = c2_p9.redact(log.read_text(encoding="utf-8", errors="replace"), c2_p9.known_secrets())
        log.write_text(text, encoding="utf-8")
        for line in text.splitlines():
            try:
                ev = json.loads(line) if line.startswith("{") else {}
            except ValueError:
                continue
            if ev.get("type") in ("tool_use", "tool"):
                tools.append((ev.get("part") or {}).get("tool"))
            errors += ev.get("type") == "error"
    return {"exit": s["exit"], "stopped": s["stopped"], "timed_out": s["timed_out"], "started": s["started"], "file_written": written,
            "shell_tool_called": "bash" in tools, "errors": errors, "turns": s["turns"]}


def attest(attempt: pathlib.Path, *, oc: dict | None = None, prereg: dict | None = None, transport=None, smoke=run_smoke,
           now=time.time) -> dict:
    """PART OF THE PAID RUN — this calls the provider. The preflight, and the attestation record it leaves in
    `attempt` whatever it finds. Written once: an attempt that already holds a preflight is refused before any request."""
    if on_hold():
        raise SystemExit(f"REFUSED: delivery is locked — {on_hold()}")
    pre = attempt / PREFLIGHT_DIR
    if pre.exists() or (attempt / ATTESTATION).exists():
        raise SystemExit(f"REFUSED: {attempt.name} already holds a preflight — it is made once, and its requests are in the budget")
    oc, prereg = oc or machine(), prereg or committed()
    shape, model = EXPERIMENT["preflight_shape"], EXPERIMENT["route"].split("/", 1)[1]
    transport = transport or default_transport()        # reads the operator's key; makes no request
    (pre / c2_p9.SESSIONS).mkdir(parents=True)
    obs, n, problems = {"route": EXPERIMENT["route"], "listing": {}, "probes": [], "smokes": []}, 0, []
    try:
        n += 1
        ledger_append(pre, {"n": n, "event": "sent", "kind": "listing"})
        code, body = transport("/models")
        row = next((x for x in (body.get("data") or [] if isinstance(body, dict) else []) if x.get("id") == model), {})
        ledger_append(pre, {"n": n, "event": "done", "http": code})
        obs["listing"] = {"http": code, "listed": bool(row), **{k: row.get(k) for k in ("id", "object", "owned_by")},
                          "limits": {k: row[k] for k in LIMIT_FIELDS if k in row}}
        for _ in range(shape["chat_probes"]):
            if identity_problems(obs, complete=False) or preflight_accounting(pre)["unaccounted"]:
                break       # the listing or a probe is not the expected identity, or a request cannot be accounted for: nothing more is sent
            n += 1
            ledger_append(pre, {"n": n, "event": "sent", "kind": "chat"})
            code, body = transport("/chat/completions", {"model": model, "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
                                                         "max_tokens": shape["chat_probe_max_tokens"], "stream": False})
            body = body if isinstance(body, dict) else {}
            ledger_append(pre, {"n": n, "event": "done", "http": code, "usage": body.get("usage")})
            obs["probes"].append({"http": code, "model": body.get("model"), "object": body.get("object"),
                                  "system_fingerprint": body.get("system_fingerprint"), "usage": body.get("usage")})
        held = not identity_problems(obs) and not preflight_accounting(pre)["unaccounted"]
        for i in range(1, shape["smokes"] + 1 if held else 1):      # the smoke runs only once the identity held, every request accounted
            n += 1
            name = f"smoke.{i}.jsonl"
            ledger_append(pre, {"n": n, "event": "sent", "kind": "smoke", "log": name})
            budget = c2_p9.Budget(EXPERIMENT["budget"], preflight_accounting(pre, ("listing", "chat")), pre / c2_p9.SESSIONS,
                                  lambda: sum(1 for r in ledger_rows(pre) if r["event"] == "sent" and r["kind"] == "smoke"))
            result = smoke(pre, i, budget)
            ledger_append(pre, {"n": n, "event": "done", **{k: result.get(k) for k in ("exit", "stopped", "timed_out", "turns")}})
            obs["smokes"].append(result)
    except Exception as e:  # noqa: BLE001 — whatever broke, the record of what was sent is written
        problems.append(f"the preflight broke: {type(e).__name__}: {e}"[:500])
    accounting = preflight_accounting(pre)
    problems += observation_problems(obs) + [f"unaccounted: {u}" for u in accounting["unaccounted"]]
    rec = attestation_record(obs, accounting, problems, oc, prereg, now(), _sha((pre / LEDGER).read_bytes()))
    (attempt / ATTESTATION).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return rec


def attestation_record(obs: dict, accounting: dict, problems: list[str], oc: dict, prereg: dict, at: float, ledger_sha: str) -> dict:
    """The attestation: bound to the preregistration, the plan, the kernel, the route, the model, the client, the
    enforcement identity and the experiment — and, when nothing is wrong, carrying the ATTESTED capabilities and the
    resolved RunSpec hash. With a problem the model stays OPAQUE and delivery stays locked."""
    fields = fingerprint_fields(obs)
    template = runspec(oc)
    rec = {"deployment_identity": deployment_identity(obs),
           "record": "AISEF V2 — DELIVERY EXPERIMENT 1: MODEL IDENTITY ATTESTATION (the provider preflight; it unlocks delivery or refuses it)",
           "experiment": {"id": EXPERIMENT["id"], "attempt": EXPERIMENT["attempt"]}, "at": at,
           "at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at)),
           "preregistration": {"path": OUT_REL, "sha256": _sha(_canon(prereg))},
           "runspec_template_hash": template.runspec_hash, "plan_hash": pc.corrected_plan().plan_hash,
           "kernel": {"commit": EXPERIMENT["kernel_commit"], "tree": EXPERIMENT["kernel_tree"]},
           "route": EXPERIMENT["route"], "expected_resolved_model": EXPERIMENT["resolved_model"], "client": allowed_identity(oc)["client"],
           "enforcement_identity": enforcement_identity(template)["sha256"],
           "observation": obs, "fingerprint_fields": fields,
           "ledger": {"path": f"{PREFLIGHT_DIR}/{LEDGER}", "sha256": ledger_sha}, "accounting": accounting,
           "problems": problems, "identity_grade": "OPAQUE", "capabilities": {}, "resolved_runspec_hash": None,
           "fingerprint_note": "a drift detector over the observable preflight fields — not a claim about model weights"}
    if problems:
        # the provider showed something other than the one stable expected identity — or the preflight could not finish
        rec["verdict"] = CANNOT if identity_problems(obs, complete=False) else "REFUSED"
        return rec
    resolved = runspec(oc, fields, bound_deployment(obs))
    models = {c.name: c for c in resolved.capabilities if c.name in ("developer", "reviewer")}
    rec.update(verdict="ATTESTED", identity_grade="ATTESTED" if all(c.grade.value == "ATTESTED" for c in models.values()) else "OPAQUE",
               aggregate_min_grade=resolved.aggregate_min_grade.value,
               capabilities={k: c.resolved() for k, c in models.items()}, resolved_runspec_hash=resolved.runspec_hash)
    return rec


def on_hold() -> str | None:
    """What the preflight and the runner ask before anything else."""
    return HOLD


def gate_problems(attempt: pathlib.Path, prereg: dict, oc: dict, now: float) -> list[str]:
    """Why delivery stays locked: everything the attestation record must be, re-derived — never taken from the record
    itself. No provider is called."""
    path, pre = attempt / ATTESTATION, attempt / PREFLIGHT_DIR
    if not path.exists():
        return [f"no attestation record at {path.name}: the provider preflight has not unlocked delivery"]
    att = json.loads(path.read_text(encoding="utf-8"))
    out = []
    if att.get("verdict") != "ATTESTED" or att.get("problems"):
        out.append(f"the attestation's verdict is {att.get('verdict')}: {att.get('problems')}")
    if att.get("experiment") != {"id": EXPERIMENT["id"], "attempt": EXPERIMENT["attempt"]}:
        out.append(f"the attestation is of {att.get('experiment')}, not of this experiment and attempt")
    if (att.get("preregistration") or {}).get("sha256") != _sha(_canon(prereg)):
        out.append("the attestation is bound to another preregistration")
    age = now - float(att.get("at") or 0)
    if not 0 <= age <= EXPERIMENT["attestation_max_age_s"]:
        out.append(f"the attestation is stale: made {age:.0f} s before this run (at most {EXPERIMENT['attestation_max_age_s']} s)")
    obs = att.get("observation") or {}
    out += [f"observed: {p}" for p in observation_problems(obs)]
    if att.get("fingerprint_fields") != fingerprint_fields(obs):
        out.append("the fingerprinted fields are not what the observation shows")
    # what the record must carry, built here from the preregistered identity and the observation
    template, resolved = runspec(oc), runspec(oc, fingerprint_fields(obs), bound_deployment(obs))
    if att.get("deployment_identity") != deployment_identity(obs):
        out.append("the deployment identity recorded is not what the observation exposes")
    want = {c.name: c.resolved() for c in resolved.capabilities if c.name in ("developer", "reviewer")}
    for name, cap in want.items():
        got = (att.get("capabilities") or {}).get(name) or {}
        if got.get("grade") != "ATTESTED":
            out.append(f"{name} is {got.get('grade', 'absent')}, not ATTESTED")
        elif got != cap:
            differs = sorted(k for k in set(cap["binding"]) | set(got.get("binding") or {}) if cap["binding"].get(k) != (got.get("binding") or {}).get(k))
            out.append(f"{name}'s attested tuple is not the one this preregistration and observation give: {differs or 'identity'}")
    if att.get("identity_grade") != "ATTESTED":
        out.append(f"the model identity grade is {att.get('identity_grade')}, not ATTESTED")
    if att.get("runspec_template_hash") != template.runspec_hash or template.runspec_hash != prereg.get("runspec_template_hash"):
        out.append("the RunSpec template is not the preregistered one")
    if att.get("resolved_runspec_hash") != resolved.runspec_hash:
        out.append("the resolved RunSpec hash is not the one the attested tuple gives")
    if att.get("plan_hash") != pc.corrected_plan().plan_hash or att.get("kernel") != {"commit": EXPERIMENT["kernel_commit"], "tree": EXPERIMENT["kernel_tree"]}:
        out.append("the attestation is bound to another plan or kernel")
    if att.get("route") != EXPERIMENT["route"] or att.get("expected_resolved_model") != EXPERIMENT["resolved_model"] \
            or att.get("client") != allowed_identity(oc)["client"]:
        out.append("the attestation is bound to another route, model or client")
    if att.get("enforcement_identity") != enforcement_identity(template)["sha256"]:
        out.append("the attestation is bound to another enforcement identity")
    accounting = preflight_accounting(pre)
    ledger = pre / LEDGER
    if accounting["unaccounted"] or accounting != att.get("accounting") or not ledger.exists() \
            or _sha(ledger.read_bytes()) != (att.get("ledger") or {}).get("sha256"):
        out.append(f"the preflight's requests are not accounted for by its ledger: {accounting['unaccounted'] or 'the record and the ledger differ'}")
    return out


def committed() -> dict:
    return json.loads((ROOT / OUT_REL).read_text(encoding="utf-8"))


def require_unlocked(attempt: pathlib.Path) -> dict:
    """What a run of the experiment executes with — or a refusal, before any provider call: the preregistration holds
    on this tree and machine, and the attempt holds a verified attestation."""
    if on_hold():
        raise SystemExit(f"REFUSED: delivery is locked — {on_hold()}")
    found = check()
    oc = machine()
    found = found or gate_problems(attempt, committed(), oc, time.time())
    if found:
        raise SystemExit("REFUSED: delivery is locked — " + "; ".join(found))
    att = json.loads((attempt / ATTESTATION).read_text(encoding="utf-8"))
    prereg = committed()
    return {**fixed(oc), "deployment": bound_deployment(att["observation"]), "plan": pc.corrected_plan(), "authority": AUTHORITY,
            "preflight_fields": att["fingerprint_fields"],
            "preflight_accounting": att["accounting"], "resolved_runspec_hash": att["resolved_runspec_hash"],
            "preregistration": {"path": OUT_REL, "sha256": C.lf_sha(ROOT / OUT_REL)}, "plan_correction": prereg["plan"]["correction"],
            "attestation": {"path": f"{c2_p9.attempt_dir(EXPERIMENT['attempt'])}/{ATTESTATION}", "sha256": _sha((attempt / ATTESTATION).read_bytes()),
                            "at_utc": att["at_utc"], "fingerprint": att["capabilities"]["developer"]["binding"]["fingerprint"],
                            "runspec_template_hash": att["runspec_template_hash"]}}


# -------------------------------------------------------------------------------- the final evaluation of a result

def materialise(git_dir: pathlib.Path, sha: str, dest: pathlib.Path) -> pathlib.Path:
    """The tree of `sha` from the preserved git directory, as plain files under `dest` (the copy is only read)."""
    data = subprocess.run(["git", "--git-dir", str(git_dir), "archive", "--format=tar", sha], capture_output=True, check=True).stdout
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(dest, filter="data")
    return dest


def final_proof(tree: pathlib.Path, sha: str) -> dict:
    """Every one of the 59 ProductProofSpecs (compiled under the persisted real approvals) put to its own probe on
    `tree` — whatever story owned it, whatever the run's journal says."""
    from aisef2.arch.enums import ContractSatisfaction, Enforcement, ProbeExecutionStatus
    from aisef2.probe import catalog
    from aisef2.probe.protocol import ExecutionEnv, RevisionRef, bound_result, run_probe
    from aisef2.product.outcome import contract_satisfaction
    env, at, rows = ExecutionEnv(sys.executable, 60, Enforcement.PARTIAL), RevisionRef(sha, str(tree.resolve())), []
    for sid, spec in c2_p9._compiled().items():
        probe = next(e for e in catalog.CATALOG if e.probe_id == spec.probe_id).factory()
        result = bound_result(run_probe(probe, spec, at, env), spec=spec, revision=at.sha, enforcement=probe.enforcement())
        executed = result.status is ProbeExecutionStatus.EXECUTED
        rows.append({"spec": sid, "product_proof_spec_id": spec.id, "semantic_hash": spec.semantic_hash, "probe_id": spec.probe_id,
                     "status": result.status.value, "verdict": result.behavior_verdict.value if executed else None,
                     "candidate_expectation": spec.candidate_expectation.value,
                     "satisfaction": contract_satisfaction(result, spec).value if executed else None,
                     "detail": None if executed else str(getattr(result, "detail", ""))[:300]})
    return {"revision": sha, "total": len(rows), "satisfied": sum(1 for r in rows if r["satisfaction"] == ContractSatisfaction.SATISFIED.value),
            "not_satisfied": [r["spec"] for r in rows if r["satisfaction"] != ContractSatisfaction.SATISFIED.value], "specs": rows}


def oracle_identity() -> dict:
    pinned = json.loads((ROOT / ORACLE_INDEPENDENCE_REL).read_text(encoding="utf-8"))
    v1 = {p["name"]: p["version"] for p in json.loads((ROOT / V1_FREEZE_REL).read_text(encoding="utf-8"))["oracle_venv"]["packages"]}

    def version(name: str) -> str | None:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return None
    now = C.lf_sha(ROOT / ORACLE_REL)
    here = {"python": platform.python_version(), "pytest": version("pytest"), "coverage": version("coverage")}
    return {"path": ORACLE_REL, "sha256": now, "sha256_pinned": pinned["oracle"]["sha256"], "unchanged_since_calibration": now == pinned["oracle"]["sha256"],
            "independence_verdict": pinned["verdict"], "interpreter": here, "v1_oracle_venv": v1,
            "runtime_difference": "none" if all(here.get(k) == v for k, v in v1.items()) else
                                  "; ".join(f"{k} {here.get(k)} vs {v}" for k, v in sorted(v1.items()) if here.get(k) != v),
            "interpreter_note": "the oracle venv of the V1 freeze is no longer on this machine; the oracle runs under the harness "
                                "interpreter, whose versions are recorded here and whose equivalence is the calibration below"}


def parse_oracle(stdout: str) -> dict:
    """Per-test outcomes of `pytest -v`, reconciled against pytest's own totals (the V1 driver's rule, SS-79): a parse
    that does not account for every test pytest counted is incomplete, never quietly believed."""
    res = {m.group(1).split("::", 1)[1]: m.group(2)
           for m in re.finditer(r"^(\S+::\S+?)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b", stdout, re.M)}
    tail = stdout.strip().splitlines()[-1] if stdout.strip() else ""
    counted = sum(int(n) for n, _ in re.findall(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed)", tail))
    return {"results": res, "total": len(res), "passed": sum(1 for v in res.values() if v == "PASSED"),
            "not_passed": sorted(k for k, v in res.items() if v != "PASSED"), "complete": bool(res) and counted == len(res)}


def v1_oracle(tree: pathlib.Path, out_dir: pathlib.Path | None = None) -> dict:
    """The V1 independent acceptance oracle, unchanged, on `tree` — the V1 driver's own invocation."""
    with tempfile.TemporaryDirectory(prefix="aisef2-dx-oracle-") as d:
        obs = pathlib.Path(d) / "observations.jsonl"
        env = {**os.environ, "AISEF_W1_PROJECT": str(tree), "AISEF_W1_ORACLE_OBSERVATIONS": str(obs), "PYTHONDONTWRITEBYTECODE": "1"}
        r = subprocess.run([sys.executable, "-m", "pytest", str(ROOT / ORACLE_REL), "-v", "-rA", "-p", "no:cacheprovider", "--tb=short"],
                           capture_output=True, encoding="utf-8", errors="replace", env=env, cwd=d, timeout=1800)
        observations = obs.read_text(encoding="utf-8").splitlines() if obs.exists() else []
    if out_dir is not None:
        (out_dir / "V1-ORACLE-OUTPUT.txt").write_text(r.stdout + "\n--- stderr ---\n" + r.stderr, encoding="utf-8")
    return {**oracle_identity(), "exit": r.returncode, **parse_oracle(r.stdout), "observations": [json.loads(x) for x in observations]}


def evaluate(git_dir: pathlib.Path, final: str, out_dir: pathlib.Path, delivery_verdict: str) -> dict:
    """The final main of a finished run, from its preserved git directory: all 59 specs, then the V1 oracle. A delivery
    PASS is confirmed only when the run's own verdict is PASS AND the product requirements hold on the final main."""
    with tempfile.TemporaryDirectory(prefix="aisef2-dx-final-") as d:
        proof = final_proof(materialise(git_dir, final, pathlib.Path(d) / "proof"), final)
        oracle = v1_oracle(materialise(git_dir, final, pathlib.Path(d) / "oracle"), out_dir)
    return {"record": "AISEF V2 — DELIVERY EXPERIMENT 1: the final main evaluated independently of the run's journal",
            "final_main": final, "preserved_git_dir": str(git_dir), "v2_final_proof": proof, "v1_oracle": oracle,
            "delivery_verdict": delivery_verdict, "delivery_pass_confirmed": confirmed(delivery_verdict, proof, oracle), "at": C.now()}


def confirmed(delivery_verdict: str, proof: dict, oracle: dict) -> bool:
    """A delivery PASS stands only with the product: the run's verdict is PASS, the final main satisfies all 59 specs,
    and the oracle's every check passed (and every check it ran is accounted for)."""
    return delivery_verdict == "PASS" and proof["total"] == 59 and proof["satisfied"] == 59 \
        and bool(oracle["complete"]) and oracle["total"] > 0 and oracle["passed"] == oracle["total"]


def oracle_mutants() -> dict:
    """The oracle's own calibration under THIS interpreter: its ten existing one-line mutants of its reference
    implementation (closure-evidence/hardening/w1/oracle/calibrate.py — read, never run as a script, nothing of V1
    written), each of which must turn its target test red."""
    spec = importlib.util.spec_from_file_location("aisef_w1_oracle_calibrate", ROOT / ORACLE_CALIBRATE_REL)
    cal = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cal)
    rows = {}
    with tempfile.TemporaryDirectory(prefix="aisef2-dx-mutants-") as d:
        for mid, target, patch, removes in cal.MUTANTS:
            res = v1_oracle(cal.fixture(pathlib.Path(d), mid, patch))["results"]
            rows[mid] = {"removes": removes, "target": target, "target_outcome": res.get(target), "killed": res.get(target) in ("FAILED", "ERROR"),
                         "also_red": sorted(k for k, v in res.items() if v != "PASSED" and k != target)}
    return {"total": len(rows), "killed": sum(r["killed"] for r in rows.values()), "survived": sorted(k for k, r in rows.items() if not r["killed"]),
            "mutants": rows}


def readiness() -> dict:
    """Measured, without a provider and without LedgerLock: both evaluations run end to end on a reference
    implementation written from the requirements — the P5 reference fixture for the 59 specs, the oracle's own
    calibration reference for the oracle — and the oracle's ten calibration mutants under this interpreter. It shows
    the evaluations can run and discriminate here; it says nothing about a delivery."""
    from aisef2.probe.calibration import FIXTURE_REVISION
    from validation.qualification import p5_falsifiability as pf
    with tempfile.TemporaryDirectory(prefix="aisef2-dx-ready-") as d:
        proof = final_proof(pf.build_tree(None, pathlib.Path(d)), FIXTURE_REVISION)
        oracle = v1_oracle(pathlib.Path(shutil.copytree(ROOT / ORACLE_REFERENCE_REL, pathlib.Path(d) / "oracle-reference")))
    return {"v2_final_proof_on_the_p5_reference_fixture": {k: proof[k] for k in ("total", "satisfied", "not_satisfied")},
            "v1_oracle_on_its_calibration_reference": {k: oracle[k] for k in ("exit", "total", "passed", "not_passed", "complete", "interpreter")},
            "v1_oracle_calibration_mutants": oracle_mutants()}


# ------------------------------------------------------------------------------------------- the preregistration

def _is_ancestor(commit: str) -> bool:
    return subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "HEAD"], capture_output=True).returncode == 0


def _tree_of(commit: str) -> str | None:
    """The kernel tree of `commit`, or None where this checkout does not hold it (a shallow clone): then nothing is unlocked."""
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", f"{commit}:aisef2"], capture_output=True, encoding="utf-8")
    return r.stdout.strip() if r.returncode == 0 else None


def measure() -> dict:
    """Everything of the preregistration that this machine decides (no provider is called)."""
    return {"oc": machine(), "client_resolution": client_resolution(), "workload": P10.ledgerlock_baseline(),
            "preserve_to": str(c2_p9.preserve_root() / f"attempt-{EXPERIMENT['attempt']}.git")}


def record(ready: dict, m: dict | None = None) -> dict:
    m = m or measure()
    oc, plan = m["oc"], pc.corrected_plan()
    template, when_attested = runspec(oc), runspec(oc, {})          # the second only for its grades: no fingerprint is known yet
    measured = json.loads((ROOT / MEASURED_REL).read_text(encoding="utf-8"))["model_sessions"]
    v1 = [json.loads((ROOT / "closure-evidence/hardening" / f"W1-LEDGERLOCK-{n}.json").read_text(encoding="utf-8"))["phases"]["finish"]["cost_semantics"]["usage_measured"]
          for n in ("deepseek-ro-1", "deepseek-ro-2", "v21-run2")]
    seen = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / W1).rglob("PROVIDER-PREFLIGHT*.json"))]
    seen = [d for d in seen if d.get("route") == EXPERIMENT["route"]]
    shape, attempts = EXPERIMENT["preflight_shape"], c2_p9.PROFILES[c2_p9.EXPERIMENT]["DEVELOPER"] + 1
    ident = oracle_identity()
    mutants = ready["v1_oracle_calibration_mutants"]
    body = {
        "record": f"AISEF V2 — DELIVERY EXPERIMENT 1, ATTEMPT {EXPERIMENT['attempt']}: PREREGISTRATION AND EXECUTION GUARD OF ONE "
                  "LEDGERLOCK DELIVERY RUN (prepared, not executed)",
        "authority": AUTHORITY,
        "status": "PREPARED — NOT STARTED. " + (f"{HOLD}." if HOLD else "A run of this preregistration is authorized only by the owner's ruling."),
        "run_authorized": f"NO — {HOLD}" if HOLD else "only by the owner's ruling — and by nothing in this record",
        "hold": HOLD, "provider_calls_made_preparing_this": 0,
        "attempt": EXPERIMENT["attempt"],
        "historical_attempts": {str(n): {"preregistration": h["preregistration"], "evidence_commit": h["evidence_commit"],
                                         "problems": historical_problems(n), "rule": "verified against its own records; never re-derived"}
                                for n, h in sorted(HISTORICAL.items())},
        "developer_context": {
            "prompts": harness_identity(),
            "prompt_rule": "H-PROMPT-002: built from the current authoritative sources only — the requirement clause of each of the story's "
                           "obligations (role, requirement and section, clause and text), the approved contracts' product subjects, the plan "
                           "stories it depends on, the harness's test-file instruction. No V1-era story text, example, signature or tuple "
                           "layout; no ProductProofSpec, probe input, stimulus, observable or expectation",
            "retry_feedback": "H-RETRY-001: c2_p9.retry_feedback — from the journal's own records and the obligations' public facts only: "
                              "criterion, role, requirement and clause, contract, spec, probe, subject, candidate, probe status, verdict "
                              "against the expectation, the verifier's agreement, the typed failure and owner, the cited journal seqs; for a "
                              "developer-owned refutation that the candidate remains refuted and the hidden proof stimulus is not disclosed. "
                              "Never a probe input; never control (PROBE-DIAGNOSTIC-GAP-001 is open: the journal records no observation detail)"},
        "kernel": {"commit": EXPERIMENT["kernel_commit"], "tree": EXPERIMENT["kernel_tree"], "head_tree": C.git("rev-parse", "HEAD:aisef2"),
                   "tree_of_the_commit": _tree_of(EXPERIMENT["kernel_commit"]),
                   "commit_is_an_ancestor_of_head": _is_ancestor(EXPERIMENT["kernel_commit"])},
        "harness": {"includes": EXPERIMENT["harness_includes"], "included": _is_ancestor(EXPERIMENT["harness_includes"]),
                    "files": [{"path": rel, "sha256": C.lf_sha(ROOT / rel)} for rel in HARNESS_FILES],
                    "run_command": f"ATTEMPT={EXPERIMENT['attempt']} PROFILE={EXPERIMENT['id']} validation/qualification/c2_p9_run.sh"},
        "workload": {"id": "LedgerLock", "benchmark_class": P10.BENCHMARK_CLASS, "generalization_claim": P10.GENERALIZATION_CLAIM,
                     "start_sha": plan.baseline, "requirements_sha256": P10.REQUIREMENTS_SHA256, "repository": m["workload"]},
        "plan": {"id": plan.id, "plan_hash": plan.plan_hash, "stories": len({o.story_id for o in plan.obligations}), "obligations": len(plan.obligations),
                 "execution_order": c2_p9.order(plan, pc.build()["graph"]),
                 "correction": {"path": pc.OUT_REL, "sha256": C.lf_sha(ROOT / pc.OUT_REL), "check": pc.check()}},
        "profile": {"name": EXPERIMENT["id"], "limits": c2_p9.PROFILES[c2_p9.EXPERIMENT], "developer_attempts_per_story": attempts,
                    "tests_policy": "TestsPolicy(blocking=True), as attempts 1 and 2"},
        "budget": {"max_provider_requests": EXPERIMENT["budget"]["provider_requests"], "max_total_turns": EXPERIMENT["budget"]["turns"],
                   "max_combined_input_tokens": EXPERIMENT["budget"]["input_tokens"],
                   "max_output_plus_reasoning_tokens": EXPERIMENT["budget"]["output_tokens"],
                   "hard": "no automatic increase; no retry pool outside it; the preflight's requests, turns and tokens are in it",
                   "units": {"provider_request": "one model session the harness starts (the journal's provider/request: developer or reviewer) or "
                                                 "one request of the preflight (the model listing, a chat probe, the smoke session); the security "
                                                 "stage is a local scanner and makes none",
                             "turn": "one finished step of a session, over the whole experiment",
                             "input": "prompt + cache read + cache write tokens, one combined number", "output": "completion + reasoning tokens"},
                   "derived_from": "the preflight ledger, the journal's provider/request events and the session streams — re-derived at every "
                                   "check; no counter is kept (c2_p9.Budget)",
                   "when_reached": "a ceiling reached or exceeded, or spend that cannot be accounted for, ends the experiment: the running "
                                   "session's process range is released, no session starts afterwards (the kernel is answered with a provider "
                                   "refusal, owner PROVIDER, never a developer failure), later stories are NOT_RUN, and the delivery verdict is "
                                   "not PASS. The request that reaches the request ceiling may run; nothing after it — and a run that reached "
                                   "any ceiling is not a PASS even when its last story committed",
                   "max_turns_per_session": EXPERIMENT["max_turns_per_session"],
                   "at_the_session_cap": "a developer or reviewer session that reaches it is stopped (its process range released) so that one "
                                         "session cannot consume the experiment's turns; what it changed is committed as the candidate and "
                                         "judged by the proofs, and the experiment goes on. Stopped sessions are counted in the run's record. "
                                         "The smoke session has its own cap (preflight.shape)",
                   "session_timeouts_s": {"developer": c2_p9.DEV_TIMEOUT_S, "reviewer": c2_p9.REVIEW_TIMEOUT_S},
                   "no_later_run": "one attempt number; a record or a preflight in the attempt directory refuses another",
                   "accounting_limitation": c2_p9.ACCOUNTING_LIMITATION,
                   "for_comparison_not_derivation": {"qp_2_9_attempt_2": {"sessions": measured["count"], "turns": sum(s["turns"] for s in measured["sessions"]),
                                                                           "tokens": measured["tokens"]},
                                                     "v1_runs_on_this_route": v1}},
        "model": {"route": EXPERIMENT["route"], "route_kind": EXPERIMENT["route_kind"], "resolved_model": EXPERIMENT["resolved_model"],
                  "dynamic_alias": False, "roles": {"developer": EXPERIMENT["route"], "reviewer": EXPERIMENT["route"]},
                  "why_this_route": "the route of the V1 baseline profile PROFILE-W1V2.1-OC-DEEPSEEKV4PRO-T80-RO (same plan base 136a68dc, "
                                    "max_retries 2): the comparison the experiment exists for",
                  "allowed_identity": allowed_identity(oc),
                  "client": {k: v for k, v in oc.items()}, "client_configuration_overlay": client_config(),
                  "client_resolution_measured_locally": m["client_resolution"],
                  "stable_declared_identity": {"recorded_preflights_on_the_route": len(seen),
                                               "upstreams_listed": sorted({str(d["listing"].get("owned_by")) for d in seen}),
                                               "models_that_answered": sorted({str(p.get("answered_by")) for d in seen for p in d["chat_probes"]}),
                                               "between": [min(d["generated"] for d in seen), max(d["generated"] for d in seen)] if seen else None,
                                               "not_measured_now": "no provider call was permitted while preparing"}},
        "preflight": {"shape": shape, "provider_requests_at_most": shape["listing"] + shape["chat_probes"] + shape["smokes"],
                      "order": "the model listing; then the chat probes, stopping at the first answer that is not the expected identity; then — "
                               "only when the listing and every probe showed the one expected model — the smoke session(s), each bounded by "
                               f"{shape['smoke_max_turns']} turns, {shape['smoke_timeout_s']:.0f} s and the budget",
                      "accounting": f"{PREFLIGHT_DIR}/{LEDGER} in the attempt directory: every request is written before it is sent and after "
                                    "it answers; a request without a result, a probe without usage, a smoke without step telemetry is "
                                    "unaccounted and locks delivery",
                      "written_once": "an attempt directory that holds a preflight, passed or failed, is never preflighted again",
                      "attest_command": "python -P validation/qualification/c2_delivery_experiment.py --attest   (calls the provider: part of the paid run)"},
        "attestation": {"grade_before_preflight": "OPAQUE", "grade_after_a_successful_preflight": "ATTESTED",
                        "contract": "aisef2/runtime/capability.py ATTESTED (RFC §23): provider, endpoint, declared_model, route, client, "
                                    "fingerprint, and deployment when exposed — no new grade, no kernel change",
                        "deployment_identity": "bound only when every probe's response carries one and the same system_fingerprint; otherwise the "
                                               f"attestation records {NOT_EXPOSED} (or EXPOSED_NOT_STABLE) and binds none — never a made-up one. "
                                               "The upstream the router's listing names (owned_by) is a required property of the route and is "
                                               "in the fingerprint; it is not called a deployment",
                        "tuple_binds": {"provider": "provider", "endpoint/provider identity": "endpoint", "fixed route": "route",
                                        "declared model id": "declared_model",
                                        "client identity, client version, client binary digest, client configuration digest relevant to routing": "client",
                                        "provider deployment identity, IF EXPOSED (system_fingerprint)": "deployment",
                                        "locally measured preflight fingerprint": "fingerprint"},
                        "fingerprint_binds": ["the route", "the listing row's id, object and owner", "declared limits when the listing exposes them",
                                              "the declared model id of every probe", "response object, system_fingerprint and usage field names",
                                              "the limits declared to the client", "the smoke probe's tool-calling behaviour"],
                        "fingerprint_is": "a drift detector over observable fields — not a claim about model weights",
                        "refused_as": f"{CANNOT} when the router does not list the route as one fixed upstream or the probes do not show one "
                                      "stable declared model equal to the expected one; delivery stays locked",
                        "record": f"{c2_p9.attempt_dir(EXPERIMENT['attempt'])}/{ATTESTATION}", "max_age_s": EXPERIMENT["attestation_max_age_s"],
                        "gate": "c2_p9.run calls require_unlocked before anything else: the preregistration re-derived, then the attestation "
                                "verified against it — experiment and attempt, preregistration hash, plan, kernel, route, model, client, "
                                "enforcement identity, the tuple and fingerprint rebuilt from the observation, the resolved RunSpec hash, the "
                                "ledger's accounting, its age. Any difference: REFUSED, no provider call"},
        "runspec": {"template_capabilities": [c.resolved() for c in template.capabilities],
                    "template_grade": {"aggregate_min_grade": template.aggregate_min_grade.value, "by_capability": {c.name: c.grade.value for c in template.capabilities}},
                    "resolved_grade_when_attested": {"aggregate_min_grade": when_attested.aggregate_min_grade.value,
                                                     "by_capability": {c.name: c.grade.value for c in when_attested.capabilities}},
                    "settings": json.loads(json.dumps(template.settings, default=dict)),
                    "resolved_derivation": "the template with the developer's and the reviewer's capability replaced by the ATTESTED tuple "
                                           "(the allowed identity plus the fingerprint of the observed preflight fields) and the template's "
                                           "hash added as the setting preregistered_template_hash — c2_delivery_experiment.runspec(oc, fields); "
                                           "the run's journal binds this resolved hash (run/spec-resolved), and it never changes after delivery begins"},
        "runspec_template_hash": template.runspec_hash,
        "enforcement": enforcement_identity(template),
        "preservation": {"root": str(c2_p9.preserve_root()), "git_dir": m["preserve_to"], "free": not pathlib.Path(m["preserve_to"]).exists(),
                         "rule": "the run repository's whole git directory is copied there, and final main and every revision the run names — "
                                 "every story parent, proved candidate, session candidate, committed revision, and every revision the journal "
                                 "cites anywhere — pinned under refs/qp-2.9/ before the temporary directory is removed; it is not removed "
                                 "unless all are held, and no delivery PASS is recorded unless they are"},
        "final_evaluation": {"v2_final_proof": "all 59 ProductProofSpecs, each on its own probe, on the final main (FINAL-EVALUATION.json)",
                             "delivery_pass_confirmed": "only when the run's delivery verdict is PASS and the final main satisfies 59 of 59 specs "
                                                        "and passes every check of the V1 oracle",
                             "v1_oracle": {**ident,
                                           "ORACLE_RUNTIME_DIFFERENCE": ident["runtime_difference"],
                                           "ORACLE_CALIBRATION_EQUIVALENCE": "PASS" if mutants["killed"] == mutants["total"] == 10 and not mutants["survived"] else "FAIL"},
                             "readiness_measured_without_a_provider": ready},
        "frozen_during_the_run": ["the run script refuses a dirty tree and a kernel tree other than the preregistered one, before and after",
                                  "the runner itself re-derives this preregistration and verifies the attestation before any provider call",
                                  "the resolved RunSpec is fixed by the attestation before delivery begins and is the one the journal binds",
                                  "HEAD must be the same commit after the run as before it",
                                  "the plan is the corrected plan by hash: no re-planning, no story split"],
    }
    body["problems"] = problems(body)
    body["verdict"] = f"PREREGISTERED — ATTEMPT {EXPERIMENT['attempt']}, THE OWNER'S BUDGET; ONE RUN" if not body["problems"] else "PROBLEMS"
    return json.loads(json.dumps(body))


TAKEN = "the preservation path is taken"


def problems(body: dict) -> list[str]:
    out = [f"historical attempt {n}: {p}" for n, h in (body.get("historical_attempts") or {}).items() for p in h["problems"]]
    if body.get("attempt") in HISTORICAL or OUT_REL in [h["preregistration"] for h in HISTORICAL.values()]:
        out.append("an attempt that has run is historical: it is never preregistered again")
    k = body["kernel"]
    if not (k["tree"] == k["head_tree"] == k["tree_of_the_commit"] and k["commit_is_an_ancestor_of_head"]):
        out.append("the kernel of this tree is not the preregistered kernel commit's")
    if not body["harness"]["included"]:
        out.append("the harness commit is not in this history")
    w = body["workload"]["repository"]
    if not (w.get("present") and w.get("requirements_match_frozen") and w.get("baseline") == body["workload"]["start_sha"]):
        out.append("the workload is not at its baseline with the frozen requirements")
    out += [f"plan correction: {p}" for p in body["plan"]["correction"]["check"]]
    if body["profile"]["developer_attempts_per_story"] != 3:
        out.append("not three developer attempts")
    b = body["budget"]
    if (b["max_provider_requests"], b["max_total_turns"], b["max_turns_per_session"], b["max_combined_input_tokens"],
            b["max_output_plus_reasoning_tokens"]) != (60, 700, 80, 60_000_000, 700_000):
        out.append("the budget is not the owner's")
    r, c = body["model"]["client_resolution_measured_locally"], body["model"]["client"]
    if not (r.get("client_present") and r.get("resolves_to_the_fixed_route") and r.get("route_model_declared")):
        out.append("the client does not resolve the fixed route")
    if c.get("endpoint") != EXPERIMENT["endpoint"] or not c.get("routing_config_digest") or not c.get("binary_sha256"):
        out.append("the client's endpoint, routing configuration or binary is not identified")
    s = body["model"]["stable_declared_identity"]
    if not s["recorded_preflights_on_the_route"] or s["models_that_answered"] != [EXPERIMENT["resolved_model"]] \
            or s["upstreams_listed"] != [EXPERIMENT["listing_owner"]]:
        out.append(f"{CANNOT}: the recorded preflights do not show one stable declared identity on the route")
    g = body["runspec"]
    if g["template_grade"]["by_capability"].get("developer") != "OPAQUE" or g["resolved_grade_when_attested"]["aggregate_min_grade"] != "ATTESTED":
        out.append("the RunSpec does not resolve to ATTESTED once the model is attested (another capability is OPAQUE)")
    if not body["preservation"]["free"]:
        out.append(TAKEN)
    o, ready = body["final_evaluation"]["v1_oracle"], body["final_evaluation"]["readiness_measured_without_a_provider"]
    if not (o["unchanged_since_calibration"] and o["independence_verdict"] == "PASS" and o["interpreter"]["pytest"] and o["interpreter"]["coverage"]):
        out.append("the V1 oracle is not the calibrated one, or cannot run here")
    p, v = ready["v2_final_proof_on_the_p5_reference_fixture"], ready["v1_oracle_on_its_calibration_reference"]
    if (p["total"], p["satisfied"]) != (59, 59):
        out.append(f"readiness: {p['satisfied']}/{p['total']} specs satisfied on the reference fixture")
    if not (v["complete"] and v["total"] == 9 and v["passed"] == 9):
        out.append(f"readiness: the oracle passed {v['passed']}/{v['total']} on its calibration reference")
    if o["ORACLE_CALIBRATION_EQUIVALENCE"] != "PASS" or v["interpreter"] != o["interpreter"]:
        out.append("ORACLE_ENVIRONMENT_NOT_EQUIVALENT: under this interpreter a calibration mutant survives, or the calibration is of another interpreter")
    return out


def check(after_run: bool = False) -> list[str]:
    """The committed preregistration against this tree and this machine; its readiness section is taken as measured.
    After the run its preservation path holds the run's result, which is then no difference and no problem. The
    preregistration of an attempt that has run is historical: it is checked against its own records instead."""
    if EXPERIMENT["attempt"] in HISTORICAL:
        return historical_problems(EXPERIMENT["attempt"])
    path = ROOT / OUT_REL
    if not path.exists():
        return [f"{OUT_REL} does not exist"]
    was = committed()
    try:
        rec = record(was["final_evaluation"]["readiness_measured_without_a_provider"])
    except (KeyError, TypeError) as e:      # a record of another version of this module: nothing is unlocked by it
        return [f"{OUT_REL} is not a preregistration this tree can derive ({type(e).__name__}: {e})"]
    if after_run:
        rec["preservation"] = was["preservation"]
        rec["problems"] = [p for p in rec["problems"] if p != TAKEN]
        rec["verdict"] = was["verdict"] if not rec["problems"] else rec["verdict"]
    return list(rec["problems"]) + ([] if rec == was else [f"{OUT_REL} is not what this tree and this machine derive"])


# ------------------------------------------------------------------------------- attempts already run: their history

#: Attempts already run — immutable historical evidence (owner ruling 'ATTEMPT-3 HISTORICALIZATION + H-PROMPT-002 +
#: H-RETRY-001', §A). Each is verified against what its own records state: the evidence commit that froze it (named by
#: the owner), the commit the run executed on (its record's `repository_execution_commit`) and the content digests its
#: preregistration bound. A later change of the harness on HEAD does not touch it; a change of anything it pins fails.
HISTORICAL = {3: {"preregistration": "closure-evidence/v2/cycle2/DELIVERY-EXPERIMENT-1-PREREGISTRATION.json",
                  "owned": "closure-evidence/v2/cycle2/P10/owned/run.attempt-3.json",
                  "evidence_commit": "f86e8f4fbbf20064953cc32c967fa21756c9f627"}}
_HEX40 = re.compile(r"[0-9a-f]{40}")


def _blob(commit: str, rel: str) -> bytes | None:
    """`rel` as `commit` holds it, from git's object store — never from the working tree."""
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{rel}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def _tree_at(commit: str) -> str | None:
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", f"{commit}:aisef2"], capture_output=True, encoding="utf-8")
    return r.stdout.strip() if r.returncode == 0 else None


def historical_files(n: int) -> dict[str, bytes | None]:
    """Attempt `n`'s evidence as this working tree holds it: every file its evidence commit froze (None where one is
    gone), and every file now in its attempt directory that the commit did not freeze."""
    h, d = HISTORICAL[n], c2_p9.attempt_dir(n)
    frozen = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", h["evidence_commit"], "--", d, h["owned"],
                             h["preregistration"]], capture_output=True, encoding="utf-8").stdout.split()
    now = [p.relative_to(ROOT).as_posix() for p in (ROOT / d).rglob("*") if p.is_file()]
    return {rel: ((ROOT / rel).read_bytes() if (ROOT / rel).is_file() else None) for rel in sorted(set(frozen) | set(now))}


def historical_problems(n: int, files: dict[str, bytes | None] | None = None) -> list[str]:
    """Why attempt `n`'s evidence does not hold, or []. `files`: its evidence as `historical_files` reads it (a test
    passes an altered copy). Sources are read only from git's objects at the commits the evidence names."""
    if n not in HISTORICAL:
        return [f"attempt {n} has not run: it has no historical evidence"]
    h, d = HISTORICAL[n], c2_p9.attempt_dir(n)
    files = historical_files(n) if files is None else files
    out = []
    for rel, data in files.items():
        frozen = _blob(h["evidence_commit"], rel)
        if frozen is None:
            out.append(f"{rel}: not in the evidence commit {h['evidence_commit'][:12]} — the historical evidence holds nothing else")
        elif data is None:
            out.append(f"{rel}: missing — its evidence commit {h['evidence_commit'][:12]} holds it")
        elif _lf(data) != _lf(frozen):
            out.append(f"{rel}: differs from its evidence commit {h['evidence_commit'][:12]}")
    try:
        att, rec = json.loads(files[f"{d}/{ATTESTATION}"]), json.loads(files[f"{d}/LEDGERLOCK-REGRESSION.json"])
        prereg_bytes = files[h["preregistration"]]
        prereg, events = json.loads(prereg_bytes), json.loads(files[f"{d}/JOURNAL.json"])
    except (KeyError, TypeError, ValueError) as e:
        return out + [f"attempt {n}'s attestation, record, preregistration or journal cannot be read ({type(e).__name__}: {e})"]
    if att.get("verdict") != "ATTESTED" or att.get("experiment") != {"id": c2_p9.EXPERIMENT, "attempt": n}:
        out.append(f"the attestation is not an ATTESTED one of attempt {n}")
    if att.get("preregistration") != {"path": h["preregistration"], "sha256": _sha(_canon(prereg))}:
        out.append("the attestation is not bound to this preregistration")
    if rec.get("preregistration") != {"path": h["preregistration"], "sha256": _sha(_lf(prereg_bytes))}:
        out.append("the run's record is not bound to this preregistration")
    run_at = rec.get("repository_execution_commit")
    if not (isinstance(run_at, str) and _HEX40.fullmatch(run_at) and _tree_at(run_at)):
        return out + [f"the commit the run executed on ({run_at!r}) is not in this repository"]
    bound = {f["path"]: f["sha256"] for f in (prereg.get("harness") or {}).get("files") or []}
    if not bound:
        out.append("the preregistration binds no harness file")
    for rel, sha in bound.items():
        blob = _blob(run_at, rel)
        if blob is None or _sha(_lf(blob)) != sha:
            out.append(f"the preregistration bound {rel} as {sha[:12]}…, which is not its blob at the commit the run executed on "
                       f"({run_at[:12]})")
    if rec.get("harness") != {"path": "validation/qualification/c2_p9.py", "sha256": bound.get("validation/qualification/c2_p9.py")}:
        out.append("the run's record names another c2_p9.py than its preregistration bound")
    k = prereg.get("kernel") or {}
    trees = {_tree_at(run_at), _tree_at(str(k.get("commit"))), k.get("tree"), (att.get("kernel") or {}).get("tree"),
             rec.get("aisef2_tree"), rec.get("head_kernel_tree")}
    commits = {k.get("commit"), (att.get("kernel") or {}).get("commit"), rec.get("semantic_candidate")}
    if len(trees) != 1 or None in trees or len(commits) != 1 or None in commits:
        out.append(f"the kernel the run executed is not the one its preregistration and attestation bound: trees "
                   f"{sorted(map(str, trees))}, commits {sorted(map(str, commits))}")
    if att.get("runspec_template_hash") != prereg.get("runspec_template_hash"):
        out.append("the attestation's RunSpec template is not the preregistered one")
    resolved = [e["data"]["runspec_hash"] for e in events if e.get("type") == "run/spec-resolved"]
    if resolved != [att.get("resolved_runspec_hash")] or (rec.get("execution_profile") or {}).get("runspec_hash") != att.get("resolved_runspec_hash"):
        out.append("the journal's resolved RunSpec is not the one the attestation fixed")
    ident = rec.get("run_identity") or {}
    if _sha(json.dumps(events, sort_keys=True, default=str).encode()) != ident.get("journal_sha256") or len(events) != ident.get("journal_events"):
        out.append("the journal is not the one the run's record names")
    if not att.get("plan_hash") == (prereg.get("plan") or {}).get("plan_hash") == (rec.get("plan_identity") or {}).get("plan_hash"):
        out.append("the attestation, the preregistration and the record name different plans")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--check-historical", action="store_true", help="every attempt already run, against its own records")
    g.add_argument("--attest", action="store_true", help="PART OF THE PAID RUN: the provider preflight (calls the provider)")
    ap.add_argument("--after-run", action="store_true")
    a = ap.parse_args(argv)
    if a.attest:
        found = check()
        if found:       # before any provider call
            raise SystemExit("REFUSED: the delivery experiment is not as preregistered: " + "; ".join(found))
        rec = attest(attempt_path())
        print(f"{rec['verdict']}: {rec['accounting']['provider_requests']} provider requests, {rec['accounting']['turns']} turns; "
              f"{'resolved RunSpec ' + rec['resolved_runspec_hash'] if rec['verdict'] == 'ATTESTED' else '; '.join(rec['problems'])}")
        return 0 if rec["verdict"] == "ATTESTED" else 1
    if a.check_historical:
        found = [f"attempt {n}: {p}" for n in sorted(HISTORICAL) for p in historical_problems(n)]
        print("\n".join(found) if found else f"PASS: attempts {sorted(HISTORICAL)} hold as their own records state")
        return 1 if found else 0
    if a.write:
        if EXPERIMENT["attempt"] in HISTORICAL:
            raise SystemExit(f"refused: attempt {EXPERIMENT['attempt']} has run — its preregistration is historical evidence and is "
                             "never re-derived")
        rec = record(readiness())
        if rec["problems"]:
            raise SystemExit("refused: " + "; ".join(rec["problems"]))
        (ROOT / OUT_REL).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(f"{OUT_REL}: {rec['verdict']}; runspec template {rec['runspec_template_hash']}; plan {rec['plan']['plan_hash']}")
        return 0
    found = check(a.after_run)
    print("\n".join(found) if found else "PASS")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
