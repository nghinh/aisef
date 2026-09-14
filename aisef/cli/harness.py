"""Harness setup and operation commands: ``init`` · ``setup`` · ``compile`` ·
``guard`` · ``gate`` · ``skill`` · ``doc``."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from ..config import Config
from ..harness.tools import aisef_argv
from ._common import ARTIFACT_ROOT, EXIT_NOT_READY, EXIT_OK, EXIT_USAGE, _artifact_root, _client


def cmd_baseline(args) -> int:
    """Build baseline for brownfield: analyse the existing codebase."""
    from ..codebase.baseline import build_baseline
    from ..codebase.detect import detect
    from ..codebase.provider import resolve

    project = Path(args.project)

    if getattr(args, "incremental", False):
        provider = resolve(project, preference=args.provider or "auto")
        result = provider.build(project, incremental=True)
        print(f"Graph updated: {provider.name} — {result.nodes} nodes, {result.edges} edges")
        return EXIT_OK

    sig = detect(project)
    if not sig.is_brownfield and not args.force:
        print(f"Greenfield: {sig.source_files} source files — use `aisef plan` instead of `aisef baseline`.")
        print("  (use --force to build baseline even for greenfield)")
        return EXIT_OK

    provider = resolve(project, preference=args.provider or "auto")
    output = _artifact_root(args) / "baseline.md"
    text = build_baseline(project, provider=provider, output=output)
    print(f"Baseline: {sig.summary}")
    print(f"  provider: {provider.name}")
    print(f"  wrote: {output}")
    lines = text.count("\n")
    print(f"  {lines} lines")
    return EXIT_OK


#: Lệnh test mặc định của mỗi stack **in tên test**. Đo 2026-09-12 trên một dự
#: án mới tinh: `init --stack python` ghi `python -m pytest`, rồi `doctor` báo
#: ngay hai mục kiểm của cổng ("has tests", "no existing tests broken") sẽ ra
#: *chưa cấu hình* — vì không đọc được tên test. Người mới không có cách nào
#: biết điều đó trước khi chạy hết một story. Thêm `-v` là đủ, không thêm phụ
#: thuộc nào. Coverage thì vẫn cần plugin, nên vẫn để người tự khai.
#: Tên trình thông dịch **có thật trên máy đang chạy `init`**. macOS và phần lớn
#: bản Linux hiện đại không có `python`, chỉ có `python3`; Windows thì ngược lại.
#: Đo 13/09/2026: `init --stack python` ghi `python -m pytest -v`, rồi
#: `aisef tool test` trên đúng máy ấy ra `exit 127: No such file or directory:
#: 'python'` — preset sinh ra một lệnh không chạy được trên máy vừa sinh ra nó.
_PY = "python" if shutil.which("python") else "python3"

#: The framework installs 155 skills into `.claude/`, and the project must
#: commit them — a story worktree is a checkout, so an uncommitted skill is
#: absent where the session runs. Which means every linter the project
#: configures will read them (bug 113: `npx eslint .` reported 116 `no-undef`
#: errors in skill scripts and failed the story's lint check). The project's
#: lint command lints the project.
_NGOAI_KHUNG_JS = (' --ignore-pattern "**/.claude/**"'
                   ' --ignore-pattern "**/.aisef/**"'
                   ' --ignore-pattern "**/.opencode/**"')
_NGOAI_KHUNG_PY = " --exclude .claude --exclude .aisef --exclude .opencode"

STACK_PRESETS: dict[str, dict[str, object]] = {
    "react": {
        "tools.test": "npx vitest run --reporter=verbose",
        "tools.lint": "npx eslint . --max-warnings=0" + _NGOAI_KHUNG_JS,
        "sandbox.image": "node:22-alpine",
        "sandbox.tools_network": True,
        "sandbox.allow_hosts": ["registry.npmjs.org", "*.npmjs.org"],
        "app.dev_command": "npm run dev",
    },
    "python": {
        "tools.test": f"{_PY} -m pytest -v",
        "tools.lint": "ruff check ." + _NGOAI_KHUNG_PY,
        "sandbox.image": "python:3.12-slim",
        "sandbox.allow_hosts": ["pypi.org", "files.pythonhosted.org"],
    },
    "go": {
        "tools.test": "go test -v ./...",
        "tools.lint": "golangci-lint run",
        "sandbox.image": "golang:1.23-alpine",
        "sandbox.allow_hosts": ["proxy.golang.org", "sum.golang.org"],
    },
    "node": {
        "tools.test": "npm test",
        "tools.lint": "npx eslint . --max-warnings=0" + _NGOAI_KHUNG_JS,
        "sandbox.image": "node:22-alpine",
        "sandbox.tools_network": True,
        "sandbox.allow_hosts": ["registry.npmjs.org", "*.npmjs.org"],
    },
}


def cmd_init(args) -> int:
    """Write default config file for customisation."""
    stack = getattr(args, "stack", "") or ""
    cfg = Config.load(args.project)
    if stack and stack in STACK_PRESETS:
        cfg = cfg.overlay(STACK_PRESETS[stack])
    path = cfg.write_template(args.project)
    print(f"wrote {path}")
    if stack:
        print(f"stack: {stack} — test/lint/sandbox configured")
        thieu = _cong_cu_chua_co(Path(args.project), cfg)
        if thieu:
            print("\n".join(thieu))
    return EXIT_OK


def _cong_cu_chua_co(project: Path, cfg) -> list[str]:
    """Which configured tool commands cannot run on this machine yet.

    A preset writes a command; whether the binary exists is a property of the
    machine (bug 82). `npx eslint` in a project with no eslint and no flat
    config exits non-zero, and nothing notices until a story fails its gate
    on lint — `provisioned()` asks whether the key is set, not whether the
    command runs, which is the right question for a configuration check and
    the wrong one to rely on alone.
    """
    ra = []
    for key in ("tools.test", "tools.lint"):
        lenh = str(cfg[key] or "").strip()
        if not lenh:
            continue
        phan = lenh.split()
        ten = phan[0]
        if ten in ("npx", "npm", "pnpm", "yarn", "bunx"):
            ten = next((t for t in phan[1:] if not t.startswith("-")), "")
            if not ten or ten in ("run", "test", "exec"):
                continue
            if (project / "node_modules" / ".bin" / ten).exists():
                continue
            them = " (and a flat config file)" if ten == "eslint" else ""
            ra.append(f"  ○ `{key}` = `{lenh}` — needs `{ten}` installed in this "
                      f"project{them}: `npm i -D {ten}`. Until then "
                      f"`aisef tool {key.split('.')[1]}` reports not-runnable, and the "
                      f"story gate fails on it after the session is paid for")
        elif not shutil.which(ten):
            ra.append(f"  ○ `{key}` = `{lenh}` — `{ten}` is not on PATH on this machine; "
                      f"install it or set `{key}` to a command that runs here")
    return ra


def cmd_setup(args) -> int:
    """Detect stack and install matching skills into the project."""
    from ..kit import install
    from ..kit.detect_stack import detect_file

    project = Path(args.project)
    req = project / "docs" / "requirements.md"
    if not req.is_file():
        print(f"✗ missing {req}", file=sys.stderr)
        print("  this is the project's sole input — create it first", file=sys.stderr)
        return EXIT_NOT_READY

    from ..kit import fetch

    references = (
        Path(args.references).resolve() if args.references else fetch.default_root()
    )
    if not args.no_fetch:
        print(f"Skill source: {references}")
        report = fetch.ensure(references)
        print(report.summary())
        print()
    if not references.is_dir():
        print(f"✗ missing source directory: {references}", file=sys.stderr)
        print("  rerun without --no-fetch to auto-fetch", file=sys.stderr)
        return EXIT_NOT_READY

    stack = detect_file(req)
    print(f"Detected stack: {stack.summary()}")
    if stack.undetermined:
        print(f"  ⚠️  undetermined: {', '.join(stack.undetermined)}")
        print("     — architecture phase will decide; not guessing here")

    text = req.read_text(encoding="utf-8", errors="replace")
    plan_ = install.plan(project, stack, references_root=references, requirements_text=text)
    print()
    print(plan_.summary())

    if args.dry_run:
        print("\n(dry-run — nothing written)")
        return EXIT_OK

    report = install.apply(plan_, project)
    print(f"\n{report.summary()}")

    from ..kit.constitution import write_for_project

    written = write_for_project(project, project.resolve().name, stack)
    print("rules: " + ", ".join(p.name for p in written))

    cfg_path = project / ".ai" / "config.json"
    if not cfg_path.is_file():
        Config.load(project).write_template(project)
        print(f"wrote {cfg_path}")

    print(f"\n✅ done. Verify: aisef --project {args.project} doctor")
    return EXIT_OK


def cmd_compile(args) -> int:
    """Generate client configuration from a single source of truth."""
    from ..clients.compile import ADAPTERS, compile_for, write_compile_report

    clients = sorted(ADAPTERS) if args.client == "all" else [args.client]
    # Don't guess the path: `aisef_argv` already prefers the name on PATH
    # (real install) before falling back to `bin/aisef` from the source repo.
    # `--bin` names one binary, so it stays one token; the fallback is argv.
    aisef_bin = args.bin or aisef_argv()

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
    print(f"\nreport: {path}")

    if any(not r.blocks_at_source for r in reports):
        print("\n⚠️  some clients can only be checked later — lower assurance, noted in report")
    return EXIT_OK


def cmd_guard(args) -> int:
    """Run a guard on a hook event read from stdin.

    Clients call this at lifecycle hooks.  Exit 2 means block, and the
    reason goes to stderr — Claude Code passes stderr into the tool result
    for the agent to read, so the reason must tell the agent what to fix.
    """
    import json
    import time

    from ..control.worktree import main_repo
    from ..harness.guardrails import project_root_from, record_outcome, run_guard

    root = Path(project_root_from(None, str(args.project))).resolve()
    artifact_root = main_repo(root) / ARTIFACT_ROOT

    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("guard: could not parse event, skipping", file=sys.stderr)
        return EXIT_OK

    t0 = time.monotonic()
    try:
        verdict = run_guard(
            args.kind,
            event,
            project_root=str(root),
            artifact_root=str(artifact_root),
        )
    except ValueError as e:
        print(f"guard: {e}", file=sys.stderr)
        return EXIT_OK
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    try:
        record_outcome(args.kind, event, verdict,
                       artifact_root=str(artifact_root),
                       duration_ms=elapsed_ms)
    except OSError as e:
        print(f"guard: could not record evidence ({e})", file=sys.stderr)

    if not verdict.allowed:
        # P1-4: structured error — JSON on stdout for machine readers,
        # human reason on stderr for agent
        import json as _json
        print(_json.dumps({
            "guard": args.kind,
            "allowed": False,
            "reason": verdict.reason,
            "tool": str(event.get("tool_name") or ""),
        }, ensure_ascii=False))
        # Prefixed so a client can tell a guard block from any other tool
        # error (bug 100). The prefix is printed by the guard itself, which
        # means it survives an out-of-date compiled hook that only forwards
        # stderr.
        print(f"aisef guard {args.kind}: {verdict.reason}", file=sys.stderr)
    return verdict.exit_code


def cmd_skill(args) -> int:
    """Build and inspect skill registry (ADR-002).  Read-only — does not modify the project."""
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
    print(f"Skill registry: {len(reg.entries)} entries")
    for st in R.STATUSES:
        if by[st]:
            print(f"  {st:10} {by[st]}")
    rej = [e for e in reg.entries.values() if e.status == R.REJECTED]
    if rej:
        print("\n✗ rejected (not routed):")
        for e in rej[:10]:
            print(f"    {e.id:50} {'; '.join(e.verified.gaps[:1])}")

    if args.story:
        plan = load_plan(_artifact_root(args))
        st = plan.stories.get(args.story)
        if st is None:
            print(f"\nstory {args.story} not found in plan", file=sys.stderr)
            return EXIT_NOT_READY
        r = RT.route(st, reg, project=project)
        print(f"\nRouting for {args.story} — {st.title}:")
        print("  " + r.prompt_section().replace(chr(10), chr(10) + "  "))
    return EXIT_OK


def cmd_doc(args) -> int:
    """Look up library documentation on demand (rule 12) — context7 via HTTP, cached.
    With `--story`, records `doc_lookup` evidence: gates and reports know what
    the agent looked up instead of guessing."""
    from ..kit.docs import DocError, lookup

    try:
        d = lookup(args.package, args.topic or "", tokens=args.tokens)
    except DocError as e:
        print(f"doc: {e}", file=sys.stderr)
        return EXIT_NOT_READY
    except OSError as e:
        print(f"doc: could not reach context7 ({e}) — work from existing docs, do not guess API names", file=sys.stderr)
        return EXIT_NOT_READY
    print(f"# {d.title or d.library} — {d.topic or 'overview'} ({'cache' if d.cached else 'context7'}: {d.library})\n")
    print(d.text)
    if args.story:
        from ..harness.observe import NOTE, Event, EvidenceStore

        EvidenceStore(_artifact_root(args)).record(args.story, Event(
            kind=NOTE, name="doc_lookup",
            detail={"package": args.package, "library": d.library, "topic": d.topic, "chars": len(d.text), "cached": d.cached},
        ))
    return EXIT_OK


def _waive_review(args) -> int:
    """Record a human override of a review-only block (closure gate G2.4b-iii).

    The `review` check is the only `model-judge` entry in `gate.CHECK_KIND`,
    and its measured error rate is not hypothetical: 11 of 20 consecutive
    reviews of an identical tree reversed the verdict. Re-verify keeps a
    blocking review conclusion at the same SHA on purpose, so a person needs a
    way to say "this claim is wrong" that does not mean rewriting the story.

    Four refusals, each closing a way this could stop being an escape hatch and
    start being a bypass: no reason, no gate scoring to override, review was
    not blocking, or the caller is an agent session (`AISEF_STORY_ID`) — an
    agent must not sign off its own review. The record is bound to the
    candidate, so the next build is scored from scratch; and the check it
    produces is `WAIVED`, which is neither blocking nor a pass.
    """
    import os

    from ..control.approvals import _current_user, _now
    from ..control.gate import REVIEW_WAIVER
    from ..control.replay import GATE_INPUT, GATE_VERDICT
    from ..harness.guardrails import ENV_STORY_ID
    from ..harness.observe import NOTE, Event, EvidenceStore

    if not args.story:
        print("✗ gate --waive-review requires <story>", file=sys.stderr)
        return EXIT_USAGE
    if not args.reason.strip():
        print("✗ gate --waive-review requires --reason: a waiver with no reason is "
              "a waiver nobody can audit", file=sys.stderr)
        return EXIT_USAGE
    if os.environ.get(ENV_STORY_ID):
        print(f"✗ refusing: {ENV_STORY_ID} is set, so this is an agent session — the "
              f"reviewer's block is not the reviewed agent's to waive. Run it from your "
              f"own shell (`unset {ENV_STORY_ID}` if it is left over from an earlier run).",
              file=sys.stderr)
        return EXIT_USAGE

    root = _artifact_root(args)
    ev = EvidenceStore(root).read(args.story)
    dau_vao = ev.last(NOTE, GATE_INPUT)
    if dau_vao is None:
        print(f"✗ {args.story}: no gate scoring recorded — nothing to override",
              file=sys.stderr)
        return EXIT_USAGE
    chan = [str(x) for x in (dau_vao.detail.get("review_blocking") or [])]
    candidate = str(dau_vao.detail.get("candidate") or "")
    if not chan:
        print(f"✗ {args.story}: review was not blocking at the last gate scoring — "
              f"nothing to waive", file=sys.stderr)
        return EXIT_USAGE
    if not candidate:
        print(f"✗ {args.story}: the last gate scoring recorded no candidate SHA, so a "
              f"waiver could not be bound to a build", file=sys.stderr)
        return EXIT_USAGE

    who = _current_user()
    EvidenceStore(root, candidate=candidate).record(args.story, Event(
        # `ok=False`: a waiver is not a pass. What it records is that a person
        # took responsibility for a block, and the gate still says `◇`, not `✅`.
        kind=NOTE, name=REVIEW_WAIVER, ok=False,
        detail={"reason": args.reason.strip(), "by": who, "at": _now(),
                "waived": chan, "attempt": int(dau_vao.detail.get("attempt") or 0)},
    ))
    print(f"◇ review block waived by {who} at candidate {candidate[:7]} "
          f"({len(chan)} item{'s' if len(chan) != 1 else ''})")
    for item in chan[:5]:
        print(f"  - {item[:150]}")
    verdict = ev.last(NOTE, GATE_VERDICT)
    khac = [str(n) for n in ((verdict.detail.get("failures") or []) if verdict else [])
            if n != "review"]
    if khac:
        print(f"⚠ still blocking on its own merits: {', '.join(khac)} — the waiver "
              f"covers `review` only")
    print(f"next: aisef run --verify-only --story {args.story}")
    return EXIT_OK


def cmd_gate(args) -> int:
    """Re-score story gates on recorded evidence (ADR-005 V4).

    Read-only: slice evidence at each round's `gate:input`, call the
    **current** code's `gate.evaluate`, print a per-item diff against the
    recorded `gate:verdict`.  No model calls — reviewer/security notes are
    what was recorded.  Rounds without `gate:input` (pre-V4) are reported
    as unreplayable, not guessed.  Exit 2 when no round can be replayed.
    """
    from ..control import replay as R
    from ..harness.observe import EvidenceStore

    if getattr(args, "waive_review", False):
        return _waive_review(args)
    if not args.replay:
        print("✗ gate: pass `--replay` (re-evaluate on recorded evidence) or "
              "`--waive-review --reason ...` (override a review-only block)", file=sys.stderr)
        return EXIT_USAGE
    if not args.story and not args.all:
        print("✗ gate --replay requires <story> or --all", file=sys.stderr)
        return EXIT_USAGE

    store = EvidenceStore(_artifact_root(args))
    ids = store.stories() if args.all else [args.story]
    print(R.BANNER)
    replayed = total = 0
    for sid in ids:
        ev = store.read(sid)
        rs = R.replay(ev, attempt=args.attempt)
        unrepl = R.unreplayable(ev)
        if args.attempt:
            unrepl = [a for a in unrepl if a == args.attempt]
        if not rs and not unrepl:
            if not args.all:
                print(f"✗ {sid}: no gate evaluation found in evidence", file=sys.stderr)
            continue
        print()
        for r in rs:
            print(r.summary())
        for a in unrepl:
            print(f"{sid} attempt {a}: not replayable (evidence predates ADR-005 V4 — "
                  f"no `gate:input`), not guessing")
        replayed += len(rs)
        total += len(rs) + len(unrepl)
    print(f"\nreplayed {replayed}/{total} attempts")
    return EXIT_OK if replayed else EXIT_NOT_READY


def cmd_replay(args) -> int:
    """Top-level replay: ``aisef replay <story>`` — delegates to gate --replay."""
    from ..control import replay as R
    from ..harness.observe import EvidenceStore

    if not args.story and not args.all:
        print("✗ replay requires <story> or --all", file=sys.stderr)
        return EXIT_USAGE

    store = EvidenceStore(_artifact_root(args))
    ids = store.stories() if args.all else [args.story]
    print(R.BANNER)
    replayed = total = 0
    for sid in ids:
        ev = store.read(sid)
        rs = R.replay(ev, attempt=args.attempt)
        unrepl = R.unreplayable(ev)
        if args.attempt:
            unrepl = [a for a in unrepl if a == args.attempt]
        if not rs and not unrepl:
            if not args.all:
                print(f"✗ {sid}: no gate evaluation found in evidence", file=sys.stderr)
            continue
        print()
        for r in rs:
            print(r.summary())
        for a in unrepl:
            print(f"{sid} attempt {a}: not replayable (predates ADR-005 V4)")
        replayed += len(rs)
        total += len(rs) + len(unrepl)
    if not total:
        print("no gate evidence found")
        return EXIT_NOT_READY
    print(f"\nreplayed {replayed}/{total} attempts")
    return EXIT_OK if replayed else EXIT_NOT_READY
