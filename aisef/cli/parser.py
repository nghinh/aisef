"""Cửa vào: dựng bộ phân tích tham số và hàm ``main``.

Đây là nơi duy nhất biết tên lệnh và cờ; mỗi lệnh nằm ở module pha của nó.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..config import ConfigError
from ..harness.guardrails import GUARD_MATCHERS
from ..phases.deploy import INSTALL_SPEC as DEPLOY_INSTALL_SPEC
from ._common import EXIT_USAGE, _gate_arg
from .dashboard import cmd_dashboard
from .doctor import cmd_doctor
from .harness import cmd_baseline, cmd_compile, cmd_doc, cmd_gate, cmd_guard, cmd_init, cmd_replay, cmd_setup, cmd_skill
from .implement import (
    cmd_ctx,
    cmd_devsecops,
    cmd_evidence,
    cmd_improve,
    cmd_issues,
    cmd_predeploy,
    cmd_qa,
    cmd_report,
    cmd_run,
    cmd_status,
    cmd_tool,
    cmd_verify,
)
from .plan import (
    cmd_approve,
    cmd_auto_approve,
    cmd_change,
    cmd_gates,
    cmd_mockup,
    cmd_plan,
    cmd_reject,
    cmd_review,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aisef",
        description="AISEF — điều phối vòng đời phát triển bằng agent",
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
    s_init = sub.add_parser("init", help="ghi .ai/config.json mặc định")
    s_init.add_argument("--stack", choices=["react", "python", "go", "node"], default="",
                        help="sinh cấu hình phù hợp cho stack (test/lint/sandbox)")
    s_init.set_defaults(func=cmd_init)
    sub.add_parser("gates", help="bảng trạng thái 8 cổng").set_defaults(func=cmd_gates)
    sub.add_parser("status", help="tiến độ story, chi phí").set_defaults(func=cmd_status)
    ch = sub.add_parser("change", help="thay đổi sau phát hành: ghi FR, stale PRD trở xuống, sinh story delta")
    ch.add_argument("requirement", help="mã yêu cầu, ví dụ FR-3")
    ch.add_argument("description", help="mô tả thay đổi — thành tiêu chí chấp nhận của story delta")
    ch.set_defaults(func=cmd_change)

    bl = sub.add_parser("baseline", help="dựng baseline cho brownfield: phân tích mã nguồn hiện tại")
    bl.add_argument("--provider", default="", help="graphify | basic | auto (mặc định)")
    bl.add_argument("--force", action="store_true", help="dựng baseline dù greenfield")
    bl.add_argument("--incremental", action="store_true", help="cập nhật graph mà không dựng lại baseline")
    bl.set_defaults(func=cmd_baseline)

    dc = sub.add_parser("doc", help="tra tài liệu thư viện theo yêu cầu (context7, có cache)")
    dc.add_argument("package", help="tên gói/thư viện, ví dụ vitest, react, fastapi")
    dc.add_argument("--topic", default="", help="chủ đề cần tra, ví dụ coverage, hooks")
    dc.add_argument("--tokens", type=int, default=2500)
    dc.add_argument("--story", default="", help="ghi bằng chứng doc_lookup cho story này")
    dc.set_defaults(func=cmd_doc)

    sk = sub.add_parser("skill", help="sổ đăng ký skill: dựng, soi, định tuyến thử")
    sk.add_argument("--story", default="", help="in skill được định tuyến cho story này")
    sk.add_argument("--scan", action="store_true",
                    help="quét SKILL.md bằng model (chỉ đọc, không tool) tìm chỉ dẫn tiêm — S6")
    sk.add_argument("--client", default="claude", help="claude | opencode (cho --scan)")
    sk.add_argument("--batch", type=int, default=8, help="số skill mỗi phiên quét")
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
    c.add_argument("--bin", default="", help="đường dẫn lệnh aisef dùng trong hook")
    c.set_defaults(func=cmd_compile)

    gt = sub.add_parser("gate", help="chấm lại cổng story trên bằng chứng đã ghi "
                                     "(ADR-005 V4) — luật hiện tại, lời reviewer cũ, không gọi model")
    gt.add_argument("story", nargs="?", default="", help="mã story; bỏ trống khi --all")
    gt.add_argument("--replay", action="store_true",
                    help="chấm lại từng lượt có `gate:input` bằng gate.evaluate hiện tại, "
                         "in diff so với `gate:verdict` đã ghi")
    gt.add_argument("--attempt", type=int, default=0, help="chỉ lượt này (mặc định: mọi lượt)")
    gt.add_argument("--all", action="store_true", help="mọi story có bằng chứng")
    gt.set_defaults(func=cmd_gate)

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
    r2.add_argument("--verify-only", action="store_true",
                    help="kiểm lại ứng viên đã đóng băng của --story (HEAD nhánh story): "
                         "không mở phiên developer, chỉ chạy lại phép kiểm ✗/thiếu, giữ rà "
                         "soát cùng SHA; không tính vào run.max_retries (ADR-004 R13)")
    r2.add_argument("--story", default="", help="story để kiểm lại — bắt buộc với --verify-only")
    r2.add_argument("--repeat", type=int, default=1, metavar="K",
                    help="với --verify-only: chạy mỗi phép kiểm K lần trên cùng SHA; test đổi kết "
                         "cục giữa các lần → cổng ghi UNRUNNABLE 'không ổn định' nêu tên, không "
                         "phải trượt (lỗi 22: e2e nhạy tải máy). Mặc định 1")
    r2.set_defaults(func=cmd_run)

    im = sub.add_parser("improve", help="vòng cải tiến epic theo bằng chứng: QA → sổ hành vi → "
                                        "một story sửa → run → QA; dừng bằng code (ADR-004 R3)")
    im.add_argument("--epic", required=True, help="epic cần cải tiến, ví dụ EPIC-01")
    im.add_argument("--max-loops", type=int, default=0,
                    help="số vòng tối đa cho epic, tính cả vòng đã chạy (mặc định improve.max_loops)")
    im.add_argument("--auto", action="store_true",
                    help="không dừng ở cổng người `improve` trước vòng ≥ 2 (5 điều kiện dừng vẫn chặn)")
    im.add_argument("--client", default="claude", help="claude | opencode")
    im.add_argument("--force", action="store_true", help="chạy dù cổng readiness chưa duyệt")
    im.set_defaults(func=cmd_improve)

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
    d.add_argument("--bin", default="", help="đường dẫn lệnh aisef dùng trong CI")
    d.add_argument("--force", action="store_true", help="sinh lại dù đã có")
    d.set_defaults(func=cmd_devsecops)

    pd = sub.add_parser("pre-deploy", help="chấm cổng trước triển khai")
    pd.add_argument("--skip-qa", action="store_true", help="bỏ qua bộ kiểm định (chỉ để soi nhanh)")
    pd.add_argument("--epic", default="", metavar="EPIC",
                    help="phạm vi nghiệm thu: chỉ chấm story của epic này; story ngoài phạm vi "
                         "được nêu tên là 'ngoài phạm vi nghiệm thu' (không xong, không thiếu)")
    pd.set_defaults(func=cmd_predeploy)

    ev = sub.add_parser("evidence", help="tra lịch sử một story hoặc một hành vi trong sổ")
    ev.add_argument("id", help="mã story (STORY-01-04) hoặc mã hành vi (AC-STORY-01-04-2, FR-3, qa:e2e, mockup:notes-list)")
    ev.add_argument("--story", default="", help="ghi bằng chứng evidence_lookup cho story này")
    ev.add_argument("--link", default="", metavar="TEST_ID",
                    help="khai truy vết: test có sẵn này chứng minh hành vi (sửa siêu dữ liệu, "
                         "không sửa mã — sổ vẫn đòi test xanh ở ứng viên đã landed); cần --why")
    ev.add_argument("--why", default="", help="vì sao test có sẵn chứng minh đủ (ghi kèm người, ngày)")
    ev.add_argument("--by", default="", help="người khai (mặc định: người dùng hệ thống)")
    ev.set_defaults(func=cmd_evidence)

    cx = sub.add_parser("ctx", help="bản đồ mã quanh phạm vi ghi của một story — đầy đủ, không cắt "
                                    "(ADR-005 V7; slot `repo_map` của prompt là bản có trần)")
    cx.add_argument("--story", default="", help="mã story (mặc định: AISEF_STORY_ID của phiên)")
    cx.add_argument("--file", default="", help="vẽ quanh một tệp/thư mục thay vì phạm vi story")
    cx.add_argument("--budget", type=int, default=0, help="trần ký tự; 0 = không cắt")
    cx.set_defaults(func=cmd_ctx)

    iss = sub.add_parser("issues", help="xuất bảng gap/hồi quy từ sổ hành vi ra tệp "
                                        "(ADR-004 R12) — để theo dõi, không chạm cổng")
    iss.add_argument("--format", default="md", choices=("md", "csv"))
    iss.add_argument("--epic", default="", help="chỉ hành vi thuộc epic này, ví dụ EPIC-01")
    iss.add_argument("--status", default="gap,reopened",
                     help="trạng thái lấy, ngăn bởi dấu phẩy: gap · reopened · verified")
    iss.add_argument("--out", default="", help="tệp ra (mặc định _bmad-output/ISSUES.md|csv)")
    iss.set_defaults(func=cmd_issues)

    rp = sub.add_parser("report", help="báo cáo nghiệm thu từ bằng chứng")
    rp.add_argument("--out", default="", help="đường dẫn file ra")
    rp.set_defaults(func=cmd_report)

    aa = sub.add_parser("auto-approve", help="tự duyệt (ghi dấu auto)")
    aa.add_argument("gates", help="'all' hoặc danh sách ngăn bởi dấu phẩy")
    aa.set_defaults(func=cmd_auto_approve)

    db = sub.add_parser("dashboard", help="báo cáo hợp quy HTML từ bằng chứng")
    db.add_argument("--out", default="", help="đường dẫn file ra (mặc định: _bmad-output/dashboard.html)")
    db.add_argument("--projects", nargs="*", metavar="DIR",
                    help="thư mục dự án bổ sung — gộp bằng chứng từ nhiều dự án")
    db.set_defaults(func=cmd_dashboard)

    rpl = sub.add_parser("replay", help="chấm lại cổng story trên bằng chứng đã ghi")
    rpl.add_argument("story", nargs="?", default="", help="mã story; bỏ trống với --all")
    rpl.add_argument("--attempt", type=int, default=0, help="chỉ lượt này")
    rpl.add_argument("--all", action="store_true", help="mọi story có bằng chứng")
    rpl.set_defaults(func=cmd_replay)

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
