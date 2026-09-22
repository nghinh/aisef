"""Shared P4 test helpers: a temporary format-2 journal and small resources that record what happened to them."""

import pathlib
import tempfile
import threading
import time

from aisef2.arch.enums import EventType as T
from aisef2.journal.format2 import JournalWriter2, ResourceKind as K
from aisef2.runtime.story_scope import Residual

SHA = "a" * 40
BEGIN = {"journal_format": 2, "run_id": "run-p4"}


class Journal2:
    """A mixin: `self.writer()` opens a fresh format-2 journal (run/begin written) that the test removes."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(prefix="aisef2-p4-")
        self.addCleanup(self._dir.cleanup)
        self.dir = pathlib.Path(self._dir.name)
        self.path = self.dir / "journal.jsonl"
        self.clock = iter(float(n) for n in range(10 ** 6))

    def writer(self, path=None, begin=True):
        w = JournalWriter2(path or self.path, clock=lambda: next(self.clock))
        self.addCleanup(w.close)
        if begin and not w.events:
            w.append(T.RUN_BEGIN, BEGIN)
        return w

    def story(self, w, story="S1"):
        w.append(T.STORY_BEGIN, {"story_id": story, "parent": SHA})
        return story

    def text(self, path=None):
        return pathlib.Path(path or self.path).read_bytes().decode("utf-8")


def closed_after(test, run):
    """Register a run's cleanup: the lease released and its journal writer closed, whatever the test does with it.
    Windows cannot remove a temporary directory whose journal is still open."""
    test.addCleanup(run.lease.release)
    test.addCleanup(lambda: run._writer.close() if run._writer is not None else None)
    return run


def emitter(w):
    """StoryScope's emit, as RunScope hands it one: the run's journal, never a writer of its own."""
    return lambda t, data, source_seqs=(): w.append(t, data, source_seqs=source_seqs)


class Fake:
    """A resource whose release is recorded in `log`; `fail`, `residual` or `hang` make it misbehave."""

    def __init__(self, name, kind=K.SESSION, log=None, fail=None, residual=None, hang=None, delay=0.0):
        self.name, self.kind, self.log = name, kind, log if log is not None else []
        self.fail, self.residual, self.hang, self.delay = fail, residual, hang, delay

    def release(self):
        if self.delay:
            time.sleep(self.delay)
        self.log.append(self.name)
        if self.hang is not None:
            self.hang.wait()
        if self.fail:
            raise OSError(self.fail)
        if self.residual:
            raise Residual(self.residual)


def released(w):
    """(resource, status) of every story/resource-released, in journal order."""
    return [(e.data["resource"], e.data["status"]) for e in w.events if e.type == T.STORY_RESOURCE_RELEASED.value]


HANG = threading.Event
