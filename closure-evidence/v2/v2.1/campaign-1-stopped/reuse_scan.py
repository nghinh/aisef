"""reuse_scan.py: for every target the stopped V2.1 campaign COMPLETED, the facts the reuse table needs — the existing
rules (target file, kill set, kill-test closure, mutant list vs the snapshot) and the stale-bytecode exposure: whether any two
CONSECUTIVE sources the runner wrote into the module file (the original, then each mutant in order) have the same byte size
(only then can CPython's mtime+size .pyc check serve the previous mutant's bytecode)."""
import json, pathlib, sys
STOP, W = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
sys.path.insert(0, str(W))
from validation.v2 import mutation as m  # noqa: E402
rows = []
for n in range(1, 5):
    rec = json.loads((STOP / f"m21-w{n}.record-at-stop.json").read_text()) if (STOP / f"m21-w{n}.record-at-stop.json").exists() else {"targets": []}
    for t in rec["targets"]:
        rel, func = t["target"].split("::")
        src = (W / rel).read_text(encoding="utf-8")
        muts = m.mutants(src, func, m._enum_members(src, W))
        sizes = [len(src.encode())] + [len(s.encode()) for _, s in muts]
        same = [(muts[i - 2][0] if i > 1 else "<original>", muts[i - 1][0]) for i in range(1, len(sizes)) if sizes[i] == sizes[i - 1]]
        rows.append({"worker": f"m21-w{n}", "target": t["target"], "mutants": t.get("mutants"), "killed": t.get("killed"),
                     "survivors": len(t.get("survivors") or []), "timeouts": t.get("killed_by_timeout"), "error": t.get("error"),
                     "kill_tests": t.get("kill_tests"), "mutant_list_matches": [r["mutant"] for r in t.get("results", [])] == [d for d, _ in muts],
                     "consecutive_same_size_pairs": len(same), "examples": same[:3]})
(STOP / "reuse-scan.json").write_text(json.dumps(rows, indent=1) + "\n")
for r in rows:
    print(f"{r['worker']} {r['target']:60s} mut {r['mutants']:>3} surv {r['survivors']:>2} tmo {r['timeouts']} same-size-consecutive {r['consecutive_same_size_pairs']:>2} list-ok {r['mutant_list_matches']}")
print(len(rows), "completed targets;", sum(1 for r in rows if r["consecutive_same_size_pairs"] == 0), "with no consecutive same-size pair")
