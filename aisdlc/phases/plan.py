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

from dataclasses import dataclass, field
from pathlib import Path

from ..clients.base import ClientAdapter, RunSpec
from ..config import Config
from ..control.approvals import GATE_ARTIFACTS, ApprovalStore, Gate, Status
from ..control.bmad_status import HeadlessStatus, parse_headless_status
from ..control.machine_gate import GateResult, check_prd
from ..control.normalize import parse_prd_file

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
        goal="Dựng ngữ cảnh dự án từ requirements: miền, người dùng, ràng buộc.",
    ),
    Phase(
        id="prd",
        skill="bmad-prd",
        artifacts=GATE_ARTIFACTS[Gate.PRD],
        gate=Gate.PRD,
        goal="Viết PRD: mỗi yêu cầu chức năng có mã và tiêu chí kiểm chứng được.",
    ),
    Phase(
        id="architecture",
        skill="bmad-architecture",
        artifacts=GATE_ARTIFACTS[Gate.ARCHITECTURE],
        gate=Gate.ARCHITECTURE,
        needs=("prd.md",),
        goal="Thiết kế kiến trúc, đánh số quyết định AR-x mà story phải tuân thủ.",
    ),
    Phase(
        id="ux",
        skill="bmad-ux",
        artifacts=GATE_ARTIFACTS[Gate.UX_SPEC],
        gate=Gate.UX_SPEC,
        needs=("prd.md",),
        goal="Đặc tả trải nghiệm: hệ thống thị giác, luồng người dùng, danh sách màn hình.",
    ),
    Phase(
        id="epics",
        skill="bmad-create-epics-and-stories",
        artifacts=GATE_ARTIFACTS[Gate.EPICS],
        gate=Gate.EPICS,
        needs=("prd.md", "architecture.md", "EXPERIENCE.md"),
        goal=(
            "Chia thành epic và story. Mỗi story ghi rõ phạm vi ghi file "
            "(write_scope), mã FR nó phủ, và tiêu chí chấp nhận."
        ),
    ),
)

PHASE_BY_ID = {p.id: p for p in PHASES}


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
        checks = {"bmad_status": self.status.status or "không đọc được"}
        if self.machine_gate:
            checks["cổng máy"] = "đạt" if self.machine_gate.passed else "không đạt"
            if self.machine_gate.warnings:
                checks["cảnh báo"] = "; ".join(self.machine_gate.warnings)
        return checks

    def summary(self) -> str:
        if self.skipped_reason:
            return f"{self.phase.id}: bỏ qua — {self.skipped_reason}"
        bits = [f"{self.phase.id}: {'ok' if self.ok else 'KHÔNG ĐẠT'}"]
        if self.status.parsed:
            bits.append(self.status.summary())
        if self.error:
            bits.append(f"lỗi: {self.error}")
        if self.machine_gate and not self.machine_gate.passed:
            bits.append(f"{len(self.machine_gate.errors)} lỗi cổng máy")
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
            lines.append(f"\n✗ dừng vì pha {self.failed_at} không đạt")
            if last and last.machine_gate:
                lines.append(last.machine_gate.summary())
        elif self.waiting_on:
            lines.append(f"\n⏸ chờ người duyệt: {self.waiting_on.value}")
            lines.append(f"   aisdlc review {self.waiting_on.value}")
        else:
            lines.append("\n✅ mọi pha đã xong và đã duyệt")
        if self.total_cost_usd:
            lines.append(f"chi phí: ${self.total_cost_usd:.2f}")
        return "\n".join(lines)


def build_prompt(phase: Phase) -> str:
    """Dựng prompt headless cho một pha.

    ``headless: true`` là cờ BMAD tự định nghĩa để bật chế độ không hỏi và
    trả JSON status ở cuối. Đường dẫn ra được chỉ định tường minh: BMAD tôn
    trọng đường dẫn được giao (kiểm chứng ở lượt chạy thật), còn tên mặc
    định của nó khác nhau giữa các skill.
    """
    inputs = ["docs/requirements.md (yêu cầu gốc)"]
    inputs += [f"{ARTIFACT_ROOT}/{n}" for n in phase.needs]
    outputs = ", ".join(f"{ARTIFACT_ROOT}/{n}" for n in phase.artifacts)

    return (
        "headless: true\n\n"
        f'Use the {phase.skill} skill. intent: "create".\n'
        f"doc_workspace: {ARTIFACT_ROOT}\n\n"
        f"Đầu vào: {', '.join(inputs)}.\n"
        f"Mục tiêu: {phase.goal}\n"
        f"Ghi ra đúng đường dẫn: {outputs}\n\n"
        "Không hỏi lại. Giả định nào phải tự suy thì ghi vào assumptions; "
        "chỗ nào cần người quyết thì ghi vào open_questions — đừng tự chọn "
        "rồi im lặng. Kết thúc bằng JSON status theo schema headless."
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
        out.skipped_reason = "artifact đã có"
        return out

    missing_inputs = _missing(project, phase.needs)
    if missing_inputs:
        out.error = f"thiếu đầu vào: {', '.join(missing_inputs)}"
        return out

    result = client.run(
        RunSpec(
            prompt=build_prompt(phase),
            workdir=project,
            max_turns=config["run.max_turns"],
            timeout_seconds=config["run.timeout_seconds"],
        )
    )
    out.ran = True
    out.cost_usd = result.cost_usd
    out.duration_ms = result.duration_ms

    if not result.ok:
        out.error = result.error or "lượt chạy thất bại"
        return out

    out.status = parse_headless_status(result.text)

    if out.status.status == "blocked":
        out.error = f"BMAD dừng: {out.status.reason or 'không nêu lý do'}"
        return out

    # Kiểm đĩa, không tin lời khai. Một lượt chạy có thể kết thúc "thành
    # công", khai đã sinh artifact, mà file không hề tồn tại.
    still_missing = _missing(project, phase.artifacts)
    if still_missing:
        out.error = f"chạy xong nhưng không thấy: {', '.join(still_missing)}"
        return out

    if phase.id == "prd":
        out.machine_gate = check_prd(parse_prd_file(project / ARTIFACT_ROOT / "prd.md"))

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

        if approvals.status(phase.gate) is Status.APPROVED:
            continue

        if phase.gate in auto_approve:
            note = "tự duyệt (--auto-approve)"
            if outcome.needs_human:
                # Không chặn — người dùng đã chọn tự duyệt. Nhưng ghi lại,
                # vì đây chính xác là artifact cần xem lại khi có sự cố.
                note += (
                    f"; BMAD khai {outcome.status.status} với "
                    f"{len(outcome.status.open_questions)} câu hỏi mở"
                )
            approvals.auto_approve(phase.gate, reason=note)
            approvals.save(_with_checks(approvals, phase.gate, outcome))
            continue

        result.waiting_on = phase.gate
        return result

    return result


def _with_checks(store: ApprovalStore, gate: Gate, outcome: PhaseOutcome):
    """Gắn kết quả kiểm máy vào bản ghi phê duyệt vừa tạo."""
    rec = store.load(gate)
    rec.machine_checks = outcome.machine_checks()
    return rec
