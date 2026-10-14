"""scope7.py OUT_DIR: what campaign 7 measures, and why — the targets whose campaign-6 result (a770fbb) is no ground at
the head the read-set was measured at (534435f), and the chain that carries every other result to it.

Campaign 5 measured all 528 targets (289885e). Campaign 6 re-measured 56 (a770fbb). After it, one kill file changed
(test_v21_r3_judge_not_run.py: exact assertions) and one was added (test_v21_r4_probe_record.py), registered for the
targets of `_probe`, `_judge` and (the first, for `_sections`) — because two skeptics refuted three audits. Two deltas at
the one head, both with the read-set of that head:

    delta-from-289885e   the chain for the campaign-5 results: re-measure = the 56 of campaign 6, 472 stand (8 of them
                         read changed code opened by an import, cleared as in campaign 6)
    delta-from-a770fbb   what campaign 6's results need: re-measure = the three below; 525 stand (26 read changed data
                         by the delta's rule — a listed ancestor directory — cleared by the exact reading)

Writes OUT_DIR/SCOPE.json and OUT_DIR/targets.txt. Reads committed files only."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[5]
out = pathlib.Path(sys.argv[1])
E = ROOT / "closure-evidence/v2/v2.1/campaign-7"
c5 = json.loads((E / "delta-from-289885e/DELTA.json").read_text())
c6 = json.loads((E / "delta-from-a770fbb/DELTA.json").read_text())
a5 = json.loads((E / "DATA-READ-ANALYSIS-from-289885e.json").read_text())["targets"]
a6 = json.loads((E / "DATA-READ-ANALYSIS-from-a770fbb.json").read_text())["targets"]
assert c5["head"] == c6["head"] and c5["read_set"]["commit"] == c6["read_set"]["commit"] == c6["head"]
modules = json.loads((ROOT / "closure-evidence/v2/v2.1/campaign-6/CHANGED-FUNCTIONS.json").read_text())["modules"]
rows = {}
for t, v in sorted(c6["targets"].items()):
    now = v["verdict"].startswith("re-measure")
    if v["data_read"] and not now:
        a = a6[t]
        now = bool(a["listings_that_changed"] or a["exactly_read_and_changed"])
    since5 = c5["targets"][t]["verdict"].startswith("re-measure")
    if c5["targets"][t]["data_read"] and not since5:
        a = a5[t]
        since5 = not (not a["listings_that_changed"] and all(modules.get(f) == "unchanged" for f in a["exactly_read_and_changed"]))
    rows[t] = {"role": "REMEASURE" if now else "STANDS", "reasons": v["reasons"] if now else [],
               "result_from": "campaign 7 (this campaign)" if now else
               ("campaign 6 (a770fbb)" if since5 else "campaign 5 (289885e)")}
run = sorted(t for t, r in rows.items() if r["role"] == "REMEASURE")
out.mkdir(parents=True, exist_ok=True)
(out / "SCOPE.json").write_text(json.dumps({
    "record": "AISEF V2.1 — campaign 7 scope: which targets are measured, and why", "head": c6["head"],
    "read_set": c6["read_set"]["commit"], "delta_bases": {"campaign 5": c5["base"], "campaign 6": c6["base"]},
    "targets": rows}, indent=1, ensure_ascii=False) + "\n")
(out / "targets.txt").write_text("".join(t + "\n" for t in run))
import collections  # noqa: E402
print(len(run), "targets:", run, "| result from:", dict(collections.Counter(r["result_from"] for r in rows.values())))
