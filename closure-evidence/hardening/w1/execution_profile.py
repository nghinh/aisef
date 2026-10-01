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
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
#: OPERATOR_ENVIRONMENT rule (owner decision 2026-09-19, section 10): temporary trees live in a dedicated qualification
#: workspace, never a shared writable directory; every `python -c` runs with -P (no cwd on sys.path)
QUAL_WS = Path.home() / "Downloads/projects/aisef-qualification-ws"


def _ws() -> str:
    QUAL_WS.mkdir(parents=True, exist_ok=True)
    return str(QUAL_WS)


ROOT = HERE.parents[2]
FREEZE = ROOT / "closure-evidence/hardening/P19-FREEZE.json"
MATRIX = ROOT / "closure-evidence/hardening/tool-capability-matrix.json"
GLOBAL_OC = Path.home() / ".config/opencode/opencode.json"
ROLES = ("developer", "reviewer", "security", "designer")
#: fields a copy's configuration determines; `verify` recomputes exactly these
CONFIG_FIELDS = ("kernel", "client", "client_version", "routes", "max_turns", "max_retries", "max_infra_retries",
                 "context_window", "small_model", "sandbox_tool_profile", "guard_digest", "prompt_catalog_digest",
                 "client_config_digest", "cost_cap_usd")
#: declared by a profile only when it has one; a profile that does not declare it keeps its original id
OPTIONAL_FIELDS = ("stage_env",)
SECRET = re.compile(r"key|token|secret|auth|password", re.I)
#: The reviewer's dependency command exactly as the workload's review skills write it (.claude/skills/bmad-code-review/
#: SKILL.md, bmad-review/SKILL.md), {project-root} and {skill-root} filled in (owner decision "FIX SS-81 FAMILY", s. 11).
REVIEWER_DEP_CMD = ("uv run {p}/_bmad/scripts/resolve_customization.py --skill {p}/.claude/skills/bmad-code-review "
                    "--project-root {p} --key workflow")
#: how a session's shell may run it: plain sh, zsh, and an interactive zsh that reads the operator's rc files
SHELLS = (("/bin/sh", "-c"), ("/bin/zsh", "-c"), ("/bin/zsh", "-ic"))


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
    return json.loads(subprocess.run([py, "-P", "-c", code, str(copy)], capture_output=True, text=True, check=True).stdout)


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


def stage_env(path: str) -> dict:
    """The `uv` a session resolves on `path` — the profile's wrapper or not — and the real uv behind it."""
    uv = shutil.which("uv", path=path)
    if not uv:
        return {"resolved_uv": None}
    p = Path(uv).resolve()
    with open(p, "rb") as fh:
        head = fh.read(65536)
    m = re.search(rb'PROFILE_REAL_UV:-([^}"]+)', head)
    real = m.group(1).decode() if m else str(p)
    try:
        ver = subprocess.run([real, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        ver = ""                                   # unmeasurable: recorded empty, so it can never match a profile's version
    return {"resolved_uv": str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p),
            "wrapper_sha256": _sha(p.read_bytes()) if m else None, "real_uv": real, "real_uv_version": ver}


def _role_env(venv: Path, role: str, path: str, copy: Path) -> dict:
    """The environment the FROZEN kernel gives a `role` session: its spec.env markers through its own child_env."""
    code = ("import json, sys\n"
            "from aisef.clients.base import child_env\n"
            "from aisef.clients.opencode import OpenCodeAdapter\n"
            "from aisef.harness import guardrails as G\n"
            "from aisef.harness.routing import ROLES\n"
            "role, wd = sys.argv[1], sys.argv[2]\n"
            "spec = {G.ENV_WORKDIR: wd, G.ENV_PROJECT: wd}\n"
            "if role == 'developer':\n"
            "    spec[G.ENV_STORY_ID] = 'PREFLIGHT'\n"
            "else:\n"
            "    spec[G.ENV_DISALLOWED_TOOLS] = ','.join(ROLES[role].disallowed_tools)\n"
            "print(json.dumps(child_env(spec, allow_prefixes=OpenCodeAdapter.env_prefixes)))\n")
    r = subprocess.run([_venv_python(venv), "-P", "-c", code, role, str(copy)], capture_output=True, text=True, check=True,
                       env={**os.environ, "PATH": path})
    return json.loads(r.stdout)


def _snapshot(tree: Path) -> str:
    """Everything a session could have changed: git's view (tracked, untracked, ignored) and every file's bytes."""
    st = subprocess.run(["git", "-C", str(tree), "status", "--porcelain=v1", "--ignored", "-uall"], capture_output=True, text=True).stdout
    files = sorted(f for f in tree.rglob("*") if f.is_file() and ".git" not in f.relative_to(tree).parts[:1])
    return _sha(st.encode() + b"".join(str(f.relative_to(tree)).encode() + b"\0" + _sha(f.read_bytes()).encode() for f in files))


def stage_env_check(copy: Path, venv: Path, path: str) -> dict:
    """Preflight (owner s. 11): the exact reviewer dependency command, run with the reviewer's and the security
    session's environment as the frozen kernel builds it, in every shell form, leaves the tree byte-identical; the
    developer's session, in a throw-away clone, still gets the real uv (it writes the lock) — so the check has teeth."""
    rows = {}
    for role in ("reviewer", "security"):
        env = _role_env(venv, role, path, copy)
        for sh in SHELLS:
            before = _snapshot(copy)
            r = subprocess.run([*sh, REVIEWER_DEP_CMD.format(p=copy)], cwd=str(copy), env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=300)
            rows[f"{role} {' '.join(sh)}"] = {"identical": _snapshot(copy) == before, "exit": r.returncode,
                                              "tail": (r.stdout + r.stderr).strip()[-240:]}
    with tempfile.TemporaryDirectory(dir=_ws()) as td:
        clone = Path(td) / "clone"
        subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(copy), str(clone)], check=True)
        env = _role_env(venv, "developer", path, clone)
        before = _snapshot(clone)
        subprocess.run(["/bin/sh", "-c", REVIEWER_DEP_CMD.format(p=clone)], cwd=str(clone), env=env, capture_output=True, timeout=300)
        new = subprocess.run(["git", "-C", str(clone), "status", "--porcelain=v1", "--ignored", "-uall"], capture_output=True,
                             text=True).stdout.split("\n")
        control = {"developer_tree_changed": _snapshot(clone) != before, "new": sorted({ln[3:].split("/")[0] for ln in new if ln})}
    return {"command": REVIEWER_DEP_CMD, "path": path, "stage_env": stage_env(path), "per_role_shell": rows,
            "developer_control": control, "pass": all(v["identical"] for v in rows.values()) and control["developer_tree_changed"]}


