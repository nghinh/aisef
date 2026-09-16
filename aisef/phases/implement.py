"""Phase 4 -- implement a story: one session, one worktree, one gate.

Story lifecycle:

    build context -> run agent (write code) -> compare mockup -> independent
    review -> score gate -> done / retry / blocked

Two invariants enforced here:

* **One session per story** (decision D1).  Do not carry context from the
  previous story -- stale context is an unverifiable source of noise.
* **Distinguish infrastructure errors from quality errors.**  A dropped
  connection is not the agent's fault: retry, and do **not** count it
  toward the attempt limit.  Merging the two means a flaky network blocks
  the story unfairly, while a bad agent gets infinite retries.
"""

from __future__ import annotations

import time

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from functools import partial
import json
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath

from ..clients.base import ClientAdapter
from ..config import Config
from ..control import gate as story_gate
from ..control import tdd
from ..kit import registry as skill_registry
from ..kit import router as skill_router
from ..control.acceptance import contract_fingerprint, ac_code, coverage as ac_coverage
from ..control.design_contract import DesignContract, load as load_contract
from ..control.impact import analyse as analyse_impact, is_test_path
from ..control.preflight import verification_contract
from ..control.security import SEVERITIES, SecurityReport
from ..control.security import parse as parse_security
from ..control.normalize import Architecture, Story, effective_write_scope
from ..harness import context as code_map
from ..harness import mockup_verify
from ..clients.compile import guard_expected
from ..clients.stream import ENVIRONMENT_STATUSES, INFRA_STATUSES, RunResult, exit_status_of, retry_delay_seconds
from ..control import identity as ident
from ..control.budget import BudgetLocked
from ..control.outcome import StageOutcome
from ..harness.guardrails import (
    ENV_BASELINE_DIRTY,
    ENV_ALLOW_HOSTS,
    ENV_DISALLOWED_TOOLS,
    ENV_PROJECT,
    ENV_WORKDIR,
    ENV_BASE_REF,
    ENV_STORY_ID,
    ENV_SESSION_ID,
    ENV_ATTEMPT,
    ENV_WRITE_SCOPE,
    changed_files,
    fork_point,
    head_sha,
)
from ..control.budget import BudgetExceeded, BudgetGuard
from ..control.journal import Entry as JEntry, JournalStore
from ..harness.mockup_map import load_for_story, prompt_section
from ..harness.observe import AGENT_RUN, MOCKUP_MAP, NOTE, SKILL_USE, TOOL_RUN, Event, Evidence, EvidenceStore
from ..harness.prompts import Catalog, load_catalog
from ..harness.routing import DEVELOPER, REVIEWER, ROLES, SECURITY, build_spec
from ..harness.testlog import MAX_IDS, parse as parse_testlog
from ..harness.tools import (BASELINE_RUN, NOP_RUN, aisef_command, describe_tools, record as record_tool,
                             run_tool)
from .qa import KINDS, find_fake_tests, run_suite

@dataclass
class Attempt:
    number: int
    ok: bool = False
    infra: bool = False
    #: Nhà cung cấp bảo chờ bao lâu trước khi thử lại (429). 0 = không nói.
    #: Thử lại ngay một lượt bị giới hạn tần suất là cách chắc chắn nhất để
    #: nhận đúng lỗi ấy lần nữa, và ngân sách hạ tầng bốc hơi trong vài giây.
    retry_after: float = 0.0
    #: The session ran fine and changed nothing. Accounted as `infra` so a
    #: session with nothing to grade does not consume a quality attempt — but
    #: it is not an infrastructure fault, and the reason given to the reader
    #: must not send them to the provider's status page (bug 102).
    noop: bool = False
    #: Fatal -- retrying is pointless.  E.g. isolation broke: the next
    #: attempt's worktree forks from a dirty trunk, so it only wastes money.
    fatal: bool = False
    error: str = ""
    cost_usd: float = 0.0
    gate: story_gate.StoryGate | None = None
    review_findings: list[str] = field(default_factory=list)
    #: The developer session that produced this attempt (control/identity.py); guard records bind to it.
    session_id: str = ""
    #: Processes the session left behind that survived the reaper (F5 / INV-L.1): the workspace is kept for them.
    orphans: list[int] = field(default_factory=list)
    #: Typed outcome of the attempt (control/outcome.StageOutcome) — the routing key; the booleans above are derived.
    outcome: str = ""
    #: The identity tuple the verdict was computed under — what `gate:verdict` was stamped with.
    identity: dict = field(default_factory=dict)
    #: Why the reviewer did **not execute** on this candidate (max_turns, timeout,
    #: transport error, tree modified, candidate moved) — "" when it did.  A
    #: reviewer that did not run has said nothing about the code: not a BLOCK,
    #: not a PASS, and never a reason to reopen the developer (D-032, lỗi 186).
    review_unrunnable: str = ""
    #: 1-based count of reviewer executions on this candidate, this one included.
    review_attempt: int = 0
    #: Stuck items from the reviewer's **machine-readable** verdict only.
    #: A terminal plan deadlock rests on this list, never on `review_findings`:
    #: the text parser splits a tag out of running prose, and on LedgerLock
    #: STORY-01-03 (2026-09-15, lỗi 180 / D-026) the sentence "So [stuck]
    #: doesn't apply." — a reviewer *rejecting* the tag — became the story's
    #: terminal verdict while its JSON said `block` with three real findings.
    plan_findings: list[str] = field(default_factory=list)
    security: SecurityReport | None = None
    #: Frozen candidate SHA -- all evidence from this attempt points to it.
    candidate: str = ""
    #: Re-verify attempt (ADR-004 R13): no developer session, does not count
    #: toward `run.max_retries`.  `reran`/`kept` are checks re-executed / kept
    #: from evidence at the correct candidate -- so readers know what was paid for.
    verify_only: bool = False
    reran: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)


@dataclass
class StoryOutcome:
    story_id: str
    attempts: list[Attempt] = field(default_factory=list)
    blocked_reason: str = ""
    #: Typed terminal (control/outcome.StageOutcome value) — what `blocked_reason` says, as data. "" while running
    #: or when the story is done. Readers decide on this, never on the prose.
    terminal: str = ""

    def block(self, kind: StageOutcome, reason: str) -> None:
        self.terminal = kind.value
        self.blocked_reason = reason

    @property
    def done(self) -> bool:
        return bool(self.attempts) and self.attempts[-1].ok

    @property
    def quality_attempts(self) -> int:
        """Attempts that **count toward the limit** -- infrastructure errors
        and re-verify attempts do not count: the former is not the agent's
        fault, the latter has no agent doing anything."""
        return len([a for a in self.attempts if not a.infra and not a.verify_only])

    @property
    def cost_usd(self) -> float:
        return sum(a.cost_usd for a in self.attempts)

    def summary(self) -> str:
        lines = [f"{self.story_id}: {'DONE' if self.done else 'NOT DONE'}"]
        for a in self.attempts:
            tag = "infra" if a.infra else ("re-verify" if a.verify_only else f"attempt {a.number}")
            head = "ok" if a.ok else (a.error or "gate failed")
            lines.append(f"  [{tag}] {head}")
            if a.verify_only:
                lines.append(f"  candidate {a.candidate[:7]}: reran {', '.join(a.reran) or '—'}"
                             f" · kept {', '.join(a.kept) or '—'}")
            if a.gate and not a.gate.passed:
                lines.extend("  " + line for line in a.gate.summary().splitlines()[1:])
        if self.blocked_reason:
            lines.append(f"  ✗ {self.blocked_reason}")
        if self.cost_usd:
            lines.append(f"  cost: ${self.cost_usd:.2f}")
        return "\n".join(lines)


def build_context(
    story: Story,
    *,
    project: Path,
    artifact_root: Path,
    architecture: Architecture | None,
    contract: DesignContract | None,
    config: Config | None,
    feedback: str = "",
    preservation: list[dict] | None = None,
) -> dict:
    """Story prompt context -- selected by lookup, not by judgment.

    ``preservation`` is the pre-computed list of behaviors to preserve (R4).
    Passed in so reviewer/security receive **exactly** the list the developer
    received: recomputing after the developer session would reflect evidence
    from that very attempt, and the three roles would see three different
    lists.  `None` = compute from ledger.
    """
    story_file = artifact_root / "stories" / story.epic_id / f"{story.id}.md"
    contract_text = (
        story_file.read_text(encoding="utf-8", errors="replace")
        if story_file.is_file()
        else _story_fallback(story)
    )
    if feedback:
        contract_text += (
            "\n\n## Previous attempt did not pass\n\n"
            "These are the gate results from the previous attempt. Fix exactly "
            "these items; do not rewrite from scratch.\n\n" + feedback + "\n"
        )

    rules = architecture.for_requirements(story.covers) if architecture else []
    slices: list = []
    if contract and story.screens:
        slices, _ = load_for_story(contract, story.screens, artifact_root=artifact_root)

    skills, skills_ev = _skills_section(story, project=project, artifact_root=artifact_root, config=config)
    led = _ledger(artifact_root)
    if preservation is None:
        preservation = preservation_items(story, project=project, ledger=led)
    cap = int(config["context.max_preservation_chars"]) if config else 1500
    return {
        "_skills": skills_ev,
        "_preservation": preservation,
        "skills": skills,
        "preservation": preservation_text(preservation, max_chars=cap),
        "validation": validation_text(story, preservation, max_chars=cap),
        "story_id": story.id,
        "story_title": story.title,
        "story_contract": contract_text,
        "architecture_rules": (
            "\n\n".join(d.as_prompt() for d in rules)
            or "(architecture has no decisions constraining this story)"
        ),
        "write_scope": _write_scope_lines(story, project),
        "mockup_section": prompt_section(slices),
        "tools": describe_tools(project, config),
        "index": _index_slice(story, artifact_root, config, ledger=led),
        "roadmap": _roadmap(story, artifact_root, config),
        "repo_map": _repo_map_section(story, project=project, artifact_root=artifact_root, config=config),
        "blast_radius": _blast_radius_section(story, project=project, config=config),
    }


def _blast_radius_section(story: Story, *, project: Path, config: Config | None) -> str:
    """Impact analysis from CodebaseGraphProvider -- only runs on brownfield."""
    baseline = project / "_bmad-output" / "baseline.md"
    if not baseline.is_file():
        return ""
    targets = list(story.write_scope) if story.write_scope else []
    if not targets:
        return ""
    try:
        from ..codebase.provider import resolve
        provider = resolve(project, preference=str((config or {}).get("context.graph_provider", "auto")))
        result = provider.impact(project, targets)
    except Exception:  # noqa: BLE001
        return ""
    if not result.affected:
        return ""
    lines = [f"- {n.file or n.id}" + (f" ({n.kind})" if n.kind else "") for n in result.affected[:30]]
    return (
        "\n## Blast Radius\n\n"
        "Files/modules affected by write_scope (impact analysis):\n\n"
        + "\n".join(lines) + "\n\n"
        "**Check regression for these files.** Do not modify outside write_scope "
        "unless necessary to maintain compatibility.\n"
    )


def _repo_map_section(story: Story, *, project: Path, artifact_root: Path, config: Config | None) -> str:
    """Slot `repo_map` (ADR-005 V7): code map around write scope, provided to
    all three roles from **code** -- no role receives it from another role's
    output (ADR-003 #9).

    Cap `context.max_repo_map_chars` = 0 disables it: empty slot, prompt has
    no entry -- until A/B T8 has numbers.  Drawn on `project` (state before
    the story) rather than on worktree: all three roles receive the same map.
    """
    cap = int(config["context.max_repo_map_chars"]) if config else 0
    if cap <= 0:
        return ""
    seeds = code_map.seeds_for(story, project, artifact_root=artifact_root, config=config)
    text = code_map.repo_map(
        project, seeds, cap,
        command=str(config.get("context.map_provider", "") or ""), story_id=story.id,
    )
    return code_map.prompt_section(text)


def _ledger(artifact_root: Path):
    """Behavior ledger projected from **existing** evidence -- does not read
    `ledger.json`.

    That file is only refreshed by `aisef report`; in a single `run` across
    an epic, the next story would not see behaviors the previous one just
    verified.  Reprojecting from evidence takes 1.1s on e9 (4.3 MB) -- cheaper
    than a missed regression.  Broken or missing ledger returns `None`,
    does not break the run.
    """
    from ..control import ledger as ledger_mod

    try:
        return ledger_mod.build(artifact_root)
    except OSError:
        return None


def _roadmap(story: Story, artifact_root: Path, config: Config | None) -> str:
    """Every story in the plan, one line — whose turn each thing is.

    The evidence index is the wrong source for this question: it is scoped to
    one epic and it is empty on a fresh project, which is exactly when the
    reviewer most needs to know that thirteen other stories exist. Bug 58 —
    STORY-01-01, whose one criterion is "the document contains these
    elements", was blocked three times for work owned by stories in EPIC-02.
    """
    from ..control.change import read_index

    cap = int(config["context.max_index_chars"]) if config else 2000
    rows = read_index(Path(artifact_root)).get("stories") or []
    lines = []
    for s in rows:
        sid = str(s.get("id") or "")
        title = str(s.get("title") or "").strip()
        lines.append(f"- {sid} — {title}" + ("   ← the story under review" if sid == story.id else ""))
    text = "\n".join(lines)
    while len(text) > cap and len(lines) > 1:
        lines.pop()
        text = "\n".join(lines) + f"\n- (+{len(rows) - len(lines)} more stories)"
    return text or "_(the plan has no story index)_"


def _index_slice(story: Story, artifact_root: Path, config: Config | None, *, ledger=None) -> str:
    """Evidence index slice for the epic containing this story (ADR-004 R6).

    Progressive disclosure: prompt receives **one line per story** -- status,
    candidate, behavior counts VERIFIED/GAP/REOPENED -- not full history.
    History is at `aisef evidence <id>`, queried when needed.  Broken or
    missing ledger yields an empty slot with an explanation, does not break
    the run.
    """
    cap = int(config["context.max_index_chars"]) if config else 2000
    led = ledger if ledger is not None else _ledger(artifact_root)
    text = led.epic_slice(story.epic_id, max_chars=cap) if led is not None else ""
    return text or "_(no evidence yet for this epic)_"


# --- Behaviors to preserve and things that must be green at candidate (ADR-004 R4)
#
# HoH puts Preservation + Validation Requirements into each round's dev doc.
# Here they are two slots **computed from the behavior ledger**, the same list
# for developer, reviewer and security -- no role receives another role's
# output (ADR-003 #9) -- and the "preservation" gate (`control/gate.py`)
# scores exactly this list on the frozen candidate.


def preservation_items(story: Story, *, project: Path, ledger) -> list[dict]:
    """VERIFIED behaviors of **other stories** whose files overlap this story's
    write scope.

    File intersection is from `complexity.verified_touched` (R5): one rule,
    two call sites, no second copy to drift.  Each item carries exactly what
    the gate needs to re-check at the candidate -- id, kind, owning story,
    verification source (test id / `qa:<kind>` / screen) -- from
    `ledger.behaviors[id].source`.
    """
    from ..control.complexity import read_scopes, verified_touched

    if ledger is None:
        return []
    out = []
    for bid in verified_touched(story, ledger.as_dict(), read_scopes(project)):
        b = ledger.behaviors[bid]
        # FR/NFR verified by the ledger **via criteria of a specific story**
        # (`source.story`) -- not necessarily the owning story: e9 FR-11 owned
        # by 01-01 (test lacks tag) but green via 01-05.  Gate must query that
        # story, otherwise it demands tests the ledger never saw (01-07 attempt 1,
        # 2026-09-06).
        out.append({"id": bid, "kind": b.kind, "story": b.story, "source": dict(b.source),
                    "via": str(b.source.get("story") or b.story)})
    return out


def _source_line(item: dict) -> str:
    src = item.get("source") or {}
    if src.get("test_id"):
        return f"test `{src['test_id']}`"
    if src.get("qa_kind"):
        return f"`qa:{src['qa_kind']}`"
    if src.get("screen"):
        return f"screen `{src['screen']}`"
    if src.get("story"):
        return "via story criteria"
    return f"`aisef evidence {item.get('id', '')}`"


def _cap(text: str, max_chars: int) -> str:
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n_(truncated to char limit — `aisef evidence <id>`)_"
    return text


def preservation_text(items: list[dict], *, max_chars: int) -> str:
    """Slot `preservation`: one line per behavior -- id, owning story, source.

    Only id and source, no history (progressive disclosure, R6).  Truncation
    by cap only truncates **display**; the gate still scores the full list --
    an agent that lost an item has a trailing line telling it to query
    `aisef evidence`.
    """
    if not items:
        return "_(does not touch any VERIFIED behaviour of another story)_"
    return _cap("\n".join(
        f"- `{it['id']}` · {it.get('story') or '?'} · {_source_line(it)}" for it in items
    ), max_chars)


def validation_text(story: Story, items: list[dict], *, max_chars: int) -> str:
    """Slot `validation`: what the **harness will re-run** on the candidate and
    the gate reads.

    Listed so the agent knows what will be scored, not for self-scoring:
    `qa:<kind>` (story contract + verified checks that were touched), screens
    (story's + other stories' touched screens).  Preservation tests only
    **count**: names already live in slot `preservation`; copying them spends
    the B5 budget twice
    (e9 01-07: 27 test id).
    """
    kinds, screens = validation_targets(story, items)
    tests = {it["source"]["test_id"] for it in items if (it.get("source") or {}).get("test_id")}
    lines = []
    if tests:
        lines.append(f"- {len(tests)} preservation tests listed above")
    if kinds:
        lines.append("- checks: " + ", ".join(f"`qa:{k}`" for k in kinds))
    if screens:
        lines.append("- screens matching mockup: " + ", ".join(f"`{s}`" for s in screens))
    return _cap("\n".join(lines), max_chars) or "_(standard gate only: test, lint, write scope)_"


def proven_text(evidence: Evidence, story: Story, *, candidate: str, max_chars: int) -> str:
    """Slot `proven`: the story's criterion-tagged tests **green at this build**.

    A reviewer that does not know what is already proven blocks on things the
    suite covers. Measured on todo-cli STORY-01-01 2026-09-13: the security
    reviewer blocked three attempts with "lstatSync ... swallows ENOENT, so
    the symlink check never runs", while the candidate shipped a green
    `AC-STORY-01-01-4: save refuses to write to broken symlink target` — and
    `lstat` on a broken symlink does not raise ENOENT at all, it returns the
    link. The story died on a claim one command would have refuted (lỗi 124).

    Not absolution: the prompt asks the reviewer to **name** the test its
    finding contradicts and say why the test does not cover the case. A
    finding that can do that still blocks; one that cannot was never a finding.
    """
    run = None
    for e in evidence.of(TOOL_RUN, "test"):
        if e.ok and (not candidate or str(e.detail.get("candidate") or "") in ("", candidate)):
            run = e
    if run is None:
        return "_(no green test run recorded at this candidate)_"
    ten = [str(t) for t in (run.detail.get("test_ids") or [])]
    if not ten:
        return "_(the test run printed no test names — cannot list what is proven)_"
    hong = {str(x) for x in (run.detail.get("failed_ids") or [])}
    hong |= {str(x) for x in (run.detail.get("skipped_ids") or [])}
    xanh = [t for t in ten if t not in hong]
    theo_tc = ac_coverage(story.id, len(story.acceptance_criteria), xanh)
    lines = [f"- AC-{story.id}-{i}: " + ", ".join(f"`{t}`" for t in ts)
             for i, ts in sorted(theo_tc.items()) if ts]
    if not lines:
        return "_(no green test carries a criterion code at this candidate)_"
    return _cap("\n".join(lines), max_chars)


def validation_targets(story: Story, items: list[dict]) -> tuple[list[str], list[str]]:
    """(verification kinds, screens) the harness must run at the candidate --
    story's own plus preservation.  Same function for the slot and for
    `run_attempt`, so what is shown to the agent and what actually runs are
    never two different lists."""
    from ..control.gate import KHONG_PHAI_QA

    kinds = [k for k in verification_contract(story) if k not in KHONG_PHAI_QA]
    screens = list(story.screens)
    for it in items:
        src = it.get("source") or {}
        # Only kinds `run_suite` can run; `qa:fake-tests` belongs to `run_attempt`,
        # recorded every attempt, so the gate sees it at the candidate without listing.
        if it.get("kind") == "qa" and src.get("qa_kind") in KINDS and src["qa_kind"] not in kinds:
            kinds.append(str(src["qa_kind"]))
        if it.get("kind") == "mockup" and src.get("screen") and src["screen"] not in screens:
            screens.append(str(src["screen"]))
    return kinds, screens


#: Which prompt slot comes from where.  Reviewer/security bundles must
#: **not** have `agent` as a source -- that is a machine-checked invariant
#: (ADR-003 #9).  A new slot not declared here shows as `?` in evidence,
#: not silently valid.
SLOT_SOURCE = {
    "story_id": "artifact", "story_title": "artifact", "story_contract": "artifact",
    "architecture_rules": "artifact", "write_scope": "artifact", "mockup_section": "artifact",
    "tools": "config", "skills": "router", "diff_summary": "git", "impact": "code",
    "repo_map": "code", "blast_radius": "code",
    "index": "ledger", "roadmap": "artifact", "preservation": "ledger", "validation": "ledger",
    "prior_review": "evidence", "proven": "evidence", "memory": "memory",
}

#: Slots allowed to be empty when building the prompt: `repo_map` empty means
#: the knob is off, not a broken prompt.  `blast_radius` empty on greenfield
#: or empty write_scope.
ALLOW_EMPTY = ("repo_map", "blast_radius")


