"""The consolidated Cycle-2 report (owner rulings 2026-09-30 A and B: 'CYCLE-2 P6/P7/P8/P9/P10 COMPLETE / V2 READY FOR FINAL
OWNER CLOSURE REVIEW'): the 61 requested items and the ruling-B additions, each read from the record that holds it and
bound by digest; the guards run here.

    python -P validation/qualification/c2_final_report.py --write
        -> closure-evidence/v2/cycle2/C2-FINAL-REPORT.json and C2-FINAL-REPORT.md

Nothing here decides anything: a missing record or a failing guard is a problem and the verdict says so.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "validation" / "v2"))

CY = "closure-evidence/v2/cycle2"
OUT_JSON, OUT_MD = f"{CY}/C2-FINAL-REPORT.json", f"{CY}/C2-FINAL-REPORT.md"
STATEMENT = ["Cycle-2 engineering and qualification scope is complete.", "LedgerLock remains DEVELOPMENT_REGRESSION.",
             "No cohort has been selected or sealed.", "No generalization claim has been made.", "PR #6 has not been merged.",
             "Public V2 release has not been performed.", "The candidate is ready for final Owner closure review."]
MASTER = "671ef9b"
PLATFORMS = ("linux-py3.11", "linux-py3.12", "linux-py3.13", "linux-py3.14", "windows-py3.11")


def git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, encoding="utf-8", check=True).stdout.strip()


def load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def ident(rel: str) -> dict:
    return {"path": rel, "sha256": hashlib.sha256((ROOT / rel).read_bytes().replace(b"\r\n", b"\n")).hexdigest()}


def _run(argv: list[str]) -> dict:
    r = subprocess.run([sys.executable, "-P", *argv], cwd=ROOT, capture_output=True, encoding="utf-8")
    return {"command": "python -P " + " ".join(argv), "exit": r.returncode, "tail": (r.stdout + r.stderr).strip().splitlines()[-1:]}


def qualification(rel: str) -> dict:
    """One QP-2.6 attempt's summary: the verdict, and per platform the PASS / N/A counts of each rung."""
    s = load(f"{rel}/SUMMARY.json")
    plats = {}
    for p in PLATFORMS:
        row = {}
        for q in ("Q0", "Q1", "Q2", "Q3"):
            f = ROOT / rel / q / f"{q}-{p}.json"
            if f.exists():
                d = json.loads(f.read_text(encoding="utf-8"))
                row[q] = {"status": d["status"], "pass": d["counts"]["PASS"], "fail": d["counts"]["FAIL"] + d["counts"]["ERROR"],
                          "not_applicable": d["counts"]["NOT_APPLICABLE"]}
        own = ROOT / rel / "PLATFORMS" / f"{p}.json"
        if own.exists():
            o = json.loads(own.read_text(encoding="utf-8"))
            row["owned_after"], row["escaped"] = o["owned_after"], len(o["escaped"])
        plats[p] = row
    return {"summary": ident(f"{rel}/SUMMARY.json"), "verdict": s["verdict"], "candidate": s["subject"]["semantic_candidate"],
            "kernel_tree": s["subject"]["kernel_tree"], "rungs": {k: v["status"] for k, v in s["rungs"].items()}, "platforms": plats,
            "mutation": (s.get("q2") or {}).get("mutation"),
            "fault_matrix": {k: (s.get("q3") or {}).get(k) for k in ("fault_matrix_rows", "fault_matrix_classes")}}


def differential(rel: str) -> dict:
    d = load(f"{rel}/DIFFERENTIAL.json")
    return {"record": ident(f"{rel}/DIFFERENTIAL.json"), "status": d["status"], "semantic_candidate": d["semantic_candidate"],
            "kernel_tree": d["kernel_tree"], "execution_commit": d["execution_commit"], "totals": d["totals"],
            "unexplained_divergences": d["totals"]["DIVERGENCE"], "kernel_digest": d["identity"]["kernel_digest"],
            "one_kernel_identity": d["one_kernel_identity"], "identities": d["one_kernel_digest_assertion"],
            "subject": ident(f"{rel}/SUBJECT.json"), "probe_id_coverage": d["coverage_summary"].get("probe_id"),
            "zero_sample_categories": d["zero_sample_categories"], "calibration": d["calibration"] if isinstance(d["calibration"], (bool, str)) else
            {k: d["calibration"].get(k) for k in ("all_detected", "sha256", "path") if k in d["calibration"]},
            "lower_rung_bound": list(d["p7_evidence"])}


