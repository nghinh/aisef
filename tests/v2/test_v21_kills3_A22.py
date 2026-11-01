"""V2.1 mutation-survivor batch A22: `aisef2/app/verify.py::_runspec_problems` and `::verify`, the survivors the triage
proposed not to test, audited — the ones whose reader needs more than the mutant leaves are pinned here.

What a reader of `aisef run --verify` needs from a problem is the identifying elements as elements: the file that could
not be read, the hash prefixes being compared (which is the directory's and which the expected one), the exception
class that says why — each a token of its own, not run together with its neighbour. Connectives, closing punctuation
and the order of an id list are not asserted (nothing reads them; see the batch report).

The runs here are the smallest the runtime's own functions can write: a journal of run/begin, the capabilities and the
RunSpec, the record naming it, the manifest binding both. No client, no provider, no repository; portable.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, client, settings  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.app.verify import _runspec_problems, verify  # noqa: E402
from aisef2.arch.enums import Enforcement, EventType as T  # noqa: E402
from aisef2.invariants import registry as reg  # noqa: E402
from aisef2.journal import format3  # noqa: E402
from aisef2.journal.format3 import JournalWriter3  # noqa: E402
from aisef2.product.contract import plain  # noqa: E402
from aisef2.runtime.capability import opaque  # noqa: E402
from aisef2.runtime.runspec import resolve  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402

REVISION = "a" * 40
JOURNAL = "run/journals/aisef-run.jsonl"
HEX12 = re.compile(r"\b[0-9a-f]{12}\b")     # a 12-hex prefix standing alone: not part of a longer run of hex


def write_run(out: pathlib.Path, project, capabilities: list[dict], spec: dict, record_settings: dict,
              manifest: bool = True) -> None:
    """The run directory a run that resolved its RunSpec and went no further leaves: the journal, the record that
    names it (spend zero, ProductProof as the journal re-derives it) and the manifest that binds both — which a
    run of a release before 2.1 did not write (`manifest=False`)."""
    (out / "run" / "journals").mkdir(parents=True)
    w = JournalWriter3(out / JOURNAL, clock=lambda: 1.0)     # no wall clock: the same bytes on every run
    try:
        w.append(T.RUN_BEGIN, {"journal_format": 3, "run_id": "a22"})
        for c in capabilities:
            w.append(T.CAPABILITY_RESOLVED, c)
        w.append(T.RUN_SPEC_RESOLVED, spec)
    finally:
        w.close()
    data = (out / JOURNAL).read_bytes()
    events = [{"seq": e.seq, "type": e.type, "data": plain(e.data)}
              for e in format3.reconstruct(data.decode("utf-8")).events]
    armed = reg.arm_runtime()   # ROADMAP-2.2 A1: a current run's record carries its kernel and arming — without them
    rec = {"format": R.FORMAT, "bundle_digest": project.digest, "settings": record_settings,   # verify notes an older
           "kernel_digest": R.kernel_digest(),                                                 # release and A22's "one
           "invariants": {"armed": sorted(i.value for i in armed.invariants),                  # note" would be two
                          "registry_digest": armed.registry_digest,
                          "code_mechanism_digest": armed.code_mechanism_digest, "statement": reg.RUNTIME_STATEMENT},
           "journal": {"path": JOURNAL, "sha256": hashlib.sha256(data).hexdigest(), "lines": data.count(b"\n")},
           "story_outcomes": {}, "delivery_verdict": "NOT_REACHED",
           "budget": {"spent": {k: 0 for k in client.Budget.KEYS}},
           "productproof": R.productproof(project, events, set())}
    (out / "RUN.json").write_text(json.dumps(rec), encoding="utf-8")
    if manifest:
        (out / R.MANIFEST).write_text(json.dumps(R.evidence_manifest(out)), encoding="utf-8")


class WithProject(unittest.TestCase):
    """The smallest real project bundle, loaded once per class: a test never hands `verify` a stand-in for it, so none
    depends on how early the verifier stops before looking at the project."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.project = bundle.load(e2e.project_bundle(REVISION))


