"""QP-2.9 — LedgerLock as a DEVELOPMENT / REGRESSION benchmark on the Cycle-2 candidate (owner rulings 2026-09-30 A
and B; cycle2-manifest QP-2.9; RFC §28-§30).

    python -P validation/qualification/c2_p9.py --run      # -> closure-evidence/v2/cycle2/P10/LEDGERLOCK-REGRESSION.json

The owner-approved PLAN-V2.2 (plan 27b679d9…, the 59 contracts under the 59 real approvals) executed as it is — no
re-planning, no story split — through the authoritative path (story_runner.run_story), every obligation proved by the
probe its ProductProofSpec names (C2-ORCHESTRATION-CONFORMANCE-REPAIR). The execution profile is P10's, recorded and
accepted in Cycle 1 (p10.runspec_for): a live developer and reviewer over OpenCode on the declared route (OPAQUE: a
routing alias is never attested), ruff as an informational scanner, and P10's budget limits. The LedgerLock
repository is never written: its baseline commit is cloned into a temporary directory.

Recorder: p10's (the manifest's "p10.py recorder reused"): DEVELOPMENT_REGRESSION, generalization NONE, delivery and
plan quality separately, plan_quality_verdict NOT_CLAIMED (DECISION-5: no PlanQualityPolicy is preregistered), the
raw plan-quality metrics, the mechanical prohibitions executed. A model review never blocks (§25): the reviewer's
findings carry no corroboration.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import common as C  # noqa: E402
from validation.qualification import p10 as P10  # noqa: E402

OUT_REL = "closure-evidence/v2/cycle2/P10"
SESSIONS = "sessions"
HISTORY_REL = "closure-evidence/v2/cycle2/C2-P9-RUN-HISTORY.json"
DEV_TIMEOUT_S = 2400.0
REVIEW_TIMEOUT_S = 900.0
#: P10's limits (p10.runspec_for), the accepted Cycle-1 execution profile
LIMITS = {"DEVELOPER": 1, "PLAN": 0, "ENVIRONMENT": 1, "PROVIDER": 1, "INTEGRATION": 0, "REVIEW": 1, "SECURITY": 1}
PROJECT = frozenset({"ledgerlock", "tests"})
SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{12,}|api[_-]?key\"?\s*[:=]\s*\"[^\"]{8,})", re.I)


def _sha(b: bytes) -> str:
    import hashlib
    return hashlib.sha256(b).hexdigest()


def test_path(story: str) -> str:
    return f"tests/test_{story.lower().replace('-', '_')}.py"


def epics_section(epics: str, story: str) -> str:
    """The V1 story's own section of _bmad-output/epics.md at the plan commit (STORY-01-05 -> '### Story 1.5:')."""
    e, n = (int(x) for x in story.split("-")[1:])
    m = re.search(rf"^### Story {e}\.{n}:.*?(?=^### |^## |\Z)", epics, re.M | re.S)
    return m.group(0).strip() if m else ""


def prompts(plan, epics: str) -> tuple[dict[str, str], dict[str, str]]:
    """The developer's task per plan story: the requirements (authoritative, in the repository), the story's epics
    section, and the requirement clause of each obligation it must deliver or preserve. The specs' probes, stimuli and
    expectations are not shown: the proof is independent of the developer."""
    from validation.qualification import p10_contracts as aid
    graph = aid.story_graph()
    specs = {s.id: sid for sid, s in _compiled().items()}
    out, clauses = {}, {}
    for story in sorted({o.story_id for o in plan.obligations}):
        lines = []
        for o in (o for o in plan.obligations if o.story_id == story):
            t = aid.SPECS[specs[o.product_proof_spec_id]]
            lines.append(f"- [{o.role.value}] {t['requirement']}: {t['clause']}")
        prior = [s for s in sorted(graph.get(story, ())) if not any(o.story_id == s for o in plan.obligations)]
        clauses[story] = "\n".join(lines)
        prior_text = "\n\n".join(epics_section(epics, s) for s in prior)
        out[story] = (
            f"You are the developer of LedgerLock story {story}. LedgerLock is a small Python library and CLI; "
            "docs/requirements.md in this repository is the authoritative specification. Implement this story in this "
            "repository (the package `ledgerlock/`, Python standard library only), working only inside this directory.\n\n"
            f"The story:\n\n{epics_section(epics, story)}\n\n"
            + (f"Earlier stories it builds on that no other step of this run delivers (implement what is missing):\n\n{prior_text}\n\n" if prior else "")
            + "When you finish, each of the following requirement clauses is verified independently against the "
              "requirements (INTRODUCE: this story makes it true; PRESERVE: it must stay true):\n"
            + "\n".join(lines)
            + f"\n\nWrite this story's unit tests in {test_path(story)} (unittest; `python -m unittest {test_path(story)}` "
              "must pass from the repository root) and keep every earlier test passing. Do not edit docs/requirements.md. "
              "Do not run git commit; the harness commits your working tree.")
    return out, clauses


