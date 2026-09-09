"""Planning phase pipeline — run BMAD skills sequentially, stop at each gate.

Each phase is a BMAD skill running in headless mode. After each phase:

1. read the JSON status BMAD returns (``complete`` / ``partial`` / ``blocked``);
2. verify **files on disk** against what it claims to have produced;
3. run **machine gate** — check whatever can be checked by code;
4. stop at the **human gate**, unless it is in ``--auto-approve``.

``run_pipeline`` does **not** run everything then report: it stops at the first
unapproved gate and returns. Call again after human approval to resume from
there — same mechanism for background runs, CI, and chat sessions, with no
process left waiting (decision D2).

Phases whose artifacts already exist are **skipped**, so reruns don't pay for
work already done.

**No `bmad-sprint-planning` phase.** Story execution order can be computed
deterministically from dependencies and ``write_scope`` (``control/scheduler``),
so delegating it to a model violates the core principle: when correctness is
required, write code. BMAD stops at generating epics and stories; scheduling
is the framework's job.
"""

from __future__ import annotations

import json
import time

from dataclasses import dataclass, field
from pathlib import Path

from ..clients.base import ClientAdapter, RunSpec
from ..config import Config
from ..control.approvals import GATE_ARTIFACTS, ApprovalStore, Gate, Status
from ..control.bmad_status import HeadlessStatus, parse_headless_status
from ..control.machine_gate import GateResult, check_experience, check_prd
from ..harness.guardrails import (
    ENV_BASELINE_DIRTY,
    ENV_PROJECT,
    ENV_STORY_ID,
    ENV_WORKDIR,
    ENV_WRITE_SCOPE,
    PLANNING_SCOPE,
    changed_files,
)
from ..harness.observe import EvidenceStore
from ..control.normalize import parse_prd_file
from ..clients.stream import INFRA_STATUSES, exit_status_of

ARTIFACT_ROOT = "_bmad-output"
RESPONSE_DIR = "evidence"


def _run_log(project: Path, msg: str) -> None:
    from ..harness.runlog import run_log
    run_log(project / ARTIFACT_ROOT, msg)


def _save_response(project: Path, phase_id: str, text: str, result) -> Path:
    """Save the full LLM response so parser failures are debuggable."""
    d = project / ARTIFACT_ROOT / RESPONSE_DIR
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"plan-{phase_id}.response.md"
    head = (
        f"# plan-{phase_id} response\n\n"
        f"session: {getattr(result, 'session_id', '')} · "
        f"turns: {getattr(result, 'num_turns', 0)} · "
        f"${getattr(result, 'cost_usd', 0.0):.2f}\n\n---\n\n"
    )
    path.write_text(head + (text or ""), encoding="utf-8")
    return path


@dataclass(frozen=True)
class Phase:
    """A planning phase: one BMAD skill, one artifact, one gate."""

    id: str
    skill: str
    #: Files this phase must produce. For gated phases, must match
    #: ``GATE_ARTIFACTS[gate]`` — the gate hashes exactly these files.
    artifacts: tuple[str, ...]
    gate: Gate | None
    #: Artifacts that must exist before this phase runs.
    needs: tuple[str, ...] = ()
    goal: str = ""


