"""W2's supplementary leak scan: the hidden evaluator's PLAIN stimulus strings in session streams.

`harness.leaks` searches each contract's stimulus and observable as one JSON string (and its quote-escaped form): the
detector of a copied evaluator document. Two limits, measured by tools/dry_check.py: a JSON form that holds a backslash
(`\\n` inside a workspace file's text, `\\.` in a regex) nested one level deeper in a session's JSON is not matched by the
quote-only escape; and a developer who saw a hidden file's CONTENT (a run id, a sentence) rather than the document leaves no
JSON form at all. This scan adds the plain strings of the STIMULI (what an arm must never have seen): every string value of
a hidden stimulus of 12+ characters, each line of a multi-line value, every workspace or scenario file name and the file
name of every `<ws>/...` argument (6+ characters) — each searched as it is and as JSON escapes it inside a string. Strings
that are public anyway (they occur in the task text or the baseline tree) are excluded by dry_check.py, which writes the
effective list to dry-check/plain-strings.json; pass it with --strings so every arm is scanned with the same list.

    python -P -B closure-evidence/v2/v2.1/e2/w2/tools/leaks_w2.py <evaluator.json> <sessions dir> [--strings FILE]

Exit 0 when no session holds a string, 1 otherwise. A hit is a reason to mark the result `valid: false` (EXPERIMENT-PLAN);
it is not proof of intent."""

from __future__ import annotations

import json
import pathlib
import sys

MIN_TEXT, MIN_NAME = 12, 6


def _values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for v in value:
            yield from _values(v)
    elif isinstance(value, dict):
        for k, v in value.items():
            if k != "step":            # a scenario step's kind (workspace, call, expect_raises) is the kernel's vocabulary, not a secret
                yield from _values(v)


def plain_strings(evaluator: dict) -> list[str]:
    out: set[str] = set()
    for c in evaluator["contracts"]:
        stim = c["stimulus"]
        for s in _values(stim):
            if s.startswith("<ws>/"):
                name = s[len("<ws>/"):].rsplit("/", 1)[-1]
                if len(name) >= MIN_NAME:
                    out.add(name)
                continue
            for line in s.splitlines():
                line = line.strip()
                if len(line) >= MIN_TEXT:
                    out.add(line)
        names = list(stim.get("workspace") or {})
        for step in (stim.get("scenario") or []):
            names += list(step.get("files") or {})
        for n in names:
            name = n.rsplit("/", 1)[-1]
            if len(name) >= MIN_NAME:
                out.add(name)
    return sorted(out)


def _forms(s: str) -> tuple[str, str]:
    return s, json.dumps(s)[1:-1]


def leaks(sessions: pathlib.Path, strings: list[str]) -> list[dict]:
    found = []
    for log in sorted(sessions.glob("*.jsonl")):
        text = log.read_text(encoding="utf-8", errors="replace")
        hits = sorted({s for s in strings if any(f in text for f in _forms(s))})
        if hits:
            found.append({"session": log.name, "strings": len(hits), "first": hits[:3]})
    return found


def main(argv: list[str]) -> int:
    evaluator = json.loads(pathlib.Path(argv[0]).read_text(encoding="utf-8"))
    strings = plain_strings(evaluator)
    if "--strings" in argv:
        strings = json.loads(pathlib.Path(argv[argv.index("--strings") + 1]).read_text(encoding="utf-8"))["strings"]
    found = leaks(pathlib.Path(argv[1]), strings)
    print(json.dumps({"plain_strings": len(strings), "found": found}, indent=1))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
