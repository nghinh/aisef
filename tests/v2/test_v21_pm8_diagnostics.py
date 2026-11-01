"""PM-8 (PROBE-DIAGNOSTIC-GAP-001): `aisef2/app/diagnostics.py`, unit by unit — the tap that changes nothing, what is kept
and what is not, the secrets, the bounds, the limit the module states about who can read it, and the structure that
gives it no authority.

* `tapped`: a subclass that overrides `observe()` only; the probe's own `Observation` returned unchanged; identity,
  digest, execution digest and sealed record the untapped probe's; an exception of the probe is the probe's;
* `Sink.note`: the findings it keeps (an executed evaluation whose contract is not SATISFIED; not the pre-state the
  routing table expects of an INTRODUCE or a VERIFY at its parent — a signal the controller did not send is kept), the
  record digest it names, redaction (the JSON-escaped forms of a secret too), bounds, create-only, private modes,
  fail-open — never an exception, a counted mark whose text names no secret;
* `access_of`: what the sandbox's own command line mounts decides the statement, and what is not shown is not claimed;
* `artifact_problems`: the file checks `--verify` makes (the end-to-end ones: test_v21_pm8_diagnostics_run.py);
* structure: no module that decides imports or names it, the sink cannot read, the prompt builders do not name it.

Pins aisef2/app/diagnostics.py, aisef2/app/run.py::probe_factories, ::story_where,
aisef2/app/review_verify.py::artifact_stem"""

from __future__ import annotations

import ast
import json
import os
import pathlib
import re
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle, confine, diagnostics as D  # noqa: E402
from aisef2.app import review_verify as V  # noqa: E402
from aisef2.app import run as R  # noqa: E402
from aisef2.arch.enums import BehaviorVerdict as BV  # noqa: E402
from aisef2.arch.enums import ControlProjection, Enforcement, SubjectAbsence  # noqa: E402
from aisef2.probe import catalog  # noqa: E402
from aisef2.probe.calibration import executing  # noqa: E402
from aisef2.probe.protocol import (  # noqa: E402
    ExecutionEnv, HarnessProbe, Observation, ObservationKind as K, Probe, ProbeInterrupted, RevisionRef, run_probe,
)
from aisef2.product.contract import plain  # noqa: E402
from aisef2.product.spec import ProductProofSpec  # noqa: E402
from tests.v2 import test_app_run as e2e  # noqa: E402

SHA = "89abcdef0123456789abcdef0123456789abcdef"
PARENT = "01234567" * 5
SECRET = "zq9-KEY-7f3a91c2b8"


def make_probe(answer, *, raises=None, name="Fake"):
    """A probe class (a HarnessProbe) answering `answer` — an Observation — or raising `raises`."""
    def observe(self, spec, at, env):
        if raises is not None:
            raise raises
        return answer
    return type(name, (HarnessProbe,), {
        "id": "probe.fake", "digest": "d" * 64, "execution_digest": "e" * 64, "observe": observe,
        "__init__": lambda self, on_range=None, scratch=None: None,
        "enforcement": lambda self: Enforcement.PARTIAL, "harness_preconditions": lambda self: ()})


def spec_of(expect=BV.SATISFIED, absence=SubjectAbsence.REQUIRES_SUBJECT, locator="app.calc:add"):
    return ProductProofSpec.create(
        contract_id="BC-X", probe_id="probe.fake", probe_digest="d" * 64,
        probe_input={"subject": {"kind": "python_callable", "locator": locator}, "stimulus": {}, "observable": {},
                     "subject_absence": absence.value},
        candidate_expectation=expect, compiler_id="t", compiler_digest="c" * 64)


def refuted(detail='{"step": 1, "why": "raised ValueError"}'):
    return Observation(K.OBSERVED, BV.REFUTED, detail)


class FailingOs:
    """`os` as the module sees it, with the named functions made to fail (the sibling is made, the rename is not)."""

    def __init__(self, **failing) -> None:
        self._failing = failing

    def __getattr__(self, name):
        return self._failing.get(name) or getattr(os, name)


class Scratch(unittest.TestCase):
    def setUp(self) -> None:
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = pathlib.Path(t.name).resolve()
        self.out = self.tmp / "out"
        self.out.mkdir()
        self.folder = self.out / D.ARTIFACT_DIR
        self.env = ExecutionEnv(sys.executable, 30, Enforcement.PARTIAL)
        self.at = RevisionRef(SHA, str(self.tmp / "checkout"))

    def fresh(self) -> None:
        """Another run directory (a subtest's own: nothing is ever removed from the one before)."""
        self.fresh_count = getattr(self, "fresh_count", 0) + 1
        self.out = self.tmp / f"out-{self.fresh_count}"
        self.out.mkdir()
        self.folder = self.out / D.ARTIFACT_DIR

    def sink(self, **kw) -> D.Sink:
        return D.Sink(self.out, **{"secrets": (SECRET,), **kw})

    def ctx(self, spec=None, **kw) -> dict:
        s = spec or spec_of()
        return {"origin": "proof", "story_id": "S1", "attempt": 1, "parent": PARENT, "introduces": frozenset(),
                "criteria": {s.id: ["C-1"]}, **kw}

    def see(self, answer, *, spec=None, sink=None, at=None, ctx=None):
        """Run a tapped probe answering `answer` through run_probe; the sink and the sealed record."""
        spec, sink = spec or spec_of(), sink or self.sink()
        probe = D.tapped(make_probe(answer), sink, ctx or self.ctx(spec))()
        record = run_probe(probe, spec, at or self.at, self.env)
        return sink, record

    def docs(self) -> list:
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(self.folder.glob("*.json"))]


