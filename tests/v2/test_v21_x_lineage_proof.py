"""V2.1 (owner decision 2026-10-15, lineage family, item 2): what this file pins, consumer by consumer — evidence of a
lineage that cannot be read or reconciled is cost UNKNOWN, never 0 and never a sum that looks complete; history is not
rewritten; and no flag lets a paid session open over a part that cannot be read. Two blind reviews of the first version
found the gaps now pinned here (the rows marked R- and F- below); what is NOT pinned is listed at the end.

The decision as five properties, and the test that pins each on each consumer of lineage cost or claims:

P1  unreadable evidence is unknown in EVERY output (never 0, never a reconciled number)
      lineage.account_of        the journal, whatever stands on its path; a journal that reads and is not the one
                                RUN.json names (F-1, R-9)       -> JournalThatIsThere, JournalThatIsNotTheOneTheRecordNames
      lineage.lineage_account   a record or a claim of the chain that does not read; a link to nothing or a loop in their
                                place (R-1); a name that is no path (F-4); a run a record names and whose directory is
                                gone (R-3, F-2)                 -> RecordsAndClaimsThatDoNotRead, LinksInPlaceOfRecordsAndClaims,
                                                                   RunsTheLineageNamesAndThatAreNotThere, NamesThatAreNoPath
      lineage.usage_lineage     RUN.json `lineage_usage`: money and tokens (R-7)  -> KnownAndTotal, NoFlagOpensAPaidSession
      run.execute               RUN.json `continues.account`, `budget`, the refusal -> NoFlagOpensAPaidSession
      bundle_cli.continue_from  the report, and what it prints  -> BundleContinue
      verify.verify             `aisef run --verify`            -> VerifyCannotRederive, JournalCutUnderItsRecord
P2  the known cost of the readable parts (exact, per run; `exact` says whether a row is a count or a lower bound — R-8) is
    kept apart from the total (None while any part is unknown)  -> KnownAndTotal, BundleContinue
P3  history is never rewritten and a claim is never released or retaken because a read failed
      lineage.process_started / _gone   a `ps` that failed is not "no such process" -> ProcessTableThatFailed
      lineage.claim                     an unread child, `--supersede-claim`        -> NoFlagOpensAPaidSession
P4  nothing that could open a paid session does while a part of the lineage cannot be read
      run.execute: --parent, --accept-unaccounted, --supersede-claim, the Budget -> NoFlagOpensAPaidSession, BudgetArithmetic (F-6)
P5  the refusal says what the operator does, and where (R-6, F-5)  -> NoFlagOpensAPaidSession, BundleContinue

NOT pinned here — each is an open decision for the owner, stated in the lane's result, not decided by this file:
* `--accept-unaccounted` over spend the evidence READS as sent and never answered (a request in flight): it is accepted by
  name and recorded, and the ceilings are then enforced against cap - known (the account says the total is not known);
  `test_a_request_in_flight_is_still_refused_without_the_flag_and_accepted_by_name_with_it` pins what IS, as a control.
* A run refused after its claim leaves one claim generation on the predecessor, and `--supersede-claim` over a child that
  does not read records the operator's assertion in it (owner-approved 2026-10-15, round 2): the claim is released by an
  assertion, and a child that reads as BEGUN afterwards sits beside the continuation that was started.
* A child that a claim names and whose directory is not there is UNBEGUN and spent nothing there (the claim lifecycle,
  tests/v2/test_v21_continue_integrity.py::ClaimLifecycle): a child that vanished may have begun and spent, and the
  lineage counts it as 0 (`RunsTheLineageNamesAndThatAreNotThere` pins what IS, as a control).
* (Closed by the owner's decision of 2026-10-15, round 2: tests/v2/test_v21_x_lineage_gone.py.) A `sessions` directory or
  a preflight ledger missing beside a journal that records answered requests was read as no tokens and no turns: the run's
  record, or the answered requests with no stream, now make that run unread. What stays as it was
  (tests/v2/test_v21_defects_lineage2.py): the same shapes beside a request in flight, which the pins there keep known.

Offline and deterministic; the full-run classes use the fake client of tests/v2/test_app_run.py. Nothing here deletes or
kills (INV-MUTATION-AUTHORITY): the temporary directories are the framework's."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, bundle_cli, cli, client, lineage  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import verify  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from aisef2.journal.event import EventType as T  # noqa: E402
from tests.v2.test_app_run import SETTINGS, ProductBase, calibrations, project_bundle, provider  # noqa: E402

IS_POSIX_USER = os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0
POSIX_USER = unittest.skipUnless(IS_POSIX_USER, "POSIX permission modes, as a user that is not root")
POSIX_CLIENT = unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
STEP = json.dumps({"type": "step_finish", "part": {"tokens": {"input": 7, "output": 3}}}) + "\n"
NOT_TEXT = b"\xff\xfe\x00 not text\n"
PRICES = {"currency": "USD", "input_per_mtok": 1.0, "cache_read_per_mtok": 0.1, "cache_write_per_mtok": 1.0,
          "output_per_mtok": 2.0, "source": "fixture", "effective_date": "2026-01-01"}


class Hand(unittest.TestCase):
    """Run directories made by hand, in the shape a run leaves (a journal of events, RUN.started.json, RUN.json)."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.top = self.root = pathlib.Path(os.path.realpath(t.name))

    def fresh(self, name: str) -> pathlib.Path:
        """A directory of its own for the next state (the states of one test never share a run directory)."""
        self.root = self.top / "".join(c if c.isalnum() else "-" for c in name)
        self.root.mkdir()
        return self.root

    def run_dir(self, name: str, requests: int = 1, continues: pathlib.Path | None = None, *, journal: bool = True,
                in_flight: bool = False, stream: bool = False, streams: bool = True, records: bool = True,
                seal: bool = False) -> pathlib.Path:
        """`requests` provider requests journaled and answered, each with the session stream a run leaves for it (one
        finished step, 7 + 3 tokens: a journal that records an answered request with no stream to stand for it is evidence
        that is gone, which `EvidenceThatIsGone` makes and this fixture must not); `in_flight`: the last one has no result
        — more streams than answers: unknown spend that READS; `stream`: a stream for the first request, which is all
        there was before `streams` (default: a stream for every request); `streams=False` is for a test whose journal is
        the evidence under test and is cut, emptied or unreadable — it is unknown on its own and the streams add findings
        of their own that the test does not count; `records=False`: neither RUN.started.json nor RUN.json (the test puts
        what it needs there: a link, say); `seal`: RUN.json names the journal as the run left it (its digest and length,
        as `run._journal_info` writes them)."""
        run = self.root / name
        run.mkdir()
        if journal:
            (run / lineage.JOURNAL).parent.mkdir(parents=True)
            w = format3.JournalWriter3(run / lineage.JOURNAL, clock=lambda: 0.0)
            try:
                w.append(T.RUN_BEGIN, {"journal_format": format3.FORMAT, "run_id": "run"})
                for n in range(requests):
                    e = w.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ("C-1",), "budget_owner": "DEVELOPER"})
                    if not (in_flight and n == requests - 1):
                        w.append(T.PROVIDER_RESULT, {"story_id": "S1", "outcome": "COMPLETED", "synthetic": False,
                                                     "detail": "answered"}, source_seqs=(e.seq,))
            finally:
                w.close()
        every = in_flight or (journal and streams)
        if stream or every and requests:
            (run / "sessions").mkdir()
            for n in range(1, (requests if every else 1) + 1):
                (run / "sessions" / f"S1.developer.{n}.jsonl").write_text(STEP, encoding="utf-8")
        rec = {"continues": {"path": str(continues)}} if continues else {}
        if records:
            (run / lineage.STARTED).write_text(json.dumps(rec), encoding="utf-8")
            (run / "RUN.json").write_text(json.dumps(rec), encoding="utf-8")
        if seal:
            self.seal(run)
        return run

    def seal(self, run: pathlib.Path) -> None:
        """RUN.json names the journal that is on disk now: what the record of a run that closed holds."""
        data = (run / lineage.JOURNAL).read_bytes()
        rec = json.loads((run / "RUN.json").read_text(encoding="utf-8"))
        rec["journal"] = {"path": lineage.JOURNAL.as_posix(), "sha256": hashlib.sha256(data).hexdigest(),
                          "lines": data.count(b"\n"), "closed": "SHUTDOWN"}
        (run / "RUN.json").write_text(json.dumps(rec), encoding="utf-8")

    def claim(self, pred: pathlib.Path, n: int, child: pathlib.Path | str | None, raw: bytes | None = None) -> bytes:
        name = lineage.CLAIM if n == 1 else f"CONTINUED-BY.{n}.json"
        data = raw if raw is not None else (json.dumps({"run": str(child), "claimed": 1.0,
                                                        "claimant": {"host": "elsewhere", "pid": 1, "started": "x"}},
                                                       sort_keys=True) + "\n").encode("utf-8")
        (pred / name).write_bytes(data)
        return data

    def locked(self, path: pathlib.Path, mode: int) -> None:
        path.chmod(mode)
        self.addCleanup(path.chmod, 0o755)

    def link(self, at: pathlib.Path, to: pathlib.Path) -> None:
        try:
            os.symlink(to, at)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links are not available here")


