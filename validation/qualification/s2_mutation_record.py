"""V2.0 release, S2: the final V2.0-S2 mutation record, merged from the campaign's workers under the owner ruling
'AISEF V2.0 — OWNER RULING: MUTATION WORKER HANDOFF' (2026-10-04).

    python -P validation/qualification/s2_mutation_record.py --import NAME WORKTREE STATUS   # a worker's history, kept
    python -P validation/qualification/s2_mutation_record.py --write   # -> S2-MUTATION.json + S2-MUTATION-SUMMARY.json
    python -P validation/qualification/s2_mutation_record.py --check   # both files are what the histories derive now

Every worker's own record and log are kept byte for byte under WORKERS_REL as historical execution evidence (`--import`).
The final record may use a result only when (ruling, "FINAL S2 MUTATION EVIDENCE MAY USE ONLY"):

* it was measured on the current release snapshot (SNAPSHOT or a descendant), or it is an earlier result whose target
  implementation AND kill tests are mechanically proven unchanged — and in both cases, between the commit it was
  measured on and HEAD: the target file is byte-identical; its kill set is the current one; every file of the kill tests'
  closure (the kill-test files, the repository test modules they import, transitively, with their package inits, and
  every tests/ path their string literals name) is byte-identical; and the current generator yields the same mutants;
* its worker is not excluded: C's stale-snapshot results are never merged (§4), even where the proof would hold.

A current-snapshot result is preferred to an earlier one; nothing current is re-measured for symmetry. Repository
modules outside tests/ that the kill tests import and that changed are reported per reused result (`other_code_changed`),
not counted against it: the ruling binds the target implementation and the kill tests.

The final record names its FINAL_HEAD and puts every kept result in exactly one class (owner, 2026-10-04):
`measured_at_final_head` — the commit it was measured on has FINAL_HEAD's tree everywhere outside closure-evidence/;
`reused_after_mechanical_proof` — any other result that passes the proof against FINAL_HEAD (e.g. one measured on
369c8ac once HEAD moved past it); `stale_excluded` — a result the proof or the ruling refuses, or a second result for a
target already accounted for. Every target is accounted for exactly once. A chosen result passes only with no unaudited
survivor and no mutant killed by the clock alone; an errored run never passes. The reuse criteria (CRITERIA) are frozen:
their source hash must stay FROZEN_CRITERIA_SHA256 (819fe4d); the record carries it beside the whole file's hash.
"""

from __future__ import annotations

import argparse
import ast
import bisect
import functools
import hashlib
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WORKERS_REL = "closure-evidence/v2/release/s2-mutation-workers"
SUMMARY_REL = "closure-evidence/v2/release/S2-MUTATION-SUMMARY.json"
SNAPSHOT = "369c8ac147e2de24361bfd2315721295cd252ab2"
EXCLUDED = {"C": "owner ruling MUTATION WORKER HANDOFF §4: C's stale-snapshot results are not merged into the final verdict"}
ROOTS = ("tests", "aisef2", "aisef", "validation")
#: the reuse criteria: every definition proof() and the selection depend on (frozen at 819fe4d, before any result of the
#: current-snapshot campaign was qualified); a change to any of them changes criteria_sha256()
CRITERIA = ("SNAPSHOT", "EXCLUDED", "ROOTS", "_git", "_blobs", "blob", "_files", "_tests_index", "_named", "_module_file",
            "closure", "proof", "_current")
FROZEN_CRITERIA_SHA256 = "dee08768f72aaacf31d2dcd0f9fde9e354d088f6b8d1ee7c8031aef664afacc0"


class ArtifactMismatch(Exception):
    """A kept worker record or log is not the bytes its history recorded."""


def _git(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True)


@functools.lru_cache(maxsize=None)
def _blobs(root: pathlib.Path, rev: str) -> dict[str, str]:
    """path -> blob id of every file of commit `rev` (one `git ls-tree`)."""
    out = {}
    for entry in _git(root, "ls-tree", "-r", "-z", _git(root, "rev-parse", rev).stdout.decode().strip()).stdout.split(b"\0"):
        if entry:
            meta, path = entry.split(b"\t", 1)
            out[path.decode("utf-8", "replace")] = meta.split()[2].decode()
    return out


