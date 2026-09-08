"""Điểm cỡ story — tất định, giải thích được từng thành phần (ADR-004 R5).

`story.max_screen_states` (P2-12) đo **một** chiều: trạng thái màn hình.
Số đo 2026-09-05 trên e9 cho thấy chiều ấy chưa đủ — STORY-01-01 không có
màn hình nào mà vẫn 61 lượt developer ở lượt đầu và 4 lượt thử (14 đường
dẫn khai, 9 sau khi trừ manifest/lockfile; 7 tiêu chí). Module này cộng
năm chiều đo được **trước khi gọi model**, mỗi chiều một trọng số có tên,
và trả về bản giải thích để người đọc kiểm lại được con số thay vì phải
tin nó.

Hiệu chuẩn (B4, hồi cứu 2026-09-05, không tốn agent — xem ADR-004 §6 R5):
11 story thật có bằng chứng (e9 STORY-01-01..01-06, `par` 5 story), đối
chiếu điểm với **lượt developer lượt đầu** (`turns` của `agent_run`
`<story>#1` đầu tiên trong evidence):

| story | trạng thái | tiêu chí | scope | fan-in | điểm | lượt đầu |
|---|---|---|---|---|---|---|
| e9 01-01 | 0 | 7 | 9 | 1 | 12,5 | 61 |
| e9 01-02 | 0 | 7 | 10 | 2 | 14,0 | 42 |
| e9 01-03 | 0 | 4 | 3 | 1 | 6,5 | 57 |
| e9 01-04 | 9 | 7 | 13 | 1 | **23,5** | 89 / 90, 4 lượt, $79,67 |
| e9 01-05 | 5 | 7 | 10 | 1 | **18,0** | 91 — chạm `max_turns` |
| e9 01-06 | 1 | 7 | 6 | 2 | 13,0 | 84 |
| par ×5 | 0 | 2 | 2 | 0 | 3,0 | 24 / 41 / 37 / — / 8 |

Spearman(điểm, lượt đầu) = **0,88** trên 10 story có số lượt (par
STORY-02-01 ghi `turns = 0` — client không báo, loại khỏi mẫu). Ngưỡng
mặc định 16 chặn đúng hai story đắt nhất (01-04 và 01-05) và không chạm
01-01/01-02/01-06 (12,5–14,0), 01-03 (6,5) hay `par` (3,0). Nó **không**
bắt được hai lần chạm `max_turns` khác (e9 01-01 ở 61/60 lượt, `par`
01-02 ở 41/40) — cả hai xảy ra dưới trần `max_turns` thấp hơn trần hiện
tại, nên đó là chuyện của `run.max_turns`, không phải của cỡ story. Xem
`docs/ADR-004-evidence-driven-epic-improvement.md` §6 R5.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..config import DEFAULTS, Config
from .normalize import MANIFESTS, Story, is_lockfile

#: Một trạng thái màn hình story **dựng đầu tiên**. Chiều đắt nhất đã đo:
#: 01-04 (9 trạng thái) 89 lượt, 01-05 (4 + 1 chạm lại) 91 lượt.
SCREEN_STATE_WEIGHT = 1.0
#: Một tiêu chí chấp nhận. Cùng cỡ với một trạng thái: e9 mọi story 7 tiêu
#: chí, và story 4 tiêu chí (01-03) rẻ hơn hẳn.
ACCEPTANCE_WEIGHT = 1.0
#: Một đường dẫn trong phạm vi ghi (không tính manifest/lockfile — chúng là
#: hệ quả tự động, xem `normalize.with_lockfiles`). Nửa trọng số: 01-01 có
#: 9 đường dẫn mà vẫn xong sau 2 lượt.
WRITE_SCOPE_WEIGHT = 0.5
#: Một story phụ thuộc vào story này. Fan-in cao nghĩa là sai ở đây lan ra
#: nhiều chỗ, nên phiên phải cẩn thận hơn.
FAN_IN_WEIGHT = 1.0
#: Một **story láng giềng** có hành vi đã VERIFIED mà phạm vi ghi của story
#: này chạm vào (ledger, R2). Đếm theo story sở hữu, không theo hành vi: đo
#: 2026-09-06 trên e9, STORY-01-07 chạm 31 hành vi của 3 story (01-04/05/06)
#: — đếm hành vi thì +15,5 điểm, một story 12,5 bị chặn oan ở 28,0.
#:
#: Trọng số **0 cho tới khi hiệu chuẩn được**: bảng B4 (Spearman 0,88) dựng
#: trên các story chạy khi sổ còn rỗng, nên chiều này chưa góp một điểm nào
#: vào tương quan ấy. Bật 0,5 thử trên sổ thật e9 (2026-09-06) thì ba story
#: sát ngưỡng (02-03 15,0 → 17,0; 03-03 15,5 → 17,0; 05-01 16,0 → 17,5) bị
#: chặn bằng một trọng số chưa có số lượt nào chứng minh. Thành phần vẫn
#: được đếm và ghi vào `complexity.json` để hiệu chuẩn khi đủ story vừa có
#: sổ vừa có số lượt (xem `divergence`); lúc ấy đặt trọng số bằng số đo.
VERIFIED_TOUCHED_WEIGHT = 0.0

#: Tên tệp hiệu chuẩn tự ghi, trong `_bmad-output/`.
CALIBRATION_FILE = "complexity.json"

#: "Xong trong một lượt ngắn" = lượt đầu dùng dưới ngần này phần `run.max_turns`.
SHORT_TURN_FRACTION = 0.5

#: Cần bao nhiêu story lệch cùng một hướng thì mới kết luận ngưỡng sai.
#: Một story lệch là chuyện thường; hai là dấu hiệu.
DIVERGENCE_MIN = 2

#: Dấu hiệu một trạng thái màn hình là **phụ** — chẻ được sang story sau.
#: Trạng thái chính là màn hình lúc mọi thứ bình thường; phần còn lại là
#: biên. Dùng để đề xuất cách chẻ, không dùng để tính điểm.
SECONDARY_STATE_MARKERS = (
    "rỗng", "trống", "empty", "lỗi", "error", "thất bại", "fail",
    "offline", "ngoại tuyến", "đang tải", "loading", "chưa sẵn sàng",
    "focus", "không khớp", "không tồn tại", "sắp cạn", "quá hạn", "trùng",
)

_DEV_RUN = re.compile(r"^(?P<story>[\w.-]+)#(?P<n>\d+)$")

#: Story trong một đợt chạy song song bằng luồng, và `record` là đọc-sửa-ghi
#: cả tệp: không có khoá thì hai story xong cùng lúc làm mất một dòng.
_WRITE_LOCK = threading.Lock()


@dataclass(frozen=True)
class Component:
    """Một chiều của điểm, kèm chỗ đã đếm ra nó."""

    name: str
    count: int
    weight: float
    evidence: str = ""

    @property
    def points(self) -> float:
        return round(self.count * self.weight, 2)

    def line(self) -> str:
        out = f"{self.name} {self.count}×{self.weight:g} = {self.points:g}"
        return f"{out} ({self.evidence})" if self.evidence else out


@dataclass(frozen=True)
class Score:
    story_id: str
    components: tuple[Component, ...] = field(default_factory=tuple)

    @property
    def total(self) -> float:
        return round(sum(c.points for c in self.components), 2)

    def get(self, name: str) -> Component:
        for c in self.components:
            if c.name == name:
                return c
        return Component(name, 0, 0.0)

    def as_dict(self) -> dict:
        return {
            "story_id": self.story_id,
            "total": self.total,
            "components": {c.name: {"count": c.count, "weight": c.weight,
                                    "points": c.points, "evidence": c.evidence}
                           for c in self.components},
        }

    def explain(self) -> str:
        return f"{self.total:g} = " + " + ".join(
            c.line() for c in self.components if c.count
        )


# ------------------------------------------------------------ thành phần


def screen_states(
    story: Story,
    *,
    experience=None,
    owned: dict[str, str] | None = None,
) -> list[tuple[str, int]]:
    """Trạng thái story phải dựng, theo từng màn hình.

    Màn hình story **khác** đã dựng trước tính 1 (chạm lại), không gánh cả
    số trạng thái của nó — giữ đúng luật `preflight.screen_owners` đã hiệu
    chuẩn trên e9 01-05.
    """
    out: list[tuple[str, int]] = []
    for sid in story.screens:
        scr = experience.by_id(sid) if experience is not None else None
        cua_minh = owned is None or owned.get(sid, story.id) == story.id
        out.append((sid, max(1, len(scr.states)) if (scr is not None and cua_minh) else 1))
    return out


def scope_paths(story: Story) -> list[str]:
    """Đường dẫn phạm vi ghi **story tự khai to tới đâu** — bỏ manifest và
    lockfile, vì harness tự thêm chúng (`normalize.with_lockfiles`)."""
    return [
        p for p in story.write_scope
        if not is_lockfile(p) and p.strip("/").rsplit("/", 1)[-1] not in MANIFESTS
    ]


def fan_in_counts(stories) -> dict[str, int]:
    """story → số story phụ thuộc vào nó."""
    out: dict[str, int] = {}
    for s in stories:
        for dep in getattr(s, "depends_on", []) or []:
            out[dep] = out.get(dep, 0) + 1
    return out


def _within(path: str, scope: str) -> bool:
    p, s = path.strip("/").split("/"), scope.strip("/").split("/")
    return len(p) >= len(s) and p[: len(s)] == s


def verified_touched(story: Story, ledger: dict | None,
                     scopes: dict[str, list[str]] | None = None) -> list[str]:
    """Hành vi đã VERIFIED của **story khác** mà phạm vi ghi của story này chạm vào.

    Sổ hành vi (R2, `control/ledger.py`) ghi story *sở hữu* hành vi, không
    ghi tệp — tệp là phạm vi ghi của story ấy, tra qua ``scopes`` (id →
    write_scope, đọc từ `stories.index.json`). Bản ghi có sẵn `files` /
    `write_scope` vẫn được đọc. Thiếu sổ, thiếu chỉ mục, hay hành vi không
    tra được tệp thì chiều này = 0 — thiếu dữ liệu không được biến thành
    điểm bịa. Hành vi của chính story (chạy lại) không tính: đó là mục tiêu
    của nó, không phải thứ nó phải giữ. Hành vi REOPENED mà `regressed_by`
    là chính story này **có** tính — nó vừa làm hỏng thì nó phải sửa lại.
    """
    if not isinstance(ledger, dict):
        return []
    scope = scope_paths(story)
    if not scope:
        return []
    scopes = scopes or {}
    out: list[str] = []
    for bid, rec in (ledger.get("behaviors") or {}).items():
        if not isinstance(rec, dict):
            continue
        status = str(rec.get("status", "")).lower()
        # REOPENED **do chính story này** vẫn là thứ nó phải giữ: bỏ khỏi danh
        # sách thì lượt 2 nhận cổng "bảo toàn" ✅ trong khi test của story
        # trước còn đỏ — đo par B3 2026-09-06: lượt 2 chỉ còn AC-01-01-2, mất
        # AC-01-01-1 và FR-1 mà lượt 1 vừa làm hỏng. REOPENED do story khác
        # thì không: story này không làm hỏng nó, chấm nó là ✗ oan.
        if status != "verified" and not (
            status == "reopened"
            and str(rec.get("regressed_by") or "").startswith(story.id + "#")
        ):
            continue
        owner = str(rec.get("story") or "")
        if owner == story.id:
            continue
        files = rec.get("files") or rec.get("write_scope") or scopes.get(owner) or []
        if isinstance(files, str):
            files = [files]
        if any(_within(str(f), s) or _within(s, str(f)) for f in files for s in scope):
            out.append(str(bid))
    return sorted(out)


def read_scopes(project: Path | str | None) -> dict[str, list[str]]:
    """id → write_scope từ `_bmad-output/stories.index.json`; thiếu thì rỗng."""
    if project is None:
        return {}
    path = Path(project) / "_bmad-output" / "stories.index.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    items = data.get("stories", []) if isinstance(data, dict) else data
    if isinstance(items, dict):
        items = list(items.values())
    return {str(s.get("id")): list(s.get("write_scope") or [])
            for s in items if isinstance(s, dict) and s.get("id")}


def read_experience(project: Path | str | None):
    """`_bmad-output/EXPERIENCE.md` nếu đọc được, không thì `None`."""
    if project is None:
        return None
    from .experience import parse_experience_file

    path = Path(project) / "_bmad-output" / "EXPERIENCE.md"
    if not path.is_file():
        return None
    try:
        return parse_experience_file(path)
    except (OSError, ValueError):
        return None


def read_ledger(project: Path | str | None) -> dict | None:
    """`_bmad-output/ledger.json` nếu có. Không có thì `None`, không lỗi."""
    if project is None:
        return None
    path = Path(project) / "_bmad-output" / "ledger.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def score_story(
    story: Story,
    *,
    project: Path | str | None = None,
    experience=None,
    owned: dict[str, str] | None = None,
    fan_in: int = 0,
    ledger: dict | None = None,
) -> Score:
    """Điểm cỡ của một story. Hàm thuần trên dữ liệu đã có, không gọi model."""
    if experience is None:
        experience = read_experience(project)
    per_screen = screen_states(story, experience=experience, owned=owned)
    states = sum(n for _, n in per_screen)
    scope = scope_paths(story)
    if ledger is None:
        ledger = read_ledger(project)
    touched = verified_touched(story, ledger, read_scopes(project))
    behaviors = (ledger or {}).get("behaviors") or {}
    # Hành vi không ghi story sở hữu (bản ghi cũ, tự tay) đếm riêng từng cái.
    owners = {str(behaviors.get(b, {}).get("story") or b) for b in touched}

    return Score(story.id, (
        Component("screen_states", states, SCREEN_STATE_WEIGHT,
                  ", ".join(f"`{sid}` {n}" for sid, n in per_screen)),
        Component("acceptance", len(story.acceptance_criteria), ACCEPTANCE_WEIGHT),
        Component("write_scope", len(scope), WRITE_SCOPE_WEIGHT,
                  ", ".join(f"`{p}`" for p in scope[:4]) + ("…" if len(scope) > 4 else "")),
        Component("fan_in", int(fan_in), FAN_IN_WEIGHT),
        Component("verified_touched", len(owners), VERIFIED_TOUCHED_WEIGHT,
                  f"{len(touched)} behaviours: " + ", ".join(touched[:4])
                  + ("…" if len(touched) > 4 else "") if touched else ""),
    ))


# ------------------------------------------------------------ gợi ý chẻ


def split_suggestion(
    story: Story,
    score: Score,
    *,
    experience=None,
    owned: dict[str, str] | None = None,
) -> str:
    """Cách chẻ story này, **tất định**, theo chiều nào đang nặng nhất.

    Ba lối, xét theo thứ tự: nhiều màn hình → mỗi màn một story; một màn
    nhiều trạng thái → trạng thái chính trước, trạng thái biên sau; không
    có màn hình → chẻ theo cụm tiêu chí chấp nhận. Không lối nào cần model:
    người lập kế hoạch đọc là làm được ngay.
    """
    per = screen_states(story, experience=experience, owned=owned)
    minh_dung = [(sid, n) for sid, n in per
                 if owned is None or owned.get(sid, story.id) == story.id]

    if len(minh_dung) > 1:
        return ("split by screen — one story per screen: "
                + "; ".join(f"`{sid}` ({n} states)" for sid, n in minh_dung))

    if minh_dung and minh_dung[0][1] > 1 and experience is not None:
        sid = minh_dung[0][0]
        scr = experience.by_id(sid)
        states = list(scr.states) if scr is not None else []
        chinh = [s for s in states if not _is_secondary(s)]
        phu = [s for s in states if _is_secondary(s)]
        if chinh and phu:
            return (f"split `{sid}` by state group — first story builds primary states "
                    f"({', '.join(chinh)}); next story builds secondary states "
                    f"({', '.join(phu)})")

    ac = story.acceptance_criteria
    if len(ac) > 1:
        nua = math.ceil(len(ac) / 2)
        return (f"split by acceptance criteria group — first story keeps AC 1–{nua}, next story "
                f"keeps AC {nua + 1}–{len(ac)}; divide `write_scope` to match the two groups "
                f"({score.get('write_scope').count} paths)")

    return "split story: reduce write scope or move acceptance criteria to a follow-up story"


def _is_secondary(state: str) -> bool:
    low = state.lower()
    return any(m in low for m in SECONDARY_STATE_MARKERS)


# ------------------------------------------------------------ hiệu chuẩn


def observed(artifact_root: Path | str, story_id: str, *, max_turns: int = 0) -> dict:
    """Số **thật** của story, đọc từ evidence: lượt developer lượt đầu, số
    lượt thử, có chạm `max_turns` không.

    Lượt đầu là `agent_run` tên `<story>#1` **đầu tiên** trong sổ: đó là
    phiên chưa có phản hồi nào, nên nó đo đúng "story này khó tới đâu khi
    đọc lần đầu". Chạy lại story sau khi sửa kế hoạch không ghi đè số ấy.
    """
    from ..harness.observe import AGENT_RUN, EvidenceStore

    ev = EvidenceStore(artifact_root).read(story_id)
    first, attempts, hit = None, 0, False
    for e in ev.of(AGENT_RUN):
        m = _DEV_RUN.match(e.name or "")
        if not m or m.group("story") != story_id:
            continue  # rà soát/bảo mật không phải lượt developer
        turns = int(e.detail.get("turns") or 0)
        attempts = max(attempts, int(m.group("n")))
        if first is None:
            first = turns
        if str(e.detail.get("error") or "") == "max_turns" or (
            max_turns and turns >= max_turns
        ):
            hit = True
    return {"first_turns": first, "attempts": attempts, "max_turns_hit": hit,
            "max_turns": int(max_turns)}


def calibration_path(artifact_root: Path | str) -> Path:
    return Path(artifact_root) / CALIBRATION_FILE


def load_calibration(artifact_root: Path | str) -> dict:
    path = calibration_path(artifact_root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = data.get("stories") if isinstance(data, dict) else None
    return rows if isinstance(rows, dict) else {}


def record(
    artifact_root: Path | str,
    story: Story,
    *,
    score: Score,
    config: Config | None = None,
) -> dict:
    """Ghi một dòng hiệu chuẩn cho story vừa xong: điểm dự đoán, từng thành
    phần, và số thật đo được từ evidence.

    Bảng này là thứ duy nhất nói được ngưỡng có còn đúng không. Không ghi
    thì mỗi lần nghi ngờ lại phải đi bới evidence bằng tay — và ngưỡng sẽ
    được nới bằng cảm giác."""
    cfg = config or Config(dict(DEFAULTS))
    row = score.as_dict() | observed(
        artifact_root, story.id, max_turns=int(cfg["run.max_turns"])
    ) | {
        "threshold": float(cfg["story.max_complexity"]),
        "at": round(time.time(), 3),
    }
    path = calibration_path(artifact_root)
    with _WRITE_LOCK:
        rows = load_calibration(artifact_root)
        rows[story.id] = row
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": 1, "stories": rows}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
    return row


def divergence(rows: dict) -> list[str]:
    """Ngưỡng có lệch dữ liệu không — đọc bảng hiệu chuẩn, không đoán.

    Hai hướng lệch, mỗi hướng cần ``DIVERGENCE_MIN`` story: ngưỡng **quá
    cao** (story dưới ngưỡng vẫn chạm `max_turns`) và ngưỡng **quá thấp**
    (story trên ngưỡng xong ngay lượt đầu, ngắn).
    """
    qua_cao, qua_thap = [], []
    for sid, r in sorted(rows.items()):
        if not isinstance(r, dict):
            continue
        total, limit = float(r.get("total") or 0), float(r.get("threshold") or 0)
        turns, cap = r.get("first_turns"), int(r.get("max_turns") or 0)
        if total <= limit and r.get("max_turns_hit"):
            qua_cao.append(f"{sid} ({total:g} ≤ {limit:g}, hit max_turns)")
        elif (total > limit and int(r.get("attempts") or 0) <= 1 and turns
                and cap and turns <= cap * SHORT_TURN_FRACTION):
            qua_thap.append(f"{sid} ({total:g} > {limit:g}, done in first run {turns} turns)")

    out = []
    if len(qua_cao) >= DIVERGENCE_MIN:
        out.append(f"`story.max_complexity` appears **too high**: {', '.join(qua_cao)}")
    if len(qua_thap) >= DIVERGENCE_MIN:
        out.append(f"`story.max_complexity` appears **too low**: {', '.join(qua_thap)}")
    return out


def spearman(xs, ys) -> float:
    """Tương quan hạng Spearman, có xử lý hạng đồng. NaN nếu không tính được.

    Dùng để đọc lại bảng hiệu chuẩn (B4): điểm dự đoán có xếp story theo
    đúng thứ tự tốn lượt không.
    """
    n = len(xs)
    if n < 2 or n != len(ys):
        return float("nan")
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def _ranks(values) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        share = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = share
        i = j + 1
    return out


__all__ = [
    "ACCEPTANCE_WEIGHT",
    "CALIBRATION_FILE",
    "Component",
    "FAN_IN_WEIGHT",
    "SCREEN_STATE_WEIGHT",
    "Score",
    "VERIFIED_TOUCHED_WEIGHT",
    "WRITE_SCOPE_WEIGHT",
    "divergence",
    "fan_in_counts",
    "load_calibration",
    "observed",
    "read_experience",
    "read_ledger",
    "record",
    "score_story",
    "scope_paths",
    "screen_states",
    "spearman",
    "split_suggestion",
]
