"""The E2 campaign driver (docs/v2.1/EXPERIMENT-PLAN.md, owner decision 2026-10-18): arms direct / aisef / aisef+ on
the same client, model, task and budget, run one after the other from a CAMPAIGN.json, every record under OUT.

    python -P validation/experiments/campaign.py run --campaign CAMPAIGN.json --out OUT --client-exe PATH
            --client-version STR [--max-runs N] [--stop-on-unknown]   # --max-runs 0: seal and check every manifest, start nothing
    python -P validation/experiments/campaign.py replay --out OUT        # every candidate evaluated again, offline
    python -P validation/experiments/campaign.py summary --out OUT       # one JSON row per workload x arm

CAMPAIGN.json: {"runs": [{"run_id", "workload": {"id"?, "repo", "commit", "requirements_path", "task_text"},
"arm": "direct" | "aisef" | "aisef+", "settings_path", "bundle_path", "evaluator_path", "rep"}, ...]} — paths relative
to the file. The runs of one workload and rep are one pair (`pair_id`): their manifests may differ only in the arm and
its settings' `review` (`variable_under_test.value`); everything else — client, route, source commit, evaluator, bundle,
the settings without `review`, the budget — is sealed equal, or the campaign refuses to start (harness.pair_problems).

Before any paid work: --client-exe is a file named exactly `opencode`, and the PATH every arm's subprocess gets — its
directory, then only python's and git's, then /usr/bin:/bin — resolves `opencode` to that same file (an aisef arm finds
the client on PATH, app/run.client_on_path; the direct arm is handed it: one binary, its realpath and sha256 in every
manifest's `client`); each run's bundle (and its evaluator, when it carries a plan) names the workload's commit as its
plan baseline; every run's manifest is built, sealed and written to OUT/<run_id>/MANIFEST.json (once: an existing one
is reused, never rewritten), checked and paired. Then, run by run: a fresh clone of the workload at its commit with no
remote, the arm, the candidate frozen (commit, tree, archive and file digests), the hidden evaluator on it, the leak
scan over the arm's session streams, the usage read (direct: the preflight's ledger and the client's streams through
app/client.Budget and app/usage; aisef: RUN.json), and OUT/<run_id>/RESULT.json — written for a failed arm too. A run
whose RESULT.json exists is skipped (resume). The driver stops at OUT/STOP, at --max-runs, and (--stop-on-unknown)
after an arm whose cost is not known and whose spend is unaccounted. Never the source repository itself; nothing only
in a temporary directory.

Both arms sample one gate before any session: the client's configured endpoint for the settings' provider is the
settings' endpoint, and the kernel's preflight (aisef2/app/preflight) attests the route — the aisef arms inside `aisef
run` (app/run.execute, stage preflight), the direct arm here (<arm>/preflight/PREFLIGHT.json, its requests in the arm's
budget). Refused at the gate, an arm is a failed one: candidate null, `identity: OPAQUE`, its record kept. So the
manifests' model identity is `provider_reported` for every arm: what the gate measures is the provider's own report
(the listing, the served model, one deployment fingerprint) — never a verification of weights — and a router alias
whose backing model varies per request fails it.

An aisef arm's candidate is RUN.json's `final_main` only when its `delivery_verdict` is PASS (app/run.delivery: PASS,
FAIL or NOT_REACHED): the kernel clones before its gates and leaves `final_main` at the baseline after an identity
stop, a budget stop or a refusal (closure-evidence/v2/v2.1/canary/tier-1/run/RUN.json) — that is a failed arm, not a
candidate of 0/N. The plan's false rejection (EXPERIMENT-PLAN.md): for every story the run rolled back, the candidates
the journal names for it are looked up in the arm's repository and, present, put to the hidden evaluator
(`false_rollbacks` in RESULT.json and the summary)."""

from __future__ import annotations

import argparse
import datetime
import functools
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aisef2.app import preflight  # noqa: E402
from validation.experiments import harness as H  # noqa: E402

