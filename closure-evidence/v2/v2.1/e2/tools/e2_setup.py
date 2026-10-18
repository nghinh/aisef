#!/opt/homebrew/bin/python3 -P -B
"""E2 launch kit, step 1: the campaign directory D of the REAL E2 campaign (18 runs = {w1-a, w2} x {direct, aisef, aisef+}
x reps 1..3), built offline — nothing here runs a client or reaches a provider. Run from any directory, python 3.14:

    python3 -P -B e2_setup.py D [--approver human:NAME] [--settings-dir DIR]   # D is new, and never inside the repository
    python3 -P -B e2_setup.py D --adopt-owner                                   # the owner's APPROVE.sh files replace approved/

D/base/<workload>                  the baseline init_repo.sh builds; its commit must be the one the bundles name (plan.baseline)
D/approved/<w>-{arms,evaluator}.json   the four bundles approved: the OWNER's `<lane>/{arms,evaluator|hidden}/approved.json`
                                   when APPROVE.sh has written it, else a PROVISIONAL technical approval by --approver
                                   (default human:orchestrator-provisional; the kernel accepts `human:<name>` only,
                                   aisef2/product/approval.py). D/APPROVALS.md says which, per bundle.
D/settings/arm-*.json              copies of --settings-dir (default ../settings: endpoint https://9router.vnteki.com/v1,
                                   route 9router/mycombo, no prices; the offline test passes ../dry-run/settings-offline)
D/client/config/opencode/opencode.json   XDG_CONFIG_HOME of the run: provider <settings provider.name> at the settings'
                                   endpoint, apiKey `{env:<settings api_key_env>}` — the shape of
                                   ../preflight-mycombo/tools/xdg-opencode.json, never a key's value
D/client/{data,state,cache}, D/home, D/tmp   XDG_DATA_HOME/STATE/CACHE, HOME and TMPDIR of the hermetic run (e2_launch.py):
                                   the operator's own OpenCode store and configuration are never read or written
D/CAMPAIGN-real.json               the 18 runs, rep-major (every arm of rep 1, then rep 2, then rep 3), run_id
                                   <workload>-r<rep>-<arm>, every path relative to D (D can be moved as a whole)
D/SETUP.json, D/APPROVALS.md       the record of this step"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent          # .../e2/tools
E2 = HERE.parent
ROOT = E2.parents[3]                                    # closure-evidence/v2/v2.1/e2 -> the AISEF repository root
sys.path.insert(0, str(ROOT))

PROVISIONAL = "human:orchestrator-provisional"
ARMS = (("direct", "arm-direct"), ("aisef", "arm-aisef"), ("aisef+", "arm-aisef-plus"))
REPS = (1, 2, 3)
WORKLOADS = {
    "w1-a": {"init": ["sh", "init_repo.sh"], "arms": "arms/bundle.json", "evaluator": "evaluator/bundle.json",
             "requirements": "docs/requirements.md", "task": "direct-task.txt"},
    "w2": {"init": ["zsh", "init_repo.sh"], "arms": "arms/bundle.json", "evaluator": "hidden/evaluator.json",
           "requirements": "docs/requirements-delta.md", "task": "baseline/TASK.txt"},
}


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p: pathlib.Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def write(p: pathlib.Path, doc) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def git(repo, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S %z")


def same_contracts(a: dict, b: dict, what: str) -> None:
    """Two bundles are the same contracts and requirements (ids and hashes); approvals may differ."""
    for key, hk in (("contracts", "contract_hash"), ("requirements", "requirement_hash")):
        if {(x["id"], x[hk]) for x in a[key]} != {(x["id"], x[hk]) for x in b[key]}:
            raise SystemExit(f"refused: {what}: the {key} differ (ids or hashes) — not the same bundle")


def owner_file(wid: str, kind: str) -> pathlib.Path:
    return (E2 / wid / WORKLOADS[wid][kind]).parent / "approved.json"


def approved_copy(wid: str, kind: str, dst: pathlib.Path, approver: str) -> dict:
    from aisef2.app import bundle_cli
    src, owner = E2 / wid / WORKLOADS[wid][kind], owner_file(wid, kind)
    doc = read(src)
    if owner.exists():
        got = read(owner)
        same_contracts(doc, got, f"{owner} vs {src}")
        doc, status = got, "owner"
        approvers = sorted({a["approver"] for a in doc["approvals"]})
    else:
        for c in doc["contracts"]:
            doc = bundle_cli.approve(doc, c["id"], approver, time.time())
        status, approvers = "provisional", [approver]
    write(dst, doc)
    lint = bundle_cli.lint(doc)
    adm = lint.get("admission")
    return {"source": str(src.relative_to(ROOT)), "source_sha256": sha(src), "approved": str(dst), "approved_sha256": sha(dst),
            "contracts": len(doc["contracts"]), "status": status, "approvers": approvers,
            "owner_file": str(owner.relative_to(ROOT)) if owner.exists() else None,
            "lint_verdict": lint["verdict"], "admitted": adm.get("admitted") if isinstance(adm, dict) else adm}


def approvals_md(rec: dict) -> str:
    rows = "\n".join(f"| {k} | {v['status']} | {', '.join(v['approvers'])} | {v['contracts']} | {v['lint_verdict']} | "
                     f"`{v['approved_sha256'][:16]}` | {v['owner_file'] or '-'} |" for k, v in rec["approved"].items())
    return f"""# Approvals in this campaign directory — {rec['at']}

