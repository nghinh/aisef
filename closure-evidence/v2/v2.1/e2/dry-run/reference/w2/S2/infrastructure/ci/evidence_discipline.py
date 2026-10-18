"""The evidence-discipline linter (story 10.8, AD-57).

The linter is the boring thing the story calls for: it scans the documentation
set, release notes, and a few designated places in the user-facing copy for
"figure-shaped" text -- numbers with a unit -- and requires each one to be
either:

- cited to a known `run_id` (an id in the run registry under
  `infrastructure/ci/run_registry.json`), or
- explicitly marked as a target with the prefix `target:`.

Targets are not measurements. AC5 is what makes the NFR-1 latency table itself
legal in the repo: the table names the SLO targets, not the achieved values.

A missing citation is reported with its file and line and fails the gate (AC3).
The linter is run as part of the standard backend quality gate, not as a manual
review step.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
RUN_REGISTRY: Path = REPO_ROOT / "infrastructure/ci/run_registry.json"

# requirements-delta §1: a directory root is walked for these suffixes, skipping these directories
SCAN_SUFFIXES: tuple[str, ...] = (".md", ".ts", ".tsx")
SKIP_DIRS: frozenset[str] = frozenset({"node_modules", "build", "dist"})


class RegistryError(ValueError):
    """requirements-delta §2.2: the run registry cannot be read as a list of run ids."""


def expand_roots(roots: Iterable[Path]) -> list[Path]:
    """§1.1–1.3: a directory root yields every .md/.ts/.tsx file under it (sorted by path; dot-directories,
    node_modules, build and dist not entered); a file root is scanned whatever its suffix."""
    files: list[Path] = []
    for root in roots:
        if not root.is_dir():
            files.append(root)
            continue
        found: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS)
            found.extend(Path(dirpath) / n for n in filenames if n.endswith(SCAN_SUFFIXES))
        files.extend(sorted(found, key=str))
    return files


def _display_path(path: Path) -> Path:
    """Show a path relative to the repo when it's inside the repo, else as-is."""
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


DOCS_GLOBS: tuple[str, ...] = (
    "docs/**/*.md",
    "_bmad-output/implementation-artifacts/**/*.md",
    "apps/web/**/*.{ts,tsx,md}",
)
"""The surfaces the linter walks (story 10.8 AC2).

User-facing copy lives in `apps/web`; release notes live in the implementation
artefacts; the docs tree holds the capacity and SLO pages. Source code prose is
intentionally not walked: a number in a code comment is a description of the
mechanism, not a claim about a measurement, and the AC2 surface is "documentation
set, release notes, or user-facing interface copy," not source files."""


# --- figure and citation grammars -------------------------------------------

# A "figure" is a number followed by a unit the SLO table or capacity page
# would naturally write. The grammar is intentionally narrow; the linter is
# honest about the false-negative risk in the README.
FIGURE_RE = re.compile(
    r"""
    (?<![A-Za-z0-9_.])              # left boundary: not part of a longer identifier
    (?P<value>\d+(?:\.\d+)?)        # the numeric value
    \s*
    (?P<unit>ms|seconds|s|m|kb|mb|gb|mhz|ghz|rps|rpm|fps|%|streams?)
    (?![A-Za-z0-9_])               # right boundary: not part of a longer identifier
    """,
    re.VERBOSE | re.IGNORECASE,
)

