"""ExecutionProfile identity (owner decision "KERNEL ACCEPTED, EXECUTION PROFILE NOT QUALIFIED", section 3).

W1 delivery qualification belongs to (Kernel, ExecutionProfile, Workload), not to the kernel alone. A profile is
everything outside the frozen kernel that shapes how the model works: client and version, route and the model that
actually answers on it, turn and retry budgets, context window, sandbox/tool profile, guard, prompt catalog and the
client's own configuration. Its id is a digest over those fields, so two runs share a profile only if every field is
equal — and a run copy is checked against its profile before the first model call.

    execution_profile.py measure <run-copy> [--venv V] [--freeze F]    identity measured from a prepared copy (JSON)
    execution_profile.py apply   <profile.json> <run-copy>             write the profile's settings into a fresh copy
    execution_profile.py verify  <profile.json> <run-copy>             exit 0 only if the copy measures to the same id

Nothing here edits aisef/: `run.max_turns` and `route.<role>_model` are the product's own typed configuration keys,
and the model declaration goes into the run copy's project-level opencode.json, never the operator's global one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FREEZE = ROOT / "closure-evidence/hardening/P19-FREEZE.json"
MATRIX = ROOT / "closure-evidence/hardening/tool-capability-matrix.json"
GLOBAL_OC = Path.home() / ".config/opencode/opencode.json"
ROLES = ("developer", "reviewer", "security", "designer")
#: fields a copy's configuration determines; `verify` recomputes exactly these
CONFIG_FIELDS = ("kernel", "client", "client_version", "routes", "max_turns", "max_retries", "max_infra_retries",
                 "context_window", "small_model", "sandbox_tool_profile", "guard_digest", "prompt_catalog_digest",
                 "client_config_digest", "cost_cap_usd")
SECRET = re.compile(r"key|token|secret|auth|password", re.I)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _redact(o):
    if isinstance(o, dict):
        return {k: ("<redacted>" if SECRET.search(k) else _redact(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [_redact(x) for x in o]
    return o


def _venv_python(venv: Path) -> str:
    return str(venv / "bin/python")


def _config(copy: Path, py: str) -> dict:
    code = ("import json,sys; from aisef.config import Config; "
            "print(json.dumps(Config.load(sys.argv[1]).values, default=str))")
    return json.loads(subprocess.run([py, "-c", code, str(copy)], capture_output=True, text=True, check=True).stdout)


def _declared_limit(copy: Path, route: str) -> dict | None:
    """The context window OpenCode will use for `route`: the project declaration wins over the global one."""
    prov, _, model = route.partition("/")
    for p in (copy / "opencode.json", GLOBAL_OC):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))["provider"][prov]["models"][model]
        except (OSError, ValueError, KeyError):
            continue
        return m.get("limit")
    return None


def _effective_routes(copy: Path, cfg: dict) -> dict:
    """What each role actually runs on: `route.<role>_model` if set, else the client default the copy resolves to."""
    default = ""
    for p in (copy / "opencode.json", copy / ".opencode/opencode.json", GLOBAL_OC):
        try:
            default = json.loads(p.read_text(encoding="utf-8")).get("model") or ""
        except (OSError, ValueError):
            continue
        if default:
            break
    return {r: (cfg.get(f"route.{r}_model") or default) for r in ROLES}


def measure(copy: Path, venv: Path, freeze: Path = FREEZE) -> dict:
    fr = json.loads(freeze.read_text(encoding="utf-8"))
    py = _venv_python(venv)
    cfg = _config(copy, py)
    routes = _effective_routes(copy, cfg)
    prompts = Path(subprocess.run([py, "-c", "import aisef, pathlib; print(pathlib.Path(aisef.__file__).parent / 'kit/prompts')"],
                                  capture_output=True, text=True, check=True).stdout.strip())
    catalog = _sha(b"".join(f.name.encode() + b"\0" + f.read_bytes() for f in sorted(prompts.glob("*.md"))))
    plugin = copy / ".opencode/plugin/aisef-guard.ts"
    guard = _sha(plugin.read_text(encoding="utf-8").replace(str(copy), "<RUN-COPY>").encode()) if plugin.is_file() else ""
    glob = json.loads(GLOBAL_OC.read_text(encoding="utf-8")) if GLOBAL_OC.is_file() else {}
    proj = json.loads((copy / "opencode.json").read_text(encoding="utf-8")) if (copy / "opencode.json").is_file() else {}
    return {
        "kernel": {"candidate_sha": fr["candidate_sha"], "product_tree": fr["aisef_tree_digest"], "wheel_sha256": fr["wheel"]["sha256"]},
        "client": "opencode",
        "client_version": subprocess.run(["opencode", "--version"], capture_output=True, text=True).stdout.strip(),
        "routes": routes,
        "max_turns": cfg.get("run.max_turns"), "max_retries": cfg.get("run.max_retries"),
        "max_infra_retries": cfg.get("run.infra_retries"),   # -1 = the kernel default, max_retries + 1
        "context_window": {r: _declared_limit(copy, m) for r, m in routes.items()},
        "small_model": proj.get("small_model") or glob.get("small_model"),
        "sandbox_tool_profile": {"sandbox.image": cfg.get("sandbox.image"),
                                 "tools": {k: v for k, v in sorted(cfg.items()) if k.startswith("tools.")},
                                 "capability_matrix_sha256": _sha(MATRIX.read_bytes()) if MATRIX.is_file() else ""},
        "guard_digest": guard,
        "prompt_catalog_digest": catalog,
        "client_config_digest": _sha(json.dumps({"global": _redact(glob), "project": _redact(proj)}, sort_keys=True).encode()),
        "cost_cap_usd": cfg.get("run.cost_cap_usd"),
    }


def profile_id(identity: dict) -> str:
    """Digest over the configuration-determined fields plus the declared route resolution."""
    picked = {k: identity[k] for k in CONFIG_FIELDS}
    picked["route_resolution"] = {r: {k: v for k, v in (identity.get("route_resolution") or {}).get(r, {}).items()
                                      if k in ("route_kind", "resolved_model")} for r in ROLES}
    return "sha256:" + _sha(json.dumps(picked, sort_keys=True, default=str).encode())


def apply(profile: dict, copy: Path) -> list[str]:
    """Write the profile's settings into a fresh copy. Returns the files changed (the caller commits them)."""
    want = profile["identity"]
    cfgp = copy / ".ai/config.json"
    c = json.loads(cfgp.read_text(encoding="utf-8"))
    c["run.max_turns"] = want["max_turns"]
    for r in ROLES:
        if want["route_config"].get(r):
            c[f"route.{r}_model"] = want["route_config"][r]
    cfgp.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    changed = [".ai/config.json"]
    if want.get("project_opencode"):
        (copy / "opencode.json").write_text(json.dumps(want["project_opencode"], indent=2) + "\n", encoding="utf-8")
        changed.append("opencode.json")
    return changed


