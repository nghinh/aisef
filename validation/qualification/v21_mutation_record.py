"""V2.1 requalification round, B-03b: the final V2.1 mutation record, merged from the campaign's workers (owner
directive 2026-10-06, closure-evidence/v2/cycle2/RELEASE-DECISIONS.json seq 5).

    python -P validation/qualification/v21_mutation_record.py --import NAME WORKTREE STATUS LOG   # a worker's history, kept
    python -P validation/qualification/v21_mutation_record.py --write   # -> v2.1/MUTATION.json + v2.1/MUTATION-SUMMARY.json
    python -P validation/qualification/v21_mutation_record.py --check   # both files are what the histories derive now

The V2.0-S2 standard, unchanged (validation/qualification/s2_mutation_record.py, whose closure/blob/selection this module
reuses): every worker's own record and log are kept byte for byte under WORKERS_REL; the final record may use a result
only when, between the commit it was measured on and the final head, the target file is byte-identical, its kill set
is the current one (mutation.V21_TARGETS), every file of the kill tests' closure is byte-identical, and the current
generator yields the same mutants. A result measured on SNAPSHOT or a descendant is preferred; a chosen result passes
only with no unaudited survivor, no mutant killed by the clock alone and no error. Every V2.1 target is accounted for
exactly once, as `measured_at_final_head` or `reused_after_mechanical_proof`; every other kept result is
`stale_excluded`, with why. The reuse criteria are frozen (CRITERIA, FROZEN_CRITERIA_SHA256) before any result is
qualified; the S2 functions they reuse are frozen by S2's own pinned hash, which the summary carries too."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import s2_mutation_record as S2  # noqa: E402

PHASE = "V2.1"
WORKERS_REL = "closure-evidence/v2/v2.1/mutation-workers"
SUMMARY_REL = "closure-evidence/v2/v2.1/MUTATION-SUMMARY.json"
SNAPSHOT = "cc5359699c057f666f1693b90f1beb4762676478"   # the campaign's snapshot (REQUALIFICATION-MANIFEST.json), frozen before any result
EXCLUDED: dict[str, str] = {}
CRITERIA = ("PHASE", "SNAPSHOT", "EXCLUDED", "proof", "_current")
FROZEN_CRITERIA_SHA256 = "9e6f9d39bee3b76549071a326bd32dd85d50d705ed18c396c8764a4c10b3dbdf"


def proof(root: pathlib.Path, result: dict, measured_on: str, head: str = "HEAD") -> tuple[list[str], list[str]]:
    """(why `result`, measured on commit `measured_on`, may not be used at `head` — [] = it may; repository modules
    outside tests/ in its kill tests' closure that changed since)."""
    from validation.v2 import mutation as m
    target = result["target"]
    rel, func = target.split("::")
    if result.get("error"):
        return [f"the run errored: {result['error'][:200]}"], []
    if target not in m.V21_TARGETS:
        return [f"not a {PHASE} target"], []
    out = []
    if S2.blob(root, measured_on, rel) != S2.blob(root, head, rel):
        out.append("the target file changed since it was measured")
    if result["kill_tests"] != m.V21_TARGETS[target]:
        out.append("its kill set is not the current one")
    kill = tuple(result["kill_tests"])
    files = S2.closure(root, head, kill) | S2.closure(root, measured_on, kill)
    changed = sorted(f for f in files if S2.blob(root, measured_on, f) != S2.blob(root, head, f))
    tests = [f for f in changed if f.startswith("tests/")]
    if tests:
        out.append(f"kill tests changed: {', '.join(tests)}")
    if not out:
        src = S2._git(root, "show", f"{head}:{rel}").stdout.decode("utf-8")
        if [d for d, _ in m.mutants(src, func, m._enum_members(src, root))] != [r["mutant"] for r in result["results"]]:
            out.append("its mutants are not the current generator's")
    return out, [f for f in changed if not f.startswith("tests/") and f != rel]


def _current(root: pathlib.Path, measured_on: str) -> bool:
    return SNAPSHOT is not None and S2._git(root, "merge-base", "--is-ancestor", SNAPSHOT, measured_on).returncode == 0


def criteria_sha256(path: pathlib.Path = HERE / "v21_mutation_record.py") -> str:
    """sha256 of the source of the CRITERIA definitions, in CRITERIA order."""
    src = path.read_text(encoding="utf-8")
    parts = {}
    for n in ast.parse(src).body:
        target = n.targets[0] if isinstance(n, ast.Assign) else n.target if isinstance(n, ast.AnnAssign) else None
        name = getattr(n, "name", None) or (target.id if isinstance(target, ast.Name) else None)
        if name in CRITERIA:
            parts[name] = ast.get_source_segment(src, n)
    return hashlib.sha256("\n\n".join(parts[c] for c in CRITERIA).encode()).hexdigest()


def histories(root: pathlib.Path = ROOT) -> list[dict]:
    """Every kept worker history, its results read from the record it kept; the record and the log must both be the
    bytes the history recorded."""
    out = []
    for p in sorted((root / WORKERS_REL).glob("*.history.json")):
        h = json.loads(p.read_text(encoding="utf-8"))
        log = root / h["log"]["path"]
        if not log.exists() or S2._sha256(log) != h["log"]["sha256"]:
            raise S2.ArtifactMismatch(f"{h['log']['path']} is not the log {p.name} kept")
        rec = h["record"] and root / h["record"]["path"]
        if rec and (not rec.exists() or S2._sha256(rec) != h["record"]["sha256"]):
            raise S2.ArtifactMismatch(f"{h['record']['path']} is not the record {p.name} kept")
        out.append({**h, "targets": json.loads(rec.read_text(encoding="utf-8"))["targets"] if rec else []})
    return out


def build(root: pathlib.Path = ROOT, head: str = "HEAD") -> tuple[dict, dict]:
    from validation.v2 import mutation as m
    final = S2._git(root, "rev-parse", head).stdout.decode().strip()
    rows: list[dict] = []
    seen_before: set[str] = set()
    kept = histories(root)
    for h in kept:
        for t in h["targets"]:
            row = {"worker": h["worker"], "measured_on": h["snapshot"], "target": t["target"], "result": t,
                   "current": False, "at_final_head": False, "other_code_changed": []}
            if h["worker"] in EXCLUDED:
                rows.append({**row, "why": [EXCLUDED[h["worker"]]]})
                seen_before.add(t["target"])
                continue
            why, other = proof(root, t, h["snapshot"], final)
            current = _current(root, h["snapshot"])
            if not current:
                seen_before.add(t["target"])
            rows.append({**row, "why": why, "current": current, "other_code_changed": other,
                         "at_final_head": not why and S2.at_final_head(root, h["snapshot"], final)})
    a = S2.account(rows, m.V21_TARGETS, frozenset(m.AUDITED))
    chosen = a["chosen"]
    targets = sorted((c["result"] for c in chosen.values()), key=lambda x: x["target"])
    record = {"record": "AISEF V2.1 — MUTATION (requalification round B-03b)", "tool": "validation/v2/mutation.py",
              "merged_by": "validation/qualification/v21_mutation_record.py", "targets": targets}
    problems = m.problems_of(record, root, PHASE)
    audited = sum(1 for t in targets for s in t["survivors"] if (t["target"], s) in m.AUDITED)
    unaudited = sum(1 for t in targets for s in t["survivors"] if (t["target"], s) not in m.AUDITED)
    timeouts = sum(S2._timeouts(t) for t in targets)
    crit, s2crit = criteria_sha256(), S2.criteria_sha256()
    frozen = FROZEN_CRITERIA_SHA256 is not None and crit == FROZEN_CRITERIA_SHA256 and s2crit == S2.FROZEN_CRITERIA_SHA256
    passing = a["accounted_exactly_once"] and not problems and not unaudited and not timeouts and not a["not_passing"] and frozen
    stale = a["stale_excluded"]
    summary = {
        "record": "AISEF V2.1 — MUTATION, FINAL (owner directive B-03b, 2026-10-06; RELEASE-DECISIONS seq 5)",
        "phase": PHASE,
        "snapshot": SNAPSHOT,
        "FINAL_HEAD": final,
        "TOTAL_TARGETS": len(m.V21_TARGETS),
        "ACCOUNTED_EXACTLY_ONCE": a["accounted_exactly_once"],
        "measured_at_final_head": len(a["measured_at_final_head"]),
        "reused_after_mechanical_proof": len(a["reused_after_mechanical_proof"]),
        "MUTANTS": sum(t["mutants"] for t in targets),
        "KILLED": sum(t["killed"] for t in targets) - timeouts,
        "KILLED_BY_TIMEOUT": timeouts,
        "AUDITED_SURVIVORS": audited,
        "UNAUDITED_SURVIVORS": unaudited,
        "STALE_RESULTS_EXCLUDED": len(stale),
        "RERUN_TARGETS": len([t for t, c in chosen.items() if c["current"] and t in seen_before]),
        "MISSING_TARGETS": a["missing"],
        "NOT_PASSING": a["not_passing"],
        "problems": problems,
        "qualifier": {"path": "validation/qualification/v21_mutation_record.py",
                      "file_sha256": S2._sha256(HERE / "v21_mutation_record.py"),
                      "criteria_sha256": crit, "criteria_sha256_frozen": FROZEN_CRITERIA_SHA256,
                      "s2_criteria_sha256": s2crit, "s2_criteria_sha256_frozen": S2.FROZEN_CRITERIA_SHA256,
                      "criteria_unchanged": frozen},
        "MUTATION_VERDICT": "PASS" if passing else "FAIL",
        "workers": [{k: h[k] for k in ("worker", "snapshot", "status", "log", "record")} | {"results": len(h["targets"])}
                    for h in kept],
        "classes": {"measured_at_final_head": a["measured_at_final_head"],
                    "reused_after_mechanical_proof": a["reused_after_mechanical_proof"]},
        "provenance": {t: {"worker": c["worker"], "measured_on": c["measured_on"],
                           "class": "measured_at_final_head" if c["at_final_head"] else "reused_after_mechanical_proof",
                           **({"other_code_changed": c["other_code_changed"]} if c["other_code_changed"] else {})}
                       for t, c in sorted(chosen.items())},
        "stale_excluded_results": stale,
    }
    return record, summary


def import_worker(name: str, worktree: pathlib.Path, status: str, log: pathlib.Path, root: pathlib.Path = ROOT) -> pathlib.Path:
    """Keep worker `name`'s record and log byte for byte, with the commit its snapshot worktree measured on. A history
    already kept is never replaced."""
    from validation.v2 import mutation as m
    snap = S2._git(worktree, "rev-parse", "HEAD").stdout.decode().strip()
    rec = worktree / m.RECORDS[PHASE]
    out = root / WORKERS_REL
    out.mkdir(parents=True, exist_ok=True)
    with (out / f"{name}.log").open("xb") as f:
        f.write(log.read_bytes())
    if rec.exists():
        with (out / f"{name}.record.json").open("xb") as f:
            f.write(rec.read_bytes())
    doc = {"worker": name, "snapshot": snap, "status": status,
           "log": {"path": f"{WORKERS_REL}/{name}.log", "sha256": S2._sha256(log)},
           "record": {"path": f"{WORKERS_REL}/{name}.record.json", "sha256": S2._sha256(rec)} if rec.exists() else None}
    with (out / f"{name}.history.json").open("x", encoding="utf-8") as f:
        f.write(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    return out / f"{name}.history.json"


def check(root: pathlib.Path = ROOT) -> list[str]:
    """[] when the committed record and summary are what the kept artifacts derive at the summary's FINAL_HEAD, HEAD's
    tree outside closure-evidence/ is FINAL_HEAD's, and the verdict is PASS."""
    from validation.v2 import mutation as m
    path = root / SUMMARY_REL
    if not path.exists():
        return [f"{SUMMARY_REL} is missing"]
    final = json.loads(path.read_text(encoding="utf-8"))["FINAL_HEAD"]
    if not S2.at_final_head(root, final, "HEAD"):
        return [f"HEAD mismatch: HEAD's tree outside closure-evidence/ is not FINAL_HEAD {final[:12]}'s"]
    try:
        record, summary = build(root, final)
    except S2.ArtifactMismatch as e:
        return [str(e)]
    out = [f"{rel} is not what the kept artifacts derive" for rel, body in ((m.RECORDS[PHASE], record), (SUMMARY_REL, summary))
           if not (root / rel).exists() or (root / rel).read_text(encoding="utf-8") != S2._render(body)]
    if summary["MUTATION_VERDICT"] != "PASS":
        out.append(f"verdict {summary['MUTATION_VERDICT']}: missing {len(summary['MISSING_TARGETS'])}, not passing "
                   f"{len(summary['NOT_PASSING'])}, problems {summary['problems'][:3]}")
    return out


def main(argv: list[str] | None = None) -> int:
    from validation.v2 import mutation as m
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--import", dest="imp", nargs=4, metavar=("NAME", "WORKTREE", "STATUS", "LOG"))
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    ap.add_argument("--head", default="HEAD", help="--write: the final head the record is derived at")
    a = ap.parse_args(argv)
    if a.imp:
        name, wt, status, log = a.imp
        print(import_worker(name, pathlib.Path(wt), status, pathlib.Path(log)))
        return 0
    if a.write:
        record, summary = build(ROOT, a.head)
        (ROOT / m.RECORDS[PHASE]).write_text(S2._render(record), encoding="utf-8")
        (ROOT / SUMMARY_REL).write_text(S2._render(summary), encoding="utf-8")
        print(S2._render({k: v for k, v in summary.items() if k not in ("provenance", "stale_excluded_results", "workers", "classes")}))
        return 0 if summary["MUTATION_VERDICT"] == "PASS" else 1
    problems = check()
    for p in problems:
        print(f"FAIL  {p}")
    print("v2.1 mutation record: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
