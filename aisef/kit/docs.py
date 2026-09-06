"""Tra tài liệu thư viện **theo yêu cầu** (luật 12: không bịa tên API, không
chắc thì tra) — qua HTTP API của context7, không MCP thường trú.

Đo 2026-09-05: `GET https://context7.com/api/v1/search?query=vitest` trả
`results[].id` (`/vitest-dev/vitest`); `GET /api/v1/<id>?type=txt&topic=…&tokens=…`
trả văn bản tài liệu kèm nguồn. Không cần khoá cho mức dùng này. Kết quả
được cache ở `~/.cache/aisef/docs/` để lần sau (và phiên agent sau) không
gọi mạng lại; agent mở bằng lệnh `aisef doc <gói> --topic <chủ đề>`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

API = "https://context7.com/api/v1"
ENV_DOCS = "AISEF_DOCS_CACHE"
DEFAULT_TOKENS = 2500
TIMEOUT = 20


def cache_root() -> Path:
    if env := os.environ.get(ENV_DOCS):
        return Path(env).expanduser().resolve()
    base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    return Path(base).expanduser() / "aisef" / "docs"


@dataclass
class Doc:
    library: str        # id context7, ví dụ `/vitest-dev/vitest`
    title: str
    topic: str
    text: str
    cached: bool
    source: str = "context7"


class DocError(RuntimeError):
    pass


def _get(url: str, fetch=None) -> str:
    """Tải văn bản; `fetch` để test thay bằng hàm giả."""
    if fetch is not None:
        return fetch(url)
    req = urllib.request.Request(url, headers={"User-Agent": "aisef"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 — https cố định
        return r.read().decode("utf-8", errors="replace")


def search(package: str, *, fetch=None) -> list[dict]:
    raw = _get(f"{API}/search?query={urllib.parse.quote(package)}", fetch)
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise DocError(f"context7 trả về không phải JSON: {e}") from e
    return list(data.get("results") or [])


def _pick(package: str, results: list[dict]) -> dict:
    if not results:
        raise DocError(f"không tìm thấy tài liệu cho `{package}`")
    p = package.lower()
    for r in results:  # ưu tiên khớp tên đúng
        rid = str(r.get("id", "")).lower()
        if rid.endswith("/" + p) or str(r.get("title", "")).lower() == p:
            return r
    return results[0]


def lookup(package: str, topic: str = "", *, tokens: int = DEFAULT_TOKENS, fetch=None,
           root: Path | None = None) -> Doc:
    """Tra tài liệu một gói (kèm chủ đề). Cache trước, mạng sau."""
    root = root or cache_root()
    key = hashlib.sha256(f"{package}|{topic}|{tokens}".encode()).hexdigest()[:16]
    cached = root / f"{_slug(package)}__{_slug(topic) or 'all'}__{key}.json"
    if cached.is_file():
        d = json.loads(cached.read_text(encoding="utf-8"))
        return Doc(d["library"], d["title"], d["topic"], d["text"], True)
    hit = _pick(package, search(package, fetch=fetch))
    lib = str(hit["id"])
    q = {"type": "txt", "tokens": str(tokens)}
    if topic:
        q["topic"] = topic
    text = _get(f"{API}{lib}?{urllib.parse.urlencode(q)}", fetch)
    if not text.strip():
        raise DocError(f"context7 không có nội dung cho `{lib}` (chủ đề: {topic or 'tất cả'})")
    root.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps({"library": lib, "title": str(hit.get("title", "")), "topic": topic,
                                  "text": text}, ensure_ascii=False), encoding="utf-8")
    return Doc(lib, str(hit.get("title", "")), topic, text, False)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]
