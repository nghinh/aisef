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


_TOOL_NAMES = {"read": "Read", "write": "Write", "edit": "Edit", "bash": "Bash", "glob": "Glob",
               "grep": "Grep", "list": "LS", "webfetch": "WebFetch", "todowrite": "TodoWrite", "skill": "Skill"}


def parse_json_events(lines) -> RunResult:
    """Luồng `opencode run --format json` → `RunResult` chuẩn. Dòng không phải
    JSON (banner, cảnh báo) bị bỏ qua, không ném."""
    import json as _json

    from .stream import ToolUse

    res = RunResult()
    texts: list[str] = []
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = _json.loads(line)
        except ValueError:
            continue
        part = ev.get("part") or {}
        kind = ev.get("type")
        if kind == "text":
            texts.append(str(part.get("text") or ""))
        elif kind == "tool_use":
            ten = str(part.get("tool") or "")
            state = part.get("state") or {}
            res.tool_uses.append(ToolUse(name=_TOOL_NAMES.get(ten.lower(), ten), tool_use_id=str(part.get("callID") or ""),
                                         input=dict(state.get("input") or {})))
            if state.get("status") == "error":
                res.guard_messages.append(str(state.get("output") or state.get("error") or "")[:300])
        elif kind == "step_finish":
            res.num_turns += 1
            tk = part.get("tokens") or {}
            res.input_tokens += int(tk.get("input") or 0)
            res.output_tokens += int(tk.get("output") or 0)
            cache = tk.get("cache") or {}
            res.cache_read_tokens += int(cache.get("read") or 0)
            res.cache_creation_tokens += int(cache.get("write") or 0)
            res.cost_usd += float(part.get("cost") or 0.0)
        if ev.get("sessionID") and not res.session_id:
            res.session_id = str(ev["sessionID"])
    res.text = "".join(texts)
    return res


class OpenCodeAdapter(ClientAdapter):
    id = "opencode"

    def __init__(self, binary: str = BINARY):
        self.binary = binary

    def available(self) -> bool:
        return bool(shutil.which(self.binary))

    def capabilities(self) -> dict[Capability, Support]:
        return {
            Capability.HEADLESS: Support.NATIVE,            # opencode run
            # Bằng chứng `par` STORY-02-01: cost=0, turns=0 cả bốn phiên. `--format
            # json` có trong `--help` nhưng chưa được chứng minh — tới lúc đó, nói
            # thật là không có. (task nâng cấp đã mở, xem ACTION-PLAN đợt 2)
            Capability.MACHINE_OUTPUT: Support.NATIVE,     # --format json, đo 2026-09-05
            Capability.PRE_TOOL_GUARD: Support.NATIVE,     # chứng minh 2026-09-05, xem docstring
            Capability.TOOL_ALLOWLIST: Support.EMULATED,  # emulated by: guardrails.check_role_tool
            Capability.DIR_ALLOWLIST: Support.UNSUPPORTED,  # không có cờ tương đương
            Capability.SUBAGENT: Support.NATIVE,            # opencode agent
            Capability.MODEL_ROUTING: Support.NATIVE,       # --model
            # `opencode stats` tồn tại nhưng không có mã nào gọi và ghi vào bằng
            # chứng; evidence thật ghi cost=0. Không mã mô phỏng → không khai mô phỏng.
            Capability.COST_REPORTING: Support.NATIVE,     # step_finish.cost/tokens — số của nhà cung cấp
            Capability.TURN_LIMIT: Support.UNSUPPORTED,     # dùng timeout thay
        }

    def build_command(self, spec: RunSpec) -> list[str]:
        # `--dir` chứ không chỉ `cwd=`: OpenCode dò gốc dự án riêng, và với
        # worktree nằm trong `<dự án>/.aisdlc/worktrees/` nó đi ngược lên
        # tới gốc dự án rồi **nói với model rằng đó là nơi làm việc**. Model
        # sau đó đọc/ghi bằng đường dẫn tuyệt đối vào gốc dự án và đặt
        # `workdir` của từng lệnh bash ở đó — công việc rơi thẳng lên thân
        # cây, worktree vẫn trống. Đo được trong bản ghi phiên:
        #
        #   {"tool":"read","input":{"filePath":"/…/par/src/reverse-words.js"}}
        #   {"tool":"bash","input":{"command":"git add … && git commit …",
        #                           "workdir":"/…/par"}}
        cmd = [self.binary, "run", "--dir", str(spec.workdir), spec.prompt]
        if spec.model:
            cmd += ["--model", spec.model]
        cmd.insert(2, "--format")
        cmd.insert(3, "json")
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

        # `--format json` (đo 2026-09-05, OpenCode 1.18.26): mỗi dòng một sự kiện
        # `step_start` / `text` / `tool_use` (part.tool, state.input/output) /
        # `step_finish` (tokens, cost). Cost là số nhà cung cấp báo — 9router
        # báo 0, đó là sự thật của nhà cung cấp, không phải của harness.
        res = parse_json_events(proc.stdout.splitlines())
        res.ok = proc.returncode == 0
        res.duration_ms = int((time.monotonic() - started) * 1000)
        res.error = "" if proc.returncode == 0 else (proc.stderr.strip()[:500] or "exit != 0")
        res.raw_result = {"returncode": proc.returncode, **res.raw_result}
        return res
