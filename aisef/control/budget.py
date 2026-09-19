"""In-flight budget reservation.

Two costs matter to the harness:

* the cost the provider bills the user for tokens and tool calls;
* the wall-clock time and turns the user is willing to wait before declaring
  the run dead.

Both can blow up across concurrent runs (``aisef run`` + ``aisef improve``
+ a notebook example).  Counting them after the call is too late: by then the
charge has happened or the timeout has already aborted.  This module makes
the reservation **before** the call and settles it **after**, with a hard
ceiling that the harness cannot exceed.

Local-first.
    The provider is not always known at import time.  The default is a pure
    offline implementation that counts turns + wall-clock time and persists
    ``tokens`` and ``cost_usd`` if the caller supplies them; remote cost is
    an explicit provider that the deployer has to opt into.  No HTTP, no
    daemon, no background thread.

Two interfaces.

* ``BudgetLedger`` — pure data, persistent across processes.  Holds the
  reservation state in a single JSON file under ``_bmad-output/``.
* ``BudgetGuard`` — the reservation call the caller makes before each
  paid ``ClientAdapter.run``.  Acquires the ledger lock, raises
  ``BudgetExceeded`` when the cap is reached, returns a token to settle
  when the call returns.
"""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .._compat import atomic_replace, flock_ex_nb, flock_un, open_lock_fd


BUDGET_FILE = Path("_bmad-output") / "budget.json"
BUDGET_LOCK = Path("_bmad-output") / "budget.json.lock"
BUDGET_VERSION = 1


class BudgetExceeded(RuntimeError):
    """Raised when a reservation would exceed the configured cap."""


class BudgetLocked(BudgetExceeded):
    """The ledger is locked by another writer: contention, not a cap. Kept a subclass so every handler that
    catches `BudgetExceeded` still does; the kernel tells them apart (SS-21: contention was reported as a cap
    and charged to the developer)."""


@dataclass
class BudgetState:
    """Pure data: current ledger entries plus the global cap."""

    cap_usd: float = 0.0
    cap_turns: int = 0
    cap_seconds: float = 0.0
    spent_usd: float = 0.0
    spent_turns: int = 0
    started_at: float = 0.0
    reservations: list[dict] = field(default_factory=list)
    #: Reservations released because their owner died or their term expired (F5 / SS-52) — the last 50, with why.
    released: list[dict] = field(default_factory=list)
    #: Chiều đã cảnh báo ("usd"/"turns"/"seconds"). Ghi xuống đĩa để một lần
    #: chạm ngưỡng kêu **một lần**, không kêu ở mọi lượt gọi còn lại.
    warned: list[str] = field(default_factory=list)
    version: int = BUDGET_VERSION

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "cap_usd": self.cap_usd,
            "cap_turns": self.cap_turns,
            "cap_seconds": self.cap_seconds,
            "spent_usd": self.spent_usd,
            "spent_turns": self.spent_turns,
            "started_at": self.started_at,
            "reservations": list(self.reservations),
            "released": list(self.released),
            "warned": list(self.warned),
        }

    @staticmethod
    def from_dict(d: dict) -> "BudgetState":
        return BudgetState(
            version=int(d.get("version") or BUDGET_VERSION),
            cap_usd=float(d.get("cap_usd") or 0.0),
            cap_turns=int(d.get("cap_turns") or 0),
            cap_seconds=float(d.get("cap_seconds") or 0.0),
            spent_usd=float(d.get("spent_usd") or 0.0),
            spent_turns=int(d.get("spent_turns") or 0),
            started_at=float(d.get("started_at") or 0.0),
            reservations=list(d.get("reservations") or []),
            released=list(d.get("released") or []),
            warned=[str(x) for x in (d.get("warned") or [])],
        )


