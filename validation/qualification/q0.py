"""Q0 — static integrity (RFC §27; owner §6–§7). Zero-provider; executes no project's admission.

Every current Q0 checker runs against the exact candidate through `checker_calibration.run()` — the count is what
discovery finds, never a constant — and each must pass the clean tree, reject its committed known-bad fixture for the
named reason, and have its always-PASS mutant rejected. On top: the required families named by the owner are mapped
to the checkers that discharge them (fail-closed if a family has no checker); the V2-006 / F5 amendment is verified
explicitly; the P4/P5/P6 seal identities, the V1 evidence identity and the catalog's both-direction fail-closed
behaviour are asserted; and removing the new F5 subcheck is shown to fail Q0.

Cycle 2 (QP-2.6): the same rung on the Cycle-2 candidate, extended — the six probe source rules and the Cycle-2
baseline guard as families of their own (each a discovered, calibrated checker whose known-bad probe fixture fails
it); the catalog's probe identities (every active Cycle-2 probe, the frozen Cycle-1 probe resolvable and inactive);
the owner's C2-P5 acceptance and its real approvals re-derived; the Cycle-1 seal lineage still asserted.
"""

from __future__ import annotations

import json
from unittest import mock

from . import common as C

OLD_PROBE_DIGEST = "c335293e03a0f3b7175a39371fe2fb3b6331d5a29d349409fb72470d8c46278e"   # pre-V2-006
#: every probe digest that is history on this tree, oldest first: pre-V2-006, then V2-006 up to the P7-FINDING-001
#: correction (the correction record carries the effective one)
OLD_PROBE_DIGESTS = {OLD_PROBE_DIGEST: "pre-V2-006",
                     "ac434a4260cdc1ebbd7e5841959a89c3de8edc2c8552e7714cb85962bc0922a0": "V2-006 to the P7-FINDING-001 correction"}
CORRECTION_REL = "closure-evidence/v2/P7-FINDING-001/CORRECTION.json"
NEW_F5_SUBCHECK = "F5.protocol_stream_vs_process_lifecycle"
#: owner §6: each required family -> the Q0 checkers (by their discovered names) or test cases that discharge it
FAMILIES = {
    "schemas": ["arch_catalog", "p6_evidence", "packaging_check"],
    "provenance": ["freeze_manifest", "run_history", "p1_evidence", "p2_evidence", "p3_evidence", "p4_evidence", "p5_evidence", "p6_evidence"],
    "architecture_catalog": ["arch_catalog"],
    "freeze_amendment_lineage_through_V2_006": ["freeze_manifest", "plan_baseline"],
    "f1_f11_conformance": ["f_conformance"],
    "ownership_graph_and_unique_INTRODUCE": ["plan_semantics", "tests:static_admission_rules"],
    "no_prose_control_walker": ["no_prose_control"],
    "no_projection_reads_time": ["no_time_in_projections"],
    "static_admission_rule_conformance": ["tests:static_admission_rules"],
    "invariant_registry": ["invariants_doc", "no_developer_artefact_at_parent", "candidate_only_execution"],
    "except_boundary_audit": ["except_boundaries"],
    "destructive_authority_audit": ["destructive_authority", "cleanup_authority"],
    "old_path_audit": ["old_path_audit"],
    "migration_table_check": ["migration_table"],
    "seal_identities_P4_P5_P6": ["explicit:seals"],
    "v1_evidence_guard": ["v1_evidence_guard"],
    # Cycle 2 (CYCLE2-QUALIFICATION-PLAN §1): each with its known-bad fixture in the checker calibration
    "cycle2_baseline_cycle1_immutability": ["cycle2_baseline"],
    "probe_registry_closure": ["probe_catalog_closure"],
    "no_clock_in_probe_facts": ["no_clock_in_probe_facts"],
    "no_test_artefact_resolution_in_probes": ["no_test_artefact_in_probes"],
    "scenario_vocabulary_closed": ["closed_dispatch_in_scenario_probes"],
    "placeholder_single_token": ["single_placeholder_token"],
    "protocol_channel_discipline": ["protocol_channel_discipline"],
    "c2_p5_owner_acceptance_and_real_approvals": ["tests:c2_p5_acceptance"],
    # owner ruling 2026-09-30 B: the V1-PF-001 lifecycle after its replacement, calibrated on its known-bad cases
    "v1_pf_001_recurrence_policy": ["run_history", "tests:c2_v1_pf_001_policy"],
}
CYCLE2_ACTIVE = {"file_artifact": "probe.file_artifact", "python_callable": "probe.python_callable_v2",
                 "cli_invocation": "probe.cli_invocation", "process_effect": "probe.process_effect"}
