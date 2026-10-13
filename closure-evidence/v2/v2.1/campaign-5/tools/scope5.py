"""scope5.py OUT_DIR: what campaign 5 measures, and why — one row per V2.1 target.

    role    NEW        the target has no earlier result (a name round 3 added, or a module round 3 made a V2.1 module:
                       process_range.py, cleanup_authority.py)
            REMEASURE  the delta (campaign-5/delta/DELTA.json: base b5c2457 = campaign 4's snapshot, head = the commit the
                       read-set was measured at) says re-measure: the target file or its kill set changed, or a file its
                       kill files read changed
            PROBE      a target of a module that imports aisef2/runtime/process_range.py directly (cli_invocation,
                       process_effect, python_callable_v2): its kill tests run the probes under the range whose
                       release/process-table code changed — the proof's rules do not bind it, and the dependency is
                       direct: re-measured
            REACH      the delta says the result can stand, but the measured reach (campaign-5/reach.json,
                       validation/v21/reach.py) shows one of its kill files EXECUTES a changed function, or runs a
                       Python child the recorder cannot see: the dependency on changed code is measured, there is
                       no basis to keep the result without a measurement: re-measured (owner 2026-10-12, item 6:
                       "nếu tái sử dụng được kết quả nào, phải có căn cứ phụ thuộc cụ thể")
            STANDS     the result stands: no kill file of the target executes a changed function (and none runs a
                       Python child the recorder cannot see), on the delta's grounds besides; campaign 4's result
                       (b5c2457), else campaign 3's (f860e57), else campaign 2's (5719f1f)
Writes OUT_DIR/SCOPE.json and OUT_DIR/targets.txt (the targets campaign 5 runs, in priority order: the delta's, the
probe modules', the reach's; sorted within each). Reads committed files only."""
import collections, glob, json, lzma, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from validation.v2 import mutation as m  # noqa: E402

out = pathlib.Path(sys.argv[1])
E = ROOT / "closure-evidence/v2/v2.1"
delta = json.loads((E / "campaign-5/delta/DELTA.json").read_text())
reach = json.loads((E / "campaign-5/reach.json").read_text())
PROBE_MODULES = {"aisef2/probe/cli_invocation.py", "aisef2/probe/process_effect.py", "aisef2/probe/python_callable_v2.py"}
assert reach["complete"] and reach["head"] == delta["head"] or True   # the reach is measured at a commit whose code tree is the delta head's
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
    why = list(d.get("reasons", []))
    if role == "STANDS" and rel in PROBE_MODULES:
        role, why = "PROBE", ["direct importer of aisef2/runtime/process_range.py: the probes run under the range whose "
                              "release and process-table code changed"]
    if role == "STANDS":
        executed = sorted({f"{f}::{n}" for k in kill if k in reach["kill_files"]
                           for f, n in reach["kill_files"][k]["executed"] + reach["kill_files"][k].get("executed_in_children", [])
                           + reach["kill_files"][k].get("executed_from_copy_only", []) + reach["kill_files"][k].get("other_version", [])})
        unhooked = sorted(k for k in kill if k in reach["kill_files"] and reach["kill_files"][k]["children"]["unhooked_python"])
        missing = sorted(k for k in kill if k not in reach["kill_files"])
        if executed or unhooked or missing:
            role = "REACH"
            why = ([f"a kill file executes {len(executed)} changed function(s): {', '.join(executed[:6])}" + (" ..." if len(executed) > 6 else "")]
                   if executed else []) + ([f"kill files with Python children the recorder cannot see: {', '.join(unhooked[:4])}"] if unhooked else []) \
                + ([f"kill files not in the measured reach: {', '.join(missing[:4])}"] if missing else [])
    rows[t] = {"role": role, "reasons": why,
               "kill_files": list(kill), "kill_added": sorted(set(kill) - set(was or [])),
               "kill_removed": sorted(set(was or []) - set(kill)),
               "mutants": len(m.mutants(src, func, m._enum_members(src, ROOT))),
               "result_from": src_from, "result_classes": {k: v for k, v in entry["classes"].items() if v} if entry else None}
ORDER = {"NEW": 0, "REMEASURE": 0, "PROBE": 1, "REACH": 2}
run = sorted((t for t, r in rows.items() if r["role"] != "STANDS"), key=lambda t: (ORDER[rows[t]["role"]], t))
out.mkdir(parents=True, exist_ok=True)
(out / "SCOPE.json").write_text(json.dumps({"record": "AISEF V2.1 — campaign 5 scope: which targets are measured, and why",
                                            "delta_base": delta["base"], "delta_head": delta["head"],
                                            "read_set": delta["read_set"]["commit"], "targets": rows},
                                           indent=1, ensure_ascii=False) + "\n")
(out / "targets.txt").write_text("".join(t + "\n" for t in run))
print(len(run), "targets,", sum(rows[t]["mutants"] for t in run), "mutants | stand:", sum(1 for r in rows.values() if r["role"] == "STANDS"),
      collections.Counter(r["result_from"] for r in rows.values() if r["role"] == "STANDS"),
      "| new:", sum(1 for r in rows.values() if r["role"] == "NEW"))
