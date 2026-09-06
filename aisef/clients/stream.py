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
import re
from dataclasses import dataclass, field
from typing import Iterable


#: Dấu nhận biết thông báo **của hook**, không phải mọi lỗi tool có chữ
#: "hook". Tìm chuỗi con "hook" là quá rộng: dự án React nói về hook suốt
#: ngày, và một `grep` hỏng trên `useEffect` đủ làm cờ `guard_blocked`
#: bật lên. Cờ sai ở đây đi thẳng vào báo cáo nghiệm thu và làm người đọc
#: đuổi theo lỗi không tồn tại.
GUARD_MESSAGE = re.compile(
    r"(?:Pre|Post)ToolUse:\S*\s+hook\b|\bStop:?\s*hook\b|\bhook error\b",
    re.IGNORECASE,
)


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
    #: Mọi đoạn văn assistant theo thứ tự. `text` chỉ là câu chốt — mà câu
    #: chốt có thể là trả lời cho hook Stop chứ không phải cho việc (hợp quy
    #: C4 trượt vì thế, 2026-09-05).
    texts: list[str] = field(default_factory=list)
    #: Thông báo từ hook đã chặn một tool. Lấy từ `tool_result` chứ không
    #: từ `hook_response`: quan sát trên luồng thật cho thấy Claude Code
    #: **không** phát `hook_response` cho lần hook chặn — nó đưa thẳng lý
    #: do vào kết quả tool cho agent đọc.
    guard_messages: list[str] = field(default_factory=list)

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
    def guard_blocked(self) -> bool:
        """True khi **guard của framework** chặn ít nhất một thao tác.

        Đây mới là tín hiệu chất lượng: agent định làm điều bị cấm.
        """
        return bool(self.guard_messages) or any(h.blocked for h in self.hooks)

    @property
    def permission_limited(self) -> bool:
        """True khi client từ chối một tool vì quyền, không phải vì guard.

        Ví dụ ``WebSearch`` bị chặn trong môi trường không có mạng. Đây là
        **hạn chế môi trường**, không phải agent làm sai — gộp chung với
        guard sẽ báo cáo sai bản chất, và dẫn tới quyết định sai về việc
        có thử lại hay chặn story.
        """
        return bool(self.denials) and not self.guard_blocked

    @property
    def was_blocked(self) -> bool:
        """Có thao tác nào bị từ chối không, bất kể vì lý do gì."""
        return bool(self.denials) or self.guard_blocked

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
            "guard_blocked": self.guard_blocked,
            "guard_messages": self.guard_messages,
            "permission_limited": self.permission_limited,
            "error": self.error,
        }


#: Kết cục một lượt, chuẩn hoá qua mọi client (ADR-005 V11 B). Danh sách
#: đóng: `aisef status` đếm theo nó, `Attempt.infra` đọc nó thay vì dò chuỗi.
EXIT_STATUSES = ("ok", "max_turns", "timeout", "cost", "context", "permission", "infra", "error")

#: Kết cục **không phải lỗi của agent** — thử lại không tính vào hạn mức
#: chất lượng (`run.max_retries`), có hạn mức hạ tầng riêng.
INFRA_STATUSES = ("timeout", "infra")


def exit_status_of(res: RunResult) -> str:
    """Suy kết cục từ `subtype`/`terminal_reason`/`stop_reason`/`error`. Hàm
    thuần: chỉ đọc `res`, không biết `max_turns` cấu hình — trần lượt là thứ
    client tự báo (`terminal_reason: max_turns`, e9 01-01 61/60, 01-05 91/90).

    Thứ tự có chủ đích: trần lượt trước hạ tầng — lượt chạm trần thường kèm
    thông báo lỗi, xếp nó vào "hạ tầng" thì story ngốn lượt được thử lại
    miễn phí. Client cắt vì hết giờ báo "quá <n>s" (`claude_code.run`,
    `opencode.run`); không có sự kiện `result` là tiến trình chết giữa chừng.
    """
    if res.ok:
        return "ok"
    raw = res.raw_result or {}
    err = (res.error or "").lower()
    why = " ".join(
        [str(raw.get(k) or "") for k in ("subtype", "terminal_reason", "stop_reason")]
        + [str(raw.get("result") or "")[:300], err]
    ).lower()
    if "max_turns" in why:
        return "max_turns"
    if err.startswith("quá "):
        return "timeout"
    if "budget" in why or "max_cost" in why:
        return "cost"
    if any(m in why for m in ("prompt is too long", "context window", "context_length", "max_tokens")):
        return "context"
    if raw.get("api_error_status") or any(
        m in why for m in ("api_error", "overloaded", "connection",
                           "không chạy được", "không có sự kiện result")
    ):
        return "infra"
    if res.permission_limited:
        return "permission"
    return "error"


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

        elif etype == "user":
            for block in (ev.get("message", {}) or {}).get("content", []) or []:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                if not block.get("is_error"):
                    continue
                body = str(block.get("content") or "")
                if GUARD_MESSAGE.search(body):
                    res.guard_messages.append(body[:300])

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
                # Thứ tự có chủ đích. `subtype` vẫn là "success" ngay cả khi
                # `is_error` là true, nên lấy nó ra sẽ cho thông báo lỗi
                # "success" — vô nghĩa với người đọc lẫn với logic thử lại.
                res.error = str(
                    ev.get("api_error_status")
                    or ev.get("terminal_reason")
                    or (ev.get("result") or "").strip()[:200]
                    or "lỗi không rõ nguyên nhân"
                )

    res.texts = assistant_text
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
