"""REL-GOV-01 evidence capture (read-only GitHub API snapshots). Never approves, rejects, pushes or edits anything.

    python3 -P relgov_evidence.py precheck                 # environment + policies; refuses unless protected
    python3 -P relgov_evidence.py snapshot RUN_ID OUT.json  # run, jobs, pending_deployments, approvals, timestamps
    python3 -P relgov_evidence.py check                    # self-test of the protection predicate (no network)

Requires `gh` authenticated as the repository owner. Repo fixed to nghinh/aisef.
"""
import datetime
import json
import subprocess
import sys

REPO = "nghinh/aisef"


def gh(path):
    r = subprocess.run(["gh", "api", f"repos/{REPO}/{path}"], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {"_error": r.stderr.strip()[:300]}


def problems(env, policies):
    """[] iff the pypi environment pauses for a human: >= 1 required reviewer and only tag-type deployment policies."""
    out = []
    rules = env.get("protection_rules") or []
    rev = [r for r in rules if r.get("type") == "required_reviewers" and r.get("reviewers")]
    if not rev:
        out.append("no required_reviewers rule with a reviewer")
    dbp = env.get("deployment_branch_policy") or {}
    if not dbp.get("custom_branch_policies"):
        out.append("deployments are not restricted to custom (tag) policies")
    pols = (policies or {}).get("branch_policies")
    if pols is None:
        out.append("deployment policies unreadable (fail closed)")
    elif not pols or any(p.get("type") != "tag" for p in pols):
        out.append("a deployment policy is not of type tag")
    if env.get("can_admins_bypass"):
        out.append("can_admins_bypass is true (record; owner decides)")
    return out


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def main(argv):
    if argv[:1] == ["check"]:
        good = {"protection_rules": [{"type": "required_reviewers", "reviewers": [{"type": "User"}]}],
                "deployment_branch_policy": {"custom_branch_policies": True}, "can_admins_bypass": False}
        assert problems(good, {"branch_policies": [{"type": "tag", "name": "v[0-9]*.[0-9]*.[0-9]*"}]}) == []
        assert problems({"protection_rules": []}, {"branch_policies": []})               # today's state FAILs
        assert problems(good, {"branch_policies": [{"type": "branch", "name": "*"}]})   # branch policy FAILs
        assert problems(good, None)                                                    # unreadable FAILs
        print("relgov predicate self-test: OK")
        return 0
    if argv[:1] == ["precheck"]:
        env, pols = gh("environments/pypi"), gh("environments/pypi/deployment-branch-policies")
        p = problems(env, pols)
        print(json.dumps({"at_utc": now(), "environment": env, "policies": pols, "problems": p}, indent=1))
        return 1 if [x for x in p if not x.startswith("can_admins")] else 0
    if argv[:1] == ["snapshot"] and len(argv) == 3:
        run = argv[1]
        snap = {"at_utc": now(), "run": gh(f"actions/runs/{run}"), "jobs": gh(f"actions/runs/{run}/jobs"),
                "pending_deployments": gh(f"actions/runs/{run}/pending_deployments"),
                "approvals": gh(f"actions/runs/{run}/approvals")}
        with open(argv[2], "x", encoding="utf-8") as f:
            json.dump(snap, f, indent=1)
        print(argv[2], snap["run"].get("status"), [j.get("status") for j in snap["jobs"].get("jobs", [])])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