class TheTapChangesNothing(Scratch):
    def test_it_returns_the_probes_own_observation_and_only_overrides_observe(self):
        answer = refuted()
        Fake = make_probe(answer)
        T = D.tapped(Fake, self.sink(), self.ctx())
        self.assertTrue(issubclass(T, Fake) and T is not Fake)
        self.assertEqual({k for k in vars(T) if not k.startswith("__")}, {"observe"})
        self.assertIs(T().observe(spec_of(), self.at, self.env), answer)
        self.assertEqual((T.__name__, T.__module__), (Fake.__name__, Fake.__module__))

    def test_identity_digest_execution_digest_and_the_sealed_record_are_the_untapped_probes(self):
        spec, answer = spec_of(), refuted()
        Fake = make_probe(answer)
        T = D.tapped(Fake, self.sink(), self.ctx(spec))
        self.assertEqual((T.id, T.digest, T.execution_digest), (Fake.id, Fake.digest, Fake.execution_digest))
        self.assertEqual(executing(T), executing(Fake))
        self.assertIsInstance(T(), Probe)
        a, b = run_probe(Fake(), spec, self.at, self.env), run_probe(T(), spec, self.at, self.env)
        self.assertEqual((a.record_digest, a.result, a.comparability), (b.record_digest, b.result, b.comparability))

    def test_the_catalog_s_probes_keep_their_identity_when_tapped(self):
        sink = self.sink()
        made = R.probe_factories(sink, self.ctx())
        self.assertEqual(sorted(made), sorted(e.probe_id for e in catalog.CATALOG))
        for e in catalog.CATALOG:
            with self.subTest(probe=e.probe_id):
                probe = made[e.probe_id](None, None)
                self.assertIs(type(probe).__mro__[1], e.factory)
                self.assertEqual((probe.id, probe.digest, executing(type(probe))), (e.probe_id, e.probe_digest, executing(e.factory)))
                self.assertIsInstance(probe, Probe)

    def test_what_the_probe_raises_is_the_probes_and_nothing_is_kept(self):
        sink = self.sink()
        T = D.tapped(make_probe(None, raises=ProbeInterrupted("a signal the controller sent")), sink, self.ctx())
        with self.assertRaises(ProbeInterrupted):
            T().observe(spec_of(), self.at, self.env)
        self.assertEqual((sink.written, sink.not_written), (0, 0))

    def test_what_has_no_observe_to_override_is_returned_as_it_is(self):
        sink = self.sink()
        plain_function = lambda **kw: None      # noqa: E731
        self.assertIs(D.tapped(plain_function, sink, {}), plain_function)

        class NoObserve:
            id, digest = "probe.x", "d" * 64
        self.assertIs(D.tapped(NoObserve, sink, {}), NoObserve)

    def test_the_decision_of_a_run_through_the_tap_is_the_untapped_one_for_every_kind_of_observation(self):
        cases = [refuted(), Observation(K.OBSERVED, BV.SATISFIED), Observation(K.SUBJECT_ABSENT, None, "no add"),
                 Observation(K.SUBJECT_DEADLINE, BV.REFUTED, "2s expired"), Observation(K.HARNESS_FAILED, None, "no python"),
                 Observation(K.UNSUPPORTED, None, "not a scenario"),
                 Observation(K.NON_CONTROLLER_SIGNAL, None, "SIGKILL after the dispatch")]
        for answer in cases:
            with self.subTest(kind=answer.kind.value, verdict=answer.verdict):
                spec = spec_of()
                plain = run_probe(make_probe(answer)(), spec, self.at, self.env)
                _, tapped = self.see(answer, spec=spec, sink=self.sink())
                self.assertEqual((tapped.record_digest, tapped.result), (plain.record_digest, plain.result))