| bundle | status | approver(s) | contracts | lint | sha256 | owner's file |
|---|---|---|---|---|---|---|
{rows}

`provisional` = a TECHNICAL approval by `{rec['approver']}` so that the kernel can compile the contracts and the
evaluation can run (aisef2/product/approval.py accepts `human:<name>` only). It is NOT the owner's acceptance of any
contract; nothing in this directory records owner acceptance. `owner` = the file APPROVE.sh wrote in the workload's
lane directory was adopted as it is (its contracts and requirements checked identical to the sealed bundle).

How the owner's approval replaces a provisional one:

1. The owner runs the lane's APPROVE.sh (`closure-evidence/v2/v2.1/e2/w1-a/APPROVE.sh human:<name>`,
   `.../e2/w2/APPROVE.sh human:<name>`): one `aisef bundle approve` per contract, written beside each bundle.
2. `python3 -P -B e2_setup.py {rec['dir']} --adopt-owner` — BEFORE the first run_e2.sh or AFTER the last run, never
   in between (refused while the campaign is partial: the first launch seals all manifests, binding the provisional
   files' sha256, and later arms must run on exactly the files their manifests name) — checks each owner file holds
   the same contracts and requirements, keeps the provisional copies under `approved/provisional/`, replaces
   `approved/*.json`, and appends to this file.
3. `python3 -P -B validation/experiments/campaign.py replay --out {rec['dir']}/out` evaluates every recorded
   candidate again under the owner-approved evaluator (RESULT.json's evaluator_path is the replaced file). Nothing
   printed = every result replays.

What adoption cannot change: runs already made used the provisional copies (their sealed MANIFEST.json binds those
files' sha256 under `bundle` and `evaluator`). For the owner's approval to bind the runs themselves, adopt before
launching — e2_setup.py uses the owner's files on its own when they exist at setup time.
"""


def adopt_owner(d: pathlib.Path) -> None:
    from aisef2.app import bundle_cli
    rec = read(d / "SETUP.json")
    # the driver seals every manifest at the first launch and reuses them (bundle/evaluator sha256 bound then):
    # adopting mid-campaign would make later arms run on files their manifests do not name. Before the first
    # launch or after the last result only.
    total, done = rec["campaign"]["runs"], len(list((d / "out").glob("*/RESULT.json"))) if (d / "out").exists() else 0
    if 0 < done < total:
        raise SystemExit(f"refused: the campaign is partial ({done} of {total} results) — adopt the owner's approvals "
                         f"before the first launch or after the last run (then `campaign.py replay`); nothing replaced")
    lines = [f"\n## Owner's approvals adopted — {now()} ({'before any run' if done == 0 else f'after all {done} runs'})\n"]
    keep = d / "approved" / "provisional"
    for name in rec["approved"]:                          # every check before any replacement
        wid, kind = name.rsplit("-", 1)
        owner, cur = owner_file(wid, kind), d / "approved" / f"{name}.json"
        if not owner.exists():
            raise SystemExit(f"refused: {owner} does not exist (APPROVE.sh of {wid} not run); nothing replaced")
        same_contracts(read(cur), read(owner), f"{owner} vs {cur}")
        if bundle_cli.lint(read(owner))["verdict"] != "READY":
            raise SystemExit(f"refused: {owner} lints NOT_READY; nothing replaced")
    for name in rec["approved"]:
        wid, kind = name.rsplit("-", 1)
        owner, cur = owner_file(wid, kind), d / "approved" / f"{name}.json"
        before = sha(cur)
        keep.mkdir(exist_ok=True)
        if not (keep / f"{name}.json").exists():
            shutil.copyfile(cur, keep / f"{name}.json")
        shutil.copyfile(owner, cur)
        who = sorted({a["approver"] for a in read(cur)["approvals"]})
        lines.append(f"- {name}: `{before[:16]}` -> `{sha(cur)[:16]}` from {owner.relative_to(ROOT)} (approvers {', '.join(who)}); "
                     f"the replaced copy is kept at approved/provisional/{name}.json")
        print(lines[-1])
    with (d / "APPROVALS.md").open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"now: python3 -P -B {ROOT}/validation/experiments/campaign.py replay --out {d / 'out'}")


def setup(d: pathlib.Path, approver: str, settings_dir: pathlib.Path) -> None:
    from aisef2.app import settings as S
    if d.exists():
        raise SystemExit(f"refused: {d} exists — setup wants a new directory")
    if d.is_relative_to(ROOT):
        raise SystemExit(f"refused: {d} is inside the repository {ROOT} — a campaign directory lives outside it")
    if not approver.startswith("human:") or not approver[6:].strip():
        raise SystemExit(f"refused: the approver is human:<name> (the kernel's rule), got {approver!r}")
    sts = {name: read(settings_dir / f"{name}.json") for _, name in ARMS}
    for st in sts.values():
        S.load(st)                                       # the kernel's own validation of each settings file
    prov = {(st["provider"]["name"], st["provider"]["endpoint"], st["provider"]["api_key_env"]) for st in sts.values()}
    if len(prov) != 1:
        raise SystemExit(f"refused: the three settings files name different providers/endpoints/key variables: {sorted(prov)}")
    provider, endpoint, key_env = prov.pop()
    for sub in ("base", "approved", "settings", "client/config/opencode", "client/data", "client/state", "client/cache", "home", "tmp"):
        (d / sub).mkdir(parents=True)
    rec: dict = {"at": now(), "dir": str(d), "aisef_head": git(ROOT, "rev-parse", "HEAD"), "approver": approver,
                 "settings_dir": str(settings_dir), "settings": {}, "baselines": {}, "approved": {}}
    for name in sts:
        shutil.copyfile(settings_dir / f"{name}.json", d / "settings" / f"{name}.json")
        rec["settings"][name] = sha(d / "settings" / f"{name}.json")
    runs = []
    for wid, w in WORKLOADS.items():
        dest = d / "base" / wid
        subprocess.run([*w["init"], str(dest)], cwd=str(E2 / wid), check=True, capture_output=True)
        commit = git(dest, "rev-parse", "HEAD")
        named = {k: (read(E2 / wid / w[k]).get("plan") or {}).get("baseline") for k in ("arms", "evaluator")}
        if named["arms"] != commit or named["evaluator"] not in (None, commit) or git(dest, "status", "--porcelain"):
            raise SystemExit(f"{wid}: init_repo.sh gave {commit}; the bundles name {named}; or the tree is dirty")
        rec["baselines"][wid] = {"repo": str(dest), "commit": commit, "tree": git(dest, "rev-parse", "HEAD^{tree}"), "named_by_bundles": named}
        for kind in ("arms", "evaluator"):
            rec["approved"][f"{wid}-{kind}"] = approved_copy(wid, kind, d / "approved" / f"{wid}-{kind}.json", approver)
        task = (E2 / wid / w["task"]).read_text(encoding="utf-8").rstrip("\n")
        for rep in REPS:
            for arm, name in ARMS:
                runs.append({"run_id": f"{wid}-r{rep}-{name[4:]}", "arm": arm, "rep": rep,
                             "workload": {"id": wid, "repo": f"base/{wid}", "commit": commit,
                                          "requirements_path": w["requirements"], "task_text": task},
                             "settings_path": f"settings/{name}.json", "bundle_path": f"approved/{wid}-arms.json",
                             "evaluator_path": f"approved/{wid}-evaluator.json"})
    runs.sort(key=lambda r: r["rep"])                    # rep-major; stable: w1-a before w2, arms in ARMS order
    write(d / "CAMPAIGN-real.json", {"runs": runs})
    write(d / "client" / "config" / "opencode" / "opencode.json",
          {"provider": {provider: {"options": {"baseURL": endpoint, "apiKey": f"{{env:{key_env}}}"}}}})
    rec.update(provider=provider, endpoint=endpoint, api_key_env=key_env,
               client_config=str(d / "client" / "config" / "opencode" / "opencode.json"),
               campaign={"path": str(d / "CAMPAIGN-real.json"), "sha256": sha(d / "CAMPAIGN-real.json"), "runs": len(runs),
                         "order": [r["run_id"] for r in runs]})
    write(d / "SETUP.json", rec)
    (d / "APPROVALS.md").write_text(approvals_md(rec), encoding="utf-8")
    print(json.dumps({k: rec[k] for k in ("at", "aisef_head", "provider", "endpoint", "api_key_env", "baselines")}, indent=1))
    for k, v in rec["approved"].items():
        print(f"approved {k}: {v['contracts']} contracts, {v['status']} by {', '.join(v['approvers'])}, lint {v['lint_verdict']}, admitted {v['admitted']}")
    print(f"campaign: {len(runs)} runs -> {d / 'CAMPAIGN-real.json'}; first {runs[0]['run_id']}, last {runs[-1]['run_id']}")


def main(argv: list[str]) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("dir")
    p.add_argument("--approver", default=PROVISIONAL)
    p.add_argument("--settings-dir", default=str(E2 / "settings"))
    p.add_argument("--adopt-owner", action="store_true")
    a = p.parse_args(argv)
    d = pathlib.Path(a.dir).resolve()
    if a.adopt_owner:
        adopt_owner(d)
    else:
        setup(d, a.approver, pathlib.Path(a.settings_dir).resolve())


if __name__ == "__main__":
    main(sys.argv[1:])