class MiniRun(WithProject):
    """A run directory `make()` writes into a fresh temporary directory; VERIFIED as it stands."""

    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.out = pathlib.Path(t.name).resolve() / "out"

    def make(self, *, capabilities=None, spec=None, record_settings=None, manifest=True) -> None:
        cap = opaque("kernel", Enforcement.FULL, tool="x")
        bound = resolve([cap], R.layers_of(self.project, settings.load(e2e.SETTINGS)), REVISION)
        write_run(self.out, self.project, [cap.resolved()] if capabilities is None else capabilities,
                  bound.resolved() if spec is None else spec, e2e.SETTINGS if record_settings is None else record_settings,
                  manifest)
        self.bound = bound


class TheRunSpecNetCatchesWhatTheReaderRefuses(WithProject):
    """`_runspec_problems` answers "the settings when they are bound, else why not" — whatever shape of capability event
    it is handed, a problem and no settings, never an exception out of the verifier. Through `verify` the journal's
    reader has already refused a capability event with a missing field or of the wrong kind (format 2's
    `capability/resolved` schema, which format 3 keeps), so the KeyError and TypeError arms of the net are defence in
    depth: this calls the function with the events the reader would have refused.
    Pins aisef2/app/verify.py::_runspec_problems [12, 13]."""

    def refused(self, capability_data):
        events = [{"seq": 1, "type": "capability/resolved", "data": capability_data},
                  {"seq": 2, "type": "run/spec-resolved", "data": {"revision": REVISION, "runspec_hash": "0" * 64}}]
        return _runspec_problems(self.project, {"settings": e2e.SETTINGS}, events)

    def test_a_capability_event_without_a_field_is_a_problem_not_a_KeyError(self):
        problems, bound = self.refused({"name": "kernel"})
        self.assertIsNone(bound)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("KeyError", problems[0])

    def test_a_capability_event_that_is_not_an_object_is_a_problem_not_a_TypeError(self):
        problems, bound = self.refused(["kernel"])
        self.assertIsNone(bound)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("TypeError", problems[0])


class TheHashPrefixesOfARefutedRunSpecAreTwoTokens(MiniRun):
    """The record's settings were edited after the run: the RunSpec they re-derive is not the one the journal chained.
    The operator compares two hash prefixes — the re-derived one first, the journal's second — so each is a prefix of
    its own, 12 hex characters, not one 24-hex run.
    Pins aisef2/app/verify.py::_runspec_problems [32]."""

    def test_the_re_derived_prefix_and_the_journaled_one_are_separate(self):
        raised = {**e2e.SETTINGS, "budget": {**e2e.SETTINGS["budget"], "output_tokens": 99999}}
        self.make(record_settings=raised)
        derived = resolve([opaque("kernel", Enforcement.FULL, tool="x")], R.layers_of(self.project, settings.load(raised)),
                          REVISION).runspec_hash
        self.assertNotEqual(derived, self.bound.runspec_hash)
        v = verify(self.project, self.out)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertEqual(len(v["problems"]), 1, v["problems"])
        self.assertEqual(HEX12.findall(v["problems"][0]), [derived[:12], self.bound.runspec_hash[:12]])


