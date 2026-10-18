"""Controlled experiments for AISEF (V2.1, proposal E): does AISEF beat the same agent run directly, at what cost?

Design rules (OpenResearch d52a053 / 951700e, mini-swe-agent 04d809c, MIT; reimplemented, nothing imported — see
docs/v2.1/UPSTREAM-RESEARCH.md):

* **Freeze before spend.** A manifest names everything an arm's outcome may depend on — source commit, tree and archive
  digest, the hidden evaluator, the bundle, policy, command, client, model (with how its identity is known), the
  environment, the one variable under test, limits and the stop rule — and is sealed by the sha256 of its canonical
  JSON. Results are a separate record citing that seal; a manifest is never edited after a result cites it.
* **Pairs differ in one thing.** Two arms of a pair are sibling manifests that may differ only in `arm`, `pair`,
  `variable_under_test.value` and their own seal: `pair_problems` names any other difference.
* **Arms share everything else:** the client binary and route, the provider settings, the baseline commit, the public
  task text and the budget caps. Arm `direct` runs the client once on the public task (no bundle, no contract, no hidden
  stimulus); the harness — not the agent — snapshots the workspace afterwards and the candidate is that commit. Arms
  `aisef` and `aisef+X` are `aisef run` under settings that differ by the one improvement X.
* **The evaluator is hidden.** It is an approved bundle of contracts that no arm sees; each candidate is evaluated by
  AISEF's own probes after it is frozen. `leaks` scans every session stream for the evaluator's distinctive strings.
* **Unknown is never 0** (app/usage). Failures are kept: every arm writes its record, whatever happened.
* **Replay before spend.** `replay` evaluates a recorded candidate again, offline; a paid campaign runs only under a
  budget the owner approved (docs/v2.1/EXPERIMENT-PLAN.md) — this module never starts one by itself.

    python -P validation/experiments/harness.py check MANIFEST.json
    python -P validation/experiments/harness.py pair CONTROL.json TREATMENT.json
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Mapping

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FORMAT = "aisef.experiment/1"
RESULT_FORMAT = "aisef.experiment-result/1"
ARMS = ("direct", "aisef", "aisef+")
IDENTITY = ("verified", "provider_reported", "unverified")
KEYS = ("format", "experiment_id", "parent_experiment_id", "pair", "workload", "source", "evaluator", "bundle", "policy",
        "command", "client", "model", "environment", "variable_under_test", "limits", "stop_rule", "created_at")
#: what may differ between the two arms of one pair
PAIR_FREE = ("pair.arm", "variable_under_test.value", "experiment_id", "manifest_sha256", "created_at", "command")


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def seal(manifest: Mapping) -> dict:
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    return {**body, "manifest_sha256": sha(canonical(body))}


def check(manifest: Mapping) -> list[str]:
    """Why a manifest is not a frozen experiment: a missing or extra key, a broken seal, an unknown arm, a model identity
    without its level and reason, an evaluator exposed to the developer."""
    out = []
    keys = set(manifest) - {"manifest_sha256"}
    if keys != set(KEYS):
        out.append(f"a manifest holds exactly {sorted(KEYS)} and its seal (missing {sorted(set(KEYS) - keys)}, "
                   f"extra {sorted(keys - set(KEYS))})")
    if manifest.get("format") != FORMAT:
        out.append(f"format is {FORMAT}")
    if seal(manifest).get("manifest_sha256") != manifest.get("manifest_sha256"):
        out.append("the seal does not bind this content: a frozen manifest is never edited")
    if (manifest.get("pair") or {}).get("arm") not in ARMS:
        out.append(f"pair.arm is one of {ARMS}")
    m = manifest.get("model") or {}
    if m.get("identity_confidence") not in IDENTITY or not m.get("reason"):
        out.append(f"model.identity_confidence is one of {IDENTITY}, with its reason")
    if (manifest.get("evaluator") or {}).get("exposed_to_developer") is not False:
        out.append("the evaluator is hidden from every arm (exposed_to_developer: false)")
    return out


def _flat(obj, prefix=""):
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            yield from _flat(v, f"{prefix}{k}.")
    else:
        yield prefix[:-1], obj


def pair_problems(control: Mapping, treatment: Mapping) -> list[str]:
    """Fields the two arms of one pair differ in besides the declared variable (and their identities)."""
    out = check(control) + check(treatment)
    a, b = dict(_flat(control)), dict(_flat(treatment))
    if (control.get("pair") or {}).get("pair_id") != (treatment.get("pair") or {}).get("pair_id"):
        out.append("the two manifests are not of one pair")
    if (control.get("variable_under_test") or {}).get("name") != (treatment.get("variable_under_test") or {}).get("name"):
        out.append("the two arms do not vary the same variable")
    differ = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k) and not k.startswith(PAIR_FREE))
    if differ:
        out.append(f"the arms differ beyond the variable under test: {differ[:10]}")
    return out


def git(repo, *args, data: bool = False):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
    return p.stdout if data else p.stdout.decode("utf-8").strip()


def tree_digest(directory: pathlib.Path) -> str:
    """The canonical content hash of an extracted tree: sorted (path, mode, sha256) — what a git tree id cannot promise
    after eol/filter conversions (research: OpenResearch rule 2 correction)."""
    rows = []
    for p in sorted(directory.rglob("*")):
        if p.is_file() and ".git" not in p.relative_to(directory).parts:
            rows.append(f"{p.relative_to(directory).as_posix()}\0{oct(p.stat().st_mode & 0o777)}\0{sha(p.read_bytes())}")
    return sha("\n".join(rows).encode("utf-8"))


def source_identity(repo: pathlib.Path, commit: str) -> dict:
    """The source an experiment starts from: a commit of a repository whose working tree is clean, its tree id, the
    digest and size of its `git archive`, and the canonical digest of the archive's files once extracted."""
    if git(repo, "status", "--porcelain"):
        raise ValueError(f"{repo}: the working tree is not clean — an experiment starts from a commit, never from edits")
    full = git(repo, "rev-parse", "--verify", f"{commit}^{{commit}}")
    archive = git(repo, "archive", "--format=tar", full, data=True)
    with tempfile.TemporaryDirectory() as t:
        tar = pathlib.Path(t) / "a.tar"
        tar.write_bytes(archive)
        with tarfile.open(tar) as f:
            f.extractall(pathlib.Path(t) / "x", filter="data")
        files = tree_digest(pathlib.Path(t) / "x")
    return {"repo": str(repo), "commit": full, "tree": git(repo, "rev-parse", f"{full}^{{tree}}"),
            "archive_sha256": sha(archive), "archive_size": len(archive), "files_sha256": files,
            "git_version": git(repo, "--version")}


