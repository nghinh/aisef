"""RFC §15.1 — vacuity, the candidate-side control (WP-5.3): do the story's own tests depend on the story's own
product change?

The experiment, exactly as frozen: take the candidate, neutralise the story's own **product** hunks in a scratch copy,
leave the developer's test files intact, run the story-owned tests there. Three values and nothing else:

* **NON_VACUOUS** — only when all four conditions hold: (1) the reconstructed tree is runnable, (2) the runner
  executes and (3) the intended story-owned tests actually execute — both read from WP-5.1's typed values, EXECUTED
  and STORY_TESTS_RAN — and (4) the failure is an assertion failure **attributable to the removal**: a story-owned case
  that passed at the candidate and, in the neutralised tree whose only difference is the neutralisation, fails by
  assertion. That attribution is a per-case comparison of typed runner facts, never a reading of prose.
* **VACUOUS** — the same conditions 1–3 hold and every intended story-owned case still passes without the story's
  product change: the tests demonstrate nothing about it. Engineering-quality evidence only; never a product verdict.
* **INDETERMINATE** — non-vacuity could not be proven: the story's tests do not pass at the candidate (no
  counterfactual to attribute), the scratch tree could not be reconstructed deterministically (a hunk that does not
  match the candidate, an opaque patch, a deletion whose content the patch does not carry), the runner could not
  execute (UNRUNNABLE), the story's tests could not be collected or did not actually run, an intended case ended in
  an exception rather than an assertion (its cause is not established), or a failure fell on a case that was not
  intended. INDETERMINATE is never NON_VACUOUS and never a developer failure here (§15.3 maps it to INCOMPLETE).

Neutralisation is deterministic and bounded: the scratch tree is a copy of the candidate (never of any other
revision) minus the story's added product files, with every story product hunk reverse-applied **exactly** — the
hunk's candidate-side lines must be found verbatim at the hunk's candidate position, or the reconstruction fails. A
deleted product file is rebuilt from the content the patch carries. Files the story's DeveloperTests own are copied
untouched; so is everything outside the story diff. Invariant IX: nothing here takes, resolves or runs anything at a
parent revision — the only tree the runner ever sees is the scratch copy the controller made from the candidate.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from aisef2.arch.enums import TestExecutionStatus, TestOutcome, TestSelection, Vacuity
from aisef2.errors import InvariantError
from aisef2.quality.relevance import _HUNK, _name
from aisef2.quality.test_execution import (
    _TIMEOUT_S, Dependencies, DeveloperTests, Runner, RunnerReport, TestExecution, execute,
)
from aisef2.runtime.process_range import ProcessRange

__all__ = ["Hunk", "FilePatch", "file_patches", "Neutralisation", "neutralise", "VacuityResult", "evaluate"]

_IGNORED_DIRS = frozenset({".git", "__pycache__", ".aisef"})
#: what may stand between hunks in a git patch besides ---/+++/@@/Binary; anything else is content the parse cannot place
_HEADERS = ("diff ", "index ", "similarity ", "dissimilarity ", "rename ", "copy ", "new file mode", "deleted file mode",
            "old mode", "new mode")


# ------------------------------------------------------------------------------------------------ the typed patch

@dataclass(frozen=True)
class Hunk:
    new_start: int
    new_count: int
    lines: tuple[tuple[str, str], ...]   # (tag, text): tag is ' ', '-' or '+'; text without its newline

    def side(self, tag: str) -> list[str]:
        return [text for t, text in self.lines if t in (" ", tag)]


@dataclass(frozen=True)
class FilePatch:
    path: str                  # the artefact at the candidate (its new name; a deleted file keeps its old name)
    added: bool                # the story created the file (--- /dev/null)
    deleted: bool              # the story deleted the file (+++ /dev/null)
    hunks: tuple[Hunk, ...]
    opaque: bool = False       # the patch names the file but carries no reconstructible content (binary, truncated)


def file_patches(patch: str) -> tuple[FilePatch, ...]:
    """A unified patch (git or difflib), typed per file with its hunks' content. Hunk lengths drive the parse."""
    out: list[FilePatch] = []
    old_path = new_path = None
    hunks: list[Hunk] = []
    lines: list[tuple[str, str]] = []
    header: tuple[int, int] | None = None
    old_left = new_left = 0
    opaque = False

    def close_hunk() -> None:
        nonlocal header, lines, opaque
        if header is not None:
            if old_left > 0 or new_left > 0:
                opaque = True  # the hunk ends before the lines its header declares: truncated
            hunks.append(Hunk(header[0], header[1], tuple(lines)))
        header, lines = None, []

    def close_file() -> None:
        nonlocal old_path, new_path, hunks, opaque
        close_hunk()
        if old_path is not None or new_path is not None:
            path = new_path if new_path is not None else old_path
            out.append(FilePatch(path, old_path is None, new_path is None, tuple(hunks), opaque or not hunks))
        old_path = new_path = None
        hunks, opaque = [], False

    for line in patch.splitlines():
        if old_left <= 0 and new_left <= 0:
            old_left = new_left = 0
            if line.startswith("--- "):
                if old_path is not None or new_path is not None:
                    close_file()
                old_path = _name(line, "a/")
            elif line.startswith("+++ "):
                new_path = _name(line, "b/")
            elif line.startswith("Binary files "):
                if old_path is not None or new_path is not None:
                    close_file()
                names = line[len("Binary files "):].rsplit(" differ", 1)[0].split(" and ")
                if len(names) == 2:  # no hunk can follow: the file is opaque by having none
                    old_path = _name("--- " + names[0], "a/")
                    new_path = _name("+++ " + names[1], "b/")
            elif (m := _HUNK.match(line)) and (old_path is not None or new_path is not None):
                close_hunk()
                old_left, new_left = int(m.group(1) or 1), int(m.group(3) or 1)
                header = (int(m.group(2)), new_left)
            elif line and not line.startswith(_HEADERS + ("\\",)) and (old_path is not None or new_path is not None):
                opaque = True  # a line between hunks that no header explains: content the parse cannot place
            continue
        if line.startswith("\\"):
            continue  # "\ No newline at end of file": not a line of either side
        tag, text = line[:1], line[1:]
        if tag == "+":
            new_left -= 1
        elif tag == "-":
            old_left -= 1
        elif tag == " " or line == "":
            tag, new_left, old_left = " ", new_left - 1, old_left - 1
        else:
            opaque = True  # a line that is neither side's: the patch cannot be reconstructed from
            continue
        lines.append((tag, text))
    close_file()
    return tuple(out)


