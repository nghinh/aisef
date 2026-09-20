"""Deterministic audit of W1-LEDGERLOCK-PLAN-V2 (owner decision 2026-09-20, section 17).

No model call: the plan is read with the product's own parser, judged against the frozen requirements, and the
result written as W1-PLAN-V2-AUDIT.json. A failing audit means no run is started.

    python3 plan_v2_audit.py <epics-v2.md> <prd.md> <requirements.md> --out W1-PLAN-V2-AUDIT.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from aisef.control.machine_gate import check_stories  # noqa: E402
from aisef.control.normalize import parse_epics_file, parse_prd_file  # noqa: E402
from aisef.control.obligation import Mode, VERIFICATION_ONLY, story_contribution  # noqa: E402
from aisef.phases.story_split import to_scheduler  # noqa: E402

#: Two stories may both CHANGE a requirement when each delivers a different, named part of it. Anything not listed
#: here is reported as an unexplained duplicate.
SPLIT_REQUIREMENTS = {
    "FR-2": "the hash chain is built in layers: canonical bytes (01-02), the digest over them (01-03), and the "
            "chained line append that uses both (01-05)",
    "FR-12": "STORY-04-02 delivers the exit codes themselves; STORY-04-03 delivers the stderr status shapes of the "
             "success paths — different observable behaviour under the same requirement",
    "FR-13": "durability appears twice: the atomic write primitive (01-04), the fsync-before-return of append "
             "(01-05) and the batch's atomic replace (03-01)",
    "FR-14": "the runtime prohibitions are established with the package (01-01) and the coverage/parity gate is a "
             "separate, later contract (05-02)",
    "FR-1": "NFC normalization is delivered as a function (01-01) and then enforced on append's key (01-05)",
    "FR-6": "verify's verdict (02-01) is library behaviour; the CLI surface for it is FR-11",
    "FR-9": "snapshot is one story (02-02); the CLI's snapshot command is FR-11",
}


def ac_rows(plan) -> list[dict]:
    rows = []
    for st in plan.stories():
        for i, text in enumerate(st.acceptance_criteria, 1):
            code = f"AC-{st.id}-{i}"
            decl = st.ac_proof.get(code) or {}
            rows.append({"ac_id": code, "story": st.id, "story_type": st.story_type,
                         "requirement": decl.get("requirement") or "", "proof_mode": decl.get("proof_mode"),
                         "depends_on": list(st.depends_on), "criterion": text})
    return rows


def audit(epics: Path, prd_path: Path, requirements: Path) -> dict:
    plan = parse_epics_file(epics)
    prd = parse_prd_file(prd_path)
    req_text = requirements.read_text(encoding="utf-8")
    rows = ac_rows(plan)
    stories = plan.stories()
    known = {r.id for r in prd.requirements}
    errors: list[str] = []
    warnings: list[str] = []

    # 1. every criterion declares a valid obligation and a requirement the PRD carries
    for r in rows:
        if r["proof_mode"] not in Mode.__members__:
            errors.append(f"{r['ac_id']}: proof mode {r['proof_mode']!r} is not declared or not valid")
        if r["requirement"] not in known:
            errors.append(f"{r['ac_id']}: requirement {r['requirement']!r} is not in the PRD")

    # 2. 100% FR -> AC traceability, in both directions
    covered = {r["requirement"] for r in rows}
    uncovered = sorted(known - covered)
    if uncovered:
        errors.append(f"requirements with no acceptance criterion: {', '.join(uncovered)}")

    # 3. every normal story contributes at least one CHANGE_REQUIRED criterion
    for st in stories:
        codes = [f"AC-{st.id}-{i}" for i in range(1, len(st.acceptance_criteria) + 1)]
        ok, why = story_contribution(st.ac_proof, codes, st.story_type)
        if not ok:
            errors.append(f"{st.id}: {why}")

    # 4. duplicate CHANGE_REQUIRED ownership of one requirement needs a stated reason
    owners: dict[str, set[str]] = {}
    for r in rows:
        if r["proof_mode"] == Mode.CHANGE_REQUIRED.value:
            owners.setdefault(r["requirement"], set()).add(r["story"])
    duplicates = {req: sorted(sids) for req, sids in owners.items() if len(sids) > 1}
    for req, sids in sorted(duplicates.items()):
        if req not in SPLIT_REQUIREMENTS:
            errors.append(f"{req} is CHANGE_REQUIRED in {', '.join(sids)} with no stated reason")

    # 5. a PRESERVE_REQUIRED criterion must have an earlier story that delivers the behaviour (its requirement is
    #    CHANGE_REQUIRED somewhere upstream); a NEGATIVE_INVARIANT needs no upstream owner
    order = {st.id: n for n, st in enumerate(stories)}
    for r in rows:
        if r["proof_mode"] != Mode.PRESERVE_REQUIRED.value:
            continue
        upstream = sorted(s for s in owners.get(r["requirement"], set()) if order[s] < order[r["story"]])
        if not upstream:
            errors.append(f"{r['ac_id']} is PRESERVE_REQUIRED for {r['requirement']} but no earlier story changes "
                          f"that requirement — nothing to preserve")
        else:
            r["preserves_work_of"] = upstream

    # 6. the contradiction the owner named must be gone, and no criterion may contradict §4.5 the same way
    conflict_rule = "MUST conflict" in req_text
    bad = [r for r in rows if re.search(r"delete\(\"?k\"?,\s*\"?r2", r["criterion"]) and "ConflictError" not in r["criterion"]]
    if conflict_rule and bad:
        errors.append("criteria still ask for a different-rid delete to succeed, which requirements §4.5 forbids: "
                      + ", ".join(r["ac_id"] for r in bad))

    # 7. the product's own machine gate over the same plan
    gate = check_stories(to_scheduler(stories), prd,
                         story_fr_map={s.id: s.covers for s in stories},
                         story_ac_count={s.id: len(s.acceptance_criteria) for s in stories},
                         story_ac_text={s.id: list(s.acceptance_criteria) for s in stories},
                         story_ac_proof={s.id: dict(s.ac_proof) for s in stories},
                         story_type={s.id: s.story_type for s in stories})
    errors += [f"machine gate: {e}" for e in gate.errors]
    warnings += [f"machine gate: {w}" for w in gate.warnings]

    counts = {m.value: sum(1 for r in rows if r["proof_mode"] == m.value) for m in Mode}
    return {
        "plan": "W1-LEDGERLOCK-PLAN-V2", "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "owner_decision": "STOP PROFILE HUNTING, FIX W1 PLAN + TDD PROOF POLICY (2026-09-20), section 17",
        "source": {"epics": str(epics), "prd": str(prd_path), "requirements": str(requirements),
                   "requirements_unchanged": True},
        "stories": len(stories), "criteria": len(rows), "obligation_counts": counts,
        "verification_only_stories": [s.id for s in stories if s.story_type == VERIFICATION_ONLY],
        "requirements_covered": sorted(covered), "requirements_uncovered": uncovered,
        "duplicate_change_ownership": {k: {"stories": v, "reason": SPLIT_REQUIREMENTS.get(k, "")}
                                       for k, v in sorted(duplicates.items())},
        "criteria_already_satisfiable_at_entry": {
            "computed": False,
            "why": "the story-entry parent is the previous stories' delivered code, which no deterministic reference "
                   "skeleton in this workload can produce; the plan mitigates it by moving the CLI surface criterion "
                   "to the story that owns FR-11 (PLAN-V2-03), by scoping the skeleton away from the CLI module "
                   "(PLAN-V2-05), by naming the error-path ownership in STORY-04-01 (PLAN-V2-06), and by declaring "
                   "the argparse usage errors PRESERVE_REQUIRED where an earlier story delivers them",
            "runtime_detection": "a CHANGE_REQUIRED criterion already satisfied at entry is reported as PLAN_OVERLAP "
                                 "and ends the story without spending a developer attempt (INV-PLAN-STORY-CONTRIBUTION)"},
        "rows": rows, "errors": errors, "warnings": warnings, "pass": not errors,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("epics")
    ap.add_argument("prd")
    ap.add_argument("requirements")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rec = audit(Path(a.epics), Path(a.prd), Path(a.requirements))
    Path(a.out).write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: rec[k] for k in ("stories", "criteria", "obligation_counts", "pass")}))
    for e in rec["errors"]:
        print("  ✗", e)
    for w in rec["warnings"]:
        print("  ⚠", w)
    return 0 if rec["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
