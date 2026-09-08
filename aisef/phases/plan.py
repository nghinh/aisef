"""Chuỗi pha lập kế hoạch — chạy skill BMAD tuần tự, dừng ở mỗi cổng.

Mỗi pha là một skill BMAD chạy ở chế độ headless. Sau mỗi pha:

1. đọc JSON status BMAD trả về (``complete`` / ``partial`` / ``blocked``);
2. đối chiếu **file trên đĩa** với những gì nó khai đã sinh ra;
3. chạy **cổng máy** — kiểm những gì kiểm được bằng code;
4. dừng ở **cổng người**, trừ khi cổng đó nằm trong ``--auto-approve``.

``run_pipeline`` **không** chạy hết rồi mới báo: nó dừng ngay ở cổng đầu
tiên chưa duyệt và trả về. Gọi lại sau khi người duyệt thì đi tiếp từ đó —
cùng một cơ chế cho chạy nền, CI lẫn phiên chat, và không cần tiến trình
nào sống chờ (quyết định Đ2).

Pha đã có đủ artifact thì **bỏ qua**, nên chạy lại không trả tiền làm lại
việc đã xong.

**Không có pha `bmad-sprint-planning`.** Thứ tự thực hiện story là thứ máy
tính được chắc chắn từ phụ thuộc và ``write_scope`` (``control/scheduler``),
nên giao nó cho model là vi phạm nguyên tắc gốc: cần đảm bảo thì viết code.
BMAD dừng ở chỗ sinh ra epic và story; xếp lịch là việc của framework.
"""

from __future__ import annotations

import json

from dataclasses import dataclass, field
from pathlib import Path

from ..clients.base import ClientAdapter, RunSpec
from ..config import Config
from ..control.approvals import GATE_ARTIFACTS, ApprovalStore, Gate, Status
from ..control.bmad_status import HeadlessStatus, parse_headless_status
from ..control.machine_gate import GateResult, check_prd
from ..harness.observe import EvidenceStore
from ..control.normalize import parse_prd_file
from ..clients.stream import INFRA_STATUSES, exit_status_of

ARTIFACT_ROOT = "_bmad-output"


@dataclass(frozen=True)
class Phase:
    """Một pha lập kế hoạch: một skill BMAD, một artifact, một cổng."""

    id: str
    skill: str
    #: File pha này phải sinh ra. Với pha có cổng, phải trùng
    #: ``GATE_ARTIFACTS[gate]`` — cổng băm đúng những file này.
    artifacts: tuple[str, ...]
    gate: Gate | None
    #: Artifact phải có sẵn trước khi chạy.
    needs: tuple[str, ...] = ()
    goal: str = ""


