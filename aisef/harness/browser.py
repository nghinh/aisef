"""Run a real browser to render mockups and extract the visual contract.

Playwright is an **optional dependency**: when missing the framework says so
explicitly instead of pretending it can still verify. Same principle as
sandbox — better to report a lower assurance level than silently run as if
everything is in place (invariant 10).

One browser launch handles the full list of screens: restarting chromium per
screen costs several seconds each, and a project can have dozens of screens.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "assets" / "render.mjs"

#: Directories to search for `node_modules` containing playwright, in priority order.
def _node_paths(project: Path) -> list[Path]:
    """Every `node_modules` from ``project`` upward — the way node resolves
    modules, and the reason `npm test` works in a story worktree.

    Stories run in `<project>/.aisef/worktrees/<id>`, a fresh checkout with no
    `node_modules` of its own. Looking only at that one directory reports
    "playwright not installed" for a project that has it installed, and mockup
    verification then records `unavailable` instead of comparing anything —
    todo/STORY-01-01 ran three attempts with that check silently empty.
    """
    repo = Path(__file__).resolve().parent.parent.parent
    project = project.resolve()
    return [*(d / "node_modules" for d in (project, *project.parents)),
            repo / "spike" / "s7" / "node_modules"]


@dataclass
class RenderedScreen:
    id: str
    html: str = ""
    url: str = ""
    png: str = ""
    route: str = ""
    title: str = ""
    snapshot: str = ""
    #: Snapshot of each `[data-sample]` region — example content, not a
    #: commitment. Excluded from the contract so the gate doesn't fail on differing data.
    sample_snapshots: list[str] = field(default_factory=list)
    #: Annotation regions of the mockup document itself — not a commitment.
    annotation_snapshots: list[str] = field(default_factory=list)
    #: Snapshot of the **primary** state. Empty when the mockup declares no
    #: `data-state`; in that case the contract covers the whole page.
    primary_snapshot: str = ""
    declared_states: list[str] = field(default_factory=list)
    fields: list[dict] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


@dataclass
class RenderResult:
    screens: list[RenderedScreen] = field(default_factory=list)
    #: Nothing could be rendered at all — node missing, playwright missing,
    #: chromium won't launch. Distinct from "rendered but the page errored".
    unavailable: str = ""

    @property
    def ok(self) -> bool:
        return not self.unavailable and all(s.ok for s in self.screens)

    def by_id(self, screen_id: str) -> RenderedScreen | None:
        return next((s for s in self.screens if s.id == screen_id), None)


def find_playwright(project: Path | str = ".") -> Path | None:
    """Return the `node_modules` directory containing playwright, if found."""
    for base in _node_paths(Path(project)):
        if (base / "playwright" / "package.json").is_file():
            return base
    return None


def availability(project: Path | str = ".") -> str:
    """Empty string if rendering is possible; otherwise the reason it is not."""
    if not shutil.which("node"):
        return "node not installed — cannot render mockup to extract contract"
    if find_playwright(project) is None:
        return (
            "playwright not installed — run: npm i -D playwright && npx playwright install chromium"
        )
    return ""


def render(
    jobs: list[dict],
    *,
    project: Path | str = ".",
    viewport: tuple[int, int] = (1280, 900),
    timeout: int = 300,
) -> RenderResult:
    """Render each HTML file; return snapshots + metadata (and screenshots)."""
    project = Path(project)
    reason = availability(project)
    if reason:
        return RenderResult(unavailable=reason)

    node_modules = find_playwright(project)
    payload = json.dumps({
        "jobs": jobs,
        "viewport": {"width": viewport[0], "height": viewport[1]},
        "playwright": str(node_modules),
    })

    try:
        proc = subprocess.run(
            ["node", str(SCRIPT)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return RenderResult(unavailable=f"mockup rendering exceeded {timeout}s")

    if proc.returncode != 0 and not proc.stdout.strip():
        return RenderResult(unavailable=(proc.stderr or "node failed").strip()[:400])

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return RenderResult(unavailable=f"cannot parse node output: {proc.stdout[:200]}")

    if data.get("error"):
        return RenderResult(unavailable=data["error"])

    result = RenderResult()
    for raw in data.get("screens", []):
        result.screens.append(
            RenderedScreen(
                id=raw.get("id", ""),
                html=raw.get("html", ""),
                url=raw.get("url", ""),
                png=raw.get("png", ""),
                route=raw.get("route", ""),
                title=raw.get("title", ""),
                snapshot=raw.get("snapshot", ""),
                sample_snapshots=raw.get("sample_snapshots", []) or [],
                annotation_snapshots=raw.get("annotation_snapshots", []) or [],
                primary_snapshot=raw.get("primary_snapshot", "") or "",
                declared_states=raw.get("declared_states", []) or [],
                fields=raw.get("fields", []),
                unresolved=raw.get("unresolved", []),
                console_errors=raw.get("console_errors", []),
                error=raw.get("error", ""),
            )
        )
    return result
