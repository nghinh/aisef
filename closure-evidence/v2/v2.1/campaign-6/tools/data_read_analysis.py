"""data_read_analysis.py BASE HEAD READ_SET.json DELTA.json OUT.json

The delta tool (`v21_snapshot_delta.py`) says a kill file READS a changed file when the measured read-set records that it
opened or looked up the file, or LISTED A DIRECTORY ABOVE it (any ancestor). A listing returns the names of the
directory's direct children and nothing below: the repository root listed by test_v21_confine.py (names of the top-level
entries) makes every file of the repository "read". This tool states the exact reading, from the same measured read-set:

    exact(kill file) = the changed files it OPENED
                     + the changed or added/removed DIRECT children of a directory it LISTED, when that directory's set
                       of children (names and types) differs between BASE and HEAD — a listing of `tests/v2` attributed
                       to aisef2/invariants/registry.py (`listed_by`: the discount of RULES["data"]) is counted as the
                       delta counts it (the registry keeps only the set of directories holding a test_*.py).

For every target the delta lists with `data_read` > 0 whose verdict is "can stand": the files its kill files exactly read
that changed, per kill file, and what is left of the delta's claim. Reads git objects only; writes OUT."""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[5]
base, head, rs_path, delta_path, out = sys.argv[1:6]


def git(*a):
    return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, check=True).stdout


def children(commit: str, d: str):
    spec = f"{commit}:{d}" if d not in ("", ".") else f"{commit}^{{tree}}"
    r = subprocess.run(["git", "-C", str(ROOT), "ls-tree", spec], capture_output=True, text=True, check=False)
    if r.returncode:
        return None
    return {line.split("\t", 1)[1]: line.split()[1] for line in r.stdout.splitlines()}   # name -> blob/tree


changed = set()
for line in git("diff", "--name-status", "-M", base, head).splitlines():
    parts = line.split("\t")
    changed.update(parts[1:])
rs = json.loads(pathlib.Path(rs_path).read_text())
delta = json.loads(pathlib.Path(delta_path).read_text())
kills = rs["kill_files"]
cache: dict[str, tuple] = {}


def dir_changed(d: str):
    """(children differ?, the direct children that were added, removed or changed type)."""
    if d not in cache:
        a, b = children(base, d), children(head, d)
        if a is None or b is None:
            cache[d] = (None, [])
        else:
            diff = sorted(n for n in set(a) | set(b) if a.get(n) != b.get(n) and (n not in a or n not in b or a[n] != b[n]))
            cache[d] = (bool(diff), diff)
    return cache[d]


def exact(kill_file: str) -> dict:
    v = kills[kill_file]
    opened = sorted(p for p in v["opened"] if p in changed)
    listed, discounted = [], []
    for d in v.get("listed", []):
        differs, names = dir_changed(d)
        if differs is None:      # a directory that is not in git at either commit: nothing to compare (runtime-made)
            continue
        by = v.get("listed_by", {}).get(d)
        if differs and by is not None and all(f == "aisef2/invariants/registry.py" for f in by):
            discounted.append(d)
            continue
        if differs:
            listed.append({"dir": d, "children_changed": names[:8], "n": len(names)})
    return {"opened_and_changed": opened, "listed_dirs_whose_children_changed": listed, "listing_discounted": discounted}


rows = {}
for t, v in sorted(delta["targets"].items()):
    if not (v["verdict"].startswith("a ") and v["data_read"]):
        continue
    kill_files = v.get("kill_files") or []
    # the delta's rows do not carry the kill set: take it from the harness registry at HEAD
    rows[t] = {"delta_data_read": v["data_read"]}
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from validation.v2 import mutation as m  # noqa: E402
for t in rows:
    per = {k: exact(k) for k in m.V21_TARGETS[t] if k in kills}
    rows[t]["kill_files"] = per
    rows[t]["exactly_read_and_changed"] = sorted({p for e in per.values() for p in e["opened_and_changed"]})
    rows[t]["listings_that_changed"] = sorted({x["dir"] for e in per.values() for x in e["listed_dirs_whose_children_changed"]})
    rows[t]["cleared"] = not rows[t]["exactly_read_and_changed"] and not rows[t]["listings_that_changed"]
doc = {"record": "AISEF V2.1 — campaign 6: the exact reading of the measured read-set for the targets the delta flags",
       "base": base, "head": head, "read_set": rs["commit"], "rule": __doc__.strip().split("\n\n")[1].strip(),
       "targets": rows}
pathlib.Path(out).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
for t, r in rows.items():
    print(("CLEARED " if r["cleared"] else "READS   "), t, r["exactly_read_and_changed"], r["listings_that_changed"])
