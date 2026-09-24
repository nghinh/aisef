"""RFC §15.0 — test execution is typed, not boolean (WP-5.1).

Two axes, the discipline §10 applies to probes: **did the runner execute** (`TestExecutionStatus`), and only then
**what did it report** (`TestOutcome`, `TestSelection`). The V1 defect this removes (SS-96 inside the adequacy gate)
was a boolean that read "the tests did not run" as "the developer failed". Here that edge cannot be built:
`TestExecution.__post_init__` refuses an `UNRUNNABLE` that carries an outcome, a selection or any owner but
`ENVIRONMENT`, and `classify` is the only way a runner's report becomes one.

* **UNRUNNABLE** (rule 1): the runner, tool or environment could not execute — not launched, died by a signal, ran
  past the harness deadline, or reported no result set (a crash before reporting, a missing runner). Owner
  `ENVIRONMENT`, the environment retry policy. Never `DEVELOPER`, and downstream never `INADEQUATE` or `INCOMPLETE`.
* **EXECUTED**: the runner ran to completion and reported a result set. `outcome` is what the executed tests said;
  `selection` says whether the story's own tests actually ran (rule 3): `STORY_TESTS_RAN`,
  `NO_STORY_TESTS_MATCHED` (a developer selector/definition defect, owner `DEVELOPER`), or
  `STORY_TESTS_NOT_COLLECTABLE` — classified by the **cause the runner reported** (rule 4), read as a typed value the
  adapter produced, never as prose: an import that resolves to a declared environment dependency is `UNRUNNABLE` /
  `ENVIRONMENT` (SS-81(A)'s shape); one that resolves to the project's own source tree is owner `DEVELOPER`; a cause
  that cannot be determined is owner `INTEGRATION`, never `DEVELOPER`.
* Regression execution uses `classify` unchanged (rule 5): the developer tests it names are the regression selection.

What a runner did is a harness-produced `RunnerReport`: the adapters (`UNITTEST`, a harness-owned runner that
executes with the stdlib alone; `PYTEST`, read through its junit result set) turn a tool's own report into typed
cases and typed collection causes. The runner runs inside an owned process range (P4); nothing here signals a
process, and nothing here takes a parent revision — the only tree it knows is the candidate's (invariant IX).
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping, Sequence
from xml.etree import ElementTree

from aisef2.arch.enums import Enforcement, Owner, TestExecutionStatus, TestOutcome, TestSelection
from aisef2.errors import InvariantError
from aisef2.runtime.process_range import ProcessRange, RangeError

_GRACE_S = (1.0, 1.0)
_WAIT_S = 30.0
_TIMEOUT_S = 600.0

#: what a collection failure's cause can be, as an adapter reports it — the classifier reads nothing else
IMPORT, SYNTAX, OTHER = "IMPORT", "SYNTAX", "OTHER"
CASE_OUTCOMES = ("passed", "failed", "error", "skipped")
#: The measurements the harness-owned runner can take (WP-5.2 names which one an artefact needs)
LINE_COVERAGE, ARTEFACT_ACCESS, BRANCH_COVERAGE = "line-coverage", "artefact-access", "branch-coverage"
MEASURE = "--measure"   # the runner target flag that turns the measurements on
_NOTHING: Mapping = MappingProxyType({})


def _norm(path: str) -> str:
    return path.replace("\\", "/").strip("/").removeprefix("./")


# ------------------------------------------------------------------------------------------------ typed inputs

@dataclass(frozen=True)
class DeveloperTests:
    """Metamodel row 8: the tests the developer authored for the story — paths relative to the candidate root, files
    or directories. The only object a developer authors; it decides nothing about product correctness."""
    story_id: str
    paths: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.story_id or not isinstance(self.story_id, str):
            raise InvariantError("developer tests belong to a story")
        if not isinstance(self.paths, tuple) or not self.paths \
                or not all(isinstance(p, str) and p and not os.path.isabs(p) for p in self.paths):
            raise InvariantError("developer tests are named by relative paths under the candidate root")

    def owns(self, path: str) -> bool:
        p = _norm(path)
        return any(p == _norm(d) or p.startswith(_norm(d) + "/") for d in self.paths)


@dataclass(frozen=True)
class Dependencies:
    """Rule 4's two resolutions: top-level import names the execution profile declares as environment dependencies,
    and top-level names of the project's own source tree at the candidate."""
    environment: frozenset[str]
    project: frozenset[str]


