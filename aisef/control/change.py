"""Vòng đời thay đổi sau phát hành (S4): `aisef change FR-x "mô tả"`.

Một yêu cầu đổi thì tầng nào cũ đi? Không phải mọi thứ — và không phải chỉ
code. Lối vào có tên này làm đúng ba việc, còn lại để cơ chế sẵn có lo:

1. Ghi thay đổi vào `docs/requirements.md` (đầu vào duy nhất của dự án) và
   đánh dấu vào `_bmad-output/prd.md` — hash đổi nên cổng PRD tự thành
   `stale`, và mọi cổng sau nó cũng thế (cascade đã có ở `approvals`).
2. Sinh **story delta** `STORY-CH-<n>` trong `EPIC-CH`, `covers=[FR-x]`, tiêu
   chí là mô tả; `write_scope` để trống — cổng máy sẽ chặn tới khi người
   khai, đúng như story thường.
3. Giữ story cũ `DONE`. Lịch sử không bị viết lại; thay đổi là việc mới.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .normalize import Story
from .state import StateStore

EPIC_ID = "EPIC-CH"
EPIC_TITLE = "Thay đổi sau phát hành"
_FR = re.compile(r"^(FR|NFR)-\d+$")


@dataclass
class ChangeResult:
    story_id: str
    story_file: Path
    requirement: str
    prd_marked: bool
    next_steps: list[str]


def apply(project: Path, requirement: str, description: str, *, today: date | None = None) -> ChangeResult:
    project = Path(project)
    root = project / "_bmad-output"
    if not _FR.match(requirement):
        raise ValueError(f"mã yêu cầu phải dạng FR-n hoặc NFR-n, nhận `{requirement}`")
    if not description.strip():
        raise ValueError("mô tả thay đổi không được rỗng")
    ngay = (today or date.today()).isoformat()

    # 1. đầu vào + đánh dấu PRD
    req = project / "docs" / "requirements.md"
    req.parent.mkdir(parents=True, exist_ok=True)
    with req.open("a", encoding="utf-8") as f:
        f.write(f"\n## {requirement} — thay đổi {ngay}\n{description.strip()}\n")
    prd = root / "prd.md"
    prd_marked = False
    if prd.is_file():
        with prd.open("a", encoding="utf-8") as f:
            f.write(f"\n> **Thay đổi {ngay} — {requirement}:** {description.strip()} "
                    f"(ghi bởi `aisef change`; cổng PRD cần duyệt lại)\n")
        prd_marked = True

    # 2. story delta
    n = 1 + sum(1 for s in read_index(root).get("stories", [])
                if str(s.get("id", "")).startswith("STORY-CH-"))
    sid = f"STORY-CH-{n:02d}"
    story = Story(id=sid, epic_id=EPIC_ID, title=description.strip().split("\n")[0][:80],
                  acceptance_criteria=[description.strip()], covers=[requirement],
                  verification_contract=["unit"])
    path = register_story(root, story, epic_title=EPIC_TITLE)

    return ChangeResult(sid, path, requirement, prd_marked, [
        f"khai `write_scope` cho {sid} trong `{path.relative_to(project)}` và chỉ mục",
        "duyệt lại cổng `prd` (và các cổng sau) — chúng đã thành stale",
        f"chạy `aisef run --epic {EPIC_ID}`",
    ])


def read_index(root: Path) -> dict:
    """`stories.index.json`, hoặc bộ khung rỗng khi dự án chưa tách story."""
    idx_path = Path(root) / "stories.index.json"
    if not idx_path.is_file():
        return {"version": 1, "epics": [], "stories": [], "waves": {}}
    return json.loads(idx_path.read_text(encoding="utf-8"))


def register_story(
    root: Path,
    story: Story,
    *,
    epic_title: str,
    extra: dict | None = None,
    body: str = "",
    wave: list[str] | None = None,
) -> Path:
    """Story **phát sinh** (thay đổi sau phát hành, story sửa của vòng cải
    tiến): ghi tệp story, đưa vào `stories.index.json` đúng định dạng
    `story_split` để `run_epic` đọc được, và đăng ký sổ trạng thái.

    Story đã có trong chỉ mục thì thay bản ghi — vòng cải tiến chạy lại
    một story sửa chưa xong. `extra` là các khoá ngoài `Story.as_dict()`
    (`repair_of`, `loop`, `preservation`); `body` nối vào cuối tệp story.
    `wave`: đợt của epic chỉ gồm những story này (vòng cải tiến chạy đúng
    một story mỗi vòng); không truyền thì nối thêm một đợt `[story]`.
    """
    from ..phases.story_split import render_story, story_file

    root = Path(root)
    idx = read_index(root)
    epics = idx.setdefault("epics", [])
    if not any(e.get("id") == story.epic_id for e in epics):
        epics.append({"id": story.epic_id, "title": epic_title})

    text = render_story(story, None)
    if body:
        # Trước dòng chân "sinh tự động từ epics.md": phần thêm là nội dung
        # story, không phải ghi chú sau chân trang.
        head, sep, tail = text.rpartition("\n---\n")
        text = head + body + sep + tail if sep else text + body
    path = story_file(root, story)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    rec = story.as_dict() | {"file": str(path.relative_to(root))} | (extra or {})
    stories = idx.setdefault("stories", [])
    pos = next((i for i, s in enumerate(stories) if s.get("id") == story.id), None)
    if pos is None:
        stories.append(rec)
    else:
        stories[pos] = rec
    waves = idx.setdefault("waves", {})
    if wave is not None:
        waves[story.epic_id] = [list(wave)]
    else:
        waves.setdefault(story.epic_id, []).append([story.id])
    (root / "stories.index.json").write_text(
        json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    StateStore(root).register(story.id, story.epic_id, wave=len(waves[story.epic_id]))
    return path