def handoff_slots(context: dict, *, feedback: bool = False) -> dict[str, tuple[str, int]]:
    """{slot: (source, char count)} -- keys starting with `_` are internal, not slots."""
    out = {}
    for k, v in context.items():
        if k.startswith("_"):
            continue
        src = SLOT_SOURCE.get(k, "?")
        if k == "story_contract" and feedback:
            src = "artifact+gate+review"   # retry: includes "Previous attempt did not pass" section
        out[k] = (src, len(str(v)))
    return out


def _skills_section(story: Story, *, project: Path, artifact_root: Path, config: Config | None) -> tuple[str, dict]:
    """"Available skills" section + routing evidence.  Router is a signal, not
    a gate: abstain means the prompt says none available, off means off."""
    if not (config and config["skills.offer"]):
        return "_(no skill routing — `skills.offer` off)_", {"enabled": False}
    reg = skill_registry.load(artifact_root)
    r = skill_router.route(story, reg, project=project)
    section, ev = r.prompt_section(), {"enabled": True, **r.as_evidence()}
    return section, ev


def skills_used(result) -> list[str]:
    """Skills the agent opened, read from `tool_use` stream (tool `Skill`).
    Client does not emit stream -> empty, and `skills_measurable` in
    capability explains why."""
    out = []
    for tu in getattr(result, "tool_uses", None) or []:
        if tu.name == "Skill":
            out.append(str((tu.input or {}).get("skill") or (tu.input or {}).get("name") or "?"))
    return out


def _write_scope_lines(story: Story, project: Path) -> str:
    """Write scope for prompt: story-declared + harness-added paths --
    agent and reviewer must see exactly the scope the guard enforces."""
    from ..control.normalize import effective_write_scope

    full = effective_write_scope(story, project)
    declared = set(story.write_scope)
    lines = [f"- `{p}`" for p in story.write_scope]
    added = [p for p in full if p not in declared]
    if added:
        lines.append("- _(added by harness: verification paths, manifests, lockfiles)_")
        lines += [f"- `{p}`" for p in added]
    return "\n".join(lines) or "(not declared)"


def _story_fallback(story: Story) -> str:
    lines = [f"# {story.id}: {story.title}", "", "## Acceptance Criteria", ""]
    lines += [f"{i}. [{ac_code(story.id, i)}] {ac}" for i, ac in enumerate(story.acceptance_criteria, 1)]
    return "\n".join(lines)


def _reserved_client_run(client: ClientAdapter, spec, *, story_id: str,
                          estimate_usd: float = 0.0,
                          estimate_turns: int = 1):
    """Run ``client.run(spec)`` inside a budget reservation if a guard
    is attached on the client.  Returns the RunResult, or raises
    ``BudgetExceeded`` without dispatching when the cap would be
    breached; ``estimate_usd`` and ``estimate_turns`` are best-effort —
    the post-call ``settle`` records the *actual* cost from the result.
    """
    guard = getattr(client, "_budget_guard", None)
    if not isinstance(guard, BudgetGuard):
        return _owned_run(client, spec)
    with guard.reserve(
        story_id=story_id, est_usd=estimate_usd, est_turns=estimate_turns,
    ) as token:
        result = _owned_run(client, spec)
        token.actual_usd = float(getattr(result, "cost_usd", 0.0) or 0.0)
        token.actual_turns = int(getattr(result, "num_turns", 1) or 1)
        return result


def _owned_run(client: ClientAdapter, spec):
    """The attempt owns the session's process tree (F5 / INV-L.1): every child of this process that the session
    leaves behind — a real client's, or one an in-process client spawned — is terminated, reaped and verified dead
    before the session is scored; the pids are recorded on the result (`raw_result["reaped"]`), never silent."""
    from ..harness import process_owner as _po
    before = _po.children_of()
    result = client.run(spec)
    reaped = _po.reap_new_children(before)
    left = _po.survivors(before)              # VERIFY: what terminate → kill could not end is typed, never silent
    if reaped or left:
        raw = dict(getattr(result, "raw_result", None) or {})
        if reaped:
            raw["reaped"] = sorted(set(raw.get("reaped") or []) | set(reaped))
        if left:
            raw["orphans"] = left
        try:
            result.raw_result = raw
        except AttributeError:
            pass
    return result


def run_attempt(
    story: Story,
    *,
    project: Path,
    workdir: Path,
    artifact_root: Path,
    client: ClientAdapter,
    config: Config,
    catalog: Catalog,
    architecture: Architecture | None,
    contract: DesignContract | None,
    number: int,
    feedback: str = "",
    base_ref: str = "",
) -> Attempt:
    """One attempt: agent writes code, then harness self-verifies."""
    attempt = Attempt(number=number)
    attempt.session_id = ident.new_session_id()
    evidence = EvidenceStore(artifact_root)

    context = build_context(
        story,
        project=project,
        artifact_root=artifact_root,
        architecture=architecture,
        contract=contract,
        config=config,
        feedback=feedback,
    )
    from ..memory import attach
    attach(context, story, project, config, DEVELOPER)
    evidence.handoff(story.id, frm="plan" if number == 1 else "gate", to=DEVELOPER,
                     attempt=number, slots=handoff_slots(context, feedback=bool(feedback)),
                     memory=context.get("_memory"))
    # R4: preservation list locked **once** here, before the developer
    # session; reviewer, security and gate receive exactly this version --
    # recomputing after the session reflects that attempt's own evidence.
    preservation = list(context.get("_preservation") or [])
    spec = build_spec(
        DEVELOPER,
        catalog.get(ROLES[DEVELOPER].prompt),
        context,
        workdir=workdir,
        config=config,
        allow_empty=ALLOW_EMPTY,
    )
    # Guard runs in a hook -- a child process of the client -- so write scope
    # and story ID reach it only via environment variables.
    scope = effective_write_scope(story, project)
    _hosts = ",".join(config["sandbox.allow_hosts"]) if config else ""
    spec.env = {
        ENV_WRITE_SCOPE: ",".join(scope),
        # SS-37 / INV-I.3: what was already dirty before this session is PREEXISTING to the guard, exactly as the
        # planning and mockup sessions declare it — under --no-isolate an operator's file is not the developer's write
        ENV_BASELINE_DIRTY: ",".join(changed_files(str(workdir))[:200]),
        ENV_STORY_ID: story.id,
        ENV_BASE_REF: base_ref,
        ENV_WORKDIR: str(workdir),
        ENV_PROJECT: str(project),
        ENV_ALLOW_HOSTS: _hosts,
        ENV_SESSION_ID: attempt.session_id,
        ENV_ATTEMPT: str(number),
    }

    # Isolation must be **verified**, not assumed.  Worktrees prevent
    # stories from stepping on each other, but nothing stops the agent from
    # `cd`-ing out and committing to the trunk.  Observed in practice: an
    # OpenCode run pushed `src/reverse-words.js` to `main` while the story
    # branch stayed unchanged -- gate only reported "empty diff" while rogue
    # code was already on trunk.
    before_sha = head_sha(project) if workdir != project else ""
    # What *this session* writes, as opposed to what the story changes.  The
    # diff against `base_ref` answers the second question and carries a
    # previous attempt's work with it, so it cannot answer the first.
    # Both halves are needed: `_tree_snapshot` sees only files git reports as
    # dirty, so an agent that commits its own work -- which the prompt asks
    # for -- leaves a clean tree and would look silent.
    tree_before = (head_sha(workdir), _tree_snapshot(workdir))

    _attach_settings(spec, project)
    from ..harness.runlog import run_log
    run_log(artifact_root, f"story={story.id}#{number} agent START "
                           f"timeout={spec.timeout_seconds}s scope={','.join(scope)}")
    try:
        result = _reserved_client_run(
            client, spec, story_id=story.id, estimate_turns=1,
        )
    except BudgetLocked as e:
        # ledger contention between parallel stories: infrastructure, retried after a short wait — never a cap,
        # never the developer's quality budget (SS-21)
        attempt.error = f"budget ledger locked by another writer — retrying shortly ({e})"
        attempt.infra = True
        attempt.retry_after = 2.0
        attempt.outcome = StageOutcome.INFRA_FAILURE.value
        attempt.ok = False
        return attempt
    except BudgetExceeded as e:
        # the kernel's cost cap: a run-level decision, typed and terminal — not a developer failure (INV-G.5)
        attempt.error = f"budget cap reached: {e}"
        attempt.fatal = True
        attempt.infra = True     # never scored, never charged
        attempt.outcome = StageOutcome.BUDGET.value
        attempt.ok = False
        return attempt
    attempt.cost_usd = result.cost_usd
    used = skills_used(result)
    run_log(artifact_root, (
        f"story={story.id}#{number} agent DONE ok={result.ok} ${result.cost_usd:.2f} "
        f"turns={getattr(result, 'num_turns', '?')} "
        f"out_tokens={getattr(result, 'output_tokens', '?')} "
        f"err={result.error or ''}"
    ))
    evidence.agent_run(
        story.id, result, name=f"{story.id}#{number}", prompt_chars=len(spec.prompt),
        skills={**context.get("_skills", {}), "used": used},
        role=DEVELOPER, model=spec.model, client=client.id,
        tool_calls=len(result.tool_uses),
        response_snippet=(result.text or "")[:300],
    )
    for sk in used:
        evidence.record(story.id, Event(kind=SKILL_USE, name=sk, detail={"role": DEVELOPER}))
    # D-034: what this session wrote outside its scope goes on record **before**
    # any exit below — the next attempt's hygiene reads this record, and a
    # session cut by the turn cap or the provider leaves the same dirt behind.
    record_scope_violation(evidence, story.id, workdir=workdir, scope=scope, before=tree_before[1],
                           attempt=number, artifact_root=artifact_root)

    after_sha = head_sha(project) if workdir != project else ""
    if before_sha and after_sha != before_sha:
        # Who moved main decides what to do about it, and the two answers are
        # opposite. An agent that escaped its worktree wrote source there, and
        # the fix is to revert. An operator who committed while the session ran
        # — measured 2026-09-13 on `todo-oc`, a `chore:` commit of harness
        # artifacts landing mid-session (lỗi 135) — touched only
        # `_bmad-output/`, and telling them to revert is telling them to throw
        # away their own commit. The tree says which: the story's scope is
        # source, `_bmad-output/` is the harness's own record.
        from ..harness.guardrails import _git_lines
        moi = _git_lines(str(project), ["diff", "--name-only", "-z", before_sha, after_sha])   # raw: harness paths too
        cua_harness = bool(moi) and all(
            f.startswith(("_bmad-output/", ".aisef/")) for f in moi)
        attempt.error = (
            f"the project's main branch moved during this session "
            f"({before_sha[:8]} → {after_sha[:8]})"
            + ((". Only harness artifacts changed (" + ", ".join(sorted(moi)[:3])
                + ") — this looks like a commit made outside the story while it was "
                "running, not an agent escaping its worktree. Nothing to revert: "
                "let the run finish, or stop it before committing to the project.")
               if cua_harness else
               ". The story must work in its own worktree; work on the trunk does not "
               "pass any gate. Revert and re-run.")
        )
        # typed at the source (F2): a harness-only trunk change is an environment event, a story write is a breach
        attempt.outcome = (StageOutcome.ENVIRONMENT_FAILURE if cua_harness else StageOutcome.ISOLATION_BREACH).value
        attempt.infra = True   # story was never scored
        attempt.fatal = True   # and retrying is pointless
        evidence.tool_run(
            story.id, "isolation", ok=False,
            detail={"truoc": before_sha, "sau": after_sha, "attempt": number,
                    "changed": sorted(moi)[:20], "harness_only": cua_harness},
        )
        return attempt

    orphans = list((getattr(result, "raw_result", None) or {}).get("orphans") or [])
    if orphans:
        # F5 / INV-L.1 (terminate, reap, VERIFY, then remove): a process the session left behind survived SIGTERM
        # and SIGKILL, so the tree is still in use — nothing is graded, the run loop keeps the workspace
        # (`attempt.orphans`), and retrying inside it is pointless. Typed and recorded, never silent.
        attempt.error = f"process(es) {orphans} left by the session survived termination — workspace kept"
        attempt.outcome = StageOutcome.ENVIRONMENT_FAILURE.value
        attempt.infra = True
        attempt.fatal = True
        attempt.orphans = orphans
        evidence.tool_run(story.id, "process", ok=False,
                          detail={"orphans": orphans, "attempt": number, "workdir": str(workdir)})
        return attempt

    if not result.ok:
        attempt.error = result.error or "run failed"
        status = exit_status_of(result)
        attempt.infra = status in INFRA_STATUSES or status in ENVIRONMENT_STATUSES
        attempt.outcome = (StageOutcome.INFRA_FAILURE.value if status in INFRA_STATUSES else
                           StageOutcome.ENVIRONMENT_FAILURE.value if status in ENVIRONMENT_STATUSES else "")
        # `context`, `permission`, `cost`: the environment limited the session — the tree is untouched and the
        # developer wrote no wrong code; retried on the infra budget, never charged to quality (SS-15, INV-G.4)
        attempt.retry_after = retry_delay_seconds(result)
        if exit_status_of(result) == "auth":
            # `auth` is kept out of `INFRA_STATUSES` on purpose and that reasoning
            # stands: a rejected credential is not transient, so retrying it burns
            # the infra budget on a failure that repeats identically (measured
            # 2026-09-12). But *excluding* it did not achieve the stated intent —
            # it only moved the cost to the **quality** budget and retried anyway.
            # Measured on marks-cli 2026-09-14: `attempt=1 FAIL … attempt=2 START`
            # on a 401, with `moved_tree: false` and nothing to grade, so the story
            # spent quality attempts on a session the agent had no part in (lỗi
            # 161 — the shape lỗi 130 measured for `max_turns`).
            #
            # The idiom already in this function for "not the agent's fault **and**
            # retrying is pointless" is both flags at once, as the isolation branch
            # above uses it.
            attempt.infra = True   # the provider refused: nothing was ever scored
            attempt.fatal = True   # and a rejected credential repeats identically
        # Running out of *turns* is not the same as writing bad code. Measured
        # on todo-cli STORY-03-02 2026-09-13 with MiniMax-M3: three sessions in
        # a row hit the 40-turn cap, each having committed 68 lines of tests
        # into the worktree, and the harness graded none of it. The story spent
        # its whole quality budget without ever producing a verdict — so the
        # next developer got no feedback, and `nop_deadlock` had nothing to
        # read (lỗi 130). The gate decides whether work is good; a turn
        # counter cannot. Half-finished work does not sneak through: it fails
        # `test`, `criteria have tests`, the nop control, review.
        #
        # Infra statuses still return here — the provider cut the session, the
        # retry costs no quality attempt, and the next one grades this tree.
        if attempt.infra:
            return attempt
        # "Left work" means **this session** moved the tree, not that the diff
        # against the base branch is non-empty: that diff also carries earlier
        # attempts' commits. The first cut of this fix asked `changed_files`
        # and logged "grading it" for a session that had written nothing,
        # immediately before the no-op check said "0 files written" — the same
        # trap the no-op check itself documents.
        da_dong = (head_sha(workdir), _tree_snapshot(workdir)) != tree_before
        run_log(artifact_root, f"story={story.id}#{number} {exit_status_of(result)} "
                + ("but the session left work in the tree — grading it"
                   if da_dong else "and the tree is untouched — nothing to grade"))
        evidence.record(story.id, Event(
            kind=NOTE, name="session:unfinished", ok=False,
            detail={"exit_status": exit_status_of(result),
                    "turns": getattr(result, "num_turns", 0),
                    "moved_tree": da_dong,
                    "error": attempt.error[:300], "attempt": number},
        ))
        if not da_dong:
            # Untouched tree: nothing to grade, and this **stays** a quality
            # failure. ADR-005 V11 (B) settled that from measurement (e9 01-05
            # hit 91/90 twice): a turn-cap retry that costs nothing lets a
            # thrashing agent retry forever. The accounting is right; what was
            # wrong is the story's closing line, fixed where it is written.
            return attempt
        attempt.error = ""      # the gate's verdict is this attempt's outcome now

    # Developer session ended: **freeze candidate immediately**, before
    # verifying anything (ADR-004 R1).  Verifying first then freezing means
    # evidence points to no specific version, and "stale" becomes undefined.
    changed_now = changed_files(str(workdir), base_ref=base_ref)

    # Zero-output diagnostic: agent responded (ok=True), wrote no files,
    # and made no tool calls.  Retrying is pointless — the model can't use
    # Claude Code's tools (common when an API proxy silently routes to a
    # different model).  Only fires when output_tokens > 0 (real stream
    # data, not a mock that omits it).
    untouched = (head_sha(workdir), _tree_snapshot(workdir)) == tree_before
    if untouched and not result.tool_uses and result.output_tokens > 0:
        # THIS session's change, not the diff against the base branch: on a retry that diff carries the frozen
        # candidate's files and the check never fired (SS-59)
        snippet = (result.text or "")[:200].strip()
        attempt.error = (
            f"agent responded ({result.output_tokens} tokens, {result.num_turns} turns) "
            f"but made 0 tool calls and wrote 0 files — it cannot write code. "
            f"Likely cause: the model behind ANTHROPIC_BASE_URL does not support "
            f"Claude Code's tool protocol. Check route.developer_model in .aisef.toml "
            f"or the API proxy configuration."
        )
        attempt.infra = True
        attempt.fatal = True
        run_log(artifact_root, (
            f"story={story.id}#{number} ZERO-OUTPUT: {result.output_tokens} tokens, "
            f"0 tool calls, 0 files. Response: {snippet!r}"
        ))
        return attempt

    # An attempt that wrote nothing is not a candidate.  Two shapes of the
    # same silence, both measured on todo-e2e 2026-09-10:
    #
    # * STORY-02-01: 7 turns, 0 edits, on a retry.  `changed_now` is the diff
    #   against the base branch, so it showed the *previous* attempt's two
    #   files and the silence was invisible.
    # * STORY-03-01: 7 turns, 0 edits, on a first attempt.  `changed_now` was
    #   empty, and the gate ran anyway -- four checks red for one cause,
    #   opening with "guard did not evaluate any write in this session -- hook
    #   cannot reach worktree?", which sends the reader after a hook problem
    #   that does not exist.
    #
    # Both paid for a full verify pass, including two more agent sessions
    # (review and security), to establish what `changed_files` already knew.
    # Nothing was written, so there is nothing to grade: the gate would return
    # either the verdict it already returned, or "no changes to review".
    reuse = False
    if (head_sha(workdir), _tree_snapshot(workdir)) == tree_before:
        # The session wrote nothing. What that means depends on what is already known about THIS state —
        # the tree as it stands now, under this contract, configuration and baseline — not on whether a
        # verdict was ever recorded at this SHA (D-035: hygiene changed the tree, the SHA stayed; SS-61: the
        # verdict at this SHA was a PASS the run never acted on). `last_fresh` is the only question asked.
        now = _identity_now(story, workdir=workdir, config=config, candidate=head_sha(workdir),
                            artifact_root=artifact_root, session_id=attempt.session_id, attempt=number)
        verdict = evidence.read(story.id).last_fresh(NOTE, "gate:verdict", now)
        if verdict is not None and not verdict.ok:
            # T6: a fresh QUALITY_BLOCK over exactly this state — proven unresolved work, decision stated.
            attempt.error = (
                f"the session wrote nothing ({result.num_turns} turns) — the tree is "
                f"exactly as the session found it, so the gate has nothing to grade: its verdict is still "
                f"current, and re-running the gate would return the block it already returned."
            )
            attempt.infra = True   # never scored, so do not charge the story
            attempt.noop = True
            run_log(artifact_root, f"story={story.id}#{number} NO-OP: "
                                   f"{result.num_turns} turns, 0 files written, fresh block at {now.candidate_sha[:8]}")
            return attempt
        if not changed_now and verdict is None:
            # Nothing frozen, nothing changed against the base: there is nothing to grade at all.
            attempt.error = (
                f"the session wrote nothing ({result.num_turns} turns) — the tree is "
                f"exactly as the session found it, so the gate has nothing to grade. "
                "If the story's work is already on the main branch, the worktree "
                "forked from it and the diff stays empty however many sessions "
                "run — check the main branch before retrying."
            )
            attempt.infra = True
            attempt.noop = True
            run_log(artifact_root, f"story={story.id}#{number} NO-OP: "
                                   f"{result.num_turns} turns, 0 files written, nothing to grade")
            return attempt
        # T6': no fresh verdict over this state (the tree, the contract or the configuration changed since
        # the last one) — or a fresh PASS the run never acted on: grade it. Fresh green evidence is kept,
        # everything else re-runs; nothing is paid for twice and nothing stale scores.
        reuse = True
        run_log(artifact_root, f"story={story.id}#{number} wrote nothing, but this state has "
                               + ("a fresh passing verdict the run never acted on — re-scoring it"
                                  if verdict is not None else "no fresh verdict — grading it"))
    run_log(artifact_root, f"story={story.id}#{number} changed_files={len(changed_now)}")
    # F4 / SS-41: a path that was already there before the session and is byte-identical now is PREEXISTING —
    # an operator fixture under a granted directory is not the developer's work and never enters the candidate
    snap_now = _tree_snapshot(workdir)
    preexisting = sorted(rel for rel, content in tree_before[1].items()
                         if rel in snap_now and snap_now[rel] == content and content is not None)
    attempt.candidate = freeze_candidate(
        workdir, story=story, scope=scope, isolated=workdir != project,
        evidence=evidence, artifact_root=artifact_root, number=number,
        changed=changed_now, preexisting=preexisting,
    )
    if not attempt.candidate:
        # The freeze is authoritative: no candidate means nothing can be graded and nothing may be stamped
        # under the parent SHA (SS-A15, SS-60). An environment outcome, not the developer's.
        attempt.error = ("candidate could not be frozen — the attempt's work cannot be bound to a version, "
                         "so nothing is graded; see the candidate:frozen evidence")
        attempt.infra = True
        evidence.record(story.id, Event(kind=NOTE, name="attempt:unrunnable", ok=False,
                                        detail={"attempt": number, "reason": "freeze failed",
                                                "session_id": attempt.session_id}))
        run_log(artifact_root, f"story={story.id}#{number} UNRUNNABLE: candidate could not be frozen")
        return attempt
    run_log(artifact_root, f"story={story.id}#{number} candidate frozen sha={attempt.candidate[:8]}")
    return verify_candidate(
        story, project=project, workdir=workdir, artifact_root=artifact_root,
        client=client, config=config, catalog=catalog, architecture=architecture,
        contract=contract, attempt=attempt, base_ref=base_ref, scope=scope,
        changed=changed_now, preservation=preservation, reuse=reuse,
    )


