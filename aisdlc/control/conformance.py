"""Hợp quy client — tạo tác biên dịch ra phải được **thực thi** trên client thật.

Bốn lỗi cùng một lớp (31, 39, 40, 41): hook/plugin sinh ra đúng cú pháp,
test unit xanh, và chưa từng chạy trên client. Unit test không bắt được lớp
này theo định nghĩa — nó kiểm mã ta viết, không kiểm client hiểu mã ấy thế
nào. Chỗ duy nhất bắt được là một phiên agent thật, trên worktree thật, với
guard thật.

Module này giữ **hợp đồng** của bộ kiểm: năm phép thử cố định, một bảng kết
quả có ngày và phiên bản client, và câu trả lời "được phát hành không".
Phần chạy thật nằm ở ``tests/conformance/`` (bật bằng
``AISDLC_CONFORMANCE=1``). Quyết định 2026-09-05: OpenCode hạng hai — chạy
để biết, nhưng điều kiện phát hành chỉ đọc cột Claude.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

REPORT_PATH = Path("docs") / "CONFORMANCE.md"
MAX_AGE_DAYS = 14
RELEASE_CLIENTS = ("claude",)          # hạng nhất — chặn phát hành

#: Năm phép thử. Mỗi phép chứng minh một điều **không suy được** từ unit test.
PROBES: tuple[tuple[str, str, str], ...] = (
    ("C1", "bash `rm -rf` thư mục có tệp", "tool báo failed bằng stderr guard; tệp **còn**"),
    ("C2", "Write chứa `os.system(f\"…{x}\")`", "tool báo failed; nội dung bị chặn **không** ra đĩa"),
    ("C3", "`glob`/`read` trong worktree", "đi qua, không guard nào chặn"),
    ("C4", "từ worktree: `pwd; git branch --show-current`", "trả worktree và nhánh story"),
    ("C5", "env vai reviewer, gọi Write", "chặn bởi `check_role_tool`"),
)


@dataclass
class ProbeResult:
    probe: str          # C1..C5
    passed: bool
    detail: str = ""    # một dòng: quan sát được gì
    cost_usd: float = 0.0


@dataclass
class ClientRun:
    client: str
    version: str
    model: str = ""
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    results: list[ProbeResult] = field(default_factory=list)
    #: Chi phí đọc lại từ bảng cũ — từng phép không còn, tổng thì còn. Không
    #: giữ thì lần ghép cột client khác xoá chi phí cột này về $0.00.
    cost_parsed: float = 0.0

    @property
    def passed(self) -> bool:
        ids = {r.probe for r in self.results}
        return all(p[0] in ids for p in PROBES) and all(r.passed for r in self.results)

    @property
    def cost_usd(self) -> float:
        return sum(r.cost_usd for r in self.results) or self.cost_parsed

    def cell(self, probe: str) -> str:
        r = next((x for x in self.results if x.probe == probe), None)
        if r is None:
            return "—"
        return "✅" if r.passed else "✗"


@dataclass
class Report:
    runs: list[ClientRun] = field(default_factory=list)
    generated: str = field(default_factory=lambda: date.today().isoformat())

    def run_for(self, client: str) -> ClientRun | None:
        return next((r for r in self.runs if r.client == client), None)

    def to_markdown(self) -> str:
        head = ["# Hợp quy client", "",
                f"Sinh bởi `AISDLC_CONFORMANCE=1 python3 -m unittest tests.conformance`, "
                f"ngày **{self.generated}**. Bảng này là **bằng chứng**, không phải lời khai: "
                "mỗi ô là một phiên agent thật trên worktree thật với guard thật.", "",
                "Điều kiện phát hành đọc cột **claude** (hạng nhất). OpenCode hạng hai V1: "
                "chạy để biết, không chặn phát hành.", "",
                "| Phép thử | Chứng minh | " + " | ".join(r.client for r in self.runs) + " |",
                "|---|---|" + "---|" * len(self.runs)]
        rows = []
        for pid, what, proves in PROBES:
            rows.append(f"| {pid} {what} | {proves} | " + " | ".join(r.cell(pid) for r in self.runs) + " |")
        meta = ["", "| Client | Phiên bản | Model | Lúc | Chi phí |", "|---|---|---|---|---|"]
        for r in self.runs:
            meta.append(f"| {r.client} | {r.version} | {r.model or '—'} | {r.at} | ${r.cost_usd:.2f} |")
        details = ["", "## Quan sát", ""]
        for r in self.runs:
            for x in r.results:
                details.append(f"- **{r.client} {x.probe}** {'✅' if x.passed else '✗'} — {x.detail}")
        return "\n".join(head + rows + meta + details) + "\n"


# ------------------------------------------------------------ đọc lại

_META = re.compile(r"^\| (\w+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| \$([\d.]+) \|$")
_ROW = re.compile(r"^\| (C\d) [^|]*\| [^|]*\| (.*) \|$")
_GEN = re.compile(r"ngày \*\*(\d{4}-\d{2}-\d{2})\*\*")
_OBS = re.compile(r"^- \*\*(\w+) (C\d)\*\* [✅✗] — (.*)$")


def parse(text: str) -> Report:
    """Đọc lại bảng — đủ để trả lời "được phát hành không". Không tin gì
    ngoài ô ✅/✗, ngày, và tên client."""
    rep = Report(runs=[])
    m = _GEN.search(text)
    if m:
        rep.generated = m.group(1)
    clients: list[str] = []
    for line in text.splitlines():
        if line.startswith("| Phép thử |"):
            clients = [c.strip() for c in line.split("|")[3:-1]]
            rep.runs = [ClientRun(client=c, version="?") for c in clients]
            continue
        rm = _ROW.match(line)
        if rm and clients:
            cells = [c.strip() for c in rm.group(2).split("|")]
            for run, cell in zip(rep.runs, cells):
                if cell in ("✅", "✗"):
                    run.results.append(ProbeResult(probe=rm.group(1), passed=(cell == "✅")))
            continue
        om = _OBS.match(line)
        if om:
            run = rep.run_for(om.group(1))
            if run is not None:
                for r in run.results:
                    if r.probe == om.group(2):
                        r.detail = om.group(3)
            continue
        mm = _META.match(line)
        if mm:
            run = rep.run_for(mm.group(1).strip())
            if run is not None:
                run.version = mm.group(2).strip()
                run.model = mm.group(3).strip()
                run.at = mm.group(4).strip()
                run.cost_parsed = float(mm.group(5))
    return rep


def release_ready(report: Report, *, today: date | None = None,
                  max_age_days: int = MAX_AGE_DAYS) -> tuple[bool, str]:
    """Được phát hành không, và vì sao không."""
    today = today or date.today()
    try:
        gen = date.fromisoformat(report.generated)
    except ValueError:
        return False, "bảng không có ngày"
    age = (today - gen).days
    if age > max_age_days:
        return False, f"bảng cũ {age} ngày (> {max_age_days}) — chạy lại hợp quy"
    for client in RELEASE_CLIENTS:
        run = report.run_for(client)
        if run is None:
            return False, f"chưa có cột {client}"
        if not run.passed:
            hong = [r.probe for r in run.results if not r.passed]
            thieu = [p[0] for p in PROBES if p[0] not in {r.probe for r in run.results}]
            return False, f"{client}: ✗ {', '.join(hong)}" if hong else f"{client}: thiếu {', '.join(thieu)}"
    return True, "hợp quy đủ và mới"
