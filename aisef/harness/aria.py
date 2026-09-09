"""Compare the live screen against the visual contract extracted from a mockup.

This is the second half of the mockup-mapping step (SOLUTION item 12bis) and
the 5th condition of the story gate.

**Why accessibility tree instead of CSS selectors or pixel diff:**

* CSS selectors break on every class rename — false positives, missed real bugs;
* pixel diff between a static mockup and the live app **never** matches,
  so the gate stays red permanently and gets disabled, and a disabled gate
  is worse than no gate at all;
* the accessibility tree carries **semantic meaning** (role + name), is
  resilient to UI changes, and checks accessibility for free.

Input is the result of Playwright's `page.locator('body').ariaSnapshot()` —
format validated experimentally in spike S7.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Roles that carry a contract. Pure `text:` nodes and layout nodes are
#: ignored: they are presentation details, not what the mockup commits to.
CONTRACT_ROLES = frozenset({
    "button", "textbox", "checkbox", "radio", "link", "combobox",
    "listbox", "option", "slider", "switch", "spinbutton", "searchbox",
    "tab", "menuitem", "heading", "img", "table", "progressbar", "alert",
})

_LINE = re.compile(r'^\s*-\s+([a-z]+)(?:\s+"([^"]*)")?')


@dataclass(frozen=True)
class Component:
    role: str
    name: str

    def __str__(self) -> str:
        return f'{self.role} "{self.name}"'


@dataclass
class MapResult:
    """Result of comparing one screen against its contract."""

    screen_id: str = ""
    route: str = ""
    contract: list[Component] = field(default_factory=list)
    actual: list[Component] = field(default_factory=list)
    missing: list[Component] = field(default_factory=list)
    extra: list[Component] = field(default_factory=list)
    #: Roles the contract promises in the data region but the app renders
    #: none of. Comparing by name in this region is meaningless (data differs),
    #: yet comparing nothing would miss an entirely empty list.
    missing_data_roles: list[str] = field(default_factory=list)

    @property
    def matched(self) -> int:
        return len(self.contract) - len(self.missing)

    @property
    def passed(self) -> bool:
        """Only `missing` items block the gate.

        The live app may have extra reasonable elements (auxiliary buttons,
        banners), but it **must not lack** what the contract promises.
        """
        return not self.missing and not self.missing_data_roles

    def to_evidence(self) -> dict:
        return {
            "screen_id": self.screen_id,
            "route": self.route,
            "contract_components": len(self.contract),
            "matched": self.matched,
            "missing": [str(c) for c in self.missing],
            "missing_data_roles": self.missing_data_roles,
            "extra": [str(c) for c in self.extra],
            "passed": self.passed,
        }

    def summary(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        parts = [f"{self.screen_id or 'screen'}: {verdict} ({self.matched}/{len(self.contract)})"]
        if self.missing:
            parts.append("  missing: " + ", ".join(str(c) for c in self.missing))
        if self.missing_data_roles:
            # An empty list is the usual cause, not a missing feature: the
            # mockup shows sample rows, the app at a bare URL has none. Say
            # where to look, or the next reader spends an afternoon on it
            # (`todo` 2026-09-09: `checkbox` missing because a fresh browser
            # profile has no stored task).
            parts.append(
                "  data region rendered no items of type: "
                + ", ".join(self.missing_data_roles)
                + " — the list was empty at this URL; `app.dev_command` must "
                  "serve an environment that already holds a record"
            )
        if self.extra:
            parts.append("  extra (warning): " + ", ".join(str(c) for c in self.extra))
        return "\n".join(parts)


def parse_aria_snapshot(text: str) -> list[Component]:
    """Parse a Playwright aria snapshot into a list of contract-bearing components.

    Nodes outside `CONTRACT_ROLES` and unnamed nodes are dropped — an
    unnamed element cannot be verified and is itself an accessibility issue.
    """
    out: list[Component] = []
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        role, name = m.group(1), (m.group(2) or "").strip()
        if role in CONTRACT_ROLES and name:
            out.append(Component(role, name))
    return out


def compare(
    contract: list[Component],
    actual: list[Component],
    *,
    screen_id: str = "",
    route: str = "",
    data_roles: list[str] | None = None,
) -> MapResult:
    """Compare the contract against the actual screen.

    Comparison is **set-based**, not order-dependent: the mockup and live
    app may arrange items differently and still satisfy the contract.
    Positioning is a visual-review concern, not the deterministic gate's.
    """
    want, have = set(contract), set(actual)
    roles_present = {c.role for c in actual}
    return MapResult(
        screen_id=screen_id,
        route=route,
        contract=list(contract),
        actual=list(actual),
        missing=[c for c in contract if c not in have],
        extra=[c for c in actual if c not in want],
        missing_data_roles=[r for r in (data_roles or []) if r not in roles_present],
    )


def compare_snapshots(
    contract_snapshot: str,
    actual_snapshot: str,
    *,
    screen_id: str = "",
    route: str = "",
    data_roles: list[str] | None = None,
) -> MapResult:
    """Convenience: compare two raw aria snapshot strings directly."""
    return compare(
        parse_aria_snapshot(contract_snapshot),
        parse_aria_snapshot(actual_snapshot),
        screen_id=screen_id,
        route=route,
        data_roles=data_roles,
    )