def _identity_now(story: Story, *, workdir: Path, config: Config, candidate: str, artifact_root: Path,
                  session_id: str = "", attempt: int = 0) -> ident.EvidenceIdentity:
    """The identity of the state a decision is about to be made on (control/identity.py)."""
    epoch = contract_fingerprint(story.acceptance_criteria)
    have = story_gate.authoritative_baseline(EvidenceStore(artifact_root).read(story.id), epoch=epoch)
    root = str((have.detail.get("root") or have.detail.get("parent") or "")) if have is not None else ""
    return ident.current(story_id=story.id, story_epoch=epoch, candidate_sha=candidate, baseline_root=root,
                         workdir=workdir, config=config, session_id=session_id, attempt=attempt)


def _at(ev: Evidence, kind: str, name: str, now: "ident.EvidenceIdentity | str") -> Event | None:
    """The most recent record of a check that is **fresh** for the state being verified — the same SHA,
    tree state, contract, configuration and environment (control/identity.py). A record of another state
    is a historical fact, not something to keep. `now` may be a bare SHA for callers that know nothing else."""
    if isinstance(now, str):
        now = ident.EvidenceIdentity(candidate_sha=now)
    return ev.last_fresh(kind, name, now)


def _green_at(ev: Evidence, kind: str, name: str, sha) -> bool:
    """Evidence at the candidate sufficient to **keep**: genuinely green -- not
    skipped (unconfigured) or unrunnable; those are cheap to re-run and may
    have changed (tool just installed, command just declared)."""
    e = _at(ev, kind, name, sha)
    return bool(e and e.ok and not e.detail.get("skipped") and not e.detail.get("unrunnable"))


def _nop_at(ev: Evidence, sha) -> bool:
    """Nop evidence at the candidate sufficient to **keep**: a real result (red
    or green are both data -- green is a deterministic fail, re-running gives
    the same answer) or "story did not add/modify test files" (a SHA fact).
    Not kept when unrunnable, disabled by config, or missing test command:
    all three may have changed."""
    e = _at(ev, TOOL_RUN, NOP_RUN, sha)
    if e is None or e.detail.get("unrunnable") or e.detail.get("disabled"):
        return False
    return not e.detail.get("skipped") or ("files" in e.detail and not e.detail["files"])


def _security_as_dict(rep: SecurityReport | None) -> dict | None:
    """Security report as a persistable dict -- same shape as `tool_run security`,
    so `_security_from_evidence` reads it back identically."""
    if rep is None:
        return None
    return {"findings": [f.line() for f in rep.findings], "error": rep.error}


def _record_gate_input(evidence: EvidenceStore, story_id: str, *, attempt: int, **kw) -> None:
    """Record gate **inputs** (ADR-005 V4): all kwargs of `gate.evaluate`
    JSON-serialized, right before scoring.  The gate is pure on `Evidence` +
    13 kwargs; kwargs only live during the run, so previously every gate-rule
    fix could only be tested via unit tests or a paid agent run (0/17 scoring
    bugs caught before shipping).  With this record, `aisef gate --replay`
    re-scores a past attempt with current code, $0, deterministic -- no model
    call: reviewer/security verdicts are already in here."""
    detail = {**kw, "security": _security_as_dict(kw.get("security")), "attempt": attempt}
    evidence.record(story_id, Event(
        kind=NOTE, name="gate:input",
        detail=json.loads(json.dumps(detail, ensure_ascii=False, default=str)),
    ))


def _security_from_evidence(e: Event) -> SecurityReport:
    """Reconstruct security report from `tool_run security` -- `[severity] body`
    lines are exactly the format `parse` reads, so one noise filter scores
    both live and persisted reports."""
    rep = parse_security("\n".join(e.detail.get("findings") or []))
    rep.error = str(e.detail.get("error") or "")
    rep.unrunnable = str(e.detail.get("unrunnable") or "")
    return rep


def _repeat_runs(k: int, run_fn: Callable[[], object]) -> None:
    """Re-run a check ``k`` times on the same SHA (ADR-004 R13 `--repeat`).

    A single run cannot distinguish "red because of code" from "red because of
    machine load": e9 STORY-01-07 (bug 22) failed attempt 3 because
    `autosave.spec.ts:210` was load-sensitive, measured 10/10 green on retry --
    $28.76 for a developer session rebuilding what already existed.
    Terminal-Bench measures flake via oracle x k; here each run is a real
    `tool_run` carrying candidate, and `_repeat_note` compares test names
    across runs.  k = 1 is the old behavior, nothing extra recorded.
    """
    for _ in range(max(1, k)):
        run_fn()


def _repeat_note(evidence: EvidenceStore, sid: str, sha: str, *, k: int,
                 checks: list[str], attempt: int) -> Event:
    """Record `note verify-only.repeat`: which checks changed outcome across
    ``k`` runs on the same SHA -- the gate reads this record
    (`gate._khong_on_dinh`).

    `flaky_ids`: tests (by name, from `test_ids`/`failed_ids` of `tool_run
    test`) green in one run, red in another; `stable_red`: red in **all**
    runs -- genuinely red, gate scores FAILED as usual; `flaky_checks`:
    checks (test / lint / `qa:<kind>`) whose `ok` flipped across runs --
    allows not printing test names.  Flaky -> that check is UNRUNNABLE
    "unstable": cannot run stably != failed, != passed.  Tests present in
    one run but absent in another are not classified -- the last run decides,
    as without `--repeat`.
    """
    ev = evidence.read(sid)
    flaky_ids: list[str] = []
    stable_red: list[str] = []
    flaky_checks: list[str] = []
    for name in checks:
        runs = [e for e in ev.of(TOOL_RUN, name)
                if str(e.detail.get("candidate") or "") == sha][-k:]
        oks = [e.ok for e in runs]
        if any(oks) and not all(oks):
            flaky_checks.append(name)
        if name != "test":
            continue
        pattern: dict[str, list[bool]] = {}
        for e in runs:
            do = set(e.detail.get("failed_ids") or [])
            bo = set(e.detail.get("skipped_ids") or [])
            for t in e.detail.get("test_ids") or []:
                if t not in bo:
                    pattern.setdefault(str(t), []).append(t not in do)
        flaky_ids += [t for t, m in pattern.items() if any(m) and not all(m)]
        stable_red += [t for t, m in pattern.items() if len(m) == len(runs) and not any(m)]
    return evidence.record(sid, Event(
        kind=NOTE, name="verify-only.repeat", ok=not (flaky_ids or flaky_checks),
        detail={"k": k, "checks": checks, "flaky_ids": flaky_ids,
                "stable_red": stable_red, "flaky_checks": flaky_checks, "attempt": attempt},
    ))


def verify_candidate(
    story: Story,
    *,
    project: Path,
    workdir: Path,
    artifact_root: Path,
    client: ClientAdapter,
    config: Config,
    catalog: Catalog,
    architecture: Architecture | None,
    contract: DesignContract | None,
    attempt: Attempt,
    base_ref: str,
    scope: list[str],
    changed: list[str],
    preservation: list[dict],
    reuse: bool = False,
    repeat: int = 1,
) -> Attempt:
    """Second half of an attempt -- verify, review, score gate -- on the
    candidate frozen at `attempt.candidate`.

    ``repeat`` (R13 `--repeat k`): each **re-runnable** check (test, lint,
    `qa:<kind>`) runs k times on the same SHA, then `note verify-only.repeat`
    records tests that changed outcome across runs -- see
    `_repeat_runs`/`_repeat_note`.

    Separated from `run_attempt` so re-verify attempts (ADR-004 R13) follow
    **exactly this path**, with no second copy to drift.  `reuse=False` is
    the normal path: run everything.  `reuse=True`: each check runs only when
    its latest evidence is not green at the correct candidate (fail, missing,
    unconfigured, unrunnable, or belongs to a different version); review and
    security are **kept** when both the session (`agent_run`) and conclusion
    (`tool_run review|security`) are at this SHA -- including blocking
    conclusions.  This is what R1 makes meaningful: a reviewer's words
    describe one version; if the version hasn't changed the words still hold,
    re-asking pays for the same answer.  Gate scores identically on both
    paths -- no relaxation, just no paying to rebuild what already exists.
    """
    sid, sha, number = story.id, attempt.candidate, attempt.number
    from ..harness.runlog import run_log

    def _log(msg: str) -> None:
        run_log(artifact_root, msg)

    _log(f"story={sid}#{number} verify START sha={sha[:8]}")
    now = _identity_now(story, workdir=workdir, config=config, candidate=sha, artifact_root=artifact_root,
                        session_id=attempt.session_id, attempt=number)
    attempt.identity = now.as_dict()
    token = ident.CURRENT.set(now)      # every store built below stamps this attempt's identity
    try:
        return _verify_candidate_under(now, story, project=project, workdir=workdir, artifact_root=artifact_root,
                                       client=client, config=config, catalog=catalog, architecture=architecture,
                                       contract=contract, attempt=attempt, base_ref=base_ref, scope=scope,
                                       changed=changed, preservation=preservation, reuse=reuse, repeat=repeat)
    finally:
        ident.CURRENT.reset(token)


def _verify_candidate_under(now: ident.EvidenceIdentity, story: Story, *, project: Path, workdir: Path,
                            artifact_root: Path, client: ClientAdapter, config: Config, catalog: Catalog,
                            architecture: Architecture | None, contract: DesignContract | None, attempt: Attempt,
                            base_ref: str, scope: list[str], changed: list[str], preservation: list[dict],
                            reuse: bool, repeat: int) -> Attempt:
    sid, sha, number = story.id, attempt.candidate, attempt.number
    from ..harness.runlog import one_line, run_log

    def _log(msg: str) -> None:
        run_log(artifact_root, msg)

    evidence = EvidenceStore(artifact_root, identity=now)
    # Read **once, before** re-running anything: re-run checks write new
    # events, and keep/run decisions must be based on evidence at entry time.
    ev = evidence.read(sid) if reuse else None

    def keep(name: str, sufficient: bool) -> bool:
        """True = keep existing evidence, do not run.  Logged on both paths."""
        if not reuse:
            return False
        (attempt.kept if sufficient else attempt.reran).append(name)
        if sufficient:
            _log(f"story={sid}#{number} {name} KEPT (reuse)")
        return sufficient

    # Nop control (ADR-005 V3) right after freeze: story's tests at parent SHA.
    if not keep(NOP_RUN, reuse and _nop_at(ev, now)):
        # the parent the control compares against is the epoch's baseline root — not a fork point recomputed
        # after main moved (SS-22, INV-C.1)
        # ...a root that stands BEFORE the story: in a non-isolated project the baseline root is HEAD itself,
        # which is the story's own build, and the control stays unrunnable there as before
        nop_ref = now.baseline_root if (now.baseline_root and now.baseline_root != sha) else base_ref
        run_nop(story, workdir=workdir, artifact_root=artifact_root, config=config,
                candidate=sha, base_ref=nop_ref, changed=changed)

    # Harness re-runs tests and lint: evidence must be recorded by the
    # harness, and the agent may have "forgotten" to run after the last edit.
    chay_lai: list[str] = []  # checks run this attempt -- `_repeat_note` compares across k runs
    for tool in ("test", "lint"):
        if not keep(tool, reuse and _green_at(ev, TOOL_RUN, tool, now)):
            _repeat_runs(repeat, partial(
                run_tool, tool, workdir, story_id=sid, artifact_root=artifact_root,
                config=config, candidate=sha,
            ))
            chay_lai.append(tool)
            last = evidence.read(sid).last(TOOL_RUN, tool)
            _log(f"story={sid}#{number} {tool} {'PASS' if last and last.ok else 'FAIL'}")

    # Tests always green because they assert nothing is worse than no tests:
    # it makes the "tests green" gate meaningless.  Checking is cheap, run every attempt.
    if not keep("qa:fake-tests", reuse and _green_at(ev, TOOL_RUN, "qa:fake-tests", now)):
        fake = find_fake_tests(workdir, changed)
        evidence.tool_run(sid, "qa:fake-tests", ok=not fake, detail={"files": fake})
        if fake:
            _log(f"story={sid}#{number} qa:fake-tests FAIL {len(fake)} file(s)")

    # Story's verification contract: run exactly the kinds it must pass.
    # Not a new phase -- same `run_suite` machinery, just scoped.
    # `verify.X` left empty is still **unconfigured**, not passed: that's
    # what `run_suite` already distinguishes, and the gate reads it as such.
    # R4: also add verification kinds and screens from behaviors to preserve
    # -- the "preservation" gate can only score what was run at this
    # candidate, and "not run" means it says UNRUNNABLE, not passed.
    hop_dong, man_hinh = validation_targets(story, preservation)
    kinds = [k for k in hop_dong
             if not keep(f"qa:{k}", reuse and _green_at(ev, TOOL_RUN, f"qa:{k}", now))]
    if kinds:
        # `clean=False`: worktree is already frozen at the correct SHA and
        # write-scope guard blocked out-of-scope changes -- clean worktree
        # (V6) is for project-level verification, where the tree could be
        # anyone's.
        _repeat_runs(repeat, partial(
            run_suite,
            workdir,
            config=config,
            only=kinds,
            has_ui=bool(man_hinh),
            story_id=sid,
            artifact_root=artifact_root,
            changed=changed,
            candidate=sha,
            clean=False,
        ))
        chay_lai += [f"qa:{k}" for k in kinds]
        _log(f"story={sid}#{number} qa suite ran={','.join(kinds)}")
    if repeat > 1:
        _repeat_note(evidence, sid, sha, k=repeat, checks=chay_lai, attempt=number)

    screens = [m for m in man_hinh
               if not keep(f"mockup:{m}", reuse and _green_at(ev, MOCKUP_MAP, m, now))]
    if screens and contract:
        _log(f"story={sid}#{number} mockup verify screens={','.join(screens)}")
        mv_result = mockup_verify.verify_screens(
            workdir, contract, screens,
            config=config, story_id=sid, artifact_root=artifact_root,
            candidate=sha,
        )
        if mv_result.unavailable:
            _log(f"story={sid}#{number} mockup UNAVAILABLE: {mv_result.unavailable}")
            for scr in screens:
                # `ok=False`: the comparison did not happen. 1.2.13 wrote
                # `ok=True` here to stop the gate blocking on "not compared",
                # which turned a check that verified nothing into a green ✅ —
                # the exact confusion `Outcome` exists to prevent. The gate
                # reads `unavailable` and scores it **unconfigured**: named,
                # not blocking, and not a pass.
                evidence.record(sid, Event(
                    kind=MOCKUP_MAP, name=scr, ok=False,
                    detail={"unavailable": mv_result.unavailable, "candidate": sha},
                ))

    # Reused only when the record carries a verdict: a review that did not
    # execute (max_turns, timeout, tree modified, candidate moved) is not
    # evidence about the candidate, however recent (D-032).
    review_ev = _at(ev, TOOL_RUN, "review", now) if reuse else None
    if keep("review", bool(review_ev and _at(ev, AGENT_RUN, f"{sid}-review", sha)
                           and _review_complete(review_ev))):
        attempt.review_findings = list(review_ev.detail.get("findings") or [])
        attempt.plan_findings = list(review_ev.detail.get("plan") or [])
        attempt.review_unrunnable = ""
        attempt.review_attempt = int(review_ev.detail.get("review_attempt") or 0)
    else:
        attempt.review_findings, verdict, attempt.review_unrunnable = review_story_v2(
            story,
            workdir=workdir,
            base_ref=base_ref,
            project=project,
            artifact_root=artifact_root,
            client=client,
            config=config,
            catalog=catalog,
            architecture=architecture,
            number=number,
            candidate=sha,
            preservation=preservation,
        )
        attempt.plan_findings = structured_plan_defects(verdict)
        attempt.review_attempt = _review_executions(evidence.read(sid), sid, sha)
        review_outcome = (REVIEW_UNRUNNABLE if attempt.review_unrunnable
                          else REVIEW_BLOCK if attempt.review_findings else REVIEW_PASS)
        # Blocking items must live in evidence, not just in the truncated
        # summary printed to screen -- when checking whether this attempt and
        # the previous were blocked for the same reason, the full text must
        # be readable.  Without this, the only way is to dig through session
        # logs.  Re-verify attempts read back exactly this record instead of
        # calling the model again.
        evidence.tool_run(
            sid,
            "review",
            ok=review_outcome == REVIEW_PASS,
            detail={"findings": attempt.review_findings, "plan": attempt.plan_findings,
                    "attempt": number, "outcome": review_outcome,
                    "unrunnable": attempt.review_unrunnable,
                    "review_attempt": attempt.review_attempt},
        )
        n_blocking = len(attempt.review_findings)
        if attempt.review_unrunnable:
            _log(f"story={sid}#{number} review UNRUNNABLE (execution {attempt.review_attempt}) "
                 f"· {one_line(attempt.review_unrunnable)}")
        else:
            _log(f"story={sid}#{number} review {'PASS' if not n_blocking else f'FAIL blocking={n_blocking}'}")
        for f in attempt.review_findings:
            _log(f"story={sid}#{number} review ✗ {one_line(f)}")

    if _verifier_budget_cap(attempt):
        _log(f"story={sid}#{number} security SKIPPED — budget cap reached in the review session (no further session)")
    elif config.get("security.semantic_review", True):
        security_ev = _at(ev, TOOL_RUN, "security", now) if reuse else None
        if keep("security", bool(security_ev and not security_ev.detail.get("unrunnable")
                                 and _at(ev, AGENT_RUN, f"{sid}-security", now))):
            attempt.security = _security_from_evidence(security_ev)
        else:
            attempt.security = security_review(
                story,
                workdir=workdir,
                base_ref=base_ref,
                project=project,
                artifact_root=artifact_root,
                client=client,
                config=config,
                catalog=catalog,
                architecture=architecture,
                number=number,
                candidate=sha,
                preservation=preservation,
            )
            sec_ok = not (attempt.security.error or attempt.security.unrunnable
                         or attempt.security.blocking(config["security.block_severities"]))
            evidence.tool_run(
                sid,
                "security",
                ok=sec_ok,
                detail={
                    "findings": [f.line() for f in attempt.security.findings],
                    "filtered": len(attempt.security.filtered),
                    "error": attempt.security.error,
                    "unrunnable": attempt.security.unrunnable,
                    "outcome": (SECURITY_UNRUNNABLE if attempt.security.unrunnable else
                                "PASS" if sec_ok else "BLOCK"),
                    "attempt": number,
                },
            )
            _log(f"story={sid}#{number} security "
                 f"{'UNRUNNABLE' if attempt.security.unrunnable else 'PASS' if sec_ok else 'FAIL'} "
                 f"findings={len(attempt.security.findings)} filtered={len(attempt.security.filtered)}"
                 + (f" · {one_line(attempt.security.unrunnable)}" if attempt.security.unrunnable else ""))
            if not sec_ok:
                if attempt.security.error:
                    _log(f"story={sid}#{number} security ✗ {one_line(attempt.security.error)}")
                for f in attempt.security.blocking(config["security.block_severities"]):
                    _log(f"story={sid}#{number} security ✗ {one_line(f.line())}")

    dau_vao = dict(
        changed=changed,
        write_scope=scope,
        screens=list(story.screens),
        contract=verification_contract(story),
        review_blocking=attempt.review_findings,
        review_unrunnable=attempt.review_unrunnable,
        security=attempt.security,
        block_severities=config["security.block_severities"],
        guard_expected=guard_expected(project, getattr(client, "id", "")),
        acceptance=len(story.acceptance_criteria),
        coverage_min=float(config["coverage.min"]),
        added_tests=tdd.added_tests(workdir, base_ref=base_ref, changed=changed, story_id=sid),
        candidate=sha,
        preservation=preservation,
    )
    # Inputs recorded **before** reading evidence to score: replay rebuilds
    # exactly the event set the gate saw by cutting at this record's seq (V4).
    _record_gate_input(evidence, sid, attempt=number, **dau_vao)
    attempt.gate = story_gate.evaluate(sid, evidence.read(sid), identity=now, **dau_vao)
    attempt.ok = attempt.gate.passed
    # Gate outcome goes into evidence, carrying candidate SHA: the behavior
    # ledger (R2) treats "passed gate at this candidate" as a per-attempt
    # landed signal -- implement does not merge, and `attempt.committed`
    # closes the transaction even on failure.
    evidence.record(sid, Event(
        kind=NOTE, name="gate:verdict", ok=attempt.ok,
        detail={"failures": [c.name for c in attempt.gate.failures][:20], "attempt": number,
                # Scoring contract (ADR-005 V9): each item carries `kind` and
                # `evidence` pointer -- replay/bench reads from here, not from summary.
                "checks": [c.as_dict() for c in attempt.gate.checks]},
    ))
    if attempt.ok:
        _log(f"story={sid}#{number} gate PASSED")
    else:
        # Names first (one grep-able line), then one line per failed check with
        # its reason. Naming the checks without their detail forced the reader
        # into the evidence file to learn anything — the log said which gate
        # failed, never why.
        _log(f"story={sid}#{number} gate FAILED: {','.join(c.name for c in attempt.gate.failures)}")
        for c in attempt.gate.failures:
            _log(f"story={sid}#{number} gate ✗ {c.name} · {c.outcome.value} · "
                 + (one_line(c.detail) or "(no detail recorded)"))
        # An escape path nobody is told about is not an escape path. When the
        # only thing between this story and done is a model's opinion, the log
        # says so and names the command — measured: 15 of todo-e2e's 19
        # blocking attempts were exactly this shape.
        if story_gate.judge_only(attempt.gate):
            _log(f"story={sid}#{number} gate judge-only: `review` is the only blocking "
                 f"check and it is model-scored. If the claim is wrong: "
                 f"`aisef gate {sid} --waive-review --reason ...`")
    return attempt