def requests_of(account: dict) -> dict[str, int]:
    return {pathlib.Path(r["run"]).name: r["provider_requests"] for r in account["runs"]}


def snapshot(top: pathlib.Path) -> dict:
    """Every file under `top`, by relative path: what history holds, byte for byte (a file that cannot be read: its size
    and times, which a write would move)."""
    out: dict = {}
    for p in sorted(top.rglob("*")):
        if p.is_file():
            try:
                out[p.relative_to(top).as_posix()] = p.read_bytes()
            except OSError:
                st = p.stat()
                out[p.relative_to(top).as_posix()] = (st.st_size, st.st_mtime_ns)
    return out


# ------------------------------------------------------------------------------------------------ P1, P2: the account

class KnownAndTotal(Hand):
    """P2: what the readable parts spent is exact and attributed (`runs`, the four counters); the lineage's total is None
    while any part is unknown — the sums beside it are what is known — and `usage_lineage` says the same of tokens and of
    money."""

    def test_a_lineage_that_is_all_known_has_a_total_that_is_the_sum(self):
        r1 = self.run_dir("run1", 3)
        r2 = self.run_dir("run2", 2, continues=r1)
        got = lineage.lineage_account(r2, self.root / "out")
        self.assertEqual(requests_of(got), {"run2": 2, "run1": 3})
        self.assertEqual((got["unaccounted"], got["unread"]), ([], []))
        self.assertEqual(got["total"], {k: got[k] for k in lineage.SPEND})
        self.assertEqual(got["total"]["provider_requests"], 5)

    def test_a_part_that_cannot_be_read_is_unknown_the_known_part_stays_exact_and_the_total_is_none(self):
        r1 = self.run_dir("run1", 3, stream=True, streams=False)
        (r1 / lineage.JOURNAL).write_bytes(NOT_TEXT)
        r2 = self.run_dir("run2", 2, continues=r1)
        got = lineage.lineage_account(r2, self.root / "out")
        self.assertTrue(any("run1" in u and "cannot be read" in u for u in got["unaccounted"]), got["unaccounted"])
        self.assertIsNone(got["total"])
        self.assertEqual(requests_of(got), {"run2": 2, "run1": 0})    # run1's requests are not 0: they are not known
        self.assertEqual(got["runs"][1]["input_tokens"], 7)           # what its stream shows is known, and attributed
        self.assertTrue(got["unread"] and all("run1" in u for u in got["unread"]), got["unread"])
        self.assertEqual(got["unread"], [u for u in got["unaccounted"] if u in got["unread"]])

    def test_a_part_whose_figures_are_a_lower_bound_says_so_beside_them(self):
        """R-8: a part whose journal does not read has `provider_requests: 0` in its row — not a count, a lower bound; the
        row says so (`exact`), as the lineage's `total` does for the whole."""
        r1 = self.run_dir("run1", 3, stream=True)
        (r1 / lineage.JOURNAL).write_bytes(NOT_TEXT)
        r2 = self.run_dir("run2", 2, continues=r1)
        by_run = {pathlib.Path(r["run"]).name: r for r in lineage.lineage_account(r2, self.root / "out")["runs"]}
        self.assertEqual((by_run["run2"]["exact"], by_run["run1"]["exact"]), (True, False))
        self.assertIs(lineage.account_of(self.run_dir("run3", 1, in_flight=True))["exact"], False)

    def test_a_part_in_flight_is_unknown_but_it_reads(self):
        r1 = self.run_dir("run1", 2, in_flight=True)
        got = lineage.lineage_account(r1)
        self.assertEqual(len(got["unaccounted"]), 1, got["unaccounted"])
        self.assertIn("in flight", got["unaccounted"][0])
        self.assertIsNone(got["total"])
        self.assertEqual(got["unread"], [])

    def test_the_usage_of_the_lineage_is_unknown_and_its_tokens_a_lower_bound_while_a_part_is_unknown(self):
        r1 = self.run_dir("run1", 3, stream=True)
        r2 = self.run_dir("run2", 2, continues=r1, stream=True)
        own = {"tokens": {"input": 1, "output": 1}, "cost": {"value": 0.5, "status": "known"}, "sessions": []}
        whole = lineage.usage_lineage(r2, self.root / "out", own, PRICES)
        self.assertEqual(whole["cost"]["status"], "known")
        self.assertIsInstance(whole["cost"]["value"], float)
        self.assertEqual(whole["tokens_status"], "known")
        (r1 / lineage.JOURNAL).write_bytes(NOT_TEXT)
        part = lineage.usage_lineage(r2, self.root / "out", own, PRICES)
        self.assertIsNone(part["cost"]["value"])
        self.assertTrue(part["cost"]["status"].startswith("unknown"), part["cost"])
        self.assertTrue(part["tokens_status"].startswith("lower bound"), part["tokens_status"])
        by_run = {pathlib.Path(e["run"]).name: e for e in part["runs"]}
        self.assertIsInstance(by_run["run2"]["cost"]["value"], float)      # the readable part: exact, attributed
        self.assertIsNone(by_run["run1"]["cost"]["value"])                  # the unread part: unknown, not 0
        self.assertIn("cannot be read", by_run["run1"]["cost"]["status"])
        self.assertIn("known", by_run["run1"]["cost"])                      # what its streams show, kept apart

    def test_this_runs_own_steps_without_tokens_make_the_lineages_tokens_a_lower_bound_too(self):
        r1 = self.run_dir("run1", 1, stream=True)
        blind = {"tokens": {"input": 1, "output": 1}, "cost": {"value": None, "status": "partial"},
                 "sessions": [{"session": "S1.developer.1.jsonl", "steps": 1, "steps_without_tokens": 1}]}
        got = lineage.usage_lineage(r1, self.root / "out", blind, PRICES)
        self.assertTrue(got["tokens_status"].startswith("lower bound"), got["tokens_status"])


# ------------------------------------------------------------------------------------------------ P1/P4: the walk

