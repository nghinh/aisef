"""V2.1 (owner B-03, survivor audit of campaign 2, round-2 review of batch R03: aisef2/app/lineage.py::account_of [42]):
what a run spent that `account_of` cannot be shown is LISTED as unknown — never raised out of it, never a 0 shown as
known (module docstring, "Spend"; the handler beside the sessions' lookup says the same of a stream the reader refuses).

The evidence it could not look at was answered differently by each CPython the product supports and wrongly by all:

* `sessions` is a link into a directory that cannot be traversed — `Path.is_dir` raised PermissionError out of
  `account_of` on 3.11-3.13 and answered False on 3.14, which took the sessions for absent: a request in flight, listed
  nowhere, spend 0 shown as known;
* a run directory with no search permission — the same lookups (`is_dir`, `is_file`, `exists`), the same two answers,
  and an all-zero account with nothing unaccounted on 3.14;
* a `sessions` directory that cannot be listed (mode 0, or search without read) — `glob` answers an empty listing on
  every version: a 0, with nothing unaccounted, on all four;
* the preflight's ledger behind a directory that cannot be traversed — listed on 3.11-3.13, a 0 on 3.14.

What is genuinely not there (no sessions directory, a file or a dangling link or a loop where it would be, no run
directory) is not unknown: it is what a run that spent nothing there looks like, and it stays exactly that.

The permission tests need POSIX modes and a user that is not root; the rest is portable (symbolic links where the
platform allows them)."""

from __future__ import annotations

import errno
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import lineage  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from aisef2.journal.event import EventType as T  # noqa: E402

STEP = json.dumps({"type": "step_finish", "part": {"tokens": {"input": 1, "output": 1}}}) + "\n"
STREAM = "S1.developer.1.jsonl"
LEDGER = '{"n": 1, "event": "sent"}\n{"n": 1, "event": "done", "input_tokens": 3, "output_tokens": 2}\n'

IS_POSIX_USER = os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0
POSIX_USER = unittest.skipUnless(IS_POSIX_USER, "POSIX permission modes, as a user that is not root")


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = pathlib.Path(t.name).resolve()
        self.tmp = self.root

    def fresh(self, name: str) -> None:
        """A directory of its own for the next state (the states of one test never share a run directory)."""
        self.tmp = self.root / "".join(c if c.isalnum() else "-" for c in name)
        self.tmp.mkdir()

    def run_dir(self) -> pathlib.Path:
        """A run directory whose journal holds a provider request with no result (in flight when the run ended)."""
        run = self.tmp / "run"
        (run / lineage.JOURNAL).parent.mkdir(parents=True)
        w = format3.JournalWriter3(run / lineage.JOURNAL, clock=lambda: 0.0)
        try:
            w.append(T.RUN_BEGIN, {"journal_format": format3.FORMAT, "run_id": "run"})
            w.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ("C-1",), "budget_owner": "DEVELOPER"})
        finally:
            w.close()
        return run

    def sessions(self, run: pathlib.Path) -> pathlib.Path:
        """The run's `sessions` directory holding the stream of the request in flight (one step, 1 + 1 tokens)."""
        (run / "sessions").mkdir()
        (run / "sessions" / STREAM).write_text(STEP, encoding="utf-8")
        return run / "sessions"

    def ledger(self, run: pathlib.Path) -> pathlib.Path:
        (run / "preflight").mkdir()
        (run / "preflight" / "LEDGER.jsonl").write_text(LEDGER, encoding="utf-8")
        return run / "preflight"

    def locked(self, path: pathlib.Path, mode: int) -> None:
        """`path` made to refuse (mode), and given back at the end — before the temporary directory is removed."""
        path.chmod(mode)
        self.addCleanup(path.chmod, 0o755)

    def link(self, link: pathlib.Path, target: pathlib.Path) -> None:
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError) as e:
            self.skipTest(f"no symbolic links here ({type(e).__name__})")

    def assert_listed(self, run: pathlib.Path, *, cause: str = "PermissionError") -> dict:
        """The account is returned (never raised), and what could not be looked at is listed — with its cause."""
        account = lineage.account_of(run)
        self.assertTrue(account["unaccounted"], f"spend the evidence cannot show was shown as a known 0: {account}")
        self.assertTrue(any(cause in u for u in account["unaccounted"]), account["unaccounted"])
        return account


