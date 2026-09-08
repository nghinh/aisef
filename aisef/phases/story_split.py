"""Split `epics.md` into **one file per story** + a machine-readable index.

A story is the unit of work for a single agent session (decision D1), so it
must be self-contained: the agent opens exactly one file and finds everything
it needs — acceptance criteria, declared scope, story dependencies, and the
**verbatim FR text** it must satisfy. Forcing the agent to re-filter a 33KB
PRD each turn wastes money and lets it decide what matters.

The `stories.index.json` index is the contract for the orchestrator: the wave
scheduler, machine gate, and status board all read from here, not markdown.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..config import DEFAULTS, Config
from ..control.acceptance import ac_code
from ..control.approvals import STORIES_INDEX
from ..control.machine_gate import GateResult, check_stories
from ..control.preflight import (
    STORY_NOT_EXECUTABLE,
    check_stories_executable,
    verification_contract,
)
from ..control.normalize import (
    EpicPlan,
    PRD,
    Story,
    parse_epics_file,
    parse_prd_file,
    verification_paths,
)
from ..control.scheduler import CycleError, UnknownDependencyError
from ..control.scheduler import Story as SchedStory
from ..control.scheduler import plan_epics

#: Most recent stories gate result — fed into the next epics prompt (P2-12).
GATE_MEMO = "stories.gate.json"

STORIES_DIR = "stories"


@dataclass
class SplitResult:
    plan: EpicPlan | None = None
    files: list[Path] = field(default_factory=list)
    removed: list[Path] = field(default_factory=list)
    index_path: Path | None = None
    gate: GateResult | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        if self.error:
            return False
        return bool(self.gate and self.gate.passed)

    @property
    def stories(self) -> list[Story]:
        return self.plan.stories() if self.plan else []

    def summary(self) -> str:
        if self.error:
            return f"split stories: ✗ {self.error}"
        n_epics = len(self.plan.epics) if self.plan else 0
        lines = [f"split stories: {len(self.stories)} stories / {n_epics} epics"]
        if self.removed:
            lines.append(f"  removed {len(self.removed)} story file(s) no longer in epics.md")
        if self.gate:
            lines.append(self.gate.summary())
        return "\n".join(lines)


def to_scheduler(stories: list[Story]) -> list[SchedStory]:
    """Convert to scheduler model (keeping only fields needed for wave assignment)."""
    return [
        SchedStory(
            id=s.id,
            epic_id=s.epic_id,
            title=s.title,
            depends_on=tuple(s.depends_on),
            write_scope=tuple(s.write_scope),
        )
        for s in stories
    ]


def render_story(story: Story, prd: PRD | None, root: Path | None = None) -> str:
    """Render story file content — the contract an agent reads before writing code."""
    out = [f"# {story.id}: {story.title}", ""]

    if story.as_a:
        out += [
            f"**As a** {story.as_a}",
            f"**I want** {story.i_want}",
            f"**so that** {story.so_that}",
            "",
        ]

    out += ["## Acceptance Criteria", ""]
    out += [f"{i}. [{ac_code(story.id, i)}] {ac}" for i, ac in enumerate(story.acceptance_criteria, 1)] or [
        "_(none — machine gate will block)_"
    ]
    out.append("")

    out += ["## Recorded Scope", ""]
    if story.write_scope:
        out += [f"- `{p}`" for p in story.write_scope]
        them = verification_paths(story, root.parent) if root is not None else []
        if them:
            out += ["", "Harness added because the story's verification contract requires them (error 21):"]
            out += [f"- `{p}`" for p in them]
        out += [
            "",
            "Guard blocks all writes outside this list. Needing to write elsewhere "
            "means the scope declaration is wrong — stop and report, do not work around it.",
        ]
    else:
        out.append("_(not declared — machine gate will block)_")
    out.append("")

    hop_dong = verification_contract(story)
    if hop_dong:
        out += [
            "## Definition of Done",
            "",
            "This story must pass the following verification types. Types not configured "
            "on the project are **not** counted as passing — they are gaps, and "
            "the gate will flag them.",
            "",
        ]
        out += [f"- `{k}`" for k in hop_dong]
        out.append("")

    if story.depends_on:
        out += ["## Dependencies", ""] + [f"- {d}" for d in story.depends_on] + [""]

    out += ["## Requirements", ""]
    if not story.covers:
        out.append("_(no FR mapped — machine gate will block)_")
    for fr_id in story.covers:
        req = prd.by_id(fr_id) if prd else None
        if req is None:
            out.append(f"### {fr_id}")
            out.append("_(not found in PRD)_")
            out.append("")
            continue
        out += [f"### {req.id}: {req.title}", ""]
        if req.description:
            out += [req.description.strip(), ""]
        if req.acceptance_criteria:
            out += ["Verifiable Consequences:", ""]
            out += [f"- {c}" for c in req.acceptance_criteria]
            out.append("")

    out += [
        "---",
        "",
        f"_Auto-generated from `epics.md`. Edits here will be lost on next split — "
        f"edit `epics.md` and run `aisef plan`._",
        "",
    ]
    return "\n".join(out)


def story_file(root: Path, story: Story) -> Path:
    return root / STORIES_DIR / story.epic_id / f"{story.id}.md"


def _prune(root: Path, keep: set[Path]) -> list[Path]:
    """Remove story files no longer present in `epics.md`.

    Missing one means a deleted story lingers on disk and gets picked up as
    real work in the next cycle.
    """
    base = root / STORIES_DIR
    if not base.is_dir():
        return []
    removed = []
    for p in sorted(base.rglob("STORY-*.md")):
        if p not in keep:
            p.unlink()
            removed.append(p)
    for d in sorted(base.glob("EPIC-*")):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    return removed


def split(
    artifact_root: Path | str,
    *,
    config: Config | None = None,
) -> SplitResult:
    """Read `epics.md`, write one file per story plus the index, then run the machine gate."""
    root = Path(artifact_root)
    res = SplitResult()

    epics_md = root / "epics.md"
    if not epics_md.is_file():
        res.error = "epics.md not found"
        return res

    res.plan = parse_epics_file(epics_md)
    stories = res.plan.stories()
    if not stories:
        res.error = "no readable stories found in epics.md"
        return res

    prd_path = root / "prd.md"
    prd = parse_prd_file(prd_path) if prd_path.is_file() else None

    written: set[Path] = set()
    # Lock verification contracts before writing: the index and story files must
    # agree, and the orchestrator reads the index.
    for story in stories:
        if not story.verification_contract:
            story.verification_contract = verification_contract(story)

    for story in stories:
        path = story_file(root, story)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_story(story, prd, root), encoding="utf-8")
        written.add(path)
    res.files = sorted(written)
    res.removed = _prune(root, written)

    res.gate = check_stories(
        to_scheduler(stories),
        prd,
        config=config,
        story_fr_map={s.id: s.covers for s in stories},
        story_ac_count={s.id: len(s.acceptance_criteria) for s in stories},
    )

    # Is the story executable — computed in code, before spending any money.
    # Checked here rather than in `check_stories`: the check needs acceptance
    # criteria and screen lists, which the scheduler layer does not carry.
    splits: dict[str, str] = {}
    for pf in check_stories_executable(stories, project=root.parent, config=config):
        for m in pf.story_defects:
            if m.capability == "size" and m.remedy:
                splits[pf.story_id] = m.remedy
        if pf.story_defects:
            res.gate.errors.append(
                f"{STORY_NOT_EXECUTABLE} {pf.story_id}: "
                + "; ".join(m.line() for m in pf.story_defects)
            )
        if pf.provisioning_gaps:
            # Not blocking: the mockup phase and tool provisioning both happen
            # **after** this gate. Blocking here would force fixing things that
            # aren't due yet. The `readiness` gate and the pre-model-call step
            # are the real blockers.
            res.gate.warnings.append(
                f"{pf.story_id} missing prerequisites to run: "
                + "; ".join(m.line() for m in pf.provisioning_gaps)
            )

    res.index_path = write_index(root, res, config)
    # Persisted so the next `plan` run feeds it into the epics prompt: stories
    # blocked for being too large must be split by the planning agent, and it
    # can only split correctly when it knows what the gate said (P2-12).
    # `splits`: **deterministic** split instructions per oversized story
    # (ADR-004 R5) — separated out so the next epics step reads them directly
    # instead of parsing error messages.
    (root / GATE_MEMO).write_text(
        json.dumps({"errors": res.gate.errors, "warnings": res.gate.warnings,
                    "splits": splits},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return res


def write_index(root: Path, res: SplitResult, config: Config | None = None) -> Path:
    """Write `stories.index.json` — the contract for the orchestrator.

    Includes pre-computed parallel waves: this is a deterministic decision
    derived from dependencies and ``write_scope``, so it is locked in once
    here instead of letting each consumer recompute it differently.
    """
    sched = to_scheduler(res.stories)
    max_parallel = (config or Config(dict(DEFAULTS)))["run.max_parallel"]
    try:
        waves = {
            ep.epic_id: [[s.id for s in wave] for wave in ep.waves]
            for ep in plan_epics(sched, max_parallel=max_parallel)
        }
        wave_error = ""
    except (CycleError, UnknownDependencyError, ValueError) as e:
        # Broken dependency graph — machine gate already recorded the error;
        # also write it into the index so consumers don't have to guess why
        # there are no waves.
        waves, wave_error = {}, str(e)

    data = {
        "source": "epics.md",
        "epics": [
            {
                "id": e.id,
                "title": e.title,
                "goal": e.goal,
                "stories": [s.id for s in e.stories],
            }
            for e in (res.plan.epics if res.plan else [])
        ],
        "stories": [s.as_dict() | {"file": str(story_file(root, s).relative_to(root))}
                    for s in res.stories],
        "waves": waves,
        "gate": {
            "passed": bool(res.gate and res.gate.passed),
            "errors": res.gate.errors if res.gate else [],
            "warnings": res.gate.warnings if res.gate else [],
        },
    }
    if wave_error:
        data["gate"]["errors"] = list(data["gate"]["errors"]) + [f"wave assignment: {wave_error}"]

    path = root / STORIES_INDEX
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def describe_index(data: dict) -> str:
    """Summarize the index for a human reviewer.

    The story gate exists so a real person reviews the work breakdown. Dumping
    350 lines of JSON at them turns the gate into a rubber stamp — what they
    need to see is: which stories, which requirements covered, where they
    write, and what runs in parallel.
    """
    lines = []
    by_id = {s["id"]: s for s in data.get("stories", [])}
    waves = data.get("waves", {})

    for epic in data.get("epics", []):
        lines.append(f"\n{epic['id']}: {epic['title']}")
        for i, wave in enumerate(waves.get(epic["id"], []), 1):
            tag = f"  wave {i}" + (" (parallel)" if len(wave) > 1 else "")
            lines.append(tag)
            for sid in wave:
                s = by_id.get(sid, {})
                lines.append(
                    f"    {sid}  {s.get('title', '')}\n"
                    f"        covers: {', '.join(s.get('covers') or ['—'])}"
                    f"  ·  writes: {', '.join(s.get('write_scope') or ['—'])}"
                    f"  ·  {len(s.get('acceptance_criteria') or [])} criteria"
                )
        listed = {sid for w in waves.get(epic["id"], []) for sid in w}
        for sid in epic.get("stories", []):
            if sid not in listed:  # unschedulable — still must be visible
                lines.append(f"    {sid}  {by_id.get(sid, {}).get('title', '')}  [not assigned to any wave]")

    gate = data.get("gate", {})
    lines.append("")
    lines.append("machine gate: " + ("PASS" if gate.get("passed") else "FAIL"))
    for e in gate.get("errors", []):
        lines.append(f"  ✗ {e}")
    for w in gate.get("warnings", []):
        lines.append(f"  ⚠️  {w}")
    return "\n".join(lines)