def evaluator_identity(path: pathlib.Path) -> dict:
    """The hidden evaluator: an approved bundle whose contracts no arm sees; its digest binds the evaluation."""
    data = path.read_bytes()
    return {"sha256": sha(data), "contracts": len(json.loads(data)["contracts"]), "exposed_to_developer": False}


def distinctive(evaluator: Mapping) -> list[str]:
    """Strings of the evaluator a session should never contain: each contract's stimulus and observable, as JSON."""
    out = []
    for c in evaluator["contracts"]:
        for part in (c["stimulus"], c["observable"]):
            s = json.dumps(part, sort_keys=True)
            if len(s) >= 12:
                out.append(s)
    return out


def leaks(sessions: pathlib.Path, evaluator: Mapping) -> list[dict]:
    """Every session stream that holds a distinctive evaluator string (the stimulus reached an arm)."""
    marks = distinctive(evaluator)
    found = []
    for log in sorted(sessions.glob("*.jsonl")):
        text = log.read_text(encoding="utf-8", errors="replace")
        hits = [m for m in marks if m in text or m.replace('"', '\\"') in text]
        if hits:
            found.append({"session": log.name, "strings": len(hits)})
    return found


def evaluate(candidate_repo: pathlib.Path, revision: str, evaluator: Mapping) -> dict:
    """The hidden evaluator's contracts put to AISEF's probes on the candidate tree at `revision` (read from the
    object store; nothing of the candidate runs outside a probe)."""
    from aisef2.app import bundle
    from validation.qualification.release_acceptance import acceptance
    project = bundle.load(evaluator)
    with tempfile.TemporaryDirectory() as t:
        tree = pathlib.Path(t) / "tree"
        git(candidate_repo, "worktree", "add", "--detach", str(tree), revision)
        try:
            return acceptance(project, tree, git(candidate_repo, "rev-parse", revision))
        finally:
            git(candidate_repo, "worktree", "remove", "--force", str(tree))


