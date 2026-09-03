"""Kho trạng thái tiến độ — nguồn sự thật duy nhất về việc gì đã xong.

Trạng thái nằm **trên đĩa**, không trong bộ nhớ tiến trình. Đó là điều
kiện để:

* dừng giữa chừng rồi chạy lại tiếp đúng chỗ dở;
* control plane là CLI gọi-một-lần chứ không phải daemon (quyết định Đ2);
* nhiều bề mặt (Desktop, CLI, CI) cùng nhìn một tiến độ.

Hai bảo đảm khi ghi:

1. **Nguyên tử** — ghi ra file tạm rồi `replace`. Bị ngắt giữa chừng thì
   file cũ còn nguyên, không bao giờ để lại JSON cụt.
2. **Khoá độc quyền** — nhiều story chạy song song, mỗi story kết thúc lại
   cập nhật trạng thái; không khoá thì hai lần ghi gần nhau sẽ mất một.

Khoá dùng ``fcntl.flock``: tự nhả khi tiến trình chết, nên không để lại
khoá mồ côi như cách dùng file cờ.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterator

STATE_FILE = "sprint-status.json"
LOCK_SUFFIX = ".lock"
LOCK_TIMEOUT_SECONDS = 30


class StoryStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    VERIFYING = "verifying"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"

    @property
    def terminal(self) -> bool:
        return self in (StoryStatus.DONE, StoryStatus.BLOCKED, StoryStatus.FAILED)

    @property
    def satisfies_dependents(self) -> bool:
        """Chỉ story xong hẳn mới mở khoá cho story phụ thuộc nó."""
        return self is StoryStatus.DONE


#: Chuyển trạng thái hợp lệ. Ngăn những bước nhảy vô nghĩa như
#: pending → done mà không qua verifying.
ALLOWED: dict[StoryStatus, frozenset[StoryStatus]] = {
    StoryStatus.PENDING: frozenset({StoryStatus.RUNNING, StoryStatus.BLOCKED}),
    StoryStatus.RUNNING: frozenset({StoryStatus.VERIFYING, StoryStatus.FAILED, StoryStatus.BLOCKED}),
    StoryStatus.VERIFYING: frozenset({StoryStatus.DONE, StoryStatus.FAILED, StoryStatus.BLOCKED}),
    # thất bại còn lượt thử thì quay lại pending
    StoryStatus.FAILED: frozenset({StoryStatus.PENDING, StoryStatus.BLOCKED}),
    StoryStatus.BLOCKED: frozenset({StoryStatus.PENDING}),
    StoryStatus.DONE: frozenset(),
}


class TransitionError(ValueError):
    """Chuyển trạng thái không hợp lệ."""


class LockTimeout(TimeoutError):
    """Không lấy được khoá trong thời gian cho phép."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class StoryRecord:
    id: str
    epic_id: str = ""
    status: str = StoryStatus.PENDING.value
    attempts: int = 0
    wave: int = 0
    worktree: str = ""
    evidence: str = ""
    cost_usd: float = 0.0
    duration_ms: int = 0
    blocked_reason: str = ""
    updated_at: str = field(default_factory=_now)

    @property
    def state(self) -> StoryStatus:
        return StoryStatus(self.status)


@dataclass
class SprintState:
    stories: dict[str, StoryRecord] = field(default_factory=dict)
    current_epic: str = ""
    started_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    # --------------------------------------------------------- truy vấn

    def by_status(self, status: StoryStatus) -> list[StoryRecord]:
        return [r for r in self.stories.values() if r.state is status]

    def done_ids(self) -> set[str]:
        return {r.id for r in self.stories.values() if r.state.satisfies_dependents}

    def totals(self) -> dict[str, int]:
        counts = {s.value: 0 for s in StoryStatus}
        for r in self.stories.values():
            counts[r.status] += 1
        return counts

    @property
    def total_cost_usd(self) -> float:
        return sum(r.cost_usd for r in self.stories.values())

    def cost_outliers(self, multiple: float) -> list[StoryRecord]:
        """Story tốn hơn `multiple` lần trung vị — dấu hiệu cần xem lại.

        Dùng trung vị chứ không dùng trung bình: một story cực đắt sẽ kéo
        trung bình lên và tự che chính nó.
        """
        costs = sorted(r.cost_usd for r in self.stories.values() if r.cost_usd > 0)
        if len(costs) < 3:
            return []
        mid = len(costs) // 2
        median = costs[mid] if len(costs) % 2 else (costs[mid - 1] + costs[mid]) / 2
        if median <= 0:
            return []
        return [r for r in self.stories.values() if r.cost_usd > median * multiple]


