"""Map mockup — **loading half**: inject exactly one screen into the coding session.

The other half (`mockup_verify`) compares the real app against the contract.
Both halves must go together: loading without verification makes the mockup
merely a suggestion; verification without loading grades the agent against a
contract it never read.

The principle here is **load minimally**: a story building the List screen
must not see the Settings contract. Loading the entire file causes the agent
to build things outside its story — and that surplus is unordered, untested,
yet still requires maintenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..control.design_contract import DesignContract, ScreenContract

#: Max components listed in prompt before truncation. A contract hundreds of
#: lines long pushes the instructions out of the model's attention window.
MAX_LISTED = 40


@dataclass
class ScreenSlice:
    """A single-screen slice, ready to embed in a prompt."""

    screen: ScreenContract
    mockup_path: Path | None = None
    screenshot_path: Path | None = None
    html: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.screen.id

    def as_prompt(self) -> str:
        s = self.screen
        lines = [
            f"### Screen `{s.id}` — {s.name}",
            f"Route to build: `{s.route}`" if s.route else "Route: (contract not declared)",
        ]
        if s.purpose:
            lines.append(f"Purpose: {s.purpose}")
        # Gate convention must be stated explicitly, not left for the agent to guess
        # (bug 14, e9 note-editor 2026-09-05: gate opened `/note/1`, app had no
        # note `1`, blank page, story failed 2 rounds with no visible cause).
        from .mockup_verify import concrete_route

        if s.route and concrete_route(s.route) != s.route:
            lines.append(
                f"The mockup map gate will open `{concrete_route(s.route)}` (dynamic params "
                f"replaced with `1`). The dev environment (`app.dev_command`) must have a record "
                f"with id `1` for this route — seed data — otherwise the gate sees a blank "
                f"page and the story will not pass."
            )

        lines += ["", "**Required** components (role + name, exactly as in mockup):"]
        for c in s.components[:MAX_LISTED]:
            lines.append(f"- {c.role} “{c.name}”")
        if len(s.components) > MAX_LISTED:
            lines.append(f"- … and {len(s.components) - MAX_LISTED} more components (see mockup)")

        if s.data_roles:
            lines += [
                "",
                "Data region — must render from real data, each item is "
                f"{', '.join(s.data_roles)}. The contract does **not** bind "
                "content here (the real app displays different data), only "
                "the element type.",
            ]

        if s.fields:
            lines += ["", "Input constraints (enforce exactly, do not relax):"]
            for f in s.fields:
                bits = [f"type={f.get('type', '')}"]
                if f.get("required"):
                    bits.append("required")
                for key in ("pattern", "minlength", "maxlength", "min", "max"):
                    if f.get(key):
                        bits.append(f"{key}={f[key]}")
                label = f.get("label") or f.get("name") or "(no label)"
                lines.append(f"- {label}: {', '.join(bits)}")

        if s.states:
            lines += ["", "States to build: " + ", ".join(s.states)]

        if self.mockup_path:
            lines += ["", f"Mockup: `{self.mockup_path}`"]
        if self.screenshot_path:
            lines.append(f"Screenshot: `{self.screenshot_path}`")

        lines += [
            "",
            "The story gate compares the real app against the list above using the "
            "accessibility tree. Missing a committed component means **fail**; adding "
            "new components is only a warning. Names must match — that is what the "
            "user reads and what the machine compares.",
        ]
        return "\n".join(lines)


def load_slice(
    contract: DesignContract,
    screen_id: str,
    *,
    artifact_root: Path | str,
    with_html: bool = False,
) -> ScreenSlice | None:
    """Return the slice of **one** screen. None if the contract lacks it."""
    screen = contract.by_id(screen_id)
    if screen is None:
        return None

    root = Path(artifact_root)
    sl = ScreenSlice(screen=screen)

    if screen.mockup:
        path = root / screen.mockup
        if path.is_file():
            sl.mockup_path = path
            if with_html:
                sl.html = path.read_text(encoding="utf-8", errors="replace")
        else:
            sl.warnings.append(f"contract points to missing mockup: {screen.mockup}")

    if screen.screenshot:
        shot = root / screen.screenshot
        if shot.is_file():
            sl.screenshot_path = shot

    if not screen.components:
        sl.warnings.append(f"{screen_id}: contract has no components to compare")
    return sl


def load_for_story(
    contract: DesignContract,
    screen_ids: list[str],
    *,
    artifact_root: Path | str,
) -> tuple[list[ScreenSlice], list[str]]:
    """Load slices for the screens declared by the story. Returns unresolved IDs alongside."""
    slices, missing = [], []
    for sid in screen_ids:
        sl = load_slice(contract, sid, artifact_root=artifact_root)
        if sl is None:
            missing.append(sid)
        else:
            slices.append(sl)
    return slices, missing


def prompt_section(slices: list[ScreenSlice]) -> str:
    """The "UI" section of the story prompt."""
    if not slices:
        return (
            "This story does not build any screen. Do not add UI — the UI "
            "belongs to another story."
        )
    return "\n\n".join(s.as_prompt() for s in slices)
