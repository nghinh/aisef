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

from abc import ABC, abstractmethod
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
