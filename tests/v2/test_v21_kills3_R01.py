"""V2.1 mutation-survivor batch R01 (round 2, campaign 3): `aisef2/app/verify.py::_runspec_problems` and `::verify`.

What `aisef run --verify` answers for a run directory is read by the operator (`verdict`, `problems`) and by the
release checks (`verdict`, `problems`, `delivery_verdict`; validation/qualification/release_rehearsal.py,
release_acceptance.py). Three requirements stand behind the survivors of this batch:

* a run that ended before its RunSpec was resolved ran nothing under settings: `_runspec_problems` answers
  `([], None)` — no problem, no settings — and `verify` re-derives the verdict from what the journal holds. The
  one problem such a directory may carry is its own (no journal at all); a finding of the verifier's making ("the
  record cannot be re-derived": a pair that was not returned and could not be unpacked) is a refutation by accident;
* a problem about EVIDENCE.json or about an evidence file says WHICH file and WHAT KIND of failure it is — the file
  could not be read (the class of the OS error, a token of its own, which an operator looks up), or it is not an
  evidence manifest — so a damaged disk is told from a rewritten file, and the path is delimited, so it can be copied;
* a record that cannot be re-derived from its evidence is a finding that names the record, the class of what the
  reader refused and that refusal's own message, as separate tokens (the module's contract: "REFUTED with its
  cause — never a traceback in place of a verdict").

The runs are the smallest that the runtime's own functions can write — a journal of run/begin (and, where the case
needs it, the capabilities and the RunSpec), the record that names it, the manifest that binds both — as
test_v21_kills3_A22 builds them. No client, no provider, no repository; portable.

Closing parentheses and connective prose are not asserted: see the batch report for the mutants audited instead.
"""

from __future__ import annotations

import errno
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, client, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import _runspec_problems, verify  # noqa: E402
from aisef2.arch.enums import Enforcement, EventType as T  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from aisef2.journal.format3 import JournalWriter3  # noqa: E402
from aisef2.product.contract import plain  # noqa: E402
from aisef2.runtime.capability import opaque  # noqa: E402
from aisef2.runtime.runspec import resolve  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402

REVISION = "a" * 40
JOURNAL = "run/journals/aisef-run.jsonl"


def write_run(out: pathlib.Path, project, journal: str | None, **changes) -> None:
    """The directory a run leaves that went as far as `journal` says: None (the run ended before it began: no journal,
    as `R.execute` records when `run` is None), "begin" (run/begin and a capability, then it stopped — the RunSpec was
    never resolved) or "spec" (the RunSpec resolved and nothing more). The record names that journal, spends nothing
    and re-derives as it stands; `changes` replace its fields. The manifest binds the record and the journal."""
    out.mkdir(parents=True)
    ref, events = None, []
    if journal is not None:
        (out / "run" / "journals").mkdir(parents=True)
        cap = opaque("kernel", Enforcement.FULL, tool="x")
        w = JournalWriter3(out / JOURNAL, clock=lambda: 1.0)     # no wall clock: the same bytes on every run
        try:
            w.append(T.RUN_BEGIN, {"journal_format": 3, "run_id": "r01"})
            w.append(T.CAPABILITY_RESOLVED, cap.resolved())
            if journal == "spec":
                bound = resolve([cap], R.layers_of(project, settings.load(e2e.SETTINGS)), REVISION)
                w.append(T.RUN_SPEC_RESOLVED, bound.resolved())
        finally:
            w.close()
        data = (out / JOURNAL).read_bytes()
        events = [{"seq": e.seq, "type": e.type, "data": plain(e.data)}
                  for e in format3.reconstruct(data.decode("utf-8")).events]
        ref = {"path": JOURNAL, "sha256": hashlib.sha256(data).hexdigest(), "lines": data.count(b"\n")}
    rec = {"format": R.FORMAT, "bundle_digest": project.digest, "settings": e2e.SETTINGS, "journal": ref,
           "story_outcomes": {}, "story_errors": [], "delivery_verdict": "NOT_REACHED",
           "budget": {"spent": {k: 0 for k in client.Budget.KEYS}} if journal == "spec" else None,
           "productproof": R.productproof(project, events, set()) if events else None, **changes}
    (out / "RUN.json").write_text(json.dumps(rec), encoding="utf-8")
    (out / R.MANIFEST).write_text(json.dumps(R.evidence_manifest(out)), encoding="utf-8")