@dataclass(frozen=True)
class Case:
    id: str
    path: str        # the test file, relative to the candidate root
    outcome: str     # one of CASE_OUTCOMES

    def __post_init__(self) -> None:
        if self.outcome not in CASE_OUTCOMES:
            raise InvariantError(f"a case outcome is one of {CASE_OUTCOMES}, not {self.outcome!r}")


@dataclass(frozen=True)
class CollectionError:
    """A test file the runner could not collect, with the cause **as the adapter typed it**: IMPORT names the
    top-level module that failed to import; SYNTAX is a syntax error in the file; OTHER is a cause the adapter could
    not determine — which the classifier reads as undeterminable, never as the developer's."""
    path: str
    kind: str
    module: str | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if self.kind not in (IMPORT, SYNTAX, OTHER):
            raise InvariantError(f"a collection cause is IMPORT, SYNTAX or OTHER, not {self.kind!r}")
        if (self.kind == IMPORT) != bool(self.module):
            raise InvariantError("an IMPORT cause names the module; no other cause does")


@dataclass(frozen=True)
class ResultSet:
    cases: tuple[Case, ...]
    collection_errors: tuple[CollectionError, ...]
    #: What the runner measured while each case ran, under the capability level it declares for each measurement
    #: (RFC §24: FULL, PARTIAL or UNAVAILABLE — never a silent degradation). WP-5.1 reads none of these; WP-5.2 does.
    capabilities: Mapping[str, Enforcement] = _NOTHING      # measurement name -> declared level
    lines: Mapping[str, Mapping[str, frozenset[int]]] = _NOTHING   # case id -> candidate path -> executed lines
    accessed: Mapping[str, frozenset[str]] = _NOTHING       # case id -> candidate paths the case opened
    arcs: Mapping[str, Mapping[str, frozenset[tuple[int, int]]]] = _NOTHING  # case id -> path -> (from, to) lines


@dataclass(frozen=True)
class RunnerReport:
    """What the runner did, harness-produced. `result_set` is None when no result set was reported."""
    launched: bool
    exit_code: int | None
    signalled: bool
    timed_out: bool
    result_set: ResultSet | None
    stderr: str = ""


# ------------------------------------------------------------------------------------------------ the typed result

@dataclass(frozen=True)
class TestExecution:
    """RFC §15.0, field for field. The shape itself refuses the SS-96 edge."""
    status: TestExecutionStatus
    outcome: TestOutcome | None          # None unless EXECUTED
    selection: TestSelection | None      # None unless EXECUTED
    owner_on_failure: Owner | None
    reason: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, TestExecutionStatus):
            raise InvariantError("a test execution has a typed status")
        if self.status is TestExecutionStatus.UNRUNNABLE:
            if self.outcome is not None or self.selection is not None:
                raise InvariantError("UNRUNNABLE: outcome and selection are defined only when EXECUTED (§15.0)")
            if self.owner_on_failure is not Owner.ENVIRONMENT:
                raise InvariantError("UNRUNNABLE is owner ENVIRONMENT and nothing else — never DEVELOPER (§15.0 rule 1, "
                                     "INV-ABSENCE-NEVER-A-DEVELOPER-FAILURE)")
            if not self.reason:
                raise InvariantError("UNRUNNABLE says why")
            return
        if not isinstance(self.outcome, TestOutcome) or not isinstance(self.selection, TestSelection):
            raise InvariantError("EXECUTED carries a typed outcome and a typed selection (§15.0)")
        expected = _owner_for(self.outcome, self.selection)
        if self.selection is TestSelection.STORY_TESTS_NOT_COLLECTABLE:
            if self.owner_on_failure not in (Owner.DEVELOPER, Owner.INTEGRATION):
                raise InvariantError("STORY_TESTS_NOT_COLLECTABLE is owned by DEVELOPER (project source) or INTEGRATION "
                                     "(undeterminable); the environment-dependency shape is UNRUNNABLE (§15.0 rule 4)")
        elif self.owner_on_failure is not expected:
            raise InvariantError(f"{self.outcome.value} + {self.selection.value} is owned by "
                                 f"{expected.value if expected else 'nobody'}, not {self.owner_on_failure} (§15.0)")


