#!/usr/bin/env python3 -P
"""make_queue.py C: write the supplementary campaign's queue into C.
  queue.txt : the 90 scope targets, one per line, LARGEST mutant-estimate first (so a giant is never left for
              the tail; two workers then pull the rest atomically).
  queue.tsv : target \\t mutants \\t kill_tests \\t weight  (weight = mutant estimate, the ETA upper bound unit).
The scope is SUPPLEMENTARY-SCOPE.json (62 MISSING ∪ closure-affected); mutant estimates from the manifest.
Read-only on the repo. Run from the v21 worktree root:  python -P <this> <campaign_dir>
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[5]
V21 = ROOT / "closure-evidence" / "v2" / "v2.1"
sys.path.insert(0, str(ROOT / "validation" / "v2"))
import mutation as m                                           # noqa: E402

C = pathlib.Path(sys.argv[1]); C.mkdir(parents=True, exist_ok=True)
scope = json.load(open(V21 / "SUPPLEMENTARY-SCOPE.json"))["targets"]
mut = {t: v["mutants"] for t, v in json.load(open(V21 / "REQUALIFICATION-MANIFEST-9.json"))["mutation"]["targets"].items()}
assert len(scope) == 90, f"scope != 90: {len(scope)}"
assert all(t in m.TARGETS for t in scope), "a scope target is not a mutation target"

ordered = sorted(scope, key=lambda t: mut.get(t, 0), reverse=True)
(C / "queue.txt").write_text("\n".join(ordered) + "\n", encoding="utf-8")
with open(C / "queue.tsv", "w", encoding="utf-8") as f:
    for t in ordered:
        f.write(f"{t}\t{mut.get(t,0)}\t{len(m.TARGETS[t])}\t{float(mut.get(t,0))}\n")
print(f"queue: {len(ordered)} targets, {sum(mut.get(t,0) for t in ordered)} mutant-estimate; "
      f"largest {ordered[0]} ({mut[ordered[0]]})")
