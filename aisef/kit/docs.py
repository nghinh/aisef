"""Look up library documentation **on demand** (rule 12: do not fabricate API
names; when unsure, look it up) -- via the context7 HTTP API, no resident MCP.

Measured 2026-09-05: `GET https://context7.com/api/v1/search?query=vitest`
returns `results[].id` (`/vitest-dev/vitest`); `GET /api/v1/<id>?type=txt&topic=...&tokens=...`
returns documentation text with sources. No key needed at this usage level.
Results are cached at `~/.cache/aisef/docs/` so subsequent calls (and later
agent sessions) skip the network; agents invoke via `aisef doc <pkg> --topic <topic>`.
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
    library: str        # context7 id, e.g. `/vitest-dev/vitest`
    title: str
    topic: str
    text: str
    cached: bool
    source: str = "context7"


class DocError(RuntimeError):
    pass


def _get(url: str, fetch=None) -> str:
    """Fetch text; `fetch` allows tests to substitute a fake."""
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
        raise DocError(f"context7 returned non-JSON: {e}") from e
    return list(data.get("results") or [])


def _pick(package: str, results: list[dict]) -> dict:
    if not results:
        raise DocError(f"no documentation found for `{package}`")
    p = package.lower()
    for r in results:  # prefer exact name match
        rid = str(r.get("id", "")).lower()
        if rid.endswith("/" + p) or str(r.get("title", "")).lower() == p:
            return r
    return results[0]


def lookup(package: str, topic: str = "", *, tokens: int = DEFAULT_TOKENS, fetch=None,
           root: Path | None = None) -> Doc:
    """Look up documentation for a package (with topic). Cache first, network second."""
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
        raise DocError(f"context7 has no content for `{lib}` (topic: {topic or 'all'})")
    root.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps({"library": lib, "title": str(hit.get("title", "")), "topic": topic,
                                  "text": text}, ensure_ascii=False), encoding="utf-8")
    return Doc(lib, str(hit.get("title", "")), topic, text, False)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]