class WhatIsKept(Scratch):
    def test_a_refuted_observation_is_kept_with_what_the_probe_saw_and_the_record_it_became(self):
        spec = spec_of()
        sink, record = self.see(refuted(), spec=spec)
        (d,) = self.docs()
        self.assertEqual(self.folder.joinpath("S1.1.p1.json").is_file(), True)
        self.assertEqual((d["format"], d["origin"], d["story_id"], d["attempt"], d["index"]),
                         (D.ARTIFACT_FORMAT, "proof", "S1", 1, 1))
        self.assertEqual((d["spec_id"], d["probe_id"], d["probe_digest"], d["revision"], d["enforcement"]),
                         (spec.id, "probe.fake", "d" * 64, SHA, "PARTIAL"))
        self.assertEqual((d["expected"], d["result"]), ("SATISFIED", {"behavior_verdict": "REFUTED", "reason": None}))
        row = {"type": "probe/evaluated", "data": {"story_id": "S1", "criterion_id": "C-1", "record": plain(record)}}
        self.assertEqual(D.artifact_problems(self.out, [row], {}), ([], []))     # the sealed record the row will hold
        shown = {"step": 1, "why": "raised ValueError"}
        self.assertEqual(d["observation"], {"kind": "OBSERVED", "verdict": "REFUTED", "elided": 0, "detail": shown,
                                            "detail_chars": len(json.dumps(shown, sort_keys=True))})
        self.assertEqual((d["criteria"], d["at_parent"], d["audience"], d["diagnostics_access"], d["redacted"]),
                         (["C-1"], False, "operator", D.SAME_USER, 0))
        self.assertEqual((sink.written, sink.not_written, sink.dropped), (1, 0, 0))

    def test_a_tampers_reason_reaches_the_operator_artifact_non_empty(self):
        # PM-8 keeps the probe's facts in the operator's probe-observation artifact — what the sealed record omits
        # ({behavior_verdict: REFUTED}, no more). A tamper REFUTED carries its reason here, so the operator can see WHY
        # it was refuted. This is the operator consumer the carried HARNESS audits missed: the reason must reach the
        # artifact and be non-empty (pinned by behaviour, not by its exact wording).
        facts = {"subject": "present", "tampered": "an answer on the subject's channel is not the agent's"}
        self.see(Observation(K.OBSERVED, BV.REFUTED, json.dumps(facts)), spec=spec_of(BV.SATISFIED))
        (d,) = self.docs()
        self.assertEqual(d["observation"]["detail"]["subject"], "present")
        self.assertTrue(d["observation"]["detail"]["tampered"], d)   # the reason reached the artifact, non-empty
        self.assertEqual(d["audience"], "operator")

    def test_what_is_not_a_finding_is_not_kept(self):
        for answer in (Observation(K.OBSERVED, BV.SATISFIED), Observation(K.HARNESS_FAILED, None, "no python"),
                       Observation(K.UNSUPPORTED, None, "not a scenario"),
                       Observation(K.SUBJECT_DEADLINE, BV.SATISFIED, "the window expired, as the contract wants")):
            # (a REFUTED observation against a contract expecting REFUTED is the other side of the same rule, below)
            with self.subTest(kind=answer.kind.value, verdict=answer.verdict):
                sink, _ = self.see(answer)
                self.assertEqual((sink.written, sink.not_written, self.folder.exists()), (0, 0, False))

    def test_it_is_the_contracts_own_expectation_that_decides_not_the_verdict_s_name(self):
        sink, _ = self.see(Observation(K.OBSERVED, BV.SATISFIED), spec=spec_of(BV.REFUTED))     # expected REFUTED: not met
        (d,) = self.docs()
        self.assertEqual((d["expected"], d["observation"]["verdict"]), ("REFUTED", "SATISFIED"))
        self.fresh()
        sink, _ = self.see(Observation(K.OBSERVED, BV.REFUTED), spec=spec_of(BV.REFUTED))       # expected REFUTED: met
        self.assertEqual((sink.written, sink.not_written, self.folder.exists()), (0, 0, False))

    def test_every_other_executed_kind_that_is_not_satisfied_is_kept_with_its_text(self):
        for answer, why, reason in (
                (Observation(K.NON_CONTROLLER_SIGNAL, None, "SIGKILL after the dispatch"), "SIGKILL after the dispatch",
                 "NON_CONTROLLER_SIGNAL"),
                (Observation(K.SUBJECT_ABSENT, None, "the module has no add"), "the module has no add", "PRECONDITION_ABSENT"),
                (Observation(K.SUBJECT_DEADLINE, BV.REFUTED, "the 2s window expired at step 1"),
                 "the 2s window expired at step 1", None)):
            with self.subTest(kind=answer.kind.value):
                self.fresh()
                self.see(answer)
                (d,) = self.docs()
                self.assertEqual((d["observation"]["kind"], d["observation"]["detail"]), (answer.kind.value, why))
                self.assertEqual(d["result"]["reason"], reason)
                self.assertEqual(d["observation"]["verdict"], answer.verdict.value if answer.verdict else None)

    def test_what_the_story_introduces_is_not_there_at_its_parent_and_that_is_no_finding(self):
        spec = spec_of()
        at_parent = RevisionRef(PARENT, str(self.tmp / "checkout"))
        for introduces, at, kept in ((frozenset({spec.id}), at_parent, 0),      # the expected state
                                     (frozenset(), at_parent, 1),               # a PRESERVE or VERIFY at the parent: real
                                     (frozenset({spec.id}), self.at, 1)):       # what it introduces, at the candidate
            with self.subTest(introduces=bool(introduces), at_parent=at is at_parent):
                self.fresh()
                self.see(refuted(), spec=spec, at=at, ctx=self.ctx(spec, introduces=introduces))
                docs = self.docs() if self.folder.exists() else []
                self.assertEqual(len(docs), kept)
                if kept:
                    self.assertEqual(docs[0]["at_parent"], at is at_parent)

    def test_at_the_parent_only_the_pre_state_the_routing_table_expects_of_the_role_is_no_finding(self):
        spec = spec_of()
        at_parent = RevisionRef(PARENT, str(self.tmp / "checkout"))
        absent = Observation(K.SUBJECT_ABSENT, None, "the module has no add")             # INDETERMINATE(PRECONDITION_ABSENT)
        signal = Observation(K.NON_CONTROLLER_SIGNAL, None, "SIGSEGV after the dispatch")  # INDETERMINATE(NON_CONTROLLER_SIGNAL)
        deadline = Observation(K.SUBJECT_DEADLINE, BV.REFUTED, "the 2s window expired")
        rows = (       # (what the plan says of the spec in this story, what the probe saw, is it a finding)
            ("introduces", refuted(), False), ("introduces", deadline, False), ("introduces", absent, False),
            ("introduces", signal, True),      # the table routes it to INTEGRATION at every point: the very gap PM-8 is
            ("verifies", refuted(), False), ("verifies", deadline, False),     # UNCONSTRAINED: either is READY
            ("verifies", absent, True), ("verifies", signal, True),           # PRECONDITION_BROKEN; INTEGRATION
            ("preserves", refuted(), True), ("preserves", deadline, True), ("preserves", absent, True),
            ("preserves", signal, True))
        for role, answer, kept in rows:
            with self.subTest(role=role, kind=answer.kind.value, detail=answer.detail[:24]):
                self.fresh()
                ctx = self.ctx(spec, **{"introduces": frozenset({spec.id})} if role == "introduces" else
                               {"verifies": frozenset({spec.id})} if role == "verifies" else {})
                sink, _ = self.see(answer, spec=spec, at=at_parent, ctx=ctx)
                self.assertEqual((sink.written, sink.not_written), (int(kept), 0))
                if kept:
                    self.assertTrue(self.docs()[0]["at_parent"])

    def test_the_parent_is_the_measurement_point_not_a_commit_id(self):
        # a story with no developer work proves at the candidate that is its parent's own commit: the proof is the
        # candidate's — the journal holds `story/admitted` by then — and what it saw is a finding
        spec = spec_of()
        at_parent = RevisionRef(PARENT, str(self.tmp / "checkout"))
        for admitted, kept in ((False, 0), (True, 1)):
            with self.subTest(admitted=admitted):
                self.fresh()
                sink, _ = self.see(refuted(), spec=spec, at=at_parent,
                                   ctx=self.ctx(spec, introduces=frozenset({spec.id}), admitted=admitted))
                self.assertEqual(sink.written, kept)
                if kept:
                    self.assertFalse(self.docs()[0]["at_parent"])

    def test_the_detail_is_data_when_the_probe_made_json_of_it_and_text_otherwise(self):
        for detail, shown in (('{"a": [1, 2]}', {"a": [1, 2]}), ("[1, 2]", [1, 2]), ("not json", "not json"),
                              ('"quoted"', '"quoted"'), ("42", "42"), ("", ""), ("{broken", "{broken")):
            with self.subTest(detail=detail):
                self.fresh()
                self.see(refuted(detail))
                self.assertEqual(self.docs()[0]["observation"]["detail"], shown)

    def test_a_deeply_nested_detail_is_cut_at_the_depth_no_probe_grammar_reaches(self):
        deep = "[" * 3000 + "]" * 3000
        sink, _ = self.see(refuted(deep))
        (d,) = self.docs()
        self.assertEqual((sink.written, sink.not_written), (1, 0))
        try:
            json.loads(deep)
        except RecursionError:   # 3.11's C parser gives up before the cut can apply: the detail is the probe's own
            self.assertEqual(d["observation"]["detail"], deep)         # text, the same rule as "{broken"
            return
        self.assertIn(f"<nested deeper than {V.DEPTH_MAX} levels>", json.dumps(d["observation"]["detail"]))
        self.assertLess(json.dumps(d).count("["), 2 * V.DEPTH_MAX)      # the file holds the cut, not 3,000 levels

    def test_the_names_are_the_story_s_stem_attempt_and_the_evaluation_s_place(self):
        long_id = "STORY-" + "x" * 80
        sink = self.sink()
        for story, attempt in (("S1", 1), ("S1", 1), ("S1", 2), (long_id, 1), ("a/b", 3)):
            spec = spec_of()
            D.tapped(make_probe(refuted()), sink, self.ctx(spec, story_id=story, attempt=attempt))().observe(
                spec, self.at, self.env)
        names = sorted(p.name for p in self.folder.glob("*.json"))
        self.assertEqual(names, sorted(["S1.1.p1.json", "S1.1.p2.json", "S1.2.p1.json",
                                        f"{V.artifact_stem(long_id)}.1.p1.json", f"{V.artifact_stem('a/b')}.3.p1.json"]))
        self.assertEqual(V.artifact_stem("a/b"), "a_b-" + __import__("hashlib").sha256(b"a/b").hexdigest()[:8])
        self.assertTrue(all(D._NAME.fullmatch(n) for n in names), names)

    def test_a_review_reproducers_file_is_named_by_the_findings_place_and_names_the_finding(self):
        spec = spec_of()
        ctx = {"origin": "review", "story_id": "S1", "attempt": 2, "index": 3, "finding": "F-7"}
        self.see(refuted(), spec=spec, ctx=ctx)
        (d,) = self.docs()
        self.assertTrue(self.folder.joinpath("S1.2.r3.json").is_file())
        self.assertEqual((d["origin"], d["index"], d["finding"]), ("review", 3, "F-7"))
        self.assertNotIn("criteria", d)
        self.assertNotIn("at_parent", d)


