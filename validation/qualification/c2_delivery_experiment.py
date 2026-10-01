"""DELIVERY EXPERIMENT 1 — the preregistration of ONE LedgerLock delivery run on the corrected kernel and the corrected
plan (owner ruling 'AISEF V2 — FINAL PLAN CORRECTION + DELIVERY RUN PREREGISTRATION / NO PROVIDER CALL', 2026-10-02).
PREPARED, NOT EXECUTED: the run needs a separate owner authorization with a hard budget.

    python -P validation/qualification/c2_delivery_experiment.py --write   # the preregistration record; measures readiness; no provider call
    python -P validation/qualification/c2_delivery_experiment.py --check   # the committed record is what this tree and this machine derive
    python -P validation/qualification/c2_delivery_experiment.py --check --after-run   # the same once the run's result is preserved
    python -P validation/qualification/c2_delivery_experiment.py --provider-preflight --out <json>   # PART OF THE PAID RUN: calls the provider

What is fixed before the run, and re-derived and compared before any model call (`require_preregistered`): the kernel
commit and tree, the harness files, the workload baseline and requirements hash, the corrected plan hash, three total
developer attempts, ONE fixed model route for the developer and the reviewer (never a routing alias — the client is
given the route explicitly and its small model is the same route), the capability identities with their grades and
enforcement, the RunSpec hash, the hard ceilings (turns per session, input and output tokens over the run), where the
run's git objects are preserved, and the final evaluation: all 59 ProductProofSpecs and the V1 independent acceptance
oracle on the final main. The run itself is validation/qualification/c2_p9_run.sh with PROFILE=delivery-experiment-1.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import io
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import c2_p9  # noqa: E402
from validation.qualification import c2_plan_correction as pc  # noqa: E402

C, P10 = c2_p9.C, c2_p9.P10
OUT_REL = "closure-evidence/v2/cycle2/DELIVERY-EXPERIMENT-1-PREREGISTRATION.json"
AUTHORITY = ("owner ruling 'AISEF V2 — FINAL PLAN CORRECTION + DELIVERY RUN PREREGISTRATION / NO PROVIDER CALL' (2026-10-02); "
             "the run itself is NOT authorized by it")
ORACLE_REL = "closure-evidence/hardening/w1/oracle/test_oracle.py"
ORACLE_INDEPENDENCE_REL = "closure-evidence/hardening/w1/ORACLE-INDEPENDENCE.json"
ORACLE_REFERENCE_REL = "closure-evidence/hardening/w1/oracle/reference"
V1_PREFLIGHT_REL = "closure-evidence/hardening/w1/provider_preflight.py"
#: the last measurement of what answers on the route (2026-09-20, the V1 baseline profile on the same plan base)
ROUTE_EVIDENCE_REL = "closure-evidence/hardening/w1/profiles/PROVIDER-PREFLIGHT-PROFILE-W1V2.1-OC-DEEPSEEKV4PRO-T80-RO.json"
#: QP-2.9 attempt 2, the measurement the token ceilings are derived from
MEASURED_REL = "closure-evidence/v2/cycle2/P10/attempt-2/LEDGERLOCK-REGRESSION.json"
EXPERIMENT = {
    "id": c2_p9.EXPERIMENT,
    "attempt": 3,                                       # the next attempt directory of closure-evidence/v2/cycle2/P10
    "kernel_commit": "d427299376d7af48d3dd6d86242bf5def6a43003",    # K-PRESAT-001
    "kernel_tree": "4fe9ccaab17d7cac03b5e578ee1ecb57d04b8160",
    "harness_includes": "7630dbe5d0aa7f873e26a573ce2b9962bb0c72c2",
    # the route of the V1 baseline profile PROFILE-W1V2.1-OC-DEEPSEEKV4PRO-T80-RO (same plan base, max_turns 80, max_retries 2)
    "route": "9router/ds/deepseek-v4-pro", "route_kind": "FIXED_MODEL", "resolved_model": "deepseek-v4-pro",
    "model_limit": {"context": 200000, "output": 32768},
    "max_turns": 80,
    "max_input_tokens": 250_000_000,
    "max_output_tokens": 1_000_000,
}
HARNESS_FILES = ("validation/qualification/c2_p9.py", "validation/qualification/c2_p9_run.sh",
                 "validation/qualification/c2_delivery_experiment.py", "validation/qualification/c2_plan_correction.py")


def fixed() -> dict:
    """What the RunSpec binds of the experiment (c2_p9.runspec_inputs)."""
    return {**EXPERIMENT, "developer_timeout_s": c2_p9.DEV_TIMEOUT_S, "reviewer_timeout_s": c2_p9.REVIEW_TIMEOUT_S}


# ------------------------------------------------------------------------------------------------ the fixed model

def client_config() -> dict:
    """The client configuration laid over the operator's own for every session of the run: the model AND the small model
    are the one fixed route (nothing can fall to a routing alias), and the route's model is declared to the client."""
    provider, model = EXPERIMENT["route"].split("/", 1)
    return {"model": EXPERIMENT["route"], "small_model": EXPERIMENT["route"],
            "provider": {provider: {"models": {model: {"name": model, "limit": EXPERIMENT["model_limit"]}}}}}


