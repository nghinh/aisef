"""V1-PF-001 after its WP-4.2 replacement (owner ruling 2026-09-30, Ruling 1 and the policy conflict correction):
the decision for the recorded recurrence and the calibration of the corrected rule.

    python -P validation/qualification/v1_pf_001_policy.py --write    # V1-PF-001-RECURRENCE-1-DECISION.json + V1-PF-001-POLICY-CALIBRATION.json
    python -P validation/qualification/v1_pf_001_policy.py --check

The rule is `validation/v2/run_history.recurrence_effect` over the policy with its amendment overlaid
(`V2-RETRY-POLICY-AMENDMENT-1.json`). Here its inputs are derived, never asserted: the typed facts of the recorded
recurrence come from the traceback kept in `V1-PF-001-RECURRENCE-1.json` (which stays byte-identical), every frame
mapped to the repository path it names; the attempt is the C2-P6 history's entry as recorded (its gate_effect STOP
untouched). The calibration runs the same function over known-bad variants of those facts; nothing keys on a CI run id
or a commit id.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import re
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (str(ROOT), str(ROOT / "validation" / "v2")):
    if p not in sys.path:
        sys.path.insert(0, p)

import run_history as rh  # noqa: E402

CYC = "closure-evidence/v2/cycle2"
RECURRENCE_REL = f"{CYC}/V1-PF-001-RECURRENCE-1.json"
HISTORY_REL = f"{CYC}/C2-P6-RUN-HISTORY.json"
AMENDMENT_REL = rh.POLICY_AMENDMENTS[0]
DECISION_REL = f"{CYC}/V1-PF-001-RECURRENCE-1-DECISION.json"
CALIBRATION_REL = f"{CYC}/V1-PF-001-POLICY-CALIBRATION.json"
QUALIFICATION_REL = f"{CYC}/Q0-Q3/SUMMARY.json"   # the V2 process-range / ownership qualification (Q3 families) of 6311254
_FRAME = re.compile(r'File "([^"]+)", line \d+, in (\S+)')
_ERROR = re.compile(r"^ERROR: (\S+) \((\S+)\)")


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def repo_path(raw: str, root: pathlib.Path = ROOT) -> str | None:
    """The repository path a traceback names: the longest suffix of its parts that exists in the tree."""
    parts = re.split(r"[\\/]+", raw)
    for i in range(len(parts)):
        rel = "/".join(parts[i:])
        if rel and (root / rel).is_file():
            return rel
    return None


def facts_from_traceback(lines: list[str], root: pathlib.Path = ROOT) -> list[dict]:
    """Every failing test of a unittest log excerpt: its name, error type, product frames (aisef/, aisef2/) and test
    frames, innermost last."""
    out, cur = [], None
    for ln in lines:
        m = _ERROR.match(ln.strip())
        if m:
            cur = {"test": f"{m.group(2)}", "error_type": None, "product_frames": [], "test_frames": []}
            out.append(cur)
            continue
        if cur is None:
            continue
        f = _FRAME.search(ln)
        if f:
            rel = repo_path(f.group(1), root)
            where = f"{rel or f.group(1)}::{f.group(2)}"
            (cur["product_frames"] if rel and rel.startswith(("aisef/", "aisef2/")) else cur["test_frames"]).append(where)
        elif re.match(r"^[A-Za-z_][\w.]*(Error|Exception)\b", ln.strip()) and cur["error_type"] is None and cur["product_frames"]:
            cur["error_type"] = ln.strip().split(":")[0]
    return out


def recorded_attempt() -> dict:
    rec = json.loads((ROOT / RECURRENCE_REL).read_text(encoding="utf-8"))
    entries = json.loads((ROOT / HISTORY_REL).read_text(encoding="utf-8"))["entries"]
    occ = rec["occurrence"]
    entry = next(e for e in entries if e["commit"] == occ["commit"] and e.get("ci_job_id") == occ["ci_job_id"])
    return {"record": rec, "entry": entry, "entries": entries}


def derived_facts(rec: dict) -> dict:
    qual = ROOT / QUALIFICATION_REL
    return {"failing": facts_from_traceback(rec["occurrence"]["log_excerpt"]),
            "v1_product_tree": rec["scope"]["v1_product_tree"]["at_the_commit"],
            "cycle1_evidence_changed": False,
            "v2_process_range_qualification": {"path": QUALIFICATION_REL, "sha256": _sha(qual)}}


def decide() -> dict:
    policy = rh.load_policy(ROOT)
    a = recorded_attempt()
    facts = derived_facts(a["record"])
    probe = {**a["entry"], "recurrence_facts": facts}      # evaluated, never written back into the history
    effect, why = rh.recurrence_effect(probe, a["entries"], policy, ROOT)
    lc = policy["known_defect_lifecycle"]["V1-PF-001"]
    return {
        "record": "AISEF V2 — V1-PF-001 RECURRENCE 1: the Cycle-2 gate effect under the corrected policy",
        "authority": "owner ruling 2026-09-30, Ruling 1 (V1-PF-001 POST-WP-4.2 POLICY RESOLVED)",
        "recurrence_record": {"path": RECURRENCE_REL, "sha256": _sha(ROOT / RECURRENCE_REL), "unchanged": True},
        "history_entry_as_recorded": {"path": HISTORY_REL, "seq": a["entry"]["seq"], "commit": a["entry"]["commit"],
                                      "job": a["entry"]["job"], "result": a["entry"]["result"], "gate_effect": a["entry"]["gate_effect"],
                                      "known_defect": a["entry"]["known_defect"],
                                      "rule": "kept exactly as recorded (FAIL, STOP); never relabeled, never erased"},
        "policy": {"base": {"path": rh.POLICY_REL, "sha256": _sha(ROOT / rh.POLICY_REL)},
                   "amendment": {"path": AMENDMENT_REL, "sha256": _sha(ROOT / AMENDMENT_REL)},
                   "checker": {"path": "validation/v2/run_history.py", "sha256": _sha(ROOT / "validation/v2/run_history.py"),
                               "function": "recurrence_effect"}},
        "typed_facts": facts,
        "derived_effect": effect, "reasons_if_stop": why,
        "classification": lc["record_only_classification"] if effect == "RECORD_ONLY" else ["STOP"],
        "is_not": lc["record_only_is_not"],
        "meaning": "the recorded failure stays a FAIL of commit a76177e's Windows job; it does not block the Cycle-2 gate; the frozen "
                   "V1 code is not fixed and not changed; the V2 process-range path is not on the failing path",
    }


# ------------------------------------------------------------------------------------------------ calibration

def _root_with(changes: dict[str, object]) -> tempfile.TemporaryDirectory:
    """A throwaway root holding the evidence the rule reads, with `changes` applied (a value None removes the file)."""
    holder = tempfile.TemporaryDirectory(prefix="aisef-v1pf-", ignore_cleanup_errors=True)
    root = pathlib.Path(holder.name)
    for ev in rh.load_policy(ROOT)["known_defect_lifecycle"]["V1-PF-001"]["replacement"]["evidence"]:
        (root / ev["path"]).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / ev["path"], root / ev["path"])
    (root / QUALIFICATION_REL).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / QUALIFICATION_REL, root / QUALIFICATION_REL)
    for rel, value in changes.items():
        (root / rel).write_text(json.dumps(value), encoding="utf-8")
    return holder


def cases() -> list[dict]:
    """Each case: the facts (and root) given, the effect expected; the expectation is the owner's list."""
    a = recorded_attempt()
    exact = derived_facts(a["record"])
    frozen = rh.load_policy(ROOT)["known_defect_lifecycle"]["V1-PF-001"]["frozen_v1_tree"]
    seal = json.loads((ROOT / "closure-evidence/v2/P4-FINAL-SEAL.json").read_text(encoding="utf-8"))
    empt = json.loads((ROOT / "closure-evidence/v2/P4-RANGE-EMPTINESS.json").read_text(encoding="utf-8"))

    def varied(fn):
        f = copy.deepcopy(exact)
        fn(f)
        return f
    return [
        {"id": "known_recurrence_before_WP_4_2", "expect": "STOP", "facts": exact,
         "root": {"closure-evidence/v2/P4-FINAL-SEAL.json": {**seal, "verdict": "P4 NOT SEALED"}}, "v1_tree": frozen},
        {"id": "exact_known_recurrence_after_WP_4_2_in_frozen_V1", "expect": "RECORD_ONLY", "facts": exact, "root": {}, "v1_tree": frozen},
        {"id": "same_signature_in_the_aisef2_process_path", "expect": "STOP",
         "facts": varied(lambda f: f["failing"][0].update(product_frames=["aisef2/runtime/process_range.py::release",
                                                                            "aisef2/runtime/process_table.py::_walk"])), "root": {}, "v1_tree": frozen},
        {"id": "known_frame_reached_through_the_aisef2_path", "expect": "STOP",
         "facts": varied(lambda f: f["failing"][0]["product_frames"].insert(0, "aisef2/orchestrate/quality.py::assess")), "root": {}, "v1_tree": frozen},
        {"id": "unknown_windows_process_cleanup_failure", "expect": "STOP",
         "facts": varied(lambda f: f["failing"][0].update(error_type="PermissionError",
                                                          product_frames=f["failing"][0]["product_frames"][:-1])), "root": {}, "v1_tree": frozen},
        {"id": "changed_v1_tree_at_the_attempt", "expect": "STOP", "facts": varied(lambda f: f.update(v1_product_tree="0" * 40)),
         "root": {}, "v1_tree": frozen},
        {"id": "changed_v1_tree_being_checked", "expect": "STOP", "facts": exact, "root": {}, "v1_tree": "0" * 40},
        {"id": "missing_replacement_evidence", "expect": "STOP", "facts": exact,
         "root": {"closure-evidence/v2/P4-RANGE-EMPTINESS.json": {k: v for k, v in empt.items() if k != "residuals_closed"}}, "v1_tree": frozen},
        {"id": "missing_v2_range_qualification_binding", "expect": "STOP",
         "facts": varied(lambda f: f.pop("v2_process_range_qualification")), "root": {}, "v1_tree": frozen},
        {"id": "v2_range_qualification_not_green", "expect": "STOP", "facts": exact,
         "root": {QUALIFICATION_REL: {"verdict": "FAILED"}}, "v1_tree": frozen},
        {"id": "cycle1_evidence_changed", "expect": "STOP", "facts": varied(lambda f: f.update(cycle1_evidence_changed=True)),
         "root": {}, "v1_tree": frozen},
        {"id": "a_second_failing_test_without_the_signature", "expect": "STOP",
         "facts": varied(lambda f: f["failing"].append({"test": "test_other (test_x.T)", "error_type": "AssertionError",
                                                         "product_frames": ["aisef/clients/base.py::run"], "test_frames": []})),
         "root": {}, "v1_tree": frozen},
        {"id": "a_v2_test", "expect": "STOP",
         "facts": varied(lambda f: f["failing"][0].update(test_frames=["tests/v2/test_x.py::test_y"])), "root": {}, "v1_tree": frozen},
        {"id": "untyped_facts", "expect": "STOP", "facts": None, "root": {}, "v1_tree": frozen},
    ]


