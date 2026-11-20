"""B1 gap kills for `aisef2/app/bundle_cli.py::_journal` (mutation campaign, v2.2 release gate).

One test per surviving mutant of `_journal` (the B1 audit's findings). Each calls `_journal` directly on a run
directory built in a temporary directory; the journals that must reconstruct are written through the project's own
writer (`tests.v2.test_v21_r3_usage_no_progress.written`). Offline; no client, no provider, no subprocess; pure
Python, well under the 5 s budget.

Where a mutant's only observable effect is a phrase of the refusal text (the WEAK_ASSERT string-emptying mutants),
the test pins the smallest stable substring that mutant destroys — anchored on the interpolated values around it —
and says so above the assertion. Everything else is asserted semantically (`JournalRefused.code`, exception type)."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle_cli  # noqa: E402
from aisef2.app.verify import _projection_refusal  # noqa: E402
from aisef2.arch.enums import EventType as T  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from tests.v2.test_v21_r3_usage_no_progress import REV, written  # noqa: E402

JOURNAL = "j.jsonl"


def valid_journal() -> str:
    """A journal the reader and the projections both take: S1 begins, commits, closes."""
    def build(j) -> None:
        j.begin()
        j.put(T.STORY_COMMIT, {"story_id": "S1", "revision": REV})
        j.close()
    return written(build)


def committing_twice() -> str:
    """A chain of valid events the writer's authority would refuse (S1 commits twice): the reader takes it,
    `_projection_refusal` does not."""
    def build(j) -> None:
        j.begin()
        j.put(T.STORY_COMMIT, {"story_id": "S1", "revision": REV})
        j.put(T.STORY_COMMIT, {"story_id": "S1", "revision": REV})
    return written(build, checked=False)


class JournalGapKills(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.run_dir = pathlib.Path(os.path.realpath(t.name))

    def with_journal(self, text: str) -> dict:
        (self.run_dir / JOURNAL).write_bytes(text.encode("utf-8"))   # exact bytes: no platform newline translation (LF stays LF on Windows)
        return {"journal": {"path": JOURNAL}}

    def refused(self, rec: dict, recorded: bool = False) -> bundle_cli.JournalRefused:
        with self.assertRaises(bundle_cli.JournalRefused) as c:
            bundle_cli._journal(self.run_dir, rec, recorded)
        return c.exception

    # kills: L920 Or swapped
    def test_an_empty_or_non_string_journal_path_is_missing_evidence(self):
        """`not isinstance(path, str) or not path`: with `and`, path='' falls through to reading the run directory
        itself (EVIDENCE_UNREADABLE) and a non-str truthy path escapes as an uncaught TypeError — both must stay
        EVIDENCE_MISSING."""
        for path in ("", 7):
            with self.subTest(path=repr(path)):
                err = self.refused({"journal": {"path": path}})
                self.assertEqual(err.code, "EVIDENCE_MISSING", str(err))

    # kills: L927 string ' cannot be read (' emptied
    def test_the_unreadable_journal_refusal_says_it_cannot_be_read(self):
        err = self.refused({"journal": {"path": "nope.jsonl"}})
        self.assertEqual(err.code, "EVIDENCE_UNREADABLE", str(err))
        self.assertIn("FileNotFoundError", str(err))
        # the mutant's only observable effect is this phrase between {where} and {type(e).__name__}
        self.assertIn(f"{self.run_dir / 'nope.jsonl'} cannot be read (", str(err))

    # kills: L931 string ' is not the journal ' emptied
    def test_the_digest_mismatch_refusal_links_the_journal_to_the_record(self):
        rec = self.with_journal("not what RUN.json names\n")
        rec["journal"].update({"sha256": "0" * 64, "lines": 1})
        err = self.refused(rec, recorded=True)
        self.assertEqual(err.code, "EVIDENCE_INTEGRITY", str(err))
        # the mutant's only observable effect is this phrase between {where} and {run_dir / 'RUN.json'}
        self.assertIn(f"{self.run_dir / JOURNAL} is not the journal {self.run_dir / 'RUN.json'}", str(err))

    # kills: L941 string ' — its hash chain or sequence is broken: the journal is not the one that was written; restore it from a faithful copy' emptied
    def test_a_broken_chain_refusal_tells_the_operator_what_to_restore(self):
        lines = valid_journal().split("\n")
        lines[1] = lines[1].replace("PLAN-1", "PLAN-9")      # same length: still JSON, the chain no longer links
        err = self.refused(self.with_journal("\n".join(lines)))
        self.assertEqual(err.code, "EVIDENCE_INTEGRITY", str(err))
        # the mutant's only observable effect is this diagnosis appended after the reader's own text
        self.assertIn("its hash chain or sequence is broken", str(err))

    # kills: L948 string " violates the control projections the kernel's writer enforces: " emptied
    def test_the_projection_refusal_frames_the_verifiers_finding(self):
        text = committing_twice()
        pid, kind, seq, _ = _projection_refusal(format3.reconstruct(text).events)
        err = self.refused(self.with_journal(text))
        self.assertEqual(err.code, "EVIDENCE_PROJECTION", str(err))
        self.assertIn(f"{pid} refuses {kind} at seq {seq}", str(err))
        # the mutant's only observable effect is this framing between {where} and {pid}
        self.assertIn(f"{self.run_dir / JOURNAL} violates the control projections the kernel's writer enforces: {pid}",
                      str(err))

    # kills: L950 string ' — no kernel wrote it, and nothing is carried from it; `aisef run --verify` refuses it the same way' emptied
    def test_the_projection_refusal_says_no_kernel_wrote_it(self):
        err = self.refused(self.with_journal(committing_twice()))
        self.assertEqual(err.code, "EVIDENCE_PROJECTION", str(err))
        # the mutant's only observable effect is this what-to-do tail appended after the [:480] slice
        self.assertIn("no kernel wrote it, and nothing is carried from it", str(err))


if __name__ == "__main__":
    unittest.main()
