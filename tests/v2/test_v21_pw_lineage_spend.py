"""V2.1 (owner decision 2026-10-15, lineage family; round 2 of the lane's review): what `account_of` says of a journal
that is THERE and cannot be read.

`account_of` re-derives what a run spent from its evidence, and its own rule is that evidence the system will not let it
look at is unknown spend — listed, never raised out of it, never a 0 shown as known (sessions, the preflight's ledger;
tests/v2/test_v21_defects_lineage2.py). The journal was the one source that rule did not reach: a journal that was there
and could not be read (no permission, not text, a hash chain broken, or one that `RUN.json` says held events and is gone)
counted 0 provider requests as known — with no session streams nothing at all was unaccounted, and with one the only
word was "1 sessions were started but 0 provider requests are recorded", the cause lost. A continuation of the lineage
then started paid work on a count of provider requests that was a guess.

What is not there is still a run that spent nothing there (no journal and no record; a record of a run that ended before
it began; a first line cut — no event was ever appended, so no request); a link to nothing or a file in a directory's
place is what `_look` has always called "not there" for spend (nothing was spent THERE). Every reading of the journal
that was there and failed is listed with its cause, and a continuation then starts no paid work until the operator accepts
it by name (`--accept-unaccounted`).

Kept apart from the rest of the lane's tests on purpose: the owner's approval text listed `account_of` among what does not
change; this is the one place the lane changes it, as a restoration of the module's own documented rule, and the change is
one commit that can be taken out. Offline; no client, no provider."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import lineage  # noqa: E402
from tests.v2.test_v21_pw_lineage_unread import JOURNAL, POSIX_USER, Lineage, a_journal  # noqa: E402


class AJournalThatIsThereAndCannotBeReadIsUnknownSpend(Lineage):
    """`account_of` counted 0 provider requests, shown as known, for a journal it could not read (no sessions: nothing
    unaccounted at all; sessions: only "N sessions were started but 0 requests are recorded"). What is not there is a
    run that spent nothing there; what is there and unread is unknown — listed, with the cause, and a continuation of the
    lineage starts no paid work until the operator accepts it."""

    def run_with(self, make) -> pathlib.Path:
        run = self.root / f"spent{len(list(self.root.iterdir()))}"
        run.mkdir()
        self.journal_dir = run
        self.child = run         # `journal_path` / `put_journal` act on the child
        make()
        return run

    @staticmethod
    def broken_chain() -> str:
        lines = a_journal().split("\n")
        lines[1] = lines[1].replace("PLAN-1", "PLAN-9")
        return "\n".join(lines)

    def unknown(self, run: pathlib.Path) -> list[str]:
        account = lineage.account_of(run)
        self.assertEqual(account["provider_requests"], 0)
        return account["unaccounted"]

    def test_a_journal_that_cannot_be_read_is_listed_with_its_cause(self):
        cases = {"not text": lambda: self.put_journal(b"\xff\xfe\x00 not text\n"),
                 "not a journal": lambda: self.put_journal("this is not a journal\n"),
                 "a hash chain broken in the middle": lambda: self.put_journal(self.broken_chain()),
                 "the record names a journal of events and there is none": lambda: (
                     (self.child / "RUN.json").write_text(
                         json.dumps({"journal": {"path": JOURNAL, "sha256": "0" * 64, "lines": 3}}), encoding="utf-8"))}
        for name, make in cases.items():
            with self.subTest(name):
                run = self.run_with(make)
                unknown = self.unknown(run)
                self.assertEqual(len(unknown), 1, unknown)
                self.assertIn("cannot be read", unknown[0])
                self.assertIn("unknown", unknown[0])
                self.assertIn(run.name, unknown[0])

    @POSIX_USER
    def test_a_journal_without_read_permission_is_listed_with_its_cause(self):
        run = self.run_with(lambda: self.locked(self.put_journal(a_journal()), 0o000))
        unknown = self.unknown(run)
        self.assertEqual(len(unknown), 1, unknown)
        self.assertIn("PermissionError", unknown[0])

    def test_what_is_not_there_stays_a_run_that_spent_nothing(self):
        def nothing() -> None:
            pass

        def a_record_that_ended_before_it_began() -> None:
            (self.child / "RUN.json").write_text(json.dumps({"journal": None}), encoding="utf-8")

        def a_journal_that_reads() -> None:
            self.put_journal(a_journal())

        def a_first_line_cut() -> None:
            self.put_journal(a_journal()[:60])      # no event was ever appended: no request

        for name, make in {"no journal, no record": nothing, "a record of a run refused before it began":
                           a_record_that_ended_before_it_began, "a journal that reads": a_journal_that_reads,
                           "a first line cut": a_first_line_cut}.items():
            with self.subTest(name):
                self.assertEqual(self.unknown(self.run_with(make)), [])

    def test_the_lineage_lists_the_spend_of_a_superseded_child_it_cannot_read(self):
        """The operator asserted the claim; the child's journal is still there and still unread: what it spent is
        unknown, and it is in the lineage's account (the continuation then needs `--accept-unaccounted`)."""
        self.put_journal(b"\xff\xfe\x00 not text\n")
        claimed = self.claim_by(self.child)
        sha = hashlib.sha256(claimed).hexdigest()
        lineage.claim(self.pred, self.new, 3.0, supersede=sha)
        got = lineage.lineage_account(self.pred, self.new)
        self.assertEqual([r.get("superseded") for r in got["runs"]], [None, True])
        self.assertTrue(any("cannot be read" in u and self.child.name in u for u in got["unaccounted"]),
                        got["unaccounted"])


if __name__ == "__main__":
    unittest.main()
