"""Phase 12 chain watchdog (owner rule B, item 7) — qualification infrastructure, so its decision is a PURE FUNCTION of
measured signals and is tested deterministically (tests/hardening/test_p12_watchdog.py). Nothing platform-specific
decides anything: the runner only gathers signals, and a signal it cannot measure is reported as TOOL_UNAVAILABLE,
never as a stall.

Classes: PROGRESSING · STALL (alive, no measurable progress for longer than max(3 × median completed chunk, 2 h))
· DEAD (the process is gone before the chunk completed) · COMPLETE · TOOL_UNAVAILABLE.

    python3 validation/p12_watchdog.py --logs <dir> --evidence closure-evidence/hardening --starts 0 10000 … 90000
exits 0 CHAIN COMPLETE · 2 MISMATCH (a chunk recorded an unexplained trace) · 3 STALL · 4 DEAD · 5 TOOL_UNAVAILABLE
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

FLOOR_S = 2 * 3600.0
FACTOR = 3.0


@dataclass(frozen=True)
class Signals:
    alive: bool | None        # None: could not be measured
    marker: object            # any comparable progress marker (sizes, counts); None: could not be measured
    completed: bool


def limit_s(completed_durations: list[float], floor_s: float = FLOOR_S, factor: float = FACTOR) -> float:
    return max(factor * statistics.median(completed_durations), floor_s) if completed_durations else floor_s


def classify(now: float, last_change_at: float, sig: Signals, limit: float) -> str:
    if sig.completed:
        return "COMPLETE"
    if sig.alive is None or sig.marker is None:
        return "TOOL_UNAVAILABLE"
    if not sig.alive:
        return "DEAD"
    if now - last_change_at > limit:
        return "STALL"
    return "PROGRESSING"


class Tracker:
    """Remembers the last marker and when it last changed; `observe` returns the class for this tick."""

    def __init__(self, now: float):
        self.last_marker = None
        self.last_change_at = now

    def observe(self, now: float, sig: Signals, limit: float) -> str:
        if sig.marker is not None and sig.marker != self.last_marker:
            self.last_marker, self.last_change_at = sig.marker, now
        return classify(now, self.last_change_at, sig, limit)


# ---- signal providers (the only platform-touching code; every failure becomes None) ---------------------------------
def running_chunk(ps_output: str | None) -> tuple[int, int] | None | bool:
    """(pid, start) of the running differential chunk; False when none runs; None when ps could not be read."""
    if ps_output is None:
        return None
    for ln in ps_output.splitlines():
        m = re.match(r"\s*(\d+)\s+.*tests\.hardening\.differential --traces \d+ --start (\d+)", ln)
        if m:
            return int(m.group(1)), int(m.group(2))
    return False


def read_ps() -> str | None:
    try:
        return subprocess.run(["ps", "-eo", "pid=,command="], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None


def alive(pid: int) -> bool | None:
    """Liveness through the product's own cross-platform probe (aisef.control.state.pid_alive — proven on Linux, macOS and
    Windows CI). `os.kill(pid, 0)` is NOT a probe on Windows (it can terminate the process); any failure of the probe
    itself is None → TOOL_UNAVAILABLE, never a false stall or a false death."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from aisef.control.state import pid_alive
        return bool(pid_alive(pid))
    except Exception:  # noqa: BLE001 — the probe is unavailable, which is the explicit class for it
        return None


def marker_for(log: Path, rows: Path) -> tuple[int, int] | None:
    try:
        return (log.stat().st_size if log.is_file() else 0, rows.stat().st_size if rows.is_file() else 0)
    except OSError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", required=True)
    ap.add_argument("--evidence", default="closure-evidence/hardening")
    ap.add_argument("--prefix", default="differential-p12")
    ap.add_argument("--log-prefix", default="diff-p12v2")
    ap.add_argument("--starts", type=int, nargs="+", default=list(range(0, 100000, 10000)))
    ap.add_argument("--interval", type=float, default=60.0)
    a = ap.parse_args()
    ev, logs = Path(a.evidence), Path(a.logs)
    tracker, current = None, None
    while True:
        done = {}
        for s in a.starts:
            f = ev / f"{a.prefix}-{s:05d}.json"
            if f.is_file():
                try:
                    done[s] = json.loads(f.read_text(encoding="utf-8"))
                except ValueError:
                    continue
                if done[s].get("unexplained_count", 0):
                    print(f"MISMATCH chunk {s:05d}: unexplained={done[s]['unexplained_count']} seeds={[u['seed'] for u in done[s]['unexplained']][:5]}", flush=True)
                    return 2
        if all(s in done for s in a.starts):
            print("CHAIN COMPLETE: " + " ".join(f"{s}:{d['matched']}/{d['traces']}@{int(d['elapsed_s'])}s" for s, d in sorted(done.items())), flush=True)
            return 0
        rc = running_chunk(read_ps())
        now = time.time()
        if rc is None:
            print("TOOL_UNAVAILABLE: ps could not be read", flush=True)
            return 5
        if rc is False:
            time.sleep(min(30.0, a.interval))     # a chunk boundary: the next one starts within seconds
            rc = running_chunk(read_ps())
            if rc is None:
                print("TOOL_UNAVAILABLE: ps could not be read", flush=True)
                return 5
            if rc is False:
                print(f"DEAD: no differential process and the chain is incomplete; completed={sorted(done)}", flush=True)
                return 4
        pid, start = rc
        if current != start:
            current, tracker = start, Tracker(now)
        sig = Signals(alive=alive(pid), marker=marker_for(logs / f"{a.log_prefix}-{start:05d}.log", ev / f"{a.prefix}-{start:05d}.rows.jsonl"),
                      completed=(ev / f"{a.prefix}-{start:05d}.json").is_file())
        lim = limit_s([d["elapsed_s"] for d in done.values()])
        cls = tracker.observe(now, sig, lim)
        if cls == "STALL":
            print(f"STALL chunk {start:05d}: no measurable progress for {int(now - tracker.last_change_at)}s > limit {int(lim)}s; marker={sig.marker}; completed={sorted(done)}", flush=True)
            return 3
        if cls == "DEAD":
            print(f"DEAD chunk {start:05d}: pid {pid} gone before its summary was written; completed={sorted(done)}", flush=True)
            return 4
        if cls == "TOOL_UNAVAILABLE":
            print(f"TOOL_UNAVAILABLE chunk {start:05d}: alive={sig.alive} marker={sig.marker}", flush=True)
            return 5
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
