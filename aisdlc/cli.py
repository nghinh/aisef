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
from .control.design_contract import CONTRACT_FILE
from .control.state import StateStore, StoryStatus
from .harness.guardrails import GUARD_MATCHERS
from .harness.tools import aisdlc_command
from .phases.deploy import INSTALL_SPEC as DEPLOY_INSTALL_SPEC

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
    """Gốc artifact — **một** gốc cho cả dự án (bất biến 2).

    Agent chạy trong worktree của story, nên `--project .` ở đó trỏ vào
    worktree. Ghi bằng chứng vào đấy thì cổng đọc ở gốc chính không thấy
    gì, và story "chưa từng chạy test" dù nó vừa chạy.
    """
    from .control.worktree import main_repo

    return main_repo(args.project) / ARTIFACT_ROOT


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

    from .harness.browser import availability as browser_availability
    from .harness.tools import image_for

    browser_why = browser_availability(project)
    check(
        "playwright + chromium",
        not browser_why,
        "sẵn sàng" if not browser_why else f"{browser_why} — không trích được hợp đồng mockup",
        required=False,
    )

    lines.append("Dự án:")
    check("thư mục dự án", project.is_dir(), str(project))
    try:
        cfg_for_sandbox = Config.load(project)
        image = image_for(project, cfg_for_sandbox)
        use_docker = cfg_for_sandbox["sandbox.use_docker"]
    except ConfigError:
        image, use_docker = "?", True
    if not use_docker:
        # Đã tắt Docker thì bàn về ảnh là vô nghĩa; thứ người cần biết là
        # công cụ chạy thẳng trên máy, tức mức bảo đảm thấp hơn.
        check(
            "cách ly sandbox",
            False,
            "đã tắt Docker (sandbox.use_docker=false) — công cụ chạy thẳng "
            "trên máy, bằng chứng ghi degraded",
            required=False,
        )
    else:
        check(
            "ảnh sandbox",
            image != "alpine:latest",
            image + (" — không có công cụ của stack nào, test sẽ đỏ vì thiếu công cụ"
                     if image == "alpine:latest" else " (hợp stack)"),
            required=False,
        )
    req = project / "docs" / "requirements.md"
    check("docs/requirements.md", req.is_file(), str(req))

    # Hook sinh ra ≠ hook chạy. Story chạy trong worktree; worktree chỉ có
    # `.claude/` nếu dự án commit nó. Harness nay truyền `--settings` tường
    # minh (G4), nhưng thứ đó chỉ được chứng minh bằng hợp quy — ở đây nói
    # thẳng tình trạng để người đọc biết mình đang dựa vào lớp nào.
    plugin = project / ".opencode" / "plugin" / "aisdlc-guard.ts"
    if plugin.is_file():
        tracked = subprocess.run(
            ["git", "-C", str(project), "ls-files", "--error-unmatch", str(plugin)],
            capture_output=True, text=True,
        ).returncode == 0
        check(
            "plugin OpenCode trong worktree",
            tracked,
            "`.opencode/plugin` đã commit — worktree tự có plugin" if tracked else
            "`.opencode/plugin` chưa commit — worktree KHÔNG có plugin, OpenCode chạy "
            "story với zero guard (đo hợp quy 2026-09-05); commit `.opencode/` hoặc "
            "không dùng OpenCode cho `run`",
            required=False,
        )
    hook = project / ".claude" / "settings.json"
    if hook.is_file():
        tracked = subprocess.run(
            ["git", "-C", str(project), "ls-files", "--error-unmatch", str(hook)],
            capture_output=True, text=True,
        ).returncode == 0
        check(
            "hook trong worktree",
            tracked,
            "`.claude/settings.json` đã commit — worktree tự có hook" if tracked else
            "`.claude/settings.json` chưa commit — worktree không có hook; harness "
            "truyền `--settings` tường minh, cổng story mục \"guard có chạy\" sẽ "
            "trượt nếu hook không tới",
            required=False,
        )

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
        # Skill của framework nằm trong kho framework; dự án giữ một bản
        # sao. Sửa skill mà không cài lại thì agent vẫn chạy bản cũ, và
        # cách duy nhất phát hiện là ngồi so từng file.
        from .kit.install import OWN_SKILLS

        stale = []
        for own in sorted(OWN_SKILLS.glob("*/SKILL.md")) if OWN_SKILLS.is_dir() else []:
            copied = skills_dir / own.parent.name / "SKILL.md"
            if copied.is_file() and copied.read_bytes() != own.read_bytes():
                stale.append(own.parent.name)
        check(
            "skill framework cập nhật",
            not stale,
            "khớp bản gốc" if not stale
            else f"cũ hơn kho: {', '.join(stale)} — chạy `aisdlc setup`",
            required=False,
        )

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
        if artifact.name == CONTRACT_FILE:
            from .phases.mockup import describe_contract

            data = json.loads(artifact.read_text(encoding="utf-8"))
            print(f"\n— {len(data.get('screens', []))} màn hình —\n")
            print(describe_contract(data, artifact.parent))
            continue
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
    from .control.preflight import STORY_NOT_EXECUTABLE, check_stories_executable
    from .phases.run import load_plan

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
    from .harness.observe import AGENT_RUN, EvidenceStore

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

    from .kit import fetch

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
    # Không tự đoán đường dẫn: `aisdlc_command` đã biết ưu tiên tên trên PATH
    # (bản cài thật) rồi mới lùi về `bin/aisdlc` của kho nguồn.
    aisdlc_bin = args.bin or aisdlc_command()

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

    from .harness.guardrails import record_outcome, run_guard

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
            project_root=str(Path(args.project).resolve()),
            artifact_root=str(_artifact_root(args)),
        )
    except ValueError as e:
        print(f"guard: {e}", file=sys.stderr)
        return EXIT_OK

    # Guard tự ghi bằng chứng: chỗ duy nhất mọi client đều đi qua, nên
    # `guard_blocked` và `FILE_CHANGE` không còn phụ thuộc client có phát
    # luồng sự kiện hay không. Ghi hỏng không được làm hỏng phán quyết.
    try:
        record_outcome(
            args.kind, event, verdict, artifact_root=str(_artifact_root(args))
        )
    except OSError as e:
        print(f"guard: không ghi được bằng chứng ({e})", file=sys.stderr)

    if not verdict.allowed:
        print(verdict.reason, file=sys.stderr)
    return verdict.exit_code


