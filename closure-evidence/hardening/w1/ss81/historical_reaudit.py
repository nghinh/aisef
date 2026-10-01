"""SS-81 family, owner section 9 — re-audit the six historical stories whose "tests verify story" PASSED on a nop
record that never executed a story test (pytest stopped at the first collection error).

Per story, with the FIXED kernel and no model call:
  A. replay   — `control.replay` (the kernel's own `aisef gate --replay`) on the evidence exactly as recorded;
  B. measure  — the kernel's own `implement.run_nop` in the real image, at the recorded parent SHA, with the
                qualified collection strategy, on a throw-away clone (the historical repository is never written);
                the new record is spliced in before the accepted attempt's `gate:input` and `gate.evaluate` re-scores
                it with that attempt's recorded inputs.

A historical PASS is a REAL FALSE PASS only when B observes a criterion test executed GREEN at the parent — the
story's tests pass without the story's code. B returning no proof is an assurance gap, reported, not a false PASS.

    .venv/bin/python closure-evidence/hardening/w1/ss81/historical_reaudit.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from aisef.config import Config                                            # noqa: E402
from aisef.control import identity as ident                                # noqa: E402
from aisef.control import replay as R                                      # noqa: E402
from aisef.control.gate import evaluate                                    # noqa: E402
from aisef.harness.observe import Evidence, EvidenceStore                  # noqa: E402
from aisef.phases.implement import NOP_RUN, run_nop                        # noqa: E402
from aisef.phases.run import load_plan                                     # noqa: E402

PROJECTS = Path.home() / "Downloads/projects"
CASES = [("w1-run-1", s) for s in ("STORY-01-02", "STORY-01-03", "STORY-01-04", "STORY-01-06")] + \
        [("w1-run-3", s) for s in ("STORY-01-01", "STORY-01-02")]
OUT = Path(__file__).with_name("HISTORICAL-REAUDIT-NEW-PROOF-MODEL.json")
CHECKS = ("tests verify story", "TDD")


def _outcomes(gate) -> dict:
    return {c.name: {"outcome": c.outcome.value, "detail": c.detail, "proof": c.data.get("proof")}
            for c in gate.checks if c.name in CHECKS}


def audit(run: str, sid: str) -> dict:
    repo = PROJECTS / run
    art = repo / "_bmad-output"
    ev = EvidenceStore(art).read(sid)
    accepted = [r for r in R.replay(ev) if r.recorded == []]
    if not accepted:
        return {"run": run, "story": sid, "error": "no accepted (recorded PASS) gate evaluation"}
    rp = accepted[-1]
    inp = next(e for e in ev.events if e.seq == rp.seq and e.name == R.GATE_INPUT)
    kw = R.kwargs_from(inp.detail)
    old_nop = [e for e in ev.events[:ev.events.index(inp)] if e.name == NOP_RUN][-1]
    parent, cand = str(old_nop.detail["parent"]), str(kw["candidate"])
    row = {"run": run, "story": sid, "attempt": rp.attempt, "candidate": cand, "parent": parent,
           "changed": kw["changed"], "acceptance": kw["acceptance"],
           "recorded": {n: o for n, o in rp.recorded_outcomes.items() if n in CHECKS},
           "A_replay_on_recorded_evidence": _outcomes(rp.gate)}

    story = load_plan(art).stories[sid]
    cfg = Config.load(repo)
    with tempfile.TemporaryDirectory() as td:
        clone, tmp_art = Path(td) / "clone", Path(td) / "art"
        subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(repo), str(clone)], check=True)
        subprocess.run(["git", "-C", str(clone), "fetch", "-q", str(repo), parent, cand], check=True)
        subprocess.run(["git", "-C", str(clone), "checkout", "-q", "--detach", cand], check=True)
        (tmp_art / "evidence").mkdir(parents=True)
        token = ident.CURRENT.set(ident.EvidenceIdentity.of(old_nop, sid))
        try:
            run_nop(story, workdir=clone, artifact_root=tmp_art, config=cfg, candidate=cand, base_ref=parent,
                    changed=list(kw["changed"]))
        finally:
            ident.CURRENT.reset(token)
        new_nop = EvidenceStore(tmp_art).read(sid).last("tool_run", NOP_RUN)
        log = tmp_art / "run.log"
        run_log = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    i = ev.events.index(inp)
    spliced = Evidence(story_id=sid, events=ev.events[:i] + [new_nop] + [inp])
    gate = evaluate(sid, spliced, **kw)
    d = new_nop.detail
    row["B_remeasured_nop"] = {k: d.get(k) for k in ("command", "collection_strategy", "proof_schema", "image", "image_id",
                                                     "exit_code", "unrunnable", "test_format", "test_ids", "failed_ids",
                                                     "errored_ids", "skipped_ids", "collection_errors",
                                                     "collection_aborted", "output_complete", "absent_at_parent",
                                                     "ac_code_files")}
    row["B_remeasured_nop"]["tail"] = str(d.get("tail") or "")[-600:]
    row["B_nop_log"] = [ln for ln in run_log.splitlines() if " nop " in ln][-2:]
    row["B_gate_with_remeasured_nop"] = _outcomes(gate)
    tv = row["B_gate_with_remeasured_nop"]["tests verify story"]
    green = [t for per in (tv["proof"] or {}).values() for t, s in (per.get("tests") or {}).items()
             if s.get("state") == "GREEN_EXECUTED"]
    row["classification"] = ("REAL_FALSE_PASS" if green else
                             "HISTORICAL_PASS_NOW_PROVEN" if tv["outcome"] == "passed" else
                             "ASSURANCE_GAP_NO_PROOF")
    row["green_at_parent"] = green
    return row


def main() -> int:
    rows = [audit(run, sid) for run, sid in CASES]
    for r in rows:
        tv = (r.get("B_gate_with_remeasured_nop") or {}).get("tests verify story", {})
        print(f"{r['run']} {r['story']}: recorded={r.get('recorded', {}).get('tests verify story')} "
              f"replay={r.get('A_replay_on_recorded_evidence', {}).get('tests verify story', {}).get('outcome')} "
              f"remeasured={tv.get('outcome')} -> {r.get('classification') or r.get('error')}")
        print("   ", (tv.get("detail") or "")[:220])
    false_pass = [f"{r['run']} {r['story']}" for r in rows if r.get("classification") == "REAL_FALSE_PASS"]
    rec = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "owner_decision": "FIX SS-81 FAMILY (2026-09-18), section 9",
           "kernel": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
           "aisef_tree": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD:aisef"], capture_output=True, text=True).stdout.strip(),
           "aisef_dirty": bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "aisef"], capture_output=True,
                                              text=True).stdout.strip()),
           "method": __doc__.strip().splitlines()[2:12], "cases": rows, "real_false_pass": false_pass,
           "stop": bool(false_pass)}
    OUT.write_text(json.dumps(rec, indent=1, default=str) + "\n", encoding="utf-8")
    print("REAL FALSE PASS:", false_pass or "none")
    return 3 if false_pass else 0


if __name__ == "__main__":
    shutil.which("docker") or sys.exit("docker required")
    sys.exit(main())
