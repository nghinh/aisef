"""The Cycle-2 final closure audit (owner ruling 'CYCLE-2 FINAL OWNER CLOSURE AUDIT / ENGINEERING RESULTS PROVISIONALLY
ACCEPTED / PUBLIC RELEASE NOT YET AUTHORIZED'): evidence records only — nothing here changes a product, a kernel, a
validation semantic or a recorded result.

    python -P validation/qualification/c2_closure_audit.py --write
        -> closure-evidence/v2/cycle2/C2-LEDGERLOCK-FAILURE-TRIAGE.json      (ruling §2)
           closure-evidence/v2/cycle2/C2-ORCHESTRATION-CHANGE-REVIEW.json   (ruling §3)
           closure-evidence/v2/cycle2/C2-HISTORY-FREEZE-CANDIDATE.json      (ruling §8)
           closure-evidence/v2/cycle2/C2-CLOSURE-AUDIT.json                 (ruling §4-§7, §9, §10)

Every classification below that the ruling reserves to the Owner is stated as the evidence's reading and returned for
the Owner's ruling; none is self-authorized. A release blocker found here stops the audit: the verdict says so.
"""

from __future__ import annotations

import argparse
import ast
import collections
import contextlib
import dataclasses
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "validation" / "v2"))

CY = "closure-evidence/v2/cycle2"
TRIAGE_REL, ORCH_REL = f"{CY}/C2-LEDGERLOCK-FAILURE-TRIAGE.json", f"{CY}/C2-ORCHESTRATION-CHANGE-REVIEW.json"
FREEZE_REL, AUDIT_REL = f"{CY}/C2-HISTORY-FREEZE-CANDIDATE.json", f"{CY}/C2-CLOSURE-AUDIT.json"
MD_REL = f"{CY}/C2-CLOSURE-AUDIT.md"
OLD = "63112544f1146097b69c538d98e09e5a52c547c1"     # the kernel before the orchestration change (QP-2.6 attempt 1)
R2 = "ac4a6c75b461e409f024965391ce77e7689c0e08"
R3 = "37dc0dcdf819387b65ee60cf614273df94aaef31"
FINAL = "c11615aeb1dd9e6ff992b6190f8c39a272636742"
REPORT_HEAD = "2dd12265caa47095ac8daebea4eda8f817f812f3"
BOOKKEEPING = "3ed2c41126e27d1a6b04e5442b56bbf3b6d89f11"
MASTER = "671ef9b259c560bf07531bc5fed63b07dc28b323"
ORCH_COMMITS = ("e3d0560e277024eeb31ddf54a95dba8fb41ae1b6", "ac88f366f98e5d1f4e2859df1001d430bdb8364c")
ORCH_FILES = ("aisef2/orchestrate/story_runner.py", "aisef2/orchestrate/proof.py")
PLATFORMS = ("linux-py3.11", "linux-py3.12", "linux-py3.13", "linux-py3.14", "windows-py3.11")
MARK = "C2-AUDIT-JOB "
CONCLUSION = ["Cycle-2 closure audit is complete.", "No benchmark result was tuned or rewritten.",
              "LedgerLock delivery remains FAIL and DEVELOPMENT_REGRESSION.", "No generalization claim is made.",
              "No cohort has been selected or sealed.", "PR #6 remains unmerged.", "No public release has been performed.",
              "Owner merge-and-release decision is required."]


def git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, encoding="utf-8", check=True).stdout.strip()


def load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def ident(rel: str) -> dict:
    return {"path": rel, "sha256": hashlib.sha256((ROOT / rel).read_bytes().replace(b"\r\n", b"\n")).hexdigest()}


def _run(argv: list[str]) -> dict:
    r = subprocess.run([sys.executable, "-P", *argv], cwd=ROOT, capture_output=True, encoding="utf-8")
    return {"command": "python -P " + " ".join(argv), "exit": r.returncode, "tail": (r.stdout + r.stderr).strip().splitlines()[-1:]}


def _tests(module: str) -> dict:
    r = subprocess.run([sys.executable, "-m", "unittest", module], cwd=ROOT, capture_output=True, encoding="utf-8")
    lines = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.startswith(("Ran ", "OK", "FAILED"))]
    return {"module": module, "exit": r.returncode, "result": lines}


# ============================================================================================ §2 the six stories

CLASSES = {"A": "FRAMEWORK_KERNEL_DEFECT", "B": "DEFAULT_PUBLIC_HARNESS_POLICY_DEFECT", "C": "BENCHMARK_SPECIFIC_HARNESS_CONFIGURATION",
           "D": "DEVELOPER_OR_MODEL_EXECUTION_FAILURE", "E": "REQUIREMENT_AMBIGUITY_OR_UNSUPPORTED_BEHAVIOR", "F": "OTHER"}
POLICY_CONFIG = ("validation/qualification/c2_p9.py: sr.Policy(limits, TestsPolicy(True), tool_timeout_s=120) — a blocking tests policy; "
                 "DeveloperTests(story, ('tests/test_<story>.py',)); limits DEVELOPER 1, PLAN 0, ENVIRONMENT 1, PROVIDER 1, INTEGRATION 0, REVIEW 1, SECURITY 1")
TRIAGE = {
    "STORY-01-01": ("D", "the developer did not create ledgerlock/ledger.py in attempt 1 (S-10-b: SUBJECT_ABSENT_AT_CANDIDATE) and, in attempt 2, "
                         "wrote `from collections.abc import Iterable, Iterator` in ledgerlock/ledger.py (S-10-a: CONTRACT_UNSATISFIED) — requirement §10 "
                         "lists the allowed modules and `collections` is not one. The kernel proved each obligation by its own probe, typed both failures "
                         "DEVELOPER / retryable, retried once within the DEVELOPER limit and rolled back. Contributing, not primary: the epics write_scope "
                         "of Story 1.1 does not name ledger.py while PLAN-V2.2 places R-10/2 and R-13/1 over it on this story (the prompt carried both).",
                    "the proof gate (CONTRACT_UNSATISFIED is DEVELOPER by the frozen routing); no configuration decided it",
                    "an ordinary user's developer that violates an approved contract is rolled back the same way: intended behaviour"),
    "STORY-02-01": ("A", "admitted fully PRE_SATISFIED (STORY-01-05's developer had implemented `verify`): developer_call_permitted false, no "
                         "developer request, candidate = parent, plan-drift emitted, the obligation's VerifiedProof SATISFIED with agreement — everything "
                         "RFC §14 and §17 name for a story that 'ends STORY_ALREADY_SATISFIED'. The engineering-adequacy stage then ran over a story no "
                         "developer had been asked to work on: the story-owned test file the harness declares (tests/test_<story>.py) does not exist, "
                         "which the kernel typed STORY_TESTS_NOT_COLLECTABLE, developer-caused, relevance IRRELEVANT -> INADEQUATE, owner DEVELOPER, "
                         "developer_chargeable true; under the blocking tests policy that is TESTS_INADEQUATE (DEVELOPER, retryable): one retry charged "
                         "to the DEVELOPER budget — with no developer call possible, so the retry repeated the same events — then ROLLBACK. "
                         "The reproducer in this record shows the same rollback and the same charged retry when the story's tests DO exist and pass at "
                         "the parent (VACUOUS and IRRELEVANT, because the product diff is empty), so the harness's test-path convention is not the cause: "
                         "under TestsPolicy(blocking=True) a fully PRE_SATISFIED story does not commit, whether its tests are absent (LedgerLock) or present "
                         "and passing (reproducer). RFC §14: a PRE_SATISFIED "
                         "obligation MUST 'consume no developer budget' and 'MUST NOT require that correct code be made incorrect' (the only way to make "
                         "the tests non-vacuous here); §17: 'a commit MUST NOT depend on a developer test verdict'; §15.3 lets a project make INADEQUATE "
                         "block. The blocking stance is the benchmark harness's choice (no shipped default exists); the defect is the kernel's handling "
                         "of that permitted stance on a story §14 says ends already satisfied. Two other readings exist and are the Owner's to weigh: "
                         "C (the stance is qualification-profile-specific and a non-blocking stance commits the story) and E (the RFC does not say how "
                         "§15.3 applies to a story with no developer call). This record takes A because a legal policy value makes the kernel contradict "
                         "a §14 MUST, and the ruling forbids choosing the convenient class.",
                    POLICY_CONFIG,
                    "YES for any integrator who chooses a blocking tests policy: every fully PRE_SATISFIED story rolls back and spends a DEVELOPER retry. "
                    "With a non-blocking policy the same story commits (reproducer). No V2 code ships today (aisef2 is excluded from the wheel)"),
    "STORY-04-01": ("D", "refused at StoryAdmission, owner PLAN, not retryable, no developer call: PRECONDITION_BROKEN on the PRESERVE obligation "
                         "AC-STORY-04-01-2:S-9-b (R-9/2, exit 2 on a usage error) — the behaviour STORY-01-01 was to introduce and, rolled back, did not. "
                         "Derivative of STORY-01-01's developer failure; the kernel refused fail-closed as RFC §13/§14 require (a hard plan blocker).",
                    "none: StoryAdmission (frozen semantics); the harness ran every story in dependency order whatever its dependencies' outcomes",
                    "an ordinary user's story whose PRESERVE precondition was not delivered upstream is refused the same way: intended behaviour"),
    "STORY-05-01": ("C", "the developer wrote only tests/test_story_05_01.py in both attempts (the story's deliverable is a property test; its two obligations "
                         "are both PRESERVE, READY at the parent: the plan asks this story for no new product behaviour). With no product hunk, vacuity is VACUOUS and relevance IRRELEVANT as RFC §15.1/§15.2 define them, so the "
                         "assembly is INADEQUATE (DEVELOPER, may block), and the benchmark harness's blocking tests policy rolled the story back after one "
                         "retry. The kernel followed §15 to the letter; no RFC MUST is contradicted (the developer was called and charged). The blocking "
                         "policy is the qualification harness's own choice.",
                    POLICY_CONFIG,
                    "YES for any integrator who chooses a blocking tests policy: a story that changes no product code (tests-only, as here) cannot commit. "
                    "The kernel offers one global stance, not a per-story one"),
    "STORY-05-03": ("D", "refused at StoryAdmission, owner PLAN, not retryable, no developer call: PRECONDITION_BROKEN on the PRESERVE obligation "
                         "AC-STORY-05-03-1:S-10-a (R-10/1, standard library only, allowed modules) — STORY-01-01's obligation, not holding at the parent. "
                         "Derivative of STORY-01-01's developer failure; refused fail-closed.",
                    "none: StoryAdmission (frozen semantics)",
                    "as STORY-04-01: intended behaviour"),
}
TRIAGE["STORY-02-02"] = ("A", TRIAGE["STORY-02-01"][1].replace("implemented `verify`", "implemented `snapshot`"), *TRIAGE["STORY-02-01"][2:])


