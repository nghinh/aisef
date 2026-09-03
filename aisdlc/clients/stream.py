"""Đọc luồng `stream-json` của Claude Code CLI.

Cấu trúc luồng được xác lập bằng thực nghiệm (spike S1, S2 — xem
`docs/SPIKE-REPORT.md`), không suy đoán từ tài liệu. Hai fixture trong
`tests/fixtures/` là luồng thật do `claude -p` sinh ra.

Các loại sự kiện quan sát được::

    system/hook_started      hook bắt đầu chạy
    system/hook_response     hook xong: exit_code, outcome, stdout, stderr
    system/init              phiên khởi tạo
    assistant                model nói hoặc gọi tool
    user                     kết quả tool trả về (is_error khi bị chặn)
    rate_limit_event         thông tin hạn mức
    system/post_turn_summary tóm tắt lượt
    result                   **sự kiện cuối** — cost, latency, usage, denials

Điều đáng giá nhất nằm ở `result`: `total_cost_usd`, `duration_ms`,
`ttft_ms`, `usage`, và `permission_denials` — danh sách những lần guard
chặn tool, kèm cả nội dung agent định ghi. Đó là bằng chứng máy đọc được
để đưa vào evidence, không phải lời agent tự khai.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class ToolUse:
    name: str
    tool_use_id: str
    input: dict


@dataclass(frozen=True)
class Denial:
    """Một lần guard chặn tool. Trích từ `result.permission_denials`."""

    tool_name: str
    tool_use_id: str
    tool_input: dict

    @property
    def target_path(self) -> str:
        """Đường dẫn bị chặn, nếu tool có khái niệm đường dẫn."""
        return self.tool_input.get("file_path", "")


@dataclass(frozen=True)
class HookRun:
    """Một lần hook chạy. `exit_code == 2` là quy ước chặn của Claude Code."""

    name: str
    event: str
    exit_code: int
    outcome: str
    stderr: str = ""

    @property
    def blocked(self) -> bool:
        return self.exit_code == 2


@dataclass
class RunResult:
    """Kết quả một lượt chạy client, đã chuẩn hoá."""

    ok: bool = False
    text: str = ""
    session_id: str = ""
    num_turns: int = 0
    stop_reason: str = ""

    cost_usd: float = 0.0
    duration_ms: int = 0
    duration_api_ms: int = 0
    ttft_ms: int = 0

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    tool_uses: list[ToolUse] = field(default_factory=list)
    denials: list[Denial] = field(default_factory=list)
    hooks: list[HookRun] = field(default_factory=list)

    error: str = ""
    raw_result: dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_tokens
            + self.cache_read_tokens
        )

    @property
    def was_blocked(self) -> bool:
        """True khi có ít nhất một tool bị guard chặn."""
        return bool(self.denials) or any(h.blocked for h in self.hooks)

    def evidence(self) -> dict:
        """Phần đưa vào `evidence/{story}.json`."""
        return {
            "ok": self.ok,
            "cost_usd": round(self.cost_usd, 6),
            "duration_ms": self.duration_ms,
            "ttft_ms": self.ttft_ms,
            "tokens": {
                "input": self.input_tokens,
                "output": self.output_tokens,
                "cache_creation": self.cache_creation_tokens,
                "cache_read": self.cache_read_tokens,
            },
            "num_turns": self.num_turns,
            "session_id": self.session_id,
            "denials": [
                {"tool": d.tool_name, "path": d.target_path} for d in self.denials
            ],
            "error": self.error,
        }


def _collect_assistant_tools(event: dict, out: list[ToolUse]) -> str:
    """Gom tool_use và text từ một sự kiện assistant."""
    text_parts = []
    for block in event.get("message", {}).get("content", []) or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use":
            out.append(
                ToolUse(
                    name=block.get("name", ""),
                    tool_use_id=block.get("id", ""),
                    input=block.get("input") or {},
                )
            )
        elif block.get("type") == "text":
            text_parts.append(block.get("text", ""))
    return "".join(text_parts)


def parse_stream(lines: Iterable[str]) -> RunResult:
    """Chuyển luồng `stream-json` thành `RunResult`.

    Dòng hỏng bị bỏ qua thay vì làm sập cả lượt chạy: mất một dòng log
    không đáng để mất kết quả của cả một story.
    """
    res = RunResult()
    assistant_text: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue

        etype = ev.get("type")

        if etype == "assistant":
            txt = _collect_assistant_tools(ev, res.tool_uses)
            if txt.strip():
                assistant_text.append(txt)

        elif etype == "system" and ev.get("subtype") == "hook_response":
            res.hooks.append(
                HookRun(
                    name=ev.get("hook_name", ""),
                    event=ev.get("hook_event", ""),
                    exit_code=int(ev.get("exit_code") or 0),
                    outcome=ev.get("outcome", ""),
                    stderr=ev.get("stderr", "") or "",
                )
            )

        elif etype == "result":
            res.raw_result = ev
            res.ok = ev.get("subtype") == "success" and not ev.get("is_error")
            res.text = ev.get("result", "") or ""
            res.session_id = ev.get("session_id", "") or ""
            res.num_turns = int(ev.get("num_turns") or 0)
            res.stop_reason = ev.get("stop_reason", "") or ""

            res.cost_usd = float(ev.get("total_cost_usd") or 0.0)
            res.duration_ms = int(ev.get("duration_ms") or 0)
            res.duration_api_ms = int(ev.get("duration_api_ms") or 0)
            res.ttft_ms = int(ev.get("ttft_ms") or 0)

            usage = ev.get("usage") or {}
            res.input_tokens = int(usage.get("input_tokens") or 0)
            res.output_tokens = int(usage.get("output_tokens") or 0)
            res.cache_creation_tokens = int(usage.get("cache_creation_input_tokens") or 0)
            res.cache_read_tokens = int(usage.get("cache_read_input_tokens") or 0)

            for d in ev.get("permission_denials") or []:
                res.denials.append(
                    Denial(
                        tool_name=d.get("tool_name", ""),
                        tool_use_id=d.get("tool_use_id", ""),
                        tool_input=d.get("tool_input") or {},
                    )
                )

            if ev.get("is_error") or ev.get("api_error_status"):
                res.error = str(ev.get("api_error_status") or ev.get("subtype") or "error")

    if not res.text and assistant_text:
        res.text = "\n".join(assistant_text)

    # Không có sự kiện `result` nghĩa là tiến trình chết giữa chừng.
    # Phải phân biệt rõ với "chạy xong nhưng thất bại" — hai thứ này cần
    # cách xử lý khác nhau (lỗi hạ tầng ≠ lỗi chất lượng).
    if not res.raw_result:
        res.ok = False
        res.error = res.error or "stream kết thúc không có sự kiện result"

    return res


def parse_file(path) -> RunResult:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return parse_stream(fh)