def blob(root: pathlib.Path, rev: str, path: str) -> str | None:
    return _blobs(root, rev).get(path)


@functools.lru_cache(maxsize=None)
def _files(root: pathlib.Path, rev: str) -> frozenset[str]:
    return frozenset(_blobs(root, rev))


@functools.lru_cache(maxsize=None)
def _tests_index(root: pathlib.Path, rev: str) -> tuple[list[str], frozenset[str]]:
    """The tests/ files of `rev`, sorted, and every directory that holds one."""
    names = sorted(x for x in _files(root, rev) if x.startswith("tests/"))
    return names, frozenset("/".join(x.split("/")[:k]) for x in names for k in range(1, x.count("/") + 1))


def _named(root: pathlib.Path, rev: str, cand: str) -> list[str]:
    names, dirs = _tests_index(root, rev)
    if cand in dirs:    # the files under a directory are contiguous in sorted order
        out = []
        for x in names[bisect.bisect_left(names, cand + "/"):]:
            if not x.startswith(cand + "/"):
                break
            out.append(x)
        return out
    return [cand] if cand in _files(root, rev) else []


def _module_file(files: frozenset[str], module: str) -> str | None:
    p = module.replace(".", "/")
    return next((c for c in (p + ".py", p + "/__init__.py") if c in files), None)


@functools.lru_cache(maxsize=None)
def closure(root: pathlib.Path, rev: str, start: tuple[str, ...]) -> frozenset[str]:
    """The files of `rev` the kill tests `start` consist of: themselves, the repository modules they import (transitively,
    package inits included), and every tests/ file or directory their string literals name."""
    files, seen, todo = _files(root, rev), set(), list(start)
    while todo:
        f = todo.pop()
        if f in seen or f not in files:
            continue
        seen.add(f)
        parts = f.split("/")
        todo += [i for i in ("/".join(parts[:k]) + "/__init__.py" for k in range(1, len(parts))) if i in files]
        if not f.endswith(".py"):
            continue
        try:
            tree = ast.parse(_git(root, "show", f"{rev}:{f}").stdout)
        except SyntaxError:
            continue
        pkg = ".".join(parts[:-1])
        for n in ast.walk(tree):
            mods: list[str] = []
            if isinstance(n, ast.Import):
                mods = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                base = n.module or ""
                if n.level:
                    up = pkg.split(".")[: len(pkg.split(".")) - (n.level - 1)]
                    base = ".".join(up + ([base] if base else []))
                mods = [base] + [f"{base}.{a.name}" for a in n.names]
            elif isinstance(n, ast.Constant) and isinstance(n.value, str) and f.startswith("tests/") \
                    and 0 < len(n.value) < 300 and "\n" not in n.value and any(c.isalnum() for c in n.value):  # "/" names nothing
                for cand in (n.value.strip("/"), f"{'/'.join(parts[:-1])}/{n.value}".strip("/")):
                    if cand.startswith("tests/"):
                        todo += _named(root, rev, cand)
            todo += [mf for mo in mods if mo.split(".")[0] in ROOTS and (mf := _module_file(files, mo))]
    return frozenset(seen)


def proof(root: pathlib.Path, result: dict, measured_on: str, head: str = "HEAD") -> tuple[list[str], list[str]]:
    """(why `result`, measured on commit `measured_on`, may not be used at `head` — [] = it may; repository modules
    outside tests/ in its kill tests' closure that changed since)."""
    from validation.v2 import mutation as m
    target = result["target"]
    rel, func = target.split("::")
    if result.get("error"):
        return [f"the run errored: {result['error'][:200]}"], []
    out = []
    if target not in m.S2_TARGETS:
        return ["not a V2.0-S2 target"], []
    if blob(root, measured_on, rel) != blob(root, head, rel):
        out.append("the target file changed since it was measured")
    if result["kill_tests"] != m.S2_TARGETS[target]:
        out.append("its kill set is not the current one")
    kill = tuple(result["kill_tests"])
    files = closure(root, head, kill) | closure(root, measured_on, kill)
    changed = sorted(f for f in files if blob(root, measured_on, f) != blob(root, head, f))
    tests = [f for f in changed if f.startswith("tests/")]
    if tests:
        out.append(f"kill tests changed: {', '.join(tests)}")
    if not out:
        src = _git(root, "show", f"{head}:{rel}").stdout.decode("utf-8")
        if [d for d, _ in m.mutants(src, func, m._enum_members(src, root))] != [r["mutant"] for r in result["results"]]:
            out.append("its mutants are not the current generator's")
    return out, [f for f in changed if not f.startswith("tests/") and f != rel]


