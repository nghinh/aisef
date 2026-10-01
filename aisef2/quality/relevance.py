"""RFC §15.2 — relevance (WP-5.2): did the story's own tests, as they actually ran, touch the story's change?

Cycle-1 minimum: `RELEVANT` when at least one **actually executed** story-owned developer test intersects at least
one **executable changed line** of the story diff. Three values and nothing else:

* **RELEVANT** — a story-owned case that executed (WP-5.1: `EXECUTED`, not skipped) intersects a changed executable
  line of a line-addressable artefact, or accessed a changed non-line-addressable artefact, under a measurement
  whose capability is `FULL`.
* **IRRELEVANT** — every changed product artefact was measurable (its required capability `FULL`) and no executed
  story-owned case intersects any of them. Only a measurement can say this.
* **UNMEASURABLE** — some changed product artefact could not be measured: its required capability is `UNAVAILABLE`,
  `PARTIAL`, nothing can measure that kind of artefact, or the change is a **deletion**: a hunk that removes
  executable lines and adds none, or a deleted file, leaves no candidate line or file for the cycle-1 candidate-side
  measurement to observe, and §15.2 defines no deletion-specific capability (WP52-002; §33's sensitivity evidence,
  deferred, would be one). Capability absence or inability is never `IRRELEVANT`; UNMEASURABLE is not the
  developer's failure and charges nothing by itself (§15.3: INCOMPLETE, never blocking).

A **tests-only diff** is not a deletion: the product change set is empty, the required measurement is fully possible,
and it proves no intersection — IRRELEVANT by the frozen definition (and §15.1's neutralised candidate is the
candidate itself, so the same story is VACUOUS): the story's tests demonstrate nothing about a product change.

What is measured and by what: a `.py` artefact is line-addressable — its executable lines come from its own code
objects (`executable_lines`) and the required capability is `line-coverage`; any other artefact is
non-line-addressable — no line approximation is forced; the capability-specific measurement is `artefact-access`
(the case opened the file while it ran). Branch intersection (`branch-coverage`, arcs from a changed executable
line) is recorded as stronger evidence when the runner provides it and never required: the value never depends on
it. The developer's own test files are part of the story diff but not of the product change: a test always executes
its own new lines, so they are excluded from the intersection domain.

Nothing here reads prose, filenames or model output for control: the diff is the typed `StoryDiff` parsed from a
unified patch, the measurement is the runner's typed `ResultSet`, and the execution is WP-5.1's `TestExecution`
(relevance is defined only when it is `EXECUTED`; a case that did not run cannot make anything RELEVANT).
"""

from __future__ import annotations

import os
import pathlib
import re
import types
from dataclasses import dataclass

from aisef2.arch.enums import Enforcement, Relevance, TestExecutionStatus
from aisef2.errors import InvariantError
from aisef2.quality.test_execution import (
    ARTEFACT_ACCESS, BRANCH_COVERAGE, LINE_COVERAGE, DeveloperTests, ResultSet, TestExecution, _norm,
)

__all__ = ["ChangedArtefact", "StoryDiff", "Intersection", "RelevanceResult", "story_diff", "line_addressable",
           "executable_lines", "measure"]


# ------------------------------------------------------------------------------------------------ the story diff

@dataclass(frozen=True)
class ChangedArtefact:
    path: str                 # relative to the candidate root, '/'-separated
    lines: frozenset[int]     # line numbers at the candidate that the diff added or modified
    removed: int = 0          # lines removed by hunks that add nothing (a deleted file: all of them) — unobservable

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path or os.path.isabs(self.path):
            raise InvariantError("a changed artefact is named by a relative path under the candidate root")
        if not isinstance(self.lines, frozenset) or not all(isinstance(n, int) and n > 0 for n in self.lines):
            raise InvariantError("changed lines are positive candidate line numbers")
        if not isinstance(self.removed, int) or self.removed < 0:
            raise InvariantError("removed lines are counted")
        if not self.lines and not self.removed:
            raise InvariantError("a changed artefact changes something: candidate lines, or removed lines")