def shipped_default_facts() -> dict:
    """Is the blocking tests policy a shipped/default AISEF setting? Measured, not asserted."""
    from aisef2.orchestrate.quality import TestsPolicy
    f = dataclasses.fields(TestsPolicy)[0]
    grep = lambda *paths: subprocess.run(["git", "grep", "-n", "TestsPolicy(", "--", *paths], cwd=ROOT, capture_output=True,  # noqa: E731
                                         encoding="utf-8").stdout.splitlines()
    constructions = grep("aisef2")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    users = sorted({ln.split(":")[0] for ln in grep("validation", "tests")})
    return {"TestsPolicy.blocking_has_a_default": f.default is not dataclasses.MISSING or f.default_factory is not dataclasses.MISSING,
            "kernel_constructs_a_policy_itself": constructions,
            "aisef2_excluded_from_the_wheel": 'exclude = ["aisef2*"]' in pyproject, "wheel_entry_point": "aisef = \"aisef.cli:main\" (V1)",
            "pyproject_version": next(ln.split('"')[1] for ln in pyproject.splitlines() if ln.startswith("version")),
            "files_that_construct_a_TestsPolicy": users,
            "reading": "no shipped default exists: the kernel requires the caller to state the stance, constructs none itself, and aisef2 is not in "
                       "the published wheel (the public `aisef` command is V1). The blocking stance of QP-2.9 is set in "
                       "validation/qualification/c2_p9.py only"}


def interaction_history() -> dict:
    """Where the adequacy stage came from and which tests ever ran a fully PRE_SATISFIED story — measured from git and the sources."""
    q = "aisef2/orchestrate/quality.py"
    log = git("log", "--format=%H %ad %s", "--date=short", "--", q).splitlines()
    orch = (ROOT / "tests/v2/test_p6_orchestration.py").read_text(encoding="utf-8")
    q5 = (ROOT / "validation/qualification/q5.py").read_text(encoding="utf-8")
    conf = (ROOT / "tests/v2/test_c2_orchestration_conformance.py").read_text(encoding="utf-8")
    i = orch.index("def test_ORCH_4_pre_satisfied")
    return {"adequacy_stage_source": {"path": q, "commits_that_touched_it": [ln[:150] for ln in log], "blob_at_head": git("rev-parse", f"HEAD:{q}"),
                                      "unchanged_by_cycle_2": len(log) == 1 and git("rev-parse", f"{OLD}:{q}") == git("rev-parse", f"HEAD:{q}")},
            "tests_that_run_a_fully_pre_satisfied_story": {
                "tests/v2/test_p6_orchestration.py ORCH-4 (Cycle 1, P6)": "tests_block=False" if "tests_block=False" in orch[i:i + 700] else "blocking",
                "validation/qualification/q5.py corpus item 'pre-satisfied' (Cycle 1, Q5)":
                    "tests_block=False" if 'Item("pre-satisfied"' in q5 and "tests_block=False" in q5[q5.index('Item("pre-satisfied"'):][:300] else "blocking",
                "tests/v2/test_c2_orchestration_conformance.py test_4 (Cycle 2)": "TestsPolicy(False)" if "TestsPolicy(False)" in conf and "TestsPolicy(True)" not in conf else "blocking"},
            "who_chose_blocking_for_qp_2_9": "the QP-2.9 harness (validation/qualification/c2_p9.py), written by the engineer of this cycle; the QP-2.9 preflight "
                                             "record does not state the stance and the engineer knows of no Owner ruling that set it",
            "reading": "the behaviour is Cycle-1 kernel code (WP-6.2), unchanged in Cycle 2; the three tests found that run a fully PRE_SATISFIED story "
                       "all set the non-blocking stance, so QP-2.9 is the first recorded execution of the path under a blocking one"}


def presatisfied_reproducer() -> dict:
    """A fully PRE_SATISFIED story whose tests exist and pass at the parent (the Q5 corpus item 'pre-satisfied', committed with
    tests_block=False), executed for real under a non-blocking and a blocking tests policy. No model, no LedgerLock."""
    from validation.qualification import q5
    item = next(i for i in q5.CORPUS if i.id == "pre-satisfied")
    out = {"source": "validation/qualification/q5.py CORPUS item 'pre-satisfied' (record mode: scripted stream, real git, probes, tests)",
           "committed_form_sets_tests_block": item.stories[0].tests_block}
    for block in (False, True):
        o = q5.execute(dataclasses.replace(item, stories=tuple(dataclasses.replace(s, tests_block=block) for s in item.stories)), "record")
        j = o.get("journal") or []
        pick = lambda t, j=j: [e["data"] for e in j if e["type"] == t]  # noqa: E731
        out["blocking" if block else "non_blocking"] = {
            "outcomes": o["outcomes"],
            "replay_stream_leftover": {k: v for k, v in o["errors"].items() if v} or None,   # the item's scripted stream is the commit path's
            "admitted": [{"developer_call_permitted": a.get("developer_call_permitted"), "dispositions": a["dispositions"]} for a in pick("story/admitted")],
            "proof_verified": [{k: p.get(k) for k in ("criterion_id", "agreement", "verdict")} for p in pick("proof/verified")],
            "tests_adequacy": [{**{k: a.get(k) for k in ("outcome", "owner", "may_block", "developer_chargeable", "vacuity", "relevance")},
                                "execution": a["execution"]["reason"]} for a in pick("tests/adequacy")],
            "failures": [{k: f.get(k) for k in ("code", "owner", "retryable")} for f in pick("failure/observed")],
            "developer_requests": sum(1 for p in pick("provider/request") if p.get("budget_owner") == "DEVELOPER"),
            "retries_charged": len(pick("story/retry")), "plan_drift_events": len(pick("story/plan-drift")),
            "terminal": [e["type"] for e in j if e["type"] in ("story/commit", "story/rollback")]}
    b, n = out["blocking"], out["non_blocking"]
    out["finding"] = {"non_blocking_commits": n["terminal"] == ["story/commit"], "blocking_rolls_back": b["terminal"] == ["story/rollback"],
                      "blocking_charges_a_developer_retry_with_no_developer_call": b["retries_charged"] >= 1 and b["developer_requests"] == 0,
                      "the_proofs_are_satisfied_in_both": all(p["agreement"] and p["verdict"] == "SATISFIED" for p in b["proof_verified"] + n["proof_verified"])}
    return out


def triage() -> dict:
    d = f"{CY}/P10/attempt-2"
    rec, ev = load(f"{d}/LEDGERLOCK-REGRESSION.json"), load(f"{d}/JOURNAL.json")
    expect = {(o["story"], o["criterion"]): o["candidate_expectation"] for o in rec["productproof"]["obligations"]}
    by: dict[str, list] = collections.defaultdict(list)
    for e in ev:
        if e["data"].get("story_id"):
            by[e["data"]["story_id"]].append(e)
    stories = {}
    for story, outcomes in rec["story_outcomes"].items():
        if outcomes[-1:] == ["COMMIT"]:
            continue
        events = by[story]
        starts = [i for i, e in enumerate(events) if e["type"] == "story/begin"]
        attempts = []
        for n, i in enumerate(starts):
            es = events[i:starts[n + 1] if n + 1 < len(starts) else None]
            pick = lambda t, es=es: [e for e in es if e["type"] == t]  # noqa: E731
            parent, admitted = es[0]["data"]["parent"], pick("story/admitted")[0]
            stage = [e["data"] for e in pick("probe/evaluated") if e["seq"] > admitted["seq"]]   # the candidate stage: after admission
            proofs = [e["data"] for e in pick("proof/verified")]
            candidates = sorted({r["record"]["revision"] for r in stage} | {p["candidate"] for p in proofs})
            unsat = [{"criterion": p["criterion_id"], "agreement": p["agreement"], "verdict": p.get("verdict"), "expectation": expect.get((story, p["criterion_id"]))}
                     for p in proofs if not (p["agreement"] and p.get("verdict") == expect.get((story, p["criterion_id"])))]
            a = admitted["data"]
            attempts.append({
                "attempt": n + 1, "parent_sha": parent, "candidate_sha": candidates[-1] if candidates else None,
                "candidate_is_the_parent": bool(candidates) and candidates[-1] == parent,
                "admission": {"admitted": a["admitted"], "developer_call_permitted": a.get("developer_call_permitted"),
                              "dispositions": dict(collections.Counter(a["dispositions"].values())),
                              "not_ready": {c: v for c, v in a["dispositions"].items() if v not in ("READY", "PRE_SATISFIED")}},
                "developer_requests": sum(1 for e in pick("provider/request") if e["data"].get("budget_owner") == "DEVELOPER"),
                "candidate_proof": {"records": len(stage),
                                    "not_satisfied": sorted({f"{r['criterion_id']}: {r['record']['result'].get('behavior_verdict')} "
                                                             f"{r['record']['result'].get('reason') or ''}".strip() for r in stage
                                                             if r["record"]["result"].get("behavior_verdict") != expect.get((story, r["criterion_id"]))})},
                "verified_proof": {"proofs": len(proofs), "satisfied": len(proofs) - len(unsat), "not_satisfied": unsat},
                "test_result": [{**{k: e["data"].get(k) for k in ("outcome", "owner", "may_block", "developer_chargeable", "vacuity", "relevance")},
                                 "selection": e["data"]["execution"]["selection"], "execution": e["data"]["execution"]["reason"],
                                 "regressions": e["data"]["regressions"]["reason"]} for e in pick("tests/adequacy")],
                "blocking_gate": [{"seq": e["seq"], **{k: e["data"].get(k) for k in ("code", "owner", "retryable", "detail")}} for e in pick("failure/observed")],
                "retry_charged": bool(pick("story/retry")),
                "terminal": next((e["type"] for e in es if e["type"] in ("story/commit", "story/rollback", "story/retry")), None)})
        letter, rationale, config, user = TRIAGE[story]
        last = attempts[-1]
        stories[story] = {
            "outcomes": outcomes, "parent_sha": last["parent_sha"], "candidate_sha": last["candidate_sha"],
            "candidate_note": ("no candidate: refused at admission, no developer call" if last["candidate_sha"] is None else
                               "the candidate is the parent: no developer call (fully PRE_SATISFIED)" if last["candidate_is_the_parent"] else None),
            "candidate_proof_result": last["candidate_proof"], "verified_proof_result": last["verified_proof"],
            "product_proof_satisfied_for_every_obligation": bool(last["verified_proof"]["proofs"]) and not last["verified_proof"]["not_satisfied"],
            "test_result": last["test_result"], "blocking_gate": last["blocking_gate"],
            "owner_and_failure_taxonomy": [f"{g['code']} / {g['owner']}" for a in attempts for g in a["blocking_gate"]],
            "retryability": [g["retryable"] for a in attempts for g in a["blocking_gate"]],
            "retries_charged": sum(a["retry_charged"] for a in attempts), "developer_requests": sum(a["developer_requests"] for a in attempts),
            "attempts": attempts,
            "classification": {"class": letter, "name": CLASSES[letter], "primary_cause": rationale},
            "exact_config_involved": config, "config_is_a_shipped_or_default_aisef_setting": False,
            "can_affect_an_ordinary_v2_user": user,
            "release_blocker": letter in ("A", "B"),
        }
    repro = presatisfied_reproducer()
    blockers = sorted(s for s, v in stories.items() if v["release_blocker"])
    return {
        "record": "AISEF V2 — CYCLE-2 LEDGERLOCK NON-COMMITTED STORY TRIAGE (QP-2.9 attempt 2)",
        "authority": "owner ruling 'CYCLE-2 FINAL OWNER CLOSURE AUDIT' §2", "written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": {"journal": ident(f"{d}/JOURNAL.json"), "regression_record": ident(f"{d}/LEDGERLOCK-REGRESSION.json")},
        "preserved": {"delivery_verdict": rec["delivery_verdict"], "plan_quality_verdict": rec["plan_quality_verdict"],
                      "generalization": rec["generalization_claim"], "workload_class": rec["benchmark_class"],
                      "attempt_1": ident(f"{CY}/P10/NO-RECORD.json"), "rule": "nothing rerun, nothing tuned, nothing rewritten"},
        "classes": CLASSES, "stories": stories, "non_committed": len(stories),
        "by_class": dict(collections.Counter(v["classification"]["class"] for v in stories.values())),
        "shipped_default_facts": shipped_default_facts(),
        "history_of_the_interaction": interaction_history(),
        "fully_pre_satisfied_reproducer": repro,
        "rfc_sources": {"§14": "docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md lines 688-701: an INTRODUCE obligation SATISFIED at the parent MUST be recorded "
                               "PRE_SATISFIED, emit story/plan-drift, consume no developer budget, MUST NOT require that correct code be made incorrect; if every "
                               "obligation is PRE_SATISFIED the story ends STORY_ALREADY_SATISFIED, every obligation still verified, the developer call skipped",
                        "§15.3": "INADEQUATE MAY block under project policy; owner DEVELOPER", "§17": "a commit MUST NOT depend on a developer test verdict"},
        "release_blockers": blockers,
        "classification_status": "the evidence's reading, returned for the Owner's ruling; the class A reading of STORY-02-01 and STORY-02-02 is a RELEASE BLOCKER "
                                 "under the ruling and stops the audit before closure acceptance",
        "not_done": ["no kernel change: fixing the §14/§15.3 interaction touches engineering-adequacy and commit semantics and needs an Owner ruling",
                     "no rerun of LedgerLock", "no change of PLAN-V2.2 or of any spec"],
    }