CYCLE1_FROZEN_PROBE = ("probe.python_callable", "1961e84d913edc687bdb52f6c6cd0f034e86f2d1dadd9e89fa76757a51dc35bf")
HISTORICAL_OLD_DIGEST_FILES = {  # evidence that legitimately names the pre-V2-006 digest as history
    "closure-evidence/v2/ARCHITECTURE-EXCEPTION-V2-003.json", "closure-evidence/v2/P4-COMPLETION-CORRECTION-V2-003.json",
    "closure-evidence/v2/P4-FINAL-SEAL.json", "closure-evidence/v2/ARCHITECTURE-EXCEPTION-V2-006.json",
    "closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-006.json", "closure-evidence/v2/P6-V2-006-PROBE-HARNESS.json",
    "closure-evidence/v2/P6-FINAL-SEAL.json", "closure-evidence/v2/P2-RUN-HISTORY.json", "closure-evidence/v2/P6-RUN-HISTORY.json",
    "closure-evidence/v2/P4-RUN-HISTORY.json", "closure-evidence/v2/P5-RUN-HISTORY.json", "closure-evidence/v2/P3-RUN-HISTORY.json",
    # the P7-FINDING-001 record set names the V2-006 digest as the one it measured and corrected
    "closure-evidence/v2/P7-RUN-HISTORY.json", "docs/implementation/v2/P6-V2-006-PROBE-HARNESS.md",
}
HISTORICAL_OLD_DIGEST_PREFIXES = ("closure-evidence/v2/P7-FINDING-001/",)


def _specs_binding(digest: str) -> list[str]:
    """Every stored ProductProofSpec (an object carrying semantic_hash and probe_digest) bound to `digest`."""
    hits = []

    def walk(o, where):
        if isinstance(o, dict):
            if "semantic_hash" in o and o.get("probe_digest") == digest:
                hits.append(where)
            for k, v in o.items():
                walk(v, f"{where}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{where}[{i}]")
    for base in ("tests/v2/fixtures", "closure-evidence/v2", "docs/implementation/v2"):
        for p in sorted((C.ROOT / base).rglob("*.json")):
            rel = p.relative_to(C.ROOT).as_posix()
            if rel in HISTORICAL_OLD_DIGEST_FILES or rel.startswith(HISTORICAL_OLD_DIGEST_PREFIXES) \
                    or rel.startswith(C.CYCLE1_OUT_REL + "/invalidated-") or rel.startswith((C.OUT_REL + "/", *(r + "/" for r in C.C2_PRIOR_OUT_RELS))):
                continue   # measurements of history (the finding's records, invalidated rungs): never a stored spec
            try:
                walk(json.loads(p.read_text(encoding="utf-8")), rel)
            except (ValueError, UnicodeDecodeError):
                continue
    return hits


def _files_mentioning(digest: str) -> list[str]:
    out = []
    for base in ("aisef2", "tests/v2", "validation/v2", "closure-evidence/v2", "docs"):   # not the scanner, not its records
        for p in sorted((C.ROOT / base).rglob("*")):
            if p.is_file() and p.suffix in (".py", ".json", ".md") and "__pycache__" not in p.parts \
                    and not p.relative_to(C.ROOT).as_posix().startswith((C.OUT_REL, C.CYCLE1_OUT_REL, *C.C2_PRIOR_OUT_RELS)):
                try:
                    if digest in p.read_text(encoding="utf-8"):
                        out.append(p.relative_to(C.ROOT).as_posix())
                except UnicodeDecodeError:
                    continue
    return out


