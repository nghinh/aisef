"""RFC §18, §18.1 — RunScope and the run lease: the lifetime order (F8; P4-LIFETIME-SEMANTICS.md §4).

**Begin** (normative): acquire the run lease -> (preflight: the previous run, read under the lease) -> write and fsync
the `OPEN` sentinel -> open the journal writer (`run/begin`) -> resolve and freeze the RunSpec (`capability/resolved`
..., `run/spec-resolved`) -> execution.

**Shutdown** (normative): every StoryScope disposed, every story ENDED -> `run/dispose-begin` -> `run/end` -> the
writer closed successfully -> `CLEAN` written and fsync'd -> the lease released **last**. A writer that fails to close,
or a `CLEAN` that cannot be recorded, leaves the sentinel `OPEN` (RUN-3, RUN-4); the lease is still released last.
The lease is an OS file lock, so a run that dies releases it with its process; while a run holds it no second run
begins, whatever its journal says (RUN-2).

RunScope owns the journal writer, the lease, the run identity, the RunSpec and the sentinel; a StoryScope emits
through `append` (its journal) and owns no writer. `trace` is the lifetime order as executed.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import signal as _signal
import threading
import time as _time
from typing import Any, Callable, Mapping

from aisef2.arch.enums import ControlProjection as P, EventType as T
from aisef2.control import budget
from aisef2.journal.event import Event, JournalError
from aisef2.journal.fold import Authority
from aisef2.journal.format3 import FORMAT, JournalWriter3
from aisef2.journal.projections import PROJECTIONS
from aisef2.runtime import sentinel
from aisef2.runtime.story_scope import DisposalReport, StoryScope

BEGIN_ORDER = ("lease", "sentinel OPEN", "journal writer", "RunSpec", "execution")
SHUTDOWN_ORDER = ("story scopes disposed", "run/dispose-begin", "run/end", "journal writer closed", "sentinel CLEAN",
                  "lease released")


class LeaseHeld(Exception):
    """Another run holds the run lease (RUN-2): this run does not begin."""


class ShutdownRefused(Exception):
    """A successful shutdown is refused before anything is written: a story is still open (§18)."""


class RetryRefused(Exception):
    """The journal-derived budget decision says no retry (§17 RETRY, §22). `charge` says why."""

    def __init__(self, charge) -> None:
        super().__init__(charge.reason)
        self.charge = charge


class RunLease:
    """The outermost ownership boundary: an exclusive, non-blocking OS lock on one file, held for the run's life."""

    def __init__(self, path: str | os.PathLike) -> None:
        self.path = pathlib.Path(path)
        self._fd: int | None = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> None:
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
        try:
            if os.name == "posix":
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            os.close(fd)
            raise LeaseHeld(f"{self.path} is held by another run") from None
        self._fd = fd

    def release(self) -> None:
        if self._fd is not None:
            fd, self._fd = self._fd, None
            os.close(fd)  # closing the descriptor releases the lock (flock and LockFile alike)


