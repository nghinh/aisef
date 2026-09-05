"""Chạy agent bằng OpenCode CLI.

**Đã chứng minh chặn thật** (2026-09-05, opencode 1.18.26, model
``9router/mycombo``, agent đứng trong thư mục con của dự án):

* ``rm -rf /tmp/moi-thu-nghiem`` → tool báo failed bằng đúng stderr của
  guard, và tệp trong thư mục đó **vẫn còn** sau lượt chạy;
* ``Write ping.py`` chứa ``os.system(f"ping -c 1 {host}")`` → tool báo
  failed bằng đúng stderr của guard, và **không có tệp nào ra đĩa**.

Phép thử thứ hai cần thiết vì phép thử ghi khoá API trước đó vô giá trị:
model tự từ chối trước khi gọi tool, nên nó chứng minh model ngoan chứ
không chứng minh guard chặn. Ca thử phải là thứ model sẵn sàng làm.

Cũng đã xác nhận plugin ở ``.opencode/plugin/`` cấp dự án được nạp khi
agent chạy từ thư mục con — đúng tình huống worktree của story.

Vì thế ``PRE_TOOL_GUARD`` khai ``NATIVE``. Hai mục còn lại vẫn hạ mức
thật: OpenCode không có giới hạn lượt và không phát luồng sự kiện có cấu
trúc, nên chi phí phải hỏi riêng.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from .base import Capability, ClientAdapter, RunSpec, Support
from .stream import RunResult

BINARY = "opencode"


class OpenCodeAdapter(ClientAdapter):
    id = "opencode"

    def __init__(self, binary: str = BINARY):
        self.binary = binary

    def available(self) -> bool:
        return bool(shutil.which(self.binary))

    def capabilities(self) -> dict[Capability, Support]:
        return {
            Capability.HEADLESS: Support.NATIVE,            # opencode run
            Capability.MACHINE_OUTPUT: Support.EMULATED,    # qua export <sessionID>
            Capability.PRE_TOOL_GUARD: Support.NATIVE,     # chứng minh 2026-09-05, xem docstring
            Capability.TOOL_ALLOWLIST: Support.EMULATED,    # qua permission config
            Capability.DIR_ALLOWLIST: Support.UNSUPPORTED,  # không có cờ tương đương
            Capability.SUBAGENT: Support.NATIVE,            # opencode agent
            Capability.MODEL_ROUTING: Support.NATIVE,       # --model
            Capability.COST_REPORTING: Support.EMULATED,    # qua opencode stats
            Capability.TURN_LIMIT: Support.UNSUPPORTED,     # dùng timeout thay
        }

    def build_command(self, spec: RunSpec) -> list[str]:
        cmd = [self.binary, "run", spec.prompt]
        if spec.model:
            cmd += ["--model", spec.model]
        return cmd

    def run(self, spec: RunSpec) -> RunResult:
        if not self.available():
            return RunResult(ok=False, error=f"không tìm thấy lệnh {self.binary}")
        if not Path(spec.workdir).is_dir():
            return RunResult(ok=False, error=f"workdir không tồn tại: {spec.workdir}")

        started = time.monotonic()
        try:
            proc = subprocess.run(
                self.build_command(spec),
                cwd=str(spec.workdir),
                capture_output=True,
                text=True,
                timeout=spec.timeout_seconds,
                env={**os.environ, **spec.env} if spec.env else None,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return RunResult(ok=False, error=f"quá {spec.timeout_seconds}s")
        except OSError as e:
            return RunResult(ok=False, error=f"không chạy được: {e}")

        # OpenCode không phát luồng sự kiện có cấu trúc như Claude Code.
        # Chỉ lấy được văn bản và mã thoát; cost phải hỏi riêng qua `stats`.
        return RunResult(
            ok=proc.returncode == 0,
            text=proc.stdout,
            duration_ms=int((time.monotonic() - started) * 1000),
            error="" if proc.returncode == 0 else (proc.stderr.strip()[:500] or "exit != 0"),
            raw_result={"returncode": proc.returncode},
        )