NO_EVALUATION = {"total": None, "satisfied": None, "not_satisfied": None}
#: the direct arm's gate (an offline test stubs it here; the kernel's own call is inside `aisef run`)
preflight_run = preflight.run
#: every manifest's model identity: the one gate both arms sample, and what it is not
MODEL_IDENTITY = {
    "identity_confidence": "provider_reported",
    "reason": "every arm samples the kernel's preflight gate (aisef2/app/preflight: the route's model listed, every chat "
              "probe served by settings provider.served_model under one deployment fingerprint, or the arm is refused with "
              "candidate null) — the provider's own report, never a verification of weights; a router alias whose backing "
              "model varies per request fails it"}


def client_path(exe: str) -> tuple[str, str, str | None]:
    """The client every arm runs and the PATH their subprocesses get: --client-exe's own directory first, then only what
    python and git need, then /usr/bin:/bin — so the `opencode` an aisef arm finds on PATH (app/run.client_on_path) is
    the file the direct arm is handed. (realpath, PATH, why it is refused | None)."""
    p = pathlib.Path(exe)
    real = os.path.realpath(exe)
    path = os.pathsep.join([os.path.dirname(os.path.abspath(exe)), os.path.dirname(sys.executable),
                            os.path.dirname(shutil.which("git") or "/usr/bin/git"), "/usr/bin", "/bin"])
    if p.name != "opencode" or not p.is_file():
        return real, path, f"--client-exe {exe} is a file whose basename is exactly 'opencode' (the name every arm resolves)"
    found = shutil.which("opencode", path=path)
    if not found or os.path.realpath(found) != real:
        return real, path, f"`opencode` on the arms' PATH ({path}) resolves to {found}, not to --client-exe {real}"
    return real, path, None


@functools.lru_cache(maxsize=None)
def client_identity(exe: str) -> dict:
    """What binds the client across the pair (harness.pair_problems: `client` is not PAIR_FREE)."""
    real = os.path.realpath(exe)
    return {"exe": real, "sha256": H.sha(pathlib.Path(real).read_bytes())}


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def read_json(p: pathlib.Path):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def write_once(p: pathlib.Path, doc) -> None:
    """A record is written once (mode x) and never rewritten."""
    with pathlib.Path(p).open("x", encoding="utf-8") as f:
        f.write(json.dumps(doc, indent=1, sort_keys=True) + "\n")


def load_campaign(path: pathlib.Path) -> list[dict]:
    """The runs, every path made absolute against the campaign file."""
    base = path.resolve().parent
    runs = []
    for r in read_json(path)["runs"]:
        w = dict(r["workload"])
        w["repo"] = str((base / w["repo"]).resolve())
        w.setdefault("id", pathlib.Path(w["repo"]).name)
        runs.append({**r, "workload": w, **{k: str((base / r[k]).resolve()) for k in ("settings_path", "bundle_path", "evaluator_path")}})
    ids = [r["run_id"] for r in runs]
    if len(set(ids)) != len(ids):
        raise ValueError(f"run_id is unique: {sorted(i for i in ids if ids.count(i) > 1)}")
    return runs


def pair_id(run: dict) -> str:
    return f"{run['workload']['id']}:rep{run['rep']}"


def frozen(repo: pathlib.Path, sha: str) -> dict:
    """The candidate frozen: commit, tree id, `git archive` digest and the extracted files' digest (the working tree
    of a run's clone is not asked to be clean: main moved under it by the kernel's merges)."""
    full = H.git(repo, "rev-parse", "--verify", f"{sha}^{{commit}}")
    archive = H.git(repo, "archive", "--format=tar", full, data=True)
    with tempfile.TemporaryDirectory() as t:
        tar = pathlib.Path(t) / "a.tar"
        tar.write_bytes(archive)
        with tarfile.open(tar) as f:
            f.extractall(pathlib.Path(t) / "x", filter="data")
        files = H.tree_digest(pathlib.Path(t) / "x")
    return {"commit": full, "tree": H.git(repo, "rev-parse", f"{full}^{{tree}}"), "archive_sha256": H.sha(archive),
            "archive_size": len(archive), "files_sha256": files}