_COMPILED: dict = {}


def _compiled() -> dict:
    """The 59 specs compiled under the persisted real approvals (C2-P5 acceptance), keyed by spec id."""
    if not _COMPILED:
        from aisef2.probe import catalog
        from aisef2.product.compiler import ProbeRef, compile_spec
        from validation.qualification import p5_acceptance as pa
        aid = pa._aid()
        reqs, real = aid.requirements(), pa.load_approvals()
        refs = {k: ProbeRef(e.probe_id, e.probe_digest) for k, e in catalog.active().items()}
        _COMPILED.update({sid: compile_spec(c, requirements=reqs, approvals=real, probes=refs) for sid, c in pa.contracts().items()})
    return _COMPILED


# --------------------------------------------------------------------------------------------- the live capabilities

def opencode_session(name: str, prompt: str, cwd: str, log: pathlib.Path, timeout_s: float) -> dict:
    """One `opencode run --format json` session inside a V2 process range (the kernel's own OS-owned range: every
    process it starts ends with it); the event stream goes to `log`."""
    from aisef2.runtime.process_range import ProcessRange
    exe = shutil.which("opencode")
    started = time.monotonic()
    with log.open("w", encoding="utf-8") as fh:
        r = ProcessRange(name, [exe, "run", "--format", "json", "--dir", cwd, prompt], cwd=cwd, output=fh)
        r.start()
        try:
            code = r.wait(timeout_s)
        finally:
            r.release()
    text, error, turns, tokens = [], None, 0, {"input": 0, "output": 0}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        part = ev.get("part") or {}
        if ev.get("type") == "text":
            text.append(str(part.get("text") or ""))
        elif ev.get("type") == "error":
            info = ev.get("error") or {}
            data = info.get("data") or {}
            error = f"{info.get('name') or 'error'}: {str(data.get('message') or '')[:200]}" + (
                f" (HTTP {data['statusCode']})" if data.get("statusCode") else "")
        elif ev.get("type") == "step_finish":
            turns += 1
            tk = part.get("tokens") or {}
            tokens["input"] += int(tk.get("input") or 0)
            tokens["output"] += int(tk.get("output") or 0)
    return {"exit": code, "timed_out": code is None, "error": error, "text": "".join(text), "turns": turns, "tokens": tokens,
            "seconds": round(time.monotonic() - started, 1), "log": log.name, "log_sha256": _sha(log.read_bytes())}


