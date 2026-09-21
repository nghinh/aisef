"""WP-1.2 — ProductProofSpec and the pure contract -> spec compiler (RFC §8, §35; F4, F9).

Semantic tests only: this module is the kill set for the compiler's mutation targets, so nothing here compares
against committed specs (compiler_digest addresses the compiler's own source; see validation/v2/mutation.py).
"""

import dataclasses
import json
import os
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import BehaviorVerdict, Polarity, SubjectAbsence, SubjectKind  # noqa: E402
from aisef2.product.approval import ContractApproval, Requirement, UnapprovedContract  # noqa: E402
from aisef2.product.compiler import (  # noqa: E402
    COMPILER_DIGEST, COMPILER_ID, CompileError, ProbeRef, compile_spec, expectation_for,
)
from aisef2.product.contract import BehaviorContract, ContractError, Subject, content_of, digest  # noqa: E402
from aisef2.product.spec import SPEC_PREFIX, ProductProofSpec, semantic_hash, spec_id  # noqa: E402

REQ = Requirement.create(id="REQ-1", text="quiet mode prints nothing", source="docs/req.md")
PROBES = {SubjectKind.CLI_INVOCATION: ProbeRef("probe.cli", "c" * 64),
          SubjectKind.PYTHON_CALLABLE: ProbeRef("probe.py", "p" * 64)}
BASE = dict(id="BC-1", requirement_ids=("REQ-1",), subject=Subject(SubjectKind.CLI_INVOCATION, "app.cli:main"),
            stimulus={"argv": ["--quiet"]}, observable={"stream": "stdout", "condition": "non_empty"},
            polarity=Polarity.MUST_NOT_HOLD, subject_absence=SubjectAbsence.REQUIRES_SUBJECT, rationale="NEG-1")


def contract(**over):
    return BehaviorContract.create(**{**BASE, **over})


def approved(c):
    return [ContractApproval(REQ.id, REQ.requirement_hash, c.id, c.contract_hash, "human:owner", 1.0, ())]


def compile_(c=None, probes=PROBES, **over):
    c = c or contract(**over)
    return compile_spec(c, requirements={REQ.id: REQ}, approvals=approved(c), probes=probes)


class Shape(unittest.TestCase):
    def test_fields_are_exactly_the_rfc_fields(self):
        self.assertEqual([f.name for f in dataclasses.fields(ProductProofSpec)],
                         ["id", "contract_id", "probe_id", "probe_digest", "probe_input", "candidate_expectation",
                          "compiler_id", "compiler_digest", "semantic_hash"])

    def test_no_plan_fact_can_be_attached(self):
        spec = compile_()
        for field in ("story_id", "plan_id", "expected_parent", "parent_expectation"):
            with self.subTest(field=field):
                with self.assertRaises(TypeError):
                    dataclasses.replace(spec, **{field: "x"})
                with self.assertRaises((AttributeError, TypeError)):
                    setattr(spec, field, "x")

    def test_a_spec_is_verified_on_construction(self):
        spec = compile_()
        good = {f.name: getattr(spec, f.name) for f in dataclasses.fields(spec)}
        for field, value in (("semantic_hash", "0" * 64), ("id", "PPS-" + "0" * 64),
                             ("candidate_expectation", BehaviorVerdict.INDETERMINATE),
                             ("probe_input", {**spec.probe_input, "story": "S-1"})):
            with self.subTest(field=field), self.assertRaises(ContractError):
                ProductProofSpec(**{**good, field: value})
        self.assertEqual(ProductProofSpec(**good), spec)

    def test_round_trip_through_json(self):
        spec = compile_()
        self.assertEqual(ProductProofSpec.from_json(json.loads(json.dumps(spec.to_json()))), spec)