def manifest(run: dict, n_runs: int, a: argparse.Namespace) -> dict:
    """One run's sealed manifest: every KEYS field of harness (the client's version is the operator's word,
    --client-version: the driver never runs the client itself; its bytes are hashed, MODEL_IDENTITY is the gate's)."""
    from aisef2.app import settings as S
    st = S.read(run["settings_path"])
    w = run["workload"]
    repo = pathlib.Path(w["repo"])
    policy = {k: v for k, v in st.content.items() if k != "review"}
    argv = command(run, a)
    return H.seal({
        "format": H.FORMAT, "experiment_id": run["run_id"], "parent_experiment_id": None,
        "pair": {"pair_id": pair_id(run), "arm": run["arm"]},
        "workload": {"id": w["id"], "requirements_path": w["requirements_path"],
                     "requirements_sha256": H.sha(H.git(repo, "show", f"{w['commit']}:{w['requirements_path']}", data=True)),
                     "task_sha256": H.sha(w["task_text"].encode("utf-8"))},
        "source": H.source_identity(repo, w["commit"]),
        "evaluator": H.evaluator_identity(pathlib.Path(run["evaluator_path"])),
        "bundle": {"sha256": H.sha(pathlib.Path(run["bundle_path"]).read_bytes())},
        "policy": {"sha256": H.sha(H.canonical(policy)), "note": "the settings without `review` (the arm's variable)"},
        "command": {"argv": argv, "sha256": H.sha(H.canonical(argv))},
        "client": {"name": st.client, "version": a.client_version, "adapter_version": "aisef2.app.client", **client_identity(a.client_exe)},
        "model": {"declared": st.model, "route": st.route, **MODEL_IDENTITY},
        "environment": {"python": platform.python_version(), "system": platform.system().lower(), "network": "provider",
                        "env_allowlist": list(st.client_env)},
        "variable_under_test": {"name": "orchestration", "value": {"arm": run["arm"], "review": st.content.get("review")}},
        "limits": {"budget": dict(st.budget), "max_turns_per_session": st.max_turns_per_session, "timeouts_s": dict(st.timeouts_s)},
        "stop_rule": {"kind": "fixed_n", "n": n_runs}, "created_at": now()})


def command(run: dict, a: argparse.Namespace) -> list[str]:
    """The argv the arm runs (recorded; `<ws>` and `<out>` stand for the run's own directories)."""
    if run["arm"] == "direct":
        return [a.client_exe, "run", "--format", "json", "--model", "<route>", "--title", "developer direct", "--dir", "<ws>", "<task>"]
    return [sys.executable, "-P", "-m", "aisef", "run", "--project", run["bundle_path"], "--settings", run["settings_path"],
            "--repo", "<ws>", "--out", "<out>/run", "--anchor-out", "<out>/run.anchor"]


def baseline_problems(run: dict) -> list[str]:
    """The bundle starts from the workload's commit — its plan.baseline is that full sha — and so does the evaluator
    when it carries a plan; else the run cannot start and no manifest of it is written."""
    w = run["workload"]
    full = H.git(w["repo"], "rev-parse", "--verify", f"{w['commit']}^{{commit}}")
    out = []
    for name in ("bundle_path", "evaluator_path"):
        base = (read_json(run[name]).get("plan") or {}).get("baseline")
        if (base is None and name == "bundle_path") or (base is not None and base != full):
            out.append(f"{name} {run[name]}: plan.baseline {base} is not the workload's commit {full}")
    return out


