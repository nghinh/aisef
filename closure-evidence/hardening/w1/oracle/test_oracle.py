"""W1 hidden oracle — LedgerLock acceptance, INDEPENDENT of the run (v2, 2026-09-17).

Every expectation is derived from the frozen docs/requirements.md (sha256 3a6a9995…) and from nothing else. The file
../ORACLE-INDEPENDENCE.json names, for every assertion, the passage it rests on, the assumptions the requirements leave
open (each with its predeclared arbitration), the calibration fixtures (reference/ — an implementation written from the
requirements — and its one-line mutants; never AISEF output) and the corrections made to v1, which had been run against
an archived AISEF delivery (disowned; kept as test_oracle.v1-disowned.py.txt). The oracle drives the delivered project
ONLY through the surfaces the requirements name (CLI §9/§14, library §5/§13), never through the agent's words, and
never edits it:

    AISEF_W1_PROJECT=/path/to/delivered/project <oracle venv>/bin/python -m pytest closure-evidence/hardening/w1/oracle -q -rA

A red test under a framework verdict of DONE is a FALSE PASS (W1 exit criterion); under BLOCKED/FAILED it is a
correctly classified product failure. A red test whose cause is an oracle ASSUMPTION (ORACLE-INDEPENDENCE.json
`assumptions`, e.g. exit 2 from `apply --batch`) is neither: it is escalated to the owner as an arbitration and never
resolved by editing the oracle to fit the delivery. Observations (AISEF_W1_ORACLE_OBSERVATIONS) carry no verdict.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(os.environ["AISEF_W1_PROJECT"]).resolve() if os.environ.get("AISEF_W1_PROJECT") else None
NFC_E, NFD_E = "é", "é"  # §3.1: one key
SKIP = "AISEF_W1_PROJECT must point at a delivered LedgerLock"


def _cli(*args: str, cwd: Path, python_flags: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = str(PROJECT)
    return subprocess.run([sys.executable, *python_flags, "-m", "ledgerlock", *args], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=120, env=env)


def _observe(**obs) -> None:
    """A fact worth recording that carries NO verdict (a requirement ambiguity — see ORACLE-INDEPENDENCE.json)."""
    p = os.environ.get("AISEF_W1_ORACLE_OBSERVATIONS")
    if p:
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(obs, ensure_ascii=False) + "\n")


def _batch_file(tmp: Path, name: str, ops: list[dict]) -> str:
    """A1: the batch spec (§5 names the file, not its shape) — a JSON array of {op, key, value, rid, ts} objects."""
    f = tmp / f"{name}.json"
    f.write_text(json.dumps(ops, ensure_ascii=False), encoding="utf-8")
    return str(f)


@unittest.skipUnless(PROJECT and (PROJECT / "ledgerlock").is_dir(), SKIP)
class TestAcceptance(unittest.TestCase):
    """§14 — the six acceptance conditions, through the CLI the requirements name."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.ledger = self.tmp / "ledger.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def _put(self, key, value, rid, ts=1):
        spec = [{"op": "put", "key": key, "value": value, "rid": rid, "ts": ts}]
        return _cli("apply", "--batch", _batch_file(self.tmp, f"put-{rid}", spec), str(self.ledger), cwd=self.tmp)

    def test_14_1_verify_exits_0_on_a_fresh_ledger(self):
        self.ledger.write_text("", encoding="utf-8")  # a fresh ledger: exists, holds no record
        r = _cli("verify", str(self.ledger), cwd=self.tmp)
        self.assertEqual(r.returncode, 0, f"§14.1 / §9: {r.stderr[-400:]}")
        r = _cli("verify", str(self.tmp / "absent.jsonl"), cwd=self.tmp)
        self.assertEqual(r.returncode, 3, f"§9: file not found is an I/O error, exit 3: {r.stderr[-400:]}")

    def test_14_2_snapshot_is_byte_deterministic(self):
        for i, k in enumerate(["b", "a", NFC_E]):
            self.assertEqual(self._put(k, {"n": i}, f"r{i}").returncode, 0)
        r = self._put(NFD_E, {"n": 3}, "r3")
        self.assertEqual(r.returncode, 4, f"§3.1 + §4.3 + §9: the NFD form is the SAME key, so a new rid conflicts: {r.stderr[-300:]}")
        out1, out2 = self.tmp / "s1.json", self.tmp / "s2.json"
        self.assertEqual(_cli("snapshot", str(self.ledger), "--out", str(out1), cwd=self.tmp).returncode, 0)
        self.assertEqual(_cli("snapshot", str(self.ledger), "--out", str(out2), cwd=self.tmp).returncode, 0)
        self.assertEqual(out1.read_bytes(), out2.read_bytes(), "§6: same chain → same snapshot bytes")
        snap = json.loads(out1.read_text(encoding="utf-8"))
        keys = list(snap.keys()) if isinstance(snap, dict) else [e["key"] for e in snap]  # A3: object keyed by key, or a list of entries
        self.assertEqual(keys, sorted(keys, key=lambda s: s.encode("utf-8")), "§6: sorted by NFC key in UTF-8 byte order")
        self.assertEqual(keys, ["a", "b", NFC_E], "§3.1 / §6: three keys, é stored once, in NFC")
        bare = [_cli("snapshot", str(self.ledger), cwd=self.tmp) for _ in range(2)]  # §14.2's bare form — observed, not judged (AMB-1)
        _observe(kind="AMB-1 snapshot bare form", exit=[b.returncode for b in bare], stdout_equal=bare[0].stdout == bare[1].stdout,
                 stdout_is_the_document=bare[0].stdout.strip() == out1.read_text(encoding="utf-8").strip())

    def test_14_3_apply_batch_commits_atomically(self):
        self.assertEqual(self._put("k0", 0, "r0").returncode, 0)
        before = self.ledger.read_bytes()
        batch = _batch_file(self.tmp, "batch", [{"op": "put", "key": "k1", "value": 1, "rid": "b1", "ts": 1},
                                                {"op": "put", "key": "k2", "value": 2, "rid": "b2", "ts": 2}])
        r = _cli("apply", "--batch", batch, str(self.ledger), cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        after = self.ledger.read_bytes()
        self.assertTrue(after.startswith(before), "§3.2: append-only — committed records are never rewritten")
        self.assertEqual(after.count(b"\n") - before.count(b"\n"), 2, "§3.2 / §5: one line per op, the full batch, never a partial one")
        self.assertEqual(_cli("verify", str(self.ledger), cwd=self.tmp).returncode, 0, "§3.3: the extended chain verifies")

    def test_14_4_repair_tail_fixes_a_truncated_tail_and_refuses_mid_chain_corruption(self):
        self.assertEqual(self._put("k0", 0, "r0").returncode, 0)
        self.assertEqual(self._put("k1", 1, "r1").returncode, 0)
        good = self.ledger.read_bytes()
        self.ledger.write_bytes(good + b'{"op": "put", "key": "k2", "va')  # §7: a crash mid-line
        self.assertEqual(_cli("verify", str(self.ledger), cwd=self.tmp).returncode, 5, "§3.3 / §9: a line that does not parse is corruption")
        self.assertEqual(_cli("repair-tail", str(self.ledger), cwd=self.tmp).returncode, 0, "§7 / §9: repair ok")
        self.assertEqual(self.ledger.read_bytes(), good, "§7: only the truncated final line is removed")
        self.assertEqual(_cli("verify", str(self.ledger), cwd=self.tmp).returncode, 0, "§7: verifies cleanly afterwards")
        self.assertEqual(_cli("repair-tail", str(self.ledger), cwd=self.tmp).returncode, 0, "§7 / §9: clean chain → no-op, exit 0")
        self.assertEqual(self.ledger.read_bytes(), good, "§7: a no-op changes nothing")
        lines = good.split(b"\n")
        first = json.loads(lines[0].decode("utf-8"))  # §3.3: mutate a committed value — whatever the serialisation
        first["value"] = 9 if first.get("value") != 9 else 8
        lines[0] = json.dumps(first, ensure_ascii=False).encode("utf-8")
        self.ledger.write_bytes(b"\n".join(lines))
        self.assertEqual(_cli("verify", str(self.ledger), cwd=self.tmp).returncode, 5, "§3.3 / §9: tamper is detected")
        self.assertEqual(_cli("repair-tail", str(self.ledger), cwd=self.tmp).returncode, 5, "§7 / §9: mid-chain corruption is refused")

    def test_14_5_coverage_at_least_85_percent_with_unittest_discover(self):
        run = subprocess.run([sys.executable, "-m", "coverage", "run", "-m", "unittest", "discover"], cwd=str(PROJECT),  # §14.5 verbatim
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        self.assertEqual(run.returncode, 0, f"§11 / §14.5: `coverage run -m unittest discover` must pass: {(run.stderr or run.stdout)[-600:]}")
        rep = subprocess.run([sys.executable, "-m", "coverage", "report"], cwd=str(PROJECT), capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=120)
        total = [ln for ln in rep.stdout.splitlines() if ln.startswith("TOTAL")]
        self.assertTrue(total, rep.stdout[-400:])
        pct = float(total[0].split()[-1].rstrip("%"))
        self.assertGreaterEqual(pct, 85.0, f"§11 / §14.5: coverage {pct}% < 85%")

    def test_14_6_no_third_party_imports_at_runtime(self):
        listed = {"hashlib", "json", "os", "sys", "pathlib", "tempfile", "argparse", "unittest", "typing", "unicodedata", "uuid", "__future__"}
        imported, os_system = set(), []
        for p in sorted((PROJECT / "ledgerlock").rglob("*.py")):
            for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"), filename=str(p))):
                if isinstance(node, ast.Import):
                    imported |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imported.add(node.module.split(".")[0])
                elif isinstance(node, ast.Attribute) and node.attr == "system" and isinstance(node.value, ast.Name) and node.value.id == "os":
                    os_system.append(f"{p.name}:{node.lineno}")
        self.assertEqual(sorted(imported - set(sys.stdlib_module_names)), [], "§2 / §10 / §14.6: a non-stdlib import")
        self.assertEqual(sorted(imported & {"socket", "subprocess"}), [], "§12: socket / subprocess are side channels")
        self.assertEqual(os_system, [], "§12: os.system is a side channel")
        _observe(kind="AMB-4 §10 allow-list", stdlib_modules_outside_the_list=sorted(imported - listed))
        self.ledger.write_text("", encoding="utf-8")
        r = _cli("verify", str(self.ledger), cwd=self.tmp, python_flags=("-S",))  # no site-packages: a third-party import cannot succeed
        self.assertEqual(r.returncode, 0, f"§14.6: the CLI must run without site-packages (python -S): {r.stderr[-400:]}")


@unittest.skipUnless(PROJECT and (PROJECT / "ledgerlock").is_dir(), SKIP)
class TestIdempotencyAndConflict(unittest.TestCase):
    """§4 through the library surface §13 names (`Ledger`, `ConflictError`, `apply_batch` with (op, key, value, rid, ts)
    tuples — §5 fixes that signature) and the CLI's exit 4 (§9)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.ledger = self.tmp / "l.jsonl"
        sys.path.insert(0, str(PROJECT))
        import importlib

        for m in [m for m in list(sys.modules) if m == "ledgerlock" or m.startswith("ledgerlock.")]:
            del sys.modules[m]
        self.L = importlib.import_module("ledgerlock.ledger")

    def tearDown(self):
        sys.path.remove(str(PROJECT))
        self._tmp.cleanup()

    def _lines(self) -> int:
        return self.ledger.read_bytes().count(b"\n") if self.ledger.is_file() else 0

    def test_replay_is_idempotent_and_a_different_rid_conflicts(self):
        led = self.L.Ledger(self.ledger)  # A2: Ledger(path)
        first = led.apply_batch([("put", "k", 1, "r1", 1)])
        n = self._lines()
        self.assertGreaterEqual(n, 1, "§3.2: a put appends one line")
        self.assertEqual(led.apply_batch([("put", "k", 1, "r1", 1)]), first, "§4.2: a replay returns the same result")
        self.assertEqual(self._lines(), n, "§4.2: a replay appends nothing")
        with self.assertRaises(self.L.ConflictError, msg="§4.3: another rid on the key"):
            led.apply_batch([("put", "k", 2, "r2", 2)])
        self.assertEqual(self._lines(), n, "§4.3: a conflict appends nothing")
        with self.assertRaises(self.L.ConflictError, msg="§4.5: put r1 then delete r2 conflicts"):
            led.apply_batch([("delete", "k", None, "r2", 3)])
        self.assertEqual(self._lines(), n, "§4.5: nothing appended")
        self.assertEqual(_cli("verify", str(self.ledger), cwd=self.tmp).returncode, 0, "§3.4: the chain verifies from disk")

    def test_a_tombstone_conflicts_like_a_live_value(self):
        led = self.L.Ledger(self.ledger)
        led.apply_batch([("delete", "t", None, "d1", 1)])  # §4.4: a delete produces a tombstone line
        n = self._lines()
        self.assertGreaterEqual(n, 1, "§4.4: the tombstone is a line of the chain")
        with self.assertRaises(self.L.ConflictError, msg="§4.4: another rid conflicts against the tombstone"):
            led.apply_batch([("put", "t", 3, "d2", 2)])
        self.assertEqual(self._lines(), n, "§4.3: nothing appended")
        led.apply_batch([("put", "t", 3, "d1", 3)])  # §4.4: same rid as the tombstone → an idempotent replay
        self.assertEqual(self._lines(), n, "§4.4: the replay is a no-op")

    def test_a_conflicting_batch_exits_4_and_commits_nothing_through_the_cli(self):
        led = self.L.Ledger(self.ledger)
        led.apply_batch([("put", "k", 1, "r1", 1)])
        before = self.ledger.read_bytes()
        batch = _batch_file(self.tmp, "b", [{"op": "put", "key": "fresh", "value": 1, "rid": "f1", "ts": 2},
                                            {"op": "put", "key": "k", "value": 2, "rid": "r2", "ts": 3}])
        r = _cli("apply", "--batch", batch, str(self.ledger), cwd=self.tmp)
        self.assertEqual(r.returncode, 4, f"§9: a conflict exits 4: {r.stderr[-200:]}")
        self.assertEqual(self.ledger.read_bytes(), before, "§4.3 + §5: the conflicting batch appends nothing — not even its non-conflicting op")


if __name__ == "__main__":
    unittest.main()
