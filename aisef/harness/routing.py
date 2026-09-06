"""Định tuyến vai — ai làm việc gì, với prompt nào, quyền tới đâu.

Mỗi vai là một **phiên riêng**. Điều quan trọng nhất ở đây là người rà
soát không được là người viết: không phải vì model khác thì giỏi hơn, mà
vì người viết đã tin đoạn code của mình đúng — nếu không họ đã sửa rồi.
Rà lại trong cùng phiên chỉ là hỏi lại chính niềm tin đó.

Vì thế ``build_spec`` **từ chối** truyền ``session_id`` cho vai rà soát.
Đây là chỗ dễ "tối ưu" nhầm: nối tiếp phiên rẻ hơn nhiều, và cái mất đi
thì không hiện ra trong hoá đơn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..clients.base import RunSpec
from ..config import Config
from .prompts import Prompt
from .sandbox import Level

DEVELOPER = "developer"
REVIEWER = "reviewer"
SECURITY = "security"
DESIGNER = "designer"


@dataclass(frozen=True)
class Role:
    id: str
    prompt: str
    level: Level
    #: Vai này có được nối tiếp phiên đang có không.
    may_resume: bool
    #: Tool bị cấm hẳn với vai này.
    disallowed_tools: tuple[str, ...] = ()
    note: str = ""


ROLES: dict[str, Role] = {
    DEVELOPER: Role(
        id=DEVELOPER,
        prompt="story-implement",
        level=Level.WORKSPACE_WRITE,
        may_resume=True,
        note="Viết code cho một story, trong worktree riêng của story.",
    ),
    REVIEWER: Role(
        id=REVIEWER,
        prompt="story-review",
        level=Level.READ_ONLY,
        may_resume=False,
        # Người rà soát mà sửa được code thì nó thành lượt viết thứ hai, và
        # không còn ai rà soát nữa.
        disallowed_tools=("Write", "Edit", "NotebookEdit"),
        note="Rà soát độc lập, phiên mới, không sửa gì.",
    ),
    SECURITY: Role(
        id=SECURITY,
        prompt="story-security-review",
        level=Level.READ_ONLY,
        may_resume=False,
        # Cùng lý do như người rà soát, cộng thêm một lý do riêng: nó đọc
        # code do agent khác viết, tức **dữ liệu không tin được**. Cho nó
        # quyền ghi là mở đúng đường mà nó đang đi tìm.
        disallowed_tools=("Write", "Edit", "NotebookEdit"),
        note="Rà soát bảo mật theo ngữ nghĩa, phiên mới, không sửa gì.",
    ),
    DESIGNER: Role(
        id=DESIGNER,
        prompt="mockup-screen",
        level=Level.WORKSPACE_WRITE,
        may_resume=False,
        note="Dựng mockup một màn hình.",
    ),
}


class RoutingError(ValueError):
    pass


@dataclass
class Routing:
    """Model cho từng vai. Rỗng nghĩa là dùng mặc định của client."""

    models: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: Config | None) -> "Routing":
        if config is None:
            return cls()
        return cls(models={
            role: str(config.get(f"route.{role}_model", "") or "")
            for role in ROLES
        })

    def model_for(self, role_id: str) -> str:
        return self.models.get(role_id, "")


def role_of(role_id: str) -> Role:
    if role_id not in ROLES:
        raise RoutingError(f"vai không có: {role_id}. Có: {', '.join(sorted(ROLES))}")
    return ROLES[role_id]


def build_spec(
    role_id: str,
    prompt: Prompt,
    context: dict,
    *,
    workdir: Path,
    config: Config | None = None,
    routing: Routing | None = None,
    session_id: str = "",
    allow_empty: tuple[str, ...] = (),
) -> RunSpec:
    """Dựng lượt chạy cho một vai.

    Kiểm hai điều mà nếu sai thì hỏng âm thầm: prompt phải đúng của vai đó,
    và vai không được nối phiên thì không được nhận ``session_id``.
    """
    role = role_of(role_id)
    if prompt.name != role.prompt:
        raise RoutingError(
            f"vai {role_id} dùng prompt {role.prompt}, không phải {prompt.name}"
        )
    if session_id and not role.may_resume:
        raise RoutingError(
            f"vai {role_id} phải chạy trong phiên mới. Nối tiếp phiên của "
            f"người viết thì người rà soát chỉ hỏi lại chính niềm tin đã có."
        )

    cfg = config
    return RunSpec(
        prompt=prompt.render(context, allow_empty=allow_empty),
        workdir=Path(workdir),
        model=(routing or Routing.from_config(cfg)).model_for(role_id),
        max_turns=cfg["run.max_turns"] if cfg else 0,
        timeout_seconds=cfg["run.timeout_seconds"] if cfg else 1800,
        disallowed_tools=list(role.disallowed_tools),
        session_id=session_id,
        env_allow=list(cfg["clients.env_allow"]) if cfg else [],
    )