class SecretsAndBounds(Scratch):
    def test_the_run_s_secrets_are_replaced_in_the_detail_in_nested_values_and_in_the_finding_s_id(self):
        detail = json.dumps({"why": f"raised KeyError: {SECRET}", "files": {SECRET: [1, f"x{SECRET}y"]}, "n": 7})
        ctx = {"origin": "review", "story_id": "S1", "attempt": 1, "index": 0, "finding": f"id-{SECRET}"}
        self.see(refuted(detail), ctx=ctx)
        raw = self.folder.joinpath("S1.1.r0.json").read_text(encoding="utf-8")
        self.assertNotIn(SECRET, raw)
        (d,) = self.docs()
        self.assertEqual(d["observation"]["detail"], {"why": f"raised KeyError: {V.REDACTED}",
                                                      "files": {V.REDACTED: [1, f"x{V.REDACTED}y"]}, "n": 7})
        self.assertEqual((d["finding"], d["redacted"]), (f"id-{V.REDACTED}", 4))

    def test_a_secret_is_replaced_in_the_json_part_of_a_text_detail_where_json_wrote_it_escaped(self):
        # file_artifact: "the 2s observation window expired (cls); " + json.dumps(facts) — not JSON as a whole, so the
        # text is searched, and json.dumps wrote a quote, a backslash, a non-ASCII letter as an escape
        secret = 'k"ey\\\u00e9-91827364'
        facts = {"read": "git", "revision": SHA, "text": f"line: {secret}"}
        detail = "the 2s observation window expired (grep_count); " + json.dumps(facts)
        self.assertNotIn(secret, detail)      # as the probe wrote it, the secret is not there in its own form
        sink = D.Sink(self.out, secrets=(secret,))
        self.see(Observation(K.SUBJECT_DEADLINE, BV.REFUTED, detail), sink=sink)
        (d,) = self.docs()
        shown = d["observation"]["detail"]
        for form in (secret, json.dumps(secret)[1:-1]):      # as the user's env holds it, as json.dumps wrote it
            self.assertNotIn(form, shown)
        self.assertIn(V.REDACTED, shown)
        self.assertGreater(d["redacted"], 0)
        self.assertIn(SHA, shown)      # and nothing else of the detail is touched

    def test_a_secret_in_its_raw_form_in_a_text_detail_is_replaced(self):
        # a secret as the user's env holds it, un-escaped, in a plain-text detail (not JSON): the raw form of it must be
        # searched too, not only json.dumps's escape of it, else a quote/backslash/non-ASCII secret leaks into RUN.json
        secret = 'k"ey\\é-91827364'
        self.assertNotEqual(secret, json.dumps(secret)[1:-1])      # raw and escaped forms differ for this secret
        sink = D.Sink(self.out, secrets=(secret,))
        self.see(refuted(f"grep_count found the line: {secret}"), sink=sink)
        (d,) = self.docs()
        shown = d["observation"]["detail"]
        self.assertNotIn(secret, shown)
        self.assertIn(V.REDACTED, shown)
        self.assertGreater(d["redacted"], 0)

    def test_the_why_of_a_failure_in_RUN_json_names_no_secret(self):
        sink = self.sink()
        with mock.patch.object(D.Sink, "_document", side_effect=RuntimeError(f"cannot render {SECRET}")):
            sink.note(self.ctx(), spec_of(), self.at, make_probe(None)(), refuted())
        self.assertEqual(sink.not_written, 1)
        self.assertNotIn(SECRET, json.dumps(sink.report()))
        self.assertEqual(sink.failures[0]["why"], f"RuntimeError: cannot render {V.REDACTED}")

    def test_a_secret_made_of_digits_in_a_number_is_replaced_too(self):
        sink = D.Sink(self.out, secrets=("918273645",))
        self.see(refuted('{"returned": 918273645}'), sink=sink)
        self.assertNotIn("918273645", self.folder.joinpath("S1.1.p1.json").read_text(encoding="utf-8"))

    def test_a_detail_longer_than_the_bound_is_cut_and_says_by_how_much(self):
        text = "x" * (D.DETAIL_MAX + 100)
        self.see(refuted(text))
        (d,) = self.docs()
        self.assertEqual((len(d["observation"]["detail"]), d["observation"]["detail_chars"], d["observation"]["elided"]),
                         (D.DETAIL_MAX, D.DETAIL_MAX + 100, 100))
        big = json.dumps({"rows": ["y" * 100] * 200})      # JSON that does not fit: its canonical text, cut
        self.see(refuted(big), ctx=self.ctx(attempt=2))
        d = self.docs()[-1]
        self.assertIsInstance(d["observation"]["detail"], str)
        self.assertEqual((len(d["observation"]["detail"]), d["observation"]["elided"] > 0), (D.DETAIL_MAX, True))
        self.assertEqual(d["observation"]["detail_chars"] - d["observation"]["elided"], D.DETAIL_MAX)

    def test_a_run_writes_at_most_its_limit_and_counts_what_it_did_not_keep(self):
        sink = self.sink(files_max=2)
        spec = spec_of()
        for _ in range(5):
            D.tapped(make_probe(refuted()), sink, self.ctx(spec))().observe(spec, self.at, self.env)
        self.assertEqual((sink.written, sink.dropped, sink.not_written), (2, 3, 0))
        self.assertEqual(len(list(self.folder.glob("*.json"))), 2)
        self.assertEqual(sink.report()["limits"], {"detail_chars": D.DETAIL_MAX, "files": 2})