CITATION_RE = re.compile(
    r"""
    (?:
        run[_-]?id\s*[=:]\s*
        (?P<run>[a-zA-Z0-9_.-]+)
    )
    |
    (?:
        \(\s*run[_-]?id\s+(?P<run_paren>[a-zA-Z0-9_.-]+)\s*\)
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# An "uncited target" prefix. Anything starting with "target:" is an SLO target,
# not a measurement, and is allowed without a citation. Observed values marked
# "target:" would fail AC5 -- that case is detected separately.
TARGET_PREFIX = "target:"
UNVERIFIED_TOKEN = "benchmark.pending"  # noqa: S105
"""Tokens the linter accepts in lieu of a real run id while the benchmark has
not yet produced one. Every acceptance is reported so a reviewer can see how
much of the repo is still keyed on a placeholder."""


@dataclass(frozen=True, slots=True)
class Finding:
    file: Path
    line_number: int
    line: str
    figure: str
    reason: str


@dataclass(frozen=True, slots=True)
class ScanResult:
    findings: tuple[Finding, ...]
    accepted_targets: int
    accepted_placeholders: int


def _git_ls_files(globs: Iterable[str]) -> list[Path]:
    """List repository-tracked files matching the globs.

    Going through `git ls-files` keeps the scanner out of `.venv`, `node_modules`,
    `build/`, and any untracked scratchpad a developer left in the tree. A file
    that isn't in the tree isn't a published claim.
    """
    args = ["git", "ls-files", "--"]
    args.extend(globs)
    try:
        result = subprocess.run(  # noqa: S603
            args, capture_output=True, text=True, check=False, cwd=REPO_ROOT
        )
    except OSError:
        return []
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line]


def load_run_registry(path: str | Path = RUN_REGISTRY) -> set[str]:
    """Return the set of currently valid run ids (§2.2: a registry that cannot be read, is not JSON, or is not an
    object whose `valid_runs` is a list of strings raises RegistryError naming the path)."""
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise RegistryError(f"{path}: cannot be read ({e.__class__.__name__})") from e
    except json.JSONDecodeError as e:
        raise RegistryError(f"{path}: not JSON ({e})") from e
    ids = payload.get("valid_runs") if isinstance(payload, dict) else None
    if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
        raise RegistryError(f"{path}: not a JSON object whose valid_runs is a list of strings")
    return set(ids)


def _is_target_line(line: str, span: tuple[int, int]) -> bool:
    """True if the figure at `span` sits inside a target marker (AC5).

    A *target* is identified by the prefix `target:` (case-insensitive). A line
    that opens with `observed:` / `measured:` / `recorded:` / `achieved:` is an
    observation no matter what other words surround it, so it never counts as a
    target. The check is anchored to the start of the head so an embedded phrase
    like "the observed target was..." is not mistaken for an observation -- only
    lines that *open* with the observation marker are treated as observations.
    """
    head = line[: span[0]]
    lowered = head.lower()
    observation_prefixes = ("observed:", "measured:", "recorded:", "achieved:")
    if any(lowered.lstrip().startswith(prefix) for prefix in observation_prefixes):
        return False
    return TARGET_PREFIX in lowered


def _has_citation(line: str) -> bool:
    return CITATION_RE.search(line) is not None


def _has_placeholder(line: str) -> bool:
    return UNVERIFIED_TOKEN in line.lower()


def _skip_line(line: str, *, in_fence: bool) -> tuple[bool, bool]:
    """Skip blank lines, fenced code blocks, and pure comment lines.

    Returns `(should_skip, in_fence_after)`. The fence tracker is stateful so a
    triple-backtick fence opened on one line suppresses every line until the next
    fence, which is the markdown / Python convention.
    """
    stripped = line.strip()
    if stripped.startswith("```"):
        return True, not in_fence
    if in_fence:
        return True, True
    if not stripped:
        return True, False
    if stripped.startswith(("#", "//", '"""', "'''")):
        return True, False
    if stripped.startswith(("<!--", "-->")):
        return True, False
    if line.startswith(("    ", "\t")):
        return True, False
    return False, False


def scan_repository(
    *,
    run_ids: Iterable[str] | None = None,
    roots: Iterable[Path] | None = None,
) -> ScanResult:
    """Walk the surfaces and report uncited figures."""
    registry = set(run_ids) if run_ids is not None else load_run_registry()
    files = roots if roots is not None else _git_ls_files(DOCS_GLOBS)
    findings: list[Finding] = []
    accepted_targets = 0
    accepted_placeholders = 0

    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        in_fence = False
        for line_number, line in enumerate(lines, start=1):
            skip, in_fence = _skip_line(line, in_fence=in_fence)
            if skip:
                continue
            for match in FIGURE_RE.finditer(line):
                figure = match.group(0)
                span = match.span()
                if _is_target_line(line, span):
                    accepted_targets += 1
                    continue
                citations = [
                    (m.group("run") or m.group("run_paren") or "")
                    for m in CITATION_RE.finditer(line)
                ]
                if citations and any(c in registry for c in citations):
                    if any(c == UNVERIFIED_TOKEN for c in citations):
                        accepted_placeholders += 1
                    continue
                if _has_placeholder(line):
                    accepted_placeholders += 1
                    continue
                findings.append(
                    Finding(
                        file=_display_path(path),
                        line_number=line_number,
                        line=line.strip(),
                        figure=figure,
                        reason="uncited figure (AD-57)",
                    )
                )
    return ScanResult(
        findings=tuple(findings),
        accepted_targets=accepted_targets,
        accepted_placeholders=accepted_placeholders,
    )


def cli_main(argv: list[str] | None = None) -> int:
    """CLI entry: return non-zero on uncited figures so the gate fails."""
    import argparse

    parser = argparse.ArgumentParser(description="Evidence-discipline linter (story 10.8)")
    parser.add_argument(
        "--root",
        type=Path,
        action="append",
        default=None,
        help="explicit root path (may repeat); overrides the tracked globs",
    )
    parser.add_argument("--report", type=Path, default=None, help="write JSON report")
    parser.add_argument("--registry", type=Path, default=RUN_REGISTRY, help="the run registry file (§2.1)")
    args = parser.parse_args(argv)

    for root in args.root or ():
        if not root.exists():          # §1.4: one message naming the path as given, nothing scanned, exit 2
            print(f"root not found: {root}", file=sys.stderr)
            return 2
    try:
        run_ids = load_run_registry(args.registry)
    except RegistryError as e:         # §2.2: one line, nothing scanned, exit 2
        print(f"run registry: {e}", file=sys.stderr)
        return 2
    roots: list[Path] | None = expand_roots(args.root) if args.root else None
    result = scan_repository(run_ids=run_ids, roots=roots)
    document = json.dumps(
        {
            "findings": [
                {
                    "file": str(finding.file),
                    "line": finding.line_number,
                    "figure": finding.figure,
                    "reason": finding.reason,
                    "text": finding.line,
                }
                for finding in result.findings
            ],
            "accepted_targets": result.accepted_targets,
            "accepted_placeholders": result.accepted_placeholders,
        },
        indent=2,
    )
    for finding in result.findings:
        print(f"{finding.file}:{finding.line_number}: {finding.figure!r} -- {finding.reason}")
        print(f"    {finding.line}")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(document, encoding="utf-8")
    return 1 if result.findings else 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
