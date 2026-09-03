"""Lập lịch chạy story: epic tuần tự, trong epic thì song song theo đợt.

Epic **luôn tuần tự** — epic sau thường dựa vào schema, API hay component mà
epic trước tạo ra, nên chạy chồng epic là mời gọi hỏng ngầm.

Trong một epic, story được chia thành các **đợt (wave)**. Story vào cùng đợt khi
thoả cả hai:

1. **Không phụ thuộc nhau** — mọi ``depends_on`` đã hoàn thành ở đợt trước.
2. **Không đụng phạm vi ghi** — hai story cùng sửa ``src/models/user.py`` mà
   chạy song song thì sẽ đè lên nhau.

Điều kiện 2 hay bị bỏ quên và là nguyên nhân hỏng khó lần nhất: đồ thị phụ
thuộc trông sạch, nhưng hai story vẫn ghi đè nhau vì cùng chạm một file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath


class CycleError(ValueError):
    """Đồ thị phụ thuộc có chu trình — không thể xếp lịch."""


class UnknownDependencyError(ValueError):
    """Story phụ thuộc vào một id không tồn tại."""


#: Trạng thái coi như đã xong, không cần chạy lại (phục vụ resume).
DONE_STATUSES = frozenset({"done", "skipped"})


@dataclass(frozen=True)
class Story:
    id: str
    epic_id: str = ""
    title: str = ""
    depends_on: tuple[str, ...] = ()
    write_scope: tuple[str, ...] = ()
    status: str = "pending"

    @property
    def is_done(self) -> bool:
        return self.status in DONE_STATUSES


def _norm(p: str) -> PurePosixPath:
    return PurePosixPath(p.strip().strip("/"))


def paths_overlap(a: str, b: str) -> bool:
    """True khi hai đường dẫn chạm cùng một vùng cây thư mục.

    So theo **đoạn đường dẫn**, không so tiền tố chuỗi: ``src/api`` và
    ``src/apidocs`` là hai vùng khác nhau, dù chuỗi này là tiền tố của chuỗi kia.
    """
    pa, pb = _norm(a), _norm(b)
    return pa == pb or pa in pb.parents or pb in pa.parents


def scopes_conflict(a: Story, b: Story) -> bool:
    """True khi hai story ghi vào vùng chồng nhau.

    Story không khai ``write_scope`` được coi là **chạm mọi thứ** — an toàn hơn
    là đoán rằng nó vô hại.
    """
    if not a.write_scope or not b.write_scope:
        return True
    return any(paths_overlap(x, y) for x in a.write_scope for y in b.write_scope)


def _validate(stories: list[Story]) -> dict[str, Story]:
    by_id: dict[str, Story] = {}
    for s in stories:
        if s.id in by_id:
            raise ValueError(f"story trùng id: {s.id}")
        by_id[s.id] = s

    for s in stories:
        for dep in s.depends_on:
            if dep not in by_id:
                raise UnknownDependencyError(f"{s.id} phụ thuộc {dep!r} không tồn tại")
    return by_id


def build_waves(stories: list[Story], *, max_parallel: int | None = None) -> list[list[Story]]:
    """Chia story của **một** epic thành các đợt chạy song song.

    Story đã ``done`` được coi là ràng buộc đã thoả và không xuất hiện trong
    kết quả — nhờ vậy chạy lại sau khi dừng giữa chừng sẽ tiếp đúng chỗ dở.

    ``max_parallel`` giới hạn số story mỗi đợt, để không vượt sức máy hoặc
    hạn mức gọi model.
    """
    if max_parallel is not None and max_parallel < 1:
        raise ValueError("max_parallel phải >= 1")

    by_id = _validate(stories)
    satisfied = {s.id for s in stories if s.is_done}
    remaining = [s for s in stories if not s.is_done]

    waves: list[list[Story]] = []
    while remaining:
        ready = [s for s in remaining if all(d in satisfied for d in s.depends_on)]
        if not ready:
            stuck = sorted(s.id for s in remaining)
            raise CycleError(f"phụ thuộc vòng hoặc bế tắc giữa: {', '.join(stuck)}")

        # Xếp greedy: nhận story nếu không đụng phạm vi ghi với story đã nhận.
        # Thứ tự id giữ cho kết quả ổn định giữa các lần chạy.
        wave: list[Story] = []
        for s in sorted(ready, key=lambda s: s.id):
            if max_parallel is not None and len(wave) >= max_parallel:
                break
            if any(scopes_conflict(s, picked) for picked in wave):
                continue  # để dành cho đợt sau
            wave.append(s)

        waves.append(wave)
        chosen = {s.id for s in wave}
        satisfied |= chosen
        remaining = [s for s in remaining if s.id not in chosen]

    return waves


@dataclass
class EpicPlan:
    """Lịch chạy của một epic."""

    epic_id: str
    waves: list[list[Story]] = field(default_factory=list)

    @property
    def story_count(self) -> int:
        return sum(len(w) for w in self.waves)

    @property
    def max_width(self) -> int:
        """Số story song song nhiều nhất trong một đợt."""
        return max((len(w) for w in self.waves), default=0)


def plan_epics(
    stories: list[Story],
    *,
    max_parallel: int | None = None,
    epic_order: list[str] | None = None,
) -> list[EpicPlan]:
    """Lập lịch toàn dự án: epic tuần tự, trong epic chia đợt song song.

    Phụ thuộc trỏ sang epic khác được coi là đã thoả khi epic đó nằm trước
    trong thứ tự chạy — đó chính là lý do epic phải tuần tự.
    """
    _validate(stories)

    groups: dict[str, list[Story]] = {}
    for s in stories:
        groups.setdefault(s.epic_id, []).append(s)

    order = epic_order or sorted(groups)
    unknown = [e for e in order if e not in groups]
    if unknown:
        raise ValueError(f"epic không có story: {', '.join(unknown)}")

    plans: list[EpicPlan] = []
    for epic_id in order:
        local = groups[epic_id]
        local_ids = {s.id for s in local}
        # Phụ thuộc ra ngoài epic đã do thứ tự epic bảo đảm; bỏ khỏi đồ thị
        # cục bộ để không bị coi là bế tắc.
        trimmed = [
            Story(
                id=s.id,
                epic_id=s.epic_id,
                title=s.title,
                depends_on=tuple(d for d in s.depends_on if d in local_ids),
                write_scope=s.write_scope,
                status=s.status,
            )
            for s in local
        ]
        plans.append(EpicPlan(epic_id, build_waves(trimmed, max_parallel=max_parallel)))
    return plans


def describe(plans: list[EpicPlan]) -> str:
    """Bản tóm tắt lịch chạy cho người đọc."""
    lines = []
    for p in plans:
        if not p.waves:
            lines.append(f"{p.epic_id}: (đã xong)")
            continue
        lines.append(f"{p.epic_id}: {p.story_count} story · {len(p.waves)} đợt · rộng nhất {p.max_width}")
        for i, wave in enumerate(p.waves, 1):
            lines.append(f"  đợt {i}: " + ", ".join(s.id for s in wave))
    return "\n".join(lines)
