"""Lệnh dựng và vận hành harness: ``init`` · ``setup`` · ``compile`` ·
``guard`` · ``gate`` · ``skill`` · ``doc``."""

from __future__ import annotations

import sys
from pathlib import Path

from ..config import Config
from ..harness.tools import aisef_command
from ._common import ARTIFACT_ROOT, EXIT_NOT_READY, EXIT_OK, EXIT_USAGE, _artifact_root, _client


def cmd_init(args) -> int:
    """Ghi file cấu hình mặc định để chỉnh."""
    path = Config.load(args.project).write_template(args.project)
    print(f"đã ghi {path}")
    return EXIT_OK


def cmd_setup(args) -> int:
    """Dò stack rồi nạp skill phù hợp vào dự án."""
    from ..kit import install
    from ..kit.detect_stack import detect_file

    project = Path(args.project)
    req = project / "docs" / "requirements.md"
    if not req.is_file():
        print(f"✗ không có {req}", file=sys.stderr)
        print("  đây là đầu vào duy nhất của dự án — tạo nó trước", file=sys.stderr)
        return EXIT_NOT_READY

    from ..kit import fetch

    references = (
        Path(args.references).resolve() if args.references else fetch.default_root()
    )
    if not args.no_fetch:
        print(f"Nguồn skill: {references}")
        bao = fetch.ensure(references)
        print(bao.summary())
        print()
    if not references.is_dir():
        print(f"✗ không có thư mục nguồn: {references}", file=sys.stderr)
        print("  chạy lại không kèm --no-fetch để tự lấy về", file=sys.stderr)
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

    from ..kit.constitution import write_for_project

    written = write_for_project(project, project.resolve().name, stack)
    print("quy tắc: " + ", ".join(p.name for p in written))

    cfg_path = project / ".ai" / "config.json"
    if not cfg_path.is_file():
        Config.load(project).write_template(project)
        print(f"đã ghi {cfg_path}")

    print(f"\n✅ xong. Kiểm tra: aisef --project {args.project} doctor")
    return EXIT_OK


def cmd_compile(args) -> int:
    """Sinh cấu hình client từ một nguồn duy nhất."""
    from ..clients.compile import ADAPTERS, compile_for, write_compile_report

    clients = sorted(ADAPTERS) if args.client == "all" else [args.client]
    # Không tự đoán đường dẫn: `aisef_command` đã biết ưu tiên tên trên PATH
    # (bản cài thật) rồi mới lùi về `bin/aisef` của kho nguồn.
    aisef_bin = args.bin or aisef_command()

    reports = []
    for client in clients:
        try:
            r = compile_for(client, args.project, aisef_bin=aisef_bin)
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


def cmd_guard(args) -> int:
    """Chạy một guard trên sự kiện hook đọc từ stdin.

    Client gọi lệnh này tại mốc vòng đời. Thoát 2 là chặn, và lý do đi ra
    stderr — Claude Code chuyển stderr vào kết quả tool cho agent đọc, nên
    lý do phải nói được agent cần sửa gì.
    """
    import json

    from ..control.worktree import main_repo
    from ..harness.guardrails import project_root_from, record_outcome, run_guard

    # Gốc dự án: harness khai qua env; `--project` biên dịch chỉ là dự phòng —
    # dự án bị chép/di chuyển thì hook vẫn ghim đường dẫn cũ (P0-1, 2026-09-05).
    goc = Path(project_root_from(None, str(args.project))).resolve()
    artifact_root = main_repo(goc) / ARTIFACT_ROOT

    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        # Không đọc được sự kiện thì cho qua: guard hỏng không được biến
        # thành thứ chặn mọi thao tác của agent.
        print("guard: không phân tích được sự kiện, bỏ qua", file=sys.stderr)
        return EXIT_OK

    try:
        verdict = run_guard(
            args.kind,
            event,
            project_root=str(goc),
            artifact_root=str(artifact_root),
        )
    except ValueError as e:
        print(f"guard: {e}", file=sys.stderr)
        return EXIT_OK

    # Guard tự ghi bằng chứng: chỗ duy nhất mọi client đều đi qua, nên
    # `guard_blocked` và `FILE_CHANGE` không còn phụ thuộc client có phát
    # luồng sự kiện hay không. Ghi hỏng không được làm hỏng phán quyết.
    try:
        record_outcome(args.kind, event, verdict, artifact_root=str(artifact_root))
    except OSError as e:
        print(f"guard: không ghi được bằng chứng ({e})", file=sys.stderr)

    if not verdict.allowed:
        print(verdict.reason, file=sys.stderr)
    return verdict.exit_code


