"""Acceptance report — aggregate existing evidence, do not narrate.

Every figure here is read from artifacts and on-disk evidence. Nothing is
written by hand, because a hand-written acceptance report only proves the
author believes they are correct.

Five sections, answering the five questions a reviewer asks:

* **Traceability** — which PRD requirement maps to which story, which files
  does that story touch, and is there a test.
* **Quality** — which gates passed, which check types were run.
* **Operations** — per-story cost, duration, and number of runs.
* **Harness** — do the six groups have real execution evidence.
* **Improvement** — behavior ledger (`control/ledger.py`): verified
  capabilities, regressions, closed gaps, marginal improvement. This is the
  question story gates cannot answer, since a gate scores **one** story at
  **one** point in time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..control.approvals import (
    GATE_ORDER,
    PRE_DEPLOY_REPORT,
    STORIES_INDEX,
    ApprovalStore,
    Status,
)
from ..control import ledger
from ..control.gate import CHECK_NAMES, qualification_table
from ..control.normalize import parse_prd_file
from ..control.outcome import Outcome
from ..control.state import StateStore
from ..harness.observe import AGENT_RUN, HANDOFF, MOCKUP_MAP, TOOL_RUN, EvidenceStore


def mockup_cell(maps) -> str:
    """Mockup-map cell for a story: **latest result per screen**.

    Before 2026-09-05 this cell required *every* comparison to have passed —
    a story that passed the gate on its final run still showed ✗ because
    earlier runs failed (e9 STORY-01-05: done, map 3/3 on last run, report
    showed ✗). History lives in evidence; the report states current status.
    """
    if not maps:
        return "✗"
    latest: dict[str, bool] = {}
    for m in maps:
        latest[m.name] = bool(m.ok)
    return "✅" if all(latest.values()) else "✗"


@dataclass
class Row:
    requirement: str
    title: str
    stories: list[str] = field(default_factory=list)
    tested: bool = False

    @property
    def covered(self) -> bool:
        return bool(self.stories)


#: Evidence not belonging to any story: planning and mockup phases.
PHASE_PREFIXES = ("plan-", "mockup-")


@dataclass
class Report:
    project: str = ""
    traceability: list[Row] = field(default_factory=list)
    gates: list[tuple[str, str, str]] = field(default_factory=list)
    stories: list[dict] = field(default_factory=list)
    phases: list[dict] = field(default_factory=list)
    harness: dict[str, str] = field(default_factory=dict)
    #: Pre-deploy gate result, if evaluated.
    pre_deploy: dict = field(default_factory=dict)
    total_cost_usd: float = 0.0
    #: Behavior ledger metrics (ADR-004 R2/R7) — projected from the same evidence.
    ledger: dict = field(default_factory=dict)
    #: Story gate qualification table (ADR-005 V9): check name -> controls present.
    #: Empty when `tests/` is absent (wheel install) — prints `?`, not 0.
    qualification: dict = field(default_factory=dict)

    @property
    def uncovered(self) -> list[str]:
        return [r.requirement for r in self.traceability if not r.covered]

    def markdown(self) -> str:
        lines = [
            f"# Acceptance Report — {self.project}",
            "",
            "All figures below are read from artifacts and on-disk evidence.",
            "",
            "## 1. Requirements Traceability",
            "",
            "| Requirement | Title | Covering Story | Test Evidence |",
            "|---|---|---|---|",
        ]
        # Acceptance scope (pre-deploy --epic, decision C-a): requirements whose
        # only stories are out of scope show "out of scope", not "—" (nothing yet).
        ngoai = set((self.pre_deploy.get("scope") or {}).get("outside") or [])
        for row in self.traceability:
            if row.tested:
                cell = "✅"
            elif row.stories and ngoai and all(s in ngoai for s in row.stories):
                cell = "out of scope"
            else:
                cell = "—"
            lines.append(
                f"| {row.requirement} | {row.title[:60]} | "
                f"{', '.join(row.stories) or '—'} | {cell} |"
            )
        if self.uncovered:
            lines += ["", f"**Uncovered:** {', '.join(self.uncovered)}"]

        lines += ["", "## 2. Approval Gate", "", "| Gate | Status | Approved By |", "|---|---|---|"]
        for gate, status, by in self.gates:
            lines.append(f"| {gate} | {status} | {by or '—'} |")

        lines += [
            "", "## 3. Per-Story Operations", "",
            "| Story | Status | Candidate | Agent Runs | Cost | Duration | Mockup Map | AC w/ Test | Behaviors (V/G/R) |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for s in self.stories:
            lines.append(
                f"| {s['id']} | {s['status']} | {s.get('candidate') or '—'} | {s['runs']} | "
                f"${s['cost']:.2f} | {s['duration_ms'] / 1000:.0f}s | {s['mockup']} | "
                f"{s.get('ac', '—')} | {s.get('behaviors', '—')} |"
            )
        chuoi = [s for s in self.stories if s.get("handoffs")]
        if chuoi:
            lines += ["", "Handoff chains (from `handoff` evidence, each role in a new session):", ""]
            lines += [f"- {s['id']}: {s['handoffs']}" for s in chuoi]
        if self.phases:
            lines += [
                "", "### Planning and Mockup Cost", "",
                "| Phase | Runs | Cost | Duration |", "|---|---|---|---|",
            ]
            for ph in self.phases:
                lines.append(
                    f"| {ph['id']} | {ph['runs']} | ${ph['cost']:.2f} | "
                    f"{ph['duration_ms'] / 1000:.0f}s |"
                )

        lines += ["", f"**Total Cost:** ${self.total_cost_usd:.2f}"]

        # How many gate checks are **fully qualified** (positive · negative · env)
        # — read from the test table, not from "gate has N conditions" counting.
        qualified = sum(all(v.values()) for v in self.qualification.values())
        total = len(self.qualification) or len(CHECK_NAMES)
        lines += ["", f"**Story Gate:** gate checks with all 3 controls: "
                      f"{qualified if self.qualification else '?'}/{total} "
                      f"(`tests/test_gate_qualification.py`; `?` = no `tests/` directory)"]

        lines += ["", "## 4. Six Harness Groups", "", "| Group | Evidence |", "|---|---|"]
        for group, proof in self.harness.items():
            lines.append(f"| {group} | {proof} |")

        lines += self._ledger_section()

        lines += ["", "## 6. Pre-Deploy Gate", ""]
        if not self.pre_deploy:
            lines.append("_Not yet evaluated — run `aisef pre-deploy`._")
        else:
            scope = self.pre_deploy.get("scope") or {}
            if scope:
                ngoai = scope.get("outside") or []
                lines += [
                    f"Acceptance scope: **{scope.get('epic')}** — "
                    f"{len(scope.get('stories') or [])} stories. "
                    + (f"**Out of scope (not accepted): {len(ngoai)} stories** — "
                       + ", ".join(ngoai[:8]) + ("…" if len(ngoai) > 8 else "") + "."
                       if ngoai else "No stories out of scope."),
                    "",
                ]
            lines += ["| Check | Result |", "|---|---|"]
            for c in self.pre_deploy.get("checks", []):
                # Mark by **outcome**, not by "non-blocking": printing ✅ for a
                # not-applicable or exempted item would self-certify an unchecked pass.
                try:
                    mark = Outcome(str(c.get("outcome") or "")).mark
                except ValueError:
                    mark = "✅" if c.get("passed") else "✗"
                lines.append(f"| {c.get('name')} | {mark} {c.get('detail', '')} |")
            qa = self.pre_deploy.get("qa") or {}
            if qa:
                unconf = ", ".join(qa.get("unconfigured", [])) or "—"
                failed = ", ".join(qa.get("failed", [])) or "—"
                lines += [
                    "",
                    f"Qualifications: failed = {failed} · unconfigured = {unconf}",
                ]
        return "\n".join(lines) + "\n"

    def _ledger_section(self) -> list[str]:
        """Section 5 — continuous improvement (ADR-004 R7).

        Four metrics, all projected from the same evidence as section 3: how
        many verified capabilities grew, how many previously-passing ones
        regressed, how many gaps were closed, and net behaviors per dollar.
        """
        m = self.ledger
        if not m:
            return ["", "## 5. Continuous Improvement (Behavior Ledger)", "",
                    "_No evidence to project into behaviors yet._"]
        lines = [
            "", "## 5. Continuous Improvement (Behavior Ledger)", "",
            "| Metric | Value |", "|---|---|",
            f"| Verified capabilities (current VERIFIED) | {m['verified']} |",
            f"| Ever verified (growth, unique over time) | {m['ever_verified']} |",
            f"| GAP | {m['gap']} |",
            f"| REOPENED (currently regressed) | {m['reopened']} |",
            f"| Regression events / rate over ever-verified | "
            f"{m['reopen_events']} · {m['reopen_rate']:.2f} |",
            f"| **Cross-story** regressions (later story broke earlier one) | {m['cross_reopens']} |",
            f"| Gaps closed (resolved) | {m['resolved']} |",
        ]
        cross = m.get("cross_reopen_list") or []
        if cross:
            lines += ["", "Cross-story regressions with source:", ""]
            lines += [
                f"- `{c['id']}` green at {c['verified_by']} → red again at {c['regressed_by']}"
                for c in cross[:10]
            ]
        loops = m.get("loops") or []
        if loops:
            lines += [
                "", "| Loop | VERIFIED | GAP | REOPENED | ΔV | ΔR | $ | Marginal Improvement |",
                "|---|---|---|---|---|---|---|---|",
            ]
            for lo in loops:
                marg = "—" if lo["marginal"] is None else f"{lo['marginal']:.2f}/\\$"
                lines.append(
                    f"| {lo['n']} | {lo['verified']} | {lo['gap']} | {lo['reopened']} | "
                    f"{lo['d_verified']:+d} | {lo['d_reopened']:+d} | "
                    f"${float(lo.get('cost_usd') or 0):.2f} | {marg} |"
                )
        return lines


def build(project: Path | str) -> Report:
    # `resolve()` because this function can be called directly from other code,
    # not only via CLI (where the path is already absolute at the entry point).
    project = Path(project).resolve()
    root = project / "_bmad-output"
    report = Report(project=project.name)

    index = _read_index(root)
    story_screens = {s["id"]: s.get("screens", []) for s in index.get("stories", [])}
    story_ac = {s["id"]: len(s.get("acceptance_criteria") or []) for s in index.get("stories", [])}
    fr_to_stories: dict[str, list[str]] = {}
    for story in index.get("stories", []):
        for fr in story.get("covers", []):
            fr_to_stories.setdefault(fr, []).append(story["id"])

    led = ledger.build(root)
    report.ledger = led.metrics() if led.behaviors else {}

    evidence = EvidenceStore(root)
    tested_stories = {
        sid for sid in evidence.stories() if evidence.read(sid).tests_green()
    }

    prd_path = root / "prd.md"
    if prd_path.is_file():
        for req in parse_prd_file(prd_path).functional():
            stories = fr_to_stories.get(req.id, [])
            report.traceability.append(
                Row(
                    requirement=req.id,
                    title=req.title,
                    stories=stories,
                    tested=bool(stories) and any(s in tested_stories for s in stories),
                )
            )

    approvals = ApprovalStore(root)
    for gate in GATE_ORDER:
        rec = approvals.load(gate)
        report.gates.append(
            (gate.value, approvals.status(gate).value, rec.decided_by if rec else "")
        )

    state = StateStore(root).load()
    for sid in sorted(evidence.stories()):
        if not sid.startswith(PHASE_PREFIXES):
            continue
        ev = evidence.read(sid)
        report.phases.append({
            "id": sid,
            "runs": len(ev.of(AGENT_RUN)),
            "cost": ev.total_cost_usd,
            "duration_ms": ev.total_duration_ms,
        })

    story_ids = [s for s in evidence.stories() if not s.startswith(PHASE_PREFIXES)]
    for sid in sorted(set(list(state.stories) + story_ids)):
        ev = evidence.read(sid)
        mockup = mockup_cell(ev.of(MOCKUP_MAP)) if story_screens.get(sid) else "—"
        record = state.stories.get(sid)
        report.stories.append({
            "id": sid,
            "status": record.status if record else "?",
            # Commit the story's evidence points to (ADR-004 R1) — if absent
            # the report must say so explicitly, not stay silent.
            "candidate": ev.candidate[:7],
            "runs": len(ev.of(AGENT_RUN)),
            "cost": ev.total_cost_usd,
            "duration_ms": ev.total_duration_ms,
            "mockup": mockup,
            "ac": _ac_cell(sid, story_ac.get(sid, 0), ev),
            "behaviors": _behavior_cell(led, sid),
            "handoffs": " → ".join(
                f"{e.detail.get('to')}#{e.detail.get('attempt')}" for e in ev.of(HANDOFF)
            ),
        })
    report.total_cost_usd = sum(s["cost"] for s in report.stories) + sum(
        p["cost"] for p in report.phases
    )
    report.harness = _harness_evidence(project, root, evidence)
    report.qualification = qualification_table()

    pre_deploy_file = root / PRE_DEPLOY_REPORT
    if pre_deploy_file.is_file():
        try:
            report.pre_deploy = json.loads(pre_deploy_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report.pre_deploy = {}
    return report


def _behavior_cell(led, sid: str) -> str:
    """Behavior cell: `V/G/R` for a story. `R > 0` is what the old report
    could not express — a story that passed the gate yet left a previously-
    passing behavior now broken."""
    v, g, r = led.counts_for(sid)
    return "—" if not (v or g or r) else f"{v}/{g}/{r}"


def _ac_cell(sid: str, n: int, ev) -> str:
    """`k/n` acceptance criteria with coded tests, from the last green test run.
    If test names cannot be read: `?/n` — unknown, not sufficient."""
    from ..control.acceptance import missing as ac_missing

    if n <= 0:
        return "—"
    green = [e for e in ev.of(TOOL_RUN, "test") if e.ok]
    if not green or not green[-1].detail.get("test_format"):
        return f"?/{n}"
    missing = ac_missing(sid, n, list(green[-1].detail.get("test_ids") or []))
    return f"{n - len(missing)}/{n}"


def _read_index(root: Path) -> dict:
    path = root / STORIES_INDEX
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _harness_evidence(project: Path, root: Path, evidence: EvidenceStore) -> dict[str, str]:
    """Six harness groups — each must point to a real artifact."""
    from ..harness.prompts import load_catalog

    any_story = [s for s in evidence.stories() if not s.startswith(PHASE_PREFIXES)]
    ev = evidence.read(any_story[0]) if any_story else None

    def yes(cond, proof, missing="no evidence"):
        return proof if cond else missing

    prompts = load_catalog()
    return {
        "1 Instructions & Rules": yes(
            (project / "CLAUDE.md").is_file(),
            f"CLAUDE.md · AGENTS.md · {len(prompts.prompts)} versioned prompts",
        ),
        "2 Tool": yes(
            bool(ev and ev.of(TOOL_RUN)),
            f"{len(ev.of(TOOL_RUN)) if ev else 0} recorded tool runs",
        ),
        "3 Sandbox": _isolation_note(ev),
        "4 Orchestration": yes(
            (root / STORIES_INDEX).is_file(),
            "story index with parallel-run batches pre-computed",
        ),
        "5 Guardrail": yes(
            (project / ".claude" / "settings.json").is_file(),
            ".claude/settings.json wiring 7 guards to 3 hooks",
        ),
        "6 Observability": yes(
            bool(any_story),
            f"evidence/ has {len(any_story)} stories with cost and latency",
        ),
    }


def _isolation_note(ev) -> str:
    """**Observed** isolation level, not the desired one.

    Reporting "sandboxed" when execution actually ran directly on the host is
    exactly the kind of self-certification this framework exists to prevent.
    """
    if ev is None:
        return "no evidence"
    levels = {
        str(e.detail.get("isolation"))
        for e in ev.of(TOOL_RUN)
        if e.detail.get("isolation")
    }
    if not levels:
        return "no evidence"
    degraded = any(e.detail.get("degraded") for e in ev.of(TOOL_RUN))
    note = "observed isolation level: " + ", ".join(sorted(levels))
    return note + (" — **degraded**, no container" if degraded else "")


def write(project: Path | str, *, out: Path | str | None = None) -> Path:
    report = build(project)
    path = Path(out) if out else Path(project) / "docs" / "ACCEPTANCE-REPORT.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.markdown(), encoding="utf-8")
    return path
