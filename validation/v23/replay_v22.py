"""v2.3 ROUND-AUTH evidence: replay the v2.2 round's sealing-gated currency tests on v2.2.0 (W1-DESIGN.md §2.6).

    python3 -P validation/v23/replay_v22.py [--tree DIR] [--only ID ...] [--out FILE]
    python3 -P validation/v23/replay_v22.py --coverage [--out FILE]

The 11 tests of V22_REPLAYED bind committed records to the tree by the v2.2 selection rule (round v2.2 + HEAD:aisef2);
any kernel or ruling-row edit on the v2.3 branch turns them red, so seq 13 (ROUND-AUTH, draft) proposes to skip them
at HEAD and prove them where they are true: on v2.2.0 itself. This script is that proof, fail-closed:

* the tree is a fresh `git clone --shared --no-checkout` of this repository detached at V2_2_0, or `--tree DIR`;
  either way it MUST be at exactly V2_2_0 with no tracked change and no untracked or ignored file (a planted file or
  a stale `__pycache__` could change what the replayed code does) — else every problem is named and the exit is 1;
* each id MUST be in that tree's own `tests/v2/sealing_gate.py` GATED list (only the round's own gated tests replay);
* each test runs alone, under the tree's own `validation/v2/owned_run.py` (owned processes measured, none may
  outlive it), with AISEF_SEALING=1 and the mutation-worker env guard: no PATH directory holding an `opencode`
  executable, XDG_DATA_HOME/XDG_STATE_HOME/XDG_CACHE_HOME in a scratch directory, no PYTHONPATH/PYTHONHOME/
  PYTHONSTARTUP, no other AISEF_* variable, no bytecode written into the tree;
* a test PASSes only if it ran (>= 1), with no failure, error, skip, expected failure or unexpected success, and
  owned_run exited 0. Anything else is named — the script never masks a red;
* every record (a file under closure-evidence/) the test process opened is reported with its sha256, and MUST equal
  the bytes V2_2_0 committed (a corrupted record is named even when the test would not notice it).

Declared limitations: the read set is the test process's `open` audit events; records read by child processes or
through git objects (`git show`) are not listed (they are still covered by the test's own verdict and the clean-tree
rule). Evidence is normalized: tree-relative paths, no host name, user or local path; host = OS, kernel, arch,
python and git versions. Raw logs stay in the scratch directory and are referenced by sha256.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import datetime
import hashlib
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = "validation/v23/replay_v22.py"
SCHEMA = "aisef.v23.replay-v22/1"
V2_2_0 = "da3ea33f3b695aaca73e87a704145a0193aced23"
RECORDS_DIR = "closure-evidence/"
TIMEOUT_S = 3600
PASS, FAIL, SKIP, ERROR = "PASS", "FAIL", "SKIP", "ERROR"
COUNTERPARTS_REL = "tests/v23/test_v23_rounds.py"

#: the v2.2-round sealing-gated tests that cannot run at HEAD (W1-DESIGN.md §2.6, "Replayed at v2.2.0 (11)")
V22_REPLAYED = (
    "tests/v2/test_c2_delivery_experiment.py::PlanCorrection.test_the_committed_record_is_what_this_tree_derives",
    "tests/v2/test_c2_k_nowork_001.py::Record.test_the_record_binds_this_tree_and_shows_the_cases_red_before_and_green_after",
    "tests/v2/test_c2_orchestration_conformance.py::Record.test_15_the_record_binds_this_tree_and_old_and_new_agree_on_every_single_probe_story",
    "tests/v2/test_c2_p10_cohort_static.py::Record.test_the_evidence_record_re_derives_from_the_tree",
    "tests/v2/test_c2_p10_profile_freeze.py::Checker.test_the_evidence_record_re_derives",
    "tests/v2/test_c2_p5_acceptance.py::Acceptance.test_the_acceptance_re_derives_on_this_tree",
    "tests/v2/test_c2_p5_acceptance.py::KernelProvenance.test_on_this_tree_the_committed_proposal_is_current",
    "tests/v2/test_v21_mutation_runner.py::Classify.test_historical_records_read_as_before",
    "tests/v2/test_p5_plan_v22_proposal.py::Record.test_P5_8_committed_record_is_current",
    "tests/v2/test_p9_reproduction.py::KernelComparison.test_Q5_19_the_kernel_comparison_record_binds_this_tree",
    "tests/v2/test_v21_conformance_ruling.py::CommittedRuling.test_the_committed_ruling_is_what_this_tree_derives",
)

#: each replayed test -> (the currency-DAG node it binds, or None; its round-v2.3 counterpart method)
COUNTERPART = dict(zip(V22_REPLAYED, (
    ("PLAN", "RoundV23.test_PLAN"),
    ("K-NOWORK", "RoundV23.test_K_NOWORK"),
    ("ORCH", "RoundV23.test_ORCH"),
    ("P10-COHORT", "RoundV23.test_P10_COHORT"),
    ("P10-PROFILE", "RoundV23.test_P10_PROFILE"),
    ("P5-REVERIFICATION", "RoundV23.test_P5_REVERIFICATION"),
    ("P5-PROPOSAL", "RoundV23.test_P5_PROPOSAL_kernel_provenance"),
    (None, "RoundV23.test_MUTATION_historical"),
    ("P5-PROPOSAL", "RoundV23.test_P5_PROPOSAL_P5_8"),
    ("Q5", "RoundV23.test_Q5"),
    ("CONFORMANCE-RULING", "RoundV23.test_CONFORMANCE_RULING"),
), strict=True))

#: the only v2.2 assertion that is not round-aware: the legacy whole-file mutation rule. Every other assertion is
#: carried verbatim into its counterpart and runs under `version_forward.in_round("v2.3")`, where the node's own
#: check selects its verified chain head (W1-DESIGN.md §2.6). (test id, assertion as ast.unparse prints it) -> the
#: counterpart assertion that replaces it.
REBOUND = {
    ("tests/v2/test_v21_mutation_runner.py::Classify.test_historical_records_read_as_before",
     "self.assertEqual(m.problems_of(record, ROOT, phase), [])"):
        "self.assertEqual(self.f5_problems(m, record, phase), [])",
}


# --------------------------------------------------------------------------------------------------- shared helpers

def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def tool_sha256() -> str:
    """This script's own digest (LF-normalized), carried by every document it writes."""
    return _sha(pathlib.Path(__file__).read_bytes().replace(b"\r\n", b"\n"))


