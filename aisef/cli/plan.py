"""Planning phase and human gates: ``gates`` · ``review`` · ``approve``
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
    is_present,
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
    _ensure_git,
)


def cmd_gates(args) -> int:
    store = _approvals(args)
    print(f"Approval gates — {_artifact_root(args)}\n")
    pending_first = None
    for gate, status, by in store.summary():
        mark = _GATE_MARK[status]
        who = f"  ({by})" if by else ""
        missing = [p.name for p in store.artifact_paths(gate) if not is_present(p)]
        exists = "" if not missing else f"   [missing: {', '.join(missing)}]"
        print(f"  {mark} {gate.value:14} {status.value:18}{who}{exists}")
        if pending_first is None and status is not Status.APPROVED:
            pending_first = gate

    if pending_first:
        print(f"\nNext gate to handle: {pending_first.value}")
        print(f"  aisef review {pending_first.value}")
        return EXIT_NOT_READY
    print("\n✅ all gates approved")
    return EXIT_OK


def cmd_review(args) -> int:
    """Display artifact and what needs to be reviewed before approval."""
    store = _approvals(args)
    gate: Gate = args.gate
    paths = store.artifact_paths(gate)
    status = store.status(gate)

    print(f"Gate: {gate.value}")
    print(f"Status: {status.value}")
    print("Artifact: " + ", ".join(str(p) for p in paths))

    missing = [p for p in paths if not p.is_file()]
    if missing:
        names = ", ".join(p.name for p in missing)
        print(f"\n✗ artifact not found ({names}) — run the generating step first")
        return EXIT_NOT_READY

    blocking = store.blocking(gate)
    if blocking:
        print(f"\n⚠️  preceding gates not yet approved: {', '.join(g.value for g in blocking)}")

    rec = store.load(gate)
    if rec and rec.note:
        print(f"\nPrevious note ({rec.status}): {rec.note}")

    for artifact in paths:
        if artifact.name == CONTRACT_FILE:
            from ..phases.mockup import describe_contract

            data = json.loads(artifact.read_text(encoding="utf-8"))
            print(f"\n— {len(data.get('screens', []))} screens —\n")
            print(describe_contract(data, artifact.parent))
            continue
        if artifact.name == STORIES_INDEX:
            from ..phases.story_split import describe_index

            data = json.loads(artifact.read_text(encoding="utf-8"))
            if gate is Gate.READINESS:
                data = _prereqs_recomputed(data, args)
            print(f"\n— {len(data.get('stories', []))} story —")
            print(describe_index(data))
            continue
        lines = artifact.read_text(encoding="utf-8", errors="replace").splitlines()
        print(f"\n— {artifact.name} ({len(lines)} lines) —\n")
        print("\n".join(lines[: args.lines]))
        if len(lines) > args.lines:
            print(f"\n… {len(lines) - args.lines} more lines. Open: {artifact}")

    if gate is Gate.READINESS:
        for line in _preflight_lines(args):
            print(line)

    print(f"\nApprove:  aisef approve {gate.value}")
    print(f"Reject:   aisef reject  {gate.value} --note \"...\"")
    return EXIT_OK


def _preflight(args):
    """(lines to print, stories that genuinely cannot run).

    Two different things were being conflated. A story missing a **run**
    capability cannot start; a story missing an optional one — the
    code-intelligence provider, whose own message says the builtin still runs,
    only coarser — merely runs with less. Approval refused on both, so a fresh
    project could never approve `readiness` without `--force`: evidence and
    optional providers are exactly what does not exist before the first run,
    and stories cannot run until readiness is approved. Measured 2026-09-09 on
    todo-e2e, 9 of 14 stories held up by one advisory line.

    The reviewer still sees every gap — that part of the design was right.
    """
    lines = _preflight_lines(args)
    return lines, _not_executable(args)


def _not_executable(args) -> list[str]:
    from ..control.preflight import check_stories_executable
    from ..phases.run import load_plan

    plan = load_plan(_artifact_root(args))
    if plan.error or not plan.stories:
        return []
    res = check_stories_executable(
        list(plan.stories.values()), project=Path(args.project).resolve(),
        config=Config.load(args.project),
    )
    return [pf.story_id for pf in res if not pf.executable]


def _prereqs_recomputed(data: dict, args) -> dict:
    """Replace the recorded provisioning warnings with today's answer.

    The stories gate runs before mockups exist and before tools are
    configured, so its warnings are expected to be out of date by the time
    anyone reads them at the `readiness` gate — which printed "configure
    `app.dev_command`" directly above the "✅ 7 stories are all executable"
    it had just computed (bug 97). The rest of the recorded gate (cycles,
    serialized epics) still holds and is left alone.
    """
    from ..control.preflight import check_stories_executable
    from ..phases.run import load_plan
    from ..phases.story_split import PREREQ_WARNING

    plan = load_plan(_artifact_root(args))
    if plan.error or not plan.stories:
        return data
    gate = dict(data.get("gate") or {})
    ghi = [w for w in gate.get("warnings", []) if PREREQ_WARNING not in w]
    for pf in check_stories_executable(
        list(plan.stories.values()), project=Path(args.project).resolve(),
        config=Config.load(args.project),
    ):
        if pf.provisioning_gaps:
            ghi.append(f"{pf.story_id} {PREREQ_WARNING}: "
                       + "; ".join(m.line() for m in pf.provisioning_gaps))
    gate["warnings"] = ghi
    return {**data, "gate": gate}


def _preflight_lines(args) -> list[str]:
    """Which stories are not yet executable — computed by code, right before
    the human gate.

    The `readiness` gate is the last checkpoint before spending money.  At
    this point mockups are built and tools are configured, so **both** kinds
    of gap are catchable: broken stories and unconfigured projects.
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
    # Human gate: require **completeness**, including acceptance capabilities.
    # This is the last checkpoint before spending money, and the reviewer
    # needs to see the gaps.
    bad = [pf for pf in res if not pf.complete]
    if not bad:
        return [f"\n✅ {len(res)} stories are all executable"]
    out = [f"\n✗ {len(bad)}/{len(res)} stories not yet eligible:"]
    for pf in bad:
        label = STORY_NOT_EXECUTABLE if not pf.executable else "MISSING EVIDENCE"
        out.append(f"  {label} {pf.story_id}")
        out += [f"    - {m.line()}" for m in pf.missing]
    return out