def client_env() -> dict:
    return {**os.environ, "OPENCODE_CONFIG_CONTENT": json.dumps(client_config(), sort_keys=True)}


def client_resolution() -> dict:
    """What the client resolves under `client_env`, read from `opencode debug config` — local, no request is made. Only
    the two model fields and the declaration are taken from its output (which holds the operator's key): nothing else
    of it is kept, printed or recorded."""
    exe = shutil.which("opencode")
    if not exe:
        return {"client_present": False}
    with tempfile.TemporaryDirectory(prefix="aisef2-dx-client-") as d:
        out = subprocess.run([exe, "debug", "config"], capture_output=True, encoding="utf-8", errors="replace", env=client_env(), cwd=d,
                             timeout=120).stdout
    top = {k: (m.group(1) if (m := re.search(rf'^  "{k}": "([^"]*)"', out, re.M)) else None) for k in ("model", "small_model")}
    return {"client_present": True, **top, "route_model_declared": f'"{EXPERIMENT["route"].split("/", 1)[1]}"' in out,
            "resolves_to_the_fixed_route": top["model"] == top["small_model"] == EXPERIMENT["route"]}


def preflight_problems(rec: dict) -> list[str]:
    """Why a provider preflight record does not show the preregistered model answering on the route."""
    s = rec.get("summary_for_identity") or {}
    out = [] if rec.get("pass") is True else ["the preflight did not pass"]
    if rec.get("route") != EXPERIMENT["route"] or s.get("route_kind") != EXPERIMENT["route_kind"]:
        out.append(f"route {rec.get('route')} kind {s.get('route_kind')}: not the fixed route {EXPERIMENT['route']}")
    if s.get("resolved_model") != EXPERIMENT["resolved_model"]:
        out.append(f"answered by {s.get('resolved_model')}, not {EXPERIMENT['resolved_model']}")
    return out


def provider_preflight(out: pathlib.Path) -> list[str]:
    """PART OF THE PAID RUN — this calls the provider. The V1 provider preflight, unchanged, on the fixed route: the
    router lists it as a fixed model, three chat probes answer with one constant model identity, two tool smokes work."""
    out.parent.mkdir(parents=True, exist_ok=True)
    limit = EXPERIMENT["model_limit"]
    subprocess.run([sys.executable, str(ROOT / V1_PREFLIGHT_REL), EXPERIMENT["route"], "--probes", "3", "--smokes", "2",
                    "--context", str(limit["context"]), "--output", str(limit["output"]), "--out", str(out)], cwd=ROOT)
    if not out.exists():
        return ["the preflight left no record"]
    return preflight_problems(json.loads(out.read_text(encoding="utf-8")))