def _git(root, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_NO_REPLACE_OBJECTS="1")
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=check, env=env)


def _git_text(root, *args: str) -> str:
    return _git(root, *args).stdout.decode("utf-8").strip()


def _norm(text: str, *roots) -> str:
    """Strip local paths from a message: each given root becomes a placeholder, the home directory `<home>`."""
    for name, r in roots:
        for form in {str(r), os.path.realpath(r)}:
            text = text.replace(form + os.sep, "").replace(form, f"<{name}>")
    return text.replace(str(pathlib.Path.home()), "<home>")


def guarded_env(scratch: pathlib.Path, base: dict | None = None) -> dict:
    """The mutation-worker env guard (W1-DESIGN.md §2.6 step 2), refused if it cannot be established."""
    env = dict(os.environ if base is None else base)
    keep = [d for d in env.get("PATH", "").split(os.pathsep)
            if d and not (os.path.isfile(os.path.join(d, "opencode")) or os.path.isfile(os.path.join(d, "opencode.exe")))]
    env["PATH"] = os.pathsep.join(keep)
    if shutil.which("opencode", path=env["PATH"]) is not None:
        raise RuntimeError("env guard: an opencode executable is still reachable on PATH")
    for k in [k for k in env if k.startswith("AISEF_") or k in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP")]:
        del env[k]
    for k in ("XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
        d = scratch / "xdg" / k.split("_")[1].lower()
        d.mkdir(parents=True, exist_ok=True)
        env[k] = str(d)
    env["AISEF_SEALING"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _gated_at(tree: pathlib.Path) -> tuple[str, ...] | None:
    p = tree / "tests/v2/sealing_gate.py"
    if not p.is_file():
        return None
    for node in ast.parse(p.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "GATED" for t in node.targets):
            return tuple(ast.literal_eval(node.value))
    return None


def preflight(tree: pathlib.Path, ids, commit: str = V2_2_0) -> tuple[dict, list[str]]:
    facts, problems = {"commit": None, "aisef2_tree": None}, []
    try:
        facts["commit"] = _git_text(tree, "rev-parse", "--verify", "HEAD^{commit}")
        # not stripped: porcelain lines start with a status column that may be a space
        status = _git(tree, "status", "--porcelain=v1", "--untracked-files=all", "--ignored").stdout.decode("utf-8")
    except (subprocess.CalledProcessError, OSError) as e:
        return facts, [f"tree is not a readable git checkout: {type(e).__name__}"]
    k = _git(tree, "rev-parse", "--verify", "HEAD:aisef2", check=False)
    facts["aisef2_tree"] = k.stdout.decode("utf-8").strip() if k.returncode == 0 else None
    if facts["commit"] != commit:
        problems.append(f"tree is at {facts['commit']}, not v2.2.0 {commit}")
    for line in status.splitlines():
        problems.append(f"tree not clean: {line[:2].strip() or '?'} {line[3:]}")
    gated = _gated_at(tree)
    if gated is None:
        problems.append("tree has no readable tests/v2/sealing_gate.py GATED list")
    else:
        problems += [f"{t}: not in the tree's sealing_gate.GATED" for t in ids if t not in gated]
    return facts, problems


def _unittest_name(tid: str) -> str:
    path, qual = tid.split("::")
    return path[:-3].replace("/", ".") + "." + qual


def run_one(tree: pathlib.Path, tid: str, env: dict, work: pathlib.Path, commit: str = V2_2_0, n: int = 0) -> dict:
    """Run one test alone in `tree` under owned_run; return its normalized result (see the module doc)."""
    stem = f"{n:02d}"
    child, owned, log = (work / f"{stem}.{x}" for x in ("child.json", "owned.json", "log"))
    cmd = [sys.executable, "-P", str(tree / "validation/v2/owned_run.py"), "--out", str(owned), "--",
           sys.executable, "-P", str(pathlib.Path(__file__).resolve()), "--child", str(tree), tid, str(child)]
    t0 = time.monotonic()
    try:
        with open(log, "wb") as f:
            rc = subprocess.run(cmd, cwd=tree, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=TIMEOUT_S).returncode
    except subprocess.TimeoutExpired:
        rc = None
    wall = round(time.monotonic() - t0, 3)
    out = {"id": tid, "outcome": ERROR, "exit": rc, "wall_s": wall, "log_sha256": _sha(log.read_bytes()) if log.exists() else None}
    try:
        res = json.loads(child.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        out["detail"] = "no result from the test process" + (" (timeout)" if rc is None else f" (exit {rc})")
        return out
    try:
        m = json.loads(owned.read_text(encoding="utf-8"))
        out["owned_run"] = {"exit": m["exit"], "owned_after": m["owned_after"], "escaped": len(m["escaped"]),
                            "released_empty": m["released_empty"]}
    except (OSError, ValueError, KeyError):
        out["owned_run"] = None
    out.update({k: res[k] for k in ("ran", "failures", "errors", "skipped", "expected_failures", "unexpected_successes",
                                    "duration_s")})
    out["messages"] = [_norm(x, ("tree", tree)) for x in res["messages"]]
    if res["failures"] or res["errors"] or res["unexpected_successes"]:
        out["outcome"] = FAIL
    elif res["skipped"] or res["expected_failures"]:
        out["outcome"] = SKIP
    elif res["ran"] >= 1 and rc == 0:
        out["outcome"] = PASS
    else:
        out["detail"] = f"ran {res['ran']}, owned_run exit {rc}"
    records = []
    for rel in sorted(res["opened"]):
        p = tree / rel
        if not (rel.startswith(RECORDS_DIR) and p.is_file()):
            continue
        blob = _git(tree, "show", f"{commit}:{rel}", check=False)
        now = _sha(p.read_bytes())
        records.append({"path": rel, "sha256": now, "committed": blob.returncode == 0 and _sha(blob.stdout) == now})
    out["records"] = records
    return out


def replay(tree: pathlib.Path, ids=V22_REPLAYED, *, scratch: pathlib.Path, commit: str = V2_2_0) -> dict:
    tree = pathlib.Path(tree).resolve()
    ids = list(ids)
    facts, problems = preflight(tree, ids, commit)
    work = scratch / "runs"
    work.mkdir(parents=True, exist_ok=True)
    env = guarded_env(scratch)
    tests = [run_one(tree, t, env, work, commit, n) for n, t in enumerate(ids)]
    for t in tests:
        if t["outcome"] != PASS:
            problems.append(f"{t['id']}: {t['outcome']}" + (f" — {t['detail']}" if t.get("detail") else "")
                            + "".join(f"\n    {m}" for m in t.get("messages", [])[:3]))
        for r in t.get("records", []):
            if not r["committed"]:
                problems.append(f"{t['id']}: record {r['path']} is not the v2.2.0 committed bytes")
    return {"schema": SCHEMA, "tool": TOOL, "tool_sha256": tool_sha256(), "round": "v2.2", "replayed_at": commit,
            "tree": facts, "selection": "all" if ids == list(V22_REPLAYED) else "subset",
            "env_guard": {"AISEF_SEALING": "1", "opencode_on_path": False, "xdg_in_scratch": True,
                          "pythonpath_removed": True, "bytecode_written": False},
            "host": host(), "tests": tests, "problems": problems,
            "verdict": "PASS" if not problems and ids == list(V22_REPLAYED) else "PARTIAL" if not problems else "FAIL"}


def host() -> dict:
    git = subprocess.run(["git", "--version"], capture_output=True, encoding="utf-8").stdout.strip()
    return {"os": platform.system(), "kernel": platform.release(), "arch": platform.machine(),
            "python": platform.python_version(), "git": git.removeprefix("git version ")}


@contextlib.contextmanager
def v22_clone(scratch: pathlib.Path, commit: str = V2_2_0):
    """A fresh shared clone of this repository detached at `commit` (removed afterwards)."""
    t = pathlib.Path(tempfile.mkdtemp(prefix="v22-replay-", dir=scratch))
    try:
        subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", str(ROOT), str(t / "tree")], check=True)
        _git(t / "tree", "-c", "advice.detachedHead=false", "checkout", "-q", "--detach", commit)
        yield t / "tree"
    finally:
        shutil.rmtree(t, ignore_errors=True)


# --------------------------------------------------------------------------------------------- assertion coverage

def _method(src: str, qual: str) -> ast.FunctionDef | None:
    cls, _, meth = qual.partition(".")
    for n in ast.parse(src).body:
        if isinstance(n, ast.ClassDef) and n.name == cls:
            return next((f for f in n.body if isinstance(f, ast.FunctionDef) and f.name == meth), None)
    return None


def assertions(fn: ast.FunctionDef) -> list[tuple[int, str]]:
    """Every `self.assert*` / `self.fail` call in a test method, in source order, as ast.unparse prints it."""
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"
             and (n.func.attr.startswith("assert") or n.func.attr == "fail")]
    return sorted((n.lineno, ast.unparse(n)) for n in calls)


def coverage(root: pathlib.Path = ROOT, commit: str = V2_2_0) -> dict:
    """The assertion-level map: each assertion of each replayed test (read from `commit`'s blob) -> replayed at
    v2.2.0, and the counterpart assertion that enforces it in round v2.3 (verbatim, or REBOUND). A gap is an
    assertion whose counterpart text is absent from the counterpart method."""
    csrc = (root / COUNTERPARTS_REL).read_text(encoding="utf-8") if (root / COUNTERPARTS_REL).is_file() else ""
    rows, gaps = [], []
    for tid in V22_REPLAYED:
        path, qual = tid.split("::")
        blob = _git(root, "show", f"{commit}:{path}").stdout
        here = (root / path).read_bytes() if (root / path).is_file() else None
        fn = _method(blob.decode("utf-8"), qual)
        node, cqual = COUNTERPART[tid]
        cfn = _method(csrc, cqual) if csrc else None
        have = {a for _, a in assertions(cfn)} if cfn else set()
        entry = {"id": tid, "node": node, "blob_sha256": _sha(blob), "byte_identical_at_head": here == blob,
                 "counterpart": f"{COUNTERPARTS_REL}::{cqual}", "counterpart_found": cfn is not None, "assertions": []}
        for line, a in assertions(fn) if fn else []:
            want = REBOUND.get((tid, a), a)
            ok = want in have
            entry["assertions"].append({"line": line, "v22": a, "replayed_at_v2_2_0": True,
                                        "kind": "rebound" if (tid, a) in REBOUND else "verbatim",
                                        "counterpart": want, "covered": ok})
            if not ok:
                gaps.append(f"{tid}:{line}: {a}")
        if fn is None:
            gaps.append(f"{tid}: method not found at {commit[:12]}")
        rows.append(entry)
    return {"schema": "aisef.v23.round-coverage/1", "tool": TOOL, "tool_sha256": tool_sha256(), "v22_commit": commit,
            "counterparts_sha256": _sha(csrc.encode("utf-8")), "tests": rows,
            "assertions": sum(len(r["assertions"]) for r in rows), "gaps": gaps}


# ------------------------------------------------------------------------------------------------------ the child

def _child(tree: str, tid: str, out: str) -> int:
    """Inside owned_run, in `tree`: record every file the process opens, run the one test, write the result."""
    import unittest
    sys.path.insert(0, tree)
    opened: set[str] = set()

    def hook(event, args):
        if event == "open" and args and isinstance(args[0], (str, bytes)):
            opened.add(os.path.abspath(os.fsdecode(args[0])))

    sys.addaudithook(hook)
    t0 = time.monotonic()
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromName(_unittest_name(tid)))
    dur = round(time.monotonic() - t0, 3)
    pre = os.path.realpath(tree) + os.sep
    rel = sorted({os.path.realpath(p)[len(pre):] for p in opened if os.path.realpath(p).startswith(pre)})
    msgs = [f"{case.id()}: {tb.strip().splitlines()[-1] if tb.strip() else ''}" for case, tb in result.failures + result.errors]
    msgs += [f"skip: {why}" for _, why in result.skipped]
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"ran": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                   "skipped": len(result.skipped), "expected_failures": len(result.expectedFailures),
                   "unexpected_successes": len(result.unexpectedSuccesses), "duration_s": dur,
                   "messages": msgs, "opened": rel}, f)
    return 0 if result.wasSuccessful() and not result.skipped else 1


