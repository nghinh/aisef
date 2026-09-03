"""Chạy agent bằng OpenCode CLI.

**Khai báo thận trọng có chủ đích.** Spike S4 chưa chạy xong được ca thử
(provider trong môi trường thử phản hồi quá chậm), nên hai điều sau vẫn
chưa được chứng minh:

* ném lỗi trong hook ``tool.execute.before`` có **chặn** tool hay chỉ ghi log;
* plugin đặt ở ``.opencode/plugin/`` cấp dự án có được nạp không.

Vì thế ``PRE_TOOL_GUARD`` khai là ``POST_HOC``, không phải ``NATIVE``.
Framework sẽ chạy lại toàn bộ guard ở bước verify và ghi mức bảo đảm thấp
hơn vào evidence. Nâng lên ``NATIVE`` chỉ khi có phép thử chạy xong chứng
minh guard chặn thật — khai xanh trước là tự lừa mình về mức an toàn
đang có.
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
            Capability.PRE_TOOL_GUARD: Support.POST_HOC,    # S4 chưa chứng minh
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