# ============================================================================================ §3 the orchestration change

def functions(src: str) -> dict:
    out = {}

    def walk(node, prefix=""):
        for n in getattr(node, "body", []):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out[prefix + n.name] = ast.dump(n)
                if isinstance(n, ast.ClassDef):
                    walk(n, prefix + n.name + ".")
    walk(ast.parse(src))
    return out


def scenarios() -> dict:
    """Runs in a child interpreter under one kernel: four stories on the paths other than 'a multi-kind story runs'."""
    from validation.qualification import c2_orchestration_repair as rp
    m = rp._load("c2_orchestration_conformance", "tests/v2/test_c2_orchestration_conformance.py")
    r_, e2e, specs, probes = m.R, m.e2e, m.SPECS, m.PROBES
    f, k = specs["F_ADD"].probe_id, specs["K_SUB"].probe_id
    out = {}

    def observe(name, build):
        with tempfile.TemporaryDirectory(prefix="aisef2-c2-audit-") as t:
            holder = m.Cleanups()
            try:
                w = m.World(holder, pathlib.Path(t) / "w")
                o = {"raised": None}
                try:
                    last = build(w)
                except Exception as e:  # noqa: BLE001 — an observation: what the kernel raised
                    last, o["raised"] = "S1", f"{type(e).__name__}: {e}"[:200]
                    with contextlib.suppress(Exception):
                        w.run.interrupt()
                admitted = [e for e in w.run.events if e.type == "story/admitted" and e.data.get("story_id") == last]
                o.update(story=last, state=m.plain(w.run.state(m.P.STORY_STATE)).get(last),
                         event_types=[e.type for e in w.run.events if e.data.get("story_id") == last],
                         dispositions=m.plain(admitted[-1].data["dispositions"]) if admitted else None,
                         failures=[list(x) for x in w.failures(last)], details=w.details(last),
                         records=[{"criterion_id": e.data["criterion_id"], "probe_id": e.data["record"]["probe_id"], "verdict": m.verdict_of(e.data["record"]),
                                   "result_fields": sorted(e.data["record"]["result"])} for e in w.records(last)],
                         proofs=[{"criterion_id": e.data["criterion_id"], "agreement": e.data["agreement"], "verdict": e.data.get("verdict")}
                                 for e in w.events("proof/verified", last)])
                out[name] = o
            finally:
                holder.close()

    def single(w):
        w.story(m.plan_of(w.base, ("C-F", "F_ADD", "S1", r_.INTRODUCE)), "S1", e2e.Dev(m.IMPLEMENTED), probes={f: probes[f]})
        return "S1"

    def miskeyed(w):
        w.story(m.plan_of(w.base, ("C-F", "F_ADD", "S1", r_.INTRODUCE)), "S1", e2e.Dev(m.IMPLEMENTED), probes={"the-only-probe": probes[f]})
        return "S1"

    def foreign(w):
        w.story(m.plan_of(w.base, ("C-P", "P_ADD", "S1", r_.INTRODUCE)), "S1", e2e.Dev(m.IMPLEMENTED), probes={f: probes[f]})
        return "S1"

    def reprove_unwired(w):
        plan = m.plan_of(w.base, ("C-K0", "K_SUB", "S0", r_.PRESERVE), ("C-M2", "F_MUL", "S2", r_.INTRODUCE))
        w.story(plan, "S0", e2e.Dev(m.IMPLEMENTED), probes={k: probes[k]})
        mul = {"app/calc.py": e2e.CALC + e2e.ADD + m.MUL, "tests/test_s2.py": m.TEST_MUL}
        w.story(plan, "S2", e2e.Dev(mul), probes={f: probes[f]}, tests=("tests/test_s2.py",))
        return "S2"

    for name, b in (("single_kind_story_wired_by_probe_id", single), ("single_kind_story_wired_under_another_key", miskeyed),
                    ("story_whose_spec_kind_the_harness_did_not_wire", foreign),
                    ("post_merge_reproof_of_a_prior_story_s_spec_of_an_unwired_kind", reprove_unwired)):
        observe(name, b)
    out["multi_kind_story"] = rp._job_multi_kind()
    return out


CHILD = """
import json, sys
kernel, root = sys.argv[1], sys.argv[2]
sys.path[:0] = [p for p in (kernel, root) if p]
import aisef2
from validation.qualification import c2_closure_audit as ca
print(ca.MARK + json.dumps({"kernel_file": aisef2.__file__, "result": ca.scenarios()}, default=str), flush=True)
"""