class PrivateAndFailOpen(Scratch):
    @unittest.skipUnless(os.name == "posix", "modes")
    def test_the_directory_is_0700_and_the_files_0600_and_no_sibling_is_left(self):
        self.see(refuted())
        self.assertEqual(self.folder.stat().st_mode & 0o777, 0o700)
        self.assertEqual([p.stat().st_mode & 0o777 for p in self.folder.iterdir()], [0o600])
        self.assertEqual([p.name for p in self.folder.iterdir()], ["S1.1.p1.json"])

    @unittest.skipUnless(os.name == "posix", "modes")
    def test_a_directory_that_exists_with_wider_modes_is_narrowed(self):
        self.folder.mkdir(mode=0o755)
        os.chmod(self.folder, 0o755)
        self.see(refuted())
        self.assertEqual(self.folder.stat().st_mode & 0o777, 0o700)

    def test_a_file_is_never_overwritten(self):
        self.folder.mkdir()
        existing = self.folder / "S1.1.p1.json"
        existing.write_text("the first", encoding="utf-8")
        sink, _ = self.see(refuted())
        self.assertEqual(existing.read_text(encoding="utf-8"), "the first")
        self.assertEqual((sink.written, sink.not_written), (0, 1))
        self.assertIn("FileExistsError", sink.failures[0]["why"])

    def test_nothing_a_diagnostic_does_raises_an_exception_and_each_fault_is_a_counted_mark(self):
        sink = self.sink()
        spec = spec_of()
        def unreadable():
            raise RuntimeError("no journal")
        faults = (("a context that cannot be read", unreadable, self.at),
                  ("a context without its keys", {"origin": "proof"}, self.at),
                  ("a revision that is not one", self.ctx(spec), None))
        for name, ctx, at in faults:
            with self.subTest(fault=name):
                before = sink.not_written
                sink.note(ctx, spec, at, make_probe(None)(), refuted())
                self.assertEqual(sink.not_written, before + 1)
        self.assertEqual(len(sink.failures), 3)
        self.assertTrue(all(f["why"] and f["spec_id"] == spec.id for f in sink.failures))

    def test_a_write_that_fails_after_the_sibling_was_made_leaves_it_counted_and_unlisted(self):
        def full_disk(*args, **kw):
            raise OSError(28, "No space left on device")
        with mock.patch.object(D, "os", FailingOs(replace=full_disk)):
            sink, record = self.see(refuted())
        self.assertEqual(record.result, run_probe(make_probe(refuted())(), spec_of(), self.at, self.env).result)
        self.assertEqual((sink.written, sink.not_written, sink.dropped), (0, 1, 0))
        self.assertIn("No space left on device", sink.failures[0]["why"])
        self.assertEqual([p.name for p in self.folder.iterdir()], ["S1.1.p1.json.tmp"])      # nothing removed
        self.assertEqual(self.docs(), [])
        problems, notes = D.artifact_problems(self.out, [], {"diagnostics": sink.report()})
        self.assertEqual(problems, [])      # the failed write is the diagnostic's own fault, not the run's
        self.assertTrue(any("S1.1.p1.json.tmp" in n and "failed write" in n for n in notes), notes)

    def test_a_failure_to_write_is_named_and_leaves_the_probes_answer_alone(self):
        self.folder.write_text("a file where the directory goes", encoding="utf-8")
        answer = refuted()
        sink = self.sink()
        spec = spec_of()
        got = D.tapped(make_probe(answer), sink, self.ctx(spec))().observe(spec, self.at, self.env)
        self.assertIs(got, answer)
        self.assertEqual((sink.written, sink.not_written), (0, 1))
        self.assertRegex(sink.failures[0]["why"], "FileExistsError|NotADirectoryError")
        self.assertEqual(sink.report()["not_written"], 1)

    def test_the_failures_named_are_bounded_and_the_count_is_whole(self):
        sink = self.sink()
        for _ in range(D.FAILURES_MAX + 5):
            sink.note({}, spec_of(), self.at, make_probe(None)(), refuted())
        self.assertEqual((sink.not_written, len(sink.failures)), (D.FAILURES_MAX + 5, D.FAILURES_MAX))

    def test_the_report_states_where_for_whom_and_how_it_is_limited(self):
        sink = self.sink(access=D.SESSIONS_CONFINED)
        r = sink.report()
        self.assertEqual((r["dir"], r["audience"], r["access"]), ("probe-observations", "operator", D.SESSIONS_CONFINED))
        self.assertEqual((r["written"], r["not_written"], r["dropped"], r["failures"]), (0, 0, 0, []))
        self.assertTrue(r["authority"].startswith("none: no delivery verdict, retry, budget, merge or route"))
        self.assertIn("--verify", r["authority"])      # it says who does read them: the verification, by the journal
        self.assertIn(("directory 0700, files 0600" if os.name == "posix" else "platform default"), r["permissions"])

    def test_on_a_non_posix_host_the_permissions_statement_still_names_that_modes_are_not_applied(self):
        # RUN.json's diagnostics.permissions is a disclosure: on a host without file modes it must SAY so,
        # never go blank, or the operator cannot tell that 0700/0600 are unenforced there. PERMISSIONS is
        # fixed at import from os.name, so re-evaluate the non-POSIX branch here on this POSIX host.
        import importlib
        with mock.patch.object(os, "name", "nt"):
            importlib.reload(D)
        try:
            self.assertEqual(D.PERMISSIONS, "platform default (modes are not applied)")
            self.assertEqual(self.sink().report()["permissions"], "platform default (modes are not applied)")
        finally:
            importlib.reload(D)      # restore to the real os.name for the rest of the suite
        # the restore pins the host's own branch — on a real non-POSIX host that IS the branch under test
        self.assertEqual(D.PERMISSIONS, "directory 0700, files 0600" if os.name == "posix"
                         else "platform default (modes are not applied)")


class TheStatementOfWhoCanRead(Scratch):
    """`access_of`: from the command line `confine.wrap` builds for a session (the same function a session's wrapper
    comes from), on a host the wrapper accepts — the case that it needs Linux is a `system` argument here."""

    def setUp(self) -> None:
        super().setUp()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.exe = str(self.bin / "opencode")
        pathlib.Path(self.exe).write_text("#!/bin/sh\n")
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.env_ = {"HOME": str(self.home), "PATH": "/usr/bin"}
        self.other = self.tmp / "operator-input"
        self.other.mkdir()

    def spec(self, *read_only, bwrap=None) -> dict:
        return {"backend": "bwrap", "bwrap": bwrap or sys.executable, "network": "host", "read_only": list(read_only)}

    def access(self, confinement, system="linux") -> str:
        return D.access_of(self.folder, confinement, self.env_, self.exe, system)

    def test_without_confinement_it_is_the_same_user_and_not_enforced(self):
        self.assertEqual(self.access(None), "same-user, not enforced")

    def test_confined_it_is_the_sandbox_s_mounts_that_say_the_directory_is_not_in_them(self):
        self.assertEqual(self.access(self.spec(str(self.other))), D.SESSIONS_CONFINED)
        full, _ = confine.wrap(self.spec(str(self.other)), ["true"], self.env_, str(self.out / "work" / "ws"), self.exe,
                               system="linux")
        mounted = confine.targets(full, host=True)
        self.assertNotIn(str(self.folder), mounted)
        self.assertFalse([m for m in mounted if str(self.folder).startswith(m.rstrip("/") + "/")], mounted)

    @unittest.skipUnless(os.name == "posix", "models Linux bind/tmpfs paths: access_of realpaths the folder on the "
                                             "HOST, and Windows drive-anchors '/tmp/...'")
    def test_a_sandbox_made_mount_over_the_run_directory_is_not_a_host_mount(self):
        # The run directory sits under /tmp. A confined session gets a FRESH --tmpfs at /tmp
        # (sandbox-made, empty), not the host's /tmp: it exposes nothing of the directory, so the
        # statement must stay SESSIONS_CONFINED. access_of lists only the HOST's binds
        # (confine.targets host=True); reading --tmpfs/--proc/--dev as host mounts would wrongly
        # claim SAME_USER for a directory a session cannot in fact read.
        folder = "/tmp/aisef-run-under-a-tmpfs.0.p0"           # need not exist: realpath + prefix compare only
        full, _ = confine.wrap(self.spec(str(self.other)), ["true"], self.env_,
                               str(pathlib.Path(folder) / "work" / "ws"), self.exe, system="linux")
        self.assertNotIn("/tmp", confine.targets(full, host=True))     # /tmp is not a host bind
        self.assertIn("/tmp", confine.targets(full, host=False))       # it is a sandbox-made tmpfs
        self.assertEqual(D.access_of(folder, self.spec(str(self.other)), self.env_, self.exe, "linux"),
                         D.SESSIONS_CONFINED)

    def test_a_directory_the_sandbox_mounts_or_one_that_holds_it_is_the_same_user_again(self):
        self.folder.mkdir()
        for held in (str(self.out), str(self.tmp), str(self.folder)):
            with self.subTest(read_only=held):
                self.assertEqual(self.access(self.spec(held)), D.SAME_USER)

    @unittest.skipUnless(os.name == "posix", "a symbolic link needs no privilege here")
    def test_a_link_to_a_parent_of_the_run_directory_is_followed(self):
        link = self.tmp / "link"
        link.symlink_to(self.tmp)
        self.assertEqual(self.access(self.spec(str(link))), D.SAME_USER)

    def test_what_cannot_be_shown_is_not_claimed(self):
        self.assertEqual(self.access(self.spec(str(self.other)), system="darwin"), D.NOT_INSPECTED)    # no backend here
        self.assertEqual(self.access(self.spec(str(self.other), bwrap=str(self.tmp / "no-bwrap"))), D.NOT_INSPECTED)
        self.assertEqual(self.access(self.spec(str(self.tmp / "absent"))), D.NOT_INSPECTED)             # a path not there
        self.assertEqual(self.access("not a settings document"), D.NOT_INSPECTED)
        self.assertTrue(D.NOT_INSPECTED.startswith(D.SAME_USER))      # as little as the plain statement says

    def test_not_inspected_is_told_apart_from_no_confinement(self):
        # The operator reads diagnostics.access (RUN.json) and each artifact's diagnostics_access:
        # 'confinement asked for but its sandbox could not be inspected' must not read as the
        # 'no confinement requested' statement, and it must say why it is only the weaker claim.
        not_inspected = self.access(self.spec(str(self.other)), system="darwin")  # no bwrap backend here
        self.assertNotEqual(not_inspected, self.access(None))        # distinct from plain same-user
        self.assertTrue(not_inspected.startswith(D.SAME_USER))       # claims no more than SAME_USER
        self.assertIn("inspect", not_inspected)                       # and states it could not be inspected

    def test_the_statements_make_no_claim_that_nobody_can_read_it(self):
        for text in (D.SAME_USER, D.NOT_INSPECTED, D.SESSIONS_CONFINED, D.AUTHORITY, D.PERMISSIONS):
            self.assertIsNone(re.search(r"cannot (be )?read|not readable|unreadable|inaccessible", text, re.I), text)
        self.assertIn("not enforced", D.SESSIONS_CONFINED)      # the kernel's own execution of the developer's code
        self.assertIn("operator's user", D.SESSIONS_CONFINED)


