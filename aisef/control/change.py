"""Post-release change lifecycle (S4): `aisef change FR-x "description"`.

Which layers go stale when a change is requested? Not everything -- and not
just code. This entry point does exactly three things; the rest is handled by
existing mechanisms:

1. Record the change in `docs/requirements.md` (the project's single source
   of input) and mark `_bmad-output/prd.md` -- the hash changes so the PRD
   gate becomes `stale`, and all downstream gates cascade (via `approvals`).
2. Generate a **delta story** `STORY-CH-<n>` in `EPIC-CH`, `covers=[FR-x]`,
   acceptance criteria from the description; `write_scope` left blank -- the
   machine gate blocks until a human declares it, same as any normal story.
3. Keep old stories `DONE`. History is not rewritten; the change is new work.
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
EPIC_TITLE = "Post-release changes"
_FR = re.compile(r"^(FR|NFR)-\d+$")


@dataclass
class ChangeResult:
    story_id: str
    story_file: Path
    requirement: str
    prd_marked: bool
    next_steps: list[str]


def _brownfield_note(project: Path) -> str:
    baseline = project / "_bmad-output" / "baseline.md"
    if not baseline.is_file():
        return ""
    return (
        "\n\n## Brownfield\n\n"
        "This project has existing source code (see `_bmad-output/baseline.md`). "
        "Preserve existing architecture and valid behaviour. Code is ground truth.\n"
    )


def apply(project: Path, requirement: str, description: str, *, today: date | None = None) -> ChangeResult:
    project = Path(project)
    root = project / "_bmad-output"
    if not _FR.match(requirement):
        raise ValueError(f"requirement id must be FR-n or NFR-n, got `{requirement}`")
    if not description.strip():
        raise ValueError("change description must not be empty")
    ngay = (today or date.today()).isoformat()

    # 1. record input + mark PRD
    req = project / "docs" / "requirements.md"
    req.parent.mkdir(parents=True, exist_ok=True)
    with req.open("a", encoding="utf-8") as f:
        f.write(f"\n## {requirement} — change {ngay}\n{description.strip()}\n")
    prd = root / "prd.md"
    prd_marked = False
    if prd.is_file():
        with prd.open("a", encoding="utf-8") as f:
            f.write(f"\n> **Change {ngay} — {requirement}:** {description.strip()} "
                    f"(recorded by `aisef change`; PRD gate needs re-approval)\n")
        prd_marked = True

    # 2. delta story
    n = 1 + sum(1 for s in read_index(root).get("stories", [])
                if str(s.get("id", "")).startswith("STORY-CH-"))
    sid = f"STORY-CH-{n:02d}"
    story = Story(id=sid, epic_id=EPIC_ID, title=description.strip().split("\n")[0][:80],
                  acceptance_criteria=[description.strip()], covers=[requirement],
                  verification_contract=["unit"])
    body = _brownfield_note(project)
    path = register_story(root, story, epic_title=EPIC_TITLE, body=body)

    steps = [
        f"declare `write_scope` for {sid} in `{path.relative_to(project)}` and the index",
        "re-approve the `prd` gate (and all downstream gates) — they are now stale",
        f"run `aisef run --epic {EPIC_ID}`",
    ]
    if (root / "baseline.md").is_file():
        steps.insert(0, "blast-radius will run automatically during implement (requires write_scope)")
    return ChangeResult(sid, path, requirement, prd_marked, steps)


def read_index(root: Path) -> dict:
    """`stories.index.json`, or an empty skeleton if stories haven't been split yet."""
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
    """Register a **generated** story (post-release change or improvement-loop
    repair): write the story file, insert into `stories.index.json` in the
    format `story_split` produces so `run_epic` can read it, and register in
    the state store.

    If the story already exists in the index, its record is replaced --
    the improvement loop may re-run an unfinished repair story. `extra`
    holds keys beyond `Story.as_dict()` (`repair_of`, `loop`,
    `preservation`); `body` is appended to the story file. `wave`: the
    epic wave containing only these stories (improvement loop runs exactly
    one story per round); omit to append a new `[story]` wave.
    """
    from ..phases.story_split import render_story, story_file

    root = Path(root)
    idx = read_index(root)
    epics = idx.setdefault("epics", [])
    if not any(e.get("id") == story.epic_id for e in epics):
        epics.append({"id": story.epic_id, "title": epic_title})

    text = render_story(story, None)
    if body:
        # Insert before the "auto-generated from epics.md" footer: the added
        # content is story body, not a post-footer note.
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