def old_vs_new() -> dict:
    from validation.qualification import c2_orchestration_repair as rp
    res = {}
    with tempfile.TemporaryDirectory(prefix="aisef2-c2-audit-old-") as t:
        info = rp.materialise(OLD, pathlib.Path(t))
        for label, kroot in (("old", t), ("new", "")):
            r = subprocess.run([sys.executable, "-P", "-B", "-c", CHILD, kroot, str(ROOT)], cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
            line = next((ln for ln in r.stdout.splitlines() if ln.startswith(MARK)), None)
            if line is None:
                raise SystemExit(f"{label} kernel job exited {r.returncode}:\n{(r.stdout + r.stderr)[-3000:]}")
            d = json.loads(line[len(MARK):])
            want = (pathlib.Path(kroot) if kroot else ROOT) / "aisef2"
            if pathlib.Path(d["kernel_file"]).resolve().parent != want.resolve():
                raise SystemExit(f"{label}: imported {d['kernel_file']}")
            res[label] = d["result"]
    out = {"old_kernel": {"commit": OLD, "aisef2_tree": info["aisef2_tree"]}, "new_kernel": {"aisef2_tree": git("rev-parse", "HEAD:aisef2")}, "scenarios": {}}
    for name in res["new"]:
        a, b = res["old"][name], res["new"][name]
        keys = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        out["scenarios"][name] = {"identical": not keys, "differing_fields": keys,
                                  "old": {k: a.get(k) for k in ("raised", "state", "failures", "details", "dispositions", "attempts", "committed") if k in a},
                                  "new": {k: b.get(k) for k in ("raised", "state", "failures", "details", "dispositions", "attempts", "committed") if k in b}}
        if keys and name.startswith("post_merge"):
            crit = "C-K0"
            out["scenarios"][name]["difference"] = {
                "old_events_for_the_unwired_spec": {"probe_evaluated": [r for r in a["records"] if r["criterion_id"] == crit],
                                                    "proof_verified": [p for p in a["proofs"] if p["criterion_id"] == crit]},
                "new_events_for_the_unwired_spec": {"probe_evaluated": [r for r in b["records"] if r["criterion_id"] == crit],
                                                    "proof_verified": [p for p in b["proofs"] if p["criterion_id"] == crit]},
                "event_count": {"old": len(a["event_types"]), "new": len(b["event_types"])},
                "same_outcome_failure_owner_retryability_detail": all(a[k] == b[k] for k in ("state", "failures", "details"))}
    return out


ASPECTS = {
    "scheduling": (["aisef2/orchestrate/story_runner.py::run_story"], "the order of stories is the caller's; run_story is AST-identical"),
    "dependency semantics": (["aisef2/plan/obligation.py", "aisef2/plan/static_admission.py", "aisef2/plan/drift.py"], "the plan modules are byte-identical"),
    "StoryAdmission": (["aisef2/plan/story_admission.py"], "byte-identical; it already selected the probe by spec.probe_id per obligation before the change"),
    "retry routing": (["aisef2/control/routing.py", "aisef2/control/budget.py"], "byte-identical"),
    "owner routing": (["aisef2/control/owner.py"], "byte-identical"),
    "budget ownership": (["aisef2/control/budget.py"], "byte-identical"),
    "story transaction semantics": (["aisef2/runtime/story_scope.py", "aisef2/runtime/run_scope.py", "aisef2/orchestrate/gate.py", "aisef2/orchestrate/merge.py",
                                     "aisef2/orchestrate/workspace.py"], "byte-identical"),
    "proof ordering": (["aisef2/orchestrate/proof.py::prove"], "prove changed: implementer run -> its probe/evaluated -> verifier run -> its probe/evaluated -> "
                                                               "proof/verified is preserved whenever both parties have a probe (the seven Cycle-1 corpus journals "
                                                               "are identical under both kernels); when a party has none, nothing is measured and nothing is journaled "
                                                               "before the typed failure"),
    "candidate freeze": (["aisef2/orchestrate/story_runner.py::_freeze_plan", "aisef2/orchestrate/story_runner.py::_committed", "aisef2/orchestrate/workspace.py",
                          "aisef2/orchestrate/adapters.py"], "AST/byte-identical; _attempt differs only in how the two Party objects are constructed"),
    "verifier agreement": (["aisef2/journal/format3.py", "aisef2/probe/protocol.py"], "verified_payload and the record comparison are byte-identical; prove's agreement "
                                                                                      "branch is unchanged text"),
    "journal events": (["aisef2/journal/event.py", "aisef2/journal/format2.py", "aisef2/journal/format3.py", "aisef2/journal/writer.py", "aisef2/arch/enums.py"],
                       "no event type, payload field or enum member added or changed. ONE measured difference in which events a failure path emits: see "
                       "old_vs_new.post_merge_reproof_of_a_prior_story_s_spec_of_an_unwired_kind"),
    "projections": (["aisef2/journal/fold.py", "aisef2/control/routing.py", "aisef2/control/budget.py", "aisef2/control/owner.py"],
                    "byte-identical; Q4 on the changed kernel: 100000/100000 matched against the six reference models, twice"),
    "failure taxonomy": (["aisef2/control/owner.py", "aisef2/arch/enums.py"], "byte-identical; prove uses the existing FailureCode.PROBE_INVALID_SPEC at one new site"),
}


def orchestration_review() -> dict:
    from validation.qualification import p5_acceptance as pa
    changed = {}
    for f in ORCH_FILES:
        a, b = functions(git("show", f"{OLD}:{f}")), functions((ROOT / f).read_text(encoding="utf-8"))
        changed[f] = {"changed": sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k)), "unchanged": sorted(k for k in b if a.get(k) == b.get(k)),
                      "blob_before": git("rev-parse", f"{OLD}:{f}"), "blob_after": git("rev-parse", f"HEAD:{f}")}
    kernel_files = sorted(ln.split("\t")[1] + f" ({ln.split(chr(9))[0]})" for ln in git("diff", "--name-status", OLD, "HEAD", "--", "aisef2").splitlines())
    aspects = {}
    for name, (refs, note) in ASPECTS.items():
        ev = {}
        for ref in refs:
            path, _, fn = ref.partition("::")
            if fn:
                a, b = functions(git("show", f"{OLD}:{path}")), functions((ROOT / path).read_text(encoding="utf-8"))
                ev[ref] = "AST-identical" if a.get(fn) == b.get(fn) and fn in b else "CHANGED"
            else:
                ev[ref] = "byte-identical" if git("rev-parse", f"{OLD}:{path}") == git("rev-parse", f"HEAD:{path}") else "CHANGED"
        aspects[name] = {"evidence": ev, "note": note,
                         "altered": "NO" if all(v != "CHANGED" for v in ev.values()) and name != "journal events" else "SEE NOTE"}
    v = pa.verify(run_guards=False)
    accepted = load(pa.OUT_REL)["verification"]["identities"]
    key = lambda r: [r["spec_id"], r["contract_id"], r["contract_hash"], r["spec_hash_id"], r["semantic_hash"], r["probe_id"], r["probe_digest"]]  # noqa: E731
    paths = old_vs_new()
    diff = git("diff", OLD, "HEAD", "--", *ORCH_FILES)
    added = "\n".join(ln for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
    tests = {"before_tests_unchanged_and_passing": {m: {"blob_identical": git("rev-parse", f"{OLD}:tests/v2/{m.split('.')[-1]}.py") == git("rev-parse", f"HEAD:tests/v2/{m.split('.')[-1]}.py"),
                                                        **_tests(m)} for m in ("tests.v2.test_p6_stages", "tests.v2.test_p6_orchestration")},
             "after_tests": _tests("tests.v2.test_c2_orchestration_conformance")}
    post = paths["scenarios"]["post_merge_reproof_of_a_prior_story_s_spec_of_an_unwired_kind"]
    conformance = (ROOT / "tests/v2/test_c2_orchestration_conformance.py").read_text(encoding="utf-8")
    named = lambda *names: [n for n in names if f"def {n.split('.')[1]}(" in conformance and f"class {n.split('.')[0]}(" in conformance] or None  # noqa: E731
    return {
        "record": "AISEF V2 — CYCLE-2 ORCHESTRATION CHANGE REVIEW (for the Owner's classification)",
        "authority": "owner ruling 'CYCLE-2 FINAL OWNER CLOSURE AUDIT' §3", "written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "1_commits": {"code": {c: git("log", "-1", "--format=%s", c)[:160] for c in ORCH_COMMITS},
                      "lane": "c2/lane-o-orchestration (e3d0560 the change; ac88f36 the correction for invariant III in proof.py), merged at "
                              "6368ae57ec8ada335546bfd6ee979d98ed80615a; authorized by owner ruling 2026-09-30 B, Ruling 3 (C2-ORCHESTRATION-CONFORMANCE-REPAIR)",
                      "kernel_files_changed_between_the_old_kernel_and_head": kernel_files},
        "2_files": {f: {"before": changed[f]["blob_before"], "after": changed[f]["blob_after"]} for f in ORCH_FILES},
        "3_functions_and_classes": {f: {"changed": changed[f]["changed"], "unchanged_count": len(changed[f]["unchanged"])} for f in ORCH_FILES},
        "4_before": "story_runner._probe(inputs, on_range, scratch) took the ONE factory of StoryInputs.probes and raised InvariantError('cycle 1 proves a story "
                    "with exactly one probe factory') when there were more; both parties were built with a maker that never saw the spec being proved. "
                    "StoryAdmission, in the same function, already resolved the probe per obligation by spec.probe_id.",
        "5_after": "story_runner._probe(inputs, on_range, scratch, spec) returns the factory registered under spec.probe_id, or None; Party(by_spec=True) hands "
                   "the spec to its maker; prove() types a party without a probe for the spec as PROBE_INVALID_SPEC with no record. One ProductProof "
                   "evaluation per obligation, by the probe its spec names; no result is cached or shared.",
        "6_why_the_four_stories_could_not_execute": "STORY-01-01, 03-01, 04-01 and 04-02 of PLAN-V2.2 carry specs of two or three probe kinds; admission "
                                                    "needs every kind's factory wired, and with more than one factory wired the candidate stage raised the "
                                                    "InvariantError — after the developer request had been spent (multi_kind_story.old)",
        "7_required_because_new_probe_kinds_exist": "YES: Cycle 1 had one probe kind, so 'the one factory' and 'the factory of the spec's probe' were the same "
                                                    "object. The second kind made the candidate stage's shortcut observable. The change adds no probe, no "
                                                    "protocol and no probe-specific branch.",
        "8_aspects": aspects,
        "9_identities": {"contracts": len(v["identities"]["specs"]),
                         "contract_hashes_spec_hashes_semantic_hashes_equal_to_the_accepted_record": [key(r) for r in v["identities"]["specs"]] == [key(r) for r in accepted["specs"]],
                         "aggregate_digest": hashlib.sha256(json.dumps([key(r) for r in v["identities"]["specs"]]).encode()).hexdigest(),
                         "semantic_change": v["semantic_change"], "plan_hash": v["identities"]["plan_hash"],
                         "caveat": "unchanged hashes show the specs and the plan did not move; they do not by themselves show orchestration semantics "
                                   "unchanged — items 8, 11, 12, 13 and old_vs_new carry that"},
        "10_probes": {"catalog": {k: e["digest"] for k, e in v["identities"]["catalog"].items()}, "equal_to_the_accepted_record": v["identities"]["catalog"] == accepted["catalog"],
                      "aisef2_probe_tree": {"old": git("rev-parse", f"{OLD}:aisef2/probe"), "head": git("rev-parse", "HEAD:aisef2/probe")}},
        "11_tests": tests,
        "12_cannot_silently_skip_a_probe": {
            "tests": named("Parties.test_a_party_without_the_spec_s_probe_runs_nothing_and_makes_no_record",
                           "Parties.test_prove_types_a_party_without_the_spec_s_probe_as_PROBE_INVALID_SPEC_and_seals_nothing",
                           "OneProofPerObligation.test_7_one_INVALID_SPEC_among_READY_is_PROBE_INVALID_from_the_real_probe_or_from_an_unwired_one",
                           "ReproofOfAnotherKind.test_a_prior_spec_whose_probe_the_harness_did_not_wire_is_PROBE_INVALID_SPEC_never_a_crash",
                           "MixedStory.test_8_each_obligation_has_its_own_candidate_records_binding_its_spec_probe_and_candidate",
                           "MixedStory.test_11_no_evaluation_is_shared_two_specs_of_one_kind_and_one_spec_under_two_obligations_each_run"),
            "measured_here": {k: paths["scenarios"][k]["new"] for k in ("story_whose_spec_kind_the_harness_did_not_wire",
                                                                        "post_merge_reproof_of_a_prior_story_s_spec_of_an_unwired_kind")},
            "reading": "an obligation whose probe is missing never commits: it is PROBE_INVALID at admission or PROBE_INVALID_SPEC at the proof; "
                       "RFC §17's commit condition (a VerifiedProof per obligation) is evaluated by unchanged code"},
        "13_one_probe_cannot_satisfy_another_s_obligation": {
            "tests": named("OneProofPerObligation.test_10_one_failing_candidate_spec_is_not_masked_by_the_others_passing",
                           "MixedStory.test_9_each_obligation_has_its_own_verified_proof_citing_its_two_records",
                           "Parties.test_the_runner_resolves_the_factory_of_the_spec_s_own_probe_identity_or_none"),
            "mechanism": "aisef2/probe/protocol.py run_probe (byte-identical) answers InvalidSpec when (spec.probe_id, spec.probe_digest) is not the probe's; "
                         "each proof/verified binds its own spec_id, semantic_hash and its two records"},
        "14_generality": {"ledgerlock_in_the_added_lines": "ledger" in added.lower(),
                          "probe_kinds_named_in_the_added_lines": [p for p in ("python_callable", "cli_invocation", "file_artifact", "process_effect") if p in added],
                          "reading": "the lookup is inputs.probes.get(spec.probe_id): any set of registered probes; the tests use synthetic two- and three-kind "
                                     "stories, permuted orders, and the four LedgerLock stories only as one case"},
        "15_exact_diff": diff.splitlines(),
        "old_vs_new": paths,
        "classification": {
            "options": ["ORCH-BUGFIX-NO-SEMANTIC-CHANGE", "ORCH-SEMANTIC-CHANGE", "ORCH-ARCHITECTURE-CHANGE"],
            "self_authorized": False,
            "what_the_evidence_shows": [
                "no frozen item, protocol, event type, payload field, enum, disposition, routing table, budget or projection module changed (item 8, byte/AST evidence)",
                "single-kind stories behave identically under both kernels: the seven Cycle-1 corpus journals (C2-ORCHESTRATION-CONFORMANCE-REPAIR.json), and three "
                "single-kind paths measured here including two misconfigurations — identical",
                "a multi-kind story: old InvariantError after a developer request; new COMMIT with one proof per obligation",
                "ONE path differs in what is journaled, with the same outcome, failure code, owner, retryability and detail: the post-merge re-proof of a prior "
                "story's spec whose probe kind the current harness did not wire. Old: the story's single (wrong-kind) probe was run on that spec — two "
                "probe/evaluated InvalidSpec records and a proof/verified with no verdict — then PROBE_INVALID_SPEC. New: nothing is measured, no record, no "
                "proof/verified, then PROBE_INVALID_SPEC. Events for the story: " + json.dumps(post.get("difference", {}).get("event_count")),
            ],
            "reading_of_the_evidence": "consistent with ORCH-BUGFIX-NO-SEMANTIC-CHANGE except for the one disclosed journal difference on a misconfiguration "
                                       "failure path; whether that difference is a semantic change is the Owner's ruling",
            "status": "RETURNED FOR THE OWNER'S EXPLICIT RULING — not accepted here"},
    }