def _write(path: str, doc: dict) -> None:
    with open(path, "x", encoding="utf-8", newline="\n") as f:   # evidence is written once, never rewritten
        f.write(json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--child"]:
        return _child(*argv[1:4])
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tree", help="an existing checkout to replay in (verified: exactly v2.2.0, clean)")
    ap.add_argument("--only", nargs="+", metavar="ID", help="a subset of V22_REPLAYED (verdict PARTIAL at best)")
    ap.add_argument("--coverage", action="store_true", help="print/write the assertion coverage map instead")
    ap.add_argument("--out", help="write the evidence JSON here (refused if the file exists)")
    ap.add_argument("--scratch", help="keep raw logs here (default: a temporary directory, removed)")
    a = ap.parse_args(argv)
    if a.coverage:
        doc = coverage()
        print(f"{doc['assertions']} assertions over {len(doc['tests'])} tests; gaps: {len(doc['gaps'])}")
        for g in doc["gaps"]:
            print(f"GAP  {g}")
        if a.out:
            _write(a.out, doc)
        return 1 if doc["gaps"] else 0
    ids = a.only or list(V22_REPLAYED)
    unknown = [t for t in ids if t not in V22_REPLAYED]
    if unknown:
        print(f"refused: not a replayed v2.2 test: {unknown}", file=sys.stderr)
        return 2
    with (contextlib.nullcontext(a.scratch) if a.scratch else tempfile.TemporaryDirectory(prefix="aisef-replay-v22-")) as s:
        scratch = pathlib.Path(s).resolve()
        scratch.mkdir(parents=True, exist_ok=True)
        with (contextlib.nullcontext(pathlib.Path(a.tree)) if a.tree else v22_clone(scratch)) as tree:
            doc = replay(tree, ids, scratch=scratch)
            doc["tree_source"] = "given" if a.tree else "fresh-clone"
            doc["date_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for t in doc["tests"]:
        print(f"{t['outcome']:5} {t.get('duration_s', '-'):>9}s  records={len(t.get('records', []))}  {t['id']}")
    for p in doc["problems"]:
        print(f"PROBLEM  {p}")
    print(f"replay v2.2 @ {V2_2_0[:12]}: {doc['verdict']}")
    if a.out:
        _write(a.out, doc)
    return 0 if not doc["problems"] else 1


if __name__ == "__main__":
    sys.exit(main())
