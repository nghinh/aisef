"""V2.1 (owner B-03, round 3, item 4): `usage.no_progress` on every journal the control projections admit.

The owner's principle: the behavioural domain covers every valid journal a supported product path can bring to
`no_progress` — `aisef run` (RUN.json), `aisef run --verify` (the re-derivation), a continuation (the child's own
journal) — and an invalid journal is refused at a defined boundary (tests/v2/test_v21_r3_usage_boundary.py). "Valid"
is what the six control projections admit: the writer's own authority (`Authority.append`). The kernel's story runner
journals one failure in an attempt that fails and none in one that commits, but the projections admit more — a
committed attempt that observed failures, failures after an outcome, several failures in an attempt — and `--verify`
reads such a journal back. The requirement the function states (aisef2/app/usage.py, docs/v2.1/USAGE-2.1.md:86,
docs/v2.1/TRACEABILITY.md P-5.3c) is retries that changed nothing:

* an attempt is FAILED when it ended in `story/retry` or `story/rollback`; a committed attempt is progress and is never
  reported, whatever failures it observed (CommittedAttemptIsProgress);
* an attempt's failures are the failures its story observed from its `story/begin` to its outcome; what the story
  observes after the outcome and before its next `story/begin` is not the next attempt's (FailuresOutsideAnAttempt);
* a story is compared with itself, whatever the other stories do between its events (StoriesAreCompared).

Every journal here is written through `Authority(JournalWriter3, PROJECTIONS)` — the six projections' pre-check the
kernel's RunScope installs — so each is admitted by construction, and read back with `format3.reconstruct`, the reader
`--verify` uses. Offline; nothing outside the temporary directory is written."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import usage  # noqa: E402
from aisef2.arch.enums import EventType as T  # noqa: E402
from aisef2.journal import format2, format3  # noqa: E402
from aisef2.journal.fold import Authority  # noqa: E402
from aisef2.journal.projections import PROJECTIONS  # noqa: E402
from aisef2.journal.writer import JournalWriter  # noqa: E402
from aisef2.product.contract import plain  # noqa: E402

SHA = "a" * 40
REV = "b" * 40
UNSAT = ("CONTRACT_UNSATISFIED", "proof of C-ADD: CONTRACT_UNSATISFIED")
TESTS = ("TESTS_INADEQUATE", "developer tests: TESTS_INADEQUATE")
MERGE = ("MERGE_CONFLICT", "merge: MERGE_CONFLICT")
_WRITERS = {1: JournalWriter, 2: format2.JournalWriter2, 3: format3.JournalWriter3}


def shown(failure: tuple[str, str]) -> str:
    return f"{failure[0]}: {failure[1]}"


class Script:
    """One journal, appended event by event the way the kernel's story runner appends: a story begins and is admitted,
    observes failures, ends in one outcome (a retry or a rollback citing its attempt's latest failure, or a commit),
    is disposed and ends. `checked=False` appends through the bare writer — the reader's rules and no projection's —
    for the journals the boundary refuses. `fmt` is the journal format (1, 2 or 3)."""

    def __init__(self, path: pathlib.Path, *, checked: bool = True, fmt: int = 3) -> None:
        self.writer = _WRITERS[fmt](path, clock=lambda: 0.0)
        self._put = Authority(self.writer, PROJECTIONS.values()).append if checked else self.writer.append
        self._latest: dict[str, int] = {}      # story -> seq of its latest failure/observed
        self.put(T.RUN_BEGIN, {"journal_format": fmt, "run_id": "run"})
        self.put(T.PLAN_FROZEN, {"plan_id": "PLAN-1", "plan_hash": "c" * 64, "roles": {"C-ADD": "INTRODUCE"}})

    def put(self, event_type: T, data: dict, cites: tuple[int, ...] = ()):
        return self._put(event_type, data, source_seqs=cites)

    def begin(self, sid: str = "S1") -> None:
        self.put(T.STORY_BEGIN, {"story_id": sid, "parent": SHA})
        self.put(T.STORY_ADMITTED, {"story_id": sid, "parent": SHA, "admitted": True, "developer_call_permitted": True,
                                    "dispositions": {"C-ADD": "READY"}})

    def fail(self, failure: tuple[str, str], sid: str = "S1") -> int:
        seq = self.put(T.FAILURE_OBSERVED, {"story_id": sid, "code": failure[0], "detail": failure[1]}).seq
        self._latest[sid] = seq
        return seq

    def retry(self, sid: str = "S1") -> None:
        self.put(T.STORY_RETRY, {"story_id": sid}, (self._latest[sid],))

    def rollback(self, sid: str = "S1") -> None:
        self.put(T.STORY_ROLLBACK, {"story_id": sid}, (self._latest[sid],))

    def commit(self, sid: str = "S1") -> None:
        self.put(T.STORY_COMMIT, {"story_id": sid, "revision": REV})

    def dispose(self, sid: str = "S1") -> None:
        self.put(T.STORY_DISPOSE, {"story_id": sid})

    def end(self, sid: str = "S1") -> None:
        self.put(T.STORY_END, {"story_id": sid})

    def close(self, sid: str = "S1") -> None:
        self.dispose(sid)
        self.end(sid)

    def attempt(self, failures, outcome: str | None, sid: str = "S1") -> None:
        """A whole attempt: begin, each failure, the outcome ('retry', 'rollback', 'commit' or None), dispose, end."""
        self.begin(sid)
        for f in failures:
            self.fail(f, sid)
        if outcome is not None:
            getattr(self, outcome)(sid)
            self.close(sid)


def written(build, *, checked: bool = True, fmt: int = 3) -> str:
    """The text of a journal `build(script)` wrote."""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "journal.jsonl"
        script = Script(path, checked=checked, fmt=fmt)
        try:
            build(script)
        finally:
            script.writer.close()
        return path.read_bytes().decode("utf-8")


def events_of(text: str) -> list[dict]:
    """The events as `aisef run --verify` hands them to the re-derivation."""
    return [{"seq": e.seq, "type": e.type, "data": plain(e.data)} for e in format3.reconstruct(text).events]


def report(build) -> list[dict]:
    return usage.no_progress(events_of(written(build)))


def repeat(story: str, attempts: list[int], failure: tuple[str, str] | list) -> dict:
    failures = [shown(f) for f in ([failure] if isinstance(failure, tuple) else failure)]
    return {"story": story, "attempts_repeating_the_one_before": attempts, "failures": sorted(failures)}


class CommittedAttemptIsProgress(unittest.TestCase):
    """A retry that succeeded is not "a retry that changed nothing": the attempt that committed is never reported, even
    when it observed the very failures of the attempt before it. The journal admits that shape (the projections admit
    `failure/observed` in an attempt that then commits); the kernel's story runner does not write it. The report is
    what RUN.json carries and `--verify` compares, so the answer on that shape is a requirement, not a curiosity."""

    def test_a_committed_attempt_that_observed_the_failures_before_it_is_not_reported(self):
        def build(j: Script) -> None:
            j.attempt([UNSAT], "retry")
            j.attempt([UNSAT], "commit")
        self.assertEqual(report(build), [])

    def test_the_failed_attempts_before_a_commit_are_still_compared_and_the_commit_is_not_one_of_them(self):
        def build(j: Script) -> None:
            j.attempt([UNSAT], "retry")
            j.attempt([UNSAT], "retry")
            j.attempt([UNSAT], "commit")
        self.assertEqual(report(build), [repeat("S1", [2], UNSAT)])

    def test_a_commit_after_a_different_failure_or_at_once_reports_nothing(self):
        def different(j: Script) -> None:
            j.attempt([TESTS], "retry")
            j.attempt([UNSAT], "commit")

        def at_once(j: Script) -> None:
            j.attempt([], "commit")
        for build in (different, at_once):
            with self.subTest(build.__name__):
                self.assertEqual(report(build), [])

    def test_several_failures_in_a_committed_attempt_are_nobodys(self):
        def build(j: Script) -> None:
            j.attempt([UNSAT], "retry")
            j.attempt([TESTS, UNSAT], "commit")
        self.assertEqual(report(build), [])

    def test_a_failure_after_a_commit_is_nobodys_either(self):
        def build(j: Script) -> None:
            j.attempt([UNSAT], "retry")
            j.begin()
            j.commit()
            j.fail(UNSAT)       # the projections admit a failure in any state once the story began
            j.close()
        self.assertEqual(report(build), [])


class FailedAttemptsAreCompared(unittest.TestCase):
    """What the function exists for, on admitted journals: consecutive failed attempts, retry or rollback."""

    def test_a_rollback_ends_a_failed_attempt_as_a_retry_does(self):
        def build(j: Script) -> None:
            j.attempt([UNSAT], "retry")
            j.attempt([UNSAT], "rollback")
        self.assertEqual(report(build), [repeat("S1", [2], UNSAT)])

    def test_each_repeat_is_listed_and_the_first_one_names_the_failures(self):
        def build(j: Script) -> None:
            j.attempt([TESTS], "retry")
            j.attempt([UNSAT], "retry")
            j.attempt([UNSAT], "retry")
            j.attempt([UNSAT], "rollback")
        self.assertEqual(report(build), [repeat("S1", [3, 4], UNSAT)])

    def test_an_attempt_that_never_ended_is_not_a_failed_attempt(self):
        def build(j: Script) -> None:
            j.attempt([UNSAT], "retry")
            j.attempt([UNSAT], None)     # the run stopped inside it: no outcome, so no repeat to report
        self.assertEqual(report(build), [])


class FailuresOutsideAnAttempt(unittest.TestCase):
    """An attempt's failures are what its story observed from its `story/begin` to its outcome. A failure the story
    observes after the outcome — the projections admit it, in any state once the story began — and before its next
    `story/begin` belongs to no attempt of the report: the next attempt had not begun, so it did not observe it. (The
    failure_owner and budgets projections reset at `story/begin` for the same reason.) Where it is journaled between the
    outcome and the next begin does not matter."""

    PLACES = ("after the outcome", "after dispose", "after end")

    def build(self, place: str, then, *, late: tuple[str, str] = TESTS, first=(UNSAT,)):
        def build(j: Script) -> None:
            j.begin()
            for f in first:
                j.fail(f)
            j.retry()
            if place == "after the outcome":
                j.fail(late)
            j.dispose()
            if place == "after dispose":
                j.fail(late)
            j.end()
            if place == "after end":
                j.fail(late)
            then(j)
        return build

    def test_a_late_failure_is_not_carried_into_the_next_attempt(self):
        for place in self.PLACES:
            with self.subTest(place):
                build = self.build(place, lambda j: j.attempt([UNSAT], "rollback"))
                # the second attempt observed UNSAT, as the first did: the report says so, and says nothing of TESTS
                self.assertEqual(report(build), [repeat("S1", [2], UNSAT)])

    def test_a_late_failure_does_not_make_a_different_attempt_look_like_a_repeat(self):
        for place in self.PLACES:
            with self.subTest(place):
                # attempt 1 observed UNSAT and TESTS and failed; UNSAT is journaled again after its outcome; attempt 2
                # observed TESTS alone. Carried into attempt 2 the late UNSAT would make {TESTS, UNSAT} = attempt 1.
                build = self.build(place, lambda j: j.attempt([TESTS], "rollback"), late=UNSAT, first=(UNSAT, TESTS))
                self.assertEqual(report(build), [])

    def test_a_failure_after_the_last_outcome_changes_nothing(self):
        def build(j: Script) -> None:
            j.attempt([UNSAT], "retry")
            j.attempt([UNSAT], "rollback")
            j.fail(TESTS)
        self.assertEqual(report(build), [repeat("S1", [2], UNSAT)])


class StoriesAreCompared(unittest.TestCase):
    """The journal interleaves stories (the projections keep each one's state): a story is compared with itself, and
    another story's begin or outcome neither closes nor discards what this story has observed so far."""

    def test_each_story_is_compared_with_itself(self):
        def build(j: Script) -> None:
            j.attempt([UNSAT], "retry", "S1")
            j.attempt([UNSAT], "retry", "S2")
            j.attempt([UNSAT], "rollback", "S1")     # S1 repeated UNSAT
            j.attempt([TESTS], "rollback", "S2")     # S2 failed differently the second time
        self.assertEqual(report(build), [repeat("S1", [2], UNSAT)])

    def test_the_report_is_in_the_order_of_each_story_s_first_outcome(self):
        def build(j: Script) -> None:
            j.begin("S1")
            j.begin("S2")
            j.fail(UNSAT, "S1")
            j.fail(UNSAT, "S2")
            j.retry("S2")           # S2's first outcome precedes S1's, though S1 began first
            j.retry("S1")
            j.close("S2")
            j.close("S1")
            j.attempt([UNSAT], "rollback", "S1")
            j.attempt([UNSAT], "rollback", "S2")
        self.assertEqual(report(build), [repeat("S2", [2], UNSAT), repeat("S1", [2], UNSAT)])

    def test_another_story_s_begin_does_not_discard_a_failure_this_story_has_observed(self):
        def build(j: Script) -> None:
            j.begin("S2")
            j.fail(UNSAT, "S2")
            j.begin("S1")           # S1 begins while S2's attempt holds a failure and has not ended
            j.retry("S2")           # S2's first attempt ends with the failure it observed before S1 began
            j.close("S2")
            j.attempt([UNSAT], "rollback", "S2")
        self.assertEqual(report(build), [repeat("S2", [2], UNSAT)])


if __name__ == "__main__":
    unittest.main()
