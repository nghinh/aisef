"""V2.1 (owner B-03, survivor audit of campaign 2): two real requirements of the lineage readers and of the run's
account, found by writing the test of the requirement and seeing it fail on the unmutated product code.

* T09b DEFECT-2 — `claim` (aisef2/app/lineage.py) met a directory where `CONTINUED-BY.json` is: `continued_by` answered
  it with the unreadable-claim marker and `lineage_account` passed it over, but `claim` read its bytes unguarded, so
  an OSError (IsADirectoryError; PermissionError on Windows) escaped `aisef run --parent` — no refusal, no file named.
  A claim that cannot be read is refused, naming the file, and nothing is superseded: with no content there is no
  digest an operator could name. (Already answered on the base this branch was cut from, by the verify cluster's
  64bd9bf: these tests pass before and after; they pin the requirement at every level a consumer sees it, and the
  commit message says so.)

* T20b — `usage` (aisef2/app/usage.py) counted a preflight ledger that EXISTS and does not read as spend 0 under a
  `known` cost: `{value, status: "known", sessions_unknown: []}` with `preflight: null`, while `lineage.account_of`
  lists the same ledger as unaccounted — so the run's cost became `partial` once it was a predecessor. P-V2-11's
  criterion is "unknown is never defaulted to 0" (docs/v2.1/TRACEABILITY.md). The run's own cost is now `partial` with
  the cause, exactly as `account_of` treats the ledger. The same function counted a preflight request that was SENT and
  NEVER ANSWERED as 0 tokens under `known` (the second form of the same defect: `account_of` lists it too).
  What stays, pinned: a run with NO preflight ledger at all (absent, or an empty file) is known as it was.

`usage.usage` is the single writer of RUN.json's `usage` (run.py) and the single re-deriver of it (`aisef run
--verify`, lineage): the through-verify tests show the two agree on a record written by the real writer.
The verification tests run a whole offline product run (the fake client of test_app_run): POSIX-only."""

from __future__ import annotations

import contextlib
import hashlib
import io
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

from aisef2.app import cli, lineage, preflight, settings, usage  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import verify  # noqa: E402
from tests.v2.test_app_run import SETTINGS, ProductBase, project_bundle  # noqa: E402

PRICES = {"currency": "USD", "input_per_mtok": 1.0, "cache_read_per_mtok": 0.1, "cache_write_per_mtok": 1.25,
          "output_per_mtok": 4.0, "source": "test table", "effective_date": "2026-10-06"}
#: one finished step of one million uncached input tokens: exactly 1.0 at PRICES
STEP = json.dumps({"type": "step_finish", "part": {"tokens": {"input": 1_000_000, "output": 0, "reasoning": 0,
                                                             "cache": {"read": 0, "write": 0}}}})
BLIND = json.dumps({"type": "step_finish", "part": {}})      # a finished step that reports no tokens
ANSWERED = ('{"n": 1, "event": "sent", "kind": "chat"}\n'
            '{"n": 1, "event": "done", "http": 200, "input_tokens": 1000000, "output_tokens": 0}\n')    # exactly 1.0
UNANSWERED = ANSWERED + '{"n": 2, "event": "sent", "kind": "chat"}\n'
#: a ledger that exists and that `preflight.accounting` refuses, each a different refusal (ValueError, KeyError,
#: TypeError) — and a directory where the file is (an OSError on every platform)
UNREADABLE = {"a torn last line": '{"n": 1, "event": "sent"}\n{"n": 1, "event": "do',
              "not JSON": "{not json",
              "a row without its number": '{"event": "sent"}\n',
              "a line that is no object": "[]\n",
              "a number that is a list": '{"n": [1], "event": "sent"}\n',
              "a directory at the path": None}


class Account(unittest.TestCase):
    """A run directory with one session of exactly 1.0 and, per test, a preflight ledger of the kind given."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.start("run")

    def start(self, name: str) -> None:
        """The run directory `name`, with its one session: a case that needs no ledger of the previous one's starts
        another directory (nothing is removed)."""
        self.out = self.tmp / name
        (self.out / "sessions").mkdir(parents=True)
        self.log("S1.developer.1.jsonl", STEP)

    def log(self, name: str, *lines: str) -> None:
        (self.out / "sessions" / name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def ledger(self, text: str | None) -> pathlib.Path:
        """The preflight's ledger as `text`; None: a directory in its place."""
        path = self.out / "preflight" / "LEDGER.jsonl"
        path.parent.mkdir(exist_ok=True)
        if text is None:
            path.mkdir()
        else:
            path.write_text(text, encoding="utf-8")
        return path

    def account(self, prices=PRICES) -> dict:
        return usage.usage(self.out, [], prices, {})


