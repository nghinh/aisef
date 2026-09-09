"""Skill registry — operational knowledge layer (ADR-002, batch 1).

Skills are imported from four sources with **heterogeneous** frontmatter:
security has `tags/subdomain/nist_csf/license/version`, bmad and superpowers
only have `name/description`. The router can't score across four shapes; and
`.aisef-managed` only records `source=` — no commit, no license, no
"use when". This registry normalizes each installed skill into **one record
with provenance and lifecycle status**, built from what already exists
(`install`, `catalog`, `security_filter`) without changing source skill
formats.

Status changes only through verification — verification is code
(`verify_structure`), not a model. Skills with status
`candidate`/`stale`/`rejected` **are never routed**.
"""

from __future__ import annotations

import json
import os
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

#: Valid lifecycle transitions. No edge **into** `verified` without passing
#: verification; no edge out of `rejected` — to reuse, reinstall from scratch
#: and re-verify from scratch.
ALLOWED: dict[str, frozenset[str]] = {
    CANDIDATE: frozenset({VERIFIED, REJECTED}),
    VERIFIED: frozenset({ACTIVE, STALE, REJECTED}),
    ACTIVE: frozenset({STALE, REJECTED}),
    STALE: frozenset({VERIFIED, REJECTED}),
    REJECTED: frozenset(),
}

#: Statuses the router considers.
ROUTABLE = frozenset({VERIFIED, ACTIVE})

#: Injection-style directive phrases — same class that prompt
#: `story-security-review` tells the reviewer to treat as a finding, not a command.
_INJECTION_PHRASES = re.compile(
    r"(?i)(ignore (all |the )?(previous|prior|above) instructions"
    r"|disregard (your|the) (system|previous)"
    r"|bỏ qua (mọi |các )?(luật|chỉ dẫn|hướng dẫn) (trước|ở trên)"
    r"|you are now (in )?(developer|debug|god) mode"
    r"|reveal (your|the) system prompt)"
)

_LINK = re.compile(r"\[[^\]]*\]\(([^)\s#]+)(?:#[^)]*)?\)")

#: Canonical capability vocabulary — same terms as `preflight`/`qa` so the
#: router can match against the story's verification contract without a lookup table.
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
    #: Usage evidence: which stories invoked this skill (accumulated from telemetry).
    used_in: list[str] = field(default_factory=list)

    @property
    def routable(self) -> bool:
        return self.status in ROUTABLE

    def text(self) -> str:
        """Text for the router's token matching — not the skill's content."""
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
            raise ValueError(f"status not found: {to}")
        if to != e.status and to not in ALLOWED[e.status]:
            raise ValueError(f"{skill_id}: {e.status} → {to} is not a valid transition")
        if to == VERIFIED and (verification is None or not verification.ok):
            raise ValueError(f"{skill_id}: transitioning to `verified` requires a passing check")
        e.status = to
        if verification is not None:
            e.verified = verification
        return e

    def record_use(self, skill_id: str, story_id: str) -> None:
        """Telemetry callback: story used a skill. `verified` with usage evidence -> `active`."""
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


# ------------------------------------------------------------- build


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


#: Capabilities a declared domain (real metadata) permits — prevents keyword
#: inference from spilling into unrelated fields. A cybersecurity skill saying
#: "performance" or "end-to-end" means it in a security context, not declaring
#: perf-benchmarking or e2e-testing capability. This is "structured metadata >
#: prose", applied to the source where we have metadata (109 security skills
#: declare `domain`).
#: Sources that don't declare `domain` in frontmatter but whose domain is
#: obvious — without this line the "story has screens" signal never reaches UI skills.
_SOURCE_DOMAIN = {"ui-ux": "ui-ux"}

_DOMAIN_CAPS: dict[str, frozenset[str]] = {
    # No "ui": 21/109 cybersecurity skills in e9 had "ui" inferred from the
    # word "screen"/"interface" in descriptions, and a keyboard-navigation story
    # was offered an end-to-end encryption skill (measured 2026-09-05). UI
    # capability must come from skills declaring a UI domain, not from words.
    "cybersecurity": frozenset({"security", "review"}),
    "ui-ux": frozenset({"ui", "accessibility", "design"}),
}


def _hit(hint: str, text: str, words: set[str]) -> bool:
    """Long hints (>= 6) safely match as substrings; short hints (`perf`, `e2e`,
    `git`, `ui`) must match **whole words** — otherwise "performative" swallows
    `perf`, "digital" swallows `git`. This is a real bug seen on e9:
    `receiving-code-review` was tagged `perf` because of "performative agreement"."""
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
    """Take `use_when` from frontmatter if present; otherwise extract the
    "Use when ..." clause from the description — superpowers follows that convention."""
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