@POSIX_USER
class Refused(Fixture):
    """The system will not let `account_of` look: what that run spent is unknown, listed."""

    def test_a_sessions_that_is_a_link_into_a_directory_that_cannot_be_traversed_is_listed(self):
        """The reproducer of the review: the stream is behind the link, EACCES on the link's target."""
        for what in ("a directory", "a file"):
            with self.subTest(what):
                self.fresh(what)
                run = self.run_dir()
                (self.tmp / "locked" / "inner").mkdir(parents=True)
                if what == "a file":
                    (self.tmp / "locked" / "inner" / "f").write_text("x", encoding="utf-8")
                    target = self.tmp / "locked" / "inner" / "f"
                else:
                    (self.tmp / "locked" / "inner" / STREAM).write_text(STEP, encoding="utf-8")
                    target = self.tmp / "locked" / "inner"
                self.link(run / "sessions", target)
                self.locked(self.tmp / "locked", 0)
                account = self.assert_listed(run)
                self.assertEqual(account["provider_requests"], 1)     # what the journal says stays counted

    def test_a_sessions_directory_that_cannot_be_listed_is_listed(self):
        """`glob` answers an empty listing for a directory it cannot list, on every CPython: a 0 shown as known."""
        for mode in (0o000, 0o300):       # no access at all; search without read (the streams can be named, not found)
            with self.subTest(oct(mode)):
                self.fresh(oct(mode))
                run = self.run_dir()
                self.locked(self.sessions(run), mode)
                account = self.assert_listed(run)
                self.assertEqual(account["provider_requests"], 1)

    def test_an_unsearchable_run_directory_is_listed(self):
        """`is_dir` / `is_file` / `exists` of its files raised on 3.11-3.13 and answered False on 3.14: a traceback, or
        an all-zero account with nothing unaccounted — missing and unreadable evidence not told apart."""
        for mode in (0o600, 0o000):       # read without search; neither
            with self.subTest(oct(mode)):
                self.fresh(oct(mode))
                run = self.run_dir()
                self.sessions(run)
                self.ledger(run)
                (run / "RUN.json").write_text("{}", encoding="utf-8")
                self.locked(run, mode)
                account = self.assert_listed(run)
                self.assertIs(account["recorded"], False)             # a record that cannot be looked at is no record

    def test_a_ledger_behind_a_directory_that_cannot_be_traversed_is_listed(self):
        """The preflight's spend: listed on 3.11-3.13 (`exists` raised into the handler), a known 0 on 3.14."""
        run = self.run_dir()
        self.locked(self.ledger(run), 0)
        account = self.assert_listed(run, cause="ledger")
        self.assertEqual(account["provider_requests"], 1)         # what the journal says stays counted

    def test_the_lineage_carries_the_unknown_to_the_run_that_continues(self):
        """`aisef run --parent` refuses paid work on `lineage_account(...)["unaccounted"]` (aisef2/app/run.py)."""
        run = self.run_dir()
        (self.tmp / "locked" / "inner").mkdir(parents=True)
        (self.tmp / "locked" / "inner" / STREAM).write_text(STEP, encoding="utf-8")
        self.link(run / "sessions", self.tmp / "locked" / "inner")
        self.locked(self.tmp / "locked", 0)
        got = lineage.lineage_account(run)
        self.assertEqual(got["unaccounted"], lineage.account_of(run)["unaccounted"])
        self.assertTrue(got["unaccounted"], got)