def _owner_for(outcome: TestOutcome, selection: TestSelection) -> Owner | None:
    if selection is TestSelection.NO_STORY_TESTS_MATCHED:
        return Owner.DEVELOPER  # rule 3: a developer-authored selector or definition defect
    if selection is TestSelection.STORY_TESTS_RAN:
        return Owner.DEVELOPER if outcome is TestOutcome.FAILED else None  # rule 2
    return None  # NOT_COLLECTABLE: by cause, decided by the classifier


def unrunnable(reason: str) -> TestExecution:
    return TestExecution(TestExecutionStatus.UNRUNNABLE, None, None, Owner.ENVIRONMENT, reason)


# ------------------------------------------------------------------------------------------------ classification

def classify(report: RunnerReport, tests: DeveloperTests, deps: Dependencies) -> TestExecution:
    """The only mapping from a runner's report to a `TestExecution` (§15.0 rules 1–5)."""
    if not report.launched:
        return unrunnable("the configured test runner could not be launched: " + (report.stderr.strip()[:200] or
                                                                                  "no process"))
    if report.timed_out:
        return unrunnable("the test runner did not finish within the harness deadline")
    if report.signalled:
        return unrunnable("the test runner ended by a signal before reporting a result set")
    if report.result_set is None:
        return unrunnable(f"the test runner reported no result set (exit {report.exit_code}): "
                          + (report.stderr.strip().splitlines()[-1][:200] if report.stderr.strip() else "no output"))
    rs = report.result_set
    mine = [c for c in rs.cases if tests.owns(c.path)]
    executed = [c for c in mine if c.outcome != "skipped"]
    failures = sum(c.outcome in ("failed", "error") for c in mine)
    outcome = TestOutcome.FAILED if failures else TestOutcome.PASSED  # the story's tests (rule 2), never others'
    # rule 4 before rule 2: a story file the runner could not collect is never hidden behind the story files that ran
    uncollectable = [e for e in rs.collection_errors if tests.owns(e.path)]
    if uncollectable:
        cause = uncollectable[0]
        owner, why = _cause_owner(cause, deps)
        if owner is Owner.ENVIRONMENT:
            return unrunnable(f"{cause.path} could not be collected: {why}")
        return TestExecution(TestExecutionStatus.EXECUTED, outcome, TestSelection.STORY_TESTS_NOT_COLLECTABLE, owner,
                             f"{cause.path} could not be collected: {why}")
    if executed:
        return TestExecution(TestExecutionStatus.EXECUTED, outcome, TestSelection.STORY_TESTS_RAN,
                             _owner_for(outcome, TestSelection.STORY_TESTS_RAN),
                             f"{len(executed)} story-owned test(s) ran; {failures} failed")
    return TestExecution(TestExecutionStatus.EXECUTED, outcome, TestSelection.NO_STORY_TESTS_MATCHED, Owner.DEVELOPER,
                         f"none of the story's declared tests {list(tests.paths)} ran ({len(rs.cases)} test(s) in the "
                         "result set)")