class StateStore:
    """Đọc/ghi trạng thái với khoá độc quyền và ghi nguyên tử."""

    def __init__(self, artifact_root: Path | str):
        self.root = Path(artifact_root)
        self.path = self.root / STATE_FILE
        self.lock_path = self.root / (STATE_FILE + LOCK_SUFFIX)

    # --------------------------------------------------------- khoá

    @contextmanager
    def _locked(self, timeout: float = LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise LockTimeout(
                            f"không lấy được khoá {self.lock_path} sau {timeout}s"
                        ) from None
                    time.sleep(0.05)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    # --------------------------------------------------------- đọc, ghi

    def load(self) -> SprintState:
        if not self.path.is_file():
            return SprintState()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # File hỏng: bắt đầu lại còn hơn chạy trên trạng thái nửa vời.
            return SprintState()
        stories = {
            sid: StoryRecord(**rec) for sid, rec in (raw.get("stories") or {}).items()
        }
        return SprintState(
            stories=stories,
            current_epic=raw.get("current_epic", ""),
            started_at=raw.get("started_at", _now()),
            updated_at=raw.get("updated_at", _now()),
        )

    def save(self, state: SprintState) -> None:
        state.updated_at = _now()
        payload = {
            "stories": {sid: asdict(r) for sid, r in state.stories.items()},
            "current_epic": state.current_epic,
            "started_at": state.started_at,
            "updated_at": state.updated_at,
        }
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    @contextmanager
    def transaction(self) -> Iterator[SprintState]:
        """Đọc — sửa — ghi dưới một khoá.

        Đọc bên trong khoá là điều bắt buộc: đọc ngoài khoá rồi mới ghi sẽ
        đè mất thay đổi của tiến trình khác xen vào giữa.
        """
        with self._locked():
            state = self.load()
            yield state
            self.save(state)

    # --------------------------------------------------------- thao tác

    def register(self, story_id: str, epic_id: str = "", wave: int = 0) -> None:
        with self.transaction() as st:
            if story_id not in st.stories:
                st.stories[story_id] = StoryRecord(id=story_id, epic_id=epic_id, wave=wave)

    def transition(
        self,
        story_id: str,
        to: StoryStatus,
        *,
        reason: str = "",
        cost_usd: float = 0.0,
        duration_ms: int = 0,
        evidence: str = "",
        worktree: str = "",
    ) -> StoryRecord:
        """Chuyển trạng thái, từ chối bước nhảy không hợp lệ."""
        with self.transaction() as st:
            rec = st.stories.get(story_id)
            if rec is None:
                rec = StoryRecord(id=story_id)
                st.stories[story_id] = rec

            current = rec.state
            if to is not current and to not in ALLOWED[current]:
                raise TransitionError(f"{story_id}: {current.value} → {to.value} không hợp lệ")

            if to is StoryStatus.RUNNING and current is not StoryStatus.RUNNING:
                rec.attempts += 1

            rec.status = to.value
            rec.updated_at = _now()
            if reason:
                rec.blocked_reason = reason
            if cost_usd:
                rec.cost_usd += cost_usd
            if duration_ms:
                rec.duration_ms += duration_ms
            if evidence:
                rec.evidence = evidence
            if worktree:
                rec.worktree = worktree
            return rec

    def set_current_epic(self, epic_id: str) -> None:
        with self.transaction() as st:
            st.current_epic = epic_id