def measure(copy: Path, venv: Path, freeze: Path = FREEZE, path: str | None = None) -> dict:
    fr = json.loads(freeze.read_text(encoding="utf-8"))
    py = _venv_python(venv)
    cfg = _config(copy, py)
    routes = _effective_routes(copy, cfg)
    prompts = Path(subprocess.run([py, "-P", "-c", "import aisef, pathlib; print(pathlib.Path(aisef.__file__).parent / 'kit/prompts')"],
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
        "stage_env": stage_env(path if path is not None else os.environ.get("PATH", "")),
    }


def profile_id(identity: dict) -> str:
    """Digest over the configuration-determined fields plus the declared route resolution."""
    picked = {k: identity[k] for k in CONFIG_FIELDS}
    picked.update({k: identity[k] for k in OPTIONAL_FIELDS if identity.get(k) is not None})
    if identity.get("provider_preflight") is not None:     # owner decision 2026-09-19 s.5: declared at definition
        picked["provider_preflight"] = identity["provider_preflight"]
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


def verify(profile: dict, copy: Path, venv: Path, freeze: Path = FREEZE, path: str | None = None) -> dict:
    got = measure(copy, venv, freeze, path)
    got["route_resolution"] = profile["identity"].get("route_resolution")
    if profile["identity"].get("provider_preflight") is not None:
        got["provider_preflight"] = profile["identity"]["provider_preflight"]    # declared; each run re-probes it
    fields = CONFIG_FIELDS + tuple(k for k in OPTIONAL_FIELDS if profile["identity"].get(k) is not None)
    for k in OPTIONAL_FIELDS:
        if profile["identity"].get(k) is None:
            got.pop(k, None)                  # a profile that declares no stage environment is not measured on one
    diffs = {k: {"profile": profile["identity"].get(k), "copy": got.get(k)} for k in fields if profile["identity"].get(k) != got.get(k)}
    pid = profile_id(got)
    return {"profile": profile["profile"], "profile_id": profile["profile_id"], "copy_id": pid,
            "matches": not diffs and pid == profile["profile_id"], "differences": diffs}


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure"); m.add_argument("copy"); m.add_argument("--venv"); m.add_argument("--freeze", default=str(FREEZE))
    a_ = sub.add_parser("apply"); a_.add_argument("profile"); a_.add_argument("copy")
    v = sub.add_parser("verify"); v.add_argument("profile"); v.add_argument("copy"); v.add_argument("--venv"); v.add_argument("--freeze", default=str(FREEZE))
    c = sub.add_parser("stage-check"); c.add_argument("copy"); c.add_argument("--venv")
    for sp in (m, v, c):
        sp.add_argument("--path", default=None, help="the PATH `aisef run` will use (default: this process's)")
    a = ap.parse_args()
    venv = Path(getattr(a, "venv", None) or json.loads(FREEZE.read_text(encoding="utf-8"))["run_venv"]["path"])
    if a.cmd == "measure":
        print(json.dumps(measure(Path(a.copy).expanduser(), venv, Path(a.freeze), a.path), indent=1, default=str))
        return 0
    if a.cmd == "stage-check":
        out = stage_env_check(Path(a.copy).expanduser(), venv, a.path or os.environ.get("PATH", ""))
        print(json.dumps(out, indent=1, default=str))
        return 0 if out["pass"] else 1
    prof = json.loads(Path(a.profile).read_text(encoding="utf-8"))
    if a.cmd == "apply":
        print(" ".join(apply(prof, Path(a.copy).expanduser())))
        return 0
    out = verify(prof, Path(a.copy).expanduser(), venv, Path(a.freeze), a.path)
    print(json.dumps(out, indent=1, default=str))
    return 0 if out["matches"] else 1


if __name__ == "__main__":
    sys.exit(main())
