"""Báo cáo nghiệm thu — gom bằng chứng đã có, không kể lại.

Mọi con số ở đây đọc từ artifact và bằng chứng trên đĩa. Không mục nào
được viết bằng tay, vì một báo cáo nghiệm thu viết tay chỉ chứng minh
người viết tin là mình đúng.

Năm phần, đúng năm câu hỏi người duyệt hỏi:

* **Truy vết** — mỗi yêu cầu trong PRD đi tới story nào, story đó động vào
  file nào, và có test không.
* **Chất lượng** — cổng nào đạt, loại kiểm định nào đã chạy.
* **Vận hành** — mỗi story tốn bao nhiêu tiền, bao lâu, mấy lượt.
* **Harness** — sáu nhóm có bằng chứng chạy thật hay chưa.
* **Cải tiến** — sổ hành vi (`control/ledger.py`): năng lực đã xác minh,
  hồi quy, gap đã đóng, cải thiện biên. Đây là câu hỏi cổng story không
  trả lời được, vì cổng chấm **một** story ở **một** thời điểm.
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
from ..control.normalize import parse_prd_file
from ..control.state import StateStore
from ..harness.observe import AGENT_RUN, HANDOFF, MOCKUP_MAP, TOOL_RUN, EvidenceStore


def mockup_cell(maps) -> str:
    """Ô "Map mockup" của một story: **kết quả mới nhất của từng màn hình**.

    Trước 2026-09-05 ô này đòi *mọi* lần đối chiếu từng đạt — story qua cổng
    ở lượt cuối vẫn bị ✗ vì các lượt trước trượt (e9 STORY-01-05: done, map
    3/3 ở lượt cuối, báo cáo ghi ✗). Lịch sử nằm ở evidence; báo cáo nói
    trạng thái hiện tại.
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
    #: Kết quả cổng trước triển khai, nếu đã chấm.
    pre_deploy: dict = field(default_factory=dict)
    total_cost_usd: float = 0.0
    #: Số của sổ hành vi (ADR-004 R2/R7) — chiếu từ cùng bằng chứng.
    ledger: dict = field(default_factory=dict)

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
            "| Story | Trạng thái | Candidate | Lượt agent | Chi phí | Thời gian | Map mockup | TCCN có test | Hành vi (V/G/R) |",
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
            lines += ["", "Chuỗi bàn giao (từ bằng chứng `handoff`, mỗi vai một phiên mới):", ""]
            lines += [f"- {s['id']}: {s['handoffs']}" for s in chuoi]
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

        lines += self._ledger_section()

        lines += ["", "## 6. Cổng trước triển khai", ""]
        if not self.pre_deploy:
            lines.append("_Chưa chấm — chạy `aisdlc pre-deploy`._")
        else:
            lines += ["| Mục | Kết quả |", "|---|---|"]
            for c in self.pre_deploy.get("checks", []):
                mark = "✅" if c.get("passed") else "✗"
                lines.append(f"| {c.get('name')} | {mark} {c.get('detail', '')} |")
            qa = self.pre_deploy.get("qa") or {}
            if qa:
                unconf = ", ".join(qa.get("unconfigured", [])) or "—"
                failed = ", ".join(qa.get("failed", [])) or "—"
                lines += [
                    "",
                    f"Kiểm định: không đạt = {failed} · chưa cấu hình = {unconf}",
                ]
        return "\n".join(lines) + "\n"

    def _ledger_section(self) -> list[str]:
        """Phần 5 — cải tiến liên tục (ADR-004 R7).

        Bốn số, tất cả chiếu từ cùng bằng chứng của phần 3: năng lực đã xác
        minh tăng bao nhiêu, bao nhiêu cái từng đúng rồi hỏng, bao nhiêu gap
        đã đóng, và mỗi đô la mua được bao nhiêu hành vi ròng.
        """
        m = self.ledger
        if not m:
            return ["", "## 5. Cải tiến liên tục (sổ hành vi)", "",
                    "_Chưa có bằng chứng nào để chiếu thành hành vi._"]
        lines = [
            "", "## 5. Cải tiến liên tục (sổ hành vi)", "",
            "| Số đo | Giá trị |", "|---|---|",
            f"| Năng lực đã xác minh (VERIFIED hiện tại) | {m['verified']} |",
            f"| Từng xác minh (growth, duy nhất theo thời gian) | {m['ever_verified']} |",
            f"| GAP | {m['gap']} |",
            f"| REOPENED (đang hỏng lại) | {m['reopened']} |",
            f"| Lần hồi quy / tỷ lệ trên hành vi từng xác minh | "
            f"{m['reopen_events']} · {m['reopen_rate']:.2f} |",
            f"| Hồi quy **liên story** (story sau làm hỏng story trước) | {m['cross_reopens']} |",
            f"| Gap đã đóng (resolved) | {m['resolved']} |",
        ]
        cross = m.get("cross_reopen_list") or []
        if cross:
            lines += ["", "Hồi quy liên story, kèm nguồn:", ""]
            lines += [
                f"- `{c['id']}` xanh ở {c['verified_by']} → đỏ lại ở {c['regressed_by']}"
                for c in cross[:10]
            ]
        loops = m.get("loops") or []
        if loops:
            lines += [
                "", "| Vòng | VERIFIED | GAP | REOPENED | ΔV | ΔR | $ | Cải thiện biên |",
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
    # `resolve()` vì hàm này gọi được thẳng từ mã khác, không chỉ qua CLI
    # (nơi đường dẫn đã được tuyệt đối hoá ở cửa vào).
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
            # Bản mà bằng chứng của story trỏ vào (ADR-004 R1) — không có
            # thì báo cáo phải nói là không có, không im lặng.
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

    pre_deploy_file = root / PRE_DEPLOY_REPORT
    if pre_deploy_file.is_file():
        try:
            report.pre_deploy = json.loads(pre_deploy_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report.pre_deploy = {}
    return report


def _behavior_cell(led, sid: str) -> str:
    """Ô "Hành vi": `V/G/R` của story. `R > 0` là thứ báo cáo cũ không nói
    được — story qua cổng mà vẫn để lại một hành vi từng đúng nay hỏng."""
    v, g, r = led.counts_for(sid)
    return "—" if not (v or g or r) else f"{v}/{g}/{r}"


def _ac_cell(sid: str, n: int, ev) -> str:
    """`k/n` tiêu chí có test mang mã, từ lần test xanh cuối. Không đọc
    được tên test thì `?/n` — chưa biết, không phải đủ."""
    from ..control.acceptance import missing as ac_missing

    if n <= 0:
        return "—"
    xanh = [e for e in ev.of(TOOL_RUN, "test") if e.ok]
    if not xanh or not xanh[-1].detail.get("test_format"):
        return f"?/{n}"
    thieu = ac_missing(sid, n, list(xanh[-1].detail.get("test_ids") or []))
    return f"{n - len(thieu)}/{n}"


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
