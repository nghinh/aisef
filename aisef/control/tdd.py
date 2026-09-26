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
from . import proof
from .acceptance import coverage
from .impact import is_test_path

TEST_FUNC = re.compile(r"^\s*(def test_|it\(|test\(|func Test)", re.MULTILINE)


def _git(cwd: Path | str, *args: str) -> str:
    try:
        p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
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


def runs_before_last_green(evidence: Evidence) -> list:
    """Non-ok, non-skipped `test` runs positioned before the last green one.

    Position in the (time-ordered) evidence, never `seq`: sequence numbers restart when a writer could not read the
    file's tail (bug 42) and are audit metadata, not order (SS-T1, INV-D.2). This is only the ordering; whether such
    a run shows anything about the story is `proven_red_before_green`'s question."""
    runs = evidence.of(TOOL_RUN, "test")
    greens = [e for e in runs if e.ok]
    if not greens:
        return []
    last_green_at = runs.index(greens[-1])
    return [e for e in runs[:last_green_at] if (not e.ok) and not e.detail.get("skipped")]


def tdd_subjects(detail: dict, story_id: str, acceptance: int, added_tests: list[str],
                 codes: list[str] | None = None) -> list[str]:
    """The tests TDD is about: the story's criterion tests green in the last green run; failing codes, the green
    tests declared in the files the story added."""
    green = [t for t in (detail.get("test_ids") or []) if t in proof.executed_green(detail)]
    if acceptance > 0:
        # V2: only criteria the plan declares CHANGE_REQUIRED have a red-before-green obligation (`codes`); with no
        # declaration the subject is every criterion, as it was under policy V1.
        want = {c for c in (codes or [])}
        ac = [t for i, ts in coverage(story_id, acceptance, green).items() for t in ts
              if not want or f"AC-{story_id}-{i}" in want]
        if ac or want:
            # With declared obligations the subject list is exactly those criteria's tests — empty means there is
            # nothing for TDD to have seen fail, not "fall back to every test the story added" (policy V2).
            return list(dict.fromkeys(ac))
    added = set(added_tests or [])
    return [t for t in green if "::" in t and t.split("::", 1)[0] in added]


def proven_red_before_green(evidence: Evidence, story_id: str, *, acceptance: int, added_tests: list[str],
                            changed: list[str], codes: list[str] | None = None):
    """The earliest run before the last green that PROVES the story's tests red (SS-83), or None.

    The old rule took any non-ok run: a run that never executed (tool or environment failure) and a run red only
    because an unrelated test failed both passed TDD. Now a run counts only if, read through the proof model, at
    least one of the story's tests in it is RED_EXECUTED or RED_COLLECTION_BOUND_TO_STORY."""
    runs = evidence.of(TOOL_RUN, "test")
    greens = [e for e in runs if e.ok]
    if not greens:
        return None
    subjects = tdd_subjects(greens[-1].detail, story_id, acceptance, added_tests, codes)
    if not subjects:
        return None
    story_files = [f for f in (changed or []) if not is_test_path(f)]
    files = proof.files_of(subjects, story_id, acceptance, None)
    return next((e for e in runs_before_last_green(evidence)
                 if proof.run_proves_red(e.detail, subjects, story_files, files=files)), None)


def test_delta(workdir: Path | str, *, base_ref: str, changed: list[str]) -> list[str]:
    """Existing test files whose test-case count decreased: `"path: 5 -> 3"`."""
    if not base_ref:
        return []
    workdir = Path(workdir)
    out = []
    for f in changed:
        if not is_test_path(f):
            continue
        before = _git(workdir, "show", f"{base_ref}:{f}")
        if not before:
            continue
        p = workdir / f
        after = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
        n0, n1 = len(TEST_FUNC.findall(before)), len(TEST_FUNC.findall(after))
        if n1 < n0:
            out.append(f"{f}: {n0} → {n1}")
    return out
