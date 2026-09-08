"""Chấm lại cổng story trên bằng chứng đã ghi (ADR-005 V4) — `inspect score`
của Inspect AI, `regrade` của Harbor, làm bằng thứ đã có.

`gate.evaluate` thuần trên `Evidence` + kwargs, và từ V4 `implement` ghi
kwargs ấy vào `note gate:input` ngay trước `gate:verdict`. Nên với mọi lượt
có bản ghi này, cổng **hiện tại** chấm lại được lượt **cũ**: cắt bằng chứng
ở `seq` của `gate:input` (đúng tập sự kiện cổng đã thấy), dựng lại kwargs,
gọi `evaluate`, so mục chặn với `gate:verdict` đã ghi. $0, tất định, và
đây là thứ 17/25 lỗi chấm sai cần: sửa một luật cổng rồi thấy ngay lượt
nào đổi kết cục, trước khi trả tiền cho một lượt agent.

Chấm lại **luật hợp** trên lời reviewer/security **đã ghi** — không gọi
lại model. Lượt không có `gate:input` (bằng chứng trước V4) thì nói là
không replay được, không đoán kwargs từ thứ khác.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..harness.observe import NOTE, Evidence, Event
from .gate import StoryGate, evaluate
from .security import parse as parse_security

GATE_INPUT = "gate:input"
GATE_VERDICT = "gate:verdict"

BANNER = ("replay: re-score gate rules (gate.evaluate from current code) on recorded "
          "evidence and reviewer/security findings — no model calls")


@dataclass
class Replay:
    story_id: str
    attempt: int
    seq: int                      # seq của `gate:input`
    candidate: str
    gate: StoryGate
    #: Mục chặn đã ghi ở `gate:verdict` sau đầu vào này; None = không có verdict.
    recorded: list[str] | None

    @property
    def now(self) -> list[str]:
        return [c.name for c in self.gate.failures]

    def rows(self) -> list[tuple[str, str, str]]:
        """(tên mục, đã ghi, nay): đã ghi chỉ biết ✗/không — `gate:verdict`
        chỉ lưu tên mục chặn; nay là kết cục đủ sáu loại."""
        truoc = set(self.recorded or [])
        return [(c.name, "✗" if c.name in truoc else "·", c.outcome.mark) for c in self.gate.checks]

    def changed(self) -> list[str]:
        """Mục đổi trạng thái chặn — thứ duy nhất so được với bản ghi cũ."""
        if self.recorded is None:
            return []
        truoc, nay = set(self.recorded), set(self.now)
        return sorted(truoc ^ nay)

    def summary(self) -> str:
        head = (f"{self.story_id} attempt {self.attempt} · candidate {self.candidate[:7] or '—'} · "
                f"recorded: {'PASS' if self.recorded == [] else 'FAIL' if self.recorded else 'no verdict'}"
                f" · now: {'PASS' if self.gate.passed else 'FAIL'}")
        lines = [head, "  check                            | recorded | now"]
        for name, truoc, nay in self.rows():
            dau = " ≠" if name in self.changed() else ""
            lines.append(f"  {name:<32} | {truoc:^6} | {nay}{dau}")
        doi = self.changed()
        lines.append("  diff: " + (", ".join(doi) if doi else "none — same blocking checks"))
        return "\n".join(lines)


def kwargs_from(detail: dict) -> dict:
    """Dựng lại kwargs của `evaluate` từ `gate:input`. `security` ghi cùng
    hình `tool_run security` ({findings: [dòng "[mức] …"], error}) nên
    `parse` đọc lại được; các khoá khác là JSON thuần."""
    kw = {k: v for k, v in detail.items() if k not in ("attempt",)}
    sec = kw.get("security")
    if sec is not None:
        rep = parse_security("\n".join(sec.get("findings") or []))
        rep.error = str(sec.get("error") or "")
        kw["security"] = rep
    return kw


def _pairs(evidence: Evidence) -> list[tuple[Event, Event | None]]:
    """Mỗi `gate:input` ghép với `gate:verdict` **đầu tiên** sau nó."""
    inputs = evidence.of(NOTE, GATE_INPUT)
    verdicts = evidence.of(NOTE, GATE_VERDICT)
    out = []
    for i, inp in enumerate(inputs):
        tran = inputs[i + 1].seq if i + 1 < len(inputs) else float("inf")
        v = next((v for v in verdicts if inp.seq < v.seq < tran), None)
        out.append((inp, v))
    return out


def unreplayable(evidence: Evidence) -> list[int]:
    """Số lượt có `gate:verdict` mà không có `gate:input` đứng trước — bằng
    chứng trước V4. Trả số lượt để người đọc biết cái gì bị bỏ, không đoán."""
    co = {v.seq for _, v in _pairs(evidence) if v is not None}
    return [int(v.detail.get("attempt") or 0)
            for v in evidence.of(NOTE, GATE_VERDICT) if v.seq not in co]


def replay(evidence: Evidence, *, attempt: int = 0) -> list[Replay]:
    """Chấm lại mọi lượt có `gate:input` (hoặc đúng `attempt`)."""
    out = []
    for inp, verdict in _pairs(evidence):
        luot = int(inp.detail.get("attempt") or 0)
        if attempt and luot != attempt:
            continue
        truoc = Evidence(story_id=evidence.story_id,
                         events=[e for e in evidence.events if e.seq <= inp.seq])
        kw = kwargs_from(inp.detail)
        gate = evaluate(evidence.story_id, truoc, **kw)
        out.append(Replay(
            story_id=evidence.story_id, attempt=luot, seq=inp.seq,
            candidate=str(kw.get("candidate") or ""), gate=gate,
            recorded=None if verdict is None else [str(x) for x in verdict.detail.get("failures") or []],
        ))
    return out
