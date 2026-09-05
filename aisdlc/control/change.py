"""Vòng đời thay đổi sau phát hành (S4): `aisdlc change FR-x "mô tả"`.

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
                    f"(ghi bởi `aisdlc change`; cổng PRD cần duyệt lại)\n")
        prd_marked = True

    # 2. story delta
    idx_path = root / "stories.index.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.is_file() else {"version": 1, "epics": [], "stories": [], "waves": {}}
    n = 1 + sum(1 for s in idx.get("stories", []) if str(s.get("id", "")).startswith("STORY-CH-"))
    sid = f"STORY-CH-{n:02d}"
    story = Story(id=sid, epic_id=EPIC_ID, title=description.strip().split("\n")[0][:80],
                  acceptance_criteria=[description.strip()], covers=[requirement],
                  verification_contract=["unit"])
    if not any(e.get("id") == EPIC_ID for e in idx.setdefault("epics", [])):
        idx["epics"].append({"id": EPIC_ID, "title": EPIC_TITLE})
    from ..phases.story_split import render_story, story_file
    path = story_file(root, story)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_story(story, None), encoding="utf-8")
    idx.setdefault("stories", []).append(story.as_dict() | {"file": str(path.relative_to(root))})
    idx.setdefault("waves", {}).setdefault(EPIC_ID, []).append([sid])
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    StateStore(root).register(sid, EPIC_ID, wave=len(idx["waves"][EPIC_ID]))

    return ChangeResult(sid, path, requirement, prd_marked, [
        f"khai `write_scope` cho {sid} trong `{path.relative_to(project)}` và chỉ mục",
        "duyệt lại cổng `prd` (và các cổng sau) — chúng đã thành stale",
        f"chạy `aisdlc run --epic {EPIC_ID}`",
    ])