def direct_arm(manifest: Mapping, out: pathlib.Path, *, task: str, client_exe: str, session_kw: dict,
               timeout_s: float) -> dict:
    """Arm `direct`: the client, once, on the public task, in a clone of the baseline; then the harness commits whatever
    the workspace holds — that commit is the candidate. The client's own "done" is recorded, never trusted."""
    from aisef2.app import client
    if (manifest.get("pair") or {}).get("arm") != "direct":
        raise ValueError("direct_arm runs a manifest of arm direct")
    if out.exists():
        raise ValueError(f"{out} exists: an arm's directory is never reused")
    out.mkdir(parents=True)
    src = manifest["source"]
    ws = out / "ws"
    subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", src["repo"], str(ws)], check=True, capture_output=True)
    git(ws, "checkout", "--quiet", "-B", "main", src["commit"])
    started = time.time()
    s = client.session("developer direct", task, str(ws), out / "sessions" / "direct.developer.1.jsonl", timeout_s,
                       exe=client_exe, **session_kw)
    git(ws, "add", "-A")
    changed = subprocess.run(["git", "-C", str(ws), "diff", "--cached", "--quiet"]).returncode != 0
    if changed:
        subprocess.run(["git", "-C", str(ws), "-c", "user.name=harness", "-c", "user.email=harness@aisef",
                        "commit", "--quiet", "-m", "direct arm: the workspace as the client left it"], check=True)
    rec = {"arm": "direct", "manifest_sha256": manifest["manifest_sha256"], "candidate": git(ws, "rev-parse", "HEAD"),
           "changed": changed, "exit": s.get("exit"), "self_reported": {"error": s.get("error"), "stopped": s.get("stopped")},
           "wall_s": round(time.time() - started, 3)}
    (out / "ARM.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return rec


def result(manifest: Mapping, arm_record: Mapping, evaluation: Mapping, usage: Mapping, leaked: list) -> dict:
    """The result record of one arm: it cites the sealed manifest and never edits it."""
    return {"format": RESULT_FORMAT, "manifest_sha256": manifest["manifest_sha256"], "arm": manifest["pair"]["arm"],
            "candidate": arm_record.get("candidate"), "evaluation": {k: evaluation[k] for k in ("total", "satisfied", "not_satisfied")},
            "escaped_defects": evaluation["not_satisfied"], "usage": usage, "evaluator_leaks": leaked,
            "valid": not leaked}


def replay(record: Mapping, candidate_repo: pathlib.Path, evaluator: Mapping) -> list[str]:
    """Evaluate a recorded candidate again, offline: what differs from the record (empty: it replays)."""
    again = evaluate(candidate_repo, record["candidate"], evaluator)
    return [f"{k}: recorded {record['evaluation'][k]!r}, replayed {again[k]!r}" for k in ("total", "satisfied", "not_satisfied")
            if record["evaluation"][k] != again[k]]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["check"] and len(argv) == 2:
        problems = check(json.loads(pathlib.Path(argv[1]).read_text(encoding="utf-8")))
    elif argv[:1] == ["pair"] and len(argv) == 3:
        problems = pair_problems(*(json.loads(pathlib.Path(p).read_text(encoding="utf-8")) for p in argv[1:]))
    else:
        print(__doc__.rsplit("\n\n", 1)[1], file=sys.stderr)
        return 2
    for p in problems:
        print(f"FAIL  {p}")
    print("experiment: " + ("PASS" if not problems else "FAIL"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