class RecordsAndClaimsThatDoNotRead(Hand):
    """P1/P4: a part the lineage cannot NAME — the run a record continues when the record cannot be read, the run a claim
    names when the claim cannot be read — was passed over in silence (`unaccounted` empty, the sum shown as the lineage's).
    It is unknown, listed, and `unread`. Controls: what reads and says "no predecessor" ends the walk; a claim of nothing is
    nothing."""

    def assert_unread(self, got: dict, *needles: str) -> None:
        self.assertTrue(got["unaccounted"], "unknown spend is listed, not passed over")
        self.assertTrue(got["unread"], got)
        self.assertIsNone(got["total"])
        for n in needles:
            self.assertTrue(any(n in u for u in got["unread"]), (n, got["unread"]))

    def test_a_record_of_the_chain_that_cannot_be_read_is_unknown_not_the_end_of_the_chain(self):
        damage = {"cut": b'{"continues": {"pa', "not text": b"\xff\xfe\x00\x01", "not an object": b"[1]",
                  "a predecessor that is no path": json.dumps({"continues": {"path": 7}}).encode()}
        for name, raw in damage.items():
            with self.subTest(name):
                self.fresh(name)
                r1 = self.run_dir("run1", 3)
                r2 = self.run_dir("run2", 2, continues=r1)
                for f in (lineage.STARTED, "RUN.json"):
                    (r2 / f).write_bytes(raw)
                got = lineage.lineage_account(r2, self.root / "out")
                self.assertEqual(requests_of(got), {"run2": 2})          # run1's 3 are NOT in the known part: said so
                self.assert_unread(got, "run2")

    @POSIX_USER
    def test_records_that_the_system_will_not_let_this_process_read_are_unknown(self):
        r1 = self.run_dir("run1", 3)
        r2 = self.run_dir("run2", 2, continues=r1)
        for f in (lineage.STARTED, "RUN.json"):
            self.locked(r2 / f, 0o000)
        self.assert_unread(lineage.lineage_account(r2, self.root / "out"), "PermissionError")

    def test_the_records_of_the_first_run_of_the_chain_that_cannot_be_read_are_unknown_too(self):
        """The oldest run names no predecessor — but only a record that reads can say so."""
        r1 = self.run_dir("run1", 3)
        for f in (lineage.STARTED, "RUN.json"):
            (r1 / f).write_bytes(NOT_TEXT)
        self.assert_unread(lineage.lineage_account(r1), "run1")

    def test_a_record_that_reads_and_names_none_ends_the_walk_whatever_the_other_one_is(self):
        """RUN.started.json is written first and names the predecessor the run was given: read, it answers."""
        for damaged in (lineage.STARTED, "RUN.json"):
            with self.subTest(damaged):
                self.fresh(damaged)
                r1 = self.run_dir("run1", 3)       # a run that continues nothing
                (r1 / damaged).write_bytes(NOT_TEXT)
                got = lineage.lineage_account(r1, self.root / "out")
                self.assertEqual((got["unaccounted"], got["unread"]), ([], []))
                self.assertEqual(got["total"]["provider_requests"], 3)

    def test_a_run_with_no_record_at_all_continues_nothing_as_before(self):
        r1 = self.run_dir("run1", 3)
        bare = self.root / "bare"     # the same journal and streams, and neither RUN.started.json nor RUN.json
        (bare / lineage.JOURNAL).parent.mkdir(parents=True)
        (bare / lineage.JOURNAL).write_bytes((r1 / lineage.JOURNAL).read_bytes())
        shutil.copytree(r1 / "sessions", bare / "sessions")
        got = lineage.lineage_account(bare)
        self.assertEqual((got["unaccounted"], got["unread"]), ([], []))
        self.assertEqual(got["total"]["provider_requests"], 3)

    def test_an_older_claim_generation_that_cannot_be_read_names_a_run_that_is_not_known(self):
        raw = {"torn": b'{"run": "/x", "cla', "not text": b"\xff\xfe\x00", "an object whose run is no string": b'{"run": 7}',
               "not an object": b"[1]"}
        for name, bytes_ in raw.items():
            with self.subTest(name):
                self.fresh(name)
                r1 = self.run_dir("run1", 3)
                r2 = self.run_dir("run2", 2, continues=r1)
                self.claim(r1, 1, None, raw=bytes_)
                self.claim(r1, 2, r2)
                got = lineage.lineage_account(r2, self.root / "out")
                self.assert_unread(got, "CONTINUED-BY.json")
                self.assertEqual(requests_of(got), {"run2": 2, "run1": 3})

    @POSIX_USER
    def test_a_claim_that_the_system_will_not_let_this_process_read_is_unknown(self):
        r1 = self.run_dir("run1", 3)
        r2 = self.run_dir("run2", 2, continues=r1)
        self.claim(r1, 1, self.root / "other")
        self.locked(r1 / lineage.CLAIM, 0o000)
        self.assert_unread(lineage.lineage_account(r2, self.root / "out"), "PermissionError")

    def test_a_claim_of_nothing_and_a_claim_that_reads_are_not_unknown(self):
        r1 = self.run_dir("run1", 3)
        r2 = self.run_dir("run2", 2, continues=r1)
        sup = self.run_dir("superseded", 5)
        self.claim(r1, 1, None, raw=b"{}\n")           # an object that names no run: a claim of nothing
        self.claim(r1, 2, sup)
        self.claim(r1, 3, r2)
        got = lineage.lineage_account(r2, self.root / "out")
        self.assertEqual((got["unaccounted"], got["unread"]), ([], []))
        self.assertEqual(requests_of(got), {"run2": 2, "superseded": 5, "run1": 3})
        self.assertEqual(got["total"]["provider_requests"], 10)

    def test_a_run_a_record_names_and_whose_directory_is_gone_is_not_a_run_that_spent_nothing(self):
        """The first version of this lane kept "absence is not a read failure" here, and two blind reviews showed the
        total then looked complete over a run that existed (a record names it) and whose journal cannot be read because
        its directory is gone. Inverted on purpose; every shape is in RunsTheLineageNamesAndThatAreNotThere."""
        r2 = self.run_dir("run2", 2, continues=self.root / "gone")
        got = lineage.lineage_account(r2, self.root / "out")
        self.assert_unread(got, "gone")
        self.assertEqual(requests_of(got), {"run2": 2, "gone": 0})      # run2's 2 are known; gone's are not 0: not known

    def test_a_predecessor_whose_claims_cannot_be_listed_is_unknown(self):
        r1 = self.run_dir("run1", 3)
        r2 = self.run_dir("run2", 2, continues=r1)
        self.claim(r1, 1, r2)
        with mock.patch.object(lineage, "claims", side_effect=lineage.LineageRefused("cannot be listed")):
            got = lineage.lineage_account(r2, self.root / "out")
        self.assert_unread(got, "cannot be listed")


class JournalThatIsThere(Hand):
    """P1: a journal that is there and does not read is unknown spend whatever stands on its path. A link to nothing, a link
    that loops, a file in a directory's place were taken for "no journal": 0 requests, nothing unaccounted — and
    `--supersede-claim` over such a child opened a paid session (NoFlagOpensAPaidSession). Controls: a run directory that is
    not there, or is not a directory, spent nothing there."""

    def variants(self, run: pathlib.Path) -> dict:
        def dangling_link() -> None:
            (run / lineage.JOURNAL).parent.mkdir(parents=True)
            self.link(run / lineage.JOURNAL, self.root / "nowhere.jsonl")

        def looping_link() -> None:
            (run / lineage.JOURNAL).parent.mkdir(parents=True)
            self.link(run / lineage.JOURNAL, run / lineage.JOURNAL)

        def journals_is_a_link_to_nothing() -> None:
            (run / "run").mkdir()
            self.link(run / "run" / "journals", self.root / "no-such-directory")

        def journals_is_a_file() -> None:
            (run / "run").mkdir()
            (run / "run" / "journals").write_text("not a directory", encoding="utf-8")

        def run_is_a_file() -> None:
            (run / "run").write_text("not a directory", encoding="utf-8")

        return {"the journal is a link to nothing": dangling_link, "the journal is a link that loops": looping_link,
                "journals is a link to nothing": journals_is_a_link_to_nothing, "journals is a file": journals_is_a_file,
                "run is a file": run_is_a_file}

    def test_each_is_unknown_spend_listed_with_its_cause(self):
        for name in self.variants(self.root):
            with self.subTest(name):
                self.fresh(name)
                run = self.root / "run"
                run.mkdir()
                self.variants(run)[name]()
                got = lineage.account_of(run)
                self.assertTrue(got["unaccounted"], f"{name}: unknown spend is listed, not a known 0")
                self.assertEqual(got["unread"], got["unaccounted"])
                self.assertIn("cannot be read", got["unread"][0])
                self.assertIn("unknown", got["unread"][0])

    def test_what_is_not_there_stays_a_run_that_spent_nothing(self):
        def missing(run):
            pass

        def a_file(run):
            run.write_text("x", encoding="utf-8")

        def a_link_to_nothing(run):
            self.link(run, self.root / "nowhere")

        def empty(run):
            run.mkdir()

        def run_and_journals_only(run):
            (run / lineage.JOURNAL).parent.mkdir(parents=True)

        for name, make in {"missing": missing, "a file": a_file, "a link to nothing": a_link_to_nothing, "empty": empty,
                           "run/journals with no journal": run_and_journals_only}.items():
            with self.subTest(name):
                self.fresh(name)
                run = self.root / "run"
                make(run)
                got = lineage.account_of(run)
                self.assertEqual((got["unaccounted"], got["unread"]), ([], []))
                self.assertEqual({k: got[k] for k in lineage.SPEND}, dict.fromkeys(lineage.SPEND, 0))


# ------------------------------------------------------------------------------------------------ review round: the gaps

class UnreadAsserts(Hand):
    """What a part the lineage cannot know looks like: listed, unread, and no total."""

    def assert_unread(self, got: dict, *needles: str) -> None:
        self.assertTrue(got["unaccounted"], "unknown spend is listed, not passed over")
        self.assertTrue(got["unread"], got)
        self.assertIsNone(got["total"])
        for n in needles:
            self.assertTrue(any(n in u for u in got["unread"]), (n, got["unread"]))

    def nowhere(self, at: pathlib.Path, kind: str) -> None:
        """`at` is what the system answers "nothing there" for, and is there: a link to nothing, or one that loops."""
        self.link(at, at if kind == "a link that loops" else self.top / "nowhere")


LINKS = ("a link to nothing", "a link that loops")