def run_baseline(story: Story, *, workdir: Path, artifact_root: Path, config: Config,
                 base_ref: str = "") -> None:
    """Run tests at the **parent candidate** before the developer changes
    anything (ADR-004 R9).

    HoH tells the developer "establish a baseline before editing"; here the
    harness does it, because developer words are not evidence.  Recorded as
    `test:baseline` (see `tools.BASELINE_RUN` for why not `test`), with
    `parent` = HEAD at run time and `red_before` = tests already red -- gate
    does not count them as regressions, and readers see why immediately.

    Runs **once per story**, before the first attempt, not per-attempt:
    attempt 2 using attempt 1's candidate as baseline would reclassify
    attempt 1's newly red tests as "already red", and attempt 2 removing
    them passes the gate cleanly.  Baseline is the state before the story
    touched anything -- cost is one test run per story, not per attempt.

    No test command means the record carries `skipped` (gate reads as
    unconfigured), not a green baseline.  Disabled via `verify.baseline`
    records it explicitly as disabled, so the gate says "not applicable"
    instead of silence.

    ``base_ref`` (fork point) recorded alongside ``parent`` so the gate knows
    whether this baseline stands **before** the story: a re-run reconnects
    the story branch, HEAD at baseline time is the story's own version
    (e9 01-07 run 3: `parent` = candidate `a60612e`), and all story tests
    are already green there -- nop level 1 must know to avoid false
    positives (ADR-005 V3).
    """
    from ..control.acceptance import contract_fingerprint
    from ..harness.runlog import run_log
    run_log(artifact_root, f"story={story.id} baseline START")
    store = EvidenceStore(artifact_root)
    head = head_sha(workdir)
    root = base_ref or head              # the integrated parent at story entry (project HEAD without a worktree)
    epoch = contract_fingerprint(story.acceptance_criteria)
    # Immutable within the story epoch (D-033): a retry, a resumed run or a
    # re-verification reuses the record captured when the story began. Taking
    # a new one at the worktree HEAD of a resumed story would baseline the
    # story's own candidate (LedgerLock STORY-03-01, ca37cc44).
    have = story_gate.authoritative_baseline(store.read(story.id), epoch=epoch)
    if have is not None and not have.detail.get("unrunnable"):
        run_log(artifact_root, f"story={story.id} baseline REUSED seq={have.seq} root={root[:8]} "
                               f"— immutable within the story epoch")
        return
    if not config.get("verify.baseline", True):
        store.tool_run(story.id, BASELINE_RUN, ok=False, detail={
            "baseline": True, "disabled": True, "root": root, "epoch": epoch,
            "skipped": "disabled by config `verify.baseline`",
        })
        return
    if base_ref and head and head != root:
        # The worktree stands at the story's own build; the baseline belongs at the integrated parent. The
        # root is known, so capture it THERE — a temporary worktree at `root` (SS-18, INV-C.3) — rather than
        # declaring the baseline unavailable for the whole epoch. Never synthesise one from the story's build.
        from ..control.worktree import WorktreeManager
        try:
            with WorktreeManager(Path(workdir)).temporary(root, label="baseline") as tmp:
                run_log(artifact_root, f"story={story.id} baseline at root {root[:8]} via a temporary worktree "
                                       f"(head={head[:8]})")
                res = run_tool("test", tmp, config=config)
                log = parse_testlog(res.stdout + "\n" + res.stderr)
                record_tool(res, story.id, artifact_root, name=BASELINE_RUN, extra={
                    "baseline": True, "root": root, "epoch": epoch, "parent": root, "base_ref": base_ref,
                    "captured_at": "temporary worktree at root", "red_before": log.failed[:MAX_IDS],
                })
                run_log(artifact_root, f"story={story.id} baseline DONE ok={res.ok} red_before={len(log.failed)}"
                                       + (f" unrunnable={res.unrunnable}" if res.unrunnable else ""))
                return
        except Exception as e:  # noqa: BLE001 — a refused temporary worktree is a typed, recorded outcome
            store.tool_run(story.id, BASELINE_RUN, ok=False, detail={
                "baseline": True, "root": root, "epoch": epoch, "parent": head, "base_ref": base_ref,
                "unrunnable": (f"BASELINE_UNAVAILABLE: the worktree stands at {head[:8]}, not at the integrated "
                               f"parent {root[:8]}, and a temporary worktree at the root could not be created: {e}"),
            })
            run_log(artifact_root, f"story={story.id} baseline UNAVAILABLE head={head[:8]} root={root[:8]}: {e}")
            return
    res = run_tool("test", workdir, config=config)   # story_id empty: recorded below, under its own name
    log = parse_testlog(res.stdout + "\n" + res.stderr)
    record_tool(res, story.id, artifact_root, name=BASELINE_RUN, extra={
        "baseline": True, "root": root, "epoch": epoch, "parent": head, "base_ref": base_ref,
        "red_before": log.failed[:MAX_IDS],
    })
    # Say *why* when it could not run: `ok=False` alone sends the reader to the
    # evidence JSONL to find out whether the baseline was red or never started.
    run_log(artifact_root, f"story={story.id} baseline DONE ok={res.ok} "
                           f"red_before={len(log.failed)}"
                           + (f" unrunnable={res.unrunnable}" if res.unrunnable else ""))


def _vang_ma_cua_story(res, changed: list[str]) -> str:
    """The story source file the nop run says is missing — "" if none is.

    Only the story's **own** non-test files count: a dependency the project
    never installed is a real environment failure and must stay unrunnable.
    """
    from ..harness.tools import NO_DEPENDENCIES, NO_SETUP

    if not res.unrunnable.startswith(NO_SETUP):
        return ""                          # tool missing, no manifest: not this
    ra = res.output()[0].lower().replace("\\", "/")
    if not any(m in ra for m in NO_DEPENDENCIES):
        return ""
    # SS-26 / INV-F.3: the missing module is the NAME the exception names, not a substring of the traceback — a
    # third-party import failing while the story's file loads is still an environment failure
    import re as _re
    missing = {n.strip("./").rstrip("/").replace(".", "/").lower()
               for n in _re.findall(r"(?:cannot find (?:module|package)|no module named)\s*['\"]([^'\"]+)['\"]", ra)}
    for f in changed:
        if is_test_path(f):
            continue
        goc = PurePosixPath(f).with_suffix("").as_posix().lower()
        if len(goc) < 3:
            continue
        if any(n == goc or goc.endswith("/" + n) or n.endswith("/" + goc) for n in missing if len(n) >= 3):
            return f
    return ""


def run_nop(story: Story, *, workdir: Path, artifact_root: Path, config: Config,
            candidate: str, base_ref: str, changed: list[str]) -> None:
    """Nop control level 2 (ADR-005 V3): run story tests at **parent SHA**.

    Terminal-Bench accepts a task only when oracle >= 1 **and** nop < 1;
    BERBench records `base_fail`.  Here: temp worktree at parent SHA, copy
    into it **test files the story added/modified** (test files in `changed`
    per `is_test_path` -- `tdd.added_tests` is a subset, so one filter
    suffices; source code is not copied), run `tools.test`, record `test:nop`
    carrying `candidate`.  Gate reads: tests carrying criteria code must be
    red or nonexistent there -- import error from missing story module is
    red, and valid.

    Parent SHA = fork point (`base_ref`) when available -- baseline
    **before** the story even on re-runs; absent (running directly in
    project) falls back to `test:baseline.parent`; absent too records
    unrunnable, does not guess.  Only `tools.test` (unit), not `qa:e2e`
    (bug 22: load-sensitive).  Temp worktree shares the `.aisef/worktrees/`
    root with the story worktree -- same `node_modules`/venv discovery, so
    if baseline runs then nop runs; cleaned up even on error.
    Disabled via `verify.nop` still records a `disabled` entry so the gate
    says "not applicable: disabled", not silence.  Story did not add/modify
    test files -> records `files: []`, nothing built.
    """
    from ..control.worktree import GitError, WorktreeManager, main_repo
    from ..harness.runlog import run_log

    store = EvidenceStore(artifact_root, candidate=candidate)
    if not config.get("verify.nop", True):
        run_log(artifact_root, f"story={story.id} nop SKIP disabled")

        store.tool_run(story.id, NOP_RUN, ok=False, detail={
            "nop": True, "disabled": True, "skipped": "disabled by config `verify.nop`"})
        return
    test_files = [f for f in changed if is_test_path(f)]
    if not test_files:
        run_log(artifact_root, f"story={story.id} nop SKIP no test files changed")
        store.tool_run(story.id, NOP_RUN, ok=False, detail={
            "nop": True, "files": [], "skipped": "story did not add/modify test files"})
        return
    base_ev = story_gate.authoritative_baseline(EvidenceStore(artifact_root).read(story.id))
    parent_ref = base_ref or (str(base_ev.detail.get("parent") or "") if base_ev is not None else "")
    if not parent_ref:
        store.tool_run(story.id, NOP_RUN, ok=False, detail={
            "nop": True, "files": test_files[:50],
            "unrunnable": "cannot determine parent SHA (no fork point or baseline)"})
        return

    run_log(artifact_root, f"story={story.id} nop START parent={parent_ref[:8]} test_files={len(test_files)}")
    wt = WorktreeManager(main_repo(workdir))
    nop_id = f"{story.id}-nop"
    try:
        wt.remove(nop_id, delete_branch=True)      # leftover from a previous crash
        tmp_path = wt.create(nop_id, base=parent_ref, refresh=False).path
        for f in test_files:
            src, dst = Path(workdir) / f, tmp_path / f
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            elif dst.exists():
                dst.unlink()                        # story deleted test file: parent SHA also lacks it
        res = run_tool("test", tmp_path, config=config)   # story_id empty: recorded below, under its own name
        if (vang := _vang_ma_cua_story(res, changed)):
            # The nop worktree deliberately lacks the story's source, so
            # "cannot find module <story file>" is the control **working**,
            # not a broken environment. Told apart only by *which* module is
            # missing — and only here, where the story's own changed files
            # are known (lỗi 120). On a greenfield project's first story
            # there are no other tests to print a name, so the generic rule
            # ("unrunnable unless something passed") cannot tell the two
            # apart, and the strongest control was recorded as not performed
            # exactly where it matters most (todo-cli STORY-01-01 2026-09-13).
            run_log(artifact_root, f"story={story.id} nop red vì thiếu {vang} — "
                                   f"đúng thứ control dựng ra để thấy")
            res.unrunnable = ""
        record_tool(res, story.id, artifact_root, candidate, name=NOP_RUN, extra={
            "nop": True, "parent": parent_ref, "base_ref": base_ref, "files": test_files[:50]})
        # `ok` here is the **test run**, and for the nop control red is the
        # wanted result: green at the parent SHA means the tests do not verify
        # the story. `ok=False` read as a failure for months; say what it means.
        # "Could not run" is not "red". A test command that fails to start
        # (exit 127 on Windows before 1.2.29) makes `ok=False`, and calling
        # that the expected result reports a control that never happened.
        ket = ("could not run at parent — control NOT performed: " + res.unrunnable
               if res.unrunnable else
               "tests red at parent (expected)" if not res.ok else
               "tests GREEN at parent — they do not verify the story")
        run_log(artifact_root,
                f"story={story.id} nop DONE {ket} {res.duration_ms}ms")
    except GitError as e:
        run_log(artifact_root, f"story={story.id} nop ERROR {e}")
        store.tool_run(story.id, NOP_RUN, ok=False, detail={
            "nop": True, "parent": parent_ref, "files": test_files[:50],
            "unrunnable": f"cannot create worktree at parent SHA: {e}"})
    finally:
        wt.remove(nop_id, delete_branch=True)


def freeze_candidate(
    workdir: Path,
    *,
    story: Story,
    scope: list[str],
    isolated: bool,
    evidence: EvidenceStore,
    artifact_root: Path,
    number: int,
    changed: list[str],
    verify_only: bool = False,
    preexisting: list[str] | None = None,
) -> str:
    """Freeze the developer session's work into **one version** and return
    its SHA. ``preexisting`` paths (there before the session, unchanged by it) are left out of the candidate and
    recorded (F4 / SS-41).

    This is what HoH calls *frozen candidate*: from here to end of attempt,
    nothing may modify the tree, and all checks refer to exactly this version.
    Before ADR-004 R1 the harness committed **after** verification and review
    -- evidence pointed to no specific version, so "which code did this test
    run on" had no answer.

    Nothing to commit means the candidate is the current HEAD (agent already
    committed).  Running directly in the project (`--no-isolate`) does
    **not** commit: there is no dedicated branch, and committing to the
    user's trunk is not an attempt's job.  ``verify_only`` marks the
    re-verify checkpoint (R13) -- no developer session preceded it, log
    readers must see that.
    """
    from ..control.worktree import GitError, commit_paths

    error = ""
    if isolated:
        try:
            commit_paths(Path(workdir), f"{story.id}: candidate attempt {number}", paths=scope, exclude=preexisting or None)
        except GitError as e:
            error = str(e)
    sha = head_sha(workdir)

    journal = JournalStore(artifact_root)
    # Sequence number **of the open transaction**, not the attempt count in
    # the story: `open_attempt()` closes an attempt by matching this number,
    # so writing a different number here leaves an "unclosed" attempt and
    # the next run cleans it up incorrectly.
    giao_dich = journal.read(story.id).attempt_no or number
    journal.record(story.id, JEntry(
        step="changes.detected", attempt=giao_dich,
        data={"luot": number, "files": changed[:50], "preexisting_excluded": (preexisting or [])[:20], "count": len(changed)}))
    journal.record(story.id, JEntry(
        step="candidate.frozen", attempt=giao_dich,
        data={"luot": number, "sha": sha, "error": error, "verify_only": verify_only}))
    if error or not sha:
        # Failed to freeze means subsequent evidence is attached to a version
        # that **does not** contain the work.  Recorded in evidence; silence
        # here would leave a gate scoring on sand.
        evidence.tool_run(story.id, "candidate:frozen", ok=False,
                          detail={"error": error or "cannot read HEAD", "attempt": number})
        return ""      # no candidate: the caller must not grade (SS-A15, SS-60)
    return sha


#: Char cap for diff in the review prompt.  Sufficient for a right-sized
#: story; exceeding the cap means the story is too large, and truncating
#: here is better than overflowing context.
REVIEW_DIFF_CHARS = 60_000


def review_diff(workdir: str, changed: list[str], *, base_ref: str = "") -> str:
    """Actual diff for review, falling back to file list when unavailable.

    Providing only filenames forces the reviewer to re-read each file -- measured
    on e9 at 31-43 tool calls and 12 minutes for a small story, mostly spent
    rebuilding what the harness already knows.  The diff does not replace reading
    surrounding code, it just removes the initial fumbling.
    """
    names = "\n".join(f"- {c}" for c in changed[:50])
    if not base_ref or not changed:
        return names
    # Limited to the story's **own** files. An unlimited `git diff` also shows
    # what the harness itself wrote into the worktree — it refreshes the guard
    # plugin there on every run — and the reviewer then blocks the story for
    # "modifies a file outside the effective write scope" while the security
    # reviewer files a finding against the harness's own generated code.
    # Measured on todo/STORY-01-02 2026-09-09: two attempts, both blocked on
    # `.opencode/plugin/aisef-guard.ts`, story marked stuck. `changed` already
    # excludes HARNESS_OWNED; the diff has to honour the same list.
    pathspec = ["--", *changed]
    lines = _git_lines_text(workdir, ["diff", "--stat", base_ref, *pathspec])
    body = _git_lines_text(workdir, ["diff", base_ref, *pathspec])
    if not body:
        return names
    if len(body) > REVIEW_DIFF_CHARS:
        body = body[:REVIEW_DIFF_CHARS] + "\n… (diff truncated, read files directly for the rest)"
    out = [names, ""]
    if lines:
        out += ["```", lines.strip(), "```", ""]
    out += ["```diff", body, "```"]
    return "\n".join(out)


def _git_lines_text(workdir: str, args: list[str]) -> str:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", *args], cwd=workdir, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout if proc.returncode == 0 else ""


def review_story(
    story: Story,
    *,
    workdir: Path,
    base_ref: str = "",
    project: Path,
    artifact_root: Path,
    client: ClientAdapter,
    config: Config,
    catalog: Catalog,
    architecture: Architecture | None,
    number: int = 0,
    candidate: str = "",
    preservation: list[dict] | None = None,
) -> list[str]:
    """Independent review -- **new session**, cannot modify anything.

    Returns list of ``[blocker]`` items.  The author already believes the code
    is correct; asking the same session only returns the same belief.

    Signature kept for the old call flow; machine-readable version is in
    `review_story_v2`.
    """
    findings, _verdict, unrunnable = review_story_v2(
        story, workdir=workdir, base_ref=base_ref, project=project,
        artifact_root=artifact_root, client=client, config=config,
        catalog=catalog, architecture=architecture, number=number,
        candidate=candidate, preservation=preservation,
    )
    return findings if not unrunnable else [f"{_LEGACY_UNRUN} {unrunnable}"]


def _review_session(
    client: ClientAdapter, spec, *, store: EvidenceStore, story_id: str,
    artifact_root: Path, workdir: Path, name: str, role: str, number: int,
):
    """One review session: run, record evidence, revert tree if modified.

    Full text recorded **after** tree comparison: the artifact may live in the
    working tree itself (no isolation) and the review text file is not "the
    reviewer modifying the tree".
    """
    before_snap = _tree_snapshot(workdir)
    try:
        result = _reserved_client_run(
            client, spec, story_id=story_id, estimate_turns=1,
        )
    except BudgetExceeded as e:
        # Review sessions are recoverable: record a synthesised failure
        # result so the rest of the pipeline can react.  Attempt is left
        # at its previous `ok` state and the failure is surfaced through
        # the evidence store as ``infra``.
        # SS-12: one RunResult type (clients.stream), never the mockup phase's. A cap and a locked ledger are
        # different outcomes; `raw_result` says which so the stage routes typed (SS-21).
        result = RunResult(ok=False, error=f"budget exceeded: {e}", cost_usd=0.0, num_turns=0,
                           raw_result={"budget": "locked" if isinstance(e, BudgetLocked) else "cap"})
    store.agent_run(story_id, result, name=name, prompt_chars=len(spec.prompt),
                    role=role, model=spec.model, client=client.id)
    for sk in skills_used(result):
        store.record(story_id, Event(kind=SKILL_USE, name=sk, detail={"role": role}))
    reverted = _revert_reviewer_writes(workdir, before_snap, _tree_snapshot(workdir))
    persist_verdict(artifact_root, story_id, role, number, result)
    return result, reverted


def _with_schema(client: ClientAdapter, spec, result, *, store: EvidenceStore,
                 story_id: str, artifact_root: Path, workdir: Path, role: str,
                 number: int):
    """Demand JSON block per schema; missing means retry **exactly once**
    (R8).

    Returns `(text, verdict, why)`: `text` is the human-readable version -- second
    attempt if it has correct schema, otherwise the first attempt's text; `why` names
    the reason the retry could not EXECUTE (budget cap, cut, moved candidate, reverted
    tree) so the caller reports that, never "answered in prose twice" (SS-12/F2).
    """
    verdict = review_verdict(result.text)
    if verdict is not None and (role != "review" or verdict.verdict == "pass" or verdict.bound_blocking()):
        return result.text, verdict, ""
    reminder = SCHEMA_REMINDER
    if verdict is not None:                                    # a verdict whose blockers bind to nothing (F3 / D-002)
        store.record(story_id, Event(kind=NOTE, name=f"{role}:unbound", ok=False,
                                     detail={"verdict": verdict.verdict, "findings": verdict.unbound(), "retried": True}))
        reminder = BINDING_REMINDER
    lai, reverted = _review_session(
        client, replace(spec, prompt=spec.prompt + reminder), store=store,
        story_id=story_id, artifact_root=artifact_root, workdir=workdir,
        name=f"{story_id}-{role}-retry", role=f"{role}-retry", number=number,
    )
    lech = _candidate_moved(workdir, store.candidate)
    if lech:
        # Retry is also checked for candidate (R1): changed version means words don't count.
        store.tool_run(story_id, f"{role}:candidate", ok=False,
                       detail={"expected": store.candidate, "got": lech,
                               "attempt": number, "retry": True})
        # SS-A10 (schema-retry half, differential seed 232): the reviewer's commit is undone here too, or the frozen
        # candidate is gone for every later reader
        _restore_candidate_after_review_commit(store, story_id, workdir, candidate=store.candidate, got=lech,
                                               number=number)
        return result.text, None, f"candidate changed during the schema retry ({store.candidate[:7]} → {lech[:7]}) — restored"
    if reverted:
        # Retry is also checked by the "review does not write tree" invariant;
        # discard its words, and say so -- silent revert means nobody knows.
        store.tool_run(
            story_id, f"{role}:immutable", ok=False,
            detail={"changed": reverted[:20], "retry": True},
        )
    if reverted:
        return result.text, None, "the reviewer modified the working tree during the schema retry — reverted"
    if not lai.ok:
        return result.text, None, f"could not run the schema retry: {lai.error}"
    verdict = review_verdict(lai.text)
    if verdict is None:
        return result.text, None, ""
    if role == "review" and verdict.verdict != "pass" and not verdict.bound_blocking():
        store.record(story_id, Event(kind=NOTE, name=f"{role}:unbound", ok=False,
                                     detail={"verdict": verdict.verdict, "findings": verdict.unbound(), "retried": False}))
        return lai.text, None, ("the reviewer's blockers bind to no file, behaviour or criterion — twice; a blocker "
                                "must name what it blocks (INV-F.2)")
    return lai.text, verdict, ""