#: Phase ordering. Sequential because each phase consumes the previous one's output.
#:
#: Filenames are the **actual** names BMAD writes when given an output path —
#: verified by real runs (see `tests/fixtures/bmad/`). The UX phase keeps
#: BMAD's two files (`DESIGN.md` for the visual system, `EXPERIENCE.md` for
#: flows and screens): merging them into a single `ux-spec.md` would break the
#: skill's own `update`/`validate` intent, since it looks for those two files.
PHASES: tuple[Phase, ...] = (
    Phase(
        id="project-context",
        skill="bmad-project-context",
        artifacts=("project-context.md",),
        gate=None,  # background context, not a product decision
        goal="Build project context from requirements: domain, users, constraints.",
    ),
    Phase(
        id="prd",
        skill="bmad-prd",
        artifacts=GATE_ARTIFACTS[Gate.PRD],
        gate=Gate.PRD,
        goal="Write PRD: each functional requirement has an ID and verifiable criteria.",
    ),
    Phase(
        id="architecture",
        skill="bmad-architecture",
        artifacts=GATE_ARTIFACTS[Gate.ARCHITECTURE],
        gate=Gate.ARCHITECTURE,
        needs=("prd.md",),
        goal="Design architecture, number decisions AD-x that stories must comply with.",
    ),
    Phase(
        id="ux",
        skill="bmad-ux",
        artifacts=GATE_ARTIFACTS[Gate.UX_SPEC],
        gate=Gate.UX_SPEC,
        needs=("prd.md",),
        goal="UX specification: visual system, user flows, screen inventory.",
    ),
    Phase(
        id="epics",
        skill="bmad-create-epics-and-stories",
        artifacts=GATE_ARTIFACTS[Gate.EPICS],
        gate=Gate.EPICS,
        needs=("prd.md", "architecture.md", "EXPERIENCE.md"),
        goal=(
            "Split into epics and stories following the template "
            "(`## Epic N: …`, `### Story N.M: …`, Given/When/Then).\n"
            "Right below the acceptance criteria of **each** story, add a block:\n"
            "**Story metadata:**\n"
            "- covers: FR-x, FR-y   (FR IDs from the PRD this story covers)\n"
            "- write_scope: path/to/, path/to/other  "
            "(all paths the story is allowed to write, relative to project root)\n"
            "- depends_on: N.M or none — only declare when the later story **cannot "
            "start** without the result of the earlier one. Chaining by written "
            "order is habit, not dependency: it turns every story sequential and "
            "wastes parallelism. Two stories writing to disjoint paths almost "
            "certainly do not depend on each other.\n"
            "- screens: screen IDs from EXPERIENCE.md that this story builds, "
            "or none if the story has no UI\n"
            "These four lines are a machine-readable contract: missing means the story is blocked."
        ),
    ),
)

#: Story split step — done by the framework itself, no model call.
SPLIT_PHASE = Phase(
    id="stories",
    skill="(code)",
    artifacts=GATE_ARTIFACTS[Gate.STORIES],
    gate=Gate.STORIES,
    needs=("epics.md",),
    goal="Split epics.md into one file per story + index.",
)

PHASE_BY_ID = {p.id: p for p in (*PHASES, SPLIT_PHASE)}


@dataclass
class PhaseOutcome:
    phase: Phase
    ran: bool = False
    skipped_reason: str = ""
    status: HeadlessStatus = field(default_factory=HeadlessStatus)
    machine_gate: GateResult | None = None
    cost_usd: float = 0.0
    duration_ms: int = 0
    error: str = ""
    #: Number of retries due to infra errors (network, timeout) — not quality
    #: errors, but still costs money so must be surfaced.
    infra_retries: int = 0
    #: Only present for the story split step.
    split: object = None

    @property
    def ok(self) -> bool:
        if self.skipped_reason:
            return True
        if self.error:
            return False
        return not (self.machine_gate and not self.machine_gate.passed)

    @property
    def needs_human(self) -> bool:
        """BMAD self-reported that the artifact is not yet standalone."""
        return self.status.needs_human

    def machine_checks(self) -> dict[str, str]:
        """Machine check results, stored with the approval record for audit trail."""
        checks = {"bmad_status": self.status.status or "unreadable"}
        if self.machine_gate:
            checks["machine gate"] = "pass" if self.machine_gate.passed else "fail"
            if self.machine_gate.warnings:
                checks["warnings"] = "; ".join(self.machine_gate.warnings)
        return checks

    def summary(self) -> str:
        if self.skipped_reason:
            return f"{self.phase.id}: skipped — {self.skipped_reason}"
        bits = [f"{self.phase.id}: {'ok' if self.ok else 'FAIL'}"]
        if self.status.parsed:
            bits.append(self.status.summary())
        if self.error:
            bits.append(f"error: {self.error}")
        if self.split is not None:
            bits.append(f"{len(self.split.stories)} stories")
        if self.machine_gate and not self.machine_gate.passed:
            bits.append(f"{len(self.machine_gate.errors)} machine gate errors")
        if self.infra_retries:
            bits.append(f"{self.infra_retries} infra retries")
        if self.cost_usd:
            bits.append(f"${self.cost_usd:.2f}")
        return " · ".join(bits)


