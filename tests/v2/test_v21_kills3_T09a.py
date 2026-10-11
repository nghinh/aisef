"""V2.1 mutation survivors, batch T09a: aisef2/app/lineage.py `_gone`, `claim` and `account_of`.

What a lineage decision rests on, held at the function that takes it, on temp directories — no client and no provider
request (the continuation tests call `R.execute`, which is refused at the claim, before anything is sent):

* `_gone`: a claimant is provably gone only when its start time is read now and is not the recorded one (or its pid is
  absent); alive when it is the same; **undecidable** when its identity was never recorded or cannot be read now;
* `claim`: the claim document is the persisted record of the decision (the run, when, who); and only the claim's own
  sha256 lets an operator supersede a claimant that is alive, elsewhere or not decidable;
* `account_of`: a run's spend re-derived from its evidence (preflight ledger, journal, session streams) against figures
  computed here from the fixture, and what is unknown *listed*, never counted as 0: an unreadable preflight ledger, a
  preflight request sent and never answered, a provider request in flight (its session started, no result).

The run directories are built the way a run leaves them: the preflight's ledger by the preflight itself, the journal by
`JournalWriter3`, session streams of one finished step. Process identity is read through `lineage.process_started`:
a table stands in for it where a real process cannot be made alive/gone/unreadable on demand, and one posix test reads
the real process table."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import socket
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, lineage, preflight, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from aisef2.journal.event import EventType as T  # noqa: E402
from tests.v2.test_app_run import ROUTE, SETTINGS, client_config, make_repo, project_bundle, provider  # noqa: E402
from tests.v2.test_v21_continue_usage import PRICES  # noqa: E402

HOST = socket.gethostname()
STARTED = "Thu Oct  1 10:00:00 2026"
LATER = "Fri Oct  2 09:00:00 2026"
#: two other start times, one that sorts before STARTED as text (LATER does too) and one that sorts after it: a start
#: time is an identity, never an ordering, so a pid that now has any other one is another process
REUSED = (LATER, "Wed Oct  7 10:00:00 2026")
DEV, REV = "DEVELOPER", "REVIEW"

#: one finished step of a session: 120 + 10 cache-read input, 7 + 3 reasoning output (what the Budget counts)
STEP = {"type": "step_finish", "part": {"tokens": {"input": 120, "output": 7, "reasoning": 3,
                                                   "cache": {"read": 10, "write": 0}}}}
SESSION = {"turns": 1, "input_tokens": 130, "output_tokens": 10}
#: the preflight's own: a listing and two chat probes (the fake provider reports 9 in / 1 out per probe)
PREFLIGHT = {"provider_requests": 3, "input_tokens": 18, "output_tokens": 2}


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_run(root: pathlib.Path, *, requests=(), streams=(), ledger=True, record=False, started=False) -> list[int]:
    """A run directory as a run's evidence leaves it; the journal seq of each request, in order. `requests`:
    (story, owner, answered); `streams`: session stream names (each one finished step)."""
    root.mkdir(parents=True)
    journal = root / lineage.JOURNAL
    journal.parent.mkdir(parents=True)
    seqs = []
    w = format3.JournalWriter3(journal, clock=lambda: 0.0)
    try:
        w.append(T.RUN_BEGIN, {"journal_format": format3.FORMAT, "run_id": root.name})
        for story, owner, answered in requests:
            e = w.append(T.PROVIDER_REQUEST, {"story_id": story, "criteria": ("C-1",), "budget_owner": owner})
            seqs.append(e.seq)
            if answered:
                w.append(T.PROVIDER_RESULT, {"story_id": story, "outcome": "COMPLETED", "synthetic": False,
                                             "detail": "answered"}, source_seqs=(e.seq,))
    finally:
        w.close()
    if streams:
        (root / "sessions").mkdir()
        for name in streams:
            (root / "sessions" / name).write_text(json.dumps(STEP) + "\n", encoding="utf-8")
    if ledger:
        preflight.run(ROUTE, 2, provider(), root / "preflight", "model-1", "fake")
    if record:
        (root / "RUN.json").write_text("{}\n", encoding="utf-8")
    if started:
        (root / lineage.STARTED).write_text("{}\n", encoding="utf-8")
    return seqs


def words(entry: str) -> list[str]:
    """An unaccounted entry as separate tokens: `run2: provider request seq 7 (S2, REVIEW) has ...` -> run2, ..., 7, S2."""
    return entry.translate({ord(c): " " for c in "(),:"}).split()


class Table:
    """The process table, as `lineage.process_started` answers it: a start time, None (no such process), or "unknown"."""

    def __init__(self) -> None:
        self.rows: dict[int, str] = {}

    def __call__(self, pid: int):
        return self.rows.get(pid)


class WithTable(unittest.TestCase):
    def setUp(self) -> None:
        self.table = Table()
        patch = mock.patch.object(lineage, "process_started", self.table)
        patch.start()
        self.addCleanup(patch.stop)
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()


def claimant(pid: int = 4242, started=STARTED, host: str = HOST) -> dict:
    return {"host": host, "pid": pid, "started": started}


class GoneVerdict(WithTable):
    """`_gone` answers from the claimant's recorded identity against the process table now.
    Pins aisef2/app/lineage.py::_gone [2, 6, 11, 13, 14, 16, 19]."""

    def test_the_same_process_is_alive_another_start_time_is_a_reused_pid_no_process_is_gone(self):
        who = claimant()
        self.table.rows[4242] = STARTED
        self.assertIs(lineage._gone(who), False)       # the process the claim names: alive
        for reused in REUSED:
            with self.subTest(reused=reused):
                self.table.rows[4242] = reused
                self.assertIs(lineage._gone(who), True)    # the pid was reused: provably gone
        del self.table.rows[4242]
        self.assertIs(lineage._gone(who), True)        # no such process

    def test_a_start_time_that_cannot_be_read_now_proves_nothing(self):
        self.table.rows[4242] = "unknown"              # ps failed at the moment of the decision
        self.assertIsNone(lineage._gone(claimant()))

    def test_a_claimant_whose_identity_was_never_recorded_is_never_gone(self):
        for recorded in (None, "unknown"):             # ps printed nothing / could not be read when it claimed
            for now in (STARTED, LATER, None):         # whatever the table says: a live pid, a reused one, no process
                with self.subTest(recorded=recorded, now=now):
                    self.table.rows.clear()
                    if now is not None:
                        self.table.rows[4242] = now
                    self.assertIsNone(lineage._gone(claimant(started=recorded)))


@unittest.skipUnless(os.name == "posix", "reads the process table with ps")
class GoneOfARealProcess(unittest.TestCase):
    """Pins aisef2/app/lineage.py::_gone [2, 6, 11] against the real process table."""

    def test_this_process_is_alive_and_its_pid_with_another_start_time_is_a_reused_pid(self):
        me = lineage.claimant()
        self.assertEqual((me["host"], me["pid"]), (HOST, os.getpid()))
        self.assertNotIn(me["started"], (None, "unknown"), "ps cannot read this process: the check would be vacuous")
        self.assertIs(lineage._gone(me), False)
        self.assertIs(lineage._gone({**me, "started": "Thu Jan  1 00:00:00 1970"}), True)


class ClaimDecisionOnTheClaimant(WithTable):
    """What `claim` tells the operator when the claimant is alive, or cannot be shown gone — the cause class decides
    what they may do (wait / assert by naming the claim). Pins aisef2/app/lineage.py::_gone [2, 6, 11, 13, 14, 16, 19]."""

    def setUp(self) -> None:
        super().setUp()
        self.pred = self.tmp / "pred"
        self.pred.mkdir()

    def held(self, who: dict) -> pathlib.Path:
        p = self.pred / lineage.CLAIM
        p.write_text(json.dumps({"run": str(self.tmp / "never-made"), "claimed": 1.0, "claimant": who}) + "\n",
                     encoding="utf-8")
        return p

    def refusal(self) -> str:
        with self.assertRaises(lineage.LineageRefused) as c:
            lineage.claim(self.pred, self.tmp / "next", 2.0)
        self.assertEqual([n for n, _ in lineage.claims(self.pred)], [1])      # no new generation
        return str(c.exception)

    def test_a_claimant_that_is_alive_is_refused_as_alive(self):
        self.table.rows[4242] = STARTED
        self.held(claimant())
        msg = self.refusal()
        self.assertIn("is alive", msg)
        self.assertNotIn("cannot be shown gone", msg)

    def test_a_claimant_not_provably_gone_is_refused_as_not_shown_gone(self):
        self.table.rows[4242] = STARTED
        cases = {"ps unreadable now": (claimant(), "unknown"),
                 "no start time recorded": (claimant(started=None), STARTED),
                 "recorded unknown": (claimant(started="unknown"), STARTED),
                 "no start time recorded, no such process": (claimant(started=None), None)}
        for n, (name, (who, now)) in enumerate(cases.items()):
            with self.subTest(name):
                if now is None:
                    self.table.rows.pop(4242, None)
                else:
                    self.table.rows[4242] = now
                self.pred = self.tmp / f"pred-{n}"      # a predecessor of its own per case: no claim left by the last
                self.pred.mkdir()
                self.held(who)
                msg = self.refusal()
                self.assertIn("cannot be shown gone", msg)
                self.assertNotIn("is alive", msg)

    def test_a_claimant_gone_is_superseded_by_evidence_never_by_assertion(self):
        self.table.rows[4242] = LATER                  # recorded STARTED: the pid was reused
        p = self.held(claimant())
        doc = lineage.claim(self.pred, self.tmp / "next", 2.0)
        sup = doc["supersedes"]
        self.assertEqual((sup["claim"], sup["sha256"], sup["claimant_gone"], sup["operator_asserted"]),
                         (lineage.CLAIM, sha(p), True, False))


class ClaimDocument(WithTable):
    """The claim is the persisted record of the first-come decision: which run took the continuation, when, and who.
    Pins aisef2/app/lineage.py::claim [5, 22]."""

    def setUp(self) -> None:
        super().setUp()
        self.table.rows[os.getpid()] = STARTED
        self.pred = self.tmp / "pred"
        self.pred.mkdir()

    def test_the_document_written_is_the_one_returned_and_carries_the_time_it_was_taken(self):
        child = self.tmp / "child"
        doc = lineage.claim(self.pred, child, 1234.5)
        written = json.loads((self.pred / lineage.CLAIM).read_text(encoding="utf-8"))
        for got in (doc, written):
            self.assertEqual(got.get("run"), str(child))
            self.assertEqual(got.get("claimed"), 1234.5)
            self.assertEqual(got.get("claimant"), {"host": HOST, "pid": os.getpid(), "started": STARTED})
            self.assertNotIn("supersedes", got)
        self.assertEqual(lineage.claims(self.pred), [(1, self.pred / lineage.CLAIM)])

    def test_a_later_generation_carries_its_own_time_and_names_the_claim_it_replaced(self):
        first = lineage.claim(self.pred, self.tmp / "dead", 1234.5)
        self.table.rows[os.getpid()] = LATER           # the first claimant's pid is now another process
        second = lineage.claim(self.pred, self.tmp / "next", 2000.5)
        written = json.loads((self.pred / "CONTINUED-BY.2.json").read_text(encoding="utf-8"))
        self.assertEqual((first.get("claimed"), second.get("claimed"), written.get("claimed")), (1234.5, 2000.5, 2000.5))
        self.assertEqual(written["supersedes"]["sha256"], sha(self.pred / lineage.CLAIM))


class SupersedeByNamingTheClaim(WithTable):
    """A claimant that is alive, on another host or not decidable is superseded only by the operator naming the claim's
    own sha256 (recorded as their assertion): any other value — junk, empty, another file's digest, an older
    generation's — is refused and changes nothing. Pins aisef2/app/lineage.py::claim [13]."""

    def held(self, name: str) -> tuple[pathlib.Path, pathlib.Path]:
        pred = self.tmp / f"pred-{name}"
        pred.mkdir()
        child = self.tmp / f"pending-{name}"
        who = {"elsewhere": claimant(pid=1, started="x", host="another-host"),
               "unreadable": claimant(pid=os.getpid(), started=None)}.get(name)
        if who is None:                                   # alive: this process claimed, and is still the same
            lineage.claim(pred, child, 1.0)
        else:
            (pred / lineage.CLAIM).write_text(json.dumps({"run": str(child), "claimed": 1.0, "claimant": who}) + "\n",
                                              encoding="utf-8")
        return pred, child

    def refused_naming(self, pred: pathlib.Path, wrong) -> None:
        before = {p.name: p.read_bytes() for p in pred.iterdir()}
        with self.assertRaises(lineage.LineageRefused) as c:
            lineage.claim(pred, self.tmp / "next", 2.0, wrong)
        self.assertIn("not superseded without evidence", str(c.exception))
        self.assertEqual({p.name: p.read_bytes() for p in pred.iterdir()}, before)     # no generation, nothing changed

    def test_only_the_claims_own_sha256_supersedes(self):
        self.table.rows[os.getpid()] = STARTED
        gone = {"alive": False, "elsewhere": None, "unreadable": None}
        for name, claimant_gone in gone.items():
            with self.subTest(name):
                pred, child = self.held(name)
                first = pred / lineage.CLAIM
                for wrong in (None, "", "yes", hashlib.sha256(b"another claim").hexdigest()):
                    self.refused_naming(pred, wrong)
                named = sha(first)
                doc = lineage.claim(pred, self.tmp / f"second-{name}", 2.0, named)
                sup = doc["supersedes"]
                self.assertEqual((sup["sha256"], sup["operator_asserted"], sup["child"], sup["child_state"]),
                                 (named, True, str(child), lineage.UNBEGUN))
                self.assertIs(sup["claimant_gone"], claimant_gone)
                self.assertEqual([n for n, _ in lineage.claims(pred)], [1, 2])
                if name == "alive":      # the newest claim is the one to name: the one it replaced is another file's
                    self.refused_naming(pred, named)
                    newest = sha(pred / "CONTINUED-BY.2.json")
                    self.assertNotEqual(newest, named)
                    third = lineage.claim(pred, self.tmp / "third-alive", 3.0, newest)
                    self.assertEqual((third["supersedes"]["sha256"], third["supersedes"]["operator_asserted"]),
                                     (newest, True))