def reproduction(rel: str) -> dict:
    d = load(f"{rel}/REPRODUCTION.json")
    t = d["totals"]
    return {"record": ident(f"{rel}/REPRODUCTION.json"), "status": d["status"], "semantic_candidate": d["semantic_candidate"],
            "kernel_tree": d["kernel_tree"], "corpus_digest": d["corpus_digest"], "replay_digest": d["replay_digest"],
            "one_identity": d["one_identity"], "items": t["items"], "green": t["green"], "assert_consumed": d["assert_consumed"],
            "model_calls": {"expected": t["expected_model_calls"], "consumed": t["consumed_model_calls"], "missing": t["missing_replay_calls"],
                            "extra": t["extra_model_calls"], "request_hash_mismatches": t["request_hash_mismatches"]},
            "only_model_stream_replayed": d["only_model_stream_replayed"], "replay_mechanism": d["replay_mechanism"],
            "re_execution": {"tool_executions": t["tool_executions"], "tool_result_replays": t["tool_result_replays"],
                             "subprocess_executions": t["subprocess_executions"], "socket_attempts": t["socket_attempts"]},
            "calibration_all_rejected": load(f"{rel}/CALIBRATION.json")["all_rejected"]}


def histories() -> tuple[dict, int, int]:
    import run_history as rh
    out, residual, escaped = {}, 0, 0
    for phase, rel in rh.HISTORIES.items():
        if not phase.startswith("C2-") or not (ROOT / rel).exists():
            continue
        e = load(rel)["entries"]
        residual += sum(x.get("owned_processes_after") or 0 for x in e)
        escaped += sum(x.get("owned_escaped") or 0 for x in e)
        out[phase] = {**ident(rel), "attempts": len(e), "passed": sum(1 for x in e if x["result"] == "PASS"),
                      "failed": [{"seq": x["seq"], "commit": x["commit"][:7], "where": x["where"], "job": x["job"], "classification": x["classification"],
                                  "known_defect": x.get("known_defect"), "gate_effect": x["gate_effect"]} for x in e if x["result"] == "FAIL"],
                      "sealed_by": rh.SEALS.get(phase) if rh.SEALS.get(phase) and (ROOT / rh.SEALS[phase]).exists() else None}
    return out, residual, escaped


