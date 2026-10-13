"""scope5.py OUT_DIR: what campaign 5 measures, and why — one row per V2.1 target.

    role    NEW        the target has no earlier result (a name round 3 added, or a module round 3 made a V2.1 module:
                       process_range.py, cleanup_authority.py)
            REMEASURE  the delta (campaign-5/delta/DELTA.json: base b5c2457 = campaign 4's snapshot, head = the commit the
                       read-set was measured at) says re-measure: the target file or its kill set changed, or a file its
                       kill files read changed
            STANDS     the result stands, on the delta's grounds: campaign 4's (b5c2457), else campaign 3's (f860e57),
                       else campaign 2's (5719f1f), each found unchanged to the later snapshots by their deltas
Writes OUT_DIR/SCOPE.json and OUT_DIR/targets.txt (the targets campaign 5 runs, sorted). Reads committed files only."""
import collections, glob, json, lzma, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from validation.v2 import mutation as m  # noqa: E402

out = pathlib.Path(sys.argv[1])
E = ROOT / "closure-evidence/v2/v2.1"
delta = json.loads((E / "campaign-5/delta/DELTA.json").read_text())
prev = json.loads((E / "REQUALIFICATION-MANIFEST-4.json").read_text())["mutation"]["targets"]
last: dict[str, tuple[str, dict]] = {}
for e in json.loads(lzma.open(E / "campaign-2/results/MUTATION.json.xz").read())["targets"]:
    last[e["target"]] = ("campaign 2 (5719f1f)", e)
for label, pat in (("campaign 3 (f860e57)", "mutation-workers/c3-w*.record.json"),
                   ("campaign 3 (f860e57)", "mutation-workers/c3b-w1.record.json"),
                   ("campaign 4 (b5c2457)", "mutation-workers/c4-w*.record.json")):
    for f in sorted(glob.glob(str(E / pat))):
        for e in json.loads(pathlib.Path(f).read_text())["targets"]:
            last[e["target"]] = (label, e)
rows = {}
for t, kill in sorted(m.V21_TARGETS.items()):
    rel, func = t.split("::")
    src = (ROOT / rel).read_text(encoding="utf-8")
    d = delta["targets"][t]
    was = prev.get(t, {}).get("kill_tests")
    new = t not in prev
    src_from, entry = last.get(t, (None, None))
    verdict = str(d["verdict"])
    role = "NEW" if new else ("REMEASURE" if verdict.startswith("re-measure") else "STANDS")
    rows[t] = {"role": role, "reasons": d.get("reasons", []),
               "kill_files": list(kill), "kill_added": sorted(set(kill) - set(was or [])),
               "kill_removed": sorted(set(was or []) - set(kill)),
               "mutants": len(m.mutants(src, func, m._enum_members(src, ROOT))),
               "result_from": src_from, "result_classes": {k: v for k, v in entry["classes"].items() if v} if entry else None}
run = sorted(t for t, r in rows.items() if r["role"] != "STANDS")
out.mkdir(parents=True, exist_ok=True)
(out / "SCOPE.json").write_text(json.dumps({"record": "AISEF V2.1 — campaign 5 scope: which targets are measured, and why",
                                            "delta_base": delta["base"], "delta_head": delta["head"],
                                            "read_set": delta["read_set"]["commit"], "targets": rows},
                                           indent=1, ensure_ascii=False) + "\n")
(out / "targets.txt").write_text("".join(t + "\n" for t in run))
print(len(run), "targets,", sum(rows[t]["mutants"] for t in run), "mutants | stand:", sum(1 for r in rows.values() if r["role"] == "STANDS"),
      collections.Counter(r["result_from"] for r in rows.values() if r["role"] == "STANDS"),
      "| new:", sum(1 for r in rows.values() if r["role"] == "NEW"))
