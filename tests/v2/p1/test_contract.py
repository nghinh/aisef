"""WP-1.1 — BehaviorContract, Subject, SubjectAbsence, Requirement and ContractApproval (RFC §6, §7; F4).

Kill set for the `contract_hash` mutation target: these tests must fail when the identity stops binding a field.
"""

import dataclasses
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.arch.enums import Polarity, SubjectAbsence, SubjectKind  # noqa: E402
from aisef2.product.approval import (  # noqa: E402
    ContractApproval, Requirement, UnapprovedContract, binding_problems, require_approved,
)
from aisef2.product.contract import (  # noqa: E402
    BehaviorContract, ContractError, Subject, canonical, contract_hash, freeze,
)


def _module(name, rel):
    s = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


fc = _module("p1_fc", "validation/v2/freeze_conformance.py")
ks = _module("p1_ks", "validation/v2/kernel_static_checks.py")
RFC = fc.RFC((ROOT / fc.RFC_REL).read_text(encoding="utf-8"))

BASE = dict(id="BC-1", requirement_ids=("REQ-1",), subject=Subject(SubjectKind.CLI_INVOCATION, "app.cli:main"),
            stimulus={"argv": ["--quiet"], "env": {}}, observable={"stdout": "empty"},
            polarity=Polarity.MUST_NOT_HOLD, subject_absence=SubjectAbsence.REQUIRES_SUBJECT,
            rationale="the CLI MUST NOT write to stdout when --quiet is given")


def contract(**over):
    return BehaviorContract.create(**{**BASE, **over})


def requirement(**over):
    return Requirement.create(**{"id": "REQ-1", "text": "quiet mode prints nothing", "source": "docs/req.md@abc",
                                 **over})


def approve(req, c, approver="human:nghi"):
    return ContractApproval(req.id, req.requirement_hash, c.id, c.contract_hash, approver, 1.0, ())


class Shapes(unittest.TestCase):
    def test_fields_equal_the_rfc_in_order(self):
        for cls in (Requirement, ContractApproval, Subject, BehaviorContract):
            with self.subTest(cls=cls.__name__):
                self.assertEqual([f.name for f in dataclasses.fields(cls)], RFC.dataclasses[cls.__name__])

    def test_contract_data_is_immutable(self):
        c = contract()
        with self.assertRaises(TypeError):
            c.stimulus["argv"] = ["x"]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            c.polarity = Polarity.MUST_HOLD


class ContractHash(unittest.TestCase):
    def test_every_field_is_bound(self):
        c = contract()
        changed = {"id": "BC-2", "requirement_ids": ("REQ-1", "REQ-2"),
                   "subject": Subject(SubjectKind.CLI_INVOCATION, "app.cli:other"),
                   "stimulus": {"argv": ["--loud"], "env": {}}, "observable": {"stdout": "non-empty"},
                   "polarity": Polarity.MUST_HOLD, "subject_absence": SubjectAbsence.ABSENCE_IS_DECIDABLE,
                   "rationale": "reworded"}
        self.assertEqual(set(changed), {f.name for f in dataclasses.fields(BehaviorContract)} - {"contract_hash"})
        for field, value in changed.items():
            with self.subTest(field=field):
                self.assertNotEqual(contract(**{field: value}).contract_hash, c.contract_hash)

    def test_subject_kind_and_nested_values_are_bound(self):
        c = contract()
        self.assertNotEqual(contract(subject=Subject(SubjectKind.PYTHON_CALLABLE, "app.cli:main")).contract_hash,
                            c.contract_hash)
        self.assertNotEqual(contract(stimulus={"argv": ["--quiet"], "env": {"A": "1"}}).contract_hash, c.contract_hash)
        self.assertNotEqual(contract(stimulus={"argv": ["--quiet"], "env": {}, "x": None}).contract_hash,
                            c.contract_hash)

    def test_hash_is_the_documented_digest(self):
        c = contract()
        self.assertEqual(c.contract_hash, contract_hash(c))
        self.assertRegex(c.contract_hash, r"^[0-9a-f]{64}$")

    def test_editing_rationale_alone_is_detected(self):
        c = contract()
        with self.assertRaises(ContractError):
            dataclasses.replace(c, rationale="a different reading")
        self.assertNotEqual(contract(rationale="a different reading").contract_hash, c.contract_hash)

    def test_a_supplied_hash_is_verified_never_trusted(self):
        with self.assertRaises(ContractError):
            BehaviorContract(**BASE, contract_hash="0" * 64)

    def test_key_order_and_sequence_type_do_not_change_identity(self):
        a = contract(stimulus={"env": {}, "argv": ["--quiet"]})
        b = contract(stimulus={"argv": ("--quiet",), "env": {}}, requirement_ids=["REQ-1"])
        self.assertEqual(a.contract_hash, contract().contract_hash)
        self.assertEqual(b.contract_hash, contract().contract_hash)

    def test_round_trip_through_json_is_identity(self):
        c = contract()
        again = BehaviorContract.from_json(json.loads(json.dumps(c.to_json())))
        self.assertEqual(again, c)
        self.assertEqual(again.contract_hash, c.contract_hash)
        tampered = {**c.to_json(), "rationale": "edited on disk"}
        with self.assertRaises(ContractError):
            BehaviorContract.from_json(tampered)

    def test_hash_is_identical_across_processes(self):
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import json; "
                "from aisef2.product.contract import BehaviorContract; "
                "print(BehaviorContract.from_json(json.loads(sys.argv[2])).contract_hash)")
        payload = json.dumps(contract().to_json())
        seen = set()
        for seed in ("0", "1", "4242"):
            r = subprocess.run([sys.executable, "-I", "-c", code, str(ROOT), payload], capture_output=True,
                               encoding="utf-8", env={**os.environ, "PYTHONHASHSEED": seed}, check=True)
            seen.add(r.stdout.strip())
        self.assertEqual(seen, {contract().contract_hash})


