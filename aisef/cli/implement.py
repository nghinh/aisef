"""Implementation and acceptance phase: ``status`` · ``run`` · ``verify`` ·
``tool`` · ``qa`` · ``devsecops`` · ``pre-deploy`` · ``report`` · ``cost``."""

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
    _ensure_git,
    _state,
)


def _attempt_breakdown(ev_store) -> tuple[dict, dict, dict]:
    """Mỗi lượt đã kết thúc **ở đâu** — đọc từ sổ bằng chứng, không đoán.

    ADR-009 §Open O4: sổ nói được một lần chạy tốn bao nhiêu, nhưng chưa nói
    được tiền ấy mua được gì. Bước đầu tiên là biết lượt nào chết vì cái gì:
    một lượt trượt vì test đỏ và một lượt trượt vì người rà soát chặn là hai
    bài toán khác nhau, và hai chi phí khác nhau để sửa.

    Ba giá trị trả về: lượt theo lớp, lượt theo mục cổng đã chặn, và số lượt
    của mỗi story. Lượt **không có** `gate:verdict` là lượt chưa bao giờ tới
    cổng — phân loại theo `exit_status` của phiên agent, và nếu cũng không có
    thì gọi tên là `unrecorded` chứ không suy đoán.
    """
    from ..harness.observe import AGENT_RUN, NOTE

    theo_lop: dict[str, int] = {}
    theo_muc: dict[str, int] = {}
    theo_story: dict[str, int] = {}
    for sid in ev_store.stories():
        ev = ev_store.read(sid)
        verdicts = [e for e in ev.of(NOTE) if e.name == "gate:verdict"]
        # Sổ bằng chứng chứa cả pha `plan-*` và `mockup-*`; chúng có phiên agent
        # nhưng **không đi qua cổng story**, nên đếm chúng vào đây thổi phồng
        # nhóm "chưa tới cổng" bằng những lượt vốn không thuộc về phép đo này.
        # Dấu hiệu đọc được từ dữ liệu: chỉ story mới có `gate:input`.
        if not verdicts and not any(e.name == "gate:input" for e in ev.of(NOTE)):
            continue
        for e in verdicts:
            lop = "passed" if e.ok else "gate"
            if not e.ok:
                for ten in (e.detail.get("failures") or ["unnamed"]):
                    theo_muc[str(ten)] = theo_muc.get(str(ten), 0) + 1
            theo_lop[lop] = theo_lop.get(lop, 0) + 1
            theo_story[sid] = theo_story.get(sid, 0) + 1
        # Lượt chưa tới cổng: phiên agent nhiều hơn số lần chấm.
        phien = [e for e in ev.of(AGENT_RUN) if str(e.detail.get("role") or "") in ("", "developer")]
        chua_toi_cong = max(0, len(phien) - len(verdicts))
        if chua_toi_cong:
            trang_thai = [str(e.detail.get("exit_status") or "unrecorded") for e in phien]
            for ten in trang_thai[-chua_toi_cong:]:
                lop = ten if ten != "ok" else "no gate verdict"
                theo_lop[lop] = theo_lop.get(lop, 0) + 1
                theo_story[sid] = theo_story.get(sid, 0) + 1
    return theo_lop, theo_muc, theo_story