#: Thứ tự pha. Tuần tự vì mỗi pha ăn output của pha trước.
#:
#: Tên file là tên BMAD **thật sự** ghi ra khi được chỉ định đường dẫn —
#: kiểm chứng bằng lượt chạy thật (xem `tests/fixtures/bmad/`). Riêng pha UX
#: giữ nguyên hai file của BMAD (`DESIGN.md` hệ thống thị giác,
#: `EXPERIENCE.md` luồng và màn hình): gộp lại thành một `ux-spec.md` sẽ phá
#: intent `update`/`validate` của chính skill đó, vì nó tìm hai file này.
PHASES: tuple[Phase, ...] = (
    Phase(
        id="project-context",
        skill="bmad-project-context",
        artifacts=("project-context.md",),
        gate=None,  # ngữ cảnh nền, không phải quyết định sản phẩm
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
        goal="Design architecture, number decisions AR-x that stories must comply with.",
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

#: Bước tách story — do framework tự làm, không gọi model.
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
    #: Số lần phải chạy lại vì lỗi hạ tầng (mạng, quá giờ) — không phải lỗi
    #: chất lượng, nhưng vẫn tốn tiền nên phải hiện ra.
    infra_retries: int = 0
    #: Chỉ có ở bước tách story.
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
        """BMAD tự khai artifact chưa đứng được một mình."""
        return self.status.needs_human

    def machine_checks(self) -> dict[str, str]:
        """Kết quả kiểm máy, ghi kèm bản ghi phê duyệt để về sau truy được."""
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
    #: Cổng khiến pipeline dừng chờ người. None nghĩa là đã chạy hết.
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
    """Ngữ cảnh brownfield cho prompt — baseline + hướng dẫn delta."""
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
    """Dựng prompt headless cho một pha.

    ``headless: true`` là cờ BMAD tự định nghĩa để bật chế độ không hỏi và
    trả JSON status ở cuối. Đường dẫn ra được chỉ định tường minh: BMAD tôn
    trọng đường dẫn được giao (kiểm chứng ở lượt chạy thật), còn tên mặc
    định của nó khác nhau giữa các skill.
    """
    brownfield = _is_brownfield(project)
    intent = "update" if brownfield and not _missing(project, phase.artifacts) else "create"

    inputs = ["docs/requirements.md (original requirements)"]
    if brownfield:
        inputs.insert(0, f"{ARTIFACT_ROOT}/baseline.md (brownfield baseline)")
    inputs += [f"{ARTIFACT_ROOT}/{n}" for n in phase.needs]
    outputs = ", ".join(f"{ARTIFACT_ROOT}/{n}" for n in phase.artifacts)
    memo = _stories_gate_memo(project) if phase.gate is Gate.EPICS else ""
    bf_ctx = _brownfield_context(project) if brownfield and project else ""

    return (
        "headless: true\n\n"
        f'Use the {phase.skill} skill. intent: "{intent}".\n'
        f"doc_workspace: {ARTIFACT_ROOT}\n\n"
        f"Inputs: {', '.join(inputs)}.\n"
        f"Goal: {phase.goal}\n"
        f"Write to exact paths: {outputs}\n\n"
        "Do not ask questions. Any assumptions you must infer go in assumptions; "
        "anything requiring human decision goes in open_questions — do not choose "
        "silently. End with a JSON status following the headless schema."
        + memo + bf_ctx
    )


def _stories_gate_memo(project: Path | None) -> str:
    """Cổng stories lần trước nói gì — để agent chẻ story cho đúng (P2-12)."""
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
    """Chạy một pha. Bỏ qua nếu đã có đủ artifact và không bị ép chạy lại."""
    out = PhaseOutcome(phase=phase)

    if not _missing(project, phase.artifacts) and not force:
        out.skipped_reason = "artifacts already exist"
        return out

    missing_inputs = _missing(project, phase.needs)
    if missing_inputs:
        out.error = f"missing inputs: {', '.join(missing_inputs)}"
        return out

    spec = RunSpec(
        prompt=build_prompt(phase, project=project),
        workdir=project,
        max_turns=config["run.max_turns"],
        timeout_seconds=config["run.timeout_seconds"],
    )

    # Lỗi hạ tầng thì thử lại, và **không** tính là pha thất bại: một lần
    # đứt kết nối giữa chừng đã tiêu $2.69 mà không sinh ra gì, bỏ luôn thì
    # lần chạy sau phải trả lại từ đầu.
    budget = config["run.max_retries"] + 1
    evidence = EvidenceStore(project / ARTIFACT_ROOT)
    while True:
        result = client.run(spec)
        out.ran = True
        out.cost_usd += result.cost_usd
        out.duration_ms += result.duration_ms
        # Chi phí lập kế hoạch cũng là chi phí. Chỉ ghi chi phí story thì
        # tổng trong báo cáo nghiệm thu thiếu mất phần đắt nhất của những
        # dự án nhỏ.
        evidence.agent_run(f"plan-{phase.id}", result, name=phase.id)
        if result.ok:
            break
        error = result.error or "run failed"
        budget -= 1
        # Cùng bảng kết cục với vòng thử lại story (ADR-005 V11 B).
        if budget <= 0 or exit_status_of(result) not in INFRA_STATUSES:
            out.error = error
            return out
        out.infra_retries += 1

    out.status = parse_headless_status(result.text)

    if out.status.status == "blocked":
        out.error = f"BMAD blocked: {out.status.reason or 'no reason given'}"
        return out

    # Kiểm đĩa, không tin lời khai. Một lượt chạy có thể kết thúc "thành
    # công", khai đã sinh artifact, mà file không hề tồn tại.
    still_missing = _missing(project, phase.artifacts)
    if still_missing:
        out.error = f"run completed but missing: {', '.join(still_missing)}"
        return out

    if phase.id == "prd":
        out.machine_gate = check_prd(parse_prd_file(project / ARTIFACT_ROOT / "prd.md"))

    return out


def _pass_gate(
    approvals: ApprovalStore,
    gate: Gate,
    outcome,
    auto_approve: frozenset[Gate],
) -> bool:
    """Cổng này đã thông chưa. False nghĩa là phải dừng chờ người.

    ``outcome`` chỉ cần có ``needs_human`` và ``machine_checks()`` — bước
    mockup dùng lại đúng hàm này.
    """
    if approvals.status(gate) is Status.APPROVED:
        return True
    if gate not in auto_approve:
        return False

    note = "auto-approved (--auto-approve)"
    if outcome.needs_human:
        # Không chặn — người dùng đã chọn tự duyệt. Nhưng ghi lại, vì đây
        # chính là artifact cần xem lại đầu tiên khi có sự cố.
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
    """Tách `epics.md` thành mỗi story một file. Bước này là **code**, không
    phải model: chia file và tính sóng chạy song song là việc có đáp án
    đúng, không phải việc cần phán đoán."""
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


def run_pipeline(
    project: Path | str,
    client: ClientAdapter,
    *,
    config: Config | None = None,
    auto_approve: frozenset[Gate] = frozenset(),
    force: bool = False,
) -> PipelineResult:
    """Chạy các pha tới cổng đầu tiên chưa duyệt, rồi dừng."""
    project = Path(project)
    cfg = config or Config.load(project)
    approvals = ApprovalStore(project / ARTIFACT_ROOT)
    result = PipelineResult()

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

    # Tách story chạy mỗi lần: `epics.md` có thể đã được người duyệt sửa,
    # và file story sinh ra từ nó thì phải theo.
    outcome = run_split(project, cfg)
    result.outcomes.append(outcome)
    if not outcome.ok:
        result.failed_at = SPLIT_PHASE.id
        return result
    if not _pass_gate(approvals, Gate.STORIES, outcome, auto_approve):
        result.waiting_on = Gate.STORIES

    return result