# ------------------------------------------------------------------ lập kế hoạch


def cmd_plan(args) -> int:
    """Chạy chuỗi pha BMAD tới cổng đầu tiên chưa duyệt."""
    from .phases.plan import run_pipeline

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
    from .control.approvals import Gate
    from .phases.mockup import generate
    from .phases.plan import _pass_gate

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


# ------------------------------------------------------------------ hiện thực


def _client(args):
    """Adapter đã kiểm tên và tình trạng cài đặt. None nếu không dùng được."""
    from .clients.compile import ADAPTERS

    if args.client not in ADAPTERS:
        print(f"✗ client không hỗ trợ: {args.client}", file=sys.stderr)
        return None, EXIT_USAGE
    adapter = ADAPTERS[args.client]()
    if not adapter.available():
        print(f"✗ chưa cài {args.client} trên máy này", file=sys.stderr)
        return None, EXIT_NOT_READY
    return adapter, EXIT_OK


def cmd_run(args) -> int:
    """Chạy đợt: epic tuần tự, trong epic chạy song song theo đợt."""
    from .control.approvals import Gate
    from .phases.run import run_sprint

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
    from .harness.guardrails import changed_files, check_completion, check_diff_scope
    from .harness.observe import EvidenceStore

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

    from .harness.guardrails import ENV_STORY_ID
    from .harness.tools import run_tool

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
    from .kit.detect_stack import detect_file
    from .phases.qa import run_suite

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
    from .phases.deploy import generate

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
    from .kit.detect_stack import detect_file

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
    from .control.approvals import Gate
    from .kit.detect_stack import detect_file
    from .phases.deploy import pre_deploy

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


def cmd_skill(args) -> int:
    """Dựng và soi sổ đăng ký skill (ADR-002). Chỉ đọc — không sửa dự án."""
    from .kit import registry as R
    from .kit import router as RT
    from .phases.run import load_plan

    project = Path(args.project)
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


def cmd_report(args) -> int:
    """Sinh báo cáo nghiệm thu từ bằng chứng đã có."""
    from .phases.report import build, write

    report = build(args.project)
    path = write(args.project, out=args.out or None)
    print(f"Báo cáo: {path}")
    print(f"  yêu cầu chưa phủ: {len(report.uncovered)}")
    print(f"  story có bằng chứng: {len(report.stories)}")
    print(f"  tổng chi phí: ${report.total_cost_usd:.2f}")
    return EXIT_OK if not report.uncovered else EXIT_NOT_READY


