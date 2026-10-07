"""V2.1 requalification round (owner B-01/B-03, 2026-10-06): the scope manifest — what is re-measured, by what, on which
commit, in which environment — written once, before the mutation campaign starts.

    python -P validation/qualification/v21_requalification.py --write --base SHA --campaign NOTE   # -> v2.1/REQUALIFICATION-MANIFEST.json
    python -P validation/qualification/v21_requalification.py --write --revision N --supersedes-reason TEXT \
        --campaign NOTE [--execution-order REL] [--t0 REL] [--preflight REL]                        # -> ...-MANIFEST-N.json
    python -P validation/qualification/v21_requalification.py --check   # the newest revision's scope is still this tree's

The manifest names: the owner's decisions (RELEASE-DECISIONS seq 4 and 5), the base commit and the snapshot (HEAD at
writing), every V2.1 mutation target with its kill set and mutant count (and how the reported 320 were checked against
the tree), what is deliberately not a target and why, every Q0 checker, the 2.1 Q5 corpus, the v2.1 records to be
produced (in order, with their tools), and the campaign's environment. --check reports where the tree no longer
matches it (a target or kill set changed, a checker added or removed, the corpus changed): the manifest is a scope
statement, so a later change of scope must be visible, not silently absorbed.

A campaign that is stopped and restarted on another commit gets a REVISION (REQUALIFICATION-MANIFEST-N.json, N >= 2):
written once like the first, it names the revision it supersedes (path and sha256), why, and the stop record; the
commit it was written at; the versions it measures with — the runner and its contract, every kill file and the
process/cleanup harness, each by sha256; the execution order of the kill files (or the declared order) and the T0 and
preflight records, each by sha256. The first manifest's snapshot stays the phase's frozen SNAPSHOT
(v21_mutation_record.py): a revision's snapshot descends from it. --check reads the newest revision; for a revision it
also reports every version that moved since it was written."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import platform
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_REL = "closure-evidence/v2/v2.1/REQUALIFICATION-MANIFEST.json"
DECISIONS_REL = "closure-evidence/v2/cycle2/RELEASE-DECISIONS.json"
#: the v2.1 records of the round, in the order they are produced, with the tool that writes each
RECORDS = (
    ("closure-evidence/v2/v2.1/ARCHITECTURE-EXCEPTION-V2-007.json", "B-01 (lane b01; bound by the V2-007 amendment)"),
    ("closure-evidence/v2/v2.1/AISEF-V2-RFC-AMENDMENT-V2-007.json", "B-01"),
    ("closure-evidence/v2/v2.1/AISEF-V2-FREEZE-MANIFEST.json", "validation/v2/freeze_manifest.py"),
    ("closure-evidence/v2/v2.1/MUTATION.json", "validation/qualification/v21_mutation_record.py --write (workers: mutation.py run)"),
    ("closure-evidence/v2/v2.1/MUTATION-SUMMARY.json", "validation/qualification/v21_mutation_record.py --write"),
    ("closure-evidence/v2/v2.1/AUTHORITY-INVENTORY.json", "validation/qualification/release_inventory.py --write"),
    ("closure-evidence/v2/v2.1/P2-STATIC-ADMISSION.json", "validation/v2/p2_evidence.py"),
    ("closure-evidence/v2/v2.1/Q0-CHECKER-CALIBRATION.json", "validation/v2/checker_calibration.py"),
    ("closure-evidence/v2/v2.1/P5-PLAN-V2.2-PROPOSAL.json", "validation/qualification/p5_acceptance.py --write-v21-proposal"),
    ("closure-evidence/v2/v2.1/P5-FALSIFIABILITY.json", "validation/qualification/p5_falsifiability.py --run-v21"),
    ("closure-evidence/v2/v2.1/C2-P5-ACCEPTANCE-REVERIFICATION.json", "validation/qualification/p5_acceptance.py --write-v21"),
    ("closure-evidence/v2/v2.1/PLAN-V2.2-CORRECTION-1.json", "validation/qualification/c2_plan_correction.py --write"),
    ("closure-evidence/v2/v2.1/K-NOWORK-001-REHEARSAL.json", "validation/qualification/c2_k_nowork_001.py --write"),
    ("closure-evidence/v2/v2.1/Q5-KERNEL-COMPARISON.json", "validation/qualification/v21_q5_compare.py --write"),
    ("closure-evidence/v2/v2.1/CONFORMANCE-RULING.json", "validation/qualification/v21_conformance_ruling.py --write"),
)


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, encoding="utf-8", check=True).stdout.strip()


def _sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def scope() -> dict:
    """What the tree says the round covers now (the part --check compares)."""
    from validation.v2 import checker_calibration as cc
    from validation.v2 import mutation as m
    from validation.qualification import q5
    targets, by_module = {}, {}
    for t, kill in sorted(m.V21_TARGETS.items()):
        rel, func = t.split("::")
        src = (ROOT / rel).read_text(encoding="utf-8")
        n = len(m.mutants(src, func, m._enum_members(src, ROOT)))
        targets[t] = {"kill_tests": kill, "mutants": n}
        by_module.setdefault(rel, [0, 0])
        by_module[rel][0] += 1
        by_module[rel][1] += n
    return {"mutation": {"phase": "V2.1", "record": m.RECORDS["V2.1"], "timeout_s_per_kill_file": m.TIMEOUT,
                         "targets": targets, "target_count": len(targets),
                         "mutant_count": sum(r["mutants"] for r in targets.values()),
                         "by_module": {k: {"targets": a, "mutants": b} for k, (a, b) in sorted(by_module.items())}},
            "checkers": sorted(make().name for make in cc.REGISTRY),
            "q5_corpus": [i.id for i in q5.CORPUS]}


def build(base: str, campaign: str) -> dict:
    decisions = json.loads((ROOT / DECISIONS_REL).read_text(encoding="utf-8"))
    entries = {e["seq"]: e for e in decisions["entries"]}
    return {
        "record": "AISEF V2.1 — REQUALIFICATION ROUND SCOPE MANIFEST (B-03)",
        "authority": [{"ledger": DECISIONS_REL, "seq": s, "id": entries[s]["id"], "approver": entries[s]["approver"]} for s in (4, 5)],
        "base": base, "snapshot": _git("rev-parse", "HEAD"), "snapshot_aisef2_tree": _git("rev-parse", "HEAD:aisef2"),
        "the_reported_320": "checked against the tree at the base: every target whose module digest differs from its record's "
                            "source_sha256 — P2 15, P6 2, C2-P1 42, V2.0-S2 261 = 320 (7,482 recorded mutants; the current "
                            "generator yields 7,912 for them, line shifts)",
        "not_targets": {"names with no mutant": "a run that cannot say NO proves nothing (mutation.py)",
                        "aisef2/app/calibrations.py::CALIBRATIONS": "generated data (release_calibration.py rewrites it), proven by its "
                                                                    "calibration record and admission check 9, not by mutating its rows"},
        **scope(),
        "records": [{"path": p, "tool": t} for p, t in RECORDS],
        "environment": {"system": platform.platform(), "python": platform.python_version(), "executable": sys.executable,
                        "worker": "env -i; PATH with every directory holding an executable `opencode` removed; HOME, "
                                  "XDG_CONFIG/DATA/STATE/CACHE and TMPDIR in the worker's own scratch directory; "
                                  "validation/v2/owned_run.py around each worker (processes before / at exit / after); "
                                  "a detached git worktree per worker at the snapshot; no real client, provider, credential "
                                  "or operator data reachable",
                        "campaign": campaign},
        "rule": "written once (mode 'x'); a later change of scope is a new record, never an edit",
    }


STOP_REL = "closure-evidence/v2/v2.1/campaign-1-stopped/CAMPAIGN-1-STOP.json"
#: what a campaign measures with, besides the kill files: the runner, its contract and the process/cleanup harness
HARNESS = ("validation/v2/mutation.py", "docs/v2.1/MUTATION-RUNNER-V2.md", "validation/v2/owned_run.py",
           "validation/v2/cleanup_authority.py", "aisef2/runtime/process_range.py")


def revision_rel(n: int) -> str:
    return OUT_REL if n == 1 else OUT_REL.replace(".json", f"-{n}.json")


def newest(root: pathlib.Path | None = None) -> int:
    """The highest revision written (0 when none)."""
    root = ROOT if root is None else root     # read at call time: ROOT is the tree checked
    n = 0
    while (root / revision_rel(n + 1)).is_file():
        n += 1
    return n


def _pinned(rel: str | None) -> dict | None:
    return None if rel is None else {"path": rel, "sha256": _sha(rel)}


def versions() -> dict:
    """Every file the campaign measures with, by sha256 (LF): the harness and each distinct kill file."""
    from validation.v2 import mutation as m
    kill = sorted({f for k in m.V21_TARGETS.values() for f in k})
    return {"harness": {rel: _sha(rel) for rel in HARNESS if (ROOT / rel).is_file()},
            "kill_files": {rel: _sha(rel) for rel in kill}}


def build_revision(n: int, reason: str, campaign: str, execution_order: str | None, t0: str | None,
                   preflight: str | None) -> dict:
    from validation.qualification import v21_mutation_record as R
    prev_rel = revision_rel(n - 1)
    if n < 2 or not (ROOT / prev_rel).is_file() or (ROOT / revision_rel(n)).exists():
        raise SystemExit(f"revision {n} needs revision {n - 1} ({prev_rel}) and no revision {n} yet")
    if not reason.strip():
        raise SystemExit("a revision says why it supersedes the previous one")
    prev = json.loads((ROOT / prev_rel).read_text(encoding="utf-8"))
    doc = build(prev["base"], campaign)
    if subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", R.SNAPSHOT, doc["snapshot"]]).returncode != 0:
        raise SystemExit(f"the snapshot {doc['snapshot']} does not descend from the phase's SNAPSHOT {R.SNAPSHOT}")
    return {**doc, "revision": n,
            "supersedes": {"path": prev_rel, "sha256": _sha(prev_rel), "reason": reason,
                           "stop_record": _pinned(STOP_REL) if (ROOT / STOP_REL).is_file() else None},
            "phase_snapshot": R.SNAPSHOT, "versions": versions(),
            "execution_order": _pinned(execution_order) or "the declared order of each kill set",
            "t0": _pinned(t0), "preflight": _pinned(preflight)}


def check() -> list[str]:
    n = newest()
    if not n:
        return [f"{OUT_REL} is missing"]
    rel = revision_rel(n)
    rec, now = json.loads((ROOT / rel).read_text(encoding="utf-8")), scope()
    out = []
    if n > 1:
        sup = rec.get("supersedes") or {}
        if sup.get("path") != revision_rel(n - 1) or sup.get("sha256") != _sha(revision_rel(n - 1)):
            out.append(f"{rel} does not name revision {n - 1} by its bytes")
        then, cur = rec.get("versions") or {}, versions()
        for kind in ("harness", "kill_files"):
            moved = sorted(f for f in set(then.get(kind, {})) | set(cur[kind]) if then.get(kind, {}).get(f) != cur[kind].get(f))
            if moved:
                out.append(f"{len(moved)} {kind.replace('_', ' ')} changed since {rel}: {moved[:10]}")
        for key in ("execution_order", "t0", "preflight"):
            pin = rec.get(key)
            if isinstance(pin, dict) and (not (ROOT / pin["path"]).is_file() or _sha(pin["path"]) != pin["sha256"]):
                out.append(f"the {key} record {pin['path']} is not the one {rel} names")
    for k in ("checkers", "q5_corpus"):
        if rec.get(k) != now[k]:
            out.append(f"the {k} changed since the manifest: {sorted(set(map(str, now[k])) ^ set(map(str, rec.get(k) or [])))[:10]}")
    old, new = rec.get("mutation", {}).get("targets", {}), now["mutation"]["targets"]
    moved = sorted(t for t in set(old) | set(new) if old.get(t) != new.get(t))
    if moved:
        out.append(f"{len(moved)} V2.1 target(s) or kill set(s) changed since the manifest: {moved[:10]}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    ap.add_argument("--base")
    ap.add_argument("--campaign", default="")
    ap.add_argument("--revision", type=int)
    ap.add_argument("--supersedes-reason", default="")
    ap.add_argument("--execution-order")
    ap.add_argument("--t0")
    ap.add_argument("--preflight")
    a = ap.parse_args(argv)
    if a.write and a.revision:
        doc = build_revision(a.revision, a.supersedes_reason, a.campaign, a.execution_order, a.t0, a.preflight)
        rel = revision_rel(a.revision)
        with (ROOT / rel).open("x", encoding="utf-8") as f:
            f.write(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
        print(f"wrote {rel}: revision {a.revision}, supersedes {doc['supersedes']['path']}; {doc['mutation']['target_count']} "
              f"targets, {doc['mutation']['mutant_count']} mutants, {len(doc['versions']['kill_files'])} kill files")
        return 0
    if a.write:
        if not a.base:
            ap.error("--write needs --base")
        doc = build(a.base, a.campaign)
        (ROOT / OUT_REL).parent.mkdir(parents=True, exist_ok=True)
        with (ROOT / OUT_REL).open("x", encoding="utf-8") as f:
            f.write(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
        print(f"wrote {OUT_REL}: {doc['mutation']['target_count']} targets, {doc['mutation']['mutant_count']} mutants, "
              f"{len(doc['checkers'])} checkers, {len(doc['q5_corpus'])} corpus items")
        return 0
    problems = check()
    for p in problems:
        print(f"FAIL  {p}")
    print("requalification manifest: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