def run(ident: dict) -> dict:
    import checker_calibration as cc
    import freeze_conformance as fc
    import freeze_manifest as fm
    import gen_arch_catalog as gc
    import p5_evidence as p5
    import p6_evidence as p6
    import v1_evidence_guard as guard
    from aisef2.arch.enums import Polarity, SubjectAbsence, SubjectKind
    from aisef2.probe import python_callable as pc
    from aisef2.product.approval import ContractApproval, Requirement
    from aisef2.product.compiler import ProbeRef, compile_spec
    from aisef2.product.contract import BehaviorContract, Subject
    problems: list[str] = []
    harness: list[str] = []

    # 1. every current Q0 checker, discovered, calibrated, current
    calibration, err = C.capture(cc.run)
    if err:
        return {"record": "AISEF V2 — Q0 STATIC INTEGRITY", "rung": "Q0", "status": C.UNRUNNABLE, "subject": ident,
                "platform": C.platform_id(), "harness_problems": [f"checker calibration could not run: {err}"], "problems": [], "cases": []}
    cal_problems = cc.problems_of(calibration)
    committed_current = (C.ROOT / cc.OUT_REL).read_text(encoding="utf-8") == cc.render(calibration)
    names = [r["checker"] for r in calibration["checkers"]]
    checkers = {r["checker"]: {"package": r["package"], "clean_passes": r["clean_passes"], "rejects_known_bad": r["rejects_known_bad"],
                               "rejects_for_the_expected_reason": r["rejects_for_the_expected_reason"], "calibrated": r["calibrated"],
                               "always_pass_mutant_rejected": r["always_pass_mutant_rejected_by_calibration"]}
                for r in calibration["checkers"]}
    problems += [f"checker calibration: {p}" for p in cal_problems]
    if not committed_current:
        problems.append(f"{cc.OUT_REL} is not the current calibration")

    # 2. the required families, each discharged by a discovered checker or a named test set
    admission = C.run_module("tests.v2.p2.test_static_admission")   # the engine's rules on fixture plans; no project's admission
    acceptance_cases = C.run_module("tests.v2.test_c2_p5_acceptance")   # re-derives the owner-accepted plan's admission
    policy_cases = C.run_module("tests.v2.test_c2_v1_pf_001_policy")    # the corrected V1-PF-001 rule on its known-bad cases
    catalog_tests = C.run_module("tests.v2.p0.test_arch_catalog")     # fail-closed in both directions
    families = {}
    for fam, refs in FAMILIES.items():
        rows = {}
        for ref in refs:
            if ref == "tests:static_admission_rules":
                rows[ref] = C.status_of(admission)
            elif ref == "tests:c2_p5_acceptance":
                rows[ref] = C.status_of(acceptance_cases)
            elif ref == "tests:c2_v1_pf_001_policy":
                rows[ref] = C.status_of(policy_cases)
            elif ref == "explicit:seals":
                rows[ref] = "asserted below"
            else:
                rows[ref] = "calibrated" if checkers.get(ref, {}).get("calibrated") else f"MISSING or uncalibrated ({ref})"
        families[fam] = rows
        if any(v.startswith("MISSING") or v in (C.FAILED, C.UNRUNNABLE) for v in rows.values()):
            problems.append(f"family {fam} is not discharged: {rows}")
    if C.status_of(catalog_tests) != C.GREEN:
        problems.append("the catalog does not fail closed in both directions: " + "; ".join(C.problems_of(catalog_tests)))

    # 3. F1–F11 at the exact candidate; the V2-006 subcheck present, passing, and load-bearing
    fresh = fc.evaluate(*fc.load_inputs())
    committed = json.loads((C.ROOT / fc.OUT_REL).read_text(encoding="utf-8"))
    f_current = (C.ROOT / fc.OUT_REL).read_text(encoding="utf-8") == fc.render(fresh)
    subs = {s["id"]: s["state"] for s in fresh["subchecks"]}
    f5_rows = {k: v for k, v in subs.items() if k.startswith("F5.")}
    real_subchecks = fc.subchecks

    def without_new_subcheck(rfc, code):
        return [s for s in real_subchecks(rfc, code) if s["id"] != NEW_F5_SUBCHECK]
    with mock.patch.object(fc, "subchecks", without_new_subcheck):
        removed = fc.evaluate(*fc.load_inputs())
    removal_detected = ((C.ROOT / fc.OUT_REL).read_text(encoding="utf-8") != fc.render(removed)
                        and NEW_F5_SUBCHECK not in {s["id"] for s in removed["subchecks"]})
    drifted_pin = C.run_case("tests.v2.conformance.test_freeze_f1_f11", "Conformance",
                             "test_F5_probe_protocol_is_compared_member_by_member_with_signatures")
    f1_f11 = {"summary": fresh["summary"], "ratchet_violations": fresh["ratchet_violations"], "committed_record_current": f_current,
              "f5_subchecks": f5_rows, "new_subcheck_present": NEW_F5_SUBCHECK in subs, "new_subcheck_passes": subs.get(NEW_F5_SUBCHECK) == fc.PASS,
              "removing_the_new_subcheck_fails_q0": removal_detected,
              "how": "with the subcheck removed the committed F-CONFORMANCE.json no longer equals the evaluation (freeze_conformance --check: stale) "
                     "and the pinned conformance case reads the subcheck by id",
              "pinned_case": drifted_pin, "committed_summary": committed["summary"]}
    if fresh["summary"] != {"PASS": 11, "PENDING": 0, "FAIL": 0} or fresh["ratchet_violations"] or not f_current:
        problems.append(f"F1–F11 not 11/0/0 current: {fresh['summary']} ratchet {fresh['ratchet_violations']} current {f_current}")
    if not (f1_f11["new_subcheck_present"] and f1_f11["new_subcheck_passes"] and removal_detected):
        problems.append("the V2-006 F5 subcheck is absent, failing or not load-bearing")

    # 4. the V2-006 amendment, explicitly
    rfc_text = (C.ROOT / fm.RFC_REL).read_text(encoding="utf-8")
    rows = {i["id"]: i["row_sha256"] for i in fm.freeze_items(rfc_text)}
    amendment = json.loads((C.ROOT / "closure-evidence/v2/AISEF-V2-RFC-AMENDMENT-V2-006.json").read_text(encoding="utf-8"))
    exception = json.loads((C.ROOT / "closure-evidence/v2/ARCHITECTURE-EXCEPTION-V2-006.json").read_text(encoding="utf-8"))
    correction = json.loads((C.ROOT / CORRECTION_REL).read_text(encoding="utf-8"))
    eff, links, broken = fm.lineage(C.ROOT)
    req = Requirement.create(id="R", text="q0", source="Q0")
    contract = BehaviorContract.create(id="C", requirement_ids=("R",), subject=Subject(SubjectKind.PYTHON_CALLABLE, "app.calc:add"),
                                       stimulus={}, observable={"condition": "exists", "within_s": 10}, polarity=Polarity.MUST_HOLD,
                                       subject_absence=SubjectAbsence.ABSENCE_IS_DECIDABLE, rationale="q0")
    approval = ContractApproval("R", req.requirement_hash, "C", contract.contract_hash, "human:q0", 0.0, ())
    hashes = {d[:12]: compile_spec(contract, requirements={"R": req}, approvals=[approval],
                                   probes={SubjectKind.PYTHON_CALLABLE: ProbeRef(pc.PROBE_ID, d)}).semantic_hash
              for d in (OLD_PROBE_DIGEST, pc.DIGEST)}
    old_specs = [w for d in OLD_PROBE_DIGESTS for w in _specs_binding(d)]
    mentions = sorted({f for d in OLD_PROBE_DIGESTS for f in _files_mentioning(d)})
    historical = lambda f: f in HISTORICAL_OLD_DIGEST_FILES or f.startswith(HISTORICAL_OLD_DIGEST_PREFIXES)  # noqa: E731
    v2_006 = {
        "lineage_ends_at_V2_006": bool(links) and links[-1]["record"].endswith("AMENDMENT-V2-006.json") and not broken,
        "effective_digests_equal_the_amendment": (eff.get("rfc_normative_digest"), eff.get("freeze_table_digest"))
            == (amendment["rfc_normative_digest"]["after"], amendment["freeze_table_digest"]["after"]),
        "f5_row_sha256": {"rfc_now": rows.get("F5"), "amendment_after": amendment["f5_row_sha256"]["after"],
                          "match": rows.get("F5") == amendment["f5_row_sha256"]["after"]},
        # the effective probe digest: V2-006's "after" was corrected by P7-FINDING-001 (the correction record's
        # "before" is V2-006's "after"; its "after" is what the tree computes); every earlier digest is history
        "probe_digest": {"now": pc.DIGEST, "v2_006_exception_after": exception["digests"]["probe_digest"]["after"],
                         "correction_before": correction["probe_digest"]["before"], "correction_after": correction["probe_digest"]["after"],
                         "old": OLD_PROBE_DIGESTS,
                         "match": pc.DIGEST == correction["probe_digest"]["after"] and correction["probe_digest"]["before"]
                                  == exception["digests"]["probe_digest"]["after"] and pc.DIGEST not in OLD_PROBE_DIGESTS},
        "f4_semantic_hash_incorporates_the_probe_digest": {"by_digest_prefix": hashes, "differs": len(set(hashes.values())) == 2},
        "stored_specs_bound_to_the_old_digest": old_specs,
        "files_naming_the_old_digest": mentions,
        "files_naming_the_old_digest_outside_the_historical_set": sorted(f for f in mentions if not historical(f)),
        "p2_calibration_digests": sorted({c["probe_digest"] for c in json.loads(
            (C.ROOT / "closure-evidence/v2/P2-CALIBRATION.json").read_text(encoding="utf-8"))["calibrations"]}),
    }
    if not (v2_006["lineage_ends_at_V2_006"] and v2_006["effective_digests_equal_the_amendment"] and v2_006["f5_row_sha256"]["match"]
            and v2_006["probe_digest"]["match"] and v2_006["f4_semantic_hash_incorporates_the_probe_digest"]["differs"]):
        problems.append("the V2-006 amendment (with the P7-FINDING-001 probe correction) is not the effective one on this tree")
    if old_specs:
        problems.append(f"stored specs still bind an old probe digest: {old_specs}")
    if v2_006["files_naming_the_old_digest_outside_the_historical_set"]:
        problems.append(f"the old probe digest is named outside historical evidence: {v2_006['files_naming_the_old_digest_outside_the_historical_set']}")
    if v2_006["p2_calibration_digests"] != [pc.DIGEST]:
        problems.append("P2-CALIBRATION is not calibrated under the current probe digest only")

    # 5. seal identities and V1 identity
    p4, p5s, p6s = (C.ROOT / f"closure-evidence/v2/P{n}-FINAL-SEAL.json" for n in (4, 5, 6))
    seal5 = json.loads(p5s.read_text(encoding="utf-8"))
    seal6 = json.loads(p6s.read_text(encoding="utf-8"))
    at_seal_commit = C.git("show", f"{C.CYCLE1_SEAL_COMMIT}:closure-evidence/v2/P6-FINAL-SEAL.json")
    seals = {
        "p4": {"sha256": C.lf_sha(p4), "bound_by_p5_seal": seal5["p4_seal"]["sha256"], "bound_by_p6_seal": seal6["p4_seal"]["sha256"]},
        "p5": {"sha256": C.lf_sha(p5s), "bound_by_p6_seal": seal6["p5_seal"]["sha256"], "verdict": seal5["verdict"]},
        "p6": {"sha256": C.lf_sha(p6s), "at_the_seal_commit": C.sha_text(at_seal_commit.replace("\r\n", "\n") + ("" if at_seal_commit.endswith("\n") else "\n")),
               "verdict": seal6["verdict"], "candidate": seal6["p6_candidate"]["commit"], "aisef2_tree": seal6["p6_candidate"]["aisef2_tree"]},
        "p5_records_identity_problems": p5.check(C.ROOT), "p6_records_identity_problems": p6.check(C.ROOT),
        # post-P6 corrective lineage (owner §21-§22): the P6 seal keeps naming the candidate it sealed; the harness's
        # candidate is the one the correction record says supersedes it
        "post_p6_corrective_lineage": {"sealed_candidate": seal6["p6_candidate"]["commit"], "sealed_aisef2_tree": seal6["p6_candidate"]["aisef2_tree"],
                                       "superseded": correction["lineage"]["new_semantic_candidate"]["supersedes"],
                                       "old_candidate_in_correction": correction["lineage"]["old_semantic_candidate"]["commit"],
                                       "corrected_candidate": correction["lineage"]["new_semantic_candidate"]["commit"],
                                       "corrected_aisef2_tree": correction["lineage"]["new_semantic_candidate"]["aisef2_tree"],
                                       "harness_candidate": C.CYCLE1_SEMANTIC_CANDIDATE, "harness_kernel_tree": C.CYCLE1_KERNEL_TREE},
    }
    seals["p6"]["byte_identical_to_the_seal_commit"] = C.git("rev-parse", f"{C.CYCLE1_SEAL_COMMIT}:closure-evidence/v2/P6-FINAL-SEAL.json") \
        == C.git("rev-parse", "HEAD:closure-evidence/v2/P6-FINAL-SEAL.json")
    ok_seals = (seals["p4"]["sha256"] == seals["p4"]["bound_by_p5_seal"] == seals["p4"]["bound_by_p6_seal"]
                and seals["p5"]["sha256"] == seals["p5"]["bound_by_p6_seal"] and seals["p5"]["verdict"] == "P5 FINAL SEALED"
                and seals["p6"]["verdict"] == "P6 FINAL SEALED" and seals["p6"]["byte_identical_to_the_seal_commit"]
                and seals["p6"]["candidate"] == seals["post_p6_corrective_lineage"]["superseded"]
                == seals["post_p6_corrective_lineage"]["old_candidate_in_correction"]
                and seals["post_p6_corrective_lineage"]["corrected_candidate"] == C.CYCLE1_SEMANTIC_CANDIDATE
                and seals["post_p6_corrective_lineage"]["corrected_aisef2_tree"] == C.CYCLE1_KERNEL_TREE
                and seals["p6"]["aisef2_tree"] == correction["lineage"]["old_semantic_candidate"]["aisef2_tree"]
                and not seals["p5_records_identity_problems"] and not seals["p6_records_identity_problems"])
    if not ok_seals:
        problems.append("a seal identity does not hold")
    w0 = C.ROOT / "closure-evidence/hardening/AISEF-W0-QUALIFICATION.json"
    v1 = {"guard_problems": guard.check(), "w0_sha256": C.lf_sha(w0),   # LF-normalised: the file is LF, so this is its raw sha on a
          # POSIX checkout and the same value on a CRLF checkout; the git blob below is the byte identity on every platform
          "w0_blob_at_HEAD": C.git("rev-parse", "HEAD:closure-evidence/hardening/AISEF-W0-QUALIFICATION.json"),
          "w0_blob_at_the_candidate": C.git("rev-parse", f"{C.SEMANTIC_CANDIDATE}:closure-evidence/hardening/AISEF-W0-QUALIFICATION.json"),
          "w0_expected": "a14c2f58083bd32dc7b7c3ce5e35bb22a4bba9e745d109538a877464df21fba3",
          "v1_product_tree": ident["v1_product_tree"], "v1_product_tree_at_p5_seal": seal5["p5_candidate"]["v1_product_tree"],
          "external_validation_tree": C.git("rev-parse", "HEAD:closure-evidence/external-validation"),
          "external_validation_tree_at_p5_seal": C.git("rev-parse", f"{seal5['seal_commit']}:closure-evidence/external-validation")
          if "seal_commit" in seal5 else C.git("rev-parse", f"{C.SEMANTIC_CANDIDATE}:closure-evidence/external-validation")}
    if v1["guard_problems"] or v1["w0_sha256"] != v1["w0_expected"] or v1["w0_blob_at_HEAD"] != v1["w0_blob_at_the_candidate"] \
            or v1["v1_product_tree"] != v1["v1_product_tree_at_p5_seal"] or v1["external_validation_tree"] != v1["external_validation_tree_at_p5_seal"]:
        problems.append("the V1 identity does not hold")

    catalog = {"check_problems": gc.check(C.ROOT), "both_directions": C.counts(catalog_tests)}
    if catalog["check_problems"]:
        problems.append(f"architecture catalog: {catalog['check_problems']}")

    # 6. Cycle 2: the probe identities, the Cycle-1 probe frozen and inactive, the owner's C2-P5 acceptance re-derived
    from aisef2.probe import catalog as probe_catalog
    from validation.qualification import p5_acceptance as pa
    entries = {e.probe_id: e for e in probe_catalog.CATALOG}
    active = {k.value: e.probe_id for k, e in probe_catalog.active().items()}
    frozen = entries.get(CYCLE1_FROZEN_PROBE[0])
    acceptance = json.loads((C.ROOT / C.C2_P5_ACCEPTANCE_REL).read_text(encoding="utf-8"))
    cycle2 = {
        "probes": {pid: {"digest": e.probe_digest, "kind": e.subject_kind.value, "active": e.active, "cycle": e.cycle,
                         "module": e.factory.__module__} for pid, e in sorted(entries.items())},
        "active_by_kind": active, "active_expected": CYCLE2_ACTIVE,
        "catalog_problems": probe_catalog.problems_of(probe_catalog.CATALOG),
        "cycle1_probe": {"id": CYCLE1_FROZEN_PROBE[0], "frozen_digest": CYCLE1_FROZEN_PROBE[1],
                         "catalog_digest": frozen.probe_digest if frozen else None, "module_digest": pc.DIGEST,
                         "active": frozen.active if frozen else None,
                         "resolvable_and_inactive": bool(frozen) and frozen.probe_digest == pc.DIGEST == CYCLE1_FROZEN_PROBE[1]
                         and not frozen.active},
        "probe_rule_checkers": {k: checkers.get(k) for k in ("probe_catalog_closure", "no_clock_in_probe_facts", "no_test_artefact_in_probes",
                                                              "closed_dispatch_in_scenario_probes", "single_placeholder_token",
                                                              "protocol_channel_discipline", "cycle2_baseline")},
        "c2_p5_acceptance": {"record": C.C2_P5_ACCEPTANCE_REL, "sha256": C.lf_sha(C.ROOT / C.C2_P5_ACCEPTANCE_REL),
                             "verdict": acceptance["verdict"], "re_derivation_problems": pa.check(),
                             "approvals": acceptance["contract_approvals"]["count"],
                             "aggregate_digest": acceptance["contract_approvals"]["aggregate_digest"], "cases": acceptance_cases},
    }
    if active != CYCLE2_ACTIVE or cycle2["catalog_problems"]:
        problems.append(f"the active probe set is not the Cycle-2 one: {active} {cycle2['catalog_problems']}")
    if not cycle2["cycle1_probe"]["resolvable_and_inactive"]:
        problems.append(f"the Cycle-1 probe is not resolvable at its frozen digest and inactive: {cycle2['cycle1_probe']}")
    if not all(v and v["calibrated"] and v["rejects_known_bad"] for v in cycle2["probe_rule_checkers"].values()):
        problems.append("a Cycle-2 probe rule checker is missing, uncalibrated or does not reject its known-bad probe fixture")
    if cycle2["c2_p5_acceptance"]["re_derivation_problems"] or not acceptance["verdict"].startswith("C2-P5 ACCEPTED"):
        problems.append(f"the C2-P5 acceptance does not re-derive: {cycle2['c2_p5_acceptance']['re_derivation_problems']}")

    cases = admission + catalog_tests + [drifted_pin] + acceptance_cases + policy_cases
    status = C.status_of(cases, problems, harness)
    return {
        "record": "AISEF V2 — Q0 STATIC INTEGRITY", "rung": "Q0", "status": status, "at": C.now(),
        "rule": "zero-provider; no project admission executed; every Q0 checker discovered and calibrated; fail-closed both ways",
        "subject": ident, "platform": C.platform_id(),
        "checker_calibration": {"discovered": len(names), "names": names, "calibrated": calibration["calibrated_count"],
                                "always_pass_mutants_rejected": calibration["always_pass_mutants_rejected"],
                                "uncovered_checker_modules": calibration["uncovered_checker_modules"], "problems": cal_problems,
                                "committed_record_current": committed_current, "checkers": checkers},
        "families": families, "static_admission_rules": {"counts": C.counts(admission), "cases": admission,
                                                          "executes_no_probe_and_no_process": next((c["outcome"] for c in admission
                                                                                                    if c["id"].endswith("test_the_engine_executes_no_probe_and_no_process")), None)},
        "architecture_catalog": {**catalog, "cases": catalog_tests},
        "f1_f11": f1_f11, "v2_006": v2_006, "seals": seals, "v1": v1, "cycle2": cycle2,
        "provider_calls": 0, "project_admissions_executed": 0,
        "problems": problems, "harness_problems": harness, "cases": cases, "counts": C.counts(cases),
    }