def cmd_skill(args) -> int:
    """Dựng và soi sổ đăng ký skill (ADR-002). Chỉ đọc — không sửa dự án."""
    from ..kit import registry as R
    from ..kit import router as RT
    from ..phases.run import load_plan

    project = Path(args.project)
    if getattr(args, "scan", False):
        from ..kit import skill_scan

        adapter, rc = _client(args)
        if adapter is None:
            return rc
        R.refresh(project, _artifact_root(args))
        rep = skill_scan.scan(project, _artifact_root(args), adapter,
                              config=Config.load(project), batch=args.batch)
        print(rep.summary())
        for v in rep.flagged:
            print(f"  {v.risk:10} {v.id:45} {v.why[:90]}")
        if rep.error:
            return EXIT_NOT_READY
    reg = R.refresh(project, _artifact_root(args))
    by = reg.by_status()
    print(f"Sổ skill: {len(reg.entries)} bản ghi")
    for st in R.STATUSES:
        if by[st]:
            print(f"  {st:10} {by[st]}")
    rej = [e for e in reg.entries.values() if e.status == R.REJECTED]
    if rej:
        print("\n✗ bị loại (không định tuyến):")
        for e in rej[:10]:
            print(f"    {e.id:50} {'; '.join(e.verified.gaps[:1])}")

    if args.story:
        plan = load_plan(_artifact_root(args))
        st = plan.stories.get(args.story)
        if st is None:
            print(f"\nkhông có story {args.story} trong kế hoạch", file=sys.stderr)
            return EXIT_NOT_READY
        r = RT.route(st, reg, project=project)
        print(f"\nĐịnh tuyến cho {args.story} — {st.title}:")
        print("  " + r.prompt_section().replace(chr(10), chr(10) + "  "))
    return EXIT_OK


def cmd_doc(args) -> int:
    """Tra tài liệu thư viện theo yêu cầu (luật 12) — context7 qua HTTP, có cache.
    Có `--story` thì ghi bằng chứng `doc_lookup`: cổng và báo cáo biết agent
    đã tra gì thay vì bịa."""
    from ..kit.docs import DocError, lookup

    try:
        d = lookup(args.package, args.topic or "", tokens=args.tokens)
    except DocError as e:
        print(f"doc: {e}", file=sys.stderr)
        return EXIT_NOT_READY
    except OSError as e:
        print(f"doc: không gọi được context7 ({e}) — làm việc theo tài liệu đã có, đừng đoán tên API", file=sys.stderr)
        return EXIT_NOT_READY
    print(f"# {d.title or d.library} — {d.topic or 'tổng quan'} ({'cache' if d.cached else 'context7'}: {d.library})\n")
    print(d.text)
    if args.story:
        from ..harness.observe import NOTE, Event, EvidenceStore

        EvidenceStore(_artifact_root(args)).record(args.story, Event(
            kind=NOTE, name="doc_lookup",
            detail={"package": args.package, "library": d.library, "topic": d.topic, "chars": len(d.text), "cached": d.cached},
        ))
    return EXIT_OK


def cmd_gate(args) -> int:
    """Chấm lại cổng story trên bằng chứng đã ghi (ADR-005 V4).

    Chỉ đọc: cắt bằng chứng ở `gate:input` của từng lượt, gọi `gate.evaluate`
    của mã **hiện tại**, in bảng từng mục so với `gate:verdict` đã ghi. Không
    gọi model — lời reviewer/security là thứ đã ghi. Lượt không có `gate:input`
    (trước V4) được nêu là không replay được, không đoán. Thoát 2 khi không
    replay được lượt nào của thứ được hỏi.
    """
    from ..control import replay as R
    from ..harness.observe import EvidenceStore

    if not args.replay:
        print("✗ gate: hiện chỉ có `--replay` (chấm lại trên bằng chứng)", file=sys.stderr)
        return EXIT_USAGE
    if not args.story and not args.all:
        print("✗ gate --replay cần <story> hoặc --all", file=sys.stderr)
        return EXIT_USAGE

    store = EvidenceStore(_artifact_root(args))
    ids = store.stories() if args.all else [args.story]
    print(R.BANNER)
    duoc = tong = 0
    for sid in ids:
        ev = store.read(sid)
        rs = R.replay(ev, attempt=args.attempt)
        thieu = R.unreplayable(ev)
        if args.attempt:
            thieu = [a for a in thieu if a == args.attempt]
        if not rs and not thieu:
            if not args.all:
                print(f"✗ {sid}: không có lượt chấm cổng nào trong bằng chứng", file=sys.stderr)
            continue
        print()
        for r in rs:
            print(r.summary())
        for a in thieu:
            print(f"{sid} lượt {a}: không replay được (bằng chứng trước ADR-005 V4 — "
                  f"không có `gate:input`), không đoán")
        duoc += len(rs)
        tong += len(rs) + len(thieu)
    print(f"\nreplay được {duoc}/{tong} lượt")
    return EXIT_OK if duoc else EXIT_NOT_READY