def cmd_status(args) -> int:
    state = _state(args).load()
    cfg = Config.load(args.project)
    if cfg.get("memory.enabled", False):
        from ..memory import MemoryError, resolve
        try:
            provider, resolution = resolve(_artifact_root(args).parent, cfg)
            print("Memory (advisory): " + json.dumps({**provider.health(), **resolution}))
        except (MemoryError, OSError):
            print("Memory (advisory): unavailable; no implicit fallback")

    if getattr(args, "attempts", False):
        # Đọc thẳng sổ bằng chứng, **trước** lối ra sớm bên dưới: câu hỏi "lượt
        # đi đâu mất" trả lời được từ sổ kể cả khi tệp trạng thái đã bị dọn, và
        # một dự án đã chạy xong thường rơi đúng vào tình huống ấy.
        from ..harness.observe import EvidenceStore as _EvidenceStore

        lop, muc, story = _attempt_breakdown(_EvidenceStore(_artifact_root(args)))
        tong = sum(lop.values())
        if not tong:
            print("Attempts: no gate verdict recorded yet")
        else:
            print(f"Attempts: {tong} across {len(story)} stories")
            for k, n in sorted(lop.items(), key=lambda kv: -kv[1]):
                print(f"  {k:22} {n:3}  ({n / tong:.0%})")
            if muc:
                print("  blocked by:")
                for k, n in sorted(muc.items(), key=lambda kv: -kv[1]):
                    print(f"    {k:20} {n:3}")
            dat = [(sid, n) for sid, n in sorted(story.items(), key=lambda kv: -kv[1]) if n > 1]
            if dat:
                print("  attempts per story: " + " · ".join(f"{sid} {n}" for sid, n in dat[:6]))
        print()

    if not state.stories:
        print("No stories registered.")
        return EXIT_OK

    totals = state.totals()
    done = totals[StoryStatus.DONE.value]
    # Against the **plan**, not against what has been registered so far: a
    # `--epic` run registers one story at a time, and "0/1 stories done" reads
    # as a one-story project when fourteen are planned.
    from ..control.change import read_index

    planned = len(read_index(_artifact_root(args)).get("stories") or [])
    total = max(planned, len(state.stories))

    print(f"Progress: {done}/{total} stories done"
          + (f" ({total - len(state.stories)} not started)"
             if total > len(state.stories) else ""))
    # `verified` = passed gate, not yet on main branch (merge conflict in a
    # previous attempt).  Without saying so, the reader assumes code is on main.
    unmerged = [r.id for r in state.by_status(StoryStatus.VERIFIED)]
    if unmerged:
        print(f"⚠️  {len(unmerged)} stories done but not merged to main: "
              f"{', '.join(unmerged[:5])} — run `aisef run` again to merge")
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

    # Per-story context loaded — measured from evidence, replacing the
    # `story.max_context_tokens` knob that never had reading code.  Same 3x
    # median threshold as cost: a story loading 3x another is a split smell.
    from ..harness.observe import AGENT_RUN, SKILL_USE, EvidenceStore

    ev_store = EvidenceStore(_artifact_root(args))
    ctx_sizes = {}
    exit_counts: dict[str, int] = {}
    for sid in ev_store.stories():
        runs = ev_store.read(sid).of(AGENT_RUN)
        sizes = [int(e.detail.get("prompt_chars") or 0) for e in runs]
        if any(sizes):
            ctx_sizes[sid] = max(sizes)
        for e in runs:
            k = str(e.detail.get("exit_status") or "unrecorded")
            exit_counts[k] = exit_counts.get(k, 0) + 1
    # Per-round exit status (ADR-005 V11 B) — counted by `exit_status`
    # normalised by harness at write time.  Rounds recorded before this key
    # are "unrecorded": do not speculate on behalf of old evidence.
    if exit_counts:
        print("Agent runs: " + " · ".join(
            f"{k} {n}" for k, n in sorted(exit_counts.items(), key=lambda kv: -kv[1])))
    skill_counts: dict[str, int] = {}
    for sid in ev_store.stories():
        for e in ev_store.read(sid).of(SKILL_USE):
            skill_counts[e.name] = skill_counts.get(e.name, 0) + 1
    if skill_counts:
        print("Skill: " + " · ".join(
            f"{k} ×{n}" for k, n in sorted(skill_counts.items(), key=lambda kv: -kv[1])))

    if len(ctx_sizes) >= 3:
        median = sorted(ctx_sizes.values())[len(ctx_sizes) // 2]
        bloated = {k: v for k, v in ctx_sizes.items() if v > cfg["cost.warn_multiple"] * median}
        if bloated:
            print(f"⚠️  {len(bloated)} stories loaded context exceeding {cfg['cost.warn_multiple']}x median "
                  f"({median:,} chars):")
            for k, v in sorted(bloated.items(), key=lambda kv: -kv[1])[:5]:
                print(f"    {k:16} {v:,} chars")

    # `failed` is also not-ready, not just `blocked`: a story that fails
    # the gate while the command returns 0 makes CI report green on a broken sprint.
    stuck = state.by_status(StoryStatus.BLOCKED) + state.by_status(StoryStatus.FAILED)
    if stuck:
        print(f"\n✗ {len(stuck)} stories not passing:")
        for r in stuck[:10]:
            print(f"    {r.id:16} {r.status:8} {r.blocked_reason or '(unknown reason)'}")
        return EXIT_NOT_READY
    return EXIT_OK


def _readiness_blocked(args) -> bool:
    """Gate `readiness`, not just `stories`: it covers **both** the story index
    and the visual design contract.  Requiring only `stories` lets a story
    declaring `screens` run without any mockups — then fail the gate for
    "not compared", after spending money writing all the code."""
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


def _canh_bao_chua_bien_dich_guard(project, adapter) -> None:
    """Say it out loud when this run has no source-level guard.

    The story gate records `guard ran: not applicable — hooks not compiled`,
    which is honest but arrives after the money is spent. Nothing said so
    beforehand: a project that never ran `aisef compile` runs exactly like one
    that did, and the difference is whether anything can block a write.
    """
    import subprocess

    from ..clients.compile import guard_expected

    client_id = getattr(adapter, "id", "")
    if not guard_expected(project, client_id):
        print(f"⚠️  guards are not compiled for `{client_id}` — nothing blocks a write at "
              f"the source in this run, and the story gate will record `guard ran` as "
              f"not applicable.\n   Compile them first:  aisef compile --client {client_id}")
        return
    # Compiled is not the same as *present where the session runs*: stories run
    # in a worktree, which is a fresh checkout, so an uncommitted OpenCode
    # plugin is simply absent there. The gate then fails the story for a guard
    # that never had a chance to run — after the session is paid for.
    plugin = Path(project) / ".opencode" / "plugin" / "aisef-guard.ts"
    if client_id == "opencode" and plugin.is_file():
        tracked = subprocess.run(
            ["git", "-C", str(project), "ls-files", "--error-unmatch", str(plugin)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        ).returncode == 0
        if not tracked:
            print("⚠️  `.opencode/plugin` is compiled but not committed — a story worktree "
                  "is a fresh checkout, so the session will run with no guard at all, and "
                  "the gate will fail `guard ran`.\n   Commit it first:  "
                  "git add .opencode && git commit -m 'guard plugin'")


def cmd_run(args) -> int:
    """Run a wave: epics sequentially, stories in parallel within each epic.

    `--verify-only --story S`: re-check on a frozen candidate (ADR-004 R13)
    — same gate, same merge path, no developer session.
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

    git_err = _ensure_git(args.project)
    if git_err is not None:
        return git_err

    _canh_bao_chua_bien_dich_guard(args.project, adapter)

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
    """Evidence-driven improvement loop for an epic (ADR-004 R3).

    One invocation runs up to `--max-loops` loops then exits; re-running
    continues from the last `loops[]` checkpoint in the behaviour ledger
    — not a daemon.
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
    """Re-run all guards on the working tree — post-check.

    This is the assurance layer for clients that cannot wire pre-check hooks:
    violations are still caught, just **after the write** instead of blocking
    at write time.
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
    """Run a harness tool and record evidence."""
    import os

    from ..harness.guardrails import ENV_STORY_ID
    from ..harness.tools import run_tool

    # The agent does not need to know its own story ID: the harness placed
    # it in the environment when opening the session.
    story = args.story or os.environ.get(ENV_STORY_ID, "")
    res = run_tool(
        args.name,
        args.project,
        story_id=story,
        artifact_root=_artifact_root(args) if story else None,
        config=Config.load(args.project),
    )
    print(res.summary())
    if not story:
        # A run that records nothing must not look like a run that does. The
        # prompt tells the agent "the gate reads evidence, not claims", so a
        # green summary with no evidence behind it is the worst of both
        # (lỗi 117): the agent believes the check is banked and stops.
        print("⚠️  not recorded as evidence: no story id — pass `--story <id>` "
              "(the harness sets AISEF_STORY_ID inside a story session)")
    # Intentional order (ADR-005 V11 A): machine-readable summary **before**
    # tail — failed test names in the first 5 lines so the agent does not
    # need to re-run the runner to find them.
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
        # Declare truncation: the agent knows it has not seen everything, and
        # knows where the full output lives.
        full_ref = f" — full output: {_rel(res.log, args.project)}" if res.log else ""
        print(f"(truncated {total - args.lines}/{total} lines{full_ref})")
    if res.skipped:
        return EXIT_NOT_READY
    return EXIT_OK if res.ok else EXIT_NOT_READY


def _rel(path: str, project) -> str:
    """Short path when the file is inside the project; absolute otherwise
    (agent runs in a worktree, evidence log is at the main repo root)."""
    try:
        return str(Path(path).resolve().relative_to(Path(project).resolve()))
    except ValueError:
        return path


def cmd_qa(args) -> int:
    """Run the project's test suite.

    Defaults to **pre-deploy** scoring: unconfigured types also block,
    because "not run" is not "passed".  `--story-level` lowers to story-level
    scoring, where missing tools are only warnings.
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
    """Generate CI pipeline (code) and operational scaffolding (model)."""
    from ..phases.deploy import generate

    adapter, code = _client(args)
    if adapter is None:
        return code

    report = generate(
        args.project,
        adapter,
        config=Config.load(args.project),
        # Default is the **command name on PATH**, not this machine's absolute
        # path: the generated CI pipeline will run on a different machine.
        aisef_bin=args.bin or "aisef",
        install_spec=args.install_spec,
        force=args.force,
    )
    print(report.summary())
    return EXIT_OK if report.ok else EXIT_NOT_READY


def _project_has_ui(project: Path) -> bool:
    """Whether this project has a UI — ask what has been **decided**, not
    what was **suggested**.

    `detect_file(requirements.md)` only reads the initial requirements doc,
    where the author often does not name a framework.  By the time we score
    the pre-deploy gate, architecture is finalised and screens are built —
    use those.  Measured on e9: a 5-screen app was reported as "project has
    no UI", and `e2e`/`accessibility` were skipped with a factually wrong reason.
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
    """Score the pre-deployment gate."""
    from ..control.approvals import Gate
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
    """Look up a story or behaviour in the behaviour ledger (ADR-004 R6).

    This is the second half of progressive disclosure: the prompt receives
    only the **index**, while history lives here, queried on demand rather
    than preloaded.
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
    """Code map around write scope (ADR-005 V7) — second half of progressive
    disclosure like `evidence`: prompt receives the capped version, full
    version is queried here.  When called in a session (has `AISEF_STORY_ID`),
    records `note:ctx_lookup` like `doc_lookup`, so gates and reports know
    what the agent looked up."""
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
    """Export gap/regression table to file (ADR-004 R12).

    This is just a way to **read** the ledger: no issue creation anywhere,
    no network calls, no gate interaction.  Anyone wanting to push to
    GitHub/Jira can take the CSV — this repo does not know the project's
    tracker, and should not.
    """
    from ..control import ledger as ledger_mod

    statuses = {s.strip().lower() for s in args.status.split(",") if s.strip()}
    unknown = statuses - {ledger_mod.VERIFIED, ledger_mod.GAP, ledger_mod.REOPENED}
    if unknown or not statuses:
        # Mistyping a status and still exporting an empty file misleads the reader into "no gaps left".
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


def cmd_cost(args) -> int:
    """Attribute spend to outcomes (ADR-009 §Open O4).

    Read-only, like `aisef issues`: a projection over `evidence/` and the
    behaviour ledger, no gate touched, no model called.
    """
    from ..control import attribution

    root = _artifact_root(args)
    att = attribution.build(root)
    text = "\n".join(attribution.report_lines(att))
    print(text)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"\n{path}")
    return EXIT_OK


def cmd_report(args) -> int:
    """Generate acceptance report from existing evidence."""
    from ..control import ledger as ledger_mod
    from ..phases.report import build, write

    report = build(args.project)
    path = write(args.project, out=args.out or None)
    print(f"Report: {path}")
    print(f"  uncovered requirements: {len(report.uncovered)}")
    print(f"  stories with evidence: {len(report.stories)}")
    print(f"  total cost: ${report.total_cost_usd:.2f}")

    # Behaviour ledger + index: rebuilt from evidence each time, not accumulated.
    led = ledger_mod.build(_artifact_root(args))
    s = led.summary()
    print(f"  behaviour ledger: {s['verified']} verified · {s['gap']} gap · "
          f"{s['reopened']} reopened (resolved {s['resolved']}, "
          f"cross-story regressions {s['cross_reopens']})")
    print(f"  {led.write(_artifact_root(args))}\n  {led.index(_artifact_root(args))}")
    return EXIT_OK if not report.uncovered else EXIT_NOT_READY
