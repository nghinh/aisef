"""C2-ORCHESTRATION-CONFORMANCE-REPAIR — the reproducer and its record (owner ruling 2026-09-30, "ORCHESTRATION
CONFORMANCE REPAIR AUTHORIZED": one ProductProof evaluation per PlanObligation / ProductProofSpec, by the probe identity
each ProductProofSpec carries; a conformance repair to the frozen architecture, not an expansion).

    python -P validation/qualification/c2_orchestration_repair.py --write   # closure-evidence/v2/cycle2/C2-ORCHESTRATION-CONFORMANCE-REPAIR.json
    python -P validation/qualification/c2_orchestration_repair.py --check   # exit 1 unless the record binds this tree

(a) The defect, reproduced. The OLD orchestration — the aisef2 tree of 6311254 (QP-2.6's candidate), materialised
    read-only from git (`git archive`) into a temporary directory and put first on a subprocess's sys.path — and the NEW
    one (this tree) run the same two-kind story (tests/v2/test_c2_orchestration_conformance.reproduce_multi_kind, loaded
    from this tree by path). The kernel reads a few files relative to its own root (the invariant registry: the tier
    packages, validation/v2's static rules, the invariants document), so 6311254's tests/v2, validation/v2 and docs trees
    are materialised beside it; they are the base's own trees (same git tree ids), recorded as such.
(b) Single-probe equivalence. The seven Cycle-1 Q5 corpus items (validation/qualification/q5.py CORPUS, record mode: the
    model stream is the item's own script, no provider) executed under both kernels. q5's normalized journals, outcomes
    and every other observation are compared. q5 derives the RunSpec's kernel capability from the working tree; here
    each process binds the kernel it actually imported, so the raw journals differ in exactly that identity (the
    kernel capability's digest and identity, and the runspec hash over them): every raw difference is listed, and the
    journals are compared again with those three values neutralised.
(c) The multi-probe test matrix: the conformance module's cases (all but the record case) under the owned-process gate.
(d) Every file changed since the base 45136086, with its sha256 before and after (LF-normalised).
(e) Identities unchanged: the 59 contract hashes, spec ids and semantic hashes and the plan hash
    (p5_acceptance.verify(run_guards=False)), the catalog's probe digests, the Cycle-1 frozen probe sources, the probe
    sources of 6311254. The accepted P5-PLAN-V2.2 proposal record also names the kernel tree it was authored on
    (`identities.aisef2_tree`, HEAD:aisef2 then); once the repair is committed the authoring aid re-derives it with the
    new tree, so p10_contracts.check and p5_acceptance.check report that record as not re-derived. The record is measured
    here field by field: that one provenance field must be the only difference (the proposal digest, every hash and the
    plan are the accepted ones); the two C2-P5 checks' outputs are recorded as they are, nothing of C2-P5 is edited.
(f) The C2-ORCH mutation record, summarised, with mutation.py's verdict on it and on P6's superseded entries, and the
    record of the phase that took over story_runner.py's targets since (K-PRESAT-001).

K-PRESAT-001 (owner rulings 2026-10-01, 'BOUNDED CORRECTIVE PATCH' §3 and 'DETERMINISTIC REPAIR COMPLETION' §2): a story
whose every obligation is PRE_SATISFIED makes no developer call and no longer runs the engineering-adequacy stage. One of
the seven Cycle-1 items (`pre-satisfied`) is such a story, so under this kernel its journal is the old kernel's WITHOUT
that stage — the three `tests …` process ranges, `tests/adequacy` and the `<story>:quality` gate check — and nothing else
differs. (b) measures exactly that (`without_adequacy_stage`): the other six items are identical as before, and this one
must differ by that stage and by nothing else, or the record states a problem.
(g) The guards, each run once.

`--check` re-derives (d), (e) and (f) and compares them with the record, and requires the verdict the record states;
(a), (b), (c) and (g) are executions — `--write` runs them and `--check` reads what they recorded.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_REL = "closure-evidence/v2/cycle2/C2-ORCHESTRATION-CONFORMANCE-REPAIR.json"
#: The lane's last commit. After integration (C2-INTEGRATION-R2.json) the record accounts for the repair's own changes
#: up to it; a later change to a recorded file, or any later change under the orchestration or the probes, still fails.
LANE_HEAD = "cacaa6bd65a0c627bdb18e1a9fc8c29b98695676"
#: The identities that must still hold on any later tree; the record's C2-P5 check observations are as written.
SEMANTIC_IDENTITIES = ("contracts", "all_equal_to_accepted", "contract_spec_semantic_digest", "semantic_change", "plan_hash",
                       "plan_ok", "catalog", "catalog_matches_the_brief", "cycle1_drift_ok", "cycle1_frozen_probe_sources",
                       "cycle1_frozen_probe_sources_identical", "probe_sources_vs_6311254", "probe_sources_identical_to_6311254")
MUTATION_REL = "closure-evidence/v2/cycle2/C2-ORCH-MUTATION.json"
P6_MUTATION_REL = "closure-evidence/v2/P6-MUTATION.json"
AUTHORITY = "owner ruling 2026-09-30, 'ORCHESTRATION CONFORMANCE REPAIR AUTHORIZED' (C2-ORCHESTRATION-CONFORMANCE-REPAIR)"
#: the Cycle-1 corpus items whose story is fully PRE_SATISFIED: under K-PRESAT-001 they run no engineering-adequacy stage
K_PRESAT_ITEMS = ("pre-satisfied",)
K_PRESAT_AUTHORITY = ("owner rulings 2026-10-01, 'AISEF V2 — BOUNDED CORRECTIVE PATCH' §3 (K-PRESAT-001) and 'AISEF V2 — "
                      "DETERMINISTIC REPAIR COMPLETION' §2 (K-PRESAT-001 CONFIRMED)")
K_PRESAT_MUTATION_REL = "closure-evidence/v2/cycle2/K-PRESAT-001-MUTATION.json"
BASE = "45136086c3e4a98534f975e6db979f94165af5f3"
OLD = "63112544f1146097b69c538d98e09e5a52c547c1"
OLD_AISEF2_TREE = "f4bfc7f1291cc72fa8ade79e798f5222f3429759"
PLAN_HASH = "27b679d9513f3dc2f9b5da68a694a3ef1baff50f87eae9903721415a4670a669"
#: the catalog's probe digests as the owner's brief names them (the inactive Cycle-1 probe first)
BRIEFED_DIGEST_PREFIXES = ("1961e84d", "b71adecf", "31465b73", "5ec17bea", "dbbe4cd5")
CYCLE1_PARENT = "7114177834da5a7e4a0fc2c7f8fa9d067e0abaa2"   # cycle2_baseline.PARENT_COMMIT
CYCLE1_PROBE_SOURCES = ("aisef2/probe/protocol.py", "aisef2/probe/python_callable.py")
REFUSAL = "InvariantError: cycle 1 proves a story with exactly one probe factory"
TEST_MODULE = "tests.v2.test_c2_orchestration_conformance"
MATRIX_CLASSES = ("OneProofPerObligation", "MixedStory", "ReproofOfAnotherKind", "Parties", "LedgerLockStories")
MARK = "C2-ORCH-JOB "
KERNEL_FIELDS = ("capability/resolved kernel: binding.digest", "capability/resolved kernel: identity",
                 "run/spec-resolved: runspec_hash")
GUARDS = {
    "cycle2_baseline": [sys.executable, "-P", "validation/v2/cycle2_baseline.py", "--check"],
    "checker_calibration": [sys.executable, "-P", "validation/v2/checker_calibration.py", "--check"],
    "freeze_conformance": [sys.executable, "-P", "validation/v2/freeze_conformance.py", "--check"],
    "v1_evidence_guard": [sys.executable, "-P", "validation/v2/v1_evidence_guard.py", "--check"],
    "old_path_audit": [sys.executable, "-P", "validation/v2/old_path_audit.py", "--check"],
    "p6_evidence": [sys.executable, "-P", "validation/v2/p6_evidence.py", "--check"],
    "destructive_authority": [sys.executable, "-P", "validation/v2/destructive_authority.py", "--check"],
    "kernel_static_checks": [sys.executable, "-P", "validation/v2/kernel_static_checks.py", "--check"],
    "except_boundaries": [sys.executable, "-P", "validation/v2/except_boundaries.py", "--check"],
    "mutation": [sys.executable, "-P", "validation/v2/mutation.py", "--check"],
    "ruff": ["ruff", "check", "."],
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _lf(data: bytes) -> str:
    return _sha(data.replace(b"\r\n", b"\n"))


def _git(*args: str, binary: bool = False):
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True)
    return r.stdout if binary else r.stdout.decode("utf-8").strip()


def _is_ancestor(a: str, b: str) -> bool:
    return subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", a, b], capture_output=True).returncode == 0


def _at(rev: str, rel: str) -> str | None:
    """The LF sha256 of `rel` at `rev`, None when the revision has no such file."""
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{rel}"], capture_output=True)
    return _lf(r.stdout) if r.returncode == 0 else None


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def kernel_digest(kernel: pathlib.Path) -> str:
    """q4's kernel digest (`_over(_file_digests(("aisef2",)))`) over the kernel at `kernel` — the directory `aisef2`."""
    files = {f"aisef2/{p.relative_to(kernel).as_posix()}": _lf(p.read_bytes())
             for p in sorted(kernel.rglob("*.py")) if "__pycache__" not in p.parts}
    return _sha("\n".join(f"{k} {v}" for k, v in sorted(files.items())).encode())