@dataclass
class PipelineResult:
    outcomes: list[PhaseOutcome] = field(default_factory=list)
    #: Gate that caused the pipeline to stop for human approval. None means all done.
    waiting_on: Gate | None = None
    failed_at: str = ""

    @property
    def total_cost_usd(self) -> float:
        return sum(o.cost_usd for o in self.outcomes)

    @property
    def complete(self) -> bool:
        return not self.failed_at and self.waiting_on is None

    def summary(self) -> str:
        lines = [o.summary() for o in self.outcomes]
        last = self.outcomes[-1] if self.outcomes else None
        if self.failed_at:
            lines.append(f"\n✗ stopped because phase {self.failed_at} failed")
            if last and last.machine_gate:
                lines.append(last.machine_gate.summary())
        elif self.waiting_on:
            lines.append(f"\n⏸ waiting for approval: {self.waiting_on.value}")
            lines.append(f"   aisef review {self.waiting_on.value}")
        else:
            lines.append("\n✅ all phases done and approved")
        if self.total_cost_usd:
            lines.append(f"cost: ${self.total_cost_usd:.2f}")
        return "\n".join(lines)


def _is_brownfield(project: Path | None) -> bool:
    if project is None:
        return False
    return (Path(project) / ARTIFACT_ROOT / "baseline.md").is_file()


def _brownfield_context(project: Path) -> str:
    """Brownfield context for the prompt — baseline + delta instructions."""
    baseline = Path(project) / ARTIFACT_ROOT / "baseline.md"
    if not baseline.is_file():
        return ""
    try:
        text = baseline.read_text(encoding="utf-8")[:4000]
    except OSError:
        return ""
    return (
        "\n\n## Brownfield Context\n\n"
        "This project ALREADY HAS source code. Here is the baseline (summary):\n\n"
        + text + "\n\n"
        "**Brownfield rules:**\n"
        "- PRESERVE existing valid architecture, code, and behaviour — only change "
        "what the change request requires.\n"
        "- Current code is ground truth; documentation may be stale — note contradictions clearly.\n"
        "- intent: 'update' instead of 'create' when the artifact already exists.\n"
        "- Produce a DELTA, do not regenerate everything.\n"
    )


def build_prompt(phase: Phase, project: Path | None = None) -> str:
    """Build the headless prompt for a phase.

    ``headless: true`` is a BMAD-defined flag that enables non-interactive mode
    and returns a JSON status at the end. Output paths are specified explicitly:
    BMAD respects the given paths (verified in real runs), while its default
    filenames differ across skills.
    """
    brownfield = _is_brownfield(project)
    intent = "update" if brownfield and not _missing(project, phase.artifacts) else "create"

    inputs = ["docs/requirements.md (original requirements)"]
    if brownfield:
        inputs.insert(0, f"{ARTIFACT_ROOT}/baseline.md (brownfield baseline)")
    inputs += [f"{ARTIFACT_ROOT}/{n}" for n in phase.needs]
    outputs = ", ".join(f"{ARTIFACT_ROOT}/{n}" for n in phase.artifacts)
    memo = _stories_gate_memo(project) if phase.gate is Gate.EPICS else ""
    if phase.id == "ux":
        memo += _UX_SCREEN_TABLE
    bf_ctx = _brownfield_context(project) if brownfield and project else ""

    return (
        "headless: true\n\n"
        f'Use the {phase.skill} skill. intent: "{intent}".\n'
        f"doc_workspace: {ARTIFACT_ROOT}\n\n"
        f"Inputs: {', '.join(inputs)}.\n"
        f"Goal: {phase.goal}\n"
        f"Write to exact paths: {outputs}\n\n"
        "IMPORTANT: This project uses AISEF, not the full BMAD framework. "
        "The _bmad/ directory does NOT exist. Skip any activation step that "
        "references _bmad/ (resolve_customization.py, memlog.py, config.yaml). "
        "Use neutral defaults for all BMAD config values (user_name, "
        "communication_language=en, document_output_language=en). "
        "Do not call list_dir or find_file on _bmad/. "
        "Do not run uv commands referencing _bmad/scripts/.\n\n"
        "Do not ask questions. "
        + (
            "Any assumptions you must infer go in assumptions; "
            "anything requiring human decision goes in open_questions — do not choose "
            "silently. "
            if phase.id == "prd"
            else
            "If input documents contain open questions (OQ-*), unresolved items, or "
            "provisional assumptions, resolve each one with the simplest reasonable "
            "MVP default and mark it resolved. Do NOT propagate 'unresolved', "
            "'pending', or 'provisional' into your output — every decision point "
            "must have a concrete answer. "
        )
        + "End with a JSON status following the headless schema."
        + memo + bf_ctx
    )