def _current(root: pathlib.Path, measured_on: str) -> bool:
    return _git(root, "merge-base", "--is-ancestor", SNAPSHOT, measured_on).returncode == 0


def histories(root: pathlib.Path = ROOT) -> list[dict]:
    """Every kept worker history, its record's results read from the record file it kept byte for byte; the record and
    the log must both be the bytes the history recorded."""
    out = []
    for p in sorted((root / WORKERS_REL).glob("*.history.json")):
        h = json.loads(p.read_text(encoding="utf-8"))
        log = root / h["log"]["path"]
        if not log.exists() or _sha256(log) != h["log"]["sha256"]:
            raise ArtifactMismatch(f"{h['log']['path']} is not the log {p.name} kept")
        rec = h["record"] and root / h["record"]["path"]
        if rec and (not rec.exists() or _sha256(rec) != h["record"]["sha256"]):
            raise ArtifactMismatch(f"{h['record']['path']} is not the record {p.name} kept")
        out.append({**h, "targets": json.loads(rec.read_text(encoding="utf-8"))["targets"] if rec else []})
    return out


def criteria_sha256(path: pathlib.Path = HERE / "s2_mutation_record.py") -> str:
    """sha256 of the source of the CRITERIA definitions, in CRITERIA order."""
    src = path.read_text(encoding="utf-8")
    parts = {}
    for n in ast.parse(src).body:
        name = getattr(n, "name", None) or (n.targets[0].id if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) else None)
        if name in CRITERIA:
            parts[name] = ast.get_source_segment(src, n)
    return hashlib.sha256("\n\n".join(parts[c] for c in CRITERIA).encode()).hexdigest()


def at_final_head(root: pathlib.Path, measured_on: str, final_head: str) -> bool:
    """The commit a result was measured on has `final_head`'s tree everywhere outside closure-evidence/."""
    return _git(root, "diff", "--quiet", measured_on, final_head, "--", ".", ":(exclude)closure-evidence").returncode == 0


def _timeouts(result: dict) -> int:
    return sum(1 for x in result.get("results", []) if x.get("timed_out"))


def account(rows: list[dict], targets, audited=frozenset()) -> dict:
    """Selection and accounting over the kept results. `rows`: one per result — worker, measured_on, target, why (the
    frozen proof's refusals or the ruling's exclusion; [] = qualified), current (measured on SNAPSHOT or a descendant),
    at_final_head, other_code_changed, result. A qualified current-snapshot result is preferred to an earlier one;
    otherwise the first kept. Every target ends in exactly one place: chosen (and then one of the two classes), or
    missing."""
    chosen: dict[str, dict] = {}
    stale: list[dict] = []
    for r in rows:
        key = {k: r[k] for k in ("worker", "measured_on", "target")}
        if r["why"]:
            stale.append({**key, "why": list(r["why"])})
            continue
        prior = chosen.get(r["target"])
        if prior is None or (r["current"] and not prior["current"]):
            if prior is not None:
                stale.append({k: prior[k] for k in ("worker", "measured_on", "target")} | {"why": ["superseded by a current-snapshot result"]})
            chosen[r["target"]] = r
        else:
            stale.append({**key, "why": ["a result already chosen for this target"]})
    not_passing = {}
    for t, r in sorted(chosen.items()):
        res, why = r["result"], []
        if res.get("error"):
            why.append(f"the run errored: {res['error'][:200]}")
        unaud = [s for s in res.get("survivors", []) if (t, s) not in audited]
        if unaud:
            why.append(f"{len(unaud)} unaudited survivor(s): {unaud}")
        if _timeouts(res):
            why.append(f"{_timeouts(res)} mutant(s) killed only by the clock")
        if res.get("mutants", 0) == 0:
            why.append("no mutants generated")
        if why:
            not_passing[t] = why
    return {"chosen": chosen, "stale_excluded": stale, "not_passing": not_passing,
            "measured_at_final_head": sorted(t for t, r in chosen.items() if r["at_final_head"]),
            "reused_after_mechanical_proof": sorted(t for t, r in chosen.items() if not r["at_final_head"]),
            "missing": sorted(set(targets) - set(chosen)), "unknown": sorted(set(chosen) - set(targets)),
            "accounted_exactly_once": set(chosen) == set(targets)}


