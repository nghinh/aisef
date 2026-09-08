"""Parse the JSON status BMAD returns when running in headless mode.

BMAD defines this contract itself (`assets/headless-schemas.md` in each
skill), and it maps almost one-to-one to the framework's approval gates:

===============  ==========================================================
``complete``     artifact stands on its own -> eligible for auto-approval
``partial``      artifact exists but has ``open_questions`` -> **requires** human review
``blocked``      could not produce artifact -> stop, report reason
===============  ==========================================================

This means we don't need to invent a "when to ask a human" mechanism --
BMAD already answers that; we just need to read it correctly.

BMAD places the JSON at the end of its reply, usually inside a ```json
fence but not always. This parser scans all top-level objects and takes
the **last object with a ``status`` key** -- the prose before it often
quotes both the schema and examples.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_DECODER = json.JSONDecoder()


@dataclass
class HeadlessStatus:
    status: str = ""  # complete | partial | blocked
    intent: str = ""  # create | update | validate
    reason: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def parsed(self) -> bool:
        """Whether a JSON status was successfully parsed."""
        return bool(self.status)

    @property
    def produced_artifact(self) -> bool:
        return self.status in ("complete", "partial")

    @property
    def needs_human(self) -> bool:
        """Whether human review is required before proceeding.

        ``partial`` means BMAD itself says the artifact cannot stand on its
        own. Auto-approving such a document bypasses the exact situation the
        human gate exists to protect against.
        """
        return self.status == "partial" or bool(self.open_questions)

    def declared_paths(self) -> list[str]:
        """All paths BMAD claims to have produced.

        Used to cross-check against disk: a declared path with no actual
        file is a silent failure, only caught if we bother to verify.
        """
        return sorted(set(self.artifacts.values()))

    def summary(self) -> str:
        if not self.parsed:
            return "could not parse BMAD JSON status"
        parts = [f"status={self.status}"]
        if self.artifacts:
            parts.append("artifact: " + ", ".join(sorted(self.artifacts)))
        if self.open_questions:
            parts.append(f"{len(self.open_questions)} open questions")
        if self.assumptions:
            parts.append(f"{len(self.assumptions)} assumptions")
        if self.reason:
            parts.append(f"reason: {self.reason}")
        return " · ".join(parts)


#: Keys with a different meaning; never an artifact path.
_NON_ARTIFACT_KEYS = frozenset(
    {"status", "intent", "reason", "assumptions", "open_questions",
     "external_handoffs", "conflicts_with_prior_decisions", "offer_to_update",
     "doc_workspace", "altitude", "purpose"}
)

_PATH_LIKE = re.compile(r"[/\\]|\.[A-Za-z0-9]{1,5}$")


def _is_path(value) -> bool:
    """Whether this string looks like a file path.

    Each BMAD skill names its artifact key differently (``spine``,
    ``design``, ``experience``, ``companions``...), so enumerating them all
    is impossible. Checking the value's shape is more reliable: a blocklist
    of keys will always be incomplete, while ``"feature"`` or
    ``"build-substrate"`` never look like a path.
    """
    return isinstance(value, str) and bool(value) and bool(_PATH_LIKE.search(value))


def _as_str_list(value) -> list[str]:
    """Normalize to a list of strings.

    ``open_questions`` is sometimes a list of strings, sometimes a list of
    ``{id, text}`` objects -- accept both rather than requiring BMAD to use
    one format.
    """
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, str):
            out.append(item.strip())
        elif isinstance(item, dict):
            text = item.get("text") or item.get("question") or ""
            ident = item.get("id") or ""
            out.append(f"{ident}: {text}".strip(": ").strip())
    return [x for x in out if x]


def _top_level_objects(text: str) -> list[dict]:
    """All top-level JSON objects in a block of text.

    Scans left to right; after reading an object it jumps past its entire
    body. This prevents nested objects from being counted as separate
    candidates -- otherwise an ``{"id": ..., "status": ...}`` inside
    ``open_questions`` would be mistaken for the run's status.
    """
    out: list[dict] = []
    i = 0
    while True:
        i = text.find("{", i)
        if i < 0:
            return out
        try:
            value, end = _DECODER.raw_decode(text, i)
        except ValueError:
            i += 1
            continue
        if isinstance(value, dict):
            out.append(value)
        i = end


def parse_headless_status(text: str) -> HeadlessStatus:
    """Extract JSON status from BMAD's reply.

    Takes the **last object with a ``status`` key**: the prose before it
    often quotes the schema or examples, while the real status is always
    at the end.
    """
    if not text:
        return HeadlessStatus()

    for data in reversed(_top_level_objects(text)):
        if "status" not in data:
            continue

        artifacts: dict[str, str] = {}
        for k, v in data.items():
            if k in _NON_ARTIFACT_KEYS:
                continue
            if _is_path(v):
                artifacts[k] = v
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    if _is_path(item):
                        artifacts[f"{k}[{i}]"] = item

        return HeadlessStatus(
            status=str(data.get("status", "")),
            intent=str(data.get("intent", "")),
            reason=str(data.get("reason", "")),
            artifacts=artifacts,
            assumptions=_as_str_list(data.get("assumptions")),
            open_questions=_as_str_list(data.get("open_questions")),
            raw=data,
        )

    return HeadlessStatus()