class LinksInPlaceOfRecordsAndClaims(UnreadAsserts):
    """R-1: a record (RUN.started.json, RUN.json) or a claim that is a link to nothing, or one that loops, is evidence
    that is there and cannot be read — the same damage as a record that is cut. It was read as "not there": the walk ended
    silently, the claim was invisible, the total looked complete and `aisef run --parent` opened a paid session."""

    def chain(self, name: str, records: bool = False) -> tuple[pathlib.Path, pathlib.Path]:
        self.fresh(name)
        r1 = self.run_dir("run1", 3)
        return r1, self.run_dir("run2", 2, continues=r1, records=records)

    def test_records_that_are_links_are_unknown_not_the_end_of_the_chain(self):
        for kind in LINKS:
            for both in (True, False):
                with self.subTest(kind, both=both):
                    r1, r2 = self.chain(f"{kind} {both}")
                    self.nowhere(r2 / "RUN.json", kind)
                    if both:
                        self.nowhere(r2 / lineage.STARTED, kind)
                    got = lineage.lineage_account(r2, self.root / "out")
                    self.assertEqual(requests_of(got), {"run2": 2})       # run1's 3 are not in the known part: said so
                    self.assert_unread(got, "run2")

    def test_a_record_that_reads_and_names_none_still_ends_the_walk_whatever_the_other_is(self):
        for kind in LINKS:
            for broken in (lineage.STARTED, "RUN.json"):
                with self.subTest(kind, broken=broken):
                    self.fresh(f"{kind} {broken}")
                    r1 = self.run_dir("run1", 3, records=False)
                    (r1 / (lineage.STARTED if broken == "RUN.json" else "RUN.json")).write_text("{}", encoding="utf-8")
                    self.nowhere(r1 / broken, kind)
                    got = lineage.lineage_account(r1, self.root / "out")
                    self.assertEqual((got["unaccounted"], got["unread"]), ([], []))
                    self.assertEqual(got["total"]["provider_requests"], 3)

    def test_a_first_generation_claim_that_is_a_link_is_listed_and_the_run_it_names_is_unknown(self):
        for kind in LINKS:
            with self.subTest(kind):
                r1, r2 = self.chain(kind, records=True)
                self.nowhere(r1 / lineage.CLAIM, kind)
                self.claim(r1, 2, r2)
                self.assertEqual([n for n, _ in lineage.claims(r1)], [1, 2])
                self.assert_unread(lineage.lineage_account(r2, self.root / "out"), "run1/CONTINUED-BY.json")

    def test_a_later_generation_that_is_a_link_is_unknown_too(self):
        for kind in LINKS:
            with self.subTest(kind):
                r1, r2 = self.chain(kind, records=True)
                self.claim(r1, 1, self.run_dir("sup", 5))
                self.nowhere(r1 / "CONTINUED-BY.2.json", kind)
                self.claim(r1, 3, r2)
                self.assertEqual([n for n, _ in lineage.claims(r1)], [1, 2, 3])
                got = lineage.lineage_account(r2, self.root / "out")
                self.assert_unread(got, "run1/CONTINUED-BY.2.json")
                self.assertEqual(requests_of(got), {"run2": 2, "run1": 3, "sup": 5})

    def test_claiming_over_a_claim_that_is_a_link_says_it_cannot_be_read_not_that_another_run_took_it(self):
        for kind in LINKS:
            with self.subTest(kind):
                self.fresh(kind)
                r1 = self.run_dir("run1", 3)
                self.nowhere(r1 / lineage.CLAIM, kind)
                with self.assertRaises(lineage.LineageRefused) as c:
                    lineage.claim(r1, self.root / "next", 1.0)
                self.assertIn("cannot be read", str(c.exception))
                self.assertNotIn("same moment", str(c.exception))
                self.assertEqual(sorted(p.name for p in r1.glob("CONTINUED-BY*")), [lineage.CLAIM], "nothing was taken")
                self.assertEqual(lineage.continued_by(r1), (lineage.UNREADABLE_CLAIM, None))
                self.assertIn("cannot be read", lineage.claim_unread(r1) or "")


class RunsTheLineageNamesAndThatAreNotThere(UnreadAsserts):
    """R-3 / F-2: a run that a record of the chain NAMES as the one it continues existed (`aisef run --parent` refuses a
    parent with no run record). What it spent cannot be told when its directory is not there, is a file, or is a link that
    leads nowhere: unknown — not a run that spent nothing. (`account_of` of a directory nothing names stays a run that
    spent nothing there: tests/v2/test_v21_defects_lineage2.py; so does a claim's superseded child, below.)"""

    SHAPES = {"missing": lambda t, p: None, "a file": lambda t, p: p.write_text("x", encoding="utf-8"),
              "a link to nothing": lambda t, p: t.link(p, t.top / "nowhere"), "a link that loops": lambda t, p: t.link(p, p)}

    def test_an_ancestor_a_record_names_is_unknown(self):
        for name, make in self.SHAPES.items():
            with self.subTest(name):
                self.fresh(name)
                gone = self.root / "run1"
                r2 = self.run_dir("run2", 2, continues=gone)
                make(self, gone)
                got = lineage.lineage_account(r2, self.root / "out")
                self.assertEqual(requests_of(got), {"run2": 2, "run1": 0})   # run2's 2 are known; run1's are not 0
                self.assert_unread(got, "run1")
                self.assertTrue(any("is not there" in u for u in got["unread"]), got["unread"])
                self.assertIs(got["runs"][1]["exact"], False)

    def test_a_predecessor_that_is_given_and_is_not_there_is_unknown(self):
        self.assert_unread(lineage.lineage_account(self.root / "gone"), "gone")

    def test_a_child_a_claim_names_and_whose_directory_is_not_there_stays_a_run_that_spent_nothing(self):
        """A control that is NOT a decision of the owner's: tests/v2/test_v21_continue_integrity.py pins that a claim whose
        child is not there is UNBEGUN and is superseded (the claim lifecycle, owner-approved), and the lineage counts that
        child as it always did. Whether a child that vanished may have spent is an open question in the lane's result."""
        for name, make in self.SHAPES.items():
            with self.subTest(name):
                self.fresh(name)
                r1 = self.run_dir("run1", 3)
                r2 = self.run_dir("run2", 2, continues=r1)
                child = self.root / "child"
                make(self, child)
                self.claim(r1, 1, child)
                self.claim(r1, 2, r2)
                got = lineage.lineage_account(r2, self.root / "out")
                self.assertEqual((got["unaccounted"], got["unread"]), ([], []))
                self.assertEqual(requests_of(got), {"run2": 2, "run1": 3, "child": 0})

    def test_the_account_of_a_directory_nothing_names_stays_a_run_that_spent_nothing(self):
        got = lineage.account_of(self.root / "gone")
        self.assertEqual((got["unaccounted"], got["unread"]), ([], []))
        self.assertIs(got["exact"], True)


class JournalThatIsNotTheOneTheRecordNames(UnreadAsserts):
    """F-1 / R-9: a journal that READS and is not the journal the run's own RUN.json names (its digest and length: what
    `--verify` and `bundle continue` compare) — emptied, cut at a line boundary, cut in a line — is not the run's spend. A
    zero-length or truncated journal is what a crash or a full disk leaves: its requests are unknown, not the few that
    are left, and not 0. No RUN.json, or one that names no journal digest: nothing to compare with."""

    CUTS = {"no bytes": lambda d: b"", "cut at a line": lambda d: b"\n".join(d.split(b"\n")[:3]) + b"\n",
            "cut in a line": lambda d: d[:-9]}

    def test_each_is_unknown_spend_listed_with_its_cause(self):
        for name, cut in self.CUTS.items():
            with self.subTest(name):
                self.fresh(name)
                r1 = self.run_dir("run1", 3, seal=True, streams=False)
                (r1 / lineage.JOURNAL).write_bytes(cut((r1 / lineage.JOURNAL).read_bytes()))
                got = lineage.account_of(r1)
                self.assertEqual(got["unread"], got["unaccounted"])
                self.assertEqual(len(got["unread"]), 1, got["unread"])
                self.assertIn("RUN.json", got["unread"][0])
                self.assertIn("unknown", got["unread"][0])
                self.assertIs(got["exact"], False)
                self.assert_unread(lineage.lineage_account(r1), "run1")

    def test_an_ancestor_is_unknown_and_the_known_part_stays_attributed(self):
        r1 = self.run_dir("run1", 3, seal=True)
        r2 = self.run_dir("run2", 2, continues=r1)
        (r1 / lineage.JOURNAL).write_bytes(self.CUTS["cut at a line"]((r1 / lineage.JOURNAL).read_bytes()))
        got = lineage.lineage_account(r2, self.root / "out")
        self.assertEqual(requests_of(got), {"run2": 2, "run1": 1})      # what is left of run1 is a lower bound, said so
        self.assert_unread(got, "run1")

    def test_controls_a_journal_that_is_the_one_named_and_a_run_that_names_none(self):
        self.fresh("intact")
        r1 = self.run_dir("run1", 3, seal=True)
        got = lineage.account_of(r1)
        self.assertEqual((got["unaccounted"], got["unread"], got["provider_requests"]), ([], [], 3))
        self.assertIs(got["exact"], True)
        for name, cut in self.CUTS.items():     # a run with no record (killed before it) or a record with no digest
            for sealed in (False, True):
                with self.subTest(name, record_names_a_journal=sealed):
                    self.fresh(f"{name} {sealed}")
                    r = self.run_dir("run1", 3)
                    if sealed:
                        (r / "RUN.json").write_text(json.dumps({"journal": {"lines": 7}}), encoding="utf-8")
                    (r / lineage.JOURNAL).write_bytes(cut((r / lineage.JOURNAL).read_bytes()))
                    self.assertEqual(lineage.account_of(r)["unread"], [])


