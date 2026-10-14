"""scope6.py OUT_DIR: what campaign 6 measures, and why — one row per V2.1 target.

Campaign 5 measured all 528 targets at one snapshot (289885e). Since then: confine.py (_sections, _judge),
process_range.py (_Posix.abort), mutation.py (data: kill sets) and kill files changed, and new kill files were added.

    role    REMEASURE  the delta (campaign-6/delta/DELTA.json: base 289885e, head = the commit the read-set was measured
                       at) says re-measure: the target file changed, its kill set changed, a kill-test closure file
                       changed, or a file its kill files read changed
            TRACE      the delta says the result can stand, but campaign-6/trace.json (validation/v21/trace_paths.py)
                       shows one of its kill files REACHED a changed path (a try without an exit status; abort's absent
                       group), or did not PASS under the marks (so was not measured): re-measured
            DATA       the delta says the result can stand by the proof's rules, but a kill file of the target READS a
                       changed file inside mutation.COPY (the measured read-set: counts.data_read) or a changed
                       file's reading was not measured, and the exact reading (data_read_analysis.py) does not clear
                       it: re-measured. Cleared (`data_read_cleared` in the row): a listing of a directory whose
                       children did not change, and a changed file that is code OPENED (imported) by a module whose
                       import-time statements are unchanged
            STANDS     the result stands: the delta's rules (target file, kill set, kill-test closure, generator, data
                       read) and the trace (no kill file of the target reached a changed path; every one passed under
                       the marks); the campaign-5 result (289885e)
Writes OUT_DIR/SCOPE.json and OUT_DIR/targets.txt (the targets campaign 6 runs; sorted). Reads committed files only."""
import collections
import glob
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from validation.v2 import mutation as m  # noqa: E402

out = pathlib.Path(sys.argv[1])
E = ROOT / "closure-evidence/v2/v2.1"
delta = json.loads((E / "campaign-6/delta/DELTA.json").read_text())
trace = json.loads((E / "campaign-6/trace.json").read_text())
analysis = json.loads((E / "campaign-6/DATA-READ-ANALYSIS.json").read_text())["targets"]
changed_fn = json.loads((E / "campaign-6/CHANGED-FUNCTIONS.json").read_text())
prev = json.loads((E / "REQUALIFICATION-MANIFEST-5.json").read_text())["mutation"]["targets"]
last = {}
for f in sorted(glob.glob(str(E / "mutation-workers/c5-w*.record.json"))):
    for e in json.loads(pathlib.Path(f).read_text())["targets"]:
        last[e["target"]] = e
assert trace["complete"], "the trace is not complete: some kill file did not PASS under the marks"
hit = {k: v["hits"] for k, v in trace["kill_files"].items() if v["hits"]}
unmeasured = sorted(set(trace.get("not_passed", {})) | set(trace.get("not_measured", {})))
rows = {}
for t, kill in sorted(m.V21_TARGETS.items()):
    rel, func = t.split("::")
    src = (ROOT / rel).read_text(encoding="utf-8")
    d = delta["targets"][t]
    was = prev.get(t, {}).get("kill_tests")
    verdict = str(d["verdict"])
    role, why = ("REMEASURE", list(d.get("reasons", []))) if verdict.startswith("re-measure") else ("STANDS", [])
    cleared = None
    if t not in last:
        role, why = "REMEASURE", ["no earlier result of this target"]
    if role == "STANDS" and (d.get("data_read") or d.get("read_set_not_measured")):
        # the delta's own rule (counts.data_read): a kill file of the target READS a changed file inside mutation.COPY
        # (measured), or a changed file's reading was not measured: the 289885e result is no ground at head.
        # The delta reads a listing as "any ancestor directory"; the exact reading (data_read_analysis.py) of the same
        # measured read-set says what is left. A changed file the kill files OPENED that is code of a module whose
        # import-time statements are unchanged (reach.watch_from_diff) is loaded, not executed: only the changed
        # functions are, and trace_paths.py shows no kill file reached the behaviour they changed.
        a = analysis.get(t)
        if a and not a["listings_that_changed"] and not d.get("read_set_not_measured") and all(
                changed_fn["modules"].get(f) == "unchanged" for f in a["exactly_read_and_changed"]):
            cleared = {"by": "campaign-6/DATA-READ-ANALYSIS.json + CHANGED-FUNCTIONS.json + trace.json",
                       "opened_and_changed": a["exactly_read_and_changed"], "listings_that_changed": [],
                       "import_time_statements": {f: changed_fn["modules"][f] for f in a["exactly_read_and_changed"]},
                       "changed_functions": {f: changed_fn["watch"].get(f, []) for f in a["exactly_read_and_changed"]}}
        else:
            role = "DATA"
            notes = [x for x in d.get("outside_the_proof", []) if x.startswith(("data its kill tests", "inside mutation.COPY"))]
            why = ["; ".join(n.split(" — ")[0][:260] for n in notes) or "changed data read, not cleared by the exact reading"]
    if role == "STANDS":
        reached = sorted(k for k in kill if k in hit)
        missing = sorted(k for k in kill if k in unmeasured or k not in trace["kill_files"])
        if reached or missing:
            role = "TRACE"
            why = ([f"kill files that reached a changed path: {', '.join(reached)} {[sorted(hit[k]) for k in reached]}"] if reached else []) \
                + ([f"kill files not measured under the marks: {', '.join(missing)}"] if missing else [])
    entry = last.get(t)
    rows[t] = {"role": role, "reasons": why, "kill_files": list(kill), "kill_added": sorted(set(kill) - set(was or [])),
               "kill_removed": sorted(set(was or []) - set(kill)),
               "mutants": len(m.mutants(src, func, m._enum_members(src, ROOT))),
               **({"data_read_cleared": cleared} if cleared else {}),
               "result_from": "campaign 5 (289885e)" if entry else None,
               "result_classes": {k: v for k, v in entry["classes"].items() if v} if entry else None}
run = sorted(t for t, r in rows.items() if r["role"] != "STANDS")
out.mkdir(parents=True, exist_ok=True)
(out / "SCOPE.json").write_text(json.dumps({
    "record": "AISEF V2.1 — campaign 6 scope: which targets are measured, and why",
    "delta_base": delta["base"], "delta_head": delta["head"], "read_set": delta["read_set"]["commit"],
    "trace": {"commit": trace["commit"], "tree_sha256": trace["tree_sha256"], "paths": trace["paths"],
              "controls": [{"tag": c["tag"], "ok": c["ok"]} for c in trace["controls"]],
              "kill_files_measured": len(trace["kill_files"]), "kill_files_with_a_hit": hit},
    "harness_changed_names": delta.get("harness", {}),
    "targets": rows}, indent=1, ensure_ascii=False) + "\n")
(out / "targets.txt").write_text("".join(t + "\n" for t in run))
print(len(run), "targets,", sum(rows[t]["mutants"] for t in run), "mutants | stand:", sum(1 for r in rows.values() if r["role"] == "STANDS"),
      collections.Counter(r["role"] for r in rows.values()), "| by module:",
      collections.Counter(t.split("::")[0] for t in run).most_common(8))