# -------------------------------------------------------------------------------- the final evaluation of a result

def materialise(git_dir: pathlib.Path, sha: str, dest: pathlib.Path) -> pathlib.Path:
    """The tree of `sha` from the preserved git directory, as plain files under `dest` (the copy is only read)."""
    data = subprocess.run(["git", "--git-dir", str(git_dir), "archive", "--format=tar", sha], capture_output=True, check=True).stdout
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(dest, filter="data")
    return dest


def final_proof(tree: pathlib.Path, sha: str) -> dict:
    """Every one of the 59 ProductProofSpecs (compiled under the persisted real approvals) put to its own probe on
    `tree` — whatever story owned it, whatever the run's journal says."""
    from aisef2.arch.enums import ContractSatisfaction, Enforcement, ProbeExecutionStatus
    from aisef2.probe import catalog
    from aisef2.probe.protocol import ExecutionEnv, RevisionRef, bound_result, run_probe
    from aisef2.product.outcome import contract_satisfaction
    env, at, rows = ExecutionEnv(sys.executable, 60, Enforcement.PARTIAL), RevisionRef(sha, str(tree.resolve())), []
    for sid, spec in c2_p9._compiled().items():
        probe = next(e for e in catalog.CATALOG if e.probe_id == spec.probe_id).factory()
        result = bound_result(run_probe(probe, spec, at, env), spec=spec, revision=at.sha, enforcement=probe.enforcement())
        executed = result.status is ProbeExecutionStatus.EXECUTED
        rows.append({"spec": sid, "product_proof_spec_id": spec.id, "semantic_hash": spec.semantic_hash, "probe_id": spec.probe_id,
                     "status": result.status.value, "verdict": result.behavior_verdict.value if executed else None,
                     "candidate_expectation": spec.candidate_expectation.value,
                     "satisfaction": contract_satisfaction(result, spec).value if executed else None,
                     "detail": None if executed else str(getattr(result, "detail", ""))[:300]})
    return {"revision": sha, "total": len(rows), "satisfied": sum(1 for r in rows if r["satisfaction"] == ContractSatisfaction.SATISFIED.value),
            "not_satisfied": [r["spec"] for r in rows if r["satisfaction"] != ContractSatisfaction.SATISFIED.value], "specs": rows}


def oracle_identity() -> dict:
    pinned = json.loads((ROOT / ORACLE_INDEPENDENCE_REL).read_text(encoding="utf-8"))

    def version(name: str) -> str | None:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return None
    now = C.lf_sha(ROOT / ORACLE_REL)
    return {"path": ORACLE_REL, "sha256": now, "sha256_pinned": pinned["oracle"]["sha256"], "unchanged_since_calibration": now == pinned["oracle"]["sha256"],
            "independence_verdict": pinned["verdict"],
            "interpreter": {"python": platform.python_version(), "pytest": version("pytest"), "coverage": version("coverage")},
            "interpreter_note": "the oracle venv of the V1 freeze (pytest 9.1.1, coverage 7.16.1) is no longer on this machine; the oracle "
                                "runs under the harness interpreter, whose versions are recorded here"}


