"""Điều phối cả đợt: epic tuần tự, trong epic chạy song song theo đợt.

Ba quyết định định hình module này:

* **Epic tuần tự** — story epic sau thường dựa trên epic trước; chạy chéo
  epic thì merge cuối đợt sẽ đụng nhau ở chỗ chưa ai lường.
* **Trong epic, story rời nhau chạy song song** (đợt/wave). Rời nhau nghĩa
  là không phụ thuộc **và** phạm vi ghi không giao — cả hai điều kiện do
  bộ xếp lịch tính sẵn và ghi vào ``stories.index.json``.
* **Mỗi story một worktree, merge tuần tự cuối đợt.** Conflict lúc merge
  không phải chuyện "gỡ cho xong": nó là **bằng chứng ``write_scope`` khai
  sai**, nên dừng lại và báo, không tự hoà giải.

Chạy lại thì tiếp từ chỗ dở: trạng thái nằm trên đĩa, story đã xong không
chạy lại.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from ..clients.base import ClientAdapter
from ..config import Config
from ..control.approvals import STORIES_INDEX
from ..control.design_contract import load as load_contract
from ..control.normalize import Story, parse_architecture_file
from ..control.state import StateStore, StoryStatus, TransitionError
from ..control.worktree import GitError, WorktreeManager
from ..harness.prompts import load_catalog
from .implement import StoryOutcome, implement_story
from .plan import ARTIFACT_ROOT


@dataclass
class Plan:
    """Kế hoạch đọc từ `stories.index.json`."""

    stories: dict[str, Story] = field(default_factory=dict)
    waves: dict[str, list[list[str]]] = field(default_factory=dict)
    epic_order: list[str] = field(default_factory=list)
    error: str = ""

    def epic_of(self, story_id: str) -> str:
        story = self.stories.get(story_id)
        return story.epic_id if story else ""


def load_plan(artifact_root: Path | str) -> Plan:
    path = Path(artifact_root) / STORIES_INDEX
    if not path.is_file():
        return Plan(error=f"chưa có {STORIES_INDEX} — chạy `aisdlc plan` trước")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return Plan(error=f"{STORIES_INDEX} hỏng: {e}")

    plan = Plan(waves=data.get("waves") or {})
    for raw in data.get("stories", []):
        plan.stories[raw["id"]] = Story(
            id=raw["id"],
            epic_id=raw.get("epic_id", ""),
            title=raw.get("title", ""),
            acceptance_criteria=raw.get("acceptance_criteria", []),
            covers=raw.get("covers", []),
            write_scope=raw.get("write_scope", []),
            depends_on=raw.get("depends_on", []),
            screens=raw.get("screens", []),
        )
    plan.epic_order = [e["id"] for e in data.get("epics", [])]
    if not plan.waves:
        plan.error = plan.error or "chỉ mục không có đợt chạy nào (đồ thị phụ thuộc hỏng?)"
    return plan


@dataclass
class WaveReport:
    epic_id: str
    index: int
    outcomes: list[StoryOutcome] = field(default_factory=list)
    merge_conflicts: dict[str, list[str]] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(o.done for o in self.outcomes) and not self.merge_conflicts


@dataclass
class RunReport:
    waves: list[WaveReport] = field(default_factory=list)
    stopped_at: str = ""
    error: str = ""

    @property
    def outcomes(self) -> list[StoryOutcome]:
        return [o for w in self.waves for o in w.outcomes]

    @property
    def cost_usd(self) -> float:
        return sum(o.cost_usd for o in self.outcomes)

    @property
    def ok(self) -> bool:
        return not self.error and not self.stopped_at and all(w.ok for w in self.waves)

    def summary(self) -> str:
        if self.error:
            return f"chạy đợt: ✗ {self.error}"
        lines = []
        for w in self.waves:
            head = f"{w.epic_id} · đợt {w.index}"
            if len(w.outcomes) > 1:
                head += f" ({len(w.outcomes)} story song song)"
            lines.append(head)
            lines += [o.summary() for o in w.outcomes]
            for sid in w.skipped:
                lines.append(f"  ○ {sid}: đã xong từ trước, bỏ qua")
            for sid, files in w.merge_conflicts.items():
                lines.append(
                    f"  ✗ {sid}: merge đụng {', '.join(files[:5])} — đây là bằng "
                    f"chứng write_scope khai sai, không phải chuyện gỡ cho xong"
                )
        if self.stopped_at:
            lines.append(f"\n⏸ dừng ở {self.stopped_at}")
        if self.cost_usd:
            lines.append(f"chi phí: ${self.cost_usd:.2f}")
        return "\n".join(lines)


def run_epic(
    epic_id: str,
    plan: Plan,
    *,
    project: Path,
    client: ClientAdapter,
    config: Config,
    state: StateStore,
    worktrees: WorktreeManager | None,
    artifact_root: Path,
    report: RunReport,
) -> bool:
    """Chạy hết một epic. False nghĩa là phải dừng cả đợt."""
    architecture = None
    arch_file = artifact_root / "architecture.md"
    if arch_file.is_file():
        architecture = parse_architecture_file(arch_file)
    contract = load_contract(artifact_root)
    catalog = load_catalog()
    state.set_current_epic(epic_id)

    for index, wave_ids in enumerate(plan.waves.get(epic_id, []), 1):
        wave = WaveReport(epic_id=epic_id, index=index)
        report.waves.append(wave)

        todo = []
        for sid in wave_ids:
            state.register(sid, epic_id, wave=index)
            if state.load().stories[sid].state is StoryStatus.DONE:
                wave.skipped.append(sid)  # chạy lại thì tiếp từ chỗ dở
            else:
                todo.append(sid)

        if todo:
            _run_wave(
                todo, plan,
                project=project, client=client, config=config, state=state,
                worktrees=worktrees, artifact_root=artifact_root,
                architecture=architecture, contract=contract, catalog=catalog,
                wave=wave,
            )

        if not all(o.done for o in wave.outcomes):
            report.stopped_at = f"{epic_id} · đợt {index}"
            return False

        if worktrees is not None:
            done_ids = [o.story_id for o in wave.outcomes if o.done]
            for sid in done_ids:
                story = plan.stories.get(sid)
                worktrees.commit_story(
                    sid,
                    f"{sid}: {story.title if story else ''}".strip(": "),
                    paths=list(story.write_scope) if story else None,
                )
            for result in worktrees.merge_wave(done_ids):
                if not result.merged:
                    wave.merge_conflicts[result.story_id] = result.conflicts
                    report.stopped_at = f"{epic_id} · đợt {index} (merge)"
                    return False
            for sid in done_ids:
                worktrees.remove(sid)
    return True


def _run_wave(
    story_ids: list[str],
    plan: Plan,
    *,
    project: Path,
    client: ClientAdapter,
    config: Config,
    state: StateStore,
    worktrees: WorktreeManager | None,
    artifact_root: Path,
    architecture,
    contract,
    catalog,
    wave: WaveReport,
) -> None:
    def one(story_id: str) -> StoryOutcome:
        story = plan.stories[story_id]
        workdir = project
        if worktrees is not None:
            workdir = worktrees.create(story_id).path

        _safe_transition(state, story_id, StoryStatus.RUNNING)
        outcome = implement_story(
            story,
            project=project,
            workdir=workdir,
            artifact_root=artifact_root,
            client=client,
            config=config,
            catalog=catalog,
            architecture=architecture,
            contract=contract,
        )
        _safe_transition(state, story_id, StoryStatus.VERIFYING, cost=outcome.cost_usd)
        _safe_transition(
            state,
            story_id,
            StoryStatus.DONE if outcome.done else StoryStatus.FAILED,
            reason=outcome.blocked_reason,
        )
        return outcome

    workers = max(1, min(config["run.max_parallel"], len(story_ids)))
    if workers == 1:
        wave.outcomes = [one(sid) for sid in story_ids]
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        wave.outcomes = list(pool.map(one, story_ids))


def _safe_transition(state: StateStore, story_id: str, to: StoryStatus, **kw) -> None:
    """Ghi trạng thái, nhưng không để lỗi máy trạng thái làm hỏng cả đợt.

    Bản ghi trạng thái là để người đọc và để chạy lại; một bước nhảy không
    hợp lệ đáng ghi vào log, không đáng làm mất công việc đã làm.
    """
    try:
        state.transition(story_id, to, cost_usd=kw.get("cost", 0.0), reason=kw.get("reason", ""))
    except TransitionError:
        pass


def run_sprint(
    project: Path | str,
    client: ClientAdapter,
    *,
    config: Config | None = None,
    only_epic: str = "",
    sequential: bool = False,
    isolate: bool = True,
) -> RunReport:
    """Chạy cả sprint: epic tuần tự, trong epic chạy theo đợt."""
    project = Path(project)
    artifact_root = project / ARTIFACT_ROOT
    cfg = config or Config.load(project)
    if sequential:
        cfg = Config({**cfg.values, "run.max_parallel": 1})

    report = RunReport()
    plan = load_plan(artifact_root)
    if plan.error:
        report.error = plan.error
        return report

    worktrees = None
    if isolate:
        try:
            worktrees = WorktreeManager(project)
        except GitError as e:
            report.error = f"{e} — cách ly story cần kho git; dùng --no-isolate nếu cố ý"
            return report

    state = StateStore(artifact_root)
    epics = [only_epic] if only_epic else (plan.epic_order or sorted(plan.waves))
    unknown = [e for e in epics if e not in plan.waves]
    if unknown:
        report.error = f"epic không có trong kế hoạch: {', '.join(unknown)}"
        return report

    for epic_id in epics:
        if not run_epic(
            epic_id, plan,
            project=project, client=client, config=cfg, state=state,
            worktrees=worktrees, artifact_root=artifact_root, report=report,
        ):
            break
    return report
