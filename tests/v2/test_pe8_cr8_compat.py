"""PE8-2 (owner ruling 2026-11-27 B/C) — versioned capability migration for probe.process_effect, CR-8
(COMPATIBILITY-MATRIX / CT-7). The deadline-integrity fix bumps process_effect CAPABILITY_VERSION 1 -> 2, so its
capability DIGEST changes. This module proves historical compatibility is preserved, adversarially:

* `bundle_cli.RELEASES["2.2.0"]` records process_effect's version-1 identity (the capability digest a 2.2.0 bundle's
  specs name), unchanged — the old capability is retained for replay, never rewritten;
* a historical 2.2.0-identity bundle is REFUSED by this release's `bundle.load` (the bump genuinely changed identity:
  no silent rebind), yet `bundle_cli.load_for_release(data, "2.2.0")` compiles it for identity and reproduces its own
  `bundle_digest` (the bundle's bytes) with no execution and no re-binding;
* a fresh v2.3 bundle uses the NEW (version-2) identity and loads under the active catalog; the two spec ids differ;
* mixing the two identities for one criterion is a PROBE_MISMATCH — the two sealed records' comparability digests
  differ, which `orchestrate.proof.prove` turns into FailureCode.PROBE_MISMATCH (RFC §16), never a proof.

Offline; no probe runs a subject (bundles are compiled for identity only)."""

from __future__ import annotations

import hashlib
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import bundle as B  # noqa: E402
from aisef2.app import bundle_cli  # noqa: E402
from aisef2.arch.enums import BehaviorVerdict, Enforcement, ObligationRole, Polarity, SubjectAbsence, SubjectKind  # noqa: E402
from aisef2.plan.obligation import EXPECTED_AT_PARENT, NOT_PREREGISTERED, Plan, PlanObligation  # noqa: E402
from aisef2.probe import catalog, process_effect as pe  # noqa: E402
from aisef2.probe.protocol import ProbeRecord  # noqa: E402
from aisef2.product.approval import ContractApproval, Requirement  # noqa: E402
from aisef2.product.contract import BehaviorContract, Subject  # noqa: E402
from aisef2.product.outcome import Executed  # noqa: E402

PE = SubjectKind.PROCESS_EFFECT
#: process_effect's capability digest at v2.2.0 — sha256([PROBE_ID, 1, CLASSES]) at tag v2.2.0 (da3ea33f), version 1.
V22_DIGEST = hashlib.sha256(
    __import__("json").dumps([pe.PROBE_ID, 1, list(pe.CLASSES)]).encode("utf-8")).hexdigest()
REQ = Requirement.create(id="R-1", text="the book saves and verifies", source="docs/requirements.md 1")


def _contract() -> BehaviorContract:
    scenario = [{"step": "construct", "args": [], "kwargs": {}},
                {"step": "call", "method": "count", "args": [], "kwargs": {}}]
    return BehaviorContract.create(id="BC-PE", requirement_ids=(REQ.id,), subject=Subject(PE, "store.book:Book"),
                                   stimulus={"scenario": scenario}, observable={"returns": 0, "within_s": 10},
                                   polarity=Polarity.MUST_HOLD, subject_absence=SubjectAbsence.REQUIRES_SUBJECT,
                                   rationale="fixture")


def _bundle(contract: BehaviorContract, spec_id: str) -> dict:
    ap = ContractApproval(REQ.id, REQ.requirement_hash, contract.id, contract.contract_hash, "human:owner", 100.0, ())
    ob = PlanObligation("C-PE", spec_id, "S1", ObligationRole.INTRODUCE,
                        EXPECTED_AT_PARENT[ObligationRole.INTRODUCE], (), "S1 introduces C-PE")
    plan = Plan.create(id="PLAN-FIX", baseline="a" * 40, obligations=(ob,), plan_quality_policy=NOT_PREREGISTERED)
    facts = {"C-PE": {"requirement": REQ.id, "section": "1", "clause": "1.1", "clause_text": REQ.text,
                      "subject": contract.subject.locator}}
    return B.dump(name="fix", description="pe8 cr8", requirements_path="docs/requirements.md",
                  requirements_sha256="ab" * 32, product_roots=("store",), requirements=(REQ,), contracts=(contract,),
                  approvals=(ap,), plan=plan, facts=facts, stories={"S1": {"depends_on": [], "tests": ["tests/t.py"]}})


def _current_spec(contract: BehaviorContract):
    refs = {k: bundle_cli.ProbeRef(e.probe_id, e.probe_digest) for k, e in catalog.active().items()}
    return bundle_cli._mint(contract, refs[PE])