def verify(profile: dict, copy: Path, venv: Path, freeze: Path = FREEZE) -> dict:
    got = measure(copy, venv, freeze)
    got["route_resolution"] = profile["identity"].get("route_resolution")
    diffs = {k: {"profile": profile["identity"].get(k), "copy": got.get(k)} for k in CONFIG_FIELDS if profile["identity"].get(k) != got.get(k)}
    pid = profile_id(got)
    return {"profile": profile["profile"], "profile_id": profile["profile_id"], "copy_id": pid,
            "matches": not diffs and pid == profile["profile_id"], "differences": diffs}


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure"); m.add_argument("copy"); m.add_argument("--venv"); m.add_argument("--freeze", default=str(FREEZE))
    a_ = sub.add_parser("apply"); a_.add_argument("profile"); a_.add_argument("copy")
    v = sub.add_parser("verify"); v.add_argument("profile"); v.add_argument("copy"); v.add_argument("--venv"); v.add_argument("--freeze", default=str(FREEZE))
    a = ap.parse_args()
    venv = Path(getattr(a, "venv", None) or json.loads(FREEZE.read_text(encoding="utf-8"))["run_venv"]["path"])
    if a.cmd == "measure":
        print(json.dumps(measure(Path(a.copy).expanduser(), venv, Path(a.freeze)), indent=1, default=str))
        return 0
    prof = json.loads(Path(a.profile).read_text(encoding="utf-8"))
    if a.cmd == "apply":
        print(" ".join(apply(prof, Path(a.copy).expanduser())))
        return 0
    out = verify(prof, Path(a.copy).expanduser(), venv, Path(a.freeze))
    print(json.dumps(out, indent=1, default=str))
    return 0 if out["matches"] else 1


if __name__ == "__main__":
    sys.exit(main())