class RunDirectory(unittest.TestCase):
    """A fresh run directory (`self.out`, not yet written) and the smallest real project bundle, loaded once."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.project = bundle.load(e2e.project_bundle(REVISION))

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.base = pathlib.Path(t.name).resolve()
        self.out = self.base / "out"

    def written(self, journal: str | None, **changes) -> None:
        write_run(self.out, self.project, journal, **changes)


# ---------------------------------------------------------------------------------- a run that ended before its RunSpec


class ARunThatEndedBeforeItsRunSpecHasNothingToBind(RunDirectory):
    """No `run/spec-resolved` in the journal — the run was refused or failed before the kernel resolved it — means that
    nothing ran under the record's settings. `_runspec_problems` answers a pair: no problem and no settings (not a
    bare None, not a pair of one: its caller unpacks two, and the verifier's net would turn the failed unpacking into
    a finding about the record). Through `verify`, such a directory is judged by what the journal holds, and the only
    problem it can carry is its own: a journal that stops after run/begin verifies, and a record with no journal at
    all (`R.execute` with `run` None) is refuted for exactly that — one problem — with the verdict the empty journal
    re-derives (NOT_REACHED), which the release checks read.
    Pins aisef2/app/verify.py::_runspec_problems [4, 9, 10]."""

    def test_the_function_answers_no_problem_and_no_settings(self):
        self.written("begin")
        events = [{"seq": 1, "type": "run/begin", "data": {"journal_format": 3, "run_id": "r01"}}]
        self.assertEqual(_runspec_problems(self.project, {"settings": e2e.SETTINGS}, events), ([], None))
        self.assertEqual(_runspec_problems(self.project, {"settings": e2e.SETTINGS}, []), ([], None))

    def test_a_journal_that_stops_before_its_runspec_verifies_with_no_problem_of_the_verifier_s_making(self):
        self.written("begin")
        v = verify(self.project, self.out)
        self.assertEqual((v["verdict"], v["problems"]), ("VERIFIED", []), v)
        self.assertEqual((v["delivery_verdict"], v["journal_events"]), ("NOT_REACHED", 2), v)

    def test_a_run_that_ended_before_it_began_is_refuted_for_its_missing_journal_alone(self):
        self.written(None, failure={"type": "RunRefused", "detail": "refused", "stage": "repository"})
        v = verify(self.project, self.out)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertEqual(len(v["problems"]), 1, v["problems"])          # the cause, once
        self.assertIn("journal", v["problems"][0])
        self.assertEqual((v["delivery_verdict"], v["journal_events"]), ("NOT_REACHED", 0), v)


# ---------------------------------------------------------------------------------- the manifest and the evidence files


class TheManifestThatCannotBeUsedIsRefusedWithItsKindOfCause(RunDirectory):
    """EVIDENCE.json is there and cannot be used: the finding is that file's, once, and it says which kind of failure it
    is — the file cannot be read (the OS error's class, as a token of its own: not run on to the file's name), or it
    is valid JSON and not an evidence manifest. Neither binds anything: the anchor is None.
    Pins aisef2/app/verify.py::verify [125, 127]."""

    def refusal(self) -> str:
        v = verify(self.project, self.out)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertIsNone(v["evidence_anchor"])
        self.assertEqual(len(v["problems"]), 1, v["problems"])          # and nothing else is wrong with the directory
        self.assertIn(R.MANIFEST, v["problems"][0])
        return v["problems"][0]

    def test_a_manifest_that_cannot_be_read_names_the_file_and_the_class_of_the_failure(self):      # [125]
        self.written("spec")
        (self.out / R.MANIFEST).rename(self.out / "EVIDENCE.json.aside")      # moved, not removed
        (self.out / R.MANIFEST).mkdir()          # a directory in the file's place: an OSError that is not "absent"
        try:
            (self.out / R.MANIFEST).read_text(encoding="utf-8")
        except OSError as e:     # IsADirectoryError on POSIX, PermissionError on Windows
            cls = type(e).__name__
        problem = self.refusal()
        self.assertRegex(problem, r"\b" + cls + r"\b")      # a word of its own, not the tail of "EVIDENCE.json…"
        kind = problem.replace(R.MANIFEST, "").replace(cls, "").lower()
        self.assertIn("read", kind)      # what was wrong with the file: it could not be read — not "is not JSON"

    def test_a_manifest_that_is_json_and_no_manifest_says_so(self):      # [127]
        for i, text in enumerate(("[]", "null", '{"files": []}')):
            with self.subTest(manifest=text):
                self.out = self.base / f"case{i}"
                self.written("spec")
                (self.out / R.MANIFEST).write_text(text, encoding="utf-8")
                kind = self.refusal().replace(R.MANIFEST, "").lower()
                self.assertIn("manifest", kind)      # the file is JSON; what it is not, is the manifest


class AnEvidenceFileThatCannotBeReadIsNamedByItsPathAndTheClassOfTheFailure(RunDirectory):
    """`R.evidence_manifest` cannot read a file the manifest binds (here the journal: the OS refuses it): one problem, a
    finding of the directory, not a traceback — which says that an evidence file could not be read, the class of the OS
    error and the file's path. The path is delimited: it is what an operator copies, so the class does not run on into
    its first character.
    Pins aisef2/app/verify.py::verify [153, 154]."""

    def test_the_path_and_the_class_are_tokens_and_the_kind_of_failure_is_read(self):
        self.written("spec")
        victim = self.out / JOURNAL
        real = R._content_sha

        def refuse(p: pathlib.Path) -> str:
            if p == victim:
                raise PermissionError(errno.EACCES, "Permission denied", str(p))
            return real(p)

        with mock.patch.object(R, "_content_sha", refuse):
            v = verify(self.project, self.out)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertEqual(len(v["problems"]), 1, v["problems"])
        (problem,) = v["problems"]
        self.assertRegex(problem, r"\bPermissionError\b")
        at = problem.find(str(victim))
        self.assertGreater(at, 0, problem)                           # the file, named by its path
        self.assertFalse(problem[at - 1].isalnum(), problem)        # …beginning where it begins
        self.assertFalse(problem[at + len(str(victim)):][:1].isalnum(), problem)     # …and ending where it ends
        kind = problem.replace(str(victim), "").replace("PermissionError", "").lower()
        self.assertIn("read", kind)      # an evidence file that could not be read: not "does not match"


# ---------------------------------------------------------------------------------- the record that cannot be re-derived


class ARecordThatCannotBeReDerivedNamesTheRecordTheClassAndTheMessage(RunDirectory):
    """The record is a file anyone can write: a field of another type than the run writes (here `budget` a string,
    met when the spend is compared) is refused by the reader, and the verifier answers REFUTED with one problem — never
    the exception. The problem says that the record could not be re-derived from the evidence (the object and the
    operation: so it is told from the findings that a re-derivation DISAGREED), then the class of the refusal and the
    refusal's own message as separate tokens.
    Pins aisef2/app/verify.py::verify [170, 171]."""

    def test_the_problem_says_the_record_the_class_and_the_message_apart(self):
        self.written("spec", budget="x")
        v = verify(self.project, self.out)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertEqual(len(v["problems"]), 1, v["problems"])
        (problem,) = v["problems"]
        self.assertRegex(problem, r"\bAttributeError\b")
        self.assertIn("record", problem)                    # the refused object: the record, not a stray class name
        self.assertIn("re-deriv", problem)                  # the operation that could not be done
        # the class is set off from the message it introduces (a space or a colon), the message is there
        self.assertRegex(problem, r"\bAttributeError\b[:\s]+\S")

    def test_whatever_the_reader_refuses_the_class_and_its_message_are_two_tokens(self):
        """The net is `except Exception`: a refusal of any class. A message that opens with a word must not run into
        the class's name ("ValueErrorstory markers...")."""
        self.written("spec")
        with mock.patch.object(R, "unfinished", side_effect=ValueError("story markers do not pair")):
            v = verify(self.project, self.out)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertEqual(len(v["problems"]), 1, v["problems"])
        (problem,) = v["problems"]
        self.assertRegex(problem, r"\bValueError\b[:\s]+story markers do not pair\b")
        self.assertIn("record", problem)
        self.assertIn("re-deriv", problem)


if __name__ == "__main__":
    unittest.main()
