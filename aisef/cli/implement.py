"""Pha hiện thực và nghiệm thu: ``status`` · ``run`` · ``verify`` ·
``tool`` · ``qa`` · ``devsecops`` · ``pre-deploy`` · ``report``."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ..config import Config
from ..control.approvals import STORIES_INDEX, Status
from ..control.state import StoryStatus
from ._common import (
    EXIT_NOT_READY,
    EXIT_OK,
    EXIT_USAGE,
    _approvals,
    _artifact_root,
    _client,
    _state,
)


def cmd_status(args) -> int:
    state = _state(args).load()
    cfg = Config.load(args.project)

    if not state.stories:
        print("No stories registered.")
        return EXIT_OK

    totals = state.totals()
    total = len(state.stories)
    done = totals[StoryStatus.DONE.value]

    print(f"Progress: {done}/{total} stories done")
    # `verified` = qua cổng, chưa lên nhánh chính (merge đụng ở lượt trước).
    # Không nói ra thì người đọc tưởng code đã ở main.
    chua_merge = [r.id for r in state.by_status(StoryStatus.VERIFIED)]
    if chua_merge:
        print(f"⚠️  {len(chua_merge)} stories done but not merged to main: "
              f"{', '.join(chua_merge[:5])} — run `aisef run` again to merge")
    if state.active_epics:
        print(f"Active epics: {', '.join(state.active_epics)}")
    elif state.current_epic:
        print(f"Current epic: {state.current_epic}")
    print()
    for status in StoryStatus:
        n = totals[status.value]
        if n:
            print(f"  {status.value:11} {n}")

    print(f"\nCost: ${state.total_cost_usd:.2f}")
    outliers = state.cost_outliers(cfg["cost.warn_multiple"])
    if outliers:
        print(f"⚠️  {len(outliers)} stories cost more than {cfg['cost.warn_multiple']}x median:")
        for r in sorted(outliers, key=lambda r: -r.cost_usd)[:5]:
            print(f"    {r.id:16} ${r.cost_usd:.2f}")

    # Ngữ cảnh nạp mỗi story — đo thật từ evidence, thay cho knob
    # `story.max_context_tokens` chưa từng có mã đọc. Cùng ngưỡng 3× trung
    # vị như chi phí: story nạp gấp ba story khác là dấu hiệu chẻ sai.
    from ..harness.observe import AGENT_RUN, SKILL_USE, EvidenceStore

    ev_store = EvidenceStore(_artifact_root(args))
    nap = {}
    ket_cuc: dict[str, int] = {}
    for sid in ev_store.stories():
        runs = ev_store.read(sid).of(AGENT_RUN)
        sizes = [int(e.detail.get("prompt_chars") or 0) for e in runs]
        if any(sizes):
            nap[sid] = max(sizes)
        for e in runs:
            k = str(e.detail.get("exit_status") or "unrecorded")
            ket_cuc[k] = ket_cuc.get(k, 0) + 1
    # Kết cục từng lượt gọi model (ADR-005 V11 B) — đếm theo `exit_status`
    # harness chuẩn hoá lúc ghi. Lượt ghi trước khoá này là "chưa ghi":
    # không suy đoán thay bằng chứng cũ.
    if ket_cuc:
        print("Agent runs: " + " · ".join(
            f"{k} {n}" for k, n in sorted(ket_cuc.items(), key=lambda kv: -kv[1])))
    skill_counts: dict[str, int] = {}
    for sid in ev_store.stories():
        for e in ev_store.read(sid).of(SKILL_USE):
            skill_counts[e.name] = skill_counts.get(e.name, 0) + 1
    if skill_counts:
        print("Skill: " + " · ".join(
            f"{k} ×{n}" for k, n in sorted(skill_counts.items(), key=lambda kv: -kv[1])))

    if len(nap) >= 3:
        trung_vi = sorted(nap.values())[len(nap) // 2]
        phinh = {k: v for k, v in nap.items() if v > cfg["cost.warn_multiple"] * trung_vi}
        if phinh:
            print(f"⚠️  {len(phinh)} stories loaded context exceeding {cfg['cost.warn_multiple']}x median "
                  f"({trung_vi:,} chars):")
            for k, v in sorted(phinh.items(), key=lambda kv: -kv[1])[:5]:
                print(f"    {k:16} {v:,} chars")

    # `failed` cũng là chưa sẵn sàng, không chỉ `blocked`: một story trượt
    # cổng mà lệnh trả 0 thì CI báo xanh trên một sprint đang hỏng.
    stuck = state.by_status(StoryStatus.BLOCKED) + state.by_status(StoryStatus.FAILED)
    if stuck:
        print(f"\n✗ {len(stuck)} stories not passing:")
        for r in stuck[:10]:
            print(f"    {r.id:16} {r.status:8} {r.blocked_reason or '(unknown reason)'}")
        return EXIT_NOT_READY
    return EXIT_OK


def _readiness_blocked(args) -> bool:
    """Cổng `readiness` chứ không phải `stories`: nó gắn vào **cả** chỉ mục
    story lẫn hợp đồng thị giác. Chỉ đòi `stories` thì một story khai
    `screens` vẫn chạy được khi chưa có mockup nào — rồi trượt ở cổng vì
    "chưa đối chiếu", sau khi đã tiêu tiền viết xong code."""
    from ..control.approvals import Gate

    store = _approvals(args)
    blocking = [g.value for g in store.blocking(Gate.READINESS)]
    if store.status(Gate.READINESS) is not Status.APPROVED:
        blocking.append(Gate.READINESS.value)
    if blocking and not args.force:
        print(f"✗ gate not approved: {', '.join(blocking)}", file=sys.stderr)
        print(f"  aisef review {blocking[0]}", file=sys.stderr)
        return True
    return False


def cmd_run(args) -> int:
    """Chạy đợt: epic tuần tự, trong epic chạy song song theo đợt.

    `--verify-only --story S`: lượt kiểm-lại trên ứng viên đã đóng băng
    (ADR-004 R13) — cùng cổng, cùng đường merge, không có phiên developer.
    """
    from ..phases.run import run_sprint, run_verify_only

    verify_only = getattr(args, "verify_only", False)
    story = getattr(args, "story", "")
    repeat = getattr(args, "repeat", 1)
    if verify_only and not story:
        print("✗ --verify-only requires --story: which story's candidate to re-check?", file=sys.stderr)
        return EXIT_USAGE
    if verify_only and args.no_isolate:
        print("✗ --verify-only checks HEAD of the story branch in a worktree — incompatible with --no-isolate",
              file=sys.stderr)
        return EXIT_USAGE
    if story and not verify_only:
        print("✗ --story only works with --verify-only (to run a regular story: use --epic)", file=sys.stderr)
        return EXIT_USAGE
    if repeat < 1:
        print(f"✗ --repeat must be >= 1, got {repeat}", file=sys.stderr)
        return EXIT_USAGE
    if repeat != 1 and not verify_only:
        print("✗ --repeat only works with --verify-only: repeat re-checks a frozen candidate, "
              "not a developer session", file=sys.stderr)
        return EXIT_USAGE

    if _readiness_blocked(args):
        return EXIT_NOT_READY

    adapter, code = _client(args)
    if adapter is None:
        return code

    if verify_only:
        report = run_verify_only(
            args.project, adapter, story_id=story, config=Config.load(args.project),
            repeat=repeat,
        )
    else:
        report = run_sprint(
            args.project,
            adapter,
            config=Config.load(args.project),
            only_epic=args.epic,
            sequential=args.sequential,
            isolate=not args.no_isolate,
        )
    print(report.summary())
    if report.error:
        return EXIT_USAGE
    return EXIT_OK if report.ok else EXIT_NOT_READY


def cmd_improve(args) -> int:
    """Vòng cải tiến epic theo bằng chứng (ADR-004 R3).

    Một lần gọi chạy tối đa `--max-loops` vòng rồi thoát; chạy lại tiếp
    từ mốc `loops[]` cuối trong sổ hành vi — không daemon.
    """
    from ..phases.improve import improve

    if _readiness_blocked(args):
        return EXIT_NOT_READY
    adapter, code = _client(args)
    if adapter is None:
        return code

    project = Path(args.project)
    report = improve(
        project, adapter, args.epic,
        config=Config.load(project),
        max_loops=args.max_loops,
        auto=args.auto,
        has_ui=_project_has_ui(project),
    )
    print(report.summary())
    if report.error:
        return EXIT_USAGE
    return EXIT_OK if report.ok else EXIT_NOT_READY


def cmd_verify(args) -> int:
    """Chạy lại toàn bộ guard trên cây làm việc — hậu kiểm.

    Đây là lớp bảo đảm cho client không gắn được hook tiền kiểm: vi phạm
    vẫn bị bắt, chỉ là bắt **sau khi đã ghi** thay vì chặn lúc ghi.
    """
    from ..harness.guardrails import changed_files, check_completion, check_diff_scope
    from ..harness.observe import EvidenceStore

    project = Path(args.project).resolve()
    scope = [p.strip() for p in args.write_scope.split(",") if p.strip()]
    problems = []

    changed = changed_files(str(project))
    print(f"Changes in tree: {len(changed)} files")
    if scope:
        v = check_diff_scope(changed, scope)
        print(("  ✅ " if v.allowed else "  ✗ ") + (v.reason or "within scope"))
        if not v.allowed:
            problems.append("write scope")
    else:
        print("  ○ no --write-scope given, skipping scope check")

    if args.story:
        evidence = EvidenceStore(_artifact_root(args)).read(args.story)
        v = check_completion(evidence)
        print(("  ✅ " if v.allowed else "  ✗ ") + (v.reason or "tests green, no changes after"))
        if not v.allowed:
            problems.append("test")

    if problems:
        print(f"\n✗ post-check failed: {', '.join(problems)}", file=sys.stderr)
        return EXIT_NOT_READY
    print("\n✅ post-check passed")
    return EXIT_OK


def cmd_tool(args) -> int:
    """Chạy một tool của harness và ghi bằng chứng."""
    import os

    from ..harness.guardrails import ENV_STORY_ID
    from ..harness.tools import run_tool

    # Agent không cần biết mã story của chính nó: harness đã đặt vào môi
    # trường khi mở phiên.
    story = args.story or os.environ.get(ENV_STORY_ID, "")
    res = run_tool(
        args.name,
        args.project,
        story_id=story,
        artifact_root=_artifact_root(args) if story else None,
        config=Config.load(args.project),
    )
    print(res.summary())
    # Thứ tự có chủ đích (ADR-005 V11 A): kết luận máy đọc **trước** tail —
    # tên test đỏ ở 5 dòng đầu, agent không phải tự chạy lại runner để tìm.
    full = res.output()[0]
    if res.name == "test" and res.ran:
        from ..harness.testlog import parse as parse_testlog

        log = parse_testlog(full)
        if log.format:
            print(f"{len(log.passed)} passed · {len(log.failed)} failed · "
                  f"{len(log.skipped)} skipped ({log.format})")
            for tid in log.failed[:20]:
                print(f"  ✗ {tid}")
            if len(log.failed) > 20:
                print(f"  … and {len(log.failed) - 20} more failed tests")
    if full:
        print(res.tail(args.lines))
    total = len(full.splitlines())
    if total > args.lines:
        # Khai cắt: agent biết mình chưa thấy hết, và biết toàn văn ở đâu.
        full_ref = f" — full output: {_rel(res.log, args.project)}" if res.log else ""
        print(f"(truncated {total - args.lines}/{total} lines{full_ref})")
    if res.skipped:
        return EXIT_NOT_READY
    return EXIT_OK if res.ok else EXIT_NOT_READY


def _rel(path: str, project) -> str:
    """Đường dẫn ngắn khi tệp nằm trong dự án; tuyệt đối khi không (agent
    chạy trong worktree, sổ bằng chứng ở gốc chính)."""
    try:
        return str(Path(path).resolve().relative_to(Path(project).resolve()))
    except ValueError:
        return path


def cmd_qa(args) -> int:
    """Chạy bộ kiểm định của dự án.

    Mặc định chấm ở mức **trước triển khai**: loại chưa cấu hình cũng chặn,
    vì "chưa chạy" không phải là "đạt". `--story-level` hạ xuống mức story,
    nơi thiếu công cụ chỉ là cảnh báo.
    """
    from ..kit.detect_stack import detect_file
    from ..phases.qa import run_suite

    project = Path(args.project)
    has_ui = True
    req = project / "docs" / "requirements.md"
    if req.is_file():
        has_ui = detect_file(req).has_ui

    report = run_suite(
        project,
        config=Config.load(project),
        only=[k.strip() for k in args.only.split(",") if k.strip()] or None,
        has_ui=has_ui,
        story_id=args.story,
        artifact_root=_artifact_root(args) if args.story else None,
    )
    print(report.summary())

    ok = report.passed if args.story_level else report.release_ready
    if ok:
        print("\n✅ QA passed")
        return EXIT_OK
    return EXIT_NOT_READY


def cmd_devsecops(args) -> int:
    """Sinh quy trình CI (code) và bộ khung vận hành (model)."""
    from ..phases.deploy import generate

    adapter, code = _client(args)
    if adapter is None:
        return code

    report = generate(
        args.project,
        adapter,
        config=Config.load(args.project),
        # Mặc định là **tên lệnh trên PATH**, không phải đường dẫn tuyệt
        # đối của máy này: quy trình CI sinh ra sẽ chạy trên máy khác.
        aisef_bin=args.bin or "aisef",
        install_spec=args.install_spec,
        force=args.force,
    )
    print(report.summary())
    return EXIT_OK if report.ok else EXIT_NOT_READY


def _project_has_ui(project: Path) -> bool:
    """Dự án này có giao diện không — hỏi thứ đã **quyết**, không phải
    thứ được **gợi ý**.

    `detect_file(requirements.md)` chỉ đọc tài liệu yêu cầu ban đầu, nơi
    người viết thường không nêu tên framework. Tới lúc chấm cổng trước
    triển khai thì kiến trúc đã chốt và màn hình đã dựng — dùng chúng.
    Đo trên e9: ứng dụng 5 màn hình bị báo "dự án không có giao diện", và
    `e2e`/`accessibility` bị bỏ qua với một lý do sai sự thật.
    """
    from ..kit.detect_stack import detect_file

    root = project / "_bmad-output"
    contract = root / "design-contract.json"
    if contract.is_file():
        try:
            raw = json.loads(contract.read_text(encoding="utf-8"))
            if raw.get("screens"):
                return True
        except (OSError, json.JSONDecodeError):
            pass

    index = root / STORIES_INDEX
    if index.is_file():
        try:
            raw = json.loads(index.read_text(encoding="utf-8"))
            if any(s.get("screens") for s in raw.get("stories", [])):
                return True
        except (OSError, json.JSONDecodeError):
            pass

    req = project / "docs" / "requirements.md"
    return detect_file(req).has_ui if req.is_file() else True


def cmd_predeploy(args) -> int:
    """Chấm cổng trước triển khai."""
    from ..control.approvals import Gate
    from ..kit.detect_stack import detect_file
    from ..phases.deploy import pre_deploy

    project = Path(args.project)
    has_ui = _project_has_ui(project)

    report = pre_deploy(project, config=Config.load(project), has_ui=has_ui,
                        skip_qa=args.skip_qa, epic=args.epic)
    print(report.summary())
    path = report.write(_artifact_root(args))
    print(f"\nreport: {path}")
    if not report.passed:
        return EXIT_NOT_READY
    scope_note = f" (scope {args.epic})" if args.epic else ""
    print(f"Approve for deployment{scope_note}: aisef approve {Gate.PRE_DEPLOY.value}")
    return EXIT_OK


def cmd_evidence(args) -> int:
    """Tra một story hoặc một hành vi trong sổ hành vi (ADR-004 R6).

    Đây là nửa sau của progressive disclosure: prompt chỉ nhận **chỉ mục**,
    còn lịch sử nằm ở đây, tra khi cần chứ không nạp sẵn.
    """
    from ..control import ledger as ledger_mod

    root = _artifact_root(args)
    target = args.id
    if getattr(args, "link", ""):
        if not args.why.strip():
            print("✗ --link requires --why: a trace without a reason is not evidence", file=sys.stderr)
            return EXIT_NOT_READY
        import getpass
        import json
        import time

        path = root / ledger_mod.TRACE_FILE
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        data[target] = {"test_id": args.link, "why": args.why.strip(),
                        "by": args.by or getpass.getuser(),
                        "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"trace: {target} ← `{args.link}` ({path.name}); ledger reconciles on next read")
    led = ledger_mod.build(root)

    def show(b) -> None:
        print(f"\n{b.id} [{b.kind}] — {b.status.upper()}"
              + (f" · candidate {b.candidate[:7]}" if b.candidate else "")
              + (f" · regressed by {b.regressed_by}" if b.regressed_by else ""))
        for h in b.history:
            src = h.get("source") or {}
            note = src.get("test_id") or src.get("why") or src.get("screen") or src.get("qa_kind") or ""
            print(f"  {h['status']:<9} {h.get('story', ''):<14} {str(note)[:90]}")

    if target in led.stories:
        line = led.stories[target]
        v, g, r = led.counts_for(target)
        print(f"{line.id} · {line.status} · candidate {line.candidate[:7] or '—'} · "
              f"V{v} G{g} R{r} · {line.evidence_path}")
        for b in sorted(led.for_story(target), key=lambda b: b.id):
            show(b)
    elif target in led.behaviors:
        show(led.behaviors[target])
    else:
        print(f"✗ no story or behaviour named {target} in ledger. "
              f"See `{root.name}/INDEX.md` (aisef report regenerates it).", file=sys.stderr)
        return EXIT_NOT_READY

    if args.story:
        from ..harness.observe import NOTE, Event, EvidenceStore

        EvidenceStore(root).record(args.story, Event(
            kind=NOTE, name="evidence_lookup", detail={"id": target},
        ))
    return EXIT_OK


def cmd_ctx(args) -> int:
    """Bản đồ mã quanh phạm vi ghi (ADR-005 V7) — nửa sau của progressive
    disclosure như `evidence`: prompt nhận bản có trần, bản đầy đủ tra ở đây.
    Gọi trong phiên (có `AISEF_STORY_ID`) thì ghi `note:ctx_lookup` như
    `doc_lookup`, để cổng và báo cáo biết agent đã tra gì."""
    import os

    from ..harness import context as code_map
    from ..harness.guardrails import ENV_STORY_ID

    project = Path(args.project)
    root = _artifact_root(args)
    config = Config.load(project)
    session = os.environ.get(ENV_STORY_ID, "")
    story_id = args.story or session
    if args.file:
        seeds = [args.file]
    else:
        if not story_id:
            print("✗ need --story <id> or --file <path>", file=sys.stderr)
            return EXIT_USAGE
        from ..phases.run import load_plan

        plan = load_plan(root)
        story = plan.stories.get(story_id)
        if story is None:
            print(f"✗ no story {story_id} in index" + (f": {plan.error}" if plan.error else ""),
                  file=sys.stderr)
            return EXIT_NOT_READY
        seeds = code_map.seeds_for(story, project, artifact_root=root, config=config)
    text = code_map.repo_map(
        project, seeds, args.budget,
        command=str(config.get("context.map_provider", "") or ""), story_id=story_id,
    )
    print(text)
    if session:
        from ..harness.observe import NOTE, Event, EvidenceStore

        EvidenceStore(root).record(session, Event(
            kind=NOTE, name="ctx_lookup",
            detail={"story": story_id, "file": args.file, "budget": args.budget, "chars": len(text)},
        ))
    return EXIT_OK


def cmd_issues(args) -> int:
    """Bảng gap/hồi quy ra tệp (ADR-004 R12).

    Chỉ là một cách **đọc** sổ: không tạo issue ở đâu, không gọi mạng, không
    chạm cổng. Ai muốn đưa lên GitHub/Jira thì cầm CSV đi — kho này không
    biết tracker của dự án, và không nên biết.
    """
    from ..control import ledger as ledger_mod

    statuses = {s.strip().lower() for s in args.status.split(",") if s.strip()}
    unknown = statuses - {ledger_mod.VERIFIED, ledger_mod.GAP, ledger_mod.REOPENED}
    if unknown or not statuses:
        # Gõ sai trạng thái mà vẫn xuất tệp rỗng là lừa người đọc "không còn gap".
        print(f"✗ invalid --status: {', '.join(sorted(unknown)) or '(empty)'}. "
              f"Valid: gap, reopened, verified", file=sys.stderr)
        return EXIT_USAGE
    root = _artifact_root(args)
    rows = ledger_mod.build(root).issues(epic=args.epic, statuses=statuses)
    path = Path(args.out) if args.out else root / f"ISSUES.{args.format}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ledger_mod.issues_text(rows, args.format), encoding="utf-8")
    reopened = sum(1 for r in rows if r["status"] == ledger_mod.REOPENED)
    print(f"{path} · {len(rows)} behaviours ({reopened} regressions)")
    return EXIT_OK


def cmd_report(args) -> int:
    """Sinh báo cáo nghiệm thu từ bằng chứng đã có."""
    from ..control import ledger as ledger_mod
    from ..phases.report import build, write

    report = build(args.project)
    path = write(args.project, out=args.out or None)
    print(f"Report: {path}")
    print(f"  uncovered requirements: {len(report.uncovered)}")
    print(f"  stories with evidence: {len(report.stories)}")
    print(f"  total cost: ${report.total_cost_usd:.2f}")

    # Sổ hành vi + chỉ mục: chiếu lại từ bằng chứng mỗi lần, không tích luỹ.
    led = ledger_mod.build(_artifact_root(args))
    s = led.summary()
    print(f"  behaviour ledger: {s['verified']} verified · {s['gap']} gap · "
          f"{s['reopened']} reopened (resolved {s['resolved']}, "
          f"cross-story regressions {s['cross_reopens']})")
    print(f"  {led.write(_artifact_root(args))}\n  {led.index(_artifact_root(args))}")
    return EXIT_OK if not report.uncovered else EXIT_NOT_READY