def calibrate() -> dict:
    a = recorded_attempt()
    policy = rh.load_policy(ROOT)
    rows = []
    for c in cases():
        holder = _root_with(c["root"])
        try:
            root = pathlib.Path(holder.name)
            entry = {**a["entry"]}
            if c["facts"] is not None:
                entry["recurrence_facts"] = c["facts"]
            got, why = rh.recurrence_effect(entry, [entry], policy, root, c["v1_tree"])
        finally:
            holder.cleanup()
        rows.append({"id": c["id"], "expected": c["expect"], "observed": got, "reasons": why, "held": got == c["expect"]})
    # the policy without its amendment: fail closed
    base = json.loads((ROOT / rh.POLICY_REL).read_text(encoding="utf-8"))
    got, why = rh.recurrence_effect({**a["entry"], "recurrence_facts": derived_facts(a["record"])}, [], base, ROOT)
    rows.append({"id": "policy_without_the_amendment", "expected": "STOP", "observed": got, "reasons": why, "held": got == "STOP"})
    # run and commit identities are not inputs: the exact facts under another run id and commit give the same effect
    other = {**a["entry"], "commit": "f" * 40, "ci_run": 1, "ci_job_id": 1, "recurrence_facts": derived_facts(a["record"])}
    got, why = rh.recurrence_effect(other, [other], policy, ROOT)
    rows.append({"id": "another_run_and_commit_same_facts", "expected": "RECORD_ONLY", "observed": got, "reasons": why,
                 "held": got == "RECORD_ONLY"})
    return {"record": "AISEF V2 — V1-PF-001 POLICY CALIBRATION (the corrected rule on known-bad cases)",
            "authority": "owner ruling 2026-09-30: 'Add adversarial calibration covering at least ...'",
            "checker": {"path": "validation/v2/run_history.py", "sha256": _sha(ROOT / "validation/v2/run_history.py")},
            "amendment": {"path": AMENDMENT_REL, "sha256": _sha(ROOT / AMENDMENT_REL)},
            "cases": rows, "all_held": all(r["held"] for r in rows)}


def render(rec: dict) -> str:
    return json.dumps(rec, indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    decision, calibration = decide(), calibrate()
    if a.write:
        (ROOT / DECISION_REL).write_text(render(decision), encoding="utf-8", newline="\n")
        (ROOT / CALIBRATION_REL).write_text(render(calibration), encoding="utf-8", newline="\n")
    else:
        stale = [rel for rel, rec in ((DECISION_REL, decision), (CALIBRATION_REL, calibration))
                 if json.loads((ROOT / rel).read_text(encoding="utf-8")) != json.loads(render(rec))]
        if stale:
            print("stale: " + ", ".join(stale))
            return 1
    print(f"decision {decision['derived_effect']} {decision['reasons_if_stop']}; calibration all held {calibration['all_held']}: "
          + ", ".join(f"{r['id']}={r['observed']}" for r in calibration["cases"]))
    return 0 if decision["derived_effect"] == "RECORD_ONLY" and calibration["all_held"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
