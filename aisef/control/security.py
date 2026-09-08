"""Rà soát bảo mật theo ngữ nghĩa — phân loại và lọc nhiễu.

Dò khuôn mẫu trả lời được "có chuỗi nào trông giống lỗ hổng không"; câu
cần trả lời là "dữ liệu người dùng đi tới đâu, và ở đó có ai kiểm
không". Câu sau cần phán đoán, nên nó giao cho model — nhưng **việc chấm
đạt/không đạt thì không**: ngưỡng là code, đọc từ cấu hình.

Phần lọc nhiễu mượn ý từ `claude-code-security-review` của Anthropic:
loại hẳn vài nhóm gây nhiễu nhiều hơn giúp. Báo một mục không khai thác
được tốn đúng bằng bỏ sót một mục thật — lần sau không ai đọc báo cáo
nữa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Thứ tự nghiêm dần. Dùng cho cả sắp xếp lẫn so ngưỡng.
SEVERITIES = ("low", "medium", "high", "critical")

#: Mức chặn story mặc định. Trùng với `security.block_severities` trong
#: cấu hình; để ở đây để module đứng một mình vẫn có nghĩa.
DEFAULT_BLOCKING = ("critical", "high")

_LINE = re.compile(
    r"^\s*[-*•]?\s*\[(?P<sev>critical|high|medium|low)\]\s*(?P<body>.+)$",
    re.IGNORECASE,
)

#: Nhóm loại hẳn khỏi báo cáo. Mượn từ `claude-code-security-review`:
#: chúng gần như luôn là nhiễu trên diff của một story, và một báo cáo
#: nhiễu thì không ai đọc.
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
    #: Mục bị lọc bỏ vì thuộc nhóm nhiễu. Giữ lại để đếm được — lọc mà
    #: không nói đã lọc gì thì không ai kiểm lại được bộ lọc.
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
        chan = self.blocking(severities)
        dem = ", ".join(f"{s}={n}" for s, n in self.counts.items() if n)
        head = "security: " + ("FAIL" if chan else "pass")
        if dem:
            head += f" ({dem})"
        if self.filtered:
            head += f" · {len(self.filtered)} items filtered as noise"
        lines = [head] + [f"  ✗ {f.line()}" for f in chan[:5]]
        return "\n".join(lines)


def is_noise(text: str) -> bool:
    low = text.lower()
    return any(any(m in low for m in nhom) for nhom in NOISE)


def parse(text: str) -> SecurityReport:
    """Đọc báo cáo của người rà soát bảo mật.

    Không chấm được thì nói **không chấm được**, đừng trả rỗng: rỗng đọc
    ra là "không có lỗ hổng", và đó là kết luận ngược hẳn.
    """
    rep = SecurityReport()
    if text is None:
        rep.error = "no results"
        return rep

    sach = text.strip()
    if not sach:
        rep.error = "empty results"
        return rep

    for raw in sach.splitlines():
        m = _LINE.match(raw)
        if not m:
            continue
        f = Finding(m.group("sev").lower(), m.group("body").strip())
        (rep.filtered if is_noise(f.text) else rep.findings).append(f)

    rep.findings.sort(key=lambda f: -f.rank)
    if not rep.findings and not rep.filtered:
        # Không mục nào **và** không câu "không có phát hiện" nghĩa là báo
        # cáo sai định dạng — khác hẳn với "đã rà, sạch".
        if "no findings" not in sach.lower() and "không có phát hiện" not in sach.lower():
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