class OpenCodeDeveloper:
    def __init__(self, run, prompts: dict[str, str], logs: pathlib.Path) -> None:
        self.run, self.prompts, self.logs, self.sessions = run, prompts, logs, []

    def implement(self, story_id: str, criteria: tuple[str, ...], checkout: str):
        from aisef2.journal.format2 import OperationOutcome as O
        from aisef2.orchestrate.adapters import Implemented, ProviderOutage
        from aisef2.orchestrate.workspace import commit_all, git
        from validation.qualification.q5 import _story_context
        attempt, prior = _story_context(self.run, story_id)
        prompt = self.prompts[story_id] + (f"\n\nA previous attempt of this story was rolled back; the kernel observed: {prior}. "
                                           "Fix the implementation." if prior else "")
        parent = git(checkout, "rev-parse", "HEAD").stdout.strip()
        s = opencode_session(f"developer {story_id}", prompt, checkout, self.logs / f"{story_id}.developer.{attempt}.jsonl", DEV_TIMEOUT_S)
        s.update(story_id=story_id, attempt=attempt, role="developer", prompt_sha256=_sha(prompt.encode()))
        self.sessions.append(s)
        changed = bool(git(checkout, "status", "--porcelain").stdout.strip()) or git(checkout, "rev-parse", "HEAD").stdout.strip() != parent
        s["developer_committed_itself"] = git(checkout, "rev-parse", "HEAD").stdout.strip() != parent
        if s["error"] and not changed:
            raise ProviderOutage(s["error"])
        if not changed:
            return Implemented(O.FAILED, None, f"the developer changed nothing (exit {s['exit']}, timed out {s['timed_out']})")
        sha = commit_all(checkout, f"{story_id}: developer attempt {attempt}")
        s["candidate"] = sha
        return Implemented(O.COMPLETED, sha, f"opencode exit {s['exit']}, {s['turns']} turns")


class OpenCodeReviewer:
    PROMPT = ("Review the implementation of LedgerLock story {story} in this read-only checkout against docs/requirements.md "
              "and these clauses:\n{clauses}\nDo not modify any file. Answer with ONLY one JSON object: "
              '{{"findings": [{{"id": "short-id", "blocking": true or false, "summary": "one line"}}]}}')

    def __init__(self, run, clauses: dict[str, str], logs: pathlib.Path) -> None:
        self.run, self.clauses, self.logs, self.sessions = run, clauses, logs, []

    def review(self, scope, criteria: tuple[str, ...]):
        from aisef2.journal.format2 import OperationOutcome as O
        from aisef2.orchestrate.adapters import Finding, ProviderOutage, Reviewed
        from validation.qualification.q5 import _story_context
        attempt, _ = _story_context(self.run, scope.story_id)
        prompt = self.PROMPT.format(story=scope.story_id, clauses=self.clauses[scope.story_id])
        s = opencode_session(f"reviewer {scope.story_id}", prompt, scope.root, self.logs / f"{scope.story_id}.reviewer.{attempt}.jsonl",
                             REVIEW_TIMEOUT_S)
        s.update(story_id=scope.story_id, attempt=attempt, role="reviewer", prompt_sha256=_sha(prompt.encode()))
        self.sessions.append(s)
        if s["error"] and not s["text"]:
            raise ProviderOutage(s["error"])
        found = []
        m = re.search(r"\{.*\}", s["text"], re.S)
        try:
            found = json.loads(m.group(0))["findings"] if m else []
        except (ValueError, KeyError, TypeError):
            found = []
        s["findings"] = found
        # a model review alone never blocks (§25, D-002): no corroborating authority is attached
        return Reviewed(O.COMPLETED, tuple(Finding(str(f.get("id")), bool(f.get("blocking")), ()) for f in found if isinstance(f, dict)),
                        f"{len(found)} findings, parsed={m is not None}")


class RuffScanner:
    """ruff as an informational scanner (P10's profile): run by the kernel in its owned range; findings never block."""
    name = "ruff"

    def argv(self, scope, report: str) -> tuple[str, ...]:
        return (shutil.which("ruff"), "check", "--exit-zero", "--no-cache", "--output-format", "json", "--output-file", report, scope.root)

    def read(self, report: str, exit_code):
        from aisef2.orchestrate.adapters import Finding, Scanned
        p = pathlib.Path(report)
        if not p.exists():
            return Scanned(False, ())
        rows = json.loads(p.read_text(encoding="utf-8") or "[]")
        return Scanned(True, tuple(Finding(f"{r.get('code')}:{pathlib.Path(r.get('filename', '')).name}:{(r.get('location') or {}).get('row')}",
                                           False, ("scanner:ruff",)) for r in rows))


# --------------------------------------------------------------------------------------------------------- the run