def build(root: pathlib.Path = ROOT, head: str = "HEAD") -> tuple[dict, dict]:
    from validation.v2 import mutation as m
    final = _git(root, "rev-parse", head).stdout.decode().strip()
    rows: list[dict] = []
    seen_before: set[str] = set()
    for h in histories(root):
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
                         "at_final_head": not why and at_final_head(root, h["snapshot"], final)})
    a = account(rows, m.S2_TARGETS, frozenset(m.AUDITED))
    chosen = a["chosen"]
    targets = sorted((c["result"] for c in chosen.values()), key=lambda x: x["target"])
    record = {"record": "AISEF V2 — V2.0-S2 MUTATION", "tool": "validation/v2/mutation.py",
              "merged_by": "validation/qualification/s2_mutation_record.py", "targets": targets}
    problems = m.problems_of(record, root, "V2.0-S2")
    audited = sum(1 for t in targets for s in t["survivors"] if (t["target"], s) in m.AUDITED)
    unaudited = sum(1 for t in targets for s in t["survivors"] if (t["target"], s) not in m.AUDITED)
    timeouts = sum(_timeouts(t) for t in targets)
    crit = criteria_sha256()
    passing = (a["accounted_exactly_once"] and not problems and not unaudited and not timeouts and not a["not_passing"]
               and crit == FROZEN_CRITERIA_SHA256)
    stale = a["stale_excluded"]
    summary = {
        "record": "AISEF V2.0 — S2 MUTATION, FINAL (owner rulings 'MUTATION WORKER HANDOFF' and its follow-ups, 2026-10-04)",
        "snapshot": SNAPSHOT,
        "FINAL_HEAD": final,
        "TOTAL_TARGETS": len(m.S2_TARGETS),
        "ACCOUNTED_EXACTLY_ONCE": a["accounted_exactly_once"],
        "measured_at_final_head": len(a["measured_at_final_head"]),
        "reused_after_mechanical_proof": len(a["reused_after_mechanical_proof"]),
        "stale_excluded": len(stale),
        "CURRENT_SNAPSHOT_TARGETS": len(a["measured_at_final_head"]),
        "MUTANTS": sum(t["mutants"] for t in targets),
        "KILLED": sum(t["killed"] for t in targets) - timeouts,
        "KILLED_BY_TIMEOUT": timeouts,
        "AUDITED_SURVIVORS": audited,
        "UNAUDITED_SURVIVORS": unaudited,
        "STALE_RESULTS_EXCLUDED": len(stale),
        "STALE_RESULTS_EXCLUDED_BY_REASON": {
            "worker excluded by the ruling (C)": sum(1 for e in stale if e["worker"] in EXCLUDED),
            "proof failed": sum(1 for e in stale if e["worker"] not in EXCLUDED and not e["why"][0].startswith(("superseded", "a result already"))),
            "superseded or duplicate": sum(1 for e in stale if e["why"][0].startswith(("superseded", "a result already")))},
        "RERUN_TARGETS": len([t for t, c in chosen.items() if c["current"] and t in seen_before]),
        "MISSING_TARGETS": a["missing"],
        "NOT_PASSING": a["not_passing"],
        "problems": problems,
        "qualifier": {"path": "validation/qualification/s2_mutation_record.py",
                      "file_sha256": _sha256(HERE / "s2_mutation_record.py"),
                      "criteria_sha256": crit, "criteria_sha256_frozen_at_819fe4d": FROZEN_CRITERIA_SHA256,
                      "criteria_unchanged": crit == FROZEN_CRITERIA_SHA256},
        "S2_MUTATION_VERDICT": "PASS" if passing else "FAIL",
        "workers": [{k: h[k] for k in ("worker", "snapshot", "status", "log", "record")} | {"results": len(h["targets"])}
                    for h in histories(root)],
        "classes": {"measured_at_final_head": a["measured_at_final_head"],
                    "reused_after_mechanical_proof": a["reused_after_mechanical_proof"]},
        "provenance": {t: {"worker": c["worker"], "measured_on": c["measured_on"],
                           "class": "measured_at_final_head" if c["at_final_head"] else "reused_after_mechanical_proof",
                           **({"other_code_changed": c["other_code_changed"]} if c["other_code_changed"] else {})}
                       for t, c in sorted(chosen.items())},
        "stale_excluded_results": stale,
    }
    return record, summary


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def import_worker(name: str, worktree: pathlib.Path, status: str, log: pathlib.Path, root: pathlib.Path = ROOT) -> pathlib.Path:
    """Keep worker `name`'s record and log byte for byte, with the commit its snapshot worktree measured on."""
    from validation.v2 import mutation as m
    snap = _git(worktree, "rev-parse", "HEAD").stdout.decode().strip()
    rec = worktree / m.RECORDS["V2.0-S2"]
    out = root / WORKERS_REL
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.log").write_bytes(log.read_bytes())
    if rec.exists():
        (out / f"{name}.record.json").write_bytes(rec.read_bytes())
    doc = {"worker": name, "snapshot": snap, "status": status,
           "log": {"path": f"{WORKERS_REL}/{name}.log", "sha256": _sha256(log)},
           "record": {"path": f"{WORKERS_REL}/{name}.record.json", "sha256": _sha256(rec)} if rec.exists() else None}
    (out / f"{name}.history.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return out / f"{name}.history.json"


def _render(obj) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False) + "\n"