class WhatVerifyChecks(Scratch):
    RESULT = {"behavior_verdict": "REFUTED", "reason": None}

    def doc(self, **kw) -> dict:
        d = {"format": D.ARTIFACT_FORMAT, "origin": "proof", "story_id": "S1", "attempt": 1, "index": 1, "spec_id": "PPS-a",
             "probe_id": "probe.fake", "probe_digest": "d" * 64, "revision": SHA, "enforcement": "PARTIAL",
             "result": dict(self.RESULT)}
        d.update(kw)
        return d

    def put(self, name: str, doc) -> None:
        self.folder.mkdir(exist_ok=True)
        (self.folder / name).write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")

    def journal(self, **changed) -> list:
        record = {"record_digest": "r" * 64, "semantic_hash": "h" * 64, "spec_id": "PPS-a", "probe_id": "probe.fake",
                  "probe_digest": "d" * 64, "revision": SHA, "enforcement": "PARTIAL", "result": dict(self.RESULT)}
        return [{"seq": 1, "type": "probe/evaluated", "data": {"story_id": "S1", "criterion_id": "C-1",
                                                                "record": {**record, **changed}}}]

    def check(self, events=None, rec=None):
        return D.artifact_problems(self.out, self.journal() if events is None else events, rec or {})

    def test_a_file_bound_to_its_row_is_no_problem(self):
        self.put("S1.1.p1.json", self.doc())
        self.assertEqual(self.check(), ([], []))

    def test_a_directory_that_is_not_there_is_no_problem(self):
        self.assertEqual(self.check(), ([], []))

    def test_each_way_a_file_is_not_this_releases_is_a_problem_naming_it(self):
        self.put("not-a-name.json", self.doc())
        self.put("S1.1.p2.json", "{ not json")
        self.put("S1.1.p3.json", self.doc(format="aisef-v2-probe-observation/0", index=3))
        self.put("S1.1.p4.json", self.doc(origin="elsewhere", index=4))
        self.put("S1.1.p5.json", self.doc(index=7))      # named for its content: no
        problems, _ = self.check()
        for needle in ("not-a-name.json is not a file this release writes", "S1.1.p2.json is not a probe observation",
                       "S1.1.p3.json is not a probe observation", "S1.1.p4.json is not a probe observation",
                       "S1.1.p5.json is not named for its story, attempt and place"):
            self.assertTrue(any(needle in p for p in problems), (needle, problems))

    def test_a_record_the_journal_does_not_hold_for_that_story_spec_and_revision_is_a_problem(self):
        self.put("S1.1.p1.json", self.doc())
        for events in (self.journal(spec_id="PPS-b"), self.journal(revision="f" * 40), self.journal(probe_id="probe.x"),
                       self.journal(probe_digest="0" * 64), self.journal(enforcement="FULL"),
                       self.journal(result={"behavior_verdict": "SATISFIED", "reason": None})):
            with self.subTest(events=events[0]["data"]["record"]):
                problems, _ = self.check(events)
                self.assertEqual(len(problems), 1)
                self.assertIn("names a probe record", problems[0])
        other_story = self.journal()
        other_story[0]["data"]["story_id"] = "S2"
        self.assertEqual(len(self.check(other_story)[0]), 1)

    def test_a_run_that_broke_may_hold_an_observation_it_never_journaled_and_that_is_a_note(self):
        self.put("S1.1.p1.json", self.doc())
        problems, notes = self.check(self.journal(spec_id="PPS-b"), {"failure": {"type": "KeyboardInterrupt"}})
        self.assertEqual(problems, [])
        self.assertTrue(any("the run broke" in n for n in notes), notes)

    def test_with_no_journal_re_derived_the_record_is_not_checked_and_that_is_a_note(self):
        self.put("S1.1.p1.json", self.doc())
        problems, notes = self.check([])
        self.assertEqual(problems, [])
        self.assertTrue(any("not re-derived" in n for n in notes), notes)

    def test_the_count_the_record_states_must_be_the_directory_s(self):
        self.put("S1.1.p1.json", self.doc())
        problems, _ = self.check(rec={"diagnostics": {"written": 2}})
        self.assertEqual(problems, ["RUN.json states 2 written, the directory holds 1"])
        self.assertEqual(self.check(rec={"diagnostics": {"written": 1}}), ([], []))
        problems, notes = self.check(rec={"diagnostics": {"written": 2}, "failure": {"type": "RuntimeError"}})
        self.assertEqual((problems, len(notes)), ([], 1))

    def test_what_was_not_written_or_dropped_is_a_note_never_a_problem(self):
        problems, notes = self.check(rec={"diagnostics": {"written": 0, "not_written": 3, "dropped": 2}})
        self.assertEqual(problems, [])
        self.assertEqual(len(notes), 2)
        self.assertIn("3 probe observation(s) could not be written", notes[0])
        self.assertIn("2 probe observation(s) were not kept", notes[1])

    def test_a_review_file_is_bound_to_the_finding_at_its_place_in_review_findings(self):
        self.put("S1.1.r0.json", self.doc(origin="review", index=0, finding="F1"))
        problems, notes = self.check()      # no artifact of the finding was kept (preserve failed: the journal says so)
        self.assertEqual(problems, [])
        self.assertEqual(len(notes), 1)
        self.assertIn("the artifact of the finding it observes was not kept (review-findings/S1.1.0.json)", notes[0])
        kept = self.out / "review-findings"
        kept.mkdir()
        (kept / "S1.1.0.json").write_text(json.dumps({"finding": {"id": "F1"}}), encoding="utf-8")
        self.assertEqual(self.check(), ([], []))
        (kept / "S1.1.0.json").write_text(json.dumps({"finding": {"id": "F2"}}), encoding="utf-8")
        problems, _ = self.check()
        self.assertEqual(len(problems), 1)
        self.assertIn("the finding it observes is not at review-findings/S1.1.0.json", problems[0])
        (kept / "S1.1.0.json").write_text("[]", encoding="utf-8")      # a document that is not an object
        self.assertEqual(len(self.check()[0]), 1)


    def test_the_finding_is_compared_as_the_text_the_gate_row_carries_whatever_json_it_is_in_its_file(self):
        for stored, shown in ((5, "5"), (1.5, "1.5"), (None, "None"), (True, "True"), ([1, 2], "[1, 2]"), ("F1", "F1")):
            with self.subTest(stored=stored):
                self.fresh()
                self.put("S1.1.r0.json", self.doc(origin="review", index=0, finding=shown))
                (self.out / "review-findings").mkdir()
                (self.out / "review-findings" / "S1.1.0.json").write_text(json.dumps({"finding": {"id": stored}}),
                                                                         encoding="utf-8")
                self.assertEqual(self.check(), ([], []))
        self.fresh()      # a finding with no id at all is the text "None" — the gate row's too
        self.put("S1.1.r0.json", self.doc(origin="review", index=0, finding="None"))
        (self.out / "review-findings").mkdir()
        (self.out / "review-findings" / "S1.1.0.json").write_text(json.dumps({"finding": {"summary": "s"}}), encoding="utf-8")
        self.assertEqual(self.check(), ([], []))
        # and another finding is still another: 5 is not "6", and an artifact that cannot be read binds nothing
        for body in ('{"finding": {"id": 6}}', '{ not json', '{"finding": "F"}'):
            with self.subTest(body=body):
                (self.out / "review-findings" / "S1.1.0.json").write_text(body, encoding="utf-8")
                self.put("S1.1.r0.json", self.doc(origin="review", index=0, finding="5"))
                self.assertEqual(len(self.check()[0]), 1)

    def test_a_sibling_a_failed_write_left_is_a_note_and_any_other_name_is_still_a_problem(self):
        self.put("S1.1.p1.json.tmp", '{"half')
        self.put("stray.json.tmp", "x")
        self.put("S1.1.p2.json.tmp.tmp", "x")
        self.put("S1.1.p3.tmp", "x")
        problems, notes = self.check(rec={"diagnostics": {"written": 0, "not_written": 1}})
        self.assertEqual(len(problems), 3, problems)
        for stray in ("stray.json.tmp", "S1.1.p2.json.tmp.tmp", "S1.1.p3.tmp"):
            self.assertTrue(any(f"{stray} is not a file this release writes" in p for p in problems), (stray, problems))
        self.assertEqual(len([n for n in notes if "S1.1.p1.json.tmp" in n]), 1, notes)
        self.assertIn("a failed write", [n for n in notes if "S1.1.p1.json.tmp" in n][0])

    def test_a_valid_name_with_a_non_tmp_tail_is_a_foreign_file_not_a_leftover(self):
        # the `.tmp` leftover note is only for a real failed-write sibling (`<name>.json.tmp`); a valid
        # stem with any OTHER 4-char tail is a file this release never writes -> a problem (verify REFUTES),
        # never swallowed as a benign leftover
        self.put("S1.1.p1.json.bak", "x")
        problems, notes = self.check()
        self.assertTrue(any("S1.1.p1.json.bak is not a file this release writes" in p for p in problems), problems)
        self.assertFalse(any("S1.1.p1.json.bak" in n for n in notes), notes)