class Accounting(WithTable):
    """`account_of` of a finished and of a killed run, against the figures of the fixture: the preflight's three
    requests and tokens, the journal's requests, the four sessions' turns and tokens.
    Pins aisef2/app/lineage.py::account_of [38, 40, 48]."""

    STORIES = [("S1", DEV, True), ("S1", REV, True), ("S2", DEV, True), ("S2", REV, True)]
    STREAMS = ["S1.developer.1.jsonl", "S1.reviewer.1.jsonl", "S2.developer.1.jsonl", "S2.reviewer.1.jsonl"]
    #: the preflight's own + 4 journaled requests + 4 sessions: computed from the fixture, not from the code under test
    EXPECTED = {"provider_requests": PREFLIGHT["provider_requests"] + 4, "turns": 4 * SESSION["turns"],
                "input_tokens": PREFLIGHT["input_tokens"] + 4 * SESSION["input_tokens"],
                "output_tokens": PREFLIGHT["output_tokens"] + 4 * SESSION["output_tokens"]}

    @staticmethod
    def figures(acct: dict) -> dict:
        return {k: acct[k] for k in lineage.SPEND}

    def test_the_account_counts_the_preflight_the_journal_and_every_session(self):
        run = self.tmp / "first"
        make_run(run, requests=self.STORIES, streams=self.STREAMS)       # a run killed before its record: not recorded
        acct = lineage.account_of(run)
        self.assertEqual(self.figures(acct), self.EXPECTED)
        self.assertIs(acct["recorded"], False)
        (run / "RUN.json").write_text("{}\n", encoding="utf-8")           # and the record written: the same spend
        acct = lineage.account_of(run)
        self.assertEqual(self.figures(acct), self.EXPECTED)
        self.assertEqual((acct["unaccounted"], acct["recorded"], acct["run"]), ([], True, str(run)))

    def test_a_finished_predecessors_cost_is_known_and_a_killed_ones_is_not(self):
        run, child = self.tmp / "first", self.tmp / "second"
        make_run(run, requests=self.STORIES, streams=self.STREAMS)       # killed before its record
        own = {"tokens": {}, "cost": {"value": 0.0}}
        got = lineage.usage_lineage(run, child, own, PRICES)
        self.assertIs(got["runs"][0]["recorded"], False)
        self.assertTrue(got["runs"][0]["cost"]["status"].startswith("partial"), got["runs"][0]["cost"])
        self.assertIsNone(got["runs"][0]["cost"]["value"])
        self.assertIsNone(got["cost"]["value"])           # never a partial sum shown as the whole
        (run / "RUN.json").write_text("{}\n", encoding="utf-8")           # finished: the record is written
        got = lineage.usage_lineage(run, child, own, PRICES)
        # 4 sessions x (120 in + 10 cache-read x 0.1, 10 out x 4) + the preflight (18 in, 2 out), per million tokens
        self.assertEqual(got["cost"]["status"], "known")
        self.assertAlmostEqual(got["cost"]["value"], (4 * (120 + 1 + 40) + 18 + 8) / 1e6, places=9)
        self.assertEqual((got["runs"][0]["recorded"], got["runs"][0]["cost"]["status"]), (True, "known"))