# --------------------------------------------------------------------------------------- the two kernels

#: what a kernel reads relative to its root (the invariant registry), materialised beside it
SUPPORT = ("tests/__init__.py", "tests/v2", "validation/v2", "docs/architecture", "docs/implementation/v2")


def materialise(commit: str, into: pathlib.Path) -> dict:
    """The aisef2 tree of `commit` and the files the kernel reads relative to its root, read from git's object store
    (the working tree and the index are never touched) into `into`, every file made read-only."""
    data = _git("archive", "--format=tar", commit, "aisef2", *SUPPORT, binary=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        t.extractall(into, filter="data")
    for p in into.rglob("*"):
        if p.is_file():
            os.chmod(p, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    kernel = into / "aisef2"
    return {"commit": commit, "aisef2_tree": _git("rev-parse", f"{commit}:aisef2"),
            "files": sum(1 for p in kernel.rglob("*.py")), "kernel_digest": kernel_digest(kernel),
            "support": {rel: {"commit": _git("rev-parse", f"{commit}:{rel}"), "base": _git("rev-parse", f"{BASE}:{rel}")}
                        for rel in SUPPORT}}


CHILD = """
import json, sys
kernel, root, job = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path[:0] = [p for p in (kernel, root) if p]
import aisef2
from validation.qualification import c2_orchestration_repair as rp
print(rp.MARK + json.dumps({"kernel_file": aisef2.__file__, "result": rp.JOBS[job]()}, default=str), flush=True)
"""


def in_kernel(kernel_root: pathlib.Path | None, job: str) -> dict:
    """`job` in a fresh interpreter whose aisef2 is the one under `kernel_root` (None: this tree's). -B: no bytecode is
    written into either tree."""
    r = subprocess.run([sys.executable, "-P", "-B", "-c", CHILD, str(kernel_root or ""), str(ROOT), job], cwd=ROOT,
                       capture_output=True, encoding="utf-8", errors="replace")
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith(MARK)), None)
    if line is None:
        raise SystemExit(f"job {job} under {kernel_root or 'this tree'} exited {r.returncode}:\n{(r.stdout + r.stderr)[-4000:]}")
    out = json.loads(line[len(MARK):])
    want = (kernel_root or ROOT) / "aisef2"
    if pathlib.Path(out["kernel_file"]).resolve().parent != want.resolve():
        raise SystemExit(f"job {job}: imported {out['kernel_file']}, not the kernel under {want}")
    return out["result"]