# ------------------------------------------------------------------------------------------------ reconstruction

def _reverse(text: str, hunks: Sequence[Hunk]) -> str | None:
    """`text` with every hunk reverse-applied exactly, or None when a hunk's candidate-side lines are not found
    verbatim at the hunk's candidate position (a reconstruction that is not deterministic is refused)."""
    body = text.split("\n")
    trailing = body and body[-1] == ""
    if trailing:
        body = body[:-1]
    for h in sorted(hunks, key=lambda h: h.new_start, reverse=True):
        after = h.side("+")
        start = h.new_start - 1 if h.new_count else h.new_start  # a hunk adding nothing sits after `new_start`
        if start < 0 or body[start:start + len(after)] != after:
            return None
        body[start:start + len(after)] = h.side("-")
    return "\n".join(body) + ("\n" if trailing or not text else "")


@dataclass(frozen=True)
class Neutralisation:
    root: str                            # the scratch tree: the candidate with the story's product hunks reversed
    neutralised: tuple[str, ...]         # product artefacts reverse-applied, rebuilt or left out
    kept: tuple[str, ...]                # story-owned test files in the diff, copied untouched
    problems: tuple[str, ...]            # why the reconstruction is not deterministic (empty: it is)


def neutralise(candidate: str | os.PathLike, patch: str, tests: DeveloperTests, scratch: str | os.PathLike) -> Neutralisation:
    """Copy the candidate into `scratch` (its .git and caches aside), leaving out the story's added product files,
    then reverse-apply every other story product hunk exactly. Test files the story owns are never touched."""
    source, root = pathlib.Path(candidate), pathlib.Path(scratch)
    patches = file_patches(patch)
    product = [p for p in patches if not tests.owns(p.path)]
    kept = tuple(p.path for p in patches if tests.owns(p.path))
    added = {p.path for p in product if p.added}
    problems: list[str] = []
    neutralised: list[str] = []

    def ignore(directory: str, names: list[str]) -> set[str]:
        rel = pathlib.Path(directory).relative_to(source).as_posix()
        return {n for n in names if n in _IGNORED_DIRS or (f"{rel}/{n}" if rel != "." else n) in added}

    shutil.copytree(source, root, ignore=ignore, symlinks=True)
    for p in product:  # in patch order
        if p.added:
            neutralised.append(p.path)  # left out of the copy above
            continue
        target = root / p.path
        if p.opaque:
            problems.append(f"{p.path}: the patch carries no reconstructible content for it")
            continue
        if p.deleted:
            if any(t == "+" for h in p.hunks for t, _ in h.lines) or target.exists():
                problems.append(f"{p.path}: a deleted file whose patch is not a plain removal")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("\n".join(t for h in p.hunks for _, t in h.lines) + "\n", encoding="utf-8")
            neutralised.append(p.path)
            continue
        if not target.is_file():
            problems.append(f"{p.path}: not a file at the candidate")
            continue
        restored = _reverse(target.read_text(encoding="utf-8"), p.hunks)
        if restored is None:
            problems.append(f"{p.path}: a hunk does not match the candidate at its position")
            continue
        target.write_text(restored, encoding="utf-8")
        neutralised.append(p.path)
    return Neutralisation(str(root), tuple(neutralised), kept, tuple(problems))


# ------------------------------------------------------------------------------------------------ the result

