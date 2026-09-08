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
from ..control.acceptance import ac_code
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
    verification_paths,
)
from ..control.scheduler import CycleError, UnknownDependencyError
from ..control.scheduler import Story as SchedStory
from ..control.scheduler import plan_epics

#: Kết quả cổng stories lần gần nhất — đầu vào cho prompt epics lần sau (P2-12).
GATE_MEMO = "stories.gate.json"

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
            return f"split stories: ✗ {self.error}"
        n_epics = len(self.plan.epics) if self.plan else 0
        lines = [f"split stories: {len(self.stories)} stories / {n_epics} epics"]
        if self.removed:
            lines.append(f"  removed {len(self.removed)} story file(s) no longer in epics.md")
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


def render_story(story: Story, prd: PRD | None, root: Path | None = None) -> str:
    """Sinh nội dung file story — bản hợp đồng agent đọc trước khi viết code."""
    out = [f"# {story.id}: {story.title}", ""]

    if story.as_a:
        out += [
            f"**As a** {story.as_a}",
            f"**I want** {story.i_want}",
            f"**so that** {story.so_that}",
            "",
        ]

    out += ["## Acceptance Criteria", ""]
    out += [f"{i}. [{ac_code(story.id, i)}] {ac}" for i, ac in enumerate(story.acceptance_criteria, 1)] or [
        "_(none — machine gate will block)_"
    ]
    out.append("")

    out += ["## Recorded Scope", ""]
    if story.write_scope:
        out += [f"- `{p}`" for p in story.write_scope]
        them = verification_paths(story, root.parent) if root is not None else []
        if them:
            out += ["", "Harness added because the story's verification contract requires them (error 21):"]
            out += [f"- `{p}`" for p in them]
        out += [
            "",
            "Guard blocks all writes outside this list. Needing to write elsewhere "
            "means the scope declaration is wrong — stop and report, do not work around it.",
        ]
    else:
        out.append("_(not declared — machine gate will block)_")
    out.append("")

    hop_dong = verification_contract(story)
    if hop_dong:
        out += [
            "## Definition of Done",
            "",
            "This story must pass the following verification types. Types not configured "
            "on the project are **not** counted as passing — they are gaps, and "
            "the gate will flag them.",
            "",
        ]
        out += [f"- `{k}`" for k in hop_dong]
        out.append("")

    if story.depends_on:
        out += ["## Dependencies", ""] + [f"- {d}" for d in story.depends_on] + [""]

    out += ["## Requirements", ""]
    if not story.covers:
        out.append("_(no FR mapped — machine gate will block)_")
    for fr_id in story.covers:
        req = prd.by_id(fr_id) if prd else None
        if req is None:
            out.append(f"### {fr_id}")
            out.append("_(not found in PRD)_")
            out.append("")
            continue
        out += [f"### {req.id}: {req.title}", ""]
        if req.description:
            out += [req.description.strip(), ""]
        if req.acceptance_criteria:
            out += ["Verifiable Consequences:", ""]
            out += [f"- {c}" for c in req.acceptance_criteria]
            out.append("")

    out += [
        "---",
        "",
        f"_Auto-generated from `epics.md`. Edits here will be lost on next split — "
        f"edit `epics.md` and run `aisef plan`._",
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
        res.error = "epics.md not found"
        return res

    res.plan = parse_epics_file(epics_md)
    stories = res.plan.stories()
    if not stories:
        res.error = "no readable stories found in epics.md"
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
        path.write_text(render_story(story, prd, root), encoding="utf-8")
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
    splits: dict[str, str] = {}
    for pf in check_stories_executable(stories, project=root.parent, config=config):
        for m in pf.story_defects:
            if m.capability == "size" and m.remedy:
                splits[pf.story_id] = m.remedy
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
                f"{pf.story_id} missing prerequisites to run: "
                + "; ".join(m.line() for m in pf.provisioning_gaps)
            )

    res.index_path = write_index(root, res, config)
    # Ghi lại để lần `plan` sau đưa vào prompt của bước epics: story bị
    # chặn vì quá lớn thì người chẻ phải là agent lập kế hoạch, và nó chỉ
    # chẻ đúng khi biết cổng đã nói gì (P2-12).
    # `splits`: cách chẻ **tất định** cho từng story quá cỡ (ADR-004 R5) —
    # nêu riêng ra để bước epics lần sau đọc thẳng, không phải bới câu chữ
    # trong dòng lỗi.
    (root / GATE_MEMO).write_text(
        json.dumps({"errors": res.gate.errors, "warnings": res.gate.warnings,
                    "splits": splits},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
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
        data["gate"]["errors"] = list(data["gate"]["errors"]) + [f"wave assignment: {wave_error}"]

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
            tag = f"  wave {i}" + (" (parallel)" if len(wave) > 1 else "")
            lines.append(tag)
            for sid in wave:
                s = by_id.get(sid, {})
                lines.append(
                    f"    {sid}  {s.get('title', '')}\n"
                    f"        covers: {', '.join(s.get('covers') or ['—'])}"
                    f"  ·  writes: {', '.join(s.get('write_scope') or ['—'])}"
                    f"  ·  {len(s.get('acceptance_criteria') or [])} criteria"
                )
        listed = {sid for w in waves.get(epic["id"], []) for sid in w}
        for sid in epic.get("stories", []):
            if sid not in listed:  # không xếp được lịch — vẫn phải thấy
                lines.append(f"    {sid}  {by_id.get(sid, {}).get('title', '')}  [not assigned to any wave]")

    gate = data.get("gate", {})
    lines.append("")
    lines.append("machine gate: " + ("PASS" if gate.get("passed") else "FAIL"))
    for e in gate.get("errors", []):
        lines.append(f"  ✗ {e}")
    for w in gate.get("warnings", []):
        lines.append(f"  ⚠️  {w}")
    return "\n".join(lines)
