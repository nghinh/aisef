"""Hợp quy sandbox — S1–S5 chạy **thật** trên từng provider, ghi
``docs/SANDBOX-CONFORMANCE.md`` (ADR-005 V5, T6).

    python3 -m tests.sandbox_conformance
    AISDLC_SANDBOX_CONFORMANCE=1 python3 -m unittest tests.sandbox_conformance

Mỗi ô là một lần chạy thật, kèm thời gian; không ô nào suy từ khai báo.
Docker chạy khi daemon có (``docker info``); Local luôn chạy — và cột Local
✗ ở S1–S4 chính là điều bảng này phải nói ra: chạy thẳng trên máy không
bảo đảm gì (bất biến 10). S5 (timeout) là việc của harness, provider nào
cũng phải đạt.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisdlc.harness import sandbox  # noqa: E402
from aisdlc.harness.sandbox import Guarantee, Level, SandboxResult, SandboxSpec  # noqa: E402

ENABLED = os.environ.get("AISDLC_SANDBOX_CONFORMANCE") == "1"
DOC = ROOT / "docs" / "SANDBOX-CONFORMANCE.md"

#: Harness đặt canary vào môi trường máy chủ, **ngoài** `spec.env` — S4 hỏi
#: chúng có lọt vào trong không.
CANARY = {"AISDLC_CANARY": "hoang-yen", "ANTHROPIC_CANARY": "hoang-yen", "AWS_CANARY": "hoang-yen"}
PREFIXES = ("AISDLC_", "ANTHROPIC_", "AWS_")


@dataclass(frozen=True)
class Probe:
    id: str
    what: str
    proves: str
    cmd: list[str]
    level: Level
    #: Bảo đảm phép thử kiểm; None = việc của harness (timeout).
    guarantee: Guarantee | None
    judge: Callable[[SandboxResult, Path], bool]
    timeout: int = 60


def _no_canary(r: SandboxResult, ws: Path) -> bool:
    return r.ok and not any(line.startswith(PREFIXES) for line in r.stdout.splitlines())


PROBES: list[Probe] = [
    Probe("S1", "`wget -T 3 -O- https://example.com` ở WORKSPACE_WRITE", "mạng bị chặn, kể cả DNS",
          ["wget", "-q", "-T", "3", "-O-", "https://example.com"], Level.WORKSPACE_WRITE,
          # 127 = không có `wget` trên máy: lệnh chưa chạy, không kết luận được "bị chặn".
          Guarantee.NETWORK_NONE, lambda r, ws: r.exit_code not in (0, 127) and not r.ok),
    Probe("S2", "`sh -c 'echo x > x'` ở READ_ONLY", "không ghi được workspace",
          ["sh", "-c", "echo x > x"], Level.READ_ONLY,
          Guarantee.READ_ONLY_FS, lambda r, ws: not r.ok and not (ws / "x").exists()),
    Probe("S3", "`sh -c 'touch /etc/x'` ở WORKSPACE_WRITE", "không ghi được ngoài workspace",
          ["sh", "-c", "touch /etc/x"], Level.WORKSPACE_WRITE,
          Guarantee.NON_ROOT, lambda r, ws: not r.ok and not Path("/etc/x").exists()),
    Probe("S4", "`env` ở WORKSPACE_WRITE; harness đặt canary `AISDLC_*`/`ANTHROPIC_*`/`AWS_*` ngoài `spec.env`",
          "bí mật máy chủ không vào trong",
          ["env"], Level.WORKSPACE_WRITE, Guarantee.SECRETS_ABSENT, _no_canary),
    Probe("S5", "`sleep 9999`, timeout 2 s", "thoát 124, `timed_out`, không để lại container",
          ["sleep", "9999"], Level.WORKSPACE_WRITE, None,
          lambda r, ws: r.timed_out and r.exit_code == 124, timeout=2),
]


@dataclass
class Cell:
    passed: bool
    ms: int
    detail: str


def _leftover_containers() -> list[str]:
    try:
        out = subprocess.run(["docker", "ps", "-q", "--filter", "name=aisdlc-"],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return out.split()


def run_probe(provider: str, probe: Probe, ws: Path) -> Cell:
    spec = SandboxSpec(workspace=ws, cmd=probe.cmd, level=probe.level,
                       timeout_seconds=probe.timeout, provider=provider, allow_degraded=True)
    started = time.monotonic()
    with mock.patch.dict(os.environ, CANARY):
        r = sandbox.run(spec)
    ms = int((time.monotonic() - started) * 1000)
    passed = probe.judge(r, ws)
    (ws / "x").unlink(missing_ok=True)
    tail = (r.stderr or r.stdout).strip().splitlines()
    detail = f"exit {r.exit_code}" + (", timed_out" if r.timed_out else "")
    if tail and probe.id != "S4":
        detail += f", `{tail[-1][:80]}`"
    if probe.id == "S5" and provider == "docker":
        # Giết CLI không giết container — đây là chỗ S5 từng lộ rò rỉ.
        con_lai = _leftover_containers()
        passed = passed and not con_lai
        detail += f", container còn lại: {len(con_lai)}"
    if probe.guarantee is not None:
        khai = sandbox.resolve_provider(provider).guarantees(probe.level)[probe.guarantee]
        if not khai.blocks_at_source:
            detail += (f" — provider khai `{probe.guarantee.value}={khai.value}`: "
                       "kết quả là hoàn cảnh máy, không phải bảo đảm")
    return Cell(passed, ms, detail)


def generate() -> tuple[str, dict[str, dict[str, Cell]]]:
    """Chạy S1–S5 trên mọi provider có mặt; trả (markdown, ô)."""
    providers = [p for p in ("docker", "local") if sandbox.resolve_provider(p).available()]
    cells: dict[str, dict[str, Cell]] = {p: {} for p in providers}
    with tempfile.TemporaryDirectory() as d:
        ws = Path(d) / "workspace"
        ws.mkdir()
        for p in providers:
            for probe in PROBES:
                cells[p][probe.id] = run_probe(p, probe, ws)
    return to_markdown(cells), cells


def _cell(c: Cell | None) -> str:
    if c is None:
        return "—"
    return f"{'✅' if c.passed else '✗'} {c.ms} ms"


def to_markdown(cells: dict[str, dict[str, Cell]]) -> str:
    cols = list(cells)
    out = ["# Hợp quy sandbox", "",
           f"Sinh bởi `python3 -m tests.sandbox_conformance`, ngày **{date.today().isoformat()}**. "
           "Mỗi ô là **một lần chạy thật** trên provider ấy (kèm thời gian); không ô nào suy từ "
           "khai báo. Docker chạy khi daemon có (`docker info`); Local luôn chạy — cột Local ✗ ở "
           "S1–S4 là điều bảng này phải nói ra: chạy thẳng trên máy không bảo đảm gì (bất biến 10).",
           "", "| Phép thử | Chứng minh | " + " | ".join(cols) + " |", "|---|---|" + "---|" * len(cols)]
    for pr in PROBES:
        out.append(f"| {pr.id} {pr.what} | {pr.proves} | "
                   + " | ".join(_cell(cells[c].get(pr.id)) for c in cols) + " |")
    out += ["", "## Bảo đảm khai (`ExecutionProvider.guarantees`)", "",
            "Bậc đọc: `READ_ONLY` cho `read_only_fs`, `WORKSPACE_WRITE` cho phần còn lại. "
            "`no_host_mount` không bậc nào đòi — mount worktree là thiết kế.", "",
            "| Bảo đảm | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    for g in Guarantee:
        lv = Level.READ_ONLY if g is Guarantee.READ_ONLY_FS else Level.WORKSPACE_WRITE
        out.append(f"| {g.value} | " + " | ".join(
            sandbox.resolve_provider(c).guarantees(lv)[g].value for c in cols) + " |")
    out += ["", "## Quan sát", ""]
    for c in cols:
        for pr in PROBES:
            cell = cells[c].get(pr.id)
            if cell:
                out.append(f"- **{c} {pr.id}** {'✅' if cell.passed else '✗'} — {cell.detail}")
    return "\n".join(out) + "\n"


@unittest.skipUnless(ENABLED, "bật bằng AISDLC_SANDBOX_CONFORMANCE=1")
class TestHopQuySandbox(unittest.TestCase):
    def test_s1_s5_moi_provider_mot_cot_chay_that(self):
        md, cells = generate()
        DOC.write_text(md, encoding="utf-8")
        self.assertIn("local", cells)
        self.assertTrue(cells["local"]["S5"].passed, "timeout là việc của harness")
        if "docker" in cells:
            thieu = [k for k, v in cells["docker"].items() if not v.passed]
            self.assertEqual(thieu, [], f"Docker trượt: {thieu}")


if __name__ == "__main__":
    md, cells = generate()
    DOC.write_text(md, encoding="utf-8")
    print(md)
    sys.exit(0 if all(v.passed for v in cells.get("docker", {}).values()) else 1)
