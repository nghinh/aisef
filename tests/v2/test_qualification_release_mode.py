"""V2.0 release charter S4/S5: the qualification subject is DATA. `common.candidate()` reads the RC2 freeze record when it
exists (release mode: the RC, its kernel tree, its subject trees, its shipped aisef tree, release output directories) and
is the Cycle-2 subject exactly otherwise; Cycle-2 history keeps meaning c11615a in either mode.

Every freeze record here is written to a temporary directory and `common.RC_FREEZE` is pointed at it: the repository's
closure-evidence/v2/release/V2.0-RC2-FREEZE.json is never written."""

from __future__ import annotations

import ast
import contextlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from validation.qualification import common as C  # noqa: E402
from validation.qualification import release_rc  # noqa: E402

C2_CANDIDATE, C2_KERNEL = "c11615aeb1dd9e6ff992b6190f8c39a272636742", "254d8f559b879c210c4936321022f1350c4b2f89"
C2_TREES = {"validation/v2": "7686f004167fc5e940b06bf6ff0248f068d8d116", "tests/v2": "fb9d8e17728a893083575638d9bad3b4faa62196"}
C2_OUTS = ("closure-evidence/v2/cycle2/Q0-Q3-R4", "closure-evidence/v2/cycle2/Q4-FINAL", "closure-evidence/v2/cycle2/Q5-FINAL")
#: V2.1: the release output directories carry the tree's own candidate tag (release_rc.TAG: 2.0.0's was the bare RC2)
RELEASE_OUTS = tuple(f"closure-evidence/v2/release/{rung}-{release_rc.TAG}" for rung in ("Q0-Q3", "Q4", "Q5"))
SUBJECT_NAMES = {"MODE", "SEMANTIC_CANDIDATE", "SEAL_COMMIT", "KERNEL_TREE", "SUBJECT_TREES", "V1_PRODUCT_TREE", "OUT_REL",
                 "Q4_OUT_REL", "Q5_OUT_REL"}


def freeze_record(sha: str) -> dict:
    """The shape release_rc.freeze writes, from `sha`'s own git objects (the artifact digests are not the subject)."""
    return {"rc": {"sha": sha, "version": release_rc.VERSION, "source_date_epoch": 0,
                   "shipped_trees": {rel: C.git("rev-parse", f"{sha}:{rel}") for rel in release_rc.SHIPPED}},
            "kernel": {"tree": C.git("rev-parse", f"{sha}:aisef2"), "digest": release_rc.kernel_digest_at(sha)},
            "artifacts": {"sha256": {}}, "problems": [], "verdict": "FROZEN"}


@contextlib.contextmanager
def frozen(rec: dict | None):
    """common.RC_FREEZE pointed at a temporary file holding `rec` (None: at a path that does not exist)."""
    with tempfile.TemporaryDirectory(prefix="aisef-rc-freeze-") as d:
        path = pathlib.Path(d) / "V2.0-RC1-FREEZE.json"
        if rec is not None:
            path.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        with mock.patch.object(C, "RC_FREEZE", path):
            yield path


