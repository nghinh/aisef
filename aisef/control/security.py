"""Semantic security review — classification and noise filtering.

Pattern matching answers "does any string look like a vulnerability"; the real
question is "where does user data flow, and is it validated there". The latter
requires judgment, so it is delegated to a model — but **the pass/fail decision
is not**: the threshold is code, read from configuration.

Noise filtering borrows from Anthropic's `claude-code-security-review`:
drop entire categories that produce more noise than signal. Reporting a
non-exploitable finding costs exactly as much as missing a real one — next
time nobody reads the report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Ascending severity order. Used for both sorting and threshold comparison.
SEVERITIES = ("low", "medium", "high", "critical")

#: Default blocking severities for a story. Matches `security.block_severities`
#: in config; kept here so the module is self-contained.
DEFAULT_BLOCKING = ("critical", "high")

_LINE = re.compile(
    r"^\s*(?:[-*•]|\d+[.):]?)?\s*\[(?P<sev>critical|high|medium|low)\]\s*(?P<body>.+)$",
    re.IGNORECASE,
)

#: Categories dropped entirely from the report. Borrowed from
#: `claude-code-security-review`: these are almost always noise on a
#: story-sized diff, and a noisy report goes unread.
NOISE = (
    ("từ chối dịch vụ", "denial of service", "dos ", "cạn bộ nhớ",
     "cạn cpu", "resource exhaustion"),
    ("giới hạn tần suất", "rate limit", "rate-limit", "throttl"),
    ("chuyển hướng mở", "open redirect"),
)


@dataclass(frozen=True)
class Finding:
    severity: str
    text: str

    @property
    def rank(self) -> int:
        return SEVERITIES.index(self.severity) if self.severity in SEVERITIES else -1

    def line(self) -> str:
        return f"[{self.severity}] {self.text}"


@dataclass
class SecurityReport:
    findings: list[Finding] = field(default_factory=list)
    #: Findings dropped as noise. Kept for counting — filtering without
    #: disclosing what was filtered makes the filter itself unauditable.
    filtered: list[Finding] = field(default_factory=list)
    error: str = ""

    def of(self, *severities: str) -> list[Finding]:
        want = {s.lower() for s in severities}
        return [f for f in self.findings if f.severity in want]

    def blocking(self, severities=DEFAULT_BLOCKING) -> list[Finding]:
        return self.of(*severities)

    @property
    def counts(self) -> dict[str, int]:
        return {s: len(self.of(s)) for s in SEVERITIES}

    def summary(self, severities=DEFAULT_BLOCKING) -> str:
        if self.error:
            return f"security: CANNOT SCORE — {self.error}"
        blocking = self.blocking(severities)
        counts_str = ", ".join(f"{s}={n}" for s, n in self.counts.items() if n)
        head = "security: " + ("FAIL" if blocking else "pass")
        if counts_str:
            head += f" ({counts_str})"
        if self.filtered:
            head += f" · {len(self.filtered)} items filtered as noise"
        lines = [head] + [f"  ✗ {f.line()}" for f in blocking[:5]]
        return "\n".join(lines)


def is_noise(text: str) -> bool:
    low = text.lower()
    return any(any(m in low for m in group) for group in NOISE)


def parse(text: str) -> SecurityReport:
    """Parse the security reviewer's report.

    When scoring is impossible, say **cannot score** — do not return empty:
    empty reads as "no vulnerabilities", which is the opposite conclusion.
    """
    rep = SecurityReport()
    if text is None:
        rep.error = "no results"
        return rep

    clean = text.strip()
    if not clean:
        rep.error = "empty results"
        return rep

    for raw in clean.splitlines():
        m = _LINE.match(raw)
        if not m:
            continue
        f = Finding(m.group("sev").lower(), m.group("body").strip())
        (rep.filtered if is_noise(f.text) else rep.findings).append(f)

    rep.findings.sort(key=lambda f: -f.rank)
    if not rep.findings and not rep.filtered:
        # No findings **and** no "no findings" phrase means the report is
        # malformed — fundamentally different from "reviewed, clean".
        low = clean.lower()
        clean_phrases = ("no findings", "no vulnerabilit", "no security issue",
                         "no issue", "all clear", "0 findings", "clean",
                         "không có phát hiện", "không tìm thấy")
        if not any(p in low for p in clean_phrases):
            rep.error = "report does not follow the required format"
    return rep


__all__ = [
    "DEFAULT_BLOCKING",
    "NOISE",
    "SEVERITIES",
    "Finding",
    "SecurityReport",
    "is_noise",
    "parse",
]
