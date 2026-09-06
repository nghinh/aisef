"""Giao diện chung cho mọi client agent.

Framework nói chuyện với Claude Code và OpenCode qua cùng một giao diện.
Chỗ khác nhau giữa chúng — cách truyền prompt, cách đọc kết quả, cách gắn
guard — nằm gọn trong từng hiện thực, không rò ra phần điều phối.

**Năng lực được khai báo, không được giả định.** Mỗi client trả về bảng
`capabilities()` nói rõ nó làm được gì ở mức nào. Client không gắn được
guard tiền kiểm thì phải khai `POST_HOC`, để framework biết mà chuyển sang
hậu kiểm ở bước verify và ghi mức bảo đảm thấp hơn vào evidence — thay vì
im lặng chạy như thể vẫn đủ (bất biến 10).
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .stream import RunResult


class Support(str, Enum):
    """Mức hỗ trợ một năng lực."""

    NATIVE = "native"          # client có sẵn, dùng thẳng
    EMULATED = "emulated"      # framework mô phỏng bằng cơ chế khác
    POST_HOC = "post_hoc"      # chỉ kiểm được sau, không chặn được lúc xảy ra
    UNSUPPORTED = "unsupported"

    @property
    def blocks_at_source(self) -> bool:
        """Có chặn được ngay lúc hành vi xảy ra không."""
        return self in (Support.NATIVE, Support.EMULATED)


class Capability(str, Enum):
    HEADLESS = "headless"              # chạy không cần người
    MACHINE_OUTPUT = "machine_output"  # kết quả máy đọc được
    PRE_TOOL_GUARD = "pre_tool_guard"  # chặn trước khi tool chạy
    TOOL_ALLOWLIST = "tool_allowlist"  # giới hạn tool được dùng
    DIR_ALLOWLIST = "dir_allowlist"    # giới hạn thư mục truy cập
    SUBAGENT = "subagent"              # sinh sub-agent
    MODEL_ROUTING = "model_routing"    # chọn model theo vai
    COST_REPORTING = "cost_reporting"  # báo chi phí, token
    TURN_LIMIT = "turn_limit"          # giới hạn số lượt


@dataclass
class RunSpec:
    """Một lượt chạy agent."""

    prompt: str
    workdir: Path
    system_prompt: str = ""
    model: str = ""
    max_turns: int = 0
    timeout_seconds: int = 1800
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    extra_dirs: list[Path] = field(default_factory=list)
    settings_file: Path | None = None
    session_id: str = ""
    #: Biến môi trường thêm vào tiến trình client. Guard chạy trong hook là
    #: tiến trình con của client, nên phạm vi ghi và mã story tới được guard
    #: qua đúng đường này.
    env: dict[str, str] = field(default_factory=dict)
    #: Tiền tố biến của máy được cho qua **thêm** (`clients.env_allow`).
    #: Mặc định rỗng: ngoài `ENV_KEEP`/`ENV_KEEP_PREFIXES` không gì qua.
    env_allow: list[str] = field(default_factory=list)


# ------------------------------------------------------------ môi trường con

#: Biến của máy được giữ **nguyên tên** cho tiến trình client — đủ để một CLI
#: chạy (tìm lệnh, thư mục nhà, locale, tmp, chứng chỉ), không hơn.
ENV_KEEP = frozenset({"PATH", "HOME", "LANG", "TERM", "TMPDIR", "SHELL", "USER", "LOGNAME",
                      "SSL_CERT_FILE"})
#: Tiền tố được giữ: locale, khoá/URL model của Claude, biến harness đặt cho
#: guard. `CLAUDE*` của phiên cha **không** có ở đây — hợp quy C3 đo phiên con
#: thừa hưởng chúng thì tự chuyển sang Bash và né guard Write/Edit (lỗi 4).
ENV_KEEP_PREFIXES = ("LC_", "ANTHROPIC_", "AISEF_")
#: Git trong phiên agent không được cầm credential của máy: không hỏi
#: terminal, askpass luôn thất bại, và `credential.helper=` rỗng **xoá** danh
#: sách helper đã khai ở system/global — osxkeychain không được hỏi (đo
#: 2026-09-06, git 2.53: helper giả không được gọi, `could not read
#: Username`). Ba biến `GIT_CONFIG_*` đi cùng nhau: có COUNT mà thiếu
#: KEY/VALUE thì git chết. Push/merge là việc của harness
#: (`worktree.merge_story`) — tiến trình harness không nhận bộ này, chỉ
#: tiến trình client.
GIT_NO_CREDENTIALS: dict[str, str] = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "/usr/bin/false",
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "credential.helper",
    "GIT_CONFIG_VALUE_0": "",
}


def child_env(spec_env: dict[str, str], *, allow_prefixes: Iterable[str] = ()) -> dict[str, str]:
    """Môi trường cho tiến trình client: **allowlist**, không phải `os.environ`
    bớt đi vài thứ (ADR-005 V2).

    Trước: OpenCode nhận trọn `os.environ` (63 biến trên máy đo), Claude chỉ
    bị bỏ `CLAUDE*`; OpenCode từng ghi secret của máy ra log của nó. Agent
    không cầm thứ nó không cần: giữ `ENV_KEEP` + `ENV_KEEP_PREFIXES` + tiền
    tố dự án khai ở `clients.env_allow`, cộng bộ vô hiệu credential git, rồi
    `spec_env` của harness đè lên trên. Giới hạn đã biết: token model của
    Claude nằm trong Keychain/OAuth của máy, harness không có broker — phiên
    con vẫn xác thực bằng tài khoản của máy.
    """
    # Tiền tố rỗng mở toang mọi biến — bỏ, không phải lỗi cấu hình đáng chết.
    prefixes = tuple(p for p in (*ENV_KEEP_PREFIXES, *allow_prefixes) if p)
    env = {k: v for k, v in os.environ.items() if k in ENV_KEEP or k.startswith(prefixes)}
    env.update(GIT_NO_CREDENTIALS)
    env.update(spec_env)
    return env


class ClientAdapter(ABC):
    """Một cách chạy agent. Hiện thực: Claude Code, OpenCode."""

    #: Tên hiển thị, cũng là khoá dùng trong cấu hình và báo cáo.
    id: str = ""

    @abstractmethod
    def available(self) -> bool:
        """Client có cài trên máy này không."""

    @abstractmethod
    def capabilities(self) -> dict[Capability, Support]:
        """Khai báo trung thực mức hỗ trợ từng năng lực."""

    @abstractmethod
    def run(self, spec: RunSpec) -> RunResult:
        """Chạy một lượt, trả kết quả đã chuẩn hoá."""

    # ------------------------------------------------------------ tiện ích

    def supports(self, capability: Capability) -> Support:
        return self.capabilities().get(capability, Support.UNSUPPORTED)

    def guards_block_at_source(self) -> bool:
        """Guard của client này chặn được ngay, hay chỉ kiểm sau."""
        return self.supports(Capability.PRE_TOOL_GUARD).blocks_at_source

    def degradations(self) -> list[str]:
        """Những năng lực không đạt mức lý tưởng — phải khai vào báo cáo."""
        out = []
        for cap, support in self.capabilities().items():
            if support is not Support.NATIVE:
                out.append(f"{cap.value}: {support.value}")
        return sorted(out)