def _job_multi_kind() -> dict:
    m = _load("c2_orchestration_conformance", "tests/v2/test_c2_orchestration_conformance.py")   # this tree's
    with tempfile.TemporaryDirectory(prefix="aisef2-c2-orch-repro-") as t:
        return m.reproduce_multi_kind(pathlib.Path(t) / "w")


#: (b) is the seven Cycle-1 corpus items by name: q5.CORPUS also carries the Cycle-2 items (QP-2.8) since the lane closed
CYCLE1_ITEMS = ("normal-completion", "retry-then-commit", "review-finding-rollback", "pre-satisfied", "security-finding-rollback",
                "developer-outage-rollback", "post-merge-regression")


def _job_q5() -> dict:
    import aisef2
    from validation.qualification import q5
    kernel = pathlib.Path(aisef2.__file__).resolve().parent
    q5.kernel_digest = lambda: kernel_digest(kernel)   # the kernel this process imported, not the working tree's
    out = {}
    for item in (i for i in q5.CORPUS if i.id in CYCLE1_ITEMS):
        o = q5.execute(item, "record")
        out[item.id] = {k: o.get(k) for k in ("outcomes", "errors", "notes", "journal", "model_requests", "consumption",
                                              "tool_ledger", "subprocesses", "initial_workspace", "final_workspace")}
    return out


JOBS = {"multi_kind": _job_multi_kind, "q5": _job_q5}


# --------------------------------------------------------------------------------------- (b) comparison

def _paths(a, b, at: str = "") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        return [p for k in sorted(set(a) | set(b)) for p in _paths(a.get(k), b.get(k), f"{at}.{k}" if at else k)]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [p for i, (x, y) in enumerate(zip(a, b, strict=True)) for p in _paths(x, y, f"{at}[{i}]")]
    return [] if a == b else [at or "<value>"]


def _neutral(journal: list[dict]) -> list[dict]:
    """The journal with the kernel's own identity replaced by a token: the kernel capability's digest and identity,
    and the runspec hash derived from them. Nothing else is touched."""
    out = json.loads(json.dumps(journal))
    for e in out:
        if e["type"] == "capability/resolved" and e["data"].get("name") == "kernel":
            e["data"]["binding"]["digest"] = e["data"]["identity"] = "<KERNEL>"
        elif e["type"] == "run/spec-resolved":
            e["data"]["runspec_hash"] = "<RUNSPEC>"
    return out


def _adequacy_stage(e: dict) -> bool:
    """An event of the engineering-adequacy stage: its `tests …` process ranges, `tests/adequacy`, the quality check."""
    d = e["data"]
    return e["type"] == "tests/adequacy" or (e["type"] == "gate/check" and str(d.get("check", "")).endswith(":quality")) or (
        e["type"] in ("story/resource-acquired", "story/resource-released") and d.get("kind") == "PROCESS_RANGE"
        and str(d.get("resource", "")).startswith("tests "))


