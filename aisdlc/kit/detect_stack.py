"""Dò công nghệ dự án dùng từ `docs/requirements.md`.

Kết quả quyết định **cài skill nào**: dự án Python + React không cần 56 skill
bảo mật đám mây cho hạ tầng nó không dùng, và cũng không cần skill Flutter.

Nguyên tắc: **không đoán khi không có căn cứ.** Requirements không nói gì
về cơ sở dữ liệu thì trả về rỗng, chứ không mặc định Postgres. Chỗ trống
được ghi lại để pha kiến trúc quyết định, đúng cách BMAD ghi
``open_questions`` thay vì bịa.

Cách dò là so từ khoá — thô nhưng minh bạch và kiểm được. Từ khoá viết
kèm ranh giới từ nên "go" không khớp trong "Django", và "react" không
khớp trong "reaction".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

#: Từ khoá theo hạng mục. Khoá là tên chuẩn hoá dùng trong toàn framework.
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

#: Dấu hiệu ứng dụng có giao diện — quyết định có cần bước mockup không.
WEB_MARKERS = ("web", "trình duyệt", "browser", "giao diện", "ui", "frontend", "spa", "pwa")

#: Tên công nghệ trùng với từ thông dụng, chỉ nhận khi viết hoa đúng cách.
#: "Dịch vụ Go" là ngôn ngữ Go; "go to the page" thì không. Phân biệt hoa
#: thường là tín hiệu rẻ nhất để tách hai trường hợp đó.
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
    #: Hạng mục không tìm được dấu hiệu nào — pha kiến trúc phải quyết.
    undetermined: list[str] = field(default_factory=list)

    @property
    def has_ui(self) -> bool:
        # "Nhắc tới web mà không nêu framework" đã được ghi là `undetermined:
        # frontend` — đó vẫn là ứng dụng có giao diện. Không tính nó thì
        # `setup` bỏ nguồn `ui-ux` với lý do sai (e9: ứng dụng React 5 màn
        # hình, requirements viết "chạy trong trình duyệt", 2026-09-05).
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
            parts.append(f"chưa xác định: {', '.join(self.undetermined)}")
        return " · ".join(parts) if parts else "không dò được gì"


def _matches(text: str, keywords: tuple[str, ...]) -> bool:
    """So từ khoá có ranh giới từ, để 'go' không khớp trong 'Django'."""
    for kw in keywords:
        pattern = r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])"
        if re.search(pattern, text):
            return True
    return False


def detect(text: str) -> Stack:
    """Dò stack từ nội dung requirements."""
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

    # Nhắc tới web mà không nêu framework cụ thể vẫn là ứng dụng có giao
    # diện — cần mockup. Ghi vào undetermined để pha kiến trúc chọn framework.
    if not stack.frontend and not stack.mobile and _matches(lowered, WEB_MARKERS):
        stack.undetermined.append("frontend")

    for category in ("backend", "database", "deploy"):
        if not found[category]:
            stack.undetermined.append(category)

    return stack


def detect_file(path: Path | str) -> Stack:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"không có {p}")
    return detect(p.read_text(encoding="utf-8", errors="replace"))
