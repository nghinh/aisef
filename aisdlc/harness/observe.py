"""Quan sát — sự kiện có cấu trúc, chi phí và độ trễ cho từng story.

Không có quan sát thì không có cách nào biết agent đang làm tốt hay đang
lặng lẽ trôi. Nhưng "log" thôi thì chưa đủ: thứ cần là **bằng chứng máy
đọc được**, vì hai chỗ khác nhau dựa vào nó:

* cổng story hỏi "test đã xanh chưa, lint sạch chưa, mockup khớp chưa";
* guard `completion` hỏi "có lần chạy test nào **sau** lần sửa file cuối
  cùng không" — đó là cách chặn agent tuyên bố xong khi chưa chạy lại test.

Vì thế mỗi sự kiện có ``seq`` tăng dần và ``at`` (mốc thời gian đơn điệu
của tiến trình). So thứ tự bằng ``seq``, không bằng đồng hồ treo tường:
file bằng chứng đi qua git giữa các máy.

Một file một story, ghi nối thêm và nguyên tử: nhiều tiến trình (agent
chạy tool, guard chạy trong hook) cùng ghi vào một story là chuyện bình
thường khi chạy song song.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

EVIDENCE_DIR = "evidence"

#: Loại sự kiện. Danh sách đóng để nơi đọc không phải đoán.
TOOL_RUN = "tool_run"          # chạy test/lint/sast/screenshot…
FILE_CHANGE = "file_change"    # agent ghi file
AGENT_RUN = "agent_run"        # một lượt gọi model
GUARD_BLOCK = "guard_block"    # guard chặn một thao tác
MOCKUP_MAP = "mockup_map"      # đối chiếu màn hình thật với mockup
NOTE = "note"


@dataclass
class Event:
    kind: str
    name: str = ""
    ok: bool = True
    seq: int = 0
    at: float = 0.0
    duration_ms: int = 0
    cost_usd: float = 0.0
    tokens: dict = field(default_factory=dict)
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Evidence:
    """Toàn bộ sự kiện của một story, đã đọc lên."""

    story_id: str
    events: list[Event] = field(default_factory=list)

    def of(self, kind: str, name: str = "") -> list[Event]:
        return [
            e for e in self.events
            if e.kind == kind and (not name or e.name == name)
        ]

    def last(self, kind: str, name: str = "") -> Event | None:
        found = self.of(kind, name)
        return found[-1] if found else None

    @property
    def total_cost_usd(self) -> float:
        return sum(e.cost_usd for e in self.events)

    @property
    def total_duration_ms(self) -> int:
        return sum(e.duration_ms for e in self.events)

    @property
    def guard_blocks(self) -> list[Event]:
        """Những lần guard chặn, do **chính guard** ghi — không phụ thuộc
        client có phát luồng sự kiện hay không."""
        return self.of(GUARD_BLOCK)

    def tests_green(self) -> bool:
        """Lần chạy test gần nhất có xanh không."""
        last = self.last(TOOL_RUN, "test")
        return bool(last and last.ok)

    def stale_since_last_test(self) -> list[str]:
        """File đã sửa **sau** lần chạy test gần nhất.

        Đây là câu hỏi mà guard `completion` cần: test xanh từ mười phút
        trước không nói gì về đoạn code vừa viết xong.
        """
        last = self.last(TOOL_RUN, "test")
        after = 0 if last is None else last.seq
        touched: list[str] = []
        for e in self.of(FILE_CHANGE):
            if e.seq > after:
                path = str(e.detail.get("path") or e.name)
                if path and path not in touched:
                    touched.append(path)
        return touched

    def summary(self) -> str:
        by_kind: dict[str, int] = {}
        for e in self.events:
            by_kind[e.kind] = by_kind.get(e.kind, 0) + 1
        parts = [f"{k}={v}" for k, v in sorted(by_kind.items())]
        if self.total_cost_usd:
            parts.append(f"${self.total_cost_usd:.2f}")
        return f"{self.story_id}: " + " · ".join(parts) if parts else f"{self.story_id}: (trống)"


class EvidenceStore:
    """Đọc/ghi ``evidence/{story}.jsonl``."""

    def __init__(self, artifact_root: Path | str):
        self.root = Path(artifact_root) / EVIDENCE_DIR

    def path(self, story_id: str) -> Path:
        return self.root / f"{story_id}.jsonl"

    def record(self, story_id: str, event: Event) -> Event:
        """Ghi nối thêm một sự kiện. `seq` do file quyết định, không do
        người gọi — hai tiến trình cùng ghi vẫn ra thứ tự nhất quán."""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path(story_id)

        event.at = event.at or time.time()
        # Mở chế độ nối thêm rồi ghi một dòng: ghi một dòng ngắn dưới
        # PIPE_BUF là nguyên tử trên POSIX, nên không cần khoá riêng.
        with path.open("a", encoding="utf-8") as fh:
            event.seq = self._next_seq(path)
            fh.write(json.dumps(event.as_dict(), ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return event

    def _next_seq(self, path: Path) -> int:
        highest = 0
        if path.is_file():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    highest = max(highest, int(json.loads(line).get("seq") or 0))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
        return highest + 1

    def read(self, story_id: str) -> Evidence:
        ev = Evidence(story_id=story_id)
        path = self.path(story_id)
        if not path.is_file():
            return ev
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue  # một dòng hỏng không được làm mất cả tệp bằng chứng
            if not isinstance(data, dict):
                continue
            ev.events.append(
                Event(
                    kind=str(data.get("kind", "")),
                    name=str(data.get("name", "")),
                    ok=bool(data.get("ok", True)),
                    seq=int(data.get("seq") or 0),
                    at=float(data.get("at") or 0.0),
                    duration_ms=int(data.get("duration_ms") or 0),
                    cost_usd=float(data.get("cost_usd") or 0.0),
                    tokens=data.get("tokens") or {},
                    detail=data.get("detail") or {},
                )
            )
        ev.events.sort(key=lambda e: e.seq)
        return ev

    def stories(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.stem for p in self.root.glob("*.jsonl"))

    # ------------------------------------------------------------ tiện ích

    def tool_run(
        self,
        story_id: str,
        name: str,
        *,
        ok: bool,
        duration_ms: int = 0,
        detail: dict | None = None,
    ) -> Event:
        return self.record(
            story_id,
            Event(kind=TOOL_RUN, name=name, ok=ok, duration_ms=duration_ms,
                  detail=detail or {}),
        )

    def file_change(self, story_id: str, path: str, *, detail: dict | None = None) -> Event:
        return self.record(
            story_id,
            Event(kind=FILE_CHANGE, name=Path(path).name,
                  detail={"path": path, **(detail or {})}),
        )

    def agent_run(self, story_id: str, result, *, name: str = "", prompt_chars: int = 0) -> Event:
        """Ghi lại một lượt gọi model từ `RunResult` — chi phí và độ trễ
        lấy từ luồng client, không tự đoán."""
        return self.record(
            story_id,
            Event(
                kind=AGENT_RUN,
                name=name or "story",
                ok=result.ok,
                duration_ms=result.duration_ms,
                cost_usd=result.cost_usd,
                tokens={
                    "input": result.input_tokens,
                    "output": result.output_tokens,
                    "cache_creation": result.cache_creation_tokens,
                    "cache_read": result.cache_read_tokens,
                },
                detail={
                    "session_id": result.session_id,
                    "turns": result.num_turns,
                    # Kích thước ngữ cảnh nạp — đo thật, thay cho knob
                    # `story.max_context_tokens` chưa từng có mã đọc.
                    "prompt_chars": prompt_chars,
                    "guard_blocked": result.guard_blocked,
                    # Cờ không nói được guard nào chặn vì gì. Thiếu chỗ
                    # này thì lần sau lại phải đi mò nhật ký phiên.
                    "guard_messages": list(result.guard_messages)[:5],
                    "permission_limited": result.permission_limited,
                    "error": result.error,
                },
            ),
        )
