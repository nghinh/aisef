"""Chạy agent bằng Claude Code CLI.

Mọi cờ dùng ở đây đã kiểm chứng bằng thực nghiệm (spike S1, S2 —
`docs/SPIKE-REPORT.md`), không suy từ tài liệu:

* ``--output-format stream-json --verbose`` cho luồng sự kiện đọc được,
  kết thúc bằng sự kiện ``result`` mang cost, latency, usage và
  ``permission_denials``;
* ``--settings`` gắn hook, và hook trả mã 2 **chặn thật** tool — kể cả khi
  chạy với ``--permission-mode acceptEdits``;
* ``< /dev/null`` là bắt buộc, nếu không CLI chờ stdin ba giây mỗi lần gọi.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import Capability, ClientAdapter, RunSpec, Support
from .stream import RunResult, parse_stream

BINARY = "claude"


class ClaudeCodeAdapter(ClientAdapter):
    id = "claude"

    def __init__(self, binary: str = BINARY):
        self.binary = binary

    def available(self) -> bool:
        return bool(shutil.which(self.binary))

    def capabilities(self) -> dict[Capability, Support]:
        return {
            Capability.HEADLESS: Support.NATIVE,          # -p
            Capability.MACHINE_OUTPUT: Support.NATIVE,    # --output-format stream-json
            Capability.PRE_TOOL_GUARD: Support.NATIVE,    # --settings + PreToolUse (S2)
            Capability.TOOL_ALLOWLIST: Support.NATIVE,    # --allowed-tools
            Capability.DIR_ALLOWLIST: Support.NATIVE,     # --add-dir
            Capability.SUBAGENT: Support.NATIVE,          # --agents
            Capability.MODEL_ROUTING: Support.NATIVE,     # --model
            Capability.COST_REPORTING: Support.NATIVE,    # result.total_cost_usd
            Capability.TURN_LIMIT: Support.NATIVE,        # --max-turns
        }

    def build_command(self, spec: RunSpec) -> list[str]:
        """Dựng dòng lệnh. Tách riêng để test được mà không gọi model."""
        cmd = [
            self.binary,
            "-p", spec.prompt,
            "--output-format", "stream-json",
            "--verbose",
        ]
        if spec.system_prompt:
            cmd += ["--append-system-prompt", spec.system_prompt]
        if spec.model:
            cmd += ["--model", spec.model]
        if spec.max_turns:
            cmd += ["--max-turns", str(spec.max_turns)]
        if spec.allowed_tools:
            cmd += ["--allowed-tools", *spec.allowed_tools]
        if spec.disallowed_tools:
            cmd += ["--disallowed-tools", *spec.disallowed_tools]
        if spec.settings_file:
            cmd += ["--settings", str(spec.settings_file)]
        for d in spec.extra_dirs:
            cmd += ["--add-dir", str(d)]
        if spec.session_id:
            cmd += ["--session-id", spec.session_id]
        return cmd

    def run(self, spec: RunSpec) -> RunResult:
        if not self.available():
            return RunResult(ok=False, error=f"không tìm thấy lệnh {self.binary}")
        if not Path(spec.workdir).is_dir():
            return RunResult(ok=False, error=f"workdir không tồn tại: {spec.workdir}")

        try:
            proc = subprocess.run(
                self.build_command(spec),
                cwd=str(spec.workdir),
                capture_output=True,
                text=True,
                timeout=spec.timeout_seconds,
                stdin=subprocess.DEVNULL,  # không có: CLI chờ stdin 3s mỗi lần
            )
        except subprocess.TimeoutExpired:
            # Hết giờ là lỗi hạ tầng, không phải lỗi chất lượng — phân biệt
            # được thì mới quyết đúng nên thử lại hay chặn story.
            return RunResult(ok=False, error=f"quá {spec.timeout_seconds}s")
        except OSError as e:
            return RunResult(ok=False, error=f"không chạy được: {e}")

        result = parse_stream(proc.stdout.splitlines())
        if not result.raw_result and proc.stderr.strip():
            result.error = proc.stderr.strip()[:500]
        return result