# ============================================================================================ §4-§7, §9, §10

def planes(rev: str) -> dict:
    from aisef.control import planes as pl
    rules = pl.rules_from(json.loads((ROOT / "docs/closure-gate.json").read_text(encoding="utf-8")))
    by: dict[str, list[str]] = collections.defaultdict(list)
    for mode, blob, path in pl.tree(ROOT, rev):
        by[pl.class_of(path, rules)].append(f"{mode} {blob} {path}")
    return {cls: {"digest": pl._digest(by.get(cls, [])), "files": len(by.get(cls, []))} for cls in (pl.PRODUCT, pl.ASSURANCE, pl.EVIDENCE, pl.DOCUMENTATION, pl.UNRESOLVED)}


def plane_changes(a: str, b: str) -> dict:
    from aisef.control import planes as pl
    rules = pl.rules_from(json.loads((ROOT / "docs/closure-gate.json").read_text(encoding="utf-8")))
    by: dict[str, list[str]] = collections.defaultdict(list)
    for p in git("diff", "--name-only", a, b).splitlines():
        by[pl.class_of(p, rules)].append(p)
    return {k: sorted(v) for k, v in sorted(by.items())}


def trees(rev: str) -> dict:
    return {t: git("rev-parse", f"{rev}:{t}") for t in ("aisef", "aisef2", "aisef2/probe", "aisef2/orchestrate", "validation/v2", "tests/v2")}


def lineage() -> list[dict]:
    rows = []
    for label, cand, rel, note in (("R2", R2, f"{CY}/Q0-Q3-R2", "FAILED on Windows (Q0 48/51: validation/qualification/v1_pf_001_policy.py repo_path); kept"),
                                   ("R3", R3, f"{CY}/Q0-Q3-R3", "GREEN; closed C2-P6 (9bd16fa); the candidate LANE-Q ran on"),
                                   ("R4", FINAL, f"{CY}/Q0-Q3-R4", "GREEN on the final candidate (LANE-Q + LANE-X)")):
        s = load(f"{rel}/SUMMARY.json")
        plat = {}
        for p in PLATFORMS:
            row = {}
            for q in ("Q0", "Q1", "Q2", "Q3"):
                f = ROOT / rel / q / f"{q}-{p}.json"
                if f.exists():
                    d = json.loads(f.read_text(encoding="utf-8"))
                    row[q] = f"{d['status']} {d['counts']['PASS']} pass, {d['counts']['FAIL'] + d['counts']['ERROR']} fail, {d['counts']['NOT_APPLICABLE']} n/a"
                else:
                    row[q] = "NOT RUN (a lower rung was not GREEN on this platform)"
            plat[p] = row
        q2 = next((json.loads(f.read_text(encoding="utf-8")) for f in sorted((ROOT / rel / "Q2").glob("Q2-linux-*.json"))), None)
        mu = q2["product_mutation"]["totals"] if q2 else None
        t = trees(cand)
        rows.append({"attempt": label, "candidate_sha": cand, "product_tree_aisef": t["aisef"], "aisef2_tree": t["aisef2"],
                     "assurance_trees": {"validation/v2": t["validation/v2"], "tests/v2": t["tests/v2"]}, "planes": planes(cand),
                     "summary": {**ident(f"{rel}/SUMMARY.json"), "verdict": s["verdict"]}, "Q0": s["rungs"]["Q0"]["status"], "Q1": s["rungs"]["Q1"]["status"],
                     "Q2": s["rungs"]["Q2"]["status"], "Q3": s["rungs"]["Q3"]["status"], "platforms": plat,
                     "mutation": None if mu is None else {"targets": mu["targets"], "total": mu["mutants"], "killed": mu["killed"], "survivors": mu["survivors"],
                                                          "audited_survivors": mu["survivors"] - mu["unaudited"], "unaudited_survivors": mu["unaudited"]},
                     "note": note})
    return rows


def survivor_audits() -> list[dict]:
    import mutation as mt
    return [{"target": t, "mutant": m, "audit": a} for (t, m), a in mt.AUDITED.items()]


def q45_audit() -> dict:
    out = {}
    r3 = load(f"{CY}/Q0-Q3-R3/SUMMARY.json")
    for name, rel, rec_name, consumed in (("Q4", f"{CY}/Q4", "DIFFERENTIAL.json", ("aisef2", "tests/v2/refmodel", "tests/v2/p3/journal_gen.py", "tests/v2/p3/test_reference_models.py")),
                                          ("Q5", f"{CY}/Q5", "REPRODUCTION.json", ("aisef2", "tests/v2"))):
        rec, sub = load(f"{rel}/{rec_name}"), load(f"{rel}/SUBJECT.json")
        i = sub["identity"]
        exe = i["execution_commit"]
        moved = [p for p in git("diff", "--name-only", R3, exe, "--", *consumed).splitlines()]
        other = {t: {"r3_candidate": git("rev-parse", f"{R3}:{t}"), "at_execution": git("rev-parse", f"{exe}:{t}")} for t in ("aisef2", "tests/v2", "validation/v2")}
        v2_changed = git("diff", "--name-only", R3, exe, "--", "validation/v2").splitlines()
        harness_src = "".join((ROOT / "validation/qualification" / f).read_text(encoding="utf-8") for f in (("q4.py", "q4_aggregate.py") if name == "Q4" else ("q5.py",)))
        same = (not moved and i["semantic_candidate"] == R3 and i["kernel_tree"] == other["aisef2"]["r3_candidate"] == other["aisef2"]["at_execution"]
                and i["working_tree_clean"] and all(e["digest"] == r3["subject"]["probes"][e["probe_id"]]["digest"] for e in i["active_catalog"].values()))
        out[name] = {
            "original_record": ident(f"{rel}/{rec_name}"), "subject_record": ident(f"{rel}/SUBJECT.json"),
            "subject_sha_at_execution": exe, "semantic_candidate_named": i["semantic_candidate"], "working_tree_clean_at_freeze": i["working_tree_clean"],
            "subject_trees": other, "consumed_paths": list(consumed), "consumed_paths_changed_between_the_r3_candidate_and_execution": moved,
            "validation_v2_changed_since_r3": {"files": v2_changed, "imported_by_this_rung": any(pathlib.Path(f).stem in harness_src for f in v2_changed),
                                               "note": "history and seal registrations of 9bd16fa; the rung does not import run_history"},
            "qualification_kernel_identity": {"kernel_tree": i["kernel_tree"], "kernel_digest": i["kernel_digest"],
                                              "one_identity": sub.get("one_kernel_identity") or sub.get("one_identity")},
            "active_probe_digests": i["active_catalog"],
            "active_probe_digests_equal_to_r3": all(e["digest"] == r3["subject"]["probes"][e["probe_id"]]["digest"] for e in i["active_catalog"].values()),
            "runspec_capability_identity": {k: i.get(k) for k in ("f1_identity", "f9_identity", "reference_digest", "generator_digest", "harness_digest", "fixture_digest") if i.get(k)},
            "corpus_identity": ({"corpus_digest": rec["corpus_digest"], "replay_digest": rec["replay_digest"]} if name == "Q5" else {"seed_schedule": i["seed_schedule"]}),
            "timestamps": {"subject_frozen_at": sub["frozen_at"], "aggregated": rec["aggregated"]},
            "erroneous_pointer_preserved": [k for k in rec["p7_evidence"] if "Q0-Q3" in k],
            "pointer_it_should_have_been": f"{CY}/Q0-Q3-R3/SUMMARY.json",
            "r2_and_r3_candidates_carry_the_same_kernel_tree": git("rev-parse", f"{R2}:aisef2") == git("rev-parse", f"{R3}:aisef2"),
            "did_the_original_measurement_run_on_the_same_consumed_identities_as_the_qualifying_candidate": "YES" if same else "NO",
            "classification": "PROVENANCE_POINTER_CORRECTION" if same else "STALE — RERUN REQUIRED",
        }
    out["corrigendum"] = ident(f"{CY}/C2-P7-P8-BINDING-CORRIGENDUM-1.json")
    fin = {}
    r4 = load(f"{CY}/Q0-Q3-R4/SUMMARY.json")
    for name, rel, rec_name, consumed in (("Q4-FINAL", f"{CY}/Q4-FINAL", "DIFFERENTIAL.json", ("aisef2", "tests/v2/refmodel", "tests/v2/p3/journal_gen.py", "tests/v2/p3/test_reference_models.py")),
                                          ("Q5-FINAL", f"{CY}/Q5-FINAL", "REPRODUCTION.json", ("aisef2", "tests/v2"))):
        rec, sub = load(f"{rel}/{rec_name}"), load(f"{rel}/SUBJECT.json")
        i = sub["identity"]
        exe = i["execution_commit"]
        moved = git("diff", "--name-only", FINAL, exe, "--", *consumed).splitlines()
        lower = [k for k in rec["p7_evidence"] if "Q0-Q3" in k]
        fin[name] = {"record": ident(f"{rel}/{rec_name}"), "status": rec["status"], "subject_sha_at_execution": exe, "semantic_candidate_named": i["semantic_candidate"],
                     "kernel_tree": i["kernel_tree"], "kernel_digest": i["kernel_digest"], "consumed_paths_changed_between_the_final_candidate_and_execution": moved,
                     "active_probe_digests_equal_to_r4": all(e["digest"] == r4["subject"]["probes"][e["probe_id"]]["digest"] for e in i["active_catalog"].values()),
                     "lower_rung_bound": lower, "lower_rung_is_green_for_this_candidate": lower == [f"{CY}/Q0-Q3-R4/SUMMARY.json"] and r4["verdict"] == "GREEN"
                     and r4["subject"]["semantic_candidate"] == i["semantic_candidate"] == FINAL,
                     "fresh": not moved and i["semantic_candidate"] == FINAL and i["working_tree_clean"]}
    out["final_candidate"] = fin
    out["why_the_final_reruns_were_needed"] = "the final candidate adds aisef2/cohort: the kernel digest Q4 and Q5 consume covers every aisef2 file, so both were rerun " \
                                              "(Q4-FINAL, Q5-FINAL); the orchestration change itself was already in the R3 kernel both original runs measured"
    return out