class TheContextTheRunGives(unittest.TestCase):
    def setUp(self) -> None:
        self.project = bundle.load(e2e.project_bundle("a" * 40))
        self.events = [types.SimpleNamespace(type="story/begin", data={"story_id": "S0", "parent": "0" * 40}),
                       types.SimpleNamespace(type="story/admitted", data={"story_id": "S0", "parent": "0" * 40}),
                       types.SimpleNamespace(type="story/begin", data={"story_id": "S1", "parent": "1" * 40}),
                       types.SimpleNamespace(type="story/admitted", data={"story_id": "S1", "parent": "1" * 40}),
                       types.SimpleNamespace(type="story/begin", data={"story_id": "S1", "parent": "2" * 40})]
        self.run = types.SimpleNamespace(events=self.events, state=lambda p: {"S1": {"attempt": 2}}
                                         if p is ControlProjection.STORY_STATE else None)

    def test_it_is_read_when_the_observation_is_made_the_attempt_the_parent_and_the_plan_s_facts(self):
        spec_id = next(iter(self.project.plan.obligations)).product_proof_spec_id
        where = R.story_where(self.run, self.project, "S1")
        self.assertEqual(where(), {"origin": "proof", "story_id": "S1", "attempt": 2, "parent": "2" * 40,
                                   "introduces": frozenset({spec_id}), "verifies": frozenset(), "admitted": False,
                                   "criteria": {spec_id: ["C-ADD"]}})
        self.events.append(types.SimpleNamespace(type="story/begin", data={"story_id": "S1", "parent": "3" * 40}))
        self.assertEqual(where()["parent"], "3" * 40)       # the latest attempt's: read now, not when the story began

    def test_admission_is_over_when_the_journal_holds_this_attempt_s_story_admitted(self):
        where = R.story_where(self.run, self.project, "S1")
        self.assertFalse(where()["admitted"])      # attempt 2 began after attempt 1's `story/admitted`: not that one
        self.events.append(types.SimpleNamespace(type="story/admitted", data={"story_id": "S2", "parent": "2" * 40}))
        self.assertFalse(where()["admitted"])      # another story's is not this story's
        self.events.append(types.SimpleNamespace(type="story/admitted", data={"story_id": "S1", "parent": "2" * 40}))
        self.assertTrue(where()["admitted"])
        self.events.append(types.SimpleNamespace(type="story/begin", data={"story_id": "S1", "parent": "3" * 40}))
        self.assertFalse(where()["admitted"])      # a retry admits again

    def test_the_specs_a_story_only_verifies_are_named_apart_from_those_it_introduces(self):
        from aisef2.arch.enums import ObligationRole
        mine = [o for o in self.project.plan.obligations if o.story_id == "S1"]
        spec_id = mine[0].product_proof_spec_id
        verifying = [types.SimpleNamespace(story_id="S1", role=ObligationRole.VERIFY, product_proof_spec_id=spec_id,
                                           criterion_id="C-V"),
                     types.SimpleNamespace(story_id="S2", role=ObligationRole.VERIFY, product_proof_spec_id="PPS-other",
                                           criterion_id="C-O")]
        project = types.SimpleNamespace(plan=types.SimpleNamespace(obligations=verifying))
        got = R.story_where(self.run, project, "S1")()
        self.assertEqual((got["introduces"], got["verifies"], got["criteria"]),
                         (frozenset(), frozenset({spec_id}), {spec_id: ["C-V"]}))

    def test_a_story_the_journal_has_not_begun_has_no_parent_yet(self):
        where = R.story_where(types.SimpleNamespace(events=[], state=self.run.state), self.project, "S1")
        self.assertIsNone(where()["parent"])