def parse_oracle(stdout: str) -> dict:
    """Per-test outcomes of `pytest -v`, reconciled against pytest's own totals (the V1 driver's rule, SS-79): a parse
    that does not account for every test pytest counted is incomplete, never quietly believed."""
    res = {m.group(1).split("::", 1)[1]: m.group(2)
           for m in re.finditer(r"^(\S+::\S+?)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b", stdout, re.M)}
    tail = stdout.strip().splitlines()[-1] if stdout.strip() else ""
    counted = sum(int(n) for n, _ in re.findall(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed)", tail))
    return {"results": res, "total": len(res), "passed": sum(1 for v in res.values() if v == "PASSED"),
            "not_passed": sorted(k for k, v in res.items() if v != "PASSED"), "complete": bool(res) and counted == len(res)}


def v1_oracle(tree: pathlib.Path, out_dir: pathlib.Path | None = None) -> dict:
    """The V1 independent acceptance oracle, unchanged, on `tree` — the V1 driver's own invocation."""
    with tempfile.TemporaryDirectory(prefix="aisef2-dx-oracle-") as d:
        obs = pathlib.Path(d) / "observations.jsonl"
        env = {**os.environ, "AISEF_W1_PROJECT": str(tree), "AISEF_W1_ORACLE_OBSERVATIONS": str(obs), "PYTHONDONTWRITEBYTECODE": "1"}
        r = subprocess.run([sys.executable, "-m", "pytest", str(ROOT / ORACLE_REL), "-v", "-rA", "-p", "no:cacheprovider", "--tb=short"],
                           capture_output=True, encoding="utf-8", errors="replace", env=env, cwd=d, timeout=1800)
        observations = obs.read_text(encoding="utf-8").splitlines() if obs.exists() else []
    if out_dir is not None:
        (out_dir / "V1-ORACLE-OUTPUT.txt").write_text(r.stdout + "\n--- stderr ---\n" + r.stderr, encoding="utf-8")
    return {**oracle_identity(), "exit": r.returncode, **parse_oracle(r.stdout), "observations": [json.loads(x) for x in observations]}


def evaluate(git_dir: pathlib.Path, final: str, out_dir: pathlib.Path) -> dict:
    """The final main of a finished run, from its preserved git directory: all 59 specs, then the V1 oracle."""
    with tempfile.TemporaryDirectory(prefix="aisef2-dx-final-") as d:
        proof = final_proof(materialise(git_dir, final, pathlib.Path(d) / "proof"), final)
        oracle = v1_oracle(materialise(git_dir, final, pathlib.Path(d) / "oracle"), out_dir)
    return {"record": "AISEF V2 — DELIVERY EXPERIMENT 1: the final main evaluated independently of the run's journal",
            "final_main": final, "preserved_git_dir": str(git_dir), "v2_final_proof": proof, "v1_oracle": oracle, "at": C.now()}


def readiness() -> dict:
    """Measured, without a provider and without LedgerLock: both evaluations run end to end on a reference
    implementation written from the requirements — the P5 reference fixture for the 59 specs, the oracle's own
    calibration reference for the oracle. It shows the evaluations can run here; it says nothing about a delivery."""
    from aisef2.probe.calibration import FIXTURE_REVISION
    from validation.qualification import p5_falsifiability as pf
    with tempfile.TemporaryDirectory(prefix="aisef2-dx-ready-") as d:
        proof = final_proof(pf.build_tree(None, pathlib.Path(d)), FIXTURE_REVISION)
        oracle = v1_oracle(pathlib.Path(shutil.copytree(ROOT / ORACLE_REFERENCE_REL, pathlib.Path(d) / "oracle-reference")))
    return {"v2_final_proof_on_the_p5_reference_fixture": {k: proof[k] for k in ("total", "satisfied", "not_satisfied")},
            "v1_oracle_on_its_calibration_reference": {k: oracle[k] for k in ("exit", "total", "passed", "not_passed", "complete", "interpreter")}}


# ------------------------------------------------------------------------------------------- the preregistration

def _is_ancestor(commit: str) -> bool:
    return subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "HEAD"], capture_output=True).returncode == 0