class NamesThatAreNoPath(UnreadAsserts):
    """F-4: a record or a claim that names a run by a string no file can have (a NUL byte) raised ValueError out of
    `lineage_account` — a traceback in `aisef run --parent`. It is a part the lineage cannot name: unknown, listed."""

    def test_a_record_that_names_its_predecessor_by_such_a_string_is_unknown(self):
        r1 = self.run_dir("run1", 3)
        r2 = self.run_dir("run2", 2, continues=r1, records=False)
        for f in (lineage.STARTED, "RUN.json"):
            (r2 / f).write_text(json.dumps({"continues": {"path": str(r1) + "\0x"}}), encoding="utf-8")
        self.assert_unread(lineage.lineage_account(r2, self.root / "out"), "run2")

    def test_a_claim_that_names_its_run_by_such_a_string_is_unknown(self):
        r1 = self.run_dir("run1", 3)
        r2 = self.run_dir("run2", 2, continues=r1)
        self.claim(r1, 1, str(self.root / "child") + "\0x")
        self.claim(r1, 2, r2)
        self.assert_unread(lineage.lineage_account(r2, self.root / "out"), "CONTINUED-BY.json")
        self.assertEqual(lineage.continued_by(r1)[0], str(r2))     # the newest claim is a claim: as it was


# ------------------------------------------------------------------------------------------------ P3: the process table

class ProcessTableThatFailed(Hand):
    """P3: a claimant is provably gone when the process table says no such process — empty output, status 1, no message. A
    `ps` that FAILED (a message on stderr, a status that is neither 0 nor 1) says nothing: the claim is not superseded."""

    def held(self) -> pathlib.Path:
        pred = self.run_dir("pred")
        who = {"host": __import__("socket").gethostname(), "pid": 4242, "started": "Thu Jan  1 00:00:00 2026"}
        (pred / lineage.CLAIM).write_text(json.dumps({"run": str(self.root / "never-began"), "claimed": 1.0,
                                                      "claimant": who}) + "\n", encoding="utf-8")
        return pred

    @staticmethod
    def ps(returncode: int, stdout: str = "", stderr: str = ""):
        return mock.patch.object(lineage.subprocess, "run", return_value=subprocess.CompletedProcess(
            ["ps"], returncode, stdout=stdout, stderr=stderr))

    def test_a_ps_that_failed_is_unknown_not_no_such_process(self):
        for name, args in {"a message and status 1": (1, "", "ps: Operation not permitted"),
                           "a message and status 0": (0, "", "ps: failed to read the table"),
                           "no output and status 0": (0, "", ""), "a status that is neither": (2, "", ""),
                           "killed by a signal": (-9, "", "")}.items():
            with self.subTest(name), self.ps(*args):
                self.assertEqual(lineage.process_started(4242), "unknown")

    def test_no_such_process_is_still_none_and_a_live_one_its_start_text(self):
        with self.ps(1):
            self.assertIsNone(lineage.process_started(4242))
        with self.ps(0, "Thu Jan  1 00:00:00 2026\n"):
            self.assertEqual(lineage.process_started(4242), "Thu Jan  1 00:00:00 2026")

    def test_a_claim_is_not_superseded_on_the_word_of_a_ps_that_failed(self):
        pred = self.held()
        with self.ps(1, "", "ps: Operation not permitted"), self.assertRaises(lineage.LineageRefused) as c:
            lineage.claim(pred, self.root / "next", 2.0)
        self.assertIn("cannot be shown gone", str(c.exception))
        self.assertEqual([n for n, _ in lineage.claims(pred)], [1])
        with self.ps(1):                    # the table answered: no such process — superseded, as it always was
            doc = lineage.claim(pred, self.root / "next", 2.0)
        self.assertIs(doc["supersedes"]["claimant_gone"], True)


# ------------------------------------------------------------------------------------------------ P2/P4: the Budget

class BudgetArithmetic(unittest.TestCase):
    """P4, the arithmetic: the Budget's spend is preflight + lineage + own, and a ceiling counts all three (continuing
    never resets a budget). The lineage share is what the readable parts spent: the gate never builds a Budget for a
    lineage with a part not read (NoFlagOpensAPaidSession), so the only lineage share that is not a total is the one the
    operator accepted by name — and then the account says so beside the number."""

    LIMITS = {"provider_requests": 10, "turns": 10, "input_tokens": 1000, "output_tokens": 100}
    BASE = {"provider_requests": 1, "turns": 0, "input_tokens": 10, "output_tokens": 1}

    def budget(self, inherited: dict | None, own_requests: int = 0) -> client.Budget:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        return client.Budget(self.LIMITS, self.BASE, pathlib.Path(t.name), lambda: own_requests, inherited)

    def test_the_lineages_known_spend_counts_and_a_ceiling_it_reaches_stops_work(self):
        known = {"provider_requests": 9, "turns": 0, "input_tokens": 0, "output_tokens": 0}
        b = self.budget({**known, "unaccounted": [], "unread": [], "total": dict(known)})
        self.assertEqual(b.spend()["provider_requests"], 10)         # 1 + 9: continuing never resets a budget
        self.assertTrue(b.reached().startswith("max_provider_requests"))
        self.assertNotIn("inherited_unaccounted", b.account())

    def test_the_remaining_is_the_ceiling_less_preflight_lineage_and_own(self):
        known = {"provider_requests": 5, "turns": 0, "input_tokens": 0, "output_tokens": 0}
        self.assertIsNone(self.budget(known, own_requests=3).reached())                       # 1 + 5 + 3 = 9 of 10
        self.assertTrue(self.budget(known, own_requests=4).reached().startswith("max_provider_requests: 10 of 10"))

    def test_a_budget_over_a_lineage_with_evidence_that_cannot_be_read_stops_all_work(self):
        """F-6: the gate never builds one (run.execute refuses first); the arithmetic itself does not stand on that. The
        ceilings are not enforced against the known part of such a lineage: the budget reports it unaccounted, as it
        does a session that finished no step. (Spend the evidence READS as unknown is not that: ADR-8, accepted by name.)"""
        known = {"provider_requests": 2, "turns": 0, "input_tokens": 0, "output_tokens": 0}
        said = "run1: its journal evidence is there and cannot be read (not text): the provider requests it recorded are unknown spend"
        b = self.budget({**known, "unaccounted": [said], "unread": [said], "total": None})
        for stop in (b.reached(), b.exceeded()):
            self.assertTrue(stop.startswith("unaccounted:") and "cannot be read" in stop, stop)
        self.assertIsNone(self.budget({**known, "unaccounted": [said], "unread": [], "total": None}).reached())

    def test_what_was_accepted_is_in_the_account_beside_what_was_counted(self):
        known = {"provider_requests": 4, "turns": 0, "input_tokens": 0, "output_tokens": 0}
        said = ["run1: provider request seq 2 (S1, DEVELOPER) has no result — in flight when the run ended: what it "
                "spent is unknown"]
        acc = self.budget({**known, "unaccounted": said, "unread": [], "total": None}).account()
        self.assertEqual(acc["inherited"], known)
        self.assertEqual(acc["inherited_unaccounted"], said)


# ------------------------------------------------------------------------------------------------ P3/P4/P5: the gate

