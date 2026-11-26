"""RULE-2 execution-order tables and the round-v2.3 order path (owner ruling 2026-11-26 §2).

(a) validation/v2/execution_order.py --write-freq derives the versioned kill-frequency rule (descending killed_by
frequency from a COMMITTED mutation record, ties by declared position) beside the T0 rule, byte-deterministically,
and --check re-derives whichever rule the table itself declares; (b) validation/v2/mutation.py --run-affected
--order threads the table entry into run_target so the ROUND record carries `execution_order` verbatim and its
rows the actual run order (the bo2 bench defect: the round entry dropped the order the v2.1 phase entry kept);
(c) the adversarial set: missing, stale, tampered, uncommitted and mismatched tables are each refused, named.
Enumeration, the kill bracket, ORD-4, T0 and every provenance rule are untouched law.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.v2.test_v21_execution_order import git  # noqa: E402 — the same hermetic-git helper
from validation.v2 import execution_order as eo  # noqa: E402
from validation.v2 import mutation as m  # noqa: E402

A, B, C, D = (f"tests/v2/test_{x}.py" for x in "abcd")
F, G = "aisef2/toy.py::f", "aisef2/toy.py::g"


def kill_entry(target: str, kill: list[str], killed_by: list[str]) -> dict:
    """A minimal record entry: one result per `killed_by` file (its killer), one survivor tail with none."""
    results = [{"mutant": f"L{i} x", "class": "KILLED", "killed": True, "killed_by": {"file": f, "first": "FAIL: t"}}
               for i, f in enumerate(killed_by)]
    results.append({"mutant": "L9 s", "class": "SURVIVED", "killed": False})
    return {"target": target, "runner": 2, "kill_tests": list(kill), "results": results}


class FreqTable(unittest.TestCase):
    def setUp(self):
        self.root = root = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory())).resolve() / "repo"
        (root / "evidence").mkdir(parents=True)
        git(root, "init", "-q", "-b", "main")
        self.enterContext(mock.patch.object(eo, "ROOT", root))
        self.enterContext(mock.patch("builtins.print"))
        self.record, self.table = root / "evidence/MUTATION.json", root / "freq-order.json"
        superseded = kill_entry(F, [A, B, C], [B, B, B])            # history: a later entry takes F over
        entries = [superseded, kill_entry(F, [A, B, C], [A, C, C]), kill_entry(G, [C, A], []),
                   {"target": "aisef2/toy.py::h", "runner": 2, "error": "stub", "results": []}]   # no kill set: no order
        self.record.write_text(json.dumps({"record": "r", "entries": entries}), encoding="utf-8")

    def commit(self, *paths: str) -> str:
        git(self.root, "add", *paths)
        git(self.root, "commit", "-q", "-m", "x")
        return git(self.root, "rev-parse", "HEAD")

    def test_the_table_follows_rule_2_from_a_committed_record_and_check_re_derives_it(self):
        with self.assertRaisesRegex(SystemExit, "evidence/MUTATION.json is not a file committed at HEAD"):
            eo.main(["--write-freq", str(self.record), str(self.table)])
        self.assertFalse(self.table.exists())
        self.commit("evidence/MUTATION.json")
        self.assertEqual(eo.main(["--write-freq", str(self.record), str(self.table)]), 0)
        doc = json.loads(self.table.read_text(encoding="utf-8"))
        src = {"path": "evidence/MUTATION.json", "sha256": hashlib.sha256(self.record.read_bytes()).hexdigest()}
        self.assertEqual((doc["rule"], doc["rule_id"], doc["from"]), (eo.RULE2, eo.RULE2_ID, src))
        self.assertEqual(doc["orders"], {   # F: the LAST entry wins (C twice, A once, B never); G: all ties keep
            F: {"files": [C, A, B], "kills": [2, 1, 0], "from": src, "rule": eo.RULE2_ID},   # the declared position
            G: {"files": [C, A], "kills": [0, 0], "from": src, "rule": eo.RULE2_ID}})
        self.assertEqual([m._order_problem(x, k) for x, k in ((doc["orders"][F], [A, B, C]),
                                                             (doc["orders"][G], [C, A]))], [None, None])
        self.assertEqual(eo.main(["--check", str(self.table)]), 0)

    def test_the_same_committed_record_derives_byte_identical_tables(self):
        self.commit("evidence/MUTATION.json")
        other = self.root / "freq-order-2.json"
        eo.main(["--write-freq", str(self.record), str(self.table)])
        eo.main(["--write-freq", str(self.record), str(other)])
        self.assertEqual(self.table.read_bytes(), other.read_bytes())

    def test_a_phase_shaped_record_derives_too_and_a_non_record_is_refused(self):
        self.record.write_text(json.dumps({"record": "r", "targets": [kill_entry(F, [A, B], [B])]}), encoding="utf-8")
        self.commit("evidence/MUTATION.json")
        eo.main(["--write-freq", str(self.record), str(self.table)])
        self.assertEqual(json.loads(self.table.read_text(encoding="utf-8"))["orders"][F]["files"], [B, A])
        self.record.write_text(json.dumps({"record": "r"}), encoding="utf-8")
        self.commit("evidence/MUTATION.json")
        with self.assertRaisesRegex(SystemExit, "not a mutation record"):
            eo.main(["--write-freq", str(self.record), str(self.table)])

    def test_missing_stale_tampered_and_unknown_rule_are_each_named(self):
        self.commit("evidence/MUTATION.json")
        eo.main(["--write-freq", str(self.record), str(self.table)])
        self.assertRegex(eo.check(self.root / "no-such-table.json")[0], "cannot be read")

        doc = json.loads(self.table.read_text(encoding="utf-8"))   # tampered: one entry's order edited by hand
        doc["orders"][F]["files"] = [A, B, C]
        self.table.write_text(eo.render(doc), encoding="utf-8")
        self.assertEqual(eo.check(self.table),
                         [f"{self.table} is not what evidence/MUTATION.json derives now — re-run --write-freq"])
        eo.main(["--write-freq", str(self.record), str(self.table)])

        rec = json.loads(self.record.read_text(encoding="utf-8"))   # stale: the source record moved on
        rec["entries"].append(kill_entry(F, [A, B, C], [B, B, B, B]))
        self.record.write_text(json.dumps(rec), encoding="utf-8")
        self.assertEqual(eo.check(self.table), ["evidence/MUTATION.json is not a file committed at HEAD: the table "
                                                "is derived from a committed record only"])   # uncommitted source
        self.commit("evidence/MUTATION.json")
        self.assertEqual(eo.check(self.table),
                         [f"{self.table} is not what evidence/MUTATION.json derives now — re-run --write-freq"])
        eo.main(["--write-freq", str(self.record), str(self.table)])
        self.assertEqual(json.loads(self.table.read_text(encoding="utf-8"))["orders"][F]["files"], [B, A, C])
        self.assertEqual(eo.check(self.table), [])

        doc = json.loads(self.table.read_text(encoding="utf-8"))   # an unknown rule is never guessed at
        doc["rule_id"] = "no-such-rule/9"
        self.table.write_text(eo.render(doc), encoding="utf-8")
        self.assertRegex(eo.check(self.table)[0], "unknown rule_id 'no-such-rule/9'")

    def test_a_mismatched_entry_is_not_an_execution_order_of_the_kill_set(self):
        src = {"path": "evidence/MUTATION.json", "sha256": "a" * 64}
        good = {"files": [B, A], "from": src, "rule": eo.RULE2_ID}
        self.assertIsNone(m._order_problem(good, [A, B]))
        for bad, kill in ((dict(good, files=[B, A, A]), [A, B]),       # a file repeated: not the same multiset
                          (dict(good, files=[B]), [A, B]),             # a file missing
                          (good, [A, C]),                              # the wrong target's kill set
                          (dict(good, **{"from": {}}), [A, B])):       # no measurement named
            with self.subTest(bad=bad, kill=kill):
                self.assertIsNotNone(m._order_problem(bad, kill))


class RoundOrderTable(unittest.TestCase):
    """mutation._order_table — the one §7.2 validation both `run --order` and `--run-affected --order` go through."""

    def setUp(self):
        self.root = root = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory())).resolve() / "repo"
        root.mkdir(parents=True)
        git(root, "init", "-q", "-b", "main")
        self.enterContext(mock.patch.object(m, "ROOT", root))
        self.enterContext(mock.patch("builtins.print"))
        self.kill_of = {F: [A, B]}.get
        self.tbl = root / "order.json"
        self.entry = {"files": [B, A], "from": {"path": "evidence/MUTATION.json", "sha256": "a" * 64}}
        self.tbl.write_text(json.dumps({"orders": {F: self.entry}}), encoding="utf-8")

    def test_a_committed_table_is_stamped_and_an_uncommitted_one_carries_no_commit(self):
        table, stamp = m._order_table(self.tbl, self.kill_of)   # uncommitted: WARNING, commit None — --check refuses it
        self.assertEqual((table, stamp["table"], stamp["table_commit"]), ({F: self.entry}, "order.json", None))
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "x")
        head = git(self.root, "rev-parse", "HEAD")
        table, stamp = m._order_table(self.tbl, self.kill_of)
        self.assertEqual(stamp, {"table": "order.json", "table_commit": head,
                                 "table_sha256": hashlib.sha256(self.tbl.read_bytes()).hexdigest()})

    def test_every_refusal_happens_before_anything_runs(self):
        with self.assertRaisesRegex(SystemExit, "refused, nothing ran"):                      # missing table file
            m._order_table(self.root / "none.json", self.kill_of)
        for doc, why in (({"rows": {}}, "has no `orders` object"),
                         ({"orders": {G: self.entry}}, "not a mutation target in the execution-order table"),
                         ({"orders": {F: dict(self.entry, files=[B])}}, "refused, nothing ran")):   # mismatched set
            with self.subTest(why=why):
                self.tbl.write_text(json.dumps(doc), encoding="utf-8")
                with self.assertRaisesRegex(SystemExit, why):
                    m._order_table(self.tbl, self.kill_of)


class RoundWriter(unittest.TestCase):
    """--run-affected --order: the round record carries `execution_order` verbatim (the bo2 defect fixed); without
    an order the appended entry's shape is byte-for-byte the old one."""

    def setUp(self):
        self.root = root = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory())).resolve() / "repo"
        root.mkdir(parents=True)
        git(root, "init", "-q", "-b", "main")
        self.entry = {"files": [B, A], "from": {"path": "evidence/MUTATION.json", "sha256": "a" * 64}}
        self.tbl = root / "order.json"
        self.tbl.write_text(json.dumps({"orders": {F: self.entry}}), encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "x")
        self.head = git(root, "rev-parse", "HEAD")
        self.enterContext(mock.patch.object(m, "ROOT", root))
        self.enterContext(mock.patch.object(m, "V23_NEW_TARGETS", {F: [A, B]}))
        self.enterContext(mock.patch.object(m, "V23_KILL_APPEND", {}))
        self.enterContext(mock.patch("validation.v23.impact.classify", return_value=[]))
        self.enterContext(mock.patch.object(m, "_worker", return_value="w0"))
        self.enterContext(mock.patch.object(m, "_earlier", return_value=[]))
        self.enterContext(mock.patch.object(m, "_pristine", side_effect=lambda root, dst: (dst, "0" * 64)))
        self.enterContext(mock.patch.object(m, "_v23_identity",
                                            return_value={"measured_on": "h" * 40, "dirty": False}))
        self.enterContext(mock.patch.object(m, "check", return_value=[]))
        self.enterContext(mock.patch("builtins.print"))

        def echo(root, target, tests, pristine=None, on_mutant=None, t0_only=False, order=None):
            # exactly run_target's record head (mutation.py: `out = {...}`): kill_tests stays the DECLARED list
            # (ORD-4) and `execution_order` is the entry kept whole — nothing else about the result moves
            return {"target": target, "runner": 2, "kill_tests": list(tests),
                    **({"execution_order": order} if order is not None else {}),
                    "mutants": 1, "killed": 1, "survivors": [],
                    "results": [{"mutant": "L1 x", "class": "KILLED", "killed": True}], "classes": {}}
        self.run_target = self.enterContext(mock.patch.object(m, "run_target", side_effect=echo))

    def entries(self) -> list[dict]:
        return json.loads((self.root / m.V23_REL).read_text(encoding="utf-8"))["entries"]

    def test_with_order_the_round_entry_carries_execution_order_and_the_table_stamp_verbatim(self):
        self.assertEqual(m.main(["--run-affected", "--order", str(self.tbl), F]), 0)
        stamp = {"table": "order.json", "table_sha256": hashlib.sha256(self.tbl.read_bytes()).hexdigest(),
                 "table_commit": self.head}
        self.assertEqual(self.run_target.call_args.kwargs["order"], {**self.entry, **stamp})
        (e,) = self.entries()
        self.assertEqual(e["execution_order"], {**self.entry, **stamp})   # verbatim, independently verifiable
        self.assertEqual(e["kill_tests"], [A, B])                         # the declared list, unchanged (ORD-4)
        self.assertEqual(e["identity"], {"measured_on": "h" * 40, "dirty": False})

    def test_without_an_order_the_appended_entry_shape_is_unchanged(self):
        self.assertEqual(m.main(["--run-affected", F]), 0)
        self.assertEqual(self.run_target.call_args.kwargs["order"], None)
        (e,) = self.entries()
        self.assertNotIn("execution_order", e)
        self.assertEqual(sorted(e), ["classes", "identity", "kill_tests", "killed", "mutants", "results",
                                     "runner", "survivors", "target"])

    def test_the_table_is_validated_against_the_round_kill_set_not_the_declared_one(self):
        with mock.patch.object(m, "V23_KILL_APPEND", {F: [C]}):   # the round runs [A, B, C]: a [B, A] table lies
            with self.assertRaisesRegex(SystemExit, "execution-order table refused, nothing ran"):
                m.main(["--run-affected", "--order", str(self.tbl), F])
        self.run_target.assert_not_called()
        self.assertFalse((self.root / m.V23_REL).exists())

    def test_misuse_is_refused_before_anything_runs(self):
        for argv in (["--run-affected", F, "--order", str(self.tbl)],            # --order not first
                     ["--run-affected", "--order"],                              # no table
                     ["--run-affected", "--order", str(self.tbl), "--order", str(self.tbl)],   # twice
                     ["--affected", "--order", str(self.tbl)]):                  # --affected never takes one
            with self.subTest(argv=argv):
                with self.assertRaisesRegex(SystemExit, "usage: mutation.py --run-affected --order"):
                    m.main(argv)
        unknown = self.root / "unknown.json"                                     # a wrong-target table: refused whole
        unknown.write_text(json.dumps({"orders": {G: self.entry}}), encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "not a mutation target in the execution-order table"):
            m.main(["--run-affected", "--order", str(unknown), F])
        self.run_target.assert_not_called()
        self.assertFalse((self.root / m.V23_REL).exists())


