"""t0_reuse_estimate.py SWEEP QUEUE_TSV FORECAST: the numbers of T0-BASELINE-REUSE.md §3. Read-only; prints only.

SWEEP: closure-evidence/v2/v2.1/T0-SWEEP-2.json (one T0 row per distinct (null mutant, kill file) pair, `targets` the
targets that hold it). QUEUE_TSV: campaign-2/tools/queue.tsv (target, mutants, chain = the sum of its kill files' sweep
T0 seconds), in queue order. FORECAST: pilot/attempt-2/forecast.json (`ord`: T0 load, cost ratios, survivor rate).

s_p = the pair's sweep T0 seconds + overhead_s; n_p = the queued targets holding pair p; L = the pilot's T0 load.
  today            L * sum_p n_p * s_p
  one per pair     L * sum_p s_p                       (campaign-wide sharing: excluded by the conditions of §4)
  one per worker   L * sum_p min(n_p, 4) * s_p         (an upper bound of the cost with an unbounded window)
  window h         a model of the queue: 4 workers take targets in queue order, each when free, a target costing
                   forecast.py's chain * L + n * (s * S + (1 - s) * K) * chain; a (target, file) T0 is saved when the
                   same worker ran an own T0 of the same pair that started at most h hours earlier. The schedule is the
                   no-reuse one (the saving does not move later targets earlier).
  sentinel f       a fraction f of the reuse opportunities runs its own T0 anyway: saving * (1 - f).
PILOT_DIR (optional, pilot/attempt-2): its T0 rows (decl and ord lanes) against each other and against the sweep's row
of the same pair — the reference (outcome, counts, skipped ids, first_test) and tail_sha256 (§8 step 0)."""
import json
import pathlib
import sys

sweep, queue_tsv, forecast = (pathlib.Path(a) for a in sys.argv[1:4])
rows = json.loads(sweep.read_text(encoding="utf-8"))["rows"]
queue = [(c[0], int(c[1]), float(c[2])) for c in (ln.split("\t") for ln in queue_tsv.read_text(encoding="utf-8").splitlines())]
f = json.loads(forecast.read_text(encoding="utf-8"))["ord"]
L, s, K, S = (f["t0_load_median"], f["survivor_rate"], f["killed_cost_over_chain"]["mutant_weighted"],
              f["survived_cost_over_chain_median"])
queued = {t for t, _, _ in queue}
pairs = {}   # target -> [(pair key, s_p)]
cost = {}    # pair key -> (n_p, s_p)
for r in rows:
    t0 = [x for x in r["rows"] if x.get("role") == "t0"]
    assert len(t0) == 1 and t0[0]["outcome"] == "PASS" and not t0[0].get("residue") and not t0[0].get("leaked"), r["key"]
    sp = t0[0]["seconds"] + t0[0].get("overhead_s", 0)
    held = [t for t in r["targets"] if t in queued]
    cost[r["key"]] = (len(held), sp)
    for t in held:
        pairs.setdefault(t, []).append((r["key"], sp))
for t, _, chain in queue:   # the queue's chain is the sum of its pairs' sweep seconds (overhead left out)
    sweep_chain = sum(x["seconds"] for r in rows if t in r["targets"] for x in r["rows"] if x.get("role") == "t0")
    assert abs(round(sweep_chain, 1) - chain) < 0.11, t
used = {k: v for k, v in cost.items() if v[0]}
today = L * sum(n * sp for n, sp in used.values())
one = L * sum(sp for _, sp in used.values())
per_w = L * sum(min(n, 4) * sp for n, sp in used.values())
print(f"queued targets {len(queue)}, pairs held {len(used)} of {len(rows)}, (target, kill file) T0 runs "
      f"{sum(n for n, _ in used.values())}; pairs held by one target {sum(1 for n, _ in used.values() if n == 1)}")
print(f"L = {L}; forecast {f['forecast']['pilot']['worker_hours']} worker-h at the pilot's survivor rate")
print(f"today {today / 3600:.1f} h | one per pair {one / 3600:.1f} h (saves {(today - one) / 3600:.1f}) | "
      f"one per worker <= {per_w / 3600:.1f} h (saves >= {(today - per_w) / 3600:.1f})")
for h in (1, 2, 6, 12, 24, float("inf")):
    free, own, saved, n_reused, n_runs = [0.0] * 4, {}, 0.0, 0, 0
    for t, n, chain in queue:
        w = min(range(4), key=lambda i: (free[i], i))
        for key, sp in pairs[t]:
            n_runs += 1
            last = own.get((w, key))
            if last is not None and free[w] - last <= h * 3600:
                saved, n_reused = saved + L * sp, n_reused + 1
            else:
                own[(w, key)] = free[w]
        free[w] += chain * L + n * (s * S + (1 - s) * K) * chain
    print(f"window {h} h: reused {n_reused}/{n_runs}, saves {saved / 3600:.1f} h ({saved / today:.0%} of T0); "
          f"with sentinels f=0.1 {0.9 * saved / 3600:.1f} h; makespan of the model {max(free) / 3600:.1f} h")
if len(sys.argv) > 4:
    def ref(x):
        return (x["outcome"], x.get("ran"), x.get("skipped", 0), x.get("expected_failures", 0),
                x.get("unexpected_successes", 0), tuple(x.get("skipped_tests", [])), x.get("first_test"))
    own = {}   # (target, file) -> [the sweep's row of its pair, then each pilot lane's row]
    for r in rows:
        for t in r["targets"]:
            own[(t, r["file"])] = [x for x in r["rows"] if x.get("role") == "t0"]
    seen = set()
    for p in sorted(pathlib.Path(sys.argv[4]).glob("l*-*.record.json")):
        for t in json.loads(p.read_text(encoding="utf-8"))["targets"]:
            for x in t.get("t0", []):
                own[(t["target"], x["file"])].append(x)
                seen.add((t["target"], x["file"]))
    runs = [own[k] for k in sorted(seen)]
    print(f"pilot: {len(runs)} (target, file) pairs, {sorted({len(v) for v in runs})} T0 rows each (sweep + lanes); "
          f"reference identical in all rows {sum(len({ref(x) for x in v}) == 1 for v in runs)}, "
          f"tail_sha256 identical {sum(len({x['tail_sha256'] for x in v}) == 1 for v in runs)}")
    for k in sorted(seen):
        if len({x["tail_sha256"] for x in own[k]}) > 1:
            print("  tail differs:", k, "references", "identical" if len({ref(x) for x in own[k]}) == 1 else "DIFFER")
