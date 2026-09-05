"""Đọc output của test runner: test **nào** đã chạy, xanh hay đỏ, coverage.

Cổng story hiện chỉ biết "lần test cuối xanh". G5 cần biết *tiêu chí nào*
có test — nghĩa là cần tên test; G10b cần số coverage. Cả hai nằm trong
stdout của lần `test`, và không ai đọc nó ngoài `tail(20)` cho người xem.

Bốn định dạng có thật trong các dự án thử: `node --test` reporter `spec`
(mặc định, `par`), `node --test --test-reporter=tap`, `vitest` (`e9`),
`pytest -v`. Không nhận ra → `format=""`, `test_ids=[]`, và cổng ghi
"không đọc được tên test" (UNCONFIGURED) — **không** đoán, không tính là
đạt. Fixture là output thật, ở `tests/fixtures/testlog/`.
"""

from __future__ import annotations

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
# vitest --reporter=verbose: "✓ file > suite > tên 12ms"; default chỉ in file
_VITEST = re.compile(r"^\s*([✓×↓])\s(.+?)(?:\s\d+ms)?$")
_VITEST_FILE = re.compile(r"^\s*[✓×↓]\s\S+\s\(\d+ tests?")
# pytest -v ; pytest -q chỉ có FAILED ở phần summary
_PYTEST = re.compile(r"^(\S+::\S+)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b")
_PYTEST_Q_FAIL = re.compile(r"^(?:FAILED|ERROR) (\S+::\S+)")
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
    note: str = ""      # vì sao không có tên test — để cổng nói đúng chỗ sửa

    @property
    def test_ids(self) -> list[str]:
        return self.passed + self.failed + self.skipped

    def to_evidence(self) -> dict:
        out = {
            "test_format": self.format,
            "test_ids": self.test_ids[:MAX_IDS],
            "failed_ids": self.failed[:MAX_IDS],
            # Cổng R9 cần biết test nào **xanh** ở baseline: bỏ qua không
            # phải xanh, và không có danh sách này thì nó bị tính là xanh.
            "skipped_ids": self.skipped[:MAX_IDS],
            "coverage": self.coverage,
        }
        if self.note:
            out["test_note"] = self.note
        return out


def parse(text: str) -> TestLog:
    lines = _ANSI.sub("", text or "").splitlines()
    log = TestLog()
    for line in lines:
        for rx in _COV:
            m = rx.match(line)
            if m:
                log.coverage = float(m.group(1))
                break
    if any("TAP version" in l for l in lines[:5]):
        _node_tap(lines, log)
    elif any(l.strip().startswith("ℹ tests") for l in lines) or any(_SPEC.match(l) for l in lines):
        _node_spec(lines, log)
    elif any(l.startswith(" RUN  v") or l.strip().startswith("Test Files") for l in lines):
        _vitest(lines, log)
    elif any("test session starts" in l or _PYTEST.match(l) or "short test summary" in l for l in lines):
        _pytest(lines, log)
    return log


def _add(log: TestLog, name: str, mark: str) -> None:
    name = name.strip()
    if not name:
        return
    {"pass": log.passed, "fail": log.failed, "skip": log.skipped}[mark].append(name)


def _node_spec(lines: list[str], log: TestLog) -> None:
    log.format = "node-spec"
    suites: list[tuple[int, str]] = []
    for line in lines:
        s = line.strip()
        if s.startswith("ℹ tests") or s.startswith("✖ failing tests"):
            break   # phần sau là tổng kết + lặp lại các ca đỏ
        m = _SPEC_SUITE.match(line)
        if m:
            suites.append((len(m.group(1)), m.group(2).strip()))
            continue
        m = _SPEC.match(line)
        if not m:
            continue
        indent, sym, name = len(m.group(1)), m.group(2), m.group(3)
        if (indent, name.strip()) in suites:
            suites.remove((indent, name.strip()))   # dòng đóng suite, không phải test
            continue
        _add(log, name, {"✔": "pass", "✖": "fail", "﹣": "skip"}[sym])


def _node_tap(lines: list[str], log: TestLog) -> None:
    log.format = "node-tap"
    pending: tuple[str, str] | None = None   # (tên, kết cục) chờ biết type
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
        log.note = "vitest reporter mặc định không in tên test — thêm `--reporter=verbose`"


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
        log.note = "pytest chưa `-v`: chỉ đọc được tên test đỏ, không biết test nào xanh"