def build() -> dict:
    from validation.qualification import p5_acceptance as pa
    problems: list[str] = []
    acc, appr = load(f"{CY}/C2-P5-ACCEPTANCE.json"), load(f"{CY}/P5-CONTRACT-APPROVALS.json")
    v = pa.verify(run_guards=False)
    corr = load(f"{CY}/C2-P5-ACCEPTANCE-CORRIGENDUM-1.json")
    p6 = load(f"{CY}/C2-P6-CLOSURE.json")
    r3, r4 = qualification(f"{CY}/Q0-Q3-R3"), qualification(f"{CY}/Q0-Q3-R4")
    q4, q4f, q5, q5f = differential(f"{CY}/Q4"), differential(f"{CY}/Q4-FINAL"), reproduction(f"{CY}/Q5"), reproduction(f"{CY}/Q5-FINAL")
    ll = load(f"{CY}/P10/attempt-2/LEDGERLOCK-REGRESSION.json")
    coh, prof = load(f"{CY}/P10-COHORT-MACHINERY.json"), load(f"{CY}/P10-PROFILE-FREEZE.json")
    fin = load(f"{CY}/C2-FINAL-INTEGRATION.json")
    rep = load(f"{CY}/C2-ORCHESTRATION-CONFORMANCE-REPAIR.json")
    cal = load(f"{CY}/V1-PF-001-POLICY-CALIBRATION.json")
    dec = load(f"{CY}/V1-PF-001-RECURRENCE-1-DECISION.json")
    hist, residual, escaped = histories()
    guards = {"cycle2_baseline": _run(["validation/v2/cycle2_baseline.py", "--check"]),
              "checker_calibration": _run(["validation/v2/checker_calibration.py", "--check"]),
              "f1_f11": _run(["validation/v2/freeze_conformance.py", "--check"]),
              "v1_guard": _run(["validation/v2/v1_evidence_guard.py", "--check"]),
              "run_history": _run(["validation/v2/run_history.py", "check"]),
              "mutation": _run(["validation/v2/mutation.py", "--check"]),
              "orchestration_repair_record": _run(["validation/qualification/c2_orchestration_repair.py", "--check"]),
              "v1_pf_001_policy": _run(["validation/qualification/v1_pf_001_policy.py", "--check"]),
              "c2_p10_cohort": _run(["validation/qualification/c2_p10_cohort.py", "--check"]),
              "c2_p10_profile": _run(["validation/qualification/c2_p10_profile.py", "--check"])}
    problems += [f"guard {k}: exit {g['exit']}" for k, g in guards.items() if g["exit"]]
    pr = json.loads(subprocess.run(["gh", "pr", "view", "6", "--json", "state,isDraft,headRefOid,baseRefName,mergedAt,headRefName"], cwd=ROOT,
                                   capture_output=True, encoding="utf-8", check=True).stdout)
    master = git("ls-remote", "origin", "refs/heads/master").split()[0]
    recurrence_blob = {"at_the_stop_commit_4513608": git("rev-parse", f"45136086c3e4a98534f975e6db979f94165af5f3:{CY}/V1-PF-001-RECURRENCE-1.json"),
                       "now": git("rev-parse", f"HEAD:{CY}/V1-PF-001-RECURRENCE-1.json")}
    att1 = {"at_the_stop_commit_4513608": git("rev-parse", f"45136086c3e4a98534f975e6db979f94165af5f3:{CY}/Q0-Q3"), "now": git("rev-parse", f"HEAD:{CY}/Q0-Q3")}
    for name, cond in (("R4 is not GREEN", r4["verdict"] != "GREEN"), ("Q4-FINAL is not GREEN", q4f["status"] != "GREEN"),
                       ("Q5-FINAL is not GREEN", q5f["status"] != "GREEN"), ("a contract/spec identity changed", v["semantic_change"] != "NONE" or bool(v["problems"])),
                       ("the recorded recurrence was rewritten", recurrence_blob["at_the_stop_commit_4513608"] != recurrence_blob["now"]),
                       ("the 6311254 records were rewritten", att1["at_the_stop_commit_4513608"] != att1["now"]),
                       ("a cohort exists", coh["census"]["cohort_count"] != 0),
                       ("PR #6 is merged", pr["state"] == "MERGED" or pr["mergedAt"]), ("master moved", not master.startswith(MASTER)),
                       ("LedgerLock is not DEVELOPMENT_REGRESSION / NONE / NOT_CLAIMED",
                        (ll["benchmark_class"], ll["generalization_claim"], ll["plan_quality_verdict"]) != ("DEVELOPMENT_REGRESSION", "NONE", "NOT_CLAIMED")),
                       ("the final integration record has problems", bool(fin["problems"])), ("a residual or escaped process is recorded", residual or escaped)):
        if cond:
            problems.append(name)
    rulings = v["rulings"]
    items = {
        "01_p5_owner_acceptance": {**ident(f"{CY}/C2-P5-ACCEPTANCE.json"), "verdict": acc["verdict"], "corrigendum": {**ident(f"{CY}/C2-P5-ACCEPTANCE-CORRIGENDUM-1.json"), "verdict": corr["verdict"]}},
        "02_owner_identity": acc["owner_identity"],
        "03_contract_approvals": {**ident(f"{CY}/P5-CONTRACT-APPROVALS.json"), "count": appr["count"], "aggregate_digest": appr["aggregate_digest"],
                                  "approvers": sorted({r["approver"] for r in appr["approvals"]})},
        "04_synthetic_not_persisted": {"synthetic_identity": acc["contract_approvals"]["synthetic_identity"], "persisted": acc["contract_approvals"]["synthetic_identity_persisted"],
                                       "approvers_in_the_file": sorted({r["approver"] for r in appr["approvals"]}),
                                       "admission_with_the_real_approvals_only": {k: v["admission"][k] for k in ("admitted", "checks_passed", "synthetic_approval_used")}},
        "05_plan_v22_identity": {"plan_hash": v["identities"]["plan_hash"], "proposal_digest": v["identities"]["proposal_digest"], "accepted": acc["accepted"],
                                 "proposal_kernel_provenance": v["proposal_kernel_provenance"]},
        "06_or_iface_1": rulings.get("OR-IFACE-1"), "07_or_iface_2": {k: rulings[k] for k in rulings if k.startswith("OR-IFACE-2")},
        "08_or_iface_3": {"binding": rulings.get("OR-IFACE-3"), "corrigendum": {"corrected_statement": corr["corrected_statement"], "measured": corr["measured"]}},
        "09_unsupported_clauses": acc["unsupported_clauses"], "10_requirement_ambiguities": acc["requirement_ambiguities"],
        "11_p5_history": {**hist.get("C2-P5", {}), "closed_at": acc["attempt_history"]},
        "12_c2_p6_candidate": {"qp26_gate_candidate_r3": p6["candidate"], "lineage": p6["lineage"], "closure": ident(f"{CY}/C2-P6-CLOSURE.json"),
                               "final_candidate_r4": {"commit": r4["candidate"], "kernel_tree": r4["kernel_tree"]}},
        "13_16_q0_q3": {"R3_on_37dc0dc": {k: r3[k] for k in ("summary", "verdict", "rungs")}, "R4_on_the_final_candidate": {k: r4[k] for k in ("summary", "verdict", "rungs")}},
        "17_mutation": {"R3": r3["mutation"], "R4": r4["mutation"]},
        "18_fault_families": r4["fault_matrix"],
        "19_23_platforms": {"R3": r3["platforms"], "R4": r4["platforms"]},
        "24_c2_p7_subject": {"qp27_on_37dc0dc": {k: q4[k] for k in ("subject", "one_kernel_identity", "semantic_candidate", "kernel_tree", "execution_commit")},
                             "final": {k: q4f[k] for k in ("subject", "one_kernel_identity", "semantic_candidate", "kernel_tree", "execution_commit")}},
        "25_27_q4": {"qp27_on_37dc0dc": q4, "final": q4f},
        "28_30_q5": {"qp28_on_37dc0dc": q5, "final": q5f},
        "31_ledgerlock_candidate_profile": {"record": ident(f"{CY}/P10/attempt-2/LEDGERLOCK-REGRESSION.json"), "execution_commit": ll["repository_execution_commit"],
                                            "kernel_tree": ll["aisef2_tree"], "plan": ll["plan_identity"], "profile": {k: ll["execution_profile"][k] for k in ("source", "runspec_hash", "aggregate_min_grade", "limits", "grade_note")},
                                            "attempts": [ident(f"{CY}/P10/NO-RECORD.json"), ident(f"{CY}/P10/attempt-2/LEDGERLOCK-REGRESSION.json")],
                                            "story_account": ident(f"{CY}/P10/attempt-2/STORY-ACCOUNT.json")},
        "32_delivery_verdict": {"verdict": ll["delivery_verdict"], "story_outcomes": ll["story_outcomes"],
                                "productproof": {k: ll["productproof"][k] for k in ("total", "with_a_verified_proof", "satisfied_at_last_proof", "delivered_in_committed_stories")},
                                "requirements": {k: ll["requirements"][k] for k in ("covered_by_productproof", "unsupported", "engineering_test_only", "classes")}},
        "33_plan_quality_verdict": ll["plan_quality_verdict"], "34_raw_plan_quality_metrics": ll["plan_quality_metrics"],
        "35_generalization": ll["generalization_claim"], "36_classification": ll["benchmark_class"],
        "37_cohort_lifecycle": {"record": ident(f"{CY}/P10-COHORT-MACHINERY.json"), "verdict": coh["verdict"], "machinery": coh["machinery"], "positive": coh["positive"],
                                "tests": coh["tests"], "mutation": coh["mutation"]},
        "38_cohort_adversarial": coh["adversarial"], "39_cohort_count": coh["census"],
        "40_profile_freeze": {"record": ident(f"{CY}/P10-PROFILE-FREEZE.json"), "verdict": prof["verdict"], "live_provider_calls": prof["live_provider_calls"], "per_run": prof["per_run"]},
        "41_attested_fixed_model": [c for c in prof["classifications"] if c.get("id") == "FIX-FIXED"],
        "42_opaque_alias": [{k: c.get(k) for k in ("id", "source", "grade", "reasons", "route")} for c in prof["classifications"] if c.get("id") != "FIX-FIXED"],
        "43_topology": {"LANE-R": "main worktree, ade198e", "LANE-O": "worktree .claude/worktrees/lane-o-orchestration, branch c2/lane-o-orchestration, cacaa6b",
                        "integration_1": "6368ae5 -> ac4a6c7 (R2, failed on Windows) -> 37dc0dc (R3, GREEN; C2-P6 closed at 9bd16fa)",
                        "LANE-Q": "main worktree, branch hardening/systematic-v1: Q4 74dffbc, Q5 fbde1d9, QP-2.9 attempt 1 1f992ba, attempt 2 266e4e2",
                        "LANE-X": "worktree .claude/worktrees/lane-x-p10, branch c2/lane-x-p10, base 9bd16fa, head 6353aa8",
                        "final_integration": "worktree .claude/worktrees/c2-final-int, branch c2/final-integration: candidate c11615a, R4 53408cb; merged to the main branch at 849b7e5"},
        "44_final_integration_candidate": {"commit": r4["candidate"], "kernel_tree": r4["kernel_tree"], "head_when_written": git("rev-parse", "HEAD"), "record": ident(f"{CY}/C2-FINAL-INTEGRATION.json")},
        "45_identity_impact": {"changed_trees": fin["changed_trees"], "kernel_change": fin["kernel_change"], "per_rung": fin["identity_impact"]},
        "46_reruns": {"QP-2.6": "R4 on the final candidate, GREEN", "Q4": "Q4-FINAL, fresh 100k", "Q5": "Q5-FINAL, corpus recorded and reproduced",
                      "QP-2.9": "not rerun (no executed path changed)", "binding_corrigendum": ident(f"{CY}/C2-P7-P8-BINDING-CORRIGENDUM-1.json")},
        "47_51_guards": guards, "51_cycle1_drift": v["cycle1_drift"],
        "52_probes": v["identities"]["catalog"],
        "53_histories": hist, "54_residual_processes": residual, "55_escaped_processes": escaped,
        "56_architecture_exceptions": {"new_in_this_scope": [], "note": "no Architecture Exception was needed or requested after V2-006; the effective RFC lineage ends at V2-006 (Q0 checks it)"},
        "57_stop_rules": {"triggered_and_reported": ["V1-PF-001 recurrence at a76177e (resolved by owner ruling B: RECORD_ONLY after WP-4.2)",
                                                     "QP-2.9 preflight: one probe per story (resolved by owner ruling B: C2-ORCHESTRATION-CONFORMANCE-REPAIR)"],
                          "owner_choices": ["2026-10-01: the narrow C2-P5 kernel-provenance rule"], "open": []},
        "58_working_tree": git("status", "--short"),
        "59_pr_6": pr, "60_master": {"origin_master": master, "expected_prefix": MASTER, "unchanged": master.startswith(MASTER)},
        "61_final_statement": STATEMENT,
    }
    ruling_b = {
        "v1_pf_001_policy": {"ruling": ident(f"{CY}/C2-OWNER-RULING-2026-09-30-B.json"), "amendment": ident(f"{CY}/V2-RETRY-POLICY-AMENDMENT-1.json"),
                             "checker": ident("validation/v2/run_history.py"), "decision": {**ident(f"{CY}/V1-PF-001-RECURRENCE-1-DECISION.json"), "derived_effect": dec.get("derived_effect")}},
        "recurrence_preserved": {**ident(f"{CY}/V1-PF-001-RECURRENCE-1.json"), "git_blob": recurrence_blob,
                                 "history_entry": next(x for x in hist["C2-P6"]["failed"] if x["known_defect"] == "V1-PF-001")},
        "calibration_cases": {**ident(f"{CY}/V1-PF-001-POLICY-CALIBRATION.json"), "all_held": cal["all_held"],
                              "cases": {c["id"]: c["observed"] for c in cal["cases"]}},
        "orchestration_reproducer": rep["defect_reproducer"], "single_probe_equivalence": {k: rep["single_probe_equivalence"][k] for k in ("items", "identical")},
        "test_matrix": rep["test_matrix"], "orchestration_files_changed": rep["files_changed"], "repair_record": ident(f"{CY}/C2-ORCHESTRATION-CONFORMANCE-REPAIR.json"),
        "contract_spec_identities": {"contracts": len(v["identities"]["specs"]), "all_equal_to_accepted": all(r["equal_to_accepted"] for r in v["identities"]["specs"]),
                                     "semantic_change": v["semantic_change"], "digest": rep["identities"]["contract_spec_semantic_digest"]},
        "attempt_1_6311254_retained": {"summary": ident(f"{CY}/Q0-Q3/SUMMARY.json"), "git_tree": att1},
        "new_qp26": {"gate_candidate": "37dc0dcdf819387b65ee60cf614273df94aaef31 (R3)", "final_candidate": f"{r4['candidate']} (R4)", "R2_failed_kept": ident(f"{CY}/Q0-Q3-R2/SUMMARY.json")},
    }
    return {"record": "AISEF V2 — CYCLE-2 P6/P7/P8/P9/P10 COMPLETE / V2 READY FOR FINAL OWNER CLOSURE REVIEW",
            "authority": "owner rulings 2026-09-30 A and B", "written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "items": items, "ruling_b_additions": ruling_b, "problems": problems,
            "verdict": "COMPLETE — READY FOR FINAL OWNER CLOSURE REVIEW" if not problems else "PROBLEMS"}


