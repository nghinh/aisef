"""Vòng cải tiến epic theo bằng chứng (ADR-004 R3): `aisdlc improve --epic E`.

HoH chứng minh vòng "đo gap → sửa → đo lại" tạo gain, nhưng chạy T = 70
vòng không có điều kiện dừng. Ở đây vòng **ghép** từ thứ có sẵn — không có
pha mới, không sửa `run`/`implement` một dòng — và dừng bằng code:

    qa.run_suite (bằng chứng cấp dự án ở HEAD) → ledger.build() → GAP/REOPENED
    thuộc epic → **một** story sửa sinh bằng code → run.run_epic (phiên mới,
    worktree, cổng, reviewer ≠ developer) → QA lại → ledger.snapshot("loop-n")
    → vòng sau.

Năm điều kiện dừng, cái nào cũng đọc từ đĩa (sổ hành vi, bằng chứng), không
từ bộ nhớ tiến trình — nên chạy lại tiếp đúng chỗ dở, không daemon:

1. không còn GAP/REOPENED thuộc epic;
2. đủ `improve.max_loops` (đếm theo epic từ `loops[]`);
3. cải thiện biên Δverified − Δreopened ≤ 0 trong `improve.flat_loops` vòng liền;
4. tổng chi phí các vòng của epic vượt `improve.cost_cap_usd`;
5. story sửa bế tắc kế hoạch (`[bế tắc]`, người rà soát đã kiểm chứng) → trả người.

Mỗi vòng **một** story sửa = **một** hành vi: B1 đòi chi phí ≤ 1 story mỗi
vòng, và một hành vi là đơn vị nhỏ nhất cổng chấm được. REOPENED đi trước
GAP — hồi quy là con số HoH đo. Story sửa sinh **tất định** từ gap; agent
chỉ vào ở R10 sau khi đo được gain.

Cổng người `improve` trước mỗi vòng ≥ 2 (trừ `--auto`): pipeline dừng ở
cổng, người đọc `LOOP-REPORT-<n>.md`, `aisdlc approve improve`, chạy lại —
cùng cơ chế với tám cổng kia, phê duyệt gắn băm báo cáo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..clients.base import ClientAdapter
from ..config import Config
from ..control import complexity
from ..control import ledger as ledger_mod
from ..control.approvals import ApprovalStore, Gate, Status
from ..control.change import read_index, register_story
from ..control.journal import reconcile_all
from ..control.ledger import GAP, REOPENED, Behavior, Ledger
from ..control.normalize import Story, verification_paths
from ..control.preflight import verification_contract
from ..control.state import StateStore, StoryStatus
from ..control.worktree import GitError, WorktreeManager
from ..harness.observe import EvidenceStore
from .implement import plan_defects
from .plan import ARTIFACT_ROOT
from .qa import KINDS as QA_KINDS, run_suite
from .run import RunReport, load_plan, run_epic

#: Mốc trước vòng đầu của một lần gọi. Ghi lại khi sổ đã đổi kể từ mốc
#: cuối (story thường chạy giữa hai lần `improve`) hoặc mốc cuối thuộc
#: epic khác, để Δ của vòng kế đo đúng phần vòng ấy làm ra trên epic ấy.
BASELINE = "loop-0"
LOOP_REPORT = "LOOP-REPORT-{n}.md"
STORY_PREFIX = "STORY-RP-"


def repair_epic(epic_id: str) -> str:
    """`EPIC-01` → `EPIC-RP-01`."""
    return "EPIC-RP-" + epic_id.removeprefix("EPIC-")


@dataclass
class Loop:
    """Một vòng: đủ để viết báo cáo và để người quyết tiếp hay dừng."""

    n: int                      # nhãn `loop-<n>` trong sổ — toàn cục, duy nhất
    epic_loop: int              # vòng thứ mấy của epic này
    story_id: str
    behavior: str
    before: dict                # summary + danh sách gap thuộc epic, trước vòng
    after: dict = field(default_factory=dict)
    cost_usd: float = 0.0
    done: bool = False
    outcome_text: str = ""
    stuck: str = ""             # lời người rà soát khi bế tắc kế hoạch
    d_verified: int = 0
    d_reopened: int = 0
    report_path: Path | None = None

    @property
    def improvement(self) -> int:
        return self.d_verified - self.d_reopened

    def line(self) -> str:
        return (
            f"loop-{self.n} · {self.story_id} sửa {self.behavior} · "
            f"{'XONG' if self.done else 'CHƯA XONG'} · ${self.cost_usd:.2f} · "
            f"V{self.d_verified:+d} R{self.d_reopened:+d} · gap thuộc epic "
            f"{len(self.before['gaps'])}→{len(self.after.get('gaps', []))}"
        )


@dataclass
class ImproveReport:
    epic: str
    loops: list[Loop] = field(default_factory=list)
    stopped: str = ""
    gaps_left: list[str] = field(default_factory=list)
    error: str = ""
    reconciled: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.error and not self.gaps_left

    @property
    def cost_usd(self) -> float:
        return sum(lo.cost_usd for lo in self.loops)

    def summary(self) -> str:
        if self.error:
            return f"cải tiến {self.epic}: ✗ {self.error}"
        lines = [f"cải tiến {self.epic}: {len(self.loops)} vòng lần này, ${self.cost_usd:.2f}"]
        lines += [f"↺ {r.line()}" for r in self.reconciled]
        lines += [f"  {lo.line()}" for lo in self.loops]
        for lo in self.loops:
            if lo.report_path:
                lines.append(f"  báo cáo: {lo.report_path}")
        lines.append(f"⏸ dừng: {self.stopped}")
        if self.gaps_left:
            lines.append(f"  còn {len(self.gaps_left)} gap thuộc epic: "
                         + ", ".join(self.gaps_left[:5]))
        return "\n".join(lines)


# ------------------------------------------------------------------ gap


def epic_counts(led: Ledger, epic_id: str) -> dict:
    """VERIFIED/GAP/REOPENED của **hành vi thuộc epic** — thứ vòng nhắm tới.

    Δ toàn cục (R7) không dùng làm điều kiện dừng: chính story sửa đẻ thêm
    hành vi (`AC-STORY-RP-nn-1`, `qa:fake-tests`) và làm Δ dương dù không
    đóng gap nào — đo trên client giả: vòng không sửa gì vẫn V+1.
    """
    out = {"epic_verified": 0, "epic_gap": 0, "epic_reopened": 0}
    for b in led.behaviors.values():
        if led.epic_of(b.story) == epic_id:
            out[f"epic_{b.status}"] = out.get(f"epic_{b.status}", 0) + 1
    return out


def epic_gaps(led: Ledger, epic_id: str) -> list[Behavior]:
    """GAP/REOPENED mà story sở hữu thuộc epic — REOPENED trước, rồi theo id.

    Story sở hữu là story trong chỉ mục, không phải story sửa: hành vi của
    `EPIC-RP-*` (tiêu chí của chính story sửa) không quay lại làm gap mới.
    """
    out = [
        b for b in led.behaviors.values()
        if b.status in (GAP, REOPENED) and led.epic_of(b.story) == epic_id
    ]
    return sorted(out, key=lambda b: (b.status != REOPENED, b.id))


# ------------------------------------------------------------------ story sửa


def _owner(root: Path, story_id: str) -> Story:
    raw = next((s for s in read_index(root).get("stories", []) if s.get("id") == story_id), {})
    return Story(
        id=story_id, epic_id=str(raw.get("epic_id") or ""), title=str(raw.get("title") or ""),
        acceptance_criteria=list(raw.get("acceptance_criteria") or []),
        covers=list(raw.get("covers") or []), write_scope=list(raw.get("write_scope") or []),
        screens=list(raw.get("screens") or []),
        verification_contract=list(raw.get("verification_contract") or []),
    )


def _describe(b: Behavior, owner: Story) -> str:
    """Tiêu chí chấp nhận của story sửa = chính hành vi ấy, giữ nguyên id
    để sổ khớp lại. Không backtick đường dẫn ở đây: tiền kiểm đọc câu này
    và sẽ đòi quyền ghi cho tệp nó thấy cạnh động từ tạo/sửa."""
    if b.kind == "ac":
        i = int(b.id.rsplit("-", 1)[1])
        text = owner.acceptance_criteria[i - 1] if 0 < i <= len(owner.acceptance_criteria) \
            else f"tiêu chí {i} của {owner.id}"
        return f"{b.id} xanh lại: {text}"
    if b.kind in ("fr", "nfr"):
        return f"{b.id} xanh: mọi tiêu chí của {owner.id} phủ yêu cầu này xanh"
    if b.kind == "qa":
        return f"{b.id} xanh: aisdlc qa --only {b.id.split(':', 1)[1]} đạt ở HEAD"
    return f"{b.id} xanh: màn hình {b.id.split(':', 1)[1]} khớp hợp đồng thị giác"


def _contract(b: Behavior, owner: Story) -> tuple[list[str], list[str]]:
    """Hợp đồng kiểm định + màn hình của story sửa, từ nguồn của hành vi."""
    kinds = verification_contract(owner)
    if b.kind == "qa":
        kind = b.id.split(":", 1)[1]
        if kind in QA_KINDS and kind not in kinds:
            kinds.append(kind)
    screens = [b.id.split(":", 1)[1]] if b.kind == "mockup" else []
    return kinds, screens


def _source_line(b: Behavior) -> str:
    src = b.source or {}
    parts = [f"{k}: `{v}`" for k, v in src.items() if k != "tests" and v]
    return "; ".join(parts) or "(sổ không ghi nguồn)"


def _body(b: Behavior, owner: Story, story: Story, preservation: list[str], loop: int) -> str:
    ac = f"AC-{story.id}-1"
    out = [
        "",
        "## Sửa hành vi (vòng cải tiến `loop-%d`, ADR-004 R3)" % loop,
        "",
        f"- Hành vi: `{b.id}` — trạng thái **{b.status}** trong sổ, thuộc {owner.id}"
        + (f" (hồi quy do {b.regressed_by})" if b.regressed_by else ""),
        f"- Nguồn: {_source_line(b)}",
        f"- Lịch sử: `aisdlc evidence {b.id}`",
        "",
        f"Test chứng minh hành vi này phải mang **cả** mã của story này "
        f"(`{ac}`) **và** mã gốc `{b.id}`: sổ hành vi khớp lại theo mã gốc, "
        f"cổng story chấm theo mã mới. Sửa **dự án**, không sửa harness hay tiêu chí.",
        "",
    ]
    if preservation:
        out += [
            "## Bảo toàn",
            "",
            "Hành vi đã VERIFIED của story khác nằm trong phạm vi ghi — sửa xong "
            "chúng vẫn phải xanh (cổng bảo toàn, ADR-004 R4):",
            "",
            *[f"- `{bid}`" for bid in preservation],
            "",
        ]
    return "\n".join(out)


def _pick_id(root: Path, state: StateStore, behavior_id: str) -> str:
    """Story sửa chưa xong của chính hành vi này thì chạy lại nó; không thì
    id mới. Không tạo bản sao cho cùng một gap mỗi vòng."""
    stories = read_index(root).get("stories", [])
    recs = state.load().stories
    for s in stories:
        sid = str(s.get("id") or "")
        if s.get("repair_of") == behavior_id and sid in recs \
                and recs[sid].state is not StoryStatus.DONE:
            return sid
    n = 1 + sum(1 for s in stories if str(s.get("id", "")).startswith(STORY_PREFIX))
    return f"{STORY_PREFIX}{n:02d}"


def repair_story(
    led: Ledger,
    b: Behavior,
    *,
    epic_id: str,
    root: Path,
    project: Path,
    config: Config,
    state: StateStore,
    loop: int,
) -> Path:
    """Sinh **tất định** một story sửa cho một hành vi và ghi vào chỉ mục.

    `write_scope` = phạm vi story sở hữu + tệp test mà hợp đồng kiểm định
    đòi (lỗi 21: đòi test rồi cấm viết test); `depends_on` rỗng; `covers`
    của story sở hữu để yêu cầu vẫn truy vết được. Story sửa đi qua đúng
    các tiền kiểm của story thường (cỡ R5, năng lực, phạm vi) ở `run_epic`.
    """
    owner = _owner(root, b.story)
    kinds, screens = _contract(b, owner)
    scope = list(owner.write_scope)
    for p in verification_paths(owner, project, config):
        if p not in scope:
            scope.append(p)
    sid = _pick_id(root, state, b.id)
    story = Story(
        id=sid, epic_id=repair_epic(epic_id),
        title=f"Sửa {b.id} ({b.status}) của {owner.id}"[:80],
        acceptance_criteria=[_describe(b, owner)],
        covers=list(owner.covers), write_scope=scope, depends_on=[],
        screens=screens, verification_contract=kinds,
    )
    preservation = complexity.verified_touched(
        story, led.as_dict(), complexity.read_scopes(project))
    return register_story(
        root, story,
        epic_title=f"Sửa hành vi theo sổ — {epic_id}",
        extra={"repair_of": b.id, "loop": f"loop-{loop}", "preservation": preservation,
               "source": dict(b.source or {})},
        body=_body(b, owner, story, preservation, loop),
        wave=[sid],   # một story mỗi vòng: story sửa cũ trượt không được chạy ké
    )


# ------------------------------------------------------------------ vòng


def _counts(rec: dict) -> tuple[int, int, int]:
    return int(rec.get("verified", 0)), int(rec.get("gap", 0)), int(rec.get("reopened", 0))


def _epic_rows(led: Ledger, epic_id: str) -> list[dict]:
    """Các vòng đã chạy của epic, kèm Δ hành vi thuộc epic so với mốc liền
    trước — mốc ấy luôn cùng epic, vì đổi epic là có mốc xuất phát mới."""
    out, prev = [], None
    for lo in led.loops:
        if lo.get("epic") == epic_id and lo.get("n") != BASELINE and prev is not None:
            out.append({
                **lo,
                "d_verified": int(lo.get("epic_verified", 0)) - int(prev.get("epic_verified", 0)),
                "d_reopened": int(lo.get("epic_reopened", 0)) - int(prev.get("epic_reopened", 0)),
            })
        prev = lo
    return out


def stop_reason(
    led: Ledger,
    epic_id: str,
    gaps: list[Behavior],
    last: Loop | None,
    *,
    max_loops: int,
    flat_loops: int,
    cost_cap: float,
    auto: bool,
    approvals: ApprovalStore,
) -> str:
    """Lý do dừng trước khi mở vòng kế; rỗng = chạy tiếp. Mọi số đọc từ sổ."""
    if not gaps:
        return "không còn GAP/REOPENED thuộc epic"
    if last is not None and last.stuck:
        return f"bế tắc kế hoạch ở {last.story_id} — trả người: {last.stuck}"
    rows = _epic_rows(led, epic_id)
    if len(rows) >= max_loops:
        return f"đủ improve.max_loops = {max_loops} ({len(rows)} vòng đã chạy cho epic)"
    tail = rows[-flat_loops:]
    if len(tail) >= flat_loops and all(r["d_verified"] - r["d_reopened"] <= 0 for r in tail):
        return (f"cải thiện biên ≤ 0 trong {flat_loops} vòng liền "
                f"({', '.join(r['n'] for r in tail)})")
    spent = sum(float(r.get("cost_usd") or 0.0) for r in rows)
    if cost_cap and spent > cost_cap:
        return f"vượt improve.cost_cap_usd = ${cost_cap:.2f} (đã tiêu ${spent:.2f})"
    if rows and not auto and approvals.status(Gate.IMPROVE) is not Status.APPROVED:
        return ("chờ người duyệt cổng `improve` trước vòng %d: aisdlc review improve · "
                "aisdlc approve improve (hoặc --auto)" % (len(rows) + 1))
    return ""


def _write_report(root: Path, epic_id: str, lo: Loop, decision: str, spent: float) -> Path:
    b, a = lo.before, lo.after
    lines = [
        f"# Vòng cải tiến loop-{lo.n} — {epic_id} (vòng {lo.epic_loop} của epic)",
        "",
        f"- Story sửa: **{lo.story_id}** — hành vi `{lo.behavior}` — "
        f"{'XONG' if lo.done else 'CHƯA XONG'}",
        f"- Chi phí vòng: ${lo.cost_usd:.2f} (bằng chứng story sửa) · tổng epic: ${spent:.2f}",
        f"- Hành vi thuộc epic: VERIFIED {b['epic_verified']}→{a['epic_verified']} · "
        f"GAP {b['epic_gap']}→{a['epic_gap']} · REOPENED {b['epic_reopened']}→{a['epic_reopened']} · "
        f"Δverified − Δreopened = {lo.improvement:+d}",
        f"- Sổ toàn dự án: VERIFIED {b['verified']}→{a['verified']} · GAP {b['gap']}→{a['gap']} · "
        f"REOPENED {b['reopened']}→{a['reopened']}",
        f"- Gap thuộc epic trước: {len(b['gaps'])} ({', '.join(b['gaps'][:8]) or '—'})",
        f"- Gap thuộc epic sau: {len(a['gaps'])} ({', '.join(a['gaps'][:8]) or '—'})",
        f"- Quyết định: {'**dừng** — ' + decision if decision else '**tiếp** vòng kế'}",
        "",
        "## Kết cục cổng",
        "",
        "```",
        lo.outcome_text.strip() or "(không có story nào chạy)",
        "```",
        "",
        "Duyệt tiếp: `aisdlc approve improve` rồi chạy lại `aisdlc improve --epic "
        f"{epic_id}`. Lịch sử một hành vi: `aisdlc evidence <id>`.",
        "",
    ]
    path = root / LOOP_REPORT.format(n=lo.n)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def improve(
    project: Path | str,
    client: ClientAdapter,
    epic_id: str,
    *,
    config: Config | None = None,
    max_loops: int = 0,
    auto: bool = False,
    has_ui: bool = True,
) -> ImproveReport:
    """Chạy tối đa `max_loops` vòng (đếm cả vòng của lần gọi trước) rồi thoát."""
    project = Path(project)
    root = project / ARTIFACT_ROOT
    cfg = config or Config.load(project)
    max_loops = int(max_loops or cfg["improve.max_loops"])
    flat_loops = int(cfg["improve.flat_loops"])
    cost_cap = float(cfg["improve.cost_cap_usd"])
    report = ImproveReport(epic=epic_id)

    plan = load_plan(root)
    if plan.error:
        report.error = plan.error
        return report
    if epic_id not in plan.waves:
        report.error = f"epic không có trong kế hoạch: {epic_id}"
        return report
    try:
        worktrees = WorktreeManager(project)
    except GitError as e:
        report.error = f"{e} — story sửa luôn chạy trong worktree, cần kho git"
        return report

    state = StateStore(root)
    report.reconciled = reconcile_all(artifact_root=root, state=state, worktrees=worktrees)
    approvals = ApprovalStore(root)
    evidence = EvidenceStore(root)

    pending: Loop | None = None
    while True:
        # Bằng chứng cấp dự án ở HEAD hiện tại. Một lần QA đóng vòng trước
        # **và** mở vòng sau — QA đầu-cuối là thứ đắt, không chạy hai lần.
        label = f"loop-{pending.n}" if pending else BASELINE
        run_suite(project, config=cfg, has_ui=has_ui, story_id=label, artifact_root=root)
        led = ledger_mod.build(root)

        if pending is None:
            last = led.loops[-1] if led.loops else None
            if last is None or last.get("epic") != epic_id \
                    or _counts(last) != _counts(led.summary()):
                led.snapshot(BASELINE).update(epic=epic_id, **epic_counts(led, epic_id))
        else:
            rec = led.snapshot(f"loop-{pending.n}", cost_usd=pending.cost_usd)
            rec.update(epic=epic_id, story=pending.story_id, behavior=pending.behavior,
                       **epic_counts(led, epic_id))
            row = _epic_rows(led, epic_id)[-1]
            pending.d_verified, pending.d_reopened = row["d_verified"], row["d_reopened"]
            pending.after = {**led.summary(), **epic_counts(led, epic_id),
                             "gaps": [b.id for b in epic_gaps(led, epic_id)]}
        led.write(root)
        led.index(root)

        gaps = epic_gaps(led, epic_id)
        report.gaps_left = [b.id for b in gaps]
        stop = stop_reason(
            led, epic_id, gaps, pending, max_loops=max_loops, flat_loops=flat_loops,
            cost_cap=cost_cap, auto=auto, approvals=approvals,
        )
        if pending is not None:
            spent = sum(float(r.get("cost_usd") or 0.0) for r in _epic_rows(led, epic_id))
            pending.report_path = _write_report(root, epic_id, pending, stop, spent)
            report.loops.append(pending)
            pending = None
        if stop:
            report.stopped = stop
            return report

        n = 1 + sum(1 for lo in led.loops if lo.get("n") != BASELINE)
        b = gaps[0]
        path = repair_story(led, b, epic_id=epic_id, root=root, project=project,
                            config=cfg, state=state, loop=n)
        sid = path.stem
        loop = Loop(n=n, epic_loop=len(_epic_rows(led, epic_id)) + 1, story_id=sid,
                    behavior=b.id,
                    before={**led.summary(), **epic_counts(led, epic_id),
                            "gaps": [g.id for g in gaps]})

        # Không đổi một dòng trong `run`/`implement`: story sửa đi qua đúng
        # đường của story thường — worktree, cổng, reviewer ≠ developer.
        cost0 = evidence.read(sid).total_cost_usd
        rr = RunReport()
        run_epic(
            repair_epic(epic_id), load_plan(root),
            project=project, client=client, config=cfg, state=state,
            worktrees=worktrees, artifact_root=root, report=rr,
        )
        loop.cost_usd = evidence.read(sid).total_cost_usd - cost0
        loop.done = rr.ok
        loop.outcome_text = rr.summary()
        # Hai model độc lập cùng kết luận story sửa sai từ kế hoạch: vòng
        # sau nhận cùng gap sẽ cho cùng kết luận — trả người kèm lời reviewer.
        findings = [f for o in rr.outcomes for a in o.attempts for f in a.review_findings]
        stuck = plan_defects(findings)
        if stuck:
            loop.stuck = next((o.blocked_reason for o in rr.outcomes if o.blocked_reason),
                              "; ".join(stuck))
        pending = loop
