"""V2.1 (owner decision 2026-10-15, lineage family): `aisef bundle continue` reads a run's journal by the rule of
`aisef run --verify`, and each way the journal can fail it is told apart.

`continue_from` read `story/commit` out of a journal with `format3.reconstruct` alone: a journal whose hash chain is
valid and whose lifecycle no kernel could have written (a story that commits twice — `--verify` REFUTES it naming the
projection and the event) produced a continuation, its carried stories planned from a record the kernel never wrote;
a journal other than the one RUN.json names (digest, length) was taken without a word; and every refusal of the reader
was one text, "the journal does not reconstruct", whatever had happened to the file. The owner's rule is the
verifier's: one definition of a valid journal (`verify._projection_refusal` over the reader's events, and the digest and
length the record names), the approved torn-tail policy (a torn last line is the reader's verified prefix, its effects
reconciled against git and reported as `cut_event` — a killed run is exactly what a continuation is for), and four
failures told apart so the operator knows what to do:

* the journal cannot be read (a permission, an I/O error, a file that is not there)      -> EVIDENCE_UNREADABLE
* it was read and is not a journal this reader accepts (bytes, a line, a format)         -> EVIDENCE_MALFORMED
* it is not the journal that was written (chain, sequence, the record's digest or length) -> EVIDENCE_INTEGRITY
* it is a journal the kernel's writer would have refused (the control projections)       -> EVIDENCE_PROJECTION
* there is nothing that authenticates it where the operator asked for that (`--expect-anchor`): the record names no
  journal, or the run has no manifest -> EVIDENCE_MISSING; the manifest or the anchor are not the ones the evidence
  has -> EVIDENCE_MISMATCH

A refusal changes nothing (the continuation file is not written; the run is never modified). The run directories are
built in a temporary directory from a real repository and a real bundle; the journals are written by the kernel's own
writer. Offline; no client, no provider."""

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

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, bundle_cli, lineage  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import _projection_refusal  # noqa: E402
from aisef2.arch.enums import EventType as T  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from tests.v2.test_app_run import make_repo, project_bundle  # noqa: E402
from tests.v2.test_v21_r3_usage_no_progress import written  # noqa: E402

IS_POSIX_USER = os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0
POSIX_USER = unittest.skipUnless(IS_POSIX_USER, "POSIX permission modes, as a user that is not root")
JOURNAL = "run/journals/aisef-run.jsonl"