class PreflightLedger(WithTable):
    """What the preflight's ledger does not account for is listed in the run's account — a ledger that does not read
    is unknown spend, not zero; a request sent and never answered is named with its number.
    Pins aisef2/app/lineage.py::account_of [9, 10, 11, 30, 39, 49] and [32, 33, 34, 50]."""

    def unreadable(self, how: str) -> pathlib.Path:
        run = self.tmp / how.replace(" ", "-")
        make_run(run, requests=[("S1", DEV, True)], streams=["S1.developer.1.jsonl"], ledger=False)
        ledger = run / "preflight" / "LEDGER.jsonl"
        ledger.parent.mkdir()
        if how == "a directory in its place":                                   # OSError
            ledger.mkdir()
        elif how == "a torn last line":                                         # ValueError (JSONDecodeError)
            ledger.write_text('{"event": "sent", "kind": "chat", "n": 2}\n{"event": "do', encoding="utf-8")
        else:                                                                   # KeyError
            ledger.write_text('{"event": "sent"}\n', encoding="utf-8")
        return run

    def test_a_ledger_that_does_not_read_is_unknown_spend_listed_never_zero(self):
        for how in ("a directory in its place", "a torn last line", "a row without its number"):
            with self.subTest(how):
                run = self.unreadable(how)
                acct = lineage.account_of(run)                                 # returns: never a traceback
                # nothing invented: the journal's own request and the session's turn and tokens, no preflight
                self.assertEqual({k: acct[k] for k in lineage.SPEND}, {"provider_requests": 1, **SESSION})
                self.assertEqual(len(acct["unaccounted"]), 1, acct["unaccounted"])
                self.assertTrue(all(w in acct["unaccounted"][0] for w in ("preflight", "ledger")), acct["unaccounted"])
                self.assertEqual(lineage.lineage_account(run)["unaccounted"], acct["unaccounted"])   # what a child is asked

    def cut_last_answer(self, run: pathlib.Path) -> None:
        ledger = run / "preflight" / "LEDGER.jsonl"
        lines = ledger.read_text(encoding="utf-8").splitlines()
        self.assertEqual({k: json.loads(lines[-1])[k] for k in ("event", "n")}, {"event": "done", "n": 3})
        ledger.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

    def test_a_preflight_request_sent_and_never_answered_is_listed_with_its_number(self):
        run = self.tmp / "killed-in-preflight"
        make_run(run)
        self.cut_last_answer(run)                         # request 3 sent, no `done` row
        acct = lineage.account_of(run)
        self.assertEqual(len(acct["unaccounted"]), 1, acct["unaccounted"])
        entry = words(acct["unaccounted"][0])
        self.assertIn("preflight", entry)                 # whose request
        self.assertIn("3", entry)                         # which one
        self.assertIn("never answered", acct["unaccounted"][0])             # why it is unaccounted
        # sent counts as a request; only what was answered has tokens (the probe of request 2: 9 in, 1 out)
        self.assertEqual({k: acct[k] for k in lineage.SPEND},
                         {"provider_requests": 3, "turns": 0, "input_tokens": 9, "output_tokens": 1})
        self.assertEqual(lineage.lineage_account(run)["unaccounted"], acct["unaccounted"])


