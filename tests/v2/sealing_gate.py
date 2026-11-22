"""ROADMAP-2.2 F1 — the sealing tier: record-currency checks, gated out of the branch/PR product signal.

A record-currency test asserts that a COMMITTED evidence record is what this tree re-derives. On every unsealed
branch that is red BY DESIGN (the records bind the sealed snapshot; re-sealing is the owner's act), so for 2.1 those
reds drowned the product signal: a newcomer's clean checkout failed ~18 tests that say nothing about the product.
The gate moves them to their own tier: `AISEF_SEALING=1` runs them (the `sealing` job of tests.yml — master and
tags only, honestly RED until the owner reseals, failing the gate a release must pass); without it they are SKIPPED,
visibly, and the suite's verdict is the product's.

What belongs here is exactly the committed-record binding — never a product test, never a live-tree static check
(those run everywhere; a red one is a real finding). GATED is the closed list; tests/v2/test_sealing_gate.py scans
the tree and refuses a gated test missing from this list or a listed test missing its gate — a sealing check can
never be dropped silently."""

from __future__ import annotations

import hashlib
import inspect
import os
import pathlib
import unittest

SEALING = os.environ.get("AISEF_SEALING") == "1"
ROOT = pathlib.Path(__file__).resolve().parents[2]

_sealing = unittest.skipUnless(
    SEALING, "record-currency/sealing check: binds committed evidence records to the sealed tree; red on every "
             "unsealed branch by design — runs on master and sealed tags (AISEF_SEALING=1)")

#: ledger seq 13 (ROUND-AUTH, GATED_TEST_WIRING): the v2.2-round currency tests, which select records by round v2.2 +
#: HEAD:aisef2, are history on the v2.3 branch — replayed byte-identically at v2.2.0 by validation/v23/replay_v22.py
#: (tests/v23/test_v23_rounds.py::RoundV23.test_replay_v22) and skipped here, naming the replay; their round-v2.3
#: counterparts are tests/v23/test_v23_rounds.py::RoundV23. Each id stays in GATED, which is unchanged.
V22_REPLAYED = (
    "tests/v2/test_c2_delivery_experiment.py::PlanCorrection.test_the_committed_record_is_what_this_tree_derives",
    "tests/v2/test_c2_k_nowork_001.py::Record.test_the_record_binds_this_tree_and_shows_the_cases_red_before_and_green_after",
    "tests/v2/test_c2_orchestration_conformance.py::Record.test_15_the_record_binds_this_tree_and_old_and_new_agree_on_every_single_probe_story",
    "tests/v2/test_c2_p10_cohort_static.py::Record.test_the_evidence_record_re_derives_from_the_tree",
    "tests/v2/test_c2_p10_profile_freeze.py::Checker.test_the_evidence_record_re_derives",
    "tests/v2/test_c2_p5_acceptance.py::Acceptance.test_the_acceptance_re_derives_on_this_tree",
    "tests/v2/test_c2_p5_acceptance.py::KernelProvenance.test_on_this_tree_the_committed_proposal_is_current",
    "tests/v2/test_v21_mutation_runner.py::Classify.test_historical_records_read_as_before",
    "tests/v2/test_p5_plan_v22_proposal.py::Record.test_P5_8_committed_record_is_current",
    "tests/v2/test_p9_reproduction.py::KernelComparison.test_Q5_19_the_kernel_comparison_record_binds_this_tree",
    "tests/v2/test_v21_conformance_ruling.py::CommittedRuling.test_the_committed_ruling_is_what_this_tree_derives",
)

#: Q0-1 (docs/v2.3/amendments/Q0-1-V23-ROUND.md): the v2.2 round's GATED Q0 calibration, the whole class, is history
#: as well — replayed at v2.2.0 by validation/v23/replay_v22.py, where the record it derives must be byte-identical to
#: the committed closure-evidence/v2/v2.1/Q0-CHECKER-CALIBRATION.json — and is skipped here by the same rule. Its
#: round-v2.3 counterpart is tests/v23/test_v23_q0_round.py::Q0RoundV23 (validation/v23/q0_round.py, with the round's
#: own Q0 record). It is replayed only together with that counterpart: both files are in V23_PINNED.
V22_REPLAYED_Q0 = ("tests/v2/p0/test_checker_calibration.py::CheckerCalibration",)