def review_story_v2(
    story: Story,
    *,
    workdir: Path,
    base_ref: str = "",
    project: Path,
    artifact_root: Path,
    client: ClientAdapter,
    config: Config,
    catalog: Catalog,
    architecture: Architecture | None,
    number: int = 0,
    candidate: str = "",
    preservation: list[dict] | None = None,
) -> tuple[list[str], Verdict | None, str]:
    """Like `review_story`, but also returns the machine-readable version
    (`behavior_id`, etc.) and, third, **why the reviewer did not execute**
    ("" when it did). A non-empty third value is REVIEW_UNRUNNABLE: the
    findings are then empty — an absent reviewer has no findings (D-032).

    The behavior ledger flow (R2) reads `note:review:verdict` in evidence to
    record GAP with source `reviewer`; here it just returns for any caller
    that needs it.
    """
    changed = changed_files(str(workdir), base_ref=base_ref)
    if not changed:
        # Name exactly two possibilities.  "Nothing to review" is usually
        # not a lazy agent: more commonly the story's work is already on
        # the main branch -- worktree forked from it so diff is empty -- and
        # then the advice "fix write_scope" leads readers astray.
        return [
            "no changes to review: either the run wrote nothing, or the "
            "story's work is already on the main branch (worktree forked "
            "from it so diff is empty). Check the main branch first; if "
            "the work is already there, this story is done."
        ], None, ""

    context = build_context(
        story,
        project=project,
        artifact_root=artifact_root,
        architecture=architecture,
        contract=None,
        config=config,
        preservation=preservation,
    )
    context["diff_summary"] = review_diff(str(workdir), changed, base_ref=base_ref)
    # Impact of changes: reviewer gets the diff but still has to trace
    # callers and test coverage on their own -- measured on e9 at 22-68
    # tool calls, each retry starting from scratch.  Providing it upfront
    # gives them a head start.
    context["impact"] = analyse_impact(
        workdir, changed, command=str(config.get("review.impact_provider", "") or "")
    ).as_prompt()
    # Existing tests with reduced cases (G8): show to reviewer, do not auto-
    # block -- "update expectations" is valid, "delete to go green" is not;
    # that is a judgment call.
    delta = tdd.test_delta(workdir, base_ref=base_ref, changed=changed)
    store = EvidenceStore(artifact_root, candidate=candidate)
    context["prior_review"] = _prior_review(store, story.id, role="review", changed=changed)
    context["proven"] = proven_text(
        store.read(story.id), story, candidate=candidate,
        max_chars=int(config["context.max_preservation_chars"]) if config else 1500)
    store.record(
        story.id, Event(kind=NOTE, name="qa:test-delta", ok=not delta, detail={"files": delta})
    )
    if delta:
        context["impact"] += (
            "\n\n**Existing tests lost cases** — ask why, do not assume it is valid: "
            + "; ".join(delta)
        )

    from ..harness.runlog import run_log
    run_log(artifact_root, f"story={story.id}#{number} review START changed={len(changed)}")
    from ..memory import attach
    attach(context, story, project, config, REVIEWER)
    store.handoff(story.id, frm=DEVELOPER, to=REVIEWER, attempt=number,
                  slots=handoff_slots(context), memory=context.get("_memory"))
    spec = build_spec(
        REVIEWER,
        catalog.get(ROLES[REVIEWER].prompt),
        context,
        workdir=workdir,
        config=config,
        allow_empty=ALLOW_EMPTY,
    )
    # Write scope -- but **not** story ID.  Without scope, the `diff-scope`
    # guard falls into the "no scope declared but files changed" branch and
    # blocks all reviewer Bash commands; with story ID, the `completion`
    # guard blocks it from stopping while tests are red -- exactly when it
    # has the most to report.
    spec.env = {
        ENV_WRITE_SCOPE: ",".join(effective_write_scope(story, project)),
        ENV_BASE_REF: base_ref,
        ENV_WORKDIR: str(workdir),
        ENV_PROJECT: str(project),
        ENV_DISALLOWED_TOOLS: ",".join(ROLES[REVIEWER].disallowed_tools),
        ENV_ALLOW_HOSTS: ",".join(config["sandbox.allow_hosts"]) if config else "",
    }

    _attach_settings(spec, project)
    run_log(artifact_root, f"story={story.id}#{number} review agent START prompt={len(spec.prompt)}ch")
    result, reverted = _review_session(
        client, spec, store=store, story_id=story.id, artifact_root=artifact_root,
        workdir=workdir, name=f"{story.id}-review", role="review", number=number,
    )
    run_log(artifact_root, (
        f"story={story.id}#{number} review agent DONE ok={result.ok} "
        f"${result.cost_usd:.2f} turns={getattr(result, 'num_turns', '?')}"
    ))
    if reverted:
        store.tool_run(
            story.id, "review:immutable", ok=False, detail={"changed": reverted[:20]},
        )
        return [], None, (
            "reviewer modified the working tree "
            f"({', '.join(reverted[:3])}) — reverted; this review attempt does not "
            "count. Review is a report, not a fix.")

    lech = _candidate_moved(workdir, candidate)
    if lech:
        # Revert only restores the **tree**; it does not undo a `git commit`.
        # Candidate changed means the reviewer just read a version different
        # from the one being scored -- that review says nothing about the
        # candidate.
        store.tool_run(story.id, "review:candidate", ok=False,
                       detail={"expected": candidate, "got": lech, "attempt": number})
        # Put the worktree back on the frozen candidate: the review retry
        # (D-032) must read the version being scored, not the reviewer's
        # commit -- which is not a candidate and never becomes one. Only what
        # the reviewer committed is undone; anything else in the tree (dirt an
        # open write-scope:violation still describes) is not the review's to
        # destroy, and the result is recorded, ok or not (SS-A10, INV-K.3).
        _restore_candidate_after_review_commit(store, story.id, workdir, candidate=candidate, got=lech, number=number)
        return [], None, (
            f"candidate changed during review session ({candidate[:7]} → {lech[:7]}) — "
            "this review attempt does not count. Review reads the frozen candidate, "
            "it does not create a new one.")

    if not result.ok:
        # The reviewer did not execute: no verdict, not a clean pass, not a
        # block — REVIEW_UNRUNNABLE, retried on the same candidate (D-032).
        return [], None, str(result.error or "reviewer session did not complete")

    text, verdict, why = _with_schema(
        client, spec, result, store=store, story_id=story.id,
        artifact_root=artifact_root, workdir=workdir, role="review", number=number,
    )
    if verdict is None:
        # Two answers without a structured verdict: the reviewer said nothing the kernel can score. Prose
        # findings are recorded as observations only — never a PASS, never a BLOCK (SS-57, INV-F.2).
        store.record(story.id, Event(kind=NOTE, name="review:no-schema", ok=False,
                                     detail={"findings": blocking_findings(text), "retried": True}))
        return [], None, why or ("no structured verdict after the schema retry — the reviewer answered in prose twice; "
                          "nothing was said about the candidate")
    return _reconcile(story.id, store, text, verdict, role="review"), verdict, ""


def _reconcile(story_id: str, ev: EvidenceStore, text: str,
               verdict: Verdict | None, *, role: str) -> list[str]:
    """The reviewer's blockers are the STRUCTURED verdict's (F3 / INV-F.2). Prose `[block]` lines are diagnostic:
    compared with the JSON, recorded as `<role>:mismatch` when they diverge, shown to the developer — never scored
    (SS-24). Without a verdict nothing blocks from prose (F2 makes that execution UNRUNNABLE)."""
    tu_van_ban = blocking_findings(text)
    if verdict is None:
        ev.record(story_id, Event(kind=NOTE, name=f"{role}:no-schema", ok=False,
                                  detail={"findings": tu_van_ban, "retried": True}))
        return []
    _no_escalation(story_id, ev, verdict, role=role)
    tu_json = verdict.bound_blocking() if role == "review" else verdict.blocking()
    if role == "review" and verdict.unbound():
        ev.record(story_id, Event(kind=NOTE, name=f"{role}:unbound", ok=False,
                                  detail={"verdict": verdict.verdict, "findings": verdict.unbound(), "retried": False}))
    _, lech = merge_findings(tu_van_ban, tu_json)
    if lech:
        ev.record(story_id, Event(
            kind=NOTE, name=f"{role}:mismatch", ok=False,
            detail={"text": tu_van_ban, "json": tu_json},
        ))
    ev.record(story_id, Event(
        kind=NOTE, name=f"{role}:verdict", ok=not tu_json,
        detail={"verdict": verdict.verdict, "findings": verdict.findings},
    ))
    return tu_json


def _prior_review(ev: EvidenceStore, story_id: str, *, role: str,
                  changed: list[str] | None = None) -> str:
    """The reviewer's own findings on the previous candidate of this story.

    Without it every attempt reviews from scratch and re-ranks its own
    advisory items into blockers; see `_no_escalation`, which enforces
    deterministically what this section asks for.

    Findings about files **no longer in the diff** are dropped. Handing them
    back invites the reviewer to file them again — the security reviewer kept
    re-raising a finding against `.opencode/plugin/aisef-guard.ts`, a file the
    harness writes and the story never touched, and raised it from `high` to
    `critical` the second time (todo/STORY-01-02 2026-09-09). What is not in
    this candidate's diff is not this candidate's to answer for.
    """
    truoc = [e for e in ev.read(story_id).of(NOTE, f"{role}:verdict")
             if str(e.detail.get("candidate") or "") != ev.candidate]
    if not truoc:
        return "_(first review of this story — nothing said before)_"
    e = truoc[-1]
    trong_diff = set(changed or [])

    def con_lien_quan(f: dict) -> bool:
        tep = str(f.get("file") or "").strip()
        return not tep or not trong_diff or tep in trong_diff

    dong = [
        f"- [{f.get('tag') or 'should fix'}] {_finding_body(f)}"
        for f in (e.detail.get("findings") or []) if con_lien_quan(f)
    ]
    sha = str(e.detail.get("candidate") or "")[:7]
    return "\n".join([f"On candidate `{sha}` you reported:", "", *dong]) if dong else (
        f"On candidate `{sha}` you reported no findings."
    )


def _no_escalation(story_id: str, ev: EvidenceStore, verdict: Verdict, *,
                   role: str) -> set[str]:
    """Demote blocking findings this reviewer itself filed as **advisory** on an
    earlier candidate of the same story; return the files left with no blocker.

    Promoting yesterday's `should fix` into today's `block` moves the goal
    posts: the author fixes what blocked, the reviewer blocks the next tier
    down, and the story burns every attempt without converging — todo
    STORY-01-01 died exactly that way, every blocking item of attempts 2 and 3
    having been advisory in attempt 1.  Either an item blocks the first time it
    is seen, or it stays advisory.  It is still reported, just not as a blocker,
    and the demotion is recorded rather than applied silently.

    Match is `(file, behavior_id)`.  Findings carrying no `behavior_id` collide
    per file — deliberately loose: erring toward convergence costs an advisory
    line in the report, erring the other way costs the whole story.
    """
    truoc: set[tuple[str, str]] = set()
    evidence = ev.read(story_id)
    # SS-05 / INV-B.2: a contract change starts from zero — a verdict of another epoch says nothing about this one.
    # An event's epoch is its identity's `story_epoch` (schema 2) or, for legacy records, the `story:contract`
    # fingerprint in force when it was written; the current epoch is the latest fingerprint recorded.
    epoch_at: dict[int, str] = {}
    cur = ""
    for e in evidence.events:
        if e.kind == NOTE and e.name == "story:contract":
            cur = str(e.detail.get("fingerprint") or "")
        epoch_at[e.seq] = str((getattr(e, "identity", None) or {}).get("story_epoch") or cur)
    epoch_now = cur
    for e in evidence.of(NOTE, f"{role}:verdict"):
        if str(e.detail.get("candidate") or "") == ev.candidate:
            continue  # this build's own verdict, not a previous position
        if epoch_at.get(e.seq, "") != epoch_now:
            continue  # another epoch: not a position on this contract
        for f in e.detail.get("findings") or []:
            if str(f.get("tag") or "").lower() not in _JSON_BLOCK_TAGS + _JSON_STUCK_TAGS:
                truoc.add((str(f.get("file") or ""), str(f.get("behavior_id") or "")))
    truoc.discard(("", ""))
    if not truoc:
        return set()

    ha_cap: list[dict] = []
    for f in verdict.findings:
        if (str(f.get("tag") or "").lower() in _JSON_BLOCK_TAGS
                and (str(f.get("file") or ""), str(f.get("behavior_id") or "")) in truoc):
            f["tag"] = "should fix"
            ha_cap.append(f)
    if not ha_cap:
        return set()

    con_chan = {str(f.get("file") or "") for f in verdict.findings
                if str(f.get("tag") or "").lower() in _JSON_BLOCK_TAGS + _JSON_STUCK_TAGS}
    if verdict.verdict != "pass" and not con_chan:
        # Every blocker was a re-escalation.  Leaving the verdict at `block`
        # makes `Verdict.blocking()` synthesise "concluded block but listed no
        # findings" and the story stays stuck on nothing.
        verdict.verdict = "pass"
    ev.record(story_id, Event(
        kind=NOTE, name=f"{role}:no-escalation", ok=True,
        detail={"demoted": ha_cap, "verdict": verdict.verdict},
    ))
    return {str(f.get("file") or "") for f in ha_cap} - con_chan


def security_review(
    story: Story,
    *,
    workdir: Path,
    base_ref: str,
    project: Path,
    artifact_root: Path,
    client: ClientAdapter,
    config: Config,
    catalog: Catalog,
    architecture: Architecture | None,
    number: int = 0,
    candidate: str = "",
    preservation: list[dict] | None = None,
) -> SecurityReport:
    """Semantic security review -- **separate session**, read-only.

    Not combined with the general review: a session holding two different
    question sets in mind treats both superficially, and security is the set
    usually dropped first.

    This session reads code just written by another agent -- **untrusted
    data**.  It has no write permission (`security` role forbids Write/Edit),
    and receives no environment variables from the story: running story code
    has no business reaching it.  Isolating from machine secrets requires a
    real sandbox, not achievable at the language level -- that is a
    limitation, and it is documented rather than hidden.
    """
    changed = changed_files(str(workdir), base_ref=base_ref)
    if not changed:
        return SecurityReport(error="no changes to review")

    context = build_context(
        story,
        project=project,
        artifact_root=artifact_root,
        architecture=architecture,
        contract=None,
        config=config,
        preservation=preservation,
    )
    context["diff_summary"] = review_diff(str(workdir), changed, base_ref=base_ref)
    context["impact"] = analyse_impact(
        workdir, changed, command=str(config.get("review.impact_provider", "") or "")
    ).as_prompt()

    from ..harness.runlog import run_log
    run_log(artifact_root, f"story={story.id}#{number} security START changed={len(changed)}")
    store = EvidenceStore(artifact_root, candidate=candidate)
    context["prior_review"] = _prior_review(store, story.id, role="security", changed=changed)
    context["proven"] = proven_text(
        store.read(story.id), story, candidate=candidate,
        max_chars=int(config["context.max_preservation_chars"]) if config else 1500)
    from ..memory import attach
    attach(context, story, project, config, SECURITY)
    store.handoff(story.id, frm=REVIEWER, to=SECURITY, attempt=number,
                  slots=handoff_slots(context), memory=context.get("_memory"))
    spec = build_spec(
        SECURITY,
        catalog.get(ROLES[SECURITY].prompt),
        context,
        workdir=workdir,
        config=config,
        allow_empty=ALLOW_EMPTY,
    )
    # Same combination proven on e9 for the reviewer: scope so `diff-scope`
    # does not block all Bash commands, working tree so guard checks the right
    # tree, forbidden tools so all clients enforce -- and **not** story ID.
    spec.env = {
        ENV_WRITE_SCOPE: ",".join(effective_write_scope(story, project)),
        ENV_BASE_REF: base_ref,
        ENV_WORKDIR: str(workdir),
        ENV_PROJECT: str(project),
        ENV_DISALLOWED_TOOLS: ",".join(ROLES[SECURITY].disallowed_tools),
        ENV_ALLOW_HOSTS: ",".join(config["sandbox.allow_hosts"]) if config else "",
    }
    _attach_settings(spec, project)
    run_log(artifact_root, f"story={story.id}#{number} security agent START prompt={len(spec.prompt)}ch")
    result, reverted = _review_session(
        client, spec, store=store, story_id=story.id, artifact_root=artifact_root,
        workdir=workdir, name=f"{story.id}-security", role="security", number=number,
    )
    run_log(artifact_root, (
        f"story={story.id}#{number} security agent DONE ok={result.ok} "
        f"${result.cost_usd:.2f} turns={getattr(result, 'num_turns', '?')}"
    ))
    if reverted:
        store.tool_run(
            story.id, "security:immutable", ok=False, detail={"changed": reverted[:20]},
        )
        return SecurityReport(unrunnable=f"security reviewer modified the working tree ({', '.join(reverted[:3])}) — reverted, this execution does not count")
    lech = _candidate_moved(workdir, candidate)
    if lech:
        store.tool_run(story.id, "security:candidate", ok=False,
                       detail={"expected": candidate, "got": lech, "attempt": number})
        return SecurityReport(
            unrunnable=f"candidate changed during security review session ({candidate[:7]} → "
                       f"{lech[:7]}) — this execution does not count"
        )
    if not result.ok:
        return SecurityReport(unrunnable=f"could not run: {result.error}")

    text, verdict, why = _with_schema(
        client, spec, result, store=store, story_id=story.id,
        artifact_root=artifact_root, workdir=workdir, role="security", number=number,
    )
    return _reconcile_security(story.id, store, text, verdict, why=why)


def _reconcile_security(story_id: str, ev: EvidenceStore, text: str,
                        verdict: Verdict | None, *, why: str = "") -> SecurityReport:
    """Same rule as `_reconcile`, but the unit is severity level.

    JSON items not in the text are re-parsed via `parse_security` so exactly
    one noise filter scores both sources.
    """
    rep = parse_security(text)
    if verdict is None:
        # Two answers without a structured verdict: nothing was SAID about the candidate. Prose findings are
        # recorded as observations; they never PASS and never BLOCK (SS-13 / SS-57, INV-F.2).
        ev.record(story_id, Event(kind=NOTE, name="security:no-schema", ok=False,
                                  detail={"findings": [f.line() for f in rep.findings],
                                          "retried": True}))
        return SecurityReport(unrunnable=why or "no structured verdict after the schema retry — the security reviewer "
                                         "answered in prose twice; nothing was said about the candidate")

    tu_van_ban = [f.line() for f in rep.findings + rep.filtered]
    tu_json = [f"[{f['severity']}] " + _finding_body(f)
               for f in verdict.findings if f.get("severity")]
    hop, lech = merge_findings(tu_van_ban, tu_json)
    them = hop[len(tu_van_ban):]
    if them:
        bo_sung = parse_security("\n".join(them))
        rep.findings.extend(bo_sung.findings)
        rep.filtered.extend(bo_sung.filtered)
        rep.findings.sort(key=lambda f: -f.rank)
    # A valid JSON block **is** a correctly formatted report: the "malformed"
    # error from the text version no longer applies.
    rep.error = ""
    if lech:
        ev.record(story_id, Event(kind=NOTE, name="security:mismatch", ok=False,
                                  detail={"text": tu_van_ban, "json": tu_json}))
    ev.record(story_id, Event(
        kind=NOTE, name="security:verdict", ok=not rep.blocking(),
        detail={"verdict": verdict.verdict, "findings": verdict.findings},
    ))
    return rep


#: Opening tag for regular blocking items.
_BLOCK_TAGS = ("[chặn]", "[blocker]", "[block]", "[blocked]", "[blocking]")
#: Opening tag for **stuck** items: the reviewer has verified that criteria
#: cannot be satisfied from within the story scope.  Two independent models
#: reached the same conclusion -- retrying burns money with no way out.
_STUCK_TAGS = ("[bế tắc]", "[be tac]", "[stuck]", "[blocked-by-plan]", "[stuck-by-plan]")


#: Directory holding the reviewer's full text -- blocking evidence must be re-readable.
REVIEWS_DIR = "reviews"


def persist_verdict(artifact_root: Path | str, story_id: str, role: str, number: int, result) -> Path:
    """Record the reviewer's / security reviewer's full text.

    Bug 16 (e9 STORY-01-05, 2026-09-05): stuck reason in sprint-status ended
    at "-- no." because only the first line of the item was kept, while the
    full text lived nowhere -- blocking evidence that readers cannot verify
    is not evidence.
    """
    d = Path(artifact_root) / REVIEWS_DIR
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{story_id}-{role}-{number}.md"
    head = (
        f"# {role} — {story_id}, attempt {number}\n\n"
        f"session: {getattr(result, 'session_id', '')} · turns: "
        f"{getattr(result, 'num_turns', 0)} · ${getattr(result, 'cost_usd', 0.0):.2f}"
        f"{' · ERROR: ' + result.error if getattr(result, 'error', '') else ''}\n\n---\n\n"
    )
    path.write_text(head + (getattr(result, "text", "") or ""), encoding="utf-8")
    return path


