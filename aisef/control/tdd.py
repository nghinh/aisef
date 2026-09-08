"""TDD verifiability (G8): red before green, and existing tests must not weaken.

The prompt has long required "write the test first, see it fail"; this is the
first machine check. Two signals, one blocking, one advisory:

1. **Red before green** — if a story *adds* tests (new test file, or new lines
   containing ``AC-<story>-``), the evidence must show a ``test`` failure
   **before** the final green run. Green from the start does not prove the test
   checks anything. Stories that add no tests (pure refactors) are exempt.
2. **Test disappearance** — if a test file present at the branch point has
   fewer test cases, surface the file name and counts to the reviewer.
   Not auto-blocking: "updating expectations" is valid and needs judgment.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..harness.observe import TOOL_RUN, Evidence
from .impact import is_test_path

TEST_FUNC = re.compile(r"^\s*(def test_|it\(|test\(|func Test)", re.MULTILINE)


def _git(cwd: Path | str, *args: str) -> str:
    try:
        p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ""
    return p.stdout if p.returncode == 0 else ""


def added_tests(workdir: Path | str, *, base_ref: str, changed: list[str], story_id: str) -> list[str]:
    """Test files **added** by the story: new relative to the branch point
    (including untracked), or containing new lines with the story's AC id."""
    workdir = Path(workdir)
    tests = [f for f in changed if is_test_path(f)]
    if not tests:
        return []
    o_goc = set()
    if base_ref:
        o_goc = {l.strip() for l in _git(workdir, "ls-tree", "-r", "--name-only", base_ref).splitlines()}
    out = []
    for f in tests:
        if f not in o_goc:
            out.append(f)                       # new file
            continue
        diff = _git(workdir, "diff", base_ref, "--", f) if base_ref else _git(workdir, "diff", "HEAD", "--", f)
        if any(l.startswith("+") and not l.startswith("+++") and f"AC-{story_id}-" in l.replace("_", "-")
               for l in diff.splitlines()):
            out.append(f)                       # new AC has test
    return out


def red_before_green(evidence: Evidence) -> bool:
    """True if a real (non-skipped) `test` failure exists before the last green run."""
    runs = evidence.of(TOOL_RUN, "test")
    greens = [e for e in runs if e.ok]
    if not greens:
        return False
    last_green = greens[-1]
    return any((not e.ok) and not e.detail.get("skipped") and e.seq < last_green.seq for e in runs)


def test_delta(workdir: Path | str, *, base_ref: str, changed: list[str]) -> list[str]:
    """Existing test files whose test-case count decreased: `"path: 5 -> 3"`."""
    if not base_ref:
        return []
    workdir = Path(workdir)
    out = []
    for f in changed:
        if not is_test_path(f):
            continue
        truoc = _git(workdir, "show", f"{base_ref}:{f}")
        if not truoc:
            continue
        p = workdir / f
        sau = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
        n0, n1 = len(TEST_FUNC.findall(truoc)), len(TEST_FUNC.findall(sau))
        if n1 < n0:
            out.append(f"{f}: {n0} → {n1}")
    return out
