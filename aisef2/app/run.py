"""The run driver: one project bundle, one settings document, one run directory that nothing removes.

    <out>/repo         the project cloned at the plan's baseline: main, every candidate and every merge
    <out>/run          the kernel's RunScope: the raw hash-chained journal (journals/<run_id>.jsonl), lease, sentinel
    <out>/work         the kernel's worktrees (each released by the story that owns it)
    <out>/test-python  the interpreter the developer's tests run with: a venv of its own, no site packages (B6). The
                       probes never run on it (V2.1): they run on the interpreter this kernel runs on, -I -S, so what
                       test code writes into its own interpreter's tree (a `.pth`, the interpreter) reaches no proof
    <out>/preflight    the provider preflight's ledger and observation
    <out>/sessions     one event stream per model session
    <out>/confinement  V2.1 (F), when the settings ask for it: the measurement's canary (its report is RUN.json's
                       `confinement`; its workspace, a worktree of <out>/repo, is removed after it)
    <out>/RUN.started.json  V2.1: the run's identities written once before anything runs (format, bundle and kernel
                       digests, plan hash, the settings' digest, the lineage) — so a run the operating system killed (no
                       `finally` runs on SIGKILL) still says what it was; never rewritten
    <out>/RUN.json     the record — written in a `finally`, so a run that breaks (an exception, an invariant failure,
                       a refused shutdown, an interruption) still leaves it beside its journal (B3)
    <out>/CONTINUED-BY.json  V2.1: created (exclusively) in a run directory when another run continues it: one
                       continuation per run, the claimant named; a later generation (CONTINUED-BY.<n>.json) only
                       supersedes, with evidence, a claim whose child never began (app/lineage); nothing is deleted
    <out>/EVIDENCE.json the evidence manifest (V2.1): the sha256 of the record, the journal, every session stream and
                       the preflight's files, written after the record; its own digest is the run's evidence anchor,
                       printed for the operator to keep outside the run directory (`aisef run --verify --expect-anchor`)

Order: the bundle and the settings load (every seal re-checked); the repository is cloned and its requirements document
checked against the bundle; the plan is admitted (RFC §12); the test interpreter is made; the route is attested by
the preflight (an identity stop otherwise); the RunSpec is resolved and the run begins; the stories run in dependency
order through the kernel's story runner while the budget holds. The delivery verdict comes from the journal only;
plan quality is NOT_CLAIMED (no PlanQualityPolicy is preregistered by a run)."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

from aisef2.app import adapters as ad
from aisef2.app import client, confine, lineage, preflight, usage
from aisef2.app.bundle import Project
from aisef2.app.settings import Settings
from aisef2.arch.enums import Enforcement
from aisef2.orchestrate import story_runner as sr
from aisef2.orchestrate.quality import TestsPolicy
from aisef2.orchestrate.workspace import REFUSED, GitMerger, GitWorkspace, git
from aisef2.plan import static_admission as sa
from aisef2.probe import catalog
from aisef2.probe.calibration import ProbeCapabilityCalibration, executing
from aisef2.probe.protocol import ExecutionEnv
from aisef2.product.contract import plain
from aisef2.quality import test_execution as te
from aisef2.runtime.capability import attested, opaque, verified
from aisef2.runtime.run_scope import RunScope, ShutdownRefused
from aisef2.runtime.runspec import resolve

FORMAT = "aisef-v2-run-record/1"
STARTED, CLAIM = lineage.STARTED, lineage.CLAIM
MANIFEST = "EVIDENCE.json"
MANIFEST_FORMAT = "aisef-v2-evidence/1"


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


#: B4 holds only on a git that takes command-scope settings (GIT_CONFIG_COUNT, 2.31) and lists scopes (2.26): an older one
#: would run with the repository's own configuration in force
MIN_GIT = (2, 31)


def client_on_path(settings: Settings) -> str | None:
    """The client on exactly the PATH the run gives it: none given, nothing found (never the os.defpath fallback)."""
    return shutil.which("opencode", path=client.environment(settings.client_env, {}).get("PATH", ""))


def check_git() -> None:
    """The git on PATH is one B4 holds on; refused before the run's first git command otherwise."""
    try:
        v = subprocess.run(["git", "--version"], capture_output=True, encoding="utf-8", errors="replace", timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        v = f"unavailable: {type(e).__name__}"
    m = re.match(r"git version (\d+)\.(\d+)", v)
    if not m or (int(m[1]), int(m[2])) < MIN_GIT:
        raise RunRefused(f"git {MIN_GIT[0]}.{MIN_GIT[1]} or newer is required (B4): found {v or 'nothing'}")


def check_repository(project: Project, repo: pathlib.Path, *, clone: bool = True, shown: pathlib.Path | None = None) -> None:
    """The project's repository holds the plan's baseline, and its requirements document there is the bundle's.
    Checked as the run applies it — on a clone of `repo` (`clone`; the run passes its own clone with `clone=False`) —
    so a key of the source's own configuration that a clone does not carry neither refuses `--check` nor goes
    unnoticed. A repository git refuses (B4: its own configuration names a key that is not inert) says so — never
    that the baseline is missing."""
    if clone:
        if not pathlib.Path(repo).is_dir():
            raise RunRefused(f"{repo} is not a directory")
        with tempfile.TemporaryDirectory(prefix="aisef-check-") as tmp:
            cloned = git(tmp, "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(pathlib.Path(repo).resolve()), "repo")
            if cloned.returncode != 0:
                raise RunRefused(f"the project repository could not be cloned: {cloned.stderr.strip()[:200]}")
            return check_repository(project, pathlib.Path(tmp) / "repo", clone=False, shown=repo)
    held = git(repo, "cat-file", "-e", f"{project.plan.baseline}^{{commit}}")
    if held.returncode == REFUSED and held.stderr.startswith("refused:"):
        raise RunRefused(held.stderr)
    if held.returncode != 0:
        raise RunRefused(f"{shown or repo} does not hold the plan's baseline {project.plan.baseline}")
    blob = git(repo, "cat-file", "blob", f"{project.plan.baseline}:{project.requirements_path}")   # text: LF line endings
    if blob.returncode != 0 or _sha(blob.stdout.encode("utf-8")) != project.requirements_sha256:
        raise RunRefused(f"the requirements document {project.requirements_path} at the baseline is not the bundle's")


def probe_interpreter(where: pathlib.Path, python: str = sys.executable) -> str:
    """B6: the interpreter the developer's tests run with — a fresh venv of this run's own, without pip and without the
    host's site packages. V2.1: the probes do not run on it (360° security W1: test code wrote a `.pth` into it, which
    the probes' `-I` interpreter then ran): they run on `sys.executable` with `-I -S`, outside the run directory."""
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


def layers_of(project: Project, settings: Settings) -> dict:
    """The RunSpec's settings layers (everything but the revision): what `runspec_hash` binds of the bundle and the
    settings — and so what `verify` re-derives the hash from to bind RUN.json's settings to the journal."""
    return {"workload": {"value": project.name, "layer": "bundle"}, "bundle_digest": {"value": project.digest, "layer": "bundle"},
            "plan_hash": {"value": project.plan.plan_hash, "layer": "plan"},
            "requirements_sha256": {"value": project.requirements_sha256, "layer": "bundle"},
            "settings_sha256": {"value": _sha(json.dumps(settings.content, sort_keys=True).encode()), "layer": "settings"},
            "limits": {"value": {k.value: v for k, v in settings.limits.items()}, "layer": "settings"},
            "budget": {"value": settings.budget, "layer": "settings"},
            "max_turns_per_session": {"value": settings.max_turns_per_session, "layer": "settings"},
            "timeouts_s": {"value": settings.timeouts_s, "layer": "settings"},
            # V2.1: bound only when the settings name it, so a 2.0.0 run's RunSpec re-derives unchanged — as given
            # (policy and floor, and the finder with its pinned binary when named)
            **({"review": {"value": dict(settings.content["review"]), "layer": "settings"}}
               if settings.review and settings.review.get("given") else {})}


def runspec_of(project: Project, settings: Settings, pre: dict, client_id: str, python: str, scanner):
    """The run's RunSpec. `python` is the developer tests' interpreter; the probes' is this process's (V2.1), and each
    active probe is bound by the digest of the bytes that run (its EXECUTION_DIGEST, V2-007)."""
    obs = pre["observation"]
    identity = {"provider": settings.provider, "endpoint": settings.endpoint, "declared_model": settings.model,
                "route": settings.route, "client": client_id}
    models = [attested(n, preflight=preflight.fingerprint_fields(obs), enforcement=Enforcement.PARTIAL,
                       deployment=preflight.deployment(obs), **identity) for n in ("developer", "reviewer")]
    scan = (verified("scanner", pathlib.Path(scanner.exe), Enforcement.PARTIAL, tool="ruff") if scanner.name == "ruff"
            else opaque("scanner", Enforcement.PARTIAL, tool="none"))
    caps = [verified("kernel", kernel_digest().encode(), Enforcement.FULL),
            verified("python", pathlib.Path(sys.executable), Enforcement.PARTIAL, version=platform.python_version()),
            verified("test-python", pathlib.Path(python), Enforcement.PARTIAL),
            verified("git", pathlib.Path(shutil.which("git")), Enforcement.PARTIAL),
            *[verified(e.probe_id, executing(e.factory).encode(), Enforcement.PARTIAL) for e in catalog.CATALOG if e.active],
            *models, scan]
    return resolve(caps, layers_of(project, settings), project.plan.baseline)


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


def outcomes_from(events: list[dict]) -> dict[str, list[str]]:
    """Each story's outcomes, in order, as the journal records its decisions (story/commit, story/rollback,
    story/retry) — the story_state projection's words."""
    word = {"story/commit": "COMMIT", "story/rollback": "ROLLBACK", "story/retry": "RETRY"}
    out: dict[str, list[str]] = {}
    for e in events:
        if e["type"] in word:
            out.setdefault(e["data"]["story_id"], []).append(word[e["type"]])
    return out


def unfinished(events: list[dict]) -> list[str]:
    """Stories the journal shows begun more often than ended: an attempt that broke off (a refused story)."""
    begun: dict[str, int] = {}
    for e in events:
        if e["type"] in ("story/begin", "story/end"):
            s = e["data"]["story_id"]
            begun[s] = begun.get(s, 0) + (1 if e["type"] == "story/begin" else -1)
    return sorted(s for s, n in begun.items() if n > 0)


def _content_sha(p: pathlib.Path) -> str:
    """A file's sha256 — for the record, of its canonical JSON content (a re-serialised identical record is the same
    record; any changed value is not)."""
    data = p.read_bytes()
    if p.name == "RUN.json":
        try:
            data = json.dumps(json.loads(data), sort_keys=True, separators=(",", ":")).encode("utf-8")
        except ValueError:
            pass
    return _sha(data)


def evidence_manifest(out: pathlib.Path) -> dict:
    """The sha256 of every file a verification re-derives from (the repository aside: `final_main` is checked in it):
    the record, the journal, each session stream, the preflight's ledger and observation."""
    files = [out / "RUN.json", out / STARTED, *sorted((out / "run" / "journals").glob("*.jsonl")),
             *sorted((out / "sessions").glob("*.jsonl")), *sorted((out / "preflight").glob("*"))]
    return {"format": MANIFEST_FORMAT,
            "files": {p.relative_to(out).as_posix(): _content_sha(p) for p in files if p.is_file()}}


def anchor_in(out: pathlib.Path) -> str | None:
    """The evidence anchor of the run directory `out` as its manifest says, or None (no manifest)."""
    try:
        return anchor_of(json.loads((out / MANIFEST).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def anchor_of(manifest: dict) -> str:
    """The run's evidence anchor: the digest of its manifest's canonical JSON."""
    return _sha(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def budget_stops(not_run: list[str], sessions: list[dict], budget) -> str | None:
    """What the budget actually stopped: a story not started for it, a session it refused or ended, spend past a ceiling
    or unaccounted. A session's own turn cap is not a run budget stop (the story is judged by its proofs)."""
    stops = list(not_run)
    stops += [f"{s.get('role')} {s.get('story_id')}: {s['stopped']}" for s in sessions
              if str(s.get("stopped") or "").startswith(("max_", "unaccounted"))]
    exceeded = budget.exceeded() if budget is not None else None
    return "; ".join(stops + ([exceeded] if exceeded else [])) or None


def execute(project: Project, settings: Settings, source: pathlib.Path, out: pathlib.Path, *, transport=None,
            client_exe: str | None = None, cals: tuple | None = None, clock=time.time,
            predecessor: pathlib.Path | None = None, accept_unaccounted: bool = False,
            supersede_claim: str | None = None) -> dict:
    """Run the project; the record (also written to <out>/RUN.json, whatever happens). `predecessor`: the run this one
    continues (`aisef run --parent`, V2.1, app/lineage): claimed before the first provider request, its path and
    evidence anchor recorded, its lineage's spend counted against this run's ceilings; a lineage with unaccounted spend
    starts nothing unless `accept_unaccounted`. Nothing of the predecessor's evidence is written — and it is a run,
    never a revision: nothing runs at it."""
    # every path the run hands git or records is absolute: a relative --out given to `git -C out clone ... out/repo`
    # would clone into out/out/repo (found by the CLI integration run, V2.1)
    out, source = pathlib.Path(out).absolute(), pathlib.Path(source).absolute()
    predecessor = pathlib.Path(predecessor).absolute() if predecessor is not None else None
    if out.exists():
        raise RunRefused(f"{out} exists: a run directory is never reused or overwritten")
    continues = None
    if predecessor is not None:
        recorded = (predecessor / "RUN.json").is_file()
        if not recorded and not (predecessor / STARTED).is_file():
            raise RunRefused(f"--parent {predecessor}: no run record there")
        continues = {"path": str(predecessor), "evidence_anchor": anchor_in(predecessor)}
        if not recorded:    # killed before its record: what it spent is re-derived from its streams, marked so
            continues["recorded"] = False
    out.mkdir(parents=True)
    rec: dict = {"format": FORMAT, "bundle_digest": project.digest, "project": project.name, "plan_hash": project.plan.plan_hash,
                 "settings": settings.content, "started": clock(), "stage": "repository", "kernel_digest": kernel_digest(),
                 "platform": {"system": platform.system().lower(), "python": platform.python_version()},
                 **({"continues": continues} if continues else {})}
    with (out / STARTED).open("x", encoding="utf-8") as f:
        f.write(json.dumps({k: rec[k] for k in ("format", "bundle_digest", "project", "plan_hash", "started",
                                                 "kernel_digest", "platform") if k in rec}
                           | {"settings_sha256": _sha(json.dumps(settings.content, sort_keys=True).encode()),
                              **({"continues": continues} if continues else {})}, indent=1, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    inherited = None
    run = None
    developer = reviewer = budget = None
    results: dict = {}
    errors: list = []
    not_run: list[str] = []
    failure: BaseException | None = None
    try:
        if predecessor is not None:     # V2.1: before any provider request — a run that loses the claim spends nothing
            rec["stage"] = "claim"
            try:
                rec["continues"]["claim"] = lineage.claim(predecessor, out, clock(), supersede_claim)
            except lineage.LineageRefused as e:
                raise RunRefused(str(e)) from None
            inherited = lineage.lineage_account(predecessor, out)
            rec["continues"]["account"] = {k: inherited[k] for k in (*lineage.SPEND, "unaccounted")}
            if inherited["unaccounted"]:
                if not accept_unaccounted:
                    raise RunRefused(f"the lineage of {predecessor} has spend no evidence accounts for — no paid work "
                                     f"starts until it is reconciled or accepted (--accept-unaccounted): "
                                     f"{'; '.join(inherited['unaccounted'])[:1500]}")
                rec["continues"]["accepted_unaccounted"] = list(inherited["unaccounted"])
        rec["stage"] = "repository"
        check_git()
        repo = out / "repo"
        cloned = git(out, "clone", "--quiet", "--no-hardlinks", str(source.resolve()), str(repo))
        if cloned.returncode != 0:
            raise RunRefused(f"the project repository could not be cloned: {cloned.stderr.strip()[:200]}")
        check_repository(project, repo, clone=False)     # the run's own clone
        if git(repo, "checkout", "-q", "-B", "main", project.plan.baseline).returncode != 0:
            raise RunRefused("the baseline could not be checked out as main")
        rec["stage"] = "admission"
        rec["admission"] = admit(project, calibrations() if cals is None else cals)
        if not rec["admission"]["admitted"]:
            raise RunRefused(f"the plan is not admitted (RFC §12): {rec['admission']['failed']}")
        rec["stage"] = "test interpreter"
        python = probe_interpreter(out / "test-python")
        exe = client_exe or client_on_path(settings)
        if settings.confinement is not None:    # V2.1 (F): measured before the first provider request, never assumed —
            rec["stage"] = "confinement"        # with the sessions' client and a worktree of the run's repository
            rec["confinement"] = confine.measure(settings.confinement, out / "confinement", exe, repo)
            if rec["confinement"]["problems"]:
                raise RunRefused("confinement was asked for and is not provided: " + "; ".join(rec["confinement"]["problems"]))
        rec["stage"] = "preflight"
        if not exe:
            raise RunRefused("the client (opencode) is not on the PATH the run gives it")
        # the client's own configuration decides where its sessions go: it must be the endpoint the preflight attests
        configured, config_key = client.configured_provider(settings.provider)
        if configured != settings.endpoint:
            raise RunRefused(f"the client's configuration sends provider {settings.provider} to {configured}, not to the "
                             f"attested endpoint {settings.endpoint}")
        key = os.environ.get(settings.api_key_env, "") if settings.api_key_env else config_key
        transport = transport or preflight.http_transport(settings.endpoint, key)
        pre = preflight.run(settings.route, settings.chat_probes, transport, out / "preflight", settings.served_model,
                            settings.listed_owner)
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
                               lambda: sum(1 for e in run.events if e.type == "provider/request"), inherited)
        kw = {"model": settings.route,
              "env": client.environment(settings.client_env, client.overlay(settings.route, settings.model_limit)),
              "budget": budget, "turn_cap": settings.max_turns_per_session, "exe": exe,
              # the operator's values the client receives, and the provider key: never left in a session's evidence
              "secrets": tuple(v for v in (*(os.environ.get(n, "") for n in settings.client_env), key) if len(v) >= 8),
              **({"confine": settings.confinement} if settings.confinement is not None else {})}
        developer = ad.Developer(run, project, logs, kw, settings.timeouts_s["developer"])
        # V2.1 (F): confined, the model reviewer's checkout is bound read-only — it writes nothing of the host
        rkw = {**kw, "workspace_writable": False} if settings.confinement is not None else kw
        reviewer = ad.Reviewer(run, project, logs, rkw, settings.timeouts_s["reviewer"], review=settings.review,
                               probe_timeout_s=settings.timeouts_s["probe"], interpreter=sys.executable,
                               route={"url": settings.endpoint, "token": key, "model": settings.model,
                                      "env": {k: v for k, v in client.environment(settings.client_env, {}).items()
                                              if k != "OPENCODE_CONFIG_CONTENT"}})
        adapters = sr.Adapters(developer, reviewer, scanner, merger, ws)
        factories = {e.probe_id: (lambda on_range, scratch, f=e.factory: f(on_range=on_range, scratch=scratch))
                     for e in catalog.CATALOG}
        env = ExecutionEnv(sys.executable, settings.timeouts_s["probe"], Enforcement.PARTIAL)   # V2.1: never the tests' venv
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
                                    te.Dependencies(frozenset(), frozenset(project.product_roots)), te.UNITTEST,
                                    test_interpreter=python)
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
            try:    # V2.1 (D): what the run used, from its evidence; a fault here never costs the record
                rec["usage"], rec["no_progress"] = usage.usage(out, events, settings.prices, rec), usage.no_progress(events)
                if continues:     # each run of the lineage once: the predecessor's lineage, then this run's own
                    rec["lineage_usage"] = lineage.usage_lineage(predecessor, out, rec["usage"], settings.prices)
            except Exception as e:  # noqa: BLE001 — named in the record, re-derived by --verify
                rec["usage"] = {"error": f"{type(e).__name__}: {e}"[:500]}
            (out / "RUN.json").write_text(json.dumps(rec, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
            try:    # after the record: the manifest binds it; its digest is the anchor the operator keeps
                (out / MANIFEST).write_text(json.dumps(evidence_manifest(out), indent=1, sort_keys=True) + "\n", encoding="utf-8")
            except OSError:
                if failure is None:
                    raise
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
    return {"path": path.relative_to(path.parents[2]).as_posix(), "sha256": _sha(data), "lines": data.count(b"\n"),
            "closed": closed}


def _close(run) -> dict:
    """Close the run and name its journal (used where the closing and the record are one step)."""
    return {"journal": _journal_info(run, _close_run(run))}
