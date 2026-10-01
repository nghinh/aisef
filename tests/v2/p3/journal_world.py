"""Shared P3 test helpers: a temporary journal, and the payloads of a small valid run (journal format 1)."""

import os
import pathlib
import tempfile

from aisef2.arch.enums import EventType as T
from aisef2.journal.writer import JournalWriter

SHA_A, SHA_B = "a" * 40, "b" * 40
BEGIN = {"journal_format": 1, "run_id": "run-1"}


def failure(story, code="PROBE_UNRUNNABLE", owner="ENVIRONMENT", retryable=True, **extra):
    return {"story_id": story, "code": code, "owner": owner, "retryable": retryable, "detail": "", **extra}


def observed(story, code="PROBE_UNRUNNABLE", **extra):
    """A failure/observed as a call site appends it: the code only; the journal carries owner and retryable."""
    return {"story_id": story, "code": code, "detail": "", **extra}


def admitted(story, dispositions, parent=SHA_A):
    blocked = any(d in ("PRECONDITION_BROKEN", "PLAN_CONTRADICTION", "PROBE_UNRUNNABLE", "PROBE_INVALID")
                  for d in dispositions.values())
    return {"story_id": story, "parent": parent, "admitted": not blocked,
            "developer_call_permitted": not blocked and "READY" in dispositions.values(),
            "dispositions": dispositions}


class Journals:
    """A mixin: `self.writer()` opens a fresh journal in a temporary directory that the test removes."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(prefix="aisef2-journal-")
        self.addCleanup(self._dir.cleanup)
        self.path = pathlib.Path(self._dir.name, "journal.jsonl")
        self.clock = iter(float(n) for n in range(10 ** 6))

    def writer(self, path=None, begin=True):
        w = JournalWriter(path or self.path, clock=lambda: next(self.clock))
        self.addCleanup(w.close)
        if begin and not w.events:
            w.append(T.RUN_BEGIN, BEGIN)
        return w

    def text(self, path=None):
        return pathlib.Path(path or self.path).read_bytes().decode("utf-8")

    def rewrite(self, lines, path=None):
        pathlib.Path(path or self.path).write_bytes("".join(lines).encode("utf-8"))

    def size(self, path=None):
        return os.path.getsize(path or self.path)