class RequestsInFlight(WithTable):
    """A provider request with no result is unknown spend exactly when a session stream of its story and role exists
    that no answered request of the same story and owner accounts for. Pins aisef2/app/lineage.py::account_of
    [26, 44, 45, 46, 55, 57, 58]."""

    S1 = [("S1", DEV, True), ("S1", REV, True)]
    CASES = {
        "the developer of S2 in flight": (S1 + [("S2", DEV, False)],
                                          ["S1.developer.1.jsonl", "S1.reviewer.1.jsonl", "S2.developer.1.jsonl"],
                                          ("S2", DEV)),
        "the reviewer of S2 in flight": (S1 + [("S2", DEV, True), ("S2", REV, False)],
                                         ["S1.developer.1.jsonl", "S1.reviewer.1.jsonl", "S2.developer.1.jsonl",
                                          "S2.reviewer.1.jsonl"], ("S2", REV)),
        "a second developer request in flight": (S1 + [("S1", DEV, False)],
                                                 ["S1.developer.1.jsonl", "S1.reviewer.1.jsonl", "S1.developer.2.jsonl"],
                                                 ("S1", DEV)),
        "a second developer request never started": (S1 + [("S1", DEV, False)],
                                                      ["S1.developer.1.jsonl", "S1.reviewer.1.jsonl"], None),
        "a second reviewer request never started": (S1 + [("S1", REV, False)],
                                                    ["S1.developer.1.jsonl", "S1.reviewer.1.jsonl"], None),
    }

    def test_each_case_is_unknown_spend_exactly_when_its_session_started(self):
        for n, (name, (requests, streams, lost)) in enumerate(self.CASES.items()):
            with self.subTest(name):
                run = self.tmp / f"run{n}"
                seqs = make_run(run, requests=requests, streams=streams)
                got = lineage.account_of(run)["unaccounted"]
                if lost is None:
                    self.assertEqual(got, [])           # nothing was sent: known 0
                    continue
                self.assertEqual(len(got), 1, got)
                story, owner = lost
                tokens = words(got[0])
                # which run (its directory name, or a path ending in it), which request, whose
                self.assertIn(run.name, [pathlib.PurePath(t).name for t in tokens], got)
                for token in (str(seqs[len(requests) - 1]), story, owner):
                    self.assertIn(token, tokens, got)
                self.assertNotIn(DEV if owner == REV else REV, tokens)


