"""B2 ground-truth PREP tooling — protocol §8: "NEW `validation/v23/ground_truth/**` only (prep, starts now)".

Shapes follow docs/v2.3/drafts/B2-GROUND-TRUTH-PROTOCOL-DRAFT.md as drafted 2026-11-25. That protocol is a DRAFT
pending the owner freeze (its §9): the freeze MAY amend any shape here, and this package then follows the frozen
text, not this draft. Modules: `corpus` (§2 — items, manifest, §2.3 repo criteria), `labels` (§3 — label schema,
derived verdict, commit-then-reveal, agreement), `metrics` (§4.2 classification and aggregates, §4.3 NO-GO).

This package never imports aisef2 (validation code is not coupled to the kernel; any kernel byte change is F5
qualification, KERNEL-COUPLING-01 — protocol §8). The canonical-JSON rule below is
aisef2/product/contract.py::canonical copied locally for already-JSON-shaped data.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical(value: Any) -> str:
    """aisef2/product/contract.py::canonical, copied: the one canonical JSON form (sorted keys, no spaces)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    """sha256 hex of the canonical form — the digest every B2 record cites."""
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def hex_problems(name: str, value: Any, length: int) -> list[str]:
    """[] iff `value` is lowercase hex of exactly `length` characters; else one problem naming `name`."""
    ok = isinstance(value, str) and len(value) == length and all(c in "0123456789abcdef" for c in value)
    return [] if ok else [f"{name} is not lowercase hex of length {length}: {value!r}"]
