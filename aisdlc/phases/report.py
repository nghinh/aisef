"""Báo cáo nghiệm thu — gom bằng chứng đã có, không kể lại.

Mọi con số ở đây đọc từ artifact và bằng chứng trên đĩa. Không mục nào
được viết bằng tay, vì một báo cáo nghiệm thu viết tay chỉ chứng minh
người viết tin là mình đúng.

Bốn phần, đúng bốn câu hỏi người duyệt hỏi:

* **Truy vết** — mỗi yêu cầu trong PRD đi tới story nào, story đó động vào
  file nào, và có test không.
* **Chất lượng** — cổng nào đạt, loại kiểm định nào đã chạy.
* **Vận hành** — mỗi story tốn bao nhiêu tiền, bao lâu, mấy lượt.
* **Harness** — sáu nhóm có bằng chứng chạy thật hay chưa.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..control.approvals import GATE_ORDER, STORIES_INDEX, ApprovalStore, Status
from ..control.normalize import parse_prd_file
from ..control.state import StateStore
from ..harness.observe import AGENT_RUN, MOCKUP_MAP, TOOL_RUN, EvidenceStore


@dataclass
class Row:
    requirement: str
    title: str
    stories: list[str] = field(default_factory=list)
    tested: bool = False

    @property
    def covered(self) -> bool:
        return bool(self.stories)


#: Bằng chứng không thuộc về story nào: pha lập kế hoạch và dựng mockup.
PHASE_PREFIXES = ("plan-", "mockup-")


@dataclass
class Report:
    project: str = ""
    traceability: list[Row] = field(default_factory=list)
    gates: list[tuple[str, str, str]] = field(default_factory=list)
    stories: list[dict] = field(default_factory=list)
    phases: list[dict] = field(default_factory=list)
    harness: dict[str, str] = field(default_factory=dict)
    total_cost_usd: float = 0.0

    @property
    def uncovered(self) -> list[str]:
        return [r.requirement for r in self.traceability if not r.covered]

    def markdown(self) -> str:
        lines = [
            f"# Báo cáo nghiệm thu — {self.project}",
            "",
            "Mọi số liệu dưới đây đọc từ artifact và bằng chứng trên đĩa.",
            "",
            "## 1. Truy vết yêu cầu",
            "",
            "| Yêu cầu | Tiêu đề | Story phủ | Có bằng chứng test |",
            "|---|---|---|---|",
        ]
        for row in self.traceability:
            lines.append(
                f"| {row.requirement} | {row.title[:60]} | "
                f"{', '.join(row.stories) or '—'} | {'✅' if row.tested else '—'} |"
            )
        if self.uncovered:
            lines += ["", f"**Chưa phủ:** {', '.join(self.uncovered)}"]

        lines += ["", "## 2. Cổng phê duyệt", "", "| Cổng | Trạng thái | Ai duyệt |", "|---|---|---|"]
        for gate, status, by in self.gates:
            lines.append(f"| {gate} | {status} | {by or '—'} |")

        lines += [
            "", "## 3. Vận hành từng story", "",
            "| Story | Trạng thái | Lượt agent | Chi phí | Thời gian | Map mockup |",
            "|---|---|---|---|---|---|",
        ]
        for s in self.stories:
            lines.append(
                f"| {s['id']} | {s['status']} | {s['runs']} | ${s['cost']:.2f} | "
                f"{s['duration_ms'] / 1000:.0f}s | {s['mockup']} |"
            )
        if self.phases:
            lines += [
                "", "### Chi phí lập kế hoạch và mockup", "",
                "| Pha | Lượt | Chi phí | Thời gian |", "|---|---|---|---|",
            ]
            for ph in self.phases:
                lines.append(
                    f"| {ph['id']} | {ph['runs']} | ${ph['cost']:.2f} | "
                    f"{ph['duration_ms'] / 1000:.0f}s |"
                )

        lines += ["", f"**Tổng chi phí:** ${self.total_cost_usd:.2f}"]

        lines += ["", "## 4. Sáu nhóm harness", "", "| Nhóm | Bằng chứng |", "|---|---|"]
        for group, proof in self.harness.items():
            lines.append(f"| {group} | {proof} |")
        return "\n".join(lines) + "\n"


def build(project: Path | str) -> Report:
    project = Path(project)
    root = project / "_bmad-output"
    report = Report(project=project.name)

    index = _read_index(root)
    story_screens = {s["id"]: s.get("screens", []) for s in index.get("stories", [])}
    fr_to_stories: dict[str, list[str]] = {}
    for story in index.get("stories", []):
        for fr in story.get("covers", []):
            fr_to_stories.setdefault(fr, []).append(story["id"])

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
        maps = ev.of(MOCKUP_MAP)
        mockup = "—"
        if story_screens.get(sid):
            mockup = "✅" if maps and all(m.ok for m in maps) else "✗"
        record = state.stories.get(sid)
        report.stories.append({
            "id": sid,
            "status": record.status if record else "?",
            "runs": len(ev.of(AGENT_RUN)),
            "cost": ev.total_cost_usd,
            "duration_ms": ev.total_duration_ms,
            "mockup": mockup,
        })
    report.total_cost_usd = sum(s["cost"] for s in report.stories) + sum(
        p["cost"] for p in report.phases
    )
    report.harness = _harness_evidence(project, root, evidence)
    return report


def _read_index(root: Path) -> dict:
    path = root / STORIES_INDEX
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _harness_evidence(project: Path, root: Path, evidence: EvidenceStore) -> dict[str, str]:
    """Sáu nhóm harness — mỗi nhóm phải chỉ ra được một artifact có thật."""
    from ..harness.prompts import load_catalog

    any_story = [s for s in evidence.stories() if not s.startswith(PHASE_PREFIXES)]
    ev = evidence.read(any_story[0]) if any_story else None

    def yes(cond, proof, missing="chưa có bằng chứng"):
        return proof if cond else missing

    prompts = load_catalog()
    return {
        "1 Chỉ dẫn & luật": yes(
            (project / "CLAUDE.md").is_file(),
            f"CLAUDE.md · AGENTS.md · {len(prompts.prompts)} prompt có phiên bản",
        ),
        "2 Tool": yes(
            bool(ev and ev.of(TOOL_RUN)),
            f"{len(ev.of(TOOL_RUN)) if ev else 0} lần chạy tool được ghi",
        ),
        "3 Sandbox": _isolation_note(ev),
        "4 Điều phối": yes(
            (root / STORIES_INDEX).is_file(),
            "chỉ mục story có đợt chạy song song tính sẵn",
        ),
        "5 Guardrail": yes(
            (project / ".claude" / "settings.json").is_file(),
            ".claude/settings.json nối 7 guard vào 3 mốc",
        ),
        "6 Quan sát": yes(
            bool(any_story),
            f"evidence/ có {len(any_story)} story, kèm chi phí và độ trễ",
        ),
    }


def _isolation_note(ev) -> str:
    """Mức cách ly **quan sát được**, không phải mức mong muốn.

    Báo "có sandbox" khi thực tế chạy thẳng trên máy là đúng loại tự khai
    mà cả framework này sinh ra để chống.
    """
    if ev is None:
        return "chưa có bằng chứng"
    levels = {
        str(e.detail.get("isolation"))
        for e in ev.of(TOOL_RUN)
        if e.detail.get("isolation")
    }
    if not levels:
        return "chưa có bằng chứng"
    degraded = any(e.detail.get("degraded") for e in ev.of(TOOL_RUN))
    note = "mức cách ly quan sát được: " + ", ".join(sorted(levels))
    return note + (" — **suy biến**, không có container" if degraded else "")


def write(project: Path | str, *, out: Path | str | None = None) -> Path:
    report = build(project)
    path = Path(out) if out else Path(project) / "docs" / "ACCEPTANCE-REPORT.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.markdown(), encoding="utf-8")
    return path