def _cause_owner(cause: CollectionError, deps: Dependencies) -> tuple[Owner, str]:
    """Rule 4, on the typed cause. Ambiguity (a name in both resolutions, or in neither, or a cause the adapter could
    not type) fails closed to INTEGRATION — the developer is charged only for what is provably the project's own."""
    if cause.kind == SYNTAX:
        return Owner.DEVELOPER, "a syntax error in the developer's own test file"
    if cause.kind == IMPORT:  # an IMPORT cause always names its module (CollectionError refuses the other shape)
        top = cause.module.split(".")[0]
        in_env, in_project = top in deps.environment, top in deps.project
        if in_env and not in_project:
            return Owner.ENVIRONMENT, f"import of {cause.module!r} failed: a declared environment dependency"
        if in_project and not in_env:
            return Owner.DEVELOPER, f"import of {cause.module!r} failed: the project's own source tree"
        return Owner.INTEGRATION, (f"import of {cause.module!r} failed: {'both' if in_env else 'neither'} a declared "
                                   "environment dependency and the project's own tree — cause undeterminable")
    return Owner.INTEGRATION, "the cause of the collection failure could not be determined"


# ------------------------------------------------------------------------------------------------ runners / adapters

@dataclass(frozen=True)
class Runner:
    """A configured test runner: how it is invoked (the interpreter is prepended) and how its result set is read."""
    name: str
    argv: tuple[str, ...]          # after the interpreter; `{out}` is the result-set path, targets follow
    adapter: Callable[[pathlib.Path], ResultSet]


_UNITTEST_RUNNER = r'''
import importlib, json, os, sys, threading, traceback, unittest
out, targets = sys.argv[1], sys.argv[2:]
measure = "--measure" in targets
targets = [t for t in targets if t != "--measure"]
cases, errors = [], []
loader = unittest.TestLoader()
suite = unittest.TestSuite()
ROOT = os.getcwd() + os.sep
current = [None]                 # the case running now: what the tracer and the audit hook attribute to
lines, accessed, arcs = {}, {}, {}
partial = [False]                # set when a case replaced the tracer: the measurement is PARTIAL, never silently FULL

def inside(filename):
    return filename.startswith(ROOT) and "__pycache__" not in filename

def local(frame, event, arg):
    if event == "line" and current[0] is not None:
        rel_path = frame.f_code.co_filename[len(ROOT):].replace(os.sep, "/")
        lines.setdefault(current[0], {}).setdefault(rel_path, set()).add(frame.f_lineno)
        last = _last.get(id(frame))
        if last is not None and last != frame.f_lineno:
            arcs.setdefault(current[0], {}).setdefault(rel_path, set()).add((last, frame.f_lineno))
        _last[id(frame)] = frame.f_lineno
    elif event == "return":
        _last.pop(id(frame), None)
    return local

_last = {}

def tracer(frame, event, arg):
    return local if event == "call" and inside(frame.f_code.co_filename) else None

def audit(event, args):
    if event == "open" and current[0] is not None and args and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.path.abspath(os.fsdecode(args[0]))
        if inside(path):
            accessed.setdefault(current[0], set()).add(path[len(ROOT):].replace(os.sep, "/"))

if measure:
    sys.addaudithook(audit)
    threading.settrace(tracer)
    sys.settrace(tracer)

def rel(path):
    try:
        return os.path.relpath(path, os.getcwd()).replace(os.sep, "/")
    except ValueError:
        return path.replace(os.sep, "/")

def cause(exc):
    if isinstance(exc, ModuleNotFoundError) and exc.name:
        return {"kind": "IMPORT", "module": exc.name}
    if isinstance(exc, ImportError) and getattr(exc, "name", None):
        return {"kind": "IMPORT", "module": exc.name}
    if isinstance(exc, SyntaxError):
        return {"kind": "SYNTAX", "module": None}
    return {"kind": "OTHER", "module": None}

def files(target):  # a directory target is every test*.py under it, in a fixed order; a file target is itself
    if not os.path.isdir(target):
        yield target
        return
    for base, dirs, names in os.walk(target):
        dirs.sort()
        yield from (os.path.join(base, n) for n in sorted(names) if n.startswith("test") and n.endswith(".py"))

for t in targets:
    target, _, sel = t.partition("::")
    for path in files(target):
        mod = os.path.splitext(rel(path))[0].replace("/", ".")
        try:
            module = importlib.import_module(mod)
        except BaseException as exc:  # a collection failure is reported with its own typed cause; it is not a test error
            errors.append({"path": rel(path), **cause(exc), "detail": "".join(traceback.format_exception_only(exc)).strip()[:500]})
            continue
        suite.addTests(loader.loadTestsFromName(sel, module) if sel else loader.loadTestsFromModule(module))

class Result(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.seen = {}
    def _path(self, test):
        m = sys.modules.get(type(test).__module__)
        f = getattr(m, "__file__", None)
        return rel(f) if f else type(test).__module__.replace(".", "/") + ".py"
    def _mark(self, test, outcome):
        self.seen[test.id()] = {"id": test.id(), "path": self._path(test), "outcome": outcome}
    def startTest(self, test):
        super().startTest(test)
        self._mark(test, "passed")
        current[0] = test.id()
    def stopTest(self, test):
        super().stopTest(test)
        if measure and sys.gettrace() is not tracer:
            partial[0] = True  # the case replaced the tracer: what ran meanwhile was not observed
            sys.settrace(tracer)
        current[0] = None
    def addError(self, test, err):
        super().addError(test, err)
        self._mark(test, "error")
    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._mark(test, "failed")
    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._mark(test, "skipped")
    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._mark(test, "passed")
    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._mark(test, "failed")

result = Result()
suite.run(result)
if measure:
    sys.settrace(None)
    threading.settrace(None)
cases = list(result.seen.values())
level = ("PARTIAL" if partial[0] else "FULL") if measure else "UNAVAILABLE"
capabilities = {"line-coverage": level, "artefact-access": level, "branch-coverage": level}
with open(out, "w", encoding="utf-8") as f:
    json.dump({"cases": cases, "collection_errors": errors, "capabilities": capabilities,
               "lines": {c: {p: sorted(v) for p, v in m.items()} for c, m in lines.items()},
               "accessed": {c: sorted(v) for c, v in accessed.items()},
               "arcs": {c: {p: sorted(v) for p, v in m.items()} for c, m in arcs.items()}}, f)
sys.exit(0 if result.wasSuccessful() else 1)
'''