def check(root: pathlib.Path = ROOT) -> list[str]:
    """[] when the committed record and summary are what the kept artifacts derive at the summary's FINAL_HEAD, HEAD's
    tree outside closure-evidence/ is FINAL_HEAD's, and the verdict is PASS."""
    from validation.v2 import mutation as m
    path = root / SUMMARY_REL
    if not path.exists():
        return [f"{SUMMARY_REL} is missing"]
    final = json.loads(path.read_text(encoding="utf-8"))["FINAL_HEAD"]
    if not at_final_head(root, final, "HEAD"):
        return [f"HEAD mismatch: HEAD's tree outside closure-evidence/ is not FINAL_HEAD {final[:12]}'s"]
    try:
        record, summary = build(root, final)
    except ArtifactMismatch as e:
        return [str(e)]
    out = [f"{rel} is not what the kept artifacts derive" for rel, body in ((m.RECORDS["V2.0-S2"], record), (SUMMARY_REL, summary))
           if not (root / rel).exists() or (root / rel).read_text(encoding="utf-8") != _render(body)]
    if summary["S2_MUTATION_VERDICT"] != "PASS":
        out.append(f"verdict {summary['S2_MUTATION_VERDICT']}: missing {len(summary['MISSING_TARGETS'])}, not passing "
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
        (ROOT / m.RECORDS["V2.0-S2"]).write_text(_render(record), encoding="utf-8")
        (ROOT / SUMMARY_REL).write_text(_render(summary), encoding="utf-8")
        print(_render({k: v for k, v in summary.items() if k not in ("provenance", "stale_excluded_results", "workers", "classes")}))
        return 0 if summary["S2_MUTATION_VERDICT"] == "PASS" else 1
    problems = check()
    for p in problems:
        print(f"FAIL  {p}")
    print("s2 mutation record: " + ("FAIL" if problems else "PASS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