def order(plan, graph) -> list[str]:
    stories = sorted({o.story_id for o in plan.obligations})
    done, out = set(), []
    while len(out) < len(stories):
        ready = [s for s in stories if s not in done and not (graph.get(s, set()) & set(stories)) - done]
        if not ready:
            raise SystemExit("the plan's story graph has a cycle")
        out.append(ready[0])
        done.add(ready[0])
    return out


def run(out_dir: pathlib.Path) -> dict:
    from aisef2.arch.enums import ControlProjection, Enforcement, Owner
    from aisef2.orchestrate import story_runner as sr
    from aisef2.orchestrate.quality import TestsPolicy
    from aisef2.orchestrate.workspace import GitMerger, GitWorkspace, git
    from aisef2.probe import catalog
    from aisef2.probe.protocol import ExecutionEnv
    from aisef2.product.contract import plain
    from aisef2.quality import test_execution as te
    from aisef2.runtime.capability import opaque, verified
    from aisef2.runtime.run_scope import RunScope
    from aisef2.runtime.runspec import resolve
    from validation.qualification import p5_acceptance as pa
    from validation.qualification import p10_contracts as aid
    from validation.qualification import q4
    started = time.time()
    base = P10.ledgerlock_baseline()
    if not base.get("present") or not base.get("requirements_match_frozen"):
        raise SystemExit(f"the LedgerLock workload is not where the freeze says or its requirements changed: {base}")
    plan = aid.build()["plan"]
    if plan.plan_hash != pa.ACCEPTED["plan_hash"] or plan.baseline != base["baseline"]:
        raise SystemExit("the plan is not the owner-approved PLAN-V2.2 at its baseline")
    specs = {s.id: s for s in _compiled().values()}
    oc = P10.opencode_identity()
    epics = subprocess.run(["git", "-C", str(P10.LEDGERLOCK_REPO), "show", f"{P10.LEDGERLOCK_PLAN_COMMIT}:_bmad-output/epics.md"],
                           capture_output=True, encoding="utf-8", check=True).stdout
    tasks, clauses = prompts(plan, epics)
    kernel = q4._over(q4._file_digests(("aisef2",)))
    caps = [verified("kernel", kernel.encode(), Enforcement.FULL, tree=C.git("rev-parse", "HEAD:aisef2")),
            verified("python", pathlib.Path(sys.executable), Enforcement.PARTIAL, version=platform.python_version()),
            verified("git", pathlib.Path(shutil.which("git")), Enforcement.PARTIAL),
            *[verified(e.probe_id, e.probe_digest.encode(), Enforcement.PARTIAL) for e in catalog.CATALOG if e.active],
            opaque("developer", Enforcement.PARTIAL, client="opencode", route=str(oc["declared_route"]), version=str(oc["version"])),
            opaque("reviewer", Enforcement.PARTIAL, client="opencode", route=str(oc["declared_route"]), version=str(oc["version"])),
            opaque("scanner", Enforcement.PARTIAL, tool="ruff", mode="lint as an informational scanner")]
    layers = {"workload": {"value": "LedgerLock", "layer": "c2-p9"}, "benchmark_class": {"value": P10.BENCHMARK_CLASS, "layer": "c2-p9"},
              "plan_hash": {"value": plan.plan_hash, "layer": "plan"}, "requirements_sha256": {"value": P10.REQUIREMENTS_SHA256, "layer": "workload"},
              "limits": {"value": LIMITS, "layer": "c2-p9 (p10 profile)"}}
    logs = out_dir / SESSIONS
    logs.mkdir(parents=True, exist_ok=True)
    results, errors, events, state, run_id, final = {}, [], [], {}, {}, None
    holder = tempfile.TemporaryDirectory(prefix="aisef2-c2-p9-")
    tmp = pathlib.Path(holder.name).resolve()
    dev = rev = None
    try:
        repo = tmp / "repo"
        subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(P10.LEDGERLOCK_REPO), str(repo)], check=True, capture_output=True, encoding="utf-8")
        git(repo, "checkout", "-q", "-B", "main", base["baseline"])
        for n in ("ws", "merge", "run"):
            (tmp / n).mkdir()
        ws, merger = GitWorkspace(repo, tmp / "ws"), GitMerger(repo, "main", tmp / "merge")
        run_ = RunScope(tmp / "run", "c2-p9-ledgerlock", spec=lambda: resolve(caps, layers, base["baseline"]))
        run_.begin()
        dev, rev = OpenCodeDeveloper(run_, tasks, logs), OpenCodeReviewer(run_, clauses, logs)
        adapters = sr.Adapters(dev, rev, RuffScanner(), merger, ws)
        factories = {e.probe_id: (lambda on_range, scratch, f=e.factory: f(on_range=on_range, scratch=scratch)) for e in catalog.CATALOG}
        env = ExecutionEnv(sys.executable, 60, Enforcement.PARTIAL)
        limits = {Owner[k]: v for k, v in LIMITS.items()}
        delivered: list[str] = []
        for story in order(plan, aid.story_graph()):
            inputs = sr.StoryInputs(specs, factories, env, te.DeveloperTests(story, (test_path(story),)),
                                    te.DeveloperTests(story, tuple(test_path(s) for s in delivered) or (test_path(story),)),
                                    te.Dependencies(frozenset(), PROJECT), te.UNITTEST)
            try:
                r = sr.run_story(run_, plan, story, inputs, adapters, sr.Policy(limits, TestsPolicy(True), tool_timeout_s=120))
                results[story] = [a.outcome for a in r.attempts]
                if results[story][-1:] == ["COMMIT"]:
                    delivered.append(story)
            except Exception as e:  # noqa: BLE001 — a typed refusal of one story is recorded; the run goes on
                errors.append({"story": story, "error": f"{type(e).__name__}: {e}"[:2000]})
                results[story] = [f"REFUSED: {type(e).__name__}"]
                if run_._state != "RUNNING":
                    break
        state = plain(run_.state(ControlProjection.STORY_STATE))
        if run_._state == "RUNNING":
            run_.shutdown()
        events = [{"seq": e.seq, "type": e.type, "data": plain(e.data)} for e in run_.events]
        run_id = {"run_id": "c2-p9-ledgerlock", "journal_events": len(events),
                  "journal_sha256": _sha(json.dumps(events, sort_keys=True, default=str).encode())}
        final = git(repo, "rev-parse", "main").stdout.strip()
    finally:
        holder.cleanup()
    return {"started": started, "results": results, "errors": errors, "events": events, "state": state,
            "run_identity": run_id, "final_main": final, "baseline": base, "oc": oc, "plan": plan, "specs": specs, "tasks": tasks,
            "sessions": (dev.sessions if dev else []) + (rev.sessions if rev else []), "caps": caps, "layers": layers, "kernel": kernel}