def seal_all(runs: list[dict], out: pathlib.Path, a: argparse.Namespace) -> tuple[dict[str, dict], list[str]]:
    """Every run's manifest sealed and written (or reused), checked, and paired: the problems that forbid a start."""
    manifests, problems = {}, []
    for r in runs:
        bad = baseline_problems(r)
        if bad:
            problems += [f"{r['run_id']}: {x}" for x in bad]
            continue
        p = out / r["run_id"] / "MANIFEST.json"
        if p.exists():
            m = read_json(p)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            m = manifest(r, len(runs), a)
            write_once(p, m)
        manifests[r["run_id"]] = m
        problems += [f"{r['run_id']}: {x}" for x in H.check(m)]
    groups: dict[str, list[dict]] = {}
    for r in runs:
        if r["run_id"] in manifests:
            groups.setdefault(pair_id(r), []).append(r)
    for pid, members in groups.items():
        first = manifests[members[0]["run_id"]]
        for r in members[1:]:
            problems += [f"pair {pid} ({members[0]['run_id']} vs {r['run_id']}): {x}"
                         for x in H.pair_problems(first, manifests[r["run_id"]])]
    return manifests, problems


def direct(run: dict, m: dict, arm_dir: pathlib.Path, a: argparse.Namespace) -> dict:
    """Arm direct behind the aisef arms' gate (app/run.execute, stage preflight): the client's configured endpoint for
    the settings' provider is the settings' endpoint, then the kernel's preflight attests the route — its ledger and
    PREFLIGHT.json under <arm>/preflight, its requests the base of the arm's budget and in its usage. Refused at
    either, the arm is a failed one (candidate null, `identity: OPAQUE`, ARM.json says why) and no session starts.
    Attested: harness.direct_arm — the client once on the public task, under the settings' route, the arms' PATH,
    budget and turn cap; a session is one provider request (app/client), so the budget counts the streams it started
    — with no journal, a requests() of 0 would read every session as unaccounted and stop it."""
    from aisef2.app import client, settings as S, usage as U
    st = S.read(run["settings_path"])
    sessions, started = arm_dir / "sessions", time.time()
    configured, config_key = client.configured_provider(st.provider)
    key = os.environ.get(st.api_key_env, "") if st.api_key_env else config_key
    rec: dict = {"arm": "direct", "manifest_sha256": m["manifest_sha256"], "candidate": None, "configured_endpoint": configured}
    pre = None
    if configured != st.endpoint:
        rec["error"] = (f"the client's configuration sends provider {st.provider} to {configured}, not to the settings' "
                        f"endpoint {st.endpoint}: no session started")
    else:
        try:
            pre = preflight_run(st.route, st.chat_probes, preflight.http_transport(st.endpoint, key), arm_dir / "preflight",
                                st.served_model, st.listed_owner)
        except preflight.IdentityStop as e:
            rec.update(identity="OPAQUE", error=f"identity: OPAQUE — {e}")
        else:
            rec["preflight"] = {"verdict": pre["verdict"], "problems": pre["problems"], "accounting": pre["accounting"]}
            if pre["verdict"] != "ATTESTED" or pre["accounting"]["unaccounted"]:
                rec.update(identity="OPAQUE", error="identity: OPAQUE — the route is not attested: " + "; ".join(
                    pre["problems"] + [f"preflight requests unaccounted: {pre['accounting']['unaccounted']}"] * bool(pre["accounting"]["unaccounted"])))
    budget = client.Budget(st.budget, pre["accounting"] if pre else dict.fromkeys(client.Budget.KEYS, 0), sessions,
                           requests=lambda: len(list(sessions.glob("*.jsonl"))) if sessions.is_dir() else 0)
    if "error" in rec:
        arm_dir.mkdir(parents=True, exist_ok=True)
        write_once(arm_dir / "ARM.json", rec)
    else:
        env = {**client.environment(st.client_env, client.overlay(st.route, st.model_limit)), "PATH": a.path}
        kw = {"model": st.route, "env": env, "budget": budget, "turn_cap": st.max_turns_per_session,
              "secrets": tuple(v for v in (*(os.environ.get(n, "") for n in st.client_env), key) if len(v) >= 8)}
        rec.update(H.direct_arm(m, arm_dir, task=run["workload"]["task_text"], client_exe=a.client_exe, session_kw=kw,
                                timeout_s=st.timeouts_s["developer"], configured_endpoint=configured, preflight=rec["preflight"]))
    finished = time.time()
    n = len(list(sessions.glob("*.jsonl"))) if sessions.is_dir() else 0
    usage = U.usage(arm_dir, [{"type": "provider/request", "data": {}}] * n, st.prices, {"started": started, "finished": finished})
    return {**rec, "sessions": sessions, "repo": arm_dir / "ws",
            "usage": {"budget": budget.account(), **usage,
                      "source": "app/client.Budget over the preflight's ledger and the arm's session streams; app/usage.usage"}}


