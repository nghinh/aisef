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

from .experience import slugify

#: `#### FR-1: Tạo ghi chú`
_FR_HEADING = re.compile(r"^#{2,5}\s+(FR-\d+)\s*[:：]\s*(.+?)\s*$", re.MULTILINE)

#: `- **NFR-1 — Thời gian mở ứng dụng.** Từ lúc…`
_NFR_ITEM = re.compile(
    r"^[-*]\s+\*\*(NFR-\d+)\s*[—–-]\s*(.+?)\.?\*\*\s*(.*)$", re.MULTILINE
)
#: Section heading for NFR block — Vietnamese or English.
#: Used as fallback: auto-number unlabelled bullets when the heading is present
#: but the agent omitted NFR-N IDs.
_NFR_SECTION = re.compile(
    r"^#{2,5}\s+(?:Yêu cầu phi chức năng|Non-?functional\s+Requirements?)"
    r"\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_PLAIN_BULLET = re.compile(r"^[-*]\s+(.+?)\s*$", re.MULTILINE)

#: Tiêu đề khối tiêu chí — agent viết bằng tiếng Anh hoặc tiếng Việt tuỳ lượt
#: (lỗi 19, 2026-09-05: lượt `plan` thứ hai viết "Hệ quả kiểm chứng được" và
#: cổng PRD loại cả 14 FR vì parser chỉ biết "Consequences (testable)").
_CONSEQUENCES_HEAD = (
    r"(?:Consequences\s*\(testable\)|Testable consequences|Acceptance criteria"
    r"|Verification criteria|Verifiable consequences"
    r"|Hệ quả(?: kiểm chứng(?:\s+được)?|\s*\((?:kiểm chứng được|có thể kiểm chứng)\))"
    r"|Tiêu chí(?:\s+(?:kiểm chứng(?:\s+được)?|chấp nhận|xác nhận|nghiệm thu|kiểm tra)))"
)
_CONSEQUENCES = re.compile(
    r"\*\*" + _CONSEQUENCES_HEAD + r"\s*[:：]\*\*\s*\n(.*?)(?=\n#{2,5}\s|\n\*\*|\Z)",
    re.IGNORECASE |
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


#: Lockfile đi theo manifest của nó. Trình quản lý gói ghi lockfile như
#: **hệ quả** của mọi thay đổi phụ thuộc — khai manifest mà không khai
#: lockfile là khai nửa một cặp bất khả phân.
#:
#: Đo trên e9: TCCN 1 của STORY-01-01 đòi "lockfile được commit", nhưng
#: `write_scope` chỉ có `package.json`. Guard chặn ghi lockfile, agent làm
#: đúng chỉ dẫn — hoàn nguyên nó rồi báo phạm vi khai thiếu — người rà
#: soát chặn đúng vì TCCN 1 không đạt, và vòng lặp thử lại 4 lần y hệt
#: nhau, $9,85 cho một thế bí không lối ra.
#: Tệp khai phụ thuộc. Story nào cũng có thể cần thêm một gói — không cho
#: chạm thì nó bí, và cái bí ấy tốn cả hạn mức lượt thử mới lộ ra.
MANIFESTS = (
    "package.json", "pyproject.toml", "requirements.txt", "requirements.in",
    "Cargo.toml", "go.mod", "Gemfile", "composer.json",
)

LOCKFILES: dict[str, tuple[str, ...]] = {
    "package.json": ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb"),
    "pyproject.toml": ("poetry.lock", "uv.lock", "pdm.lock"),
    "requirements.in": ("requirements.txt",),
    "Cargo.toml": ("Cargo.lock",),
    "go.mod": ("go.sum",),
    "Gemfile": ("Gemfile.lock",),
    "composer.json": ("composer.lock",),
}


def effective_write_scope(story: Story, project: Path) -> list[str]:
    """Phạm vi ghi có hiệu lực: story khai, cộng tệp khai phụ thuộc.

    BMAD liệt kê tệp mã nguồn vào ``write_scope``; nó không nghĩ tới việc
    story sẽ phải khai một gói. Nhưng tiêu chí chấp nhận thì có — "test
    trên ``fake-indexeddb``", "lockfile được commit" — và lúc ấy story
    không thoả nổi tiêu chí của chính mình. Đo trên e9: hai story liên
    tiếp bí đúng vì chuyện này, $20 cho tám lượt không lượt nào qua.

    Chỉ thêm tệp **thật sự có** trong dự án: thêm bừa thì phạm vi rộng ra
    mà không đổi được gì, còn danh sách phạm vi in cho agent đọc thì dài
    thêm những dòng vô nghĩa.

    Cố ý **không** đụng tới phạm vi mà bộ lập lịch dùng để chia đợt: ở đó
    câu hỏi khác — hai story có giẫm chân nhau không — và nếu tính cả
    manifest thì mọi story đều giẫm nhau, chạy song song mất sạch.
    """
    scope = list(story.write_scope)
    for name in MANIFESTS:
        if name not in scope and (project / name).is_file():
            scope.append(name)
    for path in verification_paths(story, project):
        if path not in scope:
            scope.append(path)
    return with_lockfiles(scope)


#: Loại kiểm định → khoá cấu hình chứa lệnh chạy nó.
_VERIFY_COMMAND_KEY = {"unit": "tools.test"}


def verification_paths(story: Story, project: Path, config=None) -> list[str]:
    """Thư mục/tệp test mà **hợp đồng kiểm định của story** đòi — suy từ lệnh
    kiểm định của dự án (`verify.e2e` = `npx playwright test tests/e2e` →
    `tests/e2e`), chỉ lấy đường dẫn **có thật**.

    Lỗi 21 (e9 2026-09-05, hai story liên tiếp): story khai `e2e` và
    `accessibility` nhưng write_scope chỉ có `src/**`; guard chặn ghi
    `tests/`, người rà soát đánh dấu bế tắc kế hoạch, $30 cho hai story mà
    lỗi nằm ở chỗ harness *đòi* test rồi *cấm* viết test. Harness đòi gì
    thì tự cấp phạm vi cho cái đó.
    """
    kinds = [k.strip().lower() for k in (story.verification_contract or []) if k.strip()]
    if not kinds:
        return []
    if config is None:
        from ..config import Config

        try:
            config = Config.load(project)
        except Exception:  # noqa: BLE001 — không có config thì không suy gì
            return []
    out: list[str] = []
    for kind in kinds:
        key = _VERIFY_COMMAND_KEY.get(kind, f"verify.{kind}")
        try:
            cmd = str(config[key] or "")
        except KeyError:
            continue
        for tok in cmd.replace("'", " ").replace('"', " ").split():
            if tok.startswith("-") or "/" not in tok:
                continue
            rel = tok.strip("./").rstrip("/")
            if not rel or rel.startswith("..") or rel.startswith("node_modules"):
                continue
            if (project / rel).exists() and rel not in out:
                out.append(rel)
    return out


def is_lockfile(path: str) -> bool:
    """Đường dẫn này là lockfile do `with_lockfiles` thêm vào?

    Ngưỡng "story chạm quá nhiều nơi" đo **story tự khai to tới đâu**.
    Lockfile là hệ quả tự động của manifest, nên đếm chúng vào ngưỡng sẽ
    biến một bản vá đúng thành lỗi cổng.
    """
    name = path.rstrip("/").rsplit("/", 1)[-1]
    return any(name in locks for locks in LOCKFILES.values())


def with_lockfiles(scope: list[str]) -> list[str]:
    """Thêm lockfile của mọi manifest có trong phạm vi.

    Thêm **cả họ** lockfile của manifest đó chứ không đoán trình quản lý
    gói đang dùng: thừa một đường dẫn trong phạm vi không nới lỏng gì đáng
    kể — file không tồn tại thì không ai ghi được — còn đoán sai thì story
    lại bí đúng như cũ.
    """
    have = set(scope)
    out = list(scope)
    for path in scope:
        name = path.rstrip("/").rsplit("/", 1)[-1]
        prefix = path[: len(path) - len(name)]
        for lock in LOCKFILES.get(name, ()):
            if prefix + lock not in have:
                have.add(prefix + lock)
                out.append(prefix + lock)
    return out


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

    # Fallback: agent wrote NFR section but omitted NFR-N IDs — auto-number.
    if not prd.non_functional():
        sec = _NFR_SECTION.search(text)
        if sec:
            after = text[sec.end():]
            end = re.search(r"\n#{2,5}\s", after)
            block = after[: end.start()] if end else after
            for i, bm in enumerate(_PLAIN_BULLET.finditer(block), start=1):
                line = bm.group(1).strip()
                if not line or line.startswith("#"):
                    break
                parts = re.split(r"[—–-]\s+", line, maxsplit=1)
                title = parts[0].strip().strip("*").strip()
                desc = parts[1].strip() if len(parts) > 1 else ""
                prd.requirements.append(
                    Requirement(
                        id=f"NFR-{i}",
                        kind="non_functional",
                        title=title,
                        description=desc[:600],
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
    r"\*\*(?:Acceptance Criteria|Tiêu chí chấp nhận|Tiêu chí kiểm chứng"
    r"|Tiêu chí nghiệm thu)\s*[:：]?\*\*\s*\n(.*?)"
    r"(?=\n#{2,4}\s|\n\s*\*\*(?!Given|When|Then|And)[^\n*]+\*\*\s*[:：]?\s*\n|\Z)",
    re.DOTALL,
)
_GIVEN = re.compile(r"^\s*\*\*Given\*\*", re.IGNORECASE)
#: `- write_scope: src/notes/, src/db/schema.ts` — kể cả khi in đậm nhãn.
_META_ITEM = re.compile(
    r"^[-*]?\s*\*{0,2}(covers|write[_ ]scope|depends[_ ]on|screens?)\*{0,2}\s*[:：]\s*(.+?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_STORY_REF = re.compile(r"\b(\d+)\.(\d+)\b")
#: Dòng bản đồ phủ nói rõ **không** có story. Bỏ qua chúng: dòng thật của
#: BMAD là "FR-13 → KHÔNG CÓ STORY. … Khớp nối AR-18 ở Story 1.2", và nếu
#: chỉ nhìn "có mã FR + có số hiệu story" thì FR-13 bị gán cho story 1.2 —
#: rồi cổng máy chặn cả tập story vì một câu văn xuôi.
_NO_STORY = re.compile(
    r"(không có story|chưa có story|no story|ngoài phạm vi|out of scope|n/a)", re.I
)
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
    #: Màn hình story này dựng (mã trong EXPERIENCE.md). Rỗng = story không
    #: có giao diện; bước map mockup bỏ qua nó.
    screens: list[str] = field(default_factory=list)
    #: Loại kiểm định story này phải qua. Story tự khai thì lấy bản khai;
    #: không khai thì suy ra bằng code. Không phải một pha mới — chỉ là
    #: nói rõ "xong" nghĩa là gì cho **story này**, thay vì để mặc định
    #: chung cho mọi story.
    verification_contract: list[str] = field(default_factory=list)
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
            "verification_contract": self.verification_contract,
            "depends_on": self.depends_on,
            "screens": self.screens,
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
        elif key == "verification_contract":
            meta["verification_contract"] = [v.strip().lower() for v in values if v.strip()]
        elif key == "write_scope":
            meta["write_scope"] = [v for v in values if v.lower() not in ("none", "không")]
        elif key == "depends_on":
            meta["depends_on"] = _refs_to_story_ids(m.group(2), epic_n)
        elif key in ("screen", "screens"):
            meta["screens"] = [
                slugify(v) for v in values if v.lower() not in ("none", "không")
            ]
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
    m = re.search(r"^#{2,4}\s+(?:FR Coverage Map|Bản đồ phủ FR)\s*$", text, re.MULTILINE)
    if not m:
        return {}
    section = text[m.end():]
    end = re.search(r"^#{2,3}\s+\S", section, re.MULTILINE)
    if end:
        section = section[: end.start()]

    mapping: dict[str, list[str]] = {}
    for line in section.splitlines():
        frs = _expand_fr_refs(line)
        if not frs or _NO_STORY.search(line):
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
            story.write_scope = with_lockfiles(meta.get("write_scope", []))
            story.depends_on = [d for d in meta.get("depends_on", []) if d != story.id]
            story.screens = meta.get("screens", [])
            story.verification_contract = meta.get("verification_contract", [])

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


# ---------------------------------------------------------- architecture.md

#: `### AR-1 — Một đường ghi duy nhất`
_AR_HEADING = re.compile(r"^#{2,4}\s+(AR-\d+)\s*[—–:-]\s*(.+?)\s*$", re.MULTILINE)
_AR_FIELD = re.compile(r"^[-*]\s*\*\*(Binds|Prevents|Rule)\s*[:：]?\*\*\s*(.+)$", re.MULTILINE)


@dataclass
class Decision:
    """Một quyết định kiến trúc mà story phải tuân thủ."""

    id: str
    title: str
    #: Mã yêu cầu quyết định này ràng buộc — đây là cách chọn đúng quyết
    #: định cho một story mà không phải đoán.
    binds: list[str] = field(default_factory=list)
    #: Quyết định áp cho **mọi** story (`Binds: all`, hoặc không nêu ràng
    #: buộc nào). Đây là luật nền, không phải luật của một yêu cầu.
    universal: bool = False
    prevents: str = ""
    rule: str = ""
    text: str = ""

    def as_prompt(self) -> str:
        parts = [f"**{self.id} — {self.title}**"]
        if self.rule:
            parts.append(f"Rule: {self.rule}")
        if self.prevents:
            parts.append(f"Prevents: {self.prevents}")
        return "\n".join(parts)


@dataclass
class Architecture:
    decisions: list[Decision] = field(default_factory=list)

    def by_id(self, ar_id: str) -> Decision | None:
        return next((d for d in self.decisions if d.id == ar_id), None)

    def for_requirements(self, fr_ids: list[str]) -> list[Decision]:
        """Quyết định ràng buộc bất kỳ yêu cầu nào trong danh sách.

        Nhờ mục ``**Binds:**`` mà việc chọn ngữ cảnh cho story là **tra
        cứu**, không phải phán đoán: nạp cả tài liệu kiến trúc 26KB vào mỗi
        phiên vừa tốn vừa loãng, còn để agent tự chọn thì mỗi phiên chọn
        một kiểu.
        """
        want = set(fr_ids)
        return [d for d in self.decisions if d.universal or (want & set(d.binds))]


def parse_architecture(text: str) -> Architecture:
    arch = Architecture()
    marks = list(_AR_HEADING.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end():end]
        d = Decision(id=m.group(1), title=m.group(2).strip(), text=body.strip())
        seen_binds = False
        for f in _AR_FIELD.finditer(body):
            seen_binds = seen_binds or f.group(1).lower() == "binds"
            key, value = f.group(1).lower(), " ".join(f.group(2).split())
            if key == "binds":
                d.binds = _expand_fr_refs(value) + re.findall(r"\bAR-\d+\b", value)
                d.universal = bool(re.search(r"\b(all|mọi story|toàn bộ)\b", value, re.I))
            elif key == "prevents":
                d.prevents = value
            else:
                d.rule = value
        # Không nêu ràng buộc nào = luật nền, áp cho mọi story. Coi nó là
        # "không áp cho story nào" sẽ bỏ rơi đúng những luật quan trọng nhất.
        d.universal = d.universal or not seen_binds
        arch.decisions.append(d)
    return arch


def parse_architecture_file(path: Path | str) -> Architecture:
    return parse_architecture(Path(path).read_text(encoding="utf-8", errors="replace"))
