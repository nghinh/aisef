"""Lọc kho cybersecurity-skills xuống phần dùng được cho SDLC.

Kho `references/cybersecurity-skills` có 818 skill trải 45 subdomain, phần lớn
phục vụ SOC, forensics, ICS, red team — không liên quan việc xây phần mềm.
Nạp cả kho vào một dự án vừa vô ích vừa nguy hiểm.

Bộ lọc chia ba nhóm:

* ``KEEP``          — phục vụ xây phần mềm an toàn, cài mặc định.
* ``OFFENSIVE``     — tấn công / lưỡng dụng. **Không bao giờ cài mặc định.**
                      Theo ADR: chỉ bật khi có Security Agent, uỷ quyền tường
                      minh và sandbox.
* ``OUT_OF_SCOPE``  — an ninh chính đáng nhưng không thuộc vòng đời phát triển.

Phân loại dựa vào metadata thật trong frontmatter (``subdomain``, ``tags``) và
động từ mở đầu tên skill — kho này đặt tên rất nhất quán theo động từ.
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


#: Subdomain phục vụ trực tiếp việc xây phần mềm.
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

#: Subdomain thuần tấn công.
OFFENSIVE_SUBDOMAINS = frozenset({
    "red-teaming",
    "red-team",
    "offensive-security",
    "penetration-testing",
    "purple-team",
})

#: Động từ mở đầu thể hiện hành vi tấn công.
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

#: Động từ quan sát/phòng thủ. Vô hiệu hoá các từ khoá tấn công "mềm" —
#: "detecting-attacks-on-scada" và "auditing-rbac-privilege-escalation" đều là
#: phòng thủ, dù tên chứa "attack" / "privilege-escalation".
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

#: Từ khoá chỉ đích danh hạ tầng tấn công. Chặn **bất kể** động từ — một skill
#: "audit" bằng bộ công cụ C2 vẫn là năng lực tấn công.
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

#: Từ khoá mô tả *kỹ thuật* tấn công. Chỉ chặn khi khung hành động không phải
#: phòng thủ — audit hay phát hiện kỹ thuật đó là việc chính đáng.
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
    """Xếp một skill vào một trong ba nhóm.

    Thứ tự kiểm tra có chủ đích: động từ phòng thủ được xét trước để một skill
    *phát hiện* tấn công không bị nhầm thành skill *thực hiện* tấn công.
    Ngoài ra luôn kiểm tra tấn công trước phạm vi, nên một skill tấn công nằm
    trong subdomain hợp lệ (ví dụ tiêm SQL trong ``web-application-security``)
    vẫn bị chặn.
    """
    sub = skill.subdomain.strip().lower()
    verb = skill.verb
    haystack = f"{skill.name} {' '.join(skill.tags)}".lower()

    if sub in OFFENSIVE_SUBDOMAINS:
        return Classification(skill, Verdict.OFFENSIVE, f"subdomain tấn công: {sub}")

    if verb in OFFENSIVE_VERBS:
        return Classification(skill, Verdict.OFFENSIVE, f"động từ tấn công: {verb}")

    hard = next((m for m in HARD_OFFENSIVE_MARKERS if m in haystack), None)
    if hard:
        return Classification(skill, Verdict.OFFENSIVE, f"hạ tầng tấn công: {hard}")

    if verb not in DEFENSIVE_VERBS:
        soft = next((m for m in SOFT_OFFENSIVE_MARKERS if m in haystack), None)
        if soft:
            return Classification(skill, Verdict.OFFENSIVE, f"kỹ thuật tấn công: {soft}")

    if sub in IN_SCOPE_SUBDOMAINS:
        return Classification(skill, Verdict.KEEP, f"subdomain thuộc SDLC: {sub}")

    return Classification(skill, Verdict.OUT_OF_SCOPE, f"ngoài phạm vi SDLC: {sub or 'không rõ'}")


def classify_all(root: Path) -> list[Classification]:
    """Đọc và phân loại toàn bộ skill dưới `root`."""
    return [classify(s) for s in scan(root)]


def summarize(results: list[Classification]) -> dict[str, int]:
    counts = {v.value: 0 for v in Verdict}
    for r in results:
        counts[r.verdict.value] += 1
    return counts
