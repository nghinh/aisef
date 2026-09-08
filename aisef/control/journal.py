"""Một lượt chạy story là **một giao dịch**, không phải bảy lần ghi rời.

Một lượt chạy đụng tới bảy kho trạng thái: worktree, nhánh git, bản ghi
sprint, tệp bằng chứng, trạng thái lượt thử, tiến trình con, và sổ sách
commit/merge. Chúng phải nhất quán với nhau, nhưng không có gì buộc
chúng nhất quán — nên khi một lượt chạy chết giữa chừng, mỗi kho dừng ở
một chỗ khác nhau. Đã quan sát trên e9:

* tiến trình bị dừng → story kẹt ở ``running`` vĩnh viễn;
* worktree merge vào nhánh chính xong → sổ vẫn ghi ``failed``, và chi
  phí lượt ấy không vào đâu cả;
* chạy lại story đã merge → worktree mới rẽ từ nhánh đã chứa sẵn công
  việc, diff rỗng, story không bao giờ qua được nữa.

Cách chữa mượn từ *revertible effects*: mỗi bước ghi lại **nghịch đảo**
của chính nó, và nhật ký là thứ máy đọc được để dựng lại xem lượt chạy
đã đi tới đâu. Không dựng runtime tổng quát — phạm vi đúng bằng những
kho AISEF thật sự sở hữu.

Một ranh giới cố ý: **không giả vờ hoàn nguyên thứ không hoàn nguyên
được.** Merge đã vào nhánh chính thì cách xử đúng là *đi tiếp* cho
trạng thái đuổi kịp, không phải cố lùi lại.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

JOURNAL_DIR = "journal"

#: Các mốc của một lượt chạy, đúng thứ tự. Danh sách này là hợp đồng: đọc
#: nhật ký rồi so với nó là biết lượt chạy dừng ở đâu và còn nợ gì.
#:
#: ``candidate.frozen`` mang SHA của ứng viên và đứng **trước** mọi bước
#: kiểm (ADR-004 R1): bằng chứng chỉ có nghĩa khi nó trỏ vào một bản cụ
#: thể. Trước đây bước này tên ``commit.created`` và nằm *sau*
#: ``review.completed`` — ứng viên được chốt sau khi đã chấm, nên không
#: nói được "bằng chứng này thuộc bản nào".
STEPS = (
    "attempt.started",
    "worktree.created",
    "status.running",
    "changes.detected",
    "candidate.frozen",
    "verification.completed",
    "review.completed",
    "merge.completed",
    "attempt.committed",
)

#: Bước đánh dấu công việc đã sang nhánh chính. Từ mốc này trở đi, hoàn
#: nguyên là sai: công việc đã ở ngoài tầm giao dịch.
POINT_OF_NO_RETURN = "merge.completed"

ABORTED = "attempt.aborted"
RECONCILED = "attempt.reconciled"


@dataclass
class Entry:
    seq: int = 0
    step: str = ""
    at: float = 0.0
    attempt: int = 0
    data: dict = field(default_factory=dict)
    #: Việc cần làm để gỡ bước này. Rỗng nghĩa là bước không để lại gì
    #: cần gỡ (ví dụ một mốc thuần thông tin).
    undo: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "seq": self.seq,
            "step": self.step,
            "at": round(self.at, 3),
            "attempt": self.attempt,
            "data": self.data,
            "undo": self.undo,
        }


@dataclass
class Journal:
    story_id: str
    entries: list[Entry] = field(default_factory=list)

    def steps(self) -> list[str]:
        return [e.step for e in self.entries]

    def last(self, step: str) -> Entry | None:
        for e in reversed(self.entries):
            if e.step == step:
                return e
        return None

    def reached(self, step: str) -> bool:
        return self.last(step) is not None

    @property
    def needs_merge(self) -> bool:
        """Story đã có worktree (tức phải merge) nhưng chưa merge.

        `DONE` được ghi lúc qua cổng, trước merge — nên riêng trạng thái
        không trả lời được câu "code đã lên nhánh chính chưa". Chạy thẳng
        trong dự án (`--no-isolate`) thì không có bước merge, và cũng không
        có `worktree.created`, nên trả False là đúng.
        """
        # `commit.created` (tên cũ) chỉ xảy ra trong nhánh worktree, nên nó
        # cũng là bằng chứng có worktree — cho nhật ký cũ thiếu bước đầu.
        # `candidate.frozen` **không** dùng được ở đây: nó được ghi cả khi
        # chạy thẳng trong dự án (`--no-isolate`), nơi không có gì để merge.
        co_worktree = self.reached("worktree.created") or self.reached("commit.created")
        return co_worktree and not self.merged()

    @property
    def attempt_no(self) -> int:
        return max((e.attempt for e in self.entries), default=0)

    def open_attempt(self) -> int:
        """Số hiệu lượt đã mở mà chưa đóng. 0 nếu không có lượt nào dở.

        Đóng nghĩa là có ``attempt.committed``, ``attempt.aborted`` hoặc
        ``attempt.reconciled`` **sau** lần ``attempt.started`` gần nhất.
        """
        mo = 0
        for e in self.entries:
            if e.step == "attempt.started":
                mo = e.attempt
            elif e.step in (STEPS[-1], ABORTED, RECONCILED) and e.attempt == mo:
                mo = 0
        return mo

    def merged(self) -> bool:
        """Công việc của story này đã sang nhánh chính chưa.

        Câu hỏi quan trọng nhất khi chạy lại: worktree mới rẽ từ nhánh đã
        chứa sẵn công việc thì diff rỗng, và story không bao giờ qua cổng
        rà soát được nữa. Biết nó đã merge thì bỏ qua, không thử mù.
        """
        return self.reached(POINT_OF_NO_RETURN)


class JournalStore:
    """Đọc/ghi ``journal/{story}.jsonl``. Nối thêm, không sửa."""

    def __init__(self, artifact_root: Path | str):
        self.root = Path(artifact_root) / JOURNAL_DIR

    def path(self, story_id: str) -> Path:
        return self.root / f"{story_id}.jsonl"

    def record(self, story_id: str, entry: Entry) -> Entry:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path(story_id)
        entry.at = entry.at or time.time()
        with path.open("a", encoding="utf-8") as fh:
            entry.seq = self._next_seq(path)
            fh.write(json.dumps(entry.as_dict(), ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return entry

    def _next_seq(self, path: Path) -> int:
        highest = 0
        if path.is_file():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    highest = max(highest, int(json.loads(line).get("seq") or 0))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
        return highest + 1

    def read(self, story_id: str) -> Journal:
        j = Journal(story_id=story_id)
        path = self.path(story_id)
        if not path.is_file():
            return j
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue  # một dòng hỏng không đáng làm mất cả nhật ký
            j.entries.append(Entry(
                seq=int(raw.get("seq") or 0),
                step=str(raw.get("step") or ""),
                at=float(raw.get("at") or 0.0),
                attempt=int(raw.get("attempt") or 0),
                data=raw.get("data") or {},
                undo=raw.get("undo") or {},
            ))
        return j

    def story_ids(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.stem for p in self.root.glob("*.jsonl"))


# ------------------------------------------------------------ giao dịch


@dataclass
class Reconciled:
    story_id: str
    action: str = ""      # "" | "roll-forward" | "undo" | "status-fix"
    detail: str = ""

    def line(self) -> str:
        return f"{self.story_id}: {self.action} — {self.detail}"


class StoryRunTransaction:
    """Một lượt chạy story, ghi vào nhật ký từng mốc kèm nghịch đảo.

    Cố ý **không** giữ trạng thái nào chỉ trong bộ nhớ: tiến trình chết
    thì object chết theo, còn nhật ký thì còn. Mọi thứ cần để dọn dẹp
    phải nằm trên đĩa từ lúc bước đó xảy ra, không phải lúc nó hỏng.
    """

    def __init__(
        self,
        story_id: str,
        *,
        artifact_root: Path | str,
        attempt: int = 1,
    ):
        self.story_id = story_id
        self.store = JournalStore(artifact_root)
        self.attempt = attempt
        self.committed = False

    def __enter__(self) -> "StoryRunTransaction":
        self.record("attempt.started")
        return self

    def record(self, step: str, *, undo: dict | None = None, **data) -> Entry:
        return self.store.record(self.story_id, Entry(
            step=step, attempt=self.attempt, data=data, undo=undo or {},
        ))

    def commit(self) -> None:
        self.record("attempt.committed")
        self.committed = True

    def abort(self, reason: str) -> None:
        self.record(ABORTED, reason=reason)

    def __exit__(self, exc_type, exc, tb) -> bool:
        if not self.committed:
            self.abort(f"{exc_type.__name__}: {exc}" if exc_type else "abnormal termination")
        return False  # không nuốt lỗi


def reconcile_story(
    story_id: str,
    *,
    artifact_root: Path | str,
    state,
    worktrees=None,
) -> Reconciled | None:
    """Đưa một story về trạng thái nhất quán sau lượt chạy dở.

    Ba tình huống, ba cách xử khác nhau:

    1. **Đã merge** — công việc ở ngoài tầm giao dịch rồi. Đi tiếp cho
       trạng thái đuổi kịp, không cố lùi. Đây đúng là ca đã xảy ra trên
       e9: worktree merge xong mà sổ vẫn ghi ``failed``.
    2. **Còn dở, chưa merge** — gỡ tài nguyên tạm (worktree) và đưa
       trạng thái về ``pending`` để chạy lại. Nhánh **không** xoá: công
       việc đã commit trong đó không được biến mất vì một lần dọn.
    3. **Không có lượt dở** — chỉ sửa trạng thái nếu nó kẹt ở
       ``running``/``verifying`` của một tiến trình đã chết.
    """
    from .state import StoryStatus

    j = JournalStore(artifact_root).read(story_id)
    rec = state.load().stories.get(story_id)
    if rec is None:
        return None
    cur = rec.state

    if j.merged() and cur is not StoryStatus.DONE:
        _to_done(state, story_id)
        JournalStore(artifact_root).record(story_id, Entry(
            step=RECONCILED, attempt=j.attempt_no,
            data={"action": "roll-forward", "from": cur.value},
        ))
        return Reconciled(story_id, "roll-forward",
                          "already merged to main branch, rolling status forward")

    dang_do = j.open_attempt()
    ket = cur in (StoryStatus.RUNNING, StoryStatus.VERIFYING)
    if not dang_do and not ket:
        return None

    if worktrees is not None and (dang_do or ket):
        # Nhánh giữ lại: commit trong đó là công việc thật.
        worktrees.remove(story_id, delete_branch=False)
    if cur is not StoryStatus.DONE:
        state.reset_for_retry(story_id)
    JournalStore(artifact_root).record(story_id, Entry(
        step=RECONCILED, attempt=j.attempt_no,
        data={"action": "undo", "from": cur.value},
    ))
    return Reconciled(
        story_id, "undo",
        f"incomplete run at `{j.steps()[-1] if j.entries else '?'}`, cleaned up and back to pending",
    )


def reconcile_all(
    *,
    artifact_root: Path | str,
    state,
    worktrees=None,
) -> list[Reconciled]:
    """Hoà giải mọi story có nhật ký. Chạy đầu mỗi lượt `aisef run`.

    Đây là chỗ một tiến trình bị giết ở lần chạy trước được dọn: không
    có bước này thì story kẹt ``running`` vĩnh viễn và không lệnh nào gỡ
    ra được.
    """
    store = JournalStore(artifact_root)
    out = []
    for sid in store.story_ids():
        r = reconcile_story(
            sid, artifact_root=artifact_root, state=state, worktrees=worktrees
        )
        if r:
            out.append(r)
    return out


def _to_done(state, story_id: str) -> None:
    """Đưa trạng thái tới ``done`` qua đúng các cạnh hợp lệ.

    Đi theo máy trạng thái chứ không ghi đè: bản ghi phải giữ được một
    vết chuyển hợp lệ, nếu không thì nó không còn là bằng chứng.
    """
    from .state import StoryStatus

    cur = state.load().stories[story_id].state
    if cur is StoryStatus.DONE:
        return
    if cur is StoryStatus.VERIFIED:
        state.transition(story_id, StoryStatus.DONE)
        return
    if cur is not StoryStatus.VERIFYING:
        state.reset_for_retry(story_id)
        state.transition(story_id, StoryStatus.RUNNING)
        state.transition(story_id, StoryStatus.VERIFYING)
    state.transition(story_id, StoryStatus.VERIFIED)
    state.transition(story_id, StoryStatus.DONE)