_SCRIPT_SUFFIX = (".py", ".sh", ".js", ".mjs")


def _scripts(skill_dir: Path) -> list[Path]:
    d = skill_dir / "scripts"
    if not d.is_dir():
        return []
    return sorted(p for p in d.rglob("*") if p.is_file() and p.suffix in _SCRIPT_SUFFIX)[:50]


def script_broken(path: Path, skill_dir: Path) -> str:
    """Relative path if the script fails to compile, "" if OK.
    Does not execute the script — parse only."""
    import shutil
    import subprocess

    rel = str(path.relative_to(skill_dir))
    try:
        if path.suffix == ".py":
            # Pure compile(), no .pyc written: py_compile needs a cfile path.
            compile(path.read_text(encoding="utf-8", errors="replace"), str(path), "exec")
            return ""
        if path.suffix == ".sh":
            cmd = ["sh", "-n", str(path)]
        elif shutil.which("node"):
            cmd = ["node", "--check", str(path)]
        else:
            return ""                       # no node available: inconclusive
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        return "" if r.returncode == 0 else rel
    except (SyntaxError, ValueError, OSError, subprocess.SubprocessError):
        return rel


def verify_structure(skill_dir: Path) -> Verification:
    """Structural verification — code, not model. Gaps are recorded, not hidden."""
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

    broken = []
    for rel in _LINK.findall(text):
        if rel.startswith(("http://", "https://", "mailto:")):
            continue
        if not (skill_dir / rel).exists():
            broken.append(rel)
    if broken:
        v.gaps.append(f"link hỏng: {', '.join(broken[:5])}")  # không phải ✗: cảnh báo
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

    # scripts/ must at least **compile** — a valid SKILL.md with a broken script
    # means the skill is unusable, same class of bug as a syntactically valid hook
    # the client won't run (G6). Paper demands real execution; this is the safe
    # level without Docker.
    # ponytail: syntax check only, no execution — 201 files on e9, real execution
    # needs sandbox + time budget; upgrade to smoke `--help` when there's a benchmark.
    scripts = _scripts(skill_dir)
    if scripts:
        broken = [rel for rel in (script_broken(p, skill_dir) for p in scripts) if rel]
        if broken:
            v.gaps.append(f"✗ scripts không biên dịch được: {', '.join(broken[:3])}")
        else:
            v.checks.append(f"scripts: {len(scripts)} tệp biên dịch được")

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
    """Build registry from `.claude/skills`. Preserves `used_in` and `active`
    status from the previous build; skills with a directory that no longer
    exists in this build -> `stale`."""
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
            source = "aisef"
            if marker.is_file():
                m = re.search(r"source=(\S+)", marker.read_text(encoding="utf-8"))
                source = m.group(1) if m else source
            desc = str(fm.get("description", "")).strip()
            src = src_meta.get(source)
            e = SkillEntry(
                id=d.name, source=source, path=str(d.relative_to(project)),
                description=desc, use_when=_use_when(fm, desc),
                domain=str(fm.get("domain", "")) or _SOURCE_DOMAIN.get(source, ""),
                subdomain=str(fm.get("subdomain", "")),
                tags=_listish(fm.get("tags")),
                commit=src.commit if src else "",
                license=str(fm.get("license") or (src.license if src and src.license else "NO_LICENSE")),
            )
            # Capabilities must be **declared** — frontmatter `capabilities:` or a
            # domain with a permitted set (cybersecurity). Inferring from prose for
            # skills that don't declare a domain is keyword-matching disguised as a
            # contract: measured on e9 (2026-09-05), `receiving-code-review`
            # (superpowers) had `perf` + `ui` inferred and was selected for 5/18
            # stories because "must pass perf verification".
            khai = _listish(fm.get("capabilities"))
            theo_mien = _capabilities_of(e.text(), domain=e.domain) if e.domain.strip().lower() in _DOMAIN_CAPS else []
            e.capabilities = sorted(set(khai) | set(theo_mien))
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


# ------------------------------------------------------------- disk


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
    """Rebuild preserving history, write to disk. Call after `setup` and before `run`."""
    reg = build(project, catalog=catalog, previous=load(artifact_root))
    # Semantic scan verdicts (S6) survive rebuilds: a rebuild re-reads
    # structure, it doesn't discard a verdict that cost money to produce.
    from . import skill_scan

    skill_scan.apply(reg, skill_scan.load(artifact_root))
    save(reg, artifact_root)
    return reg