#: The UX artifact is read by machines, and only the prose contract was ever
#: stated. A real run described "one surface, the Todo List screen" in a
#: paragraph, the phase gate approved, and `aisef mockup` failed later with
#: "does not list any screens" — the requirement had never been written down
#: where the author could see it.
_UX_SCREEN_TABLE = (
    "\n\nEXPERIENCE.md MUST contain a screen inventory **table**, because the "
    "next steps read it: the mockup step builds one HTML file per row, and "
    "stories reference `screen_id`. One row per screen, under a heading such "
    "as `Screen Inventory`, `Screens` or `Information Architecture`:\n\n"
    "| Screen | Route | Purpose |\n"
    "|---|---|---|\n"
    "| Todo List | / | Create and manage tasks |\n\n"
    "`Route` is the path the app serves the screen at (`/`, `/tasks`, "
    "`/note/:id`) — a path, never a sentence. A single-screen app still needs "
    "its one row: prose describing the screens is not readable by the steps "
    "that consume this file."
)


def _stories_gate_memo(project: Path | None) -> str:
    """Previous stories gate feedback — so the agent splits stories correctly (P2-12)."""
    if project is None:
        return ""
    from .story_split import GATE_MEMO

    path = Path(project) / ARTIFACT_ROOT / GATE_MEMO
    if not path.is_file():
        return ""
    try:
        errors = json.loads(path.read_text(encoding="utf-8")).get("errors") or []
    except (OSError, ValueError):
        return ""
    if not errors:
        return ""
    return (
        "\n\nMachine gate `stories` FAILED last time. Fix these issues when "
        "rewriting epics/stories (split oversized stories, do not raise thresholds):\n"
        + "\n".join(f"- {e}" for e in errors)
    )


def _missing(project: Path, names) -> list[str]:
    return [n for n in names if not (project / ARTIFACT_ROOT / n).is_file()]


