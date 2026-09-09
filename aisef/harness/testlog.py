"""Parse test runner output: **which** tests ran, pass or fail, coverage.

The story gate currently only knows "last test run passed". G5 needs to know
*which criteria have tests* — meaning test names; G10b needs coverage numbers.
Both live in the `test` run's stdout, and no one reads it beyond `tail(20)`
for the viewer.

Five formats seen in real trial projects: `node --test` reporter `spec`
(default, `par`), `node --test --test-reporter=tap`, `vitest` (`e9`),
`pytest -v`, and `python -m unittest -v` (this repo's own test suite — bench
ADR-005 V8 scores repo-bug tasks by test name). Unrecognized -> `format=""`,
`test_ids=[]`, and the gate records "could not read test names" (UNCONFIGURED)
— does **not** guess, does not count as passing. Fixtures are real output, in
`tests/fixtures/testlog/`.

The sixth format is **CTRF** (ctrf.io — common JSON for pytest-json-ctrf,
vitest-ctrf-json-reporter, jest/playwright...; ADR-005 V9): a JSON block
`{"results": {"tests": [{name, status, suite?, filePath?}]}}` anywhere in
output (`pytest --ctrf /dev/stdout`, or `cat` of the reporter's file).
The five regex formats above are kept as fallback; e9/`par` today 220/377
`tool_run test` calls could not read names (`test_format=""`) — `doctor`
suggests a reporter.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

MAX_IDS = 500

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

# node --test, reporter spec
_SPEC = re.compile(r"^(\s*)([✔✖﹣])\s(.*?)\s\(([\d.]+)ms\)(?:\s*#\s*(.*))?$")
_SPEC_SUITE = re.compile(r"^(\s*)▶\s(.*)$")
# node --test, reporter tap
_TAP = re.compile(r"^(\s*)(not )?ok \d+ - (.*?)(?:\s+# (SKIP|TODO)\b.*)?$")
_TAP_TYPE = re.compile(r"^\s*type: '(\w+)'")
# vitest --reporter=verbose: "✓ file > suite > name 12ms"; default only prints file
_VITEST = re.compile(r"^\s*([✓×↓])\s(.+?)(?:\s\d+ms)?$")
_VITEST_FILE = re.compile(r"^\s*[✓×↓]\s\S+\s\(\d+ tests?")
# pytest -v ; pytest -q only has FAILED in the summary section
_PYTEST = re.compile(r"^(\S+::\S+)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b")
_PYTEST_Q_FAIL = re.compile(r"^(?:FAILED|ERROR) (\S+::\S+)")
# python -m unittest -v: "test_x (mod.C.test_x) ... ok"; tests with docstrings
# have "... ok" at the end of the next docstring line, not on the name line
_UNITTEST = re.compile(r"^(\S+) \((\S+)\)(?: \.\.\. (.+))?$")
_UNITTEST_END = re.compile(r"\.\.\. (ok|FAIL|ERROR|skipped\b.*|expected failure|unexpected success)$")
_UNITTEST_RAN = re.compile(r"^Ran \d+ tests? in ")
# coverage: pytest-cov / c8 / istanbul
_COV = (re.compile(r"^TOTAL\s+\d+\s+\d+(?:\s+\d+\s+\d+)?\s+([\d.]+)%"),
        re.compile(r"^All files\s*\|\s*([\d.]+)"))


@dataclass
class TestLog:
    format: str = ""
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    coverage: float | None = None
    note: str = ""      # why test names are absent — so the gate points to the fix

    @property
    def test_ids(self) -> list[str]:
        return self.passed + self.failed + self.skipped

    def to_evidence(self) -> dict:
        out = {
            "test_format": self.format,
            "test_ids": self.test_ids[:MAX_IDS],
            "failed_ids": self.failed[:MAX_IDS],
            # Gate R9 needs to know which tests **passed** at baseline: skipped
            # is not passing, and without this list they would count as passed.
            "skipped_ids": self.skipped[:MAX_IDS],
            "coverage": self.coverage,
        }
        if self.note:
            out["test_note"] = self.note
        return out


#: Playwright's `list` reporter: `  ✓   3 file.spec.js:26:1 › name (217ms)`.
#: The status glyph, the ordinal, `path:line:col`, ` › `, then the title.
#: A skipped test is `-`, a failure `✘`; an ANSI-stripped line keeps them.
_PW = re.compile(r"^\s*([✓✘×✕⊘-])\s+\d+\s+\S+?:\d+:\d+\s+›\s+(.+?)(?:\s+\(\d+(?:\.\d+)?m?s\))?\s*$")


def parse(text: str) -> TestLog:
    lines = _ANSI.sub("", text or "").splitlines()
    log = TestLog()
    for line in lines:
        for rx in _COV:
            m = rx.match(line)
            if m:
                log.coverage = float(m.group(1))
                break
    ctrf = _ctrf_object(text or "")
    if ctrf is not None:
        _ctrf(ctrf, log)
    elif any("TAP version" in l for l in lines[:5]):
        _node_tap(lines, log)
    elif any(l.strip().startswith("ℹ tests") for l in lines) or any(_SPEC.match(l) for l in lines):
        _node_spec(lines, log)
    elif any(l.startswith(" RUN  v") or l.strip().startswith("Test Files") for l in lines):
        _vitest(lines, log)
    elif any(_PW.match(l) for l in lines):
        _playwright(lines, log)
    elif any(_UNITTEST_RAN.match(l) for l in lines):
        _unittest(lines, log)
    elif any("test session starts" in l or _PYTEST.match(l) or "short test summary" in l for l in lines):
        _pytest(lines, log)
    return log


def _add(log: TestLog, name: str, mark: str) -> None:
    name = name.strip()
    if not name:
        return
    {"pass": log.passed, "fail": log.failed, "skip": log.skipped}[mark].append(name)


def _ctrf_object(text: str) -> dict | None:
    """Extract a CTRF JSON block from output — both bare file (`cat report.json`)
    and inline within runner text (`pytest --ctrf /dev/stdout`). Only accepts
    objects with `results.tests` as a list; other JSON (arrays, unrelated
    objects) is ignored."""
    if '"results"' not in text:
        return None
    dec = json.JSONDecoder()
    # ponytail: try each `{"` — output with many unrelated JSON objects is O(n²);
    # real test logs are <= a few hundred KB so no need to optimize yet.
    for m in re.finditer(r'\{\s*"', text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance((obj.get("results") or {}).get("tests"), list):
            return obj
    return None


def _ctrf(data: dict, log: TestLog) -> None:
    """CTRF: `name` + `status` (passed / failed / skipped / pending / other).
    Composes id as `<filePath> > <suite> > <name>` when the reporter separates
    those (vitest) and the name does not already contain them; pytest already
    prints `a.py::test_x` so it is kept as-is — same shape as the text
    reporter, so `_la()` in the gate can still parse it."""
    log.format = "ctrf"
    for t in data["results"]["tests"]:
        if not isinstance(t, dict):
            continue
        name = str(t.get("name") or "")
        for phan in (t.get("suite"), t.get("filePath") or t.get("file_path")):
            if phan and str(phan) not in name:
                name = f"{phan} > {name}"
        # pending/other is not passing: count as skipped so baseline R9 does
        # not treat it as a pre-existing passing test.
        _add(log, name, {"passed": "pass", "failed": "fail"}.get(str(t.get("status")), "skip"))


def _node_spec(lines: list[str], log: TestLog) -> None:
    log.format = "node-spec"
    suites: list[tuple[int, str]] = []
    for line in lines:
        s = line.strip()
        if s.startswith("ℹ tests") or s.startswith("✖ failing tests"):
            break   # after this is summary + repeated failed cases
        m = _SPEC_SUITE.match(line)
        if m:
            suites.append((len(m.group(1)), m.group(2).strip()))
            continue
        m = _SPEC.match(line)
        if not m:
            continue
        indent, sym, name = len(m.group(1)), m.group(2), m.group(3)
        if (indent, name.strip()) in suites:
            suites.remove((indent, name.strip()))   # closing suite line, not a test
            continue
        _add(log, name, {"✔": "pass", "✖": "fail", "﹣": "skip"}[sym])


def _playwright(lines: list[str], log: TestLog) -> None:
    """Playwright `--reporter=list`.

    Playwright is the runner this framework itself drives for mockup and e2e
    checks, and its default reporter prints every test name — but the parser
    did not know the shape, so `criteria have tests`, `coverage`,
    `no baseline regression` and `tests verify story` all scored
    *unconfigured* on every Playwright project. Measured on `todo`
    2026-09-09: 20 named tests in the output, 0 read.

    Interleaved server logs are common (`[WebServer] ... "GET / HTTP/1.1"`)
    and simply do not match.
    """
    log.format = "playwright-list"
    mark = {"✓": "pass", "✘": "fail", "×": "fail", "✕": "fail", "⊘": "skip", "-": "skip"}
    for line in lines:
        m = _PW.match(line)
        if m:
            _add(log, m.group(2), mark[m.group(1)])


def _node_tap(lines: list[str], log: TestLog) -> None:
    log.format = "node-tap"
    pending: tuple[str, str] | None = None   # (name, outcome) awaiting type
    kind = ""

    def flush() -> None:
        if pending and kind != "suite":
            _add(log, *pending)

    for line in lines:
        m = _TAP.match(line)
        if m:
            flush()
            mark = "skip" if m.group(4) else ("fail" if m.group(2) else "pass")
            pending, kind = (m.group(3), mark), ""
            continue
        t = _TAP_TYPE.match(line)
        if t:
            kind = t.group(1)
    flush()


def _vitest(lines: list[str], log: TestLog) -> None:
    log.format = "vitest"
    for line in lines:
        if _VITEST_FILE.match(line):
            continue
        m = _VITEST.match(line)
        if m and " > " in m.group(2):
            _add(log, m.group(2), {"✓": "pass", "×": "fail", "↓": "skip"}[m.group(1)])
    if not log.test_ids:
        log.note = "vitest default reporter does not print test names — add `--reporter=verbose`"


def _unittest(lines: list[str], log: TestLog) -> None:
    """`python -m unittest -v`. Test id = fully qualified id in parentheses
    (Python >= 3.11 prints `mod.Class.test`; older versions only print
    `mod.Class` — in that case the name is appended)."""
    log.format = "unittest"
    marks = {"ok": "pass", "FAIL": "fail", "ERROR": "fail", "expected failure": "skip",
             "unexpected success": "pass"}
    pending = ""
    for line in lines:
        if line.startswith("=====") or _UNITTEST_RAN.match(line):
            break   # after this is traceback + summary, repeating failed case names
        m = _UNITTEST.match(line)
        if m:
            name, full = m.group(1), m.group(2)
            pending = full if full.endswith("." + name) else f"{full}.{name}"
            if not m.group(3):
                continue
            end = m.group(3)
        else:
            e = _UNITTEST_END.search(line)
            if not e or not pending:
                continue
            end = e.group(1)
        _add(log, pending, "skip" if end.startswith("skipped") else marks[end])
        pending = ""


def _pytest(lines: list[str], log: TestLog) -> None:
    log.format = "pytest"
    for line in lines:
        m = _PYTEST.match(line)
        if m:
            mark = {"PASSED": "pass", "XPASS": "pass", "FAILED": "fail", "ERROR": "fail",
                    "SKIPPED": "skip", "XFAIL": "skip"}[m.group(2)]
            _add(log, m.group(1), mark)
    if not log.test_ids:
        for line in lines:
            m = _PYTEST_Q_FAIL.match(line)
            if m:
                _add(log, m.group(1), "fail")
        log.note = "pytest without `-v`: can only read failing test names, cannot tell which passed"
