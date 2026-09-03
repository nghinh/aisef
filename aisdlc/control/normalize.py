"""Chuyển tài liệu BMAD thành dữ liệu có cấu trúc.

Đây là **ranh giới giữ BMAD ở vị trí phụ thuộc, không phải nền móng**
(quyết định Đ4). Framework sở hữu mô hình dữ liệu của mình; BMAD sinh
markdown, module này dịch sang mô hình đó. Đổi BMAD sang công cụ khác chỉ
cần viết bộ dịch mới, phần điều phối và cổng không đụng tới.

Hình dạng tài liệu quan sát từ PRD thật do BMAD sinh (spike S6, fixture
`tests/fixtures/bmad/prd.md`), không suy đoán:

* yêu cầu chức năng: ``#### FR-1: Tiêu đề`` rồi mô tả, rồi mục
  ``**Consequences (testable):**`` — chính là tiêu chí chấp nhận, đã viết
  sẵn ở dạng kiểm chứng được;
* yêu cầu phi chức năng: ``- **NFR-1 — Tiêu đề.** mô tả``;
* giả định: đánh dấu ``[ASSUMPTION: …]`` ngay tại chỗ phát sinh;
* câu hỏi mở: ``OQ-n``, kèm phạm vi ảnh hưởng khi có.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

#: `#### FR-1: Tạo ghi chú`
_FR_HEADING = re.compile(r"^#{2,5}\s+(FR-\d+)\s*[:：]\s*(.+?)\s*$", re.MULTILINE)

#: `- **NFR-1 — Thời gian mở ứng dụng.** Từ lúc…`
_NFR_ITEM = re.compile(
    r"^[-*]\s+\*\*(NFR-\d+)\s*[—–-]\s*(.+?)\.?\*\*\s*(.*)$", re.MULTILINE
)

_CONSEQUENCES = re.compile(
    r"\*\*Consequences \(testable\)\s*[:：]\*\*\s*\n(.*?)(?=\n#{2,5}\s|\n\*\*|\Z)",
    re.DOTALL,
)
_BULLET = re.compile(r"^[-*]\s+(.+?)\s*$", re.MULTILINE)

_ASSUMPTION = re.compile(r"\[ASSUMPTION:\s*(.+?)\]", re.DOTALL)
_OQ_MENTION = re.compile(r"\b(OQ-\d+)\b")
#: `**OQ-1 (chặn FR-13..FR-15)** — …`
_OQ_DEFINITION = re.compile(
    r"\*\*(OQ-\d+)\s*(?:\(([^)]*)\))?\*\*\s*[—–-]\s*(.+?)(?=\n\d+\.\s|\n\n|\Z)",
    re.DOTALL,
)
_FR_RANGE = re.compile(r"FR-(\d+)\s*\.\.\s*FR-(\d+)")
_FR_SINGLE = re.compile(r"\bFR-(\d+)\b")


@dataclass
class Requirement:
    id: str
    kind: str  # "functional" | "non_functional"
    title: str
    description: str = ""
    #: Hệ quả kiểm chứng được — dùng thẳng làm tiêu chí chấp nhận của story.
    acceptance_criteria: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    @property
    def is_testable(self) -> bool:
        """Yêu cầu không có tiêu chí kiểm chứng được thì không thể nghiệm thu."""
        return bool(self.acceptance_criteria)


@dataclass
class OpenQuestion:
    id: str
    text: str
    #: Yêu cầu bị chặn cho tới khi câu hỏi này được trả lời.
    blocks: list[str] = field(default_factory=list)


@dataclass
class PRD:
    requirements: list[Requirement] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    open_questions: list[OpenQuestion] = field(default_factory=list)

    def functional(self) -> list[Requirement]:
        return [r for r in self.requirements if r.kind == "functional"]

    def non_functional(self) -> list[Requirement]:
        return [r for r in self.requirements if r.kind == "non_functional"]

    def by_id(self, req_id: str) -> Requirement | None:
        return next((r for r in self.requirements if r.id == req_id), None)

    def blocked_ids(self) -> set[str]:
        """Yêu cầu đang bị câu hỏi mở chặn — không được đưa vào story."""
        blocked: set[str] = set()
        for oq in self.open_questions:
            blocked |= set(oq.blocks)
        return blocked

    def untestable(self) -> list[Requirement]:
        return [r for r in self.functional() if not r.is_testable]

    def as_dict(self) -> dict:
        return {
            "requirements": [
                {
                    "id": r.id,
                    "kind": r.kind,
                    "title": r.title,
                    "description": r.description,
                    "acceptance_criteria": r.acceptance_criteria,
                    "open_questions": r.open_questions,
                }
                for r in self.requirements
            ],
            "assumptions": self.assumptions,
            "open_questions": [
                {"id": q.id, "text": q.text, "blocks": q.blocks}
                for q in self.open_questions
            ],
        }


def _expand_fr_refs(text: str) -> list[str]:
    """`FR-13..FR-15` → [FR-13, FR-14, FR-15]; kèm cả tham chiếu lẻ."""
    ids: list[str] = []
    consumed = text
    for m in _FR_RANGE.finditer(text):
        start, end = int(m.group(1)), int(m.group(2))
        if start <= end and end - start < 100:
            ids.extend(f"FR-{n}" for n in range(start, end + 1))
            consumed = consumed.replace(m.group(0), " ")
        # Dải ngược hoặc quá rộng là lỗi viết. Không mở rộng, nhưng cũng
        # không xoá khỏi văn bản — hai mã ở hai đầu vẫn được nhặt như tham
        # chiếu lẻ. Chặn thừa một yêu cầu an toàn hơn bỏ sót cả hai.
    ids.extend(f"FR-{m.group(1)}" for m in _FR_SINGLE.finditer(consumed))
    return sorted(set(ids), key=lambda s: int(s.split("-")[1]))


def _section_for(text: str, start: int, next_start: int | None) -> str:
    return text[start : next_start if next_start is not None else len(text)]


def parse_prd(text: str) -> PRD:
    """Đọc PRD của BMAD thành mô hình của framework."""
    prd = PRD()

    fr_matches = list(_FR_HEADING.finditer(text))
    for i, m in enumerate(fr_matches):
        body = _section_for(
            text, m.end(), fr_matches[i + 1].start() if i + 1 < len(fr_matches) else None
        )

        criteria: list[str] = []
        cons = _CONSEQUENCES.search(body)
        if cons:
            criteria = [b.group(1).strip() for b in _BULLET.finditer(cons.group(1))]

        description = body[: cons.start()] if cons else body
        description = _ASSUMPTION.sub("", description)

        prd.requirements.append(
            Requirement(
                id=m.group(1),
                kind="functional",
                title=m.group(2).strip(),
                description=" ".join(description.split())[:600],
                acceptance_criteria=criteria,
                open_questions=sorted(set(_OQ_MENTION.findall(body))),
            )
        )

    for m in _NFR_ITEM.finditer(text):
        prd.requirements.append(
            Requirement(
                id=m.group(1),
                kind="non_functional",
                title=m.group(2).strip(),
                description=" ".join(_ASSUMPTION.sub("", m.group(3)).split())[:600],
                open_questions=sorted(set(_OQ_MENTION.findall(m.group(0)))),
            )
        )

    seen_assumptions: set[str] = set()
    for m in _ASSUMPTION.finditer(text):
        a = " ".join(m.group(1).split())
        if a not in seen_assumptions:
            seen_assumptions.add(a)
            prd.assumptions.append(a)

    seen_oq: set[str] = set()
    for m in _OQ_DEFINITION.finditer(text):
        oq_id = m.group(1)
        if oq_id in seen_oq:
            continue
        seen_oq.add(oq_id)
        prd.open_questions.append(
            OpenQuestion(
                id=oq_id,
                text=" ".join(m.group(3).split())[:400],
                blocks=_expand_fr_refs(m.group(2) or ""),
            )
        )

    return prd


def parse_prd_file(path: Path | str) -> PRD:
    return parse_prd(Path(path).read_text(encoding="utf-8", errors="replace"))