def record(out_dir: pathlib.Path, m: dict) -> dict:
    from aisef2.runtime.runspec import resolve
    from validation.qualification import p5_acceptance as pa
    from validation.qualification import p10_contracts as aid
    plan, events = m["plan"], m["events"]
    roles = {o.criterion_id: o.role.value for o in plan.obligations}
    delivery = P10.delivery_verdict_of(events, plan_admitted=True)
    metrics = P10.plan_quality_metrics(events, roles)
    policy, at, policy_path = P10.preregistered_policy(out_dir)
    if policy_path is not None:
        raise SystemExit("DECISION-5: no PlanQualityPolicy may be preregistered for LedgerLock")
    plan_quality = P10.plan_quality_verdict_of(metrics, policy, policy_preregistered_at=at, run_started_at=m["started"])
    verdict = P10.RunVerdict(delivery, plan_quality)
    prohibitions = {}
    for target in ("SEALED", "HOLDOUT", "EVALUATING"):
        try:
            P10.LEDGERLOCK.transition(target)
            prohibitions[target] = "ACCEPTED (defect)"
        except P10.SealingRefused as e:
            prohibitions[target] = f"REJECTED: {e}"
    for name, kw in (("generalization_claim=POSITIVE", {"generalization_claim": "POSITIVE"}), ("qualification_sample_size", {"qualification_sample_size": 1})):
        try:
            P10.Recorder().record(**{"benchmark_class": P10.BENCHMARK_CLASS, "generalization_claim": "NONE", "cohort_state": "DEVELOPMENT", "verdict": verdict, **kw})
            prohibitions[name] = "ACCEPTED (defect)"
        except P10.ClaimRefused as e:
            prohibitions[name] = f"REJECTED: {e}"
    try:
        P10.overall_verdict(verdict)
        prohibitions["overall_verdict"] = "ACCEPTED (defect)"
    except P10.ClaimRefused as e:
        prohibitions["overall_verdict"] = f"REJECTED: {e}"
    # the ProductProof account per obligation, from the journal: the last verified proof of each criterion
    proofs = {}
    for e in events:
        if e["type"] == "proof/verified":
            proofs[(e["data"].get("story_id"), e["data"].get("criterion_id"))] = {"candidate": e["data"].get("candidate"), "seq": e["seq"],
                                                                                   "agreement": e["data"].get("agreement"),
                                                                                   "verdict": e["data"].get("verdict")}
    committed = {s for s, v in m["results"].items() if v[-1:] == ["COMMIT"]}
    obligations = []
    for o in plan.obligations:
        spec = m["specs"][o.product_proof_spec_id]
        proof = proofs.get((o.story_id, o.criterion_id))
        satisfied = bool(proof and proof["agreement"] and proof["verdict"] == spec.candidate_expectation.value)
        obligations.append({"story": o.story_id, "criterion": o.criterion_id, "role": o.role.value, "spec": o.product_proof_spec_id,
                            "probe_id": spec.probe_id, "candidate_expectation": spec.candidate_expectation.value, "last_proof": proof,
                            "satisfied_at_last_proof": satisfied, "delivered": satisfied and o.story_id in committed})
    prop = json.loads((ROOT / pa.PROPOSAL_REL).read_text(encoding="utf-8"))
    clauses = prop["clauses"]
    spec_req = {sid: t["requirement"] for sid, t in aid.SPECS.items()}
    covered = sorted({spec_req[sid] for sid in pa.contracts()})
    by_class = {}
    for c in clauses:
        by_class.setdefault(c["class"], []).append(c["id"])
    sessions = m["sessions"]
    spec = resolve(m["caps"], m["layers"], m["baseline"]["baseline"])
    rec = P10.Recorder().record(
        record="AISEF V2 — CYCLE-2 QP-2.9 LEDGERLOCK REGRESSION (DEVELOPMENT / REGRESSION BENCHMARK ONLY)", rung="C2-P9 / QP-2.9",
        authority="owner rulings 2026-09-30 A ('C2-P9 / QP-2.9 — LEDGERLOCK REGRESSION') and B (QP-2.9: execute the approved plan model)",
        written=C.now(), purpose="does the Cycle-2 framework execute more of the known workload correctly? — not: how would AISEF perform on unseen projects",
        semantic_candidate=C.SEMANTIC_CANDIDATE, aisef2_tree=C.KERNEL_TREE, head_kernel_tree=C.git("rev-parse", "HEAD:aisef2"),
        repository_execution_commit=C.git("rev-parse", "HEAD"), harness={"path": "validation/qualification/c2_p9.py", "sha256": C.lf_sha(HERE / "c2_p9.py")},
        workload={"id": "LedgerLock", "benchmark_class": P10.BENCHMARK_CLASS, "repository": m["baseline"], "requirements_sha256": P10.REQUIREMENTS_SHA256,
                  "final_main": m["final_main"], "repository_written": False},
        plan_identity={"id": plan.id, "plan_hash": plan.plan_hash, "baseline": plan.baseline, "stories": len({o.story_id for o in plan.obligations}),
                       "obligations": len(plan.obligations), "execution_order": order(plan, aid.story_graph()), "replanned": False, "stories_split": False},
        approvals={"record": pa.APPROVALS_REL, "count": len(pa.load_approvals()), "approver": pa.OWNER},
        execution_profile={"source": "p10.runspec_for (Cycle-1 P10 profile): OpenCode developer and reviewer on the declared route, ruff scanner, P10 limits",
                           "runspec_hash": spec.runspec_hash, "aggregate_min_grade": spec.aggregate_min_grade.value, "limits": LIMITS,
                           "capabilities": [{"name": c.name, "grade": c.grade.value, "enforcement": c.enforcement.value} for c in spec.capabilities],
                           "model": m["oc"], "kernel_digest": m["kernel"],
                           "grade_note": "the route is a routing alias: OPAQUE, which bars sealing and nothing else here; no model identity is inferred from it"},
        run_identity=m["run_identity"], cohort_state="DEVELOPMENT", benchmark_class=P10.BENCHMARK_CLASS, generalization_claim=P10.GENERALIZATION_CLAIM,
        verdict=verdict, delivery_verdict_derivation="from the run's journal events only; no plan-quality input",
        story_outcomes=m["results"], story_state=m["state"], story_errors=m["errors"],
        productproof={"obligations": obligations, "total": len(obligations),
                      "with_a_verified_proof": sum(1 for o in obligations if o["last_proof"]),
                      "satisfied_at_last_proof": sum(1 for o in obligations if o["satisfied_at_last_proof"]),
                      "delivered_in_committed_stories": sum(1 for o in obligations if o["delivered"]),
                      "rule": "satisfied = the two parties agree and the verdict is the spec's candidate expectation; delivered = "
                              "satisfied in a story whose last outcome is COMMIT"},
        requirements={"covered_by_productproof": covered,
                      "unsupported": {"clauses": by_class.get(aid.U, []), "rule": "remain UNSUPPORTED_FOR_FULL_ENFORCEMENT; never counted as passes"},
                      "engineering_test_only": by_class.get(aid.E, []), "classes": {k: len(v) for k, v in by_class.items()},
                      "known_ambiguities": prop["requirement_risks"]},
        plan_quality_metrics=metrics, plan_drift={"attributed": metrics["attributed_plan_drift"], "unattributed": metrics["unattributed_plan_drift"]},
        plan_quality_policy={"preregistered": False, "decision": "DECISION-5: DO_NOT_PREREGISTER", "path": None},
        model_sessions={"count": len(sessions), "by_role": {r: sum(1 for s in sessions if s["role"] == r) for r in ("developer", "reviewer")},
                        "sessions": [{k: v for k, v in s.items() if k != "text"} for s in sessions],
                        "tokens": {k: sum(s["tokens"][k] for s in sessions) for k in ("input", "output")}},
        prohibitions=prohibitions, residual_processes={"owned_range": "see the owned-run record beside this file"},
        platform={"system": platform.system().lower(), "python": platform.python_version()},
        stop_rules={"kernel_tree_is_the_candidates": C.git("rev-parse", "HEAD:aisef2") == C.KERNEL_TREE, "plan_retuned": False, "kernel_repaired": False,
                    "historical_evidence_rewritten": False, "cohort_sealed": False, "generalization_claimed": False},
        finished=C.now(),
    )
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", action="store_true", required=True)
    ap.parse_args(argv)
    out_dir = ROOT / OUT_REL
    if (out_dir / "LEDGERLOCK-REGRESSION.json").exists():
        raise SystemExit("REFUSED: LEDGERLOCK-REGRESSION.json exists — a rerun is a new attempt, never an overwrite")
    m = run(out_dir)
    rec = record(out_dir, m)
    for p in (out_dir / SESSIONS).glob("*.jsonl"):
        if SECRET.search(p.read_text(encoding="utf-8", errors="replace")):
            raise SystemExit(f"STOP: {p.name} looks like it holds a secret; nothing is written")
    C.write(f"{OUT_REL}/LEDGERLOCK-REGRESSION.json", rec)
    print(f"delivery {rec['delivery_verdict']}; plan quality {rec['plan_quality_verdict']}; outcomes {rec['story_outcomes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