class Cr8Identity(unittest.TestCase):
    def test_the_bump_moved_the_capability_identity(self):
        """process_effect is at version 2 and its active digest is the version-2 digest; the version-1 digest (what a
        2.2.0 bundle names) is what RELEASES["2.2.0"] records — retained, not rewritten."""
        self.assertEqual(pe.CAPABILITY_VERSION, 2)
        self.assertEqual(pe.DIGEST, hashlib.sha256(
            __import__("json").dumps([pe.PROBE_ID, 2, list(pe.CLASSES)]).encode("utf-8")).hexdigest())
        self.assertNotEqual(pe.DIGEST, V22_DIGEST)
        probe_id, digest, version = bundle_cli.RELEASES["2.2.0"]["probes"][PE]
        self.assertEqual((probe_id, digest, version), (pe.PROBE_ID, V22_DIGEST, 1))
        self.assertEqual(catalog.active()[PE].probe_digest, pe.DIGEST)   # active catalog is the new identity

    def test_historical_v22_bundle_is_refused_under_the_active_probes_no_silent_rebind(self):
        c = _contract()
        old_id = bundle_cli._earlier(_current_spec(c), bundle_cli.RELEASES["2.2.0"])
        self.assertNotEqual(old_id, _current_spec(c).id)
        with self.assertRaises(B.BundleError) as e:
            B.load(_bundle(c, old_id))
        self.assertIn("earlier release", str(e.exception))   # it points the operator to migrate/verify-for-identity

    def test_load_for_release_verifies_the_historical_v22_bundle_for_identity(self):
        """CR-8: the 2.2.0 bundle loads under its own release's probes and reproduces its own bundle_digest (the bytes),
        with no execution and no re-binding — in contrast to migrate, which changes the digest."""
        c = _contract()
        old_id = bundle_cli._earlier(_current_spec(c), bundle_cli.RELEASES["2.2.0"])
        data = _bundle(c, old_id)
        project = bundle_cli.load_for_release(data, "2.2.0")
        self.assertEqual(project.digest, hashlib.sha256(B._canonical(dict(data))).hexdigest())
        self.assertIn(old_id, project.specs)                      # the historical spec id resolves
        self.assertEqual(project.specs[old_id].probe_digest, V22_DIGEST)   # under the version-1 identity

    def test_fresh_v23_bundle_uses_the_new_identity(self):
        c = _contract()
        spec = _current_spec(c)
        project = B.load(_bundle(c, spec.id))
        self.assertEqual(project.digest, hashlib.sha256(B._canonical(dict(_bundle(c, spec.id)))).hexdigest())
        self.assertEqual(project.specs[spec.id].probe_digest, pe.DIGEST)   # the version-2 identity
        self.assertNotIn(V22_DIGEST, {s.probe_digest for s in project.specs.values()})

    def test_mixing_the_two_identities_for_one_criterion_is_a_probe_mismatch(self):
        """A record under the historical identity and one under the new identity have different comparability digests,
        which orchestrate.proof.prove turns into PROBE_MISMATCH (proof.py:97), never a proof (RFC §16)."""
        def record(digest: str) -> ProbeRecord:
            return ProbeRecord.create(spec_id="PPS-x", semantic_hash="s" * 16, probe_id=pe.PROBE_ID,
                                      probe_digest=digest, revision="a" * 40, enforcement=Enforcement.PARTIAL,
                                      result=Executed(BehaviorVerdict.SATISFIED))
        old, new = record(V22_DIGEST), record(pe.DIGEST)
        self.assertNotEqual(old.comparability, new.comparability)        # => FailureCode.PROBE_MISMATCH
        self.assertEqual(record(pe.DIGEST).comparability, new.comparability)   # same identity is comparable (control)

    def test_load_for_release_is_fail_closed(self):
        c = _contract()
        data = _bundle(c, bundle_cli._earlier(_current_spec(c), bundle_cli.RELEASES["2.2.0"]))
        with self.assertRaises(bundle_cli.MigrationError):
            bundle_cli.load_for_release(data, "9.9.9")             # no such release
        moved = {**bundle_cli.RELEASES["2.2.0"], "compiler_digest": "f" * 64}
        with mock.patch.dict(bundle_cli.RELEASES, {"2.2.0": moved}):
            with self.assertRaises(bundle_cli.MigrationError):      # a release whose compiler moved is refused, not guessed
                bundle_cli.load_for_release(data, "2.2.0")


if __name__ == "__main__":
    unittest.main()
