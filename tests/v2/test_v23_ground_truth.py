"""B2 ground-truth prep tooling: happy paths + fail-closed negatives for every rule of protocol §2 (corpus),
§3 (labels) and §4.2/§4.3 (metrics) as implemented in validation/v23/ground_truth/ (draft of 2026-11-25).

Pins validation/v23/ground_truth/{__init__,corpus,labels,metrics}.py."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v23 import ground_truth as gt  # noqa: E402
from validation.v23.ground_truth import corpus, labels, metrics  # noqa: E402


def item(item_id: str = "todo-cli/KG-1", cls: str = "KNOWN_GOOD", repo: str = "todo-cli", **over) -> dict:
    base = {"id": item_id, "tier": "seed", "class": cls,
            "expected_delivery": corpus.EXPECTED_DELIVERY.get(cls, "PASS"),
            "repo": {"name": repo, "commit_sha": "a" * 40, "archive_sha256": "b" * 64},
            "bundle": {"plan_hash": "c" * 64, "requirements_sha256": "d" * 64},
            "candidate": {"kind": "tree", "sha256": "e" * 64},
            "recipe_sha256": None if cls == "KNOWN_GOOD" else "f" * 64,
            "labelset_sha256": "0" * 64}
    base.update(over)
    return base


def trio(repo: str = "todo-cli") -> list[dict]:
    """One item of each §2.2 class for one repo — the non-conflation minimum."""
    return [item(f"{repo}/KG-1", "KNOWN_GOOD", repo), item(f"{repo}/IS-1", "IN_SCOPE_DEFECT", repo),
            item(f"{repo}/OS-1", "OUT_OF_SCOPE_DEFECT", repo)]


def label(story: str = "S1", criterion: str = "C1", scope: str = "IN_SCOPE", verdict: str = "SATISFIED",
          severity: str | None = None, basis: str = "ran the suite at the pinned SHA; green") -> dict:
    return {"story": story, "criterion": criterion, "scope": scope, "verdict": verdict,
            "severity": severity, "basis": basis}


def measured(**over) -> dict:
    m = {"loc": 12000, "build_clean": True, "suite_green_linux": True, "suite_green_macos": True,
         "offline": True, "suite_seconds": 180.5, "probe_criterion_ran": True, "license_spdx": "MIT",
         "in_aisef_history": False, "shares_workload_identity": False,
         "commit_sha": "a" * 40, "archive_sha256": "b" * 64}
    m.update(over)
    return m


class CanonicalForm(unittest.TestCase):
    def test_canonical_matches_the_kernel_rule(self):
        """Sorted keys, no spaces, non-ASCII kept — the contract.py::canonical form, byte for byte."""
        self.assertEqual(gt.canonical({"b": 1, "a": ["x", None]}), '{"a":["x",null],"b":1}')
        self.assertEqual(gt.canonical({"đo": "thật"}), '{"đo":"thật"}')

    def test_digest_is_sha256_of_canonical(self):
        import hashlib
        self.assertEqual(gt.digest({"a": 1}), hashlib.sha256(b'{"a":1}').hexdigest())

    def test_hex_problems_rejects_uppercase_wrong_length_and_non_strings(self):
        self.assertEqual(gt.hex_problems("x", "ab" * 32, 64), [])
        for bad in ("AB" * 32, "ab" * 31, "ab" * 33, None, 7, b"ab" * 32):
            self.assertEqual(len(gt.hex_problems("x", bad, 64)), 1, bad)


class CorpusManifest(unittest.TestCase):
    def test_wellformed_two_repo_manifest_has_no_problems(self):
        manifest = corpus.build_manifest(trio("todo-cli") + trio("todo-oc"))
        self.assertEqual(corpus.manifest_problems(manifest), [])

    def test_build_manifest_is_deterministic_under_item_order(self):
        items = trio("todo-cli") + trio("todo-oc")
        self.assertEqual(corpus.render(items), corpus.render(list(reversed(items))))

    def test_render_is_canonical_json_plus_one_newline(self):
        text = corpus.render(trio())
        self.assertTrue(text.endswith("\n") and not text.endswith("\n\n"))
        self.assertEqual(text, gt.canonical(json.loads(text)) + "\n")
        self.assertEqual(json.loads(text)["schema"], corpus.SCHEMA)

    def test_duplicate_item_id_is_named(self):
        items = trio() + [item("todo-cli/KG-1", "KNOWN_GOOD")]
        bad = corpus.manifest_problems(corpus.build_manifest(items))
        self.assertTrue(any("duplicate item id" in p for p in bad), bad)

    def test_missing_class_per_repo_is_named(self):
        items = [item("r/KG-1", "KNOWN_GOOD", "r"), item("r/IS-1", "IN_SCOPE_DEFECT", "r")]
        bad = corpus.manifest_problems(corpus.build_manifest(items))
        self.assertTrue(any("non-conflation" in p and "OUT_OF_SCOPE_DEFECT" in p for p in bad), bad)

    def test_every_identity_digest_is_checked(self):
        """Uppercase hex, wrong length and a missing digest are all named — per §2.1 identity field."""
        wrong = item()
        wrong["repo"] = {"name": "todo-cli", "commit_sha": "A" * 40, "archive_sha256": "b" * 63}
        wrong["bundle"] = {"plan_hash": "c" * 64}  # requirements_sha256 missing
        bad = corpus.manifest_problems(corpus.build_manifest([wrong] + trio()[1:]))
        for name in ("repo.commit_sha", "repo.archive_sha256", "bundle.requirements_sha256"):
            self.assertTrue(any(name in p for p in bad), (name, bad))

    def test_hand_assigned_expected_delivery_is_rejected(self):
        bad = corpus.manifest_problems(corpus.build_manifest(
            [item("r/IS-1", "IN_SCOPE_DEFECT", expected_delivery="PASS")] + trio()))
        self.assertTrue(any("never hand-assigned" in p for p in bad), bad)

    def test_seeded_defect_without_recipe_is_named(self):
        bad = corpus.manifest_problems(corpus.build_manifest(
            [item("r/IS-1", "IN_SCOPE_DEFECT", recipe_sha256=None)] + trio()))
        self.assertTrue(any("recipe_sha256" in p for p in bad), bad)

    def test_known_good_recipe_may_be_null_but_not_malformed(self):
        ok = corpus.manifest_problems(corpus.build_manifest(trio()))
        self.assertEqual(ok, [])
        bad = corpus.manifest_problems(corpus.build_manifest(
            [item(recipe_sha256="XYZ")] + trio()[1:]))
        self.assertTrue(any("recipe_sha256" in p for p in bad), bad)

    def test_bad_tier_class_and_candidate_kind_are_named(self):
        bad = corpus.manifest_problems(corpus.build_manifest(
            [item(tier="tier1"), item("x", "DEFECT"), item("y", candidate={"kind": "zip", "sha256": "e" * 64})]))
        self.assertTrue(any("tier" in p for p in bad), bad)
        self.assertTrue(any("class 'DEFECT'" in p for p in bad), bad)
        self.assertTrue(any("candidate.kind" in p for p in bad), bad)

    def test_malformed_manifests_return_problems_and_never_crash(self):
        for junk in (None, [], "x", 7, {"schema": "other"}, {"schema": corpus.SCHEMA, "items": 3},
                     {"schema": corpus.SCHEMA, "items": [None, 1, "s", {}, {"id": 5}, {"repo": "r"}]}):
            self.assertTrue(corpus.manifest_problems(junk), junk)

    def test_check_cli_fails_closed_on_missing_file_and_passes_a_good_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(corpus.main(["--check", str(pathlib.Path(tmp) / "absent.json")]), 1)
            good = pathlib.Path(tmp) / "CORPUS-MANIFEST.json"
            good.write_text(corpus.render(trio()), encoding="utf-8")
            self.assertEqual(corpus.main(["--check", str(good)]), 0)
            good.write_text("not json", encoding="utf-8")
            self.assertEqual(corpus.main(["--check", str(good)]), 1)


class RepoCriteria(unittest.TestCase):
    def test_measured_values_inside_every_bound_pass(self):
        self.assertEqual(corpus.repo_criteria_problems(measured()), [])

    def test_loc_bounds_are_inclusive_1000_to_200000(self):
        self.assertEqual(corpus.repo_criteria_problems(measured(loc=1000)), [])
        self.assertEqual(corpus.repo_criteria_problems(measured(loc=200000)), [])
        for loc in (999, 200001, "12k", None, True):
            self.assertTrue(any("loc" in p for p in corpus.repo_criteria_problems(measured(loc=loc))), loc)

    def test_suite_must_be_strictly_under_ten_minutes(self):
        self.assertEqual(corpus.repo_criteria_problems(measured(suite_seconds=599.9)), [])
        for secs in (600, 601, 0, -1, "fast", None):
            bad = corpus.repo_criteria_problems(measured(suite_seconds=secs))
            self.assertTrue(any("suite_seconds" in p for p in bad), secs)

    def test_booleans_are_is_checked_not_truthy(self):
        for key, want in corpus.FLAGS:
            bad = corpus.repo_criteria_problems(measured(**{key: "yes" if want else "no"}))
            self.assertTrue(any(key in p for p in bad), key)
            bad = corpus.repo_criteria_problems(measured(**{key: not want}))
            self.assertTrue(any(key in p for p in bad), key)

    def test_independence_violations_are_named(self):
        for key in ("in_aisef_history", "shares_workload_identity"):
            bad = corpus.repo_criteria_problems(measured(**{key: True}))
            self.assertTrue(any(key in p for p in bad), key)

    def test_license_outside_the_osi_allowlist_fails_closed(self):
        for spdx in ("Proprietary", "SSPL-1.0", None, ""):
            bad = corpus.repo_criteria_problems(measured(license_spdx=spdx))
            self.assertTrue(any("license_spdx" in p for p in bad), spdx)

    def test_pinning_digests_and_non_dict_input_are_checked(self):
        self.assertTrue(corpus.repo_criteria_problems(measured(commit_sha="a" * 39)))
        self.assertTrue(corpus.repo_criteria_problems(measured(archive_sha256="B" * 64)))
        self.assertTrue(corpus.repo_criteria_problems(None))
        self.assertTrue(corpus.repo_criteria_problems([measured()]))

    def test_missing_key_is_a_problem(self):
        m = measured()
        del m["offline"]
        self.assertTrue(any("offline" in p for p in corpus.repo_criteria_problems(m)))


class LabelSchema(unittest.TestCase):
    def test_valid_satisfied_and_violated_labels_pass(self):
        self.assertEqual(labels.label_problems(label()), [])
        self.assertEqual(labels.label_problems(label(verdict="VIOLATED", severity="P1")), [])

    def test_missing_severity_on_violated_is_named(self):
        bad = labels.label_problems(label(verdict="VIOLATED"))
        self.assertTrue(any("required iff VIOLATED" in p for p in bad), bad)

    def test_severity_on_satisfied_is_named(self):
        bad = labels.label_problems(label(severity="P2"))
        self.assertTrue(any("SATISFIED" in p for p in bad), bad)

    def test_bad_enums_are_named(self):
        self.assertTrue(labels.label_problems(label(scope="CONTRACTED")))
        self.assertTrue(labels.label_problems(label(verdict="OK")))
        self.assertTrue(labels.label_problems(label(verdict="VIOLATED", severity="P4")))
        self.assertTrue(labels.label_problems(label(verdict="VIOLATED", severity="p0")))

    def test_empty_basis_story_criterion_and_non_dict_are_named(self):
        self.assertTrue(labels.label_problems(label(basis="")))
        self.assertTrue(labels.label_problems(label(basis="   ")))
        self.assertTrue(labels.label_problems(label(story="")))
        self.assertTrue(labels.label_problems(label(criterion="")))
        self.assertTrue(labels.label_problems("label"))

    def test_labelset_rejects_duplicates_empties_and_non_lists(self):
        dup = [label(), label()]
        self.assertTrue(any("duplicate (story, criterion)" in p for p in labels.labelset_problems(dup)))
        self.assertTrue(labels.labelset_problems([]))
        self.assertTrue(labels.labelset_problems({"S1": label()}))


class DerivedVerdict(unittest.TestCase):
    def test_all_satisfied_is_pass(self):
        self.assertEqual(labels.derived_verdict([label(), label(criterion="C2")]), "PASS")

    def test_one_in_scope_violation_is_fail(self):
        ls = [label(), label(criterion="C2", verdict="VIOLATED", severity="P3")]
        self.assertEqual(labels.derived_verdict(ls), "FAIL")

    def test_only_out_of_scope_violations_stay_pass(self):
        """§3.1: OUT_OF_SCOPE violations do not change the derived verdict (§2.2 by-design escape)."""
        ls = [label(), label(criterion="C2", scope="OUT_OF_SCOPE", verdict="VIOLATED", severity="P0")]
        self.assertEqual(labels.derived_verdict(ls), "PASS")

    def test_invalid_labelset_is_refused(self):
        with self.assertRaises(ValueError):
            labels.derived_verdict([label(verdict="VIOLATED")])
        with self.assertRaises(ValueError):
            labels.derived_verdict([])

    def test_most_severe_violated_in_scope(self):
        ls = [label(verdict="VIOLATED", severity="P2"),
              label(criterion="C2", verdict="VIOLATED", severity="P1"),
              label(criterion="C3", scope="OUT_OF_SCOPE", verdict="VIOLATED", severity="P0")]
        self.assertEqual(labels.most_severe_violated_in_scope(ls), "P1")  # the OUT_OF_SCOPE P0 does not count
        self.assertIsNone(labels.most_severe_violated_in_scope([label()]))


class CommitThenReveal(unittest.TestCase):
    LS = [label(), label(criterion="C2", verdict="VIOLATED", severity="P1", basis="probe X; wrong result")]

    def test_commitment_is_hex64_and_order_independent(self):
        c = labels.commitment(self.LS, b"salt-1")
        self.assertEqual(gt.hex_problems("c", c, 64), [])
        self.assertEqual(c, labels.commitment(list(reversed(self.LS)), b"salt-1"))

    def test_salt_and_content_both_move_the_hash(self):
        c = labels.commitment(self.LS, b"salt-1")
        self.assertNotEqual(c, labels.commitment(self.LS, b"salt-2"))
        changed = [dict(self.LS[0]), dict(self.LS[1], severity="P2")]
        self.assertNotEqual(c, labels.commitment(changed, b"salt-1"))

    def test_reveal_matches(self):
        c = labels.commitment(self.LS, b"salt-1")
        self.assertEqual(labels.reveal_problems(self.LS, b"salt-1", c), [])

    def test_reveal_mismatch_is_a_named_problem_not_an_exception(self):
        c = labels.commitment(self.LS, b"salt-1")
        bad = labels.reveal_problems(self.LS, b"other", c)
        self.assertTrue(any("commitment mismatch" in p for p in bad), bad)
        changed = [dict(self.LS[0], verdict="VIOLATED", severity="P3"), dict(self.LS[1])]
        self.assertTrue(any("commitment mismatch" in p for p in labels.reveal_problems(changed, b"salt-1", c)))

    def test_reveal_fails_closed_on_malformed_inputs(self):
        c = labels.commitment(self.LS, b"s")
        self.assertTrue(labels.reveal_problems(self.LS, b"s", c.upper()))
        self.assertTrue(labels.reveal_problems(self.LS, b"s", c[:-2]))
        self.assertTrue(labels.reveal_problems(self.LS, "s", c))
        self.assertTrue(labels.reveal_problems([label(verdict="VIOLATED")], b"s", c))
        with self.assertRaises(ValueError):
            labels.commitment(self.LS, "not-bytes")


class Agreement(unittest.TestCase):
    def ls(self, sev_c2: str = "P1", verdict_c2: str = "VIOLATED", scope_c2: str = "IN_SCOPE") -> list[dict]:
        sev = sev_c2 if verdict_c2 == "VIOLATED" else None
        return [label(), label(criterion="C2", scope=scope_c2, verdict=verdict_c2, severity=sev)]

    def test_identical_labelsets_agree_fully(self):
        got = labels.agreement(self.ls(), self.ls())
        self.assertEqual((got["compared"], got["agreed"], got["rate"]), (2, 2, 1.0))
        self.assertEqual(got["disagreements"], [])
        self.assertEqual(got["severity_resolutions"], [])

    def test_one_class_severity_gap_agrees_and_the_more_severe_stands(self):
        got = labels.agreement(self.ls("P2"), self.ls("P1"))
        self.assertEqual(got["rate"], 1.0)
        self.assertEqual(got["disagreements"], [])
        self.assertEqual(got["severity_resolutions"],
                         [{"story": "S1", "criterion": "C2", "a": "P2", "b": "P1", "stands": "P1"}])

    def test_larger_severity_gap_is_a_disagreement(self):
        got = labels.agreement(self.ls("P0"), self.ls("P2"))
        self.assertEqual(got["rate"], 0.5)
        self.assertEqual(got["severity_resolutions"], [])
        self.assertEqual(got["disagreements"],
                         [{"story": "S1", "criterion": "C2", "field": "severity", "a": "P0", "b": "P2"}])

    def test_verdict_and_scope_mismatches_disagree(self):
        got = labels.agreement(self.ls(), self.ls(verdict_c2="SATISFIED"))
        self.assertEqual(got["disagreements"][0]["field"], "verdict")
        got = labels.agreement(self.ls(scope_c2="OUT_OF_SCOPE"), self.ls())
        self.assertEqual(got["disagreements"][0]["field"], "scope")
        self.assertEqual(got["rate"], 0.5)

    def test_a_criterion_one_labelset_lacks_is_a_disagreement(self):
        got = labels.agreement(self.ls(), [label()])
        self.assertEqual(got["compared"], 2)
        self.assertEqual(got["rate"], 0.5)
        self.assertEqual(got["disagreements"][0]["field"], "missing")

    def test_invalid_labelsets_are_refused(self):
        with self.assertRaises(ValueError):
            labels.agreement([label(verdict="VIOLATED")], self.ls())


class Classify(unittest.TestCase):
    def test_every_cell_of_the_table(self):
        self.assertEqual(metrics.classify("PASS", "PASS"), "TA")
        self.assertEqual(metrics.classify("FAIL", "FAIL"), "TR")
        self.assertEqual(metrics.classify("PASS", "FAIL"), "FP")   # false-accept, false PASS
        self.assertEqual(metrics.classify("FAIL", "PASS"), "FN")   # false-reject, false FAIL
        self.assertEqual(metrics.classify("NOT_REACHED", "PASS"), "INDETERMINATE")
        self.assertEqual(metrics.classify("NOT_REACHED", "FAIL"), "INDETERMINATE")

    def test_a_run_refusal_is_indeterminate_whatever_the_verdict_says(self):
        self.assertEqual(metrics.classify("PASS", "FAIL", refusal=True), "INDETERMINATE")
        self.assertEqual(metrics.classify("FAIL", "PASS", refusal=True), "INDETERMINATE")

    def test_unknown_verdicts_are_refused(self):
        with self.assertRaises(ValueError):
            metrics.classify("BLOCKED", "PASS")
        with self.assertRaises(ValueError):
            metrics.classify("PASS", "NOT_REACHED")


def rec(n: int, cls: str = "IN_SCOPE_DEFECT", predicted: str = "FAIL", tier: str = "seed", repo: str = "r1",
        severity: str | None = "P1", refusal: bool = False) -> dict:
    if corpus.EXPECTED_DELIVERY[cls] == "PASS":
        severity = None
    return metrics.item_record(f"i{n}", tier=tier, repo=repo, item_class=cls, predicted=predicted,
                               refusal=refusal, severity=severity)


class ItemRecord(unittest.TestCase):
    def test_expected_is_derived_from_the_corpus_class(self):
        self.assertEqual(rec(1, "KNOWN_GOOD", "PASS")["expected"], "PASS")
        self.assertEqual(rec(2, "IN_SCOPE_DEFECT", "FAIL")["expected"], "FAIL")
        self.assertEqual(rec(3, "OUT_OF_SCOPE_DEFECT", "PASS")["expected"], "PASS")  # §2.2: passes BY DESIGN

    def test_record_carries_the_measure_row_shape(self):
        r = metrics.item_record("i1", tier="seed", repo="r1", item_class="IN_SCOPE_DEFECT", predicted="FAIL",
                                blocked=["1 of the plan's stories did not commit"], severity="P0",
                                cost={"wallclock_s": 12, "tokens": 0, "usd": 0, "estimated": False})
        for key in ("item_id", "predicted", "blocked", "expected", "class", "severity", "cost"):
            self.assertIn(key, r)
        self.assertEqual(r["class"], "TR")

    def test_expected_fail_item_requires_a_severity_and_expected_pass_refuses_one(self):
        with self.assertRaises(ValueError):
            metrics.item_record("i", tier="seed", repo="r", item_class="IN_SCOPE_DEFECT", predicted="FAIL")
        with self.assertRaises(ValueError):
            metrics.item_record("i", tier="seed", repo="r", item_class="KNOWN_GOOD", predicted="PASS", severity="P1")

    def test_bad_enums_are_refused(self):
        with self.assertRaises(ValueError):
            metrics.item_record("i", tier="tier1", repo="r", item_class="KNOWN_GOOD", predicted="PASS")
        with self.assertRaises(ValueError):
            metrics.item_record("i", tier="seed", repo="r", item_class="GOOD", predicted="PASS")
        with self.assertRaises(ValueError):
            metrics.item_record("i", tier="seed", repo="", item_class="KNOWN_GOOD", predicted="PASS")


class Aggregate(unittest.TestCase):
    def test_tiers_split_and_tier1_pool_excludes_seed(self):
        records = [rec(1, "KNOWN_GOOD", "PASS"), rec(2, tier="external", repo="r2"),
                   rec(3, "KNOWN_GOOD", "PASS", tier="external", repo="r2")]
        got = metrics.aggregate(records)
        self.assertEqual(sorted(got["per_tier"]), ["external", "seed"])
        self.assertEqual(got["per_tier"]["seed"]["items"], 1)
        self.assertEqual(got["pooled_tier1"]["items"], 2)       # §2.5/Q6: seed never pooled into Tier-1
        self.assertEqual(got["per_repo"]["r2"]["counts"]["TR"], 1)

    def test_single_p0_false_pass_raises_the_no_go_flag(self):
        records = [rec(1, "KNOWN_GOOD", "PASS"), rec(2, predicted="PASS", severity="P0")]
        got = metrics.aggregate(records)
        self.assertTrue(got["no_go"])
        self.assertEqual(got["no_go_basis"], ["i2"])
        self.assertEqual(got["per_tier"]["seed"]["false_accepts_by_severity"]["P0"], 1)

    def test_p2_false_pass_reports_but_does_not_gate(self):
        got = metrics.aggregate([rec(1, predicted="PASS", severity="P2"), rec(2)])
        self.assertFalse(got["no_go"])                           # §4.3/Q11: only P0/P1 false-PASS pre-commits
        self.assertEqual(got["per_tier"]["seed"]["false_accepts_by_severity"]["P2"], 1)

    def test_out_of_scope_escapes_are_separate_and_never_false_accepts(self):
        records = [rec(1, "OUT_OF_SCOPE_DEFECT", "PASS"), rec(2, "OUT_OF_SCOPE_DEFECT", "FAIL"), rec(3)]
        agg = metrics.aggregate(records)["per_tier"]["seed"]
        self.assertEqual(agg["counts"]["FP"], 0)                 # §2.2: never pooled with false-accepts
        self.assertEqual(agg["out_of_scope_escapes"], 1)
        self.assertEqual(agg["out_of_scope_escape_rate"], 0.5)
        self.assertEqual(sum(agg["false_accepts_by_severity"].values()), 0)
        self.assertFalse(metrics.aggregate(records)["no_go"])

    def test_recall_counts_indeterminate_defects_as_undetected(self):
        records = [rec(1), rec(2, predicted="NOT_REACHED")]      # two P1 defects, one detected
        agg = metrics.aggregate(records)["per_tier"]["seed"]
        self.assertEqual(agg["recall_by_severity"]["P1"], 0.5)
        self.assertIsNone(agg["recall_by_severity"]["P0"])

    def test_precision_is_true_fails_over_all_fails(self):
        records = [rec(1), rec(2, "KNOWN_GOOD", "FAIL")]         # one TR, one FN
        agg = metrics.aggregate(records)["per_tier"]["seed"]
        self.assertEqual(agg["precision"], 0.5)
        none = metrics.aggregate([rec(1, "KNOWN_GOOD", "PASS")])["per_tier"]["seed"]
        self.assertIsNone(none["precision"])

    def test_exactly_twenty_percent_indeterminate_is_valid_just_over_is_not(self):
        ten = [rec(n, "KNOWN_GOOD", "PASS") for n in range(8)] + \
              [rec(8, predicted="NOT_REACHED"), rec(9, predicted="NOT_REACHED")]
        agg = metrics.aggregate(ten)["per_repo"]["r1"]
        self.assertEqual(agg["indeterminate_rate"], 0.2)
        self.assertTrue(agg["measurement_valid"])                # Q5: "> 20 %" invalidates; 20 % exactly holds
        eleven = ten[:-1] + [rec(8, predicted="NOT_REACHED"), rec(9, refusal=True)]
        self.assertFalse(metrics.aggregate(eleven)["per_repo"]["r1"]["measurement_valid"])

    def test_workload_validity_is_per_repo(self):
        records = [rec(n, "KNOWN_GOOD", "PASS", repo="ok") for n in range(4)] + [rec(4, repo="ok")] + \
                  [rec(5, predicted="NOT_REACHED", repo="broken"), rec(6, "KNOWN_GOOD", "PASS", repo="broken")]
        got = metrics.aggregate(records)
        self.assertTrue(got["per_repo"]["ok"]["measurement_valid"])
        self.assertFalse(got["per_repo"]["broken"]["measurement_valid"])

    def test_raw_dicts_that_are_not_item_records_are_refused(self):
        with self.assertRaises(ValueError):
            metrics.aggregate([{"class": "WIN", "tier": "seed", "item_class": "KNOWN_GOOD"}])
        with self.assertRaises(ValueError):
            metrics.aggregate(["record"])


if __name__ == "__main__":
    unittest.main()