def aisef(run: dict, m: dict, arm_dir: pathlib.Path, a: argparse.Namespace) -> dict:
    """Arms aisef and aisef+: `aisef run` as a subprocess on a fresh clone at the baseline (the canaries' invocation,
    closure-evidence/v2/v2.1/canary/*/run-tier*.sh) with no remote, under the arms' PATH; stdout, stderr and the exit
    kept beside the run directory; the record from RUN.json (aisef_record)."""
    if arm_dir.exists():
        raise ValueError(f"{arm_dir} exists: an arm's directory is never reused")
    arm_dir.mkdir(parents=True)
    ws = arm_dir / "ws"
    subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", m["source"]["repo"], str(ws)], check=True, capture_output=True)
    H.git(ws, "checkout", "--quiet", "-B", "main", m["source"]["commit"])
    H.git(ws, "remote", "remove", "origin")      # the kernel clones ws again; two hops from a session, none to the source
    argv = [sys.executable, "-P", "-m", "aisef", "run", "--project", run["bundle_path"], "--settings", run["settings_path"],
            "--repo", str(ws), "--out", str(arm_dir / "run"), "--anchor-out", str(arm_dir / "run.anchor")]
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1", "PATH": a.path}
    started = time.time()
    with (arm_dir / "run.stdout").open("wb") as o, (arm_dir / "run.stderr").open("wb") as e:
        p = subprocess.run(argv, stdout=o, stderr=e, env=env, cwd=str(arm_dir))
    finished = time.time()
    (arm_dir / "exit.txt").write_text(f"{p.returncode}\n", encoding="utf-8")
    return aisef_record(run, m, arm_dir, p.returncode, round(finished - started, 3))


def aisef_record(run: dict, m: dict, arm_dir: pathlib.Path, exit_code: int | None, wall_s: float | None) -> dict:
    """An aisef arm's record from <arm>/run/RUN.json. The candidate is the run's `final_main` only when its
    `delivery_verdict` is PASS (app/run.delivery: PASS, FAIL, NOT_REACHED): the kernel clones before its gates and sets
    `final_main` to its clone's main whatever stopped the run — an identity stop, a budget stop, a refusal leave it at
    the baseline (closure-evidence/v2/v2.1/canary/tier-1/run/RUN.json: NOT_REACHED, final_main = baseline). That, or a
    run that left no RUN.json, is a failed arm: candidate null, the evaluation not run, the failure in the record."""
    from aisef2.app import lineage
    run_json = arm_dir / "run" / "RUN.json"
    rec = read_json(run_json) if run_json.exists() else {}
    verdict = rec.get("delivery_verdict")
    out = {"arm": run["arm"], "manifest_sha256": m["manifest_sha256"], "candidate": rec.get("final_main") if verdict == "PASS" else None,
           "exit": exit_code, "wall_s": wall_s, "sessions": arm_dir / "run" / "sessions", "repo": arm_dir / "run" / "repo",
           "journal": arm_dir / "run" / lineage.JOURNAL,
           "run": {**{k: rec.get(k) for k in ("delivery_verdict", "delivery_blocked_by", "story_outcomes", "final_main",
                                                "failure", "budget_stop", "stage")},
                   "preflight_verdict": (rec.get("preflight") or {}).get("verdict")},
           "usage": {"budget": rec.get("budget"), **(rec.get("usage") or {}), "source": "<out>/run/RUN.json usage and budget (app/run.execute)"}}
    if verdict != "PASS":
        out["error"] = (f"aisef run not delivered: delivery_verdict={verdict!r} stage={rec.get('stage')!r} "
                        f"failure={rec.get('failure')!r} blocked_by={rec.get('delivery_blocked_by')!r}" if rec
                        else f"aisef run left no RUN.json (exit {exit_code})")[:2000]
    return out


