"""V2.1 CONFORMANCE-RULING (owner B-03d, closure-evidence/v2/cycle2/RELEASE-DECISIONS.json seq 5): 2.1's behaviour changes
named against the historical cycle-2 record closure-evidence/v2/cycle2/C2-ORCHESTRATION-CONFORMANCE-REPAIR.json, which
stays byte-identical. c2_orchestration_repair.release_differences reads the committed ruling and accepts a 2.1 change
through it only by content (the file's LF sha256 is the row's sha256_2_1).

    python -P validation/qualification/v21_conformance_ruling.py --write [--out PATH]   # closure-evidence/v2/v2.1/CONFORMANCE-RULING.json
    python -P validation/qualification/v21_conformance_ruling.py --check [--out PATH]   # exit 1 unless the ruling is what this tree derives

Derived on this tree, except the per-file reasons (ROWS, IDENTITY_WHY) and the fixed statements:
- authority: the owner's B-03d text, quoted verbatim from the ledger entry (checked); who wrote the file;
- conformance: ONE ROW PER FILE that c2_orchestration_repair.check reports under (d) and that 2.1 changed (its LF sha256
  at v2.0.0 is not its sha256 now): both shas, the 2.1 commits touching it (git log 610a593..HEAD), the backlog item and
  decision, whether the owner approved the change itself, the requirement it serves and its behaviour tests (each
  test id must exist: module, class, method). A file the tree reports that ROWS does not explain, or the reverse, is
  a problem: nothing is written;
- identity: the SEMANTIC_IDENTITIES that moved from the record, each with its reason; the probe sources that moved,
  each named by a row or by the V2.0 list; the engine digest is NOT tolerated — the (e) gate is B-03a's re-verification;
- q5: validation/qualification/v21_q5_changes.py's CHANGES and UNCHANGED as they are, against q5.CORPUS;
- mutation: B-03b's phase V2.1 — (f) is accepted only while validation/v2/mutation.py check() == [];
- history: the record's (a)/(b)/(c) are cycle-2 executions; the record is its v2.0.0 blob; c2_orchestration_repair
  --write refuses on 2.1;
- what is unchanged and what is not done.
--write opens its output with mode "x", refuses a path in the repository outside closure-evidence/v2/v2.1/ (every 2.0
and cycle-2 record), a tree whose aisef2/, tests/v2/ or validation/ is not committed, and any problem. --check
re-derives the ruling and names each difference: a row missing, an extra row, a row field (a sha drift, a commit), a
stale section.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import c2_orchestration_repair as rp  # noqa: E402
from validation.qualification import common as C  # noqa: E402
from validation.qualification import p5_acceptance as pa  # noqa: E402
from validation.qualification import rebind  # noqa: E402
from validation.qualification import v21_q5_changes as X  # noqa: E402

OUT_REL = "closure-evidence/v2/v2.1/CONFORMANCE-RULING.json"
V21_DIR = "closure-evidence/v2/v2.1"
V2_0_0 = X.V2_0_0
#: 2.0.0 plus docs (aisef2 identical to v2.0.0's): the 2.1 commits are the ones after it
SINCE = "610a5935281fd01a707e035bef33499569fdbb15"
DEPENDS = ("aisef2", "tests/v2", "validation")
D_FINDINGS = ("changed since the record", "changed since the base and is not in the record")
B03D_REF = {**pa.B03_REF, "part": "B-03d"}
B01_REF = {"path": pa.DECISIONS_REL, "seq": 4, "id": "AISEF_V2_1_B01_ARCHITECTURE_EXCEPTION_V2_007"}
#: the owner's words, verbatim from the ledger entry B-03 (seq 5)
B03D_TEXT = ("B-03d — Conformance và Q5\nCho phép tạo ruling nêu rõ thay đổi hành vi của 2.1 và corpus Q5 mới tương ứng. Giữ "
             "nguyên corpus, ruling và evidence của 2.0.\nMỗi thay đổi kỳ vọng phải truy được tới requirement/quyết định đã "
             "duyệt và bằng chứng hành vi; không sửa kỳ vọng chỉ để test xanh.")
NO_WEAKENING = "Không bỏ test, giảm assertion, thêm skip/xfail hoặc nới oracle để đạt PASS."

V2_007 = ("ARCHITECTURE-EXCEPTION-V2-007 APPROVED by the owner (B-01, RELEASE-DECISIONS seq 4); applied in 919a271 before "
          "that approval (closure-evidence/v2/v2.1/ARCHITECTURE-EXCEPTION-V2-007.json says so)")


def _engineering(what: str) -> str:
    return f"none of its own: an engineering change ({what}); B-03d authorizes this ruling to name it, not the change"


_REVIEW = {"backlog": "docs/v2.1/STATUS.md §2 C1, C3 (e897437)", "owner_approval": _engineering("docs/v2.1/ADR-V2.1.md ADR-7"),
           "requirement": "RFC §25: a blocking decision MUST NOT rest on a model reviewer alone (D-002); each finding is a "
                          "gate/check row"}
_PROBE = {"backlog": "docs/v2.1/STATUS.md §2 B6 and §1 A1 (919a271)",
          "change": "V2-007 (919a271): CAPABILITY_VERSION; EXECUTION_DIGEST = the 2.0 source digest (the bytes that run); "
                    "DIGEST = sha256(json([PROBE_ID, CAPABILITY_VERSION, CLASSES])), what a spec binds. A1 (919a271): every "
                    "launch carries -S (-I does not disable site: a .pth written by test code ran inside a probe)",
          "owner_approval": V2_007 + "; A1 (-S): " + _engineering("docs/v2.1/ADR-V2.1.md ADR-1, a security fix"),
          "requirement": "RFC §5.1, §8, §35 (amended V2-007): a spec binds the probe's capability; §23: the RunSpec binds each "
                         "probe's executed bytes; -S: ADR-1 (no RFC clause)",
          "behaviour_tests": ("tests.v2.test_v21_identity.ThreeIdentities.test_a_spec_binds_the_capability_and_the_bytes_are_their_own_digest",
                              "tests.v2.test_v21_identity.ThreeIdentities.test_the_runspec_binds_each_probe_s_bytes",
                              "tests.v2.test_v21_identity_bytes.PthChannel.test_every_active_probe_launch_carries_minus_S",
                              "tests.v2.test_v21_identity.ThreeIdentities.test_every_active_probe_launch_starts_minus_I_minus_S_minus_B",
                              "tests.v2.test_v21_identity.PthChannel.test_a_probe_on_an_interpreter_holding_a_pth_never_runs_it")}
_TEST_15B = "tests.v2.test_c2_orchestration_conformance.Record.test_15b_only_the_release_s_named_changes_are_accepted_each_while_its_gate_holds"
#: why each file 2.1 changed changed — the part of a row a person states; everything else in a row is derived
ROWS = {
    "aisef2/orchestrate/adapters.py": {
        **_REVIEW, "change": "Finding.detail (default ''): what a finding states, journaled on its gate row; it never decides "
                             "(Finding.blocks is still blocking and corroborated)",
        "behaviour_tests": ("tests.v2.test_p6_stages.Adapters.test_a_finding_blocks_only_when_blocking_and_corroborated",
                            "tests.v2.test_v21_review.ProductPath.test_without_a_review_policy_the_same_review_is_advisory_as_in_2_0_0",
                            "tests.v2.test_v21_review_chain.FixLoop.test_a_correct_anchored_finding_is_fixed_before_the_merge")},
    "aisef2/orchestrate/review.py": {
        **_REVIEW, "change": "a finding's gate row detail is 2.0's text followed by ' — <the finding's detail>' when it has one; "
                             "the row's pass/fail and the REVIEW_FINDING failure are 2.0's",
        "behaviour_tests": ("tests.v2.test_p6_stages.Review.test_no_finding_is_one_passing_row_and_an_advisory_finding_alone_never_blocks",
                            "tests.v2.test_v21_review.ProductPath.test_fix_loop_does_not_block_a_confirmed_finding_its_clause_does_not_anchor",
                            "tests.v2.test_v21_review_chain.FixLoop.test_a_correct_anchored_finding_is_fixed_before_the_merge",
                            "tests.v2.test_v21_review_chain.FixLoop.test_the_fix_rounds_spent_with_the_defect_left_roll_back")},
    "aisef2/orchestrate/story_runner.py": {
        "change": "V21-38 (91a8968): every PRESERVE obligation of a committed story the change could affect "
                  "(merge.affected_preserve) is proved at the CANDIDATE: CONTRACT_UNSATISFIED, DEVELOPER, retryable, never "
                  "merged; the post-merge re-proof stays, for what the merge itself changes (INTEGRATION). A8 (51c5241, "
                  "4ea4276): a candidate diff git cannot produce is RESOURCE_ACQUISITION_FAILED (ENVIRONMENT) on the "
                  "'candidate' gate row. A1 (919a271): StoryInputs.test_interpreter — the developer's tests run on their own "
                  "interpreter, never the probes'",
        "backlog": "docs/v2.1/STATUS.md §2 B1 (V21-38, 91a8968); §1 A8 (51c5241, 4ea4276); §1 A1 (919a271)",
        "owner_approval": _engineering("docs/v2.1/ADR-V2.1.md ADR-4 for V21-38, ADR-1 for A1; STATUS §1 A8"),
        "requirement": "RFC §10.3: CANDIDATE x UNSATISFIED, any admitted role — owner DEVELOPER; §22.1: CONTRACT_UNSATISFIED "
                       "DEVELOPER RETRYABLE; §26: the post-merge re-proof of prior PRESERVE obligations (INTEGRATION) kept; "
                       "§17.1: RESOURCE_ACQUISITION_FAILED (ENVIRONMENT, retryable)",
        "behaviour_tests": (
            "tests.v2.test_v21_orchestration.PreserveAtCandidate.test_a_regression_the_developer_made_is_the_developer_s_and_never_merged",
            "tests.v2.test_v21_orchestration.PreserveAtCandidate.test_a_retry_that_repairs_it_commits",
            "tests.v2.test_v21_orchestration.PreserveAtCandidate.test_a_story_with_no_committed_predecessor_proves_only_its_own",
            "tests.v2.test_c2_orchestration_conformance.ReproofOfAnotherKind."
            "test_a_regression_of_the_prior_spec_of_another_kind_is_the_developer_s_at_the_candidate_and_never_merged",
            "tests.v2.test_p6_orchestration.Orchestration."
            "test_ORCH_9_and_10_a_post_merge_regression_of_a_prior_PRESERVE_obligation_is_INTEGRATION_and_rolled_back",
            "tests.v2.test_v21_orchestration.DiffFailure.test_a_diff_git_cannot_produce_is_RESOURCE_ACQUISITION_FAILED",
            "tests.v2.test_v21_orchestration.DiffFailure.test_a_retry_budget_takes_the_story_to_its_next_attempt",
            "tests.v2.test_v21_identity_bytes.PthChannel.test_the_run_gives_the_probes_this_interpreter_and_the_tests_their_own")},
    "aisef2/orchestrate/workspace.py": {
        "change": "GitWorkspace.diff: git exiting non-zero raises ResourceUnavailable (2.0: InvariantError, which ended the run "
                  "as a kernel defect)",
        "backlog": "docs/v2.1/STATUS.md §1 A8 (51c5241)", "owner_approval": _engineering("docs/v2.1/STATUS.md §1 A8"),
        "requirement": "RFC §17.1: a resource the scope could not acquire is RESOURCE_ACQUISITION_FAILED (ENVIRONMENT, "
                       "retryable), from the typed outcome; §22.1",
        "behaviour_tests": ("tests.v2.test_p6_stages.Workspace.test_checkouts_are_detached_worktrees_at_a_full_sha_moved_and_released_through_git",
                            "tests.v2.test_v21_orchestration.DiffFailure.test_a_diff_git_cannot_produce_is_RESOURCE_ACQUISITION_FAILED")},
    "aisef2/probe/calibration.py": {
        "change": "executing(probe): a ProbeCapabilityCalibration binds the digest of the bytes that ran (EXECUTION_DIGEST); "
                  "calibration_for matches on it, so a byte change admits nothing until it is calibrated again",
        "backlog": "docs/v2.1/STATUS.md §2 B6 (919a271)", "owner_approval": V2_007,
        "requirement": "RFC §9.1.1 (amended V2-007): ProbeCapabilityCalibration.probe_digest is the bytes that ran; §12 check 9",
        "behaviour_tests": ("tests.v2.test_v21_identity_bytes.ThreeIdentities.test_calibrations_of_other_bytes_admit_nothing",
                            "tests.v2.test_v21_identity.ThreeIdentities.test_calibrations_bound_to_the_bytes_that_run_admit_and_other_bytes_admit_nothing",
                            "tests.v2.test_v21_identity_bytes.ThreeIdentities.test_the_shipped_calibrations_name_every_class_at_the_bytes_that_run_now",
                            "tests.v2.test_v21_identity.ThreeIdentities.test_the_cycle1_probe_keeps_its_one_frozen_digest")},
    "aisef2/probe/cli_invocation.py": _PROBE,
    "aisef2/probe/file_artifact.py": {
        "change": "V2-007 (919a271): DIGEST is the capability digest, EXECUTION_DIGEST the bytes. V21-37 (06d4e62): the class "
                  "python_imports (imports counted by syntax, never by a line regex), CAPABILITY_VERSION 2",
        "backlog": "docs/v2.1/STATUS.md §2 B6 (919a271); §2 B3, V21-37 (06d4e62)",
        "owner_approval": V2_007 + "; V21-37: NOT owner-approved — " + _engineering("docs/v2.1/ADR-V2.1.md ADR-5")
                          + "; the revised LedgerLock contract that would use python_imports is an unapproved draft (STATUS §2 B3)",
        "requirement": "RFC §8 and §35 (amended V2-007): a spec binds the probe's capability, a new observation class is a new "
                       "capability version; §9.1.1",
        "behaviour_tests": ("tests.v2.test_v21_identity.ThreeIdentities.test_a_spec_binds_the_capability_and_the_bytes_are_their_own_digest",
                            "tests.v2.test_v21_python_imports.Controls.test_the_approved_regex_reproduces_the_false_rollback",
                            "tests.v2.test_v21_python_imports.Controls.test_each_draft_holds_on_the_smoke2_shape_and_refutes_a_real_import",
                            "tests.v2.test_v21_python_imports.Controls.test_a_file_that_does_not_parse_is_no_count",
                            "tests.v2.test_v21_python_imports.Controls.test_the_grammar_is_closed")},
    "aisef2/probe/process_effect.py": _PROBE,
    "aisef2/probe/python_callable_v2.py": _PROBE,
    "tests/v2/test_c2_orchestration_conformance.py": {
        "change": "91a8968: ReproofOfAnotherKind's regression case re-aimed to V21-38 (the developer's at the candidate, never "
                  "merged), each assertion kept. B-03d: test_15 names this ruling; test_15b accepts a 2.1 change only as this "
                  "ruling names it, by content, and gates (e) on B-03a's history and re-verification",
        "backlog": "docs/v2.1/STATUS.md §2 B1 (V21-38, 91a8968); owner B-03d",
        "owner_approval": "V21-38: " + _engineering("docs/v2.1/ADR-V2.1.md ADR-4") + "; test_15/test_15b: owner B-03d "
                          "(RELEASE-DECISIONS seq 5), this ruling",
        "requirement": "RFC §10.3 and §26 (as story_runner.py); the owner's B-03d text: every changed expectation traced to an "
                       "approved requirement or decision and to behaviour evidence, none changed only to pass",
        "behaviour_tests": ("tests.v2.test_c2_orchestration_conformance.ReproofOfAnotherKind."
                            "test_a_regression_of_the_prior_spec_of_another_kind_is_the_developer_s_at_the_candidate_and_never_merged",
                            _TEST_15B)},
    "validation/qualification/c2_orchestration_repair.py": {
        "change": "B-03d: release_differences accepts a 2.1 change only as this ruling names it, by content, and gates (e) on "
                  "p5_acceptance.history_problems and reverification_problems (B-03a) instead of p5_acceptance.check; write() and "
                  "the (b) job refuse before measuring once q5.CORPUS lacks a Cycle-1 item (cycle1_items_refusal): the "
                  "record is cycle-2 history",
        "backlog": "owner B-03d and B-03a (RELEASE-DECISIONS seq 5)",
        "owner_approval": "owner B-03d (this ruling); B-03a (no engine-digest tolerance, no rebind mapping hiding unverified "
                          "behaviour) sets the (e) gate",
        "requirement": "the owner's B-03d text (2.0's corpus, rulings and evidence kept; every changed expectation traced) and "
                       "B-03a's",
        "behaviour_tests": (_TEST_15B,
                            "tests.v2.test_v21_conformance_ruling.CycleTwoRecord.test_write_refuses_before_measuring_on_2_1",
                            "tests.v2.test_v21_conformance_ruling.CycleTwoRecord.test_the_b_job_refuses_before_executing_an_item")},
    "validation/v2/mutation.py": {
        "change": "the V2.1 phase (record closure-evidence/v2/v2.1/MUTATION.json, last in RECORDS): the 320 stale targets and the "
                  "2.1 modules' names, taken over through SUPERSEDED; the earlier phases' records stay history",
        "backlog": "owner B-03b (55a6b74, e97ea41; the merge 880881f adds bundle_cli::_create)",
        "owner_approval": "owner B-03b (RELEASE-DECISIONS seq 5): a new mutation phase through RECORDS/SUPERSEDED",
        "requirement": "the owner's B-03b text; (f) is accepted only while validation/v2/mutation.py check() == []",
        "behaviour_tests": ("tests.v2.test_v21_mutation_record.Phase.test_the_phase_takes_over_every_stale_module_target_and_s2_stays_whole",
                            "tests.v2.test_v21_mutation_record.Account."
                            "test_every_v21_target_is_accounted_for_exactly_once_and_a_survivor_never_passes",
                            _TEST_15B)},
}
#: why each identity that moved from the record moved
IDENTITY_WHY = {
    "catalog": "the catalog's probe digests are the probes' capability digests (V2-007, 919a271); file_artifact's capability "
               "version is 2 (V21-37, 06d4e62)",
    "catalog_matches_the_brief": "the cycle-2 brief names the 2.0 source digests (c2_orchestration_repair.BRIEFED_DIGEST_PREFIXES)",
    "contract_spec_semantic_digest": "a spec's id and semantic hash bind its probe's digest (aisef2/product/spec.py), so each of "
                                     "the 59 moves with the catalog; contract ids and contract hashes do not",
    "plan_hash": "the plan's hash is over the spec ids",
    "plan_ok": "plan_ok requires the accepted plan hash (c2_orchestration_repair.PLAN_HASH)",
    "probe_sources_vs_6311254": "the probe sources 2.1 changed (rows of this ruling) beside the V2.0 release's B1 changes",
    "probe_sources_identical_to_6311254": "as probe_sources_vs_6311254",
}


def _lf(rel: str) -> str | None:
    p = ROOT / rel
    return rp._lf(p.read_bytes()) if p.is_file() else None


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, encoding="utf-8", check=True).stdout.strip()


def tolerated() -> dict[str, str]:
    """What release_differences may accept by this ruling: each row's path -> its sha256_2_1, read from the COMMITTED
    ruling only (the file is HEAD's blob); {} when there is none, or the file is not committed as it is."""
    p = ROOT / OUT_REL
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{OUT_REL}"], capture_output=True)
    if r.returncode != 0 or not p.is_file() or rp._lf(r.stdout) != rp._lf(p.read_bytes()):
        return {}
    return {row["path"]: row["sha256_2_1"] for row in json.loads(p.read_text(encoding="utf-8"))["conformance"]["rows"]}


def missing_tests(ids) -> list[str]:
    """The ids (module.Class.method) with no such method defined in that class of that file."""
    out = []
    for t in ids:
        *mod, cls, meth = t.split(".")
        f = ROOT.joinpath(*mod).with_suffix(".py") if mod else None
        body = ast.parse(f.read_text(encoding="utf-8")).body if f and f.is_file() else []
        c = next((n for n in body if isinstance(n, ast.ClassDef) and n.name == cls), None)
        if c is None or not any(isinstance(n, ast.FunctionDef) and n.name == meth for n in c.body):
            out.append(t)
    return out


def v2_0_list() -> dict[str, str]:
    """release_differences' V2.0 list (`changed`): path -> the V2.0 release's label, read from its source."""
    tree = ast.parse((ROOT / "validation/qualification/c2_orchestration_repair.py").read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "release_differences")
    return next(ast.literal_eval(n.value) for n in ast.walk(fn)
                if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "changed")


def changed_files(found: list[str]) -> list[str]:
    """The files `check`'s (d) findings name that 2.1 changed: their LF sha256 now is not their sha256 at v2.0.0."""
    named = {x.split(" ", 2)[1] for x in found if x.split(" ", 2)[0] == "(d)" and x.split(" ", 2)[2] in D_FINDINGS}
    return sorted(p for p in named if _lf(p) != rebind.lf_sha_at(V2_0_0, p))


def derive() -> tuple[dict, list[str]]:
    """The ruling this tree gives, and its problems ([] = it can be written)."""
    from validation.qualification import p5_falsifiability as pf
    from validation.qualification import q5
    from validation.qualification import release_calibration as rc
    problems: list[str] = []
    entry = next((e for e in json.loads((ROOT / pa.DECISIONS_REL).read_text(encoding="utf-8"))["entries"]
                  if e.get("id") == pa.B03_ID), {})
    quoted = all(t in entry.get("owner_text", "") for t in (B03D_TEXT, NO_WEAKENING))
    if not (quoted and entry.get("seq") == B03D_REF["seq"] and "B-03d" in entry.get("decision", {})):
        problems.append(f"the B-03d text is not verbatim in {pa.DECISIONS_REL} entry {pa.B03_ID} (seq {B03D_REF['seq']})")
    hist = json.loads((ROOT / rp.OUT_REL).read_text(encoding="utf-8"))
    now = rp.identities()
    found = rp.check(now)
    v20 = v2_0_list()
    paths = changed_files(found)
    problems += [f"{p}: 2.1 changed it and the cycle-2 record reports it, but ROWS states no reason" for p in paths if p not in ROWS]
    problems += [f"{p}: in ROWS, but not a file 2.1 changed that the cycle-2 record reports" for p in sorted(set(ROWS) - set(paths))]
    rows = []
    for p in paths:
        stated = ROWS.get(p, {})
        log = _git("log", "--format=%H%x09%s", f"{SINCE}..HEAD", "--", p)
        rows.append({"path": p, "sha256_v2_0_0": rebind.lf_sha_at(V2_0_0, p), "sha256_2_1": _lf(p),
                     "commits_2_1": [dict(zip(("commit", "subject"), ln.split("\t", 1), strict=True)) for ln in log.splitlines()],
                     "v2_0_list": v20.get(p), **{k: stated.get(k) for k in ("change", "backlog", "owner_approval", "requirement")},
                     "behaviour_tests": list(stated.get("behaviour_tests", ()))})
        if p in ROWS and not stated.get("behaviour_tests"):
            problems.append(f"{p}: no behaviour test")
        problems += [f"{p}: behaviour test {t} does not exist" for t in missing_tests(stated.get("behaviour_tests", ()))]
    moved = sorted(k for k in rp.SEMANTIC_IDENTITIES if now.get(k) != hist["identities"].get(k))
    problems += [f"identity {k} moved from the record without a stated reason" for k in moved if k not in IDENTITY_WHY]
    sources = {}
    for rel in sorted(r for r, x in now["probe_sources_vs_6311254"].items() if x != hist["identities"]["probe_sources_vs_6311254"].get(r)):
        sources[rel] = "a row of this ruling" if rel in paths else f"the V2.0 list ({v20[rel]})" if rel in v20 else None
        if sources[rel] is None:
            problems.append(f"probe source {rel} moved from the record and neither a row nor the V2.0 list names it")
    corpus = [i.id for i in q5.CORPUS]
    for item, c in X.CHANGES.items():
        problems += [f"q5: {item} is not in q5.CORPUS"] if item not in corpus else []
        problems += [f"q5: {c['replaces']} is still in q5.CORPUS"] if c.get("replaces") in corpus else []
        problems += [f"q5: {item}: behaviour test {t} does not exist" for t in missing_tests(c["behaviour_tests"])]
    mu = rp._load("aisef_v2_mutation", "validation/v2/mutation.py")
    if "V2.1" not in mu.RECORDS:
        problems.append("validation/v2/mutation.py has no phase V2.1")
    refusal = rp.cycle1_items_refusal()
    blob = rebind.lf_sha_at(V2_0_0, rp.OUT_REL) == _lf(rp.OUT_REL)
    problems += [] if refusal else ["c2_orchestration_repair --write would measure on this tree (q5.CORPUS has every Cycle-1 item)"]
    problems += [] if blob else [f"{rp.OUT_REL} is not its v2.0.0 blob: a cycle-2 record was rewritten"]
    rec = {
        "record": "AISEF V2.1 — CONFORMANCE RULING (B-03d): 2.1's behaviour changes against the historical "
                  "C2-ORCHESTRATION-CONFORMANCE-REPAIR record",
        "id": "AISEF-V2.1-CONFORMANCE-RULING",
        "authority": {"decision": {**B03D_REF, "approver": entry.get("approver"), "decision": (entry.get("decision") or {}).get("B-03d")},
                      "owner_text": [B03D_TEXT, NO_WEAKENING], "quoted_verbatim": quoted,
                      "not_authorized_by_the_decision": entry.get("not_authorized_by_this_entry")},
        "recorded_by": "engineering: written by validation/qualification/v21_conformance_ruling.py --write from this tree and the "
                       "per-file reasons stated in it; the owner authorized a ruling (B-03d) and did not write or sign this file",
        "historical_record": rp.OUT_REL,
        "conformance": {
            "rule": "one row per file c2_orchestration_repair.check reports under (d) that 2.1 changed (its LF sha256 at v2.0.0 "
                    f"{V2_0_0} is not its sha256 now). release_differences accepts such a (d) finding when the file is in "
                    "its V2.0 list (by path, as in 2.0: v2_0_list) or this committed ruling names it AND the file's LF sha256 "
                    "is the row's sha256_2_1; --check binds every row, V2.0-listed or not, to its bytes; no ruling, nothing "
                    "new is accepted",
            "since": SINCE, "v2_0_0": V2_0_0, "rows": rows},
        "identity": {
            "moved_from_the_record": {k: IDENTITY_WHY.get(k) for k in moved},
            "unmoved": [k for k in rp.SEMANTIC_IDENTITIES if k not in moved],
            "values": {k: {"record": hist["identities"].get(k), "now": now.get(k)} for k in ("catalog", "plan_hash")},
            "probe_sources_moved_from_the_record": sources,
            "authority": {"V2-007": {**B01_REF, "decision": "ARCHITECTURE-EXCEPTION-V2-007 APPROVED"},
                          "V21-37": "file_artifact CAPABILITY_VERSION 2 — an engineering change, NOT owner-approved"},
            "all_equal_to_accepted": "unmoved because p5_acceptance.verify compares the 59 specs through rebind.spec_subst (the "
                                     "V2.0 B1 probe-identity re-binding): an identity mapping, NOT behaviour evidence",
            "behaviour_evidence": {"p5_falsifiability": pf.V21_OUT_REL, "c2_p5_reverification": pa.V21_OUT_REL,
                                   "probe_calibrations": rc.RECORD_REL,
                                   "rule": "every retained spec re-executed under this tree's probes (pristine and witness), "
                                           "compared literally inside B-03a's re-verification; the shipped calibrations at the "
                                           "bytes that run (admission check 9)"},
            "engine_digest": "NOT tolerated here: no rule accepts the static admission engine digest (a33f2aee… -> this tree's); "
                             "the (e) gate is p5_acceptance.history_problems() == [] and reverification_problems() == [] "
                             "(B-03a: the 2.0 acceptance is its v2.0.0 blob, the boundary re-verified literally on 2.1), "
                             "never p5_acceptance.check",
            "rule": "(e) is accepted only while every moved identity is in release_differences' probe_moved, every moved probe "
                    "source is in the V2.0 list or a row of this ruling at its sha256_2_1, and the (e) gate holds"},
        "q5": {"data": "validation/qualification/v21_q5_changes.py", "corpus_2_1": corpus,
               "comparison_record": X.COMPARISON_REL, "comparison_check": "validation/qualification/v21_q5_compare.py --check",
               "changes": json.loads(json.dumps(X.CHANGES)), "unchanged": json.loads(json.dumps(X.UNCHANGED)),
               "rule": "each changed expectation names its cause commit, the requirement, the decision and its behaviour "
                       "tests; 2.0's corpora (closure-evidence/v2/Q5, cycle2/Q5, cycle2/Q5-FINAL, release/Q5-RC1, "
                       "release/Q5-RC2) stay as recorded"},
        "mutation": {"authority": {**pa.B03_REF, "part": "B-03b"}, "phase": "V2.1", "record": mu.RECORDS.get("V2.1"),
                     "rule": "(f) the record's mutation summary is cycle 2's (C2-ORCH, K-PRESAT-001, K-NOWORK-001); "
                             "release_differences accepts (f) only while validation/v2/mutation.py check() == [] — every "
                             "phase's record holds on this tree, V2.1's included"},
        "history": {"record": rp.OUT_REL, "sha256": _lf(rp.OUT_REL), "is_its_v2_0_0_blob": blob,
                    "statement": "(a) defect_reproducer, (b) single_probe_equivalence and (c) test_matrix are cycle-2 "
                                 "executions, kept as recorded and never re-measured on 2.1: (b) measured the seven Cycle-1 items, "
                                 "post-merge-regression among them, which 2.1 replaced (V21-38: q5 above); (c) names "
                                 "ReproofOfAnotherKind's 2.0 case, re-aimed by 91a8968",
                    "c2_orchestration_repair_write": refusal},
        "unchanged": [f"{rp.OUT_REL}: byte-identical, its v2.0.0 blob",
                      "2.0's Q5 corpora and every 2.0 and cycle-2 record and ruling",
                      "release_differences' V2.0 list and the (f) gate (mutation.check() == [])",
                      "SEMANTIC_IDENTITIES and probe_moved: an identity outside probe_moved is never accepted"],
        "not_done": ["no 2.0 or cycle-2 record, corpus or ruling is rewritten",
                     "no engine-digest tolerance; no probe-identity re-binding in the (e) gate",
                     "c2_orchestration_repair.py --write never runs on 2.1: it refuses before measuring",
                     "no owner approval is claimed for a change beyond what its row states",
                     "no new owner acceptance of the C2-P5 boundary"],
        "written_at": {"head": _git("rev-parse", "HEAD")},
    }
    return rec, problems


def refused(out: pathlib.Path) -> str | None:
    from validation.qualification import q5
    p = out.resolve()
    if q5.within(p, ROOT) and not q5.within(p, ROOT / V21_DIR):
        return f"{p} is in the repository outside {V21_DIR} (2.0's and cycle 2's records are never written)"
    return f"{p} exists (a record is written once)" if p.exists() else None


def dirty() -> list[str]:
    return [ln for ln in _git("status", "--porcelain", "--", *DEPENDS).splitlines() if ln.strip()]


def write(out: pathlib.Path) -> int:
    why = refused(out)
    if not why and (lines := dirty()):
        why = f"{' '.join(DEPENDS)} not committed ({lines[:5]}): write from a committed tree"
    rec, problems = (None, []) if why else derive()
    why = why or "; ".join(problems)
    if not why:
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            with out.open("x", encoding="utf-8", newline="\n") as f:
                f.write(C.render(rec))
        except FileExistsError:
            why = f"{out} exists (a record is written once)"
    if why:
        print(f"REFUSED: {why}")
        return 2
    print(f"{out}: {len(rec['conformance']['rows'])} rows")
    return 0


def check(path: pathlib.Path | None = None) -> list[str]:
    path = path or ROOT / OUT_REL
    if not path.is_file():
        return [f"{path}: no ruling (v21_conformance_ruling.py --write)"]
    rec = json.loads(path.read_text(encoding="utf-8"))
    now, out = derive()
    have = {r.get("path"): r for r in (rec.get("conformance") or {}).get("rows") or []}
    want = {r["path"]: r for r in now["conformance"]["rows"]}
    out += [f"row {p}: missing — 2.1 changed it and the cycle-2 record reports it" for p in sorted(set(want) - set(have))]
    out += [f"row {p}: extra — not a file 2.1 changed that the cycle-2 record reports" for p in sorted(set(have) - set(want))]
    out += [f"row {p}: {k} is {have[p].get(k)!r:.90}, this tree derives {want[p].get(k)!r:.90}"
            for p in sorted(set(want) & set(have)) for k in sorted(set(want[p]) | set(have[p])) if have[p].get(k) != want[p].get(k)]

    def rest(d: dict) -> dict:   # everything but the rows (compared above) and when it was written
        return {k: ({**v, "rows": None} if k == "conformance" and isinstance(v, dict) else v) for k, v in d.items() if k != "written_at"}
    return out + [f"stale: {p}" for p in rebind.paths(rest(rec), rest(now))]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    ap.add_argument("--out", default=OUT_REL)
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out) if os.path.isabs(a.out) else ROOT / a.out
    if a.write:
        return write(out)
    problems = check(out)
    for p in problems:
        print(f"  {p}")
    print(f"CONFORMANCE-RULING {'PASS' if not problems else 'FAIL'}: {out}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