def cmd_approve(args) -> int:
    store = _approvals(args)
    gate: Gate = args.gate
    if not store.has_artifacts(gate):
        missing = ", ".join(p.name for p in store.artifact_paths(gate) if not is_present(p))
        print(f"✗ no artifact for gate {gate.value}: {missing}", file=sys.stderr)
        return EXIT_NOT_READY

    blocking = store.blocking(gate)
    if blocking and not args.force:
        names = ", ".join(g.value for g in blocking)
        print(f"✗ preceding gates not yet approved: {names}", file=sys.stderr)
        print("  approve them first, or use --force to skip intentionally", file=sys.stderr)
        return EXIT_NOT_READY

    if gate is Gate.READINESS and not args.force:
        lines, blocked = _preflight(args)
        if blocked:
            print("\n".join(lines), file=sys.stderr)
            print(
                f"\n✗ cannot approve: {len(blocked)} storie(s) cannot run at all "
                f"({', '.join(blocked[:5])}). Configure what they need and re-approve, "
                "or use --force to override.",
                file=sys.stderr,
            )
            return EXIT_NOT_READY
        # Gaps that only degrade quality are shown, not blocking: they are
        # what the human is here to weigh.
        if any("✗" in ln for ln in lines):
            print("\n".join(lines))

    rec = store.approve(gate, note=args.note or "")
    print(f"✅ {gate.value} approved by {rec.decided_by}")
    return EXIT_OK


def cmd_reject(args) -> int:
    store = _approvals(args)
    gate: Gate = args.gate
    # `approve` đòi tạo tác có thật; `reject` thì không — bất đối xứng ấy cho
    # phép ghi một lời từ chối cho thứ **chưa tồn tại**. Khi pha kế hoạch sinh
    # ra tạo tác thật, cổng đã mang sẵn trạng thái "bị từ chối" kèm một lời
    # nhận xét viết trước khi có gì để nhận xét — người đọc sau không có cách
    # nào biết điều đó. Đo 13/09/2026 trên dự án mới: `approve prd` thoát 2
    # "no artifact", cùng lúc `reject prd --note test` thoát 0.
    if not store.has_artifacts(gate):
        missing = ", ".join(p.name for p in store.artifact_paths(gate) if not is_present(p))
        print(f"✗ no artifact for gate {gate.value}: {missing} — nothing to reject yet",
              file=sys.stderr)
        return EXIT_NOT_READY
    try:
        rec = store.reject(gate, note=args.note)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return EXIT_USAGE
    print(f"✗ {gate.value} rejected: {rec.note}")
    return EXIT_OK


def cmd_auto_approve(args) -> int:
    """Auto-approve — always records the `auto` flag for future audit."""
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
    print(f"auto-approved: {', '.join(done) if done else '(no gate has artifacts)'}")
    return EXIT_OK


def cmd_plan(args) -> int:
    """Run the BMAD phase chain up to the first unapproved gate."""
    from ..phases.plan import run_pipeline

    try:
        gates = parse_auto_approve(args.auto_approve)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return EXIT_USAGE

    adapter, code = _client(args)
    if adapter is None:
        return code

    git_err = _ensure_git(args.project)
    if git_err is not None:
        return git_err

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
    """Generate mockups for each screen, then extract visual design contracts."""
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

    git_err = _ensure_git(args.project)
    if git_err is not None:
        return git_err

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
    print(f"\n⏸ awaiting approval: {Gate.MOCKUPS.value}\n   aisef review mockups")
    return EXIT_NOT_READY


def cmd_change(args) -> int:
    """Change lifecycle: record change request, mark PRD and downstream gates stale, generate delta stories."""
    from ..control.change import apply

    try:
        r = apply(Path(args.project), args.requirement, args.description)
    except (ValueError, OSError) as e:
        print(f"change: {e}", file=sys.stderr)
        return EXIT_NOT_READY
    print(f"Recorded change {r.requirement} → story delta {r.story_id} ({r.story_file.name})")
    print("  PRD: " + ("marked — prd gate and subsequent gates set to stale" if r.prd_marked else "no prd.md yet — gates will run from scratch"))
    print("Next steps:")
    for b in r.next_steps:
        print(f"  - {b}")
    return EXIT_OK
