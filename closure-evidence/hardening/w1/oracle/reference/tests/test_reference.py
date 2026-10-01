"""§11: unit tests for the reference, runnable with `python -m unittest discover` and with pytest."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ledgerlock import ConflictError, CorruptionError, Ledger
from ledgerlock.cli import main


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = Path(self._t.name)
        self.p = self.d / "l.jsonl"
        self.led = Ledger(self.p)

    def tearDown(self):
        self._t.cleanup()

    def lines(self) -> int:
        return self.p.read_bytes().count(b"\n") if self.p.exists() else 0


class TestChain(Base):
    def test_nfc_and_nfd_are_one_key(self):  # §3.1
        self.led.append("put", "é", "r1", 1, value=1)
        with self.assertRaises(ConflictError):
            self.led.append("put", "é", "r2", 2, value=2)
        self.assertEqual(json.loads(self.led.snapshot()), {"é": 1})

    def test_chain_links_and_tamper_is_detected_from_disk(self):  # §3.2–§3.4
        self.led.apply_batch([("put", "a", 1, "r1", 1), ("put", "b", 2, "r2", 2)])
        recs = [json.loads(ln) for ln in self.p.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(recs[0]["prev_hash"], "GENESIS")
        self.assertEqual(recs[1]["prev_hash"], recs[0]["hash"])
        self.assertEqual(self.led.verify(), {"ok": True, "first_bad_index": None})
        recs[1]["value"] = 9
        self.p.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")  # any serialisation
        self.assertEqual(self.led.verify(), {"ok": False, "first_bad_index": 1})

    def test_an_empty_ledger_verifies(self):
        self.p.write_bytes(b"")
        self.assertTrue(self.led.verify()["ok"])


class TestIdempotency(Base):
    def test_replay_conflict_and_tombstone(self):  # §4
        first = self.led.apply_batch([("put", "k", 1, "r1", 1)])
        n = self.lines()
        self.assertEqual(self.led.apply_batch([("put", "k", 1, "r1", 1)]), first)
        self.assertEqual(self.lines(), n)
        for op in ("put", "delete"):
            with self.assertRaises(ConflictError):
                self.led.apply_batch([(op, "k", 2, "r2", 2)])
        self.assertEqual(self.lines(), n)
        self.led.apply_batch([("delete", "t", None, "d1", 3)])  # a tombstone on a fresh key
        with self.assertRaises(ConflictError):
            self.led.apply_batch([("put", "t", 1, "d2", 4)])
        m = self.lines()
        self.led.apply_batch([("put", "t", 1, "d1", 5)])  # §4.4: same rid as the tombstone → replay
        self.assertEqual(self.lines(), m)

    def test_a_conflicting_batch_writes_nothing(self):  # §5
        self.led.apply_batch([("put", "k", 1, "r1", 1)])
        before = self.p.read_bytes()
        with self.assertRaises(ConflictError):
            self.led.apply_batch([("put", "new", 1, "n1", 2), ("put", "k", 2, "r2", 3)])
        self.assertEqual(self.p.read_bytes(), before)

    def test_bad_op_or_rid(self):
        with self.assertRaises(ValueError):
            self.led.apply_batch([("upsert", "k", 1, "r", 1)])
        with self.assertRaises(ValueError):
            self.led.apply_batch([("put", "k", 1, "", 1)])


class TestSnapshotAndRepair(Base):
    def test_snapshot_is_sorted_and_stable(self):  # §6
        self.led.apply_batch([("put", "b", 1, "r1", 1), ("put", "a", 2, "r2", 2), ("delete", "gone", None, "g1", 3)])
        s1 = self.led.snapshot()
        self.assertEqual(s1, self.led.snapshot())
        self.assertEqual(list(json.loads(s1)), ["a", "b"])

    def test_repair_tail(self):  # §7
        self.led.apply_batch([("put", "a", 1, "r1", 1), ("put", "b", 2, "r2", 2)])
        good = self.p.read_bytes()
        self.assertFalse(self.led.repair_tail())
        self.p.write_bytes(good + b'{"op": "pu')
        self.assertFalse(self.led.verify()["ok"])
        self.assertTrue(self.led.repair_tail())
        self.assertEqual(self.p.read_bytes(), good)
        self.p.write_bytes(good.replace(b'"value":1', b'"value":7'))
        with self.assertRaises(CorruptionError):
            self.led.repair_tail()


class TestCli(Base):
    def batch(self, ops) -> str:
        f = self.d / "b.json"
        f.write_text(json.dumps(ops), encoding="utf-8")
        return str(f)

    def test_exit_codes(self):  # §9
        self.p.write_bytes(b"")
        self.assertEqual(main(["verify", str(self.p)]), 0)
        self.assertEqual(main(["verify", str(self.d / "missing.jsonl")]), 3)
        self.assertEqual(main(["apply", "--batch", self.batch([{"op": "put", "key": "k", "value": 1, "rid": "r1", "ts": 1}]), str(self.p)]), 0)
        self.assertEqual(main(["apply", "--batch", self.batch([{"op": "put", "key": "k", "value": 2, "rid": "r2", "ts": 2}]), str(self.p)]), 4)
        self.assertEqual(main(["apply", "--batch", self.batch({"not": "a list"}), str(self.p)]), 2)
        self.assertEqual(main(["apply", "--batch", str(self.d / "absent.json"), str(self.p)]), 3)
        self.assertEqual(main(["bogus"]), 2)
        out = self.d / "s.json"
        self.assertEqual(main(["snapshot", str(self.p), "--out", str(out)]), 0)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8")), {"k": 1})
        self.assertEqual(main(["repair-tail", str(self.p)]), 0)
        self.p.write_bytes(self.p.read_bytes() + b"{trunc")
        self.assertEqual(main(["verify", str(self.p)]), 5)
        self.assertEqual(main(["repair-tail", str(self.p)]), 0)
        self.assertEqual(main(["verify", str(self.p)]), 0)
        self.p.write_bytes(self.p.read_bytes().replace(b'"value":1', b'"value":5'))
        self.assertEqual(main(["verify", str(self.p)]), 5)
        self.assertEqual(main(["repair-tail", str(self.p)]), 5)
        self.assertEqual(main(["snapshot", str(self.p), "--out", str(out)]), 5)