class ContinuationOnUnknownSpend(WithTable):
    """`aisef run --parent` on a lineage whose spend nothing accounts for starts no paid work: refused at the claim,
    naming --accept-unaccounted, before the preflight. Pins aisef2/app/lineage.py::account_of [10, 26, 30, 34, 39, 50,
    55] (the other causes of an unreadable ledger, [9] and [11], are held by PreflightLedger)."""

    def setUp(self) -> None:
        super().setUp()
        env = mock.patch.dict(os.environ, client_config(self.tmp))
        env.start()
        self.addCleanup(env.stop)

    def assert_refused_until_accepted(self, predecessor: pathlib.Path, out: str) -> None:
        source = self.tmp / "source"
        if not source.exists():
            self.project = bundle.load(project_bundle(make_repo(source)))
        transport = provider()
        child = self.tmp / out
        try:
            R.execute(self.project, settings.load(SETTINGS), source, child, transport=transport, predecessor=predecessor,
                      client_exe=str(self.tmp / "no-such-client"))      # never looked up: refused before it
        except R.RunRefused as e:
            refusal = str(e)
        except Exception as e:  # noqa: BLE001 — a run that got past the claim fails on the missing client, whatever it is
            self.fail(f"the run went past the claim on spend nothing accounts for: {type(e).__name__}")
        else:
            self.fail("the run went past the claim on spend nothing accounts for")
        self.assertIn("--accept-unaccounted", refusal)
        rec = json.loads((child / "RUN.json").read_text(encoding="utf-8"))
        self.assertEqual((rec["failure"]["stage"], rec.get("preflight")), ("claim", None))
        self.assertFalse((child / "preflight").exists())
        self.assertEqual(transport.calls, [])                              # nothing was sent

    def test_a_reviewer_in_flight_blocks_the_continuation(self):
        run = self.tmp / "first"
        make_run(run, requests=[("S1", DEV, True), ("S1", REV, True), ("S2", DEV, True), ("S2", REV, False)],
                 streams=["S1.developer.1.jsonl", "S1.reviewer.1.jsonl", "S2.developer.1.jsonl", "S2.reviewer.1.jsonl"],
                 started=True)
        self.assert_refused_until_accepted(run, "second")

    def test_a_preflight_request_never_answered_blocks_the_continuation(self):
        run = self.tmp / "first"
        make_run(run, started=True)
        ledger = run / "preflight" / "LEDGER.jsonl"
        ledger.write_text("\n".join(ledger.read_text(encoding="utf-8").splitlines()[:-1]) + "\n", encoding="utf-8")
        self.assert_refused_until_accepted(run, "second")

    def test_a_preflight_ledger_that_does_not_read_blocks_the_continuation(self):
        run = self.tmp / "first"
        make_run(run, started=True)
        (run / "preflight" / "LEDGER.jsonl").write_text('{"event": "sent", "kind": "chat", "n": 2}\n{"event": "do',
                                                         encoding="utf-8")
        self.assert_refused_until_accepted(run, "second")


if __name__ == "__main__":
    unittest.main()
