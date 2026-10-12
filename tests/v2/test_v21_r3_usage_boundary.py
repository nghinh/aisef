"""V2.1 (owner B-03, round 3, item 4): the journal boundary of `aisef run --verify`.

The reader (`format3.reconstruct`) checks every event against its schema and citations and the hash chain. It does not
fold the six control projections, which the kernel's writer enforces on every append (`Authority.append`): a story that
commits twice, an event of a story after its commit, a retry citing the failure of another attempt. A directory whose
journal breaks them is not one the kernel could have written — yet it is a valid chain of valid events, and a record
derived from it with the verifier's own functions agrees with it. Such a journal is the "invalid journal" the owner's
principle says is refused at a defined boundary rather than handed to the re-derivations (`usage.no_progress` among
them): `verify` folds the projections over the events it reconstructed and, at the first event one refuses, is REFUTED
naming the projection and the event; nothing is re-derived from that journal, as for one that does not reconstruct.

What the tests pin:

* a journal the projections refuse, with a record consistent with it, is REFUTED by a finding that names the
  projection, the event type and the seq (RefusedJournals);
* every honest journal that can be had is admitted: shapes the kernel writes and shapes only the projections admit
  (a committed attempt that observed failures, failures after an outcome), journals of formats 1 and 2, the V2.0.0
  release smoke run's 1,834 events, the reader's own fixtures (AdmittedJournals, JournalsOfRecord);
* the premise "no event of type '' can reach no_progress": a stored line of that type is refused by the reader, in
  every format (EmptyType).

Offline; the run directories are built in a temporary directory with the verifier's own derivations."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import adapters as ad  # noqa: E402
from aisef2.app import bundle, cli, settings, usage  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import _projection_refusal, verify  # noqa: E402
from aisef2.arch.enums import EventType as T  # noqa: E402
from aisef2.journal import compat, event as ev, format2, format3  # noqa: E402
from aisef2.product.contract import canonical  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402
from tests.v2.test_v21_r3_usage_no_progress import SHA, TESTS, UNSAT, Script, events_of, repeat, written  # noqa: E402

_PROJECT = None


def setUpModule() -> None:
    global _PROJECT
    _PROJECT = bundle.load(e2e.project_bundle("a" * 40))


def run_dir(tmp: pathlib.Path, text: str, *, no_progress=None) -> pathlib.Path:
    """The run directory a forger who can write the whole directory would assemble around the journal `text`: the
    journal where RUN.json names it, and a record derived from the journal with the verifier's own functions, so that
    the record agrees with the journal (no evidence manifest: a run of a release before 2.1). `no_progress` replaces
    the record's report."""
    out = tmp / "out"
    (out / "run" / "journals").mkdir(parents=True)
    data = text.encode("utf-8")
    (out / "run" / "journals" / "aisef-run.jsonl").write_bytes(data)
    events = events_of(text)
    rec = {"format": R.FORMAT, "bundle_digest": _PROJECT.digest, "story_errors": [], "budget_stop": None, "failure": None,
           "journal": {"path": "run/journals/aisef-run.jsonl", "sha256": hashlib.sha256(data).hexdigest(),
                       "lines": data.count(b"\n")},
           "story_outcomes": R.outcomes_from(events)}
    verdict, blocked, committed = R.delivery(_PROJECT, events, rec["story_outcomes"], None, [])
    rec.update(delivery_verdict=verdict, delivery_blocked_by=blocked, productproof=R.productproof(_PROJECT, events, committed))
    rec["usage"] = json.loads(json.dumps(usage.usage(out, events, None, rec), default=str))
    rec["no_progress"] = usage.no_progress(events) if no_progress is None else no_progress
    (out / "RUN.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return out


class _Tmp(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.n = 0

    def verify(self, text: str, **kw) -> dict:
        self.n += 1
        return verify(_PROJECT, run_dir(self.tmp / f"d{self.n}", text, **kw))


# ------------------------------------------------------------------------------------------ journals that are refused

def second_begin_after_commit(j: Script, hit: list) -> None:
    j.attempt([], "commit")
    hit.append(j.put(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA}).seq)


def retry_after_commit(j: Script, hit: list) -> None:
    j.begin()
    j.commit()
    j.fail(UNSAT)       # a failure after the commit is admitted; a retry that cites it is not
    hit.append(j.put(T.STORY_RETRY, {"story_id": "S1"}, (j._latest["S1"],)).seq)


def commit_before_admission(j: Script, hit: list) -> None:
    j.put(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
    hit.append(j.put(T.STORY_COMMIT, {"story_id": "S1", "revision": "b" * 40}).seq)


def failure_of_a_story_that_never_began(j: Script, hit: list) -> None:
    hit.append(j.put(T.FAILURE_OBSERVED, {"story_id": "S9", "code": UNSAT[0], "detail": UNSAT[1]}).seq)


def retry_cites_the_attempt_before(j: Script, hit: list) -> None:
    j.attempt([UNSAT], "retry")
    j.put(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
    hit.append(j.put(T.STORY_RETRY, {"story_id": "S1"}, (j._latest["S1"],)).seq)     # the first attempt's failure


def retry_not_its_latest_failure(j: Script, hit: list) -> None:
    j.begin()
    first = j.fail(UNSAT)
    j.fail(TESTS)
    hit.append(j.put(T.STORY_RETRY, {"story_id": "S1"}, (first,)).seq)


def a_second_plan_frozen(j: Script, hit: list) -> None:
    hit.append(j.put(T.PLAN_FROZEN, {"plan_id": "PLAN-2", "plan_hash": "d" * 64, "roles": {"C-ADD": "INTRODUCE"}}).seq)


def a_story_begins_after_the_run_ended(j: Script, hit: list) -> None:
    j.put(T.RUN_DISPOSE_BEGIN, {})
    j.put(T.RUN_END, {})
    hit.append(j.put(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA}).seq)


#: case -> (builder, the projection that refuses first, the type of the event it refuses). `hit` receives its seq.
REFUSED = {
    "a story begins again after it committed": (second_begin_after_commit, "story_state", "story/begin"),
    "a retry follows a commit": (retry_after_commit, "story_state", "story/retry"),
    "a commit with no admitted attempt": (commit_before_admission, "story_state", "story/commit"),
    "a failure of a story that never began": (failure_of_a_story_that_never_began, "story_state", "failure/observed"),
    "a retry cites a failure of the attempt before": (retry_cites_the_attempt_before, "failure_owner", "story/retry"),
    "a retry cites a failure that is not the latest": (retry_not_its_latest_failure, "budgets", "story/retry"),
    "a run freezes two plans": (a_second_plan_frozen, "qualification_counters", "plan/frozen"),
    "a story begins after the run ended": (a_story_begins_after_the_run_ended, "terminal_state", "story/begin"),
}


def refused_journal(case: str) -> tuple[str, int, str, str]:
    """(the journal's text, the seq of the offending event, the projection, the event type) of one case; the journal is
    written by the bare writer, which applies the reader's rules and no projection's."""
    build, pid, kind = REFUSED[case]
    hit: list[int] = []
    text = written(lambda j: build(j, hit), checked=False)
    assert len(hit) == 1, case
    return text, hit[0], pid, kind


class RefusedJournals(_Tmp):
    """Each journal is accepted by the reader and written by no kernel: the bare writer (schema, citations, chain)
    takes it, the writer's Authority would refuse it. The record is derived from the journal, so it is consistent
    with it; the finding is the projection's."""

    def test_each_is_refuted_by_a_finding_naming_the_projection_the_event_and_its_seq(self):
        for case in REFUSED:
            with self.subTest(case):
                text, seq, pid, kind = refused_journal(case)
                self.assertEqual(len(format3.reconstruct(text).events), len(text.splitlines()), "the reader takes it")
                v = self.verify(text)
                self.assertEqual(v["verdict"], "REFUTED", v)
                named = [p for p in v["problems"] if "control projections" in p]
                self.assertEqual(len(named), 1, v["problems"])
                self.assertRegex(named[0], rf"{pid} refuses {re.escape(kind)} at seq {seq}: ")
                self.assertEqual(v["journal_events"], 0, "nothing is re-derived from a journal the kernel could not write")
                self.assertNotEqual(v["delivery_verdict"], "PASS")

    def test_the_helper_names_the_first_event_in_seq_order_and_the_first_projection_to_refuse_it(self):
        for case in REFUSED:
            with self.subTest(case):
                text, seq, pid, kind = refused_journal(case)
                got = _projection_refusal(format3.reconstruct(text).events)
                self.assertIsNotNone(got)
                self.assertEqual(got[:3], (pid, kind, seq))
                self.assertIsInstance(got[3], str)
                self.assertTrue(got[3], "the projection's own reason is carried")

        def build(j: Script) -> None:
            j.put(T.PLAN_FROZEN, {"plan_id": "PLAN-2", "plan_hash": "d" * 64, "roles": {"C-ADD": "INTRODUCE"}})   # 1st
            j.put(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})
            j.put(T.STORY_COMMIT, {"story_id": "S1", "revision": "b" * 40})                                       # 2nd
        got = _projection_refusal(format3.reconstruct(written(build, checked=False)).events)
        self.assertEqual(got[:3], ("qualification_counters", "plan/frozen", 2))

    def test_a_journal_that_would_deliver_is_not_verified_as_delivering(self):
        """The severity of the gap this boundary closes: without it, a journal that breaks the lifecycle and still
        commits its one story was VERIFIED with a delivery verdict of PASS, re-derived from the very events the
        writer would have refused (2.1 at 3dc827b, measured)."""
        def delivered(j: Script, *, admitted: bool = True) -> None:
            if admitted:
                j.begin()
            else:
                j.put(T.STORY_BEGIN, {"story_id": "S1", "parent": SHA})      # a commit with no admission before it
            a = j.put(T.GATE_CHECK, {"gate": "story:S1", "check": "proof", "passed": True, "detail": "verified"}).seq
            j.put(T.GATE_DECISION, {"gate": "story:S1", "passed": True, "projections": ("story_state",)}, (a,))
            j.commit()
            j.close()

        def commits_twice(j: Script) -> None:
            delivered(j)
            j.commit()

        honest = self.verify(written(delivered))
        self.assertEqual((honest["verdict"], honest["delivery_verdict"], honest["problems"]), ("VERIFIED", "PASS", []))
        cases = {"story_state refuses story/commit": lambda j: delivered(j, admitted=False),
                 "story_state refuses story/commit again": commits_twice}
        for finding, build in cases.items():
            with self.subTest(finding):
                v = self.verify(written(build, checked=False))
                self.assertEqual(v["verdict"], "REFUTED", v)
                self.assertTrue(any("story_state refuses story/commit" in p for p in v["problems"]), v["problems"])
                self.assertNotEqual(v["delivery_verdict"], "PASS")
                self.assertEqual(v["journal_events"], 0)

    def test_the_projection_s_reason_is_in_the_finding(self):
        text, seq, pid, kind = refused_journal("a story begins again after it committed")
        reason = _projection_refusal(format3.reconstruct(text).events)[3]
        self.assertIn("S1", reason)     # the story the projection refused, as the projection says it
        v = self.verify(text)
        self.assertTrue(any(reason in p for p in v["problems"]), v["problems"])

    def test_the_operator_sees_the_finding_and_exit_status_1(self):
        """What `aisef run --verify` prints: the finding in the document, exit 1, nothing on stderr."""
        text, seq, pid, kind = refused_journal("a retry follows a commit")
        out = run_dir(self.tmp / "cli", text)
        (self.tmp / "project.json").write_text(json.dumps(e2e.project_bundle("a" * 40)), encoding="utf-8")
        shown, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(shown), contextlib.redirect_stderr(err):
            code = cli.run(["--project", str(self.tmp / "project.json"), "--verify", "--out", str(out)])
        self.assertEqual(code, 1)
        doc = json.loads(shown.getvalue())
        self.assertEqual(doc["verdict"], "REFUTED")
        self.assertTrue(any(f"{pid} refuses {kind} at seq {seq}" in p for p in doc["problems"]), doc["problems"])
        self.assertEqual(err.getvalue(), "")


# ------------------------------------------------------------------------------------------ journals that are admitted

def kernel_shape(j: Script) -> None:
    """What the story runner writes: one failure in an attempt that fails, none in the attempt that commits."""
    j.attempt([UNSAT], "retry")
    j.attempt([TESTS], "retry")
    j.attempt([], "commit")
    j.attempt([UNSAT], "retry", "S2")
    j.attempt([UNSAT], "rollback", "S2")
    j.put(T.RUN_DISPOSE_BEGIN, {})
    j.put(T.RUN_END, {})


def a_committed_attempt_that_observed_failures(j: Script) -> None:
    """Admitted by the projections, written by no story runner: the attempt that committed observed the failure of
    the one before it."""
    j.attempt([UNSAT], "retry")
    j.attempt([UNSAT], "commit")


def failures_after_an_outcome(j: Script) -> None:
    j.attempt([UNSAT], "retry")
    j.fail(TESTS)               # after the outcome, before the next begin
    j.attempt([UNSAT], "rollback")
    j.fail(TESTS)               # after the last outcome


class AdmittedJournals(_Tmp):
    """The boundary refuses nothing the writer's own authority admits: each journal here is written through
    Authority(writer, PROJECTIONS), and verify takes it — with the report the requirement says."""

    def test_a_journal_the_kernel_writes_is_verified(self):
        v = self.verify(written(kernel_shape))
        self.assertEqual((v["verdict"], v["problems"]), ("VERIFIED", []), v)
        self.assertGreater(v["journal_events"], 30)

    def test_a_committed_attempt_that_observed_failures_is_verified_and_reports_nothing(self):
        text = written(a_committed_attempt_that_observed_failures)
        self.assertEqual(usage.no_progress(events_of(text)), [])
        v = self.verify(text)
        self.assertEqual((v["verdict"], v["problems"]), ("VERIFIED", []), v)
        # the committed attempt as a repeated failed one — what 2.1 at 3dc827b recorded — is not what the evidence says
        claimed = [repeat("S1", [2], UNSAT)]
        v = self.verify(text, no_progress=claimed)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertEqual([p for p in v["problems"] if "usage" in p], ["the record's usage is not what the evidence "
                                                                       "re-derives"], v["problems"])

    def test_failures_after_an_outcome_are_verified_and_the_late_failure_is_nobodys(self):
        text = written(failures_after_an_outcome)
        v = self.verify(text, no_progress=[repeat("S1", [2], UNSAT)])
        self.assertEqual((v["verdict"], v["problems"]), ("VERIFIED", []), v)
        v = self.verify(text, no_progress=[])           # the late failure carried into attempt 2 would say this
        self.assertEqual(v["verdict"], "REFUTED", v)

    def test_journals_of_formats_1_and_2_are_admitted_by_the_same_authority(self):
        for fmt in (1, 2):
            with self.subTest(format=fmt):
                text = written(lambda j: (j.attempt([UNSAT], "retry"), j.attempt([UNSAT], "rollback")), fmt=fmt)
                self.assertEqual(format3.reconstruct(text).events[0].data["journal_format"], fmt)
                v = self.verify(text)
                self.assertEqual((v["verdict"], v["problems"]), ("VERIFIED", []), v)
                self.assertEqual(usage.no_progress(events_of(text)), [repeat("S1", [2], UNSAT)])


@unittest.skipUnless(os.name == "posix", "the executed run needs the fake client, a script started by its shebang")
class ExecutedRun(unittest.TestCase):
    """The entry point that writes RUN.json (`run.execute`) and the one that re-derives it (`verify`), on a journal the
    kernel's story runner wrote: a developer that changes nothing, so the story fails with the same failure, is retried
    once (one retry per owner in the settings) and fails again."""

    def test_a_story_that_failed_twice_the_same_way_is_reported_by_the_run_and_verified(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(t).resolve()
            project = bundle.load(e2e.project_bundle(e2e.make_repo(tmp / "source")))
            client = tmp / "client" / "opencode"
            client.parent.mkdir()
            client.write_text(f"#!{sys.executable}\nADD = {e2e.ADD!r}\nTEST = {e2e.TEST!r}\n" + e2e.FAKE_CLIENT)
            client.chmod(0o755)
            (client.parent / "mode").write_text("nothing")
            with mock.patch.object(ad, "scanner", lambda: ad.NoScanner()), \
                    mock.patch.dict(os.environ, e2e.client_config(tmp)):
                rec = R.execute(project, settings.load(e2e.SETTINGS), tmp / "source", tmp / "out",
                                client_exe=str(client), cals=e2e.calibrations(), transport=e2e.provider())
            self.assertEqual(rec["story_outcomes"], {"S1": ["RETRY", "ROLLBACK"]}, rec)
            events = events_of((tmp / "out" / rec["journal"]["path"]).read_bytes().decode("utf-8"))
            failures = [e["data"] for e in events if e["type"] == "failure/observed"]
            self.assertEqual(len(failures), 2)
            self.assertEqual(failures[0]["code"], failures[1]["code"])
            self.assertEqual(failures[0]["detail"], failures[1]["detail"])
            self.assertEqual(rec["no_progress"], [{"story": "S1", "attempts_repeating_the_one_before": [2],
                                                   "failures": [f"{failures[0]['code']}: {failures[0]['detail']}"]}])
            self.assertEqual(rec["no_progress"], usage.no_progress(events))
            v = verify(project, tmp / "out")
            self.assertEqual((v["verdict"], v["problems"]), ("VERIFIED", []), v)


class JournalsOfRecord(unittest.TestCase):
    """Journals nobody here wrote and no test could shape: the V2.0.0 release smoke run's, a real run of a real client
    (1,834 events, one story that repeated failures and then committed), and the reader's own fixtures."""

    def test_the_release_smoke_journal_is_admitted(self):
        run = ROOT / "closure-evidence" / "v2" / "release" / "smoke-2" / "run-1"
        # the journal's lines are LF bytes; a Windows autocrlf checkout of this file (it has no eol attribute) is put back
        data = (run / "aisef-run.jsonl").read_bytes().replace(b"\r\n", b"\n")
        named = json.loads((run / "RUN.json").read_text(encoding="utf-8"))["journal"]
        self.assertEqual(hashlib.sha256(data).hexdigest(), named["sha256"], "it is the journal the record names")
        journal = format3.reconstruct(data.decode("utf-8"))
        self.assertEqual(len(journal.events), 1834)
        self.assertEqual(journal.events[0].data["journal_format"], 3)
        self.assertIsNone(_projection_refusal(journal.events))

    def test_the_readers_fixtures_that_reconstruct_are_admitted_in_formats_1_and_2(self):
        formats = set()
        for path in sorted((ROOT / "tests" / "v2" / "fixtures" / "journal").glob("*.jsonl")):
            try:
                journal = format3.reconstruct(path.read_bytes().decode("utf-8"))
            except ev.JournalError:
                continue        # the fixture is the reader's refusal case: nothing for a projection to fold
            formats.add(journal.events[0].data["journal_format"])
            with self.subTest(path.name):
                self.assertIsNone(_projection_refusal(journal.events))
        self.assertEqual(formats, {1, 2})


# ------------------------------------------------------------------------------------------ the empty type

def stored(seq: int, type_: str, data: dict, prev: str) -> tuple[str, str]:
    """One stored line (canonical, chained) for an event of any type — Event's own constructor refuses an empty one."""
    event = {"data": data, "ignorable": False, "seq": seq, "source_seqs": [], "time": 0.0, "type": type_}
    event_id = hashlib.sha256(canonical(event).encode("utf-8")).hexdigest()
    chain = hashlib.sha256((prev + event_id).encode("ascii")).hexdigest()
    return canonical({"chain": chain, "event": event}) + "\n", chain


class EmptyType(unittest.TestCase):
    """`no_progress` never meets an event whose type is '': the reader refuses the line (`event.decode` builds
    `Event`, whose `__post_init__` refuses an empty type), in every format, ignorable or not. The control: the same
    line with a real type, from the same encoder, is read."""

    def test_a_line_of_type_empty_is_refused_by_the_reader_of_every_format(self):
        for fmt, reader in ((1, compat.reconstruct), (2, format2.reconstruct), (3, format3.reconstruct)):
            with self.subTest(format=fmt):
                text = written(lambda j: None, fmt=fmt)           # run/begin and plan/frozen
                lines = text.splitlines()
                prev = json.loads(lines[-1])["chain"]
                good, _ = stored(len(lines), "run/dispose-begin", {}, prev)
                bad, _ = stored(len(lines), "", {}, prev)
                self.assertEqual(len(reader(text + good).events), len(lines) + 1)     # the encoder is faithful
                with self.assertRaises(ev.JournalError) as raised:
                    reader(text + bad)
                self.assertIn("type", str(raised.exception))

    def test_the_event_itself_cannot_be_built(self):
        for type_ in ("", None, 7):
            with self.subTest(repr(type_)):
                with self.assertRaises(ev.JournalError):
                    ev.Event(0, type_, {}, 0.0)


if __name__ == "__main__":
    unittest.main()