@dataclass(frozen=True)
class StoryDiff:
    artefacts: tuple[ChangedArtefact, ...]


_HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _name(line: str, prefix: str) -> str | None:
    name = line[4:].split("\t")[0].strip()
    return None if name == "/dev/null" else _norm(name.removeprefix(prefix))  # git's a/ b/ prefixes; difflib: as given


def story_diff(patch: str) -> StoryDiff:
    """The typed story diff of a unified patch (git or difflib): per artefact at the candidate, the line numbers the
    patch added or modified, and the lines removed by hunks that add nothing (a deleted file, `+++ /dev/null`, keeps
    its `---` name and counts every line removed). Hunk lengths drive the parse, so content lines that look like
    headers cannot confuse it."""
    lines: dict[str, set[int]] = {}
    removed: dict[str, int] = {}
    path: str | None = None
    old_path: str | None = None
    old_left = new_left = 0
    new_line = added = dropped = 0

    def close_hunk() -> None:
        if path is not None and dropped and not added:
            removed[path] = removed.get(path, 0) + dropped

    for line in patch.splitlines():
        if old_left <= 0 and new_left <= 0:
            close_hunk()
            added = dropped = 0
            if line.startswith("--- "):
                old_path = _name(line, "a/")
            elif line.startswith("+++ "):
                path = _name(line, "b/") or old_path
                if path is not None:
                    lines.setdefault(path, set())
            elif (m := _HUNK.match(line)) and path is not None:
                old_left, new_line, new_left = int(m.group(1) or 1), int(m.group(2)), int(m.group(3) or 1)
            continue
        if line.startswith("+"):
            lines[path].add(new_line)
            new_line, new_left, added = new_line + 1, new_left - 1, added + 1
        elif line.startswith("-"):
            old_left, dropped = old_left - 1, dropped + 1
        elif line.startswith("\\"):
            pass  # "\ No newline at end of file" belongs to no side
        else:
            new_line, new_left, old_left = new_line + 1, new_left - 1, old_left - 1
    close_hunk()
    return StoryDiff(tuple(ChangedArtefact(p, frozenset(n), removed.get(p, 0)) for p, n in sorted(lines.items())
                           if n or removed.get(p)))


# ------------------------------------------------------------------------------------------------ what can be measured

def line_addressable(path: str) -> bool:
    """Line intersection is meaningful for Python source and nothing else in cycle 1 (no line approximation is
    forced on any other artefact: that one uses its capability-specific measurement or is UNMEASURABLE)."""
    return path.endswith(".py")


def executable_lines(candidate: str | os.PathLike, path: str) -> frozenset[int] | None:
    """The executable lines of a line-addressable artefact at the candidate — the lines its own code objects carry —
    or None when the line capability cannot read it: not a `.py` file, absent, or one Python cannot compile."""
    p = pathlib.Path(candidate, path)
    if not line_addressable(path):
        return None
    try:
        code = compile(p.read_bytes(), str(p), "exec")
    except (SyntaxError, ValueError, OSError):
        return None
    out: set[int] = set()
    stack = [code]
    while stack:
        c = stack.pop()
        out.update(n for _, _, n in c.co_lines() if n)  # None and 0 carry no source line
        stack.extend(k for k in c.co_consts if isinstance(k, types.CodeType))
    return frozenset(out)


# ------------------------------------------------------------------------------------------------ the result

@dataclass(frozen=True)
class Intersection:
    case_id: str
    path: str
    lines: frozenset[int]     # the changed executable lines the case executed; empty for an accessed artefact


