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
from difflib import SequenceMatcher

#: Roles that carry a contract. Pure `text:` nodes and layout nodes are
#: ignored: they are presentation details, not what the mockup commits to.
CONTRACT_ROLES = frozenset({
    "button", "textbox", "checkbox", "radio", "link", "combobox",
    "listbox", "option", "slider", "switch", "spinbutton", "searchbox",
    "tab", "menuitem", "heading", "img", "table", "progressbar", "alert",
})

_LINE = re.compile(r'^\s*-\s+([a-z]+)(?:\s+"([^"]*)")?')

#: Roles a repeated record carries. They never belong to a contract — a
#: contract pins **named** controls — so they are read straight from the
#: snapshot to answer one question: did the data region render any rows?
ITEM_ROLES = frozenset({"listitem", "row", "option", "gridcell", "treeitem"})


def has_items(snapshot: str) -> bool:
    """True if the snapshot shows at least one repeated record."""
    return any((m := _LINE.match(line)) and m.group(1) in ITEM_ROLES
               for line in (snapshot or "").splitlines())


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
    #: The live page showed at least one repeated record.
    items_rendered: bool = False

    @property
    def matched(self) -> int:
        return len(self.contract) - len(self.missing)

    @property
    def blocking_data_roles(self) -> list[str]:
        """Data-region roles whose absence is a real gap, not an empty list.

        On a page with no rows the two are indistinguishable — and demanding
        rows is not always answerable: the first story of a project builds the
        shell before anything can create a record, and a browser-stored app
        has no seed the dev server could serve. Reported either way, blocking
        only when there were rows to look in (measured on `todo` and
        `todo-e2e`, 2026-09-09: `checkbox` missing from an empty list cost
        both projects attempts they could not have passed).
        """
        return self.missing_data_roles if self.items_rendered else []

    @property
    def passed(self) -> bool:
        """Only `missing` items block the gate.

        The live app may have extra reasonable elements (auxiliary buttons,
        banners), but it **must not lack** what the contract promises.
        """
        return not self.missing and not self.blocking_data_roles

    def renamed(self) -> list[tuple[str, str]]:
        """Missing components that look like something the app **does** render
        under a different name.

        A renamed label is the most common way a component goes missing, and
        saying only "missing" sends the author looking for a field that is on
        the screen in front of them: todo/STORY-02-01 2026-09-09 burned three
        attempts on `missing: textbox "Description"` while
        `textbox "Description (optional)"` sat in `extra` the whole time.
        The mockup pins the accessible name — that is the point of it — so the
        fix is to rename back or re-approve the mockup, and the message has to
        say which two names are in play.
        """
        out = []
        for m in self.missing:
            gan = [e for e in self.extra if e.role == m.role and (
                m.name in e.name or e.name in m.name
                or SequenceMatcher(None, m.name.lower(), e.name.lower()).ratio() >= 0.75)]
            if gan:
                out.append((str(m), str(gan[0])))
        return out

    def to_evidence(self) -> dict:
        return {
            "screen_id": self.screen_id,
            "route": self.route,
            "contract_components": len(self.contract),
            "matched": self.matched,
            "missing": [str(c) for c in self.missing],
            # Only the blocking ones under the name every reader treats as a
            # gap; the rest are recorded separately so they stay visible
            # without turning into "missing" in the gate message and ISSUES.md.
            "missing_data_roles": self.blocking_data_roles,
            "unchecked_data_roles": [] if self.items_rendered else list(self.missing_data_roles),
            "extra": [str(c) for c in self.extra],
            "renamed": [list(x) for x in self.renamed()],
            "passed": self.passed,
        }

    def summary(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        parts = [f"{self.screen_id or 'screen'}: {verdict} ({self.matched}/{len(self.contract)})"]
        if self.missing:
            parts.append("  missing: " + ", ".join(str(c) for c in self.missing))
        for thieu, thay in self.renamed():
            parts.append(
                f"  {thieu} is on screen as {thay} — the mockup pins the accessible "
                f"name: rename it back, or change the mockup and re-approve")
        if self.missing_data_roles and self.items_rendered:
            parts.append(
                "  the data region has rows, but none of type: "
                + ", ".join(self.missing_data_roles)
                + " — the mockup shows this role inside a record"
            )
        elif self.missing_data_roles:
            parts.append(
                "  (note) data region was empty, so these roles could not be "
                "checked: " + ", ".join(self.missing_data_roles)
                + " — not a gap; seed a record to compare them"
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
    items_rendered: bool = False,
) -> MapResult:
    """Compare the contract against the actual screen.

    Comparison is **set-based**, not order-dependent: the mockup and live
    app may arrange items differently and still satisfy the contract.
    Positioning is a visual-review concern, not the deterministic gate's.

    ``items_rendered`` says whether the live page showed any repeated record.
    Roles that exist only inside the mockup's sample rows cannot be judged on
    a page with no rows — "the list is empty" and "the checkbox was never
    built" look identical there. They are still reported; they only block
    when there **were** rows to look at.
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
        items_rendered=items_rendered,
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
