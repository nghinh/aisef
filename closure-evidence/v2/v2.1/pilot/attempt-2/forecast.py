"""forecast.py PILOT_DIR QUEUE_TSV: campaign-2 worker-hours from the pilot's own measurements.
Per pilot target and order, from its record: T0 seconds (rows role t0), the mean cost of a KILLED mutant (its own runs
plus the bracket, seconds + overhead) and of a SURVIVED one, each over the target's chain (sum of its kill files' T0
seconds in the sweep, QUEUE_TSV column 3). Forecast for every queued target: T0 x load + mutants x (s x survived ratio
+ (1 - s) x killed ratio) x chain, for survivor rates s = the pilot's own, 0.04 (the 2.0 S2 campaign), 0.20."""
import json, pathlib, statistics, sys
P, Q = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
rows = {l.split("\t")[0]: (int(l.split("\t")[1]), float(l.split("\t")[2])) for l in Q.read_text().splitlines()}
per = {"decl": [], "ord": []}
for f in sorted(P.glob("l*-*.record.json")):
    mode = f.name.split("-")[1].split(".")[0]
    for t in json.loads(f.read_text())["targets"]:
        n, chain = rows[t["target"]]
        cost = lambda m: sum(r.get("seconds", 0) + r.get("overhead_s", 0) for r in m.get("files", []))
        k = [cost(m) for m in t["results"] if m["class"] == "KILLED"]
        s = [cost(m) for m in t["results"] if m["class"] == "SURVIVED"]
        t0 = sum(r.get("seconds", 0) + r.get("overhead_s", 0) for r in t.get("t0", []))
        per[mode].append({"target": t["target"], "n": n, "killed": len(k), "survived": len(s), "chain": chain,
                          "t0_load": t0 / chain, "k_ratio": (sum(k) / len(k) / chain) if k else None,
                          "s_ratio": (sum(s) / len(s) / chain) if s else None,
                          "other": sum(1 for m in t["results"] if m["class"] not in ("KILLED", "SURVIVED"))})
out = {}
for mode, ts in per.items():
    if not ts:
        continue
    kr = [x["k_ratio"] for x in ts if x["k_ratio"] is not None]
    sr = [x["s_ratio"] for x in ts if x["s_ratio"] is not None]
    load = statistics.median(x["t0_load"] for x in ts)
    s_pilot = sum(x["survived"] for x in ts) / sum(x["n"] for x in ts)
    k_w = sum(x["k_ratio"] * x["killed"] for x in ts if x["k_ratio"]) / sum(x["killed"] for x in ts)   # mutant-weighted
    s_w = statistics.median(sr) if sr else load
    fc = {}
    for label, s in (("pilot", s_pilot), ("s2_2.0", 0.04), ("high", 0.20)):
        tot = sum(chain * load + n * (s * s_w + (1 - s) * k_w) * chain for n, chain in rows.values())
        fc[label] = {"survivor_rate": round(s, 3), "worker_hours": round(tot / 3600, 1)}
    out[mode] = {"targets": len(ts), "mutants": sum(x["n"] for x in ts), "survivor_rate": round(s_pilot, 3),
                 "killed_cost_over_chain": {"mutant_weighted": round(k_w, 3), "median": round(statistics.median(kr), 3),
                                            "min": round(min(kr), 3), "max": round(max(kr), 3)},
                 "survived_cost_over_chain_median": round(s_w, 3), "t0_load_median": round(load, 3),
                 "not_killed_or_survived": sum(x["other"] for x in ts), "forecast": fc, "per_target": ts}
print(json.dumps({m: {k: v for k, v in o.items() if k != "per_target"} for m, o in out.items()}, indent=1))
(P / "forecast.json").write_text(json.dumps(out, indent=1) + "\n")
