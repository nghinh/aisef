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
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .._compat import flock_ex_nb, flock_un


BUDGET_FILE = Path("_bmad-output") / "budget.json"
BUDGET_VERSION = 1


class BudgetExceeded(RuntimeError):
    """Raised when a reservation would exceed the configured cap."""


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
        )


@dataclass
class BudgetLedger:
    """On-disk ledger of budget reservations and settlements."""

    root: Path

    @property
    def path(self) -> Path:
        return self.root / BUDGET_FILE

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
        os.replace(tmp, self.path)


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

        path = self.ledger.path
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)
        try:
            flock_ex_nb(fd)
        except (BlockingIOError, OSError) as e:
            os.close(fd)
            raise BudgetExceeded(
                f"budget ledger locked by another writer ({e})") from e
        try:
            state = self.ledger.load()
            _check_caps(state, est_usd=est_usd, est_turns=est_turns,
                        est_seconds=est_seconds)
            rid = f"{int(time.time() * 1000)}-{attempt}-{story_id}"
            state.reservations.append({
                "id": rid, "story": story_id, "label": label,
                "est_usd": float(est_usd), "est_turns": int(est_turns),
                "est_seconds": float(est_seconds), "at": time.time(),
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


def _has_at_least_one(state: BudgetState) -> bool:
    return bool(state.cap_usd or state.cap_turns or state.cap_seconds
                or state.spent_usd or state.spent_turns or state.started_at)


def _check_caps(state: BudgetState, *, est_usd: float, est_turns: int,
                est_seconds: float) -> None:
    if state.cap_usd and state.spent_usd + est_usd > state.cap_usd:
        raise BudgetExceeded(
            f"cost cap reached: spent=${state.spent_usd:.2f}, "
            f"reserve=${est_usd:.2f}, cap=${state.cap_usd:.2f}")
    if state.cap_turns and state.spent_turns + est_turns > state.cap_turns:
        raise BudgetExceeded(
            f"turn cap reached: spent={state.spent_turns}, "
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
    # Re-check after settle: a long call may have blown the cap on its own.
    _check_caps(state, est_usd=0, est_turns=0, est_seconds=0)
    ledger.save(state)


def _refund(state: BudgetState, rid: str) -> None:
    state.reservations = [r for r in state.reservations if r.get("id") != rid]


__all__ = [
    "BudgetLedger", "BudgetGuard", "BudgetConfig", "BudgetState",
    "BudgetExceeded", "BUDGET_FILE", "BUDGET_VERSION",
]