def without_adequacy_stage(journal: list[dict]) -> tuple[list[dict], dict]:
    """`journal` as it would read had the engineering-adequacy stage not run: its events removed, every later sequence
    number and every citation renumbered, a citation of a removed event dropped. With the removed events by type."""
    gone = [e for e in journal if _adequacy_stage(e)]
    kept = [e for e in journal if not _adequacy_stage(e)]
    seq = {e["seq"]: i for i, e in enumerate(kept)}
    out = [{**json.loads(json.dumps(e)), "seq": seq[e["seq"]], "source_seqs": [seq[x] for x in e.get("source_seqs", []) if x in seq]}
           for e in kept]
    removed: dict[str, int] = {}
    for e in gone:
        removed[e["type"]] = removed.get(e["type"], 0) + 1
    return out, removed


def compare_item(old: dict, new: dict, k_presat: bool = False) -> dict:
    raw = []
    for i in range(max(len(old["journal"]), len(new["journal"]))):
        a = old["journal"][i] if i < len(old["journal"]) else None
        b = new["journal"][i] if i < len(new["journal"]) else None
        if a != b:
            label = (a or b)["type"] + (f" {(a or b)['data'].get('name')}" if (a or b)["type"] == "capability/resolved" else "")
            raw.append({"index": i, "event": label, "fields": _paths(a, b)})
    only_kernel = all((d["event"], f) in {("capability/resolved kernel", "data.binding.digest"),
                                          ("capability/resolved kernel", "data.identity"),
                                          ("run/spec-resolved", "data.runspec_hash")} for d in raw for f in d["fields"])
    others = {k: old[k] == new[k] for k in ("outcomes", "errors", "notes", "model_requests", "consumption", "tool_ledger",
                                           "subprocesses", "initial_workspace", "final_workspace")}
    out = {"outcomes": new["outcomes"], "outcomes_identical": old["outcomes"] == new["outcomes"],
           "events": [len(old["journal"]), len(new["journal"])], "errors": new["errors"],
           "journal_raw_differences": raw, "journal_identical_but_kernel_identity":
               only_kernel and _neutral(old["journal"]) == _neutral(new["journal"]),
           "other_observations_identical": others}
    if k_presat:
        # K-PRESAT-001: the old journal without its adequacy stage must be the new journal, and the new one has none
        stripped, removed = without_adequacy_stage(old["journal"])
        _, in_new = without_adequacy_stage(new["journal"])
        tests = (old["subprocesses"] or {}).get("tests") if isinstance(old["subprocesses"], dict) else None
        out["k_presat_001"] = {
            "removed_from_the_old_journal": removed, "adequacy_stage_events_in_the_new_journal": in_new,
            "journal_identical_but_kernel_identity_and_the_adequacy_stage": _neutral(stripped) == _neutral(new["journal"]),
            "subprocesses": {"old": old["subprocesses"], "new": new["subprocesses"]},
            "subprocesses_identical_but_the_tests_of_the_stage": bool(tests) and {**old["subprocesses"], "tests": 0} == new["subprocesses"],
            "other_observations_identical_but_subprocesses": all(v for k, v in others.items() if k != "subprocesses")}
    return out


def by_k_presat(v: dict) -> bool:
    """The item differs from the old kernel by the engineering-adequacy stage of a fully PRE_SATISFIED story and by
    nothing else: same outcomes, the stage present in the old journal and absent from the new, the rest identical."""
    k = v.get("k_presat_001") or {}
    return bool(v["outcomes_identical"] and not v["journal_identical_but_kernel_identity"]
                and k.get("removed_from_the_old_journal", {}).get("tests/adequacy") and not k.get("adequacy_stage_events_in_the_new_journal")
                and k.get("journal_identical_but_kernel_identity_and_the_adequacy_stage")
                and k.get("subprocesses_identical_but_the_tests_of_the_stage") and k.get("other_observations_identical_but_subprocesses"))


def single_probe_equivalence(old_root: pathlib.Path) -> dict:
    old, new = in_kernel(old_root, "q5"), in_kernel(None, "q5")
    by_item = {i: compare_item(old[i], new[i], i in K_PRESAT_ITEMS) for i in new}
    same = [i for i, v in by_item.items() if v["outcomes_identical"] and v["journal_identical_but_kernel_identity"]
            and all(v["other_observations_identical"].values())]
    return {"corpus": "validation/qualification/q5.py CORPUS", "mode": "record (the item's scripted model stream; no provider)",
            "items": len(by_item), "identical": len(same), "by_item": by_item,
            "identical_but_the_adequacy_stage_of_a_fully_pre_satisfied_story": sorted(i for i, v in by_item.items() if by_k_presat(v)),
            "k_presat_001": {"authority": K_PRESAT_AUTHORITY, "items": list(K_PRESAT_ITEMS),
                             "rule": "a story whose every obligation is PRE_SATISFIED makes no developer call and runs no "
                                     "engineering-adequacy stage; such an item's journal is the old kernel's without that "
                                     "stage (its `tests …` process ranges, tests/adequacy, the quality gate check), renumbered, "
                                     "and nothing else differs"},
            "difference_rule": "the raw normalized journals differ only in " + ", ".join(KERNEL_FIELDS)
                               + " (each process binds the kernel it imported); neutralised, they are identical"}


