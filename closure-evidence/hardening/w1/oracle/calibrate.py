"""Calibrate the W1 oracle against INDEPENDENT fixtures (owner rule C): the reference implementation written from the
requirements (positive control — every oracle test must pass) and ten one-line mutants of it (negative controls — each
must turn its target test red). Never an AISEF-generated LedgerLock. Writes CALIBRATION.json beside this file; exit 0
iff every control holds.

    <oracle venv>/bin/python closure-evidence/hardening/w1/oracle/calibrate.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORACLE = HERE / "test_oracle.py"
REFERENCE = HERE / "reference"
ACC, IDEM = "TestAcceptance::", "TestIdempotencyAndConflict::"
T14_2 = ACC + "test_14_2_snapshot_is_byte_deterministic"
T14_3 = ACC + "test_14_3_apply_batch_commits_atomically"
T14_4 = ACC + "test_14_4_repair_tail_fixes_a_truncated_tail_and_refuses_mid_chain_corruption"
T14_6 = ACC + "test_14_6_no_third_party_imports_at_runtime"
T_REPLAY = IDEM + "test_replay_is_idempotent_and_a_different_rid_conflicts"
T_TOMB = IDEM + "test_a_tombstone_conflicts_like_a_live_value"
T_CLI4 = IDEM + "test_a_conflicting_batch_exits_4_and_commits_nothing_through_the_cli"
LEDGER = "ledgerlock/ledger.py"

# id, target test, (old, new) applied exactly once to reference/ledgerlock/ledger.py, the requirement it removes
MUTANTS = [
    ("M1", T14_4, ('rec.get("prev_hash") != prev or rec.get("hash") != chain_hash(prev, rec):', 'rec.get("prev_hash") != prev:'),
     "§3.3 tamper evidence: the hash is no longer recomputed on verify"),
    ("M2", T14_3, ('b"".join(self._line(r) for r in new))', 'b"".join(self._line(r) for r in new[:1]))'),
     "§5 atomic batch: only the first op of a batch is committed"),
    ("M3", T_REPLAY, ('if key in last and last[key]["id"] != rid:', 'if key in last and last[key]["id"] != rid and False:'),
     "§4.3 conflict: another rid on a key no longer conflicts"),
    ("M4", T14_2, ("key = nfc(key)", "key = str(key)"), "§3.1 NFC: keys are not normalised"),
    ("M5", T14_2, ('for k in sorted(state, key=lambda s: s.encode("utf-8"))', "for k in state"), "§6 snapshot order: insertion order, not byte order"),
    ("M6", T14_4, ('raise CorruptionError(bad, "corruption is not a truncated tail; refusing")', "pass"),
     "§7 repair-tail: mid-chain corruption is 'repaired' instead of refused"),
    ("M7", T14_6, ("import hashlib\n", "import hashlib\n\ntry:\n    import requests  # noqa: F401\nexcept ImportError:\n    requests = None\n"),
     "§2 / §10 / §14.6: a third-party import (guarded, so only a static check sees it)"),
    ("M8", T_REPLAY, ("results.append(self._result(by_rid[rid]))  # §4.2 / §4.4: replay\n                continue\n",
                      "results.append(self._result(by_rid[rid]))  # §4.2 / §4.4: replay\n"), "§4.2 idempotency: a replayed rid appends a duplicate line"),
    ("M9", T14_2, ('doc = {k: state[k] for k in sorted(state, key=lambda s: s.encode("utf-8"))}\n',
                   'doc = {k: state[k] for k in sorted(state, key=lambda s: s.encode("utf-8"))}\n        doc["\\u0000nonce"] = os.urandom(4).hex()\n'),
     "§6 determinism: the snapshot carries a random nonce"),
    ("M10", T_CLI4, ('                raise ConflictError(f"key {key!r}: last mutation by rid {last[key][\'id\']!r}, not {rid!r}")  # §4.3–§4.5\n',
                     '                if new:\n                    write_atomic(self.path, self._bytes() + b"".join(self._line(r) for r in new))\n'
                     '                raise ConflictError(f"key {key!r}: last mutation by rid {last[key][\'id\']!r}, not {rid!r}")  # §4.3–§4.5\n'),
     "§5 + §4.3: a conflicting batch commits its non-conflicting prefix"),
]
EXPECTED_TESTS = 9


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_oracle(project: Path, obs: Path) -> tuple[dict[str, str], str]:
    env = dict(os.environ, AISEF_W1_PROJECT=str(project), AISEF_W1_ORACLE_OBSERVATIONS=str(obs))
    env.pop("PYTHONPATH", None)
    r = subprocess.run([sys.executable, "-m", "pytest", str(ORACLE), "-q", "-rA", "-p", "no:cacheprovider", "--tb=line"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(HERE), timeout=1800)
    res = {}
    for m in re.finditer(r"^(PASSED|FAILED|ERROR|SKIPPED) (\S+)", r.stdout, re.M):
        node = m.group(2)
        res[node.split("::", 1)[1] if "::" in node else node] = m.group(1)
    return res, r.stdout[-2500:]


def fixture(tmp: Path, name: str, patch: tuple[str, str] | None) -> Path:
    dst = tmp / name
    shutil.copytree(REFERENCE, dst, ignore=shutil.ignore_patterns("__pycache__", ".coverage", "*.pyc"))
    if patch:
        f = dst / LEDGER
        s = f.read_text(encoding="utf-8")
        assert s.count(patch[0]) == 1, f"{name}: patch anchor occurs {s.count(patch[0])}×"
        f.write_text(s.replace(patch[0], patch[1]), encoding="utf-8")
    return dst


def main() -> int:
    t0 = time.time()
    rec = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "python": sys.version.split()[0], "interpreter": sys.executable,
           "oracle_sha256": sha(ORACLE), "requirements_sha256": sha(REFERENCE / "docs/requirements.md"),
           "reference_sha256": {str(p.relative_to(REFERENCE)): sha(p) for p in sorted(REFERENCE.rglob("*.py"))},
           "fixtures": {}, "observations": {}}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        obs = tmp / "obs-reference.jsonl"
        res, tail = run_oracle(fixture(tmp, "reference", None), obs)
        ok = len(res) == EXPECTED_TESTS and all(v == "PASSED" for v in res.values())
        rec["fixtures"]["reference"] = {"expected": f"all {EXPECTED_TESTS} PASSED", "results": res, "pass": ok, "tail": None if ok else tail}
        rec["observations"]["reference"] = [json.loads(ln) for ln in obs.read_text(encoding="utf-8").splitlines()] if obs.exists() else []
        for mid, target, patch, removes in MUTANTS:
            obs = tmp / f"obs-{mid}.jsonl"
            res, tail = run_oracle(fixture(tmp, mid, patch), obs)
            killed = res.get(target) in ("FAILED", "ERROR")
            rec["fixtures"][mid] = {"removes": removes, "target": target, "killed": killed, "results": res,
                                    "also_red": sorted(k for k, v in res.items() if v != "PASSED" and k != target), "tail": None if killed else tail}
    rec["all_targets_killed"] = all(f["killed"] for k, f in rec["fixtures"].items() if k != "reference")
    rec["pass"] = bool(rec["fixtures"]["reference"]["pass"] and rec["all_targets_killed"])
    rec["elapsed_s"] = round(time.time() - t0, 1)
    (HERE / "CALIBRATION.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("reference:", "PASS" if rec["fixtures"]["reference"]["pass"] else "FAIL", rec["fixtures"]["reference"]["results"] if not rec["fixtures"]["reference"]["pass"] else "")
    for k, f in rec["fixtures"].items():
        if k != "reference":
            print(f"{k}: {'killed' if f['killed'] else 'SURVIVED'} → {f['target'].split('::')[1]}  also red: {[t.split('::')[1] for t in f['also_red']]}")
    print("CALIBRATION:", "PASS" if rec["pass"] else "FAIL", f"({rec['elapsed_s']}s)")
    return 0 if rec["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