class Subject(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.head = C.git("rev-parse", "HEAD")
        cls.rec = freeze_record(cls.head)

    def test_a_without_a_freeze_record_the_subject_is_exactly_cycle_2(self):
        with frozen(None):
            s = C.candidate()
            ident = C.identity()
        self.assertEqual((s["mode"], s["semantic_candidate"], s["seal_commit"], s["kernel_tree"]), ("cycle2", C2_CANDIDATE, C2_CANDIDATE, C2_KERNEL))
        self.assertEqual(s["subject_trees"], C2_TREES)
        self.assertEqual(s["v1_product_tree"], "4359f347378e84fcac2d213128c7c26f282c13c0")
        self.assertEqual((s["out_rel"], s["q4_out_rel"], s["q5_out_rel"]), C2_OUTS)
        self.assertIsNone(s["freeze"])
        self.assertEqual((ident["mode"], ident["release"], ident["semantic_candidate"], ident["kernel_tree"]), ("cycle2", None, C2_CANDIDATE, C2_KERNEL))
        self.assertEqual(tuple(ident["outputs"].values()), C2_OUTS)
        self.assertEqual({rel: t["frozen"] for rel, t in ident["subject_trees"].items()}, C2_TREES)

    def test_the_rungs_bind_the_one_subject(self):
        from validation.qualification import q4, q4_aggregate, q5, summary
        s = C.candidate()
        self.assertEqual((C.MODE, C.SEMANTIC_CANDIDATE, C.SEAL_COMMIT, C.KERNEL_TREE, C.SUBJECT_TREES, C.V1_PRODUCT_TREE),
                         (s["mode"], s["semantic_candidate"], s["seal_commit"], s["kernel_tree"], s["subject_trees"], s["v1_product_tree"]))
        self.assertEqual((C.OUT_REL, C.Q4_OUT_REL, C.Q5_OUT_REL), (s["out_rel"], s["q4_out_rel"], s["q5_out_rel"]))
        self.assertEqual((q4.OUT_REL, q4.SEMANTIC_CANDIDATE, q4.KERNEL_TREE), (C.Q4_OUT_REL, C.SEMANTIC_CANDIDATE, C.KERNEL_TREE))
        self.assertEqual((q5.OUT_REL, q5.SEMANTIC_CANDIDATE, q5.KERNEL_TREE), (C.Q5_OUT_REL, C.SEMANTIC_CANDIDATE, C.KERNEL_TREE))
        self.assertEqual((summary.SUMMARY_REL, q4_aggregate.P7_EVIDENCE[0]), (f"{C.OUT_REL}/SUMMARY.json",) * 2)
        self.assertEqual(q4_aggregate.P7_EVIDENCE[1:], q4_aggregate.CYCLE2_P7_EVIDENCE[1:])

    def test_b_a_freeze_record_naming_head_is_release_mode(self):
        with frozen(self.rec) as path:
            s = C.candidate()
            ident = C.identity()
            problems = C.subject_problems(ident)
            record_id = {"path": path.as_posix(), "sha256": C.lf_sha(path)}
        self.assertEqual((s["mode"], s["semantic_candidate"], s["seal_commit"]), ("release", self.head, self.head))
        self.assertEqual((s["out_rel"], s["q4_out_rel"], s["q5_out_rel"]), RELEASE_OUTS)
        self.assertEqual(s["v1_product_tree"], self.rec["rc"]["shipped_trees"]["aisef"])
        self.assertEqual(ident["mode"], "release")
        self.assertEqual(tuple(ident["outputs"].values()), RELEASE_OUTS)
        self.assertTrue(ident["kernel_tree_is_the_candidates"])
        self.assertEqual((ident["kernel_tree"], ident["candidate_kernel_tree"]), (self.rec["kernel"]["tree"],) * 2)
        self.assertEqual(set(ident["subject_trees"]), {"validation/v2", "tests/v2"})
        for rel, t in ident["subject_trees"].items():
            self.assertEqual(t["head"], t["candidate"], rel)
            self.assertEqual(t["candidate"], t["frozen"], rel)
        self.assertTrue(ident["head_is_after_the_seal"])
        self.assertTrue(ident["v1_product_tree_unchanged"])
        rel = ident["release"]
        self.assertEqual(rel["freeze_record"], record_id)
        self.assertEqual((rel["rc_version"], rel["kernel_digest"], rel["rc_check_problems"]), (release_rc.VERSION, self.rec["kernel"]["digest"], []))
        self.assertIn("G1", rel["v1_product_tree"]["note"])
        self.assertEqual(rel["v1_product_tree"]["cycle2"], "4359f347378e84fcac2d213128c7c26f282c13c0")
        self.assertEqual(problems, [])

    def test_c_a_freeze_record_whose_kernel_tree_is_not_heads_fails_the_candidate_check(self):
        rec = json.loads(json.dumps(self.rec))
        rec["kernel"]["tree"] = C2_KERNEL
        with frozen(rec):
            ident = C.identity()
            problems = C.subject_problems(ident)
        self.assertEqual(ident["mode"], "release")
        self.assertFalse(ident["kernel_tree_is_the_candidates"])
        self.assertTrue(any(p.startswith("HEAD's aisef2 tree") and C2_KERNEL in p for p in problems), problems)
        self.assertIn("the semantic candidate does not carry the frozen kernel tree", problems)
        self.assertIn(f"the {release_rc.RC} freeze record: the kernel identity is not the RC commit's", problems)

    def test_release_q2_reads_the_calibrations_the_rc_ships(self):
        import importlib
        from aisef2.probe import catalog
        from validation.qualification import q2, release_calibration
        from aisef2.probe.calibration import executing     # V2.1 (V2-007): a calibration binds the bytes that run
        declared = {(e.probe_id, executing(e.factory), cls) for e in catalog.CATALOG for cls in importlib.import_module(e.factory.__module__).CLASSES}
        with mock.patch.object(C, "MODE", "release"):
            self.assertEqual(q2._calibration_records(), (release_calibration.RECORD_REL,))
            self.assertEqual(q2._committed_calibration_keys(), declared)
        with mock.patch.object(C, "MODE", "cycle2"):
            self.assertEqual(q2._calibration_records(), q2.CYCLE2_CALIBRATION_RECORDS)


V2_006, V2_007 = "AISEF-V2-RFC-AMENDMENT-V2-006.json", "AISEF-V2-RFC-AMENDMENT-V2-007.json"
LINEAGE_FAILS = "the effective RFC lineage does not end at V2-007 unbroken"
HISTORY_FAILS = "the 2.0 freeze manifest is not intact history"


class V21Lineage(unittest.TestCase):
    """2.1: the rungs require the lineage to end at V2-007 with V2-006 the link before it, and the 2.0 freeze manifest
    (history: the lineage up to V2-006) intact; q0 measures that V2-007 changes no freeze-table row."""

    VARIANTS = (("the lineage skips V2-006", lambda r: r.__setitem__("lineage", r["lineage"][:-2] + [V2_007]), LINEAGE_FAILS),
                ("the lineage ends at V2-006", lambda r: r.__setitem__("lineage_end", V2_006), LINEAGE_FAILS),
                ("the 2.0 manifest is not history",
                 lambda r: r.__setitem__("v2_0_manifest_history_problems", ["differs from its blob at v2.0.0"]), HISTORY_FAILS))

    def _assert_kills(self, subject_problems, ident: dict):
        self.assertEqual(ident["rfc"]["lineage"][-2:], [V2_006, V2_007])
        self.assertEqual(ident["rfc"]["v2_0_manifest_history_problems"], [])
        clean = subject_problems(ident)
        self.assertFalse([p for p in clean if p == LINEAGE_FAILS or p.startswith(HISTORY_FAILS)], clean)
        for name, mutate, reason in self.VARIANTS:
            bad = json.loads(json.dumps(ident))
            mutate(bad["rfc"])
            self.assertTrue(any(p.startswith(reason) for p in subject_problems(bad)), name)

    def test_common_subject_problems(self):
        with frozen(freeze_record(C.git("rev-parse", "HEAD"))):
            ident = C.identity()
        self._assert_kills(C.subject_problems, ident)

    def test_q5_subject_problems(self):
        from validation.qualification import q5
        import freeze_manifest as fm
        _, links, broken = fm.lineage(C.ROOT)
        ident = {"kernel_tree_is_the_candidates": True, "working_tree_clean": True, "dirty": [], "probe": {"corrected": True},
                 "corpus": {"items": {"x": {}}},
                 "rfc": {"lineage_end": pathlib.Path(links[-1]["record"]).name, "broken_links": broken,
                         "lineage": [pathlib.Path(x["record"]).name for x in links],
                         "v2_0_manifest_history_problems": fm.history_problems(C.ROOT)}}
        self.assertEqual(q5.subject_problems(ident), [])
        self._assert_kills(q5.subject_problems, ident)

    def test_q0_measures_the_rows_and_reads_the_2_0_lineage_as_history(self):
        from validation.qualification import q0
        import freeze_manifest as fm
        latest = json.loads((C.ROOT / fm.AMENDMENTS[-1]).read_text(encoding="utf-8"))
        self.assertEqual(q0.v21_lineage_history(C.ROOT, latest), {"lineage_ends_at_V2_006": True, "v2_007_changes_no_row": True})

        def in_copy(edits=None, claim=None):
            with tempfile.TemporaryDirectory() as t:
                root = pathlib.Path(t)
                for rel in (fm.HISTORY_MANIFEST_REL, fm.MANIFEST_REL):
                    (root / rel).parent.mkdir(parents=True, exist_ok=True)
                    d = json.loads((C.ROOT / rel).read_text(encoding="utf-8"))
                    (edits or {}).get(rel, lambda _: None)(d)
                    (root / rel).write_text(json.dumps(d), encoding="utf-8")
                return q0.v21_lineage_history(root, claim or latest)

        def row(d):
            d["frozen_items"][4]["row_sha256"] = "0" * 64

        def drop_row(d):
            d["frozen_items"].pop()
        self.assertFalse(in_copy({fm.MANIFEST_REL: row})["v2_007_changes_no_row"])        # a changed row, the claim says []
        self.assertFalse(in_copy({fm.HISTORY_MANIFEST_REL: row})["v2_007_changes_no_row"])
        self.assertFalse(in_copy({fm.HISTORY_MANIFEST_REL: drop_row, fm.MANIFEST_REL: drop_row})["v2_007_changes_no_row"])  # not F1-F11
        self.assertFalse(in_copy(claim={**latest, "frozen_items_changed": ["F5"]})["v2_007_changes_no_row"])
        self.assertFalse(in_copy(claim={**latest, "freeze_table_digest": {"before": "a", "after": "b"}})["v2_007_changes_no_row"])
        ends = in_copy({fm.HISTORY_MANIFEST_REL: lambda d: d["approval_lineage"].pop()})
        self.assertEqual(ends, {"lineage_ends_at_V2_006": False, "v2_007_changes_no_row": True})


class Cycle2History(unittest.TestCase):
    """The Cycle-2 history consumers read the CYCLE2_* names only, so they keep naming c11615a under a release subject."""
    HISTORY = ("validation/qualification/c2_p6_closure.py", "validation/qualification/c2_p9_preflight.py")

    def test_d_the_cycle_2_names_are_c11615a(self):
        self.assertEqual((C.CYCLE2_SEMANTIC_CANDIDATE, C.CYCLE2_SEAL_COMMIT, C.CYCLE2_KERNEL_TREE), (C2_CANDIDATE, C2_CANDIDATE, C2_KERNEL))
        self.assertEqual((C.CYCLE2_SUBJECT_TREES, C.CYCLE2_V1_PRODUCT_TREE), (C2_TREES, "4359f347378e84fcac2d213128c7c26f282c13c0"))
        self.assertEqual((C.CYCLE2_OUT_REL, C.CYCLE2_Q4_OUT_REL, C.CYCLE2_Q5_OUT_REL), C2_OUTS)

    def test_d_history_reads_no_subject_name(self):
        for rel in self.HISTORY:
            tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
            used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "C"}
            self.assertEqual(used & SUBJECT_NAMES, set(), rel)
            self.assertLessEqual({"CYCLE2_SEMANTIC_CANDIDATE", "CYCLE2_KERNEL_TREE"}, used, rel)
        p10 = ast.parse((ROOT / "validation/qualification/p10.py").read_text(encoding="utf-8"))
        attrs = {n.attr for n in ast.walk(p10) if isinstance(n, ast.Attribute)}
        self.assertIn("CYCLE2_P7_EVIDENCE", attrs)
        self.assertNotIn("P7_EVIDENCE", attrs)

    def test_d_the_p6_closure_names_c11615a_under_a_release_subject(self):
        from validation.qualification import c2_p6_closure
        release = {"SEMANTIC_CANDIDATE": "f" * 40, "SEAL_COMMIT": "f" * 40, "KERNEL_TREE": "e" * 40,
                   "SUBJECT_TREES": {"validation/v2": "d" * 40, "tests/v2": "c" * 40}, "OUT_REL": RELEASE_OUTS[0], "MODE": "release"}
        with mock.patch.multiple(C, **release):
            rec = c2_p6_closure.build()
        self.assertEqual((rec["candidate"]["commit"], rec["candidate"]["aisef2_tree"], rec["candidate"]["subject_trees"]),
                         (C2_CANDIDATE, C2_KERNEL, C2_TREES))
        self.assertEqual(rec["qualification"]["summary"]["path"], f"{C2_OUTS[0]}/SUMMARY.json")
        self.assertTrue(all(r["path"].startswith(C2_OUTS[0] + "/") for r in rec["qualification"]["records"]))


if __name__ == "__main__":
    unittest.main()