# --------------------------------------------------------------------------------------- (c) the test matrix

MATRIX_CHILD = """
import io, json, sys, unittest
sys.path.insert(0, sys.argv[1])
names = sys.argv[2:]
suite = unittest.defaultTestLoader.loadTestsFromNames(names)
out = {}
def walk(s):
    for t in s:
        walk(t) if isinstance(t, unittest.TestSuite) else out.__setitem__(t.id(), "PASS")
walk(suite)
result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
for kind, rows in (("FAIL", result.failures), ("ERROR", result.errors)):
    for t, _ in rows:
        out[t.id()] = kind
for t, reason in result.skipped:
    out[t.id()] = "SKIP: " + reason
print("MATRIX " + json.dumps({"ran": result.testsRun, "outcomes": out}), flush=True)
"""


def matrix() -> dict:
    with tempfile.TemporaryDirectory(prefix="aisef2-c2-orch-matrix-") as t:
        owned = pathlib.Path(t) / "owned.json"
        cmd = [sys.executable, "-P", "validation/v2/owned_run.py", "--out", str(owned), "--", sys.executable, "-P",
               "-W", "ignore::ResourceWarning", "-c", MATRIX_CHILD, str(ROOT), *(f"{TEST_MODULE}.{c}" for c in MATRIX_CLASSES)]
        started = time.monotonic()
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
        # owned_run's range hands the command's stdout to its own stderr: the line is looked for in both
        line = next((ln for ln in (r.stdout + r.stderr).splitlines() if ln.startswith("MATRIX ")), None)
        m = json.loads(owned.read_text(encoding="utf-8")) if owned.exists() else {}
    got = json.loads(line[len("MATRIX "):]) if line else {"ran": None, "outcomes": {}}
    outcomes = {k.removeprefix(TEST_MODULE + "."): v for k, v in got["outcomes"].items()}
    return {"module": TEST_MODULE, "classes": list(MATRIX_CLASSES), "exit": r.returncode, "ran": got["ran"],
            "passed": sum(1 for v in outcomes.values() if v == "PASS"), "outcomes": dict(sorted(outcomes.items())),
            "owned_processes": {k: m.get(k) for k in ("owned_before", "owned_at_exit", "owned_after", "released_empty")}
            | {"escaped": len(m.get("escaped") or [])}, "seconds": round(time.monotonic() - started, 1)}


# --------------------------------------------------------------------------------------- (d) (e) (f) (g)

def repair_paths() -> set[str]:
    """The repair's files: every file that differs from the base — committed since, modified or new. On an integrated
    tree (LANE_HEAD an ancestor of HEAD) the lane's own changes up to LANE_HEAD, and any later change under the
    orchestration or the probes (another lane's files are the integration record's, not this one's)."""
    head = _git("rev-parse", "HEAD")
    if head != LANE_HEAD and _is_ancestor(LANE_HEAD, head):
        later = set(_git("diff", "--name-only", LANE_HEAD).splitlines()) | set(_git("ls-files", "--others", "--exclude-standard").splitlines())
        return set(_git("diff", "--name-only", BASE, LANE_HEAD).splitlines()) | {
            x for x in later if x.startswith(("aisef2/orchestrate/", "aisef2/probe/"))}
    return set(_git("diff", "--name-only", BASE).splitlines()) | set(_git("ls-files", "--others", "--exclude-standard").splitlines())


def changed_files() -> dict:
    """Every file of the repair (`repair_paths`) except this record, before and after."""
    paths = repair_paths()
    rows = {}
    for rel in sorted(p for p in paths if p and p != OUT_REL):
        f = ROOT / rel
        rows[rel] = {"before": _at(BASE, rel), "after": _lf(f.read_bytes()) if f.exists() else None}
    return rows


PROPOSAL_REL = "closure-evidence/v2/cycle2/P5-PLAN-V2.2-PROPOSAL.json"
PROPOSAL_NOT_REDERIVED = f"{PROPOSAL_REL} is not what the authoring aid derives from this tree"


def proposal_provenance() -> dict:
    """Every path at which the accepted proposal record differs from what the authoring aid derives on this tree."""
    from validation.qualification import p10_contracts as aid
    committed = json.loads((ROOT / PROPOSAL_REL).read_text(encoding="utf-8"))
    derived = aid.record()
    paths = _paths(committed, derived)
    return {"differing_paths": paths, "committed": {p: _at_path(committed, p) for p in paths},
            "derived": {p: _at_path(derived, p) for p in paths},
            "provenance_only": paths in ([], ["identities.aisef2_tree"]),
            "proposal_digest_unchanged": derived["proposal_digest"] == committed["proposal_digest"]}