class AcceptanceReader(unittest.TestCase):
    """_problems_v2 on a round entry WITH execution_order: the table stamp is demanded; entries WITHOUT the key are
    the old rule, untouched (tests/v23/test_v23_b1_admissibility.py pins those)."""

    SRC, TGT, KILL = "aisef2/toy.py", "aisef2/toy.py::f", "tests/v2/test_a.py"

    def setUp(self):
        self.root = root = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory())).resolve() / "repo"
        root.mkdir(parents=True)
        (root / self.SRC).parent.mkdir(parents=True)
        (root / self.SRC).write_text("def f(x):\n    return x + 1\n", encoding="utf-8")

    def entry(self, **over) -> dict:
        hdr = "FAIL: t (v2.test_a.T.t) | AssertionError"
        control = {"file": self.KILL, "role": "control", "exit": 0, "outcome": "PASS", "why": None, "ran": 1}
        row = {"mutant": "L1 x", "class": "KILLED", "killed": True, "killed_by": {"file": self.KILL, "first": hdr},
               "files": [{"file": self.KILL, "exit": 1, "outcome": "FAIL", "why": None, "ran": 1, "first": hdr},
                         control, dict(control),
                         {"file": self.KILL, "role": "rerun", "exit": 1, "outcome": "FAIL", "why": None, "ran": 1,
                          "first": hdr}]}
        live = m.source_digest((self.root / self.SRC).read_text(encoding="utf-8"))
        return {"target": self.TGT, "runner": 2, "source_sha256": live, "kill_tests": [self.KILL], "mutants": 1,
                "killed": 1, "survivors": [], "results": [row],
                "t0": [{"file": self.KILL, "role": "t0", "exit": 0, "outcome": "PASS", "why": None, "ran": 1}],
                **over}

    def order(self, **over) -> dict:
        return {"files": [self.KILL], "from": {"path": "evidence/MUTATION.json", "sha256": "a" * 64},
                "table": "order.json", "table_sha256": "b" * 64, "table_commit": "c" * 40, **over}

    def test_the_stamp_rules_hold_and_an_entry_without_the_key_is_untouched(self):
        self.assertEqual(m._problems_v2(self.entry(), self.root), [])                         # no execution_order
        self.assertEqual(m._problems_v2(self.entry(execution_order=self.order()), self.root), [])
        cases = {
            "names no table and its sha256": self.order(table=None),
            "names no table and its sha256 ": self.order(table_sha256="zz"),
            "was not a file committed at the run's HEAD": self.order(table_commit=None),
            "is not the kill set in another order": self.order(files=[self.KILL, self.KILL]),
            "names no measurement": {"files": [self.KILL]},
        }
        for why, order in cases.items():
            with self.subTest(why=why):
                problems = m._problems_v2(self.entry(execution_order=order), self.root)
                self.assertTrue(any(why.strip() in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
