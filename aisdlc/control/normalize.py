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


# ----------------------------------------------------------------- epics.md

#: `## Epic 1: Nền tảng ghi chú`
_EPIC_HEADING = re.compile(r"^##\s+Epic\s+(\d+)\s*[:：]\s*(.+?)\s*$", re.MULTILINE)
#: `### Story 1.2: Sửa ghi chú` — khuôn cố định trong template BMAD.
_STORY_HEADING = re.compile(
    r"^###\s+Story\s+(\d+)\.(\d+)\s*[:：]\s*(.+?)\s*$", re.MULTILINE
)
#: Khối tiêu chí chấp nhận kết thúc ở tiêu đề mới hoặc một **nhãn in đậm**
#: khác — nhưng *không* ở `**When**`/`**Then**`/`**And**`, vốn là thân của
#: chính tiêu chí. Cắt nhầm ở đó thì mỗi story chỉ còn một tiêu chí cụt.
_AC_BLOCK = re.compile(
    r"\*\*Acceptance Criteria\s*[:：]?\*\*\s*\n(.*?)"
    r"(?=\n#{2,4}\s|\n\s*\*\*(?!Given|When|Then|And)[^\n*]+\*\*\s*[:：]?\s*\n|\Z)",
    re.DOTALL,
)
_GIVEN = re.compile(r"^\s*\*\*Given\*\*", re.IGNORECASE)
#: `- write_scope: src/notes/, src/db/schema.ts` — kể cả khi in đậm nhãn.
_META_ITEM = re.compile(
    r"^[-*]?\s*\*{0,2}(covers|write[_ ]scope|depends[_ ]on)\*{0,2}\s*[:：]\s*(.+?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_STORY_REF = re.compile(r"\b(\d+)\.(\d+)\b")
_ROLE_LINE = re.compile(
    r"^\s*(?:As an?|Tôi là)\s+(.+?),?\s*$\n"
    r"^\s*(?:I want|Tôi muốn)\s+(.+?),?\s*$\n"
    r"^\s*(?:So that|Để)\s+(.+?)\.?\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def epic_id(n: int | str) -> str:
    return f"EPIC-{int(n):02d}"


def story_id(epic: int | str, seq: int | str) -> str:
    return f"STORY-{int(epic):02d}-{int(seq):02d}"


@dataclass
class Story:
    """Một story đã chuẩn hoá — đơn vị công việc của một phiên agent."""

    id: str
    epic_id: str
    title: str
    as_a: str = ""
    i_want: str = ""
    so_that: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    #: Mã FR story này phủ. Cổng máy đối chiếu ngược với PRD.
    covers: list[str] = field(default_factory=list)
    #: Đường dẫn story được phép ghi. Guard chặn theo đúng danh sách này,
    #: và xung đột merge cuối đợt là bằng chứng nó khai sai.
    write_scope: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    body: str = ""

    @property
    def epic_seq(self) -> tuple[int, int]:
        parts = self.id.split("-")
        return int(parts[1]), int(parts[2])

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "epic_id": self.epic_id,
            "title": self.title,
            "as_a": self.as_a,
            "i_want": self.i_want,
            "so_that": self.so_that,
            "acceptance_criteria": self.acceptance_criteria,
            "covers": self.covers,
            "write_scope": self.write_scope,
            "depends_on": self.depends_on,
        }


@dataclass
class Epic:
    id: str
    title: str
    goal: str = ""
    stories: list[Story] = field(default_factory=list)


@dataclass
class EpicPlan:
    epics: list[Epic] = field(default_factory=list)
    #: FR → story, đọc từ mục "FR Coverage Map" nếu BMAD có sinh.
    coverage_map: dict[str, list[str]] = field(default_factory=dict)

    def stories(self) -> list[Story]:
        return [s for e in self.epics for s in e.stories]

    def by_id(self, sid: str) -> Story | None:
        return next((s for s in self.stories() if s.id == sid), None)


def _split_ac(block: str) -> list[str]:
    """Tách khối tiêu chí chấp nhận thành từng tiêu chí.

    Hai khuôn gặp trong thực tế: Given/When/Then nhiều dòng, và gạch đầu
    dòng. Given mở một tiêu chí mới; ngoài ra mỗi bullet là một tiêu chí.
    """
    items: list[str] = []
    current: list[str] = []

    for raw in block.splitlines():
        line = raw.strip()
        if not line or _META_ITEM.match(line):
            continue  # dòng siêu dữ liệu không phải tiêu chí
        if _GIVEN.match(line):
            if current:
                items.append(" ".join(current))
            current = [line]
        elif current:
            current.append(line)
        else:
            m = _BULLET.match(line)
            items.append(m.group(1) if m else line)
    if current:
        items.append(" ".join(current))

    cleaned = [" ".join(i.replace("**", "").split()) for i in items]
    return [c for c in cleaned if c]


def _split_list(text: str) -> list[str]:
    """`a, b · c` → ['a', 'b', 'c']. Bỏ dấu nháy và in đậm."""
    parts = re.split(r"[,;·]| và ", text)
    return [p.strip().strip("`\"'*") for p in parts if p.strip().strip("`\"'*")]


def _parse_story_meta(body: str, epic_n: int) -> dict[str, list[str]]:
    meta: dict[str, list[str]] = {}
    for m in _META_ITEM.finditer(body):
        key = m.group(1).lower().replace(" ", "_")
        values = _split_list(m.group(2))
        if key == "covers":
            meta["covers"] = _expand_fr_refs(m.group(2))
        elif key == "write_scope":
            meta["write_scope"] = [v for v in values if v.lower() not in ("none", "không")]
        elif key == "depends_on":
            meta["depends_on"] = _refs_to_story_ids(m.group(2), epic_n)
    return meta


def _refs_to_story_ids(text: str, default_epic: int) -> list[str]:
    """`1.1, 2.3` hoặc `STORY-01-01` → mã story chuẩn."""
    out = []
    for m in re.finditer(r"STORY-(\d+)-(\d+)", text, re.IGNORECASE):
        out.append(story_id(m.group(1), m.group(2)))
    for m in _STORY_REF.finditer(text):
        sid = story_id(m.group(1), m.group(2))
        if sid not in out:
            out.append(sid)
    return out


def _parse_coverage_map(text: str) -> dict[str, list[str]]:
    """Đọc mục "FR Coverage Map" — bảng hay gạch đầu dòng đều được.

    Mỗi dòng có ít nhất một mã FR và một số hiệu story thì tính là một
    dòng ánh xạ; không ép khuôn bảng, vì model trình bày mỗi lúc một khác.
    """
    m = re.search(r"^#{2,4}\s+FR Coverage Map\s*$", text, re.MULTILINE)
    if not m:
        return {}
    section = text[m.end():]
    end = re.search(r"^#{2,3}\s+\S", section, re.MULTILINE)
    if end:
        section = section[: end.start()]

    mapping: dict[str, list[str]] = {}
    for line in section.splitlines():
        frs = _expand_fr_refs(line)
        if not frs:
            continue
        refs = [story_id(a, b) for a, b in _STORY_REF.findall(line)]
        for fr in frs:
            mapping.setdefault(fr, [])
            for r in refs:
                if r not in mapping[fr]:
                    mapping[fr].append(r)
    return mapping


def parse_epics(text: str) -> EpicPlan:
    """`epics.md` của BMAD → epic và story đã chuẩn hoá."""
    plan = EpicPlan(coverage_map=_parse_coverage_map(text))

    epic_marks = list(_EPIC_HEADING.finditer(text))
    for i, em in enumerate(epic_marks):
        epic_n = int(em.group(1))
        end = epic_marks[i + 1].start() if i + 1 < len(epic_marks) else len(text)
        section = text[em.end():end]
        epic = Epic(id=epic_id(epic_n), title=em.group(2).strip())

        story_marks = list(_STORY_HEADING.finditer(section))
        epic.goal = " ".join(
            section[: story_marks[0].start() if story_marks else len(section)].split()
        )[:600]

        for j, sm in enumerate(story_marks):
            s_end = story_marks[j + 1].start() if j + 1 < len(story_marks) else len(section)
            body = section[sm.end():s_end]
            story = Story(
                id=story_id(epic_n, sm.group(2)),
                epic_id=epic.id,
                title=sm.group(3).strip(),
                body=body.strip(),
            )

            role = _ROLE_LINE.search(body)
            if role:
                story.as_a, story.i_want, story.so_that = (
                    " ".join(g.split()) for g in role.groups()
                )

            ac = _AC_BLOCK.search(body)
            if ac:
                story.acceptance_criteria = _split_ac(ac.group(1))

            meta = _parse_story_meta(body, epic_n)
            story.covers = meta.get("covers", [])
            story.write_scope = meta.get("write_scope", [])
            story.depends_on = [d for d in meta.get("depends_on", []) if d != story.id]

            epic.stories.append(story)
        plan.epics.append(epic)

    # Bản đồ phủ là nguồn dự phòng: story không tự khai `covers` thì lấy từ
    # đó, vì thiếu ánh xạ FR sẽ làm cổng máy chặn cả tập story.
    for fr, sids in plan.coverage_map.items():
        for sid in sids:
            st = plan.by_id(sid)
            if st and fr not in st.covers:
                st.covers.append(fr)

    return plan


def parse_epics_file(path: Path | str) -> EpicPlan:
    return parse_epics(Path(path).read_text(encoding="utf-8", errors="replace"))
