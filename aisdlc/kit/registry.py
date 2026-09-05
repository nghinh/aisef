"""Sổ đăng ký skill — tầng tri thức vận hành (ADR-002, đợt 1).

Skill nhập từ bốn nguồn có frontmatter **không đồng nhất**: security có
`tags/subdomain/nist_csf/license/version`, bmad và superpowers chỉ có
`name/description`. Router không thể chấm điểm trên bốn hình dạng; và
`.aisdlc-managed` chỉ ghi `source=` — không commit, không license, không
"dùng khi nào". Sổ này chuẩn hoá mỗi skill đã cài thành **một bản ghi có
provenance và trạng thái vòng đời**, dựng từ những gì đã có (`install`,
`catalog`, `security_filter`), không đổi định dạng skill nguồn.

Trạng thái chỉ đổi khi có kiểm — kiểm là code (`verify_structure`), không
phải model. Skill `candidate`/`stale`/`rejected` **không được định tuyến**.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..harness.guardrails import check_secrets
from .catalog import Catalog
from .install import MARKER, SKILLS_DIR
from .security_filter import Verdict, classify
from .skills import load_skill, parse_frontmatter

REGISTRY_FILE = "skill-registry.json"

CANDIDATE = "candidate"
VERIFIED = "verified"
ACTIVE = "active"
STALE = "stale"
REJECTED = "rejected"
STATUSES = (CANDIDATE, VERIFIED, ACTIVE, STALE, REJECTED)

#: Cạnh hợp lệ của vòng đời. Không có cạnh nào **vào** `verified` mà không
#: qua kiểm; không có cạnh nào ra khỏi `rejected` — muốn dùng lại thì cài
#: lại từ đầu, và kiểm lại từ đầu.
ALLOWED: dict[str, frozenset[str]] = {
    CANDIDATE: frozenset({VERIFIED, REJECTED}),
    VERIFIED: frozenset({ACTIVE, STALE, REJECTED}),
    ACTIVE: frozenset({STALE, REJECTED}),
    STALE: frozenset({VERIFIED, REJECTED}),
    REJECTED: frozenset(),
}

#: Trạng thái router được xét.
ROUTABLE = frozenset({VERIFIED, ACTIVE})

#: Câu dạng chỉ dẫn tiêm — cùng lớp với điều prompt `story-security-review`
#: bảo người rà soát coi là phát hiện, không phải mệnh lệnh.
_INJECTION_PHRASES = re.compile(
    r"(?i)(ignore (all |the )?(previous|prior|above) instructions"
    r"|disregard (your|the) (system|previous)"
    r"|bỏ qua (mọi |các )?(luật|chỉ dẫn|hướng dẫn) (trước|ở trên)"
    r"|you are now (in )?(developer|debug|god) mode"
    r"|reveal (your|the) system prompt)"
)

_LINK = re.compile(r"\[[^\]]*\]\(([^)\s#]+)(?:#[^)]*)?\)")

#: Từ vựng năng lực chuẩn — cùng từ với `preflight`/`qa` để router so được
#: với hợp đồng kiểm định của story mà không cần bảng dịch.
_CAPABILITY_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("security", ("security", "secure", "auth", "authz", "authn", "crypto", "owasp",
                  "injection", "secret", "vulnerab", "threat", "hardening", "sast")),
    ("ui", ("ui", "ux", "frontend", "screen", "mockup", "design", "component", "html", "css")),
    ("accessibility", ("accessib", "a11y", "wcag", "aria")),
    ("e2e", ("e2e", "playwright", "browser", "end-to-end")),
    ("perf", ("perf", "performance", "latency", "throughput", "benchmark", "load")),
    ("migration", ("migration", "migrate", "schema", "indexeddb", "database")),
    ("testing", ("test", "tdd", "assert", "coverage", "mutation", "fixture")),
    ("debugging", ("debug", "diagnos", "root cause", "bisect", "trace")),
    ("planning", ("prd", "epic", "story", "architecture", "requirements", "roadmap", "plan")),
    ("review", ("review", "code review", "rà soát")),
    ("git", ("git", "worktree", "branch", "merge", "commit")),
    ("parallel", ("parallel", "subagent", "dispatch", "song song")),
)


@dataclass
class Verification:
    at: str = ""
    by: str = ""              # "structural" | "human" | "distill"
    checks: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.at) and not any(g.startswith("✗") for g in self.gaps)


@dataclass
class SkillEntry:
    id: str
    source: str
    path: str
    description: str = ""
    use_when: str = ""
    domain: str = ""
    subdomain: str = ""
    tags: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    commit: str = ""
    license: str = "NO_LICENSE"
    status: str = CANDIDATE
    verified: Verification = field(default_factory=Verification)
    links: dict[str, list[str]] = field(default_factory=lambda: {"depends_on": [], "see_also": []})
    #: Bằng chứng dùng: story nào đã gọi skill này (tích luỹ từ telemetry).
    used_in: list[str] = field(default_factory=list)

    @property
    def routable(self) -> bool:
        return self.status in ROUTABLE

    def text(self) -> str:
        """Văn bản để router so khớp token — không phải nội dung skill."""
        return " ".join([self.id.replace("-", " "), self.description, self.use_when,
                         self.subdomain, " ".join(self.tags)]).lower()


@dataclass
class Registry:
    entries: dict[str, SkillEntry] = field(default_factory=dict)
    built_at: str = ""

    def routable(self) -> list[SkillEntry]:
        return [e for e in self.entries.values() if e.routable]

    def by_status(self) -> dict[str, int]:
        out: dict[str, int] = {s: 0 for s in STATUSES}
        for e in self.entries.values():
            out[e.status] += 1
        return out

    def transition(self, skill_id: str, to: str, *, verification: Verification | None = None) -> SkillEntry:
        e = self.entries[skill_id]
        if to not in STATUSES:
            raise ValueError(f"trạng thái không có: {to}")
        if to != e.status and to not in ALLOWED[e.status]:
            raise ValueError(f"{skill_id}: {e.status} → {to} không hợp lệ")
        if to == VERIFIED and (verification is None or not verification.ok):
            raise ValueError(f"{skill_id}: lên `verified` phải có bản kiểm đạt")
        e.status = to
        if verification is not None:
            e.verified = verification
        return e

    def record_use(self, skill_id: str, story_id: str) -> None:
        """Telemetry gọi: story dùng skill. `verified` có bằng chứng dùng → `active`."""
        e = self.entries.get(skill_id)
        if e is None:
            return
        if story_id and story_id not in e.used_in:
            e.used_in.append(story_id)
        if e.status == VERIFIED:
            e.status = ACTIVE

    def as_dict(self) -> dict:
        return {
            "version": 1,
            "built_at": self.built_at,
            "entries": {k: asdict(v) for k, v in sorted(self.entries.items())},
        }


# ------------------------------------------------------------- dựng


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


#: Năng lực mà một domain đã khai (metadata thật) cho phép — chặn suy diễn
#: keyword tràn sang lĩnh vực khác. Skill cybersecurity nói "performance" hay
#: "end-to-end" là nói trong ngữ cảnh an ninh, không phải khai năng lực đo
#: hiệu năng hay chạy e2e-test. Đây là "structured metadata > prose", áp cho
#: đúng nguồn ta có metadata (109 skill security khai `domain`).
_DOMAIN_CAPS: dict[str, frozenset[str]] = {
    "cybersecurity": frozenset({"security", "review", "ui"}),
}


def _hit(hint: str, text: str, words: set[str]) -> bool:
    """Hint dài (≥ 6) khớp chuỗi con là an toàn; hint ngắn (`perf`, `e2e`,
    `git`, `ui`) phải khớp **cả từ** — nếu không thì "performative" nuốt
    `perf`, "digital" nuốt `git`. Đây là lỗi thật thấy trên e9:
    `receiving-code-review` bị gắn `perf` vì chữ "performative agreement"."""
    if len(hint) >= 6 and " " not in hint:
        return hint in text
    return hint in words or (" " in hint and hint in text)


def _capabilities_of(text: str, *, domain: str = "") -> list[str]:
    t = text.lower()
    words = set(re.findall(r"[a-z0-9]+", t))
    caps = [cap for cap, hints in _CAPABILITY_HINTS if any(_hit(h, t, words) for h in hints)]
    allow = _DOMAIN_CAPS.get(domain.strip().lower())
    if allow is not None:
        caps = [c for c in caps if c in allow]
    return caps


def _use_when(fm: dict, description: str) -> str:
    """Frontmatter có `use_when` thì lấy; không thì lấy mệnh đề "Use when …"
    trong mô tả — superpowers viết đúng kiểu ấy."""
    if fm.get("use_when"):
        return str(fm["use_when"]).strip()
    m = re.search(r"(?i)\b(use when|dùng khi)\b(.{0,240})", description)
    return (m.group(1) + m.group(2)).strip() if m else ""


def _listish(v) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str) and v.startswith("["):
        return [x.strip(" '\"") for x in v.strip("[]").split(",") if x.strip(" '\"")]
    return [str(v).strip()] if v else []


def verify_structure(skill_dir: Path) -> Verification:
    """Kiểm cấu trúc — code, không model. Gap ghi ra, không giấu."""
    v = Verification(at=_now(), by="structural")
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        v.gaps.append("✗ không có SKILL.md")
        return v
    text = md.read_text(encoding="utf-8", errors="replace")
    fm = parse_frontmatter(text)
    if not fm:
        v.gaps.append("✗ frontmatter không đọc được")
    else:
        v.checks.append("frontmatter hợp lệ")
    name = str(fm.get("name", "")).strip()
    if name and name != skill_dir.name:
        v.gaps.append(f"✗ name `{name}` ≠ thư mục `{skill_dir.name}`")
    else:
        v.checks.append("name khớp thư mục")
    if not str(fm.get("description", "")).strip():
        v.gaps.append("✗ description rỗng")
    else:
        v.checks.append("có description")

    hong = []
    for rel in _LINK.findall(text):
        if rel.startswith(("http://", "https://", "mailto:")):
            continue
        if not (skill_dir / rel).exists():
            hong.append(rel)
    if hong:
        v.gaps.append(f"link hỏng: {', '.join(hong[:5])}")  # không phải ✗: cảnh báo
    else:
        v.checks.append("link tương đối trỏ tới tệp có thật")

    for p in [md, *sorted(skill_dir.rglob("*.md"))[:50]]:
        body = p.read_text(encoding="utf-8", errors="replace")
        if not check_secrets(body).allowed:
            v.gaps.append(f"✗ {p.relative_to(skill_dir)} có bí mật")
            break
        if _INJECTION_PHRASES.search(body):
            v.gaps.append(f"✗ {p.relative_to(skill_dir)} có câu chỉ dẫn tiêm")
            break
    else:
        v.checks.append("không có bí mật, không có câu tiêm")

    skill = load_skill(skill_dir)
    if skill is not None:
        c = classify(skill)
        if c.verdict is Verdict.OFFENSIVE:
            v.gaps.append(f"✗ security_filter: offensive — {c.reason}")
        else:
            v.checks.append(f"security_filter: {c.verdict.value}")
    return v


def build(project: Path | str, *, catalog: Catalog | None = None,
          previous: Registry | None = None) -> Registry:
    """Dựng sổ từ `.claude/skills`. Giữ `used_in` và trạng thái `active` của
    lần dựng trước; skill có thư mục mà không còn ở lần này → `stale`."""
    project = Path(project)
    root = project / SKILLS_DIR
    cat = catalog or Catalog.load()
    src_meta = {s.id: s for s in cat.sources}
    reg = Registry(built_at=_now())
    prev = previous.entries if previous else {}

    if root.is_dir():
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            md = d / "SKILL.md"
            if not md.is_file():
                continue
            fm = parse_frontmatter(md.read_text(encoding="utf-8", errors="replace"))
            marker = d / MARKER
            source = "aisdlc"
            if marker.is_file():
                m = re.search(r"source=(\S+)", marker.read_text(encoding="utf-8"))
                source = m.group(1) if m else source
            desc = str(fm.get("description", "")).strip()
            src = src_meta.get(source)
            e = SkillEntry(
                id=d.name, source=source, path=str(d.relative_to(project)),
                description=desc, use_when=_use_when(fm, desc),
                domain=str(fm.get("domain", "")), subdomain=str(fm.get("subdomain", "")),
                tags=_listish(fm.get("tags")),
                commit=src.commit if src else "",
                license=str(fm.get("license") or (src.license if src and src.license else "NO_LICENSE")),
            )
            e.capabilities = sorted(set(_capabilities_of(e.text(), domain=e.domain)))
            ver = verify_structure(d)
            old = prev.get(e.id)
            if old is not None:
                e.used_in = list(old.used_in)
            if not ver.ok:
                e.status, e.verified = REJECTED, ver
            elif src is not None and old is not None and old.commit and old.commit != src.commit:
                e.status, e.verified = STALE, ver
            else:
                e.status, e.verified = (ACTIVE if old and old.status == ACTIVE else VERIFIED), ver
            reg.entries[e.id] = e

    for sid, old in prev.items():
        if sid not in reg.entries and old.status != REJECTED:
            old.status = STALE
            old.verified.gaps.append("thư mục không còn trong .claude/skills")
            reg.entries[sid] = old
    return reg


# ------------------------------------------------------------- đĩa


def path_for(artifact_root: Path | str) -> Path:
    return Path(artifact_root) / REGISTRY_FILE


def save(reg: Registry, artifact_root: Path | str) -> Path:
    p = path_for(artifact_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(reg.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def load(artifact_root: Path | str) -> Registry:
    p = path_for(artifact_root)
    if not p.is_file():
        return Registry()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Registry()
    reg = Registry(built_at=raw.get("built_at", ""))
    for k, v in (raw.get("entries") or {}).items():
        ver = v.pop("verified", {}) or {}
        reg.entries[k] = SkillEntry(**{**v, "verified": Verification(**ver)})
    return reg


def refresh(project: Path | str, artifact_root: Path | str, *, catalog: Catalog | None = None) -> Registry:
    """Dựng lại giữ lịch sử, ghi xuống đĩa. Gọi sau `setup` và trước `run`."""
    reg = build(project, catalog=catalog, previous=load(artifact_root))
    save(reg, artifact_root)
    return reg
