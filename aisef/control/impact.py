"""What does this change touch — context for the reviewer.

A reviewer receives the diff but still must answer: who calls the changed
code, which tests cover it, which flows pass through it. Measured on e9, this
costs 22-68 turns per attempt, and each retry starts from scratch —
STORY-01-04 ran four attempts and three of them re-traced the same read path.

This is **context**, not a verdict. Call graphs built by static analysis are
always incomplete: dynamic calls, reflection, and dependency injection are
invisible. Treating it as ground truth makes the reviewer ignore what it
misses — and that is usually where the bug is. So every result here includes
its source and confidence level, and the prompt states it is only a starting
suggestion.

The architecture is **not** tied to any specific tool. `review.impact_provider`
takes a command; the command returns JSON per the contract below. If not
configured, the built-in fallback is used — much rougher, but works
immediately and says so explicitly.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ..clients.base import split_command

#: Max items per category included in the prompt. Enough to orient, not enough
#: to overshadow the diff — the reviewer must read code, not lists.
MAX_PER_KIND = 12

#: File extensions treated as source code when searching for references.
SOURCE_EXT = (
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".rs",
    ".java", ".kt", ".rb", ".php", ".cs", ".swift",
)

_TEST_HINT = re.compile(r"(^|[./_-])(test|tests|spec|__tests__|e2e)([./_-]|$)", re.I)


def is_test_path(path: str) -> bool:
    return bool(_TEST_HINT.search(path))


@dataclass
class ImpactReport:
    """Impact of a change. Empty is valid, and must be stated explicitly."""

    #: Exported function/class/constant names changed in the diff.
    changed_symbols: list[str] = field(default_factory=list)
    #: Files referencing those names but **not** in the diff.
    callers: list[str] = field(default_factory=list)
    #: Test files referencing those names.
    related_tests: list[str] = field(default_factory=list)
    #: Changed names not mentioned by any test file. This is the most valuable
    #: item: the most frequent failure pattern on e9 is "code exists but no
    #: test proves it works" — `registerSW`, `roving tabindex`, `watchNotes`,
    #: arrow-key navigation.
    untested_symbols: list[str] = field(default_factory=list)
    #: Flows/execution paths affected, if the provider knows.
    flows: list[str] = field(default_factory=list)
    #: Who computed this result.
    source: str = ""
    #: True when the result is rougher than desired (built-in fallback, or
    #: external command failed). Must be stated: the reader needs to know the
    #: confidence level.
    degraded: bool = False
    note: str = ""

    @property
    def empty(self) -> bool:
        return not (
            self.changed_symbols or self.callers
            or self.related_tests or self.untested_symbols or self.flows
        )

    def as_prompt(self) -> str:
        """Section for the review prompt. States source and limitations."""
        if self.empty:
            return (
                "_No impact analysis available_ — `review.impact_provider` "
                "not configured, or nothing could be inferred. "
                "Detect from diff manually."
            )
        lines = [
            f"_Source: {self.source or 'unknown'}"
            + (" · **rough**, starting suggestion only" if self.degraded else "")
            + "._",
            "",
            "This is a **suggestion**, not ground truth: static analysis misses "
            "dynamic calls, reflection, and dependency injection. Do not stop here, "
            "and do not ignore what it does not mention.",
            "",
        ]
        for label, level in (
            ("Changed symbols", self.changed_symbols),
            ("Callers (outside diff)", self.callers),
            ("Related tests", self.related_tests),
            ("Symbols no test mentions", self.untested_symbols),
            ("Affected flows", self.flows),
        ):
            if not level:
                continue
            lines.append(f"**{label}:**")
            lines += [f"- `{m}`" for m in level[:MAX_PER_KIND]]
            if len(level) > MAX_PER_KIND:
                lines.append(f"- … {len(level) - MAX_PER_KIND} more")
            lines.append("")
        if self.note:
            lines.append(f"_{self.note}_")
        return "\n".join(lines).strip()

    @classmethod
    def from_json(cls, raw: dict, *, source: str) -> "ImpactReport":
        """Parse the result of an external provider.

        Unknown keys are ignored, missing keys default to empty: an external
        tool changing its format should not break an entire review session.
        """
        def extract(*names: str) -> list[str]:
            for t in names:
                v = raw.get(t)
                if isinstance(v, list):
                    return [str(x) for x in v if str(x).strip()]
            return []

        return cls(
            changed_symbols=extract("changed_symbols", "symbols", "changed"),
            callers=extract("callers", "affected", "dependents", "affected_files"),
            related_tests=extract("related_tests", "tests", "affected_tests"),
            untested_symbols=extract("untested_symbols", "missing_tests", "test_gaps"),
            flows=extract("flows", "affected_flows", "processes"),
            source=source,
            note=str(raw.get("note") or ""),
        )


# ------------------------------------------------------------ providers


def analyse(
    project: Path | str,
    changed: list[str],
    *,
    command: str = "",
    timeout: int = 120,
) -> ImpactReport:
    """Analyse the impact of a set of changed files.

    Uses the external command if provided; on failure, **falls back** to the
    built-in and says so, rather than returning empty. Silent empty is the
    worst outcome: the reviewer cannot distinguish "no impact" from "nobody
    computed it."
    """
    project = Path(project)
    changed = [c for c in changed if c]
    if not changed:
        return ImpactReport(source="no changes")

    if command.strip():
        got = _run_command(project, changed, command, timeout)
        if got is not None:
            return got
        fallback = builtin(project, changed)
        fallback.degraded = True
        fallback.note = (
            f"`review.impact_provider` failed, fell back to built-in: "
            f"{command.split()[0]}"
        )
        return fallback

    return builtin(project, changed)


def _run_command(
    project: Path, changed: list[str], command: str, timeout: int
) -> ImpactReport | None:
    """Run the external provider. Returns ``None`` if the result is unusable.

    The contract is intentionally simple so any tool can plug in: receives
    file list via stdin (one file per line), returns JSON on stdout.
    """
    try:
        proc = subprocess.run(
            split_command(command),
            cwd=project,
            input="\n".join(changed),
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        raw = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    return ImpactReport.from_json(raw, source=command.split()[0])


#: Exported names, by language family. Intentionally only catches **export
#: declarations**: local variables are not worth searching across the repo.
#: Group 1 = kind, group 2 = name.
_EXPORTS = (
    # `[ \t]*` not `\s*`: `\s` swallows preceding blank lines and shifts
    # the definition's line number by that many lines.
    re.compile(r"^[ \t]*export\s+(?:default\s+)?(?:async\s+)?"
               r"(function|class|const|let|var|interface|type|enum)\s+(\w+)", re.M),
    re.compile(r"^[ \t]*(?:public\s+|async\s+)?(def|class|func|fn)\s+(\w+)", re.M),
)

#: Names shorter than this are not worth searching: `id`, `run`, `get` match everywhere.
MIN_NAME_LEN = 4
#: Names defined in more than this many files are common names (`save`, `render`)
#: — Aider down-weights them x0.1; previously `builtin` let them fill up
#: `callers` then silently cut at MAX_PER_KIND (ADR-005 §9, finding 5).
COMMON_DEFS = 5


def _read(path: Path) -> str | None:
    if not path.is_file() or path.suffix not in SOURCE_EXT:
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def symbols(project: Path | str, files=None) -> dict[str, list[tuple[str, int, str]]]:
    """{file: [(name, line, kind)]} — exported names per file.

    Excludes `_private` names (Aider: not worth searching outside the file)
    and names shorter than `MIN_NAME_LEN`. ``files`` are relative paths;
    ``None`` = entire repo.
    """
    project = Path(project)
    out: dict[str, list[tuple[str, int, str]]] = {}
    for rel in (files if files is not None else _rel_files(project)):
        body = _read(project / rel)
        if body is None:
            continue
        found = []
        for pat in _EXPORTS:
            for m in pat.finditer(body):
                kind, name = m.group(1), m.group(2)
                if len(name) < MIN_NAME_LEN or name.startswith("_"):
                    continue
                found.append((name, body.count("\n", 0, m.start()) + 1, kind))
        if found:
            out[rel] = sorted(set(found), key=lambda t: t[1])
    return out


def refs(project: Path | str, names, files=None) -> dict[str, dict[str, int]]:
    """{name: {file: mention_count}} — **one** repo scan for all names.

    Takes all names at once instead of one per call: 50 names x 500 files
    re-scanning per name is 25,000 reads, batching reduces it to 500.
    """
    project = Path(project)
    names = sorted({n for n in names if n}, key=len, reverse=True)
    out: dict[str, dict[str, int]] = {n: {} for n in names}
    if not names:
        return out
    pat = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\b")
    for rel in (files if files is not None else _rel_files(project)):
        body = _read(project / rel)
        if body is None:
            continue
        for name, k in Counter(pat.findall(body)).items():
            out[name][rel] = k
    return out


def weights(project: Path | str, names, files=None) -> dict[str, float]:
    """Weight per name using three Aider rules: `_private` -> 0, defined in
    > `COMMON_DEFS` files -> x0.1, otherwise 1. The third rule (sqrt of
    mention count) is applied at score accumulation, not here."""
    defs: Counter = Counter()
    for syms in symbols(project, files).values():
        defs.update({n for n, _, _ in syms})
    return {
        n: 0.0 if n.startswith("_") else (0.1 if defs[n] > COMMON_DEFS else 1.0)
        for n in names
    }


def builtin(project: Path | str, changed: list[str]) -> ImpactReport:
    """Built-in fallback: find exported names then search for references by text.

    Rough compared to a real call graph — name collisions produce false
    positives, dynamic calls are invisible — but works immediately, requires
    no installation, and answers the most expensive question: **which changed
    names are not mentioned by any test**. The most frequent failure pattern
    on e9 is exactly that kind.

    File score = sum(weight(name) * sqrt(mention_count)); files below 1 point
    (only matched common names) are dropped, the rest are sorted by score
    before cutting at `MAX_PER_KIND` — `save`/`render` no longer push real
    callers out of the list.
    """
    project = Path(project)
    rep = ImpactReport(source="builtin (name-based search)", degraded=True)
    changed_set = set(changed)

    names = sorted({n for syms in symbols(project, changed).values() for n, _, _ in syms})
    if not names:
        rep.note = "no exported names found in changed files"
        return rep
    rep.changed_symbols = names

    files = list(_rel_files(project))
    w = weights(project, names, files)
    score: dict[str, float] = defaultdict(float)
    nhac: set[str] = set()      # names mentioned by at least one test
    for name, per_file in refs(project, names, files).items():
        for rel, n in per_file.items():
            # The changed file itself is not a "caller" of itself; tests
            # **within** the diff do count — stories often write tests next to code.
            if rel in changed_set and not is_test_path(rel):
                continue
            score[rel] += w[name] * math.sqrt(n)
            if is_test_path(rel):
                nhac.add(name)

    kept = sorted((rel for rel, s in score.items() if s >= 1.0), key=lambda r: (-score[r], r))
    rep.callers = [r for r in kept if not is_test_path(r)]
    rep.related_tests = [r for r in kept if is_test_path(r)]
    rep.untested_symbols = sorted(set(names) - nhac)
    return rep


def _rel_files(project: Path):
    """Relative (posix) paths of all source files in the repo."""
    for f in _source_files(project):
        yield f.relative_to(project).as_posix()


def _source_files(project: Path):
    bo_qua = {
        "node_modules", ".git", "dist", "build", "__pycache__", ".venv",
        "venv", "target", ".next", "coverage", "_bmad-output", ".aisef", ".claude",
    }
    for f in sorted(project.rglob("*")):
        if not f.is_file() or f.suffix not in SOURCE_EXT:
            continue
        if bo_qua & set(f.parts):
            continue
        yield f


__all__ = [
    "COMMON_DEFS",
    "MAX_PER_KIND",
    "ImpactReport",
    "analyse",
    "builtin",
    "is_test_path",
    "refs",
    "symbols",
    "weights",
]
