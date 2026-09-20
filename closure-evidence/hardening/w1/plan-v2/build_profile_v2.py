"""Define the W1-V2 execution profile for the NEW frozen kernel (owner decision 2026-09-20, sections 14 and 20).

Same shape as the profiles of the previous cycle — one fixed model for every role, max_turns 80, the proven
read-only reviewer environment — measured from a rehearsal copy prepared exactly like a run copy from the
W1-LEDGERLOCK-PLAN-V2 base, with the route's provider-stability preflight recorded into the identity.

    python3 build_profile_v2.py --route 9router/ds/deepseek-v4-pro --name PROFILE-W1V2-OC-DEEPSEEKV4PRO-T80-RO \
        --plan-base 1621a2bc --like closure-evidence/hardening/w1/profiles/PROFILE-W1-OC-DEEPSEEKV4PRO-T80-RO.json
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
W1 = HERE.parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(W1))

import execution_profile as ep  # noqa: E402
import provider_preflight as pp  # noqa: E402


def sh(cmd: list[str], **kw) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if r.returncode:
        raise SystemExit(f"{' '.join(cmd[:4])}… failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return r.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--route", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--plan-base", required=True)
    ap.add_argument("--like", required=True, help="the previous cycle's profile this one keeps everything else from")
    ap.add_argument("--context", type=int, default=200000)
    ap.add_argument("--output", type=int, default=32768)
    ap.add_argument("--probes", type=int, default=3)
    ap.add_argument("--smokes", type=int, default=3)
    a = ap.parse_args()

    freeze = json.loads((ROOT / "closure-evidence/hardening/P19-FREEZE.json").read_text(encoding="utf-8"))
    venv = Path(freeze["run_venv"]["path"])
    model = a.route.split("/", 1)[1]
    like = json.loads(Path(a.like).read_text(encoding="utf-8"))

    draft = {"profile": a.name, "identity": copy.deepcopy(like["identity"])}
    i = draft["identity"]
    i["routes"] = {r: a.route for r in i["routes"]}
    i["route_config"] = {r: a.route for r in i["route_config"]}
    i["project_opencode"] = {"$schema": "https://opencode.ai/config.json", "model": a.route,
                             "provider": {a.route.split("/", 1)[0]: {"models": {
                                 model: {"name": model, "limit": {"context": a.context, "output": a.output}}}}}}
    draft_path = ep.QUAL_WS / f"draft-{a.name}.json"
    ep.QUAL_WS.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(json.dumps(draft, indent=1), encoding="utf-8")

    copy_dir = ep.QUAL_WS / f"rehearsal-{a.name}"
    if copy_dir.exists():
        raise SystemExit(f"refused: {copy_dir} exists — remove it or pick another name")
    env = {**os.environ, "PROFILE": str(draft_path), "PLAN_BASE": a.plan_base}
    print(sh([str(W1 / "prepare_run_copy.sh"), f"rehearsal-{a.name}", str(venv), str(copy_dir)], env=env).strip()[-400:])
    sh([str(venv / "bin/aisef"), "compile", "--client", "opencode", "--bin", str(venv / "bin/aisef")], cwd=str(copy_dir))

    path = os.pathsep.join([str(W1 / "profiles/stage-env-ro-uv/bin"), str(Path.home() / ".local/bin"), os.environ.get("PATH", "")])
    out = ROOT / f"closure-evidence/hardening/w1/profiles/PROVIDER-PREFLIGHT-{a.name}.json"
    code = subprocess.call([sys.executable, str(W1 / "provider_preflight.py"), a.route, "--probes", str(a.probes),
                            "--smokes", str(a.smokes), "--context", str(a.context), "--output", str(a.output),
                            "--stage-copy", str(copy_dir), "--venv", str(venv), "--stage-path", path, "--out", str(out)])
    if code:
        raise SystemExit("provider preflight FAILED — no profile is defined for a route that does not answer")
    pf = json.loads(out.read_text(encoding="utf-8"))

    ident = ep.measure(copy_dir, venv, ROOT / "closure-evidence/hardening/P19-FREEZE.json", path)
    ident["route_config"] = draft["identity"]["route_config"]
    ident["project_opencode"] = draft["identity"]["project_opencode"]
    listing = pp.listing(*pp._provider(a.route.split("/", 1)[0]), model)
    ev = (f"profiles/PROVIDER-PREFLIGHT-{a.name}.json: router /models lists {model} owned_by {listing.get('owned_by')!r}; "
          f"{pf['summary_for_identity']['chat_probes']} chat probes answered_by "
          f"{pf['summary_for_identity']['resolved_model']!r}; OpenCode tool smokes {pf['summary_for_identity']['tool_smokes']}")
    ident["route_resolution"] = {r: {"route_kind": listing["route_kind"], "resolved_model": pf["summary_for_identity"]["resolved_model"],
                                     "evidence": ev} for r in ep.ROLES}
    ident["provider_preflight"] = pf["summary_for_identity"]
    ident = {k: ident[k] for k in like["identity"]}
    diff = [k for k in ident if ident[k] != like["identity"][k]]

    rec = {"profile": a.name, "profile_id": ep.profile_id(ident), "status": "UNDER_QUALIFICATION", "identity": ident,
           "owner_decision": "STOP PROFILE HUNTING, FIX W1 PLAN + TDD PROOF POLICY (2026-09-20), sections 14 and 20",
           "workload": {"plan": "W1-LEDGERLOCK-PLAN-V2", "plan_base_commit": a.plan_base},
           "defined_from": "a rehearsal copy prepared exactly like a run copy (prepare_run_copy.sh + PROFILE at the "
                           "plan-V2 base, `aisef compile` with the frozen wheel) that never ran, measured with the profile's PATH",
           f"differs_from_{Path(a.like).stem}_in": diff,
           "oracle": like["oracle"],
           "provider_preflight_attempts": [{"file": out.name, "result": f"PASS — {pf['summary_for_identity']['chat_probes']} chat probes, "
                                            f"{pf['summary_for_identity']['tool_smokes']} tool smokes, reviewer read-only environment clean"}],
           "run_rule": like["run_rule"]}
    dest = ROOT / f"closure-evidence/hardening/w1/profiles/{a.name}.json"
    dest.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    check = ep.verify(rec, copy_dir, venv, ROOT / "closure-evidence/hardening/P19-FREEZE.json", path)
    print(json.dumps({"profile": a.name, "profile_id": rec["profile_id"], "differs_in": diff,
                      "rehearsal_verifies": check["matches"], "differences": check["differences"]}, ensure_ascii=False))
    return 0 if check["matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