class NothingDecidesFromIt(unittest.TestCase):
    """The structure that gives the channel no authority (decision PM-8: 'không tạo thêm thẩm quyền')."""

    APP = ROOT / "aisef2" / "app"
    DECIDING = ("orchestrate", "control", "journal", "plan", "probe", "product", "runtime", "quality", "cohort",
                "invariants", "arch")

    @staticmethod
    def imports(path: pathlib.Path) -> set[str]:
        out = set()
        for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(n, ast.ImportFrom) and n.module:
                out |= {f"{n.module}.{a.name}" for a in n.names} | {n.module}
            elif isinstance(n, ast.Import):
                out |= {a.name for a in n.names}
        return out

    def test_the_module_imports_no_module_that_decides(self):
        allowed = {"__future__", "dataclasses", "json", "os", "pathlib", "re", "sys", "typing",
                   "aisef2.app", "aisef2.app.confine", "aisef2.app.review_verify", "aisef2.arch.enums",
                   "aisef2.probe", "aisef2.probe.catalog", "aisef2.probe.protocol", "aisef2.product.contract",
                   "aisef2.product.outcome"}
        seen = self.imports(self.APP / "diagnostics.py")
        extra = {i for i in seen if not any(i == a or i.startswith(a + ".") for a in allowed)}
        self.assertEqual(extra, set())
        for deciding in ("orchestrate", "control", "journal", "plan", "runtime", "invariants", "cohort"):
            self.assertFalse([i for i in seen if i.startswith(f"aisef2.{deciding}")], deciding)

    def test_only_the_run_the_review_and_the_verification_name_the_directory_or_the_module(self):
        pattern = re.compile(r"probe-observations|app import [^\n]*\bdiagnostics\b|app\.diagnostics|diagnostics\.ARTIFACT_DIR")
        named = {p.relative_to(ROOT).as_posix() for p in (ROOT / "aisef2").rglob("*.py")
                 if pattern.search(p.read_text(encoding="utf-8"))}
        # review_verify.py and adapters.py speak of it in prose only (verify's docstring, Reviewer's) and import
        # nothing of it: the sink arrives as an argument, and its probes' entries as a parameter
        self.assertEqual(named, {"aisef2/app/diagnostics.py", "aisef2/app/run.py", "aisef2/app/verify.py"})
        for rel in ("aisef2/app/review_verify.py", "aisef2/app/adapters.py"):
            self.assertNotIn("diagnostics import", (ROOT / rel).read_text(encoding="utf-8"))
            self.assertFalse([i for i in self.imports(ROOT / rel) if "diagnostics" in i], rel)

    def test_no_module_that_decides_or_that_builds_what_a_model_is_told_names_it(self):
        for rel in sorted(p.relative_to(ROOT).as_posix() for sub in self.DECIDING for p in (ROOT / "aisef2" / sub).rglob("*.py")):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"probe-observations|app\.diagnostics|import diagnostics", rel)
        for rel in ("feedback.py", "client.py", "review_ocr.py", "preflight.py", "lineage.py", "usage.py", "bundle.py",
                    "bundle_cli.py", "settings.py", "confine.py", "cli.py"):
            text = (self.APP / rel).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"probe-observations|app\.diagnostics|\bdiagnostics\b", rel)

    def test_the_developer_class_and_the_prompt_constants_do_not_name_it(self):
        tree = ast.parse((self.APP / "adapters.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name != "Reviewer" or isinstance(node, (ast.Assign, ast.FunctionDef)):
                text = ast.unparse(node)
                self.assertNotIn("diagnostics", text, getattr(node, "name", "module constant"))
                self.assertNotIn("probe-observations", text)
        reviewer = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Reviewer")
        named = {f"{m.name}" for m in reviewer.body if isinstance(m, ast.FunctionDef) and "diagnostics" in ast.unparse(m)}
        self.assertEqual(named, {"__init__", "_verify"})      # the sink is held, and handed the probes' entries

    def test_the_prompt_builders_read_no_file(self):
        from aisef2.app import feedback
        tree = ast.parse(pathlib.Path(feedback.__file__).read_text(encoding="utf-8"))
        reads = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                 and n.attr in {"read_text", "read_bytes", "open", "glob", "rglob", "iterdir", "listdir", "walk", "scandir"}}
        calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertEqual((reads, calls & {"open", "Path"}), (set(), set()))
        for name in ("task", "clauses", "retry_feedback", "context_pack"):
            self.assertNotIn("pathlib", ast.unparse(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)))

    def test_the_sink_has_no_way_to_read_a_file_back(self):
        tree = ast.parse((self.APP / "diagnostics.py").read_text(encoding="utf-8"))
        sink = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Sink")
        text = ast.unparse(sink)
        for banned in ("read_text", "read_bytes", "json.load", ".glob(", "iterdir", "listdir", "scandir"):
            self.assertNotIn(banned, text, banned)
        calls = [n for n in ast.walk(sink) if isinstance(n, ast.Call)]
        self.assertFalse([c for c in calls if isinstance(c.func, ast.Name) and c.func.id == "open"])
        for c in (c for c in calls if ast.unparse(c.func) == "os.open"):      # the one open there is is the writing one
            self.assertIn("O_WRONLY", ast.unparse(c))
            self.assertNotIn("O_RDONLY", ast.unparse(c))
        self.assertEqual({m.name for m in sink.body if isinstance(m, ast.FunctionDef) and not m.name.startswith("_")},
                         {"note", "entries", "report"})

    @unittest.skipUnless((ROOT / "validation/qualification/authority_limits.py").exists(),
                         "validation/qualification is not in this tree (the mutation runner's copy); the suite runs it")
    def test_what_verify_reaches_never_writes_or_names_the_sink(self):
        from validation.qualification import authority_limits as al
        self.assertEqual(al.check(), [])
        mods = al._modules(al.ROOT, {})
        index = {f"{al.opa._module_name(rel)}.{name}": (rel, node) for rel, m in mods.items() for name, node in m.defs}
        reached = {q for q, _, _ in al._closure(mods, index, (al.VERIFY,))}
        self.assertIn(al.VERIFY, reached)
        self.assertFalse([q for q in reached if q.startswith("aisef2.app.diagnostics")], reached)
        self.assertNotIn("aisef2.app.adapters.Reviewer.review", reached)
        # the probes' entries come in as a parameter: verify names no sink and writes no file
        src = (self.APP / "review_verify.py").read_text(encoding="utf-8")
        verify_src = src[src.index("def verify("):src.index("class Anchor")]
        self.assertNotIn("diagnostics", verify_src.split('"""', 2)[2])      # code, not the docstring
        self.assertNotRegex(verify_src.split('"""', 2)[2], r"open\(|write|\.note\(|Sink")


if __name__ == "__main__":
    unittest.main()
