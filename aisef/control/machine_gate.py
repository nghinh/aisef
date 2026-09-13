"""Machine gate — check what code can check, before asking a human to review.

Running before the human gate is intentional: making a human read a document
with dependency cycles or unverifiable requirements wastes their time, and
these are the kind of errors machines catch better than humans.

Two severity levels, because they require different actions:

* **Errors** block — the document is too broken for the next step to use.
* **Warnings** do not block but appear in the human gate summary, so the
  approver can decide whether to accept. Unanswered open questions are the
  classic example: valid, but the approver needs to know.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..config import DEFAULTS, Config
from .normalize import PRD, is_lockfile
from .scheduler import CycleError, Story, build_waves


@dataclass
class GateResult:
    name: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        head = f"{self.name}: {'PASS' if self.passed else 'FAIL'}"
        lines = [head]
        for e in self.errors:
            lines.append(f"  ✗ {e}")
        for w in self.warnings:
            lines.append(f"  ⚠️  {w}")
        return "\n".join(lines)


def check_prd(prd: PRD) -> GateResult:
    """Check the PRD before asking a human to review."""
    r = GateResult("machine gate: prd")

    if not prd.functional():
        r.errors.append("no functional requirements found")
        return r

    untestable = prd.untestable()
    if untestable:
        ids = ", ".join(x.id for x in untestable)
        r.errors.append(
            f"requirements with no verifiable acceptance criteria: {ids} — "
            f"cannot accept what cannot be verified"
        )

    empty_title = [x.id for x in prd.requirements if not x.title.strip()]
    if empty_title:
        r.errors.append(f"requirements missing title: {', '.join(empty_title)}")

    blocked = prd.blocked_ids()
    if blocked:
        r.warnings.append(
            f"{len(blocked)} requirements blocked by open questions "
            f"({', '.join(sorted(blocked))}) — do not assign to stories until resolved"
        )

    unresolved = [q.id for q in prd.open_questions]
    if unresolved:
        r.warnings.append(
            f"{len(unresolved)} open questions need human decision: {', '.join(unresolved)}"
        )

    if prd.assumptions:
        r.warnings.append(f"{len(prd.assumptions)} assumptions recorded — review during approval")

    if not prd.non_functional():
        r.warnings.append("no non-functional requirements — rarely correct")

    return r


def check_stories(
    stories: list[Story],
    prd: PRD | None = None,
    *,
    config: Config | None = None,
    story_fr_map: dict[str, list[str]] | None = None,
    story_ac_count: dict[str, int] | None = None,
) -> GateResult:
    """Check the story set before starting implementation."""
    r = GateResult("machine gate: stories")
    cfg = config or Config(dict(DEFAULTS))

    if not stories:
        r.errors.append("no stories found")
        return r

    ids = [s.id for s in stories]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        r.errors.append(f"duplicate story ids: {', '.join(dupes)}")

    no_scope = [s.id for s in stories if not s.write_scope]
    if no_scope:
        r.errors.append(
            f"stories missing write_scope: {', '.join(no_scope)} — "
            f"cannot schedule in parallel, and guard will block all writes"
        )

    # Dependency cycle: use the actual scheduler, so the gate and runtime
    # cannot disagree on what is valid.
    try:
        build_waves(stories)
    except CycleError as e:
        r.errors.append(f"dependency cycle: {e}")
    except ValueError as e:
        r.errors.append(str(e))

    max_ac = cfg["story.max_acceptance_criteria"]
    for sid, n in (story_ac_count or {}).items():
        if n > max_ac:
            r.errors.append(
                f"{sid} has {n} acceptance criteria, exceeding limit {max_ac} — split it, "
                f"an oversized story will overflow context in a single session"
            )

    # Fully serialized epics: each story in its own wave. May be correct —
    # but also a sign the planner chained stories by habit rather than by
    # real dependency, making all parallelism unreachable.
    #
    # Checked **per epic**, since that is the unit the scheduler uses for
    # waves: epics run sequentially, stories run in parallel within an epic.
    # Computing across the whole set produces different numbers that mean
    # nothing.
    #
    # Warning, not blocking: this is a fact for the reader to question,
    # not a confident machine conclusion.
    if not r.errors:
        chuoi = []
        for epic in sorted({s.epic_id for s in stories if s.epic_id}):
            trong = [s for s in stories if s.epic_id == epic]
            if len(trong) < 3:
                continue
            try:
                dot = build_waves(trong)
            except (CycleError, ValueError, KeyError):
                continue
            if len(dot) == len(trong):
                chuoi.append(f"{epic} ({len(trong)} story)")
        if chuoi:
            r.warnings.append(
                "epics are fully serialized, no stories can run in parallel: "
                f"{', '.join(chuoi)} — review `depends_on`, only declare when a story "
                "truly needs the **output** of an earlier one"
            )

    # Two stories in one epic writing the **same** files, measured 3 for 3 on
    # todo-cli 2026-09-13: each epic was split into "implement command X" and
    # "error cases of command X", and a competent implementation of the first
    # covered the second's criteria. The later story then has nothing it can
    # do — its tests pass at the branch point, `tests verify story` blocks, and
    # no test the developer writes can be red for behaviour already merged
    # (lỗi 128). Three of thirteen stories died that way, ~45 minutes of agent
    # time, and the plan was knowable at this gate.
    #
    # Warning, not blocking: splitting one file across two stories is
    # sometimes right — a second, genuinely distinct feature in the same
    # module. The reader decides; the gate only refuses to stay quiet.
    if not r.errors:
        theo_pham_vi: dict[tuple[str, tuple[str, ...]], list[str]] = {}
        ca_du_an: dict[tuple[str, ...], int] = {}
        for s_ in stories:
            pham_vi = tuple(sorted(p for p in s_.write_scope if not is_lockfile(p)))
            if not pham_vi:
                continue
            ca_du_an[pham_vi] = ca_du_an.get(pham_vi, 0) + 1
            if s_.epic_id:
                theo_pham_vi.setdefault((s_.epic_id, pham_vi), []).append(s_.id)
        # A scope that **every** story in the plan declares is the project's
        # shape, not a smell about any pair: measured on a single-file browser
        # app where all seven stories write `index.html` — there this named two
        # pairs and told the reader nothing. On the multi-file project it stays
        # informative, `lib/commands/list.js` being shared by 2 of 13.
        co_pham_vi = sum(ca_du_an.values())
        trung = [(k, v) for k, v in theo_pham_vi.items()
                 if len(v) > 1 and ca_du_an[k[1]] < co_pham_vi]
        if trung:
            r.warnings.append(
                "stories in the same epic write exactly the same files: "
                + "; ".join(f"{', '.join(v)} → {', '.join(k[1])}" for k, v in sorted(trung))
                + " — check that each one adds behaviour the others do not. A story "
                "whose criteria the earlier story already satisfies cannot pass: its "
                "tests are green at the branch point, and that is not something the "
                "developer can fix from inside the story"
            )

    max_paths = cfg["story.max_write_scope_paths"]
    too_wide = [
        s.id
        for s in stories
        if len([p for p in s.write_scope if not is_lockfile(p)]) > max_paths
    ]
    if too_wide:
        r.errors.append(
            f"stories touch too many locations (> {max_paths} paths): {', '.join(too_wide)}"
        )

    if prd is not None:
        covered: set[str] = set()
        for fr_ids in (story_fr_map or {}).values():
            covered |= set(fr_ids)

        blocked = prd.blocked_ids()
        expected = {x.id for x in prd.functional()} - blocked
        missing = sorted(expected - covered, key=lambda s: int(s.split("-")[1]))
        if missing:
            r.errors.append(
                f"requirements not covered by any story: {', '.join(missing)} — "
                f"traceability from PRD to code is broken"
            )

        touched_blocked = sorted(covered & blocked)
        if touched_blocked:
            r.errors.append(
                f"stories touch requirements blocked by open questions: "
                f"{', '.join(touched_blocked)}"
            )

        unknown = sorted(covered - {x.id for x in prd.requirements})
        if unknown:
            r.warnings.append(f"stories reference ids not found in PRD: {', '.join(unknown)}")

    return r


def is_route_like(route: str) -> bool:
    """Can this string be opened as a URL path.

    The route is filled in by an agent writing prose in a table, and prose
    reaches the browser unchanged: `todo` 2026-09-09 declared "Single initial
    document; no route change required", the dev server answered 404, and the
    mockup-map step read the error page as an app missing every component.

    Whitespace is the tell — a real path has none, and every sentence has
    some.  Deliberately lenient about everything else: `/`, `/tasks`,
    `/note/:id`, `#/inbox`, `index.html` and `?tab=done` are all routes
    somebody really uses.
    """
    r = route.strip()
    return bool(r) and not any(c.isspace() for c in r)


def check_experience(exp) -> GateResult:
    """The UX artifact must carry a **machine-readable** screen inventory.

    `EXPERIENCE.md` is the contract between the UX phase and everything after
    it: the mockup phase builds one file per screen, the design contract pins
    each screen's components, and stories reference `screen_id`. A run on a
    fresh project produced a well-written document that described "one
    surface, the Todo List screen" in prose and never tabulated it — the UX
    gate approved, and `aisef mockup` failed a phase later with "EXPERIENCE.md
    does not list any screens", blaming the document instead of the step that
    accepted it (measured 2026-09-09, todo-e2e).

    A gate that ships an artifact its own consumer cannot read is the wrong
    place to be lenient.
    """
    r = GateResult(name="ux-spec")
    if not getattr(exp, "screens", None):
        if getattr(exp, "headless", False):
            # Declared, not omitted (bug 107). The consumers downstream read
            # this the same way: no screens to build, no browser contract.
            r.warnings.append(
                "EXPERIENCE.md declares no graphical surface — no mockups will be "
                "built and stories carry no browser or mockup-map contract"
            )
            return r
        r.errors.append(
            "EXPERIENCE.md: add a screen inventory **table** under a heading like "
            "`Screen Inventory` / `Screens` / `Information Architecture` — one row per "
            "screen, columns `Screen` (or `screen_id`), `Route`, `Purpose`. Prose is not "
            "enough: mockup builds one file per row and stories reference `screen_id`."
        )
        return r
    for s in exp.screens:
        if not s.name and not s.id:
            r.errors.append("a screen row has neither a name nor an id")
        if not s.route:
            r.warnings.append(f"{s.id or s.name}: no route declared — "
                              "the mockup gate will require one")
    return r


def check_design_contract(
    contract,
    experience,
    stories: list | None = None,
) -> GateResult:
    """Check the design contract before asking a human to review mockups.

    Three questions, all with deterministic answers:

    1. Does every screen in EXPERIENCE.md have a buildable mockup?
    2. Are there spots the mockup declares as **unresolved**?
    3. Do UI stories reference screens that **actually exist**?

    Question 3 matters because at implementation time, the agent loads the
    contract by ``screen_id`` from the story. A wrong id loads nothing and
    the agent builds UI by guesswork — exactly what the mockup-map step was
    created to prevent.
    """
    r = GateResult("machine gate: mockup")

    if not experience.screens:
        if getattr(experience, "headless", False):
            # Declared, not forgotten: a CLI, a library or a service has
            # nothing to mock up, and the gate says so instead of demanding a
            # screen inventory the product does not have.
            r.warnings.append(
                "EXPERIENCE.md declares no graphical surface — nothing to mock up, "
                "and stories carry no browser or mockup-map contract"
            )
            return r
        r.errors.append("EXPERIENCE.md lists no screens")
        return r

    missing = [s.id for s in experience.screens if contract.by_id(s.id) is None]
    if missing:
        r.errors.append(f"screens not in design contract: {', '.join(missing)}")

    unresolved: list[tuple[str, str]] = []
    for screen in contract.screens:
        if screen.error:
            r.errors.append(f"{screen.id}: {screen.error}")
            continue
        unresolved += [(screen.id, item) for item in screen.unresolved]
        if screen.whole_page and screen.duplicates:
            # Measured 2026-09-05 (e9 note-editor): mockup forgot `data-state`,
            # contract captured the whole page with 4 states -> story could not
            # pass the mockup-map step, burned $28 over 4 attempts. Blocking
            # here is much cheaper.
            r.errors.append(
                f"{screen.id}: mark the states with `data-state=\"primary\"` "
                f"(aisef-mockup-html skill, section 7), then `aisef mockup` — no --force, "
                f"it only re-extracts the contract. Until then the contract holds the whole "
                f"page ({len(screen.components)} components, {screen.duplicates} duplicates): "
                f"every state side by side, where a real app shows one, so mockup-map never matches"
            )
        if not screen.route:
            r.errors.append(
                f"{screen.id}: mockup does not declare a route (meta tag aisef-route) — "
                "cannot cross-check against the real app"
            )
        elif not is_route_like(screen.route):
            # Measured 2026-09-09 (`todo`): the route read "Single initial
            # document; no route change required" — a sentence, which became
            # a URL, which the dev server answered with its 404 page. The
            # comparison then reported every component missing and the story
            # burned all 3 attempts fixing code that was fine. A route is
            # opened, not read: it must be openable.
            r.errors.append(
                f"{screen.id}: put the real path in the `aisef-route` meta tag "
                f"(`/`, `/tasks`, `/note/:id`) and re-run `aisef mockup`. "
                f"`{screen.route[:80]}` is a sentence, not a route: it becomes a URL, the app "
                f"answers 404, and mockup-map then reports every component missing"
            )
        else:
            declared = experience.by_id(screen.id)
            if declared is not None and declared.route and declared.route != screen.route:
                # Not blocking: one of them is correct, and the approver knows which.
                r.warnings.append(
                    f"{screen.id}: mockup route ({screen.route}) differs from route in "
                    f"EXPERIENCE.md ({declared.route})"
                )
        if not screen.components:
            r.warnings.append(f"{screen.id}: mockup has no verifiable components")

    if unresolved:
        # Group by **question**, not by marked spot. 52 unresolved spots across
        # 5 screens typically map to 4-5 questions; listing every spot shows the
        # approver a wall, grouping shows exactly what needs to be done.
        by_question: dict[str, int] = {}
        for _, item in unresolved:
            m = re.search(r"\b(?:UX-)?OQ-\d+\b", item)
            key = m.group(0) if m else "no question id"
            by_question[key] = by_question.get(key, 0) + 1
        listed = " · ".join(
            f"{q} ({n} spots)" for q, n in sorted(by_question.items(), key=lambda x: -x[1])
        )
        r.errors.append(
            f"mockup has {len(unresolved)} unresolved spots across "
            f"{len({s for s, _ in unresolved})} screens, mapping to "
            f"{len(by_question)} questions: {listed}. Answer them in PRD/UX "
            f"then rebuild mockup — building code from unresolved screens costs double."
        )
        # Spots without a question id cannot be traced by the approver; show
        # a few examples so they know what they are looking at.
        loose = [item for _, item in unresolved if not re.search(r"\b(?:UX-)?OQ-\d+\b", item)]
        for item in loose[:3]:
            r.warnings.append(f"unresolved, no question id: {item[:140]}")

    extra = [s.id for s in contract.screens if experience.by_id(s.id) is None]
    if extra:
        r.warnings.append(f"design contract has screens not in EXPERIENCE.md: {', '.join(extra)}")

    if stories is not None:
        known = set(contract.ids) | set(experience.ids)
        for story in stories:
            unknown = [sid for sid in getattr(story, "screens", []) if sid not in known]
            if unknown:
                r.errors.append(
                    f"{story.id}: references non-existent screens: {', '.join(unknown)}"
                )
        used = {sid for st in stories for sid in getattr(st, "screens", [])}
        orphan = [s.id for s in experience.screens if s.id not in used]
        if orphan:
            r.warnings.append(f"screens not built by any story: {', '.join(orphan)}")

    return r


def check_all(results: list[GateResult]) -> GateResult:
    """Combine multiple gate results into one."""
    combined = GateResult("machine gate")
    for r in results:
        combined.errors.extend(f"[{r.name}] {e}" for e in r.errors)
        combined.warnings.extend(f"[{r.name}] {w}" for w in r.warnings)
    return combined