def record(ready: dict) -> dict:
    from aisef2.runtime.runspec import resolve
    plan = pc.corrected_plan()
    oc = P10.opencode_identity()
    caps, layers, kernel = c2_p9.runspec_inputs(plan, c2_p9.EXPERIMENT, oc, fixed())
    spec = resolve(caps, layers, plan.baseline)
    measured = json.loads((ROOT / MEASURED_REL).read_text(encoding="utf-8"))["model_sessions"]
    turns = sum(s["turns"] for s in measured["sessions"])
    stories = len({o.story_id for o in plan.obligations})
    attempts = c2_p9.PROFILES[c2_p9.EXPERIMENT]["DEVELOPER"] + 1
    preserve_to = c2_p9.preserve_root() / f"attempt-{EXPERIMENT['attempt']}.git"
    evidence = json.loads((ROOT / ROUTE_EVIDENCE_REL).read_text(encoding="utf-8"))
    body = {
        "record": "AISEF V2 — DELIVERY EXPERIMENT 1: PREREGISTRATION OF ONE LEDGERLOCK DELIVERY RUN (prepared, not executed)",
        "authority": AUTHORITY,
        "status": "PREPARED — NOT STARTED. The run requires a separate owner authorization with a hard budget.",
        "run_authorized": False, "provider_calls_made_preparing_this": 0,
        "kernel": {"commit": EXPERIMENT["kernel_commit"], "tree": EXPERIMENT["kernel_tree"], "head_tree": C.git("rev-parse", "HEAD:aisef2"),
                   "tree_of_the_commit": C.git("rev-parse", f"{EXPERIMENT['kernel_commit']}:aisef2"),
                   "commit_is_an_ancestor_of_head": _is_ancestor(EXPERIMENT["kernel_commit"]), "digest": kernel},
        "harness": {"includes": EXPERIMENT["harness_includes"], "included": _is_ancestor(EXPERIMENT["harness_includes"]),
                    "files": [{"path": rel, "sha256": C.lf_sha(ROOT / rel)} for rel in HARNESS_FILES],
                    "run_command": f"ATTEMPT={EXPERIMENT['attempt']} PROFILE={EXPERIMENT['id']} validation/qualification/c2_p9_run.sh"},
        "workload": {"id": "LedgerLock", "benchmark_class": P10.BENCHMARK_CLASS, "generalization_claim": P10.GENERALIZATION_CLAIM,
                     "start_sha": plan.baseline, "requirements_sha256": P10.REQUIREMENTS_SHA256, "repository": P10.ledgerlock_baseline()},
        "plan": {"id": plan.id, "plan_hash": plan.plan_hash, "stories": stories, "obligations": len(plan.obligations),
                 "execution_order": c2_p9.order(plan, pc.build()["graph"]),
                 "correction": {"path": pc.OUT_REL, "sha256": C.lf_sha(ROOT / pc.OUT_REL), "check": pc.check()}},
        "profile": {"name": EXPERIMENT["id"], "limits": c2_p9.PROFILES[c2_p9.EXPERIMENT], "developer_attempts_per_story": attempts,
                    "tests_policy": "TestsPolicy(blocking=True), as attempts 1 and 2"},
        "model": {"route": EXPERIMENT["route"], "route_kind": EXPERIMENT["route_kind"], "resolved_model": EXPERIMENT["resolved_model"],
                  "dynamic_alias": False, "roles": {"developer": EXPERIMENT["route"], "reviewer": EXPERIMENT["route"]},
                  "why_this_route": "the route of the V1 baseline profile PROFILE-W1V2.1-OC-DEEPSEEKV4PRO-T80-RO (same plan base 136a68dc, "
                                    "max_turns 80, max_retries 2): the comparison the experiment exists for",
                  "client": oc, "client_configuration_overlay": client_config(), "client_resolution_measured_locally": client_resolution(),
                  "what_answers_on_the_route": {"last_measured": {"path": ROUTE_EVIDENCE_REL, "sha256": C.lf_sha(ROOT / ROUTE_EVIDENCE_REL),
                                                                   "summary": evidence.get("summary_for_identity")},
                                                "not_measured_now": "no provider call was permitted while preparing",
                                                "at_run_start": f"{V1_PREFLIGHT_REL} on the route (3 chat probes, 2 tool smokes): the run does not "
                                                                "start unless it passes and the answering model is the resolved model; "
                                                                "repeated after the run and recorded"}},
        "capabilities": [c.resolved() for c in spec.capabilities],
        "identity_grade": {"aggregate_min_grade": spec.aggregate_min_grade.value,
                           "by_capability": {c.name: c.grade.value for c in spec.capabilities},
                           "note": "developer and reviewer are OPAQUE: a fixed route is declared and given to the client, but ATTESTED binds a "
                                   "preflight fingerprint, which is a provider call and so is not part of an identity fixed beforehand"},
        "enforcement": {"by_capability": {c.name: c.enforcement.value for c in spec.capabilities}, "probe_execution_env": "PARTIAL"},
        "runspec_hash": spec.runspec_hash,
        "runspec_settings": json.loads(json.dumps(layers)),
        "ceilings": {"max_turns_per_session": EXPERIMENT["max_turns"], "max_input_tokens_over_the_run": EXPERIMENT["max_input_tokens"],
                     "max_output_tokens_over_the_run": EXPERIMENT["max_output_tokens"],
                     "developer_session_timeout_s": c2_p9.DEV_TIMEOUT_S, "reviewer_session_timeout_s": c2_p9.REVIEW_TIMEOUT_S,
                     "counted": "from the client's event stream while a session runs, every 5 s: a turn is a finished step; input counts "
                                "prompt and cached tokens, output counts completion and reasoning tokens",
                     "at_the_turn_cap": "the session's process range is released; what it changed is committed as the candidate and judged "
                                        "by the proofs (as a timed-out session is)",
                     "at_a_token_ceiling": "the session that reached it is released; no later session starts — the kernel is answered with "
                                           "a provider refusal (owner PROVIDER, never a developer failure) and later stories are NOT_RUN",
                     "derivation": {"measured": MEASURED_REL, "sessions": measured["count"], "turns": turns, "tokens": measured["tokens"],
                                    "input_per_turn": round(measured["tokens"]["input"] / turns), "output_per_turn": round(measured["tokens"]["output"] / turns),
                                    "bound": f"{stories} stories x {attempts} developer sessions x {EXPERIMENT['max_turns']} turns, and as many "
                                             "reviewer sessions at the 30 turns measured at most, at the measured tokens per turn: about 227M "
                                             "input and 0.6M output; the ceilings sit just above"},
                     "provider_preflight_is_outside_the_ceilings": "3 chat probes of 16 output tokens and 2 tool smokes, before and after"},
        "preservation": {"root": str(c2_p9.preserve_root()), "git_dir": str(preserve_to), "free": not preserve_to.exists(),
                         "rule": "the run repository's whole git directory is copied there and final main and every candidate pinned under "
                                 "refs/qp-2.9/ before the temporary directory is removed; it is not removed unless they are held"},
        "final_evaluation": {"v2_final_proof": "all 59 ProductProofSpecs, each on its own probe, on the final main (FINAL-EVALUATION.json)",
                             "v1_oracle": oracle_identity(), "readiness_measured_without_a_provider": ready},
        "frozen_during_the_run": ["the run script refuses a dirty tree and a kernel tree other than the preregistered one, before and after",
                                  "this preregistration is re-derived and compared before any model call, and again after the run",
                                  "HEAD must be the same commit after the run as before it",
                                  "the plan is the corrected plan by hash: no re-planning, no story split"],
    }
    body["problems"] = problems(body)
    body["verdict"] = "PREREGISTERED — READY FOR AN OWNER DECISION; NOT AUTHORIZED" if not body["problems"] else "PROBLEMS"
    return json.loads(json.dumps(body))