def _at_path(doc, path: str):
    for part in path.split("."):
        doc = doc.get(part) if isinstance(doc, dict) else None
    return doc


def identities() -> dict:
    from aisef2.probe import catalog
    from validation.qualification import p5_acceptance as pa
    from validation.qualification import p10_contracts as aid
    v = pa.verify(run_guards=False)
    provenance = proposal_provenance()
    acceptance = json.loads((ROOT / pa.OUT_REL).read_text(encoding="utf-8"))
    specs = v["identities"]["specs"]
    rows = [[r["spec_id"], r["contract_id"], r["contract_hash"], r["spec_hash_id"], r["semantic_hash"], r["probe_id"],
             r["probe_digest"]] for r in specs]
    probe_files = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "aisef2/probe").glob("*.py"))
    frozen = {rel: {"cycle1_parent": _at(CYCLE1_PARENT, rel), "now": _lf((ROOT / rel).read_bytes())} for rel in CYCLE1_PROBE_SOURCES}
    old = {rel: {"6311254": _at(OLD, rel), "now": _lf((ROOT / rel).read_bytes())} for rel in probe_files}
    digests = {e.probe_id: e.probe_digest for e in catalog.CATALOG}
    return {
        "contracts": len(specs), "all_equal_to_accepted": all(r["equal_to_accepted"] for r in specs),
        "contract_spec_semantic_digest": _sha(json.dumps(rows, sort_keys=True).encode()),
        "contract_spec_semantic_rule": "sha256 of the JSON list of [spec, contract id, contract hash, spec id, semantic hash, "
                                       "probe id, probe digest] rows of p5_acceptance.verify, in proposal order",
        "semantic_change": v["semantic_change"], "verify_problems": v["problems"],
        "verify_problems_are_provenance_only": all(x == PROPOSAL_NOT_REDERIVED for x in v["problems"])
            and provenance["provenance_only"] and provenance["proposal_digest_unchanged"]
            and _paths(acceptance["verification"]["identities"], json.loads(json.dumps(v["identities"])))
            in ([], ["proposal_record_current"]),
        "c2_p5_proposal_provenance": provenance,
        "c2_p5_checks_as_observed": {"p10_contracts.check": aid.check(), "p5_acceptance.check": pa.check()},
        "c2_p5_acceptance_verification_differences": {
            k: _paths(acceptance["verification"][k], json.loads(json.dumps(v[k])))
            for k in ("identities", "semantic_change", "rulings", "admission", "cycle1_drift")},
        "plan_hash": v["identities"]["plan_hash"], "plan_ok": v["identities"]["plan_ok"] and v["identities"]["plan_hash"] == PLAN_HASH,
        "catalog": digests, "catalog_matches_the_brief": sorted(d[:8] for d in digests.values()) == sorted(BRIEFED_DIGEST_PREFIXES),
        "cycle1_drift_ok": v["cycle1_drift"]["ok"],
        "cycle1_frozen_probe_sources": frozen,
        "cycle1_frozen_probe_sources_identical": all(x["cycle1_parent"] == x["now"] for x in frozen.values()),
        "probe_sources_vs_6311254": old,
        "probe_sources_identical_to_6311254": all(x["6311254"] == x["now"] for x in old.values()),
    }


def mutation() -> dict:
    mu = _load("aisef_v2_mutation", "validation/v2/mutation.py")
    rec = json.loads((ROOT / MUTATION_REL).read_text(encoding="utf-8"))
    p6 = json.loads((ROOT / P6_MUTATION_REL).read_text(encoding="utf-8"))
    rows = {t["target"]: {k: t.get(k) for k in ("mutants", "killed", "survivors", "killed_by_timeout", "strays_reaped",
                                                 "kill_tests", "source_sha256", "error")} for t in rec["targets"]}
    later = ROOT / K_PRESAT_MUTATION_REL
    krec = json.loads(later.read_text(encoding="utf-8")) if later.exists() else {"targets": []}
    krows = {t["target"]: {k: t.get(k) for k in ("mutants", "killed", "survivors", "killed_by_timeout", "strays_reaped",
                                                  "kill_tests", "source_sha256", "error")} for t in krec["targets"]}
    return {"record": {"path": MUTATION_REL, "sha256": _lf((ROOT / MUTATION_REL).read_bytes())}, "targets": rows,
            "totals": {"targets": len(rows), "mutants": sum(r["mutants"] or 0 for r in rows.values()),
                       "killed": sum(r["killed"] or 0 for r in rows.values()),
                       "survivors": sum(len(r["survivors"] or []) for r in rows.values()),
                       "killed_by_timeout": sum(r["killed_by_timeout"] or 0 for r in rows.values())},
            "owned_targets": sorted(mu.C2_ORCH_TARGETS), "problems": mu.problems_of(rec, ROOT, "C2-ORCH"),
            "superseded_entries": mu.superseded(rec, "C2-ORCH"),
            "p6_superseded_entries": mu.superseded(p6, "P6"), "p6_problems": mu.problems_of(p6, ROOT, "P6"),
            "k_presat_001": {"record": {"path": K_PRESAT_MUTATION_REL, "sha256": _lf(later.read_bytes()) if later.exists() else None},
                             "authority": K_PRESAT_AUTHORITY, "targets": krows, "owned_targets": sorted(mu.K_PRESAT_TARGETS),
                             "totals": {"targets": len(krows), "mutants": sum(r["mutants"] or 0 for r in krows.values()),
                                        "killed": sum(r["killed"] or 0 for r in krows.values()),
                                        "survivors": sum(len(r["survivors"] or []) for r in krows.values()),
                                        "audited_survivors": sum(1 for t, r in krows.items() for m in r["survivors"] or [] if (t, m) in mu.AUDITED),
                                        "killed_by_timeout": sum(r["killed_by_timeout"] or 0 for r in krows.values())},
                             "problems": mu.problems_of(krec, ROOT, "K-PRESAT-001") if later.exists() else [f"{K_PRESAT_MUTATION_REL} is missing"]},
            "every_record": mu.check(ROOT)}