class RunScope:
    def __init__(self, root: str | os.PathLike, run_id: str, *, spec: Callable[[], Any],
                 clock: Callable[[], float] = _time.time) -> None:
        self.root = pathlib.Path(root)
        self.run_id = run_id
        self._resolve = spec
        self._clock = clock
        self.lease = RunLease(self.root / "run.lease")
        self.sentinel_path = self.root / "run.sentinel"
        self.journal_path = self.root / "journals" / f"{run_id}.jsonl"   # an execution locator, never an identity
        self.trace: list[str] = []
        self.preflight: sentinel.Preflight | None = None
        self.spec: Any = None
        self._writer: JournalWriter3 | None = None
        self._authority: Authority | None = None
        self._scopes: dict[str, StoryScope] = {}
        self._calls: list = []          # tool calls, so an interruption can close the unfinished ones
        self._frozen: float | None = None
        self._abandon = False
        self._state = "NEW"

    # ---- begin
    def begin(self) -> sentinel.Preflight:
        if self._state != "NEW":
            raise JournalError(f"run {self.run_id} is {self._state}: a RunScope begins once")
        self.root.mkdir(parents=True, exist_ok=True)
        self.lease.acquire()
        self.trace.append("lease")
        try:
            self.preflight = sentinel.preflight(self.sentinel_path)   # a state read, under the lease (§18.1)
            self.journal_path.parent.mkdir(exist_ok=True)  # the root exists: it holds the lease
            sentinel.mark_open(self.sentinel_path, self.run_id, self.journal_path)
            self.trace.append("sentinel OPEN")
            self._writer = JournalWriter3(self.journal_path, clock=self._now)  # format 3 (V2-005)
            self._authority = Authority(self._writer, PROJECTIONS.values())
            self._authority.append(T.RUN_BEGIN, {"journal_format": FORMAT, "run_id": self.run_id})
            self.trace.append("journal writer")
            self.spec = self._resolve()
            for c in self.spec.capabilities:
                self._authority.append(T.CAPABILITY_RESOLVED, c.resolved())
            self._authority.append(T.RUN_SPEC_RESOLVED, self.spec.resolved())
            self.trace.append("RunSpec")
        except BaseException:
            self._fail()
            raise
        self._state = "RUNNING"
        self.trace.append("execution")
        return self.preflight

    def _now(self) -> float:
        """The event clock; closers reuse the last real event's time instead (§20.2), so repair is idempotent."""
        return self._frozen if self._frozen is not None else self._clock()

    # ---- execution
    def append(self, event_type: T, data: Mapping, source_seqs: tuple[int, ...] = ()) -> Event:
        """Append through the six projections' pre-check: an event any of them refuses never reaches the log."""
        if self._state not in ("RUNNING", "INTERRUPTED"):
            raise JournalError(f"run {self.run_id} is {self._state}: nothing more is appended")
        return self._authority.append(event_type, data, source_seqs=source_seqs)

    def state(self, projection: P) -> Any:
        return self._authority.state(projection.value)

    @property
    def events(self) -> tuple[Event, ...]:
        return self._writer.events if self._writer is not None else ()

    def retry(self, story_id: str, limits: Mapping) -> Event:
        """RETRY, only against the budget the story's latest failure names and only within its resolved count — decided
        from the journal (`budget.charge`), never from a counter."""
        decision = budget.charge(self.events, story_id, limits)
        if not decision.retry:
            raise RetryRefused(decision)
        return self.append(T.STORY_RETRY, {"story_id": story_id}, source_seqs=(decision.failure_seq,))

    def register(self, call) -> None:
        self._calls.append(call)

    def story(self, story_id: str, **kw) -> StoryScope:
        """The StoryScope of a story's current attempt; it emits through this run's journal."""
        scope = self._scopes.get(story_id)
        if scope is None or scope.state == "DISPOSED":
            scope = self._scopes[story_id] = StoryScope(story_id, self.append, **kw)
        return scope

    # ---- shutdown
    def open_stories(self) -> list[str]:
        """Stories whose attempt is not ENDED (story_state): a successful shutdown refuses them."""
        return [s for s, v in self.state(P.STORY_STATE).items() if v["state"] != "ENDED"]  # in story order

    def shutdown(self) -> list[DisposalReport]:
        """The successful shutdown, in the normative order. Refused, with nothing written, while a story is open."""
        if self._state != "RUNNING":
            raise ShutdownRefused(f"run {self.run_id} is {self._state}")
        still_open = self.open_stories()
        if still_open:
            raise ShutdownRefused(f"stories {still_open} are not ENDED: a successful shutdown would leave them "
                                  "logically open (§18); interrupt the run instead")
        reports = [s.dispose() for s in self._scopes.values()]
        self.trace.append("story scopes disposed")
        self.append(T.RUN_DISPOSE_BEGIN, {})
        self.trace.append("run/dispose-begin")
        self.append(T.RUN_END, {})
        self.trace.append("run/end")
        self._finish()
        return reports

    # ---- interruption (§20.2)
    @contextlib.contextmanager
    def interruptible(self):
        """Run the body; a KeyboardInterrupt (SIGINT) interrupts the run instead of escaping it."""
        try:
            yield self
        except KeyboardInterrupt:
            self.interrupt()

    def interrupt(self) -> list[DisposalReport]:
        """The first interrupt: `run/interrupted`; every unfinished operation closed (NOT_STARTED / OUTCOME_UNKNOWN,
        synthetic); every StoryScope disposed, graceful-first; `run/dispose-begin`, `run/end`. A second interrupt while
        that runs abandons: what is left is named RESIDUAL, `run/interrupted {abandoned: true}` is written, and nothing
        follows it. An interrupted run is not a successful termination: the sentinel stays OPEN (the next preflight
        reports TORN, with the journal's account). The lease is released last."""
        if self._state == "INTERRUPTED":
            self._abandon = True  # the second interrupt, from inside disposal
            return []
        if self._state != "RUNNING":
            raise ShutdownRefused(f"run {self.run_id} is {self._state}: it cannot be interrupted")
        self.append(T.RUN_INTERRUPTED, {"abandoned": False})
        self._state = "INTERRUPTED"
        self.trace.append("interrupted")
        self._frozen = self.events[-1].time
        try:
            for call in self._calls:
                call.close()
            answered = {e.source_seqs[0] for e in self.events if e.type == T.PROVIDER_RESULT.value}
            for e in [e for e in self.events if e.type == T.PROVIDER_REQUEST.value and e.seq not in answered]:
                self.append(T.PROVIDER_RESULT, {"story_id": e.data["story_id"], "outcome": "OUTCOME_UNKNOWN",
                                                "synthetic": True, "detail": "interrupted before its result"},
                            source_seqs=(e.seq,))
        finally:
            self._frozen = None
        self.trace.append("operations closed")
        with self._second_interrupt_abandons():
            reports = [s.dispose(abandoned=lambda: self._abandon) for s in self._scopes.values()]
        self.trace.append("story scopes disposed")
        if self._abandon:
            self.append(T.RUN_INTERRUPTED, {"abandoned": True})
            self.trace.append("abandoned")
        else:
            self.append(T.RUN_DISPOSE_BEGIN, {})
            self.append(T.RUN_END, {})
            self.trace.append("run/end")
        self._state = "ENDED"
        try:
            self._writer.close()
            self.trace.append("journal writer closed")
        finally:
            self.lease.release()
            self.trace.append("lease released")
        return reports

    @contextlib.contextmanager
    def _second_interrupt_abandons(self):
        if threading.current_thread() is not threading.main_thread():
            yield
            return
        previous = _signal.signal(_signal.SIGINT, lambda *_: self.interrupt())
        try:
            yield
        finally:
            _signal.signal(_signal.SIGINT, previous)

    def _finish(self) -> None:
        """Writer closed -> CLEAN -> lease released last. A failure leaves the sentinel OPEN and still releases."""
        self._state = "ENDED"
        try:
            self._writer.close()
            self.trace.append("journal writer closed")
            sentinel.mark_clean(self.sentinel_path, self.run_id)
            self.trace.append("sentinel CLEAN")
        finally:
            self.lease.release()
            self.trace.append("lease released")

    def _fail(self) -> None:
        """A begin that failed: the writer, if open, is closed; the sentinel stays as it is (OPEN, if written: TORN is
        conservative); the lease is released last."""
        self._state = "FAILED"
        try:
            if self._writer is not None:
                self._writer.close()
        finally:
            self.lease.release()
            self.trace.append("lease released")
