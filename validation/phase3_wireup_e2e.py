#!/usr/bin/env python3
"""End-to-end validation of the Phase 3 wire-up without paid calls.

Exercises every cross-tier seam pinned by ADR-009 against a scratch
project and a tiny in-memory dev server.  Records observations in
``validation/phase3-report.md`` next to this script.  Exits non-zero
if any step fails.

Steps:
  1. Scratch project + loaded Config (verify new keys surface).
  2. Pre-flight qualification policy in three states
     (ready / failed-and-retryable / stuck).
  3. Budget guard: short-circuit (no caps) + cap-block before dispatch
     + refund on exception + idempotent settle.
  4. Server identity lease: bind a port for ``run-A``, refuse a probe
     from ``run-B``, then release and re-acquire.
  5. Findings round-trip: structured ``Finding`` instance → canonical
     lines → ``FindingBook.parse_lines`` back to instances.
  6. ``Evidence.after_event`` survives a stale higher-seq entry that
     precedes the most recent test (bug 47 cross-tier).
  7. Budget ledger sidecar lock + cap-headroom reservation math
     (Bug-48 sidecar lock + Bug-49 reservation cap-overrun).
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aisef.config import Config  # noqa: E402
from aisef.control.budget import (  # noqa: E402
    BudgetConfig,
    BudgetExceeded,
    BudgetGuard,
    BudgetLedger,
)
from aisef.control.findings import (  # noqa: E402
    Finding,
    FindingBook,
    Severity,
    Status,
    Trust,
)
from aisef.control.qualification import (  # noqa: E402
    Decision as QDecision,
    Inputs,
    PHASE_RUN,
    Profile,
    StorySnapshot,
    qualify,
)
from aisef.harness.server_identity import (  # noqa: E402
    acquire_port_lease,
    ready_with_identity,
    release_port_lease,
)


REPORT: list[str] = []


def record(stage: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    line = f"[{mark}] {stage}: {detail}".rstrip()
    REPORT.append(line)
    print(line)


def _free_port() -> int:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        try:
            s.close()
        except OSError:
            pass


class _IdentityHandler(BaseHTTPRequestHandler):
    body = b""

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/_aisef/identity"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(self.body)
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"hi")

    def log_message(self, *_a, **_k) -> None:
        return


@contextmanager
def _http_server(handler_cls):
    port = _free_port()
    srv = HTTPServer(("127.0.0.1", port), handler_cls)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield srv, port
    finally:
        srv.shutdown()
        srv.server_close()


def step_config() -> None:
    with tempfile.TemporaryDirectory() as d:
        cfg = Config.load(d)
        defaults = {
            "run.cost_cap_usd": 0.0,
            "run.turn_cap": 0,
            "run.wall_clock_cap_seconds": 0.0,
            "run.qualify_preflight": False,
        }
        missing = [k for k, v in defaults.items() if cfg.get(k) != v]
        record(
            "1.config defaults surface",
            not missing,
            f"missing={missing}" if missing else "all four knobs at default 0/false",
        )


def _make_profile(states: dict[str, str], retries: dict[str, int] | None = None,
                   attempt: int = 0, max_retries: int = 2,
                   verified: tuple[str, ...] = ()) -> tuple[Profile, Inputs]:
    pf = Profile(phase=PHASE_RUN, attempt=attempt, max_retries=max_retries)
    snaps = []
    for sid, status in states.items():
        has_candidate = sid in verified or status in ("verified", "done")
        snaps.append(StorySnapshot(sid, status, has_candidate=has_candidate,
                                   verification_ok=(status in ("verified", "done"))))
    return pf, Inputs(stories=tuple(snaps))


def step_qualify() -> None:
    # 1. Failed beyond max_retries → STOP.
    pf, inp = _make_profile({"S1": "failed"}, attempt=5, max_retries=2)
    v = qualify(pf, inp)
    record(
        "2.qualify failed+over-max-retries → STOP",
        v.decision is QDecision.STOP,
        v.reason,
    )

    # 2. Failed but still under budget → VERIFY (one more attempt).
    pf2, inp2 = _make_profile({"S1": "failed"}, attempt=1, max_retries=2)
    v2 = qualify(pf2, inp2)
    record(
        "2.qualify failed+retryable → VERIFY",
        v2.decision is QDecision.VERIFY,
        v2.reason,
    )

    # 3. Verified with no blockers → MERGE.
    pf3, inp3 = _make_profile({"S1": "verified", "S2": "verified"},
                                attempt=2, max_retries=2)
    v3 = qualify(pf3, inp3)
    record(
        "2.qualify all-verified → MERGE",
        v3.decision is QDecision.MERGE,
        v3.reason,
    )


def step_budget() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        no_guard = BudgetGuard(BudgetLedger(root))
        with no_guard.reserve(story_id="x", est_usd=999.0, est_turns=999):
            pass
        record("3.budget no-caps short-circuit", True, "999/999 accepted")

        cap_guard = BudgetGuard(BudgetLedger(root / "cap"))
        cap_guard.configure(BudgetConfig(cap_usd=1.0))
        blocked = False
        try:
            with cap_guard.reserve(story_id="y", est_usd=2.0, est_turns=1) as r:
                r.actual_usd = 0.5
        except BudgetExceeded:
            blocked = True
        state_after_block = BudgetLedger(root / "cap").load()
        record(
            "3.budget cap-block before settle",
            blocked and state_after_block.spent_usd == 0.0,
            f"blocked={blocked} spent={state_after_block.spent_usd:.4f}",
        )

        refunded = None
        try:
            with cap_guard.reserve(story_id="z", est_usd=0.5, est_turns=1):
                raise RuntimeError("simulate paid-call explosion")
        except RuntimeError:
            refunded = BudgetLedger(root / "cap").load()
        record(
            "3.budget refund on exception",
            refunded is not None and refunded.spent_usd == 0.0,
            f"spent={refunded.spent_usd:.4f} after refund",
        )

        with cap_guard.reserve(story_id="a", est_usd=0.0, est_turns=1) as r:
            r.actual_usd = 0.4
            r.actual_turns = 1
        spend = BudgetLedger(root / "cap").load()
        record(
            "3.budget settle on success",
            abs(spend.spent_usd - 0.4) < 1e-6,
            f"spent={spend.spent_usd:.4f}",
        )


def step_identity() -> None:
    with tempfile.TemporaryDirectory() as d:
        body_for_a = b"r1"
        handler = type(
            "H", (_IdentityHandler,), {"body": body_for_a}
        )
        lease_root = Path(d) / ".aisef"
        with _http_server(handler) as (srv, port):
            base = f"http://127.0.0.1:{port}"
            fd = acquire_port_lease(lease_root, "r1", base)
            if fd is None:
                record("4.identity lease acquire", False, "fd None on free port")
                return
            try:
                ok_same = ready_with_identity(base, "r1", attempts=3)
                ok_other = ready_with_identity(base, "r2", attempts=3)
                record(
                    "4.identity probe matches bound run",
                    ok_same and not ok_other,
                    f"r1={ok_same} r2={ok_other}",
                )
            finally:
                release_port_lease(lease_root, "r1", fd=fd)
            # Re-acquire on the same root after release — must succeed.
            fd2 = acquire_port_lease(lease_root, "r1", base)
            record(
                "4.identity lease re-acquire after release",
                fd2 is not None,
                f"second fd={fd2}",
            )
            if fd2 is not None:
                release_port_lease(lease_root, "r1", fd=fd2)


def step_findings() -> None:
    original = Finding.make(
        source="reviewer",
        trust=Trust.REVIEWER.value,
        severity=Severity.HIGH.value,
        file="src/foo.py",
        line=10,
        body="mismatch",
        evidence="conformance:sha123",
        prescription="refactor to match",
    )
    book = FindingBook()
    book.add(original)
    lines = [f.format_line() for f in book]
    body_text = "\n".join(lines)
    parsed = FindingBook.from_lines(lines, source="reviewer",
                                    trust=Trust.REVIEWER.value)
    record(
        "5.findings round-trip id-stable",
        len(parsed) == 1 and next(iter(parsed)).id == original.id,
        f"lines={len(lines)} ids-match={next(iter(parsed)).id == original.id}",
    )

    book2 = FindingBook()
    book2.add(Finding.make(
        source="reviewer", trust=Trust.REVIEWER.value,
        severity=Severity.HIGH.value,
        file="src/foo.py", line=10, body="mismatch",
        prescription="refactor to match",
    ))
    same = next(iter(book2)).id == original.id
    diff_id = Finding.make(
        source="reviewer", trust=Trust.REVIEWER.value,
        severity=Severity.HIGH.value,
        file="src/bar.py", line=10, body="mismatch",
        prescription="refactor to match",
    ).id
    record(
        "5.findings stable id across same/different file",
        same and diff_id != original.id,
        f"same={same} different_id={diff_id[:8]}",
    )


def step_after_event_by_position() -> None:
    """Bug 47 cross-tier: an old file_change with seq 165 written
    33 min **before** the most recent test run (seq 144) must NOT appear
    in "events after the test" — position-after-sort is what "after"
    means, not ``seq``."""
    import json as _json
    from aisef.harness.observe import EvidenceStore
    with tempfile.TemporaryDirectory() as d:
        path = EvidenceStore(d).path("S-01")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            f.write(_json.dumps({"kind": "file_change", "name": "old.py",
                                  "seq": 165, "at": 100.0,
                                  "detail": {"path": "old.py"}}) + "\n")
            f.write(_json.dumps({"kind": "tool_run", "name": "test",
                                  "seq": 144, "at": 200.0,
                                  "detail": {"ok": True}}) + "\n")
            f.write(_json.dumps({"kind": "file_change", "name": "new.py",
                                  "seq": 200, "at": 300.0,
                                  "detail": {"path": "new.py"}}) + "\n")
        ev = EvidenceStore(d).read("S-01")
        last_test = ev.last("tool_run", "test")
        paths = [e.detail["path"] for e in ev.after_event(last_test)
                 if e.kind == "file_change"]
        record(
            "6.after_event excludes older higher-seq event",
            paths == ["new.py"],
            f"paths={paths} (expected ['new.py']; old.py seq=165 pre-dates test seq=144 in time)",
        )
        # Sanity: seq-based comparison WOULD have included old.py.
        seq_view = [e.detail["path"] for e in ev.of("file_change")
                    if e.seq > last_test.seq]
        record(
            "6.seq-based view would have included stale event",
            seq_view == ["old.py", "new.py"],
            f"seq_view={seq_view} (illustrative: shows why the fix matters)",
        )


def step_budget_concurrency() -> None:
    """Concurrency sanity for the Phase 3 budget ledger:

    * sidecar lock survives ``os.replace`` of the state file;
    * cap math subtracts outstanding reservations, not just settled
      spend, so two parallel reserves cannot blow past the cap.
    """
    from aisef.control.budget import BudgetState, _check_caps
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        g1 = BudgetGuard(BudgetLedger(root))
        g2 = BudgetGuard(BudgetLedger(root))
        g1.configure(BudgetConfig(cap_usd=10.0))
        blocked = False
        try:
            with g1.reserve(story_id="outer", est_usd=0.5, est_turns=1) as r1:
                with g2.reserve(story_id="inner", est_usd=0.5, est_turns=1):
                    pass
        except BudgetExceeded:
            blocked = True
        finally:
            r1.actual_usd = 0.5
        record(
            "7.lock sidecar serialises concurrent reserves",
            blocked,
            f"second guard raised BudgetExceeded while first held the lock",
        )

        state = BudgetState(cap_usd=0.10, spent_usd=0.0)
        state.reservations = [{"est_usd": 0.06, "est_turns": 1, "id": "r1"}]
        blocked_cap = False
        try:
            _check_caps(state, est_usd=0.06, est_turns=1, est_seconds=0.0)
        except BudgetExceeded:
            blocked_cap = True
        record(
            "7.cap check counts outstanding reservations",
            blocked_cap,
            "0.06 outstanding + 0.06 proposed > 0.10 cap blocks at reserve",
        )


def main() -> int:
    step_config()
    step_qualify()
    step_budget()
    step_identity()
    step_findings()
    step_after_event_by_position()
    step_budget_concurrency()

    fails = [r for r in REPORT if r.startswith("[FAIL]")]
    summary = f"# Phase 3 end-to-end validation\n\n{len(REPORT) - len(fails)}/{len(REPORT)} checks passed.\n\n"
    summary += "## Detailed observations\n\n" + "\n".join(f"- {r}" for r in REPORT) + "\n"

    out_path = Path(__file__).parent / "phase3-report.md"
    out_path.write_text(summary, encoding="utf-8")
    print(f"\nReport written to {out_path}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