def guards() -> dict:
    out = {}
    for name, cmd in GUARDS.items():
        t = time.monotonic()
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
        out[name] = {"command": " ".join(["python -P", *cmd[2:]] if cmd[0] == sys.executable else cmd), "exit": r.returncode,
                     "tail": (r.stdout + r.stderr).strip().splitlines()[-2:], "seconds": round(time.monotonic() - t, 1)}
    return out


# --------------------------------------------------------------------------------------- the record

def verdict_problems(rec: dict) -> list[str]:
    out = []
    a = rec["defect_reproducer"]
    if a["old"]["raised"] != REFUSAL:
        out.append(f"(a) the old kernel did not refuse with {REFUSAL!r}: {a['old']['raised']!r}")
    if a["new"]["raised"] is not None or a["new"]["attempts"] != ["COMMIT"]:
        out.append(f"(a) the new kernel did not commit the two-kind story: {a['new']['raised']!r} {a['new']['attempts']}")
    b = rec["single_probe_equivalence"]
    staged = b.get("identical_but_the_adequacy_stage_of_a_fully_pre_satisfied_story")
    if (b["items"], b["identical"], staged) != (7, 7 - len(K_PRESAT_ITEMS), sorted(K_PRESAT_ITEMS)):
        out.append(f"(b) {b['identical']} of {b['items']} single-probe items identical under both kernels and {staged} identical "
                   f"but the adequacy stage of a fully PRE_SATISFIED story (K-PRESAT-001): expected {7 - len(K_PRESAT_ITEMS)} and "
                   f"{sorted(K_PRESAT_ITEMS)}")
    c = rec["test_matrix"]
    bad = {k: v for k, v in c["outcomes"].items() if v != "PASS"}
    if bad or c["exit"] != 0 or not c["ran"] or c["owned_processes"]["owned_after"] != 0 or c["owned_processes"]["escaped"]:
        out.append(f"(c) the test matrix: exit {c['exit']}, not passed {bad}, owned {c['owned_processes']}")
    e = rec["identities"]
    for k in ("all_equal_to_accepted", "plan_ok", "catalog_matches_the_brief", "cycle1_drift_ok",
              "cycle1_frozen_probe_sources_identical", "probe_sources_identical_to_6311254"):
        if e[k] is not True:
            out.append(f"(e) {k} is not true")
    if e["contracts"] != 59 or e["semantic_change"] != "NONE" or not e["verify_problems_are_provenance_only"]:
        out.append(f"(e) {e['contracts']} contracts, semantic change {e['semantic_change']}, {e['verify_problems']}")
    f = rec["mutation"]
    k = f.get("k_presat_001") or {"problems": ["no K-PRESAT-001 mutation summary"], "totals": {}}
    if f["problems"] or f["p6_problems"] or f["every_record"] or f["totals"]["survivors"] or k["problems"]:
        out.append(f"(f) mutation: {f['problems'] + f['p6_problems'] + f['every_record'] + k['problems']} survivors {f['totals']['survivors']}")
    out += [f"(g) guard {k}: exit {v['exit']}" for k, v in rec["guards"].items() if v["exit"] != 0]
    return out


