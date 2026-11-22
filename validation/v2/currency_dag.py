"""The record-currency dependency DAG (owner v2.2 directive #1, cross-record resolution).

The sealing tier's currency records are NOT independent: a dependent's checker reads an UPSTREAM record, and when the
tree advances (a re-qualification round) the upstream must be read at its CURRENT-round (v2.2) supersession, not the
stale v2.1 one. This module declares that DAG once — each node's legacy record, its v2.2 supersession (None when the
node is frozen history with no record of its own, only a cross-record checker), and the upstream nodes it depends on —
and validates it in topological order: a cycle, an unknown dependency, a missing/ambiguous/tampered/cross-version
supersession each fail explicitly (version_forward.resolve_upstream / toposort). It is the single source of truth for
the write/check order and the C2/C4 manifest; it changes no acceptance semantics (every per-node verdict stays the
group's own checker).

Not every sealing record is a version-forward node. The C3-gated ledgers (checker calibration / Q0, the
destructive-authority ledger, INV-MUTATION-AUTHORITY), the V2-007 freeze manifest (C10) and the historical P1..V2.0-S2
mutation records (read against each record's OWN original binding — a kernel edit after a seal is the owner's re-run,
not a version-forward) are owner-gated, listed under OWNER_GATED for the manifest, and never resolved here.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.v2 import version_forward as vf  # noqa: E402

V21 = "closure-evidence/v2/v2.1"
V22 = "closure-evidence/v2/v2.2"
CYC = "closure-evidence/v2/cycle2"


class Node:
    __slots__ = ("legacy", "v22", "deps", "owner", "gated_tests", "note")

    def __init__(self, legacy, v22, deps, owner, gated_tests, note=""):
        self.legacy, self.v22, self.deps = legacy, v22, tuple(deps)
        self.owner, self.gated_tests, self.note = owner, tuple(gated_tests), note


#: the version-forward currency DAG. deps are UPSTREAM node ids the node's v2.2 checker must resolve for this round.
NODES: dict[str, Node] = {
    "P5-PROPOSAL": Node(f"{V21}/P5-PLAN-V2.2-PROPOSAL.json", f"{V22}/P5-PLAN-V2.2-PROPOSAL.json", (),
                        "validation/qualification/p5_acceptance.py (--write/-check-v22-proposal)",
                        ("tests/v2/test_p5_plan_v22_proposal.py::Record.test_P5_8_committed_record_is_current",
                         "tests/v2/test_c2_p5_acceptance.py::KernelProvenance.test_on_this_tree_the_committed_proposal_is_current")),
    "P5-FALSIFIABILITY": Node(f"{V21}/P5-FALSIFIABILITY.json", f"{V22}/P5-FALSIFIABILITY.json", ("P5-PROPOSAL",),
                              "validation/qualification/p5_falsifiability.py (--write/-check-v22)", (),
                              note="upstream behaviour evidence; no gated test of its own — PLAN/P5-REVERIFICATION read it"),
    "P5-REVERIFICATION": Node(f"{V21}/C2-P5-ACCEPTANCE-REVERIFICATION.json", f"{V22}/C2-P5-ACCEPTANCE-REVERIFICATION.json",
                              ("P5-FALSIFIABILITY", "P5-PROPOSAL"),
                              "validation/qualification/p5_acceptance.py (--write/-check-v22)",
                              ("tests/v2/test_c2_p5_acceptance.py::Acceptance.test_the_acceptance_re_derives_on_this_tree",)),
    "PLAN": Node(f"{V21}/PLAN-V2.2-CORRECTION-1.json", f"{V22}/PLAN-V2.2-CORRECTION-1.json", ("P5-FALSIFIABILITY",),
                 "validation/qualification/c2_plan_correction.py (--write/-check-v22)",
                 ("tests/v2/test_c2_delivery_experiment.py::PlanCorrection.test_the_committed_record_is_what_this_tree_derives",)),
    "K-NOWORK": Node(f"{V21}/K-NOWORK-001-REHEARSAL.json", f"{V22}/K-NOWORK-001-REHEARSAL.json", ("PLAN",),
                     "validation/qualification/c2_k_nowork_001.py (--write/-check-v22)",
                     ("tests/v2/test_c2_k_nowork_001.py::Record.test_the_record_binds_this_tree_and_shows_the_cases_red_before_and_green_after",)),
    "CONFORMANCE-RULING": Node(f"{V21}/CONFORMANCE-RULING.json", f"{V22}/CONFORMANCE-RULING.json", (),
                               "validation/qualification/v21_conformance_ruling.py (--write/-check-v22)",
                               ("tests/v2/test_v21_conformance_ruling.py::CommittedRuling.test_the_committed_ruling_is_what_this_tree_derives",)),
    "ORCH": Node(f"{CYC}/C2-ORCHESTRATION-CONFORMANCE-REPAIR.json", None, ("CONFORMANCE-RULING", "P5-REVERIFICATION"),
                 "validation/qualification/c2_orchestration_repair.py (release_differences_v22)",
                 ("tests/v2/test_c2_orchestration_conformance.py::Record.test_15_the_record_binds_this_tree_and_old_and_new_agree_on_every_single_probe_story",
                  "tests/v2/test_c2_orchestration_conformance.py::Record.test_15b_only_the_release_s_named_changes_are_accepted_each_while_its_gate_holds"),
                 note="frozen cycle-2 history (never re-derived); its release_differences checker resolves the v2.2 ruling and P5 reverification"),
    "P10-PROFILE": Node(f"{CYC}/P10-PROFILE-FREEZE.json", f"{V22}/P10-PROFILE-FREEZE.json", (),
                        "validation/qualification/c2_p10_profile.py (--write/-check-v22)",
                        ("tests/v2/test_c2_p10_profile_freeze.py::Checker.test_the_evidence_record_re_derives",)),
    "P10-COHORT": Node(f"{CYC}/P10-COHORT-MACHINERY.json", f"{V22}/P10-COHORT-MACHINERY.json", (),
                       "validation/qualification/c2_p10_cohort.py (--write/-check-v22)",
                       ("tests/v2/test_c2_p10_cohort_static.py::Record.test_the_evidence_record_re_derives_from_the_tree",)),
    "Q5": Node(f"{V21}/Q5-KERNEL-COMPARISON.json", f"{V22}/Q5-KERNEL-COMPARISON.json", (),
               "validation/qualification/v21_q5_compare.py (--write/-check-v22)",
               ("tests/v2/test_p9_reproduction.py::KernelComparison.test_Q5_18_check_binds_the_record_to_q5_both_kernels_the_corpus_and_the_ruling_s_data",
                "tests/v2/test_p9_reproduction.py::KernelComparison.test_Q5_19_the_kernel_comparison_record_binds_this_tree")),
}

#: sealing records that are NOT version-forward nodes (owner-gated; never resolved here). For the manifest only.
OWNER_GATED = {
    "Q0-CHECKER-CALIBRATION": "tests/v2/p0/test_checker_calibration.py — C3 interlock (owner holds C3)",
    "DESTRUCTIVE-AUTHORITY": "tests/v2/p0/test_destructive_authority.py — the C3 ledger (7 approved rows; owner holds C3)",
    "INV-MUTATION-AUTHORITY": "tests/v2/p5/test_invariants.py::MutationAuthority — destructive sites ledgered (C3)",
    "FREEZE-MANIFEST / V2-007": "tests/v2/p0/test_freeze_manifest.py + tests/v2/test_cycle2_wp201.py — C10/V2-007 ruling",
    "MUTATION-HISTORICAL": "tests/v2/test_v21_mutation_runner.py::Classify.test_historical_records_read_as_before — "
                           "P1..V2.0-S2 read against each record's OWN original binding; a post-seal kernel edit flags "
                           "'re-run the target' (the owner's re-run, not a version-forward). V2.1 MUTATION-SUMMARY FAIL "
                           "(7 survivors) audited separately: 0 REAL_DEFECT.",
}


def graph() -> dict[str, list[str]]:
    return {nid: list(n.deps) for nid, n in NODES.items()}


def _checks() -> dict:
    """The owner check function per node, run in round v2.3 (W1-DESIGN §2.6). Imports are lazy: the qualification
    modules are heavy and the v2.2 path never needs them."""
    from validation.qualification import (c2_k_nowork_001, c2_orchestration_repair, c2_p10_cohort, c2_p10_profile,
                                          c2_plan_correction, p5_acceptance, p5_falsifiability,
                                          v21_conformance_ruling, v21_q5_compare)
    return {
        "P5-PROPOSAL": p5_acceptance.check_v22_proposal,
        "P5-FALSIFIABILITY": p5_falsifiability.check_v22,
        "P5-REVERIFICATION": p5_acceptance.reverification_v22_problems,
        "PLAN": c2_plan_correction.check_v22,
        "K-NOWORK": c2_k_nowork_001.check_v22,
        "CONFORMANCE-RULING": v21_conformance_ruling.check_version_forward,
        "ORCH": c2_orchestration_repair.release_differences_v22,
        "P10-PROFILE": c2_p10_profile.check_version_forward,
        "P10-COHORT": c2_p10_cohort.check_version_forward,
        "Q5": v21_q5_compare.check_v22,
    }


def _validate_v23(root: pathlib.Path) -> dict:
    """Round v2.3 (W1-DESIGN §2.6, ledger seq 13): visit the DAG in topological order and run each node's own
    UNCHANGED v2.2 check under `vf.in_round("v2.3")`, where selection is the verified head of the node's chain.
    States: MEASURED (the head is a committed v2.3 round record), VERIFIED_REUSE (the v2.2.0-accepted record,
    re-checked in this round), INVALIDATED (the check found problems, or an upstream is not current), UNRESOLVED
    (the check raised). Every non-OK state is a problem — fail closed, no fallback."""
    order = vf.toposort(graph())
    checks = _checks()
    nodes, problems, ok = {}, [], set()
    for nid in order:
        n = NODES[nid]
        entry = {"owner": n.owner, "deps": list(n.deps), "gated_tests": list(n.gated_tests), "note": n.note,
                 "legacy": n.legacy, "v22": n.v22}
        bad = [d for d in n.deps if d not in ok]
        if bad:
            entry["state"] = "INVALIDATED"
            entry["detail"] = f"upstream not current for round 'v2.3': {bad}"
        else:
            try:
                with vf.in_round(vf.BRANCH_ROUND):
                    found = checks[nid]()
                    if found:
                        entry["state"], entry["detail"] = "INVALIDATED", str(found[0])
                    else:
                        head = vf.load_series(root, n.legacy, n.v22)[-1][0] if n.v22 is not None else n.legacy
                        if head.startswith(vf.V23_DIR + "/"):
                            entry["state"] = "MEASURED"
                            entry["head"] = head
                        else:
                            entry["state"] = "VERIFIED_REUSE"
                            entry["basis"] = "v2.2.0-accepted@da3ea33f; re-checked in round v2.3"
                        ok.add(nid)
            except Exception as e:                                       # noqa: BLE001 — any raise = fail closed
                entry["state"], entry["detail"] = "UNRESOLVED", f"{type(e).__name__}: {e}"
        if nid not in ok:
            problems.append(f"{nid}: {entry['state']}: {entry.get('detail', '')}")
        nodes[nid] = entry
    return {"round": "v2.3", "topological_order": order, "nodes": nodes, "owner_gated": OWNER_GATED,
            "problems": problems}


def validate(root: pathlib.Path = ROOT, *, kernel_digest: str | None = None, round: str | None = None) -> dict:
    """Topologically order the DAG (a cycle / unknown dep fails here) and, for each node in that order, resolve its
    own v2.2 supersession (if it has one) and each upstream dependency for this round+tree — context-bound and
    provenance-verified, no fallback. Returns the per-node report and the problems; an empty `problems` means every
    declared edge resolves to a current-round, provenance-verified record. With `round` unset, a caller passing a
    `kernel_digest` is verifying v2.2 selection and a caller passing nothing gets the v2.3 branch round."""
    round = round or ("v2.2" if kernel_digest is not None else "v2.3")
    if round == "v2.3":
        return _validate_v23(root)
    with vf.in_round(vf.CURRENT_ROUND):      # the v2.2 path selects by (round, tree) whatever the ambient round
        return _validate_v22(root, kernel_digest)


def _validate_v22(root: pathlib.Path, kernel_digest: str | None) -> dict:
    if kernel_digest is None:
        _, kernel_digest = vf.current_context(root)
    order = vf.toposort(graph())          # raises ValueError on a cycle / unknown dependency
    nodes, problems = {}, []
    for nid in order:
        n = NODES[nid]
        entry = {"owner": n.owner, "deps": list(n.deps), "gated_tests": list(n.gated_tests), "note": n.note,
                 "legacy": n.legacy, "v22": n.v22}
        if n.v22 is not None:
            try:
                path, rec = vf.resolve_upstream(root, n.legacy, n.v22, kernel_digest=kernel_digest)
                entry["status"] = "current"
                entry["bound_kernel"] = rec_kernel(root, n.v22)
            except LookupError as e:
                entry["status"] = "missing" if "no record declared" in str(e) else "error"
                entry["detail"] = str(e)
                if entry["status"] == "error":
                    problems.append(f"{nid}: {e}")
        else:
            entry["status"] = "checker-only (frozen history)"
        unresolved = []
        for d in n.deps:
            dv22 = NODES[d].v22
            if dv22 is None:
                continue
            try:
                vf.resolve_upstream(root, NODES[d].legacy, dv22, kernel_digest=kernel_digest)
            except LookupError as e:
                unresolved.append(f"{d} ({e})")
        if unresolved:
            entry["unresolved_dependencies"] = unresolved
            problems.append(f"{nid}: upstream not resolvable for this round: {unresolved}")
        nodes[nid] = entry
    return {"kernel_digest": kernel_digest, "topological_order": order, "nodes": nodes,
            "owner_gated": OWNER_GATED, "problems": problems}


def rec_kernel(root: pathlib.Path, v22_rel: str) -> str | None:
    doc = json.loads((root / v22_rel).read_text(encoding="utf-8"))
    return (doc.get(vf.BLOCK) or {}).get("kernel_digest")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", action="store_true", help="emit the full DAG report as JSON")
    ap.add_argument("--round", choices=("v2.2", "v2.3"), default=None,
                    help="the round to validate for (default: v2.2 with --kernel, else v2.3)")
    ap.add_argument("--kernel", default=None, metavar="TREE", help="verify v2.2 selection against this aisef2 tree")
    ap.add_argument("--affected", action="store_true", help="print only the non-current nodes with reasons")
    a = ap.parse_args(argv)
    rep = validate(kernel_digest=a.kernel, round=a.round)
    if a.json:
        print(json.dumps(rep, indent=1, ensure_ascii=False))
        return 1 if rep["problems"] else 0
    head = f"round {rep['round']}" if "round" in rep else f"kernel {rep['kernel_digest'][:12]}"
    if a.affected:
        for p in rep["problems"]:
            print(f"AFFECTED  {p}")
        print(f"currency DAG ({head}): {len(rep['problems'])} affected node(s)")
        return 1 if rep["problems"] else 0
    print(f"currency DAG — {head}; topological order:")
    for nid in rep["topological_order"]:
        e = rep["nodes"][nid]
        print(f"  {e.get('state') or e.get('status'):28} {nid:20} deps={e['deps']}")
    for p in rep["problems"]:
        print(f"PROBLEM  {p}")
    print("currency DAG: " + ("SOUND" if not rep["problems"] else f"{len(rep['problems'])} problem(s)"))
    return 1 if rep["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
