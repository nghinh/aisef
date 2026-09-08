"""Detect the project's technology stack from `docs/requirements.md`.

The result determines **which skills to install**: a Python + React project
does not need 56 cloud-security skills for infrastructure it does not use,
nor does it need Flutter skills.

Principle: **do not guess without evidence.** If the requirements say nothing
about databases, return empty rather than defaulting to Postgres. Gaps are
recorded so the architecture phase decides, the way BMAD records
``open_questions`` instead of fabricating answers.

Detection is keyword matching -- crude but transparent and testable. Keywords
use word boundaries so "go" does not match inside "Django", and "react" does
not match inside "reaction".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

#: Keywords by category. Keys are normalized names used throughout the framework.
SIGNATURES: dict[str, dict[str, tuple[str, ...]]] = {
    "backend": {
        "python": ("python", "fastapi", "django", "flask", "pydantic", "sqlalchemy"),
        "go": ("golang", "go lang", "goroutine", "gin framework", "fiber", "gorm", "go mod"),
        "node": ("node", "nodejs", "express", "nestjs", "fastify"),
        "java": ("java", "spring boot", "spring", "quarkus"),
        "dotnet": (".net", "dotnet", "asp.net", "c#"),
        "php": ("php", "laravel", "symfony"),
        "ruby": ("ruby", "rails"),
        "rust": ("rust", "axum", "actix"),
    },
    "frontend": {
        "react": ("react", "next.js", "nextjs", "remix"),
        "vue": ("vue", "nuxt"),
        "angular": ("angular",),
        "svelte": ("svelte", "sveltekit"),
    },
    "mobile": {
        "flutter": ("flutter", "dart"),
        "react-native": ("react native", "react-native", "expo"),
        "ios": ("swift", "swiftui", "ios native"),
        "android": ("kotlin", "jetpack compose", "android native"),
    },
    "database": {
        "postgres": ("postgres", "postgresql", "pgsql"),
        "mysql": ("mysql", "mariadb"),
        "mongodb": ("mongodb", "mongo"),
        "sqlite": ("sqlite",),
        "redis": ("redis",),
        "indexeddb": ("indexeddb", "index db"),
    },
    "deploy": {
        "docker": ("docker", "container"),
        "kubernetes": ("kubernetes", "k8s"),
        "aws": ("aws", "amazon web services", "lambda", "s3", "ec2"),
        "gcp": ("gcp", "google cloud"),
        "azure": ("azure",),
        "serverless": ("serverless", "cloudflare workers", "edge function"),
        "vercel": ("vercel", "netlify"),
    },
}

#: Markers for apps with a UI -- determines whether the mockup step is needed.
WEB_MARKERS = ("web", "trình duyệt", "browser", "giao diện", "ui", "frontend", "spa", "pwa")

#: Technology names that collide with common words; only accepted when cased correctly.
#: "Go service" is the Go language; "go to the page" is not. Case sensitivity
#: is the cheapest signal to distinguish the two.
CASE_SENSITIVE: dict[str, tuple[tuple[str, str], ...]] = {
    "backend": (("go", "Go"), ("rust", "Rust")),
}


@dataclass
class Stack:
    backend: list[str] = field(default_factory=list)
    frontend: list[str] = field(default_factory=list)
    mobile: list[str] = field(default_factory=list)
    database: list[str] = field(default_factory=list)
    deploy: list[str] = field(default_factory=list)
    #: Categories with no detected markers -- the architecture phase must decide.
    undetermined: list[str] = field(default_factory=list)

    @property
    def has_ui(self) -> bool:
        # "Mentions web without naming a framework" is recorded as `undetermined:
        # frontend` -- that is still an app with a UI. Not counting it would
        # cause `setup` to drop the `ui-ux` source for the wrong reason
        # (e9: React app with 5 screens, requirements says "runs in the
        # browser", 2026-09-05).
        return bool(self.frontend or self.mobile or "frontend" in self.undetermined)

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "backend": self.backend,
            "frontend": self.frontend,
            "mobile": self.mobile,
            "database": self.database,
            "deploy": self.deploy,
            "undetermined": self.undetermined,
        }

    def summary(self) -> str:
        parts = [
            f"{k}: {', '.join(v)}"
            for k, v in self.as_dict().items()
            if v and k != "undetermined"
        ]
        if self.undetermined:
            parts.append(f"undetermined: {', '.join(self.undetermined)}")
        return " · ".join(parts) if parts else "nothing detected"


def _matches(text: str, keywords: tuple[str, ...]) -> bool:
    """Match keywords with word boundaries so 'go' does not match inside 'Django'."""
    for kw in keywords:
        pattern = r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])"
        if re.search(pattern, text):
            return True
    return False


def detect(text: str) -> Stack:
    """Detect stack from requirements content."""
    lowered = text.lower()
    found: dict[str, list[str]] = {}

    for category, options in SIGNATURES.items():
        hits = {name for name, kws in options.items() if _matches(lowered, kws)}
        for name, exact in CASE_SENSITIVE.get(category, ()):
            if re.search(r"(?<![A-Za-z0-9])" + re.escape(exact) + r"(?![a-z0-9])", text):
                hits.add(name)
        found[category] = sorted(hits)

    stack = Stack(
        backend=found["backend"],
        frontend=found["frontend"],
        mobile=found["mobile"],
        database=found["database"],
        deploy=found["deploy"],
    )

    # Mentions web without naming a specific framework -- still an app with a
    # UI that needs mockups. Record as undetermined so the architecture phase picks.
    if not stack.frontend and not stack.mobile and _matches(lowered, WEB_MARKERS):
        stack.undetermined.append("frontend")

    for category in ("backend", "database", "deploy"):
        if not found[category]:
            stack.undetermined.append(category)

    return stack


def detect_file(path: Path | str) -> Stack:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"not found: {p}")
    return detect(p.read_text(encoding="utf-8", errors="replace"))