def run_phase(
    phase: Phase,
    project: Path,
    client: ClientAdapter,
    *,
    config: Config,
    force: bool = False,
) -> PhaseOutcome:
    """Run one phase. Skip if all artifacts exist and force is not set."""
    out = PhaseOutcome(phase=phase)
    # Name the timeout: an agent turn is silent for minutes at a time, and
    # without the bound the reader cannot tell "thinking" from "hung"
    # (measured twice on 2026-09-09: a 14-minute silence each time).
    _run_log(project, f"phase={phase.id} START timeout={config['run.timeout_seconds']}s")

    if not _missing(project, phase.artifacts) and not force:
        out.skipped_reason = "artifacts already exist"
        _run_log(project, f"phase={phase.id} SKIP (artifacts exist)")
        return out

    missing_inputs = _missing(project, phase.needs)
    if missing_inputs:
        out.error = f"missing inputs: {', '.join(missing_inputs)}"
        _run_log(project, f"phase={phase.id} ERROR missing inputs: {', '.join(missing_inputs)}")
        return out

    spec = RunSpec(
        prompt=build_prompt(phase, project=project),
        workdir=project,
        max_turns=config["run.max_turns"],
        timeout_seconds=config["run.timeout_seconds"],
    )
    # Declare what the guard must see, instead of letting it infer from what
    # is **absent**.  With no env at all, `effective_scope` fell back to the
    # planning scope only as long as the host had no `AISEF_*` left over from
    # an earlier run: a stale `AISEF_STORY_ID` in the shell flips the guard
    # into story mode with an empty scope, and every planning write is denied
    # with "story has not declared write_scope".  The harness knows the answer
    # here; nothing should be left to the ambient environment.
    spec.env = {
        ENV_WRITE_SCOPE: ",".join(PLANNING_SCOPE),
        ENV_STORY_ID: "",
        ENV_PROJECT: str(project),
        ENV_WORKDIR: str(project),
        # What was already dirty before this phase opened. `diff-scope` reads
        # the whole tree, so an uncommitted file the operator left behind
        # otherwise blocks every tool call of the phase.
        ENV_BASELINE_DIRTY: ",".join(changed_files(str(project))[:200]),
    }

    # Retry on infra errors, and do **not** count as phase failure: a single
    # mid-run disconnect already spent $2.69 producing nothing — giving up
    # would force the next run to pay again from scratch.
    budget = config["run.max_retries"] + 1
    evidence = EvidenceStore(project / ARTIFACT_ROOT)
    while True:
        result = client.run(spec)
        out.ran = True
        out.cost_usd += result.cost_usd
        out.duration_ms += result.duration_ms
        # Planning cost is still cost. Recording only story costs would make
        # the acceptance report total miss the most expensive part of small
        # projects.
        evidence.agent_run(f"plan-{phase.id}", result, name=phase.id)
        if result.ok:
            break
        error = result.error or "run failed"
        budget -= 1
        # Same exit-status table as the story retry loop (ADR-005 V11 B).
        if budget <= 0 or exit_status_of(result) not in INFRA_STATUSES:
            _save_response(project, phase.id, result.text, result)
            # Artifacts on disk win: agent may have written the files before
            # failing (e.g. max_turns after writing but before JSON status).
            if not _missing(project, phase.artifacts):
                _run_log(project, f"phase={phase.id} RECOVER ${out.cost_usd:.2f} err={error}")
                break
            out.error = error
            _run_log(project, f"phase={phase.id} FAIL ${out.cost_usd:.2f} err={error}")
            return out
        # Say it in the log the operator watches. An SSE timeout after 22
        # minutes, retried silently, reads as 36 minutes of one motionless
        # `START` line — measured on `todo-e3`, 2026-09-09.
        from ..harness.runlog import one_line
        _run_log(project, f"phase={phase.id} RETRY (infra) after {result.duration_ms}ms "
                          f"err={one_line(error, 200)} · {budget} left")
        out.infra_retries += 1

    _save_response(project, phase.id, result.text, result)
    out.status = parse_headless_status(result.text)

    still_missing = _missing(project, phase.artifacts)
    if out.status.status == "blocked" and still_missing:
        out.error = f"BMAD blocked: {out.status.reason or 'no reason given'}"
        return out
    if still_missing:
        out.error = f"run completed but missing: {', '.join(still_missing)}"
        _run_log(project, f"phase={phase.id} FAIL ${out.cost_usd:.2f} missing={', '.join(still_missing)}")
        return out

    if phase.id == "prd":
        out.machine_gate = check_prd(parse_prd_file(project / ARTIFACT_ROOT / "prd.md"))
    elif phase.id == "ux":
        from ..control.experience import parse_experience_file

        out.machine_gate = check_experience(
            parse_experience_file(project / ARTIFACT_ROOT / "EXPERIENCE.md"))

    status_tag = out.status.status if out.status.parsed else "no-json"
    _run_log(project, f"phase={phase.id} OK ${out.cost_usd:.2f} status={status_tag}")
    return out