@dataclass(frozen=True)
class RelevanceResult:
    relevance: Relevance
    intersections: tuple[Intersection, ...]          # what makes it RELEVANT (empty otherwise)
    branch_intersections: tuple[Intersection, ...]   # stronger evidence when arcs were measured; never required
    unmeasured: tuple[tuple[str, str], ...]          # (artefact, why) for every artefact no capability could measure
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.relevance, Relevance):
            raise InvariantError("relevance is one of RELEVANT, IRRELEVANT, UNMEASURABLE (§15.2)")
        if (self.relevance is Relevance.RELEVANT) != bool(self.intersections):
            raise InvariantError("RELEVANT is exactly a measured intersection (§15.2)")
        if self.relevance is Relevance.IRRELEVANT and self.unmeasured:
            raise InvariantError("IRRELEVANT is said only when every artefact was measured — capability absence is "
                                 "UNMEASURABLE, never IRRELEVANT (§15.2)")
        if self.relevance is Relevance.UNMEASURABLE and not self.unmeasured:
            raise InvariantError("UNMEASURABLE names the artefact no capability could measure")


def measure(execution: TestExecution, result_set: ResultSet, tests: DeveloperTests, diff: StoryDiff,
            candidate: str | os.PathLike) -> RelevanceResult:
    """§15.2 on typed inputs: WP-5.1's execution and result set, the story diff, the candidate tree."""
    if execution.status is not TestExecutionStatus.EXECUTED:
        raise InvariantError("relevance is defined only when the execution is EXECUTED (§15)")
    ran = [c.id for c in result_set.cases if tests.owns(c.path) and c.outcome != "skipped"]
    level = {k: result_set.capabilities.get(k, Enforcement.UNAVAILABLE) for k in (LINE_COVERAGE, ARTEFACT_ACCESS, BRANCH_COVERAGE)}
    hits: list[Intersection] = []
    branches: list[Intersection] = []
    unmeasured: list[tuple[str, str]] = []
    for artefact in diff.artefacts:
        if tests.owns(artefact.path):
            continue  # the developer's own test file: part of the diff, not of the product change
        needs = LINE_COVERAGE if line_addressable(artefact.path) else ARTEFACT_ACCESS
        if level[needs] is not Enforcement.FULL:
            unmeasured.append((artefact.path, f"{needs} is {level[needs].value}"))
            continue
        if not pathlib.Path(candidate, artefact.path).exists():
            unmeasured.append((artefact.path, "deleted at the candidate: nothing is left for a candidate-side "
                                              "measurement to observe (§15.2 defines no deletion capability)"))
            continue
        if needs is LINE_COVERAGE:
            executable = executable_lines(candidate, artefact.path)
            if executable is None:
                unmeasured.append((artefact.path, f"{needs} cannot read it: not compilable at the candidate"))
                continue
            changed = artefact.lines & executable
            found = []
            for case in ran:
                hit = frozenset(result_set.lines.get(case, {}).get(artefact.path, ())) & changed
                if hit:
                    found.append(Intersection(case, artefact.path, hit))
                if level[BRANCH_COVERAGE] is Enforcement.FULL:
                    taken = frozenset(a for a, _ in result_set.arcs.get(case, {}).get(artefact.path, ())) & changed
                    if taken:
                        branches.append(Intersection(case, artefact.path, taken))
            hits.extend(found)
            if artefact.removed and not found:
                unmeasured.append((artefact.path, f"{artefact.removed} executable line(s) removed with nothing added: "
                                                  "no candidate line carries the deletion, so the candidate-side line "
                                                  "measurement cannot observe it (§15.2 defines no deletion capability)"))
        else:
            hits.extend(Intersection(case, artefact.path, frozenset())
                        for case in ran if artefact.path in result_set.accessed.get(case, ()))
    if hits:
        value = Relevance.RELEVANT
        why = f"{len(hits)} intersection(s) of executed story-owned tests with the change"
    elif unmeasured:
        value = Relevance.UNMEASURABLE
        why = f"{len(unmeasured)} changed artefact(s) no capability could measure: {unmeasured[0][1]}"
    else:
        value = Relevance.IRRELEVANT
        why = f"{len(ran)} executed story-owned test(s) measured; none intersects the change"
    return RelevanceResult(value, tuple(hits), tuple(branches), tuple(unmeasured), why)
