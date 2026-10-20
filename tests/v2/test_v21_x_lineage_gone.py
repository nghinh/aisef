"""V2.1 (owner decision 2026-10-15, lineage family, item 2; round 2): evidence of a run that is GONE is cost unknown —
never a number that looks reconciled.

The gap (found by the final verifier of round 1): when `sessions/` or `preflight/` of a run that was handed over is not
there NEXT TO a journal that reads, `lineage.account_of` answered `exact: True` and `unaccounted: []`, `lineage_account`
a `total` that looked complete (turns 0, 18 input tokens, where the run's RUN.json records 5 requests, 2 turns, 278
input and 22 output tokens), and `usage_lineage` a cost of 2.2e-05 "known" where the evidence the run left priced
0.000304. Only evidence that EXISTS and cannot be read was unknown; evidence that is gone was a run that spent less.

What the owner required (the narrow rule, option (a)) and what is pinned here, shape by shape:

* a RUN.json whose `budget.spent` (less the `budget.inherited` share) EXCEEDS what the evidence re-derives, and, with no
  record that names a spend (a run killed before RUN.json), a request the journal records as ANSWERED (a result that is
  not a closer's) for which no stream stands — make that run UNREAD for cost: `exact` False, `total` None, cost None,
  `aisef run --parent` refused with the refusal of any unread evidence whatever the flags, history never rewritten, no
  claim released because of it, and the refusal says what to restore;
* the known part of that run stays attributed to it (the counters are what is left, no more exact than that);
* what the record vouches for is not gone (a session that never started leaves an answered request and no stream); more
  evidence than the record names is not gone either; a request in flight (no result) is the state
  tests/v2/test_v21_defects_lineage2.py pins and is neither;
* a normal complete lineage is unchanged: its total is what its records say, and a continuation does not count the share
  it inherited as its own evidence;
* (review round 2) a run that failed before its Budget was built (the route not attested) names the preflight's own
  account in RUN.json (`preflight.accounting`): that is its record of spend, compared like `budget.spent`;
* (review round 2) with no record, an answered request with no stream is gone OR a session that never started (a budget
  reached, a reviewer that could not run) — the journal cannot tell them apart. The rule takes the unknown, as the owner
  wrote it, and the cause says there may be nothing to restore. Narrowing it (only a COMPLETED request owes a stream) is an
  open owner decision, pinned here as it is: `NoRecordCannotTellGoneFromNeverStarted`.

Unchanged and not touched here (owner decisions already recorded): the three `StaysAsItWas` pins of
tests/v2/test_v21_defects_lineage2.py (one request in flight), R3 (a replaced child a claim names whose directory is gone
stays UNBEGUN), R4 (`--accept-unaccounted` over spend the evidence READS as in flight), R5 (the claim comes before the gate).

Offline and deterministic; the full-run classes use the fake client of tests/v2/test_app_run.py. Evidence is "gone" by
renaming it away, cutting a file or editing the copy of a run directory this test made: nothing here deletes or kills
(INV-MUTATION-AUTHORITY)."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, bundle_cli, cli, client, lineage, preflight, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import verify  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from aisef2.journal.event import EventType as T  # noqa: E402
from tests.v2 import test_v21_x_lineage_proof as P  # noqa: E402
from tests.v2.test_app_run import SETTINGS, ProductBase, calibrations, project_bundle, provider  # noqa: E402

SPEND = lineage.SPEND
#: what the fake client's run spends (tests/v2/test_app_run.py): the preflight is a listing and two probes (3 requests,
#: 18 input and 2 output tokens), the journal records two requests (the developer's and the reviewer's), each session
#: finishes one step (130 input tokens with the cache read, 10 output with the reasoning)
INTACT = {"provider_requests": 5, "turns": 2, "input_tokens": 278, "output_tokens": 22}
OWN = {"tokens": {"input": 0, "output": 0}, "cost": {"value": 0.0, "status": "known"}, "sessions": []}
THE_REFUSAL = ("cannot be read", "not 0", "Make it readable again", "faithful copy", "--accept-unaccounted does not cover it",
               "without --parent", "is gone", "RUN.json records")


def moved(path: pathlib.Path) -> None:
    """Out of sight, not deleted: the file or directory is renamed (the test's own copy of a run)."""
    os.rename(path, path.with_name(path.name + ".moved"))


def first_line_only(path: pathlib.Path) -> None:
    path.write_text(path.read_text(encoding="utf-8").split("\n")[0] + "\n", encoding="utf-8")


def ledger_two_rows(d: pathlib.Path) -> None:
    ledger = d / "preflight" / "LEDGER.jsonl"
    ledger.write_text("".join(ledger.read_text(encoding="utf-8").splitlines(keepends=True)[:2]), encoding="utf-8")


def record_says_more(d: pathlib.Path) -> None:
    rec = json.loads((d / "RUN.json").read_text(encoding="utf-8"))
    rec["budget"]["spent"]["turns"] += 1
    rec["budget"]["spent"]["output_tokens"] += 5
    (d / "RUN.json").write_text(json.dumps(rec), encoding="utf-8")


#: shape -> (how the evidence goes, what is left of it: the four counters the account keeps for the run)
SHAPES = {
    "the sessions directory is moved away": (lambda d: moved(d / "sessions"),
                                             {"provider_requests": 5, "turns": 0, "input_tokens": 18, "output_tokens": 2}),
    "the preflight directory is moved away": (lambda d: moved(d / "preflight"),
                                              {"provider_requests": 2, "turns": 2, "input_tokens": 260, "output_tokens": 20}),
    "one session stream is moved away": (lambda d: moved(d / "sessions" / "S1.reviewer.1.jsonl"),
                                         {"provider_requests": 5, "turns": 1, "input_tokens": 148, "output_tokens": 12}),
    "a session stream is cut to its first line": (lambda d: first_line_only(d / "sessions" / "S1.developer.1.jsonl"),
                                                  {"provider_requests": 5, "turns": 1, "input_tokens": 148,
                                                   "output_tokens": 12}),
    "the preflight's ledger is cut to its first rows": (ledger_two_rows,
                                                        {"provider_requests": 3, "turns": 2, "input_tokens": 260,
                                                         "output_tokens": 20}),
    "the record says more than the evidence holds": (record_says_more, INTACT),
}


@P.POSIX_CLIENT
class Gone(P.Delivered):
    """A delivered run with a record, copied and damaged: the evidence it left is no longer all there."""

    claim = P.Hand.claim

    def setUp(self) -> None:
        super().setUp()
        self.n = 0

    def copy(self, name: str) -> pathlib.Path:
        dst = self.tmp / "".join(c if c.isalnum() else "-" for c in name)
        shutil.copytree(self.first, dst, symlinks=True)
        return dst

    def damaged(self, name: str) -> pathlib.Path:
        d = self.copy(name)
        SHAPES[name][0](d)
        return d

    def refused(self, pred: pathlib.Path, **kw) -> tuple[str, dict]:
        """The refusal's text and the refused run's record; it began nothing: no provider request, no clone, no preflight,
        no Budget (so no ceiling was computed from the part that was read)."""
        self.n += 1
        out, transport = self.tmp / f"asked{self.n}", provider()
        with self.assertRaises(R.RunRefused) as c:
            R.execute(self.project, self.settings, self.tmp / "source", out, transport=transport,
                      client_exe=str(self.client), cals=calibrations(), predecessor=pred, **kw)
        rec = json.loads((out / "RUN.json").read_text(encoding="utf-8"))
        self.assertEqual(transport.calls, [], "no provider request was made")
        self.assertEqual(rec["failure"]["stage"], "claim", rec["failure"])
        self.assertEqual([n for n in ("preflight", "repo", "run", "sessions") if (out / n).exists()], [])
        self.assertIsNone(rec["budget"])
        self.assertNotIn("accepted_unaccounted", rec["continues"])
        self.assertIsNone(rec["continues"]["account"]["total"])
        self.assertTrue(rec["continues"]["account"]["unread"], rec["continues"]["account"])
        whole = rec["lineage_usage"]        # the refused run's own record states the lineage's money and tokens as unknown
        self.assertIsNone(whole["cost"]["value"])
        self.assertTrue(whole["tokens_status"].startswith("lower bound"), whole["tokens_status"])
        return str(c.exception), rec

    # ---------------------------------------------------------------------------------------------------- controls

    def test_an_intact_run_and_its_continuation_are_exact_and_the_totals_are_the_records(self):
        """Before and after the change: the figures of a normal complete lineage. The totals are what the runs' own RUN.json
        record, and the share the continuation inherited is not counted as its own evidence."""
        self.assertEqual({k: self.rec["budget"]["spent"][k] for k in SPEND}, INTACT)
        acct = lineage.account_of(self.first)
        self.assertEqual(({k: acct[k] for k in SPEND}, acct["exact"], acct["unaccounted"], acct["unread"]),
                         (INTACT, True, [], []))
        got = lineage.lineage_account(self.first, self.tmp / "next")
        self.assertEqual((got["total"], got["unaccounted"], got["unread"]), (INTACT, [], []))
        whole = lineage.usage_lineage(self.first, self.tmp / "next", OWN, P.PRICES)
        self.assertEqual((whole["cost"]["status"], whole["tokens_status"]), ("known", "known"))
        self.assertAlmostEqual(whole["cost"]["value"], 0.000304, places=6)
        second = self.continue_run()
        self.assertEqual(second["delivery_verdict"], "PASS", second.get("failure"))
        spent = {k: second["budget"]["spent"][k] for k in SPEND}
        self.assertEqual(second["budget"]["inherited"], INTACT)     # what the continuation counted of the lineage
        both = lineage.lineage_account(self.tmp / "second")
        self.assertEqual((both["total"], both["unaccounted"], both["unread"]), (spent, [], []))
        self.assertEqual([pathlib.Path(r["run"]).name for r in both["runs"]], ["second", "first"])
        self.assertEqual(verify(self.project2, self.tmp / "second")["verdict"], "VERIFIED")

    def test_a_real_run_killed_before_its_record_has_nothing_to_exceed_and_needs_a_stream_per_answered_request(self):
        """The copy of a finished run less its RUN.json (what a run killed before its record holds, as
        tests/v2/test_v21_kills3_T13a.py makes it): exact while each answered request has its stream — the journal's two
        requests, one the developer's and one the reviewer's — and unknown, with the cause, when one has not."""
        d = self.copy("killed")
        moved(d / "RUN.json")
        acct = lineage.account_of(d)
        self.assertEqual(({k: acct[k] for k in SPEND}, acct["exact"], acct["recorded"], acct["unread"]), (INTACT, True, False, []))
        for name, damage, said in (("the sessions directory", lambda x: moved(x / "sessions"),
                                    "S1 developer: 1 answered, 0 streams; S1 reviewer: 1 answered, 0 streams"),
                                   ("the reviewer's stream", lambda x: moved(x / "sessions" / "S1.reviewer.1.jsonl"),
                                    "S1 reviewer: 1 answered, 0 streams")):
            with self.subTest(name):
                e = self.copy(name)
                moved(e / "RUN.json")
                damage(e)
                got = lineage.account_of(e)
                self.assertEqual(len(got["unread"]), 1, got["unread"])
                self.assertIn(said, got["unread"][0])
                self.assertIs(got["exact"], False)
                self.assertIsNone(lineage.lineage_account(e)["total"])
                text, _ = self.refused(e, accept_unaccounted=True)
                self.assertIn(str(e), text)
                self.assertIn("is gone", text)

    # ---------------------------------------------------------------------------------------------------- the account

    def test_each_shape_makes_the_run_unknown_and_the_known_part_stays_attributed_to_it(self):
        for name, (_, left) in SHAPES.items():
            with self.subTest(name):
                d = self.damaged(name)
                acct = lineage.account_of(d)
                self.assertIs(acct["exact"], False)
                self.assertIs(acct["recorded"], True)
                self.assertEqual(len(acct["unread"]), 1, acct["unread"])
                self.assertIn(acct["unread"][0], acct["unaccounted"])
                self.assertIn("RUN.json records", acct["unread"][0])
                self.assertIn("is not there", acct["unread"][0])
                self.assertEqual({k: acct[k] for k in SPEND}, left)     # what is left: a lower bound, attributed
                got = lineage.lineage_account(d, self.tmp / "next")
                self.assertIsNone(got["total"])
                self.assertEqual(got["unread"], acct["unread"])
                self.assertEqual(lineage.unread_runs(got), str(d))      # where the operator restores it
                self.assertEqual({k: got[k] for k in SPEND}, left)
                self.assertIs(got["runs"][0]["exact"], False)

    def test_each_shape_makes_the_cost_unknown_not_a_smaller_figure(self):
        for name in SHAPES:
            with self.subTest(name):
                d = self.damaged(name)
                whole = lineage.usage_lineage(d, self.tmp / "next", OWN, P.PRICES)
                row = whole["runs"][0]
                self.assertIsNone(row["cost"]["value"])
                self.assertTrue(row["cost"]["status"].startswith("partial: "), row["cost"])
                if name != "a session stream is cut to its first line":     # that one the usage account leaves unpriced itself
                    self.assertIn("RUN.json records", row["cost"]["status"])
                self.assertIn("known", row["cost"])             # what the evidence left prices, kept apart
                self.assertIsNone(whole["cost"]["value"])
                self.assertTrue(whole["cost"]["status"].startswith("unknown"), whole["cost"])
                self.assertTrue(whole["tokens_status"].startswith("lower bound"), whole["tokens_status"])

    def test_reading_the_account_writes_nothing_into_the_run(self):
        d = self.damaged("the sessions directory is moved away")
        before = P.snapshot(d)
        lineage.account_of(d)
        lineage.lineage_account(d, self.tmp / "next")
        lineage.usage_lineage(d, self.tmp / "next", OWN, P.PRICES)
        bundle_cli.continue_from(self.doc, d)
        self.assertEqual(P.snapshot(d), before)

    # ---------------------------------------------------------------------------------------------------- the gate

    def test_no_flag_opens_a_session_over_evidence_that_is_gone_and_the_refusal_says_what_to_restore(self):
        for name in SHAPES:
            with self.subTest(name):
                d = self.damaged(name)
                before = P.snapshot(d)
                for flags in ({}, {"accept_unaccounted": True}):
                    text, rec = self.refused(d, **flags)
                    for needle in THE_REFUSAL:
                        self.assertIn(needle, text)
                    self.assertIn(str(d), text)                     # the run directory to restore, by its path
                    self.assertIn("RUN.json records", " ".join(rec["continues"]["account"]["unread"]))
                # the operator names the claim of a child that never began: the claim is superseded, the run is not opened
                e = self.copy(name + " asserted")
                SHAPES[name][0](e)
                sha = hashlib.sha256(self.claim(e, 1, self.tmp / "never-began")).hexdigest()
                for flags in ({"supersede_claim": sha}, {"supersede_claim": sha, "accept_unaccounted": True}):
                    text, _ = self.refused(e, **flags)
                    for needle in THE_REFUSAL:
                        self.assertIn(needle, text)
                after = P.snapshot(d)
                self.assertEqual({k: after[k] for k in before}, before, "history was not rewritten, a byte")
                self.assertTrue(all(pathlib.PurePosixPath(n).name.startswith("CONTINUED-BY") for n in set(after) - set(before)),
                                sorted(set(after) - set(before)))

    def test_the_cli_refuses_with_exit_2_and_says_what_to_restore(self):
        d = self.damaged("the preflight directory is moved away")
        (self.tmp / "bundle.json").write_text(json.dumps(project_bundle(self.baseline)), encoding="utf-8")
        (self.tmp / "settings.json").write_text(json.dumps(SETTINGS), encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = cli.run(["--project", str(self.tmp / "bundle.json"), "--settings", str(self.tmp / "settings.json"),
                            "--repo", str(self.tmp / "source"), "--out", str(self.tmp / "cli-out"), "--parent", str(d),
                            "--accept-unaccounted"])
        self.assertEqual(code, 2, err.getvalue())
        self.assertRegex(err.getvalue(), r"^aisef run: refused: ")
        for needle in THE_REFUSAL:
            self.assertIn(needle, err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_the_budget_never_computes_a_remaining_from_the_known_part(self):
        """The gate refuses before a Budget is built; the arithmetic itself does not stand on that. The known part of
        this lineage is far below every ceiling — `cap - known` would be a remaining — and the budget stops all work: it
        is the unread part, not a ceiling, that stops it. Without it the same figures stop nothing."""
        d = self.damaged("the sessions directory is moved away")
        account = lineage.lineage_account(d, self.tmp / "next")
        limits = {"provider_requests": 1000, "turns": 1000, "input_tokens": 10 ** 9, "output_tokens": 10 ** 9}
        base = {k: 0 for k in SPEND}
        with_the_unread = client.Budget(limits, base, self.tmp / "no-sessions", lambda: 0, account)
        for stop in (with_the_unread.reached(), with_the_unread.exceeded()):
            self.assertTrue(stop.startswith("unaccounted:") and "RUN.json records" in stop, stop)
            self.assertIn("cannot be read, or is gone", stop)       # evidence that is gone is not said to be unreadable
        known_only = {**{k: account[k] for k in SPEND}, "unaccounted": [], "unread": []}
        self.assertIsNone(client.Budget(limits, base, self.tmp / "no-sessions", lambda: 0, known_only).reached())

    # ---------------------------------------------------------------------------------------------------- the reports

    def test_bundle_continue_reports_the_known_part_apart_from_the_unknown_and_sends_the_operator_to_restore(self):
        for name, (_, left) in SHAPES.items():
            with self.subTest(name):
                d = self.damaged(name)
                _, report = bundle_cli.continue_from(self.doc, d)
                self.assertIsNone(report["spend"]["total"])
                self.assertEqual(report["spend"]["known"], left)
                self.assertEqual([r["exact"] for r in report["spend_by_run"]], [False])
                self.assertTrue(any("RUN.json records" in u for u in report["unread"]), report["unread"])
                self.assertIn("no flag accepts it", report["run_parent_refused"])
                self.assertIn("is gone", report["run_parent_refused"])
                self.assertIn("faithful copy", report["run_parent_refused"])
                self.assertIn(str(d), report["run_parent_refused"])
                self.assertFalse(report["next"].startswith("aisef run "), report["next"])
                self.assertIn("unread", report["next"])

    def test_a_continuation_whose_ancestor_lost_its_sessions_is_refuted_and_the_next_run_is_refused(self):
        self.assertEqual(self.continue_run()["delivery_verdict"], "PASS")
        second = self.tmp / "second"
        self.assertEqual(verify(self.project2, second)["verdict"], "VERIFIED")
        moved(self.first / "sessions")
        both = lineage.lineage_account(second)
        self.assertIsNone(both["total"])
        by_run = {pathlib.Path(r["run"]).name: r for r in both["runs"]}
        self.assertIs(by_run["second"]["exact"], True)          # the readable part is exact, attributed
        self.assertIs(by_run["first"]["exact"], False)          # the run that lost its evidence is not
        self.assertEqual(lineage.unread_runs(both), str(self.first))
        v = verify(self.project2, second)
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertTrue(any("lineage's evidence cannot be read now" in p and "is gone" in p and "RUN.json records" in p
                            for p in v["problems"]), v["problems"])
        for flags in ({}, {"accept_unaccounted": True}):
            with self.subTest(flags=flags), self.assertRaises(R.RunRefused) as c:
                self.n += 1
                R.execute(self.project2, self.settings, second / "repo", self.tmp / f"third{self.n}", transport=provider(),
                          client_exe=str(self.client), cals=calibrations(), predecessor=second, **flags)
            for needle in THE_REFUSAL:
                self.assertIn(needle, str(c.exception))
            self.assertIn(str(self.first), str(c.exception))


class HandGone(P.Hand):
    """Run directories made by hand: each witness, alone, and what it does not say."""

    def record(self, run: pathlib.Path, spent=None, inherited=None, budget="account") -> None:
        rec = json.loads((run / "RUN.json").read_text(encoding="utf-8"))
        rec["budget"] = (None if budget is None else budget if budget != "account" else
                         {"spent": {**spent, "unaccounted": []}, **({"inherited": inherited} if inherited is not None else {})})
        (run / "RUN.json").write_text(json.dumps(rec), encoding="utf-8")

    def journaled(self, name: str, *rows, streams: tuple = ()) -> pathlib.Path:
        """A run killed before its record: a journal of requests — each row `answered`, `failed` (a measured failure that
        needs no session), `in flight` or `closed` (a closer's result: the run ended without it), optionally
        `(row, "REVIEW")` — and the session streams named (`S1.developer.1`)."""
        run = self.root / name
        (run / lineage.JOURNAL).parent.mkdir(parents=True)
        w = format3.JournalWriter3(run / lineage.JOURNAL, clock=lambda: 0.0)
        try:
            w.append(T.RUN_BEGIN, {"journal_format": format3.FORMAT, "run_id": "run"})
            for row in rows:
                kind, owner = row if isinstance(row, tuple) else (row, "DEVELOPER")
                e = w.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ("C-1",), "budget_owner": owner})
                if kind == "answered":
                    w.append(T.PROVIDER_RESULT, {"story_id": "S1", "outcome": "COMPLETED", "synthetic": False, "detail": "answered"},
                             source_seqs=(e.seq,))
                elif kind == "failed":      # a measured failure (not a closer's): the session may never have started
                    w.append(T.PROVIDER_RESULT, {"story_id": "S1", "outcome": "FAILED", "synthetic": False,
                                                 "detail": "reviewer cannot run: a budget was reached"}, source_seqs=(e.seq,))
                elif kind == "closed":
                    w.append(T.PROVIDER_RESULT, {"story_id": "S1", "outcome": "OUTCOME_UNKNOWN", "synthetic": True,
                                                 "detail": "the run ended without its result (repair)"}, source_seqs=(e.seq,))
        finally:
            w.close()
        if streams:
            (run / "sessions").mkdir()
            for s in streams:
                (run / "sessions" / f"{s}.jsonl").write_text(P.STEP, encoding="utf-8")
        return run

    # ---------------------------------------------------------------------------------------------------- the record

    def test_what_the_record_vouches_for_is_not_gone_whatever_the_journal(self):
        """Three requests answered and no session ever started for them (a budget reached, a reviewer that could not run):
        the record says so — its counters are the evidence's — and the run is as exact as it was."""
        run = self.run_dir("run", 3, streams=False)
        self.record(run, dict(provider_requests=3, turns=0, input_tokens=0, output_tokens=0))
        got = lineage.account_of(run)
        self.assertEqual((got["unaccounted"], got["unread"], got["exact"], got["provider_requests"]), ([], [], True, 3))

    def test_a_counter_the_record_holds_and_the_evidence_does_not_is_gone_and_the_known_part_is_kept(self):
        run = self.run_dir("run", 3, streams=False)
        self.record(run, dict(provider_requests=3, turns=1, input_tokens=7, output_tokens=3))
        got = lineage.account_of(run)
        self.assertEqual(len(got["unread"]), 1, got["unread"])
        for needle in ("turns 1 (the evidence shows 0)", "input_tokens 7 (the evidence shows 0)",
                       "output_tokens 3 (the evidence shows 0)"):
            self.assertIn(needle, got["unread"][0])
        self.assertNotIn("provider_requests 3", got["unread"][0])       # that counter is the evidence's
        self.assertEqual({k: got[k] for k in SPEND}, {"provider_requests": 3, "turns": 0, "input_tokens": 0, "output_tokens": 0})
        self.assertIs(got["exact"], False)

    def test_more_evidence_than_the_record_names_is_not_gone(self):
        run = self.run_dir("run", 2)                                  # two streams: 2 turns, 14 input, 6 output tokens
        self.record(run, dict(provider_requests=2, turns=0, input_tokens=0, output_tokens=0))
        got = lineage.account_of(run)
        self.assertEqual((got["unread"], got["unaccounted"], got["exact"], got["turns"]), ([], [], True, 2))

    def test_a_stream_that_held_no_step_is_counted_by_the_record_too(self):
        """A session stream that finished no step has no counter to miss: the record's `sessions_started` is the witness."""
        run = self.run_dir("run", 2)                                  # two streams: 2 turns, 14 input, 6 output tokens
        spent = dict(provider_requests=2, turns=2, input_tokens=14, output_tokens=6)
        for started, unread in ((2, False), (3, True), ("two", False)):
            with self.subTest(sessions_started=started):
                self.record(run, {**spent, "sessions_started": started})
                got = lineage.account_of(run)
                self.assertEqual(bool(got["unread"]), unread, got["unread"])
                if unread:
                    self.assertIn("sessions_started 3 (the evidence shows 2)", got["unread"][0])

    def test_the_inherited_share_is_not_the_runs_own_evidence(self):
        own = dict(provider_requests=2, turns=2, input_tokens=14, output_tokens=6)       # what run_dir("run", 2) leaves
        share = dict(provider_requests=4, turns=1, input_tokens=50, output_tokens=5)
        total = {k: own[k] + share[k] for k in SPEND}
        run = self.run_dir("run", 2)
        self.record(run, total, inherited=share)
        got = lineage.account_of(run)
        self.assertEqual((got["unread"], got["exact"], {k: got[k] for k in SPEND}), ([], True, own))
        self.record(run, total)         # the same spend with no share named: it is all this run's, and its evidence is short
        self.assertEqual(len(lineage.account_of(run)["unread"]), 1)
        self.record(run, {**total, "turns": total["turns"] + 1}, inherited=share)         # the share named, one turn more
        self.assertIn("turns 3 (the evidence shows 2)", lineage.account_of(run)["unread"][0])     # its own: 4 less the share

    def test_a_budget_that_is_not_an_account_cannot_be_compared_and_is_unknown(self):
        ok = dict(provider_requests=3, turns=3, input_tokens=21, output_tokens=9)
        bad = {"spent is a word": {"spent": "many"}, "spent is a list": {"spent": [3, 3, 21, 9]},
               "a count is negative": {"spent": {**ok, "turns": -1}}, "a count is a bool": {"spent": {**ok, "turns": True}},
               "a count is a float": {"spent": {**ok, "turns": 3.0}},
               "a counter is missing": {"spent": {k: v for k, v in ok.items() if k != "turns"}},
               "no spent": {"inherited": {k: 0 for k in SPEND}},
               "inherited is a number": {"spent": ok, "inherited": 5},
               "inherited is larger than spent": {"spent": ok, "inherited": {**ok, "turns": 9}},
               "the budget is a word": "a budget"}
        for name, budget in bad.items():
            with self.subTest(name):
                self.fresh(name)
                run = self.run_dir("run", 3)
                self.record(run, budget=budget)
                got = lineage.account_of(run)
                self.assertEqual(len(got["unread"]), 1, got["unread"])
                self.assertIn("is not an account of what the run spent", got["unread"][0])
                self.assertIs(got["exact"], False)
        self.fresh("an account")
        run = self.run_dir("run", 3)
        self.record(run, ok)
        self.assertEqual(lineage.account_of(run)["unread"], [])

    def test_a_run_that_built_no_budget_and_a_record_that_cannot_be_read_name_no_spend(self):
        """`budget: null` is a run that failed before its budget (nothing to compare); a record that is cut, a link to nothing,
        or has no `budget` at all names none either: the journal's answered requests decide, as for a run with no record."""
        for name in ("null", "cut", "absent", "link"):
            for streams in (True, False):
                with self.subTest(name, streams=streams):
                    self.fresh(f"{name} {streams}")
                    run = self.run_dir("run", 2, streams=streams)
                    if name == "null":
                        self.record(run, budget=None)
                    elif name == "cut":
                        (run / "RUN.json").write_text('{"budget": {"sp', encoding="utf-8")
                    elif name == "link":
                        (run / "RUN.json").write_text("{}", encoding="utf-8")
                        moved(run / "RUN.json")
                        self.link(run / "RUN.json", self.root / "nowhere.json")
                    got = lineage.account_of(run)
                    self.assertEqual(bool(got["unread"]), not streams, got["unread"])

    def test_nothing_else_unread_is_said_twice(self):
        run = self.run_dir("run", 3, streams=False)
        self.record(run, dict(provider_requests=3, turns=1, input_tokens=7, output_tokens=3))
        (run / lineage.JOURNAL).write_bytes(P.NOT_TEXT)
        got = lineage.account_of(run)
        self.assertEqual(len(got["unread"]), 1, got["unread"])
        self.assertIn("cannot be read", got["unread"][0])
    # ------------------------------------------------------------------------------- a run that built no Budget (round 2)

    def ledger(self, run: pathlib.Path, requests: int) -> None:
        """The preflight's ledger as the preflight writes it: each request sent and answered (6 input, 1 output tokens)."""
        (run / "preflight").mkdir()
        rows = [row for n in range(1, requests + 1) for row in ({"n": n, "event": "sent", "kind": "probe"},
                                                                  {"n": n, "event": "done", "http": 200, "input_tokens": 6,
                                                                   "output_tokens": 1})]
        (run / "preflight" / "LEDGER.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def preflight_record(self, run: pathlib.Path, accounting) -> None:
        rec = json.loads((run / "RUN.json").read_text(encoding="utf-8"))
        rec["budget"], rec["preflight"] = None, {"accounting": accounting}
        (run / "RUN.json").write_text(json.dumps(rec), encoding="utf-8")

    def test_a_run_that_built_no_budget_is_compared_with_the_preflights_account_its_record_holds(self):
        """The run failed after its preflight and before its Budget: RUN.json has `budget: null`, and the preflight's
        `accounting` is the only spend it names — the same kind of witness as `budget.spent`."""
        said = dict(provider_requests=3, turns=0, input_tokens=18, output_tokens=3, unaccounted=[])
        run = self.run_dir("run", 0)
        self.ledger(run, 3)
        self.preflight_record(run, said)
        got = lineage.account_of(run)
        self.assertEqual((got["unread"], got["unaccounted"], got["exact"], got["provider_requests"]), ([], [], True, 3))
        for name, damage in (("the ledger directory is gone", lambda: os.rename(run / "preflight", run / "preflight.moved")),
                             ("the ledger is cut to its first rows", lambda: (run / "preflight" / "LEDGER.jsonl").write_text(
                                 "".join((run / "preflight.moved" / "LEDGER.jsonl").read_text(encoding="utf-8")
                                         .splitlines(keepends=True)[:2]), encoding="utf-8"))):
            with self.subTest(name):
                if "cut" in name:
                    (run / "preflight").mkdir()
                damage()
                got = lineage.account_of(run)
                self.assertEqual(len(got["unread"]), 1, got["unread"])
                self.assertIn("RUN.json records that the run spent provider_requests 3 (the evidence shows", got["unread"][0])
                self.assertIs(got["exact"], False)
                self.assertIsNone(lineage.lineage_account(run)["total"])

    def test_a_preflight_account_that_is_not_four_counts_names_no_spend(self):
        """Nothing to compare is nothing to exceed: the journal's answered requests decide, as for a run with no record."""
        for name, accounting in (("a word", "three"), ("a count is missing", dict(provider_requests=3, turns=0, input_tokens=18)),
                                 ("a count is negative", dict(provider_requests=-3, turns=0, input_tokens=18, output_tokens=3)),
                                 ("a count is a bool", dict(provider_requests=True, turns=0, input_tokens=18, output_tokens=3)),
                                 ("none", None)):
            with self.subTest(name):
                self.fresh(name)
                run = self.run_dir("run", 0)
                self.preflight_record(run, accounting)
                got = lineage.account_of(run)
                self.assertEqual((got["unread"], got["exact"]), ([], True))


    # ---------------------------------------------------------------------------------------------------- no record

    def test_a_run_with_no_record_needs_a_stream_for_every_answered_request(self):
        """A run killed before RUN.json: there is nothing to exceed, and the journal's answered requests are all there is."""
        whole = self.journaled("whole", "answered", "answered", streams=("S1.developer.1", "S1.developer.2"))
        got = lineage.account_of(whole)
        self.assertEqual((got["unread"], got["unaccounted"], got["exact"], got["provider_requests"]), ([], [], True, 2))
        for name, streams, say in (("one stream gone", ("S1.developer.1",), "S1 developer: 2 answered, 1 stream)"),
                                   ("no sessions directory", (), "S1 developer: 2 answered, 0 streams)")):
            with self.subTest(name):
                run = self.journaled(name, "answered", "answered", streams=streams)
                got = lineage.account_of(run)
                self.assertEqual(len(got["unread"]), 1, got["unread"])
                self.assertIn(say, got["unread"][0])
                self.assertIn("no record names what the run spent", got["unread"][0])
                self.assertIs(got["exact"], False)
                self.assertEqual(got["provider_requests"], 2)           # what the journal says is kept
                self.assertIsNone(lineage.lineage_account(run)["total"])

    def test_the_reviewers_streams_are_told_from_the_developers(self):
        run = self.journaled("mixed", "answered", ("answered", "REVIEW"), streams=("S1.developer.1",))
        got = lineage.account_of(run)
        self.assertEqual(len(got["unread"]), 1, got["unread"])
        self.assertIn("S1 reviewer: 1 answered, 0 streams", got["unread"][0])
        self.assertNotIn("developer", got["unread"][0])
        whole = self.journaled("whole", "answered", ("answered", "REVIEW"), streams=("S1.developer.1", "S1.reviewer.1"))
        self.assertEqual(lineage.account_of(whole)["unread"], [])

    def test_the_cause_without_a_record_says_where_a_session_never_started_there_is_nothing_to_restore(self):
        """The journal of a stream that is gone and that of a session that never started are the same one: the rule takes
        the unknown, and the operator is told, not sent to restore what may never have existed."""
        run = self.journaled("run", "answered", ("failed", "REVIEW"), streams=("S1.developer.1",))
        got = lineage.account_of(run)
        self.assertEqual(len(got["unread"]), 1, got["unread"])
        self.assertIn("S1 reviewer: 1 answered, 0 streams", got["unread"][0])
        for needle in ("a session that never started", "a budget reached", "only RUN.json would tell the two apart",
                       "no stream to restore"):
            self.assertIn(needle, got["unread"][0])

    def test_answered_requests_are_paired_with_streams_by_count_not_by_the_number_in_a_stream_name(self):
        """A stream's name carries the kernel's attempt number, which a request does not follow: the reviewer is not
        reached on an attempt whose proof failed, so a run's first review request may stand for `S1.reviewer.2`."""
        run = self.journaled("run", "answered", ("answered", "REVIEW"), streams=("S1.developer.1", "S1.reviewer.2"))
        got = lineage.account_of(run)
        self.assertEqual((got["unread"], got["unaccounted"], got["exact"]), ([], [], True))

    def test_a_request_in_flight_and_one_a_closer_closed_are_not_answered_requests(self):
        """The state tests/v2/test_v21_defects_lineage2.py pins (one request in flight, no stream, no record: not unknown,
        not unread), and a request the run's repair closed with a synthetic result — no answer was measured."""
        for name, rows in (("in flight", ("in flight",)), ("closed by a closer", ("closed",)),
                           ("answered, closed and in flight", ("answered", "closed", "in flight"))):
            with self.subTest(name):
                run = self.journaled(name, *rows, streams=("S1.developer.1",) if len(rows) == 3 else ())
                got = lineage.account_of(run)
                self.assertEqual((got["unread"], got["unaccounted"]), ([], []), name)

    def test_a_run_nothing_names_and_a_run_with_no_requests_stay_a_run_that_spent_nothing(self):
        self.assertEqual(lineage.account_of(self.root / "gone")["unread"], [])
        run = self.journaled("no requests")
        self.assertEqual((lineage.account_of(run)["unread"], lineage.account_of(run)["exact"]), ([], True))


@P.POSIX_CLIENT
class UnattestedRoute(ProductBase):
    """A real run that failed after its preflight and before its Budget (the route is not attested): RUN.json has
    `budget: null`, and 3 preflight requests (18 input and 2 output tokens) are all it spent."""

    def setUp(self) -> None:
        super().setUp()
        with self.assertRaises(preflight.IdentityStop):
            self.execute("first", transport=provider(served="model-2"))
        self.first = self.tmp / "first"
        self.n = 0

    def copy(self, name: str) -> pathlib.Path:
        dst = self.tmp / name
        shutil.copytree(self.first, dst, symlinks=True)
        return dst

    def test_intact_it_is_exact_and_gone_it_is_unknown_with_what_is_left_attributed(self):
        rec = json.loads((self.first / "RUN.json").read_text(encoding="utf-8"))
        self.assertIsNone(rec["budget"])
        left = {"provider_requests": 3, "turns": 0, "input_tokens": 18, "output_tokens": 2}
        acct = lineage.account_of(self.first)
        self.assertEqual(({k: acct[k] for k in SPEND}, acct["exact"], acct["unread"]), (left, True, []))
        whole = lineage.usage_lineage(self.first, self.tmp / "next", OWN, P.PRICES)
        self.assertEqual(whole["cost"]["status"], "known")
        self.assertAlmostEqual(whole["cost"]["value"], 2.2e-05, places=9)
        for name, damage, kept in (("the preflight directory is moved away", lambda d: moved(d / "preflight"),
                                    {k: 0 for k in SPEND}),
                                   ("the ledger is cut to its first rows", ledger_two_rows,
                                    {"provider_requests": 1, "turns": 0, "input_tokens": 0, "output_tokens": 0})):
            with self.subTest(name):
                d = self.copy("cut" if "cut" in name else "away")
                damage(d)
                acct = lineage.account_of(d)
                self.assertIs(acct["exact"], False)
                self.assertEqual(len(acct["unread"]), 1, acct["unread"])
                self.assertIn("RUN.json records that the run spent provider_requests 3", acct["unread"][0])
                self.assertEqual({k: acct[k] for k in SPEND}, kept)
                got = lineage.lineage_account(d, self.tmp / "next")
                self.assertIsNone(got["total"])
                self.assertEqual(lineage.unread_runs(got), str(d))
                whole = lineage.usage_lineage(d, self.tmp / "next", OWN, P.PRICES)
                self.assertIsNone(whole["cost"]["value"])
                self.assertTrue(whole["cost"]["status"].startswith("unknown"), whole["cost"])
                self.assertTrue(whole["tokens_status"].startswith("lower bound"), whole["tokens_status"])

    def test_no_flag_opens_a_session_over_it_and_nothing_is_written_into_the_run(self):
        d = self.copy("away")
        moved(d / "preflight")
        before = P.snapshot(d)
        for flags in ({}, {"accept_unaccounted": True}):
            with self.subTest(flags=flags), self.assertRaises(R.RunRefused) as c:
                self.n += 1
                transport = provider()
                try:
                    R.execute(self.project, self.settings, self.tmp / "source", self.tmp / f"asked{self.n}", transport=transport,
                              client_exe=str(self.client), cals=calibrations(), predecessor=d, **flags)
                finally:
                    self.assertEqual(transport.calls, [], "no provider request was made")
            for needle in THE_REFUSAL:
                self.assertIn(needle, str(c.exception))
            self.assertIn(str(d), str(c.exception))
        after = P.snapshot(d)
        self.assertEqual({k: after[k] for k in before}, before, "history was not rewritten, a byte")


@P.POSIX_CLIENT
class BudgetStopped(ProductBase):
    """A real run that stopped at its turn ceiling: its journal holds answered requests no session ever started for."""

    def setUp(self) -> None:
        super().setUp()
        self.settings = settings.load({**SETTINGS, "budget": {"provider_requests": 20, "turns": 1, "input_tokens": 100000,
                                                               "output_tokens": 10000}})
        self.rec = self.execute("first")
        self.first = self.tmp / "first"

    def test_the_run_that_wrote_its_record_is_exact_and_the_same_run_killed_before_it_is_the_unknown_the_rule_takes(self):
        """The record vouches for the figures (6 requests, 1 turn: three requests started no session); without it the
        journal alone cannot tell a stream that is gone from a session that never started. Pinned as the owner wrote the
        rule; whether only a COMPLETED request owes a stream is an open owner decision."""
        spent = {k: self.rec["budget"]["spent"][k] for k in SPEND}
        self.assertEqual(spent, {"provider_requests": 6, "turns": 1, "input_tokens": 148, "output_tokens": 12})
        acct = lineage.account_of(self.first)
        self.assertEqual(({k: acct[k] for k in SPEND}, acct["exact"], acct["unread"]), (spent, True, []))
        killed = self.tmp / "killed"
        shutil.copytree(self.first, killed, symlinks=True)
        moved(killed / "RUN.json")
        got = lineage.account_of(killed)
        self.assertEqual({k: got[k] for k in SPEND}, spent)         # nothing was lost: the figures are the same
        self.assertIs(got["exact"], False)
        self.assertEqual(len(got["unread"]), 1, got["unread"])
        self.assertIn("a session that never started", got["unread"][0])
        self.assertIsNone(lineage.lineage_account(killed)["total"])


class UnreadRunsNamesEachUnreadRunApart(unittest.TestCase):
    """When two runs of a lineage are both unread, the operator restore message
    (run.py / bundle_cli.py / verify.py embed unread_runs in it) must name each run
    directory apart, separated by ', ', or the paths run together into one that names
    no directory and the operator cannot restore either (owner: lineage/operator report)."""

    def test_two_unread_runs_are_named_apart_so_the_operator_can_restore_each(self):
        account = {"runs": [
            {"run": "/lin/run1", "unread": ["run1: RUN.json records spend whose evidence is gone"]},
            {"run": "/lin/run2", "unread": ["run2: sessions/ cannot be read (PermissionError)"]},
        ]}
        got = lineage.unread_runs(account)
        self.assertEqual(got, "/lin/run1, /lin/run2")              # comma-space separated, in order
        self.assertEqual(got.split(", "), ["/lin/run1", "/lin/run2"])  # each a directory the operator can restore

    def test_one_unread_run_is_named_alone(self):
        account = {"runs": [
            {"run": "/lin/run1", "unread": ["run1: gone"]},
            {"run": "/lin/run2", "unread": []},
        ]}
        self.assertEqual(lineage.unread_runs(account), "/lin/run1")

    def test_no_unread_run_sends_the_operator_to_the_list_below(self):
        self.assertEqual(lineage.unread_runs({"runs": [{"run": "/lin/run1", "unread": []}]}),
                         "the runs named below")


class TheUnreadRefusalListsEachUnreadItemSeparately(unittest.TestCase):
    """`aisef run --parent` over a lineage whose evidence cannot be read refuses and names every unread item so the
    operator can restore each; execute joins them with '; ' (aisef2/app/run.py::execute, line 542). A lineage's `unread`
    is the flat list of every run's unread evidence (app/lineage.py::lineage_account), so two is ordinary -- a run whose
    preflight ledger does not read and another whose session stream does not read. Drop the separator and the two
    descriptions fuse into one run-on the operator cannot act on; this pins that they stay separate."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.pred = self.tmp / "pred"
        self.pred.mkdir()
        (self.pred / "RUN.json").write_text("{}", encoding="utf-8")   # a run record there: the claim stage is reached
        self.project = bundle.load(project_bundle("0" * 40))
        self.settings = settings.load(SETTINGS)

    def test_two_unread_items_are_not_fused_in_the_refusal(self):
        a = "run-a: the preflight's ledger does not read (JSONDecodeError): what the preflight spent is unknown"
        b = "run-b: a session's event stream does not read (ValueError): what the sessions spent is unknown"
        account = {**{k: 0 for k in SPEND}, "unaccounted": [], "unread": [a, b], "total": None, "runs": []}
        with mock.patch.object(lineage, "claim", return_value=b"a-claim"), \
             mock.patch.object(lineage, "lineage_account", return_value=account), \
             self.assertRaises(R.RunRefused) as c:
            R.execute(self.project, self.settings, self.tmp / "source", self.tmp / "out", predecessor=self.pred)
        text = str(c.exception)
        self.assertIn(a, text)                   # both unread items are named
        self.assertIn(b, text)
        self.assertIn(f"{a}; {b}", text)         # and separated, not fused into one run-on the operator cannot read


if __name__ == "__main__":
    unittest.main()