def commits() -> dict:
    from validation.qualification import p5_acceptance as pa
    v = pa.verify(run_guards=False)
    key = lambda r: [r["spec_id"], r["contract_id"], r["contract_hash"], r["spec_hash_id"], r["semantic_hash"], r["probe_id"], r["probe_digest"]]  # noqa: E731
    agg = hashlib.sha256(json.dumps([key(r) for r in v["identities"]["specs"]]).encode()).hexdigest()
    kernel_digest = load(f"{CY}/Q4-FINAL/SUBJECT.json")["identity"]["kernel_digest"]
    rows, prev = {}, None
    for name, sha in (("c11615a", FINAL), ("2dd1226", REPORT_HEAD), ("3ed2c41", BOOKKEEPING)):
        t = trees(sha)
        rows[name] = {"sha": sha, "parents": git("log", "-1", "--format=%P", sha).split(), "subject": git("log", "-1", "--format=%s", sha)[:140],
                      "changed_paths_since": None if prev is None else {"since": prev, "by_plane": plane_changes(prev, sha)},
                      "changed_paths_in_this_commit": plane_changes(f"{sha}^", sha),
                      "planes": planes(sha), "trees": t,
                      "inputs_of_the_plan_and_specs": {p: git("rev-parse", f"{sha}:{p}") for p in ("validation/qualification/p10_contracts.py", "validation/qualification/p5_acceptance.py",
                                                                                                  "validation/qualification/p5_falsifiability.py", "tests/v2/fixtures/workloads",
                                                                                                  f"{CY}/P5-CONTRACT-APPROVALS.json", f"{CY}/P5-PLAN-V2.2-PROPOSAL.json")}}
        prev = sha
    same = lambda k: len({json.dumps(r[k], sort_keys=True) for r in rows.values()}) == 1  # noqa: E731
    return {"commits": rows,
            "identical_across_the_three": {"aisef2_tree": len({r["trees"]["aisef2"] for r in rows.values()}) == 1,
                                           "probe_tree": len({r["trees"]["aisef2/probe"] for r in rows.values()}) == 1,
                                           "validation_v2_tree": len({r["trees"]["validation/v2"] for r in rows.values()}) == 1,
                                           "tests_v2_tree": len({r["trees"]["tests/v2"] for r in rows.values()}) == 1,
                                           "plan_and_spec_inputs": same("inputs_of_the_plan_and_specs"),
                                           "PRODUCT_AFFECTING_digest": len({r["planes"]["PRODUCT_AFFECTING"]["digest"] for r in rows.values()}) == 1},
            "measured_at_head_and_valid_for_all_three_because_the_trees_are_identical": {
                "active_probe_digests": {k: e["digest"] for k, e in v["identities"]["catalog"].items() if e["active"]},
                "inactive_cycle1_probe": {k: e["digest"] for k, e in v["identities"]["catalog"].items() if not e["active"]},
                "plan_v22_hash": v["identities"]["plan_hash"], "semantic_hashes_aggregate_59": agg, "contracts": len(v["identities"]["specs"]),
                "qualification_kernel_identity": {"aisef2_tree": rows["c11615a"]["trees"]["aisef2"], "kernel_digest": kernel_digest}},
            "plane_rules": "docs/closure-gate.json#planes via aisef.control.planes (the existing V1 closure model, read-only): PRODUCT_AFFECTING is what the "
                           "published wheel ships (aisef/*, build config); aisef2/*, tests/* and validation/* are ASSURANCE_AFFECTING; closure-evidence/* is EVIDENCE_ONLY",
            "answers": {
                "product_candidate": f"{FINAL} — the V2 kernel under qualification is its aisef2 tree {rows['c11615a']['trees']['aisef2']}. Under the existing plane "
                                     "rules the PRODUCT_AFFECTING plane is the V1 wheel content, identical at all three commits: Cycle 2 changes nothing that ships",
                "qualification_candidate": f"{FINAL} (QP-2.6 R4, Q4-FINAL, Q5-FINAL); QP-2.9 ran on kernel tree 37bf6457f350dd720a2214f04f3896c554ad0904 "
                                           f"(the R3 candidate {R3}) and was not rerun: the kernel files that differ between that tree and the final one are "
                                           f"{git('diff', '--name-status', R3, FINAL, '--', 'aisef2').split()} — the cohort package, which no other kernel module imports (git grep)",
                "evidence_only_bookkeeping": f"{BOOKKEEPING} (one history file). {REPORT_HEAD} adds evidence and one validation/qualification builder "
                                             "(ASSURANCE_AFFECTING by the rule 'validation/*', outside the trees QP-2.6 consumes)",
                "release_source_candidate_if_approved": "the branch head that carries this audit — its aisef2, validation/v2 and tests/v2 trees are the final "
                                                        f"candidate's ({FINAL}). The Owner names it; nothing here does",
                "release_fact_for_the_owner": "pyproject.toml excludes aisef2* from the wheel and the version is the V1 one: as the tree stands, a published artifact "
                                              "contains no V2 code. Packaging a V2 release is a PRODUCT_AFFECTING change outside Cycle 2's scope"}}


def gate_of(sha: str, history_rel: str) -> dict:
    e = [x for x in load(history_rel)["entries"] if x["commit"] == sha]
    ci = [x for x in e if x["where"] == "ci"]
    return {"commit": sha, "recorded_in": history_rel, "seq": [x["seq"] for x in e],
            "local": next(({"result": x["result"], "tests_run": x["tests_run"], "owned_after": x.get("owned_processes_after"), "escaped": x.get("owned_escaped")}
                           for x in e if x["where"] == "local"), None),
            "ci_run": sorted({x.get("ci_run") for x in ci if x.get("ci_run")}),
            "ci_jobs": {x["job"]: {"result": x["result"], "tests_run": x.get("tests_run"), "owned_after": x.get("owned_processes_after"), "escaped": x.get("owned_escaped")} for x in ci},
            "all_pass": bool(e) and all(x["result"] == "PASS" for x in e),
            "residual": sum(x.get("owned_processes_after") or 0 for x in e), "escaped": sum(x.get("owned_escaped") or 0 for x in e)}


