"""The security scanner (RFC §25, V2-005 §10): a tool the story invokes in its read-only scope — `tool/invoked`,
`tool/result` through P4's owned process range — and one `gate/check` row per finding read from the scanner's typed
report. A scanner that ran and found is EXECUTED; its blocking finding is SECURITY_FINDING (owner SECURITY, the
SECURITY budget). A scanner that cannot start is CAPABILITY_UNRUNNABLE. Nothing is parsed from its text."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

from aisef2.control.owner import Classification, FailureCode, classify
from aisef2.journal.format2 import OperationOutcome as O
from aisef2.orchestrate import gate
from aisef2.orchestrate.adapters import CapabilityUnrunnable, ReadOnlyScope, Scanner
from aisef2.runtime.process_range import RangeError
from aisef2.runtime.tool import ToolCall

_RAN = frozenset({O.COMPLETED.value, O.FAILED.value})


@dataclass(frozen=True, slots=True)
class Scan:
    invoked_seq: int | None
    result_seq: int | None
    checks: tuple[int, ...]
    failure: Classification | None


def scan(run, story_id: str, scope: ReadOnlyScope, scanner: Scanner, scratch: str, *, timeout_s: float,
         attempt: int) -> Scan:
    """One invocation per attempt (a call id is invoked once per run). A scanner that cannot even name its command
    (CapabilityUnrunnable) and a tool that cannot start (the range's own RangeError) are both CAPABILITY_UNRUNNABLE,
    typed from the refusal, never from text."""
    report = str(pathlib.Path(scratch) / f"{scanner.name}-{story_id}.report")
    try:
        argv = scanner.argv(scope, report)
    except CapabilityUnrunnable:
        return Scan(None, None, (), classify(FailureCode.CAPABILITY_UNRUNNABLE))
    call = ToolCall(run, story_id, f"{scanner.name}-{story_id}#{attempt}", scanner.name, argv, cwd=scope.root)
    try:
        invoked = call.dispatch()
    except RangeError:
        closed = call.close()
        return Scan(None, closed.seq if closed else None, (), classify(FailureCode.CAPABILITY_UNRUNNABLE))
    recorded = call.finish(timeout_s)
    if recorded.data["outcome"] not in _RAN:
        return Scan(invoked.seq, recorded.seq, (), classify(FailureCode.CAPABILITY_UNRUNNABLE))
    scanned = scanner.read(report, call.range.returncode)
    if not scanned.executed:
        return Scan(invoked.seq, recorded.seq, (), classify(FailureCode.CAPABILITY_UNRUNNABLE))
    checks = [gate.check(run, story_id, f"security:{f.id}", not f.blocks, "blocking" if f.blocks else "informational")
              for f in scanned.findings]
    if not checks:
        checks.append(gate.check(run, story_id, "security", True, f"{scanner.name} ran: no finding"))
    failure = classify(FailureCode.SECURITY_FINDING) if any(f.blocks for f in scanned.findings) else None
    return Scan(invoked.seq, recorded.seq, tuple(checks), failure)