def write() -> dict:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="aisef2-kernel-6311254-") as t:
        old_root = pathlib.Path(t)
        old = materialise(OLD, old_root)
        if old["aisef2_tree"] != OLD_AISEF2_TREE:
            raise SystemExit(f"6311254:aisef2 is {old['aisef2_tree']}, not {OLD_AISEF2_TREE}")
        reproducer = {"story": f"{TEST_MODULE}.reproduce_multi_kind: C-F (file_artifact) and C-P (python_callable_v2), "
                               "both INTRODUCE and READY at the parent; the harness wires exactly the story's two probes",
                      "old": in_kernel(old_root, "multi_kind"), "new": in_kernel(None, "multi_kind")}
        equivalence = single_probe_equivalence(old_root)
    rec = {
        "record": "AISEF V2 — C2-ORCHESTRATION-CONFORMANCE-REPAIR: one ProductProof evaluation per PlanObligation, by the "
                  "probe identity its ProductProofSpec carries",
        "authority": AUTHORITY,
        "classification": "CONFORMANCE REPAIR to the frozen architecture (not an architecture expansion, not a new probe feature)",
        "subject": {"base": BASE, "head_when_written": _git("rev-parse", "HEAD"),
                    "note": "written on head_when_written, the commit that carries the repair, and committed in the commit "
                            "after it (a record cannot name the commit that contains it; the C2-P5 proposal's derived "
                            "provenance in (e) reads HEAD's kernel tree); (d) binds every changed file by content",
                    "old_kernel": old,
                    "new_kernel": {"kernel_digest": kernel_digest(ROOT / "aisef2"),
                                   "rule": "q4's kernel digest over this working tree's aisef2 (its git tree exists once the "
                                           "repair is committed; (d) binds the two changed modules by content)"}},
        "repair": {
            "story_runner._probe": "resolves the factory of the spec's own probe identity (inputs.probes.get(spec.probe_id)); "
                                   "None when the harness wires none; without a spec only a single factory is unambiguous (as before)",
            "proof.Party": "keyword-only by_spec: the maker is given the spec it is asked to prove; a maker without the spec's "
                           "probe makes the party run nothing and return no record (a party never manufactures one: invariant "
                           "III, INV-III-1 pins the record producers to protocol.py and story_admission.py); one-argument "
                           "makers unchanged",
            "proof.prove": "a party with no probe for the spec's identity is PROBE_INVALID_SPEC, the code an INVALID_SPEC result "
                           "routes to at every point (§10) — never a crash, never another probe's run; the journal order of "
                           "a proof is unchanged (implementer record, verifier record, proof)",
            "StoryInputs.probes": "several factories keyed by probe id (a harness wires every probe the plan's specs name)",
            "unchanged": "StoryAdmission, ContractSatisfaction, routing, budgets, journal events and payloads, the RunSpec, "
                         "F1-F11, every contract, spec, plan and probe identity"},
        "k_presat_001": {
            "authority": K_PRESAT_AUTHORITY,
            "story_runner._attempt": "the engineering-adequacy stage runs only when the story has developer work "
                                     "(`not continuation.already_satisfied`): a story whose every obligation is PRE_SATISFIED "
                                     "made no developer call, so the stage is not run and can neither fail nor charge it (RFC §14)",
            "unchanged": "the developer call was already skipped for such a story; its independent verification at the candidate, "
                         "plan-drift, review, security, merge and post-merge re-proof are as before",
            "effect_on_this_record": "(b): the one Cycle-1 item that is a fully PRE_SATISFIED story differs from the old kernel "
                                     "by exactly that stage; (d): story_runner.py; (f): its mutation targets are re-measured in "
                                     f"{K_PRESAT_MUTATION_REL}, the C2-ORCH entries for them kept as historical"},
        "defect_reproducer": reproducer,
        "single_probe_equivalence": equivalence,
        "test_matrix": matrix(),
        "files_changed": changed_files(),
        "identities": identities(),
        "mutation": mutation(),
        "guards": guards(),
        "platform": {"python": sys.version.split()[0], "platform": sys.platform},
    }
    rec["problems"] = verdict_problems(rec)
    rec["verdict"] = "COMPLETE" if not rec["problems"] else "PROBLEMS"
    rec["seconds"] = round(time.monotonic() - started, 1)
    (ROOT / OUT_REL).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return rec


def check() -> list[str]:
    p = ROOT / OUT_REL
    if not p.exists():
        return [f"{OUT_REL} is missing"]
    rec = json.loads(p.read_text(encoding="utf-8"))
    out = [] if rec.get("verdict") == "COMPLETE" and not rec.get("problems") else [f"the record's verdict is {rec.get('verdict')}"]
    out += verdict_problems(rec)
    for rel, row in rec["files_changed"].items():
        f = ROOT / rel
        now = _lf(f.read_bytes()) if f.exists() else None
        if now != row["after"]:
            out.append(f"(d) {rel} changed since the record")
    committed = {x for x in repair_paths() if x and x != OUT_REL}
    out += [f"(d) {x} changed since the base and is not in the record" for x in sorted(committed - set(rec["files_changed"]))]
    now = identities()
    if {k: now.get(k) for k in SEMANTIC_IDENTITIES} != {k: rec["identities"].get(k) for k in SEMANTIC_IDENTITIES}:
        out.append("(e) the identities differ from the record")
    if mutation() != rec["mutation"]:
        out.append("(f) the mutation summary differs from the record")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.write:
        rec = write()
        print(f"{OUT_REL}: {rec['verdict']} ({rec['seconds']} s)")
        for x in rec["problems"]:
            print(f"FAIL  {x}")
        return 0 if rec["verdict"] == "COMPLETE" else 1
    problems = check()
    for x in problems:
        print(f"FAIL  {x}")
    print("c2 orchestration repair: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