class Continuation(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(os.path.realpath(t.name))
        self.source = self.tmp / "source"
        self.baseline = make_repo(self.source)
        self.doc = project_bundle(self.baseline)
        self.project = bundle.load(self.doc)
        self.n = 0

    # -- journals ---------------------------------------------------------------------------------------------------
    def delivered(self) -> str:
        """The journal of a run that committed S1 at the baseline (written through the kernel's authority)."""
        def build(j) -> None:
            j.begin()
            j.put(T.STORY_COMMIT, {"story_id": "S1", "revision": self.baseline})
            j.close()
        return written(build)

    def committing_twice(self) -> str:
        """A chain of valid events the writer's authority would refuse (S1 commits twice): the reader takes it."""
        def build(j) -> None:
            j.begin()
            j.put(T.STORY_COMMIT, {"story_id": "S1", "revision": self.baseline})
            j.put(T.STORY_COMMIT, {"story_id": "S1", "revision": self.baseline})
        return written(build, checked=False)

    # -- the run directory --------------------------------------------------------------------------------------------
    def run_dir(self, journal: str | bytes, *, record: bool = True, manifest: bool = False, names: bytes | str | None = None,
                journal_ref="default") -> pathlib.Path:
        """A run directory around `journal`: its clone (the source repository), RUN.started.json, and — `record` —
        RUN.json naming the journal with the digest and length of `names` (the journal's own bytes when not given),
        and — `manifest` — EVIDENCE.json as the run writes it."""
        self.n += 1
        run = self.tmp / f"run{self.n}"
        (run / "run" / "journals").mkdir(parents=True)
        data = journal if isinstance(journal, bytes) else journal.encode("utf-8")
        (run / JOURNAL).write_bytes(data)
        shutil.copytree(self.source, run / "repo")      # the run's own clone: it holds the baseline
        start = {"format": R.FORMAT, "bundle_digest": self.project.digest, "kernel_digest": R.kernel_digest()}
        (run / R.STARTED).write_text(json.dumps(start), encoding="utf-8")
        if record:
            said = data if names is None else (names if isinstance(names, bytes) else names.encode("utf-8"))
            ref = {"path": JOURNAL, "sha256": hashlib.sha256(said).hexdigest(), "lines": said.count(b"\n")} \
                if journal_ref == "default" else journal_ref
            (run / "RUN.json").write_text(json.dumps({**start, "journal": ref}), encoding="utf-8")
        if manifest:
            (run / R.MANIFEST).write_text(json.dumps(R.evidence_manifest(run), indent=1, sort_keys=True) + "\n", encoding="utf-8")
        return run

    def refused(self, run: pathlib.Path, **kw) -> bundle.BundleError:
        with self.assertRaises(bundle.BundleError) as c:
            bundle_cli.continue_from(self.doc, run, **kw)
        return c.exception

    def code_of(self, run: pathlib.Path, **kw) -> str | None:
        return getattr(self.refused(run, **kw), "code", None)

    def cli(self, run: pathlib.Path, *extra: str) -> tuple[int, str, pathlib.Path]:
        bundle_file = self.tmp / "bundle.json"
        bundle_file.write_text(json.dumps(self.doc), encoding="utf-8")
        out = self.tmp / f"continued{self.n}.json"
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = bundle_cli.main(["continue", str(bundle_file), "--from-run", str(run), "--out", str(out), *extra])
        return code, err.getvalue(), out


class ControlsThatMustKeepWorking(Continuation):
    """A journal that holds, a killed run, a torn tail: continued as before."""

    def test_a_recorded_run_with_a_valid_journal_is_continued(self):
        _, report = bundle_cli.continue_from(self.doc, self.run_dir(self.delivered(), manifest=True))
        self.assertEqual((report["carried"], report["baseline"], report["recorded"], report["torn_tail"]),
                         (["S1"], self.baseline, True, False))

    def test_a_killed_run_with_no_record_and_no_manifest_is_continued(self):
        """The run killed before its record: nothing binds its journal, and that is what the report says (it is not a
        refusal: the continuation of a killed run is the feature)."""
        _, report = bundle_cli.continue_from(self.doc, self.run_dir(self.delivered(), record=False))
        self.assertEqual((report["carried"], report["recorded"], report["evidence_anchor"]), (["S1"], False, None))

    def test_without_an_expected_anchor_the_report_says_the_anchor_was_not_checked(self):
        for manifest in (False, True):
            with self.subTest(manifest=manifest):
                _, report = bundle_cli.continue_from(self.doc, self.run_dir(self.delivered(), manifest=manifest))
                self.assertIs(report["anchor_checked"], False)

    def test_a_torn_last_line_is_the_verified_prefix_and_its_cut_is_reported(self):
        """The approved policy: `--verify` calls a torn tail a finding of a FINISHED run; a continuation exists for the
        run that was killed mid-append, so the verified prefix is taken and the cut event is named — its effects are
        reconciled against git, never assumed undone."""
        text = self.delivered() + '{"chain": "0123456789abcdef", "event": {"data": {"story_id": "S2"'
        for record in (True, False):
            with self.subTest(record=record):
                _, report = bundle_cli.continue_from(self.doc, self.run_dir(text, record=record))
                self.assertEqual((report["carried"], report["torn_tail"]), (["S1"], True))
                self.assertEqual(report["cut_event"]["stories"], ["S2"])
                self.assertEqual(report["cut_event"]["seq"], len(text.split("\n")) - 1)

    def test_a_journal_of_no_complete_event_commits_no_story(self):
        """Not one of the failures below: nothing was verified, so nothing is carried — the refusal it always had."""
        err = self.refused(self.run_dir(self.delivered()[:60], record=False))
        self.assertIn("committed no story", str(err))


@POSIX_USER
class TheJournalCannotBeRead(Continuation):
    def test_a_journal_without_read_permission(self):
        run = self.run_dir(self.delivered(), manifest=True)
        (run / JOURNAL).chmod(0o000)
        self.addCleanup((run / JOURNAL).chmod, 0o644)
        err = self.refused(run)
        self.assertEqual(getattr(err, "code", None), "EVIDENCE_UNREADABLE")
        self.assertIn("PermissionError", str(err))
        self.assertIn(JOURNAL, str(err))

    def test_a_journal_the_record_names_that_is_not_there(self):
        run = self.run_dir(self.delivered())
        (run / JOURNAL).unlink()
        err = self.refused(run)
        self.assertEqual(getattr(err, "code", None), "EVIDENCE_UNREADABLE")
        self.assertIn("FileNotFoundError", str(err))

    def test_a_run_directory_that_cannot_be_searched_is_not_a_missing_record(self):
        """Neither "no run record" nor a journal that does not reconstruct: the directory the operator named."""
        run = self.run_dir(self.delivered())
        run.chmod(0o000)
        self.addCleanup(run.chmod, 0o755)
        err = self.refused(run)
        self.assertIn("PermissionError", str(err))
        self.assertNotIn("no run record", str(err))

    def test_the_text_says_nothing_was_changed_and_what_to_do(self):
        run = self.run_dir(self.delivered())
        (run / JOURNAL).chmod(0o000)
        self.addCleanup((run / JOURNAL).chmod, 0o644)
        text = str(self.refused(run))
        self.assertRegex(text, r"read access|restore|copy")
        self.assertRegex(text, r"never modif|nothing was (written|changed)|not modified")


class TheRecordItself(Continuation):
    """RUN.json is what binds the journal (its digest and length). A run killed before it wrote one is continued from
    RUN.started.json; a record that is there is never quietly replaced by that weaker one."""

    @POSIX_USER
    def test_a_record_that_cannot_be_read_is_not_demoted_to_the_started_record(self):
        """Demoted, the journal's digest is not checked: a journal swapped under an unreadable record was continued."""
        run = self.run_dir(self.delivered(), manifest=False)
        (run / "RUN.json").chmod(0o000)
        self.addCleanup((run / "RUN.json").chmod, 0o644)
        err = self.refused(run)
        self.assertEqual(getattr(err, "code", None), "EVIDENCE_UNREADABLE", str(err))
        self.assertIn("RUN.json", str(err))
        self.assertIn("PermissionError", str(err))

    def test_a_record_that_is_valid_json_and_no_record_is_malformed_not_a_kill(self):
        run = self.run_dir(self.delivered())
        (run / "RUN.json").write_text("[1, 2]", encoding="utf-8")
        self.assertEqual(self.code_of(run), "EVIDENCE_MALFORMED")

    def test_a_record_cut_by_a_kill_during_its_write_falls_back_to_the_started_record(self):
        """The kill window of the record's own write: not JSON, so not a record — the run is continued as one killed
        before its record, and the report says so (`recorded: false`)."""
        run = self.run_dir(self.delivered())
        (run / "RUN.json").write_text('{"format": "aisef-v2-run-rec', encoding="utf-8")
        _, report = bundle_cli.continue_from(self.doc, run)
        self.assertEqual((report["carried"], report["recorded"]), (["S1"], False))


class TheJournalIsNotAJournal(Continuation):
    """Read, and refused by the reader for what it is — bytes, a line, a form. Each journal is bound by a record that
    names its own bytes, so that the digest is not the finding."""

    def test_each_is_malformed_and_is_not_called_integrity(self):
        crlf = self.delivered().replace("\n", "\r\n")
        cases = {"a text that is no journal": "this is not a journal\n",
                 "bytes that are not UTF-8": b"\xff\xfe\x00\x01 not text\n",
                 "a line that is not an event": '{"chain": "x"}\n',
                 "a journal re-encoded with CRLF (not the canonical encoding of its events)": crlf}
        for name, text in cases.items():
            with self.subTest(name):
                err = self.refused(self.run_dir(text))
                self.assertEqual(getattr(err, "code", None), "EVIDENCE_MALFORMED", str(err))
                self.assertRegex(str(err), r"not (a )?journal|not JSON|not a stored event|UTF-8|canonical")


class TheJournalIsNotWhatWasWritten(Continuation):
    def test_a_byte_changed_in_the_middle_breaks_the_hash_chain(self):
        lines = self.delivered().split("\n")
        lines[1] = lines[1].replace("PLAN-1", "PLAN-9")
        err = self.refused(self.run_dir("\n".join(lines)))
        self.assertEqual(getattr(err, "code", None), "EVIDENCE_INTEGRITY", str(err))
        self.assertIn("chain", str(err))

    def test_a_line_removed_breaks_the_sequence(self):
        lines = self.delivered().split("\n")
        del lines[2]
        err = self.refused(self.run_dir("\n".join(lines)))
        self.assertEqual(getattr(err, "code", None), "EVIDENCE_INTEGRITY", str(err))
        self.assertIn("seq", str(err))

    def test_a_journal_that_is_not_the_one_the_record_names_is_refused_though_it_reads(self):
        """A journal that is a valid prefix of the real one (the last line removed) or another valid journal: the
        reader takes both; `--verify` refuses them on the record's digest and length — so does a continuation."""
        full = self.delivered()
        cut = full.rsplit("\n", 2)[0] + "\n"              # the last event removed at a line boundary
        for name, journal, names in (("the last line removed", cut, full),
                                     ("another journal under the record's name", self.committing_twice(), full)):
            with self.subTest(name):
                err = self.refused(self.run_dir(journal, names=names))
                self.assertEqual(getattr(err, "code", None), "EVIDENCE_INTEGRITY", str(err))
                self.assertIn("RUN.json", str(err))
                self.assertRegex(str(err), r"digest|length")

    def test_a_record_whose_length_is_not_the_journals_is_refused_though_its_digest_is(self):
        full = self.delivered()
        run = self.run_dir(full, journal_ref={"path": JOURNAL, "sha256": hashlib.sha256(full.encode()).hexdigest(),
                                              "lines": 1})
        self.assertEqual(self.code_of(run), "EVIDENCE_INTEGRITY")


class TheKernelsWriterWouldHaveRefusedIt(Continuation):
    def test_a_story_that_commits_twice_is_refused_naming_the_projection_the_event_and_its_seq(self):
        text = self.committing_twice()
        self.assertIsNotNone(_projection_refusal(format3.reconstruct(text).events), "the reader takes it")
        pid, kind, seq, _ = _projection_refusal(format3.reconstruct(text).events)
        err = self.refused(self.run_dir(text))
        self.assertEqual(getattr(err, "code", None), "EVIDENCE_PROJECTION", str(err))
        self.assertIn(f"{pid} refuses {kind} at seq {seq}", str(err))      # the verifier's own finding, word for word

    def test_the_same_journal_without_a_record_or_with_a_torn_tail_is_refused_the_same(self):
        text = self.committing_twice()
        for name, journal, record in (("no record (a killed run)", text, False),
                                      ("a torn tail after it", text + '{"chain": "cut', True)):
            with self.subTest(name):
                self.assertEqual(self.code_of(self.run_dir(journal, record=record)), "EVIDENCE_PROJECTION")

    def test_nothing_is_written_when_it_is_refused(self):
        run = self.run_dir(self.committing_twice())
        before = sorted(p.name for p in run.iterdir())
        code, err, out = self.cli(run)
        self.assertEqual(code, 2, err)
        self.assertFalse(out.exists(), "no continuation bundle is written")
        self.assertIn("EVIDENCE_PROJECTION", err)
        self.assertRegex(err, r"^refused: ")
        self.assertEqual(sorted(p.name for p in run.iterdir()), before)

    def test_what_verify_admits_is_admitted(self):
        """The rule is the verifier's, not stricter: a journal the projections admit (a story that retried and then
        committed) is continued."""
        def build(j) -> None:
            j.attempt([("CONTRACT_UNSATISFIED", "proof of C-ADD: CONTRACT_UNSATISFIED")], "retry")
            j.begin()
            j.put(T.STORY_COMMIT, {"story_id": "S1", "revision": self.baseline})
            j.close()
        text = written(build)
        self.assertIsNone(_projection_refusal(format3.reconstruct(text).events))
        _, report = bundle_cli.continue_from(self.doc, self.run_dir(text))
        self.assertEqual(report["carried"], ["S1"])


class TheOperatorAsksForAnAnchor(Continuation):
    """`--expect-anchor`, as `--verify` has it: the anchor the run printed, kept where the developer cannot write. Not
    given, a continuation proves consistency and says so; given, it must be shown."""

    def anchor_of(self, run: pathlib.Path) -> str:
        return R.anchor_in(run)

    def test_the_anchor_the_run_has_is_checked_and_reported(self):
        run = self.run_dir(self.delivered(), manifest=True)
        _, report = bundle_cli.continue_from(self.doc, run, expect_anchor=self.anchor_of(run))
        self.assertIs(report["anchor_checked"], True)
        self.assertEqual(report["evidence_anchor"], self.anchor_of(run))

    def test_a_run_with_no_manifest_cannot_show_it(self):
        for name, run in (("a killed run", self.run_dir(self.delivered(), record=False)),
                          ("a record and no manifest", self.run_dir(self.delivered()))):
            with self.subTest(name):
                err = self.refused(run, expect_anchor="a" * 64)
                self.assertEqual(getattr(err, "code", None), "EVIDENCE_MISSING", str(err))
                self.assertIn(R.MANIFEST, str(err))

    def test_a_different_anchor_is_a_mismatch_not_a_missing_evidence(self):
        run = self.run_dir(self.delivered(), manifest=True)
        err = self.refused(run, expect_anchor="b" * 64)
        self.assertEqual(getattr(err, "code", None), "EVIDENCE_MISMATCH", str(err))
        self.assertIn(self.anchor_of(run)[:12], str(err))
        self.assertIn("b" * 12, str(err))

    def test_evidence_changed_after_the_manifest_was_written_is_a_mismatch_even_with_the_stored_anchor(self):
        """A consistent-looking directory: the manifest still says what it said. Its files do not."""
        run = self.run_dir(self.delivered(), manifest=True)
        anchor = self.anchor_of(run)
        (run / "RUN.json").write_text(json.dumps({"format": R.FORMAT, "changed": True}), encoding="utf-8")
        err = self.refused(run, expect_anchor=anchor)
        self.assertEqual(getattr(err, "code", None), "EVIDENCE_MISMATCH", str(err))

    def test_a_record_that_names_no_journal_is_missing_evidence(self):
        run = self.run_dir(self.delivered(), journal_ref=None)
        err = self.refused(run)
        self.assertEqual(getattr(err, "code", None), "EVIDENCE_MISSING", str(err))
        self.assertRegex(str(err), r"names no journal|ended before")

    def test_the_cli_takes_it_and_refuses_a_value_that_is_not_one(self):
        run = self.run_dir(self.delivered(), manifest=True)
        code, err, out = self.cli(run, "--expect-anchor", self.anchor_of(run))
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(out.exists())
        code, err, _ = self.cli(self.run_dir(self.delivered(), manifest=True), "--expect-anchor", "b" * 64)
        self.assertEqual(code, 2)
        self.assertIn("EVIDENCE_MISMATCH", err)
        with self.assertRaises(SystemExit):        # argparse's own refusal of an argument that is not a sha256
            with contextlib.redirect_stderr(io.StringIO()):
                self.cli(run, "--expect-anchor", "not-hex")


@POSIX_USER
class WhatTheLineageHolds(Continuation):
    """The run asked about is claimed already: the report says by whom and in what state, and a reading failure of
    the child is that state — not a refusal of the continuation bundle (the claim is taken by `aisef run --parent`)."""

    def claim_naming(self, run: pathlib.Path, child: pathlib.Path) -> None:
        (run / lineage.CLAIM).write_text(json.dumps({"run": str(child), "claimed": 1.0, "claimant": {}}) + "\n",
                                         encoding="utf-8")

    def test_a_child_that_cannot_be_read_is_reported_unread_with_its_cause(self):
        run = self.run_dir(self.delivered(), manifest=True)
        child = self.tmp / "child"
        (child / "run" / "journals").mkdir(parents=True)
        (child / JOURNAL).write_text(self.delivered(), encoding="utf-8")
        (child / JOURNAL).chmod(0o000)
        self.addCleanup((child / JOURNAL).chmod, 0o644)
        self.claim_naming(run, child)
        _, report = bundle_cli.continue_from(self.doc, run)
        held = report["already_continued_by"]
        self.assertEqual((held["run"], held["state"]), (str(child), "UNREAD"))
        self.assertIn("PermissionError", held["why"])

    def test_a_child_that_began_still_refuses(self):
        run = self.run_dir(self.delivered(), manifest=True)
        child = self.tmp / "child"
        (child / "run" / "journals").mkdir(parents=True)
        (child / JOURNAL).write_text(self.delivered(), encoding="utf-8")
        self.claim_naming(run, child)
        self.assertIn("which began", str(self.refused(run)))

    def test_a_run_directory_that_cannot_be_listed_is_refused_not_a_traceback(self):
        """The claims of the run are in its directory: a listing that is denied is not "no claims"."""
        run = self.run_dir(self.delivered(), manifest=True)
        run.chmod(0o300)
        self.addCleanup(run.chmod, 0o755)
        code, err, out = self.cli(run)
        self.assertEqual(code, 2, err)
        self.assertRegex(err, r"^refused: ")
        self.assertIn("PermissionError", err)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
