"""Tách `epics.md` thành **mỗi story một file** + chỉ mục máy đọc được.

Một story là đơn vị công việc của một phiên agent (quyết định Đ1), nên nó
phải đứng được một mình: agent mở đúng một file và thấy đủ thứ cần —
tiêu chí chấp nhận, phạm vi được ghi, story phụ thuộc, và **nguyên văn yêu
cầu FR** mà nó phải thoả. Bắt agent tự lọc lại PRD 33KB mỗi lượt vừa tốn
tiền vừa để nó tự chọn phần nào là quan trọng.

Chỉ mục `stories.index.json` là bản hợp đồng cho phần điều phối: bộ xếp
sóng, cổng máy và bảng trạng thái đều đọc từ đây, không đọc markdown.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..config import DEFAULTS, Config
from ..control.approvals import STORIES_INDEX
from ..control.machine_gate import GateResult, check_stories
from ..control.preflight import (
    STORY_NOT_EXECUTABLE,
    check_stories_executable,
    verification_contract,
)
from ..control.normalize import (
    EpicPlan,
    PRD,
    Story,
    parse_epics_file,
    parse_prd_file,
)
from ..control.scheduler import CycleError, UnknownDependencyError
from ..control.scheduler import Story as SchedStory
from ..control.scheduler import plan_epics

STORIES_DIR = "stories"


@dataclass
class SplitResult:
    plan: EpicPlan | None = None
    files: list[Path] = field(default_factory=list)
    removed: list[Path] = field(default_factory=list)
    index_path: Path | None = None
    gate: GateResult | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        if self.error:
            return False
        return bool(self.gate and self.gate.passed)

    @property
    def stories(self) -> list[Story]:
        return self.plan.stories() if self.plan else []

    def summary(self) -> str:
        if self.error:
            return f"tách story: ✗ {self.error}"
        n_epics = len(self.plan.epics) if self.plan else 0
        lines = [f"tách story: {len(self.stories)} story / {n_epics} epic"]
        if self.removed:
            lines.append(f"  gỡ {len(self.removed)} file story không còn trong epics.md")
        if self.gate:
            lines.append(self.gate.summary())
        return "\n".join(lines)


def to_scheduler(stories: list[Story]) -> list[SchedStory]:
    """Chuyển sang mô hình bộ xếp lịch (chỉ giữ phần cần để xếp sóng)."""
    return [
        SchedStory(
            id=s.id,
            epic_id=s.epic_id,
            title=s.title,
            depends_on=tuple(s.depends_on),
            write_scope=tuple(s.write_scope),
        )
        for s in stories
    ]


def render_story(story: Story, prd: PRD | None) -> str:
    """Sinh nội dung file story — bản hợp đồng agent đọc trước khi viết code."""
    out = [f"# {story.id}: {story.title}", ""]

    if story.as_a:
        out += [
            f"**Là** {story.as_a}",
            f"**tôi muốn** {story.i_want}",
            f"**để** {story.so_that}",
            "",
        ]

    out += ["## Tiêu chí chấp nhận", ""]
    out += [f"{i}. {ac}" for i, ac in enumerate(story.acceptance_criteria, 1)] or [
        "_(chưa có — cổng máy sẽ chặn)_"
    ]
    out.append("")

    out += ["## Phạm vi được ghi", ""]
    if story.write_scope:
        out += [f"- `{p}`" for p in story.write_scope]
        out += [
            "",
            "Guard chặn mọi thao tác ghi ngoài danh sách này. Cần ghi chỗ khác "
            "nghĩa là phạm vi khai sai — dừng lại và báo, đừng lách.",
        ]
    else:
        out.append("_(chưa khai — cổng máy sẽ chặn)_")
    out.append("")

    hop_dong = verification_contract(story)
    if hop_dong:
        out += [
            "## Xong nghĩa là gì",
            "",
            "Story này phải qua các loại kiểm định sau. Loại chưa cấu hình "
            "trên dự án **không** được tính là đạt — nó là chỗ trống, và "
            "cổng sẽ nói ra.",
            "",
        ]
        out += [f"- `{k}`" for k in hop_dong]
        out.append("")

    if story.depends_on:
        out += ["## Phụ thuộc", ""] + [f"- {d}" for d in story.depends_on] + [""]

    out += ["## Yêu cầu phải thoả", ""]
    if not story.covers:
        out.append("_(chưa ánh xạ FR nào — cổng máy sẽ chặn)_")
    for fr_id in story.covers:
        req = prd.by_id(fr_id) if prd else None
        if req is None:
            out.append(f"### {fr_id}")
            out.append("_(không tìm thấy trong PRD)_")
            out.append("")
            continue
        out += [f"### {req.id}: {req.title}", ""]
        if req.description:
            out += [req.description.strip(), ""]
        if req.acceptance_criteria:
            out += ["Hệ quả kiểm chứng được:", ""]
            out += [f"- {c}" for c in req.acceptance_criteria]
            out.append("")

    out += [
        "---",
        "",
        f"_Sinh tự động từ `epics.md`. Sửa ở đây sẽ mất khi tách lại — "
        f"sửa `epics.md` rồi chạy `aisdlc plan`._",
        "",
    ]
    return "\n".join(out)


def story_file(root: Path, story: Story) -> Path:
    return root / STORIES_DIR / story.epic_id / f"{story.id}.md"


def _prune(root: Path, keep: set[Path]) -> list[Path]:
    """Xoá file story không còn trong `epics.md`.

    Bỏ sót thì một story đã bị gỡ vẫn nằm đó và sẽ được nhặt lên như việc
    thật ở vòng sau.
    """
    base = root / STORIES_DIR
    if not base.is_dir():
        return []
    removed = []
    for p in sorted(base.rglob("STORY-*.md")):
        if p not in keep:
            p.unlink()
            removed.append(p)
    for d in sorted(base.glob("EPIC-*")):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    return removed


def split(
    artifact_root: Path | str,
    *,
    config: Config | None = None,
) -> SplitResult:
    """Đọc `epics.md`, ghi mỗi story một file và chỉ mục, rồi chạy cổng máy."""
    root = Path(artifact_root)
    res = SplitResult()

    epics_md = root / "epics.md"
    if not epics_md.is_file():
        res.error = "chưa có epics.md"
        return res

    res.plan = parse_epics_file(epics_md)
    stories = res.plan.stories()
    if not stories:
        res.error = "epics.md không có story nào đọc được"
        return res

    prd_path = root / "prd.md"
    prd = parse_prd_file(prd_path) if prd_path.is_file() else None

    written: set[Path] = set()
    # Chốt hợp đồng kiểm định trước khi ghi: chỉ mục và tệp story phải
    # nói cùng một thứ, và phần điều phối đọc chỉ mục.
    for story in stories:
        if not story.verification_contract:
            story.verification_contract = verification_contract(story)

    for story in stories:
        path = story_file(root, story)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_story(story, prd), encoding="utf-8")
        written.add(path)
    res.files = sorted(written)
    res.removed = _prune(root, written)

    res.gate = check_stories(
        to_scheduler(stories),
        prd,
        config=config,
        story_fr_map={s.id: s.covers for s in stories},
        story_ac_count={s.id: len(s.acceptance_criteria) for s in stories},
    )

    # Story chạy được không — tính bằng code, trước khi tiêu đồng nào.
    # Chấm ở đây chứ không trong `check_stories`: phép kiểm cần tiêu chí
    # chấp nhận và danh sách màn hình, mà tầng lập lịch không mang theo.
    for pf in check_stories_executable(stories, project=root.parent, config=config):
        if pf.story_defects:
            res.gate.errors.append(
                f"{STORY_NOT_EXECUTABLE} {pf.story_id}: "
                + "; ".join(m.line() for m in pf.story_defects)
            )
        if pf.provisioning_gaps:
            # Chưa chặn: pha dựng mockup và việc cấu hình công cụ đều diễn
            # ra **sau** cổng này. Chặn ở đây là bắt người sửa thứ chưa tới
            # lượt. Cổng `readiness` và bước ngay trước khi gọi model mới
            # chặn thật.
            res.gate.warnings.append(
                f"{pf.story_id} còn thiếu để chạy được: "
                + "; ".join(m.line() for m in pf.provisioning_gaps)
            )

    res.index_path = write_index(root, res, config)
    return res


def write_index(root: Path, res: SplitResult, config: Config | None = None) -> Path:
    """Ghi `stories.index.json` — hợp đồng cho phần điều phối.

    Kèm luôn các sóng chạy song song đã tính sẵn: đây là quyết định máy tính
    được chắc chắn từ phụ thuộc và ``write_scope``, nên chốt một lần ở đây
    thay vì để mỗi nơi tính lại một kiểu.
    """
    sched = to_scheduler(res.stories)
    max_parallel = (config or Config(dict(DEFAULTS)))["run.max_parallel"]
    try:
        waves = {
            ep.epic_id: [[s.id for s in wave] for wave in ep.waves]
            for ep in plan_epics(sched, max_parallel=max_parallel)
        }
        wave_error = ""
    except (CycleError, UnknownDependencyError, ValueError) as e:
        # Đồ thị hỏng — cổng máy đã ghi lỗi; ghi thêm vào chỉ mục để nơi
        # đọc chỉ mục không phải đoán vì sao không có sóng nào.
        waves, wave_error = {}, str(e)

    data = {
        "source": "epics.md",
        "epics": [
            {
                "id": e.id,
                "title": e.title,
                "goal": e.goal,
                "stories": [s.id for s in e.stories],
            }
            for e in (res.plan.epics if res.plan else [])
        ],
        "stories": [s.as_dict() | {"file": str(story_file(root, s).relative_to(root))}
                    for s in res.stories],
        "waves": waves,
        "gate": {
            "passed": bool(res.gate and res.gate.passed),
            "errors": res.gate.errors if res.gate else [],
            "warnings": res.gate.warnings if res.gate else [],
        },
    }
    if wave_error:
        data["gate"]["errors"] = list(data["gate"]["errors"]) + [f"xếp sóng: {wave_error}"]

    path = root / STORIES_INDEX
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def describe_index(data: dict) -> str:
    """Tóm tắt chỉ mục cho người duyệt.

    Cổng story tồn tại để một người thật xem lại cách chia việc. Ném 350
    dòng JSON vào mặt họ thì cổng chỉ còn là thủ tục — thứ cần nhìn là:
    story nào, phủ yêu cầu nào, ghi vào đâu, và chạy song song với ai.
    """
    lines = []
    by_id = {s["id"]: s for s in data.get("stories", [])}
    waves = data.get("waves", {})

    for epic in data.get("epics", []):
        lines.append(f"\n{epic['id']}: {epic['title']}")
        for i, wave in enumerate(waves.get(epic["id"], []), 1):
            tag = f"  đợt {i}" + (" (song song)" if len(wave) > 1 else "")
            lines.append(tag)
            for sid in wave:
                s = by_id.get(sid, {})
                lines.append(
                    f"    {sid}  {s.get('title', '')}\n"
                    f"        phủ: {', '.join(s.get('covers') or ['—'])}"
                    f"  ·  ghi: {', '.join(s.get('write_scope') or ['—'])}"
                    f"  ·  {len(s.get('acceptance_criteria') or [])} tiêu chí"
                )
        listed = {sid for w in waves.get(epic["id"], []) for sid in w}
        for sid in epic.get("stories", []):
            if sid not in listed:  # không xếp được lịch — vẫn phải thấy
                lines.append(f"    {sid}  {by_id.get(sid, {}).get('title', '')}  [chưa xếp được đợt]")

    gate = data.get("gate", {})
    lines.append("")
    lines.append("cổng máy: " + ("ĐẠT" if gate.get("passed") else "KHÔNG ĐẠT"))
    for e in gate.get("errors", []):
        lines.append(f"  ✗ {e}")
    for w in gate.get("warnings", []):
        lines.append(f"  ⚠️  {w}")
    return "\n".join(lines)