def rollback(arm_rec: dict) -> bool:
    """An aisef arm whose RUN.json shows a story rolled back (story_outcomes, the journal's story/rollback)."""
    return any("ROLLBACK" in v for v in ((arm_rec.get("run") or {}).get("story_outcomes") or {}).values())


def journal_events(path: pathlib.Path) -> list[dict]:
    """The journal's rows, raw (format 3: one {"chain", "event"} per line); RUN.json's journal.sha256 binds the file
    and `aisef run --verify` checks the chain — this reader only looks events up."""
    return [json.loads(line)["event"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def false_rollbacks(arm_rec: dict, evaluator: dict) -> list[dict]:
    """EXPERIMENT-PLAN.md's false rejection, per story the run rolled back (RUN.json story_outcomes holding ROLLBACK):
    the candidates the journal names for it — `proof/verified` rows' data.candidate, the only rows that carry the
    candidate's sha (orchestrate/proof.prove); a story the developer or the admission failed names none, 'candidate not
    in journal' — each looked up in the arm's repository (`git cat-file -e`: released worktrees leave the object until
    a gc; gone, 'candidate object gone') and, present, put to the hidden evaluator (harness.evaluate). A story is a
    false rollback when any candidate of it satisfies every hidden contract — all of them, not only the story's own:
    simpler, and the evaluator is the workload's whole hidden truth."""
    outcomes = (arm_rec.get("run") or {}).get("story_outcomes") or {}
    rolled = sorted(s for s, v in outcomes.items() if "ROLLBACK" in v)
    if not rolled:
        return []
    repo, journal = pathlib.Path(arm_rec["repo"]), pathlib.Path(arm_rec["journal"])
    events = journal_events(journal) if journal.is_file() else []
    out = []
    for s in rolled:
        shas = list(dict.fromkeys(e["data"]["candidate"] for e in events
                                  if e["type"] == "proof/verified" and e["data"].get("story_id") == s and e["data"].get("candidate")))
        row: dict = {"story": s, "outcomes": outcomes[s], "candidates": [], "false_rollback": False}
        if not shas:
            row["note"] = "candidate not in journal"
        for sha in shas:
            present = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True).returncode == 0
            c: dict = {"sha": sha, "present": present, "evaluation": None}
            if present:
                ev = H.evaluate(repo, sha, evaluator)
                c["evaluation"] = {k: ev[k] for k in ("total", "satisfied", "not_satisfied")}
                c["passes"] = bool(ev["total"]) and not ev["not_satisfied"]
                row["false_rollback"] = row["false_rollback"] or c["passes"]
            else:
                c["note"] = "candidate object gone"
            row["candidates"].append(c)
        out.append(row)
    return out


def unknown_spend(usage: dict) -> bool:
    """Cost not known and spend unaccounted (the plan's stop rule with --stop-on-unknown)."""
    cost, spent = usage.get("cost") or {}, (usage.get("budget") or {}).get("spent") or {}
    return cost.get("status") != "known" and bool(spent.get("unaccounted") or cost.get("sessions_unknown"))


def record(run: dict, m: dict, arm_rec: dict, out: pathlib.Path, error: str | None = None) -> dict:
    """After an arm: the candidate frozen, the hidden evaluator on it, the leak scan, the result record (harness.result)
    with its wall time and raw exit, written once; one line to OUT/campaign.log."""
    evaluator = read_json(run["evaluator_path"])
    repo, candidate, sessions = arm_rec.get("repo"), arm_rec.get("candidate"), arm_rec.get("sessions")
    error = error or arm_rec.get("error")
    evaluation, froze, rolled = None, None, []
    try:
        if candidate and repo and (pathlib.Path(repo) / ".git").exists():
            froze = frozen(pathlib.Path(repo), candidate)
            evaluation = H.evaluate(pathlib.Path(repo), candidate, evaluator)
        rolled = false_rollbacks(arm_rec, evaluator)
    except Exception as e:  # noqa: BLE001 — a candidate that does not evaluate is recorded as such
        error = f"{error + '; ' if error else ''}evaluate: {type(e).__name__}: {e}"[:2000]
    leaked = H.leaks(pathlib.Path(sessions), evaluator) if sessions and pathlib.Path(sessions).is_dir() else []
    res = H.result(m, arm_rec, evaluation or NO_EVALUATION, arm_rec.get("usage") or {}, leaked)
    res.update(run_id=run["run_id"], workload=run["workload"]["id"], rep=run["rep"], exit=arm_rec.get("exit"),
               wall_s=arm_rec.get("wall_s"), candidate_frozen=froze, evaluator_path=run["evaluator_path"],
               candidate_repo=str(pathlib.Path(repo).resolve().relative_to(out.resolve())) if repo else None,
               aisef_run=arm_rec.get("run"), rollback=rollback(arm_rec), false_rollbacks=rolled,
               identity=arm_rec.get("identity"), configured_endpoint=arm_rec.get("configured_endpoint"),
               preflight=arm_rec.get("preflight"), self_reported=arm_rec.get("self_reported"), error=error, recorded_at=now())
    write_once(out / run["run_id"] / "RESULT.json", res)
    ev = res["evaluation"]
    cost = (res["usage"].get("cost") or {}).get("value")
    with (out / "campaign.log").open("a", encoding="utf-8") as f:
        f.write(f"{now()} {run['run_id']} {run['arm']} workload={run['workload']['id']} rep={run['rep']} exit={res['exit']} "
                f"candidate={(res['candidate'] or 'none')[:12]} evaluation={ev['satisfied']}/{ev['total']} valid={res['valid']} "
                f"rollback={res['rollback']} wall_s={res['wall_s']} cost={cost} error={error!r}\n")
    return res


ARMS = {"direct": direct, "aisef": aisef, "aisef+": aisef}


def run_campaign(a: argparse.Namespace) -> int:
    out = pathlib.Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    runs = load_campaign(pathlib.Path(a.campaign))
    copy = out / "CAMPAIGN.json"
    data = pathlib.Path(a.campaign).read_bytes()
    if copy.exists():
        if copy.read_bytes() != data:
            print(f"refused: {copy} differs from {a.campaign}: a campaign is one list of runs", file=sys.stderr)
            return 2
    else:
        copy.write_bytes(data)
    real, a.path, why = client_path(a.client_exe)
    if why:
        print(f"refused: {why}", file=sys.stderr)
        return 2
    print(f"campaign: client {real} sha256 {client_identity(a.client_exe)['sha256']}; arms' PATH {a.path}")
    manifests, problems = seal_all(runs, out, a)
    for p in problems:
        print(f"FAIL  {p}")
    if problems:
        print("campaign: REFUSED (no arm started)")
        return 2
    print(f"campaign: {len(runs)} manifests sealed and paired")
    done = 0
    for r in runs:
        if (out / r["run_id"] / "RESULT.json").exists():
            continue
        if (out / "STOP").exists():
            print(f"campaign: STOP file at {out / 'STOP'}: stopped before {r['run_id']}")
            return 3
        if done >= a.max_runs:
            print(f"campaign: --max-runs {a.max_runs} reached: stopped before {r['run_id']}")
            return 3
        arm_dir = out / r["run_id"] / "arm"
        arm_rec, error = {"arm": r["arm"], "manifest_sha256": manifests[r["run_id"]]["manifest_sha256"], "candidate": None}, None
        print(f"{now()} {r['run_id']} {r['arm']}: starting")
        try:
            arm_rec = ARMS[r["arm"]](r, manifests[r["run_id"]], arm_dir, a)
        except Exception as e:  # noqa: BLE001 — a failed arm is kept with its record
            error = f"{type(e).__name__}: {e}"[:2000]
            arm_rec.update(sessions=arm_dir / ("sessions" if r["arm"] == "direct" else "run/sessions"),
                           repo=arm_dir / ("ws" if r["arm"] == "direct" else "run/repo"))
        res = record(r, manifests[r["run_id"]], arm_rec, out, error)
        done += 1
        ev = res["evaluation"]
        print(f"{now()} {r['run_id']} {r['arm']}: exit={res['exit']} evaluation={ev['satisfied']}/{ev['total']} valid={res['valid']}"
              + (f" error={error}" if error else ""))
        if a.stop_on_unknown and unknown_spend(res["usage"]):
            print(f"campaign: {r['run_id']}: cost not known and spend unaccounted (--stop-on-unknown): stopped")
            return 3
    print(f"campaign: done ({done} arms this invocation)")
    return 0


def results(out: pathlib.Path) -> list[dict]:
    return [read_json(p) for p in sorted(out.glob("*/RESULT.json"))]


def replay(a: argparse.Namespace) -> int:
    """Every recorded candidate evaluated again, offline; what differs is printed (nothing: every result replays)."""
    out = pathlib.Path(a.out).resolve()
    bad = 0
    for res in results(out):
        if not res.get("candidate"):
            continue
        diffs = H.replay(res, out / res["candidate_repo"], read_json(res["evaluator_path"]))
        for d in diffs:
            print(f"{res['run_id']}: {d}")
        bad += bool(diffs)
    return 1 if bad else 0


def summary(a: argparse.Namespace) -> int:
    """One JSON row per workload x arm, from the RESULT.json records only."""
    groups: dict[tuple, list[dict]] = {}
    for res in results(pathlib.Path(a.out).resolve()):
        groups.setdefault((res["workload"], res["arm"]), []).append(res)
    for (w, arm), rs in sorted(groups.items()):
        ev = [r["evaluation"] for r in rs if r["evaluation"]["total"]]
        tokens: dict[str, int] = {}
        for r in rs:
            for k, v in ((r["usage"].get("tokens") or {}).items()):
                tokens[k] = tokens.get(k, 0) + int(v or 0)
        costs = [(r["usage"].get("cost") or {}).get("value") for r in rs]
        print(json.dumps({
            "workload": w, "arm": arm, "n": len(rs), "evaluated": len(ev),
            "satisfied_mean": round(sum(e["satisfied"] / e["total"] for e in ev) / len(ev), 4) if ev else None,
            "escaped_defects": sum(len(e["not_satisfied"]) for e in ev),
            "false_rollbacks": sum(1 for r in rs for s in (r.get("false_rollbacks") or []) if s["false_rollback"]),
            "tokens": tokens,
            "requests": sum(int(((r["usage"].get("budget") or {}).get("spent") or {}).get("provider_requests") or 0) for r in rs),
            "wall_s": round(sum(float(r["wall_s"] or 0) for r in rs), 3),
            "cost": None if any(c is None for c in costs) else round(sum(costs), 6),
            "valid": all(r["valid"] for r in rs), "failed": sum(1 for r in rs if r.get("error"))}, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="campaign.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="seal every manifest, then run the arms one after the other")
    r.add_argument("--campaign", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--client-exe", required=True, help="the client binary, a file named exactly opencode, every arm runs")
    r.add_argument("--client-version", required=True, help="what `opencode --version` printed for the operator")
    r.add_argument("--max-runs", type=int, default=10**9)
    r.add_argument("--stop-on-unknown", action="store_true")
    r.set_defaults(fn=run_campaign)
    for name, fn in (("replay", replay), ("summary", summary)):
        s = sub.add_parser(name)
        s.add_argument("--out", required=True)
        s.set_defaults(fn=fn)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