class TheCauseClassOfARunSpecThatDoesNotRederiveIsAToken(MiniRun):
    """A journaled capability whose binding cannot be what its grade requires (VERIFIED with no digest) makes the RunSpec
    not re-derive. The problem names the exception class — the reason code — and the exception's own message, which
    here opens with the capability's name; the class is a token, not the front half of "CapabilityErrorkernel".
    Pins aisef2/app/verify.py::_runspec_problems [42]."""

    def test_the_class_name_stands_apart_from_the_message(self):
        capability = {"name": "kernel", "grade": "VERIFIED", "enforcement": "FULL", "binding": {"version": "1.0"},
                      "identity": "0" * 64}
        spec = {"runspec_hash": "0" * 64, "aggregate_min_grade": "VERIFIED", "capabilities": ["kernel"],
                "revision": REVISION}
        self.make(capabilities=[capability], spec=spec)
        v = verify(self.project, self.out)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertEqual(len(v["problems"]), 1, v["problems"])
        self.assertRegex(v["problems"][0], r"\bCapabilityError\b")
        self.assertIn("kernel", v["problems"][0])     # which capability: the message the class introduces


class TheAnchorsOfAMismatchAreTwoTokensInRoleOrder(MiniRun):
    """`--expect-anchor` is given and the directory's manifest hashes to another value. The refusal puts the directory's
    anchor first and the expected one second, each 12 hex characters of its own: the operator reads which is which by
    position and compares each with what they hold.
    Pins aisef2/app/verify.py::verify [108]."""

    def test_the_directory_s_prefix_then_the_expected_one(self):
        self.make()
        anchor = R.anchor_in(self.out)
        expected = hashlib.sha256(b"an anchor of another run").hexdigest()
        self.assertEqual(verify(self.project, self.out, expect_anchor=anchor)["verdict"], "VERIFIED")
        v = verify(self.project, self.out, expect_anchor=expected)
        self.assertEqual(v["verdict"], "REFUTED", v)
        self.assertEqual(len(v["problems"]), 1, v["problems"])
        self.assertEqual(HEX12.findall(v["problems"][0]), [anchor[:12], expected[:12]])


class AnUnreadableRecordIsNamedByItsFileAndItsCause(WithProject):
    """RUN.json is absent, or is not JSON: nothing to verify against, and the problem is the only thing that says why —
    the path of the file as a token of its own (an operator copies it) and the exception class as another. Where in the
    sentence they stand is not asserted.
    Pins aisef2/app/verify.py::verify [154]."""

    def test_the_path_is_delimited_and_the_cause_class_is_a_token(self):
        for label, content, cause in (("absent", None, "FileNotFoundError"), ("not JSON", "{", "JSONDecodeError")):
            with self.subTest(label), tempfile.TemporaryDirectory() as t:
                out = pathlib.Path(t).resolve()
                if content is not None:
                    (out / "RUN.json").write_text(content, encoding="utf-8")
                v = verify(self.project, out)
                self.assertEqual(v["verdict"], "REFUTED")
                (problem,) = v["problems"]
                path = str(out / "RUN.json")
                at = problem.find(path)
                self.assertGreaterEqual(at, 0, problem)
                self.assertFalse(problem[at + len(path):][:1].isalnum(), problem)     # the path ends where it ends
                self.assertRegex(problem, r"\b" + cause + r"\b")


class ARunWithoutAManifestIsVerifiedWithANoteThatNamesTheFileAndTheReleaseBoundary(MiniRun):
    """A run directory without EVIDENCE.json is VERIFIED — consistency only — with no anchor, and the one note that
    names the missing file and the release from which runs carry one: the same absence in a run of 2.1 or later is a
    manifest deleted, and the release boundary is what lets the operator tell the two apart. What the note goes on to
    say of the record (it is bound by nothing but itself) is not asserted: `evidence_anchor` None says it in the
    document, and a clause nobody parses is not pinned word for word.
    Pins aisef2/app/verify.py::verify [135]."""

    def test_the_note_names_the_file_and_the_release_boundary(self):
        self.make(manifest=False)
        v = verify(self.project, self.out)
        self.assertEqual((v["verdict"], v["evidence_anchor"], v["problems"]), ("VERIFIED", None, []))
        (note,) = v["notes"]
        self.assertIn(R.MANIFEST, note)
        self.assertIn("2.1", note)


if __name__ == "__main__":
    unittest.main()