@dataclass
class BudgetLedger:
    """On-disk ledger of budget reservations and settlements."""

    root: Path

    @property
    def path(self) -> Path:
        return self.root / BUDGET_FILE

    @property
    def lock_path(self) -> Path:
        # Sidecar lock file.  The state file is rewritten via ``os.replace``,
        # which swaps the inode on filesystems where ``os.replace`` is not
        # in-place (macOS APFS, several network FS).  An exclusive flock
        # held on the state file would be left dangling on the orphan inode
        # while a new fd on the new inode slips past the lock.  Locking a
        # never-replaced sidecar keeps the lock stable across save() calls.
        return self.root / BUDGET_LOCK

    def load(self) -> BudgetState:
        if not self.path.exists():
            return BudgetState()
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return BudgetState.from_dict(json.load(fh))
        except (OSError, json.JSONDecodeError):
            return BudgetState()

    def save(self, state: BudgetState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state.to_dict(), fh, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        atomic_replace(tmp, self.path)


@dataclass
class BudgetConfig:
    """Caller-supplied caps.  Zero = unbounded for that dimension."""

    cap_usd: float = 0.0
    cap_turns: int = 0
    cap_seconds: float = 0.0

    def write_to(self, state: BudgetState) -> BudgetState:
        state.cap_usd = float(self.cap_usd or 0.0)
        state.cap_turns = int(self.cap_turns or 0)
        state.cap_seconds = float(self.cap_seconds or 0.0)
        if not state.started_at:
            state.started_at = time.time()
        return state


@dataclass
class BudgetGuard:
    """Acquire before each paid call, settle after."""

    ledger: BudgetLedger

    @contextmanager
    def reserve(self, *, story_id: str = "", attempt: int = 0,
                est_turns: int = 1, est_usd: float = 0.0,
                est_seconds: float = 0.0, label: str = ""):
        if not _has_at_least_one(self.ledger.load()):
            # No cap configured — short-circuit, no I/O.
            yield _Reservation(token=None, spent_usd=0.0, spent_turns=0)
            return

        lock_path = self.ledger.lock_path
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = open_lock_fd(lock_path)
        try:
            flock_ex_nb(fd)
        except (BlockingIOError, OSError) as e:
            os.close(fd)
            raise BudgetLocked(
                f"budget ledger locked by another writer ({e})") from e
        try:
            state = self.ledger.load()
            _check_caps(state, est_usd=est_usd, est_turns=est_turns,
                        est_seconds=est_seconds)
            _prune_dead_reservations(state)                          # SS-52: a killed run's reservation dies with it
            rid = f"{int(time.time() * 1000)}-{attempt}-{story_id}"
            from .state import machine_id
            state.reservations.append({
                "id": rid, "story": story_id, "label": label,
                "est_usd": float(est_usd), "est_turns": int(est_turns),
                "est_seconds": float(est_seconds), "at": time.time(),
                "owner": machine_id(), "expires_at": time.time() + max(2 * float(est_seconds or 0), 600.0),
            })
            self.ledger.save(state)
            token = _Reservation(
                token=rid, spent_usd=state.spent_usd,
                spent_turns=state.spent_turns,
            )
            try:
                yield token
                _settle(self.ledger, state, rid,
                        actual_usd=token.actual_usd,
                        actual_turns=token.actual_turns,
                        actual_seconds=token.actual_seconds)
            except BaseException:
                # On any error, refund the reservation so the next attempt
                # can still run if there's room.
                _refund(state, rid)
                self.ledger.save(state)
                raise
        finally:
            flock_un(fd)
            os.close(fd)

    def configure(self, cfg: BudgetConfig) -> None:
        state = self.ledger.load()
        cfg.write_to(state)
        self.ledger.save(state)


@dataclass
class _Reservation:
    token: str | None
    spent_usd: float = 0.0
    spent_turns: int = 0
    actual_usd: float = 0.0
    actual_turns: int = 0
    actual_seconds: float = 0.0


#: Cảnh báo khi tiêu tới đây. Chặn là tại trần; cảnh báo phải tới **trước** đó
#: đủ sớm để người còn kịp quyết định, và đủ muộn để không kêu suốt. Đo trên
#: `todo-e2e`: một phiên đơn lẻ chiếm 42 % token của cả dự án — nếu chỉ có
#: chặn-tại-trần thì lần đầu người biết là lúc story dừng giữa chừng.
WARN_FRACTION = 0.8


def _canh_bao(state: BudgetState) -> list[str]:
    """Câu cảnh báo cho chiều nào vừa vượt ngưỡng, và **đánh dấu đã kêu**.

    Có số thật trong câu: "sắp hết ngân sách" không giúp ai quyết định gì.
    """
    ra: list[str] = []
    da_tieu = (("usd", state.spent_usd, state.cap_usd, "${:.2f}"),
               ("turns", float(state.spent_turns), float(state.cap_turns), "{:.0f} lượt"),
               ("seconds", (time.time() - state.started_at) if state.started_at else 0.0,
                state.cap_seconds, "{:.0f}s"))
    for ten, tieu, tran, mau in da_tieu:
        if not tran or ten in state.warned or tieu < tran * WARN_FRACTION:
            continue
        state.warned.append(ten)
        ra.append(f"⚠ ngân sách: đã dùng {mau.format(tieu)} / {mau.format(tran)} "
                  f"({tieu / tran:.0%} trần {ten}) — vượt trần sẽ **dừng trước khi gọi model**")
    return ra


def _has_at_least_one(state: BudgetState) -> bool:
    return bool(state.cap_usd or state.cap_turns or state.cap_seconds
                or state.spent_usd or state.spent_turns or state.started_at)


def _reservation_live(r: dict) -> bool:
    """A reservation counts while its owner is not known dead on this host and its term has not expired (SS-52)."""
    from .state import claim_is_orphaned
    owner = str(r.get("owner") or "")
    if owner and claim_is_orphaned(owner):
        return False
    exp = float(r.get("expires_at") or 0.0)
    return not exp or exp > time.time()


def _prune_dead_reservations(state: BudgetState) -> list[dict]:
    dead = [r for r in state.reservations if not _reservation_live(r)]
    if dead:
        state.reservations = [r for r in state.reservations if _reservation_live(r)]
        for r in dead:
            why = "term expired" if float(r.get("expires_at") or 0.0) <= time.time() else "owner dead"
            state.released = (state.released + [{**r, "released_at": time.time(), "why": why}])[-50:]   # the record
            print(f"budget: released reservation {r.get('id')} of {r.get('owner') or 'an unknown owner'} "
                  f"({why}): ${float(r.get('est_usd') or 0):.2f}", file=sys.stderr)
    return dead


def _check_caps(state: BudgetState, *, est_usd: float, est_turns: int,
                est_seconds: float) -> None:
    # In-flight reservations must count toward cap usage; otherwise two
    # reserves that each fit below the cap but together exceed it slip
    # through the per-call check and only blow the cap at settle time,
    # after the spend has already happened.
    live = [r for r in state.reservations if _reservation_live(r)]      # SS-52: the dead and the expired do not count
    reserved_usd = sum(float(r.get("est_usd") or 0.0) for r in live)
    reserved_turns = sum(int(r.get("est_turns") or 0) for r in live)
    if state.cap_usd:
        if state.spent_usd + reserved_usd + est_usd > state.cap_usd:
            raise BudgetExceeded(
                f"cost cap reached: spent=${state.spent_usd:.2f}, "
                f"reserved=${reserved_usd:.2f}, "
                f"reserve=${est_usd:.2f}, cap=${state.cap_usd:.2f}")
    if state.cap_turns:
        if state.spent_turns + reserved_turns + est_turns > state.cap_turns:
            raise BudgetExceeded(
                f"turn cap reached: spent={state.spent_turns}, "
                f"reserved={reserved_turns}, "
                f"reserve={est_turns}, cap={state.cap_turns}")
    if state.cap_seconds and state.started_at:
        elapsed = time.time() - state.started_at + est_seconds
        if elapsed > state.cap_seconds:
            raise BudgetExceeded(
                f"wall-clock cap reached: elapsed={elapsed:.0f}s "
                f"(cap={state.cap_seconds:.0f}s)")


def _settle(ledger: BudgetLedger, state: BudgetState, rid: str,
            *, actual_usd: float, actual_turns: int, actual_seconds: float) -> None:
    state.reservations = [r for r in state.reservations if r.get("id") != rid]
    state.spent_usd = round(state.spent_usd + max(0.0, actual_usd), 4)
    state.spent_turns = state.spent_turns + max(0, actual_turns)
    for cau in _canh_bao(state):
        print(cau, file=sys.stderr)
    # Re-check after settle: a long call may have blown the cap on its own.
    try:
        _check_caps(state, est_usd=0, est_turns=0, est_seconds=0)
    finally:
        # Lưu cả khi vượt trần: cờ đã-cảnh-báo và số đã tiêu là sự thật, mất nó
        # thì lần chạy sau kêu lại từ đầu và đếm lại từ đầu.
        ledger.save(state)


def _refund(state: BudgetState, rid: str) -> None:
    state.reservations = [r for r in state.reservations if r.get("id") != rid]


__all__ = [
    "BudgetLedger", "BudgetGuard", "BudgetConfig", "BudgetState",
    "BudgetExceeded", "BUDGET_FILE", "BUDGET_LOCK", "BUDGET_VERSION",
]