def _read_unittest(path: pathlib.Path) -> ResultSet:
    d = json.loads(path.read_text(encoding="utf-8"))
    return ResultSet(tuple(Case(c["id"], c["path"], c["outcome"]) for c in d["cases"]),
                     tuple(CollectionError(e["path"], e["kind"], e.get("module"), e.get("detail", ""))
                           for e in d["collection_errors"]),
                     MappingProxyType({k: Enforcement(v) for k, v in d.get("capabilities", {}).items()}),
                     MappingProxyType({c: MappingProxyType({p: frozenset(v) for p, v in m.items()})
                                       for c, m in d.get("lines", {}).items()}),
                     MappingProxyType({c: frozenset(v) for c, v in d.get("accessed", {}).items()}),
                     MappingProxyType({c: MappingProxyType({p: frozenset(map(tuple, v)) for p, v in m.items()})
                                       for c, m in d.get("arcs", {}).items()}))


_IMPORT_ERROR = re.compile(r"(?:ModuleNotFoundError|ImportError): (?:No module named|cannot import name .+? from) '([^']+)'")


def _read_junit(path: pathlib.Path) -> ResultSet:
    """pytest's junit result set (junit_family=xunit1, which the runner's argv fixes: every testcase carries `file`).
    A `collection failure` error is typed by its traceback text: a missing module is IMPORT with the module the
    runner named; a syntax error is SYNTAX; anything else is OTHER."""
    root = ElementTree.parse(path).getroot()
    cases, errors = [], []
    for tc in root.iter("testcase"):
        file = tc.get("file", "").replace(os.sep, "/")
        name = tc.get("name", "")
        error = tc.find("error")
        if error is not None and "collection failure" in error.get("message", ""):
            body = ElementTree.tostring(error, encoding="unicode", method="text")
            m = _IMPORT_ERROR.search(body)
            if m:
                errors.append(CollectionError(file, IMPORT, m.group(1), body[-500:]))
            elif "SyntaxError" in body or "IndentationError" in body:
                errors.append(CollectionError(file, SYNTAX, None, body[-500:]))
            else:
                errors.append(CollectionError(file, OTHER, None, body[-500:]))
            continue
        outcome = ("error" if error is not None else "failed" if tc.find("failure") is not None
                   else "skipped" if tc.find("skipped") is not None else "passed")
        cases.append(Case(f"{file}::{tc.get('classname', '')}::{name}", file, outcome))
    return ResultSet(tuple(cases), tuple(errors))


