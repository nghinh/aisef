"""Giao diện dòng lệnh.

Mọi lệnh đều **gọi-một-lần**: đọc trạng thái trên đĩa, làm việc, ghi lại,
rồi thoát. Không lệnh nào giả định mình là tiến trình chính, không lệnh
nào chạy nền. Đó là điều kiện để cùng bộ lệnh này dùng được ở hai chế độ
(quyết định Đ2):

* **driver-led** — script hoặc CI gọi ``aisdlc run``;
* **agent-led** — chính agent gọi ``aisdlc next`` / ``verify`` / ``complete``
  qua Bash, ngay trong phiên chat của Claude Desktop hay OpenCode.

Quy ước mã thoát: ``0`` thành công · ``1`` lỗi dùng sai · ``2`` trạng thái
chưa đạt (cổng chưa duyệt, doctor không đạt) — để CI phân biệt được
"hỏng" với "chưa xong".
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from .config import Config, ConfigError
from .control.approvals import (
    GATE_ORDER,
    STORIES_INDEX,
    ApprovalStore,
    Gate,
    Status,
    parse_auto_approve,
)
from .control.state import StateStore, StoryStatus
from .harness.guardrails import GUARD_MATCHERS

ARTIFACT_ROOT = "_bmad-output"

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NOT_READY = 2

#: Ký hiệu trạng thái cổng, đủ để đọc lướt.
_GATE_MARK = {
    Status.APPROVED: "✅",
    Status.PENDING: "⏳",
    Status.CHANGES_REQUESTED: "✗",
    Status.STALE: "⚠️",
}


def _artifact_root(args) -> Path:
    return Path(args.project) / ARTIFACT_ROOT


def _approvals(args) -> ApprovalStore:
    return ApprovalStore(_artifact_root(args))


def _state(args) -> StateStore:
    return StateStore(_artifact_root(args))


# ------------------------------------------------------------------ doctor


def cmd_doctor(args) -> int:
    """Kiểm tra môi trường có đủ chạy framework không."""
    project = Path(args.project)
    problems: list[str] = []
    lines: list[str] = []

    def check(label: str, ok: bool, detail: str = "", *, required: bool = True) -> None:
        mark = "✅" if ok else ("✗" if required else "○")
        lines.append(f"  {mark} {label}{(' — ' + detail) if detail else ''}")
        if required and not ok:
            problems.append(label)

    lines.append("Môi trường:")
    check("python >= 3.11", sys.version_info >= (3, 11), sys.version.split()[0])
    check("git", bool(shutil.which("git")))

    claude = shutil.which("claude")
    check("claude CLI", bool(claude), claude or "không tìm thấy", required=False)
    opencode = shutil.which("opencode")
    check("opencode CLI", bool(opencode), opencode or "không tìm thấy", required=False)

    docker_ok = False
    if shutil.which("docker"):
        try:
            docker_ok = subprocess.run(
                ["docker", "info"], capture_output=True, timeout=10
            ).returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            docker_ok = False
    check(
        "docker daemon",
        docker_ok,
        "chạy" if docker_ok else "không chạy — sandbox sẽ suy biến, bảo đảm thấp hơn",
        required=False,
    )

    lines.append("Dự án:")
    check("thư mục dự án", project.is_dir(), str(project))
    req = project / "docs" / "requirements.md"
    check("docs/requirements.md", req.is_file(), str(req))

    try:
        cfg = Config.load(project)
        check("cấu hình", True, cfg.source)
    except ConfigError as e:
        check("cấu hình", False, str(e))

    skills_dir = project / ".claude" / "skills"
    if skills_dir.is_dir():
        from .kit.security_filter import Verdict, classify_all

        installed = [d for d in skills_dir.iterdir() if d.is_dir()]
        lines.append("Skill đã cài:")
        check("có skill", bool(installed), f"{len(installed)} thư mục")

        # Bất biến: skill tấn công không bao giờ được có mặt trong dự án.
        offensive = [
            c.skill.name
            for c in classify_all(skills_dir)
            if c.verdict is Verdict.OFFENSIVE
        ]
        check(
            "không có skill tấn công",
            not offensive,
            "sạch" if not offensive else f"LỌT: {', '.join(offensive[:5])}",
        )
    else:
        lines.append("Skill đã cài:")
        check("đã chạy setup", False, "chưa — chạy: aisdlc setup", required=False)

    print("\n".join(lines))
    if problems:
        print(f"\n✗ thiếu: {', '.join(problems)}")
        return EXIT_NOT_READY
    print("\n✅ sẵn sàng")
    return EXIT_OK


# ------------------------------------------------------------------ cổng


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


def _gate_arg(value: str) -> Gate:
    try:
        return Gate(value)
    except ValueError:
        valid = ", ".join(g.value for g in GATE_ORDER)
        raise argparse.ArgumentTypeError(f"cổng không hợp lệ: {value}. Hợp lệ: {valid}")


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
        if artifact.name == STORIES_INDEX:
            from .phases.story_split import describe_index

            data = json.loads(artifact.read_text(encoding="utf-8"))
            print(f"\n— {len(data.get('stories', []))} story —")
            print(describe_index(data))
            continue
        lines = artifact.read_text(encoding="utf-8", errors="replace").splitlines()
        print(f"\n— {artifact.name} ({len(lines)} dòng) —\n")
        print("\n".join(lines[: args.lines]))
        if len(lines) > args.lines:
            print(f"\n… còn {len(lines) - args.lines} dòng. Mở: {artifact}")

    print(f"\nDuyệt:    aisdlc approve {gate.value}")
    print(f"Trả lại:  aisdlc reject  {gate.value} --note \"...\"")
    return EXIT_OK


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


# ------------------------------------------------------------------ trạng thái


def cmd_status(args) -> int:
    state = _state(args).load()
    cfg = Config.load(args.project)

    if not state.stories:
        print("Chưa có story nào được đăng ký.")
        return EXIT_OK

    totals = state.totals()
    total = len(state.stories)
    done = totals[StoryStatus.DONE.value]

    print(f"Tiến độ: {done}/{total} story xong")
    if state.current_epic:
        print(f"Epic hiện tại: {state.current_epic}")
    print()
    for status in StoryStatus:
        n = totals[status.value]
        if n:
            print(f"  {status.value:11} {n}")

    print(f"\nChi phí: ${state.total_cost_usd:.2f}")
    outliers = state.cost_outliers(cfg["cost.warn_multiple"])
    if outliers:
        print(f"⚠️  {len(outliers)} story tốn hơn {cfg['cost.warn_multiple']}× trung vị:")
        for r in sorted(outliers, key=lambda r: -r.cost_usd)[:5]:
            print(f"    {r.id:16} ${r.cost_usd:.2f}")

    blocked = state.by_status(StoryStatus.BLOCKED)
    if blocked:
        print(f"\n✗ {len(blocked)} story bị chặn:")
        for r in blocked[:10]:
            print(f"    {r.id:16} {r.blocked_reason or '(không rõ lý do)'}")
        return EXIT_NOT_READY
    return EXIT_OK


def cmd_init(args) -> int:
    """Ghi file cấu hình mặc định để chỉnh."""
    path = Config.load(args.project).write_template(args.project)
    print(f"đã ghi {path}")
    return EXIT_OK


# ------------------------------------------------------------------ setup


def cmd_setup(args) -> int:
    """Dò stack rồi nạp skill phù hợp vào dự án."""
    from .kit import install
    from .kit.detect_stack import detect_file

    project = Path(args.project)
    req = project / "docs" / "requirements.md"
    if not req.is_file():
        print(f"✗ không có {req}", file=sys.stderr)
        print("  đây là đầu vào duy nhất của dự án — tạo nó trước", file=sys.stderr)
        return EXIT_NOT_READY

    references = Path(args.references).resolve()
    if not references.is_dir():
        print(f"✗ không có thư mục nguồn: {references}", file=sys.stderr)
        return EXIT_NOT_READY

    stack = detect_file(req)
    print(f"Stack dò được: {stack.summary()}")
    if stack.undetermined:
        print(f"  ⚠️  chưa xác định: {', '.join(stack.undetermined)}")
        print("     — pha kiến trúc sẽ quyết; không đoán ở đây")

    text = req.read_text(encoding="utf-8", errors="replace")
    plan_ = install.plan(project, stack, references_root=references, requirements_text=text)
    print()
    print(plan_.summary())

    if args.dry_run:
        print("\n(dry-run — chưa ghi gì)")
        return EXIT_OK

    report = install.apply(plan_, project)
    print(f"\n{report.summary()}")

    from .kit.constitution import write_for_project

    written = write_for_project(project, project.resolve().name, stack)
    print("quy tắc: " + ", ".join(p.name for p in written))

    cfg_path = project / ".ai" / "config.json"
    if not cfg_path.is_file():
        Config.load(project).write_template(project)
        print(f"đã ghi {cfg_path}")

    print(f"\n✅ xong. Kiểm tra: aisdlc --project {args.project} doctor")
    return EXIT_OK


# ------------------------------------------------------------------ compile


def cmd_compile(args) -> int:
    """Sinh cấu hình client từ một nguồn duy nhất."""
    from .clients.compile import ADAPTERS, compile_for, write_compile_report

    clients = sorted(ADAPTERS) if args.client == "all" else [args.client]
    aisdlc_bin = args.bin or str((Path(__file__).resolve().parent.parent / "bin" / "aisdlc"))

    reports = []
    for client in clients:
        try:
            r = compile_for(client, args.project, aisdlc_bin=aisdlc_bin)
        except ValueError as e:
            print(f"✗ {e}", file=sys.stderr)
            return EXIT_USAGE
        reports.append(r)
        print(r.summary())

    path = write_compile_report(args.project, reports)
    print(f"\nbáo cáo: {path}")

    if any(not r.blocks_at_source for r in reports):
        print("\n⚠️  có client chỉ kiểm được sau — mức bảo đảm thấp hơn, đã ghi vào báo cáo")
    return EXIT_OK


# ------------------------------------------------------------------ guard


def cmd_guard(args) -> int:
    """Chạy một guard trên sự kiện hook đọc từ stdin.

    Client gọi lệnh này tại mốc vòng đời. Thoát 2 là chặn, và lý do đi ra
    stderr — Claude Code chuyển stderr vào kết quả tool cho agent đọc, nên
    lý do phải nói được agent cần sửa gì.
    """
    import json

    from .harness.guardrails import run_guard

    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        # Không đọc được sự kiện thì cho qua: guard hỏng không được biến
        # thành thứ chặn mọi thao tác của agent.
        print("guard: không phân tích được sự kiện, bỏ qua", file=sys.stderr)
        return EXIT_OK

    try:
        verdict = run_guard(args.kind, event, project_root=str(Path(args.project).resolve()))
    except ValueError as e:
        print(f"guard: {e}", file=sys.stderr)
        return EXIT_OK

    if not verdict.allowed:
        print(verdict.reason, file=sys.stderr)
    return verdict.exit_code


# ------------------------------------------------------------------ lập kế hoạch


def cmd_plan(args) -> int:
    """Chạy chuỗi pha BMAD tới cổng đầu tiên chưa duyệt."""
    from .clients.compile import ADAPTERS
    from .phases.plan import run_pipeline

    # Kiểm tham số trước, kiểm môi trường sau: sai tham số thì máy nào
    # cũng sai, còn thiếu client thì tuỳ máy — trộn hai loại lại sẽ cho mã
    # thoát đổi theo máy chạy.
    if args.client not in ADAPTERS:
        print(f"✗ client không hỗ trợ: {args.client}", file=sys.stderr)
        return EXIT_USAGE
    try:
        gates = parse_auto_approve(args.auto_approve)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return EXIT_USAGE

    adapter = ADAPTERS[args.client]()
    if not adapter.available():
        print(f"✗ chưa cài {args.client} trên máy này", file=sys.stderr)
        return EXIT_NOT_READY

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


# ------------------------------------------------------------------ đầu vào


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aisdlc",
        description="AI-SDLC — điều phối vòng đời phát triển bằng agent",
    )
    p.add_argument("--project", default=".", help="thư mục dự án (mặc định: thư mục hiện tại)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("setup", help="dò stack và nạp skill vào dự án")
    s.add_argument("--references", default="references", help="thư mục chứa kho skill đã clone")
    s.add_argument("--dry-run", action="store_true", help="chỉ in kế hoạch, không ghi")
    s.set_defaults(func=cmd_setup)

    sub.add_parser("doctor", help="kiểm tra môi trường").set_defaults(func=cmd_doctor)
    sub.add_parser("init", help="ghi .ai/config.json mặc định").set_defaults(func=cmd_init)
    sub.add_parser("gates", help="bảng trạng thái 8 cổng").set_defaults(func=cmd_gates)
    sub.add_parser("status", help="tiến độ story, chi phí").set_defaults(func=cmd_status)

    r = sub.add_parser("review", help="xem artifact của một cổng")
    r.add_argument("gate", type=_gate_arg)
    r.add_argument("--lines", type=int, default=60, help="số dòng hiển thị")
    r.set_defaults(func=cmd_review)

    a = sub.add_parser("approve", help="duyệt một cổng")
    a.add_argument("gate", type=_gate_arg)
    a.add_argument("--note", default="")
    a.add_argument("--force", action="store_true", help="duyệt dù cổng trước chưa xong")
    a.set_defaults(func=cmd_approve)

    j = sub.add_parser("reject", help="trả lại một cổng kèm ghi chú")
    j.add_argument("gate", type=_gate_arg)
    j.add_argument("--note", required=True, help="cần sửa gì — bắt buộc")
    j.set_defaults(func=cmd_reject)

    c = sub.add_parser("compile", help="sinh cấu hình client (hook, plugin)")
    c.add_argument("--client", default="all", help="claude | opencode | all")
    c.add_argument("--bin", default="", help="đường dẫn lệnh aisdlc dùng trong hook")
    c.set_defaults(func=cmd_compile)

    g = sub.add_parser("guard", help="chạy guard trên sự kiện hook (đọc stdin)")
    g.add_argument("kind", choices=sorted(GUARD_MATCHERS))
    g.set_defaults(func=cmd_guard)

    pl = sub.add_parser("plan", help="chạy chuỗi pha BMAD tới cổng chưa duyệt")
    pl.add_argument("--client", default="claude", help="claude | opencode")
    pl.add_argument("--auto-approve", default="", help="'all' hoặc danh sách cổng")
    pl.add_argument("--force", action="store_true", help="chạy lại cả pha đã có artifact")
    pl.set_defaults(func=cmd_plan)

    aa = sub.add_parser("auto-approve", help="tự duyệt (ghi dấu auto)")
    aa.add_argument("gates", help="'all' hoặc danh sách ngăn bởi dấu phẩy")
    aa.set_defaults(func=cmd_auto_approve)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as e:
        print(f"✗ cấu hình: {e}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("\nđã huỷ", file=sys.stderr)
        return EXIT_USAGE
    except Exception as e:  # noqa: BLE001 — biên ngoài cùng: báo rõ, không nuốt
        print(f"✗ {type(e).__name__}: {e}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
