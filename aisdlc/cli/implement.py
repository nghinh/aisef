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
        print("Chưa có story nào được đăng ký.")
        return EXIT_OK

    totals = state.totals()
    total = len(state.stories)
    done = totals[StoryStatus.DONE.value]

    print(f"Tiến độ: {done}/{total} story xong")
    # `verified` = qua cổng, chưa lên nhánh chính (merge đụng ở lượt trước).
    # Không nói ra thì người đọc tưởng code đã ở main.
    chua_merge = [r.id for r in state.by_status(StoryStatus.VERIFIED)]
    if chua_merge:
        print(f"⚠️  {len(chua_merge)} story xong nhưng chưa merge vào nhánh chính: "
              f"{', '.join(chua_merge[:5])} — chạy lại `aisdlc run` để merge")
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

    # Ngữ cảnh nạp mỗi story — đo thật từ evidence, thay cho knob
    # `story.max_context_tokens` chưa từng có mã đọc. Cùng ngưỡng 3× trung
    # vị như chi phí: story nạp gấp ba story khác là dấu hiệu chẻ sai.
    from ..harness.observe import AGENT_RUN, EvidenceStore

    ev_store = EvidenceStore(_artifact_root(args))
    nap = {}
    for sid in ev_store.stories():
        sizes = [int(e.detail.get("prompt_chars") or 0)
                 for e in ev_store.read(sid).of(AGENT_RUN)]
        if any(sizes):
            nap[sid] = max(sizes)
    if len(nap) >= 3:
        trung_vi = sorted(nap.values())[len(nap) // 2]
        phinh = {k: v for k, v in nap.items() if v > cfg["cost.warn_multiple"] * trung_vi}
        if phinh:
            print(f"⚠️  {len(phinh)} story nạp ngữ cảnh hơn {cfg['cost.warn_multiple']}× trung vị "
                  f"({trung_vi:,} ký tự):")
            for k, v in sorted(phinh.items(), key=lambda kv: -kv[1])[:5]:
                print(f"    {k:16} {v:,} ký tự")

    # `failed` cũng là chưa sẵn sàng, không chỉ `blocked`: một story trượt
    # cổng mà lệnh trả 0 thì CI báo xanh trên một sprint đang hỏng.
    stuck = state.by_status(StoryStatus.BLOCKED) + state.by_status(StoryStatus.FAILED)
    if stuck:
        print(f"\n✗ {len(stuck)} story chưa qua được:")
        for r in stuck[:10]:
            print(f"    {r.id:16} {r.status:8} {r.blocked_reason or '(không rõ lý do)'}")
        return EXIT_NOT_READY
    return EXIT_OK


def cmd_run(args) -> int:
    """Chạy đợt: epic tuần tự, trong epic chạy song song theo đợt."""
    from ..control.approvals import Gate
    from ..phases.run import run_sprint

    # Cổng `readiness` chứ không phải `stories`: nó gắn vào **cả** chỉ mục
    # story lẫn hợp đồng thị giác. Chỉ đòi `stories` thì một story khai
    # `screens` vẫn chạy được khi chưa có mockup nào — rồi trượt ở cổng vì
    # "chưa đối chiếu", sau khi đã tiêu tiền viết xong code.
    store = _approvals(args)
    blocking = [g.value for g in store.blocking(Gate.READINESS)]
    if store.status(Gate.READINESS) is not Status.APPROVED:
        blocking.append(Gate.READINESS.value)
    if blocking and not args.force:
        print(f"✗ cổng chưa duyệt: {', '.join(blocking)}", file=sys.stderr)
        print(f"  aisdlc review {blocking[0]}", file=sys.stderr)
        return EXIT_NOT_READY

    adapter, code = _client(args)
    if adapter is None:
        return code

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
    print(f"Thay đổi trong cây: {len(changed)} file")
    if scope:
        v = check_diff_scope(changed, scope)
        print(("  ✅ " if v.allowed else "  ✗ ") + (v.reason or "nằm trong phạm vi"))
        if not v.allowed:
            problems.append("phạm vi ghi")
    else:
        print("  ○ chưa truyền --write-scope, bỏ qua kiểm phạm vi")

    if args.story:
        evidence = EvidenceStore(_artifact_root(args)).read(args.story)
        v = check_completion(evidence)
        print(("  ✅ " if v.allowed else "  ✗ ") + (v.reason or "test xanh, không sửa gì sau đó"))
        if not v.allowed:
            problems.append("test")

    if problems:
        print(f"\n✗ hậu kiểm không đạt: {', '.join(problems)}", file=sys.stderr)
        return EXIT_NOT_READY
    print("\n✅ hậu kiểm đạt")
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
    if res.tail():
        print(res.tail(args.lines))
    if res.skipped:
        return EXIT_NOT_READY
    return EXIT_OK if res.ok else EXIT_NOT_READY


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
        print("\n✅ kiểm định đạt")
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
        aisdlc_bin=args.bin or "aisdlc",
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
                        skip_qa=args.skip_qa)
    print(report.summary())
    path = report.write(_artifact_root(args))
    print(f"\nbáo cáo: {path}")
    if not report.passed:
        return EXIT_NOT_READY
    print(f"Duyệt để triển khai: aisdlc approve {Gate.PRE_DEPLOY.value}")
    return EXIT_OK


def cmd_report(args) -> int:
    """Sinh báo cáo nghiệm thu từ bằng chứng đã có."""
    from ..phases.report import build, write

    report = build(args.project)
    path = write(args.project, out=args.out or None)
    print(f"Báo cáo: {path}")
    print(f"  yêu cầu chưa phủ: {len(report.uncovered)}")
    print(f"  story có bằng chứng: {len(report.stories)}")
    print(f"  tổng chi phí: ${report.total_cost_usd:.2f}")
    return EXIT_OK if not report.uncovered else EXIT_NOT_READY