UNITTEST = Runner("unittest", ("-E", "-s", "-c", _UNITTEST_RUNNER, "{out}"), _read_unittest)
PYTEST = Runner("pytest", ("-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "junit_family=xunit1",
                           "--junitxml", "{out}"), _read_junit)


def _scrubbed_env(extra: Mapping[str, str] | None = None) -> dict:
    keep = ("PATH", "SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "LANG")
    return {**{k: os.environ[k] for k in keep if k in os.environ}, "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8", **(extra or {})}


def execute(runner: Runner, candidate: str | os.PathLike, tests: DeveloperTests, deps: Dependencies, *,
            interpreter: str = sys.executable, targets: Sequence[str] | None = None, timeout_s: float = _TIMEOUT_S,
            env: Mapping[str, str] | None = None, on_range: Callable[[ProcessRange], None] | None = None,
            ) -> tuple[RunnerReport, TestExecution]:
    """Run `runner` at the candidate over `targets` (the story's tests by default) inside an owned process range, read
    what it reported, and classify. The candidate is the only tree this function knows; there is no parent here."""
    root = pathlib.Path(candidate)
    with tempfile.TemporaryDirectory(prefix="aisef2-tests-") as work:
        out = os.path.join(work, "result-set.json" if runner.name == "unittest" else "result-set.xml")
        argv = [interpreter, *(a.replace("{out}", out) for a in runner.argv), *(targets or tests.paths)]
        run = ProcessRange(f"tests {tests.story_id}", argv, cwd=str(root), env=_scrubbed_env(env),
                           output=subprocess.PIPE, grace_s=_GRACE_S, wait_s=_WAIT_S)
        try:
            run.start()
        except (RangeError, OSError) as e:
            report = RunnerReport(False, None, False, False, None, f"{type(e).__name__}: {e}")
            return report, classify(report, tests, deps)
        if on_range is not None:
            on_range(run)
        chunks: list[str] = []
        pump = threading.Thread(target=_pump, args=(run, chunks), daemon=True)
        pump.start()
        try:
            code = run.wait(timeout_s)
            timed_out = code is None
        finally:
            run.release()  # on the controller's own deadline this is the ladder, in the ledger; else a no-op wait
        pump.join(2.0)
        code = run.returncode
        signalled = code is not None and code < 0
        result_set = None
        if os.path.exists(out) and not timed_out and not signalled:
            try:
                result_set = runner.adapter(pathlib.Path(out))
            except (ValueError, KeyError, ElementTree.ParseError, OSError):
                result_set = None  # an unreadable result set is no result set
        report = RunnerReport(True, code, signalled, timed_out, result_set, "".join(chunks[-20:]))
        return report, classify(report, tests, deps)


def _pump(run: ProcessRange, chunks: list) -> None:
    """The runner's output, read to EOF so a chatty runner never blocks on a full pipe; the last lines are kept."""
    try:
        for line in run.output:
            chunks.append(line)
            del chunks[:-200]
    except (OSError, ValueError):
        pass


def project_top_level(candidate: str | os.PathLike) -> frozenset[str]:
    """Top-level import names of the project's own source tree at the candidate: packages (a directory with an
    __init__.py) and modules at the root and under a `src/` directory."""
    root = pathlib.Path(candidate)
    names = set()
    for base in (root, root / "src"):
        if not base.is_dir():
            continue
        for p in base.iterdir():
            if (p / "__init__.py").is_file():
                names.add(p.name)
            elif p.suffix == ".py":
                names.add(p.stem)
    return frozenset(names)


def to_json(execution: TestExecution) -> dict:
    return {k: (v.value if hasattr(v, "value") else v) for k, v in dataclasses.asdict(execution).items()}
