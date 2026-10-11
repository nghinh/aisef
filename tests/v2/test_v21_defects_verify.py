"""V2.1 (owner B-03, survivor audit of campaign 2): `aisef run --verify` and the lineage readers meet a file that is
damaged or that is not what a run writes, and answer it with a FINDING — never a traceback, never a silent pass.

* `--verify` (aisef2/app/verify.py): an evidence file that cannot be read (A14); an EVIDENCE.json that is valid JSON and
  no manifest — a list, a number, `{"files": []}`, `null` — which is neither a crash nor "no manifest" (T22b); a RUN.json
  whose journal reference is no object (T22b); a record whose fields are not what a run writes, or a ledger or session
  stream that does not read, met while the record is re-derived. REFUTED, with the cause.
* the lineage readers (aisef2/app/lineage.py, usage.py): a ledger line that is valid JSON but no object (T09a) is spend
  that is unknown, listed — never a TypeError out of `account_of` and `usage`; a claim file that is valid JSON but no
  object (T09b) is as unreadable as a torn one — the marker of `continued_by`, passed over by `lineage_account`, not
  superseded without evidence by `claim`. Their siblings in the same readers: a claimant that is no object, a claim that
  cannot be opened, a run record that is no object, a session stream that does not read.

What stays as it was is pinned too: a manifest that is absent is still a run of a release before 2.1 (a note, VERIFIED).
The verification tests run a whole offline product run (the fake client of test_app_run), so they are POSIX-only."""

from __future__ import annotations

import contextlib
import errno
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

from aisef2.app import cli, lineage, usage  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import verify  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from aisef2.journal.event import EventType as T  # noqa: E402
from tests.v2.test_app_run import ProductBase, project_bundle  # noqa: E402