class CanonicalForm(unittest.TestCase):
    """The identity is a digest of one exact text; each property below is load-bearing for that text."""

    def test_the_canonical_text_is_exact(self):
        self.assertEqual(canonical({"b": [1, 2.5, True, None], "a": "é"}), '{"a":"é","b":[1,2.5,true,null]}')

    def test_key_order_never_changes_the_text(self):
        self.assertEqual(canonical({"b": 1, "a": 2}), canonical({"a": 2, "b": 1}))

    def test_non_finite_numbers_have_no_canonical_form(self):
        for bad in (float("nan"), float("inf")):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    canonical(bad)
                with self.assertRaisesRegex(ContractError, "non-finite"):
                    freeze(bad)

    def test_json_scalars_are_accepted_and_anything_else_refused(self):
        self.assertEqual(freeze({"s": "x", "i": 3, "f": 1.5, "b": False, "n": None})["i"], 3)
        c = contract(stimulus={"timeout": 1.5, "retries": 2, "strict": True, "argv": ["--quiet"]})
        self.assertEqual((c.stimulus["timeout"], c.stimulus["retries"], c.stimulus["strict"]), (1.5, 2, True))
        with self.assertRaisesRegex(ContractError, "not JSON-shaped"):
            freeze({"x": {1, 2}})
        with self.assertRaisesRegex(ContractError, "keys must be strings"):
            freeze({1: "x"})

    def test_frozen_data_is_immutable_and_key_sorted(self):
        c = contract(stimulus={"env": {"B": "1", "A": "2"}, "argv": ["--quiet"]})
        self.assertIsInstance(c.stimulus["argv"], tuple)
        self.assertEqual(list(c.stimulus), ["argv", "env"])
        self.assertEqual(list(c.stimulus["env"]), ["A", "B"])
        self.assertEqual(json.dumps(c.to_json()),
                         json.dumps(contract(stimulus={"argv": ["--quiet"], "env": {"A": "2", "B": "1"}}).to_json()))


class SubjectAbsenceIsDeclared(unittest.TestCase):
    def test_it_cannot_be_omitted_or_inferred(self):
        content = {k: v for k, v in BASE.items() if k != "subject_absence"}
        with self.assertRaises((TypeError, ContractError)):
            BehaviorContract.create(**content)
        with self.assertRaises(ContractError):
            contract(subject_absence=None)
        with self.assertRaises(ContractError):
            contract(subject_absence="REQUIRES_SUBJECT")

    def test_both_declarations_exist_for_both_polarities(self):
        for p in Polarity:
            for a in SubjectAbsence:
                self.assertIs(contract(polarity=p, subject_absence=a).subject_absence, a)