#: A tag the model wrote **mid-line**, glued to whatever came before it.
#: todo-e2e/STORY-01-02 2026-09-10 opened with "...whether each test can
#: detect regressions.[block] tests/todo.spec.js:217 -- ..." on one line, and
#: a parser that only looked at line starts lost that blocker.  Split there.
#:
#: Not after a backtick: there the model is **naming** the tag, not raising
#: it. Both shapes measured on todo-cli 2026-09-13 (lỗi 122) — the reviewer
#: thinking out loud ("whether this is a `[block]` or `[should fix]`:") and
#: the reviewer recalling an earlier review ("The `[block]` item from the
#: previous review ... persists", whose own JSON verdict listed no blocker).
#: Both were counted as blocking items and both failed a story on a sentence
#: that raised nothing.
_TAG_MO_DAU = re.compile(
    "(?<=[^\n`])(" + "|".join(re.escape(t) for t in _BLOCK_TAGS + _STUCK_TAGS) + ")",
    re.IGNORECASE)


#: A path-like token: has a directory separator or a file extension. The
#: review prompt's format is `[block] path/file.ts:12 — description`, and that
#: path is what separates an **item** from the reviewer talking *about* tags
#: mid-sentence ("This is a [block].", "I'll keep the [block] tag for this
#: review."). Measured on todo-oc STORY-04-02 2026-09-13: 29 text items, of
#: which 2 had a path — and the JSON verdict declared exactly those 2.
_CO_DUONG_DAN = re.compile(r"^[\w.@+-]*[/\\][\w./\\@+-]*|^[\w@+-]+\.[A-Za-z][\w]{0,9}\b")


def _la_muc_that(line: str) -> bool:
    """Does this line follow the format the reviewer was given?

    `[stuck]` is exempt: it is a verdict about the plan ("these criteria
    cannot be met from inside this story"), which has no file to point at.
    """
    m = re.match(r"\s*\[([^\]]*)\]\**\s*(\S*)", line or "")
    if not m:
        return False
    if m.group(1).strip().lower() in _JSON_STUCK_TAGS:
        return True
    return bool(_CO_DUONG_DAN.match(m.group(2).strip()))


def blocking_findings(text: str) -> list[str]:
    """Extract `[blocker]` and `[stuck]` items from a review report.

    An item may span multiple lines: a following line not starting with a
    bullet or a new tag belongs to the previous item (bug 16 -- previously
    only the first line was kept, stuck reasons truncated at "-- no.").

    A tag is an item wherever it starts, not only at the start of a line
    (`_TAG_MO_DAU`).
    """
    out: list[str] = []
    dang_mo = False
    for line in _TAG_MO_DAU.sub(r"\n\1", text or "").splitlines():
        raw = line.rstrip()
        stripped = raw.strip().lstrip("-*• ").strip()
        low = stripped.lower()
        if low.startswith(_BLOCK_TAGS) or low.startswith(_STUCK_TAGS):
            out.append(stripped)
            dang_mo = True
            continue
        if not stripped:
            dang_mo = False
            continue
        la_muc_moi = raw.lstrip().startswith(("-", "*", "•", "#")) or low.startswith("[")
        if dang_mo and not la_muc_moi:
            out[-1] = out[-1] + " " + stripped
        else:
            dang_mo = False
    return [x for x in out if _la_muc_that(x)]


def structured_plan_defects(verdict: "Verdict | None") -> list[str]:
    """Stuck items the reviewer declared in the **JSON verdict** — the only
    evidence a terminal plan deadlock may rest on.

    Text is still read for blocking (`blocking_findings`, unioned in
    `_reconcile`), but a `[stuck]` that appears only in prose blocks the
    attempt and nothing more: prose is where a reviewer thinks aloud, and
    "So [stuck] doesn't apply." is a rejection of the tag, not a verdict
    (LedgerLock STORY-01-03 2026-09-15, lỗi 180 / D-026). No JSON after the
    schema reminder means the structured output is malformed: fail closed
    (the text items still block), never terminal. A JSON verdict of `stuck`
    with no items keeps `Verdict.blocking()`'s synthesised line — the
    reviewer did conclude it, in the field the gate reads.
    """
    if verdict is None:
        return []
    return [x for x in verdict.bound_blocking() if x.lower().startswith("[stuck]")]   # a [stuck] on nothing named is not terminal (F3)


# --- Machine-readable review verdicts (ADR-004 R8) ----------------------------
#
# Text is the human-readable version; JSON block is the machine-readable one.
# The two must agree -- and when they diverge, **union** the sources rather
# than relaxing: a blocking item lost because the model forgot to copy it to
# JSON means the gate loses it too, the worst kind of silent failure.

#: Valid verdicts.  Anything outside these three is a schema error.
VERDICTS = ("pass", "block", "blocked", "stuck")
#: JSON tags corresponding to the two blocking item types in text.
_JSON_BLOCK_TAGS = ("chặn", "chan", "block", "blocker", "blocked", "blocking")
_JSON_STUCK_TAGS = ("bế tắc", "be tac", "stuck", "blocked-by-plan", "stuck-by-plan")

#: Remind the schema when the first attempt lacks a JSON block.  Exactly
#: **once**: if the second attempt still lacks it, the model cannot do it,
#: retrying further wastes money.
BINDING_REMINDER = (
    "\n\n---\n\n**Your blockers name nothing.** Every `block` or `stuck` finding must bind to what it blocks: the "
    "`file` (with `line` where possible), the `behavior_id` from the contract, or the criterion code (`AC-…`) in `why`. "
    "A blocker that names no file, behaviour or criterion cannot be acted on and does not count. Reply **again** in "
    "full, and end with exactly one ```json``` block per the schema, each blocker bound.\n"
)

SCHEMA_REMINDER = (
    "\n\n---\n\n**Missing JSON block per schema.** Your previous reply was plain "
    "text without a machine-readable JSON block, so the gate could not read your "
    "conclusion. Reply **again** in full as requested above, and end with exactly "
    "one ```json``` block following the stated schema. The JSON and the text must "
    "match.\n"
)

_decoder = json.JSONDecoder()


@dataclass
class Verdict:
    """Machine-readable version of a review report."""

    verdict: str
    findings: list[dict] = field(default_factory=list)

    def _blocking_items(self) -> list[tuple[dict, str]]:
        out: list[tuple[dict, str]] = []
        for f in self.findings:
            if f["tag"] in _JSON_STUCK_TAGS:
                out.append((f, "[stuck] " + _finding_body(f)))
            elif f["tag"] in _JSON_BLOCK_TAGS:
                out.append((f, "[block] " + _finding_body(f)))
        return out

    def bound_blocking(self) -> list[str]:
        """Blocking/stuck items that BIND to an identity — a file, a `behavior_id`, or a criterion code in the reason
        (F3 / INV-F.2; D-002's structural property: a judge-only block names what it blocks). A `block`/`stuck`
        verdict whose items bind to nothing has no blocker here — `_with_schema` asks once more, then the review is
        UNRUNNABLE; it never PASSes and never opens a developer session."""
        return [line for f, line in self._blocking_items() if finding_bound(f)]

    def unbound(self) -> list[dict]:
        """Blocking/stuck items that bind to nothing — recorded as `review:unbound`, never scored."""
        return [f for f, _ in self._blocking_items() if not finding_bound(f)]

    def blocking(self) -> list[str]:
        """Blocking/stuck items, formatted as text-version lines (every item, bound or not)."""
        out = [line for _, line in self._blocking_items()]
        if self.verdict != "pass" and not out:
            # Verdict says blocked but lists no items: keep the verdict, do
            # not let it pass.  Do not trust the client -- even when it
            # contradicts itself.
            tag = "[stuck]" if self.verdict == "stuck" else "[block]"
            out.append(f"{tag} reviewer concluded `{self.verdict}` "
                       "but listed no findings in the JSON block")
        return out


_TRACE_MARK = re.compile(r"^\s*(?:trace|truy vết)\s*:\s*\S", re.IGNORECASE)


def finding_bound(f: dict) -> bool:
    """A finding binds when it names a file, a behaviour id, a criterion code (`AC-<story>-<n>`) in its reason, or —
    the improve loop's own protocol — a test identity after the `trace:` marker it asks the reviewer to use."""
    why = str(f.get("why") or "")
    return bool(str(f.get("file") or "").strip() or str(f.get("behavior_id") or "").strip()
                or _MA_TIEU_CHI.search(why) or _TRACE_MARK.match(why))


def _finding_body(f: dict) -> str:
    """`{file}:{line} -- {why}` -- same format as lines the reviewer writes."""
    where = f.get("file") or ""
    if where and f.get("line"):
        where += f":{f['line']}"
    why = f.get("why") or ""
    return f"{where} — {why}".strip(" —") if where else why


def review_verdict(text: str) -> Verdict | None:
    """First JSON block with a valid `verdict`; invalid items dropped, no
    crash.

    Same approach as `kit/skill_scan.parse_verdicts`, but uses `raw_decode`:
    it stops exactly where JSON ends so trailing text (and ```json fences)
    do not break parsing.
    """
    for m in re.finditer(r"\{", text or ""):
        try:
            data, _ = _decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if not isinstance(data, dict) or "verdict" not in data:
            continue
        verdict_str = str(data.get("verdict", "")).strip().lower()
        if verdict_str not in VERDICTS:
            return None
        out = []
        for item in data.get("findings") or []:
            if not isinstance(item, dict):
                continue
            tag = str(item.get("tag", "")).strip().lower()
            sev = str(item.get("severity", "")).strip().lower()
            if not tag and sev not in SEVERITIES:
                continue
            f = {
                "tag": tag,
                "file": str(item.get("file", ""))[:200],
                "line": str(item.get("line", "") or "")[:10],
                "why": str(item.get("why", ""))[:500],
                "behavior_id": str(item.get("behavior_id", ""))[:80],
            }
            if sev in SEVERITIES:
                f["severity"] = sev
            out.append(f)
        return Verdict(verdict_str, out)
    return None


def _finding_key(line: str) -> tuple[str, str, str]:
    """Reconciliation key between two versions: (tag type, file, line).

    Not compared verbatim: JSON and text versions never match word-for-word,
    but pointing at the same place means they are one item.

    The **place** is file *and* line.  Keying on the file alone -- which this
    did until todo-e2e/STORY-01-02 2026-09-10 -- makes every finding in one
    file the same item: the reviewer filed three blockers in
    `tests/todo.spec.js`, the text version carried two of them, and the union
    concluded the two covered the three.  The third was dropped, and
    `review:mismatch` stayed silent because the two key *sets* matched.
    Losing a blocker costs the story; repeating one costs a line in the fix
    list.  Callers wanting the file alone take element 1.
    """
    m = re.match(r"\s*\[([^\]]*)\]\s*(\S*)", line or "")
    if not m:
        return ("", "", "")
    tag = m.group(1).strip().lower()
    kind = tag
    if tag in _JSON_STUCK_TAGS:
        kind = "stuck"
    elif tag in _JSON_BLOCK_TAGS:
        kind = "block"
    filepath = m.group(2).strip().rstrip(":,;")
    dong = re.search(r":(\d+(?:-\d+)?)$", filepath)
    filepath = re.sub(r":\d+(-\d+)?$", "", filepath)
    return (kind, filepath, dong.group(1) if dong else "")


def _gop_trung(items: list[str]) -> list[str]:
    """Same finding restated is one finding.

    A reviewer deliberating at length writes its blockers several times —
    once while reasoning, once per summary section, once in the final list.
    Measured on todo-oc STORY-04-02 2026-09-13: the JSON verdict carried
    **2** blocking findings and the text yielded **29**, so the gate line
    read "29 blocking items" and the next developer received the same two
    problems fourteen times over (lỗi 141). `_finding_key` already defines
    when two lines are the same item: same tag, same file, same line.

    An item with no file cannot be keyed that way, so those are deduped by
    their own text — two distinct unlocated blockers stay two.
    """
    ra: list[str] = []
    thay: set = set()
    for x in items:
        khoa = _finding_key(x)
        # `_finding_key` takes the next token whatever it is, so "criteria"
        # from `[stuck] criteria A cannot be met` looks like a file. Key by
        # place only when the token really is one; otherwise by the text.
        co_noi = bool(_CO_DUONG_DAN.match(khoa[1]))
        rieng = khoa if co_noi else ("van-ban", " ".join((x or "").split()).lower()[:200], "")
        if rieng in thay:
            continue
        thay.add(rieng)
        ra.append(x)
    return ra


def merge_findings(text_items: list[str], json_items: list[str]) -> tuple[list[str], bool]:
    """Union two sources and report whether they diverged.  Text first, JSON
    fills in after."""
    text_items = _gop_trung(text_items)
    khoa_text = {_finding_key(x) for x in text_items}
    khoa_json = {_finding_key(x) for x in json_items}
    them = [x for x in json_items if _finding_key(x) not in khoa_text]
    return text_items + them, khoa_text != khoa_json



#: Hook config that `aisef compile` generates for Claude Code.
CLAUDE_SETTINGS = Path(".claude") / "settings.json"


def _attach_settings(spec, project: Path) -> None:
    """Pass hook files **explicitly** to the client, instead of relying on it
    finding them on its own.

    Claude Code reads `.claude/settings.json` from the tree it stands in.
    Stories run in worktrees, and the worktree only has that directory if the
    project **commits** it.  A project that `.gitignore`s `.claude/` runs
    every story with zero guards -- and evidence looks identical to a
    well-behaved agent, because nothing gets recorded.  e9 and par both
    commit `.claude/`, so this hole has not surfaced; that is luck, not
    design.

    Adapters that do not support the flag (OpenCode) ignore this field --
    their plugin loads via a different path, already proven.
    """
    path = Path(project) / CLAUDE_SETTINGS
    if path.is_file():
        spec.settings_file = path


def _tree_snapshot(workdir: Path) -> dict[str, bytes | None]:
    """Working tree snapshot: path -> content of every file git sees as
    changed or untracked (None if too large to hold).  Skips harness-written
    paths (`_bmad-output/`, `.aisef/`): evidence from this session is written
    during the session, counting it is a false positive."""
    from ..harness.ownership import NOT_A_WRITE, classify, porcelain_entries
    out: dict[str, bytes | None] = {}
    for _, rel in porcelain_entries(workdir):                                # renames yield the real path (SS-35)
        if classify(rel) in NOT_A_WRITE:                                     # harness, tool artifact, vendor, client (F4)
            continue
        p = Path(workdir) / rel
        try:
            out[rel] = p.read_bytes() if p.is_file() and p.stat().st_size <= 5_000_000 else None
        except OSError:
            out[rel] = None
    return out


def _revert_reviewer_writes(workdir: Path, before_snap: dict, after_snap: dict) -> list[str]:
    """A reviewer that can modify code becomes a second write session.

    Forbidding `Write`/`Edit` in guards is layer one; compliance testing on
    2026-09-05 showed this was bypassed **on both clients** via Bash
    (`echo > file`) -- and Bash cannot be forbidden, reviewers need it to
    run tests.  So layer two is revert: all tree differences after the
    review session are restored to their prior state, logged, and that
    review session **does not count** -- same "coarse-grained revert"
    mechanism as the worktree.
    """
    changed = sorted({k for k in after_snap if k not in before_snap or after_snap[k] != before_snap[k]}
                     | {k for k in before_snap if k not in after_snap})
    if not changed:
        return []
    for rel in changed:
        p = Path(workdir) / rel
        if rel in before_snap and before_snap[rel] is not None:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(before_snap[rel])           # changed or untracked file: restore content
        elif rel in before_snap:
            subprocess.run(["git", "checkout", "--", rel], cwd=workdir,
                           capture_output=True, timeout=30)   # too large to snapshot: delegate to git
        elif p.exists():
            try:
                p.unlink()                       # new file created by the reviewer
            except OSError:
                pass
    return changed


# ------------------------------------------------------------ retry hygiene (D-034)

#: Evidence names of retry hygiene (D-034, lỗi 188).
SCOPE_VIOLATION = "write-scope:violation"
RETRY_RECOVERY = "retry:recovery"


def _dirt_outside_scope(workdir: Path, scope: list[str]) -> dict[str, bytes | None]:
    """Paths dirty against HEAD that lie outside the write scope: the out-of-scope
    part of what `_tree_snapshot` sees (harness-owned paths already skipped),
    minus tool artifacts — a run produces those, no agent writes them."""
    from ..harness.guardrails import _within, is_tool_artifact
    return {rel: content for rel, content in _tree_snapshot(workdir).items()
            if not is_tool_artifact(rel) and not any(_within(rel, s) for s in scope)}


def _tracked_at_head(workdir: Path, rel: str) -> bool:
    r = subprocess.run(["git", "cat-file", "-e", f"HEAD:{rel}"], cwd=workdir,
                       capture_output=True, timeout=30)
    return r.returncode == 0


def record_scope_violation(evidence: EvidenceStore, story_id: str, *, workdir: Path, scope: list[str],
                           before: dict, attempt: int, artifact_root: Path) -> Event | None:
    """What **this** developer session left outside the write scope, on record the
    moment the session ends (D-034, lỗi 188).

    Measured on LedgerLock STORY-04-01 (1.7.5): `ruff format ledgerlock/` reformatted
    two files outside scope; `freeze_candidate` rightly kept them out of the
    candidate, and nothing named them afterwards — so both retries inherited them,
    and the `diff-scope` after-hook blocked every one of their tool calls from the
    first `ls`. A path already dirty when the session opened is not this session's
    doing and is listed apart (`preexisting`)."""
    dirt = _dirt_outside_scope(workdir, scope)
    tracked, untracked, preexisting = [], [], []
    for rel in sorted(dirt):
        if rel in before:
            preexisting.append(rel)
        elif _tracked_at_head(workdir, rel):
            tracked.append(rel)
        else:
            untracked.append(rel)
    if not tracked and not untracked:
        return None
    from ..harness.runlog import run_log
    run_log(artifact_root, f"story={story_id}#{attempt} wrote outside write_scope: "
                           f"{', '.join(tracked + untracked)} — on record; restored before the next attempt")
    return evidence.record(story_id, Event(kind=NOTE, name=SCOPE_VIOLATION, ok=False, detail={
        "attempt": attempt, "head": head_sha(workdir), "tracked": tracked, "untracked": untracked,
        "preexisting": preexisting, "scope": list(scope)}))


def _attributed_out_of_scope(ev: Evidence, scope: list[str]) -> tuple[set[str], int]:
    """Out-of-scope paths an attempt of this story is on record for, and that
    attempt's number. The `write-scope:violation` note is the record; a tree left
    by a harness that wrote none (≤ 1.7.5) is read through the last `gate:input`,
    whose `changed` list is exactly what the gate failed `write scope` on."""
    from ..harness.guardrails import _within
    recs = ev.of(NOTE, SCOPE_VIOLATION)
    if recs:
        last = recs[-1]
        paths = set(last.detail.get("tracked") or []) | set(last.detail.get("untracked") or [])
        return paths, int(last.detail.get("attempt") or 0)
    gi = ev.last(NOTE, "gate:input")
    if gi is None:
        return set(), 0
    paths = {p for p in (gi.detail.get("changed") or []) if not any(_within(p, s) for s in scope)}
    return paths, int(gi.detail.get("attempt") or 0)


def recover_out_of_scope(evidence: EvidenceStore, story_id: str, *, workdir: Path, scope: list[str],
                         next_attempt: int, artifact_root: Path) -> Event | None:
    """Before a developer attempt opens in a story worktree: put the out-of-scope
    paths an earlier attempt of this story left dirty back to the frozen candidate
    — tracked paths restored from HEAD, untracked ones removed, and only those —
    then check the tree is clean of out-of-scope changes (D-034, lỗi 188).

    Dirt no attempt of this story is on record for is **not** touched: it is
    someone's uncommitted work, and deleting it is not the harness's call. The
    attempt does not open on it either — a developer on that tree can only be
    blocked by the guard — and the event says what to clean. Returns None when
    there was nothing to do; otherwise the recorded event, `ok` meaning clean."""
    dirt = _dirt_outside_scope(workdir, scope)
    if not dirt:
        return None
    attributed, failed_attempt = _attributed_out_of_scope(evidence.read(story_id), scope)
    candidate = head_sha(workdir)
    tracked = [p for p in sorted(dirt) if p in attributed and _tracked_at_head(workdir, p)]
    untracked = [p for p in sorted(dirt) if p in attributed and not _tracked_at_head(workdir, p)]
    unattributed = [p for p in sorted(dirt) if p not in attributed]
    actions: list[str] = []
    if tracked:
        r = subprocess.run(["git", "restore", "--source", candidate, "--staged", "--worktree", "--", *tracked],
                           cwd=workdir, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=60)
        actions.append(f"git restore --source {candidate[:8]} --staged --worktree -- {' '.join(tracked)}"
                       + ("" if r.returncode == 0 else f" → exit {r.returncode}: {r.stderr.strip()[:200]}"))
    for rel in untracked:
        # A new file the agent also staged must leave the index, not only the disk.
        subprocess.run(["git", "rm", "-q", "--cached", "--ignore-unmatch", "--", rel], cwd=workdir,
                       capture_output=True, timeout=30)
        p = Path(workdir) / rel
        try:
            p.unlink()
            actions.append(f"rm {rel}")
        except FileNotFoundError:
            actions.append(f"rm {rel} (already gone)")
        except OSError as e:
            actions.append(f"rm {rel} → {e}")
    after = sorted(_dirt_outside_scope(workdir, scope))
    ok = not after
    if actions:
        _invalidate_after_tree_change(evidence, story_id, candidate=candidate, workdir=workdir,
                                      reason="retry:recovery", actions=actions)
    reason = ""
    if not ok:
        reason = (
            f"the story worktree still has changes outside write_scope before attempt {next_attempt}: "
            f"{', '.join(after[:5])}" + (f" (+{len(after) - 5} more)" if len(after) > 5 else "")
            + ((". No attempt of this story is on record for " + ", ".join(unattributed[:5])
                + " — the harness does not delete what it did not make: commit or remove them, then re-run.")
               if unattributed else
               ". Restoring them from the frozen candidate did not leave the tree clean — see the "
               "retry:recovery evidence.")
            + " A developer session on this tree would be blocked by the guard on every call."
        )
    from ..harness.runlog import run_log
    run_log(artifact_root, f"story={story_id} retry recovery before attempt {next_attempt}: "
            + (f"restored {', '.join(tracked + untracked)} to candidate {candidate[:8]}; tree clean"
               if ok else reason[:200]))
    return evidence.record(story_id, Event(kind=NOTE, name=RETRY_RECOVERY, ok=ok, detail={
        "attempt": failed_attempt, "next_attempt": next_attempt, "candidate": candidate,
        "tracked": tracked, "untracked": untracked, "unattributed": unattributed,
        "actions": actions, "status_after": after, "ok": ok, "reason": reason}))


