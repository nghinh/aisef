"""Visual contract -- the bridge between mockups and code.

A mockup is what people see; the contract is what the machine checks. It is
extracted from **mockups rendered in a real browser**, not by parsing HTML
with regex: what the user sees is the commitment; tags hidden by CSS are not.

Two consumers, and they are the reason this file exists:

* **mockup gate (phase 5)** -- every screen in EXPERIENCE.md must have a
  mockup, with no remaining self-declared unresolved items;
* **map-mockup step (phase 6.7a)** -- an agent writing a story may only load
  ``slice_for(screen_id)``: exactly one screen. Loading the full file would
  cause it to build things outside its story's scope.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..harness.aria import Component, parse_aria_snapshot
from .experience import Experience, Screen

CONTRACT_FILE = "design-contract.json"
CONTRACT_VERSION = 1


@dataclass
class ScreenContract:
    id: str
    name: str = ""
    route: str = ""
    purpose: str = ""
    mockup: str = ""
    screenshot: str = ""
    #: UI skeleton -- committed by (role, name) pairs.
    components: list[Component] = field(default_factory=list)
    #: Roles present in the sample-data region. The real app shows different
    #: data, so we commit only to **presence**, not to specific names.
    data_roles: list[str] = field(default_factory=list)
    fields: list[dict] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    #: Items the mockup self-declares as unresolved (`data-unresolved`). Any
    #: remaining item blocks the gate: coding against an unresolved screen means
    #: doing the work twice.
    unresolved: list[str] = field(default_factory=list)
    #: Mockup did not declare `data-state="primary"` -- contract covers the
    #: **whole page**. A page rendering multiple states side by side never
    #: matches a real single-state screen (e9 note-editor 2026-09-05: 32
    #: components, 4x "Add tag", story burned $28 over 4 rounds and still
    #: could not pass the gate).
    whole_page: bool = False
    #: Number of duplicate (role, name) components merged -- a sign of multiple states.
    duplicates: int = 0
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "route": self.route,
            "purpose": self.purpose,
            "mockup": self.mockup,
            "screenshot": self.screenshot,
            "components": [{"role": c.role, "name": c.name} for c in self.components],
            "data_roles": self.data_roles,
            "fields": self.fields,
            "states": self.states,
            "unresolved": self.unresolved,
            "whole_page": self.whole_page,
            "duplicates": self.duplicates,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScreenContract":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            route=data.get("route", ""),
            purpose=data.get("purpose", ""),
            mockup=data.get("mockup", ""),
            screenshot=data.get("screenshot", ""),
            components=[
                Component(c.get("role", ""), c.get("name", ""))
                for c in data.get("components", [])
            ],
            data_roles=data.get("data_roles", []),
            fields=data.get("fields", []),
            states=data.get("states", []),
            unresolved=data.get("unresolved", []),
            whole_page=bool(data.get("whole_page", False)),
            duplicates=int(data.get("duplicates", 0) or 0),
            error=data.get("error", ""),
        )


@dataclass
class DesignContract:
    screens: list[ScreenContract] = field(default_factory=list)
    version: int = CONTRACT_VERSION

    def by_id(self, screen_id: str) -> ScreenContract | None:
        return next((s for s in self.screens if s.id == screen_id), None)

    @property
    def ids(self) -> list[str]:
        return [s.id for s in self.screens]

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "screens": [s.as_dict() for s in self.screens],
        }

    def slice_for(self, screen_id: str) -> dict | None:
        """Single-screen slice -- input for the map-mockup step during coding."""
        screen = self.by_id(screen_id)
        return screen.as_dict() if screen else None

    def write(self, artifact_root: Path | str) -> Path:
        path = Path(artifact_root) / CONTRACT_FILE
        path.write_text(
            json.dumps(self.as_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path


def load(artifact_root: Path | str) -> DesignContract:
    path = Path(artifact_root) / CONTRACT_FILE
    if not path.is_file():
        return DesignContract()
    data = json.loads(path.read_text(encoding="utf-8"))
    return DesignContract(
        version=int(data.get("version") or CONTRACT_VERSION),
        screens=[ScreenContract.from_dict(s) for s in data.get("screens", [])],
    )


def build(
    experience: Experience,
    rendered,
    *,
    artifact_root: Path | str = ".",
) -> DesignContract:
    """Join the screen list (EXPERIENCE.md) with rendered mockup results.

    A screen present in EXPERIENCE.md but not yet rendered still **appears**
    in the contract, with a reason. Dropping it would make the contract look
    complete while a screen is actually missing -- exactly the kind of error
    the gate exists to catch.
    """
    root = Path(artifact_root)
    contract = DesignContract()

    for screen in experience.screens:
        contract.screens.append(_one(screen, rendered.by_id(screen.id) if rendered else None, root))
    return contract


def _rel(root: Path, path: str) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).resolve().relative_to(root.resolve()))
    except ValueError:
        return path


def _one(screen: Screen, rendered, root: Path) -> ScreenContract:
    out = ScreenContract(
        id=screen.id,
        name=screen.name,
        purpose=screen.purpose,
        states=list(screen.states),
    )
    if rendered is None:
        out.error = "mockup could not be built for this screen"
        return out
    if rendered.error:
        out.error = rendered.error
        return out

    out.route = rendered.route
    out.mockup = _rel(root, rendered.html)
    out.screenshot = _rel(root, rendered.png)
    # A mockup file often renders multiple states side by side, but the real
    # app shows only **one** state at a time. Merging all of them means no
    # real screen can match, and the gate fails for the wrong reason.
    primary = getattr(rendered, "primary_snapshot", "") or rendered.snapshot
    everything = parse_aria_snapshot(primary)
    in_samples = [
        c for snap in getattr(rendered, "sample_snapshots", []) or []
        for c in parse_aria_snapshot(snap)
    ]
    ignored = set(in_samples) | {
        c for snap in getattr(rendered, "annotation_snapshots", []) or []
        for c in parse_aria_snapshot(snap)
    }
    unique: list[Component] = []
    for c in everything:
        if c in ignored:
            continue
        if c in unique:
            out.duplicates += 1
        else:
            unique.append(c)
    out.components = unique
    out.whole_page = not getattr(rendered, "primary_snapshot", "")
    out.data_roles = sorted({c.role for c in in_samples if c in set(everything)}) or sorted(
        {c.role for c in in_samples}
    )
    out.states = list(getattr(rendered, "declared_states", []) or []) or out.states
    out.fields = rendered.fields
    out.unresolved = list(rendered.unresolved)
    if rendered.console_errors:
        out.error = f"mockup javascript error: {rendered.console_errors[0][:200]}"
    return out
