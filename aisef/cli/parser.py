"""CLI entry point: build the argument parser and ``main`` function.

This is the only place that knows command names and flags;
each command lives in its own phase module.
"""

from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path

from ..config import ConfigError
from ..harness.guardrails import GUARD_MATCHERS
from ..phases.deploy import INSTALL_SPEC as DEPLOY_INSTALL_SPEC
from ._common import EXIT_USAGE, _gate_arg
from .closure import cmd_closure
from .dashboard import cmd_dashboard
from .doctor import cmd_doctor
from .harness import cmd_baseline, cmd_compile, cmd_doc, cmd_gate, cmd_guard, cmd_init, cmd_replay, cmd_setup, cmd_skill
from .implement import (
    cmd_cost,
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


class _Parser(argparse.ArgumentParser):
    """`ArgumentParser` thoát **1** khi gõ sai, không phải 2.

    Quy ước thoát của CLI này (README): `0` xong · `1` gõ sai · `2` **chưa
    sẵn sàng** (cổng chưa duyệt, doctor chưa đạt) — để CI phân biệt "hỏng" với
    "chưa tới lúc". Mặc định của argparse là 2, nên một lỗi gõ lệnh đọc thành
    "chưa tới lúc" và script CI đi tiếp như thể mọi thứ bình thường. Đo
    13/09/2026: `aisef evidence` thiếu tham số thoát 2.
    """

    def error(self, message: str):   # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    from .. import __version__

    p = _Parser(
        prog="aisef",
        description="AISEF — orchestrate the AI-assisted software development lifecycle",
    )
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--project", default=".", help="project directory (default: current directory)")
    sub = p.add_subparsers(dest="command", required=True, parser_class=_Parser)

    from .memory import cmd_memory
    mem = sub.add_parser("memory", help="experimental scoped advisory memory (default off)")
    mem.add_argument("action", choices=("status", "recall", "search", "show", "capture", "consolidate", "audit", "forget", "providers"))
    mem.add_argument("value", nargs="?", default="")
    mem.add_argument("--story", default="")
    mem.add_argument("--role", choices=("developer", "reviewer", "security", "designer"), default="developer")
    mem.add_argument("--tool", default="*")
    mem.add_argument("--json", action="store_true")
    mem.set_defaults(func=cmd_memory)

    s = sub.add_parser("setup", help="detect stack and install skills into the project")
    s.add_argument("--references", default="", help="directory containing skill sources (default: user cache)")
    s.add_argument("--no-fetch", action="store_true",
                   help="do not fetch sources; use only what is already on disk")
    s.add_argument("--dry-run", action="store_true", help="print the plan without writing files")
    s.set_defaults(func=cmd_setup)

    sub.add_parser("doctor", help="check environment and prerequisites").set_defaults(func=cmd_doctor)
    s_init = sub.add_parser("init", help="write default .ai/config.json")
    s_init.add_argument("--stack", choices=["react", "python", "go", "node"], default="",
                        help="generate config tailored to this stack (test/lint/sandbox)")
    s_init.set_defaults(func=cmd_init)
    sub.add_parser("gates", help="show gate status table").set_defaults(func=cmd_gates)
    st = sub.add_parser("status", help="show story progress and cost")
    st.add_argument("--attempts", action="store_true",
                    help="where attempts ended: which gate check blocked them, which never reached the gate")
    st.set_defaults(func=cmd_status)
    ch = sub.add_parser("change", help="post-release change: record FR, stale PRD downward, generate delta stories")
    ch.add_argument("requirement", help="requirement ID, e.g. FR-3")
    ch.add_argument("description", help="change description — becomes acceptance criteria for the delta story")
    ch.set_defaults(func=cmd_change)

    bl = sub.add_parser("baseline", help="build baseline for brownfield projects: analyze existing codebase")
    bl.add_argument("--provider", default="", help="graphify | basic | auto (default)")
    bl.add_argument("--force", action="store_true", help="build baseline even for greenfield projects")
    bl.add_argument("--incremental", action="store_true", help="update graph without rebuilding baseline")
    bl.set_defaults(func=cmd_baseline)

    dc = sub.add_parser("doc", help="look up library documentation on demand (context7, cached)")
    dc.add_argument("package", help="package/library name, e.g. vitest, react, fastapi")
    dc.add_argument("--topic", default="", help="topic to look up, e.g. coverage, hooks")
    dc.add_argument("--tokens", type=int, default=2500)
    dc.add_argument("--story", default="", help="record doc_lookup evidence for this story")
    dc.set_defaults(func=cmd_doc)

    sk = sub.add_parser("skill", help="skill registry: build, inspect, test routing")
    sk.add_argument("--story", default="", help="print skill routed for this story")
    sk.add_argument("--scan", action="store_true",
                    help="scan SKILL.md with model (read-only, no tools) for injection directives — S6")
    sk.add_argument("--client", default="claude", help="claude | opencode (for --scan)")
    sk.add_argument("--batch", type=int, default=8, help="skills per scan session")
    sk.set_defaults(func=cmd_skill)

    r = sub.add_parser("review", help="view artifact for a gate")
    r.add_argument("gate", type=_gate_arg)
    r.add_argument("--lines", type=int, default=60, help="lines to display")
    r.set_defaults(func=cmd_review)

    a = sub.add_parser("approve", help="approve a gate")
    a.add_argument("gate", type=_gate_arg)
    a.add_argument("--note", default="")
    a.add_argument("--force", action="store_true", help="approve even if prior gate is incomplete")
    a.set_defaults(func=cmd_approve)

    j = sub.add_parser("reject", help="reject a gate with a note")
    j.add_argument("gate", type=_gate_arg)
    j.add_argument("--note", required=True, help="what needs fixing — required")
    j.set_defaults(func=cmd_reject)

    c = sub.add_parser("compile", help="generate client configuration (hooks, plugins)")
    c.add_argument("--client", default="all", help="claude | opencode | all")
    c.add_argument("--bin", default="", help="path to aisef binary used in hooks")
    c.set_defaults(func=cmd_compile)

    gt = sub.add_parser("gate", help="re-score story gates on recorded evidence "
                                     "(ADR-005 V4) — current rules, prior reviewer notes, no model calls")
    gt.add_argument("story", nargs="?", default="", help="story ID; omit when using --all")
    gt.add_argument("--replay", action="store_true",
                    help="re-evaluate each round with `gate:input` using current gate.evaluate, "
                         "print diff against recorded `gate:verdict`")
    gt.add_argument("--attempt", type=int, default=0, help="only this attempt (default: all)")
    gt.add_argument("--all", action="store_true", help="all stories with evidence")
    gt.add_argument("--waive-review", action="store_true",
                    help="record your override of a review-only block at the story's current "
                         "candidate; needs --reason, refuses inside an agent session")
    gt.add_argument("--reason", default="",
                    help="why the review block is wrong — recorded in evidence with your name")
    gt.set_defaults(func=cmd_gate)

    # `guard` **không** dùng `_Parser`: xem `_GuardParser` — hook coi mã thoát
    # khác 2 là "không chặn", nên lỗi gõ ở đây phải chặn, không được cho qua.
    g = sub.add_parser("guard", help="run guard on a hook event (reads stdin)")
    g.error = types.MethodType(_guard_error, g)      # type: ignore[method-assign]
    g.add_argument("kind", choices=sorted(GUARD_MATCHERS))
    g.set_defaults(func=cmd_guard)

    pl = sub.add_parser("plan", help="run BMAD phase chain up to the first unapproved gate")
    pl.add_argument("--client", default="claude", help="claude | opencode")
    pl.add_argument("--auto-approve", default="", help="'all' or comma-separated gate list")
    pl.add_argument("--force", action="store_true", help="re-run even if phase already has artifacts")
    pl.set_defaults(func=cmd_plan)

    mk = sub.add_parser("mockup", help="generate screen mockups + visual design contracts")
    mk.add_argument("--client", default="claude", help="claude | opencode")
    mk.add_argument("--auto-approve", default="", help="'all' or comma-separated gate list")
    mk.add_argument("--force", action="store_true", help="regenerate even if screens already exist")
    mk.add_argument("--only", default="", help="only build these screen_ids")
    mk.set_defaults(func=cmd_mockup)

    r2 = sub.add_parser("run", help="execute a wave: epics sequentially, stories in parallel")
    r2.add_argument("--client", default="claude", help="claude | opencode")
    r2.add_argument("--epic", default="", help="run only this epic")
    r2.add_argument("--sequential", action="store_true", help="disable parallel execution")
    r2.add_argument("--no-isolate", action="store_true", help="run directly in project, no worktree")
    r2.add_argument("--force", action="store_true", help="run even if stories gate is unapproved")
    r2.add_argument("--verify-only", action="store_true",
                    help="re-verify frozen candidate of --story (HEAD of story branch): "
                         "no developer session, only re-run failing/missing checks, keep "
                         "review on same SHA; does not count toward run.max_retries (ADR-004 R13)")
    r2.add_argument("--story", default="", help="story to re-verify — required with --verify-only")
    r2.add_argument("--repeat", type=int, default=1, metavar="K",
                    help="with --verify-only: run each check K times on the same SHA; tests that "
                         "flip results between runs → gate records UNRUNNABLE 'flaky' naming them, "
                         "not a failure (error 22: e2e sensitive to machine load). Default 1")
    r2.set_defaults(func=cmd_run)

    im = sub.add_parser("improve", help="evidence-driven improvement loop for an epic: QA → behaviour ledger → "
                                        "one fix story → run → QA; stops by code (ADR-004 R3)")
    im.add_argument("--epic", required=True, help="epic to improve, e.g. EPIC-01")
    im.add_argument("--max-loops", type=int, default=0,
                    help="max loops for the epic, including already-run loops (default: improve.max_loops)")
    im.add_argument("--auto", action="store_true",
                    help="skip human `improve` gate before loop >= 2 (5 stop conditions still apply)")
    im.add_argument("--client", default="claude", help="claude | opencode")
    im.add_argument("--force", action="store_true", help="run even if readiness gate is unapproved")
    im.set_defaults(func=cmd_improve)

    v = sub.add_parser("verify", help="re-run guards on the working tree (post-check)")
    v.add_argument("--write-scope", default="", help="story write scope, comma-separated")
    v.add_argument("--story", default="", help="story ID for checking test evidence")
    v.set_defaults(func=cmd_verify)

    t = sub.add_parser("tool", help="run a harness tool and record evidence")
    t.add_argument("name", help="test | lint | sast")
    t.add_argument("--story", default="", help="story ID for recording evidence")
    t.add_argument("--lines", type=int, default=40, help="output lines to display")
    t.set_defaults(func=cmd_tool)

    q = sub.add_parser("qa", help="run the test suite (unit, sit, e2e, security, ...)")
    q.add_argument("--only", default="", help="run only these types")
    q.add_argument("--story", default="", help="story ID for recording evidence")
    q.add_argument("--story-level", action="store_true",
                   help="score at story level: missing tools only warn")
    q.set_defaults(func=cmd_qa)

    d = sub.add_parser("devsecops", help="generate CI + Dockerfile + deployment + runbook")
    d.add_argument("--client", default="claude", help="claude | opencode")
    d.add_argument("--install-spec", default=DEPLOY_INSTALL_SPEC,
                   help="what CI will `pip install` — PyPI package name, git+URL, "
                        "or path to source checkout")
    d.add_argument("--bin", default="", help="path to aisef binary used in CI")
    d.add_argument("--force", action="store_true", help="regenerate even if files already exist")
    d.set_defaults(func=cmd_devsecops)

    pd = sub.add_parser("pre-deploy", help="score pre-deployment gate")
    pd.add_argument("--skip-qa", action="store_true", help="skip test suite (quick inspection only)")
    pd.add_argument("--epic", default="", metavar="EPIC",
                    help="acceptance scope: score only stories from this epic; out-of-scope stories "
                         "are listed as 'out of acceptance scope' (not incomplete, not missing)")
    pd.set_defaults(func=cmd_predeploy)

    ev = sub.add_parser("evidence", help="look up history for a story or behaviour in the ledger")
    ev.add_argument("id", help="story ID (STORY-01-04) or behaviour ID (AC-STORY-01-04-2, FR-3, qa:e2e, mockup:notes-list)")
    ev.add_argument("--story", default="", help="record evidence_lookup evidence for this story")
    ev.add_argument("--link", default="", metavar="TEST_ID",
                    help="declare traceability: this existing test proves the behaviour (metadata edit, "
                         "not code — ledger still requires green test at landed candidate); requires --why")
    ev.add_argument("--why", default="", help="why the existing test is sufficient (recorded with user and date)")
    ev.add_argument("--by", default="", help="who declared it (default: system user)")
    ev.set_defaults(func=cmd_evidence)

    cx = sub.add_parser("ctx", help="code map around a story's write scope — full, untruncated "
                                    "(ADR-005 V7; the `repo_map` prompt slot is the capped version)")
    cx.add_argument("--story", default="", help="story ID (default: AISEF_STORY_ID from session)")
    cx.add_argument("--file", default="", help="map around a file/directory instead of story scope")
    cx.add_argument("--budget", type=int, default=0, help="character cap; 0 = no truncation")
    cx.set_defaults(func=cmd_ctx)

    iss = sub.add_parser("issues", help="export gap/regression table from behaviour ledger "
                                        "(ADR-004 R12) — for tracking, does not touch gates")
    iss.add_argument("--format", default="md", choices=("md", "csv"))
    iss.add_argument("--epic", default="", help="only behaviours from this epic, e.g. EPIC-01")
    iss.add_argument("--status", default="gap,reopened",
                     help="statuses to include, comma-separated: gap | reopened | verified")
    iss.add_argument("--out", default="", help="output file (default: _bmad-output/ISSUES.md|csv)")
    iss.set_defaults(func=cmd_issues)

    rp = sub.add_parser("report", help="generate acceptance report from evidence")
    rp.add_argument("--out", default="", help="output file path")
    rp.set_defaults(func=cmd_report)

    ct = sub.add_parser("cost", help="attribute spend to outcomes: net VERIFIED behaviour "
                                     "per dollar (per input token when the provider prices "
                                     "nothing), split by attempt outcome (ADR-009 O4)")
    ct.add_argument("--out", default="", help="write the Markdown table to a file too")
    ct.set_defaults(func=cmd_cost)

    aa = sub.add_parser("auto-approve", help="auto-approve gates (records auto flag)")
    aa.add_argument("gates", help="'all' or comma-separated gate list")
    aa.set_defaults(func=cmd_auto_approve)

    db = sub.add_parser("dashboard", help="generate conformance HTML dashboard from evidence")
    db.add_argument("--out", default="", help="output file path (default: _bmad-output/dashboard.html)")
    db.add_argument("--projects", nargs="*", metavar="DIR",
                    help="additional project directories — merge evidence from multiple projects")
    db.set_defaults(func=cmd_dashboard)

    cl = sub.add_parser("closure", help="score the project closure gate (read-only, no model calls)")
    # Cùng lý do như `guard`: lệnh này có quy ước mã thoát riêng do hợp đồng
    # §4.3 định (0 đóng được · 1 bị chặn · 2 gõ sai), nên lỗi gõ phải ra 2 —
    # mặc định `_Parser` trả 1, và 1 ở đây đọc thành "bị chặn".
    cl.error = types.MethodType(_closure_error, cl)      # type: ignore[method-assign]
    cl.add_argument("--report", action="store_true",
                    help="regenerate docs/CLOSURE-REPORT.md from the last evaluation")
    cl.add_argument("--waive", default="", metavar="CRITERION",
                    help="record a waiver for a waiver-eligible criterion (requires --reason)")
    cl.add_argument("--reason", default="", help="why the gap is accepted — a waiver without a reason is not evidence")
    cl.add_argument("--approve", action="store_true",
                    help="owner signature; refuses unless every criterion is non-blocking")
    cl.add_argument("--note", default="", help="note recorded with --approve")
    cl.add_argument("--pin", action="store_true",
                    help="pin contract_sha256 (and the bench pre-registration) in docs/closure-gate.json")
    cl.add_argument("--force", action="store_true", help="re-pin over an existing pin")
    cl.add_argument("--corpus", default="", metavar="DIR",
                    help="G4 corpus path (default: the primary corpus beside the main checkout)")
    cl.set_defaults(func=cmd_closure)

    rpl = sub.add_parser("replay", help="re-score story gates on recorded evidence")
    rpl.add_argument("story", nargs="?", default="", help="story ID; omit with --all")
    rpl.add_argument("--attempt", type=int, default=0, help="only this attempt")
    rpl.add_argument("--all", action="store_true", help="all stories with evidence")
    rpl.set_defaults(func=cmd_replay)

    return p


def _speak_utf8() -> None:
    """Write UTF-8 whatever the console's code page says.

    Windows consoles default to a legacy code page (cp1252 on the CI runner),
    and this CLI prints `✅`, `·` and Vietnamese throughout. Two things break:
    the command dies with UnicodeEncodeError on its own output, and a parent
    process reading that output gets mojibake — `EPIC-01 · wave 1` arrived as
    `EPIC-01 ? wave 1` and every assertion on it failed. Encoding is a
    property of what we write, not of the terminal we happen to land in.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass       # not a real stream (captured in tests, piped oddly)


def _guard_error(self: argparse.ArgumentParser, message: str):
    """Lỗi gõ ở `aisef guard` phải **chặn**, không được cho qua.

    Hook của Claude Code đọc mã thoát: **2 = chặn**, mọi mã khác = không chặn.
    Nên quy ước "1 = gõ sai" của CLI này (xem `_Parser`) đúng ở mọi lệnh **trừ**
    lệnh này: một hook đã biên dịch với tên guard gõ sai hay đã đổi tên sẽ âm
    thầm tắt guard ấy. Đây đúng là bài học của lỗi 32 — guard không chạy được
    thì phải chặn.

    Đo 13/09/2026: sau khi sửa lỗi 81, `aisef guard <tên sai>` thoát 1 và hook
    coi là cho qua. Lỗ hổng do chính bản vá ấy mở ra, bắt được bằng cách chạy
    lệnh guard bằng tay.
    """

    self.exit(2, f"guard could not run ({message}) — blocking, not allowing\n")


def _closure_error(self: argparse.ArgumentParser, message: str):
    """`aisef closure` gõ sai phải thoát **2**, không phải 1.

    Hợp đồng đóng dự án (`docs/PROJECT-CLOSURE-GATE.md` §4.3) định mã thoát của
    riêng lệnh này: 0 đóng được · 1 **bị chặn** · 2 gõ sai. Nếu để mặc định
    `_Parser` (1 = gõ sai) thì một cờ viết sai đọc thành "cổng bị chặn" — một
    lỗi gõ lệnh biến thành một kết luận về dự án.
    """
    self.print_usage(sys.stderr)
    self.exit(2, f"{self.prog}: error: {message}\n")


def _cho_moi_lenh_nhan_project(p: argparse.ArgumentParser) -> None:
    """Cho `--project` đứng **sau** tên lệnh nữa, không chỉ trước.

    `aisef --project X gates` là dạng argparse mặc định; `aisef gates --project X`
    là dạng người thật gõ (và là dạng `git`/`docker` nhận). Trước 13/09/2026 dạng
    thứ hai ra lỗi gõ sai — đo được: `gates` trong thư mục rỗng thoát 2, cùng lệnh
    thêm `--project <dir>` thoát 1 vì argparse không nhận nổi cờ ấy.

    `default=SUPPRESS` là phần quan trọng: nếu để mặc định `"."` thì
    `aisef --project X gates` sẽ bị chính subparser ghi đè về `"."` — hỏng theo
    hướng im lặng, tệ hơn hẳn lỗi gõ sai.
    """
    for act in p._subparsers._group_actions if p._subparsers else ():   # noqa: SLF001
        for sub in getattr(act, "choices", {}).values():
            sub.add_argument("--project", default=argparse.SUPPRESS,
                             help="project directory (also accepted before the command)")


def main(argv: list[str] | None = None) -> int:
    _speak_utf8()
    parser = build_parser()
    _cho_moi_lenh_nhan_project(parser)
    args = parser.parse_args(argv)
    args.project = str(Path(args.project).resolve())
    try:
        return args.func(args)
    except ConfigError as e:
        print(f"✗ config: {e}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("\ncancelled", file=sys.stderr)
        return EXIT_USAGE
    except Exception as e:  # noqa: BLE001
        print(f"✗ {type(e).__name__}: {e}", file=sys.stderr)
        return EXIT_USAGE
