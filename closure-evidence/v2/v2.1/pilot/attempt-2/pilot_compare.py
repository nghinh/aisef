"""pilot_compare.py PILOT_DIR OUT.json: the pilot's two orders compared, per target and per mutant (owner 2026-10-07
steps 1, 2, 7). For each lane the two records (lN-decl.record.json, lN-ord.record.json): per target and order, the
classes, which file confirmed each kill and at which position of the order run, the mutant's own kill-file runs (the
chain, without the bracket's control/re-run), the runner time (every row's seconds + overhead_s, T0 included) and the
worker wall time; then per mutant whether the class is the same in both orders. A class that differs is listed whole."""
import collections, datetime, json, pathlib, sys

P, OUT = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])


def wall(name):
    t = [datetime.datetime.fromisoformat((P / f"{name}.{x}").read_text().strip().replace("Z", "+00:00"))
         for x in ("started", "finished")]
    return (t[1] - t[0]).total_seconds()


def per_target(entry):
    order = (entry.get("execution_order") or {}).get("files") or entry["kill_tests"]
    rows = [r for m in entry["results"] for r in m.get("files", [])] + entry.get("t0", []) + entry.get("original", [])
    own = [r for m in entry["results"] for r in m.get("files", []) if not r.get("role")]
    pos = collections.Counter()
    for m in entry["results"]:
        if m["class"] == "KILLED":
            pos[order.index(m["killed_by"]["file"]) + 1] += 1
    cls = collections.Counter(m["class"] for m in entry["results"])
    return {"order": order, "mutants": entry["mutants"], "classes": dict(cls),
            "kill_position": dict(sorted(pos.items())), "own_runs": len(own),
            "full_chains": sum(1 for m in entry["results"] if m["class"] != "KILLED"),
            "runner_seconds": round(sum(r.get("seconds", 0) + r.get("overhead_s", 0) for r in rows), 1),
            "t0_seconds": round(sum(r.get("seconds", 0) for r in entry.get("t0", [])), 1),
            "error": entry.get("error"), "stopped": entry.get("stopped"),
            "survivors": [m["mutant"] for m in entry["results"] if m["class"] == "SURVIVED"],
            "timeout_infra_notrun": {m["mutant"]: m["class"] for m in entry["results"]
                                     if m["class"] in ("TIMEOUT", "INFRA", "NOT_RUN")},
            # keyed by generator position: two mutants can share a description (the same edit at two sites)
            "_by_mutant": {(i, m["mutant"]): (m["class"], (m.get("killed_by") or {}).get("file"))
                           for i, m in enumerate(entry["results"])}}


out = {"lanes": {}, "targets": {}, "differ": [], "totals": collections.Counter()}
for lane in sorted({p.name.split("-")[0] for p in P.glob("l*-decl.record.json")}):
    recs = {}
    for mode in ("decl", "ord"):
        f = P / f"{lane}-{mode}.record.json"
        recs[mode] = {e["target"]: e for e in json.loads(f.read_text())["targets"]} if f.exists() else {}
        out["lanes"].setdefault(lane, {})[mode] = {"wall_s": wall(f"{lane}-{mode}") if (P / f"{lane}-{mode}.finished").exists() else None,
                                                   "log_tail": (P / f"{lane}-{mode}.log").read_text().splitlines()[-3:]
                                                   if (P / f"{lane}-{mode}.log").exists() else ["not run"]}
    for t in sorted(set(recs["decl"]) | set(recs["ord"])):
        d = {mode: per_target(recs[mode][t]) for mode in recs if t in recs[mode]}
        if len(d) == 2:
            bd, bo = d["decl"].pop("_by_mutant"), d["ord"].pop("_by_mutant")
            same = [k for k in bd if bd[k][0] == bo.get(k, (None,))[0]]
            assert set(bd) == set(bo), f"{t}: the two orders' records list different mutants"
            diff = [{"target": t, "index": k[0], "mutant": k[1], "decl": bd[k], "ord": bo.get(k)} for k in bd if k not in same]
            out["differ"] += diff
            d["compare"] = {"mutants": len(bd), "same_class": len(same), "differ": len(diff),
                            "same_killing_file": sum(1 for k in same if bd[k][1] == bo[k][1]),
                            "runner_seconds_ratio_ord_over_decl": round(d["ord"]["runner_seconds"] / d["decl"]["runner_seconds"], 3)
                            if d["decl"]["runner_seconds"] else None,
                            "own_runs_decl_ord": [d["decl"]["own_runs"], d["ord"]["own_runs"]]}
            for mode in ("decl", "ord"):
                out["totals"][f"{mode}_runner_seconds"] += d[mode]["runner_seconds"]
                out["totals"][f"{mode}_own_runs"] += d[mode]["own_runs"]
            out["totals"]["mutants"] += len(bd); out["totals"]["same_class"] += len(same)
        else:
            for v in d.values():
                v.pop("_by_mutant")
        out["targets"][t] = {"lane": lane, **d}
out["totals"] = dict(out["totals"])
OUT.write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out["totals"]), f"differ={len(out['differ'])}")