@POSIX_CLIENT
class NoFlagOpensAPaidSession(ProductBase):
    """P4/P5 through `run.execute` and the CLI: while any part of the lineage is not reconciled — evidence there that cannot
    be read, or a part that cannot be named — the run is refused at the claim stage, before the clone, the admission and
    the preflight (the first provider request), whatever `--accept-unaccounted` and `--supersede-claim` say; the refusal
    says what to do; nothing of the lineage's history is written or changed. A request in flight (evidence that reads) is
    still accepted by name."""

    run_dir, claim, locked, link, fresh, seal = (Hand.run_dir, Hand.claim, Hand.locked, Hand.link, Hand.fresh,
                                                 Hand.seal)

    def setUp(self) -> None:
        super().setUp()
        self.top = self.root = self.tmp / "lineage"
        self.top.mkdir()
        self.out_n = 0

    def refused_at_the_claim(self, **kw) -> str:
        """The refusal's text; the run began nothing: no provider request, no clone, no preflight, no budget."""
        self.out_n += 1
        out, transport = f"out{self.out_n}", provider()
        with self.assertRaises(R.RunRefused) as c:
            R.execute(self.project, self.settings, self.tmp / "source", self.tmp / out, transport=transport,
                      client_exe=str(self.client), cals=calibrations(), **kw)
        rec = json.loads((self.tmp / out / "RUN.json").read_text(encoding="utf-8"))
        self.assertEqual(transport.calls, [], "no provider request was made")
        self.assertEqual(rec["failure"]["stage"], "claim", rec["failure"])
        self.assertEqual([n for n in ("preflight", "repo", "run", "sessions") if (self.tmp / out / n).exists()], [])
        self.assertNotIn("preflight", rec)
        self.assertIsNone(rec["budget"], "no Budget was built: no ceiling was computed from the parts that were read")
        self.assertNotEqual(rec["delivery_verdict"], "PASS")
        self.last_rec = rec
        return str(c.exception)

    def assert_what_to_do(self, text: str) -> None:
        for needle in ("cannot be read", "not 0", "Make it readable again", "faithful copy",
                       "--accept-unaccounted does not cover it", "without --parent"):
            self.assertIn(needle, text)

    # a lineage, built fresh in `self.root`, with one part of it that does not read; each returns the predecessor to give

    def journal_not_text(self) -> pathlib.Path:
        r1 = self.run_dir("run1", requests=3)
        (r1 / lineage.JOURNAL).write_bytes(NOT_TEXT)
        return self.run_dir("run2", requests=2, continues=r1)

    def ledger_not_text(self) -> pathlib.Path:
        r1 = self.run_dir("run1", requests=3)
        (r1 / "preflight").mkdir()
        (r1 / "preflight" / "LEDGER.jsonl").write_bytes(NOT_TEXT)
        return self.run_dir("run2", requests=2, continues=r1)

    def stream_without_permission(self) -> pathlib.Path:
        r1 = self.run_dir("run1", requests=3, stream=True)
        self.locked(r1 / "sessions" / "S1.developer.1.jsonl", 0o000)
        return self.run_dir("run2", requests=2, continues=r1)

    def the_predecessors_own_journal(self) -> pathlib.Path:
        r1 = self.run_dir("run1", requests=3)
        (r1 / lineage.JOURNAL).write_bytes(NOT_TEXT)
        return r1

    def record_not_text(self) -> pathlib.Path:
        r1 = self.run_dir("run1", requests=3)
        r2 = self.run_dir("run2", requests=2, continues=r1)
        for f in (lineage.STARTED, "RUN.json"):
            (r2 / f).write_bytes(NOT_TEXT)
        return r2

    def record_of_the_first_run_cut(self) -> pathlib.Path:
        r1 = self.run_dir("run1", requests=3)
        for f in (lineage.STARTED, "RUN.json"):
            (r1 / f).write_bytes(b'{"continues": {"pa')
        return r1

    def claim_generation_cut(self) -> pathlib.Path:
        r1 = self.run_dir("run1", requests=3)
        r2 = self.run_dir("run2", requests=2, continues=r1)
        self.claim(r1, 1, None, raw=b'{"run": "/x", "cla')
        self.claim(r1, 2, r2)
        return r2

    def journal_a_link_to_nothing(self) -> pathlib.Path:
        r1 = self.run_dir("run1", requests=3, journal=False)
        (r1 / lineage.JOURNAL).parent.mkdir(parents=True)
        self.link(r1 / lineage.JOURNAL, self.root / "nowhere.jsonl")
        return self.run_dir("run2", requests=2, continues=r1)

    def records_are_links_to_nothing(self) -> pathlib.Path:
        """run3 (readable) continues run2, whose two records are links to nothing, and run2 continued run1 (3 requests)."""
        self.run_dir("run1", requests=3)
        r2 = self.run_dir("run2", requests=2, records=False)
        for f in (lineage.STARTED, "RUN.json"):
            self.link(r2 / f, self.root / "nowhere.json")
        return self.run_dir("run3", requests=1, continues=r2)

    def records_are_links_that_loop(self) -> pathlib.Path:
        self.run_dir("run1", requests=3)
        r2 = self.run_dir("run2", requests=2, records=False)
        for f in (lineage.STARTED, "RUN.json"):
            self.link(r2 / f, r2 / f)
        return self.run_dir("run3", requests=1, continues=r2)

    def claim_generation_is_a_link_to_nothing(self) -> pathlib.Path:
        r1 = self.run_dir("run1", requests=3)
        r2 = self.run_dir("run2", requests=2, continues=r1)
        self.link(r1 / lineage.CLAIM, self.root / "nowhere.json")
        self.claim(r1, 2, r2)
        return r2

    def ancestor_directory_is_not_there(self) -> pathlib.Path:
        return self.run_dir("run2", requests=2, continues=self.root / "run1")

    def ancestor_directory_is_a_link_to_nothing(self) -> pathlib.Path:
        self.link(self.root / "run1", self.root / "nowhere")
        return self.run_dir("run2", requests=2, continues=self.root / "run1")

    def predecessors_journal_emptied_under_its_record(self) -> pathlib.Path:
        r1 = self.run_dir("run1", requests=3, seal=True)
        (r1 / lineage.JOURNAL).write_bytes(b"")
        return r1

    def ancestors_journal_cut_at_a_line_under_its_record(self) -> pathlib.Path:
        r1 = self.run_dir("run1", requests=3, seal=True)
        (r1 / lineage.JOURNAL).write_bytes(b"\n".join((r1 / lineage.JOURNAL).read_bytes().split(b"\n")[:3]) + b"\n")
        return self.run_dir("run2", requests=2, continues=r1)

    def record_names_a_path_with_a_nul(self) -> pathlib.Path:
        r1 = self.run_dir("run1", requests=3)
        r2 = self.run_dir("run2", requests=2, continues=r1, records=False)
        for f in (lineage.STARTED, "RUN.json"):
            (r2 / f).write_text(json.dumps({"continues": {"path": str(r1) + "\0x"}}), encoding="utf-8")
        return r2

    def claim_names_a_run_with_a_nul(self) -> pathlib.Path:
        r1 = self.run_dir("run1", requests=3)
        r2 = self.run_dir("run2", requests=2, continues=r1)
        self.claim(r1, 1, str(self.root / "child") + "\0x")
        self.claim(r1, 2, r2)
        return r2

    def test_no_flag_opens_a_session_over_a_part_that_does_not_read(self):
        builders = {"a journal that is not text": self.journal_not_text, "a ledger that is not text": self.ledger_not_text,
                    "the predecessor's own journal": self.the_predecessors_own_journal,
                    "a record of the chain that is not text": self.record_not_text,
                    "the record of the first run, cut": self.record_of_the_first_run_cut,
                    "a claim generation that is cut": self.claim_generation_cut,
                    "a journal that is a link to nothing": self.journal_a_link_to_nothing,
                    "records that are links to nothing": self.records_are_links_to_nothing,
                    "records that are links that loop": self.records_are_links_that_loop,
                    "a claim generation that is a link to nothing": self.claim_generation_is_a_link_to_nothing,
                    "an ancestor whose directory is not there": self.ancestor_directory_is_not_there,
                    "an ancestor that is a link to nothing": self.ancestor_directory_is_a_link_to_nothing,
                    "the predecessor's journal emptied under its record": self.predecessors_journal_emptied_under_its_record,
                    "an ancestor's journal cut at a line under its record": self.ancestors_journal_cut_at_a_line_under_its_record,
                    "a record that names its predecessor by a path with a NUL": self.record_names_a_path_with_a_nul,
                    "a claim that names its run by a string with a NUL": self.claim_names_a_run_with_a_nul}
        if IS_POSIX_USER:
            builders["a session stream with no read permission"] = self.stream_without_permission
        for name, build in builders.items():
            for flags in ({}, {"accept_unaccounted": True}):
                with self.subTest(name, flags=flags):
                    self.fresh(f"{name} {flags}")
                    pred = build()
                    before = snapshot(self.root)
                    self.assert_what_to_do(self.refused_at_the_claim(predecessor=pred, **flags))
                    account = self.last_rec["continues"]["account"]      # the record says what the refusal says
                    self.assertIsNone(account["total"])
                    self.assertTrue(account["unread"] and account["unaccounted"], account)
                    self.assertNotIn("accepted_unaccounted", self.last_rec["continues"])
                    after = snapshot(self.root)
                    self.assertTrue(set(before) <= set(after))
                    self.assertEqual({k: after[k] for k in before}, before, "history was not rewritten, a byte")
                    self.assertTrue(all(pathlib.PurePosixPath(n).name.startswith("CONTINUED-BY")
                                        for n in set(after) - set(before)), sorted(set(after) - set(before)))

    def child_not_text(self) -> pathlib.Path:
        child = self.run_dir("run3", requests=4)
        (child / lineage.JOURNAL).write_bytes(NOT_TEXT)
        return child

    def child_a_link_to_nothing(self) -> pathlib.Path:
        child = self.run_dir("run3", requests=4, journal=False)
        (child / lineage.JOURNAL).parent.mkdir(parents=True)
        self.link(child / lineage.JOURNAL, self.root / "nowhere.jsonl")
        return child

    def child_without_permission(self) -> pathlib.Path:
        child = self.run_dir("run3", requests=4)
        self.locked(child / lineage.JOURNAL, 0o000)
        return child

    def test_superseding_the_claim_of_a_child_that_does_not_read_does_not_open_a_session_and_rewrites_nothing(self):
        builders = {"a journal that is not text": self.child_not_text, "a journal that is a link to nothing":
                    self.child_a_link_to_nothing}
        if IS_POSIX_USER:
            builders["a journal with no read permission"] = self.child_without_permission
        for name, build in builders.items():
            with self.subTest(name):
                self.fresh(name)
                pred = self.run_dir("run2", requests=2)
                child = build()
                sha = hashlib.sha256(self.claim(pred, 1, child)).hexdigest()
                before = snapshot(self.root)
                # without the operator's assertion: the claim is not taken, not by the claimant's absence, nothing written
                self.out_n += 1
                with self.assertRaises(R.RunRefused) as c:
                    R.execute(self.project, self.settings, self.tmp / "source", self.tmp / f"asked{self.out_n}",
                              transport=provider(), client_exe=str(self.client), cals=calibrations(), predecessor=pred)
                self.assertIn("UNREAD", str(c.exception))
                self.assertEqual(snapshot(self.root), before)
                # with it, and with the flag as well: the assertion is recorded, and the session does not open
                for flags in ({"supersede_claim": sha}, {"supersede_claim": sha, "accept_unaccounted": True}):
                    text = self.refused_at_the_claim(predecessor=pred, **flags)
                    self.assert_what_to_do(text)
                    self.assertIn("run3", text)
                after = snapshot(self.root)
                self.assertEqual({k: after[k] for k in before}, before, "no claim, no record of the lineage was changed")
                added = sorted(set(after) - set(before))
                self.assertTrue(added and all(pathlib.PurePosixPath(n).name.startswith("CONTINUED-BY.") for n in added), added)
                asserted = [json.loads(after[n])["supersedes"] for n in added
                            if json.loads(after[n]).get("supersedes", {}).get("sha256") == sha]
                self.assertEqual([a["operator_asserted"] for a in asserted], [True])

    def test_superseding_the_claim_of_a_predecessor_that_does_not_read_does_not_open_a_session_either(self):
        """The predecessor's own journal does not read; its claimant is elsewhere and its child did not begin, so only the
        operator's sha256 supersedes — and what the predecessor spent is still not known."""
        pred = self.the_predecessors_own_journal()
        sha = hashlib.sha256(self.claim(pred, 1, self.root / "never-began")).hexdigest()
        before = snapshot(self.root)
        for flags in ({"supersede_claim": sha}, {"supersede_claim": sha, "accept_unaccounted": True}):
            self.assert_what_to_do(self.refused_at_the_claim(predecessor=pred, **flags))
        after = snapshot(self.root)
        self.assertEqual({k: after[k] for k in before}, before)
        self.assertTrue(any(json.loads(v).get("supersedes", {}).get("operator_asserted") is True
                            for k, v in after.items() if k not in before), "the operator's assertion is recorded")

    def test_the_refusal_names_the_directory_of_each_run_whose_evidence_must_be_made_readable(self):
        """P5: "a faithful copy of the run directory at the path named" — the entries name a run by its basename (two runs
        of a lineage may be called `out`), so the refusal names the paths."""
        for build in (self.journal_not_text, self.ancestor_directory_is_not_there, self.ancestors_journal_cut_at_a_line_under_its_record):
            with self.subTest(build.__name__):
                self.fresh(build.__name__)
                text = self.refused_at_the_claim(predecessor=build())
                self.assertIn(str(self.root / "run1"), text)

    @POSIX_USER
    def test_a_stream_of_the_lineage_that_cannot_be_read_does_not_cost_the_record_its_usage(self):
        """R-7: the lineage's money and tokens raised out of `usage_lineage`, and one handler dropped this run's own `usage`
        and the whole `lineage_usage` with it: the readable parts' cost stays attributed beside an unknown total."""
        self.refused_at_the_claim(predecessor=self.stream_without_permission())
        rec = self.last_rec
        self.assertNotIn("error", rec["usage"], rec["usage"])
        whole = rec["lineage_usage"]
        self.assertIsNotNone(whole)
        by_run = {pathlib.Path(e["run"]).name: e for e in whole["runs"]}
        self.assertIsNone(by_run["run1"]["cost"]["value"])
        self.assertIn("cannot be read", by_run["run1"]["cost"]["status"])
        self.assertIn("run2", by_run)                               # the readable part is still there, attributed
        self.assertIsNone(whole["cost"]["value"])
        self.assertTrue(whole["tokens_status"].startswith("lower bound"), whole["tokens_status"])

    def test_the_cli_refuses_with_exit_2_and_says_what_to_do(self):
        r2 = self.journal_not_text()
        (self.tmp / "bundle.json").write_text(json.dumps(project_bundle(self.baseline)), encoding="utf-8")
        (self.tmp / "settings.json").write_text(json.dumps(SETTINGS), encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = cli.run(["--project", str(self.tmp / "bundle.json"), "--settings", str(self.tmp / "settings.json"),
                            "--repo", str(self.tmp / "source"), "--out", str(self.tmp / "cli-out"), "--parent", str(r2),
                            "--accept-unaccounted"])
        self.assertEqual(code, 2, err.getvalue())
        self.assertRegex(err.getvalue(), r"^aisef run: refused: ")
        self.assert_what_to_do(err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_a_request_in_flight_is_still_refused_without_the_flag_and_accepted_by_name_with_it(self):
        r1 = self.run_dir("run1", requests=2, in_flight=True)
        text = self.refused_at_the_claim(predecessor=r1)
        self.assertIn("--accept-unaccounted", text)
        self.assertIn("no evidence accounts for", text)
        self.assertNotIn("Make it readable again", text)     # its evidence reads: nothing to make readable
        rec = R.execute(self.project, self.settings, self.tmp / "source", self.tmp / "accepted", transport=provider(),
                        client_exe=str(self.client), cals=calibrations(), predecessor=r1, accept_unaccounted=True)
        # the gate was passed (the run delivered its story): what was accepted is recorded, and the outputs say that no
        # total is known — the budget's account, the lineage's tokens and money, the record's account of the lineage
        self.assertEqual(rec["delivery_verdict"], "PASS", rec.get("failure"))
        said = rec["continues"]["accepted_unaccounted"]
        self.assertEqual(len(said), 1)
        self.assertIn("in flight", said[0])
        self.assertEqual(rec["budget"]["inherited_unaccounted"], said)
        account = rec["continues"]["account"]
        self.assertIsNone(account["total"])
        self.assertEqual(account["unaccounted"], said)
        self.assertEqual(account["unread"], [])
        # run1, and `out1`: the refused attempt above claimed it and was superseded by evidence — it spent nothing
        self.assertEqual([(pathlib.Path(r["run"]).name, r["provider_requests"], bool(r.get("superseded")))
                          for r in account["runs"]], [("run1", 2, False), ("out1", 0, True)])
        self.assertIsNone(rec["lineage_usage"]["cost"]["value"])
        self.assertTrue(rec["lineage_usage"]["tokens_status"].startswith("lower bound"))
        v = verify(self.project, self.tmp / "accepted")      # and the verifier says it was accepted, not that it is known
        self.assertEqual((v["verdict"], v["problems"]), ("VERIFIED", []))
        self.assertTrue(any("accepted by name" in n for n in v["notes"]), v["notes"])


# ------------------------------------------------------------------------------------------------ bundle continue, --verify

@POSIX_CLIENT
class Delivered(ProductBase):
    """One delivered run (`first`) and, built from it, a continuation (`second`, of the bundle `doc2`)."""

    def setUp(self) -> None:
        super().setUp()
        self.doc = project_bundle(self.baseline)
        self.rec = self.execute("first")
        self.first = self.tmp / "first"
        self.assertEqual(self.rec["delivery_verdict"], "PASS", self.rec.get("failure"))

    def continue_run(self, out: str = "second", **kw) -> dict:
        self.doc2, _ = bundle_cli.continue_from(self.doc, self.first)
        self.project2 = bundle.load(self.doc2)
        return R.execute(self.project2, self.settings, self.first / "repo", self.tmp / out, transport=provider(),
                         client_exe=str(self.client), cals=calibrations(), predecessor=self.first, **kw)

    def spoil_ledger_of(self, run: pathlib.Path) -> None:
        (run / "preflight" / "LEDGER.jsonl").write_bytes(b"\xff\xfe not a ledger\n")


class BundleContinue(Delivered):
    """P1/P2/P5 for `aisef bundle continue`: its report keeps the readable parts' spend (`spend.known`, per run in
    `spend_by_run`) apart from the lineage's total (`spend.total`, None while any part is unknown) and says what `aisef run
    --parent` will do — before the operator runs it. It accounted only the run it continues (`account_of`): an ancestor's
    unknown spend was invisible until the next run was refused."""

    def test_a_lineage_that_reads_has_a_total_and_nothing_to_refuse(self):
        _, report = bundle_cli.continue_from(self.doc, self.first)
        self.assertEqual(report["spend"]["total"], report["spend"]["known"])
        self.assertEqual((report["unaccounted"], report["unread"], report["run_parent_refused"]), ([], [], None))
        self.assertEqual([pathlib.Path(r["run"]).name for r in report["spend_by_run"]], ["first"])

    def test_a_ledger_that_cannot_be_read_is_unknown_and_the_report_says_the_next_run_is_refused(self):
        self.spoil_ledger_of(self.first)
        _, report = bundle_cli.continue_from(self.doc, self.first)
        self.assertTrue(report["unaccounted"], report)
        self.assertIsNone(report["spend"]["total"])
        self.assertTrue(report["unread"], report)
        self.assertIn("ledger", report["unread"][0])
        self.assertIn("no flag accepts it", report["run_parent_refused"])
        self.assertIn("faithful copy", report["run_parent_refused"])
        with self.assertRaises(R.RunRefused) as c:      # and it is: with the flag too
            self.continue_run("second", accept_unaccounted=True)
        self.assertIn("Make it readable again", str(c.exception))

    def test_the_report_names_where_to_restore_and_sends_the_operator_to_no_command_that_will_be_refused(self):
        """P5: `run_parent_refused` says "the run directory at the path named" — and names only a basename; `next` was the
        `aisef run --parent` command that is refused. Each row of `spend_by_run` says whether its figures are exact."""
        _, clean = bundle_cli.continue_from(self.doc, self.first)
        self.assertTrue(clean["next"].startswith("aisef run "), clean["next"])
        self.assertEqual([r["exact"] for r in clean["spend_by_run"]], [True])
        self.spoil_ledger_of(self.first)
        _, report = bundle_cli.continue_from(self.doc, self.first)
        self.assertIn(str(self.first), report["run_parent_refused"])
        self.assertEqual([r["exact"] for r in report["spend_by_run"]], [False])
        self.assertFalse(report["next"].startswith("aisef run "), report["next"])
        self.assertIn("aisef run ", report["next"])
        self.assertIn("unread", report["next"])

    def test_the_report_names_the_whole_lineage_not_only_the_run_it_continues(self):
        second = self.continue_run()
        self.assertEqual(second["delivery_verdict"], "PASS", second.get("failure"))
        self.spoil_ledger_of(self.first)      # the ancestor's evidence, two runs back
        _, report = bundle_cli.continue_from(self.doc2, self.tmp / "second")
        self.assertTrue(any("first" in u and "ledger" in u for u in report["unaccounted"]), report["unaccounted"])
        self.assertEqual([pathlib.Path(r["run"]).name for r in report["spend_by_run"]], ["second", "first"])
        self.assertTrue(any("first" in u and "ledger" in u for u in report["unread"]), report["unread"])
        self.assertIsNone(report["spend"]["total"])

    def test_the_cli_prints_the_same(self):
        self.spoil_ledger_of(self.first)
        (self.tmp / "b.json").write_text(json.dumps(self.doc), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bundle_cli.main(["continue", str(self.tmp / "b.json"), "--from-run", str(self.first),
                                    "--out", str(self.tmp / "c.json")])
        self.assertEqual(code, 0, err.getvalue())
        printed = json.loads(out.getvalue())
        self.assertEqual({"spend", "spend_by_run", "unaccounted", "unread", "run_parent_refused"} - set(printed), set())
        self.assertIsNone(printed["spend"]["total"])
        self.assertTrue(printed["unread"])


class VerifyCannotRederive(Delivered):
    """P1 for `aisef run --verify`: a continuation whose lineage's evidence cannot be read now is REFUTED because that
    evidence cannot be read — the inherited share the record states cannot be re-derived — not because the record's numbers
    happen to differ: when the unreadable part adds nothing to the sums, it was VERIFIED."""

    def test_a_lineage_that_reads_verifies_and_one_that_does_not_is_refuted_for_that_reason(self):
        rec = self.continue_run()
        self.assertEqual(rec["delivery_verdict"], "PASS", rec.get("failure"))
        v = verify(self.project2, self.tmp / "second")
        self.assertEqual((v["verdict"], v["problems"]), ("VERIFIED", []))
        self.spoil_ledger_of(self.first)
        v = verify(self.project2, self.tmp / "second")
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertTrue(any("lineage's evidence cannot be read now" in p and "ledger" in p for p in v["problems"]),
                        v["problems"])

    def test_records_of_the_ancestor_that_cannot_be_read_refute_even_when_the_sums_do_not_move(self):
        rec = self.continue_run()
        self.assertEqual(rec["delivery_verdict"], "PASS", rec.get("failure"))
        for f in (lineage.STARTED, "RUN.json"):     # `first` continued nothing: only a record that reads can say so
            (self.first / f).write_text('{"continues": {"pa', encoding="utf-8")
        v = verify(self.project2, self.tmp / "second")
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertTrue(any("cannot be read now" in p for p in v["problems"]), v["problems"])
        self.assertFalse(any("spend is not what the evidence re-derives" in p for p in v["problems"]), v["problems"])


class JournalCutUnderItsRecord(Delivered):
    """F-1 end to end: a delivered run `first` is continued by `second`; then the journal of `first` is cut at a line
    boundary — a hash chain that is valid, under a RUN.json that names the whole journal. Reading it as the run's spend
    made the requests that were cut unknown only by luck (fewer journaled requests than session streams: an unaccounted
    spend `--accept-unaccounted` accepted) and, with no streams, nothing at all."""

    def setUp(self) -> None:
        super().setUp()
        self.assertEqual(self.continue_run()["delivery_verdict"], "PASS")
        journal = self.first / lineage.JOURNAL
        journal.write_bytes(b"\n".join(journal.read_bytes().split(b"\n")[:5]) + b"\n")

    def test_the_next_continuation_is_refused_whatever_the_flag(self):
        second = self.tmp / "second"
        for n, flags in enumerate(({}, {"accept_unaccounted": True})):
            with self.subTest(flags=flags), self.assertRaises(R.RunRefused) as c:
                R.execute(self.project2, self.settings, second / "repo", self.tmp / f"third{n}", transport=provider(),
                          client_exe=str(self.client), cals=calibrations(), predecessor=second, **flags)
            self.assertIn("Make it readable again", str(c.exception))
            self.assertIn(str(self.first), str(c.exception))

    def test_verify_cannot_rederive_the_inherited_share(self):
        v = verify(self.project2, self.tmp / "second")
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertTrue(any("lineage's evidence cannot be read now" in p for p in v["problems"]), v["problems"])


if __name__ == "__main__":
    unittest.main()