def problems(body: dict) -> list[str]:
    out = []
    k = body["kernel"]
    if not (k["tree"] == k["head_tree"] == k["tree_of_the_commit"] and k["commit_is_an_ancestor_of_head"]):
        out.append("the kernel of this tree is not the preregistered kernel commit's")
    if not body["harness"]["included"]:
        out.append("the harness commit is not in this history")
    w = body["workload"]["repository"]
    if not (w.get("present") and w.get("requirements_match_frozen") and w.get("baseline") == body["workload"]["start_sha"]):
        out.append("the workload is not at its baseline with the frozen requirements")
    out += [f"plan correction: {p}" for p in body["plan"]["correction"]["check"]]
    if body["profile"]["developer_attempts_per_story"] != 3:
        out.append("not three developer attempts")
    r = body["model"]["client_resolution_measured_locally"]
    if not (r.get("client_present") and r.get("resolves_to_the_fixed_route") and r.get("route_model_declared")):
        out.append("the client does not resolve the fixed route")
    if (body["model"]["what_answers_on_the_route"]["last_measured"]["summary"] or {}).get("resolved_model") != body["model"]["resolved_model"]:
        out.append("the route's last measurement names another model")
    if not body["preservation"]["free"]:
        out.append(TAKEN)
    o, ready = body["final_evaluation"]["v1_oracle"], body["final_evaluation"]["readiness_measured_without_a_provider"]
    if not (o["unchanged_since_calibration"] and o["independence_verdict"] == "PASS" and o["interpreter"]["pytest"] and o["interpreter"]["coverage"]):
        out.append("the V1 oracle is not the calibrated one, or cannot run here")
    p, v = ready["v2_final_proof_on_the_p5_reference_fixture"], ready["v1_oracle_on_its_calibration_reference"]
    if (p["total"], p["satisfied"]) != (59, 59):
        out.append(f"readiness: {p['satisfied']}/{p['total']} specs satisfied on the reference fixture")
    if not (v["complete"] and v["total"] and v["passed"] == v["total"]):
        out.append(f"readiness: the oracle passed {v['passed']}/{v['total']} on its calibration reference")
    return out