class NoDeveloperArtefacts(unittest.TestCase):
    NAMED_TESTS = ["tests/test_cli.py", "pkg.tests.test_cli", "test_cli.py::test_quiet", "app/test/helpers.py",
                   "conftest.py", "cli_test.py", "pytest", "python -m pytest", "unittest.main",
                   "tests.test_cli:TestQuiet", "x.py::TestQuiet::test_a"]
    PRODUCT = ["app.cli:main", "src/app/cli.py", "attest.py", "latest/report.json", "GET /status", "contest.run"]

    def test_a_locator_naming_a_test_is_rejected(self):
        for loc in self.NAMED_TESTS:
            with self.subTest(locator=loc), self.assertRaises(ContractError):
                Subject(SubjectKind.PYTHON_CALLABLE, loc)

    def test_product_locators_are_accepted(self):
        for loc in self.PRODUCT:
            with self.subTest(locator=loc):
                self.assertEqual(Subject(SubjectKind.FILE_ARTIFACT, loc).locator, loc)

    def test_stimulus_or_observable_naming_a_test_is_rejected(self):
        with self.assertRaises(ContractError):
            contract(stimulus={"argv": ["python", "-m", "pytest", "tests/"]})
        with self.assertRaises(ContractError):
            contract(observable={"file": "tests/out.txt"})
        with self.assertRaises(ContractError):
            contract(stimulus={"tests/fixture.json": 1})


class Approval(unittest.TestCase):
    def setUp(self):
        self.req, self.c = requirement(), contract()
        self.reqs = {"REQ-1": self.req}

    def test_a_valid_approval_binds_both_hashes(self):
        a = approve(self.req, self.c)
        self.assertEqual(binding_problems(a, self.req, self.c), [])
        require_approved(self.c, self.reqs, [a])

    def test_an_unapproved_contract_is_refused(self):
        with self.assertRaises(UnapprovedContract):
            require_approved(self.c, self.reqs, [])

    def test_editing_the_requirement_invalidates_the_approval(self):
        a = approve(self.req, self.c)
        edited = requirement(text="quiet mode prints nothing, ever")
        self.assertNotEqual(edited.requirement_hash, self.req.requirement_hash)
        with self.assertRaises(UnapprovedContract):
            require_approved(self.c, {"REQ-1": edited}, [a])

    def test_editing_the_contract_invalidates_the_approval(self):
        a = approve(self.req, self.c)
        for field, value in (("rationale", "reworded"), ("subject_absence", SubjectAbsence.ABSENCE_IS_DECIDABLE)):
            with self.subTest(field=field), self.assertRaises(UnapprovedContract):
                require_approved(contract(**{field: value}), self.reqs, [a])

    def test_an_approval_of_another_contract_or_requirement_does_not_count(self):
        other = contract(id="BC-9")
        with self.assertRaises(UnapprovedContract):
            require_approved(self.c, self.reqs, [approve(self.req, other)])
        with self.assertRaises(UnapprovedContract):
            require_approved(self.c, self.reqs, [approve(requirement(id="REQ-2"), self.c)])

    def test_every_cited_requirement_needs_its_own_approval(self):
        c2 = contract(requirement_ids=("REQ-1", "REQ-2"))
        r2 = requirement(id="REQ-2", text="second")
        reqs = {"REQ-1": self.req, "REQ-2": r2}
        with self.assertRaises(UnapprovedContract):
            require_approved(c2, reqs, [approve(self.req, c2)])
        require_approved(c2, reqs, [approve(self.req, c2), approve(r2, c2)])
        with self.assertRaises(UnapprovedContract):
            require_approved(c2, {"REQ-1": self.req}, [approve(self.req, c2), approve(r2, c2)])

    def test_approval_authority_belongs_to_a_human(self):
        for who in ("model:deepseek-v4", "agent:reviewer", "human:", "nghi", ""):
            with self.subTest(approver=who), self.assertRaises(ContractError):
                approve(self.req, self.c, approver=who)

    def test_requirement_hash_is_verified(self):
        with self.assertRaises(ContractError):
            Requirement("REQ-1", "text", "src", "0" * 64)


class NoProseControl(unittest.TestCase):
    def test_no_kernel_module_reads_prose(self):
        self.assertEqual(ks.check(ROOT, ("NO_PROSE_CONTROL",)), [])

    def test_the_rule_sees_a_read(self):
        for src in ("def f(c):\n    return c.rationale\n", "def f(r):\n    return r.text == 'x'\n",
                    "def f(o):\n    return getattr(o, 'ownership_rationale')\n"):
            with self.subTest(src=src):
                self.assertTrue(ks.violations("aisef2/plan/x.py", src, ("NO_PROSE_CONTROL",)))


if __name__ == "__main__":
    unittest.main()