class Claim(unittest.TestCase):
    """T09b DEFECT-2: a claim that cannot be read — here a directory where the file is, an OSError on every platform."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.pred = self.tmp / "pred"
        self.pred.mkdir()

    def refused(self, **kw) -> str:
        before = sorted(p.name for p in self.pred.iterdir())
        with self.assertRaises(lineage.LineageRefused) as why:      # not an IsADirectoryError / PermissionError
            lineage.claim(self.pred, self.tmp / "next", 1.0, **kw)
        self.assertEqual(sorted(p.name for p in self.pred.iterdir()), before)    # nothing was claimed or superseded
        return str(why.exception)

    def test_a_claim_that_cannot_be_opened_is_refused_naming_the_file(self):
        (self.pred / lineage.CLAIM).mkdir()
        self.assertIn(lineage.CLAIM, self.refused())

    def test_it_cannot_be_superseded_by_an_assertion_there_is_no_digest_to_name(self):
        (self.pred / lineage.CLAIM).mkdir()
        for sha in (hashlib.sha256(b"").hexdigest(), "0" * 64):      # the digest of "no content" is no claim's digest
            with self.subTest(sha=sha[:8]):
                self.assertIn(lineage.CLAIM, self.refused(supersede=sha))

    def test_the_other_readers_answer_it_and_raise_nothing(self):
        """What the consumers of the same file rely on (the claim's refusal must be as theirs is: an answer)."""
        (self.pred / lineage.CLAIM).mkdir()
        self.assertEqual(lineage.continued_by(self.pred), ("(an unreadable claim)", None))
        self.assertEqual([pathlib.Path(r["run"]) for r in lineage.lineage_account(self.pred)["runs"]], [self.pred])

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0,
                         "a file closed to its owner is unreadable only to a user that is not root, on POSIX")
    def test_a_claim_closed_to_its_user_is_refused_naming_the_file(self):
        claim = self.pred / lineage.CLAIM
        body = (json.dumps({"run": str(self.tmp / "gone")}) + "\n").encode("utf-8")
        claim.write_bytes(body)
        claim.chmod(0)
        self.addCleanup(claim.chmod, 0o644)
        self.assertIn(lineage.CLAIM, self.refused())
        self.assertIn(lineage.CLAIM, self.refused(supersede=hashlib.sha256(body).hexdigest()))   # even its true digest


