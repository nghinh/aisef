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
    #: Qua cổng, **chưa** lên nhánh chính. Trước 2026-09-05 trạng thái này
    #: không tồn tại: `done` được ghi lúc qua cổng, trước merge — merge đụng
    #: thì story "xong" mà code kẹt trên nhánh story, và không ai biết
    #: (lỗi 42). Giờ `done` chỉ được ghi **sau** `merge.completed`.
    VERIFIED = "verified"
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
    # `verifying → done` thẳng chỉ dành cho chạy không cách ly (`--no-isolate`):
    # không có nhánh riêng thì không có bước merge. Có worktree thì `run.py`
    # đi qua `verified`.
    StoryStatus.VERIFYING: frozenset({
        StoryStatus.VERIFIED, StoryStatus.DONE, StoryStatus.FAILED, StoryStatus.BLOCKED,
    }),
    # merge xong → done; merge đụng và người đã sửa → về pending để merge lại
    StoryStatus.VERIFIED: frozenset({StoryStatus.DONE, StoryStatus.PENDING, StoryStatus.BLOCKED}),
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
        self._migrate_done_before_merge(stories)
        return SprintState(
            stories=stories,
            current_epic=raw.get("current_epic", ""),
            started_at=raw.get("started_at", _now()),
            updated_at=raw.get("updated_at", _now()),
        )

    def _migrate_done_before_merge(self, stories: dict[str, StoryRecord]) -> None:
        """Sổ cũ ghi `done` lúc qua cổng, trước merge. Story `done` mà nhật
        ký nói chưa merge là `verified` theo nghĩa mới — sửa lúc đọc, một
        lần, để mọi nơi hỏi trạng thái đều thấy cùng một sự thật."""
        from .journal import JournalStore  # tránh vòng import

        doi = False
        store = JournalStore(self.root)
        for sid, rec in stories.items():
            if rec.state is StoryStatus.DONE and store.read(sid).needs_merge:
                rec.status = StoryStatus.VERIFIED.value
                rec.updated_at = _now()
                doi = True
        if doi:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            payload["stories"] = {sid: asdict(r) for sid, r in stories.items()}
            self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")

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

    def reset_for_retry(self, story_id: str) -> bool:
        """Đưa story chưa xong về ``pending`` để chạy lại. True nếu có đổi.

        Chạy lại là lối vào hợp lệ, nhưng máy trạng thái không có cạnh nào
        đi thẳng từ ``failed`` hay từ ``running`` bỏ dở sang ``running``.
        Không mở lối này thì mọi lần chuyển của lượt chạy lại đều bị từ
        chối — và vì `_safe_transition` nuốt lỗi, story vẫn chạy, vẫn
        merge, mà bản ghi đứng nguyên ở lần thất bại cũ, chi phí lượt mới
        không vào sổ.

        ``running``/``verifying`` còn sót là của tiến trình đã chết: lượt
        chạy mới thu hồi chúng. ``done`` thì không đụng — xong là xong.
        """
        with self.transaction() as st:
            rec = st.stories.get(story_id)
            # `verified` là công việc **đã qua cổng**, đang chờ merge — không
            # phải lượt dở. Đưa nó về pending là chạy lại một story đã xong.
            if rec is None or rec.state in (StoryStatus.DONE, StoryStatus.VERIFIED):
                return False
            if rec.state is StoryStatus.PENDING:
                return False
            rec.status = StoryStatus.PENDING.value
            rec.blocked_reason = ""
            rec.updated_at = _now()
            return True

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
