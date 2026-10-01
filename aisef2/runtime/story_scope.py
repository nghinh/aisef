"""RFC §17.1, §18 — StoryScope: an explicit ordered resource stack, disposed in reverse, one release at a time
(P4-LIFETIME-SEMANTICS.md §2).

* `acquire` pushes a resource and emits `story/resource-acquired`; acquisition is in non-increasing disposal rank
  (`format2.DISPOSAL_RANK`), so reverse disposal is processes -> sandbox -> worktree -> scratch. Acquiring while
  disposing is refused (`INACTIVE_ACQUIRE`) and the offered resource is released at once.
* `dispose` pops every resource and emits exactly one `story/resource-released` for each: `RELEASED`, `FAILED` (the
  release raised) or `RESIDUAL` (named, not released). A failure never stops the disposal of the rest; a process
  range that was not proved empty makes the sandbox, worktree and scratch after it `RESIDUAL` — they are not released
  while something could still write to them.
* The scope emits through the run's journal (`emit`, handed in by RunScope) and owns no journal writer.
"""

from __future__ import annotations

import pathlib
import shutil
import threading
from dataclasses import dataclass
from typing import Callable, Protocol

from aisef2.arch.enums import EventType as T
from aisef2.errors import InvariantError
from aisef2.journal.event import Event, JournalError
from aisef2.journal.format2 import DISPOSAL_RANK, ReleaseStatus as S, ResourceKind as K

#: The bound on one release before it is named RESIDUAL ("still running"); None waits without bound.
RELEASE_TIMEOUT_S = 600.0


class ScopeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class Residual(Exception):
    """Raised by a release that could not complete: the resource is named RESIDUAL for the next run's preflight."""


class Resource(Protocol):
    name: str
    kind: K

    def release(self) -> None: ...


@dataclass(frozen=True)
class Released:
    resource: str
    kind: str
    status: str
    detail: str
    unrecorded: str | None = None  # the journal refused the record (the release itself still happened)


@dataclass(frozen=True)
class DisposalReport:
    story_id: str
    records: tuple[Released, ...]

    @property
    def ok(self) -> bool:
        """DISPOSE succeeds only when every resource was released and recorded (§17.1: a failure MAY fail DISPOSE)."""
        return all(r.status == S.RELEASED.value and r.unrecorded is None for r in self.records)


Emit = Callable[..., Event]


class StoryScope:
    def __init__(self, story_id: str, emit: Emit, *, release_timeout_s: float | None = RELEASE_TIMEOUT_S) -> None:
        self.story_id = story_id
        self._emit = emit
        self._timeout = release_timeout_s
        self._stack: list[tuple[Resource, Event]] = []
        self._state = "ACTIVE"
        self._report: DisposalReport | None = None

    @property
    def state(self) -> str:
        return self._state

    @property
    def held(self) -> tuple[str, ...]:
        return tuple(r.name for r, _ in self._stack)

    def acquire(self, resource: Resource) -> Resource:
        kind = K(resource.kind)
        if self._state != "ACTIVE":
            self._release(resource)
            raise ScopeError("INACTIVE_ACQUIRE", f"{self.story_id} is {self._state}: {resource.name} refused and "
                                                 "released (§17.1)")
        if self._stack and DISPOSAL_RANK[kind] > DISPOSAL_RANK[K(self._stack[-1][0].kind)]:
            self._release(resource)
            raise ScopeError("ORDER", f"{kind.value} {resource.name} after {K(self._stack[-1][0].kind).value}: reverse "
                                      "disposal would release it too late (§17.1); refused and released")
        try:
            acquired = self._emit(T.STORY_RESOURCE_ACQUIRED, {"story_id": self.story_id, "resource": resource.name,
                                                              "kind": kind.value})
        except InvariantError:
            raise
        except BaseException:
            self._release(resource)
            raise
        self._stack.append((resource, acquired))
        return resource

    def release(self, resource: Resource) -> Released:
        """Release the most recently acquired resource before the scope disposes (a tool's range when the tool is done).
        Only the top of the stack: anything else would break the reverse order (§17.1)."""
        if not self._stack or self._stack[-1][0] is not resource:
            raise ScopeError("ORDER", f"{resource.name} is not the most recent resource of {self.story_id}: only the "
                                      "top of the stack is released early")
        _, acquired = self._stack.pop()
        status, detail = self._release(resource)
        return self._record(resource, K(resource.kind), status, detail, acquired)

    def dispose(self, *, abandoned: Callable[[], bool] = lambda: False) -> DisposalReport:
        """Release every resource in reverse acquisition order. `abandoned` is asked before each release: once it says
        yes (a second interrupt, §20.2), every resource left is named RESIDUAL instead of released."""
        if self._report is not None:
            return self._report
        self._state = "DISPOSING"
        records, blocked_by = [], None
        while self._stack:
            resource, acquired = self._stack.pop()
            kind = K(resource.kind)
            if blocked_by is not None and DISPOSAL_RANK[kind] > DISPOSAL_RANK[K.PROCESS_RANGE]:
                status, detail = S.RESIDUAL, f"not released: process range {blocked_by} was not proved empty (§17.1)"
            elif abandoned():
                status, detail = S.RESIDUAL, "not released: disposal was abandoned (second interrupt, §20.2)"
            else:
                status, detail = self._release(resource)
                if kind is K.PROCESS_RANGE and status is not S.RELEASED:
                    blocked_by = resource.name
            records.append(self._record(resource, kind, status, detail, acquired))
        self._state = "DISPOSED"
        self._report = DisposalReport(self.story_id, tuple(records))
        return self._report

    def _record(self, resource: Resource, kind: K, status: S, detail: str, acquired: Event) -> Released:
        try:
            self._emit(T.STORY_RESOURCE_RELEASED, {"story_id": self.story_id, "resource": resource.name,
                                                   "kind": kind.value, "status": status.value, "detail": detail,
                                                   "synthetic": False}, source_seqs=(acquired.seq,))
            unrecorded = None
        except JournalError as e:
            unrecorded = str(e)  # the journal is broken; the remaining resources are still released
        return Released(resource.name, kind.value, status.value, detail, unrecorded)

    def _release(self, resource: Resource) -> tuple[S, str]:
        box: dict = {}

        def run() -> None:
            try:
                resource.release()
                box["status"] = (S.RELEASED, "")
            except InvariantError as e:  # uncontainable (§4): carried across the thread and re-raised by the caller
                box["invariant"] = e
                raise
            except Residual as e:
                box["status"] = (S.RESIDUAL, str(e))
            except Exception as e:
                box["status"] = (S.FAILED, f"{type(e).__name__}: {e}")

        if self._timeout is None:
            run()
            return box["status"]
        t = threading.Thread(target=run, name=f"release {resource.name}", daemon=True)
        t.start()
        t.join(self._timeout)
        if "invariant" in box:
            raise box["invariant"]
        if t.is_alive():
            return S.RESIDUAL, f"not released: the release was still running after {self._timeout:g}s"
        return box["status"]


class Directory:
    """A worktree or scratch directory owned by a story. Its release removes it and checks that it is gone."""

    def __init__(self, name: str, kind: K, path: str | pathlib.Path) -> None:
        if kind not in (K.WORKTREE, K.SCRATCH, K.SANDBOX):
            raise ValueError(f"a directory resource is a worktree, sandbox or scratch, not {kind.value}")
        self.name, self.kind, self.path = name, kind, pathlib.Path(path)

    def release(self) -> None:
        if self.path.exists():
            shutil.rmtree(self.path)
        if self.path.exists():
            raise Residual(f"{self.path} still exists after its removal")