class RunParent(ProductBase):
    """What the operator runs: `aisef run --parent` on a predecessor whose claim file cannot be read. Refused before
    the repository is cloned and before any provider request — not portable-skipped: the client is never reached."""

    def test_the_command_refuses_with_the_file_named_not_a_traceback(self):
        pred = self.tmp / "pred"
        pred.mkdir()
        (pred / R.STARTED).write_text("{}\n", encoding="utf-8")      # a predecessor killed before its record
        (pred / lineage.CLAIM).mkdir()
        (self.tmp / "project.json").write_text(json.dumps(project_bundle(self.baseline)), encoding="utf-8")
        (self.tmp / "settings.json").write_text(json.dumps(SETTINGS), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.run(["--project", str(self.tmp / "project.json"), "--settings", str(self.tmp / "settings.json"),
                            "--repo", str(self.tmp / "source"), "--out", str(self.tmp / "child"), "--parent", str(pred)])
        self.assertEqual(code, 2)                      # a refusal: the command's own answer, not an exception
        self.assertIn(lineage.CLAIM, err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())
        rec = json.loads((self.tmp / "child" / "RUN.json").read_text(encoding="utf-8"))
        self.assertEqual((rec["failure"]["type"], rec["failure"]["stage"]), ("RunRefused", "claim"))
        self.assertFalse((self.tmp / "child" / "repo").exists())          # nothing was cloned, so nothing ran


class UnknownPreflightSpend(Account):
    """T20b: the run's cost counts what the preflight spent only as far as it is known — never as 0 under `known`."""

    def test_a_ledger_that_exists_and_does_not_read_makes_the_cost_partial_with_the_cause(self):
        for n, (name, text) in enumerate(UNREADABLE.items()):
            with self.subTest(name):
                self.start(f"run-{n}")
                self.ledger(text)
                u = self.account()
                cost = u["cost"]
                self.assertIsNone(cost["value"], cost)           # was 1.0 under "known": the preflight counted as 0
                self.assertTrue(cost["status"].startswith("partial"), cost)
                self.assertIn("ledger", cost["status"])          # the cause is named: it is the ledger, not a session
                self.assertEqual(cost["known"], 1.0)             # what is known stays, beside the unknown
                self.assertEqual(cost["sessions_unknown"], [])
                self.assertIsNone(u["preflight"])                # unchanged: no figure is invented for it
                self.assertEqual(u["tokens"]["input"], 1_000_000)

    def test_it_is_what_account_of_says_and_what_the_run_s_cost_is_as_a_predecessor(self):
        """The run's own cost agrees with the lineage's reading of the same evidence."""
        self.ledger(UNREADABLE["not JSON"])
        self.assertTrue(any("ledger" in u for u in lineage.account_of(self.out)["unaccounted"]))
        own = self.account()
        entry = lineage.usage_lineage(self.out, self.tmp / "child", own, PRICES)["runs"][0]
        self.assertEqual(entry["run"], str(self.out))
        self.assertIsNone(entry["cost"]["value"])
        self.assertIsNone(own["cost"]["value"])
        self.assertEqual(own["cost"]["status"].partition(":")[0], entry["cost"]["status"].partition(":")[0])    # partial

    def test_a_preflight_request_sent_and_never_answered_makes_the_cost_partial(self):
        """The second form: `account_of` lists it as unaccounted ("sent and never answered"), as it lists a ledger it
        cannot read; the run's cost was `known` with the request counted as 0 tokens."""
        self.ledger(UNANSWERED)
        u = self.account()
        cost = u["cost"]
        self.assertIsNone(cost["value"], cost)
        self.assertTrue(cost["status"].startswith("partial"), cost)
        self.assertRegex(cost["status"], r"preflight.*\b2\b")    # the cause names the request
        self.assertEqual(cost["known"], 2.0)                     # the session and the answered request: a lower bound
        self.assertEqual(cost["sessions_unknown"], [])
        self.assertEqual(u["preflight"]["unaccounted"], [2])     # unchanged: the ledger's own account
        self.assertTrue(any("2" in x and "never answered" in x for x in lineage.account_of(self.out)["unaccounted"]))

    def test_the_sessions_and_the_preflight_are_both_named_when_both_are_unknown(self):
        self.log("S2.reviewer.1.jsonl", BLIND)
        self.ledger(UNREADABLE["not JSON"])
        cost = self.account()["cost"]
        self.assertIsNone(cost["value"])
        self.assertEqual(cost["sessions_unknown"], ["S2.reviewer.1.jsonl"])
        self.assertIn("ledger", cost["status"])
        self.assertIn("session", cost["status"])

    def test_the_same_run_is_known_when_the_preflight_is_known(self):
        """What stays: no ledger at all — absent, or a file with no row — and a ledger of answered requests."""
        absent = self.account()
        self.assertEqual((absent["cost"]["value"], absent["cost"]["status"], absent["cost"]["known"]), (1.0, "known", 1.0))
        self.assertEqual(absent["preflight"], {"provider_requests": 0, "turns": 0, "input_tokens": 0, "output_tokens": 0,
                                               "unaccounted": []})
        for n, text in enumerate(("", ANSWERED)):
            with self.subTest(ledger=text):
                self.start(f"run-{n}")
                self.ledger(text)
                u = self.account()
                self.assertEqual((u["cost"]["status"], u["cost"]["value"], u["cost"]["sessions_unknown"]),
                                 ("known", 2.0 if text else 1.0, []))
                self.assertEqual(u["preflight"]["input_tokens"], 1_000_000 if text else 0)

    def test_a_session_that_is_unknown_is_still_the_only_cause_it_was(self):
        """What stays: the status of a run whose only unknown is a session is exactly what it was."""
        self.log("S2.reviewer.1.jsonl", BLIND)
        self.ledger(ANSWERED)
        cost = self.account()["cost"]
        self.assertEqual((cost["value"], cost["status"], cost["known"], cost["sessions_unknown"]),
                         (None, "partial: these sessions' cost is unknown (not 0)", 2.0, ["S2.reviewer.1.jsonl"]))

    def test_without_a_price_table_the_cost_is_unknown_as_it_was(self):
        self.ledger(UNREADABLE["not JSON"])
        self.assertEqual(self.account(None)["cost"], {"value": None, "status": "unknown",
                                                    "why": "the settings give no price table"})


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class ThroughVerify(ProductBase):
    """The record is written by the real writer (run.py, in the run's `finally`) and re-derived by `--verify`, which
    calls the same function: they agree on a run that stopped at its preflight with the ledger damaged. The record of
    a writer that counted the unknown as 0 is the one verify answers."""

    def setUp(self) -> None:
        super().setUp()
        self.settings = settings.load({**SETTINGS, "prices": PRICES})
        self.out = self.tmp / "out"

    def stopped_with(self, drop_or_tear, error):
        """A run whose preflight ledger is damaged by `drop_or_tear(real_append, ledger, row)` as it is written; the
        record the run wrote."""
        real = preflight._append

        def damaged(ledger, row):
            drop_or_tear(real, ledger, row)
        with mock.patch.object(preflight, "_append", damaged):
            with self.assertRaises(error):
                self.execute()
        return json.loads((self.out / "RUN.json").read_text(encoding="utf-8"))

    def agrees_with_verify(self, rec: dict) -> None:
        cost = rec["usage"]["cost"]
        self.assertIsNone(cost["value"], cost)
        self.assertTrue(cost["status"].startswith("partial"), cost)
        v = verify(self.project, self.out)       # refuted for the missing journal — not for the account
        self.assertEqual(v["verdict"], "REFUTED")
        self.assertFalse(any("usage" in p for p in v["problems"]), v["problems"])
        stale = {**rec, "usage": {**rec["usage"], "cost": {**cost, "value": cost["known"], "status": "known"}}}
        (self.out / "RUN.json").write_text(json.dumps(stale), encoding="utf-8")
        (self.out / R.MANIFEST).write_text(json.dumps(R.evidence_manifest(self.out)), encoding="utf-8")
        self.assertTrue(any("usage" in p for p in verify(self.project, self.out)["problems"]))

    def test_a_ledger_that_does_not_read(self):
        def tear(real, ledger, row):
            if row.get("event") == "done" and row.get("n") == 3:     # the last probe's answer is cut mid-line
                with ledger.open("a", encoding="utf-8") as f:
                    f.write('{"event": "do')
            else:
                real(ledger, row)
        rec = self.stopped_with(tear, ValueError)
        self.assertIn("ledger", rec["usage"]["cost"]["status"])
        self.agrees_with_verify(rec)

    def test_a_request_sent_and_never_answered(self):
        def drop(real, ledger, row):
            if not (row.get("event") == "done" and row.get("n") == 3):
                real(ledger, row)
        rec = self.stopped_with(drop, preflight.IdentityStop)
        self.assertEqual(rec["failure"]["type"], "IdentityStop")
        self.agrees_with_verify(rec)

    def test_a_run_that_reached_no_preflight_is_known_and_verifies_as_it_did(self):
        """What stays: the usage of a run refused before its preflight (no ledger at all) is `known` — and the same
        function re-derives it."""
        client_config_other = {"provider": {"fakeprov": {"options": {"baseURL": "https://elsewhere.invalid/v1",
                                                                     "apiKey": "{env:AISEF_TEST_NO_KEY}"}}}}
        (self.tmp / "xdg" / "opencode" / "opencode.json").write_text(json.dumps(client_config_other), encoding="utf-8")
        with self.assertRaises(R.RunRefused):       # the client is configured for another endpoint: refused first
            self.execute()
        rec = json.loads((self.out / "RUN.json").read_text(encoding="utf-8"))
        self.assertFalse((self.out / "preflight").exists())
        self.assertEqual((rec["usage"]["cost"]["value"], rec["usage"]["cost"]["status"]), (0.0, "known"))
        v = verify(self.project, self.out)
        self.assertFalse(any("usage" in p for p in v["problems"]), v["problems"])


if __name__ == "__main__":
    unittest.main()
