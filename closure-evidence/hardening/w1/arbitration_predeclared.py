"""ARBITRATION-PREDECLARED.json (owner rule D): every arbitration expected BEFORE a W1 run, in the required form — the
exact conflicting passages, why the conflict is objectively present (MEASURED on the W1 copy, not asserted), the
decision and its authority, whether it opens a new epoch, and the approval invalidation it is expected to cause.
A predeclared arbitration is not a waiver: the kernel must still detect the condition through its normal path at
run start, and that detection is recorded before the operator acts.

    python3 closure-evidence/hardening/w1/arbitration_predeclared.py ~/Downloads/projects/w1-run-1
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import aisef.control.approvals as ap  # noqa: E402

OUT = Path(__file__).resolve().parent / "ARBITRATION-PREDECLARED.json"


def measure(project: Path) -> dict:
    root = project / "_bmad-output"
    a = ap.ApprovalStore(root)
    rec = a.load(ap.Gate.READINESS)
    arts = a.artifact_paths(ap.Gate.READINESS)
    signed_method = hashlib.sha256("\n".join(f"{p.relative_to(root)}:{ap._artifact_hash(p)}" for p in arts).encode()).hexdigest()
    return {
        "project": str(project), "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gate_statuses": {g.value: a.status(g).value for g in ap.GATE_ORDER},
        "gates_stale": [g.value for g in ap.GATE_ORDER if a.status(g) is ap.Status.STALE],
        "readiness": {
            "status": a.status(ap.Gate.READINESS).value, "stored_digest": rec.artifact_sha256, "stored_seq": rec.seq,
            "stored_decided_by": rec.decided_by, "stored_decided_at": rec.decided_at,
            "current_digest": a.content_hash(ap.Gate.READINESS),
            "digest_recomputed_by_the_signed_method": signed_method,
            "artifacts_byte_identical_to_what_was_signed": signed_method == rec.artifact_sha256,
            "artifacts": {str(p.relative_to(root)): {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in arts},
            "verifier_config_digest_now_part_of_the_hash": ap._verifier_config_digest(root),
        },
    }


def main(argv: list[str]) -> int:
    project = Path(argv[1]).expanduser().resolve() if len(argv) > 1 else Path.home() / "Downloads/projects/w1-run-1"
    m = measure(project)
    r = m["readiness"]
    only_readiness = m["gates_stale"] == ["readiness"]
    arb1 = {
        "id": "ARB-1", "gate": "readiness",
        "kind": "framework rule (hash method) vs the frozen environment contract — NOT a conflict inside the LedgerLock requirements",
        "conflicting_passages": [
            {"where": "aisef/control/approvals.py — module docstring",
             "text": "Changing the hash method makes previously signed `stories`/`readiness` approvals stale **once** — stated here instead of leaving the user to guess."},
            {"where": "aisef/control/approvals.py — ApprovalStore.content_hash",
             "text": "readiness covers the verifier configuration (SS-55) … INV-P.1: the digest is what a person approved."},
            {"where": "docs/SCALE-QUALIFICATION.md — What \"qualified\" means operationally, 2", "text": "No AISEF change during the runs."},
            {"where": "closure-evidence/hardening/family-plans/P20-w1-ledgerlock.md — Procedure 1",
             "text": "confirm approvals (PRD, architecture, epics, stories, readiness) are APPROVED for that tree's digests"},
        ],
        "why_objectively_present": {
            "statement": "The owner signed `readiness` on 2026-09-15 under the 1.7.6 hash method (the two artifacts only). The hardened "
                         "candidate adds `verifier-config:<digest>` to the readiness hash (SS-55 / Phase 16). The two artifacts are "
                         "byte-identical to what was signed — recomputing the signed method over them reproduces the stored digest "
                         "exactly — so the STALE reading is caused by the hash-method change alone, exactly as the module states.",
            "measured": r, "only_readiness_is_stale": only_readiness,
        },
        "kernel_path_first": {
            "rule": "The owner's rule: a predeclared arbitration must not become a hidden waiver; W1 must still detect and enter "
                    "HUMAN_REQUIRED through the normal kernel path.",
            "procedure": "At W1 start `aisef run` is invoked with NO re-approval and NO `--force`. The kernel's own readiness check must "
                         "refuse or stop on the STALE gate before any agent call; its exit code, message and the absence of any agent "
                         "session are recorded in the run's W1 record. Only after that observation is the gate re-approved. A run that "
                         "proceeds past a STALE readiness without `--force` is a P0 finding and stops W1.",
        },
        "decision": "Re-approve `readiness` for the byte-identical content through the normal CLI (`aisef approve readiness`), never a "
                    "state edit; record seq, digest before/after, decided_by and a note naming this record (ARB-1) in W1-LEDGERLOCK-<n>.json.",
        "decision_authority": {
            "owner_decision_given_for_this_specific_re_approval": False,
            "basis": [
                "the content is byte-identical to what the owner (`" + str(r["stored_decided_by"]) + "`) signed on " + str(r["stored_decided_at"]),
                "the approvals module states that a hash-method change stales `stories`/`readiness` once — the re-approval is the module's own documented remedy",
                "the owner approved Phases 11–21 including three fresh W1 executions; without this re-approval no W1 run can start (`--force` is excluded)",
            ],
            "if_the_owner_rejects": "the re-approval and every W1 run that rests on it are void; W1 waits for the owner's own `aisef approve readiness`.",
            "performed_by": "the operator (this program), recorded as `decided_by` of the new approval record",
        },
        "new_epoch": {"value": False, "reason": "story epochs are the stories' `acceptance.contract_fingerprint` (D-033); stories.index.json is byte-identical, "
                                                 "so no contract fingerprint changes; a readiness approval is not part of any story's epoch"},
        "expected_approval_invalidation": {
            "upstream": "none — a re-approval never touches upstream gates (prd … mockups stay approved for their digests)",
            "downstream": "pre-deploy is pending and was never approved — nothing to invalidate",
            "story_verdicts": "none exist at run start (fresh copy at 8ff9f13 + fd4c644)",
            "verification": "the gate statuses are measured again right after the re-approval; any status other than readiness→approved is a finding",
        },
        "not_a_waiver": ["no `--force`", "no manual state edit", "the kernel's STALE detection is observed and recorded first",
                         "any OTHER stale gate at W1 start is a finding, not an arbitration (measured now: " + json.dumps(m["gates_stale"]) + ")"],
    }
    requirement_ambiguities = {
        "declared_in": "closure-evidence/hardening/w1/ORACLE-INDEPENDENCE.json → ambiguities (AMB-1 … AMB-4) and assumptions (A1 … A7)",
        "predeclared_handling_during_a_run": [
            "if a run enters HUMAN_REQUIRED citing a requirement ambiguity, the operator records the story, the reviewer's words and the passages, "
            "and does NOT edit the requirements, the stories, the config or the oracle; the run's terminal state stands as a correctly classified stop",
            "the owner decides after the run whether the ambiguity is resolved by a requirements change (a new epoch, a new W1 series) or by accepting the delivery",
            "an oracle ASSUMPTION failure (A1–A7) is escalated exactly as ORACLE-INDEPENDENCE.json predeclares — never a FALSE PASS, never a product failure, never an oracle edit",
        ],
        "anything_else": "any operator decision during a run that is not listed here is an UNPLANNED arbitration; it is reported as such in the run record and in the final report",
    }
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "rule": "Do not let a predeclared arbitration become a hidden waiver.",
           "arbitrations": [arb1], "requirement_ambiguities": requirement_ambiguities,
           "checks": {"artifacts_byte_identical_to_what_was_signed": r["artifacts_byte_identical_to_what_was_signed"], "only_readiness_is_stale": only_readiness,
                      "readiness_signed_by_a_person": r["stored_decided_by"] not in ("auto", "", None)},
           }
    out["verdict"] = "DECLARED" if all(out["checks"].values()) else "MEASUREMENT DOES NOT MATCH THE DECLARATION — do not start W1"
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out["checks"], indent=1)); print("ARBITRATION-PREDECLARED:", out["verdict"])
    return 0 if out["verdict"] == "DECLARED" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