# ------------------------------------------------------------------ đầu vào


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aisdlc",
        description="AI-SDLC — điều phối vòng đời phát triển bằng agent",
    )
    p.add_argument("--project", default=".", help="thư mục dự án (mặc định: thư mục hiện tại)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("setup", help="dò stack và nạp skill vào dự án")
    s.add_argument("--references", default="", help="thư mục chứa kho skill (mặc định: cache người dùng)")
    s.add_argument("--no-fetch", action="store_true",
                   help="không tự lấy nguồn về; chỉ dùng những gì đã có trên đĩa")
    s.add_argument("--dry-run", action="store_true", help="chỉ in kế hoạch, không ghi")
    s.set_defaults(func=cmd_setup)

    sub.add_parser("doctor", help="kiểm tra môi trường").set_defaults(func=cmd_doctor)
    sub.add_parser("init", help="ghi .ai/config.json mặc định").set_defaults(func=cmd_init)
    sub.add_parser("gates", help="bảng trạng thái 8 cổng").set_defaults(func=cmd_gates)
    sub.add_parser("status", help="tiến độ story, chi phí").set_defaults(func=cmd_status)
    sk = sub.add_parser("skill", help="sổ đăng ký skill: dựng, soi, định tuyến thử")
    sk.add_argument("--story", default="", help="in skill được định tuyến cho story này")
    sk.set_defaults(func=cmd_skill)

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

    mk = sub.add_parser("mockup", help="dựng mockup từng màn hình + hợp đồng thị giác")
    mk.add_argument("--client", default="claude", help="claude | opencode")
    mk.add_argument("--auto-approve", default="", help="'all' hoặc danh sách cổng")
    mk.add_argument("--force", action="store_true", help="dựng lại cả màn hình đã có")
    mk.add_argument("--only", default="", help="chỉ dựng các screen_id này")
    mk.set_defaults(func=cmd_mockup)

    r2 = sub.add_parser("run", help="chạy đợt: epic tuần tự, story song song")
    r2.add_argument("--client", default="claude", help="claude | opencode")
    r2.add_argument("--epic", default="", help="chỉ chạy một epic")
    r2.add_argument("--sequential", action="store_true", help="tắt chạy song song")
    r2.add_argument("--no-isolate", action="store_true", help="chạy thẳng trong dự án, không worktree")
    r2.add_argument("--force", action="store_true", help="chạy dù cổng stories chưa duyệt")
    r2.set_defaults(func=cmd_run)

    v = sub.add_parser("verify", help="chạy lại guard trên cây làm việc (hậu kiểm)")
    v.add_argument("--write-scope", default="", help="phạm vi ghi của story, ngăn bởi dấu phẩy")
    v.add_argument("--story", default="", help="mã story để kiểm bằng chứng test")
    v.set_defaults(func=cmd_verify)

    t = sub.add_parser("tool", help="chạy tool của harness và ghi bằng chứng")
    t.add_argument("name", help="test | lint | sast")
    t.add_argument("--story", default="", help="mã story để ghi bằng chứng")
    t.add_argument("--lines", type=int, default=40, help="số dòng output hiển thị")
    t.set_defaults(func=cmd_tool)

    q = sub.add_parser("qa", help="chạy bộ kiểm định (unit · sit · e2e · bảo mật …)")
    q.add_argument("--only", default="", help="chỉ chạy các loại này")
    q.add_argument("--story", default="", help="mã story để ghi bằng chứng")
    q.add_argument("--story-level", action="store_true",
                   help="chấm ở mức story: thiếu công cụ chỉ cảnh báo")
    q.set_defaults(func=cmd_qa)

    d = sub.add_parser("devsecops", help="sinh CI + Dockerfile + triển khai + runbook")
    d.add_argument("--client", default="claude", help="claude | opencode")
    d.add_argument("--install-spec", default=DEPLOY_INSTALL_SPEC,
                   help="thứ CI sẽ `pip install` — tên gói PyPI, git+URL, "
                        "hay đường dẫn tới bản sao kho nguồn")
    d.add_argument("--bin", default="", help="đường dẫn lệnh aisdlc dùng trong CI")
    d.add_argument("--force", action="store_true", help="sinh lại dù đã có")
    d.set_defaults(func=cmd_devsecops)

    pd = sub.add_parser("pre-deploy", help="chấm cổng trước triển khai")
    pd.add_argument("--skip-qa", action="store_true", help="bỏ qua bộ kiểm định (chỉ để soi nhanh)")
    pd.set_defaults(func=cmd_predeploy)

    rp = sub.add_parser("report", help="báo cáo nghiệm thu từ bằng chứng")
    rp.add_argument("--out", default="", help="đường dẫn file ra")
    rp.set_defaults(func=cmd_report)

    aa = sub.add_parser("auto-approve", help="tự duyệt (ghi dấu auto)")
    aa.add_argument("gates", help="'all' hoặc danh sách ngăn bởi dấu phẩy")
    aa.set_defaults(func=cmd_auto_approve)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Tuyệt đối hoá **một lần, ở cửa vào**. Mặc định `--project .` làm
    # `Path(".").name` thành chuỗi rỗng, và mỗi pha lại dùng nó một kiểu:
    # báo cáo nghiệm thu ra tiêu đề cụt, prompt devsecops trượt vì biến
    # rỗng. Vá từng chỗ dùng là vá triệu chứng — chín chỗ trong mã làm
    # `Path(project)` mà không resolve, và chỗ thứ mười sẽ lại hỏng.
    args.project = str(Path(args.project).resolve())
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
