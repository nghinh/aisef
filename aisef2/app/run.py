"""The run driver: one project bundle, one settings document, one run directory that nothing removes.

    <out>/repo         the project cloned at the plan's baseline: main, every candidate and every merge
    <out>/run          the kernel's RunScope: the raw hash-chained journal (journals/<run_id>.jsonl), lease, sentinel
    <out>/work         the kernel's worktrees (each released by the story that owns it)
    <out>/probe-python the interpreter probes and developer tests run with: a venv of its own, no site packages (B6)
    <out>/preflight    the provider preflight's ledger and observation
    <out>/sessions     one event stream per model session
    <out>/RUN.json     the record — written in a `finally`, so a run that breaks (an exception, an invariant failure,
                       a refused shutdown, an interruption) still leaves it beside its journal (B3)

Order: the bundle and the settings load (every seal re-checked); the repository is cloned and its requirements document
checked against the bundle; the plan is admitted (RFC §12); the probe interpreter is made; the route is attested by
the preflight (an identity stop otherwise); the RunSpec is resolved and the run begins; the stories run in dependency
order through the kernel's story runner while the budget holds. The delivery verdict comes from the journal only;
plan quality is NOT_CLAIMED (no PlanQualityPolicy is preregistered by a run)."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import time

from aisef2.app import adapters as ad
from aisef2.app import client, preflight
from aisef2.app.bundle import Project
from aisef2.app.settings import Settings
from aisef2.arch.enums import Enforcement
from aisef2.orchestrate import story_runner as sr
from aisef2.orchestrate.quality import TestsPolicy
from aisef2.orchestrate.workspace import GitMerger, GitWorkspace, git
from aisef2.plan import static_admission as sa
from aisef2.probe import catalog
from aisef2.probe.calibration import ProbeCapabilityCalibration
from aisef2.probe.protocol import ExecutionEnv
from aisef2.product.contract import plain
from aisef2.quality import test_execution as te
from aisef2.runtime.capability import attested, opaque, verified
from aisef2.runtime.run_scope import RunScope, ShutdownRefused
from aisef2.runtime.runspec import resolve

FORMAT = "aisef-v2-run-record/1"


class RunRefused(Exception):
    """The run cannot start as given: nothing was sent to a provider."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def kernel_digest() -> str:
    """The digest of the kernel this process runs: every .py file of the installed `aisef2` package, LF-normalized,
    by relative path."""
    root = pathlib.Path(__file__).resolve().parents[1]
    h = hashlib.sha256()
    for p in sorted(root.rglob("*.py")):
        h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def calibrations(rows=None) -> tuple:
    """The probe capability calibrations this release ships (aisef2/app/calibrations.py), or `rows` given."""
    if rows is None:
        try:
            from aisef2.app.calibrations import CALIBRATIONS as rows
        except ImportError:     # an install without them admits no plan: check 9 names every spec
            return ()
    return tuple(ProbeCapabilityCalibration(r["probe_id"], r["probe_digest"], r["observation_class"], r["positive_fixture"],
                                            r["negative_fixture"], float(r["demonstrated_at"])) for r in rows)


def admit(project: Project, cals: tuple) -> dict:
    """RFC §12: a plan runs only if the StaticPlanAdmissionEngine admits it; re-derived here, never taken on trust."""
    inputs = sa.AdmissionInputs(project.requirements, project.contracts, project.approvals, project.specs,
                                catalog.catalogue(), cals, catalog.registry())
    result = sa.StaticPlanAdmissionEngine().admit(project.plan, inputs)
    out = {"admitted": result.admitted, "engine_digest": result.engine_digest, "result_digest": result.result_digest,
           "failed": [{"check": f"{c.number}. {c.name}", "problems": list(c.problems[:5])} for c in result.checks if not c.passed]}
    return out


def check_repository(project: Project, repo: pathlib.Path) -> None:
    """The project's repository holds the plan's baseline, and its requirements document there is the bundle's."""
    if git(repo, "cat-file", "-e", f"{project.plan.baseline}^{{commit}}").returncode != 0:
        raise RunRefused(f"{repo} does not hold the plan's baseline {project.plan.baseline}")
    blob = git(repo, "cat-file", "blob", f"{project.plan.baseline}:{project.requirements_path}")   # text: LF line endings
    if blob.returncode != 0 or _sha(blob.stdout.encode("utf-8")) != project.requirements_sha256:
        raise RunRefused(f"the requirements document {project.requirements_path} at the baseline is not the bundle's")


def probe_interpreter(where: pathlib.Path, python: str = sys.executable) -> str:
    """B6: the interpreter probes and developer tests run with — a fresh venv of this run's own, without pip and
    without the host's site packages, so no `.pth` file of the host runs in a proof."""
    subprocess.run([python, "-I", "-m", "venv", "--without-pip", str(where)], check=True, capture_output=True)
    exe = where / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not exe.exists():
        raise RunRefused(f"the probe interpreter was not created at {exe}")
    return str(exe)