def _invalidate_after_tree_change(evidence: EvidenceStore, story_id: str, *, candidate: str, workdir: Path,
                                  reason: str, actions: list[str]) -> Event | None:
    """The evaluated tree changed (a restore, a reset, a refresh): every verdict computed over the previous
    tree state of this candidate is now a historical fact. Say so, in one typed record naming them
    (INV-K.2) — the freshness function already refuses them; this makes the refusal visible."""
    digest = ident.tree_state_digest(workdir)
    ev = evidence.read(story_id)
    stale = []
    for e in ev.events:
        if e.kind not in (NOTE, TOOL_RUN) or e.name in ident.NON_CANDIDATE_NOTES:
            continue
        rec = ident.EvidenceIdentity.of(e, story_id)
        if rec.candidate_sha != candidate:
            continue
        if rec.tree_state_digest != digest:
            stale.append(e)
    if not stale and not actions:
        return None
    return evidence.record(story_id, Event(kind=NOTE, name=ident.INVALIDATED, ok=True, detail={
        "reason": reason, "candidate": candidate, "tree_state_after": digest, "actions": actions,
        "invalidated": [e.seq for e in stale][:200], "names": sorted({e.name for e in stale})[:40],
        "schema_1": [e.seq for e in stale if not e.identity][:200]}))


def _restore_candidate_after_review_commit(store: EvidenceStore, story_id: str, workdir: Path, *, candidate: str,
                                           got: str, number: int) -> bool:
    """HEAD back on `candidate` without a hard reset: a soft reset moves HEAD, then only the paths the
    reviewer's commit touched are put back (restored from the candidate, or removed when the candidate never
    had them). Everything else in the working tree survives. One typed record names what was done and
    whether HEAD is on the candidate afterwards."""
    def _git(*args):
        return subprocess.run(["git", *args], cwd=workdir, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=60)
    diff = _git("diff", "--name-only", candidate, got)
    paths = [x for x in diff.stdout.split("\n") if x.strip()]
    actions: list[str] = []
    r = _git("reset", "-q", "--soft", candidate)
    ok = r.returncode == 0
    actions.append(f"git reset --soft {candidate[:8]}" + ("" if ok else f" → exit {r.returncode}: {r.stderr.strip()[:200]}"))
    if ok:
        for rel in paths:
            exists = _git("cat-file", "-e", f"{candidate}:{rel}").returncode == 0
            if exists:
                r2 = _git("restore", "--source", candidate, "--staged", "--worktree", "--", rel)
                actions.append(f"git restore --source {candidate[:8]} -- {rel}" + ("" if r2.returncode == 0 else f" → exit {r2.returncode}"))
                ok = ok and r2.returncode == 0
            else:
                _git("rm", "-q", "--cached", "--ignore-unmatch", "--", rel)
                try:
                    (Path(workdir) / rel).unlink()
                    actions.append(f"rm {rel} (the reviewer created it)")
                except FileNotFoundError:
                    actions.append(f"rm {rel} (already gone)")
                except OSError as e:
                    actions.append(f"rm {rel} → {e}")
                    ok = False
    after = head_sha(workdir)
    ok = ok and after == candidate
    store.record(story_id, Event(kind=NOTE, name=ident.INVALIDATED, ok=ok, detail={
        "reason": "review:candidate-moved", "candidate": candidate, "got": got, "restored": paths[:50],
        "actions": actions, "head_after": after, "attempt": number}))
    return ok


def _candidate_moved(workdir: Path, candidate: str) -> str:
    """Current HEAD if it has moved away from the candidate; "" if still at
    the correct version.

    Cannot check (not yet frozen, or git unreadable) returns "": a review
    session wrongly canceled because the harness is blind is worse."""
    if not candidate:
        return ""
    bay_gio = head_sha(workdir)
    return bay_gio if bay_gio and bay_gio != candidate else ""


#: Criterion codes named inside a gate check's detail — the nop control lists
#: exactly which tests were green at the parent SHA.
_MA_TIEU_CHI = re.compile(r"\bAC-[A-Za-z0-9_-]*?-\d+(?![0-9A-Za-z_-])")


#: Sessions that declined to write, in a row, before the harness stops asking.
#: A cut session had work in flight and deserves a generous budget; a session
#: that ran clean and wrote nothing has **decided** — and re-opening it with
#: identical context returns the same decision. Sharing one budget with cut
#: sessions meant raising the cut budget to 6 made this case worse, not better
#: (lỗi 127): STORY-05-02 spent six sessions on a verdict it had after two.
MAX_NOOP = 2

#: Review outcomes (D-032). PASS and BLOCK are the reviewer's verdicts about the
#: candidate; REVIEW_UNRUNNABLE is the reviewer's *absence* — max_turns,
#: timeout, transport failure, a session that modified the tree, a candidate
#: that moved under it. LedgerLock Run #2 STORY-01-06 (2026-09-15, 1.7.3):
#: deterministic gates green, security clean, reviewer cut at 40 turns; the
#: loop's only move was a new developer session, the developer correctly wrote
#: nothing, and the no-op policy made the story terminal.
REVIEW_PASS = "PASS"
REVIEW_BLOCK = "BLOCK"
REVIEW_UNRUNNABLE = "REVIEW_UNRUNNABLE"
SECURITY_UNRUNNABLE = "SECURITY_UNRUNNABLE"
#: bounded re-runs of a deterministic stage (test/lint/qa) that could not run, per candidate
MAX_TOOL_RETRIES = 2
#: Reviewer executions on one candidate after the first, before the story ends
#: as REVIEW_UNRUNNABLE. A cut reviewer is retried on the **same** frozen
#: candidate; nothing about the code changed, so nothing else is re-asked.
MAX_REVIEW_RETRIES = 2
#: Legacy prefix (≤ 1.7.3) under which an execution failure was stored as a
#: finding; read so a resumed pre-1.7.4 run is recovered, never written again.
_LEGACY_UNRUN = "review could not run:"


def _review_complete(ev: Event | None) -> bool:
    """Does this `tool_run review` carry a reviewer's **verdict** (PASS or
    BLOCK)? An execution failure recorded there — new `unrunnable`/`outcome`
    fields, or the ≤ 1.7.3 finding text — is not evidence about the candidate
    and must not be reused as if it were (D-032)."""
    if ev is None:
        return False
    d = ev.detail
    if d.get("unrunnable") or d.get("outcome") == REVIEW_UNRUNNABLE:
        return False
    return not any(str(f).startswith(_LEGACY_UNRUN) for f in (d.get("findings") or []))


def _review_executions(ev: Evidence, story_id: str, sha: str) -> int:
    """Reviewer sessions already spent on this candidate."""
    return sum(1 for e in ev.of(AGENT_RUN, f"{story_id}-review")
               if str(e.detail.get("candidate") or "") == sha)


def _security_executions(ev: Evidence, story_id: str, sha: str) -> int:
    """Security reviewer EXECUTIONS already spent on this candidate — a schema retry belongs to the execution that
    asked for it, exactly as `Attempt.review_attempt` counts the reviewer's (one bound, in executions, per stage)."""
    return sum(1 for e in ev.of(AGENT_RUN) if e.name == f"{story_id}-security"
               and str(e.detail.get("candidate") or "") == sha)


def _only_review_unrunnable(attempt: Attempt) -> bool:
    """The gate failed on the reviewer's absence and nothing else."""
    return bool(attempt.review_unrunnable) and attempt.gate is not None and (
        [c.name for c in attempt.gate.failures] == ["review"])


def exit_status_of_error(error: str) -> str:
    """Classify a stored attempt error the way `exit_status_of` classifies a live result (fatal attempts keep
    only the text)."""
    return exit_status_of(RunResult(ok=False, error=error))


def _absent_stages(attempt: Attempt) -> list[str]:
    """Stages the gate is blocked on ONLY because they said nothing (UNRUNNABLE): review, security, a tool that
    could not run, stale evidence. Empty when any check FAILED — then something deterministic is wrong with the
    work and the developer is the right next stage (with every finding as feedback). Never a developer when
    only absences remain (SS-13, SS-14, SS-19, INV-G.1–G.3)."""
    if attempt.gate is None or attempt.ok:
        return []
    failures = list(attempt.gate.failures)
    if any(c.outcome is story_gate.Outcome.FAILED for c in failures):
        return []
    return [c.name for c in failures if c.outcome is story_gate.Outcome.UNRUNNABLE]


def _verifier_budget_cap(attempt: Attempt) -> str:
    """The budget cap reached inside a verifier session of this attempt ("" otherwise). A cap is a run-level
    condition: no further session may be opened, whatever else the gate says (SS-12, INV-G.5). Lock contention
    (`locked`) is an ordinary infra absence and is retried (SS-21)."""
    # both verifiers are read: a review absent for another reason must not hide the security session's cap
    # (differential seeds 1330–2574 after F2: `or` stopped at the review's text)
    for why in (attempt.review_unrunnable or "", getattr(attempt.security, "unrunnable", "") or ""):
        if "budget exceeded" in why and "locked" not in why:
            return why
    return ""


def _stage_of(check_name: str) -> str:
    if check_name == "review":
        return "review"
    if check_name == "security":
        return "security"
    return "tools"


def _pending_review(root: Path, story_id: str, workdir: Path) -> str:
    """Candidate at the worktree HEAD whose last verdict failed **only**
    because the reviewer did not run — the state a resumed run must pick up
    at the review stage, not with a developer session (Run #2's forced resume
    opened two developer sessions on exactly this state and blocked again)."""
    sha = head_sha(workdir)
    if not sha:
        return ""
    ev = EvidenceStore(root).read(story_id)
    now = ident.current(story_id=story_id, candidate_sha=sha, workdir=workdir)
    verdict = ev.last_fresh(NOTE, "gate:verdict", now)
    if verdict is None or list(verdict.detail.get("failures") or []) != ["review"]:
        return ""
    return sha if not _review_complete(_at(ev, TOOL_RUN, "review", now)) else ""


def _noop_lien_tiep(attempts: list[Attempt]) -> int:
    """No-op sessions at the tail of the list, unbroken."""
    n = 0
    for a in reversed(attempts):
        if not a.noop:
            break
        n += 1
    return n


def nop_deadlock(attempts: list[Attempt]) -> str:
    """The story's criteria are already satisfied without the story.

    `tests verify story` failing with *the same criteria* on two graded
    attempts is not a developer who has not tried hard enough: no test can be
    red at the branch point for behaviour that is already on the main branch.
    Measured on todo-cli STORY-03-02 2026-09-13, whose four criteria were
    implemented by STORY-03-01 one wave earlier. The developer worked it out
    and correctly wrote nothing — which the harness read as a no-op session,
    spent the whole infrastructure budget re-opening it, and reported as
    "sessions kept producing nothing to grade" (lỗi 126): a plan defect
    described as a client problem, six sessions after it was knowable.
    """
    cham = [a for a in attempts if a.gate is not None and not a.infra]
    if not cham:
        return ""

    def _ma(a: Attempt) -> set[str]:
        muc = next((c for c in a.gate.failures if c.name == "tests verify story"), None)
        if muc is None:
            return set()
        data = getattr(muc, "data", None) or {}
        if "still_green" in data:                                  # SS-32: the producer's list, not its sentence
            return set(_MA_TIEU_CHI.findall(" ".join(map(str, data["still_green"]))))
        return set(_MA_TIEU_CHI.findall(muc.detail))               # legacy check without data: the criterion CODES only

    ma = _ma(cham[-1])
    if not ma:
        return ""
    if len(cham) >= 2 and _ma(cham[-2]) == ma:
        pass                                # two graded attempts, same criteria
    elif _noop_lien_tiep(attempts) >= 2:
        # One graded attempt with that verdict, then the developer declining to
        # write anything, twice. That refusal *is* the second data point: it is
        # the only way a developer can say "this is already done" (lỗi 127,
        # todo-cli STORY-05-02 — five no-op sessions after one such verdict,
        # the whole infrastructure budget spent re-asking).
        pass
    else:
        return ""
    return (
        "deadlock due to plan: criteria " + ", ".join(sorted(ma))
        + " are already satisfied at the branch point — their tests pass with "
        "the story's code absent, and a second session confirmed it. Either another "
        "story already shipped this behaviour (check the epic index) or the "
        "criteria describe something the code already does. No test the "
        "developer writes can be red at the parent SHA for behaviour that is "
        "already there; fix the criteria or drop the story, then re-run."
    )


def deadlock_reason(attempts: list[Attempt], write_scope: list[str] | None = None) -> str:
    """Deadlock: two consecutive attempts blocked for the same reason.
    Empty if not deadlocked.

    Reviewer blocking at the same spot means the last attempt made no
    progress -- and the next, with the same context and feedback, will not
    either.  Usually a contradiction outside the agent's reach: acceptance
    criteria demand something that ``write_scope`` forbids.

    Compared by **similarity**, not exact string match.  The reviewer is a
    model: the same defect gets reworded differently each attempt.  Measured
    on e9, STORY-01-02 was blocked 4 attempts for exactly one issue --
    `fake-indexeddb` not declared in `package.json` -- but no two phrasings
    matched, so the string-comparison detector stayed silent the whole time
    and the story burned its retry budget: $10.39.
    """
    # Consecutive GRADED positions: an attempt whose reviewer said nothing (UNRUNNABLE, re-run by the review stage)
    # is not a position and must not break the pair — the re-run's verdict is that candidate's position (SS-63,
    # differential seed 2624: a reviewer mutation between two identical out-of-scope blocks hid the plan conflict).
    graded = [a for a in attempts if not a.infra and not getattr(a, "review_unrunnable", "")]
    if len(graded) < 2:
        return ""
    last_attempt, prev_attempt = graded[-1], graded[-2]
    if not last_attempt.review_findings or not prev_attempt.review_findings:
        return ""
    if not _same_complaint(last_attempt.review_findings, prev_attempt.review_findings):
        return ""

    # Repeated **and** pointing outside write scope is stuck.  Inside scope
    # is "not yet fixed", not "cannot fix" -- and measured on e9, STORY-01-02
    # passed on attempt 3 after two failures, while STORY-01-04 was blocked
    # two attempts running for the same AR-7 violation on
    # `src/app/list-notes.ts`, a file right inside its scope.  Stopping there
    # cuts short a story that could still be saved; let the retry limit do
    # its job.
    ngoai = _paths_outside(last_attempt.review_findings, write_scope or [])
    if not ngoai:
        return ""
    return (
        "stuck: two consecutive attempts blocked for the same reason — "
        + "; ".join(last_attempt.review_findings[:2])
        + f". Blocking findings point to {', '.join(ngoai)} — not in the "
        f"story's write_scope, so the agent cannot fix it no matter how many "
        f"attempts. Widen write_scope or fix the acceptance criteria, then "
        f"re-run."
    )


#: Two blocking items are "the same issue" when they share **proper nouns**
#: -- filenames, package names, identifiers -- not when the text is similar.
#: The reviewer is a model: the same defect gets reworded differently each
#: attempt, so text comparison never matches.  But `fake-indexeddb` and
#: `package.json` appear in every attempt.
#:
#: Requiring **two** shared proper nouns, not one: sharing only
#: `package.json` would match "missing X" and "wrong Y" -- but that is
#: progress, not deadlock.  The coverage ratio handles the case where a long
#: blocking item mentions in passing what the other item focuses on.
SAME_COMPLAINT_NOUNS = 2
SAME_COMPLAINT_OVERLAP = 0.4


def _same_complaint(a: list[str], b: list[str]) -> bool:
    """Does any blocking item from this attempt match one from the previous?

    Prefers the new structured ``Finding`` id — two findings raised against
    the same defect carry the same 16-hex digest by construction (see
    ``aisef/control/findings.py``). Falls back to the legacy token overlap
    rule for callers that haven't migrated to the canonical line shape.
    """
    if _same_complaint_by_finding(a, b):
        return True
    for x in (_tokens(i) for i in a):
        for y in (_tokens(j) for j in b):
            if not x or not y:
                continue
            if x == y:
                return True  # verbatim repeat, no need to analyze
            chung = x & y
            if len(_rieng(chung)) < SAME_COMPLAINT_NOUNS:
                continue
            if len(chung) / min(len(x), len(y)) >= SAME_COMPLAINT_OVERLAP:
                return True
    return False


def _rieng(tokens: set[str]) -> set[str]:
    """Proper nouns: contain identifier separators, long enough to not be
    punctuation stuck to a word."""
    return {t for t in tokens if len(t) >= 4 and any(c in t for c in "./-_@")}


def _same_complaint_by_finding(a: list[str], b: list[str]) -> bool:
    """Exact-match path: identical canonical lines share a structured
    ``Finding.id`` 16-hex digest (see ``aisef/control/findings.py``).
    Two review attempts raising the same defect produce the same id —
    cheaper and more reliable than token overlap.  Non-canonical
    lines are silently ignored: the legacy fallback still runs.
    """
    try:
        from ..control.findings import Finding
        ids_a = {f.id for f in Finding.parse_lines(
            a, source="reviewer", trust="reviewer")}
        ids_b = {f.id for f in Finding.parse_lines(
            b, source="reviewer", trust="reviewer")}
    except (ValueError, TypeError):
        return False
    return bool(ids_a and ids_b and ids_a & ids_b)


#: Words appearing in nearly every blocking item, too common to distinguish.
_NHIEU = frozenset(
    "chặn blocker block và or không có là của một các cả cho khi thì mà "
    "nhưng nó này đó ở trong ngoài với từ đến được bị phải nào đâu nữa "
    "the a an is are not no this that it".split()
)


def _tokens(finding: str) -> set[str]:
    """Reduce a blocking item to a comparable word set.  Strip line numbers
    and overly common words."""
    import re as _re

    # Strip line numbers, keep all other numbers: "AC 1" and "AC 7" are two
    # different issues, merging them makes the detector report deadlock when
    # there is progress.
    low = _re.sub(r":\d+", " ", finding.lower())
    words = _re.findall(r"[\w./@-]+", low)
    return {
        w for w in words
        if w not in _NHIEU and (len(w) >= 2 or w.isdigit())
    }


def _paths_outside(findings: list, scope: list[str]) -> list[str]:
    """Files the blocking items point at that the story is not allowed to write — the concrete answer to "why is
    retrying pointless". The location is the finding's IDENTITY: a structured finding's `file`, or the leading
    `path[:line]` token of the kernel's canonical line `[tag] path:line — why`. A technology name or a filename
    mentioned in the prose is not a path (SS-25 / INV-F.2, INV-Q.1)."""
    import re as _re
    from ..harness.guardrails import _within
    out: list[str] = []
    for f in findings:
        if isinstance(f, dict):
            loc = str(f.get("file") or "")
        else:
            m = _re.match(r"\s*\[[^\]]*\]\s*(\S+?)(?::\d+)?(?=\s|$)", str(f))
            loc = m.group(1) if m else ""
        if not loc or loc in out or ("/" not in loc and "." not in loc):
            continue
        if not any(_within(loc, s) for s in scope):
            out.append(loc)
    return out[:3]


def _unfinished_review(root: Path, story_id: str, workdir: Path) -> str:
    """Blocking findings left over from a run that was interrupted.

    `feedback` is a local of the retry loop, so it dies with the process.
    Evidence does not.  A resumed story therefore opens at attempt 1 with the
    reviewer's rejection sitting unread in `_bmad-output/evidence`, the author
    re-submits the candidate that was already rejected, and the reviewer files
    the same finding again -- one attempt of the budget spent on being
    interrupted.  Measured on todo-e2e/STORY-01-02 2026-09-10: the resumed
    attempt drew back `tests/todo.spec.js:217 -- the serialization-error test
    fails validation before JSON.stringify`, word for word.

    Only while the worktree still carries the candidate they were filed
    against: reconciliation keeps the branch, but a tree rebuilt from the base
    has nothing those findings describe.
    """
    ev = EvidenceStore(root).read(story_id)
    # the reviewer's verdict is recorded as `reviewer:verdict` (structured) — `NOTE review` was never written (SS-04)
    last = ev.last(NOTE, "reviewer:verdict") or ev.last(NOTE, "review:verdict")
    if last is None or str(last.detail.get("verdict") or "").lower() not in ("block", "stuck"):
        return ""
    findings = [_finding_line(f) for f in (last.detail.get("findings") or [])]
    findings = [f for f in findings if f]
    sha = str(last.detail.get("candidate") or "")
    if not findings or not sha:
        return ""
    same = subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"],
                          cwd=workdir, capture_output=True, timeout=30)
    if same.returncode != 0:
        return ""
    return ("The run was interrupted after the reviewer had already rejected "
            "this candidate. These items are still blocking:\n"
            + "\n".join(f"- {f}" for f in findings[:10]))