class StaysAsItWas(Fixture):
    """The guard answers a refusal only: what is there is counted as before, what is not there is not unknown."""

    def test_what_is_not_there_is_not_unknown(self):
        def sessions_a_file(run):
            (run / "sessions").write_text("not a directory", encoding="utf-8")

        def sessions_dangling(run):
            self.link(run / "sessions", self.tmp / "nowhere")

        def sessions_loop(run):
            self.link(run / "sessions", run / "sessions")

        for name, make in (("no sessions directory", lambda run: None), ("sessions is a file", sessions_a_file),
                           ("sessions is a dangling link", sessions_dangling),
                           ("sessions is a link that loops", sessions_loop)):
            with self.subTest(name):
                self.fresh(name)
                run = self.run_dir()
                make(run)
                account = lineage.account_of(run)
                self.assertEqual(account["unaccounted"], [], account)
                self.assertEqual((account["provider_requests"], account["turns"], account["recorded"]), (1, 0, False))

    def test_a_run_directory_that_is_not_there_is_not_unknown(self):
        for name in ("missing", "a file"):
            with self.subTest(name):
                self.fresh(name)
                run = self.tmp / "run"
                if name == "a file":
                    run.write_text("x", encoding="utf-8")
                account = lineage.account_of(run)
                self.assertEqual(account["unaccounted"], [], account)
                self.assertEqual({k: account[k] for k in lineage.SPEND}, dict.fromkeys(lineage.SPEND, 0))
                self.assertIs(account["recorded"], False)

    def test_a_name_no_file_can_have_is_not_unknown(self):
        """A claim may name a run by any string: a NUL byte names no file (pathlib has always answered "not there")."""
        account = lineage.account_of(pathlib.Path(str(self.tmp / "run") + "\x00x"))
        self.assertEqual(account["unaccounted"], [], account)
        self.assertEqual({k: account[k] for k in lineage.SPEND}, dict.fromkeys(lineage.SPEND, 0))

    def test_what_the_system_says_of_a_name_that_is_not_there_is_not_a_refusal(self):
        """EBADF, and what Windows says for an invalid name, a drive not ready, a reparse point that does not resolve:
        pathlib has always taken them for "not there" and so does the guard — and any other answer to the listing of
        `sessions` (an I/O error here) is a refusal: listed, on every CPython. No filesystem here can be made to say
        these, so the listing of `sessions` is made to."""
        class Windows(OSError):
            def __init__(self, winerror: int) -> None:
                super().__init__(errno.EINVAL, "no")
                self.winerror = winerror

        run = self.run_dir()
        self.sessions(run)
        real = os.listdir

        def answering(error: OSError):
            def listdir(path="."):
                if os.fspath(path) == str(run / "sessions"):
                    raise error
                return real(path)
            return listdir

        for error in (OSError(errno.EBADF, "no"), Windows(21), Windows(123), Windows(1921)):
            with self.subTest(repr(error)):
                with mock.patch.object(os, "listdir", answering(error)):
                    account = lineage.account_of(run)
                # not a refusal: the stream is there to be read, and its request is the one in flight
                self.assertEqual(len(account["unaccounted"]), 1, account)
                self.assertIn("in flight", account["unaccounted"][0])
        with mock.patch.object(os, "listdir", answering(OSError(errno.EIO, "no"))):
            self.assert_listed(run, cause="OSError")

    def test_streams_that_can_be_looked_at_are_counted_and_the_request_in_flight_listed(self):
        """The ordinary run, three ways to reach its sessions: a directory, a link to one, and a run directory that can
        be searched but not listed (every file is named, none is looked for)."""
        def plain(run):
            self.sessions(run)

        def linked(run):
            (self.tmp / "real").mkdir()
            (self.tmp / "real" / STREAM).write_text(STEP, encoding="utf-8")
            self.link(run / "sessions", self.tmp / "real")

        def run_not_listable(run):
            self.sessions(run)
            self.locked(run, 0o300)

        for name, make, posix in (("a directory", plain, False), ("a link to one", linked, False),
                                  ("a run directory that cannot be listed", run_not_listable, True)):
            with self.subTest(name):
                if posix and not IS_POSIX_USER:
                    continue
                self.fresh(name)
                run = self.run_dir()
                (run / "RUN.json").write_text("{}", encoding="utf-8")
                make(run)
                account = lineage.account_of(run)
                self.assertEqual((account["provider_requests"], account["turns"], account["input_tokens"],
                                  account["output_tokens"], account["recorded"]), (1, 1, 1, 1, True))
                self.assertEqual(len(account["unaccounted"]), 1, account["unaccounted"])
                self.assertIn("in flight", account["unaccounted"][0])

    def test_a_ledger_that_is_there_is_counted(self):
        run = self.run_dir()
        self.ledger(run)
        account = lineage.account_of(run)
        self.assertEqual((account["provider_requests"], account["input_tokens"], account["output_tokens"]), (2, 3, 2))
        self.assertEqual(account["unaccounted"], [])


if __name__ == "__main__":
    unittest.main()
