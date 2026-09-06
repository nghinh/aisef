"""Đọc output của test runner: test **nào** đã chạy, xanh hay đỏ, coverage.

Cổng story hiện chỉ biết "lần test cuối xanh". G5 cần biết *tiêu chí nào*
có test — nghĩa là cần tên test; G10b cần số coverage. Cả hai nằm trong
stdout của lần `test`, và không ai đọc nó ngoài `tail(20)` cho người xem.

Năm định dạng có thật trong các dự án thử: `node --test` reporter `spec`
(mặc định, `par`), `node --test --test-reporter=tap`, `vitest` (`e9`),
`pytest -v`, và `python -m unittest -v` (bộ test của chính kho — bench
ADR-005 V8 chấm task lỗi kho theo tên test). Không nhận ra → `format=""`, `test_ids=[]`, và cổng ghi
"không đọc được tên test" (UNCONFIGURED) — **không** đoán, không tính là
đạt. Fixture là output thật, ở `tests/fixtures/testlog/`.

Định dạng thứ sáu là **CTRF** (ctrf.io — JSON chung cho pytest-json-ctrf,
vitest-ctrf-json-reporter, jest/playwright…; ADR-005 V9): một khối JSON
`{"results": {"tests": [{name, status, suite?, filePath?}]}}` ở bất kỳ đâu
trong output (`pytest --ctrf /dev/stdout`, hay `cat` tệp reporter ghi ra).
Regex năm định dạng trên giữ làm dự phòng; e9/`par` hôm nay 220/377 lần
`tool_run test` không đọc được tên (`test_format=""`) — `doctor` gợi reporter.
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
# vitest --reporter=verbose: "✓ file > suite > tên 12ms"; default chỉ in file
_VITEST = re.compile(r"^\s*([✓×↓])\s(.+?)(?:\s\d+ms)?$")
_VITEST_FILE = re.compile(r"^\s*[✓×↓]\s\S+\s\(\d+ tests?")
# pytest -v ; pytest -q chỉ có FAILED ở phần summary
_PYTEST = re.compile(r"^(\S+::\S+)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b")
_PYTEST_Q_FAIL = re.compile(r"^(?:FAILED|ERROR) (\S+::\S+)")
# python -m unittest -v: "test_x (mod.C.test_x) ... ok"; test có docstring thì
# "... ok" nằm cuối dòng docstring kế tiếp, không cùng dòng với tên
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
    ctrf = _ctrf_object(text or "")
    if ctrf is not None:
        _ctrf(ctrf, log)
    elif any("TAP version" in l for l in lines[:5]):
        _node_tap(lines, log)
    elif any(l.strip().startswith("ℹ tests") for l in lines) or any(_SPEC.match(l) for l in lines):
        _node_spec(lines, log)
    elif any(l.startswith(" RUN  v") or l.strip().startswith("Test Files") for l in lines):
        _vitest(lines, log)
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
    """Khối JSON CTRF trong output — cả tệp trần (`cat report.json`) lẫn chen
    giữa text của runner (`pytest --ctrf /dev/stdout`). Chỉ nhận vật thể có
    `results.tests` là danh sách; JSON khác (mảng, object lạ) bỏ qua."""
    if '"results"' not in text:
        return None
    dec = json.JSONDecoder()
    # ponytail: thử từng `{"` — output có nhiều object JSON lạ thì O(n²);
    # log test thật ≤ vài trăm KB nên chưa cần cắt.
    for m in re.finditer(r'\{\s*"', text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance((obj.get("results") or {}).get("tests"), list):
            return obj
    return None


def _ctrf(data: dict, log: TestLog) -> None:
    """CTRF: `name` + `status` (passed · failed · skipped · pending · other).
    Id ghép `<filePath> > <suite> > <name>` khi reporter tách phần ấy ra
    (vitest) và tên chưa chứa nó; pytest đã in `a.py::test_x` thì giữ nguyên
    — cùng hình dạng với reporter văn bản, nên `_la()` ở cổng vẫn đọc được."""
    log.format = "ctrf"
    for t in data["results"]["tests"]:
        if not isinstance(t, dict):
            continue
        name = str(t.get("name") or "")
        for phan in (t.get("suite"), t.get("filePath") or t.get("file_path")):
            if phan and str(phan) not in name:
                name = f"{phan} > {name}"
        # pending/other không phải xanh: tính là bỏ qua để baseline R9 không
        # coi nó là test xanh có sẵn.
        _add(log, name, {"passed": "pass", "failed": "fail"}.get(str(t.get("status")), "skip"))


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


def _unittest(lines: list[str], log: TestLog) -> None:
    """`python -m unittest -v`. Mã test = id đầy đủ trong ngoặc (Python ≥ 3.11
    in `mod.Class.test`; bản cũ chỉ in `mod.Class` — khi ấy nối thêm tên)."""
    log.format = "unittest"
    marks = {"ok": "pass", "FAIL": "fail", "ERROR": "fail", "expected failure": "skip",
             "unexpected success": "pass"}
    pending = ""
    for line in lines:
        if line.startswith("=====") or _UNITTEST_RAN.match(line):
            break   # phần sau là traceback + tổng kết, lặp lại tên ca đỏ
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
        log.note = "pytest chưa `-v`: chỉ đọc được tên test đỏ, không biết test nào xanh"