def _record_head_moved(root: Path, story_id: str, workdir: Path) -> None:
    """The story's tree stands on a commit that is not the candidate of record (a refresh merged main, a
    wave-end commit of leftover work, a manual move): every verdict over that candidate is a historical
    fact. One typed record says so and names them (SS-09 / SS-16, INV-E.1 / INV-K.2) — the freshness function
    already refuses them; this makes the refusal visible before any session opens on the new tree."""
    store = EvidenceStore(root)
    ev = store.read(story_id)
    frozen, head = ev.candidate, head_sha(workdir)
    if not frozen or not head or head == frozen:
        return
    last = ev.last(NOTE, ident.INVALIDATED)
    if last is not None and str(last.detail.get("head") or "") == head:
        return                                  # already recorded for this move
    names = ("gate:verdict", "gate:input", "review", "security", "test", "lint")
    store.record(story_id, Event(kind=NOTE, name=ident.INVALIDATED, ok=True, detail={
        "reason": "worktree:head-moved", "candidate": frozen, "head": head,
        "invalidated": [e.seq for e in ev.events if str(e.detail.get("candidate") or "") == frozen and e.name in names][:200]}))
    from ..harness.runlog import run_log
    run_log(root, f"story={story_id} HEAD {head[:8]} is not the candidate of record {frozen[:8]}: "
                  f"its verdicts are invalidated; the tree will be graded anew")


def _finding_line(f) -> str:
    """One reviewer finding as a line for the developer — a structured item or a legacy string."""
    if isinstance(f, dict):
        where = str(f.get("file") or "")
        if f.get("line"):
            where += f":{f.get('line')}"
        why = str(f.get("why") or f.get("text") or "")
        return f"[{f.get('tag') or 'block'}] {where} — {why}".strip(" —")
    return str(f)


def implement_story(
    story: Story,
    *,
    project: Path | str,
    workdir: Path | str | None = None,
    artifact_root: Path | str | None = None,
    client: ClientAdapter,
    config: Config | None = None,
    catalog: Catalog | None = None,
    architecture: Architecture | None = None,
    contract: DesignContract | None = None,
) -> StoryOutcome:
    """Run a story until it passes the gate or exhausts retries."""
    from ..harness.runlog import one_line, run_log

    project = Path(project)
    workdir = Path(workdir) if workdir else project
    root = Path(artifact_root) if artifact_root else project / "_bmad-output"
    cfg = config or Config.load(project)
    cat = catalog or load_catalog()
    contract = contract if contract is not None else load_contract(root)

    def _log(msg: str) -> None:
        run_log(root, msg)

    outcome = StoryOutcome(story_id=story.id)
    max_retries = cfg["run.max_retries"]
    # Infrastructure errors have their own budget: they score nothing, so
    # spending one is not spending a quality attempt. `-1` keeps the old
    # coupling to `max_retries`; a project on a client with a measured failure
    # rate sets its own number (`run.infra_retries`).
    khai = int(cfg["run.infra_retries"])
    infra_budget = max_retries + 1 if khai < 0 else khai
    feedback = _unfinished_review(root, story.id, workdir)

    _log(f"story={story.id} START max_retries={max_retries}")

    base_ref = ""
    if workdir != project:
        head = head_sha(project)
        base_ref = fork_point(str(workdir), head) if head else ""

    _record_head_moved(root, story.id, workdir)
    run_baseline(story, workdir=workdir, artifact_root=root, config=cfg, base_ref=base_ref)

    def _review_stage(attempt: Attempt) -> Attempt:
        """Retry the stages that said NOTHING about the frozen candidate — the reviewer, the security reviewer,
        a tool that could not run — while the gate is blocked only by such absences. Bounded per stage and per
        candidate; the terminal names the stage (REVIEW_UNRUNNABLE / SECURITY_UNRUNNABLE / ENVIRONMENT_FAILURE)
        and keeps the candidate. Never a developer session: nothing about the code has been said (D-032 for the
        reviewer; SS-13, SS-14, SS-19 for the rest)."""
        sha = attempt.candidate
        tool_retries = 0
        scope = effective_write_scope(story, project)
        changed = changed_files(str(workdir), base_ref=base_ref)
        # the list the attempt was written and first scored against, pinned in its gate:input (SS-20, INV-D.1);
        # recomputed from the ledger only when no scoring of this candidate exists yet
        pinned = next((e for e in reversed(EvidenceStore(root).read(story.id).of(NOTE, "gate:input"))
                       if str(e.detail.get("candidate") or "") == attempt.candidate), None)
        preservation = (list(pinned.detail.get("preservation") or []) if pinned is not None
                        else preservation_items(story, project=project, ledger=_ledger(root)))
        def _budget_left(absent: list[str]) -> bool:
            stages = {_stage_of(n) for n in absent}
            ev_now = EvidenceStore(root).read(story.id)
            if "review" in stages and attempt.review_attempt > MAX_REVIEW_RETRIES:
                return False
            if "security" in stages and _security_executions(ev_now, story.id, sha) > MAX_REVIEW_RETRIES:
                return False
            if "tools" in stages and tool_retries > MAX_TOOL_RETRIES:
                return False
            return True


        absent = _absent_stages(attempt)
        while absent and _budget_left(absent) and not _verifier_budget_cap(attempt):
            _log(f"story={story.id}#{attempt.number} {', '.join(absent)} UNRUNNABLE on candidate {sha[:8]} "
                 f"— retrying the {'/'.join(sorted({_stage_of(n) for n in absent}))} stage(s), not the developer: "
                 f"{(attempt.review_unrunnable or getattr(attempt.security, 'unrunnable', '') or absent[0])[:80]}")
            if "tools" in {_stage_of(n) for n in absent}:
                tool_retries += 1
            lai = Attempt(number=attempt.number, verify_only=True)
            lai.candidate = sha
            lai = verify_candidate(
                story, project=project, workdir=workdir, artifact_root=root, client=client,
                config=cfg, catalog=cat, architecture=architecture, contract=contract,
                attempt=lai, base_ref=base_ref, scope=scope, changed=changed,
                preservation=preservation, reuse=True,
            )
            outcome.attempts.append(lai)
            attempt = lai
            absent = _absent_stages(attempt)
        if absent and _verifier_budget_cap(attempt):
            outcome.block(StageOutcome.BUDGET, f"budget cap reached inside a verifier session on candidate {sha[:8]}: "
                                               f"{_verifier_budget_cap(attempt)}. The candidate is kept; raise the cap and re-run "
                                               f"`{aisef_command()} run --verify-only --story {story.id}`.")
            _log(f"story={story.id} BUDGET cap inside a verifier on {sha[:8]}")
        elif absent:
            stages = {_stage_of(n) for n in absent}
            hint = f"`{aisef_command()} run --verify-only --story {story.id}`"
            if "tools" not in stages and "review" in stages:
                stages = {"review"}          # both verifiers absent: the reviewer's absence names the terminal
            if stages == {"review"}:
                outcome.block(StageOutcome.UNRUNNABLE, (
                    f"{REVIEW_UNRUNNABLE}: the reviewer did not produce a verdict on candidate "
                    f"{sha[:8]} in {attempt.review_attempt} executions — last: "
                    f"{attempt.review_unrunnable}. Deterministic checks passed and the candidate is "
                    f"kept; no developer change is needed. Re-run the review stage when the reviewer "
                    f"can run: {hint}."))
            elif stages == {"security"}:
                outcome.block(StageOutcome.UNRUNNABLE, (
                    f"{SECURITY_UNRUNNABLE}: the security reviewer did not produce a verdict on candidate "
                    f"{sha[:8]} — last: {getattr(attempt.security, 'unrunnable', '')}. The candidate is kept; "
                    f"no developer change is needed. Re-run when it can: {hint}."))
            else:
                names = ", ".join(absent)
                outcome.block(StageOutcome.ENVIRONMENT_FAILURE, (
                    f"ENVIRONMENT_FAILURE: {names} could not run on candidate {sha[:8]} after "
                    f"{tool_retries} re-run(s) — the environment, not the work, is what failed. The candidate "
                    f"is kept; fix the environment and re-run: {hint}."))
            _log(f"story={story.id} {outcome.terminal} after retrying {'/'.join(sorted(stages))} on {sha[:8]}")
        return attempt

    # A resumed story whose worktree already carries a candidate that failed
    # only because the reviewer did not run picks up at the review stage.
    pending = _pending_review(root, story.id, workdir)
    if pending:
        _log(f"story={story.id} resuming at the review stage on candidate {pending[:8]}")
        attempt = Attempt(number=outcome.quality_attempts + 1, verify_only=True)
        attempt.candidate = pending
        attempt.review_unrunnable = "pending from a previous run"
        attempt.review_attempt = _review_executions(EvidenceStore(root).read(story.id), story.id, pending)
        attempt.gate = story_gate.StoryGate(story_id=story.id, checks=[
            story_gate.Check("review", story_gate.Outcome.UNRUNNABLE, "pending from a previous run")])
        attempt = _review_stage(attempt)
        if attempt.ok:
            _log(f"story={story.id} review stage OK on resumed candidate {pending[:8]}")
            return outcome
        if outcome.blocked_reason:
            return outcome
        # A genuine verdict now exists: the loop below reads it as feedback.
        feedback = feedback or _unfinished_review(root, story.id, workdir)

    while True:
        n = outcome.quality_attempts + 1
        if workdir != project:
            # D-034: a developer attempt opens on a tree clean of out-of-scope
            # changes, or does not open. Restoration is path-specific and only
            # for what an attempt of this story is on record for.
            hygiene = recover_out_of_scope(EvidenceStore(root), story.id, workdir=workdir,
                                           scope=effective_write_scope(story, project),
                                           next_attempt=n, artifact_root=root)
            if hygiene is not None and not hygiene.ok:
                outcome.block(StageOutcome.ENVIRONMENT_FAILURE, hygiene.detail["reason"])
                _log(f"story={story.id} BLOCKED retry hygiene: {hygiene.detail['reason'][:160]}")
                return outcome
        _log(f"story={story.id} attempt={n} START")
        attempt = run_attempt(
            story,
            project=project,
            workdir=workdir,
            artifact_root=root,
            client=client,
            config=cfg,
            catalog=cat,
            architecture=architecture,
            contract=contract,
            number=n,
            feedback=feedback,
            base_ref=base_ref,
        )
        outcome.attempts.append(attempt)

        # A verifier or a tool did not run on an otherwise-good candidate: retry THAT stage, bounded, before
        # anything else is decided (D-032; SS-13, SS-14, SS-19).
        if (cap := _verifier_budget_cap(attempt)):
            outcome.block(StageOutcome.BUDGET, f"budget cap reached inside a verifier session on candidate "
                                               f"{attempt.candidate[:8]}: {cap}. The candidate is kept; raise the cap and "
                                               f"re-run `{aisef_command()} run --verify-only --story {story.id}`.")
            _log(f"story={story.id} BUDGET cap inside a verifier on {attempt.candidate[:8]}")
            return outcome
        if _absent_stages(attempt):
            attempt = _review_stage(attempt)
            if outcome.blocked_reason:
                return outcome

        if attempt.ok:
            _log(f"story={story.id} attempt={n} OK ${attempt.cost_usd:.2f}")
            return outcome

        if attempt.fatal:
            kind = (StageOutcome(attempt.outcome) if attempt.outcome in StageOutcome._value2member_map_ else
                    StageOutcome.AUTH_FAILURE if exit_status_of_error(attempt.error) == "auth" else
                    StageOutcome.ISOLATION_BREACH if "isolation" in attempt.error.lower() else
                    StageOutcome.ENVIRONMENT_FAILURE)
            outcome.block(kind, attempt.error)
            _log(f"story={story.id} attempt={n} FATAL {kind.value} ${attempt.cost_usd:.2f} err={attempt.error[:120]}")
            return outcome

        if attempt.infra:
            infra_budget -= 1
            if (lien := _noop_lien_tiep(outcome.attempts)) >= MAX_NOOP:
                # Not a failure to retry: a decision, stated twice. Say which
                # decision, and prefer the plan diagnosis when the last graded
                # verdict explains it (lỗi 127).
                plan = nop_deadlock(outcome.attempts)
                outcome.block(StageOutcome.PLAN_CONFLICT if plan else StageOutcome.NOOP, plan or (
                    f"{lien} sessions in a row ran clean and wrote nothing: {attempt.error} "
                    f"Re-opening with the same context returns the same decision — "
                    f"read the last gate verdict and fix what it asks for, or the story."
                ))
                _log(f"story={story.id} BLOCKED {lien} no-op sessions in a row")
                return outcome
            cho = attempt.retry_after
            _log(f"story={story.id} attempt={n} INFRA ${attempt.cost_usd:.2f} "
                 f"err={attempt.error[:80]} budget={infra_budget}"
                 + (f" wait={cho:.0f}s" if cho else ""))
            if infra_budget <= 0:
                outcome.block(StageOutcome.NOOP if attempt.noop else
                              StageOutcome(attempt.outcome) if attempt.outcome in StageOutcome._value2member_map_ else
                              StageOutcome.INFRA_FAILURE, (
                    f"sessions kept producing nothing to grade: {attempt.error}"
                    if attempt.noop else
                    f"recurring infrastructure error: {attempt.error}"
                ))
                _log(f"story={story.id} BLOCKED "
                     + ("no-op sessions" if attempt.noop else "infra budget exhausted"))
                return outcome
            if cho:
                time.sleep(cho)
            continue

        loi_ke_hoach = attempt.plan_findings
        if loi_ke_hoach:
            outcome.block(StageOutcome.PLAN_CONFLICT, (
                "deadlock due to plan, reviewer verified: "
                + "; ".join(loi_ke_hoach[:2])
                + ". Fix the acceptance criteria or the story's write_scope, then "
                "re-run — retrying will not resolve this."
            ))
            _log(f"story={story.id} DEADLOCK plan: {'; '.join(loi_ke_hoach[:2])}")
            return outcome

        van = nop_deadlock(outcome.attempts) or deadlock_reason(
            outcome.attempts, effective_write_scope(story, project))
        if van:
            outcome.block(StageOutcome.PLAN_CONFLICT, van)
            _log(f"story={story.id} DEADLOCK {van[:120]}")
            return outcome

        if outcome.quality_attempts > max_retries:
            # "Did not pass gate" is only true if a gate ever ran. A story whose
            # every session ended out of turns with an untouched tree never
            # produced a verdict, and closing it with that line sends the reader
            # to read gate failures that do not exist (lỗi 130). The sessions
            # are the story here, so say what they did.
            da_cham = [a for a in outcome.attempts if a.gate is not None]
            if da_cham:
                outcome.block(StageOutcome.QUALITY_BLOCK,
                              f"tried {outcome.quality_attempts} attempts, still did not pass gate")
            else:
                ket = sorted({a.error.split(":")[0].strip() for a in outcome.attempts if a.error})
                n_s = outcome.quality_attempts
                outcome.terminal = StageOutcome.QUALITY_BLOCK.value
                outcome.blocked_reason = (
                    f"{n_s} session{'s' if n_s != 1 else ''} ended with nothing to grade "
                    f"— no gate verdict exists for this story"
                    + (f" ({', '.join(ket)})" if ket else "")
                    + ". The sessions are the story: read the last one's turns, and consider "
                    "whether `run.max_turns` fits this model or the story is too large for "
                    "one session."
                )
            _log(f"story={story.id} EXHAUSTED {outcome.quality_attempts} attempts ${outcome.cost_usd:.2f}")
            # What was still blocking when it gave up — the one thing a reader
            # opens the log for after an exhausted story.
            for c in (attempt.gate.failures if attempt.gate else []):
                _log(f"story={story.id} EXHAUSTED ✗ {c.name} · {c.outcome.value} · "
                     + (one_line(c.detail) or "(no detail recorded)"))
            return outcome

        gate_fb = attempt.gate.feedback() if attempt.gate else attempt.error
        # Check names only: each reason already has its own `gate ✗` line above.
        # Slicing the joined feedback to 120 chars printed one reason, cut
        # mid-word, and hid the other seven.
        _log(f"story={story.id} attempt={n} FAIL ${attempt.cost_usd:.2f} gate="
             + (",".join(c.name for c in attempt.gate.failures) if attempt.gate
                else one_line(attempt.error)))
        feedback = gate_fb
        if attempt.review_findings:
            feedback += "\n" + "\n".join(f"- {f}" for f in attempt.review_findings[:10])


def verify_only(
    story: Story,
    *,
    project: Path | str,
    workdir: Path | str,
    artifact_root: Path | str | None = None,
    client: ClientAdapter,
    config: Config | None = None,
    catalog: Catalog | None = None,
    architecture: Architecture | None = None,
    contract: DesignContract | None = None,
    repeat: int = 1,
) -> StoryOutcome:
    """Re-verify on the frozen candidate (ADR-004 R13) -- does **not** open
    a developer session.  Same signature as `implement_story` so `run.py`
    can substitute it (``repeat`` is a keyword with a default, `run.py`
    attaches via `partial`).

    ``repeat`` = k: each re-runnable check runs k times on the same SHA;
    tests that change outcome across runs -> `flaky_ids`, gate records
    UNRUNNABLE "unstable" instead of FAILED; red in all runs -> FAILED as
    usual (`_repeat_note`).

    Candidate = HEAD of story branch; `workdir` must be standing there
    (`run.py` recreates the worktree **without** bringing main in -- bringing
    it in creates a new version, and all old evidence becomes stale).
    Re-freeze: nothing to commit means SHA is unchanged, and evidence for
    test/lint/`qa:*`/review at that SHA is kept by
    `verify_candidate(reuse=True)`, only re-running failed/missing checks.

    Why needed: e9 STORY-01-07 (2026-09-06) failed attempt 3 solely because
    e2e was load-sensitive; candidate `a60612e` measured 10/10 green on
    retry, review and security at that exact SHA both passed -- but the
    harness only knew "new attempt = new developer session", costing $10-15
    to rebuild what already existed.  No gate relaxation: still scores every
    item.

    Does not count toward `run.max_retries` (`Attempt.verify_only`): this is
    re-verification, not a developer attempt.
    """
    project = Path(project)
    workdir = Path(workdir)
    root = Path(artifact_root) if artifact_root else project / "_bmad-output"
    cfg = config or Config.load(project)
    cat = catalog or load_catalog()
    contract = contract if contract is not None else load_contract(root)

    outcome = StoryOutcome(story_id=story.id)
    evidence = EvidenceStore(root)
    # Sequence number = the n-th gate scoring for the story, so the file
    # `reviews/<story>-review-<n>.md` (if re-reviewed) does not overwrite
    # the previous developer attempt's text.
    number = len(evidence.read(story.id).of(NOTE, "gate:verdict")) + 1
    head = head_sha(project)
    base_ref = fork_point(str(workdir), head) if head else ""
    scope = effective_write_scope(story, project)
    changed_now = changed_files(str(workdir), base_ref=base_ref)

    attempt = Attempt(number=number, verify_only=True)
    attempt.candidate = freeze_candidate(
        workdir, story=story, scope=scope, isolated=True, evidence=evidence,
        artifact_root=root, number=number, changed=changed_now, verify_only=True,
    )
    evidence.candidate = attempt.candidate
    # R4: same list for reviewer (if re-called), security and gate --
    # computed once here as `build_context` does before the developer session.
    preservation = preservation_items(story, project=project, ledger=_ledger(root))
    attempt = verify_candidate(
        story, project=project, workdir=workdir, artifact_root=root, client=client,
        config=cfg, catalog=cat, architecture=architecture, contract=contract,
        attempt=attempt, base_ref=base_ref, scope=scope, changed=changed_now,
        preservation=preservation, reuse=True, repeat=repeat,
    )
    evidence.record(story.id, Event(
        kind=NOTE, name="verify-only", ok=attempt.ok,
        detail={
            "reran": attempt.reran, "kept": attempt.kept, "attempt": number,
            "repeat": repeat,
            # Main branch advanced past the candidate: still score the
            # candidate -- that is the version being scored -- but note it;
            # the end-of-attempt merge will encounter the new commits.
            "main_ahead": head if head and base_ref and base_ref != head else "",
        },
    ))
    outcome.attempts.append(attempt)
    absent = _absent_stages(attempt)
    if absent:
        # A verifier or tool did not run again: name that, not a failed gate (D-032; SS-13/14).
        stages = {_stage_of(n) for n in absent}
        label = (REVIEW_UNRUNNABLE if "review" in stages and "tools" not in stages
                 else SECURITY_UNRUNNABLE if stages == {"security"} else "ENVIRONMENT_FAILURE")
        why = attempt.review_unrunnable or getattr(attempt.security, "unrunnable", "") or ", ".join(absent)
        outcome.block(StageOutcome.UNRUNNABLE if label != "ENVIRONMENT_FAILURE" else StageOutcome.ENVIRONMENT_FAILURE, (
            f"{label}: {', '.join(absent)} did not produce a verdict on candidate "
            f"{attempt.candidate[:8]} — {why}. Deterministic checks passed and the candidate is "
            f"kept; re-run `{aisef_command()} run --verify-only --story {story.id}` when it can run."
        ))
    elif not attempt.ok:
        outcome.block(StageOutcome.QUALITY_BLOCK, (
            f"re-verify candidate {attempt.candidate[:7]} did not pass gate: "
            + "; ".join(c.name for c in attempt.gate.failures)
        ))
    return outcome
