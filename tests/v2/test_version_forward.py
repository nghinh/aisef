"""Gate C1 — the version-forward supersession mechanism (owner v2.2 directive, Option C), proven in isolation.

Two halves:
  * the pure mechanism on SYNTHETIC series — selection is context-bound (never global newest), and every bad
    series (tamper, wrong-version, missing, ambiguous-head, broken-chain, rollback, replay) fails explicitly;
  * a PILOT on the real C2-P10 / PROFILE-FREEZE group — the live current tree's `build()` is wrapped as a v2.2
    supersession of the real committed cycle-2 record, and the selector picks it for THIS tree and it re-derives;
    the legacy checker's code is untouched and still reports the record stale on this advanced tree (the v2.1
    verification is byte-for-byte the same path, the supersession is what makes v2.2 current).

Not a record-currency test itself (no @sealing, nothing committed): it binds no evidence to the sealed tree, it
proves the mechanism. The v2.2 records themselves are re-derived under the manifest at Gate C4.
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

C1, K1 = "c1" * 20, "k1" * 20          # a v2.2 candidate's (commit, kernel tree)
C0, K0 = "c0" * 20, "k0" * 20          # the earlier v2.1 tree the base is valid for


def _bytes(doc: dict) -> bytes:
    return json.dumps(doc, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _series(*docs: dict) -> list[tuple[str, dict, bytes]]:
    return [(f"r{i}.json", d, _bytes(d)) for i, d in enumerate(docs)]


def _chain(base: dict, *supersessions: tuple[str, str]) -> list[tuple[str, dict, bytes]]:
    """base + one record per (version_context, (commit,kernel)) pair, each superseding the previous."""
    series = _series(base)
    for ctx, (commit, kernel) in supersessions:
        prev_path, _, prev_bytes = series[-1]
        rec = vf.bind({"record": ctx, "payload": ctx}, version_context=ctx, source_commit=commit,
                      kernel_digest=kernel, predecessor_path=prev_path, predecessor_bytes=prev_bytes)
        series.append((f"{ctx}.json", rec, _bytes(rec)))
    return series


class PureMechanism(unittest.TestCase):
    def setUp(self) -> None:
        self.base = {"record": "BASE", "payload": "legacy"}
        self.series = _chain(self.base, ("2.2.0", (C1, K1)))

    def test_a_valid_chain_selects_the_record_bound_to_the_tree(self):
        self.assertEqual(vf.validate_chain(self.series), [])
        path, rec = vf.select_for_tree(self.series, source_commit=C1, kernel_digest=K1)
        self.assertEqual(rec["record"], "2.2.0")
        self.assertEqual(path, "2.2.0.json")

    def test_the_same_series_selects_the_legacy_base_for_the_v2_1_context(self):
        # context-bound, NOT global newest: give the base's own binding and ask for the v2.1 tree -> the base.
        path, rec = vf.select_for_tree(self.series, source_commit=C0, kernel_digest=K0,
                                       legacy_binding=(C0, K0))
        self.assertEqual(rec["record"], "BASE")
        self.assertEqual(path, "r0.json")
        # and WITHOUT the legacy binding the v2.1 tree is simply not present (no silent fall-through to v2.2)
        with self.assertRaises(LookupError):
            vf.select_for_tree(self.series, source_commit=C0, kernel_digest=K0)

    def test_wrong_version_is_refused_with_no_fallback(self):
        with self.assertRaises(LookupError) as e:
            vf.select_for_tree(self.series, source_commit="zz" * 20, kernel_digest=K1)
        self.assertIn("no record binds this tree", str(e.exception))

    def test_a_missing_supersession_is_refused(self):
        base_only = _series(self.base)
        with self.assertRaises(LookupError):
            vf.select_for_tree(base_only, source_commit=C1, kernel_digest=K1)

    def test_a_tampered_record_fails_the_digest(self):
        path, doc, _ = self.series[-1]
        doc2 = json.loads(json.dumps(doc)); doc2["payload"] = "TAMPERED"
        bad = self.series[:-1] + [(path, doc2, _bytes(doc2))]
        self.assertTrue(any("tampered" in p for p in vf.validate_chain(bad)))
        with self.assertRaises(LookupError):
            vf.select_for_tree(bad, source_commit=C1, kernel_digest=K1)

    def test_a_broken_supersede_link_is_detected(self):
        path, doc, raw = self.series[-1]
        doc2 = json.loads(json.dumps(doc))
        doc2[vf.BLOCK]["supersedes"]["record_digest"] = "deadbeef" * 8
        doc2[vf.BLOCK]["record_digest"] = vf.body_digest(doc2)   # re-seal self so only the LINK is wrong
        bad = self.series[:-1] + [(path, doc2, _bytes(doc2))]
        probs = vf.validate_chain(bad)
        self.assertTrue(any("broken chain" in p for p in probs), probs)

    def test_an_ambiguous_head_is_refused(self):
        # two records bind the SAME tree (kernel) -> never pick one; refused as an ambiguous head
        extra = vf.bind({"record": "2.2.0-dup", "payload": "dup"}, version_context="2.2.0b", source_commit=C1,
                        kernel_digest=K1, predecessor_path=self.series[-1][0],
                        predecessor_bytes=self.series[-1][2])
        amb = self.series + [("dup.json", extra, _bytes(extra))]
        self.assertTrue(any("ambiguous head" in p for p in vf.validate_chain(amb)))
        with self.assertRaises(LookupError) as e:
            vf.select_for_tree(amb, source_commit=C1, kernel_digest=K1)
        self.assertIn("ambiguous head", str(e.exception))

    def test_a_rollback_reintroducing_a_superseded_kernel_is_detected(self):
        roll = _chain(self.base, ("2.2.0", (C1, K1)), ("2.2.1", ("c2" * 20, K0)), ("2.2.2", ("c3" * 20, K1)))
        self.assertTrue(any("rollback" in p for p in vf.validate_chain(roll)))

    def test_a_replayed_context_is_detected(self):
        a = _chain(self.base, ("2.2.0", (C1, K1)))
        dup = vf.bind({"record": "again"}, version_context="2.2.0", source_commit=C1, kernel_digest="k9" * 20,
                      predecessor_path=a[-1][0], predecessor_bytes=a[-1][2])
        a.append(("again.json", dup, _bytes(dup)))
        self.assertTrue(any("replay" in p or "duplicate" in p for p in vf.validate_chain(a)))

    def test_shape_rules_base_has_no_block_and_a_supersession_must(self):
        bad_base = vf.bind({"record": "x"}, version_context="2.2.0", source_commit=C1, kernel_digest=K1,
                           predecessor_path="none", predecessor_bytes=b"")
        self.assertTrue(any("base record must not carry" in p
                            for p in vf.validate_chain(_series(bad_base))))
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
        cls.supersession = vf.bind(dict(cls.body), version_context=cls._ver(), source_commit=cls.commit,
                                   kernel_digest=cls.tree, predecessor_path=p10.OUT_REL,
                                   predecessor_bytes=cls.legacy_bytes)
        cls.series = [(p10.OUT_REL, json.loads(cls.legacy_bytes), cls.legacy_bytes),
                      ("closure-evidence/v2/v2.2/P10-PROFILE-FREEZE.json", cls.supersession,
                       _bytes(cls.supersession))]

    @staticmethod
    def _ver() -> str:
        import tomllib
        return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]

    def test_the_legacy_checker_is_untouched_and_reports_the_record_stale_on_this_tree(self):
        # v2.1 verification path is the same code; on this advanced tree it honestly fails (it is one of the 21).
        self.assertIn("does not re-derive from the tree", " ".join(self.p10.check()))

    def test_the_chain_is_sound_and_the_selector_picks_the_v2_2_record_for_this_tree(self):
        self.assertEqual(vf.validate_chain(self.series), [])
        path, rec = vf.select_for_tree(self.series, source_commit=self.commit, kernel_digest=self.tree)
        self.assertEqual(path, "closure-evidence/v2/v2.2/P10-PROFILE-FREEZE.json")
        self.assertEqual(rec[vf.BLOCK]["kernel_digest"], self.tree)

    def test_the_selected_v2_2_record_re_derives_on_this_tree_with_no_problem(self):
        _, rec = vf.select_for_tree(self.series, source_commit=self.commit, kernel_digest=self.tree)
        body = {k: v for k, v in rec.items() if k != vf.BLOCK}
        fresh = {**self.p10.build(), "observed_at_write": body.get("observed_at_write")}
        self.assertEqual(self.p10.problems_of(fresh), [])
        self.assertEqual(self.p10.render(body), self.p10.render(fresh))   # the supersession IS this tree's derivation

    def test_the_supersession_binds_the_exact_current_tree_and_supersedes_the_committed_record(self):
        b = self.supersession[vf.BLOCK]
        self.assertEqual((b["source_commit"], b["kernel_digest"]), (self.commit, self.tree))
        self.assertEqual(b["supersedes"]["record_digest"], vf.digest_bytes(self.legacy_bytes))


if __name__ == "__main__":
    unittest.main()