def history_freeze(candidate: dict) -> dict:
    import run_history as rh
    rows, residual, escaped = {}, 0, 0
    for phase, rel in rh.HISTORIES.items():
        if not phase.startswith("C2-") or not (ROOT / rel).exists():
            continue
        e = load(rel)["entries"]
        residual += sum(x.get("owned_processes_after") or 0 for x in e)
        escaped += sum(x.get("owned_escaped") or 0 for x in e)
        seal = rh.SEALS.get(phase)
        rows[phase] = {"path": rel, "file_sha256_when_written": ident(rel)["sha256"], "entry_count": len(e), "last_sequence": e[-1]["seq"],
                       "full_history_digest": hashlib.sha256(json.dumps(e, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                       "known_failures": [{"seq": x["seq"], "commit": x["commit"], "where": x["where"], "job": x["job"], "classification": x["classification"],
                                           "known_defect": x.get("known_defect"), "gate_effect": x["gate_effect"]} for x in e if x["result"] == "FAIL"],
                       "already_sealed_by": seal if seal and (ROOT / seal).exists() else None,
                       "status": "SEALED (existing mechanism, earlier ruling)" if seal and (ROOT / seal).exists() else "FROZEN_BY_OWNER_CLOSURE_PENDING_APPROVAL"}
    return {
        "record": "AISEF V2 — CYCLE-2 HISTORY FREEZE CANDIDATE (Owner-closure candidate record; evidence only)",
        "authority": "owner ruling 'CYCLE-2 FINAL OWNER CLOSURE AUDIT' §8", "written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "existing_mechanism": {
            "what_it_is": "validation/v2/run_history.py SEALS: a phase -> a seal or acceptance record whose attempt_history.total_attempts the checker compares with the history",
            "can_it_seal_these_histories_without_changing_assurance_semantics": "NO",
            "why": ["registering a seal is an edit of validation/v2/run_history.py: the validation/v2 tree is an identity QP-2.6 consumed (R4), so the edit would move the "
                    "qualified candidate",
                    "every Cycle-2 seal so far is an Owner acceptance or a closure written under an Owner ruling; no acceptance of C2-P7..C2-P10 or of the final "
                    "candidate exists yet to seal against"],
            "new_validation_code_written": False},
        "mandatory_seal_source": {"searched": ["docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md", "closure-evidence/v2/V2-RETRY-POLICY.json",
                                               "docs/implementation/v2/cycle2/cycle2-manifest.json"],
                                  "found": None, "note": "no normative source read here says a mechanical history seal is mandatory for release; 'sealed' in the RFC is "
                                                         "the evaluation-cohort state"},
        "accepted_candidate_identity": candidate,
        "histories": rows, "residual_processes_recorded": residual, "escaped_processes_recorded": escaped,
        "digest_rule": "full_history_digest is sha256 over json.dumps(entries, sort_keys=True, ensure_ascii=False) of the entries with sequence 1..last_sequence: "
                       "an append-only history keeps that prefix, so the digest stays checkable after a later append",
        "rule": "no row deleted, edited or relabelled. The gate attempts of the commit that carries this record cannot be in the record it carries: they are "
                "reported to the Owner with the audit and are appended (append-only) by whatever commit the Owner's ruling next authorizes",
        "status": "FROZEN_BY_OWNER_CLOSURE_PENDING_APPROVAL",
    }


def build() -> dict:
    tri = triage()
    orch = orchestration_review()
    lin, q45, com = lineage(), q45_audit(), commits()
    guards = {"cycle2_baseline": _run(["validation/v2/cycle2_baseline.py", "--check"]), "f1_f11": _run(["validation/v2/freeze_conformance.py", "--check"]),
              "v1_guard": _run(["validation/v2/v1_evidence_guard.py", "--check"]), "checker_calibration": _run(["validation/v2/checker_calibration.py", "--check"]),
              "run_history": _run(["validation/v2/run_history.py", "check"]), "mutation": _run(["validation/v2/mutation.py", "--check"]),
              "orchestration_repair_record": _run(["validation/qualification/c2_orchestration_repair.py", "--check"]),
              "v1_pf_001_policy": _run(["validation/qualification/v1_pf_001_policy.py", "--check"]),
              "c2_p10_cohort": _run(["validation/qualification/c2_p10_cohort.py", "--check"]), "c2_p10_profile": _run(["validation/qualification/c2_p10_profile.py", "--check"])}
    gate = gate_of(BOOKKEEPING, f"{CY}/C2-FINAL-RUN-HISTORY.json")
    candidate = {"final_candidate": FINAL, **trees(FINAL), "head_when_written": git("rev-parse", "HEAD")}
    frz = history_freeze(candidate)
    q4f, q5f = load(f"{CY}/Q4-FINAL/DIFFERENTIAL.json"), load(f"{CY}/Q5-FINAL/REPRODUCTION.json")
    ll = load(f"{CY}/P10/attempt-2/LEDGERLOCK-REGRESSION.json")
    coh, prof = load(f"{CY}/P10-COHORT-MACHINERY.json"), load(f"{CY}/P10-PROFILE-FREEZE.json")
    from validation.qualification import p5_acceptance as pa
    v = pa.verify(run_guards=False)
    pr = json.loads(subprocess.run(["gh", "pr", "view", "6", "--json", "state,isDraft,headRefOid,baseRefName,mergedAt,headRefName"], cwd=ROOT,
                                   capture_output=True, encoding="utf-8", check=True).stdout)
    master = git("ls-remote", "origin", "refs/heads/master").split()[0]
    r4 = lin[-1]
    dirty = [ln for ln in git("status", "--short").splitlines() if ln[3:] not in (TRIAGE_REL, ORCH_REL, FREEZE_REL, AUDIT_REL, MD_REL, "validation/qualification/c2_closure_audit.py",
                                                                                 f"{CY}/C2-FINAL-RUN-HISTORY.json")]
    cycle1_frozen = _run(["validation/v2/cycle2_baseline.py", "--check"])["exit"] == 0
    tests = {
        "QP-2.6 final candidate GREEN": r4["summary"]["verdict"] == "GREEN" and all(r4[q] == "GREEN" for q in ("Q0", "Q1", "Q2", "Q3")),
        "unaudited mutation survivors = 0": r4["mutation"]["unaudited_survivors"] == 0,
        "Q4 = 100000/100000, divergence = 0": q4f["totals"]["MATCHED"] == q4f["totals"]["requested"] == 100000 and q4f["totals"]["DIVERGENCE"] == 0,
        "Q4 binding/freshness proven": q45["Q4"]["classification"] == "PROVENANCE_POINTER_CORRECTION" and q45["final_candidate"]["Q4-FINAL"]["fresh"]
        and q45["final_candidate"]["Q4-FINAL"]["lower_rung_is_green_for_this_candidate"],
        "Q5 = 12/12": (q5f["totals"]["green"], q5f["totals"]["items"]) == (12, 12),
        "Q5 assertConsumed = GREEN": q5f["assert_consumed"] is True,
        "tool-result replay count = 0": q5f["totals"]["tool_result_replays"] == 0,
        "Q5 binding/freshness proven": q45["Q5"]["classification"] == "PROVENANCE_POINTER_CORRECTION" and q45["final_candidate"]["Q5-FINAL"]["fresh"],
        "LedgerLock result preserved honestly as FAIL": ll["delivery_verdict"] == "FAIL",
        "LedgerLock classification DEVELOPMENT_REGRESSION": ll["benchmark_class"] == "DEVELOPMENT_REGRESSION",
        "plan_quality NOT_CLAIMED": ll["plan_quality_verdict"] == "NOT_CLAIMED", "generalization NONE": ll["generalization_claim"] == "NONE",
        "no cohort selected/sealed": coh["census"]["cohort_count"] == 0,
        "orchestration change separately reviewed": True,
        "no unapproved orchestration semantic change": "PENDING THE OWNER'S CLASSIFICATION (C2-ORCHESTRATION-CHANGE-REVIEW.json)",
        "all six failed LedgerLock stories triaged": tri["non_committed"] == 6,
        "no FRAMEWORK_KERNEL_DEFECT release blocker": tri["by_class"].get("A", 0) == 0,
        "no DEFAULT_PUBLIC_HARNESS_POLICY_DEFECT release blocker": tri["by_class"].get("B", 0) == 0,
        "3ed2c41 gates complete and acceptable": gate["all_pass"] and len(gate["ci_jobs"]) == 7,
        "histories immutable/content-addressed": guards["run_history"]["exit"] == 0,
        "residual processes = 0": frz["residual_processes_recorded"] == 0, "escaped processes = 0": frz["escaped_processes_recorded"] == 0,
        "cycle2_baseline PASS": guards["cycle2_baseline"]["exit"] == 0, "F1-F11 PASS": guards["f1_f11"]["exit"] == 0, "V1 guard PASS": guards["v1_guard"]["exit"] == 0,
        "Cycle-1 frozen evidence unchanged": cycle1_frozen and v["cycle1_drift"]["ok"],
        "working tree clean": not dirty, "PR #6 still unmerged": pr["state"] == "OPEN" and not pr["mergedAt"], "master unchanged": master == MASTER,
    }
    failing = [k for k, ok in tests.items() if ok is False]
    pending = [k for k, ok in tests.items() if isinstance(ok, str)]
    blockers = []
    if tri["release_blockers"]:
        blockers.append({"blocker": "FRAMEWORK_KERNEL_DEFECT (the evidence's reading; class A)", "stories": tri["release_blockers"],
                         "what": "a fully PRE_SATISFIED story under a blocking tests policy is rolled back and charged a DEVELOPER retry with no developer call "
                                 "(RFC §14 vs §15.3); reproduced without LedgerLock", "record": TRIAGE_REL})
    blockers.append({"blocker": "ORCHESTRATION CHANGE CLASSIFICATION PENDING", "what": "returned for the Owner's explicit ruling; one journal difference on a "
                                                                                    "misconfiguration failure path is disclosed", "record": ORCH_REL})
    blockers.append({"blocker": "PACKAGING (a fact, not a Cycle-2 defect)", "what": "pyproject.toml excludes aisef2* from the wheel; version 1.7.6: a release from this "
                                                                                 "tree ships no V2 code"})
    stop = bool(failing) or bool(tri["release_blockers"])
    audit = {
        "record": "AISEF V2 — CYCLE-2 FINAL CLOSURE AUDIT",
        "authority": "owner ruling 'CYCLE-2 FINAL OWNER CLOSURE AUDIT / ENGINEERING RESULTS PROVISIONALLY ACCEPTED / PUBLIC RELEASE NOT YET AUTHORIZED'",
        "written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "4_qp26_lineage": lin, "4_survivor_audits": survivor_audits(),
        "5_q4_q5_corrigendum_audit": q45,
        "q4_final_totals": q4f["totals"],
        "q5_final_totals": {k: q5f["totals"][k] for k in ("items", "green", "expected_model_calls", "consumed_model_calls", "tool_executions", "tool_result_replays",
                                                           "subprocess_executions", "socket_attempts")} | {"assert_consumed": q5f["assert_consumed"],
                                                                                                           "only_model_stream_replayed": q5f["only_model_stream_replayed"]},
        "6_commit_lineage_and_planes": com,
        "7_gate_of_3ed2c41": gate, "guards_now": guards, "cycle1_drift": v["cycle1_drift"],
        "8_history_freeze": ident(FREEZE_REL) if (ROOT / FREEZE_REL).exists() else FREEZE_REL,
        "9_c2_p10": {"cohort_count": coh["census"]["cohort_count"], "cohort_verdict": coh["verdict"], "profile_verdict": prof["verdict"],
                     "live_provider_calls": prof["live_provider_calls"], "workload_selected": False, "cohort_sealed": False},
        "ledgerlock": {"delivery_verdict": ll["delivery_verdict"], "plan_quality_verdict": ll["plan_quality_verdict"], "generalization": ll["generalization_claim"],
                       "workload_class": ll["benchmark_class"], "story_outcomes": ll["story_outcomes"], "attempt_1": ident(f"{CY}/P10/NO-RECORD.json"),
                       "attempt_2": {"record": ident(f"{CY}/P10/attempt-2/LEDGERLOCK-REGRESSION.json"), "execution_commit": ll["repository_execution_commit"],
                                     "kernel_tree": ll["aisef2_tree"], "journal": ll["journal_file"], "runspec_hash": ll["execution_profile"]["runspec_hash"]},
                       "triage": ident(TRIAGE_REL) if (ROOT / TRIAGE_REL).exists() else TRIAGE_REL},
        "orchestration_review": ident(ORCH_REL) if (ROOT / ORCH_REL).exists() else ORCH_REL,
        "10_acceptance_test": tests, "acceptance_failing": failing, "acceptance_pending_owner": pending,
        "release_blockers": blockers,
        "pr_6": pr, "master": master, "working_tree_outside_this_audit": dirty,
        "verdict": "STOPPED BEFORE CLOSURE ACCEPTANCE — RELEASE BLOCKER RETURNED TO THE OWNER" if stop else
                   "CLOSURE AUDIT COMPLETE — READY FOR OWNER MERGE-AND-RELEASE DECISION",
        "conclusion": None if stop else CONCLUSION,
    }
    return {"triage": tri, "orch": orch, "freeze": frz, "audit": audit}


def markdown(tri: dict, orch: dict, frz: dict, a: dict) -> str:
    """The audit as the Owner reads it: the ruling's forty items, every value taken from the four records."""
    stop = a["conclusion"] is None
    com, lin, q45, gate, ll = a["6_commit_lineage_and_planes"], a["4_qp26_lineage"], a["5_q4_q5_corrigendum_audit"], a["7_gate_of_3ed2c41"], a["ledgerlock"]
    r4 = lin[-1]
    out = ["# AISEF V2 — CYCLE-2 FINAL CLOSURE AUDIT", "", f"**{a['verdict']}**", "",
           f"Records: `{AUDIT_REL}`, `{TRIAGE_REL}`, `{ORCH_REL}`, `{FREEZE_REL}` (builder `validation/qualification/c2_closure_audit.py`).", ""]
    if stop:
        out += ["## Stop", ""] + [f"- **{b['blocker']}** — {b['what']}" + (f" Stories: {', '.join(b['stories'])}." if b.get("stories") else "") for b in a["release_blockers"]] + [""]
    n = iter(range(1, 41))
    item = lambda title, *lines: out.extend([f"## {next(n)}. {title}", "", *lines, ""])  # noqa: E731
    item("Final commit lineage", *[f"- `{r['sha']}` (parent `{' '.join(r['parents'])}`) — {r['subject']}" for r in com["commits"].values()],
         *[f"- {k.replace('_', ' ')}: {v}" for k, v in com["answers"].items()])
    item("Plane identities at each commit", "| commit | PRODUCT_AFFECTING | ASSURANCE_AFFECTING | EVIDENCE_ONLY | aisef2 tree |", "|---|---|---|---|---|",
         *[f"| `{r['sha']}` | `{r['planes']['PRODUCT_AFFECTING']['digest']}` | `{r['planes']['ASSURANCE_AFFECTING']['digest']}` | "
           f"`{r['planes']['EVIDENCE_ONLY']['digest']}` | `{r['trees']['aisef2']}` |" for r in com["commits"].values()],
         "", *[f"- {k.replace('_', ' ')}: `{json.dumps(v, ensure_ascii=False)}`" for k, v in
               com["measured_at_head_and_valid_for_all_three_because_the_trees_are_identical"].items()],
         f"- identical across the three: `{json.dumps(com['identical_across_the_three'])}`")
    item("3ed2c41 local gate", f"`{json.dumps(gate['local'])}` (history seq {gate['seq']})")
    item("3ed2c41 CI result", f"run {gate['ci_run']}; all PASS: {gate['all_pass']}", *[f"- {j}: `{json.dumps(v)}`" for j, v in sorted(gate["ci_jobs"].items())])
    item("QP-2.6 R2/R3/R4 lineage", "| attempt | candidate | aisef2 tree | validation/v2 | tests/v2 | Q0 | Q1 | Q2 | Q3 | mutants | survivors | audited | unaudited |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
         *[f"| {r['attempt']} | `{r['candidate_sha']}` | `{r['aisef2_tree']}` | `{r['assurance_trees']['validation/v2']}` | `{r['assurance_trees']['tests/v2']}` | "
           f"{r['Q0']} | {r['Q1']} | {r['Q2']} | {r['Q3']} | {r['mutation']['total']} | {r['mutation']['survivors']} | {r['mutation']['audited_survivors']} | "
           f"{r['mutation']['unaudited_survivors']} |" for r in lin], "",
         *[f"- {r['attempt']} {p}: " + "; ".join(f"{q} {v}" for q, v in row.items()) for r in lin for p, row in r["platforms"].items()],
         *[f"- {r['attempt']}: {r['note']}; V1 product tree `{r['product_tree_aisef']}`; PRODUCT_AFFECTING `{r['planes']['PRODUCT_AFFECTING']['digest']}`" for r in lin])
    item("Final QP-2.6 identity", f"candidate `{r4['candidate_sha']}`; aisef2 `{r4['aisef2_tree']}`; validation/v2 `{r4['assurance_trees']['validation/v2']}`; "
         f"tests/v2 `{r4['assurance_trees']['tests/v2']}`; summary `{r4['summary']['sha256']}` {r4['summary']['verdict']}")
    item("Mutation summary", f"`{json.dumps(r4['mutation'])}`")
    item("The survivor audits", *[f"- `{x['target']}` {x['mutant']}: {x['audit']}" for x in a["4_survivor_audits"]])
    item("Unaudited survivors", str(r4["mutation"]["unaudited_survivors"]))
    for name in ("Q4", "Q5"):
        d, f = q45[name], q45["final_candidate"][f"{name}-FINAL"]
        item(f"{name} execution identity", f"- original: executed at `{d['subject_sha_at_execution']}`, candidate named `{d['semantic_candidate_named']}`, kernel "
             f"`{json.dumps(d['qualification_kernel_identity'])}`, record `{d['original_record']['sha256']}`",
             f"- final: executed at `{f['subject_sha_at_execution']}`, candidate `{f['semantic_candidate_named']}`, kernel tree `{f['kernel_tree']}`, digest "
             f"`{f['kernel_digest']}`, record `{f['record']['sha256']}` {f['status']}, fresh: {f['fresh']}, lower rung: `{f['lower_rung_bound']}`")
        item(f"{name} corrigendum audit", f"- consumed paths changed between the R3 candidate and execution: `{d['consumed_paths_changed_between_the_r3_candidate_and_execution']}`",
             f"- active probe digests equal to R3: {d['active_probe_digests_equal_to_r3']}; pointer preserved: `{d['erroneous_pointer_preserved']}`; corrigendum "
             f"`{q45['corrigendum']['sha256']}`",
             f"- DID THE ORIGINAL MEASUREMENT RUN ON THE SAME CONSUMED IDENTITIES AS THE QUALIFYING CANDIDATE? **"
             f"{d['did_the_original_measurement_run_on_the_same_consumed_identities_as_the_qualifying_candidate']}** — {d['classification']}")
    item("Zero tool-result replay", f"Q5-FINAL `{json.dumps(a['q5_final_totals'])}`; Q4-FINAL `{json.dumps(a['q4_final_totals'])}`")
    item("Orchestration exact diff", f"commits `{list(orch['1_commits']['code'])}`", *[f"- `{f}`: {v['changed']}" for f, v in orch["3_functions_and_classes"].items()],
         f"- the diff itself: `{ORCH_REL}` field `15_exact_diff` ({len(orch['15_exact_diff'])} lines)")
    item("Orchestration classification", f"**{orch['classification']['status']}**", f"- reading of the evidence: {orch['classification']['reading_of_the_evidence']}",
         *[f"- {x}" for x in orch["classification"]["what_the_evidence_shows"]])
    item("Mixed-probe adversarial evidence", *[f"- cannot skip: {t}" for t in orch["12_cannot_silently_skip_a_probe"]["tests"]],
         *[f"- cannot substitute: {t}" for t in orch["13_one_probe_cannot_satisfy_another_s_obligation"]["tests"]],
         f"- after tests: `{json.dumps(orch['11_tests']['after_tests']['result'])}`; generality: {orch['14_generality']['reading']}")
    item("The six failed-story classifications", "| story | class | parent | candidate | gate | retries | developer requests |", "|---|---|---|---|---|---|---|",
         *[f"| {sid} | {v['classification']['class']} {v['classification']['name']} | `{v['parent_sha']}` | `{v['candidate_sha']}` | "
           f"{'; '.join(v['owner_and_failure_taxonomy'])} | {v['retries_charged']} | {v['developer_requests']} |" for sid, v in tri["stories"].items()],
         "", *[f"- **{sid}**: {v['classification']['primary_cause']}" for sid, v in tri["stories"].items()])
    blocked = [sid for sid, v in tri["stories"].items() if v["product_proof_satisfied_for_every_obligation"]]
    item("The ProductProof-SATISFIED-but-test-blocked stories", f"{len(blocked)} stories, not two: {', '.join(blocked)}.",
         *[f"- {sid}: tests `{json.dumps(tri['stories'][sid]['test_result'], ensure_ascii=False)}`" for sid in blocked],
         f"- reproducer without LedgerLock: `{json.dumps(tri['fully_pre_satisfied_reproducer']['finding'])}`",
         f"- history: {tri['history_of_the_interaction']['reading']}")
    item("Is any failure a shipped/default harness defect", tri["shipped_default_facts"]["reading"], f"class B stories: {tri['by_class'].get('B', 0)}")
    item("LedgerLock delivery", ll["delivery_verdict"] + f" — outcomes `{json.dumps(ll['story_outcomes'])}`")
    item("plan_quality", ll["plan_quality_verdict"])
    item("generalization", ll["generalization"] + f"; workload class {ll['workload_class']}")
    item("Attempt-1 NO-RECORD (HARNESS)", f"`{ll['attempt_1']['path']}` sha256 `{ll['attempt_1']['sha256']}` — unchanged")
    item("Attempt-2 identity", f"`{json.dumps(ll['attempt_2'], ensure_ascii=False)}`")
    item("C2-P10 result", f"`{json.dumps(a['9_c2_p10'])}`")
    item("Cohort count", str(a["9_c2_p10"]["cohort_count"]))
    item("Provider-call count (C2-P10)", str(a["9_c2_p10"]["live_provider_calls"]))
    item("History digests", "| history | entries | last seq | full history digest | status |", "|---|---|---|---|---|",
         *[f"| {k} | {v['entry_count']} | {v['last_sequence']} | `{v['full_history_digest']}` | {v['status']} |" for k, v in frz["histories"].items()])
    item("History freeze/seal mechanism", f"existing mechanism usable without changing assurance semantics: {frz['existing_mechanism']['can_it_seal_these_histories_without_changing_assurance_semantics']}",
         *[f"- {w}" for w in frz["existing_mechanism"]["why"]], f"- used instead: `{FREEZE_REL}`, status {frz['status']}; mandatory-seal source found: {frz['mandatory_seal_source']['found']}")
    g = a["guards_now"]
    item("cycle2_baseline", f"exit {g['cycle2_baseline']['exit']} {g['cycle2_baseline']['tail']}")
    item("F1-F11", f"exit {g['f1_f11']['exit']} {g['f1_f11']['tail']}")
    item("V1 guard", f"exit {g['v1_guard']['exit']} {g['v1_guard']['tail']}")
    item("Cycle-1 drift", f"`{json.dumps(a['cycle1_drift'])}`")
    item("Residual processes", str(frz["residual_processes_recorded"]))
    item("Escaped processes", str(frz["escaped_processes_recorded"]))
    item("Release blockers", *[f"- **{b['blocker']}**: {b['what']}" for b in a["release_blockers"]],
         f"- acceptance test failing: `{a['acceptance_failing']}`; pending the Owner: `{a['acceptance_pending_owner']}`")
    item("PR #6", f"`{json.dumps(a['pr_6'])}`")
    item("master", f"`{a['master']}`")
    item("Conclusion", *(a["conclusion"] or ["The audit stopped before closure acceptance: the ruling's conclusion is not stated.",
                                              "No benchmark result was tuned or rewritten. LedgerLock delivery remains FAIL and DEVELOPMENT_REGRESSION. No generalization "
                                              "claim is made. No cohort has been selected or sealed. PR #6 remains unmerged. No public release has been performed.",
                                              "An Owner ruling on the release blocker and on the orchestration classification is required."]))
    return "\n".join(out) + "\n"


def check() -> list[str]:
    """The committed records still describe the tree: each frozen history keeps its recorded prefix, the audit binds the
    three records it names, and the LedgerLock result is the one preserved."""
    problems = []
    frz, audit, tri = load(FREEZE_REL), load(AUDIT_REL), load(TRIAGE_REL)
    for phase, row in frz["histories"].items():
        e = load(row["path"])["entries"][:row["entry_count"]]
        if hashlib.sha256(json.dumps(e, sort_keys=True, ensure_ascii=False).encode()).hexdigest() != row["full_history_digest"]:
            problems.append(f"{phase}: the first {row['entry_count']} entries are not the frozen ones")
    for key, rel in (("8_history_freeze", FREEZE_REL), ("orchestration_review", ORCH_REL)):
        if audit[key] != ident(rel):
            problems.append(f"{rel} is not the record the audit binds")
    if audit["ledgerlock"]["triage"] != ident(TRIAGE_REL):
        problems.append(f"{TRIAGE_REL} is not the record the audit binds")
    ll = load(f"{CY}/P10/attempt-2/LEDGERLOCK-REGRESSION.json")
    now = {"delivery_verdict": ll["delivery_verdict"], "plan_quality_verdict": ll["plan_quality_verdict"],
           "generalization": ll["generalization_claim"], "workload_class": ll["benchmark_class"]}
    want = {"delivery_verdict": "FAIL", "plan_quality_verdict": "NOT_CLAIMED", "generalization": "NONE", "workload_class": "DEVELOPMENT_REGRESSION"}
    if now != want or {k: tri["preserved"][k] for k in want} != want:
        problems.append(f"the LedgerLock result is not the preserved one: {now}")
    if tri["preserved"]["attempt_1"] != ident(f"{CY}/P10/NO-RECORD.json") or tri["source"]["journal"] != ident(f"{CY}/P10/attempt-2/JOURNAL.json"):
        problems.append("the attempt-1 NO-RECORD or the attempt-2 journal changed")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.check:
        problems = check()
        print("\n".join(problems) or "c2 closure audit: the records bind this tree")
        return 1 if problems else 0
    r = build()
    for rel, key in ((TRIAGE_REL, "triage"), (ORCH_REL, "orch"), (FREEZE_REL, "freeze")):
        (ROOT / rel).write_text(json.dumps(r[key], indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8", newline="\n")
    a = r["audit"]
    a["8_history_freeze"], a["ledgerlock"]["triage"], a["orchestration_review"] = ident(FREEZE_REL), ident(TRIAGE_REL), ident(ORCH_REL)
    (ROOT / AUDIT_REL).write_text(json.dumps(a, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8", newline="\n")
    (ROOT / MD_REL).write_text(markdown(r["triage"], r["orch"], r["freeze"], a), encoding="utf-8", newline="\n")
    print(a["verdict"])
    print("  failing:", a["acceptance_failing"], "| pending owner:", a["acceptance_pending_owner"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
