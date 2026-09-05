"""Pha lập kế hoạch và các cổng người: ``gates`` · ``review`` · ``approve``
· ``reject`` · ``auto-approve`` · ``plan`` · ``mockup`` · ``change``."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ..config import Config
from ..control.approvals import (
    GATE_ORDER,
    STORIES_INDEX,
    ApprovalStore,
    Gate,
    Status,
    parse_auto_approve,
)
from ..control.design_contract import CONTRACT_FILE
from ._common import (
    _GATE_MARK,
    EXIT_NOT_READY,
    EXIT_OK,
    EXIT_USAGE,
    _approvals,
    _artifact_root,
    _client,
)


def cmd_gates(args) -> int:
    store = _approvals(args)
    print(f"Cổng phê duyệt — {_artifact_root(args)}\n")
    pending_first = None
    for gate, status, by in store.summary():
        mark = _GATE_MARK[status]
        who = f"  ({by})" if by else ""
        missing = [p.name for p in store.artifact_paths(gate) if not p.is_file()]
        exists = "" if not missing else f"   [thiếu: {', '.join(missing)}]"
        print(f"  {mark} {gate.value:14} {status.value:18}{who}{exists}")
        if pending_first is None and status is not Status.APPROVED:
            pending_first = gate

    if pending_first:
        print(f"\nCổng kế tiếp cần xử lý: {pending_first.value}")
        print(f"  aisdlc review {pending_first.value}")
        return EXIT_NOT_READY
    print("\n✅ mọi cổng đã duyệt")
    return EXIT_OK


def cmd_review(args) -> int:
    """Hiện artifact và những gì cần xem trước khi duyệt."""
    store = _approvals(args)
    gate: Gate = args.gate
    paths = store.artifact_paths(gate)
    status = store.status(gate)

    print(f"Cổng: {gate.value}")
    print(f"Trạng thái: {status.value}")
    print("Artifact: " + ", ".join(str(p) for p in paths))

    missing = [p for p in paths if not p.is_file()]
    if missing:
        names = ", ".join(p.name for p in missing)
        print(f"\n✗ chưa có artifact ({names}) — chạy bước sinh ra nó trước")
        return EXIT_NOT_READY

    blocking = store.blocking(gate)
    if blocking:
        print(f"\n⚠️  cổng phía trước chưa duyệt: {', '.join(g.value for g in blocking)}")

    rec = store.load(gate)
    if rec and rec.note:
        print(f"\nGhi chú lần trước ({rec.status}): {rec.note}")

    for artifact in paths:
        if artifact.name == CONTRACT_FILE:
            from ..phases.mockup import describe_contract

            data = json.loads(artifact.read_text(encoding="utf-8"))
            print(f"\n— {len(data.get('screens', []))} màn hình —\n")
            print(describe_contract(data, artifact.parent))
            continue
        if artifact.name == STORIES_INDEX:
            from ..phases.story_split import describe_index

            data = json.loads(artifact.read_text(encoding="utf-8"))
            print(f"\n— {len(data.get('stories', []))} story —")
            print(describe_index(data))
            continue
        lines = artifact.read_text(encoding="utf-8", errors="replace").splitlines()
        print(f"\n— {artifact.name} ({len(lines)} dòng) —\n")
        print("\n".join(lines[: args.lines]))
        if len(lines) > args.lines:
            print(f"\n… còn {len(lines) - args.lines} dòng. Mở: {artifact}")

    if gate is Gate.READINESS:
        for line in _preflight_lines(args):
            print(line)

    print(f"\nDuyệt:    aisdlc approve {gate.value}")
    print(f"Trả lại:  aisdlc reject  {gate.value} --note \"...\"")
    return EXIT_OK


def _preflight_lines(args) -> list[str]:
    """Story nào chưa chạy được — tính bằng code, ngay trước cổng người.

    Cổng `readiness` là mốc cuối trước khi tiêu tiền. Ở đây mockup đã dựng
    và công cụ đã cấu hình xong, nên **cả hai** loại thiếu đều chặn được:
    story hỏng lẫn dự án chưa cấu hình.
    """
    from ..control.preflight import STORY_NOT_EXECUTABLE, check_stories_executable
    from ..phases.run import load_plan

    project = Path(args.project).resolve()
    plan = load_plan(_artifact_root(args))
    if plan.error or not plan.stories:
        return []
    res = check_stories_executable(
        list(plan.stories.values()), project=project, config=Config.load(args.project)
    )
    # Cổng người: đòi **đủ**, kể cả năng lực nghiệm thu. Đây là mốc
    # cuối trước khi tiêu tiền, và người duyệt cần thấy chỗ trống.
    xau = [pf for pf in res if not pf.complete]
    if not xau:
        return [f"\n✅ {len(res)} story đều chạy được"]
    out = [f"\n✗ {len(xau)}/{len(res)} story chưa đủ điều kiện:"]
    for pf in xau:
        nhan = STORY_NOT_EXECUTABLE if not pf.executable else "THIẾU BẰNG CHỨNG"
        out.append(f"  {nhan} {pf.story_id}")
        out += [f"    - {m.line()}" for m in pf.missing]
    return out


def cmd_approve(args) -> int:
    store = _approvals(args)
    gate: Gate = args.gate
    if not store.has_artifacts(gate):
        missing = ", ".join(p.name for p in store.artifact_paths(gate) if not p.is_file())
        print(f"✗ chưa có artifact cho cổng {gate.value}: {missing}", file=sys.stderr)
        return EXIT_NOT_READY

    blocking = store.blocking(gate)
    if blocking and not args.force:
        names = ", ".join(g.value for g in blocking)
        print(f"✗ cổng phía trước chưa duyệt: {names}", file=sys.stderr)
        print("  duyệt chúng trước, hoặc dùng --force nếu cố ý bỏ qua", file=sys.stderr)
        return EXIT_NOT_READY

    if gate is Gate.READINESS and not args.force:
        lines = _preflight_lines(args)
        if any("✗" in ln for ln in lines):
            print("\n".join(lines), file=sys.stderr)
            print(
                "\n✗ không duyệt được: còn story chưa chạy được. Sửa rồi duyệt "
                "lại, hoặc --force nếu cố ý.",
                file=sys.stderr,
            )
            return EXIT_NOT_READY

    rec = store.approve(gate, note=args.note or "")
    print(f"✅ {gate.value} đã duyệt bởi {rec.decided_by}")
    return EXIT_OK


def cmd_reject(args) -> int:
    store = _approvals(args)
    gate: Gate = args.gate
    try:
        rec = store.reject(gate, note=args.note)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return EXIT_USAGE
    print(f"✗ {gate.value} trả lại: {rec.note}")
    return EXIT_OK


def cmd_auto_approve(args) -> int:
    """Tự duyệt — luôn ghi dấu `auto` để về sau truy được."""
    try:
        gates = parse_auto_approve(args.gates)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return EXIT_USAGE

    store = _approvals(args)
    done = []
    for gate in GATE_ORDER:
        if gate in gates and store.has_artifacts(gate):
            store.auto_approve(gate)
            done.append(gate.value)
    print(f"tự duyệt: {', '.join(done) if done else '(không cổng nào có artifact)'}")
    return EXIT_OK


def cmd_plan(args) -> int:
    """Chạy chuỗi pha BMAD tới cổng đầu tiên chưa duyệt."""
    from ..phases.plan import run_pipeline

    # Kiểm tham số trước, kiểm môi trường sau: sai tham số thì máy nào
    # cũng sai, còn thiếu client thì tuỳ máy — trộn hai loại lại sẽ cho mã
    # thoát đổi theo máy chạy.
    try:
        gates = parse_auto_approve(args.auto_approve)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return EXIT_USAGE

    adapter, code = _client(args)
    if adapter is None:
        return code

    result = run_pipeline(
        args.project,
        adapter,
        config=Config.load(args.project),
        auto_approve=gates,
        force=args.force,
    )
    print(result.summary())

    if result.failed_at:
        return EXIT_USAGE
    return EXIT_OK if result.complete else EXIT_NOT_READY


def cmd_mockup(args) -> int:
    """Dựng mockup cho từng màn hình rồi trích hợp đồng thị giác."""
    from ..control.approvals import Gate
    from ..phases.mockup import generate
    from ..phases.plan import _pass_gate

    try:
        gates = parse_auto_approve(args.auto_approve)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return EXIT_USAGE

    adapter, code = _client(args)
    if adapter is None:
        return code

    res = generate(
        args.project,
        adapter,
        config=Config.load(args.project),
        force=args.force,
        only=[s.strip() for s in args.only.split(",") if s.strip()] or None,
    )
    print(res.summary())

    if res.error or res.failed:
        return EXIT_USAGE
    if not res.ok:
        return EXIT_NOT_READY

    store = ApprovalStore(_artifact_root(args))
    if _pass_gate(store, Gate.MOCKUPS, res, gates):
        return EXIT_OK
    print(f"\n⏸ chờ người duyệt: {Gate.MOCKUPS.value}\n   aisdlc review mockups")
    return EXIT_NOT_READY


def cmd_change(args) -> int:
    """Vòng đời thay đổi: ghi yêu cầu đổi, đánh stale PRD trở xuống, sinh story delta."""
    from ..control.change import apply

    try:
        r = apply(Path(args.project), args.requirement, args.description)
    except (ValueError, OSError) as e:
        print(f"change: {e}", file=sys.stderr)
        return EXIT_NOT_READY
    print(f"Đã ghi thay đổi {r.requirement} → story delta {r.story_id} ({r.story_file.name})")
    print("  PRD: " + ("đã đánh dấu — cổng prd và các cổng sau thành stale" if r.prd_marked else "chưa có prd.md — cổng sẽ chạy từ đầu"))
    print("Việc tiếp theo:")
    for b in r.next_steps:
        print(f"  - {b}")
    return EXIT_OK