def _pass_gate(
    approvals: ApprovalStore,
    gate: Gate,
    outcome,
    auto_approve: frozenset[Gate],
) -> bool:
    """Whether this gate has passed. False means must stop for human approval.

    ``outcome`` only needs ``needs_human`` and ``machine_checks()`` — the
    mockup step reuses this same function.
    """
    if approvals.status(gate) is Status.APPROVED:
        return True
    if gate not in auto_approve:
        return False

    note = "auto-approved (--auto-approve)"
    if outcome.needs_human:
        # Don't block — user opted for auto-approve. But log it, since this
        # is the artifact to review first when something goes wrong.
        note += f"; {_why_human(outcome)}"
    approvals.auto_approve(gate, reason=note)
    rec = approvals.load(gate)
    rec.machine_checks = outcome.machine_checks()
    approvals.save(rec)
    return True


def _why_human(outcome) -> str:
    status = getattr(outcome, "status", None)
    if status is not None and getattr(status, "parsed", False):
        return f"BMAD reported {status.status} with {len(status.open_questions)} open questions"
    return "this step always needs human review"


def run_split(project: Path, config: Config) -> PhaseOutcome:
    """Split `epics.md` into one file per story. This step is **code**, not a
    model call: file splitting and parallel wave computation have deterministic
    answers, not judgment calls."""
    from .story_split import split

    out = PhaseOutcome(phase=SPLIT_PHASE)
    res = split(project / ARTIFACT_ROOT, config=config)
    out.ran = True
    out.split = res
    if res.error:
        out.error = res.error
    else:
        out.machine_gate = res.gate
    return out


MAX_SPLIT_RETRIES = 2


def run_pipeline(
    project: Path | str,
    client: ClientAdapter,
    *,
    config: Config | None = None,
    auto_approve: frozenset[Gate] = frozenset(),
    force: bool = False,
) -> PipelineResult:
    """Run phases up to the first unapproved gate, then stop.

    When the stories gate fails (oversized stories), the pipeline loops back
    to re-run epics with the gate memo feedback, up to ``MAX_SPLIT_RETRIES``
    times.  Without this, a single ``aisef plan --auto-approve=all`` would
    stop at the first oversized story and the user would have to manually
    re-run — a bad first experience for external users.
    """
    project = Path(project)
    cfg = config or Config.load(project)
    approvals = ApprovalStore(project / ARTIFACT_ROOT)
    result = PipelineResult()
    _run_log(project, "pipeline START")

    for phase in PHASES:
        outcome = run_phase(phase, project, client, config=cfg, force=force)
        result.outcomes.append(outcome)

        if not outcome.ok:
            result.failed_at = phase.id
            return result
        if phase.gate is None:
            continue
        if not _pass_gate(approvals, phase.gate, outcome, auto_approve):
            result.waiting_on = phase.gate
            return result

    # Story split runs every time: `epics.md` may have been edited during
    # human review, and the generated story files must follow.
    # When the machine gate fails (oversized stories), loop back: re-run
    # the epics phase with force + gate memo so the agent splits them.
    epics_phase = PHASE_BY_ID["epics"]
    for attempt in range(1 + MAX_SPLIT_RETRIES):
        outcome = run_split(project, cfg)
        result.outcomes.append(outcome)
        if outcome.ok:
            break
        if outcome.error or attempt >= MAX_SPLIT_RETRIES:
            result.failed_at = SPLIT_PHASE.id
            return result
        # Gate failed (oversized stories) — gate memo already written by
        # run_split.  Re-run epics with force=True (skips the "artifacts
        # exist" check).  Do NOT delete epics.md: the agent reads the
        # existing plan and only splits the flagged stories instead of
        # rewriting from scratch; and if the re-run fails, the old file
        # survives.
        epics_out = run_phase(epics_phase, project, client, config=cfg, force=True)
        result.outcomes.append(epics_out)
        if not epics_out.ok:
            result.failed_at = epics_phase.id
            return result
        if not _pass_gate(approvals, epics_phase.gate, epics_out, auto_approve):
            result.waiting_on = epics_phase.gate
            return result

    if not _pass_gate(approvals, Gate.STORIES, outcome, auto_approve):
        result.waiting_on = Gate.STORIES

    total = sum(o.cost_usd for o in result.outcomes)
    tag = "DONE" if result.complete else f"STOP({result.failed_at or result.waiting_on})"
    _run_log(project, f"pipeline {tag} ${total:.2f}")
    return result
