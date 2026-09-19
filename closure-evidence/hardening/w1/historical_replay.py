"""P20 step 5 — historical replays (deterministic, $0): `aisef replay` over the ARCHIVED 1.7.4 evidence
(closure-evidence/dogfood/ledgerlock-run2/replay-1.7.4*/) with the candidate under test, every expected classification
STATED HERE before the run and compared after. The archive keeps evidence as flat files; the story index, story files
and config the gate needs are the minimal state snapshots in historical-replay/ (see its README).

    python3 closure-evidence/hardening/w1/historical_replay.py --aisef-root . --label rehearsal      # the checkout
    <w1 venv>/bin/python closure-evidence/hardening/w1/historical_replay.py --label frozen-<sha>      # the wheel

D-035 (a verdict over a changed tree is stale) and retry hygiene are run-loop behaviours `aisef replay` cannot exercise
on archived evidence; they are proven on the candidate by the deterministic suites in SUITES, which this runner also
executes (they import the checkout — the candidate SHA is recorded next to them).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ARCHIVE = REPO / "closure-evidence/dogfood/ledgerlock-run2"
STATES = {
    "1.7.4": {"state": HERE / "historical-replay/state-1.7.4",
              "evidence": {"STORY-01-06": ARCHIVE / "replay-1.7.4/STORY-01-06.evidence.jsonl"}},
    "1.7.4-opencode": {"state": HERE / "historical-replay/state-1.7.4-opencode",
                       "evidence": {"STORY-03-01": ARCHIVE / "replay-1.7.4-opencode/STORY-03-01.evidence.jsonl",
                                    "STORY-04-01": ARCHIVE / "replay-1.7.4-opencode/STORY-04-01.evidence.jsonl"}},
}
SUITES = ["tests/hardening/test_verdict_freshness.py", "tests/test_retry_hygiene.py", "tests/test_baseline_provenance.py"]

# Every check whose outcome MUST differ from the 1.7.4 record, keyed by (state, story, attempt, candidate[:7]):
# check → (recorded, now, why). Every other attempt must reproduce its record exactly (no changed row, same blocking
# set). Any other difference is UNEXPECTED — a finding, never normalised.
EXPECTED_CHANGES = {
    ("1.7.4", "STORY-01-06", 3, "eed6f87"): {
        "no baseline regression": ("failed", "passed",
                                   "the baseline of record is the epoch root's record (seq 2), not the re-run the forced resume made AFTER "
                                   "the candidate's test run (seq 41), which 1.7.4 selected by recency; compared with the candidate's test "
                                   "run (seq 24) nothing is lost — SS-22 / baseline provenance (owner rule: sequence never determines correctness)"),
        "TDD": ("failed", "passed", "the nop control bound to the candidate proves the criteria tests red or absent at the parent; read by "
                                    "candidate binding, not by recency (SS-T1)"),
        "tests verify story": ("failed", "passed", "same nop control, same binding"),
    },
    ("1.7.4-opencode", "STORY-03-01", 3, "01c1d30"): {
        "no baseline regression": ("failed", "passed",
                                   "the archive's own OBS-OC-1 (FRAMEWORK ASSURANCE DEFECT, 1.7.5): 1.7.4 compared against the newest baseline "
                                   "(seq 393, taken at the story's own candidate ca37cc44 on resume); the hardened kernel compares against the "
                                   "epoch's baseline at the parent 9cf22f5c (seq 2): the two tests the story itself created and renamed are not a "
                                   "regression — the verdict becomes PASS, as 1.7.5's phase 4 measured on the live project"),
    },
    ("1.7.4-opencode", "STORY-03-01", 5, "01c1d30"): {
        "no baseline regression": ("failed", "passed", "same record, same cause as attempt 3 (verify-only re-score at 01c1d30)"),
    },
}
NOTES = {
    ("1.7.4", "STORY-01-06", 2, "eed6f87"): "D-032 on a 1.7.3 record: the review tool_run is a STRUCTURED ok=False whose prose says 'could not run: "
                                            "max_turns'; a legacy record is never upgraded by reading prose (Phase 16), so it scores as recorded (✗). "
                                            "The typed UNRUNNABLE exists only in records written by ≥ 1.7.4 — STORY-04-01 attempt 3 keeps ⚠ both.",
    ("1.7.4", "STORY-01-06", 3, "eed6f87"): "1.7.4's REPLAY.json step1 called these ✗ 'pre-existing R13 properties of a verify-only pass … the forced "
                                            "resume re-ran the baseline after the last test run' — a misclassification the hardened kernel corrects; "
                                            "the verdict stays FAIL (guard ran, review).",
}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def outcome_str(o) -> str:
    return str(getattr(o, "value", o))


def replay_state(name: str, spec: dict) -> list[dict]:
    from aisef.control import replay as R
    from aisef.harness.observe import EvidenceStore

    rows = []
    with tempfile.TemporaryDirectory() as td:
        proj = Path(td) / "project"
        shutil.copytree(spec["state"], proj)
        (proj / "_bmad-output" / "evidence").mkdir(parents=True, exist_ok=True)
        for sid, src in spec["evidence"].items():
            shutil.copy(src, proj / "_bmad-output" / "evidence" / f"{sid}.jsonl")
        store = EvidenceStore(proj / "_bmad-output")
        for sid in sorted(spec["evidence"]):
            ev = store.read(sid)
            for r in R.replay(ev):
                key = (name, sid, r.attempt, r.candidate[:7])
                checks = {}
                for c in getattr(r.gate, "checks", []):
                    rec = r.recorded_outcomes.get(c.name)
                    now = outcome_str(c.outcome)
                    changed = (rec != now) if rec else ((c.name in (r.recorded or [])) != (c.name in r.now))
                    reason = str(getattr(c, "reason", None) or getattr(c, "detail", None) or getattr(c, "message", "") or "")
                    checks[c.name] = {"recorded": rec, "now": now, "changed": changed, "reason": reason,
                                      "evidence_seqs": list(getattr(c, "evidence", []) or [])}
                exp = EXPECTED_CHANGES.get(key, {})
                actual_changed = {k: (v["recorded"], v["now"]) for k, v in checks.items() if v["changed"]}
                unexpected = {k: v for k, v in actual_changed.items() if k not in exp or (exp[k][0], exp[k][1]) != v}
                missing = {k: v for k, v in exp.items() if k not in actual_changed}
                rows.append({"state": name, "story": sid, "attempt": r.attempt, "seq": r.seq, "candidate": r.candidate,
                             "recorded_blocking": r.recorded, "now_blocking": r.now,
                             "verdict": {"recorded": "PASS" if r.recorded == [] else "FAIL", "now": "PASS" if not r.now else "FAIL"},
                             "changed_rows": {k: {"recorded": checks[k]["recorded"], "now": checks[k]["now"], "reason_now": checks[k]["reason"],
                                                  "evidence_seqs": checks[k]["evidence_seqs"], "expected_why": exp.get(k, (None, None, None))[2]}
                                              for k in actual_changed},
                             "unexpected_changes": unexpected, "expected_changes_missing": missing,
                             "note": NOTES.get(key), "pass": not unexpected and not missing})
    return rows


def run_suites() -> dict:
    r = subprocess.run([sys.executable, "-m", "pytest", *SUITES, "-q", "-p", "no:cacheprovider"], cwd=str(REPO),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]
    return {"suites": SUITES, "exit": r.returncode, "summary": tail, "pass": r.returncode == 0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aisef-root", default="", help="import aisef from this checkout (rehearsal); default: the installed package")
    ap.add_argument("--label", default="run")
    ap.add_argument("--no-suites", action="store_true")
    a = ap.parse_args()
    if a.aisef_root:
        sys.path.insert(0, str(Path(a.aisef_root).resolve()))
    import aisef  # noqa: E402

    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
    dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--", "aisef"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
    t0 = time.time()
    rows = [row for name, spec in STATES.items() for row in replay_state(name, spec)]
    suites = None if a.no_suites else run_suites()
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "label": a.label,
           "candidate": {"aisef_file": aisef.__file__, "aisef_version": getattr(aisef, "__version__", None), "checkout_head": head,
                         "checkout_aisef_dirty": dirty.splitlines(), "python": sys.version.split()[0]},
           "archive": {name: {sid: {"path": str(p.relative_to(REPO)), "sha256": sha(p)} for sid, p in spec["evidence"].items()} for name, spec in STATES.items()},
           "state_snapshots": {name: str(spec["state"].relative_to(REPO)) for name, spec in STATES.items()},
           "expected_changes_declared": {"|".join(map(str, k)): {c: {"recorded": v[0], "now": v[1], "why": v[2]} for c, v in d.items()} for k, d in EXPECTED_CHANGES.items()},
           "attempts": rows, "suites": suites,
           "totals": {"attempts": len(rows), "attempts_with_changed_rows": sum(1 for r in rows if r["changed_rows"]),
                      "verdict_flips": [f"{r['state']} {r['story']} attempt {r['attempt']} {r['candidate'][:7]}: {r['verdict']['recorded']}→{r['verdict']['now']}"
                                        for r in rows if r["verdict"]["recorded"] != r["verdict"]["now"]],
                      "unexpected": sum(len(r["unexpected_changes"]) for r in rows), "expected_missing": sum(len(r["expected_changes_missing"]) for r in rows)},
           "elapsed_s": round(time.time() - t0, 1)}
    out["pass"] = all(r["pass"] for r in rows) and (suites is None or suites["pass"])
    dest = HERE / f"HISTORICAL-REPLAY-{a.label}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for r in rows:
        flag = "ok " if r["pass"] else "!! "
        print(f"{flag}{r['state']:15} {r['story']} attempt {r['attempt']} {r['candidate'][:7]} {r['verdict']['recorded']}→{r['verdict']['now']} "
              f"changed={list(r['changed_rows'])} unexpected={list(r['unexpected_changes'])} missing={list(r['expected_changes_missing'])}")
    print("suites:", suites and suites["summary"]); print("HISTORICAL REPLAY:", "PASS" if out["pass"] else "FAIL", f"→ {dest.relative_to(REPO)}")
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