def regression_tests(repo: pathlib.Path, project: Project, story: str, delivered: dict[str, bool]) -> tuple[str, ...]:
    """H-REGRESSION-001: the tests of every earlier committed story that produced them or that main holds now; with
    none, the story's own."""
    def held(p: str) -> bool:
        return git(repo, "cat-file", "-e", f"main:{p}").returncode == 0
    named = tuple(p for s, produced in delivered.items() for p in project.stories[s]["tests"] if produced or held(p))
    return named or tuple(project.stories[story]["tests"])


def client_identity(exe: str | None) -> str:
    if not exe:
        return "opencode (absent)"
    try:
        version = subprocess.run([exe, "--version"], capture_output=True, text=True, encoding="utf-8", timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        version = f"unavailable: {type(e).__name__}"
    return f"opencode {version} binary-sha256:{_sha(pathlib.Path(exe).read_bytes())}"


def runspec_of(project: Project, settings: Settings, pre: dict, client_id: str, python: str, scanner):
    obs = pre["observation"]
    identity = {"provider": settings.provider, "endpoint": settings.endpoint, "declared_model": settings.model,
                "route": settings.route, "client": client_id}
    models = [attested(n, preflight=preflight.fingerprint_fields(obs), enforcement=Enforcement.PARTIAL,
                       deployment=preflight.deployment(obs), **identity) for n in ("developer", "reviewer")]
    scan = (verified("scanner", pathlib.Path(scanner.exe), Enforcement.PARTIAL, tool="ruff") if scanner.name == "ruff"
            else opaque("scanner", Enforcement.PARTIAL, tool="none"))
    caps = [verified("kernel", kernel_digest().encode(), Enforcement.FULL),
            verified("python", pathlib.Path(python), Enforcement.PARTIAL, version=platform.python_version()),
            verified("git", pathlib.Path(shutil.which("git")), Enforcement.PARTIAL),
            *[verified(e.probe_id, e.probe_digest.encode(), Enforcement.PARTIAL) for e in catalog.CATALOG if e.active],
            *models, scan]
    layers = {"workload": {"value": project.name, "layer": "bundle"}, "bundle_digest": {"value": project.digest, "layer": "bundle"},
              "plan_hash": {"value": project.plan.plan_hash, "layer": "plan"},
              "requirements_sha256": {"value": project.requirements_sha256, "layer": "bundle"},
              "settings_sha256": {"value": _sha(json.dumps(settings.content, sort_keys=True).encode()), "layer": "settings"},
              "limits": {"value": {k.value: v for k, v in settings.limits.items()}, "layer": "settings"},
              "budget": {"value": settings.budget, "layer": "settings"},
              "max_turns_per_session": {"value": settings.max_turns_per_session, "layer": "settings"},
              "timeouts_s": {"value": settings.timeouts_s, "layer": "settings"}}
    return resolve(caps, layers, project.plan.baseline)


def productproof(project: Project, events: list[dict], committed: set[str]) -> dict:
    proofs = {}
    for e in events:
        if e["type"] == "proof/verified":
            proofs[(e["data"].get("story_id"), e["data"].get("criterion_id"))] = {
                "candidate": e["data"].get("candidate"), "seq": e["seq"], "agreement": e["data"].get("agreement"),
                "verdict": e["data"].get("verdict")}
    rows = []
    for o in project.plan.obligations:
        spec = project.specs[o.product_proof_spec_id]
        proof = proofs.get((o.story_id, o.criterion_id))
        satisfied = bool(proof and proof["agreement"] and proof["verdict"] == spec.candidate_expectation.value)
        rows.append({"story": o.story_id, "criterion": o.criterion_id, "role": o.role.value, "spec": spec.id,
                     "probe_id": spec.probe_id, "expected": spec.candidate_expectation.value, "last_proof": proof,
                     "satisfied_at_last_proof": satisfied, "delivered": satisfied and o.story_id in committed})
    return {"obligations": rows, "total": len(rows), "satisfied_at_last_proof": sum(r["satisfied_at_last_proof"] for r in rows),
            "delivered": sum(r["delivered"] for r in rows)}


def delivery(project: Project, events: list[dict], results: dict, budget_stop: str | None, errors: list) -> tuple[str, list[str], set[str]]:
    """From the journal: PASS only when every plan story's last outcome is its commit, the budget stopped nothing and
    no story was refused; NOT_REACHED when no story reached its gate. `budget_stop` is an actual stop (`budget_stops`),
    never spend that merely sits at a ceiling (review IR-02)."""
    last, decided = {}, False
    for e in events:
        if e["type"] == "gate/decision":
            decided = True
        if e["type"] in ("story/commit", "story/rollback", "story/retry"):
            last[e["data"]["story_id"]] = e["type"]
    committed = {s for s, v in results.items() if v[-1:] == ["COMMIT"] and last.get(s) == "story/commit"}
    missing = sorted({o.story_id for o in project.plan.obligations} - committed)
    blocked = ([f"{len(missing)} of the plan's stories did not commit: {missing}"] if missing else []) \
        + ([f"the budget ended the run: {budget_stop}"] if budget_stop else []) \
        + ([f"{len(errors)} stories were refused"] if errors else [])
    verdict = "NOT_REACHED" if not decided else ("FAIL" if blocked else "PASS")
    return verdict, blocked, committed


def budget_stops(not_run: list[str], sessions: list[dict], budget) -> str | None:
    """What the budget actually stopped: a story not started for it, a session it refused or ended, spend past a ceiling
    or unaccounted. A session's own turn cap is not a run budget stop (the story is judged by its proofs)."""
    stops = list(not_run)
    stops += [f"{s.get('role')} {s.get('story_id')}: {s['stopped']}" for s in sessions
              if str(s.get("stopped") or "").startswith(("max_", "unaccounted"))]
    exceeded = budget.exceeded() if budget is not None else None
    return "; ".join(stops + ([exceeded] if exceeded else [])) or None


def execute(project: Project, settings: Settings, source: pathlib.Path, out: pathlib.Path, *, transport=None,
            client_exe: str | None = None, cals: tuple | None = None, clock=time.time) -> dict:
    """Run the project; the record (also written to <out>/RUN.json, whatever happens)."""
    if out.exists():
        raise RunRefused(f"{out} exists: a run directory is never reused or overwritten")
    out.mkdir(parents=True)
    rec: dict = {"format": FORMAT, "bundle_digest": project.digest, "project": project.name, "plan_hash": project.plan.plan_hash,
                 "settings": settings.content, "started": clock(), "stage": "repository", "kernel_digest": kernel_digest(),
                 "platform": {"system": platform.system().lower(), "python": platform.python_version()}}
    run = None
    developer = reviewer = budget = None
    results: dict = {}
    errors: list = []
    not_run: list[str] = []
    failure: BaseException | None = None
    try:
        repo = out / "repo"
        cloned = git(out, "clone", "--quiet", "--no-hardlinks", str(source.resolve()), str(repo))
        if cloned.returncode != 0:
            raise RunRefused(f"the project repository could not be cloned: {cloned.stderr.strip()[:200]}")
        check_repository(project, repo)
        if git(repo, "checkout", "-q", "-B", "main", project.plan.baseline).returncode != 0:
            raise RunRefused("the baseline could not be checked out as main")
        rec["stage"] = "admission"
        rec["admission"] = admit(project, calibrations() if cals is None else cals)
        if not rec["admission"]["admitted"]:
            raise RunRefused(f"the plan is not admitted (RFC §12): {rec['admission']['failed']}")
        rec["stage"] = "probe interpreter"
        python = probe_interpreter(out / "probe-python")
        rec["stage"] = "preflight"
        exe = client_exe or shutil.which("opencode", path=client.environment(settings.client_env, {}).get("PATH"))
        if not exe:
            raise RunRefused("the client (opencode) is not on the PATH the run gives it")
        transport = transport or preflight.http_transport(settings.endpoint, settings.api_key_env)
        pre = preflight.run(settings.route, settings.chat_probes, transport, out / "preflight")
        rec["preflight"] = pre
        if pre["verdict"] != "ATTESTED":
            raise preflight.IdentityStop("the route is not attested: " + "; ".join(pre["problems"]))
        if pre["accounting"]["unaccounted"]:
            raise preflight.IdentityStop(f"preflight requests unaccounted: {pre['accounting']['unaccounted']}")
        scanner = ad.scanner()
        spec = runspec_of(project, settings, pre, client_identity(exe), python, scanner)
        rec.update(runspec_hash=spec.runspec_hash, aggregate_min_grade=spec.aggregate_min_grade.value, scanner=scanner.name)
        rec["stage"] = "run"
        run = RunScope(out / "run", "aisef-run", spec=lambda: spec, clock=clock)
        run.begin()
        work = out / "work"
        (work / "ws").mkdir(parents=True)
        (work / "merge").mkdir()
        ws, merger = GitWorkspace(repo, work / "ws"), GitMerger(repo, "main", work / "merge")
        logs = out / "sessions"
        budget = client.Budget(settings.budget, pre["accounting"], logs,
                               lambda: sum(1 for e in run.events if e.type == "provider/request"))
        kw = {"model": settings.route, "env": client.environment(settings.client_env, client.overlay(settings.route)),
              "budget": budget, "turn_cap": settings.max_turns_per_session, "exe": exe,
              # the operator's values the client receives, and the provider key: never left in a session's evidence
              "secrets": tuple(os.environ[n] for n in (*settings.client_env, settings.api_key_env)
                               if len(os.environ.get(n, "")) >= 8)}
        developer = ad.Developer(run, project, logs, kw, settings.timeouts_s["developer"])
        reviewer = ad.Reviewer(run, project, logs, kw, settings.timeouts_s["reviewer"])
        adapters = sr.Adapters(developer, reviewer, scanner, merger, ws)
        factories = {e.probe_id: (lambda on_range, scratch, f=e.factory: f(on_range=on_range, scratch=scratch))
                     for e in catalog.CATALOG}
        env = ExecutionEnv(python, settings.timeouts_s["probe"], Enforcement.PARTIAL)
        policy = sr.Policy(settings.limits, TestsPolicy(True), tool_timeout_s=settings.timeouts_s["tool"])
        delivered: dict[str, bool] = {}
        for story in project.order():
            why = budget.reached()
            if why:
                results[story] = [f"NOT_RUN: {why}"]
                not_run.append(f"{story} not run: {why}")
                continue
            tests = tuple(project.stories[story]["tests"])
            inputs = sr.StoryInputs(project.specs, factories, env, te.DeveloperTests(story, tests),
                                    te.DeveloperTests(story, regression_tests(repo, project, story, delivered)),
                                    te.Dependencies(frozenset(), frozenset(project.product_roots)), te.UNITTEST)
            try:
                r = sr.run_story(run, project.plan, story, inputs, adapters, policy)
                results[story] = [a.outcome for a in r.attempts]
                if results[story][-1:] == ["COMMIT"]:
                    delivered[story] = all(git(repo, "cat-file", "-e", f"main:{p}").returncode == 0 for p in tests)
            except Exception as e:  # noqa: BLE001 — a typed refusal of one story is recorded; the run goes on
                errors.append({"story": story, "error": f"{type(e).__name__}: {e}"[:2000]})
                results[story] = [f"REFUSED: {type(e).__name__}"]
                if run._state != "RUNNING":
                    break
        rec["stage"] = "finished"
    except BaseException as e:      # recorded by the `finally` below as it propagates: nothing of the run is lost to it
        failure = e
        raise
    finally:
        closed = None
        try:
            closed = _close_run(run)
        finally:    # B3: the record is written even when closing the run raises; that exception then propagates
            rec["journal"] = _journal_info(run, closed if closed is not None or run is None else f"closing failed in state {run._state}")
            events = [{"seq": e.seq, "type": e.type, "data": plain(e.data)} for e in run.events] if run is not None else []
            sessions = (developer.sessions if developer else []) + (reviewer.sessions if reviewer else [])
            stop = budget_stops(not_run, sessions, budget)
            verdict, blocked, committed = delivery(project, events, results, stop, errors)
            final = git(out / "repo", "rev-parse", "main").stdout.strip() if (out / "repo").exists() else None
            rec.update(finished=clock(), story_outcomes=results, story_errors=errors, final_main=final or None,
                       delivery_verdict="FAIL" if failure is not None and verdict == "PASS" else verdict, delivery_blocked_by=blocked,
                       plan_quality_verdict="NOT_CLAIMED", generalization_claim="NONE",
                       productproof=productproof(project, events, committed) if events else None,
                       budget=budget.account() if budget else None, budget_stop=stop,
                       sessions=[{k: v for k, v in s.items() if k != "text"} for s in sessions],
                       failure=None if failure is None else {"type": type(failure).__name__, "detail": str(failure)[:2000],
                                                             "stage": rec.get("stage")})
            (out / "RUN.json").write_text(json.dumps(rec, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return rec


def _close_run(run) -> str | None:
    """Close the RunScope however the run ended: a normal shutdown, or — if the kernel refuses it (an open story) —
    its interruption. How it closed."""
    if run is None:
        return None
    closed = run._state
    if run._state == "RUNNING":
        try:
            run.shutdown()
            closed = "SHUTDOWN"
        except ShutdownRefused as e:
            run.interrupt()
            closed = f"INTERRUPTED after a refused shutdown: {e}"
    return closed


def _journal_info(run, closed: str | None) -> dict | None:
    """The journal's location (relative to the run directory), digest and length, as it is on disk now."""
    if run is None:
        return None
    path = run.journal_path
    data = path.read_bytes() if path.exists() else b""
    return {"path": str(path.relative_to(path.parents[2])), "sha256": _sha(data), "lines": data.count(b"\n"), "closed": closed}


def _close(run) -> dict:
    """Close the run and name its journal (used where the closing and the record are one step)."""
    return {"journal": _journal_info(run, _close_run(run))}
