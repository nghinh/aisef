"""Route skills for a story — harness-side, with thresholds and abstention.

Evidence this is needed (ADR-002 S1): e9 installed 156 skills, 86 Claude
sessions, the `Skill` tool was called 11 times for exactly 4 skills — all
explicitly named by the harness prompt. Stack-based installation doesn't
generate usage; naming in the prompt does. So skill selection is the harness's
job, not a client-side discovery mechanism over 156 descriptions.

Selection is **structured judgment**: structured signals (verification
contract, required capabilities, screens, phase) score deterministically;
acceptance-criteria prose is only a weak signal. Insufficient score means
**abstain** — the paper records 2/20 tasks failed because wrong skills were
stuffed in, causing the agent to deviate from its own strategy.

The router is a signal for the agent, not a gate: wrong selection doesn't
block a story; it surfaces in telemetry (`skills_offered` vs `skills_used`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..control.normalize import Story
from ..control.preflight import required_capabilities, verification_contract
from .registry import Registry, SkillEntry

#: Threshold and cap — knobs **read by code** (config `skills.route_threshold`,
#: `skills.route_max`); tuned by measured precision.
DEFAULT_THRESHOLD = 3
DEFAULT_MAX = 3

#: Weights. Structured signals first, prose second.
W_CONTRACT = 3      # verification type the story requires <-> skill capability
W_NEED = 3          # preflight-inferred capability <-> skill capability
W_SCREEN = 2        # story has screens <-> skill `ui`
W_TOKEN = 1         # acceptance-criteria token <-> tags/subdomain (capped at W_TOKEN_CAP)
W_TOKEN_CAP = 3
W_FRAMEWORK = 5     # framework skill matching the phase

#: Framework skills by phase — called by exact name, as prompts already do.
FRAMEWORK_BY_PHASE: dict[str, tuple[str, ...]] = {
    "mockup": ("aisef-mockup-html",),
}

#: UI **entry-point** skill: invited for every story with screens at the
#: implement phase, by policy rather than by text matching. Measured reason
#: (e9 2026-09-05): stories written in Vietnamese, `ui-ux` skill described in
#: English, no declared capabilities -> two signals never sufficient, and an
#: app with 5 screens was never offered any UI skill. `ui-ux-pro-max` routes
#: further to sub-skills (progressive disclosure) so only one entry is needed.
UI_ENTRY_SKILLS: tuple[str, ...] = ("ui-ux-pro-max",)

#: Words too generic to be a signal — matching them only adds noise.
_STOP = frozenset({
    "the", "and", "for", "with", "when", "then", "given", "user", "data", "file",
    "code", "test", "tests", "story", "một", "các", "của", "khi", "thì", "được", "và",
    "cho", "với", "trong", "gọi", "trả", "về", "có", "không", "là", "this", "that",
})
_TOKEN = re.compile(r"[a-zA-ZÀ-ỹ][a-zA-ZÀ-ỹ0-9_-]{2,}")


#: UI domains — only skills declaring one of these domains receive the
#: "story has screens" signal. Inferring from prose would turn encryption skills into UI skills.
UI_DOMAINS = frozenset({"ui", "ux", "ui-ux", "ui/ux", "design", "frontend", "accessibility"})


@dataclass
class Pick:
    entry: SkillEntry
    score: int
    rationale: list[str] = field(default_factory=list)
    framework: bool = False
    strong: int = 0        # contract / need — signal from story contract, not from prose
    screen: bool = False
    token_hits: int = 0

    @property
    def eligible(self) -> bool:
        """Paper S4.2 rejects keyword-only matches. Measured on e9: a single word
        "migration" made a schema-IndexedDB story match a post-quantum-crypto skill;
        "screen + one word" made a keyboard-navigation story match an end-to-end
        encryption skill. So still **two** independent signals are needed — but screens
        only count for UI-domain skills, and "screen + one word" is not two."""
        # Prose is only a signal when paired with a story contract; paired with
        # screens (every UI story has them) requires >= 2 token hits.
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
        """Section for the prompt — name, use-when, how to open. Does **not**
        inline skill content: that's progressive disclosure, the agent opens when needed."""
        if self.abstained:
            return (
                "No skill matched this story well enough (considered "
                f"{self.considered}). Follow the constitution and architecture "
                "decisions; do not search for skills."
            )
        lines = ["The skills below were selected for **this specific story**. Open with "
                 "tool `Skill` (or read `SKILL.md` at the path) **when you reach the step "
                 "that needs it**, do not open all at once:", ""]
        for p in self.picked:
            why = p.rationale[0] if p.rationale else ""
            hint = f" — dùng khi: {p.entry.use_when}" if p.entry.use_when else ""
            lines.append(f"- `{p.entry.id}`{hint}\n  vì sao chọn: {why}. Đường dẫn: `{p.entry.path}`")
        return "\n".join(lines)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text) if t.lower() not in _STOP}


def score(entry: SkillEntry, story: Story, *, phase: str = "implement",
          contract: list[str] | None = None, needs: list[str] | None = None) -> Pick:
    """Score one skill against one story. Each point added has a rationale."""
    caps = set(entry.capabilities)
    pick = Pick(entry=entry, score=0)

    if entry.id in FRAMEWORK_BY_PHASE.get(phase, ()):
        pick.score += W_FRAMEWORK
        pick.framework = True
        pick.rationale.append(f"skill của framework cho pha `{phase}`")

    if story.screens and phase == "implement" and entry.id in UI_ENTRY_SKILLS:
        pick.score += W_FRAMEWORK
        pick.framework = True
        pick.rationale.append(f"skill cửa ngõ giao diện — story có màn hình ({', '.join(story.screens[:2])})")

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
    """Select <= `limit` skills scoring >= `threshold`; abstain if none qualify."""
    contract = [k for k in verification_contract(story) if k != "mockup-map"]
    try:
        needs = sorted({n.capability for n in required_capabilities(story, project=project)})
    except Exception:  # preflight is a secondary signal — if it breaks the router still runs
        needs = []
    # `unit` appears in every story: matching it says nothing about this story.
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
