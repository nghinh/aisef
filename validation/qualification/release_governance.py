"""REL-GOV-01 (docs/v2.3/W1-DESIGN.md §5; CODE-AUDIT #1): a production publish waits for a human.

The control is a repository setting, not YAML: the `pypi` deployment environment that release.yml's `publish` job
targets must have a Required reviewer, and its deployments must be restricted to tag policies. This guard reads that
setting with GET requests only and fails closed; release.yml's `governance` job runs it, and `publish` cannot start
unless it passed (tests/v23/test_v23_release_governance.py pins the dependency):

    GITHUB_REPOSITORY=<owner>/<repo> GITHUB_TOKEN=<token> python -P validation/qualification/release_governance.py

Exit 0 only when `problems()` is empty; the JSON report also states `can_admins_bypass` and `prevent_self_review`
(reported, not judged: the owner decides them). It FAILs truthfully until the owner configures `pypi`. The guard is
detective, at tag time; the pause itself is GitHub's, observed by the owner's tag-push probe (W1) and on the real
release tag (W6). It never changes a setting and never approves or rejects a deployment.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ENV = "pypi"
API = "https://api.github.com"


def problems(env: dict | None, policies: dict | None) -> list[str]:
    """[] iff `pypi` pauses for a human: a required_reviewers rule with >= 1 reviewer, deployments restricted to custom
    policies, and every policy (GET .../deployment-branch-policies, None = unreadable) of type tag."""
    if not isinstance(env, dict):
        return [f"environment {ENV} unreadable (fail closed)"]
    out = []
    rules = env.get("protection_rules") or []
    if not any(isinstance(r, dict) and r.get("type") == "required_reviewers" and r.get("reviewers") for r in rules):
        out.append("no required_reviewers rule with a reviewer: the publish job never waits for a human")
    if (env.get("deployment_branch_policy") or {}).get("custom_branch_policies") is not True:
        out.append("deployments are not restricted to custom (tag) policies")
    listed = policies.get("branch_policies") if isinstance(policies, dict) else None
    if not isinstance(listed, list):
        out.append("deployment policies unreadable (fail closed): the tag restriction cannot be read here")
    elif not listed:
        out.append("no deployment policy")
    else:
        bad = [p.get("name") if isinstance(p, dict) else p for p in listed if not isinstance(p, dict) or p.get("type") != "tag"]
        if bad:
            out.append(f"deployment policies not of type tag: {bad}")
        if policies.get("total_count") != len(listed):
            out.append(f"deployment policies listed {len(listed)} of {policies.get('total_count')} (fail closed)")
    return out


def report(env: dict | None, policies: dict | None) -> dict:
    found = problems(env, policies)
    env = env if isinstance(env, dict) else {}
    rules = [r for r in env.get("protection_rules") or [] if isinstance(r, dict) and r.get("type") == "required_reviewers"]
    listed = policies.get("branch_policies") if isinstance(policies, dict) else None
    return {"environment": ENV, "verdict": "FAIL" if found else "PASS", "problems": found,
            "reviewers": sum(len(r.get("reviewers") or []) for r in rules),   # a count: no identity in a public log
            "prevent_self_review": [r.get("prevent_self_review") for r in rules],
            "can_admins_bypass": env.get("can_admins_bypass"),
            "policies": [{"name": p.get("name"), "type": p.get("type")} for p in listed or [] if isinstance(p, dict)]}


def _get(url: str, token: str | None) -> dict | None:
    """One GET; None on any failure (the caller fails closed)."""
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers, method="GET"), timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"unreadable: {url}: {e}", file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if repo.count("/") != 1:
        print("GITHUB_REPOSITORY=<owner>/<repo> is required", file=sys.stderr)
        return 2
    token = os.environ.get("GITHUB_TOKEN")
    base = f"{API}/repos/{repo}/environments/{ENV}"
    doc = report(_get(base, token), _get(f"{base}/deployment-branch-policies?per_page=100", token))
    print(json.dumps(doc, indent=1))
    print(f"REL-GOV-01 release governance: {doc['verdict']}")
    return 0 if doc["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
