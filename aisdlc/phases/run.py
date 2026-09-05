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
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from ..clients.base import ClientAdapter
from ..config import Config
from ..control.approvals import STORIES_INDEX
from ..control.design_contract import load as load_contract
from ..control.journal import (
    Entry as JEntry,
    JournalStore,
    StoryRunTransaction,
    reconcile_all,
)
from ..control.normalize import Story, parse_architecture_file
from ..control.preflight import STORY_NOT_EXECUTABLE, check_story, screen_owners
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
            verification_contract=raw.get("verification_contract", []),
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
    #: Story được dọn dấu vết lượt chạy trước. In ra, không nuốt: người
    #: đọc cần biết harness vừa sửa trạng thái của story nào và vì sao.
    reconciled: list = field(default_factory=list)

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
        for r in self.reconciled:
            lines.append(f"↺ {r.line()}")
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
        can_merge_lai = []
        for sid in wave_ids:
            state.register(sid, epic_id, wave=index)
            trang_thai = state.load().stories[sid].state
            if trang_thai is StoryStatus.DONE:
                wave.skipped.append(sid)  # chạy lại thì tiếp từ chỗ dở
            elif trang_thai is StoryStatus.VERIFIED:
                # Qua cổng rồi, chưa lên nhánh chính (merge đụng ở lượt trước,
                # người đã sửa). Chỉ merge lại — công việc đã nằm trên nhánh
                # story, và worktree có thể đã bị dọn.
                if worktrees is not None:
                    can_merge_lai.append(sid)
                else:
                    wave.skipped.append(sid)
            else:
                # Về `pending` trước: không có cạnh nào đi thẳng từ
                # `failed`, hay từ `running` mà tiến trình đã chết, sang
                # `running`. Bỏ bước này thì lượt chạy lại làm hết việc
                # nhưng mọi lần ghi trạng thái đều bị từ chối và nuốt.
                state.reset_for_retry(sid)
                todo.append(sid)

        if todo:
            _run_wave(
                todo, plan,
                project=project, client=client, config=config, state=state,
                worktrees=worktrees, artifact_root=artifact_root,
                architecture=architecture, contract=contract, catalog=catalog,
                wave=wave,
            )

        # Gỡ worktree của story **trượt** trước khi thoát. Chúng nằm
        # trong cây dự án, và `.gitignore` chỉ che được git: vitest,
        # eslint, tsc đều quét thẳng thư mục và nhặt phải test của story
        # đang dở. Đo trên e9, cổng trước triển khai báo "unit đỏ" vì
        # đúng chuyện này — test không đỏ, nó đọc nhầm cây.
        #
        # Chốt phần còn dở vào nhánh trước khi gỡ: nhánh giữ công việc,
        # thư mục thì không cần giữ — `create` dựng lại được từ nhánh khi
        # cần xem lại.
        if worktrees is not None:
            for o in wave.outcomes:
                if o.done:
                    continue
                story = plan.stories.get(o.story_id)
                worktrees.commit_story(
                    o.story_id,
                    f"{o.story_id}: dở dang, chốt để không mất",
                    paths=list(story.write_scope) if story else None,
                )
                worktrees.remove(o.story_id, delete_branch=False)

        if not all(o.done for o in wave.outcomes):
            report.stopped_at = f"{epic_id} · đợt {index}"
            return False

        if worktrees is not None:
            journal = JournalStore(artifact_root)
            done_ids = [o.story_id for o in wave.outcomes if o.done]
            # Story đã xong từ lượt trước nhưng chưa merge: chỉ merge lại,
            # **không** commit lại — công việc của nó đã nằm trên nhánh
            # story rồi, và worktree có thể đã bị dọn.
            # Ứng viên đã được đóng băng ngay sau phiên developer (ADR-004
            # R1) nên ở đây thường không còn gì để chốt. Vẫn gọi: phần dư
            # nào sót lại phải sang được nhánh chính, và bước này không ghi
            # nhật ký nữa — `candidate.frozen` mới là mốc chốt bản.
            for sid in done_ids:
                story = plan.stories.get(sid)
                worktrees.commit_story(
                    sid,
                    f"{sid}: {story.title if story else ''}".strip(": "),
                    paths=list(story.write_scope) if story else None,
                )
            for result in worktrees.merge_wave(can_merge_lai + done_ids):
                if not result.merged:
                    wave.merge_conflicts[result.story_id] = result.conflicts
                    report.stopped_at = f"{epic_id} · đợt {index} (merge)"
                    return False
                # Mốc không quay lại được: công việc đã ra ngoài tầm giao
                # dịch. Ghi **ngay** sau khi merge, trước cả việc dọn
                # worktree — chết giữa hai bước này thì lần chạy sau phải
                # đọc được rằng đã merge, không thì nó chạy lại một story
                # đã xong và chỉ thấy diff rỗng.
                n = journal.read(result.story_id).attempt_no
                journal.record(result.story_id,
                               JEntry(step="merge.completed", attempt=n))
                # `done` chỉ được ghi **sau** dòng trên. Bất biến của G12:
                # trong `sprint-status.json`, `done` không bao giờ đứng trước
                # `merge.completed` của nhật ký.
                _safe_transition(state, result.story_id, StoryStatus.DONE)
            for sid in can_merge_lai + done_ids:
                worktrees.remove(sid)
                n = journal.read(sid).attempt_no
                journal.record(sid, JEntry(step="attempt.committed", attempt=n))

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

        # Chặn **trước** khi mở worktree và gọi model. Cổng `stories` đã
        # chấm cùng phép kiểm này, nhưng cấu hình dự án đổi được sau khi
        # cổng ấy duyệt — và một story không chạy được thì mọi đồng tiêu
        # cho nó là tiêu vào chỗ không thể qua.
        pf = check_story(story, project=project, config=config,
                         owned=screen_owners(plan.stories.values()))
        if not pf.executable:
            out = StoryOutcome(story_id=story_id)
            out.blocked_reason = (
                f"{STORY_NOT_EXECUTABLE}: "
                + "; ".join(m.line() for m in pf.missing)
            )
            _safe_transition(state, story_id, StoryStatus.BLOCKED,
                             reason=out.blocked_reason)
            return out

        # Một lượt chạy là **một giao dịch**. Nhật ký nằm trên đĩa nên
        # nó sống sót qua cả tiến trình bị giết — đó mới là lúc cần nó.
        with StoryRunTransaction(story_id, artifact_root=artifact_root) as tx:
            workdir = project
            if worktrees is not None:
                workdir = worktrees.create(story_id).path
                tx.record("worktree.created", path=str(workdir),
                          undo={"worktree.remove": story_id})

            _safe_transition(state, story_id, StoryStatus.RUNNING)
            tx.record("status.running", undo={"status.reset": "pending"})

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
            tx.record(
                "verification.completed",
                ok=outcome.done,
                attempts=outcome.quality_attempts,
                cost_usd=round(outcome.cost_usd, 4),
            )
            tx.record("review.completed", blocked=[
                f for a in outcome.attempts for f in a.review_findings
            ][:5])

            _safe_transition(state, story_id, StoryStatus.VERIFYING,
                             cost=outcome.cost_usd, attempts=outcome.quality_attempts)
            # Qua cổng ≠ xong. Có worktree thì còn nợ merge — `verified`,
            # và `done` chỉ ghi ở cuối đợt sau `merge.completed`. Không cách
            # ly thì không có bước merge: `done` ngay.
            if outcome.done:
                qua_cong = StoryStatus.DONE if worktrees is None else StoryStatus.VERIFIED
            else:
                qua_cong = StoryStatus.FAILED
            _safe_transition(state, story_id, qua_cong, reason=outcome.blocked_reason)
            # Story trượt: giao dịch đóng ngay, không nợ gì. Story xong
            # còn nợ commit và merge — đóng ở cuối đợt.
            if not outcome.done:
                tx.commit()
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
        state.transition(story_id, to, cost_usd=kw.get("cost", 0.0), reason=kw.get("reason", ""),
                         attempts=kw.get("attempts", 0))
    except TransitionError as e:
        # Nói ra. Nuốt im lặng đã che một lỗi thật: story chạy lại xong,
        # merge xong, mà bản ghi vẫn đứng ở lần thất bại cũ.
        print(f"trạng thái {story_id}: {e}", file=sys.stderr)


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

    # Dọn dấu vết lượt chạy trước bị giết, **trước** khi làm gì khác.
    # Không có bước này thì story kẹt `running` vĩnh viễn và không lệnh
    # nào gỡ ra được; còn story đã merge mà sổ ghi `failed` sẽ bị chạy
    # lại trên một worktree rẽ từ nhánh đã chứa sẵn công việc — diff rỗng,
    # không bao giờ qua được.
    report.reconciled = reconcile_all(
        artifact_root=artifact_root, state=state, worktrees=worktrees
    )

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