class Compile(unittest.TestCase):
    def test_expectation_follows_polarity(self):
        self.assertIs(expectation_for(Polarity.MUST_HOLD), BehaviorVerdict.SATISFIED)
        self.assertIs(expectation_for(Polarity.MUST_NOT_HOLD), BehaviorVerdict.REFUTED)
        self.assertIs(compile_(polarity=Polarity.MUST_HOLD).candidate_expectation, BehaviorVerdict.SATISFIED)
        self.assertIs(compile_(polarity=Polarity.MUST_NOT_HOLD).candidate_expectation, BehaviorVerdict.REFUTED)
        with self.assertRaisesRegex(CompileError, "^no candidate expectation for polarity 'MUST_HOLD'$"):
            expectation_for("MUST_HOLD")

    def test_an_unapproved_contract_cannot_be_compiled(self):
        c = contract()
        with self.assertRaises(UnapprovedContract):
            compile_spec(c, requirements={REQ.id: REQ}, approvals=[], probes=PROBES)
        with self.assertRaises(UnapprovedContract):
            compile_spec(contract(rationale="edited"), requirements={REQ.id: REQ}, approvals=approved(c), probes=PROBES)

    def test_a_subject_kind_without_a_probe_is_refused(self):
        with self.assertRaisesRegex(CompileError, "^no probe declared for subject kind file_artifact$"):
            compile_(subject=Subject(SubjectKind.FILE_ARTIFACT, "LICENSE"))

    def test_the_spec_carries_the_contract_semantics_and_the_probe_identity(self):
        c = contract()
        spec = compile_(c)
        self.assertEqual(spec.contract_id, c.id)
        self.assertEqual((spec.probe_id, spec.probe_digest), ("probe.cli", "c" * 64))
        self.assertEqual(json.loads(json.dumps(spec.to_json()["probe_input"])), {
            "subject": {"kind": "cli_invocation", "locator": "app.cli:main"}, "stimulus": {"argv": ["--quiet"]},
            "observable": {"condition": "non_empty", "stream": "stdout"}, "subject_absence": "REQUIRES_SUBJECT"})
        self.assertEqual((spec.compiler_id, spec.compiler_digest), (COMPILER_ID, COMPILER_DIGEST))
        self.assertRegex(COMPILER_DIGEST, r"^[0-9a-f]{64}$")

    def test_compile_is_pure(self):
        c = contract()
        before = c.to_json()
        self.assertEqual(compile_(c), compile_(c))
        self.assertEqual(c.to_json(), before)

    def test_compile_is_deterministic_across_processes(self):
        code = ("import sys, json; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2]);"
                "import test_spec_compiler as t; print(json.dumps(t.compile_().to_json(), sort_keys=True))")
        seen = set()
        for seed in ("0", "7", "31337"):
            r = subprocess.run([sys.executable, "-I", "-c", code, str(ROOT), str(pathlib.Path(__file__).parent)],
                               capture_output=True, encoding="utf-8", env={**os.environ, "PYTHONHASHSEED": seed},
                               check=True)
            seen.add(r.stdout.strip())
        self.assertEqual(seen, {json.dumps(compile_().to_json(), sort_keys=True)})


class SemanticHash(unittest.TestCase):
    def test_it_is_the_documented_digest(self):
        spec = compile_()
        self.assertEqual(spec.semantic_hash, semantic_hash(spec))
        self.assertEqual(spec.semantic_hash, digest({"probe_id": spec.probe_id, "probe_digest": spec.probe_digest,
                                                     "probe_input": spec.probe_input,
                                                     "candidate_expectation": spec.candidate_expectation}))
        self.assertEqual(spec.id, SPEC_PREFIX + digest(content_of(spec, without="id")))
        self.assertEqual(spec.id, spec_id(spec))

    def test_every_semantic_change_changes_it(self):
        base = compile_().semantic_hash
        changes = {"subject locator": dict(subject=Subject(SubjectKind.CLI_INVOCATION, "app.cli:other")),
                   "subject kind": dict(subject=Subject(SubjectKind.PYTHON_CALLABLE, "app.cli:main")),
                   "stimulus": dict(stimulus={"argv": ["--loud"]}),
                   "observable": dict(observable={"stream": "stderr", "condition": "non_empty"}),
                   "polarity": dict(polarity=Polarity.MUST_HOLD),
                   "subject_absence": dict(subject_absence=SubjectAbsence.ABSENCE_IS_DECIDABLE)}
        for name, over in changes.items():
            with self.subTest(change=name):
                self.assertNotEqual(compile_(**over).semantic_hash, base)
        for name, probes in (("probe id", {**PROBES, SubjectKind.CLI_INVOCATION: ProbeRef("probe.cli2", "c" * 64)}),
                             ("probe digest", {**PROBES, SubjectKind.CLI_INVOCATION: ProbeRef("probe.cli", "d" * 64)})):
            with self.subTest(change=name):
                self.assertNotEqual(compile_(probes=probes).semantic_hash, base)

    def test_prose_and_ids_do_not_change_what_was_proved(self):
        base = compile_()
        for over in (dict(rationale="reworded"), dict(id="BC-OTHER")):
            with self.subTest(change=list(over)):
                other = compile_(**over)
                self.assertEqual(other.semantic_hash, base.semantic_hash)
        self.assertNotEqual(compile_(id="BC-OTHER").id, base.id)

    def test_compiler_identity_changes_the_spec_id_but_not_the_semantic_hash(self):
        spec = compile_()
        moved = ProductProofSpec.create(**{**{f.name: getattr(spec, f.name) for f in dataclasses.fields(spec)
                                              if f.name not in ("id", "semantic_hash")}, "compiler_digest": "e" * 64})
        self.assertEqual(moved.semantic_hash, spec.semantic_hash)
        self.assertNotEqual(moved.id, spec.id)


if __name__ == "__main__":
    unittest.main()
