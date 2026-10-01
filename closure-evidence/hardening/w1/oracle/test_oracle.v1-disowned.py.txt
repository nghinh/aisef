"""W1 hidden oracle — LedgerLock acceptance, INDEPENDENT of the run.

Written from docs/requirements.md §14 (acceptance) and the behaviours it rests on (§3–§9), as CODE that drives the
delivered project through its own CLI and library — never through the agent's words, never visible to the run
(this directory is outside every project the agent sees). Run AFTER the framework declares completion:

    AISEF_W1_PROJECT=/path/to/delivered/project python3 -m pytest closure-evidence/hardening/w1/oracle -q

Every test names the requirement it asserts. A failing oracle test with a framework verdict of DONE is a FALSE PASS
(a W1 exit criterion); a failing oracle test with a framework verdict of BLOCKED/FAILED is a correctly classified
product failure. The oracle never edits the project.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(os.environ.get("AISEF_W1_PROJECT", "")).resolve() if os.environ.get("AISEF_W1_PROJECT") else None


def _cli(*args: str, cwd: Path, stdin: str | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = str(PROJECT)
    return subprocess.run([sys.executable, "-m", "ledgerlock", *args], cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", input=stdin, timeout=120, env=env)


@unittest.skipUnless(PROJECT and (PROJECT / "ledgerlock").is_dir(), "AISEF_W1_PROJECT must point at a delivered LedgerLock")
class TestAcceptance(unittest.TestCase):
    """§14 — the six acceptance conditions, through the CLI the requirements name."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(); self.tmp = Path(self._tmp.name)
        self.ledger = self.tmp / "ledger.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def _put(self, key, value, rid, ts=1):
        """§5: the CLI's only mutating surface is `apply --batch <file>`; one-op batches stand in for single puts."""
        batch = self.tmp / f"batch-{rid}.json"
        batch.write_text(json.dumps([{"op": "put", "key": key, "value": value, "rid": rid, "ts": ts}]), encoding="utf-8")
        return _cli("apply", "--batch", str(batch), str(self.ledger), cwd=self.tmp)

    def test_14_1_verify_exits_0_on_a_fresh_ledger(self):
        self.ledger.write_text("", encoding="utf-8")
        r = _cli("verify", str(self.ledger), cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])

    def test_14_2_snapshot_is_byte_deterministic(self):
        for i, k in enumerate(["b", "a", "é", "é"]):      # NFC and NFD forms of é are ONE key (§3.1)
            self._put(k, {"n": i}, f"r{i}")
        out1, out2 = self.tmp / "s1.json", self.tmp / "s2.json"
        self.assertEqual(_cli("snapshot", str(self.ledger), "--out", str(out1), cwd=self.tmp).returncode, 0)
        self.assertEqual(_cli("snapshot", str(self.ledger), "--out", str(out2), cwd=self.tmp).returncode, 0)
        self.assertEqual(out1.read_bytes(), out2.read_bytes(), "§6: same chain → same snapshot bytes")
        snap = json.loads(out1.read_text(encoding="utf-8"))
        keys = list(snap.keys()) if isinstance(snap, dict) else [e["key"] for e in snap]
        self.assertEqual(keys, sorted(keys, key=lambda s: s.encode("utf-8")), "§6: sorted by NFC key in byte order")
        self.assertEqual(len(keys), 3, "§3.1: é (NFC) and e+combining acute (NFD) are the same key")

    def test_14_3_apply_batch_commits_atomically(self):
        self._put("k0", 0, "r0")
        before = self.ledger.read_bytes()
        batch = self.tmp / "batch.json"
        batch.write_text(json.dumps([{"op": "put", "key": "k1", "value": 1, "rid": "b1", "ts": 1},
                                     {"op": "put", "key": "k2", "value": 2, "rid": "b2", "ts": 2}]), encoding="utf-8")
        r = _cli("apply", "--batch", str(batch), str(self.ledger), cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        after = self.ledger.read_bytes()
        self.assertTrue(after.startswith(before), "§3.2: append-only — existing records are never rewritten")
        self.assertEqual(after.count(b"\n") - before.count(b"\n"), 2, "§5: the full batch, never a partial one")
        self.assertEqual(_cli("verify", str(self.ledger), cwd=self.tmp).returncode, 0)

    def test_14_4_repair_tail_fixes_a_truncated_tail_and_refuses_mid_chain_corruption(self):
        self._put("k0", 0, "r0"); self._put("k1", 1, "r1")
        good = self.ledger.read_bytes()
        self.ledger.write_bytes(good + b'{"op": "put", "key": "k2", "va')        # a crash mid-line (§7)
        self.assertEqual(_cli("verify", str(self.ledger), cwd=self.tmp).returncode, 5, "§9: corruption exits 5")
        self.assertEqual(_cli("repair-tail", str(self.ledger), cwd=self.tmp).returncode, 0)
        self.assertEqual(self.ledger.read_bytes(), good, "§7: only the truncated final line is removed")
        self.assertEqual(_cli("verify", str(self.ledger), cwd=self.tmp).returncode, 0)
        self.assertEqual(_cli("repair-tail", str(self.ledger), cwd=self.tmp).returncode, 0, "§7: clean chain → no-op")
        lines = good.split(b"\n")
        lines[0] = lines[0].replace(b'"value": 0', b'"value": 9')                   # §3.3: mutate a committed value
        self.ledger.write_bytes(b"\n".join(lines))
        self.assertEqual(_cli("verify", str(self.ledger), cwd=self.tmp).returncode, 5, "§3.3: tamper is detected")
        self.assertEqual(_cli("repair-tail", str(self.ledger), cwd=self.tmp).returncode, 5, "§7: mid-chain corruption is refused")

    def test_14_5_coverage_at_least_85_percent_with_unittest_discover(self):
        r = subprocess.run([sys.executable, "-m", "coverage", "run", "--source=ledgerlock", "-m", "unittest", "discover", "-q"],
                           cwd=str(PROJECT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        self.assertEqual(r.returncode, 0, (r.stderr or r.stdout)[-600:])
        rep = subprocess.run([sys.executable, "-m", "coverage", "report"], cwd=str(PROJECT), capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=120)
        total = [l for l in rep.stdout.splitlines() if l.startswith("TOTAL")]
        self.assertTrue(total, rep.stdout[-400:])
        pct = float(total[0].split()[-1].rstrip("%"))
        self.assertGreaterEqual(pct, 85.0, f"§11: coverage {pct}% < 85%")

    def test_14_6_no_third_party_imports_at_runtime(self):
        src = "\n".join(p.read_text(encoding="utf-8") for p in (PROJECT / "ledgerlock").rglob("*.py"))
        for bad in ("import requests", "import cryptography", "import nacl", "import socket", "import subprocess", "os.system("):
            self.assertNotIn(bad, src, f"§10/§12: {bad!r} is forbidden")


@unittest.skipUnless(PROJECT and (PROJECT / "ledgerlock").is_dir(), "AISEF_W1_PROJECT must point at a delivered LedgerLock")
class TestIdempotencyAndConflict(unittest.TestCase):
    """§4 through the LIBRARY surface §13 names (`Ledger`, `ConflictError`, `apply_batch` with (op, key, value, rid, ts)
    tuples — the one signature the requirements fix): a replay appends nothing, a different rid on the same key raises
    ConflictError and appends nothing, a tombstone conflicts like a live value."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(); self.tmp = Path(self._tmp.name); self.ledger = self.tmp / "l.jsonl"
        sys.path.insert(0, str(PROJECT))
        import importlib
        for m in [m for m in list(sys.modules) if m == "ledgerlock" or m.startswith("ledgerlock.")]:
            del sys.modules[m]
        self.L = importlib.import_module("ledgerlock.ledger")

    def tearDown(self):
        sys.path.remove(str(PROJECT)); self._tmp.cleanup()

    def _lines(self) -> int:
        return self.ledger.read_text(encoding="utf-8").count("\n") if self.ledger.is_file() else 0

    def test_replay_is_idempotent_and_a_different_rid_conflicts(self):
        led = self.L.Ledger(self.ledger)
        led.apply_batch([("put", "k", 1, "r1", 1)])
        n = self._lines(); self.assertGreaterEqual(n, 1)
        led.apply_batch([("put", "k", 1, "r1", 1)])                                            # §4.2 replay
        self.assertEqual(self._lines(), n, "§4.2: a replay appends nothing")
        with self.assertRaises(self.L.ConflictError):                                         # §4.3
            led.apply_batch([("put", "k", 2, "r2", 2)])
        self.assertEqual(self._lines(), n, "§4.3: a conflict appends nothing")
        with self.assertRaises(self.L.ConflictError):                                         # §4.5
            led.apply_batch([("delete", "k", None, "r2", 3)])
        self.assertEqual(self._lines(), n)
        self.assertEqual(_cli("verify", str(self.ledger), cwd=self.tmp).returncode, 0, "§3.4: the chain verifies from disk")

    def test_a_tombstone_conflicts_like_a_live_value(self):
        led = self.L.Ledger(self.ledger)
        led.apply_batch([("put", "k", 1, "r1", 1)])
        led.apply_batch([("delete", "k", None, "r1", 2)])            # §4.5: same rid, different op — a replay, no conflict
        n = self._lines()
        with self.assertRaises(self.L.ConflictError):                # §4.4: another rid against the tombstone
            led.apply_batch([("put", "k", 3, "r9", 3)])
        self.assertEqual(self._lines(), n)

    def test_a_conflicting_batch_exits_4_through_the_cli(self):
        led = self.L.Ledger(self.ledger)
        led.apply_batch([("put", "k", 1, "r1", 1)])
        n = self._lines()
        batch = self.tmp / "b.json"
        batch.write_text(json.dumps([{"op": "put", "key": "k", "value": 2, "rid": "r2", "ts": 2}]), encoding="utf-8")
        r = _cli("apply", "--batch", str(batch), str(self.ledger), cwd=self.tmp)
        self.assertEqual((r.returncode, self._lines()), (4, n), f"§9: conflict exits 4 and appends nothing: {r.stderr[-200:]}")


if __name__ == "__main__":
    unittest.main()