def markdown(r: dict) -> str:
    i, b = r["items"], r["ruling_b_additions"]
    ll, q = i["32_delivery_verdict"], i["19_23_platforms"]["R4"]
    row = lambda p: " | ".join(f"{q[p][k]['status']} {q[p][k]['pass']}" + (f" (+{q[p][k]['not_applicable']} N/A)" if q[p][k]["not_applicable"] else "") for k in ("Q0", "Q1", "Q2", "Q3"))  # noqa: E731
    lines = [f"# {r['record']}", "", f"Written {r['written']}. Verdict: **{r['verdict']}**. Problems: {r['problems'] or 'none'}.", "",
             "Every figure below is read from the record named in `C2-FINAL-REPORT.json` (bound by sha256).", "",
             "## QP-2.6 on the final candidate (R4)", "", f"Candidate `{i['44_final_integration_candidate']['commit']}`, kernel tree `{i['44_final_integration_candidate']['kernel_tree']}`.", "",
             "| platform | Q0 | Q1 | Q2 | Q3 |", "|---|---|---|---|---|", *[f"| {p} | {row(p)} |" for p in PLATFORMS], "",
             f"Mutation: {i['17_mutation']['R4']}. Residual processes recorded across all Cycle-2 histories: {i['54_residual_processes']}; escaped: {i['55_escaped_processes']}.", "",
             "## Q4 / Q5", "",
             f"- Q4 (final): {i['25_27_q4']['final']['status']}, {i['25_27_q4']['final']['totals']['MATCHED']} / {i['25_27_q4']['final']['totals']['requested']} matched, "
             f"divergences {i['25_27_q4']['final']['unexplained_divergences']}, kernel digest `{i['25_27_q4']['final']['kernel_digest']}`.",
             f"- Q5 (final): {i['28_30_q5']['final']['status']}, {i['28_30_q5']['final']['green']} / {i['28_30_q5']['final']['items']} items, corpus `{i['28_30_q5']['final']['corpus_digest']}`, "
             f"assertConsumed {i['28_30_q5']['final']['assert_consumed']}, re-execution {i['28_30_q5']['final']['re_execution']}.", "",
             "## LedgerLock (QP-2.9, attempt 2)", "",
             f"- classification **{i['36_classification']}**, generalization **{i['35_generalization']}**, delivery_verdict **{ll['verdict']}**, plan_quality_verdict **{i['33_plan_quality_verdict']}**.",
             f"- stories: {ll['story_outcomes']}", f"- ProductProof: {ll['productproof']}",
             f"- raw plan-quality metrics: {i['34_raw_plan_quality_metrics']}", "",
             "## C2-P10", "", f"- cohort machinery: {i['37_cohort_lifecycle']['verdict']}", f"- profile freeze: {i['40_profile_freeze']['verdict']}; live provider calls {i['40_profile_freeze']['live_provider_calls']}", "",
             "## Ruling-B additions", "", f"- V1-PF-001 calibration all held: {b['calibration_cases']['all_held']}; cases {b['calibration_cases']['cases']}",
             f"- 59 identities: {b['contract_spec_identities']}", "",
             "## Final statement", "", *STATEMENT, ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", required=True)
    ap.parse_args(argv)
    r = build()
    (ROOT / OUT_JSON).write_text(json.dumps(r, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8", newline="\n")
    (ROOT / OUT_MD).write_text(markdown(r), encoding="utf-8", newline="\n")
    print(r["verdict"])
    for p in r["problems"]:
        print("  " + p)
    return 1 if r["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