#: RA-GP-1, Q0-1: what the V22_REPLAYED and V22_REPLAYED_Q0 skip stands on, pinned by the sha256 of each file's LF
#: bytes — the round-v2.3 counterparts (the 11 and Q0), the replay, the round's Q0 calibration, the digest tool, and
#: the (empty) package file that lets `discover` find them. The skip holds only while every pinned file is exactly as
#: pinned; a deleted or edited one un-skips all 12, which then run under AISEF_SEALING=1 as they did before seq 13. Changing a pinned file therefore needs an edit of this file, which
#: is wiring other than the one ledger seq 13 names.
V23_PINNED = {
    "tests/v23/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "tests/v23/test_v23_q0_round.py": "9b9433f33c1176367a80dd2a3144f37f8f3e2250d6cd62df9a3956bb3ca8c7cb",
    "tests/v23/test_v23_rounds.py": "a8ab309988a6e9dd66bfa782dd6b5f65b204066ea73b511870d17451690323f3",
    "validation/v23/ledger_digest.py": "660624c01b47811b8b9d2f41f371d4b721bb8b7c802eaa87b656c05f99ee3df9",
    "validation/v23/q0_round.py": "038906381a500a0c40e179803078c471527f960b884644d34eea64b4ff85fccf",
    "validation/v23/replay_v22.py": "6b7195ec4aafb4cefcb304ad94325331853360206330d25e95af26e4449adc60",
}


def _lf_sha256(rel: str) -> str | None:
    try:
        return hashlib.sha256((ROOT / rel).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    except OSError:
        return None


V23_PINS_HOLD = all(_lf_sha256(rel) == want for rel, want in V23_PINNED.items())


def sealing(obj):
    """The one gate. Its id is the defining file's repo-relative path + `__qualname__` (never `__module__`: `discover
    -s tests` names modules `v2.test_x`). A V22_REPLAYED or V22_REPLAYED_Q0 test is skipped naming the replay, but
    only while V23_PINS_HOLD; every other gated test, and a replayed one when a pin breaks, is a visible skip without
    AISEF_SEALING=1 and runs with it."""
    try:
        rid = f"{pathlib.Path(inspect.getfile(obj)).resolve().relative_to(ROOT).as_posix()}::{obj.__qualname__}"
    except (TypeError, ValueError):
        rid = None
    if rid in (*V22_REPLAYED, *V22_REPLAYED_Q0) and V23_PINS_HOLD:
        return unittest.skip("round v2.2 history: replayed at v2.2.0 (da3ea33f) by validation/v23/replay_v22.py; "
                             "round v2.3 = tests/v23/test_v23_rounds.py::RoundV23, "
                             "tests/v23/test_v23_q0_round.py::Q0RoundV23")(obj)
    return _sealing(obj)


#: every gated test, closed: "path::Class" gates the class, "path::Class.method" one method
GATED = (
    "tests/v2/p0/test_checker_calibration.py::CheckerCalibration",
    "tests/v2/p0/test_destructive_authority.py::Checker.test_this_tree_passes_and_every_site_is_ledgered",
    "tests/v2/p0/test_freeze_manifest.py::FreezeManifest.test_the_V2_007_exception_records_what_the_owner_decided_and_when",
    "tests/v2/p5/test_invariants.py::MutationAuthority.test_INV_MUTATION_AUTHORITY_destructive_sites_of_the_invariant_code_are_ledgered",
    "tests/v2/test_c2_delivery_experiment.py::PlanCorrection.test_the_committed_record_is_what_this_tree_derives",
    "tests/v2/test_c2_k_nowork_001.py::Record.test_the_record_binds_this_tree_and_shows_the_cases_red_before_and_green_after",
    "tests/v2/test_c2_orchestration_conformance.py::Record.test_15_the_record_binds_this_tree_and_old_and_new_agree_on_every_single_probe_story",
    "tests/v2/test_c2_orchestration_conformance.py::Record.test_15b_only_the_release_s_named_changes_are_accepted_each_while_its_gate_holds",
    "tests/v2/test_c2_p10_cohort_static.py::Record.test_the_evidence_record_re_derives_from_the_tree",
    "tests/v2/test_c2_p10_profile_freeze.py::Checker.test_the_evidence_record_re_derives",
    "tests/v2/test_c2_p5_acceptance.py::Acceptance.test_the_acceptance_re_derives_on_this_tree",
    "tests/v2/test_c2_p5_acceptance.py::KernelProvenance.test_on_this_tree_the_committed_proposal_is_current",
    # §8 reads the committed P1..V2.0-S2 mutation records against THIS tree's sources: any kernel edit after a seal
    # (wave 1 touched fold.py, run_scope.py, registry.py) honestly flags every target of the edited file
    # "changed since the mutation run — re-run it"; the re-run/reseal is the owner's act, so the binding is this tier's
    "tests/v2/test_v21_mutation_runner.py::Classify.test_historical_records_read_as_before",
    "tests/v2/test_cycle2_wp201.py::Baseline.test_the_committed_freeze_manifest_holds",
    "tests/v2/test_p5_plan_v22_proposal.py::Record.test_P5_8_committed_record_is_current",
    "tests/v2/test_p9_reproduction.py::KernelComparison.test_Q5_18_check_binds_the_record_to_q5_both_kernels_the_corpus_and_the_ruling_s_data",
    "tests/v2/test_p9_reproduction.py::KernelComparison.test_Q5_19_the_kernel_comparison_record_binds_this_tree",
    "tests/v2/test_v21_conformance_ruling.py::CommittedRuling.test_the_committed_ruling_is_what_this_tree_derives",
)
