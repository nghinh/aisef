"""scope4.py OUT_DIR: what campaign 4 measures, and why — one row per V2.1 target.

    role    REMEASURE  the delta (campaign-4/delta/DELTA.json: base f860e57 = campaign 3's snapshot, head = the commit the
                       read-set was measured at) says re-measure: the target file or its kill set changed, or a file its
                       kill files read changed
            STANDS     the result stands: campaign 3's (measured at f860e57) or, for a target campaign 3 did not run,
                       campaign 2's (5719f1f, which campaign 3's delta found unchanged to f860e57)
Writes OUT_DIR/SCOPE.json and OUT_DIR/targets.txt (the targets campaign 4 runs, sorted). Reads committed files only."""
import collections, glob, json, lzma, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from validation.v2 import mutation as m  # noqa: E402

out = pathlib.Path(sys.argv[1])
E = ROOT / "closure-evidence/v2/v2.1"
delta = json.loads((E / "campaign-4/delta/DELTA.json").read_text())
prev = json.loads((E / "REQUALIFICATION-MANIFEST-3.json").read_text())["mutation"]["targets"]
c3 = {}
for f in sorted(glob.glob(str(E / "mutation-workers/c3-w*.record.json"))) + [str(E / "mutation-workers/c3b-w1.record.json")]:
    for e in json.loads(pathlib.Path(f).read_text())["targets"]:
        c3[e["target"]] = e          # c3b-w1 last: the re-run of the two targets that did not close
c2 = {e["target"]: e for e in json.loads(lzma.open(E / "campaign-2/results/MUTATION.json.xz").read())["targets"]}
rows = {}
for t, kill in sorted(m.V21_TARGETS.items()):
    rel, func = t.split("::")
    src = (ROOT / rel).read_text(encoding="utf-8")
    d = delta["targets"][t]
    was = prev.get(t, {}).get("kill_tests") or []
    last = c3.get(t) or c2.get(t)
    rows[t] = {"role": "REMEASURE" if d["verdict"].startswith("re-measure") else "STANDS", "reasons": d.get("reasons", []),
               "kill_files": list(kill), "kill_added": sorted(set(kill) - set(was)), "kill_removed": sorted(set(was) - set(kill)),
               "mutants": len(m.mutants(src, func, m._enum_members(src, ROOT))),
               "result_from": "campaign 3 (f860e57)" if t in c3 else "campaign 2 (5719f1f)",
               "result_classes": {k: v for k, v in last["classes"].items() if v} if last else None}
run = sorted(t for t, r in rows.items() if r["role"] == "REMEASURE")
out.mkdir(parents=True, exist_ok=True)
(out / "SCOPE.json").write_text(json.dumps({"record": "AISEF V2.1 — campaign 4 scope: which targets are measured, and why",
                                            "delta_base": delta["base"], "delta_head": delta["head"], "read_set": delta["read_set"]["commit"],
                                            "targets": rows}, indent=1, ensure_ascii=False) + "\n")
(out / "targets.txt").write_text("".join(t + "\n" for t in run))
print(len(run), "targets,", sum(rows[t]["mutants"] for t in run), "mutants | stand:", sum(1 for r in rows.values() if r["role"] == "STANDS"),
      collections.Counter(r["result_from"] for r in rows.values() if r["role"] == "STANDS"))
