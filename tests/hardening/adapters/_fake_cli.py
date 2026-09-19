"""Recorded-stream stand-in for a client CLI — the process the REAL adapter spawns in these suites.

Replays a JSON *plan* written by the test: the JSONL events a real ``claude -p`` / ``opencode run``
would print, then exits, sleeps, crashes or leaves a survivor, as the plan says. No model.
argv: ``<plan.json> [adapter flags…]`` — the adapter's own flags are recorded, never interpreted.

Plan keys: ``lines`` (JSONL, one event each) · ``trailing`` (bytes with no newline: killed mid-line) ·
``stderr`` · ``exit`` · ``sleep`` (seconds, after emitting) · ``grandchild`` (spawn a sleeper the
kill must reach) · ``survivor`` (one line written *after* this process dies, by a child in its own
session — D-027's shape) · ``pids`` (file: own pid + descendants) · ``dump`` (file: env/argv/prompt).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time


def _orphan(parent: int, line: str) -> None:
    """Outlive the process tree, then write one late line into the inherited stdout."""
    while os.getppid() == parent:
        time.sleep(0.02)
    sys.stdout.buffer.write((line + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


def main() -> int:
    if sys.argv[1] == "--orphan":
        _orphan(int(sys.argv[2]), sys.argv[3])
        return 0
    with open(sys.argv[1], encoding="utf-8") as fh:
        plan = json.load(fh)
    prompt = sys.stdin.buffer.read().decode("utf-8", "replace")
    if plan.get("dump"):
        with open(plan["dump"], "w", encoding="utf-8") as fh:
            json.dump({"env": dict(os.environ), "argv": sys.argv[2:], "prompt": prompt}, fh)
    # Descendants first, so the pid file exists before the adapter's deadline can fire.
    pids = [os.getpid()]
    if plan.get("grandchild"):
        pids.append(subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]).pid)
    if plan.get("survivor"):
        pids.append(subprocess.Popen([sys.executable, __file__, "--orphan", str(os.getpid()), plan["survivor"]],
                                     start_new_session=True).pid)
    if plan.get("pids"):
        with open(plan["pids"], "w", encoding="utf-8") as fh:
            fh.write("\n".join(map(str, pids)))
    out = sys.stdout.buffer
    for line in plan.get("lines", []):
        out.write((line + "\n").encode("utf-8"))
        out.flush()
    if plan.get("trailing"):
        out.write(plan["trailing"].encode("utf-8"))
        out.flush()
    if plan.get("stderr"):
        sys.stderr.write(plan["stderr"])
        sys.stderr.flush()
    time.sleep(plan.get("sleep", 0))
    return int(plan.get("exit", 0))


if __name__ == "__main__":
    sys.exit(main())
