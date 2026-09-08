"""Acceptance criteria ↔ test: the ``AC-<story>-<i>`` code contract.

Old traceability stopped at "story covers FR with green tests" — criterion 3
was never checked yet the report stayed green, and the reviewer was told
"point out which test covers which criterion": judgment where lookup was
needed. Now each criterion *i* of a story has code ``AC-<story>-<i>``; the
code must appear in the **name** of at least one test, and test names are
read from runner output (``harness/testlog``), not from agent claims.

Exact code matching: ``AC-S-1`` does not match ``AC-S-10``; ``_`` and ``-``
are treated as equivalent because pytest function names cannot contain
hyphens (``test_AC_S_1_empty_string``).
"""

from __future__ import annotations

import re


def ac_code(story_id: str, i: int) -> str:
    return f"AC-{story_id}-{i}"


def codes(story_id: str, n: int) -> list[str]:
    return [ac_code(story_id, i) for i in range(1, n + 1)]


def _pattern(code: str) -> re.Pattern:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(code.replace('_', '-'))}(?![0-9])", re.I)


def coverage(story_id: str, n: int, test_ids: list[str]) -> dict[int, list[str]]:
    """Criterion i -> tests carrying its code (may be empty)."""
    norm = [(t, t.replace("_", "-")) for t in test_ids]
    out: dict[int, list[str]] = {}
    for i in range(1, n + 1):
        rx = _pattern(ac_code(story_id, i))
        out[i] = [t for t, tn in norm if rx.search(tn)]
    return out


def missing(story_id: str, n: int, test_ids: list[str]) -> list[int]:
    return [i for i, tests in coverage(story_id, n, test_ids).items() if not tests]
