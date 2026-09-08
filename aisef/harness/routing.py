"""Role routing — who does what, with which prompt, and what permissions.

Each role runs in its own **separate session**. The key invariant is that
the reviewer must not be the writer: not because a different model is better,
but because the writer already believes their code is correct — otherwise they
would have fixed it. Re-reviewing in the same session just re-asks the same
belief.

Therefore ``build_spec`` **refuses** to pass ``session_id`` to reviewer roles.
This is an easy place to "optimize" incorrectly: resuming sessions is much
cheaper, but the loss does not show up on the invoice.
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
    #: Whether this role may resume an existing session.
    may_resume: bool
    #: Tools completely disallowed for this role.
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
        # A reviewer that can edit code becomes a second write pass, and
        # no one is left to review.
        disallowed_tools=("Write", "Edit", "NotebookEdit"),
        note="Rà soát độc lập, phiên mới, không sửa gì.",
    ),
    SECURITY: Role(
        id=SECURITY,
        prompt="story-security-review",
        level=Level.READ_ONLY,
        may_resume=False,
        # Same reason as the reviewer, plus an additional one: it reads
        # code written by another agent, i.e. **untrusted data**. Granting
        # write access opens the exact attack surface it is looking for.
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
    """Model per role. Empty means use the client's default."""

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
        raise RoutingError(f"role not found: {role_id}. Available: {', '.join(sorted(ROLES))}")
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
    """Build a run spec for a role.

    Validates two invariants that break silently if wrong: the prompt must
    belong to that role, and roles that forbid session resumption must not
    receive a ``session_id``.
    """
    role = role_of(role_id)
    if prompt.name != role.prompt:
        raise RoutingError(
            f"role {role_id} uses prompt {role.prompt}, not {prompt.name}"
        )
    if session_id and not role.may_resume:
        raise RoutingError(
            f"role {role_id} must run in a new session. Resuming the writer's "
            f"session means the reviewer only re-asks its own existing beliefs."
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
