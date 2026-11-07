"""Gate C1 — the version-forward supersession mechanism (owner v2.2 directive, Option C), proven in isolation.

Two halves:
  * the pure mechanism on SYNTHETIC series — selection is by the DECLARED round + tree (version_context,
    kernel_digest), never a global newest, and every bad series (tamper, wrong-version, missing, ambiguous-head,
    broken-chain, rollback/replay) fails explicitly;
  * a PILOT on the real C2-P10 / PROFILE-FREEZE group — the live current tree's `build()` is wrapped as a v2.2
    supersession of the real committed cycle-2 record, and the selector picks it for THIS round+tree and it
    re-derives; the legacy checker's code is untouched and still reports the record stale on this advanced tree.

Not a record-currency test itself (no @sealing, nothing committed): it proves the mechanism. The v2.2 records
themselves are re-derived under the manifest at Gate C4.
"""
from __future__ import annotations

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v2 import version_forward as vf  # noqa: E402

K1, K0 = "k1" * 20, "k0" * 20          # the v2.2 candidate kernel tree, and the earlier v2.1 kernel tree
V22, V21 = "v2.2", "v2.1"              # declared qualification rounds
COMMIT = "c" * 40                      # a provenance commit (recorded, not a selection key)


def _bytes(doc: dict) -> bytes:
    return json.dumps(doc, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _series(*docs: dict) -> list[tuple[str, dict, bytes]]:
    return [(f"r{i}.json", d, _bytes(d)) for i, d in enumerate(docs)]


def _chain(base: dict, *supersessions: tuple[str, str]) -> list[tuple[str, dict, bytes]]:
    """base + one record per (version_context, kernel_digest), each superseding the previous."""
    series = _series(base)
    for ctx, kernel in supersessions:
        prev_path, _, prev_bytes = series[-1]
        rec = vf.bind({"record": ctx, "payload": ctx}, version_context=ctx, source_commit=COMMIT,
                      kernel_digest=kernel, predecessor_path=prev_path, predecessor_bytes=prev_bytes)
        series.append((f"{ctx}-{kernel[:4]}.json", rec, _bytes(rec)))
    return series


class PureMechanism(unittest.TestCase):
    def setUp(self) -> None:
        self.base = {"record": "BASE", "payload": "legacy"}
        self.series = _chain(self.base, (V22, K1))

    def test_a_valid_chain_selects_the_record_for_the_round_and_tree(self):
        self.assertEqual(vf.validate_chain(self.series), [])
        path, rec = vf.select_for_tree(self.series, version_context=V22, kernel_digest=K1)
        self.assertEqual(rec["record"], V22)
        self.assertEqual(path, f"{V22}-{K1[:4]}.json")

    def test_the_same_series_selects_the_legacy_base_for_the_v2_1_round(self):
        # context-bound, NOT global newest: give the base's own binding and ask for the v2.1 round+tree -> the base.
        path, rec = vf.select_for_tree(self.series, version_context=V21, kernel_digest=K0,
                                       legacy_binding=(V21, K0))
        self.assertEqual(rec["record"], "BASE")
        self.assertEqual(path, "r0.json")
        # and WITHOUT the legacy binding the v2.1 round is simply not present (no silent fall-through to v2.2)
        with self.assertRaises(LookupError):
            vf.select_for_tree(self.series, version_context=V21, kernel_digest=K0)

    def test_wrong_version_is_refused_with_no_fallback(self):
        with self.assertRaises(LookupError) as e:
            vf.select_for_tree(self.series, version_context="v9.9", kernel_digest=K1)
        self.assertIn("no record declared for round", str(e.exception))

    def test_a_right_round_but_wrong_tree_is_refused(self):
        with self.assertRaises(LookupError):
            vf.select_for_tree(self.series, version_context=V22, kernel_digest=K0)

    def test_a_missing_supersession_is_refused(self):
        base_only = _series(self.base)
        with self.assertRaises(LookupError):
            vf.select_for_tree(base_only, version_context=V22, kernel_digest=K1)

    def test_a_tampered_record_fails_the_digest(self):
        path, doc, _ = self.series[-1]
        doc2 = json.loads(json.dumps(doc)); doc2["payload"] = "TAMPERED"
        bad = self.series[:-1] + [(path, doc2, _bytes(doc2))]
        self.assertTrue(any("tampered" in p for p in vf.validate_chain(bad)))
        with self.assertRaises(LookupError):
            vf.select_for_tree(bad, version_context=V22, kernel_digest=K1)

    def test_a_broken_supersede_link_is_detected(self):
        path, doc, _ = self.series[-1]
        doc2 = json.loads(json.dumps(doc))
        doc2[vf.BLOCK]["supersedes"]["record_digest"] = "deadbeef" * 8
        doc2[vf.BLOCK]["record_digest"] = vf.body_digest(doc2)   # re-seal self so only the LINK is wrong
        bad = self.series[:-1] + [(path, doc2, _bytes(doc2))]
        self.assertTrue(any("broken chain" in p for p in vf.validate_chain(bad)))

    def test_an_ambiguous_head_two_records_for_one_round_and_tree_is_refused(self):
        extra = vf.bind({"record": "dup", "payload": "dup"}, version_context=V22, source_commit=COMMIT,
                        kernel_digest=K1, predecessor_path=self.series[-1][0],
                        predecessor_bytes=self.series[-1][2])
        amb = self.series + [("dup.json", extra, _bytes(extra))]
        self.assertTrue(any("ambiguous head" in p for p in vf.validate_chain(amb)))
        with self.assertRaises(LookupError):
            vf.select_for_tree(amb, version_context=V22, kernel_digest=K1)

    def test_a_replay_or_rollback_of_a_sealed_round_tree_pair_is_detected(self):
        roll = _chain(self.base, (V22, K1), ("v2.3", K0), (V22, K1))   # the last re-seals (v2.2, K1)
        probs = vf.validate_chain(roll)
        self.assertTrue(any("rollback" in p or "replay" in p or "duplicate" in p for p in probs), probs)

    def test_a_round_may_legitimately_reuse_a_kernel_across_different_rounds(self):
        # same kernel, DIFFERENT rounds is fine (only non-kernel inputs changed) — not flagged.
        ok = _chain(self.base, (V22, K1), ("v2.3", K1))
        self.assertEqual(vf.validate_chain(ok), [])

    def test_shape_rules_base_has_no_block_and_a_supersession_must(self):
        bad_base = vf.bind({"record": "x"}, version_context=V22, source_commit=COMMIT, kernel_digest=K1,
                           predecessor_path="none", predecessor_bytes=b"")
        self.assertTrue(any("base record must not carry" in p for p in vf.validate_chain(_series(bad_base))))
        naked = {"record": "naked"}            # a non-base with no block
        self.assertTrue(any("carries no" in p for p in vf.validate_chain(_series(self.base, naked))))


class PilotProfileFreeze(unittest.TestCase):
    """The mechanism on the real C2-P10 group, on the live current tree, nothing written to the repo."""

    @classmethod
    def setUpClass(cls) -> None:
        from validation.qualification import c2_p10_profile as p10
        cls.p10 = p10
        cls.commit, cls.tree = vf.current_context(ROOT)
        cls.legacy_bytes = (ROOT / p10.OUT_REL).read_bytes()
        built = p10.build()
        cls.body = {**built, "observed_at_write": json.loads(cls.legacy_bytes).get("observed_at_write")}
        cls.supersession = vf.bind(dict(cls.body), version_context=vf.CURRENT_ROUND, source_commit=cls.commit,
                                   kernel_digest=cls.tree, predecessor_path=p10.OUT_REL,
                                   predecessor_bytes=cls.legacy_bytes)
        cls.series = [(p10.OUT_REL, json.loads(cls.legacy_bytes), cls.legacy_bytes),
                      ("closure-evidence/v2/v2.2/P10-PROFILE-FREEZE.json", cls.supersession,
                       _bytes(cls.supersession))]

    def test_the_legacy_checker_is_untouched_and_reports_the_record_stale_on_this_tree(self):
        # v2.1 verification path is the same code; on this advanced tree it honestly fails (it is one of the 21).
        self.assertIn("does not re-derive from the tree", " ".join(self.p10.check()))

    def test_the_selector_picks_the_v2_2_record_for_this_round_and_tree(self):
        self.assertEqual(vf.validate_chain(self.series), [])
        path, rec = vf.select_for_tree(self.series, version_context=vf.CURRENT_ROUND, kernel_digest=self.tree)
        self.assertEqual(path, "closure-evidence/v2/v2.2/P10-PROFILE-FREEZE.json")
        self.assertEqual(rec[vf.BLOCK]["kernel_digest"], self.tree)

    def test_the_selected_v2_2_record_re_derives_on_this_tree_with_no_problem(self):
        _, rec = vf.select_for_tree(self.series, version_context=vf.CURRENT_ROUND, kernel_digest=self.tree)
        body = {k: v for k, v in rec.items() if k != vf.BLOCK}
        fresh = {**self.p10.build(), "observed_at_write": body.get("observed_at_write")}
        self.assertEqual(self.p10.problems_of(fresh), [])
        self.assertEqual(self.p10.render(body), self.p10.render(fresh))   # the supersession IS this tree's derivation

    def test_the_supersession_binds_the_round_and_exact_tree_and_supersedes_the_committed_record(self):
        b = self.supersession[vf.BLOCK]
        self.assertEqual((b["version_context"], b["kernel_digest"]), (vf.CURRENT_ROUND, self.tree))
        self.assertEqual(b["source_commit"], self.commit)
        self.assertEqual(b["supersedes"]["record_digest"], vf.digest_bytes(self.legacy_bytes))


if __name__ == "__main__":
    unittest.main()
