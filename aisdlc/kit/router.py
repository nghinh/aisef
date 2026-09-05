"""Định tuyến skill cho một story — phía harness, có ngưỡng, biết từ chối.

Bằng chứng buộc phải có nó (ADR-002 §1): e9 cài 156 skill, 86 phiên Claude,
tool `Skill` được gọi 11 lần cho đúng 4 skill — tất cả đều được prompt của
harness gọi **đích danh**. Cài theo stack không sinh ra sử dụng; prompt nêu
tên mới sinh ra. Vậy chọn skill là việc của harness, không phải cơ chế khám
phá của client trên 156 mô tả.

Chọn là **phán đoán có cấu trúc**: tín hiệu có cấu trúc (hợp đồng kiểm
định, năng lực story cần, màn hình, pha) cho điểm tất định; câu chữ tiêu
chí chấp nhận chỉ là tín hiệu yếu. Không đủ điểm thì **abstain** — paper
ghi 2/20 task hỏng vì skill nhồi nhầm làm agent lạc khỏi chiến lược riêng.

Router là tín hiệu cho agent, không phải cổng: chọn sai không chặn story;
nó lộ ra ở telemetry (`skills_offered` so với `skills_used`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..control.normalize import Story
from ..control.preflight import required_capabilities, verification_contract
from .registry import Registry, SkillEntry

#: Ngưỡng và trần — knob **có mã đọc** (config `skills.route_threshold`,
#: `skills.route_max`); điều chỉnh theo precision đo được.
DEFAULT_THRESHOLD = 3
DEFAULT_MAX = 3

#: Trọng số. Có cấu trúc trước, câu chữ sau.
W_CONTRACT = 3      # loại kiểm định story phải qua ↔ năng lực skill
W_NEED = 3          # năng lực preflight suy ra ↔ năng lực skill
W_SCREEN = 2        # story có màn hình ↔ skill `ui`
W_TOKEN = 1         # token tiêu chí chấp nhận ↔ tags/subdomain (tối đa W_TOKEN_CAP)
W_TOKEN_CAP = 3
W_FRAMEWORK = 5     # skill của framework đúng pha

#: Skill framework theo pha — tên gọi đích danh, như prompt vẫn làm.
FRAMEWORK_BY_PHASE: dict[str, tuple[str, ...]] = {
    "mockup": ("aisdlc-mockup-html",),
}

#: Từ quá chung để làm tín hiệu — khớp chúng chỉ tạo nhiễu.
_STOP = frozenset({
    "the", "and", "for", "with", "when", "then", "given", "user", "data", "file",
    "code", "test", "tests", "story", "một", "các", "của", "khi", "thì", "được", "và",
    "cho", "với", "trong", "gọi", "trả", "về", "có", "không", "là", "this", "that",
})
_TOKEN = re.compile(r"[a-zA-ZÀ-ỹ][a-zA-ZÀ-ỹ0-9_-]{2,}")


#: Miền giao diện — chỉ skill khai một trong các miền này mới ăn tín hiệu
#: "story có màn hình". Suy từ chữ thì skill mã hoá cũng thành skill giao diện.
UI_DOMAINS = frozenset({"ui", "ux", "ui-ux", "ui/ux", "design", "frontend", "accessibility"})


@dataclass
class Pick:
    entry: SkillEntry
    score: int
    rationale: list[str] = field(default_factory=list)
    framework: bool = False
    strong: int = 0        # contract / need — tín hiệu từ hợp đồng story, không từ chữ
    screen: bool = False
    token_hits: int = 0

    @property
    def eligible(self) -> bool:
        """Paper §4.2 loại thẳng khớp keyword-only. Đo trên e9: một chữ
        "migration" làm story schema-IndexedDB khớp skill mật-mã-hậu-lượng-tử;
        "màn hình + một chữ" làm story điều hướng bàn phím khớp skill mã hoá
        đầu-cuối. Nên vẫn là **hai** tín hiệu độc lập — nhưng màn hình chỉ
        tính cho skill miền giao diện, và "màn hình + một chữ" không phải hai."""
        # Chữ chỉ là một tín hiệu khi đi cùng hợp đồng story; đi cùng màn hình
        # (mọi story giao diện đều có) thì phải ≥ 2 chữ.
        tok = 1 if (self.token_hits >= 2 or (self.token_hits >= 1 and self.strong >= 1)) else 0
        return self.framework or (self.strong + int(self.screen) + tok) >= 2

    def line(self) -> str:
        return f"{self.entry.id} ({self.score}): {'; '.join(self.rationale)}"


@dataclass
class Routing:
    picked: list[Pick] = field(default_factory=list)
    considered: int = 0
    threshold: int = DEFAULT_THRESHOLD
    best_rejected: Pick | None = None

    @property
    def abstained(self) -> bool:
        return not self.picked

    def ids(self) -> list[str]:
        return [p.entry.id for p in self.picked]

    def as_evidence(self) -> dict:
        return {
            "offered": [{"id": p.entry.id, "score": p.score, "why": p.rationale} for p in self.picked],
            "abstained": self.abstained,
            "considered": self.considered,
            "threshold": self.threshold,
            "best_rejected": None if self.best_rejected is None else
                {"id": self.best_rejected.entry.id, "score": self.best_rejected.score},
        }

    def prompt_section(self) -> str:
        """Mục cho prompt — tên, dùng khi, cách mở. **Không** dán nội dung
        skill: đó là progressive disclosure, agent mở khi cần."""
        if self.abstained:
            return (
                "Không có skill nào đủ khớp với story này (đã xét "
                f"{self.considered}). Làm theo hiến pháp và quyết định kiến "
                "trúc; đừng đi tìm skill."
            )
        lines = ["Những skill dưới đây được chọn cho **đúng story này**. Mở bằng "
                 "tool `Skill` (hoặc đọc `SKILL.md` ở đường dẫn) **khi tới bước "
                 "cần nó**, không mở hết từ đầu:", ""]
        for p in self.picked:
            why = p.rationale[0] if p.rationale else ""
            dung = f" — dùng khi: {p.entry.use_when}" if p.entry.use_when else ""
            lines.append(f"- `{p.entry.id}`{dung}\n  vì sao chọn: {why}. Đường dẫn: `{p.entry.path}`")
        return "\n".join(lines)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text) if t.lower() not in _STOP}


def score(entry: SkillEntry, story: Story, *, phase: str = "implement",
          contract: list[str] | None = None, needs: list[str] | None = None) -> Pick:
    """Chấm một skill cho một story. Mỗi điểm cộng có một câu vì sao."""
    caps = set(entry.capabilities)
    pick = Pick(entry=entry, score=0)

    if entry.id in FRAMEWORK_BY_PHASE.get(phase, ()):
        pick.score += W_FRAMEWORK
        pick.framework = True
        pick.rationale.append(f"skill của framework cho pha `{phase}`")

    for kind in (contract or []):
        if kind in caps:
            pick.score += W_CONTRACT
            pick.strong += 1
            pick.rationale.append(f"story phải qua kiểm định `{kind}`")

    for need in (needs or []):
        if need in caps:
            pick.score += W_NEED
            pick.strong += 1
            pick.rationale.append(f"story cần năng lực `{need}`")

    if story.screens and "ui" in caps and entry.domain.strip().lower() in UI_DOMAINS:
        pick.score += W_SCREEN
        pick.screen = True
        pick.rationale.append(f"story có màn hình ({', '.join(story.screens[:2])})")

    weak = _tokens(" ".join(story.acceptance_criteria) + " " + story.title)
    hits = sorted(weak & _tokens(" ".join(entry.tags) + " " + entry.subdomain + " " + entry.id.replace("-", " ")))
    if hits:
        add = min(W_TOKEN * len(hits), W_TOKEN_CAP)
        pick.score += add
        pick.token_hits = len(hits)
        pick.rationale.append(f"tiêu chí nhắc tới: {', '.join(hits[:4])}")
    return pick


def route(story: Story, registry: Registry, *, phase: str = "implement",
          threshold: int = DEFAULT_THRESHOLD, limit: int = DEFAULT_MAX,
          project=None) -> Routing:
    """Chọn ≤ `limit` skill có điểm ≥ `threshold`; không có thì abstain."""
    contract = [k for k in verification_contract(story) if k != "mockup-map"]
    try:
        needs = sorted({n.capability for n in required_capabilities(story, project=project)})
    except Exception:  # preflight là tín hiệu phụ — hỏng thì router vẫn chạy
        needs = []
    # `unit` có ở mọi story: khớp nó không nói gì về story này.
    contract = [k for k in contract if k != "unit"]

    picks = [score(e, story, phase=phase, contract=contract, needs=needs)
             for e in registry.routable()]
    picks.sort(key=lambda p: (-p.score, p.entry.id))
    out = Routing(considered=len(picks), threshold=threshold)
    for p in picks:
        if p.score >= threshold and p.eligible and len(out.picked) < limit:
            out.picked.append(p)
        elif out.best_rejected is None and p.score > 0:
            out.best_rejected = p
    return out
