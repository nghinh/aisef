"""RFC §20.2 — one tool operation of a story, run inside its own process range (WP-4.6; P4-LIFETIME-SEMANTICS.md §7).

* `dispatch` starts the range, acquires it into the story's scope and writes `tool/invoked`.
* `finish` records the tool's exit as `tool/result` — COMPLETED (0), FAILED (its exit status) or SIGNALLED with the
  signal and its provenance: CONTROLLER when this range's ledger holds that signal (the controller stopped it),
  UNKNOWN otherwise — then releases the range. A signal exit is a fact about a process, never an owner: nothing here
  writes a failure code (INTERRUPT-SIG-1, INTERRUPT-SIG-2).
* `close` is the interruption closer: a synthetic `tool/result`, NOT_STARTED if the call was never dispatched,
  OUTCOME_UNKNOWN if it was (INTERRUPT-SIG-3). What the tool did before it was stopped is not known, so no measured
  outcome is invented.
"""

from __future__ import annotations

import os
import signal as _signal
from typing import Mapping, Sequence

from aisef2.arch.enums import EventType as T
from aisef2.journal.event import Event
from aisef2.journal.format2 import OperationOutcome as O, SignalProvenance as S
from aisef2.runtime.process_range import BACKEND, ProcessRange


def outcome(returncode: int | None, anchor_returncode: int | None, ledger: Sequence[Mapping],
            backend=BACKEND) -> dict:
    """The measured outcome of a finished range's target, with the provenance of any signal (tool/result fields).
    `backend` is the range's OS adapter, which alone knows how a controller's stop shows in an exit status."""
    sent = {s["signal"] for s in ledger}

    def signalled(sig: int, detail: str) -> dict:
        try:
            name = _signal.Signals(sig).name
        except ValueError:
            name = f"signal {sig}"
        mine = name in sent
        return {"outcome": O.SIGNALLED.value, "signal": sig,
                "provenance": (S.CONTROLLER if mine else S.UNKNOWN).value,
                "detail": f"{detail}: {name}, {'sent by the controller' if mine else 'not sent by the controller'}"}
    if returncode == 0:
        return {"outcome": O.COMPLETED.value, "signal": 0, "provenance": S.NONE.value, "detail": ""}
    if backend.controller_stopped(returncode, ledger):
        return {"outcome": O.SIGNALLED.value, "signal": 9, "provenance": S.CONTROLLER.value,
                "detail": "terminated with its job by the controller (TerminateJobObject)"}
    if returncode is not None and returncode < 0:
        return signalled(-returncode, "the tool died by a signal")
    if returncode is None and anchor_returncode is not None and anchor_returncode < 0:
        return signalled(-anchor_returncode, "the range died by a signal before the tool's status was reported")
    return {"outcome": O.FAILED.value, "signal": 0, "provenance": S.NONE.value,
            "detail": f"exit status {returncode}" if returncode is not None else "exit status not reported"}


class ToolCall:
    def __init__(self, run, story_id: str, call_id: str, tool: str, argv: Sequence[str], *,
                 cwd: str | os.PathLike | None = None, env: Mapping[str, str] | None = None, **range_kw) -> None:
        self.run, self.story_id, self.call_id, self.tool = run, story_id, call_id, tool
        self.range = ProcessRange(f"tool {call_id}", argv, cwd=cwd, env=env, **range_kw)
        self.state = "PENDING"
        self._invoked: Event | None = None
        self.recorded: Event | None = None
        run.register(self)

    def _data(self, fields: dict, synthetic: bool = False) -> dict:
        return {"story_id": self.story_id, "call_id": self.call_id, **fields, "synthetic": synthetic}

    def dispatch(self) -> Event:
        if self.state != "PENDING":
            raise RuntimeError(f"call {self.call_id} is {self.state}")
        scope = self.run.story(self.story_id)
        scope.acquire(self.range.start())
        self._invoked = self.run.append(T.TOOL_INVOKED, {"story_id": self.story_id, "call_id": self.call_id,
                                                         "tool": self.tool})
        self.state = "DISPATCHED"
        return self._invoked

    def finish(self, timeout: float | None = None) -> Event:
        """Wait for the tool; stop it (graceful-first) if it is still running after `timeout`; record and release."""
        if self.state != "DISPATCHED":
            raise RuntimeError(f"call {self.call_id} is {self.state}")
        scope = self.run.story(self.story_id)
        code = self.range.wait(timeout)
        released = None
        if code is None:
            released = scope.release(self.range)  # the ladder: the ledger now says what the controller sent
            code = self.range.returncode
        fields = outcome(code, self.range.anchor_returncode, self.range.ledger)
        self.recorded = self.run.append(T.TOOL_RESULT, self._data(fields), source_seqs=(self._invoked.seq,))
        if released is None:
            scope.release(self.range)
        self.state = "DONE"
        return self.recorded

    def close(self) -> Event | None:
        """The interruption closer, synthetic; nothing for a call that already has its result."""
        if self.state in ("DONE", "CLOSED"):
            return None
        if self.state == "PENDING":
            self.recorded = self.run.append(T.TOOL_RESULT, self._data(
                {"outcome": O.NOT_STARTED.value, "signal": 0, "provenance": S.NONE.value,
                 "detail": "interrupted before dispatch"}, synthetic=True))
        else:
            self.recorded = self.run.append(T.TOOL_RESULT, self._data(
                {"outcome": O.OUTCOME_UNKNOWN.value, "signal": 0, "provenance": S.NONE.value,
                 "detail": "interrupted after dispatch: what the tool did is not known"}, synthetic=True),
                source_seqs=(self._invoked.seq,))
        self.state = "CLOSED"
        return self.recorded