TAKEN = "the preservation path is taken"


def check(after_run: bool = False) -> list[str]:
    """The committed preregistration against this tree and this machine; its readiness section is taken as measured.
    After the run its preservation path holds the run's result, which is then no difference and no problem."""
    path = ROOT / OUT_REL
    if not path.exists():
        return [f"{OUT_REL} does not exist"]
    committed = json.loads(path.read_text(encoding="utf-8"))
    rec = record(committed["final_evaluation"]["readiness_measured_without_a_provider"])
    if after_run:
        rec["preservation"], rec["problems"] = committed["preservation"], [p for p in rec["problems"] if p != TAKEN]
        rec["verdict"] = committed["verdict"] if not rec["problems"] else rec["verdict"]
    return list(rec["problems"]) + ([] if rec == committed else [f"{OUT_REL} is not what this tree and this machine derive"])


def require_preregistered() -> dict:
    """What a run under the experiment's profile executes with — or a refusal, before any model call."""
    found = check()
    if found:
        raise SystemExit("REFUSED: the delivery experiment is not as preregistered: " + "; ".join(found))
    committed = json.loads((ROOT / OUT_REL).read_text(encoding="utf-8"))
    return {**fixed(), "plan": pc.corrected_plan(), "authority": AUTHORITY, "runspec_hash": committed["runspec_hash"],
            "preregistration": {"path": OUT_REL, "sha256": C.lf_sha(ROOT / OUT_REL)}, "plan_correction": committed["plan"]["correction"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--provider-preflight", action="store_true", help="PART OF THE PAID RUN: calls the provider")
    ap.add_argument("--out")
    ap.add_argument("--after-run", action="store_true")
    a = ap.parse_args(argv)
    if a.provider_preflight:
        found = provider_preflight(pathlib.Path(a.out).resolve()) if a.out else ["--out is required"]
        print("\n".join(found) if found else f"the fixed route answers as {EXPERIMENT['resolved_model']}")
        return 1 if found else 0
    if a.write:
        rec = record(readiness())
        if rec["problems"]:
            raise SystemExit("refused: " + "; ".join(rec["problems"]))
        (ROOT / OUT_REL).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(f"{OUT_REL}: {rec['verdict']}; runspec {rec['runspec_hash']}; plan {rec['plan']['plan_hash']}")
        return 0
    found = check(a.after_run)
    print("\n".join(found) if found else "PASS")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
