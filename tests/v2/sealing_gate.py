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

import os
import unittest

SEALING = os.environ.get("AISEF_SEALING") == "1"

#: the one gate: without AISEF_SEALING=1 a record-currency test is a visible skip, never a red herring
sealing = unittest.skipUnless(
    SEALING, "record-currency/sealing check: binds committed evidence records to the sealed tree; red on every "
             "unsealed branch by design — runs on master and sealed tags (AISEF_SEALING=1)")

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