@unittest.skipUnless(os.name == "posix", "the fake client is a script started by its shebang")
class DamagedRunDirectory(ProductBase):
    """One executed, verified run; each test damages a copy of its files and verifies again."""

    def setUp(self) -> None:
        super().setUp()
        self.execute()
        self.out = self.tmp / "out"
        self.rec = json.loads((self.out / "RUN.json").read_text(encoding="utf-8"))
        self.assertEqual(verify(self.project, self.out)["verdict"], "VERIFIED")
        self.files = {p: p.read_bytes() for p in [self.out / "RUN.json", self.out / R.MANIFEST, self.out / R.STARTED,
                                                  self.out / self.rec["journal"]["path"],
                                                  *sorted((self.out / "preflight").glob("*")),
                                                  *sorted((self.out / "sessions").glob("*.jsonl"))]}

    def restore(self) -> None:
        for p, data in self.files.items():
            if p.is_dir():
                p.rmdir()
            elif p.exists():
                p.chmod(0o644)
            p.write_bytes(data)

    def remanifest(self) -> None:     # as if the run had written it so: what refutes is not the manifest's digest
        (self.out / R.MANIFEST).write_text(json.dumps(R.evidence_manifest(self.out)), encoding="utf-8")

    def with_record(self, **changes) -> dict:
        (self.out / "RUN.json").write_text(json.dumps({**self.rec, **changes}), encoding="utf-8")
        self.remanifest()
        return verify(self.project, self.out)

    def refuted(self, v: dict) -> None:
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertTrue(v["problems"] and all(isinstance(p, str) and p for p in v["problems"]), v)

    # ------------------------------------------------------------------------------------------ an evidence file

    def test_an_evidence_file_that_cannot_be_read_is_refuted_naming_the_file(self):
        """A14: the manifest binds every session stream; one the verifier cannot open was an OSError out of `verify`."""
        stream = sorted((self.out / "sessions").glob("*.jsonl"))[0]
        real = R._content_sha

        def refuse(p: pathlib.Path) -> str:
            if p == stream:
                raise PermissionError(errno.EACCES, "Permission denied", str(p))
            return real(p)
        with mock.patch.object(R, "_content_sha", refuse):
            v = verify(self.project, self.out)
        self.refuted(v)
        self.assertTrue(any(stream.name in p for p in v["problems"]), v["problems"])
        self.assertIsNotNone(v["evidence_anchor"])          # the manifest itself read: its anchor is still what it says

        if hasattr(os, "geteuid") and os.geteuid() != 0:    # and the file really closed to its user
            for victim in (stream, self.out / self.rec["journal"]["path"], self.out / "preflight" / "LEDGER.jsonl"):
                with self.subTest(closed=victim.name):
                    self.restore()
                    victim.chmod(0)
                    self.addCleanup(victim.chmod, 0o644)
                    v = verify(self.project, self.out)
                    self.refuted(v)
                    self.assertTrue(any(victim.name in p for p in v["problems"]), v["problems"])

    # ------------------------------------------------------------------------------------------ the manifest

    def test_a_manifest_that_is_valid_json_and_no_manifest_is_refuted_never_a_crash_or_a_pass(self):
        """T22b: `[]`, `"x"`, `5` and `{"files": []}` were an AttributeError; `null` was read as "no manifest" — VERIFIED,
        no problem, not even the note. A file that is there and is none is a finding; it binds nothing: no anchor."""
        for text in ("[]", '"x"', "5", "true", "null", '{"files": []}', '{"files": null}', '{"files": "x"}'):
            with self.subTest(manifest=text):
                self.restore()
                (self.out / R.MANIFEST).write_text(text, encoding="utf-8")
                v = verify(self.project, self.out)
                self.refuted(v)
                self.assertIsNone(v["evidence_anchor"])
                self.assertTrue(any(R.MANIFEST in p for p in v["problems"]), v["problems"])
                self.assertEqual(v["notes"], [])      # not the note of a run that never had one

    def test_only_an_absent_manifest_is_a_run_of_an_older_release(self):
        """What stays: a run of a release before 2.1 has no manifest — a note, and it verifies. One that is there and
        cannot be read (here: a directory in its place) is damaged evidence, not that. And what stays of a manifest
        that is an object: one that binds none of the files is a manifest that does not match (with its anchor)."""
        (self.out / R.MANIFEST).write_text("{}", encoding="utf-8")
        v = verify(self.project, self.out)
        self.refuted(v)
        self.assertEqual(v["evidence_anchor"], R.anchor_of({}))
        self.assertTrue(any("does not match" in p for p in v["problems"]), v["problems"])
        (self.out / R.MANIFEST).unlink()
        v = verify(self.project, self.out)
        self.assertEqual((v["verdict"], v["problems"], v["evidence_anchor"]), ("VERIFIED", [], None), v)
        self.assertEqual(len(v["notes"]), 1, v["notes"])
        self.assertIn("2.1", v["notes"][0])
        (self.out / R.MANIFEST).mkdir()
        v = verify(self.project, self.out)
        self.refuted(v)
        self.assertTrue(any(R.MANIFEST in p for p in v["problems"]), v["problems"])
        self.assertEqual(v["notes"], [])

    # ------------------------------------------------------------------------------------------ the journal reference

    def test_a_journal_reference_that_is_no_object_or_no_path_is_refuted(self):
        """T22b: RUN.json's `journal` truthy and no object was an AttributeError; a path with a NUL was a ValueError."""
        for journal in ("x", [1], 7, True):
            with self.subTest(journal=journal):
                v = self.with_record(journal=journal)
                self.refuted(v)
                self.assertTrue(any("journal" in p for p in v["problems"]), v["problems"])
                self.assertEqual(v["journal_events"], 0, v)       # nothing was read, so nothing is claimed of it
        v = self.with_record(journal={**self.rec["journal"], "path": "run/journals/a\x00b.jsonl"})
        self.refuted(v)
        named = [p for p in v["problems"] if "ValueError" in p]
        self.assertEqual(len(named), 1, v["problems"])
        self.assertIn("journal", named[0])

    # ------------------------------------------------------------------------------------------ re-derivation

    def test_a_record_field_of_another_type_is_refuted_never_a_crash(self):
        """The record is a file anyone can write: a field of another type than the run writes was an AttributeError,
        a TypeError or a KeyError out of the re-derivation."""
        spent = dict(self.rec["budget"], spent=[1])
        for label, change in {"story_outcomes a list": {"story_outcomes": [1]},
                              "story_outcomes a number": {"story_outcomes": 7},
                              "budget a string": {"budget": "x"},
                              "budget.spent a list": {"budget": spent},
                              "continues a list": {"continues": [1]},
                              "continues without its path": {"continues": {"account": {"provider_requests": 0}}},
                              "story_errors a number": {"story_errors": 7}}.items():
            with self.subTest(label):
                self.refuted(self.with_record(**change))

    def test_a_ledger_or_a_stream_that_does_not_read_is_refuted_never_a_crash(self):
        """The spend is re-derived from the preflight's ledger and the session streams: a ledger line that is no
        object, a torn one, a row without its number, a stream whose steps are no objects — with the manifest made
        again, so it is not the manifest that refutes."""
        ledger = self.out / "preflight" / "LEDGER.jsonl"
        stream = sorted((self.out / "sessions").glob("*.jsonl"))[0]
        for label, victim, text in (("a line that is a list", ledger, "[]\n"), ("a line that is null", ledger, "null\n"),
                                    ("a torn line", ledger, '{"event": "se'), ("a row without its number", ledger, '{"event": "sent"}\n'),
                                    ("a step whose part is a list", stream, '{"type": "step_finish", "part": [1]}\n'),
                                    ("a step whose cache is a list", stream,
                                     '{"type": "step_finish", "part": {"tokens": {"input": 1, "output": 1, "cache": [1]}}}\n')):
            with self.subTest(label):
                self.restore()
                victim.write_text(text, encoding="utf-8")
                self.remanifest()
                self.refuted(verify(self.project, self.out))

    def test_the_command_exits_1_with_the_finding_not_a_traceback(self):
        """What the operator runs: `aisef run --verify` on a directory with a manifest that is no manifest."""
        (self.tmp / "project.json").write_text(json.dumps(project_bundle(self.baseline)), encoding="utf-8")
        (self.out / R.MANIFEST).write_text("[]", encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.run(["--project", str(self.tmp / "project.json"), "--verify", "--out", str(self.out)])
        self.assertEqual(code, 1)
        shown = json.loads(out.getvalue())
        self.assertEqual(shown["verdict"], "REFUTED")
        self.assertTrue(any(R.MANIFEST in p for p in shown["problems"]), shown["problems"])
        self.assertEqual(err.getvalue(), "")


class Dirs(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()

    def run_dir(self, name: str, *, ledger: str | None = None, streams: dict[str, str] | None = None,
                requests: int = 0) -> pathlib.Path:
        run = pathlib.Path(tempfile.mkdtemp(prefix=f"{name}-", dir=self.tmp))     # a name of its own, whatever the case
        if requests:                                                              # a journal of answered requests
            (run / lineage.JOURNAL).parent.mkdir(parents=True)
            w = format3.JournalWriter3(run / lineage.JOURNAL, clock=lambda: 0.0)
            try:
                w.append(T.RUN_BEGIN, {"journal_format": format3.FORMAT, "run_id": run.name})
                for _ in range(requests):
                    e = w.append(T.PROVIDER_REQUEST, {"story_id": "S1", "criteria": ("C-1",), "budget_owner": "DEVELOPER"})
                    w.append(T.PROVIDER_RESULT, {"story_id": "S1", "outcome": "COMPLETED", "synthetic": False,
                                                 "detail": "answered"}, source_seqs=(e.seq,))
            finally:
                w.close()
        if ledger is not None:
            (run / "preflight").mkdir()
            (run / "preflight" / "LEDGER.jsonl").write_text(ledger, encoding="utf-8")
        for stream, text in (streams or {}).items():
            (run / "sessions").mkdir(exist_ok=True)
            (run / "sessions" / stream).write_text(text, encoding="utf-8")
        return run


NOT_AN_OBJECT = ('[1]', 'null', '"x"', '5', 'true')      # valid JSON, and no claim, no record, no ledger row
GOOD_LEDGER = ('{"event": "sent", "kind": "listing", "n": 1}\n{"event": "done", "http": 200, "n": 1}\n'
               '{"event": "sent", "kind": "chat", "n": 2}\n'
               '{"event": "done", "http": 200, "input_tokens": 9, "n": 2, "output_tokens": 1}\n')


class Ledger(Dirs):
    """T09a: a preflight ledger line that is valid JSON but no object was a TypeError out of `account_of` (and out of
    `usage`) — `aisef bundle continue`, `aisef run --parent` — where a torn line or a row without its number are
    spend that is unknown, listed."""

    LINES = ('[]', '1', 'null', '"text"', '{"n": 1, "event": "sent"}\n[]', '{"n": [1], "event": "sent"}',
             '{"n": 1, "event": "done", "input_tokens": [1]}',
             '{"n": 1, "event": "done", "input_tokens": 1e999}')      # an OverflowError: whatever the damage

    def test_a_ledger_line_that_is_no_object_is_unknown_spend_listed(self):
        for line in self.LINES:
            with self.subTest(line):
                run = self.run_dir("run", ledger=line + "\n")
                acct = lineage.account_of(run)                 # returns: never a traceback
                self.assertEqual({k: acct[k] for k in lineage.SPEND}, dict.fromkeys(lineage.SPEND, 0))   # nothing invented
                self.assertEqual(len(acct["unaccounted"]), 1, acct["unaccounted"])
                self.assertTrue(all(w in acct["unaccounted"][0] for w in ("preflight", "ledger")), acct["unaccounted"])
                self.assertEqual(lineage.lineage_account(run)["unaccounted"], acct["unaccounted"])   # what a child is asked

    def test_the_run_s_usage_does_not_know_its_preflight_rather_than_crash(self):
        run = self.run_dir("known", ledger=GOOD_LEDGER)
        self.assertEqual(usage.usage(run, [], None, {})["preflight"]["provider_requests"], 2)     # what stays
        for line in self.LINES:
            with self.subTest(line):
                run = self.run_dir("run", ledger=line + "\n")
                self.assertIsNone(usage.usage(run, [], None, {})["preflight"])


class SessionStreams(Dirs):
    """A session stream the reader refuses was an AttributeError out of `account_of`: what the sessions spent is
    unknown — listed, and the lineage's continuation is then refused unless the operator accepts it."""

    def test_a_stream_that_does_not_read_is_unknown_spend_listed(self):
        for name, text in {"a step whose part is a list": '{"type": "step_finish", "part": [1]}\n',
                           "a step whose cache is a string": '{"type": "step_finish", "part": {"tokens": '
                                                             '{"input": 1, "output": 1, "cache": "x"}}}\n'}.items():
            with self.subTest(name):
                run = self.run_dir("run", ledger=GOOD_LEDGER, streams={"S1.developer.1.jsonl": text}, requests=1)
                acct = lineage.account_of(run)
                self.assertTrue(any("session" in u and "does not read" in u for u in acct["unaccounted"]), acct["unaccounted"])
                # what is known stays known: the preflight's two requests and tokens, the journal's request; the
                # sessions' turns and tokens are the unknown — listed above, not a 0 shown as known
                self.assertEqual({k: acct[k] for k in lineage.SPEND},
                                 {"provider_requests": 3, "turns": 0, "input_tokens": 9, "output_tokens": 1})
                self.assertEqual(lineage.lineage_account(run)["unaccounted"], acct["unaccounted"])

    def test_a_stream_that_reads_is_still_counted(self):
        step = '{"type": "step_finish", "part": {"tokens": {"input": 5, "output": 2}}}\n'
        run = self.run_dir("run", streams={"S1.developer.1.jsonl": step})
        acct = lineage.account_of(run)
        self.assertEqual((acct["turns"], acct["input_tokens"], acct["output_tokens"]), (1, 5, 2))
        self.assertFalse(any("does not read" in u for u in acct["unaccounted"]), acct["unaccounted"])


class Claims(Dirs):
    """T09b: a claim file that is valid JSON but no object was an AttributeError from `continued_by`,
    `lineage_account` and `claim`. As a torn claim: `continued_by` gives the marker and no state, `lineage_account`
    passes over a claim that names no run, `claim` supersedes nothing it cannot reconcile."""

    BODIES = ("{", *NOT_AN_OBJECT, '{"run": 7}', '{"run": ["a"]}')     # the first is the torn one: the others are as it

    def test_continued_by_gives_the_marker_and_no_state(self):
        for body in self.BODIES:
            with self.subTest(body):
                pred = self.run_dir("pred")
                (pred / lineage.CLAIM).write_text(body + "\n", encoding="utf-8")
                marker, state = lineage.continued_by(pred)
                self.assertIsNone(state)
                self.assertIn("unreadable", marker)

    def test_the_lineage_account_passes_over_a_claim_that_names_no_run(self):
        for body in self.BODIES:
            with self.subTest(body):
                pred = self.run_dir("pred")
                (pred / lineage.CLAIM).write_text(body + "\n", encoding="utf-8")
                got = lineage.lineage_account(pred, self.tmp / "asking")             # the predecessor's own claims
                self.assertEqual([r["run"] for r in got["runs"]], [str(pred)])
                earlier = self.run_dir("earlier")             # and those of an earlier run
                (earlier / lineage.CLAIM).write_text(body + "\n", encoding="utf-8")
                (pred / "RUN.json").write_text(json.dumps({"continues": {"path": str(earlier)}}), encoding="utf-8")
                got = lineage.lineage_account(pred, self.tmp / "asking")
                self.assertEqual([r["run"] for r in got["runs"]], [str(pred), str(earlier)])

    def test_a_claim_that_is_no_claim_is_not_superseded_without_evidence(self):
        for body in self.BODIES:
            with self.subTest(body):
                pred = self.run_dir("pred")
                (pred / lineage.CLAIM).write_text(body + "\n", encoding="utf-8")
                with self.assertRaises(lineage.LineageRefused):
                    lineage.claim(pred, self.tmp / "next", 1.0)
                self.assertEqual(sorted(p.name for p in pred.iterdir()), [lineage.CLAIM])      # nothing was written

    def test_a_claimant_that_is_no_object_cannot_be_shown_gone(self):
        child = self.tmp / "child"                      # no record, no journal: UNBEGUN
        for claimant in ([1], "x", 7):
            with self.subTest(claimant):
                pred = self.run_dir("pred")
                (pred / lineage.CLAIM).write_text(json.dumps({"run": str(child), "claimant": claimant}) + "\n",
                                                  encoding="utf-8")
                with self.assertRaises(lineage.LineageRefused) as why:
                    lineage.claim(pred, self.tmp / "next", 1.0)
                self.assertIn("cannot be shown gone", str(why.exception))

    def test_a_claim_that_cannot_be_opened_is_refused_naming_it(self):
        pred = self.run_dir("pred")
        (pred / lineage.CLAIM).mkdir()                  # a directory where the claim is: an OSError on every platform
        with self.assertRaises(lineage.LineageRefused) as why:
            lineage.claim(pred, self.tmp / "next", 1.0)
        self.assertIn(lineage.CLAIM, str(why.exception))
        self.assertEqual(lineage.continued_by(pred)[1], None)      # what stays: the marker, not an exception

    def test_a_valid_claim_is_still_read_and_superseded_by_evidence(self):
        """What stays: a claim `claim` wrote names its run, and one whose child is refused before it began is superseded."""
        pred = self.run_dir("pred")
        child = self.run_dir("child")
        (child / "RUN.json").write_text("{}", encoding="utf-8")        # ENDED_UNBEGUN: a record, no journal
        first = lineage.claim(pred, child, 1.0)
        self.assertEqual(first["run"], str(child))
        self.assertEqual(lineage.continued_by(pred), (str(child), lineage.ENDED_UNBEGUN))
        bare = self.run_dir("bare")                       # an object that names no run: a claim of nothing, not unreadable
        (bare / lineage.CLAIM).write_text("{}\n", encoding="utf-8")
        self.assertEqual(lineage.continued_by(bare), (None, None))
        second = lineage.claim(pred, self.tmp / "next", 2.0)
        self.assertEqual(second["supersedes"]["claim"], lineage.CLAIM)
        self.assertEqual([r["run"] for r in lineage.lineage_account(pred, self.tmp / "next")["runs"]], [str(pred), str(child)])


class RunRecords(Dirs):
    """`predecessor_of` reads RUN.started.json, then RUN.json, of each run of a lineage: one that is valid JSON and no
    object was an AttributeError, a `continues.path` that is no string a TypeError."""

    def test_a_record_that_is_no_object_names_no_predecessor_and_the_next_is_read(self):
        before = self.run_dir("before")
        for body in NOT_AN_OBJECT:
            with self.subTest(body):
                run = self.run_dir("run")
                (run / lineage.STARTED).write_text(body, encoding="utf-8")
                self.assertIsNone(lineage.predecessor_of(run))
                (run / "RUN.json").write_text(json.dumps({"continues": {"path": str(before)}}), encoding="utf-8")
                self.assertEqual(lineage.predecessor_of(run), before)       # as for a torn one: the next file is read
                (run / "RUN.json").write_text(body, encoding="utf-8")
                self.assertIsNone(lineage.predecessor_of(run))

    def test_a_predecessor_that_is_no_path_is_none(self):
        for path in (7, ["a"], {"a": 1}, True, ""):
            with self.subTest(path):
                run = self.run_dir("run")
                (run / "RUN.json").write_text(json.dumps({"continues": {"path": path}}), encoding="utf-8")
                self.assertIsNone(lineage.predecessor_of(run))

    def test_a_chain_whose_record_is_no_object_ends_there(self):
        """The reader of the chain: `lineage_account` accounts the run and stops, rather than raising."""
        run = self.run_dir("run")
        (run / "RUN.json").write_text("[1]", encoding="utf-8")
        got = lineage.lineage_account(run)
        self.assertEqual([r["run"] for r in got["runs"]], [str(run)])


if __name__ == "__main__":
    unittest.main()