@dataclass(frozen=True)
class VacuityResult:
    vacuity: Vacuity
    neutralised: tuple[str, ...]          # what the counterfactual removed (empty for a tests-only story)
    attributed: tuple[str, ...]           # the intended cases whose assertion failure the removal caused
    execution: TestExecution | None       # WP-5.1's typed reading of the neutralised run (None: it never ran)
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.vacuity, Vacuity):
            raise InvariantError("vacuity is one of NON_VACUOUS, VACUOUS, INDETERMINATE (§15.1)")
        ran = self.execution is not None and self.execution.status is TestExecutionStatus.EXECUTED \
            and self.execution.selection is TestSelection.STORY_TESTS_RAN
        if self.vacuity is Vacuity.NON_VACUOUS and not (self.attributed and ran and self.execution.outcome is TestOutcome.FAILED):
            raise InvariantError("NON_VACUOUS is exactly an attributed assertion failure of an intended story-owned test "
                                 "in a neutralised tree where the story's tests executed (§15.1, all four conditions)")
        if self.vacuity is Vacuity.VACUOUS and not (ran and self.execution.outcome is TestOutcome.PASSED and not self.attributed):
            raise InvariantError("VACUOUS is exactly the story's tests executing and passing without the story's "
                                 "product change (§15.1)")
        if self.vacuity is Vacuity.INDETERMINATE and self.attributed:
            raise InvariantError("INDETERMINATE attributes nothing")


def evaluate(runner: Runner, candidate: str | os.PathLike, patch: str, tests: DeveloperTests, deps: Dependencies,
             baseline: tuple[RunnerReport, TestExecution], *, interpreter: str = sys.executable,
             targets: Sequence[str] | None = None, timeout_s: float = _TIMEOUT_S, env: Mapping[str, str] | None = None,
             on_range: Callable[[ProcessRange], None] | None = None) -> VacuityResult:
    """§15.1 on typed inputs: the candidate, the story's patch, the story's tests, and the candidate run WP-5.1
    already made (`baseline`). The neutralised run happens in a scratch copy the controller owns for the call."""
    report0, execution0 = baseline
    intended = sorted(c.id for c in (report0.result_set.cases if report0.result_set else ()) if tests.owns(c.path)
                      and c.outcome == "passed")
    if execution0.status is not TestExecutionStatus.EXECUTED or execution0.selection is not TestSelection.STORY_TESTS_RAN \
            or execution0.outcome is not TestOutcome.PASSED or not intended:
        return VacuityResult(Vacuity.INDETERMINATE, (), (), None,
                             "the story's tests do not execute and pass at the candidate: there is no counterfactual to attribute")
    with tempfile.TemporaryDirectory(prefix="aisef2-vacuity-") as work:
        n = neutralise(candidate, patch, tests, os.path.join(work, "tree"))
        if n.problems:
            return VacuityResult(Vacuity.INDETERMINATE, n.neutralised, (), None,
                                 "the neutralised tree could not be reconstructed deterministically: " + "; ".join(n.problems))
        report, execution = execute(runner, n.root, tests, deps, interpreter=interpreter, targets=targets,
                                    timeout_s=timeout_s, env=env, on_range=on_range)
    if execution.status is not TestExecutionStatus.EXECUTED:
        return VacuityResult(Vacuity.INDETERMINATE, n.neutralised, (), execution,
                             "the runner could not execute in the neutralised tree: " + (execution.reason or ""))
    if execution.selection is not TestSelection.STORY_TESTS_RAN:
        return VacuityResult(Vacuity.INDETERMINATE, n.neutralised, (), execution,
                             "the story's tests did not actually execute in the neutralised tree: " + (execution.reason or ""))
    outcome = {c.id: c.outcome for c in report.result_set.cases if tests.owns(c.path)}
    missing = [i for i in intended if outcome.get(i, "skipped") == "skipped"]
    if missing:
        return VacuityResult(Vacuity.INDETERMINATE, n.neutralised, (), execution,
                             f"{len(missing)} intended story-owned test(s) did not execute in the neutralised tree")
    errors = [i for i in intended if outcome[i] == "error"]
    if errors:
        return VacuityResult(Vacuity.INDETERMINATE, n.neutralised, (), execution,
                             f"{len(errors)} intended story-owned test(s) ended in an exception, not an assertion: "
                             "the cause is not established")
    attributed = tuple(i for i in intended if outcome[i] == "failed")
    if execution.outcome is TestOutcome.PASSED:
        return VacuityResult(Vacuity.VACUOUS, n.neutralised, (), execution,
                             f"{len(intended)} intended story-owned test(s) still pass without the story's product change")
    if attributed:
        return VacuityResult(Vacuity.NON_VACUOUS, n.neutralised, attributed, execution,
                             f"{len(attributed)} intended story-owned test(s) fail by assertion once the story's product "
                             f"change is neutralised ({', '.join(n.neutralised)})")
    return VacuityResult(Vacuity.INDETERMINATE, n.neutralised, (), execution,
                         "the neutralised run failed only in story-owned tests that were not intended: not attributable")
