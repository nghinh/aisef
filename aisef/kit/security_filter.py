"""Filter the cybersecurity-skills repo down to the SDLC-relevant subset.

The `references/cybersecurity-skills` repo has 818 skills across 45 subdomains,
most serving SOC, forensics, ICS, red team — unrelated to building software.
Loading the entire repo into a project is both useless and dangerous.

The filter classifies into three groups:

* ``KEEP``          — serves secure software development, installed by default.
* ``OFFENSIVE``     — attack / dual-use. **Never installed by default.**
                      Per ADR: enabled only with a Security Agent, explicit
                      authorization, and sandbox.
* ``OUT_OF_SCOPE``  — legitimate security but outside the development lifecycle.

Classification is based on real metadata in frontmatter (``subdomain``, ``tags``)
and the leading verb of the skill name — this repo names skills very consistently
by verb.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .skills import Skill, scan


class Verdict(str, Enum):
    KEEP = "keep"
    OFFENSIVE = "offensive"
    OUT_OF_SCOPE = "out_of_scope"


#: Subdomains that directly serve software development.
IN_SCOPE_SUBDOMAINS = frozenset({
    "application-security",
    "web-application-security",
    "api-security",
    "devsecops",
    "container-security",
    "supply-chain-security",
    "cryptography",
    "vulnerability-management",
    "identity-access-management",
    "identity-and-access-management",
    "identity-security",
    "zero-trust-architecture",
    "zero-trust",
    "compliance-governance",
    "governance-risk-compliance",
    "privacy-compliance",
    "data-protection",
    "ai-security",
    "mobile-security",
    "cloud-security",
})

#: Purely offensive subdomains.
OFFENSIVE_SUBDOMAINS = frozenset({
    "red-teaming",
    "red-team",
    "offensive-security",
    "penetration-testing",
    "purple-team",
})

#: Leading verbs indicating offensive behavior.
OFFENSIVE_VERBS = frozenset({
    "exploiting",
    "abusing",
    "bypassing",
    "attacking",
    "cracking",
    "evading",
    "hijacking",
    "escalating",
    "pivoting",
    "post",  # post-exploiting-*
})

#: Observation/defensive verbs. Neutralize "soft" offensive keywords —
#: "detecting-attacks-on-scada" and "auditing-rbac-privilege-escalation" are both
#: defensive, even though their names contain "attack" / "privilege-escalation".
DEFENSIVE_VERBS = frozenset({
    "detecting",
    "hunting",
    "analyzing",
    "monitoring",
    "triaging",
    "investigating",
    "auditing",
    "securing",
    "hardening",
    "verifying",
    "scanning",
    "prioritizing",
    "remediating",
    "patching",
    "reverse",
    "collecting",
    "extracting",
})

#: Keywords naming offensive infrastructure explicitly. Blocked **regardless** of
#: verb — an "audit" skill using a C2 toolkit is still an offensive capability.
HARD_OFFENSIVE_MARKERS = frozenset({
    "c2",
    "command-and-control",
    "backdoor",
    "keylogger",
    "adversary-simulation",
    "lateral-movement",
    "aadinternals",
    "mimikatz",
    "cobalt-strike",
})

#: Keywords describing offensive *techniques*. Blocked only when the action frame
#: is not defensive — auditing or detecting these techniques is legitimate work.
SOFT_OFFENSIVE_MARKERS = frozenset({
    "attack",
    "exploit",
    "spoofing",
    "bypass",
    "cracking",
    "evasion",
    "privilege-escalation",
    "privesc",
    "credential-access",
    "phishing-payload",
})


@dataclass(frozen=True)
class Classification:
    skill: Skill
    verdict: Verdict
    reason: str


def classify(skill: Skill) -> Classification:
    """Classify one skill into one of three groups.

    Check order is deliberate: defensive verbs are evaluated first so a skill
    that *detects* an attack isn't mistaken for one that *performs* it.
    Additionally, offensive checks always precede scope checks, so an offensive
    skill in a valid subdomain (e.g. SQL injection under
    ``web-application-security``) is still blocked.
    """
    sub = skill.subdomain.strip().lower()
    verb = skill.verb
    haystack = f"{skill.name} {' '.join(skill.tags)}".lower()

    if sub in OFFENSIVE_SUBDOMAINS:
        return Classification(skill, Verdict.OFFENSIVE, f"offensive subdomain: {sub}")

    if verb in OFFENSIVE_VERBS:
        return Classification(skill, Verdict.OFFENSIVE, f"offensive verb: {verb}")

    hard = next((m for m in HARD_OFFENSIVE_MARKERS if m in haystack), None)
    if hard:
        return Classification(skill, Verdict.OFFENSIVE, f"offensive infrastructure: {hard}")

    if verb not in DEFENSIVE_VERBS:
        soft = next((m for m in SOFT_OFFENSIVE_MARKERS if m in haystack), None)
        if soft:
            return Classification(skill, Verdict.OFFENSIVE, f"offensive technique: {soft}")

    if sub in IN_SCOPE_SUBDOMAINS:
        return Classification(skill, Verdict.KEEP, f"SDLC subdomain: {sub}")

    return Classification(skill, Verdict.OUT_OF_SCOPE, f"outside SDLC scope: {sub or 'unknown'}")


def classify_all(root: Path) -> list[Classification]:
    """Read and classify all skills under `root`."""
    return [classify(s) for s in scan(root)]


def summarize(results: list[Classification]) -> dict[str, int]:
    counts = {v.value: 0 for v in Verdict}
    for r in results:
        counts[r.verdict.value] += 1
    return counts


# ------------------------------------------------------------------ tier 2

#: Subdomains needed regardless of the project's stack — all software has
#: dependencies, secrets, and vulnerabilities to manage.
ALWAYS_RELEVANT = frozenset({
    "devsecops",
    "supply-chain-security",
    "vulnerability-management",
    "cryptography",
    "application-security",
    "compliance-governance",
    "governance-risk-compliance",
})

#: Which technology implies which subdomains.
STACK_SUBDOMAINS: dict[str, frozenset[str]] = {
    # any backend exposes an API
    "backend:*": frozenset({"api-security", "web-application-security"}),
    "frontend:*": frozenset({"web-application-security"}),
    "mobile:*": frozenset({"mobile-security"}),
    "database:*": frozenset({"data-protection", "privacy-compliance"}),
    "deploy:docker": frozenset({"container-security"}),
    "deploy:kubernetes": frozenset({"container-security", "zero-trust-architecture"}),
    "deploy:aws": frozenset({"cloud-security"}),
    "deploy:gcp": frozenset({"cloud-security"}),
    "deploy:azure": frozenset({"cloud-security"}),
    "deploy:serverless": frozenset({"cloud-security"}),
}

#: User authentication present implies identity-management subdomains needed.
AUTH_SUBDOMAINS = frozenset({
    "identity-access-management",
    "identity-and-access-management",
    "identity-security",
})

#: Keywords indicating the project has authentication.
AUTH_MARKERS = ("auth", "login", "đăng nhập", "tài khoản", "oauth", "jwt", "sso", "phân quyền")


def subdomains_for_stack(stack_dict: dict[str, list[str]], *, requirements_text: str = "") -> set[str]:
    """Set of subdomains needed for a specific project.

    `stack_dict` is the result of `detect_stack.Stack.as_dict()`.
    """
    wanted = set(ALWAYS_RELEVANT)

    for category, values in stack_dict.items():
        if category == "undetermined" or not values:
            continue
        wanted |= STACK_SUBDOMAINS.get(f"{category}:*", frozenset())
        for value in values:
            wanted |= STACK_SUBDOMAINS.get(f"{category}:{value}", frozenset())

    lowered = requirements_text.lower()
    if any(m in lowered for m in AUTH_MARKERS):
        wanted |= AUTH_SUBDOMAINS

    return wanted


def select_for_stack(
    results: list[Classification],
    stack_dict: dict[str, list[str]],
    *,
    requirements_text: str = "",
) -> list[Classification]:
    """Tier 2 filter: from the set that passed tier 1, keep what fits the project.

    Only considers ``KEEP`` skills — offensive skills are never included,
    regardless of the stack.
    """
    wanted = subdomains_for_stack(stack_dict, requirements_text=requirements_text)
    return [
        r
        for r in results
        if r.verdict is Verdict.KEEP and r.skill.subdomain.strip().lower() in wanted
    ]
