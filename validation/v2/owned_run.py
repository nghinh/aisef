"""Process-leak discipline (owner decision "AUTHORIZE P4" §9): owned processes measured, never grepped.

    python -P validation/v2/owned_run.py [--out FILE] -- CMD ...

CMD runs inside a process range (`aisef2.runtime.process_range`): it and everything it starts are the range's members
by the operating system's mechanism (POSIX: the session and process group of a pinned anchor; Windows: a job). When
CMD exits the range is measured — members still alive (`owned_after`, with their identities) and processes that left
it (`escaped`) — then released and measured empty. A live owned residual fails the run (exit 3) even when CMD exited
0; unrelated system processes are never counted, because only members are.

`owned_before` is the range's membership before CMD starts: a new range has none. The P2-era harness orphan signature
(parent PID 1, the python_callable harness) is also counted before and after, machine-wide, for continuity with the
earlier gate.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.runtime import process_range as pr  # noqa: E402

SETTLE_S = 5.0            # a process still exiting when CMD ends is given this long before it counts as residual
HARNESS_SIGNATURE = "json.loads(sys.stdin.read())"


def harness_orphans() -> int | None:
    """P2 python_callable harness processes re-parented to init, machine-wide (POSIX); None where not measurable."""
    if os.name != "posix":
        return None
    return sum(1 for p in pr.process_table().values() if p.ppid == 1 and HARNESS_SIGNATURE in p.command)


def measure(argv: list[str], *, settle_s: float = SETTLE_S, grace_s=(2.0, 2.0), wait_s: float = 60.0) -> dict:
    orphans_before = harness_orphans()
    r = pr.ProcessRange("owned-run", argv, output=None, grace_s=grace_s, wait_s=wait_s).start()
    code = r.wait(None)
    at_exit = r.members()
    r.wait_empty(settle_s)
    residual, escaped = r.members(), r.escaped()
    try:
        r.release()
        released = True
    except pr.RangeEscaped:
        released = True  # the range itself emptied; the escapees are reported below
    except pr.RangeNotEmpty:
        released = False
    return {"command": argv, "exit": code,
            "mechanism": "posix-session-and-group" if os.name == "posix" else "windows-job",
            "owned_before": 0, "owned_at_exit": len(at_exit), "owned_after": len(residual), "residual": [{"pid": p.pid, "command": p.command} for p in residual],
            "escaped": [{"pid": p.pid, "command": p.command} for p in escaped],
            "ladder": [s["stage"] for s in r.ledger], "released_empty": released and not r.members(),
            "harness_orphans_before": orphans_before, "harness_orphans_after": harness_orphans()}


def problems_of(m: dict) -> list[str]:
    out = []
    if m["owned_after"]:
        out.append(f"{m['owned_after']} owned process(es) outlived the command: {m['residual']}")
    if m["escaped"]:
        out.append(f"{len(m['escaped'])} process(es) left the range and are alive: {m['escaped']}")
    if not m["released_empty"]:
        out.append("the range was not measured empty after release")
    before, after = m.get("harness_orphans_before"), m.get("harness_orphans_after")
    if before is not None and after is not None and after > before:
        out.append(f"harness orphans rose from {before} to {after}")
    return out


def check(root: pathlib.Path = ROOT) -> list[str]:
    """The clean half of calibration: a command that leaves nothing behind measures clean."""
    return problems_of(measure([sys.executable, "-c", "import subprocess, sys; subprocess.run([sys.executable, '-c', "
                                                      "'pass'])"], settle_s=1.0))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    out = None
    if argv[:1] == ["--out"]:
        out, argv = pathlib.Path(argv[1]), argv[2:]
    if argv[:1] != ["--"] or len(argv) < 2:
        print("usage: owned_run.py [--out FILE] -- CMD ...", file=sys.stderr)
        return 2
    t = time.monotonic()
    m = measure(argv[1:])
    problems = problems_of(m)
    if out is not None:
        out.write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"owned processes: before={m['owned_before']} at_exit={m['owned_at_exit']} after={m['owned_after']} "
          f"escaped={len(m['escaped'])} released_empty={m['released_empty']} ladder={m['ladder']} "
          f"harness_orphans={m['harness_orphans_before']}->{m['harness_orphans_after']} ({m['mechanism']}, "
          f"{time.monotonic() - t:.0f}s)", flush=True)
    for p in problems:
        print(f"FAIL  {p}", flush=True)
    return 3 if problems else (m["exit"] if m["exit"] is not None else 1)


if __name__ == "__main__":
    sys.exit(main())
