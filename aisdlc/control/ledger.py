"""Sổ hành vi — VERIFIED / GAP / REOPENED (ADR-004 R2, R6, R7).

Cổng story trả lời "story này xong chưa". Nó **không** trả lời được câu
thứ hai, câu mà HoH đo bằng 17/81 issue reopened: *hành vi nào từng đúng
rồi hỏng?* Bằng chứng hôm nay đã đủ để trả lời — mỗi lần chạy test ghi
tên từng test và test nào đỏ, mỗi lần đối chiếu mockup ghi màn hình nào
khớp — nhưng chưa ai đọc nó **theo thời gian**.

Module này là một **phép chiếu**, không phải kho mới: không có sự kiện
nào chỉ nó ghi được, không có sự thật nào chỉ nó biết. Xoá `ledger.json`
rồi dựng lại từ `evidence/` phải ra đúng cái cũ — trừ `loops[]`, mốc của
vòng cải tiến, thứ duy nhất không suy được từ bằng chứng nên được mang
sang từ sổ cũ. Vì thế không ai sửa được lịch sử hành vi, và không có chỗ
cho ai đó "đánh dấu là xong".

Bốn loại hành vi, mỗi loại một nguồn máy đọc được:

* `AC-<story>-<i>` — tên test ở lần chạy `tool_run test` (qua `acceptance`);
* `FR-x` / `NFR-x` — `covers` của story, xanh khi tiêu chí của story xanh;
* `qa:<kind>`   — `tool_run` tên `qa:<kind>`;
* `mockup:<màn>` — sự kiện `mockup_map`.

Trạng thái suy bằng code theo thứ tự thời gian, không ai khai:

    (chưa có) → xanh   → VERIFIED
    (chưa có) → đỏ     → GAP
    VERIFIED  → đỏ     → REOPENED  (`regressed_by` = story#lượt[@candidate])
    GAP/REOPENED → xanh → VERIFIED  (đếm vào *resolved*)

Lịch sử chỉ ghi khi trạng thái **đổi**. e9 có ~100 lần chạy test × ~280
tên test; ghi mọi lần quan sát thì sổ to hơn bằng chứng nó chiếu ra.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..harness.observe import (
    BEHAVIOR,
    EVIDENCE_DIR,
    MOCKUP_MAP,
    TOOL_RUN,
    AGENT_RUN,
    EvidenceStore,
)
from .acceptance import ac_code, coverage as ac_coverage

VERSION = 1
LEDGER_FILE = "ledger.json"
INDEX_FILE = "INDEX.md"
STORIES_INDEX = "stories.index.json"

VERIFIED = "verified"
GAP = "gap"
REOPENED = "reopened"

#: Bằng chứng không thuộc story nào — pha lập kế hoạch, dựng mockup, quét skill.
PHASE_PREFIXES = ("plan-", "mockup-", "skill-")
#: Bằng chứng cấp dự án của vòng cải tiến (ADR-004 R3): `evidence/loop-<n>.jsonl`.
#: Là **mốc**, không phải story: sổ đọc nó (hành vi có `since = loop-n`)
#: nhưng không dựng dòng chỉ mục cho nó.
LOOP_PREFIX = "loop-"

_ATTEMPT = re.compile(r"#(\d+)$")
_EPIC_FROM_ID = re.compile(r"^STORY-(\d+)-")


@dataclass
class Behavior:
    """Một hành vi và toàn bộ đường đời của nó."""

    id: str
    kind: str                                   # ac | fr | nfr | qa | mockup
    story: str = ""
    status: str = ""
    candidate: str = ""
    since: str = ""                             # "<story>#<lượt>" hoặc "loop-n"
    source: dict = field(default_factory=dict)
    regressed_by: str = ""
    history: list[dict] = field(default_factory=list)

    @property
    def ever_verified(self) -> bool:
        return any(h["status"] == VERIFIED for h in self.history)

    def as_dict(self) -> dict:
        out = {
            "kind": self.kind, "status": self.status, "candidate": self.candidate,
            "since": self.since, "source": self.source, "history": self.history,
        }
        if self.story:
            out["story"] = self.story
        if self.regressed_by:
            out["regressed_by"] = self.regressed_by
        return out


@dataclass
class StoryLine:
    """Một dòng chỉ mục: thứ đủ để quyết định có cần đọc bằng chứng không."""

    id: str
    epic: str = ""
    acceptance: int = 0
    covers: list[str] = field(default_factory=list)
    status: str = "?"
    candidate: str = ""

    @property
    def evidence_path(self) -> str:
        return f"{EVIDENCE_DIR}/{self.id}.jsonl"


@dataclass
class Ledger:
    root: Path = field(default_factory=Path)
    behaviors: dict[str, Behavior] = field(default_factory=dict)
    stories: dict[str, StoryLine] = field(default_factory=dict)
    loops: list[dict] = field(default_factory=list)
    #: Số lần một hành vi đã xác minh bị làm hỏng lại, và số lần đóng được gap.
    reopen_events: int = 0
    resolved: int = 0
    #: Hồi quy **liên story**: hành vi xanh ở story A, đỏ lại ở bằng chứng của
    #: story B ≠ A. Đây là con số HoH đo (17/81 của Fusepoint); đỏ-lại trong
    #: chính lượt của story mình phần lớn là TDD bình thường, không phải hồi quy.
    cross_reopens: list[dict] = field(default_factory=list)

    # ------------------------------------------------------------- ghi nhận

    def observe(
        self,
        bid: str,
        kind: str,
        *,
        ok: bool,
        at: float,
        story: str,
        owner: str = "",
        attempt: int = 0,
        candidate: str = "",
        source: dict | None = None,
    ) -> None:
        """Một quan sát.

        `story` là story **quan sát** (tệp bằng chứng nào ghi), `owner` là
        story **sở hữu** hành vi. Hai cái khác nhau chính là lúc đáng đọc
        nhất: tiêu chí của story trước đỏ lại trong lượt chạy của story sau.
        """
        b = self.behaviors.get(bid)
        if b is None:
            b = self.behaviors[bid] = Behavior(id=bid, kind=kind)
        b.story = b.story or owner or story

        status = VERIFIED if ok else (REOPENED if b.ever_verified else GAP)
        if status == b.status:
            # Không đổi trạng thái: cập nhật candidate mới nhất, không ghi sử.
            b.candidate = candidate or b.candidate
            return

        marker = f"{story}#{attempt}" if attempt else story
        if status == REOPENED:
            self.reopen_events += 1
            b.regressed_by = marker + (f"@{candidate[:7]}" if candidate else "")
            was = next(
                (h["story"] for h in reversed(b.history) if h["status"] == VERIFIED), ""
            )
            if was and was != story:
                self.cross_reopens.append(
                    {"id": bid, "verified_by": was, "regressed_by": b.regressed_by, "at": at}
                )
        elif status == VERIFIED and b.status in (GAP, REOPENED):
            self.resolved += 1
            b.regressed_by = ""

        b.status, b.candidate, b.since = status, candidate, marker
        b.source = dict(source or {})
        b.history.append({
            "at": at, "status": status, "candidate": candidate,
            "story": story, "source": b.source,
        })

    # ------------------------------------------------------------- đọc ra

    def summary(self) -> dict:
        counts = {VERIFIED: 0, GAP: 0, REOPENED: 0}
        for b in self.behaviors.values():
            counts[b.status] = counts.get(b.status, 0) + 1
        return {
            "behaviors": len(self.behaviors),
            "verified": counts[VERIFIED],
            "gap": counts[GAP],
            "reopened": counts[REOPENED],
            "resolved": self.resolved,
            "reopen_events": self.reopen_events,
            "cross_reopens": len(self.cross_reopens),
        }

    def epic_of(self, story_id: str) -> str:
        line = self.stories.get(story_id)
        return (line.epic if line else "") or _epic_of(story_id)

    def for_story(self, story_id: str) -> list[Behavior]:
        """Hành vi *của* story: tiêu chí và yêu cầu nó phủ, cộng hành vi mà
        chính bằng chứng của nó đặt trạng thái lần đầu."""
        line = self.stories.get(story_id)
        ids = set()
        if line:
            ids |= {ac_code(story_id, i) for i in range(1, line.acceptance + 1)}
            ids |= set(line.covers)
        return [
            b for b in self.behaviors.values()
            if b.id in ids or b.story == story_id
        ]

    def counts_for(self, story_id: str) -> tuple[int, int, int]:
        out = {VERIFIED: 0, GAP: 0, REOPENED: 0}
        for b in self.for_story(story_id):
            out[b.status] = out.get(b.status, 0) + 1
        return out[VERIFIED], out[GAP], out[REOPENED]

    def metrics(self) -> dict:
        """R7 — bốn số của vòng cải tiến, tất cả đọc từ `history`."""
        entries = sorted(
            ((h["at"], bid, h) for bid, b in self.behaviors.items() for h in b.history),
            key=lambda t: (t[0], t[1]),
        )
        seen: set[str] = set()
        growth: list[dict] = []
        for at, bid, h in entries:
            if h["status"] == VERIFIED and bid not in seen:
                seen.add(bid)
                growth.append({"at": at, "story": h.get("story", ""), "verified": len(seen)})

        s = self.summary()
        loops = []
        prev = None
        for loop in self.loops:
            dv = loop["verified"] - (prev["verified"] if prev else 0)
            dr = loop["reopened"] - (prev["reopened"] if prev else 0)
            cost = float(loop.get("cost_usd") or 0.0)
            loops.append({
                **loop,
                "d_verified": dv,
                "d_reopened": dr,
                # Cải thiện biên: hành vi ròng thu được trên mỗi đô la vòng đó.
                # Không có chi phí thì không có mẫu số — `None`, không phải 0.
                "marginal": ((dv - dr) / cost) if cost else None,
            })
            prev = loop
        return {
            **s,
            "ever_verified": len(seen),
            "growth": growth,
            "reopen_rate": (self.reopen_events / len(seen)) if seen else 0.0,
            "cross_reopen_list": self.cross_reopens,
            "loops": loops,
        }

    def snapshot(self, loop_label: str, cost_usd: float = 0.0) -> dict:
        """Chốt một mốc (vòng cải tiến, hoặc lần chạy) vào `loops[]`."""
        s = self.summary()
        rec = {
            "n": loop_label, "at": time.time(),
            "verified": s["verified"], "gap": s["gap"], "reopened": s["reopened"],
            "cost_usd": float(cost_usd),
        }
        self.loops.append(rec)
        return rec

    # ------------------------------------------------------------- ghi đĩa

    def as_dict(self) -> dict:
        return {
            "version": VERSION,
            "behaviors": {bid: b.as_dict() for bid, b in sorted(self.behaviors.items())},
            "loops": self.loops,
        }

    def write(self, root: Path | str | None = None) -> Path:
        path = Path(root or self.root) / LEDGER_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.as_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    # ------------------------------------------------------------- chỉ mục

    def index_lines(self) -> list[str]:
        """R6 — một dòng mỗi epic, một dòng mỗi story. Không hơn.

        Chỉ mục là thứ *thay* cho việc đổ lịch sử vào prompt: nó nói có gì
        và ở đâu; ai cần chi tiết thì `aisdlc evidence <id>`.
        """
        by_epic: dict[str, list[StoryLine]] = {}
        for line in self.stories.values():
            by_epic.setdefault(self.epic_of(line.id), []).append(line)
        out: list[str] = []
        for epic in sorted(by_epic):
            stories = sorted(by_epic[epic], key=lambda s: s.id)
            tv = tg = tr = 0
            body = []
            for s in stories:
                v, g, r = self.counts_for(s.id)
                tv, tg, tr = tv + v, tg + g, tr + r
                body.append(
                    f"- {s.id} · {s.status} · {s.candidate[:7] or '—'} · "
                    f"V{v} G{g} R{r} · {s.evidence_path}"
                )
            done = sum(1 for s in stories if s.status == "done")
            out.append(f"## {epic} — {done}/{len(stories)} story xong · V{tv} G{tg} R{tr}")
            out += body
        return out

    def index(self, root: Path | str | None = None) -> Path:
        text = "\n".join([
            "# Chỉ mục bằng chứng",
            "",
            "Một dòng mỗi story: trạng thái · candidate · số hành vi "
            "VERIFIED/GAP/REOPENED · tệp bằng chứng. Chi tiết: `aisdlc evidence <id>`.",
            "",
            *self.index_lines(),
        ]) + "\n"
        path = Path(root or self.root) / INDEX_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def epic_slice(self, epic_id: str, *, max_chars: int = 2000) -> str:
        """Lát cắt chỉ mục của một epic, cho slot prompt. Có trần: ngữ cảnh
        là tài nguyên hữu hạn, và cắt có báo tốt hơn tràn im lặng."""
        want = epic_id or ""
        keep: list[str] = []
        taking = False
        for line in self.index_lines():
            if line.startswith("## "):
                taking = line[3:].split(" —")[0].strip() == want
            if taking:
                keep.append(line)
        text = "\n".join(keep)
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "\n_(đã cắt theo trần ký tự — `aisdlc evidence <id>`)_"
        return text


# ---------------------------------------------------------------- dựng sổ


def build(artifact_root: Path | str) -> Ledger:
    """Chiếu toàn bộ `evidence/` thành sổ hành vi, theo thứ tự thời gian."""
    root = Path(artifact_root)
    led = Ledger(root=root)

    index = _read_json(root / STORIES_INDEX)
    for raw in index.get("stories") or []:
        sid = str(raw.get("id") or "")
        if not sid:
            continue
        led.stories[sid] = StoryLine(
            id=sid,
            epic=str(raw.get("epic_id") or ""),
            acceptance=len(raw.get("acceptance_criteria") or []),
            covers=[str(c) for c in raw.get("covers") or []],
        )
    for sid, rec in (_read_json(root / "sprint-status.json").get("stories") or {}).items():
        if sid in led.stories and isinstance(rec, dict):
            led.stories[sid].status = str(rec.get("status") or "?")

    # `behaviors` dựng lại từ đầu mỗi lần; `loops[]` là phần **duy nhất**
    # không suy được từ evidence (mốc và chi phí của một vòng cải tiến), nên
    # nó được mang sang từ sổ cũ — nếu không, một lần `aisdlc report` sẽ xoá
    # sạch mốc mà vòng R3 vừa chốt.
    led.loops = [lo for lo in _read_json(root / LEDGER_FILE).get("loops") or []
                 if isinstance(lo, dict)]

    store = EvidenceStore(root)
    events: list[tuple] = []
    for sid in store.stories():
        if sid.startswith(PHASE_PREFIXES):
            continue
        if not sid.startswith(LOOP_PREFIX):
            led.stories.setdefault(sid, StoryLine(id=sid))
        for e in store.read(sid).events:
            events.append((e.at, sid, e.seq, e))
    # Thứ tự thời gian **giữa** các story: `seq` chỉ có nghĩa trong một tệp.
    events.sort(key=lambda t: (t[0], t[1], t[2]))

    attempts: dict[str, int] = {}
    for at, sid, _seq, e in events:
        attempts[sid] = _attempt(e, sid, attempts.get(sid, 0))
        n = attempts[sid]
        # R1 do luồng khác làm; evidence cũ không có candidate và đó là hợp lệ.
        cand = str(e.detail.get("candidate") or "")
        if cand and sid in led.stories:
            led.stories[sid].candidate = cand

        if e.kind == BEHAVIOR:
            det = e.detail
            led.observe(
                str(det.get("id") or e.name), str(det.get("kind") or _kind_of(e.name)),
                ok=str(det.get("status") or "") == VERIFIED, at=at, story=sid,
                attempt=n, candidate=cand or str(det.get("candidate") or ""),
                source=dict(det.get("source") or {}),
            )
        elif e.kind == TOOL_RUN and e.name == "test":
            _observe_tests(led, e, sid, n, cand, at)
        elif e.kind == TOOL_RUN and e.name.startswith("qa:"):
            led.observe(
                e.name, "qa", ok=bool(e.ok) and not e.detail.get("skipped"),
                at=at, story=sid, attempt=n, candidate=cand,
                source={"qa_kind": e.name.split(":", 1)[1],
                        **({"why": str(e.detail["skipped"])} if e.detail.get("skipped") else {})},
            )
        elif e.kind == MOCKUP_MAP:
            missing = list(e.detail.get("missing") or []) + list(e.detail.get("missing_data_roles") or [])
            led.observe(
                f"mockup:{e.name}", "mockup", ok=bool(e.ok), at=at, story=sid,
                attempt=n, candidate=cand,
                source={"screen": e.name, **({"why": "thiếu " + ", ".join(missing)} if missing else {})},
            )
    return led


def _observe_tests(led: Ledger, e, sid: str, attempt: int, cand: str, at: float) -> None:
    """Một lần chạy test → trạng thái của mọi tiêu chí nó *nhìn thấy*.

    Story chủ nhà bị chấm đủ: tiêu chí không có test nào mang mã của nó là
    GAP, đúng như cổng nói "chưa cấu hình ≠ đạt". Story khác chỉ bị chấm
    những tiêu chí thực sự có test trong lần chạy này — bộ test chạy một
    phần không được biến story không liên quan thành hồi quy.
    """
    det = e.detail
    ids = [str(t) for t in det.get("test_ids") or []]
    failed = {str(t) for t in det.get("failed_ids") or []}
    readable = bool(det.get("test_format")) and bool(ids)

    def note(story_id: str, i: int, ok: bool, source: dict) -> None:
        led.observe(ac_code(story_id, i), "ac", ok=ok, at=at, story=sid,
                    owner=story_id, attempt=attempt, candidate=cand,
                    source={"test_run": e.name, **source})

    targets: list[tuple[str, StoryLine, bool]] = []
    own = led.stories.get(sid)
    if own and own.acceptance:
        targets.append((sid, own, True))
    if readable:
        blob = "\n".join(ids).replace("_", "-")
        for other, line in led.stories.items():
            if other != sid and line.acceptance and f"AC-{other}-" in blob:
                targets.append((other, line, False))

    for story_id, line, owner in targets:
        if not readable:
            if not owner:
                continue
            why = str(det.get("unrunnable") or det.get("test_note") or "") or (
                "không đọc được tên test từ output runner"
            )
            for i in range(1, line.acceptance + 1):
                note(story_id, i, False, {"why": why})
            _observe_covers(led, line, ok=False, at=at, story=sid, attempt=attempt,
                            cand=cand, why=why)
            continue

        cov = ac_coverage(story_id, line.acceptance, ids)
        judged = []
        for i, tests in cov.items():
            if not tests:
                if owner:
                    note(story_id, i, False, {"why": "chưa có test mang mã"})
                    judged.append(False)
                continue
            red = [t for t in tests if t in failed]
            # Nguồn của một GAP phải là test **đỏ**, không phải test đầu danh
            # sách: người đọc `aisdlc evidence` cần tên để mở, không cần một
            # cái tên xanh nằm cạnh chỗ hỏng.
            note(story_id, i, not red, {"test_id": (red or tests)[0], "tests": len(tests)})
            judged.append(not red)
        # Yêu cầu xanh khi **tiêu chí của nó** xanh — không phải khi cả lần
        # chạy xanh. Một lần chạy đỏ vì story khác không được biến FR của
        # story này thành hồi quy (đo trên e9: FR-1/FR-11 bị kết tội oan ở
        # STORY-01-06 vì luật cũ đọc `e.ok`).
        story_green = all(judged) if judged else bool(e.ok)
        _observe_covers(led, line, ok=story_green, at=at, story=sid, attempt=attempt,
                        cand=cand, why="" if story_green else "tiêu chí của story chưa xanh")


def _observe_covers(led: Ledger, line: StoryLine, *, ok: bool, at: float, story: str,
                    attempt: int, cand: str, why: str) -> None:
    for req in line.covers:
        led.observe(req, _kind_of(req), ok=ok, at=at, story=story, owner=line.id,
                    attempt=attempt, candidate=cand,
                    source={"story": line.id, **({"why": why} if why else {})})


def _kind_of(bid: str) -> str:
    up = bid.upper()
    if up.startswith("NFR"):
        return "nfr"
    if up.startswith("FR"):
        return "fr"
    if bid.startswith("qa:"):
        return "qa"
    if bid.startswith("mockup:"):
        return "mockup"
    return "ac"


def _epic_of(story_id: str) -> str:
    m = _EPIC_FROM_ID.match(story_id)
    return f"EPIC-{m.group(1)}" if m else "(không epic)"


def _attempt(e, sid: str, current: int) -> int:
    """Lượt thử hiện tại của story — đọc từ tên `agent_run` (`STORY-x#2`)
    hoặc `detail.attempt` của handoff/rà soát. Không đoán: không thấy thì giữ."""
    if e.kind == AGENT_RUN and e.name.startswith(sid):
        m = _ATTEMPT.search(e.name)
        if m:
            return int(m.group(1))
    raw = e.detail.get("attempt")
    if isinstance(raw, int) and raw > 0:
        return raw
    return current


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}
